"""`memory`: an advisory check on a mission's verification. `pass` when a knowledge row cites the
mission, `skip` when none does yet, never `fail`; it is only recorded when the mission's branch
changed files, and it never moves a verdict."""

import pytest

from archeus.core.application import verification as V
from archeus.core.domain import entities, ids
from archeus.core.verification import evidence, reviewer

from .test_gaps_core_verification_worker import (
    AUTO, BASE, REV, _Node, _result, _script, _tool_on_path, rig)  # noqa: F401


def lesson(r, mid=None):
    r._place(entities.Relation(id=ids.new_id('relation'), src_kind='knowledge_item',
                               src_id=ids.new_id('knowledge_item'), rel='learned_from',
                               dst_kind='mission', dst_id=mid or r.mid))


def node(stat, **fake):
    return _Node(git_head=_script(REV), run_check=_script(fake.pop('run', _result())),
                 git_numstat=_script(stat), **fake)


def memory(r):
    return [c for v in r.rows('mission') for c in v.checks if c['name'] == 'memory']


def test_a_mission_that_changed_files_and_cites_a_lesson_passes_the_memory_check(rig):  # noqa: F811
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, task_state='SUCCEEDED',
            success=(AUTO,), node=node([(1, 0, 'a.py')]))
    lesson(r)
    assert r.worker._verify_mission(r.mid) is True
    (c,) = memory(r)
    assert (c['kind'], c['result']) == ('state', 'pass')
    assert '1 knowledge relation' in c['detail']


def test_without_a_row_it_is_a_skip_with_a_detail_and_the_verdict_stays_passed(rig):  # noqa: F811
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, task_state='SUCCEEDED',
            success=(AUTO,), node=node([(1, 0, 'a.py')]))
    lesson(r, ids.new_id('mission'))
    r.worker._verify_mission(r.mid)
    (c,) = memory(r)
    assert c['result'] == 'skip' and 'no knowledge' in c['detail']
    assert [v.state for v in r.rows('mission')] == ['PASSED']


def test_a_failing_command_still_fails_and_the_memory_check_does_not_change_why(rig):  # noqa: F811
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, task_state='SUCCEEDED',
            success=(AUTO,), node=node([(1, 0, 'a.py')], run=_result(exit_code=1)))
    r.worker._verify_mission(r.mid)
    assert [v.state for v in r.rows('mission')] == ['FAILED']
    assert memory(r)[0]['result'] == 'skip'


def test_no_changed_files_or_no_branch_records_no_memory_check(rig):  # noqa: F811
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, task_state='SUCCEEDED',
            success=(AUTO,), node=node([]))
    r.worker._verify_mission(r.mid)
    assert memory(r) == []


def test_a_mission_with_no_integration_branch_never_asks_git_for_a_diff(rig):  # noqa: F811
    n = _Node(git_head=_script(REV), run_check=_script(_result()))
    r = rig(mission_state='VERIFYING', task_state='SUCCEEDED', success=(AUTO,), node=n)
    r.worker._verify_mission(r.mid)
    assert memory(r) == [] and 'git_numstat' not in n.calls


@pytest.mark.parametrize('result', ['pass', 'skip'])
def test_a_memory_check_never_flips_the_verdict(result):
    command = {'name': 'test', 'kind': 'command', 'result': 'pass'}
    assert V.verdict_of([command, {'name': 'memory', 'kind': 'state', 'result': result}]) == 'PASSED'


def test_the_review_prompt_says_the_memory_check_is_advisory(rig):  # noqa: F811
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, task_state='SUCCEEDED',
            success=(AUTO,), node=node([(1, 0, 'a.py')]))
    r.worker._verify_mission(r.mid)
    with r.db.read() as conn:
        text = reviewer.prompt(conn, r.mission(), None, {})
    assert 'Memory (advisory, not part of the verdict): skip, no knowledge' in text


def test_memory_check_is_a_read_of_relations_to_the_mission(rig):  # noqa: F811
    r = rig()
    with r.db.read() as conn:
        assert evidence.memory_check(conn, r.mid)['result'] == 'skip'
    lesson(r)
    lesson(r)
    with r.db.read() as conn:
        c = evidence.memory_check(conn, r.mid)
    assert c['result'] == 'pass' and c['detail'].startswith('2 ')


def test_a_retried_mission_verification_records_the_memory_check_too(rig):  # noqa: F811
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, task_state='SUCCEEDED',
            success=(AUTO,), node=node([(1, 0, 'a.py')]))
    vid = r.vrow(subject='mission', criterion=0, state='ERROR', errors=1,
                 holds_mission=False, revision=REV, workspace='wt')
    assert r.worker._retry(vid) is True
    assert [c['result'] for c in r.verification(vid).checks if c['name'] == 'memory'] == ['skip']


def test_only_a_live_lesson_learned_from_the_mission_counts(rig):  # noqa: F811
    r = rig()
    for extra in ({'rel': 'relates_to'}, {'valid_until': '2026-01-01T00:00:00Z'},
                  {'src_kind': 'meeting'}):
        r._place(entities.Relation(**dict(
            id=ids.new_id('relation'), src_kind='knowledge_item',
            src_id=ids.new_id('knowledge_item'), rel='learned_from', dst_kind='mission',
            dst_id=r.mid) | extra))
    with r.db.read() as conn:
        assert evidence.memory_check(conn, r.mid)['result'] == 'skip'
