"""T-1265 — close the highest-risk test gaps in claude_sessions/diskgc.py,
lines 110-178 inclusive (tip 6bbd3b44; re-located by reading the source, the
card's line numbers came from an older tip, and the file is 178 lines at this
worktree's tip).

Slice: `_prune_tree`, `_prune_transcripts`, `_remove`, `_stat`, `_listdir` and
`_subdirs`, i.e. the per-file walk of the store folders, the per-file walk of
`projects/`, the containment check before every removal, and the error
swallowing around stat, listing and removal.

Selected branches, denial/fail-closed first, then boundaries, then error paths:

 1. :153  the account root itself and a sibling whose name starts with the
          same letters are refused; a real descendant is allowed
 2. :153  a traversal that normalises outside the account is refused; the
          separator spelling and the case spelling of an inside path are both
          accepted through a named normcase seam
 3. :153  a transcript reached through a folder that resolves outside the
          account must not be removed (lexical guard only; strict xfail)
 4. :133  .name, tags.json, extra-paths, system-prompt and other sidecars in
          projects/ survive a full apply; only .jsonl files are candidates
 5. :136  a referenced old transcript is counted as kept before any stat; a
          young transcript and a transcript whose stat returns None are skipped
 6. :141  mtime exactly at the cutoff is kept; one second older is a candidate,
          removed only with apply=True
 7. :120  the dry-run tree scan counts nested old files and bytes, excludes the
          recent file, and never removes a file or a directory
 8. :157  a deletion OSError is swallowed, the remaining candidates are still
          attempted, and the report counts candidates, not confirmed removals
 9. :116  a stat that returns None skips the file without a removal attempt;
          the walk never removes a directory itself
10. :178  an unreadable directory yields an empty listing, and a regular file
          at the projects/ level is never selected as a project folder

Closest existing tests (tests/test_clientstate.py): the outside-account refusal
of one file in tmp_path, the sidecar exclusion of system-prompt.txt, the apply
of one old file beside a new one, and the dry run of one project transcript.
These probes pin the sibling prefix, the exact root, normalised traversal,
sidecar variety, the reference-before-stat order, the exact cutoff, the
candidate counts on error, the stat race and the unreadable folder.

Seams: `diskgc.time` is a fake clock, `os.remove` and `os.listdir` are
recorded or failed on request, `diskgc._stat` is replaced for the stat race,
`_c.log` is replaced so no event store is written, and the link resolution in
the xfail probe is a fake of what the operating system would do. No link is
created; every file lives under tmp_path.
"""

import os

import pytest

from claude_sessions import diskgc

FIXED_NOW = 1_700_000_000
DAY = 86400


class FakeClock:
    @staticmethod
    def time():
        return float(FIXED_NOW)


class RecordingLog:
    def __init__(self):
        self.errors = []

    def error(self, msg, *args):
        self.errors.append(msg % args)


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(diskgc, 'time', FakeClock())


@pytest.fixture
def log(monkeypatch):
    rec = RecordingLog()
    monkeypatch.setattr(diskgc._c, 'log', rec)
    return rec


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


def names(paths):
    return [os.path.basename(p) for p in paths]


def test_remove_refuses_the_account_root_and_a_same_prefix_sibling(
        tmp_path, removed, log):
    acct = tmp_path / 'acct'
    acct.mkdir()
    sibling = put(tmp_path / 'acct2' / 'x.jsonl')
    diskgc._remove(str(acct), str(acct))
    diskgc._remove(str(sibling), str(acct))
    assert removed == []
    assert len(log.errors) == 2

    child = put(acct / 'projects' / 'x.jsonl')
    diskgc._remove(str(child), str(acct))
    assert removed == [str(child)]


def test_traversal_that_normalises_outside_is_refused(tmp_path, removed, log):
    acct = tmp_path / 'acct'
    acct.mkdir()
    put(tmp_path / 'outside.jsonl')
    diskgc._remove(os.path.join(str(acct), '..', 'outside.jsonl'), str(acct))
    assert removed == []
    assert len(log.errors) == 1


def test_separator_and_case_spellings_of_an_inside_path_are_accepted(
        tmp_path, removed, monkeypatch):
    acct = tmp_path / 'acct'
    acct.mkdir()
    f = put(acct / 'projects' / 'a.jsonl')
    spelled = str(f).replace(os.sep, '/')
    monkeypatch.setattr(diskgc.os.path, 'normcase', lambda p: p.lower())
    diskgc._remove(spelled, str(acct).upper())
    assert removed == [spelled]


@pytest.mark.xfail(
    strict=True,
    reason="claude_sessions/diskgc.py:153 the containment check is lexical; "
           "a projects/ folder that resolves outside the account is walked by "
           "_prune_transcripts and its transcript is removed through the link")
def test_a_transcript_reached_through_a_folder_that_resolves_outside_is_not_removed(
        tmp_path, clock, monkeypatch):
    acct = tmp_path / 'acct'
    foreign = tmp_path / 'foreign'
    linked = acct / 'projects' / 'linked'
    put(linked / 'aaaa.jsonl', days=40)
    put(foreign / 'bbbb.jsonl', days=40)
    link_text = str(linked)
    foreign_text = str(foreign)
    removed_targets = []

    def operating_system_remove(path):
        if path.startswith(link_text):
            path = foreign_text + path[len(link_text):]
        removed_targets.append(path)

    monkeypatch.setattr(diskgc.os, 'remove', operating_system_remove)
    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    inside = str(acct) + os.sep
    assert all(t.startswith(inside) for t in removed_targets), removed_targets


