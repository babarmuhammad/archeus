"""T-1449: the POSIX key decoder in claude_sessions/term.py (_decode_posix,
_decode_escape, _decode_utf8; source lines 92-141 at worktree 44aaf17f).

Only the branches test_platform.py does not pin are here, plus the modified
arrow (ESC [ 1 ; 5 C, Ctrl+Right): its parameters end at the final byte, so the
key after it is not swallowed.
"""

import pytest

from claude_sessions import term


class Keys:
    """Scripted bytes. A timed read past the end returns b'' (nothing followed the
    Escape); a blocking read past the end returns b'' too, so no test can hang."""

    def __init__(self, data):
        self.data = list(data)
        self.timeouts = 0

    def getch(self):
        return bytes([self.data.pop(0)]) if self.data else b''

    def timeout(self, _secs):
        self.timeouts += 1
        return bytes([self.data.pop(0)]) if self.data else b''

    def install(self, monkeypatch):
        monkeypatch.setattr(term, 'BACKEND', 'posix')
        monkeypatch.setattr(term, 'getch', self.getch)
        monkeypatch.setattr(term, '_getch_timeout', self.timeout)


def test_modified_arrow_is_not_dropped_or_consuming(monkeypatch):
    keys = Keys(b'\x1b[1;5Cx')
    keys.install(monkeypatch)
    term.key_event()
    assert term.key_event() == ('char', 'x')


def test_delete_maps_and_insert_is_ignored(monkeypatch):
    keys = Keys(b'\x1b[3~x')
    keys.install(monkeypatch)
    assert term.key_event() == ('del',)
    assert term.key_event() == ('char', 'x')

    keys = Keys(b'\x1b[2~x')
    keys.install(monkeypatch)
    assert term.key_event() is None
    assert term.key_event() == ('char', 'x')


def test_esc_then_letter_consumes_the_letter(monkeypatch):
    keys = Keys(b'\x1bx')
    keys.install(monkeypatch)
    assert term.key_event() == ('esc',)
    assert keys.data == []


def test_double_escape_yields_one_event(monkeypatch):
    keys = Keys(b'\x1b\x1bx')
    keys.install(monkeypatch)
    assert term.key_event() == ('esc',)
    assert term.key_event() == ('char', 'x')


def test_ss3_arrows_and_unknown_final(monkeypatch):
    keys = Keys(b'\x1bOBx')
    keys.install(monkeypatch)
    assert term.key_event() == ('down',)
    assert term.key_event() == ('char', 'x')

    keys = Keys(b'\x1bOPx')
    keys.install(monkeypatch)
    assert term.key_event() is None
    assert term.key_event() == ('char', 'x')


def test_empty_read_and_nul_are_ignored(monkeypatch):
    for data in (b'', b'\x00'):
        Keys(data).install(monkeypatch)
        assert term.key_event() is None


def test_stray_continuation_byte_is_ignored(monkeypatch):
    for byte in (b'\x80', b'\xbf'):
        Keys(byte).install(monkeypatch)
        assert term.key_event() is None


def test_utf8_two_byte_char_and_truncated_sequence(monkeypatch):
    Keys('é'.encode('utf-8')).install(monkeypatch)
    assert term.key_event() == ('char', 'é')

    Keys(b'\xc3').install(monkeypatch)
    assert term.key_event() is None


def test_bad_utf8_consumes_continuation_bytes(monkeypatch):
    """Boundary: a four-byte lead reads three continuation bytes whatever they are,
    so the two ASCII keys typed after a broken sequence are consumed with it."""
    keys = Keys(b'\xf0\x9fABC')
    keys.install(monkeypatch)
    assert term.key_event() is None
    assert term.key_event() == ('char', 'C')


def test_escape_reads_only_as_far_as_needed(monkeypatch):
    keys = Keys(b'\x1b')
    keys.install(monkeypatch)
    assert term.key_event() == ('esc',)
    assert keys.timeouts == 1

    keys = Keys(b'\x1b[A')
    keys.install(monkeypatch)
    assert term.key_event() == ('up',)
    assert keys.timeouts == 2
