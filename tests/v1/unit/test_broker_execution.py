"""PV-20 provider broker in the execution path (PV20-08 §4, PV20-09): the recorded digest,
cleared on every end path and hidden from views; the manager's admission and ordering,
revocation, and the per-request recheck; the typed launch binding and the isolated
environment; the router's `broker` step; and - pinned first - that with
BROKER_DISPATCH_ENABLED off nothing changes."""

import ast
import os
from types import SimpleNamespace

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.execution import manager as M
from archeus.core.routing import router as R
from archeus.harnesses import base
from archeus.node import broker as B
from v1.unit.test_execution_units import _row, _seeded, _spawn_rig, _steps
from v1.unit.test_routing_units import acct, harness, own, snap, steps, task

SRC = os.path.join(os.path.dirname(X.__file__), 'executions.py')


class Spy:
    """A broker the manager can hold; every call lands in *calls*."""

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail
        self.core_instance, self.limits = 'core1', B.BrokerLimits(max_requests=5)

    def upstream_of(self, account_id):
        return B.Upstream('https://api.example.com')

    def issue(self, binding):
        self.calls.append(('issue', binding))
        if self.fail:
            raise self.fail
        return 'brk_tok', 'd' * 64, 'ep', 4321

    def revoke(self, execution_id):
        self.calls.append(('revoke', execution_id))

    def sweep(self, live):
        self.calls.append(('sweep', set(live)))

    def revoke_all(self):
        self.calls.append(('revoke_all',))


# ── switch off: today's behaviour, exactly ──

@pytest.mark.parametrize('decide', [False, True])
def test_with_the_switch_off_the_spawn_is_untouched_even_with_a_broker_held(
        monkeypatch, tmp_path, decide):
    assert B.BROKER_DISPATCH_ENABLED is False
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide)
    m.broker = spy = Spy()
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['requested'] + ['stage'] * decide + [
        'workspace', 'inventory', 'prepare_process', 'spawn', 'record_process']
    (_, spec, _), = [x for x in log if x[0] == 'spawn']
    assert spec.broker is None and spy.calls == []
    assert [x[1]['broker_digest'] for x in log if x[0] == 'prepare_process'] == [None]


def test_a_manager_made_without_a_broker_holds_none():
    m = M.ExecutionManager.__new__(M.ExecutionManager)
    M.ExecutionManager.__init__(m, SimpleNamespace(), actor=None, registry=None,
                                work=SimpleNamespace(policy=None, missions=None, router=None),
                                node=SimpleNamespace())
    assert m.broker is None


def test_the_router_filters_nothing_without_the_gate():
    s = snap([harness('claude_code'), harness('codex')],
             [acct('a1', 'claude_code', auth='subscription_oauth'), own('codex')])
    d = R.route(task(), s)
    assert 'broker' not in steps(d).values()
    assert R.route(task(), dict(s, isolated_dispatch=None)) == d


# ── switch on ──

def _on(monkeypatch, tmp_path, decide=True, kind='api_key', fail=None, **rig):
    monkeypatch.setattr(B, 'BROKER_DISPATCH_ENABLED', True)
    m, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, decide, **rig)
    m.broker = Spy(fail)
    e.harness_id, e.account_id, e.route_decision_id, e.model = (
        'claude_code', 'acc_1' if kind else None, 'rte_1', 'claude-x')
    get = M.rows.get

    def rows_get(r, k, i):
        if k is entities.Account:
            return SimpleNamespace(entity=SimpleNamespace(auth_kind=kind, home_ref=None))
        return get(r, k, i)
    monkeypatch.setattr(M.rows, 'get', rows_get)
    return m, e, mission, log


def test_an_isolated_process_is_granted_before_it_is_prepared_and_started(monkeypatch,
                                                                          tmp_path):
    m, e, mission, log = _on(monkeypatch, tmp_path)
    assert m._spawn(e, mission) is True
    assert _steps(log) == ['requested', 'stage', 'workspace', 'inventory', 'prepare_process',
                           'spawn', 'record_process']
    (op, bd), = m.broker.calls
    assert op == 'issue' and (bd.execution_id, bd.process_seq, bd.principal) == (
        e.id, 1, M.profile_name(e.id))
    assert (bd.account_id, bd.route_decision_id, bd.model, bd.core_instance) == (
        'acc_1', 'rte_1', 'claude-x', 'core1')
    (_, spec, _), = [x for x in log if x[0] == 'spawn']
    assert spec.broker == base.BrokerLaunch(4321, 'brk_tok')
    assert [x[1]['broker_digest'] for x in log if x[0] == 'prepare_process'] == ['d' * 64]


