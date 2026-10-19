### T-110 · O7 backoff/breaker: what the canonical design says (code-and-doc analysis for T-106)
owner: qwen · status: review
auth: Owner 2026-10-19 (AskUserQuestion answer, verbatim): "T-108 round 5 (Recommended), T-109 Lows (Recommended), T-110 O7 read (Qwen), T-111 E1 evidence (Qwen)"
scope: .collab/T-110-o7-breaker.md (new note) and this card only.
refs: T-106; owner decision O7 2026-10-08 (isolation-establishment failures uncharged, with a backoff and breaker); reviews/T-102-c91d4f1.claude.md (63 executions in 4 s on a permanent Popen failure); docs/architecture/ (find O7 and every "backoff"/"breaker" for dispatch or spawn).
accept: quoting file:line, state: where O7 is recorded and its exact words; whether the design names the breaker's location, threshold, window, reset and visibility, or leaves any open (each open one is an owner question, listed); which existing breaker code (execution breaker AVAILABLE/DEGRADED/OPEN, pairing breaker, loop guard) could carry it, with file:line; the dispatch path a permanent spawn failure takes today (file:line) and why it loops.
verify: read-only grep and reading of D:/archeus-p20-mcp (git show b73f875:<path>); no code, no tests, no process, no native or ACL operation, no web fetch.
commits: -
review: independent Claude reviewer (metadata plus the cited lines). No Codex unless the note reports a conflict between canonical documents.
notes: Feeds T-106: once the owner answers the open questions, T-106 becomes ready for Claude on T-108's candidate.
  QWEN 2026-10-19: note written at .collab/T-110-o7-breaker.md (byline Qwen). O7 decision quoted from
  PV20-S1-GATE-2026-10-08.md §7 lines 128–141 (plus its placements at §7.3 157–163 and §7.5 item 10
  181–183); deferral chain cited (p20 §4.2 371, §12 64 at 1250–1262 and 72 at 1420–1429, table 2770;
  p11 1018–1022 and 1030–1031; PV-20 309–312/400/650/715/894; ADR-0053 66/178–179/220). Breaker
  candidates with file:line at b73f875: execution breaker (states.py:285–303, executions.py:825–860,
  constants :799–801), harness state (states.py:395, no trip/reset moves), pairing breaker
  (api/auth.py:198–236, in-memory so not restart-reconcilable), P14 loop guard (automations.py:269–279,
  matcher.py:26–27 — the only existing "suspend until the user" exhaustion model), plus BLOCKING
  (executions.py:40–42, 211–212, 545–548) as the already-built halt. Loop traced to manager.py:332–341
  → executions.py:38–39/480–483 (uncharged → READY, max_attempts never consulted) → engine.py:272–280
  / work.py:315–330, with no idle wait at runtime.py:293–295; Case A (SpawnWriteFailed → charged
  workspace) already bounded, Case C (isolation establishment, isolation.py:1567–1602/783–799) latent
  behind PRODUCTION_DISPATCH_ENABLED=False (isolation.py:86–90, 685–696). Nine owner questions (Q1–Q9)
  listed in note §2; named-vs-open table included. No conflict between canonical documents found, so
  the card's review routing (independent Claude reviewer, no Codex) stands. VERIFY ran as written:
  read-only grep/reading only, code via `git show b73f875:<path>`; no tests, no processes, no native or
  ACL operation, no web fetch. commits: none — the deliverable is a .collab note (git-excluded), so
  there is nothing to show `git show` for; review.py will skip it as an analysis card.
