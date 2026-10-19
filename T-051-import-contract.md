# T-051 · K3: import and no-import contract

Analysis only (Claude fork, 2026-10-13). The reviewed baseline is `5dfac53` in `D:\archeus-pv20-s2-l`, read with file reads and searches only. Candidate K1 (T-048, `D:\archeus-pv20-k1`, being corrected by another fork) is cited **CANDIDATE**: unreviewed, read only to name interfaces, relied on for nothing. Nothing was run: no Git, data walk, import or copy, no tests, processes or model requests, and no native, token, profile, ACL or registry API.

This note builds on T-030 and does not reopen it. Where it restates T-030, Correction C-1012-T030-2 (fence, one ordering) and T-049 including C-1013-T049 (byte core, exact maps) are the authority. Facts carry a citation; **CANDIDATE** marks a proposal; **UNKNOWN** marks something nobody has checked.

## 0. What this note does not do

- It enables no import, seed or project. T-027's refusal stands (`manager.py:367-374`), and K1-K6 stay unauthorised.
- It proves no closed Job and no tree quiescence. The fence below is the contract C-1012-T030-2 §1 approved; it exists in no code.
- It decides none of T-030 §3.3's owner questions. It recommends answers for Q2 (no import) and the import half of Q1 (links); the owner adopts or not.
- It does not cover no-project executions. They get no store, seed or import (C-1012-T030 §2), and under K4a their end facts are already "not measured" (`manager.py:558-559`, `:935`).

## 1. Today, at 5dfac53

- **No import exists.** A known-isolated execution's end records `files_changed` as one not-measured line and `end_state` None (`_unmeasured`, `manager.py:559`, `:935`), and so does the restart path (`:834`, `:840`).
- **Verification gets no revision from an isolated workdir.** `_verify_task` sets `revision`, `base` and `ws` to None when `e.isolated is True` (`worker.py:198-201`). `mergeable_revision` returns None when the row's execution or the verified execution is isolated True (`verification.py:114-127`). So an isolated task can be accepted by a person but never merged.
- **A pressure hand-off with no digest is refused as no progress and charged** (`executions.py:515-541`, `:559-579`; owner P1). An import supplies that digest; nothing else does.
- **The hand-off continuation is created inside `record_handoff`'s transaction** (`executions.py:580-581` → `handoff.py:22-56`). A refusal there makes the task READY uncharged (`handoff.py:48-53`).

## 2. Producer quiescence versus root exit: what Core can observe

| Signal | Observed today | Where |
|---|---|---|
| Root exit code | Yes, from Core's own child handle when Core launched it | `adapter.status` `child.poll()`, `claude_code/adapter.py:194-197` |
| Exit written durably | Yes, the `ended` tombstone, first thing after collection | `manager.py:551` |
| `killed` | Yes, only from Core's own stop record | `adapter.py:214-222`; `manager.py:571` |
| Root gone (identity view) | Yes, root only: Core's handle, or PID plus recorded creation time | `_process_state`, `isolation.py:891-917`; its docstring says descendants "are not looked at one by one" (`:897-898`) |
| Job membership / active processes | **No.** The Job's only limit is kill-on-close; no query primitive exists | `create_job` `:1646-1653`; `close_job` `:1680`; no `QueryInformationJobObject` anywhere in `archeus/` |
| Job held by this Core | Yes, `held_job` | `isolation.py:800-803` |
| After a Core restart | No Job is held; the old one closed when the old Core died | `_reconcile_isolated`, `manager.py:801-849` |
| Writers outside the Job under the execution's identity | **No** | not observable (C-1012-T030-2 §1, "demonstrated versus intended") |

**Consequence.** Root exit is observed; producer quiescence is not, today, by any means. The contract keeps C-1012-T030-2 §1's fence unchanged: after the root's exit is captured, Core reads the Job's active-process count through the handle it still holds (a new boundary primitive, K3), polls up to `EXIT_WAIT_S` (`isolation.py:509`), and imports only on zero; then it closes the Job. A survivor at the bound, a failed query, or no held Job means **no import**. Zero members does not prove no outside writer; that evidence stays with T-008 (C6), and K3's result is "implemented, not demonstrated".

## 3. The import read: bounded, non-following, root `.git` excluded

