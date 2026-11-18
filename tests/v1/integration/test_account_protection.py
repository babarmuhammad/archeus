"""AP-1 on the real database (ADR-0041 §1, §3; ADR-0048; testing-strategy §8:
AP-1, G9, G10, AP-UK, AP-CC, AP-ID, AP-RT, AP-LG, AP-WB, AP-RB, CX-7): the
consumption classes through dispatch, retry, continuation and own calls; one
account key; the ledger that never turns a missing figure into 0; live work
counted for concurrency, inside the writer; and nothing written outside
ARCHEUS_HOME. Fake adapters and temporary directories only."""

import ast
import glob
import hashlib
import os
import shutil

import pytest

from archeus.core import calls as OC
from archeus.core import ports
from archeus.core.application import calls as C, resources
from archeus.core.application.authorization import NotPermitted
from archeus.core.domain import entities
from archeus.core.routing import router as R
from archeus.core.verification import reviewer
from archeus.harnesses import base
from archeus.harnesses.fake import FakeCaller, FakeHarness
from archeus.infra.db import Database, migrate
from archeus.infra.db import backup as B

from v1.integration.test_execution import DONE, PRESSURE, Rig as ExecRig, _running, ended
from v1.integration.test_policy import task
from v1.integration.test_routing import Rig

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


@pytest.fixture
def r(db):
    return Rig(db)


def policy(r, acc, measures=('tokens',), **fields):
    return r.do(resources.set_resource_policy, who=r.user, account_id=acc,
                usage_measures=measures, **fields)


def own(r, *callers, timeout_s=600):
    return OC.OwnCalls(r.db, actor=r.system, callers=list(callers) or [FakeCaller(
        'fake', replies={'*': [{'parsed': {'ok': True}}]})], usage=r.feed, timeout_s=timeout_s,
        preference=ports.FixedOwnCallPreference())


def ask(o, **kw):
    return o.run(**dict(dict(purpose='brain', source={'kind': 'mission', 'id': 'msn_x'},
                             workspace_id='ws_global', project_id=None, prompt='p',
                             schema=None, check=lambda p: [], workdir='.'), **kw))


def cand(rd, resource):
    return next(c for c in rd.candidates if c['resource'] == resource)


def snapshot_call(r, callers, now=None):
    with r.db.read() as conn:
        return resources.call_snapshot(
            conn, callers=callers, feed=r.feed, preference=ports.OwnCallPreference(),
            purpose='brain', schema=None, project_id=None, min_tier=None, now=now,
            max_run_s=1200)


def ledger(r, acc, now=None):
    import time
    now = time.time() if now is None else now
    with r.db.read() as conn:
        return resources.ledger_totals(conn, acc, resources._iso(now)[:10], now)


# ── the policy write (ADR-0041 §1, §3) ──────────────────────────────────────

def test_the_class_is_set_by_a_user_device_and_a_budget_only_on_a_reported_measure(r):
    acc = r.account('A')
    got = policy(r, acc, consumption='last_resort', budgets={'tokens_per_day': 10})
    assert (got['consumption'], got['budgets']) == ('last_resort', {'tokens_per_day': 10})
    with pytest.raises(NotPermitted):
        r.do(resources.set_resource_policy, who=r.brain, account_id=acc,
             consumption='normal', usage_measures=('tokens',))
    with pytest.raises(ValueError, match='cost measure'):
        policy(r, acc, budgets={'cost_per_day': 1})
    with pytest.raises(ValueError, match='tokens measure'):
        policy(r, acc, measures=(), budgets={'tokens_per_day': 1})
    with pytest.raises(ValueError, match='tokens measure'):
        r.do(resources.set_resource_policy, who=r.user, account_id=acc,
             budgets={'tokens_per_day': 1})            # nobody said what it reports
    assert policy(r, acc, measures=(), budgets={'concurrency': 2})['budgets'] == {
        'concurrency': 2}                              # Core counts it itself
    with pytest.raises(ValueError):
        policy(r, acc, consumption='sometimes')


# ── the partition and the lift, through dispatch (AP-1, G9) ─────────────────

def test_a_last_resort_account_waits_while_a_normal_one_can_run(r):
    a = r.account('A', priority=1)
    b = r.account('B', priority=2)
    policy(r, a, consumption='last_resort')
    mid = r.ready()
    r.dispatch(mid)
    (rd,) = r.rds(mission_id=mid)
    assert (rd.result, rd.account_id) == ('selected', b)
    assert (cand(rd, a)['eliminated_at_step'], cand(rd, a)['reason']) == (
        'partition', 'a last-resort account, not used while a normal one can run')
    assert 'a last-resort account' in rd.explanation


