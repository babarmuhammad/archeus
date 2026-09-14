"""The claudectl -> archeus move, against a fake old-layout home.

Every assertion here is about something a user would lose if the step were
missing: the settings file is their accounts and per-project launch defaults,
`.claudectl/memory` is the graph every session starts from, and the two library
directories are agents and skills they wrote by hand.

Written so that deleting any one step in `migrate.py` fails a test — checked by
doing exactly that for each of them.
"""
import io
import json
import os
import sys

import pytest

from claude_sessions import config as _c
from claude_sessions import migrate, store


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(text)


@pytest.fixture()
def old_home(monkeypatch, tmp_path):
    """A ~/.claude that a claudectl 1.9.x install would have left behind, with
    a second account, one project and its mirror."""
    home = tmp_path / '.claude'
    other = tmp_path / 'acct2'
    proj = tmp_path / 'work' / 'myproject'

    _write(str(home / 'claudectl.json'), json.dumps({
        'theme': 'nord',
        'accounts': [{'name': 'second', 'dir': str(other)}],
        'project_defaults': {'D--work-myproject': {'model': 'claude-opus-5'}},
    }))
    for name in ('claudectl-stats-cache.json', 'claudectl-versions.json',
                 'claudectl-models.json', 'claudectl-events.jsonl'):
        _write(str(home / name), '{}')
    _write(str(home / 'claudectl-agents' / 'core' / 'reviewer.md'), 'agent')
    _write(str(home / 'claudectl-skills' / 'mine' / 'SKILL.md'), 'skill')
    _write(str(other / 'claudectl-stats-cache.json'), '{}')

    # the project, its mirror, and the files archeus writes into .claude/
    enc = 'D--work-myproject'
    folder = home / 'projects' / enc
    _write(str(folder / 'sess.jsonl'),
           json.dumps({'cwd': str(proj), 'type': 'user'}) + '\n')
    _write(str(folder / '.claudectl' / 'snapshots' / 'claude_md.prev'), 'old')
    _write(str(proj / '.claudectl' / 'memory' / 'graph.json'), '{"entities":[]}')
    _write(str(proj / '.claudectl' / 'bash-log.txt'), 'ls\n')
    _write(str(proj / '.claude' / '.claudectl-agents.json'), '[]')
    _write(str(proj / '.claude' / '.claudectl-managed.json'), '{}')
    _write(str(proj / '.claude' / 'rules' / 'claudectl-mem-app-api.md'), '# api')

    monkeypatch.setattr(_c, 'settings_file', str(home / 'archeus.json'))
    monkeypatch.setattr(migrate, 'OLD_SETTINGS', str(home / 'claudectl.json'))
    # find_actual_path caches per folder across tests; a fresh dict per test
    from claude_sessions import paths
    monkeypatch.setattr(paths, '_path_cache', {})
    return home, other, proj, folder


def test_it_moves_every_artifact_a_user_would_miss(old_home):
    home, other, proj, folder = old_home
    _moved, failed = migrate.run()
    assert not failed, failed

    # settings, with their contents intact — this is accounts and launch defaults
    s = json.load(io.open(str(home / 'archeus.json'), encoding='utf-8'))
    assert s['theme'] == 'nord'
    assert s['project_defaults']['D--work-myproject']['model'] == 'claude-opus-5'
    assert not (home / 'claudectl.json').exists()

    # caches, in BOTH accounts
    assert (home / 'archeus-stats-cache.json').exists()
    assert (home / 'archeus-events.jsonl').exists()
    assert (other / 'archeus-stats-cache.json').exists(), \
        'the second account was skipped — all_config_dirs() cannot be used here'

    # the two libraries, with their contents
    assert (home / 'archeus-agents' / 'core' / 'reviewer.md').exists()
    assert (home / 'archeus-skills' / 'mine' / 'SKILL.md').exists()

    # the project, resolved from the transcript's cwd, and its mirror
    assert (proj / '.archeus' / 'memory' / 'graph.json').exists()
    assert (proj / '.archeus' / 'bash-log.txt').exists()
    assert (folder / '.archeus' / 'snapshots' / 'claude_md.prev').exists()
    assert not (proj / '.claudectl').exists()

    # and what archeus writes into the project's own .claude/
    assert (proj / '.claude' / '.archeus-agents.json').exists()
    assert (proj / '.claude' / '.archeus-managed.json').exists()
    assert (proj / '.claude' / 'rules' / 'archeus-mem-app-api.md').exists()


