"""P19.5 R9 in a real browser against a real Core: the resizable inspector
(rulebook §15, design system §5).

A thin divider on the inspector's left edge, a window splitter: drag it, or
focus it and use ←/→ (with or without Alt), Home and End. The width stays
within 360–560 px, is remembered in this browser and is never sent to Core;
below 1000 px, where the inspector covers the main column, there is none.
Mutation-verified by tools/mutate_p19_5.py. Check floors keep a test that
silently checks nothing from passing."""

import os

from .conftest import wait
from .test_spa_p16 import AXE, Checks, _go, _mission, _open

SEP = '[role="separator"][aria-label="Inspector width"]'


def _width(page):
    return round(page.locator('aside.inspector').bounding_box()['width'])


def test_the_inspector_is_resized_by_its_divider_and_remembers_it(browser, core):
    check = Checks()
    mid = _mission(core, 'Ship the chart')
    context, page, errors = _open(browser, core, viewport={'width': 1440, 'height': 900}, bypass_csp=True)
    sent = []
    page.on('request', lambda r: sent.append(r.url) if r.method != 'GET' and '/v1/' in r.url else None)
    _go(page, '#/o/mission/' + mid)
    sep = page.locator(SEP)
    sep.wait_for()
    check((sep.get_attribute('aria-valuemin'), sep.get_attribute('aria-valuemax')) == ('360', '560'), 'its bounds')
    check(sep.get_attribute('aria-orientation') == 'vertical', 'a vertical splitter')
    start = _width(page)
    check(start == 560 and sep.get_attribute('aria-valuenow') == '560', 'the default width, said: %s' % start)

    sep.focus()
    page.keyboard.press('ArrowRight')
    wait(page, lambda: _width(page) == 544, what='→ narrows by 16')
    check(sep.get_attribute('aria-valuenow') == '544', '→ narrows it, and says so')
    page.keyboard.press('Alt+ArrowLeft')
    wait(page, lambda: _width(page) == 560, what='Alt+← widens')
    check(page.evaluate('() => location.hash') == '#/o/mission/' + mid, 'Alt+← on the divider resizes, it does not go back')
    page.keyboard.press('ArrowLeft')
    check(_width(page) == 560, 'never past 560')
    page.keyboard.press('Home')
    wait(page, lambda: _width(page) == 360, what='Home: 360')
    page.keyboard.press('ArrowRight')
    check(_width(page) == 360 and sep.get_attribute('aria-valuenow') == '360', 'never under 360')
    page.keyboard.press('End')
    wait(page, lambda: _width(page) == 560, what='End: 560')
    check(True, 'Home and End are the bounds')

    # a drag: the divider follows the pointer, within bounds
    box = sep.bounding_box()
    x, y = box['x'] + box['width'] / 2, box['y'] + 200
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 120, y, steps=4)
    page.mouse.up()
    wait(page, lambda: abs(_width(page) - 440) <= 2, what='dragged to about 440')
    check(True, 'a drag resizes it: %s' % _width(page))
    page.mouse.move(x + 120, y)
    page.mouse.down()
    page.mouse.move(x + 600, y, steps=4)
    page.mouse.up()
    check(_width(page) == 360, 'a drag stops at 360: %s' % _width(page))
    check(page.evaluate("() => localStorage.getItem('archeus:inspector-width')") == '360', 'remembered in this browser')
    check(not sent, 'nothing is sent to Core: %s' % sent)

    # a new page of the same browser opens the inspector at the remembered width
    page2 = context.new_page()
    page2.set_viewport_size({'width': 1440, 'height': 900})
    page2.goto(core.core.launch_url())
    page2.get_by_role('heading', name='Now', exact=True).wait_for()
    _go(page2, '#/o/mission/' + mid)
    page2.locator(SEP).wait_for()
    check(_width(page2) == 360 and page2.locator(SEP).get_attribute('aria-valuenow') == '360', 'the width is remembered')
    page2.close()

    if os.path.isfile(AXE):
        page.add_script_tag(path=AXE)
        bad = page.evaluate('async () => (await axe.run(document, {resultTypes: ["violations"]})).violations'
                            '.filter(v => ["serious", "critical"].includes(v.impact)).map(v => v.id)')
        check(not bad, 'axe with the divider: %s' % bad)

    # below 1000 px the inspector covers the main column: no divider
    page.set_viewport_size({'width': 900, 'height': 900})
    _go(page, '#/o/mission/' + mid)
    check(not page.locator(SEP).is_visible(), 'no divider where the inspector covers the main column')
    check(not errors, errors)
    context.close()
    assert check.n >= 16
