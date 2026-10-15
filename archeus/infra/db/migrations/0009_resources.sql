-- 0009: the resource router (P10; p10-design-gate §5).
--
-- Same row shape as 0001-0008. Three new tables and four promoted columns:
--
-- `accounts`           an authenticated instance of a harness; its health moves
--                      along the account_health machine.
-- `resource_policies`  one per account (UNIQUE): priority, the allocation
--                      ceiling, reserves, budgets, project restrictions.
-- `usage_snapshots`    one observation of one provider window, never rewritten
--                      (observed truth; the router reads the newest per window).
--
-- `route_decisions` gains `mission_id` and `task_id` (a task's routing is
-- looked up by both); `usage_ledger` gains `account_id` (budgets sum it per
-- account). Rows written before this migration keep NULL there: an own call
-- before P10 named its harness home in `account_ref`, never an account.

CREATE TABLE accounts (
    id          TEXT PRIMARY KEY,
    harness_id  TEXT NOT NULL,
    health      TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
CREATE INDEX accounts_by_harness ON accounts (harness_id);

CREATE TABLE resource_policies (
    id          TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL UNIQUE REFERENCES accounts (id),
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);

CREATE TABLE usage_snapshots (
    id          TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL REFERENCES accounts (id),
    window      TEXT NOT NULL,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
CREATE INDEX usage_snapshots_by_account ON usage_snapshots (account_id, window);

ALTER TABLE route_decisions ADD COLUMN mission_id TEXT REFERENCES missions (id);
ALTER TABLE route_decisions ADD COLUMN task_id TEXT REFERENCES tasks (id);
CREATE INDEX route_decisions_by_task ON route_decisions (task_id);
ALTER TABLE usage_ledger ADD COLUMN account_id TEXT REFERENCES accounts (id);
CREATE INDEX usage_ledger_by_account ON usage_ledger (account_id);
