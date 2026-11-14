# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""Findings of the self-review of the five wiring slices: an ending that cannot be
half-written, a clock or bound that cannot hang it, and a cancel that races the start.
Same fakes as the wire tests."""

import threading

import pytest

from archeus.node import local, mxc_ledger as ledger_mod, staging

from .test_mxc_wire import args, journal_ops, native_parts, wire  # noqa: F401

OK = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)


def started(wire, **options):
    h = wire(**dict(OK, **options))
    h.launch.start(job=h.job)
    return h


@pytest.mark.parametrize('bound', [float('nan'), float('inf'), -1, -0.5, '1', None])
def test_an_unusable_quiescence_bound_is_refused(args, wire, bound):
    h = wire()
    with pytest.raises(staging.StageError, match='quiescence bound'):
        local.MxcLaunch(api=h.api, boundary=h.boundary, ledger=h.journal,
                        schema_validator=lambda raw: True, execution_id='e9',
                        outcome=lambda process: 0, quiescence_wait=bound, **args)


@pytest.mark.parametrize('reading', [float('nan'), float('inf')])
def test_a_clock_with_no_usable_reading_never_proves_quiescence(wire, reading):
    h = started(wire)
    h.launch.clock = lambda: reading
    state = h.launch.cancel(outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert 'no usable reading' in state['quiescence']
    assert 'completion' not in journal_ops(h.journal)


@pytest.mark.parametrize('reading', [None, 'late'])
def test_a_clock_that_is_not_a_number_ends_unverified(wire, reading):
    h = started(wire)
    h.launch.clock = lambda: reading
    assert h.launch.cancel(outcome=0)['state'] == ledger_mod.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops


def test_a_ledger_that_cannot_be_read_at_the_end_still_ends_the_launch(wire):
    h = started(wire)

    def journals():
        raise OSError('ledger unreadable')

    h.journal.journals = journals
    state = h.launch.cancel(outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.cancel() is state and h.launch.end_state is state
    assert h.api.handles == {}


def test_a_callback_that_cancels_again_does_not_deadlock_the_ending(wire):
    h = started(wire)
    inner = []
    h.launch._end_job = lambda job: inner.append(h.launch.cancel(reason='again'))
    results = []
    thread = threading.Thread(target=lambda: results.append(h.launch.cancel(outcome=0)),
                              daemon=True)
    thread.start()
    thread.join(5)
    assert not thread.is_alive() and inner == [None]
    assert results[0]['state'] == ledger_mod.DEAD_CLEAN


def test_a_cancel_that_lands_before_the_resume_stops_the_resume(wire):
    h = wire(**OK)
    real = h.api.create_process_w
    seen = []

    def create_process_w(**kwargs):
        made = real(**kwargs)
        seen.append(h.launch.cancel(reason='host asked'))
        return made

    h.api.create_process_w = create_process_w
    with pytest.raises(staging.StageError, match='ended before it resumed'):
        h.launch.start(job=h.job)
    assert h.api.events.count('resume') == 0 and h.api.events.count('kill') == 1
    assert h.api.handles == {} and h.launch.process is None
    assert seen[0]['state'] == ledger_mod.DEAD_UNVERIFIED
    assert journal_ops(h.journal)[-1] == 'quarantine'


def test_a_cancel_that_lands_after_the_resume_terminates_the_child(wire):
    h = wire(**OK)
    real = h.api.resume_thread

    def resume_thread(thread):
        done = real(thread)
        h.launch.cancel(reason='host asked')
        return done

    h.api.resume_thread = resume_thread
    with pytest.raises(staging.StageError, match='ended while it started'):
        h.launch.start(job=h.job)
    assert h.api.events.count('kill') == 1 and h.api.handles == {}
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_an_ended_launch_is_never_started(wire):
    h = wire(**OK)
    h.launch.cancel(reason='before start')
    with pytest.raises(staging.StageError, match='already consumed'):
        h.launch.start(job=h.job)
    assert 'create' not in h.api.events