def test_running_it_twice_changes_nothing(old_home):
    migrate.run()
    assert not migrate.pending(), 'the flag was not written, so it runs forever'
    moved, failed = migrate.run()
    assert (moved, failed) == ([], []), 'a second run touched the disk'


def test_it_never_overwrites_something_already_there(old_home):
    """A half-finished earlier run leaves both names present. The new one is the
    live copy by then, so the old one must not be moved over it.

    The FILE collision is the one that matters and is checked first: `os.replace`
    onto an existing file overwrites it silently on every platform, while onto a
    non-empty directory it raises — so a directory-only test passes even without
    the guard, which is exactly what the mutation run caught.
    """
    home, _other, proj, _folder = old_home
    rules = proj / '.claude' / 'rules'
    _write(str(rules / 'archeus-mem-app-api.md'), '# the live one')
    _write(str(proj / '.archeus' / 'memory' / 'graph.json'), '{"entities":["new"]}')

    _moved, failed = migrate.run()
    assert not failed, 'a collision was reported as a failure instead of skipped'

    assert '# the live one' in io.open(str(rules / 'archeus-mem-app-api.md'),
                                      encoding='utf-8').read(), \
        'the stale rule file overwrote the live one'
    kept = io.open(str(proj / '.archeus' / 'memory' / 'graph.json'),
                   encoding='utf-8').read()
    assert 'new' in kept, 'the stale graph overwrote the live one'
    # and neither old copy was destroyed to make room
    assert (rules / 'claudectl-mem-app-api.md').exists()
    assert (proj / '.claudectl' / 'memory' / 'graph.json').exists()


def test_a_workdir_a_hook_already_created_is_merged_into_not_skipped(old_home):
    """The destination can exist before the migration has ever run.

    Claude Code fires this package's hooks during ordinary work, and they write
    through `store.workdir`. Install the new version, let one hook run before
    opening the UI, and `<project>/.archeus/` exists holding a single sidecar.
    Skipping on a present destination would then strand that project's whole
    memory graph under the old name for good — which is what happened on a real
    machine while this rename was being written.
    """
    _home, _other, proj, _folder = old_home
    _write(str(proj / '.archeus' / 'memory' / 'dirty.log'), 'src/app.py\n')

    _moved, failed = migrate.run()
    assert not failed, failed

    # the sidecar the hook wrote is untouched, and everything else arrived
    assert (proj / '.archeus' / 'memory' / 'dirty.log').exists()
    assert (proj / '.archeus' / 'memory' / 'graph.json').exists(), \
        'the memory graph was stranded under the old name'
    assert (proj / '.archeus' / 'bash-log.txt').exists()
    assert not (proj / '.claudectl').exists(), \
        'the emptied old tree was left behind'


def test_a_failure_does_not_write_the_done_flag(old_home, monkeypatch):
    """Otherwise one locked file — an editor holding it open, a sync client —
    means everything after it is never retried."""
    real = migrate._move

    def _flaky(src, dst, moved, failed):
        if src.endswith('claudectl-events.jsonl'):
            failed.append((src, 'locked'))
            return
        return real(src, dst, moved, failed)

    monkeypatch.setattr(migrate, '_move', _flaky)
    _moved, failed = migrate.run()
    assert failed
    assert migrate.pending(), 'the flag was written despite a failure'


