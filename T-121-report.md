# T-121 report: P21 slices F (Core search, D7) and G (OS notifications, D1)

Claude fork, 2026-10-19, worktree D:\archeus-t121, branch p21-fg. Not pushed. BOARD.md not edited.

## Recovered vs added

- Recovered: e6d9a25 (content of the earlier fork that stopped at the 85% pause). I audited it against the card and the gate (D1, D7, sections 8 and 9) and found it complete. It contains `GET /v1/search` (`observe`, 1..200-char needle, missions/projects/knowledge cut to id and title, at most 20 each), the Core-backed command bar with the client-only filter kept as the offline fallback, and the tray notices while the window is hidden. Notices name the kind only. They read from the head onward and say each event once. When Core is down the tray stays silent. The commit also has F01-F03, G01-G02, Z50-Z59, the regenerated client/API reference, and the gate's "As built" section. There is no migration: 0019 is unused, because the search scans the three tables in Python. A `ponytail:` note marks the ceiling.
- Scope check: scopes are global (`archeus/api/auth.py:24`, no per-project grants), and `/v1/missions`, `/v1/projects` and `/v1/knowledge` filter no rows by caller. Search under `observe` therefore exposes nothing the caller cannot already read. F03 covers a no-`observe` token (403) and no token (401).
- Notification content: G01 runs on a real Core with a mission title carrying `TOKEN=sk-live-123`, and none of it is said. G02 covers a payload with a command and an unknown kind, which is said as "request".
- Added:
  - f5980f4: `tests/v1/unit/test_api_structure.py` gains a `P21` route table. The recovered slice had left the exact-route-table test failing on the extra `/v1/search` row.
  - 3a95544: one line in the gate's "Found while building" section recording it.

## Commits (on p21-fg)

- e6d9a25 Recover P21 slice fg (kept as is)
- f5980f4 P21 slice F: the route-table test names /v1/search
- 3a95544 P21 gate: record the slice F route-table row

## Verify

- Targeted, with ARCHEUS_E2E=1 and the SPA built: test_p21_search, test_gui_shell, test_mutation_suites_parse, e2e test_spa_palette, e2e test_gui_qt. **63 passed.**
- Doc gates and route suites: tests/v1/design, tests/v1/judge/test_traceability.py, tests/v1/unit/test_paths.py, tests/v1/unit/test_api_structure.py. **81 passed.**
- Contract and API suites:
  - tests/v1/contract, test_api_client, test_api_origin, test_directives, test_p195_core: passed.
  - test_api_errors: every failure was `OSError: [WinError 10048]` (port already bound; other forks' Cores were running at the same time). The failing set changed from run to run (12 failures = 12 bind errors). The `/v1/search` case and the token-refusal test pass when run alone (2 passed).
- Mutants: `tools/mutate_p21.py Z50..Z59` **10/10 killed**, tree clean after. Z01-Z22 were not re-run in this pass. The earlier fork reports 20/20, with Z13/Z14 re-anchored.
- Client: `tsc --noEmit` clean. Node tests 244/245. The one failure ("the rows read the page's reduced motion and its slow frames") is a CRLF checkout artifact: Git for Windows has `core.autocrlf=true` system-wide, and the test regex expects `\n`. The committed blob of `clients/app/src/components/ui.tsx` matches, and this slice does not touch that file.
- Generators: `gen_api_docs.py --check` and `gen_ui.py --check` current. Ruff clean.

## Files touched by the slice (e6d9a25 + additions)

archeus/api/routes.py, archeus/api/schemas.py, archeus/cli/_api.py (generated), archeus/cli/gui.py,
archeus/core/application/queries.py, claude_sessions/gui_qt.py, clients/app/src/api/generated.ts
(generated), clients/app/src/state/palette.ts (comment only), clients/app/src/surfaces/CommandBar.tsx,
docs/architecture/api-reference.md (generated), docs/architecture/p21-design-gate.md,
tests/v1/e2e/test_spa_palette.py, tests/v1/integration/test_gui_shell.py,
tests/v1/integration/test_p21_search.py, tests/v1/unit/test_mutation_suites_parse.py,
tests/v1/unit/test_api_structure.py, tools/gen_api_docs.py, tools/mutate_p21.py.

None of these is isolation, boundary, credential or auth code. `routes.py` only adds a row under the existing `observe` scope, and `auth.py` is unchanged.

## For the reviewer

- `Shell.notices` reads `/v1/events?after=…&limit=500`. A backlog of more than 500 events between two 10-second ticks is said across several ticks, not dropped.
- `tests/v1/unit/test_mutation_suites_parse.py` now parse-checks `mutate_p21`. If slices A/C/D also touch `tools/mutate_p21.py`, expect merge conflicts in that file when the slices are integrated.
