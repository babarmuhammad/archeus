"""MXC seam checks use synthetic policies, filesystem fixtures and fake transports."""

from dataclasses import replace
from types import SimpleNamespace

import os
import pytest

from archeus.node import mxc


def policy(tmp_path, **changes):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    args = dict(workspace=work, cwd=work, command_line='cmd.exe /d /c echo fixture',
                env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': str(work)},
                timeout_ms=1000)
    args.update(changes)
    return mxc.compile_policy(**args)


def test_closed_default_policy(tmp_path):
    raw = policy(tmp_path).raw
    assert raw['version'] == '1.0.0' and raw['containment'] == 'processcontainer'
    assert raw['lifecycle'] == {'destroyOnExit': True, 'preservePolicy': False}
    assert raw['process']['inheritDefaultEnv'] is False
    assert raw['process']['env'] == [
        'LOCALAPPDATA=%s' % (tmp_path / 'work'), 'SYSTEMROOT=C:\\Windows']
    assert raw['network'] == {'egress': {'default': 'deny'},
                              'ingress': {'default': 'deny', 'hostLoopback': 'deny'}}
    assert raw['ui'] == {'disable': True, 'clipboard': 'none', 'injection': False}
    assert raw['telemetry'] == {'enabled': False}


@pytest.mark.parametrize('changes', [
    {'env': None}, {'env': {'SYSTEMROOT': 'C:\\Windows'}},
    {'env': {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'x', 'systemroot': 'x'}},
    {'timeout_ms': True}, {'timeout_ms': 0}, {'command_line': ''},
    {'egress': 'allow'}, {'ui': 1}, {'cwd': 'relative'},
    {'proxy_url': 'http://example.invalid:80'}, {'proxy_url': 'http://127.0.0.1'},
    {'proxy_url': 'http://user@127.0.0.1:80'},
])
def test_invalid_policy_never_spawns(tmp_path, changes):
    with pytest.raises(mxc.MxcUnavailable):
        policy(tmp_path, **changes)


def test_proxy_uses_f3_fixture_fields_and_ui_stays_disabled(tmp_path):
    raw = policy(tmp_path, proxy_url='http://127.0.0.1:18080').raw
    assert raw['processContainer'] == {'capabilities': ['internetClient']}
    assert raw['runtimeConfig'] == {'networkProxy': 'http://127.0.0.1:18080'}
    assert raw['network']['ingress'] == {'default': 'allow', 'hostLoopback': 'allow'}
    assert raw['ui']['disable'] is True


def test_writable_ancestors_cannot_cover_protected_paths(tmp_path):
    protected = tmp_path / 'work' / 'readonly'
    protected.mkdir(parents=True)
    with pytest.raises(mxc.MxcUnavailable, match='overlaps protected'):
        policy(tmp_path, readonly=(protected,))


@pytest.mark.parametrize('readonly', [False, True])
def test_hardlinks_refuse_every_granted_path(tmp_path, readonly):
    work = tmp_path / 'work'
    work.mkdir()
    outside = tmp_path / 'outside'
    outside.write_text('synthetic')
    root = tmp_path / 'runtime' if readonly else work
    root.mkdir(exist_ok=True)
    os.link(outside, root / 'alias')
    with pytest.raises(mxc.MxcUnavailable, match='multiple links'):
        policy(tmp_path, readonly=(root,) if readonly else ())


@pytest.mark.parametrize('readonly', [False, True])
def test_hardlink_added_after_compile_refuses_at_launch(tmp_path, readonly):
    root = tmp_path / 'runtime' if readonly else tmp_path / 'work'
    root.mkdir()
    compiled = policy(tmp_path, readonly=(root,) if readonly else ())
    outside = tmp_path / 'outside'
    outside.write_text('synthetic')
    os.link(outside, root / 'late')
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='multiple links'):
        mxc.spawn(compiled, exe='unused', job=object(), backend=fake)
    assert fake.calls == []


def test_mutated_policy_refuses_before_backend(tmp_path):
    compiled = policy(tmp_path)
    compiled.raw['process']['inheritDefaultEnv'] = True
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable):
        mxc.spawn(compiled, exe='unused', job=object(), backend=fake)
    assert fake.calls == []


