"""T-402: hand-mutant pins on `archeus/core/execution/manager.py`.

Each test pins one condition of the pass that no existing test would notice if it
were inverted, removed or loosened (p11-design-gate §24.3, testing-strategy §1.1).
Every OS question is answered by the fake node or by a monkeypatched seam
(`M.rows`, `M.canonical`), so no real process, network, sleep or OS error text is
involved; paths come from `tmp_path`, so nothing depends on a separator, a drive
letter, a name's case or a localized message.
"""

import time
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities, ids
from archeus.core.execution import checkpoint as CP
from archeus.core.execution import manager as M
from archeus.core.execution import pressure as PR
from archeus.harnesses import base

PRJ, MSN = ids.new_id('project'), ids.new_id('mission')

# ── the fakes ────────────────────────────────────────────────────────────────


class FakeNode:
    """The node seam: `answers[name]` is a value or a callable, every call is
    logged, so a test can say both what was answered and what was never asked."""

    def __init__(self, **answers):
        self.answers = answers
        self.log = []
        self.kills = []
        self.flags = []
        self.responded = []
        self.registry = []

    def _a(self, name, *args):
        self.log.append((name,) + args)
        got = self.answers.get(name)
        return got(*args) if callable(got) else got

    def disarmed(self):
        return bool(self._a('disarmed'))

    def spawn(self, adapter, spec, resume_state=None, isolated=False):
        self.log.append(('spawn', spec, resume_state, isolated))
        got = self.answers.get('spawn')
        if callable(got):
            return got(adapter, spec)
        return got if got is not None else SimpleNamespace(pid=4242, create_time=7.5)

    def alive(self, handle):
        return bool(self._a('alive', handle))

    def kill(self, adapter, handle):
        self.kills.append((adapter, handle))
        return 'killed'

    def kill_identity(self, handle):
        self.kills.append(('identity', handle))
        return bool(self._a('kill_identity', handle))

    def set_flag(self, execution_id, flag):
        self.flags.append((execution_id, flag))

    def respond(self, execution_id, seq, decision, reason):
        self.responded.append((seq, decision, reason))

    def pending_requests(self, execution_id):
        return self._a('pending_requests', execution_id) or []

    def precompacted(self, execution_id):
        return bool(self._a('precompacted', execution_id))

    def git_branch(self, path):
        return self._a('git_branch', path)

    def git_remotes(self, path):
        return self._a('git_remotes', path) or {}

    def command_context(self, execution_id, workdir, cwd):
        return self._a('command_context', execution_id, workdir, cwd)

    def branch_exists(self, root, branch):
        return bool(self._a('branch_exists', root, branch))

    def add_worktree(self, root, path, branch, base='HEAD'):
        self.log.append(('add_worktree', root, path, branch, base))
        return path

    def diff_stat(self, workdir):
        return self._a('diff_stat', workdir) or []

    def end_state(self, workdir):
        return self._a('end_state', workdir)

    def ended(self, handle, exit_code, seq):
        return self._a('ended', handle, exit_code, seq)

    def unended(self):
        return self._a('unended') or []

    def files(self, execution_id):
        return self._a('files', execution_id)

    def isolation_record(self, execution_id):
        return self._a('isolation_record', execution_id)

    def reclaim_isolation(self, live):
        return self._a('reclaim_isolation', live) or []

    def _registry(self, line):
        self.registry.append(line)


def _mgr(**answers):
    """A manager off the database: the node is the fake, the writer is a list."""
    m = M.ExecutionManager.__new__(M.ExecutionManager)
    m.node = FakeNode(**answers)
    m._procs = {}
    m._noted = set()
    m._isolation_fault = None
    m._clock = {'accounts': 0.0, 'usage': 0.0, 'isolation': 0.0}
    m.calls = []
    m.db = SimpleNamespace(read=nullcontext,
                           writer=SimpleNamespace(live=(None, 'the-writer-path')))
    m.scenarios = {}
    m.policy = m.missions = m.router = None
    m.usage = None
    m.broker = None
    m.registry = SimpleNamespace(get=lambda hid: 'the-adapter')
    m.grace_s = 10.0
    m.pause_timeout = 120.0
    m.start_timeout = 60.0
    m.lost_after = 90.0
    m.actor = 'system'
    m.booted = False

    def _do(command, **kw):
        m.calls.append((command.__name__, kw))
        return {'refused': False, 'moved': 0}
    m._do = _do
    m._reload = lambda e: e
    m._tombstone = lambda e: None
    m._step = lambda e, mm, d: False
    return m


def _e(state='RUNNING', **over):
    """One execution row's fields, as far as the pass reads them."""
    e = {'id': ids.new_id('execution'), 'state': state, 'mission_id': 'mission-1',
         'harness_id': 'fake', 'task_id': 't1', 'account_id': None,
         'route_decision_id': None, 'process_seq': 1, 'stop_reason': None,
         'isolated': None, 'branch': None, 'workdir': None, 'stream_offset': 0,
         'usage': None, 'context': None, 'pressure': None, 'served_level': None,
         'served_model': None, 'model': 'm1', 'effort': None, 'adapter_state': {},
         'handoff_from': None, 'attempt': 1, 'pid': None, 'seed_revision': None,
         'charged': True, 'broker_token_hash': 'b' * 64, 'created_at': ''}
    e.update(over)
    return SimpleNamespace(**e)


def _proc(m, e, **over):
    """One live process in the pass's own book, from `_fresh`."""
    p = M.ExecutionManager._fresh(SimpleNamespace(), SimpleNamespace(), 1, 0, None)
    p.update(over)
    m._procs[e.id] = p
    return p


def _mission(state='EXECUTING', **over):
    d = {'id': MSN, 'state': state, 'project_id': None, 'objective': 'the aim'}
    d.update(over)
    return SimpleNamespace(**d)


def _task(mode='worktree', **over):
    d = {'key': 't1', 'title': 'T', 'kind': 'code', 'estimate': None,
         'action_classes': (), 'workspace_mode': mode}
    d.update(over)
    return SimpleNamespace(**d)


def _names(m):
    return [n for n, _ in m.calls]


def _kw(m, name):
    return [kw for n, kw in m.calls if n == name]


def _rows(monkeypatch, **by_kind):
    """What `rows.get` / `rows.where` answer, per entity kind."""
    def get(r, kind, id_):
        got = by_kind.get(kind.__name__)
        return SimpleNamespace(entity=got) if got is not None else None

    def where(r, kind, **filt):
        got = by_kind.get(kind.__name__)
        return [SimpleNamespace(entity=x) for x in (got if isinstance(got, list) else [got]
                                                    if got is not None else [])]
    monkeypatch.setattr(M.rows, 'get', get)
    monkeypatch.setattr(M.rows, 'where', where)


def _boom(*args, **kw):
    raise AssertionError('this seam must not be reached')


# ── the hook pass (_hooks): what one tool call is answered with ──────────────

def _hook_rig(tmp_path, monkeypatch, pending, *, isolated=None, record=None, branch=None,
              answer=None, broken=False):
    """`_hooks` on fakes: the writer, the canonicaliser and the node all log."""
    m = _mgr(isolation_record=record, pending_requests=pending)
    e = _e(workdir=str(tmp_path / 'work'), branch=branch, isolated=isolated)
    m._tail = lambda e, p: None
    seen = []

    def canonicalise_hook(tool, inp, ctx, command_context):
        seen.append((tool, ctx['cwd'], command_context))
        return ((), ('class-1',))
    monkeypatch.setattr(M.canonical, 'canonicalise_hook', canonicalise_hook)

    def _do(command, **kw):
        m.calls.append((command.__name__, kw))
        if broken:
            raise RuntimeError('the writer died mid-request')
        return dict(answer or {'decision': 'allow', 'reason': 'ok'})
    m._do = _do
    return m, e, seen


def test_an_unreadable_request_is_halted_and_judged_by_nobody(tmp_path, monkeypatch):
    # manager.py:607-609 (`if req is None`): a request Core cannot read is halted,
    # never handed to policy, and nothing else is written for it.
    m, e, seen = _hook_rig(tmp_path, monkeypatch,
                          [(7, None), (8, {'tool': 'Read', 'input': {}})])
    assert m._hooks(e, {}, disarmed=False) is True
    assert m.node.responded == [(7, 'halt', 'the request could not be read'),
                                (8, 'allow', 'ok')]
    assert _names(m) == ['serve_hook']                        # the readable one only
    assert [s[0] for s in seen] == ['Read']


def test_a_cwd_outside_the_workdir_is_never_ok(tmp_path, monkeypatch):
    # manager.py:612 (`cwd is None or _inside(cwd, workdir)`): the escaped cwd and
    # the absent cwd must reach the writer differently, by `_inside` alone.
    (tmp_path / 'work').mkdir()
    (tmp_path / 'elsewhere').mkdir()
    inside = str(tmp_path / 'work' / 'sub')
    for cwd, want in ((None, True), (str(tmp_path / 'work'), True), (inside, True),
                      (str(tmp_path / 'elsewhere'), False), (str(tmp_path), False)):
        m, e, seen = _hook_rig(tmp_path, monkeypatch,
                               [(1, {'tool': 'Read', 'input': {}, 'cwd': cwd})])
        assert m._hooks(e, {}, disarmed=False) is True, cwd
        assert _kw(m, 'serve_hook')[0]['cwd_ok'] is want, cwd
        assert m.node.responded == [(1, 'allow', 'ok')], cwd


def test_only_a_bash_call_inside_its_workdir_gets_a_command_context(tmp_path, monkeypatch):
    # manager.py:619-620 (`req.get('tool') == 'Bash' and cwd_ok`): the trusted
    # command evidence is taken for no other tool, and never for an escaped cwd.
    CTX = object()
    (tmp_path / 'work').mkdir()
    (tmp_path / 'elsewhere').mkdir()
    for tool, cwd, want in (('Bash', None, CTX), ('Bash', str(tmp_path / 'work'), CTX),
                            ('Bash', str(tmp_path / 'elsewhere'), None),
                            ('Read', None, None), ('Read', str(tmp_path / 'work'), None),
                            ('Write', str(tmp_path / 'elsewhere'), None)):
        m, e, seen = _hook_rig(tmp_path, monkeypatch,
                               [(1, {'tool': tool, 'input': {}, 'cwd': cwd})])
        m.node.answers['command_context'] = lambda *a: CTX
        assert m._hooks(e, {}, disarmed=False) is True, (tool, cwd)
        assert seen[-1][2] is want, (tool, cwd)
        asked = [x for x in m.node.log if x[0] == 'command_context']
        assert len(asked) == (1 if want is CTX else 0), (tool, cwd)


