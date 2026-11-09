"""T-749 (pv22-verification-hardening): the branches of the review own call
(`archeus/core/verification/reviewer.py`) that no test in tests/v1 reached — the
fail-closed and denial paths first (what verdict Core admits, what may count as
evidence at all), then the boundary values (the 12-character revision, the 500
character claim, the 80-row diff), then the error paths.

The module's existing tests are tests/v1/unit/test_verification_units.py (the
closest one: `independent` and `forbidden` over plain tuples, whose style and
fixtures this file copies) and
tests/v1/integration/test_t144_prompt_projection.py (the CLAIM projection and the
cap that follows it). Added here is the rest of the module, read over the real
database so every `rows.where` filter is a real filter and not a fake's answer: a
Verification of a superseded plan, of another task, of another mission, at a
revision the mission no longer holds, with no checks, with no revision, with no
summary, with an account only its route decision knows.

Nothing here spawns a process, opens a socket, runs git or names a platform-specific API. The
one OS-facing object is a `Homes` matcher built the way its own docstring tells
tests to build it (`shorts` injected, so nothing probes a short name), holding a
path from pytest's tmp_path. The ten branches this file exists for are listed
with file:line in /work/QWEN-DONE-T-749.md, each with the test that covers it and
what would survive its removal.
"""

import sys

import pytest

from archeus.core.domain import entities, ids, shapes
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes
from archeus.core.verification import reviewer
from archeus.infra.db import Database, rows

#: the mission branch head as Core recorded it, and a commit the mission does not hold
HEAD, STALE = 'a' * 40, 'b' * 40
HEAD12, STALE12 = HEAD[:12], STALE[:12]
#: one check row, in both kinds the prompt quotes, and what the mission asks
CHECK = {'name': 'tool --check', 'kind': 'command', 'result': 'pass'}
GIT = {'name': 'git diff', 'kind': 'git', 'result': 'pass'}
AUTO = {'text': 'the checks pass', 'check': 'automatic'}
HUMAN = {'text': 'a person looks at it', 'check': 'human'}
#: the task every scene starts with, as the prompt renders it
TASK_LINE = '- t1 Do the thing (VERIFYING): do it well'
CLAIM = '    CLAIM by the agent (attempt %d): '
ACC_A, ACC_B = ids.new_id('account'), ids.new_id('account')
#: the event each seeded row owes its insert, as the writer's own registry names it
_EVENTS = {entities.Mission: ('mission.created', 'mission'),
           entities.Plan: ('plan.created', 'plan'),
           entities.Task: ('task.created', 'task'),
           entities.Execution: ('execution.intent', 'execution'),
           entities.Verification: ('verification.created', 'verification'),
           entities.RouteDecision: ('route.decided', 'route_decision')}


def _homes(*paths):
    """A real `Homes` matcher over *paths*, with the seams a unit test may use:
    `shorts` injected so nothing probes the filesystem, and account keys with no
    separator so no public-account id (and no discovery secret) is read."""
    return Homes((), tuple(('fake', 'fakeharness%d' % i, p) for i, p in enumerate(paths)),
                 shorts=lambda _p: None, platform=sys.platform)


def _lines(text):
    return text.split('\n')


def _after(text, marker):
    """Every line after the exact line *marker*."""
    ls = _lines(text)
    return ls[ls.index(marker) + 1:]


def _block(text, marker, word):
    """The indented lines under *task line* *marker* that carry *word*: one task's
    verifications, or its claims, kept apart from the acceptance lines it indents
    the same way."""
    out = []
    for line in _after(text, marker):
        if not line.startswith('    '):
            break
        if word in line:
            out.append(line)
    return out


