"""T-303: the highest-risk branches of archeus/core/execution/manager.py the other
tests never reached — the launch and its denials, the stops, the e-stop, the stop
grace and the pause timeout, the cleanup that must follow every end, the second
stop that must never be fired, a worker that crashed, and the hook that is never
allowed on a failure.

Everything runs on fakes at the seams the module's own tests use (`Node`,
`Adapter`, the `_spawn_rig` of test_execution_units.py): no process, no network,
no installed runtime, no OS call the fake cannot answer, so the same file passes
or fails the same way on Linux and Windows. What is NOT faked is the writer: the
commands go to a real database, so an end that the state machine would refuse
(illegal trigger, stale version) fails here instead of in the field.
"""

import time
from types import SimpleNamespace

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.execution import manager as M
from archeus.core.execution.manager import ExecutionManager
from archeus.harnesses import base
from archeus.infra.db import Database, rows
from v1.unit.test_execution_units import _spawn_rig, _steps

#: the stop reasons that do not wait for a boundary; the manager keeps its own
#: copy (manager.py:54) of four names the domain owns (entities.STOP_REASONS,
#: entities.py:870), and this file is what pins the copies to the same set
_NOW = ('estop', 'limit', 'disarmed', 'breaker')


# ── the fakes ────────────────────────────────────────────────────────────────

class Node:
    """Everything the pass does to the world, recorded and answered by the test."""

    def __init__(self, disarmed=False):
        self.disarmed_flag, self.pending = disarmed, []
        self.kills, self.flags, self.responded = [], [], []
        self.ended_calls, self.released, self.registry, self.world = [], [], [], []
        self.cancelled_handles = set()

    def disarmed(self):
        return self.disarmed_flag

    def kill(self, adapter, handle, reason=None):
        self.kills.append((adapter, handle))

    def set_flag(self, execution_id, flag):
        self.flags.append((execution_id, flag))

    def respond(self, execution_id, seq, decision, reason):
        self.responded.append((execution_id, seq, decision, reason))

    def pending_requests(self, execution_id):
        return self.pending

    def ended(self, handle, exit_code, process_seq):
        self.ended_calls.append((handle, exit_code, process_seq))

    def cancelled(self, handle, process_seq):
        return handle in self.cancelled_handles

    def end_isolation(self, execution_id, reason=None):
        self.released.append((execution_id, reason))

    def _registry(self, line):
        self.registry.append(line)

    def git_branch(self, workdir):
        self.world.append(('git_branch', workdir))
        return 'main'

    def git_remotes(self, workdir):
        self.world.append(('git_remotes', workdir))
        return {}

    def command_context(self, execution_id, workdir, cwd):
        self.world.append(('command_context', cwd))
        return None


class Adapter:
    """One harness: answers the four questions the pass asks about a process."""

    id = 'fake'

    def __init__(self, result=None, state='exited', exit_code=0, events=(),
                 installed=True, caps=('resume',)):
        self.result = result or base.ExecutionResult('ok', exit_code)
        self.state, self.exit_code, self.events = state, exit_code, events
        self.installed, self.caps = installed, caps

    def discover(self):
        return SimpleNamespace(installed=self.installed)

    def capabilities(self, account):
        return SimpleNamespace(capabilities=self.caps)

    def inspect(self, handle, offset=0):
        return base.Snapshot(self.events, offset)

    def status(self, handle):
        return base.ProcStatus(self.state, self.exit_code)

    def collect_result(self, handle):
        return self.result


def _mgr(db=None, who=None, node=None, reply=None):
    """A manager built the way the module's own tests build one: no engine, no
    thread. With *db* its `_do`, `_read` and `_reload` are the real ones, so every
    recorded command runs against the real state machine; without it the writer is
    faked and answers *reply*."""
    m = ExecutionManager.__new__(ExecutionManager)
    m.db, m.actor, m.node = db, who, node or Node()
    m._procs, m._noted, m.writes = {}, set(), []
    m._clock = {'accounts': float('inf'), 'usage': float('inf'), 'isolation': float('inf')}
    m.usage, m.broker, m.scenarios = None, None, {}
    m.policy = m.missions = m.router = None
    m.registry = SimpleNamespace(get=lambda hid: Adapter())
    m.grace_s, m.pause_timeout, m.start_timeout, m.lost_after = 10.0, 120.0, 60.0, 90.0
    answered = dict(reply or {'refused': False, 'decision': 'deny', 'reason': 'policy'})

    def _do(command, **kw):
        m.writes.append((command.__name__, kw))
        return answered if db is None else ExecutionManager._do(m, command, **kw)

    m._do = _do
    if db is None:
        m._read = lambda kind, id_: None
        m._reload = lambda e: e
    return m


