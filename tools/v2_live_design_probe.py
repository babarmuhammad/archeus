"""V2 Live design kit probe: renders clients/v2-live-design/gallery.html?specimen in every theme at 390/768/1280 (+ real forced-colors) and fails on:
  error     console error or page error, failed request
  target    interactive element under 44 px (48 px for primary buttons and nav at 1024 px or wider)
  contrast  text under 4.5:1 against its effective background (computed colours)
  hscroll   the page scrolls sideways
  clipped / overlap / covered   same meaning as tools/v2_live_layout_probe.py (its measuring script is reused)
  backdrop  any element with backdrop-filter, or the string in a stylesheet
  loops     more than one kind of infinite animation, or any other than core-breath; any animation under Quiet
  focus     a control that shows no outline or box-shadow when focused by keyboard
Run through the shared lock from the worktree root:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_design_probe.py [--themes dark,light] [--viewports 390x844] [--shots dir] [--css-dir dir]
Serves the kit from its own http.server on a free port and stops it. Exit 1 on any defect.
"""
import argparse
import importlib.util
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location('layout_probe', os.path.join(ROOT, 'tools', 'v2_live_layout_probe.py'))
_lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lp)
MEASURE = (_lp.MEASURE.replace(".btn.primary, .btn.decide, .nav-item, .send", ".ds-btn:not(.quiet), .ds-rail a")
           .replace("a[href], button, input, select, textarea, summary,", "a[href], button, input:not([type=checkbox]):not([type=radio]), label:has(input[type=checkbox]), select, textarea, summary,")
           .replace('[tabindex]:not([tabindex="-1"])', '[tabindex]:not([tabindex="-1"]):not([role=tabpanel])'))

THEMES = ['dark', 'light', 'dark-hc', 'light-hc', 'system', 'forced']
VIEWPORTS = ['390x844', '768x1024', '1280x900']

EXTRA = r"""
() => {
  const out = [];
  for (const el of document.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if ((cs.backdropFilter && cs.backdropFilter !== 'none') || (cs.webkitBackdropFilter && cs.webkitBackdropFilter !== 'none')) out.push({ kind: 'backdrop', msg: el.tagName.toLowerCase() + '.' + el.className });
  }
  const loops = document.getAnimations().filter((a) => a.effect.getComputedTiming().iterations === Infinity).map((a) => a.animationName || a.constructor.name);
  const kinds = [...new Set(loops)];
  if (kinds.length > 1 || kinds.some((k) => k !== 'core-breath')) out.push({ kind: 'loops', msg: 'infinite animations: ' + kinds.join(',') });
  const ctl = [...document.querySelectorAll('a[href], button, input, select, textarea, summary, [role=tab], [tabindex]:not([tabindex="-1"])')].filter((e) => !e.disabled && e.checkVisibility({ checkVisibilityCSS: true }) && e.getBoundingClientRect().width > 1);
  for (const e of ctl) {
    e.focus({ focusVisible: true });
    const cs = getComputedStyle(e);
    let ring = false;
    for (let a = e; a && !ring; a = a.parentElement) { const c = getComputedStyle(a); ring = (c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) >= 2) || (a === e && c.boxShadow !== 'none'); if (a.matches(':focus-within') === false) break; }
    if (!ring) out.push({ kind: 'focus', msg: e.tagName.toLowerCase() + '.' + e.className + ' outline ' + cs.outlineStyle + ' ' + cs.outlineWidth });
    e.blur();
  }
  return out;
}
"""

