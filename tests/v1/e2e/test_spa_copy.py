"""R1's copy/id gate and the minimum R9 Details disclosure (ADR-0029 §4,
testing-strategy §7 `innerText`, rulebook §5.13 and §15), in a real browser
against a real Core.

Every page is read as a person reads it — the visible text and the accessible
names, never the closed contents of a disclosure — and must carry no Archeus
id, no JSON and no hash. The identifiers are not gone: Core still returns them,
and each object shows them, labelled by what they name, behind one explicit
Details disclosure that is closed by default and holds rows, never a dump.
Mutation-verified by tools/mutate_p19_5.py (N71-N79)."""

import re
import time

from archeus.core import engine, ports, runtime
from archeus.core.domain import ids
from v1.judge.http import TempCore
from v1.judge.support import FixtureRepo

import pytest

from .test_spa_p16 import DESTINATIONS, MISSION_TABS, NAV, SECTIONS, _go, _mission, _open, _settled

CROCK = '[0-9A-HJKMNP-TV-Z]'
#: what may never be read in a default view, by what it is. The id prefixes are
#: Core's own list (ids.PREFIXES), not a copy of it.
LEAKS = {
    'id': re.compile(r'\b(?:%s)_%s{6,}|\bws_global\b' % (
        '|'.join(sorted(ids.PREFIXES.values(), key=len, reverse=True)), CROCK)),
    'ulid': re.compile(r'\b[0-7]%s{25}\b' % CROCK),
    'json': re.compile(r'[{\[]\s*"[^"\n]{1,64}"\s*:'),
    'hash': re.compile(r'\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,}\b'),
}

DEPLOY = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0], action_classes=['deploy'])])

#: the text a person meets: visible text nodes, and the accessible names of
#: visible elements. A closed <details> renders nothing but its summary.
SEEN = '''() => {
  const out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode())
    if (n.textContent.trim() && n.parentElement && n.parentElement.checkVisibility({ visibilityProperty: true, contentVisibilityAuto: true }))
      out.push(n.textContent);
  for (const el of document.querySelectorAll('[aria-label],[title]'))
    if (el.checkVisibility()) out.push(el.getAttribute('aria-label') || '', el.getAttribute('title') || '');
  return out.join('\\n');
}'''

DETAILS = '''() => [...document.querySelectorAll('details[data-details]')].map((d) => ({
  open: d.open,
  summary: d.querySelector(':scope > summary')?.textContent ?? null,
  stray: d.querySelectorAll(':scope > :not(summary):not(dl.kv)').length,
  rows: [...d.querySelectorAll(':scope > dl.kv > div')].map((r) => [r.querySelector('dt')?.textContent ?? '', r.querySelector('dd')?.textContent ?? '', r.children.length]),
}))'''


def leaks(text):
    return {k: sorted(set(p.findall(text))) for k, p in LEAKS.items() if p.search(text)}


def test_the_leak_patterns_catch_what_they_name_and_nothing_a_person_reads():
    """The gate's own patterns, without a browser: each catches its kind, in
    full and shortened, and none fires on the words, numbers and names the
    pages are meant to show."""
    mid = ids.new_id('mission')
    for text, kind in ((mid, 'id'), ('mission ' + mid[:12] + '…', 'id'), ('ws_global', 'id'),
                       (ids.new_ulid(), 'ulid'), ('{"type": "mission"}', 'json'),
                       ('[{"task":"t1"}]', 'json'), ('d7704d84ec561fb1', 'hash'), ('at 3f9a2c1', 'hash')):
        assert kind in leaks(text), (kind, text)
    for text in ('claude-opus-5-5', 'claude_code', 'fake', '2026-10-01 21:21', 'as of event 1234',
                 'Plan v1', 'attempt 1', 't1 · Do the work', 'five hour 42%', 'deploy', 'Work laptop',
                 'When a mission.state_changed event happens, where to is FAILED', 'added 12 bed'):
        assert not leaks(text), text


def _read(page, where, check):
    seen = page.evaluate(SEEN)
    check(len(seen) > 40, '%s rendered something to read' % where)
    bad = leaks(seen)
    assert not bad, '%s shows %s' % (where, bad)
    for d in page.evaluate(DETAILS):
        assert not d['open'] and d['summary'] == 'Details', (where, d)
        assert d['rows'] and not d['stray'], (where, d)
        for k, v, n in d['rows']:
            assert n == 2 and k and v and not LEAKS['json'].search(v), (where, k, v)
    return seen


