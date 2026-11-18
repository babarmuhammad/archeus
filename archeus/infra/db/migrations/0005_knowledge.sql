-- 0005: knowledge and learning (P6; p6-design-gate §4, domain-model §4, §5, §7.8, §8).
--
-- Same row shape as 0001-0004. Relations are flat, with both ends indexed, so
-- a neighbourhood is two index lookups. A route decision is written before
-- the call it routes (INTENT's discipline) and gains its `outcome` once, when
-- the call ends; usage of an own call is ledgered against it, not against an
-- execution (ADR-0022). `provider_terms` is keyed by harness id: one row per
-- ADR-0021 answer, and no row means the answer is still `unknown`.

CREATE TABLE relations (
    id          TEXT PRIMARY KEY,
    src_kind    TEXT NOT NULL,
    src_id      TEXT NOT NULL,
    rel         TEXT NOT NULL,
    dst_kind    TEXT NOT NULL,
    dst_id      TEXT NOT NULL,
    project_id  TEXT,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
CREATE INDEX relations_from ON relations (src_kind, src_id, rel);
CREATE INDEX relations_to ON relations (dst_kind, dst_id, rel);

CREATE TABLE meetings (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id   TEXT REFERENCES projects (id),
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL
);

CREATE TABLE feedback (
    id          TEXT PRIMARY KEY,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);

CREATE TABLE route_decisions (
    id          TEXT PRIMARY KEY,
    purpose     TEXT,
    project_id  TEXT,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
CREATE INDEX route_decisions_by_purpose ON route_decisions (purpose, project_id);

CREATE TABLE usage_ledger (
    id                TEXT PRIMARY KEY,
    execution_id      TEXT,
    route_decision_id TEXT REFERENCES route_decisions (id),
    version           INTEGER NOT NULL CHECK (version >= 1),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    updated_by        TEXT NOT NULL,
    body              TEXT NOT NULL
);

CREATE TABLE provider_terms (
    id          TEXT PRIMARY KEY,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