# Force every core live under full motion: the only infinite loop allowed is core-breath; Quiet must run nothing.
LIVE = "document.querySelectorAll('.ds-core').forEach((c) => { c.dataset.live = 'true'; c.dataset.core = 'breath'; }); document.getAnimations().length"


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--themes', default=','.join(THEMES))
    ap.add_argument('--viewports', default=','.join(VIEWPORTS))
    ap.add_argument('--shots', default='')
    ap.add_argument('--css-dir', default=os.path.join(ROOT, 'clients', 'v2-live-design'))
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()
    port = free_port()
    srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', a.css_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    found = []
    pages = 0
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/gallery.html' % port, timeout=1).read(10)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise SystemExit('server did not start')
        for name in os.listdir(a.css_dir):
            if name.endswith('.css') and re.search(r'backdrop-filter', open(os.path.join(a.css_dir, name), encoding='utf-8-sig').read()):
                found.append(('css', name, 'backdrop', 'backdrop-filter in stylesheet'))
        with sync_playwright() as p:
            br = p.chromium.launch()
            runs = [(t, vp, 'full', False) for t in a.themes.split(',') for vp in a.viewports.split(',')]
            runs += [('dark', vp, 'reduced', False) for vp in a.viewports.split(',')]
            runs += [('light', '390x844', 'reduced', False), ('system', '1280x900', 'full', True)]
            for theme, vp, motion, forced in runs:
                w, h = [int(x) for x in vp.split('x')]
                ctx = br.new_context(viewport={'width': w, 'height': h}, forced_colors='active' if forced else 'none',
                                     reduced_motion='reduce' if motion == 'reduced' else 'no-preference')
                pg = ctx.new_page()
                pg.bring_to_front()
                errs = []
                pg.on('pageerror', lambda e: errs.append(str(e)))
                pg.on('console', lambda m: errs.append(m.text) if m.type in ('error', 'warning') else None)
                pg.on('requestfailed', lambda r: errs.append('request failed ' + r.url))
                pg.on('response', lambda r: errs.append('HTTP %d %s' % (r.status, r.url)) if r.status >= 400 else None)
                pg.goto('http://127.0.0.1:%d/gallery.html?specimen=1&theme=%s&motion=%s' % (port, theme, motion), wait_until='load')
                pg.evaluate('document.fonts.ready.then(() => true)')
                pg.wait_for_timeout(300)
                tag = '%s%s %s %s' % (theme, '+forced-colors' if forced else '', motion, vp)
                res = pg.evaluate(MEASURE, {'layer': None, 'desktop': w >= 1024})
                res += pg.evaluate(EXTRA)
                n = pg.evaluate(LIVE)
                loops = pg.evaluate("document.getAnimations().filter((x) => x.effect.getComputedTiming().iterations === Infinity).map((x) => x.animationName)")
                if motion == 'reduced' and n:
                    res.append({'kind': 'loops', 'msg': 'Quiet still runs %d animations' % n})
                if motion == 'full' and any(x != 'core-breath' for x in loops):
                    res.append({'kind': 'loops', 'msg': 'live core runs %r' % loops})
                res += [{'kind': 'error', 'msg': e} for e in errs]
                if a.shots:
                    os.makedirs(a.shots, exist_ok=True)
                    pg.screenshot(path=os.path.join(a.shots, '%s_%s_%s.png' % (theme + ('-fc' if forced else ''), motion, vp)), full_page=True)
                for r in res:
                    if r['kind'] != 'stat':
                        found.append((tag, '', r['kind'], r['msg']))
                pages += 1
                ctx.close()
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
    kinds = {}
    for _, _, k, _ in found:
        kinds[k] = kinds.get(k, 0) + 1
    print('Pages probed: %d.  Defects per kind: %s' % (pages, ', '.join('%s %d' % kv for kv in sorted(kinds.items())) or 'none'))
    seen = {}
    for tag, _, k, m in found:
        key = (k, m)
        seen.setdefault(key, []).append(tag)
    limit = None if a.verbose else 40
    for (k, m), tags in list(seen.items())[:limit]:
        print('  %-9s %s   [%s%s]' % (k, m, tags[0], ' +%d more' % (len(tags) - 1) if len(tags) > 1 else ''))
    print('TOTAL DEFECTS: %d' % len(found))
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
