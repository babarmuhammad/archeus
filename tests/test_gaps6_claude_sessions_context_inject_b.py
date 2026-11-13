"""T-1289: claude_sessions/context_inject.py lines 103-197 at 6bbd3b44.

Selected candidates, not measured coverage. Probes ranked denial/fail-closed
first, then boundaries, then error paths:

1. 122 source menu Cancel stops before the target picker, write, env and spawn
   -> test_source_menu_cancel_stops_before_the_target_picker
2. 130 target Cancel makes no context write and no CLI lookup or spawn (both harness branches)
   -> test_target_cancel_writes_nothing_and_looks_up_no_cli
3. 135 a failed context write blocks both launch branches
   -> test_context_write_failure_blocks_both_launch_branches
4. 148 alternate builder gets the chosen target, choice 'new', inert pointer; RuntimeError gives False
   -> test_alternate_builder_gets_the_chosen_target_and_an_inert_pointer
5. 167 claude branch pins the target home (passing) and scrubs the API key shadow (strict xfail)
   -> test_claude_branch_pins_the_target_home / test_claude_branch_scrubs_the_api_key_shadow
6. 168 extra PATH and add-dirs come from the target folder
   -> test_extra_path_and_add_dirs_come_from_the_target_folder
7. 180 a failed system-prompt merge refuses the launch
   -> test_system_prompt_merge_failure_refuses_the_launch
8. 194 claude branch spawn failure must not report launched (strict xfail)
   -> test_claude_branch_spawn_failure_is_not_a_launch
9. 156 alternate branch spawn failure must not report success (strict xfail); argv, cwd, env exact
   -> test_alternate_spawn_failure_is_not_a_launch / test_alternate_argv_cwd_env_are_exact
10. 183 model and permission come from project policy; dash-led add-dir values are refused (strict xfail)
   -> test_model_and_permission_come_from_project_policy / test_dash_led_add_dir_is_refused

Closest existing tests (tests/test_context_inject.py; test_p05_seams.py has no
context_inject spawn case):
test_inject_launches_under_chosen_target_account and
test_injected_session_launches_in_the_default_permission_mode cover the happy
launch; test_unreadable_base_prompt_refuses_the_inject_launch covers a read
failure of the base prompt (probe 7 covers the write side);
test_missing_executable_on_a_non_claude_target_names_the_real_failure covers
the RuntimeError (probe 4) for a missing executable only. None assert a spawn
failure's return value or the dash-led add-dir value.

Seams faked: ui.menu, ui.flash, ui._cls; sessions functions; harnesses.instances
and of; _write_context_file; main.build_launch_command; subprocess.call;
system_prompt.merged_system_prompt; config.get_claude_exe and launch_defaults.
"""

import os
import subprocess
from types import SimpleNamespace

import pytest

from claude_sessions import config as config_mod
from claude_sessions import context_inject as ci
from claude_sessions import harnesses, main, store, system_prompt, ui
from claude_sessions import sessions as sessions_mod
from claude_sessions.paths import encode_component

SID = 'aaaa0000-0000-0000-0000-000000000000'
EXE = os.path.join('C:', 'bin', 'claude.exe')
BODY = 'SECRET-BODY-TEXT'


