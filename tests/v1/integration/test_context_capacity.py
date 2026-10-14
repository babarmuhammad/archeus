"""ADR-0047 (D-26, P21), the governed half: pressure measured with its basis on
real processes (the fake harness), the PreCompact signal, the window of the
execution's own account, the no-progress guard over whole continuation chains,
its charged end and the ordinary retry and replan after it, live work and the
`why` and `status` answers — all from Core's records (testing-strategy §10).

Every git workdir here is a temporary repository; no real project is touched,
and the test of the chain checks the repository holds nothing but what the
agent wrote."""

import json
import os
import subprocess

import pytest

from archeus.api import schemas
from archeus.core.application import commands, conversation as C, executions as X, grammar
from archeus.core.application import live, world
from archeus.core.domain import entities
from archeus.core.execution import pressure as P
from archeus.harnesses import base
from archeus.harnesses.fake import FakeHarness
from archeus.infra.paths import ExecPaths

from v1.integration.test_execution import DONE, Rig, ended
from v1.integration.test_policy import AUTO, task

USAGE = lambda n, **kw: dict({'emit': {'type': 'usage', 'usage': {'input_tokens': n}}}, **kw)  # noqa: E731
READ = lambda **kw: dict({'emit': {'type': 'tool', 'name': 'Read',  # noqa: E731
                                   'input': {'file_path': 'a.txt'}}}, **kw)


def WRITE(content, **kw):
    return dict({'emit': {'type': 'tool', 'name': 'Write',
                          'input': {'file_path': 'a.txt', 'content': content}}}, **kw)


@pytest.fixture
def x(db):
    rig = Rig(db)
    yield rig
    rig.cleanup()


def _execs(x, mid):
    return sorted(x.all(entities.Execution, mission_id=mid), key=lambda e: e.attempt)


def _asked(x, eid):
    return [why for _f, to, why in _transitions(x, eid) if to == 'HANDING_OFF']


def _transitions(x, eid):
    with x.db.read() as r:
        return live.transitions(r, eid)


# ── CX-1, CX-2: the threshold is p12 D20's ──────────────────────────────────

def test_cx1_below_the_threshold_never_hands_off(x):
    x.scenarios['t1'] = [USAGE(148000), READ(), DONE]          # 0.74 of the fake's 200,000
    mid = x.ready(task('t1', 'write_repo', 'read', min_model_tier='large'))
    e = x.drive(mid, lambda: x.exe(mission_id=mid))
    x.drive(mid, ended(x, e.id))
    e = x.state(e.id)
    assert e.state == 'ENDED_OK' and e.stop_reason is None
    assert e.pressure == 0.74 and P.view(e)['quality'] in ('reported', 'stale')


def test_cx2_at_the_threshold_the_report_hands_off_with_its_basis(x):
    x.scenarios['t1'] = [USAGE(152000, attempt=1), READ(attempt=1), DONE]   # 0.76
    mid = x.ready(task('t1', 'write_repo', 'read', min_model_tier='large'))
    first = x.drive(mid, lambda: next((e for e in _execs(x, mid) if e.state == 'ENDED_HANDOFF'),
                                      None))
    assert (first.stop_reason, first.charged, first.pressure) == ('pressure', False, 0.76)
    assert first.context['window_source'] == 'offer' and first.context['used_tokens'] == 152000
    (why,) = _asked(x, first.id)
    assert why == ('context pressure 0.76 reached 0.75: the harness reported 152,000 of '
                   '200,000 tokens; window from the offer')


def test_an_execution_with_no_model_chosen_is_estimated(x):
    x.scenarios['t1'] = [USAGE(160000, attempt=1), READ(attempt=1), DONE]
    mid = x.ready(task('t1', 'write_repo', 'read'))           # no tier: no model routed
    first = x.drive(mid, lambda: next((e for e in _execs(x, mid) if e.state == 'ENDED_HANDOFF'),
                                      None))
    assert P.view(first)['window_source'] == 'harness_smallest'
    assert 'window estimated' in _asked(x, first.id)[0]


# ── PreCompact: signalled, never a usage report ─────────────────────────────

def _precompact_when_running(x, mid):
    e = x.drive(mid, lambda: next((e for e in _execs(x, mid) if e.state == 'RUNNING'), None))
    with open(os.path.join(ExecPaths(e.id).dir, 'precompact.json'), 'w') as f:
        json.dump({'at': 1}, f)
    return e


