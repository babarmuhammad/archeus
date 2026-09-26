-- 0002: the work a mission is made of (P3.5 walking skeleton; domain-model §7.2-§7.7).
--
-- Same row shape as 0001: `id`, the promoted columns a query or a guard
-- snapshot filters on, `version`, timestamps, the audit pair and `body`.
-- A Plan is immutable once proposed (a replan is a new row with the next
-- `plan_version`); Task, Execution, Verification and Review move only through
-- `Tx.transition()`.

CREATE TABLE plans (
    id           TEXT PRIMARY KEY,
    mission_id   TEXT NOT NULL REFERENCES missions (id),
    plan_version INTEGER NOT NULL CHECK (plan_version >= 1),
    state        TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL,
    UNIQUE (mission_id, plan_version)
);

CREATE TABLE tasks (
    id          TEXT PRIMARY KEY,
    plan_id     TEXT NOT NULL REFERENCES plans (id),
    mission_id  TEXT NOT NULL REFERENCES missions (id),
    key         TEXT NOT NULL,
    state       TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL,
    UNIQUE (plan_id, key)
);
CREATE INDEX tasks_by_mission ON tasks (mission_id, state);

-- One attempt at a task. A retry is a new row with the next `attempt`, never
-- a reset of this one (state-machines §0: terminal states are terminal).
CREATE TABLE executions (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks (id),
    mission_id  TEXT NOT NULL REFERENCES missions (id),
    attempt     INTEGER NOT NULL CHECK (attempt >= 1),
    state       TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL,
    UNIQUE (task_id, attempt)
);
CREATE INDEX executions_by_state ON executions (state);

CREATE TABLE verifications (
    id          TEXT PRIMARY KEY,
    plan_id     TEXT NOT NULL REFERENCES plans (id),
    state       TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
CREATE INDEX verifications_by_plan ON verifications (plan_id);

CREATE TABLE reviews (
    id          TEXT PRIMARY KEY,
    mission_id  TEXT NOT NULL REFERENCES missions (id),
    plan_id     TEXT NOT NULL REFERENCES plans (id),
    state       TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
CREATE INDEX reviews_by_plan ON reviews (plan_id);