def _proc(m, adapter, handle='h', seq=1, offset=0, usage=None, since=None, key=None):
    """What the manager knows about one live process, made by the real `_fresh`.
    The key is the execution: that is how `_step` registers it and what `_collect`
    drops it by."""
    p = ExecutionManager._fresh(adapter, handle, seq, offset, usage)
    p['since'] = since
    m._procs[key or handle] = p
    return p


def _seed(state='RUNNING', mission_state='EXECUTING', stop_reason=None, max_attempts=1,
          isolated=None, process_seq=0, account=False, approval=None, harness_id='fake',
          workdir=None, branch=None):
    """Mission, plan, task, execution (and an account, an approval when asked
    for) on a real database, seeded the way test_execution_units seeds one."""
    db = Database.open()
    who = Ref('system', ids.new_id('principal'))       # the manager's own actor
    mid, pid, tid, eid = (ids.new_id(k) for k in ('mission', 'plan', 'task', 'execution'))
    aid = ids.new_id('account') if account else None

    def run(tx, **_):
        for row in (
                entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                 objective='o', state=mission_state),
                entities.Plan(id=pid, mission_id=mid, state='APPROVED'),
                entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                              kind='code_change', state='RUNNING', max_attempts=max_attempts),
                entities.Execution(id=eid, task_id=tid, mission_id=mid, plan_id=pid,
                                   attempt=1, state=state, stop_reason=stop_reason,
                                   isolated=isolated, process_seq=process_seq,
                                   harness_id=harness_id, account_id=aid,
                                   workdir=workdir, branch=branch)):
            tx.insert(row, actor=who)
        if aid is not None:
            tx.insert(entities.Account(id=aid, harness_id=harness_id, label='a',
                                       auth_kind='api_key', health='AVAILABLE'), actor=who)
        if approval is not None:
            tx.insert(entities.Approval(id=ids.new_id('approval'), subject=Ref('task', tid),
                                        action_hash='0' * 64, kind='action', state=approval,
                                        requested_by=who.id, mission_id=mid, task_id=tid,
                                        execution_id=eid,
                                        expires_at='2099-01-01T00:00:00+00:00'),
                      actor=who)
        tx.append(new_event('mission.updated', Ref('mission', mid), who, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return SimpleNamespace(db=db, who=who, eid=eid, tid=tid, mid=mid, aid=aid,
                           manager=_mgr(db, who))


def _live(rig):
    """The execution and the mission as the pass reads them."""
    return _row(rig, entities.Execution, rig.eid), _row(rig, entities.Mission, rig.mid)


def _row(rig, kind, id_):
    with rig.db.read() as r:
        return rows.get(r, kind, id_).entity


def _state_and_version(rig):
    """(state, version) of the execution row: equal before and after a pass means
    the pass wrote nothing, which is what a refusal must leave behind."""
    with rig.db.read() as r:
        got = rows.get(r, entities.Execution, rig.eid)
    return got.entity.state, got.version


# ── launch: what starts nothing ──────────────────────────────────────────────

def test_the_emergency_stop_refuses_an_execution_that_never_started():
    """manager.py:211-213 — under the e-stop an INTENT execution is refused where
    it stands: no process, and an uncharged end the task may retry once rearmed."""
    rig = _seed('INTENT')
    try:
        m, node = rig.manager, rig.manager.node
        node.disarmed_flag = True
        e, mission = _live(rig)
        assert m._first(e, mission, True) is True
        assert [c for c, _ in m.writes] == ['refuse']
        assert m.writes[0][1]['stop_reason'] == 'disarmed'
        assert _row(rig, entities.Execution, rig.eid).state == 'ABANDONED'
        assert node.kills == [] and m._procs == {}
    finally:
        rig.db.close()


@pytest.mark.parametrize('mission_state,writes', [
    ('CANCELLED', ['refuse']), ('FAILED', ['refuse']), ('COMPLETED', ['refuse']),
    (None, ['refuse']), ('BLOCKED', []), ('PAUSED', []), ('DRAFT', []),
])
def test_a_mission_that_ended_refuses_its_work_and_a_mission_that_did_not_start_waits(
        mission_state, writes):
    """manager.py:215-221 — a mission that is gone or terminal spends the execution
    (`cancel`, uncharged); one that is merely not EXECUTING starts nothing at all,
    which is what keeps a paused mission from launching agents behind the user."""
    rig = _seed('INTENT', mission_state='EXECUTING')
    try:
        m = rig.manager
        e, _ = _live(rig)
        mission = (None if mission_state is None
                   else SimpleNamespace(id=rig.mid, state=mission_state))
        assert m._first(e, mission, False) is bool(writes)
        assert [c for c, _ in m.writes] == writes
        if writes:
            assert m.writes[0][1]['stop_reason'] == 'cancel'
            assert _row(rig, entities.Execution, rig.eid).state == 'ABANDONED'
            want = 'gone' if mission is None else mission_state
            assert want in m.writes[0][1]['reason']
        else:
            assert _row(rig, entities.Execution, rig.eid).state == 'INTENT'
    finally:
        rig.db.close()


def test_provider_terms_that_do_not_permit_the_harness_start_nothing_at_all(monkeypatch,
                                                                            tmp_path):
    """manager.py:231-234 — the terms gate is the first thing `_spawn` does: the
    isolation authority is never asked, no workspace is made, nothing is prepared
    and no process is started."""
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, True)
    monkeypatch.setattr(M.resources, 'terms_permit', lambda r, a: False)
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['refuse']
    assert log[0][1]['stop_reason'] == 'binding'
    assert 'provider terms' in log[0][1]['reason']


def test_an_e_stop_that_races_the_spawn_refuses_it_before_the_process(monkeypatch, tmp_path):
    """manager.py:340-344 — the flag went up after `prepare_process` and before
    `spawn`: the process is never started, and what was already written is refused
    rather than left prepared for something that will not run."""
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path)
    m.node.disarmed = lambda: True
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['requested', 'workspace', 'inventory', 'prepare_process',
                           'refuse']
    assert log[-1][1]['stop_reason'] == 'disarmed'
    assert [x for x in log if x[0] in ('spawn', 'record_process')] == []


