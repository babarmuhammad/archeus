"""T-1243: the ten highest-risk uncovered branches of archeus/node/mxc_watchdog_host.py 59-143.

Source under test: archeus/node/mxc_watchdog_host.py, lines 59-143 inclusive at tip 6bbd3b44
(`WatchdogHost.tick`, `done`, `state`, `report`, `_advance`, `_beat`, `_register`, `_stand_down`,
`_arm`, `_drain`, `_running_as`, `_core_alive`). Every line:NN below is inside that slice; these
are reasoned branch selections from reading the source and the existing assertions of
tests/v1/unit/test_mxc_watchdog_host.py, tests/v1/unit/test_gaps2_node_mxc_watchdog.py,
tests/v1/unit/test_mxc_watchdog.py and tests/v1/unit/test_mxc_wire_watchdog.py, NOT measured
coverage. Denial and fail-closed first, then boundaries, then error paths:

 1. 60-61   a host whose core_stop is STOPPED skips _advance and _stop_core entirely: a later
            registration is never read or adopted, terminations are frozen, yet the status is
            still republished every tick.
 2. 89-90   a retained channel fault after a clean registration keeps the owned job recorded,
            refuses to drain beats past the fault (129-133) and reports the workload survivor
            instead of claiming the stop.
 3. 96-98   an identity_reader that raises AFTER the channel read succeeded is a type-named
            core read fault: never false core_gone evidence, never a claimed stop.
 4. 109-110 beats taken into pending while the dog is STOOD_DOWN must be cleared by the
            re-arm: stale beats cannot keep the replacement watch alive nor replay into it.
 5. 71-74   a retained fault outranks a clean STOOD_DOWN dog: the published state is UNCERTAIN
            and the stop is attempted, whatever the retired watch says.
 6. 59-65   every UNCERTAIN retry tick publishes the status only AFTER the stop attempt and it
            carries that attempt's fresh failure; attempts stay bounded; no premature done.
 7. 101-103 a beat at exactly armed_at is accepted, an older one is excluded without a fault,
            and pending drains exactly once in the original file order.
 8. 135-138 bool, zero, negative, equal-valued float, str and list answers raise ValueError at
            the host seam (never laundered into absence or into a stopped claim), while None,
            a mismatched positive int and the exact positive int are the clean observations.
 9. 91-93   an ARMED dog is ticked before the direct core_alive fallback and RETURNs: exactly
            one core identity observation per armed tick, never a duplicate fallback read.
10. 76-83   report() hands out a snapshot (the rejected mapping is not a mutable alias of the
            host's own) and a failing status write propagates out of tick instead of being
            claimed as a published write.

Fakes only: the seam of tests/v1/unit/test_mxc_watchdog_host.py (Clock, World, env, own,
register) is copied into this one file; the process table, sentinel, terminate, identity_reader
and journals are in-memory or tmp_path fixtures. No process, sentinel, native reader, thread,
network or real clock is touched, nothing sleeps at all, and every channel and journal byte
stays under tmp_path.
"""

from types import SimpleNamespace

import pytest

from claude_sessions import config
from archeus.node import mxc_heartbeat as hb, mxc_ledger, mxc_watchdog as wd
from archeus.node import mxc_watchdog_host as host_mod

CORE_PID, CORE_TIME = 900, 9000
PID, CREATION_TIME = 4129, 133100000000000000
DEADLINE = 10.0
DIGEST = 'a' * 64


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
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(hb, 'HEARTBEAT_ENABLED', True)
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


def events(env):
    return env.world.events


def roll_back(env, by=1.0):
    env.clock.now -= by
    return env.host.tick()


def publish_log(env, ledger):
    """Record what every write_status call saw: the stop-attempt ledger as it stood at that
    very moment and the status, so the ORDER of the attempts against the publish is observable."""
    published = []
    real = env.host_channel.write_status

    def spy(status):
        published.append((list(ledger()), dict(status)))
        return real(status)

    env.host_channel.write_status = spy
    return published


# ── denial and fail-closed ──

