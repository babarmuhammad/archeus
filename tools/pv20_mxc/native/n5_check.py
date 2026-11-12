"""Owner-gated N5 fixture probes. Never an activation or production qualification."""

import importlib
import hashlib
import json
import os
import sys
import time

from tools.pv20_mxc.native import common, n2_check as n2
from tools.pv20_mxc import controller, fixtures
from tools.pv20_mxc.protocol import STAGES

STAGE = 'N5'
CASES = STAGES[STAGE].cases
AUTHORIZATION = '--owner-authorized-n5-2026-11-09'
JOURNAL = 'n5_journal.jsonl'
BUDGET_S = 1700
MODULES = ('mxc_watchdog_host', 'mxc_heartbeat', 'mxc_watchdog', 'mxc_outcome')
LIMITATIONS = dict(zip(CASES, (
    'No activated fixture Core or independent effective identity reader; direct MxcLaunch only.',
    'No activated manager rearm path; cancellation cannot prove dispatch stays disarmed.',
    'Host logic runs in this process; Job termination substitutes for native registry kill.',
    'Closing the held Job substitutes for real fixture Core death; no independent host process.',
    'Fresh Ledger only; no boot admission path or MXC registration absence reader.',
    'Native MXC six-invariant boundary/readers unavailable; legacy SID/ACL facts are not MXC facts.',
    'A4 helper refusal only; no activated router or observable detached fallback path.',
    'Sentinel callback present/absent/denied, not native hook halt or denied filesystem access.',
    'Synthetic channel/outcome attacks, not hostile container access to Core-private lifecycle.',
    'Held Job emptiness/close only; cross-process duplicate-handle exclusion not readable.',
)))


def require(rec, case, holds, detail):
    if not holds:
        rec.record(case, 'FAIL', detail)


class Evidence(common.Recorder):
    def __init__(self, path):
        super().__init__(STAGE)
        self.path = path

    def record(self, case, status, detail=''):
        if case not in CASES or status not in ('PASS', 'FAIL', 'INCONCLUSIVE'):
            raise ValueError('invalid N5 evidence row')
        with open(self.path, 'a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps({'case': case, 'status': status,
                                     'detail': common.redact(detail)}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        super().record(case, status, detail)


def identity(pid):
    code = n2._exit_code(pid)
    if code is None:
        raise OSError('process state unreadable')
    if code != n2.STILL_ACTIVE:
        return None
    created = common._process_creation_time(pid)
    if type(created) is not int or created <= 0:
        raise OSError('process creation time unreadable')
    return created


def authorized_manifest(parent):
    common._validate_parent(parent)
    manifest = controller.read_json(os.path.join(parent, 'n5-manifest.json'))
    if (not isinstance(manifest, dict)
            or manifest.get('stage') != STAGE or manifest.get('fixture_parent') != parent
            or manifest.get('cases') != list(CASES)
            or not isinstance(manifest.get('prerequisites'), dict)
            or manifest['prerequisites'].get('N4') != 'PASS'):
        raise fixtures.Refused('N5 manifest scope or prerequisites mismatch')
    with open(__file__, 'rb') as stream:
        script_hash = hashlib.sha256(stream.read()).hexdigest()
    if manifest.get('n5_script_hash') != script_hash:
        raise fixtures.Refused('N5 script changed since review')
    controller.authorize(manifest, os.path.join(parent, 'n5-authorization.json'), native=True)
    controller.verify_manifest(manifest)
    return manifest


