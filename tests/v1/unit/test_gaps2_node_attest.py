"""T-1002: the highest-risk uncovered branches of archeus/node/attest.py lines 1-245.

Source slice: `archeus/node/attest.py:1-245` (the whole pure attestor: `attest_owner`,
`attest_peer`, `_attest`, `binding_valid`, `_alive_failures`, `_user_failures`,
`_launcher_missing`, `_finite`). Definitions and imports outside that slice are
read-only context; branch ownership stays inside it, including for the two endpoints.

Selected branches (ranked, with evidence, in /work/QWEN-DONE-T-1002.md; the numbering here is
the same as the report's):
  1 `attest_owner` must never take the user-by-exclusion path (attest.py:141-143 with :82)
  2 `_user_failures` CORE_DESCENDANT on the recheck of a user binding, with its reason
    pinned, plus the accept-time denial of a process with a Core ancestor
    (attest.py:229-230)
  3 the execution half of the recheck reads `in_core_job is not True` (attest.py:200)
  4 the age bound is inclusive: `now - accepted_at == max_age_s` is still the accept-time
    answer, a hair past it fails closed before any reader is consulted (attest.py:183)
  5 the recheck chooses its rule set from the binding's own kind bit, and both kinds are
    driven through the same recheck with their exact reason tuples (attest.py:196)
  6 creation time on a USER binding: the recycle reason, and an unreadable time never
    double-reported as a recycle (attest.py:193-195)
  7 every fact must be exactly True/False: a truthy non-bool `alive`, `in_core_job`,
    `same_session` or `outside_core` is no evidence, at accept, at the recheck and on the
    execution side (attest.py:131, 138, 211, 220-221, 227-228, 229-230)
  8 `_user_failures` OTHER_SESSION and INSIDE_CORE_JOB at the recheck, with the reason
    pinned (attest.py:220-221, 227-228)
  9 `_user_failures` LAUNCHER_PRESENT at the recheck and the case-folding ancestry match
    (attest.py:223-224, 238)
 10 `_user_failures` MALFORMED (attest.py:225-226, 235-237): unreadable ancestry must
    never read as "no user failure", at accept or at recheck

Also included, where the existing suite was already nearer (see the report's last section):
the user entry's reader/clock error paths (attest.py:125-128, 145-150, 179-191), the
non-finite `creation_time` at the user entry (attest.py:133), the negative age for a user
binding (attest.py:183, `0 <=`), and the all-failures-at-once reason order.

Everything is the pure attestor over seam-faked OS calls: the port -> owner map, the
PID -> observation table and the clock are all injected callables, so no DLL, no Windows
API, no socket, no real process and no network is touched and the assertions hold
unchanged on Linux and Windows. No sleeps, no temp files, no environment reads, no
assertion on OS error text or on live threads. The file is independent: it imports no
other test module and nothing here depends on queue order.
"""

import math

import pytest

from archeus.node.attest import (
    CORE_DESCENDANT,
    CREATION_TIME_MISMATCH,
    CREATION_TIME_UNREADABLE,
    DEAD,
    DEFAULT_LAUNCHER,
    DEFAULT_MAX_AGE_S,
    EXPIRED,
    INSIDE_CORE_JOB,
    LAUNCHER_PRESENT,
    LAUNCHER_UNPROVEN,
    MALFORMED,
    OTHER_SESSION,
    OUTSIDE_CORE_JOB,
    READER_ERROR,
    AttestResult,
    ProcessBinding,
    ProcessInfo,
    PeerOwner,
    attest_owner,
    attest_peer,
    binding_valid,
)

PORT = 54321
PID = 4124
CT = 100.0                                    # creation time of the bound instance
T0 = 1000.0                                   # fake clock base
_UNSET = object()                             # "no override" vs "override to None"

# The peer the exclusion path is supposed to accept: alive, a readable creation time, in
# no Core Job, no launcher ancestor, Core's own session, and positively not Core or a
# descendant of Core. Every one of those facts is a separate check inside this slice.
USER = ProcessInfo(alive=True, creation_time=CT, ancestors=('explorer.exe',),
                   in_core_job=False, same_session=True, outside_core=True)
# The same process seen as an execution: under the launcher, inside a Core Job.
EXEC = ProcessInfo(alive=True, creation_time=CT, ancestors=(DEFAULT_LAUNCHER, 'services.exe'),
                   in_core_job=True, same_session=True, outside_core=False)
