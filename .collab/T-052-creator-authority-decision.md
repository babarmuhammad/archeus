# T-052 · S2-G creator-authority: mechanisms that keep strict peer exclusion

> **PARTLY SUPERSEDED 2026-10-13 — read `Correction C-1013-T052` at the end of this file
> before using this note.** The §2(c) traversal premise and the M1/M2 coverage claims, the
> §2(b) "WRITE_DAC already closed" framing, the §3-M3/M4 feasibility, uniqueness and
> coverage claims, the §4 reading, and the §2(e) exclusion of same-user actors are
> superseded there. Original text kept unchanged as the historical argument, per
> `.collab/README.md`. Card: T-052, `reviews/T-052-analysis.md` CHANGES.

Prepared by **Qwen** (pi, `spark/qwen3.8-flash-next`), 2026-10-13, card T-052 (owner
parallel-card/planning request; preventive routing permission of 2026-10-12 — no new
classifier refusal is claimed or reconstructed here). Analysis only: no code, no test, no
Git, no process, no native/ACL/token/profile/registry call, no network, no page files.
Companion to `T-010-creator-access.md` (options, partly superseded by Correction
C-1012-1) and `T-004-evidence.md` (static findings, partly superseded by C-1012-2).
Nothing here unblocks T-004: the mechanism choice stays the owner's, with Codex's
architecture review, on that card.

Sources actually read for this note (all read-only):

- `docs/architecture/pv20-execution-isolation-design.md` §3.1 (R7 wording at line 74:
  "One execution-specific identity/principal, created before spawn and torn down after the
  execution; **other executions' state is inaccessible to it**"), §6 (line 646: "**R7 —
  profile granularity: IMPLEMENTATION CONSTRAINT**"; the only item there routed to the
  owner is sharing a principal between executions).
- `docs/architecture/decisions/ADR-0053.md` (R7 restated at line 163).
- Codex's `pv20-evidence/WRITER-CREATOR-CLOSEOUT-2026-10-11.md` (creator/owner experiment,
  its "Observed facts" 1–6 and its own boundary sentences), read directly.