def test_a_branch_that_moved_halts_a_call_of_an_ordinary_execution(tmp_path, monkeypatch):
    # manager.py:625-626 (`e.branch is None or (not known and branch_now == e.branch)`):
    # policy only ever sees branch_ok True while the recorded branch is checked out.
    for now, want in (('archeus/m.t1', True), ('main', False), (None, False)):
        m, e, seen = _hook_rig(tmp_path, monkeypatch,
                               [(1, {'tool': 'Read', 'input': {}})], branch='archeus/m.t1')
        m.node.answers['git_branch'] = now
        assert m._hooks(e, {}, disarmed=False) is True, now
        assert _kw(m, 'serve_hook')[0]['branch_ok'] is want, now
    # an execution that never recorded a branch is not judged by one
    m, e, seen = _hook_rig(tmp_path, monkeypatch, [(1, {'tool': 'Read', 'input': {}})])
    m.node.answers['git_branch'] = lambda w: (_ for _ in ()).throw(AssertionError('no git'))
    assert m._hooks(e, {}, disarmed=False) is True
    assert _kw(m, 'serve_hook')[0]['branch_ok'] is True


def test_a_failure_to_judge_halts_and_never_allows(tmp_path, monkeypatch):
    # manager.py:629-630 (`except Exception`): the one place a broken judgement is
    # answered, and it is answered as a halt, never as an allow.
    m, e, seen = _hook_rig(tmp_path, monkeypatch, [(1, {'tool': 'Read', 'input': {}})],
                           broken=True)
    assert m._hooks(e, {}, disarmed=False) is True
    assert m.node.responded == [(1, 'halt', 'Archeus could not judge the request')]
    assert _names(m) == ['serve_hook']                # only the attempt, no other write


@pytest.mark.parametrize('answer', [{'decision': 'deny', 'reason': 'a locked floor'},
                                    {'decision': 'ask', 'reason': 'ask the owner'}],
                         ids=['deny', 'ask'])
def test_what_the_writer_decided_is_what_the_hook_is_answered(tmp_path, monkeypatch, answer):
    # manager.py:631 (`respond(..., out['decision'], out['reason'])`): the decision is
    # forwarded verbatim, so a deny cannot become an allow on the way.
    m, e, seen = _hook_rig(tmp_path, monkeypatch, [(1, {'tool': 'Read', 'input': {}})],
                           answer=answer)
    assert m._hooks(e, {}, disarmed=False) is True
    assert m.node.responded == [(1, answer['decision'], answer['reason'])]


@pytest.mark.parametrize('disarmed', [True, False], ids=['disarmed', 'armed'])
def test_the_estop_state_reaches_the_writer_through_the_hook(tmp_path, monkeypatch, disarmed):
    # manager.py:627 (`disarmed=disarmed`): policy is told the real state, both ways.
    m, e, seen = _hook_rig(tmp_path, monkeypatch, [(1, {'tool': 'Read', 'input': {}})])
    m._hooks(e, {}, disarmed=disarmed)
    assert _kw(m, 'serve_hook')[0]['disarmed'] is disarmed


# ── the stream (_tail / _pressure / _maybe_handoff / _progress / _watch) ─────

class _Snap:
    def __init__(self, events, offset):
        self.events, self.offset = tuple(events), offset


def _tail_rig(events, offset=40):
    """`_tail` on fakes: the adapter hands back one snapshot, and everything else
    the pass would write or read elsewhere is recorded."""
    m = _mgr()
    e = _e()

    class Adapter:
        def __init__(self):
            self.inspected = []

        def inspect(self, handle, off):
            self.inspected.append(off)
            return _Snap(events, offset)

    a = Adapter()
    p = _proc(m, e)
    p['adapter'] = a
    m._progress = lambda e, p: m.calls.append(('progress', {}))
    m._stop_account = lambda aid, reason, why: m.calls.append(
        ('stop_account', {'account_id': aid, 'reason': reason}))
    m._window = lambda e, adapter: (None, 'none')
    return m, e, p, a


def test_a_quiet_read_of_the_stream_writes_nothing():
    # manager.py:528-530 (`if not snap.events and snap.offset == p['offset']`): an
    # unchanged tail is no news; loosening it republishes progress on every pass.
    m, e, p, a = _tail_rig([])
    p['offset'] = 40
    assert m._tail(e, p) is False
    assert _names(m) == [] and a.inspected == [40]


def test_a_new_byte_alone_is_still_a_read_of_the_stream():
    # the same condition's other half: an offset that moved is news even with no
    # event in it, and the new offset is kept.
    m, e, p, a = _tail_rig([], offset=41)
    assert m._tail(e, p) is True
    assert p['offset'] == 41 and _names(m) == ['progress']


def test_a_model_event_is_provenance_and_never_a_progress_line():
    # manager.py:534-537 (`ev.get('type') == 'model'` then `continue`): it names the
    # served model and is not counted as output, so it cannot look like progress.
    m, e, p, a = _tail_rig([{'type': 'model', 'model': 'm2'}])
    assert m._tail(e, p) is True
    assert (p['events'], p['lines'], p['served']) == (0, [], {'level': 'SERVED',
                                                              'model': 'm2'})


def test_a_normal_line_is_counted_once_and_never_becomes_provenance():
    m, e, p, a = _tail_rig([{'type': 'assistant', 'text': 'hello'}])
    assert m._tail(e, p) is True
    assert p['events'] == 1 and p['lines'] == ['assistant: hello'] and 'served' not in p


def test_one_limit_event_limits_the_account_once():
    # manager.py:549-554 (`== 'limit'`, `account_id is not None`, `not p.get('limit')`):
    # the account is LIMITED and its work stopped exactly once per process.
    m, e, p, a = _tail_rig([{'type': 'limit', 'resets_at': '2026-10-30T12:00:00+00:00'}])
    e.account_id = 'account-1'
    assert m._tail(e, p) is True
    assert _names(m).count('account_limited') == 1 and _names(m).count('stop_account') == 1
    assert _kw(m, 'account_limited')[0]['account_id'] == 'account-1'
    assert _kw(m, 'account_limited')[0]['resets_at'] == '2026-10-30T12:00:00+00:00'
    assert _kw(m, 'stop_account')[0] == {'account_id': 'account-1', 'reason': 'limit'}
    m.calls = []
    assert m._tail(e, p) is True                               # the same event again
    assert 'account_limited' not in _names(m) and 'stop_account' not in _names(m)


def test_a_limit_event_without_an_account_stops_nothing():
    m, e, p, a = _tail_rig([{'type': 'limit'}])
    assert m._tail(e, p) is True
    assert 'account_limited' not in _names(m) and 'stop_account' not in _names(m)


def test_a_usage_report_is_measured_and_a_non_mapping_is_ignored():
    # manager.py:544-547 (`isinstance(ev.get('usage'), dict)`): only a mapping is a
    # usage report; a string one would raise inside the pressure read.
    m, e, p, a = _tail_rig([{'type': 'assistant', 'text': 'x', 'usage': '999'}])
    assert m._tail(e, p) is True
    assert p['usage'] is None and p['context'] is None
    m, e, p, a = _tail_rig([{'type': 'assistant', 'text': 'x',
                             'usage': {'input_tokens': 5}}])
    assert m._tail(e, p) is True
    assert p['usage'] == {'input_tokens': 5}
    assert p['context']['used_tokens'] == 5 and p['pressure'] is None


def test_pressure_under_the_threshold_hands_nothing_off():
    # manager.py:572 (`(p['pressure'] or 0.0) < PRESSURE_HANDOFF`): nothing is asked
    # of a running execution below the threshold, and it is not latched either.
    m = _mgr()
    e, p = _e(state='RUNNING'), {'pressure': PR.PRESSURE_HANDOFF - 0.01}
    m._progress = lambda e, p: m.calls.append(('progress', {}))
    m._maybe_handoff(e, p)
    assert _names(m) == [] and 'handing_off' not in p


@pytest.mark.parametrize('state', ['RUNNING', 'PAUSED', 'STOPPING', 'STARTING'],
                         ids=['running', 'paused', 'stopping', 'starting'])
def test_a_handoff_is_asked_once_and_only_of_running_work(state):
    # manager.py:572-580: `>= PRESSURE_HANDOFF`, the `handing_off` latch, and the
    # state re-read before the request is written.
    m = _mgr()
    e, p = _e(state=state), {'pressure': PR.PRESSURE_HANDOFF, 'context': None}
    m._progress = lambda e, p: m.calls.append(('progress', {}))
    m._maybe_handoff(e, p)
    asked = len(_kw(m, 'request_handoff'))
    assert asked == (1 if state == 'RUNNING' else 0), state
    if asked:
        assert _kw(m, 'request_handoff')[0]['stop_reason'] == 'pressure'
        assert p['handing_off'] is True
    m._maybe_handoff(e, p)                                     # the latch holds
    assert len(_kw(m, 'request_handoff')) == asked, state
    # a threshold reading exactly is a hand-off; one hundredth under it is not
    m2 = _mgr()
    p2 = {'pressure': PR.PRESSURE_HANDOFF - 0.0001}
    m2._progress = lambda e, p: None
    m2._maybe_handoff(_e(state='RUNNING'), p2)
    assert _names(m2) == []


