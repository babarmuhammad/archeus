"""Render the eight V2 surfaces at their master size and compare them with the concept (full resolution, no blur).

usage: py -I tools/polish_measure.py <surface|all> <out_dir>
  surfaces: desktop, replay, mission, shared, terminal, phone1, phone2, phone3

Each surface opens clients/v2-prototype on localhost in headless Chromium (reduced motion, fonts awaited), takes the
frame at the master size and writes render-<s>.png, absdiff-<s>.png (x4) and metrics.json. Metric: mean absolute RGB
difference (0 to 255) and the share of pixels whose largest channel difference is above 24.
Phone frames are captured at DPR 2 (804 x 1373, 724 x 1573). Nothing leaves the machine.
"""
import http.server
import json
import os
import socketserver
import sys
import threading

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "clients", "v2-prototype"))
PORT = 8791
CONCEPTS = {
    "desktop": r"D:\hub-concepts-codex4\desktop-1-now-v2.png",
    "replay": r"D:\hub-concepts-codex4\replay-2-desktop-v2.png",
    "mission": r"D:\hub-v2-final-codex\concept-mission.png",
    "shared": r"D:\hub-v2-final-codex\concept-shared.png",
    "terminal": r"D:\hub-concepts-codex4\terminal-1-overview-v2.png",
    "termsvg": r"D:\hub-concepts-codex4\terminal-1-overview-v2.png",
    "phone1": r"D:\hub-concepts-codex4\phone-1-now-v2.png",
    "phone2": r"D:\hub-concepts-codex4\phone-2-decision-v2.png",
    "phone3": r"D:\hub-concepts-codex4\phone-3-chat-v2.png",
}
# name: (hash, viewport w, viewport h, dpr, crop w, crop h)
SURFACES = {
    "desktop": ("#/now", 1296, 755, 1, 1296, 729),
    "replay": ("#/replay/m-date", 1440, 836, 1, 1440, 810),
    "mission": ("#/mission/m-date", 1244, 855, 1, 1244, 829),
    "shared": ("#/shared", 1382, 948, 1, 1382, 922),
    "terminal": ("#/terminal", 1600, 900, 1, 1600, 900),
    "termsvg": ("#/terminal", 2200, 1400, 1, 1600, 900),
    "phone1": ("#/now", 402, 687, 2, 804, 1373),
    "phone2": ("#/plan/m-search", 362, 787, 2, 724, 1573),
    "phone3": ("#/now", 362, 787, 2, 724, 1573),
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


def capture(pg, name, out_path):
    hsh, vw, vh, dpr, cw, ch = SURFACES[name]
    pg.goto(f"http://127.0.0.1:{PORT}/{hsh}", wait_until="load")
    pg.evaluate("document.fonts.ready")
    if name == "termsvg":
        pg.evaluate("document.querySelector(\"[data-tsize='120']\").click()")
        pg.evaluate("""() => { const w = document.querySelector('.term-wrap');
            w.style.width = '1600px'; w.style.maxWidth = 'none'; }""")
        pg.wait_for_timeout(150)
        box = pg.query_selector("#term svg").bounding_box()
        pg.screenshot(path=out_path, clip={"x": box["x"], "y": box["y"], "width": 1600, "height": 900})
        return
    if name == "phone3":
        pg.click("#chat-input")
    pg.wait_for_timeout(150)
    if name == "terminal":
        pg.evaluate("document.querySelector(\"[data-tsize='120']\").click()")
        pg.evaluate("window.scrollTo(0, 0)")
        pg.wait_for_timeout(150)
        pg.screenshot(path=out_path, clip={"x": 0, "y": 0, "width": 1600, "height": 900})
        return
    if name.startswith("phone"):
        pg.screenshot(path=out_path)
        return
    pg.screenshot(path=out_path, clip={"x": 0, "y": 0, "width": cw / dpr, "height": ch / dpr})


def measure(name, out_dir):
    from playwright.sync_api import sync_playwright
    hsh, vw, vh, dpr, cw, ch = SURFACES[name]
    os.makedirs(out_dir, exist_ok=True)
    rp = os.path.join(out_dir, f"render-{name}.png")
    srv = serve()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(channel="msedge") if os.path.exists(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") else p.chromium.launch()
            pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=dpr, reduced_motion="reduce")
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            capture(pg, name, rp)
            br.close()
    finally:
        srv.shutdown()
        srv.server_close()
    c = np.asarray(Image.open(CONCEPTS[name]).convert("RGB")).astype(np.int16)
    r = np.asarray(Image.open(rp).convert("RGB")).astype(np.int16)
    H, W = c.shape[:2]
    if r.shape[0] < H or r.shape[1] < W:
        raise SystemExit(f"render too small for {name}: {r.shape} vs {c.shape}")
    r = r[:H, :W]
    d = np.abs(c - r)
    mx = d.max(-1)
    out = {"surface": name, "size": [W, H], "mean_abs": round(float(d.mean()), 2),
           "gt24_pct": round(100.0 * float((mx > 24).mean()), 2), "page_errors": errors}
    Image.fromarray(np.clip(d * 4, 0, 255).astype(np.uint8)).save(os.path.join(out_dir, f"absdiff-{name}.png"))
    with open(os.path.join(out_dir, f"metrics-{name}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    which = sys.argv[1]
    out_dir = sys.argv[2]
    names = list(SURFACES) if which == "all" else which.split(",")
    for n in names:
        measure(n, out_dir)
