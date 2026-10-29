"""P18 in a real browser against a real Core (p18-design-gate §13, §16): the
drill world → project → mission → execution, Enter to the canonical inspector
and Back, zoom and fit and find by keyboard, the loop parking on a hidden page,
a lost context and reduced motion, the import graph, the 390 px list fallback,
axe-core and the overflow audit. A check floor keeps a suite that silently
checks nothing from passing."""

import os
import time

import pytest

from archeus.core import engine, ports, runtime
from archeus.harnesses.fake import FakeHarness
from claude_sessions import proc
from v1.judge.http import TempCore
from v1.judge.support import FixtureRepo

from .conftest import wait
from .test_spa_p16 import AXE, Checks, _go, _mission, _open, _settled

SLOW = {'work': [{'emit': {'type': 'working'}}, {'emit': {'type': 'working'}},
                 {'sleep': 1}, {'emit': {'type': 'working'}}, {'sleep': 30}]}


@pytest.fixture
def slow(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(SLOW),
        executors=[FakeHarness()])).start()
    yield tc
    for p in list(tc.core.manager._procs.values()):
        proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
    tc.stop(kill=True)


def _project(tc, archeus_home):
    repo = FixtureRepo.create('layered-python', os.path.dirname(str(archeus_home)))
    r = tc.http('POST', '/v1/projects', body={'name': 'Atlas', 'root_paths': [repo.path],
                                              'idempotency_key': 'prj-%f' % time.time()})
    assert r.status == 200, r.body
    return r.json()


def _graph(page):
    g = page.locator('.graph')
    g.wait_for(timeout=15000)
    return g


def _mirror(page):
    return page.locator('[data-graph-mirror] li[data-key]').evaluate_all(
        'els => els.map(e => e.dataset.key)')


def _find(page, text):
    page.focus('canvas.graph-canvas')
    page.keyboard.press('/')
    page.keyboard.type(text)
    page.keyboard.press('Escape')               # back to the canvas


def test_the_drill_world_project_mission_execution_and_back(browser, core, archeus_home):
    """A18-01/02/03/06/09/10: every step a URL, the list mirror equal to what
    is drawn, Enter to the canonical inspector and Back to the same focus."""
    check = Checks()
    project = _project(core, archeus_home)
    r = core.http('POST', '/v1/missions', body={
        'title': 'Drill me', 'objective': 'o', 'project_id': project['project']['id'],
        'idempotency_key': 'drill-%f' % time.time()})
    assert r.status == 200, r.body
    mid = r.json()['id']
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core)
    _go(page, '#/world/graph')
    g = _graph(page)
    check(g.get_attribute('data-graph-focus') == 'workspace', 'world level')
    check('project:%s' % project['project']['id'] in _mirror(page), 'the project is a cluster at world level')
    check(not [k for k in _mirror(page) if not k.startswith(('project:', 'more:'))],
          'the world level loads no child row')
    page.focus('canvas.graph-canvas')
    page.keyboard.press('f')                    # focus the graph on the project
    wait(page, lambda: page.evaluate('location.hash') == '#/world/graph/project/%s' % project['project']['id'],
         what='the project focus URL')
    g = _graph(page)
    wait(page, lambda: 'mission:%s' % mid in _mirror(page), what="the project's mission")
    _find(page, 'Drill me')
    wait(page, lambda: g.get_attribute('data-graph-at') == 'mission:%s' % mid, what='found')
    page.focus('canvas.graph-canvas')
    page.keyboard.press('f')                    # and on to the mission
    wait(page, lambda: page.evaluate('location.hash') == '#/world/graph/mission/%s' % mid,
         what='the mission focus URL')
    g = _graph(page)
    # the URL changes before the new graph renders: wait for it, as for the project
    wait(page, lambda: g.get_attribute('data-graph-focus') == 'mission:%s' % mid,
         what='the mission graph')
    check(True, 'mission focus')
    keys = _mirror(page)
    ex = [k for k in keys if k.startswith('execution:')]
    check(ex and 'mission:%s' % mid in keys and any(k.startswith('plan:') for k in keys),
          'the mission graph holds its plan and its execution')
    _find(page, 'Attempt 1')
    wait(page, lambda: g.get_attribute('data-graph-at') == ex[0], what='search lands on the attempt')
    page.focus('canvas.graph-canvas')
    page.keyboard.press('Enter')
    wait(page, lambda: page.evaluate('location.hash').startswith('#/o/execution/'),
         what='Enter opens the canonical inspector')
    check(page.evaluate('location.hash') == '#/o/execution/%s' % ex[0].split(':', 1)[1],
          'the inspector of the node that was selected')
    page.go_back()
    wait(page, lambda: page.evaluate('location.hash') == '#/world/graph/mission/%s' % mid,
         what='Back returns to the graph')
    check(page.locator('.graph').is_visible(), 'the graph again')
    check(not errors, errors)
    assert check.n >= 8
    context.close()


