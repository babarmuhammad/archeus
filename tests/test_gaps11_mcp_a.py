"""T-1399 · the highest-risk UNCOVERED branches of claude_sessions/mcp.py, lines
121-205 (_status_icon, _mcp_background, analyze_mcp_tools, and the global
CLAUDE.md MCP section writer update_global_claude_md_mcp), at tip 6a32dc14.

The existing suites already pin most of this slice: a stray START beside its
own END (test_gaps7_claude_sessions_mcp_a.py:164), a second same-name pair
(:146), an unreadable file (:93), a byte-exact replace (:208), a missing file
(:121), the status icon fall-through (test_gaps3_claude_sessions_mcp_a.py:386)
and the Codex reader's raising path (test_gaps3_claude_sessions_mcp_a.py:358).
Those are not repeated here. The tests below cover what they leave open:

 1. mcp.py:202-203  trailing newlines only: appended after one blank line
                    -> test_append_after_trailing_newlines_only
 2. mcp.py:200-201  a whitespace-only file is not a missing one (no stub)
                    -> test_whitespace_only_file_is_appended_to_not_stubbed
 3. mcp.py:149-151  no claude executable: analyze never calls the model
                    -> test_analyze_no_exe_never_calls_model
 4. mcp.py:159-163  a None reply is '' and a reply is stripped; timeout and
                    crumbs are the ones the menu relies on
                    -> test_analyze_reply_is_stripped_and_none_is_empty
 5. mcp.py:135-140  a status failure sets the error flag, marks ready and keeps
                    the last good server list -> test_background_failure_sets_error_and_ready
 6. mcp.py:189-193  a stray START beside ANOTHER server's complete block refuses
                    and writes nothing -> test_stray_start_beside_another_servers_block_refuses
 7. mcp.py:196-197  two same-name pairs with another server's block between them
                    refuse -> test_two_same_name_pairs_with_another_block_between_refuse
 8. mcp.py:188      XFAIL (strict): the read is in text mode, so CRLF outside the
                    block is written back as LF -> test_crlf_outside_block_survives_the_rewrite

Every file is under tmp_path; the global CLAUDE.md is redirected through
config.global_claude_md_for. The model, the executable lookup, the status reader
and the logger are faked. No real subprocess, network or account home.
"""
import os

import pytest

from claude_sessions import config as _c
from claude_sessions import memory

_real_get_claude_exe = _c.get_claude_exe
_c.get_claude_exe = lambda: None                # noqa: E731 — import guard only
try:
    from claude_sessions import mcp as mcp_mod
finally:
    _c.get_claude_exe = _real_get_claude_exe

FAKE_EXE = os.path.join('C:\\fake', 'claude.exe')


def _start(name):
    return f'<!-- MCP:{name}:START -->'


def _end(name):
    return f'<!-- MCP:{name}:END -->'


def _section(name, doc):
    return f"{_start(name)}\n## MCP: {name}\n{doc}\n{_end(name)}\n"


@pytest.fixture
def md(tmp_path, monkeypatch):
    path = str(tmp_path / 'home' / 'CLAUDE.md')
    os.makedirs(os.path.dirname(path))
    monkeypatch.setattr(_c, 'global_claude_md_for', lambda cfgdir=None: path)
    return path


def _put(path, data):
    with open(path, 'wb') as f:
        f.write(data)


def _get(path):
    with open(path, 'rb') as f:
        return f.read()


def _spy_writes(monkeypatch):
    calls = []

    def spy(path, text, mode=None):
        calls.append((path, text))
        return True

    monkeypatch.setattr(_c, 'write_atomic', spy)
    return calls


def test_append_after_trailing_newlines_only(md):
    """Branch: mcp.py:201 — a non-empty file with no block: its trailing newlines
    are cut to one blank line before the section."""
    _put(md, b'Notes for the team\n\n\n')
    assert mcp_mod.update_global_claude_md_mcp('svc', 'DOC') is True
    assert _get(md) == ('Notes for the team\n\n' + _section('svc', 'DOC')).encode('utf-8')


def test_whitespace_only_file_is_appended_to_not_stubbed(md):
    """Branch: mcp.py:200-201 — a file that holds only spaces is non-empty: the
    section is appended, and the new-file stub is not written."""
    _put(md, b'   \n')
    assert mcp_mod.update_global_claude_md_mcp('svc', 'DOC') is True
    data = _get(md)
    assert data == ('   \n\n' + _section('svc', 'DOC')).encode('utf-8')
    assert b'Global Claude Context' not in data


