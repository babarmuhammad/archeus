"""Record the guided tour as an animated WebP — the GUI half of the video guide.

archeus cannot ship a video: a real recording is tens of megabytes, goes stale
the first time a screen changes, and nothing in CI can tell that it has. So the
"video guide" is GENERATED from the same tour the app runs — the real app, in a
real browser, driven through `TOUR.start()` and screenshotted — which means it
is re-recordable with one command every time the front end moves, exactly like
the screenshots (`tools/shot_gui.py`) it sits beside.

    py -3 tools/capture_tour.py                 # short tour -> docs + www
    py -3 tools/capture_tour.py --which long
    py -3 tools/capture_tour.py --hold 3.0 --fps 6

WebP, never GIF, and for the reason `capture_graph_gif.py` already records: GIF
has no interframe compression worth the name, and the same capture is roughly
ten times the bytes. This is a page's largest paint; ten times is not a detail.

It drives the SAME stub workspace `tools/shot_gui.py` screenshots, so the frames
show a populated app rather than an empty one, and it takes the graph world for
the same reason the published captures do: one look across one published set.
"""

import argparse
import importlib.util
import io
import os
import shutil
import sys
import threading
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

#: the stub server and its workspace, loaded the way shot_gui loads it — one
#: definition of "a realistic workspace", not a third.
_spec = importlib.util.spec_from_file_location(
    'sg', os.path.join(ROOT, 'tools', 'smoke_gui.py'))
sg = importlib.util.module_from_spec(_spec)
sg.__name__ = 'sg'
_spec.loader.exec_module(sg)

PORT = 8803
DOCS = os.path.join(ROOT, 'docs', 'img')
WWW = os.path.join(ROOT, 'www', 'public', 'img')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--which', default='short', choices=('short', 'long'))
    ap.add_argument('--hold', type=float, default=2.5,
                    help='seconds a step stays on screen')
    #: 2fps, not a video frame rate. Every frame inside a step is identical with
#: motion frozen, so this decides how many duplicate frames the encoder gets
#: to collapse rather than how smooth anything looks; the only thing it
#: really sets is how long a step is readable for.
    ap.add_argument('--fps', type=int, default=2)
    ap.add_argument('--width', type=int, default=1152)
    ap.add_argument('--height', type=int, default=720)
    ap.add_argument('--quality', type=int, default=60)
    ap.add_argument('--out', default='')
    ap.add_argument('--live-motion', action='store_true',
                    help='leave the background scene running (much larger file)')
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print('Playwright not installed. Run:\n  pip install playwright pillow\n'
              '  playwright install chromium')
        return 1
    from PIL import Image

    out = args.out or os.path.join(DOCS, 'tour-gui-%s.webp' % args.which)
    interval = max(1, int(1000 / max(1, args.fps)))
    per_step = max(1, int(round(args.hold * args.fps)))
    frames = []

    srv = ThreadingHTTPServer(('127.0.0.1', PORT), sg.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        # SwiftShader, so the background stage is actually in the frames rather
        # than the static fallback — the same flags shot_gui and smoke_gui use.
        br = pw.chromium.launch(args=[
            '--use-gl=angle', '--use-angle=swiftshader',
            '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
        pg = br.new_page(viewport={'width': args.width, 'height': args.height})
        pg.goto('http://127.0.0.1:%d/?k=%s' % (PORT, sg.gui.TOKEN))
        pg.wait_for_timeout(2500)
        # the world the published captures wear
        try:
            pg.evaluate("ST.world='graph';applyTheme(ST.theme)")
            pg.wait_for_timeout(600)
        except Exception:
            pass
        # a project open, so the tour's project-tab steps have tabs to ring
        try:
            pg.evaluate("openProject(ST.projects[0])")
            pg.wait_for_timeout(600)
        except Exception:
            pass
        # STILL by default, and it is a size decision rather than a taste one:
        # WebP compresses BETWEEN frames, so a background scene that moves makes
        # every frame of a step unique and the file is what a real screen
        # recording costs. Frozen, the frames inside one step are identical and
        # the encoder throws them away — measured here, 860 KB -> a fraction of
        # it, for a recording of a step tour in which nothing but the step is
        # supposed to be moving anyway.
        if not args.live_motion:
            try:
                pg.evaluate("document.documentElement.classList.add('mo-off');"
                            "if(window.STAGE&&STAGE.blur)STAGE.blur(true);"
                            "if(window.MO&&MO.stop)MO.stop();")
                pg.wait_for_timeout(400)
            except Exception:
                pass

        n = pg.evaluate("(async()=>{await TOUR.start('%s');return TOUR.steps.length;})()"
                        % args.which)
        if not n:
            print('the tour returned no steps — is /api/tour served?')
            br.close()
            return 1
        print('recording %d steps of the %s tour at %d fps, %.1fs each'
              % (n, args.which, args.fps, args.hold))
        for i in range(n):
            pg.wait_for_timeout(500)          # the step's own navigation lands
            for _ in range(per_step):
                frames.append(Image.open(io.BytesIO(pg.screenshot())).convert('RGB'))
                pg.wait_for_timeout(interval)
            if i + 1 < n:
                pg.evaluate('TOUR.next()')
        br.close()
    srv.shutdown()

    if not frames:
        print('no frames captured')
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    frames[0].save(out, 'WEBP', save_all=True, append_images=frames[1:],
                   duration=interval, loop=0, quality=args.quality, method=6)
    size = os.path.getsize(out) // 1024
    print('wrote %s  (%d KB, %d frames)' % (out, size, len(frames)))
    # published to both hosts, like every other capture: docs/img is the
    # manual's and www/public/img is the apex's, and a file in only one of them
    # is a broken image on the other.
    if not args.out:
        os.makedirs(WWW, exist_ok=True)
        shutil.copy2(out, os.path.join(WWW, os.path.basename(out)))
        print('       -> %s' % os.path.join(WWW, os.path.basename(out)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
