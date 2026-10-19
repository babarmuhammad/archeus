VERDICT: CHANGES
1. .collab/T-097-login-probe-reads.md:115 - Finding 2 remains partly inaccurate: email, plan and tier are copied credential-file fields (853f63f:claude_sessions/usage.py:73-87), returned through GUI API (gui_api.py:1149-1154). Required change: remove “not a field of the file” and narrow “only place a field ... leaves the process” to accessToken. Findings 1 and 3 answered accurately.
Not checked: Rest of note, runtime behavior, exception-message contents, real credential files; no tests run.

Aimed Codex review (owner 2026-10-16: aimed reviews only); the question asked is in .collab/BOARD.md.
