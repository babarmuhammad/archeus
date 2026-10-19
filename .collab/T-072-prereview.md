# T-072 pre-review: T-062, T-086/T-085, and the four union merge resolutions

Read-only review by a general-purpose agent (fork), input for Codex — not a review
verdict. Repo reviewed: `D:/archeus-pv20-integration` at HEAD `b6ff773`. No product
or test code was run; findings are from reading the diffs and the resulting code at
HEAD, plus tracing call graphs by hand.

## 1. T-062 (A6-4 confined verifier sinks) — `6203e8d`

**Checked, no issue** (traced every path that can create or update a `Verification`
row, not just the ones the card names):

- `archeus/core/application/verification.py::start()` (`:185-231`) is the only place
  that stamps `verifier_version='a6.1'` (`CONFINED_VERIFIER`), and only when
  `guarded and verifier != 'generic_human'` and `confined(e, revision, workspace)`
  holds, re-derived from a fresh `_task_lineage()` read inside the transaction — not
  from anything the worker passed in. `start()`'s signature has no `verifier_version`
  parameter at all (verified against the actual kwargs-only signature, not just the
  docstring), so a caller passing it gets `TypeError` before any row is touched;
  `tests/v1/integration/test_verification.py::test_A6_4_a_caller_cannot_name_the_verifier_version`
  (added by this commit) asserts exactly that via a real call, not a mock.
