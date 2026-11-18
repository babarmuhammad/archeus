"""The policy worker (`archeus-policy`, P9 §17): ends every approval whose time
is up. That is all it does — expiry is also judged at every decision and every
use (an expired approval covers nothing whether or not this has run), so the
sweep only makes the state say what the clock already decided."""

from datetime import datetime, timezone

from ...infra.db import rows
from ..application import authorization
from ..domain import entities


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class Expiry:
    """`pending()` counts approvals past their expiry; `pass_once()` ends them."""

    def __init__(self, db, *, actor, clock=_now):
        self.db, self.actor, self.clock = db, actor, clock
        self.on_wake = None
        self.stopping = lambda: False

    def _due(self, conn):
        now = self.clock()
        return [r for r in rows.where(conn, entities.Approval)
                if r.entity.expires_at <= now and (
                    r.entity.state == 'PENDING'
                    or (r.entity.state == 'APPROVED' and r.entity.kind == 'action'))]

    def pending(self):
        with self.db.read() as conn:
            n = len(self._due(conn))
        if n and self.on_wake is not None:
            self.on_wake()
        return n

    def sweep(self):
        return []

    def pass_once(self):
        with self.db.read() as conn:
            if not self._due(conn):
                return {'changed': False}
        out = self.db.writer.execute(authorization.expire_due, {'actor': self.actor})
        return {'changed': bool(out['expired'])}
