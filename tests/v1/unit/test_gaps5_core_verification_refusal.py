import json

import pytest

from archeus.core.application import optins, verification as V
from archeus.core.domain import ids
from archeus.core.domain.values import Ref
from archeus.core.verification import evidence
from claude_sessions import proc

from . import test_gaps_core_verification_worker as W
from .test_gaps_core_verification_worker import BASE, REV, REV2, _Node, _result, _script

rig = W.rig

TEST1 = 'tool --check'
NAME1 = 'test: tool --check'
MOVED = 'the workspace moved during verification (%s -> %s)'
REFUSED = 'the workspace could not be checked after verification: %s refused or unavailable'


@pytest.fixture(autouse=True)
def _tool_found_on_path(tmp_path, monkeypatch):
    real = proc.which
    found = str(tmp_path / 'bin' / 'tool')

    def which(name, path=None, avoid=()):
        return found if name == 'tool' else real(name, path=path, avoid=avoid)
    monkeypatch.setattr(proc, 'which', which)


def _node(head_first=REV, head_final=REV, dirty_final=False, dirty_answers=None,
          run_exit=0, **over):
    fake = {'git_head': _script(head_first, head_final),
            'git_dirty': _script(*dirty_answers) if dirty_answers else _script(dirty_final),
            'branch_exists': _script(False),
            'git_merge_base': _script(BASE),
            'run_check': _script(_result(exit_code=run_exit))}
    fake.update(over)
    return _Node(**fake)


def _go(rig, node, *, kind='inspection', **over):
    r = rig(workdir='ws', kind=kind, node=node, tests=(TEST1,), **over)
    seen = r.spy()
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    return r, seen


def _names(seen):
    return [n for n, _k in seen]


def _workspace(v):
    got = [c for c in v.checks if c['name'] == 'workspace']
    assert len(got) == 1, 'workspace checks: %r' % ([c['name'] for c in v.checks],)
    return got[0]


def _fail_only_row_is(r, v, detail):
    assert v.state == 'ERROR' and v.errors == 1
    assert v.error == detail
    assert r.task().state == 'VERIFYING' and r.missions.fired == []


def test_both_final_git_reads_refused_name_head_and_git_status_and_record_once(rig):
    r, seen = _go(rig, _node(head_final=None, dirty_final=None))
    v = r.one()
    check = _workspace(v)
    assert check['kind'] == 'git' and check['result'] == 'error'
    assert check['detail'] == REFUSED % 'HEAD and git status'
    assert 'moved' not in check['detail']
    assert _names(seen) == ['start', 'record']
    _fail_only_row_is(r, v, REFUSED % 'HEAD and git status')


def test_a_refused_status_under_a_stable_head_names_git_status_and_never_head(rig):
    r, seen = _go(rig, _node(dirty_final=None))
    v = r.one()
    check = _workspace(v)
    assert check['detail'] == REFUSED % 'git status'
    assert 'HEAD' not in check['detail'] and 'moved' not in check['detail']
    assert [c['name'] for c in v.checks] == [NAME1, 'workspace']
    assert v.checks[0]['result'] == 'pass'
    assert _names(seen) == ['start', 'record']
    _fail_only_row_is(r, v, REFUSED % 'git status')


def test_a_tracked_change_seen_while_head_refused_is_recorded_as_moved(rig):
    r, seen = _go(rig, _node(head_final=None, dirty_final=True))
    v = r.one()
    check = _workspace(v)
    assert check['detail'] == MOVED % (REV[:12], '')
    assert 'refused' not in check['detail'] and 'unavailable' not in check['detail']
    assert _names(seen) == ['start', 'record']
    _fail_only_row_is(r, v, MOVED % (REV[:12], ''))


def test_a_dirty_tree_at_a_stable_head_is_moved_wording_never_the_refusal_one(rig):
    seen = {'dirty': []}

    def git_dirty(ws, **kw):
        seen['dirty'].append((ws, dict(kw)))
        return True
    node = _node(dirty_final=False)
    node.fake['git_dirty'] = git_dirty
    r, spied = _go(rig, node)
    v = r.one()
    check = _workspace(v)
    assert check['detail'] == MOVED % (REV[:12], REV[:12])
    assert 'refused' not in check['detail'] and 'unavailable' not in check['detail']
    assert seen['dirty'] == [('ws', {'tracked_only': True})]
    assert _names(spied) == ['start', 'record']
    _fail_only_row_is(r, v, MOVED % (REV[:12], REV[:12]))


def test_no_weakening_finding_omits_the_advisory_and_the_refusal_still_reaches_record(rig):
    node = _node(dirty_answers=(False, None),
                 git_numstat=_script([('1', '0', 'a.py')]), git_diff=_script(''))
    r, seen = _go(rig, node, kind='code_change', branch='task')
    v = r.one()
    assert [c['name'] for c in v.checks] == ['changes', NAME1, 'workspace']
    assert evidence.WEAKENING not in [c['name'] for c in v.checks]
    assert v.checks[0]['result'] == 'pass' and v.checks[1]['result'] == 'pass'
    assert _workspace(v)['detail'] == REFUSED % 'git status'
    assert v.state == 'ERROR' and v.error == REFUSED % 'git status'
    assert r.task().state == 'VERIFYING' and r.missions.fired == []
    assert _names(seen) == ['start', 'record']


