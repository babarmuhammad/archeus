# ruff: noqa: F811
import inspect
import io
import os
import queue
import threading
from types import SimpleNamespace

import pytest

from tools.pv20_mxc.native import f8_check as script, n2_check as n2
from tools.pv20_mxc.native.common import Recorder, StopRun


class FakeHarness:
    def __init__(self, root, *, leak=False, missing_control=False, host_works=True):
        self.work, self.lay = str(root), {'outside': str(root)}
        self.cmd, self.env = 'cmd.exe', {}
        self.leak, self.missing_control, self.host_works = leak, missing_control, host_works
        self.authorities, self.starts = [], []

    def prepare(self):
        pass

    def pipe(self, label, payload):
        pipe = SimpleNamespace(name='fixture_' + label, payload=payload, hits=0, errors=[])
        self.authorities.append(pipe)
        return pipe

    def start(self, tag, argv, *, port=None, principal=None):
        inspect.signature(script.Harness.start).bind(self, tag, argv, port=port, principal=principal)
        self.starts.append(argv)
        chain = argv[-1]
        marker_path = chain.split(' & ')[0].removeprefix('type ')
        marker = open(marker_path, 'rb').read()
        path = chain.split(' & ')[1].removeprefix('type ')
        authority = next((p for p in self.authorities if p.name == path), None)
        leak = b''
        if self.leak:
            if authority:
                authority.hits += 1
                leak = authority.payload
            else:
                leak = open(path, 'rb').read()
        output = leak if self.missing_control else marker + leak + b'F8_DONE'
        return SimpleNamespace(wait=lambda: 0, stdout=io.BytesIO(output)), None

    def host(self, argv, **kwargs):
        path = argv[-1]
        authority = next((p for p in self.authorities if p.name == path), None)
        if authority:
            authority.hits += 1
            payload = authority.payload
        else:
            payload = open(path, 'rb').read()
        return SimpleNamespace(returncode=0 if self.host_works else 1,
                               stdout=payload if self.host_works else b'')


def test_all_three_authorities_have_bracketing_positive_controls(tmp_path, monkeypatch):
    h = FakeHarness(tmp_path)
    calls = []

    def host(argv, **kwargs):
        calls.append(argv)
        return h.host(argv, **kwargs)

    monkeypatch.setattr(script.subprocess, 'run', host)
    rec = Recorder('F8')
    script.run(h, rec)
    assert len(h.starts) == 3 and len(calls) == 6
    assert len(h.authorities) == 2
    assert all(pipe.hits == 2 for pipe in h.authorities)
    assert rec.exit_code() == 2
    assert all(status != 'FAIL' for _, status in rec.results)


@pytest.mark.parametrize('options', [dict(leak=True), dict(missing_control=True),
                                    dict(host_works=False)])
def test_no_denial_pass_without_live_host_and_container_controls(tmp_path, monkeypatch, options):
    h = FakeHarness(tmp_path, **options)
    monkeypatch.setattr(script.subprocess, 'run', h.host)
    rec = Recorder('F8')
    with pytest.raises(StopRun):
        script.run(h, rec)
    assert len(h.starts) <= 1
    assert rec.results[-1][1] == 'FAIL'
    if not h.host_works:
        assert not h.starts


def test_pipe_leak_fails_even_without_payload(tmp_path, monkeypatch):
    h = FakeHarness(tmp_path)
    authority = h.pipe('agent', b'SYNTHETIC')
    monkeypatch.setattr(script.subprocess, 'run', h.host)
    original = h.start

    def start(*args, **kwargs):
        launch, job = original(*args, **kwargs)
        authority.hits += 1
        return launch, job

    monkeypatch.setattr(h, 'start', start)
    with pytest.raises(StopRun):
        script.probe(h, Recorder('F8'), 'agent', authority.name, authority.payload, authority)


def test_f8_entry_requires_distinct_authorization(monkeypatch):
    seen = {}

    def entry(argv, **kwargs):
        seen.update(kwargs)
        return 3

    monkeypatch.setattr(script.shared, 'entry', entry)
    assert script.main(['fixture']) == 3
    assert seen['filename'] == 'F8-owner-authorization.json'
    assert seen['scopes'] == script.SCOPES
    assert seen['stage'] == 'F8'


def test_pipe_server_sends_only_synthetic_bytes_and_closes_over_fakes(monkeypatch):
    import multiprocessing.connection as connection

    pending, sent = queue.Queue(), []
    delivered = threading.Event()

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send_bytes(self, data):
            sent.append(data)
            delivered.set()

    class Listener:
        def __init__(self, name, family, authkey):
            assert family == 'AF_PIPE' and authkey is None
            self.closed = False

        def accept(self):
            return pending.get(timeout=2)

        def close(self):
            self.closed = True

    def wake(name, family, authkey):
        client = Client()
        pending.put(client)
        return client

    monkeypatch.setattr(connection, 'Listener', Listener)
    monkeypatch.setattr(connection, 'Client', wake)
    pipe = script.AuthorityPipe('fixture-only', b'SYNTHETIC')
    try:
        pending.put(Client())
        assert delivered.wait(2)
        assert pipe.hits == 1 and sent == [b'SYNTHETIC'] and not pipe.errors
    finally:
        pipe.close()
    assert pipe.listener.closed and not pipe.thread.is_alive()


@pytest.mark.skipif(os.name != 'nt', reason='production policy uses Windows path grammar')
def test_f8_launch_drift_uses_real_transport_and_deny_all_policy(machine, tmp_path, sdk):
    h = script.Harness(str(tmp_path / 'root'), sdk[0], r'C:\Windows', n2.Budget(1e9))
    h.prepare()
    try:
        launch, _ = h.start('drift', [h.cmd, '/d', '/c', 'echo fixture'])
        raw = launch.policy.raw
        assert raw['network']['egress']['default'] == 'deny'
        assert 'networkProxy' not in raw.get('runtimeConfig', {})
        launch.wait()
        assert h.ops(launch.execution_id)[0] == n2.QUARANTINED
    finally:
        h.wind_down()


from .test_mxc_boundary import sdk  # noqa: E402, F401
from .test_pv20_native_drift import machine  # noqa: E402, F401
