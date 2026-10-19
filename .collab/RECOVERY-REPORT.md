# .collab Rebuild Report

Reconstruction of `D:\Claude\.collab\` as it stood just before the wipe at 2026-10-19T12:31:50Z, staged at `C:\Users\mab\archeus-recovery\collab-rebuild\`.

## Summary

- Total files accounted for: **178**
- EXACT: **143**
- RECONSTRUCTED: **18**
- PARTIAL: **5**
- MISSING: **12**

## BOARD.md (pass 2: anchor-and-replay)

- Status: **PARTIAL** (improved from pass 1) — 549415 chars, 1728 lines.
- Previous linear replay-from-start attempt kept as `BOARD.md.pass1` (668 lines); a corrected, deduplicated re-run of that same method (see Method) is kept as `BOARD.md.pass1b` and used only as the trailing-section/preamble source below.
- **Bug found and fixed since pass 1**: `C:\Users\mab\.claude\projects\D--Archeus\95e3252a-...pre-restart-D--Claude.jsonl.bak` duplicates almost all of the live session's own `.jsonl` (it is a pre-restart snapshot of the same session, not independent history). Pass 1 processed both and double-applied ~20 late heredoc appends/edits. Pass 2 (and the regenerated `pass1b`) filter it out via `claude_events.dedup.jsonl`.
- Method: for every `### T-NNN` card, the newest-before-cutoff anchor among (a) a card-boundary-safe slice of a Read snapshot and (b) a Codex reviewer-prompt's embedded `The card:\n\n<block>` (review.py/batch_review.py/analysis_review.py/aimed_codex.py all copy the live card verbatim into the prompt) is taken as that card's ground truth at that timestamp. Cards assembled in numeric order; trailing non-card `## ` sections and the preamble come from `BOARD.md.pass1b`. Every subsequent Write/Edit/Bash-heredoc/Python-script mutation (Claude) and `edit` (Qwen/pi) is then replayed in timestamp order, **skipped** when every card it names already has an anchor at or after the mutation's own timestamp (already reflected), and otherwise applied the same sandboxed way as pass 1.
- Anchors: 100 of 120 known cards have a ground-truth anchor; 20 have none in any source (listed MISSING below).
- Replay-after-anchor outcome: 74 OK, 75 skipped as already superseded by a later anchor, 4 skipped non-mutating diagnostics, 3 FAILED-ORIGINALLY (the paired tool_result for that same event shows it failed live too — not a reconstruction gap), 80 REMAINING-GAP (failed here but the original tool_result shows success or is unavailable — a real reconstruction shortfall, logged per-event in `board_replay_v2_log.tsv`).
- Qwen/pi BOARD.md edits: all 20 extracted and merged into the single replay timeline above (no longer a separate unmerged gap).
- REMAINING-GAP breakdown: 59 of 80 are cases where the original tool_result shows the live script succeeded but it raised here (almost all exit-1 Python errors) — meaning the anchor text we re-seeded that card/section with differs just enough from what the original script expected (e.g. it expects an intermediate wording its own *preceding* mutation would have produced, but that preceding mutation is itself a different REMAINING-GAP) for its `s.index(...)`/`s.count(...)` match to still hold; 11 fail with no exit code (e.g. the script's own internal assertion about what it would write didn't hold against our content); 10 have no recoverable tool_result at all (`orig=unknown`). None of these lose information outright — the untouched prior anchor text for that card stays in place — they just mean the specific one or few fields that mutation intended to update (typically `status:`/`review:`/`commits:`/`notes:`) were not updated to their truest final wording for 51 cards. Full per-event detail: `board_replay_v2_log.tsv`.
- Target length check: the 2026-10-19T10:19:57Z Read snapshot (lines 1370-1420, 52 lines returned off a limit of 120 -> true EOF) is the newest full-fidelity evidence of the pre-cutoff length; it anchors T-108/T-109/T-111 directly. The board above still falls short of the ~1,420-line target mainly because of the 20 MISSING cards (no anchor at all) and the REMAINING-GAP mutations below.

### Per-card status

