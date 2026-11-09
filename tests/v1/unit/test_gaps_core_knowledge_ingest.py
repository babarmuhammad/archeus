"""T-767: the ten highest-risk test gaps of archeus/core/knowledge/ingest.py.

Fail-closed and denial paths first (non-string path, missing path, the byte cap,
the undated refusal, the refusal storing no artifact), then boundary values
(exactly the cap, the five-line date window, the name/date `or` chains), then
the error and hostile-document paths (undecodable bytes, a BOM, byte-size), and
finally import_file's mapping and its never-touching-the-writer refusal.

Same in-process style as test_knowledge_units.py and test_broker_gaps.py: the
artifact store is faked through the module seam `ingest.artifacts` (a real
sha256 over the bytes it was handed), the database is a capturing writer, and
notes files are real bytes in tmp_path with explicit newlines. No OS call is
faked where a real tmp file answers, no clock, no network, no real process,
nothing Windows-specific and nothing POSIX-specific.
"""

import hashlib
import os
from pathlib import Path

import pytest

from archeus.core.application import knowledge as K
from archeus.core.knowledge import ingest


class Artifacts:
    """The store seam: records the exact bytes, returns their real sha256."""

    def __init__(self):
        self.seen = []

    def put(self, data):
        self.seen.append(data)
        return hashlib.sha256(data).hexdigest()


@pytest.fixture
def store(monkeypatch):
    fake = Artifacts()
    monkeypatch.setattr(ingest, 'artifacts', fake)
    return fake


class Writer:
    def __init__(self):
        self.calls = []

    def execute(self, command, params, idempotency_key=None):
        self.calls.append((command, params, idempotency_key))
        return {'changed': True}


class DB:
    def __init__(self):
        self.writer = Writer()


def make_file(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)                                    # explicit bytes, explicit newlines
    return str(p)


# ── 1–2 the `not a file` refusal: non-string, missing, directory ──

@pytest.mark.parametrize('bad', [
    pytest.param(Path('sync-2026-05-04.md'), id='pathlib'),
    pytest.param(None, id='none'),
    pytest.param(7, id='int'),
    pytest.param(b'sync-2026-05-04.md', id='bytes'),
])
def test_a_non_string_path_is_refused(store, bad):
    with pytest.raises(ValueError, match='not a file'):
        ingest.read_notes(bad)
    assert store.seen == []                                # a refusal stores nothing


def test_a_missing_path_and_a_directory_are_refused(store, tmp_path):
    with pytest.raises(ValueError, match='not a file'):
        ingest.read_notes(str(tmp_path / 'gone.md'))
    with pytest.raises(ValueError, match='not a file'):
        ingest.read_notes(str(tmp_path))
    assert store.seen == []


# ── 3 the byte cap: refusal over it, acceptance at exactly it, nothing stored ──

def test_exactly_the_cap_imports_and_one_more_byte_is_refused(store, tmp_path):
    at = make_file(tmp_path, 'sync-2026-05-04.md', b'a' * ingest.MAX_NOTES_BYTES)
    over = make_file(tmp_path, 'sync-2026-05-05.md', b'a' * (ingest.MAX_NOTES_BYTES + 1))
    assert ingest.read_notes(at)['size'] == ingest.MAX_NOTES_BYTES   # `>` not `>=`
    with pytest.raises(ValueError, match='notes over'):
        ingest.read_notes(over)
    assert len(store.seen) == 1                            # the oversized file stored nothing


# ── 4–5 the undated refusal and its opt-in: never the clock, never the file's mtime ──

def test_no_date_anywhere_is_refused_rather_than_guessed(store, tmp_path):
    p = make_file(tmp_path, 'notes.md', b'# Sync\nnothing dated, just 2026 talk\n')
    with pytest.raises(ValueError, match='no date'):
        ingest.read_notes(p)
    assert store.seen == []


def test_allow_undated_imports_with_no_date_never_a_date_invented(store, tmp_path):
    p = make_file(tmp_path, 'notes.md', b'# Sync\nnothing dated\n')
    assert ingest.read_notes(p, allow_undated=True)['held_at'] is None
    # the opt-in never masks a real date: a dated file is still dated
    q = make_file(tmp_path, 'sync-2026-05-04.md', b'x\n')
    assert ingest.read_notes(q, allow_undated=True)['held_at'] == '2026-05-04'


# ── 6 ordering: the caller's held_at, then the name's date, then the first lines' ──

def test_the_name_date_beats_a_different_date_in_the_first_lines(store, tmp_path):
    p = make_file(tmp_path, 'sync-2026-01-02.md', b'held 2026-03-04\nmore\n')
    assert ingest.read_notes(p)['held_at'] == '2026-01-02'
    assert ingest.read_notes(p, held_at='2025-12-31')['held_at'] == '2025-12-31'


# ── 7 the five-line window: the fifth line counts, the sixth is out of the file ──

def test_only_the_first_five_lines_carry_a_date(store, tmp_path):
    hit = make_file(tmp_path, 'kickoff.md', b'one\ntwo\nthree\nfour\n2026-06-07\nsix\n')
    assert ingest.read_notes(hit)['held_at'] == '2026-06-07'
    miss = make_file(tmp_path, 'wrapup.md', b'one\ntwo\nthree\nfour\nfive\n2026-06-07\n')
    with pytest.raises(ValueError, match='no date'):
        ingest.read_notes(miss)
    assert len(store.seen) == 1