- Two other constructors of `entities.Verification` exist outside this file
  (`archeus/core/application/work.py:416,441` and `archeus/core/ports.py:116,170`).
  Neither ever sets `verifier_version` (it defaults to `None`), and neither is on the
  production path: `work.py`'s `record_task_verification`/`verify_mission` and the
  `ports.py` stubs (`AutoPassVerifier`, `ScriptedVerifier`, …) are explicitly the P3.5
  "walking skeleton" (`archeus/core/engine.py`'s own docstring: "real verification …
  (the verification worker, core/verification/worker.py, P13 — the engine verifies
  and reviews only through injected stubs)"). They cannot produce an `'a6.1'` row, but
  they also have **no A6/A6-4 guard of their own** — see finding below.
- `evidence.run_commands()` refuses a `CONFINED_VERIFIER`-stamped row before any node
  call (`:107-108`), and tracing every caller of `run_commands` (`_run_and_record`,
  `_retry`'s mission branch, `_verify_mission`) confirms none of them can reach it with
  `verifier_version == 'a6.1'`: the task branch of `_run_and_record` is only invoked
  when `guarded` is false or when a confined route was unavailable and `cmds` was
  already forced to `[]` by the guarded branch (`worker.py:211-219`), which routes to
  the human verifier instead and never calls `run_commands`. Mission-subject
  verifications can never be stamped `'a6.1'` at all, since `confined()` requires
  `subject.kind == 'task'`.
- `worker.py::_task_due` (`:139-149`) correctly refuses to re-queue a guarded
  non-confined ERROR row for retry (`hold` only), while a confined (`'a6.1'`) ERROR
  row is allowed through to `retry`/`_retry_confined`. `retry()` in
  `verification.py` (`:335-354`) re-checks `confined()` against a freshly re-read
  execution before allowing the retry, so a race where `import_revision` changes
  between the worker's outer read and the write transaction is caught as `Refused`
  (handled by `pass_once()`'s race-log path), not silently accepted.
- `_confined_route()` (availability decided before any row starts, owner T-054 Q2 A)
  and `evidence.confined_argv()` were checked for the Windows `shutil.which`
  cwd-prepend quirk explicitly called out in the code's own comment
  (`evidence.py:76-79`): even though `which()` can resolve a program via a literal
  path or cwd lookup on Windows, the subsequent
  `os.path.dirname(os.path.abspath(found)) not in dirs` check rejects anything not
  physically inside one of the toolchain directories, and the resolved path is made
  absolute before it is ever used as `argv[0]`, so no further PATH search happens at
  spawn time. This closes the path-escape concern the comment itself raises.

**Minor / documentation gap (not a new defect, already called out by the author in
the card's own GAPS list, included here for completeness):** `record_task_verification`
and `verify_mission` in `application/work.py` have no A6/A6-4 concept whatsoever —
they will happily record a PASSED verification (with `verifier_version=None`) for a
task in a guarded mission if ever driven by something other than the engine's
injected stubs. Confidence: low severity, since the only caller is the P3.5 skeleton
engine with hardcoded stub verifiers; flagging only because "every path that creates
or updates a verification row" was asked for explicitly.

## 2. T-086 + T-085 (no-tools own calls) — `9afe908`, `08b899c`, `e7a9c31`

**Checked, no issue:**

- `archeus/harnesses/calls.py::ClaudeCodeCaller.call()` (`:91-100`) builds the
  no-tools `extra` tuple exactly as claimed: `--tools '' --strict-mcp-config
  --disable-slash-commands --setting-sources user --safe-mode`, and sets
  `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` / `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` on the env
  returned by `config.account_env()`. `account_env()` (`claude_sessions/config.py:891`)
  sets `CLAUDE_CONFIG_DIR` and pops `ANTHROPIC_API_KEY` per the `claude` harness's own
  `env_pops` table (`claude_sessions/harnesses.py:125`) — this part is pre-existing,
  unchanged by T-086, and correctly still applies.
- Argv is a Python list passed straight to `subprocess.Popen` (`llmcall.run_headless`,
  no `shell=True`), so the empty-string `--tools ''` argument is quoted correctly by
  CPython's own Windows `list2cmdline` (`""`), not hand-rolled — no quoting bug.
  `test_claude_with_no_tools_gets_an_empty_tools_list` /
  `test_claude_with_no_tools_also_drops_mcp_skills_project_settings_and_claude_md`
  assert the exact argv and env, via a real list equality / membership check, not a
  loose substring match.
- `PiCaller.call()` routes through `pi.headless_argv(exe, model, no_tools=...)`
  (`claude_sessions/pi.py:302-311`), which emits `['--no-tools', '--no-extensions']`
  instead of `['--tools', 'read,grep,find,ls']` — matches the card and the real-call
  verification recorded on T-085.
- Ordinary (non-`no_tools`) own calls are untouched: `extra` stays `()` in that
  branch, and `test_an_ordinary_claude_call_keeps_its_context` /
  `test_every_other_own_call_keeps_its_argv` assert the base argv/env set is
  unaffected.
- T-081's static gate (`tests/v1/integration/test_deputies.py`,
  `test_every_own_call_runs_in_a_fresh_directory_with_no_tools` and
  `test_every_own_call_and_nothing_else_asks_for_no_tools`) is a real AST walk over
  `archeus/` that enumerates every `no_tools=` keyword argument and every call through
  `OwnCalls.run`/`PASS_THROUGH`, not a hand-maintained list — it would fail if a sixth
  own call were added without `no_tools=True` and a fresh `workdir`. I did not find
  any own call site (decisions, lessons, brain, planner, review, retry) that bypasses
  it; the five named in T-081 plus review's shared `ask` dict (`worker.py:474-480`)
  all carry `no_tools=True` and `workdir=paths.fresh_call_dir`.

**Documented gaps, not new findings** (already named in the card's own notes, worth
restating since they bound what "no tools" actually means): whether `--tools ""`
also disables `Task`/subagent dispatch and whether Claude Code reads
`.claude/settings.json`/`CLAUDE.md` from directories *above* `ARCHEUS_HOME` are both
unverified; `init.plugins` still lists the account's installed plugins under
`--safe-mode` (nothing of theirs *ran*, per the recorded real-call evidence, but
whether they are unloaded or just inert is not established either way).

## 3. The four union merge resolutions

### `bebfe55` (T-055/T-056/T-061 A6 chain into `archeus/node/local.py`)

**Checked, no issue.** The merged import line
(`archeus/node/local.py:31-32`) pulls in the union of both sides' names
(`ExecPaths, VerifyPaths, archeus_home, processes_registry, repo_store, repos_dir,
run_dir, seed_staging, stop_sentinel`); I confirmed every one of the nine names is
actually referenced at least once elsewhere in the file (no stray unused import, no
missing one that would `NameError` at import time). `run_confined_check`
(`:639-671`) sits before the "K1: the Core-owned store" section comment (`:673`),
matching the commit message's description of the resolution, and it is a normal
method continuing the same `LocalNode` class on both sides of the seam — nothing
reads as spliced mid-class.

### `6bc0668` (T-078 long paths, `archeus/core/application/executions.py::refuse()`)

**Checked, no issue in the resolution itself**, but **found a pre-existing latent
bug one hop away that the merge's own stated scope ("check refuse() behaves right
for both K2's failure_class and T-078's BLOCKING/missions") makes directly relevant:**

- `refuse()` (`:185-207`) correctly merges both sides: `_respond(tx, actor, e,
  reason, failure_class)` then, when `stop_reason in BLOCKING`, `_block(tx, actor,
  missions, e.mission_id, reason)`. This is the resolution as described and it is
  correct in isolation.
- **Finding (minor, pre-existing — not introduced by this merge):**
  `archeus/core/application/executions.py::stop()` (`:483-489`) validates
  `stop_reason` against `entities.STOP_REASONS`, which (since `ada596c`, T-078's own
  commit) includes `'path_too_long'` — the one value in `BLOCKING`. But `stop()`
  calls `refuse(tx, actor=actor, execution_id=e.id, reason=reason,
  stop_reason=stop_reason)` **without** forwarding a `missions=` argument. If
  `stop()` is ever invoked with `stop_reason='path_too_long'`, `refuse()`'s
  `missions` parameter defaults to `None`, and `_block(tx, actor, None,
  e.mission_id, reason)` calls `missions._fire(...)` → `AttributeError: 'NoneType'
  object has no attribute '_fire'` instead of the intended "block the mission so it
  isn't re-dispatched" behaviour.
  - I verified this already existed in `ada596c` before T-072's merge (diff shown
    by `git show ada596c -- archeus/core/application/executions.py` — `stop()` is
    untouched by that commit), so the merge did not introduce it and did not drop
    anything; it is a gap in T-078 itself that the merge carries forward unchanged.
  - **Reachability today: low.** I traced every call site of `X.stop`
    (`archeus/core/execution/manager.py:309,511,516,704`) and the only caller that
    can pick `stop_reason='path_too_long'` is `manager.py:225`, which calls
    `X.refuse` **directly** (not through `stop()`) and does pass
    `missions=self.missions` — so production code never hits this path today. No
    API endpoint was found that lets a client choose an arbitrary `stop_reason`
    string reaching `executions.stop()`.
  - Confidence: medium-high that the bug exists as described (read the exact
    function bodies and signatures); low-medium that it is currently reachable by
    any real caller. Worth a one-line fix (`stop()` taking and forwarding
    `missions=None`) or an explicit comment/guard, since `STOP_REASONS` and
    `BLOCKING` are shared vocabularies and nothing stops a future caller of
    `stop()` from using `'path_too_long'`.

### `7685559` (T-080 short worktree layout, `archeus/infra/paths.py` docstring / `worker.py` imports / `test_verification.py`)

**Checked, no issue.** `worker.py` keeps `import sys` (used by
`toolchain()` → `sys.base_prefix`) and correctly drops the now-unused `import os`
(T-080 removed the only user, `_mission_wt`) — confirmed `os.` is not referenced
anywhere else in the file. `test_verification.py`'s two appended sections (T-062's
A6-4 tests, then T-080's) have no duplicate test names (51 `test_*` functions,
checked via `ast`, zero duplicates) and no shared fixture-name collisions that would
silently shadow one one side's setup.

## Commits/scope verified present

Spot-checked that the SHAs named in the card notes for these three resolutions
(`1738013`/`97797de`→`bebfe55`; `1dd19e0`/`ada596c`→`6bc0668`; `534f4cc`/`10ea156`→
`7685559`) match the actual merge parents in `git log`/`git show --stat` — no
mismatch between what the board claims and what is in the tree.

## Summary

| # | Item | Verdict | Severity |
|---|------|---------|----------|
| 1 | T-062 A6-4 sinks | No bypass found in any Verification-row writer | — |
| 1b | `work.py`/`ports.py` stub verifiers have no A6 guard | Known/documented gap, dead outside P3.5 skeleton | minor, informational |
| 2 | T-086/T-085 no-tools argv/env | Matches claims; argv quoting correct; static gate is a real AST walk | — |
| 3a | `bebfe55` local.py union | Clean union, no missing/unused names | — |
| 3b | `6bc0668` executions.py refuse() | Merge itself correct | — |
| 3b | `executions.stop()` drops `missions` for `path_too_long` | Pre-existing (ada596c), not a merge defect, currently unreachable in production | minor/latent, worth a follow-up fix |
| 3c | `7685559` paths/worker/tests | Clean, no duplicate tests, no unused imports | — |

No blocker-severity findings. One minor/latent correctness gap (3b) is flagged for
a follow-up card; it predates T-072's integration and was not introduced by any of
the merges reviewed here.
