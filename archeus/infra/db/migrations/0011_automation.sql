-- 0011: automations and their runs (P14; p14-design-gate §7).
--
-- Same row shape as 0001-0010. Two new tables:
--
-- `automations`      a persistent rule: its scope is promoted (workspace, project),
--                    so the consumer reads the enabled rules of one scope; the
--                    trigger and the mission template are body fields.
-- `automation_runs`  one decision about one event. (automation, event seq) is
--                    UNIQUE: that constraint is P14's idempotency key, so a
--                    re-delivered event can never claim a second run.

CREATE TABLE automations (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL,
    project_id    TEXT REFERENCES projects (id),
    principal_id  TEXT REFERENCES principals (id),
    state         TEXT NOT NULL,
    version       INTEGER NOT NULL CHECK (version >= 1),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    created_by    TEXT NOT NULL,
    updated_by    TEXT NOT NULL,
    body          TEXT NOT NULL
);
CREATE INDEX automations_by_state ON automations (state);

CREATE TABLE automation_runs (
    id                    TEXT PRIMARY KEY,
    automation_id         TEXT NOT NULL REFERENCES automations (id),
    triggering_event_seq  INTEGER NOT NULL,
    mission_id            TEXT REFERENCES missions (id),
    state                 TEXT NOT NULL,
    version               INTEGER NOT NULL CHECK (version >= 1),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    created_by            TEXT NOT NULL,
    updated_by            TEXT NOT NULL,
    body                  TEXT NOT NULL,
    UNIQUE (automation_id, triggering_event_seq)
);
CREATE INDEX automation_runs_by_mission ON automation_runs (mission_id);
