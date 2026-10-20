"""LE-5 filmstrips: each middle-band primitive frozen at 0, 25, 50, 75 and 100 % of its own
duration (WAAPI animations paused and seeked; nothing timed by the wall clock), plus its reduced
form at rest. Prototype tooling.   py filmstrip.py
"""
from PIL import Image, ImageDraw

from serve import results, serve
from playwright.sync_api import sync_playwright

T = [0, 0.25, 0.5, 0.75, 1.0]
# name: (trigger JS returning nothing, clip selector, viewport)
P = {
    'disclose': ("MID.disclose(document.querySelector('#missions .row'), true)", '#missions', (1100, 900)),
    'reorder': ("(() => { const h = document.querySelector('#missions'); MID._lastReorder = -1e9; MID.reorder(h, () => h.querySelector('[data-group=\"g3\"]').after(h.querySelector('.row'))); })()", '#missions', (1100, 900)),
    'count': ("MID.count(document.querySelector('#cnt'), 7)", '#cnt', (1100, 900)),
    'confirm': ("(() => { const r = document.querySelectorAll('#decide .row'); MID.confirm(r[0], 'Approved 14:02', r[1].querySelector('[data-verb]')); })()", '#decide', (1100, 900)),
    'reveal': ("document.querySelector('#menu').showPopover()", '#toolbar', (1100, 900)),
    'push': ("MID.push(document.querySelector('#page'))", 'body', (390, 844)),
    'release': ("(() => { const s = document.querySelector('#strip'); MID.release(s, 0, -496, -1.6); })()", 'body', (390, 844)),
}


def main():
    base, srv = serve()
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, (js, sel, (w, h)) in P.items():
            frames = []
            for mode in ('', '&motion=reduced'):
                c = b.new_context(viewport={'width': w, 'height': h}, device_scale_factor=1)
                pg = c.new_page()
                pg.goto(base + 'motion.html?clean=1' + mode)
                pg.wait_for_timeout(300)
                if name in ('disclose', 'reorder', 'confirm'):
                    pg.evaluate("document.querySelector('%s').scrollIntoView()" % sel)
                pg.evaluate("() => { %s; for (const a of document.getAnimations()) a.pause(); }" % js)
                ts = T if not mode else [1.0]
                for t in ts:
                    pg.evaluate('''t => { for (const a of document.getAnimations()) { const d = a.effect.getComputedTiming().endTime || 0; a.currentTime = d * t; } }''', t)
                    pg.wait_for_timeout(30)
                    el = pg.locator(sel).first
                    box = el.bounding_box() if sel != 'body' else {'x': 0, 'y': 0, 'width': w, 'height': h}
                    clip = {'x': max(0, box['x'] - 8), 'y': max(0, box['y'] - 8), 'width': min(w, box['width'] + 16), 'height': min(h, max(60, box['height']) + 16)}
                    path = results('le5', 'film', '%s_%s%d.png' % (name, 'r' if mode else '', int(t * 100)))
                    pg.screenshot(path=path, clip=clip)
                    frames.append((('reduced ' if mode else '') + '%d%%' % int(t * 100), path))
                c.close()
            ims = [Image.open(f) for _, f in frames]
            W = sum(i.width for i in ims) + 12 * (len(ims) + 1)
            H = max(i.height for i in ims) + 40
            sheet = Image.new('RGB', (W, H), (14, 17, 22))
            d = ImageDraw.Draw(sheet)
            x = 12
            for (lbl, _), im in zip(frames, ims):
                sheet.paste(im, (x, 30))
                d.text((x, 8), '%s %s' % (name, lbl), fill=(170, 179, 192))
                x += im.width + 12
            sheet.save(results('le5', 'film', 'strip_%s.png' % name))
            print('strip', name)
        b.close()


if __name__ == '__main__':
    main()