# Under the launcher but not descended from Core: an execution-shaped process in no Job.
LAUNCHER_PEER = ProcessInfo(alive=True, creation_time=CT,
                            ancestors=(DEFAULT_LAUNCHER, 'services.exe'),
                            in_core_job=False, same_session=True, outside_core=True)
# A child of Core that sits in no Job: exactly what the exclusion path exists to catch.
CORE_CHILD = ProcessInfo(alive=True, creation_time=CT,
                         ancestors=(DEFAULT_LAUNCHER, 'services.exe'),
                         in_core_job=False, same_session=True, outside_core=False)


class Table:
    """The whole outside world of the attestor: one peer port, one PID, one clock."""

    def __init__(self, info=USER):
        self.info = info
        self.owner = PID
        self.owner_error = None
        self.process_error = None
        self.now = T0
        self.clock_answer = _UNSET
        self.events = []                        # 'owner' / 'process', in call order
        self.ports = []
        self.pids = []

    def resolve_owner(self, port):
        self.events.append('owner')
        self.ports.append(port)
        if self.owner_error is not None:
            raise self.owner_error
        return PeerOwner(pid=self.owner if port == PORT else None)

    def read_process(self, pid):
        self.events.append('process')
        self.pids.append(pid)
        if self.process_error is not None:
            raise self.process_error
        return self.info if pid == PID else None

    def clock(self):
        return self.now if self.clock_answer is _UNSET else self.clock_answer

    def fork(self):
        """An identical table with its own counters, for a control beside a case."""
        clone = Table(self.info)
        clone.now = self.now
        return clone


def _peer(table, **overrides):
    kwargs = dict(remote_port=PORT, resolve_owner=table.resolve_owner,
                  read_process=table.read_process, clock=table.clock)
    kwargs.update(overrides)
    return attest_peer(**kwargs)


def _owner(table, **overrides):
    kwargs = dict(remote_port=PORT, resolve_owner=table.resolve_owner,
                  read_process=table.read_process, clock=table.clock)
    kwargs.update(overrides)
    return attest_owner(**kwargs)


def _recheck(table, binding, **overrides):
    kwargs = dict(read_process=table.read_process, clock=table.clock)
    kwargs.update(overrides)
    return binding_valid(binding, **kwargs)


def _user_binding(table):
    """A binding to the current observation, taken through the real accept path, with
    the accept-time counters put back the way they were."""
    result = _peer(table)
    assert result.ok and result.failures == ()
    assert result.binding is not None and result.binding.core_job_at_accept is False
    del table.events[:], table.ports[:], table.pids[:]
    return result.binding


def _binding(core_job_at_accept):
    return ProcessBinding(remote_port=PORT, pid=PID, creation_time=CT, accepted_at=T0,
                          core_job_at_accept=core_job_at_accept)


def _exec_binding(table):
    """A binding to the execution observation, taken through the real accept path."""
    result = _owner(table)
    assert result.ok and result.failures == ()
    assert result.binding is not None and result.binding.core_job_at_accept is True
    del table.events[:], table.ports[:], table.pids[:]
    return result.binding


def _refused(result):
    """The only shape a refusal may ever have: no verdict, no partial binding, a reason."""
    assert isinstance(result, AttestResult)
    assert result.ok is False
    assert result.binding is None
    assert result.failures                                      # never a silent refusal


# ── report 1: the execution entry point never takes the user path (attest.py:141-143) ──

def test_the_execution_entry_point_never_attests_a_process_the_user_path_would_accept():
    """`attest_owner` is `_attest(user_allowed=False)`, and it is the entry the server
    uses for every accept. A peer that satisfies every exclusion check must still be
    refused by it, or Core's execution gate would start binding user processes: drop the
    `user_allowed` conjunct of attest.py:141 (or let `attest_owner` pass True) and this
    refusal turns into a binding."""
    table = Table(USER)
    assert _peer(table.fork()).binding.core_job_at_accept is False      # same facts, user

    _refused(_owner(table))
    assert table.events == ['owner', 'process']                 # one lookup, one read
    assert table.ports == [PORT] and table.pids == [PID]
    assert _owner(table).failures == (LAUNCHER_UNPROVEN, OUTSIDE_CORE_JOB)


# ── report 2: the USER exclusion rejects Core ancestry (attest.py:223-224, 229-230) ──

