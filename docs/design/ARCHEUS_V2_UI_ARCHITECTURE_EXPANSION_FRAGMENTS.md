<!-- RECOVERY NOTE: this is NOT a reconstruction of a full document. It collects verbatim fragments
     of an EXPANDED, uncommitted revision of docs/design/ARCHEUS_V2_UI_ARCHITECTURE.md that existed
     in D:\Claude after the 2026-10-04 commit (`059b47c`, 762 lines) and before the 2026-10-19 wipe.
     The committed version has sections through "## T. Decisions, gates and the next phase" with no
     body; this later revision added real prototype RESULTS directly into new subsections (§D.1,
     §E.1, §J.4a, §K.1, §T.1, §T.2) and ran past line 1045. No Claude Code transcript in
     C:\Users\mab\.claude\projects\D--Archeus captured any edit to this file after its initial
     2026-10-04 authoring (see RECOVERY.md §1) — this expansion was made by some other means (most
     likely the same claude.ai/code cloud session referenced in commit 059b47c's `Claude-Session:`
     trailer, which leaves no local transcript here).

     Recovered instead from TWO Codex CLI sessions that later READ this file (never wrote to it):
     - C:\Users\mab\.codex\sessions\2026\10\09\rollout-2026-10-09T11-00-35-01a11fe4-8fb4-76a3-9298-9bface729ebc.jsonl.zst
       (an unrelated PV-20/S1 review session that happened to `cat`/`grep` this file for context)
     - C:\Users\mab\.codex\sessions\2026\10\11\rollout-2026-10-11T10-59-32-01a12a30-51d3-7b30-9737-95a802db19db.jsonl.zst
     Both are grep/read ECHOES, not edits — Codex made zero Write/Edit/apply_patch calls to any V2
     file in either the 804 zstd+plain rollouts search (task 1) or the plain .jsonl rollouts.
     Status: PARTIAL (fragments only — paragraph-level quotes and table rows, not a contiguous file).
-->

# Fragments recovered from the post-commit expansion of ARCHEUS_V2_UI_ARCHITECTURE.md

## Revised opening (replaces the committed intro's bullet list)

> **Status: ARCHITECTURE — DIRECTION RECORDED, NOT IMPLEMENTED.** This document defines the
> architecture that V2 UI implementation will follow. It is not an implementation plan, and it
> starts no implementation. Here is what is decided and what is not:
>
> - **Decided:** the direction the user gave on 2026-10-04, recorded in rulebook §46.4:
>   - S-1, S-2 and S-3 as V1 corrections;
>   - V-D1, V-D2 and V-D3;
>   - V-D4 and V-D5, gated on prototypes.
> - **Decided by prototype (the user, 2026-10-04; §T.1):** PR-1 PASS WITH VARIANT (the
>   `signature` thread, with "pen" in the light theme); PR-2 PASS for hand-built spatial
>   transitions and STOP for View Transitions in the Qt shell; PR-3 PASS WITH VARIANT for the
>   layered recede, with application scaling stopped; PR-4 PASS WITH VARIANT for the Display
>   instance of Segoe UI Variable on the hierarchy-opening sentence and headlines.
> - **Accepted as the working V2 direction (the user, 2026-10-05; §D.1):** PR-5 PASS WITH
>   VARIANT for treatment C, thread-derived state figures. Its human identification gate is
>   still open, so the decision stands on the lab measurements until a person has been tested.
> - **Proposed:** everything else, until it becomes an ADR or a design rule the user approves
>   (§T).
> - **V1 still governs.** ... This document amends it only in the single §27 clarification that
>   V-D1 required. "Do not proceed on inferred approval" (rulebook §0, R5) applies.

