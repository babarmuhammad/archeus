"""R3 in a real browser against a real Core (ADR-0025 §3-4, rulebook §12, §20,
§22, §24): the project hull read from the canvas's framebuffer (a pixel read,
not a screenshot) — present with drawn members, gone collapsed or unticked, an
outline under forced colours; "What does this affect?" entered and left by its
button and Esc, its count equal to a breadth-first search over the recorded
relations of Core's own read; the hull, depth and impact said in words in the
mirror; a running attempt's core of thread ink at its centre; and none of it a
request, a route or a write. Mutation-verified by tools/mutate_p19_5.py
(N103-N119)."""

import time

from v1.judge.support import FixtureRepo

from .conftest import wait
from .motion import freeze
from .test_spa_copy import leaks
from .test_spa_halo import _halo_view, _running
from .test_spa_p16 import Checks, _go, _mission, _open, _settled
from .test_spa_p18 import _graph, slow  # noqa: F401 (a fixture)

#: canvas pixels in the hull's tint — `--bg` mixed toward `--text` at hull or
#: hull-focus — counted on the framebuffer
_HULL = """() => {
  const c = document.querySelector('canvas.graph-canvas'), st = getComputedStyle(c);
  const hex = (v) => { const h = st.getPropertyValue(v).trim().replace('#', ''); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); };
  const bg = hex('--bg'), tx = hex('--text');
  const tints = [0.06, 0.1].map((a) => bg.map((b, i) => b + (tx[i] - b) * a));
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let n = 0;
  for (let o = 0; o < d.length; o += 4)
    if (tints.some((t) => Math.abs(d[o] - t[0]) + Math.abs(d[o + 1] - t[1]) + Math.abs(d[o + 2] - t[2]) <= 4)) n++;
  return n;
}"""

#: the pixel at the focused node's centre against thread ink: summed channel distance
_CORE = """() => {
  const c = document.querySelector('canvas.graph-canvas'), st = getComputedStyle(c);
  const h = st.getPropertyValue('--thread').trim().replace('#', ''), ink = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  const [x, y] = c.dataset.at.split(',').map(Number), dpr = c.width / c.clientWidth;
  const o = (Math.round(y * dpr) * c.width + Math.round(x * dpr)) * 4, d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  return Math.abs(d[o] - ink[0]) + Math.abs(d[o + 1] - ink[1]) + Math.abs(d[o + 2] - ink[2]);
}"""


def _key(r):
    return ('path:' if r['kind'] in ('path', 'directory', 'file') else r['kind'] + ':') + r['id']


def _affected(read, start, hops):
    """Core's read, searched as ADR-0025 §3 says: recorded relations, both ways, within *hops*."""
    loaded = {_key(n) for n in read['nodes']}
    adj = {}
    for e in read['edges']:
        if e.get('tier') not in (None, 'EXTRACTED'):
            continue
        a, b = _key(e['from']), _key(e['to'])
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    seen, ring = {start}, [start]
    for _ in range(hops):
        ring = [y for x in ring for y in adj.get(x, []) if y in loaded and not (y in seen or seen.add(y))]
    return seen - {start}


def _project_with_work(core, archeus_home):
    repo = FixtureRepo.create('layered-python', str(archeus_home.parent))
    r = core.http('POST', '/v1/projects', body={'name': 'Atlas', 'root_paths': [repo.path], 'idempotency_key': 'prj-%f' % time.time()})
    assert r.status == 200, r.body
    pid = r.json()['project']['id']
    r = core.http('POST', '/v1/missions', body={'title': 'Chart the hull', 'objective': 'Tests pass', 'project_id': pid,
                                                'idempotency_key': 'm-%f' % time.time()})
    assert r.status == 200, r.body
    _settled(core, r.json()['id'], 'COMPLETED')
    return pid


