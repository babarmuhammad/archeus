"""The event log as an outbox: cursors, replay, consumers, retention."""

from datetime import datetime, timedelta, timezone

import pytest

from archeus.infra.db import Database
from archeus.infra.eventlog import consumers, outbox, retention
from archeus.infra.eventlog.outbox import CursorExpired


def _after(db, cursor, **kw):
    with db.read() as r:
        return outbox.events_after(r, cursor, **kw)


def _head(db):
    with db.read() as r:
        return outbox.head(r)


def _later(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat().replace('+00:00', 'Z')


# ── cursors and replay ──

def test_replay_is_ordered_and_pages_without_skips_or_repeats(db, new_mission):
    made = [new_mission('m%d' % i)['seq'] for i in range(7)]
    seen, cursor = [], 0
    while True:
        page = _after(db, cursor, limit=3)
        if not page:
            break
        seen += [e.seq for e in page]
        cursor = page[-1].seq
    assert seen == made and cursor == _head(db)


def test_a_reader_continues_from_its_cursor_across_a_restart(archeus_home, actor):
    from archeus.core.application import commands
    args = {'actor': actor, 'title': 't', 'objective': 'o'}
    d = Database.open()
    for _ in range(3):
        d.writer.execute(commands.create_mission, args)
    with d.read() as r:
        first = outbox.events_after(r, 0)
    cursor = first[-1].seq
    d.close()
    d = Database.open()
    try:
        with d.read() as r:
            assert outbox.events_after(r, 0) == first       # history unchanged
            assert outbox.events_after(r, cursor) == []
        new = d.writer.execute(commands.create_mission, args)
        with d.read() as r:
            assert [e.seq for e in outbox.events_after(r, cursor)] == [new['seq']]
    finally:
        d.close()


def test_a_replayed_event_is_the_event_that_was_written(db, new_mission):
    m = new_mission('exact')
    (e,) = _after(db, m['seq'] - 1)
    env = e.to_envelope()
    assert env['seq'] == m['seq'] and env['subject'] == {'kind': 'mission', 'id': m['id']}
    assert env['actor']['kind'] == 'user_device' and env['payload'] == {'title': 'exact'}


@pytest.mark.parametrize('cursor', [-1, True, '3', 1.5, None])
def test_a_malformed_cursor_is_a_client_error(db, cursor):
    with pytest.raises(ValueError, match='cursor'):
        _after(db, cursor)


@pytest.mark.parametrize('limit', [0, outbox.MAX_LIMIT + 1, True])
def test_the_page_size_is_bounded(db, limit):
    with pytest.raises(ValueError, match='limit'):
        _after(db, 0, limit=limit)


def test_a_cursor_from_the_future_must_resync(db, new_mission):
    new_mission()
    with pytest.raises(CursorExpired) as err:
        _after(db, _head(db) + 1)
    assert err.value.reason == 'ahead'


def test_a_cursor_behind_retention_must_resync(db, new_mission):
    for _ in range(3):
        new_mission()
    head = _head(db)
    got = db.writer.execute(retention.prune, {'now': _later(365)})
    assert got['events'] == 3 and got['through'] == head
    with pytest.raises(CursorExpired) as err:
        _after(db, 0)
    assert (err.value.reason, err.value.floor) == ('pruned', head)
    assert _after(db, head) == []                       # a caught-up reader is fine
    later = new_mission()
    assert later['seq'] == head + 1                     # AUTOINCREMENT: no seq reuse
    assert [e.seq for e in _after(db, head)] == [head + 1]


def test_retention_removes_a_prefix_and_never_passes_a_consumer(db, new_mission):
    for _ in range(5):
        new_mission()
    consumers.deliver(db, 'slow', lambda e: 'ok', limit=2)      # cursor at 2
    got = db.writer.execute(retention.prune, {'now': _later(365)})
    assert got['through'] == 2
    assert [e.seq for e in _after(db, 2)] == [3, 4, 5]
    assert consumers.deliver(db, 'slow', lambda e: 'ok') == 3


def test_retention_keeps_what_is_inside_the_window_and_expires_old_keys(db, new_mission):
    new_mission(key='k')
    got = db.writer.execute(retention.prune, {})
    assert got == {'events': 0, 'through': 0, 'idempotency_keys': 0}
    got = db.writer.execute(retention.prune, {'now': _later(2), 'keep_days': 180})
    assert got['events'] == 0 and got['idempotency_keys'] == 1


# ── consumers ──

def _cursor(db, name):
    with db.read() as r:
        return consumers.cursor(r, name)


def test_a_consumer_sees_every_event_once_in_order(db, new_mission):
    made = [new_mission()['seq'] for _ in range(4)]
    calls = []
    assert consumers.deliver(db, 'c', lambda e: calls.append(e.seq) or 'done') == 4
    assert consumers.deliver(db, 'c', lambda e: calls.append(e.seq)) == 0
    assert calls == made and _cursor(db, 'c') == made[-1]
    with db.read() as r:
        rows = r.execute("SELECT event_seq, result FROM consumer_effects WHERE consumer = 'c' "
                         'ORDER BY event_seq').fetchall()
    assert [tuple(x) for x in rows] == [(s, 'done') for s in made]


def test_a_crash_after_the_effect_and_before_the_cursor_repeats_nothing(db, new_mission,
                                                                        monkeypatch):
    made = [new_mission()['seq'] for _ in range(3)]
    calls = []
    real = consumers._advance

    def crash(tx, **kw):
        raise OSError('injected: after_effect_before_cursor')
    monkeypatch.setattr(consumers, '_advance', crash)
    with pytest.raises(OSError, match='after_effect_before_cursor'):
        consumers.deliver(db, 'c', lambda e: calls.append(e.seq))
    assert calls == made[:1] and _cursor(db, 'c') == 0         # effect done, cursor not moved
    monkeypatch.setattr(consumers, '_advance', real)
    consumers.deliver(db, 'c', lambda e: calls.append(e.seq))
    assert calls == made                                        # the first was not re-run
    assert _cursor(db, 'c') == made[-1]


def test_a_crash_before_the_effect_is_recorded_redelivers(db, new_mission):
    made = [new_mission()['seq'] for _ in range(2)]
    calls = []

    def flaky(e):
        calls.append(e.seq)
        if len(calls) == 1:
            raise RuntimeError('handler died')
        return 'ok'
    with pytest.raises(RuntimeError):
        consumers.deliver(db, 'c', flaky)
    consumers.deliver(db, 'c', flaky)
    assert calls == [made[0], made[0], made[1]]                 # at-least-once
    assert _cursor(db, 'c') == made[-1]


def test_a_consumer_resumes_after_a_restart_without_redelivery(archeus_home, actor):
    from archeus.core.application import commands
    args = {'actor': actor, 'title': 't', 'objective': 'o'}
    d = Database.open()
    d.writer.execute(commands.create_mission, args)
    calls = []
    consumers.deliver(d, 'c', lambda e: calls.append(e.seq))
    d.close()
    d = Database.open()
    try:
        new = d.writer.execute(commands.create_mission, args)['seq']
        consumers.deliver(d, 'c', lambda e: calls.append(e.seq))
        assert calls == [new - 1, new]
    finally:
        d.close()


def test_a_cursor_never_moves_backwards(db, new_mission):
    for _ in range(3):
        new_mission()
    consumers.deliver(db, 'c', lambda e: None)
    db.writer.execute(consumers._advance, {'name': 'c', 'seq': 1})
    assert _cursor(db, 'c') == 3
