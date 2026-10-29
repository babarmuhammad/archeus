-- 0004: context packages (P5; p5-design-gate §4, context-and-knowledge §2.3).
--
-- Same row shape as 0001-0003. A package is immutable: written once by the
-- mission's `context_ready` move, never updated, so `version` stays 1. Items,
-- exclusions and conflicts are references with provenance in `body`; nothing
-- here copies the rows they point at, and no rendered text is stored.

CREATE TABLE context_packages (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id   TEXT REFERENCES projects (id),
    subject_kind TEXT NOT NULL,
    subject_id   TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL
);
CREATE INDEX context_packages_by_subject ON context_packages (subject_kind, subject_id);
