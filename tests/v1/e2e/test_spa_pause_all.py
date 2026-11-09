"""P19.5 R10a in a real browser against a real Core: Pause all and Resume all
on the operations strip and on Work (ADR-0027 §3, rulebook §10, §19).

Pause all pauses the missions executing now, by Core's own command; it is not
the emergency stop and asks no confirmation, since Resume all inverts it.
Resume all is offered exactly while Core's `/v1/status` names missions it would
resume (`resumable`: the newest Pause all's missions still paused by it), never
because some mission is paused and never from the missions' own batch ids.
Every check is against Core's own reads. Mutation-verified by
tools/mutate_p19_5.py (N208 onward). Check floors keep a test that silently
checks nothing from passing."""

import json
import os

from .conftest import wait
from .test_spa_halo import _running
from .test_spa_p16 import AXE, Checks, _go, _mission, _open, _settled
from .test_spa_p18 import slow  # noqa: F401 (a fixture)
from .test_spa_strip import _agrees

ALL = ('/v1/missions/pause-all', '/v1/missions/resume-all')


def _executing(tc, title):
    mid = _mission(tc, title)
    _running(tc, mid)
    _settled(tc, mid, 'EXECUTING')
    return mid


def _resumable(tc):
    return tc.http('GET', '/v1/status').json()['resumable']


def _post(tc, path, key):
    r = tc.http('POST', path, body={'idempotency_key': key})
    assert r.status == 200, r.body
    return r.json()


def _button(page, where, name):
    return page.locator('%s .action > button' % where, has_text=name)


STRIP = '.strip [data-strip="pause-all"]'
WORK = '[data-pause-all]'


def _offers(page, where, name):
    b = _button(page, where, name)
    return b.count() == 1 and b.inner_text() == name


def _shown(page, tc, check, what):
    """Resume all on the strip and on Work exactly when Core says it would resume something."""
    want = bool(_resumable(tc))
    _go(page, '#/work')
    wait(page, lambda: _offers(page, STRIP, 'Resume all') == want and _offers(page, WORK, 'Resume all') == want,
         what='Resume all %s (%s)' % ('shown' if want else 'hidden', what))
    check(True, 'Resume all %s on the strip and on Work: %s' % ('shown' if want else 'hidden', what))


