"""The offline snapshot in a real browser against a real Core (P16 seam S6;
p19-design-gate B7): the SPA keeps exactly the Now composition in IndexedDB
after its reads — no token, no event, no ended mission — and a cold start
with no Core shows it read-only under "Offline — as of <time>" with nothing to
act on. Revoking this client clears it, whether it revokes itself, is revoked
while open, or is revoked while away (read first on the next online start). A
client paired `observe`-only never keeps one. Offline, Needs you and the digest
name what they point at from the kept missions, in the app frame's inset (R13-02).
A check floor keeps a test that silently checks nothing from passing."""

import json

from .conftest import wait
from .test_spa_p16 import FULL, Checks, _go, _mission, _open, _settled, deploy, slow  # noqa: F401 (fixtures)

NOW = ['/v1/status', '/v1/digest', '/v1/attention', '/v1/missions']

#: Never opens the snapshot database unless the app created it: opening it here
#: would create it without its store.
KEPT = """async () => {
  if (!(await indexedDB.databases()).some((d) => d.name === 'archeus-snapshot')) return null;
  const db = await new Promise((r, j) => { const q = indexedDB.open('archeus-snapshot'); q.onsuccess = () => r(q.result); q.onerror = j; });
  const s = db.transaction('now').objectStore('now');
  const get = (q) => new Promise((r) => { q.onsuccess = () => r(q.result); });
  const out = {keys: await get(s.getAllKeys()), values: await get(s.getAll())};
  db.close();
  return out;
}"""

TOKEN = """async () => {
  const db = await new Promise((r) => { const q = indexedDB.open('archeus', 1); q.onsuccess = () => r(q.result); });
  const t = await new Promise((r) => { const q = db.transaction('auth').objectStore('auth').get('device-token'); q.onsuccess = () => r(q.result); });
  db.close();
  return t;
}"""

COMMANDS = 'button, a[href], input, select, textarea, [contenteditable="true"], [tabindex="0"]'


def _kept(page):
    return page.evaluate(KEPT)


def _paths(kept):
    return sorted(v['path'] for v in (kept or {'values': []})['values'])


def _under_the_worker(page):
    page.evaluate('navigator.serviceWorker.ready')
    wait(page, lambda: page.evaluate('!!navigator.serviceWorker.controller'), what='the shell under the worker')
    page.reload()                       # the shell's assets now come through the worker, which keeps them
    page.get_by_role('heading', name='Now', exact=True).wait_for()


def test_an_offline_cold_start_shows_the_last_now_read_only(browser, slow):  # noqa: F811
    tc = slow
    check = Checks()
    done = _mission(tc, 'Stopped by hand')
    _settled(tc, done, 'EXECUTING')
    assert tc.http('POST', '/v1/missions/%s/stop' % done, body={'idempotency_key': 's-' + done}).status == 200
    _settled(tc, done, 'BLOCKED')
    mid = _mission(tc, 'Ship the offline fix')
    _settled(tc, mid, 'EXECUTING')
    context, page, errors = _open(browser, tc)
    page.locator('.now-main li[data-mission="%s"]' % mid).first.wait_for()
    wait(page, lambda: _paths(_kept(page)) == sorted(NOW), what='the Now reads kept')
    kept = _kept(page)
    origin = tc.base_url
    check(sorted(kept['keys']) == sorted('%s %s' % (origin, p) for p in NOW),
          'exactly the Now composition, keyed by the Core origin: %s' % kept['keys'])
    check(all(v['origin'] == origin and v['at'] for v in kept['values']), 'each read with its origin and time')
    check(all(isinstance(v['seq'], int) for v in kept['values']), 'and the event head it was read at')
    missions = next(v for v in kept['values'] if v['path'] == '/v1/missions')['data']['missions']
    check(sorted(m['id'] for m in missions) == sorted([mid, done]),
          'the missions that have not ended: the running one, and the stopped one waiting on a person')
    token = page.evaluate(TOKEN)
    blob = json.dumps(kept)
    check(token and token not in blob, 'no token is kept')
    check('events' not in blob and 'stream' not in blob, 'no event is kept')

    _under_the_worker(page)
    posts = []
    page.on('request', lambda r: posts.append(r.url) if r.method != 'GET' else None)
    context.set_offline(True)
    page.reload()
    snap = page.locator('[data-offline-snapshot]')
    snap.wait_for()
    check(snap.get_by_role('status').inner_text().startswith('Offline — as of '), 'it says it is offline, as of when')
    check(snap.locator('[data-mission="%s"]' % mid).count() == 1, 'the mission it last read')
    check('Ship the offline fix' in snap.inner_text() and snap.locator('[data-mission="%s"]' % done).count() == 0,
          'by its title, and the stopped one not as happening')
    att = next(v for v in kept['values'] if v['path'] == '/v1/attention')['data']
    check(snap.get_by_role('heading', name='Needs you').count() == 1
          and snap.locator('[data-ref]').count() >= len(att['items']), 'and what needed you')
    check(page.locator(COMMANDS).count() == 0, 'no command, link or field is reachable')
    page.keyboard.press('Tab')
    check(page.evaluate('document.activeElement === document.body'), 'the keyboard reaches nothing')
    check(not posts, 'nothing was sent: %s' % posts)
    context.set_offline(False)
    check(not [e for e in errors if 'net::' not in e and 'Failed to load resource' not in e], errors)
    assert check.n >= 14, 'only %d checks ran' % check.n
    context.close()


