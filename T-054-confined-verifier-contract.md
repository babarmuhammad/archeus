# T-054 · A6 confined-verifier contract

Claude (fork), 2026-10-13. Analysis only. Read-only at reviewed baseline `5dfac53` (`D:/archeus-pv20-s2-l`); nothing was run, built, granted, copied or probed. The K1 candidate in `D:/archeus-pv20-k1` and the sibling notes T-050 (broker) and T-053 (origin) are cited only as dependencies, never as evidence. Tags: **[CODE]** read at `5dfac53`; **[ADR]** ADR-0053 text; **[CAND]** proposed here; **[UNK]** unknown, needs evidence.

## 0. What this note does not do

It authorises no code, no native call, no grant, no activation and no change to the interim T-042 guards. It does not choose the toolchain, network or missing-verifier policy (§8). It does not make the confined verifier the route for ordinary missions; that switch is part of activation, a separate owner go.

## 1. The decision being implemented, and where the code stands

**[ADR]** R4b (ADR-0053:80-94) and A6 V-1 (:250-266):
- every verification gets a fresh verifier principal, distinct from the user and every execution, for one verification, never reused, destroyed after Core records the result;
- it runs in its own Core-held Job, on its own Core-materialised checkout of the Core-recorded revision (:239-240), with its own scratch, home and temp;
- it has no user, provider or broker credential, local or hook token, mailbox, Core database or state, Core route, execution repository or import repository;
- its maximum authority is a subset of the execution's runtime/tool grants, plus its checkout and scratch, with network only if P23 allows;
- a check that needs more is missing evidence, ERROR or AWAITING_HUMAN, never PASSED (:265-266, :315-316).

Left undecided by the ADR (:317-318, :421-429): ERROR versus AWAITING_HUMAN for a missing verifier, the exact toolchain grants, dependency provisioning, and network for verification (P23).

**[CODE] As built, no command check is confined.**
- `evidence.run_commands` (`evidence.py:65-91`) calls `node.run_check` (`local.py:490-524`). That is a plain `Popen` in the workspace with Core's whole environment minus `PYTEST_*` (`:499-500`), as the user.
- T-042's interim guard keeps it off any mission with an execution that is not exactly ordinary:
  - `unconfined` (`verification.py:102`);
  - the start sink (`:193-195`) and the retry sink (`:329-330`);
  - the `WITHHELD` reason (`:39-40`) and `hold` (`:337-346`);
  - the worker (`worker.py:197-208`, `:251-255`, `:328-339`);
  - `mergeable_revision` (`verification.py:114`).

  This contract keeps every one of these.

## 2. What already exists to reuse (one mechanism, not a second framework)

| Need | Existing mechanism | Gap for a verifier |
|---|---|---|
| Per-principal identity | `Isolation.establish` / `_establish` (`isolation.py:669-757`), `WindowsBoundary.create_profile` (`:1576-1596`), zero capabilities (`:67`) | Keyed on an execution id only: `validated_profile` requires `ids.is_id(…, 'execution')` (`:108-113`), `profile_name` uses `archeus.exec.` (`:75`, `:87-91`), and `isolation_state` takes execution ids only (`paths.py:108-113`) |
| Core-only Job, kill-on-close | `_ensure_job` / `held_job` (`isolation.py:791-803`), `create_job` (`:1646-1664`) | Sets `KILL_ON_JOB_CLOSE` only (`:1653`); no process, memory or time limit |
| Confined launch, Core-held stdio | `IsolationContext.launch` (`:1180-1221`), `open_inherited` (`:1925-1936`), `launch` (`:1938`, created suspended, assigned, resumed) | Takes `ExecPaths` (prompt, stream); a verifier needs an output file and an empty stdin |
| Pre-spawn invariant | `check_invariant` (`:175-263`), `CONDITIONS` (`:120`) | Conditions 2 and 5 require the execution's mailbox rows and a broker (`REQUIRED_GRANTS` `:126`, `CLASS_ROWS` `:131`); a verifier must have none of them |
| Teardown, quarantine, boot reclaim | `teardown` (`:817-842`), `quarantine` (`:965`), `reclaim` (`:1020`), `is_stale_profile` (`:94-95`) | Prefix and id kind as above |
| Registry line for the item-83 stop | `Isolation._note` → `node._registry` (`isolation.py:619-624`, `local.py:148`) | None |
| Built-from-nothing environment | `_isolated_env` (`base.py:408-472`), `_profile` (`:386-389`), `_inside` / `_absolute` (`:392-405`), `CAPABILITY_ENV` | Carries `ARCHEUS_EXECUTION_ID`, `ARCHEUS_HOME` and hook names (`:426`, `:448-449`); its PATH is an unverified narrowing of Core's own (`:414-416`, `:438-446`) |
| Runtime as a Core copy | `staging.stage` / `verify` (`staging.py:203`, `:216`) | Stdlib only: `site-packages` is in `SKIP` (`:28`), so no test runner ships (§6) |
| Check contract and verdict | `run_commands`' result shape (`evidence.py:80-90`), `V.record` (`verification.py:220-268`), `verdict_of` | None. The confined path returns the same dict |
| Crash recovery | `V.sweep` (`verification.py:438-450`: RUNNING → ERROR `core_restarted`) | None |
| Fresh checkout | K2 seed builder (T-049 §4 steps 1-6 and C-1013-T049 byte mode), on K1 | Built for an execution workspace with a `.git`; a verifier needs a tree-only variant (§4) |