def _world(monkeypatch, tmp_path, target_harness='claude'):
    cfg = {n: str(tmp_path / (n + '-cfg')) for n in ('src', 'tgt')}
    proj = str(tmp_path / 'proj')
    os.makedirs(proj)
    enc = encode_component(proj)
    folders = {n: os.path.join(cfg[n], 'projects', enc) for n in cfg}
    for f in folders.values():
        os.makedirs(f)

    monkeypatch.setattr(harnesses, 'instances',
                        lambda: [('src', cfg['src'], 'claude'), ('tgt', cfg['tgt'], 'claude')])
    monkeypatch.setattr(harnesses, 'of',
                        lambda cfgdir=None: {'id': target_harness if cfgdir == cfg['tgt'] else 'claude'})
    monkeypatch.setattr(sessions_mod, 'account_folders_for',
                        lambda e: [(n, folders[n]) for n in cfg])
    monkeypatch.setattr(sessions_mod, 'scan_sessions', lambda folder: [(100, SID, 'p', 1)])
    monkeypatch.setattr(sessions_mod, 'load_name', lambda folder, sid: 'Alpha')
    monkeypatch.setattr(sessions_mod, 'get_session_title', lambda path: None)
    monkeypatch.setattr(sessions_mod, 'load_add_dirs', lambda folder: [])
    monkeypatch.setattr(sessions_mod, 'read_extra_paths', lambda folder: [])
    monkeypatch.setattr(config_mod, 'get_claude_exe', lambda: EXE)
    monkeypatch.setattr(config_mod, 'launch_defaults', lambda enc='': (None, None))
    monkeypatch.setattr(system_prompt, 'merged_system_prompt', lambda sp, p, out: out)
    monkeypatch.setattr(ui, '_cls', lambda: None)
    flashes = []
    monkeypatch.setattr(ui, 'flash', lambda msg, **k: flashes.append((msg, k)))
    monkeypatch.setattr(ui, 'menu', _menu_queue([0, ('tgt', cfg['tgt'])]))

    spawned = []
    monkeypatch.setattr(subprocess, 'call',
                        lambda args, **k: spawned.append((args, k)) or 0)
    built = []
    monkeypatch.setattr(main, 'build_launch_command',
                        lambda *a, **k: built.append((a, k)) or (['codex', 'run'], {'X': '1'}, None))
    written = []

    def write(project_path, folder, sid, acct):
        written.append((folder, sid, acct))
        ctx = os.path.join(project_path, ci.CTX_FILE)
        os.makedirs(os.path.dirname(ctx), exist_ok=True)
        with open(ctx, 'w', encoding='utf-8') as f:
            f.write(BODY)
        return ctx, 'Alpha'
    monkeypatch.setattr(ci, '_write_context_file', write)
    return SimpleNamespace(cfg=cfg, proj=proj, enc=enc, folders=folders, spawned=spawned,
                           built=built, written=written, flashes=flashes)


def _menu_queue(answers):
    queue = list(answers)

    def menu(items, title, *a, **k):
        if not queue:
            raise AssertionError('unexpected menu: ' + title)
        return queue.pop(0)
    return menu


def _pop_menus(monkeypatch, answers):
    monkeypatch.setattr(ui, 'menu', _menu_queue(answers))


def _run(w):
    return ci.run(w.proj, w.folders['src'], 'proj')


# ── the cancel paths write nothing and spawn nothing ──

def test_source_menu_cancel_stops_before_the_target_picker(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path)
    _pop_menus(monkeypatch, [None])
    monkeypatch.setattr(ci, '_pick_target_account',
                        lambda *a: pytest.fail('target picker after source cancel'))
    assert _run(w) is False
    assert w.written == [] and w.spawned == [] and w.built == []


@pytest.mark.parametrize('target_harness', ['claude', 'codex'])
def test_target_cancel_writes_nothing_and_looks_up_no_cli(monkeypatch, tmp_path, target_harness):
    w = _world(monkeypatch, tmp_path, target_harness)
    _pop_menus(monkeypatch, [0, None])
    lookups = []
    monkeypatch.setattr(config_mod, 'get_claude_exe', lambda: lookups.append('exe') or EXE)
    monkeypatch.setattr(main, 'build_launch_command',
                        lambda *a, **k: lookups.append('build') or (['x'], {}, None))
    assert _run(w) is False
    assert w.written == [] and lookups == [] and w.spawned == []
    assert not os.path.exists(os.path.join(w.proj, ci.CTX_FILE))


@pytest.mark.parametrize('target_harness', ['claude', 'codex'])
def test_context_write_failure_blocks_both_launch_branches(monkeypatch, tmp_path, target_harness):
    w = _world(monkeypatch, tmp_path, target_harness)
    _pop_menus(monkeypatch, [0, ('tgt', w.cfg['tgt'])])

    def broken(*a, **k):
        raise OSError('disk full')
    monkeypatch.setattr(ci, '_write_context_file', broken)
    with pytest.raises(OSError):
        _run(w)
    assert w.spawned == [] and w.built == []


# ── the alternate harness: explicit target, inert pointer, exact spawn ──

def test_alternate_builder_gets_the_chosen_target_and_an_inert_pointer(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path, target_harness='codex')
    assert _run(w) is True
    (args, kw), = w.built
    assert args[0] == w.proj and args[1] == w.enc and args[2] == 'new'
    opts = args[3]
    assert opts['cfgdir'] == w.cfg['tgt']
    assert 'injected-context.md' in opts['prompt'] and BODY not in opts['prompt']
    assert kw == {}