def _details(page, scope='body'):
    """{label: value} of every Details under *scope* (closed or not)."""
    rows = {}
    for d in page.locator(scope).first.evaluate('''(root) => [...root.querySelectorAll('details[data-details] > dl.kv > div')]
      .map((r) => [r.querySelector('dt').textContent, r.querySelector('dd').textContent])'''):
        rows[d[0]] = d[1]
    return rows


def _wait_heading(page, text):
    page.locator('h1', has_text=text).first.wait_for(timeout=15000)


@pytest.fixture
def deploy(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(DEPLOY))).start()
    yield tc
    tc.stop()


def test_no_page_shows_an_id_json_or_hash_and_details_holds_them(browser, deploy, archeus_home):
    tc = deploy
    n = [0]

    def check(ok, what):
        assert ok, what
        n[0] += 1

    # what the pages have to say: an account, a project with a repository, an
    # automation, and a mission that asks before it deploys
    r = tc.http('POST', '/v1/accounts', body={'harness_id': 'fake', 'label': 'Work laptop', 'auth_kind': 'api_key',
                                              'idempotency_key': 'acc-%f' % time.time()})
    assert r.status == 200, r.body
    acc = r.json()['id']
    # an account with no readable usage runs only as a fallback the user allowed (AP-1)
    r = tc.http('POST', '/v1/resource-policies/%s' % acc, body={'fallback': 'allow', 'idempotency_key': 'rpo-%f' % time.time()})
    assert r.status == 200, r.body
    repo = FixtureRepo.create('layered-python', str(archeus_home.parent))
    r = tc.http('POST', '/v1/projects', body={'name': 'Atlas', 'root_paths': [repo.path], 'idempotency_key': 'prj-%f' % time.time()})
    assert r.status == 200, r.body
    pid = r.json()['project']['id']
    r = tc.http('POST', '/v1/automations', body={'name': 'Look at failures', 'idempotency_key': 'aut-%f' % time.time(),
                                                 'trigger': {'kind': 'event', 'type': 'mission.state_changed', 'where': {'to': 'FAILED'}},
                                                 'template': {'title': 'Why did {subject.id} fail', 'objective': 'Find the cause'}})
    assert r.status == 200, r.body
    aut = r.json()['id']
    mid = _mission(tc, 'Deploy the docs')
    _settled(tc, mid, 'APPROVAL_REQUIRED')
    approval = tc.http('GET', '/v1/approvals?mission=%s' % mid).json()['approvals'][0]
    context, page, errors = _open(browser, tc)

    # waiting on you: the approval card and the mission, read before the decision
    for h in ('#/now', '#/attention', '#/o/mission/%s' % mid):
        _go(page, h)
        page.locator('text=Deploy the docs >> visible=true').first.wait_for(timeout=15000)
        _read(page, h, check)
    _go(page, '#/attention')
    card = page.locator('article[data-kind="approval"]')
    card.wait_for()
    got = _details(page, 'article[data-kind="approval"]')
    check(got.get('Action hash (what an approval is bound to)') == approval['action_hash'], 'the action hash is in Details, whole')
    check(got.get('Approval id') == approval['id'] and got.get('Mission id') == mid, 'the approval names its ids')
    card.get_by_role('button', name='Approve plan').click()
    _settled(tc, mid, 'COMPLETED')

    # the identifiers are still Core's: nothing was deleted from the API to pass
    m = tc.http('GET', '/v1/missions/%s' % mid).json()
    plan = tc.http('GET', '/v1/missions/%s/plan' % mid).json()['plan']
    task = plan['tasks'][0]
    ex = tc.http('GET', '/v1/tasks/%s/executions' % task['id']).json()['executions'][-1]
    assert m['id'] == mid and m['integration_branch'].endswith(mid) and ex['account_id'] == acc
    session = tc.http('GET', '/v1/sessions?mission=%s' % mid).json()['sessions'][0]
    routes = tc.http('GET', '/v1/route-decisions?source=%s' % mid).json()['route_decisions']
    policies = tc.http('GET', '/v1/policy-decisions?mission=%s' % mid).json()['policy_decisions']
    verifications = tc.http('GET', '/v1/missions/%s/verifications' % mid).json()['verifications']
    proj = tc.http('GET', '/v1/projects/%s' % pid).json()
    r = tc.http('POST', '/v1/feedback', body={'subject': {'kind': 'mission', 'id': mid}, 'signal': 'correction',
                                              'text': 'deploys wait for a person', 'idempotency_key': 'fb-%f' % time.time(),
                                              'promote': {'type': 'LESSON', 'title': 'A deploy asks first'}})
    assert r.status == 200, r.body
    kid = r.json()['promoted']['id']

    pages = []
    for did, label in DESTINATIONS:
        pages.append(('#/control/autonomy' if did == 'control' else '#/' + did, label))
    pages += [('#/control/' + s, 'Control') for s in SECTIONS]
    pages += [('#/o/mission/%s/%s' % (mid, t), 'Deploy the docs') for t in MISSION_TABS]
    pages += [('#/o/execution/%s/%s' % (ex['id'], t), 'attempt') for t in NAV['inspector_tabs']['execution']]
    pages += [('#/o/session/%s/%s' % (session['id'], t), 'Session') for t in NAV['inspector_tabs']['session']]
    pages += [('#/o/plan/%s' % plan['id'], 'Plan version'), ('#/o/task/%s' % task['id'], 'Task'),
              ('#/world/%s' % pid, 'Atlas'), ('#/o/project/%s' % pid, 'Project')]
    pages += [('#/o/route_decision/%s' % x['id'], 'Route decision') for x in routes]
    pages += [('#/o/policy_decision/%s' % x['id'], 'Policy decision') for x in policies]
    pages += [('#/o/verification/%s' % x['id'], 'Verification') for x in verifications]
    pages += [('#/o/repository/%s' % x['id'], 'Repository') for x in proj.get('repositories') or []]
    pages += [('#/o/knowledge_item/%s/%s' % (kid, t), 'A deploy asks first') for t in NAV['inspector_tabs']['knowledge_item']]
    seen = {}
    for h, expect in pages:
        _go(page, h)
        _wait_heading(page, expect)
        page.wait_for_timeout(300)                  # named references read their own rows
        seen[h] = _read(page, h, check)

    # the readable half is still there: names, states, labels, sentences
    insp = '#/o/mission/%s/outcome' % mid
    check('Deploy the docs' in seen[insp] and 'verified and reviewed' in seen[insp], 'the mission by title and state')
    check('Work laptop' in seen['#/o/execution/%s/output' % ex['id']], 'the account by its label on the execution')
    check('Work laptop' in seen['#/control/resources'], 'the account by its label in Control')
    check('When a mission.state_changed event happens, where to is FAILED' in seen['#/control/automations'], 'the trigger in words')
    check('Start a mission “Why did {subject.id} fail”: Find the cause' in seen['#/control/automations'], 'the template in words')
    check('fake' in seen['#/o/session/%s/brief' % session['id']], 'the session by its harness')

    # Details exposes what it should, whole, and opening it shows it
    exposed = (
        (insp, '.insp-head', {'Mission id': mid, 'Plan id': plan['id'], 'Mission branch (git)': m['integration_branch']}),
        ('#/o/execution/%s/output' % ex['id'], '.insp-head', {'Execution id': ex['id'], 'Account id': acc, 'Task id': task['id']}),
        ('#/o/session/%s/brief' % session['id'], '.insp-head', {'Session id': session['id'], 'Mission id': mid}),
        ('#/o/plan/%s' % plan['id'], '.insp-head', {'Plan version id': plan['id'], 'Plan digest': plan['digest']}),
        ('#/control/resources', 'main', {'Account id': acc}),
        ('#/control/automations', 'main', {'Automation id': aut}),
        ('#/world/%s' % pid, 'main', {'Project id': pid}),
        ('#/o/knowledge_item/%s' % kid, '.insp-head', {'Knowledge item id': kid}),
    )
    for h, scope, want in exposed:
        _go(page, h)
        page.locator(scope).first.locator('details[data-details]').first.wait_for(state='attached')
        got = _details(page, scope)
        for k, v in want.items():
            check(got.get(k) == v, '%s Details has %s' % (h, k))
        d = page.locator(scope).first.locator('details[data-details]').first
        d.locator('summary').click()
        opened = page.evaluate(SEEN)
        check(next(iter(want.values())) in opened, '%s: opening Details shows the id' % h)

    # one read per page, the three before the decision, two on the approval, six
    # readable, and per Details every id it must hold plus the opening
    floor = len(pages) + 3 + 2 + 6 + sum(len(w) + 1 for _h, _s, w in exposed)
    assert n[0] >= floor, 'ran %d checks, floor %d' % (n[0], floor)
    assert not errors, errors
    context.close()
