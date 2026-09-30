"""The event log as an outbox (ADR-0002, state-machines §14, api-and-realtime §3.4).

There is no second queue: the `events` table IS the outbox. A command's events
commit with its state, and everything that reacts — consumers now, SSE later —
reads them back by `seq` after commit.

outbox     committed events after a cursor, with the 410 resync rule
consumers  cursor + idempotent-effects delivery
retention  pruning old events and expired idempotency keys
"""