## 3. The verifier principal

**[CAND] Identity per run attempt, not per row.**
- `V.retry` re-runs the same row (`verification.py:331-334`). A6 says a principal serves one verification and is destroyed once its result is recorded. A retry therefore gets a new principal.
- The name is derived, never taken from a caller or a record: `archeus.verify.<verification_id>.<n>`, where `n` is the row's `errors` count when the run starts. That count is durable and only grows (`:258`), so no name recurs.
- The record lives at `run/isolation/verify/<verification_id>.<n>.json`: Core-owned state, outside every verifier-writable directory.

**[CAND] Generalising, not duplicating.**
- `validated_profile` / `profile_name` / `isolation_state` / `is_stale_profile` gain a kind (`'execution'` | `'verification'`), with an exact prefix and id check per kind.
- `IsolationRequest` gains `kind`. `check_invariant` keeps all six conditions, with different content for a verifier:
  - **grants:** exactly `checkout` rw, `scratch` rw and `toolchain` rx;
  - **mailbox inverted:** no mailbox, response, sentinel, spawn configuration or broker named, and `core_state` ungranted;
  - **no_broad_grants, job, isolated_path, identity:** as today.
- An execution request is untouched. A test asserts the two kinds cannot name each other's profile.

**[CAND] Never the parent's identity.** The verifier's profile name and SID are derived from the verification id. They never equal or contain the execution's (`archeus.exec.<eid>`). A test derives both and asserts the SIDs differ and that neither record names the other.

## 4. Canonical input and fresh state

**Input.** The run binds to Core's record, never to a workdir.
- **Task rows:** the revision is the execution's Core-recorded `import_revision` (T-030 C6, built by K3), and the checkout is Core's materialisation of that revision from Core's store.
- **Mission rows:** the revision is `m.integration_head` (`verification.py:187-189`), but only once that commit is in Core's store. Today it exists only on the user's mission branch, and reaching it needs either the K1 `store_fetch` (test-gated) or the store-side merge (T-030 Q9). Until then a guarded mission's criteria stay human, as T-042 already makes them (`worker.py:338-339`).

**[CAND] Tree-only checkout.**
- K2's step 4 (Core writes blob bytes as data, with exclusive create) and its bounds and path rules (T-049 §5, C-1013-T049 §1-§2) produce the tree, without K2's `.git` skeleton or index.
- Built in a Core-private staging directory, verified entry by entry against the manifest, then renamed into `run/verify/<vid>/<n>/own/checkout`. K1 refuses every Git path under `run/`, so no Git ever runs in the verifier's directory.
- No `.git` means nothing Git-shaped executes for the verifier. A project test that needs Git fails or errors, which is evidence, never a PASSED.

**[CAND] Layout**, per attempt, under `run/verify/<vid>/<n>/`:
- **Core-owned, never granted:** `out.log` (the output file), the attempt's record, and the parent directory itself.
- **Verifier class 7:** `own/checkout` (rw), plus `own/home`, `own/tmp` and `own/config` (rw, scratch).
- The existing `run/verify/<vid>/<i>.log` of `evidence.py:69-78` moves under the attempt.

**[CAND] Environment.**
- A new `_verifier_env(paths, toolchain)` is built from the same pieces (`_profile`, `_inside`, `_absolute`, `CAPABILITY_ENV`, the `SystemRoot` checks of `base.py:429-437`): HOME, USERPROFILE, APPDATA, LOCALAPPDATA, TEMP and TMP point into scratch.
- **Absent by construction:** every `ARCHEUS_*` name (ARCHEUS_HOME included), `CLAUDE_CONFIG_DIR`, every hook name and every provider variable.
- **PATH** holds only the granted toolchain directories, never a narrowing of Core's PATH.
- Unlike `_isolated_env`, it takes no request map, so no caller can add a name.

## 5. Budgets, evidence channel, lifetime

