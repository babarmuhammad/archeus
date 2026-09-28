"""P15 units and boundaries (p15-design-gate §19 P31, P32; §6, §8, §11)."""

import ast
import inspect
import os
import textwrap

import pytest

from archeus.api import auth, presence, routes, schemas, sse
from archeus.core.application import commands
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
P15_HANDLERS = (routes.pair_start, routes.pair_redeem, routes.list_devices, routes.sync)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


# ── pairing codes (§6.2) ──

def test_a_pairing_code_carries_its_grant_once_and_only_until_it_expires():
    c = Clock()
    codes = auth.PairingCodes(clock=c)
    code = codes.mint({'starter': 'prn_x', 'scopes': ['observe']})
    assert len(code) >= 21                                  # 128 bits, url-safe
    assert codes.redeem(code) == {'starter': 'prn_x', 'scopes': ['observe']}
    assert codes.redeem(code) is None
    late = codes.mint({'starter': 'prn_x', 'scopes': ['observe']})
    c.now += auth.PAIR_TTL_S + 0.1
    assert codes.redeem(late) is None
    for bad in (None, '', 42):
        assert codes.redeem(bad) is None


def test_the_failure_breaker_burns_every_code_and_reopens_after_its_window():
    c = Clock()
    codes = auth.PairingCodes(clock=c)
    live = codes.mint({'starter': 'p'})
    for _ in range(codes.FAIL_LIMIT):
        assert codes.redeem('wrong') is None
    with pytest.raises(auth.PairingLocked):
        codes.redeem('wrong')
    with pytest.raises(auth.PairingLocked):
        codes.redeem(live)
    c.now += codes.FAIL_WINDOW_S
    assert codes.redeem(live) is None and len(codes) == 0
    # failures spread wider than the window never trip it
    for _ in range(codes.FAIL_LIMIT * 2):
        c.now += codes.FAIL_WINDOW_S / codes.FAIL_LIMIT + 0.1
        assert codes.redeem('wrong') is None


def test_launch_codes_are_unchanged_by_the_refactor():
    c = Clock()
    codes = auth.LaunchCodes(clock=c)
    code = codes.mint('prn_a', 'dvc_a')
    assert codes.redeem(code) == ('prn_a', 'dvc_a') and codes.redeem(code) is None


def test_step_up_failures_revoke_at_the_fifth_in_a_row_and_reset_on_success():
    f = auth.StepUpFailures()
    assert [f.failed('d') for _ in range(4)] == [False] * 4
    f.reset('d')
    assert [f.failed('d') for _ in range(5)] == [False] * 4 + [True]


# ── remote hosts (§8.2) ──

@pytest.mark.parametrize('host', ['pc.tailnet.ts.net', 'Archeus.Example.com', 'a.b:8443'])
def test_a_remote_host_is_a_dns_name(host):
    assert auth.remote_host(host) == host.lower()


@pytest.mark.parametrize('host', ['*.ts.net', '100.64.0.1', 'localhost', 'pc', '',
                                  'https://pc.ts.net', 'pc.ts.net/x', '127.0.0.1:7337'])
def test_anything_else_is_refused(host):
    with pytest.raises(ValueError):
        auth.remote_host(host)


def test_the_origin_of_a_host_is_its_own_and_https_for_a_tunnel():
    o = auth.Origin(7337, ['pc.ts.net'])
    assert o.host_ok('127.0.0.1:7337') and o.host_ok('pc.ts.net')
    assert not o.host_ok('evil.ts.net') and not o.host_ok('localhost:7337')
    assert o.local_host('127.0.0.1:7337') and not o.local_host('pc.ts.net')
    assert o.fetch_ok({'Host': 'pc.ts.net', 'Origin': 'https://pc.ts.net'})
    assert not o.fetch_ok({'Host': 'pc.ts.net', 'Origin': 'http://pc.ts.net'})
    assert not o.fetch_ok({'Host': 'pc.ts.net', 'Origin': 'http://127.0.0.1:7337'})
    assert auth.Origin(7337).remote == ()                   # nothing remote by default


# ── narrowing (§11) ──

class E:
    def __init__(self, type_, project):
        self.type, self.project = type_, project


def test_narrowing_only_removes_frames():
    everything = sse.narrowing()
    one = sse.narrowing(['prj_a'], ['mission.'])
    for e in (E('mission.created', 'prj_a'), E('mission.created', None),
              E('mission.created', 'prj_b'), E('approval.requested', 'prj_a')):
        assert everything(e)
        if one(e):
            assert everything(e)
    assert one(E('mission.created', 'prj_a')) and one(E('mission.created', None))
    assert not one(E('mission.created', 'prj_b')) and not one(E('approval.requested', 'prj_a'))


# ── the step-up PIN at rest (§6.6) ──

def test_a_pin_is_stored_as_pbkdf2_and_only_matches_itself():
    rec = commands.hash_pin('482913')
    assert entities.PIN_HASH.fullmatch(rec) and '482913' not in rec
    assert commands.pin_matches(rec, '482913')
    assert not commands.pin_matches(rec, '482914') and not commands.pin_matches(rec, None)
    assert not commands.pin_matches(None, '482913')
    assert commands.hash_pin('482913') != rec                       # salted
    with pytest.raises(ValueError):
        entities.Device(id=ids.new_id('device'), principal_id=ids.new_id('principal'),
                        name='x', platform='web', pin_hash='482913')