def test_precompact_is_the_signalled_quality_with_the_policy_stand_in(x):
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 3.0}, READ(), DONE]
    mid = x.ready(task('t1', 'write_repo', 'read', min_model_tier='large'))
    e = _precompact_when_running(x, mid)
    x.drive(mid, lambda: x.state(e.id).state == 'ENDED_HANDOFF')
    e = x.state(e.id)
    v = P.view(e)
    assert (e.stop_reason, e.pressure) == ('pressure', 0.9)
    assert (v['quality'], v['signal'], v['usage_source']) == ('signalled', 'precompact', 'none')
    assert (v['used_tokens'], v['window'], v['remaining']) == (None, None, None)
    assert isinstance(v['signal_seq'], int)
    assert 'PreCompact' in _asked(x, e.id)[0] and 'by policy' in _asked(x, e.id)[0]


def test_precompact_after_a_report_keeps_the_report(x):
    x.scenarios['t1'] = [USAGE(50000), {'sleep': 3.0}, READ(), DONE]
    mid = x.ready(task('t1', 'write_repo', 'read', min_model_tier='large'))
    e = x.drive(mid, lambda: next((e for e in _execs(x, mid) if e.state == 'RUNNING'
                                   and (e.context or {}).get('used_tokens')), None))
    with open(os.path.join(ExecPaths(e.id).dir, 'precompact.json'), 'w') as f:
        json.dump({'at': 1}, f)
    # the agent is asleep: no output arrives, and the signal is recorded all the same
    x.drive(mid, lambda: x.state(e.id).state == 'HANDING_OFF')
    assert P.view(x.state(e.id))['quality'] == 'signalled'
    x.drive(mid, lambda: x.state(e.id).state == 'ENDED_HANDOFF')
    v = P.view(x.state(e.id))
    assert (v['quality'], v['used_tokens'], v['window'], v['remaining']) == (
        'signalled', 50000, 200000, None)


# ── the window is the execution's own account's (C-22) ──────────────────────

def homes():
    """The fake, whose offers differ by account home as pi's do. Patched on the
    instance: the fake is exempt from provider terms by class identity."""
    h = FakeHarness()

    def capabilities(account):
        big = account is not None and account.home_ref == 'big-home'
        return base.Capabilities(h._caps, h._enforcement,
                                 (base.ModelInfo('fake-model', 'large',
                                                 1000000 if big else 200000),),
                                 efforts=h._efforts)
    h.capabilities = capabilities
    return h


def test_the_window_is_the_offer_of_the_executions_own_account(db):
    x = Rig(db, adapters=[homes()])
    try:
        acc = x.account('Big', home_ref='big-home')
        x.scenarios['t1'] = [USAGE(300000), READ(), DONE]   # 0.3 of its own 1,000,000
        mid = x.ready(task('t1', 'write_repo', 'read', min_model_tier='large'))
        e = x.drive(mid, lambda: x.exe(mission_id=mid))
        x.drive(mid, ended(x, e.id))
        e = x.state(e.id)
        assert e.account_id == acc and e.state == 'ENDED_OK'
        assert (e.context['window'], e.context['window_source'], e.pressure) == (
            1000000, 'offer', 0.3)
    finally:
        x.cleanup()


# ── the guard over a whole chain (CX-3) ─────────────────────────────────────

def _git_project(x, tmp_path):
    root = str(tmp_path / 'proj')
    os.makedirs(root)
    g = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run(['git', 'init', '-q', root], check=True)
    with open(os.path.join(root, 'README'), 'w') as f:
        f.write('x\n')
    subprocess.run(g + ['add', 'README'], cwd=root, check=True)
    subprocess.run(g + ['commit', '-qm', 'init'], cwd=root, check=True)
    pid = x.do(world.create_project, who=x.user, name='P', root_paths=[root])['project']['id']
    return root, pid


