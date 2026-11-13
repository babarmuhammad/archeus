r"""T-1181 · gap tests for claude_sessions/migrate.py lines 1-341 (inclusive).

Card T-1181. Slice owned: `claude_sessions/migrate.py:1-341` — `_move`, `_merge`,
`_rename_prefixed`, `_migrate_config_dir`, `_migrate_project`, `_repoint`,
`repair_commands`, `_old_config_dirs`, `pending`, `_has_old_artifacts`. Existing
coverage read first: `tests/test_migration.py` (+ `tests/test_tui_hooks.py` for
the re-key seam). Everything here targets a branch NO existing test exercises;
the ten final branches, ranked by risk (fail-closed / denial first, then
boundaries, then error paths):

 1. `migrate.py:281-285` — `hooks._save` raising must put the cfgdir in `failed`
    so the caller cannot stamp the done flag.                                  (F1)
 2. `migrate.py:240-244` — one account whose settings reader raises is recorded
    and SKIPPED; the other accounts are still repaired.                        (F2)
 3. `migrate.py:101-103 + 112-125` — a locked child during `_merge`: exactly
    that child lands in `failed`, siblings move, the foreign live file already
    in the destination is untouched, the swallowed `os.rmdir` failure adds no
    bogus failure, and the next call completes and removes the source.         (F3)
 4. `migrate.py:185-191 + 259/268/281` — a dead command that is NOT ours stays
    byte-identical and the settings file is not re-saved at all.               (F4)
 5. `migrate.py:294-308` — account list from the old settings: junk filtered,
    duplicates collapsed on the normcase key, `~` expanded, default first.     (F5)
 6. `migrate.py:97-98` — missing source is a silent no-op: no move, no failure,
    no destination created, no `os.replace` call.                              (F6)
 7. `migrate.py:127-138` — prefix rename cuts EXACTLY at the prefix (name ==
    prefix, near-misses, already-new names) and an unreadable directory is
    skipped without touching `failed`.                                         (F7)
 8. `migrate.py:160,183-189` — a quoted dead path containing spaces is replaced
    wholesale by the `"([^"]+\.py)"` branch; the bare `\S+\.py` branch matches
    only whole non-space tokens.                                               (F8)
 9. `migrate.py:199-200` — a command with NO interpreter half keeps its shape
    (the `else out` side): nothing is re-prefixed with `sys.executable` and the
    template's arguments survive.                                              (F9)
10. `migrate.py:246-257` — malformed shapes (`hooks` event not a list, inner
    hook not a dict) are skipped, not fatal: repair still runs on every start
    and the valid sibling in the same entry is repaired.                       (F10)

Replaced probes (already covered elsewhere, per the card): destination
collision FILE-vs-FILE is mutation-covered by
`test_migration.py::test_it_never_overwrites_something_already_there` (the
dir-src/file-dst composition hits the same `migrate.py:105-106` decision), and
the one-level foreign-destination merge is covered by
`test_migration.py::test_a_workdir_a_hook_already_created_is_merged_into_not_skipped`
— its nested + locked-child composition is F3.

No host state is touched: settings files are real files under tmp_path, the
package directory is faked through `migrate.__file__`, and fault injection
happens only at the OS/IO seams (`os.replace`, `hooks._load`,
`_c.write_json_atomic`). Invented path strings only; nothing here reads a
credential, the user home or the host environment.
"""
import io
import json
import os
import sys

import pytest

from claude_sessions import config as _c
from claude_sessions import hooks, migrate


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _read(path):
    with io.open(path, encoding='utf-8') as f:
        return f.read()


@pytest.fixture()
def pkg(tmp_path, monkeypatch):
    """A fake installation to re-point at: `repair_commands` derives pkg_dir
    from `__file__`, so that is the seam — the real repo is never consulted."""
    d = tmp_path / 'install' / 'claude_sessions'
    d.mkdir(parents=True)
    for name in ('recall_hook.py', 'statusline_cli.py'):
        (d / name).write_text('# stub\n', encoding='utf-8')
    monkeypatch.setattr(migrate, '__file__', str(d / 'migrate.py'))
    return str(d)


def _settings(cfgdir, d):
    os.makedirs(str(cfgdir), exist_ok=True)
    _write(os.path.join(str(cfgdir), 'settings.json'), json.dumps(d))
    return os.path.join(str(cfgdir), 'settings.json')


