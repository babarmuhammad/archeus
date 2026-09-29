"""K1 — the SPA's walking-skeleton guarantees, kept through P16 (p3.5b design
gate §9, §10 K1; SK "rendered by the SPA"): the launch bootstrap, no polling,
one stream per browser, a Core restart survived, and a read-only launch device
that the page does not pretend can act. P16 moved the views from two tabs to
the navigation table (p16-design-gate §4.2)."""

import os
import re

from archeus.api import server
from v1.judge.http import request

from .conftest import INDEX, need, wait


def _mission(core, title):
    r = core.http('POST', '/v1/missions', body={'title': title, 'objective': 'o',
                                                'idempotency_key': 'k-' + title})
    assert r.status == 200
    return r.json()['id']


READ_TOKEN = """() => new Promise((ok, fail) => {
  const r = indexedDB.open('archeus', 1);
  r.onerror = () => fail(r.error);
  r.onsuccess = () => {
    const g = r.result.transaction('auth').objectStore('auth').get('device-token');
    g.onsuccess = () => ok(g.result || null);
  };
})"""


def test_the_built_page_has_no_inline_script_and_no_inline_handler():
    need(os.path.isfile(INDEX), 'the SPA is not built')
    html = open(INDEX, encoding='utf-8').read()
    scripts = re.findall(r'<script\b([^>]*)>(.*?)</script>', html, re.S)
    assert scripts and all('src=' in attrs and not body.strip() for attrs, body in scripts)
    assert not re.search(r'\son[a-z]+\s*=', html)
    for name in os.listdir(os.path.join(server.STATIC_DIR, 'assets')):
        assert not name.endswith('.map'), name


def test_launch_now_work_and_live_updates_through_the_stream(browser, core):
    context = browser.new_context()
    urls, problems = [], []
    context.on('request', lambda r: urls.append((r.method, r.url)))
    page = context.new_page()
    page.on('console', lambda m: problems.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: problems.append(str(e)))

    launch = core.core.launch_url()                  # the default grant: observe only
    code = launch.split('#launch=', 1)[1]
    page.goto(launch)
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    assert '#' not in page.url and code not in page.url           # the fragment is gone
    token = page.evaluate(READ_TOKEN)
    assert token and token.startswith('dev_')
    page.get_by_text('Nothing is in progress.').wait_for()
    assert page.get_by_text('walking skeleton: fake harness, stub policy').count() == 0

    # the device the launch made is read-only: Core refuses it, and the page
    # offers no command it could send — every one is disabled, with the reason
    r = request(core.base_url, 'POST', '/v1/missions', token=token,
                body={'title': 'x', 'objective': 'o', 'idempotency_key': 'nope'})
    assert (r.status, r.json()['detail']) == (403, {'scope': 'control'})
    page.get_by_text('does not hold the “control” scope').first.wait_for()
    for b in page.locator('.action button').all():
        assert b.is_disabled()

    # SSE alone: no timer re-queries the list; only an event does
    wait(page, lambda: any(u.endswith('/v1/events/stream') for _m, u in urls), what='the stream')
    page.wait_for_timeout(1500)
    listed = sum(u.endswith('/v1/missions') for _m, u in urls)
    assert listed >= 1
    page.wait_for_timeout(2500)
    assert sum(u.endswith('/v1/missions') for _m, u in urls) == listed, 'the page polls'

    mid = _mission(core, 'Walk')
    page.get_by_role('link', name='Work').click()
    row = page.locator('li[data-mission="%s"]' % mid)
    row.wait_for()
    wait(page, lambda: row.get_attribute('data-state') == 'COMPLETED', what='COMPLETED in the list')
    assert sum(u.endswith('/v1/missions') for _m, u in urls) > listed

    # every state on screen is one Core returned
    states = {m['id']: m['state'] for m in core.client().list_missions()}
    for li in page.locator('li[data-mission]').all():
        assert li.get_attribute('data-state') == states[li.get_attribute('data-mission')]
        assert li.locator('.state').get_attribute('data-state') == states[li.get_attribute('data-mission')]

    assert not [u for _m, u in urls if code in u or token in u or 'token=' in u]
    assert not problems, problems
    context.close()


def test_two_tabs_share_one_stream_and_the_follower_takes_over(browser, core):
    context = browser.new_context()
    streams = []
    context.on('request', lambda r: streams.append(r) if r.url.endswith(
        '/v1/events/stream') else None)
    first = context.new_page()
    first.goto(core.core.launch_url())
    first.get_by_role('link', name='Work').wait_for()
    second = context.new_page()
    second.goto(core.base_url + '/')                  # no code: the stored token
    second.get_by_role('link', name='Work').click()
    second.wait_for_timeout(1500)
    assert len(streams) == 1, 'each tab opened its own stream'

    mid = _mission(core, 'Shared')
    for page in (first, second):                      # the follower hears it too
        page.get_by_role('link', name='Work').click()
        page.locator('li[data-mission="%s"]' % mid).wait_for()

    first.close()                                     # the leader goes
    wait(second, lambda: len(streams) >= 2, what='the follower to open the stream')
    again = _mission(core, 'After')
    second.locator('li[data-mission="%s"]' % again).wait_for()
    context.close()


def test_the_page_reconnects_after_core_restarts(browser, core):
    context = browser.new_context()
    page = context.new_page()
    page.goto(core.core.launch_url())
    page.get_by_role('link', name='Work').click()
    first = _mission(core, 'Before')
    page.locator('li[data-mission="%s"]' % first).wait_for()
    core.restart(kill=False)
    after = _mission(core, 'After')
    page.locator('li[data-mission="%s"]' % after).wait_for(timeout=30000)
    context.close()


def test_without_a_token_or_code_the_page_says_how_to_open_archeus(browser, core):
    page = browser.new_page()
    page.goto(core.base_url + '/#launch=not-a-real-code')
    page.get_by_text('archeus core --open').wait_for()
    assert '#' not in page.url