**[CAND] Budgets**, each a refusal or an `error` check, never a pass:
- **Tree:** K2's manifest bounds on the checkout, before any write.
- **Wall time:** `CHECK_TIMEOUT_S` (`evidence.py:17`). On expiry Core closes the Job, which kills the tree (`teardown` `isolation.py:830-832`), and records `timed out`.
- **Job limits:** active-process, job-memory and per-job CPU-time limits on the verifier's Job, through the same `SetInformationJobObject` call `create_job` already makes (`:1654-1656`). **[UNK]** The exact limit flags and their observed behaviour need the native card.
- **Output and scratch:** `run_check` keeps a 256 KiB tail (`local.py:33`) but lets the file grow without bound. The candidate is Core polling the size of `out.log` and scratch during the run and closing the Job past a cap. **[UNK]** The overshoot is bounded only by the polling interval; no stdlib quota exists, and NTFS quotas need admin.

**[CAND] Evidence channel.**
- `stdout` and `stderr` are one Core-opened handle to `out.log`, made inheritable for that one `CreateProcessW` only (`open_inherited` plus `launch`'s handle list). `stdin` is a Core-opened empty file.
- The exit code comes from the process handle Core holds.
- The check dict is `run_commands`' shape (`evidence.py:80-90`), plus `confinement: IsolationContext.facts()` (`isolation.py:1224-1230`: profile, SID, zero capabilities, Job kind). The confinement facts live inside `checks` and need no schema change.
- **Dropped on this path:** the post-run `git_head` / `git_dirty` check (`worker.py:229-233`). It would run Git in a verifier-written directory, which A5 forbids, and it is unnecessary because Core materialised the input and discards the directory.
- `changes` stays K5b's data-only diff in the store (T-041 §8).

**[CAND] Order of one attempt:**
1. The sink starts the row (RUNNING).
2. Core materialises the checkout and establishes the principal.
3. The six-condition invariant is checked; then launch, wait and capture.
4. `V.record`.
5. Teardown: close the Job, delete the profile.
6. A profile that will not go is quarantined (`isolation.py:965`) and is never re-derivable for another attempt. Record-then-teardown means a teardown failure never changes a recorded verdict.

**Retention.** The checkout and scratch are kept: keep-all, matching T-049. A delete of a verifier-written tree must not follow junctions, and this note grants no cleanup. **[UNK]** Python 3.10 `shutil.rmtree` and junctions; a later cleanup card should use a non-following walk, as `staging._tree` does (`staging.py:172-200`).

**Restart.** The Job dies with Core (R6-A, `isolation.py:5-9`). `V.sweep` marks the row ERROR (`core_restarted`). `reclaim` removes stale `archeus.verify.*` profiles once the prefix is known to it. Nothing is re-adopted.

## 6. Authority: what the verifier can and cannot do

- **Can:** read and write its checkout and scratch, execute from the toolchain grant, and write to its one output handle.
- **Cannot:**
  - read Core state (`run/isolation`, the database, `run/exec/*`, other attempts): ungranted, and checked by condition 3;
  - reach a network: zero capability SIDs (`isolation.py:67`, `:71`), with P23 owning any change;
  - reach a Core route or a token: none is in its environment, and R1-A/A3 (T-053) refuses verifier-originated requests anyway;
  - reach the execution's repository or Core's store.
- **[UNK] Grants are not applied by anything today.** S1 applies no ACE (`isolation.py:12-14`); grant application is S2-G, under its own authorisation (CLAUDE.md, T-052). An AppContainer cannot read its own checkout without an ACE, so any real verifier run depends on S2-G exactly as an execution does. **Never a grant on a shared tree**, such as the user's Python install or a repo root (the 2026-10-08 incident).
- **Toolchain.** The only Core-staged runtime is stdlib Python with no `site-packages` (`staging.py:26-31`). Most real checks (`pytest`, `npm test`) therefore have no runner inside the boundary and come out `error`: missing evidence. Granting the user's installed toolchains is excluded (no ACL on shared trees). Provisioning is owner question 1.

## 7. Interim guards preserved, and how a confined row enters

**[CAND] The marker is the existing frozen `verifier_version`** (`VERIFIER_VERSION` `verification.py:31`). `start` sets `'a6.1'` on a confined code row. No new field, state or table is added.

**[CAND] Sink rules:**
- **`start`:** a guarded mission still refuses every non-human verifier (`:193-195`) unless all of these hold:
  - the call names a confined run (`verifier_version='a6.1'`);
  - the subject is a task whose execution has a Core-recorded `import_revision`, and `revision` equals it;
  - `workspace` is None.
- **`retry`:** for a guarded subject it refuses as today (`:329-330`) unless the row's frozen `verifier_version` is `'a6.1'`.
- A legacy frozen code row stays held, never relabelled (T-041 C2). Both sinks stay the linearisation points.

**[CAND] Worker routing.**
- `_verify_task` takes the confined path only when every one of these holds; otherwise it keeps today's human route (`worker.py:209-215`) with the `WITHHELD` reason:
  - the subject is guarded;
  - the confined verifier is available;
  - the platform check passes;
  - the toolchain resolves;
  - `import_revision` exists.
- `_retry` keeps its RUNNING gate (`:254-255`).
- Unguarded missions keep today's unconfined `run_check` until activation.

**Merge.** `mergeable_revision` (`verification.py:114`) still refuses an isolated row. Accepting an `import_revision`-backed PASSED row as mergeable is K5b's, not A6's.

## 8. Cards (each small; none authorised by this note)

| Card | Files | Checks | Depends on |
|---|---|---|---|
| **A6-1** identity by kind | `node/isolation.py` (kind on profile name, record path, stale prefix, `IsolationRequest`, `check_invariant` conditions 2 and 5), `infra/paths.py` (`VerifyPaths`, `isolation_state` by kind) | Fake boundary in `tests/v1/unit/test_pv20_isolation.py`: names never cross kinds; a verifier request with a mailbox, broker or hook row fails condition 5; one missing checkout, scratch or toolchain row fails condition 2; reclaim sees both prefixes; the execution path is unchanged | — |
| **A6-2** verifier environment | `harnesses/base.py` (`_verifier_env`) | Unit: no `ARCHEUS_*`, `CLAUDE_CONFIG_DIR`, hook or provider name; PATH is toolchain-only; scratch HOME/TEMP; no caller-supplied names | — |
| **A6-3** confined run | `node/isolation.py` (`run_confined`: establish, launch with an output handle and empty stdin, deadline closes the Job, output/scratch cap poll, facts), `node/local.py` (`run_check` contract unchanged; a confined sibling delegates) | Fake boundary and fake process: run_check result shape; timeout closes the Job; cap kills; record-then-teardown ordering; teardown failure quarantines and leaves the verdict; zero launches when any condition is unmet | A6-1, A6-2 |
| **A6-4** routing and sinks | `application/verification.py` (`start`/`retry` confined rule on `verifier_version`), `verification/worker.py` (`_verify_task`/`_retry` confined path, no post-run Git), `verification/evidence.py` (materialised checkout argument) | `tests/v1/integration/test_verification.py` with a fake confined runner: a guarded task with `import_revision` runs confined, a PASSED row is marked `'a6.1'`, a legacy frozen row is still held, guarded without an import goes human, retry gets a new attempt name, and all T-042 7a-7g tests are unchanged | A6-3, K3 `import_revision`, K2 tree-only export on K1 |
| **A6-5** native evidence | `create_job` limit flags; one real verifier run on a synthetic project in pytest temp with the staged stdlib runtime | Token is an AppContainer with zero capability SIDs; cannot read `run/isolation`, the DB or `run/exec`; output captured; deadline kill; memory/process limit observed; profile gone after teardown | **Owner auth** for the native run; S2-G grant application; never a shared tree |

Activation (routing unguarded missions through A6, retiring the unconfined `run_check`, mission criteria) is a separate owner go after A6-5, K3 and K5b.

## 9. Unknowns

- Job limit flags and their behaviour for a real test runner's process tree, and whether a polled output/scratch cap bounds a fast writer: native card only.
- Whether an AppContainer with only S2-G's ACEs can run a staged Python and write its checkout without further capabilities.
- Python 3.10 `shutil.rmtree` on a verifier-planted junction.
- How many real projects' checks pass with no `.git` and no third-party runner (most will not, by design, until question 1 is answered).
- The K1 candidate is unreviewed. K2/K3 are contracts, not code.

## Owner questions

1. **Toolchain for verification** (ADR "not decided": toolchain grants, dependency provisioning).
   - **A (recommended):** the first cards use Core-staged runtimes only (today stdlib Python). Checks needing anything else are missing evidence, so a guarded task goes to a human as it does now. Nothing new is copied or granted.
   - **B:** add a Core-staged, content-addressed per-project toolchain (venv packages, node/npm), copied like `staging.stage` and never granted in place. It is a new mechanism and its own card, needing a decision on what may be copied from where.
   - **Granting the user's installed toolchains in place is not offered** (no ACL on shared trees).
2. **Missing or unavailable confined verifier** (ADR :317, open).
   - **A (recommended):** decide availability before `start`. If unavailable, take today's T-042 human route with the A6 reason, so no row errors and nothing retries a structural absence.
   - **B:** start the row and record an `error` check, so the retry then hold of `ERROR_ATTEMPTS` (`verification.py:33`) applies. Costs a retry that cannot succeed.
