"""P19.5 A-08 in a real browser against a real Core: attention arrival
(rulebook §17, §20, §21; §46.2).

When Core's count of things that need the user rises, the nav badge pulses
once (240 ms, a CSS transform), the new count is said in the polite live
region, and the tab's name carries it. A page opened on a count that is
already there does not pulse, and neither does reduced motion, where the words
and the count still change. Afterwards nothing runs. Mutation-verified by
tools/mutate_p19_5.py (N294 onward). Check floors keep a test that silently
checks nothing from passing."""

from .conftest import wait
from .motion import running_animations
from .test_spa_p16 import Checks, _mission, _open, _settled, deploy  # noqa: F401 (a fixture)

BADGE = 'nav[aria-label="Destinations"] .badge'

#: the arrival pulses that start, recorded from the page's own animation events
_PULSES = """() => { window.__pulses = 0; document.addEventListener('animationstart', e => {
  if (e.animationName === 'attention-arrival') window.__pulses++; }); }"""


def _needs_you(tc, title):
    mid = _mission(tc, title)
    _settled(tc, mid, 'APPROVAL_REQUIRED')
    return tc.http('GET', '/v1/attention').json()['count']


def _said(page, text):
    return text in page.locator('#live-polite').inner_text()


def test_a_rise_in_what_needs_you_pulses_the_badge_once(browser, deploy):  # noqa: F811
    check = Checks()
    context, page, errors = _open(browser, deploy)
    page.evaluate(_PULSES)
    check(page.locator(BADGE).count() == 0 and page.title() == 'Archeus', 'nothing needs you: no badge, the plain name')

    n = _needs_you(deploy, 'Arrival one')
    check(n == 1, 'Core counts one')
    wait(page, lambda: page.evaluate('window.__pulses') == 1, what='the badge pulses once')
    check(page.locator(BADGE).inner_text() == '1', 'the badge says the count')
    check(page.locator(BADGE).get_attribute('data-arrival') is not None, 'the pulse is the arrival')
    wait(page, lambda: page.title() == '(1) Archeus', what='the tab name carries the count')
    wait(page, lambda: _said(page, '1 thing needs you'), what='the arrival is announced')
    page.wait_for_timeout(500)   # past the 240 ms pulse, in real time (the announcer runs on timers)
    check(not running_animations(page), 'after the pulse nothing runs')

    _needs_you(deploy, 'Arrival two')
    wait(page, lambda: page.evaluate('window.__pulses') == 2, what='a second rise, a second pulse')
    wait(page, lambda: page.title() == '(2) Archeus', what='the tab name follows')
    page.wait_for_timeout(500)   # past the 240 ms pulse, in real time (the announcer runs on timers)
    check(page.evaluate('window.__pulses') == 2, 'one pulse per rise, no more')
    check(not errors, errors)
    context.close()

    # a page opened on a count already there: the first read is the baseline
    context, page, errors = _open(browser, deploy)
    page.evaluate(_PULSES)
    page.locator(BADGE).wait_for()
    page.wait_for_timeout(500)   # past the 240 ms pulse, in real time (the announcer runs on timers)
    check(page.locator(BADGE).inner_text() == '2' and page.locator(BADGE).get_attribute('data-arrival') is None,
          'opened on two: the badge, no arrival')
    check(page.evaluate('window.__pulses') == 0 and page.title() == '(2) Archeus', 'no pulse, the name says two')
    check(not errors, errors)
    context.close()
    assert check.n >= 10


def test_reduced_motion_says_the_rise_and_pulses_nothing(browser, deploy):  # noqa: F811
    check = Checks()
    context, page, errors = _open(browser, deploy, reduced_motion='reduce')
    page.evaluate(_PULSES)
    _needs_you(deploy, 'Arrival, reduced')
    wait(page, lambda: page.locator(BADGE).count() == 1, what='the badge appears')
    wait(page, lambda: _said(page, '1 thing needs you'), what='the arrival is still announced')
    page.wait_for_timeout(500)   # past the 240 ms pulse, in real time (the announcer runs on timers)
    check(page.evaluate('window.__pulses') == 0 and not running_animations(page), 'reduced motion: no pulse')
    check(page.locator(BADGE).get_attribute('data-arrival') is None, 'no arrival is marked')
    check(page.title() == '(1) Archeus', 'the tab name still carries the count')
    check(not errors, errors)
    context.close()
    assert check.n >= 4