def test_a_process_that_is_not_isolated_is_never_brokered(monkeypatch, tmp_path):
    m, e, mission, log = _on(monkeypatch, tmp_path, decide=False)
    assert m._spawn(e, mission) is True
    (_, spec, _), = [x for x in log if x[0] == 'spawn']
    assert spec.broker is None and m.broker.calls == []


@pytest.mark.parametrize('kind', [None, 'subscription_oauth'])
def test_an_account_the_broker_cannot_serve_starts_nothing(monkeypatch, tmp_path, kind):
    m, e, mission, log = _on(monkeypatch, tmp_path, kind=kind)
    assert m._spawn(e, mission) is True
    assert _steps(log)[-1] == 'refuse' and 'spawn' not in _steps(log)
    assert log[-1][1]['stop_reason'] == 'binding' and 'broker' in log[-1][1]['reason']
    assert m.broker.calls == []


@pytest.mark.parametrize('err', [B.BrokerUnavailable('no pipe'), B.Refused(403, 'no ceiling')])
def test_a_grant_that_cannot_be_issued_starts_nothing(monkeypatch, tmp_path, err):
    m, e, mission, log = _on(monkeypatch, tmp_path, fail=err)
    assert m._spawn(e, mission) is True
    assert 'spawn' not in _steps(log) and 'prepare_process' not in _steps(log)
    assert log[-1][1]['stop_reason'] == 'binding' and 'no broker grant' in log[-1][1]['reason']
    assert m.broker.calls[-1] == ('revoke', e.id)


def test_a_spawn_that_fails_after_the_grant_revokes_it(monkeypatch, tmp_path):
    m, e, mission, log = _on(monkeypatch, tmp_path)

    def boom(adapter, spec, **kw):
        raise base.SpawnFailed('no')
    m.node.spawn = boom
    assert m._spawn(e, mission) is True
    assert m.broker.calls[-1] == ('revoke', e.id)


def test_the_adapter_login_check_is_never_called_on_the_brokered_path(monkeypatch, tmp_path):
    m, e, mission, log = _on(monkeypatch, tmp_path)
    adapter = m.registry.get('claude_code')
    adapter.authenticate = lambda account: pytest.fail('the subscription reader was called')
    assert m._spawn(e, mission) is True


@pytest.mark.parametrize('disarmed', [False, True])
def test_every_pass_revokes_the_grants_of_executions_no_longer_live(disarmed):
    m = M.ExecutionManager.__new__(M.ExecutionManager)
    live = [SimpleNamespace(id='exe_live', mission_id='m')]
    m._read = lambda: (live, {})
    m._step = lambda e, mi, d: False
    m._orphans = lambda ids_, d: 0
    m.node = SimpleNamespace(disarmed=lambda: disarmed)
    m.usage, m.broker = None, Spy()
    m._clock = {'accounts': float('inf'), 'usage': float('inf'), 'isolation': float('inf')}
    m.tick()
    assert m.broker.calls == ([('revoke_all',)] if disarmed else [('sweep', {'exe_live'})])


# ── the recorded digest ──

def _is_none(node):
    return isinstance(node, ast.Constant) and node.value is None


def test_every_end_path_that_clears_the_hook_digest_clears_the_broker_digest():
    tree = ast.parse(open(SRC, encoding='utf-8').read())
    cleared = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            pairs = {k.value: v for k, v in zip(n.keys, n.values)
                     if isinstance(k, ast.Constant)}
            if _is_none(pairs.get('hook_token_hash')):
                cleared += 1
                assert _is_none(pairs.get('broker_token_hash')), ast.unparse(n)
        elif isinstance(n, ast.Call):
            kws = {k.arg: k.value for k in n.keywords}
            if _is_none(kws.get('hook_token_hash')):
                cleared += 1
                assert _is_none(kws.get('broker_token_hash')), ast.unparse(n)
    assert cleared >= 6


