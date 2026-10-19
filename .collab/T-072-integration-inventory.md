# T-072 · Integration inventory (coordination only)

Claude (fork), 2026-10-14. Owner: "T-072 inventory (Recommended)". Read-only git only: `rev-parse`, `log`, `diff --name-only`, `show`, `patch-id`, `range-diff`, `cherry`, `branch --contains`, `cat-file`, and `git merge-tree --write-tree` dry runs (git 2.49.0.windows.1). merge-tree writes tree and blob objects into the object store but no ref, index, worktree or commit. No checkout, cherry-pick, commit, test or BOARD edit. **Integration itself stays proposed and unauthorised.**

Target base: frozen S2 `5dfac53f0724a80417bdd5196e7986f5752bb132` (branch `pv20-s2`, also on `origin/pv20-s2`).

## 0. Heads verified (`git -C <checkout> rev-parse HEAD`, all `status --short` empty)

| Card | Checkout | Head (full) | Card status at check |
|---|---|---|---|
| T-048 K1 | D:/archeus-pv20-k1 | d92da8adcb9c3627e4bc564d5afb77f63454331c | done (APPROVE d92da8a) |
| T-066 K2 | D:/archeus-pv20-k2 | 82b53a73e59a06bacfdde1e3c092ea3a3a3121e2 | review (r1 correction; last verdict CHANGES on 7c6fe3b) |
| T-055 A6-1 | D:/archeus-pv20-a61 | faecc6a783201085b545b50898e767f5abfe6858 | done (APPROVE faecc6a) |
| T-056 A6-2 | D:/archeus-pv20-a62 | 7f76ecb973c912976e59e216a23010108334ff99 | done (APPROVE 7f76ecb) |
| T-061 A6-3 | D:/archeus-pv20-a63 | 97797de22d42d52b51c91ec8e04d8586184cef81 | review (r1 correction; last verdict CHANGES on c2cbdde) |
| T-057 K-O1 | D:/archeus-pv20-ko1 | f334113c2ada820601ac31a6e02f4336ef877ccd | done (APPROVE) |
| T-058 K-O3 | D:/archeus-pv20-ko3 | 743836f59c4c1fc7af6897ab5afe8ccddd3b993c | done (APPROVE) |
| T-059 R1-A | D:/archeus-pv20-q4 | 606d5b60eed8b30677ea40dfda301ae8768cbe6a | done (APPROVE) |
| T-070 R1-A compat | D:/archeus-pv20-q4-compat | dcbc848de9067ff4469271fba33b1f8d812c7e1b | done (APPROVE, file T-070-606d5b6.md) |
| T-060 K-O2 | D:/archeus-pv20-ko2 | aaddefd1275fd48483837829c70874690e002c50 | review (r1 correction; last verdict CHANGES on e95bd2d) |
| T-069 own-call routing | D:/archeus-pv20-call-route | cece71d89acbc01d74b9a39b02d2ab1432ede0e9 | review (no verdict yet) |
| T-073 CI fixes | D:/Claude | 3257dd0b6c181f7563c94015a8c6f3c1bced3848 | review (no verdict yet) |

Not inventoried: T-067 K3 (D:/archeus-pv20-k3, at 82b53a7 with no own commit yet, in progress); T-074 (D:/archeus-pv20-q4-parity, `a430301` on dcbc848, touching only `clients/app/test/fixtures/parity-inputs.mjs` and `parity.json`; appeared during this check, not dry-run).

## 1. Manifest: each card's own commits (oldest first), excluding inherited bases

