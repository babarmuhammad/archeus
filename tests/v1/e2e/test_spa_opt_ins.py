"""P20 slice E in a real browser against a real Core (p20-design-gate D6,
ADR-0049): what an execution may load from its settings sources.

Control → Resources lists every opt-in read-only (no form: the CLI sets them)
and follows Core when one changes; an execution's
inspector shows, beside its Why, the inventory Core recorded at its spawn — the
flags it was given and what became of each item. Every word is Core's record.
Check floors keep a test that silently checks nothing from passing."""

import time

from .conftest import wait
from .test_spa_p16 import Checks, _go, _mission, _open


def _section(page):
    return page.locator('section', has=page.get_by_role(
        'heading', name='What executions may load from their settings sources', exact=True))


def _opt(tc, owner, kind, name, on):
    r = tc.http('POST', '/v1/opt-ins', body={'owner_id': owner, 'kind': kind, 'name': name,
                                             'opted_in': on,
                                             'idempotency_key': 'k-%f' % time.time()})
    assert r.status == 200, r.body
    return r.json()


def test_the_opt_ins_are_listed_read_only_and_follow_core(browser, core):
    check = Checks()
    acc = core.http('POST', '/v1/accounts', body={
        'harness_id': 'fake', 'label': 'Work', 'auth_kind': 'api_key',
        'idempotency_key': 'acc-%f' % time.time()}).json()['id']
    context, page, errors = _open(browser, core)
    _go(page, '#/control/resources')
    _section(page).wait_for()
    check('Nothing is opted in: every settings source is excluded.' in _section(page).inner_text(),
          'nothing opted in, said')
    check(_section(page).locator('input, select, textarea, button, form').count() == 0,
          'read-only: no form, no button')
    _opt(core, acc, 'mcp', 'gh', True)
    row = _section(page).locator('[data-opt-in]')
    wait(page, lambda: row.count() == 1, what='the new opt-in appears without a reload')
    check(row.locator('td').first.inner_text() == 'mcp', 'the row names the kind')
    check(row.locator('th').inner_text() == 'gh', 'the row names the server')
    check('opted in' in row.inner_text() and acc in row.inner_text(), 'its state and owner')
    _opt(core, acc, 'mcp', 'gh', False)
    wait(page, lambda: 'opted out' in row.inner_text(), what='the opt-out follows Core')
    check(row.locator('td').last.inner_text() == '2', 'its version counts the change')
    check(not errors, 'no console error: %s' % errors)
    assert check.n == 7
    context.close()


def test_an_execution_shows_what_it_inherited_beside_its_why(browser, core):
    check = Checks()
    _mission(core, 'Inherit nothing')
    deadline = time.monotonic() + 30
    eid = None
    while eid is None and time.monotonic() < deadline:
        evs = core.http('GET', '/v1/events').json()['events']
        eid = next((e['subject']['id'] for e in evs if e['type'] == 'execution.prepared'), None)
        time.sleep(0.1)
    assert eid, 'no execution was prepared'
    context, page, errors = _open(browser, core)
    _go(page, '#/o/execution/%s' % eid)
    inv = page.locator('[data-inventory]')
    inv.wait_for()
    text = inv.inner_text()
    check('Settings sources loaded' in text and 'none' in text, 'no source loaded, said')
    check('only the opted in: none' in text, 'MCP strict with no server')
    check('disabled' in text, 'skills disabled')
    check('not yet (PV-19)' in text, 'not claimed as observed')
    check(page.get_by_text('Why', exact=True).count() >= 1, 'beside the Why')
    check(not errors, 'no console error: %s' % errors)
    assert check.n == 6
    context.close()
