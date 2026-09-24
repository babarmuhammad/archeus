"""Queries: read-only views over one snapshot (`Database.read()`)."""

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox
from ..domain import entities


def view(row):
    """An entity row as the API shows it: the entity plus its row metadata."""
    return dict(row.entity.to_dict(), version=row.version, created_at=row.created_at,
                updated_at=row.updated_at)


def get_mission(conn, mission_id):
    row = rows.get(conn, entities.Mission, mission_id)
    if row is None:
        raise NotFound(mission_id)
    return view(row)


def events(conn, after_seq=0, *, limit=None):
    """Envelopes after *after_seq*; every one when *limit* is None (paged)."""
    out, cursor = [], after_seq
    while True:
        page = outbox.events_after(conn, cursor, limit=outbox.MAX_LIMIT if limit is None else limit)
        out += [e.to_envelope() for e in page]
        if limit is not None or len(page) < outbox.MAX_LIMIT:
            return out
        cursor = page[-1].seq