def test_an_e_stop_that_arrives_after_the_process_was_recorded_stops_it_at_once(
        monkeypatch, tmp_path):
    """manager.py:373-379 — the flag went up while the process was coming up: the
    process is registered and recorded, and the very same pass stops the execution,
    because a process that began under an e-stop must not be left to run on."""
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path)
    started = []
    real = m.node.spawn

    def spawn(ad, spec, **kw):
        got = real(ad, spec, **kw)
        started.append(True)                      # the world was stopped mid-spawn
        return got
    m.node.spawn = spawn
    m.node.disarmed = lambda: bool(started)       # False at 340, True at 376
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['requested', 'workspace', 'inventory', 'prepare_process',
                           'spawn', 'record_process', 'stop']
    assert log[-1][1]['stop_reason'] == 'disarmed'
    assert list(m._procs) == [e.id]               # watched: the next pass kills it


@pytest.mark.parametrize('error,stop_reason', [
    (base.SpawnWriteFailed('no marker'), 'workspace'),
    (base.SpawnFailed('no launcher'), 'spawn'),
    (base.AlreadySpawned('a marker is there'), 'binding'),
])
def test_a_start_that_failed_spends_only_a_write_failure_and_always_frees_its_identity(
        monkeypatch, tmp_path, error, stop_reason):
    """manager.py:352-372 — three different ends, told apart by the reason they are
    refused for: only what Core could not write (`workspace`) is the task's own
    fault and spends an attempt (P11 note 11); a harness that cannot start is O7's
    (`spawn`) and a marker that is already there is reconciliation's (`binding`).
    None of the three records a process, and none leaves an isolation identity."""
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path)
    released = []
    m.node.end_isolation = lambda eid, reason=None: released.append((eid, reason))

    def spawn(ad, spec, **kw):
        raise error
    m.node.spawn = spawn
    assert m._spawn(e, mission) is True
    assert _steps(log)[-1] == 'refuse'
    assert log[-1][1]['stop_reason'] == stop_reason
    assert log[-1][1]['reason'].startswith('the process did not start')
    assert 'record_process' not in _steps(log)          # nothing claimed a process
    assert released == [(e.id, 'ended')]                # and nothing kept an identity


