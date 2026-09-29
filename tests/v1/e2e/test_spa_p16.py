"""P16 in a real browser against a real Core (p16-design-gate §24.1): every
destination and inspector tab, the approval flow, pause and resume, pairing and
revocation across two clients, reconnect, keyboard-only use, axe-core, the
overflow audit at four widths, reduced motion and touch targets. A check floor
derived from the navigation table keeps a suite that silently checks nothing
from passing."""

import os
import re
import time

import pytest

from archeus.api import auth
from archeus.core import engine, ports, runtime
from archeus.harnesses.fake import FakeHarness
from claude_sessions import proc
from v1.judge.http import TempCore, request

from .conftest import wait

APP = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'clients', 'app')
NAV = open(os.path.join(APP, 'src', 'nav', 'destinations.ts'), encoding='utf-8').read()
DESTINATIONS = re.findall(r"\{ id: '(\w+)', label: '(\w+)'", NAV.split('export const DESTINATIONS')[1].split('];')[0])
SECTIONS = re.findall(r"\{ id: '(\w+)', label: '[\w ]+' \}", NAV.split('CONTROL_SECTIONS')[1].split('] as const')[0])
MISSION_TABS = re.findall(r"'(\w+)'", re.search(r'mission: \[([^\]]+)\]', NAV).group(1))
DEPLOY = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0],
                                                 action_classes=['deploy'])])
SLOW = {'work': [{'emit': {'type': 'working'}}, {'sleep': 30}]}
FULL = auth.LOCAL_SCOPES


class Checks:
    def __init__(self):
        self.n = 0

    def __call__(self, ok, what):
        assert ok, what
        self.n += 1


def _mission(tc, title='Fix the flaky date test'):
    r = tc.http('POST', '/v1/missions', body={'title': title, 'objective': 'Tests pass',
                                              'idempotency_key': 'k-%s-%f' % (title, time.time())})
    assert r.status == 200, r.body
    return r.json()['id']


def _state(tc, mid):
    return tc.http('GET', '/v1/missions/' + mid).json()['state']


def _settled(tc, mid, want):
    deadline = time.monotonic() + 30
    while _state(tc, mid) != want:
        assert time.monotonic() < deadline, 'mission %s never reached %s' % (mid, want)
        time.sleep(0.05)


def _open(browser, tc, scopes=FULL, **ctx):
    context = browser.new_context(**ctx)
    page = context.new_page()
    errors = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(tc.core.launch_url(scopes))
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    return context, page, errors


def _go(page, hash_):
    page.evaluate('h => location.hash = h', hash_)
    page.wait_for_timeout(250)


@pytest.fixture
def deploy(archeus_home):
    """A Core whose plan deploys: the plan asks for approval (P9)."""
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(DEPLOY))).start()
    yield tc
    tc.stop()


@pytest.fixture
def slow(archeus_home):
    """A Core whose one task runs for 30 s on the fake harness."""
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(SLOW),
        executors=[FakeHarness()])).start()
    yield tc
    for p in list(tc.core.manager._procs.values()):
        proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
    tc.stop()


def test_every_destination_and_every_mission_tab_renders_what_core_holds(browser, core):
    check = Checks()
    mid = _mission(core)
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core)
    for did, label in DESTINATIONS:
        _go(page, '#/control/autonomy' if did == 'control' else '#/' + did)
        page.get_by_role('heading', name=label, exact=True).wait_for()
        check(page.locator('nav[aria-label="Destinations"] a[aria-current="page"]').inner_text().strip().startswith(label), did)
    for s in SECTIONS:
        _go(page, '#/control/' + s)
        page.locator('.subnav a[aria-current="page"]').wait_for()
        check(page.locator('.subnav a[aria-current="page"]').get_attribute('href') == '#/control/' + s, s)
    for t in MISSION_TABS:
        _go(page, '#/o/mission/%s/%s' % (mid, t))
        tab = page.locator('#tab-%s' % t)
        tab.wait_for()
        check(tab.get_attribute('aria-selected') == 'true', t)
        check(page.locator('#panel-%s' % t).count() == 1, 'panel ' + t)
    # the state on screen is the one Core returned, glyph AND label
    badge = page.locator('.insp-head .state').first
    check(badge.get_attribute('data-state') == 'COMPLETED', 'state')
    check('verified and reviewed' in badge.inner_text(), 'label')
    # the Done mission's Why says so, and names the row it read
    _go(page, '#/o/mission/%s/why' % mid)
    page.get_by_text('Completed: its result was verified').wait_for()
    check(True, 'why')
    floor = len(DESTINATIONS) + len(SECTIONS) + 2 * len(MISSION_TABS) + 3
    assert check.n >= floor, 'ran %d checks, floor %d' % (check.n, floor)
    assert not errors, errors
    context.close()


