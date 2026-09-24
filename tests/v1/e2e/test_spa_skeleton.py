"""K1 — the SPA skeleton in a real browser against a real Core (p3.5b design
gate §9, §10 K1; SK "rendered by the SPA").

Needs the built SPA and Playwright's Chromium. Outside the `v1-client` CI job
they may be absent and the test skips; that job sets ARCHEUS_E2E=1, which
turns a missing prerequisite into a failure — a suite that collects nothing
must not report success."""

import os
import re
import time

import pytest

from archeus.api import server
from v1.judge.http import TempCore, request

REQUIRED = os.environ.get('ARCHEUS_E2E') == '1'
INDEX = os.path.join(server.STATIC_DIR, 'index.html')


def _need(ok, why):
    if not ok:
        if REQUIRED:
            pytest.fail(why)
        pytest.skip(why)


@pytest.fixture
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _need(False, 'playwright is not installed')
    _need(os.path.isfile(INDEX), 'the SPA is not built: npm ci && npm run build in clients/app')
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home).start()
    yield tc
    tc.stop()


def _mission(core, title):
    r = core.http('POST', '/v1/missions', body={'title': title, 'objective': 'o',
                                                'idempotency_key': 'k-' + title})
    assert r.status == 200
    return r.json()['id']


def _wait(page, fn, timeout=30, what='condition'):
    """Poll *fn*, pumping Playwright: its sync API delivers events only while a
    Playwright call runs, so a bare time.sleep would never see them."""
    deadline = time.monotonic() + timeout
    while not fn():
        assert time.monotonic() < deadline, 'timed out: %s' % what
        page.wait_for_timeout(50)


READ_TOKEN = """() => new Promise((ok, fail) => {
  const r = indexedDB.open('archeus', 1);
  r.onerror = () => fail(r.error);
  r.onsuccess = () => {
    const g = r.result.transaction('auth').objectStore('auth').get('device-token');
    g.onsuccess = () => ok(g.result || null);
  };
})"""


def test_the_built_page_has_no_inline_script_and_no_inline_handler():
    _need(os.path.isfile(INDEX), 'the SPA is not built')
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

    launch = core.core.launch_url()
    code = launch.split('#launch=', 1)[1]
    page.goto(launch)
    page.get_by_role('tab', name='Now').wait_for()
    assert '#' not in page.url and code not in page.url           # the fragment is gone
    token = page.evaluate(READ_TOKEN)
    assert token and token.startswith('dev_')
    page.get_by_text('walking skeleton: fake harness, stub policy').wait_for()
    assert page.get_by_text('Nothing is in progress.').is_visible()

    # the device the launch made is read-only, and the page offers no command
    r = request(core.base_url, 'POST', '/v1/missions', token=token,
                body={'title': 'x', 'objective': 'o', 'idempotency_key': 'nope'})
    assert (r.status, r.json()['detail']) == (403, {'scope': 'control'})
    assert page.locator('button').count() == 2                   # the two tabs, nothing else
    assert page.locator('form, input, textarea, select').count() == 0

    # SSE alone: no timer re-queries the list; only an event does
    _wait(page, lambda: any(u.endswith('/v1/events/stream') for _m, u in urls),
          what='the stream')
    page.wait_for_timeout(1500)
    listed = sum(u.endswith('/v1/missions') for _m, u in urls)
    assert listed >= 1
    page.wait_for_timeout(2500)
    assert sum(u.endswith('/v1/missions') for _m, u in urls) == listed, 'the page polls'

    mid = _mission(core, 'Walk')
    page.get_by_role('tab', name='Work').click()
    row = page.locator('li[data-mission="%s"] .state' % mid)
    row.wait_for()
    _wait(page, lambda: row.text_content() == 'COMPLETED', what='COMPLETED in the list')
    assert sum(u.endswith('/v1/missions') for _m, u in urls) > listed

    # every state on screen is one Core returned
    states = {m['id']: m['state'] for m in core.client().list_missions()}
    for li in page.locator('li[data-mission]').all():
        assert li.locator('.state').text_content() == states[li.get_attribute('data-mission')]

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
    first.get_by_role('tab', name='Work').wait_for()
    second = context.new_page()
    second.goto(core.base_url + '/')                  # no code: the stored token
    second.get_by_role('tab', name='Work').click()
    second.wait_for_timeout(1500)
    assert len(streams) == 1, 'each tab opened its own stream'

    mid = _mission(core, 'Shared')
    for page in (first, second):                      # the follower hears it too
        page.get_by_role('tab', name='Work').click()
        page.locator('li[data-mission="%s"]' % mid).wait_for()

    first.close()                                     # the leader goes
    _wait(second, lambda: len(streams) >= 2, what='the follower to open the stream')
    again = _mission(core, 'After')
    second.locator('li[data-mission="%s"]' % again).wait_for()
    context.close()


def test_the_page_reconnects_after_core_restarts(browser, core):
    context = browser.new_context()
    page = context.new_page()
    page.goto(core.core.launch_url())
    page.get_by_role('tab', name='Work').click()
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
