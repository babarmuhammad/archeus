"""T-1182 · the uncovered high-risk branches of ``claude_sessions/migrate.py``.

Source under test: ``claude_sessions/migrate.py`` lines **342-685** (tip
56d53504) — the body of ``run()``, ``sweep_pending``, ``sweep``,
``_mark_sweep_done``, ``_sweep_claude_md``, ``_sweep_loops``,
``stale_env_warning``, ``_mark_done``, ``_encoded_folders`` and
``_rederive_config_paths``. Everything above line 342 (``_move``, ``_merge``,
``_repoint``, ``repair_commands``, ``_old_config_dirs``, ``pending``,
``_has_old_artifacts``) is read-only context: it is faked or driven, never the
branch this file owns. Existing coverage read first: ``tests/test_migration.py``.

The ten final cases: the card's ten probes, each tagged with the probe it came
from, the source lines whose branch it owns and the test that owns them, in the
risk order the accept asks for — fail-closed and denial first, then boundaries,
then error paths. Case 9 (probe 4) is owned by two tests.

  1. probe 1 — migrate.py:379, 381: a failure recorded anywhere, including the
     repair step, keeps the done flag unwritten.
     ``test_a_repair_failure_keeps_the_done_flag_unwritten``
  2. probe 6 — migrate.py:559-561, 565-570: a scheduler QUERY that fails never
     reaches a destructive update (no ``schtasks /delete``, no ``crontab -``
     write of an emptied table).
     ``test_a_scheduler_query_that_fails_writes_nothing_down``
  3. probe 8 — migrate.py:571-574 + 469-470: a REFUSED crontab rewrite is
     recorded, nothing is re-registered, the sweep gate stays open.
     ``test_a_crontab_rewrite_failure_is_recorded_and_retried``
  4. probe 5 — migrate.py:528-531 + 469-470: an atomic write that answers False
     is recorded and the file keeps its bytes; the gate stays open.
     ``test_a_failed_sentinel_rewrite_keeps_the_old_bytes``
  5. probe 2 — migrate.py:501-508 + 469-470: the sweep gate is about WRITES, so
     a file that cannot be read closes it instead of re-walking forever.
     ``test_an_unreadable_file_does_not_hold_the_gate_open``
  6. probe 9 — migrate.py:589-595: the stale-environment warning names
     variables, never their values, and ignores any name outside the prefix.
     ``test_the_env_warning_names_the_variable_and_never_the_value``
  7. probe 7 — migrate.py:552, 556-563, 575-579: only the OLD-named task is
     deleted; a live entry and a row with no id survive, and every delete
     precedes the re-create.
     ``test_a_lost_task_never_takes_a_live_one_with_it``
  8. probe 3 — migrate.py:513-527: sentinels that do not pair are left byte for
     byte, with no write at all.
     ``test_markers_that_do_not_pair_are_left_byte_for_byte``
  9. probe 4 — migrate.py:511-525: a stale block sitting AFTER the live one is
     dropped, not renamed, and the prose around both survives
     (``test_a_stale_block_after_the_live_one_is_dropped_not_renamed``), and two
     stale blocks must not both end up owning the new sentinel
     (``test_two_stale_duplicates_cannot_both_own_the_new_sentinel``,
     ``xfail(strict=True)`` — a source defect: the contract is migrate.py:485-488,
     the first-occurrence index is claude_md.py:59-60)
  10. probe 10 — migrate.py:376 + 682-685: a crash inside the path rederive
     writes no settings and leaves the gate (and the four import-time paths)
     alone. ``test_a_crash_in_the_path_rederive_writes_no_settings``

Three further tests cover boundaries in the same slice that no test reached:
the order ``run()`` moves things in (371), the ``projects/<enc>`` mirror that
must keep its history bytes (447-457), and the success side of the rederive.

Every host seam is faked BEFORE the module is entered: the settings path, the
old settings file, the account list, the project-path resolver, the OS
scheduler runner and the atomic writer. Nothing here reads a real home
directory, a credential file, the OS scheduler, the editor or a pager, and
nothing writes outside ``tmp_path``. The environment is replaced with a
synthetic mapping for the one function that reads it.
"""
import io
import json
import os

