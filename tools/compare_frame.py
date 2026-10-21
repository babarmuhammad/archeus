"""Compare a rendered phone frame with the concept at full resolution (no blur, no resampling).

usage: py -I tools/compare_frame.py <concept.png> <render.png> <config.json> <out_dir> [label]

Both images must be 804 x 1373 (the concept at 402 css px wide, DPR 2). The render is the frame
captured with clip (0, 0, 402, 686.5) at DPR 2. Metrics are the mean absolute RGB difference (0 to 255),
the 99th percentile of the per-pixel maximum channel difference, and the share of pixels whose maximum
channel difference is above 24. Regions: the art (not covered by any live element), each text line,
each live mark, the controls, the header and the full frame. Writes: diff x4, a 50 % blend, an alpha
overlay, lossless PNGs of both frames for alternation, and crops of the ten worst 48 px blocks.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image


def load(path):
    im = cv2.imread(path, cv2.IMREAD_COLOR)
    return im[..., ::-1].astype(np.int16)


def region_stats(d, mx, box):
    x0, y0, x1, y1 = box
    sub = d[y0:y1, x0:x1]
    m = mx[y0:y1, x0:x1]
    return {
        'mean': round(float(sub.mean()), 2),
        'p99': int(np.percentile(m, 99)),
        'gt24': round(100.0 * float((m > 24).mean()), 2),
    }


def main():
    concept, render, cfg_path, out_dir = sys.argv[1:5]
    label = sys.argv[5] if len(sys.argv) > 5 else 'render'
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    os.makedirs(out_dir, exist_ok=True)
    c = load(concept)
    r = load(render)
    H, W = c.shape[:2]
    if r.shape[0] < H:
        pad = np.zeros((H - r.shape[0], W, 3), np.int16)
        r = np.vstack([r, pad])
    r = r[:H, :W]
    d = np.abs(c - r)
    mx = d.max(-1)

    live = np.zeros((H, W), bool)
    boxes = {}
    for name, box in cfg['text_boxes'].items():
        boxes['text:' + name] = box
    for name, box in cfg['mark_boxes'].items():
        boxes['mark:' + name] = box
    for name, box in cfg['control_boxes'].items():
        boxes['control:' + name] = box
    for name, box in boxes.items():
        x0, y0, x1, y1 = box
        live[y0:y1, x0:x1] = True
    art = ~live
    res = {}
    art_stats = {'mean': round(float(d[art].mean()), 2), 'p99': int(np.percentile(mx[art], 99)),
                 'gt24': round(100.0 * float((mx[art] > 24).mean()), 2)}
    res['art (no live element)'] = art_stats
    for name, box in boxes.items():
        res[name] = region_stats(d, mx, box)
    res['header'] = region_stats(d, mx, cfg['header_box'])
    res['frame'] = region_stats(d, mx, (0, 0, W, H))
    res['scene (art plus marks)'] = region_stats(d, mx, cfg['scene_box'])

    # Ten worst 48 px blocks (mean of the channel-max difference), as crops.
    B = 48
    worst = []
    for y in range(0, H - B + 1, B // 2):
        for x in range(0, W - B + 1, B // 2):
            worst.append((float(mx[y:y + B, x:x + B].mean()), x, y))
    worst.sort(reverse=True)
    top = worst[:10]
    tiles = []
    ci = Image.open(concept).convert('RGB')
    ri = Image.open(render).convert('RGB')
    ri = Image.fromarray(np.asarray(ri)[:H, :W]) if ri.height >= H else ri
    for val, x, y in top:
        a = ci.crop((x, y, x + B, y + B)).resize((B * 4, B * 4), Image.NEAREST)
        b = ri.crop((x, y, x + B, y + B)).resize((B * 4, B * 4), Image.NEAREST)
        t = Image.new('RGB', (B * 8 + 8, B * 4), (90, 90, 90))
        t.paste(a, (0, 0)); t.paste(b, (B * 4 + 8, 0))
        tiles.append((t, val, x, y))
    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (B * 8 + 8) + 16, rows * (B * 4 + 30)), (20, 20, 20))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for i, (t, val, x, y) in enumerate(tiles):
        cx, cy = (i % cols) * (B * 8 + 8 + 16), (i // cols) * (B * 4 + 30)
        sheet.paste(t, (cx, cy + 22))
        dr.text((cx, cy + 4), '#%d x=%d y=%d mean %.1f' % (i + 1, x, y, val), fill=(240, 240, 240))
    sheet.save(os.path.join(out_dir, 'worst10.png'))

    amp = np.clip(d * 4, 0, 255).astype(np.uint8)
    Image.fromarray(amp).save(os.path.join(out_dir, 'diff-x4.png'))
    blend = ((c + r) / 2).clip(0, 255).astype(np.uint8)
    Image.fromarray(blend).save(os.path.join(out_dir, 'blend50.png'))
    ov = c.copy().astype(np.uint8)
    alpha = (mx > 24)
    ov[alpha] = [255, 0, 255]
    Image.fromarray(ov).save(os.path.join(out_dir, 'overlay-gt24.png'))
    Image.open(concept).convert('RGB').save(os.path.join(out_dir, 'a-concept.png'))
    Image.open(render).convert('RGB').save(os.path.join(out_dir, 'b-' + label + '.png'))

    with open(os.path.join(out_dir, 'metrics.json'), 'w', encoding='utf-8') as fh:
        json.dump({'label': label, 'regions': res, 'worst': [[round(v, 1), x, y] for v, x, y in top]}, fh, indent=1)
    print('ink boxes, concept vs render (x0 y0 x1 y1; dx dy dw dh in px at 804 wide):')
    for name, box in cfg['text_boxes'].items():
        x0, y0, x1, y1 = box
        cs = c[y0:y1, x0:x1].mean(-1)
        rs = r[y0:y1, x0:x1].mean(-1)
        def ink(a):
            fl = np.percentile(a, 30)
            ys, xs = np.nonzero(a > fl + 40)
            if len(xs) == 0:
                return None
            return [int(xs.min()) + x0, int(ys.min()) + y0, int(xs.max()) + x0 + 1, int(ys.max()) + y0 + 1]
        ci, ri = ink(cs), ink(rs)
        if ci and ri:
            mc = float(np.clip(cs - np.percentile(cs, 30), 0, None).sum())
            mr = float(np.clip(rs - np.percentile(rs, 30), 0, None).sum())
            print('  %-18s concept %s render %s  d %+d %+d %+d %+d  ink mass ratio %.2f' % (name, ci, ri, ri[0]-ci[0], ri[1]-ci[1], ri[2]-ci[2], ri[3]-ci[3], mr / max(mc, 1)))
    print('%-28s %8s %6s %7s' % ('region', 'mean', 'p99', '>24 %'))
    for k, v in res.items():
        if v is None:
            continue
        print('%-28s %8.2f %6d %7.2f' % (k[:28], v['mean'], v['p99'], v['gt24']))
    print('worst blocks (mean channel-max diff, x, y):', [(round(v, 1), x, y) for v, x, y in top[:5]])


if __name__ == '__main__':
    main()