def test_zoom_fit_and_the_loop_parking(browser, core):
    """A18-07/08/16/17: zoom and fit by keyboard; a hidden page and a lost
    context park the one loop; nothing draws until they end."""
    check = Checks()
    mid = _mission(core, 'Zoom me')
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core)
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    canvas = page.locator('canvas.graph-canvas')
    wait(page, lambda: g.get_attribute('data-graph-loop') == 'parked', what='idle parks')
    # the visible canvas is the static layer copied: it must show the graph, not a blank
    inked = page.evaluate("""() => { const c = document.querySelector('canvas.graph-canvas');
        const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
        for (let i = 0; i < d.length; i += 4) if (d[i] !== d[0] || d[i+1] !== d[1] || d[i+2] !== d[2]) n++;
        return n; }""")
    check(inked > 200, 'the copied static layer shows the graph (%d inked pixels)' % inked)
    z0 = float(canvas.get_attribute('data-zoom'))
    page.focus('canvas.graph-canvas')
    page.keyboard.press('+')
    wait(page, lambda: float(canvas.get_attribute('data-zoom')) > z0 * 1.2, what='zoom in')
    wait(page, lambda: g.get_attribute('data-graph-loop') == 'parked', what='parks after the zoom')
    check(True, 'zoomed and parked')
    page.keyboard.press('0')
    wait(page, lambda: abs(float(canvas.get_attribute('data-zoom')) - z0) < 0.01, what='fit')
    check(True, 'fit')
    # a hidden page: nothing is scheduled, whatever is asked
    page.evaluate("() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});"
                  " document.dispatchEvent(new Event('visibilitychange')); }")
    frames = int(canvas.get_attribute('data-frames'))
    page.keyboard.press('+')
    page.wait_for_timeout(400)
    check(g.get_attribute('data-graph-loop') == 'parked', 'hidden: parked')
    check(int(canvas.get_attribute('data-frames')) == frames, 'hidden: no frame drawn')
    page.evaluate("() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});"
                  " document.dispatchEvent(new Event('visibilitychange')); }")
    wait(page, lambda: int(canvas.get_attribute('data-frames')) > frames, what='visible again: the owed frame')
    # a lost context
    page.evaluate("() => document.querySelector('canvas.graph-canvas').dispatchEvent(new Event('contextlost'))")
    frames = int(canvas.get_attribute('data-frames'))
    page.keyboard.press('-')
    page.wait_for_timeout(400)
    check(int(canvas.get_attribute('data-frames')) == frames, 'lost: no frame drawn')
    page.evaluate("() => document.querySelector('canvas.graph-canvas').dispatchEvent(new Event('contextrestored'))")
    wait(page, lambda: int(canvas.get_attribute('data-frames')) > frames, what='restored: redrawn')
    check(not errors, errors)
    assert check.n >= 6
    context.close()


def test_reduced_motion_moves_nothing(browser, core):
    """A18-15: under reduced motion a zoom is one frame, never a tween."""
    mid = _mission(core, 'Still')
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core, reduced_motion='reduce')
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    canvas = page.locator('canvas.graph-canvas')
    wait(page, lambda: g.get_attribute('data-graph-loop') == 'parked', what='idle')
    frames = int(canvas.get_attribute('data-frames'))
    page.focus('canvas.graph-canvas')
    page.keyboard.press('+')
    page.wait_for_timeout(500)
    assert int(canvas.get_attribute('data-frames')) - frames == 1
    assert not errors, errors
    context.close()


def test_a_running_execution_is_live_on_its_edge(browser, slow):
    """A18-14: live from Core's state; a pulse only for a frame about it."""
    mid = _mission(slow, 'Still running')
    deadline = time.monotonic() + 30
    while not [x for x in slow.http('GET', '/v1/world/graph?focus=mission:' + mid).json()['nodes']
               if x['kind'] == 'execution' and x.get('state') == 'RUNNING']:
        assert time.monotonic() < deadline, 'no running execution'
        time.sleep(0.1)
    context, page, errors = _open(browser, slow)
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    wait(page, lambda: int(g.get_attribute('data-graph-live') or 0) >= 1, what='a live edge')
    assert not errors, errors
    context.close()


