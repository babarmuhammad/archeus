"""T-237 gap checks for the closed MXC seam: fail-closed paths, grant widening,
network/proxy/UI fields, environment and command quoting, scan errors.

Style follows tests/v1/unit/test_node_mxc.py: synthetic policies, tmp_path
fixtures, monkeypatched lstat seams, fake transports. No network, no process
spawning, no Windows API call.
"""

import os
import stat
from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.node import linkscan, mxc

_DROP = object()


def policy(tmp_path, **changes):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    args = dict(workspace=work, cwd=work, command_line='cmd.exe /d /c echo fixture',
                env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': str(work)},
                timeout_ms=1000)
    args.update(changes)
    return mxc.compile_policy(**args)


def _mutate(raw, path, value):
    target = raw
    for key in path[:-1]:
        target = target[key]
    if value is _DROP:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return raw


class Forbidden(mxc.FakeMxc):
    """A backend that must never see an unsafe policy."""
    def spawn(self, policy, *, exe, job):
        pytest.fail('backend reached with a policy that must refuse')


def refuses(tmp_path, mutations, expect, **changes):
    """Mutate a compiled policy; validation must refuse before any backend."""
    compiled = policy(tmp_path, **changes)
    for path, value in mutations:
        _mutate(compiled.raw, path, value)
    with pytest.raises(mxc.MxcUnavailable, match=expect) as caught:
        mxc.spawn(compiled, exe='unused', job=object(), backend=Forbidden([]))
    return str(caught.value)


def fake_lstat(monkeypatch, targets):
    """Replace os.lstat answers for the named paths only (reparse/error fixtures)."""
    real = os.lstat

    def lstat(path, *args, **kwargs):
        key = os.fspath(path)
        if key in targets:
            spec = targets[key]
            if isinstance(spec, Exception):
                raise spec
            return SimpleNamespace(st_mode=spec['st_mode'], st_nlink=1,
                                   st_file_attributes=spec.get('attributes', 0))
        return real(path)

    monkeypatch.setattr(mxc.os, 'lstat', lstat)


def reparse(path):
    return {'st_mode': os.lstat(path).st_mode, 'attributes': 0x400}


def mode(path, kind):
    return {'st_mode': kind | (os.lstat(path).st_mode & 0o777)}


# --- the ten highest-risk uncovered branches ---------------------------------

@pytest.mark.parametrize('change', [
    (('processContainer',), {'capabilities': ['internetClient']}),
    (('runtimeConfig',), {'networkProxy': 'http://127.0.0.1:18080'}),
    (('telemetry',), _DROP),
    (('ui',), _DROP),
    (('lifecycle',), _DROP),
    (('process',), _DROP),
    (('containment',), _DROP),
])
def test_unknown_or_missing_top_level_fields_refuse(tmp_path, change):
    """mxc.py:149 unknown or missing policy fields (capabilities smuggled in)."""
    refuses(tmp_path, [change], 'unknown or missing policy fields')


@pytest.mark.parametrize('change', [
    (('lifecycle', 'destroyOnExit'), False),
    (('lifecycle', 'destroyOnExit'), 1),
    (('lifecycle', 'preservePolicy'), True),
    (('lifecycle', 'preservePolicy'), 0),
    (('lifecycle', 'preserveHandles'), True),
    (('lifecycle', 'destroyOnExit'), _DROP),
])
def test_unsafe_lifecycle_refuses(tmp_path, change):
    """mxc.py:155 unsafe lifecycle (a container or policy outliving the launch)."""
    expect = 'invalid MXC policy' if change[1] is _DROP else 'unsafe lifecycle'
    refuses(tmp_path, [change], expect)


