# Shared workspace board — rebuilt 2026-10-19 after the D:\Claude wipe

## What happened and what was recovered

The `D:\Claude` working tree (git object store, `.collab`, the owner's uncommitted docs) was
deleted 2026-10-19 ~12:33 UTC. Cause: a Qwen `pi` run cleaning its T-111 test fixture ran
`cmd /c rmdir /s /q D:\t111` from a bash heredoc; the heredoc turned `\t` into a TAB, so cmd
received `rmdir /s /q D:` = the current directory on drive D, which was the repo root. The
archeus GUI then wrote a fresh project scaffold over the empty folder (it did NOT cause the
deletion — Qwen's own session log holds the command).

Recovery:
- Canonical repo re-cloned to `C:\Users\mab\archeus-recovery\repo` (origin `c8f5bd5`, all pushed
  work intact).
- Unpushed commits rebuilt from the surviving sibling worktrees (content identical; original SHAs
  dead) and pushed to origin under `recover/*`:
  - `recover/p20-p21-chain` = cddec29 → T-112/T-113 (e9c2191) → T-116 (3dba2cc) → P21 gate (d0b98d3)
  - `recover/p21-a`, `recover/p21-c`, `recover/p21-d`, `recover/p21-fg` — the four P21 slices, each
    off the recovered gate, NOT yet reviewed or merged.
- Lost and not recoverable: `.collab` history (board, all review files, the T-110 O7 note), the
  owner's uncommitted `docs/design/ARCHEUS_V2_*` edits and untracked files in `D:\Claude`. Check
  Windows Previous Versions / File History on `D:\Claude` for those.

Qwen is now contained (`.collab/qwen_run.py`): cwd locked to `C:\Users\mab\qwen-sandbox` (an
isolated worktree), analysis/review cards run with NO bash tool, test-running cards refused
without explicit owner sign-off.

## Current card state

| Card | State | Where |
|---|---|---|
| T-072 round 5, T-108, T-109 | done, pushed | origin c8f5bd5 |
| T-112 / T-113 | done (reviewed APPROVE) | recover/p20-p21-chain e9c2191 |
| T-116 | done (reviewed APPROVE) | recover/p20-p21-chain 3dba2cc |
| T-117 P21 gate | approved (D0-D14) | recover/p20-p21-chain d0b98d3 |
| T-118 P21 slice A (provenance) | built, NEEDS REVIEW | recover/p21-a |
| T-119 P21 slice C-read (trace) | built, NEEDS REVIEW; C-write scope note lost | recover/p21-c |
| T-120 P21 slice D (metrics/doctor) | built, NEEDS REVIEW | recover/p21-d |
| T-121 P21 slices F+G (search/notify) | built, NEEDS REVIEW | recover/p21-fg |
| T-114 (main→branch merge) | done, pushed | origin c8f5bd5 |
| T-110 O7 breaker note (Qwen) | LOST (Codex had said CHANGES); redo | — |
| T-097 login-probe note (Qwen) | Codex CHANGES r2 outstanding; note lost | — |
| T-111 E1 evidence (Qwen) | BLOCKED — see QWEN-DONE-T-111.md; its native ACL run is what wiped the repo | — |
| T-008 Windows evidence (Qwen) | authorized, NOT started | — |
| T-106 O7 breaker | proposed; waits on T-110 | — |
| T-004, T-065 | blocked on owner | — |

## Open follow-ups (integration)

- Migration collision: P21 slice A and slice D both number their migration `0017`
  (`0017_artifact_records.sql` vs `0017_metrics_daily.sql`). Renumber one (A=0017, D=0018) when
  merging.
- Integrate the recovered P21 work onto the live `archeus-v1-rearchitecture` (c8f5bd5) after the
  four slices are reviewed — same round-5 merge discipline.
- `.collab` must never again be the only copy of state: this board now lives in the tracked repo
  under `.collab/` of the recovery clone, but confirm the repo's `.gitignore` is not excluding it
  before relying on commits.

## Hard rules (unchanged, plus the wipe lesson)

- Never build a shell deletion path by string-interpolation or through a heredoc: `\t`, `\n` etc.
  are mangled. Delete only with Python `shutil.rmtree` on an absolute path asserted to be under a
  known temp root. Never `cmd /c rmdir`, never a bare `D:`/`C:` drive spec.
- Qwen never runs in or cd's to a real repo; its cwd is the sandbox worktree only.
- `.collab` and any state that matters is kept in a tracked, pushed location — not an ignored dir
  that one `rmdir` erases.