import pytest

from claude_sessions import config as _c
from claude_sessions import loops, migrate, paths, proc

#: a fake encoded project folder name (`paths.encode_component`'s alphabet)
ENC = 'P--work-proj'
ENC2 = 'P--work-lost'

#: the genuine implementation, captured before any fixture can cover it; one
#: test needs it to actually resolve the setting the move just made readable
_REAL_GET_CONFIG_DIR = _c.get_config_dir


# ── helpers ──────────────────────────────────────────────────

def _write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def _tag(name, part, old=True):
    return '<!-- %s:%s:%s -->' % ('CLAUDECTL' if old else 'ARCHEUS', name, part)


def _block(name, body, old=True):
    return '\n'.join((_tag(name, 'START', old), body, _tag(name, 'END', old)))


class _Res:
    """Stands in for one `proc.run` result (never a real process)."""

    def __init__(self, returncode=0, stdout=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ''


class _FakeOS:
    """`os` with a synthetic environment; everything else delegates."""

    def __init__(self, real, environ):
        self._real = real
        self.environ = dict(environ)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture()
def fake_home(monkeypatch, tmp_path):
    """An account tree under tmp_path with every host seam closed.

    `config.settings_file`, `migrate.OLD_SETTINGS`, `config.get_config_dir` and
    `paths.find_actual_path` are all redirected BEFORE anything in migrate is
    called, and the four import-time `config` constants that
    `_rederive_config_paths` overwrites are taken over by monkeypatch so they
    are restored whatever a test does with them.
    """
    home = tmp_path / 'acct1'
    other = tmp_path / 'acct2'
    home.mkdir()
    other.mkdir()
    (home / 'projects').mkdir()
    monkeypatch.setattr(_c, 'settings_file', str(home / 'archeus.json'))
    monkeypatch.setattr(migrate, 'OLD_SETTINGS', str(home / 'claudectl.json'))
    monkeypatch.setattr(_c, 'get_config_dir', lambda: str(home))
    for attr in ('config_dir', 'projects_dir', 'last_session_file',
                 'global_claude_md'):
        monkeypatch.setattr(_c, attr, getattr(_c, attr))
    monkeypatch.setattr(paths, '_path_cache', {})
    return tmp_path, home, other


def _sweep_gate_open(migrated_from='claudectl'):
    """A finished move, so `sweep()` gets past its two gates."""
    _c.save_settings({'brand_migrated': True, 'migrated_from': migrated_from})


def _seed_old_install(tmp_path, home, other, extra=None):
    """The old-name artifacts `run()` walks, plus one project and its mirror."""
    settings = {'theme': 'nord',
                'accounts': [{'name': 'second', 'dir': str(other)}]}
    settings.update(extra or {})
    _write(str(home / 'claudectl.json'), json.dumps(settings))
    _write(str(home / 'claudectl-stats.json'), '{}')
    _write(str(other / 'claudectl-versions.json'), '{}')
    proj = tmp_path / 'work' / 'proj'
    _write(str(proj / '.claudectl' / 'memory' / 'graph.json'), '{"entities":[]}')
    _write(str(home / 'projects' / ENC / 'sess.jsonl'),
           json.dumps({'cwd': str(proj), 'type': 'user'}) + '\n')
    return proj


# ── 1. fail-closed: the done flag (probe 1) ─────────────────

def test_a_repair_failure_keeps_the_done_flag_unwritten(fake_home, monkeypatch):
    """migrate.py:379 + 381.

    `failed.extend(_rfailed)` is the only thing connecting a hook-repair failure
    to `if not failed: _mark_done(moved)`. The closest existing test,
    `test_a_failure_does_not_write_the_done_flag`, injects its fault at
    `migrate._move`, so deleting the extend (or calling `_mark_done`
    unconditionally, which is what an "idempotence" tweak would do) leaves that
    test green while every later start silently skips the repair that failed:
    `pending()` sees the leftover file, `repair_commands` never runs again, and
    the hooks stay broken for good with the flag set.
    """
    tmp_path, home, other = fake_home
    proj = _seed_old_install(tmp_path, home, other)
    before = _read(str(home / 'claudectl.json'))
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda enc, folder=None, **kw: str(proj))
    monkeypatch.setattr(migrate, 'repair_commands',
                        lambda cfgdirs=None, **kw: ([], [(str(home), 'locked')]))

    moved, failed = migrate.run()
    assert failed, 'the repair fault never reached the caller'
    assert moved, 'the fixture no longer moves anything'
    assert migrate.pending(), 'the gate closed over a run that failed'
    assert _read(str(home / 'archeus.json')) == before, \
        'the settings file was rewritten even though the run failed'