def test_preparation_records_the_digest_it_is_given_and_none_by_default():
    tree = ast.parse(open(SRC, encoding='utf-8').read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == 'prepare_process')
    defaults = dict(zip([a.arg for a in fn.args.kwonlyargs], fn.args.kw_defaults))
    assert isinstance(defaults['broker_digest'], ast.Constant)
    assert defaults['broker_digest'].value is None
    assert "'broker_token_hash': broker_digest" in ast.unparse(fn)


def _with_digests(db, eid):
    """Both digests as preparation leaves them. Written raw: the record is no state change
    the writer would demand an event for, and the digests live in the row's body."""
    def run(tx, **_):
        tx.execute("UPDATE executions SET body = json_set(body, '$.hook_token_hash', ?, "
                   "'$.broker_token_hash', ?) WHERE id = ?", ('h' * 64, 'b' * 64, eid))
    db.writer.execute(run, {})


def test_a_refusal_clears_both_digests():
    db, who, eid, _ = _seeded('INTENT')
    try:
        _with_digests(db, eid)
        db.writer.execute(X.refuse, {'actor': who, 'execution_id': eid, 'reason': 'x',
                                     'stop_reason': 'binding'})
        e = _row(db, entities.Execution, eid).entity
        assert (e.hook_token_hash, e.broker_token_hash) == (None, None)
    finally:
        db.close()


def test_the_digest_is_never_in_a_view():
    db, who, eid, tid = _seeded('RUNNING')
    try:
        _with_digests(db, eid)
        with db.read() as r:
            one, many = X.view(r, eid), X.of_task(r, tid)
        for d in [one] + many:
            assert 'broker_token_hash' not in d and 'hook_token_hash' not in d
            assert 'b' * 64 not in repr(d)
    finally:
        db.close()


def test_the_recheck_follows_the_recorded_generation():
    db, who, eid, _ = _seeded('PAUSED', isolated=True, process_seq=1)
    try:
        _with_digests(db, eid)
        m = M.ExecutionManager.__new__(M.ExecutionManager)
        m.db = db
        e = _row(db, entities.Execution, eid).entity
        bd = B.BrokerBinding(core_instance='c', execution_id=eid, process_seq=1, principal='p',
                             route_decision_id=e.route_decision_id, account_id=e.account_id,
                             harness_id='claude_code', model=e.model,
                             upstream=B.Upstream('https://x'))
        assert m.broker_live(bd, 'b' * 64)
        assert not m.broker_live(bd, 'c' * 64)                         # another digest
        assert not m.broker_live(B.BrokerBinding(**dict(bd.__dict__, process_seq=2)), 'b' * 64)
        assert not m.broker_live(B.BrokerBinding(**dict(bd.__dict__, model='other')), 'b' * 64)
        db.writer.execute(X.refuse, {'actor': Ref('system', ids.new_id('principal')),
                                     'execution_id': eid, 'reason': 'x', 'stop_reason': 'binding'})
        assert not m.broker_live(bd, 'b' * 64)                         # ended
    finally:
        db.close()


# ── the launch binding and the isolated environment ──

@pytest.mark.parametrize('port,token', [(0, 'brk_a'), (70000, 'brk_a'), (80, 'hook_a'),
                                        (80, 'brk_a b'), ('80', 'brk_a')])
def test_a_launch_binding_is_a_port_and_a_broker_token(port, token):
    with pytest.raises(ValueError):
        base.BrokerLaunch(port, token)


def test_the_launch_binding_never_prints_its_token():
    launch = base.BrokerLaunch(4321, 'brk_tok')
    assert 'brk_tok' not in repr(launch)
    assert 'brk_tok' not in repr(base.ExecutionSpec(execution_id=ids.new_id('execution'),
                                                    prompt='p', workdir='.', broker=launch))


def _paths(tmp_path):
    for d in ('h', 't', 'c'):
        (tmp_path / d).mkdir()
    return SimpleNamespace(home=str(tmp_path / 'h'), tmp=str(tmp_path / 't'),
                           config=str(tmp_path / 'c'))


