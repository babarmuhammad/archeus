# T-100 · The strict-storage mechanism decision for T-004: **O1 chosen**

Written by **Qwen** (`pi`, `spark/qwen3.8-flash-next`), 2026-10-15, card T-100.

**Auth (on the card):** owner 2026-10-15 ~01:30, verbatim — *"Let qwen decide the option by
itself afterwards when codex quota returns we eill let it review it"*. Routing: classifier
family of T-004/T-008/T-071 (owner rule 2026-10-15, preventive); **no refusal is claimed on
this card and no withheld content is reconstructed.** The owner's own bound is carried:
*"The choice authorizes no ACL code and no native run: S2-G code and any grant still need an
`auth:` naming the operation."*

**What this note is:** the choice the owner delegated, plus what the choice commits nobody to.
It is analysis. It changes no code, canonical document, gate item or card other than T-100.
**What it is not:** a mechanism acceptance, a T-004 unblock, an R7 change, or an
authorization for anything that runs.

**Labels** (as in T-052 and T-071, unchanged): **PINNED** (a quotation from a fetched page —
none is fetched here, and T-071 r2 Finding 1's caveat keeps applying to every pin T-071
carries: *unverified-against-source*), **OBSERVED** (a repo/collab artifact, cited),
**INFERRED** (reasoned from the cited material, not tested), **UNKNOWN** (only a named,
separately authorized run settles it).

---

## 1. The decision

> **Chosen: O1 — settle the user-mode question first: run T-052's E1/E2 (the two-worker
> temp fixture) under its own named authorization, while T-004 stays BLOCKED BY OWNER.**

Two attachments that are part of the choice, not extra options:

1. **The fallback is named, not chosen.** If E1's ancestor cases come back negative, the
   owner's next choice moves to **O3** (per-execution VMs behind a privileged management
   path of undecided shape), with **O2** (Hyper-V-isolated containers) as its
   management-stack variant, and **O4** (process-isolated containers) staying recorded as
   **unsupported evidence on this host class** (T-071 §3 B2, §5 O4; r2 Finding 3; r3
   Finding 2). Ranking for that case: **O3 > O2 > O4**.
2. **The mechanism itself is still the owner's call**, taken on E1's bounded result —
   exactly the sequence T-071 Correction r3 Finding 4 sets: run E1/E2 under named `auth:` →
   record the result as a dated `docs/architecture/p20-design-gate.md` §12 item → the owner
   weighs T-004 with that evidence in hand. This note does not skip step three.

Why O1 is expressible as *the* choice rather than a stall: T-071's own O1 entry says it *"is
the fallback test either way — O2/O3 do not withdraw it"*. Choosing O1 therefore discards no
option and no evidence; choosing O2 or O3 now would discard the user-mode measurement that
every option still depends on. **OBSERVED** (the sentence, T-071 §5 O1).

**Non-consequences, stated so nothing reads this as more than it is:** T-004 stays
**BLOCKED BY OWNER** (its block is an owner decision about a creation-permitting design, not
a queue position — r3 Finding 4); **R7 is unchanged** (`pv20-execution-isolation-design.md`
§3.1:74, §6:646; `ADR-0053.md`:163, as cited by T-052 §1); no S2-G ACL code is authorized;
no native run is authorized; no grant, no profile, no process, no fetch was performed here.

---

## 2. The question each option had to answer

T-004's blocking reason, as carried on the board: an execution *chooses the creation
descriptor of the objects it creates*, so the current construction cannot promise **strict
peer exclusion for execution-created descendants** — the observed case being P creating
`explicit.txt` with a peer-Q allow ACE and Q reading *and writing* it while P held no
WRITE_DAC anywhere (writer/creator closeout obs. 1–6, separated in T-052 Correction
C-1013-T052 §1–§2). The acceptance offered two shapes: remove creation-time authority across
**all** writable surfaces, or confine storage so peers cannot traverse.

T-071 r2 Finding 5 set the standard of proof that follows from that, and it binds this
choice: *"Strict R7 … is established only by observed peer exclusion on the actual boundary
— two executions, one naming the other's object the way obs. 5 did, both directions denied"*
plus the F1 (applied-ACE ledger / DACL read-back) and F5 (mask gate) carry-overs satisfied on
the real writes, plus the deputy review for whatever helper the option brings. **No
support-risk acceptance substitutes for any of that.**

So the comparison below is on one axis only: **which option can actually produce that
observation, on the surface where the breach lives, soonest and cheapest, without spending
unverified claims.**

