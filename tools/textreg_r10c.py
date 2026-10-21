"""Register the live text of the Mission (03) and Shared (06) frames against a render at the concept size.

Run: py -I tools/textreg_r10c.py mission|shared <render.png> [--write]
For each text item, the ink box of the concept and of the render are measured inside the same search box (grown by
a few px for the render). Prints the offsets (render minus concept) and the width difference. With --write, the
measured offsets are added to the item's dx/dy in clients/v2-prototype/layout-r10c.js (placeFrame applies them).
Widths are reported, not changed: the font size is solved from the concept's ink width (tools/textfit_r10c.py).
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textfit_r10c as tf  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT = os.path.join(os.path.dirname(HERE), "clients", "v2-prototype", "layout-r10c.js")


def load_layout():
    raw = open(LAYOUT, encoding="utf8").read()
    return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])


def write_layout(data):
    with open(LAYOUT, "w", encoding="utf8") as f:
        f.write("/* Round 10c: live text layout for the Mission and Shared frames, solved from the concept rasters\n")
        f.write("   by tools/textfit_r10c.py (ink boxes in master px). Positions are the box origin; s is px, t is tracking px.\n")
        f.write("   dx, dy are registration offsets measured by tools/textreg_r10c.py against a render. */\n")
        f.write("window.R10C_LAYOUT = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n")


def main():
    name, render_path = sys.argv[1], sys.argv[2]
    write = "--write" in sys.argv
    items = tf.MISSION if name == "mission" else tf.SHARED
    concept = cv2.cvtColor(cv2.imread(tf.CONCEPTS[name]), cv2.COLOR_BGR2GRAY)
    render = cv2.cvtColor(cv2.imread(render_path), cv2.COLOR_BGR2GRAY)
    data = load_layout()
    layout = data[name]
    print(f"{'item':<13}{'dx':>7}{'dy':>7}{'dw':>7}{'dh':>7}  match")
    tot = []
    for iid, kind, box, text_ref, text_show, spaced, size_of in items:
        if iid not in layout:
            continue
        x0, y0, x1, y1 = box
        a = tf.ink_box(concept, box)
        if a is None:
            print(f"{iid:<13} no ink")
            continue
        # Offset by normalised cross-correlation of the concept's ink patch inside the render, within +-R px.
        R = 8
        tpl = concept[a[1]:a[3], a[0]:a[2]].astype(np.float32)
        tpl = tpl - tpl.mean()
        rx0, ry0 = max(0, a[0] - R), max(0, a[1] - R)
        rx1, ry1 = min(render.shape[1], a[2] + R), min(render.shape[0], a[3] + R)
        region = render[ry0:ry1, rx0:rx1].astype(np.float32)
        if tpl.shape[0] >= region.shape[0] or tpl.shape[1] >= region.shape[1]:
            print(f"{iid:<13} region too small")
            continue
        res = cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED)
        _, _, _, best = cv2.minMaxLoc(res)
        dx = (rx0 + best[0]) - a[0]
        dy = (ry0 + best[1]) - a[1]
        b = tf.ink_box(render, (rx0 + best[0], ry0 + best[1], rx0 + best[0] + (a[2] - a[0]), ry0 + best[1] + (a[3] - a[1])))
        dw = dh = 0
        if b is not None:
            dw, dh = (b[2] - b[0]) - (a[2] - a[0]), (b[3] - b[1]) - (a[3] - a[1])
        tot.append((abs(dx), abs(dy)))
        print(f"{iid:<13}{dx:>7}{dy:>7}{dw:>7}{dh:>7}  ncc {res.max():.2f}")
        if write and res.max() >= 0.45:
            layout[iid]["dx"] = round(layout[iid].get("dx", 0) - dx, 2)
            layout[iid]["dy"] = round(layout[iid].get("dy", 0) - dy, 2)
    if tot:
        print("max |dx|", max(t[0] for t in tot), "max |dy|", max(t[1] for t in tot))
    if write:
        data[name] = layout
        write_layout(data)
        print("wrote offsets to", LAYOUT)


if __name__ == "__main__":
    main()
