"""T-780 gap checks for the closed MXC seam (archeus/node/mxc.py): fail-closed and
denial paths first, then boundary values, then error paths.

Style follows tests/v1/unit/test_node_mxc.py and tests/v1/unit/test_node_mxc_gaps.py:
synthetic policies, tmp_path fixtures, monkeypatched seams, fake transports.
No network, no real process, no Windows API call; every OS call stays behind the
same seams the existing tests fake.
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


class SequencedChild:
    """A suspended child that records the disposal the ordering contract owes."""

    def __init__(self, events):
        self.events = events

    def terminate(self):
        self.events.append('terminate')

    def wait(self, timeout):
        self.events.append(('wait', timeout))


class HookTransport:
    """Scriptable transport: every call is an event; scripted answers only."""

    def __init__(self, events, child, policy_path, resume_count=1):
        self.events, self.child = events, child
        self.policy_path, self.resume_count = policy_path, resume_count
        self.argv = None

    def stage_policy(self, raw):
        self.events.append('stage')
        return self.policy_path

    def create_suspended(self, argv, *, policy):
        self.events.append('create_suspended')
        self.argv = argv
        return self.child

    def assign_job(self, job, proc):
        self.events.append('assign')

    def in_job(self, job, proc):
        self.events.append('verify_job')
        return True

    def resume(self, proc):
        self.events.append('resume')
        return self.resume_count


class LedgerInterrupt(BaseException):
    """A fault from the ledger that is deliberately NOT an Exception."""


# --- the ten highest-risk uncovered branches ---------------------------------

def test_native_hook_failure_never_resumes_and_retains_the_child(tmp_path, monkeypatch):
    """mxc.py:293-294,297-305 a before_resume fault must never reach the single
    resume, and the suspended child must be terminated, waited on and retained on
    the error for Core to quarantine. Removing the try/except, moving the hook
    after the resume, or dropping terminate/wait all fail this check."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    events = []
    child = SequencedChild(events)
    transport = HookTransport(events, child, str(tmp_path / 'policy.json'))

    def hook(proc):
        events.append('hook')
        raise mxc.MxcUnavailable('ledger refused')

    backend = mxc.NativeMxc(transport, lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='ledger refused') as caught:
        backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                      job=object(), before_resume=hook)
    assert caught.value.child is child
    assert 'resume' not in events
    assert events == ['stage', 'create_suspended', 'assign', 'verify_job', 'hook',
                      'terminate', ('wait', 5)]
    assert not hasattr(caught.value, 'cleanup_error')


def test_native_hook_runs_after_membership_before_the_resume(tmp_path, monkeypatch):
    """mxc.py:291-295 the ownership facts are durable only after membership was
    verified and before the launcher can run. Running the hook before assign or
    before verify_job (unverified child, facts not owed), after the resume (facts
    after code ran), or never calling a provided hook all fail this check."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    events = []
    child = SequencedChild(events)
    transport = HookTransport(events, child, str(tmp_path / 'policy.json'))
    seen = []

    def hook(proc):
        seen.append((proc is child, 'verify_job' in events, 'resume' in events))
        events.append('hook')

    backend = mxc.NativeMxc(transport, lambda raw: True)
    assert backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                         job=object(), before_resume=hook) is child
    assert seen == [(True, True, False)]
    assert events == ['stage', 'create_suspended', 'assign', 'verify_job', 'hook', 'resume']


def test_native_hook_base_exception_still_never_resumes(tmp_path, monkeypatch):
    """mxc.py:354-361 'a hook that raises' is not narrowed to Exception: any fault,
    a BaseException included, leaves the child terminated and retained (`err.child`),
    never a suspended child handed to no one."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    events = []
    child = SequencedChild(events)
    transport = HookTransport(events, child, str(tmp_path / 'policy.json'))

    def hook(proc):
        events.append('hook')
        raise LedgerInterrupt('interrupted')

    backend = mxc.NativeMxc(transport, lambda raw: True)
    raised = None
    try:
        backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'),
                      job=object(), before_resume=hook)
    except LedgerInterrupt as err:
        raised = err
    assert raised is not None
    assert 'resume' not in events
    assert getattr(raised, 'child', None) is child
    assert events[-2:] == ['terminate', ('wait', 5)]


def test_spawn_refuses_the_policy_reason_not_the_backend_gate(tmp_path):
    """mxc.py:254-257 validate_policy runs before the backend gate, so an unsafe
    policy is refused with its policy reason even when the backend is missing or
    foreign. Swapping the two lines would answer 'disabled' instead and hide the
    containment failure behind a generic error."""
    compiled = policy(tmp_path)
    compiled.raw['process']['inheritDefaultEnv'] = True
    with pytest.raises(mxc.MxcUnavailable) as caught:
        mxc.spawn(compiled, exe='unused', job=object(), backend=None)
    assert 'invalid MXC policy' in str(caught.value)
    assert 'disabled' not in str(caught.value)
    with pytest.raises(mxc.MxcUnavailable, match='native MXC execution disabled'):
        mxc.spawn(policy(tmp_path), exe='unused', job=object(), backend=None)


