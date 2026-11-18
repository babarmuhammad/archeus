# ruff: noqa: F811
import inspect
import io
import json
import os
import queue
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.api import origin
from archeus.node import broker, broker_listener, origin_native, origin_windows
from tools.pv20_mxc.native import n2_check as n2, n3b_check as script
from tools.pv20_mxc.native.common import Recorder, StopRun
from tools.pv20_mxc.protocol import STAGES

from .test_broker_listener import Conn, Listening
from .test_origin_native import FakeApi, JOB, PEER


@pytest.fixture
def rig(tmp_path, monkeypatch):
    h = script.Harness(str(tmp_path), '', r'C:\Windows', n2.Budget(1000))
    h.work = str(tmp_path)
    h.curl = 'curl.exe'
    h.origin_api = FakeApi()
    h.origin_api.contained()
    h.p = SimpleNamespace(origin=origin, origin_native=origin_native,
                          origin_windows=origin_windows, broker=broker)
    h.jobs = [SimpleNamespace(handle=JOB)]
    h.principals, h.backends, h.observations, h.forwarded = {}, {}, [], []
    h.response_status, h.response_body = 200, b'fixture-response'
    monkeypatch.setattr(broker_listener._Listener, 'start',
                        lambda self, binding: setattr(self, 'binding', binding))
    h.broker = broker_listener.loopback_broker(
        backend_of=h.backend, principal_of=h.principal_of, bind=Listening,
        core_instance='fixture_core', live=lambda b, d: True,
        credentials=lambda b: {'x-api-key': 'sk-ant-api03-FIXTURE_ONLY'},
        upstream_of=lambda a: broker.Upstream('http://127.0.0.1:1', 'provider_proxy'),
        limits=broker.BrokerLimits(max_requests=5), send=h.send)
    starts = []

    def start(tag, argv, *, port=None, principal=None):
        inspect.signature(script.Harness.start).bind(h, tag, argv, port=port, principal=principal)
        starts.append(argv)
        h.eid(tag)
        endpoint = next(g['endpoint'] for g in h.broker._grants.values() if g['port'] == port)
        token = argv[argv.index('-H') + 1].removeprefix('Authorization: Bearer ')
        target = argv[argv.index('--request-target') + 1]
        path = argv[argv.index('--data-binary') + 1][1:]
        body = open(path, 'rb').read()
        head = ('POST %s HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer %s\r\n'
                % (target, token))
        extra = argv[argv.index('--write-out') + 2:-1]
        for offset in range(0, len(extra), 2):
            head += extra[offset + 1] + '\r\n'
        if not extra:
            head += 'Content-Length: %d\r\n' % len(body)
        conn = Conn(port, head.encode() + b'\r\n' + body)
        h.origin_api.rows = [origin_native.TcpRow('127.0.0.1', PEER, '127.0.0.1', port, 5, 4124)]
        h.origin_api.contained()
        h.principals[JOB] = principal

        def wait():
            endpoint.handle(conn)
            h.origin_api.table[4124] = replace(h.origin_api.table[4124], alive=False)
            status = conn.sent.split(b' ', 2)[1]
            body = conn.sent.partition(b'\r\n\r\n')[2]
            launch.stdout = io.BytesIO(body + b'\nSTATUS:' + status)
            return 0

        launch = SimpleNamespace(wait=wait)
        return launch, SimpleNamespace(handle=JOB)

    monkeypatch.setattr(h, 'start', start)
    monkeypatch.setattr(h, 'descendants', lambda argv: argv)
    monkeypatch.setattr(script.subprocess, 'run',
                        lambda *a, **kw: SimpleNamespace(returncode=52, stdout=b''))
    yield h, starts
    h.broker.revoke_all()


def test_broker_rows_drive_production_listener_attestor_and_broker(rig):
    h, starts = rig
    rec = Recorder('N3')
    script.broker_cases(h, rec)
    assert rec.exit_code() == 2
    assert len(starts) == 11
    assert all(case in STAGES['N3'].cases for case, _ in rec.results)
    assert len(h.forwarded) == 4
    assert any(ev.origin is origin.OriginClass.EXECUTION for _, ev in h.observations)


def test_broker_row_stops_at_first_bad_control(rig, monkeypatch):
    h, _ = rig
    monkeypatch.setattr(h, 'request', lambda *a, **kw: (0, 'STATUS:500', None))
    rec = Recorder('N3')
    with pytest.raises(StopRun):
        script.broker_cases(h, rec)
    assert rec.results == [('broker-reach', 'FAIL')]


