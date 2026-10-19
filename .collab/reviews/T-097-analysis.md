VERDICT: CHANGES
1. .collab/T-097-login-probe-reads.md:68 - “Core never reads this cache” is false: archeus/core/routing/usage.py:63-64 calls windows_snapshot(..., poll=True), reading cached windows/status and starting background credential reads - document this indirect Core path; distinguish it from register/enable authentication. D7 still stands: this path stores no API key.
2. .collab/T-097-login-probe-reads.md:73 - “Sent anywhere: one place” misses credential-derived email, plan and tier returned through GUI API (claude_sessions/gui_api.py:1149-1154,1166) - distinguish accessToken’s Bearer-header send to Anthropic from metadata copied into cache and GUI responses.
3. .collab/T-097-login-probe-reads.md:72 - Header placement does not prove exception messages can never contain credentials; usage.py:163 logs unexpected exceptions without explicit redaction - narrow claim to no explicit credential logging in inspected code.
Not checked: Runtime behavior, external Claude CLI internals, real credential files; no tests run. Note absent from candidate checkout and commit 853f63f; reviewed D:/Claude/.collab/T-097-login-probe-reads.md against candidate source.

Aimed Codex review (owner 2026-10-16: aimed reviews only); the question asked is in .collab/BOARD.md.