def test_a_plan_that_asks_is_approved_from_attention_and_the_mission_moves(browser, deploy):
    mid = _mission(deploy, 'Deploy the docs')
    _settled(deploy, mid, 'APPROVAL_REQUIRED')
    context, page, errors = _open(browser, deploy)
    badge = page.locator('nav a[href="#/attention"] .badge')
    badge.wait_for()
    assert badge.inner_text() == '1'
    _go(page, '#/attention')
    card = page.locator('article[data-kind="approval"]')
    card.wait_for()
    # the canonical action, why it asks, what each answer does, the expiry
    assert card.locator('table.canonical td', has_text='deploy').count() >= 1
    for text in ('Why it asks', 'If you approve', 'If you reject', 'Expires'):
        assert card.get_by_text(text).count() == 1, text
    # a destructive/step-up approval puts Reject first
    buttons = [b.inner_text() for b in card.locator('.decide button').all()]
    assert buttons[0] == 'Reject', buttons
    card.get_by_role('button', name='Approve plan').click()
    _settled(deploy, mid, 'COMPLETED')
    # the card re-reads the row; nothing is shown as done before Core says so
    page.get_by_text('Nothing waits on you.').wait_for(timeout=15000)
    approvals = deploy.http('GET', '/v1/approvals?mission=%s' % mid).json()['approvals']
    assert approvals[0]['state'] == 'APPROVED'
    assert not errors, errors
    context.close()


def test_pause_and_resume_from_the_mission_header(browser, slow):
    mid = _mission(slow, 'Long work')
    _settled(slow, mid, 'EXECUTING')
    context, page, errors = _open(browser, slow)
    _go(page, '#/o/mission/%s' % mid)
    head = page.locator('.insp-head')
    head.get_by_role('button', name='Pause').click()
    wait(page, lambda: head.locator('.state').first.get_attribute('data-state') == 'PAUSED', what='PAUSED')
    assert _state(slow, mid) == 'PAUSED'
    head.get_by_role('button', name='Resume').click()
    wait(page, lambda: head.locator('.state').first.get_attribute('data-state') in ('EXECUTING', 'RESUMED'),
         what='resumed')
    # the Now tab shows the execution with harness, model and account as three fields
    _go(page, '#/o/mission/%s/now' % mid)
    ex = page.locator('li.execution').first
    ex.wait_for()
    fields = [d.get_attribute('data-field') for d in ex.locator('.resources > div').all()]
    assert fields[:3] == ['harness', 'model', 'account'], fields
    assert not errors, errors
    context.close()


def test_pairing_a_second_client_then_revoking_it_signs_it_out(browser, core):
    desktop, page, errors = _open(browser, core)
    _go(page, '#/control/devices')
    page.get_by_label('Name (what the new client is called here)').fill('Test phone')
    page.get_by_role('button', name='Start pairing').click()
    link = page.locator('.pairing .mono', has_text='#pair=')
    link.wait_for()
    code = re.search(r'#pair=([\w-]+)', link.inner_text()).group(1)
    phone = browser.new_context(viewport={'width': 390, 'height': 844})
    p2 = phone.new_page()
    p2.goto(core.base_url + '/#pair=' + code)
    p2.get_by_role('button', name='Pair').wait_for()
    assert '#' not in p2.url                            # the code left the address bar
    p2.get_by_role('button', name='Pair').click()
    p2.get_by_role('heading', name='Now', exact=True).wait_for()
    # the desktop sees the new client, paired, with its presence
    row = page.locator('li[data-device]', has_text='Test phone')
    row.wait_for(timeout=15000)
    wait(page, lambda: row.get_attribute('data-presence') == 'connected', what='the phone connected')
    assert 'paired' in row.inner_text() and '(declared)' in row.inner_text()
    # the code is spent: a second redemption is refused
    again = request(core.base_url, 'POST', '/v1/devices/pair/redeem', body={'code': code, 'platform': 'web'})
    assert again.status == 401
    row.get_by_role('button', name='Revoke').click()
    page.locator('dialog[open]').get_by_role('button', name='Revoke').click()
    p2.get_by_text('This client is signed out').wait_for(timeout=20000)
    assert not errors, errors
    phone.close()
    desktop.close()


def test_a_restart_shows_reconnecting_then_current_data(browser, core):
    context, page, _errors = _open(browser, core)
    _go(page, '#/work')
    core.restart(kill=False)
    page.locator('.banner[data-conn]').first.wait_for(timeout=15000)
    mid = _mission(core, 'After restart')
    page.locator('li[data-mission="%s"]' % mid).wait_for(timeout=30000)
    wait(page, lambda: page.locator('.banner').count() == 0, timeout=15, what='the banner to clear')
    context.close()


