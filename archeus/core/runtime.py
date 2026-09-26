"""The Core process (p3.5b design gate §3 D4, §5, §7): the one writer and the
one engine for a home, reachable over HTTP.

Start, in this order; stop in the reverse:

    1 take run/core.lock (another holder: refuse, touching nothing else)
    2 open the database (starts the writer thread)
    3 ensure the local token (run/local-token, hash in `tokens`)
    4 start the engine thread: the boot reconciliation sweep, then the loop
    5 start the world thread: the inspection sweep, then the loop (P4)
    6 bind HTTP on 127.0.0.1:<port>
    7 write run/core.json

One Engine per Core, built here and only here (and by the in-process judge
binding, which takes the same lock). It is never re-created inside a process:
a new instance treats every execution the old one started as an orphan and
kills it — adoption is P11's. The engine loop steps every mission that is not
settled; a step that changed nothing PARKS the mission at its version, and a
parked mission is stepped again only once some command has moved it. A lost
race with an HTTP command (IllegalTrigger, GuardFailed, VersionConflict) is
logged and skipped; any other exception fails Core (exit 3). Nothing here
runs inside a transaction: every change is one writer command.

The intent worker (P7, `archeus-intent`) reads every user message: the
control grammar, else one brain call through `archeus_call`, applied by one
command. It is the knowledge worker's shape and shares its OwnCalls.

The world worker (P4) is the same shape: one per Core, a failing repository is
a FAILED inspection, and any other exception fails Core (exit 3). It passes
every WORLD_POLL_S seconds, on every commit, and whenever `pending()` finds
due work (a health check does), so nothing waits a poll interval to be seen.
"""

import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field

from claude_sessions import proc

from ..api import auth, server
from ..harnesses.fake import FakeHarness
from ..harnesses.registry import AdapterRegistry
from ..infra import discovery, paths
from ..infra.db import Database
from ..infra.eventlog import outbox
from . import engine, ports as P
from .application import commands, errors, queries, work
from ..harnesses.calls import real_callers
from .calls import OwnCalls
from .domain.values import Ref
from .application.conversation import Conversations
from .knowledge.passes import Passes
from .knowledge.worker import Knowledge
from .missions.intent import Intents
from .world.worker import World

DEFAULT_PORT = 7337
IDLE_S = 1.0
WORLD_POLL_S = 10.0         # D6

log = logging.getLogger('archeus.core')


def _version():
    try:
        from importlib.metadata import version
        return version('archeus')
    except Exception:
        return 'dev'


VERSION = _version()


class PortInUse(OSError):
    pass


class RefuseStart(RuntimeError):
    """A condition Core will not start under (loose token permissions)."""


@dataclass
class Ports:
    """The ports Core runs on. P3.5b runs only stubs and the fake harness; the
    real ones arrive with P7 (brain), P9 (policy), P10 (router), P13."""
    policy: object = field(default_factory=P.AllowAllPolicy)
    brain: object = field(default_factory=lambda: P.FixedPlanBrain(engine.SKELETON_PLAN))
    verifier: object = field(default_factory=P.ScriptedVerifier)
    reviewer: object = field(default_factory=P.ScriptedReview)
    route: str = 'fake'
    scenarios: dict = field(default_factory=dict)
    # Archeus's own calls (P6, ADR-0022): the adapters offered for them (None:
    # the real ones, each gated by ADR-0021) and the own-call preference.
    callers: list = None
    preference: object = field(default_factory=P.LegacyOwnCallPreference)

    @property
    def stub(self):
        return getattr(self.policy, 'is_stub', True) is not False