**This directly supersedes the committed intro's PR status.** The committed `059b47c` version
(docs/design/ARCHEUS_V2_UI_ARCHITECTURE.md:7-15, per git HEAD) only records V-D1…V-D5 as
"gated on prototypes" with no results — it predates PR-1…PR-5 actually running. The results above
are later and authoritative; nothing in the committed file contradicts them (the gate gained
results, it didn't change the gate), but anyone reading only HEAD would not know PR-1…PR-5 had
already run and passed (with variants) by 2026-10-04/05.

## §T.1 / §T.2 (new sections, not in the committed file — committed §T ends at "the next phase" with no subsections)

- `### T.1 Prototype results (V2-U0)` (heading only recovered; body partly reconstructed from the
  table rows below, sourced from the same expansion, line numbers as grepped by Codex)
- `### T.2 V2-U0 decision (2026-10-05): READY WITH CONDITIONS — nothing starts today` (heading
  only; body not recovered)

### PR result rows (table, §T.1; exact source lines unknown — recovered as isolated grep -n hits)

| Row | Content |
|---|---|
| PR-1 | The thread's light quality holds in Qt — p95 ≤ 16.7 ms during travel on integrated graphics; no tearing; idle invariant holds; HC/reduced forms correct. **Met.** A heap snapshot was also taken (§Frame rate / §Memory rows below). |
| PR-2 | Frame rate during motion: "Met in PR-1 and by spatial in PR-2 (View Transitions missed it, §C.5)." I.e. the hand-built spatial transition passed; the native View Transitions API failed in the Qt shell (consistent with the opening's "STOP for View Transitions in the Qt shell"). |
| PR-3 | The focus plane helps without discomfort — no discomfort reported; the base stays legible under the scrim. Kill fallback taken: "→ scrim only" (application-scaling recede was stopped per the opening paragraph). Adds ≈1.1 KB gzip. |
| PR-5 | The state pictures are identifiable without colour at 12/16/20 px — "the user identifies every state. **A human test**, run to the protocol in `results/pr5-ident.md`" (treatment D/C — the opening paragraph names "treatment C, thread-derived state figures" as accepted 2026-10-05; §D.1's heading says "PR-5, PASS WITH VARIANT, accepted as the working direction 2026-10-05"; a separate fragment says "treatment D, which lit the figures, put 1.4–2.5× the light source on the page" — the two treatment letters (C vs D) could not be reconciled from the fragments available; flagged as an open discrepancy, not resolved here). |
| PR-6 | **"Automated evidence recorded; the human gate is open."** K-1, K-2 and K-3 each pass every measure: ≤ 900 ms; Qt p95 16.7–16.8 ms with 0 long frames; rest = reduced form, 0 px in every environment; 0 hot-band light at rest; 27–96 ms CPU per occurrence. K-2 and K-3 need the tuned governor (§C.6 F-2/F-8/F-9: about 4.5 heroes on a typical day, never more than 2 in ten minutes, synthetic replay). K-4 passes as a design and is deferred to V2-U5 (needs P21). The rich forms are costed candidates. The dogfood kit is built and smoke-tested against a stub Core; **0 of 14 days run.** Recorded 2026-10-05 (§K.1 heading: "PR-6 result (recorded 2026-10-05; the two-week human gate is OPEN)"). Source: `prototypes/v2-u0/results/pr6.md`. |

### Budget, as re-measured in this expansion (§ unclear, likely still §Q)

> **Committed so far:** spatial transitions about 2.2 KB gzip unminified (PR-2) + the layered
> recede about 1.1 KB (PR-3) + display typography about 0.24 KB (PR-4) + the thread-derived state
> figures and spine about 3.5 KB (PR-5) ≈ **7.0 KB**. About 3 KB remains... **PR-6 measured:**
> K-1/K-2/K-3 base + a governor without diagnostic strings ≈ 2.7 KB (→ ≈ 9.7 KB); all four as
> built ≈ 3.6 KB (→ 10.6, over); rich parts +0.18–0.67 KB each; K-4 (0.9 KB) is priced with
> Relations V2.

This is a tighter, measured version of the ≈12.5 KB figure recorded in `ARCHEUS_V2_LATER_UI_EVIDENCE.md`
§9 LD-1 (which is a *different* budget pass, over the `v2-later` lab, not `v2-u0`) — the two are not
the same measurement and should not be conflated; both are cited here for completeness.

## A fact recovered in passing: `ARCHEUS_V2_LATER_UI_RESEARCH.md` is 1,034 lines

A `wc -l` result echoed in the same Oct-9 Codex session gives the one fact this recovery could not
get any other way for that file: `1034 ARCHEUS_V2_LATER_UI_RESEARCH.md`. No content, headings or
further detail were found for it in any of the 804 Codex rollouts searched (see RECOVERY.md §2 —
status stays **NOT RECOVERABLE**, beyond now knowing its size).
