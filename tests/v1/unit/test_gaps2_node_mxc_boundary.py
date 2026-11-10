"""T-1010: the uncovered fail-closed branches of `archeus/node/mxc_boundary.py` (1-255).

The shipped tests of this boundary cover what `available()` answers, the six conditions,
the identity calls, the pass-through Job calls and what `launch` compiles into a policy.
Nothing here repeats them. Each test below takes a branch of this slice that no existing
test reaches, and says which:

  1 `launch_confined` 227-231   a resumed launcher whose child cannot be built is ended
  2 `available()` 86-88         only a pin mismatch is an "unavailable", not a failed read
  3 `launch_confined` 225-226   a check refused by the policy never resumes a launcher
  4 `launch_confined` 226-228   the resume, the hand-over, the confined cap, this cap's deadline
  5 `reconcile()` 95-96         nothing is read without a ledger and a way to read a process
  6 `reconcile()` 97-98         an absence nobody proved is never a clean end
  7 `_launch` 234,252, `_key_of` 150   one verifier attempt, its own rows and journals
  8 `grant_established` 161, `_launch` 247   one row however it is spelled
  9 `_same` 55-56, `_launch` 241   the working directory is the grant it normalizes to
  10 `launch` 215               a launch's own deadline, and never a silent default

Nothing here starts a process or reaches the OS: the launcher is `Launch` and the draining
child is `Child`, both recorded, and the Job/handle half is the `Jobs` fake of
`test_mxc_boundary`, whose own OS mutation calls the autouse tripwire keeps armed.
"""

import os
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.node import isolation as iso, local, mxc_boundary, mxc_ledger, mxc_verifier

from .test_mxc_boundary import gate, make, sdk, seed_journal  # noqa: F401  (the fixtures)
from .test_pv20_isolation import (make_satisfying_request, new_execution_id,
                                  os_tripwire)  # noqa: F401  (the autouse tripwire)

#: the order the boundary's own calls happen in, as the seams saw them
ORDER = []


class CutShort(BaseException):
    """A cut that is not an `Exception`: the launcher must still be ended before it runs."""


class Launch:
    """`local.MxcLaunch`, recorded: what the boundary asks of a launcher, nothing run."""

    made = []

    def __init__(self, **kw):
        self.kw, self.started, self.cancelled = kw, [], []
        Launch.made.append(self)

    def start(self, *, job):
        self.started.append(job)
        ORDER.append(('start', self))
        return self

    def cancel(self, **kw):
        self.cancelled.append(kw)
        ORDER.append(('cancel', self))
        return None


class Child:
    """`mxc_verifier.ConfinedChild`: built and recorded, or it fails as `fails` says."""

    built, fails = [], None

    def __init__(self, launch, timeout, stdin_path, out_path):
        ORDER.append(('child', launch))
        if Child.fails is not None:
            raise Child.fails
        self.launch, self.timeout = launch, timeout
        self.stdin_path, self.out_path = stdin_path, out_path
        Child.built.append(self)


@pytest.fixture
def staged(request):
    """The expanded MXC SDK of `test_mxc_boundary`, read by name: this file takes that
    very fixture without binding its name, which ruff would read as a redefinition."""
    return request.getfixturevalue('sdk')


@pytest.fixture
def open_admission(request):
    """Native admission opened, exactly as `test_mxc_boundary` opens it."""
    return request.getfixturevalue('gate')