class _Rig:
    """Rows as `reviewer.py` reads them, in the one database it reads: the real
    `Database.open()` under the test's own ARCHEUS_HOME (tests/v1/conftest.py),
    filled by plain inserts and never by a command, a process or git. One per
    test: two of them would be two Cores over that home, reading each other's
    rows (the sibling worker rig says the same)."""

    def __init__(self):
        self.db = Database.open()
        self.actor = Ref('system', ids.new_id('principal'))

    def close(self):
        self.db.close()

    def put(self, *entities_):
        """One transaction of plain inserts, each with the event its insert owes
        (the writer refuses a mutation that records none)."""
        def run(tx, **_):
            for e in entities_:
                tx.insert(e, actor=self.actor)
                type_, kind = _EVENTS[type(e)]
                tx.append(new_event(type_, Ref(kind, e.id), self.actor,
                                    payload={'fields': []}))
        self.db.writer.execute(run, {})

    # ── the rows the reviewer reads ──

    def mission(self, **f):
        f.setdefault('id', ids.new_id('mission'))
        f.setdefault('workspace_id', ids.GLOBAL_WORKSPACE)
        f.setdefault('title', 'Review this')
        f.setdefault('objective', 'make it so')
        f.setdefault('integration_head', HEAD)
        f.setdefault('state', 'EXECUTING')
        self.put(entities.Mission(**f))
        return f['id']

    def plan(self, mission_id, plan_version=1, **f):
        f.setdefault('id', ids.new_id('plan'))
        f.update(mission_id=mission_id, plan_version=plan_version)
        f.setdefault('state', 'APPROVED')
        self.put(entities.Plan(**f))
        return f['id']

    def task(self, plan_id, mission_id, key, **f):
        f.setdefault('id', ids.new_id('task'))
        f.update(plan_id=plan_id, mission_id=mission_id, key=key)
        f.setdefault('title', 'Do the thing')
        f.setdefault('kind', 'code_change')
        f.setdefault('objective', 'do it well')
        f.setdefault('acceptance', (AUTO,))
        f.setdefault('state', 'VERIFYING')
        self.put(entities.Task(**f))
        return f['id']

    def execution(self, task_id, mission_id, **f):
        f.setdefault('id', ids.new_id('execution'))
        f.update(task_id=task_id, mission_id=mission_id)
        f.setdefault('attempt', 1)
        f.setdefault('state', 'ENDED_OK')
        f.setdefault('harness_id', 'fake')
        self.put(entities.Execution(**f))
        return f['id']

    def verification(self, subject, plan_id, **f):
        f.setdefault('id', ids.new_id('verification'))
        f.update(subject=subject, plan_id=plan_id)
        f.setdefault('verifier', 'code')
        f.setdefault('state', 'PASSED')
        f.setdefault('revision', HEAD)
        if subject.kind == 'mission':
            f.setdefault('criterion', 0)
        self.put(entities.Verification(**f))
        return f['id']

    def decision(self, **f):
        f.setdefault('id', ids.new_id('route_decision'))
        f.setdefault('subject', Ref('route_decision', ids.new_id('route_decision')))
        f.setdefault('purpose', 'review')
        f.setdefault('harness_id', 'fake')
        self.put(entities.RouteDecision(**f))
        return f['id']

    # ── the module under test, over a read snapshot ──

    def prompt(self, mid, diff=None, homes=()):
        with self.db.read() as conn:
            m = rows.get(conn, entities.Mission, mid).entity
            return reviewer.prompt(conn, m, diff, _homes(*homes))

    def executed(self, mid):
        with self.db.read() as conn:
            return reviewer.executions_of(conn, rows.get(conn, entities.Mission, mid).entity)

    def resource_of(self, rd_id):
        with self.db.read() as conn:
            return reviewer.resource_of(conn, rd_id)

    # ── the scene every prompt test starts from, unless it says otherwise ──

    def scene(self, **mission):
        """One mission, the plan in force, and the one task that plan gave it."""
        mid = self.mission(**mission)
        pid = self.plan(mid)
        return {'mid': mid, 'pid': pid, 'tid': self.task(pid, mid, 't1')}


@pytest.fixture
def rig():
    made = []

    def make():
        assert not made, 'one rig per test: two would share the one database'
        made.append(_Rig())
        return made[0]
    yield make
    for r in made:
        r.close()


# ── the verdict Core admits: no accept that quietly names what is missing ──

def test_an_acceptance_that_names_a_missing_requirement_is_refused():
    # reviewer.py:37-38, the one rule the schema cannot say: dropping the rule,
    # or the `and`, lets an accepting review that admits a gap through
    parsed = {'verdict': 'accept', 'summary': 'fine', 'requirements_missing': ['r2']}
    assert reviewer.check(parsed) == ['an accepting review lists missing requirements']


