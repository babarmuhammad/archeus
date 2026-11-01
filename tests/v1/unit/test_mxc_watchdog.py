from types import SimpleNamespace

import pytest

from archeus.node import mxc_watchdog as watchdog


class Clock:
    def __init__(self, now=100.0):
        self.now, self.error = now, None

    def __call__(self):
        if isinstance(self.error, Exception):
            raise self.error
        return self.now

    def advance(self, delta):
        self.now += delta


class Channel:
    def __init__(self, batches=((),), error=None):
        self.batches, self.error, self.reads = [list(b) for b in batches] or [[]], error, 0

    def __call__(self):
        self.reads += 1
        if isinstance(self.error, Exception):
            raise self.error
        return self.batches.pop(0) if len(self.batches) > 1 else self.batches[0]


class CoreAlive:
    def __init__(self, alive=True, error=None):
        self.alive, self.error, self.reads = alive, error, 0

    def __call__(self):
        self.reads += 1
        if isinstance(self.error, Exception):
            raise self.error
        return self.alive


class Identities:
    def __init__(self, table=None, error=None):
        self.table, self.error, self.reads = dict(table or {}), error, []

    def __call__(self, pid):
        self.reads.append(pid)
        if isinstance(self.error, Exception):
            raise self.error
        return self.table.get(pid)


class Killer:
    def __init__(self, result=True, error=None):
        self.result, self.error, self.by_ref, self.killed = result, error, {}, []

    def __call__(self, job_ref):
        self.killed.append(job_ref)
        for ref, err in self.by_ref.items():
            if ref is job_ref:
                raise err
        if isinstance(self.error, Exception):
            raise self.error
        return self.result


def make(now=100.0, deadline_s=30.0, alive=True, batches=((),), table=None, kill_result=True):
    world = SimpleNamespace(clock=Clock(now), channel=Channel(batches), core_alive=CoreAlive(alive),
                            identities=Identities(table), killer=Killer(kill_result))
    world.watchdog = watchdog.Watchdog(clock=world.clock, deadline_s=deadline_s,
                                       channel=world.channel, core_alive=world.core_alive,
                                       identity_reader=world.identities, kill=world.killer)
    return world


def beat(seq, sent_at):
    return {'seq': seq, 'sent_at': sent_at}


def record(watch, execution_id='e1', pid=41, create_time=900, ref=None):
    ref = object() if ref is None else ref
    watch.record({'execution_id': execution_id, 'pid': pid, 'create_time': create_time,
                  'job_ref': ref})
    return ref


def verdicts(watch):
    return {row['execution_id']: row['verdict'] for row in watch.report()['verdicts']
            if row['execution_id'] is not None}


def test_states_are_the_four_typed_states():
    assert watchdog.STATES == ('ARMED', 'FIRED', 'STOOD_DOWN', 'UNCERTAIN')
    assert make().watchdog.state == watchdog.ARMED


def test_healthy_core_keeps_the_watchdog_armed_and_reads_nothing():
    world = make(batches=([beat(1, 100)],), table={41: 900})
    ref = record(world.watchdog)
    assert world.watchdog.tick() == watchdog.ARMED
    assert world.killer.killed == []
    assert world.identities.reads == []
    assert world.watchdog.report()['verdicts'] == []
    assert world.watchdog.report()['last_beat'] == 100
    assert ref is not None


def test_fresh_heartbeat_defers_the_deadline():
    world = make(batches=([beat(1, 129)], [beat(2, 159)], [beat(3, 189)]), table={41: 900})
    record(world.watchdog)
    for _ in range(3):
        world.clock.advance(30)
        assert world.watchdog.tick() == watchdog.ARMED
    assert world.killer.killed == []


def test_heartbeat_then_silence_fires_from_the_last_beat():
    world = make(batches=([beat(1, 100)], []), table={41: 900})
    ref = record(world.watchdog)
    world.clock.advance(20)
    assert world.watchdog.tick() == watchdog.ARMED
    world.clock.advance(11)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.killer.killed == [ref]
    assert world.watchdog.report()['reason'] == 'core_silent'


def test_silence_below_the_deadline_does_not_fire():
    world = make(table={41: 900})
    ref = record(world.watchdog)
    world.clock.advance(29.999)
    assert world.watchdog.tick() == watchdog.ARMED
    assert world.killer.killed == []
    assert ref is not None


