"""Outbox consumers: a cursor and an effects table each (state-machines §14).

`deliver()` hands a consumer the events after its cursor, in seq order. For
each one it runs the handler (the side effect, OUTSIDE any transaction), commits
`(consumer, seq) -> result` to `consumer_effects`, and only then advances the
cursor. So a crash:
- before the effect is recorded re-delivers the event and the handler runs
  again — handlers must be idempotent in what they do outside the database;
- after the effect is recorded but before the cursor moved re-delivers the
  event and the handler is NOT run again: the effects table answers for it.

Delivery is at-least-once to the handler and never skips an event. Cursors only
move forward (`MAX`), so an out-of-date advance cannot rewind one.
"""

from . import outbox


def cursor(conn, name):
    r = conn.execute('SELECT last_seq FROM consumer_cursors WHERE name = ?', (name,)).fetchone()
    return r[0] if r else 0


def _record_effect(tx, *, name, seq, result):
    tx.execute('INSERT OR IGNORE INTO consumer_effects (consumer, event_seq, result, at) '
               'VALUES (?, ?, ?, ?)', (name, seq, result, tx.now))


def _advance(tx, *, name, seq):
    tx.execute('INSERT INTO consumer_cursors (name, last_seq, updated_at) VALUES (?, ?, ?) '
               'ON CONFLICT (name) DO UPDATE SET '
               'last_seq = MAX(last_seq, excluded.last_seq), updated_at = excluded.updated_at',
               (name, seq, tx.now))


def deliver(db, name, handler, *, limit=100):
    """Deliver the next batch to *handler(event) -> str*; returns how many
    events the cursor moved past."""
    with db.read() as conn:
        start = cursor(conn, name)
        batch = outbox.events_after(conn, start, limit=limit)
        done = {r[0] for r in conn.execute(
            'SELECT event_seq FROM consumer_effects WHERE consumer = ? AND event_seq > ?',
            (name, start))}
    for event in batch:
        if event.seq not in done:
            result = handler(event)
            db.writer.execute(_record_effect, {'name': name, 'seq': event.seq,
                                               'result': str(result or '')})
        db.writer.execute(_advance, {'name': name, 'seq': event.seq})
    return len(batch)