**Location.** The workspace is located only by `ExecPaths(e.id).work` (`paths.py:155`), derived from the id. `e.workdir` and `e.branch` are rewritten on each preparation (`executions.py:127-128`) and are never authority (T-049 §8).

**Walk** (CANDIDATE). One recursive walk by Core's own Python, never by Git and never with the workspace as any process's `cwd`:
- **Root `.git` excluded by name** at the top level only: the entry `.git` (case-insensitively) and its short form `git~1`. Nothing under it is opened. Nested `.git` is a link-policy case (§6).
- **Every entry is `os.lstat`-ed before use.** A reparse point (`st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT`), a symlink, or a file with `st_nlink > 1` goes to §6 and is never opened through. The same `_plain` test K1 uses for its store (`local.py:962-989` CANDIDATE), not a second one.
- **Open-then-verify.** A regular file is opened, `os.fstat`-ed, and its `(st_dev, st_ino, st_size)` must equal the lstat's, or the import refuses. This narrows a swap between check and read; it does not close same-user races.
- **Path rules:** the seed's validator, shared, not copied (T-049 §5: no `.`/`..`/empty component, no `\`/`:`/NUL/control character, no reserved device name, no trailing dot or space). Names must encode to strict UTF-8 (a lone surrogate refuses). Two paths equal under `casefold` refuse.
- **Empty directories** cannot be stored in a Git tree. They are dropped and counted in the import facts, never silently.
- **Ignore files are not parsed** (T-030 §3.2): everything except the root `.git` is imported, and the bounds catch bulk.

**Bounds**, checked while walking, before any byte is sent to Git (candidate values, set by the K3 card): entries ≤ 100,000; total bytes ≤ 2 GiB; depth ≤ 64; full path ≤ 259 characters; one deadline for walk plus write (candidate 300 s). The first breach stops the walk, kills any child, and means no import.

## 4. One pinned writer: what is K1, K2 and K3

**The writer** (CANDIDATE, mechanics **UNKNOWN**): one `git fast-import --done` process, run by K1's single spawner with `git_dir` = the store and `cwd` = the store, fed a stream Core generates:
- `commit refs/archeus/exec/<execution_id>/import`, Core's identity (`CORE_GIT_NAME/EMAIL`, `local.py:31`), a Core timestamp, and a message naming the execution id;
- `from <seed_revision>`, then `deleteall`, then one `M <mode> inline <path>` + `data <n>` per file, so the commit's tree is exactly the walked set;
- `done`, so a truncated stream aborts rather than commits.

Core hashes every blob itself while streaming (`b'blob %d\0' % n` + bytes, SHA-1, as T-049 C1 does on read). After the writer exits, Core reads `ls-tree -r -z -l <import>` back in byte mode and requires the map {path: mode, id, size} to equal the walk's exactly.

**Why one process.** The alternative, `hash-object -w --stdin` per blob plus `mktree` plus `commit-tree`, is N+2 spawns and an O(N) argv/stdin protocol; `hash-object` by path would let Git open workspace paths itself. Fast-import reads only Core's stream. Whether fast-import reads any store config beyond what K1's sealed store holds, and which temp files it leaves on a kill, is **UNKNOWN** (§10).

| Owner | Item |
|---|---|
| **K1 (T-048), unchanged, CANDIDATE** | `_store_pin`, the single spawner `store_git`, `_outside_executions`, `store_open`'s seal/pin-record/layout checks |
| **K2 (T-049 C1)** | the byte-mode core (no decode, chunked, killed on refusal, one deadline); Codex's r2 qualifications: stderr drained and capped too, reliable child and pipe cleanup, no publication on timeout |
| **K3 adds** | an `import` pin mode whose `_STORE_ARGS` row allows only `fast-import` (and `ls-tree`/`rev-parse` for the read-back, already `trusted`); the byte core's stdin-streaming direction (bounded, same deadline); the walk; the import facts |

Nothing in the execution's workspace is ever passed to Git as a path, so K1's refusal of `run/exec/*` paths stands unmodified.

**Modes** (CANDIDATE). The executable bit is never read from the execution's index or claims. A path present in `seed_revision`'s tree keeps that tree's mode (100644 or 100755); a new path is 100644. Mode 120000 and 160000 arise only from §6.