def test_the_repository_import_graph(browser, core, archeus_home):
    """A18-23/24: the stored payload, focused and one level down."""
    project = _project(core, archeus_home)
    rep = project['repositories'][0]['id']
    deadline = time.monotonic() + 30
    while not core.http('GET', '/v1/repositories/%s/graph' % rep).json().get('available'):
        assert time.monotonic() < deadline, 'the repository was never inspected'
        time.sleep(0.2)
    context, page, errors = _open(browser, core)
    _go(page, '#/world/graph/repository/%s/modules' % rep)
    _graph(page)
    keys = _mirror(page)
    assert keys and all(k.startswith('path:') for k in keys), keys
    top = [k for k in keys if '/' not in k[len('path:'):] and not k.startswith('path:outside:')]
    assert top, keys
    assert not errors, errors
    context.close()


def test_an_unknown_focus_says_so(browser, core):
    context, page, _errors = _open(browser, core)
    _go(page, '#/world/graph/mission/msn_01J0000000000000000000000Z')
    page.get_by_text('no longer exists', exact=False).first.wait_for(timeout=10000)
    context.close()


def test_below_600_px_the_relations_list_is_the_view(browser, core):
    """A18-28: no canvas on a phone; the Relations list instead."""
    mid = _mission(core, 'Phone')
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core, viewport={'width': 390, 'height': 844})
    _go(page, '#/world/graph/mission/%s' % mid)
    page.locator('[data-graph-narrow]').wait_for(timeout=10000)
    assert page.locator('canvas').count() == 0
    page.locator('.rel-list, .relations').first.wait_for(timeout=10000)
    assert page.locator('.graph-toggle').count() == 0      # no link to what cannot be shown
    page.wait_for_timeout(300)
    # the list equivalent must not scroll the page sideways at phone width (A12)
    assert page.evaluate('() => document.documentElement.scrollWidth - innerWidth') <= 0
    for url in ('#/world/graph', '#/world/graph/mission/%s' % mid):
        _go(page, url)
        page.locator('[data-graph-narrow]').wait_for(timeout=10000)
        page.wait_for_timeout(300)
        over = page.evaluate('() => document.documentElement.scrollWidth - innerWidth')
        assert over <= 0, (url, over)
    assert not errors, errors
    context.close()


def test_closing_the_inspector_returns_to_the_canvas_and_a_pin_is_never_stored(browser, core):
    """A11: closing an inspector opened from the graph gives focus back to the
    canvas with the same node selected. A13: a pin is view state for this tab
    only, so a reload forgets it and nothing stores it."""
    check = Checks()
    mid = _mission(core, 'Come back')
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core)
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    page.focus('canvas.graph-canvas')
    page.keyboard.press('ArrowDown')
    page.keyboard.press('ArrowRight')           # across an edge: a node that is not the focus
    at = g.get_attribute('data-graph-at')
    check(at and at != 'mission:%s' % mid, 'walked to a neighbour')
    page.keyboard.press('.')
    wait(page, lambda: g.get_attribute('data-graph-pinned') == '1', what='pinned')
    check(page.locator('[data-graph-mirror] li[data-key="%s"]' % at).first.inner_text()
          .split('\n')[0].count('(pinned)') == 1, 'the mirror says it is pinned')
    page.keyboard.press('Enter')
    wait(page, lambda: page.evaluate('location.hash').startswith('#/o/'), what='the inspector')
    page.locator('.inspector h1').first.wait_for(timeout=10000)
    page.focus('.inspector h1')                 # focus is in the inspector, off the canvas
    check(page.evaluate("() => !!document.activeElement?.closest('.inspector')"), 'in the inspector')
    page.keyboard.press('Escape')
    wait(page, lambda: page.evaluate('location.hash') == '#/world/graph/mission/%s' % mid,
         what='closed')
    on_canvas = "() => document.activeElement?.classList.contains('graph-canvas')"
    wait(page, lambda: page.evaluate(on_canvas), what='focus back on the canvas')
    page.wait_for_timeout(300)                  # and still there once the close has settled
    check(page.evaluate(on_canvas), 'focus stays on the canvas')
    check(g.get_attribute('data-graph-at') == at, 'the same node selected')
    check(g.get_attribute('data-graph-pinned') == '1', 'the pin kept for the tab')
    stored = page.evaluate('() => JSON.stringify([Object.keys(localStorage), Object.keys(sessionStorage)])')
    check('pin' not in stored.lower(), 'nothing stores a pin: %s' % stored)
    page.reload()
    g = _graph(page)
    check(g.get_attribute('data-graph-pinned') == '0', 'a reload forgets the pin')
    check(not errors, errors)
    assert check.n >= 9
    context.close()


