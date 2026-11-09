"""The application theme in a real browser against a real Core (ADR-0044;
p19-design-gate B9; testing-strategy §8 T1-T3, T5, T6): Control → Appearance
offers exactly the token sets, an explicit choice holds whatever the emulated
OS says, `system` follows it, forced colours override any choice, the choice
survives a reload and an offline start from the service worker with no Core
read, and <html> carries it while the stylesheet has not even arrived. The
Qt shell's restart (T5's third half) is B8's. A check floor keeps a test that
silently checks nothing from passing."""

import json
import os

from .conftest import wait
from .test_spa_p16 import Checks, _go, _open

with open(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'clients', 'app', 'tokens',
                       'tokens.json'), encoding='utf-8') as _f:
    TOKENS = json.load(_f)['themes']
#: what getComputedStyle answers: the same colours, in lower case
LOW = {name: {role: v.lower() for role, v in t.items()} for name, t in TOKENS.items()}
KEY = 'archeus-appearance'

LOOK = """() => {
  const h = document.documentElement, r = getComputedStyle(h);
  return {theme: h.dataset.theme, contrast: h.dataset.contrast,
          bg: r.getPropertyValue('--bg').trim(), text3: r.getPropertyValue('--text-3').trim(),
          colors: [...document.querySelectorAll('meta[name="theme-color"]')].map((m) => m.content)};
}"""


def _look(page):
    return page.evaluate(LOOK)


def _choose(page, label, option):
    page.get_by_role('combobox', name=label, exact=True).select_option(label=option)


def test_appearance_is_this_clients_choice_over_the_systems(browser, core):
    check = Checks()
    context, page, errors = _open(browser, core, color_scheme='light')
    first = _look(page)
    check((first['theme'], first['contrast']) == ('system', 'system'), 'T2: a first launch is system/system')
    check(first['bg'] == LOW['light']['bg'], 'T2: it follows an OS in light')
    page.emulate_media(color_scheme='dark', contrast='more')
    now = _look(page)
    check(now['bg'] == LOW['dark']['bg'], 'T2: and follows the OS when it changes')
    check(now['text3'] == LOW['dark']['text-2'], "T2: the OS's contrast too")
    check(now['colors'] == [TOKENS['dark']['bg'], TOKENS['light']['bg']], 'the theme colour follows the OS')

    _go(page, '#/control/appearance')
    theme, contrast = page.get_by_role('combobox', name='Theme', exact=True), page.get_by_role('combobox', name='Contrast', exact=True)
    theme.wait_for()
    check(theme.locator('option').all_inner_texts() == ['Follow the system', 'Dark', 'Light'],
          'T6: the token sets are the only themes')
    check(contrast.locator('option').all_inner_texts() == ['Follow the system', 'Standard', 'High'],
          'T6: and the contrast choices')
    check(page.get_by_role('combobox', name='Motion', exact=True).count() == 1, 'motion is chosen here')

    _choose(page, 'Theme', 'Light')
    _choose(page, 'Contrast', 'Standard')
    for os_scheme, os_contrast in (('dark', 'more'), ('light', 'no-preference')):
        page.emulate_media(color_scheme=os_scheme, contrast=os_contrast)
        x = _look(page)
        check((x['theme'], x['contrast'], x['bg'], x['text3'])
              == ('light', 'standard', LOW['light']['bg'], LOW['light']['text-3']),
              'T1: light/standard whatever the OS says (%s, %s): %s' % (os_scheme, os_contrast, x))
        check(x['colors'] == [TOKENS['light']['bg']] * 2, 'T1: the theme colour is the choice')
    _choose(page, 'Theme', 'Dark')
    _choose(page, 'Contrast', 'High')
    x = _look(page)
    check((x['bg'], x['text3']) == (LOW['dark']['bg'], LOW['dark']['text-2']),
          'T1: dark/high over an OS in light without a contrast preference: %s' % x)
    check(json.loads(page.evaluate('k => localStorage.getItem(k)', KEY)) == {'theme': 'dark', 'contrast': 'high'},
          'stored in this client, under its own key')
    page.emulate_media(color_scheme='light', contrast='more')
    _choose(page, 'Contrast', 'Standard')
    check(_look(page)['text3'] == LOW['dark']['text-3'], "T1: dark/standard holds off the OS's high contrast")
    _choose(page, 'Contrast', 'High')

    page.reload()
    page.get_by_role('combobox', name='Theme', exact=True).wait_for()
    x = _look(page)
    check((x['theme'], x['contrast'], x['bg']) == ('dark', 'high', LOW['dark']['bg']), 'T5: a reload keeps it')
    check(page.get_by_role('combobox', name='Theme', exact=True).input_value() == 'dark', 'and the section shows it')
    other = context.new_page()
    other.goto(core.base_url + '/')
    check(other.evaluate('document.documentElement.dataset.theme') == 'dark', 'T5: so does another tab of this client')
    other.close()

    page.evaluate('k => localStorage.setItem(k, JSON.stringify({theme: "tokyo-night", contrast: "max"}))', KEY)
    page.reload()
    page.get_by_role('combobox', name='Theme', exact=True).wait_for()
    x = _look(page)
    check((x['theme'], x['contrast'], x['bg']) == ('system', 'system', LOW['light']['bg']),
          'T6: a palette name is no theme: it is the system again')

    _go(page, '#/control/about')
    page.get_by_role('heading', name='This Core').wait_for()
    check(page.get_by_role('combobox', name='Motion', exact=True).count() == 0, 'motion moved out of About')
    # a fast reload opens the stream before Core has seen the old page's close
    check(not [e for e in errors if '429' not in e], 'no console errors: %s' % errors)
    assert check.n >= 19, 'only %d checks ran' % check.n
    context.close()


