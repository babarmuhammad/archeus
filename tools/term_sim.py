"""Render the terminal screens at their concept size and compare them with the concept.

usage:
  py -I tools/term_sim.py render <out_dir> [screen]     screen: overview (default), mission, decision, replay, help, stack
  py -I tools/term_sim.py compare <out_dir>              full-resolution metrics, diff, montage (overview only)

The render serves clients/v2-prototype on localhost, opens #/terminal in headless Chromium at DPR 1, pins the
terminal wrapper to the master width (1600 css px for the overview, 862 for the page screens) and screenshots
the SVG at its design size. Nothing is sent anywhere; the page is the local prototype.
"""
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "clients", "v2-prototype"))
CONCEPT = r"D:\hub-concepts-codex4\terminal-1-overview-v2.png"
PORT = 8779

SCREENS = {
    # name: (hash, data-tsize button or None, wrapper width in css px, mode)
    "overview": ("#/terminal", "120", 1600),
    "stack": ("#/terminal", "80", 1118),
    "mission": ("#/terminal", "j Enter", 862),
    "decision": ("#/terminal", "r", 862),
    "replay": ("#/terminal", "j p", 862),
    "help": ("#/terminal", "?", 862),
}


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = lambda *a, **k: Quiet(*a, directory=ROOT, **k)
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def render(out_dir, screen="overview"):
    from playwright.sync_api import sync_playwright
    hsh, tsize, width = SCREENS[screen]
    os.makedirs(out_dir, exist_ok=True)
    srv = serve()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(channel="msedge") if os.path.exists(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") else p.chromium.launch()
            pg = br.new_page(viewport={"width": width + 600, "height": 1400}, device_scale_factor=1,
                             reduced_motion="reduce")
            pg.goto(f"http://127.0.0.1:{PORT}/{hsh}", wait_until="load")
            pg.evaluate("document.fonts.ready")
            pg.evaluate(f"""() => {{
                const w = document.querySelector('.term-wrap');
                w.style.width = '{width}px';
                w.style.maxWidth = 'none';
            }}""")
            if tsize and tsize.isdigit():
                pg.click(f"[data-tsize='{tsize}']")
            elif tsize:
                pg.focus("#term")
                for key in tsize.split():
                    pg.keyboard.press(key)
            if screen in ("mission", "decision", "replay"):
                pass
            if os.environ.get("TERM_EXTRA_CSS"):
                pg.add_style_tag(content=os.environ["TERM_EXTRA_CSS"])
            pg.wait_for_timeout(120)
            el = pg.query_selector("#term svg")
            box = el.bounding_box()
            pg.screenshot(path=os.path.join(out_dir, f"render-{screen}.png"),
                          clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]})
            info = pg.evaluate("() => ({w: document.querySelector('#term svg').getAttribute('width'), h: document.querySelector('#term svg').getAttribute('height'), cssw: document.querySelector('#term svg').getBoundingClientRect().width, font: getComputedStyle(document.querySelector('.term text') || document.body).fontFamily})")
            print(json.dumps(info))
            br.close()
    finally:
        srv.shutdown()
        srv.server_close()
    print("wrote", os.path.join(out_dir, f"render-{screen}.png"))


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float64)


def lum(a):
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def region(d, x0, y0, x1, y1):
    return float(d[y0:y1, x0:x1].mean())