def test_axe_and_no_sideways_scroll_on_the_graph(browser, core):
    """A18-27: axe-core finds nothing serious; nothing overflows at 768-1920."""
    if not os.path.isfile(AXE):
        pytest.skip('axe-core is not installed (npm ci in clients/app)')
    mid = _mission(core, 'Accessible graph')
    _settled(core, mid, 'COMPLETED')
    for width in (768, 1280, 1920):
        context, page, errors = _open(browser, core, bypass_csp=True,
                                      viewport={'width': width, 'height': 900})
        _go(page, '#/world/graph/mission/%s' % mid)
        _graph(page)
        page.wait_for_timeout(300)
        over = page.evaluate('() => document.documentElement.scrollWidth - innerWidth')
        assert over <= 0, (width, over)
        page.add_script_tag(path=AXE)
        bad = page.evaluate('async () => (await axe.run(document, {resultTypes: ["violations"]})).violations'
                            '.filter(v => ["serious", "critical"].includes(v.impact))'
                            '.map(v => v.id + ": " + v.nodes.map(n => n.target.join(" ")).slice(0, 3).join(", "))')
        assert not bad, (width, bad)
        assert not errors, errors
        context.close()


# ── the approved behaviours built after the consistency pass (gate §22.2 N1–N7) ──

def _row(page, key):
    return page.locator('[data-graph-mirror] li[data-key="%s"]' % key).first.inner_text().split('\n')[0]


def _at(page):
    x, y = page.locator('canvas.graph-canvas').get_attribute('data-at').split(',')
    box = page.locator('canvas.graph-canvas').bounding_box()
    return box['x'] + int(x), box['y'] + int(y), box


def test_counts_route_facts_hover_search_centre_path_and_esc(browser, core, archeus_home):
    """N1 world counts, N2 a route decision's recorded facts, N3 hover, N4 a
    search match centred, N5 "no path", N6 Esc clears the selection — each
    read from what the page shows."""
    check = Checks()
    project = _project(core, archeus_home)
    pid = project['project']['id']
    r = core.http('POST', '/v1/missions', body={
        'title': 'Count me', 'objective': 'o', 'project_id': pid,
        'idempotency_key': 'count-%f' % time.time()})
    assert r.status == 200, r.body
    mid = r.json()['id']
    _settled(core, mid, 'COMPLETED')
    second = FixtureRepo.create('layered-python', os.path.dirname(str(archeus_home)))
    r = core.http('POST', '/v1/projects', body={'name': 'Borealis', 'root_paths': [second.path],
                                                'idempotency_key': 'b-%f' % time.time()})
    assert r.status == 200, r.body
    other = r.json()['project']['id']
    context, page, errors = _open(browser, core)
    # N1: the world level says what Core counted
    _go(page, '#/world/graph')
    g = _graph(page)
    wait(page, lambda: 'project:%s' % other in _mirror(page), what='both projects')
    row = _row(page, 'project:%s' % pid)
    check('1 mission (' in row and '1 repository' in row and 'knowledge item' in row, 'counts: %s' % row)
    check('0 missions' in _row(page, 'project:%s' % other), 'the other project counted too')
    # N5: two loaded ends with no loaded path between them
    page.focus('canvas.graph-canvas')
    first = g.get_attribute('data-graph-at')
    page.keyboard.press('p')
    _find(page, 'Borealis' if first == 'project:%s' % pid else 'Atlas')
    page.focus('canvas.graph-canvas')
    page.keyboard.press('p')
    wait(page, lambda: g.get_attribute('data-graph-path') == 'none', what='no path found')
    check(page.get_by_role('status').filter(has_text='No path within the loaded neighbourhood').count() == 1,
          'the page says there is no path')
    # N2: a mission's route decision, with its recorded facts and nothing else
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    wait(page, lambda: g.get_attribute('data-graph-focus') == 'mission:%s' % mid, what='the mission graph')
    rds = [x for x in _mirror(page) if x.startswith('route_decision:')]
    check(rds, 'the mission graph holds a route decision: %s' % _mirror(page))
    facts = _row(page, rds[0])
    check(' — harness ' in facts, 'its recorded facts: %s' % facts)
    for bad in ('explanation', 'requirement', 'candidate', 'snapshot'):
        check(bad not in facts.lower(), '%s shown' % bad)
    # N6: Esc clears the search, the path marks and the selection
    page.focus('canvas.graph-canvas')
    page.keyboard.press('ArrowDown')
    check(g.get_attribute('data-graph-selected') != '', 'a relationship selected')
    page.keyboard.press('p')
    page.keyboard.press('p')
    check(g.get_attribute('data-graph-path') == 'found', 'a path marked')
    page.fill('input.graph-search', 'zzz')
    page.focus('canvas.graph-canvas')
    page.keyboard.press('Escape')
    check(g.get_attribute('data-graph-selected') == '', 'Esc cleared the selection')
    check(g.get_attribute('data-graph-path') == '', 'Esc cleared the path marks')
    check(page.input_value('input.graph-search') == '', 'Esc cleared the search')
    # N4: a search match is centred in the canvas
    _find(page, 'Attempt 1')
    wait(page, lambda: g.get_attribute('data-graph-at').startswith('execution:'), what='found')
    wait(page, lambda: g.get_attribute('data-graph-loop') == 'parked', what='the move ends')
    x, y, box = _at(page)
    check(abs(x - (box['x'] + box['width'] / 2)) <= 2 and abs(y - (box['y'] + box['height'] / 2)) <= 2,
          'the match is centred: at %s,%s in %s' % (x, y, box))
    # N3: the mouse over a node is the hovered node (its label drawn — TS render test)
    page.mouse.move(x, y)
    wait(page, lambda: page.locator('canvas.graph-canvas').get_attribute('data-hover') == g.get_attribute('data-graph-at'),
         what='hovered')
    page.mouse.move(box['x'] + 2, box['y'] + 2)
    wait(page, lambda: page.locator('canvas.graph-canvas').get_attribute('data-hover') == '', what='hover left')
    check(True, 'hover follows the mouse')
    check(not errors, errors)
    assert check.n >= 16
    context.close()