- `archeus/node/isolation.py` and `archeus/harnesses/hook.py` in worktree
  `D:/archeus-pv20-s2-l` at `5dfac53` (line numbers below are that commit; read and
  grepped only, no command run against that tree beyond `git rev-parse --short HEAD`,
  declared here as a deviation in the same class as T-046's).
- `S2G-ARCHITECTURE-READINESS-2026-10-11.md` and T-004 as carried on the board; the two
  correction sections named above.

Every claim below carries one of three labels and must not be read at more strength than
its label:

- **OBSERVED** — an artifact exists (a closeout run, a source line) and is cited to it.
- **INFERRED** — reasoned from documented platform semantics; the primary documentation
  was **not re-read for this note** (no network tools were available to this session), so
  each INFERRED item names the claim a later primary-source check must pin.
- **UNKNOWN** — no evidence either way; only a named, authorized run can settle it.

## 1. The exact gap the mechanisms must close

R7 as written (design §3.1, §6; implementation constraint, not an owner decision) demands
inaccessibility of one execution's state to another, unconditionally. The open case is
narrow and is exactly Codex's observation 5:

> OBSERVED — P created `explicit.txt` with a supplied protected creation descriptor
> containing an allow ACE for Q; Q read and then wrote it successfully, while P itself
> had no WRITE_DAC anywhere (its WRITE_DAC opens on its req directory and on its own
> default-created file both failed with winerror 5, observations 2–3). Both workers were
> AppContainers with distinct package SIDs, **Low integrity, zero capabilities**.

Equally observed on the same fixture, and worth re-reading before proposing mechanisms:

- **OBSERVED** — Q could **not** open P's `default.txt` (inherited DACL) for read or
  write, error 5 (observation 4). Non-consensual exclusion held on that fixture.
- **OBSERVED** — the files P created were owned by the **user's** SID, with
  SYSTEM/user Full Control inherited (observation 1); Core's three gated
  `NtSetSecurityObject` calls later left only SYSTEM/user Full Control in the DACL
  (observation 6).
- The closeout's own bound, quoted: "Neither writer run proves universal non-propagation,
  concurrency safety or the production API contract. They measure these bounded fixtures
  only." And: "No OWNER RIGHTS, deny ACE, integrity-label writer, broker or
  precreated-file mitigation was added." That last sentence is the inventory of what has
  **never been tested in this repo** — and it is the candidate space this note walks.

What is *not* the gap, restated so it stays closed: no Core path can name a peer SID
(T-004-evidence F2, stands), no ACL writer exists anywhere in the product (F1, stands),
and the accepted-mask checker already refuses any grant carrying `WRITE_DAC`,
`WRITE_OWNER` or `GENERIC_ALL` (`access_covered`, isolation.py:1282,1290; F5, stands).
So mechanisms below are compared only against **creation-time** descriptors chosen by an
execution, on surfaces where the execution holds `rw` rows (`workspace`, `req`, `state`;
`default_plan`, isolation.py:1137-1165).

## 2. The five levers, separated (they were merged in earlier notes)

The acceptance asks for exactly this separation. Each lever is a different OS decision
point; a mechanism that closes one does not automatically close another.

### (a) Creation rights — who may create an object, where

Governs: `FILE_ADD_FILE` / `FILE_ADD_SUBDIRECTORY` (`0x2`/`0x4` family) on a **parent**
directory. An execution can choose a creation descriptor only where it is allowed to
create at all.

- OBSERVED: `default_plan` grants `rw` on `workspace`, `req` and `state`; the execution's
  own directory `exec/<id>/` is `core_only` (isolation.py:1165) and never granted; the
  hook creates its mailbox when missing (`os.makedirs(box, exist_ok=True)`,
  hook.py:77-80) — an execution-side create inside a class directory, on today's grant-free
  path so it only ever succeeds when the directory already exists.
- INFERRED (needs primary-doc pin): with no add-file/add-subdir right on a directory,
  `CreateFile`/`CreateDirectory` there fails regardless of the descriptor supplied. This
  is what "remove creation-time authority" reduces to on a per-directory basis.
- UNKNOWN: on the production layout, once `req` is actually granted `rw`, whether any
  execution-side create remains inside a Core-created class directory (the hook's
  `makedirs` line is the named code path). Needs a run (T-008 family).

### (b) WRITE_DAC — changing security after creation

Already closed, by two independent facts:

- OBSERVED (source): the plan checker rejects any mask carrying WRITE_DAC (isolation.py:1290).
- OBSERVED (fixture): P's WRITE_DAC opens failed with error 5 even on objects inside its
  own granted area (closeout observations 2–3).
- INFERRED (needs primary-doc pin): the owner of an object can change its DACL
  irrespective of Write DAC only if granted WRITE_DAC or being owner is honoured — the
  closeout observed P *not* being the owner of files P created (user SID owned them,
  observation 1). Whether an execution can ever take ownership of a Core-created object
  (`WRITE_OWNER`, `SeRestorePrivilege`-style paths) on the production layout is UNKNOWN;
  the mask gate keeps WRITE_OWNER out of grants, but owner-takeover semantics were not
  tested.

The gap is therefore **only** the descriptor passed at create time, on surfaces where
creation rights exist. Any mechanism aimed at (b) is solving an already-closed lever.

### (c) Ancestor/descendant protection — the path check at open time

Governs: whether a peer can *reach* a leaf whose own DACL admits it. Windows checks every
path component on open (traversal `FILE_EXECUTE`/`0x20` on intermediate directories —
isolation.py:1255 already models execute separately).

- OBSERVED: W-1 (T-010 §B, and the writer closeout) reports leaf access that does **not**
  depend on the parent's metadata being readable — so a parent whose DACL the peer cannot
  *read* can still be traversed if traversal was granted; these are separate rights.
- OBSERVED (fixture): the creator/Q pair shared a common temp root that **both** package
  SIDs could traverse — Q reached P's leaf there. The exclusion that did hold (obs. 4) was
  the leaf's own inherited DACL, not path shape.
- INFERRED (needs primary-doc pin, then a run): if every ancestor of a leaf denies the
  peer the traversal right — by having no allow ACE for it, since AppContainer access is
  deny-by-default absent an explicit allow — then opening the leaf fails at the ancestor,
  whatever descriptor the leaf carries. A creator-supplied descriptor is powerless above
  the object it sits on.
- INFERRED: a deny ACE evaluated before allow ACEs (deny-before-allow DACL order,
  isolation.py:1266 already knows `ACCESS_DENIED_ACE_TYPE` exists and its DACL readers
  refuse to credit deny ACEs as satisfying a row, :1359) cannot be overridden by a
  child's own descriptor, because the child never gets evaluated for a principal the
  ancestor already denies. Needs primary-doc pin and a positive-control run.
- UNKNOWN: whether links (symlinks/junctions) an execution can create insert extra path
  components that change the component set checked — i.e. whether a peer-reachable path
  can be re-routed through an alias. The T-048 candidate already built a
  lstat/reparse-point `_plain` checker for stores; reusing that pattern on the grant side
  is a later slice, and the alias question itself needs a run.

### (d) Existing handles — the access decision is made at open time

Governs: handles opened before a deny was applied, or moved between processes.

- INFERRED: DACL changes do not retroactively revoke already-open handles; revocation
  contracts must therefore speak to *new opens*, and separately to handle *passing*.
- OBSERVED (bound): the closeout explicitly disclaims "existing-open-handle invalidation"
  from what its revoke experiment proved.
- UNKNOWN (product path): whether one execution can duplicate a handle into a peer's
  process (`PROCESS_DUP_HANDLE` across AppContainers) or hand a handle to a process it
  spawns under a peer-admitting descriptor. Default process/object DACLs under AppContainer
  tokens are the mechanism's weak point; nothing in this repo has tested it. This belongs
  in the same authorized run as C6 (which already covers jobs/handles, T-008).

### (e) Ordinary same-user tampering — a different adversary, mostly out of scope

Governs: what a non-AppContainer process of the same user can do.

- OBSERVED: on the fixture, files were user-owned with SYSTEM/user Full Control
  (observation 1). The user's own processes reach everything; that is not a peer breach.
- Position stated explicitly: the threat R7 bounds is **execution principals against
  each other** (plus not reaching Core-owned state); the same-user process is the owner's
  own agent and is not the adversary. Evidence collected for peer exclusion must
  therefore always be read as "Q = another package SID", never inferred from
  user-level results — and any mechanism whose only proof is "the user couldn't do it"
  proves nothing about R7.
- UNKNOWN: none claimed; kept here so future notes do not re-merge (e) into (a)-(d).

## 3. Candidate mechanisms

The two families T-004's readiness record names are *"removes creation-time authority
across all writable surfaces"* and *"confines storage so peers cannot traverse"*. This
note compares the minimum mechanisms it could name inside those, plus the privileged
escalations, against the repo's real writers (workspace row, `req`/`res`/`ctl`, `state`
row — the T-010 §2 surface table stands on this point).

