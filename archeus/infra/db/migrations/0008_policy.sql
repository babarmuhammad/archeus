-- 0008: policy, autonomy and authorisation (P9; p9-design-gate §15, D17).
--
-- Same row shape as 0001-0007. Three tables, none of them ever rewritten:
--
-- `policy_rules`     one immutable rule revision; a change retires the old row
--                    (`retired_at`, written once) and inserts the next revision
--                    (`supersedes_rule_id`). Built-in and profile rules are
--                    code, never rows.
-- `policy_decisions` one evaluation, recorded with the move it justifies;
--                    every field frozen. A later evaluation is a new row.
-- `approvals`        a user device's decision about one exact identity
--                    (`action_hash`, p9-design-gate §7); its content is frozen,
--                    its state moves along the Approval machine. At most one
--                    live (PENDING or APPROVED) approval per identity, so the
--                    same thing asked twice finds the same row.
--
-- No backfill: a plan the P1 stub policy "approved" has no authorisation, and
-- inventing one would be the thing P9 exists to prevent (§15).

CREATE TABLE policy_rules (
    id                 TEXT PRIMARY KEY,
    scope_level        TEXT NOT NULL,
    scope_ref          TEXT,
    action_class       TEXT NOT NULL,
    decision           TEXT NOT NULL,
    retired_at         TEXT,
    supersedes_rule_id TEXT REFERENCES policy_rules (id),
    version            INTEGER NOT NULL CHECK (version >= 1),
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    created_by         TEXT NOT NULL,
    updated_by         TEXT NOT NULL,
    body               TEXT NOT NULL
);
CREATE INDEX policy_rules_live ON policy_rules (action_class, scope_level)
    WHERE retired_at IS NULL;

CREATE TABLE policy_decisions (
    id          TEXT PRIMARY KEY,
    stage       TEXT NOT NULL,
    mission_id  TEXT REFERENCES missions (id),
    plan_id     TEXT REFERENCES plans (id),
    task_id     TEXT REFERENCES tasks (id),
    decision    TEXT NOT NULL,
    action_hash TEXT,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
CREATE INDEX policy_decisions_by_mission ON policy_decisions (mission_id, stage);

CREATE TABLE approvals (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    mission_id  TEXT NOT NULL REFERENCES missions (id),
    plan_id     TEXT NOT NULL REFERENCES plans (id),
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
CREATE UNIQUE INDEX approvals_live ON approvals (action_hash)
    WHERE state IN ('PENDING', 'APPROVED');
CREATE INDEX approvals_by_mission ON approvals (mission_id, state);
