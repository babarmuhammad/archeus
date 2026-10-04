"""The offline snapshot in a real browser against a real Core (P16 seam S6;
p19-design-gate B7): the SPA keeps exactly the Now composition in IndexedDB
after its reads — no token, no event, no settled mission — and a cold start
with no Core shows it read-only under "Offline — as of <time>" with nothing to
act on. Revoking this client clears it, whether it revokes itself, is revoked
while open, or is revoked while away (read first on the next online start). A
client paired `observe`-only never keeps one. A check floor keeps a test that
silently checks nothing from passing."""

import json

from .conftest import wait
from .test_spa_p16 import FULL, Checks, _go, _mission, _open, _settled, slow  # noqa: F401 (a fixture)

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
    done = _mission(tc, 'Already settled')
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
    check([m['id'] for m in missions] == [mid], 'the missions as Now shows them, never a settled one')
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
    check('Ship the offline fix' in snap.inner_text() and 'Already settled' not in snap.inner_text(),
          'by its title, and nothing settled')
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
