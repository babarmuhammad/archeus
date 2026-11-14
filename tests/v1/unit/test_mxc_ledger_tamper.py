"""T-1092 — characterisation tests for what the ledger reader detects TODAY (tests only).

One-line summary: read_records checks each line against itself, not against its
neighbours. `read_records` (mxc_ledger.py:85-106) verifies each line's own envelope
(length + sha256 over its own record), its `execution_id`, its `op`, and its `seq`
against the COUNT of records accepted so far; nothing chains one line to the hash of
the line before it. So damage is caught and a hostile rewrite that recomputes the sha
is not — the comment at mxc_ledger.py:152 ("checksums detect damage, not hostile
rewrites") is measured here, case by case. The two strict-xfail tests at the bottom
are the deliverable: they fail today and their failure names the gap.

Read ranges (this snapshot; re-open them, they can be off by a few):
  archeus/node/mxc_ledger.py 34-42 (`_json`, `_line`), 45-82 (`_validate`),
      85-106 (`read_records`), 151-160 (`Ledger` comment), 174-215 (`append`,
      context only, never called here).
  tests/v1/unit/test_pins_node_mxc_ledger.py 1-50 (builders `intent`, `owner`,
      `disposal`, `completion`, `lines`, `invalid`) and 182-187
      (`test_sequence_must_be_contiguous`); tests/v1/unit/test_mxc_ledger_gaps.py
      75-112 and 201-212 (`test_bad_line_keeps_valid_prefix`). The few builder lines
      needed are copied below as ROWS/LINES; no test module is imported.

In-memory bytes only: no `Ledger` object, no tmp file, no process, no clock, no
network, and every line ends with an explicit b'\\n' so the file is platform-neutral.
"""

import hashlib

import pytest

from archeus.node import mxc_ledger as ledger

DIGEST = 'a' * 64


def chained(rows):
    out, prev = [], ledger.GENESIS
    for row in rows:
        out.append(dict(row, version=ledger.FORMAT_VERSION, prev=prev))
        prev = hashlib.sha256(ledger._line(out[-1])).hexdigest()
    return out


ROWS = chained([
    {'execution_id': 'e1', 'op': 'intent', 'seq': 0, 'requested_policy_digest': DIGEST,
     'planned': [], 'applied': [], 'observed': {}},
    {'execution_id': 'e1', 'op': 'ownership', 'seq': 1, 'pid': 41, 'create_time': 900,
     'requested_policy_digest': DIGEST, 'applied': [], 'observed': {}, 'owned': []},
    {'execution_id': 'e1', 'op': 'disposal', 'seq': 2, 'verified_absent': True},
    {'execution_id': 'e1', 'op': 'completion', 'seq': 3, 'outcome': 0},
])
LINES = [ledger._line(r) for r in ROWS]
ANCHOR = (4, hashlib.sha256(LINES[3]).hexdigest())


def read(data, eid='e1', anchor=None):
    return ledger.read_records(data, eid, anchor)


def edited(i, **fields):
    """A fresh line for row *i* with *fields* replaced, so a fresh sha over the edit."""
    return ledger._line(dict(ROWS[i], **fields))


def flip_sha(line):
    """Change ONE hex digit of the stored sha (damage to the envelope, not a rewrite)."""
    key = b'"sha256":"'
    i = line.index(key) + len(key)
    return line[:i] + (b'1' if line[i:i + 1] == b'0' else b'0') + line[i + 1:]


def journal(*lines):
    """A journal out of whole lines only; never touched on disk."""
    return b''.join(lines)


def test_a_clean_four_record_journal_reads_clean():
    """Branch: the accept path of read_records (mxc_ledger.py:102-103, `_validate`
    passes and `records.append(record)`) — the happy path every case below is
    measured against; if it breaks, every xfail below turns into a false xpass."""
    assert read(journal(*LINES)) == (ROWS, False)


