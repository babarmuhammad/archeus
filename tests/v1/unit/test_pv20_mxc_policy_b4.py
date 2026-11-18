"""PV-20 B4: the owner-approved UI posture, the proxy route with its capability set, the
explicit environment and the launch inputs, all still closed and validated.

Assumption recorded with OD-1 (completion plan default a): the desktop is opened only by the
named posture `mxc.UI_CODE_CHANGE`, with the clipboard and injection still closed, and only
`MxcLaunch`'s caller can name it for a code_change execution. Fakes only: nothing here
creates a container, starts a process or calls a native API."""

import copy
import os

import pytest

from archeus.node import local, mxc, staging

ERROR = mxc.MxcUnavailable
PROXY = 'http://127.0.0.1:18080'
ENV = {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\pv20\\home\\AppData\\Local'}


def compile_of(tmp_path, **changes):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    args = dict(workspace=str(work), cwd=str(work), command_line='cmd.exe /d /c echo fixture',
                env=dict(ENV), timeout_ms=1000)
    args.update(changes)
    return mxc.compile_policy(**args)


def refused(tmp_path, match, **changes):
    with pytest.raises(ERROR, match=match):
        compile_of(tmp_path, **changes)


# ── the UI posture ──


def test_the_default_posture_is_blocked(tmp_path):
    assert compile_of(tmp_path).raw['ui'] == {'disable': True, 'clipboard': 'none',
                                              'injection': False}


def test_the_code_change_posture_opens_only_the_ui_subsystem(tmp_path):
    blocked = compile_of(tmp_path).raw
    opened = compile_of(tmp_path, ui=mxc.UI_CODE_CHANGE).raw
    assert opened['ui'] == {'disable': False, 'clipboard': 'none', 'injection': False}
    opened['ui'] = blocked['ui']
    assert opened == blocked


def test_the_code_change_posture_does_not_touch_the_network_or_the_grants(tmp_path):
    raw = compile_of(tmp_path, ui=mxc.UI_CODE_CHANGE).raw
    assert raw['network'] == {'egress': {'default': 'deny'},
                              'ingress': {'default': 'deny', 'hostLoopback': 'deny'}}
    assert 'runtimeConfig' not in raw and 'processContainer' not in raw
    assert raw['telemetry'] == {'enabled': False}


@pytest.mark.parametrize('ui', [True, 1, 0, None, 'blocked', 'CODE_CHANGE', 'code_change ',
                                'code-change', ' code_change', '', ['code_change'], b'code_change',
                                1.0, 'true', 'all', {'disable': False}])
def test_only_the_named_posture_and_false_compile(tmp_path, ui):
    refused(tmp_path, 'unsupported UI or egress policy', ui=ui)


def test_the_posture_is_no_licence_for_egress(tmp_path):
    refused(tmp_path, 'unsupported UI or egress policy', ui=mxc.UI_CODE_CHANGE, egress='allow')


@pytest.mark.parametrize('ui', [False, mxc.UI_CODE_CHANGE])
def test_both_postures_validate_and_a_mutated_clipboard_or_injection_does_not(tmp_path, ui):
    policy = compile_of(tmp_path, ui=ui)
    mxc.validate_policy(policy)
    for field, value in (('clipboard', 'read'), ('clipboard', 'write'), ('injection', True),
                         ('allowWindows', True)):
        bad = copy.deepcopy(policy.raw)
        bad['ui'][field] = value
        with pytest.raises(ERROR, match='unsafe UI or telemetry'):
            mxc.validate_policy(_loose(bad))


def _loose(raw):
    policy = object.__new__(mxc.MxcPolicy)
    object.__setattr__(policy, 'raw', raw)
    return policy


@pytest.mark.parametrize('disable', ['false', 0, 1, None, 'no', [], {}])
def test_a_ui_disable_that_is_not_a_boolean_does_not_validate(tmp_path, disable):
    raw = copy.deepcopy(compile_of(tmp_path).raw)
    raw['ui']['disable'] = disable
    with pytest.raises(ERROR, match='unsafe UI or telemetry'):
        mxc.validate_policy(_loose(raw))


def test_the_posture_and_a_proxy_compose_and_both_validate(tmp_path):
    raw = compile_of(tmp_path, ui=mxc.UI_CODE_CHANGE, proxy_url=PROXY).raw
    assert raw['ui']['disable'] is False
    assert raw['runtimeConfig'] == {'networkProxy': PROXY}
    assert raw['network']['egress'] == {'default': 'deny'}


# ── the capability set ──


def test_a_proxy_carries_its_reviewed_capability_by_default(tmp_path):
    raw = compile_of(tmp_path, proxy_url=PROXY).raw
    assert raw['processContainer'] == {'capabilities': ['internetClient']}


def test_the_reviewed_set_can_be_named_and_is_the_same_policy(tmp_path):
    named = compile_of(tmp_path, proxy_url=PROXY, capabilities=('internetClient',)).raw
    assert named == compile_of(tmp_path, proxy_url=PROXY).raw
    assert named == compile_of(tmp_path, proxy_url=PROXY, capabilities=['internetClient']).raw


@pytest.mark.parametrize('caps', [('internetClient', 'runAllTasks'), ('runAllTasks',),
                                  ('internetClientServer',), ('InternetClient',),
                                  ('internetClient', 'internetClient'), (), ('',), (None,)])
def test_a_capability_outside_the_reviewed_set_is_refused(tmp_path, caps):
    refused(tmp_path, 'capabilities', proxy_url=PROXY, capabilities=caps)


@pytest.mark.parametrize('caps', ['internetClient', b'internetClient', 5, True, object()])
def test_capabilities_that_are_not_a_list_of_names_are_refused(tmp_path, caps):
    refused(tmp_path, 'capabilities', proxy_url=PROXY, capabilities=caps)


@pytest.mark.parametrize('caps', [('internetClient',), ['internetClient']])
def test_a_capability_with_no_proxy_route_is_refused(tmp_path, caps):
    refused(tmp_path, 'only with a proxy', capabilities=caps)


def test_a_proxy_with_an_empty_capability_set_is_refused(tmp_path):
    refused(tmp_path, 'only with a proxy', proxy_url=PROXY, capabilities=())


def test_no_proxy_means_no_container_section(tmp_path):
    assert 'processContainer' not in compile_of(tmp_path, capabilities=None).raw


@pytest.mark.parametrize('mutate,message', [
    (lambda raw: raw['processContainer'].update(capabilities=[]), 'invalid proxy policy'),
    (lambda raw: raw['processContainer'].update(capabilities=['internetClient', 'x']),
     'invalid proxy policy'),
    (lambda raw: raw['processContainer'].update(capabilities=['x']), 'invalid proxy policy'),
    (lambda raw: raw['processContainer'].update(capabilities=['internetClient'] * 2),
     'invalid proxy policy'),
    (lambda raw: raw['processContainer'].update(capabilities='internetClient'),
     'invalid proxy policy'),
    (lambda raw: raw['processContainer'].update(leastPrivilege=True), 'invalid proxy policy'),
    (lambda raw: raw.update(processContainer={}), 'invalid proxy policy'),
])
def test_a_mutated_capability_section_does_not_validate(tmp_path, mutate, message):
    raw = copy.deepcopy(compile_of(tmp_path, proxy_url=PROXY).raw)
    mutate(raw)
    with pytest.raises(ERROR, match=message):
        mxc.validate_policy(_loose(raw))


def test_a_capability_section_with_no_proxy_does_not_validate(tmp_path):
    raw = copy.deepcopy(compile_of(tmp_path).raw)
    raw['processContainer'] = {'capabilities': ['internetClient']}
    with pytest.raises(ERROR, match='unknown or missing policy fields'):
        mxc.validate_policy(_loose(raw))


# ── MxcLaunch passes the posture, the route and the set, and nothing else ──


class Backend(mxc.FakeMxc):
    compile_policy = staticmethod(mxc.compile_policy)


@pytest.fixture
def launch_args(tmp_path):
    work, tools = tmp_path / 'work', tmp_path / 'tools'
    work.mkdir()
    tools.mkdir()
    return dict(sdk_root=tmp_path, pins={'package.json': 'a' * 64}, outcome=lambda p: 0,
                workspace=str(work), readonly=(str(tools),), cwd=str(work),
                command_line='agent.exe', env=dict(ENV), timeout_ms=1000)


@pytest.fixture(autouse=True)
def sdk_verified(monkeypatch):
    monkeypatch.setattr(staging, 'verify_mxc', lambda root, *, pins: 'wxc-exec.exe')
    monkeypatch.setattr(staging, 'scan_grants', lambda grants: None)


def test_a_launch_defaults_to_the_closed_posture(launch_args):
    raw = local.MxcLaunch(backend=Backend(), **launch_args).policy.raw
    assert raw['ui']['disable'] is True
    assert 'runtimeConfig' not in raw and 'processContainer' not in raw


def test_a_launch_carries_the_named_posture_route_and_capabilities(launch_args):
    raw = local.MxcLaunch(backend=Backend(), ui=mxc.UI_CODE_CHANGE, proxy_url=PROXY,
                          capabilities=('internetClient',), **launch_args).policy.raw
    assert raw['ui']['disable'] is False
    assert raw['runtimeConfig'] == {'networkProxy': PROXY}
    assert raw['processContainer'] == {'capabilities': ['internetClient']}


@pytest.mark.parametrize('extra', [
    dict(ui=True), dict(ui='all'), dict(proxy_url='http://10.0.0.1:8080'),
    dict(proxy_url='http://localhost:18080'), dict(proxy_url='https://127.0.0.1:18080'),
    dict(capabilities=('internetClient',)), dict(proxy_url=PROXY, capabilities=('runAllTasks',)),
])
def test_a_launch_refuses_what_the_compiler_refuses(launch_args, extra):
    with pytest.raises(ERROR):
        local.MxcLaunch(backend=Backend(), **extra, **launch_args)


def test_a_launch_with_no_pins_reads_the_committed_ones_and_refuses_while_unset(launch_args):
    launch_args.pop('pins')
    with pytest.raises(staging.StageError):
        local.MxcLaunch(backend=Backend(), **launch_args)


# ── the explicit environment ──

HOME = 'C:\\pv20\\run\\home'
RUN = 'C:\\pv20\\run'
TOOLS = 'C:\\pv20\\tools'


def isolated():
    """What base._isolated_env builds, in its own spellings."""
    return {'TEMP': RUN + '\\tmp', 'TMP': RUN + '\\tmp', 'CLAUDE_CONFIG_DIR': RUN + '\\config',
            'USERPROFILE': HOME, 'HOME': HOME, 'APPDATA': HOME + '\\AppData\\Roaming',
            'LOCALAPPDATA': HOME + '\\AppData\\Local', 'SystemRoot': 'C:\\Windows',
            'windir': 'C:\\Windows', 'ComSpec': 'C:\\Windows\\System32\\cmd.exe',
            'PATH': 'C:\\Users\\someone\\bin;C:\\Python', 'ARCHEUS_EXECUTION_ID': 'e1'}


def env_of(env=None, *, path=(TOOLS,), writable=(RUN,), readonly=(TOOLS,)):
    return local.mxc_env(isolated() if env is None else env, writable=writable,
                         readonly=readonly, path=path)


@pytest.mark.skipif(os.name != 'nt', reason='drive paths')
class TestMxcEnv:
    def test_it_keeps_the_derived_values_and_replaces_path(self):
        out = env_of()
        assert out['PATH'] == TOOLS
        assert out['SystemRoot'] == 'C:\\Windows' and out['ARCHEUS_EXECUTION_ID'] == 'e1'
        assert out['LOCALAPPDATA'] == isolated()['LOCALAPPDATA']
        assert set(out) == set(isolated())

    def test_the_host_path_never_reaches_the_container(self):
        assert 'someone' not in env_of()['PATH']

    def test_it_feeds_the_compiler(self, tmp_path):
        env = env_of()
        policy = compile_of(tmp_path, env=env)
        assert 'PATH=%s' % TOOLS in policy.raw['process']['env']

    def test_a_system32_entry_is_allowed_beside_the_staged_tools(self):
        assert env_of(path=(TOOLS, 'C:\\Windows\\System32'))['PATH'] == \
            TOOLS + os.pathsep + 'C:\\Windows\\System32'

    @pytest.mark.parametrize('name', ['TEMP', 'TMP', 'USERPROFILE', 'HOME', 'APPDATA',
                                      'LOCALAPPDATA', 'CLAUDE_CONFIG_DIR'])
    def test_a_folder_variable_outside_the_execution_folders_is_refused(self, name):
        env = isolated()
        env[name] = 'C:\\Users\\someone\\AppData\\Local'
        with pytest.raises(staging.StageError, match=name):
            env_of(env)

    @pytest.mark.parametrize('value', ['relative', '', 'C:rel', '\\\\host\\share\\x', None])
    def test_a_folder_variable_that_is_not_an_absolute_drive_path_is_refused(self, value):
        env = isolated()
        env['home'] = value
        del env['HOME']
        with pytest.raises(staging.StageError):
            env_of(env)

    def test_a_folder_variable_in_any_case_is_checked(self):
        env = isolated()
        env['localappdata'] = 'C:\\elsewhere'
        del env['LOCALAPPDATA']
        with pytest.raises(staging.StageError, match='localappdata'):
            env_of(env)

    def test_a_sibling_prefix_is_not_inside(self):
        env = isolated()
        env['TEMP'] = RUN + '-other\\tmp'
        with pytest.raises(staging.StageError):
            env_of(env)

    @pytest.mark.parametrize('system', [None, '', 'Windows', 'C:Windows'])
    def test_an_absent_or_relative_system_root_is_refused(self, system):
        env = isolated()
        del env['SystemRoot']
        if system is not None:
            env['SystemRoot'] = system
        with pytest.raises(staging.StageError, match='SYSTEMROOT'):
            env_of(env)

    @pytest.mark.parametrize('path', [(), ('C:\\Users\\someone\\bin',), (TOOLS, 'C:\\Python'),
                                      (RUN + '\\work',), (RUN,), ('relative',), ('',),
                                      (TOOLS + '-x',)])
    def test_a_path_entry_that_is_not_staged_read_only_or_system_is_refused(self, path):
        with pytest.raises(staging.StageError, match='PATH'):
            env_of(path=path)

    def test_a_writable_folder_inside_a_read_only_grant_is_no_path_entry(self):
        with pytest.raises(staging.StageError, match='PATH'):
            env_of(path=(TOOLS + '\\w',), writable=(RUN, TOOLS + '\\w'), readonly=(TOOLS,))

    def test_a_lowercase_path_is_dropped_too(self):
        env = isolated()
        env['Path'] = env.pop('PATH')
        out = env_of(env)
        assert out['PATH'] == TOOLS and 'Path' not in out

    def test_the_input_is_not_changed(self):
        env = isolated()
        before = dict(env)
        env_of(env)
        assert env == before
