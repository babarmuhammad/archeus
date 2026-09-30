"""The SPA in a real browser against a real Core (testing-strategy §1 E2E UI).

Needs the built SPA and Playwright's Chromium. Outside the `v1-client` CI job
they may be absent and the tests skip; that job sets ARCHEUS_E2E=1, which
turns a missing prerequisite into a failure — a suite that collects nothing
must not report success."""

import os
import time

import pytest

from archeus.api import server
from v1.judge.http import TempCore

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


def wait(page, fn, timeout=30, what='condition'):
    """Poll *fn*, pumping Playwright: its sync API delivers events only while a
    Playwright call runs, so a bare time.sleep would never see them."""
    deadline = time.monotonic() + timeout
    while not fn():
        assert time.monotonic() < deadline, 'timed out: %s' % what
        page.wait_for_timeout(50)
