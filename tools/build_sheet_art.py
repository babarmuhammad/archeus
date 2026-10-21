"""Build the base art and the live-layout data for a phone sheet frame (round 10f: phone-2 decision, phone-3 chat).

usage: py -I tools/build_sheet_art.py <concept.png> <trace.json> <name> <sheet_top> [out_dir]

  <trace.json>  tools/trace_phone2.json or tools/trace_phone3.json: the text windows, marks and controls to remove
  <name>        'phone-2' or 'phone-3' (file names in clients/v2-prototype/art/)
  <sheet_top>   the y (concept units) of the sheet's top edge; everything below it is the sheet, not scene

Steps: trace_concept.py removes the live text, marks and controls and writes the layout anchors; the sheet
area below sheet_top is then replaced by the page background (the median of the band just above the sheet,
per column), because the sheet is the one tinted translucent element and is drawn live; fit_type.py fits the
text to the concept ink (spec in tools/<name>-spec.json); the art is written as lossy WebP at quality 100.
"""
import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fit_glow  # noqa: E402
REPO = os.path.dirname(HERE)
PROTO = os.path.join(REPO, 'clients', 'v2-prototype')


def run(args):
    print('>', ' '.join(args))
    subprocess.run([sys.executable, '-I'] + args, check=True)


def fill_sheet(art, sheet_top):
    """Replace rows from sheet_top down by the page background: per column, the median of the dark pixels in the
    40 rows above the sheet, held constant down the sheet (the page background is almost flat there)."""
    band = art[sheet_top - 40:sheet_top - 2].astype(np.float32)
    lum = band.mean(axis=2)
    out = art.copy()
    cols = np.zeros((art.shape[1], 3), np.float32)
    for x in range(art.shape[1]):
        m = lum[:, x] < 45
        cols[x] = np.median(band[m, x], axis=0) if m.sum() >= 5 else np.median(band[:, x], axis=0)
    # smooth the column profile so no seam shows
    cols = cv2.GaussianBlur(cols.reshape(1, -1, 3), (0, 0), 30).reshape(-1, 3)
    out[sheet_top - 1:] = np.clip(cols, 0, 255).astype(np.uint8)[None, :, :]
    return out


def main():
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    concept, trace_cfg, name, sheet_top = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    out_dir = sys.argv[5] if len(sys.argv) > 5 else os.path.join(PROTO, 'art')
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='sheet-art-')
    art_png = os.path.join(tmp, 'art.png')
    layout = os.path.join(out_dir, name + '-layout.js')
    type_js = os.path.join(out_dir, name + '-type.js')
    webp = os.path.join(out_dir, name + '-base.webp')
    fonts = os.path.join(tmp, 'fonts.json')
    with open(fonts, 'w', encoding='utf-8') as fh:
        json.dump({'serif': {'file': os.path.join(PROTO, 'fonts', 'LibreCaslonText-VF.ttf')},
                   'sans': {'file': os.path.join(PROTO, 'fonts', 'Inter-VF.ttf')}}, fh)
    run([os.path.join(HERE, 'trace_concept.py'), os.path.abspath(concept), os.path.abspath(trace_cfg), art_png, layout])
    art = cv2.imread(art_png)
    art = fill_sheet(art, sheet_top)
    cfg = json.load(open(trace_cfg, encoding='utf-8'))
    concept_bgr = cv2.imread(concept)
    rgb = concept_bgr[:, :, ::-1].astype(np.float32)
    lum = rgb.mean(axis=2)
    bg = fit_glow.background(rgb, lum < 45)
    sil = fit_glow.silhouettes(rgb, lum, cfg['glow_boxes'])
    glows = {}
    colours = {'amber_diamond': (246, 188, 78), 'blue_star': (111, 177, 255)}
    for key, box in cfg['glow_boxes'].items():
        glows[key] = fit_glow.fit(key, sil[key], colours[key], rgb, lum, bg)
        glows[key]['box'] = box
    art = fit_glow.subtract(art, concept_bgr, glows, 0)
    cv2.imwrite(webp, art, [cv2.IMWRITE_WEBP_QUALITY, 100])
    spec = os.path.join(HERE, name + '-spec.json')
    run([os.path.join(HERE, 'fit_type.py'), layout, fonts, os.path.abspath(concept), type_js, '-', spec])
    # each frame gets its own globals (window.PH2_LAYOUT, window.PH2_TYPE, ...) so the frames load together
    prefix = 'PH' + name.split('-')[-1]
    for path in (layout, type_js):
        text = open(path, encoding='utf-8').read()
        text = text.replace('window.ARCHEUS_LAYOUT', 'window.%s_LAYOUT' % prefix).replace('window.ARCHEUS_TYPE', 'window.%s_TYPE' % prefix)
        open(path, 'w', encoding='utf-8').write(text)
    # the measured glows ride in the layout, so the live layer draws the same blur and strength the art was cleaned of
    text = open(layout, encoding='utf-8').read()
    head, body = text.split('=', 1)
    data = json.loads(body.strip().rstrip(';'))
    data['glows'] = glows
    open(layout, 'w', encoding='utf-8').write(head + '= ' + json.dumps(data, separators=(',', ':')) + ';' + chr(10))
    print('wrote', webp, os.path.getsize(webp), 'bytes')


if __name__ == '__main__':
    main()