| card | source of final text | anchor/last event (UTC) | gaps |
|---|---|---|---|
| T-001 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | anchor only, no later mutation |
| T-002 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | anchor only, no later mutation |
| T-003 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | anchor only, no later mutation |
| T-004 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +11 applied, 8 REMAINING-GAP mutation(s) after anchor |
| T-005 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +1 applied |
| T-006 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | anchor only, no later mutation |
| T-007 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | 1 REMAINING-GAP mutation(s) after anchor |
| T-008 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +4 applied, 5 REMAINING-GAP mutation(s) after anchor |
| T-009 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +1 applied |
| T-010 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +2 applied, 4 REMAINING-GAP mutation(s) after anchor |
| T-011 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +2 applied, 2 REMAINING-GAP mutation(s) after anchor |
| T-012 | codex-prompt | 2026-10-12T12:04:58.323Z | +2 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-013 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | anchor only, no later mutation |
| T-014 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +1 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-015 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +3 applied, 3 REMAINING-GAP mutation(s) after anchor |
| T-016 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +2 applied, 3 REMAINING-GAP mutation(s) after anchor |
| T-017 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +2 applied, 5 REMAINING-GAP mutation(s) after anchor |
| T-018 | read-snapshot@offset=None | 2026-10-12T12:02:03.951Z | +2 applied, 3 REMAINING-GAP mutation(s) after anchor |
| T-019 | codex-prompt | 2026-10-12T12:23:15.962Z | 3 REMAINING-GAP mutation(s) after anchor |
| T-020 | codex-prompt | 2026-10-12T12:25:11.940Z | 2 REMAINING-GAP mutation(s) after anchor |
| T-021 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-022 | codex-prompt | 2026-10-12T13:37:45.691Z | +1 applied |
| T-023 | codex-prompt | 2026-10-12T13:36:12.650Z | +1 applied, 2 REMAINING-GAP mutation(s) after anchor |
| T-024 | codex-prompt | 2026-10-12T13:05:25.442Z | +1 applied |
| T-025 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-026 | codex-prompt | 2026-10-12T15:23:52.516Z | 1 REMAINING-GAP mutation(s) after anchor |
| T-027 | codex-prompt | 2026-10-12T14:06:15.789Z | 4 REMAINING-GAP mutation(s) after anchor |
| T-028 | codex-prompt | 2026-10-12T14:30:06.202Z | +1 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-029 | codex-prompt | 2026-10-12T14:51:21.869Z | +1 applied |
| T-030 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-031 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-032 | codex-prompt | 2026-10-12T15:42:11.865Z | 2 REMAINING-GAP mutation(s) after anchor |
| T-033 | codex-prompt | 2026-10-13T09:16:37.719Z | +1 applied |
| T-034 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-035 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-036 | codex-prompt | 2026-10-13T10:20:03.169Z | +1 applied, 4 REMAINING-GAP mutation(s) after anchor |
| T-037 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-038 | codex-prompt | 2026-10-13T11:43:13.266Z | +3 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-039 | codex-prompt | 2026-10-13T12:20:42.278Z | +5 applied |
| T-040 | codex-prompt | 2026-10-13T13:41:30.672Z | 3 REMAINING-GAP mutation(s) after anchor |
| T-041 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-042 | codex-prompt | 2026-10-13T15:08:24.050Z | +1 applied, 2 REMAINING-GAP mutation(s) after anchor |
| T-043 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-044 | codex-prompt | 2026-10-13T15:02:18.438Z | +2 applied |
| T-045 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-046 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-047 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-048 | codex-prompt | 2026-10-13T19:31:43.465Z | +2 applied, 6 REMAINING-GAP mutation(s) after anchor |
| T-049 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-050 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-051 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-052 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-053 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-054 | read-snapshot@offset=638 | 2026-10-14T14:46:11.302Z | 4 REMAINING-GAP mutation(s) after anchor |
| T-055 | read-snapshot@offset=638 | 2026-10-14T14:46:11.302Z | +1 applied |
| T-056 | read-snapshot@offset=638 | 2026-10-14T14:46:11.302Z | +1 applied |
| T-057 | read-snapshot@offset=638 | 2026-10-14T14:46:11.302Z | 1 REMAINING-GAP mutation(s) after anchor |
| T-058 | read-snapshot@offset=638 | 2026-10-14T14:46:11.302Z | 1 REMAINING-GAP mutation(s) after anchor |
| T-059 | read-snapshot@offset=638 | 2026-10-14T14:46:11.302Z | 1 REMAINING-GAP mutation(s) after anchor |
| T-060 | read-snapshot@offset=638 | 2026-10-14T14:46:11.302Z | 1 REMAINING-GAP mutation(s) after anchor |
| T-061 | codex-prompt | 2026-10-14T21:58:02.359Z | +2 applied |
| T-062 | codex-prompt | 2026-10-14T21:58:36.792Z | +3 applied |
| T-063 | codex-prompt | 2026-10-14T14:29:55.136Z | +2 applied |
| T-064 | codex-prompt | 2026-10-14T22:06:47.947Z | +1 applied, 2 REMAINING-GAP mutation(s) after anchor |
| T-066 | codex-prompt | 2026-10-14T21:56:19.580Z | +2 applied, 4 REMAINING-GAP mutation(s) after anchor |
| T-067 | codex-prompt | 2026-10-14T21:57:14.445Z | +3 applied |
| T-068 | codex-prompt | 2026-10-14T22:06:47.947Z | +2 applied, 2 REMAINING-GAP mutation(s) after anchor |
| T-069 | codex-prompt | 2026-10-14T14:36:38.027Z | +2 applied, 2 REMAINING-GAP mutation(s) after anchor |
| T-070 | codex-prompt | 2026-10-14T09:55:01.231Z | 1 REMAINING-GAP mutation(s) after anchor |
| T-071 | codex-prompt | 2026-10-14T22:42:36.127Z | +5 applied, 4 REMAINING-GAP mutation(s) after anchor |
| T-072 | codex-prompt | 2026-10-14T22:01:35.946Z | +8 applied, 1 REMAINING-GAP mutation(s) after anchor, 1 confirmed originally-failed (skipped, not a gap) |
| T-073 | read-snapshot@offset=863 | 2026-10-14T14:46:12.434Z | +1 applied |
| T-074 | read-snapshot@offset=863 | 2026-10-14T14:46:12.434Z | anchor only, no later mutation |
| T-075 | read-snapshot@offset=863 | 2026-10-14T14:46:12.434Z | +1 applied |
| T-076 | read-snapshot@offset=863 | 2026-10-14T14:46:12.434Z | anchor only, no later mutation |
| T-077 | read-snapshot@offset=863 | 2026-10-14T14:46:12.434Z | +1 applied |
| T-078 | read-snapshot@offset=915 | 2026-10-14T14:46:14.374Z | anchor only, no later mutation |
| T-079 | read-snapshot@offset=915 | 2026-10-14T14:46:14.374Z | +1 applied |
| T-080 | codex-prompt | 2026-10-16T11:20:00.306Z | +6 applied, 3 REMAINING-GAP mutation(s) after anchor |
| T-081 | read-snapshot@offset=936 | 2026-10-14T22:32:50.409Z | +1 applied, 2 REMAINING-GAP mutation(s) after anchor |
| T-082 | read-snapshot@offset=936 | 2026-10-14T22:32:50.409Z | anchor only, no later mutation |
| T-083 | codex-prompt | 2026-10-16T11:20:00.306Z | +5 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-084 | read-snapshot@offset=915 | 2026-10-14T14:46:14.374Z | +1 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-085 | read-snapshot@offset=915 | 2026-10-14T14:46:14.374Z | anchor only, no later mutation |
| T-086 | codex-prompt | 2026-10-14T21:59:43.109Z | +2 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-087 | read-snapshot@offset=915 | 2026-10-14T14:46:14.374Z | +1 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-088 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-089 | codex-prompt | 2026-10-16T11:20:00.306Z | +5 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-090 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-091 | MISSING | - | no card-block anchor in any Read snapshot, Codex reviewer prompt, or the pass1/pass1b sequential replay |
| T-092 | codex-prompt | 2026-10-16T11:20:00.306Z | +6 applied, 2 REMAINING-GAP mutation(s) after anchor |
| T-093 | read-snapshot@offset=1113 | 2026-10-14T22:32:50.729Z | +5 applied, 2 REMAINING-GAP mutation(s) after anchor, 1 confirmed originally-failed (skipped, not a gap) |
| T-094 | codex-prompt | 2026-10-16T12:08:49.579Z | +9 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-095 | read-snapshot@offset=1139 | 2026-10-16T11:13:06.517Z | +1 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-096 | read-snapshot@offset=1139 | 2026-10-16T11:13:06.517Z | +6 applied, 1 confirmed originally-failed (skipped, not a gap) |
| T-097 | codex-prompt | 2026-10-19T08:51:30.241Z | +7 applied |
| T-098 | read-snapshot@offset=1139 | 2026-10-16T11:13:06.517Z | +10 applied |
| T-099 | replay(pass1)-fallback | - | +10 applied, 1 REMAINING-GAP mutation(s) after anchor, 1 confirmed originally-failed (skipped, not a gap) |
| T-100 | codex-prompt | 2026-10-16T11:18:21.915Z | +7 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-101 | codex-prompt | 2026-10-16T11:19:35.523Z | +6 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-102 | replay(pass1)-fallback | - | +9 applied, 3 REMAINING-GAP mutation(s) after anchor |
| T-103 | codex-prompt | 2026-10-16T12:14:02.268Z | +15 applied |
| T-104 | read-snapshot@offset=1256 | 2026-10-16T11:13:09.732Z | +1 applied |
| T-105 | read-snapshot@offset=1256 | 2026-10-16T11:13:09.732Z | +7 applied, 1 REMAINING-GAP mutation(s) after anchor |
| T-106 | read-snapshot@offset=1256 | 2026-10-16T11:13:09.732Z | +4 applied |
| T-107 | read-snapshot@offset=1256 | 2026-10-16T11:13:09.732Z | +7 applied |
| T-108 | read-snapshot@offset=1370 | 2026-10-19T10:19:57.733Z | +3 applied |
| T-109 | read-snapshot@offset=1370 | 2026-10-19T10:19:57.733Z | +4 applied |
| T-110 | codex-prompt | 2026-10-19T11:34:33.128Z | +3 applied |
| T-111 | read-snapshot@offset=1370 | 2026-10-19T10:19:57.733Z | +2 applied |
| T-112 | replay(pass1)-fallback | - | +2 applied |
| T-113 | replay(pass1)-fallback | - | +2 applied |
| T-114 | codex-prompt | 2026-10-19T11:33:21.311Z | +1 applied |
| T-115 | replay(pass1)-fallback | - | +1 applied |
| T-116 | replay(pass1)-fallback | - | +2 applied |
| T-117 | codex-prompt | 2026-10-19T11:19:52.797Z | +1 applied |
| T-118 | replay(pass1)-fallback | - | +1 applied |
| T-119 | replay(pass1)-fallback | - | +1 applied |
| T-120 | replay(pass1)-fallback | - | +1 applied |
| T-121 | replay(pass1)-fallback | - | +1 applied |