def test_silent_core_fires_and_kills_every_recorded_job():
    world = make(table={41: 900, 42: 901})
    ref_a, ref_b = record(world.watchdog, 'e1', 41, 900), record(world.watchdog, 'e2', 42, 901)
    world.clock.advance(30)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.killer.killed == [ref_a, ref_b]
    assert world.killer.killed[0] is ref_a
    assert verdicts(world.watchdog) == {'e1': watchdog.KILLED, 'e2': watchdog.KILLED}


def test_silence_fires_with_nothing_recorded():
    world = make()
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.killer.killed == []
    assert world.watchdog.report()['verdicts'] == [
        {'execution_id': None, 'verdict': 'FIRED', 'reason': 'core_silent'}]


def test_dead_core_fires_despite_a_fresh_heartbeat():
    world = make(alive=False, batches=([beat(1, 100)],), table={41: 900})
    ref = record(world.watchdog)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.killer.killed == [ref]
    assert world.identities.reads == [41]
    assert world.watchdog.report()['reason'] == 'core_dead'


def test_dead_core_without_observed_jobs_fires_without_a_kill():
    world = make(alive=False)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.killer.killed == []
    assert world.identities.reads == []


def test_reused_pid_is_never_killed():
    world = make(table={41: 900, 42: 902})
    ref_a = record(world.watchdog, 'e1', 41, 900)
    ref_b = record(world.watchdog, 'e2', 42, 901)
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.killer.killed == [ref_a]
    assert ref_b not in world.killer.killed
    assert verdicts(world.watchdog) == {'e1': watchdog.KILLED,
                                        'e2': watchdog.SKIPPED_REUSED_PID}


def test_absent_process_is_never_killed():
    world = make(table={41: None})
    record(world.watchdog)
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.killer.killed == []
    assert world.identities.reads == [41]
    assert verdicts(world.watchdog) == {'e1': watchdog.ALREADY_ABSENT}


def test_kill_failure_is_uncertain_and_is_never_retried():
    world = make(table={41: 900})
    ref = record(world.watchdog)
    world.killer.error = RuntimeError('kill transport down')
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert verdicts(world.watchdog) == {'e1': watchdog.KILL_FAILED}
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.killer.killed == [ref]


def test_kill_that_does_not_confirm_is_uncertain():
    world = make(table={41: 900}, kill_result=None)
    record(world.watchdog)
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert verdicts(world.watchdog) == {'e1': watchdog.KILL_UNVERIFIED}
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert len(world.killer.killed) == 1


def test_one_kill_failure_does_not_stop_the_other_kills():
    world = make(table={41: 900, 42: 901})
    ref_a, ref_b = record(world.watchdog, 'e1', 41, 900), record(world.watchdog, 'e2', 42, 901)
    world.killer.by_ref[ref_a] = RuntimeError('one kill down')
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.killer.killed == [ref_a, ref_b]
    assert verdicts(world.watchdog) == {'e1': watchdog.KILL_FAILED, 'e2': watchdog.KILLED}


def test_double_fire_is_refused():
    world = make(table={41: 900})
    ref = record(world.watchdog)
    world.clock.advance(40)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.killer.killed == [ref]
    assert world.core_alive.reads == world.channel.reads == 1


def test_recording_or_standing_down_after_firing_is_refused():
    world = make(table={41: 900})
    record(world.watchdog)
    world.clock.advance(40)
    assert world.watchdog.tick() == watchdog.FIRED
    with pytest.raises(watchdog.WatchdogUnavailable):
        world.watchdog.record({'execution_id': 'e2', 'pid': 42, 'create_time': 901,
                               'job_ref': object()})
    with pytest.raises(watchdog.WatchdogUnavailable):
        world.watchdog.stand_down('core_came_back')
    assert world.watchdog.report()['recorded'] == ['e1']


def test_stood_down_watchdog_never_kills():
    world = make(table={41: 900})
    record(world.watchdog)
    assert world.watchdog.stand_down('core_reclaimed') == watchdog.STOOD_DOWN
    world.clock.advance(100)
    world.core_alive.alive = False
    assert world.watchdog.tick() == watchdog.STOOD_DOWN
    assert world.killer.killed == []
    assert world.identities.reads == []
    assert world.watchdog.report()['reason'] == 'core_reclaimed'
    with pytest.raises(watchdog.WatchdogUnavailable):
        world.watchdog.stand_down()
    with pytest.raises(watchdog.WatchdogUnavailable):
        record(world.watchdog, 'e2', 42, 901)