def test_a_clean_install_settles_in_one_run_without_walking_projects(
        monkeypatch, tmp_path):
    """Nothing from claudectl on disk. The gate is flag-only, so the first run
    still happens — it must cost a listdir, not a transcript read per project,
    and it must close the gate so it never happens again."""
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))
    monkeypatch.setattr(migrate, 'OLD_SETTINGS', str(tmp_path / 'claudectl.json'))
    os.makedirs(str(tmp_path / 'projects' / 'D--x'))

    from claude_sessions import paths
    called = []
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda *a, **k: called.append(a) or None)

    assert migrate.pending()
    moved, failed = migrate.run()
    assert (moved, failed) == ([], [])
    assert not called, 'it resolved project paths on a machine that never had claudectl'
    assert not migrate.pending()
    s = _c.load_settings()
    assert s['brand_migrated'] is True
    assert s['migrated_from'] == '', 'it claimed to have migrated something'


def test_a_hook_pointing_into_the_old_environment_is_re_pointed(old_home,
                                                                monkeypatch):
    """pipx installs into a NEW venv, so every recorded hook path still points
    into claudectl's — which `pipx uninstall claudectl` then deletes.

    Nothing notices on its own: hooks are matched by whole command string, so an
    old-path one is unrecognised rather than repaired, and `statusline
    .is_installed` only tests that the command CONTAINS the package name, so a
    dead statusline reports itself installed and prints nothing on every turn.
    """
    home, _other, _proj, _folder = old_home
    dead = str(home / 'gone' / 'claude_sessions' / 'recall_hook.py')
    _write(str(home / 'settings.json'), json.dumps({
        'hooks': {'UserPromptSubmit': [
            {'hooks': [{'type': 'command', 'command': '"C:\\gone\\python.exe" "%s"' % dead}]}]},
        'statusLine': {'type': 'command',
                       'command': '"C:\\gone\\pythonw.exe" "%s"'
                                  % str(home / 'gone' / 'claude_sessions' / 'statusline_cli.py')},
    }))
    _moved, failed = migrate.run()
    assert not failed, failed

    from claude_sessions import statusline
    s = json.load(io.open(str(home / 'settings.json'), encoding='utf-8'))
    hook = s['hooks']['UserPromptSubmit'][0]['hooks'][0]['command']
    sl = s['statusLine']['command']
    pkg = os.path.dirname(os.path.abspath(migrate.__file__))
    # the interpreter moved with the package, so that half is rebuilt too — as
    # `sys.executable` for a hook, and as `statusline._interpreter()` for the
    # statusline, which runs on every turn and must stay windowless
    for cmd, script, exe in ((hook, 'recall_hook.py', sys.executable),
                             (sl, 'statusline_cli.py', statusline._interpreter())):
        assert os.path.join(pkg, script) in cmd, cmd
        assert 'gone' not in cmd, 'it still points into the environment being removed'
        assert exe in cmd, 'the interpreter was left in the old venv'


def test_a_live_command_is_left_alone_even_when_the_filename_is_one_of_ours(
        old_home, tmp_path):
    """Only a path that is BOTH dead and one of ours may be rewritten.

    The filename is deliberately `recall_hook.py` — the same name the bundled
    hook has. A user who wrote their own, or who runs a fork from a checkout,
    has a LIVE path whose basename collides with ours, and the only thing
    standing between that and being silently re-pointed at this installation is
    the "does it still resolve?" check. A test using a made-up filename proves
    nothing: the second check catches that one anyway.
    """
    home, _other, _proj, _folder = old_home
    theirs = tmp_path / 'fork' / 'claude_sessions' / 'recall_hook.py'
    theirs.parent.mkdir(parents=True)
    theirs.write_text('# their own', encoding='utf-8')
    mine = '"python" "%s" --flag' % theirs
    _write(str(home / 'settings.json'), json.dumps({
        'hooks': {'PreToolUse': [{'hooks': [{'type': 'command', 'command': mine}]}]}}))
    migrate.run()
    s = json.load(io.open(str(home / 'settings.json'), encoding='utf-8'))
    assert s['hooks']['PreToolUse'][0]['hooks'][0]['command'] == mine, \
        'a hook that still resolves was re-pointed at this installation'