def test_only_an_acceptance_is_held_to_naming_nothing_missing():
    # reviewer.py:37 (both operands) and :39: a refusal that reached
    # `changes_requested` would silence the verdict that asks for the work to be
    # redone, and a missing key is not a missing requirement
    for verdict in ('changes_requested', 'reject'):
        assert reviewer.check({'verdict': verdict, 'summary': 's',
                               'requirements_missing': ['r1']}) == []
    assert reviewer.check({'verdict': 'accept', 'summary': 's'}) == []
    assert reviewer.check({'verdict': 'accept', 'summary': 's',
                           'requirements_missing': []}) == []
    assert reviewer.check({}) == []


def test_only_the_three_verdicts_and_a_summary_are_admissible_at_all():
    # reviewer.py:16-22: a verdict outside the enum, or a review with no summary,
    # would be recorded as Core's own judgement of the work; the caps are what
    # keeps a model's answer inside the row and inside the ledger
    for verdict in ('accept', 'changes_requested', 'reject'):
        shapes.validate({'verdict': verdict, 'summary': 'ok'}, reviewer.SCHEMA)
    for bad in ({'verdict': 'approve', 'summary': 'ok'},        # not a verdict Core knows
                {'verdict': 'ACCEPT', 'summary': 'ok'},         # and not a case-free match
                {'verdict': 'accept'},                          # the reviewer said nothing
                {'verdict': 'accept', 'summary': 'ok', 'verdict2': 'accept'},
                {'verdict': 'accept', 'summary': 'ok', 'met': ['x']},
                {'verdict': 'accept', 'summary': 'x' * 2001},   # _S
                {'verdict': 'accept', 'summary': 'ok', 'risks': 'one risk'},
                {'verdict': 'accept', 'summary': 'ok', 'risks': ['r' * 501]},
                {'verdict': 'accept', 'summary': 'ok', 'risks': ['x'] * 21}):
        with pytest.raises(shapes.Invalid):
            shapes.validate(bad, reviewer.SCHEMA)


# ── what the reviewer is told about the work: rows, never the agent's word ──

def test_an_empty_desired_outcome_is_never_offered_as_an_outcome(rig):
    # reviewer.py:47-48: inverted, an empty field would read as a stated outcome
    r = rig()
    said = r.scene(desired_outcome='it starts without a prompt')
    silent = r.scene(desired_outcome='')
    assert [x for x in _lines(r.prompt(said['mid']))
            if x.startswith('Desired outcome')] == ['Desired outcome: it starts '
                                                    'without a prompt']
    assert not [x for x in _lines(r.prompt(silent['mid']))
                if x.startswith('Desired outcome')]


def test_a_requirement_keeps_the_origin_the_row_carries(rig):
    # reviewer.py:52: what the user asked and what Archeus inferred stay apart on
    # every line; shown the other way, the reviewer may discount the user's own
    # words, which the state machines §7 will not allow. (The `origin` default of
    # this line cannot be reached from a row: `Mission._check` refuses a
    # requirement or constraint that does not name one, entities.py:778-783.)
    r = rig()
    s = r.scene(requirements=({'text': 'keeps the old api', 'origin': 'explicit'},
                             {'text': 'no new dependency', 'origin': 'inferred'}))
    lines = _lines(r.prompt(s['mid']))
    assert lines[lines.index('Requirements:') + 1] == '- keeps the old api (explicit)'
    assert '- no new dependency (inferred)' in lines


def test_requirements_and_constraints_are_kept_apart_and_silent_when_empty(rig):
    # reviewer.py:49-52: the two headings come out of one tuple, so a swapped
    # pair turns a hard constraint into a requirement; and an empty list prints
    # no heading at all rather than one the reviewer reads as "nothing asked here"
    r = rig()
    s = r.scene(requirements=({'text': 'keeps the old api', 'origin': 'explicit'},),
                constraints=())
    lines = _lines(r.prompt(s['mid']))
    assert 'Constraints:' not in lines
    assert lines[lines.index('Requirements:') + 1] == '- keeps the old api (explicit)'
    mid = r.mission(requirements=(), constraints=({'text': 'offline only',
                                                  'origin': 'explicit'},))
    r.plan(mid)
    assert _after(r.prompt(mid), 'Constraints:')[0] == '- offline only (explicit)'


