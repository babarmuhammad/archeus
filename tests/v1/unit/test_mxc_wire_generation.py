# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""PV20 B2 and B3: a journal belongs to one process generation, so a resume of the same
execution can launch again and a verifier key has a name the ledger accepts; and an end
terminates the Job through the boundary without ever closing it. Same fakes as the wire
tests."""

import pytest

from archeus.core.domain import ids
from archeus.node import isolation as iso, mxc_ledger as ledger_mod, staging

from .test_mxc_wire import args, journal_ops, native_parts, wire  # noqa: F401

OK = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
VID = ids.new_id('verification')


def key(attempt=3):
    return 'verify/%s.%d' % (VID, attempt)


# ── the names ──

def test_an_execution_key_takes_its_process_generation():
    assert ledger_mod.journal_name('exe_01', 1) == 'exe_01-p1'
    assert ledger_mod.journal_name('exe_01', 12) == 'exe_01-p12'


def test_a_verifier_key_maps_to_a_name_without_slash_or_dot():
    assert ledger_mod.journal_name(key(), 1) == 'verify_%s_3-p1' % VID


def test_two_generations_or_two_keys_never_share_a_name(tmp_path):
    names = {ledger_mod.journal_name(k, n) for k in ('e1', 'e11', key(1), key(11))
             for n in (1, 11)}
    assert len(names) == 8
    journal = ledger_mod.Ledger(tmp_path)
    for name in names:
        journal.append(name, 'intent', requested_policy_digest='0' * 64, planned=[],
                       applied=[], observed={})
    assert len(journal.journals()) == 8


@pytest.mark.parametrize('seq', [0, -1, None, '1', 1.0, True])
def test_a_process_generation_that_is_not_a_positive_integer_is_refused(seq):
    with pytest.raises(ValueError, match='generation'):
        ledger_mod.journal_name('e1', seq)


@pytest.mark.parametrize('bad', [None, 7, '', 'e-1', 'e/1', 'e.1', 'e 1', 'é', 'verify_x',
                                 'verify/', 'verify/%s' % VID, 'verify/%s.01' % VID,
                                 'verify/%s.x' % VID, 'verify/vrf_bad.1', key() + '/x'])
def test_a_key_the_ledger_cannot_name_is_refused(bad):
    with pytest.raises(ValueError):
        ledger_mod.journal_name(bad, 1)


# ── a resume launches again ──

def test_a_resume_of_the_same_execution_launches_under_its_own_journal(wire):
    first = wire(**OK)
    first.launch.start(job=first.job)
    assert first.launch.wait() == 0
    second = wire(process_seq=2, **OK)
    second.launch.start(job=second.job)
    assert second.launch.wait() == 0
    assert set(second.journal.journals()) == {'e1-p1', 'e1-p2'}
    assert journal_ops(second.journal, 'e1-p1') == journal_ops(second.journal, 'e1-p2') == [
        'intent', 'ownership', 'disposal', 'completion']


def test_the_same_generation_twice_is_still_refused(wire):
    first = wire(**OK)
    first.launch.start(job=first.job)
    assert first.launch.wait() == 0
    again = wire(**OK)
    with pytest.raises(staging.StageError, match='ledger journal'):
        again.launch.start(job=again.job)


def test_a_verifier_launches_under_the_mapped_name_and_the_broker_gets_its_key(wire):
    h = wire(execution_id=key(), **OK)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    name = 'verify_%s_3-p1' % VID
    assert set(h.journal.journals()) == {name} and h.broker.revoked == [key()]
    assert h.launch.journal == name and journal_ops(h.journal, name)[-1] == 'completion'


def test_the_readers_and_the_restart_see_the_journal_name(wire):
    seen = []

    def reader(name, owner):
        seen.append(name)
        return True

    h = wire(outcome=lambda process: 0, reader=reader, process_seq=2)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    assert seen == ['e1-p2'] and h.broker.revoked == ['e1']
    h2 = wire(outcome=lambda process: 0, reader=reader, process_seq=3)
    h2.launch.start(job=h2.job)
    h2.launch.process.terminate()
    assert h2.journal.reconcile(lambda pid: None, lambda name, owner: True) == {
        'e1-p3': ledger_mod.DEAD_CLEAN}


@pytest.mark.parametrize('seq', [0, -1, None, True])
def test_a_launch_with_no_valid_generation_is_refused_before_anything(wire, seq):
    with pytest.raises(staging.StageError, match='process generation'):
        wire(process_seq=seq, **OK)


# ── the end terminates the Job and never closes it ──

def test_an_end_terminates_the_job_through_the_boundary_and_keeps_it_open(wire):
    h = wire(**OK)
    h.launch.start(job=h.job)
    assert h.launch.cancel(reason='host asked', outcome=0)['state'] == ledger_mod.DEAD_CLEAN
    assert h.boundary.terminated == [h.job]
    assert h.boundary.closed == [] and h.job in h.boundary.open


def test_an_end_job_the_caller_gives_replaces_the_boundarys(wire):
    mine = []
    h = wire(end_job=mine.append, **OK)
    h.launch.start(job=h.job)
    h.launch.cancel(reason='host asked', outcome=0)
    assert mine == [h.job] and h.boundary.terminated == []


def test_the_default_is_the_boundarys_terminate_job_method(wire):
    h = wire(**OK)
    assert h.launch._end_job == h.boundary.terminate_job


def test_a_terminate_that_fails_is_never_a_clean_end(wire):
    h = wire(**OK)

    def refuse(job):
        raise OSError('TerminateJobObject failed')

    h.launch._end_job = refuse
    h.launch.start(job=h.job)
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED and 'end_job' in h.launch.facts['faults']
    assert h.boundary.closed == []


# ── the production boundary's own binding, with its kernel call replaced ──

@pytest.mark.skipif(not iso.WINDOWS, reason='the Windows boundary exists only on Windows')
class TestWindowsTerminateJob:
    def test_it_calls_terminate_with_the_job_and_never_closes_it(self, monkeypatch):
        calls = []
        monkeypatch.setattr(iso, '_TerminateJobObject',
                            lambda job, code: calls.append((job, code)) or 1)
        monkeypatch.setattr(iso, '_CloseHandle', lambda handle: calls.append('closed'))
        iso.WindowsBoundary().terminate_job(77)
        assert calls == [(77, 1)]

    def test_a_refused_terminate_raises(self, monkeypatch):
        monkeypatch.setattr(iso, '_TerminateJobObject', lambda job, code: 0)
        with pytest.raises(iso.IsolationUnavailable, match='TerminateJobObject'):
            iso.WindowsBoundary().terminate_job(77)

    def test_no_job_raises(self, monkeypatch):
        monkeypatch.setattr(iso, '_TerminateJobObject', lambda job, code: 1)
        with pytest.raises(iso.IsolationUnavailable, match='job_missing'):
            iso.WindowsBoundary().terminate_job(None)


def test_the_unavailable_boundary_refuses_terminate_job():
    with pytest.raises(iso.IsolationUnavailable):
        iso.UnavailableBoundary().terminate_job(1)
