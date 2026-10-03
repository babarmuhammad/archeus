"""P19.5 R11 in a real browser against a real Core: the forget flow (rulebook
§13, §42).

Forgetting goes through Core's one forget entry point. The preview is Core's
own dry run, which changes nothing; Forget sends the same selector and mode
for real, only after a preview of that mode and behind a confirmation that
says it cannot be undone. No undo is offered anywhere. Mutation-verified by
tools/mutate_p19_5.py. Check floors keep a test that silently checks nothing
from passing."""

import json
import time

from .conftest import wait
from .test_spa_p16 import Checks, _go, _mission, _open, _settled


def _lesson(tc, title='A deploy asks first'):
    mid = _mission(tc, 'Ship it')
    _settled(tc, mid, 'COMPLETED')
    r = tc.http('POST', '/v1/feedback', body={'subject': {'kind': 'mission', 'id': mid}, 'signal': 'correction',
                                              'text': 'deploys wait for a person', 'idempotency_key': 'fb-%f' % time.time(),
                                              'promote': {'type': 'LESSON', 'title': title}})
    assert r.status == 200, r.body
    kid = r.json()['promoted']['id']
    k = tc.http('GET', '/v1/knowledge/' + kid).json()
    r = tc.http('POST', '/v1/knowledge/%s/confirm' % kid, body={'idempotency_key': 'c-' + kid, 'expected_version': k['version']})
    assert r.status == 200, r.body
    return kid


def _k(tc, kid):
    return tc.http('GET', '/v1/knowledge/' + kid).json()


def test_forgetting_previews_by_cores_dry_run_and_offers_no_undo(browser, core):
    check = Checks()
    kid = _lesson(core)
    check(_k(core, kid)['state'] == 'CONFIRMED', 'a confirmed lesson')
    context, page, errors = _open(browser, core)
    sent = []
    page.on('request', lambda r: sent.append(json.loads(r.post_data or '{}'))
            if r.method == 'POST' and r.url.endswith('/v1/knowledge/forget') else None)
    _go(page, '#/o/knowledge_item/' + kid)
    box = page.locator('.inspector [data-forget]')
    box.locator('summary').click()
    forget = box.locator('.action > button', has_text='Forget')
    check(forget.is_disabled(), 'Forget waits for a preview')
    check(box.get_by_text('See what would change first.').count() == 1, 'and says so')
    check(box.get_by_label('Stop using it', exact=False).is_checked(), 'retract is the default')

    box.get_by_role('button', name='See what would change').click()
    preview = box.locator('[data-forget-preview]')
    preview.wait_for()
    check(preview.get_attribute('role') == 'status', 'the preview is said')
    check('it stops being used as context (confirmed → retracted)' in preview.inner_text(), preview.inner_text())
    check(_k(core, kid)['state'] == 'CONFIRMED', 'the preview changed nothing in Core')
    check(len(sent) == 1 and sent[0]['dry_run'] is True and sent[0]['selector'] == {'ids': [kid]}
          and sent[0]['mode'] == 'retract', 'the preview is Core\'s own dry run: %s' % sent)

    # another mode is another question: its preview first
    box.get_by_label('Erase its content', exact=False).check()
    wait(page, lambda: preview.count() == 0, what='changing the mode drops the preview')
    check(forget.is_disabled(), 'and Forget waits again')
    box.get_by_role('button', name='See what would change').click()
    preview.wait_for()
    check('its content is erased; its provenance stays' in preview.inner_text(), preview.inner_text())

    forget.click()
    dialog = page.locator('dialog.confirm[open]')
    dialog.wait_for()
    check('This cannot be undone.' in dialog.inner_text(), 'the confirmation says it cannot be undone')
    check(page.evaluate('() => document.activeElement.textContent') == 'Cancel', 'Cancel is focused')
    page.keyboard.press('Escape')
    wait(page, lambda: dialog.count() == 0, what='Esc cancels')
    check(len(sent) == 2 and _k(core, kid)['state'] == 'CONFIRMED', 'nothing was forgotten')
    forget.click()
    page.locator('dialog.confirm[open] .btn.danger').click()
    wait(page, lambda: _k(core, kid)['state'] == 'RETRACTED', what='Core retracts it')
    k = _k(core, kid)
    check(k['text'] == '' and k.get('purged') is True, 'and purges it: its content is gone')
    check(sent[-1]['dry_run'] is False and sent[-1]['mode'] == 'purge' and sent[-1]['selector'] == {'ids': [kid]},
          'Forget sent the previewed selector and mode for real')
    check(page.get_by_role('button', name='Undo').count() == 0, 'no undo is offered')

    # forgotten already: the dry run says nothing would change, and Forget waits
    box = page.locator('.inspector [data-forget]')
    wait(page, lambda: box.count() == 1, what='the flow after the re-read')
    if not box.evaluate('d => d.open'):
        box.locator('summary').click()
    box.get_by_label('Erase its content', exact=False).check()
    box.get_by_role('button', name='See what would change').click()
    preview = box.locator('[data-forget-preview]')
    preview.wait_for()
    check(preview.inner_text() == 'Nothing would change: it is already forgotten this way.', preview.inner_text())
    check(box.locator('.action > button', has_text='Forget').is_disabled(), 'nothing to forget, nothing offered')
    check(not errors, errors)
    context.close()

    # a client without control is told why, and sends nothing
    k2 = _lesson(core, 'Another lesson')
    ro = browser.new_context()
    page = ro.new_page()
    page.goto(core.core.launch_url())
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    _go(page, '#/o/knowledge_item/' + k2)
    box = page.locator('.inspector [data-forget]')
    box.locator('summary').click()
    check(box.get_by_role('button', name='See what would change').is_disabled(), 'no preview without control')
    check(box.get_by_text('does not hold the “control” scope').count() >= 1, 'it says why')
    ro.close()
    assert check.n >= 21
