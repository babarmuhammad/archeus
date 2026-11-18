-- 0012: account protection (AP-1; ADR-0041 §1, §3; ADR-0048).
--
-- The new fields live in the row body and need no column: a policy's
-- `consumption` reads `normal` when absent, a ledger row's figures may be
-- NULL (not reported, never 0) and its `basis` reads `partial` when absent,
-- because a row written before this migration never said it was the total.
--
-- One promoted column: `accounts.home_key`, the canonical home (ADR-0048
-- D-25.2), so that one home is registered at most once per harness. NULL (no
-- home) is never a duplicate. V1 has one node (ADR-0008), so the index is per
-- harness; the command checks the node as well.

ALTER TABLE accounts ADD COLUMN home_key TEXT;
CREATE UNIQUE INDEX accounts_one_per_home ON accounts (harness_id, home_key)
    WHERE home_key IS NOT NULL;
