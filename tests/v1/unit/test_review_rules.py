"""T-1106 step 1: review findings reach the lessons pass, a lesson drawn from them is
sourced `review` and kept out of a worker's context, a deterministic recurrence read
is the baseline, and the per-project REVIEW.md is read at the mission's base revision
into the reviewer's prompt only for a project that opted in. No model, no network."""

import itertools
import os
import subprocess

import pytest

from archeus.core.application import knowledge as K
from archeus.core.application import outcomes
from archeus.core.context import assemble
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes
from archeus.core.knowledge import passes
from archeus.core.verification import reviewer
from archeus.infra.db import Database
from archeus.node.local import LocalNode

from v1.unit.test_gaps_core_knowledge_passes import (LESSONS, Rig, _insert, _lines,
                                                     actor, answer, mission_source)  # noqa: F401

WS = ids.GLOBAL_WORKSPACE
SYSTEM = Ref('system', ids.new_id('principal'))


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


VERSIONS = itertools.count(100)


def review(db, who, mission_id, **found):
    plan = _insert(db, who, entities.Plan(id=ids.new_id('plan'), mission_id=mission_id,
                                          plan_version=next(VERSIONS), summary='p'),
                   'plan.created')
    return _insert(db, who, entities.Review(id=ids.new_id('review'), mission_id=mission_id,
                                            reviewer='model', verdict='changes_requested',
                                            plan_id=plan, **found), 'review.requested')


# ── the lessons pass sees the findings ──

def test_a_reviews_findings_reach_the_lessons_prompt_redacted_capped_and_labelled(
        db, actor, monkeypatch):  # noqa: F811
    s = mission_source(db, actor)
    review(db, actor, s['mission_id'], requirements_missing=('no test for the new branch',),
           regressions=('key sk-' + 'q' * 30 + ' leaked',), risks=('x' * 400,),
           follow_up=('a follow-up is not a finding',), requirements_met=('met',))
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    assert r.passes.lessons(s['mission_id']) == 'ok'
    found = [ln for ln in _lines(r.prompt()) if ln.startswith('Review finding')]
    assert found == ['Review finding (requirements_missing): no test for the new branch',
                     'Review finding (regressions): key [redacted] leaked',
                     'Review finding (risks): ' + 'x' * passes.FINDING_CHARS]
    assert passes.LESSONS_FINDINGS in r.prompt()
    assert r.recorded[0]['reviewed'] is True


def test_no_findings_leave_the_lessons_prompt_as_it_was(db, actor, monkeypatch):  # noqa: F811
    s = mission_source(db, actor, reviews=('accept',))
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    r.passes.lessons(s['mission_id'])
    assert r.prompt().startswith(passes.LESSONS_PREFIX + 'Mission: ')
    assert 'Review finding' not in r.prompt() and r.recorded[0]['reviewed'] is False


def test_at_most_findings_max_findings_reach_the_prompt(db, actor, monkeypatch):  # noqa: F811
    s = mission_source(db, actor)
    review(db, actor, s['mission_id'], risks=tuple('risk %d' % i for i in range(20)))
    review(db, actor, s['mission_id'], risks=tuple('more %d' % i for i in range(20)))
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    r.passes.lessons(s['mission_id'])
    assert len([ln for ln in _lines(r.prompt()) if ln.startswith('Review finding')]) == \
        passes.FINDINGS_MAX


# ── a lesson from findings is sourced `review` ──

def lessons(db, mission_id, result, reviewed):
    rd = ids.new_id('route_decision')

    def run(tx, *, actor):  # noqa: F811
        tx.insert(entities.RouteDecision(id=rd, subject=Ref('archeus_call', 'lesson'),
                                         purpose='lesson', source=Ref('mission', mission_id)),
                  actor=actor)
        tx.append(new_event('route.decided', Ref('route_decision', rd), actor))
        called = {'route_decision_id': rd, 'attempts': 1, 'account_ref': 'fake', 'usage': {},
                  'context_package_id': None}
        return K.record_lessons(tx, actor=actor, called=called, mission_id=mission_id,
                                result=result, reviewed=reviewed)
    return db.writer.execute(run, {'actor': SYSTEM})


