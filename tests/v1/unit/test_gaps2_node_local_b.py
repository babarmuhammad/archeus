# ruff: noqa: F401  (imported for the fakes and fixtures they hand to these tests)
# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-1026: the highest-risk uncovered branches of archeus/node/local.py 408-578.

The slice is the ownership seam and the two exits that must never be confused for one
another: `_seam`, `_requested_digest`, `_record_intent`, `_record_ownership`,
`_resource_record`, `_separate`, the stream accessors, `terminate`, `wait`,
`_workload_code` and `cancel` (local.py:408-578 inclusive). Everything here is a fake:
the Win32 api, Core's boundary, the admission broker and the readers are the fakes the
wire tests already use, the ledger is a real journal under tmp_path, and no Windows api,
DLL, real process or network is touched, so every test runs on Linux and on Windows
unchanged.

The ten selected branches, ranked by risk (fail-closed denial first, then ownership
boundaries, then the drains, then the cold error paths). Each line of the list is a
branch that has never been taken, not merely a line nobody asserted on; the card report
carries the evidence, which is: no test in tests/v1 argues these cases at any tier, the
existing suite survives a mutation of each of the ten, and the six lines behind entries 7
to 10 have never been executed at all by any test that runs here
(442, 505, 509, 517, 521, 533 - the tracer of the card report; `coverage` is not
installed in this container):

1. local.py:484-494  `_separate` never refused a live peer holding THIS execution id:
   the execution-id clause has never been the one that refused a launch.
2. local.py:463-467 + 479-481  a path Core denied, read back as anything but denied,
   has never refused a launch - every existing read-back test compiles no denied path.
3. local.py:463-467  the denied set has never been part of the requested grants an
   ownership record is built from (no record in the suite holds a deny access).
4. local.py:427-429 + 413-418  the create intent has never named a denied path, and
   nothing pins what the requested digest is the digest of, or that it cannot move.
5. local.py:490-492  a recycled stamp (same pid at another creation time, or the same
   creation time at another pid) has never been told from the process it replaced.
6. local.py:535  the ending of a stopped drain never carried the reason its owner gave
   (`stop_reason` has never been set by a test, only by mxc_context and mxc_verifier).
7. local.py:505-517  the four accessors that hand a launch's identity and pipes to its
   caller: three of the four (pid, stdin, stderr) are lines no test here has executed,
   and `launch.pid` is what mxc_context.py:32 and :111 write into Core's live record.
8. local.py:519-521  `MxcLaunch.terminate()` with a live child has never run; only the
   no-child guard of that line has (tests/v1/integration/test_pv20_mxc_local.py:285).
9. local.py:532-533  the drain-preserving re-raise of AlreadyDraining has never run on
   a journalled launch with its ledger, broker and handle facts asserted.
10. local.py:441-442  `_record_ownership` with no ledger has never run: an
   unjournaled backend is promised no ownership hook, so the guard itself is cold.