def test_nothing_new_writes_no_progress_but_a_changed_measurement_does():
    # manager.py:584-587: the early return is exactly as wide as the five fields it
    # lists; a new pressure, basis, provenance or output is news on its own.
    m = _mgr()
    e = _e(stream_offset=10, context={'used_tokens': 1}, pressure=0.2,
           served_level=None, served_model=None)
    quiet = {'events': 0, 'offset': 10, 'context': {'used_tokens': 1}, 'pressure': 0.2,
             'served': None, 'lines': [], 'usage': None}
    m._progress(e, quiet)
    assert _names(m) == [], 'an unchanged pass writes no progress'
    for field, value in (('pressure', 0.9), ('context', {'used_tokens': 9}),
                         ('served', {'level': 'BILLED', 'model': 'm1'}), ('events', 3),
                         ('offset', 11)):
        m.calls = []
        m._progress(e, dict(quiet, **{field: value}))
        assert _names(m) == ['record_progress'], field
        assert _kw(m, 'record_progress')[0][field] == value or field == 'offset', field
    # the same pass again, once it has been reported: quiet again
    m.calls = []
    m._progress(e, quiet)
    assert _names(m) == []


def test_the_precompact_backstop_signals_once_and_raises_the_pressure():
    # manager.py:516-521 (`precompacted(...)` and `... != 'precompact'`): the
    # harness's own signal becomes one basis and the policy stand-in pressure, once.
    m = _mgr(precompacted=True)
    e = _e()
    p = _proc(m, e)
    handed = []
    m._tail = lambda e, p: False
    m._hooks = lambda e, p, d: False
    m._control = lambda e, mm, p, d: False
    m._maybe_handoff = lambda e, p: handed.append(p['pressure'])
    p['adapter'].status = lambda handle: base.ProcStatus('running')
    m._collect = lambda e, p, st: None
    assert m._watch(e, _mission(), disarmed=False) is False
    assert p['context']['signal'] == 'precompact' and handed == [PR.PRESSURE_PRECOMPACT]
    assert m._watch(e, _mission(), disarmed=False) is False
    assert handed == [PR.PRESSURE_PRECOMPACT], 'one signal, however many passes'


def test_an_exit_the_adapter_reports_ends_the_pass_at_once():
    m = _mgr(precompacted=False)
    e = _e()
    p = _proc(m, e)
    gone = base.ProcStatus('exited', 0)
    p['adapter'].status = lambda handle: gone
    m._tail = lambda e, p: False
    m._hooks = lambda e, p, d: False
    m._control = lambda e, mm, p, d: False
    got = []
    m._collect = lambda e, p, st: got.append(st)
    assert m._watch(e, _mission(), disarmed=False) is True
    assert got == [gone]


# ── control (_control): the flag, the grace, the timeout, the kill ───────────

def test_the_estop_stops_running_work_and_kills_at_once():
    # manager.py:636-638 (`disarmed and state in (...)`): an e-stop waits for no
    # boundary, and the flag it sets is the STOP flag.
    m = _mgr()
    e = _e(state='RUNNING')
    p = _proc(m, e)
    assert m._control(e, _mission(), p, disarmed=True) is True
    assert _names(m) == ['stop']
    assert _kw(m, 'stop')[0]['stop_reason'] == 'estop'
    assert m.node.flags == [(e.id, 'STOP')]
    assert m.node.kills == [(p['adapter'], p['handle'])]


def test_a_mission_that_ended_stops_the_work_and_still_waits_the_grace():
    # manager.py:639-643 and 667-669: the stop is charged to `cancel`, and a stop
    # that is not an immediate one is killed only after `grace_s`.
    for mission in (None, _mission('CANCELLED'), _mission('FAILED'), _mission('COMPLETED')):
        m = _mgr()
        e = _e(state='RUNNING', stop_reason='cancel')
        p = _proc(m, e)
        assert m._control(e, mission, p, disarmed=False) is True
        assert _kw(m, 'stop')[-1]['stop_reason'] == 'cancel', mission
        assert m.node.flags == [(e.id, 'STOP')], mission
        assert m.node.kills == [], mission                     # the grace still holds
        p['since'] = time.monotonic() - m.grace_s
        assert m._control(e, mission, p, disarmed=False) is True
        assert m.node.kills, mission                           # and then it does kill


def test_a_paused_mission_pauses_running_work_with_the_pause_flag():
    # manager.py:644-646 and 652-654: PAUSING takes the PAUSE flag, not the STOP one.
    m = _mgr()
    e = _e(state='RUNNING')
    p = _proc(m, e)
    assert m._control(e, _mission('PAUSED'), p, disarmed=False) is True
    assert _names(m) == ['pause_work']
    assert _kw(m, 'pause_work')[0]['mission_id'] == MSN
    assert m.node.flags == [(e.id, 'PAUSE')] and m.node.kills == []


@pytest.mark.parametrize('reason,killed',
                         [('pressure', False), ('user', False), ('limit', True),
                          ('estop', True), ('disarmed', True), ('breaker', True)],
                         ids=['pressure', 'user', 'limit', 'estop', 'disarmed', 'breaker'])
def test_a_handoff_meets_the_boundary_or_waits_the_timeout(reason, killed):
    # manager.py:656-662 (`e.stop_reason in _NOW` and `waited >= pause_timeout`): a
    # hand-off for an account change or an e-stop is killed at once, one for
    # pressure is left to reach a tool boundary.
    m = _mgr()
    e = _e(state='HANDING_OFF', stop_reason=reason)
    p = _proc(m, e)
    assert m._control(e, _mission(), p, disarmed=False) is True
    assert bool(m.node.kills) is killed, reason
    assert m.node.flags == [(e.id, 'HANDOFF')]


def test_a_handoff_that_never_meets_a_boundary_is_killed_eventually():
    m = _mgr()
    e = _e(state='HANDING_OFF', stop_reason='pressure')
    p = _proc(m, e)
    p['since'] = time.monotonic() - (m.pause_timeout + 1.0)
    assert m._control(e, _mission(), p, disarmed=False) is True
    assert len(m.node.kills) == 1


def test_a_pause_with_no_boundary_becomes_a_stop_and_restarts_its_clock():
    # manager.py:663-666 (`state == 'PAUSING' and waited >= pause_timeout`): the
    # command is `pause_timed_out`, and the wait for the stop starts again.
    m = _mgr()
    e = _e(state='PAUSING')
    p = _proc(m, e, since=time.monotonic() - (m.pause_timeout + 1.0), flagged=True)
    assert m._control(e, _mission(), p, disarmed=False) is True
    assert _names(m) == ['pause_timed_out']
    assert _kw(m, 'pause_timed_out')[0]['execution_id'] == e.id
    assert p['flagged'] is False and p['since'] > time.monotonic() - 2.0
    assert m.node.flags == [] and m.node.kills == []


def test_a_pause_inside_its_timeout_waits_and_flags_the_process_once():
    # manager.py:652-655 (`if not p['flagged']`): the flag is written once per pause,
    # not once per pass, and the wait is not re-started by a later pass.
    m = _mgr()
    e = _e(state='PAUSING')
    p = _proc(m, e)
    for _ in range(3):
        assert m._control(e, _mission(), p, disarmed=False) is True
    assert _names(m) == [] and m.node.kills == []
    assert m.node.flags == [(e.id, 'PAUSE')], 'one PAUSE flag, however many passes'
    assert p['since'] is not None and p['flagged'] is True


def test_a_state_that_needs_no_control_leaves_no_stale_wait_behind():
    # manager.py:647-649: a pass that is not pausing, stopping or handing off resets
    # `since` and `flagged`, or its next pause would be killed the first time it.
    m = _mgr()
    e = _e(state='RUNNING')
    p = _proc(m, e, since=time.monotonic() - 500.0, flagged=True)
    assert m._control(e, _mission(), p, disarmed=False) is False
    assert (p['since'], p['flagged']) == (None, False)
    assert m.node.flags == [] and m.node.kills == []


# ── the dispatch table (_step / _first / _paused / _awaiting / _resume) ──────

def test_every_state_of_the_pass_reaches_exactly_one_handler():
    # manager.py:187-206: the state table itself, one row per state, and the
    # `process_seq == 0` and `id in self._procs` gates beside it.
    m = _mgr()
    hits = []
    for name, want in (('_first', 'first'), ('_reconcile_one', 'reconcile'),
                       ('_watch', 'watch'), ('_paused', 'paused'),
                       ('_awaiting', 'awaiting')):
        setattr(m, name, (lambda w: (lambda *a: hits.append(w) or True))(want))
    for state, seq, live, want in (
            ('INTENT', 0, False, 'first'), ('INTENT', 2, False, 'reconcile'),
            ('RUNNING', 1, False, 'reconcile'), ('RUNNING', 1, True, 'watch'),
            ('STARTING', 1, True, 'watch'), ('STOPPING', 1, True, 'watch'),
            ('HANDING_OFF', 1, True, 'watch'), ('PAUSING', 1, True, 'watch'),
            ('PAUSED', 1, False, 'paused'), ('AWAITING_APPROVAL', 1, False, 'awaiting'),
            ('AWAITING_APPROVAL', 1, True, 'watch'), ('LOST', 1, False, 'reconcile')):
        hits[:] = []
        e = _e(state=state, process_seq=seq)
        m._procs = {e.id: object()} if live else {}
        assert M.ExecutionManager._step(m, e, _mission(), False) is True, (state, seq, live)
        assert hits == [want], (state, seq, live)
    hits[:] = []
    assert M.ExecutionManager._step(m, _e(state='ENDED_OK'), _mission(), False) is False
    assert hits == []


@pytest.mark.parametrize('mission,why', [(None, 'gone'),
                                         (_mission('CANCELLED'), 'CANCELLED'),
                                         (_mission('FAILED'), 'FAILED'),
                                         (_mission('COMPLETED'), 'COMPLETED')],
                         ids=['gone', 'cancelled', 'failed', 'completed'])
def test_nothing_starts_over_a_mission_that_is_gone_or_ended(mission, why):
    # manager.py:214-217: the execution is refused, charged to `cancel`, and the
    # reason names the mission's own state.
    m = _mgr()
    m._spawn = _boom
    assert m._first(_e(state='INTENT', process_seq=0), mission, False) is True
    assert _names(m) == ['refuse']
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'cancel'
    assert why in _kw(m, 'refuse')[0]['reason']


@pytest.mark.parametrize('state', ['PAUSED', 'BLOCKED', 'DRAFT'],
                         ids=['paused', 'blocked', 'draft'])
