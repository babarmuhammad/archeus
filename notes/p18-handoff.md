# P18 handoff — spatial visualization, mid pre-push audit

Written 2026-09-29 for the next session. Branch `archeus-v1-rearchitecture`. **Nothing of P18
is pushed.** Do not push without the user's explicit approval.

## Where things stand

- P17 is pushed and CI-green (run 36601924119, all 12 jobs; `b5f978f`).
- P18 is implemented and committed locally in 7 commits on top of `b5f978f`:
  - `ecfbacd` docs: P18 design gate (APPROVED, A1–A17, §4.1 decisions, §1.3 inventory)
  - `20c26ec` the graph query + `GET /v1/world/graph`, `GET /v1/repositories/{id}/graph`
  - `5bada10` `EDGE_WORDS` in `relations.ts`; `/v1/world/graph**` in `invalidation.json`
  - `711a052` the spatial view (`clients/app/src/graph/*`, World/Relations links, routes)
  - `67ae6b6` TS, browser, boundary tests; `tools/mutate_p18.py`
  - `24d6190` P16 M28 / P17 M11 mutation anchors moved with the invalidation table
  - `f9ad2ee` docs: P18 as built (gate §22 I1–I13, §23; plan; ui-architecture §5; ADR-0016;
    research §26; design system; testing strategy)
- The user **approved I1, I2, I3, I5** (2026-09-29) and asked for a final pre-push audit
  before any push. That approval is **not yet written into the gate** — record it in §22
  (status column "approved 2026-09-29") in a docs commit.

## Verified results (code tree unchanged since `67ae6b6` except tools anchors and docs)

- Full suite `py -m pytest tests/ --basetemp=C:\t18`: 4,801 passed, 0 failed, 15 skipped, 6 xfailed (16 min).
- e2e + G3 (`ARCHEUS_E2E=1`): 27 passed, 3 skipped (GUI/TUI over in-process), 1 xfailed (P19).
- `npm test` 64/64, `tsc`, `vite build` (390 KB JS / 119 KB gzip, 17 KB CSS), Ruff,
  `gen_ui.py --check`, `gen_api_docs.py --check`, mkdocs `--strict`: clean.
- Wheel: built, installed in a clean venv, `tools/check_wheel.py` passes, installed Core lists both graph routes.
- Mutations: P18 33/33; P8 22, P9 36, P10 37, P11 36, P12 28, P13 16, P14 21, P15 23, P16 29,
  P17 28 — all killed (P16/P17 after `24d6190`).

## Audit progress (the user's 10-point audit) — what is done, what is open

Done: false-kill check of the TS-guarded P18 mutants (script in the old session's
scratchpad, easy to redo: apply each mutant, run `node --test test/graph.test.ts`, check the
test named for its invariant is among the failures). Result: all direct **except M17**.

### Findings — genuine gaps against APPROVED gate decisions (user said: STOP and report, do not fix speculatively)

