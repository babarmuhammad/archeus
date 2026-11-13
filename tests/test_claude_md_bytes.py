"""Byte-level contract for CLAUDE.md machine-block writers.

A machine-only update must leave every byte outside the owned block spans
untouched: CRLF, mixed newlines, trailing blanks and a missing final newline
all survive. The owned span is the block's marker lines plus the newline that
closed its END line, and the generated body is LF. Files are written and read
back in binary, so no text-mode translation can hide a lost byte.
"""
import os

import pytest

from claude_sessions import claude_md as cm
from claude_sessions import config as _cfg

S, E = _cfg._MEMORY_START, _cfg._MEMORY_END
AS, AE = _cfg._AUTOGEN_START, _cfg._AUTOGEN_END


def _block(closing=b'\n', body='new body'):
    return f"{S}\n{body}\n{E}".encode() + closing


def _write(path, data):
    with open(path, 'wb') as f:
        f.write(data)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _refresh(tmp_path, data, section=None):
    _write(os.path.join(tmp_path, 'CLAUDE.md'), data)
    ok, _, _ = cm.upsert_block(str(tmp_path), S, E,
                               section if section is not None
                               else _block().decode())
    assert ok
    return _read(os.path.join(tmp_path, 'CLAUDE.md'))


def test_crlf_prefix_and_suffix_survive_a_refresh(tmp_path):
    old = (b"# P\r\n\r\nUSER\r\n\r\n" + S.encode() + b"\r\nold\r\n" + E.encode()
           + b"\r\n\r\nTAIL\r\n")
    out = _refresh(tmp_path, old)
    assert out == b"# P\r\n\r\nUSER\r\n\r\n" + _block(b"\r\n") + b"\r\nTAIL\r\n"


def test_mixed_newlines_survive_a_refresh(tmp_path):
    old = (b"# P\nLF line\r\nCRLF line\n\r\n" + S.encode() + b"\nold\n" + E.encode()
           + b"\n\ntail\r\n\n")
    out = _refresh(tmp_path, old)
    assert out == b"# P\nLF line\r\nCRLF line\n\r\n" + _block() + b"\ntail\r\n\n"


def test_prose_without_final_newline_after_block_survives(tmp_path):
    old = b"# P\r\nUSER\r\n" + S.encode() + b"\nold\n" + E.encode() + b"\nno final newline"
    out = _refresh(tmp_path, old)
    assert out == b"# P\r\nUSER\r\n" + _block() + b"no final newline"


def test_block_at_eof_without_terminator_keeps_prefix(tmp_path):
    old = b"# P\r\nUSER\r\n" + S.encode() + b"\nold\n" + E.encode()
    out = _refresh(tmp_path, old)
    assert out == b"# P\r\nUSER\r\n" + _block(closing=b"")


def test_append_keeps_original_bytes_including_trailing_blanks(tmp_path):
    old = b"# P\r\nUSER\r\n\n\n"
    out = _refresh(tmp_path, old)
    assert out.startswith(old)
    assert out[len(old):].endswith(_block())
    assert out[len(old):-len(_block())].strip(b"\r\n") == b""


def test_delete_leaves_exactly_the_bytes_outside_the_block(tmp_path):
    old = (b"# P\r\n\r\nUSER\r\n\r\n" + S.encode() + b"\nold\n" + E.encode()
           + b"\n\r\nTAIL\r\n")
    out = _refresh(tmp_path, old, section='')
    assert out == b"# P\r\n\r\nUSER\r\n\r\n" + b"\r\nTAIL\r\n"


def test_repeated_refresh_is_byte_identical(tmp_path):
    old = b"# P\r\n\r\nUSER\r\n\r\n" + S.encode() + b"\nold\n" + E.encode() + b"\r\nTAIL\r\n"
    first = _refresh(tmp_path, old)
    second = _refresh(tmp_path, first)
    assert second == first


def test_swap_block_removal_consumes_only_the_closing_terminator():
    text = f"A\r\n{AS}\r\nx\r\n{AE}\r\nB\r\n"
    assert cm._swap_block(text, AS, AE, '') == "A\r\nB\r\n"


def test_swap_block_append_keeps_original_tail():
    text = "A\n\n\n"
    out = cm._swap_block(text, AS, AE, f"{AS}\nb\n{AE}\n")
    assert out.startswith(text)