# ── 8–9 the name `or` chain: first heading, empty heading, date-stripped stem, stem ──

def test_the_first_heading_wins_and_a_later_one_is_ignored(store, tmp_path):
    p = make_file(tmp_path, 'sync-2026-05-04.md', b'# First\n# Second\n')
    assert ingest.read_notes(p)['name'] == 'First'


@pytest.mark.parametrize('body', [
    pytest.param(b'# \n# Real Title\n', id='empty-first-heading'),
    pytest.param(b'#Heading only\n', id='no-space-not-a-heading'),
])
def test_no_usable_heading_falls_back_to_the_date_stripped_stem(store, tmp_path, body):
    p = make_file(tmp_path, 'sync-2026-05-04.md', body)
    assert ingest.read_notes(p)['name'] == 'sync'


def test_a_purely_dated_stem_stays_the_name_instead_of_becoming_empty(store, tmp_path):
    p = make_file(tmp_path, '2026-05-04.md', b'no heading here\n')
    n = ingest.read_notes(p)
    assert (n['name'], n['held_at']) == ('2026-05-04', '2026-05-04')


# ── 10 hostile documents: undecodable bytes, a BOM hiding the heading, byte-size ──

def test_undecodable_bytes_are_replaced_and_the_raw_bytes_are_the_artifact(store, tmp_path):
    data = b'\xff\xfe\x00\x81junk\xff\n\x00\n'
    p = make_file(tmp_path, 'sync-2026-05-04.md', data)
    n = ingest.read_notes(p)
    assert store.seen == [data]                            # bytes went to the store as read
    assert (n['sha256'], n['size'], n['name']) == (hashlib.sha256(data).hexdigest(),
                                                   len(data), 'sync')


def test_a_bom_hides_the_heading_so_the_name_comes_from_the_stem(store, tmp_path):
    data = b'\xef\xbb\xbf# Title\nnotes\n'                 # BOM + a heading: startswith fails
    p = make_file(tmp_path, 'sync-2026-05-04.md', data)
    assert ingest.read_notes(p)['name'] == 'sync'


def test_size_counts_bytes_not_characters(store, tmp_path):
    p = make_file(tmp_path, 'sync-2026-05-04.md', 'café rue\n'.encode('utf-8'))
    assert ingest.read_notes(p)['size'] == 10              # 9 characters, 10 bytes


# ── import_file: the command mapping, and refusals that never reach the writer ──

def test_import_file_maps_the_notes_onto_the_command(store, tmp_path):
    data = b'# Planning\nship it\n'
    p = make_file(tmp_path, 'sync-2026-05-04.md', data)
    db = DB()
    out = ingest.import_file(db, 'user', p, project_id='prj_1', idempotency_key='imp_1')
    (command, params, key), = db.writer.calls
    assert command is K.import_meeting and key == 'imp_1' and out == {'changed': True}
    assert (params['actor'], params['project_id'], params['name'], params['held_at']) == (
        'user', 'prj_1', 'Planning', '2026-05-04')
    assert params['notes_sha256'] == hashlib.sha256(data).hexdigest()
    assert params['notes_size'] == len(data)
    assert params['imported_from'] == os.path.abspath(p)


def test_a_refused_import_never_reaches_the_writer(store, tmp_path):
    db = DB()
    with pytest.raises(ValueError, match='not a file'):
        ingest.import_file(db, 'user', str(tmp_path / 'gone.md'))
    p = make_file(tmp_path, 'notes.md', b'# Sync\nno date here\n')
    with pytest.raises(ValueError, match='no date'):
        ingest.import_file(db, 'user', p)
    with pytest.raises(ValueError, match='no date'):       # False must not import undated
        ingest.import_file(db, 'user', p, allow_undated=False)
    assert db.writer.calls == [] and store.seen == []


def test_the_undated_opt_in_reaches_read_notes(store, tmp_path):
    p = make_file(tmp_path, 'notes.md', b'# Sync\nno date here\n')
    db = DB()
    ingest.import_file(db, 'user', p, allow_undated=True)
    (_, params, _key), = db.writer.calls
    assert params['held_at'] is None                       # asked for later, never invented


# ── two source faults the tests above deliberately do not paper over ──

@pytest.mark.xfail(strict=True, reason='_DATE checks digits only: the impossible calendar '
                     'date 2026-13-45 in the name is imported as held_at instead of being '
                     'refused — a fail-closed module must not store a date that cannot be')
def test_an_impossible_calendar_date_is_refused(store, tmp_path):
    p = make_file(tmp_path, 'sync-2026-13-45.md', b'# Sync\nnotes\n')
    with pytest.raises(ValueError):
        ingest.read_notes(p)


@pytest.mark.xfail(strict=True, reason='a non-None held_at skips all date parsing, so an '
                     'empty-string held_at (routes.py imports b.get("held_at") verbatim) is '
                     'kept as "": neither None-with-allow_undated nor a date the meeting has')
def test_an_empty_held_at_is_refused_not_stored(store, tmp_path):
    p = make_file(tmp_path, 'sync-2026-05-04.md', b'# Sync\nnotes\n')
    with pytest.raises(ValueError):
        ingest.read_notes(p, held_at='')
