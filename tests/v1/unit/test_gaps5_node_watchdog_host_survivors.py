"""T-1245: gap tests for the survivor-retry slice of archeus/node/mxc_watchdog_host.py.

Source slice under test: archeus/node/mxc_watchdog_host.py lines 165-210 inclusive
(round-8 slice at tip 6bbd3b44; this container has no git, so the lines were pinned
by direct read of the file in this checkout). Fakes only: an in-memory process
table, injected identity_reader / terminate / engage_sentinel / journals and the
temp-directory channel and ledger. No real process, sentinel, native call, clock
wait, thread or subprocess.

Selected branches (file:line - what a removal or inversion of the branch would let):
- archeus/node/mxc_watchdog_host.py:196-197  a malformed journal or a first op
  other than OWNED_OPS denies the kill even when the process table still matches
  the record: no terminate, no sentinel, process left alive in the table.
- archeus/node/mxc_watchdog_host.py:199  a journal that names the same pid at
  another create_time denies the kill before terminate: no pid-only adoption.
- archeus/node/mxc_watchdog_host.py:205-207  the survivor retry asks the journal
  again and refuses a job whose ownership changed after registration: no
  terminate of the newly unowned process, while the pass keeps going.
- archeus/node/mxc_watchdog_host.py:208-210  the kill engages the sentinel once,
  before its first termination, only when _core_seen is True; False/None engages
  nothing and infers no sentinel; only terminate() answering the bool True is a
  success (a truthy non-bool is not).
- archeus/node/mxc_watchdog_host.py:171  a survivor whose pid was reused with a
  different create_time is skipped without a kill, and the pass still continues
  to kill the next live survivor.
- archeus/node/mxc_watchdog_host.py:165-166  with no dog at all the workloads are
  empty: _unstopped still verifies Core's identity and nothing else, and
  _retry_survivors makes no observation and no call.
- archeus/node/mxc_watchdog_host.py:178-179  a still-live Core returns the Core
  reason before any workload is read (no workload claim from the short circuit).
- archeus/node/mxc_watchdog_host.py:180-185  None means every observed original
  is absent or reused; no replacement process is killed or removed on the way.
- archeus/node/mxc_watchdog_host.py:173  an identity read that raises on one
  survivor does not stop the check and the kill of the next survivor.
- archeus/node/mxc_watchdog_host.py:183-184  a raising workload read after the
  Core is gone names the exception type and is never a verified (None) stop.

Closest existing coverage compared before selecting (read, never copied):
tests/v1/unit/test_mxc_watchdog_host.py, tests/v1/unit/test_gaps2_node_mxc_watchdog.py
and tests/v1/unit/test_mxc_watchdog.py. These are seam tests, not measured coverage.
"""

from types import SimpleNamespace

import pytest

from archeus.node import mxc_heartbeat as hb, mxc_ledger, mxc_watchdog as wd
from archeus.node import mxc_watchdog_host as host_mod

CORE_PID, CORE_TIME = 900, 9000
PID, CREATION_TIME = 4129, 133100000000000000
DEADLINE = 10.0
DIGEST = 'a' * 64
JOB_TWO = ('e2-p1', PID + 1, CREATION_TIME + 1)


class SurvivorTableBusy(OSError):
    """Named fake: the type name must reach the 'stop not verified' report."""


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


class World:
    """The process table, the sentinel and the terminate calls, in the order they happened."""

    def __init__(self):
        self.table = {CORE_PID: CORE_TIME}
        self.events = []
        self.sentinel = True
        self.terminated = True
        self.survivors = set()

    def identity(self, pid):
        return self.table.get(pid)

    def terminate(self, pid, create_time):
        self.events.append(('terminate', pid, create_time))
        if (self.terminated and self.table.get(pid) == create_time
                and pid not in self.survivors):
            del self.table[pid]
        return self.terminated

    def engage(self):
        self.events.append(('sentinel',))
        if isinstance(self.sentinel, Exception):
            raise self.sentinel
        return self.sentinel


