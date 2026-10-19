# T-119 report: P21 slice C-read (trace view, R13-03, R13-05) and the C-write file-scope check

Claude (T-119 fork), 2026-10-19. Stopped by the owner's wrap-up order before review. Work in
D:\archeus-t119, branch `p21-c`. Not pushed.

## Commits on p21-c

| Commit | What |
|---|---|
| `23e973a` (recovered, kept) | everything the slice builds: `archeus/core/application/trace.py` (new), the trace route and schemas, `normalise` keeps the lane and call/result ids, TUI and SPA Trace tab with a two-clock replay, bare `why` in a thread (R13-05), the digest folds messages (R13-03), generated client and API reference, `tests/v1/integration/test_trace.py` (7), `tests/v1/e2e/test_spa_trace.py` (1), Z30-Z39 |
| `e5e11b0` (WIP, added) | `tests/v1/unit/test_api_structure.py` gets a P21 table naming the trace route (the recovered slice failed this structural test); `docs/architecture/p21-design-gate.md` section 12, slice C-read as built |

## What was in the recovered content and what was added

Audited 23e973a against the card's accept. Already there: the trace builder over events and
`cause_chain`, decisions, checkpoints; sidechain lanes with call->result pairing; the event-time
replay; R13-05; R13-03; the SPA view; Z30-Z39. Added: the route-table test fix and the gate's
section 12. No migration (none needed). Re-checked the C-write analysis (below).

Touched files (both commits): `archeus/api/routes.py`, `archeus/api/schemas.py`,
`archeus/cli/_api.py`, `archeus/cli/tui/_tables.py`, `archeus/cli/tui/screens.py`,
`archeus/core/application/conversation.py`, `archeus/core/application/grammar.py`,
`archeus/core/application/trace.py`, `archeus/core/world/digest.py`,
`archeus/harnesses/claude_code/adapter.py` (stream normaliser only: reads three more fields of the
stream, no launch, hook or judgement change), `clients/app/src/api/generated.ts`,
`clients/app/src/nav/table.ts`, `clients/app/src/surfaces/Mission.tsx`,
`clients/app/src/surfaces/Now.tsx`, `clients/app/test/shell.test.ts`,
`clients/app/tokens/navigation.json`, `docs/architecture/api-reference.md`,
`docs/architecture/p21-design-gate.md`, `tests/v1/e2e/test_spa_trace.py`,
`tests/v1/integration/test_trace.py`, `tests/v1/unit/test_api_structure.py`, `tools/mutate_p21.py`.
None of them is `archeus/node/isolation.py`, the hook, `authorization.py` or a credential path.

## Verify so far

- `tests/v1/integration/test_trace.py`: 7 passed.
- `tests/v1/e2e/test_spa_trace.py` (ARCHEUS_E2E=1, real browser): 1 passed.
- `ruff check archeus tests tools`: clean. `gen_ui.py --check`, `gen_api_docs.py --check`: current.
- Client: `tsc --noEmit` + `vite build` pass. `node --test`: 244/245; the one failure ("the rows read
  the page's reduced motion and its slow frames") matches a `\n` regex against `Components.tsx`,
  which this slice does not touch; this checkout has `core.autocrlf=true`, so the file is CRLF.
  Environmental, not this slice.
- Full `tests/v1` without e2e (48 min, run with other forks loading the machine): 4458 passed,
  8 failed. One was this slice (`test_api_structure` route table) and is fixed in `e5e11b0`
  (`test_api_structure.py` 8 passed after). An earlier run with `-x` stopped on
  `test_p195_core::test_the_all_scope_routes_answer_over_http` with `WinError 10048` (socket
  exhaustion); it passes alone. **Not yet rerun:** `test_api_errors` (2),
  `test_settings_sources` H01/H02, `test_mutation_suites_parse[mutate_p17]` (2, likely the CRLF
  checkout), `test_tool_removal_units` F10. None is in a file the slice touches; not yet shown to
  fail on the base `d0b98d3` as well.

## Not done

- Z30-Z39 mutation run (`py tools/mutate_p21.py Z30 ... Z39`). It edits sources, so it had to wait
  for the full run. Not run.
- Full e2e suite (only the trace test ran).
- The rerun of the seven failures above, on this branch and on `d0b98d3`.
- Independent Claude review; Codex aimed review of the C-write analysis (the card's review line).

## C-write

Not built. `.collab/T-119-cwrite-scope.md` holds the check: the pre-wipe text, recovered, with
corrections marked [re-check]. The result is unchanged. Approval-issued causes need
`authorization.py`, so C-write waits for P20 or the owner's explicit word. A narrower C-write-1
(only the three event consumers and cause forwarding) touches no excluded file. It is the owner's
choice and is not recommended.

## Next step

Run Z30-Z39 and the full e2e on an otherwise idle machine. Rerun the seven failures here and on
`d0b98d3`. Then the independent review, plus Codex on `T-119-cwrite-scope.md`.
