"""P19.5 R10b in a real browser against a real Core: reprioritise as an absolute
"Priority N" (D-14, rulebook §46.1).

One number per mission, set by Core's one command (`POST
/v1/missions/{id}/reprioritize`); no drag, no Alt+Up/Down and no relative move,
because Core has none. The mission inspector's header offers it until the
mission ends, a Work row says a priority other than the default, and every
check is against Core's own read of the mission. Mutation-verified by
tools/mutate_p19_5.py (N223 onward). Check floors keep a test that silently
checks nothing from passing."""

import json
import os

from .conftest import wait
from .test_spa_p16 import AXE, Checks, _go, _mission, _open, _settled
from .test_spa_p18 import slow  # noqa: F401 (a fixture)
from .test_spa_pause_all import _executing

FORM = '.inspector [data-priority-form]'


def _priority(tc, mid):
    return tc.http('GET', '/v1/missions/' + mid).json()['priority']


def test_priority_is_one_number_set_by_cores_one_command(browser, slow):  # noqa: F811
    check = Checks()
    sent = []
    m = _executing(slow, 'Ship the chart')
    context, page, errors = _open(browser, slow, bypass_csp=True)
    page.on('request', lambda r: sent.append((r.url.split('/v1', 1)[1], json.loads(r.post_data or '{}')))
            if r.method == 'POST' and r.url.endswith('/reprioritize') else None)
    _go(page, '#/o/mission/' + m)
    field = page.locator(FORM).get_by_label('Priority', exact=True)
    field.wait_for()
    check(field.input_value() == '0', 'the field shows Core\'s priority, 0 by default')
    check(page.locator(FORM).get_by_text('Every mission starts at 0').count() == 1, 'it says what the number does')
    button = page.locator(FORM + ' .action > button')
    check(button.inner_text() == 'Set priority', 'one name for the one command')

    field.fill('3')
    button.click()
    wait(page, lambda: _priority(slow, m) == 3, what='Core holds priority 3')
    check(True, 'Set priority sets Core\'s priority')
    wait(page, lambda: len(sent) == 1, what='one request')
    path, body = sent[0]
    check(path == '/missions/%s/reprioritize' % m, 'sent to Core\'s reprioritise route: %s' % path)
    check(body.get('priority') == 3 and isinstance(body.get('priority'), int), 'an absolute integer: %s' % body)
    check(isinstance(body.get('expected_version'), int), 'against the version on screen')
    check(bool(body.get('idempotency_key')), 'keyed')
    check(_settled(slow, m, 'EXECUTING') is None, 'it changes nothing else: the mission still runs')
    wait(page, lambda: field.input_value() == '3', what='the field shows the new priority')
    check(True, 'the field shows what Core now holds')
    r = slow.http('POST', '/v1/missions/%s/reprioritize' % m, body={'priority': 7, 'idempotency_key': 'elsewhere'})
    assert r.status == 200, r.body
    wait(page, lambda: field.input_value() == '7', what='a priority set elsewhere reaches the field')
    check(True, 'the field follows Core when the priority is set elsewhere')

    # not a whole number: refused before it is sent, and it says why
    field.fill('2.5')
    check(button.is_disabled(), 'a fraction is not sent')
    check(page.locator(FORM).get_by_text('A priority is a whole number.').count() == 1, 'it says why')
    field.fill('-2')
    check(not button.is_disabled(), 'a negative whole number is a priority')
    button.click()
    wait(page, lambda: _priority(slow, m) == -2, what='Core holds priority -2')
    check(len(sent) == 2 and sent[1][1]['priority'] == -2, 'the second press sends -2')
    check(sent[0][1]['idempotency_key'] != sent[1][1]['idempotency_key'], 'each press carries its own key')

    # Work says a priority other than the default, from Core's list
    _go(page, '#/work')
    row = page.locator('[data-mission="%s"] [data-priority]' % m)
    wait(page, lambda: row.count() == 1 and row.inner_text() == 'priority -2', what='the row says priority -2')
    check(True, 'the Work row says the priority Core holds')
    field = None
    _go(page, '#/o/mission/' + m)
    page.locator(FORM).get_by_label('Priority', exact=True).fill('0')
    page.locator(FORM + ' .action > button').click()
    wait(page, lambda: _priority(slow, m) == 0, what='back to 0')
    _go(page, '#/work')
    wait(page, lambda: page.locator('[data-mission="%s"]' % m).count() == 1, what='the row')
    wait(page, lambda: row.count() == 0, what='a default priority is not said')
    check(True, 'a row at the default says nothing about priority')
    check(page.locator('[draggable="true"]').count() == 0, 'nothing is draggable: no drag is built (D-14)')

    if os.path.isfile(AXE):
        _go(page, '#/o/mission/' + m)
        page.locator(FORM).wait_for()
        page.add_script_tag(path=AXE)
        bad = page.evaluate('async () => (await axe.run(document, {resultTypes: ["violations"]})).violations'
                            '.filter(v => ["serious", "critical"].includes(v.impact)).map(v => v.id)')
        check(not bad, 'axe on the inspector with the priority field: %s' % bad)

    # a phone: the field and its command fit
    page.set_viewport_size({'width': 390, 'height': 844})
    _go(page, '#/o/mission/' + m)
    page.locator(FORM).wait_for()
    check(page.locator(FORM + ' .action > button').bounding_box()['height'] >= 44, 'a 44 px target on a phone')
    check(page.evaluate('() => document.documentElement.scrollWidth - innerWidth') <= 0, 'nothing scrolls sideways')
    check(not errors, errors)
    context.close()
    assert check.n >= 20


def test_an_ended_mission_offers_no_priority(browser, core):  # noqa: F811
    check = Checks()
    done = _mission(core, 'Quick')
    _settled(core, done, 'COMPLETED')
    context, page, errors = _open(browser, core)
    _go(page, '#/o/mission/' + done)
    page.get_by_role('heading', name='Quick').wait_for()
    check(page.locator(FORM).count() == 0, 'an ended mission offers no priority: Core refuses it there')
    r = core.http('POST', '/v1/missions/%s/reprioritize' % done, body={'priority': 1, 'idempotency_key': 'k'})
    check(r.status == 422, 'Core does refuse it: %s' % r.status)
    context.close()

    assert check.n >= 2


def test_a_client_without_control_is_told_why(browser, slow):  # noqa: F811
    check = Checks()
    live = _executing(slow, 'Later')
    ro = browser.new_context()
    page = ro.new_page()
    page.goto(slow.core.launch_url())                  # the default grant: observe only
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    _go(page, '#/o/mission/' + live)
    button = page.locator(FORM + ' .action > button')
    button.wait_for()
    check(button.is_disabled(), 'disabled for a client without control')
    check(page.locator(FORM).get_by_text('does not hold the “control” scope').count() == 1, 'it says why')
    check(_priority(slow, live) == 0, 'nothing was sent')
    ro.close()
    assert check.n >= 3