## 5. Record, transaction, crash, refusal, retention

**Parent and revision.** The import commit's only parent is the execution's own write-once `seed_revision` (T-049 §2), never the workspace's HEAD, index or refs. `Execution.import_revision` is a new body field (precedent `inventory_sha256`; 40 lowercase hex, matching the SHA-1-only candidate store), written **once**, only by the end transaction.

**Order** (C-1012-T030-2 §2, unchanged): exit captured → classification captured → fence → close → import → one durable transition → cleanup. Import runs only for the ENDED_OK and ENDED_HANDOFF routes. `record_end`/`record_handoff` gain `import_revision` and write it with the end in one transaction; `facts['end_state']` becomes the import commit's tree id and `files_changed` the store's `diff --stat seed_revision import_revision`, both computed by Core before the transaction.

**Ref.** `refs/archeus/exec/<id>/import` is created by fast-import's `commit` (CANDIDATE: a create-only guard, refusing if the ref already exists, is needed; whether fast-import offers one, or Core must check before and verify after, is **UNKNOWN**).

**Crash and lost race.**
- A crash or lost race after the ref exists but before the transaction leaves an import commit in the store that no row names. It is kept and **never canonical**: `import_revision` comes only from the row, and no reader ever lists `refs/archeus/exec/*/import` to find one.
- On restart, the end is resolved by `_reconcile_isolated` with no held Job, so the fence fails and there is no import, even though an orphan ref may exist.
- A second attempt for the same execution never happens: the end is recorded once.

**Refusal.** Any failure in §3 or §4 means `import_revision` None. It never changes the captured end state (C-1012-T030-2 §2 rules); what the task becomes is §7.

**Retention.** Keep-all: the workspace stays on disk after a successful import or a refusal; the store keeps the commit, its objects and refs; nothing is collected, pruned or deleted. Cleanup needs its own authorised card.

## 6. Links at import (separate from the seed)

The seed half is T-049's owner question (A: inert representation). The import half is separate, because at import the workspace is execution-written:
- **Symlinks, junctions, other reparse points**, at any depth: never followed (§3).
- **Hardlinked files** (`st_nlink > 1`): never read. A hardlink can make a file outside the workspace look like workspace content.
- **Nested `.git` or `git~1` directories** below the root: never descended.
- **What follows** is the owner choice (§11 Q1): refuse the whole import, or skip each entry and record it. Representing a link inertly (target text as a 120000 blob) would need the reparse target read (`os.readlink`, which covers symlinks and junctions on Windows since Python 3.8, **UNKNOWN** for other reparse tags) and is not recommended: a link's target is an execution claim, and a merged symlink is a hazard on the user's machine.

## 7. No import: recommended dispositions (owner decides; T-030 §3.3 Q2)

The no-import cases are: a survivor at the fence, a failed query, no held Job (every end resolved after a restart), a bounds breach, a link refusal (if §11 Q1 = refuse), and a writer or verification failure.

| Route | Recommendation | Why |
|---|---|---|
| ENDED_OK, no import | The task cannot be verified or merged. Treat it as a **charged** failed attempt (`charged_failure` with a new failure class `import`, `executions.py:381`): `execution_failed_retry` while attempts remain, else `execution_failed_final` → replan. | Fail closed and bounded by `max_attempts`; no person is asked to accept work nobody can merge |
| ENDED_HANDOFF, no import | Create **no continuation** (seeding it from the predecessor's seed would silently drop its work). The hand-off ends, and the task takes the same charged route as ENDED_OK | One rule for both routes; the existing `continue_task` refusal shape (`handoff.py:48-53`) already ends a hand-off without a continuation |
| Accounting | Usage is ledgered as today (`_ledger`, `executions.py:566`); `charged` follows the row above; the reason text names the no-import cause | Spent tokens are spent |

**The alternative the owner may prefer:** charge only causes the execution controls (survivor, bounds, links) and leave Core causes (restart, query failure, store error) uncharged. That needs a separate bound on uncharged retries, because a Core that keeps restarting would otherwise retry forever. Not recommended for the first cut.

**Retry base** after no import: T-049 §2's rule already covers it (the latest earlier import, else that attempt's own seed), so the next attempt redoes the lost work from the last Core record.

## 8. What changes downstream (not K3's code)

