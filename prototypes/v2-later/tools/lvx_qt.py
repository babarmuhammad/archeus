"""LV2-X.2: does the desktop app render the refined E as Chrome does? Prototype tooling.
  py prototypes/v2-later/tools/lvx_qt.py
Loads the same screens in the shipped shell (PyQt6 QWebEngineView, as `archeus gui` does) and in Playwright's
Chromium at 1440x900, reads the same layout facts from both (element boxes, counts, page width and height,
the features the design leans on), and captures the Qt window as it is composed (DWM capture of the client
rect, the method PR-3 established; a headless Qt view does not compose). Writes results/lvx/qt/.
A Qt window opens on the desktop while it runs. Fails when a box moves by more than 2 px, a count differs,
a feature is missing in Qt, or the page scrolls sideways in either engine.
"""
import ctypes
import ctypes.wintypes as W
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'v2-u0', 'tools'))
from measure_qt import _foreground  # noqa: E402
from serve import serve, results  # noqa: E402

SCREENS = [('home', 'v=home'), ('home_x2', 'v=home&corpus=x2'), ('idle', 'v=home&s=idle'), ('primed', 'v=home&s=primed'),
           ('stopped', 'v=home&s=stopped'), ('offline', 'v=home&s=offline'), ('missions_x2', 'v=missions&corpus=x2'),
           ('m_running', 'v=mission&id=m-4c1e'), ('m_approval', 'v=mission&id=m-91d2'), ('m_record', 'v=mission&id=m-91d2&did=approve&drawer=approval'),
           ('m_blocked', 'v=mission&id=m-c3e9'), ('m_explain', 'v=mission&id=m-c3e9&ask=explain'), ('m_rejected', 'v=mission&id=m-a3f0'),
           ('project_x2', 'v=project&pid=p-inv&corpus=x2'), ('ideas', 'v=ideas'), ('ideas_new', 'v=ideas&compose=p-inv'),
           ('idea', 'v=idea&iid=ida-3e90'), ('control', 'v=control'), ('tell_done', 'v=home&tell=done'), ('noprojects', 'v=home&s=noprojects')]
SEL = ['.x-sys', '.x-nav', '.x-main', 'h1', '.x-grid', '.x-zone', '.x-row', '.x-tile', '.x-line-full', '.x-comp', '.x-ca .btn', '.x-two',
       '.x-term', '.x-drawer', '.x-modal', '.x-board', '.x-mi', '.x-ig', '.x-mono', '.estop', '.x-tell', '.x-band', '.x-kn', '.x-cgrid']
PROBE = r"""(() => {
  const r = (e) => { const b = e.getBoundingClientRect(); return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]; };
  const box = {};
  for (const s of %s) { const all = document.querySelectorAll(s); if (all.length) box[s] = { n: all.length, first: r(all[0]), last: r(all[all.length - 1]) }; }
  const feat = {
    colorMix: CSS.supports('color', 'color-mix(in srgb, red 50%%, blue)'), has: CSS.supports('selector(:has(a))'),
    is: CSS.supports('selector(:is(a))'), lineClamp: CSS.supports('-webkit-line-clamp', '2'), waapi: 'animate' in Element.prototype,
    getAnimations: 'getAnimations' in document, svgText: !!document.querySelector('.x-mono text'),
    displayFont: document.fonts.check('600 32px "Segoe UI Variable Display"'), textFont: document.fonts.check('13px "Segoe UI Variable Text"'),
    monoFont: document.fonts.check('12px "Cascadia Mono"'), reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
  };
  return JSON.stringify({ box, feat, w: document.documentElement.scrollWidth, iw: innerWidth, h: document.documentElement.scrollHeight,
    errors: (window.__errs || []).length });
})()""" % json.dumps(SEL)


def chromium(base):
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='dark')
        for name, q in SCREENS:
            pg = c.new_page()
            pg.goto(base + q + '&shot=1')
            pg.wait_for_timeout(300)
            out[name] = json.loads(pg.evaluate(PROBE))
            pg.close()
        b.close()
    return out


def qt(base, shots):
    from PIL import ImageGrab
    from PyQt6.QtCore import Qt, QTimer, QUrl
    from PyQt6.QtGui import QColor
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    U = ctypes.windll.user32
    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.page().setBackgroundColor(QColor('#0E1116'))
    view.resize(1440, 900)
    view.setWindowFlags(view.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    view.show()
    out = {}

    def grab(name):
        hwnd = int(view.window().winId())
        r = W.RECT(); U.GetClientRect(hwnd, ctypes.byref(r))
        p = W.POINT(0, 0); U.ClientToScreen(hwnd, ctypes.byref(p))
        ImageGrab.grab(bbox=(p.x, p.y, p.x + r.right, p.y + r.bottom), all_screens=True).save(os.path.join(shots, name + '.png'))

    def run(i):
        if i >= len(SCREENS):
            app.quit()
            return
        name, q = SCREENS[i]

        def got(txt):
            out[name] = json.loads(txt)
            grab(name)
            run(i + 1)

        def loaded(ok):
            view.loadFinished.disconnect(loaded)
            _foreground(view.window())
            QTimer.singleShot(900, lambda: view.page().runJavaScript(PROBE, got))
        view.loadFinished.connect(loaded)
        view.load(QUrl(base + q + '&shot=1'))

    QTimer.singleShot(100, lambda: run(0))
    app.exec()
    return out


def main():
    shots = results('lvx', 'qt', 'x')[:-2]
    os.makedirs(shots, exist_ok=True)
    base, srv = serve()
    base = base.replace('/lab/', '/lvx/') + 'index.html?d=e2&'
    cr = chromium(base)
    q = qt(base, shots)
    srv.shutdown()
    lines, bad = [], 0
    for name, _ in SCREENS:
        a, b, probs, worst = cr[name], q.get(name), [], 0
        if not b:
            probs.append('Qt did not answer')
        else:
            for s in sorted(set(a['box']) | set(b['box'])):
                x, y = a['box'].get(s), b['box'].get(s)
                if not x or not y or x['n'] != y['n']:
                    probs.append('%s count %s vs %s' % (s, x and x['n'], y and y['n']))
                    continue
                d = max(abs(i - j) for k in ('first', 'last') for i, j in zip(x[k], y[k]))
                worst = max(worst, d)
                if d > 2:
                    probs.append('%s moved %d px (%s vs %s)' % (s, d, x['first'], y['first']))
            missing = [k for k, v in a['feat'].items() if v and not b['feat'].get(k) and k != 'reducedMotion']
            if missing:
                probs.append('missing in Qt: %s' % missing)
            if b['w'] > b['iw'] or a['w'] > a['iw']:
                probs.append('sideways scroll (Chromium %d, Qt %d)' % (a['w'] - a['iw'], b['w'] - b['iw']))
            if abs(a['h'] - b['h']) > 2:
                probs.append('page height %d vs %d' % (a['h'], b['h']))
        bad += bool(probs)
        lines.append('%-12s worst %2d px  %s' % (name, worst, '; '.join(probs) or 'ok'))
    feats = {k: (cr['home']['feat'][k], q['home']['feat'][k]) for k in cr['home']['feat']} if q.get('home') else {}
    lines.append('features (Chromium, Qt): %s' % json.dumps(feats))
    lines.append('FAILURES: %s' % (bad or 'none'))
    open(os.path.join(shots, 'check.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    json.dump({'chromium': cr, 'qt': q}, open(os.path.join(shots, 'probe.json'), 'w', encoding='utf-8'), indent=1)
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
