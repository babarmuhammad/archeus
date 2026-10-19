# T-004 · Static evidence for the S2-G decision

Prepared by Qwen (this session), 2026-10-12, at the owner's request ("you can do this too to collect more evidence"). The "Claude" attribution this file first carried was wrong and is corrected here; the parallel Claude session did the T-006 work Codex reviewed.
Read-only: no code changed, no Windows call, no decision. Companion to `T-010-creator-access.md`, which holds the option comparison; this file is what the code at `ef42204` (worktree `D:\archeus-pv20-s2-l`, branch `pv20-s2`) says about those options.

> **PARTLY SUPERSEDED 2026-10-12 — read `Correction C-1012-2` at the end of this file before using it.**
> F3's parent-rights claim is downgraded and **F4 is withdrawn entirely**, with it going the "A + C" conclusion in
> "Reading of the five". F1, F2 and F5 stand as filed. Original text kept unchanged as the historical
> argument, per `.collab/README.md`. Card: T-014.

Anything marked **needs a run** cannot be settled by reading code, and no run here is authorized — see T-008.

## F1 — The product has no ACL writer at all

`grep -rn "SetNamedSecurityInfo|SetSecurityInfo|SetFileSecurity" archeus/` → **zero hits**. The only hits in the repository are the fakes in `tests/v1/unit/test_pv20_isolation.py` and the untracked writer fixture (T-009).

- `WindowsBoundary` (isolation.py:1545-2010) exposes create/delete profile, derive, job, token, `open_inherited`, `launch` — **no grant, no revoke**.
- Its DACL half, `DaclReaders` (isolation.py:1315-1346), only reads: `grant_established`, `granted_to`, `broad_write_grant`, `dacl`.
- The record says so itself: "S1 applies none … `applied` is always empty" (isolation.py:373-374), and the ledger types (isolation.py:438) carry `planned`, never `applied`.

**Why it matters for the decision.** S2-G's grant will be the first ACL write in the product, and its revoke has no apply-side inventory to be checked against. "Revocation removes every ACE Core applied" is not testable against a recorded set today, because nothing records one. Whatever option is chosen, the S2-G contract should require the apply path to write the `applied` inventory, and prove revoke by **reading the DACL back**, not by diffing an expected list. An option that assumes an ACE ledger exists is assuming work that is not there.

## F2 — Nothing in Core can name a peer

`derive_sid`/`derive` are called only with an execution's own id (isolation.py:297, 464, 1593). No function, record or API in `archeus/node/` or `archeus/core/execution/` accepts or stores another execution's SID; the word "peer" does not appear.

**Why it matters.** The consensual-sharing gap Codex reported is produced by a third-party program choosing a descriptor at create time, not by any Core call. So closing it does not mean removing a Core API — there isn't one. It only changes what the options differ on: *where* those programs are allowed to create (A, B) or whether that access is in scope at all (C).

## F3 — "Core creates every class directory" is a sequence, not a boundary

- Core creates `exec/<id>`, `req`, `res`, `ctl` at spawn: base.py:299-302.
- But the hook, which runs **inside the isolated process**, creates the mailbox when it is missing: `os.makedirs(box, exist_ok=True)` (hook.py:76-80), called from three sites inside the execution (hook.py:85, 113, 143). It also creates `<seq>.lock` with `O_CREAT|O_EXCL` (hook.py:119), `<seq>.req.part` + `os.replace` (hook.py:123-125), `halted.json.tmp` + replace (hook.py:86-89) and `precompact.json` (hook.py:144).
- The invariant's mailbox condition checks that the three class directories **exist and are separate**; it never asks who can create in them (isolation.py:186 `check_invariant`).

Today that is theoretical — the execution holds no grant (F1). The moment S2-G grants `req/` `rw`, whether the execution can recreate a class directory is decided by the creation rights on the parent `exec/<id>/`, which nothing in the plan or the invariant constrains. **Needs a run** to confirm, but the code position is: option A is not just a hook-protocol change, it is the first thing that makes the parent's create rights load-bearing.

> **DOWNGRADED 2026-10-12 — see C-1012-2 §1.** "Nothing constrains" overstates a static read: the *intended* masks, the *checks that exist in source*, and the *runtime answer* are three different things and were run together here.

## F4 — The shared workspace is designed, not leaked

> **WITHDRAWN 2026-10-12 — see C-1012-2 §2 in full.** Everything below describes today's **unisolated**
> behaviour and treats it as the isolated requirement. A1 withdraws `in_place` for isolated executions and
> requires a separate execution repository; this finding cannot bear on R7 at all, and it is the reason
> option C has now been withdrawn in `T-010-creator-access.md`. Read as a description of current code only.

`manager._workspace` (manager.py:324-345):

| case | workdir |
|---|---|
| no project | `ExecPaths(eid).work` — the execution's own private dir |
| `workspace_mode == 'worktree'` and a branch | `archeus_home()/worktrees/<project>/<mission>/<task>` — per task |
| otherwise | `p.entity.root_paths[0]` — **the project root, shared** |

`WORKSPACE_MODES = ('in_place', 'worktree')` (entities.py:865), and `engine._conflict` (engine.py:79-88) serialises two tasks of one project when either is `in_place`, either has no `touches`, or their touches overlap.

**Why it matters.** Two executions of one project already run in the same directory by design, and Core's protection there is the scheduler, not the ACL. An R7 that promises ACL-level peer exclusion over the *workspace row* asserts a property the product does not ask for and the scheduler deliberately contradicts. That is evidence bearing on option C's narrowing (exclusion enforced for non-consensual access, strict, with the shared-workspace case treated as Core-designated sharing rather than as a violation) — it is not the decision.

## F5 — What `rw` means is already pinned

`access_covered` (isolation.py:1262-1279): a row is satisfied by read+write, and Control/`WRITE_DAC`/`WRITE_OWNER`/`GENERIC_ALL` **exceed** a row and fail it. `_write_like` (isolation.py:1282-1288) is the broad-write test behind `broad_write_grant`.

**Why it matters.** The verification side already refuses a grant that carries metadata rights. The apply path S2-G writes has to produce a Modify-style mask that this checker accepts — the contract for the grant's shape exists in the tests before the grant exists in the code, which is the ordering Codex's readiness record asked for.

## Reading of the five, for the owner

> **SUPERSEDED 2026-10-12 — see C-1012-2 §3.** The "A + C" recommendation leaned on the withdrawn F4 and on
> an unsupported user-mode impossibility claim. Do not carry it into the T-004 decision.

F2 + F4 say the gap is narrow and partly by design; F3 + F1 say the strict reading of R7 depends on machinery (apply-side ledger, parent create-rights) that does not exist yet, on a surface (workspace) where Core cannot reach the writer. That is consistent with T-010's **A + C** being the smallest coherent position — A because `req/` is the one surface Core fully owns and can make Core-created end to end, C because the workspace and runtime-state rows cannot be delivered strictly from user mode. The choice stays yours, with Codex's review.

## Still needs an authorized run (not produced here)

- whether an execution can create in `exec/<id>/`, `res/`, `ctl/` once `req/` is granted (F3);
- whether a grant Core applied is fully removed by revoke, read back from the DACL (F1);
- independent rerun of the non-consensual exclusion Codex reported (Q against a default-created file of P; Q against a class directory);
- Finding 3, C6, Gap B — unchanged from T-010 §5.

All four are on T-008, which is blocked on authorization that names the operation, not on effort.
