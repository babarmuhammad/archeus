"""P19 S1 in a real browser against a real Core (p19-design-gate B3, §4.1): the
mission's Now tab holds the mission's own conversation above what is running
for it. A turn sent there is the mission's and its reply lands there; a reply
whose links name an attempt shown on the tab draws the thread's line to that
row once (A-05, extended to this surface), and never again on a reload. The
replies come from the control grammar, which answers without a model call.
Mutation-verified by tools/mutate_p19.py. A check floor keeps a test that
silently checks nothing from passing."""

import math
import time

from .conftest import wait
from .test_spa_halo import _running
from .test_spa_p16 import Checks, _go, _mission, _settled, deploy  # noqa: F401 (a fixture)
from .test_spa_p18 import slow  # noqa: F401 (a fixture)
from .test_spa_thread import _context, _page, _quiet_line, _threads


def _say(tc, conversation, text):
    r = tc.http('POST', '/v1/conversations/%s/messages' % conversation,
                body={'text': text, 'idempotency_key': 'say-%f' % time.monotonic()})
    assert r.status == 200, r.body
    sent = r.json()['message_id']
    deadline = time.monotonic() + 30
    while True:
        ms = tc.http('GET', '/v1/conversations/%s/messages' % conversation).json()['messages']
        reply = [m for m in ms if m.get('in_reply_to') == sent]
        if reply:
            return sent, reply[0]
        assert time.monotonic() < deadline, 'no reply to %r' % text
        time.sleep(0.05)


def test_the_mission_now_tab_is_its_thread_and_a_reply_reaches_a_row_there(browser, slow):  # noqa: F811
    tc = slow
    check = Checks()
    alpha = _mission(tc, 'Alpha')
    attempt = _running(tc, alpha)
    # tall enough that the attempt's row is on screen below the thread: a row
    # off screen gets no line (A-05), which test_spa_thread covers
    context, page, errors = _context(browser, tc, viewport={'width': 1280, 'height': 1100})
    _go(page, '#/o/mission/%s/now' % alpha)
    tab = page.locator('.mission-now')
    tab.locator('section.conversation').wait_for()
    check(tab.locator('h2', has_text="This mission's conversation").count() == 1, 'the thread is on the tab')
    check(tab.locator('textarea').count() == 1, 'with its composer')
    row = '.mission-now li.execution[data-ref="execution:%s"]' % attempt['id']
    page.locator(row).wait_for()
    first = tab.locator('section.conversation').bounding_box()
    work = page.locator(row).bounding_box()
    check(first['y'] < work['y'], 'the thread stands above what is running')

    # a status asked in the thread links the running attempt, whose row is here
    page.evaluate('q => window.__target = q', row)
    sent, reply = _say(tc, alpha, 'status')
    check({'kind': 'execution', 'id': attempt['id']} in [l['ref'] for l in reply['links']],
          'Core links the reply to the running attempt')
    tab.locator('[data-message="%s"]' % reply['id']).wait_for()
    check(tab.locator('[data-message="%s"]' % sent).count() == 1, 'the turn is in the thread')
    wait(page, lambda: len(_threads(page)) == 1, what='the line starts')
    check(_threads(page)[0]['key'] == reply['id'], 'drawn for the reply, to the attempt')
    wait(page, lambda: len(page.evaluate('window.__ended')) == 1, what='the line ends')
    t = page.evaluate('window.__ended')[0]
    check(t['row'] is not None and t['msg'] is not None, 'from the reply to the attempt on this tab')
    reach = (t['left'] + t['width'] * math.cos(t['angle']),
             t['top'] + t['width'] * math.sin(t['angle']))
    row_box = t['row']
    check(row_box[0] - 4 <= reach[0] <= row_box[2] + 4 and row_box[1] - 4 <= reach[1] <= row_box[3] + 4,
          'it ends on the row of the attempt: %s in %s' % (reach, row_box))
    _quiet_line(page)

    # nothing replays: a reload of the tab draws no line for the same reply
    page.close()
    page = _page(context, tc, errors)
    _go(page, '#/o/mission/%s/now' % alpha)
    page.locator('.mission-now [data-message="%s"]' % reply['id']).wait_for()
    time.sleep(1)
    check(_threads(page) == [], 'a reload draws nothing')

    # a bare verb sent from the tab's own composer is about this mission
    page.locator('.mission-now textarea').fill('pause')
    page.locator('.mission-now').get_by_role('button', name='Send').click()
    deadline = time.monotonic() + 30
    while tc.http('GET', '/v1/missions/' + alpha).json()['state'] != 'PAUSED':
        assert time.monotonic() < deadline, 'the thread\'s "pause" never paused Alpha'
        time.sleep(0.05)
    check(True, 'the composer\'s "pause" paused Alpha')
    check(not errors, 'no console errors: %s' % errors)
    context.close()
    assert check.n >= 11, 'ran %d checks' % check.n