def test_every_success_criterion_says_who_has_to_check_it(rig):
    # reviewer.py:53-55: a human criterion shown as automatic reads to the
    # reviewer, and to the `verified` guard it is quoting, as a pass a command gave
    r = rig()
    s = r.scene(success_criteria=(AUTO, HUMAN))
    lines = _after(r.prompt(s['mid']), 'Success criteria:')
    assert lines[:2] == ['- [automatic] the checks pass', '- [human] a person looks at it']


def test_the_prompt_is_built_from_the_plan_in_force_not_the_first_plan(rig):
    # reviewer.py:45, 56, 58: after a replan the superseded version's tasks are
    # not the work under review; showing them reviews work nobody is doing
    r = rig()
    mid = r.mission()
    old = r.plan(mid, 1, state='SUPERSEDED')
    r.task(old, mid, 't9', title='The abandoned way')
    new = r.plan(mid, 2)
    r.verification(Ref('task', r.task(new, mid, 't1')), new)
    text = r.prompt(mid)
    lines = _lines(text)
    assert 'Plan version 2, tasks:' in lines
    assert TASK_LINE in lines
    assert 't9' not in text and 'The abandoned way' not in text


def test_a_verification_of_a_superseded_plan_is_not_evidence(rig):
    # reviewer.py:57: the plan_id filter. Without it a FAILED row left by the plan
    # the mission no longer runs is quoted as this plan's evidence — and a PASSED
    # one of that plan would satisfy the reviewer for a check nobody re-ran
    r = rig()
    mid = r.mission()
    old, new = r.plan(mid, 1, state='SUPERSEDED'), r.plan(mid, 2)
    tid = r.task(new, mid, 't1')
    r.verification(Ref('task', tid), old, verifier='research', state='FAILED',
                   checks=({'name': 'the old check', 'kind': 'command', 'result': 'fail'},))
    text = r.prompt(mid)
    assert 'the old check' not in text and 'research' not in text
    assert 'verification ' not in text


def test_a_task_line_quotes_the_verifier_and_every_check_it_ran(rig):
    # reviewer.py:60-66: state, verifier, the short revision and each check by
    # name and result are the whole of what Core can show; a joined-out `result`
    # would leave a failed check indistinguishable from a passed one
    r = rig()
    s = r.scene()
    r.verification(Ref('task', s['tid']), s['pid'], checks=(dict(CHECK), dict(GIT)))
    assert _block(r.prompt(s['mid']), TASK_LINE, 'verification ') == [
        '    verification PASSED by code at %s: tool --check pass; git diff pass' % HEAD12]
    # what the task accepts is indented the same way and is not a check that ran
    assert _block(r.prompt(s['mid']), TASK_LINE, 'acceptance ') == [
        '    acceptance [automatic]: the checks pass']


def test_the_weakening_findings_of_a_verification_are_listed_for_the_reviewer(rig):
    # T-1067: the advisory check's findings reach the prompt, labelled as read from
    # the diff and 20 to a verification
    r = rig()
    s = r.scene()
    weak = {'name': 'test weakening (advisory)', 'kind': 'git', 'result': 'pass',
            'findings': ['test file deleted: tests/a.py']
                        + ['assertions removed: t%d' % i for i in range(25)]}
    r.verification(Ref('task', s['tid']), s['pid'], checks=(dict(CHECK), weak))
    block = _block(r.prompt(s['mid']), TASK_LINE, 'advisory, read')
    assert block[0] == ('    advisory, read from the diff, QUOTING the change: '
                        '"test file deleted: tests/a.py"')
    assert len(block) == 20 and block[-1].endswith('assertions removed: t18"')


def test_a_verification_that_ran_no_checks_says_so_instead_of_nothing(rig):
    # reviewer.py:66 (`or 'no checks'`): with the fallback gone the line ends in
    # a colon and a space, which a reviewer reads as an empty detail, not as
    # evidence that was never produced
    r = rig()
    s = r.scene()
    r.verification(Ref('task', s['tid']), s['pid'], checks=())
    assert _block(r.prompt(s['mid']), TASK_LINE, 'verification ') == [
        '    verification PASSED by code at %s: no checks' % HEAD12]