def test_a_second_pass_never_starts_a_second_process_for_a_live_execution():
    """manager.py:188-206 — a RUNNING row whose process this Core does not hold
    goes to reconciliation, never to `_first`/`_spawn`: two processes for one
    execution would both answer to the same hook mailbox."""
    m = _mgr()
    seen = []
    m._reconcile_one = lambda e, d: seen.append(('reconcile', e.state)) or True
    m._watch = lambda e, mi, d: seen.append(('watch', e.state)) or True
    m._first = lambda e, mi, d: seen.append(('first', e.state)) or True
    m._spawn = lambda e, mi, resume_state=None: seen.append(('spawn', e.state)) or True
    for state in ('STARTING', 'RUNNING', 'PAUSING', 'STOPPING', 'HANDING_OFF'):
        m._step(SimpleNamespace(id='exe_1', state=state, mission_id='m', process_seq=1),
                None, False)
    assert [x[0] for x in seen] == ['reconcile'] * 5
    seen[:] = []
    m._procs['exe_1'] = {'adapter': Adapter(), 'handle': 'h'}
    assert m._step(SimpleNamespace(id='exe_1', state='RUNNING', mission_id='m',
                                  process_seq=1), None, False) is True
    assert [x[0] for x in seen] == ['watch']
    seen[:] = []
    # an INTENT that was prepared and never recorded is reconciled, not re-spawned
    m._step(SimpleNamespace(id='exe_2', state='INTENT', mission_id='m', process_seq=1),
            None, False)
    assert [x[0] for x in seen] == ['reconcile']


# ── the stops, the e-stop and the clocks ─────────────────────────────────────

def test_the_emergency_stop_stops_a_live_process_and_kills_it_at_once():
    """manager.py:636-638 with 667-669 — the e-stop is not a request: the row goes
    to STOPPING with `estop` and the process is killed in the same pass, without
    waiting for the stop grace."""
    rig = _seed('RUNNING', process_seq=1)
    try:
        m, node = rig.manager, rig.manager.node
        node.disarmed_flag = True
        adapter = Adapter()
        p = _proc(m, adapter, handle='h', seq=1)
        e, mission = _live(rig)
        assert m._control(e, mission, p, True) is True
        assert [c for c, _ in m.writes] == ['stop']
        assert m.writes[0][1]['stop_reason'] == 'estop'
        assert node.kills == [(adapter, 'h')]
        assert node.flags == [(rig.eid, 'STOP')]
        got = _row(rig, entities.Execution, rig.eid)
        assert (got.state, got.stop_reason) == ('STOPPING', 'estop')
    finally:
        rig.db.close()


@pytest.mark.parametrize('disarmed,killed', [(True, True), (False, False)])
def test_a_stop_that_is_already_under_way_is_never_fired_again(disarmed, killed):
    """manager.py:634-641 — the guard that keeps a second `stop` off a STOPPING
    execution, e-stop or no e-stop: the state machine has no STOPPING -> STOPPING
    edge, so a second one would raise inside the pass and no other execution would
    be served. The process is still killed at once under the e-stop, because that
    does not go through the row."""
    rig = _seed('STOPPING', mission_state='CANCELLED', stop_reason='user', process_seq=1)
    try:
        m, node = rig.manager, rig.manager.node
        node.disarmed_flag = disarmed
        adapter = Adapter()
        p = _proc(m, adapter, handle='h', seq=1)
        e, mission = _live(rig)
        before = _state_and_version(rig)
        assert m._control(e, mission, p, disarmed) is True
        assert m.writes == []                            # no stop, no second anything
        assert node.kills == ([(adapter, 'h')] if killed else [])
        assert node.flags == [(rig.eid, 'STOP')]
        assert _state_and_version(rig) == before         # the row was not touched
    finally:
        rig.db.close()


@pytest.mark.parametrize('mission_state,want', [('CANCELLED', 'STOPPING'),
                                                ('FAILED', 'STOPPING'),
                                                ('COMPLETED', 'STOPPING'),
                                                ('PAUSED', 'PAUSING')])
def test_a_mission_that_ended_stops_the_process_and_a_paused_one_halts_it_at_a_boundary(
        mission_state, want):
    """manager.py:639-655 — the mission decides which flag the process is asked
    to respect: STOP for a mission that is gone, PAUSE for one that is paused.
    A PAUSE is never a kill: nothing is killed before the pause timeout."""
    rig = _seed('RUNNING', process_seq=1)
    try:
        m, node = rig.manager, rig.manager.node
        p = _proc(m, Adapter(), handle='h', seq=1)
        e, _ = _live(rig)
        assert m._control(e, SimpleNamespace(id=rig.mid, state=mission_state), p, False)
        assert [c for c, _ in m.writes] == ['stop' if want == 'STOPPING' else 'pause_work']
        assert node.flags == [(rig.eid, 'STOP' if want == 'STOPPING' else 'PAUSE')]
        assert node.kills == []
        got = _row(rig, entities.Execution, rig.eid)
        assert got.state == want
        assert got.stop_reason == ('cancel' if want == 'STOPPING' else None)
    finally:
        rig.db.close()