def test_revoking_this_client_clears_its_snapshot(browser, slow):  # noqa: F811
    tc = slow
    check = Checks()
    mid = _mission(tc, 'Revoke me')
    _settled(tc, mid, 'EXECUTING')

    def kept_now(page):
        page.locator('.now-main li[data-mission="%s"]' % mid).first.wait_for()
        wait(page, lambda: _paths(_kept(page)) == sorted(NOW), what='the Now reads kept')

    # it revokes itself (Control → Clients)
    context, page, _e = _open(browser, tc)
    kept_now(page)
    _go(page, '#/control/devices')
    row = page.locator('li[data-device]:has(.tag:text-is("this client"))')
    row.get_by_role('button', name='Revoke').click()
    page.locator('dialog[open]').get_by_role('button', name='Revoke').click()
    page.get_by_text('access was revoked').first.wait_for(timeout=20000)
    wait(page, lambda: _paths(_kept(page)) == [], what='cleared on leaving')
    check(True, 'leaving this client clears its snapshot')
    context.close()

    # revoked from another client while open
    context, page, _e = _open(browser, tc)
    kept_now(page)
    dev = _device(tc, page)
    _revoke(tc, dev)
    page.get_by_text('This client is signed out').wait_for(timeout=20000)
    wait(page, lambda: _paths(_kept(page)) == [], what='cleared when revoked while open')
    check(True, 'revoked while open: cleared')
    context.close()

    # revoked while away: the next online start reads the revocation first
    context, page, _e = _open(browser, tc)
    kept_now(page)
    dev = _device(tc, page)
    page.close()
    _revoke(tc, dev)
    page = context.new_page()
    page.goto(tc.base_url + '/')
    page.get_by_text('Open Archeus from the desktop app').wait_for()
    check(_paths(_kept(page)) == [], 'revoked while away: cleared before anything is shown')
    check(page.locator('[data-offline-snapshot]').count() == 0, 'and none is shown')
    context.close()
    assert check.n >= 4


def _device(tc, page):
    """This page's own device id, as Core reports it."""
    return page.evaluate("""async () => {
      const db = await new Promise((r) => { const q = indexedDB.open('archeus', 1); q.onsuccess = () => r(q.result); });
      const t = await new Promise((r) => { const q = db.transaction('auth').objectStore('auth').get('device-token'); q.onsuccess = () => r(q.result); });
      db.close();
      return (await (await fetch('/v1/sync', {headers: {Authorization: 'Bearer ' + t}})).json()).client.id;
    }""")