### M1 — Core-created ancestors + peer-blind descriptors + confined creation rights

The user-mode minimum. Three conjuncts, all required:

1. Core creates every **ancestor directory** of every writable surface with an explicit,
   non-inherited descriptor allowing only that one execution's SID (plus SYSTEM/Core),
   never an app-package group SID (isolation.py:1276 already treats `S-1-15-2-1`/`-2`
   allows as broad);
2. execution creates are confined to leaf-granted directories (row masks already exclude
   write-metadata rights, (b) above);
3. revoke is proven by **reading the DACL back** (F1: there is no applied-ACE ledger; any
   contract assuming one assumes work that does not exist).

- Coverage if the traversal inference of §2(c) holds: all rows, because peers never get a
  path to the leaf. Creator-supplied descriptors then only ever name peers who cannot
  arrive.
- Cost: S2-G's apply path must create ancestors in a fixed order and verify each; the
  hook's `makedirs` path (hook.py:77-80) must be pinned to fail-closed or removed
  (execution-created class dir = creator-supplied descriptor inside Core's layout).
- Privilege: none beyond the current user-mode design.
- Evidence needed: E1 below. **The claim "peers cannot traverse ⇒ peer-named descriptors
  are unreachable" is the load-bearing INFERRED premise of this whole family.**

### M2 — Ancestor deny ACE against the app-package well-known SIDs

Place an explicit deny for `S-1-15-2-1`/`S-1-15-2-2` on the shared ancestor that every
peer must traverse (e.g. `exec/` above the per-execution dirs). Deny-before-allow makes
the creator's descriptor moot for AppContainer peers.

- Problem that kills it as stated: both owner and peer are AppContainers; a blanket deny
  on a shared ancestor the **owner itself** traverses denies the owner too. Selective
  deny needs a per-principal deny set, and the peer set is unbounded over time (every
  future execution SID). Conditional/callback deny ACEs are the only shape that could do
  this — never examined in this repo.
- Verdict: **not** independently viable; only worth a probe as a positive control inside
  E1 (does an ancestor deny defeat a leaf allow at all — the semantics claim itself).
- Evidence needed: E2 below.

### M3 — Core-mediated (brokered) creation

The execution holds no create right anywhere; every object materializes through a Core
broker that applies its own descriptor.

- On `req/`: feasible and already scoped in T-010 §3-A (fixed slots, Core checks
  completeness instead of trusting the rename). This is option A and stands on its own.
- On `workspace` and `state`: **INFERRED infeasible in user mode without a filter** —
  the writers there are third-party programs (git, shells, build tools) doing arbitrary
  creates; brokering them is a filesystem filter product, not S2-G. Stated as inference,
  not as the withdrawn impossibility claim of T-010 §B: nobody has surveyed or priced
  filter vendors or the brokered-namespace variants here.
- Evidence needed: none new for `req/` beyond T-010's own table (one Windows run: cannot
  create in `req/`, can write its slot); workspace/state brokering would need its own
  survey before being chosen or dismissed.

