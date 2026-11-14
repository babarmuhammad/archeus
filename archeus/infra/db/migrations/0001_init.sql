-- 0001: the P2 schema (target-architecture §5, domain-model §1, §3, §9.5, §10).
--
-- Entity tables share one shape: `id`, the fields promoted to columns (scope,
-- state, foreign keys), `version` for optimistic concurrency, timestamps, the
-- audit pair `created_by`/`updated_by` (the acting principal), and `body` — the
-- entity's remaining fields as JSON, validated by the domain dataclass, never by
-- SQL. Only entities P2 persists have a table; later phases add theirs.
--
-- Portable to SQLite 3.31: no RETURNING, no STRICT, no JSON functions.

CREATE TABLE principals (
    id          TEXT PRIMARY KEY,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);

CREATE TABLE devices (
    id           TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL REFERENCES principals (id),
    state        TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL
);

-- Credentials (api-and-realtime §5.3): only sha256(token) is ever stored; the
-- token itself is shown once. Minting and verification arrive with the API.
CREATE TABLE tokens (
    token_hash   TEXT PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('device', 'node', 'execution')),
    principal_id TEXT NOT NULL REFERENCES principals (id),
    scopes       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    expires_at   TEXT,
    revoked_at   TEXT
);

CREATE TABLE missions (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id   TEXT,
    state        TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL
);
CREATE INDEX missions_by_scope_state ON missions (workspace_id, project_id, state);

-- Content-addressed: the id IS the sha256; the blob lives in artifacts/ab/cd/<sha>.
CREATE TABLE artifacts (
    id          TEXT PRIMARY KEY,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);

-- The append-only history, and the outbox: consumers read it by `seq`.
-- AUTOINCREMENT, not a bare INTEGER PRIMARY KEY: a seq is never reused, even
-- after retention deletes the newest rows, so a cursor can never be handed an
-- event it has already passed.
CREATE TABLE events (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL UNIQUE,
    type         TEXT NOT NULL,
    at           TEXT NOT NULL,
    -- the envelope's `actor`: the causing PRINCIPAL (domain-model §9.5
    -- `actor_principal_id` is `actor_id`), never an execution or device id
    actor_kind   TEXT NOT NULL,
    actor_id     TEXT NOT NULL,
    cause_chain  TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_id   TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    project_id   TEXT,
    visibility   TEXT NOT NULL CHECK (visibility IN ('user', 'system')),
    payload      TEXT NOT NULL
);
CREATE INDEX events_by_subject ON events (subject_kind, subject_id, seq);

-- One row per outbox consumer (state-machines §14).
CREATE TABLE consumer_cursors (
    name        TEXT PRIMARY KEY,
    last_seq    INTEGER NOT NULL CHECK (last_seq >= 0),
    updated_at  TEXT NOT NULL
);

-- What a consumer has already done for an event, so re-delivery after a crash
-- between the effect and the cursor advance repeats nothing.
CREATE TABLE consumer_effects (
    consumer    TEXT NOT NULL,
    event_seq   INTEGER NOT NULL,
    result      TEXT NOT NULL,
    at          TEXT NOT NULL,
    PRIMARY KEY (consumer, event_seq)
);

-- A repeated command returns its original response (api-and-realtime §2: 24 h).
CREATE TABLE idempotency_keys (
    key          TEXT PRIMARY KEY,
    command      TEXT NOT NULL,
    actor        TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response     TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