def test_the_workspace_error_lands_after_the_augmented_checks_with_baselines_intact(rig):
    rec = {'made': [], 'dropped': [], 'runs': []}

    def run_check(ws, argv, **kw):
        rec['runs'].append((ws, list(argv), kw.get('out_path')))
        return _result(exit_code=1 if ws == 'ws' else 0)

    def base_checkout(root, path, rev):
        rec['made'].append((root, path, rev))
        return path

    def drop_checkout(root, path):
        rec['dropped'].append(path)
        return True
    node = _node(head_final=REV2, run_check=run_check, base_checkout=base_checkout,
                 drop_checkout=drop_checkout)
    r = rig(workdir='ws', branch='task', kind='inspection', node=node, tests=(TEST1,))
    r.db.writer.execute(optins.set_opt_in, dict(
        actor=Ref('user_device', ids.new_id('principal')), owner_id=r.proj,
        kind='verify', name='baseline', opted_in=True))
    seen = r.spy()
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    assert [c['name'] for c in v.checks] == [NAME1, 'workspace']
    aug = v.checks[0]
    assert aug['result'] == 'fail' and 'regressed' in aug['detail']
    assert aug['baseline']['revision'] == BASE
    assert aug['baseline']['result'] == 'pass' and aug['baseline']['label'] == 'regressed'
    assert _workspace(v)['detail'] == MOVED % (REV[:12], REV2[:12])
    assert v.state == 'FAILED' and _names(seen) == ['start', 'record']
    tree = rec['made'][0][1]
    assert rec['dropped'] == [tree]
    assert [ws for ws, _argv, _out in rec['runs']] == ['ws', tree]


def test_the_head_is_read_only_after_the_last_command_check_has_finished(rig):
    node = _node()
    r, seen = _go(rig, node)
    last_run = max(i for i, c in enumerate(node.calls) if c == 'run_check')
    last_head = max(i for i, c in enumerate(node.calls) if c == 'git_head')
    assert node.calls[0] == 'git_head' and last_head > last_run
    assert node.calls[-1] == 'git_dirty'
    assert _names(seen) == ['start', 'record']
    v = r.one()
    assert v.state == 'PASSED' and [c['name'] for c in v.checks] == [NAME1]


def test_the_movement_detail_bounds_both_revisions_to_twelve_characters(rig):
    assert len(REV) == 40 and len(REV2) == 40
    r, _seen = _go(rig, _node(head_final=REV2))
    v = r.one()
    check = _workspace(v)
    assert check['detail'] == MOVED % (REV[:12], REV2[:12])
    assert REV[12:] not in check['detail'] and REV2[12:] not in check['detail']
    assert REV not in check['detail'] and REV2 not in check['detail']
    assert all(REV[12:] not in json.dumps(c.get('detail', '')) for c in v.checks)
    assert all(REV2[12:] not in json.dumps(c.get('detail', '')) for c in v.checks)


def test_a_command_runner_that_dies_is_never_partially_recorded_and_raises_untouched(
        rig, monkeypatch):
    def run_commands(node, workspace, cmds, *, verification_id, timeout_s,
                     verifier_version):
        raise RuntimeError('the runner died mid-battery')
    monkeypatch.setattr(evidence, 'run_commands', run_commands)
    node = _node()
    r = rig(workdir='ws', kind='inspection', node=node, tests=(TEST1,))
    seen = r.spy()
    with pytest.raises(RuntimeError, match='mid-battery'):
        r.worker.pass_once()
    assert _names(seen) == ['start']
    v = r.one()
    assert v.state == 'RUNNING' and not v.checks
    assert r.task().state == 'VERIFYING' and r.missions.fired == []
    assert node.calls.count('git_head') == 1 and 'git_dirty' not in node.calls


def test_a_refused_record_of_a_refused_workspace_happens_once_and_keeps_its_checks(
        rig, monkeypatch):
    def run_commands(node, workspace, cmds, *, verification_id, timeout_s,
                     verifier_version):
        assert workspace == 'ws' and cmds == [('test', TEST1)]
        assert verification_id == vid and timeout_s == 7 and verifier_version == 'v1'
        return [{'name': NAME1, 'kind': 'command', 'result': 'pass', 'detail': 'exit 0'}]
    monkeypatch.setattr(evidence, 'run_commands', run_commands)
    node = _node(head_first=None, head_final=None, dirty_final=None)
    r = rig(workdir='ws', kind='inspection', node=node, tests=(TEST1,))
    vid = r.vrow(state='RUNNING', revision=None)
    calls = []
    real = r.worker._do

    def do(command, **kw):
        if command is V.record:
            calls.append(kw)
            raise RuntimeError('the record was refused')
        return real(command, **kw)
    r.worker._do = do
    m, t = r.mission(), r.task()
    with pytest.raises(RuntimeError, match='record was refused'):
        r.worker._run_and_record(vid, m, t, 'root', 'ws', None, None,
                                 [('test', TEST1)], 'v1')
    assert len(calls) == 1
    checks = calls[0]['checks']
    assert [c['name'] for c in checks] == [NAME1, 'workspace']
    assert checks[-1]['result'] == 'error'
    assert checks[-1]['detail'] == REFUSED % 'HEAD and git status'
    assert r.verification(vid).state == 'RUNNING'