def test_an_approval_card_in_the_thread_decides_it_as_attention_does(browser, deploy):  # noqa: F811
    """P19 S3 (B5): the approval is a card in the mission's thread; its
    Approve sends the turn carrying the card's hash, and Core decides it by
    the SPA's own principal: the mission moves exactly as after Attention."""
    check = Checks()
    mid = _mission(deploy, 'Deploy from the thread')
    _settled(deploy, mid, 'APPROVAL_REQUIRED')
    (a,) = deploy.http('GET', '/v1/approvals?mission=' + mid).json()['approvals']
    context, page, errors = _context(browser, deploy, viewport={'width': 1280, 'height': 1100})
    _go(page, '#/o/mission/%s/now' % mid)
    card = page.locator('.mission-now article[data-approval="%s"]' % a['id']).first
    card.wait_for()
    check(card.get_attribute('data-state') == 'PENDING', 'the card shows the live approval')
    card.get_by_role('button', name='Approve').click()
    _settled(deploy, mid, 'COMPLETED')
    got = deploy.http('GET', '/v1/approvals/' + a['id']).json()
    check(got['state'] in ('APPROVED', 'CONSUMED'), 'Core decided it')
    check(got['decided_by'] != 'archeus' and got['decided_by'] is not None, 'by the poster')
    msgs = deploy.http('GET', '/v1/conversations/%s/messages' % mid).json()['messages']
    turn = [m for m in msgs if m['author'] == 'user' and m['text'] == 'approve']
    check(len(turn) == 1, 'the decision is a turn in the thread')
    page.locator('.mission-now [data-message]', has_text='Approved for').wait_for()
    wait(page, lambda: card.get_attribute('data-state') != 'PENDING', what='the card re-reads')
    check(card.get_attribute('data-state') == got['state'], 'the card says what Core says')
    check(not errors, 'no console errors: %s' % errors)
    context.close()
    assert check.n >= 6, 'ran %d checks' % check.n


def test_the_stop_and_emergency_stop_cards_confirm_what_the_words_only_asked(browser, slow):  # noqa: F811
    """P19 B10 (C-33, G2): `stop` on a running mission answers with a card whose
    Stop mission sends the confirming turn, and Core pauses then cancels it;
    `emergency stop` answers with a card whose button is the strip's command."""
    from archeus.node.local import LocalNode
    check = Checks()
    mid = _mission(slow, 'Stop from the thread')
    _settled(slow, mid, 'EXECUTING')
    _sent, reply = _say(slow, mid, 'stop')
    check([c['type'] for c in reply['cards']] == ['stop'], 'the words only asked')
    context, page, errors = _context(browser, slow, viewport={'width': 1280, 'height': 1100})
    try:
        _go(page, '#/o/mission/%s/now' % mid)
        card = page.locator('.mission-now article[aria-label="stop mission"]').first
        card.wait_for()
        check(slow.http('GET', '/v1/missions/' + mid).json()['state'] == 'EXECUTING',
              'nothing stopped before the confirmation')
        card.get_by_role('button', name='Stop mission').click()
        _settled(slow, mid, 'CANCELLED')
        msgs = slow.http('GET', '/v1/conversations/%s/messages' % mid).json()['messages']
        check(len([m for m in msgs if m['author'] == 'user' and m['text'] == 'stop']) == 2,
              'the confirmation is a turn in the thread')
        _say(slow, mid, 'emergency stop')
        es = page.locator('.mission-now article[aria-label="emergency stop"]').first
        es.wait_for()
        check(slow.http('GET', '/v1/status').json()['armed'] is True, 'the words engaged nothing')
        es.get_by_role('button', name='Emergency stop').click()
        wait(page, lambda: slow.http('GET', '/v1/status').json()['armed'] is False,
             what='the strip\'s command ran')
        es.get_by_text('The emergency stop is engaged.').wait_for()
        check(not errors, 'no console errors: %s' % errors)
    finally:
        context.close()
        LocalNode.clear_estop()
    assert check.n >= 5, 'ran %d checks' % check.n


def test_a_change_card_is_confirmed_through_the_existing_admin_route(browser, slow):  # noqa: F811
    """P19 B10 (ADR-0042 §3, G3): `use` naming an `explicit_only` account
    changes nothing and answers with a change card; its Save preferences runs
    the mission's resources route with Core's body, and the card then closes."""
    check = Checks()
    from archeus.core.domain.ids import new_ulid as key
    assert slow.http('POST', '/v1/policies/profile', body={
        'scope': 'user', 'profile': 'careful', 'idempotency_key': key()}).status == 200
    acc = slow.http('POST', '/v1/accounts', body={'harness_id': 'fake', 'label': 'Shared',
                                                  'auth_kind': 'api_key',
                                                  'idempotency_key': key()}).json()['id']
    assert slow.http('POST', '/v1/resource-policies/' + acc, body={
        'consumption': 'explicit_only', 'idempotency_key': key()}).status == 200
    mid = _mission(slow, 'Widen me')
    _sent, reply = _say(slow, mid, 'use Shared')
    check([c['type'] for c in reply['cards']] == ['change'], 'only proposed')
    prefs = lambda: slow.http('GET', '/v1/missions/' + mid).json().get('resource_preferences') or {}  # noqa: E731
    check(acc not in (prefs().get('preferred_accounts') or []), 'nothing was applied')
    context, page, errors = _context(browser, slow, viewport={'width': 1280, 'height': 1100})
    try:
        _go(page, '#/o/mission/%s/now' % mid)
        card = page.locator('.mission-now article[aria-label="change"]').first
        card.wait_for()
        card.get_by_role('button', name='Save preferences').click()
        wait(page, lambda: acc in (prefs().get('preferred_accounts') or []),
             what='the route applied Core\'s body')
        card.get_by_text('were set again since').wait_for()
        check(not errors, 'no console errors: %s' % errors)
    finally:
        context.close()
    assert check.n >= 3, 'ran %d checks' % check.n
