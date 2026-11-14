"""T-1438: the uncovered branches of `archeus/node/local.py` lines 2667-2778 inclusive
(`_import_plan`, `_import_stream`) at tip 026ea58e. No source file is edited. The stream's
source identity check (2761) and the end of the function (2776-2778) were read in this round.

Ten selected branches, denial and fail-closed first, then boundaries, then error paths:

1. 2713-2719 _import_plan gitlink: a seeded 160000 whose path is now a file is refused; an
   empty directory is planned by its id; one holding an entry is refused.
   Catches: the isdir test or the scandir emptiness test removed.
2. 2720-2726 _import_plan seeded link, identical bytes: a regular file with the link target's
   bytes is planned as 120000: that is how an unchanged seeded link looks, since _write_tree
   writes a link as its target text (owner Q1, A). The card premise (refuse) was wrong.
3. 2721-2722 _import_plan seeded link: a size difference or a directory refuses before _blob_id
   is called. Catches: the size or isdir clause removed, or the order changed.
4. 2696-2697 _import_plan root skip: the root `.git` and `git~1` are skipped, and a nested `.git`
   is refused by _seed_path (2703, refused_component). CORRECTED PREMISE: the card expected a nested
   `.git` to be planned; the source refuses it through _seed_path, which matches docstring 2671-2672.
5. 2704-2706 _import_plan case collision: two names differing only in case in one directory raise.
   Catches: the folded setdefault check removed.
6. 2700-2702 _import_plan non-UTF-8 name: a lone surrogate raises 'a path that is not UTF-8' before
   any plan entry. Catches: the encode test removed.
7. 2707-2709 and 2683-2685 budgets: SEED_MAX_ENTRIES and SEED_MAX_BYTES refuse past their bound; the
   link budget is taken before _blob_id reads a byte. Catches: either bound removed or moved after.
8. 2730-2731 and 2737-2738 _import_plan counts: an empty directory is dropped and counted; 'deleted'
   counts seeded paths absent from the plan. Catches: the counter or the set difference removed.
9. 2678 and 2711 _import_plan mode: a seeded 100755 keeps its mode; a new file is 100644; the seed
   is looked up by exact path, so a case-folded match gets the new-file mode.
   Catches: the seed lookup or its default removed.
10. 2746-2757 _import_stream header and link/gitlink lines: the commit header carries the ref,
    committer identity, byte length of the message and seed revision, then deleteall; a seeded link or
    gitlink is an 'M <mode> <id> <name>' line with sent filled and no file opened.
    Catches: the header fields, the link branch or the sent bookkeeping removed.

Fake os.scandir and a fake _plain drive every case that needs no real bytes. The 120000 premise and
the stream's identity check use real files under tmp_path. No git, no subprocess, no Win32, no network.
"""

import hashlib
import os
import re
import stat
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.node import local
from archeus.node.local import StoreError


def _blob(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


class _Ample:
    def left(self):
        return 1e9


class _Scan:
    def __init__(self, names):
        self.names = names

    def __enter__(self):
        return iter([SimpleNamespace(name=n) for n in self.names])

    def __exit__(self, *exc):
        return False


def _fake_tree(monkeypatch, tree):
    """tree: {rel: ('d',) | ('f', size, dev, ino)}, rel '/'-separated, '' is the root."""
    work = os.path.abspath('fake-work')

    def key(rel):
        return os.path.join(work, *rel.split('/')) if rel else work

    stats = {key(rel): v for rel, v in tree.items()}
    stats[work] = ('d',)

    def fake_plain(p, is_dir):
        v = stats[p]
        if v[0] == 'd':
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_size=0, st_dev=1, st_ino=1,
                                   st_nlink=1)
        return SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_size=v[1], st_dev=v[2],
                               st_ino=v[3], st_nlink=1)

    def scandir(d):
        rel = '' if d == work else os.path.relpath(d, work).replace(os.sep, '/')
        names = [r.rsplit('/', 1)[-1] for r in tree
                 if (r.rsplit('/', 1)[0] if '/' in r else '') == rel]
        return _Scan(names)

    monkeypatch.setattr(local, '_plain', fake_plain)
    monkeypatch.setattr(local, 'os', SimpleNamespace(scandir=scandir, path=os.path, sep=os.sep))
    return work


def _seed(*entries):
    return SimpleNamespace(entries=list(entries))


def _plan(monkeypatch, tree, *entries):
    work = _fake_tree(monkeypatch, tree)
    return local._import_plan(work, _seed(*entries), _Ample())


def test_a_seeded_gitlink_that_became_a_file_or_holds_an_entry_is_refused(monkeypatch):
    oid = 'c' * 40
    row = ('160000', oid, None, 'sub')
    with pytest.raises(StoreError, match='the seeded gitlink sub was changed'):
        _plan(monkeypatch, {'sub': ('f', 1, 1, 1)}, row)
    with pytest.raises(StoreError, match='the seeded gitlink sub was changed'):
        _plan(monkeypatch, {'sub': ('d',), 'sub/x': ('f', 1, 1, 2)}, row)
    plan, _counts = _plan(monkeypatch, {'sub': ('d',)}, row)
    assert plan == [('160000', 'sub', oid, None)]


def test_an_unchanged_seeded_link_written_as_its_target_text_is_kept_as_a_link(tmp_path):
    # _write_tree seeds a link as a plain file holding its target text (owner Q1, A)
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'link').write_bytes(b'bin.dat')
    oid = _blob(b'bin.dat')
    plan, _counts = local._import_plan(str(work), _seed(('120000', oid, 7, 'link')), _Ample())
    assert plan == [('120000', 'link', oid, None)]


