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


def run_v1(shell, on_ready=None):
    """`archeus gui` (p19-design-gate B8): Archeus V1's app in this window, with
    a tray. *shell* is an `archeus.cli.gui.Shell`, which owns every decision —
    the launch address, the shell's credential, the tray's actions, the profile
    directory, the colours; this function only draws them. Returns the exit
    code. `on_ready(view, app)` as in `run_desktop`.

    - The page lives in a NAMED, persistent QWebEngineProfile under
      `<ARCHEUS_HOME>/QtWebEngine/` (ADR-0044 T5): its storage, so the
      appearance choice and B7's snapshot, survives a restart. The page's
      device token does not: the page holds it in memory only (T-096), so a
      reload is answered with a fresh launch address. The default profile
      `run_desktop` uses is kept apart: the legacy GUI is unchanged.
    - Before the page paints, the window shows the OS scheme's token
      background (ADR-0044 §4), never a fixed dark.
    - Closing the window hides it to the tray; Quit in the tray quits. Core is
      not stopped: it outlives the shell (target-architecture §4).
    - The tray's Emergency stop asks first, in a native box whose default is
      Cancel; only its own button reaches `shell.estop`.
    - The tray icon carries the attention colour only while Attention's count
      is non-zero, read when the menu opens and when the window hides to the
      tray.
    - While the window is hidden, and only then, the tray reads Core's events
      every `shell.NOTICE_EVERY_S` seconds and says an approval request or an
      e-stop in a notification, by kind only (p21-design-gate D1). Showing the
      window stops it.
    - GPU compositing stays on, as in `run_desktop`.
    """
    from PyQt6.QtCore import Qt, QTimer, QUrl
    from PyQt6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPixmap
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QMessageBox, QSystemTrayIcon

    app = QApplication(sys.argv[:1] or ['archeus'])
    app.setApplicationName('archeus')
    app.setQuitOnLastWindowClosed(False)
    dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark

    store = shell.profile_dir()
    profile = QWebEngineProfile('archeus', app)
    profile.setPersistentStoragePath(store)
    profile.setCachePath(os.path.join(store, 'cache'))

    ico = _icon_path()
    plain = QIcon(ico) if ico else QIcon()

    def with_dot():
        px = plain.pixmap(32, 32) if ico else QPixmap(32, 32)
        if not ico:
            px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(shell.attention_colour(dark)))
        p.drawEllipse(18, 18, 13, 13)
        p.end()
        return QIcon(px)

    alert = with_dot()
    tray = QSystemTrayIcon(plain, app)
    tray.setToolTip('Archeus')

    def refresh():
        n = shell.attention()
        tray.setIcon(alert if n else plain)
        tray.setToolTip('Archeus — %d need%s you' % (n, '' if n != 1 else 's') if n
                        else 'Archeus')

    quitting = []

    def quit_():
        quitting.append(True)            # Qt's quit closes the windows first
        app.quit()

    class Window(QMainWindow):
        def closeEvent(self, ev):        # hide to the tray; Quit is the tray's
            if quitting:
                return ev.accept()
            ev.ignore()
            self.hide()
            refresh()
            heard[0] = shell.notices(None)[0]     # from now: nothing older is said
            watch.start()

    win = Window()
    win.setWindowTitle('Archeus')
    win.setWindowIcon(plain)
    class Page(QWebEnginePage):
        reloads = 0

        def acceptNavigationRequest(self, url, kind, main):
            if not (main and kind == QWebEnginePage.NavigationType.NavigationTypeReload):
                return super().acceptNavigationRequest(url, kind, main)
            fresh = shell.page_url()
            if fresh is None:        # Core is down: a plain reload shows B7's snapshot
                return True
            # a query that changes each time: a fragment-only change is not a load
            Page.reloads += 1
            u = QUrl(fresh)
            u.setQuery('r=%d' % Page.reloads)
            QTimer.singleShot(0, lambda: self.load(u))
            return False

    view = QWebEngineView()
    page = Page(profile, view)
    page.setBackgroundColor(QColor(shell.preload_bg(dark)))
    page.newWindowRequested.connect(lambda req: QDesktopServices.openUrl(req.requestedUrl()))
    view.setPage(page)
    url = shell.page_url()
    if url is None:
        return 2
    view.load(QUrl(url))
    win.setCentralWidget(view)
    win.resize(1280, 840)

    def show():
        watch.stop()
        win.showNormal()
        win.raise_()
        win.activateWindow()

    def say(text):
        tray.showMessage('Archeus', text)

    heard = [None]

    def notify():
        heard[0], said = shell.notices(heard[0])
        for text in said:
            say(text)
        if said:
            refresh()

    watch = QTimer(win)
    watch.setInterval(shell.NOTICE_EVERY_S * 1000)
    watch.timeout.connect(notify)

    def estop():
        # destructive, so it asks first, Cancel the default (rulebook §6 O-1, §17)
        box = QMessageBox(QMessageBox.Icon.Warning, 'Emergency stop', shell.estop_confirm)
        stop = box.addButton('Emergency stop', QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(box.addButton(QMessageBox.StandardButton.Cancel))
        box.exec()
        if box.clickedButton() is stop:
            say(shell.estop()[1])

    menu = QMenu()
    for label, act in (('Open', show), ('Pause all', lambda: say(shell.pause_all())),
                       ('Emergency stop', estop),
                       ('Quit', quit_)):
        a = QAction(label, menu)
        a.triggered.connect(act)
        menu.addAction(a)
    menu.aboutToShow.connect(refresh)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda why: why == QSystemTrayIcon.ActivationReason.Trigger and show())
    tray.show()
    win.show()
    if on_ready is not None:
        view.loadFinished.connect(lambda ok: ok and on_ready(view, app))
    try:
        return app.exec()
    finally:
        # the page must go before its profile, or the profile is never flushed
        view.setPage(None)
        page.deleteLater()
        del page
