"""T-1310: the highest-risk uncovered branches of archeus claude_sessions/mcp.py
lines 171-200 inclusive (tip 51f4af3f), `update_global_claude_md_mcp`.

The ten selected branches, denial and fail-closed first, then boundaries, then
error paths:

 1. mcp.py:185-190  an existing file that cannot be read (PermissionError) is
                    refused: no write, bytes unchanged
 2. mcp.py:189-190  any other read exception is refused the same way, never
                    replaced by an empty context
 3. mcp.py:199-200  a missing file gets the header plus one complete named
                    section through the atomic writer
 4. mcp.py:192      END before START is refused and the manual text is preserved
 5. mcp.py:192-194  two complete same-name pairs: the update must not leave a
                    stale duplicate managed section behind
 6. mcp.py:192      START without END is refused and nothing is appended
 7. mcp.py:192      END without START is refused and the manual bytes survive
 8. mcp.py:194-196  one well-ordered pair is replaced with prefix and suffix,
                    including an adjacent other MCP section, untouched
 9. mcp.py:202      a False from the atomic writer is returned as False, with no
                    fallback plain write
10. mcp.py:181-183  an empty tools doc and a non-ASCII name produce one matching
                    sentinel pair, and a repeated update leaves one pair

Every probe is a fake or a tmp_path file: the global CLAUDE.md is pointed at a
path under tmp_path through `config.global_claude_md_for`, and the read-error
probes replace `builtins.open` for that one path only. No real user home, no
credential file, no subprocess, no network.
"""
import builtins
import errno
import os

import pytest

from claude_sessions import config as _c
from claude_sessions import mcp as mcp_mod


_REAL_OPEN = builtins.open


def _start(name):
    return f'<!-- MCP:{name}:START -->'


def _end(name):
    return f'<!-- MCP:{name}:END -->'


@pytest.fixture
def md(tmp_path, monkeypatch):
    """The one global CLAUDE.md this module may touch, under tmp_path."""
    path = str(tmp_path / 'home' / 'CLAUDE.md')
    os.makedirs(os.path.dirname(path))
    monkeypatch.setattr(_c, 'global_claude_md_for', lambda cfgdir=None: path)
    return path


def _write(path, text):
    with _REAL_OPEN(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def _read(path):
    with _REAL_OPEN(path, encoding='utf-8') as f:
        return f.read()


def _fail_reads_of(path, exc):
    target = os.path.normcase(os.path.abspath(path))

    def fake_open(file, *a, **k):
        if os.path.normcase(os.path.abspath(str(file))) == target:
            raise exc
        return _REAL_OPEN(file, *a, **k)
    return fake_open


def _spy_writes(monkeypatch):
    writes = []

    def spy(path, text, mode=None):
        writes.append((path, text))
        return _REAL_WRITE(path, text, mode)
    monkeypatch.setattr(_c, 'write_atomic', spy)
    return writes


_REAL_WRITE = _c.write_atomic


def test_an_unreadable_existing_file_is_refused_and_left_as_it_was(md, monkeypatch):
    """Branch: mcp.py:188-190 with PermissionError. The file's text is unknown, so
    it is not ours to replace: no write, and the bytes stay exactly the same."""
    original = '# Mine\nKEEP THIS\n'
    _write(md, original)
    writes = _spy_writes(monkeypatch)
    monkeypatch.setattr(builtins, 'open',
                        _fail_reads_of(md, PermissionError(errno.EACCES, 'synthetic')))
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is False
    monkeypatch.setattr(builtins, 'open', _REAL_OPEN)
    assert writes == []
    assert _read(md) == original


def test_any_other_read_error_refuses_and_never_substitutes_an_empty_context(md, monkeypatch):
    """Branch: mcp.py:189-190 `except Exception`. A read that fails for any other
    reason must not be treated as an empty file, which would overwrite it."""
    original = '# Mine\nKEEP THIS TOO\n'
    _write(md, original)
    writes = _spy_writes(monkeypatch)
    monkeypatch.setattr(builtins, 'open',
                        _fail_reads_of(md, OSError(errno.EIO, 'synthetic')))
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is False
    monkeypatch.setattr(builtins, 'open', _REAL_OPEN)
    assert writes == []
    assert _read(md) == original


def test_a_missing_file_gets_the_header_and_one_complete_section(md, monkeypatch):
    """Branch: mcp.py:199-200. No file yet: the header plus exactly one named
    section, written through the atomic writer."""
    writes = _spy_writes(monkeypatch)
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is True
    assert len(writes) == 1 and writes[0][0] == md
    text = writes[0][1]
    assert text.startswith('# Global Claude Context\n')
    assert text.count(_start('svc')) == 1 and text.count(_end('svc')) == 1
    assert text.index(_start('svc')) < text.index('NEW DOC') < text.index(_end('svc'))
    assert _read(md) == text


def test_end_before_start_is_refused_and_the_manual_text_is_preserved(md, monkeypatch):
    """Branch: mcp.py:192 `well_formed`. The markers are out of order, so the
    rewrite is refused: the manual lines keep their order and nothing is added."""
    original = (f'MANUAL-A\n{_end("svc")}\nMANUAL-B\n{_start("svc")}\n'
                f'MANUAL-C\n')
    _write(md, original)
    writes = _spy_writes(monkeypatch)
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is False
    assert writes == []
    assert _read(md) == original


def test_two_complete_same_name_pairs_never_leave_a_stale_duplicate(md):
    """Branch: mcp.py:192-196. Two complete pairs with the same name are
    ambiguous. Either the update is refused and the file is unchanged, or it
    leaves exactly one managed pair; a second pair carrying the old doc must not
    survive a successful update.

    Source replaces the first pair and keeps the second with its old doc, so this
    is a strict xfail on the safety property."""
    original = (f'{_start("svc")}\n## MCP: svc\nSTALE ONE\n{_end("svc")}\n'
                f'GAP\n'
                f'{_start("svc")}\n## MCP: svc\nSTALE TWO\n{_end("svc")}\n')
    _write(md, original)
    ok = mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md))
    text = _read(md)
    assert text == original or text.count(_start('svc')) == 1, (
        'a duplicate managed pair survived the update: ok=%r' % (ok,))


