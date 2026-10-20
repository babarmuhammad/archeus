"""LV2-X.3 Q18: the four ways a phone action can say what it does, side by side, on the same screens.
  py prototypes/v2-later/tools/lvx_q18.py      -> results/lvx/x3/q18_*.png (one sheet per screen)
a: the consequence in the label · b: one sentence by the group · c: every action a row with its consequence
d: rows for actions that change something, a compact button for one that does not (with DR-9's Explain drawn).
Prototype tooling.
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from serve import serve, results

SCREENS = [
    ('error', 'v=mission&id=m-c3e9', '#ask'),
    ('stopped_after', 'v=mission&id=x-09&corpus=x2', '#ask'),
    ('approval_bar', 'v=mission&id=m-91d2', '.x-abar'),
    ('approval_sheet', 'v=mission&id=m-91d2&sheet=1', '.x-sheet, .x-abar'),
]
VARIANTS = ['a', 'b', 'c', 'd']


def main():
    out = os.path.join(results('lvx', 'x')[:-2], 'x3')
    os.makedirs(out, exist_ok=True)
    base, _srv = serve()
    base = base.replace('/lab/', '/lvx/')
    font = ImageFont.truetype('segoeui.ttf', 26)
    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True, color_scheme='dark')
        for name, q, sel in SCREENS:
            if name == 'approval_sheet':
                vs = ['c']
            else:
                vs = VARIANTS
            tiles = []
            for v in vs:
                pg = c.new_page()
                pg.goto('%sindex.html?d=e2&%s&q18=%s%s&shot=1' % (base, q, v, '&dr9=1' if v == 'd' and name == 'error' else ''))
                pg.wait_for_timeout(250)
                el = pg.locator(sel).last
                el.scroll_into_view_if_needed()
                png = el.screenshot() if name != 'approval_sheet' else pg.screenshot()
                tiles.append((v, Image.open(io.BytesIO(png))))
                pg.close()
            w = sum(t.width for _, t in tiles) + 40 * (len(tiles) + 1)
            h = max(t.height for _, t in tiles) + 90
            sheet = Image.new('RGB', (w, h), (13, 17, 23))
            d = ImageDraw.Draw(sheet)
            x = 40
            for v, t in tiles:
                d.text((x, 24), '%s · %s' % (name, v), fill=(201, 209, 217), font=font)
                sheet.paste(t, (x, 70))
                x += t.width + 40
            sheet.save(os.path.join(out, 'q18_%s.png' % name))
            print('q18', name, len(tiles))
        b.close()


if __name__ == '__main__':
    main()