def test_a_host_already_stopped_refuses_to_reopen_supervision_but_still_publishes(env):
    # probe 1, 60-61: done() short-circuits _advance; the STOPPED clause of 67-69 is final
    with open(env.core.path, 'ab') as stream:
        stream.write(b'oops\n')
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == host_mod.STOPPED and env.host.done()
    frozen = list(env.world.events)
    with open(env.core.path, 'wb'):
        pass                                  # a perfectly readable channel from here on
    own(env, 'late-p1')
    register(env, 'late-p1')
    env.clock.now += DEADLINE * 3
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host_channel.offset == 0       # _advance never ran again: nothing was read
    assert env.host.dog is None and env.host.rejected == {}
    assert env.world.events == frozen         # no termination or sentinel after the stop
    status = env.core.read_status()
    assert status['at'] == env.clock.now      # the tick still republished, refusal intact
    assert status['state'] == wd.UNCERTAIN and status['recorded'] == []


def test_a_channel_fault_after_a_registration_keeps_the_owned_job_and_denies_the_stop(env):
    # probe 2, 89-90 with 129-133: the fault is retained, prior ownership survives, the
    # survivor is reported, never claimed stopped, and no workload kill is attempted yet
    armed(env)
    env.world.survivors = {PID}
    with open(env.core.path, 'ab') as stream:
        stream.write(b'oops\n')
    assert env.host.tick() == wd.UNCERTAIN
    report = env.host.report()
    assert report['reason'].startswith('channel read failed:')
    assert report['recorded'] == ['e1-p1']    # the registration before the fault is kept
    assert env.host.dog.report()['reason'] == 'heartbeat channel read failed'  # drain refused
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]  # no job kill
    assert report['core_stop'].startswith('owned workload e1-p1 still running')
    assert not env.host.done()
    status = env.core.read_status()
    assert status['state'] == wd.UNCERTAIN and status['recorded'] == ['e1-p1']
    assert status['core_stop'].startswith('owned workload e1-p1 still running')


def test_a_core_read_that_raises_after_a_good_channel_read_is_a_typed_fault(env):
    # probe 3, 96-98: never false core_gone evidence, never a claimed stop, channel first
    seen = []
    real_read = env.host_channel.read

    def read_spy():
        seen.append('channel-read')
        return real_read()

    env.host_channel.read = read_spy

    def unreadable(pid):
        seen.append(('identity', pid))
        raise OSError('table busy')

    env.host.identity_reader = unreadable
    env.core.append({'kind': 'beat', 'seq': 1, 'sent_at': env.clock.now})
    assert env.host.tick() == wd.UNCERTAIN
    assert seen[0] == 'channel-read' and seen[1] == ('identity', CORE_PID)
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]
    report = env.host.report()
    assert report['reason'] == 'core read failed: OSError'
    assert env.host.core_gone is False        # an unreadable Core is not a dead Core
    assert report['core_stop'] == 'stop not verified: OSError'
    assert not env.host.done()
    status = env.core.read_status()
    assert status['reason'] == 'core read failed: OSError'
    assert status['core_stop'] == 'stop not verified: OSError'


def test_beats_held_during_a_stand_down_never_keep_the_replacement_watch_alive(env):
    # probe 4, 109-110: the re-arm clears pending; a stale beat cannot feed or replay into it
    armed(env)
    env.core.append({'kind': 'stand_down', 'execution_id': 'e1-p1', 'reason': 'launch ended'})
    assert env.host.tick() == wd.STOOD_DOWN
    env.core.append({'kind': 'beat', 'seq': 1, 'sent_at': env.clock.now})
    assert env.host.tick() == wd.STOOD_DOWN   # a retired watch is not re-armed by a beat
    assert env.host.pending == [{'seq': 1, 'sent_at': env.clock.now}]
    own(env, 'e2-p1', PID + 1, CREATION_TIME + 1)
    register(env, 'e2-p1', PID + 1, CREATION_TIME + 1)
    assert env.host.tick() == wd.ARMED
    assert env.host.pending == []             # the re-arm dropped the stale beat, un-fed
    env.clock.now += DEADLINE
    assert env.host.tick() == wd.FIRED        # silence, not a stale beat, decides the watch
    assert events(env) == [('sentinel',), ('terminate', PID + 1, CREATION_TIME + 1)]
    assert env.host.dog.report()['last_beat'] is None
    assert env.host.dog.report()['verdicts'][0]['reason'] == 'core_silent'


