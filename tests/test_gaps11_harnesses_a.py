"""Descriptor table, home lookup and path ownership of claude_sessions/harnesses.py (lines 98-106, 448-528)."""
import importlib
import os
import types

import pytest

from claude_sessions import harnesses as h

CLAUDE = h.HARNESSES['claude']
CODEX = h.HARNESSES['codex']


def test_of_path_home_itself_is_not_owned(tmp_path, monkeypatch):
    home = tmp_path / 'codex'
    monkeypatch.setattr(h, '_homes', lambda: [('codex', str(home))])
    assert h.of_path(str(home)) is CLAUDE
    assert h.of_path(os.path.join(str(home), 'rollout.jsonl')) is CODEX


def test_sibling_home_with_prefix_name_not_captured(tmp_path, monkeypatch):
    monkeypatch.setattr(h, '_homes', lambda: [('codex', str(tmp_path / 'codex'))])
    assert h.of_path(os.path.join(str(tmp_path), 'codex-2', 'rollout.jsonl')) is CLAUDE


@pytest.mark.parametrize('reverse', [False, True])
def test_of_path_longest_home_wins_nested(tmp_path, monkeypatch, reverse):
    outer = tmp_path / 'outer'
    inner = outer / 'inner'
    pairs = [('codex', str(outer)), ('pi', str(inner))]
    if reverse:
        pairs.reverse()
    monkeypatch.setattr(h, '_homes', lambda: pairs)
    assert h.of_path(os.path.join(str(inner), 'x.jsonl')) is h.HARNESSES['pi']
    assert h.of_path(os.path.join(str(outer), 'x.jsonl')) is CODEX


def test_default_home_skipped_in_of_path(tmp_path, monkeypatch):
    pairs = [(h.DEFAULT, str(tmp_path / 'a' / 'b')), ('codex', str(tmp_path / 'a'))]
    monkeypatch.setattr(h, '_homes', lambda: pairs)
    assert h.of_path(os.path.join(str(tmp_path), 'a', 'b', 'x.jsonl')) is CODEX


def test_of_trailing_separator_matches_home_unknown_is_default(tmp_path, monkeypatch):
    home = tmp_path / 'codex'
    monkeypatch.setattr(h, '_homes', lambda: [('codex', str(home))])
    assert h.of(str(home) + os.sep) is CODEX
    assert h.of(str(tmp_path / 'elsewhere')) is CLAUDE
    assert h.of() is CLAUDE


def test_descriptor_unknown_id_is_default():
    assert h.descriptor(None) is CLAUDE
    assert h.descriptor('nope') is CLAUDE
    assert h.descriptor('codex') is CODEX


def test_impl_missing_key_is_keyerror(monkeypatch):
    with pytest.raises(KeyError):
        h.impl('no_such_key', 'codex')

    sentinel = object()
    seen = []

    def fake_import(name, package=None):
        seen.append((name, package))
        return types.SimpleNamespace(scan=sentinel)

    monkeypatch.setattr(importlib, 'import_module', fake_import)
    assert h.impl('scan', 'codex') is sentinel
    assert seen == [('.codex', h.__package__)]


def test_home_dir_relative_to_userprofile_at_call_time(tmp_path, monkeypatch):
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    monkeypatch.setattr(h._c, '_USERPROFILE', str(first))
    assert h.home_dir('codex') == os.path.join(str(first), '.codex')
    assert h.home_dir() == os.path.join(str(first), '.claude')
    monkeypatch.setattr(h._c, '_USERPROFILE', str(second))
    assert h.home_dir('codex') == os.path.join(str(second), '.codex')


def test_claude_exe_names_are_exact_pair():
    assert h._claude_exe_names() == ('claude.exe', 'claude')
    assert CLAUDE['exe_names'] == ('claude.exe', 'claude')


def test_ids_default_first_then_sorted(monkeypatch):
    monkeypatch.setitem(h.HARNESSES, 'zeta', dict(CODEX))
    monkeypatch.setitem(h.HARNESSES, 'alpha', dict(CODEX))
    got = h.ids()
    assert got[0] == h.DEFAULT
    assert got[1:] == sorted(k for k in h.HARNESSES if k != h.DEFAULT)
    assert len(set(got)) == len(got)