@pytest.fixture
def probe(tmp_path, staged, monkeypatch):
    """The boundary over recorded launcher and child seams, with a reserved identity whose
    plan is verified, so a confined check reaches the hand-over instead of a refusal."""
    ORDER.clear()
    Launch.made, Child.built, Child.fails = [], [], None
    monkeypatch.setattr(local, 'MxcLaunch', Launch)
    monkeypatch.setattr(mxc_verifier, 'ConfinedChild', Child)
    h = make(tmp_path, staged)
    handles = []
    h.jobs.open_inherited = lambda path, mode: handles.append(('open', path, mode))
    h.jobs.close_handle = lambda handle: handles.append(('close', handle))
    req = make_satisfying_request(new_execution_id(), str(tmp_path / 'layout'))
    identity = h.boundary.create_profile(req.execution_id)
    for g in req.grants:
        assert h.boundary.grant_established(g.path, identity['sid'], g.access)

    def go(**over):
        kw = dict(argv=['agent.exe', 'two words'], cwd=req.workspace, env={'A': '1'},
                  profile=identity['profile'], job={'job': 1}, stdin='the-stdin',
                  stdout='the-stdout')
        kw.update(over)
        return h.boundary.launch(kw.pop('argv'), **kw)

    def confined(**over):
        kw = dict(argv=['check', 'ok'], cwd=req.workspace, env={},
                  profile=identity['profile'], job={'job': 1}, timeout=2.0,
                  stdin_path=str(tmp_path / 'inert-stdin'), out_path=str(tmp_path / 'out.log'))
        kw.update(over)
        return h.boundary.launch_confined(kw.pop('argv'), **kw)

    def fail(err):
        Child.fails = err

    return SimpleNamespace(h=h, req=req, identity=identity, go=go, confined=confined,
                           made=Launch.made, built=Child.built, order=ORDER, fail=fail,
                           handles=handles)


# ── 1: a confined check whose child cannot be built must not leave a resumed launcher ──

@pytest.mark.parametrize('broken', [
    lambda: OSError(13, 'the attempt log is closed to us'),
    lambda: CutShort('the drain was cut before it owned the launch')])
def test_a_confined_check_whose_child_cannot_be_built_ends_the_launch_it_resumed(
        probe, broken):
    # mxc_boundary.py:226 resumed the launcher; 229-231 is the only end it can now get.
    # `test_a_started_launch_whose_child_cannot_be_built_is_ended` (tests/v1/integration/
    # test_pv20_mxc_verifier.py) walks the whole path through `checks.run`, which ends and
    # quarantines the launch itself, and so passes with this cancel gone; nothing there
    # pins that the boundary ends what it resumed, once, and hands the failure on unmoved.
    failure = broken()
    probe.fail(failure)
    with pytest.raises(BaseException) as raised:
        probe.confined()
    assert raised.value is failure                       # the failure is passed on, unmoved
    launch = probe.made[0]
    assert launch.started == [{'job': 1}]                # it really was resumed first
    assert len(launch.cancelled) == 1                    # ended exactly once, here
    assert isinstance(launch.cancelled[0]['reason'], str) and launch.cancelled[0]['reason']
    assert [(kind, who) for kind, who in probe.order] == [('start', launch), ('child', launch),
                                                          ('cancel', launch)]
    assert probe.built == []                             # no child exists that could drain it
    assert probe.h.jobs.terminated == [] and probe.h.jobs.closed == []   # the Job is Core's


# ── 2: only a pin mismatch is an answer; a failed read is not an absence ──

def test_a_pin_check_that_fails_for_a_reason_it_cannot_name_is_not_answered_unavailable(
        tmp_path, staged, open_admission, monkeypatch):
    # mxc_boundary.py:86-88 catches `staging.StageError` and nothing else. Answering
    # `False` for any failure would let `establish` fall back to the detached path as
    # though the isolated path had simply not been activated, and no shipped test reads
    # the branch: `test_pins_that_the_staged_sdk_does_not_match_make_it_unavailable`
    # only ever raises the one error this call is allowed to answer.
    h = make(tmp_path, staged)
    assert h.boundary.available() is True

    def unreadable(root, pins=None):
        raise OSError(13, 'the staged tree cannot be read')

    monkeypatch.setattr(mxc_boundary.staging, 'verify_mxc', unreadable)
    with pytest.raises(OSError, match='cannot be read'):
        h.boundary.available()


# ── 3: a confined check the policy refuses never reaches a launcher at all ──

