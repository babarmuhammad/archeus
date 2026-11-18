"""P19.5 R9 in a real browser against a real Core: loading is a static skeleton
(rulebook §21 A-12, §42, Appendix B).

While a list's read is pending the page shows skeleton rows in the shape of a
list — never a shimmer, no animation and no animation frame — and says
"Reading X…" only to a screen reader; when Core answers, the rows replace it.
Mutation-verified by tools/mutate_p19_5.py. Check floors keep a test that
silently checks nothing from passing."""

from .conftest import wait
from .test_spa_p16 import FULL, Checks, _go, _mission


def _held_open(browser, tc, path, **ctx):
    """A page whose every read of *path* waits until the test releases it."""
    context = browser.new_context(**ctx)
    held = []
    context.route('**' + path, lambda r: held.append(r))
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(tc.core.launch_url(FULL))
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    return context, page, held, errors


def test_a_pending_list_is_a_still_skeleton_until_core_answers(browser, core):
    check = Checks()
    _mission(core, 'Ship the chart')
    context, page, held, errors = _held_open(browser, core, '/v1/missions')
    _go(page, '#/work')
    sk = page.locator('main [data-skeleton]')
    wait(page, lambda: sk.count() >= 1 and held, what='the Work list waits on its read')
    first = sk.first
    check(first.get_attribute('role') == 'status', 'the skeleton is a status region')
    check(first.inner_text().strip() == 'Reading the missions…', 'it says what it reads: %r' % first.inner_text())
    check(first.locator('.sr').count() == 1, 'the words are visually hidden')
    rows = first.locator('.sk-row')
    check(rows.count() == 3, 'rows in the shape of a list: %d' % rows.count())
    check(all(rows.nth(i).get_attribute('aria-hidden') == 'true' for i in range(rows.count())),
          'the bars are hidden from a screen reader')
    moving = page.evaluate('''() => document.getAnimations().map(a => [a.animationName || a.id,
        a.effect && a.effect.target && a.effect.target.className, !!(a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('[data-skeleton]'))])''')
    check(not [m for m in moving if m[2]], 'nothing in the skeleton animates: %s' % moving)
    style = page.evaluate("""() => { const s = getComputedStyle(document.querySelector('main .sk-row'));
        return [s.animationName, s.transitionDuration, s.backgroundImage] }""")
    check(style == ['none', '0s', 'none'], 'no shimmer: no animation, transition or gradient: %s' % style)
    box = rows.first.bounding_box()
    check(box['height'] >= 28 and box['width'] > 100, 'a row-shaped bar: %s' % box)

    for r in held:
        r.continue_()
    context.unroute('**/v1/missions')
    wait(page, lambda: page.locator('main [data-mission]').count() >= 1, what='the rows arrive')
    wait(page, lambda: page.locator('main [data-skeleton]').count() == 0, what='the skeleton leaves')
    check(True, 'Core\'s rows replace the skeleton')
    check(not errors, errors)
    context.close()

    # forced colours drop a background, so the bars keep an outline there
    context, page, held, errors = _held_open(browser, core, '/v1/missions', forced_colors='active')
    _go(page, '#/work')
    wait(page, lambda: page.locator('main [data-skeleton] .sk-row').count() >= 1, what='the skeleton')
    border = page.evaluate("() => getComputedStyle(document.querySelector('main .sk-row')).borderTopStyle")
    check(border == 'solid', 'an outline under forced colours: %s' % border)
    for r in held:
        r.continue_()
    context.unroute('**/v1/missions')
    context.close()
    assert check.n >= 11
