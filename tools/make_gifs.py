"""Dev-only: render a promo GIF of the architecture graph — a faithful preview
of the live HTML canvas (rotating geodesic wireframe cages, per-cluster bubbles,
glowing curved edges, flowing particles on a dark neural field). NOT a runtime
dependency and NOT a screen recording — it recreates the graph's look from a
small example structure (archeus's own module names; no user data).

    py tools/make_gifs.py

Requires Pillow. Writes docs/graph.gif.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs')
W, H = 720, 400
FRAMES = 44
BG_TOP = (10, 16, 30)
BG_BOT = (3, 5, 11)

# example workspace: clusters (project modules) → nodes, sized by "importance"
CLUSTERS = [
    ('memory',      (200, 150), (125, 211, 252), [('recall', 15), ('lessons', 11),
                                                  ('graph', 9), ('digest', 7)]),
    ('connections', (500, 130), (138, 180, 248), [('hierarchy', 14), ('deps', 10),
                                                  ('render', 8)]),
    ('ui',          (250, 300), (167, 139, 250), [('menu', 12), ('hub', 9),
                                                  ('themes', 7), ('pager', 6)]),
    ('agents',      (520, 310), (94, 234, 212),  [('suggest', 10), ('library', 8),
                                                  ('hooks', 6)]),
]
# dependency edges between node labels (for glow curves + particles)
EDGES = [('recall', 'graph'), ('recall', 'lessons'), ('graph', 'hierarchy'),
         ('hierarchy', 'deps'), ('deps', 'render'), ('menu', 'hub'),
         ('hub', 'recall'), ('suggest', 'graph'), ('hub', 'themes'),
         ('library', 'hooks'), ('digest', 'recall'), ('menu', 'suggest')]

# The geodesic icosahedral cage: 42 vertices, 120 edges. Same swap as the GUI
# stage and the real graph — notes/constellation-study.md. Faces are derived from
# adjacency rather than a hardcoded list, so the base solid is stated once.
PHI = 1.6180339887


def _nrm(v):
    L = math.sqrt(sum(c * c for c in v))
    return tuple(c / L for c in v)


_IV = [_nrm(v) for v in
       [(0, 1, PHI), (0, 1, -PHI), (0, -1, PHI), (0, -1, -PHI),
        (1, PHI, 0), (1, -PHI, 0), (-1, PHI, 0), (-1, -PHI, 0),
        (PHI, 0, 1), (PHI, 0, -1), (-PHI, 0, 1), (-PHI, 0, -1)]]
_MN = min(math.dist(_IV[i], _IV[j]) for i in range(12) for j in range(i + 1, 12))
#: the BASE icosahedron's own 30 edges — the small-hull level of detail below.
_LE = [(i, j) for i in range(12) for j in range(i + 1, 12)
       if math.dist(_IV[i], _IV[j]) < _MN * 1.1]
_DV, _DE = [], []


def _build_cage():
    mn = _MN
    idx, seen = {}, set()

    def put(v):
        k = tuple(round(c, 4) for c in v)
        if k not in idx:
            idx[k] = len(_DV)
            _DV.append(v)
        return idx[k]

    def edge(a, b):
        k = (min(a, b), max(a, b))
        if k not in seen:
            seen.add(k)
            _DE.append(k)

    def mid(a, b):
        return _nrm(tuple(a[c] + b[c] for c in range(3)))

    for i in range(12):
        for j in range(i + 1, 12):
            if math.dist(_IV[i], _IV[j]) > mn * 1.1:
                continue
            for k in range(j + 1, 12):
                if (math.dist(_IV[i], _IV[k]) > mn * 1.1
                        or math.dist(_IV[j], _IV[k]) > mn * 1.1):
                    continue
                a, b, c = _IV[i], _IV[j], _IV[k]
                ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
                for tri in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)):
                    p = [put(v) for v in tri]
                    edge(p[0], p[1]); edge(p[1], p[2]); edge(p[2], p[0])


_build_cage()
assert (len(_DV), len(_DE)) == (42, 120), (len(_DV), len(_DE))
assert (len(_IV), len(_LE)) == (12, 30), (len(_IV), len(_LE))

#: Apparent radius, in pixels, at which a hull can carry the subdivided cage.
#: This frame is a fixed 720x400 render with no zoom, so a node's radius IS its
#: apparent size — the equivalent of `r*view.k` in `connections.drawCluster`.
BIG_PX = 20


def _bg():
    img = Image.new('RGB', (W, H))
    px = img.load()
    cx, cy = W / 2, H / 2
    maxd = math.hypot(cx, cy)
    for y in range(H):
        for x in range(0, W, 2):
            t = math.hypot(x - cx, y - cy) / maxd
            c = tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3))
            px[x, y] = c
            if x + 1 < W:
                px[x + 1, y] = c
    return img


def _positions():
    pos = {}
    for _name, (cx, cy), col, nodes in CLUSTERS:
        n = len(nodes)
        for k, (lbl, imp) in enumerate(nodes):
            a = 2 * math.pi * k / n
            r = 46 + n * 4
            pos[lbl] = (cx + math.cos(a) * r, cy + math.sin(a) * r, imp, col)
    return pos


def _cluster(draw, x, y, rad, col, T, ph):
    """One node: a wireframe cage holding an interior population.

    LEVEL OF DETAIL, by apparent size — the same call `connections.drawCluster`
    makes, and the one thing that decides whether this reads as a cage or as a
    solid ball. 120 struts over a 15px hull put an edge every 2px and paint a
    filled disc, so the subdivided cage (42v/120e) is for the hulls that can
    carry it and the base icosahedron (12v/30e) is for the rest. The joints are
    sized in pixels and capped at both ends for the same reason: one that grows
    with the hull turns a large cage into a ring of blobs, and one that does not
    shrink turns a small cage into a burr.
    """
    ax, ay = T * 0.9 + ph, T * 0.66 + ph * 1.7
    ca, sa, cb, sb = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay)

    def rot(v):
        x1 = v[0] * cb + v[2] * sb
        z1 = -v[0] * sb + v[2] * cb
        # third value is the depth cue — the far side of a hull is dimmer, which
        # is most of what stops a wireframe sphere reading as a flat disc
        return x1, v[1] * ca - z1 * sa, 0.55 + 0.45 * (v[1] * sa + z1 * ca + 1) / 2

    def shade(f):
        return tuple(min(255, int(c * f)) for c in col)

    big = rad >= BIG_PX
    GV, GE = (_DV, _DE) if big else (_IV, _LE)
    P = [(x + p[0] * rad, y + p[1] * rad, p[2]) for p in (rot(v) for v in GV)]
    # struts are filaments and dimmer than the joints; a denser cage has to be
    # dimmer still, or its 120 lines sum to a fill
    k = 0.58 if big else 1.0
    for i, j in GE:
        draw.line([P[i][:2], P[j][:2]],
                  fill=shade(k * (P[i][2] + P[j][2]) / 2), width=1)
    # the interior population — a cluster is made of clusters. Big hulls only:
    # below that it is noise rather than structure.
    if big:
        cnt = min(56, int(rad * 1.8))
        for m in range(cnt):
            yy = 1 - 2 * (m + 0.5) / cnt
            ring = math.sqrt(max(0.0, 1 - yy * yy))
            th = m * 2.399963
            hr = ((m * 7919 + 13) % 2333) / 2333
            r2 = 0.55 * rad * hr ** 0.45
            mx, my, ms = rot((math.cos(th) * ring, yy, math.sin(th) * ring))
            draw.point((x + mx * r2, y + my * r2), fill=shade(0.45 + 0.5 * ms))
    # a white core inside a coloured node, not a coloured dot
    vr = min(1.7, max(0.9, rad * 0.055))
    for pxp, pyp, ps in P:
        draw.ellipse([pxp - vr, pyp - vr, pxp + vr, pyp + vr],
                     fill=shade(0.6 + 0.4 * ps))
        if vr >= 1.2:
            draw.point((pxp, pyp), fill=(255, 255, 255))


def _qpt(a, b, t):
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    nx, ny = -(b[1] - a[1]), (b[0] - a[0])
    L = math.hypot(nx, ny) or 1
    cx, cy = mx + nx / L * 26, my + ny / L * 26
    u = 1 - t
    return (u * u * a[0] + 2 * u * t * cx + t * t * b[0],
            u * u * a[1] + 2 * u * t * cy + t * t * b[1])


def _frame(fi, base, pos):
    T = fi / FRAMES * 2 * math.pi
    img = base.copy()
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    # cluster bubbles
    for _name, (cx, cy), col, nodes in CLUSTERS:
        rr = 60 + len(nodes) * 8
        gd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                   fill=(col[0], col[1], col[2], 16))
    # edges + node halos on the glow layer
    for a, b in EDGES:
        if a in pos and b in pos:
            pa, pb = pos[a][:2], pos[b][:2]
            pts = [_qpt(pa, pb, k / 12) for k in range(13)]
            gd.line(pts, fill=(150, 190, 255, 60), width=1)
    for lbl, (x, y, imp, col) in pos.items():
        r = 6 + imp * 1.6
        halo = int(r * 2.4)
        gd.ellipse([x - halo, y - halo, x + halo, y + halo],
                   fill=(col[0], col[1], col[2], 40))
    glow = glow.filter(ImageFilter.GaussianBlur(7))
    img = Image.alpha_composite(img.convert('RGBA'), glow)

    d = ImageDraw.Draw(img)
    # flow particles
    for ei, (a, b) in enumerate(EDGES):
        if a in pos and b in pos:
            t = ((fi / FRAMES) * 1.4 + ei * 0.13) % 1.0
            px_, py_ = _qpt(pos[a][:2], pos[b][:2], t)
            d.ellipse([px_ - 2, py_ - 2, px_ + 2, py_ + 2], fill=(210, 235, 255))
    # rotating cages + labels
    for lbl, (x, y, imp, col) in pos.items():
        r = 6 + imp * 1.5
        _cluster(d, x, y, r, col, T, hash(lbl) % 100 / 10.0)
        d.text((x + r + 3, y - 5), lbl, fill=(200, 214, 235))
    # title
    d.text((16, 14), "archeus  architecture graph", fill=(150, 190, 255))
    return img.convert('RGB')


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    base = _bg()
    pos = _positions()
    frames = [_frame(i, base, pos) for i in range(FRAMES)]
    # MAXCOVERAGE, not MEDIANCUT: median-cut splits the colour cube by pixel
    # POPULATION, and this frame is overwhelmingly dark blue — so the four
    # per-cluster accents, which are exactly what the picture is about, get
    # merged into the blue and every cage comes out the same pale hue. Measured:
    # the agents cluster's #5EEAD4 landed on (138,203,222) under median cut and
    # on (93,233,211) under max coverage, at the same 128 colours. Max coverage
    # then spends its bins on colour SPREAD, so a 128-entry palette bands the
    # soft cluster bubbles into contour rings — the full 256 buys them back and
    # the file is still lighter than the median-cut 128 it replaces.
    frames = [f.quantize(colors=256, method=Image.MAXCOVERAGE) for f in frames]
    out = os.path.join(OUT_DIR, 'graph.gif')
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=70, loop=0, optimize=True, disposal=2)
    print(f"wrote {out}  ({os.path.getsize(out) // 1024} KB, {FRAMES} frames)")


if __name__ == '__main__':
    main()