@pytest.mark.parametrize('stop_reason,waited,killed', [
    ('user', 0.0, False), ('user', 9.0, False), ('cancel', 9.0, False),
    ('user', 10.0, True), ('estop', 0.0, True), ('limit', 0.0, True),
    ('disarmed', 0.0, True), ('breaker', 0.0, True),
])
def test_the_stop_grace_holds_and_the_reasons_that_do_not_wait_kill(
        stop_reason, waited, killed):
    """manager.py:656-669 — the grace is what a process gets to finish its tool
    call, and `_NOW` is what forfeits it: one second either side of the boundary
    changes the kill and nothing else does."""
    assert set(_NOW) == set(M._NOW)
    # a reason the domain does not know would be a reason nothing can report
    assert set(M._NOW) <= set(entities.STOP_REASONS)
    rig = _seed('STOPPING', stop_reason=stop_reason, process_seq=1)
    try:
        m, node = rig.manager, rig.manager.node
        adapter = Adapter()
        p = _proc(m, adapter, handle='h', seq=1, since=time.monotonic() - waited)
        e, mission = _live(rig)
        assert m._control(e, mission, p, False) is True
        assert node.kills == ([(adapter, 'h')] if killed else [])
        assert node.flags == [(rig.eid, 'STOP')]
        assert m.writes == []
    finally:
        rig.db.close()


def test_a_pause_that_meets_no_boundary_times_out_exactly_once_and_becomes_a_stop():
    """manager.py:663-666 — the pause timeout is a one-way door: `pause_timed_out`
    may be recorded once, because the second one is an illegal transition; the
    execution it leaves is a STOPPING one Core then kills by the stop grace."""
    rig = _seed('PAUSING', process_seq=1)
    try:
        m, node = rig.manager, rig.manager.node
        adapter = Adapter()
        p = _proc(m, adapter, handle='h', seq=1,
                  since=time.monotonic() - m.pause_timeout)
        e, mission = _live(rig)
        assert m._control(e, mission, p, False) is True
        assert [c for c, _ in m.writes] == ['pause_timed_out']
        assert node.kills == [] and node.flags == [(rig.eid, 'PAUSE')]
        assert p['flagged'] is False and p['since'] is not None
        assert _row(rig, entities.Execution, rig.eid).state == 'STOPPING'
        # the next pass, with the row as the writer left it: no second timeout
        m.writes[:] = []
        node.flags[:] = []
        e, mission = _live(rig)
        assert m._control(e, mission, p, False) is True
        assert [c for c, _ in m.writes] == []
        assert node.kills == []                      # `pause_timeout` waits its grace
        assert node.flags == [(rig.eid, 'STOP')]
    finally:
        rig.db.close()


def test_a_pause_still_inside_its_timeout_is_never_timed_out():
    """manager.py:663-666 — the other side of the pause timeout: a PAUSING process
    one second short of it is left alone, still asking its process to pause at a
    boundary, with nothing spent. A timeout that fired early would stop work that
    was about to reach a tool boundary and lose its half-written turn."""
    rig = _seed('PAUSING', process_seq=1)
    try:
        m, node = rig.manager, rig.manager.node
        p = _proc(m, Adapter(), handle='h', seq=1,
                  since=time.monotonic() - (m.pause_timeout - 1.0))
        e, mission = _live(rig)
        assert m._control(e, mission, p, False) is True
        assert m.writes == []                       # no timeout spent
        assert node.kills == [] and node.flags == [(rig.eid, 'PAUSE')]
        assert p['flagged'] is True                 # it was asked once, already
        assert _row(rig, entities.Execution, rig.eid).state == 'PAUSING'
    finally:
        rig.db.close()


def test_an_orphan_is_killed_by_its_grace_and_collected_when_it_exits():
    """manager.py:170-186 — the execution has already ended, so no other pass
    will ever reach its process: while it runs it is killed at the stop grace (at
    once under the e-stop) and when it has exited its end is collected and its
    identity released, which is the only place that ever does it."""
    rig = _seed('RUNNING', process_seq=1)
    try:
        m, node = rig.manager, rig.manager.node
        adapter = Adapter(state='running')
        p = _proc(m, adapter, handle='h', seq=1, key=rig.eid)
        # end it the way the mission layer would, leaving the process in `_procs`
        rig.db.writer.execute(X.stop, {'actor': rig.who, 'execution_id': rig.eid,
                                       'reason': 'the user stopped it',
                                       'stop_reason': 'user'})
        rig.db.writer.execute(X.record_end, {'actor': rig.who, 'execution_id': rig.eid,
                                             'exit_code': None, 'killed': True})
        assert _row(rig, entities.Execution, rig.eid).state == 'ENDED_KILLED'
        assert m._orphans(set(), False) == 0 and node.kills == []
        p['since'] = time.monotonic() - m.grace_s
        assert m._orphans(set(), False) == 1
        assert node.kills == [(adapter, 'h')]
        # and under the e-stop it does not wait for that grace at all
        p['since'] = time.monotonic()
        node.kills[:] = []
        assert m._orphans(set(), True) == 1
        assert node.kills == [(adapter, 'h')]
        # an orphan that has exited is collected: its keys go, and its identity
        adapter.state = 'exited'
        assert m._orphans(set(), False) == 1
        assert m._procs == {} and node.released == [(rig.eid, 'ended')]
    finally:
        rig.db.close()