@pytest.mark.parametrize('change', [
    (('version',), '1.0.1'),
    (('version',), '1.0'),
    (('version',), 1.0),
    (('containment',), 'appcontainer'),
    (('containment',), 'ProcessContainer'),
    (('containment',), 'sandbox'),
])
def test_wrong_schema_or_backend_refuses(tmp_path, change):
    """mxc.py:151 wrong schema or backend (a non-processcontainer launch)."""
    refuses(tmp_path, [change], 'wrong schema or backend')


@pytest.mark.parametrize('change', [
    (('network', 'egress', 'default'), 'allow'),
    (('network', 'egress', 'default'), 'block'),
    (('network', 'ingress', 'default'), 'allow'),
    (('network', 'ingress', 'hostLoopback'), 'allow'),
    (('network', 'ingress', 'peerExcluded'), False),
    (('network', 'egress'), {}),
    (('network', 'ingress'), {'default': 'deny'}),
])
def test_network_widening_refuses_before_backend(tmp_path, change):
    """mxc.py:192 unsafe network policy (egress or host loopback opened)."""
    refuses(tmp_path, [change], 'unsafe network policy')


@pytest.mark.parametrize('change', [
    (('network', 'egress', 'default'), 'allow'),
    (('network', 'ingress', 'hostLoopback'), 'deny'),
])
def test_proxy_never_widens_egress_or_drops_loopback_guard(tmp_path, change):
    """mxc.py:192 with the F3 proxy fields present the network block stays exact."""
    refuses(tmp_path, [change], 'unsafe network policy',
            proxy_url='http://127.0.0.1:18080')


@pytest.mark.parametrize('change', [
    (('processContainer', 'capabilities'), ['internetClient', 'runAllTasks']),
    (('processContainer', 'capabilities'), ['runAllTasks']),
    (('processContainer', 'capabilities'), []),
    (('processContainer', 'capabilities'), 'internetClient'),
    (('processContainer', 'profiles'), ['thing']),
    (('processContainer',), _DROP),
    (('runtimeConfig', 'allowAnyHost'), True),
])
def test_proxy_capability_widening_refuses(tmp_path, change):
    """mxc.py:196 invalid proxy policy (capabilities beyond the F3 fixture)."""
    expect = 'unknown or missing policy fields' if change[1] is _DROP else 'invalid proxy policy'
    refuses(tmp_path, [change], expect, proxy_url='http://127.0.0.1:18080')


@pytest.mark.parametrize('url', [
    'http://10.0.0.1:18080', 'http://0.0.0.0:18080', 'http://192.168.1.1:18080',
    'https://127.0.0.1:18080', 'socks5://127.0.0.1:18080', 'http://127.0.0.1:0',
    'http://127.0.0.1:18080/relay', 'http://127.0.0.1:18080?target=evil',
    'http://127.0.0.1:18080#frag', 'http://user:pass@127.0.0.1:18080',
])
def test_mutated_proxy_endpoint_refuses_before_backend(tmp_path, url):
    """mxc.py:201 invalid proxy endpoint (a policy staged for one proxy, relaunched for another)."""
    refuses(tmp_path, [(('runtimeConfig', 'networkProxy'), url)],
            'invalid proxy endpoint', proxy_url='http://127.0.0.1:18080')


@pytest.mark.parametrize('change', [
    (('ui', 'disable'), 0),
    (('ui', 'clipboard'), 'readwrite'),
    (('ui', 'clipboard'), 'read'),
    (('ui', 'injection'), True),
    (('ui', 'injection'), 1),
    (('ui', 'allowWindows'), True),
    (('telemetry', 'enabled'), True),
    (('telemetry', 'enabled'), 0),
    (('telemetry',), {'enabled': False, 'sampling': 0}),
])
def test_ui_or_telemetry_widening_refuses(tmp_path, change):
    """mxc.py:207 unsafe UI or telemetry (desktop escape or exfil channel)."""
    refuses(tmp_path, [change], 'unsafe UI or telemetry')


