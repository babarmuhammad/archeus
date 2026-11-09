"""P19.5 R5 in a real browser against a real Core: the change rule and the
row pulse (ADR-0024 §5-6, ADR-0026 §1, rulebook §21 A-02 and A-06).

The change rule (thread T2): on every list whose objects the digest can name,
a row carries the 2 px left-edge rule in thread ink, and says "changed since
you looked", exactly when Core's digest names its object — checked row by row
against Core's own digest, with objects changed before an acknowledgement and
after it. Dismissing the digest clears every rule with one 200 ms fade, and
under reduced motion at once.

The row pulse: an `execution.*` frame about a running attempt pulses its
mission's row once (one CSS opacity step, no animation frame), at most once
per 2 s, never again for an event already presented, never after a remount,
never under reduced motion — and the page is idle before, between and after.
The Relations list joined in P19 (p19-design-gate B2).
Mutation-verified by tools/mutate_p19_5.py (N120 onward) and tools/mutate_p19.py. Check floors keep a
test that silently checks nothing from passing."""

import math
import time

from archeus.core import ports, runtime
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from v1.judge.http import TempCore
from v1.judge.support import FixtureRepo

import pytest

from .conftest import wait
from .motion import advance, freeze, frames, hear, running_animations, settle
from .test_spa_copy import DEPLOY
from .test_spa_halo import _running
from .test_spa_marker import FENCE, _frame, _heard
from .test_spa_p16 import Checks, _go, _mission, _open, _settled
from .test_spa_p18 import slow  # noqa: F401 (a fixture)

IDLE_MS = 10_000
EVERY_MS = 2000     # the registry's row-pulse min_interval_ms (clients/app/tokens/motion.json)

#: every element that can carry the rule, with what names its object and how its left edge is drawn
_ROWS = """() => [...document.querySelectorAll('[data-thread]')].filter(e => e.checkVisibility()).map(e => {
  const s = getComputedStyle(e, '::before');
  return {
    attrs: Object.fromEntries([...e.attributes].filter(a => a.name.startsWith('data-')).map(a => [a.name, a.value])),
    title: e.matches('section') ? e.querySelector(':scope > header h2').firstChild.textContent : null,
    self: !!e.querySelector(':scope > strong'),
    changed: e.dataset.thread === 'changed',
    words: e.textContent.includes('changed since you looked'),
    left: [s.borderLeftStyle, s.borderLeftWidth, s.borderLeftColor, s.left],
    shown: s.opacity,
  };
})"""

_THREAD = """() => {
  const h = getComputedStyle(document.documentElement).getPropertyValue('--thread').trim().replace('#', '');
  return 'rgb(' + [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)).join(', ') + ')';
}"""

#: count the fades the rule plays (its bar's opacity)
_FADES = """() => { window.__fades = 0; document.addEventListener('transitionstart', e => {
  if (e.propertyName === 'opacity' && e.pseudoElement === '::before' && e.target.matches('[data-thread]')) window.__fades++; }); }"""

#: count the row pulses that start, by the mission row they start on
_PULSES = """() => { window.__pulses = []; document.addEventListener('animationstart', e => {
  if (e.animationName === 'row-pulse') window.__pulses.push(e.target.closest('[data-mission]').dataset.mission); }); }"""


@pytest.fixture
def deploy(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(DEPLOY))).start()
    yield tc
    tc.stop()


def _post(tc, path, body):
    r = tc.http('POST', path, body=dict(body, idempotency_key='%s-%f' % (path, time.monotonic())))
    assert r.status == 200, (path, r.body)
    return r.json()


def _idea(tx, *, actor, title):
    """An idea as the conversation captures one (conversation._idea): the only
    writer of ideas is the intent pipeline, which this Core has no model for."""
    idea = entities.Idea(id=ids.new_id('idea'), workspace_id=ids.GLOBAL_WORKSPACE, text=title, title=title)
    tx.insert(idea, actor=actor)
    tx.append(new_event('idea.created', Ref('idea', idea.id), actor, payload={'title': title, 'message_id': None},
                        workspace=idea.workspace_id))
    return {'id': idea.id}


def _quiet(tc):
    """Wait until Core's event head stops moving: what the objects owe has happened."""
    head, still = None, 0
    deadline = time.monotonic() + 30
    while still < 4:
        assert time.monotonic() < deadline, 'Core never went quiet'
        now = tc.http('GET', '/v1/digest').json()['up_to_seq']
        still = still + 1 if now == head else 0
        head = now
        time.sleep(0.25)


