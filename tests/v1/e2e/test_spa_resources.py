"""P19.5 R11 in a real browser against a real Core: the Resources form
(rulebook §43; D-7, rulebook §46.1).

Each account's policy is a form over Core's existing `POST
/v1/resource-policies/{id}`: priority, allocation ceiling, the two reserves,
fallback, the three budgets and the projects it may or may not serve, read
from Core and saved against the version on screen. The draft's own problems
are said before anything is sent; Core's refusals are shown where they
happen; a client without admin is told why. Mutation-verified by
tools/mutate_p19_5.py. Check floors keep a test that silently checks nothing
from passing."""

import json
import os
import re
import subprocess
import time

from .conftest import wait
from .test_spa_p16 import Checks, _go, _open


def _account(tc):
    r = tc.http('POST', '/v1/accounts', body={'harness_id': 'fake', 'label': 'Work laptop', 'auth_kind': 'api_key',
                                              'idempotency_key': 'acc-%f' % time.time()})
    assert r.status == 200, r.body
    return r.json()['id']


def _project(tc, home, name):
    root = os.path.join(str(home), name)
    os.makedirs(root, exist_ok=True)
    subprocess.run(['git', 'init', '-q', root], check=True)
    r = tc.http('POST', '/v1/projects', body={'name': name, 'root_paths': [root], 'idempotency_key': 'p-' + name})
    assert r.status == 200, r.body
    return r.json()['project']['id']


def _policy(tc, acc):
    return next(a for a in tc.http('GET', '/v1/accounts').json()['accounts'] if a['id'] == acc)['resource_policy']


def test_an_accounts_policy_is_a_form_over_cores_route(browser, core, archeus_home):
    check = Checks()
    acc = _account(core)
    atlas = _project(core, archeus_home, 'Atlas')
    _project(core, archeus_home, 'Beacon')
    before = _policy(core, acc)
    context, page, errors = _open(browser, core)
    sent = []
    page.on('request', lambda r: sent.append(json.loads(r.post_data or '{}'))
            if r.method == 'POST' and '/v1/resource-policies/' in r.url else None)
    _go(page, '#/control/resources')
    form = page.locator('[data-policy-form="%s"]' % acc)
    form.locator('summary').click()
    field = lambda name: form.get_by_label(re.compile('^' + re.escape(name)))  # noqa: E731
    check(field('Priority').input_value() == str(before['priority']), 'the priority Core holds')
    check(field('Allocation ceiling').input_value() == str(before['allocation_pct']), 'the ceiling Core holds')
    check(form.locator('select').input_value() == before['fallback'], 'the fallback Core holds')
    check(form.get_by_text('a lower number is tried first').count() == 1, 'it says which way priority goes')
    save = form.locator('.action > button', has_text='Save policy')

    # the draft's own problems, before anything is sent
    field('Reserve, %').fill('60')
    field('Own-call reserve').fill('50')
    check(save.is_disabled(), 'reserves over the ceiling are not sent')
    check(form.get_by_text('The two reserves together cannot exceed the allocation ceiling.').count() == 1, 'it says why')
    field('Allocation ceiling').fill('80')
    field('Reserve, %').fill('10')
    field('Own-call reserve').fill('5')
    field('Priority').fill('3')
    form.locator('select').select_option('ask')
    field('Attempts at once').fill('2')
    form.get_by_label('Atlas').first.check()
    check(not save.is_disabled(), 'a sound draft may be saved')
    save.click()
    wait(page, lambda: _policy(core, acc)['priority'] == 3, what='Core holds the new policy')
    p = _policy(core, acc)
    check((p['allocation_pct'], p['reserve_pct'], p['brain_reserve_pct'], p['fallback']) == (80, 10, 5, 'ask'),
          'every field reached Core: %s' % p)
    check(p['budgets'] == {'concurrency': 2}, 'the one budget filled: %s' % p['budgets'])
    check(list(p.get('project_allow') or []) == [atlas] and not p.get('project_deny'), 'only Atlas: %s' % p)
    check(len(sent) == 1 and sent[0]['expected_version'] == before['version'] and sent[0]['idempotency_key'],
          'one save, against the version on screen, keyed')
    check(isinstance(sent[0]['priority'], int) and sent[0]['budgets'] == {'concurrency': 2}, 'numbers, not text: %s' % sent[0])

    # a blank budget removes it; untick a project. The save's new version resets
    # the draft when it arrives, and the field already reads '2' before then, so
    # an edit made in between would be wiped: wait for the version itself.
    wait(page, lambda: form.get_attribute('data-version') == str(_policy(core, acc)['version']),
         what='the form holds the version the save made')
    wait(page, lambda: field('Attempts at once').input_value() == '2', what='the form shows what Core holds')
    field('Attempts at once').fill('')
    form.get_by_label('Atlas').first.uncheck()
    save.click()
    wait(page, lambda: _policy(core, acc)['budgets'] in ({}, None), what='the budget removed')
    check(not _policy(core, acc).get('project_allow'), 'no project restriction left')
    v = _policy(core, acc)['version']
    wait(page, lambda: form.get_attribute('data-version') == str(v), what='the form holds the version Core now has')
    r = core.http('POST', '/v1/resource-policies/' + acc, body={'priority': 7, 'idempotency_key': 'elsewhere'})
    assert r.status == 200, r.body
    wait(page, lambda: field('Priority').input_value() == '7', what='a policy changed elsewhere reaches the form')
    check(True, 'the form follows Core when the policy changes elsewhere')

    # Core's own refusal is shown where it happened
    field('Cost per day').fill('5')
    save.click()
    err = form.locator('.err[role="alert"]')
    err.wait_for()
    check('cost' in err.inner_text(), 'Core refuses a budget on a measure the account does not report: %r' % err.inner_text())
    check(not (_policy(core, acc)['budgets'] or {}).get('cost_per_day'), 'and nothing was saved')
    check(page.locator('main section', has_text='Recent routing decisions').count() == 1, 'the route preview is beside it')
    check(not [e for e in errors if 'status of 400' not in e], errors)
    context.close()

    # a client without admin is told why
    ro = browser.new_context()
    page = ro.new_page()
    page.goto(core.core.launch_url())
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    _go(page, '#/control/resources')
    form = page.locator('[data-policy-form="%s"]' % acc)
    form.locator('summary').click()
    check(form.locator('.action > button', has_text='Save policy').is_disabled(), 'no save without admin')
    check(form.get_by_text('does not hold the “admin” scope').count() == 1, 'it says why')
    ro.close()
    assert check.n >= 20
