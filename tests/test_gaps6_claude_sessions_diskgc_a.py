"""T-1264 — close the highest-risk test gaps in claude_sessions/diskgc.py,
lines 37-107 inclusive (tip 6bbd3b44; re-located by reading the source, the
card's line numbers came from an older tip, and the file is 178 lines at this
worktree's tip).

Slice: `policy_days`, `run`, `_referenced_sessions` and `_sweep`, i.e. the
retention clamp, the account selection, the reference scan that protects
sessions, and the per-store totals.

Selected branches, denial/fail-closed first, then boundaries, then error paths:

 1. :58   default run (no apply) passes apply=False to every store sweep; the
          dry-run walk of file-history removes nothing
 2. :51   an explicit cfgdir visits only that account; a sibling whose name
          starts with the same letters is never swept
 3. :81   last-session dict records and legacy string records protect their
          ids in every project folder, not only the one they name
 4. :88   a .name sidecar protects its session even when empty; only the exact
          `.name` suffix counts, `.names` does not
 5. :91   a truthy tag entry protects its id; an empty tag list does not
 6. :78   the reference scan reads the selected account's projects root; the
          other account's references do not decide this account's files
 7. :55   days=0 reads each account's cleanupPeriodDays separately; an explicit
          positive days overrides every account's setting
 8. :41   stored retention clamps to one day at the bottom; invalid or missing
          values fall back to DEFAULT_DAYS and never widen the sweep
 9. :104  store totals add once each, referenced transcripts count as kept and
          not as bytes, and no folder is created in the account
10. :82   a session_id that is not a string aborts the sweep (strict xfail);
          the valid references and the unreferenced candidate are expected to
          be honoured

Closest existing tests (tests/test_clientstate.py): the dry run of one project
transcript, applying a single old file, a named session, a tagged session, the
sidecar exclusion, the outside-account refusal and the per-account policy read
of one settings file. Those assert one branch each on one folder; these probes
pin the seams the existing tests leave open: default apply, the sibling prefix,
legacy records across folders, empty sidecars and tags, cross-account reads,
explicit overrides, clamp boundaries, totals and the shape defect.

Seams: `diskgc.time` is a fake clock, `os.remove` is recorded instead of run,
`_c.all_config_dirs` returns synthetic accounts, and `_c.log` is replaced so no
event store is written. Every file lives under tmp_path.
"""

import json
import os

import pytest

from claude_sessions import diskgc

FIXED_NOW = 1_700_000_000
DAY = 86400


class FakeClock:
    @staticmethod
    def time():
        return float(FIXED_NOW)


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(diskgc, 'time', FakeClock())


@pytest.fixture
def removed(monkeypatch):
    calls = []
    monkeypatch.setattr(diskgc.os, 'remove', lambda p: calls.append(p))
    return calls


@pytest.fixture
def acct(tmp_path):
    d = tmp_path / 'acct'
    d.mkdir()
    return d


def put(path, data=b'x' * 10, days=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if days is not None:
        t = FIXED_NOW - days * DAY
        os.utime(path, (t, t))
    return path


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding='utf-8')
    return path


def test_a_default_run_removes_nothing_from_the_store_trees(acct, clock, removed):
    old = put(acct / 'file-history' / 'snap' / 'h.bin', days=40)
    r = diskgc.run(days=30, cfgdir=str(acct))
    assert removed == []
    assert old.exists()
    assert r['applied'] is False
    assert r['files'] == 1


def test_an_explicit_account_never_sweeps_a_sibling_whose_name_starts_the_same(
        tmp_path, clock):
    acct = tmp_path / 'acct'
    sibling = tmp_path / 'acct2'
    mine = put(acct / 'projects' / 'D--x' / 'aaaa.jsonl', days=40)
    other = put(sibling / 'projects' / 'D--x' / 'bbbb.jsonl', days=40)
    r = diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert not mine.exists()
    assert other.exists()
    assert [a['dir'] for a in r['accounts']] == [str(acct)]


def test_last_session_records_protect_ids_in_every_project_folder(acct, clock, removed):
    root = acct / 'projects'
    write_json(root / 'last-session.json', {
        'D--x': {'session_id': 'aaaa'},
        'D--y': 'bbbb',
        'D--z': 7,
    })
    put(root / 'D--x' / 'aaaa.jsonl', days=40)
    put(root / 'D--y' / 'bbbb.jsonl', days=40)
    put(root / 'D--z' / 'cccc.jsonl', days=40)
    r = diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert [os.path.basename(p) for p in removed] == ['cccc.jsonl']
    assert r['kept'] == 2


def test_an_empty_name_sidecar_protects_and_only_the_exact_suffix_counts(
        acct, clock, removed):
    proj = acct / 'projects' / 'D--x'
    put(proj / 'aaaa.jsonl', days=40)
    put(proj / 'aaaa.name', data=b'', days=40)
    put(proj / 'cccc.jsonl', days=40)
    put(proj / 'cccc.names', data=b'a name', days=40)
    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert [os.path.basename(p) for p in removed] == ['cccc.jsonl']