def test_native_refuses_a_mutated_policy_before_asking_the_schema(tmp_path, monkeypatch):
    """mxc.py:280-286 revalidation precedes the pinned-schema consultation and the
    staged policy file. If the schema validator (or the transport) saw the document
    first, a mutated policy would be staged, reviewed and only then refused; this
    check fails if validate_policy moves after line 281 or 286."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    events = []
    compiled = policy(tmp_path)
    compiled.raw['network']['egress']['default'] = 'allow'

    def validator(raw):
        events.append('schema')
        return True

    transport = HookTransport(events, SequencedChild(events), str(tmp_path / 'policy.json'))
    backend = mxc.NativeMxc(transport, validator)
    with pytest.raises(mxc.MxcUnavailable, match='unsafe network policy'):
        backend.spawn(compiled, exe=str(tmp_path / 'wxc-exec.exe'), job=object())
    assert events == []


@pytest.mark.parametrize('raw', ['containmentprocesscontainer', None, 7, ['version'], ('x',)],
                         ids=['str', 'none', 'int', 'list', 'tuple'])
def test_policy_object_with_a_non_dict_raw_refuses(tmp_path, raw):
    """mxc.py:141-142 both halves of the guard matter: an MxcPolicy whose raw was
    replaced by a non-dict must be refused by name. Without the isinstance-dict
    test a str raw survives on substring/`in` semantics and every later error is
    mislabelled 'invalid MXC policy: ...' instead of 'MxcPolicy object required'."""
    compiled = policy(tmp_path)
    object.__setattr__(compiled, 'raw', raw)
    with pytest.raises(mxc.MxcUnavailable, match='MxcPolicy object required'):
        mxc.validate_policy(compiled)
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='MxcPolicy object required'):
        mxc.spawn(compiled, exe='unused', job=object(), backend=fake)
    assert fake.calls == []


def test_validate_refuses_an_empty_anchor_value_the_compiler_let_through(tmp_path):
    """mxc.py:170-171 the compiler only requires the anchor names (line 107) and
    string values (line 103); an empty SYSTEMROOT='' compiles and only the launch
    revalidation refuses it. Dropping the truthiness check on env.get would launch
    a container whose Windows anchors are blank."""
    with pytest.raises(mxc.MxcUnavailable, match='SYSTEMROOT and LOCALAPPDATA required'):
        policy(tmp_path, env={'SYSTEMROOT': '', 'LOCALAPPDATA': 'x'})
    compiled = policy(tmp_path)
    compiled.raw['process']['env'] = ['SYSTEMROOT=', 'LOCALAPPDATA=x']
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='SYSTEMROOT and LOCALAPPDATA required'):
        mxc.spawn(compiled, exe='unused', job=object(), backend=fake)
    assert fake.calls == []


def test_validate_refuses_a_nameless_environment_entry(tmp_path):
    """mxc.py:166-168 an entry '=x' splits to an empty key; without the `not key`
    clause it would validate (env[''] = 'x') and reach the backend as a policy the
    container must ignore. The refusal must name it a policy error, not pass it."""
    compiled = policy(tmp_path)
    compiled.raw['process']['env'] = ['=x', 'SYSTEMROOT=C:\\Windows', 'LOCALAPPDATA=x']
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='duplicate environment entry'):
        mxc.spawn(compiled, exe='unused', job=object(), backend=fake)
    assert fake.calls == []


def test_native_refuses_a_relative_exe_before_anything_is_staged(tmp_path, monkeypatch):
    """mxc.py:337 the launcher is re-passed through _path before the policy is staged:
    a bare exe (PATH-hijacked) refuses with nothing staged, so no protected policy
    file is left behind and no child is created. The staged path is not checked here
    on purpose (the transport's own `stage_policy` refuses a relative one)."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    events = []
    transport = HookTransport(events, SequencedChild(events), str(tmp_path / 'policy.json'))
    backend = mxc.NativeMxc(transport, lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='policy paths must be absolute'):
        backend.spawn(policy(tmp_path), exe='wxc-exec.exe', job=object())
    assert events == []


def test_identity_refuses_an_equal_float_create_time(tmp_path):
    """mxc.py:244 the type gate is load-bearing: 100000.0 == 100000 and > 0, so a
    numeric-only check would certify a launcher that reports a float timestamp (a
    reused-PID or truncation hazard the int identity is checked against)."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    report = mxc.effective_identity(proc)
    proc.identity_reader = lambda p: replace(report, create_time=float(report.create_time))
    with pytest.raises(mxc.MxcUnavailable, match='dead, reused or unverified'):
        mxc.effective_identity(proc)


@pytest.mark.parametrize('answer', [None, 1, 'alive', lambda: True],
                         ids=['none', 'one', 'str', 'callable'])
def test_identity_requires_liveness_to_be_exactly_true(tmp_path, answer):
    """mxc.py:245 `proc.is_alive() is not True` refuses a launcher whose liveness
    probe answers anything but True; relaxing it to a truthiness test would certify
    a process whose is_alive returned a junk truthy value or None on error."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    mxc.effective_identity(proc)
    proc.is_alive = lambda: answer
    with pytest.raises(mxc.MxcUnavailable, match='unverified process identity'):
        mxc.effective_identity(proc)


# --- supplementary checks, beyond the required ten ---------------------------

@pytest.mark.parametrize('field,value', [
    ('is_appcontainer', True),
    ('ac_sid', 'S-1-15-3-claimed'),
    ('capability_sids', ('S-1-15-3-cap',)),
], ids=['appcontainer', 'ac-sid', 'capabilities'])
def test_identity_refuses_each_unverified_appcontainer_claim_alone(tmp_path, field, value):
    """mxc.py:248 the three AppContainer terms are separate `or` clauses; the pair
    is_appcontainer+ac_sid+capability_sids together is already pinned elsewhere.
    If any single clause were dropped (e.g. is_appcontainer flipped alone), an F1
    host-user token would claim an F2 AppContainer SID and be certified."""
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    proc = fake.spawn(policy(tmp_path), exe='unused', job=object())
    report = mxc.effective_identity(proc)
    proc.identity_reader = lambda p: replace(report, **{field: value})
    with pytest.raises(mxc.MxcUnavailable, match='dead, reused or unverified'):
        mxc.effective_identity(proc)


@pytest.mark.parametrize('answer', [None, 1, 'verified'], ids=['none', 'one', 'str'])
def test_native_requires_the_schema_answer_to_be_exactly_true(tmp_path, monkeypatch, answer):
    """mxc.py:281-282 `is not True`, not truthiness: a pinned-schema validator that
    answers 1 or 'verified' (or forgets to return) must stop the launch before any
    transport call, exactly like the documented False case."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    events = []
    transport = HookTransport(events, SequencedChild(events), str(tmp_path / 'policy.json'))
    backend = mxc.NativeMxc(transport, lambda raw: answer)
    with pytest.raises(mxc.MxcUnavailable, match='pinned schema validation failed'):
        backend.spawn(policy(tmp_path), exe=str(tmp_path / 'wxc-exec.exe'), job=object())
    assert events == []


def test_native_flag_enabled_still_requires_the_per_call_claim(tmp_path, monkeypatch):
    """mxc.py:255-256 native execution needs BOTH the module flag AND the caller's
    native_run=True. With the flag flipped on (e.g. by a reviewed run), a caller
    that forgot to claim native_run must still be refused, and a foreign backend
    must never be reached; dropping the native_run conjunct fails this."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    seen = []

    class Foreign:
        def spawn(self, policy, *, exe, job):
            seen.append((exe, job))
            return SimpleNamespace(pid=1)

    for kwargs in ({}, {'native_run': False}):
        with pytest.raises(mxc.MxcUnavailable, match='native MXC execution disabled'):
            mxc.spawn(policy(tmp_path), exe='unused', job=object(),
                      backend=Foreign(), **kwargs)
    assert seen == []


def test_compiled_policy_is_sealed_against_nested_mutation_of_its_source(tmp_path):
    """mxc.py:91 the deepcopy in __post_init__ is what makes MxcPolicy a seal: a
    caller that keeps the raw dict alive must not be able to widen a compiled
    policy by mutating nested sections afterwards. Replacing deepcopy with a plain
    binding leaks every mutation below into the sealed policy."""
    compiled = policy(tmp_path)
    source = dict(compiled.raw)
    sealed = mxc.MxcPolicy(source)
    source['process']['inheritDefaultEnv'] = True
    source['network']['egress']['default'] = 'allow'
    assert sealed.raw['process']['inheritDefaultEnv'] is False
    assert sealed.raw['network']['egress'] == {'default': 'deny'}
    assert mxc.spawn(sealed, exe='unused', job=object(),
                     backend=mxc.FakeMxc([mxc.FakeOutcome()])) is not None


def test_fake_backend_orders_the_ownership_seam_before_the_resume(tmp_path):
    """mxc.py:363-367 the fake owes the same ordering as the transport: the hook
    runs after create/assign/verify and before 'resume'. Moving before_resume
    after the append on line 367, or skipping a provided hook, fails this check."""
    fake = mxc.FakeMxc([mxc.FakeOutcome(), mxc.FakeOutcome()])
    seen = []

    def hook(proc):
        seen.append((proc.pid, tuple(fake.events)))

    proc = fake.spawn(policy(tmp_path), exe='unused', job=object(), before_resume=hook)
    assert seen == [(proc.pid, ('create_suspended', 'assign_job', 'verify_job'))]
    assert fake.events == ['create_suspended', 'assign_job', 'verify_job', 'resume']
    plain = fake.spawn(policy(tmp_path), exe='unused', job=object())
    assert fake.events[-1] == 'resume' and len(fake.events) == 8 and plain is not None