def test_pause_all_and_resume_all_follow_cores_newest_batch(browser, slow):  # noqa: F811
    check = Checks()
    sent = []
    m1 = _executing(slow, 'm1')
    context, page, errors = _open(browser, slow, bypass_csp=True)
    page.on('request', lambda r: sent.append((r.url.split('/v1', 1)[1], json.loads(r.post_data or '{}'),
                                              r.headers.get('authorization', '')))
            if r.method == 'POST' and r.url.endswith(ALL) else None)
    _go(page, '#/work')
    wait(page, lambda: _offers(page, STRIP, 'Pause all') and _offers(page, WORK, 'Pause all'), what='Pause all offered')
    check(True, 'Pause all on the strip and on Work, by its one name')
    check(_offers(page, '.strip [data-strip="estop"]', 'Emergency stop'), 'beside the emergency stop, which stays distinct')
    check(_resumable(slow) == [], 'nothing resumable yet')
    _shown(page, slow, check, 'nothing paused')

    # Pause all from the strip: every executing mission paused, no confirmation
    _button(page, STRIP, 'Pause all').click()
    check(page.locator('dialog[open]').count() == 0, 'no confirmation: Resume all inverts it')
    wait(page, lambda: slow.http('GET', '/v1/missions/' + m1).json()['state'] == 'PAUSED', what='m1 paused')
    a = slow.http('GET', '/v1/missions/' + m1).json()['pause_batch_id']
    check(a is not None, 'Core recorded the batch on the mission')
    check(_resumable(slow) == [m1], 'Core says Resume all would resume m1')
    _shown(page, slow, check, 'the newest batch holds m1')
    wait(page, lambda: _agrees(page, slow), what='the running count equals Core after Pause all')
    check(True, 'the running count equals Core after Pause all')

    # the gap: batch B pauses m2, m2 is resumed by hand; m1 still carries A's id
    m2 = _executing(slow, 'm2')
    _button(page, WORK, 'Pause all').click()
    _settled(slow, m2, 'PAUSED')
    b = slow.http('GET', '/v1/missions/' + m2).json()['pause_batch_id']
    check(b is not None and b != a, 'Work\'s Pause all recorded a second batch')
    _post(slow, '/v1/missions/%s/resume' % m2, 'resume-m2')
    _settled(slow, m2, 'EXECUTING')
    check(slow.http('GET', '/v1/missions/' + m1).json()['pause_batch_id'] == a, 'm1 still carries batch A')
    check(_resumable(slow) == [], 'the newest batch holds nothing, so nothing is resumable')
    _shown(page, slow, check, 'only an older batch still holds a mission')
    out = _post(slow, '/v1/missions/resume-all', 'resume-all-gap')
    check((out['changed'], out['pause_batch_id']) == (False, b), 'Core agrees: Resume all would change nothing')
    check(slow.http('GET', '/v1/missions/' + m1).json()['state'] == 'PAUSED', 'm1 stays paused')

    # paused on its own: never resumable; a Pause all with nothing executing records nothing
    _post(slow, '/v1/missions/%s/pause' % m2, 'pause-m2')
    _settled(slow, m2, 'PAUSED')
    check(_resumable(slow) == [], 'a mission paused on its own is not resumable')
    _shown(page, slow, check, 'only missions paused on their own')
    _button(page, STRIP, 'Pause all').click()
    wait(page, lambda: len(sent) == 3, what='the third Pause all is sent')
    check(_post(slow, '/v1/missions/resume-all', 'resume-all-empty')['pause_batch_id'] == b,
          'a Pause all that paused nothing left batch B the newest')

    # batch C: m3 and m4; m4 resumed and paused again by hand; m5 paused on its own
    _post(slow, '/v1/missions/%s/resume' % m2, 'resume-m2-again')
    _settled(slow, m2, 'EXECUTING')
    m3, m4, m5 = (_executing(slow, t) for t in ('m3', 'm4', 'm5'))
    _post(slow, '/v1/missions/%s/pause' % m5, 'pause-m5')
    _settled(slow, m5, 'PAUSED')
    _button(page, STRIP, 'Pause all').click()
    for m in (m2, m3, m4):
        _settled(slow, m, 'PAUSED')
    check(sorted(_resumable(slow)) == sorted([m2, m3, m4]), 'the newest batch holds what it paused')
    _post(slow, '/v1/missions/%s/resume' % m4, 'resume-m4')
    _settled(slow, m4, 'EXECUTING')
    _post(slow, '/v1/missions/%s/pause' % m4, 'pause-m4')
    _settled(slow, m4, 'PAUSED')
    check(sorted(_resumable(slow)) == sorted([m2, m3]), 'resumed and paused again by hand: no longer the batch\'s')
    _shown(page, slow, check, 'the newest batch still holds two')

    # Resume all from Work: exactly what Core said, then hidden; a second one changes nothing
    said = _resumable(slow)
    _button(page, WORK, 'Resume all').click()
    for m in said:
        _settled(slow, m, 'EXECUTING')
    check([slow.http('GET', '/v1/missions/' + m).json()['state'] for m in (m1, m4, m5)] == ['PAUSED'] * 3,
          'never an older batch\'s mission or one paused by hand')
    _shown(page, slow, check, 'Resume all resumed what it held')
    wait(page, lambda: _agrees(page, slow), what='the running count equals Core after Resume all')
    check(True, 'the running count equals Core after Resume all')
    check(_post(slow, '/v1/missions/resume-all', 'resume-all-again')['changed'] is False, 'a second Resume all: nothing')

    # every press went to Core's own route, keyed and authorised, one key per press
    check([p for p, _, _ in sent] == ['/missions/pause-all'] * 4 + ['/missions/resume-all'],
          'each press is one POST to its route: %s' % [p for p, _, _ in sent])
    keys = [body.get('idempotency_key') for _, body, _ in sent]
    check(all(keys) and len(set(keys)) == len(keys), 'each press carries its own idempotency key')
    check(all(auth.startswith('Bearer ') for _, _, auth in sent), 'each press is authorised')

    if os.path.isfile(AXE):
        page.add_script_tag(path=AXE)
        bad = page.evaluate('async () => (await axe.run(document, {resultTypes: ["violations"]})).violations'
                            '.filter(v => ["serious", "critical"].includes(v.impact)).map(v => v.id)')
        check(not bad, 'axe on Work with the strip: %s' % bad)

    # a phone: the strip is compact, so Work holds the two verbs, at 44 px
    page.set_viewport_size({'width': 390, 'height': 844})
    _go(page, '#/work')
    check(not page.locator(STRIP).is_visible(), 'the compact strip leaves them to Work on a phone')
    h = _button(page, WORK, 'Pause all').bounding_box()['height']
    check(h >= 44, 'a 44 px target on a phone: %s' % h)
    check(page.evaluate('() => document.documentElement.scrollWidth - innerWidth') <= 0, 'nothing scrolls sideways')

    check(not errors, errors)
    # a project's Work does not offer the workspace-wide verbs (the strip still does)
    page.set_viewport_size({'width': 1280, 'height': 900})
    _go(page, '#/work/prj_00000000000000000000000000')
    page.get_by_role('heading', name='Work', exact=True).wait_for()
    check(page.locator(WORK).count() == 0 and _offers(page, STRIP, 'Pause all'), "a project's Work leaves them to the strip")
    context.close()
    assert check.n >= 33


def test_a_client_without_control_is_told_why(browser, slow):  # noqa: F811
    check = Checks()
    m = _executing(slow, 'm')
    _post(slow, '/v1/missions/pause-all', 'pause-all-ro')
    context = browser.new_context()
    page = context.new_page()
    page.goto(slow.core.launch_url())                  # the default grant: observe only
    page.get_by_role('heading', name='Now', exact=True).wait_for()
    _go(page, '#/work')
    for name in ('Pause all', 'Resume all'):
        b = _button(page, WORK, name)
        b.wait_for()
        check(b.is_disabled(), '%s is disabled for a read-only client' % name)
    check(page.locator(WORK).get_by_text('does not hold the “control” scope').count() == 2, 'it says why')
    check(slow.http('GET', '/v1/missions/' + m).json()['state'] == 'PAUSED', 'nothing was sent')
    context.close()
    assert check.n >= 4