def test_analyze_no_exe_never_calls_model(monkeypatch):
    """Branch: mcp.py:149-151 — no claude executable: the analysis answers ''
    and the model is never called."""
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: None)
    calls = []
    monkeypatch.setattr(memory, '_claude_stdin', lambda *a, **k: calls.append((a, k)) or 'x')
    assert mcp_mod.analyze_mcp_tools('svc') == ''
    assert calls == []


def test_analyze_reply_is_stripped_and_none_is_empty(monkeypatch):
    """Branch: mcp.py:159-163 — the model gets timeout 120 and the MCP ANALYSIS
    crumbs; a None reply is '' and a real reply is stripped."""
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: FAKE_EXE)
    replies = [None, '  | tool |\n  ok \n']
    calls = []

    def fake(prompt, cwd, timeout=None, crumbs=None, label=None):
        calls.append((prompt, cwd, timeout, crumbs))
        return replies.pop(0)

    monkeypatch.setattr(memory, '_claude_stdin', fake)
    assert mcp_mod.analyze_mcp_tools('svc') == ''
    assert mcp_mod.analyze_mcp_tools('svc') == '| tool |\n  ok'
    for prompt, cwd, timeout, crumbs in calls:
        assert 'svc' in prompt
        assert cwd is None
        assert timeout == 120
        assert crumbs == ('ARCHEUS', 'svc', 'MCP ANALYSIS')


def test_background_failure_sets_error_and_ready(monkeypatch):
    """Branch: mcp.py:137-140 — a failing status read sets the error flag, logs,
    marks the status ready, and leaves the last good server list in place."""
    monkeypatch.setattr(mcp_mod, '_mcp_error', False)
    monkeypatch.setattr(mcp_mod, '_mcp_ready', False)
    monkeypatch.setattr(mcp_mod, 'mcp_servers', [('keep', 'ok')])
    logged = []

    class _Log:
        def exception(self, msg, *a, **k):
            logged.append(msg)

    def broken(*a, **k):
        raise RuntimeError('synthetic status failure')

    monkeypatch.setattr(mcp_mod, 'get_mcp_status', broken)
    monkeypatch.setattr(_c, 'log', _Log())
    mcp_mod._mcp_background()
    assert mcp_mod._mcp_error is True
    assert mcp_mod._mcp_ready is True
    assert mcp_mod.mcp_servers == [('keep', 'ok')]
    assert logged == ['mcp status failed']


def test_stray_start_beside_another_servers_block_refuses(md, monkeypatch):
    """Branch: mcp.py:189-193 — a stray START for this server is refused even
    when another server's complete block sits in the same file; no write."""
    original = (_section('db', 'DB DOC') + 'MANUAL\n' + _start('svc') + '\nHALF\n').encode('utf-8')
    _put(md, original)
    writes = _spy_writes(monkeypatch)
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW') is False
    assert writes == []
    assert _get(md) == original


def test_two_same_name_pairs_with_another_block_between_refuse(md, monkeypatch):
    """Branch: mcp.py:196-197 — two complete pairs for this server, with another
    server's block between them, are refused: the file stays byte-identical."""
    original = (_section('svc', 'A') + _section('db', 'B') + _section('svc', 'C')).encode('utf-8')
    _put(md, original)
    writes = _spy_writes(monkeypatch)
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW') is False
    assert writes == []
    assert _get(md) == original


@pytest.mark.xfail(
    strict=True,
    reason="claude_sessions/mcp.py:188 reads CLAUDE.md in text mode, so every CRLF "
           "outside the MCP block is written back as LF on every platform; "
           "claude_md.py:103 reads with newline='' and keeps the bytes")
def test_crlf_outside_block_survives_the_rewrite(md):
    """Branch: mcp.py:188 — bytes outside the block must survive the rewrite."""
    original = b'# Mine\r\nkeep this line\r\n\r\n'
    _put(md, original)
    assert mcp_mod.update_global_claude_md_mcp('svc', 'DOC') is True
    assert _get(md).startswith(b'# Mine\r\nkeep this line\r\n')