def test_a_confined_check_the_policy_refuses_resumes_nothing_and_needs_no_end(probe):
    # mxc_boundary.py:225-226 hands the deadline and the transport to `_launch` (234-243) before
    # it starts anything: `test_a_profile_that_was_never_reserved_is_refused` and
    # `test_a_working_directory_that_is_not_a_writable_grant_is_refused` walk the plain
    # `launch` only, so the confined path keeping its refusals ahead of the resume is
    # what nothing here has ever checked.
    with pytest.raises(iso.IsolationUnavailable, match='profile_unknown'):
        probe.confined(profile=iso.profile_name(new_execution_id()))
    with pytest.raises(iso.IsolationUnavailable, match='mxc_policy'):
        probe.confined(cwd=probe.req.grant_for('runtime').path)
    assert probe.made == [] and probe.built == [] and probe.order == []
    assert probe.h.jobs.terminated == [] and probe.h.jobs.closed == []


# ── 4: what the confined hand-over carries, and in what order ──────────────────

def test_a_confined_check_is_resumed_before_its_child_is_built_over_the_confined_cap(probe):
    # mxc_boundary.py:226-228: the deadline is this check's own seconds rounded up, the
    # transport is the cap the attempt log is held to, and the child is handed the launch
    # that was already started. The integration pair covers a whole-number deadline
    # (42 s) and the cap behind `Isolation.run_confined`, never this hand-over, never a
    # sub-second check, and never that no stdio handle leaves the boundary.
    child = probe.confined(stdin_path='the-empty-stdin', out_path='the-attempt-log')
    launch = probe.made[0]
    assert launch.started == [{'job': 1}]
    assert child.launch is launch and child.timeout == 2.0
    assert (child.stdin_path, child.out_path) == ('the-empty-stdin', 'the-attempt-log')
    assert launch.kw['timeout_ms'] == 2000 and launch.kw['transport'] == {
        'output_limit': iso.CONFINED_OUT_MAX, 'total_limit': iso.CONFINED_OUT_MAX}
    assert [(kind, who) for kind, who in probe.order] == [('start', launch), ('child', launch)]
    probe.confined(timeout=0.0004)                       # a check of less than a millisecond
    assert probe.made[1].kw['timeout_ms'] == 1           # is never a launcher with no deadline
    assert probe.made[1].kw['timeout_ms'] != probe.h.boundary.timeout_ms
    for made in probe.made:                              # the transport owns the child's stdio
        assert 'stdin' not in made.kw and 'stdout' not in made.kw
    probe.go(stdin='the-stdin', stdout='the-stdout')
    assert 'stdin' not in probe.made[-1].kw and 'stdout' not in probe.made[-1].kw
    assert probe.handles == []                           # no inherited handle was opened for it


# ── 5 and 6: the restart read of a journal ─────────────────────────────────────

def test_a_restart_reads_no_journal_without_a_ledger_or_a_way_to_read_a_process(tmp_path,
                                                                                staged):
    # mxc_boundary.py:95-96. No unit test has called `MxcBoundary.reconcile`: the only
    # boundary read of a restart that exists, `test_a_boundary_with_no_ledger_reconciles_
    # nothing` (tests/v1/integration/test_pv20_mxc_lifecycle.py), holds an
    # `UnavailableBoundary`, whose answer is `{}` without a ledger to skip reading.
    reads = []

    class Ledger:
        root = os.sep + 'no-such-ledger'

        def journals(self):
            reads.append('journals')
            raise AssertionError('a restart with no process to read may read no journal')

    bare = make(tmp_path, staged, ledger=Ledger(), process_reader=None).boundary
    assert bare.reconcile() == {}
    assert reads == []
    h = make(tmp_path, staged)                           # a ledger, no process reader
    h.boundary.ledger = None
    assert h.boundary.reconcile() == {}