def test_ui_enabled_policy_refuses_before_backend(tmp_path):
    """mxc.py:207 the sealed subset keeps the desktop UI disabled, whatever the raw says."""
    refuses(tmp_path, [(('ui', 'disable'), False)], 'unsafe UI or telemetry')


def test_compiler_refuses_an_enabled_ui(tmp_path):
    """mxc.py:99 UI is a deny-only knob: ui=True must not compile."""
    with pytest.raises(mxc.MxcUnavailable, match='unsupported UI or egress policy'):
        policy(tmp_path, ui=True)


@pytest.mark.parametrize('shape,expect', [
    (lambda work: [str(work) + os.sep], 'noncanonical path'),
    (lambda work: [os.path.join(str(work), '.')], 'noncanonical path'),
    (lambda work: [os.path.join(str(work), '..')], 'noncanonical path'),
    (lambda work: [str(work) + os.sep + '..' + os.sep + 'work'], 'noncanonical path'),
    (lambda work: [os.path.dirname(str(work)) + os.sep + os.sep + os.path.basename(str(work))],
     'noncanonical path'),
    (lambda work: ['relative' + os.sep + 'work'], 'must be absolute'),
])
def test_noncanonical_grant_path_refuses(tmp_path, shape, expect):
    """mxc.py:180 noncanonical path (dot, dot-dot, separator or relative grants)."""
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    compiled = policy(tmp_path)
    compiled.raw['filesystem']['readwritePaths'] = shape(work)
    with pytest.raises(mxc.MxcUnavailable, match=expect):
        mxc.spawn(compiled, exe='unused', job=object(), backend=Forbidden([]))


@pytest.mark.parametrize('which', ['outside', 'missing', 'empty', 'excluded'])
def test_cwd_outside_grants_or_empty_writable_refuses(tmp_path, which):
    """mxc.py:184 cwd outside grants (the launch directory must be a granted directory)."""
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    other = tmp_path / 'other'
    other.mkdir(exist_ok=True)
    changes = {'outside': {'cwd': other}, 'missing': {'cwd': work / 'missing'},
               'empty': {'workspace': ()}, 'excluded': {'workspace': (other,), 'cwd': work}}
    with pytest.raises(mxc.MxcUnavailable, match='cwd outside grants'):
        policy(tmp_path, **changes[which])


def test_cwd_may_live_in_a_readonly_grant(tmp_path):
    """mxc.py:184 positive control: cwd inside a readonly grant is still legal."""
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    compiled = policy(tmp_path, readonly=(runtime,), cwd=runtime)
    assert compiled.raw['process']['cwd'] == str(runtime)
    assert mxc.spawn(compiled, exe='unused', job=object(),
                     backend=mxc.FakeMxc([mxc.FakeOutcome()])) is not None


@pytest.mark.parametrize('readonly,denied,expect', [
    ('runtime', 'runtime-secret', 'readonly grant overlaps denied path'),
    ('protected-sub', 'protected', 'readonly grant overlaps denied path'),
    ('runtime', 'work-secret', 'overlaps protected path'),
])
def test_denied_path_cannot_hide_under_a_grant(tmp_path, readonly, denied, expect):
    """mxc.py:188 readonly grant overlaps denied path (a denied tree under a grant)."""
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    protected = tmp_path / 'protected'
    (protected / 'sub').mkdir(parents=True)
    roots = {'runtime': runtime, 'protected-sub': protected / 'sub', 'protected': protected,
             'runtime-secret': runtime / 'secrets', 'work-secret': tmp_path / 'work' / 'secrets'}
    refuses(tmp_path, [(('filesystem', 'readonlyPaths'), [str(roots[readonly])]),
                       (('filesystem', 'deniedPaths'), [str(roots[denied])])], expect)


# --- supplementary checks, beyond the required ten ---------------------------