# 1. a settings save that fails must land in `failed` (migrate.py:281-285)

def test_a_failed_settings_save_is_reported_as_a_failure(tmp_path, monkeypatch,
                                                          pkg):
    """`run()` writes the done flag only when `failed` is empty. If the atomic
    write of the repaired settings throws (locked by a sync client, read-only
    volume) and the repair only reports it in its log, the caller is told
    "nothing failed" while the fix never reached the disk."""
    cfg = str(tmp_path / 'acct')
    dead = str(tmp_path / 'gone' / 'claude_sessions' / 'recall_hook.py')
    exe = str(tmp_path / 'oldvenv' / 'Scripts' / 'python.exe')
    path = _settings(cfg, {'hooks': {'UserPromptSubmit': [
        {'hooks': [{'type': 'command', 'command': '"%s" "%s"' % (exe, dead)}]}]}})

    def _locked(path_, obj, *a, **k):
        raise OSError('locked')

    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))
    monkeypatch.setattr(_c, 'write_json_atomic', _locked)
    moved, failed = migrate.repair_commands([cfg])
    fixed = '"%s" "%s"' % (sys.executable, os.path.join(pkg, 'recall_hook.py'))
    assert failed == [(cfg, 'locked')], \
        'an unsaved repair was reported as no failure — the done flag becomes writable'
    assert moved == [(cfg, 'hook -> ' + fixed)], moved
    assert json.loads(_read(path))['hooks']['UserPromptSubmit'][0]['hooks'][0][
        'command'] == '"%s" "%s"' % (exe, dead), 'the on-disk file was half-written'


# 2. one unreadable account must not abort the others (migrate.py:240-244)

def test_one_unreadable_account_does_not_stop_the_others(tmp_path, monkeypatch,
                                                         pkg):
    """Repair runs on EVERY start. If one account's settings reader throws and
    the loop has no per-account guard, a single broken account means NO account
    ever gets its dead hook paths repaired again."""
    a = str(tmp_path / 'acctA')
    b = str(tmp_path / 'acctB')
    dead = str(tmp_path / 'dead' / 'claude_sessions' / 'recall_hook.py')
    exe = str(tmp_path / 'oldvenv' / 'Scripts' / 'python.exe')
    cmd_a = '"%s" "%s" --denied' % (exe, os.path.join(str(tmp_path / 'dead' / 'claude_sessions'),
                                                       'recall_hook.py'))
    path_a = _settings(a, {'hooks': {'UserPromptSubmit': [{'hooks': [
        {'type': 'command', 'command': cmd_a}]}]}})
    cmd_b = '"%s" "%s"' % (exe, dead)
    path_b = _settings(b, {'hooks': {'UserPromptSubmit': [{'hooks': [
        {'type': 'command', 'command': cmd_b}]}]}})

    real_load = hooks._load

    def _load(cfgdir=None):
        if str(cfgdir) == a:
            raise OSError('locked')
        return real_load(cfgdir)

    monkeypatch.setattr(hooks, '_load', _load)
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))
    moved, failed = migrate.repair_commands([a, b])
    assert failed == [(a, 'locked')], \
        'the broken account was not reported, so completion could still be claimed'
    assert [m[0] for m in moved] == [b], 'the healthy account was skipped with it'
    assert json.loads(_read(path_a))['hooks']['UserPromptSubmit'][0]['hooks'][0][
        'command'] == cmd_a
    saved_b = json.loads(_read(path_b))['hooks']['UserPromptSubmit'][0]['hooks'][0][
        'command']
    assert os.path.join(pkg, 'recall_hook.py') in saved_b


# 3. partial move + retry, merging into a foreign live destination
#    (migrate.py:101-103, 112-125)