def test_registry_matrix_uses_observed_native_evidence(rig):
    h, _ = rig
    grant = h.grant()
    h.request(grant)
    rec = Recorder('N3')
    script.matrix_cases(h, rec)
    assert rec.exit_code() == 2
    assert ('privileged-effect-origin-matrix', 'PASS') in rec.results


def test_evidence_persists_failure_before_stop(tmp_path):
    rec = script.Evidence('N3', str(tmp_path), 'owner-test')
    with pytest.raises(StopRun):
        rec.record('broker-reach', 'FAIL', 'control absent')
    row = json.loads(open(rec.path, encoding='utf-8').read())
    assert row['authorization_id'] == 'owner-test'
    assert row['status'] == 'FAIL'


@pytest.mark.parametrize('field,value', [('approved', False), ('scopes', []),
                                         ('script', 'N3'), ('authorization_id', '')])
def test_authorization_refuses_changed_scope(tmp_path, monkeypatch, field, value):
    monkeypatch.setattr(n2, 'parent_ok', lambda parent: True)
    data = dict(approved=True, script='N3b', authorization_id='owner-test', scopes=list(script.SCOPES))
    data[field] = value
    (tmp_path / script.AUTHORIZATION).write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(n2.SetupError):
        script.authorization(str(tmp_path), script.AUTHORIZATION, script.SCOPES)


def test_authorization_requires_existing_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(n2, 'parent_ok', lambda parent: True)
    with pytest.raises(OSError):
        script.authorization(str(tmp_path), script.AUTHORIZATION, script.SCOPES)


def test_missing_authorization_precedes_fixture_creation(monkeypatch):
    monkeypatch.setattr(script, 'authorization', lambda *a: (_ for _ in ()).throw(n2.SetupError()))
    monkeypatch.setattr(script, 'safe_root', lambda *a: pytest.fail('created fixture before authorization'))
    monkeypatch.setattr(n2, 'parent_ok', lambda p: True)
    monkeypatch.setattr(n2, '_on_windows', lambda: True)
    assert script.main(['fixture']) == 3


def test_receive_is_bounded():
    channel = SimpleNamespace(poll=lambda seconds: False)
    with pytest.raises(n2.SetupError):
        script.receive(channel, timeout=0)


def test_effect_matrix_calls_production_http_gate_without_sockets(rig, monkeypatch):
    from archeus.api import server as api_server

    h, _ = rig
    h.p.server = api_server
    h.p.routes = SimpleNamespace(
        ROUTES=[SimpleNamespace(method='POST', path='/v1/fixture-effect')], CLASS={})
    servers = []

    class Server:
        def __init__(self, address, handler):
            self.server_port, self.handler = 41099, handler
            servers.append(self)

        def serve_forever(self):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    def start(tag, argv, *, port=None):
        server = servers[-1]
        h.origin_api.rows = [origin_native.TcpRow('127.0.0.1', PEER, '127.0.0.1', port, 5, 4124)]
        h.origin_api.contained()
        output = b'EFFECT_CONTROL'
        for index, credential in enumerate(('bootstrap', 'local', 'paired')):
            handler = server.handler.__new__(server.handler)
            handler.context = origin.ConnectionContext(None, ('127.0.0.1', port),
                                                        ('127.0.0.1', PEER), str(index))
            handler.evidence, handler.evidence_acquired = None, False
            handler.origin_backend = server.api.origin_backend
            handler.origin_registry = server.api.origin_registry
            handler.headers = {'Host': '127.0.0.1:%d' % port, 'X-Fixture-Credential': credential}
            handler.command, handler.path = 'POST', '/v1/fixture-effect'
            statuses = []
            handler.send_response = statuses.append
            handler.send_header = lambda *a: None
            handler.end_headers = lambda: None
            handler.effect()
            assert statuses == [403]
            assert handler.evidence.origin is origin.OriginClass.EXECUTION
            output += ('EFFECT_%d:%d' % (index, statuses[0])).encode()
        output += b'EFFECT_DONE'
        return SimpleNamespace(wait=lambda: 0, stdout=io.BytesIO(output)), None

    monkeypatch.setattr(script.http.server, 'ThreadingHTTPServer', Server)
    monkeypatch.setattr(h, 'start', start)
    rec = Recorder('N3')
    script.effect_cases(h, rec)
    assert rec.exit_code() == 0
    assert len(rec.results) == 6


