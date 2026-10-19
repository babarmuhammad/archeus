### T-110 · O7 backoff/breaker: what the canonical design says (code-and-doc analysis for T-106)
owner: qwen · status: changes
auth: Owner 2026-10-19 (AskUserQuestion answer, verbatim): "T-108 round 5 (Recommended), T-109 Lows (Recommended), T-110 O7 read (Qwen), T-111 E1 evidence (Qwen)"
scope: .collab/T-110-o7-breaker.md (new note) and this card only.
refs: T-106; owner decision O7 2026-10-08 (isolation-establishment failures uncharged, with a backoff and breaker); reviews/T-102-c91d4f1.claude.md (63 executions in 4 s on a permanent Popen failure); docs/architecture/ (find O7 and every "backoff"/"breaker" for dispatch or spawn).
accept: quoting file:line, state: where O7 is recorded and its exact words; whether the design names the breaker's location, threshold, window, reset and visibility, or leaves any open (each open one is an owner question, listed); which existing breaker code (execution breaker AVAILABLE/DEGRADED/OPEN, pairing breaker, loop guard) could carry it, with file:line; the dispatch path a permanent spawn failure takes today (file:line) and why it loops.
verify: read-only grep and reading of D:/archeus-p20-mcp (git show b73f875:<path>); no code, no tests, no process, no native or ACL operation, no web fetch.
commits: - (note .collab/T-110-o7-breaker.md)
review: reviews/T-110-analysis.md CHANGES (Codex aimed, 2026-10-19; Claude read the verdict line only)
notes: CORRECTION REQUESTED 2026-10-19 (Claude, metadata only): address every finding in .collab/reviews/T-110-analysis.md; when done QWEN-DONE-T-110.md STATUS: review. Queued for Qwen after T-008. DONE 2026-10-19 (Qwen): report in .collab/QWEN-DONE-T-110.md. Feeds T-106: once the owner answers the open questions, T-106 becomes ready for Claude on T-108's candidate.

QUESTION:
Judge only Qwen's note .collab/T-110-o7-breaker.md against the T-110 card in .collab/QWEN-CARD-T-110.md: verify each file:line it cites against `git show b73f875:<path>`; is O7's record quoted exactly; are the breaker's location, threshold, window, reset and visibility correctly reported as decided or open; is the permanent-spawn-failure loop path right? List every open owner question it should have listed and did not.

Reply in exactly this format, nothing before it:
VERDICT: APPROVE | CHANGES | ESCALATE
1. path:line - problem - required change
(one numbered line per finding; "none" if APPROVE with no findings)
Not checked: <what you could not verify, or "nothing">

ESCALATE means only the owner can decide (canonical-doc conflict, missing authorization).


CORRECTION REQUESTED 2026-10-19 (Claude, metadata only) - this run:
- Address every finding in .collab/reviews/T-110-analysis.md (Codex, CHANGES, 8 findings). Fix each IN PLACE in
  .collab/T-110-o7-breaker.md and add a section "## Correction 2026-10-19 (Qwen) - reviews/T-110-analysis.md" that
  answers each finding by number with the new file:line.
- The candidate source is checked out read-only at C:\Users\mab\qwen-src\b73f875 (it replaces D:/archeus-p20-mcp, which no
  longer exists). Read files there with your read/grep/find tools; you have no shell and need none.
- Edit only .collab/T-110-o7-breaker.md and .collab/QWEN-DONE-T-110c.md in your sandbox. Never edit anything under
  C:\Users\mab\qwen-src. No tests, no process, no web.
- When done write .collab/QWEN-DONE-T-110c.md: first line "STATUS: review", then one line per finding (number - what changed).
