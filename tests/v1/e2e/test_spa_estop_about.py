"""P20 slice B in a real browser against a real Core: Control → About's
emergency stop (F7, F8; p20-design-gate D3, D4).

The section states whether Core is armed and offers only the action that
applies: Emergency stop while armed, Re-arm while disarmed, neither while Core
cannot be reached (then it says so instead of guessing). After a press one
status line says what Core answered, in the tray's words: what it stopped, that
it refused (nothing stopped), that it failed, or that it did not answer. A
re-arm changes the section only once Core has said so. The confirmation keeps
Cancel first, and Enter or Escape stop nothing. Mutation-verified by
tools/mutate_p20.py (Q09 onward). Check floors keep a test that silently
checks nothing from passing."""

import json

from .conftest import wait
from .test_spa_p16 import Checks, _go, _open


def _section(page):
    return page.locator('section', has=page.get_by_role('heading', name='Emergency stop', exact=True))


def _armed(page):
    p = _section(page).locator('[data-armed]')
    return p.get_attribute('data-armed') if p.count() else None


def _buttons(page):
    return sorted(b.inner_text() for b in _section(page).locator('.action > button').all())


def _said(page):
    return ' '.join(x.inner_text().strip() for x in _section(page).locator('[data-estop-said]').all()).strip()


def _health(tc):
    return tc.http('GET', '/v1/health').json()['armed']


def _about(browser, tc):
    context, page, errors = _open(browser, tc)
    _go(page, '#/control/about')
    wait(page, lambda: _armed(page) == 'true', what='the section says Core is armed')
    return context, page, errors


def _press_stop(page):
    _section(page).get_by_role('button', name='Emergency stop').click()
    dialog = _section(page).locator('dialog[open]')
    dialog.wait_for()
    return dialog


def test_armed_stop_then_disarmed_rearm_only_from_cores_answer(browser, core):
    check = Checks()
    context, page, errors = _about(browser, core)
    check('Armed: Archeus accepts new work.' in _section(page).inner_text(), 'armed, in words (F8)')
    check(_buttons(page) == ['Emergency stop'], 'armed offers only Emergency stop (F8)')

    # the confirmation: Cancel first; Enter and Escape stop nothing
    _press_stop(page)
    check(page.evaluate('() => document.activeElement.textContent') == 'Cancel', 'the confirmation opens on Cancel')
    page.keyboard.press('Enter')
    page.wait_for_timeout(300)
    check(_section(page).locator('dialog[open]').count() == 0 and _health(core) is True, 'Enter stops nothing')
    _press_stop(page)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    check(_section(page).locator('dialog[open]').count() == 0 and _health(core) is True, 'Escape stops nothing')
    check(_said(page) == '', 'nothing pressed, nothing said')

    _press_stop(page).get_by_role('button', name='Emergency stop').click()
    wait(page, lambda: _armed(page) == 'false', what='the section follows Core to disarmed')
    check(_health(core) is False, 'Core is disarmed')
    check(_said(page) == 'Emergency stop: 0 execution(s) stopped; Core is disarmed until re-armed.',
          'the status line is Core\'s answer, in the tray\'s words (F7): %r' % _said(page))
    check('Emergency stop engaged: Archeus refuses new work until you re-arm.' in _section(page).inner_text(),
          'disarmed, in words (F8)')
    check(_buttons(page) == ['Re-arm'], 'disarmed offers only Re-arm (F8)')

    # re-armed elsewhere (another device, the CLI): the line it no longer describes goes
    assert core.http('POST', '/v1/rearm', body={'idempotency_key': 'rearm-elsewhere'}).status == 200
    wait(page, lambda: _armed(page) == 'true', what='the section follows a re-arm made elsewhere')
    check(_said(page) == '', 'a status line never outlives the state it describes: %r' % _said(page))
    _press_stop(page).get_by_role('button', name='Emergency stop').click()
    wait(page, lambda: _armed(page) == 'false', what='disarmed again')

    # a refused re-arm changes nothing
    page.route('**/v1/rearm', lambda r: r.fulfill(status=403, content_type='application/json',
                                                  body=json.dumps({'error': 'scope_required', 'detail': {'scope': 'control'}})))
    _section(page).get_by_role('button', name='Re-arm').click()
    wait(page, lambda: 'refused the re-arm' in _said(page), what='the refusal said')
    check(_said(page) == 'Core refused the re-arm, so it stays disarmed: This client does not hold the “control” scope.',
          'a refused re-arm says it stays disarmed: %r' % _said(page))
    check(_armed(page) == 'false' and _buttons(page) == ['Re-arm'] and _health(core) is False, 'still disarmed')
    page.unroute('**/v1/rearm')

    # a held re-arm: the section waits for Core's answer
    held = []
    page.route('**/v1/rearm', lambda r: held.append(r))
    _section(page).get_by_role('button', name='Re-arm').click()
    wait(page, lambda: held, what='the re-arm is in flight')
    page.wait_for_timeout(300)
    check(_armed(page) == 'false' and 'Re-armed' not in _said(page), 'no success before Core answers')
    held[0].continue_()
    wait(page, lambda: _armed(page) == 'true', what='the section follows Core to armed')
    check(_health(core) is True, 'Core is armed')
    check(_said(page) == 'Re-armed: Core accepts new work again.', 'the re-arm said from Core\'s answer: %r' % _said(page))
    check(_buttons(page) == ['Emergency stop'], 'armed again offers only Emergency stop')
    check(not [e for e in errors if '403' not in e], errors)          # the routed refusal's own log line
    context.close()
    assert check.n >= 16


