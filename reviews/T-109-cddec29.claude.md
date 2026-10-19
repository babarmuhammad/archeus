VERDICT: APPROVE

Scope: T-109's five items (a-e) on cddec29 (D:/archeus-pv20-t109, detached from ca123e5): 1adbd8e
(a, T-107 busy-retry shape), 5049338 (b, T-096 clearToken memory mode), fc60d3d (c, T-103 runtime
gate), 4fce4ef (d, T-105 parse guard), cddec29 (e, T-098 one no-PIN reason). Read each diff with
`git show`, read the five cited reviews (T-107-1b87969, T-096-e7141c1, T-103-ec90967, T-105-fadadd7,
T-098-e0880a2), then ran every test and mutant from the live checkout and from throwaway copies
(`git archive cddec29` into D:/trv-T109-m1 for mutants, restored byte-identical after each one).

## Per-item judgement

**(a) T-107 busy-retry shape + armed replay.** Meets the accept item. J04b (test_presence.py:808-830)
holds the writer with a threading.Event so a keyed right-PIN re-arm answers 503 busy and commits
afterwards; its retry answers `{'armed': False}` with Core still disarmed, and a fresh request
re-arms. J04 (test_presence.py:788-803) adds a replay while Core is armed, expecting
`{'armed': True}`. Both are exactly reviewer probes P1 and P2 from reviews/T-107-1b87969.claude.md.
Mutants re-run on a fresh archive, routes.py:645-646:
  - R14 (replay clears the sentinel when no `core.estopped` followed the last `core.rearmed`,
    reconstructed from the events log via `queries.events`): **J04b fails it**
    (`{'armed': True}` instead of `False`).
  - R15 (replay always answers `armed: false`): **J04 fails it** (`{'armed': False}` instead of
    `True`).
  - File restored and diffed byte-identical to the archive after each.

**(b) T-096 clearToken in memory mode.** Meets the accept item. transport.ts:46-50: `clearToken`
now skips the IndexedDB delete when `memoryOnly()`, leaving the disk copy to `retire()` alone.
transport.test.ts adds a parametrized case (sync 503, revoke 500, revoke 403, sync with no client)
asserting the kept-admin-token invariant, plus a case that `clearToken()` in memory mode leaves a
disk-kept token alone.
  - Mutant "keep only on status 0" (`if (e instanceof CoreError && e.status === 0) return;`,
    dropping the `401` check and the outer negation so only a network error keeps the token and
    everything else — 401, 403, 500, 503 — deletes): **the four parametrized cases fail** (503,
    revoke 500, revoke 403, no-client all now delete). The two pre-existing tests ("Core down" and
    "already revoked") pass unaffected, since those two land on status 0 and 401 respectively,
    which this mutant's boundary happens to get right — the parametrized cases are what catches it.
  - Restored byte-identical; `node --test test/transport.test.ts` and `test/estop.test.ts`: 17
    passed; `tsc --noEmit`: clean.
  - Behaviour check asked for: does sign-out in memory mode now leave a live token nothing
    retires? No. `clearToken()`'s callers are (1) `authenticate()`'s own revoked-while-away branch,
    which is disk-mode only (`stored` path, not `held`); (2) Control's "Revoke this client", which
    calls `api.revokeDevice` on the server FIRST and runs `clearToken()` only in `onDone` after
    that succeeds (Control.tsx:706-713) — so the only token this path forgets is the one just
    revoked server-side, and `held` is what's cleared in memory mode. A *different* legacy disk
    token this shell could not revoke earlier is untouched by either path and stays for the next
    launch's `retire()` to retry, which is the pre-existing documented contract at transport.ts:53-57
    ("Core down or refusing: it stays where it is and the next launch tries again"), unchanged by
    this commit.

**(c) T-103 runtime secrets gate.** Meets all four parts of the accept item.
test_p20_secrets_runtime.py: the `rig` fixture (149-163) attaches a `logging.FileHandler` on
`archeus.core` exactly as `Core._open_log` does, and removes it on teardown. `PIN` is now a
12-digit value (`'482913570264'`) added to `found` and scanned, allowed nowhere. `_files()` (76-90)
catches `FileNotFoundError` only, not `OSError`. `leaks()` asserts `MUST_READ <= read`
(`{'logs/core.log', 'archeus.db'}`), and the HTTP test adds `assert auth.token_hash(local).encode()
in db` (131). The mission step now goes through the local token and asserts `m.status == 200` (111),
resolving finding 6 by making the lifecycle real rather than refused.
  - Mutant "PIN logged" (`logging.getLogger('archeus.core').info('pin %s', b.get('pin'))` in
    `pair_redeem`, routes.py:268-269): **test_no_minted_credential_is_at_rest_outside_its_one_home
    fails** — `leaks()` finds `('pin', 'logs/core.log')`.
  - Mutant "unreadable file" (reverting `_files()`'s `except FileNotFoundError` back to the old
    `except OSError`, T-103 review finding 4): verified both halves with a throwaway probe (a
    `run/`-file holding a known secret, locked with `msvcrt.locking` for the scan's duration).
    Under the current (fixed) `except FileNotFoundError`, `leaks()` on the locked file raises
    `PermissionError` — it fails the scan rather than silently passing. Reverted to the old
    `except OSError`, the same locked-and-secret-holding file is silently skipped and `leaks()`
    returns `[]` — the exact pre-fix regression. Probe file removed afterward; both touched files
    restored byte-identical.
  - `py -m pytest tests/v1/integration/test_p20_secrets_runtime.py`: 2 passed (unmutated).

**(d) T-105 orphan adoption parse guard.** Meets the accept item. manager.py:836-842:
`_adopt_orphan` now builds `ProcessHandle`/`ExecPaths` inside a `try` that catches
`(KeyError, ValueError)`, logs `'registry line %r cannot be read (%s); skipped'`, and returns
`False` rather than letting a malformed line raise through `boot()`. The no-adapter kill path
(847-856) now checks `kill_identity`'s return and logs "it could not be killed (gone meanwhile, or
the kill was refused)" when it returns `False`, instead of unconditionally claiming "killed by its
recorded identity".
  test_settings_sources.py adds two tests: one plants a spawn line with `execution_id: 'not-an-id'`
  and one missing `pid`, boots twice, and asserts both are logged and skipped on every boot (4
  "cannot be read" warnings total) rather than stopping Core; the other monkeypatches
  `kill_identity` to return `False` and asserts the log says "could not be killed", not "killed by
  its recorded".
  - Mutant "parse guard removed" (dropping the `try/except` so `ProcessHandle`/`ExecPaths` build
    unconditionally): **test_T105_a_registry_line_that_cannot_be_read_is_skipped_on_every_boot
    fails** — `ExecPaths('not-an-id')` raises `ValueError: not an execution id: 'not-an-id'`
    straight out of `boot()`, exactly the review's "nothing short of hand-editing
    run/processes.jsonl" scenario.
  - The except clause is scoped correctly: `KeyError` (missing `pid`/`execution_id`) and
    `ValueError` (`ExecPaths` rejects a non-id string) are precisely the two things a Core-written
    spawn line can never produce and a corrupt/planted one can. No legitimate line is swallowed —
    `test_T105_a_pid_now_held_by_another_process_is_neither_taken_in_nor_killed` and the harness/
    no-row cases still pass (10 passed, `-k T105`).
  - File restored and diffed byte-identical.

