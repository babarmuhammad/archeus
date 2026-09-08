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