class EngineLoop:
    def __init__(self, eng, db, *, idle_s=IDLE_S, on_fail=None):
        self.engine, self.db, self.idle_s, self.on_fail = eng, db, idle_s, on_fail
        self.state, self.observed_seq, self.parked = 'starting', 0, {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='archeus-engine', daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        """Signal the loop. Never waits: a step may be waiting for a child
        process, which is detached and reconciled by the next Core (§5.4)."""
        self._stop.set()
        self.db.writer.wake()

    def join(self, timeout):
        self._thread.join(timeout)

    def status(self):
        return {'state': self.state, 'observed_seq': self.observed_seq,
                'parked': len(self.parked)}

    def _run(self):
        try:
            self.state = 'reconciling'
            done = self.engine.reconcile_orphans()
            if done:
                log.info('reconciled %d orphan execution(s)', len(done))
            self.state = 'running'
            while not self._stop.is_set():
                self._pass()
            self.state = 'stopped'
        except errors.WriterClosed:
            if not self._stop.is_set():
                self._failed()
            self.state = 'stopped'
        except Exception:
            if self._stop.is_set():
                self.state = 'stopped'
            else:
                self._failed()

    def _failed(self):
        self.state = 'failed'
        log.exception('the engine thread failed; Core stops (exit 3)')
        if self.on_fail:
            self.on_fail()

    def _pass(self):
        writer = self.db.writer
        seen = writer.commit_count
        with self.db.read() as conn:
            head = outbox.head(conn)
            live = [(m['id'], m['version']) for m in queries.list_missions(conn)
                    if m['state'] not in engine.SETTLED]
        progressed = False
        for mid, version in live:
            if self._stop.is_set():
                return
            if self.parked.get(mid) == version:
                continue
            # `running` only while a mission is stepped: a pass that re-reads
            # parked missions and finds nothing to do is still idle (health
            # sampled it as running on one idle wake-up in five once P7 added
            # a worker thread). The idle signal stays safe: `observed_seq`
            # moves only at the end of a pass, so an unseen commit is not idle.
            self.state = 'running'
            try:
                out = self.engine.step(mid)
            except errors.LOST_RACE as e:
                # a command moved the mission between our read and our fire;
                # the guards refused the stale move. Parked at the version we
                # read: stepped again only if it moves, so a refusal that is
                # really a bug cannot spin
                log.info('engine lost a race on %s: %s', mid, e)
                self.parked[mid] = version
                continue
            if out['changed']:
                progressed = True
                self.parked.pop(mid, None)
            else:
                self.parked[mid] = version
        ids = {m for m, _v in live}
        self.parked = {m: v for m, v in self.parked.items() if m in ids}
        if progressed:
            return
        self.observed_seq, self.state = head, 'idle'
        writer.wait_commit(seen, self.idle_s, until=self._stop.is_set)


class WorldLoop:
    """A worker thread: the boot sweep, then passes — `archeus-world` (P4),
    `archeus-knowledge` (P6) and `archeus-intent` (P7). It waits on the writer's commit notification with
    the poll interval as its timeout, and `wake()` (called by the worker's
    `pending()` when it finds due work) ends a wait early."""

    def __init__(self, world, db, *, poll_s=WORLD_POLL_S, on_fail=None, name='archeus-world'):
        self.world, self.db, self.poll_s, self.on_fail = world, db, poll_s, on_fail
        self.name, self.state = name, 'starting'
        self._stop, self._wake = threading.Event(), threading.Event()
        world.on_wake = self.wake
        world.stopping = self._stop.is_set
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self):
        self._thread.start()

    def wake(self):
        self._wake.set()
        self.db.writer.wake()

    def stop(self):
        self._stop.set()
        self.db.writer.wake()

    def join(self, timeout):
        self._thread.join(timeout)

    def status(self):
        pending = self.world.pending() if self.state in ('idle', 'running') else 0
        return {'state': self.state, 'pending': pending}

    def _run(self):
        try:
            self.state = 'reconciling'
            swept = self.world.sweep()
            if swept:
                log.info('%s: failed %d item(s) a previous Core left running', self.name,
                         len(swept))
            while not self._stop.is_set():
                seen = self.db.writer.commit_count
                self.state = 'running'
                if self.world.pass_once()['changed']:
                    continue
                self.state = 'idle'
                self.db.writer.wait_commit(
                    seen, self.poll_s, until=lambda: self._stop.is_set() or self._wake.is_set())
                self._wake.clear()
            self.state = 'stopped'
        except errors.WriterClosed:
            self.state = 'stopped'
            if not self._stop.is_set():
                self._failed()
        except Exception:
            if self._stop.is_set():
                self.state = 'stopped'
            else:
                self._failed()

    def _failed(self):
        self.state = 'failed'
        log.exception('the %s thread failed; Core stops (exit 3)', self.name)
        if self.on_fail:
            self.on_fail()