def test_a_locked_child_leaves_the_rest_of_the_tree_for_the_next_run(
        tmp_path, monkeypatch):
    """The destination exists (a hook wrote through `store.workdir`) AND one
    child is locked (sync client). The locked child alone must be reported, its
    siblings must arrive, the live file the destination already held must be
    untouched, the src must stay (the swallowed `os.rmdir` failure is not a
    migration failure) — and the next call must finish the job."""
    src = tmp_path / '.claudectl'
    dst = tmp_path / '.archeus'
    (src / 'sub').mkdir(parents=True)
    dst.joinpath('sub').mkdir(parents=True)
    _write(str(src / 'a.txt'), 'a')
    _write(str(src / 'locked.txt'), 'mine')
    _write(str(src / 'sub' / 'b.txt'), 'b')
    _write(str(dst / 'sub' / 'live.log'), 'LIVE')   # foreign entry already there

    state = {'lock': True}
    real_replace = os.replace

    def _replace(s, d):
        if state['lock'] and os.fspath(s).endswith('locked.txt'):
            raise PermissionError(13, 'locked')
        return real_replace(s, d)

    monkeypatch.setattr(os, 'replace', _replace)

    moved1, failed1 = [], []
    migrate._merge(str(src), str(dst), moved1, failed1)
    assert len(failed1) == 1 and failed1[0][0] == str(src / 'locked.txt'), \
        'the locked child was not the (only) reported failure: %r' % failed1
    assert 'locked' in failed1[0][1]
    assert (dst / 'a.txt').exists() and (dst / 'sub' / 'b.txt').exists(), \
        'siblings of the locked child did not arrive'
    assert _read(str(dst / 'sub' / 'live.log')) == 'LIVE', \
        'a file the live destination already held was overwritten'
    assert (src / 'locked.txt').exists() and src.exists(), \
        'the half-emptied source tree was destroyed or force-removed'
    assert all('locked.txt' not in m[0] for m in moved1), moved1
    assert any(m[0].endswith('a.txt') for m in moved1), moved1

    state['lock'] = False
    moved2, failed2 = [], []
    migrate._merge(str(src), str(dst), moved2, failed2)
    assert failed2 == [], failed2
    assert (dst / 'locked.txt').exists() and _read(str(dst / 'locked.txt')) == 'mine'
    assert not src.exists(), 'the emptied old tree survived a completed retry'


# 4. a dead foreign command is left dead, and NOTHING is saved
#    (migrate.py:185-191, 259, 268, 281)

def test_a_dead_command_that_is_not_ours_is_left_dead_and_unsaved(
        tmp_path, monkeypatch, pkg):
    """Two guards have to hold at once: the path is dead but its basename is
    not one of ours, so neither replacement branch may fire — and with nothing
    rewritten, `changed` must stay False so the user's file is not re-serialised
    (a rewrite reorders/reformats a file Claude Code owns)."""
    cfg = str(tmp_path / 'acct')
    theirs_dir = tmp_path / 'theirs'
    _write(str(theirs_dir / 'live_hook.py'), '# user script, still alive')
    dead_foreign = str(tmp_path / 'theirs' / 'lint_tool.py')     # never created
    cmd = '"C:\\old\\python.exe" "%s"' % dead_foreign
    live = '"C:\\old\\python.exe" "%s"' % str(theirs_dir / 'live_hook.py')
    path = _settings(cfg, {
        'hooks': {'PreToolUse': [{'hooks': [
            {'type': 'command', 'command': cmd},
            {'type': 'command', 'command': live}]}]},
        'statusLine': {'type': 'command', 'command': cmd},
    })
    before = _read(path)

    saved = []
    real_save = hooks._save

    def _spy(d, cfgdir=None):
        saved.append(cfgdir)
        return real_save(d, cfgdir)

    monkeypatch.setattr(hooks, '_save', _spy)
    moved, failed = migrate.repair_commands([cfg])
    assert (moved, failed, saved) == ([], [], []), \
        'a foreign dead command was treated as ours to repair and save'
    assert _read(path) == before, 'the untouched file was still rewritten'


# 5. the old account list: junk filtered, duplicates collapsed, default first
#    (migrate.py:294-308)

def test_the_account_list_is_cleaned_deduped_and_default_first(tmp_path,
                                                               monkeypatch):
    """This list decides which accounts get walked at all. A non-dict entry
    crashing it kills the whole migration; un-expanded `~` silently skips an
    account's caches; a duplicate double-walks one account. The default must be
    first because `run()` moves the settings file last, from the default out."""
    home = tmp_path / 'home'
    home.mkdir()
    default = str(home)
    acct_x = str(tmp_path / 'acctX')
    monkeypatch.setattr(_c, 'settings_file', os.path.join(default, 'archeus.json'))
    old = tmp_path / 'claudectl.json'
    _write(str(old), json.dumps({'accounts': [
        {'name': 'dup-of-default', 'dir': default + os.sep + '.'},
        {'name': 'x', 'dir': acct_x},
        'plain-string',
        {},
        {'name': 'no-dir'},
        {'name': 'x-again', 'dir': acct_x},
        {'name': 'tilde', 'dir': '~/acctT'},
    ]}))
    monkeypatch.setattr(migrate, 'OLD_SETTINGS', str(old))
    monkeypatch.setenv('HOME', str(tmp_path))     # synthetic value, not the host's
    monkeypatch.setenv('USERPROFILE', str(tmp_path))

    out = migrate._old_config_dirs()
    assert out[0] == default, 'the default account is not first'
    assert out.count(default) == 1, 'the default was walked twice via a spelling'
    assert out.count(acct_x) == 1, 'a duplicated account was walked twice'
    assert [os.path.normpath(p) for p in out] == \
        [default, acct_x, os.path.join(str(tmp_path), 'acctT')], out