def test_a_user_binding_whose_peer_turns_out_to_be_core_is_refused_by_core_descendant():
    """The binding was issued while the reader said `outside_core=True`; when the same
    PID is later reported as Core itself, or as Core's child, the recheck must refuse
    with CORE_DESCENDANT and nothing else. Delete attest.py:229-230 and the very same
    recheck comes back ok, so the recycled identity of a Core process keeps its
    user-level validity."""
    table = Table(USER)
    binding = _user_binding(table)
    table.info = USER._replace(outside_core=False)
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (CORE_DESCENDANT,)
    assert table.events == ['process']                          # never re-attested


def test_a_user_binding_whose_peer_is_a_core_child_reports_both_user_failures_in_order():
    """A Core child in no Core Job trips the launcher check and the Core-ancestry check
    at once. The refusal has to name both, in the order the checks run, because the
    caller reports `failures[0]` to the audit log: returning early after the first
    append, or dropping either of them, changes this tuple."""
    table = Table(USER)
    binding = _user_binding(table)
    table.info = CORE_CHILD
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (LAUNCHER_PRESENT, CORE_DESCENDANT)


def test_a_process_with_a_core_ancestor_and_no_other_doubt_is_still_not_the_user():
    """Accept side of the same rule, and the whole reason `outside_core` exists: every
    other fact perfect (alive, readable time, no Job, no launcher, Core's session) is
    still not the user if the reader reports a Core ancestor. Remove the check and this
    peer is bound as the user, which is the T-17 hole the field was added for."""
    table = Table(USER._replace(outside_core=False))
    result = _peer(table)
    _refused(result)
    assert result.binding is None
    assert table.events == ['owner', 'process']                 # one read, no second pass
    # accept reports the execution list; CORE_DESCENDANT is observable at the recheck
    assert _peer(table).failures == (LAUNCHER_UNPROVEN, OUTSIDE_CORE_JOB)
    assert _peer(Table(USER)).ok is True                        # the control binds


# ── report 7: only True and False are answers (attest.py:131, 138, 200, 211, 220-230) ──

@pytest.mark.parametrize('field,value,code', [
    ('alive', 1, DEAD),
    ('in_core_job', 1, INSIDE_CORE_JOB),
    ('same_session', 1, OTHER_SESSION),
    ('outside_core', 1, CORE_DESCENDANT),
    ('same_session', 'yes', OTHER_SESSION),
    ('outside_core', None, CORE_DESCENDANT),
    ('alive', None, DEAD),
], ids=['alive 1', 'job 1', 'session 1', 'outside 1', 'session yes', 'outside none',
        'alive none'])
def test_a_user_fact_that_is_merely_truthy_binds_nothing_at_accept_or_at_the_recheck(
        field, value, code):
    """`alive is True`, `in_core_job is False`, `same_session is True`, `outside_core is
    True`: a reader that answers 1 or 'yes' instead of True, or answers nothing at all
    (`None`, the unknown outside_core of the card's probe), has proven nothing, and the
    peer is neither an execution nor the user. Rewrite any of attest.py:131, 220, 227 or
    229 as a plain truth test and the same observation binds."""
    table = Table(USER._replace(**{field: value}))
    _refused(_peer(table))
    assert table.pids == [PID]                                  # and still only one read

    holder = Table(USER)
    binding = _user_binding(holder)
    holder.info = USER._replace(**{field: value})
    _refused(_recheck(holder, binding))
    assert _recheck(holder, binding).failures == (code,)


@pytest.mark.parametrize('field,value,code', [
    ('in_core_job', 1, OUTSIDE_CORE_JOB),
    ('in_core_job', 'yes', OUTSIDE_CORE_JOB),
    ('alive', 1, DEAD),
], ids=['job 1', 'job yes', 'alive 1'])
def test_an_execution_fact_that_is_merely_truthy_never_opens_the_job_or_the_clock(
        field, value, code):
    """The execution half of the same boundary. `in_core_job=1` was never proven inside a
    Core Job and `alive=1` was never proven alive, so no binding may issue; inverting
    attest.py:131 or :138 into a truth test issues exactly the binding this refuses."""
    table = Table(EXEC._replace(**{field: value}))
    result = _owner(table)
    _refused(result)
    assert result.failures == (code,)
    assert _owner(Table(EXEC)).binding.core_job_at_accept is True       # the control binds


