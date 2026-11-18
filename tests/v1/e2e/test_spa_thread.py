"""P19.5 R6 in a real browser against a real Core: the thread's T1 form
(ADR-0026 §1, design system §2, rulebook §20, §21 A-05, §34).

A new Archeus message whose links name an object with a row on screen draws
one line in thread ink from the message to that row — once, in at most 600 ms,
and gone; the polite live region says "Archeus updated …"; the message's card
or link carries the change rule (R5's, while Core's digest names the object).
It never replays: not for the same frame heard again, a lost stream, or a
reload. With no row on screen there is no line, only the words. Reduced motion
draws none; forced colours draw it 2 px in Highlight, high contrast 2 px in
the focus colour. The replies come from the control grammar, which answers
without a model call. Mutation-verified by tools/mutate_p19_5.py (N140 onward).
A check floor keeps a test that silently checks nothing from passing."""

import math
import time

from v1.judge.support import FixtureRepo

from .conftest import wait
from .motion import hear, running_animations
from .test_spa_halo import _running
from .test_spa_p16 import FULL, Checks, _go, _mission
from .test_spa_p18 import slow  # noqa: F401 (a fixture)

TRAVEL_MS = 600     # the registry's thread-travel (clients/app/tokens/motion.json)

#: from the first script of every page load: each line that starts drawing and
#: each that ends, with where it is placed and the two boxes it joins then
_WATCH = """(() => {
  window.__threads = [];
  window.__ended = [];
  const seen = (e) => {
    const el = e.target, s = getComputedStyle(el), key = el.dataset.threadLine;
    const box = (q) => { const r = document.querySelector(q)?.getBoundingClientRect(); return r && [r.left, r.top, r.right, r.bottom]; };
    return { key, left: parseFloat(el.style.left), top: parseFloat(el.style.top), width: parseFloat(el.style.width),
      angle: parseFloat(el.style.getPropertyValue('--angle')), height: s.height, ink: s.backgroundColor,
      duration: s.animationDuration, msg: box('[data-message="' + key + '"]'), row: window.__target && box(window.__target) };
  };
  document.addEventListener('animationstart', (e) => { if (e.animationName === 'thread-draw') window.__threads.push(seen(e)); });
  document.addEventListener('animationend', (e) => { if (e.animationName === 'thread-draw') window.__ended.push(seen(e)); });
})()"""


def _say(tc, text):
    r = tc.http('POST', '/v1/conversations/primary/messages',
                body={'text': text, 'idempotency_key': 'say-%f' % time.monotonic()})
    assert r.status == 200, r.body
    sent = r.json()['message_id']
    deadline = time.monotonic() + 30
    while True:
        ms = tc.http('GET', '/v1/conversations/primary/messages').json()['messages']
        reply = [m for m in ms if m.get('in_reply_to') == sent]
        if reply:
            return reply[0]
        assert time.monotonic() < deadline, 'no reply to %r' % text
        time.sleep(0.05)


def _threads(page):
    return page.evaluate('window.__threads')


def _digest(tc):
    return {(g['ref']['kind'], g['ref']['id']) for g in tc.http('GET', '/v1/digest').json()['groups']}


def _page(context, tc, errors):
    """A fresh load of the app in *context*, watched from its first script."""
    page = context.new_page()
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(tc.core.launch_url(FULL))
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    return page


def _context(browser, tc, **opts):
    context = browser.new_context(**opts)
    context.add_init_script(_WATCH)
    errors = []
    return context, _page(context, tc, errors), errors


def _quiet_line(page):
    wait(page, lambda: page.locator('.thread-line').count() == 0, timeout=5, what='the line is gone')
    wait(page, lambda: not running_animations(page), timeout=5, what='nothing animates')