def _revoke(tc, dev):
    r = tc.http('POST', '/v1/devices/%s/revoke' % dev, body={'idempotency_key': 'rv-' + dev})
    assert r.status == 200, r.body


def test_a_client_paired_observe_only_keeps_nothing(browser, slow):  # noqa: F811
    tc = slow
    check = Checks()
    mid = _mission(tc, 'Watched from afar')
    _settled(tc, mid, 'EXECUTING')
    code = tc.http('POST', '/v1/devices/pair/start', body={'name': 'Phone', 'scopes': ['observe']}).json()['code']
    phone = browser.new_context(viewport={'width': 390, 'height': 844})
    page = phone.new_page()
    page.goto(tc.base_url + '/#pair=' + code)
    page.get_by_role('button', name='Pair').click()
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    page.locator('.now-main li[data-mission="%s"]' % mid).first.wait_for()
    _go(page, '#/attention')
    _go(page, '#/now')
    _under_the_worker(page)
    page.wait_for_timeout(1000)
    check(_kept(page) is None or _paths(_kept(page)) == [], 'an observe-only paired client keeps nothing')
    phone.set_offline(True)
    page.reload()
    page.get_by_text('Archeus could not start').wait_for()
    check(page.locator('[data-offline-snapshot]').count() == 0, 'so an offline start shows none')
    phone.close()
    assert check.n >= 2


def test_what_was_read_before_the_client_was_known_is_kept(browser, core):
    """On a quiet Core nothing is read twice: the Now reads that answered before
    this client's own record did are kept from what is already read."""
    check = Checks()
    context = browser.new_context()
    page = context.new_page()
    held, answered = [], set()
    page.route('**/v1/sync', lambda r: held.append(r))
    page.on('response', lambda r: answered.add(r.url.split(core.base_url, 1)[-1]) if r.ok else None)
    page.goto(core.core.launch_url(FULL))
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    wait(page, lambda: set(NOW) <= answered and held, what='the Now reads, with the client still unknown')
    check(_paths(_kept(page)) == [], 'nothing kept while the client is unknown')
    for r in held:
        r.continue_()
    page.unroute('**/v1/sync')
    wait(page, lambda: _paths(_kept(page)) == sorted(NOW), what='kept once the client is known')
    check(True, 'kept from what was already read')
    context.close()
    assert check.n >= 2


def _section(snap, heading):
    return snap.locator('section').filter(has=snap.page.get_by_role('heading', name=heading))


