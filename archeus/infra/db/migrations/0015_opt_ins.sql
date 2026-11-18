-- 0015: settings-source opt-ins (P20 D6; ADR-0049 §2).
--
-- One row per thing an account's or a project's executions are let load again
-- from their settings sources: a source, a plugin or an MCP server. Exactly one
-- owner per row. An opt-out is the same row's next version (`opted_in` false),
-- so a name is opted in or out by one row, never two: the unique index is
-- per owner, kind and name, the absent owner read as ''.
--
-- An execution's inventory reference (`inventory_sha256`) lives in the
-- execution row's body: nothing queries by it, so it needs no column.

CREATE TABLE opt_ins (
    id          TEXT PRIMARY KEY,
    account_id  TEXT REFERENCES accounts (id),
    project_id  TEXT REFERENCES projects (id),
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL,
    CHECK ((account_id IS NULL) <> (project_id IS NULL))
);
CREATE UNIQUE INDEX opt_ins_one ON opt_ins (IFNULL(account_id, ''), IFNULL(project_id, ''),
                                            kind, name);
