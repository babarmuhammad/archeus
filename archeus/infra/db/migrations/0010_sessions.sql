-- 0010: session and context continuity (P12; p12-design-gate §20).
--
-- Same row shape as 0001-0009. Two new tables:
--
-- `sessions`     a provider conversation (headless: the one an execution ran in;
--                interactive_attached / manual: a user's own). Its workspace and
--                project are fixed at creation, its mission is a link. A hand-off
--                target names its source; (source, request) is unique, so the
--                same hand-off request can never make a second target.
-- `checkpoints`  Core-derived history of one ended execution: at most one per
--                execution (UNIQUE), never rewritten.
--
-- Executions gain nothing promoted: `session_id`, `handoff_from` and `pressure`
-- are body fields, read with the execution itself.

CREATE TABLE sessions (
    id                       TEXT PRIMARY KEY,
    workspace_id             TEXT NOT NULL,
    project_id               TEXT REFERENCES projects (id),
    mission_id               TEXT REFERENCES missions (id),
    harness_id               TEXT NOT NULL,
    state                    TEXT NOT NULL,
    handoff_from_session_id  TEXT REFERENCES sessions (id),
    handoff_request          TEXT,
    version                  INTEGER NOT NULL CHECK (version >= 1),
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    created_by               TEXT NOT NULL,
    updated_by               TEXT NOT NULL,
    body                     TEXT NOT NULL,
    UNIQUE (handoff_from_session_id, handoff_request)
);
CREATE INDEX sessions_by_mission ON sessions (mission_id);
CREATE INDEX sessions_by_project ON sessions (project_id);

CREATE TABLE checkpoints (
    id            TEXT PRIMARY KEY,
    execution_id  TEXT NOT NULL UNIQUE REFERENCES executions (id),
    mission_id    TEXT NOT NULL REFERENCES missions (id),
    task_id       TEXT REFERENCES tasks (id),
    version       INTEGER NOT NULL CHECK (version >= 1),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    created_by    TEXT NOT NULL,
    updated_by    TEXT NOT NULL,
    body          TEXT NOT NULL
);
CREATE INDEX checkpoints_by_mission ON checkpoints (mission_id);
CREATE INDEX checkpoints_by_task ON checkpoints (task_id);