# ── the hook: nothing is ever allowed on a failure ───────────────────────────

def _hook_rig(tmp_path, pending, reply=None, branch=None, isolated=None, process_seq=1):
    """An execution with hook requests waiting, and the `serve_hook` writer made of
    the test's own answer: what the manager does with a decision — and with a
    failure — is the manager's own behaviour (the answers themselves are P21's)."""
    rig = _seed('RUNNING', process_seq=process_seq, isolated=isolated, branch=branch,
                workdir=str(tmp_path / 'work'))
    m, node = rig.manager, rig.manager.node
    node.pending = pending
    m._procs[rig.eid] = ExecutionManager._fresh(Adapter(), 'h', process_seq, 0, None)
    answered = dict(reply or {'decision': 'deny', 'reason': 'not allowed'})

    def _do(command, **kw):
        m.writes.append((command.__name__, kw))
        return dict(answered)
    m._do = _do
    return rig, m, node


def test_a_request_core_cannot_judge_halts_and_is_never_allowed(tmp_path):
    """manager.py:628-630 — the whole of the hook's fail-closed rule: whatever
    raises while a request is being judged (the canonicaliser, the policy, the
    writer) answers `halt`, never `allow` and never a silent retry."""
    rig, m, node = _hook_rig(tmp_path, [(1, {'tool': 'Read',
                                             'input': {'file_path': 'a.py'},
                                             'cwd': str(tmp_path / 'work')})])

    def boom(command, **kw):
        m.writes.append((command.__name__, kw))
        raise RuntimeError('the policy engine blew up')
    m._do = boom
    try:
        assert m._hooks(_live(rig)[0], m._procs[rig.eid], False) is True
        assert node.responded == [(rig.eid, 1, 'halt',
                                   'Archeus could not judge the request')]
        assert [c for c, _ in m.writes] == ['serve_hook']   # it tried, and failed closed
    finally:
        rig.db.close()


def test_a_request_core_cannot_read_halts_without_asking_the_policy_at_all(tmp_path):
    """manager.py:607-609 — a mailbox line that does not parse is an unjudged
    request: it halts where it is read and the writer is never entered for it."""
    rig, m, node = _hook_rig(tmp_path, [(7, None),
                                        (8, {'tool': 'Read',
                                              'input': {'file_path': 'a.py'},
                                              'cwd': str(tmp_path / 'work')})])
    try:
        assert m._hooks(_live(rig)[0], m._procs[rig.eid], False) is True
        assert node.responded[0] == (rig.eid, 7, 'halt', 'the request could not be read')
        assert [c for c, _ in m.writes] == ['serve_hook']      # only the readable one
        assert node.responded[1][:2] == (rig.eid, 8)
    finally:
        rig.db.close()


def test_a_cwd_outside_the_workspace_and_an_isolated_branch_are_never_believed(
        tmp_path):
    """manager.py:610-616 with 623-627 — `cwd_ok` is what turns a Bash command's
    directory context off, and an isolated execution's branch is never probed or
    believed: Git would run in a directory the execution controls."""
    rig, m, node = _hook_rig(tmp_path, [(1, {'tool': 'Bash',
                                             'input': {'command': 'git status'},
                                             'cwd': str(tmp_path)})],
                             branch='archeus/m.t', isolated=True)
    try:
        e, _ = _live(rig)
        node.isolation_record = lambda eid: object()               # Core's own record
        assert m._hooks(e, m._procs[rig.eid], False) is True
        (name, kw), = m.writes
        assert name == 'serve_hook'
        assert kw['cwd_ok'] is False and kw['branch_ok'] is False
        assert kw['disarmed'] is False
        assert node.world == []                                    # no git probe at all
        assert [d for (_e, _s, d, _r) in node.responded] == ['deny']
    finally:
        rig.db.close()


