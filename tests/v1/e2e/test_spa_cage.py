"""R12 in a real browser against a real Core: the static project cage
(ADR-0025 §4, rulebook §12, §36), read from the canvas's framebuffer — pixel
reads at known positions, not a screenshot.

At the world level a project drawn 48 px across or more is a 12-junction cage:
node ink at each junction, the background where its circle's outline would
be. Zoomed out below 48 px it is its circle again. It never rotates: the same
pixels later, and no frame drawn for it. Mutation-verified by
tools/mutate_p19_5.py. Check floors keep a test that silently checks nothing
from passing."""

import math
import os
import subprocess
import time

from .conftest import wait
from .test_spa_p16 import Checks, _go, _open
from .test_spa_p18 import _graph

R = 26                     # encoding.radiusOf('cluster')
PHI = (1 + 5 ** 0.5) / 2


def _cage():
    """The cage's unit junctions, as render.ts computes them."""
    v = []
    for a in (-1, 1):
        for b in (-PHI, PHI):
            v += [(0, a, b), (a, b, 0), (b, 0, a)]
    n = (PHI / 3, 0, (2 * PHI + 1) / 3)
    ln = math.hypot(*n)
    nx, nz = n[0] / ln, n[2] / ln
    flat = [(x * nz - z * nx, y) for x, y, z in v]
    r = max(math.hypot(*p) for p in flat)
    return [(x / r, y / r) for x, y in flat]


_INK = """([pts]) => {
  const c = document.querySelector('canvas.graph-canvas'), dpr = c.width / c.clientWidth;
  const [cx, cy] = c.dataset.at.split(',').map(Number), k = Number(c.dataset.zoom);
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  const at = (x, y) => { const o = (Math.round(y * dpr) * c.width + Math.round(x * dpr)) * 4; return [d[o], d[o + 1], d[o + 2]]; };
  const bg = at(4, 4);
  // the strongest ink within 1 px of each point: summed channel distance from the background
  return pts.map(([px, py]) => { let best = 0;
    for (const dx of [-1, 0, 1]) for (const dy of [-1, 0, 1]) {
      const p = at(cx + px * 26 * k + dx, cy + py * 26 * k + dy);
      best = Math.max(best, Math.abs(p[0] - bg[0]) + Math.abs(p[1] - bg[1]) + Math.abs(p[2] - bg[2])); }
    return best; });
}"""


def _project(core, home):
    root = os.path.join(str(home), 'atlas')
    os.makedirs(root, exist_ok=True)
    subprocess.run(['git', 'init', '-q', root], check=True)
    r = core.http('POST', '/v1/projects', body={'name': 'Atlas', 'root_paths': [root], 'idempotency_key': 'p-%f' % time.time()})
    assert r.status == 200, r.body
    return r.json()['project']['id']


def test_a_large_project_at_the_world_level_is_a_still_cage(browser, core, archeus_home):
    check = Checks()
    pid = _project(core, archeus_home)
    context, page, errors = _open(browser, core, viewport={'width': 1280, 'height': 900})
    _go(page, '#/world/graph')
    _graph(page)
    canvas = page.locator('canvas.graph-canvas')
    wait(page, lambda: canvas.get_attribute('data-at') and float(canvas.get_attribute('data-zoom') or 0) > 0,
         what='the project is drawn and placed')
    page.wait_for_timeout(500)
    k = float(canvas.get_attribute('data-zoom'))
    check(2 * R * k >= 48, 'drawn at least 48 px across: %.1f px' % (2 * R * k))
    cage = _cage()
    junctions = page.evaluate(_INK, [cage])
    check(all(v > 60 for v in junctions), 'node ink at all 12 junctions: %s' % junctions)
    # the rim between two outer junctions: where the circle's outline would be, the cage leaves background
    outer = sorted((math.atan2(y, x) for x, y in cage if abs(math.hypot(x, y) - 1) < 1e-6))
    gaps = [((outer[i] + outer[(i + 1) % len(outer)] + (2 * math.pi if i == len(outer) - 1 else 0)) / 2) for i in range(len(outer))]
    rim = [(math.cos(a), math.sin(a)) for a in gaps]
    empty = page.evaluate(_INK, [rim])
    check(len(rim) == 6 and all(v < 30 for v in empty), 'no circle outline: the background on the rim between junctions: %s' % empty)

    # never rotated: the same pixels later, and nothing drawn for it meanwhile
    layers = canvas.get_attribute('data-layers')
    page.wait_for_timeout(1500)
    check(page.evaluate(_INK, [cage]) == junctions, 'the same junction pixels 1.5 s later')
    check(canvas.get_attribute('data-layers') == layers, 'no layer redrawn: nothing about it moves')
    check(page.evaluate('() => document.getAnimations().length') == 0, 'no animation')

    # zoomed out below 48 px: its circle
    page.focus('canvas.graph-canvas')
    for _ in range(6):
        if 2 * R * float(canvas.get_attribute('data-zoom')) < 48:
            break
        page.keyboard.press('-')
        page.wait_for_timeout(400)
    k = float(canvas.get_attribute('data-zoom'))
    check(2 * R * k < 48, 'zoomed out: %.1f px across' % (2 * R * k))
    page.wait_for_timeout(400)
    ring = page.evaluate(_INK, [rim])
    check(sum(v > 60 for v in ring) >= 5, 'its circle\'s outline is drawn: %s' % ring)
    inner = [p for p in cage if math.hypot(*p) < 0.9]
    check(len(inner) == 6 and all(v < 30 for v in page.evaluate(_INK, [inner])), 'and no inner junction')

    # not at the world level: a project's own graph keeps its circle, however large
    _go(page, '#/world/graph/project/' + pid)
    _graph(page)
    wait(page, lambda: canvas.get_attribute('data-at') and 2 * R * float(canvas.get_attribute('data-zoom') or 0) >= 48,
         what='the project, large, in its own graph')
    page.wait_for_timeout(500)
    ring = page.evaluate(_INK, [rim])
    check(sum(v > 60 for v in ring) >= 5, 'its circle, not its cage, outside the world level: %s' % ring)
    check(not errors, errors)
    context.close()
    assert check.n >= 10
