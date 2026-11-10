"""T-1022 — close the highest-risk test gaps in archeus/node/mxc.py lines 241-422.

Selected branches (ranked by risk; fail-closed and denial first, then boundaries,
then error paths), all inside the slice archeus/node/mxc.py:241-422:

1. mxc.py:303-305  spawn() must refuse a non-FakeMxc backend when the caller did
   not pass native_run=True, even with NATIVE_RUN_ENABLED open.
2. mxc.py:346-347,352-358  NativeMxc.spawn: a before_resume fault never resumes;
   the suspended child is terminated, waited on and retained on the error.
3. mxc.py:344-347  NativeMxc.spawn: a truthy-but-not-True in_job answer refuses
   and the ownership hook never runs.
4. mxc.py:346-349  NativeMxc.spawn: before_resume runs exactly once, after
   verified membership and before the single resume, on the child returned.
5. mxc.py:296  effective_identity refuses unexpected capability SIDs on a
   report that claims no AppContainer.
6. mxc.py:296  effective_identity refuses an unexpected AppContainer SID.
7. mxc.py:330,333-334  NativeMxc.spawn accepts only the boolean True from the
   pinned schema validator, and touches no transport otherwise.
8. mxc.py:293  effective_identity requires proc.is_alive() to be True itself,
   not merely truthy.
9. mxc.py:292  effective_identity requires an int create time; an equal-valued
   float is a reused-identity smuggle.
10. mxc.py:419-421  FakeMxc.spawn records create/assign/verify before the hook
    and the resume only after it returns.

Seam-faked OS calls only: no DLL, no Windows API, no network, no real process,
no sleeps. Placement and fakes follow tests/v1/unit/test_node_mxc_gaps.py and
tests/v1/unit/test_node_mxc_policy.py; nothing is imported from any other
test_gaps2 file, so sibling cards stay independent.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.node import mxc


def policy(tmp_path, **changes):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    args = dict(workspace=work, cwd=work, command_line='cmd.exe /d /c echo fixture',
                env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': str(work)},
                timeout_ms=1000)
    args.update(changes)
    return mxc.compile_policy(**args)


class Recorder:
    """A fake transport: records every call, answers from scripts, owns no kernel."""

    def __init__(self, *, member=True, resume=1):
        self.events = []
        self.member = member
        self.resume_answer = resume
        self.child = SimpleNamespace(
            terminate=lambda: self.events.append('terminate'),
            wait=lambda timeout: self.events.append(('wait', timeout)))

    def stage_policy(self, raw):
        self.events.append('stage')
        return 'unused'

    def create_suspended(self, argv, *, policy):
        self.events.append('create')
        return self.child

    def assign_job(self, job, proc):
        assert proc is self.child
        self.events.append('assign')

    def in_job(self, job, proc):
        assert proc is self.child
        self.events.append('membership')
        return self.member

    def resume(self, proc):
        assert proc is self.child
        self.events.append('resume')
        return self.resume_answer


def live_proc(tmp_path):
    """A fake-launched process whose identity currently verifies."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    mxc.effective_identity(proc)
    return proc


# --- 1. the native gate stays closed without the caller's own ask -------------

def test_the_seam_refuses_a_native_backend_the_call_did_not_ask_for(tmp_path, monkeypatch):
    """mxc.py:303-305: with NATIVE_RUN_ENABLED open, a caller that omits
    native_run=True must still be refused and the transport untouched."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    transport = Recorder()
    backend = mxc.NativeMxc(transport, lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='disabled'):
        mxc.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                  job=object(), backend=backend)
    assert transport.events == []
    # control: the same call that explicitly asks does reach the reviewed seam
    proc = mxc.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                     job=object(), backend=backend, native_run=True)
    assert proc is transport.child
    assert transport.events == ['stage', 'create', 'assign', 'membership', 'resume']


# --- 2-4. the before_resume seam on NativeMxc.spawn ---------------------------

@pytest.mark.parametrize('fault', [OSError('ledger disk failed'),
                                   mxc.MxcUnavailable('ledger refused'),
                                   KeyboardInterrupt('interrupted')],
                         ids=['oserror', 'mxcunavailable', 'interrupt'])
def test_a_failing_ownership_hook_never_resumes_and_retains_the_child(tmp_path, monkeypatch,
                                                                      fault):
    """mxc.py:346-347,352-358: a hook fault after verified membership terminates
    the suspended child, waits, retains it on the error, and resumes never."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    transport = Recorder()
    hooked = []

    def before_resume(child):
        hooked.append(child)
        raise fault

    backend = mxc.NativeMxc(transport, lambda raw: True)
    with pytest.raises(type(fault)) as caught:
        backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                      job=object(), before_resume=before_resume)
    assert hooked == [transport.child]                      # it ran, on the right child
    assert 'resume' not in transport.events
    assert transport.events[transport.events.index('membership'):] == [
        'membership', 'terminate', ('wait', 5)]             # killed, then waited
    assert caught.value.child is transport.child            # retained for quarantine
    assert not hasattr(caught.value, 'cleanup_error')       # cleanup itself succeeded