def _spec(tmp_path, **kw):
    w = tmp_path / 'w'
    w.mkdir(exist_ok=True)
    return base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt='p',
                              workdir=str(w), **kw)


def test_the_isolated_environment_takes_the_model_variables_from_the_binding_alone(tmp_path):
    p = _paths(tmp_path)
    launch = base.BrokerLaunch(4321, 'brk_tok')
    env = base._isolated_env(_spec(tmp_path, broker=launch, env={
        'ANTHROPIC_AUTH_TOKEN': None, 'ANTHROPIC_API_KEY': None}), p)
    assert env['ANTHROPIC_BASE_URL'] == 'http://127.0.0.1:4321'
    assert env['ANTHROPIC_AUTH_TOKEN'] == 'brk_tok'
    assert env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] == '1'
    assert 'ANTHROPIC_API_KEY' not in env and 'CLAUDE_CODE_OAUTH_TOKEN' not in env
    with pytest.raises(ValueError):          # a caller cannot choose another endpoint
        base._isolated_env(_spec(tmp_path, broker=launch,
                                 env={'ANTHROPIC_BASE_URL': 'http://127.0.0.1:1'}), p)
    with pytest.raises(ValueError):          # nor name one without a binding
        base._isolated_env(_spec(tmp_path, env={'ANTHROPIC_BASE_URL':
                                                'http://127.0.0.1:4321'}), p)
    plain = base._isolated_env(_spec(tmp_path), p)
    assert not {k for k in plain if k.startswith('ANTHROPIC')}


def test_a_brokered_claude_code_process_skips_the_preflight_fetch():
    import json
    from archeus.harnesses.claude_code.adapter import ClaudeCodeAdapter
    a = ClaudeCodeAdapter(exe='claude')
    eid = ids.new_id('execution')
    spec = base.ExecutionSpec(execution_id=eid, prompt='p', workdir='.')
    plain = json.load(open(a._settings(spec), encoding='utf-8'))
    brokered = json.load(open(a._settings(base.ExecutionSpec(
        execution_id=eid, prompt='p', workdir='.',
        broker=base.BrokerLaunch(4321, 'brk_tok'))), encoding='utf-8'))
    assert 'skipWebFetchPreflight' not in plain and brokered['skipWebFetchPreflight'] is True


# ── the router's `broker` step, while isolated dispatch is on ──

GATE = {'broker': {h: list(k) for h, k in base.BROKER_ELIGIBLE.items()}}


def test_while_isolated_dispatch_is_on_only_broker_eligible_accounts_survive():
    s = snap([harness('claude_code'), harness('codex')],
             [acct('a1', 'claude_code', auth='api_key'),
              acct('a2', 'claude_code', auth='subscription_oauth'),
              acct('a3', 'claude_code', auth='provider_proxy'), own('codex')],
             isolated_dispatch=GATE)
    st = steps(R.route(task(), s))
    assert st['a2'] == 'broker' and st['codex'] == 'broker'
    assert st['a1'] != 'broker' and st['a3'] != 'broker'


def test_the_gate_never_touches_archeus_own_calls():
    from v1.unit.test_routing_units import call
    s = snap([harness('codex', 'headless')], [own('codex')], isolated_dispatch=GATE)
    assert 'broker' not in steps(R.route(call(), s)).values()


def test_broker_eligibility_is_claude_code_on_api_or_proxy_accounts_only():
    assert base.broker_eligible('claude_code', 'api_key')
    assert base.broker_eligible('claude_code', 'provider_proxy')
    for h, k in (('claude_code', 'subscription_oauth'), ('claude_code', None),
                 ('codex', 'api_key'), ('pi', 'provider_proxy')):
        assert not base.broker_eligible(h, k)


def test_the_task_snapshot_carries_the_gate_only_when_set(monkeypatch):
    from archeus.core.application import resources
    assert resources.ISOLATED_DISPATCH is None
    src = open(resources.__file__, encoding='utf-8').read()
    assert src.count("snap['isolated_dispatch'] = ISOLATED_DISPATCH") == 1
    assert "    if ISOLATED_DISPATCH:\n        snap['isolated_dispatch']" in src

