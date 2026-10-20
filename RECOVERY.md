# Archeus V2 — post-wipe recovery report

Source of truth for this report: `D:\Archeus` git history (all refs), and Claude Code session
transcripts in `C:\Users\mab\.claude\projects\D--Archeus\*.jsonl` (797 MB, ~130 sessions). All V2
work located (docs and prototype) was done through Claude Code sessions against `D:\Claude` (cwd,
pre-rename) between 2026-10-04 and 2026-10-07.

- **`pi` sessions** (`C:\Users\mab\.pi\agent\sessions\**`, all dirs, not just `--D--Claude--`) were
  searched and contain no Write/Edit/heredoc touching an `ARCHEUS_V2`, `v2`, `prototype`,
  `PR-1..PR-6`, `jarvis` or scratch-harness path. The two `.pi` transcripts previously recovered
  from this store (T-110, T-097, referenced in `codex-recover.log`) are unrelated Core/O7 cards,
  not V2 UI work.
- **Update (2026-10-20, follow-up pass): Codex rollouts were searched.** Node 24's built-in
  `zlib.zstdDecompressSync` decompressed all 419 `.jsonl.zst` files in memory (no decompressed
  copies written to disk except transient `_codex_tmp` scratch, deleted with `shutil.rmtree`
  afterward), alongside the 385 plain `.jsonl` rollouts — 804 session files total, run at
  below-normal process priority. Search terms: `ARCHEUS_V2`, `v2-later`, `prototypes/`, `PR-1..PR-6`,
  `Direction D`/`Direction E`, `LV2-`, `jarvis` (case-insensitive).
  - **127 of 804 files matched.** Nearly all are incidental: Codex sessions reviewing unrelated
    work (PV-13, PV-20/S1 AppContainer isolation, P20 slice reviews) whose injected context
    happened to include a `git status`/`ls`/`wc -l` echo that listed V2 filenames, or a repeated
    ~4 KB boilerplate preview of `p20-design-gate.md` (154 of 290 extracted fragments were this
    exact duplicate). **Zero** Write/Edit/`apply_patch` calls to any V2 doc or prototype file were
    found anywhere — Codex only ever *read* this material, never authored or changed it.
  - **One genuine new finding:** two Oct-9/Oct-11 Codex sessions echo fragments of a **further
    revision of `docs/design/ARCHEUS_V2_UI_ARCHITECTURE.md`** — larger than the committed 762-line
    `059b47c` version, with new subsections (§D.1, §E.1, §J.4a, §K.1, §T.1, §T.2) holding real
    measured PR-1…PR-6 prototype results. This revision was never committed and no Claude Code
    transcript captured writing it (same "cloud session" gap as the final polish pass on this file
    and `ARCHEUS_V2_UI_RESEARCH.md`, §1 above). Recovered fragments — not a full reconstruction,
    paragraph/table-row quotes only — are in
    `v2-rebuild\docs\design\ARCHEUS_V2_UI_ARCHITECTURE_EXPANSION_FRAGMENTS.md`. This **revises §1's
    "EXACT" verdict for this file down to "EXACT as committed, but a later uncommitted expansion
    with the actual prototype results exists and is only partially recovered."**
  - Also recovered in passing: `ARCHEUS_V2_LATER_UI_RESEARCH.md` (§2, listed there as fully
    unrecoverable) is confirmed **1,034 lines** by an echoed `wc -l`, with no further content found
    anywhere in the Codex corpus either.

Wipe instant: 2026-10-19T12:33 UTC. Reconstruction cutoff used throughout: 2026-10-19T12:31:50Z.

## 1. What's in git (nothing lost here)

| File | Status | Last commit |
|---|---|---|
| `docs/design/ARCHEUS_V2_UI_RESEARCH.md` | **EXACT** | `059b47c` |
| `docs/design/ARCHEUS_V2_VISUAL_DIRECTION.md` | **EXACT** | `059b47c` |
| `docs/design/ARCHEUS_V2_UI_ARCHITECTURE.md` | **EXACT** | `059b47c` |
| `docs/research/2026-10-v2-ui-reference-study.md` | **EXACT** | `059b47c` |
| `docs/architecture/ARCHEUS_V2_ASSISTANT_LAYER.md` | **EXACT** | `381d729` |
| `docs/design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md` §46.3/§46.4 (the "rulebook" decisions — see §4 below) | **EXACT** | `059b47c` |