## Per-file status

| path | status | last event (UTC) | source |
|---|---|---|---|
| `BOARD.md` | PARTIAL | 2026-10-19T10:19:57.733Z (last confirmed read snapshot) | Claude Code Write/Edit + Bash heredoc/python-script replay (see BOARD.md section) |
| `QWEN-DONE-T-097.md` | EXACT | 2026-10-19T11:40:17.096Z | Qwen (pi) session (write/edit) |
| `QWEN-DONE-T-110.md` | EXACT | 2026-10-19T11:32:03.276Z | Qwen (pi) session (write/edit) |
| `QWEN-DONE-T-114.md` | EXACT | 2026-10-19T11:18:46.112Z | Qwen (pi) session (write/edit) |
| `README.md` | EXACT | 2026-10-12T09:09:42.933Z | Claude Code transcripts (Write/Edit/Read) |
| `STATUS-2026-10-12.md` | RECONSTRUCTED | 2026-10-12T11:37:48.079Z | Qwen (pi) session (write/edit) |
| `T-004-evidence.md` | PARTIAL | 2026-10-12T10:36:09.470Z | Qwen (pi) session (write/edit) |
| `T-010-creator-access.md` | EXACT | 2026-10-12T09:58:08.383Z | Claude Code transcripts (Write/Edit/Read) |
| `T-015-gap-b-matrix.md` | EXACT | 2026-10-12T12:08:58.634Z | Claude Code transcripts (Write/Edit/Read) |
| `T-016-private-workspace-plan.md` | EXACT | 2026-10-12T12:09:48.297Z | Claude Code transcripts (Write/Edit/Read) |
| `T-017-private-config-plan.md` | RECONSTRUCTED | 2026-10-12T12:09:07.398Z | Claude Code transcripts (Write/Edit/Read) |
| `T-018-arrival-policy.md` | RECONSTRUCTED | 2026-10-12T12:06:22.286Z | Claude Code transcripts (Write/Edit/Read) |
| `T-021-isolation-decision-contract.md` | EXACT | 2026-10-12T12:24:54.160Z | Claude Code transcripts (Write/Edit/Read) |
| `T-025-limit-report-authority.md` | PARTIAL | 2026-10-12T13:09:43.447Z | Claude Code transcripts (Write/Edit/Read) |
| `T-030-seed-import-contract.md` | EXACT | 2026-10-12T14:56:48.568Z | Claude Code transcripts (Write/Edit/Read) |
| `T-031-isolated-environment-contract.md` | EXACT | 2026-10-12T15:28:18.756Z | Claude Code transcripts (Write/Edit/Read) |
| `T-034-staged-runtime-contract.md` | RECONSTRUCTED | 2026-10-13T08:58:22.728Z | Claude Code transcripts (Write/Edit/Read) |
| `T-035-isolated-provenance-contract.md` | EXACT | 2026-10-13T08:58:10.773Z | Claude Code transcripts (Write/Edit/Read) |
| `T-037-lost-isolation-record-contract.md` | EXACT | 2026-10-13T10:07:55.189Z | Claude Code transcripts (Write/Edit/Read) |
| `T-041-verification-guard-contract.md` | EXACT | 2026-10-13T13:10:01.121Z | Claude Code transcripts (Write/Edit/Read) |
| `T-043-isolated-facts-contract.md` | RECONSTRUCTED | 2026-10-13T14:07:21.072Z | Claude Code transcripts (Write/Edit/Read) |
| `T-045-regression-report.md` | EXACT | 2026-10-13T15:33:30.135Z | Claude Code transcripts (Write/Edit/Read) |
| `T-046-core-git-store-contract.md` | EXACT | 2026-10-13T15:20:16.207Z | Claude Code transcripts (Write/Edit/Read) |
| `T-047-regression-report.md` | EXACT | 2026-10-13T18:29:01.822Z | Claude Code transcripts (Write/Edit/Read) |
| `T-049-seed-contract.md` | RECONSTRUCTED | 2026-10-13T18:21:09.342Z | Claude Code transcripts (Write/Edit/Read) |
| `T-050-provider-broker-contract.md` | EXACT | 2026-10-13T19:43:06.150Z | Claude Code transcripts (Write/Edit/Read) |
| `T-051-import-contract.md` | EXACT | 2026-10-13T19:41:43.320Z | Claude Code transcripts (Write/Edit/Read) |
| `T-052-creator-authority-decision.md` | RECONSTRUCTED | 2026-10-13T19:44:51.243Z | Qwen (pi) session (write/edit) |
| `T-053-origin-transport-contract.md` | EXACT | 2026-10-13T19:43:21.539Z | Claude Code transcripts (Write/Edit/Read) |
| `T-054-confined-verifier-contract.md` | EXACT | 2026-10-13T19:42:50.159Z | Claude Code transcripts (Write/Edit/Read) |
| `T-071-storage-namespace-options.md` | PARTIAL | 2026-10-14T10:01:57.596Z | Qwen (pi) session (write/edit) |
| `T-072-integration-inventory.md` | EXACT | 2026-10-14T10:20:51.566Z | Claude Code transcripts (Write/Edit/Read) |
| `T-072-prereview.md` | EXACT | 2026-10-14T13:27:41.886Z | Claude Code transcripts (Write/Edit/Read) |
| `T-072-regression-report.md` | EXACT | 2026-10-14T12:12:21.367Z | Claude Code transcripts (Write/Edit/Read) |
| `T-075-k03-flake.md` | EXACT | 2026-10-14T10:48:40.847Z | Claude Code transcripts (Write/Edit/Read) |
| `T-077-long-home.md` | RECONSTRUCTED | 2026-10-14T10:56:50.901Z | Claude Code transcripts (Write/Edit/Read) |
| `T-079-worktree-layout.md` | EXACT | 2026-10-14T11:00:52.745Z | Claude Code transcripts (Write/Edit/Read) |
| `T-081-own-calls-tools.md` | EXACT | 2026-10-14T11:53:21.301Z | Claude Code transcripts (Write/Edit/Read) |
| `T-087-and-native-auth.md` | EXACT | 2026-10-14T13:22:59.685Z | Claude Code transcripts (Write/Edit/Read) |
| `T-097-login-probe-reads.md` | PARTIAL | 2026-10-14T22:41:14.393Z | Qwen (pi) session (write/edit) |
| `T-100-mechanism-decision.md` | RECONSTRUCTED | 2026-10-14T22:54:11.073Z | Qwen (pi) session (write/edit) |
| `T-110-o7-breaker.md` | RECONSTRUCTED | 2026-10-19T11:29:41.376Z | Qwen (pi) session (write/edit) |
| `T-119-cwrite-scope.md` | EXACT | 2026-10-19T11:47:07.823Z | Claude Code transcripts (Write/Edit/Read) |
| `analysis_review.py` | EXACT | 2026-10-14T22:16:11.108Z | Claude Code Bash (python transform of the scratchpad source, replayed verbatim) |
| `batch_review.py` | EXACT | 2026-10-14T22:20:32.350Z | Claude Code Bash (sed transform of the scratchpad source, replayed verbatim) |
| `review.py` | RECONSTRUCTED | 2026-10-12T09:10:08.747Z | Claude Code transcripts (Write/Edit/Read) |
| `review.py` | EXACT | 2026-10-12T09:10:08.747Z | Claude Code Write tool (direct) |
| `reviews/T-012-8997446.md` | EXACT | 2026-10-12T12:06:23.715Z | Codex session (review) |
| `reviews/T-019-b460fc5.md` | EXACT | 2026-10-12T12:24:13.843Z | Codex session (review) |
| `reviews/T-020-ad27e52.md` | EXACT | 2026-10-12T12:26:04.609Z | Codex session (review) |
| `reviews/T-022-af80a16.md` | EXACT | 2026-10-12T12:47:53.975Z | Codex session (review) |
| `reviews/T-022-f6d843d.md` | EXACT | 2026-10-12T13:39:03.740Z | Codex session (review) |
| `reviews/T-023-b3bc2c9.md` | EXACT | 2026-10-12T13:37:41.506Z | Codex session (review) |
| `reviews/T-024-9c80cb2.md` | EXACT | 2026-10-12T13:06:26.169Z | Codex session (review) |
| `reviews/T-024-efc31cc.md` | EXACT | 2026-10-12T12:49:11.196Z | Codex session (review) |
| `reviews/T-026-f72d48e.md` | EXACT | 2026-10-12T15:25:19.912Z | Codex session (review) |
| `reviews/T-027-ce7df6e.md` | EXACT | 2026-10-12T14:07:13.602Z | Codex session (review) |
| `reviews/T-028-0c535e7.md` | EXACT | 2026-10-12T14:31:06.295Z | Codex session (review) |
| `reviews/T-029-38497a2.md` | EXACT | 2026-10-12T14:52:02.522Z | Codex session (review) |
| `reviews/T-030-analysis.r3.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-032-7675095.md` | EXACT | 2026-10-12T15:43:25.811Z | Codex session (review) |
| `reviews/T-033-894c0bd.md` | EXACT | 2026-10-13T09:17:35.887Z | Codex session (review) |
| `reviews/T-036-cea27bb.md` | EXACT | 2026-10-13T10:20:47.910Z | Codex session (review) |
| `reviews/T-038-648d039.md` | EXACT | 2026-10-13T11:44:07.360Z | Codex session (review) |
| `reviews/T-038-dc7c437.md` | EXACT | 2026-10-13T11:39:56.188Z | Codex session (review) |
| `reviews/T-039-3cccc0e.md` | EXACT | 2026-10-13T12:02:04.989Z | Codex session (review) |
| `reviews/T-039-60fd712.md` | EXACT | 2026-10-13T12:08:00.983Z | Codex session (review) |
| `reviews/T-039-6443703.md` | EXACT | 2026-10-13T12:14:50.216Z | Codex session (review) |
| `reviews/T-039-90405a2.md` | EXACT | 2026-10-13T11:56:57.869Z | Codex session (review) |
| `reviews/T-039-d2ecac4.md` | EXACT | 2026-10-13T12:21:47.826Z | Codex session (review) |
| `reviews/T-040-2361aa9.md` | EXACT | 2026-10-13T13:20:06.704Z | Codex session (review) |
| `reviews/T-040-a16d3c9.md` | EXACT | 2026-10-13T13:42:33.790Z | Codex session (review) |
| `reviews/T-042-9e4443f.md` | EXACT | 2026-10-13T15:10:10.223Z | Codex session (review) |
| `reviews/T-042-c9e9e28.md` | EXACT | 2026-10-13T14:41:57.006Z | Codex session (review) |
| `reviews/T-044-57a87fd.md` | EXACT | 2026-10-13T15:03:45.414Z | Codex session (review) |
| `reviews/T-046-analysis.md` | EXACT | 2026-10-13T15:38:21.302Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-046-analysis.r2.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-048-0c1b49e.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-048-0c1b49e.md` | EXACT | 2026-10-13T19:35:50.501Z | Codex session (review) |
| `reviews/T-048-33b639f.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-048-33b639f.md` | EXACT | 2026-10-13T19:12:27.144Z | Codex session (review) |
| `reviews/T-048-4d1a91b.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-048-4d1a91b.md` | EXACT | 2026-10-13T19:01:33.107Z | Codex session (review) |
| `reviews/T-048-5dfac53.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-048-5dfac53.md` | EXACT | 2026-10-13T18:32:18.083Z | Codex session (review) |
| `reviews/T-048-c06113f.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-048-c06113f.md` | EXACT | 2026-10-13T18:43:40.482Z | Codex session (review) |
| `reviews/T-048-c3f1069.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-048-c3f1069.md` | EXACT | 2026-10-13T18:53:39.211Z | Codex session (review) |
| `reviews/T-049-analysis.md` | EXACT | 2026-10-13T18:25:40.600Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-050-analysis.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-051-analysis.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-053-analysis.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-054-analysis.md` | MISSING |  | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-055-faecc6a.md` | EXACT | 2026-10-14T09:58:26.951Z | Codex session (review) |
| `reviews/T-060-aaddefd.md` | EXACT | 2026-10-14T14:26:38.401Z | Codex session (review) |
| `reviews/T-061-128679a.md` | EXACT | 2026-10-14T21:58:24.886Z | Codex session (review) |
| `reviews/T-061-97797de.md` | EXACT | 2026-10-14T14:28:01.699Z | Codex session (review) |
| `reviews/T-062-6203e8d.md` | EXACT | 2026-10-14T14:29:51.390Z | Codex session (review) |
| `reviews/T-062-cab3843.md` | EXACT | 2026-10-14T21:59:13.448Z | Codex session (review) |
| `reviews/T-063-6ff342b.md` | EXACT | 2026-10-14T14:30:39.986Z | Codex session (review) |
| `reviews/T-064-84969bf.md` | EXACT | 2026-10-14T14:31:54.771Z | Codex session (review) |
| `reviews/T-064-9fdb897.md` | EXACT | 2026-10-14T22:07:12.778Z | Codex session (batch) |
| `reviews/T-066-82b53a7.md` | EXACT | 2026-10-14T14:34:03.267Z | Codex session (review) |
| `reviews/T-066-e472f5e.md` | EXACT | 2026-10-14T21:56:51.383Z | Codex session (review) |
| `reviews/T-067-a6c3188.md` | EXACT | 2026-10-14T21:57:49.904Z | Codex session (review) |
| `reviews/T-067-e5f77aa.md` | EXACT | 2026-10-14T14:35:50.186Z | Codex session (review) |
| `reviews/T-068-a645d2d.md` | EXACT | 2026-10-14T14:36:33.114Z | Codex session (review) |
| `reviews/T-068-cc46cb2.md` | EXACT | 2026-10-14T22:07:12.778Z | Codex session (batch) |
| `reviews/T-069-cece71d.md` | EXACT | 2026-10-14T14:37:51.563Z | Codex session (review) |
| `reviews/T-070-606d5b6.md` | EXACT | 2026-10-14T09:56:20.365Z | Codex session (review) |
| `reviews/T-071-analysis.md` | EXACT | 2026-10-14T22:15:43.631Z | Codex session (analysis) |
| `reviews/T-071-analysis.r2.md` | EXACT | 2026-10-14T22:32:35.164Z | Codex session (analysis) |
| `reviews/T-071-analysis.r3.md` | EXACT | 2026-10-14T22:43:29.625Z | Codex session (analysis) |
| `reviews/T-072-7685559.md` | EXACT | 2026-10-14T14:39:53.561Z | Codex session (review) |
| `reviews/T-072-e853d68.md` | EXACT | 2026-10-14T22:03:08.791Z | Codex session (review) |
| `reviews/T-073-3d98f84.claude.md` | EXACT | 2026-10-14T14:56:14.869Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-073-3d98f84.md` | EXACT | 2026-10-14T14:40:37.288Z | Codex session (review) |
| `reviews/T-074-a430301.claude.md` | EXACT | 2026-10-14T14:56:26.626Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-076-24b1322.claude.md` | EXACT | 2026-10-14T14:56:53.809Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-078-bf56850.claude.md` | EXACT | 2026-10-14T14:52:35.708Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-080-10ea156.md` | EXACT | 2026-10-14T22:05:38.148Z | Codex session (batch) |
| `reviews/T-080-2ff46ce.md` | EXACT | 2026-10-16T11:20:30.605Z | Codex session (aimed_batch) |
| `reviews/T-081-81b831e.claude.md` | EXACT | 2026-10-14T14:52:58.364Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-082-5c355eb.claude.md` | EXACT | 2026-10-14T14:57:18.687Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-083-015a351.md` | EXACT | 2026-10-14T22:05:38.148Z | Codex session (batch) |
| `reviews/T-083-4eb7ca5.md` | EXACT | 2026-10-16T11:20:30.605Z | Codex session (aimed_batch) |
| `reviews/T-085-e7a9c31.claude.md` | EXACT | 2026-10-14T14:53:21.217Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-086-08b899c.md` | EXACT | 2026-10-14T22:00:36.587Z | Codex session (review) |
| `reviews/T-087-189b209.claude.md` | EXACT | 2026-10-14T14:53:42.369Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-088-b942945.claude.md` | EXACT | 2026-10-14T14:50:00.999Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-089-02007f1.md` | EXACT | 2026-10-16T11:20:30.605Z | Codex session (aimed_batch) |
| `reviews/T-089-3bdc485.md` | EXACT | 2026-10-14T22:05:38.148Z | Codex session (batch) |
| `reviews/T-090-8a34125.claude.md` | EXACT | 2026-10-14T14:50:33.668Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-091-b26225a.claude.md` | EXACT | 2026-10-14T22:09:24.708Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-092-2ff46ce.claude.md` | EXACT | 2026-10-14T22:41:12.612Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-092-44cbb47.md` | EXACT | 2026-10-16T11:20:30.605Z | Codex session (aimed_batch) |
| `reviews/T-093-853f63f.claude.md` | RECONSTRUCTED | 2026-10-14T22:44:54.946Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-094-2f93182.claude.md` | RECONSTRUCTED | 2026-10-16T11:32:15.595Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-094-36160ba.claude.md` | RECONSTRUCTED | 2026-10-15T00:05:11.771Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-094-d80a9b4.md` | EXACT | 2026-10-16T12:09:41.677Z | Codex session (aimed) |
| `reviews/T-095-82c7e2d.claude.md` | RECONSTRUCTED | 2026-10-14T23:25:45.176Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-096-9abca6c.claude.md` | EXACT | 2026-10-15T00:30:23.534Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-096-e7141c1.claude.md` | EXACT | 2026-10-15T01:04:02.683Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-097-analysis.md` | EXACT | 2026-10-16T11:19:31.753Z | Codex session (aimed) |
| `reviews/T-097-analysis.r2.md` | EXACT | 2026-10-19T08:52:00.307Z | Codex session (aimed) |
| `reviews/T-098-d6877a2.claude.md` | EXACT | 2026-10-15T00:39:17.790Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-098-e0880a2.claude.md` | RECONSTRUCTED | 2026-10-16T11:40:23.825Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-099-56e4c8b.claude.md` | EXACT | 2026-10-14T23:09:36.156Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-099-b2dbf4c.claude.md` | EXACT | 2026-10-14T23:32:48.615Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-100-analysis.md` | EXACT | 2026-10-16T11:18:51.108Z | Codex session (aimed) |
| `reviews/T-101-ee6dabb.claude.md` | EXACT | 2026-10-14T23:45:08.591Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-101-ee6dabb.md` | EXACT | 2026-10-16T11:19:54.101Z | Codex session (aimed) |
| `reviews/T-101-f357434.claude.md` | EXACT | 2026-10-14T23:33:17.809Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-102-0fb5daa.claude.md` | EXACT | 2026-10-15T00:48:14.300Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-102-438d5ca.claude.md` | EXACT | 2026-10-15T00:25:36.236Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-102-b73f875.claude.md` | EXACT | 2026-10-15T00:54:44.495Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-102-c91d4f1.claude.md` | EXACT | 2026-10-14T23:57:54.804Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-103-2b6e852.md` | EXACT | 2026-10-16T12:14:23.444Z | Codex session (aimed) |
| `reviews/T-103-7c92b10.claude.md` | EXACT | 2026-10-15T00:13:47.891Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-103-cbc0ee6.md` | EXACT | 2026-10-16T12:12:56.212Z | Codex session (aimed) |
| `reviews/T-103-ec90967.claude.md` | RECONSTRUCTED | 2026-10-16T11:34:55.387Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-103-ec90967.md` | EXACT | 2026-10-16T11:36:52.462Z | Codex session (aimed) |
| `reviews/T-104-64cf479.claude.md` | EXACT | 2026-10-15T00:02:55.259Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-105-9f057fc.claude.md` | EXACT | 2026-10-15T00:26:03.387Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-105-fadadd7.claude.md` | EXACT | 2026-10-15T00:47:57.112Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-107-1b87969.claude.md` | EXACT | 2026-10-16T11:46:23.529Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-107-e90217a.claude.md` | RECONSTRUCTED | 2026-10-15T01:02:48.794Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-108-ca123e5.claude.md` | EXACT | 2026-10-19T10:02:47.562Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-108-ca123e5.md` | EXACT | 2026-10-19T09:58:03.073Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-108-ca123e5.md` | EXACT | 2026-10-19T09:39:26.455Z | Codex session (aimed) |
| `reviews/T-109-cddec29.claude.md` | EXACT | 2026-10-19T10:29:53.444Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-110-analysis.md` | EXACT | 2026-10-19T11:36:49.521Z | Codex session (aimed) |
| `reviews/T-113-ee9f933.claude.md` | EXACT | 2026-10-19T11:16:58.686Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-114-c8f5bd5.md` | EXACT | 2026-10-19T11:34:10.815Z | Codex session (aimed) |
| `reviews/T-116-bb55cd9.claude.md` | EXACT | 2026-10-19T11:26:44.109Z | Claude Code transcripts (Write/Edit/Read) |
| `reviews/T-117-474815f.md` | EXACT | 2026-10-19T11:14:52.342Z | Codex session (aimed) |
| `reviews/T-117-b9ff906.md` | EXACT | 2026-10-19T11:20:25.024Z | Codex session (aimed) |

