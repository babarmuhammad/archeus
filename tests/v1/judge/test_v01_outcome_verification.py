"""V01-V03, V05, V11, V14, V15 — the outcome is verified from evidence, never
inferred from a process that exited 0 (p13-design-gate §24).

Each scenario registers a fixture repository as the mission's project, scripts
what the fake agent writes into its worktree (an allowed `Write` tool call is a
real file), and lets the verification worker judge the workspace: Core runs the
commands P4's inspection found and records every check. The agent's own report
is never evidence.
"""

import os
import subprocess

import pytest

from .support import mission_states, wait_for, wait_state

pytestmark = pytest.mark.real_verification

FIX = 'def add(a, b):\n    return a + b\n'
WRONG = 'def add(a, b):\n    return a * b\n'


def _write(content, path='calc.py'):
    return {'emit': {'type': 'tool', 'name': 'Write',
                     'input': {'file_path': path, 'content': content}}}


def _mission(client, rig, repo, steps, objective='Make add add'):
    rig.script_harness('t1', steps)
    return client.create_mission(title='Fix add', objective=objective,
                                 project_id=repo.project_id)


def _task_verifications(client, mid):
    return [v for v in client.verifications(mid) if v['subject']['kind'] == 'task']


def _git(path, *args):
    return subprocess.run(['git', *args], cwd=path, capture_output=True, text=True,
                          check=True).stdout.strip()


def test_V02_V15_a_right_change_is_verified_merged_and_reviewed(client, rig):
    repo = rig.fixture_repo('verify-python')
    m = _mission(client, rig, repo, [_write(FIX), {'emit': {'type': 'result', 'summary': 'done'}}])
    done = wait_state(client, m['id'], 'COMPLETED', timeout=120)
    (v,) = _task_verifications(client, m['id'])
    assert v['state'] == 'PASSED' and v['verifier'] == 'code'
    names = {c['name']: c for c in v['checks']}
    assert names['changes']['result'] == 'pass'
    assert names['test: python -m pytest']['result'] == 'pass'
    assert names['test: python -m pytest']['exit_code'] == 0
    assert all(c['result'] == 'satisfied' for c in v['criteria'])
    # V15: the mission branch holds exactly the verified commit
    assert done['integration_head']
    branch = _git(repo.path, 'rev-parse', 'archeus/%s' % m['id'])
    assert branch == done['integration_head']
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', v['revision'], branch],
                          cwd=repo.path).returncode == 0
    assert _git(repo.path, 'show', '%s:calc.py' % branch).replace('\r\n', '\n') == FIX.strip()
    # the mission's criteria were verified on that branch, then reviewed
    crit = [x for x in client.verifications(m['id']) if x['subject']['kind'] == 'mission']
    assert crit and all(x['state'] == 'PASSED' and x['revision'] == branch for x in crit)
    seen = mission_states(client, m['id'])
    assert seen.index('VERIFYING') < seen.index('REVIEWING') < seen.index('COMPLETED')
    (r,) = client.reviews(m['id'])
    assert r['state'] == 'ACCEPTED' and r['independent'] is True
    # the provenance of what was verified is the execution's, not the agent's
    assert v['performed_by']['harness_id'] == 'fake' and v['execution_id']


def test_V01_V14_exit_0_with_a_wrong_change_is_a_verification_failure(client, rig):
    repo = rig.fixture_repo('verify-python')
    m = _mission(client, rig, repo, [_write(WRONG),
                                     {'emit': {'type': 'result', 'summary': 'done, fixed'}}])
    wait_for(lambda: 'REPLANNING' in mission_states(client, m['id']), timeout=120)
    vs = _task_verifications(client, m['id'])
    assert vs and all(v['state'] == 'FAILED' for v in vs)
    tests = [c for c in vs[0]['checks'] if c['name'] == 'test: python -m pytest']
    assert tests[0]['result'] == 'fail' and tests[0]['exit_code'] != 0
    assert tests[0]['output_sha256']            # the output is kept as evidence
    # the execution ended OK — its process exited 0 — and that proved nothing
    assert 'SUCCEEDED' not in [e['payload']['to'] for e in client.events(0)
                               if e['type'] == 'task.state_changed']