All six are on `origin` (branch `archeus-v1-rearchitecture`), confirmed present at `HEAD`. I
replayed each file's pre-commit edit history from the transcripts as a sanity check:
`ARCHEUS_V2_UI_ARCHITECTURE.md` reconstructs byte-for-byte identical to `HEAD`.
`ARCHEUS_V2_UI_RESEARCH.md` and `ARCHEUS_V2_VISUAL_DIRECTION.md` reconstruct to an **earlier draft**
— the committed version has a final polish pass (decision annotations, a Part II table of
contents, some section renumbering) applied by some means other than the Edit tool (most likely a
short Bash/sed pass, or manual editing, in the ~2 hours between the last captured Edit and the
19:46 commit). This is not a loss: `HEAD` is the later, authoritative, complete version. I did not
copy these 3 files into `v2-rebuild/` — there is nothing to recover.

**Note on the task brief:** it named `ARCHEUS_V2_ASSISTANT_LAYER.md`'s first commit as `059b47c`;
git shows it was actually `381d729` (same day, 14:17, a separate commit). `059b47c` (19:46) covers
the three UI docs + the reference study only.

## 2. Uncommitted docs — never in git, recovered from transcripts

The wipe note (`BOARD.post-wipe-recovery.md`, commit `c3fb994`) says only "the owner's uncommitted
`docs/design/ARCHEUS_V2_*` edits" were lost. The actual loss is much larger: **ten entire
documents** matching that glob were written after the 2026-10-04 commits and were never committed
at all — confirmed against a real `git status` captured verbatim inside a 2026-10-08 `pi`
transcript (`--D--Claude--\2026-10-08T10-09-42-756Z_...jsonl`, line 11, `isError: false`), which
lists all ten plus `prototypes/` as untracked. They are the continuation of the V2 UI work
(evidence → LV2-1 gate → LV2-2 plan → a UX reassessment → a competing design-reset critique → two
correction rounds → a rulebook → a reference study), built 2026-10-05 to 2026-10-07, and they
contain the project's only record of the prototype's measured results and almost all of the
owner's later decisions (Direction D, Direction E, Q12–Q18, the LV2-X.4/X.5 phone-pass approval).
Two recovery sources were used: the Edit-tool replay method from §1, and — where that undercounted
badly — a **full-file `Read` tool call** some session happened to make before editing further,
which captures the file's exact byte-for-byte state at that moment and needed no replay at all.