@pytest.mark.parametrize('candidate', [
    None, {}, {'version': '1.0.0'}, [], 'policy',
])
def test_non_policy_object_never_reaches_a_backend(tmp_path, candidate):
    """mxc.py:142 MxcPolicy object required (a bare dict is not a policy)."""
    with pytest.raises(mxc.MxcUnavailable, match='MxcPolicy object required'):
        mxc.validate_policy(candidate)
    with pytest.raises(mxc.MxcUnavailable, match='MxcPolicy object required'):
        mxc.spawn(candidate, exe='unused', job=object(), backend=mxc.FakeMxc([]))


@pytest.mark.parametrize('env,expect', [
    (['SYSTEMROOT'], 'invalid environment entry'),
    ([1], 'invalid environment entry'),
    (['PATH=a', 'Path=b', 'SYSTEMROOT=C:\\Windows', 'LOCALAPPDATA=x'], 'duplicate environment entry'),
    (['PATH=a=', 'PATH=b', 'SYSTEMROOT=C:\\Windows', 'LOCALAPPDATA=x'], 'duplicate environment entry'),
    (['LOCALAPPDATA=x'], 'SYSTEMROOT and LOCALAPPDATA required'),
    (['SYSTEMROOT=', 'LOCALAPPDATA=x'], 'SYSTEMROOT and LOCALAPPDATA required'),
    (['SYSTEMROOT=C:\\Windows', 'LOCALAPPDATA=x', 'BAD\0NAME=y'], 'invalid environment entry'),
])
def test_environment_entries_reject_injection_and_duplicates(tmp_path, env, expect):
    """mxc.py:165,168,171 environment entries (case collisions, NUL, missing anchors)."""
    refuses(tmp_path, [(('process', 'env'), env)], expect)


def test_environment_value_may_hold_equals_and_stays_one_variable(tmp_path):
    """mxc.py:167 positive control: one '=' split only, so a value cannot fork a variable."""
    compiled = policy(tmp_path, env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'x',
                                     'TOKEN': 'a=b=c'})
    assert compiled.raw['process']['env'] == ['LOCALAPPDATA=x', 'SYSTEMROOT=C:\\Windows',
                                              'TOKEN=a=b=c']
    assert mxc.validate_policy(compiled) is None


@pytest.mark.parametrize('env', [
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'x', 'localappdata': 'y'},
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'x', 'SystemRoot': 'y'},
])
def test_compile_rejects_case_colliding_environment_names(env):
    """mxc.py:107 two names that are one variable must refuse while compiling, not later."""
    with pytest.raises(mxc.MxcUnavailable, match='explicit SYSTEMROOT and LOCALAPPDATA required'):
        mxc.compile_policy(workspace='workspace', cwd='workspace', command_line='cmd.exe /c echo x',
                           env=env, timeout_ms=1000)


@pytest.mark.parametrize('env', [
    ['SYSTEMROOT=C:\\Windows', 'LOCALAPPDATA=x'],
    1,
    {'SYSTEMROOT': 1, 'LOCALAPPDATA': 'x'},
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'a\0b'},
    {'SYSTEMROOT=C:\\Windows': 'x', 'LOCALAPPDATA': 'x'},
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'x', '': 'x'},
    {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'x', None: 'x'},
])
def test_compile_rejects_environment_that_is_not_a_string_map(env):
    """mxc.py:105 invalid explicit environment (host env smuggled in as junk)."""
    with pytest.raises(mxc.MxcUnavailable, match='invalid explicit environment'):
        mxc.compile_policy(workspace='workspace', cwd='workspace', command_line='cmd.exe /c echo x',
                           env=env, timeout_ms=1000)


@pytest.mark.parametrize('line', ['cmd.exe /d /c "echo a && echo b"', "cmd.exe /c 'a;b'",
                                  'cmd.exe /c echo back\\slash', 'a' * 900])
def test_command_line_is_carried_verbatim(tmp_path, line):
    """mxc.py:112 command quoting: the compiled argv string is never rewritten."""
    assert policy(tmp_path, command_line=line).raw['process']['commandLine'] == line