def test_a_restart_that_cannot_prove_an_absence_never_calls_a_death_clean(tmp_path, staged):
    # mxc_boundary.py:97-98: the reader the ledger is handed is Core's answer, and the
    # fallback that answers nothing is what keeps an unproven absence a quarantine.
    # No shipped test reaches either arm; `mxc_ledger.reconcile` is only ever read here
    # through the boundary.
    h = make(tmp_path, staged, resource_reader=None)
    eid = new_execution_id()
    name = mxc_ledger.journal_name(eid, 1)
    seed_journal(h, name, 'intent', 'ownership')         # a process that is simply gone
    assert h.boundary.reconcile() == {name: mxc_ledger.DEAD_UNVERIFIED}
    records, invalid = mxc_ledger.read_records(h.ledger.journals()[name], name)
    assert not invalid and [r['op'] for r in records] == ['intent', 'ownership', 'quarantine']
    assert records[-1]['reason'] == 'restart_unverified'

    asked, other = [], mxc_ledger.Ledger(str(tmp_path / 'other-ledger'))
    seed_journal(SimpleNamespace(ledger=other), name, 'intent', 'ownership')
    h.boundary.ledger, h.boundary.resource_reader = other, (
        lambda execution_id, owner: asked.append((execution_id, owner)) or True)
    assert h.boundary.reconcile() == {name: mxc_ledger.DEAD_CLEAN}
    assert asked == [(name, {'op': 'ownership', 'seq': 1, 'execution_id': name, 'pid': 1,
                             'create_time': 1, 'requested_policy_digest': '0' * 64,
                             'applied': [], 'observed': {}, 'owned': []})]  # never the plan
    assert [r['op'] for r in mxc_ledger.read_records(other.journals()[name], name)[0]] == [
        'intent', 'ownership']


# ── 7: one verifier attempt, its own rows and its own journals ─────────────────

def test_a_verifier_attempt_launches_over_its_own_attempt_s_rows_only(tmp_path, staged,
                                                                      monkeypatch):
    # mxc_boundary.py:234 maps a profile back to one reserved key, 150-161 registers a
    # row under the marker that names it and 252 counts that key's journals. The shipped
    # verifier tests name and reserve an attempt (`test_a_verifier_attempt_is_named_and_
    # reserved_like_an_execution`) and run one attempt per boundary, so two attempts held
    # at once, and which one a launch belongs to, has never been read.
    Launch.made = []
    del ORDER[:]
    monkeypatch.setattr(local, 'MxcLaunch', Launch)
    h = make(tmp_path, staged)
    vid = ids.new_id('verification')
    keys = [iso.Principal('verify', vid, n).key for n in (0, 1)]
    dirs = []
    for n, key in enumerate(keys):
        assert h.boundary.create_profile(key)['profile'] == iso.profile_name(key)
        d = os.path.join(str(tmp_path / 'checks'), 'attempt-%d' % n)
        os.makedirs(d, exist_ok=True)
        dirs.append(d)
    sid0, sid1 = (h.boundary.derive_sid(key) for key in keys)
    assert (sid0, sid1) != (None, None) and sid0 != sid1
    stray = os.path.join(str(tmp_path / 'checks'), 'stray')
    os.makedirs(stray, exist_ok=True)
    # the marker names the launch a row belongs to: a directory one attempt holds is
    # registered under the attempt that verified it, never under the other
    assert h.boundary.grant_established(stray, sid0, 'rw') is True
    assert h.boundary._reserved[keys[1]] == []
    assert h.boundary._reserved[keys[0]] == [(os.path.normpath(stray), 'rw')]
    assert h.boundary.grant_established(dirs[0], sid0, 'rw') is True
    assert h.boundary.grant_established(dirs[1], sid1, 'rw') is True
    assert h.boundary.granted_to(dirs[1], sid0) is False  # attempt 0 reaches none of 1's
    assert h.boundary.granted_to(dirs[0], sid1) is False
    seed_journal(h, mxc_ledger.journal_name(keys[1], 1), 'intent', 'ownership', 'disposal',
                 'completion')

    def check(n):
        return h.boundary.launch(['check'], cwd=dirs[n], env={}, job={'job': n},
                                 profile=iso.profile_name(keys[n]), stdin=None, stdout=None)

    late, first = check(1), check(0)
    assert late.kw['execution_id'] == keys[1] and first.kw['execution_id'] == keys[0]
    assert late.kw['workspace'] == os.path.normpath(dirs[1])
    assert first.kw['workspace'] == os.path.normpath(dirs[0])
    assert (late.kw['writable'], late.kw['readonly']) == ([], [])   # no row of attempt 0's
    assert sorted(first.kw['writable']) == [os.path.normpath(stray)]
    assert late.kw['process_seq'] == 2 and first.kw['process_seq'] == 1