def test_the_coinstall_warning_names_the_command_that_repairs_it(monkeypatch):
    """Both distributions ship `claude_sessions`, so `pip uninstall claudectl`
    deletes archeus's files and leaves it listed as installed but unimportable.
    No packaging metadata expresses 'conflicts with', so saying so is the only
    defence — and it has to name the fix, not just the hazard."""
    import importlib.metadata as md
    monkeypatch.setattr(md, 'distribution', lambda name: object())
    msg = migrate.coinstalled_warning()
    assert 'pip uninstall claudectl' in msg and '--force-reinstall archeus' in msg

    def _absent(name):
        raise md.PackageNotFoundError(name)
    monkeypatch.setattr(md, 'distribution', _absent)
    assert migrate.coinstalled_warning() == '', 'it warns on a clean install'


def test_the_migration_still_knows_both_names():
    """The rename was done by substitution, and a substitution pass over this
    repo once rewrote migrate.py's own `OLD` to the new name.

    That is the worst failure this module has: `OLD == NEW` makes every move a
    no-op, `_has_old_artifacts` finds nothing, and the done flag is written
    anyway — so every existing user's settings, caches and memory graphs stay
    under the old name forever, and nothing anywhere reports a problem. It went
    unnoticed at the time because the same pass rewrote the tests too, so they
    kept passing.

    Asserting that the two constants DIFFER is what survives that: a blind
    substitution collapses them into each other, and no rewrite of this file
    can make the comparison true again.
    """
    assert migrate.OLD != migrate.NEW
    assert migrate.OLD_WORKDIR != migrate.NEW_WORKDIR
    assert not migrate.OLD_SETTINGS.endswith(os.path.basename(_c.settings_file)), \
        'the migration is looking for the settings file it is migrating TO'


def test_the_workdir_name_the_migration_targets_is_the_one_store_uses():
    """Two spellings of the destination is two chances to disagree, and the
    disagreement would be silent: the move would succeed into a directory
    nothing ever reads."""
    assert migrate.NEW_WORKDIR == store.WORKDIR


def test_the_scheduler_prefix_the_sweep_looks_for_is_not_the_one_in_use():
    """Same failure as `OLD == NEW` above, in the one constant that is spelled
    out in two modules: collapse them and the sweep deletes the live task and
    re-creates it, for ever, on every machine."""
    from claude_sessions import loops
    assert loops.TASK_PREFIX == migrate.NEW + '-loop-'
    assert migrate.OLD_TASK_PREFIX != loops.TASK_PREFIX


# ── the repair is not one-shot ────────────────────────────────

def test_the_repair_runs_after_the_migration_flag_is_set(old_home, monkeypatch):
    """The whole reason this is a separate entry point.

    `_repoint` only rewrites a DEAD path, and the single run the migration gave
    it happened at the one moment when the old paths still resolve: you install
    into the new environment, archeus starts, the repair finds nothing, the flag
    closes — and only THEN does `pipx uninstall claudectl` delete the venv every
    recorded command points into. Same for a checkout that is moved or renamed
    afterwards, and for a machine that never had the old name at all.
    """
    home, _other, _proj, _folder = old_home
    _c.save_settings(dict(_c.load_settings(), brand_migrated=True))
    assert not migrate.pending(), 'the fixture no longer reaches the case'
    dead = str(home / 'gone' / 'claude_sessions' / 'recall_hook.py')
    _write(str(home / 'settings.json'), json.dumps({
        'hooks': {'UserPromptSubmit': [
            {'hooks': [{'type': 'command', 'command': '"C:\\gone\\python.exe" "%s"' % dead}]}]}}))

    fixed, failed = migrate.repair_commands([str(home)])
    assert not failed, failed
    assert fixed, 'a dead hook was left dead once the migration flag was set'
    s = json.load(io.open(str(home / 'settings.json'), encoding='utf-8'))
    cmd = s['hooks']['UserPromptSubmit'][0]['hooks'][0]['command']
    assert os.path.join(os.path.dirname(os.path.abspath(migrate.__file__)),
                        'recall_hook.py') in cmd
    assert 'gone' not in cmd