def test_a_tag_entry_protects_only_when_it_is_truthy(acct, clock, removed):
    proj = acct / 'projects' / 'D--x'
    put(proj / 'aaaa.jsonl', days=40)
    put(proj / 'bbbb.jsonl', days=40)
    write_json(proj / 'tags.json', {'aaaa': ['keep'], 'bbbb': []})
    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert [os.path.basename(p) for p in removed] == ['bbbb.jsonl']


def test_the_reference_scan_reads_only_the_selected_accounts_projects(
        tmp_path, clock):
    acct_a = tmp_path / 'a'
    acct_b = tmp_path / 'b'
    write_json(acct_a / 'projects' / 'last-session.json', {'D--x': {'session_id': 'aaaa'}})
    kept_elsewhere = put(acct_a / 'projects' / 'D--x' / 'aaaa.jsonl', days=40)
    stale_here = put(acct_b / 'projects' / 'D--x' / 'aaaa.jsonl', days=40)
    diskgc.run(days=30, apply=True, cfgdir=str(acct_b))
    assert not stale_here.exists()
    assert kept_elsewhere.exists()


def test_cleanup_policy_is_read_per_account_unless_days_is_explicit(
        tmp_path, clock, monkeypatch):
    acct_a = tmp_path / 'one'
    acct_b = tmp_path / 'two'
    write_json(acct_a / 'settings.json', {'cleanupPeriodDays': 7})
    write_json(acct_b / 'settings.json', {'cleanupPeriodDays': 60})
    monkeypatch.setattr(diskgc._c, 'all_config_dirs',
                        lambda: [('one', str(acct_a)), ('two', str(acct_b))])
    a_file = put(acct_a / 'projects' / 'D--x' / 'aaaa.jsonl', days=10)
    b_file = put(acct_b / 'projects' / 'D--x' / 'bbbb.jsonl', days=10)

    r = diskgc.run(days=0, apply=True)
    assert [a['days'] for a in r['accounts']] == [7, 60]
    assert not a_file.exists()
    assert b_file.exists()

    forced = diskgc.run(days=5, apply=False)
    assert [a['days'] for a in forced['accounts']] == [5, 5]
    assert forced['files'] == 1


@pytest.mark.parametrize('stored, expected', [
    (0, 1),
    (-5, 1),
    (2.9, 2),
    ('abc', diskgc.DEFAULT_DAYS),
    (None, diskgc.DEFAULT_DAYS),
    ([], diskgc.DEFAULT_DAYS),
])
def test_stored_retention_clamps_at_one_and_unusable_values_use_the_default(
        acct, stored, expected):
    write_json(acct / 'settings.json', {'cleanupPeriodDays': stored})
    assert diskgc.policy_days(str(acct)) == expected


def test_store_totals_add_once_and_referenced_transcripts_count_as_kept(
        acct, clock):
    put(acct / 'file-history' / 'h.bin', data=b'x' * 10, days=40)
    put(acct / 'paste-cache' / 'p.bin', data=b'x' * 20, days=40)
    put(acct / 'projects' / 'D--x' / 'aaaa.jsonl', data=b'x' * 30, days=40)
    put(acct / 'projects' / 'D--x' / 'bbbb.jsonl', data=b'x' * 100, days=40)
    write_json(acct / 'projects' / 'D--x' / 'tags.json', {'bbbb': ['k']})
    before = sorted(os.listdir(acct))

    r = diskgc.run(days=30, cfgdir=str(acct))

    assert r['bytes'] == 60
    assert r['files'] == 3
    assert r['kept'] == 1
    account = r['accounts'][0]
    assert account['bytes'] == 60 and account['files'] == 3
    assert sorted(row['name'] for row in account['stores']) == [
        'file-history', 'paste-cache', 'projects']
    assert sorted(os.listdir(acct)) == before


@pytest.mark.xfail(
    strict=True, raises=TypeError,
    reason="claude_sessions/diskgc.py:82 an unhashable session_id raises "
           "TypeError and aborts the whole sweep, so the valid references and "
           "the unreferenced candidate are never honoured")
def test_a_session_id_that_is_not_a_string_is_ignored_and_the_sweep_completes(
        acct, clock, removed):
    root = acct / 'projects'
    write_json(root / 'last-session.json', {
        'D--x': {'session_id': ['aaaa']},
        'D--y': 'bbbb',
    })
    put(root / 'D--x' / 'cccc.jsonl', days=40)
    kept = put(root / 'D--y' / 'bbbb.jsonl', days=40)
    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert kept.exists()
    assert [os.path.basename(p) for p in removed] == ['cccc.jsonl']