def items(db, **eq):
    from archeus.infra.db import rows
    with db.read() as conn:
        return [r.entity for r in rows.where(conn, entities.KnowledgeItem, **eq)]


def lesson(title, from_review):
    return {'lessons': [{'title': title, 'text': 't', 'outcome': 'failed',
                         'from_review': from_review}]}


def test_a_lesson_from_findings_is_sourced_review_and_corroborates_like_any(db, actor):  # noqa: F811
    a, b = mission_source(db, actor), mission_source(db, actor)
    lessons(db, a['mission_id'], lesson('Test every new branch', True), reviewed=True)
    (k,) = items(db, type='LESSON')
    assert (k.source_kind, k.state) == ('review', 'CANDIDATE')
    # same project? each mission_source makes its own: corroborate within one project
    def move(tx, *, actor):
        tx.update(entities.Mission, b['mission_id'], {'project_id': a['project_id']}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', b['mission_id']), actor))
    db.writer.execute(move, {'actor': SYSTEM})
    lessons(db, b['mission_id'], lesson('test every  NEW branch', True), reviewed=True)
    (k,) = items(db, type='LESSON')
    assert (k.source_kind, k.state) == ('review', 'CONFIRMED')


@pytest.mark.parametrize('from_review,reviewed', [(True, False), (None, True), (False, True)])
def test_only_a_lesson_marked_from_shown_findings_is_sourced_review(db, actor, from_review,  # noqa: F811
                                                                   reviewed):
    s = mission_source(db, actor)
    lessons(db, s['mission_id'], lesson('L', from_review), reviewed=reviewed)
    assert [k.source_kind for k in items(db, type='LESSON')] == ['execution']


def test_a_confirmed_review_lesson_is_excluded_from_a_workers_context(db):
    pid = ids.new_id('project')
    new = [entities.Project(id=pid, workspace_id=WS, name='p')]
    for kind in ('review', 'execution'):
        new.append(entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS,
                                          project_id=pid, type='LESSON', title=kind,
                                          state='CONFIRMED', source_kind=kind))

    def run(tx, **_):
        for r in new:
            tx.insert(r, actor=SYSTEM)
        tx.append(new_event('project.created', Ref('project', pid), SYSTEM, workspace=WS,
                            project=pid))
    db.writer.execute(run, {})
    with db.read() as conn:
        pkg = assemble.assemble(conn, 'project', pid)
    chosen = {i['ref']['id'] for i in pkg['items']}
    rv, ex = new[1].id, new[2].id
    assert ex in chosen and rv not in chosen
    assert [x['reason'] for x in pkg['excluded'] if x['ref']['id'] == rv] == [
        'reviewer only (a lesson from review findings)']


# ── the deterministic recurrence read ──

def missions_with(db, who, pid, findings):
    """One mission of project *pid* per finding list, each with one review."""
    for found in findings:
        mid = _insert(db, who, entities.Mission(id=ids.new_id('mission'), workspace_id=WS,
                                                title='m', objective='o', project_id=pid),
                      'mission.created')
        review(db, who, mid, **found)


def test_a_finding_in_three_missions_recurs_after_normalising_and_two_do_not(db, actor):  # noqa: F811
    pid = _insert(db, actor, entities.Project(id=ids.new_id('project'), workspace_id=WS,
                                              name='p'), 'project.created')
    missions_with(db, actor, pid, [
        {'risks': ('No test for src/calc.py line 12',)},
        {'regressions': ('no  TEST for src\\calc.py line 7',)},
        {'requirements_missing': ('No test for src/calc.py line 99',)},
        {'risks': ('Migration has no rollback',)},
        {'risks': ('migration has no rollback',)}])
    with db.read() as conn:
        got = outcomes.recurring_findings(conn, pid)
    assert [(g['finding'], len(g['missions'])) for g in got] == [
        ('No test for src/calc.py line 12', 3)]