def test_a_mission_that_is_not_executing_waits_instead_of_refusing(state):
    m = _mgr()
    m._spawn = lambda *a, **kw: m.calls.append(('spawn', {})) or True
    assert m._first(_e(state='INTENT', process_seq=0), _mission(state), False) is False
    assert _names(m) == [], state


def test_the_estop_refuses_an_execution_before_anything_is_prepared():
    # manager.py:211-213: the very first check of `_first` is the e-stop, before the
    # mission, the workspace, the token and the adapter are touched.
    m = _mgr()
    m._spawn = _boom
    assert m._first(_e(state='INTENT', process_seq=0), _mission(), True) is True
    assert _names(m) == ['refuse']
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'disarmed'
    assert 'emergency stop' in _kw(m, 'refuse')[0]['reason']
    m2 = _mgr()
    m2._spawn = lambda *a, **kw: m2.calls.append(('spawn', {})) or True
    assert m2._first(_e(state='INTENT', process_seq=0), _mission(), False) is True
    assert _names(m2) == ['spawn'], 'armed work does reach the spawn'


@pytest.mark.parametrize('mission,why', [(None, 'the mission ended'),
                                         (_mission('CANCELLED'), 'the mission ended'),
                                         (_mission('FAILED'), 'the mission ended')],
                         ids=['gone', 'cancelled', 'failed'])
def test_a_paused_execution_ends_when_its_mission_can_no_longer_run(mission, why):
    # manager.py:780-786: the emergency stop and a gone or ended mission refuse it;
    # a mission that is merely not EXECUTING leaves it paused.
    m = _mgr()
    m._resume = _boom
    assert m._paused(_e(state='PAUSED'), mission, False) is True
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'cancel' and why in _kw(m, 'refuse')[0]['reason']
    m = _mgr()
    m._resume = _boom
    assert m._paused(_e(state='PAUSED'), _mission('PAUSED'), False) is False
    assert _names(m) == []
    m = _mgr()
    m._resume = lambda e, mm: m.calls.append(('resume', {})) or True
    assert m._paused(_e(state='PAUSED'), _mission(), False) is True
    assert _names(m) == ['resume']
    m = _mgr()
    m._resume = _boom
    assert m._paused(_e(state='PAUSED'), _mission(), True) is True
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'disarmed'
    assert 'emergency stop' in _kw(m, 'refuse')[0]['reason']


@pytest.mark.parametrize('approval,end', [(None, True),
                                           (SimpleNamespace(state='REJECTED'), True),
                                           (SimpleNamespace(state='EXPIRED'), True),
                                           (SimpleNamespace(state='SUPERSEDED'), True),
                                           (SimpleNamespace(state='REQUESTED'), False),
                                           (SimpleNamespace(state='WITHDRAWN'), False)],
                         ids=['none', 'rejected', 'expired', 'superseded', 'requested',
                              'withdrawn'])
def test_an_approval_wait_ends_only_on_an_answer_that_refuses_it(monkeypatch, approval, end):
    # manager.py:797-802: the end is written for the three refusing states and for no
    # row at all; anything short of APPROVED/CONSUMED keeps waiting, uncharged.
    m = _mgr()
    m._resume = _boom
    monkeypatch.setattr(X, 'waiting_approval', lambda r, e: approval)
    assert m._awaiting(_e(state='AWAITING_APPROVAL'), _mission(), False) is end
    assert _names(m) == (['approval_answered'] if end else [])


@pytest.mark.parametrize('state', ['APPROVED', 'CONSUMED'], ids=['approved', 'consumed'])
def test_an_approved_execution_resumes_only_under_an_executing_mission(monkeypatch, state):
    # manager.py:803-805 (`a.state not in ('APPROVED','CONSUMED') or m.state != ...`)
    m = _mgr()
    m._resume = lambda e, mm: m.calls.append(('resume', {})) or True
    monkeypatch.setattr(X, 'waiting_approval', lambda r, e: SimpleNamespace(state=state))
    assert m._awaiting(_e(state='AWAITING_APPROVAL'), _mission('PAUSED'), False) is False
    assert _names(m) == []
    assert m._awaiting(_e(state='AWAITING_APPROVAL'), _mission(), False) is True
    assert _names(m) == ['resume']


@pytest.mark.parametrize('installed,caps,refused',
                         [(False, ('resume',), True), (True, ('headless',), True),
                          (True, ('resume', 'headless'), False)],
                         ids=['not-installed', 'cannot-resume', 'can-resume'])
def test_a_halt_waits_for_a_harness_that_can_really_resume(installed, caps, refused):
    # manager.py:808-813 (`caps is None or 'resume' not in caps.capabilities`): an
    # adapter that is not installed, or cannot resume, is a charged binding end;
    # only a harness that can is asked again, and then it spawns.
    m = _mgr()
    adapter = SimpleNamespace(discover=lambda: SimpleNamespace(installed=installed),
                              capabilities=lambda _: SimpleNamespace(
                                  capabilities=frozenset(caps)))
    m.registry = SimpleNamespace(get=lambda hid: adapter)
    m._spawn = lambda e, mm, resume_state=None: m.calls.append(('spawn', resume_state)) or True
    e = _e(state='PAUSED', adapter_state={'step': 3})
    assert m._resume(e, _mission()) is True
    if refused:
        assert _names(m) == ['refuse']
        assert _kw(m, 'refuse')[0]['stop_reason'] == 'binding'
    else:
        assert _names(m) == ['resume_checked', 'spawn']
        assert _kw(m, 'spawn')[0] == {'step': 3}


# ── the ceilings and the account stop (_ceilings / _stop_account) ───────────

def test_the_allocation_ceiling_is_strict_and_reads_live_work_only(monkeypatch):
    # manager.py:837-852: only STARTING/RUNNING/PAUSING executions count, an account
    # with no reading is skipped entirely, and the ceiling trips at `>=`, not above.
    acc = SimpleNamespace(id='account-1', harness_id='fake', home_ref='h')
    asked = []

    def run(worst, states=('RUNNING',)):
        m = _mgr()
        _rows(monkeypatch, Account=acc, ResourcePolicy=[SimpleNamespace(allocation_pct=80.0)])
        # the worst of several windows is the one that trips the allocation
        m.usage = SimpleNamespace(read=lambda q: asked.append(q) or {'windows': {
            'quiet': 0.0, 'hot': worst, 'mid': worst / 2.0}})
        stopped = []
        m._stop_account = lambda aid, reason, why: stopped.append((aid, reason))
        live = [_e(state=s, account_id='account-1') for s in states]
        assert m._ceilings(live) == (1 if worst >= 80.0 else 0), worst
        return m, stopped
    for worst in (79.9, 80.0, 95.0):
        asked.clear()
        m, stopped = run(worst)
        assert _names(m) == ['observe'], worst
        assert _kw(m, 'observe')[0]['readings'] == {
            'account-1': {'windows': {'quiet': 0.0, 'hot': worst, 'mid': worst / 2.0}}}, worst
        assert asked == [{'id': 'account-1', 'harness_id': 'fake', 'home_ref': 'h'}], worst
        assert stopped == ([('account-1', 'ceiling')] if worst >= 80.0 else []), worst
    # an account whose work is only waiting for approval is not polled at all
    m = _mgr()
    _rows(monkeypatch, Account=acc, ResourcePolicy=[SimpleNamespace(allocation_pct=80.0)])
    seen = []
    m.usage = SimpleNamespace(read=lambda q: seen.append(q) or {'windows': {'w': 99.0}})
    m._stop_account = _boom
    assert m._ceilings([_e(state='AWAITING_APPROVAL', account_id='account-1'),
                        _e(state='PAUSED', account_id='account-1'),
                        _e(state='RUNNING', account_id=None)]) == 0
    assert seen == [] and _names(m) == []
    # nothing observed when the reader has nothing to say
    m = _mgr()
    _rows(monkeypatch, Account=acc, ResourcePolicy=[SimpleNamespace(allocation_pct=80.0)])
    m.usage = SimpleNamespace(read=lambda q: {})
    m._stop_account = _boom
    assert m._ceilings([_e(state='RUNNING', account_id='account-1')]) == 0
    assert _names(m) == [], 'an account with no reading is not even observed'


@pytest.mark.parametrize('reason', list(X.HANDOFF_CAUSES) + ['user', 'cancel'],
                         ids=list(X.HANDOFF_CAUSES) + ['user', 'cancel'])
def test_an_account_stop_continues_running_work_and_stops_the_rest(reason):
    # manager.py:820-833: exactly those six states are touched, and a running one is
    # continued elsewhere only while the reason is a hand-off cause.
    mine = [_e(state=s, account_id='account-1') for s in
            ('INTENT', 'PAUSED', 'AWAITING_APPROVAL', 'STARTING', 'RUNNING', 'PAUSING')]
    others = [_e(state='RUNNING', account_id='account-2'), _e(state='STOPPING',
                                                               account_id='account-1'),
              _e(state='HANDING_OFF', account_id='account-1'), _e(state='ENDED_OK',
                                                                   account_id='account-1')]
    m = _mgr()
    m._read = lambda: (mine + others, {})
    m._stop_account('account-1', reason, 'the reason')
    asked = {kw['execution_id'] for kw in _kw(m, 'request_handoff')}
    stopped = {kw['execution_id'] for kw in _kw(m, 'stop')}
    assert asked == ({mine[4].id} if reason in X.HANDOFF_CAUSES else set()), reason
    assert stopped == {x.id for x in mine} - asked, reason
    assert not asked & stopped, reason
    for kw in _kw(m, 'stop'):
        assert kw['stop_reason'] == reason and kw['reason'] == 'the reason'


# ── the window and the workspace (_window / _workspace) ─────────────────────

def _offers(models):
    return SimpleNamespace(capabilities=lambda ref: SimpleNamespace(models=models))