@pytest.fixture
def env(tmp_path):
    clock, world = Clock(), World()
    ledger = mxc_ledger.Ledger(tmp_path / 'ledger')
    core_side = hb.Channel(tmp_path / 'chan')
    host_side = hb.Channel(tmp_path / 'chan')
    host = host_mod.WatchdogHost(channel=host_side, clock=clock, deadline_s=DEADLINE,
                                 core=(CORE_PID, CORE_TIME), identity_reader=world.identity,
                                 terminate=world.terminate, engage_sentinel=world.engage,
                                 journals=ledger.journals)
    return SimpleNamespace(clock=clock, world=world, ledger=ledger, core=core_side,
                           host_channel=host_side, host=host, tmp=tmp_path)


def own(env, name, pid=PID, create_time=CREATION_TIME, *, live=True):
    env.ledger.append(name, 'intent', requested_policy_digest=DIGEST, planned=[], applied=[],
                      observed={})
    env.ledger.append(name, 'ownership', pid=pid, create_time=create_time,
                      requested_policy_digest=DIGEST, applied=[], observed={}, owned=[])
    if live:
        env.world.table[pid] = create_time


def register(env, name, pid=PID, create_time=CREATION_TIME):
    env.core.append({'kind': 'register', 'execution_id': name, 'pid': pid,
                     'create_time': create_time})


def armed(env, name='e1-p1'):
    own(env, name)
    register(env, name)
    assert env.host.tick() == wd.ARMED
    return name


def arm_two(env):
    own(env, 'e1-p1')
    register(env, 'e1-p1')
    own(env, JOB_TWO[0], JOB_TWO[1], JOB_TWO[2])
    register(env, JOB_TWO[0], JOB_TWO[1], JOB_TWO[2])
    assert env.host.tick() == wd.ARMED
    assert env.host.dog.report()['recorded'] == ['e1-p1', JOB_TWO[0]]
    return env.host.dog.jobs


def rewrite_journal(env, name, pid, create_time):
    """Replace the ledger's bytes for *name* with a fresh valid intent+ownership pair."""
    scratch = mxc_ledger.Ledger(env.tmp / ('scratch-' + name))
    scratch.append(name, 'intent', requested_policy_digest=DIGEST, planned=[], applied=[],
                   observed={})
    scratch.append(name, 'ownership', pid=pid, create_time=create_time,
                   requested_policy_digest=DIGEST, applied=[], observed={}, owned=[])
    with open(scratch._path(name), 'rb') as stream:
        data = stream.read()
    with open(env.ledger._path(name), 'wb') as stream:
        stream.write(data)
    # the anchor follows the bytes, so this reaches the pair check rather than the anchor
    with open(scratch._anchor_path(name), 'rb') as stream:
        anchor = stream.read()
    with open(env.ledger._anchor_path(name), 'wb') as stream:
        stream.write(anchor)


def events(env):
    return env.world.events


def spy_identities(env):
    real, seen = env.world.identity, []

    def reader(pid):
        seen.append(pid)
        return real(pid)
    env.host.identity_reader = reader
    return seen


# ── denial and fail-closed first ──

@pytest.mark.parametrize('damage', ['malformed-tail', 'intent-only'])
def test_the_kill_refuses_a_journal_holding_no_open_ownership_even_though_the_identity_matches(
        env, damage):
    # :196-197 - if the invalid/ops check were dropped the live, still-matching process
    # below would be terminated and the sentinel engaged without any proven ownership.
    armed(env)
    path = env.ledger._path('e1-p1')
    with open(path, 'rb') as stream:
        data = stream.read()
    data = data + b'garbage' if damage == 'malformed-tail' else data.split(b'\n')[0] + b'\n'
    with open(path, 'wb') as stream:
        stream.write(data)
    assert env.world.table[PID] == CREATION_TIME  # the table still matches the old record
    with pytest.raises(ValueError, match='the journal holds no open ownership record'):
        env.host._kill('e1-p1')
    assert events(env) == []  # no terminate and no sentinel attempted before the refusal
    assert env.world.table[PID] == CREATION_TIME  # the process was left alone
    assert env.host.sentinel is None


