"""T-1384: claude_sessions/launch.py lines 101-169 at tip 73ad7a90 (session id
refusal, exe lookup order, provider record refusal, choice to flag mapping,
effort and env gating). Candidate probes, not measured coverage.

Branches: 109-110 a bad id is refused before get_claude_exe; 105-110 an empty
named resume is refused; 166-169 an unrecorded provider refuses the launch;
164-165 no project folder skips the provider record; 117-125 choice mapping;
127-128 and 96-99 effort and env only when set.
"""

from types import SimpleNamespace

import pytest

from claude_sessions import config, harnesses, launch, omniroute, sessions


@pytest.fixture
def seams(monkeypatch, tmp_path):
    s = SimpleNamespace(profiles={}, saved=[], save_result=True, exe_calls=0,
                        settings={'launch_fallback_models': []}, acct=str(tmp_path / 'acct'))

    def get_claude_exe():
        s.exe_calls += 1
        return 'C:/fake/claude.exe'

    def provider_profile(pid, st=None):
        return s.profiles.get(pid)

    def prepare_launch(model, prof, ctx_bytes=0):
        return {'ANTHROPIC_BASE_URL': 'http://127.0.0.1:9'}, ''

    def save_session_provider(proj, sid, pid):
        s.saved.append((proj, sid, pid))
        return s.save_result

    monkeypatch.setattr(launch, 'get_claude_exe', get_claude_exe)
    monkeypatch.setattr(launch, 'load_settings', lambda: s.settings)
    monkeypatch.setattr(config, 'provider_profile', provider_profile)
    monkeypatch.setattr(config, 'effective_perm', lambda perm, model='', routed='': perm)
    monkeypatch.setattr(config, 'otel_env', lambda st=None: {})
    monkeypatch.setattr(config, 'account_env', lambda cfgdir=None, harness=None: {})
    monkeypatch.setattr(omniroute, 'prepare_launch', prepare_launch)
    monkeypatch.setattr(sessions, 'save_session_provider', save_session_provider)
    monkeypatch.setattr(sessions, 'read_extra_paths', lambda p: [])
    monkeypatch.setattr(sessions, 'load_add_dirs', lambda p: [])
    monkeypatch.setattr(harnesses, 'of', lambda cfgdir=None: harnesses.descriptor())
    return s


def opts(acct, **kw):
    base = {'cfgdir': acct, 'model': '', 'effort': '', 'perm': '', 'name': '', 'worktree': '',
            'agent': '', 'prompt': '', 'provider': '', 'provider_model': ''}
    base.update(kw)
    return base


@pytest.mark.parametrize('choice', [
    'resume:bad id',
    'resume:bad/id',
    'resume-named::bad id::Name',
    'fork:bad;id',
])
def test_bad_session_id_refused_before_exe_lookup(seams, choice):
    with pytest.raises(RuntimeError, match='not a plain session'):
        launch.build_launch_command('p-x', 'p-x', choice, opts(seams.acct))
    assert seams.exe_calls == 0


@pytest.mark.parametrize('choice', ['resume:', 'resume-named::', 'resume-named::::Name', 'fork:'])
def test_empty_session_id_refused_not_passed_as_empty_resume(seams, choice):
    with pytest.raises(RuntimeError, match='not a plain session'):
        launch.build_launch_command('p-x', 'p-x', choice, opts(seams.acct))
    assert seams.exe_calls == 0


def test_unrecorded_provider_refuses_launch(seams):
    seams.profiles = {'p1': {'id': 'p1', 'model': 'm'}}
    seams.save_result = False
    with pytest.raises(RuntimeError, match='could not record which provider'):
        launch.build_launch_command('p-x', 'p-x', 'new', opts(seams.acct, provider='p1'))
    assert len(seams.saved) == 1 and seams.saved[0][2] == 'p1'


def test_no_project_folder_skips_provider_record(seams):
    seams.profiles = {'p1': {'id': 'p1', 'model': 'm'}}
    args, _env, proj = launch.build_launch_command('p-x', '', 'new', opts(seams.acct, provider='p1'))
    assert proj is None
    assert seams.saved == []
    assert args[args.index('--session-id') + 1]


@pytest.mark.parametrize('choice, expected', [
    ('continue', ['-c']),
    ('resume:abc', ['-r', 'abc']),
    ('resume-named::abc::My::Name', ['-r', 'abc']),
    ('fork:abc', ['-r', 'abc', '--fork-session']),
])
def test_choice_flag_mapping(seams, choice, expected):
    args, _env, _ = launch.build_launch_command('p-x', 'p-x', choice, opts(seams.acct))
    assert args[1:1 + len(expected)] == expected


def test_effort_and_env_only_when_set(seams):
    args, env, _ = launch.build_launch_command('p-x', 'p-x', 'new', opts(seams.acct))
    assert '--effort' not in args
    assert 'MAX_THINKING_TOKENS' not in env
    assert 'CLAUDE_CODE_SUBAGENT_MODEL' not in env

    args, env, _ = launch.build_launch_command(
        'p-x', 'p-x', 'new',
        opts(seams.acct, effort='high', max_thinking='8000', subagent_model='m-sub'))
    assert args[args.index('--effort') + 1] == 'high'
    assert env['MAX_THINKING_TOKENS'] == '8000'
    assert env['CLAUDE_CODE_SUBAGENT_MODEL'] == 'm-sub'