### M4 — Privileged namespace escalation

Separate machine accounts per execution, silos, Hyper-V isolation, VM per execution. Each
provides a boundary that a creator-supplied descriptor cannot cross (peers live in a
different security domain). All need administrator rights and change the deployment model;
**none has been surveyed, priced or run in this repo** (C-1012-1 §3 stands: T-010's "only
reachable with a privileged component" was an unbounded claim and stays withdrawn). This
note does not rank them; a mechanism spike, if the owner commissions one, is the artifact
that would.

### M5 — Named but unexamined (listed so the survey, when run, has a starting list)

Integrity-label/mandatory-label schemes between same-IL peers (the fixture shows both
peers at Low IL, so IL cannot distinguish them — OBSERVED obs. 5 + worker description;
any label scheme would need labels *below* the AppContainer default, unexplored),
per-execution object namespaces, EFS-style per-principal encryption of execution storage,
OWNER RIGHTS-anchored DACL shapes, Conditional Access Express conditions. All UNKNOWN;
none was excluded here.

## 4. Comparison against the repo's real writable rows

| row (isolation.py:1137-1165) | who writes today | M1 | M2 | M3 | M4 |
|---|---|---|---|---|---|
| `req` (rw) | the hook (slot protocol possible) | covers | redundant | covers (T-010 §3-A) | covers |
| `res`, `ctl` (rx) | Core only | covers | redundant | n/a | covers |
| `exec/<id>/` (core_only) | Core + hook `makedirs` path | covers, if hook create is pinned fail-closed | redundant | n/a | covers |
| `workspace` (rw) | arbitrary third-party writers | covers **if** §2(c) traversal inference holds | fails on owner self-deny | infeasible in user mode (inferred) | covers |
| `state` (rw) | harness runtime caches | same as workspace | same | same | covers |
| profile AppContainer storage | OS-defined paths | not examined — UNKNOWN | UNKNOWN | UNKNOWN | covers |

Reading: **M1 is the only user-mode candidate that could cover every row**, and it is
contingent on one INFERRED premise (ancestor traversal denial defeats leaf allows for
AppContainer arrivals) plus two UNKNOWNs (link-mediated path components, handle passing).
M3 covers only the one row Core owns end-to-end. That is a comparison, not a decision, and
it is a comparison of candidates — none of it is validated evidence.

## 5. Recommendation to the owner (input to T-004; changes nothing by itself)

1. **Commission E1 as the deciding evidence** (authorization must name the operation;
   T-008 already holds the gated-fixture machinery, `ARCHEUS_REAL_BOUNDARY=1` style opt-in):
   in a pytest-temp tree with two AppContainer workers like the creator fixture —
   (a) positive control: current reachable-root case reproduces obs. 5;
   (b) test case: Core-created ancestors, peer traversal absent, P recreates
   `explicit.txt` with a Q-named ACE → Q must fail at the ancestor;
   (c) deny-semantics control (E2): ancestor deny ACE for `S-1-15-2-1` vs a leaf allow;
   (d) handle-passing probe (shared with C6): P duplicates a file handle into Q's process;
   (e) alias probe: P creates a symlink/junction toward its leaf if allowed, and whether
   the traversal check follows it.
   All five are bounded fixtures with named calls; none is an ACL write on a real tree,
   and the closeout's "no deny ACE / broker / precreated-file mitigation was tested" gap
   is exactly what (b)-(e) fill.
2. **Do not treat M1 as chosen** until (b) passes: if it fails, the user-mode field is
   narrowed by evidence and M4's spike becomes the named next decision, with its
   deployment cost on the table.
3. **Keep the two cheap certainties regardless of the mechanism**, because nothing
   withdraws them: the accepted-mask gate (F5) and "revoke proven by DACL read-back, and
   the apply path must record an `applied` inventory" (F1).
4. **Not an option, and not this note's to offer**: narrowing R7. Design §6 records it as
   an implementation constraint; the only design-routed owner decision is sharing a
   principal between executions. If a future survey concludes R7 is unmeetable as written,
   it arrives as evidence plus a new architecture proposal, reviewed on its own — the
   closeout's "change the trust requirement" line is a future proposal, not a T-004 menu
   item.
5. R7's remaining known-unknowns (Finding 3, C6, Gap B, production environment, T-008's
   four open runs) are not answered by anything above and stay listed.

