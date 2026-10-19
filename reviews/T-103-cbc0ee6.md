VERDICT: CHANGES
1. docs/architecture/p20-design-gate.md:2624 - “in the idempotency table for 24 h” confuses replay validity with retention: writer._recall deletes expired rows only when their key is reused; retention.prune has no production caller. PIN hashes can persist indefinitely and enter later backups - document 24 h replay validity separately from unbounded row retention; remove implied backup exposure window. Other corrections answer prior findings; diff adds 58 lines, removes none.
Not checked: Tests, actual permissions, real credential files or backups; full T-096/T-099 implementations outside cbc0ee6.

Aimed Codex review (owner 2026-10-16: aimed reviews only); the question asked is in .collab/BOARD.md.