def test_a_fault_after_a_stand_down_outranks_the_stood_down_report(env):
    # probe 5, 71-74: the retained fault wins over the retired watch at the publish
    armed(env)
    env.core.append({'kind': 'stand_down', 'execution_id': 'e1-p1', 'reason': 'launch ended'})
    assert env.host.tick() == wd.STOOD_DOWN
    del env.world.table[PID]                  # the stood-down launch really ended
    with open(env.core.path, 'ab') as stream:
        stream.write(b'oops\n')
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host.dog.state == wd.STOOD_DOWN   # the dog is not rewritten; the fault wins
    report = env.host.report()
    assert report['reason'].startswith('channel read failed:')
    assert report['core_stop'] == host_mod.STOPPED
    assert env.host.done()
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]
    assert env.core.read_status()['state'] == wd.UNCERTAIN   # never published as STOOD_DOWN


def test_the_status_of_a_retrying_tick_is_published_after_the_attempt_with_its_failure(env):
    # probe 6, 59-65: attempt, then publish; the fresh failure rides in the same status;
    # the attempts stay bounded and no tick ever claims done too early
    armed(env)
    calls = []

    def stubborn(pid, create_time):
        calls.append((pid, create_time))
        return False

    env.host.terminate = stubborn
    assert roll_back(env) == wd.UNCERTAIN
    published = publish_log(env, lambda: list(calls))
    for round_number in (2, 3, 4):
        assert env.host.tick() == wd.UNCERTAIN
        attempts, status = published[-1]
        assert attempts == calls              # every attempt of this tick preceded the write
        assert status['state'] == wd.UNCERTAIN
        assert status['core_stop'] == env.host.report()['core_stop']
        assert not env.host.done()
        if round_number in (2, 3):
            assert status['core_stop'] == 'Core still running after its stop'
        else:
            assert status['core_stop'] == ('persistent stop failure after 3 attempts: '
                                           'Core still running after its stop')
    assert [len(t) for t, _ in published] == [3, 5, 5]     # bounded: nothing new after #3
    assert len(published) == 3                # exactly one publish per tick
    assert env.host.tick() == wd.UNCERTAIN and not env.host.done()
    assert calls == [(CORE_PID, CORE_TIME)] + [(CORE_PID, CORE_TIME),
                                               (PID, CREATION_TIME)] * 2


# ── boundaries ──

def test_a_beat_at_exactly_armed_at_is_accepted_an_older_one_excluded_and_drains_once(env):
    # probe 7, 101-103 with 129-133: the >= boundary, silent exclusion, single ordered drain
    armed(env)
    armed_at = env.host.dog.armed_at
    env.core.append({'kind': 'beat', 'seq': 1, 'sent_at': armed_at})
    assert env.host.tick() == wd.ARMED        # exactly armed_at is inside the window
    assert env.host.dog.report()['last_beat'] == armed_at
    env.core.append({'kind': 'beat', 'seq': 2, 'sent_at': armed_at - 0.5})
    assert env.host.tick() == wd.ARMED        # older is excluded, not a window fault
    assert env.host.pending == []
    env.core.append({'kind': 'beat', 'seq': 2, 'sent_at': armed_at})
    env.core.append({'kind': 'beat', 'seq': 3, 'sent_at': armed_at})
    assert env.host.tick() == wd.ARMED        # both, in the file order they were appended
    assert env.host.dog.report()['last_beat'] == armed_at
    assert env.host.pending == []
    assert env.host.tick() == wd.ARMED        # drained once: a redrain would replay seq 2
    assert events(env) == []                  # no sentinel and no kill anywhere near this


@pytest.mark.parametrize('answer', [True, False, 0, -3, CORE_TIME * 1.0, 'x', [CORE_TIME]])
def test_a_malformed_identity_answer_is_a_typed_fault_never_absence_never_a_stopped_claim(
        env, answer):
    # probe 8a, 135-138: bool, zero, negative, equal-valued float, str, list all raise
    # ValueError; the fault names the type, the stop stays unverified, the Core stays unread
    env.world.terminated = False              # the poisoned entry is not washed out by a kill
    env.world.table[CORE_PID] = answer
    assert env.host.tick() == wd.UNCERTAIN
    report = env.host.report()
    assert report['reason'] == 'core read failed: ValueError'
    assert report['core_stop'] == 'stop not verified: ValueError'
    assert env.host.core_gone is False and not env.host.done()


