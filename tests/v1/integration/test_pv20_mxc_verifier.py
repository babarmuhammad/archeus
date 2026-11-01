# ruff: noqa: F811  (the imported fixtures are taken as arguments)
"""PV20 B11: a confined verifier check over the production `MxcBoundary`, over fakes.

The path is `LocalNode.run_confined_check` -> `Isolation.run_confined` ->
`MxcBoundary.launch_confined` -> `MxcLaunch` -> `mxc_verifier.ConfinedChild`. What stands
in for Windows is the scripted launcher of `test_mxc_boundary`; the fixtures are the
agent-path file's (`checks`, `no_process`), so nothing starts a process.
"""

import json
import os
import time

import pytest

from archeus.core.domain import ids
from archeus.core.verification import evidence
from archeus.infra.paths import VerifyPaths
from archeus.node import isolation as iso
from archeus.node import local, mxc_ledger, mxc_verifier

from v1.integration.test_pv20_mxc_agent_path import (SEED, Traced, checks,  # noqa: F401
                                                     no_process)
from v1.unit.test_mxc_boundary import gate, make, outcome, script, sdk  # noqa: F401
from v1.unit.test_pv20_isolation import os_tripwire  # noqa: F401


def run_one(checks, attempt=0, **kw):
    vid = ids.new_id('verification')
    return vid, checks.run(vid, attempt, **kw)


def journals(checks):
    return checks.boundary.ledger.journals()


def test_the_checks_output_is_drained_into_its_own_log_and_the_exit_is_the_workloads(checks):
    checks.api.outcomes = script([outcome(agent_outcome=4, stdout=b'ran 3 tests\n',
                                          stderr=b'one failed\n')])
    vid, result = run_one(checks)
    assert result['exit_code'] == 4 and result['error'] is None
    assert result['output'] == b'ran 3 tests\none failed\n' == open(
        VerifyPaths(vid, 0).out, 'rb').read()
    assert result['output_bytes'] == 23 and result['truncated'] is False


def test_only_the_tail_the_caller_keeps_is_returned_and_the_log_holds_it_all(checks):
    checks.api.outcomes = script([outcome(stdout=b'x' * 100 + b'tail')])
    vid = ids.new_id('verification')
    result = checks.node.run_confined_check(
        vid, 0, ['runner'], toolchain=[checks.tool], timeout=30, record=checks.recorded.append,
        project_id='proj', revision=SEED, workdirs=[], keep=4)
    assert result['output'] == b'tail' and result['truncated'] is True
    assert result['output_bytes'] == 104


def test_the_log_sits_outside_every_grant_so_only_core_writes_it(checks):
    vid, _ = run_one(checks)
    fs = checks.boundary.launches[0].policy.raw['filesystem']
    granted = fs['readwritePaths'] + fs['readonlyPaths']
    log = VerifyPaths(vid, 0).out
    assert not [g for g in granted if iso._within(log, g)]


def test_the_transport_is_bounded_by_the_cap_the_log_is_held_to(checks):
    run_one(checks)
    transport = checks.boundary.launches[0].backend.transport
    assert transport.output_limit == transport.total_limit == iso.CONFINED_OUT_MAX


def test_the_deadline_is_this_checks_not_the_boundarys(checks):
    assert checks.boundary.timeout_ms == 5000
    run_one(checks, timeout=42)
    assert checks.boundary.launches[0].policy.raw['process']['timeout'] == 42000


def test_output_past_the_cap_is_an_error_result_and_never_a_verdict(checks, monkeypatch):
    monkeypatch.setattr(iso, 'CONFINED_OUT_MAX', 100)
    checks.api.outcomes = script([outcome(agent_outcome=0, stdout=b'y' * 300)])
    vid, result = run_one(checks)
    assert result['exit_code'] is None
    assert result['error'] == 'launcher_failed: launcher output bound exceeded'
    assert result['output_bytes'] <= 100
    assert checks.recorded == [result] and len(checks.jobs.closed) == 1
    assert evidence.check_of('test', 'runner check', ['runner'], result)['result'] == 'error'


def test_a_launcher_that_never_exits_is_a_timeout_and_is_ended(checks):
    checks.api.outcomes = script([outcome(launcher_exit=None, stdout=b'hang\n')])
    vid, result = run_one(checks, timeout=1)
    assert result['exit_code'] is None and result['error'] == 'timed out after 1s'
    assert result['output'] == b'hang\n'
    assert len(checks.jobs.closed) == 1
    launch = checks.boundary.launches[0]
    assert launch.end_state is not None and checks.api.exited[1000] == 1
    assert evidence.check_of('test', 'runner check', ['runner'], result)['result'] == 'error'


def used_after_close(checks):
    late = []
    for name in ('terminate_job', 'job_active_processes'):
        real = getattr(checks.jobs, name)

        def after_close(job, _real=real, _name=name):
            if job in checks.jobs.closed:
                late.append(_name)
            return _real(job)
        setattr(checks.jobs, name, after_close)
    return late