def test_death_orchestrator_requires_ready_and_reads_held_generation(rig, tmp_path, monkeypatch):
    h, _ = rig
    killed, waited = [], []

    class Process:
        exitcode = 0

        def __init__(self, **kwargs):
            self.alive = False

        def start(self):
            pass

        def terminate(self):
            killed.append(1)

        def join(self, seconds):
            pass

        def is_alive(self):
            return self.alive

    channel = SimpleNamespace(close=lambda: None, send=lambda value: None)
    context = SimpleNamespace(Process=Process, Pipe=lambda: (channel, channel))
    monkeypatch.setattr(script.multiprocessing, 'get_context', lambda method: context)
    roots = iter(str(tmp_path / str(index)) for index in range(3))
    monkeypatch.setattr(script, 'safe_root', lambda parent: next(roots))
    answers = iter([(4124, 100, 41000), True, True,
                    (4124, 100, 41000), True, True, (4124, 100, 41000)])
    monkeypatch.setattr(script, 'receive', lambda channel: next(answers))
    h.origin_api.kernel = SimpleNamespace(
        OpenProcess=lambda *a: 44, CloseHandle=lambda handle: None,
        WaitForSingleObject=lambda handle, timeout: waited.append((handle, timeout)) or 0)

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, seconds):
            pass

        def connect_ex(self, address):
            return 10061

    monkeypatch.setattr(script.socket, 'socket', Socket)
    rec = Recorder('N3')
    script.death_cases(h, rec)
    assert len(killed) == 1 and waited == [(44, 5000)]
    assert rec.exit_code() == 2


def test_ipv4_ipv6_and_descendant_denials_need_host_controls(rig, monkeypatch):
    h, _ = rig
    sockets, launches = [], []

    class Connection:
        def __init__(self):
            self.done = threading.Event()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, seconds):
            pass

        def recv(self, size):
            return b'GET / HTTP/1.1\r\n\r\n'

        def sendall(self, data):
            self.done.set()

    class Socket:
        def __init__(self, family):
            self.queue, self.family = queue.Queue(), family
            self.address = None
            sockets.append(self)

        def bind(self, address):
            self.address = (address[0], 45000 + len(sockets))

        def listen(self, count):
            pass

        def settimeout(self, seconds):
            pass

        def getsockname(self):
            return self.address

        def accept(self):
            try:
                return self.queue.get(timeout=0.01), ('fixture', 1234)
            except queue.Empty:
                raise TimeoutError from None

        def close(self):
            pass

    def host(*args, **kwargs):
        connection = Connection()
        sockets[-1].queue.put(connection)
        assert connection.done.wait(2)
        return SimpleNamespace(returncode=0, stdout=b'OK')

    def start(tag, argv, **kwargs):
        launches.append((tag, argv))
        return SimpleNamespace(wait=lambda: 7, stdout=io.BytesIO(b'N3B_CONTROL')), None

    monkeypatch.setattr(script.socket, 'socket', Socket)
    monkeypatch.setattr(script.subprocess, 'run', host)
    monkeypatch.setattr(h, 'start', start)
    rec = Recorder('N3')
    script.network_cases(h, rec)
    assert [sock.family for sock in sockets] == [script.socket.AF_INET, script.socket.AF_INET6]
    assert len(launches) == 6
    assert rec.results.count(('forbidden-ipv4-ipv6-descendants', 'PASS')) == 4
    assert rec.exit_code() == 2


@pytest.mark.skipif(os.name != 'nt', reason='production policy uses Windows path grammar')
def test_launch_drift_uses_real_mxc_transport_ledger_and_policy(machine, tmp_path, sdk):
    h = script.Harness(str(tmp_path / 'root'), sdk[0], r'C:\Windows', n2.Budget(1e9))
    n2.Harness.prepare(h)
    h.work, h.principals = h.lay['p']['state'], {}
    try:
        launch, job = h.start('drift', [h.cmd, '/d', '/c', 'echo fixture'],
                              port=41000, principal='fixture_principal')
        assert launch.policy.raw['runtimeConfig']['networkProxy'] == 'http://127.0.0.1:41000'
        assert h.principals[job.handle] == 'fixture_principal'
        launch.wait()
        assert h.ops(launch.execution_id)[0] == n2.QUARANTINED
    finally:
        h.wind_down()


from .test_mxc_boundary import sdk  # noqa: E402, F401
from .test_pv20_native_drift import machine  # noqa: E402, F401