def test_protected_block_keeps_its_crlf():
    existing = f"# P\r\n\r\n{S}\r\nmem\r\n{E}\r\n"
    out = cm._preserve_block("# P\n\nnew prose\n", existing)
    assert f"{S}\r\nmem\r\n{E}\r\n" in out


def test_protected_block_keeps_its_own_closing_terminator():
    existing = f"# P\r\n{S}\r\nmem\r\n{E}\n"
    out = cm._preserve_block("# P\n\nnew prose\n", existing)
    assert out.endswith(f"{S}\r\nmem\r\n{E}\n")


def test_protected_block_at_eof_keeps_its_missing_terminator():
    existing = f"# P\r\n{S}\r\nmem\r\n{E}"
    out = cm._preserve_block("# P\n\nnew prose\n", existing)
    assert out.endswith(f"{S}\r\nmem\r\n{E}")


def test_backup_is_the_exact_original_bytes(tmp_path):
    original = b"# P\r\n\r\nUSER\r\n\r\n" + S.encode() + b"\r\nmem\r\n" + E.encode() + b"\r\n"
    md = os.path.join(tmp_path, 'CLAUDE.md')
    _write(md, original)
    assert cm.set_manual_prose(str(tmp_path), None, text='# P\n\nnew\n') == (True, '')
    assert _read(md + '.bak') == original


def test_undecodable_file_refresh_is_refused_and_untouched(tmp_path):
    original = b"# P\nUSER \xff\xfe\n"
    md = os.path.join(tmp_path, 'CLAUDE.md')
    _write(md, original)
    ok, _, _ = cm.upsert_block(str(tmp_path), S, E, _block().decode())
    assert ok is False
    assert _read(md) == original


def test_undecodable_file_manual_save_is_refused_and_untouched(tmp_path):
    original = b"# P\nUSER \xff\xfe\n" + S.encode() + b"\nmem\n" + E.encode() + b"\n"
    md = os.path.join(tmp_path, 'CLAUDE.md')
    _write(md, original)
    ok, err = cm.set_manual_prose(str(tmp_path), None, text='# P\n\nnew\n')
    assert ok is False
    assert _read(md) == original


def test_undecodable_file_prune_is_refused_and_untouched(tmp_path):
    original = b"# P\nUSER \xff\xfe\n" + AS.encode() + b"\nold\n" + AE.encode() + b"\n"
    md = os.path.join(tmp_path, 'CLAUDE.md')
    _write(md, original)
    assert cm.prune_claude_md(str(tmp_path), None) is None
    assert _read(md) == original


def test_scaffold_keeps_crlf_prose_before_appended_autogen(tmp_path):
    original = b"# P\r\n\r\nUSER\n\n\n"
    md = os.path.join(tmp_path, 'CLAUDE.md')
    _write(md, original)
    assert cm.scaffold_claude_md(str(tmp_path), None) is True
    assert _read(md).startswith(original)


@pytest.mark.parametrize('original', [b" \r\n\t\r\n", b" \t"])
def test_whitespace_only_file_keeps_its_bytes_on_append(tmp_path, original):
    out = _refresh(tmp_path, original)
    sep = b'\n' if original.endswith(b'\n') else b'\n\n'
    assert out == original + sep + _block()


def test_whitespace_only_block_append_in_swap_keeps_its_bytes():
    text = " \r\n\t\r\n"
    block = f"{AS}\nb\n{AE}\n"
    assert cm._swap_block(text, AS, AE, block) == text + "\n" + block


def test_swap_block_on_empty_text_is_the_block_alone():
    assert cm._swap_block('', AS, AE, f"{AS}\nb\n{AE}\n") == f"{AS}\nb\n{AE}\n"


def test_crlf_end_line_with_crlf_section_does_not_gain_a_cr(tmp_path):
    old = b"# P\r\n" + S.encode() + b"\r\nold\r\n" + E.encode() + b"\r\nTAIL\r\n"
    section = f"{S}\r\nnew\r\n{E}\r\n"
    out = _refresh(tmp_path, old, section=section)
    assert out == b"# P\r\n" + section.encode() + b"TAIL\r\n"
    assert b"\r\r" not in out
    assert _refresh(tmp_path, out, section=section) == out