@pytest.mark.parametrize('line', ['a\0b', '', 5, ['echo', 'x'], 3.5, ('echo',)])
def test_command_line_rejects_nul_or_non_text(tmp_path, line):
    """mxc.py:158 invalid process policy (NUL, empty or non-text command line)."""
    compiled = policy(tmp_path)
    compiled.raw['process']['commandLine'] = line
    with pytest.raises(mxc.MxcUnavailable, match='invalid process policy'):
        mxc.spawn(compiled, exe='unused', job=object(), backend=Forbidden([]))


@pytest.mark.parametrize('field,value,expect', [
    ('deniedPaths', _DROP, 'invalid filesystem policy'),
    ('executePaths', [], 'invalid filesystem policy'),
    ('readwritePaths', 'duplicates', 'duplicate or invalid paths'),
    ('readonlyPaths', 'tuple', 'duplicate or invalid paths'),
])
def test_filesystem_policy_shape_refuses(tmp_path, field, value, expect):
    """mxc.py:174,177 invalid filesystem policy and duplicate or invalid paths."""
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    if value == 'duplicates':
        value = [str(work), str(work)]
    elif value == 'tuple':
        value = (str(runtime),)
    refuses(tmp_path, [(('filesystem', field), value)], expect)


def test_duplicate_grant_path_refuses(tmp_path):
    """mxc.py:177 the same path twice is a policy bug, not a no-op."""
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    refuses(tmp_path, [(('filesystem', 'readonlyPaths'), [str(runtime), str(runtime)])],
            'duplicate or invalid paths')


def test_within_helper_treats_uncommon_paths_as_outside(tmp_path):
    """mxc.py:43 _within: an unusable comparison is never read as containment."""
    parent = str(tmp_path / 'a')
    assert mxc._within(os.path.join(parent, 'b'), parent) is True
    assert mxc._within(parent, os.path.join(parent, 'b')) is False
    assert mxc._within(parent, str(tmp_path / 'zz')) is False
    assert mxc._within(parent, parent) is True
    assert mxc._within(parent, 'relative') is False


def test_within_helper_refuses_an_empty_operand(tmp_path):
    """mxc.py:43 _within: an empty operand must not look contained."""
    assert mxc._within(str(tmp_path / 'a'), '') is False


def test_alias_in_grant_ancestor_refuses(tmp_path, monkeypatch):
    """mxc.py:60 a reparse point above the grant must not become the grant root."""
    fake_lstat(monkeypatch, {str(tmp_path): reparse(tmp_path)})
    with pytest.raises(mxc.MxcUnavailable, match='alias in grant ancestor') as caught:
        policy(tmp_path)
    assert 'ancestor' in str(caught.value)


def test_unreadable_grant_ancestor_refuses_without_leaking(tmp_path, monkeypatch):
    """mxc.py:62 an unreadable ancestor refuses; the host error text stays out."""
    fake_lstat(monkeypatch, {str(tmp_path): PermissionError('host-secret-path')})
    with pytest.raises(mxc.MxcUnavailable, match='unreadable grant ancestor') as caught:
        policy(tmp_path)
    assert 'host-secret-path' not in str(caught.value)


def test_unreadable_grant_entry_refuses_without_leaking(tmp_path, monkeypatch):
    """mxc.py:83 an unreadable entry inside the grant refuses the whole grant."""
    nested = tmp_path / 'work' / 'nested'
    nested.mkdir(parents=True)
    (nested / 'file').write_text('synthetic')
    fake_lstat(monkeypatch, {str(nested / 'file'): PermissionError('host-secret-path')})
    monkeypatch.setattr(linkscan, 'multi_linked_files', lambda root: [])
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='unreadable grant') as caught:
        mxc.spawn(policy(tmp_path), exe='unused', job=object(), backend=fake)
    assert 'host-secret-path' not in str(caught.value)
    assert fake.calls == []


