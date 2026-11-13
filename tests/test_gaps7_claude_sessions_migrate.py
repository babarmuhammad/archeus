"""T-1315 · the highest-risk uncovered branches of `claude_sessions/migrate.py`
lines 477-533 inclusive (`_sweep_claude_md`, tip 51f4af3f; relocated at the
current tip): denial and fail-closed first, then boundaries, then error paths.

Candidate list, ranked (file:line, closest existing test, why it misses):
 1. migrate.py:514-521  several stale old copies plus a current block  - test_gaps3_claude_sessions_migrate_b
    asserts one stale block only; no test loops the drop while several remain.
    -> test_several_stale_copies_are_dropped_and_the_current_block_is_kept
 2. migrate.py:525-528  half START-only pair left byte-identical         - migrate_b covers a complete pair.
    -> test_a_start_only_pair_is_left_byte_identical
 3. migrate.py:525-528  half END-only pair left unchanged, no new sentinel - none exact.
    -> test_an_end_only_pair_is_left_byte_identical
 4. migrate.py:525-528  malformed nested/duplicate legacy sequence not renamed - none.
    -> test_a_nested_legacy_sequence_is_not_renamed
 5. migrate.py:523-532  several valid old pairs, no current block, all renamed, prose kept - migrate_b one pair.
    -> test_every_valid_old_pair_is_renamed_and_the_prose_between_them_kept
 6. migrate.py:491, 524  KEEP pair renamed, never removed as a superseded block - migrate_b KEEP single.
    -> test_a_keep_pair_is_renamed_even_when_a_new_keep_block_exists
 7. migrate.py:533-538  second sweep on renamed file: no write, no entries - none exact.
    -> test_a_second_sweep_writes_nothing_and_records_nothing
 8. migrate.py:517-521  first stale deletion write fails: append, stop, no rename - migrate_b covers success only.
    -> test_a_failed_stale_drop_stops_before_any_rename
 9. migrate.py:535-538  rename write fails: failure recorded, no sentinel-renamed claim - none exact.
    -> test_a_failed_rename_write_claims_no_rename
10. migrate.py:504-509  unreadable or missing file left untouched, only logged - migrate_b read-failure with OSError only.
    -> test_an_unreadable_or_missing_file_is_left_untouched

For each test, the source branch whose removal or inversion it breaks is the one
named in the candidate list above.

No defect in these ten: every test passes against the current source, so none is
marked xfail.

Fixture: real CLAUDE.md files under tmp_path only. `write_atomic` is spied (and
faked to fail where a probe needs it). No subprocess, network, sleep, environment,
credential or real home read. The old and new names come from `migrate.OLD` and
`migrate.NEW`, so this file holds no literal of the old name.
"""

import pytest

from claude_sessions import claude_md
from claude_sessions import config as _c
from claude_sessions import migrate

OLD = migrate.OLD
NEW = migrate.NEW
OT = '<!-- %s:' % OLD.upper()
NT = '<!-- %s:' % NEW.upper()


def _block(tag, name, body):
    return '%s%s:START -->\n%s\n%s%s:END -->\n' % (tag, name, body, tag, name)


def _start(tag, name):
    return '%s%s:START -->' % (tag, name)


def _end(tag, name):
    return '%s%s:END -->' % (tag, name)


def _put(tmp_path, text):
    path = tmp_path / 'CLAUDE.md'
    path.write_bytes(text.encode('utf-8'))
    return path


def _get(path):
    return path.read_bytes().decode('utf-8')


def _sweep(tmp_path):
    fixed, failed = [], []
    migrate._sweep_claude_md(str(tmp_path), fixed, failed)
    return fixed, failed


@pytest.fixture
def writes(monkeypatch):
    calls = []
    real = _c.write_atomic

    def spy(path, text, *args, **kwargs):
        calls.append(path)
        return real(path, text, *args, **kwargs)

    monkeypatch.setattr(_c, 'write_atomic', spy)
    return calls


def _refuse_writes(monkeypatch):
    calls = []

    def refuse(path, text, mode=None):
        calls.append(path)
        return False

    monkeypatch.setattr(_c, 'write_atomic', refuse)
    return calls


def test_several_stale_copies_are_dropped_and_the_current_block_is_kept(tmp_path, writes):
    current = _block(NT, 'MEMORY', 'current digest')
    text = ('intro\n'
            + _block(OT, 'MEMORY', 'stale one')
            + 'manual\n'
            + _block(OT, 'MEMORY', 'stale two')
            + _block(OT, 'MEMORY', 'stale three')
            + current)
    path = _put(tmp_path, text)
    fixed, failed = _sweep(tmp_path)
    got = _get(path)
    assert failed == []
    assert OT not in got
    assert got.count(_start(NT, 'MEMORY')) == 1
    assert 'current digest' in got and 'manual' in got and 'intro' in got
    assert [m for _, m in fixed] == ['dropped the superseded MEMORY block'] * 3


