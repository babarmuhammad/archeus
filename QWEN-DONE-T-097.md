STATUS: review

Card T-097 — CORRECTION r2 DONE 2026-10-19 (Qwen): the single finding of
`.collab/reviews/T-097-analysis.r2.md` is answered in place in
`.collab/T-097-login-probe-reads.md`.

## Commits
- None. Analysis card; scope is `.collab/T-097-login-probe-reads.md` (plus this card
  file), both under `/.collab/` excluded via `.git/info/exclude:20` — verified with
  `git check-ignore -v`. Card `commits:` stays `—`; no tracked file changed.

## What the r2 finding required, and what was changed
Finding (verbatim): "Finding 2 remains partly inaccurate: email, plan and tier are
copied credential-file fields (853f63f:claude_sessions/usage.py:73-87), returned through
GUI API (gui_api.py:1149-1154). Required change: remove 'not a field of the file' and
narrow 'only place a field ... leaves the process' to accessToken. Findings 1 and 3
answered accurately."

Fixed in place, in the "Sent anywhere" bullet:
1. "and it is derived account metadata, not a field of the file" — REMOVED; the bullet
   now names `email`/`plan`/`tier` as credential-file fields copied by `_account_email`
   (claude_sessions/usage.py:71-80) and `account_meta` (usage.py:83-87) from the
   `claudeAiOauth` block, returned by `api_usage_plan` (gui_api.py:1149, 1154).
2. "the only place a field of `.credentials.json` leaves the process" — NARROWED to the
   access token: `accessToken` reaches the network only via the Bearer header
   (usage.py:129-133 → USAGE_URL usage.py:18); the file-sourced email/plan/tier leave
   the process only through the local 127.0.0.1 GUI response (gui.py:3, 1005;
   gui_api.py:1166, route 4638).
Also corrected while re-checking citations for this round (same bullet/table):
sibling-readers table spans `_token_expired` 61-68, `_account_email` 71-80,
`account_meta` 83-87, and `_acct_state` write lines usage.py:169-171. A dated
"Correction r2 2026-10-19 (Qwen)" section records the change; the earlier
2026-10-16 correction section is left as history. No conclusion moved: D7
(Core stores no API key) stands. Card set to `status: review` with the
"CORRECTION r2 DONE 2026-10-19 (Qwen):" notes prefix.

## What ran (all read-only, per card verify:)
In D:/archeus-p20-i, candidate `853f63f` (`git rev-parse --short HEAD`; clean tree):
- `grep -n` on claude_sessions/usage.py: def lines 45/57/61/71/83/213/241, email keys
  (75), subscriptionType/rateLimitTier (86-87), Bearer (130), USAGE_URL (18, 129) —
  all citations in the corrected bullet re-checked against these.
- Read-only `sed`/`awk` views of usage.py 40-89, 118-136, 160-180, 241-262;
  gui.py 3, 572/589, 1000-1010 (ThreadingHTTPServer / 127.0.0.1);
  gui_api.py 1125-1132, 1146-1156, 1164-1168 and route-table line 4638.
- In D:/Claude: `git check-ignore -v` on the two edited files (both excluded);
  `git status --porcelain -- .collab` empty.
All exact results are reflected in the note text; no command produced an error.

## What was NOT run
- No tests (card verifies by read-only source inspection only).
- No file under any account home, `~/.claude` or any credential store was opened,
  listed or printed; no command read user files.
- No network. No code or test change. No push, no staging, no commit
  (nothing in scope is git-tracked).
- Exception-message contents and the rest of the note outside the corrected
  bullet/table were not re-audited this round (r2 marked findings 1 and 3 accurate).

Signed: Qwen (pi, spark/qwen3.8-flash-next) — card owner per `owner: qwen`.
