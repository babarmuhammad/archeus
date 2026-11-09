"""F6 (p20-design-gate D5) in a real browser against a real Core: the command
bar has a touch exit. At 390 px with touch, a tap on its visible Close button
and a tap on its backdrop each close it and give focus back to the opener; a tap
on the bar itself closes nothing; Escape and Ctrl+K are unchanged; forced colours
and high contrast keep the button visible. Mutation-verified by
tools/mutate_p20.py (Q34 onward). The check floor keeps a test that silently
checks nothing from passing."""

from .conftest import wait
from .test_spa_p16 import Checks, _open

PHONE = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)


def _bar(page):
    return page.locator('dialog.command')


def _is_open(page):
    return page.evaluate("() => !!document.querySelector('dialog.command')?.open")


def _focused_opener(page):
    return page.evaluate("() => document.activeElement?.classList.contains('cmd-open') ?? false")


def _open_by_tap(page):
    page.locator('.cmd-open').tap()
    wait(page, lambda: _is_open(page), what='the bar opens')


def test_on_a_phone_close_and_a_backdrop_tap_each_close_the_bar_and_restore_focus(browser, core):
    check = Checks()
    context, page, errors = _open(browser, core, **PHONE)

    _open_by_tap(page)
    close = _bar(page).get_by_role('button', name='Close', exact=True)
    box = close.evaluate('e => [e.offsetWidth, e.offsetHeight]')   # layout, not the open animation
    check(close.is_visible() and box[0] >= 44 and box[1] >= 44,
          'a visible Close of at least the phone target: %s' % box)
    close.tap()
    wait(page, lambda: not _is_open(page), what='Close closes the bar')
    check(True, 'a tap on Close closes the bar')
    check(_focused_opener(page), 'focus is back on the opener after Close')

    _open_by_tap(page)
    r = _bar(page).bounding_box()
    page.touchscreen.tap(r['x'] + r['width'] / 2, r['y'] + r['height'] - 2)   # the bar's own padding
    page.wait_for_timeout(250)
    check(_is_open(page), 'a tap on the bar itself closes nothing')
    page.touchscreen.tap(r['x'] + r['width'] / 2, min(840, r['y'] + r['height'] + 60))
    wait(page, lambda: not _is_open(page), what='a backdrop tap closes the bar')
    check(True, 'a tap on the backdrop closes the bar')
    check(_focused_opener(page), 'focus is back on the opener after the backdrop')

    _open_by_tap(page)
    page.keyboard.press('Escape')
    wait(page, lambda: not _is_open(page), what='Escape still closes the bar')
    check(True, 'Escape is unchanged')
    check(not errors, errors)
    context.close()
    assert check.n >= 8


def test_on_a_desktop_ctrl_k_and_escape_are_unchanged_and_close_is_there_too(browser, core):
    check = Checks()
    context, page, errors = _open(browser, core, viewport={'width': 1280, 'height': 900})
    page.keyboard.press('Control+K')
    wait(page, lambda: _is_open(page), what='Ctrl+K opens the bar')
    check(page.evaluate("() => document.activeElement?.id") == 'cmd', 'the input has focus, as before')
    check(_bar(page).get_by_role('button', name='Close', exact=True).is_visible(), 'Close is shown on a desktop too')
    page.keyboard.press('Escape')
    wait(page, lambda: not _is_open(page), what='Escape closes the bar')
    check(True, 'Escape closes it')
    page.locator('.cmd-open').click()
    wait(page, lambda: _is_open(page), what='the button opens the bar')
    page.mouse.click(5, 5)                                       # the backdrop
    wait(page, lambda: not _is_open(page), what='a backdrop click closes the bar')
    check(_focused_opener(page), 'focus is back on the opener')
    check(not errors, errors)
    context.close()
    assert check.n >= 5


def test_forced_colours_and_high_contrast_keep_close_visible(browser, core):
    check = Checks()
    for media in ({'forced_colors': 'active'}, {'contrast': 'more'}):
        context, page, errors = _open(browser, core, **PHONE)
        page.emulate_media(**media)
        _open_by_tap(page)
        close = _bar(page).get_by_role('button', name='Close', exact=True)
        style = close.evaluate("e => { const s = getComputedStyle(e); return [s.visibility, s.display,"
                               " s.borderTopStyle, parseFloat(s.borderTopWidth)] }")
        check(close.is_visible() and style[0] == 'visible' and style[1] != 'none'
              and style[2] != 'none' and style[3] >= 1, '%s: Close drawn with a border: %s' % (media, style))
        close.tap()
        wait(page, lambda page=page: not _is_open(page), what='Close closes the bar under %s' % media)
        check(True, '%s: Close still closes' % media)
        check(not errors, errors)
        context.close()
    assert check.n >= 6