# ── 2. denial: a scheduler query that cannot answer (probe 6) 

def test_a_scheduler_query_that_fails_writes_nothing_down(fake_home, monkeypatch):
    """migrate.py:559-561 and 565-570.

    Both halves read the scheduler before touching it and are supposed to stop
    there, leaving the registry alone. Drop the `crontab -l` guard and the code
    writes an EMPTY crontab back over the user's own (and then re-registers the
    loop, so the entry appears twice); drop the `schtasks /query` guard and it
    deletes a task on the strength of a query that never answered. The closest
    existing tests —
    `test_the_old_cron_line_is_dropped_and_the_users_own_lines_survive` and
    `test_the_old_scheduler_entry_is_replaced_not_left_firing` — answer every
    process call with rc=0, so neither guard has ever run in the suite.
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    loops._save([{'id': 'abc123', 'interval': '15m'}], str(home))
    calls = []

    def posix_run(argv, **kw):
        calls.append(list(argv))
        return _Res(1) if argv[:2] == ['crontab', '-l'] else _Res(0)

    def win_run(argv, **kw):
        calls.append(list(argv))
        if argv[:2] == ['schtasks', '/query']:
            return None                       # schtasks did not answer at all
        return _Res(0)

    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(proc, 'run', posix_run)
    _sweep_gate_open()
    fixed, failed = migrate.sweep([str(home)])
    assert (fixed, failed) == ([], []), 'a missing cron was reported as a failure'
    assert not [c for c in calls if c[:2] == ['crontab', '-']], \
        'the user crontab was rewritten — and emptied — on a query that failed'

    del calls[:]
    monkeypatch.setattr(proc, 'WINDOWS', True)
    monkeypatch.setattr(proc, 'run', win_run)
    _sweep_gate_open()
    fixed, failed = migrate.sweep([str(home)])
    assert (fixed, failed) == ([], [])
    assert not [c for c in calls if c[:2] == ['schtasks', '/delete']], \
        'a task was deleted on the strength of a query that never answered'
    assert not [c for c in calls if c[:2] == ['schtasks', '/create']], \
        'the loop was re-registered while its state is unknown'


# ── 3. error path: the crontab write itself (probe 8) ───────

def test_a_crontab_rewrite_failure_is_recorded_and_retried(fake_home, monkeypatch):
    """migrate.py:571-574 + 469-470.

    `crontab -` can refuse (a read-only spool, a locked spool directory, a
    disabled cron daemon). The old line is still in place then, so
    re-registering the loop would give two of them — one firing the old module —
    and closing the gate would hide the duplicate for good, because `pending()`
    is already clear. The nearest existing test,
    `test_the_old_cron_line_is_dropped_and_the_users_own_lines_survive`, answers
    every process call with rc=0, so this branch has never run in the suite.
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    loops._save([{'id': 'abc123', 'interval': '1h'}], str(home))
    mine = '0 4 * * * /usr/bin/backup.sh'
    stale = '*/15 * * * * python -m claude_sessions --loop-run abc123 # %sabc123' \
            % migrate.OLD_TASK_PREFIX
    writes = []

    def fake_run(argv, **kw):
        if argv[:2] == ['crontab', '-l']:
            return _Res(0, mine + '\n' + stale + '\n')
        if argv[:2] == ['crontab', '-']:
            writes.append(kw.get('stdin') or '')
        return _Res(1)                        # the write did not land

    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(proc, 'run', fake_run)

    fixed, failed = migrate.sweep([str(home)])
    assert fixed == [], 'a crontab that was never written counted as repaired'
    assert failed[:1] == [(str(home), 'could not rewrite the crontab')], failed
    assert writes, 'the fixture no longer reaches the write'
    assert not any(loops._cron_tag('abc123') in w for w in writes), \
        'the loop was re-registered while the old line was still in place'
    assert migrate.sweep_pending(), \
        'the gate closed over a crontab it could not write'