def _world(tc, archeus_home, tag):
    """One object of every kind the lists show, named by *tag*."""
    out = {}
    out['account'] = _post(tc, '/v1/accounts', {'harness_id': 'fake', 'label': '%s laptop' % tag, 'auth_kind': 'api_key'})['id']
    # an account with no readable usage runs only as a fallback the user allowed (AP-1)
    _post(tc, '/v1/resource-policies/%s' % out['account'], {'fallback': 'allow'})
    repo = FixtureRepo.create('layered-python', str(archeus_home.parent))
    out['project'] = _post(tc, '/v1/projects', {'name': '%s project' % tag, 'root_paths': [repo.path]})['project']['id']
    out['repo_path'] = repo.path
    out['automation'] = _post(tc, '/v1/automations', {
        'name': '%s automation' % tag,
        'trigger': {'kind': 'event', 'type': 'mission.state_changed', 'where': {'to': 'APPROVAL_REQUIRED'}},
        'template': {'title': '%s follow-up' % tag, 'objective': 'Look again'}})['id']
    out['rule'] = _post(tc, '/v1/policies/rules', {'scope_level': 'USER', 'action_class': 'web', 'decision': 'ASK'})['id']
    out['mission'] = _mission(tc, '%s mission' % tag)
    _settled(tc, out['mission'], 'APPROVAL_REQUIRED')
    # approved, it runs: the run is a session of its own
    a = tc.http('GET', '/v1/approvals?mission=%s' % out['mission']).json()['approvals'][0]
    _post(tc, '/v1/approvals/%s/decide' % a['id'], {'decision': 'approve', 'action_hash': a['action_hash']})
    _settled(tc, out['mission'], 'COMPLETED')
    out['session'] = tc.http('GET', '/v1/sessions?mission=%s' % out['mission']).json()['sessions'][0]['id']
    return out


def _rows(page):
    return page.evaluate(_ROWS)


def _key(r, sections):
    a = r['attrs']
    for attr, kind in (('data-mission', 'mission'), ('data-idea', 'idea'), ('data-project', 'project'),
                       ('data-knowledge', 'knowledge_item'), ('data-rule', 'policy_rule'), ('data-run', 'automation_run'),
                       ('data-harness', 'harness'), ('data-account', 'account'), ('data-session', 'session')):
        if attr in a:
            return (kind, a[attr])
    if 'data-ref' in a:
        return tuple(a['data-ref'].split(':', 1))
    if r['title'] is not None:
        return sections.get(r['title'])
    return sections.get('self') if r['self'] else None


def _check_page(page, tc, check, where, sections, seen, ink):
    """Every visible row that can carry the rule carries it exactly when Core's
    digest names its object; a changed one says so in words, on its left edge."""
    want = {(g['ref']['kind'], g['ref']['id']) for g in tc.http('GET', '/v1/digest').json()['groups']}
    rows = _rows(page)
    check(rows, '%s: rows that can carry the rule' % where)
    for r in rows:
        k = _key(r, sections)
        if k is None:
            continue
        check(r['changed'] == (k in want), '%s: %s ruled %s, in the digest %s' % (where, k, r['changed'], k in want))
        check(r['words'] == r['changed'], '%s: %s says "changed since you looked" only when ruled' % (where, k))
        check(r['left'] == ['solid', '2px', ink, '0px'], '%s: %s the bar on the left edge %s' % (where, k, r['left']))
        check(r['shown'] == ('1' if r['changed'] else '0'), '%s: %s bar shown %s' % (where, k, r['shown']))
        seen.add((where, k, r['changed']))
    return want


