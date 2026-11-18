-- 0013: Pause all batches (P19.5 Core slice; ADR-0030, ADR-0042 §1).
--
-- Same row shape as 0001-0012. One new table:
--
-- `pause_batches`  one Pause all: the missions it paused (body). Immutable.
--                  Resume all reads the newest row and resumes those of its
--                  missions still PAUSED by it (`Mission.pause_batch_id`, a body
--                  field): never the event log, which retention may prune.

CREATE TABLE pause_batches (
    id          TEXT PRIMARY KEY,
    version     INTEGER NOT NULL CHECK (version >= 1),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    body        TEXT NOT NULL
);