def test_a_user_binding_kept_alive_only_by_truthy_flags_is_refused_at_the_recheck():
    """The recheck half again, on a binding that is already held: as soon as the reader
    degrades to truthy non-bools the binding is gone, and it goes without a partial
    pass. The last case pins that two simultaneous user failures are two reasons."""
    table = Table(USER)
    binding = _user_binding(table)
    table.info = USER._replace(alive=1)
    _refused(_recheck(table, binding))
    assert _recheck(table, binding).failures == (DEAD,)
    table.info = USER._replace(same_session='yes', outside_core=1)
    _refused(_recheck(table, binding))
    assert _recheck(table, binding).failures == (OTHER_SESSION, CORE_DESCENDANT)


@pytest.mark.parametrize('in_core_job', [1, 'yes'], ids=['job 1', 'job yes'])
def test_an_execution_binding_whose_job_membership_goes_merely_truthy_is_refused(in_core_job):
    """The execution half of the recheck boundary: a bound execution the reader can no
    longer put inside a Core Job (`in_core_job` answering 1 is not answering True) has
    lost the one fact holding its PID to Core's executions, and must not stay valid.
    Every existing job-membership case flips the flag to False, so turning attest.py:200
    into a truth test is caught here and nowhere else."""
    table = Table(EXEC)
    binding = _exec_binding(table)
    table.info = EXEC._replace(in_core_job=in_core_job)
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (OUTSIDE_CORE_JOB,)
    assert _recheck(Table(EXEC), _exec_binding(Table(EXEC))).ok is True    # control holds


@pytest.mark.parametrize('creation_time', [None, float('nan'), float('inf'), '100.0', True],
                         ids=['none', 'nan', 'inf', 'str', 'true'])
def test_an_execution_peer_with_an_unreadable_creation_time_is_bound_by_neither_entry(
        creation_time):
    """The creation time is what makes a PID a particular instance; `nan`, `inf`, text or
    `True` is not one, and the peer is then neither an execution nor the user. The
    existing unreadable-time tests all go through `attest_owner`, so the user entry point
    used here is the one that could otherwise hand out a binding naming no instance: with
    the finiteness test off attest.py:133 the Job-shaped peer below is bound."""
    _refused(_peer(Table(EXEC._replace(creation_time=creation_time))))
    assert _peer(Table(EXEC._replace(creation_time=creation_time))).failures == \
        (CREATION_TIME_UNREADABLE,)
    _refused(_owner(Table(EXEC._replace(creation_time=creation_time))))
    assert _owner(Table(EXEC)).binding.core_job_at_accept is True           # control binds


def test_every_user_failure_at_once_is_reported_at_once():
    """No partial pass inside the exclusion list: all four user failures together, in the
    order the checks run (Job, launcher, session, Core ancestry). An early `return` in
    `_user_failures`, or a check that overwrites instead of appends, shortens this."""
    table = Table(USER)
    binding = _user_binding(table)
    table.info = USER._replace(in_core_job=True, ancestors=(DEFAULT_LAUNCHER,),
                               same_session=False, outside_core=False)
    _refused(_recheck(table, binding))
    assert _recheck(table, binding).failures == (INSIDE_CORE_JOB, LAUNCHER_PRESENT,
                                                 OTHER_SESSION, CORE_DESCENDANT)


# ── report 9: the launcher ancestor on the user path (attest.py:223-224) ──

def test_a_user_binding_that_gains_a_launcher_ancestor_is_refused_as_launcher_present():
    """A peer that starts out beside Core and later has `wxc-exec` above it is a process
    Core spawned, and the recheck must say LAUNCHER_PRESENT and nothing else. The
    ancestry match is case-folded, so the uppercase spelling below pins both the code
    and the fold: take `.lower()` off attest.py:238 and the answer becomes
    LAUNCHER_UNPROVEN, which tells the operator a different story."""
    table = Table(USER)
    binding = _user_binding(table)
    table.info = USER._replace(ancestors=(DEFAULT_LAUNCHER.upper(), 'services.exe'))
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (LAUNCHER_PRESENT,)
    assert table.events == ['process']


def test_a_process_under_the_launcher_but_in_no_core_job_is_attested_as_nothing():
    """Accept side of LAUNCHER_PRESENT: in no Core Job (so not an execution) with the
    launcher above it (so not the user) is the orphaned-execution shape, and it must
    bind nothing. Delete attest.py:223-224 and this peer is attested as the user, which
    is how a helper Core spawned would get user privileges."""
    table = Table(LAUNCHER_PEER)
    result = _peer(table)
    _refused(result)
    assert result.failures == (OUTSIDE_CORE_JOB,)               # the execution list wins
    assert _peer(Table(LAUNCHER_PEER._replace(ancestors=('explorer.exe',)))).ok is True