def test_explicit_only_is_used_only_when_a_user_device_names_it_for_that_mission(r):
    c = r.account('C')
    policy(r, c, consumption='explicit_only')
    m1 = r.ready(title='one')
    r.dispatch(m1)
    (rd,) = r.rds(mission_id=m1)
    assert rd.result == 'blocked' and cand(rd, c)['eliminated_at_step'] == 'restriction'
    with pytest.raises(NotPermitted):                   # a brain reading never lifts a class
        r.do(resources.set_mission_resources, who=r.brain, mission_id=m1,
             preferences={'preferred_accounts': [c]})
    m2 = r.ready(title='two')
    r.do(resources.set_mission_resources, who=r.user, mission_id=m2,
         preferences={'preferred_accounts': [c]})
    r.dispatch(m2)
    (rd2,) = r.rds(mission_id=m2)
    assert (rd2.result, rd2.account_id) == ('selected', c)
    # the lift is that mission's: another mission is still refused
    m3 = r.ready(title='three')
    r.dispatch(m3)
    assert r.rds(mission_id=m3)[0].result == 'blocked'


# ── one account key (AP-ID, ADR-0048 D-25.2) ────────────────────────────────

def test_one_home_is_one_account_and_its_home_never_changes(r, tmp_path):
    home = str(tmp_path / 'Claude')
    a = r.account('A', home_ref=home)
    with pytest.raises(ValueError, match='already registered as account %s' % a):
        # normcase folds case only where the filesystem does (Windows)
        again = 'claude' if os.name == 'nt' else 'Claude'
        r.account('again', home_ref=os.path.join(str(tmp_path), '.', again) + os.sep)
    r.account('other harness', harness_id='pi', home_ref=home)   # keys never cross harnesses
    with pytest.raises(ValueError, match=r"frozen once recorded: \['home_ref'\]"):
        r.do(lambda tx, actor: tx.update(entities.Account, a, {'home_ref': str(tmp_path)},
                                         actor=actor), who=r.user)
    assert r.one(entities.Account, id=a).home_key == base.canonical_home(home)


def test_a_task_and_an_own_call_name_the_unregistered_default_alike(r):
    """The same real account has one key in both snapshots, so a review routed
    away from the accounts that did the work really is (P13 §14.3)."""
    with r.db.read() as conn:
        _req, snap_t, _ = resources.task_snapshot(
            conn, adapters=[FakeHarness()], feed=r.feed, mission=_mission(), plan=_ns(id='p'),
            task=_task(), decision=_ns(id='pdc_x', outcome='covered', items=()), now=0)
    req_c, snap_c, _ = snapshot_call(r, [FakeCaller('fake')])
    (t,) = [a['ref'] for a in snap_t['accounts'] if not a['registered']]
    (c,) = [a['ref'] for a in snap_c['accounts'] if not a['registered']]
    assert t == c == 'fake:fake'
    away = dict(req_c, forbidden=reviewer.forbidden([('fake', t, None)]))
    d = R.route(away, snap_c)
    assert d['result'] != 'selected'
    assert steps_of(d) == {'fake': 'restriction'}


def test_claude_code_names_its_default_account_the_same_for_tasks_and_own_calls(
        monkeypatch, tmp_path):
    from archeus.harnesses import calls as real
    from archeus.harnesses.claude_code.adapter import ClaudeCodeAdapter
    from claude_sessions import config
    monkeypatch.setattr(config, 'config_dir', str(tmp_path / 'Dot-Claude'))
    e, o = ClaudeCodeAdapter().default_account(), real.ClaudeCodeCaller().default_account()
    assert e == o
    assert e.account_id == 'claude_code:%s' % base.canonical_home(str(tmp_path / 'Dot-Claude'))
    # the key is canonical; the home stays the real path the process runs on
    assert e.home_ref == os.path.abspath(str(tmp_path / 'Dot-Claude'))


def test_the_default_account_exists_only_until_the_harness_has_a_registered_one(r):
    """Cases 16 and 17."""
    _req, before, _ = snapshot_call(r, [FakeCaller('fake')])
    assert [(a['registered'], a['ref']) for a in before['accounts']] == [(False, 'fake:fake')]
    acc = r.account('First')
    _req, after, _ = snapshot_call(r, [FakeCaller('fake')])
    assert [(a['registered'], a['id']) for a in after['accounts']] == [(True, acc)]


