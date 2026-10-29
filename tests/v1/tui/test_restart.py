"""T07 through the whole TUI (p17-design-gate §7): Core restarts under a running
TUI. It shows the reconnect in words, never commands while it lasts, re-reads
everything once the stream is back, and shows nothing stale as current."""

import time

from archeus.cli.tui import app as A, client as C
from archeus.cli.tui.view import Style

from .conftest import mission, plain, settled


def _until(app, cond, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.pump()
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError('never; connection %r' % app.conn)


def test_T07_a_core_restart_is_shown_then_everything_is_read_again(core):
    mid = mission(core, 'Survives a restart')
    settled(core, mid, 'COMPLETED')
    app = A.App(C.Core(core.port, core.token), Style(), size=lambda: (100, 30))
    app.stream.start()
    try:
        _until(app, lambda: app.conn['conn'] == 'live')
        app.go({'view': 'work'})
        assert 'Survives a restart' in plain(app)
        gen = app.conn['gen']
        core.restart()
        app.stream.core = app.core = C.Core(core.port, core.token)
        _until(app, lambda: app.conn['conn'] in ('reconnecting', 'resynced'))
        if app.conn['conn'] == 'reconnecting':
            shown = plain(app)
            assert 'Reconnecting' in shown and 'Not connected' not in shown
            assert app.why_not({'scope': 'observe', 'disabled': None}) == \
                'Not connected — nothing is sent while reconnecting.'
        _until(app, lambda: app.conn['conn'] in ('resynced', 'live') and app.conn['gen'] > gen)
        # every read held before the restart is from an older generation, so the
        # next frame reads it again rather than showing it as current
        assert all(e['gen'] < app.conn['gen'] for e in app.cache.values())
        shown = plain(app)
        assert all(e['gen'] == app.conn['gen'] for p, e in app.cache.items()
                   if p in ('/v1/missions', '/v1/attention'))
        assert 'Survives a restart' in shown
        _until(app, lambda: app.conn['conn'] == 'live', timeout=10)
        assert 'Back — everything on screen was read again.' not in plain(app)
    finally:
        app.stream.stop()
