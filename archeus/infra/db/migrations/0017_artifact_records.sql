-- 0017: the artifact producer record (P21 D5; ADR-0034 §1; ADR-0030 §4).
--
-- Who produced an artifact: an execution, for a task of a mission, with the
-- artifact's kind and label. A table of its own because an artifact is
-- content-addressed, so the same bytes from two producers are one artifact row
-- and two records here. Rows are immutable; the producer reference lives in the
-- body, and the task and mission columns are what records are read by.

CREATE TABLE artifact_records (
    id           TEXT PRIMARY KEY,
    artifact_id  TEXT NOT NULL REFERENCES artifacts (id),
    task_id      TEXT REFERENCES tasks (id),
    mission_id   TEXT REFERENCES missions (id),
    version      INTEGER NOT NULL CHECK (version >= 1),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    body         TEXT NOT NULL
);
CREATE INDEX artifact_records_by_task ON artifact_records (task_id);
CREATE INDEX artifact_records_by_mission ON artifact_records (mission_id);
CREATE INDEX artifact_records_by_artifact ON artifact_records (artifact_id);
