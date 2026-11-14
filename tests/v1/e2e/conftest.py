"""The SPA in a real browser against a real Core (testing-strategy §1 E2E UI).

Needs the built SPA and Playwright's Chromium. Outside the `v1-client` CI job
they may be absent and the tests skip; that job sets ARCHEUS_E2E=1, which
turns a missing prerequisite into a failure — a suite that collects nothing
must not report success."""

import os
import time
from urllib.parse import urlsplit

import pytest

from archeus.api import server
from v1.judge.http import TUNNEL, TempCore, request

REQUIRED = os.environ.get('ARCHEUS_E2E') == '1'
INDEX = os.path.join(server.STATIC_DIR, 'index.html')


def need(ok, why):
    if not ok:
        if REQUIRED:
            pytest.fail(why)
        pytest.skip(why)


@pytest.fixture
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        need(False, 'playwright is not installed')
    need(os.path.isfile(INDEX), 'the SPA is not built: npm ci && npm run build in clients/app')
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home).start()
    yield tc
    tc.stop()


#: What a TLS-terminating tunnel replaces on the way in: the peer stays
#: loopback, the Host and the Origin are the remote host's (p15 §8.2-8.3).
_HOP = {'host', 'origin', 'referer', 'content-length', 'connection',
        'sec-fetch-site', 'sec-fetch-mode', 'sec-fetch-dest'}


class Tunnel:
    """A paired browser's commands through the configured remote host (T-053
    branch P, Q4-A), in process: Playwright cannot stream a fulfilled response,
    so reads and the event stream stay on the loopback Host, where a paired
    credential keeps its observe routes. Every request that carries a
    credential and is not a read is sent to Core as the tunnel delivers it:
    Host and Origin the remote host's, everything else the browser's. Core
    decides; nothing here grants anything. Host policy only, never an
    attestation of a real tunnel hop."""

    def __init__(self, tc):
        self.tc, self.token, self.sent = tc, None, []

    def __call__(self, route):
        req = route.request
        cred = req.headers.get('authorization')
        if cred:
            self.token = cred.split(' ', 1)[1]
        if req.method == 'GET' or not cred:
            route.continue_()
            return
        url = urlsplit(req.url)
        headers = {k: v for k, v in req.headers.items() if k.lower() not in _HOP}
        headers.update({'Host': TUNNEL, 'Origin': 'https://' + TUNNEL,
                        'Sec-Fetch-Site': 'same-origin'})
        r = request(self.tc.base_url, req.method,
                    url.path + ('?' + url.query if url.query else ''),
                    headers=headers, raw=req.post_data_buffer)
        self.sent.append((req.method, url.path, r.status))
        route.fulfill(status=r.status, body=r.body,
                      headers={k: v for k, v in r.headers.items()
                               if k.lower() not in ('content-length', 'transfer-encoding',
                                                    'connection')})


def wait(page, fn, timeout=30, what='condition'):
    """Poll *fn*, pumping Playwright: its sync API delivers events only while a
    Playwright call runs, so a bare time.sleep would never see them."""
    deadline = time.monotonic() + timeout
    while not fn():
        assert time.monotonic() < deadline, 'timed out: %s' % what
        page.wait_for_timeout(50)
