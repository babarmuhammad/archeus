"""T-1279: claude_sessions/launch.py lines 105-199 at tip 6bbd3b44 (argv
boundaries, provider binding and launch intent in build_launch_command).
Selected probes, not measured coverage.

Selected branches: 121 provider id resolves from the picker, never the active
profile; 134 provider model wins, one --model; 155 new session id and provider
record; 155 provider-record write result; 163 permission and routed marker;
109 resume id beginning with a dash; 191 add-dir argv shape; 198 opening prompt
beginning with a flag; 182-184 name and worktree flags; 170-172 fallback chain.
"""

import os
import uuid
from types import SimpleNamespace

import pytest

from claude_sessions import config, harnesses, launch, omniroute, sessions, store


@pytest.fixture
def seams(monkeypatch, tmp_path):
    s = SimpleNamespace(profiles={}, prepared=[], saved=[], save_result=True, perm_calls=[],
                        settings={'launch_fallback_models': []}, acct=str(tmp_path / 'acct'))

    def provider_profile(pid, st=None):
        return s.profiles.get(pid)

    def prepare_launch(model, prof, ctx_bytes=0):
        s.prepared.append((model, prof['id']))
        return {'ANTHROPIC_BASE_URL': 'http://127.0.0.1:9'}, ''

    def save_session_provider(proj, sid, pid):
        s.saved.append((proj, sid, pid))
        return s.save_result

    def effective_perm(perm, model='', routed=''):
        s.perm_calls.append((perm, model, routed))
        return perm

    monkeypatch.setattr(config, 'provider_profile', provider_profile)
    monkeypatch.setattr(config, 'effective_perm', effective_perm)
    monkeypatch.setattr(config, 'otel_env', lambda st=None: {})
    monkeypatch.setattr(omniroute, 'prepare_launch', prepare_launch)
    monkeypatch.setattr(sessions, 'save_session_provider', save_session_provider)
    monkeypatch.setattr(sessions, 'read_extra_paths', lambda p: [])
    monkeypatch.setattr(sessions, 'load_add_dirs', lambda p: [])
    monkeypatch.setattr(launch, 'load_settings', lambda: s.settings)
    monkeypatch.setattr(launch, 'get_claude_exe', lambda: 'C:/fake/claude.exe')
    monkeypatch.setattr(config, 'account_env', lambda cfgdir=None, harness=None: {})
    monkeypatch.setattr(harnesses, 'of', lambda cfgdir=None: harnesses.descriptor())
    return s


def opts(acct, **kw):
    base = {'cfgdir': acct, 'model': '', 'effort': '', 'perm': '', 'name': '', 'worktree': '',
            'agent': '', 'prompt': '', 'provider': '', 'provider_model': ''}
    base.update(kw)
    return base


def build(s, choice, **kw):
    return launch.build_launch_command('p-x', 'p-x', choice, opts(s.acct, **kw))


def tail(args, flag):
    return args[args.index(flag):]


def test_unknown_provider_id_never_borrows_the_active_profile(seams):
    seams.profiles = {'active': {'id': 'active', 'model': 'm-active'}}
    args, env, _ = build(seams, 'new', provider='gone', model='claude-opus-5')
    assert seams.prepared == []
    assert 'ANTHROPIC_BASE_URL' not in env
    assert args[args.index('--model') + 1] == 'claude-opus-5'


def test_provider_model_wins_and_emits_exactly_one_model_flag(seams):
    seams.profiles = {'p1': {'id': 'p1', 'model': 'prov-model'}}
    args, _env, _ = build(seams, 'new', provider='p1', model='claude-opus-5')
    assert args.count('--model') == 1
    assert args[args.index('--model') + 1] == 'prov-model'

    args, _env, _ = build(seams, 'new', provider='p1', model='claude-opus-5', provider_model='picked')
    assert args.count('--model') == 1
    assert args[args.index('--model') + 1] == 'picked'