# ── 4. error path: the atomic write of the sentinels (probe 5) 

def test_a_failed_sentinel_rewrite_keeps_the_old_bytes(fake_home, monkeypatch):
    """migrate.py:528-531 + 469-470.

    `write_atomic` answers False rather than raising (a locked file, a full
    disk). The only test standing near here,
    `test_a_write_failure_does_not_close_the_sweep_gate`, says in its own
    docstring that it injects at `upsert_block` and NOT at `write_atomic`,
    because `save_settings` writes through it too — so the rename's own write
    has never been made to fail. Stubbing it for ONE path reaches that write and
    still lets the flag be saved, which is what lets this assert the identity of
    the failure, the `fixed` list and the untouched bytes of the file.
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    md = str(home / 'CLAUDE.md')
    text = '# p\n\nmy own prose\n\n' + _block('AGENTS', '- **python-pro**') + '\n'
    _write(md, text)
    real_write = _c.write_atomic

    def fake_write_atomic(path, body, **kw):
        if os.path.abspath(str(path)) == md:
            return False                      # locked by an editor / sync client
        return real_write(path, body, **kw)
    monkeypatch.setattr(_c, 'write_atomic', fake_write_atomic)

    fixed, failed = migrate.sweep([str(home)])
    assert failed == [(md, 'could not rewrite the sentinels')], failed
    assert fixed == [], 'a file that was never written counted as repaired'
    assert _read(md) == text, 'the file on disk was changed by a failed write'
    assert migrate.sweep_pending(), \
        'the gate closed over a file it could not write'


# ── 5. the gate's other half: a read that fails (probe 2) ───

def test_an_unreadable_file_does_not_hold_the_gate_open(fake_home, monkeypatch):
    """migrate.py:501-508 + 469-470.

    `_mark_sweep_done` closes on everything except a WRITE failure, on purpose:
    a CLAUDE.md that cannot be read may contain no sentinel at all, and treating
    that as a failure would re-walk every account on every start for ever — and
    report a file the sweep never even looked at as a permanent error. Record
    the read failure (the obvious "symmetric" fix) and the second pass never
    closes. Nothing injects a failure at the read: `tests/test_migration.py`
    only ever stubs `_move`, `repair_commands`, `proc.run` and `upsert_block`.
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    md = str(home / 'CLAUDE.md')
    text = '# p\n\nmy own prose\n\n' + _block('LOOP', 'journal') + '\n'
    _write(md, text)
    real_open = io.open

    def fake_open(path, *a, **kw):
        if os.path.abspath(str(path)) == md:
            raise OSError('locked by another program')
        return real_open(path, *a, **kw)
    monkeypatch.setattr(migrate, 'open', fake_open, raising=False)

    fixed, failed = migrate.sweep([str(home)])
    assert (failed, fixed) == ([], []), \
        'a read failure was recorded as if it had been a write failure'
    assert not migrate.sweep_pending(), \
        'one unreadable file re-walks every account on every start'
    assert _read(md) == text, 'the file was rewritten behind a failed read'