@pytest.mark.parametrize('k', [0, 1, 2, 3], ids=['k0', 'k1', 'k2', 'k3'])
def test_a_flipped_sha_digit_is_detected_and_the_prefix_survives(k):
    """Branch: `or envelope['sha256'] != hashlib.sha256(payload).hexdigest()` in
    read_records (mxc_ledger.py:96) drops the damaged line; the later lines then
    fail `record['seq'] != len(records)` (mxc_ledger.py:100), which is why only the
    prefix before the damage survives."""
    data = journal(*[LINES[j] if j != k else flip_sha(LINES[j]) for j in range(4)])
    assert read(data) == (ROWS[:k], True)


def test_a_changed_value_under_its_old_sha_is_detected():
    """Branch: the same sha comparison (mxc_ledger.py:96). `length` (line 95) does
    NOT catch it — it is recomputed from the edited record itself — so deleting only
    line 96 makes this read clean; deleting only 95 does not."""
    tampered = LINES[1].replace(b'"pid":41', b'"pid":42')
    assert tampered != LINES[1]
    assert read(journal(LINES[0], tampered, LINES[2], LINES[3])) == (ROWS[:1], True)


@pytest.mark.parametrize('k', [0, 1, 2], ids=['k0', 'k1', 'k2'])
def test_a_deleted_line_is_detected(k):
    """Branch: `or record['seq'] != len(records)` in read_records
    (mxc_ledger.py:100) fires first on the line after the hole; the state machine in
    `_validate` (mxc_ledger.py:58, 67, 71) backs it up, so removing either check
    alone still reads invalid is True — both together are needed to hide a deletion."""
    data = journal(*[LINES[j] for j in range(4) if j != k])
    assert read(data) == (ROWS[:k], True)


@pytest.mark.parametrize('k', [0, 1, 2, 3], ids=['k0', 'k1', 'k2', 'k3'])
def test_a_duplicated_line_is_detected_and_every_record_is_kept(k):
    """Branch: `or record['seq'] != len(records)` (mxc_ledger.py:100) rejects only
    the repeat (its seq is one behind the count), and since a rejected line is
    skipped rather than fatal (mxc_ledger.py:104-105) all four records survive with
    invalid True. `_validate` (mxc_ledger.py:53/58/67/71) is the backstop."""
    lines = []
    for j in range(4):
        lines.append(LINES[j])
        if j == k:
            lines.append(LINES[j])          # the very same bytes, immediately again
    assert read(journal(*lines)) == (ROWS, True)


@pytest.mark.parametrize('order,kept', [
    ((1, 0, 2, 3), ROWS[:1]),
    ((0, 2, 1, 3), ROWS[:2]),
    ((0, 1, 3, 2), ROWS[:3]),
], ids=['swap01', 'swap12', 'swap23'])
def test_reordered_lines_are_detected(order, kept):
    """Branch: `or record['seq'] != len(records)` (mxc_ledger.py:100) fires first on
    the moved line (its seq no longer equals the count), with `_validate`
    (mxc_ledger.py:53/58/67/71) behind it. swap23 keeps THREE records, not two: the
    moved completion (seq 3, count 2) is skipped, and the disposal then still finds
    count 2 and the ops list ['intent', 'ownership'] it wants (mxc_ledger.py:67), so
    it is accepted out of position. The card listed (ROWS[:2], True) for swap23; the
    source keeps ROWS[:3], pinned here as read — detection (invalid True) is unchanged."""
    assert read(journal(*[LINES[j] for j in order])) == (kept, True)


@pytest.mark.parametrize('data,kept', [
    (journal(LINES[0], LINES[1], edited(3, seq=2)), ROWS[:2]),
    (journal(LINES[0], edited(2, seq=1), edited(3, seq=2)), ROWS[:1]),
], ids=['drop2renumber', 'drop1renumber'])
def test_a_removed_line_with_renumbered_later_lines_is_still_detected(data, kept):
    """Branch: NOT the seq check — the renumbered lines carry a fresh sha and a `seq`
    that equals the running count, so mxc_ledger.py:100 lets them through; what stops
    them is the state-machine order in `_validate`: `if ops != ['intent', 'ownership',
    'disposal']` for completion (mxc_ledger.py:71) and `if ops != ['intent',
    'ownership']` for disposal (mxc_ledger.py:67). No chain is involved: the ops list
    is rebuilt from the accepted records, which is the only neighbour-binding today."""
    assert read(data) == (kept, True)