def test_the_context_window_comes_from_the_offer_then_from_the_smallest(monkeypatch):
    # manager.py:470-475 (`if e.model in known`, `min(known.values())`, the truthy
    # window filter): the smallest declared window, never the largest, never one that
    # was not declared, and never a bare string offer.
    M_ = base.ModelInfo
    models = [M_('m1', None, 200000), M_('m2', None, 32000), M_('m3', None, None), 'legacy']
    for model, want, source in (('m1', 200000, 'offer'), ('m2', 32000, 'offer'),
                                ('other', 32000, 'harness_smallest'),
                                (None, 32000, 'harness_smallest')):
        m = _mgr()
        assert m._window(_e(model=model, account_id=None), _offers(models)) == (want, source)
    m = _mgr()
    assert m._window(_e(model='m1'), _offers([M_('m1', None, None), 'legacy'])) == \
        (None, 'none')

    def broken(_):
        raise RuntimeError('the offer could not be read')
    m = _mgr()
    assert m._window(_e(model='m1'), SimpleNamespace(capabilities=broken)) == (None, 'none')
    # an account whose row is gone: still asked, with no home claimed for it
    _rows(monkeypatch)
    m = _mgr()
    assert m._window(_e(model='m1', account_id='account-1'), _offers(models)) == \
        (200000, 'offer')


def test_a_project_with_no_root_and_a_branch_that_cannot_be_read_are_safe(monkeypatch,
                                                                          tmp_path):
    # manager.py:493-499 (`if not roots: raise`, `and branch is not None`): a project
    # with no root is an OSError, and a worktree task whose branch cannot be read runs
    # in place rather than under a base nobody verified.
    _rows(monkeypatch)                                            # no project row at all
    m = _mgr()
    with pytest.raises(OSError):
        m._workspace(_e(), _mission(project_id=PRJ), _task(), isolated=False)
    m = _mgr()
    _rows(monkeypatch, Project=SimpleNamespace(root_paths=[]))
    with pytest.raises(OSError):                                  # an empty root list too
        m._workspace(_e(), _mission(project_id=PRJ), _task(), isolated=False)
    root = str(tmp_path / 'root')
    m = _mgr(git_branch=None)
    _rows(monkeypatch, Project=SimpleNamespace(root_paths=[root]))
    assert m._workspace(_e(), _mission(project_id=PRJ), _task(), isolated=False) \
        == (root, None)
    assert [x for x in m.node.log if x[0] == 'add_worktree'] == []


def test_an_isolated_execution_is_refused_a_project_workspace(monkeypatch, tmp_path):
    # manager.py:487-492 (`if isolated: raise`): never the user's root, never a
    # worktree linked to its .git, and no git probe of the root first.
    root = str(tmp_path / 'root')
    m = _mgr(git_branch=lambda p: (_ for _ in ()).throw(AssertionError('no git probe')))
    _rows(monkeypatch, Project=SimpleNamespace(root_paths=[root]))
    with pytest.raises(OSError):
        m._workspace(_e(), _mission(project_id=PRJ), _task(), isolated=True)
    assert [x for x in m.node.log if x[0] == 'git_branch'] == []


def test_a_worktree_starts_from_the_mission_branch_once_it_exists(monkeypatch, tmp_path):
    # manager.py:499-507 (`t.workspace_mode == 'worktree' and branch is not None`,
    # `mission if branch_exists(...) else 'HEAD'`): the dependency a later task sees
    # is the merged mission branch, under the one segment P9's profiles allow.
    root = str(tmp_path / 'root')
    m = _mgr(git_branch='main', branch_exists=False)
    _rows(monkeypatch, Project=SimpleNamespace(root_paths=[root]))
    e, mission, task = _e(), _mission(project_id=PRJ), _task('worktree')
    assert m._workspace(e, mission, task, isolated=False)[1] == 'archeus/%s.t1' % MSN
    line = [x for x in m.node.log if x[0] == 'add_worktree'][0]
    assert line[4] == 'HEAD', line
    m.node.answers['branch_exists'] = True
    m._workspace(e, mission, task, isolated=False)
    line = [x for x in m.node.log if x[0] == 'add_worktree'][-1]
    assert line[4] == M.mission_branch(MSN) == 'archeus/%s' % MSN, line
    # an in-place task takes the root and the branch that is checked out
    m2 = _mgr(git_branch='main')
    _rows(monkeypatch, Project=SimpleNamespace(root_paths=[root]))
    assert m2._workspace(e, mission, _task('in_place'), isolated=False) == (root, 'main')


# ── recovery (_collect_gone / _orphans / _sweep_isolation) ──────────────────

@pytest.mark.parametrize('state,want',
                         [('STOPPING', 'collect'), ('HANDING_OFF', 'collect'),
                          ('PAUSING', 'collect'), ('RUNNING', 'lost'),
                          ('STARTING', 'lost'), ('INTENT', 'lost')],
                         ids=['stopping', 'handing-off', 'pausing', 'running', 'starting',
                              'intent'])
def test_an_exit_nobody_read_is_never_a_success(state, want):
    # manager.py:1147-1160 (`st.state != 'exited' or st.exit_code is None`, then the
    # three states that are collected and the rest that are LOST).
    m = _mgr()
    e = _e(state=state)
    adapter = SimpleNamespace(status=lambda handle: base.ProcStatus('unknown', None))
    got = []
    m._collect = lambda e, p, st: got.append(st)
    assert m._collect_gone(e, adapter, object()) is True
    if want == 'collect':
        assert got == [base.ProcStatus('exited', None)] and _names(m) == []
    else:
        assert got == [] and _names(m) == ['lost']
        assert 'left no exit' in _kw(m, 'lost')[0]['reason']


def test_an_orphan_is_killed_after_the_grace_and_at_once_under_the_estop():
    # manager.py:169-177 (`st.state == 'running'`, `since` taken once, `disarmed or
    # waited >= grace_s`): the grace is measured from the first look at it.
    for waited, disarmed, killed in ((None, False, False), (0.0, False, False),
                                     (10.0, False, True), (0.0, True, True)):
        m = _mgr()
        e = _e(state='ENDED_KILLED')
        p = _proc(m, e, since=None if waited is None else time.monotonic() - waited)
        p['adapter'].status = lambda handle: base.ProcStatus('running', None)
        assert m._orphans(set(), disarmed) == (1 if killed else 0), (waited, disarmed)
        assert bool(m.node.kills) is killed, (waited, disarmed)
        assert _names(m) == [], 'an orphan under its grace is not collected'
        assert p['since'] is not None, 'the wait starts the first time it is seen'


def test_an_orphan_that_exited_is_collected_once_and_then_forgotten(monkeypatch):
    # manager.py:178-184: an ended orphan goes through the collection that records
    # its end and drops its key, so the next pass does not read it again.
    m = _mgr()
    e = _e(state='RUNNING')
    p = _proc(m, e)
    st = base.ProcStatus('exited', 0)
    p['adapter'].status = lambda handle: st
    _rows(monkeypatch, Execution=e)
    got = []

    def _collect(e, p, st):
        got.append(st)
        m._procs.pop(e.id, None)                  # what the real one does with the key
    m._collect = _collect
    assert m._orphans(set(), False) == 1
    assert got == [st]
    assert m._orphans(set(), False) == 0 and e.id not in m._procs


def test_a_live_execution_is_left_out_of_the_orphan_pass_entirely():
    m = _mgr()
    e = _e(state='RUNNING')
    p = _proc(m, e)
    p['adapter'].status = _boom
    assert m._orphans({e.id}, False) == 0 and m.node.kills == []


def test_the_isolation_sweep_skips_live_work_and_logs_one_fault(caplog, monkeypatch):
    # manager.py:1112-1124 (`sweeper is None`, `or []`, and the one-logging rule): a
    # node without the authority is left alone, the sweep is told only the live ids,
    # and one standing fault is logged once rather than once per pass.
    m = _mgr()
    m.node = object()                                   # a node with no such authority
    assert m._sweep_isolation([_e()]) == [], 'no sweeper, no sweep'
    m = _mgr()
    asked = []
    monkeypatch.setattr(m.node, 'reclaim_isolation', lambda live: asked.append(live) or None)
    live = [_e(), _e()]
    assert m._sweep_isolation(live) == []
    assert asked == [{x.id for x in live}]
    fault = OSError('the identity could not be torn down')

    def sweep(live):
        raise fault
    monkeypatch.setattr(m.node, 'reclaim_isolation', sweep)

    def logged():
        return sum(1 for r in caplog.records if 'isolation sweep did not complete'
                   in r.getMessage())
    with caplog.at_level('WARNING'):
        assert m._sweep_isolation(live) == []
        assert logged() == 1
        assert m._sweep_isolation(live) == []
        assert logged() == 1, 'a standing fault is not logged once per pass'
        fault = OSError('a different failure entirely')
        assert m._sweep_isolation(live) == []
        assert logged() == 2, 'a new fault is still logged'


# ── the facts a checkpoint is built from (_facts / _facts_from / _fresh) ────

def test_no_git_runs_where_the_execution_had_neither_branch_nor_workdir():
    # manager.py:772-777 (`self.node.diff_stat(workdir) if e.branch or e.workdir`,
    # twice, and `[-30:]`): no Core Git where the execution never worked, and the
    # decisions kept are the last thirty.
    m = _mgr()
    m.node.answers['diff_stat'] = m.node.answers['end_state'] = _boom
    facts = m._facts(_e(branch=None, workdir=None),
                     {'decisions': ['d%d' % i for i in range(35)], 'last_error': 'boom'})
    assert facts == {'files_changed': [], 'decisions': ['d%d' % i for i in range(5, 35)],
                     'last_error': 'boom', 'end_state': None}
    assert m.node.log == []