def test_session_id_and_provider_record_follow_choice(seams, monkeypatch):
    seams.profiles = {'p1': {'id': 'p1', 'model': 'm'}}
    monkeypatch.setattr(uuid, 'uuid4', lambda: uuid.UUID(int=7))
    proj = store.project_folder(seams.acct, 'p-x')
    sid = str(uuid.UUID(int=7))

    args, _env, _ = build(seams, 'new', provider='p1')
    assert tail(args, '--session-id')[:2] == ['--session-id', sid]
    assert seams.saved == [(proj, sid, 'p1')]

    seams.saved.clear()
    args, _env, _ = build(seams, 'resume:abc', provider='p1')
    assert '--session-id' not in args
    assert args[args.index('-r'):args.index('-r') + 2] == ['-r', 'abc']
    assert seams.saved == [(proj, 'abc', 'p1')]

    seams.saved.clear()
    args, _env, _ = build(seams, 'fork:abc', provider='p1')
    assert args[args.index('-r'):args.index('-r') + 3] == ['-r', 'abc', '--fork-session']
    assert seams.saved == []

    args, _env, _ = build(seams, 'continue', provider='p1')
    assert seams.saved == []


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/launch.py:155-156 discards save_session_provider's False "
    "(sessions.py:420-421 returns False when the record is unreadable) and returns an "
    "argv that claims a recorded provider binding"))
def test_failed_provider_record_write_is_not_silent(seams, monkeypatch):
    seams.profiles = {'p1': {'id': 'p1', 'model': 'm'}}
    seams.save_result = False
    with pytest.raises(RuntimeError):
        build(seams, 'resume:abc', provider='p1')


def test_permission_and_routed_marker_come_from_the_actual_model(seams):
    seams.profiles = {'p1': {'id': 'p1', 'model': 'prov-model'}}
    args, _env, _ = build(seams, 'new', provider='p1', model='claude-opus-5', perm='plan')
    assert seams.perm_calls[-1] == ('plan', 'prov-model', 'prov-model')
    assert tail(args, '--permission-mode')[:2] == ['--permission-mode', 'plan']

    build(seams, 'new', model='claude-opus-5', perm='auto')
    assert seams.perm_calls[-1] == ('auto', 'claude-opus-5', '')


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/launch.py:109 and :150 put a resume id that begins with '-' "
    "straight after -r; no refusal exists, so the CLI reads it as an option"))
def test_resume_id_beginning_with_dash_is_refused(seams):
    with pytest.raises((ValueError, RuntimeError)):
        build(seams, 'resume:-x')


def test_resume_argv_keeps_the_id_as_one_element(seams):
    args, _env, _ = build(seams, 'resume:abc-123')
    assert args[args.index('-r'):args.index('-r') + 2] == ['-r', 'abc-123']


def test_add_dir_values_stay_separate_argv_elements(seams):
    seams.settings = dict(seams.settings)
    args, _env, _ = build(seams, 'new')
    assert '--add-dir' not in args
    args, _env, _ = launch.build_launch_command(
        'p-x', 'p-x', 'new', opts(seams.acct, add_dirs=['C:/a b/x', '-evil']))
    assert tail(args, '--add-dir') == ['--add-dir', 'C:/a b/x', '-evil']


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/launch.py:197-198 appends an opening prompt beginning with '--' "
    "as a bare argv element: no '--' delimiter and no refusal, so the CLI reads "
    "--dangerously-skip-permissions as a flag"))
def test_opening_prompt_that_looks_like_a_flag_is_not_an_option(seams):
    prompt = '--dangerously-skip-permissions'
    try:
        args, _env, _ = build(seams, 'new', prompt=prompt)
    except (ValueError, RuntimeError):
        return
    assert args[-2:] == ['--', prompt]


def test_plain_opening_prompt_stays_the_last_argument(seams):
    args, _env, _ = build(seams, 'new', prompt='check CI')
    assert args[-1] == 'check CI'


def test_name_and_worktree_flags_only_for_new_sessions(seams):
    args, _env, _ = build(seams, 'new', name='n', worktree='*')
    assert tail(args, '-n')[:2] == ['-n', 'n']
    assert tail(args, '-w') == ['-w']

    args, _env, _ = build(seams, 'new', worktree='feat/x y')
    assert tail(args, '-w') == ['-w', 'feat/x y']

    args, _env, _ = build(seams, 'continue', name='n', worktree='feat/x')
    assert '-n' not in args and '-w' not in args


def test_fallback_chain_drops_empty_entries_and_stays_one_value(seams):
    seams.settings['launch_fallback_models'] = ['m1', '', 'm2&calc;rm']
    args, _env, _ = build(seams, 'new')
    assert tail(args, '--fallback-model') == ['--fallback-model', 'm1,m2&calc;rm']

    seams.settings['launch_fallback_models'] = ['']
    args, _env, _ = build(seams, 'new')
    assert '--fallback-model' not in args
