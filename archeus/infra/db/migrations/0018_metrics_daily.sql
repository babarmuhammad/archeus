-- 0018: metrics_daily (P21 slice D, p21-design-gate D2, plan section 28).
--
-- One row per finished UTC day, written once by Core's metrics worker after the
-- day ends; `metrics` is a JSON object of the plan's figures, each None when the
-- day had nothing to measure (never 0 for "unknown"). Nothing else writes it.
-- 0018: it follows slice A's 0017_artifact_records.

CREATE TABLE metrics_daily (
    day         TEXT PRIMARY KEY,
    metrics     TEXT NOT NULL,
    computed_at TEXT NOT NULL
);