def test_no_v1_module_chooses_an_account_outside_the_router():
    """AP-RT: legacy rotation is the legacy app's (ADR-0048 D-25.5); V1 never
    imports it, and no adapter takes a rotation answer."""
    hits = []
    for path in glob.glob(os.path.join(ROOT, 'archeus', '**', '*.py'), recursive=True):
        tree = ast.parse(open(path, encoding='utf-8').read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [(node.module or '') + '.' + a.name for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            hits += ['%s: %s' % (os.path.relpath(path, ROOT), n) for n in names
                     if n.split('.')[-1] == 'rotate' or '.rotate.' in n]
            if isinstance(node, ast.FunctionDef) and node.name == 'account' and any(
                    a.arg == 'rotation' for a in node.args.kwonlyargs):
                hits.append('%s: account(rotation)' % os.path.relpath(path, ROOT))
    assert hits == []


# ── the ledger: never 0 for what was not reported (AP-UK) ───────────────────

def test_an_execution_that_ran_always_leaves_a_row_with_its_basis(r):
    acc = r.account('A')
    rows_ = {}
    for usage, total, key in (({'input_tokens': 5, 'output_tokens': 2}, True, 'total'),
                              ({'input_tokens': 5}, False, 'partial'), (None, False, 'none')):
        mid = r.ready(title=key)
        out = r.dispatch(mid)
        r.do(r.work.record_spawn, execution_id=out['execution_id'], pid=1, create_time=1.0)
        r.do(r.work.record_exit, execution_id=out['execution_id'], exit_reason='ok',
             exit_code=0, usage=usage, usage_total=total)
        (rows_[key],) = r.all(entities.UsageLedger, execution_id=out['execution_id'])
    assert (rows_['total'].basis, rows_['total'].tokens_in) == ('reported_total', 5)
    assert (rows_['partial'].basis, rows_['partial'].tokens_out) == ('partial', None)
    assert (rows_['none'].basis, rows_['none'].tokens_in) == ('none', None)
    led = ledger(r, acc)
    assert (led['tokens_today'], led['complete']['tokens']) == (12, False)


def test_an_own_call_leaves_a_row_unless_it_never_ran(r):
    acc = r.account('A')
    ok = ask(own(r))
    failed = ask(own(r, FakeCaller('fake', replies={'*': [{'error': 'failed'}]})))
    missing = ask(own(r, FakeCaller('fake', replies={'*': [{'error': 'unavailable'}]})))
    r.do(C.end_call, who=r.system, route_decision_id=ok.route_decision_id,
         outcome={'state': 'ok'}, usage=ok.usage)
    got = {x.route_decision_id: x for x in r.all(entities.UsageLedger, account_id=acc)}
    assert got[ok.route_decision_id].basis == 'reported_total'
    assert (got[failed.route_decision_id].basis, got[failed.route_decision_id].tokens_in) == (
        'none', None)
    assert missing.route_decision_id not in got      # no binary: nothing ran


def test_a_call_that_ended_with_no_outcome_makes_the_day_unknown_never_zero(r):
    acc = r.account('A')
    policy(r, acc, budgets={'tokens_per_day': 1000})
    req, snap, _ = snapshot_call(r, [FakeCaller('fake')])
    got = r.do(resources.record_call_route, who=r.system, purpose='brain',
               source={'kind': 'mission', 'id': 'msn_x'}, workspace_id='ws_global',
               project_id=None, requirements=dict(req, max_run_s=0), snapshot=snap)
    import time
    led = ledger(r, acc, now=time.time() + 5)            # past its maximum run
    assert (led['running'], led['complete']) == (0, {'tokens': False, 'cost': False})
    with r.db.read() as conn:
        d = R.route(req, resources.refresh_ledgers(conn, snap, time.time() + 5))
    assert cand_d(d, acc)['reason'] == ('budget tokens_per_day cannot be evaluated: usage '
                                        'partly unreported')
    assert got['decision']['result'] == 'selected'


# ── concurrency over live work, inside the writer (AP-CC) ───────────────────

def test_an_own_call_in_flight_holds_the_last_slot_against_a_task(r):
    """Cases 11 and 12."""
    a = r.account('A', priority=1)
    b = r.account('B', priority=2)
    policy(r, a, measures=(), budgets={'concurrency': 1})
    req, snap, _ = snapshot_call(r, [FakeCaller('fake')])
    held = r.do(resources.record_call_route, who=r.system, purpose='planner',
                source={'kind': 'mission', 'id': 'msn_x'}, workspace_id='ws_global',
                project_id=None, requirements=req, snapshot=snap)
    assert held['decision']['account_id'] == a and ledger(r, a)['running'] == 1
    mid = r.ready()
    r.dispatch(mid)
    (rd,) = r.rds(mission_id=mid)
    assert (rd.account_id, cand(rd, a)['reason']) == (b, 'budget reached: concurrency')
    # the outcome releases it, once
    r.do(C.end_call, who=r.system, route_decision_id=held['route_decision_id'],
         outcome={'state': 'ok'})
    with pytest.raises(ValueError, match='already has its outcome'):
        r.do(C.end_call, who=r.system, route_decision_id=held['route_decision_id'],
             outcome={'state': 'ok'})
    assert ledger(r, a)['running'] == 0 and ledger(r, b)['running'] == 1


def test_a_live_task_holds_the_last_slot_against_an_own_call(r):
    a = r.account('A')
    policy(r, a, measures=(), budgets={'concurrency': 1})
    r.dispatch(r.ready())                                # an INTENT execution is live work
    got = ask(own(r))
    assert got.state == 'unavailable'
    assert got.detail == ('budget reached: concurrency; only your approval could use it, which '
                          'an own call never asks')


def test_two_own_calls_cannot_both_take_the_last_slot(r):
    """Case 13: both gathered their snapshot before either recorded; the second
    is decided again inside its own transaction and finds the slot taken."""
    a = r.account('A')
    policy(r, a, measures=(), budgets={'concurrency': 1})
    req, snap, _ = snapshot_call(r, [FakeCaller('fake')])
    kw = dict(purpose='brain', source={'kind': 'mission', 'id': 'msn_x'},
              workspace_id='ws_global', project_id=None, requirements=req, snapshot=snap)
    first = r.do(resources.record_call_route, who=r.system, **kw)
    second = r.do(resources.record_call_route, who=r.system, **kw)
    assert first['decision']['account_id'] == a
    assert second['decision']['result'] != 'selected' and second['decision']['selected'] is None
    rd = r.one(entities.RouteDecision, id=second['route_decision_id'])
    assert R.replay({'requirements': rd.requirements, 'input_snapshot': rd.input_snapshot}
                    ) == second['decision']      # the record still replays


def test_a_failed_or_abandoned_call_releases_its_slot(r):
    """Case 14: an outcome of any kind ends it; one that never gets an outcome
    stops counting after its maximum run."""
    import time
    a = r.account('A')
    policy(r, a, measures=(), budgets={'concurrency': 1})
    failed = ask(own(r, FakeCaller('fake', replies={'*': [{'error': 'timeout'}]})))
    assert failed.state == 'timeout' and ledger(r, a)['running'] == 0
    req, snap, _ = snapshot_call(r, [FakeCaller('fake')])
    r.do(resources.record_call_route, who=r.system, purpose='brain',
         source={'kind': 'mission', 'id': 'msn_x'}, workspace_id='ws_global',
         project_id=None, requirements=dict(req, max_run_s=1), snapshot=snap)
    assert ledger(r, a)['running'] == 1
    assert ledger(r, a, now=time.time() + 5)['running'] == 0


# ── retries and continuations route through the same protection (CX-7) ──────

@pytest.fixture
def x(db):
    from archeus.node.local import LocalNode
    rig = ExecRig(db)
    yield rig
    rig.cleanup()
    LocalNode.clear_estop()


def test_a_continuation_never_goes_back_to_an_account_protected_since(x):
    """Case 10: the hand-off routes again; affinity points at A, and A is now
    last_resort, so the continuation runs on B."""
    a = x.account('A', priority=1)
    b = x.account('B', priority=2)
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 0.8}] + PRESSURE[1:]
    mid = x.ready(task('t1', 'write_repo', 'read'))
    first = _running(x, mid)
    assert first.account_id == a
    policy(x, a, consumption='last_resort')
    nxt = x.drive(mid, lambda: next((e for e in x.all(entities.Execution, mission_id=mid)
                                     if e.handoff_from == first.id), None))
    x.drive(mid, ended(x, nxt.id))
    assert nxt.account_id == b
    rd = x.one(entities.RouteDecision, id=nxt.route_decision_id)
    assert cand(rd, a)['eliminated_at_step'] == 'partition'


