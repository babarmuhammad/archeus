"""Fit the live text to the concept's measured ink boxes.

usage: py -I tools/fit_type.py <layout.js> <fonts.json> <concept.png> <out.js> [offsets.json]

offsets.json maps a text key to [dx, dy, dls] in concept units (dls adds to the tracking): the correction measured by compare_frame.py
(the rendered ink box minus the concept's), so the next fit lands on the concept.

For each text in the layout (ink box measured from the concept by trace_concept.py):
- the font size comes from the ink height,
- the tracking from the ink width (zero for body and tappable text, which keep the 14 CSS px floor),
- the origin from the ink left and the baseline,
- the weight from WEIGHT (set by hand against the concept glyphs).
The fonts are the files the page loads (fonts.json maps family to file), so the metrics are the page's metrics.
"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SPEC = {
    'wordmark': ('serif', 'ARCHEUS'),
    'fixture': ('sans', 'CONCEPT FIXTURE'),
    'status_text': ('sans', 'Not stopped \u00b7 accepts new work'),
    'headline_1': ('serif', '1 needs you \u00b7'),
    'headline_2': ('serif', '1 verifying'),
    'label_search': ('serif', 'Search provenance'),
    'label_review_plan': ('sans', 'Review plan'),
    'label_fix': ('serif', 'Fix date test'),
    'label_codex': ('sans', 'Codex'),
    'chip_text': ('sans', '2 more projects'),
    'review_label': ('sans', 'Review'),
    'bar_text': ('sans', 'Tell Archeus\u2026'),
    'stop_text': ('sans', 'Stop'),
}
# Chosen by overlay against the concept glyphs (see README round 10d), not by ink mass.
WEIGHT = {'wordmark': 400, 'fixture': 400, 'status_text': 400, 'headline_1': 500, 'headline_2': 500,
          'label_search': 500, 'label_review_plan': 400, 'label_fix': 500, 'label_codex': 400, 'chip_text': 400,
          'review_label': 600, 'bar_text': 400, 'stop_text': 500}
MIN_TAPPABLE = {'status_text': 31.4, 'chip_text': 31.4, 'review_label': 31.4, 'bar_text': 31.4, 'stop_text': 31.4}
TRACKED = {'wordmark', 'fixture'}
S = 200


def word_lefts(lum, box, size, words):
    """Ink left edge of each word in the concept: column runs of ink, merged across gaps smaller than
    0.15 em. Returns None when the run count does not match the word count."""
    x0, y0, x1, y1 = box
    sub = lum[y0:y1, x0:x1]
    fl = np.percentile(sub, 30)
    cols = ((sub - fl) > 40).any(axis=0)
    runs = []
    i = 0
    while i < len(cols):
        if cols[i]:
            j = i
            while j < len(cols) and cols[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged = []
    gap = 0.15 * size
    for r in runs:
        if merged and r[0] - merged[-1][1] < gap:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    if len(merged) != len(words):
        return None
    return [x0 + m[0] for m in merged]


def ink_left(font, text):
    """Left ink offset (in S units, from the origin) of a string, measured on a rendered mask; PIL's bbox
    starts at the origin, not at the first ink pixel."""
    w = int(font.getlength(text)) + 2 * S
    canvas = Image.new('L', (w, 2 * S), 0)
    ImageDraw.Draw(canvas).text((S, S), text, font=font, fill=255, anchor='ls')
    cols = np.nonzero(np.asarray(canvas).max(axis=0) > 60)[0]
    return float(cols[0] - S) if len(cols) else 0.0


def load_layout(path):
    raw = open(path, encoding='utf-8').read()
    return json.loads(raw[raw.index('{'): raw.rindex('}') + 1])


def font_at(path, wght):
    f = ImageFont.truetype(path, S)
    axes = f.get_variation_axes()
    f.set_variation_by_axes([14, wght] if len(axes) == 2 else [wght])
    return f


def main():
    layout = load_layout(sys.argv[1])
    fonts = json.load(open(sys.argv[2], encoding='utf-8'))
    concept = np.asarray(Image.open(sys.argv[3]).convert('L'), dtype=np.float32)
    offsets = json.load(open(sys.argv[5], encoding='utf-8')) if len(sys.argv) > 5 else {}
    out = {}
    for key, (family, text) in SPEC.items():
        x0, y0, x1, y1 = layout['text'][key]['box']
        path = fonts[family]['file']
        base = font_at(path, WEIGHT[key])
        l, t, r, b = base.getbbox(text, anchor='ls')
        k = (y1 - y0) / float(b - t)
        l = ink_left(base, text)
        size = S * k
        n = len(text)
        ls = ((x1 - x0) - (r - l) * k) / max(1, n - 1)
        if key in MIN_TAPPABLE:
            size = max(size, MIN_TAPPABLE[key])
            ls = 0.0
        elif key not in TRACKED:
            ls = max(min(ls, 6.0), -6.0)
        wght = WEIGHT[key]
        f = font_at(path, wght)
        l, t, r, b = f.getbbox(text, anchor='ls')
        l = ink_left(f, text)
        k = size / S
        dx, dy, dls = (offsets.get(key, [0, 0, 0]) + [0])[:3]
        ls += dls
        words = None
        if key not in MIN_TAPPABLE and key not in TRACKED:
            parts = text.split(' ')
            lefts = word_lefts(concept, layout['text'][key]['box'], size, parts)
            if lefts is not None and len(parts) > 1:
                f = font_at(path, wght)
                words = []
                for part, left in zip(parts, lefts):
                    words.append([part, round(left - ink_left(f, part) * k, 2)])
        out[key] = {
            'family': family, 'weight': wght, 'text': text,
            'size': round(size, 2), 'ls': round(ls, 2),
            'x': round(x0 - l * k + dx, 2), 'y': round(y0 - t * k + dy, 2),
        }
        if words:
            out[key]['words'] = words
    with open(sys.argv[4], 'w', encoding='utf-8') as fh:
        fh.write('/* Generated by tools/fit_type.py from the concept ink boxes. Do not edit by hand. */\n')
        fh.write('window.ARCHEUS_TYPE = ' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n')
    for key, v in out.items():
        print('%-18s size %6.2f  ls %6.2f  wght %d  x %7.2f  y %7.2f' % (key, v['size'], v['ls'], v['weight'], v['x'], v['y']))


if __name__ == '__main__':
    main()
