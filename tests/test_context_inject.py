import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, make_jsonl, run_flow, DOWN, ENTER
from claude_sessions import context_inject as ci
from claude_sessions import config as config_mod
from claude_sessions.paths import encode_component


def _two_accounts(sb, tmp_path, monkeypatch):
    """Patch all_config_dirs to expose a 2nd account ('work')."""
    other = tmp_path / 'work-cfg'
    (other / 'projects').mkdir(parents=True)
    accts = lambda: [('default', str(sb.cfg)), ('work', str(other))]
    monkeypatch.setattr(config_mod, 'all_config_dirs', accts)
    return str(other)


def test_account_name_for_matches_default(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    assert ci._account_name_for(sb.cfg) == 'default'


def test_find_sessions_across_accounts_reads_title(monkeypatch, tmp_path):
    # find_sessions_across_accounts uses the REAL encode_component (unlike
    # harness.add_project's simplified fake scheme), so build the project
    # folder directly with the real encoding.
    sb = Sandbox(monkeypatch, tmp_path)
    actual = str(tmp_path / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = encode_component(actual)
    folder = os.path.join(str(sb.projects), enc)
    os.makedirs(folder, exist_ok=True)
    sid = 'aaaa0000-0000-0000-0000-000000000000'
    make_jsonl(os.path.join(folder, f'{sid}.jsonl'), title='Fix the bug')

    found = ci.find_sessions_across_accounts(actual)
    assert len(found) == 1
    acct_name, found_folder, found_sid, mtime, preview, title = found[0]
    assert acct_name == 'default'
    assert found_folder == folder
    assert found_sid == sid
    assert title == 'Fix the bug'


def test_pick_target_account_single_account_no_prompt(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    proj_folder = os.path.join(str(sb.projects), 'X--enc')
    d, name = ci._pick_target_account(proj_folder)
    assert os.path.normcase(os.path.abspath(d)) == os.path.normcase(os.path.abspath(sb.cfg))
    assert name == 'default'


def test_pick_target_account_lets_user_choose_other(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    other = _two_accounts(sb, tmp_path, monkeypatch)
    proj_folder = os.path.join(str(sb.projects), 'X--enc')   # current = default
    # menu is sorted current-first: [default, work, Cancel] → DOWN picks 'work'
    (d, name), _cap, _ = run_flow(monkeypatch, [*DOWN, *ENTER],
                                  ci._pick_target_account, proj_folder)
    assert os.path.normcase(os.path.abspath(d)) == os.path.normcase(os.path.abspath(other))
    assert name == 'work'


def test_inject_launches_under_chosen_target_account(monkeypatch, tmp_path):
    import subprocess
    sb = Sandbox(monkeypatch, tmp_path)
    other = _two_accounts(sb, tmp_path, monkeypatch)
    # a source session under the default account, real encoding
    actual = str(tmp_path / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = encode_component(actual)
    folder = os.path.join(str(sb.projects), enc)
    os.makedirs(folder, exist_ok=True)
    make_jsonl(os.path.join(folder, 'aaaa0000-0000-0000-0000-000000000000.jsonl'),
               title='Fix the bug')
    proj_folder = folder   # current account = default

    calls = []
    monkeypatch.setattr(subprocess, 'call', lambda *a, **k: calls.append((a, k)) or 0)
    # source menu: ENTER (first session) → target menu: DOWN,ENTER ('work')
    keys = [*ENTER, *DOWN, *ENTER]
    launched, _cap, _ = run_flow(monkeypatch, keys, ci.run, actual, proj_folder, 'alpha')
    assert launched is True
    env = calls[0][1]['env']
    assert os.path.normcase(os.path.abspath(env['CLAUDE_CONFIG_DIR'])) == \
           os.path.normcase(os.path.abspath(other))


def test_write_context_file_contains_transcript(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, sids = sb.add_project('beta', n_sessions=1, title='Refactor auth')
    ctx_path, title = ci._write_context_file(actual, folder, sids[0], 'default')
    assert title == 'Refactor auth'
    assert os.path.isfile(ctx_path)
    text = open(ctx_path, encoding='utf-8').read()
    assert 'Refactor auth' in text
    assert 'account: default' in text
    assert 'hello world message' in text   # from make_jsonl's default preview text


def test_injected_session_launches_in_the_default_permission_mode(monkeypatch, tmp_path):
    """A new-chat-with-context launch must carry the same starting mode as one
    started through the launch picker — it passed --model but never
    --permission-mode, so it silently started in Claude Code's own default."""
    import subprocess
    sb = Sandbox(monkeypatch, tmp_path)
    actual = str(tmp_path / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = encode_component(actual)
    folder = os.path.join(str(sb.projects), enc)
    os.makedirs(folder, exist_ok=True)
    make_jsonl(os.path.join(folder, 'aaaa0000-0000-0000-0000-000000000000.jsonl'),
               title='Fix the bug')
    config_mod.save_settings({'default_permission': 'auto',
                              'default_model': 'claude-sonnet-5'})

    calls = []
    monkeypatch.setattr(subprocess, 'call', lambda *a, **k: calls.append((a, k)) or 0)
    launched, _cap, _ = run_flow(monkeypatch, [*ENTER], ci.run, actual, folder, 'alpha')
    assert launched is True
    args = calls[0][0][0]
    assert '--permission-mode' in args
    assert args[args.index('--permission-mode') + 1] == 'auto'


def test_a_project_default_wins_over_the_account_default(monkeypatch, tmp_path):
    import subprocess
    sb = Sandbox(monkeypatch, tmp_path)
    actual = str(tmp_path / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = encode_component(actual)
    folder = os.path.join(str(sb.projects), enc)
    os.makedirs(folder, exist_ok=True)
    make_jsonl(os.path.join(folder, 'aaaa0000-0000-0000-0000-000000000000.jsonl'),
               title='Fix the bug')
    config_mod.save_settings({'default_permission': 'auto',
                              'project_defaults': {enc: {'permission': 'plan'}}})

    calls = []
    monkeypatch.setattr(subprocess, 'call', lambda *a, **k: calls.append((a, k)) or 0)
    run_flow(monkeypatch, [*ENTER], ci.run, actual, folder, 'alpha')
    args = calls[0][0][0]
    assert args[args.index('--permission-mode') + 1] == 'plan'


def test_a_pinned_project_model_does_not_reach_a_launch_with_no_picker(monkeypatch, tmp_path):
    """The launch picker re-saves its model pick as the project default on every
    launch, so one trial run on an expensive model became every later
    context-inject — a path that shows no picker, so the choice was invisible
    and unchangeable. The account default is the only model a no-picker launch
    may use."""
    import subprocess
    sb = Sandbox(monkeypatch, tmp_path)
    actual = str(tmp_path / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = encode_component(actual)
    folder = os.path.join(str(sb.projects), enc)
    os.makedirs(folder, exist_ok=True)
    make_jsonl(os.path.join(folder, 'aaaa0000-0000-0000-0000-000000000000.jsonl'),
               title='Fix the bug')
    config_mod.save_settings({'default_model': '',
                              'project_defaults': {enc: {'model': 'claude-fable-5'}}})

    calls = []
    monkeypatch.setattr(subprocess, 'call', lambda *a, **k: calls.append((a, k)) or 0)
    run_flow(monkeypatch, [*ENTER], ci.run, actual, folder, 'alpha')
    assert '--model' not in calls[0][0][0]


def test_auto_is_not_claimed_for_a_model_that_cannot_run_it(monkeypatch, tmp_path):
    import subprocess
    sb = Sandbox(monkeypatch, tmp_path)
    actual = str(tmp_path / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = encode_component(actual)
    folder = os.path.join(str(sb.projects), enc)
    os.makedirs(folder, exist_ok=True)
    make_jsonl(os.path.join(folder, 'aaaa0000-0000-0000-0000-000000000000.jsonl'),
               title='Fix the bug')
    config_mod.save_settings({'default_permission': 'auto',
                              'default_model': 'claude-haiku-4-5'})

    calls = []
    monkeypatch.setattr(subprocess, 'call', lambda *a, **k: calls.append((a, k)) or 0)
    run_flow(monkeypatch, [*ENTER], ci.run, actual, folder, 'alpha')
    assert '--permission-mode' not in calls[0][0][0]


def _unreadable(monkeypatch, path):
    import builtins
    target = os.path.normcase(os.path.abspath(path))
    real_open = builtins.open

    def fake_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)) and \
                os.path.normcase(os.path.abspath(os.fspath(file))) == target:
            raise PermissionError(13, 'fake denied', str(file))
        return real_open(file, *a, **k)
    monkeypatch.setattr(builtins, 'open', fake_open)


def test_unreadable_base_prompt_refuses_the_inject_launch(monkeypatch, tmp_path):
    import subprocess
    from claude_sessions import store, ui
    sb = Sandbox(monkeypatch, tmp_path)
    other = _two_accounts(sb, tmp_path, monkeypatch)
    actual = str(tmp_path / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = encode_component(actual)
    folder = os.path.join(str(sb.projects), enc)
    os.makedirs(folder, exist_ok=True)
    make_jsonl(os.path.join(folder, 'aaaa0000-0000-0000-0000-000000000000.jsonl'),
               title='Fix the bug')
    target_folder = store.project_folder(other, enc)
    os.makedirs(target_folder, exist_ok=True)
    base = os.path.join(target_folder, 'system-prompt.txt')
    with open(base, 'w', encoding='utf-8') as f:
        f.write('BASE RULE\n')
    _unreadable(monkeypatch, base)

    calls = []
    flashes = []
    monkeypatch.setattr(subprocess, 'call', lambda *a, **k: calls.append((a, k)) or 0)
    monkeypatch.setattr(ui, 'flash', lambda msg, **k: flashes.append(msg))
    keys = [*ENTER, *DOWN, *ENTER]
    launched, _cap, _ = run_flow(monkeypatch, keys, ci.run, actual, folder, 'alpha')
    assert launched is False
    assert calls == []
    assert flashes and flashes[0].startswith('Cannot ')