def test_a_repair_does_not_stamp_the_install_as_having_come_from_the_old_name(
        old_home):
    """`_mark_done` reads the list of things that moved to decide whether to
    write `migrated_from`. A routine hook repair years later is not a migration,
    and recording it as one is how a support question gets the wrong answer."""
    home, _other, _proj, _folder = old_home
    os.remove(str(home / 'claudectl.json'))
    for name in list(os.listdir(str(home))):
        if name.startswith('claudectl'):
            import shutil
            p = str(home / name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    dead = str(home / 'gone' / 'claude_sessions' / 'recall_hook.py')
    _write(str(home / 'settings.json'), json.dumps({
        'hooks': {'UserPromptSubmit': [
            {'hooks': [{'type': 'command', 'command': '"py" "%s"' % dead}]}]}}))
    migrate.run()
    assert _c.load_settings()['migrated_from'] == '', \
        'a hook repair was recorded as a migration off the old name'


def test_the_statusline_keeps_the_windowless_interpreter(old_home, monkeypatch):
    """The statusline runs on EVERY conversation turn, so repairing it with
    `sys.executable` — python.exe — puts a console window on screen once a turn
    on Windows. `statusline._command()` is the same script path with
    `_interpreter()`'s pythonw preference, which is why that function exists."""
    from claude_sessions import statusline
    home, _other, _proj, _folder = old_home
    monkeypatch.setattr(statusline, '_interpreter', lambda: 'WINDOWLESS')
    _write(str(home / 'settings.json'), json.dumps({
        'statusLine': {'type': 'command',
                       'command': '"C:\\gone\\pythonw.exe" "%s"'
                                  % str(home / 'gone' / 'statusline_cli.py')}}))
    migrate.repair_commands([str(home)])
    sl = json.load(io.open(str(home / 'settings.json'),
                           encoding='utf-8'))['statusLine']['command']
    assert sl == statusline._command()
    assert 'WINDOWLESS' in sl, 'the repair fell back to the console interpreter'


def test_a_dead_statusline_stops_reporting_itself_as_working(old_home):
    """`is_installed` asks only whether the command names this package, so an
    entry into a deleted environment reported itself installed and printed
    nothing, on every turn, for ever."""
    from claude_sessions import statusline
    home, _other, _proj, _folder = old_home
    _write(str(home / 'settings.json'), json.dumps({
        'tui': 'fullscreen',
        'statusLine': {'type': 'command',
                       'command': '"py" "%s"'
                                  % str(home / 'gone' / 'claude_sessions' / 'statusline_cli.py')}}))
    assert statusline.is_installed(str(home)), 'the fixture no longer reaches the case'
    assert 'dead-command' in [k for k, _m in statusline.blockers(str(home))]
    _write(str(home / 'settings.json'), json.dumps({
        'tui': 'fullscreen',
        'statusLine': {'type': 'command', 'command': statusline._command()}}))
    assert 'dead-command' not in [k for k, _m in statusline.blockers(str(home))]


# ── the second pass: what the path move could not reach ───────

OLD_MEM = '<!-- CLAUDECTL:MEMORY:START -->\nstale digest\n<!-- CLAUDECTL:MEMORY:END -->'
NEW_MEM = '<!-- ARCHEUS:MEMORY:START -->\nlive digest\n<!-- ARCHEUS:MEMORY:END -->'
OLD_AGENTS = ('<!-- CLAUDECTL:AGENTS:START -->\n- **python-pro**\n'
              '<!-- CLAUDECTL:AGENTS:END -->')


@pytest.fixture()
def swept(monkeypatch, tmp_path):
    """A finished move: the flag is set, `migrated_from` records the old name,
    and one account has one project."""
    home = tmp_path / '.claude'
    proj = tmp_path / 'work' / 'myproject'
    enc = 'D--work-myproject'
    _write(str(home / 'projects' / enc / 'sess.jsonl'),
           json.dumps({'cwd': str(proj), 'type': 'user'}) + '\n')
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_c, 'settings_file', str(home / 'archeus.json'))
    _c.save_settings({'brand_migrated': True, 'migrated_from': 'claudectl'})
    from claude_sessions import paths
    monkeypatch.setattr(paths, '_path_cache', {})
    return home, proj