# ── 6. denial: what the warning may say (probe 9) ───────────

def test_the_env_warning_names_the_variable_and_never_the_value(fake_home,
                                                                monkeypatch):
    """migrate.py:589-595.

    `CLAUDECTL_*` values are secrets in the wild (an API key, a token) and this
    string is shown in the UI. The existing test,
    `test_the_warning_names_the_stale_env_vars_and_the_old_plugin`, only checks
    that the OLD and the NEW name both appear; it never checks that the VALUE
    stays out, nor that a name merely STARTING with the old brand is left off
    the list. The environment is a synthetic mapping, never the host's.
    """
    secret = 'sk-FAKE-NOT-A-REAL-CREDENTIAL-77'
    monkeypatch.setattr(migrate, 'os', _FakeOS(os, {
        'CLAUDECTL_MODEL': secret,
        'CLAUDECTL_DEBUG': secret,
        'CLAUDECTL': secret,
        'CLAUDECTLX': secret,
        'ARCHEUS_DEBUG': '1',
    }))
    msg = migrate.stale_env_warning()
    assert 'CLAUDECTL_DEBUG is now ARCHEUS_DEBUG' in msg
    assert 'CLAUDECTL_MODEL is now ARCHEUS_MODEL' in msg
    assert msg.index('CLAUDECTL_DEBUG') < msg.index('CLAUDECTL_MODEL'), \
        'the names are not sorted, so the warning reorders under a rename'
    assert secret not in msg, 'the VALUE of a user variable leaked into the warning'
    assert 'CLAUDECTLX' not in msg, 'a name outside the prefix was reported'
    assert 'CLAUDECTL is now' not in msg, 'the bare brand name was reported as a var'
    assert 'ARCHEUS_DEBUG is now' not in msg, 'it warns about the new name too'

    monkeypatch.setattr(migrate, 'os', _FakeOS(os, {'PATH': '/bin', 'HOME': '/h'}))
    assert migrate.stale_env_warning() == '', 'it warns on a clean environment'


# ── 7. boundary: scheduler entries that are not ours (probe 7) 