| # | Gate section | Gap | Smallest compliant fix | Changes an approved decision? |
|---|---|---|---|---|
| F1 | A13 | **Pin** is not implemented: `pinned` state exists in `GraphView.tsx` but nothing ever sets it (no key, no UI). | A key (e.g. `.` or `I`) toggling the selected node in `pinned`; layout already fixes pinned nodes; never auto-collapse a pinned node; mirror says "pinned"; one TS test + mutant. | No (implements A13) — or the user drops pin (a decision change) |
| F2 | A10 | **Frame-time degrade** (3 frames > 20 ms during an animation → drop pulses and non-focus labels) is not implemented. | Track frame deltas in `Loop.tick`; expose `degraded`; `render` skips pulses and non-focus labels when set; TS test with a fake clock + mutant. | No |
| F3 | A10 proxy (5) | During a pulse the **whole scene is redrawn** each frame; the gate said only the pulsed edge is redrawn over a static layer. | Either cache the static layer (offscreen canvas) and draw pulses over it, or correct the gate's proxy (5) — a doc change to an approved proxy, needs the user. | Possibly (if the doc route is chosen) |
| F4 | A11 | Closing an inspector opened from the graph moves focus to `main h1` (P16's rule), **not back to the canvas with the same node selected**. | In `GraphView`, on becoming visible again after an inspector closes, focus the canvas (walk state is kept); e2e assertion. | No |
| F5 | A3 | A **superseded/rejected plan version node** is not drawn at `--text-3`; only its edge is. | `render.drawNodes`: inactive plan states → `--text-3`; extend the encoding test. | No |
| F6 | A18-14 / as-built | The **pulse itself is not tested** (rate limit ≤ 1 per 2 s, frame → pulse, none when ended/reduced). As-built §23 wrongly says "the pulse itself is TS-tested". | Extract the pulse decision (frame, live set, last-pulse map, now, reduced → pulse or not) into a pure function in `model.ts`/`loop.ts`, test it, add a mutant; fix the §23 sentence. | No |
| F7 | mutation integrity | **M17 possible false kill**: under the mutant, `node --test test/graph.test.ts` printed no failing test in the false-kill check, yet the suite recorded it killed (a crash/timeout or exit code counted as a kill?). | Re-run M17 alone, read the node output; if the loop test does not fail cleanly, make `host.run`'s cap produce an assertion failure (it should: `run()` returns 1000 ≠ 1) and fix the runner to require a test failure, not any non-zero exit. | No |

### Documentation inaccuracies found (fix in a docs commit; no architecture change)

- **D1 A1**: says `graph.py` holds one `EDGES` table; it is a per-kind `held_edges()` function (+ `relation_edge`, `_holders`). Also "`structural` marks two" is superseded by I3.
- **D2 A2**: parent of a review is its **plan** (`reviews.plan_id`), not its mission; session → mission else project; automation_run → automation; context_package/automation → project.
- **D3 A5**: "payload missing → logged once per sha" is not implemented (no logging). Drop the claim or add the log line (tiny; user's call — doc fix is the default).
- **D4 A6/A15**: queries are **per node** (`rows.where` per id), not "one batched IN per edge definition per hop". Cost is bounded by the size of the neighbourhoods read (a project with 10k knowledge items loads them all before the cap), **not by the 1,000-node cap** — measured 0.10 s for 1,100 items. Correct the "bounded cost" wording and add it to the P24 carry-forward (DoS/aggregation).
- **D5 A7**: a **focus change** remounts the view (key = read path) and **jumps**; there is no camera tween on focus change (zoom/fit do tween). Less motion than approved — record with I6.
- **D6 A10**: the client never exceeds the cap because a view holds **one read** (≤ limit + "+N" stubs) and a stub re-focuses; the "collapse the farthest cluster first" mechanism is unnecessary and not built. Record.
- **D7 §13**: the `Math.random`/`Date.now` ban on `layout.ts` lives in `clients/app/test/graph.test.ts`, not `tests/v1/design/test_design_gates.py`.
- **D8 §23**: after F1–F6 are decided, the sentence "Everything in §1–§21 is built as written … except I1–I13" must list what is not built.

### Audit points not yet re-checked this session (were green at the last full run)

- Points 2–4 (preservation, boundaries, security) were verified by the existing tests and
  code reading: `graph.py` imports no writer/router/extractor (`test_graph_boundaries.py`),
  routes use `db.read()` only, `KINDS` excludes credential kinds, per-kind field allowlist,
  `clean_label` (redact + printable + 120), repository `focus` rejects `..`/`.`/`\`/>1024 and
  is only compared with stored paths. `relate()` untouched; `connections.build_hierarchy`,
  `relations.ts` list functions (output unchanged, `parity.json`), `present.py` untouched.
- Point 6: 390 px overflow of a graph URL was not measured (P16's overflow audit covers
  destinations, P18's covers 768–1920). Quick check: open `#/world/graph/mission/<id>` at
  390×844 and assert `scrollWidth - innerWidth <= 0`.
- Point 7: after any fix, re-run everything below.

## Constraints (the user's, binding)

Do not touch `main` (`26f983b`), PR #6 settings/auto-merge, `.gitignore` (user edit),
`notes/p16-handoff.md`, `references/`, the two GitHub Desktop stashes. Do not amend or squash.
Separate commits for doc fixes and test/anchor maintenance. Genuine product defects: report
first (F1–F7 above are that report), fix only after the user decides. Never claim the manual
checks. Push only on explicit approval, then watch CI and report every job.

## Manual checks still owed by the user (steps in gate §23)

1. 60 fps on integrated graphics (A10) — DevTools Performance during `+`/`-`/`0` and a pulse.
2. Windows Terminal + conhost check of `archeus tui` (carried from P17).

## How to run things (gotchas learned here)

- Run long suites in a hidden console: write a `.ps1`, launch with
  `powershell.exe -NoProfile -Command "Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','<script>'"`.
  PowerShell `>>` writes UTF-16; read logs with `bytes.replace(b'\x00', b'')`.
- Full suite needs a **short** `--basetemp` (`C:\t18`); a long one breaks `git worktree add`.
- Mutation runners (`tools/mutate_p*.py`) read files raw: a **CRLF working copy** makes
  multi-line anchors miss. Normalise with Python (`bytes.replace(b'\r\n', b'\n')`); `grep $'\r'`
  under Git Bash did not detect it. Git shows such files as modified with an empty diff.
- Bash heredocs eat backslashes (`\n`, `\r`): write patch scripts with the Write tool.
- `mutate_p18.py` M33 rebuilds the SPA (`npm run build`) before and after its browser test.
- e2e: `ARCHEUS_E2E=1 py -m pytest tests/v1/e2e tests/v1/judge/test_g03_one_model.py`.
- Regression order used: gen checks → ruff → SPA build + `npm test` → e2e + G3 → full suite →
  `mutate_p8`…`mutate_p18` (sequential; they edit sources) → mkdocs strict → wheel in a clean
  venv + `tools/check_wheel.py`.

## Next steps, in order

1. Record the user's approval of I1, I2, I3, I5 in gate §22 (docs commit).
2. Resolve F7 (runner integrity) — it is test infrastructure, may be fixed as maintenance
   if the cause is the runner; report it either way.
3. Present F1–F6 and D1–D8 to the user; wait for decisions on F1–F6 (F3 may become a doc fix).
4. Apply the approved fixes in separate commits, D1–D8 in a docs commit.
5. Re-run the full regression list above on the final tree.
6. Report the pre-push status in the user's format; push only on explicit approval.