def test_offline_needs_you_names_what_waits_and_sits_in_the_app_frame(browser, deploy):  # noqa: F811
    """R13-02: on a phone, offline, Needs you names the mission waiting for
    approval and the digest names its rows from the kept missions; an ended
    mission is never kept; the view has the app frame's inset and no sideways
    scroll."""
    tc = deploy
    check = Checks()
    ended, waits = _mission(tc, 'Rejected and gone'), _mission(tc, 'Deploy the release notes')
    _settled(tc, ended, 'APPROVAL_REQUIRED')
    _settled(tc, waits, 'APPROVAL_REQUIRED')
    (a,) = [a for a in tc.http('GET', '/v1/approvals?mission=' + ended).json()['approvals']
            if a['state'] == 'PENDING']
    r = tc.http('POST', '/v1/approvals/%s/decide' % a['id'], body={
        'decision': 'reject', 'action_hash': a['action_hash'], 'idempotency_key': 'no-' + ended})
    check(r.status == 200, 'rejected: %s' % r.body)
    _settled(tc, ended, 'CANCELLED')
    context, page, errors = _open(browser, tc, viewport={'width': 390, 'height': 844},
                                  is_mobile=True, has_touch=True)
    wait(page, lambda: _paths(_kept(page)) == sorted(NOW), what='the Now reads kept')
    kept = _kept(page)
    missions = next(v for v in kept['values'] if v['path'] == '/v1/missions')['data']['missions']
    check([m['id'] for m in missions] == [waits], 'the mission waiting for approval is kept, the ended one never')
    frame = page.evaluate("getComputedStyle(document.querySelector('main.main')).paddingLeft")

    _under_the_worker(page)
    context.set_offline(True)
    page.reload()
    snap = page.locator('[data-offline-snapshot]')
    snap.wait_for()
    att = next(v for v in kept['values'] if v['path'] == '/v1/attention')['data']
    (item,) = [i for i in att['items'] if i['kind'] == 'approval' and i['mission_id'] == waits]
    needs = _section(snap, 'Needs you').locator('[data-ref="approval:%s"]' % item['ref']['id'])
    check(needs.count() == 1 and 'Deploy the release notes' in needs.inner_text(),
          'Needs you names the mission the approval is for: %s' % (needs.all_inner_texts(),))
    happening = _section(snap, 'Happening now')
    check(happening.locator('[data-mission="%s"]' % waits).count() == 0, 'a waiting mission is not happening now')
    digest = snap.locator('ul.digest > li')
    rows = dict(zip(digest.evaluate_all('ls => ls.map((l) => l.dataset.ref)'), digest.all_inner_texts()))
    mine = [t for ref, t in rows.items() if ref == 'mission:' + waits]
    check(mine and all(t.startswith('mission Deploy the release notes · ') for t in mine),
          'the digest names a mission by its title: %s' % mine)
    tied = [t for ref, t in rows.items() if ref == 'approval:' + item['ref']['id']]
    check(all(t.startswith('approval for Deploy the release notes · ') for t in tied),
          'and what Attention ties to it by its title: %s' % tied)
    check('Rejected and gone' not in snap.inner_text(), 'nothing names the ended mission')
    check(page.locator(COMMANDS).count() == 0, 'still no command, link or field')
    box = page.evaluate("""() => {
      const v = document.querySelector('[data-offline-snapshot]');
      const ink = [...v.querySelectorAll('h1, h2, p, li')].map((e) => e.getBoundingClientRect());
      return {sw: document.documentElement.scrollWidth, iw: innerWidth, pad: getComputedStyle(v).paddingLeft,
              left: Math.min(...ink.map((b) => b.left)), right: Math.max(...ink.map((b) => b.right))};
    }""")
    check(box['sw'] <= box['iw'], 'no sideways scroll at 390 px: %s' % box)
    check(box['pad'] == frame, "the app frame's inset: %s against %s" % (box['pad'], frame))
    inset = float(frame[:-2])
    check(inset >= 16 and box['left'] >= inset - 0.5 and box['right'] <= box['iw'] - inset + 0.5,
          'text is inset from both edges: %s' % box)
    context.set_offline(False)
    check(not [e for e in errors if 'net::' not in e and 'Failed to load resource' not in e], errors)
    assert check.n >= 12, 'only %d checks ran' % check.n
    context.close()


def test_a_read_whose_body_never_arrives_is_never_data(browser, core):
    """A 200 whose body is cut short (the connection dropped mid-read, as when a
    client goes offline during a read) is a network failure: no view takes it
    for data and the snapshot never keeps it. It was the cause of an
    intermittent "reading 'filter'" page error in the cold-start test."""
    check = Checks()
    context = browser.new_context()
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    def cut(body):
        return lambda route: route.fulfill(status=200, content_type='application/json', body=body)
    page.route('**/v1/approvals', cut('{"approvals": ['))
    page.route('**/v1/digest', cut('{"count": 1, "gro'))
    page.goto(core.core.launch_url(FULL))
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    wait(page, lambda: '/v1/status' in _paths(_kept(page)), what='the reads that did arrive kept')
    page.wait_for_timeout(1000)
    kept = _kept(page)
    check('/v1/digest' not in _paths(kept) and 'invalid_response' not in json.dumps(kept),
          'a cut-short read is never kept: %s' % _paths(kept))
    check(not errors, 'and no view takes it for data: %s' % errors)
    assert check.n >= 2
    context.close()