def test_unsupported_grant_object_refuses(tmp_path, monkeypatch):
    """mxc.py:81 a fifo or device inside the grant is not a grantable object."""
    nested = tmp_path / 'work' / 'nested'
    nested.mkdir(parents=True)
    (nested / 'pipe').write_text('synthetic')
    fake_lstat(monkeypatch, {str(nested / 'pipe'): mode(nested / 'pipe', stat.S_IFIFO)})
    with pytest.raises(mxc.MxcUnavailable, match='unsupported grant object'):
        policy(tmp_path)


def test_native_backend_refuses_without_the_module_flag(tmp_path, monkeypatch):
    """mxc.py:273 NativeMxc.spawn alone is not permission to launch."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', False)
    events = []

    class Transport:
        def stage_policy(self, raw):
            events.append('stage')

    backend = mxc.NativeMxc(Transport(), lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='disabled'):
        backend.spawn(policy(tmp_path), exe='unused', job=object())
    assert events == []


def test_native_requires_a_core_held_job_before_staging(tmp_path, monkeypatch):
    """mxc.py:278 no policy file is staged and no child made without the Job."""
    events = []

    class Transport:
        def stage_policy(self, raw):
            events.append('stage')
            return str(tmp_path / 'policy.json')

        def create_suspended(self, argv, *, policy):
            events.append('create')
            return object()

    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    backend = mxc.NativeMxc(Transport(), lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='Job required'):
        backend.spawn(policy(tmp_path), exe='unused', job=None)
    assert events == []


def test_failed_launcher_cleanup_failure_is_retained(tmp_path, monkeypatch):
    """mxc.py:296 when terminate() itself fails the child error is kept for quarantine."""
    events = []
    child = SimpleNamespace(pid=7, create_time=700,
                            terminate=lambda: (_ for _ in ()).throw(RuntimeError('handle held')),
                            wait=lambda timeout: events.append(('wait', timeout)))

    class Transport:
        def stage_policy(self, raw):
            return str(tmp_path / 'policy.json')

        def create_suspended(self, argv, *, policy):
            return child

        def assign_job(self, job, proc):
            raise mxc.MxcUnavailable('assign failed')

        def in_job(self, job, proc):
            events.append('membership')

        def resume(self, proc):
            events.append('resume')
            return 1

    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    backend = mxc.NativeMxc(Transport(), lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='assign failed') as caught:
        mxc.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                  job=object(), backend=backend, native_run=True)
    assert caught.value.child is child
    assert isinstance(caught.value.cleanup_error, RuntimeError)
    assert 'handle held' in str(caught.value.cleanup_error)
    assert events == []


def test_fake_backend_never_inherits_the_host_environment(tmp_path):
    """mxc.py:113 env is exactly the explicit list, sorted, never os.environ."""
    compiled = policy(tmp_path, env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'x',
                                     'ZED': 'z', 'ALPHA': 'a'})
    assert compiled.raw['process']['env'] == ['ALPHA=a', 'LOCALAPPDATA=x',
                                              'SYSTEMROOT=C:\\Windows', 'ZED=z']
    assert compiled.raw['process']['inheritDefaultEnv'] is False


def test_fake_backend_requires_job_and_records_nothing_for_a_crashed_launcher(tmp_path):
    """mxc.py:349,352 the fake still holds the Job and scripts launcher crashes."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='Job required'):
        fake.spawn(policy(tmp_path), exe='unused', job=None)
    assert fake.calls == [] and fake.events == []
    broken = mxc.FakeMxc([mxc.MxcUnavailable('launcher missing'), mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='launcher missing'):
        broken.spawn(policy(tmp_path), exe='unused', job=object())
    assert broken.calls == [] and broken.events == []
    assert broken.spawn(policy(tmp_path), exe='unused', job=object()).wait() == 0


def test_fake_process_terminate_marks_the_launcher_dead(tmp_path):
    """mxc.py:327,331,334 poll, returncode and terminate agree about liveness."""
    fake = mxc.FakeMxc([mxc.FakeOutcome(3)])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    assert proc.is_alive() is True and proc.poll() is None and proc.returncode is None
    proc.terminate()
    assert proc.is_alive() is False
    assert proc.wait() == 1 and proc.poll() == 1 and proc.returncode == 1


@pytest.mark.parametrize('changes', [
    {'user_sid': ''}, {'user_sid': None}, {'integrity': ''}, {'integrity': None},
    {'backend': 'appcontainer'}, {'backend': ''}, {'tier': 'base'}, {'tier': ''},
    {'create_time': '100000'}, {'create_time': 0}, {'create_time': None},
    {'pid': 1},
])
def test_identity_accepts_only_a_verified_container_report(tmp_path, changes):
    """mxc.py:243 every identity field is load-bearing for the separation claim."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    report = mxc.effective_identity(proc)
    proc.identity_reader = lambda p: replace(report, **changes)
    with pytest.raises(mxc.MxcUnavailable, match='unverified process identity'):
        mxc.effective_identity(proc)


def test_identity_refuses_an_unverified_appcontainer_claim(tmp_path):
    """mxc.py:243 an AppContainer claim needs an AC SID and a verified capability set."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    report = mxc.effective_identity(proc)
    proc.identity_reader = lambda p: replace(report, is_appcontainer=True,
                                             ac_sid='S-1-15-3-claimed',
                                             capability_sids=('S-1-15-3-claimed',))
    with pytest.raises(mxc.MxcUnavailable, match='unverified process identity'):
        mxc.effective_identity(proc)


@pytest.mark.parametrize('reader', [lambda p: None, lambda p: {}, lambda p: object()])
def test_identity_requires_an_identity_report_object(tmp_path, reader):
    """mxc.py:243 a launcher that cannot report identity is not verified."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    proc.identity_reader = reader
    with pytest.raises(mxc.MxcUnavailable, match='unverified process identity'):
        mxc.effective_identity(proc)


def test_dead_process_identity_refuses_after_terminate(tmp_path):
    """mxc.py:245 is_alive is re-read at identity time, not cached at spawn."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    mxc.effective_identity(proc)
    proc.terminate()
    with pytest.raises(mxc.MxcUnavailable, match='dead, reused or unverified'):
        mxc.effective_identity(proc)


def test_workspace_sequence_is_the_full_writable_inventory(tmp_path):
    """mxc.py:98 a sequence workspace is the whole writable set, never split per char."""
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    runtime = tmp_path / 'runtime'
    runtime.mkdir(exist_ok=True)
    both = policy(tmp_path, workspace=[work, runtime], cwd=work)
    assert both.raw['filesystem']['readwritePaths'] == [str(work), str(runtime)]
    single = policy(tmp_path, workspace=str(work), cwd=work)
    assert single.raw['filesystem']['readwritePaths'] == [str(work)]


@pytest.mark.parametrize('proxy', [None, 'http://127.0.0.1:18080', 'http://[::1]:18080',
                                   'http://127.0.0.1:18080/'])
def test_proxy_never_reopens_ui_or_telemetry(tmp_path, proxy):
    """mxc.py:133 the proxy branch keeps UI disabled and telemetry off."""
    raw = policy(tmp_path, proxy_url=proxy).raw
    assert raw['ui'] == {'disable': True, 'clipboard': 'none', 'injection': False}
    assert raw['telemetry'] == {'enabled': False}
    assert raw['network']['egress'] == {'default': 'deny'}


@pytest.mark.parametrize('proxy', ['http://127.0.0.1:18080/example', 'http://127.0.0.1:70000',
                                   'http:///18080', 'not-a-url', '', 'http://127.0.0.1:18080:80'])
def test_compile_rejects_any_proxy_that_is_not_a_loopback_http_endpoint(tmp_path, proxy):
    """mxc.py:126 proxy must be an explicit loopback HTTP endpoint at compile time."""
    with pytest.raises(mxc.MxcUnavailable, match='loopback HTTP endpoint'):
        policy(tmp_path, proxy_url=proxy)


BS = chr(92)


@pytest.mark.skipif(os.name != 'nt', reason='Windows path forms')
@pytest.mark.parametrize('prefix', [BS * 2 + '?' + BS, BS * 2 + '.' + BS])
def test_a_path_form_commonpath_cannot_compare_is_refused_not_skipped(tmp_path, prefix):
    """T-661#5: commonpath raises across extended-length forms; that used to read as 'no
    overlap', so a denied path inside the workspace slipped past the overlap gate."""
    work = tmp_path / 'work'
    work.mkdir()
    with pytest.raises(mxc.MxcUnavailable, match='plain drive paths'):
        policy(tmp_path, denied=[prefix + str(work / 'secrets')])
    with pytest.raises(mxc.MxcUnavailable, match='plain drive paths'):
        policy(tmp_path, readonly=[BS * 2 + 'localhost' + BS + 'C$' + BS + 'x'])


def _staging_transport(events, resume=1):
    child = SimpleNamespace(terminate=lambda: events.append('terminate'),
                            wait=lambda timeout: None)

    class Transport:
        def stage_policy(self, raw):
            events.append('stage')
            return 'unused'

        def create_suspended(self, argv, *, policy):
            return child

        def assign_job(self, job, proc):
            pass

        def in_job(self, job, proc):
            return True

        def resume(self, proc):
            return resume

    return Transport()


def test_a_relative_launcher_is_refused_before_a_policy_is_staged(tmp_path, monkeypatch):
    """T-661#8: the policy lease was staged first and leaked when the launcher path raised."""
    events = []
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    backend = mxc.NativeMxc(_staging_transport(events), lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='absolute'):
        backend.spawn(policy(tmp_path), exe='wxc-exec.exe', job=object())
    assert events == []


def test_the_staged_policy_path_reaches_the_transport_untouched(tmp_path, monkeypatch):
    """T-661#8: normalising the transport's own lease key would desync it from its table."""
    staged = str(tmp_path / 'a' / '..' / 'policy.json')
    seen = []
    transport = _staging_transport([])
    transport.stage_policy = lambda raw: staged
    create = transport.create_suspended
    transport.create_suspended = lambda argv, *, policy: seen.append(argv[-1]) or create(
        argv, policy=policy)
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    mxc.NativeMxc(transport, lambda raw: True).spawn(
        policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'), job=object())
    assert seen == [staged]


@pytest.mark.parametrize('answer', [True, 1.0])
def test_a_resume_answer_must_be_the_integer_one(tmp_path, monkeypatch, answer):
    """T-661#16: `!= 1` accepted True and 1.0 from a transport that is not the native one."""
    events = []
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    backend = mxc.NativeMxc(_staging_transport(events, resume=answer), lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='exactly once'):
        backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'), job=object())
    assert events[-1] == 'terminate'


def test_a_missing_workspace_is_a_refusal_not_a_type_error(tmp_path):
    """T-661#17: tuple(None) escaped as TypeError, past callers that catch MxcUnavailable."""
    with pytest.raises(mxc.MxcUnavailable):
        policy(tmp_path, workspace=None)
    with pytest.raises(mxc.MxcUnavailable):
        policy(tmp_path, cwd=None)


def test_a_schema_validator_that_raises_is_a_refusal(tmp_path, monkeypatch):
    """T-661#17: a raising validator escaped isolation's `except MxcUnavailable`."""
    def broken(raw):
        raise RuntimeError('schema artifact unreadable')

    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    with pytest.raises(mxc.MxcUnavailable, match='schema validation'):
        mxc.NativeMxc(_staging_transport([]), broken).spawn(
            policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'), job=object())