def test_keyboard_only_navigation(browser, core):
    mid = _mission(core, 'Keyboard')
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core)
    page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement.textContent') == 'Skip to content'
    page.keyboard.press('Control+2')
    page.get_by_role('heading', name='Work', exact=True).wait_for()
    wait(page, lambda: page.evaluate('document.activeElement.tagName') == 'H1', what='focus on the heading')
    page.locator('li[data-mission="%s"] a' % mid).focus()
    page.keyboard.press('Enter')
    tab = page.locator('#tab-outcome')
    tab.wait_for()
    tab.focus()
    page.keyboard.press('ArrowRight')
    wait(page, lambda: page.locator('#tab-plan').get_attribute('aria-selected') == 'true', what='arrow moves tabs')
    assert page.evaluate('document.activeElement.id') == 'tab-plan'
    page.keyboard.press('End')
    wait(page, lambda: page.locator('#tab-relations').get_attribute('aria-selected') == 'true', what='End')
    page.keyboard.press('Escape')
    wait(page, lambda: page.locator('aside.inspector').count() == 0, what='Escape closes the inspector')
    page.keyboard.press('Control+k')
    page.locator('dialog.command[open]').wait_for()
    page.keyboard.type('Work')
    page.keyboard.press('Enter')
    page.get_by_role('heading', name='Work', exact=True).wait_for()
    assert not errors, errors
    context.close()


AXE = os.path.join(APP, 'node_modules', 'axe-core', 'axe.min.js')


def test_axe_finds_no_serious_or_critical_violation(browser, deploy):
    if not os.path.isfile(AXE):
        pytest.skip('axe-core is not installed (npm ci in clients/app)')
    mid = _mission(deploy, 'Accessible')
    _settled(deploy, mid, 'APPROVAL_REQUIRED')
    context, page, _errors = _open(browser, deploy, bypass_csp=True)
    bad = []
    for hash_ in ('#/now', '#/work', '#/world', '#/attention', '#/control/devices', '#/control/autonomy',
                  '#/o/mission/%s' % mid, '#/o/mission/%s/why' % mid):
        _go(page, hash_)
        page.wait_for_timeout(500)
        page.add_script_tag(path=AXE)
        got = page.evaluate('async () => (await axe.run(document, {resultTypes: ["violations"]})).violations'
                            '.filter(v => ["serious", "critical"].includes(v.impact))'
                            '.map(v => v.id + ": " + v.nodes.map(n => n.target.join(" ")).slice(0, 3).join(", "))')
        bad += ['%s %s' % (hash_, v) for v in got]
    assert not bad, bad
    context.close()


@pytest.mark.parametrize('width', [390, 768, 1280, 1920])
def test_nothing_scrolls_sideways_at_any_width(browser, deploy, width):
    mid = _mission(deploy, 'A mission with a long enough title to wrap on a phone screen')
    _settled(deploy, mid, 'APPROVAL_REQUIRED')
    context, page, errors = _open(browser, deploy, viewport={'width': width, 'height': 900})
    over = []
    for hash_ in ['#/' + d for d, _l in DESTINATIONS if d != 'control'] + ['#/control/' + s for s in SECTIONS] + \
            ['#/o/mission/%s/%s' % (mid, t) for t in MISSION_TABS]:
        _go(page, hash_)
        page.wait_for_timeout(200)
        extra = page.evaluate('() => document.documentElement.scrollWidth - innerWidth')
        if extra > 0:
            over.append((hash_, extra))
    assert not over, over
    if width == 390:
        # a phone: the tab bar holds Now, Work, World and Attention, and targets are 44 px
        tabs = [t.inner_text().strip() for t in page.locator('nav .nav-label').all() if t.is_visible()]
        assert tabs == ['Now', 'Work', 'World', 'Attention'], tabs
        for b in page.locator('nav a').all():
            if b.is_visible():
                assert b.bounding_box()['height'] >= 44
    assert not errors, errors
    context.close()


def test_reduced_motion_removes_movement(browser, core):
    mid = _mission(core, 'Still')
    _settled(core, mid, 'COMPLETED')
    context, page, _errors = _open(browser, core, reduced_motion='reduce')
    assert page.evaluate('document.documentElement.dataset.motion') == 'reduced'
    _go(page, '#/o/mission/%s' % mid)
    page.locator('aside.inspector').wait_for()
    assert page.evaluate("getComputedStyle(document.querySelector('aside.inspector')).animationName") == 'none'
    context.close()
    context, page, _errors = _open(browser, core)
    assert page.evaluate('document.documentElement.dataset.motion') == 'full'
    context.close()
