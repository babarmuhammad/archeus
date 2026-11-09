"""R2 in a real browser against a real Core (ADR-0025 §1-2, rulebook §12, §20
and §25, X-20): the graph's legend, expand all / collapse all, and the plain
tier words. The legend lists what the loaded picture holds, as a list of real
checkboxes over swatches the renderer's own marks are drawn into; unticking a
row hides it from the drawing and from nothing else; the two whole-graph
commands reach the same states by button and by key, twice as once; none of
it asks Core anything, moves the URL or stores anything. Mutation-verified by
tools/mutate_p19_5.py (N89-N102)."""

import time

from .conftest import wait
from .test_spa_p16 import Checks, _go, _mission, _open, _settled
from .test_spa_p18 import _find, _graph

ENUMS = ('EXTRACTED', 'INFERRED', 'AMBIGUOUS', 'extracted', 'inferred', 'ambiguous')


def _key(n):
    return ('path:' if n['kind'] in ('path', 'directory', 'file') else n['kind'] + ':') + n['id']


def _top(read):
    """The nodes drawn with nothing expanded: those with no loaded parent."""
    loaded = {_key(n) for n in read['nodes']}
    return {_key(n) for n in read['nodes'] if not (n.get('parent') and _key(n['parent']) in loaded and _key(n['parent']) != _key(n))}


def _n(g):
    return int(g.get_attribute('data-graph-nodes'))


def _lesson(tc, mid, title, **promote):
    r = tc.http('POST', '/v1/feedback', body={'subject': {'kind': 'mission', 'id': mid}, 'signal': 'correction',
                                              'text': title, 'idempotency_key': 'fb-%s-%f' % (title, time.time()),
                                              'promote': dict(promote, type='LESSON', title=title)})
    assert r.status == 200, r.body
    return r.json()['promoted']['id']


