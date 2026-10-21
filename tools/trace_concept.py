"""Build the base art for a phone concept and measure the live layout anchors.

usage: py -I tools/trace_concept.py <concept.png> <config.json> <art_out.png> <layout_out.js> [--debug <dir>]

The concept raster is the picture. This script removes every live element from it (text ink,
the Review button, the Tell bar, Stop, the chip, the mission marks, the status dot) and writes the
cleaned raster as the base layer. Mesh threads that cross a removed glyph are redrawn from the
neighbouring strokes so no wire is interrupted. It also writes the measured anchors (ink boxes of
each text and mark, the control shapes and their colours) that the live overlay is placed on.
Config: tools/trace_phone.json. Re-run it for another concept by writing a new config.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from scipy import ndimage


def nconv(a, valid, sigma):
    num = ndimage.gaussian_filter(a * valid, sigma)
    den = ndimage.gaussian_filter(valid.astype(np.float32), sigma)
    return num / np.maximum(den, 1e-3)


def seg_cover(x1, y1, x2, y2, w, box):
    """Coverage of an anti-aliased line of width w over the pixel box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = x2 - x1, y2 - y1
    L2 = max(dx * dx + dy * dy, 1e-6)
    t = np.clip(((xs + 0.5 - x1) * dx + (ys + 0.5 - y1) * dy) / L2, 0, 1)
    d = np.hypot(xs + 0.5 - (x1 + t * dx), ys + 0.5 - (y1 + t * dy))
    return np.clip(w / 2 + 0.5 - d, 0, 1)


def merge_segments(segs, ang_tol, off_tol, gap):
    items = []
    for x1, y1, x2, y2 in segs:
        dx, dy = x2 - x1, y2 - y1
        if dx < 0 or (dx == 0 and dy < 0):
            x1, y1, x2, y2, dx, dy = x2, y2, x1, y1, -dx, -dy
        th = math.atan2(dy, dx) % math.pi
        ux, uy = math.cos(th), math.sin(th)
        items.append([th, -x1 * uy + y1 * ux, min(x1 * ux + y1 * uy, x2 * ux + y2 * uy), max(x1 * ux + y1 * uy, x2 * ux + y2 * uy)])
    items.sort(key=lambda s: (round(s[0], 2), s[1]))
    used = [False] * len(items)
    out = []
    for i, a in enumerate(items):
        if used[i]:
            continue
        used[i] = True
        th, rho, t0, t1 = a
        for j in range(i + 1, len(items)):
            b = items[j]
            if used[j]:
                continue
            dth = abs(b[0] - th)
            if min(dth, math.pi - dth) > ang_tol or abs(b[1] - rho) > off_tol or b[2] > t1 + gap or b[3] < t0 - gap:
                continue
            used[j] = True
            t0, t1 = min(t0, b[2]), max(t1, b[3])
        out.append((th, rho, t0, t1))
    res = []
    for th, rho, t0, t1 in out:
        ux, uy = math.cos(th), math.sin(th)
        px, py = -uy * rho, ux * rho
        res.append((px + ux * t0, py + uy * t0, px + ux * t1, py + uy * t1))
    return res


def multiscale_fill(rgb, hole, ring):
    """Fill each hole by harmonic interpolation (Laplace equation) from the pixels around it.
    Smooth by construction: no seams, no blotches. Pixels closer than `ring` to the hole are not
    used as boundary, so the glow and shadow of the removed glyphs do not leak in."""
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    H, W = hole.shape
    near = ndimage.binary_dilation(hole, iterations=ring)
    known = ~near
    # boundary value per hole pixel: smoothed colour of the known ring, not the raw pixels
    smooth = np.stack([wide_nconv(rgb[..., c], known) for c in range(3)], -1)
    idx = -np.ones((H, W), np.int64)
    unk = hole
    idx[unk] = np.arange(unk.sum())
    n = int(unk.sum())
    rows, cols, vals = [], [], []
    rhs = np.zeros((n, 3), np.float64)
    ys, xs = np.nonzero(unk)
    for k, (y, x) in enumerate(zip(ys, xs)):
        rows.append(k); cols.append(k); vals.append(4.0)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if not (0 <= yy < H and 0 <= xx < W):
                continue
            if unk[yy, xx]:
                rows.append(k); cols.append(idx[yy, xx]); vals.append(-1.0)
            else:
                rhs[k] += smooth[yy, xx]
    A = sparse.csr_matrix((vals, (rows, cols)), shape=(n, n))
    out = rgb.astype(np.float64).copy()
    for c in range(3):
        out[ys, xs, c] = spsolve(A, rhs[:, c])
    return out