def test_forced_colours_override_any_choice(browser, core):
    """T3: under `forced-colors: active` the page is the system's colours
    whichever theme and contrast this client chose."""
    check = Checks()
    context, page, _errors = _open(browser, core)
    page.emulate_media(forced_colors='active')
    page.evaluate("""() => {
      for (const c of ['thread-line', 'probe']) {
        const d = document.createElement('div');
        d.className = c;
        document.body.append(d);
      }
      document.querySelector('.probe').style.cssText = 'background: Highlight; forced-color-adjust: none';
    }""")
    seen = set()
    for choice in ({'theme': 'light', 'contrast': 'high'}, {'theme': 'dark', 'contrast': 'standard'},
                   {'theme': 'system', 'contrast': 'system'}):
        page.evaluate('c => archeusAppearance(c)', choice)
        seen.add(tuple(page.evaluate("""() => {
          const bg = (s) => getComputedStyle(document.querySelector(s)).backgroundColor;
          return [bg('body'), getComputedStyle(document.body).color, bg('.thread-line') === bg('.probe')];
        }""")))
    check(len(seen) == 1, 'one look under forced colours, whatever was chosen: %s' % seen)
    check(next(iter(seen))[2], 'the thread line is Highlight, never the high-contrast rule')
    assert check.n >= 2
    context.close()


def test_the_choice_is_on_html_before_the_stylesheet_and_survives_an_offline_start(browser, core):
    """T6: a classic `'self'` script sets the attributes while the stylesheet is
    still held; T5: an offline start from the service worker keeps the choice
    and needs no Core read."""
    check = Checks()
    context = browser.new_context(service_workers='block')
    context.add_init_script('localStorage.setItem(%s, %s)' % (
        json.dumps(KEY), json.dumps(json.dumps({'theme': 'light', 'contrast': 'high'}))))
    page = context.new_page()
    held = []
    page.route('**/assets/*.css', lambda r: held.append(r))
    page.goto(core.base_url + '/', wait_until='commit')
    wait(page, lambda: held, what='the stylesheet request')
    x = page.evaluate("""() => [document.documentElement.dataset.theme, document.documentElement.dataset.contrast,
                                 document.querySelector('link[rel=stylesheet]').sheet === null,
                                 getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()]""")
    check(x == ['light', 'high', True, ''], 'T6: on <html> before any stylesheet arrived: %s' % x)
    held[0].continue_()
    context.close()

    context, page, _errors = _open(browser, core)
    _go(page, '#/control/appearance')
    _choose(page, 'Theme', 'Light')
    _choose(page, 'Contrast', 'High')
    page.evaluate('navigator.serviceWorker.ready')
    wait(page, lambda: page.evaluate('!!navigator.serviceWorker.controller'), what='the shell under the worker')
    page.reload()                                    # the assets now come through it, and it keeps them
    page.wait_for_load_state('load')
    context.set_offline(True)
    page.reload()
    page.wait_for_load_state('load')
    x = _look(page)
    check((x['theme'], x['contrast'], x['bg'], x['text3'])
          == ('light', 'high', LOW['light']['bg'], LOW['light']['text-2']),
          'T5: an offline start keeps the choice: %s' % x)
    check(not page.evaluate("fetch('/v1/health').then(() => true, () => false)"),
          'with Core out of reach: no Core read is needed')
    context.close()
    assert check.n >= 3