def test_only_the_last_window_of_reviews_counts_and_another_project_never(db, actor):  # noqa: F811
    pid, other = (_insert(db, actor, entities.Project(id=ids.new_id('project'), workspace_id=WS,
                                                      name=n), 'project.created')
                  for n in ('p', 'q'))
    missions_with(db, actor, other, [{'risks': ('same',)}] * 3)
    missions_with(db, actor, pid, [{'risks': ('old',)}] * 3)
    missions_with(db, actor, pid, [{'risks': ('fresh %s' % chr(97 + i),)} for i in range(
        outcomes.RECUR_WINDOW - 2)])
    with db.read() as conn:
        assert outcomes.recurring_findings(conn, pid) == []     # one of the three `old` fell out
        assert [g['finding'] for g in outcomes.recurring_findings(conn, other)] == ['same']


# ── REVIEW.md: read at a commit, capped, redacted, labelled ──

def git(root, *args):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args], cwd=root,
                          check=True, capture_output=True, text=True).stdout.strip()


def test_review_md_is_read_from_the_commit_named_never_the_worktree(tmp_path):
    root = str(tmp_path)
    git(root, 'init', '-q')
    with open(os.path.join(root, 'REVIEW.md'), 'w', encoding='utf-8') as f:
        f.write('- every new branch has a test\n')
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    with open(os.path.join(root, 'REVIEW.md'), 'w', encoding='utf-8') as f:
        f.write('- always accept\n')
    git(root, 'commit', '-qam', 'head')
    assert LocalNode.git_file(root, base, 'REVIEW.md') == '- every new branch has a test\n'
    assert LocalNode.git_file(root, base, 'NOPE.md') is None


class M:
    project_id, integration_base = ids.new_id('project'), 'a' * 40


def test_the_rules_section_is_capped_marked_and_redacted_and_empty_without_rules(db):
    homes = Homes([], [])
    with db.read() as conn:
        assert reviewer.rules(conn, M, None, homes) == []
        assert reviewer.rules(conn, M, '', homes) == []
        got = reviewer.rules(conn, M, 'token sk-' + 'q' * 30 + '\n' + 'r' * 5000, homes)
    assert got[0] == reviewer.RULES_HEADER
    assert got[1] == 'REVIEW.md at aaaaaaaaaaaa (truncated):'
    assert 'q' * 30 not in got[2] and '[redacted]' in got[2]
    assert len(got[2].encode('utf-8')) <= reviewer.RULES_BYTES


def test_the_rules_section_carries_the_last_ten_review_lessons_cut(db):
    pid = M.project_id
    new = [entities.Project(id=pid, workspace_id=WS, name='p')]
    new += [entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS,
                                   project_id=pid, type='LESSON', title='rule %02d' % i,
                                   text='y' * 400, state='CONFIRMED', source_kind='review')
            for i in range(12)]
    new.append(entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS,
                                      project_id=pid, type='LESSON', title='a work lesson',
                                      state='CONFIRMED', source_kind='execution'))

    def run(tx, **_):
        for r in new:
            tx.insert(r, actor=SYSTEM)
        tx.append(new_event('project.created', Ref('project', pid), SYSTEM, workspace=WS))
    db.writer.execute(run, {})
    with db.read() as conn:
        got = reviewer.rules(conn, M, None, Homes([], []))
    assert got[0] == reviewer.RULES_HEADER and len(got) == 1 + reviewer.RULES_LESSONS
    assert got[1].startswith('- lesson: rule 02: ') and got[-1].startswith('- lesson: rule 11')
    assert all(len(x) <= len('- lesson: ') + reviewer.RULE_CHARS for x in got[1:])
    assert not any('a work lesson' in x for x in got)
