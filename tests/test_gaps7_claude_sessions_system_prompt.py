"""T-1312 — gap tests for `claude_sessions/system_prompt.py` lines 10-23 (inclusive)
at worktree tip d429bf96 (card tip 51f4af3f; the lines still match).

Source slice: `merged_system_prompt(sp_file, pointer, out_path)` — the base read
(16-18), the join with the pointer (19), the directory creation (20) and the
single write (21-23). The base read is not wrapped in this tip: an unreadable
existing base raises instead of being dropped.

Selected branches (denial/fail-closed first, then boundaries, then error paths):
 1. :17-18    unreadable existing base raises PermissionError; the output is
              byte-identical and no makedirs or write is attempted
 2. :17-20    unknown base (read fails) creates no output directory; an absent
              base is a different case and still writes the pointer
 3. :17       missing base (path absent, '' or None) writes the pointer alone
 4. :18-19    whitespace-only base contributes no separator
 5. :18-19    a non-empty base is stripped once, joined by exactly two newlines,
              and the pointer is always last
 6. :20-23    a nested output directory is created before the write and the
              requested path is returned
 7. :21-23    an output write failure propagates; no path is returned
 8. context_inject.run (177-181 in the caller) with an unreadable base never
              launches the successor
 9. plan_execute.run (455, 657-660 in the caller) with an unreadable base never
              launches execution
10. both callers keep the base before the pointer and never stack
              --append-system-prompt (the pointer would be lost)

Every filesystem path is under tmp_path. The base read is denied through a fake
open that matches only the exact base path, so no real file is touched and the
test is the same on Windows and Linux (no chmod, no OS error text is asserted).
"""

import builtins
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from claude_sessions import context_inject, plan_execute, store, system_prompt  # noqa: E402
from claude_sessions import config, harnesses, render, sessions, ui  # noqa: E402


def _deny_read(monkeypatch, path):
    """Fake open(): a read of exactly `path` raises PermissionError; every other
    call, and every write, goes to the real open."""
    target = os.path.abspath(str(path))
    real_open = builtins.open

    def fake_open(file, *args, **kwargs):
        mode = args[0] if args else kwargs.get('mode', 'r')
        if mode == 'r' and isinstance(file, (str, os.PathLike)) \
                and os.path.abspath(os.fspath(file)) == target:
            raise PermissionError('denied for this test')
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', fake_open)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_unreadable_base_raises_and_leaves_output_untouched(tmp_path, monkeypatch):
    """Branch :17-18. The read happens before any directory or write, so a denied
    base must raise with the existing output bytes unchanged and no makedirs
    call. Swallowing the error (as an older tip did) would write the pointer over
    the prior file."""
    base = _write(tmp_path / 'proj' / 'system-prompt.txt', 'Base rules.')
    out = _write(tmp_path / 'merged' / 'out.txt', 'PRIOR')
    _deny_read(monkeypatch, base)
    made = []
    real_makedirs = os.makedirs

    def spy_makedirs(path, *args, **kwargs):
        made.append(os.fspath(path))
        return real_makedirs(path, *args, **kwargs)

    monkeypatch.setattr(os, 'makedirs', spy_makedirs)
    with pytest.raises(PermissionError):
        system_prompt.merged_system_prompt(str(base), 'POINTER', str(out))
    assert out.read_text(encoding='utf-8') == 'PRIOR'
    assert made == []


def test_unknown_base_creates_no_directory_while_absent_base_still_writes(tmp_path, monkeypatch):
    """Branch :17-20. An existing-but-unreadable base is unknown, so it must not
    create the output's parent directory. An absent base is a different state
    (isfile False, no read) and writes the pointer alone to the same path."""
    base = _write(tmp_path / 'sp.txt', 'Base rules.')
    _deny_read(monkeypatch, base)
    out = tmp_path / 'missing' / 'nested' / 'out.txt'
    with pytest.raises(PermissionError):
        system_prompt.merged_system_prompt(str(base), 'POINTER', str(out))
    assert not (tmp_path / 'missing').exists()
    assert system_prompt.merged_system_prompt(str(tmp_path / 'nope.txt'), 'POINTER',
                                              str(out)) == str(out)
    assert out.read_text(encoding='utf-8') == 'POINTER'


def test_absent_or_empty_base_writes_the_pointer_alone(tmp_path):
    """Branch :17. A path that is not a file, an empty string and None all skip
    the read; the output is the pointer and nothing else (no leading separator)."""
    for i, base in enumerate([str(tmp_path / 'nope.txt'), '', None]):
        out = tmp_path / f'out{i}.txt'
        system_prompt.merged_system_prompt(base, 'POINTER', str(out))
        assert out.read_text(encoding='utf-8') == 'POINTER'


