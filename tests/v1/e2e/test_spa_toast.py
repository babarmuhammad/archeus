"""P19.5 R9 in a real browser against a real Core: the completion toast
(rulebook §17, §21 A-13; D-8, rulebook §46.1).

A toast appears only when work that ran at least 10 s finishes while nothing
on screen shows it: an attempt Core reads as ENDED_OK, its own started_at and
ended_at 10 s or more apart, its mission's row and inspector off screen. It is
said in a status region mounted at boot, fades in, stays 4 s and fades out
(still under reduced motion), never replays for an event heard again, and is
never the only signal. Mutation-verified by tools/mutate_p19_5.py. Check
floors keep a test that silently checks nothing from passing."""

import time
from datetime import datetime

import pytest

from archeus.core import engine, ports, runtime
from archeus.harnesses.fake import FakeHarness
from claude_sessions import proc
from v1.judge.http import TempCore

from .conftest import wait
from .motion import hear
from .test_spa_p16 import Checks, _go, _mission, _open, _settled

TEN = {'work': [{'emit': {'type': 'working'}}, {'sleep': 11}]}
TOAST = '.toast-region [data-toast]'


@pytest.fixture
def ten(archeus_home):
    """A Core whose one task runs for 11 s on the fake harness, then ends well."""
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(TEN),
        executors=[FakeHarness()])).start()
    yield tc
    for p in list(tc.core.manager._procs.values()):
        proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
    tc.stop(kill=True)


def _ended(tc, mid):
    """Core's own record of the mission's ended attempt and its end event."""
    deadline = time.monotonic() + 60
    while True:
        for e in tc.http('GET', '/v1/events?after=0&limit=1000').json()['events']:
            if e['type'] == 'execution.ended':
                x = tc.http('GET', '/v1/executions/' + e['subject']['id']).json()
                if x['mission_id'] == mid:
                    return x, e['seq']
        assert time.monotonic() < deadline, 'the attempt never ended'
        time.sleep(0.2)


def _ran(x):
    p = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()  # noqa: E731
    return p(x['ended_at']) - p(x['started_at'])


def test_long_work_finishing_off_screen_gives_one_toast_that_leaves(browser, ten):
    check = Checks()
    context, page, errors = _open(browser, ten)
    region = page.locator('.toast-region')
    check(region.count() == 1 and region.get_attribute('role') == 'status', 'the status region is there from boot')
    check(page.locator(TOAST).count() == 0, 'and empty')
    _go(page, '#/control/autonomy')                      # no row of the mission here
    mid = _mission(ten, 'Ship the chart')
    toast = page.locator(TOAST)
    toast.wait_for(timeout=60_000)
    x, seq = _ended(ten, mid)
    check(x['state'] == 'ENDED_OK' and _ran(x) >= 10, 'Core: the attempt ended well after %.1f s' % _ran(x))
    check(toast.get_attribute('data-toast') == str(seq), 'the toast presents Core\'s end event')
    check(toast.inner_text() == 'Finished: “Ship the chart”, attempt 1. Open it', toast.inner_text())
    check(toast.get_by_role('link', name='Open it').get_attribute('href') == '#/o/mission/' + mid, 'it links the mission')
    check(page.evaluate("() => getComputedStyle(document.querySelector('.toast')).animationName") == 'toast-in',
          'it fades in by the registered motion')
    check(page.locator('.toast-region').count() == 1 and page.locator('.toast').count() == 1, 'one at a time')
    t0 = time.monotonic()
    wait(page, lambda: toast.count() == 0, what='the toast leaves', timeout=10)
    gone = time.monotonic() - t0
    check(3.0 <= gone <= 6.5, 'it stays about 4 s: %.1f s' % gone)
    check(page.evaluate('() => document.getAnimations().length') == 0, 'and leaves nothing running')

    # nothing replays: the same end heard again is no toast; a newer one is
    hear(page, {'id': seq, 'event': 'execution.ended', 'data': {'subject': {'kind': 'execution', 'id': x['id']}}})
    page.wait_for_timeout(800)
    check(toast.count() == 0, 'the same end heard again gives no toast')
    hear(page, {'id': seq - 1, 'event': 'execution.ended', 'data': {'subject': {'kind': 'execution', 'id': x['id']}}})
    page.wait_for_timeout(800)
    check(toast.count() == 0, 'an older end gives no toast')
    hear(page, {'id': seq + 1, 'event': 'execution.ended', 'data': {'subject': {'kind': 'execution', 'id': x['id']}}})
    toast.wait_for(timeout=5000)
    check(True, 'a newer end does (positive control)')

    # on screen, the row says it: the mission's row on Work, no toast
    wait(page, lambda: toast.count() == 0, what='the control toast leaves', timeout=10)
    _go(page, '#/work')
    m2 = _mission(ten, 'Write the notes')
    page.locator('[data-mission="%s"]' % m2).first.wait_for(timeout=10_000)
    x2, _ = _ended(ten, m2)
    check(x2['state'] == 'ENDED_OK' and _ran(x2) >= 10, 'Core: the second attempt ended well too')
    page.wait_for_timeout(1500)
    check(toast.count() == 0, 'its row on screen: no toast')
    check(not errors, errors)
    context.close()
    assert check.n >= 16


def test_reduced_motion_shows_the_toast_still(browser, ten):
    check = Checks()
    context, page, errors = _open(browser, ten, reduced_motion='reduce')
    _go(page, '#/world')
    _mission(ten, 'Quietly')
    toast = page.locator(TOAST)
    toast.wait_for(timeout=60_000)
    check(toast.get_attribute('data-still') == 'true', 'no fade under reduced motion')
    check(page.evaluate('() => document.getAnimations().length') == 0, 'nothing animates')
    wait(page, lambda: toast.count() == 0, what='it leaves at once when its time is up', timeout=10)
    check(True, 'and it still leaves')
    context.close()
    assert check.n >= 3


def test_short_work_never_celebrates(browser, core):
    check = Checks()
    context, page, errors = _open(browser, core)
    _go(page, '#/world')
    mid = _mission(core, 'Quick')
    _settled(core, mid, 'COMPLETED')
    x, _ = _ended(core, mid)
    check(x['state'] == 'ENDED_OK' and _ran(x) < 10, 'Core: a short attempt ended well (%.1f s)' % _ran(x))
    page.wait_for_timeout(1500)
    check(page.locator(TOAST).count() == 0, 'short work gives no toast')
    context.close()
    assert check.n >= 2
