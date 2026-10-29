"""P19.5 R11 in a real browser against a real Core: the command palette
(rulebook §18; D-12, rulebook §46.1).

Ctrl+K opens it; ↑/↓ move the active option (aria-activedescendant,
aria-selected) and Enter takes it. A mission's actions are the same Core verbs
as its buttons, each saying its effect first from Core's live work. While
connected, typing asks Core's search and the hits are Core's (P21 D7); offline
the hits come from what this client has read and no search is sent. "Tell Archeus" reuses
its key after a network failure. Without a connection or the control scope an
action says why and sends nothing. Mutation-verified by tools/mutate_p19_5.py.
Check floors keep a test that silently checks nothing from passing."""

import json

from .conftest import wait
from .test_spa_p16 import Checks, _go, _open, _settled
from .test_spa_p18 import slow  # noqa: F401 (a fixture)
from .test_spa_pause_all import _executing


def _hits(page):
    return page.locator('#cmd-hits [role="option"]')


def _open_palette(page):
    page.keyboard.press('Control+K')
    try:
        page.locator('#cmd').wait_for(timeout=4000)
    except Exception:
        print('DIAG', page.evaluate('''() => ({hash: location.hash, open: document.querySelector('dialog.command').open, active: document.activeElement && (document.activeElement.tagName + '.' + document.activeElement.className), modal: [...document.querySelectorAll('dialog[open]')].length, title: document.title})'''))
        page.keyboard.press('Control+K')
        page.wait_for_timeout(1000)
        print('DIAG2', page.evaluate('() => document.querySelector("dialog.command").open'))
        raise