def test_a_retry_never_goes_to_an_account_made_explicit_only_since(x):
    a = x.account('A', priority=1)
    b = x.account('B', priority=2)
    x.scenarios['t1'] = [{'emit': {'type': 'working'}, 'attempt': 1},
                         {'sleep': 0.8, 'attempt': 1}, {'exit': 1, 'attempt': 1},
                         dict(DONE, attempt=2)]
    mid = x.ready(task('t1', 'write_repo'))
    first = _running(x, mid)
    assert first.account_id == a
    policy(x, a, consumption='explicit_only')
    retry = x.drive(mid, lambda: next((e for e in x.all(entities.Execution, mission_id=mid)
                                       if e.attempt == 2), None))
    x.drive(mid, ended(x, retry.id))
    assert (retry.handoff_from, retry.account_id) == (None, b)


# ── legacy coexistence and project files (AP-LG, AP-WB) ─────────────────────

def _digest(root):
    out = {}
    for d, _subs, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, root)] = (hashlib.sha256(fh.read()).hexdigest(),
                                                 os.stat(p).st_mtime_ns)
    return out


def test_ap1_writes_nothing_outside_archeus_home(r, tmp_path, monkeypatch):
    """A legacy home (settings, rotation state, a project's .archeus memory) and
    a project's files are byte- and timestamp-identical across routing, own
    calls and the policy writes; legacy rotation is never consulted."""
    from claude_sessions import config, rotate
    from archeus.harnesses import calls as real
    from archeus.infra.paths import archeus_home
    legacy = tmp_path / 'legacy'
    project = tmp_path / 'project'
    (legacy / 'projects').mkdir(parents=True)
    (legacy / 'settings.json').write_text('{"keep": true}', encoding='utf-8')
    (legacy / 'archeus-rotation.json').write_text('{"mode": "auto"}', encoding='utf-8')
    (project / '.archeus' / 'memory').mkdir(parents=True)
    (project / '.archeus' / 'memory' / 'graph.json').write_text('{}', encoding='utf-8')
    (project / 'CLAUDE.md').write_text('# keep\n', encoding='utf-8')
    before = (_digest(legacy), _digest(project))
    monkeypatch.setattr(config, 'config_dir', str(legacy))
    monkeypatch.setattr(rotate, 'elect', lambda *a, **k: pytest.fail('legacy rotation used'))
    writes = []
    for name in ('write_atomic', 'write_json_atomic'):
        realw = getattr(config, name)
        monkeypatch.setattr(config, name, lambda p, *a, _w=realw, **k: writes.append(p)
                            or _w(p, *a, **k))
    acc = r.account('A')
    policy(r, acc, consumption='last_resort', budgets={'concurrency': 3})
    snapshot_call(r, [real.ClaudeCodeCaller(), FakeCaller('fake')])
    ask(own(r), workdir=str(project))
    r.dispatch(r.ready())
    assert (_digest(legacy), _digest(project)) == before
    home = os.path.normcase(os.path.abspath(archeus_home()))
    assert [w for w in writes if not os.path.normcase(os.path.abspath(w)).startswith(home)] == []


