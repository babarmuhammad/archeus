"""T-1316 · the highest-risk uncovered branches of `tools/_rename_brand.py` lines
37-149 inclusive (the shared SKIP / HOLD contract; tip 51f4af3f, relocated at the
current tip): denial and fail-closed first, then boundaries, then error paths.

Candidate list, ranked (file:line, closest existing test, why it misses):
 1. _rename_brand.py:107        a SKIP file listed by git is not yielded and never
                                opened by main -> tests/test_no_old_brand_string.py reads SKIP only.
                                -> test_a_skipped_file_is_not_yielded_or_opened
 2. _rename_brand.py:117-122    every HOLD string survives while the unheld brand
                                beside it changes -> no test drives substitute.
                                -> test_every_held_string_survives_while_the_unheld_brand_changes
 3. _rename_brand.py:119-120    all three SUBS spellings replaced outside held text
                                -> none exact. -> test_all_three_case_spellings_are_replaced_outside_held_strings
 4. _rename_brand.py:117-122    repeated held strings in one text survive in order
                                -> none exact. -> test_repeated_held_strings_survive_in_order
 5. _rename_brand.py:141-145    main rewrites a changed ordinary file and keeps the
                                held domain in the same file -> none exact.
                                -> test_main_rewrites_an_ordinary_file_and_keeps_the_held_domain
 6. _rename_brand.py:142        held-only file is not written: no write open, bytes
                                and mtime preserved -> none exact.
                                -> test_a_held_only_file_is_not_written
 7. _rename_brand.py:135        CRLF survives read, substitute and write
                                -> none exact. -> test_a_crlf_file_keeps_its_bytes
 8. _rename_brand.py:107,141    a SKIP file with the old string beside an eligible
                                changed file stays untouched; substitute takes no filename
                                -> none exact. -> test_a_skipped_file_with_the_old_string_stays_untouched
 9. _rename_brand.py:37         the test suite imports SKIP and HOLD from this tool
                                -> none that reads the import. -> test_the_brand_test_imports_skip_and_hold_from_the_tool
10. _rename_brand.py:117-149    a second substitute and main pass after mixed input
                                changes nothing -> none exact.
                                -> test_a_second_pass_after_mixed_input_changes_nothing

For each test the source branch whose removal or inversion it breaks is the one
named in the candidate list above.

No defect in these ten: every test passes against the current source, so none is
marked xfail. Fakes: `git ls-files` is a fake subprocess (no real git), `io` is a
recording wrapper around the real module, and ROOT is redirected to tmp_path. The
only real read is the repository's own test file, read as text for the import
contract. No network, no sleep, no environment read.
"""

import importlib
import inspect
import io as real_io
import os
import sys
from types import SimpleNamespace

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(REPO, 'tools'))

rb = importlib.import_module('_rename_brand')

OLD, NEW = rb.SUBS[0]
OLD_T, NEW_T = rb.SUBS[1]
OLD_U, NEW_U = rb.SUBS[2]
DOMAIN = next(k for k in rb.HOLD if k.endswith('.space'))
SKIP_FILE = 'CHANGELOG.md'
SKIP_DIR_FILE = 'claude_sessions/migrate.py'


class _Git:
    def __init__(self, names):
        self.names = names

    def run(self, args, **kwargs):
        return SimpleNamespace(stdout='\n'.join(self.names) + '\n')


class _IO:
    def __init__(self):
        self.opened = []

    def open(self, path, mode='r', **kwargs):
        self.opened.append((path, mode))
        return real_io.open(path, mode, **kwargs)


def _setup(tmp_path, monkeypatch, files, names=None):
    for rel, data in files.items():
        dest = tmp_path.joinpath(*rel.split('/'))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    monkeypatch.setattr(rb, 'ROOT', str(tmp_path))
    monkeypatch.setattr(rb, 'subprocess', _Git(list(files) if names is None else names))
    spy = _IO()
    monkeypatch.setattr(rb, 'io', spy)
    return spy


def _bytes(tmp_path, rel):
    return tmp_path.joinpath(*rel.split('/')).read_bytes()


