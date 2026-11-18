"""T-1419: the uncovered branches of `archeus/node/mxc_watchdog.py` lines 48-120:
_job_problem, _heartbeat_problem, the Watchdog constructor, record, stand_down and the
head of tick (the clock read).

Ten selected probes, denial and fail-closed first, then boundaries, then error paths:

1  _job_problem 49-50       a non-dict or a wrong key set is a malformed job record
                            -> test_a_job_record_of_the_wrong_shape_is_refused
2  _job_problem 51-52       an empty, NUL-holding or non-text execution_id is refused
                            -> test_an_unusable_execution_id_is_refused
3  _job_problem 53-55       pid and create_time: bool, float, zero, negative refused; positive int accepted
                            -> test_pid_and_create_time_must_be_positive_ints
4  _job_problem 56-57       job_ref None is refused; any other value passes -> test_only_a_none_job_ref_is_refused
5  _heartbeat_problem 62-65 wrong shape, non-int seq, bool or non-number sent_at are malformed
                            -> test_a_malformed_heartbeat_stops_the_watchdog
6  _heartbeat_problem 66-67 seq equal to or below last_seq is a replay; one above is accepted
                            -> test_a_replayed_heartbeat_sequence_is_refused
                            -> test_the_next_heartbeat_sequence_is_accepted
7  _heartbeat_problem 68-69 sent_at equal to armed_at or to now is accepted; outside the window is refused
                            -> test_a_heartbeat_at_the_window_edges_is_accepted
                            -> test_a_heartbeat_outside_the_armed_window_is_refused
8  __init__ 75-92           a bad deadline, a missing reader, a clock that raises, returns a
                            non-number or a negative value are refused at construction
                            -> test_a_bad_deadline_is_refused
                            -> test_a_missing_reader_is_named
                            -> test_a_clock_unusable_at_arm_time_is_refused
9  record 96-106            a terminal watchdog refuses; a repeated execution_id or job_ref is refused;
                            a stored job is a copy -> test_a_terminal_watchdog_refuses_a_record
                            -> test_a_repeated_execution_or_job_ref_is_refused
                            -> test_a_recorded_job_is_a_copy
10 stand_down 108-112 and tick 114-120  a non-text reason and a terminal watchdog are refused; a valid
                            reason sets STOOD_DOWN; an ARMED tick reads the clock, a raising clock is UNCERTAIN
                            -> test_stand_down_needs_a_text_reason_and_one_go
                            -> test_a_tick_reads_the_clock_and_a_raising_clock_is_uncertain

Only the constructor, record, stand_down and tick are called. The clock is scripted, the channel
returns a fixed list, core_alive answers True, identity_reader and kill are recording fakes, and kill
is never called. No real clock, process table, ledger or process is touched.
"""

import pytest

from archeus.node import mxc_watchdog as wd


class Clock:
    """A settable clock; an item that is an exception is raised instead of returned."""

    def __init__(self, value=0.0):
        self.value = value
        self.reads = 0

    def __call__(self):
        self.reads += 1
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class Channel:
    def __init__(self, beats=()):
        self.beats = list(beats)

    def __call__(self):
        return list(self.beats)


class Recorder:
    def __init__(self, answer=None):
        self.answer = answer
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.answer


def make(clock=None, channel=None, core_alive=None, identity_reader=None, kill=None,
         deadline_s=10.0):
    return wd.Watchdog(clock=clock if clock is not None else Clock(0.0),
                       deadline_s=deadline_s,
                       channel=channel if channel is not None else Channel(),
                       core_alive=core_alive if core_alive is not None else (lambda: True),
                       identity_reader=identity_reader if identity_reader is not None else Recorder(),
                       kill=kill if kill is not None else Recorder(answer=True))


def job(**changes):
    base = {'execution_id': 'exec-1', 'pid': 4242, 'create_time': 1700000000,
            'job_ref': 'job-ref-1'}
    base.update(changes)
    return base


def beat(**changes):
    base = {'seq': 1, 'sent_at': 0.0}
    base.update(changes)
    return base


# ── 1-4: job records ────────────────────────────────────────────────────────

@pytest.mark.parametrize('record', [
    ['execution_id', 'pid'],
    job(extra=1),
    {k: v for k, v in job().items() if k != 'job_ref'},
    'not-a-dict',
    None,
], ids=['list', 'extra-key', 'missing-key', 'text', 'none'])
def test_a_job_record_of_the_wrong_shape_is_refused(record):
    with pytest.raises(wd.WatchdogUnavailable, match='malformed job record'):
        make().record(record)