def test_the_legend_and_the_whole_graph_commands(browser, core):
    check = Checks()
    mid = _mission(core, 'Draw the legend')
    _settled(core, mid, 'COMPLETED')
    read = core.http('GET', '/v1/world/graph?focus=mission:%s' % mid).json()
    kinds = {n['kind'] for n in read['nodes'] if not n.get('endpoint')}
    stubs = len(read.get('hidden') or [])
    total = len(read['nodes']) + stubs
    top = len(_top(read)) + sum(1 for h in read.get('hidden') or [] if _key(h['parent']) not in {_key(n) for n in read['nodes']})
    check(total > top, 'the mission graph has something to collapse')

    context, page, errors = _open(browser, core)
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    wait(page, lambda: g.get_attribute('data-graph-loop') == 'parked', what='idle')
    sent, stored = [], page.evaluate('() => JSON.stringify([{...localStorage}, {...sessionStorage}])')
    page.on('request', lambda r: sent.append((r.method, r.url)))
    hash_ = page.evaluate('location.hash')

    # ── the legend: what this picture holds, in words, as checkboxes ──
    legend = page.locator('[data-graph-legend]')
    check(legend.evaluate('d => d.open') and legend.locator('summary').inner_text() == 'Legend', 'the legend is open and titled')
    rows = legend.locator('li[data-legend]').evaluate_all('els => els.map(e => e.dataset.legend)')
    check({'kind:' + k for k in kinds} <= set(rows), 'every loaded kind has a row: %s' % rows)
    check(not [r for r in rows if r.startswith('kind:') and r[5:] not in kinds | {'endpoint', 'decision'}], 'no row for a kind not loaded')
    check([r for r in rows if r.startswith('tier:')] == ['tier:EXTRACTED'], 'only the tier the loaded edges carry')
    check(rows[-2:] == ['halo', 'marker'], 'the two marks of live work close the list')
    boxes = legend.locator('input[type=checkbox]')
    check(boxes.count() == len([r for r in rows if r.startswith(('kind:', 'tier:'))]), 'one real checkbox per shape and line row')
    check(all(boxes.nth(i).is_checked() for i in range(boxes.count())), 'everything shown to begin with')
    check(legend.locator('ul[aria-label]').count() == 3, 'shapes, lines and live work, each a labelled list')
    text = page.locator('.graph').inner_text()
    check('recorded' in legend.inner_text() and not any(w in text for w in ENUMS), 'the tier said in words, never the enum')
    inked = legend.locator('canvas.legend-swatch').evaluate_all('''cs => cs.map((c) => {
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
      for (let i = 3; i < d.length; i += 4) if (d[i]) n++; return n; })''')
    check(len(inked) == len(rows) and all(inked), 'every row has a drawn swatch: %s' % inked)
    check(legend.locator('canvas.legend-swatch[aria-hidden=true]').count() == len(rows), 'the swatches are decoration; the words carry it')

    # unticking a kind hides it from the drawing, not from the list
    execs = [_key(n) for n in read['nodes'] if n['kind'] == 'execution']
    check(execs, 'the mission ran an attempt')
    legend.locator('li[data-legend="kind:execution"] input').uncheck()
    wait(page, lambda: _n(g) == total - len(execs), what='executions hidden')
    check(g.get_attribute('data-graph-hidden') == '1', 'one row unticked')
    mirror = page.locator('[data-graph-mirror] li[data-key]').evaluate_all('els => els.map(e => e.dataset.key)')
    check(set(execs) <= set(mirror), 'the mirror still lists the hidden attempts')
    legend.locator('li[data-legend="kind:execution"] input').check()
    wait(page, lambda: _n(g) == total, what='executions back')
    legend.locator('li[data-legend="tier:EXTRACTED"] input').uncheck()
    wait(page, lambda: g.get_attribute('data-graph-hidden') == '1', what='a tier unticked')
    check(_n(g) == total, 'unticking a line hides edges, never a node')
    legend.locator('li[data-legend="tier:EXTRACTED"] input').check()

    # ── expand all / collapse all: by button, by key, twice as once ──
    collapsible = int(g.get_attribute('data-graph-collapsible'))
    check(_n(g) == total and int(g.get_attribute('data-graph-expanded')) == collapsible, 'opens expanded')
    bar = page.locator('.graph-bar')
    for _ in range(2):
        bar.get_by_role('button', name='Collapse all').click()
        wait(page, lambda: _n(g) == top, what='collapsed to the top')
        check(g.get_attribute('data-graph-expanded') == '0', 'nothing expanded')
    at = g.get_attribute('data-graph-at')
    check(at in _top(read), 'the keyboard stands on a drawn node after the collapse (%s)' % at)
    for _ in range(2):
        bar.get_by_role('button', name='Expand all').click()
        wait(page, lambda: _n(g) == total, what='expanded')
        check(int(g.get_attribute('data-graph-expanded')) == collapsible, 'everything with children expanded')
    attempt = next(n for n in read['nodes'] if n['kind'] == 'execution')
    _find(page, attempt['label'])
    wait(page, lambda: g.get_attribute('data-graph-at') == _key(attempt), what='the keyboard on the attempt')
    page.focus('canvas.graph-canvas')
    page.keyboard.press('c')
    wait(page, lambda: _n(g) == top, what='C collapses')
    check(g.get_attribute('data-graph-at') in _top(read), 'the collapse hid the attempt: the keyboard moved to what stands for it')
    page.keyboard.press('Space')                # one node's own toggle still works
    wait(page, lambda: _n(g) > top, what='Space opens the focused node')
    check(_n(g) < total and g.get_attribute('data-graph-expanded') == '1', 'partly expanded: one node open')
    page.keyboard.press('e')
    wait(page, lambda: _n(g) == total, what='E expands all from a partial picture')
    page.keyboard.press('e')
    page.wait_for_timeout(200)
    check(_n(g) == total, 'E again changes nothing')

    # ── none of it was a request, a route or a write ──
    check(not [s for s in sent if s[0] != 'GET' or '/v1/' in s[1]], 'no request to Core: %s' % sent)
    check(page.evaluate('location.hash') == hash_, 'the URL did not move')
    check(page.evaluate('() => JSON.stringify([{...localStorage}, {...sessionStorage}])') == stored, 'nothing stored')
    check(core.http('GET', '/v1/missions/%s' % mid).json()['state'] == 'COMPLETED', 'the mission is as it was')
    assert not errors, errors
    context.close()

    # a relation with a tier, in the list and the graph: the word, never the enum
    first = _lesson(core, mid, 'Draw it once')
    second = _lesson(core, mid, 'Draw it twice', supersedes_id=first)
    context, page, errors = _open(browser, core)
    _go(page, '#/o/knowledge_item/%s/relations' % second)
    tier = page.locator('.rel-list .tier').first
    tier.wait_for(timeout=15000)
    check(tier.inner_text().strip() == 'recorded' and tier.get_attribute('data-style') == 'solid', 'the Relations list says "recorded"')
    _go(page, '#/world/graph/knowledge_item/%s' % second)
    g = _graph(page)
    wait(page, lambda: page.locator('[data-graph-legend] li[data-legend="tier:EXTRACTED"]').count() == 1, what='the tier row')
    said = page.locator('[data-graph-mirror]').inner_text()
    check('(recorded)' in said and not any(w in said for w in ENUMS), 'the mirror says the word: %s' % said)
    assert not errors, errors
    context.close()

    # under reduced motion the legend describes the static live edge, not the marker
    context, page, errors = _open(browser, core, reduced_motion='reduce')
    _go(page, '#/world/graph/mission/%s' % mid)
    _graph(page)
    check('thicker line' in page.locator('[data-graph-legend] li[data-legend=marker]').inner_text(), 'reduced motion: the static edge')
    assert not errors, errors
    context.close()
    assert check.n >= 32, 'ran %d checks' % check.n