def _md(path):
    return io.open(path, encoding='utf-8').read()


def test_the_sweep_drops_the_orphan_and_renames_the_one_with_no_successor(swept):
    """The shape this was written for, measured on three real projects.

    `upsert_block` needs BOTH new sentinels to replace a block, so after the
    rename it could not see the old one and APPENDED a second block beside it.
    The orphan then goes into every session for ever, saying whatever it said the
    day the rename landed — and the memory one tells the model to run a command
    that no longer exists.

    The two halves are one rule read twice: a block the new name already owns is
    superseded and goes; a block with no successor is the live one under an old
    name, and renaming it in place is what stops the NEXT build appending a
    duplicate of it too.
    """
    home, proj = swept
    _write(str(proj / 'CLAUDE.md'),
           '# myproject\n\nmy own prose\n\n%s\n\n%s\n\n%s\n' % (OLD_MEM, OLD_AGENTS, NEW_MEM))

    fixed, failed = migrate.sweep([str(home)])
    assert not failed, failed
    assert fixed, 'it found nothing to do'

    text = _md(str(proj / 'CLAUDE.md'))
    assert 'CLAUDECTL' not in text
    assert text.count('<!-- ARCHEUS:MEMORY:START -->') == 1, 'two blocks, one renderer'
    assert 'live digest' in text and 'stale digest' not in text
    assert '<!-- ARCHEUS:AGENTS:START -->' in text and 'python-pro' in text, \
        'the block with no successor was deleted instead of renamed'
    assert 'my own prose' in text


def test_a_half_written_block_is_left_exactly_as_it_is(swept):
    """A start with no end is possible — a hand edit, a torn pre-atomic write, a
    model that echoed one sentinel. Renaming it would be the worst outcome
    available: `upsert_block` indexes the FIRST occurrence, so a stray new-name
    start captures every later write and orphans the real block for ever."""
    home, proj = swept
    text = ('# p\n\n<!-- CLAUDECTL:MEMORY:START -->\nhalf\n\n%s\n' % NEW_MEM)
    _write(str(proj / 'CLAUDE.md'), text)
    migrate.sweep([str(home)])
    assert _md(str(proj / 'CLAUDE.md')) == text, 'a half pair was touched'


def test_the_keep_fence_is_renamed_and_never_removed(swept):
    """KEEP is the user's own fence, not a generated block: it may appear many
    times, and what is inside it is prose nothing may delete. Until it is
    renamed, `claude_md._KEEP_RE` cannot see it and the compression prompt is
    free to rewrite what it was protecting."""
    from claude_sessions import claude_md
    home, proj = swept
    fence = ('<!-- CLAUDECTL:KEEP:START -->\nhand written %d\n'
             '<!-- CLAUDECTL:KEEP:END -->')
    _write(str(proj / 'CLAUDE.md'),
           '# p\n\n%s\n\n%s\n\n%s\n' % (fence % 1, fence % 2, NEW_MEM))
    migrate.sweep([str(home)])

    text = _md(str(proj / 'CLAUDE.md'))
    assert 'hand written 1' in text and 'hand written 2' in text
    assert len(claude_md._KEEP_RE.findall(text)) == 2, \
        'the fence is still invisible to the thing that protects it'