def test_decision_lines_and_the_last_error_are_kept_as_they_are_read():
    # manager.py:1177-1186: a DECISION line counts only at the start of a line of an
    # assistant event, and an error, stderr or limit event is the last error.
    p = M.ExecutionManager._fresh(object(), object(), 1, 0, None)
    M._facts_from({'type': 'assistant',
                   'text': 'a\n  DECISION: keep me\nnot DECISION: shout'}, p)
    M._facts_from({'type': 'tool', 'text': 'DECISION: not from a tool event'}, p)
    M._facts_from({'type': 'assistant', 'text': 7}, p)
    assert p['decisions'] == ['keep me'] and p['last_error'] is None
    M._facts_from({'type': 'error', 'text': 'it broke'}, p)
    assert p['last_error'] == 'it broke'
    p2 = M.ExecutionManager._fresh(object(), object(), 1, 0, None)
    M._facts_from({'type': 'limit', 'kind': 'rate'}, p2)
    assert p2['last_error'] == 'rate'
    p3 = M.ExecutionManager._fresh(object(), object(), 1, 0, None)
    M._facts_from({'type': 'assistant', 'text': 'DECISION: ' + 'x' * (M.FACT_CAP + 50)}, p3)
    assert len(p3['decisions'][0]) == M.FACT_CAP


def test_a_process_starts_with_nothing_measured():
    # manager.py:434-439 (`_fresh`): the defaults a pass must not inherit, above all
    # `window_source='none'`, `since=None` and an empty decision list.
    p = M.ExecutionManager._fresh('adapter', 'handle', 4, 17, {'input_tokens': 1})
    assert p['adapter'] == 'adapter' and p['handle'] == 'handle'
    assert (p['seq'], p['offset'], p['usage']) == (4, 17, {'input_tokens': 1})
    assert (p['reported'], p['events'], p['lines'], p['since'], p['flagged']) == \
        (0.0, 0, [], None, False)
    assert p['decisions'] == [] and p['last_error'] is None and p['pressure'] is None
    assert p['window'] is None and p['window_source'] == 'none' and p['context'] is None


def test_an_unmeasured_end_says_so_rather_than_nothing_changed():
    # manager.py:1189-1193 (`_unmeasured`): the diff is stated as not measured, never
    # as the empty list a checkpoint would read as a workdir nothing touched.
    f = M._unmeasured({'decisions': ['a'], 'last_error': 'boom'})
    assert f['files_changed'] == [M.UNMEASURED] and f['end_state'] is None
    assert f['decisions'] == ['a'] and f['last_error'] == 'boom'
    assert M._unmeasured({})['decisions'] == [] and M._unmeasured({})['last_error'] is None


# ── the broker's recheck (broker_live) ───────────────────────────────────────

def _binding(**over):
    from archeus.node import broker as B
    d = dict(core_instance='c', execution_id=None, process_seq=2, principal='p',
             route_decision_id='route-1', account_id='account-1', harness_id='claude_code',
             model='m1', upstream=None, limits=None)
    d.update(over)
    return B.BrokerBinding(**d)


def _live():
    return _e(state='RUNNING', isolated=True, process_seq=2, route_decision_id='route-1',
              account_id='account-1', model='m1', broker_token_hash='b' * 64)


@pytest.mark.parametrize('field,value',
                         [('state', 'ENDED_OK'), ('state', 'ENDED_KILLED'),
                          ('state', 'ABANDONED'), ('isolated', False), ('isolated', None),
                          ('process_seq', 3), ('broker_token_hash', 'c' * 64),
                          ('route_decision_id', 'route-2'), ('route_decision_id', None),
                          ('account_id', 'account-2'), ('account_id', None),
                          ('model', 'other')],
                         ids=['ended-ok', 'ended-killed', 'abandoned', 'not-isolated',
                              'unknown-isolation', 'other-generation', 'other-digest',
                              're-routed', 'no-route', 'other-account', 'no-account',
                              'other-model'])
def test_a_grant_follows_exactly_its_own_recorded_generation(monkeypatch, field, value):
    # manager.py:420-425: every one of the seven comparisons, one at a time. A grant
    # whose execution was re-routed, re-accounted or restarted is not its execution's.
    e = _live()
    setattr(e, field, value)
    m = _mgr()
    _rows(monkeypatch, Execution=e)
    binding = _binding(execution_id=e.id)
    assert m.broker_live(binding, 'b' * 64) is False, (field, value)


def test_a_live_recorded_generation_holds_its_grant(monkeypatch):
    m = _mgr()
    e = _live()
    _rows(monkeypatch, Execution=e)
    assert m.broker_live(_binding(execution_id=e.id), 'b' * 64) is True


def test_a_row_that_is_gone_holds_no_grant(monkeypatch):
    m = _mgr()
    _rows(monkeypatch)                                            # no execution at all
    assert m.broker_live(_binding(execution_id=ids.new_id('execution')), 'b' * 64) is False


# ── the pass clock (tick) ───────────────────────────────────────────────────

def test_the_pass_clocks_run_one_in_its_own_time(monkeypatch):
    # manager.py:147-158 (`>= ACCOUNTS_S`, `self.usage is not None and >= USAGE_S`,
    # `>= ISOLATION_SWEEP_S`): the ceilings run only while a usage reader is held,
    # and the isolation sweep is not counted as work done.
    m = _mgr(disarmed=False)
    m._read = lambda: ([], {})
    m._clock = dict.fromkeys(('accounts', 'usage', 'isolation'), -1e6)
    m.broker = None
    swept, ceil = [], []
    monkeypatch.setattr(m.node, 'reclaim_isolation', lambda live: swept.append(live))
    m._ceilings = lambda live: ceil.append(live) or 0
    assert m.tick() == 0, 'an idle pass stays an idle pass'
    assert _names(m) == ['accounts_tick'] and ceil == [] and swept == [set()]
    now = time.monotonic()
    m._clock = dict.fromkeys(('accounts', 'usage', 'isolation'), now)
    m.calls = []
    assert m.tick() == 0
    assert _names(m) == [] and ceil == [] and swept == [set()], 'nothing is due yet'
    m._clock = dict.fromkeys(('accounts', 'usage', 'isolation'), -1e6)
    m.usage = SimpleNamespace(read=lambda q: {})
    m.tick()
    assert len(ceil) == 1, 'the ceilings run once the reader is held'
    assert len(swept) == 2 and _names(m) == ['accounts_tick']


class _Broker:
    """The broker seam: which of its two doors the pass knocked on, and with what."""

    def __init__(self):
        self.done = []

    def sweep(self, ids):
        self.done.append(('sweep', set(ids)))

    def revoke_all(self):
        self.done.append(('revoke_all', None))


def test_the_broker_grants_of_work_that_is_gone_are_revoked():
    # manager.py:139-146 (`if self.broker is not None`, `if disarmed`): under the
    # e-stop every grant goes, otherwise only the ones no live execution holds.
    live = [_e(), _e()]
    for disarmed, want in ((False, 'sweep'), (True, 'revoke_all')):
        m = _mgr(disarmed=disarmed)
        m._read = lambda: (live, {})
        m._clock = dict.fromkeys(('accounts', 'usage', 'isolation'), time.monotonic())
        broker = _Broker()
        m.broker = broker
        m.tick()
        assert [d[0] for d in broker.done] == [want], disarmed
        if want == 'sweep':
            assert broker.done[0][1] == {x.id for x in live}


# ---------- the spawn (manager.py:218-304) ----------------------------------

def _spawn_rig(monkeypatch, permitted=True, disarms=(False, False), prepare_refused=False):
    """A manager whose spawn talks to the seams only: the terms read, the workspace,
    the size read, the spawn and the registry are all recorded in ONE sequence, so
    the ORDER the pass does them in is pinned as well as whether it does them."""
    m = _mgr()
    m.registry = SimpleNamespace(get=lambda hid: SimpleNamespace(id='fake'))
    order = m.node.log                                      # one sequence for everything

    def _terms(r, adapter):
        order.append(('terms',))
        return permitted

    def _workspace(e, mm, t, isolated=None):
        order.append(('workspace',))
        return '/work', 'archeus/mission-1.t1'

    def _offset(e):
        order.append(('offset',))
        return 77

    def _do(command, **kw):
        m.calls.append((command.__name__, kw))
        order.append((command.__name__,))
        return {'refused': prepare_refused, 'moved': 0, 'why': 'the hook is not there'}

    def _disarmed():
        asked = len([x for x in order if x[0] in ('prepare_process', 'spawn')])
        return disarms[min(max(asked - 1, 0), len(disarms) - 1)]

    monkeypatch.setattr(M.resources, 'terms_permit', _terms)
    monkeypatch.setattr(M.optins, 'effective', lambda r, account_id=None, project_id=None: ())
    _rows(monkeypatch, Task=_task('worktree'))
    m._workspace = _workspace
    m._offset = _offset
    m._do = _do
    m.node.answers['disarmed'] = _disarmed
    m.node.answers['spawn'] = lambda a, spec: SimpleNamespace(pid=4242, create_time=7.5)
    return m


def test_the_provider_terms_are_read_before_anything_is_asked_of_the_node(monkeypatch):
    # manager.py:231-234 (ADR-0021): the terms gate runs before the workspace is
    # staged and before the process is prepared or spawned.
    m = _spawn_rig(monkeypatch, permitted=True)
    assert m._spawn(_e(), _mission()) is True
    assert [x[0] for x in m.node.log] == ['terms', 'workspace', 'prepare_process',
                                          'disarmed',          # the stop, before the spawn
                                          'offset', 'spawn', 'record_process', 'disarmed']


def test_work_whose_provider_terms_do_not_permit_it_never_reaches_the_node(monkeypatch):
    # manager.py:231-234: nothing is staged, prepared or spawned when the terms refuse,
    # and the end is charged to the binding, not to a spawn that never happened.
    m = _spawn_rig(monkeypatch, permitted=False)
    assert m._spawn(_e(), _mission()) is True
    assert _kw(m, 'refuse')[0]['reason'] == 'provider terms do not permit it'
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'binding'
    assert _names(m) == ['refuse'], 'the node was never touched'
    assert [x[0] for x in m.node.log] == ['terms', 'refuse'], 'no workspace, no prepare, no spawn'