---

## 3. Why O1 beats each other option on that axis

### 3.1 O1 vs O2 (Hyper-V-isolated containers)

- O2's headline isolation sentence is pinned **for containers generally, not for this
  workload**; T-071 says so itself — "adopting it for per-execution untrusted workloads is an
  extension of the documented claim, not its test" (§3 B1) and O2's documentation item (v)
  asks for a primary statement covering *execution-chosen* descriptors on shared storage,
  which was never fetched. **OBSERVED** (the sentences).
- The mechanism-specific question — whether one containerized execution can name another in
  a descriptor on storage both can reach — is **UNKNOWN** on both of its conditions
  (peer reach; the SID a containerized process writes as on the host): T-071 r2 Finding 4 and
  r3 Finding 3. An option whose peer-exclusion answer is UNKNOWN cannot beat an option whose
  entire purpose is to answer it.
- O2 additionally needs the B4 daemon/HCS permission statement (unfetched pin-target), the
  mount-SID observation, the HNS/loopback semantics behind T-050 Q2, and image/layer retention
  docs behind B5 — i.e. **its own evidence-card set comes before any claim**, and every one of
  those cards is native.
- And its client-SKU posture is *unsupported evidence*, not a plan: the FAQ's client row reads
  `Unlimited (for test or development purposes only)` in **both** container-limit columns
  (B2; r2 Finding 3 removed any production recommendation toward Hyper-V isolation).
- Meanwhile the hypervisor boundary O2 buys is exactly O3's boundary ("each container runs
  inside of a highly optimized virtual machine and effectively gets its own kernel" — the
  convergence claim, which r3 Finding 2 scopes to **Hyper-V isolation only**). So O2 pays a
  management stack for a boundary it does not own more cheaply than O3 does.

### 3.2 O1 vs O3 (per-execution VMs behind a privileged management path)

- O3 is the most complete **structural** answer to obs. 5 (T-071 §2 A2) — and structural is
  the word: "no run in this repo has ever exercised a VM boundary", and O3's own entry says
  **"No documentation fetched documents this per-ephemeral-execution usage; its fit is
  UNKNOWN pending a spike."** Choosing it would promote an unspiked shape over a measurement
  that is already designed, costed and scoped.
- Its cost side is unresolved in ways O1's is not: the privileged management path's **shape**
  is UNKNOWN (r3 Finding 1 — only the documented operations' privileges are PINNED);
  `execution-architecture.md:351` demands its own PV-20 analysis before such a node runs
  isolated executions; R6-A (no isolated process outlives the Core holding its Job) must be
  **re-derived** for helper-held VM lifetime (A4); the broker loopback (T-050 Q2) and origin
  attestation (T-053) become a per-VM network redesign plus **new trusted in-guest agent code
  inside adversary territory**, under the deputy rule (`ADR-0053.md`:111-115, 288-303);
  retention is GB-per-execution against the keep-all default (A5); and Windows Sandbox's
  pinned single-instance limit removes the disposable-VM shortcut, forcing the full VM stack.
- Decisive on the axis: O3's evidence list **ends in the same experiment O1 is** — "the
  cross-execution probe showing obs. 5's shape cannot occur between two guests". O1 runs the
  obs.-5-shape probe on the surface the breach was actually observed on (a shared, traversable
  directory tree), for a fraction of the setup, and its result is *also* the input that tells
  the owner whether O3 is needed at all. Buying the VM stack first would spend the fallback
  test.

### 3.3 O1 vs O4 (process-isolated containers for untrusted peers)

- Recorded as **unsupported evidence on this host class** (B2), not impossibility, and T-071
  explicitly does not recommend it. It requires everything O2 requires **plus** an
  owner-commissioned ADR knowingly accepting dev/test-scoped documentation as a production
  control, and it is the mode where peer exclusion is *least* supported: r3 Finding 3 — under
  process isolation "no *additional* isolation mechanism is pinned between two executions on a
  shared mount", with both obs.-5 conditions UNKNOWN.
- O4 is therefore strictly behind O1 on evidence, and behind O2/O3 on capability. It stays
  where T-071 put it: on the record, not on the menu.

### 3.4 The cost O1 does not escape (stated so O1 is not read as free)

O1 buys no exemption from the carry-overs that every option pays: **F1** (no ACL writer exists
anywhere in `archeus/`, so revoke has no applied-ACE ledger and must be proven by DACL
read-back — T-011 F1, stands) and **F5** (the accepted-mask gate, `access_covered`,
isolation.py:1282,1290 as recorded in T-052 §1/§2(b), stands). And under C-1013-T052 §2, the
effective rights, ownership and creation-side controls of execution-created descendants are
**mechanism-dependent requirements**, not closed items — so an E1 pass does not close WRITE_DAC
or ownership either. **INFERRED** from those citations: paying F1/F5 under the cheapest
boundary first is the correct order, because they are owed whichever boundary is chosen.

---

## 4. What "O1 chosen" commits, and the decision rule the owner applies on its result

**Sequence** (T-071 r3 Finding 4, restated straight): prepare E1/E2 → run them under their own
`auth:` naming every operation → append the result as a dated `p20-design-gate.md` §12 item →
the owner weighs T-004's mechanism with it. **T-004 stays blocked throughout.**

**The rule, in the shape T-052 §5 already recommends:**

- **If** E1's two ancestor cases pass on a **production-shaped AppContainer token whose
  privilege set is real and whose LUIDs are name-*looked-up*, not assumed (C-1013-T052 §1(iii))
  — i.e. P recreates `explicit.txt` with a Q-named ACE and Q's open fails at the ancestor, both
  the no-peer-allow and the explicit-peer-deny ancestors, with the alias and handle probes not
  opening a bypass — then the owner should adopt the **M1-shape user-mode mechanism** for T-004:
  Core-created, peer-blind ancestors + confined creation rights + revoke proven by DACL
  read-back + C-1013-T052 §4's fourth conjunct (ancestor integrity inherits R4a/A5, R4b/A6; no
  deputy write counts as a user-level control). That is when S2-G's ACL code becomes worth
  authorizing — and it needs an `auth:` naming that operation (§6 below).
