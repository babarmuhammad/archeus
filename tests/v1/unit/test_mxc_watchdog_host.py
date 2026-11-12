# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""PV-20 B13: the heartbeat channel, Core's sender and registration proxy, and the
watchdog host that ends what the ledger says Core launched. Fakes only: no process is
spawned and nothing native is read; the channel is files in a temp directory."""

import importlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from archeus.node import local, mxc_heartbeat as hb, mxc_ledger, mxc_watchdog as wd
from archeus.node import mxc_watchdog_host as host_mod

from .test_mxc_wire import CREATION_TIME, PID, journal_ops, native_parts, wire, args  # noqa: F401

CORE_PID, CORE_TIME = 900, 9000
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
        if self.terminated:
            self.table = {p: t for p, t in self.table.items() if p in self.survivors}
        return self.terminated

    def engage(self):
        self.events.append(('sentinel',))
        if isinstance(self.sentinel, Exception):
            raise self.sentinel
        return self.sentinel


@pytest.fixture
def open_channel(monkeypatch):
    monkeypatch.setattr(hb, 'HEARTBEAT_ENABLED', True)


@pytest.fixture
def env(tmp_path, open_channel):
    clock, world = Clock(), World()
    ledger = mxc_ledger.Ledger(tmp_path / 'ledger')
    core_side = hb.Channel(tmp_path / 'chan')
    host_side = hb.Channel(tmp_path / 'chan')
    host = host_mod.WatchdogHost(channel=host_side, clock=clock, deadline_s=DEADLINE,
                                 core=(CORE_PID, CORE_TIME), identity_reader=world.identity,
                                 terminate=world.terminate, engage_sentinel=world.engage,
                                 journals=ledger.journals)
    return SimpleNamespace(clock=clock, world=world, ledger=ledger, core=core_side,
                           host_channel=host_side, host=host, tmp=tmp_path,
                           sender=hb.HeartbeatSender(core_side, clock),
                           proxy=hb.WatchdogProxy(core_side, clock, max_age_s=5.0))


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


# ── the channel ──

def test_the_channel_hands_each_message_over_once(env):
    env.sender.beat()
    assert [m['kind'] for m in env.host_channel.read()] == ['beat']
    assert env.host_channel.read() == []
    register(env, 'x')
    assert [m['kind'] for m in env.host_channel.read()] == ['register']


def test_a_line_still_being_written_waits_for_its_newline(env):
    with open(env.core.path, 'ab') as stream:
        stream.write(b'{"kind":"beat","seq":1')
    assert env.host_channel.read() == []
    with open(env.core.path, 'ab') as stream:
        stream.write(b',"sent_at":1.0}\n')
    assert env.host_channel.read() == [{'kind': 'beat', 'seq': 1, 'sent_at': 1.0}]


@pytest.mark.parametrize('line', [b'not json\n', b'[1]\n', b'{"kind":"beat","seq":1}\n',
                                  b'{"kind":"kill","pid":1}\n',
                                  b'{"kind":"beat","seq":1,"sent_at":1,"x":2}\n'])
def test_a_damaged_line_is_never_guessed_past(env, line):
    with open(env.core.path, 'ab') as stream:
        stream.write(line)
    with pytest.raises(ValueError):
        env.host_channel.read()


def test_a_channel_that_shrank_or_vanished_is_a_fault(env):
    env.sender.beat()
    env.host_channel.read()
    with open(env.core.path, 'wb'):
        pass
    with pytest.raises(ValueError):
        env.host_channel.read()


def test_a_channel_that_was_read_and_vanished_is_a_fault(env):
    env.sender.beat()
    env.host_channel.read()
    import os
    os.remove(env.core.path)
    with pytest.raises(ValueError):
        env.host_channel.read()


def test_no_channel_yet_is_no_messages(env):
    assert env.host_channel.read() == []


def test_a_malformed_message_is_never_written(env):
    with pytest.raises(ValueError):
        env.core.append({'kind': 'beat', 'seq': 1})
    with pytest.raises(ValueError):
        env.core.append({'kind': 'other'})
    assert env.host_channel.read() == []


def test_the_status_round_trips_and_garbage_reads_as_none(env):
    assert env.core.read_status() is None
    env.host_channel.write_status({'state': 'IDLE'})
    assert env.core.read_status() == {'state': 'IDLE'}
    with open(env.core.status_path, 'w', encoding='utf-8') as stream:
        stream.write('[1]')
    assert env.core.read_status() is None
    with open(env.core.status_path, 'w', encoding='utf-8') as stream:
        stream.write('{')
    assert env.core.read_status() is None


# ── Core's side ──

def test_the_sender_and_the_proxy_are_closed_by_default(tmp_path):
    channel = hb.Channel(tmp_path / 'c')
    assert hb.HEARTBEAT_ENABLED is False
    with pytest.raises(wd.WatchdogUnavailable):
        hb.HeartbeatSender(channel, Clock())
    with pytest.raises(wd.WatchdogUnavailable):
        hb.WatchdogProxy(channel, Clock(), max_age_s=5)


def test_heartbeats_climb_in_sequence_and_never_in_the_past(env):
    for now in (100.0, 101.0, 99.0, 102.0):
        env.clock.now = now
        env.sender.beat()
    beats = env.host_channel.read()
    assert [b['seq'] for b in beats] == [1, 2, 3, 4]
    assert [b['sent_at'] for b in beats] == [100.0, 101.0, 101.0, 102.0]


@pytest.mark.parametrize('now', [float('nan'), float('inf'), 'late', None, True])
def test_a_clock_that_cannot_be_read_writes_no_heartbeat(env, now):
    env.clock.now = now
    with pytest.raises(ValueError):
        env.sender.beat()
    assert env.host_channel.read() == []


@pytest.mark.parametrize('age', [0, -1, float('nan'), 'x', True])
def test_the_proxy_needs_a_positive_status_age(env, age):
    with pytest.raises(wd.WatchdogUnavailable):
        hb.WatchdogProxy(env.core, env.clock, max_age_s=age)


def test_the_node_beats_once_per_sweep_and_only_with_a_sender():
    beats = []
    isolation = SimpleNamespace(reclaim=lambda live: ['x'], reconcile_ledger=lambda: None)
    quiet = local.LocalNode(isolation=isolation)
    assert quiet.heartbeat is None and quiet.reclaim_isolation(()) == ['x']
    node = local.LocalNode(isolation=isolation, heartbeat=SimpleNamespace(
        beat=lambda: beats.append(1)))
    assert node.reclaim_isolation(()) == ['x'] and node.reclaim_isolation(()) == ['x']
    assert beats == [1, 1]


def test_a_failed_beat_is_the_sweeps_fault_not_a_silent_skip():
    def beat():
        raise OSError('disk')

    node = local.LocalNode(isolation=SimpleNamespace(
        reclaim=lambda live: pytest.fail('swept'), reconcile_ledger=lambda: None),
        heartbeat=SimpleNamespace(beat=beat))
    with pytest.raises(OSError):
        node.reclaim_isolation(())


# ── the host: a hung or dead Core ──

def test_a_hung_core_gets_the_sentinel_first_and_then_the_identity_checked_kill(env):
    armed(env)
    env.sender.beat()
    env.clock.now += DEADLINE - 1
    assert env.host.tick() == wd.ARMED
    env.clock.now += 1
    assert env.host.tick() == wd.FIRED
    assert events(env) == [('sentinel',), ('terminate', PID, CREATION_TIME)]
    status = env.core.read_status()
    assert status['state'] == wd.FIRED and status['reason'] == 'core_silent'
    assert status['sentinel'] == 'engaged'
    assert status['verdicts'][0]['verdict'] == wd.KILLED


def test_a_dead_core_is_killed_for_without_a_sentinel(env):
    armed(env)
    del env.world.table[CORE_PID]
    assert env.host.tick() == wd.FIRED
    assert events(env) == [('terminate', PID, CREATION_TIME)]
    assert env.host.report()['reason'] == 'core_dead' and env.host.sentinel is None


def test_a_core_pid_reused_by_another_process_is_a_dead_core(env):
    armed(env)
    env.world.table[CORE_PID] = CORE_TIME + 1
    assert env.host.tick() == wd.FIRED
    assert env.host.report()['reason'] == 'core_dead'


def test_a_beating_core_is_never_killed_for(env):
    armed(env)
    for _ in range(5):
        env.clock.now += DEADLINE / 2
        env.sender.beat()
        assert env.host.tick() == wd.ARMED
    assert events(env) == []


def test_a_malformed_core_reading_is_uncertain_and_stops_core(env):
    armed(env)
    env.world.table[CORE_PID] = 'x'
    assert env.host.tick() == wd.UNCERTAIN
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]
    assert env.host.done()


def test_a_process_that_is_already_gone_or_reused_is_not_killed(env):
    armed(env, 'gone-p1')
    own(env, 'reuse-p1', PID + 1, CREATION_TIME + 1)
    register(env, 'reuse-p1', PID + 1, CREATION_TIME + 1)
    env.host.tick()
    del env.world.table[PID]
    env.world.table[PID + 1] = CREATION_TIME + 2
    del env.world.table[CORE_PID]
    assert env.host.tick() == wd.FIRED
    assert events(env) == []
    assert [v['verdict'] for v in env.core.read_status()['verdicts'][:2]] == [
        wd.ALREADY_ABSENT, wd.SKIPPED_REUSED_PID]


def test_a_kill_that_does_not_confirm_is_uncertain(env):
    armed(env)
    env.world.terminated = False
    env.clock.now += DEADLINE
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host.report()['verdicts'][0]['verdict'] == wd.KILL_UNVERIFIED


@pytest.mark.parametrize('sentinel', [False, OSError('denied'), None])
def test_a_sentinel_that_cannot_be_verified_never_withholds_the_kill(env, sentinel):
    armed(env)
    env.world.sentinel = sentinel
    env.clock.now += DEADLINE
    assert env.host.tick() == wd.FIRED
    assert events(env) == [('sentinel',), ('terminate', PID, CREATION_TIME)]
    assert env.host.report()['sentinel'] == 'unverified'


def test_the_sentinel_is_engaged_once_for_every_job(env):
    armed(env, 'a-p1')
    own(env, 'b-p1', PID + 1, CREATION_TIME + 1)
    register(env, 'b-p1', PID + 1, CREATION_TIME + 1)
    env.host.tick()
    env.clock.now += DEADLINE
    assert env.host.tick() == wd.FIRED
    assert events(env) == [('sentinel',), ('terminate', PID, CREATION_TIME),
                           ('terminate', PID + 1, CREATION_TIME + 1)]


def test_a_hung_core_with_nothing_alive_engages_no_sentinel(env):
    armed(env)
    del env.world.table[PID]
    env.clock.now += DEADLINE
    assert env.host.tick() == wd.FIRED
    assert events(env) == []


# ── the host: only what the ledger says Core launched ──

def test_a_registration_with_no_journal_is_refused_and_never_killed(env):
    env.world.table[PID] = CREATION_TIME
    register(env, 'forged-p1')
    assert env.host.tick() == host_mod.IDLE
    assert env.core.read_status()['rejected'] == {
        'forged-p1': 'the journal holds no open ownership record'}
    del env.world.table[CORE_PID]
    env.host.tick()
    assert events(env) == [] and env.host.dog is None


def test_a_registration_naming_another_process_than_the_ledger_is_refused(env):
    own(env, 'e1-p1')
    register(env, 'e1-p1', PID, CREATION_TIME + 1)
    env.host.tick()
    assert env.host.rejected == {'e1-p1': 'the ownership record names another process'}
    register(env, 'e1-p1', PID + 1, CREATION_TIME)
    env.host.tick()
    assert env.host.dog is None


def test_a_journal_with_an_intent_and_no_ownership_is_not_watched(env):
    env.ledger.append('e1-p1', 'intent', requested_policy_digest=DIGEST, planned=[],
                      applied=[], observed={})
    register(env, 'e1-p1')
    env.host.tick()
    assert 'e1-p1' in env.host.rejected


def test_a_torn_journal_is_not_watched(env):
    own(env, 'e1-p1')
    with open(env.ledger._path('e1-p1'), 'ab') as stream:
        stream.write(b'garbage')
    register(env, 'e1-p1')
    env.host.tick()
    assert 'e1-p1' in env.host.rejected


def test_a_second_registration_of_the_same_job_is_refused(env):
    armed(env)
    register(env, 'e1-p1')
    env.host.tick()
    assert env.host.rejected == {'e1-p1': 'execution already recorded'}
    assert env.host.state() == wd.ARMED


def test_the_kill_asks_the_ledger_again(env):
    armed(env)
    forged = {}
    env.host.journals = lambda: forged
    env.clock.now += DEADLINE
    assert env.host.tick() == wd.UNCERTAIN
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]
    assert env.host.report()['verdicts'][0]['verdict'] == wd.KILL_FAILED


def test_a_job_that_ended_still_has_its_ownership_record_for_the_kill(env):
    armed(env)
    env.ledger.append('e1-p1', 'disposal', verified_absent=True)
    env.clock.now += DEADLINE
    assert env.host.tick() == wd.FIRED
    assert events(env)[-1] == ('terminate', PID, CREATION_TIME)


# ── the host: its own life ──

def test_beats_from_before_the_watch_began_are_dropped_not_taken_for_a_fault(env):
    env.sender.beat()
    own(env, 'e1-p1')
    register(env, 'e1-p1')
    env.core.append({'kind': 'beat', 'seq': 2, 'sent_at': env.clock.now - 5})
    assert env.host.tick() == wd.ARMED


def test_a_beat_ahead_of_the_hosts_clock_is_uncertain(env):
    armed(env)
    env.clock.now += 1
    env.core.append({'kind': 'beat', 'seq': 1, 'sent_at': env.clock.now + 50})
    assert env.host.tick() == wd.UNCERTAIN
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]


def test_a_replayed_sequence_is_uncertain(env):
    armed(env)
    env.clock.now += 1
    env.sender.beat()
    assert env.host.tick() == wd.ARMED
    env.core.append({'kind': 'beat', 'seq': 1, 'sent_at': env.clock.now})
    assert env.host.tick() == wd.UNCERTAIN


def test_a_damaged_channel_is_uncertain_and_stops_core(env):
    armed(env)
    with open(env.core.path, 'ab') as stream:
        stream.write(b'oops\n')
    env.clock.now += DEADLINE * 2
    assert env.host.tick() == wd.UNCERTAIN
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]
    assert env.host.done()
    assert env.core.read_status()['state'] == wd.UNCERTAIN


def test_a_damaged_channel_with_nothing_watched_ends_the_host(env):
    with open(env.core.path, 'ab') as stream:
        stream.write(b'oops\n')
    assert env.host.tick() == wd.UNCERTAIN and env.host.done()


def roll_back(env, by=1.0):
    env.clock.now -= by
    return env.host.tick()


def test_a_rollback_engages_the_sentinel_then_stops_core_by_identity_then_verifies(env):
    armed(env)
    env.clock.now += 5
    assert env.host.tick() == wd.ARMED
    real = env.host.identity_reader
    env.host.identity_reader = lambda pid: (events(env).append(('identity', pid)), real(pid))[1]
    assert roll_back(env, 3) == wd.UNCERTAIN
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME),
                           ('identity', CORE_PID), ('identity', PID)]
    report = env.host.report()
    assert report['reason'] == 'malformed clock observation'
    assert report['sentinel'] == 'engaged' and report['core_stop'] == host_mod.STOPPED
    assert env.host.done()


def test_a_failed_stop_keeps_supervision_active_and_reports_it(env):
    armed(env)
    env.world.terminated = False
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == 'Core still running after its stop'
    assert not env.host.done()


def test_a_stop_that_leaves_core_running_is_reported_not_claimed(env):
    armed(env)
    env.world.survivors = {CORE_PID}
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == 'Core still running after its stop'
    assert not env.host.done()


def test_a_stop_that_leaves_an_owned_workload_running_is_reported_not_claimed(env):
    armed(env)
    env.world.survivors = {PID}
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.report()['core_stop'].startswith('owned workload e1-p1 still running')
    assert not env.host.done()


def test_core_that_exits_after_a_failed_first_attempt_is_verified_stopped_on_the_next_tick(env):
    armed(env)
    env.world.terminated = False
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == 'Core still running after its stop'
    del env.world.table[CORE_PID], env.world.table[PID]
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == host_mod.STOPPED and env.host.done()
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]


def test_a_verification_that_briefly_fails_is_read_again_on_the_next_tick(env):
    armed(env)
    real, failed = env.world.identity, []

    def flaky(pid):
        if ('terminate', CORE_PID, CORE_TIME) in events(env) and not failed:
            failed.append(pid)
            raise OSError('table busy')
        return real(pid)
    env.host.identity_reader = flaky
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == 'stop not verified: OSError'
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == host_mod.STOPPED and env.host.done()
    assert [e for e in events(env) if e[0] == 'terminate'] == [('terminate', CORE_PID, CORE_TIME)]


def test_a_survivor_gets_two_more_identity_bound_attempts_then_a_persistent_failure(env):
    armed(env)
    calls = []

    def stubborn(pid, create_time):
        calls.append((pid, create_time))
        return False
    env.host.terminate = stubborn
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host.tick() == wd.UNCERTAIN
    assert calls == [(CORE_PID, CORE_TIME)] * 3
    for _ in range(3):
        assert env.host.tick() == wd.UNCERTAIN
    assert calls == [(CORE_PID, CORE_TIME)] * 3
    assert env.host.report()['core_stop'] == ('persistent stop failure after 3 attempts: '
                                              'Core still running after its stop')
    assert not env.host.done()
    assert events(env).count(('sentinel',)) == 1


def test_a_pid_reused_between_the_retries_is_never_terminated(env):
    armed(env)
    calls = []

    def stubborn(pid, create_time):
        calls.append((pid, create_time))
        return False
    env.host.terminate = stubborn
    assert roll_back(env) == wd.UNCERTAIN
    env.world.table[CORE_PID] = CORE_TIME + 1
    del env.world.table[PID]
    assert env.host.tick() == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == host_mod.STOPPED and env.host.done()
    assert calls == [(CORE_PID, CORE_TIME)]
    assert env.world.table[CORE_PID] == CORE_TIME + 1


def test_a_terminate_that_claims_success_does_not_make_the_stop_stopped(env):
    armed(env)
    env.world.survivors = {CORE_PID}
    assert roll_back(env) == wd.UNCERTAIN
    assert env.world.terminated is True
    assert env.host.report()['core_stop'] == 'Core still running after its stop'
    assert not env.host.done()


def test_a_clock_that_only_moves_forward_stops_nothing(env):
    armed(env)
    for _ in range(5):
        env.clock.now += DEADLINE * 3
        env.sender.beat()
        assert env.host.tick() == wd.ARMED
    assert events(env) == [] and env.host.report()['core_stop'] is None


def test_a_damaged_channel_with_nothing_watched_ends_the_host_after_its_stop(env):
    with open(env.core.path, 'ab') as stream:
        stream.write(b'oops\n')
    env.host.tick()
    assert env.host.report()['core_stop'] == host_mod.STOPPED and env.host.done()


def test_a_core_already_gone_with_nothing_owned_is_stopped_whatever_terminate_says(env):
    armed(env)
    env.world.table.clear()
    env.world.terminated = False
    assert roll_back(env) == wd.UNCERTAIN
    assert events(env) == [('sentinel',), ('terminate', CORE_PID, CORE_TIME)]
    assert env.host.report()['core_stop'] == host_mod.STOPPED and env.host.done()


def test_a_core_already_gone_with_a_workload_still_running_is_not_stopped(env):
    armed(env)
    env.world.table = {PID: CREATION_TIME}
    env.world.survivors = {PID}
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.report()['core_stop'].startswith('owned workload e1-p1 still running')
    assert not env.host.done()


def test_a_terminate_that_raises_is_decided_by_the_verification_alone(env):
    armed(env)
    env.world.table.clear()

    def raising(pid, create_time):
        raise OSError('denied')
    env.host.terminate = raising
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == host_mod.STOPPED and env.host.done()


def test_a_stop_that_cannot_read_identities_back_is_not_reported_stopped(env):
    armed(env)

    def unreadable(pid):
        raise OSError('table gone')
    env.host.identity_reader = unreadable
    assert roll_back(env) == wd.UNCERTAIN
    assert env.host.report()['core_stop'] == 'stop not verified: OSError'
    assert not env.host.done()


def test_an_idle_host_ends_when_core_is_gone_and_not_before(env):
    assert env.host.tick() == host_mod.IDLE and not env.host.done()
    del env.world.table[CORE_PID]
    assert env.host.tick() == host_mod.IDLE and env.host.done()
    assert env.host.report()['reason'] == 'core gone with nothing watched'
    assert events(env) == []


def test_an_unreadable_core_with_nothing_watched_ends_the_host_uncertain(env):
    env.world.table[CORE_PID] = 'x'
    assert env.host.tick() == wd.UNCERTAIN and env.host.done()


def test_a_stand_down_of_the_sole_job_retires_the_watch_and_the_next_job_rearms(env):
    armed(env)
    env.core.append({'kind': 'stand_down', 'execution_id': 'e1-p1', 'reason': 'launch ended'})
    assert env.host.tick() == wd.STOOD_DOWN
    first = env.host.dog
    env.clock.now += DEADLINE * 3
    assert env.host.tick() == wd.STOOD_DOWN and events(env) == []
    own(env, 'e2-p1', PID + 1, CREATION_TIME + 1)
    register(env, 'e2-p1', PID + 1, CREATION_TIME + 1)
    assert env.host.tick() == wd.ARMED and env.host.dog is not first
    assert env.host.report()['recorded'] == ['e2-p1']
    env.clock.now += DEADLINE
    assert env.host.tick() == wd.FIRED
    assert events(env)[-1] == ('terminate', PID + 1, CREATION_TIME + 1)


def test_a_stand_down_for_a_shared_or_other_job_is_ignored(env):
    armed(env, 'a-p1')
    own(env, 'b-p1', PID + 1, CREATION_TIME + 1)
    register(env, 'b-p1', PID + 1, CREATION_TIME + 1)
    env.core.append({'kind': 'stand_down', 'execution_id': 'a-p1', 'reason': 'x'})
    assert env.host.tick() == wd.ARMED
    env.core.append({'kind': 'stand_down', 'execution_id': 'zzz', 'reason': 'x'})
    assert env.host.tick() == wd.ARMED


def test_a_stand_down_before_any_watch_is_ignored(env):
    env.core.append({'kind': 'stand_down', 'execution_id': 'a-p1', 'reason': 'x'})
    assert env.host.tick() == host_mod.IDLE


def test_nothing_is_adopted_after_the_watch_fired(env):
    armed(env)
    del env.world.table[CORE_PID]
    env.host.tick()
    own(env, 'late-p1', PID + 1, CREATION_TIME + 1)
    register(env, 'late-p1', PID + 1, CREATION_TIME + 1)
    env.host.tick()
    assert env.host.rejected == {}
    assert 'late-p1' not in env.host.report()['recorded']


def test_a_tick_after_the_end_only_republishes(env):
    armed(env)
    del env.world.table[CORE_PID]
    env.host.tick()
    count = len(events(env))
    env.world.table[CORE_PID] = CORE_TIME
    env.host.tick()
    assert len(events(env)) == count and env.host.state() == wd.FIRED


def test_every_tick_publishes_the_status_the_proxy_reads(env):
    env.host.tick()
    status = env.core.read_status()
    assert status['state'] == host_mod.IDLE and status['at'] == env.clock.now
    assert status['recorded'] == [] and status['rejected'] == {}


def test_run_ticks_until_the_watch_ends_and_never_after(env):
    armed(env)
    naps = []

    def sleep(seconds):
        naps.append(seconds)
        env.clock.now += DEADLINE

    report = env.host.run(2.0, sleep=sleep)
    assert report['state'] == wd.FIRED and naps == [2.0, 2.0]
    assert env.host.run(2.0, sleep=sleep)['state'] == wd.FIRED and naps == [2.0, 2.0]


def test_run_obeys_a_stop_request(env):
    assert env.host.run(1.0, sleep=lambda s: None, stop=lambda: True)['state'] == host_mod.IDLE
    assert env.core.read_status() is None


# ── the proxy ──

def hosted(env):
    env.host.tick()


def job(name='e1-p1'):
    return {'execution_id': name, 'pid': PID, 'create_time': CREATION_TIME, 'job_ref': 'handle'}


def test_a_launch_is_refused_while_the_host_is_absent_stale_or_unreadable(env):
    with pytest.raises(wd.WatchdogUnavailable, match='unreadable'):
        env.proxy.record(job())
    hosted(env)
    env.clock.now += 5.5
    with pytest.raises(wd.WatchdogUnavailable, match='stale'):
        env.proxy.record(job())
    env.clock.now -= 6
    with pytest.raises(wd.WatchdogUnavailable, match='stale'):
        env.proxy.record(job())
    assert env.host_channel.read() == []


@pytest.mark.parametrize('bad', [{'state': 'ARMED'}, {'at': 100.0, 'state': 'WHAT',
                                                       'recorded': [], 'rejected': {}},
                                 {'at': 100.0, 'state': 'ARMED', 'recorded': 'x',
                                  'rejected': {}},
                                 {'at': 100.0, 'state': 'ARMED', 'recorded': [],
                                  'rejected': []},
                                 {'at': 'now', 'state': 'ARMED', 'recorded': [], 'rejected': {}}])
def test_a_status_of_the_wrong_shape_is_unreadable(env, bad):
    env.host_channel.write_status(bad)
    with pytest.raises(wd.WatchdogUnavailable, match='unreadable'):
        env.proxy.record(job())
    assert env.proxy.report()['state'] == wd.UNCERTAIN


@pytest.mark.parametrize('state', [wd.FIRED, wd.UNCERTAIN])
def test_a_launch_is_refused_once_the_host_has_acted(env, state):
    env.host_channel.write_status({'at': env.clock.now, 'state': state, 'recorded': [],
                                   'rejected': {}})
    with pytest.raises(wd.WatchdogUnavailable, match=state):
        env.proxy.record(job())


def test_a_launch_the_host_can_watch_is_registered_through_the_channel(env):
    hosted(env)
    assert env.proxy.record(job()) is True
    assert env.host_channel.read() == [{'kind': 'register', 'execution_id': 'e1-p1',
                                        'pid': PID, 'create_time': CREATION_TIME}]


@pytest.mark.parametrize('field,value', [('job_ref', None), ('pid', 0), ('pid', True),
                                         ('create_time', -1), ('execution_id', '')])
def test_a_malformed_job_is_refused_before_anything_is_written(env, field, value):
    hosted(env)
    with pytest.raises(wd.WatchdogUnavailable):
        env.proxy.record(dict(job(), **{field: value}))
    assert env.host_channel.read() == []


def test_the_report_is_the_hosts_and_only_armed_lets_a_launch_stand_down(env):
    hosted(env)
    assert env.proxy.report()['state'] == wd.UNCERTAIN
    assert 'no watch' in env.proxy.report()['reason']
    own(env, 'e1-p1')
    env.proxy.record(job())
    env.host.tick()
    assert env.proxy.report() == {'state': wd.ARMED, 'reason': 'armed', 'recorded': ['e1-p1']}
    assert env.proxy.stand_down('launch ended') is True
    env.host.tick()
    assert env.host.state() == wd.STOOD_DOWN


def test_a_launch_the_host_refused_reads_back_uncertain(env):
    hosted(env)
    env.proxy.record(job('nowhere-p1'))
    env.host.tick()
    report = env.proxy.report()
    assert report['state'] == wd.UNCERTAIN and 'nowhere-p1' in report['reason']


def test_a_refusal_of_someone_elses_launch_is_not_ours(env):
    own(env, 'mine-p1')
    hosted(env)
    register(env, 'other-p1')
    env.proxy.record(job('mine-p1'))
    env.host.tick()
    assert env.proxy.report()['state'] == wd.ARMED


def test_a_proxy_stands_down_only_from_a_sole_armed_job(env):
    armed(env, 'a-p1')
    own(env, 'b-p1', PID + 1, CREATION_TIME + 1)
    register(env, 'b-p1', PID + 1, CREATION_TIME + 1)
    env.host.tick()
    with pytest.raises(wd.WatchdogUnavailable):
        env.proxy.stand_down()
    assert [m for m in env.host_channel.read() if m['kind'] == 'stand_down'] == []


def test_a_proxy_cannot_stand_down_a_host_that_is_not_armed(env):
    hosted(env)
    with pytest.raises(wd.WatchdogUnavailable):
        env.proxy.stand_down()


# ── the whole path: MxcLaunch, the proxy, the host ──

def test_a_launch_registers_through_the_channel_and_a_clean_end_stands_the_host_down(
        env, wire):
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    host = host_mod.WatchdogHost(
        channel=env.host_channel, clock=env.clock, deadline_s=DEADLINE,
        core=(CORE_PID, CORE_TIME), identity_reader=env.world.identity,
        terminate=env.world.terminate, engage_sentinel=env.world.engage,
        journals=h.journal.journals)
    env.world.table[PID] = CREATION_TIME
    host.tick()
    h.launch.watchdog = env.proxy
    h.launch.start(job=h.job)
    assert journal_ops(h.journal) == ['intent', 'ownership']
    assert host.tick() == wd.ARMED and host.report()['recorded'] == ['e1-p1']
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == mxc_ledger.DEAD_CLEAN
    assert host.tick() == wd.STOOD_DOWN


def test_a_launch_is_never_resumed_while_the_host_is_absent(env, wire):
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    h.launch.watchdog = env.proxy
    with pytest.raises(wd.WatchdogUnavailable):
        h.launch.start(job=h.job)
    assert h.api.events.count('resume') == 0


def test_a_hung_core_ends_the_launch_the_host_watched(env, wire):
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    host = host_mod.WatchdogHost(
        channel=env.host_channel, clock=env.clock, deadline_s=DEADLINE,
        core=(CORE_PID, CORE_TIME), identity_reader=env.world.identity,
        terminate=env.world.terminate, engage_sentinel=env.world.engage,
        journals=h.journal.journals)
    env.world.table[PID] = CREATION_TIME
    host.tick()
    h.launch.watchdog = env.proxy
    h.launch.start(job=h.job)
    host.tick()
    env.clock.now += DEADLINE
    assert host.tick() == wd.FIRED
    assert events(env) == [('sentinel',), ('terminate', PID, CREATION_TIME)]
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == mxc_ledger.DEAD_UNVERIFIED


# ── the entry point ──

ARGV = ['--root', 'R', '--ledger', 'L', '--core-pid', str(CORE_PID),
        '--core-create-time', str(CORE_TIME), '--deadline-s', '10', '--poll-s', '1']


def argv(tmp_path):
    out = list(ARGV)
    out[1], out[3] = str(tmp_path / 'chan'), str(tmp_path / 'ledger')
    return out


def bindings(world, clock):
    return {'clock': clock, 'identity_reader': world.identity, 'terminate': world.terminate,
            'engage_sentinel': world.engage}


def test_the_host_is_closed_by_default(tmp_path, capsys):
    world = World()
    assert host_mod.HOST_ENABLED is False
    assert host_mod.main(argv(tmp_path), bindings=bindings(world, Clock())) == 2
    assert 'closed' in capsys.readouterr().err
    assert not (tmp_path / 'chan').exists()


def test_an_open_host_with_no_native_readers_still_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(host_mod, 'HOST_ENABLED', True)
    assert host_mod.main(argv(tmp_path)) == 2
    assert not (tmp_path / 'chan').exists()


def test_the_entry_point_runs_the_host_to_the_end_of_its_watch(tmp_path, monkeypatch):
    monkeypatch.setattr(host_mod, 'HOST_ENABLED', True)
    world, clock = World(), Clock()
    del world.table[CORE_PID]
    assert host_mod.main(argv(tmp_path), bindings=bindings(world, clock)) == 0
    world.table[CORE_PID] = 'x'
    assert host_mod.main(argv(tmp_path), bindings=bindings(world, clock)) == 3


@pytest.mark.parametrize('missing', ['--root', '--core-pid', '--deadline-s'])
def test_the_entry_point_needs_every_argument(tmp_path, missing):
    args_ = argv(tmp_path)
    at = args_.index(missing)
    del args_[at:at + 2]
    with pytest.raises(SystemExit):
        host_mod.main(args_)


def test_importing_the_host_spawns_nothing(monkeypatch):
    def spawn(*a, **k):
        raise AssertionError('spawned')

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    monkeypatch.setattr('os.system', spawn)
    importlib.reload(host_mod)
    importlib.reload(hb)
    assert host_mod.HOST_ENABLED is False and hb.HEARTBEAT_ENABLED is False


def test_the_channel_messages_are_plain_json(env):
    env.sender.beat()
    with open(env.core.path, encoding='ascii') as stream:
        assert json.loads(stream.readline())['kind'] == 'beat'