## 6. What this note does not claim

- No mechanism here is asserted to work; every coverage cell rests on OBSERVED, INFERRED
  (unpinned) or a fixture bound, as labeled. No unproven mechanism is presented as chosen.
- No new experiment design beyond the E1/E2 bullet points, no fixture code (the writer and
  creator fixtures are T-008/T-009 artifacts and are not duplicated), no grant/revoke
  implementation (T-004's, once unblocked), no ADR change, no R7 change.
- Primary Windows documentation was **not** consulted for this session; each INFERRED
  claim's pin-before-reliance is named in §2. If E1 is authorized, the pin pass is a
  prerequisite, not an afterthought.
- Deviation, stated as T-046's was: one read-only `git rev-parse --short HEAD` in
  `D:/archeus-pv20-s2-l` to pin the cited commit (`5dfac53`). No other command ran there;
  nothing was written to it.
- Authorship: Qwen, this session, per `.collab/README.md` sign-your-own-work. Board
  claims for T-052 are mine; other agents' lines on the board are untouched.

---

## Correction C-1013-T052 (2026-10-13, Qwen) — responds to `reviews/T-052-analysis.md` (CHANGES)

Append-only correction under the same owner-routed note-only scope: no experiment, no
native call, no test, no page file, no implementation. Sources read for it, all directly:
`W1-CLOSEOUT-2026-10-11.md` (its "Observations" and "Next gate"),
`WRITER-CREATOR-CLOSEOUT-2026-10-11.md` (obs. 1–6), `ADR-0053.md` lines 107-115 and
288-303, and `isolation.py` at `5dfac53` (the S1-applies-none docstring, :375-376). The
two Microsoft pointers the review supplied (*Bypass traverse checking*;
*Checking for Traverse Privilege on IRP\_MJ\_CREATE*, learn.microsoft.com) were **not**
fetched by this session (no network tools); every claim they would pin stays a named
pin-target below. No new evidence was produced, no mechanism is selected, T-004 stays
blocked, R7 is unchanged.

### 1. Finding 1 — traversal is not an ordinary ancestor-ACL question (supersedes §2(c) traversal bullets, §3-M1 "Coverage if the traversal inference holds" and its "load-bearing premise" sentence, §3-M2's deny-vs-allow framing, §4's M1 row, §5.1(b))

Four different things were merged; separated:

- **(i) metadata denial** — the only thing W-1 recorded: "Every case observed **denied
  metadata** on its execution parent. Granted req directories remained readable", with
  "LUID 23 present/enabled; its privilege-name mapping **remains an assumption, not a
  lookup**" on all nine tokens (W1 "Observations"). That is leaf access despite denied
  parent *metadata* — nothing more. It does not establish how ancestor ACLs behave
  against traversal generally.
- **(ii) traverse checks** — the `FILE_TRAVERSE`/execute check on intermediate
  directories at open time.
- **(iii) privilege effects** — enabled privileges change which checks run at all. The
  review cites Microsoft documentation that SeChangeNotifyPrivilege ("bypass traverse
  checking") bypasses traverse permission checks on intermediate folders. W-1's nine
  tokens each had LUID 23 present/enabled under an **assumed** name mapping; if that
  mapping holds, the very fixture demonstrating leaf reachability ran with traversal
  checks likely skipped — so §2(c)'s INFERRED bullet ("no allow ACE for the peer on the
  ancestor ⇒ the open fails at the ancestor") may have no effect against such tokens.
  Whether an enabled bypass privilege, an explicit deny ACE, or the AppContainer token
  shape decides each remaining check is **UNKNOWN**, and the LUID→name question is
  itself open.
- **(iv) namespace isolation** — the object being unreachable by other means entirely;
  no observation here bears on it.

Replacement positions: **M1 and M2 coverage on every row is UNKNOWN until actual token
semantics** — the real privilege set of a production-shaped AppContainer token, its
LUIDs name-*looked-up*, not assumed — support it; it is not a strict solution contingent
merely on one ordinary ancestor-ACL test. No privilege removal or any experiment is
implied or authorized by this note. E1(b) is replaced by **two ancestor cases** run
against that as-is token — ancestor with no peer allow ACE, and ancestor with an
explicit peer **deny** ACE (the deny case doubles as E2's semantics control, since
deny-before-allow surviving a bypass-enabled token is exactly the unverified claim M2
quietly relied on) — each case stating in (i)-(iv) terms which check it probes. E1(c)-(e)
unchanged. W-1's own "Next gate" bound governs: leaf access despite denied parent
metadata, for that fixture only; "It does not establish broad confinement".

### 2. Finding 2 — WRITE_DAC is not "already closed" (supersedes §2(b)'s header claim, its "two independent facts" framing and its closing sentence)

What is actually established, stated exactly:

- **Planned-grant exclusion — OBSERVED (source):** `access_covered` (isolation.py:1282,
  1290) refuses any *planned* mask carrying WRITE_DAC/WRITE_OWNER/GENERIC_ALL, and S1
  applies none of it (isolation.py:375-376: "`applied` is always empty"). It gates rows
  Core plans; it controls no live DACL.
- **Observed failures — two objects, one fixture:** P's WRITE_DAC opens on its req
  directory and its default-created file failed, error 5, one account/build. That is
  two tested objects, not a property of every execution-created descendant.

The pieces the note itself listed but its conclusion ignored: the owner of an object may
rewrite its DACL by ownership rules (the fixture's files were **user-SID-owned**,
obs. 1 — which is why OWNER RIGHTS sits in M5); whether P becomes owner of its creates
under the production layout's rights is not known; WRITE_OWNER/owner-takeover semantics
were not tested. Restated: the create-time descriptor is the **observed** gap; the
effective rights, ownership and creation-side controls of execution-created descendants
are **mechanism-dependent requirements** the chosen mechanism's contract must specify and
prove — not closed items. §2(b)'s "Any mechanism aimed at (b) is solving an
already-closed lever" is withdrawn.

### 3. Finding 3 — unbounded feasibility, uniqueness and coverage claims removed (supersedes §3-M3's workspace/state verdict wording, §3-M4's first sentence, §4's "Reading" first claim, §5.2's "narrowed by evidence")

- M3 workspace/state: "INFERRED infeasible … not S2-G" → **unknown**. No survey was run;
  brokering arbitrary third-party creates is named as a candidate limitation in shape and
  cost (a create-path broker or a filter would be needed), neither chosen nor dismissed —
  the same standing as T-010 §B's never-run survey.
- M4: "Each provides a boundary that a creator-supplied descriptor cannot cross" is
  withdrawn. **Separate machine accounts alone are not proof** of a separate object
  namespace or of creator-DACL containment (shared temp, junctions, network paths and
  shared groups are untouched by account separation by itself); each privileged-family
  member carries candidate-specific UNKNOWNs and must earn its claim with its own
  evidence. No mechanism is selected; the note still does not rank them.
- §4's "M1 is the only user-mode candidate that could cover every row": **uniqueness
  withdrawn.** Among the candidates *named in this note*, M1 is the only one *described*
  in a form that could cover every row — and its coverage is UNKNOWN per correction §1.
  This list is not a survey (M5 is a list of named-unexamined items), M4-family per-row
  coverage is unknown, and the profile AppContainer-storage row is UNKNOWN for every
  named candidate. §4's closing sentence — a comparison of candidates, none of it
  validated evidence — governs every cell.
- §5.2: an E1 failure would bound only what its fixture shows, not "narrow the user-mode
  field" as a general proposition.

### 4. Finding 4 — same-user actors are not a single class (supersedes §2(e)'s "not the adversary" position)

Two kinds, and the note collapsed them:

- **Unrelated owner/user processes** — not the adversary of R7's peer-exclusion claim;
  peer-exclusion evidence still always reads Q as another package SID. That half of
  §2(e) stands.
- **Archeus-managed, execution-influenced same-user deputies** — the verifier,
  forwarding hops, proxies, Core's repository/import operations, harnesses, clients —
  are **explicitly in scope**, per ADR-0053's own words: R1-A's scope (lines 113-115):
  "a forwarded request is never direct local origin; **the verifier, forwarding hops,
  proxies and execution-influenced user-identity deputies receive no §3.6 authority**",
  its soundness sentence (lines 111-112), and the hop/deputy rules (lines 288-303) making
  R1-A sound only if R4a/R4b close every
  path by which execution-influenced code runs under the user's identity — "to
  attestation, such code *is* the user". These are soundness prerequisites of any
  mechanism chosen here and cannot be excluded from this analysis.

Consequence recorded: **M1 gains a fourth conjunct** — "Core-created, peer-blind
ancestors" is worthless if an execution can induce an Archeus same-user process (a
verification command, an import/repo operation, anything loading execution-influenced
configuration) to write into the protected layout under the user's identity. The
mechanism choice inherits the R4a/A5 and R4b/A6 obligations rather than restating them,
and no E1-style fixture may count such a deputy write as a "user-level" control.

### 5. What is unchanged

Strict R7 as an implementation constraint; the existing-handle caveat (§2(d)) as filed;
T-004 is not unblocked and no new experiment, native authoring, validation or run
decision is made here; no mechanism selected; ordinary cards stay Claude's. The F1/F5
carry-overs (§5.3), the R7-narrowing refusal (§5.4), the open-runs list (§5.5) and §6
stand, extended by every UNKNOWN named above. Original authorship of the superseded
sections remains Qwen; the supersessions are mine as well — no reviewer was asked to
agree with anything withdrawn here.