class Core:
    def __init__(self, *, port=DEFAULT_PORT, ports=None, heartbeat_s=15.0, idle_s=IDLE_S,
                 launch_clock=time.monotonic, lock_retry_s=2.0, static_dir=server.STATIC_DIR,
                 world_poll_s=WORLD_POLL_S):
        self.port, self.ports = port, ports or Ports()
        self.heartbeat_s, self.idle_s = heartbeat_s, idle_s
        self.launch_clock, self.lock_retry_s = launch_clock, lock_retry_s
        self.static_dir, self.world_poll_s = static_dir, world_poll_s
        self.lock = self.db = self.loop = self.world = self.api = self.server = None
        self.knowledge = self.intent = None
        self.warning = None
        self.exit_code = 0
        self._done = threading.Event()
        self._log_handler = None

    # ── start ──

    def start(self):
        self.lock = discovery.acquire(self.lock_retry_s)
        try:
            self._start()
        except BaseException:
            self.stop()
            raise
        return self

    def _start(self):
        ok, self.warning = discovery.token_protection()
        if not ok:
            raise RefuseStart(self.warning)
        self._open_log()
        self.started_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        self.db = Database.open()
        with self.db.read() as conn:
            self.schema = conn.execute('PRAGMA user_version').fetchone()[0]
            system = queries.system_principal(conn)
        if system is None:
            system = self.db.writer.execute(commands.register_principal, {
                'kind': 'system', 'scopes': ('system',)})['id']
        self.system = Ref('system', system)
        self.local = self._ensure_local_token()
        if self.warning:
            log.warning(self.warning)

        self.missions = commands.Missions(policy=self.ports.policy)
        registry = AdapterRegistry(self.ports.policy)
        registry.register(FakeHarness())
        eng = engine.Engine(
            self.db, actor=self.system,
            work=work.Work(missions=self.missions,
                           router=P.FixedCandidateRouter(self.ports.route)),
            brain=self.ports.brain, registry=registry, verifier=self.ports.verifier,
            reviewer=self.ports.reviewer, scenarios=self.ports.scenarios)
        self.loop = EngineLoop(eng, self.db, idle_s=self.idle_s, on_fail=self._engine_failed)
        self.loop.start()
        self.world = WorldLoop(World(self.db, actor=self.system), self.db,
                               poll_s=self.world_poll_s, on_fail=self._engine_failed)
        self.world.start()
        callers = self.ports.callers
        own = OwnCalls(self.db, actor=self.system,
                       callers=real_callers() if callers is None else callers,
                       preference=self.ports.preference)
        self.knowledge = WorldLoop(Knowledge(self.db, actor=self.system,
                                             passes=Passes(self.db, actor=self.system,
                                                           calls=own)),
                                   self.db, poll_s=self.world_poll_s,
                                   on_fail=self._engine_failed, name='archeus-knowledge')
        self.knowledge.start()
        self.conversations = Conversations(missions=self.missions)
        self.intent = WorldLoop(Intents(self.db, actor=self.system, calls=own,
                                        conversations=self.conversations,
                                        after='knowledge'),
                                self.db, poll_s=self.world_poll_s,
                                on_fail=self._engine_failed, name='archeus-intent')
        self.intent.start()

        self.api = server.Api(db=self.db, missions=self.missions,
                              conversations=self.conversations, port=self.port,
                              health=self.health, version=VERSION,
                              heartbeat_s=self.heartbeat_s, launch_clock=self.launch_clock,
                              static_dir=self.static_dir)
        try:
            self.server = server.Server(self.api, self.port)
        except OSError as e:
            raise PortInUse('port %d is in use (%s)' % (self.port, e)) from e
        threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.2},
                         name='archeus-http', daemon=True).start()
        discovery.write_core_json({
            'pid': os.getpid(), 'create_time': proc.process_create_time(os.getpid()),
            'port': self.port, 'started_at': self.started_at, 'version': VERSION,
            'schema': self.schema})
        log.info('Core started on 127.0.0.1:%d (pid %d)', self.port, os.getpid())

    def _open_log(self):
        logs = os.path.join(paths.archeus_home(), 'logs')
        os.makedirs(logs, exist_ok=True)
        self._log_handler = logging.FileHandler(os.path.join(logs, 'core.log'), encoding='utf-8')
        self._log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        log.addHandler(self._log_handler)
        log.setLevel(logging.INFO)

    def _ensure_local_token(self):
        """The CLI's credential: kept while its hash is live, re-minted when it
        is missing, revoked or expired. Returns {token, principal_id, device_id}."""
        token = discovery.read_local_token()
        if token:
            h = auth.token_hash(token)
            with self.db.read() as conn:
                cred = queries.credential(conn, h)
            if auth.live(cred, h):
                return {'token': token, 'principal_id': cred['principal_id'],
                        'device_id': cred['device_id']}
        token = auth.new_token()
        out = self.db.writer.execute(commands.register_device, {
            'actor': self.system, 'name': 'local', 'platform': 'tui',
            'token_hash': auth.token_hash(token), 'scopes': list(auth.LOCAL_SCOPES)})
        discovery.write_local_token(token)
        return {'token': token, 'principal_id': out['principal_id'],
                'device_id': out['device_id']}

    def health(self):
        return {'core': {'pid': os.getpid(), 'started_at': self.started_at,
                         'version': VERSION, 'schema': self.schema,
                         'ports': 'stub' if self.ports.stub else 'real'},
                'engine': self.loop.status(), 'world': self.world.status(),
                'knowledge': self.knowledge.status(), 'intent': self.intent.status()}

    def launch_url(self):
        """A fresh launch code in the URL fragment (never sent to the server)."""
        code = self.api.launch.mint(self.local['principal_id'], self.local['device_id'])
        return '%s/#launch=%s' % (self.api.origin.origin, code)

    # ── stop ──

    def _engine_failed(self):
        self.exit_code = 3
        self._done.set()

    def request_stop(self):
        self._done.set()

    def wait(self):
        """Block until a stop is requested or the engine fails; the exit code."""
        while not self._done.wait(0.5):      # a timeout keeps Ctrl+C deliverable
            pass
        return self.exit_code

    def stop(self, *, drain=True):
        """Reverse order (§5.4). drain=False is the in-process stand-in for a
        kill: queued commands are dropped, not run."""
        if self.api is not None:
            self.api.stopping = True
            self.api.sse.close_all()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.intent is not None:
            self.intent.stop()
        if self.knowledge is not None:
            self.knowledge.stop()
        if self.world is not None:
            self.world.stop()
        if self.loop is not None:
            self.loop.stop()
        if self.db is not None:
            self.db.close(drain=drain)
            self.db = None
        if self.lock is not None:
            discovery.remove_core_json()        # ours, or stale: we hold the lock
            self.lock.release()
            self.lock = None
        if self._log_handler is not None:
            log.removeHandler(self._log_handler)
            self._log_handler.close()
            self._log_handler = None
        self.api = None
        self._done.set()


