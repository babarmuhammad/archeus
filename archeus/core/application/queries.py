"""Queries: read-only views over one snapshot (`Database.read()`)."""

import json

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox
from ..domain import entities, states


def view(row):
    """An entity row as the API shows it: the entity plus its row metadata."""
    return dict(row.entity.to_dict(), version=row.version, created_at=row.created_at,
                updated_at=row.updated_at)


def get_mission(conn, mission_id):
    row = rows.get(conn, entities.Mission, mission_id)
    if row is None:
        raise NotFound(mission_id)
    return view(row)


def list_missions(conn, state=None):
    """Every mission, oldest first; only those in *state* when it is given."""
    if state is not None and state not in states.states('mission'):
        raise ValueError('%r is not a mission state' % (state,))
    eq = {} if state is None else {'state': state}
    return [view(r) for r in rows.where(conn, entities.Mission, **eq)]


def system_principal(conn):
    """The oldest `system` principal (the engine's actor), or None."""
    return next((r.entity.id for r in rows.where(conn, entities.Principal)
                 if r.entity.kind == 'system'), None)


def credential(conn, token_hash):
    """The device a token hash belongs to: `{principal_id, device_id, scopes,
    expires_at, revoked_at, device_state}`, or None. Judging it (revoked,
    expired, inactive) is the caller's."""
    t = conn.execute("SELECT * FROM tokens WHERE token_hash = ? AND kind = 'device'",
                     (token_hash,)).fetchone()
    if t is None:
        return None
    dev = rows.where(conn, entities.Device, principal_id=t['principal_id'])
    return {'token_hash': t['token_hash'], 'principal_id': t['principal_id'],
            'device_id': dev[0].entity.id if dev else None,
            'device_state': dev[0].entity.state if dev else None,
            'scopes': tuple(json.loads(t['scopes'])), 'expires_at': t['expires_at'],
            'revoked_at': t['revoked_at']}


def events(conn, after_seq=0, *, limit=None):
    """Envelopes after *after_seq*; every one when *limit* is None (paged)."""
    out, cursor = [], after_seq
    while True:
        page = outbox.events_after(conn, cursor, limit=outbox.MAX_LIMIT if limit is None else limit)
        out += [e.to_envelope() for e in page]
        if limit is not None or len(page) < outbox.MAX_LIMIT:
            return out
        cursor = page[-1].seq