@pytest.mark.parametrize('execution_id', ['', '\0x', 7, None],
                         ids=['empty', 'nul', 'number', 'none'])
def test_an_unusable_execution_id_is_refused(execution_id):
    with pytest.raises(wd.WatchdogUnavailable, match='invalid execution id'):
        make().record(job(execution_id=execution_id))


@pytest.mark.parametrize('field, value', [
    ('pid', True), ('pid', 1.0), ('pid', 0), ('pid', -3),
    ('create_time', True), ('create_time', 2.5), ('create_time', 0), ('create_time', -1),
], ids=['pid-bool', 'pid-float', 'pid-zero', 'pid-negative',
        'time-bool', 'time-float', 'time-zero', 'time-negative'])
def test_pid_and_create_time_must_be_positive_ints(field, value):
    with pytest.raises(wd.WatchdogUnavailable, match='invalid ' + field):
        make().record(job(**{field: value}))


def test_a_positive_int_pid_and_create_time_are_accepted():
    watchdog = make()
    assert watchdog.record(job(pid=1, create_time=1)) is True


def test_only_a_none_job_ref_is_refused():
    with pytest.raises(wd.WatchdogUnavailable, match='missing job ref'):
        make().record(job(job_ref=None))
    watchdog = make()
    assert watchdog.record(job(job_ref=123)) is True


# ── 5-7: heartbeats (through tick, the only caller) ─────────────────────────

def armed(channel, clock_at=0.0, now=1.0, **kw):
    clock = Clock(clock_at)
    watchdog = make(clock=clock, channel=channel, **kw)
    clock.value = now
    return watchdog


@pytest.mark.parametrize('beats, reason', [
    ([{'seq': 1}], 'malformed heartbeat record'),
    ([beat(extra=1)], 'malformed heartbeat record'),
    ([beat(seq=1.0)], 'malformed heartbeat record'),
    ([beat(seq=True)], 'malformed heartbeat record'),
    ([beat(sent_at=True)], 'malformed heartbeat record'),
    ([beat(sent_at='0')], 'malformed heartbeat record'),
    ('not-a-list-of-beats', 'malformed heartbeat record'),
], ids=['missing-key', 'extra-key', 'float-seq', 'bool-seq', 'bool-sent', 'text-sent', 'bad-shape'])
def test_a_malformed_heartbeat_stops_the_watchdog(beats, reason):
    if isinstance(beats, str):
        watchdog = armed(Channel(), now=1.0)
        watchdog.channel = lambda: [beats]
    else:
        watchdog = armed(Channel(beats))
    assert watchdog.tick() == wd.UNCERTAIN
    assert watchdog.reason == reason


def test_a_replayed_heartbeat_sequence_is_refused():
    channel = Channel([beat(seq=1, sent_at=0.5)])
    watchdog = armed(channel, now=1.0)
    assert watchdog.tick() == wd.ARMED
    channel.beats = [beat(seq=1, sent_at=0.6)]
    watchdog.clock.value = 2.0
    assert watchdog.tick() == wd.UNCERTAIN
    assert watchdog.reason == 'replayed heartbeat sequence'


def test_a_heartbeat_sequence_below_or_equal_the_last_is_a_replay():
    watchdog = armed(Channel([beat(seq=0, sent_at=0.0)]), now=1.0)
    assert watchdog.tick() == wd.UNCERTAIN
    assert watchdog.reason == 'replayed heartbeat sequence'


def test_the_next_heartbeat_sequence_is_accepted():
    watchdog = armed(Channel([beat(seq=1, sent_at=0.5)]), now=1.0)
    assert watchdog.tick() == wd.ARMED
    assert watchdog.last_seq == 1


@pytest.mark.parametrize('sent_at, now', [(0.0, 1.0), (1.0, 1.0)],
                         ids=['equal-to-armed', 'equal-to-now'])
def test_a_heartbeat_at_the_window_edges_is_accepted(sent_at, now):
    watchdog = armed(Channel([beat(seq=1, sent_at=sent_at)]), clock_at=0.0, now=now)
    assert watchdog.tick() == wd.ARMED
    assert watchdog.last_beat == sent_at