def test_the_sweep_reaches_every_account(swept, tmp_path, monkeypatch):
    """`run()` is forbidden to use `all_config_dirs()` — it reads the settings
    file it has not moved yet. The sweep is the INVERSION of that rule: by the
    time it runs, the new settings file is the only place the account list
    exists, and reusing `_old_config_dirs()` here would sweep the default
    account and silently skip every other one.

    Called with NO argument on purpose: passing the directories in would prove
    only that the loop body works, and the mutation run says so — the bug this
    is about lives entirely in which function supplies that list.
    """
    home, proj = swept
    other = tmp_path / 'acct2'
    proj2 = tmp_path / 'work' / 'second'
    _write(str(other / 'projects' / 'D--work-second' / 's.jsonl'),
           json.dumps({'cwd': str(proj2), 'type': 'user'}) + '\n')
    for p in (proj, proj2):
        _write(str(p / 'CLAUDE.md'), '# p\n\n%s\n\n%s\n' % (OLD_MEM, NEW_MEM))
    # the real one would name the real ~/.claude, which is not this test's to
    # walk; `_old_config_dirs()` reads the monkeypatched settings_file and so
    # answers with the default account only — which is the mutant
    monkeypatch.setattr(_c, 'all_config_dirs',
                        lambda: [('default', str(home)), ('second', str(other))])

    migrate.sweep()
    for p in (proj, proj2):
        assert 'CLAUDECTL' not in _md(str(p / 'CLAUDE.md')), p


def test_the_sweep_runs_once_and_closes_its_own_gate(swept, monkeypatch):
    """Its own flag, not `brand_migrated`: that one is already True on every
    install this has to reach, so gating on it would mean the sweep never runs
    at all."""
    home, proj = swept
    _write(str(proj / 'CLAUDE.md'), '# p\n\n%s\n\n%s\n' % (OLD_MEM, NEW_MEM))
    assert migrate.sweep_pending()
    migrate.sweep([str(home)])
    assert not migrate.sweep_pending()
    assert _c.load_settings()['brand_sweep'] is True

    from claude_sessions import paths
    called = []
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda *a, **k: called.append(a) or None)
    assert migrate.sweep([str(home)]) == ([], [])
    assert not called, 'it walked the projects again after closing its gate'


def test_a_machine_that_never_had_the_old_name_is_not_walked(swept, monkeypatch):
    """`migrated_from` is the record of a move that actually happened, which is
    exactly the question here. A clean install must pay one settings read."""
    home, _proj = swept
    _c.save_settings(dict(_c.load_settings(), migrated_from=''))
    from claude_sessions import paths
    called = []
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda *a, **k: called.append(a) or None)
    assert migrate.sweep([str(home)]) == ([], [])
    assert not called
    assert not migrate.sweep_pending(), 'it will re-walk on every start for ever'


def test_a_write_failure_does_not_close_the_sweep_gate(swept, monkeypatch):
    """A locked file — an editor holding it open, a sync client — is retried on
    the next start rather than left half done for good.

    The failure is injected at `upsert_block` and NOT at `write_atomic`, which
    was the first version: `save_settings` writes through `write_atomic` too, so
    stubbing that one also blocks the flag write and the test passes whether or
    not the guard is there. The mutation run is what said so.
    """
    from claude_sessions import claude_md
    home, proj = swept
    _write(str(proj / 'CLAUDE.md'), '# p\n\n%s\n\n%s\n' % (OLD_MEM, NEW_MEM))
    monkeypatch.setattr(claude_md, 'upsert_block', lambda *a, **k: (False, '', ''))
    _fixed, failed = migrate.sweep([str(home)])
    assert failed
    assert migrate.sweep_pending(), 'the gate closed over a file it could not write'