@pytest.mark.parametrize('reader', ['clock', 'channel', 'core_alive', 'identity_reader'])
def test_reader_exception_is_uncertain_and_kills_nothing(reader):
    world = make(table={41: 900, 42: 901})
    record(world.watchdog, 'e1', 41, 900)
    record(world.watchdog, 'e2', 42, 901)
    fakes = {'clock': world.clock, 'channel': world.channel, 'core_alive': world.core_alive,
             'identity_reader': world.identities}
    fakes[reader].error = OSError('reader down')
    world.clock.advance(40)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.killer.killed == []
    assert world.watchdog.report()['verdicts'][-1]['verdict'] == watchdog.UNCERTAIN


MALFORMED = {
    'beat_without_seq': ('beat', {'sent_at': 100}, 'malformed heartbeat record'),
    'beat_without_sent_at': ('beat', {'seq': 1}, 'malformed heartbeat record'),
    'beat_extra_field': ('beat', dict(beat(1, 100), execution_id='e1'),
                         'malformed heartbeat record'),
    'beat_not_a_dict': ('beat', 42, 'malformed heartbeat record'),
    'beat_seq_is_bool': ('beat', {'seq': True, 'sent_at': 100}, 'malformed heartbeat record'),
    'beat_seq_replayed': ('beat', {'seq': 0, 'sent_at': 100}, 'replayed heartbeat sequence'),
    'beat_from_the_future': ('beat', {'seq': 1, 'sent_at': 1000},
                             'heartbeat outside the armed clock window'),
    'beat_negative': ('beat', {'seq': 1, 'sent_at': -1},
                      'heartbeat outside the armed clock window'),
    'beat_nan': ('beat', {'seq': 1, 'sent_at': float('nan')}, 'malformed heartbeat record'),
    'beat_sent_at_is_text': ('beat', {'seq': 1, 'sent_at': '100'}, 'malformed heartbeat record'),
    'channel_not_iterable': ('channel', 42, 'heartbeat channel read failed'),
    'core_alive_is_not_bool': ('alive', 'up', 'malformed core_alive observation'),
    'identity_is_bool': ('identity', True, 'malformed identity observation'),
    'identity_is_zero': ('identity', 0, 'malformed identity observation'),
    'identity_is_text': ('identity', '901', 'malformed identity observation'),
}


@pytest.mark.parametrize('damage', sorted(MALFORMED))
def test_malformed_observation_is_uncertain_and_kills_nothing(damage):
    kind, payload, reason = MALFORMED[damage]
    world = make(table={41: 900, 42: 901})
    record(world.watchdog, 'e1', 41, 900)
    record(world.watchdog, 'e2', 42, 901)
    if kind == 'beat':
        world.channel.batches = [[payload]]
    elif kind == 'channel':
        world.channel.batches = [payload]
    elif kind == 'alive':
        world.core_alive.alive = payload
    else:
        world.identities.table[42] = payload
    world.clock.advance(40)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.killer.killed == []
    assert world.watchdog.report()['verdicts'][-1]['reason'] == reason


def test_watchdog_holds_no_outer_job_handle():
    injected = dict(deadline_s=30.0, channel=Channel(), core_alive=CoreAlive(),
                    identity_reader=Identities(), kill=Killer())
    with pytest.raises(TypeError):
        watchdog.Watchdog(clock=Clock(), job=object(), **injected)
    with pytest.raises(TypeError):
        watchdog.Watchdog(Clock(), **injected)
    world = make(table={41: 900})
    assert not hasattr(world.watchdog, 'job')
    ref = record(world.watchdog)
    world.clock.advance(31)
    world.watchdog.tick()
    assert world.killer.killed[0] is ref