def test_the_kill_refuses_a_journal_that_names_the_same_pid_at_another_create_time(env):
    # :199 - without the (pid, create_time) pair comparison the kill would fall through
    # to a pid-only terminate although the journal names a different process generation.
    armed(env)
    rewrite_journal(env, 'e1-p1', PID, CREATION_TIME + 7)  # same pid, another create_time
    assert env.world.table[PID] == CREATION_TIME
    with pytest.raises(ValueError, match='the ownership record names another process'):
        env.host._kill('e1-p1')
    assert [e for e in events(env) if e[0] == 'terminate'] == []
    assert events(env) == []
    assert env.world.table[PID] == CREATION_TIME  # the pid it refused to adopt is untouched


def test_the_survivor_retry_refuses_a_job_whose_journal_changed_after_registration(env):
    # :205-207 - if the retry did not re-ask the ledger, or the refusal did not raise,
    # the newly unowned process would be terminated by its stale record.
    arm_two(env)
    rewrite_journal(env, 'e1-p1', PID, CREATION_TIME + 7)  # ownership changed after arming
    env.world.survivors = {PID}
    env.host.sentinel = 'engaged'  # as _stop_core has already engaged it before the retry
    env.host._retry_survivors()
    assert events(env) == [('terminate', JOB_TWO[1], JOB_TWO[2])]  # only the still-owned kill
    assert env.world.table[PID] == CREATION_TIME  # the unowned process was left alive
    assert all(e[1] != PID for e in events(env) if e[0] == 'terminate')


@pytest.mark.parametrize('core_seen,answer,verdict',
                         [(True, True, True), (False, True, True), (None, True, True),
                          (None, 1, False), (True, 1, False)])
def test_a_kill_engages_the_sentinel_once_before_its_first_termination_only_when_core_was_seen(
        env, core_seen, answer, verdict):
    # :208-210 - if the True check were loose (truthy) or removed, the sentinel would
    # be inferred for a Core that was never seen alive; if `is True` became truthy, a
    # terminate answering 1 would be reported as a success.
    arm_two(env)
    env.host._core_seen = core_seen
    env.host.terminate = lambda pid, create_time: (
        env.world.events.append(('terminate', pid, create_time)), answer)[1]
    assert env.host._kill('e1-p1') is verdict
    assert env.host._kill(JOB_TWO[0]) is verdict
    assert events(env) == ([(('sentinel',))] if core_seen is True else []) + [
        ('terminate', PID, CREATION_TIME), ('terminate', JOB_TWO[1], JOB_TWO[2])]
    assert env.host.sentinel == ('engaged' if core_seen is True else None)


# ── boundaries next ──

def test_the_survivor_retry_skips_a_reused_pid_and_still_kills_the_next_survivor(env):
    # :171 - inverting or breaking the identity check would either terminate the reused
    # pid (somebody else's process) or abandon the pass before the second survivor.
    arm_two(env)
    env.world.table[PID] = CREATION_TIME + 5  # the first survivor's pid was reused
    env.world.survivors = {PID}
    env.host.sentinel = 'engaged'  # the stop attempt engaged it; no duplicate from this pass
    env.host._retry_survivors()
    assert events(env) == [('terminate', JOB_TWO[1], JOB_TWO[2])]
    assert env.world.table[PID] == CREATION_TIME + 5  # neither killed nor removed