def test_a_skipped_file_is_not_yielded_or_opened(tmp_path, monkeypatch, capsys):
    spy = _setup(tmp_path, monkeypatch,
                 {SKIP_FILE: (OLD + ' log\n').encode(), 'README.md': b'plain\n'},
                 names=[SKIP_FILE, 'README.md'])
    assert list(rb.tracked_text_files()) == ['README.md']
    before = _bytes(tmp_path, SKIP_FILE)
    rb.main()
    capsys.readouterr()
    skipped_path = os.path.join(str(tmp_path), SKIP_FILE)
    assert all(p != skipped_path for p, _ in spy.opened)
    assert _bytes(tmp_path, SKIP_FILE) == before


def test_every_held_string_survives_while_the_unheld_brand_changes():
    for key in rb.HOLD:
        assert rb.substitute('%s and %s' % (key, OLD)) == '%s and %s' % (key, NEW)


def test_all_three_case_spellings_are_replaced_outside_held_strings():
    src = '%s %s %s %s' % (OLD, OLD_T, OLD_U, DOMAIN)
    assert rb.substitute(src) == '%s %s %s %s' % (NEW, NEW_T, NEW_U, DOMAIN)


def test_repeated_held_strings_survive_in_order():
    keys = list(rb.HOLD) * 2
    src = ' | '.join(part for key in keys for part in (key, OLD))
    want = ' | '.join(part for key in keys for part in (key, NEW))
    got = rb.substitute(src)
    assert got == want
    assert '\x00' not in got


def test_main_rewrites_an_ordinary_file_and_keeps_the_held_domain(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch, {'README.md': ('site %s and %s\n' % (DOMAIN, OLD)).encode()})
    assert rb.main() == 0
    assert _bytes(tmp_path, 'README.md') == ('site %s and %s\n' % (DOMAIN, NEW)).encode()
    assert '1 files rewritten' in capsys.readouterr().out


def test_a_held_only_file_is_not_written(tmp_path, monkeypatch, capsys):
    rel = 'docs/held.md'
    data = ('only %s here\n' % DOMAIN).encode()
    spy = _setup(tmp_path, monkeypatch, {rel: data})
    dest = tmp_path.joinpath(*rel.split('/'))
    os.utime(dest, ns=(1_000_000_000, 1_000_000_000))
    before = dest.stat().st_mtime_ns
    rb.main()
    capsys.readouterr()
    assert all(mode == 'r' for _, mode in spy.opened)
    assert _bytes(tmp_path, rel) == data
    assert dest.stat().st_mtime_ns == before


def test_a_crlf_file_keeps_its_bytes(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch, {'README.md': ('first\r\n%s second\r\n' % OLD).encode()})
    rb.main()
    capsys.readouterr()
    assert _bytes(tmp_path, 'README.md') == ('first\r\n%s second\r\n' % NEW).encode()


def test_a_skipped_file_with_the_old_string_stays_untouched(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch,
           {SKIP_FILE: ('%s old\n' % OLD).encode(), 'README.md': ('%s new\n' % OLD).encode()},
           names=[SKIP_FILE, 'README.md'])
    rb.main()
    capsys.readouterr()
    assert _bytes(tmp_path, SKIP_FILE) == ('%s old\n' % OLD).encode()
    assert _bytes(tmp_path, 'README.md') == ('%s new\n' % NEW).encode()
    assert list(inspect.signature(rb.substitute).parameters) == ['src']


def test_the_brand_test_imports_skip_and_hold_from_the_tool():
    with real_io.open(os.path.join(REPO, 'tests', 'test_no_old_brand_string.py'),
                      encoding='utf-8') as f:
        text = f.read()
    assert 'from _rename_brand import HOLD, SKIP' in text
    assert 'tests/test_no_old_brand_string.py' in rb.SKIP
    assert SKIP_DIR_FILE in rb.SKIP


def test_a_second_pass_after_mixed_input_changes_nothing(tmp_path, monkeypatch, capsys):
    rel = 'README.md'
    _setup(tmp_path, monkeypatch,
           {rel: ('%s %s %s\n' % (DOMAIN, OLD, OLD_T)).encode()})
    rb.main()
    once = _bytes(tmp_path, rel)
    assert once == ('%s %s %s\n' % (DOMAIN, NEW, NEW_T)).encode()
    capsys.readouterr()
    rb.main()
    assert '0 files rewritten' in capsys.readouterr().out
    assert _bytes(tmp_path, rel) == once
    text = once.decode('utf-8')
    assert rb.substitute(text) == text
