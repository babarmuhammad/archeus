"""Native desktop shell for the archeus GUI — a PyQt6 window hosting the
local web app (like Claude Desktop: web UI in a native frame). PyQt6 is an
OPTIONAL dependency: gui.run_gui() only calls run_desktop() when the import
succeeds, falling back to an Edge app-mode window, then the default browser.
"""

import os
import sys
import threading


def _icon_path():
    """The app icon, or '' — one file, shipped with the package.

    There was a GUI-specific icon with the TUI's as a fallback, which is two
    marks to keep in step and no answer to "which one is the logo". It resolves
    in `config` now, because the Qt window is not the only consumer: the browser
    shells need the same file as a favicon and cannot import this module.
    """
    from .config import app_icon_path
    return app_icon_path()


#: fallback when nothing is saved or the saved name has gone — the 'default'
#: palette's own bg, which is what the old hardcoded value was.
_FALLBACK_BG = '#0d1117'


def _page_bg():
    """The active palette's `bg`, for the Qt page's backing surface.

    A world overrides the palette while worn, exactly as `applyTheme` does in
    the browser, so the two agree about what colour the page is.
    """
    try:
        from .config import load_settings
        from .themes import PALETTES, WORLDS
        s = load_settings()
        w = WORLDS.get((s.get('world') or '').strip())
        name = w['palette'] if w else (s.get('theme') or 'default').strip()
        return PALETTES.get(name, PALETTES['default'])['bg']
    except Exception:
        return _FALLBACK_BG


def run_desktop(on_ready=None):
    """Serve the GUI and show it in a native Qt window. Blocks until the
    window closes. Raises ImportError if PyQt6/WebEngine is unavailable —
    caller falls back.

    `on_ready(view, app)` is called once the page has loaded, and exists for
    ONE caller: tools/probe_qt.py, which measures the stage inside the real Qt
    shell because that is the only place the surface-tearing bug lives. It is a
    callback rather than a copy of this function in the tool because a
    hand-maintained copy of something the code already states drifts — and what
    would drift here is precisely the GPU and compositing setup the measurement
    is about."""
    # GPU compositing stays ON here — forcing --disable-gpu-compositing (the
    # old fix) routed the WHOLE page through the CPU compositor and made the
    # app sluggish. The flicker it was papering over had a specific DOM cause,
    # now fixed at the source in app.css:
    #   1. the full-screen job overlay used backdrop-filter: blur(), which
    #      makes QtWebEngine's GPU compositor read back + reblur the entire
    #      framebuffer every composite — with an animating spinner on top that
    #      thrashes the hardware surface swap and tears. Removed (solid dim).
    #   2. the spinner/pulse/shimmer keyframes now use steps() instead of a
    #      smooth 60fps tween, so animated nodes invalidate ~8-10x/sec.
    #   3. plan-execute no longer opens that blocking overlay at all — it runs
    #      inline + non-blocking (see app.js peJob*), so its long jobs never
    #      put an animated modal over the page.
    # If a flicker ever reappears on specific hardware, the escape hatch is to
    # set QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu-compositing (or --disable-gpu
    # for full software render) in the environment before launching — this
    # module no longer overrides a pre-set value.

    from PyQt6.QtWidgets import QApplication, QMainWindow
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtGui import QIcon, QDesktopServices, QColor
    from PyQt6.QtCore import QMetaObject, Qt, QUrl

    from . import gui
    from .gui import make_server

    srv = make_server()
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    # QtWebEngine's Chromium layer needs argv[0] (the program name) — an
    # empty list crashes it with STATUS_STACK_BUFFER_OVERRUN on load.
    app = QApplication(sys.argv[:1] or ['archeus'])
    app.setApplicationName('archeus')
    win = QMainWindow()
    win.setWindowTitle('archeus')
    ico = _icon_path()
    if ico:
        win.setWindowIcon(QIcon(ico))
    view = QWebEngineView()
    # QWebEngineView's page defaults to a white backing surface; every repaint
    # briefly shows that white through before Chromium composites the page over
    # it, reading as a flicker. Matching the page background removes the flash.
    #
    # Read from the palette, not hardcoded. The old comment here said "--bg is
    # always #0d1117 (GUI has no light theme)" — no longer true: there are four
    # light palettes (#fffcf0, #fafafa …) and six OLED ones at #050505, and on
    # any of them a hardcoded #0d1117 was the wrong-coloured flash rather than
    # the fix. It is also what shows through for the half second the GL canvas
    # is hidden on blur, which is one of the three causes of the background
    # flicker (see the `win-blur` block at the end of app.css).
    view.page().setBackgroundColor(QColor(_page_bg()))
    # window.open (graph tab) is silently dropped by QWebEngineView unless
    # new-window requests are handled — route them to the system browser
    view.page().newWindowRequested.connect(
        lambda req: QDesktopServices.openUrl(req.requestedUrl()))
    # ?k= — `/` is token-gated, because it is the response the token is written
    # into and an unauthenticated one hands it to any local socket peer.
    view.load(QUrl(f'http://127.0.0.1:{port}/?k={gui.TOKEN}'))
    win.setCentralWidget(view)
    win.resize(1280, 840)
    win.show()
    if on_ready is not None:
        view.loadFinished.connect(lambda ok: ok and on_ready(view, app))

    # POST /api/quit runs on a request thread, and Qt may only be touched from
    # the thread that owns the object — a QTimer created off-thread has no event
    # loop to fire it. A queued invocation is the one safe way across.
    def _quit():
        QMetaObject.invokeMethod(app, 'quit', Qt.ConnectionType.QueuedConnection)
        return True

    gui.QUIT_HOOK = _quit
    try:
        app.exec()
    finally:
        srv.shutdown()
        srv.server_close()