def test_the_change_rule_marks_exactly_what_changed_on_every_list(browser, deploy, archeus_home):
    tc = deploy
    check = Checks()
    old = _world(tc, archeus_home, 'Old')
    _quiet(tc)
    tc.http('POST', '/v1/digest/ack', body={'up_to_seq': tc.http('GET', '/v1/digest').json()['up_to_seq']})
    new = _world(tc, archeus_home, 'New')
    _post(tc, '/v1/automations/%s/state' % new['automation'], {'action': 'enable'})
    new['knowledge'] = _post(tc, '/v1/feedback', {
        'subject': {'kind': 'mission', 'id': new['mission']}, 'signal': 'correction', 'text': 'deploys wait for a person',
        'promote': {'type': 'LESSON', 'title': 'A deploy asks first'}})['promoted']['id']
    new['idea'] = tc.core.db.writer.execute(_idea, {'actor': tc.core.system, 'title': 'A digest email'})['id']
    n2 = _mission(tc, 'New second mission')            # fires the new automation: a run of it
    _settled(tc, n2, 'APPROVAL_REQUIRED')
    _quiet(tc)
    runs = tc.http('GET', '/v1/automations/%s' % new['automation']).json().get('runs') or []
    check(runs, 'the new automation ran')
    digest = {(g['ref']['kind'], g['ref']['id']) for g in tc.http('GET', '/v1/digest').json()['groups']}
    for kind, key in (('mission', 'mission'), ('account', 'account'), ('project', 'project'), ('automation', 'automation'),
                      ('policy_rule', 'rule'), ('session', 'session'), ('knowledge_item', 'knowledge'), ('idea', 'idea')):
        check((kind, new[key]) in digest, 'Core names the new %s' % kind)
    for kind, key in (('mission', 'mission'), ('project', 'project'), ('automation', 'automation'),
                      ('policy_rule', 'rule'), ('session', 'session')):
        check((kind, old[key]) not in digest, 'the old %s was acknowledged' % kind)
    check(('automation_run', runs[0]['id']) in digest, 'Core names the run')
    proj = [tc.http('GET', '/v1/projects/%s' % w['project']).json() for w in (new, old)]
    sections = {'New automation': ('automation', new['automation']), 'Old automation': ('automation', old['automation'])}
    for p in proj:
        for repo in p.get('repositories') or []:
            sections['%s · %s' % (repo['kind'], repo['path'])] = ('repository', repo['id'])

    context, page, errors = _open(browser, tc)
    freeze(page)
    ink = page.evaluate(_THREAD)
    seen = set()
    pages = [('#/now', {}), ('#/work', {}), ('#/world', {}), ('#/attention', {}),
             ('#/control/autonomy', {}), ('#/control/automations', {}), ('#/control/resources', {}),
             ('#/control/sessions', {}), ('#/world/%s' % new['project'], {}), ('#/world/%s' % old['project'], {}),
             ('#/o/session/%s/lineage' % new['session'], {'self': ('session', new['session'])}),
             ('#/o/session/%s/lineage' % old['session'], {'self': ('session', old['session'])}),
             ('#/o/knowledge_item/%s/detail' % new['knowledge'], {'self': ('knowledge_item', new['knowledge'])}),
             # the Relations list (P19 B2): each row is its neighbour's
             ('#/o/mission/%s/relations' % new['mission'], {}), ('#/o/mission/%s/relations' % old['mission'], {}),
             ('#/o/session/%s/relations' % new['session'], {})]
    for h, extra in pages:
        _go(page, h)
        settle(page)
        _check_page(page, tc, check, h, dict(sections, **extra), seen, ink)
    _go(page, '#/world')
    page.locator('[role="tab"]', has_text='Knowledge').click()
    settle(page)
    _check_page(page, tc, check, 'knowledge', sections, seen, ink)

    # every applicable list was reached, with a changed row and, where Core
    # holds one, an unchanged row beside it
    def ruled(where, kind, ident, on=True):
        check((where, (kind, ident), on) in seen, '%s: %s %s %s' % (where, kind, ident, 'ruled' if on else 'clear'))
    ruled('#/work', 'mission', n2)              # Now's happening-now rows: the pulse test, which has running work
    ruled('#/work', 'mission', new['mission'])
    ruled('#/work', 'mission', old['mission'], False)
    ruled('#/work', 'idea', new['idea'])
    ruled('#/world', 'project', new['project'])
    ruled('#/world', 'project', old['project'], False)
    ruled('knowledge', 'knowledge_item', new['knowledge'])
    ruled('#/control/autonomy', 'policy_rule', new['rule'])
    ruled('#/control/autonomy', 'policy_rule', old['rule'], False)
    ruled('#/control/automations', 'automation', new['automation'])
    ruled('#/control/automations', 'automation', old['automation'], False)
    ruled('#/control/automations', 'automation_run', runs[0]['id'])
    ruled('#/control/resources', 'account', new['account'])
    ruled('#/control/sessions', 'session', new['session'])
    ruled('#/control/sessions', 'session', old['session'], False)
    ruled('#/o/session/%s/lineage' % new['session'], 'session', new['session'])
    ruled('#/o/session/%s/lineage' % old['session'], 'session', old['session'], False)
    ruled('#/o/knowledge_item/%s/detail' % new['knowledge'], 'knowledge_item', new['knowledge'])
    ruled('#/o/mission/%s/relations' % new['mission'], 'session', new['session'])
    ruled('#/o/mission/%s/relations' % old['mission'], 'session', old['session'], False)
    ruled('#/o/session/%s/relations' % new['session'], 'mission', new['mission'])
    check(any(w == '#/control/resources' and k[0] == 'harness' and not on for w, k, on in seen), 'the harness rows can carry it')
    check(any(w == '#/attention' and on for w, k, on in seen), 'Attention: a ruled item')
    check(any(w == '#/world/%s' % new['project'] and k[0] == 'repository' for w, k, on in seen), 'the repositories')
    # nothing is moving while the rules are up
    _go(page, '#/work')
    settle(page)
    before = frames(page)
    advance(page, IDLE_MS)
    check(frames(page) == before and not running_animations(page), 'the rules are static: nothing runs')

    # Dismiss: every rule fades once, 200 ms, and is gone
    _go(page, '#/now')
    settle(page)
    page.evaluate(_FADES)
    ruled_now = sum(r['changed'] for r in _rows(page))
    check(ruled_now >= 1, 'rules on Now before Dismiss')
    page.get_by_role('button', name='Dismiss').click()
    settle(page)
    wait(page, lambda: not any(r['changed'] for r in _rows(page)), what='the rules leave with the digest')
    wait(page, lambda: page.evaluate('window.__fades') >= ruled_now, what='each rule fades')
    wait(page, lambda: all(r['shown'] == '0' for r in _rows(page)), what='the fade ends clear')
    wait(page, lambda: not running_animations(page), timeout=5, what='the fades end')
    for h, extra in pages[1:9]:
        _go(page, h)
        settle(page)
        want = _check_page(page, tc, check, 'after Dismiss ' + h, dict(sections, **extra), seen, ink)
        for kind, key in (('mission', 'mission'), ('project', 'project'), ('automation', 'automation'), ('session', 'session')):
            check((kind, new[key]) not in want, 'after Dismiss: Core no longer names the new %s' % kind)
    check(not errors, errors)
    context.close()

    # reduced motion: the rule arrives at once and leaves at once, and no fade plays
    fresh = _mission(tc, 'Reduced mission')
    _settled(tc, fresh, 'APPROVAL_REQUIRED')
    _quiet(tc)
    asks = tc.http('GET', '/v1/approvals?mission=%s' % fresh).json()['approvals'][0]['id']
    context, page, errors = _open(browser, tc, reduced_motion='reduce')
    page.evaluate(_FADES)
    _go(page, '#/attention')
    row = page.locator('ul.attention > li[data-ref="approval:%s"]' % asks)
    row.wait_for()
    wait(page, lambda: row.get_attribute('data-thread') == 'changed', what='the new approval is ruled')
    check('changed since you looked' in row.text_content(), 'reduced motion: the words stay')
    # the rule's own removal, read the instant it happens: no transition holds the colour
    gone = page.evaluate("""e => { e.dataset.thread = ''; const o = getComputedStyle(e, '::before').opacity;
                                   e.dataset.thread = 'changed'; return o; }""", row.element_handle())
    check(gone == '0', 'reduced motion: gone at once, not at opacity %s' % gone)
    _go(page, '#/now')
    page.get_by_role('button', name='Dismiss').click()
    wait(page, lambda: page.get_by_role('button', name='Dismiss').count() == 0, what='the digest is dismissed')
    _go(page, '#/attention')
    row.wait_for()
    wait(page, lambda: row.get_attribute('data-thread') == '', what='the rule left with the digest')
    check('changed since you looked' not in row.text_content(), 'and its words')
    check(page.evaluate('window.__fades') == 0 and not running_animations(page), 'reduced motion: no fade')
    check(not errors, errors)
    context.close()
    assert check.n >= 200, 'ran %d checks' % check.n


