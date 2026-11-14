"""T-1387: claude_sessions/store.py lines 123-158 at tip 73ad7a90 (temp_root and
under_temp). Candidate probes, not measured coverage. Filesystem-root, profile,
sibling-prefix, empty-input and gettempdir-failure cases are already pinned by
tests/test_gaps6_claude_sessions_store_b.py and tests/test_codex.py.

Branches: 136 a relative temp is made absolute; 146-158 a trailing separator is
normalised; 154-156 a refused root classifies nothing as temp; 157-158 temp_root
is read on every call; 150-152 normcase decides case, faked so it runs on any OS.
"""

import os
import tempfile

from claude_sessions import config as _c
from claude_sessions import store


def test_temp_root_absolutises_a_relative_temp(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: 'scratch')
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    assert store.temp_root() == os.path.abspath(os.path.join(str(tmp_path), 'scratch'))


def test_under_temp_trailing_separator_is_normalised(monkeypatch, tmp_path):
    root = tmp_path / 'tmp'
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(root))
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    assert store.under_temp(str(root) + os.sep) is True


def test_refused_root_never_matches(monkeypatch, tmp_path):
    anchor = os.path.splitdrive(str(tmp_path))[0] + os.sep
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: anchor)
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    assert store.temp_root() == ''
    assert store.under_temp(anchor) is False
    assert store.under_temp(os.path.join(anchor, 'anything')) is False


def test_under_temp_reads_temp_on_every_call(monkeypatch, tmp_path):
    first, second = tmp_path / 'a', tmp_path / 'b'
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(first))
    assert store.under_temp(str(first / 'x')) is True
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(second))
    assert store.under_temp(str(first / 'x')) is False
    assert store.under_temp(str(second / 'x')) is True


def test_under_temp_case_folding_follows_normcase(monkeypatch, tmp_path):
    monkeypatch.setattr(os.path, 'normcase', lambda p: p.lower())
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path / 'Temp'))
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    assert store.under_temp(str(tmp_path / 'temp' / 'x')) is True
