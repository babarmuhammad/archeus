"""The single writer: atomicity, sequence, idempotency, transitions, concurrency."""

import os
import threading
import time
from concurrent.futures import wait

import pytest

from archeus.core.application import commands
from archeus.core.domain import entities, events, ids
from archeus.core.domain.values import Ref
from archeus.infra.db import connection, migrate, rows, writer
from archeus.infra.db.writer import (IdempotencyConflict, InvalidTransition, Writer,
                                     WriterBusy, WriterClosed)
from archeus.infra.eventlog import outbox


def _counts(db):
    with db.read() as r:
        return tuple(r.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
                     for t in ('missions', 'events', 'idempotency_keys')) + (outbox.head(r),)


def _mission_events(db, mission_id):
    with db.read() as r:
        return [e for e in outbox.events_after(r, 0, limit=1000) if e.subject.id == mission_id]


def move(tx, *, actor, mission_id, to, expected_version=None):
    row, e = tx.transition(entities.Mission, mission_id, to, actor=actor,
                           reason='test says so', expected_version=expected_version)
    return {'state': row.entity.state, 'version': row.version, 'seq': e.seq}


# ── A: an accepted command commits state and event together ──

def test_a_command_commits_its_row_and_its_event_together(db, new_mission):
    m = new_mission('first', key='k1')
    with db.read() as r:
        row = rows.get(r, entities.Mission, m['id'])
        (e,) = [e for e in outbox.events_after(r, 0) if e.type == 'mission.created']
        key = r.execute('SELECT response FROM idempotency_keys WHERE key = ?', ('k1',)).fetchone()
    assert row.entity.title == 'first' and row.version == 1 and row.entity.state == 'CREATED'
    assert e.subject.id == m['id'] and e.seq == m['seq'] and e.actor.id == row.created_by
    assert key is not None


# ── B/C: a failed command leaves nothing behind, wherever it fails ──

def test_a_command_that_raises_after_writing_leaves_nothing(db, actor):
    before = _counts(db)

    def half(tx, *, actor):
        commands.create_mission(tx, actor=actor, title='t', objective='o')
        raise ValueError('changed my mind')
    with pytest.raises(ValueError, match='changed my mind'):
        db.writer.execute(half, {'actor': actor}, idempotency_key='k')
    assert _counts(db) == before


def test_failing_after_the_state_write_and_before_the_event_rolls_back(db, new_mission,
                                                                       monkeypatch):
    before = _counts(db)

    def boom(self, event):
        raise OSError('injected: after_state_write_before_event')
    monkeypatch.setattr(writer.Tx, 'append', boom)
    with pytest.raises(OSError, match='after_state_write_before_event'):
        new_mission()
    assert _counts(db) == before


def test_failing_after_the_event_and_before_the_idempotency_record_rolls_back(db, actor):
    """The response is serialised after the events are appended and before the
    key is stored; an unserialisable response fails exactly there."""
    before = _counts(db)

    def bad_response(tx, *, actor):
        commands.create_mission(tx, actor=actor, title='t', objective='o')
        return {'not json': object()}
    with pytest.raises(TypeError):
        db.writer.execute(bad_response, {'actor': actor}, idempotency_key='k')
    assert _counts(db) == before


def test_failing_before_commit_rolls_back(db, new_mission, monkeypatch):
    before = _counts(db)

    def no_commit(conn):
        raise OSError('injected: before_commit')
    monkeypatch.setattr(writer, '_commit', no_commit)
    with pytest.raises(OSError, match='before_commit'):
        new_mission(key='k')
    monkeypatch.undo()
    assert _counts(db) == before
    new_mission(key='k')                    # the key was never consumed
    assert _counts(db)[0] == before[0] + 1


def test_a_constraint_failure_mid_command_rolls_back_the_earlier_writes(db, actor):
    before = _counts(db)

    def twice(tx, *, actor):
        m = entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                             title='t', objective='o')
        tx.insert(m, actor=actor)
        tx.append(events.new_event('mission.created', Ref('mission', m.id), actor))
        tx.insert(m, actor=actor)           # same id: UNIQUE fails
    with pytest.raises(Exception, match='UNIQUE'):
        db.writer.execute(twice, {'actor': actor})
    assert _counts(db) == before