def _still(page, check, what):
    before = frames(page)
    advance(page, IDLE_MS)
    check(frames(page) == before, '%s: %d frames' % (what, frames(page) - before))
    check(all(math.isfinite(a['end']) for a in running_animations(page)), '%s: an unbounded animation' % what)
    wait(page, lambda: not running_animations(page), timeout=5, what='%s: animations end' % what)


def test_a_running_attempt_pulses_its_mission_row_once(browser, slow):  # noqa: F811
    check = Checks()
    mid = _mission(slow, 'Pulse')
    ex = _running(slow, mid)
    other = _mission(slow, 'Beside it')
    context, page, errors = _open(browser, slow)
    freeze(page)
    _go(page, '#/work')
    settle(page)
    row = page.locator('li[data-mission="%s"]' % mid)
    row.wait_for()
    page.locator('li[data-mission="%s"]' % other).wait_for()
    _still(page, check, 'before')
    page.evaluate(_PULSES)
    pulses = lambda: page.evaluate('window.__pulses')  # noqa: E731
    shown = lambda: row.locator('.row-pulse').get_attribute('data-pulse') if row.locator('.row-pulse').count() else None  # noqa: E731

    # the fence: after it every frame Core sends is history, so only this test moves.
    # The slow harness's own frames may have pulsed the row while the wait above
    # ran (they turn the shell's orbit too, which that wait sees): leave the
    # 2 s window of any such pulse before the fence is heard
    advance(page, EVERY_MS)
    f0 = frames(page)
    hear(page, _frame(ex['id'], FENCE))
    wait(page, lambda: shown() == str(FENCE), what='a new event pulses the row')
    wait(page, lambda: pulses() == [mid], what='one pulse, on its mission\'s row')
    css = page.evaluate("e => { const s = getComputedStyle(e); return [s.animationName, s.animationDuration, s.animationIterationCount]; }",
                        row.locator('.row-pulse').element_handle())
    check(css == ['row-pulse', '0.24s', '1'], 'one 240 ms opacity step, once: %s' % css)
    check(page.locator('li[data-mission="%s"] .row-pulse[data-pulse="%d"]' % (other, FENCE)).count() == 0,
          'the other mission\'s row does not pulse')
    check(frames(page) == f0, 'a CSS pulse runs no animation frame')
    wait(page, lambda: not running_animations(page), timeout=5, what='the pulse ends')

    # at most one per row every 2 s
    advance(page, EVERY_MS // 4)
    _heard(page, _frame(ex['id'], FENCE + 1))
    settle(page)
    check(pulses() == [mid] and shown() == str(FENCE), 'a second batch inside 2 s: no pulse')
    advance(page, EVERY_MS)
    hear(page, _frame(ex['id'], FENCE + 2))
    wait(page, lambda: shown() == str(FENCE + 2), what='after 2 s the next batch pulses')
    wait(page, lambda: len(pulses()) == 2, timeout=5, what='the second pulse plays')
    check(pulses() == [mid, mid], 'exactly two pulses: %s' % pulses())

    # nothing presented replays: the same event, an older one, a lost stream and a resync, a remount
    advance(page, 3 * EVERY_MS)
    _heard(page, _frame(ex['id'], FENCE + 2))
    _heard(page, _frame(ex['id'], FENCE + 1))
    hear(page, {'event': 'stream-lost'})
    hear(page, {'event': 'stream-open'})
    settle(page, 5000)
    hear(page, {'event': 'resync'})
    settle(page, 5000)
    check(pulses() == [mid, mid], 'a historical event or a resync pulsed: %s' % pulses())
    _go(page, '#/now')
    settle(page)
    now_row = page.locator('li[data-mission="%s"]' % mid)
    now_row.wait_for()
    check(now_row.locator('.row-pulse').count() == 0, 'a remount replays nothing')
    # Now's happening-now row carries the change rule too: nothing here was ever dismissed
    check(('mission', mid) in {(g['ref']['kind'], g['ref']['id']) for g in slow.http('GET', '/v1/digest').json()['groups']}
          and now_row.get_attribute('data-thread') == 'changed' and 'changed since you looked' in now_row.text_content(),
          'the running mission is ruled on Now')
    advance(page, 3 * EVERY_MS)
    hear(page, _frame(ex['id'], FENCE + 3))
    wait(page, lambda: now_row.locator('.row-pulse').count() == 1, what='Now\'s row pulses too')
    wait(page, lambda: len(pulses()) == 3, timeout=5, what='it plays')
    check(pulses() == [mid, mid, mid], 'one more pulse')
    _still(page, check, 'after')
    check(not errors, errors)
    context.close()

    # reduced motion: no pulse; the row's state word says the work is running
    context, page, errors = _open(browser, slow, reduced_motion='reduce')
    freeze(page)
    _go(page, '#/work')
    settle(page)
    row = page.locator('li[data-mission="%s"]' % mid)
    row.wait_for()
    page.evaluate(_PULSES)
    f0 = frames(page)
    _heard(page, _frame(ex['id'], FENCE + 10))
    settle(page)
    check(row.locator('.row-pulse').count() == 0 and page.evaluate('window.__pulses') == [], 'reduced motion: no pulse')
    check(frames(page) == f0 and not running_animations(page), 'reduced motion: nothing runs')
    check(row.locator('.state .label').inner_text().strip(), 'the state word is the equivalent')
    check(not errors, errors)
    context.close()
    assert check.n >= 18, 'ran %d checks' % check.n
