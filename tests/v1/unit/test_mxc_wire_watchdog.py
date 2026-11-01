# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-803: the launch's Job is recorded with an injected watchdog before the resume, and
a clean end retires it; the tick stays the caller's. Same fakes as the wire tests."""

import pytest

from archeus.node import local, mxc_ledger as ledger_mod, mxc_watchdog as wd_mod, staging

from .test_mxc_wire import (CREATION_TIME, PID, args, journal_ops,  # noqa: F401
                            native_parts, wire)

OK = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
FOREIGN = {'execution_id': 'other', 'pid': 7, 'create_time': 70, 'job_ref': 'other-job'}


def watchdog(alive=True, kill=lambda ref: True, identity=lambda pid: CREATION_TIME):
    state = {'alive': alive, 'kills': []}

    def kill_job(ref):
        state['kills'].append(ref)
        return kill(ref)

    dog = wd_mod.Watchdog(clock=lambda: 0.0, deadline_s=10, channel=lambda: [],
                          core_alive=lambda: state['alive'], identity_reader=identity,
                          kill=kill_job)
    dog.state_of_world = state
    return dog


def started(wire, dog, **options):
    h = wire(**dict(OK, **options))
    h.launch.watchdog = dog
    h.launch.start(job=h.job)
    return h


def test_the_job_is_recorded_before_the_resume_and_after_the_ownership(wire):
    dog = watchdog()
    h = wire(**OK)
    h.launch.watchdog = dog
    seen = []
    real = h.api.resume_thread

    def resume_thread(thread):
        seen.append((journal_ops(h.journal), list(dog.jobs)))
        return real(thread)

    h.api.resume_thread = resume_thread
    h.launch.start(job=h.job)
    job = {'execution_id': 'e1-p1', 'pid': PID, 'create_time': CREATION_TIME, 'job_ref': h.job}
    assert seen == [(['intent', 'ownership'], [job])]
    h.launch.process.terminate()


def test_a_clean_end_stands_the_watchdog_down(wire):
    dog = watchdog()
    h = started(wire, dog)
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN
    assert dog.state == wd_mod.STOOD_DOWN


def test_an_unclean_end_leaves_the_watchdog_armed(wire):
    dog = watchdog()
    h = started(wire, dog, reader=lambda execution_id, owner: None)
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert dog.state == wd_mod.ARMED


def test_a_watchdog_shared_with_another_job_stays_armed(wire):
    dog = watchdog()
    dog.record(FOREIGN)
    h = started(wire, dog)
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN
    assert dog.state == wd_mod.ARMED and dog.report()['recorded'] == ['other', 'e1-p1']


@pytest.mark.parametrize('failure', [wd_mod.WatchdogUnavailable('refused'), OSError('lost')])
def test_a_job_that_cannot_be_recorded_never_resumes(wire, failure):
    dog = watchdog()

    def record(job):
        raise failure

    dog.record = record
    h = wire(**OK)
    h.launch.watchdog = dog
    with pytest.raises(type(failure)):
        h.launch.start(job=h.job)
    assert h.api.events.count('resume') == 0 and h.api.events.count('kill') == 1
    assert h.api.handles == {} and h.launch.process is None
    assert journal_ops(h.journal)[-1] == 'quarantine'
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_a_watchdog_that_fired_ends_the_launch_not_clean(wire):
    dog = watchdog()
    h = started(wire, dog)
    dog.state_of_world['alive'] = False
    assert dog.tick() == wd_mod.FIRED
    assert dog.state_of_world['kills'] == [h.job]
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops


def test_a_watchdog_that_lost_its_reading_ends_the_launch_not_clean(wire):
    dog = watchdog()
    h = started(wire, dog)
    dog.core_alive = lambda: 'maybe'
    assert dog.tick() == wd_mod.UNCERTAIN
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert 'completion' not in journal_ops(h.journal)


def test_a_watchdog_stood_down_by_someone_else_is_not_a_clean_end(wire):
    dog = watchdog()
    h = started(wire, dog)
    dog.stand_down('operator')
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_a_watchdog_that_cannot_stand_down_is_not_a_clean_end(wire):
    dog = watchdog()
    h = started(wire, dog)

    def stand_down(reason='x'):
        raise wd_mod.WatchdogUnavailable('refused')

    dog.stand_down = stand_down
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops


def test_a_watchdog_without_a_journalled_launch_is_refused(args):
    with pytest.raises(staging.StageError, match='journalled'):
        local.MxcLaunch(backend=object(), outcome=lambda process: 0, watchdog=watchdog(),
                        **args)


def test_the_default_has_no_watchdog_and_ends_as_before(wire):
    h = wire(**OK)
    h.launch.start(job=h.job)
    assert h.launch.watchdog is None and h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN


def test_a_shared_watchdog_that_fired_is_never_a_clean_end(wire):
    dog = watchdog()
    dog.record(FOREIGN)
    h = started(wire, dog)
    dog.state_of_world['alive'] = False
    assert dog.tick() == wd_mod.FIRED
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert 'completion' not in journal_ops(h.journal)