def test_whitespace_only_base_adds_no_separator(tmp_path):
    """Branch :18-19. A base that strips to '' is falsy, so `text` is the pointer
    with no leading newline pair. Dropping the `if base` guard would write
    '\\n\\nPOINTER'."""
    base = _write(tmp_path / 'sp.txt', '  \n\t\n   ')
    out = tmp_path / 'out.txt'
    system_prompt.merged_system_prompt(str(base), 'POINTER', str(out))
    assert out.read_text(encoding='utf-8') == 'POINTER'


def test_nonempty_base_is_stripped_once_then_pointer_last(tmp_path):
    """Branch :18-19. Surrounding whitespace of the base is removed once, and the
    base is followed by exactly two newlines and the pointer. Keeping the raw base
    would double the blank lines; putting the pointer before the base would hide
    it from the instruction order the callers rely on."""
    base = _write(tmp_path / 'sp.txt', '\n\n  Be terse.  \n\n')
    out = tmp_path / 'out.txt'
    system_prompt.merged_system_prompt(str(base), 'POINTER', str(out))
    assert out.read_text(encoding='utf-8') == 'Be terse.\n\nPOINTER'


def test_nested_output_directory_is_created_and_requested_path_returned(tmp_path):
    """Branch :20-23. The parent chain is created before the write, and the return
    value is the exact path requested (not a normalized or derived one)."""
    out = tmp_path / 'a' / 'b' / 'c.txt'
    ret = system_prompt.merged_system_prompt(None, 'POINTER', str(out))
    assert ret == str(out)
    assert out.read_text(encoding='utf-8') == 'POINTER'


def test_output_write_failure_propagates_and_never_reports_success(tmp_path, monkeypatch):
    """Branch :21-23. A failing write for the output path must raise. Returning
    the path after a failed write would hand the launcher a file that does not
    exist."""
    out = tmp_path / 'out.txt'
    real_open = builtins.open

    def failing_open(file, *args, **kwargs):
        mode = args[0] if args else kwargs.get('mode', 'r')
        if mode == 'w' and os.path.abspath(os.fspath(file)) == os.path.abspath(str(out)):
            raise OSError(28, 'injected write failure')
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', failing_open)
    with pytest.raises(OSError):
        system_prompt.merged_system_prompt(None, 'POINTER', str(out))
    assert not out.exists()


def _fake_context_seams(monkeypatch, tmp_path):
    """Replace every seam context_inject.run touches except the merge itself, and
    record subprocess.call. The project's system-prompt.txt is the base."""
    calls, flashes = [], []
    target = tmp_path / 'target'
    base = target / 'system-prompt.txt'
    monkeypatch.setattr(ui, 'menu', lambda items, title='', *a, **k: 0)
    monkeypatch.setattr(ui, 'flash', lambda msg, **k: flashes.append(msg))
    monkeypatch.setattr(ui, '_cls', lambda: None)
    monkeypatch.setattr(config, 'get_claude_exe', lambda: 'claude-fake')
    monkeypatch.setattr(config, 'launch_defaults', lambda encoded: (None, None))
    monkeypatch.setattr(sessions, 'load_add_dirs', lambda folder: [])
    monkeypatch.setattr(sessions, 'read_extra_paths', lambda folder: [])
    monkeypatch.setattr(context_inject, 'find_sessions_across_accounts',
                        lambda pp: [('acct', 'folder', 'sid123456', 0, 'preview', 'title')])
    monkeypatch.setattr(context_inject, '_pick_target_account',
                        lambda pf: (str(target), 'target'))
    monkeypatch.setattr(context_inject, '_write_context_file',
                        lambda pp, folder, sid, acct: (str(tmp_path / 'ctx.md'), 'title'))
    monkeypatch.setattr(store, 'project_folder', lambda d, e: str(target))
    monkeypatch.setattr(store, 'workfile', lambda pp, name: str(tmp_path / 'work' / name))
    monkeypatch.setattr(harnesses, 'of', lambda d: harnesses.descriptor(harnesses.DEFAULT))
    monkeypatch.setattr(context_inject.subprocess, 'call',
                        lambda args, **k: calls.append(list(args)) or 0)
    return base, calls, flashes


def test_context_inject_with_unreadable_base_never_launches(tmp_path, monkeypatch):
    """Caller probe 8. context_inject.run (177-181) must return False and call
    subprocess.call zero times when the base cannot be read; the user is told why."""
    base, calls, flashes = _fake_context_seams(monkeypatch, tmp_path)
    _write(base, 'Base rules.')
    _deny_read(monkeypatch, base)
    assert context_inject.run(str(tmp_path / 'proj'), str(tmp_path / 'pf'), 'proj') is False
    assert calls == []
    assert any('Cannot read the base system prompt' in m for m in flashes)