def test_a_lost_task_never_takes_a_live_one_with_it(fake_home, monkeypatch):
    """migrate.py:552, 556-563, 575-579.

    Three separate survivals in one loop body: the registry row with no `id` is
    not a schedulable entry, the loop whose OLD task does not exist must not be
    deleted or re-registered (its live task is `archeus-loop-…` and is firing
    correctly — deleting it stops the schedule, re-registering it duplicates it),
    and every delete must precede the create. The closest existing test,
    `test_the_old_scheduler_entry_is_replaced_not_left_firing`, registers ONE row
    that does have an id and answers every query with rc=0, so the `r.get('id')`
    filter and the skip path have never run.
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    loops._save([{'id': 'abc123', 'interval': '15m'},
                 {'id': 'keep999', 'interval': '1h'},
                 {'interval': '1h'}], str(home))
    calls = []

    def fake_run(argv, **kw):
        calls.append(list(argv))
        if argv[:2] == ['schtasks', '/query']:
            # only the OLD-named task of abc123 actually exists
            return _Res(0 if argv[3] == migrate.OLD_TASK_PREFIX + 'abc123' else 1)
        return _Res(0)
    monkeypatch.setattr(proc, 'WINDOWS', True)
    monkeypatch.setattr(proc, 'run', fake_run)

    _fixed, failed = migrate.sweep([str(home)])
    deleted = [c[3] for c in calls if c[:2] == ['schtasks', '/delete']]
    created = [c[3] for c in calls if c[:2] == ['schtasks', '/create']]
    assert deleted == [migrate.OLD_TASK_PREFIX + 'abc123'], \
        'something other than the old-name task was deleted: %r' % deleted
    assert created == [loops.TASK_PREFIX + 'abc123'], \
        'a live entry was re-registered or a stale one left unscheduled: %r' % created
    assert not failed, failed
    di = [i for i, c in enumerate(calls) if c[:2] == ['schtasks', '/delete']]
    ci = [i for i, c in enumerate(calls) if c[:2] == ['schtasks', '/create']]
    assert max(di) < min(ci), 'the loop was re-registered before the old task died'


# ── 8. boundary: sentinels that do not pair (probe 3) ───────

def test_markers_that_do_not_pair_are_left_byte_for_byte(fake_home, monkeypatch):
    """migrate.py:513-527.

    A half pair (two KEEP starts with one end, and a LOOP end with no start) is
    left exactly as it is, and the file is not rewritten at all: `new == text`
    returns at 520-521 before `write_atomic`. Invert the count equality at 522
    and a half pair is renamed, which is the state the docstring calls
    unfixable — `upsert_block` indexes the FIRST occurrence, so a stray
    new-name start sentinel silently captures every later write and orphans the
    real block. Delete the 520 guard and an unchanged file is stamped as
    repaired. `test_a_half_written_block_is_left_exactly_as_it_is` covers one
    half pair of one block (a MEMORY start with no end) and never asks whether a
    write happened.
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    md = str(home / 'CLAUDE.md')
    text = ('# p\n\nmy own prose\n\n'
            + _tag('KEEP', 'START') + '\nhand written 1\n'
            + _tag('KEEP', 'START') + '\nhand written 2\n' + _tag('KEEP', 'END')
            + '\n\n' + _tag('LOOP', 'END') + '\n')
    _write(md, text)
    written = []
    real_write = _c.write_atomic

    def spy_write_atomic(path, body, **kw):
        written.append(os.path.abspath(str(path)))
        return real_write(path, body, **kw)
    monkeypatch.setattr(_c, 'write_atomic', spy_write_atomic)

    fixed, failed = migrate.sweep([str(home)])
    assert (fixed, failed) == ([], []), fixed or failed
    assert _read(md) == text, 'an unmatched marker was touched'
    assert md not in written, 'an unchanged file was rewritten and called fixed'
    assert not migrate.sweep_pending()


# ── 9. boundary: duplicate blocks, untested order (probe 4) ─

def test_a_stale_block_after_the_live_one_is_dropped_not_renamed(fake_home):
    """migrate.py:511-525, with the stale block on the OTHER side of the live one.

    `test_the_sweep_drops_the_orphan_and_renames_the_one_with_no_successor` puts
    every old block before its successor. The delete loop (511-519) and the
    rename loop (520-525) are ordered on purpose: swap them and the rename runs
    first, the delete then finds no old tag, and the file ends with two blocks
    carrying identical new sentinels.
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    md = str(home / 'CLAUDE.md')
    _write(md, '# p\n\nprose A\n\n%s\n\n%s\n\nprose B\n'
           % (_block('MEMORY', 'live digest', old=False),
              _block('MEMORY', 'stale digest')))

    _fixed, failed = migrate.sweep([str(home)])
    assert not failed, failed
    out = _read(md)
    assert out.count(_tag('MEMORY', 'START', old=False)) == 1, \
        'two blocks, one renderer: the stale one was renamed instead of dropped'
    assert 'live digest' in out and 'stale digest' not in out
    assert 'prose A' in out and 'prose B' in out, 'text outside the blocks was lost'
    assert 'CLAUDECTL' not in out


@pytest.mark.xfail(
    strict=True,
    reason='source defect: migrate.py:513-519 drops only the FIRST old block '
           '(`upsert_block` indexes the first occurrence, claude_md.py:59-60) and '
           'migrate.py:523 then renames the surviving duplicate, leaving two blocks '
           'with identical ARCHEUS sentinels — the state migrate.py:485-488 says '
           'the delete-first order exists to prevent')
def test_two_stale_duplicates_cannot_both_own_the_new_sentinel(fake_home):
    """migrate.py:511-525 — the double-append the docstring was measured on.

    Three of the author's own projects had TWO old blocks, because every build
    appended a second one beside the first. With a live successor present the
    supersede rule fires once (it drops the first pair only) and the rename
    round then promotes the second, so the file ends with two blocks under one
    sentinel and the renderer keeps whichever is first. The contract in the
    docstring (migrate.py:485-488) is one block per unique name; this asserts
    that and fails on the source as written — verified by running it against a
    copy of the module whose delete loop removes every duplicate, where it
    XPASSes (which the strict marker then reports as an error).
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    md = str(home / 'CLAUDE.md')
    _write(md, '# p\n\nprose A\n\n%s\n\n%s\n\n%s\n\nprose B\n'
           % (_block('MEMORY', 'live digest', old=False),
              _block('MEMORY', 'stale one'), _block('MEMORY', 'stale two')))

    _fixed, failed = migrate.sweep([str(home)])
    assert not failed, failed
    out = _read(md)
    assert 'prose A' in out and 'prose B' in out
    assert 'live digest' in out
    assert 'stale one' not in out and 'stale two' not in out, \
        'a duplicate stale block survived the sweep'
    assert out.count(_tag('MEMORY', 'START', old=False)) == 1, \
        'two blocks now share one sentinel; the renderer picks the first blindly'


