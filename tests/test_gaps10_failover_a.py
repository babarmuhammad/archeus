"""T-1382: branch gaps in claude_sessions/failover.py lines 119-215.

Covers candidates, enabled, port_of and serve_cli. Every seam is faked: no
socket, thread, subprocess or lock file, and ctypes.windll is a recording fake
so the console-title call never reaches Win32.
"""
import ctypes

import pytest

from claude_sessions import failover as fo

BASE = fo._c.PROFILE_PORT_BASE


class _Daemon:
    def __init__(self):
        self.locks = []
        self.clears = 0

    def write_lock(self, port):
        self.locks.append(port)

    def clear_lock(self):
        self.clears += 1


class _Srv:
    def __init__(self, raises=None):
        self._raises = raises

    def serve_forever(self):
        if self._raises is not None:
            raise self._raises


class _Kernel:
    def __init__(self):
        self.titles = []

    def SetConsoleTitleW(self, title):
        self.titles.append(title)


class _Windll:
    def __init__(self):
        self.kernel32 = _Kernel()


def _wire(monkeypatch, *, prof=None, active=None, server=None, make_raises=None):
    daemon, lines, made = _Daemon(), [], []

    def make(port):
        made.append(port)
        if make_raises is not None:
            raise make_raises
        return server

    monkeypatch.setattr(fo, '_emit', lines.append)
    monkeypatch.setattr(fo, '_daemon', lambda p: daemon)
    monkeypatch.setattr(fo, 'make_server', make)
    monkeypatch.setattr(fo._c, 'provider_profile', lambda pid: prof)
    monkeypatch.setattr(fo._c, 'active_provider', lambda: active)
    monkeypatch.setattr(fo._c, 'provider_upstream', lambda p: 'https://upstream.test')
    monkeypatch.setattr(ctypes, 'windll', _Windll(), raising=False)
    return daemon, lines, made


def _prof(models=('m1',), pid='p1'):
    return {'id': pid, 'name': 'Prof', 'failover_models': list(models)}


def test_serve_cli_unknown_profile_binds_nothing(monkeypatch):
    """Branch: serve_cli `if not prof` refusal. The active profile is set, so a
    fallback would have bound; the refusal must bind and lock nothing. Caught by:
    replacing the refusal with `prof = active_provider()`."""
    daemon, lines, made = _wire(monkeypatch, prof=None,
                                active=_prof(pid='active'), server=_Srv())
    assert fo.serve_cli(8123, 'nope') == 1
    assert made == [] and daemon.locks == []
    assert any('refusing to start' in ln for ln in lines)


def test_serve_cli_no_pid_no_active_refuses(monkeypatch):
    """Branch: serve_cli with pid '' takes the active profile; none set gives the
    '(active)' refusal, returns 1 and binds nothing. Caught by: skipping the
    `if not prof` check on the active path."""
    daemon, lines, made = _wire(monkeypatch, prof=None, active=None, server=_Srv())
    assert fo.serve_cli(8123, '') == 1
    assert made == [] and daemon.locks == []
    assert any("'(active)'" in ln for ln in lines)


def test_serve_cli_bind_failure_writes_no_lock(monkeypatch):
    """Branch: serve_cli make_server raising. Returns 1 with the port in the message
    and never writes the lock. Caught by: moving write_lock above the try."""
    daemon, lines, _made = _wire(monkeypatch, prof=_prof(), make_raises=OSError('denied'))
    assert fo.serve_cli(8123, 'p1') == 1
    assert daemon.locks == [], 'a lock was written for a port that never bound'
    assert any('cannot bind port 8123' in ln for ln in lines)


def test_serve_cli_clears_lock_on_crash(monkeypatch):
    """Branch: serve_cli finally clears the lock when serve_forever raises an error
    other than KeyboardInterrupt, and the error propagates. Caught by: a bare
    `except Exception` that swallows it, or clear_lock moved out of finally."""
    daemon, _lines, _made = _wire(monkeypatch, prof=_prof(),
                                  server=_Srv(raises=RuntimeError('boom')))
    with pytest.raises(RuntimeError, match='boom'):
        fo.serve_cli(8123, 'p1')
    assert daemon.locks == [8123]
    assert daemon.clears == 1


def test_serve_cli_keyboard_interrupt_returns_zero(monkeypatch):
    """Branch: serve_cli `except KeyboardInterrupt: pass` returns 0 and still clears
    the lock. Caught by: letting the interrupt escape, or skipping clear_lock."""
    daemon, _lines, _made = _wire(monkeypatch, prof=_prof(),
                                  server=_Srv(raises=KeyboardInterrupt()))
    assert fo.serve_cli(8123, 'p1') == 0
    assert daemon.locks == [8123]
    assert daemon.clears == 1


def test_ensure_running_no_profile_skips_daemon(monkeypatch):
    """Branch: ensure_running `if not prof` returns before the daemon is built. The
    fake _daemon fails the test if it is ever called. Caught by: removing the guard."""
    monkeypatch.setattr(fo, '_daemon', lambda p: pytest.fail('daemon built without a profile'))
    assert fo.ensure_running(None) == (False, 'no provider profile')


def test_enabled_whitespace_only_is_disabled():
    """Branch: enabled() strips each entry. A list of whitespace or empty entries is
    disabled; one real entry enables it. Caught by: testing truthiness without strip."""
    assert fo.enabled({'failover_models': ['  ', '', None]}) is False
    assert fo.enabled({'failover_models': ['  ', 'm1']}) is True
    assert fo.enabled(None) is False


def test_candidates_strip_dedupe_order():
    """Branch: candidates strips, drops empty and None, dedupes after strip, keeps
    the primary first and tolerates a missing profile. Caught by: deduping before
    stripping (' m1 ' would survive next to 'm1')."""
    assert fo.candidates(' m1 ', {'failover_models': ['m2', 'm1', '', None, ' m2 ', 'm3']}) \
        == ['m1', 'm2', 'm3']
    assert fo.candidates('x', None) == ['x']
    assert fo.candidates(None, None) == []


def test_port_of_fallbacks():
    """Branch: port_of falls back to PROFILE_PORT_BASE for 0, '', None or no port,
    and int-converts a numeric string. Caught by: `or` replaced with a None-only
    check (0 would then be kept)."""
    assert fo.port_of({'port': 0}) == BASE
    assert fo.port_of({'port': ''}) == BASE
    assert fo.port_of({'port': None}) == BASE
    assert fo.port_of({}) == BASE
    assert fo.port_of(None) == BASE
    got = fo.port_of({'port': '8123'})
    assert got == 8123 and isinstance(got, int)


def test_serve_cli_banner_candidates(monkeypatch):
    """Branch: serve_cli banner lists '(none)' when no failover model is enabled,
    and skips whitespace entries otherwise. Caught by: joining the raw list
    (the banner would show an empty candidate)."""
    _d, lines, _m = _wire(monkeypatch, prof=_prof(models=['  ']), server=_Srv())
    assert fo.serve_cli(8123, 'p1') == 0
    assert 'candidates: (none)' in lines

    _d, lines, _m = _wire(monkeypatch, prof=_prof(models=['  ', 'm1']), server=_Srv())
    assert fo.serve_cli(8123, 'p1') == 0
    assert 'candidates: m1' in lines