def test_a_verification_shows_only_the_start_of_its_revision(rig):
    # reviewer.py:65, the 12-character boundary of the short form
    r = rig()
    s = r.scene()
    r.verification(Ref('task', s['tid']), s['pid'], revision=STALE)
    (line,) = _block(r.prompt(s['mid']), TASK_LINE, 'verification ')
    assert 'at %s:' % STALE12 in line and STALE not in line


@pytest.mark.xfail(strict=True, reason='reviewer.py:65 caps the no-repository label to 12 '
                                       'characters as if it were a revision, so the line '
                                       'reads "at no repositor": a missing repository is '
                                       'shown mangled rather than said in words')
def test_a_verification_with_no_revision_says_there_is_no_repository(rig):
    r = rig()
    s = r.scene()
    r.verification(Ref('task', s['tid']), s['pid'], revision=None)
    (line,) = _block(r.prompt(s['mid']), TASK_LINE, 'verification ')
    assert line.startswith('    verification PASSED by code at no repository: ')


def test_a_task_verification_is_never_shown_under_another_task(rig):
    # reviewer.py:63: the subject is part of the row. Shown under the wrong task
    # it moves a FAILED from one row's evidence to another's clean record
    r = rig()
    s = r.scene()
    t2 = r.task(s['pid'], s['mid'], 't2', title='Second')
    r.verification(Ref('task', s['tid']), s['pid'])
    r.verification(Ref('task', t2), s['pid'], verifier='research', state='FAILED')
    text = r.prompt(s['mid'])
    assert _block(text, TASK_LINE, 'verification ') == [
        '    verification PASSED by code at %s: no checks' % HEAD12]
    assert _block(text, '- t2 Second (VERIFYING): do it well', 'verification ') == [
        '    verification FAILED by research at %s: no checks' % HEAD12]


def test_an_execution_with_no_summary_leaves_no_claim_behind(rig):
    # reviewer.py:68: the agent said nothing about itself. A blank CLAIM line is
    # still a claim, and §14 counts a claim as something the reviewer must discount
    r = rig()
    s = r.scene()
    r.execution(s['tid'], s['mid'], summary='')
    assert _block(r.prompt(s['mid']), TASK_LINE, 'CLAIM') == []


def test_each_claim_is_the_agents_own_with_its_attempt_and_its_cap(rig):
    # reviewer.py:69-70: which attempt spoke is part of the row, and the 500
    # character cap (after the projection) is what keeps one long claim out of the
    # prompt; the silent attempt above stays out
    r = rig()
    s = r.scene()
    r.execution(s['tid'], s['mid'], attempt=1, summary='')
    r.execution(s['tid'], s['mid'], attempt=2, summary='x' * 600)
    assert _block(r.prompt(s['mid']), TASK_LINE, 'CLAIM') == [CLAIM % 2 + 'x' * 500]


def test_a_claim_about_a_live_home_reaches_the_reviewer_projected(rig, tmp_path):
    # reviewer.py:70 (`scrub_text(e.summary, homes)`): the homes the caller was
    # given are the ones used, so a home only that call knows about cannot ride
    # the prompt out of the process; the stored row stays raw
    r = rig()
    s = r.scene()
    home = str(tmp_path / 'Claim-Home-Only')
    r.execution(s['tid'], s['mid'], summary='I read ' + home + '/settings.json twice')
    text = r.prompt(s['mid'], homes=(home,))
    assert home not in text and 'Claim-Home-Only' not in text
    assert _block(text, TASK_LINE, 'CLAIM') == [
        CLAIM % 1 + 'I read its home/settings.json twice']
    with r.db.read() as conn:
        e = rows.where(conn, entities.Execution, task_id=s['tid'])[0].entity
    assert e.summary == 'I read ' + home + '/settings.json twice'


def test_only_mission_checks_at_the_recorded_head_count(rig):
    # reviewer.py:71-72, both filters: a verification of another mission, and one
    # at a revision the branch no longer holds, are not this mission's checks.
    # Without the revision filter the reviewer is shown a pass of a commit that
    # was superseded — the same staleness the `verified` guard refuses
    r = rig()
    s = r.scene()
    other = r.mission(title='Elsewhere', objective='other work')
    r.verification(Ref('mission', s['mid']), s['pid'], criterion=0)
    r.verification(Ref('mission', s['mid']), s['pid'], criterion=1, revision=STALE)
    r.verification(Ref('mission', other), s['pid'], criterion=2)
    r.verification(Ref('task', s['tid']), s['pid'])
    assert _after(r.prompt(s['mid']), 'Mission checks at %s:' % HEAD12) == \
        ['- criterion 0: PASSED']