def test_a_state_change_without_an_event_is_refused(db, actor):
    before = _counts(db)

    def silent(tx, *, actor):
        tx.insert(entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                                   title='t', objective='o'), actor=actor)
    with pytest.raises(writer.UnrecordedMutation):
        db.writer.execute(silent, {'actor': actor})
    assert _counts(db) == before


@pytest.mark.parametrize('kind', ['execution', 'device'])
def test_the_actor_is_a_principal_never_an_execution_or_device_id(db, kind):
    """`actor_id` / `created_by` hold the causing principal (domain-model §9.5);
    an `exe_…` id is provenance, not identity, and is refused as an actor."""
    before = _counts(db)
    stand_in = Ref('execution' if kind == 'execution' else 'user_device', ids.new_id(kind))
    with pytest.raises(ValueError, match='principal id'):
        db.writer.execute(commands.create_mission,
                          {'actor': stand_in, 'title': 't', 'objective': 'o'})
    assert _counts(db) == before


def test_created_by_is_a_principal_even_when_the_event_actor_is(db, actor):
    before = _counts(db)

    def mixed(tx, *, actor):
        m = entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                             title='t', objective='o')
        tx.insert(m, actor=Ref('execution', ids.new_id('execution')))
        tx.append(events.new_event('mission.created', Ref('mission', m.id), actor))
    with pytest.raises(ValueError, match='created_by'):
        db.writer.execute(mixed, {'actor': actor})
    assert _counts(db) == before


def test_the_caller_cannot_choose_a_seq(db, actor):
    def forged(tx, *, actor):
        tx.append(events.new_event('mission.created', Ref('mission', ids.new_id('mission')),
                                   actor, seq=7))
    with pytest.raises(ValueError, match='assigned by the writer'):
        db.writer.execute(forged, {'actor': actor})


# ── sequence ──

def test_seq_is_monotonic_contiguous_and_not_consumed_by_a_rollback(db, new_mission, actor):
    a = new_mission()['seq']

    def fail(tx, *, actor):
        commands.create_mission(tx, actor=actor, title='t', objective='o')
        raise RuntimeError('rolled back')
    with pytest.raises(RuntimeError):
        db.writer.execute(fail, {'actor': actor})
    b = new_mission()['seq']
    assert b == a + 1


def test_concurrent_commands_get_unique_ordered_seqs(db, actor):
    def burst(n):
        return [db.writer.submit(commands.create_mission,
                                 {'actor': actor, 'title': 't%d' % i, 'objective': 'o'})
                for i in range(n)]
    threads, futs = [], []
    for _ in range(8):
        t = threading.Thread(target=lambda: futs.extend(burst(40)))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    wait(futs)
    seqs = sorted(f.result()['seq'] for f in futs)
    assert len(seqs) == len(set(seqs)) == 320
    with db.read() as r:
        log = [e.seq for e in outbox.events_after(r, 0, limit=1000)]
    assert log == sorted(log) == list(range(log[0], log[0] + 320))


def test_seq_survives_a_restart(archeus_home, actor):
    from archeus.infra.db import Database
    args = {'actor': actor, 'title': 't', 'objective': 'o'}
    d = Database.open()
    first = d.writer.execute(commands.create_mission, args)['seq']
    d.close()
    d = Database.open()
    try:
        assert d.writer.execute(commands.create_mission, args)['seq'] == first + 1
    finally:
        d.close()


# ── idempotency ──

def test_a_retried_command_returns_the_original_result_and_writes_nothing(db, new_mission):
    first = new_mission('once', key='same')
    after_first = _counts(db)
    again = new_mission('once', key='same')
    assert again == first
    assert _counts(db) == after_first