def test_a_client_records_how_it_registered_and_old_rows_read_as_local():
    d = entities.Device.from_dict({'id': ids.new_id('device'),
                                   'principal_id': ids.new_id('principal'),
                                   'name': 'local', 'platform': 'tui', 'state': 'ACTIVE'})
    assert (d.origin, d.client_type, d.pin_hash) == ('local', None, None)
    with pytest.raises(ValueError):
        entities.Device(id=ids.new_id('device'), principal_id=ids.new_id('principal'),
                        name='x', platform='web', origin='tunnel')


# ── P31: P15 bypasses no owner ──

def _src(fn):
    return textwrap.dedent(inspect.getsource(fn))


def _run_targets(fn):
    return {ast.unparse(n.args[0]) for n in ast.walk(ast.parse(_src(fn)))
            if isinstance(n, ast.Call) and ast.unparse(n.func) == 'req.run'}


def test_P31_p15_routes_register_clients_and_nothing_else():
    assert set().union(*(_run_targets(f) for f in P15_HANDLERS)) == {'commands.register_device'}
    # the stream writes only its presence trace; the step-up lockout only revokes
    assert _run_targets(sse.Streams._trace) == {'commands.record_connection'}
    assert _run_targets(routes._step_up_failed) == {'commands.revoke_device'}


def test_P31_a_presence_trace_moves_no_entity():
    tree = ast.parse(_src(commands.record_connection))
    calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert 'tx.append' in calls
    assert not {c for c in calls if c.endswith(('fire', '.insert', '.update'))}, calls


def test_P31_nothing_in_core_reads_presence():
    """Presence is the API's memory; no command, guard, worker or query in
    `archeus/core` may consult it (§5). Identifiers only: prose may name it."""
    bad = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, 'archeus', 'core')):
        for f in files:
            if not f.endswith('.py'):
                continue
            tree = ast.parse(open(os.path.join(dirpath, f), encoding='utf-8').read())
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute) and n.attr in ('seen', 'connections'):
                    bad.append('%s: .%s' % (f, n.attr))       # the Api's memory
                names = ([n.id] if isinstance(n, ast.Name) else
                         [a.name for a in n.names] + [n.module or '']
                         if isinstance(n, ast.ImportFrom) else
                         [a.name for a in n.names] if isinstance(n, ast.Import) else [])
                bad += ['%s: %s' % (f, x) for x in names if 'presence' in x]
    assert not bad, bad


def test_P31_the_stream_imports_no_domain_owner():
    tree = ast.parse(open(sse.__file__, encoding='utf-8').read())
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert names <= {'commands', 'queries', 'ids', 'outbox', 'auth', 'Refused'}, names


# ── P32: model and harness selection stays outside P15 ──

@pytest.mark.parametrize('field', ['model', 'harness_id', 'account_id', 'effort',
                                   'resource_preferences', 'scopes'])
def test_P32_a_redemption_cannot_carry_a_selection_or_a_scope(field):
    with pytest.raises(schemas.Invalid):
        schemas.validate({'code': 'c', 'platform': 'ios', field: 'x'}, schemas.PAIR_REDEEM)


@pytest.mark.parametrize('field', ['model', 'harness_id', 'account_id', 'effort'])
def test_P32_a_pairing_start_cannot_carry_a_selection(field):
    with pytest.raises(schemas.Invalid):
        schemas.validate({field: 'x'}, schemas.PAIR_START)


def test_P32_no_p15_module_imports_routing_or_harnesses():
    for mod in (auth, presence, sse):
        src = open(mod.__file__, encoding='utf-8').read()
        assert 'routing' not in src and 'harness' not in src, mod.__name__
    for fn in P15_HANDLERS:
        src = _src(fn)
        assert 'route' not in src.replace('routes', '') and 'harness' not in src, fn.__name__


def test_a_client_trace_is_recorded_as_the_client_not_as_a_session(tmp_path, monkeypatch):
    """P30 at the command: the trace's subject is the client and its type a
    `device.stream_*`; it creates no row of any kind."""
    monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path))
    from archeus.infra.db import Database
    db = Database.open()
    try:
        system = db.writer.execute(commands.register_principal,
                                   {'kind': 'system', 'scopes': ('system',)})['id']
        out = db.writer.execute(commands.register_device, {
            'actor': Ref('system', system), 'name': 'p', 'platform': 'ios',
            'token_hash': 'b' * 64, 'scopes': ('observe',), 'origin': 'paired'})
        with db.read() as conn:
            before = {t: conn.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
                      for t in ('missions', 'sessions', 'executions', 'devices', 'tokens')}
        db.writer.execute(commands.record_connection, {
            'actor': Ref('user_device', out['principal_id']), 'device_id': out['device_id'],
            'connection_id': ids.new_ulid(), 'opened': False, 'reason': 'client_gone'})
        with db.read() as conn:
            after = {t: conn.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
                     for t in before}
            last = conn.execute('SELECT type, subject_kind FROM events ORDER BY seq DESC '
                                'LIMIT 1').fetchone()
        assert after == before
        assert (last[0], last[1]) == ('device.stream_closed', 'device')
    finally:
        db.close()