def test_mission_checks_of_a_mission_with_no_branch_are_still_shown(rig):
    # reviewer.py:71-76: `None == None`, so the rows taken with no repository are
    # the mission's own and stay shown, at the head the mission really has. The
    # row at a revision is the stale one, and a missing criterion line is a
    # criterion nobody checked
    r = rig()
    s = r.scene(integration_head=None)
    r.verification(Ref('mission', s['mid']), s['pid'], criterion=1, revision=None,
                   state='AWAITING_HUMAN')
    r.verification(Ref('mission', s['mid']), s['pid'], criterion=2, revision=HEAD)
    (header,) = [x for x in _lines(r.prompt(s['mid'])) if x.startswith('Mission checks ')]
    assert _after(r.prompt(s['mid']), header) == ['- criterion 1: AWAITING_HUMAN']


@pytest.mark.xfail(strict=True, reason='reviewer.py:74 caps the no-repository label to 12 '
                                       'characters as if it were a revision, so the header '
                                       'of a mission with no branch reads "at no repositor"')
def test_the_mission_check_header_names_the_branch_it_was_taken_at(rig):
    r = rig()
    s = r.scene(integration_head=None)
    r.verification(Ref('mission', s['mid']), s['pid'], criterion=0, revision=None)
    (header,) = [x for x in _lines(r.prompt(s['mid'])) if x.startswith('Mission checks ')]
    assert header == 'Mission checks at no repository:'


def test_a_diff_is_added_deleted_path_and_capped_at_eighty_rows(rig):
    # reviewer.py:77-79: the three columns in that order (a path first would read
    # as a file that changed nothing) and the 80-row boundary that decides what
    # the reviewer is told exists at all
    r = rig()
    s = r.scene()
    diff = [('%d' % (i + 1), '0', 'src/part%02d.py' % i) for i in range(79)]
    diff.append(('999', '1', 'src/part79.py'))
    diff.append(('1', '1', 'the-eighty-first-file.py'))
    text = r.prompt(s['mid'], diff=diff)
    assert 'the-eighty-first-file' not in text
    lines = _after(text, 'Changes on the mission branch (added, deleted, path):')
    assert len(lines) == 80
    assert lines[0] == '- 1 0 src/part00.py' and lines[79] == '- 999 1 src/part79.py'


def test_no_diff_prints_no_changes_section_at_all(rig):
    # reviewer.py:77: the worker passes None when the mission is guarded or has no
    # branch. A heading with nothing under it is a clean branch to a reviewer,
    # which is the opposite of what the worker's own extra line says
    r = rig()
    s = r.scene()
    for diff in (None, ()):
        assert 'Changes on the mission branch' not in r.prompt(s['mid'], diff=diff)
    assert 'Changes on the mission branch' in r.prompt(s['mid'], diff=[('1', '0', 'a.py')])


# ── independence: who did the work, and who may not review it ──

def test_the_work_is_attributed_to_the_account_that_ran_it(rig):
    # reviewer.py:89-92: the execution's own account beats its decision's, the
    # decision's own account is used when the row has none, and an execution with
    # neither names nothing. A wrong account here routes the review onto the very
    # resource that did the work (§14.3)
    r = rig()
    s = r.scene()
    loose = r.decision(account_ref='harness-own-account')
    decided = r.decision(account_ref='routed-by-the-decision')
    r.execution(s['tid'], s['mid'], harness_id='h1', account_id=ACC_A,
                route_decision_id=loose, model='m-large')
    r.execution(s['tid'], s['mid'], attempt=2, harness_id='h2', account_id=None,
                route_decision_id=decided)
    r.execution(s['tid'], s['mid'], attempt=3, harness_id='h3', account_id=None,
                route_decision_id=None, model='m-small')
    assert r.executed(s['mid']) == [('h1', ACC_A, 'm-large'),
                                    ('h2', 'routed-by-the-decision', None),
                                    ('h3', None, 'm-small')]