# ── report 6: wrong creation time on a user binding (attest.py:193-195) ──

def test_a_recycled_pid_never_inherits_a_user_binding():
    """The PID survived into a new instance: same number, new creation time, every user
    fact still perfect. Only the creation time separates the two, so the recheck must
    refuse with CREATION_TIME_MISMATCH and consult no owner table on the way out. Remove
    the `!=` clause of attest.py:194 and the recycled process keeps the user's binding."""
    table = Table(USER)
    binding = _user_binding(table)
    table.info = USER._replace(creation_time=CT + 1.0)
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (CREATION_TIME_MISMATCH,)
    assert table.events == ['process']                          # never re-attested


@pytest.mark.parametrize('creation_time', [None, float('nan'), float('inf'), '100.0', True],
                         ids=['none', 'nan', 'inf', 'str', 'true'])
def test_a_user_binding_with_an_unreadable_creation_time_is_not_reported_as_recycled(
        creation_time):
    """An unreadable time is "no evidence", not "a different instance": the recycle probe
    is suppressed so no caller is ever told a PID was reused when nothing proves it, and
    the peer is refused either way. Drop the suppression on attest.py:194 and the tuple
    gains a second, invented reason; drop the finiteness test and it comes back ok."""
    table = Table(USER)
    binding = _user_binding(table)
    table.info = USER._replace(creation_time=creation_time)
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (CREATION_TIME_UNREADABLE,)


# ── report 8: the session check on the user path (attest.py:227-228) ──

def test_a_user_binding_that_left_cores_session_is_refused_as_other_session():
    """A peer that changes session after accept belongs to somebody else; the recheck
    must refuse with OTHER_SESSION and no binding. Remove attest.py:227-228 and the
    binding stays valid, letting another session's process effect a privileged call as
    the user."""
    table = Table(USER)
    binding = _user_binding(table)
    table.info = USER._replace(same_session=False)
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (OTHER_SESSION,)
    assert table.events == ['process']                          # no re-attestation


# ── report 4/5: the age bound, and both kinds through one recheck (attest.py:183, 196) ──

@pytest.mark.parametrize('core_job_at_accept', [True, False], ids=['execution', 'user'])
def test_a_binding_exactly_at_its_maximum_age_is_still_the_accept_time_answer(
        core_job_at_accept):
    """`0 <= now - accepted_at <= max_age_s` is closed at the top: exactly at the limit
    the caller still holds the answer it was given at accept, a hair past it the answer
    is stale and the process table is never even read. Every existing expiry case sits at
    1.0 or 10.0 against a 2.0 limit, so turning `<=` into `<` fails nothing but this."""
    table = Table(EXEC if core_job_at_accept else USER)
    binding = _binding(core_job_at_accept)
    table.now = T0 + DEFAULT_MAX_AGE_S                          # exactly at the limit
    assert _recheck(table, binding) == AttestResult(True, binding, ())
    table.now = T0 + DEFAULT_MAX_AGE_S + 1e-6                   # a hair past it
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (EXPIRED,)
    assert table.events == ['process']                          # the last one was accept


@pytest.mark.parametrize('core_job_at_accept', [True, False], ids=['execution', 'user'])
def test_a_binding_from_the_future_is_expired_for_both_kinds_of_peer(core_job_at_accept):
    """The bottom of the same bound: a clock that rewound below the accept time makes the
    answer untrustworthy, and both kinds of binding fail closed before any reader is
    consulted at all. Invert `0 <=` on attest.py:183 and a rewound clock reads as fresh."""
    table = Table(EXEC if core_job_at_accept else USER)
    binding = _binding(core_job_at_accept)
    table.now = T0 - 1e-6
    result = _recheck(table, binding)
    _refused(result)
    assert result.failures == (EXPIRED,)
    assert table.events == []                                   # no reader consulted


# ── extras: the user paths fail closed, without raising (attest.py:125-128, 145-150, 179-191) ──

def test_a_user_peer_whose_owner_or_process_cannot_be_read_is_refused_not_crashed():
    """`attest_peer` is the entry that decides "this is the user", so its own failure
    modes have to answer with a refusal: a raising owner reader, a table that names no
    process and a process reader that answers something that is not a `ProcessInfo` all
    fail closed, none of them raises, none of them issues a binding."""
    table = Table(USER)
    table.owner_error = OSError('the tcp table query failed')
    assert _peer(table) == AttestResult(False, None, (READER_ERROR,))
    table = Table(None)                                         # the PID names nothing
    assert _peer(table) == AttestResult(False, None, (MALFORMED,))
    table.info = 'alive'
    assert _peer(table) == AttestResult(False, None, (MALFORMED,))