Two further tests sit below the cut: they harden two paths whose ending is already
asserted elsewhere (the forwarded `cancelled` stop, and an outcome reader that raises),
kept because the assertions around them - who was asked, who was not, what the journal
and the broker and the boundary owe the ending - are not made there. Each test names, in
its own comment, the source branch whose removal or inversion it would catch.
"""

import copy
import hashlib
import io
import itertools
from types import SimpleNamespace

import pytest

from archeus.node import local, mxc, mxc_ledger, mxc_native, staging

from .test_mxc_wire import (CREATION_TIME, PID, FakeApi, FakeBoundary,  # noqa: F401
                           FakeBroker, TracedLedger, args, journal_ops, journal_records,
                           native_parts)
from .test_mxc_wire_resources import facts, grants  # noqa: F401

#: a path Core denies: the launcher must never write, or read, through it
DENIED = 'C:/fixture/denied'
DENIED_ID = local.mxc_resource_id(DENIED)
CLEAN = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)


def parts(tmp_path, args, *, execution_id='e1', process_seq=1, denied=(), exit_code=0,
          reads=None, counts=(), broker=True, outcome=None, reader=None, disposal=None,
          transport=None):
    """The same five fakes as the wire fixture (tests/v1/unit/test_mxc_wire.py:245),
    with the two knobs that fixture has no argument for: a compiled denied grant, and
    the clock and pause of the launcher transport itself."""
    api = FakeApi()
    boundary = FakeBoundary(api, counts)
    api.exit, api.stalled = exit_code, False
    if reads is not None:
        api.reads = reads
    journal = TracedLedger(tmp_path / 'ledger', api)
    tick = itertools.count(0.0)
    admission = FakeBroker(api) if broker else None
    launch = local.MxcLaunch(api=api, boundary=boundary, ledger=journal,
                             schema_validator=lambda raw: True, execution_id=execution_id,
                             process_seq=process_seq, broker=admission, end_job=None,
                             resource_reader=reader, disposal=disposal,
                             outcome=outcome or (lambda process: 0), quiescence_wait=0.0,
                             denied=denied, clock=lambda: float(next(tick)),
                             pause=lambda seconds: None, transport=transport or {}, **args)
    return SimpleNamespace(api=api, boundary=boundary, journal=journal, broker=admission,
                           launch=launch, job=boundary.create_job(execution_id))


def read_back(launch, **observed):
    """A read-back answering exactly what was requested unless `observed` says
    otherwise; the same helper shape as tests/v1/unit/test_mxc_wire_resources.py:30."""
    calls = []

    def readback(child):
        calls.append(child)
        return copy.deepcopy(facts(launch, **observed))

    launch.readback = readback
    return calls


def never_resumed(h, match):
    """What a fail-closed seam owes on a refusal: nothing ever ran, the suspended
    child was ended, the ownership fact never reached the journal, and the end is a
    quarantine rather than a completion."""
    with pytest.raises(staging.StageError, match=match) as caught:
        h.launch.start(job=h.job)
    assert h.api.events.count('resume') == 0 and h.api.events.count('kill') == 1
    assert h.api.handles == {} and h.launch.process is None
    ops = journal_ops(h.journal)
    assert 'ownership' not in ops and 'completion' not in ops and ops[-1] == 'quarantine'
    return caught.value


class NoJournal:
    """A backend with no journal to hook: the peer of the journalled fakes above, and
    the only thing that reaches the no-ledger guard of `_record_ownership`."""

    compile_policy = staticmethod(mxc.compile_policy)

    def __init__(self):
        self.hooks = []
        self.child = SimpleNamespace(pid=PID, create_time=CREATION_TIME,
                                     stdin=io.BytesIO(), stdout=io.BytesIO(),
                                     stderr=io.BytesIO())

    def spawn(self, policy, *, exe, job, **hooks):
        self.hooks.append(dict(hooks))
        return self.child


# ── 1. separation: two live executions never share one execution id (local.py:484-494)

def test_a_second_live_launch_over_the_same_execution_id_owns_nothing(tmp_path, args,
                                                                      native_parts,
                                                                      monkeypatch):
    """local.py:490 `held.execution_id == record.execution_id` - the clause of the
    separation test that has never refused anything: the closest test,
    test_two_live_launches_never_share_a_process
    (tests/v1/unit/test_mxc_wire_resources.py:118), collides two launches that both
    answer the same PID and CREATION_TIME, so the (pid, create_time) pair always refuses
    first and the id clause is never reached; the tests that do differ on the pair either
    end the peer first or move the ledger root, which skips the comparison altogether
    (tests/v1/unit/test_mxc_wire_resources.py:128 and :138). Drop that clause, or reduce
    the separation test to the pair alone, and this second launch holds an ownership
    record over the journal of a live execution and resumes: two owners of one execution,
    and the ledger of the first ends up reporting an end it never verified. The transport
    calls this seam between the membership query and the resume, and the refusal must
    land there, before the write."""
    monkeypatch.setattr(local, '_MXC_LIVE', set())        # exactly one peer, no leftovers
    first = parts(tmp_path, args)
    first.launch.start(job=first.job)
    second = parts(tmp_path, args)                        # same ledger root, same journal
    second.launch.job = second.job
    assert second.launch.journal == first.launch.journal
    before = journal_ops(second.journal)
    child = SimpleNamespace(pid=PID + 41, create_time=CREATION_TIME + 10000000)
    with pytest.raises(staging.StageError, match='shares this execution id or process'):
        second.launch._record_ownership(child)
    assert second.launch._resource is None                # nothing held, nothing registered
    assert journal_ops(second.journal) == before          # and nothing was journalled
    assert second.api.events == []                        # no create, no resume, no kill
    assert first.api.events.count('resume') == 1          # and never the first one's either
    first.launch.process.terminate()


# ── 2-4. a denied path is requested, journalled, and refused back (local.py:420-482)

def test_a_denied_path_is_requested_in_the_ownership_record(tmp_path, args, native_parts):
    """local.py:463-467: the comprehension that folds `deniedPaths` into the requested
    grants has never been entered - no test in tests/v1 compiles a denied path into a
    launch at all (tests/v1/unit/test_mxc_native.py:250 gives one to the backend, never
    to a record), so no ownership record in the suite has ever held a `deny` access.
    Remove the ('deniedPaths', 'deny') entry and the record plans a policy with no
    denial in it: the read-back comparison of local.py:479 then has nothing to differ
    over, which is the refusal below, and the journalled fact Core reconciles against
    promises fewer grants than Core asked for."""
    h = parts(tmp_path, args, denied=(DENIED,), **CLEAN)
    calls = read_back(h.launch)
    h.launch.start(job=h.job)
    assert calls == [h.launch.process] and h.api.events.count('resume') == 1
    wanted = sorted(grants(h.launch), key=lambda grant: grant['resource'])
    owner = journal_records(h.journal)[-1]
    assert owner['applied'] == wanted
    assert owner['observed']['effective_grants'] == wanted
    assert {'resource': DENIED_ID, 'access': 'deny'} in owner['applied']
    assert (DENIED_ID, 'deny') in h.launch._resource.requested_grants
    h.launch.process.terminate()


@pytest.mark.parametrize('lie', ['writable', 'read-only', 'missing'])
def test_a_denied_path_that_reads_back_as_anything_else_never_resumes(tmp_path, args,
                                                                      native_parts, lie):
    """local.py:479-481 over a deny grant: test_a_read_back_that_differs_never_resumes
    (tests/v1/unit/test_mxc_wire_resources.py:70) varies tier, backend, the effective
    list and the capability SIDs, always over a policy with nothing denied - so the one
    answer that must refuse, "Core denied this path and the container hands it out
    anyway", has never been through the seam. Invert the differences test of
    mxc_resources.py:159-164, or let an unobserved grant pass, and an execution resumes
    holding write access to a path Core refused, journalled as if it had been verified."""
    h = parts(tmp_path, args, denied=(DENIED,), **CLEAN)
    access = {'writable': 'rw', 'read-only': 'ro'}.get(lie)
    asked = grants(h.launch)
    effective = [grant for grant in asked
                 if not (lie == 'missing' and grant['resource'] == DENIED_ID)]
    if access is not None:
        effective = [{'resource': grant['resource'],
                      'access': access if grant['resource'] == DENIED_ID else grant['access']}
                     for grant in effective]
    read_back(h.launch, effective_grants=effective)
    error = str(never_resumed(h, 'differ from the request'))
    assert DENIED_ID in error
    assert {'writable': 'observed rw, requested deny',
            'read-only': 'observed ro, requested deny',
            'missing': 'requested, not observed'}[lie] in error


def test_the_intent_names_every_requested_path_and_its_digest_never_moves(tmp_path, args,
                                                                         native_parts):
    """local.py:427-429 and 413-418: test_ownership_is_durable_before_the_resume
    (tests/v1/unit/test_mxc_wire.py:335) compares the two records with each other and
    asserts `planned` is truthy (tests/v1/unit/test_mxc_wire.py:352), never that it names
    the paths Core asked for, and test_the_create_intent_is_durable_before_the_create
    (tests/v1/unit/test_mxc_wire.py:381) likewise checks truthiness only. So a denied path
    missing from the intent, or a digest taken over anything but the requested policy -
    the backend's answer, the process block alone, one recomputed after the policy moved
    - reads as covered today, while restart reconciliation reads that requested set to
    decide what was owed. The digest is asked for twice per launch (intent, then
    ownership); drop the cache of local.py:416-418 and the last assertion is what catches
    it, because the two records of one execution would then report two different
    requests."""
    h = parts(tmp_path, args, denied=(DENIED,))
    h.launch.start(job=h.job)
    intent, owner = journal_records(h.journal)
    assert intent['planned'] == [args['workspace'], args['readonly'][0], DENIED]
    assert intent['applied'] == [] and intent['observed'] == {}
    digest = hashlib.sha256(mxc_ledger._json(h.launch.policy.raw)).hexdigest()
    assert intent['requested_policy_digest'] == digest == owner['requested_policy_digest']
    h.launch.policy.raw['filesystem']['deniedPaths'].append('C:/fixture/later')
    assert h.launch._requested_digest() == digest         # requested is what Core asked for
    h.launch.process.terminate()


# ── 5. a recycled stamp is another process (local.py:484-496)

@pytest.mark.parametrize('moved', ['pid', 'create_time'])
def test_a_recycled_stamp_never_inherits_the_ownership_it_replaced(tmp_path, args,
                                                                   native_parts, monkeypatch,
                                                                   moved):
    """local.py:490-492: the pair has only ever been compared against itself -
    test_two_live_launches_never_share_a_process
    (tests/v1/unit/test_mxc_wire_resources.py:118) collides two fakes answering the same
    two constants, and every test that must not collide ends the peer first or moves the
    ledger root. Neither half of `held.pair == record.pair` has ever had to disagree
    with the other: compare the pid alone and a fresh execution is refused by a recycled
    number and never starts at all, compare the creation time alone and it is refused by
    an unrelated process, and read the pair wrongly the other way and the record that is
    written names a process that is not the child it belongs to."""
    monkeypatch.setattr(local, '_MXC_LIVE', set())        # exactly one peer, no leftovers
    live = parts(tmp_path, args)
    live.launch.start(job=live.job)                       # holds (PID, CREATION_TIME)
    pair = (PID + 7, CREATION_TIME) if moved == 'pid' else (PID, CREATION_TIME + 10000000)
    second = parts(tmp_path, args, execution_id='e2')
    second.launch._record_intent()                        # the transport's own order
    second.launch._record_ownership(SimpleNamespace(pid=pair[0], create_time=pair[1]))
    owner = journal_records(second.journal, 'e2-p1')[-1]
    assert (owner['pid'], owner['create_time']) == pair   # stamped with its own child
    assert (second.launch._resource.pid, second.launch._resource.create_time) == pair
    assert [event for event in second.api.events                # the seam creates, assigns
                if event not in ('intent', 'ownership')] == []  # and resumes nothing
    assert live.api.events.count('resume') == 1           # nothing else, ever
    live.launch.process.terminate()


# ── 6. whoever stopped the drain is who the ending blames (local.py:523-536)

@pytest.mark.parametrize('given,reason', [
    (None, 'launcher ended during the drain'),
    ('the verifier hit its read bound', 'the verifier hit its read bound'),
], ids=['no-reason-given', 'reason-given'])
def test_the_reason_a_stopped_drain_gives_is_the_reason_of_the_end(tmp_path, args,
                                                                   native_parts, given,
                                                                   reason):
    """local.py:535 `self.stop_reason or 'launcher ended during the drain'`: only
    mxc_context.py:77 and mxc_verifier.py:65 ever set `stop_reason`, and no test has, so
    the branch has only ever taken its fallback -
    test_a_cancel_ending_a_drain_quarantines_and_leaves_the_job_to_its_owner
    (tests/v1/unit/test_mxc_wire.py:583) asserts the ending, never whose stop it was, and
    would still pass if the reason were hard-coded. Drop `self.stop_reason` here and the
    audit trail of an execution Core itself stopped blames the launcher, and the
    quarantine is written over the wrong fact."""
    ticks = itertools.count(0.0, 5.0)                     # past the launcher I/O bound
    h = parts(tmp_path, args, exit_code=None, reads={1: [], 2: []},
              transport=dict(clock=lambda: float(next(ticks)), pause=lambda seconds: None),
              **CLEAN)
    h.launch.stop_reason = given
    h.launch.start(job=h.job)
    with pytest.raises(TimeoutError):
        h.launch.wait()
    assert h.launch.launcher_exit is None and h.launch.completed is None
    assert h.launch.end_state['reason'] == reason
    assert h.launch.end_state['state'] == mxc_ledger.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops
    assert h.boundary.terminated == [h.job] and h.boundary.closed == []   # Job stays open
    assert h.broker.revoked == [h.launch.execution_id]


# ── 7. the identity and the pipes a launch reports (local.py:505-517)

def test_the_streams_of_a_launch_are_the_streams_of_its_child(tmp_path, args, native_parts):
    """local.py:505, 509 and 517 are lines no test in this container has ever executed
    (the tracer in the card report: of the four accessors here, only `stdout` is read,
    by test_launcher_exit_does_not_decide_workload_outcome in
    tests/v1/integration/test_pv20_mxc_local.py). They are not decoration:
    mxc_context.py:32 makes `launch.pid` the pid of the child object the authority keeps
    live, and mxc_context.py:111 journals it as the ownership identity of the execution
    and asks `base_create_time(launch.pid)` who that process is. Forward `pid` to
    anything but this child - a stale child, the number of another execution - and the
    record Core reconciles at restart names a process this launch never owned, while the
    pipes handed to a caller (the TUI's keyboard, the reader of a launcher's reply) come
    from somewhere else. Compare all four against the child object itself, which is the
    one thing the drain is reading."""
    h = parts(tmp_path, args, **CLEAN)
    h.launch.start(job=h.job)
    child = h.launch.process
    assert h.launch.pid == child.pid == PID
    assert h.launch.stdin is child.stdin
    assert h.launch.stdout is child.stdout
    assert h.launch.stderr is child.stderr
    h.launch.process.terminate()


# ── 8. a second caller takes no second drain (local.py:532-533)

def test_a_second_wait_on_a_draining_launcher_reads_nothing_and_ends_nothing(
        tmp_path, args, native_parts):
    """local.py:532-533: AlreadyDraining is only ever asserted about a process nobody
    journalled - test_a_second_wait_on_a_draining_launch_ends_nothing
    (tests/v1/integration/test_pv20_mxc_lifecycle.py:238) asserts a bare `end_state is
    None` for a launch on an authority's shelf, and that file does not run on this
    container (27 of its 36 tests fail here before reaching any assertion). Swallow the
    re-raise as a normal end, or clear the drain flag on the way, and this second caller
    ends a launch its owner is still producing: the quarantine is written over facts that
    are still moving, the first drain's pipes are handed to a second reader, and the
    outcome is forged from an empty buffer. Checked here: not one byte read twice, the
    drain flag of the first caller untouched, every handle still open, no journal write of
    any kind, no revoked grant, no ended Job - and the launch intact for its owner."""
    h = parts(tmp_path, args, **CLEAN)
    h.launch.start(job=h.job)
    h.launch.process._draining = True                     # the drain thread owns it
    with pytest.raises(mxc_native.AlreadyDraining, match='already draining'):
        h.launch.wait()
    assert h.api.reads == {1: [b''], 2: [b'']}            # not one byte was read twice
    assert h.launch.process._draining is True             # still the first caller's drain
    assert set(h.api.handles.values()) >= {'parent0', 'parent1', 'parent2'}
    assert h.launch.completed is None and h.launch.launcher_exit is None
    assert h.launch.bound is None and h.launch.end_state is None
    assert journal_ops(h.journal) == ['intent', 'ownership']    # neither end was written
    assert h.broker.revoked == [] and h.boundary.terminated == [] and h.boundary.closed == []
    assert 'kill' not in h.api.events                     # the container stays Core's to end
    h.launch.process._draining = False                    # the drain owner comes back
    assert h.launch.wait() == 0                           # and its launch is intact
    assert h.launch.end_state['state'] == mxc_ledger.DEAD_CLEAN


# ── 9. terminate stops the child and never ends its own launch (local.py:519-521)

def test_terminate_ends_the_child_and_leaves_the_ending_to_its_owner(tmp_path, args,
                                                                    native_parts):
    """local.py:520-521, the `if self.process is not None` arm: the only test of
    `terminate()` is test_terminate_before_start_is_a_no_op
    (tests/v1/integration/test_pv20_mxc_local.py:285) on a launch that never spawned a
    child, so the line has only ever run as its no-child guard, and a caller with a live
    container has never asked for a stop. Run the ending from here instead of stopping the
    child (or turn terminate() into cancel()) and a caller that only wanted the process
    stopped revokes the broker grant, ends Core's Job, writes the quarantine and forges an
    end the owner of the launch never asked for."""
    h = parts(tmp_path, args, **CLEAN)
    h.launch.start(job=h.job)
    h.launch.terminate()
    assert h.api.events.count('kill') == 1
    assert h.launch.process.launcher_exit == 1            # the child is the stopped thing
    assert h.api.events.count('resume') == 1              # nothing new ran either
    assert h.launch.end_state is None and h.launch.completed is None
    assert h.broker.revoked == [] and h.boundary.terminated == [] and h.boundary.closed == []
    assert journal_ops(h.journal) == ['intent', 'ownership']    # nothing was ended
    h.launch.terminate()                                  # a second stop stops nothing
    assert h.api.events.count('kill') == 1
    assert h.launch.cancel(reason='the host asked', outcome=0)['state'] == mxc_ledger.DEAD_CLEAN


# ── 10. a backend with no journal is promised no ownership fact (local.py:438-443)

def test_a_launch_with_no_journal_writes_no_ownership_fact(args, native_parts):
    """local.py:441-442: `_record_ownership` has only ever run with a ledger - the
    transport is handed the hook by every journalled launch (local.py:408-411) and every
    test of it uses the journalled fixture, while the unjournaled launches of
    test_a_backend_without_a_ledger_is_asked_for_no_ownership_hook
    (tests/v1/integration/test_pv20_mxc_local.py:198) stop at `wait()` and never reach
    this seam. Remove the guard and an unjournaled launch, whose journal name is None, is
    recorded as an execution named None, enters `_separate` as an owner no restart
    reconciliation can ever reach, or dies building a record it was never going to
    write."""
    backend = NoJournal()
    launch = local.MxcLaunch(backend=backend, outcome=lambda process: 0, **args)
    launch.start(job={'core': 'holds the job'})
    assert backend.hooks == [{}]                          # the seam was never promised
    assert launch._record_ownership(backend.child) is None
    assert launch._resource is None                       # it owns nothing, holds nothing
    assert launch.end_state is None                       # and nothing was ended on the way


# ── below the cut: a raise whose ending is asserted elsewhere, hardened (540-543, 562)

@pytest.mark.parametrize('error', [OSError('the outcome reader died'), KeyboardInterrupt()],
                         ids=['oserror', 'keyboard-interrupt'])
def test_an_outcome_reader_that_raises_ends_the_execution_unverified(tmp_path, args,
                                                                     native_parts, error):
    """local.py:542-544 is reached today, by
    test_a_reader_that_is_interrupted_still_ends_the_launch
    (tests/v1/unit/test_mxc_wire_outcome.py:92), which is why this one is below the cut.
    It is kept because it is the other half of the same ending: the raise there comes
    from a *workload* reader behind `bind_outcome`, which turns an Exception into a state
    instead of a raise, and the Core-owned outcome callable of local.py:562 has only ever
    been called by tests that let it answer. Let a raise from the callable through
    local.py:542 without an ending, or end it as a clean exit, and a launch whose outcome
    nobody could read keeps its broker grant and its open Job, its journal carries no
    quarantine, and the caller never learns the reader died."""
    h = parts(tmp_path, args, **CLEAN)
    h.launch.outcome = lambda process: (_ for _ in ()).throw(error)
    h.launch.start(job=h.job)
    with pytest.raises(type(error)):
        h.launch.wait()
    assert h.launch.bound is None and h.launch.completed is None
    assert h.launch.end_state['reason'] == 'the outcome reader failed'
    assert h.launch.end_state['state'] == mxc_ledger.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops
    assert h.boundary.closed == [] and h.boundary.terminated == [h.job]
    assert h.broker.revoked == [h.launch.execution_id]


# ── below the cut: a stop already forwarded elsewhere (local.py:529-530)

@pytest.mark.parametrize('stop_after', [3, None],
                         ids=['caller-stops-the-drain', 'nobody-stops-the-drain'])
def test_the_stop_a_caller_asks_for_is_carried_into_the_drain(tmp_path, args, native_parts,
                                                             stop_after):
    """local.py:530, the `cancelled is not None` arm. Below the cut because the branch is
    not uncovered: test_a_cancel_ending_a_drain_quarantines_and_leaves_the_job_to_its_owner
    (tests/v1/unit/test_mxc_wire.py:583) does hand `wait` a `cancelled=lambda: True` and
    does see the drain refused. What that leaves unasked is whether the drain ever
    *consulted* the caller - it asserts the ending, which the same ending arrives at if
    the drain simply reaches its bound - so dropping the forwarding keeps that suite
    green. Here the callback counts its own consultations and the control beside it is the
    same drain with nobody asking, which is the one that reaches the bound: the pair pins
    that the stop the caller asked for is the stop the transport obeyed."""
    ticks = itertools.count(0.0, 0.2)                     # 0.2s a turn, 1.0s of bound
    asked = []

    def stop_requested():
        asked.append(1)                                   # the drain asks once per turn
        return stop_after is not None and len(asked) >= stop_after

    h = parts(tmp_path, args, exit_code=None, reads={1: [], 2: []},
              transport=dict(clock=lambda: float(next(ticks)), pause=lambda seconds: None),
              **CLEAN)
    h.launch.start(job=h.job)
    if stop_after is None:
        with pytest.raises(TimeoutError):
            h.launch.wait()
        assert asked == []                                # nothing was ever asked
    else:
        with pytest.raises(mxc.MxcUnavailable, match='launcher cancelled during drain'):
            h.launch.wait(cancelled=stop_requested)
        assert len(asked) == stop_after                   # asked, and heard, on the third
    assert h.launch.completed is None and h.launch.bound is None
    assert h.launch.end_state['reason'] == 'launcher ended during the drain'
    assert h.launch.end_state['state'] == mxc_ledger.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops
    assert h.boundary.terminated == [h.job] and h.boundary.closed == []   # Job stays open
    assert h.broker.revoked == [h.launch.execution_id]
    assert h.api.handles == {}                            # the stopped drain left no pipe