def test_only_the_plan_in_force_did_work_this_review_is_routed_away_from(rig):
    # reviewer.py:85-87: the tasks come from the plan in force, so a superseded
    # plan's executions neither add their accounts to the forbidden list nor
    # excuse the current one; a plan with no execution forbids nobody
    r = rig()
    mid = r.mission()
    old, new = r.plan(mid, 1, state='SUPERSEDED'), r.plan(mid, 2)
    r.execution(r.task(old, mid, 't9'), mid, harness_id='h1', account_id=ACC_A,
                model='m-large')
    r.execution(r.task(new, mid, 't1'), mid, harness_id='h2', account_id=ACC_B,
                model='m-small')
    assert r.executed(mid) == [('h2', ACC_B, 'm-small')]
    other = r.mission(title='Unstaffed', objective='a plan with no work yet')
    r.plan(other)
    assert r.executed(other) == []


def test_the_forbidden_list_is_sorted_unique_and_never_names_a_none():
    # reviewer.py:98: the router reads one JSON list of accounts. A None, a
    # harness id, a duplicate or an unsorted list changes who is excluded
    assert reviewer.forbidden([]) == {'accounts': []}
    assert reviewer.forbidden([('h', None, 'm'), ('h2', None, None)]) == {'accounts': []}
    got = reviewer.forbidden([('h1', 'acc_b', 'm'), ('h2', 'acc_a', None),
                              ('h1', 'acc_b', 'other'), ('h3', None, 'm')])
    assert got == {'accounts': ['acc_a', 'acc_b']} and isinstance(got['accounts'], list)


def test_an_execution_whose_model_is_unknown_is_the_same_resource():
    # reviewer.py:106-107, the fail-closed side: a model unknown on either side is
    # not "another model", or a review on the account that did the work would be
    # called independent because nobody recorded which model ran it
    ran = [('fake', 'acc_1', 'm-large')]
    assert reviewer.independent(('fake', 'acc_1', 'm-large'), ran) is False
    assert reviewer.independent(('fake', 'acc_1', None), ran) is False
    assert reviewer.independent(('fake', 'acc_1', ''), ran) is False
    assert reviewer.independent(('fake', 'acc_1', 'm-small'), [('fake', 'acc_1', None)]) \
        is False
    assert reviewer.independent(('fake', 'acc_1', 'm-small'), [('fake', 'acc_1', '')]) \
        is False
    assert reviewer.independent(('fake', 'acc_1', 'm-small'), ran) is True


def test_every_execution_of_the_plan_is_compared_not_only_the_first():
    # reviewer.py:105-109: one differently-looking resource must not excuse the
    # whole plan wherever it appears in the list, and nothing executed leaves
    # nothing to be captured by
    assert reviewer.independent(('h', 'a', 'm'), [('other', 'x', 'y'),
                                                  ('h', 'a', 'm')]) is False
    assert reviewer.independent(('h', 'a', 'm'), [('h', 'a', 'm'),
                                                  ('other', 'x', 'y')]) is False
    assert reviewer.independent(('h', 'a', 'm'), []) is True
    assert reviewer.independent(('h', 'a', 'm'), [('h', None, 'm')]) is True
    assert reviewer.independent(('h', None, 'm-large'), [('h', None, 'm-large')]) is False
    assert reviewer.independent(('h', None, 'm-large'), [('h', None, 'm-small')]) is True


def test_the_reviewers_resource_is_its_own_decisions_saying(rig):
    # reviewer.py:112-115: the decision's own account wins over the harness's, and
    # a decision that names neither is no account at all — the None is what makes
    # `independent` compare two unknowns instead of inventing a resource. A
    # decision that does not exist is no resource either, and says so by failing
    r = rig()
    both = r.decision(harness_id='h1', account_id=ACC_A, account_ref='harness-own',
                      model='m-large')
    own = r.decision(harness_id='h1', account_id=None, account_ref='harness-own')
    bare = r.decision(harness_id='h1', account_id=None, account_ref=None)
    assert r.resource_of(both) == {'harness_id': 'h1', 'account': ACC_A, 'model': 'm-large'}
    assert r.resource_of(own) == {'harness_id': 'h1', 'account': 'harness-own',
                                  'model': None}
    assert r.resource_of(bare) == {'harness_id': 'h1', 'account': None, 'model': None}
    with pytest.raises(AttributeError):
        r.resource_of(ids.new_id('route_decision'))