@pytest.mark.parametrize('answer, gone', [(None, True), (CORE_TIME + 7, True),
                                           (CORE_TIME, False)])
def test_only_absence_or_a_mismatched_creation_time_are_clean_negatives_about_the_core(
        env, answer, gone):
    # probe 8b, 139: None and a differing positive int are clean negatives (never reused-
    # pid-as-Core), the exact int is Core itself; none of them is ever a fault
    if answer is None:
        del env.world.table[CORE_PID]
    else:
        env.world.table[CORE_PID] = answer
    assert env.host.tick() == host_mod.IDLE
    assert env.host.core_gone is gone
    assert env.host.done() is gone
    assert env.host.report()['core_stop'] is None
    assert events(env) == []                  # a clean negative never triggers a privileged act


# ── error paths ──

def test_an_armed_tick_observes_only_core_identity_and_a_reused_core_pid_fires_on_the_job(env):
    # probe 9, 91-93: the ARMED branch ticks the dog and RETURNS; the 94-99 fallback is
    # mutually exclusive, so every observation is of Core's own pid and never of a workload
    armed(env)
    reads = []
    real = env.world.identity
    env.host.identity_reader = lambda pid: (reads.append(pid), real(pid))[1]
    env.clock.now += 1
    assert env.host.tick() == wd.ARMED
    assert set(reads) == {CORE_PID}
    assert events(env) == []
    env.core.append({'kind': 'stand_down', 'execution_id': 'e1-p1', 'reason': 'launch ended'})
    assert env.host.tick() == wd.STOOD_DOWN
    reads.clear()
    env.clock.now += 1
    assert env.host.tick() == wd.STOOD_DOWN
    assert set(reads) == {CORE_PID}
    assert events(env) == []


def test_a_reused_core_pid_on_an_armed_tick_ends_the_recorded_job_and_never_core(env):
    # the dog reads Core's pid as a different process: Core is dead, so the recorded job is
    # the one identity-checked kill; the reused pid is never terminated as if it were Core
    armed(env)
    env.world.table[CORE_PID] = CORE_TIME + 7
    assert env.host.tick() == wd.FIRED
    assert [e for e in events(env) if e[0] == 'terminate'] == [('terminate', PID, CREATION_TIME)]
    assert env.host.done()
    assert env.world.table[CORE_PID] == CORE_TIME + 7


def test_the_reported_rejections_are_a_snapshot_the_host_does_not_share_or_mutate(env):
    # probe 10a, 82: dict(self.rejected) is a copy; tampering with a report cannot rewrite
    # the host's refusals or the next published status
    register(env, 'forged-p1')
    assert env.host.tick() == host_mod.IDLE
    refusal = 'the journal holds no open ownership record'
    assert env.host.rejected == {'forged-p1': refusal}
    report = env.host.report()
    report['rejected']['forged-p1'] = 'tampered'
    report['rejected']['adopted-p1'] = 'tampered too'
    assert env.host.rejected == {'forged-p1': refusal}
    assert env.host.report()['rejected'] == {'forged-p1': refusal}
    env.host.tick()
    assert env.core.read_status()['rejected'] == {'forged-p1': refusal}


def test_a_status_write_that_fails_propagates_out_of_the_tick_and_is_never_claimed(env,
                                                                                   monkeypatch):
    # probe 10b, 64: a failed write_status is the tick's failure, not a swallowed one, and
    # the previously published status stands: no write, no claim of one
    assert env.host.tick() == host_mod.IDLE
    published = env.core.read_status()

    def refusal(*args, **kwargs):
        return False

    monkeypatch.setattr(config, 'write_atomic', refusal)
    env.clock.now += 1.0
    with pytest.raises(OSError, match='not written'):
        env.host.tick()
    assert env.core.read_status() == published   # the old status stands, nothing was claimed
    monkeypatch.undo()
    env.clock.now += 1.0
    assert env.host.tick() == host_mod.IDLE
    assert env.core.read_status()['at'] == env.clock.now