# 6. missing source is a silent no-op (migrate.py:97-98)

def test_a_missing_source_is_a_silent_no_op(tmp_path, monkeypatch):
    """`_migrate_project` calls `_move` for EVERY project root; most have no
    `.claudectl`. Without the exists() guard, `os.replace` raises
    FileNotFoundError — caught by the OSError arm as a bogus failure — so
    `run()` never gets a clean pass and the done flag is never written: the
    whole tree is re-walked on every launch forever."""
    gone = str(tmp_path / 'proj' / '.claudectl')
    dst = str(tmp_path / 'proj' / '.archeus')
    calls = []
    real_replace = os.replace

    def _spy(s, d):
        calls.append((s, d))
        return real_replace(s, d)

    monkeypatch.setattr(os, 'replace', _spy)
    moved, failed = [], []
    migrate._move(gone, dst, moved, failed)
    os.makedirs(dst)
    migrate._move(gone, dst, moved, failed)              # dst present, src gone
    assert (moved, failed) == ([], []), \
        'a missing source was reported as a failure — the gate would never close'
    assert calls == [], 'os.replace was called for a source that does not exist'
    assert os.path.isdir(dst), 'the live destination directory was disturbed'


# 7. prefix rename cuts exactly; unreadable dirs are silent (migrate.py:127-138)

def test_the_prefix_rename_cuts_exactly_and_ignores_unreadable_dirs(tmp_path):
    """`name.startswith(OLD)` + `name[len(OLD):]` is a boundary: a name EQUAL to
    the prefix must rename to exactly the new prefix (empty remainder), a
    near-miss (`claudctl.json`) and an already-migrated `archeus-*` must not be
    touched, and a directory-less account (listdir OSError) must add NOTHING to
    `failed` — claudectl simply never ran there."""
    d = tmp_path / 'cfg'
    (d / 'claudectl-agents').mkdir(parents=True)
    for name, body in (('claudectl', 'exact'), ('claudectl.json', '{}'),
                       ('claudctl.json', 'near-miss'),
                       ('xclaudectl.json', 'foreign'),
                       ('archeus-already.json', 'done'),
                       ('claudectl-agents' + os.sep + 'inner.md', 'agent')):
        _write(str(d / name), body)
    moved, failed = [], []
    migrate._rename_prefixed(str(d), migrate.OLD, migrate.NEW, moved, failed)
    pairs = set(moved)
    assert (str(d / 'claudectl'), str(d / 'archeus')) in pairs, \
        'the exact-prefix boundary renamed to the wrong name or not at all'
    assert (str(d / 'claudectl.json'), str(d / 'archeus.json')) in pairs
    assert (str(d / 'claudectl-agents'), str(d / 'archeus-agents')) in pairs
    assert _read(str(d / 'archeus')) == 'exact'
    for kept in ('claudctl.json', 'xclaudectl.json', 'archeus-already.json'):
        assert (d / kept).exists(), '%s was renamed but does not start with the ' \
            'old prefix' % kept
    assert failed == [], failed

    # unreadable directories: missing, and a plain file where a dir should be
    moved2, failed2 = [], []
    migrate._rename_prefixed(str(tmp_path / 'no-such-dir'), migrate.OLD,
                             migrate.NEW, moved2, failed2)
    a_file = tmp_path / 'afile.txt'
    _write(str(a_file), 'x')
    migrate._rename_prefixed(str(a_file), migrate.OLD, migrate.NEW, moved2, failed2)
    assert (moved2, failed2) == ([], []), \
        'an unreadable directory was reported as a migration failure'


# 8. the `"([^"]+\.py)"` branch replaces spaced paths wholesale; `\S+` does not
#    split on quotes (migrate.py:160, 183-189)