| Card | Parent of first own commit | Own commits (full SHA) | Depends on |
|---|---|---|---|
| T-048 K1 | S2 5dfac53 | de726ced19a57add189643b3baed850c706c82bc, c06113f0a43cb87d002717e25927b97adf7f1ca0, c3f10697e4239a1ba6c7db01aea935de5d1bdfd4, 4d1a91b76197723653f3b8899c8430cbcb4fa7e9, 33b639fd5c251fca306a6547797f33aa00290d2e, 0c1b49e2a2271f02ec77beb55c9368be37d02565, d92da8adcb9c3627e4bc564d5afb77f63454331c | S2 |
| T-066 K2 | d92da8a (K1) | a38e6c233ee52075fa11537f54185849b31ccb04, de1ce06e433df7f6dc6e999df96f0faffc1ff79e, 7c6fe3b2ff73bf40491309ce7aabf8ba6e39facb, bf24bde81da79f19ee78abe4c921e3b70439dab6, 82b53a73e59a06bacfdde1e3c092ea3a3a3121e2 | K1 |
| T-055 A6-1 | S2 5dfac53 | b50672b2ec577b7e594e0eb1b5e7b4358b14cceb, faecc6a783201085b545b50898e767f5abfe6858 | S2 |
| T-056 A6-2 | S2 5dfac53 | 7f76ecb973c912976e59e216a23010108334ff99 | S2 |
| T-061 A6-3 | b50672b (T-055 r0) | own: c2cbdde913cef8aabe428acd441fba9d357bbcdc, 97797de22d42d52b51c91ec8e04d8586184cef81. Chain also carries fc23c2fb865dcd4cebd40d86e115510ac3137719 (= T-056) and 448cdc76061464708929f997f55003246e2b8ea9 (= T-055 r1) | T-055, T-056 |
| T-057 K-O1 | S2 5dfac53 | f334113c2ada820601ac31a6e02f4336ef877ccd | S2 |
| T-059 R1-A | f334113 (T-057) | 606d5b60eed8b30677ea40dfda301ae8768cbe6a | T-057 |
| T-070 R1-A compat | 606d5b6 (T-059) | dcbc848de9067ff4469271fba33b1f8d812c7e1b | T-059 |
| T-058 K-O3 | S2 5dfac53 | 743836f59c4c1fc7af6897ab5afe8ccddd3b993c | S2 |
| T-060 K-O2 | S2 5dfac53 | 475ed39941153aadb7d19b3a33315f721c6e6e89, e95bd2dc9a8db8420fa25ad136a1e13772a8eed7, aaddefd1275fd48483837829c70874690e002c50 | S2 |
| T-069 | e95bd2d (T-060 r1 head) | cece71d89acbc01d74b9a39b02d2ab1432ede0e9 only (475ed39 and e95bd2d are T-060's, inherited) | T-060 up to e95bd2d |
| T-073 | f6abc4d | 3257dd0b6c181f7563c94015a8c6f3c1bced3848 | **not on S2** (see §6.5) |

**Duplicate cherry-picks, checked by `git patch-id --stable` and `git range-diff`:**

- `7f76ecb` (T-056, APPROVED) and `fc23c2f` (inside the T-061 chain): patch-id `37a40842ec843f62` for both; range-diff `7f76ecb = fc23c2f`. Same change.
- `faecc6a` (T-055 r1, APPROVED) and `448cdc7` (inside the T-061 chain): patch-id `400f2fe92861af07` for both; range-diff `faecc6a = 448cdc7`. Same change, applied on a different parent (c2cbdde rather than b50672b).

**Which to take:**
- If T-061 is accepted, take its chain head `97797de`, which carries both copies. Do not also merge `faecc6a` or `7f76ecb`.
  - Merging `faecc6a` on top conflicts. §4 has the result: 97797de rewrites the admission line that faecc6a adds.
  - The approvals are on `7f76ecb`/`faecc6a`. Their identical patches `fc23c2f`/`448cdc7` carry them only if Codex or the owner accepts the patch-id equivalence. Record that explicitly; don't assume it.
- If T-061 isn't accepted, take `faecc6a` and `7f76ecb` (the approved SHAs), and leave the A6 chain out.

## 2. File-by-card matrix (`git diff --name-only <parent> <head>` per card; T-061 = fc23c2f..97797de, T-069 = e95bd2d..cece71d)

`**` = touched by two or more cards in this inventory.

| File | K1 | K2 | T-055 | T-056 | T-061 own+448cdc7 | T-057 | T-059 | T-070 | T-058 | T-060 | T-069 | T-073 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| archeus/infra/paths.py ** | x | x | x | | x (448cdc7) | | | | | x | | |
| archeus/node/local.py ** | x | x | | | x | | | | | x | | |
| archeus/node/isolation.py ** | | | x | | x | | | | | | | |
| archeus/harnesses/base.py ** | | | | x | | | | | | x | | |
| archeus/core/calls.py ** | | | | | | | | | | x | x | |
| archeus/harnesses/calls.py ** | | | | | | | | | | x | x | |
| tests/v1/integration/test_knowledge.py ** | | | | | | | | | | x | x | |
| archeus/api/server.py ** | | | | | | x | x | x | | | | |
| tests/v1/unit/test_api_origin.py ** | | | | | | x | x | x | | | | |
| tests/v1/integration/test_repo_store.py ** | x | x | | | | | | | | | | |
| tests/v1/unit/test_repo_store.py ** | x | x | | | | | | | | | | |
| tests/v1/unit/test_pv20_isolation.py ** | | | x | | x (448cdc7) | | | | | | | |
| archeus/core/application/executions.py | | x | | | | | | | | | | |
| archeus/core/domain/entities.py | | x | | | | | | | | | | |
| tests/v1/unit/test_execution_units.py | | x | | | | | | | | | | |
| docs/architecture/target-architecture.md | x | | | | | | | | | | | |
| tests/v1/unit/test_verifier_env.py | | | | x | | | | | | | | |
| tests/v1/unit/test_confined_run.py | | | | | x | | | | | | | |
| archeus/api/auth.py, archeus/api/routes.py | | | | | | x | | | | | | |
| tests/v1/integration/test_presence.py, tests/v1/judge/conftest.py, tests/v1/judge/http.py | | | | | | | x | | | | | |
| archeus/cli/tui/sync.py, clients/app/src/data/commands.ts, clients/app/test/commands.test.ts, tests/v1/e2e/conftest.py, tests/v1/e2e/test_unification.py | | | | | | | | x | | | | |
| tests/v1/unit/test_hook_mailbox_origin.py | | | | | | | | | x | | | |
| archeus/core/knowledge/passes.py, tests/v1/integration/test_deputies.py | | | | | | | | | | x | (inherited only) | |
| archeus/core/application/resources.py, archeus/harnesses/fake.py, tests/v1/unit/test_own_call_no_tools.py | | | | | | | | | | | x | |
| tests/v1/e2e/test_spa_command_close.py, test_spa_estop_about.py, tests/v1/integration/test_account_protection.py, test_dev_launcher.py, test_stream_takeover.py | | | | | | | | | | | | x |

The overlaps inside one chain are sequential by construction: K1→K2, T-057→T-059→T-070, T-060→T-069 and T-055→T-061. The cross-chain overlaps are `paths.py`, `local.py`, `isolation.py` and `harnesses/base.py`.

## 3. Dependency-aware order (proposal)

1. K chain: `82b53a7` (K1 + K2). If K2 is not accepted, use `d92da8a` (K1 alone).
2. A6 chain: `97797de` (T-055 r0 + T-056 + T-061 + T-055 r1). If T-061 is not accepted, use `faecc6a` then `7f76ecb`.
   - **This step is where the only real conflict occurs** (§4).
3. R1-A chain: `dcbc848` (T-057 → T-059 → T-070).
   - Optionally T-074 `a430301` on top, once reviewed.
4. `743836f` (T-058, tests only).
5. `aaddefd` (T-060).
6. `cece71d` (T-069). Apply it with merge base `e95bd2d` (or cherry-pick `cece71d` alone). §4 shows that using base S2 here re-applies T-060's first two commits against their own correction and conflicts.
7. T-073 and T-006 (`f6abc4d` + `3257dd0`) only if the owner decides how S2 and `archeus-v1-rearchitecture` join (§6.5).

Ordering 5 before 6 matters only because T-069 is built on `e95bd2d`. Steps 3 and 4 are independent of 1, 2, 5 and 6.

## 4. Dry-run results

### Pairwise (natural merge base unless noted), `git merge-tree --write-tree --name-only A B`

| A × B | rc | Result |
|---|---|---|
| 82b53a7 (K1+K2) × 97797de (A6 chain) | 1 | **CONFLICT archeus/node/local.py**; paths.py auto-merged |
| 82b53a7 × aaddefd (T-060) | 0 | clean |
| 97797de × aaddefd | 0 | clean |
| aaddefd × cece71d (base e95bd2d) | 0 | clean (calls.py, harnesses/calls.py and test_knowledge.py auto-merged) |
| faecc6a × 97797de | 1 | **CONFLICT archeus/node/isolation.py** (the duplicate case, §1) |
| 7f76ecb × 97797de | 0 | clean |
| dcbc848 × 743836f | 0 | clean |
| dcbc848 × aaddefd | 0 | clean |
| 82b53a7 × cece71d | 0 | clean |
| 97797de × cece71d | 0 | clean |

**Conflict 1: `local.py`, K2 × T-061.** Result tree `54ee392350d795eed1f8a4cc6abbf0c991e818e2` has two hunks.

- **Hunk at line 31, the `from ..infra.paths import (...)` line.**
  - K side: `ExecPaths, archeus_home, processes_registry, repo_store, repos_dir, run_dir, seed_staging, stop_sentinel`.
  - A6 side: `ExecPaths, VerifyPaths, processes_registry, run_dir, stop_sentinel`.
  - Resolution is the union of both lists.
- **Hunk at lines 609-1506, two additive blocks inserted at the same point at the end of `LocalNode`.**
  - K side: the whole K1/K2 store section: `store_git`, `store_open`, `store_read`, `store_fetch`, `resolve_base`, `store_seed_ref`, `seed_workspace`, and the byte-core helpers.
  - A6 side (lines 1472-1506): `run_confined_check` with its nested `prepare()`.
  - Resolution is to keep both, one after the other.
- No line edits both sides; this is a positional collision. It still needs the reviewed resolution the T-072 card requires.

**Conflict 2: `isolation.py`, faecc6a × 97797de.** Result tree `13ba2ad8d981c50b8964c09dfbb5f79afe083286`, lines 797-804, inside `establish` under `if request.kind == 'verify':`.
- faecc6a side: `_admit(request.execution_id)`.
- 97797de side: `if request.execution_id in self._admitted: self._admitted.discard(...)` `else: _admit(...)`.
- 97797de is the later revision of the same line. This conflict exists only if both heads are merged, which §1 says not to do.

### Cumulative, chained

The chain feeds each result tree into the next `merge-tree --write-tree --merge-base=<base>`. Git 2.49 accepts a tree as the first side when `--merge-base` is given. Every input descends from S2, so base S2 is a correct three-way base, except T-069, whose base is `e95bd2d`.

| Run | Steps (base) | Outcome | Final tree |
|---|---|---|---|
| A: approved only | d92da8a, faecc6a, 7f76ecb, dcbc848, 743836f (all S2) | all rc=0 | `2924fa433e1dd0874c203dabb01432753231117e` |
| B: full candidate, naive | 82b53a7, 97797de, dcbc848, 743836f, aaddefd, cece71d (all S2) | 97797de rc=1 (local.py, as pairwise). cece71d rc=1: calls.py, passes.py, test_deputies.py (add/add), test_knowledge.py | `2e66ea9cb53db355be346765e55a7b81025d86a6`. **Invalid**: wrong base for T-069 |
| B′: full candidate | as B, but cece71d on base e95bd2d | 97797de rc=1 (local.py only); every other step rc=0 | `9c5ceaa9be203a2992e03e499188c7dac53c28d9` (carries local.py markers) |
| C: full candidate without T-061 | 82b53a7, faecc6a, 7f76ecb, dcbc848, 743836f, aaddefd (S2), cece71d (e95bd2d) | all rc=0 | `592eeaa4e3f6130b9ae7c824d31561e766c767e2` |

Spot checks of tree C, by `cat-file` only; nothing was run:
- **`core/calls.py`, `OwnCalls.run`:** carries both `no_tools` into `call_snapshot` (T-069) and the callable `workdir` resolved after routing (T-060).
- **`knowledge/passes.py`:** `workdir=paths.fresh_call_dir, ..., no_tools=True`; the other calls keep `paths.archeus_home()`.
- **`paths.py`:** one definition each of `repos_dir`, `repo_store`, `seed_staging`, `verify_key_parts`, `isolation_state`, `verify_consumed`, `call_dir`, `_plain_dir`, `fresh_call_dir`.
- **T-060's `test_nothing_in_paths_deletes_or_moves`:** still holds on the merged `paths.py` (only `os.makedirs`/`os.mkdir` in it).
- **`_plain_dir`:** T-061 defines its own in `isolation.py` (97797de:1415). It is a different module from T-060's in `paths.py`, so there is no name clash.

**T-073 / T-006:**
- `merge-tree 5dfac53 3257dd0`: rc=0, tree `4b7aca2f2c50be0b0935f4900232dcddc379e3f9`.
- Tree C × 3257dd0 with base 77008db: rc=0, tree `02190ef9801d51931224da0a23987d1e34e8488c`.
- S2 never touched the nine files f6abc4d and 3257dd0 change (`git diff --stat 77008db 5dfac53 -- <files>` is empty).
- **So S2 is red on CI for the same four reasons T-073 records.**

## 5. Review status and what blocks integration today

- **Approved, integrable now:** T-048 `d92da8a`, T-055 `faecc6a`, T-056 `7f76ecb`, T-057 `f334113`, T-058 `743836f`, T-059 `606d5b6`, T-070 `dcbc848`. Run A shows they compose cleanly.
- **In review after a CHANGES round** (correction committed, new verdict pending Codex quota): T-066 `82b53a7`, T-061 `97797de`, T-060 `aaddefd`. T-061 is also the one with the real `local.py` conflict.
- **In review, no verdict yet:** T-069 `cece71d`, T-073 `3257dd0`, T-074 `a430301`.
- **Blocking today**, beyond the missing integration authority itself:
  - the three pending CHANGES re-reviews;
  - T-069's review;
  - an owner/Codex acceptance that the patch-identical `fc23c2f`/`448cdc7` carry the approvals of `7f76ecb`/`faecc6a`;
  - a reviewed resolution of the `local.py` collision;
  - the S2-vs-branch decision (§6.5) for T-073.

## 6. Choices integration must not make silently (owner)

1. **A6 chain shape.** Take T-061's chain (patch-identical copies, then 97797de's rewrite of the admission line), or the two approved SHAs without T-061. One or the other; not both.
2. **`local.py` resolution.** A positional union looks mechanical, but `run_confined_check` and the K1/K2 store block would then share a module-level import set, and neither card's static gates were written against the other. That needs one focused test run on the merged tree, under its own authority.
3. **Ship T-060 and T-069 together, or neither.** T-060 alone makes every knowledge pass fail when pi is the preferred harness (pi refuses `no_tools`). T-069 is what routes it to Claude. Integrating T-060 without T-069 is a product regression.
4. **Behaviour changes that arrive with the chain:**
   - T-059/T-070: a paired client on loopback loses privileged routes, and the browser e2e is unverified (no SPA build, no tunnel).
   - T-060: the knowledge pass loses direct repository access and its tools.
   - K1/K2/T-061: still unwired to the manager, so no runtime change, and production fetch stays off.
5. **Which line integrates.**
   - `archeus-v1-rearchitecture` (f6abc4d, 3257dd0) and `pv20-s2` (5dfac53) diverge at `77008dbe20f9f9a74045033a4f6aac3692dd27fd` (PV-20 S1).
   - Before the T-073 fixes can count for S2, the owner chooses the integration base: S2 plus these two commits, or S2 merged into the branch. `git cherry -v 5dfac53 3257dd0` lists both f6abc4d and 3257dd0 as absent from S2.
6. **Canonical documents.**
   - `remote_host_required` is not in `docs/architecture/api-and-realtime.md` §1 or `p16-design-gate.md:677` (T-070 GAP 4). That needs an append-only amendment card.
   - K1's additive `target-architecture.md` row is already in `de726ce`..`d92da8a`.
7. **Regression.** No combined test run is implied by this note. T-072's own `verify:` keeps one filtered V1 run on an immutable candidate under separate authorization.