def test_the_hull_and_what_this_affects(browser, core, archeus_home):
    check = Checks()
    pid = _project_with_work(core, archeus_home)
    read = core.http('GET', '/v1/world/graph?focus=project:%s' % pid).json()
    root = 'project:%s' % pid
    context, page, errors = _open(browser, core)
    _go(page, '#/world/graph/project/%s' % pid)
    g = _graph(page)
    canvas = page.locator('canvas.graph-canvas')
    wait(page, lambda: g.get_attribute('data-graph-loop') == 'parked', what='idle')
    sent, stored = [], page.evaluate('() => JSON.stringify([{...localStorage}, {...sessionStorage}])')
    page.on('request', lambda r: sent.append((r.method, r.url)))
    hash_ = page.evaluate('location.hash')

    # ── the hull: a filled volume under the project's drawn members ──
    check(canvas.get_attribute('data-hulls') == '1', 'one project, one hull')
    tinted = page.evaluate(_HULL)
    check(tinted > 2000, 'the hull is on the canvas: %d tinted pixels' % tinted)
    page.locator('.graph-bar').get_by_role('button', name='Collapse all').click()
    wait(page, lambda: canvas.get_attribute('data-hulls') == '0', what='a collapsed project has no hull')
    check(page.evaluate(_HULL) < tinted / 10, 'collapsed: the volume is gone from the canvas')
    page.locator('.graph-bar').get_by_role('button', name='Expand all').click()
    wait(page, lambda: canvas.get_attribute('data-hulls') == '1', what='the hull is back')
    legend = page.locator('[data-graph-legend]')
    legend.locator('li[data-legend="kind:project"] input').uncheck()
    wait(page, lambda: canvas.get_attribute('data-hulls') == '0', what='the project unticked: no hull')
    legend.locator('li[data-legend="kind:project"] input').check()
    wait(page, lambda: canvas.get_attribute('data-hulls') == '1', what='ticked again')
    check(legend.locator('li[data-legend]').evaluate_all('els => els.map(e => e.dataset.legend)')[-2:] == ['halo', 'marker'], 'the legend gained no row')

    # ── depth and hull in words: the mirror ──
    mission = next(n for n in read['nodes'] if n['kind'] == 'mission')
    row = page.locator('[data-graph-mirror] li[data-key="%s"]' % _key(mission)).first.inner_text()
    check('in project Atlas' in row and '1 step from Atlas' in row, 'the mirror: %s' % row)

    # ── "What does this affect?": entered by its button, left by it and by Esc ──
    button = page.locator('.graph-bar').get_by_role('button', name='What does this affect?')
    check(button.get_attribute('aria-pressed') == 'false' and g.get_attribute('data-graph-impact') == '', 'off to begin with')
    button.click()
    want = _affected(read, root, 2)
    check(want, 'the project affects something recorded')
    wait(page, lambda: g.get_attribute('data-graph-impact') == str(len(want)), what='the impact count')
    line = page.locator('[data-graph-impact-line]').inner_text()
    check('affects %d objects within 2 steps' % len(want) in line and 'recorded relations in this loaded view only' in line, line)
    check(button.get_attribute('aria-pressed') == 'true', 'the toggle says it is on')
    hit = page.locator('[data-graph-mirror] li[data-key]').evaluate_all(
        "els => els.filter(e => e.textContent.includes('affected, ')).map(e => e.dataset.key)")
    check(set(hit) == want, 'the mirror lists exactly what is affected: %s' % hit)
    page.locator('.graph-bar select[aria-label="How many steps"]').select_option('1')
    one = _affected(read, root, 1)
    wait(page, lambda: g.get_attribute('data-graph-impact') == str(len(one)), what='within 1 step')
    check(not leaks(page.locator('.graph').inner_text() + page.locator('[data-graph-mirror]').inner_text()), 'no id, JSON or hash')
    page.focus('canvas.graph-canvas')
    page.keyboard.press('Escape')
    wait(page, lambda: g.get_attribute('data-graph-impact') == '', what='Esc leaves the impact view')
    check(page.locator('[data-graph-impact-line]').count() == 0 and button.get_attribute('aria-pressed') == 'false', 'off: no line, not pressed')
    button.click()
    wait(page, lambda: g.get_attribute('data-graph-impact') != '', what='on again')
    page.locator('.graph-bar').get_by_role('button', name='Collapse all').click()
    wait(page, lambda: canvas.get_attribute('data-hulls') == '0', what='collapsed with the impact view on')
    at = g.get_attribute('data-graph-at')
    check(at == root and g.get_attribute('data-graph-impact') == str(len(_affected(read, root, 2))), 'the focus stays drawn; the impact still counts what it affects')
    button.click()
    wait(page, lambda: g.get_attribute('data-graph-impact') == '', what='the button leaves it')

    # ── none of it was a request, a route or a write ──
    check(not [s for s in sent if s[0] != 'GET' or '/v1/' in s[1]], 'no request to Core: %s' % sent)
    check(page.evaluate('location.hash') == hash_, 'the URL did not move')
    check(page.evaluate('() => JSON.stringify([{...localStorage}, {...sessionStorage}])') == stored, 'nothing stored')
    assert not errors, errors
    context.close()

    # forced colours: every alpha opaque — the hull is an outline, never a fill;
    # reduced motion changes none of R3's static marks
    for opts, filled in (({'forced_colors': 'active'}, False), ({'reduced_motion': 'reduce'}, True)):
        context, page, errors = _open(browser, core, **opts)
        _go(page, '#/world/graph/project/%s' % pid)
        g = _graph(page)
        wait(page, lambda g=g: g.get_attribute('data-graph-loop') == 'parked', what='idle')
        c = page.locator('canvas.graph-canvas')
        check(c.get_attribute('data-hulls') == '1', '%s: the hull is drawn' % opts)
        n = page.evaluate(_HULL)
        check((n > 2000) == filled, '%s: %d tinted pixels' % (opts, n))
        assert not errors, errors
        context.close()
    assert check.n >= 20, 'ran %d checks' % check.n


def test_a_running_attempt_is_cored(browser, slow):  # noqa: F811
    check = Checks()
    mid = _mission(slow, 'Core')
    ex = _running(slow, mid)
    context, page, errors = _open(browser, slow)
    freeze(page)
    g = _halo_view(page, mid, ex['label'], check, 'cored')
    check(g.get_attribute('data-graph-at') == 'execution:%s' % ex['id'], 'the running attempt is focused')
    check(page.evaluate(_CORE) < 30, 'its centre is thread ink: distance %d' % page.evaluate(_CORE))
    assert not errors, errors
    context.close()
    assert check.n >= 2