class _R:
    def __init__(self, returncode=0, stdout=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ''


def test_the_old_scheduler_entry_is_replaced_not_left_firing(swept, monkeypatch):
    """A scheduler entry is a NAME, so no path move could reach it: the registry
    moved and the task is still `claudectl-loop-<id>`. `loops.is_scheduled` then
    reports the loop as unscheduled while the old entry goes on firing — and the
    moment the user schedules it again from the UI there are two of them.

    Replaced rather than renamed, because the old entry's command line also names
    the interpreter of the environment the user just removed: a rename would give
    a correctly named task that fails silently for ever.
    """
    from claude_sessions import loops, proc
    home, _proj = swept
    loops._save([{'id': 'abc123', 'interval': '15m', 'cfgdir': str(home)}], str(home))
    calls = []

    def fake_run(argv, **kw):
        calls.append(list(argv))
        if argv[:2] == ['schtasks', '/query']:
            return _R(0 if migrate.OLD_TASK_PREFIX in argv[3] else 1)
        return _R(0)
    monkeypatch.setattr(proc, 'WINDOWS', True)
    monkeypatch.setattr(proc, 'run', fake_run)

    migrate.sweep([str(home)])
    deleted = [c for c in calls if c[:2] == ['schtasks', '/delete']]
    created = [c for c in calls if c[:2] == ['schtasks', '/create']]
    assert deleted and migrate.OLD_TASK_PREFIX + 'abc123' in deleted[0], \
        'the old task was left in the scheduler, still firing'
    assert created and loops.TASK_PREFIX + 'abc123' in created[0], \
        'the loop was unscheduled and never re-registered'


def test_the_old_cron_line_is_dropped_and_the_users_own_lines_survive(
        swept, monkeypatch):
    """`loops._cron_write` filters on the NEW tag only, so the old line survives
    every rewrite it will ever do. It has to be stripped once, here — and the
    crontab belongs to the user, so everything else in it is carried through."""
    from claude_sessions import loops, proc
    home, _proj = swept
    loops._save([{'id': 'abc123', 'interval': '1h', 'cfgdir': str(home)}], str(home))
    mine = '0 4 * * * /usr/bin/backup.sh'
    old = '*/15 * * * * python -m claude_sessions --loop-run abc123 # %sabc123' % (
        migrate.OLD_TASK_PREFIX)
    written = []

    def fake_run(argv, stdin=None, **kw):
        if argv == ['crontab', '-l']:
            return _R(0, mine + '\n' + old + '\n')
        if argv == ['crontab', '-']:
            written.append(stdin or '')
        return _R(0)
    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(proc, 'run', fake_run)

    migrate.sweep([str(home)])
    assert written, 'the crontab was never rewritten'
    assert mine in written[0], "it dropped one of the user's own lines"
    assert migrate.OLD_TASK_PREFIX not in written[0]
    assert any(loops._cron_tag('abc123') in w for w in written), \
        'the loop was unscheduled and never re-registered'


def test_the_warning_names_the_stale_env_vars_and_the_old_plugin(monkeypatch,
                                                                 tmp_path):
    """Two things archeus must not fix on the user's behalf: a value in their
    shell profile, and a plugin whose caches are only ever written through the
    `claude` CLI. Both have been silently doing nothing since the rename."""
    from claude_sessions import plugins
    monkeypatch.setenv('CLAUDECTL_DEBUG', '1')
    msg = migrate.stale_env_warning()
    assert 'CLAUDECTL_DEBUG' in msg and 'ARCHEUS_DEBUG' in msg
    monkeypatch.delenv('CLAUDECTL_DEBUG')
    assert migrate.stale_env_warning() == '', 'it warns about a clean environment'

    _write(str(tmp_path / 'plugins' / 'installed_plugins.json'),
           json.dumps({'version': 2, 'plugins': {'claudectl@claudectl': [{'scope': 'user'}]}}))
    monkeypatch.setattr(plugins, 'plugins_dir', lambda c=None: str(tmp_path / 'plugins'))
    out = migrate.stale_plugin_warning()
    assert 'claudectl@claudectl' in out and '/plugin install archeus@archeus' in out

    _write(str(tmp_path / 'plugins' / 'installed_plugins.json'),
           json.dumps({'version': 2, 'plugins': {}}))
    assert migrate.stale_plugin_warning() == '', 'it warns with nothing installed'
