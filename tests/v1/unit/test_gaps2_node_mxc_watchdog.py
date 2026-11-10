"""T-1015: the ten highest-risk uncovered branches of archeus/node/mxc_watchdog.py 1-202.

Source under test: archeus/node/mxc_watchdog.py, lines 1-202 inclusive (the whole module slice;
every line:NN below is inside that range). Fail-closed and denial first, then boundaries, then
error paths. Selected branches, in risk order:

 1. 128-131 beat before 143-144: a dead Core plus an unreadable heartbeat channel must leave the
    watchdog UNCERTAIN with no kill at all (the dead-Core decision is downstream of the read).
 2. 169-173: an identity read that fails AFTER an earlier job read cleanly must abandon the whole
    observation - no kill, and no partial per-job verdict for the job that read well.
 3. 141-142 (fall-through 141->143): an accepted heartbeat whose sent_at does not advance the quiet
    clock must not move it backwards, while last_seq still advances.
 4. 178: creation-time comparison is per record, not against the set of all recorded creation times
    - two records whose live creation times are cross-matched are BOTH somebody else's process.
 5. 176: a creation time that is equal in value but not an int (900.0) never authorizes a kill.
 6. 193-194: a kill that answers with something truthy but not True is KILL_UNVERIFIED, never a
    confirmation, and is never retried.
 7. 128-131: a channel that yields one beat and then raises mid-read applies NOTHING (no last_seq,
    no last_beat) and kills nothing.
 8. 141/145: a clock rewound below the last accepted beat (still >= armed_at) must not silently
    disarm the silence backstop forever (kept as a strict xfail: the source stays ARMED).
 9. 114-115: a repeated sweep from UNCERTAIN after a failed observation reads and kills nothing.
10. 167-183 vs 190-199: every recorded job is read to the end before the FIRST kill is requested.

Fakes only: clock, channel, core_alive, identity_reader and kill are the injected seams of
tests/v1/unit/test_mxc_watchdog.py (Clock, Channel, CoreAlive, beat, record, verdicts are imported
from there); no DLL is loaded, no process is created, no network, no sleep over 1 second, and every
path stays inside tmp-free pure objects, so the file is platform-neutral.
"""

from types import SimpleNamespace

import pytest

from archeus.node import mxc_watchdog as watchdog

from .test_mxc_watchdog import (Channel, Clock, CoreAlive, beat, make, record, verdicts)


class Log:
    """One shared timeline so the ORDER of identity reads and kill requests is observable."""

    def __init__(self):
        self.entries = []


class Identity:
    """identity_reader seam: answers the live creation time of a pid, None if absent, raises for
    the pids named in fail_on (a read the watchdog is not allowed to reason about)."""

    def __init__(self, log, table=None, fail_on=()):
        self.log, self.reads = log, []
        self.table, self.fail_on = dict(table or {}), tuple(fail_on)

    def __call__(self, pid):
        self.reads.append(pid)
        self.log.entries.append(('read', pid))
        if pid in self.fail_on:
            raise OSError('identity store refused the read')
        return self.table.get(pid)


class Kill:
    """kill seam: records every request in call order, answers anything, raises per job_ref."""

    def __init__(self, log, answer=True, errors=()):
        self.log, self.killed = log, []
        self.answer, self.errors = answer, list(errors)

    def __call__(self, job_ref):
        self.killed.append(job_ref)
        self.log.entries.append(('kill', job_ref))
        for ref, error in self.errors:
            if ref is job_ref:
                raise error
        return self.answer


class HalfChannel:
    """channel seam that hands out its beats and THEN raises, so the read dies half way through."""

    def __init__(self, beats, error):
        self.beats, self.error, self.reads = list(beats), error, 0

    def __call__(self):
        self.reads += 1
        return self._stream()

    def _stream(self):
        for row in self.beats:
            yield dict(row)
        raise self.error


def rig(now=100.0, deadline_s=30.0, alive=True, batches=((),), table=None, fail_on=(),
        kill_answer=True, kill_errors=(), channel=None):
    log = Log()
    world = SimpleNamespace(log=log, clock=Clock(now),
                            channel=channel if channel is not None else Channel(batches),
                            core_alive=CoreAlive(alive), identities=Identity(log, table, fail_on),
                            kill=Kill(log, kill_answer, kill_errors))
    world.watchdog = watchdog.Watchdog(clock=world.clock, deadline_s=deadline_s,
                                       channel=world.channel, core_alive=world.core_alive,
                                       identity_reader=world.identities, kill=world.kill)
    return world


def observed(watch):
    return [(row['execution_id'], row['verdict']) for row in watch.report()['verdicts']]


