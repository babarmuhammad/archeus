-- 0014: a mission's start can be an approval (P19 S4; p19-design-gate B6).
--
-- An approval of kind `start` is consent to start one mission under `careful`,
-- bound to the mission alone: it is asked before there is a plan, so
-- `approvals.plan_id` becomes nullable. SQLite cannot drop a NOT NULL, so the
-- table is rebuilt with the same rows and indexes. Nothing references
-- `approvals (id)`, so the rebuild needs no foreign-key pause.

CREATE TABLE approvals_0014 (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    mission_id  TEXT NOT NULL REFERENCES missions (id),
    plan_id     TEXT REFERENCES plans (id),
    task_id     TEXT REFERENCES tasks (id),
    action_hash TEXT NOT NULL,
    state       TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
INSERT INTO approvals_0014 SELECT id, kind, mission_id, plan_id, task_id, action_hash, state,
    expires_at, version, created_at, updated_at, created_by, updated_by, body FROM approvals;
DROP TABLE approvals;
ALTER TABLE approvals_0014 RENAME TO approvals;
CREATE UNIQUE INDEX approvals_live ON approvals (action_hash)
    WHERE state IN ('PENDING', 'APPROVED');
CREATE INDEX approvals_by_mission ON approvals (mission_id, state);
