"""P19's unification scenario over one real Core (the plan's P19 test,
p19-design-gate B12): create on desktop → observe on mobile → approve on
mobile → execute on PC → review on desktop → inspect on TUI.

Every step is a user's: the mission is asked for in the desktop SPA's
composer (the conversation's brain makes it), a phone paired from the
desktop's Control → Clients watches it at 390 px and approves its plan with
its own credential, the fake harness runs the task on this machine, the
desktop accepts the result its reviewer rejected, and the TUI reads the row.
At each step every client open says the state Core holds. A check floor keeps
a test that silently checks nothing from passing."""

import re
import time

import pytest

from archeus.core import ports, runtime
from archeus.harnesses.fake import FakeCaller
from v1.judge.http import TempCore
from v1.judge.support import TuiDriver

from .conftest import wait
from .test_spa_p16 import DEPLOY, FULL, Checks, _go, _settled, _state
from .test_spa_r9_details import _RejectingReview

ASK = 'Deploy the release notes'
WORK = {'kind': 'new_work', 'title': 'Deploy the release notes',
        'objective': 'The release notes are live.',
        'requirements': [{'text': 'the release notes are deployed', 'origin': 'explicit'}]}
PIN = '246810'
DESKTOP = {'width': 1280, 'height': 800}
PHONE = {'width': 390, 'height': 844}


@pytest.fixture
def unified(archeus_home):
    """One Core: the conversation's brain answers the request, the plan deploys
    (so it asks), the task runs on the fake harness, and the reviewer rejects
    the result, so it waits for a person."""
    brain = FakeCaller('fake_brain', structured='native', replies={
        'brain': [{'when': 'The message:\n' + ASK, 'parsed': WORK}]})
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(DEPLOY), callers=[brain], reviewer=_RejectingReview())).start()
    yield tc
    tc.stop(kill=True)


def _watch(context):
    page = context.new_page()
    errors = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    return page, errors


def _row_state(page, mid):
    row = page.locator('li[data-mission="%s"]' % mid)
    return row.get_attribute('data-state') if row.count() else None


def _shows(page, mid, want, what):
    """The page's Work row reaches *want* by itself: the event stream, no reload."""
    wait(page, lambda: _row_state(page, mid) == want, what='%s shows %s' % (what, want))