def test_a_run_that_stops_early_ends_the_launch_before_the_job_is_closed(checks):
    late = used_after_close(checks)
    checks.api.outcomes = script([outcome(launcher_exit=None, stdout=b'hang\n')])
    run_one(checks, timeout=1)
    launch = checks.boundary.launches[0]
    assert launch.end_state is not None and late == []
    assert checks.jobs.terminated == [launch.job]


def test_a_run_that_fails_ends_the_launch_before_the_job_is_closed(checks, monkeypatch):
    late = used_after_close(checks)

    def broken(self, timeout=None):
        raise RuntimeError('the wait failed')
    monkeypatch.setattr(mxc_verifier.ConfinedChild, 'wait', broken)
    checks.api.outcomes = script([outcome(launcher_exit=None)])
    with pytest.raises(RuntimeError, match='the wait failed'):
        run_one(checks)
    assert len(checks.jobs.closed) == 1 and len(checks.jobs.terminated) == 1 and late == []


def test_an_attempt_is_journalled_under_its_own_name_and_ends_with_a_completion(checks):
    vid, _ = run_one(checks, attempt=2)
    name = 'verify_%s_2-p1' % vid
    assert name == mxc_ledger.journal_name('verify/%s.2' % vid, 1)
    assert list(journals(checks)) == [name]
    records, invalid = mxc_ledger.read_records(journals(checks)[name], name)
    assert not invalid
    assert [r['op'] for r in records] == ['intent', 'ownership', 'disposal', 'completion']


def test_two_attempts_of_one_row_are_two_journals(checks):
    vid = ids.new_id('verification')
    checks.run(vid, 0)
    checks.run(vid, 1)
    assert sorted(journals(checks)) == ['verify_%s_0-p1' % vid, 'verify_%s_1-p1' % vid]


def test_the_checkout_is_exactly_the_exported_tree_when_the_launcher_is_spawned(checks):
    seen = {}
    vid = ids.new_id('verification')
    p = VerifyPaths(vid, 0)

    def at_launch():
        seen['files'] = sorted(os.listdir(p.checkout))
        seen['src'] = open(os.path.join(p.checkout, 'src', 'main.py'), 'rb').read()
    checks.boundary.before_launch = at_launch
    checks.run(vid, 0)
    assert seen == {'files': ['src'], 'src': b'print("x")\n'}      # no .git
    assert checks.boundary.launch_calls[0]['cwd'] == p.checkout


@pytest.mark.parametrize('fail', [ValueError('a tree Core cannot export'),
                                  OSError('the store is gone')])
def test_a_tree_that_cannot_be_exported_launches_nothing(checks, monkeypatch, fail):
    def export(*args):
        raise fail
    monkeypatch.setattr(local, '_export_tree', export)
    _, result = run_one(checks)
    assert result['exit_code'] is None and result['error'].startswith('prepare_failed')
    assert checks.boundary.launch_calls == [] and journals(checks) == {}
    assert checks.recorded == [result]


def test_the_scratch_is_a_second_writable_grant_over_the_checkout(checks):
    vid, _ = run_one(checks)
    p = VerifyPaths(vid, 0)
    scratch = os.path.dirname(p.checkout)
    fs = checks.boundary.launches[0].policy.raw['filesystem']
    assert fs['readwritePaths'] == [os.path.normpath(p.checkout), os.path.normpath(scratch)]
    env = checks.boundary.launch_calls[0]['env']
    assert env['USERPROFILE'] == scratch and env['TEMP'] == p.tmp


# ── Option 3: with no confined identity a check is an error, never a pass ──

def test_with_admission_closed_nothing_runs_and_the_row_reads_error(tmp_path, sdk, monkeypatch):
    h = make(tmp_path, sdk, cls=Traced)
    tool = tmp_path / 'toolchain'
    tool.mkdir()
    (tool / 'runner.exe').write_bytes(b'the staged runner')
    monkeypatch.setattr(local, '_export_tree', lambda *a: None)
    node = local.LocalNode()
    node.isolation = iso.Isolation(node, boundary=h.boundary)
    assert h.boundary.available() is False
    recorded = []
    result = node.run_confined_check(ids.new_id('verification'), 0, ['runner', 'check'],
                                     toolchain=[str(tool)], timeout=30, record=recorded.append,
                                     project_id='proj', revision=SEED, workdirs=[])
    assert result['exit_code'] is None and result['error'].startswith('isolation: ')
    assert h.boundary.launch_calls == [] and h.api.created == [] and journals_of(h) == {}
    assert recorded == [result]
    check = evidence.check_of('test', 'runner check', ['runner', 'check'], result)
    assert check['result'] == 'error' and 'pass' not in json.dumps(check['result'])


def journals_of(h):
    return h.ledger.journals()
