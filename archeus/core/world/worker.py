"""The world worker (p4-design-gate §6.1): HEAD check → decide → inspect or
re-evaluate → drift → commit. No task, execution, harness or model.

One pass plans from ONE read snapshot plus a cheap HEAD read per repository
(`plan`), then does each item through writer commands. `pending()` runs the
same `plan`, so the answer to "is there world work?" is exactly the work the
next pass would do — never a guess, and never stale by a poll interval — and
a caller that finds some wakes the worker (§14 A1).

Invariants kept here, and re-checked by the commands:
- an inspection result is committed only if HEAD did not move during the walk;
- an assessment is committed only against the constraint set it evaluated;
- a revision with a COMPLETED inspection by this extractor is never walked
  again — a constraint change re-evaluates the stored payload instead;
- a revision that failed MAX_ATTEMPTS counted times waits for HEAD to move.
"""

import json
import logging
import time
from datetime import datetime

from ...infra.artifacts import store as artifacts
from ...infra.db import rows
from ..application import errors, world
from ..domain import entities
from . import drift, inspection

log = logging.getLogger('archeus.core')

BACKOFF_S = 60.0
BACKOFF_MAX_S = 3600.0


def backoff(attempts):
    """Seconds to wait after the *attempts*-th counted failure."""
    return 0.0 if attempts == 0 else min(BACKOFF_S * 2 ** (attempts - 1), BACKOFF_MAX_S)


def _epoch(stamp):
    return datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()


class World:
    def __init__(self, db, *, actor, clock=time.time):
        self.db, self.actor, self.clock = db, actor, clock
        self.on_wake = None          # set by the thread that runs the passes
        self.stopping = lambda: False

    # ── planning ──

    def _due(self, failed):
        f = failed.entity
        if f.attempts >= world.MAX_ATTEMPTS:
            return False
        if (f.failure or '').split(':', 1)[0] in world.UNCOUNTED:
            return True
        return self.clock() >= _epoch(f.failed_at) + backoff(f.attempts)

    def plan(self, conn):
        """[(action, repository row, detail)] — the work due now."""
        work, sets = [], {}
        for r in rows.where(conn, entities.Repository):
            repo = r.entity
            if repo.project_id not in sets:
                cs = world.constraints(conn, repo.project_id)
                sets[repo.project_id] = drift.token(cs)
            try:
                head, why = inspection.head_revision(repo.path), None
            except inspection.Unreadable as e:
                head, why = None, e.reason
            if head is not None:
                # a current assessment stays current across an extractor
                # upgrade: the architecture machine has no edge for it (D5),
                # so the new extractor walks at the next HEAD move or
                # constraint change, never re-evaluating an old observation
                if (repo.architecture_state in ('CONSISTENT', 'DRIFTED')
                        and repo.last_revision == head
                        and repo.evaluated_against == sets[repo.project_id]):
                    continue
                done = world.completed_inspection(conn, repo.id, head)
                if done is not None:
                    if (repo.architecture_state in ('UNKNOWN', 'STALE')
                            or repo.last_inspection_id != done.entity.id
                            or repo.evaluated_against != sets[repo.project_id]):
                        work.append(('assess', r, {'inspection': done}))
                    continue
            tries = [x for x in rows.where(conn, entities.RepositoryInspection,
                                           repository_id=repo.id,
                                           extractor_version=inspection.EXTRACTOR_VERSION)
                     if x.entity.revision == head and x.entity.state != 'COMPLETED']
            last = tries[-1] if tries else None
            if last is not None and (last.entity.state != 'FAILED' or not self._due(last)):
                continue
            work.append(('inspect' if head else 'unreadable', r,
                         {'head': head, 'why': why, 'retry_of': last and last.entity.id}))
        return work

    def pending(self):
        """How much world work is due now; wakes the worker when there is any."""
        with self.db.read() as conn:
            n = len(self.plan(conn))
        if n and self.on_wake is not None:
            self.on_wake()
        return n

    # ── doing ──

    def _run(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.actor))

    def sweep(self):
        return self._run(world.sweep_inspections)['failed']

    def pass_once(self):
        with self.db.read() as conn:
            work = self.plan(conn)
        for action, r, detail in work:
            if self.stopping():
                break
            getattr(self, '_' + action)(r.entity, **detail)
        return {'changed': bool(work), 'done': len(work)}

    def _unreadable(self, repo, head, why, retry_of):
        b = self._run(world.begin_inspection, repository_id=repo.id, revision=None,
                      retry_of=retry_of)
        self._run(world.fail_inspection, inspection_id=b['inspection_id'], failure=why)

    def _inspect(self, repo, head, why, retry_of):
        b = self._run(world.begin_inspection, repository_id=repo.id, revision=head,
                      retry_of=retry_of)
        iid = b['inspection_id']
        try:
            obs, payload = inspection.inspect(repo.path)
        except inspection.Unreadable as e:
            self._run(world.fail_inspection, inspection_id=iid, failure=e.reason)
            return
        except Exception as e:           # an extractor bug fails this inspection, not Core
            log.exception('inspection of %s failed', repo.path)
            self._run(world.fail_inspection, inspection_id=iid,
                      failure='error: %s: %s' % (type(e).__name__, e))
            return
        try:
            after = inspection.head_revision(repo.path)
        except inspection.Unreadable:
            after = None
        if after != head:
            # the walk read files of more than one revision: nothing is kept
            self._run(world.fail_inspection, inspection_id=iid, failure='revision_moved_during')
            return
        data = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        sha = artifacts.put(data)
        previous = self._previous(repo.id, head)
        change = None
        if previous is not None:
            change = inspection.diff(json.loads(artifacts.get(previous.payload_sha256)), payload,
                                     previous.to_dict(), obs)
        self._run(world.complete_inspection, inspection_id=iid, observation=obs,
                  payload_sha256=sha, payload_size=len(data), diff_from_previous=change)
        self._assess(repo, iid, payload)

    def _assess(self, repo, inspection=None, payload=None):
        iid = inspection if isinstance(inspection, str) else inspection.entity.id
        if payload is None:
            payload = json.loads(artifacts.get(inspection.entity.payload_sha256))
        with self.db.read() as conn:
            cs = world.constraints(conn, repo.project_id)
        findings = drift.evaluate(payload, cs)
        try:
            self._run(world.record_assessment, repository_id=repo.id, inspection_id=iid,
                      findings=findings, evaluated_against=drift.token(cs))
        except errors.LOST_RACE as e:
            # a constraint was declared (or the row moved) after we read: the
            # next pass sees the new set and evaluates again
            log.info('world lost a race on %s: %s', repo.id, e)

    def _previous(self, repository_id, head):
        with self.db.read() as conn:
            done = [x.entity for x in rows.where(conn, entities.RepositoryInspection,
                                                 repository_id=repository_id, state='COMPLETED')
                    if x.entity.revision != head]
        return done[-1] if done else None