## Not recovered / explicitly known-incomplete

- `BOARD.md` body (see above) — PARTIAL, 1,727 lines staged (pass 2, anchor-and-replay) against an estimated ~1,420+ pre-cutoff lines; 20 cards (`T-021`, `T-025`, `T-030`, `T-031`, `T-034`, `T-035`, `T-037`, `T-041`, `T-043`, `T-045`, `T-046`, `T-047`, `T-049`, `T-050`, `T-051`, `T-052`, `T-053`, `T-088`, `T-090`, `T-091`) have no card-block anchor in any source at all and are entirely absent from the staged file; 51 further cards have an anchor but at least one later mutation that still would not re-apply (REMAINING-GAP, logged per-card in `card_gap_summary.tsv` and per-event in `board_replay_v2_log.tsv`).
- `QWEN-CARD-T-097.md`, `QWEN-CARD-T-110.md` — only Qwen `edit` calls were found (no `write` that created them); the base content was never captured by any source. MISSING.
- `QWEN-NEXT.md` and any further `STATUS-2026-10-1x.md` beyond `STATUS-2026-10-12.md` — no Write/Read/edit evidence found in the sources scanned. MISSING.
- Any `.collab` file this run's source scan did not surface at all (silent gaps are, by construction, not listed above) — see Method/tools below for how to extend the search.

## Tools

All scripts are under `collab-rebuild-tools\`: `scan1_grep.py` (raw `.collab` hits across every source), `scan2_claude.py`/`classify_codex.py`/`scan_codex.py`/`scan_pi.py` (per-source structured extraction), `reconstruct_simple.py`/`reconstruct_pi_notes.py` (Write/Edit replay for ordinary notes/reviews), `gen_report.py` (this file's non-BOARD sections).

BOARD.md pass 1 (linear replay-from-start): `collect_board_mutations.py` / `extract_board_py.py` / `replay_board.py`.

BOARD.md pass 2 (anchor-and-replay, current): `extract_board_reads.py` (Read-snapshot card slices), `extract_card_anchors.py` (per-card newest-anchor selection from snapshots + Codex prompts), `extract_targeted_results.py` (re-fetches the tool_result for every mutation's own tool_use_id, since the original broad scan dropped results that didn't mention `.collab`), `replay_board_v2.py` (anchored assembly + skip-if-superseded replay + duplicate-card guard), `gen_board_report.py` (the BOARD.md section above). `claude_events.dedup.jsonl` is the event set with the `.pre-restart-D--Claude.jsonl.bak` duplicate session removed.