def test_every_sidecar_in_projects_survives_and_only_jsonl_is_a_candidate(
        acct, clock, removed):
    proj = acct / 'projects' / 'D--x'
    for n in ('aaaa.name', 'tags.json', 'extra-paths.json',
              'system-prompt.txt', 'notes.md', 'cccc.jsonl.bak'):
        put(proj / n, days=400)
    put(proj / 'bbbb.jsonl', days=400)
    r = diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert names(removed) == ['bbbb.jsonl']
    assert r['files'] == 1


def test_referenced_young_and_unstattable_transcripts_are_skipped_before_removal(
        acct, clock, removed, monkeypatch):
    proj = acct / 'projects' / 'D--x'
    old_ref = put(proj / 'aaaa.jsonl', days=400)
    put(proj / 'aaaa.name', days=400)
    young = put(proj / 'bbbb.jsonl', days=1)
    gone = put(proj / 'cccc.jsonl', days=400)
    real_stat = diskgc._stat
    stat_names = []

    def stat_race(p):
        stat_names.append(os.path.basename(p))
        if os.path.basename(p) == 'cccc.jsonl':
            return None
        return real_stat(p)

    monkeypatch.setattr(diskgc, '_stat', stat_race)
    r = diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert 'aaaa.jsonl' not in stat_names
    assert removed == []
    assert old_ref.exists() and young.exists() and gone.exists()
    assert r['kept'] == 1
    assert r['files'] == 0


def test_mtime_exactly_at_the_cutoff_is_kept_and_one_second_older_is_removed_on_apply(
        acct, clock, removed):
    proj = acct / 'projects' / 'D--x'
    cutoff = FIXED_NOW - 30 * DAY
    at = put(proj / 'aaaa.jsonl')
    os.utime(at, (cutoff, cutoff))
    older = put(proj / 'bbbb.jsonl')
    os.utime(older, (cutoff - 1, cutoff - 1))

    dry = diskgc.run(days=30, cfgdir=str(acct))
    assert dry['files'] == 1
    assert removed == []

    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert removed == [str(older)]


def test_the_tree_scan_counts_nested_old_files_and_removes_nothing(acct, clock, removed):
    put(acct / 'paste-cache' / 'a' / 'deep' / 'old.bin', data=b'x' * 7, days=60)
    put(acct / 'paste-cache' / 'new.bin', data=b'x' * 9, days=2)
    (acct / 'paste-cache' / 'empty').mkdir(parents=True)

    r = diskgc.run(days=30, cfgdir=str(acct))

    assert r['accounts'][0]['stores'] == [
        {'name': 'paste-cache', 'bytes': 7, 'files': 1}]
    assert r['bytes'] == 7
    assert removed == []


def test_a_failed_removal_is_swallowed_and_the_report_counts_candidates(
        acct, clock, monkeypatch):
    proj = acct / 'projects' / 'D--x'
    put(proj / 'aaaa.jsonl', days=40)
    put(proj / 'bbbb.jsonl', days=40)
    attempts = []

    def refuse_the_first(p):
        attempts.append(os.path.basename(p))
        if len(attempts) == 1:
            raise PermissionError(13, 'denied')

    monkeypatch.setattr(diskgc.os, 'remove', refuse_the_first)
    r = diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert sorted(attempts) == ['aaaa.jsonl', 'bbbb.jsonl']
    assert r['files'] == 2


def test_a_stat_race_skips_the_file_and_the_walk_never_removes_a_directory(
        acct, clock, removed, monkeypatch):
    base = acct / 'file-history'
    put(base / 's1' / 'a.bin', days=60)
    put(base / 's1' / 'b.bin', days=60)
    (base / 's2').mkdir(parents=True)
    real_stat = diskgc._stat
    monkeypatch.setattr(diskgc, '_stat',
                        lambda p: None if p.endswith('a.bin') else real_stat(p))

    r = diskgc.run(days=30, apply=True, cfgdir=str(acct))

    assert names(removed) == ['b.bin']
    assert r['accounts'][0]['stores'] == [
        {'name': 'file-history', 'bytes': 10, 'files': 1}]
    assert (base / 's2').is_dir()


def test_an_unreadable_folder_yields_nothing_and_a_stray_file_is_not_a_project(
        acct, clock, removed, monkeypatch):
    projects = acct / 'projects'
    put(projects / 'stray.jsonl', days=40)
    (projects / 'D--locked').mkdir(parents=True)
    put(projects / 'D--x' / 'aaaa.jsonl', days=40)
    real_listdir = os.listdir

    def listdir(p):
        if os.path.basename(p) == 'D--locked':
            raise PermissionError(13, 'denied')
        return real_listdir(p)

    monkeypatch.setattr(diskgc.os, 'listdir', listdir)
    diskgc.run(days=30, apply=True, cfgdir=str(acct))
    assert names(removed) == ['aaaa.jsonl']