def test_a_start_only_pair_is_left_byte_identical(tmp_path, writes):
    text = 'keep\n' + _start(OT, 'MEMORY') + '\nbody with no end\n'
    path = _put(tmp_path, text)
    fixed, failed = _sweep(tmp_path)
    assert _get(path) == text
    assert (fixed, failed) == ([], [])
    assert writes == []


def test_an_end_only_pair_is_left_byte_identical(tmp_path, writes):
    text = 'keep\nbody with no start\n' + _end(OT, 'MEMORY') + '\n'
    path = _put(tmp_path, text)
    fixed, failed = _sweep(tmp_path)
    assert _get(path) == text
    assert (fixed, failed) == ([], [])
    assert writes == []
    assert NT not in _get(path)


def test_a_nested_legacy_sequence_is_not_renamed(tmp_path, writes):
    text = (_start(OT, 'MEMORY') + '\nouter\n'
            + _start(OT, 'MEMORY') + '\ninner\n'
            + _end(OT, 'MEMORY') + '\n')
    path = _put(tmp_path, text)
    assert not claude_md.well_formed(text, _start(OT, 'MEMORY'), _end(OT, 'MEMORY'))
    fixed, failed = _sweep(tmp_path)
    assert _get(path) == text
    assert (fixed, failed) == ([], [])
    assert writes == []


def test_every_valid_old_pair_is_renamed_and_the_prose_between_them_kept(tmp_path, writes):
    text = (_block(OT, 'MEMORY', 'first')
            + 'manual interstitial\n'
            + _block(OT, 'MEMORY', 'second')
            + _block(OT, 'LOOP', 'loop body'))
    path = _put(tmp_path, text)
    fixed, failed = _sweep(tmp_path)
    got = _get(path)
    assert failed == []
    assert OT not in got
    assert got.count(_start(NT, 'MEMORY')) == 2
    assert got.count(_start(NT, 'LOOP')) == 1
    assert 'manual interstitial' in got
    assert [m for _, m in fixed] == ['sentinels renamed']


def test_a_keep_pair_is_renamed_even_when_a_new_keep_block_exists(tmp_path, writes):
    text = (_block(NT, 'KEEP', 'current keep')
            + _block(OT, 'KEEP', 'users own fence'))
    path = _put(tmp_path, text)
    fixed, failed = _sweep(tmp_path)
    got = _get(path)
    assert failed == []
    assert OT not in got
    assert got.count(_start(NT, 'KEEP')) == 2
    assert 'users own fence' in got and 'current keep' in got
    assert fixed == [(str(path), 'sentinels renamed')]


def test_a_second_sweep_writes_nothing_and_records_nothing(tmp_path, writes):
    path = _put(tmp_path, _block(OT, 'MEMORY', 'a') + _block(OT, 'LOOP', 'b'))
    first_fixed, first_failed = _sweep(tmp_path)
    assert first_failed == [] and first_fixed
    after_first = _get(path)
    writes_before = len(writes)
    second_fixed, second_failed = _sweep(tmp_path)
    assert (second_fixed, second_failed) == ([], [])
    assert _get(path) == after_first
    assert len(writes) == writes_before


def test_a_failed_stale_drop_stops_before_any_rename(tmp_path, monkeypatch):
    attempts = _refuse_writes(monkeypatch)
    text = (_block(OT, 'MEMORY', 'stale')
            + _block(NT, 'MEMORY', 'current')
            + _block(OT, 'LOOP', 'loop left old'))
    path = _put(tmp_path, text)
    fixed, failed = _sweep(tmp_path)
    assert _get(path) == text
    assert fixed == []
    assert failed == [(str(path), 'could not drop the superseded MEMORY block')]
    assert len(attempts) == 1


def test_a_failed_rename_write_claims_no_rename(tmp_path, monkeypatch):
    attempts = _refuse_writes(monkeypatch)
    text = _block(OT, 'MEMORY', 'only old')
    path = _put(tmp_path, text)
    fixed, failed = _sweep(tmp_path)
    assert _get(path) == text
    assert fixed == []
    assert failed == [(str(path), 'could not rewrite the sentinels')]
    assert len(attempts) == 1


@pytest.mark.parametrize('case', ['missing', 'undecodable'])
def test_an_unreadable_or_missing_file_is_left_untouched(tmp_path, writes, case):
    if case == 'missing':
        path = tmp_path / 'CLAUDE.md'
        assert not path.exists()
    else:
        raw = b'\xff\xfe' + OT.encode('utf-8') + b'MEMORY:START -->\n'
        path = tmp_path / 'CLAUDE.md'
        path.write_bytes(raw)
    fixed, failed = _sweep(tmp_path)
    assert (fixed, failed) == ([], [])
    assert writes == []
    if case == 'missing':
        assert not path.exists()
    else:
        assert path.read_bytes() == raw