def test_alternate_argv_cwd_env_are_exact(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path, target_harness='codex')
    assert _run(w) is True
    assert w.spawned == [(['codex', 'run'], {'cwd': w.proj, 'env': {'X': '1'}})]


def test_alternate_builder_runtime_error_is_a_refusal_without_spawn(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path, target_harness='codex')

    def refuse(*a, **k):
        raise RuntimeError('no codex binary')
    monkeypatch.setattr(main, 'build_launch_command', refuse)
    assert _run(w) is False
    assert w.spawned == []
    assert w.flashes and w.flashes[0][0] == 'no codex binary'


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/context_inject.py:157-159 catches the spawn error and returns '
    'True, so a failed alternate launch reports success'))
def test_alternate_spawn_failure_is_not_a_launch(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path, target_harness='codex')

    def boom(args, **k):
        raise OSError('spawn failed')
    monkeypatch.setattr(subprocess, 'call', boom)
    assert _run(w) is False


# ── the claude branch: env pin, extra PATH, prompt merge, spawn ──

def test_claude_branch_pins_the_target_home(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path)
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', w.cfg['src'])
    assert _run(w) is True
    (args, kw), = w.spawned
    assert kw['env']['CLAUDE_CONFIG_DIR'] == w.cfg['tgt']
    assert kw['cwd'] == w.proj and '--system-prompt-file' in args


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/context_inject.py:166 copies os.environ unchanged for the claude '
    'branch, so ANTHROPIC_API_KEY shadows the target login; config.account_env pops it '
    '(harnesses.py:125 env_pops)'))
def test_claude_branch_scrubs_the_api_key_shadow(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-key-value')
    _run(w)
    (args, kw), = w.spawned
    assert 'ANTHROPIC_API_KEY' not in kw['env']


def test_extra_path_and_add_dirs_come_from_the_target_folder(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path)
    seen = {'extra': [], 'dirs': []}

    def extra(folder):
        seen['extra'].append(folder)
        return ['EXTRA-BIN']

    def dirs(folder):
        seen['dirs'].append(folder)
        return []
    monkeypatch.setattr(sessions_mod, 'read_extra_paths', extra)
    monkeypatch.setattr(sessions_mod, 'load_add_dirs', dirs)
    assert _run(w) is True
    tgt_folder = store.project_folder(w.cfg['tgt'], w.enc)
    assert seen == {'extra': [tgt_folder], 'dirs': [tgt_folder]}
    (args, kw), = w.spawned
    assert kw['env']['PATH'].startswith('EXTRA-BIN;')


def test_system_prompt_merge_failure_refuses_the_launch(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path)

    def no_write(sp, pointer, out):
        raise OSError('merged prompt not writable')
    monkeypatch.setattr(system_prompt, 'merged_system_prompt', no_write)
    assert _run(w) is False
    assert w.spawned == []
    assert len(w.flashes) == 1 and w.flashes[0][1].get('ok') is False


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/context_inject.py:197-201 catches the spawn error and returns '
    'True, so a failed claude launch reports launched'))
def test_claude_branch_spawn_failure_is_not_a_launch(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path)

    def boom(args, **k):
        raise OSError('spawn failed')
    monkeypatch.setattr(subprocess, 'call', boom)
    assert _run(w) is False


def test_model_and_permission_come_from_project_policy(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path)
    monkeypatch.setattr(config_mod, 'launch_defaults', lambda enc='': ('m-test', 'plan'))
    assert _run(w) is True
    (args, kw), = w.spawned
    assert args[args.index('--model') + 1] == 'm-test'
    assert args[args.index('--permission-mode') + 1] == 'plan'
    assert args[0] == EXE


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/context_inject.py:190-192 passes add-dirs.txt entries after '
    '--add-dir unchecked, so a dash-led value can be read as an option by claude'))
def test_dash_led_add_dir_is_refused(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    os.makedirs('-x-dir')
    os.makedirs('plain-dir')
    monkeypatch.setattr(sessions_mod, 'load_add_dirs', lambda folder: ['-x-dir', 'plain-dir'])
    _run(w)
    (args, kw), = w.spawned
    assert '-x-dir' not in args


def test_alternate_spawn_failure_argv_does_not_use_a_shell(monkeypatch, tmp_path):
    w = _world(monkeypatch, tmp_path, target_harness='codex')
    _run(w)
    (args, kw), = w.spawned
    assert kw.get('shell') is None