def _ready_in(x, project_id, *tasks_):
    mid = x.do(commands.create_mission, who=x.user, title='M', objective='o',
               project_id=project_id, success_criteria=[AUTO])['id']
    for trig in ('start', 'understood'):
        x.do(x.missions.fire, mission_id=mid, trigger=trig, reason='test')
    x.do(x.missions.context_ready, mission_id=mid)
    out = x.propose(mid, *tasks_)
    assert out['mission']['state'] == 'APPROVED', out
    x.do(x.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
    x.do(x.work.ready_tasks, mission_id=mid)
    return mid


def _link(content, attempt):
    return [WRITE(content, attempt=attempt), USAGE(190000, attempt=attempt),
            READ(attempt=attempt)]


def test_cx3_a_chain_that_returns_to_an_earlier_state_ends_charged(x, tmp_path):
    root, pid = _git_project(x, tmp_path)
    spy, real = [], x.router.route

    def counting(*a, **kw):
        spy.append(kw.get('task').id if kw.get('task') is not None else None)
        return real(*a, **kw)
    x.router.route = counting
    # A, then B (progress), then A again: no progress over the chain
    x.scenarios['t1'] = _link('1', 1) + _link('2', 2) + _link('1', 3) + [dict(DONE, attempt=4)]
    mid = _ready_in(x, pid, task('t1', 'write_repo', 'read'))
    retry = x.drive(mid, lambda: next((e for e in _execs(x, mid) if e.attempt == 4), None),
                    timeout=60)
    x.drive(mid, ended(x, retry.id), timeout=30)
    e1, e2, e3, e4 = _execs(x, mid)[:4]
    assert (e1.handoff_from, e2.handoff_from, e3.handoff_from) == (None, e1.id, e2.id)
    assert e1.end_state_digest and e2.end_state_digest not in (None, e1.end_state_digest)
    assert e3.end_state_digest == e1.end_state_digest            # A -> B -> A
    assert (e1.state, e1.charged, e2.state, e2.charged) == (
        'ENDED_HANDOFF', False, 'ENDED_HANDOFF', False)
    assert (e3.state, e3.exit_reason, e3.stop_reason, e3.charged) == (
        'ENDED_HANDOFF', 'handoff', 'pressure', True)
    # no continuation of the guarded end; the retry is a fresh execution
    assert not [e for e in _execs(x, mid) if e.handoff_from == e3.id]
    assert (e4.handoff_from, e4.attempt, x.state(e4.id).state) == (None, 4, 'ENDED_OK')
    ends = [why for _f, to, why in _transitions(x, e3.id) if to == 'ENDED_HANDOFF']
    assert ends and ends[0].startswith('context insufficient') and 'charged' in ends[0]
    (cp,) = x.all(entities.Checkpoint, execution_id=e3.id)
    assert any(p.startswith('context insufficient') for p in cp.open_problems)
    task_moves = [(ev['payload']['from'], ev['payload']['to'], ev['payload']['reason'])
                  for ev in x.events('task.state_changed') if ev['subject']['id'] == e3.task_id]
    assert any(to == 'READY' and 'context insufficient' in why and 'retrying' in why
               for _f, to, why in task_moves)
    # every link was authorised and routed afresh: one route per execution
    t_id = e1.task_id
    assert spy.count(t_id) >= 4
    assert len({e.route_decision_id for e in (e1, e2, e3, e4)}) == 4
    # the repository holds only what the agent wrote: no Archeus file in it
    st = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root,
                        capture_output=True, text=True, check=True).stdout.split()
    assert set(st) <= {'??', 'a.txt'}, st


def test_a_chain_that_keeps_progressing_has_no_count_cap(x, tmp_path):
    root, pid = _git_project(x, tmp_path)
    x.scenarios['t1'] = (_link('1', 1) + _link('2', 2) + _link('3', 3) + _link('4', 4)
                         + [dict(DONE, attempt=5)])
    mid = _ready_in(x, pid, task('t1', 'write_repo', 'read'))
    last = x.drive(mid, lambda: next((e for e in _execs(x, mid) if e.attempt == 5), None),
                   timeout=90)
    x.drive(mid, ended(x, last.id), timeout=30)
    es = _execs(x, mid)
    assert [e.handoff_from for e in es[1:5]] == [es[0].id, es[1].id, es[2].id, es[3].id]
    assert not any(e.charged for e in es[:4])                   # progress: never charged
    with x.db.read() as r:
        assert live.handoff_of(r, es[4])['count'] == 4