# ── 8: one row, however the plan spelled it ───────────────────────────────────

def test_the_same_grant_written_two_ways_is_one_row_of_the_policy(probe):
    # mxc_boundary.py:161 registers the normalized path and 247 keeps the workspace
    # out of the writable list by equality on that registration.
    # `test_the_same_path_twice_is_one_grant` passes the identical string twice and
    # `test_a_verified_grant_is_registered_once_per_path_for_the_launch` reads back a row
    # it spelled itself, so a row kept as it arrived, and with it a policy that writes the
    # workspace twice, has never been read.
    state = probe.req.grant_for('state').path
    spelled = state + os.sep + '.' + os.sep
    assert probe.h.boundary.grant_established(spelled, probe.identity['sid'], 'rw') is True
    rows = probe.h.boundary._reserved[probe.req.execution_id]
    canonical = os.path.normpath(state)
    assert (spelled, 'rw') not in rows                     # the row is kept canonically
    assert rows.count((canonical, 'rw')) == 2              # and is still the one row twice read
    kw = probe.go().kw
    assert [p for p in kw['writable'] if os.path.normpath(p) == canonical] == [canonical]
    assert all(path == os.path.normpath(path) for path in kw['writable'] + kw['readonly'])
    assert kw['workspace'] not in kw['writable']


# ── 9: the working directory is the grant it normalizes to ─────────────────────

def test_a_working_directory_spelled_like_a_grant_is_that_grant_and_not_a_refusal(probe):
    # mxc_boundary.py:55-56 and 241: the policy carries the granted path, not the
    # directory as the caller wrote it. `test_a_working_directory_that_is_not_a_writable_
    # grant_is_refused` only ever passes a cwd that equals its row exactly, so a plain
    # equality would answer every test shipped and still refuse a plan whose cwd merely
    # ends in a separator.
    child = probe.go(cwd=probe.req.workspace + os.sep)
    assert child.kw['workspace'] == os.path.normpath(probe.req.workspace)
    assert child.kw['cwd'] == probe.req.workspace + os.sep      # kept as the caller wrote it
    assert probe.made == [child]


# ── 10: a launch's own deadline, and never a silent default ───────────────────

def test_a_launch_given_its_own_deadline_uses_it_and_never_the_boundarys_default(probe):
    # mxc_boundary.py:215: the launch's deadline if it brought one, the boundary's
    # otherwise, and `None` is the only answer that means "not given". Every shipped
    # launch goes through `launched.go`, which never passes a `timeout_ms`, so the whole
    # arm of an explicit deadline is unread: `assert kw['timeout_ms'] == 5000`
    # (test_the_launch_is_built_from_the_native_parts_and_nothing_else) only reads the
    # default, and `test_a_launch_without_a_deadline_is_refused` only the boundary's own.
    assert probe.go(timeout_ms=222).kw['timeout_ms'] == 222
    assert probe.go().kw['timeout_ms'] == probe.h.boundary.timeout_ms == 5000
    assert probe.go(timeout_ms=0).kw['timeout_ms'] == 0    # given, and falsy: still its own