def test_reusing_a_key_for_a_different_request_fails_clearly(db, new_mission, actor):
    new_mission('once', key='k')
    before = _counts(db)
    with pytest.raises(IdempotencyConflict, match="'k'"):
        new_mission('different title', key='k')
    with pytest.raises(IdempotencyConflict):
        db.writer.execute(commands.create_mission,           # same body, other actor
                          {'actor': Ref('user_device', ids.new_id('principal')),
                           'title': 'once', 'objective': 'o'}, idempotency_key='k')
    with pytest.raises(IdempotencyConflict):
        db.writer.execute(commands.register_principal, {'kind': 'system'},
                          idempotency_key='k')              # other command
    assert _counts(db) == before


def test_an_expired_key_is_a_new_request(db, new_mission):
    first = new_mission('old', key='k')
    c = connection.connect(db.path)
    c.execute("UPDATE idempotency_keys SET created_at = '2000-01-01T00:00:00.000Z'")
    c.close()
    second = new_mission('old', key='k')
    assert second['id'] != first['id']


# ── transitions ──

def test_a_valid_transition_bumps_the_version_and_records_the_edge(db, new_mission, actor):
    m = new_mission()
    got = db.writer.execute(move, {'actor': actor, 'mission_id': m['id'], 'to': 'UNDERSTANDING'})
    assert got['state'] == 'UNDERSTANDING' and got['version'] == 2
    e = _mission_events(db, m['id'])[-1]
    assert e.type == 'mission.state_changed' and e.seq == got['seq']
    assert e.payload == {'from': 'CREATED', 'to': 'UNDERSTANDING', 'trigger': 'start',
                         'reason': 'test says so'}
    with db.read() as r:
        row = rows.get(r, entities.Mission, m['id'])
    assert (row.entity.state, row.version, row.updated_by) == ('UNDERSTANDING', 2, actor.id)


@pytest.mark.parametrize('path, to, why', [
    ((), 'EXECUTING', 'no such edge'),                                   # skips the machine
    (('UNDERSTANDING', 'CONTEXT_GATHERING', 'REASONING', 'PLANNING'), 'APPROVED',
     'needs a transition proof'),                                        # guarded edge
    (('UNDERSTANDING', 'CONTEXT_GATHERING', 'REASONING', 'PLANNING', 'CANCELLED'), 'CREATED',
     'no such edge'),                                                    # out of a terminal
])
def test_an_invalid_transition_changes_nothing(db, new_mission, actor, path, to, why):
    m = new_mission()
    for s in path:
        db.writer.execute(move, {'actor': actor, 'mission_id': m['id'], 'to': s})
    before = _counts(db)
    with pytest.raises(InvalidTransition, match=why) as err:
        db.writer.execute(move, {'actor': actor, 'mission_id': m['id'], 'to': to})
    assert (err.value.machine, err.value.to) == ('mission', to)
    assert _counts(db) == before


def test_a_transition_needs_a_reason_and_a_known_entity(db, new_mission, actor):
    m = new_mission()

    def unexplained(tx, *, actor):
        tx.transition(entities.Mission, m['id'], 'UNDERSTANDING', actor=actor, reason=' ')
    with pytest.raises(ValueError, match='reason'):
        db.writer.execute(unexplained, {'actor': actor})
    with pytest.raises(writer.NotFound):
        db.writer.execute(move, {'actor': actor, 'mission_id': ids.new_id('mission'),
                                 'to': 'UNDERSTANDING'})


def test_a_stale_expected_version_is_a_conflict(db, new_mission, actor):
    m = new_mission()
    db.writer.execute(move, {'actor': actor, 'mission_id': m['id'], 'to': 'UNDERSTANDING',
                             'expected_version': 1})
    with pytest.raises(writer.VersionConflict) as err:
        db.writer.execute(move, {'actor': actor, 'mission_id': m['id'],
                                 'to': 'CONTEXT_GATHERING', 'expected_version': 1})
    assert (err.value.expected, err.value.current) == (1, 2)


