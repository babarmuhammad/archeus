import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from harness import Sandbox

from claude_sessions import main as main_mod


OPTS0 = {'effort': '', 'model': '', 'perm': '', 'name': '', 'worktree': '', 'agent': ''}


def captured_launch(monkeypatch, sb, choice, opts, folder_files=None,
                    encoded='X--work-proj'):
    """Run _direct_launch with subprocess.call captured. Returns (args, kwargs)."""
    calls = []
    import subprocess

    def fake_call(*a, **kw):
        calls.append((a, kw))
        return 0
    monkeypatch.setattr(subprocess, 'call', fake_call)
    monkeypatch.setattr(main_mod, 'get_claude_exe', lambda: r'C:\fake\claude.exe')
    folder = sb.projects / encoded
    folder.mkdir(exist_ok=True)
    for fname, content in (folder_files or {}).items():
        (folder / fname).write_text(content, encoding='utf-8')
    main_mod._direct_launch(str(sb.root), encoded, choice, dict(OPTS0, **opts))
    return calls[0]


def argv_of(call):
    return call[0][0]


def test_direct_launch_new_plain(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'new', {})
    argv = argv_of(call)
    # a new session's id is archeus's to choose, so the backend it was launched
    # on can be written down before Claude Code has written a line
    assert argv[0] == r'C:\fake\claude.exe'
    assert argv[1] == '--session-id' and len(argv) == 3
    uuid.UUID(argv[2])                      # raises if it is not one


def test_direct_launch_resume(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'resume:abc-123', {})
    assert argv_of(call)[1:3] == ['-r', 'abc-123']


def test_direct_launch_resume_named(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'resume-named::abc::My Name', {})
    assert argv_of(call)[1:3] == ['-r', 'abc']


def test_direct_launch_fork(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'fork:abc', {})
    argv = argv_of(call)
    assert argv[1:3] == ['-r', 'abc'] and '--fork-session' in argv


def test_direct_launch_continue(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'continue', {})
    assert argv_of(call)[1] == '-c'


def test_direct_launch_agent(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'resume:abc', {'agent': 'reviewer'})
    argv = argv_of(call)
    assert '--agent' in argv and argv[argv.index('--agent') + 1] == 'reviewer'