def test_a_dead_core_with_an_unreadable_heartbeat_channel_asks_for_no_kill():
    # 1. tick() reads the channel (128-131) BEFORE it looks at alive (143-144): with the Core dead
    # and the channel unreadable the watchdog must still be UNCERTAIN and ask for no kill at all.
    world = rig(alive=False, table={41: 900})
    ref = record(world.watchdog)
    world.channel.error = OSError('heartbeat pipe down')
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    report = world.watchdog.report()
    assert report['reason'] == 'heartbeat channel read failed'
    assert report['verdicts'] == [{'execution_id': None, 'verdict': 'UNCERTAIN',
                                   'reason': 'heartbeat channel read failed'}]
    assert world.log.entries == []          # the dead-Core observation never started
    assert world.kill.killed == [] and ref not in world.kill.killed
    assert world.core_alive.reads == 1 and world.channel.reads == 1


def test_an_identity_read_that_fails_half_way_through_kills_nobody():
    # 2. _observe() returns `None, 'identity read failed'` (172-173): the job that read cleanly is
    # NOT carried into the fire loop, so nobody is killed and no partial verdict is recorded.
    world = rig(table={41: 900}, fail_on=(42,))
    ref_a = record(world.watchdog, 'e1', 41, 900)
    ref_b = record(world.watchdog, 'e2', 42, 901)
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    report = world.watchdog.report()
    assert report['reason'] == 'identity read failed'
    assert world.kill.killed == [] and ref_a not in world.kill.killed
    assert ref_b not in world.kill.killed
    assert world.identities.reads == [41, 42]     # the read was attempted to the end, not bailed
    assert [row['execution_id'] for row in report['verdicts']] == [None]
    assert observed(world.watchdog) == [(None, watchdog.UNCERTAIN)]
    assert verdicts(world.watchdog) == {}   # no per-job verdict survived the failed sweep


def test_a_late_heartbeat_never_moves_the_quiet_clock_back():
    # 3. Line 141-142: the second beat is valid (new seq, inside the window) but older, so last_beat
    # has to stay at 120 and the deadline is still measured from 120. The 141->143 fall-through is
    # the one arc no existing test in the slice reaches.
    world = rig(table={41: 900}, batches=([beat(1, 120), beat(2, 105)], []))
    ref = record(world.watchdog)
    world.clock.now = 130.0                 # both beats sit inside [armed_at, now]
    assert world.watchdog.tick() == watchdog.ARMED
    assert world.watchdog.last_seq == 2 and world.watchdog.report()['last_beat'] == 120
    world.clock.now = 140.0                       # 20 s of quiet: still inside the deadline
    assert world.watchdog.tick() == watchdog.ARMED
    assert world.kill.killed == []
    world.clock.now = 150.5                       # 30.5 s from 120, 45.5 s from 105
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.watchdog.report()['reason'] == 'core_silent' and world.kill.killed == [ref]


def test_creation_times_that_match_another_job_never_authorize_a_kill():
    # 4. Line 178 compares the live creation time with THIS record's, not with everything recorded:
    # pid 41 answers with 901 (e2's time) and pid 42 with 900 (e1's time), so both are somebody
    # else's process and the fire ends with two skips and not one kill request.
    world = rig(table={41: 901, 42: 900})
    ref_a = record(world.watchdog, 'e1', 41, 900)
    ref_b = record(world.watchdog, 'e2', 42, 901)
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.identities.reads == [41, 42]
    assert world.kill.killed == [] and ref_a not in world.kill.killed
    assert ref_b not in world.kill.killed
    assert verdicts(world.watchdog) == {'e1': watchdog.SKIPPED_REUSED_PID,
                                        'e2': watchdog.SKIPPED_REUSED_PID}


@pytest.mark.parametrize('answer', [900.0, True, '900'])
def test_a_creation_time_that_is_not_an_int_never_authorizes_a_kill(answer):
    # 5. Line 176 keeps `type(current) is not int` in front of the 178 comparison: 900.0 == 900 and
    # '900' are not proof of identity, so the sweep is UNCERTAIN instead of a kill.
    world = rig(alive=False, table={41: answer})
    ref = record(world.watchdog)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.watchdog.report()['reason'] == 'malformed identity observation'
    assert world.kill.killed == [] and ref not in world.kill.killed
    assert world.identities.reads == [41]


@pytest.mark.parametrize('answer', [1, 0.5, 'confirmed', [0]])
def test_a_kill_that_answers_truthy_but_not_true_is_no_confirmation(answer):
    # 6. Lines 193-194 ask `self.kill(...) is not True`: a truthy answer is KILL_UNVERIFIED, the
    # verdict is UNCERTAIN, and the second tick must not re-ask for the kill.
    world = rig(table={41: 900}, kill_answer=answer)
    ref = record(world.watchdog)
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.watchdog.report()['reason'] == 'kill not verified'
    assert verdicts(world.watchdog) == {'e1': watchdog.KILL_UNVERIFIED}
    assert world.kill.killed == [ref]
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.kill.killed == [ref]