def wide_nconv(a, valid):
    """Normalised convolution at growing scales: every pixel gets the average of the valid pixels
    around it, from the nearest scale that has enough support."""
    out = np.zeros(a.shape, np.float64)
    done = np.zeros(a.shape, bool)
    for sigma in (6.0, 16.0, 40.0, 120.0):
        den = ndimage.gaussian_filter(valid.astype(np.float32), sigma)
        ok = (den > 0.05) & ~done
        num = ndimage.gaussian_filter((a * valid).astype(np.float64), sigma)
        out[ok] = (num / np.maximum(den, 1e-9))[ok]
        done |= ok
    return out


def solid_bbox(sub, x0, y0):
    """Bounding box of the dense part of a mask: rows and columns that hold at least 30 % of the peak
    count, so a few stray pixels (a thread, a glint) do not stretch the box."""
    cols = sub.sum(0)
    rows = sub.sum(1)
    cx = np.nonzero(cols >= 0.3 * cols.max())[0]
    ry = np.nonzero(rows >= 0.3 * rows.max())[0]
    return [int(cx.min()) + x0, int(ry.min()) + y0, int(cx.max()) + x0 + 1, int(ry.max()) + y0 + 1]


def main():
    args = sys.argv[1:]
    debug = None
    if '--debug' in args:
        k = args.index('--debug')
        debug = args[k + 1]
        del args[k:k + 2]
    src, cfg_path, art_out, layout_out = args[:4]
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    bgr = cv2.imread(src, cv2.IMREAD_COLOR)
    H, W = bgr.shape[:2]
    if [W, H] != cfg['size']:
        sys.exit('concept size %dx%d does not match config %s' % (W, H, cfg['size']))
    rgb = bgr[..., ::-1].astype(np.float32)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)

    # Live elements. 'shape' boxes are opaque controls (filled whole); 'ink' boxes hold text or marks,
    # where only the ink pixels are removed and the mesh around them is kept.
    shape_mask = np.zeros((H, W), bool)
    for name, (x0, y0, x1, y1) in cfg['shapes'].items():
        shape_mask[y0:y1, x0:x1] = True
    ink_mask_box = np.zeros((H, W), bool)
    for name, (x0, y0, x1, y1) in cfg['inks'].items():
        ink_mask_box[y0:y1, x0:x1] = True
    all_box = shape_mask | ink_mask_box

    # Background model from pixels that are neither removed nor on a stroke (two passes).
    valid = ~ndimage.binary_dilation(all_box, iterations=4)
    bgL = nconv(lum, valid, cfg['bg_sigma'])
    dev = lum - bgL
    stroke0 = ndimage.binary_dilation(np.abs(dev) > 8, iterations=2) & valid
    valid2 = valid & ~stroke0
    bgL = nconv(lum, valid2, cfg['bg_sigma'])
    bgRGB = np.stack([nconv(rgb[..., c], valid2, cfg['bg_sigma']) for c in range(3)], -1)
    dev = lum - bgL

    # Ink of text and marks: pixels that stand out from their background.
    ink = np.zeros((H, W), bool)
    for name, (x0, y0, x1, y1) in cfg['inks'].items():
        thr = cfg.get('ink_thr', {}).get(name, cfg['ink_default'])
        sub = np.abs(dev[y0:y1, x0:x1]) > thr
        ink[y0:y1, x0:x1] |= sub
    ink = ndimage.binary_dilation(ink, iterations=cfg['ink_grow'])
    removed = (shape_mask | ink) & (np.ones((H, W), bool))
    removed = removed.astype(np.uint8) * 255

    # Strokes of the mesh (white top-hat ridges), measured on the original with live ink excluded.
    lum8 = np.clip(lum, 0, 255).astype(np.uint8)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (cfg['tophat_k'], cfg['tophat_k']))
    tophat = cv2.morphologyEx(lum8, cv2.MORPH_TOPHAT, kern).astype(np.float32)
    barrier = (tophat > cfg['barrier']) & ~(removed > 0)
    lines = cv2.HoughLinesP((barrier * 255).astype(np.uint8), 1, np.pi / 720, cfg['hough_thr'],
                            minLineLength=cfg['min_len'], maxLineGap=cfg['gap'])
    raw = [] if lines is None else [tuple(map(float, l[0])) for l in lines]
    segs = merge_segments(raw, math.radians(cfg['merge_angle']), cfg['merge_offset'], cfg['merge_gap'])
    info = []
    for x1, y1, x2, y2 in segs:
        L = math.hypot(x2 - x1, y2 - y1)
        if L < cfg['min_len']:
            continue
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        prof_pk, prof_rgb, prof_bg, prof_w = [], [], [], []
        for t in np.linspace(0.15, 0.85, 7):
            cx, cy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            offs = np.arange(-2.5, 2.51, 0.5)
            px, py = cx - uy * offs, cy + ux * offs
            pr = ndimage.map_coordinates(dev, [py, px], order=1)
            k = int(np.argmax(pr))
            if pr[k] < cfg['min_peak']:
                continue
            prof_pk.append(pr[k])
            prof_rgb.append([ndimage.map_coordinates(rgb[..., c], [[py[k]], [px[k]]], order=1)[0] for c in range(3)])
            prof_bg.append([ndimage.map_coordinates(bgRGB[..., c], [[py[k]], [px[k]]], order=1)[0] for c in range(3)])
            prof_w.append(float(np.clip(np.clip(pr, 0, None).sum() * 0.5 / pr[k], 0.5, 3.0)))
        if len(prof_pk) < 3:
            continue
        pc = np.median(np.array(prof_rgb), 0)
        bc = np.median(np.array(prof_bg), 0)
        info.append({'p': (x1, y1, x2, y2), 'pc': pc, 'bc': bc, 'w': float(np.median(prof_w)), 'L': L})

    REF = {'ivory': np.array(cfg['refs']['ivory'], np.float32), 'amber': np.array(cfg['refs']['amber'], np.float32),
           'blue': np.array(cfg['refs']['blue'], np.float32)}

    def cls_of(pc, bc):
        d = pc - bc
        if d[0] - d[2] > 40 and d[0] > 60:
            return 'amber'
        if d[2] - d[0] > 40:
            return 'blue'
        return 'ivory'
    for s in info:
        s['cls'] = cls_of(s['pc'], s['bc'])
        ref = REF[s['cls']]
        d = ref - s['bc']
        s['a'] = float(np.clip(np.dot(s['pc'] - s['bc'], d) / max(np.dot(d, d), 1.0), 0, 1))

    # Threads across a removed glyph: pairs of collinear strokes whose gap crosses removed ink.
    bridges = []
    rem_bool = removed > 0
    for A in info:
        for end in (0, 1):
            ex, ey = A['p'][2 * end], A['p'][2 * end + 1]
            ox, oy = A['p'][2 - 2 * end], A['p'][3 - 2 * end]
            ang = math.atan2(ey - oy, ex - ox)
            for B in info:
                if B is A or B['cls'] != A['cls']:
                    continue
                for fe in (0, 1):
                    fx, fy = B['p'][2 * fe], B['p'][2 * fe + 1]
                    dist = math.hypot(fx - ex, fy - ey)
                    if dist < 2 or dist > cfg['bridge_max']:
                        continue
                    ab = math.atan2(fy - ey, fx - ex)
                    if min(abs(ab - ang), 2 * math.pi - abs(ab - ang)) > math.radians(cfg['bridge_angle']):
                        continue
                    ts = np.linspace(0, 1, int(dist) + 2)
                    sx, sy = ex + (fx - ex) * ts, ey + (fy - ey) * ts
                    inside = rem_bool[np.clip(sy.astype(int), 0, H - 1), np.clip(sx.astype(int), 0, W - 1)]
                    if inside.mean() < 0.5 or inside.sum() < 2:
                        continue
                    if (ex, ey, fx, fy) not in [(b[0], b[1], b[2], b[3]) for b in bridges]:
                        bridges.append((ex, ey, fx, fy, A['w'], A['a'], A['cls']))
    # Keep each gap once (the closest partner per end).
    kept = []
    for b in sorted(bridges, key=lambda b: math.hypot(b[2] - b[0], b[3] - b[1])):
        if all(math.hypot(b[0] - k[0], b[1] - k[1]) > 3 for k in kept):
            kept.append(b)

    # Base art: inpaint the removed pixels, redraw the threads across them, feather the seam.
    base = multiscale_fill(rgb, removed > 0, cfg['fill_ring']).astype(np.float32)[..., ::-1]
    grow = cv2.dilate(removed, np.ones((3, 3), np.uint8)) > 0
    for ex, ey, fx, fy, w, a, cls in kept:
        x0, y0 = int(max(0, min(ex, fx) - 4)), int(max(0, min(ey, fy) - 4))
        x1, y1 = int(min(W, max(ex, fx) + 5)), int(min(H, max(ey, fy) + 5))
        cov = seg_cover(ex, ey, fx, fy, w, (x0, y0, x1, y1)) * a
        cov = cov * grow[y0:y1, x0:x1]
        col_bgr = REF[cls][::-1]
        region = base[y0:y1, x0:x1]
        base[y0:y1, x0:x1] = region * (1 - cov[..., None]) + col_bgr * cov[..., None]
    feather = cv2.GaussianBlur(cv2.dilate(removed, np.ones((3, 3), np.uint8)).astype(np.float32) / 255.0, (0, 0), cfg['feather'])
    feather = np.clip(feather * 1.0, 0, 1)[..., None]
    art = (base * feather + bgr.astype(np.float32) * (1 - feather)).clip(0, 255).astype(np.uint8)
    # Extend the art above and below by its edge rows (smoothed along the row), so a taller phone shows a
    # continuous background. The frame itself is unchanged; the extension is only seen off the 402 x 686.5 frame.
    pad = cfg['pad']
    top = cv2.GaussianBlur(art[0:4].astype(np.float32).mean(0, keepdims=True), (0, 0), sigmaX=12, sigmaY=0)
    bot = cv2.GaussianBlur(art[-4:].astype(np.float32).mean(0, keepdims=True), (0, 0), sigmaX=12, sigmaY=0)
    top_ext = np.repeat(top, pad, axis=0)
    bot_ext = np.repeat(bot, pad, axis=0)
    art_ext = np.vstack([top_ext, art.astype(np.float32), bot_ext]).clip(0, 255).astype(np.uint8)
    cv2.imwrite(art_out, art_ext, [cv2.IMWRITE_PNG_COMPRESSION, 9])

    # Measured anchors for the overlay. Text: ink box of the glyphs; marks and controls: ink box.
    text = {}
    for name, box in cfg['texts'].items():
        x0, y0, x1, y1 = box
        mode = cfg['text_mode'].get(name, 'light')
        sub = dev[y0:y1, x0:x1] > cfg['text_thr'] if mode == 'light' else lum[y0:y1, x0:x1] < cfg['dark_text_max']
        ys, xs = np.nonzero(sub)
        if len(xs) == 0:
            text[name] = {'box': [x0, y0, x1, y1]}
            continue
        text[name] = {'box': [int(xs.min()) + x0, int(ys.min()) + y0, int(xs.max()) + x0 + 1, int(ys.max()) + y0 + 1]}
    shapes = {}
    for name, box in cfg['shape_boxes'].items():
        x0, y0, x1, y1 = box
        r_, g_, b_ = rgb[y0:y1, x0:x1, 0], rgb[y0:y1, x0:x1, 1], rgb[y0:y1, x0:x1, 2]
        if cfg['shape_kind'].get(name) == 'amber':
            sub = (r_ > 200) & (g_ > 140) & (b_ < 140)
        else:
            sub = np.abs(dev[y0:y1, x0:x1]) > cfg['shape_thr']
        shapes[name] = solid_bbox(sub, x0, y0) if sub.any() else list(box)
    marks = {}
    for name, box in cfg['marks'].items():
        x0, y0, x1, y1 = box
        sub = np.abs(dev[y0:y1, x0:x1]) > cfg['ink_default']
        strong = np.abs(dev[y0:y1, x0:x1]) > cfg['mark_thr']
        ys, xs = np.nonzero(strong)
        marks[name] = [int(xs.min()) + x0, int(ys.min()) + y0, int(xs.max()) + x0 + 1, int(ys.max()) + y0 + 1] if len(xs) else list(box)

    # Background of the frame edges, for the extension above and below a taller phone.
    top_row = np.median(rgb[0:4].reshape(-1, 3), 0)
    bot_row = np.median(rgb[-4:].reshape(-1, 3), 0)
    layout = {
        'size': [W, H],
        'pad': pad,
        'text': text,
        'shapes': shapes,
        'marks': marks,
        'bridges': len(kept),
        'edge': {'top': [int(v) for v in top_row], 'bottom': [int(v) for v in bot_row]},
        'strokes': len(info),
    }
    with open(layout_out, 'w', encoding='utf-8') as fh:
        fh.write('/* Generated by tools/trace_concept.py from ' + os.path.basename(src) + '. Do not edit by hand. */\n')
        fh.write('window.ARCHEUS_LAYOUT = ' + json.dumps(layout, separators=(',', ':')) + ';\n')
    print('removed px %d, bridges %d, strokes %d' % (int((removed > 0).sum()), len(kept), len(info)))
    if debug:
        os.makedirs(debug, exist_ok=True)
        cv2.imwrite(os.path.join(debug, 'removed.png'), removed)
        cv2.imwrite(os.path.join(debug, 'art.png'), art)


if __name__ == '__main__':
    main()