def test_touch_pinch_double_tap_and_44_px_targets(browser, core):
    """N7 (A12) on an emulated touch screen at 1280 px: two real touch points
    (CDP Input.dispatchTouchEvent) pinch the zoom, a double-tap opens the node,
    and every toolbar control is at least 44 px. A physical touch device is
    still manual evidence (gate §23)."""
    check = Checks()
    mid = _mission(core, 'Touch me')
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core, has_touch=True, viewport={'width': 1280, 'height': 900})
    check(page.evaluate("matchMedia('(pointer: coarse)').matches"), 'the emulated screen is coarse')
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    canvas = page.locator('canvas.graph-canvas')
    wait(page, lambda: g.get_attribute('data-graph-loop') == 'parked', what='idle')
    small = page.evaluate("""() => [...document.querySelectorAll('.graph-bar .chip, .graph-search')]
        .map(e => e.getBoundingClientRect()).filter(r => r.height < 44 || r.width < 44).length""")
    check(small == 0, '%d toolbar controls under 44 px' % small)
    # pinch: two fingers spreading from 40 px apart to 200 px apart
    box = canvas.bounding_box()
    cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
    z0 = float(canvas.get_attribute('data-zoom'))
    cdp = context.new_cdp_session(page)

    def touch(kind, gap):
        pts = [] if kind == 'touchEnd' else [
            {'x': cx - gap / 2, 'y': cy, 'id': 1}, {'x': cx + gap / 2, 'y': cy, 'id': 2}]
        cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': pts})

    touch('touchStart', 100)
    for gap in (110, 125, 140, 150):
        touch('touchMove', gap)
    touch('touchEnd', 0)
    # the zoom follows the fingers: 100 px apart to 150 px apart is x1.5
    wait(page, lambda: abs(float(canvas.get_attribute('data-zoom')) - z0 * 1.5) <= z0 * 0.03,
         what='the pinch zoomed x1.5 (from %s)' % z0)
    check(True, 'pinch zooms: %s -> %s' % (z0, canvas.get_attribute('data-zoom')))
    # a single tap selects; a double-tap on the same node opens it
    page.focus('canvas.graph-canvas')
    page.keyboard.press('0')
    wait(page, lambda: abs(float(canvas.get_attribute('data-zoom')) - z0) < 0.01, what='fit')
    wait(page, lambda: g.get_attribute('data-graph-loop') == 'parked', what='parked')
    x, y, _box = _at(page)
    at = g.get_attribute('data-graph-at')
    page.touchscreen.tap(x, y)
    page.wait_for_timeout(100)
    check(page.evaluate('location.hash') == '#/world/graph/mission/%s' % mid, 'one tap does not open')
    page.touchscreen.tap(x, y)
    wait(page, lambda: page.evaluate('location.hash') == '#/o/%s/%s' % tuple(at.split(':', 1)),
         what='the double-tap opens the node')
    check(True, 'double-tap opens')
    check(not errors, errors)
    assert check.n >= 6
    context.close()
