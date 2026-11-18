"""P19.5 R11 in a real browser against a real Core: the read-only Ideas
stepper (rulebook §43; D-11, rulebook §46.1).

Each idea on Work shows Core's path — Captured to Learned — with the idea's
place on it marked as the current step, and what Core records as its evidence
(where it was captured, the mission it was made into). Core has no
idea-transition command, so no step is a button. Mutation-verified by
tools/mutate_p19_5.py. Check floors keep a test that silently checks nothing
from passing."""

from archeus.core.domain import entities as E, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref

from .conftest import wait
from .test_spa_p16 import Checks, _go, _mission, _open

PATH = ['Captured', 'Understood', 'Explored', 'Validated', 'Concept', 'Planned', 'Scheduled', 'Implementing',
        'Completed', 'Learned']


def _idea(tc, text, state, mission=None, message=None):
    """An idea as Core's writer records it (a browser Core has no own-call
    adapter to classify a message as an idea)."""
    actor = Ref('user_device', tc.http('GET', '/v1/sync').json()['client']['principal_id'])
    i = E.Idea(id=ids.new_id('idea'), workspace_id=ids.GLOBAL_WORKSPACE, text=text, state=state,
               promoted_mission_id=mission, origin_message_id=message)

    def run(tx, **_):
        tx.insert(i, actor=actor)
        tx.append(new_event('idea.created', Ref('idea', i.id), actor, payload={}, workspace=ids.GLOBAL_WORKSPACE))
    tc.core.db.writer.execute(run, {})
    return i.id


def _get(tc, iid):
    return next(x for x in tc.http('GET', '/v1/ideas').json()['ideas'] if x['id'] == iid)


def test_each_idea_shows_where_it_is_on_cores_path_and_offers_no_transition(browser, core):
    check = Checks()
    first = _idea(core, 'a weekly digest email of what Archeus did', 'CAPTURED', message=ids.new_id('message'))
    idea = _get(core, first)
    check(idea['state'] == 'CAPTURED', 'Core: a captured idea')
    context, page, errors = _open(browser, core)
    _go(page, '#/work')
    row = page.locator('main li[data-idea="%s"]' % idea['id'])
    row.wait_for()
    steps = row.locator('[data-stepper] > li')
    check(steps.all_inner_texts() == PATH, 'Core\'s path in order: %s' % steps.all_inner_texts())
    check(row.locator('[data-stepper]').get_attribute('aria-label') == 'Where this idea is on its path', 'named')
    check(row.locator('[aria-current="step"]').inner_text() == 'Captured', 'the idea\'s place is the current step')
    check(row.locator('[aria-current="step"]').count() == 1, 'one current step')
    check(row.locator('button').count() == 0, 'no step is a button: Core has no transition command')
    check(row.locator('[data-idea-evidence]').inner_text().startswith('Captured from the conversation.'), 'where it came from')

    mid = _mission(core, 'Weekly digest')
    second = _idea(core, 'a monthly report', 'IMPLEMENTING', mission=mid)
    idea = _get(core, second)
    row = page.locator('main li[data-idea="%s"]' % second)
    wait(page, lambda: row.count() == 1, what='the second idea arrives')
    check(row.locator('[aria-current="step"]').inner_text() == 'Implementing', 'its place: implementing')
    check(idea['state'] == 'IMPLEMENTING', 'Core: the idea is implementing')
    link = row.locator('[data-idea-evidence] a')
    link.wait_for()
    check(link.get_attribute('href') == '#/o/mission/' + mid, 'it links the mission it became')
    check('Made into' in row.locator('[data-idea-evidence]').inner_text(), 'and says so')
    check(row.locator('[data-stepper] [data-at="earlier"]').count() == 7, 'the steps before it are only earlier')

    page.set_viewport_size({'width': 390, 'height': 844})
    _go(page, '#/work')
    row.wait_for()
    check(page.evaluate('() => document.documentElement.scrollWidth - innerWidth') <= 0, 'a phone: the path wraps, nothing scrolls sideways')
    check(not errors, errors)
    context.close()
    assert check.n >= 13