def test_a_user_binding_whose_recheck_reader_fails_is_refused_not_crashed():
    """The re-check runs before every privileged effect, so its own failure modes must be
    refusals: a raising reader, a vanished process, a clock that answers text (which
    `float()` would raise on, outside the reader's own exception contract) and a clock
    that answers NaN. Narrow any of these `except Exception` clauses to `OSError` and the
    ValueError escapes into the connection instead of refusing it."""
    table = Table(USER)
    binding = _user_binding(table)
    table.process_error = OSError('the process died under the query')
    assert _recheck(table, binding) == AttestResult(False, None, (READER_ERROR,))
    table.process_error = None
    table.info = None
    assert _recheck(table, binding) == AttestResult(False, None, (MALFORMED,))
    table.info = USER
    table.clock_answer = 'not-a-time'
    assert _recheck(table, binding) == AttestResult(False, None, (READER_ERROR,))
    table.clock_answer = math.nan
    assert _recheck(table, binding) == AttestResult(False, None, (EXPIRED,))


def test_a_user_accept_whose_clock_cannot_be_read_issues_no_binding():
    """`accepted_at` is the timestamp every later re-check measures itself against, so a
    clock that will not answer as a number refuses the accept rather than storing a
    meaningless instant: a non-number, NaN and an infinity all refuse, and the same
    healthy table binds. Let attest.py:149 pass a NaN through and the binding this
    refuses would never age out, since every later age test against it is false."""
    table = Table(USER)
    table.clock_answer = 'not-a-time'
    assert _peer(table) == AttestResult(False, None, (READER_ERROR,))
    table.clock_answer = math.nan
    assert _peer(table) == AttestResult(False, None, (READER_ERROR,))
    table.clock_answer = math.inf
    assert _peer(table) == AttestResult(False, None, (READER_ERROR,))
    table.clock_answer = _UNSET
    assert _peer(table).ok is True                              # the control binds


# ── report 10: unreadable ancestry on the user path (attest.py:225-226) ──

@pytest.mark.parametrize('shape', ['str', 'list', 'mixed', 'launcher'],
                         ids=['str', 'list', 'mixed', 'launcher'])
def test_a_user_peer_with_unreadable_ancestry_is_never_bound(shape):
    """`ancestors` that is not a tuple of str (or a launcher the caller cannot name)
    proves nothing, and "nothing proven" is not "no user failure": without the MALFORMED
    append of attest.py:225-226 the user list comes back empty and this peer is bound as
    the user, so an unreadable ancestry becomes a privilege instead of a refusal."""
    ancestors = {'str': DEFAULT_LAUNCHER, 'list': [DEFAULT_LAUNCHER],
                 'mixed': (DEFAULT_LAUNCHER, 7)}.get(shape)
    overrides = {'launcher': None} if shape == 'launcher' else {}
    table = Table(USER._replace(ancestors=ancestors) if ancestors is not None else USER)
    _refused(_peer(table, **overrides))
    assert _peer(table, **overrides).failures == (MALFORMED, OUTSIDE_CORE_JOB)
    control = _peer(Table(USER), **overrides)
    assert control.ok is (shape != 'launcher')                  # no name, no attestation


@pytest.mark.parametrize('shape', ['str', 'mixed', 'launcher'], ids=['str', 'mixed', 'launcher'])
def test_a_user_binding_with_unreadable_ancestry_is_refused_as_malformed(shape):
    """The recheck half of the same rule, where the reason code is the only observable: a
    bound user whose ancestry turns unreadable is refused with MALFORMED alone, because
    no other check in `_user_failures` could say anything about it. Delete the append and
    the recheck returns the binding as still valid."""
    table = Table(USER)
    binding = _user_binding(table)
    overrides = {}
    if shape == 'launcher':
        overrides['launcher'] = None
    else:
        ancestors = {'str': DEFAULT_LAUNCHER, 'mixed': (DEFAULT_LAUNCHER, 7)}[shape]
        table.info = USER._replace(ancestors=ancestors)
    result = _recheck(table, binding, **overrides)
    _refused(result)
    assert result.failures == (MALFORMED,)