def test_the_answer_comes_from_the_writer_and_the_e_stop_reaches_the_policy(tmp_path):
    """manager.py:623-631 — the decision the writer returns is the answer given,
    and `disarmed` is passed to it: a halt that ignored the e-stop would let a
    tool call through while the world was being stopped."""
    rig, m, node = _hook_rig(tmp_path, [(3, {'tool': 'Read',
                                             'input': {'file_path': 'a.py'},
                                             'cwd': str(tmp_path / 'work')})],
                             reply={'decision': 'halt', 'reason': 'the emergency stop'})
    try:
        assert m._hooks(_live(rig)[0], m._procs[rig.eid], True) is True
        (_name, kw), = m.writes
        assert kw['disarmed'] is True and kw['cwd_ok'] is True
        assert node.responded == [(rig.eid, 3, 'halt', 'the emergency stop')]
    finally:
        rig.db.close()


# ── ends and cleanup ─────────────────────────────────────────────────────────

def test_a_worker_that_crashed_ends_its_execution_and_leaves_nothing_behind():
    """manager.py:676-686 with 731-739 — a non-zero exit of a RUNNING execution is
    its end, once: the process is dropped from what this Core watches, the node is
    told it ended, the isolation identity is released, and a second collection of
    the same process records nothing."""
    rig = _seed('RUNNING', process_seq=1, max_attempts=1)
    try:
        m, node = rig.manager, rig.manager.node
        adapter = Adapter(result=base.ExecutionResult('error', 1, failure='task'))
        p = _proc(m, adapter, handle='h', seq=1, key=rig.eid)
        e, _ = _live(rig)
        m._collect(e, p, base.ProcStatus('exited', 1))
        assert [c for c, _ in m.writes] == ['record_end']
        assert m._procs == {}
        assert node.ended_calls == [('h', 1, 1)]
        assert node.released == [(rig.eid, 'ended')]
        got = _row(rig, entities.Execution, rig.eid)
        assert (got.state, got.exit_code, got.charged) == ('ENDED_ERROR', 1, True)
        assert _row(rig, entities.Task, rig.tid).state == 'FAILED'
        # the same process collected again (an orphan pass reaching it late) records
        # nothing a second time; `node.ended` is told again and that is safe, because
        # the end line is keyed by handle and sequence (T-105 review 2b)
        m.writes[:] = []
        m._collect(_live(rig)[0], p, base.ProcStatus('exited', 1))
        assert m.writes == []
        assert node.ended_calls == [('h', 1, 1)] * 2
    finally:
        rig.db.close()


@pytest.mark.parametrize('cancelled', [False, True])
def test_a_stop_of_cores_that_ended_an_isolated_launch_is_a_kill_whatever_the_adapter_says(
        cancelled):
    """manager.py `_collect`: an isolated launch ends through the node, and the adapter
    never sees that stop, so the node's word that Core cancelled it is what makes the end
    a kill (and so never a clean hand-off)."""
    rig = _seed('RUNNING', process_seq=1, max_attempts=1)
    try:
        m, node = rig.manager, rig.manager.node
        if cancelled:
            node.cancelled_handles.add('h')
        p = _proc(m, Adapter(result=base.ExecutionResult('ok', 0)), handle='h', seq=1,
                  key=rig.eid)
        m._collect(_live(rig)[0], p, base.ProcStatus('exited', 0))
        (_name, kw), = [w for w in m.writes if w[0] == 'record_end']
        assert kw['killed'] is cancelled
    finally:
        rig.db.close()


def test_a_limit_seen_only_at_the_exit_limits_the_account_and_hands_the_work_off():
    """manager.py:694-699 — the provider refused at the very end: the account is
    LIMITED and the work continues elsewhere by hand-off, instead of the
    execution ending as if the task had failed."""
    rig = _seed('RUNNING', process_seq=1, account=True)
    try:
        m, node = rig.manager, rig.manager.node
        adapter = Adapter(result=base.ExecutionResult('ok', 0, failure='limit'))
        p = _proc(m, adapter, handle='h', seq=1, key=rig.eid)
        e, _ = _live(rig)
        m._collect(e, p, base.ProcStatus('exited', 0))
        assert [c for c, _ in m.writes] == ['account_limited', 'request_handoff',
                                            'record_end']
        assert m.writes[1][1]['stop_reason'] == 'limit'
        assert _row(rig, entities.Account, rig.aid).health == 'LIMITED'
        assert node.released == [(rig.eid, 'ended')]
    finally:
        rig.db.close()


@pytest.mark.parametrize('disarmed,mission_state,reason_want,stop_want', [
    (True, 'EXECUTING', 'emergency stop', 'disarmed'),
    (False, 'CANCELLED', 'the mission ended', 'cancel')])
