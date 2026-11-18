"""P19.5 R9 in a real browser against a real Core: pinned missions (D-9) and a
row's actions as a menu (rulebook §10, §20).

Pins are a local preference: a Pinned group at the top of Work, at every
width, kept in this browser and never sent to Core. A Work row's menu opens by
right-click, Shift+F10 or the menu key and holds exactly what is offered
elsewhere — Open, Pin and the inspector's own Pause / Resume / Stop, which reach
Core by the same command. Mutation-verified by tools/mutate_p19_5.py. Check
floors keep a test that silently checks nothing from passing."""

import os

from .conftest import wait
from .test_spa_p16 import AXE, Checks, _go, _open, _settled
from .test_spa_p18 import slow  # noqa: F401 (a fixture)
from .test_spa_pause_all import _executing


def _row(page, mid, pinned=False):
    return page.locator('main li[data-mission="%s"]%s' % (mid, '[data-pinned]' if pinned else ':not([data-pinned])'))


def _sections(page):
    return page.locator('main section > header h2').all_inner_texts()


def test_pins_are_a_group_at_the_top_of_work_kept_in_this_browser(browser, slow):  # noqa: F811
    check = Checks()
    m1, m2 = _executing(slow, 'Ship the chart'), _executing(slow, 'Write the notes')
    context, page, errors = _open(browser, slow)
    sent = []
    page.on('request', lambda r: sent.append(r.url) if r.method != 'GET' and '/v1/' in r.url else None)
    _go(page, '#/work')
    _row(page, m2).wait_for()
    check(not [s for s in _sections(page) if s.startswith('Pinned')], 'no Pinned group while nothing is pinned')
    pin = _row(page, m2).locator('button.pin')
    check(pin.get_attribute('aria-pressed') == 'false' and pin.inner_text() == 'Pin', 'each row offers Pin')
    check(pin.get_attribute('aria-label') == 'Pin “Write the notes”', 'named for its mission')
    pin.click()
    wait(page, lambda: _sections(page)[:1] == ['Pinned · 1'], what='the Pinned group at the top')
    check(True, 'pinning puts a Pinned group first')
    check(_row(page, m2, pinned=True).count() == 1, 'the pinned mission is in it')
    check(_row(page, m2).count() == 1, 'and still in its own group')
    check(_row(page, m2).locator('button.pin').get_attribute('aria-pressed') == 'true', 'its pin reads pressed')
    _row(page, m1).locator('button.pin').click()
    wait(page, lambda: _sections(page)[:1] == ['Pinned · 2'], what='two pinned')
    order = page.locator('main #pinned li[data-mission]').evaluate_all('els => els.map(e => e.dataset.mission)')
    check(order == [m2, m1], 'oldest pin first: %s' % order)
    check(not sent, 'nothing is sent to Core: %s' % sent)

    # kept in this browser: a new page of the same browser still has them
    page2 = context.new_page()
    page2.goto(slow.core.launch_url())
    page2.get_by_role('heading', name='Now', exact=True).wait_for()
    _go(page2, '#/work')
    wait(page2, lambda: _sections(page2)[:1] == ['Pinned · 2'], what='pins kept')
    check(True, 'pins survive a new page in the same browser')
    page2.close()

    # every width: a phone keeps the group at the top, at 44 px
    page.set_viewport_size({'width': 390, 'height': 844})
    _go(page, '#/work')
    wait(page, lambda: _sections(page)[:1] == ['Pinned · 2'], what='the group on a phone')
    check(True, 'a phone has the Pinned group at the top of Work')
    check(_row(page, m1).locator('button.pin').bounding_box()['height'] >= 44, 'a 44 px pin on a phone')
    check(page.evaluate('() => document.documentElement.scrollWidth - innerWidth') <= 0, 'nothing scrolls sideways')
    page.set_viewport_size({'width': 1280, 'height': 900})
    _row(page, m1, pinned=True).locator('button.pin').click()
    _row(page, m2).locator('button.pin').click()
    wait(page, lambda: not [s for s in _sections(page) if s.startswith('Pinned')], what='unpinned')
    check(True, 'unpinning both removes the group')
    check(not errors, errors)
    context.close()

    # a browser that refuses storage still pins for the page's life
    context, page, errors = _open(browser, slow)
    page.add_init_script("Object.defineProperty(window, 'localStorage', {get() { throw new Error('denied') }})")
    page.goto(slow.core.launch_url())
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    _go(page, '#/work')
    _row(page, m1).locator('button.pin').click()
    wait(page, lambda: _sections(page)[:1] == ['Pinned · 1'], what='pinned without storage')
    check(True, 'no storage: the pin still holds for the page')
    check(not errors, errors)
    context.close()
    assert check.n >= 17


