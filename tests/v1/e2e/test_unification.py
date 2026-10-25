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

import os
import re
import time

import pytest

from archeus.core import ports, runtime
from archeus.harnesses.fake import FakeCaller
from v1.judge.http import TUNNEL, TempCore, request
from v1.judge.support import TuiDriver

from .conftest import Tunnel, wait
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
    tc = TempCore(archeus_home, remote_hosts=(TUNNEL,), ports=runtime.Ports(
        brain=ports.FixedPlanBrain(DEPLOY), callers=[brain], reviewer=_RejectingReview())).start()
    yield tc
    tc.stop(kill=True)



class _Route:
    """Playwright's Route, as far as Tunnel reads it: no browser needed."""

    def __init__(self, method, path, headers, body=None):
        self.request = type('Req', (), {
            'method': method, 'url': 'http://127.0.0.1/' + path.lstrip('/'),
            'headers': headers, 'post_data_buffer': body})()
        self.done = None

    def continue_(self):
        self.done = ('continued',)

    def fulfill(self, status, body, headers):
        self.done = ('fulfilled', status, body)


def test_the_tunnel_sends_only_credentialed_commands_through_the_remote_host(archeus_home):
    """The fixture itself, without a browser: a command carrying a credential
    reaches Core through the remote host (Core then decides), and a read, the
    stream and an uncredentialed redemption stay on the loopback Host."""
    tc = TempCore(archeus_home, remote_hosts=(TUNNEL,)).start()
    try:
        code = tc.http('POST', '/v1/devices/pair/start',
                       body={'scopes': ['observe', 'control']}).json()['code']
        token = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                        body={'code': code, 'platform': 'web'}).json()['token']
        cred = {'authorization': 'Bearer ' + token, 'content-type': 'application/json',
                'host': '127.0.0.1', 'origin': tc.base_url, 'sec-fetch-site': 'same-origin'}
        tunnel = Tunnel(tc)
        for route in (_Route('GET', '/v1/missions', cred), _Route('GET', '/v1/stream', cred),
                      _Route('POST', '/v1/devices/pair/redeem', {}, b'{}')):
            tunnel(route)
            assert route.done == ('continued',), route.request.url
        body = ('{"title": "M", "objective": "o", "idempotency_key": "%s"}'
                % os.urandom(8).hex()).encode()
        command = _Route('POST', '/v1/missions', cred, body)
        tunnel(command)
        assert command.done[:2] == ('fulfilled', 200), command.done
        assert tunnel.sent == [('POST', '/v1/missions', 200)] and tunnel.token == token
        direct = request(tc.base_url, 'POST', '/v1/missions', token=token, raw=body,
                         headers={'Content-Type': 'application/json'})
        assert (direct.status, direct.json()['error']) == (403, 'remote_host_required')
    finally:
        tc.stop()

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
    # T-150: under `standard` a chat mission asks to start; the desktop approves that card
    wait(page, lambda: [x for x in tc.http('GET', '/v1/approvals?mission=' + mid).json()['approvals']
                        if x['state'] == 'PENDING'], what='the start card')
    (start,) = [x for x in tc.http('GET', '/v1/approvals?mission=' + mid).json()['approvals']
                if x['state'] == 'PENDING']
    started = tc.http('POST', '/v1/approvals/%s/decide' % start['id'], body={
        'decision': 'approve', 'action_hash': start.get('action_hash'),
        'expected_version': start.get('version'), 'idempotency_key': 'start-' + start['id']})
    check(started.status == 200, 'the desktop approved the start: %s' % started.body)
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
    # the phone's commands reach Core through the remote host, as from a
    # phone on the tailnet; the desktop stays on this machine (T-053 Q4-A)
    tunnel = Tunnel(tc)
    phone.route('**/v1/**', tunnel)
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
    # the direct-loopback negative control: the phone's own credential, on the
    # loopback Host, is refused before anything is decided
    check(tunnel.token is not None, 'the phone has sent its credential')
    direct = request(tc.base_url, 'POST', '/v1/approvals/%s/decide' % pending['id'],
                     token=tunnel.token, body={
                         'decision': 'approve', 'action_hash': pending.get('action_hash'),
                         'expected_version': pending.get('version'),
                         'idempotency_key': 'direct-' + pending['id'], 'step_up': PIN})
    check((direct.status, direct.json()['error']) == (403, 'remote_host_required'),
          'on the loopback Host the phone cannot approve: %s' % direct.body)
    check(tc.http('GET', '/v1/approvals/' + pending['id']).json()['state'] == 'PENDING',
          'the refused approval left it pending')
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
    check(('POST', '/v1/approvals/%s/decide' % pending['id'], 200) in tunnel.sent,
          'the approval went through the remote host: %s' % tunnel.sent)

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
    assert check.n >= 22, 'only %d checks ran' % check.n
    phone.close()
    desktop.close()