@pytest.mark.parametrize('sent_at', [-0.5, 1.5], ids=['before-armed', 'after-now'])
def test_a_heartbeat_outside_the_armed_window_is_refused(sent_at):
    watchdog = armed(Channel([beat(seq=1, sent_at=sent_at)]), clock_at=0.0, now=1.0)
    assert watchdog.tick() == wd.UNCERTAIN
    assert watchdog.reason == 'heartbeat outside the armed clock window'


# ── 8: the constructor ──────────────────────────────────────────────────────

@pytest.mark.parametrize('deadline', [0, -1.0, True, 'ten', None],
                         ids=['zero', 'negative', 'bool', 'text', 'none'])
def test_a_bad_deadline_is_refused(deadline):
    with pytest.raises(wd.WatchdogUnavailable, match='deadline must be a positive number'):
        make(deadline_s=deadline)


@pytest.mark.parametrize('name', ['clock', 'channel', 'core_alive', 'identity_reader', 'kill'])
def test_a_missing_reader_is_named(name):
    readers = {'clock': Clock(0.0), 'channel': Channel(), 'core_alive': lambda: True,
               'identity_reader': Recorder(), 'kill': Recorder()}
    readers[name] = 'not-callable'
    with pytest.raises(wd.WatchdogUnavailable, match=name + ' must be injected'):
        wd.Watchdog(deadline_s=10.0, **readers)


@pytest.mark.parametrize('clock_value', [RuntimeError('clock down'), 'soon', True, -1.0, float('nan')],
                         ids=['raises', 'text', 'bool', 'negative', 'nan'])
def test_a_clock_unusable_at_arm_time_is_refused(clock_value):
    clock = Clock(clock_value)
    with pytest.raises(wd.WatchdogUnavailable) as err:
        make(clock=clock)
    assert str(err.value) in ('clock unreadable at arm time', 'clock malformed at arm time')
    assert clock.reads == 1


# ── 9: record ───────────────────────────────────────────────────────────────

def test_a_terminal_watchdog_refuses_a_record():
    watchdog = make()
    watchdog.stand_down('done')
    with pytest.raises(wd.WatchdogUnavailable, match='cannot record a job from STOOD_DOWN'):
        watchdog.record(job())
    assert watchdog.jobs == []


def test_a_repeated_execution_or_job_ref_is_refused():
    watchdog = make()
    watchdog.record(job())
    with pytest.raises(wd.WatchdogUnavailable, match='execution already recorded'):
        watchdog.record(job(job_ref='other-ref'))
    with pytest.raises(wd.WatchdogUnavailable, match='job ref already recorded'):
        watchdog.record(job(execution_id='exec-2'))
    assert len(watchdog.jobs) == 1


def test_a_recorded_job_is_a_copy():
    watchdog = make()
    source = job()
    watchdog.record(source)
    source['pid'] = 1
    source['execution_id'] = 'changed'
    assert watchdog.jobs == [job()]


# ── 10: stand_down and the tick head ────────────────────────────────────────

@pytest.mark.parametrize('reason', [7, '', None], ids=['number', 'empty', 'none'])
def test_stand_down_needs_a_text_reason(reason):
    watchdog = make()
    with pytest.raises(wd.WatchdogUnavailable, match='invalid stand-down reason'):
        watchdog.stand_down(reason)
    assert watchdog.state == wd.ARMED


def test_stand_down_needs_one_go():
    watchdog = make()
    assert watchdog.stand_down('operator') == wd.STOOD_DOWN
    assert watchdog.state == wd.STOOD_DOWN and watchdog.reason == 'operator'
    with pytest.raises(wd.WatchdogUnavailable, match='cannot stand down from STOOD_DOWN'):
        watchdog.stand_down('again')


def test_a_tick_reads_the_clock_and_a_raising_clock_is_uncertain():
    clock = Clock(0.0)
    kills, alive = Recorder(), Recorder(answer=True)
    watchdog = make(clock=clock, core_alive=lambda: True, kill=kills)
    clock.value = 1.0
    assert watchdog.tick() == wd.ARMED
    assert clock.reads == 2                                # arm, then the tick

    clock.value = RuntimeError('clock vanished')
    assert watchdog.tick() == wd.UNCERTAIN
    assert watchdog.reason == 'clock read failed'
    assert kills.calls == []