@pytest.mark.parametrize('change', [
    {'pid': 41, 'create_time': 900},
    dict(execution_id='e1', pid=41, create_time=900, job_ref=object(), extra=1),
    42,
    dict(execution_id='', pid=41, create_time=900, job_ref=object()),
    dict(execution_id='e1', pid=True, create_time=900, job_ref=object()),
    dict(execution_id='e1', pid=0, create_time=900, job_ref=object()),
    dict(execution_id='e1', pid=41, create_time='900', job_ref=object()),
    dict(execution_id='e1', pid=41, create_time=-900, job_ref=object()),
    dict(execution_id='e1', pid=41, create_time=900, job_ref=None),
])
def test_malformed_job_record_is_refused_without_recording(change):
    watch = make().watchdog
    with pytest.raises(watchdog.WatchdogUnavailable):
        watch.record(change)
    assert watch.report()['recorded'] == []
    assert watch.state == watchdog.ARMED


def test_duplicate_execution_and_job_ref_are_refused():
    watch = make().watchdog
    ref = record(watch, 'e1', 41, 900)
    with pytest.raises(watchdog.WatchdogUnavailable):
        watch.record({'execution_id': 'e1', 'pid': 42, 'create_time': 901, 'job_ref': object()})
    with pytest.raises(watchdog.WatchdogUnavailable):
        watch.record({'execution_id': 'e2', 'pid': 43, 'create_time': 902, 'job_ref': ref})
    assert watch.report()['recorded'] == ['e1']


@pytest.mark.parametrize('missing', ['clock', 'channel', 'core_alive', 'identity_reader', 'kill'])
def test_every_reader_must_be_injected(missing):
    injected = dict(clock=Clock(), deadline_s=30.0, channel=Channel(), core_alive=CoreAlive(),
                    identity_reader=Identities(), kill=Killer())
    injected[missing] = None
    with pytest.raises(watchdog.WatchdogUnavailable):
        watchdog.Watchdog(**injected)


@pytest.mark.parametrize('deadline', [0, -1, None, '30', True, float('nan'), float('inf')])
def test_deadline_must_be_a_positive_number(deadline):
    with pytest.raises(watchdog.WatchdogUnavailable):
        watchdog.Watchdog(clock=Clock(), deadline_s=deadline, channel=Channel(),
                          core_alive=CoreAlive(), identity_reader=Identities(), kill=Killer())


def test_clock_that_cannot_be_read_at_arm_time_refuses_to_arm():
    clock = Clock()
    clock.error = OSError('clock down')
    with pytest.raises(watchdog.WatchdogUnavailable):
        watchdog.Watchdog(clock=clock, deadline_s=30.0, channel=Channel(), core_alive=CoreAlive(),
                          identity_reader=Identities(), kill=Killer())


@pytest.mark.parametrize('armed_at', ['100', None, True, float('nan'), -1])
def test_clock_that_is_unreadable_at_arm_time_refuses_to_arm(armed_at):
    with pytest.raises(watchdog.WatchdogUnavailable):
        watchdog.Watchdog(clock=lambda: armed_at, deadline_s=30.0, channel=Channel(),
                          core_alive=CoreAlive(), identity_reader=Identities(), kill=Killer())


@pytest.mark.parametrize('now', ['140', None, True, float('nan'), 50.0])
def test_malformed_clock_observation_is_uncertain_and_kills_nothing(now):
    world = make(table={41: 900})
    record(world.watchdog)
    world.clock.now = now
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.killer.killed == []


@pytest.mark.parametrize('reason', ['', None, 0, 'in\x00valid'])
def test_stood_down_requires_a_usable_reason(reason):
    with pytest.raises(watchdog.WatchdogUnavailable):
        make().watchdog.stand_down(reason)


def test_report_is_a_copy_of_the_recorded_verdicts():
    world = make(table={41: 900, 42: 902})
    record(world.watchdog, 'e1', 41, 900)
    record(world.watchdog, 'e2', 42, 901)
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.FIRED
    report = world.watchdog.report()
    assert set(report) == {'state', 'reason', 'deadline_s', 'armed_at', 'last_beat', 'recorded',
                          'verdicts'}
    assert report['state'] == watchdog.FIRED and report['reason'] == 'core_silent'
    assert report['recorded'] == ['e1', 'e2'] and report['armed_at'] == 100.0
    assert report['verdicts'][:2] == [
        {'execution_id': 'e1', 'verdict': 'KILLED', 'reason': 'core_silent'},
        {'execution_id': 'e2', 'verdict': 'SKIPPED_REUSED_PID',
         'reason': 'pid creation time differs from record'}]
    report['verdicts'].append({'execution_id': 'e3', 'verdict': 'forged'})
    assert len(world.watchdog.report()['verdicts']) == 3