def test_a_quoted_dead_path_with_spaces_is_replaced_wholesale(pkg):
    """Invented path strings (no host paths): a quoted path with SPACES is one
    argument — the quoted branch must match it whole and replace it whole; a
    bare path with spaces can only ever match as the trailing token, so a
    foreign one must survive byte-identical; a bare quoted-less ours-path must
    be replaced via the second alternative and stay bare."""
    ours = os.path.join(pkg, 'recall_hook.py')
    exe = 'old venv/Scripts/python.exe'
    dead = os.path.abspath(os.path.join('gone dir', 'claude_sessions', 'recall_hook.py'))
    res = migrate._repoint('"%s" "%s" --denied' % (exe, dead), pkg)
    assert res == '"%s" "%s" --denied' % (sys.executable, ours), res

    foreign = 'Tools With Spaces/lint_tool.py'
    cmd = 'run "%s" --x' % foreign
    assert migrate._repoint(cmd, pkg) == cmd, 'a quoted foreign path was rewritten'

    sl = os.path.join(pkg, 'statusline_cli.py')
    dead_sl = os.path.abspath(os.path.join('gone', 'claude_sessions', 'statusline_cli.py'))
    assert migrate._repoint('py %s --flag' % dead_sl, pkg) == \
        'py %s --flag' % sl, 'the bare (unquoted) alternative did not fire'


# 9. no interpreter half -> the command keeps its shape (migrate.py:199-200)

def test_a_command_with_no_interpreter_keeps_its_shape_and_arguments(pkg):
    """The rebuild exists because the interpreter moved WITH the package. When
    there is no interpreter to strip, `tail != out.strip()` is False and the
    `else out` side must fire: prefixing `sys.executable` anyway would change
    how Claude Code shells out (and on Windows, what window flashes), and
    dropping the template's `--denied` argument would silently change what the
    hook enforces."""
    ours = os.path.join(pkg, 'recall_hook.py')
    res = migrate._repoint('"%s" --denied' % os.path.abspath(
        os.path.join('oldenv', 'claude_sessions', 'recall_hook.py')), pkg)
    assert res == '"%s" --denied' % ours, res
    assert sys.executable not in res, 'an interpreter was invented for a bare script'
    assert '--denied' in res, 'the appended template argument did not survive'


# 10. malformed hook shapes are skipped, not fatal (migrate.py:246-257)

def test_malformed_hook_entries_are_skipped_not_fatal(tmp_path, monkeypatch, pkg):
    """settings.json is hand-editable and written by Claude Code itself; this
    repair runs on every start. A `hooks` event that is a bare string, or a
    non-dict entry in an entry's `hooks` list, must be SKIPPED (the two
    isinstance guards) — if either raises, the exception escapes the loop and
    the machine is never repaired again, dead paths and all."""
    cfg = str(tmp_path / 'acct')
    exe = str(tmp_path / 'oldvenv' / 'Scripts' / 'python.exe')
    dead = str(tmp_path / 'dead' / 'claude_sessions' / 'recall_hook.py')
    cmd = '"%s" "%s" --denied' % (exe, dead)
    path = _settings(cfg, {'hooks': {
        'PreToolUse': 'not-a-list',
        'UserPromptSubmit': [{'matcher': 'x', 'hooks': [
            'just-a-string',
            {'type': 'command', 'command': cmd}]}],
    }})

    rekeys = []
    monkeypatch.setattr(hooks, 'rekey_label',
                        lambda ev, was, new: rekeys.append((ev, was, new)))
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))
    moved, failed = migrate.repair_commands([cfg])
    fixed = '"%s" "%s" --denied' % (sys.executable, os.path.join(pkg,
                                                                  'recall_hook.py'))
    assert failed == [], failed
    assert moved == [(cfg, 'hook -> ' + fixed)], moved
    out = json.loads(_read(path))
    assert out['hooks']['PreToolUse'] == 'not-a-list', \
        'the malformed event was dropped from the saved file instead of skipped'
    inner = out['hooks']['UserPromptSubmit'][0]['hooks']
    assert inner[0] == 'just-a-string' and inner[1]['command'] == fixed
    assert [r[0] for r in rekeys] == ['UserPromptSubmit'], \
        'the malformed event reached rekey_label too (guard ordering changed)'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q', '-p', 'no:cacheprovider']))
