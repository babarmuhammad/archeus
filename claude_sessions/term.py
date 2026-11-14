"""Raw keyboard input, on both families of terminal.

`import msvcrt` at the top of `ui.py` was the only one in the codebase, and
every screen funnels through `ui.wait_event()` / `poll_event()`, so the whole
POSIX port of the TUI is this one seam. `render.py` needs nothing: it already
emits plain ANSI.

The event vocabulary is unchanged — ('up',) ('down',) ('left',) ('right',)
('enter',) ('esc',) ('back',) ('del',) ('tab',) ('char', c) — because that is
what fifteen screens already match on.

`BACKEND` is a module attribute rather than a constant derived from os.name so
the test harness can drive the Windows decoder from a POSIX runner: its key
scripts are written in Windows scancodes, and the point of running the suite on
Linux is to exercise the screens, not to re-script every test.
"""

import os
import sys

WINDOWS = os.name == 'nt'
BACKEND = 'windows' if WINDOWS else 'posix'

if WINDOWS:
    import msvcrt
else:
    msvcrt = None
    import select
    import termios
    import tty

__all__ = ['kbhit', 'getch', 'key_event', 'enable_vt', 'clear', 'BACKEND']


# ── raw byte access ──────────────────────────────────────────

def kbhit():
    if msvcrt is not None:
        return msvcrt.kbhit()
    try:
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except Exception:
        return False


def getch():
    """One raw byte, as bytes."""
    if msvcrt is not None:
        return msvcrt.getch()
    return os.read(sys.stdin.fileno(), 1)


def _getch_timeout(seconds):
    """One byte if it arrives within *seconds*, else b''. POSIX only — this is
    what separates a bare Escape keypress from the start of an arrow key."""
    try:
        if not select.select([sys.stdin], [], [], seconds)[0]:
            return b''
    except Exception:
        return b''
    return os.read(sys.stdin.fileno(), 1)


# ── decoding ─────────────────────────────────────────────────

def key_event():
    """The next key as an event tuple, or None for one this UI ignores."""
    return _decode_windows() if BACKEND == 'windows' else _decode_posix()


def _decode_windows():
    key = ord(getch())
    if key in (0, 224):
        k2 = ord(getch())
        return {72: ('up',), 80: ('down',), 75: ('left',), 77: ('right',),
                83: ('del',)}.get(k2, None)
    if key == 13: return ('enter',)
    if key == 27: return ('esc',)
    if key == 8:  return ('back',)
    if key == 9:  return ('tab',)
    if 32 <= key <= 126 or key > 127:
        try:
            return ('char', chr(key))
        except ValueError:
            return None
    return None


_CSI = {'A': ('up',), 'B': ('down',), 'C': ('right',), 'D': ('left',)}


def _decode_posix():
    b = getch()
    if not b:
        return None
    key = b[0]
    if key == 0x1b:
        return _decode_escape()
    if key in (13, 10): return ('enter',)
    if key in (8, 127):  return ('back',)      # DEL is the usual Backspace here
    if key == 9:        return ('tab',)
    if 32 <= key <= 126:
        return ('char', chr(key))
    if key >= 0xc0:
        return _decode_utf8(key)
    return None


def _decode_escape():
    """ESC alone, or the start of a CSI/SS3 sequence. The distinction is
    timing: a real Escape has nothing behind it."""
    nxt = _getch_timeout(0.03)
    if nxt not in (b'[', b'O'):
        return ('esc',)
    final = _getch_timeout(0.03)
    if not final:
        return ('esc',)
    ch = final.decode('latin-1')
    if ch in _CSI:
        return _CSI[ch]
    if ch.isdigit():                      # ESC [ <params> <final>  — Del is ESC [ 3 ~
        num = ch
        while True:
            more = _getch_timeout(0.03)
            if not more or 0x40 <= more[0] <= 0x7e:   # any final byte ends it, not only '~'
                break
            num += more.decode('latin-1')
        return ('del',) if num == '3' and more == b'~' else None
    return None


def _decode_utf8(first):
    """Rebuild one non-ASCII character from its continuation bytes."""
    need = 1 if first < 0xe0 else (2 if first < 0xf0 else 3)
    buf = bytes([first])
    for _ in range(need):
        nxt = _getch_timeout(0.03)
        if not nxt:
            break
        buf += nxt
    try:
        return ('char', buf.decode('utf-8'))
    except UnicodeDecodeError:
        return None


# ── terminal mode ────────────────────────────────────────────

_saved_tty = None


def enable_vt():
    """Turn on ANSI escape handling, and put the terminal where single
    keypresses arrive without Enter. True when ANSI can be used."""
    global _saved_tty
    if WINDOWS:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                if kernel32.SetConsoleMode(handle, mode.value | 0x0004):
                    return True
        except Exception:
            pass
        return False
    # POSIX: cbreak, not full raw — Ctrl-C must still reach the process, and
    # the alternate-screen restore in render.py runs from atexit.
    try:
        fd = sys.stdin.fileno()
        _saved_tty = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        import atexit
        atexit.register(restore)
    except Exception:
        _saved_tty = None
    return True


def restore():
    global _saved_tty
    if _saved_tty is not None and not WINDOWS:
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _saved_tty)
        except Exception:
            pass
        _saved_tty = None


def clear():
    """Fallback screen clear for a console with no ANSI at all. Only an old
    Windows conhost lands here; every POSIX terminal takes the escape."""
    if os.name == 'nt':
        os.system('cls')
    else:
        sys.stdout.write('\x1b[2J\x1b[H')
        sys.stdout.flush()
