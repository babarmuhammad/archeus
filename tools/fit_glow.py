"""Measure the soft glow around the phone Overview's marks in the concept raster.

usage: py -I tools/fit_glow.py <concept.png>

For each glowing silhouette (the amber diamond, the blue star), the glow is modelled as the silhouette blurred
with a Gaussian of sigma s and scaled by an amplitude a, laid over the local background in the glow's colour.
The per-pixel alpha of that colour is fitted against the concept: alpha = (pixel - background) . (colour -
background) / |colour - background|^2, over the pixels within 45 units of the silhouette that carry no ink
(luminance below 60). Prints the best sigma and amplitude per glow. The values go into tools/trace_phone.json
under "glows"; build_phone_art.py subtracts the same model from the art, and the live layer draws it back as
an SVG blur filter (round 10f), so the glow is not counted twice.
The Review button has no measurable outside glow in the concept (alpha within 0.01 out to 40 units), so it is
not in the list.
"""
import json
import sys

import cv2
import numpy as np
from scipy import ndimage


def background(rgb, dark, k=41):
    out = np.zeros_like(rgb)
    n = ndimage.uniform_filter(dark.astype(np.float32), k)
    for c in range(3):
        s = ndimage.uniform_filter(np.where(dark, rgb[:, :, c], 0.0), k)
        out[:, :, c] = s / np.maximum(n, 1e-3)
    return out


def silhouettes(rgb, lum, boxes):
    """The glowing silhouettes in concept units: the amber diamond (a filled rhombus in its box) and the blue star
    (the bright blue pixels in its box, closed and hole-filled). boxes: {'amber_diamond': [x0, y0, x1, y1], 'blue_star': [...]}"""
    H, W = lum.shape
    yy, xx = np.mgrid[0:H, 0:W]
    out = {}
    if 'amber_diamond' in boxes:
        x0, y0, x1, y1 = boxes['amber_diamond']
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        out['amber_diamond'] = (np.abs(xx - cx) / ((x1 - x0) / 2.0) + np.abs(yy - cy) / ((y1 - y0) / 2.0)) <= 1
    if 'blue_star' in boxes:
        x0, y0, x1, y1 = boxes['blue_star']
        win = np.zeros((H, W), bool)
        win[y0:y1, x0:x1] = True
        blue = (rgb[:, :, 2] > 170) & (rgb[:, :, 0] < 170) & win
        out['blue_star'] = ndimage.binary_fill_holes(ndimage.binary_closing(blue, iterations=2))
    return out


def subtract(art_bgr, concept_bgr, glows, pad):
    """Remove the measured glows from the art (BGR uint8, padded by `pad` rows top and bottom): the same model the
    live layer draws back, so no glow is counted twice."""
    rgb = concept_bgr[:, :, ::-1].astype(np.float32)
    lum = rgb.mean(axis=2)
    bg = background(rgb, lum < 45)
    sil = silhouettes(rgb, lum, {k: g['box'] for k, g in glows.items()})
    h = concept_bgr.shape[0]
    out = art_bgr[:, :, ::-1].astype(np.float32)
    for key, g in glows.items():
        a = g['amp'] * ndimage.gaussian_filter(sil[key].astype(np.float32), g['sigma'])
        out[pad:pad + h] -= a[..., None] * (np.asarray(g['colour'], np.float32) - bg)
    return np.clip(out, 0, 255).astype(np.uint8)[:, :, ::-1].copy()


def fit(name, sil, colour, rgb, lum, bg):
    C = np.asarray(colour, np.float32)
    D = C[None, None, :] - bg
    alpha = ((rgb - bg) * D).sum(axis=2) / np.maximum((D * D).sum(axis=2), 1)
    dist = ndimage.distance_transform_edt(~sil)
    ring = (dist > 0.5) & (dist < 45) & (lum < 60)
    best = None
    for s in np.arange(1.5, 25, 0.5):
        b = ndimage.gaussian_filter(sil.astype(np.float32), s)[ring]
        den = float((b * b).sum())
        if den <= 0:
            continue
        a = float((alpha[ring] * b).sum()) / den
        err = float(np.sqrt(((alpha[ring] - a * b) ** 2).mean()))
        if best is None or err < best[0]:
            best = (err, s, a)
    err, s, a = best
    print('%s: sigma %.1f amplitude %.3f rms %.4f' % (name, s, a, err))
    return {'sigma': s, 'amp': round(a, 3), 'colour': list(colour)}


def main():
    """usage: fit_glow.py <concept.png> <boxes.json> ; boxes.json maps 'amber_diamond' and 'blue_star' to boxes."""
    rgb = cv2.imread(sys.argv[1], cv2.IMREAD_COLOR)[:, :, ::-1].astype(np.float32)
    lum = rgb.mean(axis=2)
    bg = background(rgb, lum < 45)
    boxes = json.load(open(sys.argv[2], encoding='utf-8'))
    sil = silhouettes(rgb, lum, boxes)
    res = {}
    if 'amber_diamond' in sil:
        res['amber_diamond'] = fit('amber diamond', sil['amber_diamond'], (246, 188, 78), rgb, lum, bg)
        res['amber_diamond']['box'] = boxes['amber_diamond']
    if 'blue_star' in sil:
        res['blue_star'] = fit('blue star', sil['blue_star'], (111, 177, 255), rgb, lum, bg)
        res['blue_star']['box'] = boxes['blue_star']
    print(json.dumps(res))


if __name__ == '__main__':
    main()