# ── 10. fail-closed: a crash in the rederive (probe 10) ─────

def test_a_crash_in_the_path_rederive_writes_no_settings(fake_home, monkeypatch):
    """migrate.py:376 + 682-685.

    `_rederive_config_paths` is the last thing to touch settings before the flag
    is written, and it reads the file the move has just relocated. If it raises,
    the run must not be recorded as done — swallowing it (the tempting "make the
    start robust" fix) would stamp a half-migrated machine as finished and leave
    the process pointed at the account that no longer exists. Nothing in
    `tests/test_migration.py` fails inside this function.
    """
    tmp_path, home, other = fake_home
    proj = _seed_old_install(tmp_path, home, other)
    before = _read(str(home / 'claudectl.json'))
    kept = {a: getattr(_c, a) for a in ('config_dir', 'projects_dir',
                                        'last_session_file', 'global_claude_md')}
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda enc, folder=None, **kw: str(proj))
    monkeypatch.setattr(migrate, 'repair_commands',
                        lambda cfgdirs=None, **kw: ([], []))

    def boom():
        raise OSError('the settings file is locked')
    monkeypatch.setattr(_c, 'get_config_dir', boom)

    with pytest.raises(OSError):
        migrate.run()
    assert migrate.pending(), 'a run that died halfway was recorded as finished'
    assert _read(str(home / 'archeus.json')) == before, \
        'settings were written by a run that crashed'
    assert {a: getattr(_c, a) for a in kept} == kept, \
        'the process was left carrying half of the moved account'


# ── the three extra boundaries no test in the suite reached ─

def test_the_account_settings_file_is_the_last_thing_moved(fake_home, monkeypatch):
    """migrate.py:357-371.

    The config dirs are moved LAST because `_old_config_dirs()` and `pending()`
    both read that one file: move it first and a crash in the middle leaves
    nothing pointing at the accounts still to do. Reorder the two loops and the
    artifacts all still arrive, so only the order itself catches it.
    """
    tmp_path, home, other = fake_home
    proj = _seed_old_install(tmp_path, home, other)
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda enc, folder=None, **kw: str(proj))
    monkeypatch.setattr(migrate, 'repair_commands',
                        lambda cfgdirs=None, **kw: ([], []))
    order = []
    real_project, real_config = migrate._migrate_project, migrate._migrate_config_dir

    def spy_project(base, moved, failed):
        order.append(('project', base, os.path.isfile(str(home / 'claudectl.json'))))
        return real_project(base, moved, failed)

    def spy_config(cfgdir, moved, failed):
        order.append(('config', cfgdir, os.path.isfile(str(home / 'claudectl.json'))))
        return real_config(cfgdir, moved, failed)
    monkeypatch.setattr(migrate, '_migrate_project', spy_project)
    monkeypatch.setattr(migrate, '_migrate_config_dir', spy_config)

    _moved, failed = migrate.run()
    assert not failed, failed
    kinds = [k for k, _b, _s in order]
    assert 'project' in kinds and 'config' in kinds, 'the fixture never walked'
    assert max(i for i, k in enumerate(kinds) if k == 'project') \
        < min(i for i, k in enumerate(kinds) if k == 'config'), \
        'the config dirs went first: a crash then loses the account list'
    assert all(still_there for k, _b, still_there in order if k == 'project'), \
        'the old settings file was already gone while projects were being walked'