- **K4b:** hook context and the branch gate use Core records (`manager.py:496-497` fails every hook of a known-isolated execution with a recorded branch today; T-049 §7).
- **K5:** verification takes `revision = e.import_revision` and `base = seed_revision`; `mergeable_revision` must accept a row whose `revision` equals its execution's `import_revision` even when that execution is isolated True. That changes T-042's rule (`verification.py:125`), so it is K5's, under review, not K3's. Command checks stay withheld until A6 (`unconfined`, `verification.py:102`).
- **Pressure (P1):** with an import, `end_state_digest` is the import tree id, so an isolated pressure chain can show progress; without one, P1's charged stop stands.

## 9. Manifest (proposed; authorises nothing)

| Kind | Files |
|---|---|
| **Code** | `archeus/node/isolation.py` (fence primitive and teardown split, per C-1012-T030-2 §3); `archeus/core/execution/manager.py` (`_collect` order; `_reconcile_isolated` keeps no import); `archeus/core/application/executions.py` (`record_end`/`record_handoff` take `import_revision`, write-once, the §7 disposition); `archeus/core/domain/entities.py` (`Execution.import_revision` and its check); `archeus/node/local.py` (`import` pin mode, walk, stdin byte streaming) |
| **Fake tests** | `tests/v1/unit/test_pv20_isolation.py`: fake boundary counts (above zero to the bound, zero after polls, query raises, no held Job) and a call recorder for exit → fence → close → import → transaction → teardown. `tests/v1/unit/test_execution_units.py`: write-once `import_revision`, lost race leaves the ref unrecorded, each §7 row. `tests/v1/unit/test_repo_store.py`: walk bounds, path rules, casefold collision, open-then-verify mismatch, link cases, pin argv, all with zero spawns |
| **Owned-temp real Git** | `tests/v1/integration/test_repo_store.py`: a hostile workspace (`.git/config` with fsmonitor and a filter, `.git/hooks/*`, `.gitattributes`, `.gitmodules`, `.lfsconfig`, `refs/replace/`) leaves every sentinel uncreated, and the import tree's bytes equal the files written; NUL and invalid-UTF-8 content round-trips; a fast-import killed mid-stream leaves no ref, and the next `store_open` behaves as recorded (§10) |
| **Native, not authorised** | the fence's `QueryInformationJobObject` read on Windows and any demonstration of tree quiescence: T-008 (C6) only |

**Dependencies:** K1 reviewed; K2 (seed, `seed_revision`, byte core); C-1012-T030-2's fence accepted for implementation; T-030 §3.3 Q1 (import half) and Q2; K4b and K5 before any isolated project result is verifiable or mergeable; K6 plus the owner's go for enablement. K2 and K3 both edit `entities.py`, `executions.py` and `local.py`, so they run one after the other.

## 10. Unknown

- Fast-import: whether it reads store config beyond the sealed set, its behaviour on `--done` with a truncated stream, a create-only ref guard, and the files a kill leaves (crash report, `tmp_pack_*`). Candidate K1's `_layout` only alias-checks unknown top-level and pack entries (`local.py:974-982` CANDIDATE), so debris would not block the store; whether it should is K3's test.
- That the computed SHA-1 per blob equals fast-import's, for every content (recalled, not checked).
- Windows: `fstat` identity fields under Python 3.10, long paths, `os.readlink` on non-junction reparse tags.
- The fence primitive's behaviour, and every quiescence claim (T-008).
- Same-user writers outside the Job between fence and read: narrowed by §3, not closed.

**No hostile-content confinement claim.** Core reads execution-written bytes and Git parses them into objects in Core's unconfined process.

## 11. Owner questions

1. **Links at import (T-030 §3.3 Q1, import half).** (A, recommended) Refuse the whole import when the walk meets a reparse point, symlink, hardlinked file or nested `.git`: no import, §7 applies. (B) Skip each such entry and record it in the import facts, importing the rest. A partially imported tree can then pass verification without the skipped files.
2. **No import (T-030 §3.3 Q2).** (A, recommended) §7's table: a charged failed attempt with failure class `import`, the same for ENDED_OK and ENDED_HANDOFF, no continuation without an import. (B) Charge only execution-caused cases, with a new bound on uncharged retries.
