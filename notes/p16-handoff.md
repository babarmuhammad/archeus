# P16 handoff — where the session stopped (2026-09-28)

Branch `archeus-v1-rearchitecture`. Gate committed: `544e4c6` (docs: P16 design gate).
**Implementation is NOT committed and NOT pushed.** Everything below is in the working tree.

## Done

- Design gate `docs/architecture/p16-design-gate.md` (committed), plus §30 As built and
  `DESIGN_GATE = IMPLEMENTED` (uncommitted edit).
- User decisions this session: **D2 launch scopes = "minter chooses"**; **CI edit approved**
  (v1-client: `npm test` + G3 judge file added to the e2e step — done); **delete
  `clients/app/src/styles.css` approved** (done, `git rm`).
- Backend seams: `archeus/core/application/attention.py` (attention + timeline),
  `archeus/core/execution/output.py` (redacted output tail), route rows/schemas/auth/server/
  runtime/CLI changes, `tools/gen_api_docs.py` query types. API ref + `generated.ts` regenerated.
- Client: tokens/presentation tables, `tools/gen_ui.py`, whole SPA under `clients/app/src/`,
  `public/` (sw.js, manifest, icons), deps `qrcode-generator` (runtime), `axe-core` +
  `@types/node` (dev).
- Tests, all green when last run: `tests/v1/integration/test_ui_seams.py` (10),
  `tests/v1/design/test_design_gates.py` (15), `clients/app` `npm test` (38),
  `tests/v1/e2e` (17, with ARCHEUS_E2E=1), G3 GUI judge function (xfail marker removed),
  unit pins updated (`test_api_structure`, `test_api_auth_units`, `test_presence_units`).
- `tools/mutate_p16.py`: **29/29 killed**.
- Ruff clean, `tsc` clean, `gen_api_docs --check` and `gen_ui --check` clean.
- Plan: P16 as-built entry under §31.1 and Q4–Q8 statuses updated (uncommitted).

## Second session (2026-09-28, afternoon) — state when stopped

Done and green:
- Full suite (hidden console): 4514 passed, 31 failed — ALL 31 were the verification tests
  (`test_verification.py`, judge S06/V01/V06), and all caused by my `--basetemp` sitting under
  the long scratchpad path: `git worktree add` failed with `fatal: '$GIT_DIR' too big`. Re-run
  hidden with a short basetemp (`%TEMP%\ptv`): **31/31 pass**. Always use a SHORT basetemp.
- `npx vite build` (360 KB JS), `npm test` 38/38, e2e + G3 (`ARCHEUS_E2E=1`): 18 passed,
  2 skipped, 3 xfailed (later-phase drivers). `mutate_p16.py`: **29/29 killed**.
- `mkdocs build --strict`: clean.
- Doc notes (step 5) written: `ui-architecture.md` (Q4 as built, §5.1 done),
  `api-and-realtime.md` (UI reads row, launch grant), `testing-strategy.md` (G3 row, client
  units layer), `external-references.md` R7 (c1b70d0, MIT, patterns only).

Product bug seen, NOT fixed (out of P16 scope — report it, decide later): when
`git worktree add` fails after creating the branch, every retry fails on "branch already
exists" and the task is retried forever ("not charged (binding)"): 395 attempts in one test.
A failed workspace preparation needs either branch cleanup or a retry budget.

## Still to do (in order)

1. P8–P15 mutation suites: `scratchpad` had a loop script; simply run each
   `tools/mutate_p8.py` … `mutate_p15.py` under `Start-Process … -WindowStyle Hidden -Wait`.
2. `python -m build --wheel` + `tools/check_wheel.py` (wheel must carry `static/sw.js`,
   `static/manifest.webmanifest`, `static/assets/icon-*.png`).
3. Commit implementation separately from the gate (stage explicitly; **do not** stage the
   user's `.gitignore` edit). Push only after validation and the user's OK; watch CI.
4. Final report per the P16 brief §22 (most content is in gate §30).

## Console windows during tests — fixed (after the first stop)

Cause, proven with a probe: executions were spawned with `DETACHED_PROCESS`
(`archeus/harnesses/base.py` → `proc.spawn_detached`), so they had no console and every
console program they started (the fake agent's PreToolUse hook on EVERY tool call; in
production a real harness's hooks, git, test commands) got a new **visible** window. Hiding the
pytest parent could not help: a detached child inherits nothing.

Fix: `proc.hidden_console_flags` (`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`) and
`spawn_detached(..., hidden_console=True)`, used by the harness spawn only; the default
(`detached_flags`, the upgrade worker) is unchanged. Test:
`tests/v1/unit/test_spawn_console.py` (mutation-checked by hand: dropping the flag fails it).
`test_p05_seams`, `test_versions`, `test_skeleton`, `test_execution` pass. This is a product fix
too and belongs in the P16 commit (or its own commit).

The full suite was stopped at 64% with no failures (it was the one opening windows). Re-run it
from the start; windows should no longer appear. If one still does, find its spawner with the
same probe idea (`GetConsoleWindow` + `IsWindowVisible` in the grandchild).

## Don't touch

`main`, PR #6, stashes, `references/`, the user's unstaged `.gitignore` edit.
