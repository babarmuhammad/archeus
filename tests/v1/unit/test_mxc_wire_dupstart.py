# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-805: claiming an execution id is atomic: the first start wins and a second start
of the same id is refused, even from two threads. Same fakes as the wire tests."""

import threading

import pytest

from archeus.node import local, mxc_ledger as ledger_mod, staging

from .test_mxc_wire import args, journal_ops, native_parts, wire  # noqa: F401

OK = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)


def run(launch, job, outcomes, barrier=None):
    try:
        if barrier is not None:
            barrier.wait(5)
        launch.start(job=job)
        outcomes.append('started')
    except Exception as err:
        outcomes.append(err)


def test_two_threads_starting_one_id_let_exactly_one_proceed(wire):
    one, two = wire(**OK), wire(**OK)
    barrier, outcomes = threading.Barrier(2), []
    gate = threading.Barrier(2, timeout=0.3)

    for h in (one, two):
        real = h.journal.journals

        def journals(real=real):
            found = real()
            try:
                gate.wait()                # both would pass the check here, were it the only guard
            except threading.BrokenBarrierError:
                pass
            return found

        h.journal.journals = journals
    threads = [threading.Thread(target=run, args=(h.launch, h.job, outcomes, barrier))
               for h in (one, two)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    errors = [item for item in outcomes if item != 'started']
    assert outcomes.count('started') == 1 and len(errors) == 1
    assert isinstance(errors[0], staging.StageError)
    assert one.api.events.count('create') + two.api.events.count('create') == 1
    assert one.api.events.count('resume') + two.api.events.count('resume') == 1
    assert journal_ops(one.journal) == ['intent', 'ownership']


def test_a_start_is_refused_while_another_is_still_writing_its_intent(wire):
    first, second = wire(**OK), wire(**OK)
    writing, release = threading.Event(), threading.Event()
    real = first.journal.journal.append

    def append(execution_id, op, **facts):
        if op == 'intent':
            writing.set()
            release.wait(5)
        return real(execution_id, op, **facts)

    first.journal.journal.append = append
    outcomes = []
    thread = threading.Thread(target=run, args=(first.launch, first.job, outcomes))
    thread.start()
    assert writing.wait(5)
    with pytest.raises(staging.StageError, match='already being started'):
        second.launch.start(job=second.job)
    assert second.api.events == [] and journal_ops(second.journal) == []
    release.set()
    thread.join(5)
    assert outcomes == ['started']
    assert journal_ops(first.journal) == ['intent', 'ownership']


def test_a_failing_intent_write_leaves_no_journal_and_frees_the_id(wire, monkeypatch):
    first = wire(**OK)
    with monkeypatch.context() as patch:
        patch.setattr(ledger_mod.config, 'write_atomic', lambda *a, **k: False)
        with pytest.raises(OSError, match='initialization failed'):
            first.launch.start(job=first.job)
    assert 'create' not in first.api.events and first.journal.journals() == {}
    second = wire(**OK)
    second.launch.start(job=second.job)
    assert second.api.events.count('resume') == 1
    assert journal_ops(second.journal) == ['intent', 'ownership']


def test_a_start_that_cannot_read_the_ledger_frees_the_id(wire):
    first, second = wire(**OK), wire(**OK)

    def journals():
        raise OSError('ledger unreadable')

    first.journal.journals = journals
    with pytest.raises(OSError, match='unreadable'):
        first.launch.start(job=first.job)
    second.launch.start(job=second.job)
    assert second.api.events.count('resume') == 1


@pytest.mark.parametrize('torn', [b'', b'{"length": 9, "sha256": "ab'])
def test_a_half_written_intent_is_refused_and_reconciled_at_restart(wire, torn):
    h = wire(**OK)
    with open(h.journal.journal._path('e1-p1'), 'wb') as stream:
        stream.write(torn)
    with pytest.raises(staging.StageError, match='ledger journal'):
        h.launch.start(job=h.job)
    assert h.api.events == []
    results = h.journal.reconcile(lambda pid: None, lambda execution_id, owner: True)
    assert results == {'e1-p1': ledger_mod.DEAD_UNVERIFIED}
    rows, _ = ledger_mod.read_records(h.journal.journals()['e1-p1'], 'e1-p1')
    assert [row['op'] for row in rows] == ['quarantine']


def test_the_default_without_a_ledger_claims_nothing(args):
    class Backend:
        def compile_policy(self, **kwargs):
            return local.mxc.compile_policy(**kwargs)

    launch = local.MxcLaunch(backend=Backend(), outcome=lambda process: 0, **args)
    assert launch._claim() is None