def test_a_reply_draws_its_thread_to_the_row_once(browser, slow, archeus_home):  # noqa: F811
    tc = slow
    check = Checks()
    alpha = _mission(tc, 'Alpha')
    _running(tc, alpha)
    repo = FixtureRepo.create('layered-python', str(archeus_home.parent))
    r = tc.http('POST', '/v1/projects', body={'name': 'Atlas', 'root_paths': [repo.path], 'idempotency_key': 'p-%f' % time.time()})
    assert r.status == 200, r.body
    atlas = r.json()['project']['id']
    context, page, errors = _context(browser, tc)
    _go(page, '#/now')
    row = '.now-main li[data-mission="%s"]' % alpha
    page.locator(row).wait_for()

    # a reply that touched Alpha, whose row is on screen: one line, message → row
    page.evaluate('q => window.__target = q', row)
    reply = _say(tc, 'reprioritise Alpha to 5')
    check([l['ref'] for l in reply['links']] == [{'kind': 'mission', 'id': alpha}], 'Core links the reply to Alpha')
    wait(page, lambda: len(_threads(page)) == 1, what='the line starts')
    t = _threads(page)[0]
    check(t['key'] == reply['id'], 'drawn for the reply')
    check(t['duration'] == '%gs' % (TRAVEL_MS / 1000), 'in %s' % t['duration'])
    wait(page, lambda: len(page.evaluate('window.__ended')) == 1, what='the line ends')
    t = page.evaluate('window.__ended')[0]      # where it lands, after whatever moved the page meanwhile
    check(t['key'] == reply['id'], 'the same line ends')
    msg, target = t['msg'], t['row']
    toward_left = (target[0] + target[2]) / 2 < (msg[0] + msg[2]) / 2
    start = (msg[0] if toward_left else msg[2], (msg[1] + msg[3]) / 2)
    end = (t['left'] + t['width'] * math.cos(t['angle']), t['top'] + t['width'] * math.sin(t['angle']))
    want = (target[2] if toward_left else target[0], (target[1] + target[3]) / 2)
    check(abs(t['left'] - start[0]) < 1 and abs(t['top'] - start[1]) < 1, 'it leaves the message: %s vs %s' % ((t['left'], t['top']), start))
    check(math.dist(end, want) < 2, 'it reaches Alpha\'s row: %s vs %s' % (end, want))
    thread = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--thread').trim()")
    rgb = 'rgb(%d, %d, %d)' % tuple(int(thread.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
    check(t['ink'] == rgb and t['height'] in ('1px', '1.5px'), 'a fine line in thread ink: %s %s' % (t['ink'], t['height']))
    live = page.locator('#live-polite')
    wait(page, lambda: live.text_content() == 'Archeus updated mission Alpha', what='the live region says it')
    check(True, 'the live region says it')
    _quiet_line(page)
    card = page.locator('[data-message="%s"] a.card[data-ref="mission:%s"]' % (reply['id'], alpha))
    on = ('mission', alpha) in _digest(tc)
    check(on and card.get_attribute('data-thread') == 'changed' and 'changed since you looked' in card.text_content(),
          'the card carries the change rule while the digest names Alpha')

    # never again: the same frame heard again, a lost stream, a reload
    hear(page, {'id': 10 ** 9, 'event': 'message.created', 'data': {'subject': {'kind': 'message', 'id': reply['id']}}})
    hear(page, {'event': 'stream-lost'})
    hear(page, {'event': 'stream-open'})
    page.wait_for_timeout(1500)
    check(len(_threads(page)) == 1, 'heard again: %d lines' % len(_threads(page)))
    # the app loaded afresh (a refresh, without aborting the page under test)
    page = _page(context, tc, errors)
    _go(page, '#/now')
    page.locator(row).wait_for()
    live = page.locator('#live-polite')
    page.wait_for_timeout(1500)
    check(_threads(page) == [] and page.locator('.thread-line').count() == 0, 'a fresh load replays nothing')

    # a link with no card is shown as one, and draws the same way
    why = _say(tc, 'why %s' % alpha)
    # (P19 B10: its one card is the route decision's; Alpha stays a bare link)
    check(not [c for c in why['cards'] if c['ref']['id'] == alpha]
          and {'kind': 'mission', 'id': alpha} in [l['ref'] for l in why['links']],
          'Core\'s "why" links Alpha without a card')
    bare = page.locator('[data-message="%s"] a.card[data-ref="mission:%s"]' % (why['id'], alpha))
    bare.wait_for()
    check('mission Alpha' in bare.text_content(), 'named as a person reads it: %s' % bare.text_content())
    wait(page, lambda: [x['key'] for x in _threads(page)] == [why['id']], what='its line')
    _quiet_line(page)

    # nothing of it on screen: no line, only the words
    page.get_by_role('button', name='Dismiss').click()
    # the running mission keeps adding to the digest; Atlas does not
    wait(page, lambda: page.locator('.now-main [data-ref="project:%s"]' % atlas).count() == 0, what='Atlas leaves the digest')
    status = _say(tc, 'status Atlas')
    check({'kind': 'project', 'id': atlas} in [l['ref'] for l in status['links']], 'Core links the reply to Atlas')
    page.locator('[data-message="%s"]' % status['id']).wait_for()
    check(page.locator('.now-main [data-ref="project:%s"]' % atlas).count() == 0, 'Atlas has no row on Now')
    page.wait_for_timeout(1500)
    check([x['key'] for x in _threads(page)] == [why['id']], 'no row on screen: no line')
    wait(page, lambda: (live.text_content() or '').startswith('Archeus updated project Atlas'), timeout=15, what='still said in words')
    check(True, 'said in words')
    check(not errors, errors)
    context.close()

    # reduced motion: no line at all; the words and the card stay
    context, page, errors = _context(browser, tc, reduced_motion='reduce')
    _go(page, '#/now')
    page.locator(row).wait_for()
    quiet = _say(tc, 'reprioritise Alpha to 7')
    page.locator('[data-message="%s"]' % quiet['id']).wait_for()
    page.wait_for_timeout(1500)
    check(_threads(page) == [] and page.locator('.thread-line').count() == 0, 'reduced motion: no line')
    wait(page, lambda: page.locator('#live-polite').text_content() == 'Archeus updated mission Alpha', what='reduced motion: the words')
    check(page.locator('[data-message="%s"] a.card[data-ref="mission:%s"]' % (quiet['id'], alpha)).count() == 1, 'reduced motion: the card')
    check(not errors, errors)
    context.close()

    # forced colours: 2 px in Highlight; high contrast: 2 px in the focus colour
    for opts, ink in (({'forced_colors': 'active'}, None), ({'contrast': 'more'}, '--focus')):
        context, page, errors = _context(browser, tc, **opts)
        _go(page, '#/now')
        page.locator(row).wait_for()
        r = _say(tc, 'reprioritise Alpha to %d' % (8 + len(opts)))
        wait(page, lambda p=page: len(_threads(p)) == 1, what='%s: the line' % opts)
        t = _threads(page)[0]
        check(t['key'] == r['id'] and t['height'] == '2px', '%s: 2 px, not %s' % (opts, t['height']))
        if ink:
            v = page.evaluate("v => getComputedStyle(document.documentElement).getPropertyValue(v).trim()", ink).lstrip('#')
            check(t['ink'] == 'rgb(%d, %d, %d)' % tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)), '%s: in the focus colour %s' % (opts, t['ink']))
        else:
            hl = page.evaluate("() => { const e = document.createElement('i'); e.style.color = 'Highlight'; document.body.append(e); const c = getComputedStyle(e).color; e.remove(); return c; }")
            check(t['ink'] == hl, '%s: in Highlight %s vs %s' % (opts, t['ink'], hl))
        _quiet_line(page)
        check(not errors, errors)
        context.close()
    assert check.n >= 24, 'ran %d checks' % check.n
