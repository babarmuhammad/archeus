-- 0003: the world model (P4; p4-design-gate §4, domain-model §3.1, §4, §5).
--
-- Same row shape as 0001/0002. A repository is registered once per workspace:
-- `path_key` is its real, case-folded path, so two spellings of one directory
-- are one key. An inspection is an observation of one repository at one
-- revision; the drift assessment lives on the repository, beside the exact
-- constraints it was evaluated against. `users` holds at most the owner, whose
-- row is written by the first digest acknowledgement.

CREATE TABLE users (
    id          TEXT PRIMARY KEY,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);

CREATE TABLE projects (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    state        TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL
);

CREATE TABLE repositories (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL,
    project_id         TEXT NOT NULL REFERENCES projects (id),
    path_key           TEXT NOT NULL,
    architecture_state TEXT NOT NULL,
    version            INTEGER NOT NULL CHECK (version >= 1),
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    created_by         TEXT NOT NULL,
    updated_by         TEXT NOT NULL,
    body               TEXT NOT NULL,
    UNIQUE (workspace_id, path_key)
);
CREATE INDEX repositories_by_project ON repositories (project_id);

CREATE TABLE repository_inspections (
    id                TEXT PRIMARY KEY,
    repository_id     TEXT NOT NULL REFERENCES repositories (id),
    revision          TEXT,
    extractor_version INTEGER NOT NULL,
    state             TEXT NOT NULL,
    version           INTEGER NOT NULL CHECK (version >= 1),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    updated_by        TEXT NOT NULL,
    body              TEXT NOT NULL
);
CREATE INDEX inspections_by_repository ON repository_inspections (repository_id, state);

CREATE TABLE knowledge_items (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id   TEXT REFERENCES projects (id),
    type         TEXT NOT NULL,
    state        TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL
);
CREATE INDEX knowledge_by_project ON knowledge_items (project_id, type, state);