def test_the_mirror_folder_keeps_its_history_bytes(fake_home, monkeypatch):
    """migrate.py:447-457.

    Only the REAL working directory has its CLAUDE.md rewritten: the
    `projects/<enc>` mirror holds snapshots and diff records, and history keeps
    its own bytes. And when the transcript cannot resolve a folder, that project
    is skipped without inventing a failure (the walk is best effort; only a WRITE
    failure holds the gate). No test in `tests/test_migration.py` puts a
    CLAUDE.md in a mirror folder, and none makes the resolver raise.
    """
    _tmp, home, _other = fake_home
    _sweep_gate_open()
    proj1 = _tmp / 'work' / 'proj'
    proj2 = _tmp / 'work' / 'lost'
    stale = '# p\n\nmy own prose\n\n%s\n' % _block('MEMORY', 'old digest')
    for d in (str(home / 'projects' / ENC), str(home / 'projects' / ENC2),
              str(proj1), str(proj2)):
        _write(os.path.join(d, 'CLAUDE.md'), stale)

    def fake_resolve(enc, folder=None, **kw):
        if enc == ENC:
            return str(proj1)
        raise OSError('the transcript is unreadable')
    monkeypatch.setattr(paths, 'find_actual_path', fake_resolve)

    _fixed, failed = migrate.sweep([str(home)])
    assert not failed, failed
    assert 'CLAUDECTL' not in _read(str(proj1 / 'CLAUDE.md')), \
        'the live project was left with the orphan'
    assert _read(str(home / 'projects' / ENC / 'CLAUDE.md')) == stale, \
        'the mirror history was rewritten'
    assert _read(str(proj2 / 'CLAUDE.md')) == stale, \
        'an unresolvable folder was swept anyway'
    assert _read(str(home / 'projects' / ENC2 / 'CLAUDE.md')) == stale
    assert not migrate.sweep_pending()


def test_the_run_repoints_the_process_at_the_moved_account(fake_home, monkeypatch):
    """migrate.py:376, 682-685 (the success side of the same rule).

    `config.config_dir` and its three siblings were computed at import from a
    settings file that did not exist yet, so an install with a
    `claude_config_dir` override spent the rest of that process looking at the
    default account. Drop any one of the four assignments and the values disagree
    with each other — the failure is silent because every reader trusts them.
    """
    tmp_path, home, other = fake_home
    acct3 = tmp_path / 'acct3'
    proj = _seed_old_install(tmp_path, home, other,
                             extra={'claude_config_dir': str(acct3)})
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda enc, folder=None, **kw: str(proj))
    monkeypatch.setattr(migrate, 'repair_commands',
                        lambda cfgdirs=None, **kw: ([], []))
    # this one asks what the REAL resolver makes of the file that was just moved
    monkeypatch.setattr(_c, 'get_config_dir', _REAL_GET_CONFIG_DIR)

    moved, failed = migrate.run()
    assert not failed, failed
    assert moved, 'the fixture no longer moves anything'
    assert _c.config_dir == str(acct3)
    assert _c.projects_dir == os.path.join(str(acct3), 'projects')
    assert _c.last_session_file == os.path.join(_c.projects_dir,
                                                'last-session.json')
    assert _c.global_claude_md == os.path.join(_c.config_dir, 'CLAUDE.md')
    assert not migrate.pending()
    assert _c.load_settings()['migrated_from'] == migrate.OLD