def test_create_on_desktop_observe_and_approve_on_mobile_execute_review_inspect(browser, unified):
    tc, check = unified, Checks()

    # ── create on desktop ──
    desktop = browser.new_context(viewport=DESKTOP)
    page, errors = _watch(desktop)
    before = {d['id'] for d in tc.http('GET', '/v1/devices').json()['devices']}
    page.goto(tc.core.launch_url(FULL))
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    (me,) = [d for d in tc.http('GET', '/v1/devices').json()['devices'] if d['id'] not in before]
    page.get_by_label('Tell Archeus what you want').first.fill(ASK)
    page.locator('form.composer button', has_text='Send').first.click()

    def made():
        ms = [m for m in tc.http('GET', '/v1/missions').json()['missions'] if m['title'] == WORK['title']]
        return ms[0]['id'] if ms else None
    wait(page, lambda: made() is not None, what='the brain made the mission')
    mid = made()
    mission = tc.http('GET', '/v1/missions/' + mid).json()
    check(mission['origin'] == 'conversation', 'the mission came from the desktop conversation')
    page.locator('.conversation [data-ref="mission:%s"]' % mid).first.wait_for()
    check(True, "the desktop's conversation names the mission it made")
    _settled(tc, mid, 'APPROVAL_REQUIRED')
    _go(page, '#/work')
    _shows(page, mid, 'APPROVAL_REQUIRED', 'the desktop')
    check(True, 'the desktop shows the plan waiting')

    # ── observe on mobile: a phone paired from the desktop, its own credential ──
    _go(page, '#/control/devices')
    page.get_by_label('Name (what the new client is called here)').fill('Phone')
    page.get_by_role('button', name='Start pairing').click()
    link = page.locator('.pairing .mono', has_text='#pair=')
    link.wait_for()
    code = re.search(r'#pair=([\w-]+)', link.inner_text()).group(1)
    phone = browser.new_context(viewport=PHONE, is_mobile=True, has_touch=True)
    mobile, phone_errors = _watch(phone)
    mobile.goto(tc.base_url + '/#pair=' + code)
    mobile.locator('input[inputmode="numeric"]').fill(PIN)
    mobile.get_by_role('button', name='Pair').click()
    mobile.get_by_role('heading', name='Now', exact=True).wait_for()
    devices = tc.http('GET', '/v1/devices').json()['devices']
    (paired,) = [d for d in devices if d['name'] == 'Phone']
    check(paired['origin'] == 'paired' and 'approve' in paired['scopes'] and 'admin' not in paired['scopes'],
          'the phone holds its own paired credential: %s' % paired)
    check(paired['principal_id'] != me['principal_id'], 'a second principal, not the desktop again')
    check(mobile.evaluate('() => document.documentElement.scrollWidth') <= PHONE['width'],
          'the phone does not scroll sideways')
    _go(mobile, '#/work')
    _shows(mobile, mid, 'APPROVAL_REQUIRED', 'the phone')
    check(True, 'the phone observes the plan waiting')

    # ── approve on mobile ──
    (pending,) = [a for a in tc.http('GET', '/v1/approvals?mission=' + mid).json()['approvals']
                  if a['state'] == 'PENDING']
    _go(mobile, '#/attention')
    card = mobile.locator('article[data-kind="approval"]')
    card.wait_for()
    check(pending['step_up'], 'a deploy asks for a step-up')
    card.get_by_label('This client’s PIN (step-up)').fill(PIN)     # a paired client's proof
    card.get_by_role('button', name='Approve plan').click()

    def decided():
        a = tc.http('GET', '/v1/approvals/' + pending['id']).json()
        return a if a['state'] != 'PENDING' else None
    wait(mobile, lambda: decided() is not None, what='the phone decided')
    got = decided()
    check(got['state'] == 'APPROVED', 'the phone approved the plan: %s' % got['state'])
    check(got['decided_by'] == paired['principal_id'],
          'decided by the phone, not the desktop: %s' % got['decided_by'])

    # ── execute on PC: the fake harness runs the task on this machine ──
    _settled(tc, mid, 'REVIEWING')
    (task,) = tc.http('GET', '/v1/missions/%s/plan' % mid).json()['plan']['tasks']
    xs = tc.http('GET', '/v1/tasks/%s/executions' % task['id']).json()['executions']
    check(len(xs) == 1 and xs[0]['harness_id'] == 'fake' and xs[0]['state'] == 'ENDED_OK',
          'one attempt ran on the local fake harness and ended well: %s' % xs)
    _go(mobile, '#/work')
    _go(page, '#/work')
    _shows(mobile, mid, 'REVIEWING', 'the phone')
    _shows(page, mid, 'REVIEWING', 'the desktop')
    check(True, 'both clients show the mission in review')

    # ── review on desktop ──
    _go(page, '#/o/mission/%s/evidence' % mid)
    page.locator('.action > button', has_text='Accept result').click()
    _settled(tc, mid, 'COMPLETED')
    reviews = tc.http('GET', '/v1/missions/%s/reviews' % mid).json()['reviews']
    check([r['reviewer'] for r in reviews] == ['stub', 'user'] and reviews[-1]['verdict'] == 'accept',
          "the desktop's review accepted what the reviewer rejected: %s" % reviews)
    check(reviews[-1]['principal_id'] == me['principal_id'],
          'the review is the desktop\'s, not the phone\'s: %s' % reviews[-1]['principal_id'])
    badge = page.locator('.insp-head .state').first
    wait(page, lambda: badge.get_attribute('data-state') == 'COMPLETED', what='the desktop says completed')
    check(True, 'the desktop shows the mission completed')
    _shows(mobile, mid, 'COMPLETED', 'the phone')       # still on Work: Core's stream told it
    check(True, 'the phone, left open, shows it completed')

    # ── inspect on TUI ──
    row = TuiDriver(tc).mission_row(mid)
    check(row['state'] == 'COMPLETED' == _state(tc, mid), 'the TUI reads the state Core holds: %s' % row)
    check(row['label'].strip() and WORK['title'] in row['text'], 'the TUI row names it in words: %s' % row)

    check(not errors, 'no console errors on the desktop: %s' % errors)
    check(not phone_errors, 'no console errors on the phone: %s' % phone_errors)
    assert check.n >= 18, 'only %d checks ran' % check.n
    phone.close()
    desktop.close()