- **If** any of them fails, the user-mode answer is bounded out **for that fixture** and the
  owner's next choice is O3, with the ranking in §1.

**Strength bound, not softened:** a pass is *evidence for* the owner's choice, **not** proof of
strict R7. C-1013-T052 §3's last bullet cuts both ways — a result bounds what its fixture
shows. Strict R7 still needs F1/F5 on the real writes, the production-shaped environment, the
T-008 items, and the deputy review (§5). **UNKNOWN** stays the honest label for R7 until then.

---

## 5. Evidence cards that must run before any code

Named as cards the owner should raise (this note does not authorize any of them). E1/E2 here
are **T-052's** evidence plan — *not* T-033's "E1", which is the unrelated isolated-environment
slice.

1. **Documentation pin pass** (prerequisite of E1 per T-052 §5/§6, and of any use of T-071's
   pins per r2 Finding 1). Two halves: the traversal/privilege pages T-052's review named and
   T-052 never fetched (*Bypass traverse checking*; *Checking for Traverse Privilege on
   IRP_MJ_CREATE*), and a re-verification of T-071's load-bearing PINNED quotations against
   their originals (B2's client-SKU table cells, A1's enablement/PowerShell-Direct sentences,
   B3's support/non-support lists). Needs network, so it needs its own card; and per r2
   Finding 1's lesson, that card's `verify:` must state the fetched-page-file exclusion
   explicitly (in the project, or an archival requirement) so it cannot be read either way.
2. **Token-semantics card**: the real privilege set and LUID→name lookup for a production-shaped
   AppContainer token (C-1013-T052 §1(iii): LUID 23's name mapping "remains an assumption, not
   a lookup"). Without it, every ancestor-case result is ambiguous, because an enabled
   bypass-traverse privilege changes which checks run at all. Native, read-only observation of a
   token the test itself creates.
3. **E1** — the bounded two-worker temp fixture (T-052 §5): (a) positive control reproducing
   obs. 5; (b1) ancestor with **no peer allow ACE**; (b2) ancestor with an **explicit peer deny**
   (doubles as E2's deny-semantics control); (d) handle-passing probe (shared with C6); (e) alias
   probe (symlink/junction re-routing the traversal check). Each case states, in C-1013-T052 §1's
   (i)–(iv) terms, which check it probes.
4. **C6 / T-008's outstanding Windows evidence** — still unrun, still needs `auth:` naming the
   operation (zero Job handle on the product path, kill-on-close ≥3 levels deep, same-user
   process scan). E1's handle probe is shared with it, so the two should be authorized in one
   pass rather than twice.
5. **F1 + F5 evidence on the real writes** (applied-ACE inventory, DACL read-back; accepted-mask
   gate) — owed by whichever mechanism the owner ends up choosing; carried over from T-052 §5.3
   and T-011 F1/F5.
6. **Production-shaped layout question, named rather than assumed** (T-052 §2(a) UNKNOWN): once
   `req` is actually granted `rw`, does any execution-side create remain inside a Core-created
   class directory — the hook's `os.makedirs(box, exist_ok=True)` (`hook.py:77-80` at
   `5dfac53`). It decides whether M1's conjunct 2 has a hole on day one. Settles in the same
   native pass.

Explicitly **not** required before code under O1: the read-only feature/edition/SLAT query, the
boundary fixture, mount-SID observation, virtual-switch/JEA delegation research, and the
in-guest agent work — those sit in O2/O3's manifests (T-071 r2 Finding 5) and come only with
that fallback.

---

## 6. Exact file scopes (as T-071 names them for O1) — and where the ACL wall is

T-071 r2 Finding 5, **O1's manifest**, verbatim in substance:

- **Code: none.** E1 changes no product source.
- **Fake tests:** `tests/v1/unit/test_pv20_isolation.py` — interpretation/assertion cases
  **only if** E1's result changes what the fakes pin; otherwise no fake work.
- **Native tests:** `tests/v1/integration/test_pv20_isolation_windows.py` — existing, opt-in,
  gated on `ARCHEUS_REAL_BOUNDARY=1`; the E1/E2 cases live there **under the card naming them**.
- **Consumed, never edited** (all options): `archeus/core/ports.py` (Node Protocol),
  `archeus/core/execution/manager.py` (the one early isolation decision, T-023/T-036/T-038),
  `archeus/node/local.py`.
- Path existence re-checked read-only this pass in `D:\Claude` on `archeus-v1-rearchitecture`:
  those four paths all exist. No file named `(new)` in T-071's manifests exists in
  `archeus/node/` (`vm_node.py`, `helper_rpc.py`, `container_node.py`, `container_rpc.py`) —
  consistent with their "(new)" marks; **OBSERVED**.
- Fixture placement and hygiene follow the ground rules already written down in
  `.collab/T-087-and-native-auth.md` (Part B): a new detached checkout, pytest `basetemp` under
  a short Core-owned root, System32 binaries only, production switches off
  (`PRODUCTION_DISPATCH_ENABLED`, `A4_ENFORCED`, `isolation.CAPABILITIES`,
  `CONFINED_VERIFICATION_ENABLED`), never the Python install, never a user repository, never a
  shared tree, profile/Job cleanup plus before/after profile and `icacls` digests.

**The wall, said plainly:** E1's ancestor cases are not observable without **applying** DACLs to
fixture ancestors (a no-peer-allow descriptor, an explicit peer-deny ACE). That is an ACL
application, and the README is unambiguous — ACL code is S2-G's behind its own authorization,
`grant()`/`require_core_owned`/`_call_icacls` were removed in S1 and a static gate fails on any
ACL-writing API in `archeus/`, `claude_sessions/` or `tools/`, and no grant may ever touch a
tree archeus does not own. So E1's authorization must name the ACL application **on the
Core-owned pytest-temp fixture only**, in the T-064/T-068 style of a positive permission plus an
explicit not-authorized list. Nothing here grants it. **INFERRED** (from the cited hard rules):
an E1 card that does not name it cannot be run as scoped, and must come back as
`BLOCKED BY OWNER` rather than improvise.

---

## 7. What stays UNKNOWN after this choice

None of these is settled by choosing O1; each names what settles it.

1. **Traversal/token semantics** — whether ancestor denial defeats a leaf allow for an arriving
   AppContainer, given enabled bypass-traverse privileges. Settles: E1(b1)/(b2) on a
   token-semantics-verified token. *(M1's whole coverage rests on this — T-052 §3-M1,
   C-1013-T052 §1.)*
2. **Alias-mediated path components** — whether a symlink/junction an execution can create
   re-routes the traversal check. Settles: E1(e).
3. **Handle passing** — cross-AppContainer handle duplication / hand-off. Settles: E1(d) with
   C6/T-008.
4. **Ownership and effective rights of execution-created descendants** — the fixture's files were
   **user-SID-owned** with SYSTEM/user Full Control inherited (obs. 1), WRITE_DAC failures were
   observed on exactly two objects in one fixture, `WRITE_OWNER`/owner-takeover untested, OWNER
   RIGHTS unexamined (C-1013-T052 §2; T-052 M5). Mechanism-dependent requirements, not closed.
5. **The profile AppContainer-storage row** — UNKNOWN for every candidate named anywhere
   (C-1013-T052 §3).
6. **Whether any execution-side create survives inside a Core-created class dir** on the
   production layout (`hook.py:77-80`). Settles: the native pass (§5.6).
7. **The deputy surface** — any Archeus-managed, execution-influenced same-user process that can
   write into the protected layout under the user's identity voids ancestor integrity; R4a/A5 and
   R4b/A6 soundness prerequisites apply to whichever mechanism is chosen (C-1013-T052 §4;
   `ADR-0053.md`:111-115, 288-303).
8. **Every pin's fidelity** — T-071's PINNED quotations remain **unverified against source** (r2
   Finding 1), so nothing in §3 is more than as-good-as-its-citation until the pin pass runs.
9. **Fallback-path UNKNOWNs, dormant while O1 holds** — container-write SID identity on host
   mounts; the non-admin container-permission statement; the shape of the privileged management
   path (r3 Finding 1); per-ephemeral-execution VM use; per-VM virtual-switch policy;
   in-guest/in-container broker loopback (T-050 Q2); origin attestation inside a VM (T-053);
   **this host's edition and feature state — deliberately uninspected by every card in this
   family, including this one.**

---

## 8. Owner authorizations O1 will need — **named here, NOT granted by this note**

Per the README hard rule, each must be authorized by the owner **naming the operation**; the
owner's 2026-10-15 words already exclude ACL code and native runs from this choice.

1. **The E1/E2 native authorization** — AppContainer profile create/delete for two workers, Job
   creation with `KILL_ON_JOB_CLOSE`, launches of named System32 binaries under that token inside
   a Core-owned basetemp, **and the ACL application to fixture ancestors** (§6) — with an
   explicit not-authorized list (no grant on any tree archeus does not own, no Python install, no
   user repository, no shared tree, no elevation, no loopback exemption or firewall change, no
   capability SIDs, no production switch), plus the profile/`icacls` before-and-after digests as
   evidence.
2. **The C6/T-008 authorization** (same pass, §5.4) — named separately, since it is a separate
   card with its own limitations.
3. **S2-G ACL code** (T-004's implementation) — a *different* permission from executing it:
   writing the apply/read-back path needs its own `auth:` naming it, and only becomes worth
   raising after E1's result (§4's rule).
4. **Fallback-only, not now:** Hyper-V/container feature enablement and edition queries (admin per
   T-071 A1), VM/container management, any always-on privileged helper or JEA endpoint
   provisioning, an in-guest agent, and the retention/cleanup card O3/O2's keep-all conflict
   requires (T-071 A5/B5).

---

## 9. What this note does not claim

No mechanism is asserted to work. O1 is chosen as the **decision path**; M1's shape is *recommended
to the owner conditionally* on E1, and is not adopted here. No T-004 unblock, no R7 change or
narrowing (T-052 §5.4's refusal stands), no ADR proposed, no gate item written, no canonical
document touched, no native/ACL/token/profile/registry call, no test, no process, no code change,
no web fetch, no fetched page file, no installed-state or edition inventory, no vendor or price.

**Verify actually honored this pass:** read-only reads of `.collab/README.md`, `.collab/BOARD.md`
(T-004, T-008, T-052, T-071, T-087-part-B card text, T-100), `.collab/T-071-storage-namespace-options.md`
including Corrections r2 and r3, `.collab/T-052-creator-authority-decision.md` including
C-1013-T052, `.collab/reviews/T-071-analysis.r3.md`, `.collab/T-087-and-native-auth.md`; one
read-only directory/file listing to confirm the four O1 paths exist and the four `(new)` paths do
not; no other command, no write anywhere except this note and the T-100 card. T-052/T-071 line
numbers are cited **as recorded in those notes at their own commits** (`5dfac53`, and the
closeout), not re-opened here.

**For Codex at its next reset** (architecture review, per the owner's words):
`py .collab/analysis_review.py T-100 .collab/T-100-mechanism-decision.md` →
`reviews/T-100-analysis.md`.

*Authored by Qwen (`pi`, `spark/qwen3.8-flash-next`), 2026-10-15, card T-100 — read-only
analysis, signed per `.collab/README.md` sign-your-own-work. Mechanism choice: **O1**;
fallback ranking **O3 > O2 > O4**, conditional on E1's bounded result; T-004 stays
BLOCKED BY OWNER; R7 unchanged.*
