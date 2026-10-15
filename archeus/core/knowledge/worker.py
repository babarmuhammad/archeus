"""The knowledge worker (P6): an outbox consumer (`consumers.deliver`, at-least-
once, handler outside any transaction) that turns four facts into passes.

| event | pass |
|---|---|
| `repository_inspection.state_changed` to COMPLETED | the project's initial knowledge pass, once per project |
| `meeting.imported` | decision candidates from the notes |
| `mission.state_changed` to COMPLETED or FAILED | lessons, once per mission |
| `provider_terms.decided` permitting headless use | every pass still gated by ADR-0021, again |

"Once" is read from the RouteDecisions themselves: a source whose pass ended
`ok` or `invalid` is not passed again, so a re-delivered event (a crash between
the call and the consumer's effect) is a no-op and knowledge is never doubled.
A pass that failed for a reason outside the answer (no harness, a timeout, a
Core that died mid-call) may run again when its event comes round again.
"""

import logging

from ...infra.db import rows
from ...infra.eventlog import consumers, outbox
from ..application import calls as C
from ..domain import entities

log = logging.getLogger('archeus.core')

CONSUMER = 'knowledge'
#: outcomes after which a source is never passed again by its own trigger
SETTLED = ('ok', 'invalid')


class Knowledge:
    def __init__(self, db, *, actor, passes):
        self.db, self.actor, self.passes = db, actor, passes
        self.on_wake = None
        self.stopping = lambda: False

    def pending(self):
        with self.db.read() as conn:
            n = outbox.head(conn) - consumers.cursor(conn, CONSUMER)
        if n and self.on_wake is not None:
            self.on_wake()
        return n

    def sweep(self):
        """A call a previous Core was in the middle of has no outcome: it ends
        `failed` (core_restarted), which lets its pass run again."""
        with self.db.read() as conn:
            open_ = [r.entity.id for r in rows.where(conn, entities.RouteDecision)
                     if r.entity.outcome is None]
        for rd in open_:
            self.db.writer.execute(C.end_call, {'actor': self.actor, 'route_decision_id': rd,
                                                'outcome': {'state': 'failed',
                                                            'reason': 'core_restarted'}})
        return open_

    def pass_once(self):
        return {'changed': consumers.deliver(self.db, CONSUMER, self._handle) > 0}

    # ── dispatch ──

    def _handle(self, e):
        """One event. A pass that breaks is this event's failure, recorded as its
        effect, never the worker's: the world worker's per-repository rule."""
        try:
            return self._dispatch(e)
        except Exception as x:
            log.exception('knowledge pass for event %d failed', e.seq)
            return 'error: %s: %s' % (type(x).__name__, x)

    def _dispatch(self, e):
        to = (e.payload or {}).get('to')
        if e.type == 'repository_inspection.state_changed' and to == 'COMPLETED':
            return self._knowledge(e.subject.id)
        if e.type == 'meeting.imported':
            return self._once('knowledge_extraction', 'meeting', e.subject.id,
                              self.passes.decisions)
        if e.type == 'mission.state_changed' and to in ('COMPLETED', 'FAILED'):
            return self._once('lesson', 'mission', e.subject.id, self.passes.lessons)
        if e.type == 'provider_terms.decided' and e.payload.get('headless') == 'permitted':
            return self._rerun_gated()
        return ''

    def _decisions(self, purpose, **eq):
        with self.db.read() as conn:
            return [r.entity for r in rows.where(conn, entities.RouteDecision, purpose=purpose,
                                                 **eq)]

    def _settled(self, decisions):
        return any(d.outcome is not None and d.outcome.get('state') in SETTLED
                   for d in decisions)

    def _once(self, purpose, kind, source_id, run):
        mine = [d for d in self._decisions(purpose)
                if d.source is not None and (d.source.kind, d.source.id) == (kind, source_id)]
        if self._settled(mine):
            return 'already passed'
        return '%s:%s' % (purpose, run(source_id))

    def _knowledge(self, inspection_id):
        """The project's first COMPLETED inspection queues its initial pass
        (plan P6); a later inspection of the same project does not."""
        def project_of(conn):
            i = rows.get(conn, entities.RepositoryInspection, inspection_id).entity
            return rows.get(conn, entities.Repository, i.repository_id).entity.project_id
        with self.db.read() as conn:
            project_id = project_of(conn)
        passes = [d for d in self._decisions('knowledge_extraction', project_id=project_id)
                  if d.source is not None and d.source.kind == 'repository_inspection']
        if self._settled(passes) or any(d.outcome and d.outcome.get('state') == 'gated'
                                        for d in passes):
            return 'already passed'
        return 'knowledge:%s' % self.passes.knowledge(inspection_id)

    def _rerun_gated(self):
        """Every source whose latest pass was gated, passed again now that
        headless use has been permitted for some harness."""
        runs = {'repository_inspection': self.passes.knowledge,
                'meeting': self.passes.decisions, 'mission': self.passes.lessons}
        latest = {}
        for purpose in ('knowledge_extraction', 'lesson'):
            for d in self._decisions(purpose):
                if d.source is not None:
                    latest[(purpose, d.source.kind, d.source.id)] = d     # rows are oldest first
        done = []
        for (purpose, kind, sid), d in sorted(latest.items()):
            if d.outcome and d.outcome.get('state') == 'gated' and kind in runs:
                done.append('%s:%s' % (sid, runs[kind](sid)))
        return 'rerun ' + ','.join(done)