def test_the_ownership_hook_runs_after_membership_and_before_the_single_resume(
        tmp_path, monkeypatch):
    """mxc.py:346-349: the durable-ownership write sits exactly between the
    verified membership and the one resume, on the child the caller gets back."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    transport = Recorder()
    seen = []

    def before_resume(child):
        seen.append((child is transport.child, 'resume' in transport.events))
        transport.events.append('hook')

    backend = mxc.NativeMxc(transport, lambda raw: True)
    child = backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                          job=object(), before_resume=before_resume)
    assert child is transport.child
    assert seen == [(True, False)]                          # same child, not yet resumed
    assert transport.events == ['stage', 'create', 'assign', 'membership', 'hook',
                                'resume']                    # exact order, resume once


@pytest.mark.parametrize('member', [False, 1, 1.0, 'yes', None],
                         ids=['false', 'one', 'float', 'text', 'none'])
def test_membership_that_is_not_the_boolean_true_refuses_and_the_hook_never_runs(
        tmp_path, monkeypatch, member):
    """mxc.py:344-347: only the kernel's own True proves Job membership; until it
    does, the ownership hook is unreachable and the child is killed, not resumed."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    transport = Recorder(member=member)
    seen = []
    backend = mxc.NativeMxc(transport, lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='membership unverified') as caught:
        backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                      job=object(), before_resume=lambda child: seen.append(child))
    assert seen == []                                       # hook never ran
    assert 'resume' not in transport.events
    assert transport.events[-2:] == ['terminate', ('wait', 5)]
    assert caught.value.child is transport.child


# --- 5-6, 8-9. effective_identity fail-closed boundaries ----------------------

@pytest.mark.parametrize('caps', [('S-1-15-3-1',), ['S-1-15-3-1', 'S-1-15-3-2'],
                                  'S-1-15-3-1', ['']],
                         ids=['tuple', 'list', 'text', 'empty-entry'])
def test_capability_sids_nobody_granted_refuse_the_identity(tmp_path, caps):
    """mxc.py:296: a report that claims no AppContainer yet carries capability SIDs
    is a smuggled token, not a verified container, on its own."""
    proc = live_proc(tmp_path)
    report = mxc.effective_identity(proc)
    proc.identity_reader = lambda p: replace(report, capability_sids=caps)
    with pytest.raises(mxc.MxcUnavailable, match='unverified process identity'):
        mxc.effective_identity(proc)


def test_an_appcontainer_sid_without_the_claim_refuses_the_identity(tmp_path):
    """mxc.py:296: ac_sid set while is_appcontainer stays False is its own lie and
    must refuse by itself, not ride on the is_appcontainer check."""
    proc = live_proc(tmp_path)
    report = mxc.effective_identity(proc)
    assert report.ac_sid is None                            # accepted baseline
    proc.identity_reader = lambda p: replace(report, ac_sid='S-1-15-3-claimed')
    with pytest.raises(mxc.MxcUnavailable, match='unverified process identity'):
        mxc.effective_identity(proc)


@pytest.mark.parametrize('answer', [1, 'yes', [True]], ids=['one', 'text', 'list'])
def test_a_liveness_answer_that_is_truthy_but_not_true_refuses(tmp_path, answer):
    """mxc.py:293: `is not True` is load-bearing; a liveness probe answering 1 (or
    any truthy stand-in) is not proof the pid is still the one we launched."""
    proc = live_proc(tmp_path)
    proc.is_alive = lambda: answer
    with pytest.raises(mxc.MxcUnavailable, match='dead, reused or unverified'):
        mxc.effective_identity(proc)


def test_an_equal_valued_float_create_time_refuses_the_identity(tmp_path):
    """mxc.py:292: the type check is `type is int`, not isinstance or equality; a
    float that == the real create time would otherwise read as a live, matching
    process while every integer-formatted consumer downstream reads garbage."""
    proc = live_proc(tmp_path)
    report = mxc.effective_identity(proc)
    proc.identity_reader = lambda p: replace(report, create_time=float(report.create_time))
    with pytest.raises(mxc.MxcUnavailable, match='dead, reused or unverified'):
        mxc.effective_identity(proc)


# --- 7. the pinned schema answer must be True itself ---------------------------

@pytest.mark.parametrize('answer', [1, 1.0, 'true', [True], object()],
                         ids=['one', 'float', 'text', 'list', 'object'])
def test_a_schema_answer_that_is_truthy_but_not_true_refuses_before_any_transport(
        tmp_path, monkeypatch, answer):
    """mxc.py:330,333-334: `is True` is the gate; a validator returning 1 is a
    review bypass, and nothing may be staged or created while asking."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    transport = Recorder()
    backend = mxc.NativeMxc(transport, lambda raw: answer)
    with pytest.raises(mxc.MxcUnavailable, match='pinned schema validation failed'):
        backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'), job=object())
    assert transport.events == []                           # no lease staged, no child made


# --- 10. the fake owes the same ownership ordering the transport must keep -----

def test_the_fake_backend_records_ownership_before_the_hook_and_resumes_after(
        tmp_path):
    """mxc.py:419-421: the scripted backend keeps the native ordering contract. If
    the hook runs before the verify events, or the resume is logged before the
    hook returns, ledger tests built on this fake certify an order the real
    transport does not owe; and a failing hook must leave the resume unlogged."""
    good = mxc.FakeMxc([mxc.FakeOutcome()])
    seen = []

    def hook(proc):
        seen.append((tuple(good.events), proc.is_alive() is True, proc.poll() is None))
        good.events.append('hook')

    proc = good.spawn(policy(tmp_path), exe='unused', job=object(), before_resume=hook)
    assert seen == [(('create_suspended', 'assign_job', 'verify_job'), True, True)]
    assert good.events == ['create_suspended', 'assign_job', 'verify_job', 'hook', 'resume']
    assert proc.is_alive() is True                          # the hook did not run it down

    broken = mxc.FakeMxc([mxc.FakeOutcome()])

    def fault(proc):
        raise mxc.MxcUnavailable('ledger refused')

    with pytest.raises(mxc.MxcUnavailable, match='ledger refused'):
        broken.spawn(policy(tmp_path), exe='unused', job=object(), before_resume=fault)
    assert broken.events == ['create_suspended', 'assign_job', 'verify_job']