def run(*, port=DEFAULT_PORT, ports=None, open_browser=False, out=None, err=None):
    """`archeus core` in the foreground. Exit codes: 0 stopped cleanly, 1
    another Core holds the lock (or Core refused to start), 2 the port is in
    use, 3 the engine or the world worker failed."""
    out, err = out or sys.stdout, err or sys.stderr
    core = Core(port=port, ports=ports)
    try:
        core.start()
    except discovery.LockHeld:
        info = discovery.read_core_json() or {}
        print('Core is already running (pid %s, port %s)'
              % (info.get('pid', '?'), info.get('port', '?')), file=err)
        return 1
    except PortInUse:
        print('port %d is in use: another program is listening on 127.0.0.1:%d; stop it, '
              'then run `archeus core` again' % (port, port), file=err)
        return 2
    except RefuseStart as e:
        print('Core will not start: %s' % e, file=err)
        return 1
    print('Archeus Core on http://127.0.0.1:%d (pid %d) — Ctrl+C stops it'
          % (port, os.getpid()), file=out, flush=True)
    if core.warning:
        print('warning: %s' % core.warning, file=err)
    if open_browser:
        import webbrowser
        webbrowser.open(core.launch_url())
    for name in ('SIGTERM', 'SIGBREAK'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: core.request_stop())
    try:
        code = core.wait()
    except KeyboardInterrupt:
        code = 0
    core.stop()
    return code