class Harness(n2.Harness):
    def prepare(self):
        super().prepare()
        self.lifecycle = {name: importlib.import_module('archeus.node.' + name)
                          for name in MODULES}

    def eid(self, tag):
        self.seq += 1
        return 'n5_%02d_%s' % (self.seq, tag.replace('-', '_'))

    def start_tree(self, tag):
        return n2._start_loop(self, tag, (self.lay['rev'],), (self.lay['runtime'],))

    def observe(self, pid):
        return identity(pid)

    def host(self, tag, eid, launch, job, sentinel='present'):
        hb = self.lifecycle['mxc_heartbeat']
        host = self.lifecycle['mxc_watchdog_host']
        directory = os.path.join(self.lay['root'], 'heartbeat_' + tag)
        channel = hb.Channel(directory)
        events = []
        path = os.path.join(directory, 'STOP')
        if sentinel == 'present':
            with open(path, 'x', encoding='utf-8') as stream:
                stream.write('STOP')

        def engage():
            events.append('sentinel')
            if sentinel == 'denied':
                raise PermissionError('injected sentinel denial')
            if not os.path.exists(path):
                with open(path, 'x', encoding='utf-8') as stream:
                    stream.write('STOP')
            return n2.read_text(path) == 'STOP'

        def terminate(pid, created):
            events.append('terminate')
            if (pid, created) != (launch.process.pid, launch.process.create_time):
                raise ValueError('not this fixture launch')
            if self.observe(pid) != created:
                return False
            self.boundary.terminate_job(job.handle)
            return self.wait_job(job, lambda count: count == 0, 5) == 0

        core_pid = os.getpid()
        core_time = self.observe(core_pid)
        instance = host.WatchdogHost(
            channel=hb.Channel(directory), clock=time.monotonic, deadline_s=0.2,
            core=(core_pid, core_time), identity_reader=self.observe,
            terminate=terminate, engage_sentinel=engage, journals=self.ledger.journals)
        channel.append({'kind': 'register', 'execution_id': self.name(eid),
                        'pid': launch.process.pid, 'create_time': launch.process.create_time})
        return instance, channel, events


def step_candidate(h, rec):
    case = CASES[0]
    seen = []
    for tag in ('p', 'q'):
        eid, launch, job, _ = h.start_tree(tag)
        ops, invalid = h.ops(eid)
        require(rec, case, not invalid and ops == ['intent', 'ownership'],
                'ownership must be durable before resume')
        require(rec, case, h.observe(launch.process.pid) == launch.process.create_time,
                'launcher identity mismatch')
        seen.append((launch.process.pid, launch.process.create_time, job.handle))
        launch.cancel(reason='n5_identity')
        require(rec, case, h.wait_job(job, lambda n: n == 0, 5) == 0,
                'candidate Job not empty after cancel')
    require(rec, case, seen[0] != seen[1] and seen[0][2] != seen[1][2],
            'peer launches shared identity or Job')


def step_estop(h, rec):
    eid, launch, job, _ = h.start_tree('estop')
    launch.cancel(reason='estop')
    ops, invalid = h.ops(eid)
    require(rec, CASES[1], not invalid and 'quarantine' in ops and 'completion' not in ops
            and h.wait_job(job, lambda n: n == 0, 5) == 0,
            'e-stop cancellation must end Job without successful completion')


def step_hung(h, rec, sentinel='present', tag='hung', case=None):
    case = case or CASES[2]
    eid, launch, job, _ = h.start_tree(tag)
    host, channel, events = h.host(tag, eid, launch, job, sentinel)
    wd = h.lifecycle['mxc_watchdog']
    require(rec, case, host.tick() == wd.ARMED, 'host failed to arm owned launch')
    time.sleep(0.25)
    require(rec, case, host.tick() == wd.FIRED, 'host failed to end silent-Core launch')
    report = channel.read_status()
    require(rec, case, events == ['sentinel', 'terminate'] and report is not None
            and report['sentinel'] == ('unverified' if sentinel == 'denied' else 'engaged')
            and h.wait_job(job, lambda n: n == 0, 5) == 0,
            'sentinel ordering, read-back or Job emptiness failed')


def step_close(h, rec, case):
    _, launch, job, _ = h.start_tree('close')
    pid, created = launch.process.pid, launch.process.create_time
    job.close()
    require(rec, case, h.wait_dead(pid, created, 5), 'launcher survived sole held Job close')
    require(rec, case, h.observe(pid) is None, 'launcher absence unreadable or unconfirmed')


def step_restart(h, rec):
    ledger = h.m.mxc_ledger
    eid, launch, job, _ = h.start_tree('restart')
    name = h.name(eid)
    fresh = ledger.Ledger(h.lay['ledger'])
    state = fresh.reconcile(h.observe, lambda key, owner: None)
    require(rec, CASES[4], state.get(name) == ledger.STILL_RUNNING,
            'fresh ledger did not preserve live owner')
    job.close()
    require(rec, CASES[4], h.wait_dead(launch.process.pid, launch.process.create_time, 5),
            'restart fixture launcher survived close')
    state = fresh.reconcile(h.observe, lambda key, owner: None)
    require(rec, CASES[4], state.get(name) == ledger.DEAD_UNVERIFIED,
            'missing resource absence must quarantine, never certify clean disposal')


