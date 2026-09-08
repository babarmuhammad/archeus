"""Capture the REAL architecture-graph HTML render to an animated GIF.

Unlike tools/make_gifs.py (a hand-drawn preview), this drives a headless
Chromium over the actual connections-graph.html and screenshots the live
animated canvas frame by frame, then assembles a GIF. Run it on YOUR machine.

Setup (once):
    pip install playwright pillow
    playwright install chromium

Usage:
    py tools/capture_graph_gif.py --project . --frames 48 --out docs/graph-real.gif
    py tools/capture_graph_gif.py --html "D:\\repos\\.archeus\\connections-graph.html"

Notes:
  --project builds/uses that project's graph (defaults to the current dir).
  --html captures an existing rendered graph HTML directly.
  Bigger --frames / --width = smoother + heavier GIF. Trim with --fps / --width.
"""

import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _graph_html_for(project):
    from claude_sessions import connections
    g = connections.build_hierarchy(project, None, force=False)
    return connections.write_graph_html(g, project, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default='.')
    ap.add_argument('--html', default='')
    ap.add_argument('--out', default=os.path.join('docs', 'graph-real.gif'))
    ap.add_argument('--frames', type=int, default=48)
    ap.add_argument('--fps', type=int, default=15)
    ap.add_argument('--width', type=int, default=1200)
    ap.add_argument('--height', type=int, default=680)
    ap.add_argument('--colors', type=int, default=96, help='GIF palette size (smaller = lighter)')
    ap.add_argument('--settle-ms', type=int, default=2000,
                    help='wait before capture so the layout settles')
    ap.add_argument('--expand-all', action='store_true',
                    help='click Expand all before capturing')
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("Playwright not installed. Run:\n  pip install playwright pillow\n"
              "  playwright install chromium")
        sys.exit(1)
    from PIL import Image

    html = args.html or _graph_html_for(os.path.abspath(args.project))
    if not html or not os.path.isfile(html):
        print(f"Graph HTML not found: {html}")
        sys.exit(1)
    url = 'file:///' + os.path.abspath(html).replace('\\', '/')

    interval = max(1, int(1000 / args.fps))
    frames = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': args.width, 'height': args.height},
                                device_scale_factor=1)
        page.goto(url)
        page.wait_for_selector('canvas', timeout=15000)
        if args.expand_all:
            try:
                page.click('#expand', timeout=2000)
            except Exception:
                pass
        page.wait_for_timeout(args.settle_ms)         # let the force layout settle
        target = page.query_selector('canvas') or page
        print(f"Capturing {args.frames} frames @ {args.fps}fps from {os.path.basename(html)} ...")
        for i in range(args.frames):
            png = target.screenshot()
            frames.append(Image.open(io.BytesIO(png)).convert('RGB'))
            page.wait_for_timeout(interval)
        browser.close()

    frames = [f.quantize(colors=args.colors, method=Image.MEDIANCUT,
                         dither=Image.Dither.NONE) for f in frames]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or '.', exist_ok=True)
    frames[0].save(args.out, save_all=True, append_images=frames[1:],
                   duration=interval, loop=0, optimize=True, disposal=2)
    print(f"wrote {args.out}  ({os.path.getsize(args.out) // 1024} KB, {len(frames)} frames)")


if __name__ == '__main__':
    main()