def compare(out_dir, render_path=None):
    c = load(CONCEPT)
    r_path = render_path or os.path.join(out_dir, "render-overview.png")
    r = load(r_path)
    H, W = c.shape[:2]
    r = r[:H, :W]
    d = np.abs(c - r)
    mx = d.max(axis=-1)
    # Text boxes (concept ink, rounded out) and the rest of the frame.
    text_boxes = {
        "header": (30, 45, 640, 110), "header-right": (1360, 45, 1575, 80),
        "root": (700, 110, 900, 180), "main-title": (510, 245, 1080, 270), "main-rows": (500, 300, 1090, 610),
        "notes-ideas": (1230, 290, 1530, 590), "footer": (30, 675, 430, 745), "keys": (30, 780, 1060, 815),
        "input": (30, 830, 300, 862),
    }
    lines = {
        "rule": (25, 36, 1575, 42), "main-box": (480, 230, 1112, 656), "divider": (808, 298, 818, 630),
        "notes-box": (1234, 292, 1528, 418), "ideas-box": (1234, 460, 1528, 585), "connectors": (1108, 260, 1230, 530),
        "strip": (20, 820, 1580, 872),
    }
    res = {}
    for k, (x0, y0, x1, y1) in {**text_boxes, **lines}.items():
        res[k] = {"mean_abs": round(region(d, x0, y0, x1, y1), 2),
                  "p99": int(np.percentile(mx[y0:y1, x0:x1], 99)),
                  "gt24_pct": round(100.0 * float((mx[y0:y1, x0:x1] > 24).mean()), 2)}
    res["frame"] = {"mean_abs": round(float(d.mean()), 2), "p99": int(np.percentile(mx, 99)),
                    "gt24_pct": round(100.0 * float((mx > 24).mean()), 2)}
    # 160 px luminance and colour similarity (as in the round 10c metrics).
    from scipy import ndimage

    def small(a):
        im = Image.fromarray(a.astype(np.uint8)).resize((160, round(H * 160 / W)), Image.LANCZOS)
        return np.asarray(im).astype(np.float64)
    cs, rs = small(c), small(r)
    blur = lambda a: ndimage.gaussian_filter(a, 1.2)
    mad_l = float(np.abs(blur(lum(cs)) - blur(lum(rs))).mean())
    amb = lambda a: np.clip((a[..., 0] - a[..., 2]) * (a[..., 0] > a[..., 2]) / 255.0, 0, 1)
    blu = lambda a: np.clip((a[..., 2] - a[..., 0]) * (a[..., 2] > a[..., 0]) / 255.0, 0, 1)
    mad_a = float(np.abs(blur(amb(cs)) - blur(amb(rs))).mean() * 255)
    mad_b = float(np.abs(blur(blu(cs)) - blur(blu(rs))).mean() * 255)
    res["sim160"] = {"lum_mad": round(mad_l, 2), "amber_mad": round(mad_a, 2), "blue_mad": round(mad_b, 2)}

    # Outputs: diff x4 (gray), 50 % overlay, and lossless PNG copies for alternation.
    diff = np.clip(mx * 4, 0, 255).astype(np.uint8)
    Image.fromarray(diff).save(os.path.join(out_dir, "diff-x4.png"))
    blend = (0.5 * c + 0.5 * r).astype(np.uint8)
    Image.fromarray(blend).save(os.path.join(out_dir, "blend-50.png"))
    Image.fromarray(c.astype(np.uint8)).save(os.path.join(out_dir, "concept.png"))
    Image.fromarray(r.astype(np.uint8)).save(os.path.join(out_dir, "render.png"))
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, indent=1))


def probe(screen="overview"):
    """Label overlap: pairs of text runs whose boxes intersect (zero expected)."""
    from playwright.sync_api import sync_playwright
    hsh, tsize, width = SCREENS[screen]
    srv = serve()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            pg = br.new_page(viewport={"width": width + 600, "height": 1400}, reduced_motion="reduce")
            pg.goto(f"http://127.0.0.1:{PORT}/{hsh}", wait_until="load")
            if tsize and tsize.isdigit():
                pg.click(f"[data-tsize='{tsize}']")
            elif tsize:
                pg.focus("#term")
                for key in tsize.split():
                    pg.keyboard.press(key)
            boxes = pg.evaluate("""() => [...document.querySelectorAll('#term svg text')].map(t => {
                const b = t.getBBox(); return {s: t.textContent, x0: b.x, y0: b.y, x1: b.x + b.width, y1: b.y + b.height}; })""")
            br.close()
    finally:
        srv.shutdown()
        srv.server_close()
    hits = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a["x0"] < b["x1"] - 0.5 and b["x0"] < a["x1"] - 0.5 and a["y0"] < b["y1"] - 0.5 and b["y0"] < a["y1"] - 0.5:
                hits.append((a["s"], b["s"]))
    print(screen, "text runs", len(boxes), "overlapping pairs", len(hits), hits[:10])
    return hits


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "render":
        render(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "overview")
    elif cmd == "probe":
        probe(sys.argv[2] if len(sys.argv) > 2 else "overview")
    elif cmd == "compare":
        compare(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