def step_routes(h, rec):
    iso = h.m.isolation
    for route in ('fake', 'test', ''):
        eligible, unmet = iso.a4_eligibility(
            harness_id=route, isolated_launch=True, job_held=True,
            sandbox=True, exception_claimed=False, evidence='fixture')
        require(rec, CASES[6], not eligible and 'production_dispatch' in unmet,
                'unsupported/test route eligible')


def step_invariants(h, rec):
    for condition in h.m.isolation.CONDITIONS:
        rec.record(CASES[5], 'INCONCLUSIVE',
                   condition + ': native MXC invariant fault injection/read-back unavailable')


def step_forgery(h, rec):
    case = CASES[8]
    eid, launch, job, _ = h.start_tree('forgery')
    host, channel, events = h.host('forgery', eid, launch, job)
    wd = h.lifecycle['mxc_watchdog']
    channel.append({'kind': 'register', 'execution_id': 'n5_forged-p1',
                    'pid': launch.process.pid, 'create_time': launch.process.create_time})
    require(rec, case, host.tick() == wd.ARMED
            and 'n5_forged-p1' in host.report()['rejected'], 'forged ownership accepted')
    now = time.monotonic()
    beat = {'kind': 'beat', 'seq': 1, 'sent_at': now}
    channel.append(beat)
    require(rec, case, host.tick() == wd.ARMED, 'valid heartbeat control failed')
    channel.append(beat)
    # UNCERTAIN is the rejection: the host then engages the sentinel and asks Core to stop
    # (events: 'sentinel', 'terminate', as in step_hung). Core is this process, which the
    # fixture terminate refuses, so the registered workload is the thing that must survive.
    require(rec, case, host.tick() == wd.UNCERTAIN
            and h.observe(launch.process.pid) == launch.process.create_time,
            'replayed heartbeat accepted or killed the registered workload')
    outcome = h.lifecycle['mxc_outcome']
    expected = {'execution_id': eid, 'nonce': 'fresh', 'digest': 'a' * 64,
                'now': 100, 'max_age': 10}
    record = {'execution_id': eid, 'nonce': 'fresh', 'payload_digest': 'a' * 64,
              'timestamp': 100, 'status': 'succeeded', 'workload_exit': 0}
    require(rec, case, outcome.bind_outcome(0, lambda: record, expected).succeeded,
            'valid bound outcome control failed')
    for field, value in (('nonce', 'old'), ('execution_id', 'peer'), ('timestamp', 1)):
        forged = dict(record, **{field: value})
        require(rec, case, outcome.bind_outcome(0, lambda forged=forged: forged, expected).state
                == outcome.OUTCOME_FORGED, 'forged/replayed outcome accepted')
    launch.cancel(reason='n5_forgery')


def run(h, rec):
    h.prepare()
    steps = (step_candidate, step_estop, step_hung,
             lambda h, rec: step_close(h, rec, CASES[3]), step_restart,
             step_invariants, step_routes,
             lambda h, rec: [step_hung(h, rec, mode, 'sent_' + mode, CASES[7])
                             for mode in ('present', 'absent', 'denied')],
             step_forgery, lambda h, rec: step_close(h, rec, CASES[9]))
    for case, step in zip(CASES, steps):
        h.budget.check()
        step(h, rec)
        rec.record(case, 'INCONCLUSIVE', LIMITATIONS[case])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[1] != AUTHORIZATION or not n2.parent_ok(argv[0]):
        print('REFUSED: N5 needs separate owner authorization; see N5-review-sheet.md')
        return 3
    parent = argv[0]
    systemroot = os.environ.get('SystemRoot', '')
    if not n2._on_windows() or not n2._system_ok(systemroot) or not os.path.isdir(parent):
        return 3
    root, h, code = None, None, 3
    try:
        manifest = authorized_manifest(parent)
        root = str(fixtures.create_root(parent, manifest['fixture_uuid']))
        rec = Evidence(os.path.join(root, JOURNAL))
        h = Harness(root, os.path.join(parent, *n2.SDK_TAIL), systemroot, n2.Budget(BUDGET_S))
        run(h, rec)
        code = rec.exit_code()
    except common.StopRun:
        code = 1
    except (Exception, KeyboardInterrupt) as err:
        print(common.redact('N5 stopped: ' + type(err).__name__))
    finally:
        if h is not None:
            try:
                if h.wind_down():
                    code = 3
            except Exception as err:
                print('N5 cleanup unverified: ' + type(err).__name__)
                code = 3
        if root is not None:
            print(common.redact('N5 fixture preserved: ' + root))
    return code


if __name__ == '__main__':
    sys.exit(main())
