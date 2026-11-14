"""T-1360 · claude_sessions/versions.py lines 607-683: marketplace entry reading, version resolution, clone HEAD and same-version match.

Selected branches, highest risk first:
1. 658 PREMISE: a HEAD of 'ref: ../../<file>' must not read a file outside the clone's .git directory (strict xfail)
2. 631-633 no entry gives ('', '')
3. 635-641 an explicit version wins over a sha; the sha is cut to 12 characters
4. 642-643 source './', '.' or '' uses the clone HEAD through entry _root; a missing root yields ''
5. 644 other git sources return ('', ref) without reading the clone
6. 654-655 a detached HEAD (bare sha) returns its first 12 characters
7. 662-667 the packed-refs fallback matches the exact ref name, not a prefix; a missing file returns ''
8. 678-682 same-version: a sha shorter than 7 characters never matches a longer one; a 7+ character sha matches its full offered sha
9. 611-619 marketplace entries without a name are skipped; a non-dict doc returns nothing; keys are '<name>@<marketplace>'
10. 614 a missing marketplace.json gives no entries, not an error

Plus one strict xfail for 643/647-651: an empty root reads .git/HEAD relative to the working directory.

Seams: plugins.known_marketplaces is replaced with synthetic rows; every clone is a tmp_path tree with synthetic .git/HEAD, packed-refs and marketplace.json. No git, no network, no subprocess.
"""

import json
import os

import pytest

from claude_sessions import plugins
from claude_sessions import versions as v

A = 'a' * 40
B = 'b' * 40
D = 'd' * 40


def _clone(tmp_path, name='mkt'):
    root = tmp_path / 'plugins' / 'marketplaces' / name
    (root / '.git').mkdir(parents=True, exist_ok=True)
    return root


def _head(root, text):
    (root / '.git' / 'HEAD').write_text(text, encoding='utf-8')


def _manifest(root, doc):
    (root / '.claude-plugin').mkdir(parents=True, exist_ok=True)
    text = doc if isinstance(doc, str) else json.dumps(doc)
    (root / '.claude-plugin' / 'marketplace.json').write_text(text, encoding='utf-8')


def _rows(monkeypatch, *rows):
    monkeypatch.setattr(plugins, 'known_marketplaces', lambda cfg_dir=None: list(rows))


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/versions.py:658 - the HEAD ref is joined under .git with no '
    'containment check, so "ref: ../../<file>" reads a file outside the clone'))
def test_a_head_ref_cannot_point_outside_the_git_directory(tmp_path):
    root = _clone(tmp_path)
    (root.parent / 'outside_ref').write_text(A + '\n', encoding='utf-8')
    _head(root, 'ref: ../../outside_ref\n')
    assert v._clone_head(str(root)) == ''


def test_no_entry_or_an_unusable_one_offers_nothing():
    assert v._entry_version({}) == ('', '')
    assert v._entry_version(None) == ('', '')


def test_an_explicit_version_wins_and_a_sha_is_cut_to_twelve(tmp_path):
    assert v._entry_version({'version': '2.0.0', 'source': {'sha': A, 'ref': 'v2'}}) == ('2.0.0', 'v2')
    assert v._entry_version({'source': {'sha': B}}) == (B[:12], '')


@pytest.mark.parametrize('source', ['./', '.', ''])
def test_a_self_source_reads_the_clone_head_and_a_missing_root_yields_nothing(tmp_path, monkeypatch, source):
    root = _clone(tmp_path)
    _head(root, 'ref: refs/heads/main\n')
    (root / '.git' / 'refs' / 'heads').mkdir(parents=True)
    (root / '.git' / 'refs' / 'heads' / 'main').write_text(D + '\n', encoding='utf-8')
    assert v._entry_version({'source': source, '_root': str(root)}) == (D[:12], '')

    empty = tmp_path / 'empty'
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert v._entry_version({'source': source, '_root': ''}) == ('', '')


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/versions.py:643 with 647-651 - an empty _root makes _clone_head read '
    '.git/HEAD relative to the working directory'))
def test_a_missing_root_never_reads_the_working_directory_clone(tmp_path, monkeypatch):
    """versions.py:642-643 with 647-651 — an entry with no root gives _root '',
    and os.path.join('', '.git', 'HEAD') is the working directory's own .git."""
    here = tmp_path / 'here'
    here.mkdir()
    (here / '.git').mkdir()
    (here / '.git' / 'HEAD').write_text(B + '\n', encoding='utf-8')
    monkeypatch.chdir(here)
    assert v._entry_version({'source': './', '_root': ''}) == ('', '')


def test_other_git_sources_return_their_ref_without_reading_the_clone(tmp_path):
    root = _clone(tmp_path)
    _head(root, 'ref: refs/heads/main\n')
    entry = {'_root': str(root), 'source': {
        'source': 'git-subdir', 'url': 'https://example.invalid/x.git', 'ref': 'v1.5.5'}}
    assert v._entry_version(entry) == ('', 'v1.5.5')


def test_a_detached_head_is_its_first_twelve_characters(tmp_path):
    root = _clone(tmp_path)
    _head(root, B + '\n')
    assert v._clone_head(str(root)) == B[:12]


def test_packed_refs_match_the_exact_name_and_a_missing_file_is_empty(tmp_path):
    root = _clone(tmp_path)
    _head(root, 'ref: refs/heads/main\n')
    (root / '.git' / 'packed-refs').write_text(
        '# pack-refs with: peeled\n%s refs/heads/mainline\n%s refs/heads/main\n' % ('f' * 40, D),
        encoding='utf-8')
    assert v._clone_head(str(root)) == D[:12]

    bare = _clone(tmp_path, 'bare')
    _head(bare, 'ref: refs/heads/main\n')
    assert v._clone_head(str(bare)) == ''


def test_same_version_needs_seven_characters_before_a_sha_matches():
    assert v._same_version('abc', 'abcdef0' + '1' * 33) is False
    assert v._same_version('abcdef0', 'abcdef0' + '1' * 33) is True
    assert v._same_version('abcdef0123', 'abcdef0123' + '4' * 30) is True
    assert v._same_version('1.0.0', 'a' * 40, 'a' * 12) is True


def test_a_nameless_entry_is_skipped_and_keys_are_name_at_marketplace(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    _manifest(root, {'plugins': [{'version': '1'}, 'stray',
                                 {'name': 'alpha', 'version': '1.0.0'}, {'name': ''}]})
    _rows(monkeypatch, {'name': 'mkt', 'path': str(root)})
    entries = v._marketplace_entries()
    assert set(entries) == {'alpha@mkt'}
    assert entries['alpha@mkt']['version'] == '1.0.0'
    assert entries['alpha@mkt']['_root'] == str(root)


def test_a_manifest_that_is_not_an_object_yields_nothing(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    _manifest(root, '[{"name": "alpha"}]')
    _rows(monkeypatch, {'name': 'mkt', 'path': str(root)})
    assert v._marketplace_entries() == {}


def test_a_missing_manifest_gives_no_entries_not_an_error(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    _rows(monkeypatch, {'name': 'mkt', 'path': str(root)})
    assert v._marketplace_entries() == {}