def test_direct_launch_all_flags(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    dir1 = str(sb.root)   # exists
    call = captured_launch(
        monkeypatch, sb, 'new',
        {'effort': 'high', 'model': 'claude-sonnet-4-6', 'perm': 'plan',
         'name': 'Sess', 'worktree': '*'},
        folder_files={'system-prompt.txt': 'sp', 'add-dirs.txt': dir1})
    argv = argv_of(call)
    s = ' '.join(argv)
    assert '--effort high' in s
    assert '--model claude-sonnet-4-6' in s
    assert '--permission-mode plan' in s
    assert '-n Sess' in s
    assert '-w' in argv
    assert '--system-prompt-file' in s
    assert '--add-dir' in s and dir1 in argv


def test_auto_permission_mode_is_passed(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'new',
                           {'perm': 'auto', 'model': 'claude-sonnet-5'})
    assert '--permission-mode auto' in ' '.join(argv_of(call))


def test_manual_is_expressible(monkeypatch, tmp_path):
    """'' means "pass no flag", which on a Pro/Max plan inherits Claude Code's
    own auto default — so forcing manual needs the literal value 'default'."""
    sb = Sandbox(monkeypatch, tmp_path)
    argv = argv_of(captured_launch(monkeypatch, sb, 'new', {'perm': 'default'}))
    assert '--permission-mode default' in ' '.join(argv)
    argv = argv_of(captured_launch(monkeypatch, sb, 'new', {'perm': ''}))
    assert '--permission-mode' not in argv


def _stub_provider(monkeypatch, **over):
    """prepare_launch() probes (and would start) the real OmniRoute daemon —
    a blocking network call that has no place in a launch-assembly test.

    Also puts one profile where build_launch_command will resolve it: `provider`
    is a profile ID now, so a launch naming one that does not exist is correctly
    treated as Anthropic and proves nothing."""
    from claude_sessions import config as _cfg, main as _main, omniroute
    monkeypatch.setattr(omniroute, 'prepare_launch', lambda m, prof=None, **kw: ({}, ''))
    prof = _cfg.new_profile(id='p1', name='OmniRoute', kind='omniroute',
                            base_url='http://localhost:20128', model='auto/coding',
                            port=20129, **over)
    s = dict(_cfg._DEFAULT_SETTINGS, providers=[prof], provider_active='p1')
    monkeypatch.setattr(_main, 'load_settings', lambda: dict(s))
    return prof


def test_auto_is_dropped_for_a_routed_provider(monkeypatch, tmp_path):
    """The classifier is a separate model request and would follow
    ANTHROPIC_BASE_URL to the free-tier proxy, which does not serve it."""
    sb = Sandbox(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    call = captured_launch(monkeypatch, sb, 'new',
                           {'perm': 'auto', 'provider': 'p1',
                            'provider_model': 'auto/coding'})
    argv = argv_of(call)
    assert '--permission-mode' not in argv
    assert '--model' in argv and 'auto/coding' in argv   # the rest still applies


def test_a_launch_naming_an_unknown_profile_stays_on_anthropic(monkeypatch, tmp_path):
    """Never a fall back to the active profile: a session routed at a backend
    nobody chose is the failure the profile layer exists to remove. A deleted
    profile means Anthropic, and `auto` keeps working because the classifier is
    reachable again."""
    sb = Sandbox(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    call = captured_launch(monkeypatch, sb, 'new',
                           {'perm': 'auto', 'provider': 'deleted',
                            'provider_model': 'auto/coding'})
    argv = argv_of(call)
    assert 'auto/coding' not in argv
    assert '--permission-mode' in argv


def test_auto_is_dropped_for_a_model_that_does_not_support_it(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'new',
                           {'perm': 'auto', 'model': 'claude-haiku-4-5'})
    assert '--permission-mode' not in argv_of(call)


def test_only_auto_is_ever_suppressed(monkeypatch, tmp_path):
    """Suppression is narrow on purpose: every other mode applies to every
    model and provider, so none of them may be silently dropped."""
    from claude_sessions.config import PERMS
    sb = Sandbox(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    for perm in [p for p in PERMS if p and p != 'auto']:
        argv = argv_of(captured_launch(
            monkeypatch, sb, 'new',
            {'perm': perm, 'model': 'claude-haiku-4-5', 'provider': 'auto/coding'}))
        assert f'--permission-mode {perm}' in ' '.join(argv), perm


def test_fallback_chain_and_autocompact_come_from_settings(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import config as cfg
    s = cfg.load_settings()
    s['launch_fallback_models'] = ['claude-sonnet-5', '', 'claude-haiku-4-5']
    s['launch_autocompact'] = '500k'
    cfg.save_settings(s)
    argv = argv_of(captured_launch(monkeypatch, sb, 'new', {}))
    j = ' '.join(argv)
    assert '--fallback-model claude-sonnet-5,claude-haiku-4-5' in j   # blanks dropped
    assert '--autocompact 500k' in j


def test_direct_launch_worktree_custom(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'new', {'worktree': 'feat-x'})
    argv = argv_of(call)
    i = argv.index('-w')
    assert argv[i + 1] == 'feat-x'


def test_direct_launch_name_only_for_new(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'resume:abc',
                           {'name': 'X', 'worktree': '*'})
    argv = argv_of(call)
    assert '-n' not in argv and '-w' not in argv


def test_direct_launch_terminal(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'terminal', {})
    # argv list, never a shell string: nothing in the environment or the cwd
    # can be reinterpreted by cmd on the way through. The two spawn tables in
    # proc.py are both real behaviour, so assert the host's rather than skip.
    if os.name == 'nt':
        assert call[0][0] == ['cmd', '/k']
    else:
        assert call[0][0][0].endswith(('sh', 'bash', 'zsh')), call[0][0]
    assert call[1].get('shell') is None


def test_direct_launch_cwd_and_extra_paths(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    extra = str(sb.root)
    call = captured_launch(monkeypatch, sb, 'new', {},
                           folder_files={'extra-paths.txt': extra})
    kw = call[1]
    assert kw['cwd'] == str(sb.root)
    assert kw['env']['PATH'].startswith(extra + ';')


def test_choice_line_matrix(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)          # pins main_mod.config_dir
    cfg = str(sb.cfg)
    cases = [
        ('new', dict(OPTS0), f'v8|P|E|new|-|-|-|-|-|{cfg}|-|-|-|-|-|-'),
        ('continue', dict(OPTS0, effort='low'),
         f'v8|P|E|continue|low|-|-|-|-|{cfg}|-|-|-|-|-|-'),
        ('resume:abc', dict(OPTS0, model='claude-fable-5', perm='dontAsk'),
         f'v8|P|E|resume:abc|-|claude-fable-5|dontAsk|-|-|{cfg}|-|-|-|-|-|-'),
        ('new', dict(OPTS0, name='N N', worktree='wt', agent='rev'),
         f'v8|P|E|new|-|-|-|N N|wt|{cfg}|rev|-|-|-|-|-'),
        ('new', dict(OPTS0, max_thinking='8000', subagent_model='claude-haiku-4-5'),
         f'v8|P|E|new|-|-|-|-|-|{cfg}|-|-|8000|claude-haiku-4-5|-|-'),
    ]
    for choice, opts, expected in cases:
        line = main_mod.build_choice_line('P', 'E', choice, opts)
        assert line == expected, (choice, line)


# ── F3: launch economy env + choice-line v6 ──────────────────

def env_of(call):
    return call[1].get('env', {})


def test_economy_env_injected(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'new',
                           {'max_thinking': '8000', 'subagent_model': 'claude-haiku-4-5'})
    env = env_of(call)
    assert env['MAX_THINKING_TOKENS'] == '8000'
    assert env['CLAUDE_CODE_SUBAGENT_MODEL'] == 'claude-haiku-4-5'


def test_economy_env_absent_when_unset(monkeypatch, tmp_path):
    # ambient values leak in when the test itself runs inside an archeus-launched session
    monkeypatch.delenv('MAX_THINKING_TOKENS', raising=False)
    monkeypatch.delenv('CLAUDE_CODE_SUBAGENT_MODEL', raising=False)
    sb = Sandbox(monkeypatch, tmp_path)
    call = captured_launch(monkeypatch, sb, 'new', {})
    env = env_of(call)
    assert 'MAX_THINKING_TOKENS' not in env
    assert 'CLAUDE_CODE_SUBAGENT_MODEL' not in env


def test_choice_line_v8_round_trip(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    opts = dict(OPTS0, effort='high', model='claude-sonnet-5', cfgdir='C:/cfg',
                max_thinking='16000', subagent_model='claude-haiku-4-5',
                agent='', agents_json='')
    line = main_mod.build_choice_line('C:/proj', 'ENC', 'new', opts)
    assert line.startswith('v8|')
    p, enc, choice, got = main_mod.parse_choice_line(line)
    assert (p, enc, choice) == ('C:/proj', 'ENC', 'new')
    assert got['max_thinking'] == '16000'
    assert got['subagent_model'] == 'claude-haiku-4-5'
    assert got['effort'] == 'high'


def test_v5_line_parses_without_economy(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    v5 = 'v5|C:/proj|ENC|new|high|claude-sonnet-5|-|-|-|C:/cfg|-|-'
    p, enc, choice, got = main_mod.parse_choice_line(v5)
    assert (p, enc, choice) == ('C:/proj', 'ENC', 'new')
    assert got['max_thinking'] == '' and got['subagent_model'] == ''
    assert got['effort'] == 'high'


# ── what a PROJECT configures reaches every CLI, not only Claude Code ──

def test_a_projects_extra_dirs_and_prompt_survive_the_harness_dispatch(
        monkeypatch, tmp_path):
    """`build_launch_command` resolves the project's extra directories and its
    system prompt from `proj_folder`, and both were resolved a hundred lines
    BELOW the point where it hands off to a non-Claude builder. So
    `codex.launch_argv` read an `add_dirs` nothing ever set, and a project's
    configuration silently applied under one CLI and not the others.

    Asserted at `build_launch_command` rather than in `codex.py`, because the
    bug was never in the builder — it was which side of the dispatch the value
    was computed on.
    """
    sb = Sandbox(monkeypatch, tmp_path)
    enc = 'X--proj'
    folder = sb.projects / enc
    folder.mkdir(exist_ok=True)
    extra = str(sb.root)                       # must exist: the filter drops it otherwise
    (folder / 'add-dirs.txt').write_text(extra, encoding='utf-8')
    (folder / 'system-prompt.txt').write_text('sp', encoding='utf-8')

    seen = {}

    def fake_argv(exe, choice, opts, cwd):
        seen.update(opts)
        return [exe]

    monkeypatch.setattr(main_mod._harnesses, 'exe', lambda hid=None: 'codex.exe')
    monkeypatch.setattr(main_mod._harnesses, 'impl',
                        lambda key, hid=None: fake_argv)
    monkeypatch.setattr(main_mod._harnesses, 'of',
                        lambda cfgdir=None: main_mod._harnesses.descriptor('codex'))
    main_mod.build_launch_command(str(sb.root), enc, 'new', dict(OPTS0))
    assert seen.get('add_dirs') == [extra]
    assert seen.get('system_prompt_file', '').endswith('system-prompt.txt')