def test_no_git_workdir_gets_one_pressure_continuation_per_attempt(x):
    x.scenarios['t1'] = ([USAGE(190000, attempt=1), READ(attempt=1)]
                         + [USAGE(190000, attempt=2), READ(attempt=2)] + [dict(DONE, attempt=3)])
    mid = x.ready(task('t1', 'write_repo', 'read'))
    third = x.drive(mid, lambda: next((e for e in _execs(x, mid) if e.attempt == 3), None))
    x.drive(mid, ended(x, third.id))
    e1, e2, e3 = _execs(x, mid)[:3]
    assert e1.end_state_digest is None and e2.end_state_digest is None   # not measurable
    assert (e2.handoff_from, e2.state, e2.charged) == (e1.id, 'ENDED_HANDOFF', True)
    assert e3.handoff_from is None and x.state(e3.id).state == 'ENDED_OK'
    assert 'could not be measured' in [w for _f, to, w in _transitions(x, e2.id)
                                       if to == 'ENDED_HANDOFF'][0]


def test_cx18_the_retry_is_bounded_and_the_task_fails_context_insufficient(x):
    x.scenarios['t1'] = [USAGE(190000), READ()]              # every link hands off again
    mid = x.ready(task('t1', 'write_repo', 'read'))
    t = x.task_of(mid)
    x.drive(mid, lambda: x.task_of(mid).state == 'FAILED', timeout=60)
    for _ in range(40):                                       # nothing more is created
        x.engine.step(mid)
        x.manager.tick()
    es = _execs(x, mid)
    assert [(e.handoff_from is not None, e.charged) for e in es] == [
        (False, False), (True, True), (False, False), (True, True)]
    assert x.task_of(mid).failure_class == 'context_insufficient'
    assert sum(1 for e in es if e.charged) == t.max_attempts     # the attempt budget, spent


# ── live work, why and status (CX-14) ───────────────────────────────────────

def test_live_work_carries_the_recorded_context(x):
    x.scenarios['t1'] = [USAGE(100000), {'sleep': 30}]
    mid = x.ready(task('t1', 'write_repo', 'read', min_model_tier='large'))
    x.drive(mid, lambda: next((e for e in _execs(x, mid)
                               if (e.context or {}).get('used_tokens') == 100000), None))
    with x.db.read() as r:
        (item,) = live.live_work(r)
    schemas.validate(item, schemas.TYPES['LiveItem'])
    c = item['context']
    assert (item['kind'], item['state'], item['task_key']) == ('execution', 'RUNNING', 't1')
    assert (c['used_tokens'], c['window'], c['remaining'], c['pressure']) == (
        100000, 200000, 100000, 0.5)
    assert c['quality'] in ('reported', 'stale') and item['handoff']['count'] == 0
    with x.db.read() as r:
        assert live.live_work(r, project_id='prj_none') == []


def test_why_and_status_answer_from_the_record(x):
    x.scenarios['t1'] = ([USAGE(190000, attempt=1), READ(attempt=1)]
                         + [USAGE(190000, attempt=2), READ(attempt=2)]
                         + [dict({'sleep': 30}, attempt=3)])
    mid = x.ready(task('t1', 'write_repo', 'read'))
    third = x.drive(mid, lambda: next((e for e in _execs(x, mid) if e.attempt == 3
                                       and e.state == 'RUNNING'), None))
    e2 = _execs(x, mid)[1]
    with x.db.read() as r:
        assert grammar.resolve(r, 'why %s' % e2.id).target == {'kind': 'execution', 'id': e2.id}
    text, rd = x.do(lambda tx, actor: C._why(tx, {'kind': 'execution', 'id': e2.id}))
    assert rd == e2.route_decision_id                  # the card the reply carries (P19 B10)
    assert 'context insufficient' in text and '(charged)' in text
    assert 'No continuation was created' in text and 'checkpoint' in text
    assert 'It continues execution %s in a fresh session' % _execs(x, mid)[0].id in text
    st, _links = x.do(lambda tx, actor: C._status(tx, None))
    assert 'Running now: t1 attempt 3 (RUNNING, context unavailable)' in st
    with x.db.read() as r:
        assert X.view(r, e2.id)['why'] == text


def test_a_handoff_in_one_mission_disturbs_no_other(x):
    x.scenarios['t1'] = [USAGE(190000, attempt=1), READ(attempt=1), DONE]
    x.scenarios['t2'] = [{'sleep': 30}]
    a = x.ready(task('t1', 'write_repo', 'read'), title='A')
    b = x.ready(task('t2', 'write_repo', 'read'), title='B')
    other = x.drive(b, lambda: next((e for e in _execs(x, b) if e.state == 'RUNNING'), None))
    x.drive(a, lambda: any(e.state == 'ENDED_HANDOFF' for e in _execs(x, a)))
    assert x.state(other.id).state == 'RUNNING' and x.state(other.id).stop_reason is None