def test_the_process_is_recorded_with_the_generation_and_token_it_was_started_with(monkeypatch):
    # manager.py:269,333-375: the prepare, the child and the registry row carry ONE
    # process_seq, the recorded token digest is the hash of the token in the child
    # env, and the account the child runs under is the account ref it was given.
    e = _e(process_seq=2)
    m = _spawn_rig(monkeypatch, disarms=(False, False))
    assert m._spawn(e, _mission()) is True
    spec = [x for x in m.node.log if x[0] == 'spawn'][0][1]
    prepared = _kw(m, 'prepare_process')[0]
    recorded = _kw(m, 'record_process')[0]
    assert prepared['workdir'] == spec.workdir == '/work'
    assert set(recorded) == {'execution_id', 'pid', 'create_time', 'process_seq'}
    assert spec.process_seq == prepared['process_seq'] == recorded['process_seq'] == 3
    assert spec.prompt.startswith('the aim\n\nT\n'), 'what the child is told'
    assert X.token_hash(spec.env['ARCHEUS_HOOK_TOKEN']) == prepared['token_digest']
    assert recorded['pid'] == 4242 and recorded['create_time'] == 7.5
    assert spec.account.account_id == 'fake' and spec.account.home_ref is None, \
        'a default harness account, and the home its decision recorded'
    assert spec.task_contract['key'] == 't1' and spec.task_contract['kind'] == 'code'
    assert spec.task_contract['estimate'] is None
    assert spec.task_contract['action_classes'] == [], "the task's own action classes"
    assert spec.task_contract['continuation'] == 0, 'not a continuation of anything'
    _rows(monkeypatch, Task=_task('worktree'),
          Account=SimpleNamespace(id='account-9', home_ref='the recorded home'))
    assert m._spawn(_e(process_seq=2, account_id='account-9'), _mission()) is True
    given = [x for x in m.node.log if x[0] == 'spawn'][-1][1].account
    assert given.account_id == 'account-9' and given.home_ref == 'the recorded home'
    assert all(spec.env[k] == v for k, v in M.CAPABILITY_ENV.items()), \
        'the capability gate the child starts with'


def test_the_stop_wins_the_race_against_the_spawn_and_the_launch_cannot_start(monkeypatch):
    # manager.py:340-344 and 376-378: the stop is checked after the prepare (nothing
    # starts) and again after the record (the process that did start is stopped).
    m = _spawn_rig(monkeypatch, disarms=(True, False))
    assert m._spawn(_e(), _mission()) is True
    assert _names(m) == ['prepare_process', 'refuse']
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'disarmed'
    assert 'spawn' not in [x[0] for x in m.node.log]
    m = _spawn_rig(monkeypatch, disarms=(False, True))
    assert m._spawn(_e(), _mission()) is True
    assert _names(m) == ['prepare_process', 'record_process', 'stop']
    assert _kw(m, 'stop')[0]['stop_reason'] == 'disarmed'
    assert _kw(m, 'stop')[0]['reason'] == 'emergency stop during the spawn'


def test_a_prepare_that_refuses_leaves_the_work_prepared_by_nobody(monkeypatch):
    # manager.py:337-339: the hook runtime's own refusal starts nothing and records
    # nothing — the work stays where it is, and the child is never asked for.
    m = _spawn_rig(monkeypatch, prepare_refused=True)
    assert m._spawn(_e(), _mission()) is True
    assert _names(m) == ['prepare_process'], 'no refusal, no spawn, no record'
    assert 'spawn' not in [x[0] for x in m.node.log]


# ---------- what the stream says is billed ----------------------------------

def test_the_model_that_answered_is_provenance_and_the_billed_one_is_the_attributed_one():
    # manager.py:535-542 (`p['served'] = {'level': 'SERVED', ...}` and the `_billed`
    # line): an answer's own model is recorded, a billed line claims only what the
    # usage attributes, and a billed line that can attribute nothing claims nothing.
    m, e, p, a = _tail_rig([{'type': 'model', 'model': 'm1'},
                           {'billed': ['m1', 'other'], 'text': 'said'}])
    assert m._tail(e, p) is True
    assert p['served'] == {'level': 'BILLED', 'model': 'm1'}
    m, e, p, a = _tail_rig([{'billed': ['one', 'two'], 'text': 'said'}])
    assert m._tail(e, p) is True
    assert p['served'] is None, 'nothing attributed: nothing is claimed'
    m, e, p, a = _tail_rig([{'type': 'model', 'model': 'm9'},
                           {'billed': ['other'], 'text': 'said'}])
    assert m._tail(e, p) is True
    assert p['served'] == {'level': 'BILLED', 'model': 'other'}, 'the only model it attributes'


# ---------- the end of a process (manager.py:676-731) -----------------------

def _collect_rig(state='RUNNING', isolated=False, failure=None, offset=1, exit_code=0,
                 halted=False, exit_reason=None, account='account-1', seed=None, usage=None):
    """`_collect` on fakes: the adapter's end report, the node's observed exit and the
    isolation questions are all answers, and every command the end writes is listed."""
    m = _mgr()
    e = _e(state=state, account_id=account, seed_revision=seed)
    p = _proc(m, e, offset=offset)
    p['seq'] = 4
    p['adapter'] = SimpleNamespace(collect_result=lambda handle: SimpleNamespace(
        usage=usage, usage_total=True, failure=failure, exit_reason=exit_reason,
        halted=halted, adapter_state={'a': 1}, reported_summary='the report'))
    m.node.answers['ended'] = lambda h, code, seq: base.ProcStatus('exited', exit_code)
    m._tail = lambda e, p: None
    m._progress = lambda e, p: None
    m._isolation_record = lambda xid: None
    m._isolated = lambda x, rec: isolated
    m._facts = lambda x, pp: {'facts': 'of the stream'}
    m._release_isolation = lambda x: m.calls.append(('release_isolation', {}))
    m._import = lambda x, rec: m.calls.append(('import', {})) or {
        'revision': 'r-1', 'tree': 't-1', 'files_changed': [], 'deleted': 0,
        'dropped_dirs': 0, 'why': None}
    return m, e, p


def test_a_limit_seen_only_at_the_exit_limits_the_account_and_hands_the_work_on():
    # manager.py:693-700: a limit the adapter reports only when the process ended
    # still LIMITEDs the account and hands the work on, but only for a RUNNING
    # execution of an account that has one.
    m, e, p = _collect_rig(failure='limit')
    m._collect(e, p, base.ProcStatus('exited', 0))
    assert _names(m) == ['account_limited', 'request_handoff', 'record_end']
    assert _kw(m, 'account_limited')[0] == {'account_id': 'account-1'}
    assert _kw(m, 'request_handoff')[0]['stop_reason'] == 'limit'
    assert _kw(m, 'record_end')[0]['failure'] == 'limit'
    for over in ({'account': None}, {'state': 'HANDING_OFF'}):
        m, e, p = _collect_rig(failure='limit', **over)
        m._collect(e, p, base.ProcStatus('exited', 0))
        assert 'account_limited' not in _names(m), over
        assert 'request_handoff' not in _names(m) or over.get('state') == 'HANDING_OFF'


def test_work_that_is_already_ended_is_only_let_go_of():
    # manager.py:682-684 and 730-731 (`if e.state in _ENDED`): the row's own state
    # decides, and an end that is already recorded is never written a second time;
    # the isolation is still released, both here and after the recorded end.
    m, e, p = _collect_rig(state='ENDED_OK')
    assert m._collect(e, p, base.ProcStatus('exited', 0)) is None
    assert _names(m) == ['release_isolation']
    seen = []

    def _reload(x):
        seen.append(1)
        return x if len(seen) == 1 else _e(state='ENDED_KILLED', account_id='account-1')
    m, e, p = _collect_rig()
    m._reload = _reload
    m._collect(e, p, base.ProcStatus('exited', 1))
    assert _names(m) == ['record_end', 'release_isolation']


def test_a_process_that_wrote_nothing_is_never_imported_as_if_it_had_worked():
    # manager.py:711 (`X.imports(..., p['offset'] > 0)`): a STARTING execution that
    # never wrote a byte has nothing to import; one that wrote something does.
    m, e, p = _collect_rig(state='STARTING', isolated=True, seed='rev-1', offset=0)
    m._collect(e, p, base.ProcStatus('exited', 0))
    assert 'import' not in _names(m), 'no output, no import'
    assert 'no_import' not in _kw(m, 'record_end')[0], 'an ordinary end asks for no import'
    m, e, p = _collect_rig(state='STARTING', isolated=True, seed='rev-1', offset=1)
    m._collect(e, p, base.ProcStatus('exited', 0))
    assert _names(m)[:2] == ['import', 'record_end']
    assert _kw(m, 'record_end')[0]['import_revision'] == 'r-1'
    assert _kw(m, 'record_end')[0]['final_offset'] == 1


def test_the_answer_of_the_stream_is_read_before_the_execution_is_answered(tmp_path,
                                                                           monkeypatch):
    # manager.py:613 (`self._tail(e, p)` before the requests are answered): a tool
    # call is judged on the stream as far as it has been read, so the read that
    # makes the execution's state current cannot come after the answer.
    m, e, seen = _hook_rig(tmp_path, monkeypatch, [(7, {'tool': 'Read', 'input': {}})])
    order = []
    m._tail = lambda e, p: order.append('tail')
    m._do = lambda command, **kw: (order.append(command.__name__),
                                   {'decision': 'allow', 'reason': 'ok'})[1]
    m._hooks(e, _proc(m, e), disarmed=False)
    assert order == ['tail', 'serve_hook'], 'the read comes first, then the answer'


# ---------- the restart (manager.py:889-1160) -------------------------------

def _line(**over):
    xid = over.pop('execution_id', None) or ids.new_id('execution')
    d = {'execution_id': xid, 'pid': 4242, 'create_time': 7.5, 'process_seq': 1}
    d.update(over)
    return d


def test_a_live_process_this_core_cannot_account_for_is_killed_by_its_own_identity(monkeypatch):
    # manager.py:983-996: a process that is still running but has no row here (or a
    # harness this Core does not register) is ours by its recorded identity alone,
    # and is killed by it at once rather than left running with a live token; its
    # end line is written so no later boot probes it again.
    m = _mgr(alive=True, kill_identity=True, unended=[_line()])
    _rows(monkeypatch)                        # no execution row for it
    assert m._adopt_orphans([]) is None
    assert [k[0] for k in m.node.kills] == ['identity'], 'killed by its identity'
    assert m.node.kills[0][1].pid == 4242 and m.node.kills[0][1].create_time == 7.5
    assert [x for x in m.node.log if x[0] == 'ended'][0][2] is None, 'no exit is claimed'
    assert m._procs == {}, 'it is never taken in as live work'
    m = _mgr(alive=True, kill_identity=False, unended=[_line()])
    m._adopt_orphans([])
    assert [x for x in m.node.log if x[0] == 'ended'] == [], 'no kill, no end line'