def test_a_host_that_never_watched_anything_verifies_only_core_identity_and_asks_for_nothing(env):
    # :165-166 - if the empty-dog path guessed at workloads or skipped Core's identity,
    # the reads and calls below would no longer be exactly Core's one observation.
    seen = spy_identities(env)
    assert env.host.dog is None
    assert env.host._workloads() == []
    assert env.host._unstopped() == 'Core still running after its stop'
    assert seen == [CORE_PID]  # Core's identity read by create time, not adopted by pid
    assert env.host._retry_survivors() is None
    assert seen == [CORE_PID] and events(env) == []  # no observation, no kill, no sentinel
    del env.world.table[CORE_PID]
    assert env.host._unstopped() is None  # Core verified absent, nothing was ever watched
    assert seen == [CORE_PID, CORE_PID]
    assert events(env) == []


def test_a_live_core_is_answered_before_any_workload_is_read_when_a_stop_is_verified(env):
    # :178-179 - if the Core check did not return first, the raising second-workload
    # read below would turn the answer into 'stop not verified: SurvivorTableBusy'.
    arm_two(env)
    real = env.world.identity

    def reader(pid):
        seen.append(pid)
        if pid == JOB_TWO[1]:
            raise SurvivorTableBusy('table busy')
        return real(pid)
    seen = []
    env.host.identity_reader = reader
    assert env.host._unstopped() == 'Core still running after its stop'
    assert seen == [CORE_PID]  # no workload was read, so nothing is claimed about them
    assert events(env) == []


def test_a_stop_verified_over_gone_and_reused_originals_is_none_and_touches_no_replacement(env):
    # :180-185 - if a reused pid counted as alive, or any original were mistaken for
    # its replacement, the answer would name a workload instead of verifying the stop,
    # and a privileged call would appear for one of the observed pids.
    arm_two(env)
    del env.world.table[CORE_PID]  # the Core is gone
    del env.world.table[PID]  # the first original is already absent
    env.world.table[JOB_TWO[1]] = CREATION_TIME + 9  # the second pid was reused
    seen = spy_identities(env)
    assert env.host._unstopped() is None
    assert set(seen) == {CORE_PID, PID, JOB_TWO[1]}  # every original observed, in any order
    assert events(env) == []  # no terminate, no sentinel: None asked for nothing privileged
    assert env.world.table[JOB_TWO[1]] == CREATION_TIME + 9  # the replacement is untouched


# ── error paths last ──

def test_the_survivor_retry_checks_the_next_job_after_an_identity_read_raises(env):
    # :173 - if the except left the loop or re-raised, the second live survivor below
    # would never be checked or killed; if the raise were taken for absence, the first
    # survivor would be silently skipped instead of left un-killed (never guessed at).
    arm_two(env)
    real, seen = env.world.identity, []

    def reader(pid):
        seen.append(pid)
        if pid == PID:
            raise SurvivorTableBusy('table busy')
        return real(pid)
    env.host.identity_reader = reader
    env.host.sentinel = 'engaged'  # the stop attempt engaged it; no duplicate from this pass
    env.host._retry_survivors()
    assert set(seen) == {PID, JOB_TWO[1]}  # the first was attempted, the pass still continued
    assert events(env) == [('terminate', JOB_TWO[1], JOB_TWO[2])]  # only the verified kill


def test_a_raising_second_workload_read_after_a_gone_core_names_the_exception_never_none(env):
    # :183-184 - if the except returned None (or the loop stopped after the first
    # absent job), the host would report a verified stop while one workload's fate
    # is unknown; the report must carry the exception type instead, always a string.
    arm_two(env)
    del env.world.table[CORE_PID]
    del env.world.table[PID]  # the first workload is absent, so the loop reaches the second
    real = env.world.identity

    def reader(pid):
        seen.append(pid)
        if pid == JOB_TWO[1]:
            raise SurvivorTableBusy('table busy')
        return real(pid)
    seen = []
    env.host.identity_reader = reader
    answer = env.host._unstopped()
    assert answer == 'stop not verified: SurvivorTableBusy'
    assert answer is not None and answer != host_mod.STOPPED
    assert set(seen) == {CORE_PID, PID, JOB_TWO[1]}
    assert events(env) == []  # an unverified stop never reaches for terminate