def test_start_without_end_is_refused_and_nothing_is_appended(md, monkeypatch):
    """Branch: mcp.py:192. A START with no END is a malformed block. The file is
    not rewritten: no second START and no appended section."""
    original = f'MANUAL-A\n{_start("svc")}\nHALF BLOCK\nMANUAL-B\n'
    _write(md, original)
    writes = _spy_writes(monkeypatch)
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is False
    assert writes == []
    assert _read(md) == original


def test_end_without_start_is_refused_and_the_manual_bytes_survive(md, monkeypatch):
    """Branch: mcp.py:192. An orphan END is refused. The manual bytes survive
    exactly and no section is appended after them."""
    original = f'MANUAL-A\n{_end("svc")}\nMANUAL-B'
    _write(md, original)
    writes = _spy_writes(monkeypatch)
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is False
    assert writes == []
    assert _read(md) == original


OTHER_SECTION = f'{_start("other")}\n## MCP: other\nOTHER DOC\n{_end("other")}\n'


def _one_pair_file():
    return (f'PROSE-BEFORE\n{_start("svc")}\n## MCP: svc\nOLD DOC\n'
            f'{_end("svc")}\n{OTHER_SECTION}PROSE-AFTER\n')


def test_one_well_ordered_pair_is_replaced_and_the_neighbour_section_survives(md):
    """Branch: mcp.py:194-196 `existing[:span[0]] + section + existing[span[1]:]`.
    The prose before, the prose after, and an adjacent other MCP section keep
    their content; only the svc doc changes."""
    _write(md, _one_pair_file())
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is True
    text = _read(md)
    assert text.startswith('PROSE-BEFORE\n')
    assert text.endswith('PROSE-AFTER\n')
    assert text.count(OTHER_SECTION) == 1
    assert 'NEW DOC' in text and 'OLD DOC' not in text
    assert text.count(_start('svc')) == 1 and text.count(_end('svc')) == 1


def test_one_well_ordered_pair_replacement_is_byte_exact_outside_the_pair(md):
    """Branch: mcp.py:196 `existing[span[1]:]`. Everything outside the pair must
    be byte-identical after the replacement."""
    _write(md, _one_pair_file())
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is True
    expected = (f'PROSE-BEFORE\n{_start("svc")}\n## MCP: svc\nNEW DOC\n'
                f'{_end("svc")}\n{OTHER_SECTION}PROSE-AFTER\n')
    assert _read(md) == expected


def test_a_refused_atomic_write_returns_false_with_no_fallback_write(md, monkeypatch):
    """Branch: mcp.py:202 `return _c.write_atomic(...)`. A False from the atomic
    writer is the answer; there is no second, plain write that could leave a
    truncated file."""
    original = '# Mine\nKEEP\n'
    _write(md, original)
    calls = []
    monkeypatch.setattr(_c, 'write_atomic', lambda path, text, mode=None: calls.append(path) or False)
    plain = []
    monkeypatch.setattr(builtins, 'open', _spy_open(md, plain))
    assert mcp_mod.update_global_claude_md_mcp('svc', 'NEW DOC', os.path.dirname(md)) is False
    monkeypatch.setattr(builtins, 'open', _REAL_OPEN)
    assert calls == [md]
    assert plain == []
    assert _read(md) == original


def _spy_open(path, log):
    target = os.path.normcase(os.path.abspath(path))

    def fake_open(file, mode='r', *a, **k):
        if os.path.normcase(os.path.abspath(str(file))) == target and 'w' in mode:
            log.append(mode)
        return _REAL_OPEN(file, mode, *a, **k)
    return fake_open


def test_an_empty_doc_and_a_non_ascii_name_keep_one_pair_across_updates(md):
    """Branch: mcp.py:181-183 sentinel construction and 193-196 re-tag. An empty
    doc still produces a matching START/END pair, a non-ASCII name matches
    itself, and a repeated update replaces the pair instead of adding one,
    keeping the prose around it."""
    name = 'svc-é'
    _write(md, 'PROSE-BEFORE\nPROSE-AFTER\n')
    assert mcp_mod.update_global_claude_md_mcp(name, '', os.path.dirname(md)) is True
    first = _read(md)
    assert first.count(_start(name)) == 1 and first.count(_end(name)) == 1
    assert 'PROSE-BEFORE' in first and 'PROSE-AFTER' in first

    assert mcp_mod.update_global_claude_md_mcp(name, 'DOC-é', os.path.dirname(md)) is True
    second = _read(md)
    assert second.count(_start(name)) == 1 and second.count(_end(name)) == 1
    assert 'DOC-é' in second and 'PROSE-BEFORE' in second and 'PROSE-AFTER' in second