def test_a_foreign_execution_id_is_refused():
    """Branch: `or record['execution_id'] != execution_id` in read_records
    (mxc_ledger.py:97): the whole journal read as 'e2' yields nothing, and one
    spliced line with a foreign id (fresh sha, so self-consistent) is dropped by that
    check while the following completion then fails `seq` (mxc_ledger.py:100)."""
    assert read(journal(*LINES), 'e2') == ([], True)
    data = journal(LINES[0], LINES[1], edited(2, execution_id='e2'), LINES[3])
    assert read(data) == (ROWS[:2], True)


def test_a_torn_tail_is_detected():
    """Branch: `not line.endswith(b'\\n')`, the first test of the framing `if` in
    read_records (mxc_ledger.py:94): cutting the last newline loses the completion
    and flags the journal, but only because the torn line is still its own splitline
    — a torn tail that cuts mid-line also fails json.loads (mxc_ledger.py:91)."""
    assert read(journal(*LINES)[:-1]) == (ROWS[:3], True)


@pytest.mark.parametrize('data', [
    journal(LINES[0], edited(1, pid=42), LINES[2], LINES[3]),
    journal(edited(0, planned=['x']), LINES[1], LINES[2], LINES[3]),
    journal(LINES[0], LINES[1], LINES[2], edited(3, outcome=9)),
], ids=['pid42', 'planned', 'outcome9'])
def test_gap_an_edited_field_with_a_fresh_sha_is_not_detected(data):
    """Branch: none — that is the gap. `_line` (mxc_ledger.py:39-42) seals the record
    it is handed, so the sha proves only self-consistency, and `_validate`
    (mxc_ledger.py:45-82) binds the ops ORDER and the ownership record's copy of the
    intent's `requested_policy_digest` (mxc_ledger.py:60) but nothing binds `planned`,
    `pid`, `create_time`, `owned` or `outcome`. Today each of these reads
    `(<rows with the edit>, False)`; a tamper-evident reader must say invalid is True."""
    assert read(data, anchor=ANCHOR)[1] is True


def test_gap_a_deleted_last_line_is_not_detected():
    """Branch: none — the second gap. `read_records` (mxc_ledger.py:85-106) has no
    rule about what a finished journal looks like: the completion is only checked if
    present (`if ops != ['intent', 'ownership', 'disposal']`, mxc_ledger.py:71), and
    with no chain (mxc_ledger.py:152) a journal truncated by one whole line is a
    perfect copy of a run that has not finished. A tamper-evident reader must say
    invalid is True; today this reads (ROWS[:3], False)."""
    assert read(journal(*LINES[:3]), anchor=ANCHOR)[1] is True


@pytest.mark.parametrize('lines,anchor,invalid', [
    (LINES, ANCHOR, False),
    (LINES, (3, hashlib.sha256(LINES[2]).hexdigest()), False),
    (LINES[:3], ANCHOR, True),
], ids=['anchor-current', 'crash-after-a-line-before-its-anchor', 'removed-last-line'])
def test_anchor_accepts_one_unanchored_line_and_refuses_a_missing_one(lines, anchor, invalid):
    assert read(journal(*lines), anchor=anchor)[1] is invalid


def test_ledger_refuses_an_edited_anchored_line_and_accepts_one_unanchored_line(tmp_path):
    led = ledger.Ledger(tmp_path)
    led.append('e1', 'intent', requested_policy_digest=DIGEST, planned=[], applied=[],
               observed={})
    led.append('e1', 'ownership', pid=41, create_time=900, requested_policy_digest=DIGEST,
               applied=[], observed={}, owned=[])
    good = (tmp_path / 'e1.jsonl').read_bytes()
    assert led.journals()['e1'] == good
    (tmp_path / 'e1.jsonl').write_bytes(LINES[0] + edited(1, pid=42))
    assert led.journals()['e1'] == b'invalid\n'
    (tmp_path / 'e1.jsonl').write_bytes(good + LINES[2])
    assert read(led.journals()['e1'])[1] is False