def test_launcher_exit_is_not_agent_outcome(tmp_path):
    fake = mxc.FakeMxc([mxc.FakeOutcome(0, 'FAILED', b'fixture'),
                        mxc.FakeOutcome(7, None)])
    first = mxc.spawn(policy(tmp_path), exe='unused', job=object(), backend=fake)
    assert first.stdout.read() == b'fixture'
    assert first.wait() == 0 and first.agent_outcome == 'FAILED'
    second = fake.spawn(policy(tmp_path), exe='unused', job=object())
    assert second.wait() == 7 and second.agent_outcome is None


def test_default_and_injected_native_backend_cannot_run(tmp_path):
    class Forbidden:
        def spawn(self, *args, **kwargs):
            pytest.fail('native backend reached')
    for backend in (None, Forbidden()):
        with pytest.raises(mxc.MxcUnavailable, match='disabled'):
            mxc.spawn(policy(tmp_path), exe='unused', job=object(),
                      backend=backend, native_run=True)


def test_effective_identity_accepts_host_user_psec_and_refuses_dead_or_reused_pid(tmp_path):
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    report = mxc.effective_identity(proc)
    assert not report.is_appcontainer and report.ac_sid is None and report.user_sid
    proc.identity_reader = lambda p: replace(report, create_time=report.create_time + 1)
    with pytest.raises(mxc.MxcUnavailable):
        mxc.effective_identity(proc)
    proc.identity_reader = lambda p: report
    proc.wait()
    with pytest.raises(mxc.MxcUnavailable):
        mxc.effective_identity(proc)


@pytest.mark.parametrize('failure', [None, 'assign', 'membership', 'resume'])
def test_suspended_job_order_and_failed_launcher_retention(tmp_path, monkeypatch, failure):
    events = []
    child = SimpleNamespace(terminate=lambda: events.append('terminate'),
                            wait=lambda timeout: events.append(('wait', timeout)))

    class Transport:
        def stage_policy(self, raw):
            return str(tmp_path / 'policy.json')

        def create_suspended(self, argv, *, policy):
            assert argv == [str(tmp_path / 'wxc-exec.exe'), '--debug', str(tmp_path / 'policy.json')]
            events.append('create_suspended')
            return child

        def assign_job(self, job, proc):
            assert proc is child
            events.append('assign')
            if failure == 'assign':
                raise mxc.MxcUnavailable('assign failed')

        def in_job(self, job, proc):
            events.append('membership')
            return failure != 'membership'

        def resume(self, proc):
            events.append('resume')
            return 0 if failure == 'resume' else 1

    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    backend = mxc.NativeMxc(Transport(), lambda raw: True)
    if failure:
        with pytest.raises(mxc.MxcUnavailable) as err:
            mxc.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                      job=object(), backend=backend, native_run=True)
        assert err.value.child is child
        assert events[-2:] == ['terminate', ('wait', 5)]
        if failure in ('assign', 'membership'):
            assert 'resume' not in events
    else:
        assert mxc.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                         job=object(), backend=backend, native_run=True) is child
        assert events == ['create_suspended', 'assign', 'membership', 'resume']


def test_schema_rejection_precedes_process_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    backend = mxc.NativeMxc(None, lambda raw: False)
    with pytest.raises(mxc.MxcUnavailable, match='schema validation'):
        mxc.spawn(policy(tmp_path), exe='unused', job=object(), backend=backend, native_run=True)


def test_missing_job_refuses_fake_before_any_launch(tmp_path):
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='Job required'):
        mxc.spawn(policy(tmp_path), exe='unused', job=None, backend=fake)
    assert not fake.calls


def test_windows_boundary_never_guesses_mxc_resource_identity_or_disposal():
    from archeus.node import isolation
    from archeus.core.domain import ids
    if isolation.WindowsBoundary is None:
        pytest.skip('Windows boundary methods')
    boundary = isolation.WindowsBoundary()
    assert not boundary.available()
    key = ids.new_id('execution')
    for method in (boundary.create_profile, boundary.delete_profile,
                   boundary.derive_sid, boundary.profile_exists):
        with pytest.raises(isolation.IsolationUnavailable, match='unverified'):
            method(key)


def test_reparse_point_in_grant_refuses_without_following(tmp_path, monkeypatch):
    root = tmp_path / 'work'
    root.mkdir()
    link = root / 'junction'
    link.mkdir()
    real_stat = os.lstat

    def lstat(path):
        answer = real_stat(path)
        if os.fspath(path) == str(link):
            return SimpleNamespace(st_mode=answer.st_mode, st_file_attributes=0x400)
        return answer

    monkeypatch.setattr(mxc.os, 'lstat', lstat)
    with pytest.raises(mxc.MxcUnavailable, match='alias in grant'):
        policy(tmp_path)
