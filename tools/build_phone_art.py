"""Rebuild the phone Overview's art and live-layout data from the concept master.

usage: py -I tools/build_phone_art.py <concept.png> [out_dir]

Writes into clients/v2-prototype/art/ (default out_dir):
  phone-1-base.webp   the concept with every live element removed, extended above and below by its edge rows
  phone-1-layout.js   measured anchors (ink boxes of text, marks and controls), from trace_concept.py
  phone-1-type.js     live text sizes, tracking, weights and origins, from fit_type.py

Steps: trace_concept.py (config tools/trace_phone.json), fit_type.py (offsets tools/type_offsets.json), then the
WebP encode at quality 100 (lossy WebP; a lossless WebP is 618 KB, over the 400 KB budget). Run tools/compare_frame.py afterwards to check the frame against the master.
"""
import json
import os
import subprocess
import sys
import tempfile

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fit_glow  # noqa: E402
REPO = os.path.dirname(HERE)
PROTO = os.path.join(REPO, 'clients', 'v2-prototype')


def run(args):
    print('>', ' '.join(args))
    subprocess.run([sys.executable, '-I'] + args, check=True)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    concept = os.path.abspath(sys.argv[1])
    out_dir = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(PROTO, 'art')
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='phone-art-')
    art_png = os.path.join(tmp, 'art.png')
    layout = os.path.join(out_dir, 'phone-1-layout.js')
    type_js = os.path.join(out_dir, 'phone-1-type.js')
    webp = os.path.join(out_dir, 'phone-1-base.webp')
    fonts = os.path.join(tmp, 'fonts.json')
    with open(fonts, 'w', encoding='utf-8') as fh:
        json.dump({'serif': {'file': os.path.join(PROTO, 'fonts', 'LibreCaslonText-VF.ttf')},
                   'sans': {'file': os.path.join(PROTO, 'fonts', 'Inter-VF.ttf')}}, fh)
    run([os.path.join(HERE, 'trace_concept.py'), concept, os.path.join(HERE, 'trace_phone.json'), art_png, layout])
    run([os.path.join(HERE, 'fit_type.py'), layout, fonts, concept, type_js, os.path.join(HERE, 'type_offsets.json')])
    art = cv2.imread(art_png)
    cfg = json.load(open(os.path.join(HERE, 'trace_phone.json'), encoding='utf-8'))
    art = fit_glow.subtract(art, cv2.imread(concept), cfg['glows'], cfg['pad'])
    cv2.imwrite(webp, art, [cv2.IMWRITE_WEBP_QUALITY, 100])
    print('wrote', webp, os.path.getsize(webp), 'bytes')


if __name__ == '__main__':
    main()