def test_a_process_that_is_not_running_is_left_to_the_compaction_untouched():
    # manager.py:980-981 (`if not self.node.alive(handle): return False`): a line
    # whose process is gone asks nothing of the node - no kill, no end, no adoption.
    m = _mgr(alive=False, kill_identity=True, unended=[_line()])
    assert m._adopt_orphans([]) is None
    assert m.node.kills == [] and [x for x in m.node.log if x[0] == 'ended'] == []
    assert m._procs == {}


def test_one_odd_registry_line_never_keeps_the_core_from_coming_up(monkeypatch):
    # manager.py:898-909: a line already held is not probed again, a line that does
    # not parse names no process and is skipped with the boot still succeeding, and
    # a line that fails is RETURNED for boot to raise after its sweeps.
    held = _e()
    _rows(monkeypatch)                        # no row for anything
    m = _mgr(alive=True, kill_identity=True,
             unended=[_line(execution_id=held.id), {'execution_id': 'exe_broken'}])
    assert m._adopt_orphans([held]) is None, 'one odd line does not fail the boot'
    assert m.node.kills == [], 'a line already held is not probed again'
    m = _mgr(alive=True, kill_identity=True, unended=[_line()])
    boom = OSError('the registry could not be read')

    def _explode(line):
        raise boom
    m._adopt_orphan = _explode
    assert m._adopt_orphans([]) is boom, 'returned, never raised here'


def test_a_process_of_another_generation_is_never_taken_for_this_one():
    # manager.py:959 (`seq == e.process_seq or e.state == 'INTENT'`): a process
    # recorded under a generation the row no longer names is not a handle, so the
    # pass must not adopt a stale process as the current one.
    m = _mgr(alive=True)
    m._adopt = lambda *a: m.calls.append(('adopt', {}))
    m._collect_gone = lambda e, a, h: m.calls.append(('collect_gone', {})) or True
    e = _e(state='RUNNING', process_seq=3)
    m.node.answers['files'] = ({'process_seq': 3}, {'pid': 4242, 'create_time': 7.5,
                                                    'process_seq': 2}, False)
    assert m._reconcile_one(e, False) is True
    assert _names(m) == ['lost'], 'tombstoned and lost, never adopted'
    assert m.node.kills == []
    assert _kw(m, 'lost')[0]['reason'] == 'Core restarted; no process was recorded'
    e = _e(state='RUNNING', process_seq=2)
    m = _mgr(alive=True)
    m._adopt = lambda *a: m.calls.append(('adopt', {}))
    m.node.answers['files'] = ({'process_seq': 2}, {'pid': 4242, 'create_time': 7.5,
                                                    'process_seq': 2}, False)
    assert m._reconcile_one(e, False) is True
    assert _names(m) == ['adopt'], 'the same generation is the process of this row'


def test_the_stop_kills_what_the_restart_found_alive(monkeypatch):
    # manager.py:963-965 (`if alive and disarmed`): a process the restarted pass
    # finds running under the emergency stop is killed there and then, and is not
    # adopted as live work afterwards.
    m = _mgr(alive=True)
    m._adopt = lambda *a: m.calls.append(('adopt', {}))
    m._collect_gone = lambda e, a, h: m.calls.append(('collect_gone', {})) or True
    m.node.answers['files'] = ({'process_seq': 1}, {'pid': 4242, 'create_time': 7.5,
                                                    'process_seq': 1}, False)
    m.registry = SimpleNamespace(get=lambda hid: 'the-adapter')
    assert m._reconcile_one(_e(state='RUNNING'), True) is True
    assert m.node.kills == [('the-adapter', m.node.kills[0][1])]
    assert _names(m) == ['collect_gone'], 'dead work is collected, not adopted'


def test_an_intent_that_started_no_process_and_one_begun_but_unconfirmed_end_differently():
    # manager.py:969-976 (`if marker is None or (ended and pid is None)`, then
    # `if pid is None`): no marker is a refusal charged to the binding (the stop's,
    # when the stop is why), a marker with no confirmation is a LOST, tombstoned.
    m = _mgr(alive=False)
    m.node.answers['files'] = (None, None, False)
    assert m._reconcile_one(_e(state='INTENT'), False) is True
    assert _kw(m, 'refuse')[0]['reason'] == 'no process was started'
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'binding'
    m = _mgr(alive=False)
    m.node.answers['files'] = ({'process_seq': 1}, None, True)
    assert m._reconcile_one(_e(state='INTENT'), True) is True
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'disarmed'
    m = _mgr(alive=False)
    m.node.answers['files'] = ({'process_seq': 1}, None, False)
    tombstoned = []
    e = _e(state='INTENT')
    m._tombstone = lambda x: tombstoned.append(x.id)
    assert m._reconcile_one(e, False) is True
    assert tombstoned == [e.id]
    assert _kw(m, 'lost')[0]['reason'] == 'a spawn was begun and never confirmed'


def test_what_the_restart_takes_in_keeps_its_own_offsets_and_its_recorded_basis():
    # manager.py:1138-1142 (`_adopt`): the pass's own book for an adopted process is
    # built from the ROW, and the context basis the execution had recorded is carried
    # into it - losing it silently restarts the pressure accounting from nothing.
    m = _mgr()
    e = _e(process_seq=2, stream_offset=17, usage={'in': 3},
           context={'signal': 'precompact'})
    m._adopt(e, 'the-adapter', SimpleNamespace(pid=4242, create_time=7.5))
    p = m._procs[e.id]
    assert (p['adapter'], p['seq'], p['offset'], p['usage']) == ('the-adapter', 2, 17,
                                                                {'in': 3})
    assert p['context'] == {'signal': 'precompact'}
    assert p['since'] is None and p['flagged'] is False and p['decisions'] == []
    assert _kw(m, 'adopted')[0] == {'execution_id': e.id, 'pid': 4242, 'offset': 17}


def test_a_hand_off_chain_is_counted_whole_and_its_predecessor_checkpoint_is_prepended(
        monkeypatch):
    # manager.py:447 (`n < 1000` in the walk) and 451-453: the count is the number of
    # executions this one continues, and the prompt is the objective plus the
    # checkpoint of the execution handed off from.
    m = _mgr()
    root, middle = _e(), _e()
    middle = _e(handoff_from=root.id)
    e = _e(handoff_from=middle.id)
    got = {root.id: root, middle.id: middle}

    def _get(r, kind, id_):
        return SimpleNamespace(entity=got[id_]) if id_ in got else None
    monkeypatch.setattr(M.rows, 'get', _get)
    monkeypatch.setattr(CP, 'of_execution', lambda r, xid: {'k': 'cp'})
    monkeypatch.setattr(CP, 'text_of', lambda cp, homes: 'the checkpoint')
    monkeypatch.setattr(M.resources, 'homes', lambda r, reg, live: 'the homes')
    assert m._continuation(e, 'the aim\n\nT\n') == ('the aim\n\nT\n\nthe checkpoint\n', 2)


def _raiser(exc):
    def _go(*args, **kw):
        raise exc
    return _go


def test_a_process_that_could_not_be_written_is_charged_and_one_could_not_start_is_not(
        monkeypatch):
    # manager.py:352-370: a spawn that could not write the execution's OWN files is
    # charged like a workspace that cannot be made (`workspace`), a spawn that merely
    # could not start is uncharged (`spawn`: infrastructure, not the task failing)
    # and one already spawned is a `binding` failure. All three let go of the
    # isolation, and none of them records a process.
    for exc, why in ((base.SpawnWriteFailed('the files could not be written'), 'workspace'),
                     (base.SpawnFailed('the harness is not there'), 'spawn'),
                     (base.AlreadySpawned('a process is already recorded'), 'binding')):
        m = _spawn_rig(monkeypatch, disarms=(False, False))
        m.node.answers['spawn'] = _raiser(exc)
        m._release_isolation = lambda x, _m=m: _m.calls.append(('release_isolation', {}))
        assert m._spawn(_e(), _mission()) is True
        assert _names(m) == ['prepare_process', 'refuse', 'release_isolation'], why
        assert _kw(m, 'refuse')[0]['stop_reason'] == why, why
        assert _kw(m, 'refuse')[0]['reason'].startswith('the process did not start: '), why
        assert 'record_process' not in _names(m), why


def test_settings_sources_that_cannot_be_read_start_nothing_and_are_charged(monkeypatch):
    # manager.py:320-331: an inventory that cannot be taken revokes the grant, is
    # charged to the `workspace` (P11 note 11: an uncharged end would re-dispatch the
    # task on every tick, forever) and the child is never asked for.
    m = _spawn_rig(monkeypatch, disarms=(False, False))
    m.registry = SimpleNamespace(get=lambda hid: SimpleNamespace(
        inventory=_raiser(OSError('the settings sources are unreadable'))))
    assert m._spawn(_e(), _mission()) is True
    assert _names(m) == ['refuse'], 'nothing was prepared and nothing was spawned'
    assert _kw(m, 'refuse')[0]['stop_reason'] == 'workspace'
    assert 'the settings sources could not be inventoried: OSError' in \
        _kw(m, 'refuse')[0]['reason']
    assert [x[0] for x in m.node.log] == ['terms', 'workspace', 'refuse']


def test_an_import_names_the_project_and_only_the_workdirs_core_recorded(monkeypatch):
    # manager.py:757-763 (`_store_inputs`, K1): the store is named by the mission's
    # project and the workdirs are Core's own records with the absent ones dropped,
    # so no store call may name a workspace of its own.
    m = _mgr()
    _rows(monkeypatch, Mission=SimpleNamespace(project_id='project-1'),
          Execution=[SimpleNamespace(workdir='/w/one'), SimpleNamespace(workdir=None)])
    assert m._store_inputs(_e()) == ('project-1', ['/w/one'])
