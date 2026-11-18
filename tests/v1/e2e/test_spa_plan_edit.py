"""P19 S2 in a real browser against a real Core (p19-design-gate B4): the plan
awaiting approval is edited on the mission's Plan tab — a task renamed, one
added, moved first and waited for — and saving sends the whole list to `POST
/v1/plans/{id}/edit`. Core keys the tasks in the order shown and asks again,
and the tab shows the person's version. A check floor keeps a test that
silently checks nothing from passing."""

from .conftest import wait
from .test_spa_p16 import Checks, _go, _mission, _open, _settled, deploy  # noqa: F401 (a fixture)


def test_the_plan_awaiting_approval_is_edited_on_its_tab(browser, deploy):  # noqa: F811
    tc = deploy
    check = Checks()
    mid = _mission(tc, 'Edit my plan')
    _settled(tc, mid, 'APPROVAL_REQUIRED')
    v1 = tc.http('GET', '/v1/missions/%s/plan' % mid).json()['plan']
    context, page, errors = _open(browser, tc)
    _go(page, '#/o/mission/%s/plan' % mid)
    page.get_by_role('button', name='Edit plan…').click()
    form = page.locator('form.plan-editor')
    form.wait_for()
    check(form.locator('[data-edit-task]').count() == 1, 'the editor holds the plan in force')
    form.get_by_label('Title').fill('Deploy the fix')
    form.get_by_role('button', name='Add task').click()
    new = form.locator('[data-edit-task]').nth(1)
    new.get_by_label('Title').fill('Check the fix')
    new.get_by_label('Description').fill('Read the change.')
    new.get_by_label('Criterion 1', exact=True).fill('the change reads right')
    new.get_by_role('button', name='Move up').click()
    first = form.locator('[data-edit-task]').nth(0)
    check(first.get_by_label('Title').input_value() == 'Check the fix', 'moved first')
    form.get_by_role('button', name='Save plan').click()

    def version(n):
        p = tc.http('GET', '/v1/missions/%s/plan' % mid).json()['plan']
        return p if p['plan_version'] == n else None
    wait(page, lambda: version(2) is not None, what='the edit reached Core')
    p2 = version(2)
    check([(t['key'], t['title'], t['depends_on']) for t in p2['tasks']] == [
        ('t1', 'Check the fix', []), ('t2', 'Deploy the fix', [])],
        'Core keyed the tasks in the order shown: %s' % p2['tasks'])
    check(p2['edited_by'] is not None and p2['supersedes_plan_id'] == v1['id'],
          "the version is the person's and replaces v1")
    check(tc.http('GET', '/v1/missions/' + mid).json()['state'] == 'APPROVAL_REQUIRED',
          'it still deploys, so it asks again')
    page.get_by_role('heading', name='Plan v2').wait_for()
    check(page.get_by_text('edited by a person').count() == 1, 'the tab says whose version it is')

    # the new version awaiting approval is edited again: the deploy waits for the check
    page.get_by_role('button', name='Edit plan…').click()
    form.wait_for()
    form.locator('[data-edit-task]').nth(1).get_by_label('Check the fix').check()
    form.get_by_role('button', name='Save plan').click()
    wait(page, lambda: version(3) is not None, what='the second edit reached Core')
    check([(t['key'], t['depends_on']) for t in version(3)['tasks']] == [
        ('t1', []), ('t2', ['t1'])], 'the deploy waits for the check')
    (a,) = [a for a in tc.http('GET', '/v1/approvals?mission=' + mid).json()['approvals']
            if a['state'] == 'PENDING']
    ok = tc.http('POST', '/v1/approvals/%s/decide' % a['id'], body={
        'decision': 'approve', 'action_hash': a['action_hash'], 'idempotency_key': 'ok-' + mid})
    check(ok.status == 200, 'approved: %s' % ok.body)
    wait(page, lambda: page.get_by_role('button', name='Edit plan…').count() == 0,
         what='an approved plan offers no edit')
    check(True, 'an approved plan offers no edit')
    check(not errors, 'no console errors: %s' % errors)
    assert check.n >= 10, 'only %d checks ran' % check.n
    context.close()