def test_a_row_menu_holds_the_rows_own_actions_by_keyboard_and_pointer(browser, slow):  # noqa: F811
    check = Checks()
    m1 = _executing(slow, 'Ship the chart')
    context, page, errors = _open(browser, slow, bypass_csp=True)
    _go(page, '#/o/mission/' + m1)
    page.locator('.inspector .insp-head').wait_for()
    inspector = page.locator('.inspector .insp-head .row.actions .action > button').all_inner_texts()
    _go(page, '#/work')
    link = _row(page, m1).locator('a.row-link')
    link.wait_for()
    check(link.get_attribute('aria-keyshortcuts') == 'Shift+F10', 'the row says how to open its menu')
    menu = page.locator('main [data-row-menu]')
    link.focus()
    page.keyboard.press('Shift+F10')
    menu.wait_for()
    check(menu.get_attribute('role') == 'dialog' and menu.get_attribute('aria-label') == 'Actions for “Ship the chart”',
          'Shift+F10 opens it, named for its mission')
    check(page.evaluate('() => document.activeElement.textContent') == 'Open', 'focus moves into it')
    items = [x.strip() for x in menu.locator(':scope > a, :scope > button, .action > button').all_inner_texts()]
    check(items == ['Open', 'Pin'] + inspector, 'exactly Open, Pin and the inspector\'s actions: %s vs %s' % (items, inspector))
    page.keyboard.press('Escape')
    wait(page, lambda: menu.count() == 0, what='Esc closes it')
    check(page.evaluate('() => document.activeElement.classList.contains("row-link")'), 'Esc returns to the row')
    page.keyboard.press('ContextMenu')
    menu.wait_for()
    check(True, 'the menu key opens it too')
    page.keyboard.press('Tab')
    page.keyboard.press('Tab')
    for _ in range(4):
        page.keyboard.press('Tab')
    wait(page, lambda: menu.count() == 0, what='leaving it by keyboard closes it')
    check(True, 'tabbing out of it closes it')

    # pointer: a right-click opens it; a press outside closes it
    _row(page, m1).click(button='right')
    menu.wait_for()
    check(True, 'a right-click opens it')
    page.mouse.click(5, 5)
    wait(page, lambda: menu.count() == 0, what='a press outside closes it')
    check(True, 'a press outside closes it')

    if os.path.isfile(AXE):
        _row(page, m1).click(button='right')
        menu.wait_for()
        page.add_script_tag(path=AXE)
        bad = page.evaluate('async () => (await axe.run(document, {resultTypes: ["violations"]})).violations'
                            '.filter(v => ["serious", "critical"].includes(v.impact)).map(v => v.id)')
        check(not bad, 'axe on Work with a row menu open: %s' % bad)
    else:
        _row(page, m1).click(button='right')
        menu.wait_for()

    # its actions are the inspector's: Pause reaches Core by the same command
    menu.locator('.action > button', has_text='Pause').click()
    _settled(slow, m1, 'PAUSED')
    check(True, 'Pause from the menu paused the mission in Core')
    # Stop keeps its confirmation, Cancel first; Esc there leaves the menu open
    _go(page, '#/work')
    _row(page, m1).click(button='right')
    menu.wait_for()
    wait(page, lambda: menu.locator('.action > button', has_text='Resume').count() == 1, what='the paused mission offers Resume')
    menu.locator('.action > button', has_text='Stop').click()
    dialog = page.locator('main [data-row-menu] dialog[open]')
    dialog.wait_for()
    check(page.evaluate('() => document.activeElement.textContent') == 'Cancel', 'the confirmation focuses Cancel')
    page.keyboard.press('Escape')
    wait(page, lambda: dialog.count() == 0, what='Esc cancels the confirmation')
    check(menu.count() == 1, 'and only the confirmation')
    check(slow.http('GET', '/v1/missions/' + m1).json()['state'] == 'PAUSED', 'nothing was stopped')
    check(not errors, errors)
    context.close()
    assert check.n >= 15