def test_work_halted_for_a_pause_or_an_approval_ends_when_its_mission_is_gone(
        disarmed, mission_state, reason_want, stop_want):
    """manager.py:779-783 and 789-793 — a halted or waiting execution whose
    mission went, or whose Core is under the e-stop, is discarded rather than
    left for a resume that can never come: the row ends, the harness is never
    even routed to, and nothing is ever spawned for it."""
    for state in ('PAUSED', 'AWAITING_APPROVAL'):
        rig = _seed(state, mission_state=mission_state, process_seq=1)
        try:
            m, node = rig.manager, rig.manager.node

            def no_registry(hid):
                raise AssertionError('halted work is never routed to a harness')
            m.registry = SimpleNamespace(get=no_registry)          # nothing spawns
            e, mission = _live(rig)
            got = (m._paused(e, mission, disarmed) if state == 'PAUSED'
                   else m._awaiting(e, mission, disarmed))
            assert got is True
            (name, kw), = m.writes
            assert name == 'refuse' and kw['stop_reason'] == stop_want
            assert reason_want in kw['reason']
            assert _row(rig, entities.Execution, rig.eid).state == 'ENDED_KILLED'
            assert node.kills == []
        finally:
            rig.db.close()


def test_a_halted_execution_is_never_resumed_without_its_answer_or_its_capability():
    """manager.py:779-817 — the denials around a resume: a PAUSED row whose mission
    is not EXECUTING waits, an AWAITING_APPROVAL row whose approval is still PENDING
    is never resumed (that is the whole point of asking), a harness without the
    `resume` capability ends the execution rather than restarting it from scratch,
    and a halted execution ended by the e-stop is never charged to the task."""
    rig = _seed('PAUSED', mission_state='PAUSED', process_seq=1)
    try:
        m = rig.manager
        e, mission = _live(rig)
        assert m._paused(e, mission, False) is False and m.writes == []
    finally:
        rig.db.close()

    rig = _seed('AWAITING_APPROVAL', process_seq=1, approval='PENDING')
    try:
        m = rig.manager
        e, mission = _live(rig)
        assert m._awaiting(e, mission, False) is False and m.writes == []
        assert _row(rig, entities.Execution, rig.eid).state == 'AWAITING_APPROVAL'
    finally:
        rig.db.close()

    rig = _seed('PAUSED', process_seq=1)
    try:
        m = rig.manager
        m.registry = SimpleNamespace(get=lambda hid: Adapter(caps=()))
        e, mission = _live(rig)
        assert m._resume(e, mission) is True
        assert [c for c, _ in m.writes] == ['refuse']          # it never asked Core
        assert 'cannot resume' in m.writes[0][1]['reason']
        assert m.writes[0][1]['stop_reason'] == 'binding'
        assert _row(rig, entities.Execution, rig.eid).state == 'ENDED_KILLED'
    finally:
        rig.db.close()

    rig = _seed('PAUSED', process_seq=1)
    try:
        # the same end under the e-stop spends nothing on the task: a halted
        # process ran no work after it was halted, so the task may be tried again
        # once the world is rearmed (P11 note 11).
        m = rig.manager
        e, mission = _live(rig)
        assert m._paused(e, mission, True) is True
        got = _row(rig, entities.Execution, rig.eid)
        assert (got.state, got.charged) == ('ENDED_KILLED', False)
    finally:
        rig.db.close()


def test_a_rejected_approval_ends_the_execution_that_was_waiting_on_it():
    """manager.py:795-802 — the answer that says no is an end, charged: a waiting
    execution whose approval was rejected never runs, and an approval that is
    gone is never treated as an answer that says yes."""
    rig = _seed('AWAITING_APPROVAL', process_seq=1, approval='REJECTED')
    try:
        m = rig.manager
        e, mission = _live(rig)
        assert m._awaiting(e, mission, False) is True
        assert [c for c, _ in m.writes] == ['approval_answered']
        got = _row(rig, entities.Execution, rig.eid)
        assert (got.state, got.exit_reason, got.charged) == ('ENDED_REJECTED', 'rejected',
                                                             True)
    finally:
        rig.db.close()

    rig = _seed('AWAITING_APPROVAL', process_seq=1)          # no approval row at all
    try:
        m = rig.manager
        e, mission = _live(rig)
        assert m._awaiting(e, mission, False) is True
        assert [c for c, _ in m.writes] == ['approval_answered']
        # fail closed: with nothing to read it is never resumed, and never run
        assert _row(rig, entities.Execution, rig.eid).state == 'AWAITING_APPROVAL'
    finally:
        rig.db.close()