def test_V11_passing_tests_and_no_change_is_contradictory_and_fails(client, rig):
    """The tests the repository already had pass; the task changed nothing. Two
    authoritative checks disagree: the failure is recorded beside the pass."""
    repo = rig.fixture_repo('verify-python')
    repo.commit('already fixed', {'calc.py': FIX})
    rig.assessed(repo)
    m = _mission(client, rig, repo, [{'emit': {'type': 'result', 'summary': 'all done'}}])
    wait_for(lambda: [v for v in _task_verifications(client, m['id'])
                      if v['state'] in ('PASSED', 'FAILED')])
    v = _task_verifications(client, m['id'])[0]
    by = {c['name']: c['result'] for c in v['checks']}
    assert by == {'changes': 'fail', 'test: python -m pytest': 'pass'}
    assert v['state'] == 'FAILED'


def test_V03_nothing_to_run_waits_for_your_acceptance(client, rig):
    repo = rig.fixture_repo('verify-notests')
    m = _mission(client, rig, repo, [_write('notes, revised\n', 'notes.txt'),
                                     {'emit': {'type': 'result', 'summary': 'done'}}],
                 objective='Revise the notes')
    wait_state(client, m['id'], 'BLOCKED', timeout=120)
    (v,) = _task_verifications(client, m['id'])
    assert v['state'] == 'AWAITING_HUMAN' and v['verifier'] == 'generic_human'
    assert all(c['result'] == 'unknown' for c in v['criteria'])
    assert client.get_mission(m['id'])['state'] == 'BLOCKED'
    out = client.decide_verification(v['id'], 'accept', note='looks right')
    assert out['state'] == 'PASSED' and out['resumed'] is True
    # the mission's own criteria have nothing to run either: you decide them too
    def crit_waiting():
        return [x for x in client.verifications(m['id'])
                if x['subject']['kind'] == 'mission' and x['state'] == 'AWAITING_HUMAN']
    for x in wait_for(crit_waiting):
        client.decide_verification(x['id'], 'accept')
    wait_state(client, m['id'], 'COMPLETED', timeout=120)
    decided = [x for x in client.verifications(m['id']) if x['id'] == v['id']][0]
    assert decided['decided_by'] and decided['note'] == 'looks right'
    # a decided verification cannot be decided again
    with pytest.raises(Exception) as err:
        client.decide_verification(v['id'], 'reject')
    assert getattr(err.value, 'status', None) == 409


def test_V05_a_failing_criterion_among_passing_ones_replans(client, rig):
    """Two mission criteria read one battery on the merged branch; a task's
    automatic check passing does not satisfy a human criterion of the task."""
    repo = rig.fixture_repo('verify-python')
    m = client.create_mission(title='Fix add', objective='Make add add', project_id=repo.project_id,
                              success_criteria=[{'text': 'tests pass', 'check': 'automatic'},
                                                {'text': 'you like it', 'check': 'human'}])
    rig.script_harness('t1', [_write(FIX), {'emit': {'type': 'result', 'summary': 'done'}}])
    wait_state(client, m['id'], 'BLOCKED', timeout=120)       # the human criterion is open

    def decided():                  # the battery may still run while you are asked
        crit = {x['criterion']: x for x in client.verifications(m['id'])
                if x['subject']['kind'] == 'mission'}
        return crit if crit.get(0, {}).get('state') in ('PASSED', 'FAILED') else None
    crit = wait_for(decided)
    assert crit[0]['state'] == 'PASSED'                # automatic: the battery passed
    human = [x for x in crit.values() if x['state'] == 'AWAITING_HUMAN']
    assert human, crit
    client.decide_verification(human[0]['id'], 'reject', note='not what I wanted')
    wait_for(lambda: 'REPLANNING' in mission_states(client, m['id']), timeout=120)