**(e) T-098 one no-PIN reason.** Meets the accept item. Control.tsx:934-939: the standalone hint
paragraph for `stepUp === 'none'` is gone; its sentence is now the `ActionButton`'s own `disabled`
value for that case (`stepUp === 'none' ? '...re-arm on the desktop.' : stepUpBlocked(stepUp, pin)`).
A no-PIN paired client now sees exactly one sentence.
  Behaviour check: does the no-PIN paired client still fail to re-arm, and is the local client
  unaffected? Yes to both, read from `stepUpBlocked` (present.ts:361-364) and the ternary: for
  `stepUp === 'none'` the button is unconditionally disabled with the custom string, same as
  before (`stepUpBlocked('none', pin)` was already unconditionally truthy regardless of `pin`); for
  `stepUp` undefined/`'local'`, the ternary falls to `stepUpBlocked(undefined, pin)`, which returns
  `null` (enabled) exactly as before — the local client's path is untouched text and untouched
  logic.
  `tools/mutate_p20.py`'s Q129 anchor was updated to the new string and is a unique match in
  Control.tsx (`grep -c` = 1); Q130's anchor is unchanged and still present.

## Ran

All pytest runs: `-p no:cacheprovider -m "not real_process"`, fresh `--basetemp` per run, on the
live checkout D:/archeus-pv20-t109 (not mutated):
- `test_presence.py -k J`: 10 passed.
- `test_p20_secrets_runtime.py`: 2 passed.
- `test_settings_sources.py`: 44 passed.
- `node --experimental-strip-types --no-warnings --test test/transport.test.ts test/estop.test.ts`
  (clients/app, node_modules already present in the checkout): 17 passed, 0 failed.
- `npx tsc --noEmit -p .` (clients/app): clean, no output.
- `py -m ruff check` on the five changed .py files: all checks passed.
- `git show --check` on all five commits: clean, no CR.

Mutants, each on a `git archive cddec29` copy (D:/trv-T109-m1), one at a time, file restored and
verified byte-identical (`git show <sha>:<path>` compared to the file on disk) before the next:
- R14 (a, routes.py): J04b **FAILED** it.
- R15 (a, routes.py): J04 **FAILED** it.
- status-0-only keep (b, transport.ts): the four new parametrized node cases **FAILED** it; the two
  pre-existing cases passed unaffected.
- PIN logged (c, routes.py pair_redeem): test_no_minted_credential... **FAILED** it.
- unreadable file / broad `except OSError` (c, test_p20_secrets_runtime.py): demonstrated with a
  throwaway locked-file probe — fails the scan (raises `PermissionError`) under the current fix,
  silently passes (misses the leak) under the reverted broad except. Probe file deleted afterward.
- parse guard removed (d, manager.py `_adopt_orphan`): the new T-105 test **FAILED** it
  (`ValueError` propagated out of `boot()`).

D:/trv-T109-m1 and all D:/trv-T109-bt* basetemps removed with `shutil.rmtree` (read-only git
objects cleared via `onerror` first). `D:/archeus-pv20-t109` is clean and detached at cddec29; no
writes were made there. No test process left running belonging to this review.

## Not checked

- Full tests/v1, POSIX, real_process, Qt, SPA e2e/browser suites (`test_spa_estop_about`,
  `test_unification`) — not asked for in this task's run list, and the e2e needs a fresh SPA
  build; the implementer's own verify line already reports it green (4 passed).
- `tools/mutate_p20.py Q125-Q130` as a batch run (the tool rebuilds the SPA for the e2e-guarded
  ones); I verified Q129's anchor by inspection and uniqueness instead.
- POSIX-specific behaviour named in the T-105 review (Linux starttime residual, single SIGTERM, no
  descendant identity check) — explicitly out of scope per the card's notes.
- The T-107 review's info items (races failing toward disarmed, the busy-shape's dangling
  `core.rearmed` audit entry) — unchanged by this card and not re-verified.

Reviewer: independent Claude agent (fork), 2026-10-19