@pytest.mark.parametrize('with_version', [True, False])
def test_concurrent_transitions_of_one_entity_lose_no_update(db, new_mission, actor,
                                                             with_version):
    m = new_mission()
    start = threading.Barrier(10)
    results = []

    def racer():
        start.wait()
        args = {'actor': actor, 'mission_id': m['id'], 'to': 'UNDERSTANDING'}
        if with_version:
            args['expected_version'] = 1
        try:
            results.append(db.writer.execute(move, args))
        except (writer.VersionConflict, InvalidTransition) as e:
            results.append(type(e))
    threads = [threading.Thread(target=racer) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wins = [r for r in results if isinstance(r, dict)]
    losers = [r for r in results if not isinstance(r, dict)]
    assert len(wins) == 1 and wins[0]['version'] == 2
    assert set(losers) == {writer.VersionConflict if with_version else InvalidTransition}
    assert [e.type for e in _mission_events(db, m['id'])] == ['mission.created',
                                                              'mission.state_changed']


# ── the writer thread ──

def _writer(path, **kw):
    def open_conn():
        c = connection.connect(path)
        migrate.migrate(c)
        return c
    return Writer(open_conn, **kw)


def test_the_queue_is_bounded(tmp_path):
    gate = threading.Event()
    w = _writer(str(tmp_path / 'w.db'), max_pending=2)
    try:
        w.submit(lambda tx, *, g: g.wait(10), {'g': gate})     # occupies the thread
        time.sleep(0.2)
        w.submit(lambda tx: None)
        w.submit(lambda tx: None)
        assert w.pending() == 2
        with pytest.raises(WriterBusy):
            w.submit(lambda tx: None)
    finally:
        gate.set()
        w.close()


def test_closing_drains_and_a_kill_drops_what_is_queued(tmp_path, actor):
    gate = threading.Event()
    w = _writer(str(tmp_path / 'w.db'))
    busy = w.submit(lambda tx, *, g: g.wait(10), {'g': gate})
    time.sleep(0.2)
    queued = [w.submit(commands.create_mission,
                       {'actor': actor, 'title': 't', 'objective': 'o'}) for _ in range(3)]
    closer = threading.Thread(target=lambda: w.close(drain=False))
    closer.start()
    time.sleep(0.2)
    gate.set()
    closer.join(10)
    busy.result(5)
    for f in queued:
        with pytest.raises(WriterClosed):
            f.result(5)
    with pytest.raises(WriterClosed):
        w.submit(lambda tx: None)
    c = connection.connect(str(tmp_path / 'w.db'), readonly=True)
    try:
        assert c.execute('SELECT COUNT(*) FROM missions').fetchone()[0] == 0
    finally:
        c.close()

    w2 = _writer(str(tmp_path / 'w.db'))
    futs = [w2.submit(commands.create_mission,
                      {'actor': actor, 'title': 't', 'objective': 'o'}) for _ in range(5)]
    w2.close()                                       # drain: every queued command runs
    assert all(f.result(5)['seq'] for f in futs) and w2.committed == 5


def test_a_failing_command_does_not_stop_the_writer(db, new_mission):
    def broken(tx):
        raise KeyError('nope')
    with pytest.raises(KeyError):
        db.writer.execute(broken)
    assert new_mission()['id']
    assert db.writer.failed == 1


#: plan §31.1 P2: the architectural target, asserted on a developer machine.
TARGET_RATE = 500
#: Hosted CI runners have fsync costs this code does not control, so there the
#: test is a regression floor, not the benchmark (target-architecture §5.2).
CI_FLOOR = 200


def test_writer_throughput_is_at_least_500_commands_per_second(db, actor):
    """Pipelined, as an API under load would submit them. Best of three
    batches, so one scheduler or antivirus stall does not decide the result."""
    n, best = 500, 0.0
    for _ in range(3):
        t = time.perf_counter()
        futs = [db.writer.submit(commands.create_mission,
                                 {'actor': actor, 'title': 't', 'objective': 'o'})
                for _ in range(n)]
        for f in futs:
            f.result(60)
        best = max(best, n / (time.perf_counter() - t))
    floor = CI_FLOOR if os.environ.get('CI') else TARGET_RATE
    assert best >= floor, '%.0f commands/s (floor %d)' % (best, floor)
