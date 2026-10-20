"""LV2-X.3 Q17: the phone's running-work strip in every state that matters, side by side.
  py prototypes/v2-later/tools/lvx_q17.py  -> results/lvx/x3/q17_<page>.png
Also measures, per state, whether the strip covers content: the last element of the page must end above the dock
when scrolled to the bottom. Prototype tooling.
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from serve import serve, results

STATES = [('nothing running', 's=idle'), ('one running', 's=one'), ('several', ''), ('stress day', 'corpus=x2'),
          ('waiting + failed', ''), ('stopped', 's=stopped'), ('Core unreachable', 's=offline')]
PAGES = ['projects', 'home']
COVER = r"""() => {
  window.scrollTo(0, document.documentElement.scrollHeight);
  const dock = document.querySelector('.x-dock'), main = document.querySelector('.x-pmain');
  if (!dock || !main) return null;
  const last = [...main.querySelectorAll('*')].filter(e => e.getBoundingClientRect().height > 0).pop();
  return { strip: !!document.querySelector('.x-strip'), text: (document.querySelector('.x-strip') || {}).innerText || '',
    gap: Math.round(dock.getBoundingClientRect().top - last.getBoundingClientRect().bottom) };
}"""


def main():
    out = os.path.join(results('lvx', 'x')[:-2], 'x3')
    os.makedirs(out, exist_ok=True)
    base, _srv = serve()
    base = base.replace('/lab/', '/lvx/')
    font = ImageFont.truetype('segoeui.ttf', 30)
    lines = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True, color_scheme='dark')
        for page in PAGES:
            tiles = []
            for label, q in STATES:
                pg = c.new_page()
                pg.goto('%sindex.html?d=e2&v=%s&%s&shot=1' % (base, page, q))
                pg.wait_for_timeout(250)
                tiles.append((label, Image.open(io.BytesIO(pg.screenshot()))))
                r = pg.evaluate(COVER)
                lines.append('%-9s %-18s strip=%-5s clear-of-dock=%s  %s' % (page, label, r and r['strip'], r and r['gap'] >= 0, (r and r['text'] or '').replace('\n', ' | ')))
                pg.close()
            sc = 0.5
            tw, th = int(tiles[0][1].width * sc), int(tiles[0][1].height * sc)
            sheet = Image.new('RGB', (len(tiles) * (tw + 30) + 30, th + 80), (13, 17, 23))
            d = ImageDraw.Draw(sheet)
            for i, (label, t) in enumerate(tiles):
                x = 30 + i * (tw + 30)
                d.text((x, 22), label, fill=(201, 209, 217), font=font)
                sheet.paste(t.resize((tw, th)), (x, 70))
            sheet.save(os.path.join(out, 'q17_%s.png' % page))
        b.close()
    open(os.path.join(out, 'q17.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