def test_a_seeded_link_of_another_size_or_a_directory_is_refused_before_it_is_hashed(monkeypatch):
    row = ('120000', _blob(b'bin.dat'), 7, 'link')
    monkeypatch.setattr(local, '_blob_id', lambda *a, **k: pytest.fail('hashed'))
    with pytest.raises(StoreError, match='the seeded link link was changed'):
        _plan(monkeypatch, {'link': ('f', 99, 1, 2)}, row)
    with pytest.raises(StoreError, match='the seeded link link was changed'):
        _plan(monkeypatch, {'link': ('d',)}, row)


def test_the_root_git_is_skipped_and_a_nested_one_is_refused_as_a_path_core_does_not_seed(
        monkeypatch):
    tree = {'.git': ('d',), 'git~1': ('f', 1, 1, 9), 'a.txt': ('f', 3, 1, 1)}
    plan, _counts = _plan(monkeypatch, tree, ('100644', _blob(b'one'), 3, 'a.txt'))
    assert [p for _m, p, _o, _s in plan] == ['a.txt']
    nested = {'sub': ('d',), 'sub/.git': ('f', 1, 1, 5)}
    with pytest.raises(StoreError, match='a path Core does not seed'):
        _plan(monkeypatch, nested)


def test_two_names_one_case_insensitive_name_in_one_directory_refuse(monkeypatch):
    with pytest.raises(StoreError, match='two paths one case-insensitive name'):
        _plan(monkeypatch, {'A.txt': ('f', 1, 1, 1), 'a.txt': ('f', 1, 1, 2)})


def test_a_name_that_is_not_utf8_refuses_before_any_entry_is_planned(monkeypatch):
    with pytest.raises(StoreError, match='a path that is not UTF-8'):
        _plan(monkeypatch, {'\udc80': ('f', 1, 1, 1)})


def test_the_entry_and_byte_budgets_refuse_past_their_bounds(monkeypatch):
    monkeypatch.setattr(local, 'SEED_MAX_ENTRIES', 2)
    with pytest.raises(StoreError, match='a workspace past 2 entries'):
        _plan(monkeypatch, {'a': ('f', 1, 1, 1), 'b': ('f', 1, 1, 2), 'c': ('f', 1, 1, 3)})
    monkeypatch.setattr(local, 'SEED_MAX_ENTRIES', 100000)
    monkeypatch.setattr(local, 'SEED_MAX_BYTES', 5)
    with pytest.raises(StoreError, match='a workspace past 5 bytes'):
        _plan(monkeypatch, {'a': ('f', 3, 1, 1), 'b': ('f', 4, 1, 2)})


def test_a_link_past_the_byte_budget_is_refused_before_its_id_is_taken(monkeypatch):
    monkeypatch.setattr(local, 'SEED_MAX_BYTES', 2)
    monkeypatch.setattr(local, '_blob_id', lambda *a, **k: pytest.fail('hashed'))
    with pytest.raises(StoreError, match='a workspace past 2 bytes'):
        _plan(monkeypatch, {'link': ('f', 3, 1, 2)}, ('120000', _blob(b'xyz'), 3, 'link'))


def test_an_empty_directory_is_dropped_and_a_seeded_path_absent_is_counted_deleted(monkeypatch):
    plan, counts = _plan(monkeypatch, {'a.txt': ('f', 3, 1, 1), 'empty': ('d',)},
                         ('100644', _blob(b'one'), 3, 'a.txt'),
                         ('100644', _blob(b'two'), 3, 'gone.txt'))
    assert [p for _m, p, _o, _s in plan] == ['a.txt']
    assert counts == {'deleted': 1, 'dropped_dirs': 1}


def test_a_seeded_mode_is_kept_by_exact_path_and_a_new_or_recased_file_is_100644(monkeypatch):
    plan, _counts = _plan(monkeypatch, {'run.sh': ('f', 3, 1, 1)},
                          ('100755', _blob(b'#!x'), 3, 'run.sh'))
    assert [(m, p) for m, p, _o, _s in plan] == [('100755', 'run.sh')]
    plan, _counts = _plan(monkeypatch, {'Run.sh': ('f', 3, 1, 1)},
                          ('100755', _blob(b'#!x'), 3, 'run.sh'))
    assert [(m, p) for m, p, _o, _s in plan] == [('100644', 'Run.sh')]


def test_the_stream_header_then_links_and_gitlinks_by_id_without_opening_a_file(monkeypatch):
    monkeypatch.setattr(local, 'open', lambda *a, **k: pytest.fail('opened'), raising=False)
    eid = ids.new_id('execution')
    msg = b'archeus: the workspace of %s\n' % eid.encode('ascii')
    plan = [('120000', 'link', 'a' * 40, None), ('160000', 'sub', 'c' * 40, None)]
    sent = {}
    chunks = list(local._import_stream(eid, 'e' * 40, plan, _Ample(), sent))
    body = b''.join(chunks)
    head = re.match(rb'commit (\S+)\ncommitter Archeus <archeus@localhost> \d+ \+0000\n'
                    rb'data (\d+)\n', body)
    assert head and head.group(1) == local._import_ref(eid).encode('ascii')
    assert int(head.group(2)) == len(msg)
    assert b'\nfrom %s\ndeleteall\n' % (b'e' * 40) in body
    assert b'M 120000 %s link\n' % (b'a' * 40) in body
    assert b'M 160000 %s sub\n' % (b'c' * 40) in body
    assert sent == {'link': ('120000', 'a' * 40), 'sub': ('160000', 'c' * 40)}
    assert body.endswith(b'done\n')