def test_a_channel_that_raises_after_one_beat_applies_nothing():
    # 7. Line 129 reads the channel to the end inside one `list(...)`; when it dies after the first
    # beat, that beat must not be applied: no last_seq, no last_beat, no verdict, no kill.
    error = OSError('heartbeat pipe lost mid-read')
    world = rig(table={41: 900}, channel=HalfChannel([beat(1, 120)], error))
    ref = record(world.watchdog)
    world.clock.now = 130.0                 # the beat would have been accepted if the read finished
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    report = world.watchdog.report()
    assert report['reason'] == 'heartbeat channel read failed'
    assert report['last_beat'] is None and world.watchdog.last_seq == 0
    assert report['verdicts'] == [{'execution_id': None, 'verdict': 'UNCERTAIN',
                                   'reason': 'heartbeat channel read failed'}]
    assert world.kill.killed == [] and ref not in world.kill.killed


@pytest.mark.xfail(strict=True,
                   reason='archeus/node/mxc_watchdog.py:145 (with 141-142 and 155-156) compares '
                          'now - _quiet_since() against deadline_s with no lower bound while 120 '
                          'only checks now >= armed_at: after the clock is rewound below an already '
                          'accepted last_beat the difference is negative, so tick() answers ARMED '
                          'for ever instead of the fail-closed UNCERTAIN and the silence backstop '
                          'can be disarmed by any clock rewind')
def test_a_clock_rewound_below_the_last_beat_is_not_a_quiet_forever():
    # 8. Line 68 refuses a beat with sent_at > now, so the module's own invariant is
    # last_beat <= now. Once the clock goes backwards under an accepted last_beat, line 145
    # subtracts to a negative number and the silence backstop can never fire again while the Core
    # says it is alive: fail-closed demands UNCERTAIN, the source stays ARMED and never fires.
    world = rig(table={41: 900}, batches=([beat(1, 129)], []))
    ref = record(world.watchdog)
    world.clock.now = 130.0
    assert world.watchdog.tick() == watchdog.ARMED          # beat accepted, last_beat = 129
    world.clock.now = 110.0                                 # >= armed_at (100), < last_beat
    assert world.watchdog.tick() == watchdog.UNCERTAIN      # fail-closed expectation
    assert world.watchdog.report()['reason'] == 'malformed clock observation'
    assert world.kill.killed == [] and ref not in world.kill.killed


def test_a_second_sweep_after_a_failed_observation_reads_and_kills_nothing():
    # 9. Lines 114-115 are the only thing between an UNCERTAIN verdict and another sweep: repeated
    # ticks must not re-read the channel, must not re-read identities and must not ask for a kill.
    world = rig(table={41: 900, 42: 901}, fail_on=(42,))
    record(world.watchdog, 'e1', 41, 900)
    record(world.watchdog, 'e2', 42, 901)
    world.clock.advance(31)
    assert world.watchdog.tick() == watchdog.UNCERTAIN
    reads, channel_reads, alive_reads = (list(world.identities.reads), world.channel.reads,
                                         world.core_alive.reads)
    verdict_rows = list(world.watchdog.report()['verdicts'])
    for _ in range(3):
        world.clock.advance(10)
        assert world.watchdog.tick() == watchdog.UNCERTAIN
    assert world.identities.reads == reads == [41, 42]
    assert world.channel.reads == channel_reads == 1 and world.core_alive.reads == alive_reads == 1
    assert world.kill.killed == []
    assert world.watchdog.report()['verdicts'] == verdict_rows


def test_every_recorded_job_is_read_before_the_first_kill_is_asked():
    # 10. _observe (167-183) runs to the end of self.jobs and only then does _fire (190-199) ask for
    # any kill: one shared timeline proves the reads of all three jobs precede the single kill, in
    # record order, and that an absent or reused pid never reaches the kill seam.
    world = rig(alive=False, table={41: 900, 42: None, 43: 902})
    ref_a = record(world.watchdog, 'e1', 41, 900)
    ref_b = record(world.watchdog, 'e2', 42, 901)
    ref_c = record(world.watchdog, 'e3', 43, 903)
    assert world.watchdog.tick() == watchdog.FIRED
    assert world.log.entries == [('read', 41), ('read', 42), ('read', 43), ('kill', ref_a)]
    assert world.kill.killed == [ref_a] and ref_b not in world.kill.killed
    assert ref_c not in world.kill.killed
    assert verdicts(world.watchdog) == {'e1': watchdog.KILLED,
                                        'e2': watchdog.ALREADY_ABSENT,
                                        'e3': watchdog.SKIPPED_REUSED_PID}
    assert world.watchdog.report()['reason'] == 'core_dead'


def test_the_imported_fixture_still_describes_an_armed_watchdog():
    # Guard for the imported fixtures themselves (make/Channel/CoreAlive): every rig above shares
    # them, so a change to test_mxc_watchdog.py's fakes has to break here first.
    world = make(table={41: 900})
    assert world.watchdog.state == watchdog.ARMED and world.watchdog.reason == 'armed'
    ref = record(world.watchdog)
    assert ref is not None and world.watchdog.report()['recorded'] == ['e1']