def test_the_palette_moves_by_arrows_and_acts_by_cores_verbs(browser, slow):  # noqa: F811
    check = Checks()
    m1, m2 = _executing(slow, 'Ship the chart'), _executing(slow, 'Write the notes')
    r = slow.http('POST', '/v1/missions/%s/pause' % m2, body={'idempotency_key': 'p2'})
    assert r.status == 200, r.body
    _settled(slow, m2, 'PAUSED')
    context, page, errors = _open(browser, slow)
    _go(page, '#/work')
    page.locator('main [data-mission="%s"]' % m2).first.wait_for()
    reads = []
    page.on('request', lambda r: reads.append(r.url) if '/v1/' in r.url and 'events' not in r.url else None)
    _open_palette(page)
    page.keyboard.type('the chart')
    wait(page, lambda: [u for u in reads if '/v1/search?q=' in u], what='a Core search')
    check(True, "typing asks Core's search (D7)")
    labels = _hits(page).all_inner_texts()
    live = len([x for x in slow.http('GET', '/v1/status').json()['live'] if x['mission_id'] == m1])
    want = '%d running %s' % (live, 'attempt pauses' if live == 1 else 'attempts pause')
    check(labels == ['Mission: Ship the chart', 'Pause “Ship the chart” — %s' % want], 'the mission and its action, with its effect: %s' % labels)
    box = page.locator('#cmd')
    check(box.get_attribute('role') == 'combobox' and box.get_attribute('aria-controls') == 'cmd-hits', 'a combobox over the list')
    check(box.get_attribute('aria-activedescendant') == 'cmd-opt-0' and _hits(page).nth(0).get_attribute('aria-selected') == 'true',
          'the first hit is active')
    page.keyboard.press('ArrowDown')
    check(box.get_attribute('aria-activedescendant') == 'cmd-opt-1' and _hits(page).nth(1).get_attribute('aria-selected') == 'true'
          and _hits(page).nth(0).get_attribute('aria-selected') == 'false', '↓ moves the active hit')
    page.keyboard.press('ArrowDown')
    check(box.get_attribute('aria-activedescendant') == 'cmd-opt-0', '↓ wraps round')
    page.keyboard.press('ArrowUp')
    check(box.get_attribute('aria-activedescendant') == 'cmd-opt-1', '↑ moves back')
    page.keyboard.press('Enter')
    _settled(slow, m1, 'PAUSED')
    check(True, 'Enter on "Pause" pauses the mission in Core, by its own verb')
    page.locator('dialog.command [role="status"]').wait_for()
    check('was sent' in page.locator('dialog.command [role="status"]').inner_text(), 'it says it was sent, not that it is done')

    # the second mission resumes from the palette
    box.fill('the notes')
    wait(page, lambda: any(h.startswith('Resume “Write the notes”') for h in _hits(page).all_inner_texts()), what='Resume offered')
    _hits(page).filter(has_text='Resume').click()
    _settled(slow, m2, 'EXECUTING')
    check(True, 'a click on "Resume" resumes it')

    # the hits are Core's answer, not this client's lists (D7)
    page.route('**/v1/search?*', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(
        {'missions': [], 'projects': [{'id': 'prj_core_only', 'name': 'chart from Core only'}], 'knowledge': []})))
    box.fill('chart from')
    wait(page, lambda: 'Project: chart from Core only' in _hits(page).all_inner_texts(), what='a hit only Core knows')
    check(True, "a hit only Core's search answered is shown")
    page.unroute('**/v1/search?*')

    # going to an object closes the palette
    box.fill('the chart')
    page.keyboard.press('Enter')
    wait(page, lambda: page.evaluate('() => location.hash') == '#/o/mission/' + m1, what='Enter goes to the mission')
    check(page.locator('dialog.command[open]').count() == 0, 'and closes the palette')

    # Tell Archeus: a network failure keeps the key; an answer brings a new one
    told = []
    fail = {'n': 1}

    def route(r):
        told.append(json.loads(r.request.post_data or '{}').get('idempotency_key'))
        if fail['n']:
            fail['n'] -= 1
            r.abort()
        else:
            r.continue_()
    page.route('**/v1/conversations/primary/messages', lambda r: route(r) if r.request.method == 'POST' else r.continue_())
    _open_palette(page)
    page.locator('#cmd').fill('write a weekly digest')
    tell = page.get_by_role('button', name='Tell Archeus: “write a weekly digest”')
    tell.click()
    wait(page, lambda: len(told) == 1, what='the first try')
    page.locator('dialog.command [role="status"]', has_text='could not be reached').wait_for()
    tell.click()
    wait(page, lambda: len(told) == 2, what='the retry')
    check(told[0] == told[1], 'the retry after a network failure carries the same key')
    page.locator('dialog.command [role="status"]', has_text='Sent to Archeus').wait_for()
    page.locator('#cmd').fill('and one more thing')
    page.get_by_role('button', name='Tell Archeus: “and one more thing”').click()
    wait(page, lambda: len(told) == 3, what='a new message')
    check(told[2] != told[1], 'a new message after an answer has a new key')
    page.unroute('**/v1/conversations/primary/messages')
    page.keyboard.press('Escape')

    # offline: an action says why and sends nothing
    posts = []
    page.on('request', lambda r: posts.append(r.url) if r.method == 'POST' and '/v1/missions/' in r.url else None)
    context.set_offline(True)
    page.wait_for_timeout(300)
    searched = []
    page.on('request', lambda r: searched.append(r.url) if '/v1/search' in r.url else None)
    _open_palette(page)
    page.locator('#cmd').fill('the chart')
    act = _hits(page).filter(has_text='Resume')
    act.wait_for()
    check('Not connected' in act.inner_text() and act.get_attribute('aria-disabled') == 'true', 'offline: it says why')
    act.dispatch_event('click')
    page.wait_for_timeout(400)
    check(slow.http('GET', '/v1/missions/' + m1).json()['state'] == 'PAUSED', 'nothing changed')
    check(not posts, 'and nothing was even tried: %s' % posts)
    check(not searched, 'offline, no search is sent; the hits are the cached reads: %s' % searched)
    context.set_offline(False)
    check(not [e for e in errors if 'ERR_FAILED' not in e and 'net::' not in e], errors)
    context.close()
    assert check.n >= 19