| File | Status | Detail |
|---|---|---|
| `ARCHEUS_V2_PRODUCT_UX_REASSESSMENT.md` | **RECONSTRUCTED** (99%) | The Edit-tool replay alone recovered only 37 KB of a 79,778-byte file (47%) — missing §9.A–C (the three design directions), all of §17 (Direction D, the owner's first review) and §18–19 (Direction E and the **decision register — every owner decision for the V2 UI**). Recovered in full instead from two full/ranged `Read` calls in session `350dece5…` (lines 82 and 93, 2026-10-06T10:56), which together capture lines 1–964 of a 964-line file (78,593 bytes recovered vs. 79,778 real — the only gap is one `Update 2026-10-06` cross-reference line added 44 minutes after that Read, pointing at the LV2-X.2 doc, which is itself fully recovered). **This is the single most important recovered file: it holds the owner's actual decisions for Directions D and E.** |
| `ARCHEUS_V2_LATER_UI_EVIDENCE.md` | **PARTIAL** | 12 of 15 Edit-tool ops applied cleanly. §10 "Accessibility results" and §11 "Performance results" are still the placeholder `*(completed below)*` in the last captured state (12:32 on 2026-10-05) — no transcript evidence they were ever filled before work moved on to the LV2-1 gate doc, so this is likely the document's true last state, not a gap in this recovery. One clarifying sentence for a contrast-defect table row could not be placed (its anchor text doesn't appear anywhere in the recovered content); exact lost text: *"The first full run that confirms the chevron fix is the design pass's (`le8`); that pass added and fixed one more (a separator at 4.31 : 1 on the strip in light)."* |
| `ARCHEUS_V2_LATER_UI_LV2_1_GATE.md` | **RECONSTRUCTED** | All 7 edits applied; full document (harness readiness check, H-1…H-8 human-test protocol, W2 pause note). |
| `ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md` | **RECONSTRUCTED** | The 2026-10-05 draft (10.8 KB) was fully superseded by a 2026-10-07 rewrite "on Direction E" (47 KB) + 2 edits — all applied. |
| `ARCHEUS_V2_LV2_X2_REFINEMENT.md` | **RECONSTRUCTED** | Full (Direction E refined as one product, Q12–Q18 opened); 462 of 462 real lines accounted for. |
| `ARCHEUS_V2_LV2_X3_CORRECTION.md` | **RECONSTRUCTED** | All 7 edits applied, including the full §9 "LV2-X.4 — the owner's decisions" and §9.7 "LV2-X.5 — the phone pass" (the owner's real-phone approval, two findings and fixes). |
| `ARCHEUS_V2_LATER_UI_RULEBOOK.md` | **RECONSTRUCTED** | No Edit-tool history exists for this file at all — recovered whole from one full `Read` in session `32eeef06…` (line 71, 2026-10-05T10:58): 156 of 156 real lines (confirmed against a `wc -l` elsewhere in the transcripts). The V2 "Do/Don't" rulebook, explicitly **not in force** pending owner approval of a later-V2 phase. |
| `ARCHEUS_V2_PRODUCT_DESIGN_RESET.md` | **PARTIAL** | A second author's independent critique of the V2 direction, reading and partly disagreeing with the UX Reassessment above. Recovered: lines 1–40 (`head -40` output) and 141–507 of 506 real lines, from two Bash/Read calls in session `350dece5…`. **Missing: lines 41–140** (the rest of §1 "Executive diagnosis", all of §2 "Product mental model", all of §3 "What Archeus should communicate on launch") — not located in any transcript; marked with an explicit gap comment in the recovered file. |
| `ARCHEUS_V2_LATER_UI_REFERENCE_STUDY.md` | **PARTIAL (stub)** | Only its first 60 lines were ever `sed`'d into a transcript (session `32eeef06…`, line 73, 2026-10-05T10:58) — the intro/methodology and §D "The current V1 SPA" (findings D-1…D-7, the seeded-Core screenshot diagnosis). The bulk of the document — the LJ/LA/LP/LM/LMo/LV reference passes it's built from (JARVIS/assistant landscape, agent-orchestration products, premium desktop, mobile, motion/accessibility, visual depth) — was never read back into any session found here and is **not recovered**; true file length unknown. |
| `ARCHEUS_V2_LATER_UI_RESEARCH.md` | **NOT RECOVERABLE** | Confirmed to have existed (named in the 2026-10-08 `git status`) but **zero bytes of content, zero headings, and no size were found in any transcript** — it was created and then apparently never read, grepped, or edited again in any session this recovery could search. (Not to be confused with the committed `ARCHEUS_V2_UI_RESEARCH.md`, §1 — this is a separate, later, uncommitted file.) |

All ten are in `v2-rebuild\docs\design\`. The `git status` also named five more untracked files
**outside** the `ARCHEUS_V2_*` glob that were therefore out of this task's scope and not pursued:
`docs/architecture/lv2-dr1-project-name-gate.md`, `lv2-dr2-remote-url-gate.md`,
`lv2-dr3-mission-repository-gate.md`, `lv2-dr4-approval-environment-gate.md`,
`lv2-dr8-verification-output-gate.md` (P21 data-contract gates, referenced by several of the
recovered V2 docs as DR-1/DR-2/DR-3/DR-4/DR-8). If these matter, the same two recovery methods
(Edit-tool replay, then full/ranged `Read` calls) apply.

## 3. Prototype files (`prototypes/v2-later/`, the PR-1…PR-6 scratch harness)

**On disk now: none.** Checked `D:\Archeus`, every `D:\archeus-*` worktree (82 of them), and every
scratchpad under `C:\Users\mab\AppData\Local\Temp\claude\*`. Not committed to git at any point
(`git log --all` for `prototypes/*` is empty). The directory only ever existed under the wiped
`D:\Claude`.

62 distinct files were created, all via Claude Code sessions `32eeef06…` (2026-10-05, the bulk of
the harness), `f9bb0b8a…`/`350dece5…`/`89680c69…` (2026-10-05–07, the `lvx/` replay harness and
LV2-2 rewrite). Full per-file list and status: `v2-rebuild\_reconstruction_report.txt`. Summary:

- **54 of 62 files: RECONSTRUCTED** (single Write, or a Write plus Edit-tool edits that all
  applied cleanly) — `README.md`, every `lab/*`, every `lvx/*` except `e2.css`/`e2.js`, every
  `results/*.md`, and most of `tools/*.py`.
- **5 files PARTIAL**: `lab/ia.js`, `lab/light.js`, `tools/light_probe.py`, `lvx/e2.css`,
  `lvx/e2.js`. These were edited heavily through **ad-hoc Bash heredocs** (`py - <<'EOF' ... s =
  s.replace(...) ... EOF`) rather than the Edit tool — a pattern this recovery does not parse. The
  recovered version of each is a real, working **earlier snapshot**, missing an unknown number of
  later Bash-applied changes. `lvx/e2.js` is the worst case: 24 of 39 tracked edits applied, and
  spot-checking found at least one entire Bash-driven rewrite (the "Running/queued" counter tile
  and zone-meta fix, found at `89680c69…jsonl:2514`, 2026-10-06T12:56:09Z) that is not reflected.
  Fully recovering these five would mean re-parsing every Bash command in the `32eeef06` (600+
  calls) and `89680c69` (119 calls) sessions for embedded `rep(a, b)`/`s.replace(a, b)` pairs and
  re-interleaving them by timestamp with the Edit-tool ops — possible, but not attempted here given
  these are throwaway lab files, not product code.
- **Screenshots/stills are gone for good.** The harness's evidence (`results/**/*.png`,
  `results/le1/env/*.png`, etc. — at least 15 referenced in the docs) were written directly to disk
  by a Playwright-driven `shoot.py`/`filmstrip.py` run via the Bash tool. No image byte ever passed
  through a transcript-visible Write call, so there is nothing to replay. **Not recoverable by any
  means** — this also means the human-test screen captures and the design-pass before/after shots
  referenced throughout `ARCHEUS_V2_LATER_UI_EVIDENCE.md` cannot be regenerated, only the harness
  code that produced them (where reconstructed) can be re-run to make new ones.

## 4. V2 decisions and corrections

All committed, in git, intact — nothing lost:

- **S-1, S-2, S-3** (V1 corrections: approval-card task table, live-map key caption, TUI Now
  header) and **V-D1…V-D5** (V2 direction: the thread as functional state light, prototype gates
  for V-D4/V-D5) are recorded in `docs/design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md`,
  §46.3 and §46.4 ("the rulebook" is this file's informal name throughout the codebase — not a
  separate file; there is no file literally named `rulebook.md`). Committed `059b47c`.
- Their consumption sites (`ARCHEUS_V2_UI_RESEARCH.md`, `ARCHEUS_V2_UI_ARCHITECTURE.md`,
  `ARCHEUS_V2_VISUAL_DIRECTION.md` §30, `p19-design-gate.md`, `testing-strategy.md`,
  `ARCHEUS_V1_REARCHITECTURE_PLAN.md`) are all committed too.
- The **later** decisions — Direction E's acceptance, Q12–Q18, the six replay-inconsistency fixes,
  and the LV2-X.4/X.5 owner sign-offs (phone pass approved, two findings fixed) — were never
  committed. They are recovered in §2 above: `ARCHEUS_V2_LV2_X2_REFINEMENT.md` and
  `ARCHEUS_V2_LV2_X3_CORRECTION.md §9`.

## Where things are

- Reconstructed docs: `C:\Users\mab\archeus-recovery\v2-rebuild\docs\design\*.md` (9 files; a 10th, `ARCHEUS_V2_LATER_UI_RESEARCH.md`, has no recoverable content beyond its 1,034-line count; an 11th, `ARCHEUS_V2_UI_ARCHITECTURE_EXPANSION_FRAGMENTS.md`, holds Codex-echoed fragments of a later uncommitted expansion of the committed `ARCHEUS_V2_UI_ARCHITECTURE.md`)
- Reconstructed prototype: `C:\Users\mab\archeus-recovery\v2-rebuild\prototypes\v2-later\**` (62 files)
- Per-file machine-readable status (path, RECONSTRUCTED/PARTIAL, edits applied/failed, timestamps):
  `C:\Users\mab\archeus-recovery\v2-rebuild\_reconstruction_report.txt`
- This file: `C:\Users\mab\archeus-recovery\v2-rebuild\RECOVERY.md`

Nothing in `D:\Archeus` or any other repo was modified, committed, or deleted in the course of this
recovery; it is forensic/read-only, written only under `C:\Users\mab\archeus-recovery\v2-rebuild\`.