# ── rollback (AP-RB) ────────────────────────────────────────────────────────

def test_migration_0012_leaves_a_copy_the_pre_ap1_build_opens(tmp_path):
    old = tmp_path / 'migrations-v11'
    old.mkdir()
    for f in sorted(os.listdir(migrate.MIGRATIONS_DIR)):
        if f.endswith('.sql') and int(f[:4]) <= 11:
            shutil.copy(os.path.join(migrate.MIGRATIONS_DIR, f), str(old))
    path = str(tmp_path / 'home' / 'archeus.db')
    Database.open(path, migrations_dir=str(old)).close()
    latest = migrate.migrations()[-1][0]           # 12 or later: 0012 is among them
    db = Database.open(path)
    with db.read() as conn:
        assert migrate.version(conn) == latest
    db.close()
    (copy,) = glob.glob(str(tmp_path / 'home' / 'backups' /
                            ('migration-archeus-v11-to-v%d-*.db' % latest)))
    restored = str(tmp_path / 'restored.db')
    B.restore(copy, restored)
    back = Database.open(restored, migrations_dir=str(old))
    with back.read() as conn:
        assert migrate.version(conn) == 11
    back.close()


# ── helpers for the snapshot builders ───────────────────────────────────────

def _ns(**kw):
    import types
    return types.SimpleNamespace(**kw)


def _mission():
    return _ns(id='msn_x', project_id=None, resource_preferences=None)


def _task():
    return _ns(id='tsk_x', capabilities_required=('code_edit',), min_model_tier=None,
               estimate=2)


def steps_of(d):
    return {c['resource']: c['eliminated_at_step'] for c in d['candidates']}


def cand_d(d, resource):
    return next(c for c in d['candidates'] if c['resource'] == resource)

