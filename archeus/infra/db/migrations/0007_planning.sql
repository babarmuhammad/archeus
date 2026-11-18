-- 0007: the plan engine (P8; p8-design-gate §5, §13, §20).
--
-- A `plans` row is one immutable PlanVersion. Two fields are promoted to
-- columns: `supersedes_plan_id` (the version it replaced) and `round_seq` (the
-- seq of the event that started its planning round). `(mission_id, round_seq)`
-- is UNIQUE, so a re-delivered or raced round can never record a second
-- version; plans recorded outside a round (the stub brain) have no round_seq,
-- which SQLite's UNIQUE allows any number of.
--
-- The plan machine gained its edges (state-machines §2.1). Rows written before
-- it were all left DRAFT; per mission the highest version is the one that was
-- in force (PROPOSED: validated, never approved by a real policy) and every
-- lower one had been replaced (SUPERSEDED). Development databases only: V1 is
-- unreleased, and no event is written for this backfill.

ALTER TABLE plans ADD COLUMN supersedes_plan_id TEXT REFERENCES plans (id);
ALTER TABLE plans ADD COLUMN round_seq INTEGER CHECK (round_seq >= 1);
CREATE UNIQUE INDEX plans_by_round ON plans (mission_id, round_seq);

UPDATE plans SET state = 'SUPERSEDED'
 WHERE state = 'DRAFT'
   AND plan_version < (SELECT MAX(p.plan_version) FROM plans p
                        WHERE p.mission_id = plans.mission_id);
UPDATE plans SET state = 'PROPOSED' WHERE state = 'DRAFT';