def test_context_inject_keeps_base_before_pointer_without_stacking_flags(tmp_path, monkeypatch):
    """Caller probe 10, context_inject. A readable base reaches the single merged
    file ahead of the pointer, and the launch argv carries --system-prompt-file
    only. A second --append-system-prompt would silently drop the pointer when
    --system-prompt-file is also present."""
    base, calls, _flashes = _fake_context_seams(monkeypatch, tmp_path)
    _write(base, 'Existing rules.')
    assert context_inject.run(str(tmp_path / 'proj'), str(tmp_path / 'pf'), 'proj') is True
    (args,) = calls
    assert '--append-system-prompt' not in args
    merged = tmp_path / 'work' / 'context-system-prompt.txt'
    assert args[:3] == ['claude-fake', '--system-prompt-file', str(merged)]
    text = merged.read_text(encoding='utf-8')
    assert text.startswith('Existing rules.\n\nPrior conversation context')
    assert text.endswith('then continue from where the user picks up.')


def _fake_exec_seams(monkeypatch, tmp_path):
    """Replace every seam plan_execute.run touches before and around the launch,
    so the only real code is run -> build_exec_launch -> merged_system_prompt."""
    calls, flashes = [], []
    cfg = str(tmp_path / 'cfg')
    monkeypatch.setattr(ui, 'text_input', lambda prompt, *a, **k: 'do the thing')
    monkeypatch.setattr(ui, 'menu', lambda items, title='', *a, **k: 'high')
    monkeypatch.setattr(ui, 'confirm', lambda prompt, *a, **k: False)
    monkeypatch.setattr(ui, 'flash', lambda msg, **k: flashes.append(msg))
    monkeypatch.setattr(ui, '_cls', lambda: None)
    monkeypatch.setattr(ui, 'pager', lambda *a, **k: None)
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    monkeypatch.setattr(config, 'active_provider', lambda s: None)
    monkeypatch.setattr(config, 'provider_env', lambda prof: None)
    monkeypatch.setattr(config, 'all_config_dirs', lambda: [('default', cfg)])
    monkeypatch.setattr(config, 'get_claude_exe', lambda: 'claude-fake')
    monkeypatch.setattr(config, 'config_dir', cfg)
    monkeypatch.setattr(sessions, 'load_add_dirs', lambda folder: [])
    monkeypatch.setattr(sessions, 'read_extra_paths', lambda folder: [])
    monkeypatch.setattr(plan_execute, 'plan_review_loop', lambda plan, title='': plan)
    monkeypatch.setattr(plan_execute, 'write_plan_file',
                        lambda pp, task, plan: str(tmp_path / 'plan.md'))
    monkeypatch.setattr(store, 'workfile', lambda pp, name: str(tmp_path / 'work' / name))
    monkeypatch.setattr(render, 'screen_restore', lambda: None)
    monkeypatch.setattr(render, 'screen_init', lambda: None)
    monkeypatch.setattr(plan_execute.subprocess, 'call',
                        lambda args, **k: calls.append(list(args)) or 0)
    return calls, flashes


def test_plan_execute_with_unreadable_base_never_launches(tmp_path, monkeypatch):
    """Caller probe 9. plan_execute.run must return False, flash the reason and
    never call subprocess.call when build_exec_launch cannot read the base
    (the OSError guard at plan_execute.py:657-660)."""
    calls, flashes = _fake_exec_seams(monkeypatch, tmp_path)
    proj = tmp_path / 'pf'
    base = _write(proj / 'system-prompt.txt', 'Base rules.')
    _deny_read(monkeypatch, base)
    result = plan_execute.run(str(tmp_path / 'proj'), str(proj), 'proj', plan='1. step')
    assert result is False
    assert calls == []
    assert any('Cannot prepare the launch' in m for m in flashes)


def test_plan_execute_keeps_base_before_pointer_without_stacking_flags(tmp_path, monkeypatch):
    """Caller probe 10, plan_execute. A readable base reaches the merged file ahead
    of the plan pointer, the launch argv uses --system-prompt-file only, and the
    pointer ends with the task text the model is told to execute."""
    calls, _flashes = _fake_exec_seams(monkeypatch, tmp_path)
    proj = tmp_path / 'pf'
    _write(proj / 'system-prompt.txt', 'Existing rules.')
    assert plan_execute.run(str(tmp_path / 'proj'), str(proj), 'proj', plan='1. step') is True
    (args,) = calls
    assert '--append-system-prompt' not in args
    merged = tmp_path / 'work' / 'plan-system-prompt.txt'
    assert args[:3] == ['claude-fake', '--system-prompt-file', str(merged)]
    text = merged.read_text(encoding='utf-8')
    assert text.startswith('Existing rules.\n\nAn approved implementation plan')
    assert text.endswith('Task: do the thing')