def test_a_refused_a_failed_and_an_unanswered_stop_claim_nothing(browser, core):
    check = Checks()
    context, page, errors = _about(browser, core)
    answers = [
        (lambda r: r.fulfill(status=403, content_type='application/json',
                             body=json.dumps({'error': 'scope_required', 'detail': {'scope': 'control'}})),
         'Core refused the emergency stop, so nothing was stopped: This client does not hold the “control” scope.'),
        (lambda r: r.fulfill(status=500, content_type='application/json',
                             body=json.dumps({'error': 'internal', 'detail': {}})),
         'The emergency stop failed inside Core, so nothing is confirmed stopped:'),
        (lambda r: r.abort(),
         'Core did not answer, so nothing is confirmed stopped. The tray’s Emergency stop and “archeus estop” stop without Core.'),
    ]
    for answer, want in answers:
        page.route('**/v1/estop', answer)
        _press_stop(page).get_by_role('button', name='Emergency stop').click()
        wait(page, lambda want=want: want.split(':')[0] in _said(page), what=want)
        check(_said(page).startswith(want), 'said %r, wanted %r' % (_said(page), want))
        check(_section(page).locator('[role=alert][data-estop-said]').count() == 1, 'a failure is an alert')
        check(_health(core) is True, 'Core is still armed: nothing was stopped')
        page.unroute('**/v1/estop')
        wait(page, lambda: _armed(page) == 'true', what='connected again')
    check(not [e for e in errors if 'estop' not in e and 'Failed to load' not in e], errors)
    context.close()
    assert check.n >= 10


def test_with_core_unreachable_the_state_is_not_guessed(browser, core):
    check = Checks()
    context, page, errors = _about(browser, core)
    core.stop(kill=True)
    wait(page, lambda: _armed(page) == 'unknown', timeout=60, what='the section stops claiming a state')
    text = _section(page).inner_text()
    check('Core cannot be reached, so whether it is armed is not known here.' in text, 'unreachable, in words (F8)')
    check('Armed:' not in text and 'engaged' not in text, 'no guessed state')
    check(_buttons(page) == [], 'no action offered while Core cannot be reached')
    context.close()
    assert check.n >= 3


def _as_pin_client(route):
    """Core's own answer, as a paired client holding a PIN would get it: no
    e2e pairs a browser, so the capability is what is stubbed (T-098)."""
    r = route.fetch()
    body = r.json()
    body['client']['capabilities']['step_up'] = 'pin'
    route.fulfill(response=r, body=json.dumps(body))


def test_a_pin_client_re_arms_only_with_six_digits_and_the_pin_never_stays(browser, core):
    """D10 from a PIN-holding client (T-098 review findings 1 and 2): an empty
    or short PIN is never sent, since an empty proof counts toward the
    revocation; whatever Core answers, the field is empty again."""
    check = Checks()
    context, page, errors = _about(browser, core)
    context.route('**/v1/sync', _as_pin_client)          # re-read after the stop's '/v1'
    _press_stop(page).get_by_role('button', name='Emergency stop').click()
    wait(page, lambda: _armed(page) == 'false', what='disarmed')
    pin = _section(page).locator('label.pin input')
    rearm = _section(page).get_by_role('button', name='Re-arm')
    pin.wait_for()
    check(rearm.is_disabled() and 'Enter this client’s PIN first.' in _section(page).inner_text(),
          'no PIN typed: Re-arm is not offered')
    pin.fill('48291')
    check(rearm.is_disabled(), 'five digits: Re-arm is not offered')

    sent = []

    def _local(route):          # the stub is the client; this Core knows it as local
        body = route.request.post_data_json
        sent.append(body.pop('step_up', None))
        route.continue_(post_data=json.dumps(body))
    context.route('**/v1/rearm', _local)
    pin.fill('482913')
    check(not rearm.is_disabled(), 'six digits: Re-arm is offered')
    rearm.click()
    wait(page, lambda: _armed(page) == 'true', what='re-armed')
    check(sent == ['482913'], 'the PIN went with the re-arm: %r' % sent)
    _press_stop(page).get_by_role('button', name='Emergency stop').click()
    wait(page, lambda: _armed(page) == 'false', what='disarmed again')
    pin.wait_for()
    check(pin.input_value() == '' and rearm.is_disabled(), 'after a re-arm the next one asks again')

    context.unroute('**/v1/rearm')
    context.route('**/v1/rearm', lambda r: r.fulfill(status=422, content_type='application/json', body=json.dumps(
        {'error': 'guard_failed', 'detail': {'reason': 're-arming from a paired device needs a valid step-up proof'}})))
    pin.fill('000000')
    rearm.click()
    wait(page, lambda: 'refused the re-arm' in _said(page), what='the refusal said')
    check(pin.input_value() == '' and rearm.is_disabled(), 'after a refused re-arm the PIN is gone too')
    check(_health(core) is False, 'still disarmed')
    check(not [e for e in errors if '422' not in e], errors)
    context.close()
    assert check.n >= 8
