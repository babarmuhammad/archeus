# P20 design gate — security and trust hardening

Status: **APPROVED IN PART** (the user, 2026-10-05): D1, D2, D3, D4, D5, D10 and D15 as
proposed; D7 as an amendment; D8 and D9 moved out of P20. **D6 approved as written** (the user,
2026-10-06). **D11, D12, D13 (breaker drills), D14 and the order of §5 after slice E are not yet
decided** and are not inferred (§4.1). Implementation was authorised one slice at a time: **A, B,
C, D and E are implemented with automated evidence; A–D await their manual checks (§10). E is
closed for its automated and CLI-level evidence (2026-10-07, §12 items 68–74): O4 and O5 were
approved and built, and PV-19's real-CLI cases pass. D15's observed run through Core is NOT RUN
(ADR-0021 open). P20 is not complete; no slice after E is authorised, and slice F is not** (§14).
Anything
implementation finds that departs from an approved decision is recorded in §12 for the user's
review, never applied silently.

Sources read, in precedence order: the plan (§27, §31.1 P11, P15, P19.5, P20, P21–P24, §31.3,
§33 Q15, Q21, Q22), this repository at `59281ac` (P19.5 exited, nothing pushed; the V2 research
edits and `prototypes/` in the working tree are another track and are not quoted for any P20
fact), the user's P20 brief of 2026-10-05, [p19-design-gate.md](p19-design-gate.md) §12 items
80–86, 96, 112 and 114, [r13-design-review.md](r13-design-review.md) (R13-03 to R13-16, §3 "Not
findings", §5, §8, §12), [p11-design-gate.md](p11-design-gate.md) (§13.4, §15.2, §18, D26, D30,
the deferral table), [p15-design-gate.md](p15-design-gate.md) (§22, D20, item 5),
[p3.5b-design-gate.md](p3.5b-design-gate.md) (D5, A14), ADR-0049, ADR-0050 §11, ADR-0051, ADR-0052,
[XR-14_TOOL_ALLOWLIST_BRIEF.md](XR-14_TOOL_ALLOWLIST_BRIEF.md),
[ARCHEUS_V2_ASSISTANT_LAYER.md](ARCHEUS_V2_ASSISTANT_LAYER.md) §4–§5 (PV-10, PV-13, PV-19, PV-20,
PV-22), [execution-architecture.md](execution-architecture.md) §2 and §10,
[testing-strategy.md](testing-strategy.md) §2 (G5, G6, G7) and §7.1, the rulebook
[../design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md](../design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md)
(§17, §19, the R15 and Q-B5 rows).

---

## 0. What P20 is, and what it is not

The plan's entry (§31.1), committed:

> **P20 — Security and trust hardening.** Depends: P19.5, explicitly finished. Work: breaker
> drills, e-stop drills, secrets review (DPAPI path), threat-model review of remote access,
> dependency audit, fuzzing of the command API and hook canonicaliser. Carried from P19.5: item
> 83's e-stop without Core, with F7 and F8; F4 with item 86; F6. Added 2026-10-02, decided
> 2026-10-03: ADR-0049 (settings sources), ADR-0051 (isolation boundary), ADR-0052 (tool
> removal), the threat model (ADR-0051 §3). Acceptance: G6 fully passes; no High findings open.

P20 is therefore **five kinds of work**:

1. **Controls built late** (the decided ADRs): the Core-less e-stop (G5), settings-source
   exclusion and inventory with the exit-code-2 deny (ADR-0049, PV-10), tool removal (ADR-0052,
   PV-22).
2. **Controls verified as built**: ADR-0051 §2's boundary tests, breaker and e-stop drills,
   fuzzing of the command API and the hook canonicaliser.
3. **Reviews that produce findings**: the secrets review (DPAPI path), the remote-access threat
   model review, the dependency audit, and the threat model document (ADR-0051 §3).
4. **Five P19.5 carry-overs**, all trust-of-control items: item 83, F7, F8, F4 with item 86, F6.
5. **Observed runs on a real account** (PV-19, ADR-0052 §7), gated by ADR-0021.

It is **not**: an OS-level sandbox (ADR-0051, PV-20), P21's observability views or `live_work`,
P22's legacy import and Resources UI, P23's acceptance matrix (M3, Android, the capture matrix),
P24's cross-phase audit, V2 work of any kind, or any change to a P19.5 decision (§3).

## 1. What exists [V = verified at `59281ac`]

### 1.1 The e-stop (item 83, G5) [V]
- Core-side path built (P11): `POST /v1/estop` writes `run/STOP`, kills executions, disarms;
  `POST /v1/rearm` (`control`, user device) clears it.
- The registry the Core-less path needs is built: `archeus/node/local.py` appends
  `{op: spawn|end, execution_id, process_seq, pid, create_time}` to `run/processes.jsonl` and
  compacts it at boot (p11 D26). `engage_estop()` writes the sentinel. `proc.kill_pid_tree(pid,
  create_time)` exists and is used by the Claude Code adapter.
- `archeus estop` with Core down prints "the e-stop without Core arrives with P20" and exits 2
  (`archeus/cli/main.py:325-340`). The tray's Emergency stop runs that same function
  (`archeus/cli/gui.py:116`) behind its native confirmation (R13-01: Cancel default, Enter and
  Escape stop nothing).
- `tests/v1/judge/test_g05_estop.py::test_the_estop_works_with_core_down_and_core_comes_back_disarmed`
  is `xfail(strict, "phase:P20")`; `support.estop_without_core` is still `_pending`.

### 1.2 F7 and F8: the window's commands [V]
- `ActionButton` (`clients/app/src/components/ui.tsx:157`) has a pre-action `confirm` dialog
  (Cancel autofocused) and shows only a refusal (`role="alert"`). On success it shows nothing;
  the reread changes whatever the command changed.
- Control → About's Emergency stop **has** the pre-action confirmation
  (`surfaces/Control.tsx:866`). What it lacks, and what F7 records, is any acknowledgement of
  the result: the tray says "emergency stop: N execution(s) stopped …" and "Nothing was
  running"; the window says nothing, except the strip's "Emergency stop engaged".
- Pause all (`surfaces/Work.tsx:130`, the strip) has no pre-action confirmation, as in the tray;
  with nothing running nothing visible changes.
- Control → About renders Emergency stop and Re-arm side by side whatever `health.armed` says,
  and names no state (F8).

### 1.3 F4 and item 86: streams and shell credentials [V]
- `archeus/api/sse.py`: `PER_DEVICE = 2`, `MAX_STREAMS = 8`, `TooManyStreams` refuses a third
  stream from one device. A stream whose client vanished is reaped only when a heartbeat write
  fails (`heartbeat_s = 15`). Two reloads inside that window leave two dead streams and refuse
  the live page for about 20 s (item 112: measured 19.9 s).
- The shell redeems a fresh launch code on every launch as a device row named "desktop shell"
  (`observe` + `control`), holds the token in memory only, and never revokes the last one
  (item 86). Revoking a device is `POST /v1/devices/{id}/revoke`, scope `admin`, which the shell
  does not hold. The launch code itself is minted with the local token.

### 1.4 F6: the command bar [V]
"Go to or tell…" closes on Escape or on choosing a destination only. A touch user without a
screen reader has no exit (item 114).

### 1.5 The execution boundary (ADR-0049, ADR-0051, ADR-0052) [V]
- `archeus/harnesses/claude_code/adapter.py` spawns with `CLAUDE_CONFIG_DIR` = the account home
  and `--settings <exec dir>/settings.json` (Archeus's `PreToolUse` and `PreCompact` hook only).
  It passes no `--setting-sources`, `--strict-mcp-config`, `--disable-slash-commands`, `--tools`
  or `--disallowedTools`, and no `--add-dir`.
- `archeus/harnesses/hook.py` denies with a JSON `permissionDecision` and exit 0; it checks
  `run/STOP` first.
- Credential removal and the worktree workdir are built (p11 §18).
- `archeus/core/execution/canonical.py:56` `canonicalise(tool, tool_input, ctx)` is the
  canonicaliser the plan's fuzzing names.
- The `claude` CLI is installed on this machine (`~/.local/bin/claude.exe`); its version is read
  at the start of slice F, not assumed. **Codex is not installed.**

### 1.6 Breakers, secrets, dependencies [V]
- Breakers that exist: the execution breaker (per account, resource/auth failures,
  `executions.py:675-705`, `stop_reason = 'breaker'`), the pairing breaker (`PairingLocked`,
  `api/auth.py:208`), five wrong PINs revoking a device (`routes.py:844`), and P14's automation
  loop guard (S10b).
- Secrets Archeus holds at rest: `run/local-token` (POSIX `0600`; on Windows the profile ACL,
  p3.5b D5, DPAPI deferred by the user); device, node and hook tokens are stored hashed. No API
  key is stored by Core (`AUTH_KINDS` includes `api_key`, but accounts are node-bound and Core
  keeps metadata). This is verified in slice I, not assumed.
- Python runtime: stdlib only. SPA: `clients/app/package-lock.json`. Neither has had an audit
  recorded. No fuzzing or property-testing library is installed (`hypothesis` is absent).

### 1.7 Phase markers [V]
Two `xfail(strict, reason="phase:P20")`: G5's Core-less e-stop, and G7's Codex adapter
(`tests/v1/contract/test_adapter_contract.py:229`, p11 D30).

## 2. Contradictions this gate cannot resolve alone

| # | What disagrees | Sources | Needs |
|---|---|---|---|
| X1 | **Notifications.** The rulebook assigns OS notification and mobile push to P20 ("P20 gate", Q-B5, R15; §17 rows); the plan's P20 entry does not list them; p15 D20 says ntfy "P20 or Q3" | rulebook §17, R15, Q-B5; plan §31.1 P15, P20 | D8 |
| X2 | **The Codex adapter.** p11 D30 and testing-strategy G7 give it to P20, and a `phase:P20` xfail holds it; the plan's P20 entry does not list it; Codex is not installed and no recording exists | p11 D30; G7; plan §31.1 P11 | D9 |
| X3 | **The mobile e-stop PIN.** Rulebook §19 says "e-stop (confirm + PIN)"; Core's route is `control` and no client asks for a PIN; R13 listed it for "the user's P20 credential review" | rulebook §19; r13 §3 "Not findings" | D10 |
| X4 | **DPAPI.** Plan §27 says "API keys at rest via DPAPI"; Core stores no API key; the one secret at rest, the local token, had DPAPI deferred by the user (p3.5b D5, A14) | plan §27; p3.5b D5 | D7 |
| X5 | **F7's word "confirmation".** Control's e-stop already confirms before acting; the finding compares the window with the tray, which reports the result | item 114 | D3 |
| X6 | **ADR-0021 is OPEN** (decisions index), and PV-19 and ADR-0052 §7 are gated by it, while the plan's P20 acceptance includes the observed run | ADR-0049, ADR-0052 §7; decisions README | §10, D15 |

## 3. Scope

**In scope:** §0 items 1–5, as the slices of §5.

**Preserved, not reopened** (the user's brief, 2026-10-05): the V1 visual language, the P19
luminous thread, the appearance system, the offline snapshot architecture, S-1/S-2/S-3, Q-A5,
the live-map key decision, Ctrl/⌘+K, ⌘+, unbound, Ctrl+, retained, the browser/OS matrix
(testing-strategy §7.1) and the P19.5 acceptance boundary. Where a P20 slice touches one of
these surfaces (F6 the command bar, F7/F8 Control and the strip), it adds the smallest compatible
change and says why in §12.

**Not introduced:** WebGL, three.js, GSAP, Lottie, Rive, View Transitions, any V2 effect, any
new runtime dependency without a recorded reason.

**Out of scope (owner):** R13-03 to R13-13 (§4 D11; none is P20's), the activity chip (P21),
thread tints (P22), M3 and the matrix rows (P23), the capture matrix and framebuffer probes
(P23), cross-phase attack (P24), the OS sandbox (PV-20), X7 steering (its own ADR), the
intermittent `test_spa_marker.py` (item 22) and the out-of-scope `test_cli_help` failure
(item 69), which stay classified as they are.

## 4. Decisions requiring approval

Each: problem · design · alternatives · test. **Bold = the recommendation.**

### D1 — Item 86: one desktop-shell credential at a time
- **Problem.** One "desktop shell" device row per launch, forever (§1.3). Revoke-on-Quit misses
  a crash; reusing a row needs the token on disk, which p19 §9 rules out.
- **Design.** **The launch code the shell mints carries `supersede: "desktop shell"`. Minting
  needs `admin`, which the shell holds only through the local token, so the authority is the
  local machine's. Redeeming such a code revokes,
  in the same transaction, every other live credential that was itself redeemed from a
  superseding shell code, and closes their streams.** No token on disk; a crash is cleaned up
  at the next launch; the page's own device is untouched.
- **Cost.** A second concurrent `archeus gui` revokes the first shell's credential; the first
  then reports Core refusals until restarted. The shell is one per desktop in practice; §12
  records it if implementation shows otherwise.
- **Alternatives.** (b) Core expires shell rows unseen for N days (rows still accumulate within
  N). (c) Revoke on Quit plus (a) (more code, same result). (d) Leave it and document it.
- **Test.** Two launches leave one live "desktop shell" row; a killed shell's row is revoked at
  the next launch; an ordinary launch code supersedes nothing; mutants on each.

### D2 — F4: a device's newest stream wins
- **Problem.** Dead streams count against `PER_DEVICE` until a heartbeat fails (§1.3).
- **Design.** **When a device opens a stream at its cap, Core closes that device's oldest
  stream instead of refusing the new one.** It is scoped to one device token, so it opens no
  cross-device denial of service; `MAX_STREAMS` stays a refusal. The leader-tab sharing
  (api-and-realtime) already keeps a healthy client to one stream.
- **Alternatives.** (b) A shorter heartbeat (more writes, still a delay). (c) Raise the cap
  (moves the problem).
- **Test.** Two dead streams plus a reload connect at once; a third device's streams are
  untouched; `MAX_STREAMS` still refuses; presence records the takeover as one close and one
  open; mutant restoring the refusal.

### D3 — F7: the window acknowledges what a command did
- **Reading (X5).** **F7 is the missing result, not a missing pre-confirmation.** Control's
  e-stop already confirms first; Pause all is not destructive and has no pre-confirmation in
  the tray either.
- **Design.** **Pause all and Emergency stop, wherever the window offers them (strip, Work,
  Control → About), show Core's answer in one polite status line next to the button, in the
  tray's words: "Paused N running mission(s)", "Nothing was running", "Emergency stop: N
  execution(s) stopped; Archeus refuses new work until re-armed".** It uses `ActionButton`'s
  existing `onDone`; `role="status"`, not `alert`; no new motion; it clears on the next press.
- **Alternatives.** A toast (rulebook §17 reserves toasts for off-screen completion).
- **Test.** Each of the three answers is rendered and announced; an error still uses the
  existing alert; mutants dropping the line.

### D4 — F8: Control → About names Core's state and offers the one action that applies
- **Design.** **The section opens with the state in words from `health.armed`: "Armed — new
  work is accepted." or "Emergency stop engaged — Archeus refuses new work until you re-arm."
  Armed offers Emergency stop only; disarmed offers Re-arm only.** No new colour; the disarmed
  sentence uses the existing problem word and glyph.
- **Alternatives.** Keep both buttons and add the sentence (a second e-stop while disarmed is
  harmless but meaningless).
- **Test.** Each state renders its sentence and only its button; mutants swapping them.

### D5 — F6: the command bar has a touch exit
- **Design.** **A visible "Close" button in the bar, the size of the existing small buttons
  (≥ 24 px target, rulebook touch rules), plus a tap on the backdrop.** Escape and the
  screen-reader escape gesture are unchanged; focus returns to the opener. Ctrl/⌘+K is
  unchanged.
- **Test.** At 390 px, a tap on Close and on the backdrop each close the bar and restore focus;
  forced colours and high contrast keep the button visible; mutant removing it.

### D6 — ADR-0049: where an opt-in lives and how it is given
ADR-0049 leaves the store, the command and the UI to P20.
- **Design.** **Opt-ins are per account and per project** (a project's `.claude/` is the
  project's; a plugin installed in an account home is the account's), stored as versioned rows
  written by a Core command from a user device with `admin` (the `data_class` pattern of
  ADR-0035). The CLI gets `archeus executions opt-in|opt-out <account|project> <source|plugin|mcp>
  <name>`; the SPA shows the list read-only in Control → Accounts and the per-execution
  inventory in Why. **No opt-in UI form in the SPA in P20** (CLI and TUI only), to keep the
  surface change minimal; a form is P22's Resources work if wanted.
- **Spawn.** `--setting-sources` narrowed as far as the login allows (which value that is, is
  PV-19's to observe; until then the narrowest value that the fake and the recorded stream
  accept, with the fallback rule), `--strict-mcp-config` with only opted-in servers in
  `--mcp-config`, `--disable-slash-commands` unless a skill is opted in, `--plugin-dir` per
  opted-in plugin.
- **Inventory.** Recorded on the execution as one artifact-referenced JSON (hook commands,
  enabled plugins, skills, MCP server names, permission rules, `CLAUDE.md` hashes; excluded /
  opted in / not excludable), read-only reads (ADR-0046), shown in Why.
- **Deny form.** Exit code 2 with the reason on stderr; halt keeps `continue: false`; a hook
  crash and a timeout are tested to fail closed.
- **Test.** ADR-0049's exclusion, inventory, fallback and exit-code-2 tests in G6; argv mutants.

### D7 — The secrets review and DPAPI (X4)
- **Design.** **The review enumerates every secret Archeus writes at rest and records each one's
  protection. If it confirms Core stores no API key, plan §27's DPAPI row is amended to say so,
  and the local token stays under the profile ACL as the user accepted in p3.5b D5.** DPAPI for
  the local token is offered as an option, not built by default.
- **Alternatives.** (b) Build DPAPI (`ctypes`, `CryptProtectData`) for `run/local-token` now.
- **Test.** A gate listing every file under `ARCHEUS_HOME` that holds a secret and asserting its
  protection; mutant loosening one.

### D8 — Notifications (X1)
- **Recommendation.** **Out of P20.** P20 is the hardening of existing controls; an OS
  notification and a push transport are a new feature with a new external surface (a push
  relay is a third party). Move the rulebook's Q-B5/R15 rows to P21 (attention and Health) for
  the OS notification while the window is hidden, and leave push (ntfy) to the user as a V1.x
  question.
- **Alternative.** Build the OS notification only (Qt tray message on approval-required and
  e-stop while hidden), no push, in P20.

### D9 — The Codex adapter (X2)
- **Recommendation.** **It stays in P20 only if the user installs Codex and allows one recorded
  stream; otherwise it moves to P23 (real-harness contract runs), and the `phase:P20` xfail is
  re-marked `phase:P23` with that reason.** A Codex adapter written without a recording would be
  a guess, which p11 D30 already refused. ADR-0051's "network-denied tasks only to `sandbox`
  harnesses" is still tested in P20 against the router with a fake sandbox harness.

### D10 — The mobile e-stop PIN (X3)
- **Recommendation.** **No PIN on the e-stop.** An emergency stop must be the easiest safe
  action, and it only reduces what runs; re-arm is the action that adds risk. Amend rulebook §19
  to "e-stop (confirm)", and **require step-up on `POST /v1/rearm` from a paired (non-local)
  device**, the existing PIN step-up path.
- **Alternatives.** (b) PIN on both. (c) Leave §19 as written and unbuilt.

### D11 — R13-03 to R13-13: owners (none is P20's)

| Finding | Owner phase (recommended) | Why | Dependency |
|---|---|---|---|
| R13-03 digest message rows → "N new messages" | P21 | the digest and Since you last looked are P21's attention and observability surface; Core digest change | none |
| R13-04 approval card ids, ISO time, TUI list repr | P23 | copy and presentation; the copy gate extension is acceptance work | none |
| R13-05 bare `why` in a thread → "why this mission?" | P21 | `why` and the trace view are P21's | P21 trace view |
| R13-06 `status` in words | P21 | ADR-0043 rebuilds the `status` verb from `live_work` in P21 | `live_work` |
| R13-07 chat-card wording | P23 | copy | none |
| R13-08 one live approval card per approval | P23 | conversation presentation | none |
| R13-09 standing change card closes | P22 | ADR-0041 standing preferences and the Resources UI are P22's | P22 Resources |
| R13-10 plan editor Kind words | P23 | presentation map | none |
| R13-11 Relations source column out of the reading path | P23 | presentation; P16 contract kept | none |
| R13-12 "Save preferences" in the TUI | P22 | lands with the Resources UI | P22 Resources |
| R13-13 PLANNING/APPROVED once on Now | P23 | presentation over `state/now.ts` | none |

All stay due before P26, as recorded. **None is implemented in P20.** The user may move any of
them; the plan's P21–P23 entries gain the assigned rows on approval.

### D12 — Fuzzing without a new dependency
- **Design.** **A stdlib fuzz harness (`random.Random(seed)`, a corpus of recorded inputs plus
  structured mutation), run in CI with a fixed seed and a small budget, and on demand with a
  large one (`tools/fuzz_p20.py`).** Targets: every command route's body against its schema
  (`schemas.*`) through the real route table, and `canonicalise()` over every tool the mapping
  names. The property is the same for both: no 500, no unhandled exception, and a canonicaliser
  that never returns a less strict class than the conservative one for an input it cannot
  parse.
- **Alternative.** Add `hypothesis` as a test-only dependency.

### D13 — Drills
- **E-stop drills:** with Core running and down, against fake executions of both enforcement
  kinds (hook and registry-only), including a process that starts in the race and a registry
  line whose `create_time` no longer matches (must not kill a reused pid).
- **Breaker drills:** each breaker of §1.6 tripped deliberately and its recovery observed.
- Both are tests under `tests/v1`, not scripts.

### D14 — Mutation strategy
`tools/mutate_p20.py`, ids `Q01…` (P-prefixed ids are taken by P19's suite), each gate's direct
test kills its mutant; affected P19 mutants (P126–P131 on the tray e-stop) re-run.

### D15 — The observed runs (PV-19, ADR-0052 §7) (X6)
- **Recommendation.** **Built and tested in P20 against the fake harness and the recorded
  stream; the observed run on a real account is a manual check owed by the user under
  ADR-0021's permit, and P20 is reported "ready except the observed run" until it is done.**
  Until PV-19 observes otherwise, every undocumented flag effect is recorded as a verification
  item, never as fact (ADR-0049).

### 4.1 Decisions taken (the user, 2026-10-05)

Recorded as given. Nothing beyond what is written here is approved.

| Decision | Answer |
|---|---|
| **D1** shell credential | **Approved.** A new Qt shell launch revokes the previous shell credential. The token is never persisted to disk. The shell keeps exactly its `observe` + `control` scopes |
| **D2** stream cap | **Approved.** At a device's stream cap the newest stream wins and the oldest is closed. This is the deterministic policy |
| **D3** F7 | **Approved.** Control → About's Emergency stop already confirms before acting; a post-action status line shows Core's actual answer in the tray's terminology. No second stop mechanism |
| **D4** F8 | **Approved.** Control → About states whether Core is armed and offers only the action that applies. No contradictory actions |
| **D5** F6 | **Approved.** The mobile command bar gets a visible Close control, and a tap on the backdrop closes it |
| **D6** ADR-0049 opt-ins | **Approved as written** (the user, 2026-10-06): D6's design, spawn, inventory, deny form and test exactly as §4 states them, keeping ADR-0052's "except opted-in servers" link to slice F and D6 as a prerequisite of PV-19 within D15. Slice E authorised as the next slice; F, G, H, I and J not in parallel. As built: §12 items 42–57 |
| **D7** DPAPI | **Approved as an amendment.** First establish the evidence for what credentials and API keys Core stores. If Core stores no API key needing DPAPI, amend plan §27's obsolete requirement instead of manufacturing DPAPI work; record the evidence and rationale here (slice I) |
| **D8** notifications | **Moved out of P20** to a later phase; the plan and dependency records are updated. Owner: **P21** (attention and Health), whose design gate decides the push transport or records its deferral |
| **D9** Codex adapter | **Moved to P23.** No artificial evidence. It returns to discussion only if a real Codex installation and stream become available and the user reconsiders ownership. G7's xfail is re-marked `phase:P23` |
| **D10** mobile e-stop | **Approved as proposed.** No PIN before Emergency stop, which stays the fastest safety action. Re-arm is the privileged operation and requires the PIN step-up (built in its own slice, not in A) |
| **D15** observed run | **Approved.** No observed-run evidence is claimed before it is performed. P20 may complete its implementation and other evidence, but stays **"ready except for the observed run"** until ADR-0021 is resolved and the real run is done |
| **Item 83** | **Proceed exactly against the existing design** (execution-architecture §10 path 2, p11 §13.4, D26). Acceptance: the e-stop is available with Core down; the local safety action actually happens; no new work starts afterwards; re-arm restores starting work; the operation is safe against accidental activation; the STOP file and the process registry are reused, with no parallel mechanism. The requirement is not weakened because the mechanism exists |
| **Not decided** | D11 (R13-03 to R13-13 owners), D12 (fuzz tooling), D13's breaker drills, D14 (mutant ids), the order of §5 after slice E; and the questions §4.2 adds |

### 4.2 Open questions found during implementation (the user's, not inferred)

| # | Question | Found in | Status |
|---|---|---|---|
| O1 | Should a re-arm re-ask the plan gate for missions that `builtin:estop` blocked while Core was disarmed? Today they stay BLOCKED after the re-arm (P9's existing rule, both e-stop paths) | slice A, §12 item 5 | **open**; nothing changed |
| O2 | F7 also names the window's **Pause all** with nothing running. D3's approved text names only Control → About's Emergency stop. Does Pause all (strip, Work) get the same post-action line? | slice B, §12 item 17 | **open**; not built |
| O3 | D14: are `Q01…` the suite's ids? Slices A and B use them provisionally (Q01–Q17) | slices A, B | **open**; ids not renamed |
| O4 | **The halt against the real CLI.** A PreToolUse `{"continue": false}` lets a call the CLI allows by default run, and is not honoured when the CLI refuses the call. Approved D6 says both "halt keeps `continue: false`" and "crash and timeout fail closed", and the real CLI cannot satisfy both as built. Candidate observed to block the call and stop the session (2/2): `continue: false` plus `permissionDecision: "deny"` at exit 0. Which form? | slice E closeout, §12 item 60 | **decided** (the user, 2026-10-07): both fields, as the minimal D6 correction; built, §12 item 68 |
| O5 | Correct the inventory's item statuses to the observed rule (a CLAUDE.md or skill follows its setting source) and record the built-in plugins, bundled skills and ancestor `.claude/CLAUDE.md`? This is record-only; the argv is unchanged | slice E closeout, §12 item 61 | **decided** (the user, 2026-10-07): built, §12 item 69 |
| O6 | With nothing opted in, an execution loads no CLAUDE.md (user, project or ancestor). The project's file comes back only with the whole `project` source. Intended, or should executions get the project's instructions another way? | slice E closeout, §12 item 62 | **recorded, not changed** (the user, 2026-10-07); a change of default is a separate design decision, §12 item 71 |
| O7 | P11's `SpawnFailed` ends `binding` (uncharged), contradicting P11 note 11's definition of `binding`, and re-dispatches every tick. Charged, uncharged with a backoff or breaker, or routed away from the harness? | slice E §12 item 48; closeout item 64 | **deferred to P11** (the user, 2026-10-07); P11 not modified, §12 item 72 |

Slice A's mutants are numbered `Q01…` in `tools/mutate_p20.py` as D14 proposes; D14 being
undecided, the ids are provisional and renumbering them is a text edit.

**Recorded direction, not P20 scope (the user, 2026-10-05):** after V1 and the current V2
evidence and implementation phases, a dedicated, evidence-driven and prototyped UI/UX refinement
research phase (desktop and especially mobile: structure, interaction, purposeful motion,
hierarchy, a premium feel). Nothing of it enters V1 or P20.

## 5. Slices and order (after approval)

1. **A** item 83: Core-less e-stop (sentinel + registry kill, `create_time`-checked), Core comes
   back disarmed, G5's xfail removed, e-stop drills (D13). The tray needs no change (item 83).
2. **B** F7 + F8 (D3, D4).
3. **C** F4 + item 86 (D2, D1).
4. **D** F6 (D5).
5. **E** ADR-0049 PV-10 (D6), including the exit-code-2 deny.
6. **F** ADR-0052 PV-22: CLI tool names read from the installed CLI first, mapping, argv,
   completeness, drift; execution-architecture §2 amendment; p11 §18 as-built note.
7. **G** ADR-0051 §2 boundary tests; the threat model document (ADR-0051 §3, ADR-0050 §11).
8. **H** breaker drills, fuzzing (D12, D13).
9. **I** secrets review (D7), remote-access threat-model review (P15), dependency audit
   (`npm audit` on the lockfile; the stdlib runtime recorded as such).
10. **J** (only if D8/D9/D10 put it in P20) notifications, Codex, re-arm step-up.
11. **K** G6 complete; full verification; P20 as built (§13); report and stop. P21 is not
    started.

Each slice: its own commits, targeted tests, the relevant E2E, client tests when the SPA
changes, the design and traceability gates, its mutants. The full `tests/v1` with
`ARCHEUS_E2E=1` before exit.

## 6. Data model and storage impact
- D1: a `supersede` field on launch codes and a marker on the credential redeemed from one (one
  migration).
- D6: an opt-in table (versioned rows) and an inventory reference on `Execution` (one migration).
- No other schema change. ARCHEUS_HOME ownership is unchanged.

## 7. API, CLI, UI and TUI impact
- API: `supersede` on `POST /v1/devices/launch/code` (`admin`; the shell mints with the local token); opt-in commands and
  reads; the inventory in the execution read. Generated clients and both API documents
  regenerated.
- CLI: `archeus estop` gains its Core-down path; `archeus executions opt-in|opt-out|opt-ins`.
- SPA: D3, D4, D5, the inventory in Why, the read-only opt-in list. No new route or destination.
- TUI: the opt-in list and the inventory, for parity with the SPA's reads.

## 8. Failure modes and races
- A pid reused after Core died: the registry kill requires a matching `create_time` (§15.2).
- A process spawned while the Core-less e-stop runs: the sentinel is written first, and the
  hook and the manager both check it.
- A superseding redeem racing a live shell request: the old token fails with the ordinary
  revoked error and the shell reports it.
- A stream takeover racing a heartbeat: closing is idempotent (`_close` waits on `done`).
- A narrowed `--setting-sources` breaking the login: ADR-0049's recorded fallback, shown.

## 9. Security
This phase is the security phase; its additions are the controls above. No new network listener,
no token on disk, no new runtime dependency. The supersede authority is the local token, which
already mints launch codes.

## 10. Evidence required before P20 is declared complete
- G5 and G6 pass with ADR-0049, ADR-0051 §2 and ADR-0052 §6's tests; no `phase:P20` xfail left
  (G7's either passes or is re-marked by D9).
- Every Q-mutant killed; affected P19 mutants re-run.
- The full `tests/v1` with E2E; client type check, unit tests, `gen_ui.py --check`,
  `gen_api_docs.py --check`; traceability and design gates.
- The threat model, secrets review, remote-access review and dependency audit committed, with
  **no High finding open**.
- **Manual, owed by the user.** None is removed or downgraded by a later slice; each is NOT
  RUN until the user performs it. A sub-check that cannot be performed (no suitable device) is
  recorded NOT RUN, never passed by a weaker criterion.

  | Id | Check | Procedure | Expected | Status |
  |---|---|---|---|---|
  | **A-M1** | Slice A, item 83 (M1 step 5): tray e-stop with Core down | On the real Windows display, with a mission running, stop Core. Tray → Emergency stop → confirm "Emergency stop". Then `archeus status`; then `archeus gui`; then Re-arm from a user device | The notification reads "emergency stop without Core: N process(es) killed; …"; the mission's process is gone; `archeus status` still exits 1 (Core not started); `archeus gui` starts Core **disarmed**; after Re-arm, new work starts (§12 item 10) | NOT RUN |
  | **B-M1** | Slice B: Control → About in the real Qt shell | In `archeus gui`, open Control → About. While armed: press Emergency stop; check Cancel is the default and Enter and Escape stop nothing; confirm; read the status line; press Re-arm | Armed shows its sentence and Emergency stop only; the accepted line is Core's answer in the tray's words; disarmed shows Re-arm only; after Re-arm the section says armed only once Core confirms (§12 items 13–18, 23) | NOT RUN |
  | **B-M2** | Slice B: Control → About on a phone, including Core unreachable | On a real phone at ≈ 390 px, the same as B-M1; then stop Core and reopen the section | The sentence, the one action and the status line fit at 390 px; with Core stopped, the "Core cannot be reached …" sentence and **no** button (§12 items 13, 23) | NOT RUN |
  | **F6-M1** | F6 (D5) on a real phone | On a real phone (no screen reader): tap "Go to or tell…" to open the command bar; tap its **Close** button. Open it again; tap the dimmed backdrop outside it. Open it again; tap inside the bar's own edge, away from any control | Close and the backdrop tap each close the bar, and focus returns to the opener; a tap on the bar itself closes nothing; Close is at least a phone target (44 px) and is visible in the OS's high-contrast / forced-colours mode if the phone offers one (§12 items 35-36) | NOT RUN |
  | **C-M1** | Slice C, item 86: desktop shell supersession | 1. Launch `archeus gui`. 2. Control → Clients shows the expected "desktop shell". 3. End that GUI process externally (e.g. Task Manager). 4. Launch `archeus gui` again. 5. Check Control → Clients | Exactly one ACTIVE "desktop shell"; the previous shell's credential is no longer usable (its row REVOKED); the new shell is the active one; no second active desktop-shell credential remains. (A row created before slice C has no marker and is not superseded: §12 item 33) | NOT RUN |
  | **C-M2** | Slice C, F4: rapid reload takeover | Against one device/session, reload the page twice in quick succession. Once in a real desktop browser; once on a real phone if one is available. Keep a second device's page open meanwhile | The page reconnects promptly, with no ≈ 20 s lockout (item 112's 19.9 s); the device's own oldest stream is taken over and the previous stream closed; the other device's stream is unaffected | desktop NOT RUN · phone NOT RUN |

- **The observed runs (D15).** Not a UI check: see §14.E. Until they are done, P20 is at most
  "ready except for the observed run".

## 11. Deviations declared up front
- The plan's P20 entry does not list notifications, Codex or the re-arm step-up; this gate
  surfaces them (X1–X3) rather than silently including or dropping them.
- F7 is read as a missing result acknowledgement (X5); if the user meant a pre-confirmation on
  Pause all, D3 changes.

## 12. Deviations and new decisions for the user's review

### Slice A — item 83, the e-stop with Core down (2026-10-05)

1. **As built, against the existing design** (execution-architecture §10 path 2, p11 §13.4,
   D26). `LocalNode.estop_without_core()` (`archeus/node/local.py`) writes `run/STOP` first, then
   calls `proc.kill_pid_tree(pid, create_time)` on every `run/processes.jsonl` spawn line that
   has no end line. The unended-line rule is now one method, `LocalNode.unended()`, which
   `compact_registry()` also reads, so boot compaction and the e-stop cannot disagree about what
   may still run. `archeus estop` (`archeus/cli/main.py`) takes that path when no Core answers,
   and says "emergency stop without Core: N process(es) killed; Core starts disarmed and runs
   nothing until re-armed". The tray's Emergency stop runs the same function behind its
   unchanged R13-01 confirmation, so item 83 closes with no change to `gui.py`, as item 83 said
   it would. No second mechanism: the sentinel, the registry and the kill helper are the ones
   P11 built.
2. **"Down or unreachable", read precisely (clarification, for the user's review).** The
   Core-less path runs when discovery finds no running Core (`not_running` or `unreadable`), when
   there is no local token, or when the POST to `/v1/estop` fails at the network level
   (`CoreError` code `network`, which includes a timeout). **A Core that answers and refuses is
   not bypassed**: the command prints Core's refusal and exits 2, and nothing is killed
   (`test_A04`, Q06). The reason: a refusal is a decision by a live Core, and overriding it
   locally would be a second authority. An unwritable sentinel exits 2 and reports a failure,
   never a stop (`test_A05`, Q08).
3. **Accidental activation (no change).** `archeus estop` is an explicit verb with no prompt,
   as §10 specifies. The tray asks first (R13-01: Cancel is the default; Enter and Escape stop
   nothing; P126-P131). A second press is harmless: the sentinel stays and nothing is left to
   kill (`test_A01`). No new confirmation was added.
4. **After a Core-less e-stop (the drill).** `test_A06` runs it on the real runtime:
   - Core is killed and its execution's process lives on;
   - the e-stop kills that process with Core still down;
   - Core restarts disarmed, and the killed execution reconciles to an `ENDED_*` state that is
     never `ENDED_OK`;
   - a mission created while disarmed starts nothing;
   - `POST /v1/rearm` restores starting work, and a new mission's execution starts.

   G5's `phase:P20` xfail is removed. On both bindings it now checks that the e-stop reports
   the one running process killed before Core returns. The judge may not import Core
   internals, so whether the process is dead is checked by `test_A06`.
5. **Found, not changed (a design question for the user).** A mission created while Core is
   disarmed is refused at its plan gate by `builtin:estop` (P9's existing rule;
   `test_I_G6_estop_denies_the_plan`). It stays **BLOCKED after the re-arm**. This holds for
   both e-stop paths and predates P20. The e-stop's wording ("Missions are not lost; they
   wait") is about missions that existed when it was pressed, and those do wait. Should a
   re-arm re-ask the plan gate for missions blocked only by `builtin:estop`? That is a P9
   behaviour change, so it is not in slice A.
6. **Test infrastructure.** The in-process judge binding's `status()` now carries `armed` as
   `routes.status` composes it. G5 had asserted it since P3.5, but only the HTTP binding
   provided it. Both bindings gained `_stop_core()`, and `Rig.estop_without_core()` has a body.
7. **Known ceiling (unchanged, recorded).** `kill_pid_tree` checks `create_time` and then
   kills, in two steps. A pid recycled in the microseconds between them is not caught (its
   existing `ponytail:` note). Closing that gap needs handle-based tree kills (Job Objects),
   which is PV-20's ground, not P20's.
8. **Tests.** `tests/v1/integration/test_estop_drills.py` holds A01-A06, 7 cases:
   - exactly the live registry processes die; ended and recycled pids are untouched;
   - the sentinel is written before any kill;
   - an unanswering Core (`unreadable`, or `running` with a network failure) is stopped
     without it;
   - a refusing Core is not bypassed;
   - an unwritable sentinel fails;
   - the restart, re-arm and new-work drill.

   Updated tests: `test_X07` (the CLI with Core down stops and never starts Core),
   `test_gui_shell.py::test_emergency_stop_with_core_down_never_starts_it` (the tray now stops),
   and G5. The CLI help line now describes the Core-down path instead of naming P20.
9. **Mutants.** `tools/mutate_p20.py`, Q01-Q08 (ids provisional, D14), **8/8 killed**.
   Re-run because their code or tests changed: P19's P122 and P123 (the tray e-stop), 2/2
   killed; P11's X06, X07, X33 and X34 (`node/local.py`), 4/4 killed.
   `test_mutation_suites_parse.py` now covers `mutate_p20`. The full run caught a first cut
   whose refusal line repeated P19's P20 anchor (`print(sync.explain(e.refusal()), …)`) at a
   deeper indent, so that anchor matched twice. The e-stop's line was reworded rather than
   re-anchoring P20; P19 and P20 were re-run, 2/2 killed, and the parse gate passes for
   `mutate_p19` and `mutate_p20`.
10. **Manual, owed by the user.** M1 step 5 on the real Windows display, re-run with the new
    expectation. With Core stopped and a mission running, Tray → Emergency stop → "Emergency
    stop" gives a notification "emergency stop without Core: N process(es) killed; …"; the
    mission's process is gone; `archeus status` still exits 1. Then `archeus gui` starts Core
    disarmed, and Re-arm from a user device restores work.
11. **The full run** (`tests/v1` plus `tests/test_p05_seams.py`, `ARCHEUS_E2E=1`, before the two
    fixes above): **2616 passed, 6 failed, 14 skipped, 3 xfailed** (38 min).
    - Slice A's own, fixed and re-run green: the parse gate's two `mutate_p19` cases (item 9)
      and `test_traceability::test_judge_scenarios_never_import_core_internals` (G5 had
      imported `claude_sessions.proc`; item 4).
    - `test_spa_resources.py`: item 22/48/90's known intermittent. In isolation it failed 1 of
      3 runs.
    - `test_g03_one_model.py::test_every_client_agrees[http]` read `VERIFYING` on one client and
      `COMPLETED` on another, a read race between clients. It passed 4 of 4 re-runs. Slice A
      changes no Core-up path; recorded as **newly observed intermittent**, not fixed.
    - `test_spa_halo.py::test_the_halo_marks_live_work_until_core_says_it_stopped` ("a failed
      re-read cleared the halo") passed 3 of 3 in isolation. Slice A changes no SPA code;
      recorded as **newly observed intermittent under load**, not fixed.
    - Outside `tests/v1`: `test_cli_help.py::test_a_deferred_v1_verb_imports_only_its_dispatcher`,
      item 69's, unchanged and out of scope.
    - After the fixes, the slice's targeted set (drills, G5, `test_execution_http.py`,
      `test_gui_shell.py`, traceability, seams) gave 62 passed, 1 skipped. The full suite was
      not re-run, because the two fixes touch only a message string and a test import.

### Slice B — F7 and F8, Control → About's emergency stop (2026-10-05)

Decisions used: D3 and D4 as recorded in §4.1. Nothing of D6, D11, D12, D14 or §4.2 was used or
resolved.

12. **As built.**
    - `ActionButton` (`clients/app/src/components/ui.tsx`) gains one optional prop, `report`.
      A caller that passes it is told how the press ended, and the button then shows no error
      of its own. There are four outcomes: Core's answer; refused (4xx, nothing was done);
      failed inside Core (5xx); no answer. Every other caller is unchanged.
    - Control → About's "Emergency stop" section is a small `Estop` component in
      `surfaces/Control.tsx`.
    - Its words come from two pure functions in `state/present.ts`, `armedText` and
      `estopSaid`, so the node tests and the mutants reach them directly.
    - No new component kind, route, Core command or stop mechanism. The press still sends
      `POST /v1/estop` (or `/v1/rearm`) through the existing button, behind the existing
      confirmation.
13. **F8: the state, and only the action that applies.** The section opens with the state in
    words:
    - armed: "Armed: Archeus accepts new work." It offers **Emergency stop** only.
    - disarmed: "Emergency stop engaged: Archeus refuses new work until you re-arm." This is
      the strip's existing `tag blocked` treatment. It offers **Re-arm** only.
    - **unknown**: "Core cannot be reached, so whether it is armed is not known here. The
      tray's Emergency stop and "archeus estop" work without Core." It offers **no action**.
      This applies whenever the connection cannot command, or Core's health has not been
      read; an older read is never shown as the current state.
14. **F7: one status line, Core's answer, in the tray's words.**
    - Accepted: "Emergency stop: N execution(s) stopped; Core is disarmed until re-armed." N
      is the length of Core's `stopped`. The sentence is the tray's.
    - Refused: "Core refused the emergency stop, so nothing was stopped: <Core's reason>".
    - Failed inside Core: "The emergency stop failed inside Core, so nothing is confirmed
      stopped: <reason>".
    - No answer: "Core did not answer, so nothing is confirmed stopped. The tray's Emergency
      stop and "archeus estop" stop without Core."
    - Re-arm: "Re-armed: Core accepts new work again." only when Core answers `armed: true`.
      If Core answers otherwise: "Core answered, but it is still disarmed." Refused, failed
      and unanswered re-arms say the re-arm did not happen or is not confirmed.
15. **Clarification, for the user's review: "Core unreachable and the Core-down path was
    used" cannot happen in the page.**
    - The SPA holds no local authority. It cannot write `run/STOP` or kill a process, and
      giving it either would be new authority in the shell and a second stop authority. The
      brief excludes both.
    - So, in the page, "unreachable" is the honest "nothing is confirmed stopped", plus the
      name of the stop that does work without Core.
    - The Core-down stop is reported where it happens: the tray and `archeus estop` (slice A,
      unchanged).
    - The four cases are therefore covered across the two surfaces:

      | | Tray and CLI | Control → About |
      |---|---|---|
      | Core accepted | "emergency stop: N execution(s) stopped; …" | same sentence |
      | Core unreachable | "emergency stop without Core: N process(es) killed; …" | "Core did not answer, so nothing is confirmed stopped …" |
      | Core refused | "Core did not accept the e-stop: <reason>" | "Core refused the emergency stop, so nothing was stopped: …" |
      | Failure | "emergency stop failed: the STOP file could not be written …" | "The emergency stop failed inside Core, so nothing is confirmed stopped: …" |

16. **Not a notification system.**
    - One line, held in the section's own state.
    - It is replaced by the next press, gone on navigation, and **shown only while the state
      it describes still holds.** A line about a disarmed Core disappears when Core is
      re-armed from anywhere else; the E2E test re-arms over HTTP and checks this.
    - Success is `role="status"`; refused, failed and unanswered are `role="alert"`, as the
      button's own error was. No toast, no persistence, no motion.
17. **Not changed.**
    - The confirmation: the same text, Cancel autofocused, Enter and Escape stop nothing
      (re-tested in the About section itself).
    - The strip's and the conversation card's Emergency stop.
    - The tray: no code change; `test_gui_shell.py` and P19's P122/P123 green.
    - Slice A's semantics. Nothing in the page reaches the Core-down path.
    - F7's Pause-all half is **not built**: D3's approved text names only Control → About
      (§4.2 O2).
18. **Re-arm only from Core's confirmation.**
    - The section's state comes only from Core's reads. The status line comes only from
      Core's answer.
    - The E2E test holds the re-arm request in flight and checks that the section still says
      disarmed, with no success line, until Core answers.
    - Re-arm's re-read widened from `/v1/health` to `/v1`, as the e-stop already did, so the
      strip and `/v1/status` follow at once (minor; no new read).
19. **D10 untouched.** The re-arm PIN step-up is approved but not built: it is its own slice
    (§4.1 D10). This slice adds no PIN or authentication.
20. **Tests.**
    - `clients/app/test/estop.test.ts`: 6 node tests over both wording functions. The client
      suite is 231/231; type check clean; `gen_ui.py --check` and `gen_api_docs.py --check`
      current.
    - `tests/v1/e2e/test_spa_estop_about.py`: 3 browser tests against a real Core.
      - Armed, then stop (Cancel first; Enter and Escape stop nothing), then the accepted
        line. A re-arm made elsewhere clears the line. Disarmed offers Re-arm only. A refused
        re-arm changes nothing. A held re-arm shows nothing until Core answers.
      - Refused (403), failed (500) and unanswered (aborted) stops: each says its line as an
        alert, and Core stays armed.
      - Core killed: the state becomes unknown, with no guess and no action.
      - 4 consecutive green runs.
    - Related suites green: `test_spa_appearance`, `test_spa_strip`, `test_spa_pause_all`,
      `test_spa_mission_thread`, `test_gui_qt`, `test_spa_p16`, `test_gui_shell`, and the
      slice A drills (50 passed). Design gates 37 passed.
21. **Mutants.** Q09–Q17, **9/9 killed**:
    - Q09: the last read is shown while unreachable.
    - Q10: a disarmed Core is offered the Emergency stop.
    - Q11: a re-arm is said without Core's `armed`.
    - Q12: a 5xx reads as a refusal.
    - Q13: the stopped count is not Core's.
    - Q14: a line outlives its state.
    - Q15: a refused or failed press says nothing.
    - Q16: unreachable is given a state.
    - Q17: no answer reads as a refusal.

    `test_mutation_suites_parse.py` passes for every suite it runs with TypeScript, including
    `mutate_p20`. Q09 was first written so that it left two names unused, which TypeScript
    rejects; it now keeps them in use. No older mutant is anchored on the changed lines.
    - **Line endings.** Three of this slice's edits were first written with CRLF. Python's
      text-mode write on Windows turned `ui.tsx`, `Control.tsx` and `mutate_p20.py` into
      CRLF, and the editor wrote the two new test files with CRLF. A node test that reads
      `ui.tsx` as text (`rowpulse.test.ts`) caught it. All five were normalised to LF before
      any mutant ran.
22. **The full run** (`tests/v1` plus `tests/test_p05_seams.py`, `ARCHEUS_E2E=1`, slices A and B):
    **2623 passed, 1 failed, 1 error, 14 skipped, 3 xfailed** (40 min).
    - The error, `test_graph_query.py::test_a_missing_payload_is_logged_once_per_sha` ("fixture
      'caplog' not found"), came from the run's own `-p no:logging` flag, as at P19's item 110.
      Re-run without the flag: passed.
    - The failure, `test_g03_one_model.py::test_every_client_agrees[http]`, read `REVIEWING` on
      one client and `COMPLETED` on another. It is the same failure as slice A's full run
      (`VERIFYING` there).
      - **Classified as a pre-existing race in the test**, not a regression. The test reads the
        SPA, the TUI, the CLI and the API one after another while the mission is still moving
        through VERIFYING, REVIEWING and COMPLETED, and waits for nothing to settle
        (unchanged since `937d8ea`, P19 B11).
      - Both full runs ran beside an unrelated CPU-bound job on this machine, which widens the
        window.
      - Slices A and B change no Core-up path and nothing those four reads use. It passed 4 of
        4 isolated re-runs after slice A.
      - **Not fixed and not called green.** It is listed with the known intermittents, beside
        `test_spa_marker`, `test_spa_resources` and slice A's `test_spa_halo`, which did not
        recur in this run.
    - Outside `tests/v1`: `test_cli_help.py`'s deferred-verb test, item 69, unchanged.
23. **Manual, owed by the user.**
    - Control → About in the real Qt shell: armed, stop (Enter and Escape stop nothing), the
      line, Re-arm.
    - The same on a phone, where the line and the single action must fit at 390 px.
    - With Core stopped, the unknown sentence and no button.

### Slice C — F4 and item 86: streams and the shell's credential (2026-10-05)

Authorised by the user for slice C only (2026-10-05). Decisions used: D2 and D1 as recorded in
§4.1. Nothing of D6, D10, D11, D12, D13, D14, D15 or §4.2 (O1–O3) was used or resolved.

24. **F4 as built (D2).** `Streams._register` (`archeus/api/sse.py`) decides under the pool's
    lock. A device at `PER_DEVICE` has its **oldest** stream (first in opening order) taken
    out of the pool and flagged closing with the reason `superseded`; if that stream has
    already sent its `200`, its socket is shut down too. The new stream is registered in the
    same critical section. Only when the device is under
    its own cap does `MAX_STREAMS` apply, and it is still `429 too_many_streams`.
    - **Clarification, for the user's review: a capped device at a full pool still takes
      over.** Replacing its own stream does not grow the pool, so refusing it would leave
      item 112 alive whenever the pool is full. A device under its cap at a full pool is
      refused as before.
    - **Why the socket is shut down at the takeover**, not only when the old thread notices:
      a stream blocked writing to a client that stopped reading would otherwise hold its
      thread outside the pool's count until TCP gives up. Each takeover would then leave one
      more such thread, which a device could repeat. `_Stream.hangup()` is the same shutdown
      the stream's own `finally` already did, now one method.
    - **A race found and fixed during the slice.** The first cut shut the socket down
      unconditionally. In a burst, a stream superseded before its `200` was written then had
      its socket cut mid-handshake, so that client saw a connection error instead of an
      answer (1 in 20 stress runs of the burst test; 1 failure in the first related-suite
      run). Now a stream that has not started is only flagged: it writes its `200`, sees
      `closing` at its loop's first check and ends with an EOF. The flag and the loop's check
      cannot both miss: the takeover sets `closing` before reading `started`, the stream sets
      `started` before reading `closing`. After the fix: the takeover file 30/30 runs green.
    - **Presence (D2's "one close and one open").** The live presence list
      (`Streams.connections`) shows the oldest connection id gone and a new one present. **No
      `device.stream_opened`/`_closed` trace is written for a takeover**: p15 §5 D4 records only
      the transitions none→one and one→none, and a takeover is neither. Recorded as the reading
      of D2's test line, not a change to D4.
    - **Determinism.** The survivor set is decided by registration order under one lock, never
      by network order: of any burst, the last two registered survive.
    - **No authority added.** Authentication (route scope, live credential) runs before
      `serve`, so a revoked, absent or wrong token reaches no stream of anyone's. The takeover
      touches only the presenting device's own streams.
25. **Item 86 as built (D1).**
    - `POST /v1/devices/launch/code` accepts `supersede`, whose only allowed value is
      `"desktop shell"` (`entities.SUPERSEDE_SLOTS`, enforced by the request schema and by the
      entity). The route is `admin` and loopback-only as before, so the authority to supersede
      is the local token's: the shell asks with the local token, as it already did.
    - `LaunchCodes.mint` fixes the slot in the code's payload, like the scopes; the redeemer
      cannot add or change it.
    - `commands.register_device(supersede=…)` revokes, **in the redeem's own transaction**,
      every `ACTIVE` device whose `supersede` equals the slot (reason "superseded by a new
      desktop shell"), then records the new device with the slot. Revocation is the existing
      `revoke_device` (device `REVOKED`, every token of its principal revoked).
    - The shell (`archeus/cli/gui.py`) adds `'supersede': SHELL_NAME` to the code it asks for.
      Its scopes stay exactly `observe` + `control`; it cannot revoke anything itself.
    - The token is still held in memory only; nothing is written to disk.
    - A superseded shell's streams end at the redeem's commit: every stream wakes on a commit
      and closes when its credential is no longer live (the existing `_still_valid` rule).
26. **Deviations from the gate's text (for the user's review).**
    - **No migration** (§6 named one). The marker is a new optional `Device.supersede` field.
      Entity fields that are not promoted to a column live in the row's JSON `body`
      (`infra/db/rows.py`), as P15's `origin`, `host_label` and `pin_hash` did. Rows written
      before P20 read `supersede = None`: they hold no slot, so the **first** P20 shell launch
      cannot revoke a pre-P20 shell row. Those rows stay as they are and can be revoked from
      Clients as before; every later launch keeps one.
    - **No explicit stream close in the redeem route.** A first cut called `close_device` for
      each superseded device, as `revoke_device` does. It was removed: the commit already
      closes those streams, so the loop was redundant and its mutant could not be killed
      deterministically. The revoke route keeps its own close, which also makes its answer
      wait for it.
27. **Limitations and races found (recorded, not changed).**
    - **A device opening a third stream ping-pongs.** Three tabs of one client that each open
      their own stream (no leader-tab sharing) evict each other in turn, each reconnecting.
      The SPA's leader tab keeps a healthy browser to one stream, so this needs a client that
      does not share; D2's cost, as designed.
    - **A second concurrent `archeus gui`** revokes the first shell's credential (D1's stated
      cost). The first shell's tray then reads Attention as unknown and reports Core's refusal
      for Pause all. The tray's Emergency stop is unaffected: it uses the local token
      (`archeus estop`), never the shell's credential.
    - **A shell request racing the superseding redeem** fails with the ordinary
      `401 unauthenticated` (gate §8), as the tests show.
28. **Tests.**
    - `tests/v1/integration/test_stream_takeover.py` (6, real HTTP stack): item 112's two
      reloads (the live page connects at once and receives frames); newest wins, oldest
      closes, and another device's two streams are untouched and still receive; a takeover
      writes no presence trace; a burst of 8 concurrent opens over 2 old streams answers 200
      to all and keeps exactly the last two **registered** (order taken from the pool's own
      registration, not the network); the pool's cap still refuses a new device while a
      capped device at a full pool takes over; no takeover without a live credential (absent,
      wrong and revoked tokens are 401 and touch nothing).
    - `tests/v1/unit/test_stream_takeover_units.py` (3): which stream is superseded and that
      it is told every way (out of the pool, `closing`, reason, hang-up once started); a
      stream superseded before its `200` is not cut; the pool's cap against a capped device.
    - `tests/v1/integration/test_gui_shell.py`, 6 new: a second launch revokes the first
      (401 `unauthenticated` on reads and Pause all, its stream closed; the second works,
      `observe` + `control` only, cannot revoke; neither token anywhere under
      `ARCHEUS_HOME`); the revocation is recorded with its reason; an ordinary launch code,
      and a browser merely *named* "desktop shell", supersede nothing and are never
      superseded; a crashed shell is revoked at the next launch **across a Core restart**; 4
      concurrent launches leave exactly one live shell; only `admin` mints a superseding code
      and only for the shell's slot (403, 400).
    - Changed to the approved behaviour: `test_api_pools.py` (a third stream of one device is
      now 200 and closes the oldest) and P22 in `test_presence.py` (renamed `…a_third_takes_
      the_oldest`). The launch-code payload asserts in two unit files gained the slot (`None`).
    - Stability: the takeover file 30/30 consecutive runs; `test_gui_shell.py` 10/10.
    - Client: type check clean, 231/231; `gen_api_docs.py --check` and `gen_ui.py --check`
      current (the generated client gained `supersede?: 'desktop shell' | null`).
29. **Mutants.** `tools/mutate_p20.py` Q18–Q33 (ids provisional, D14), **16/16 killed**:
    - F4: Q18 the cap refuses again; Q19 the newest closed instead; Q20 the pool's cap gone;
      Q21 a capped device refused at a full pool; Q22 another device's stream taken; Q23 not
      flagged closing; Q24 not hung up; Q25 a takeover traced as a transition; Q33 a stream
      cut before its `200`.
    - Item 86: Q26 the redeem revokes nothing; Q27 every active client revoked, slot or not;
      Q28 the slot not recorded; Q29 the shell does not ask for it; Q30 the code drops it;
      Q31 a non-admin client mints one; Q32 the slot is free text.
    - Re-run because their files changed: P15's whole suite (`auth.py`, `sse.py`) 23/23; P16
      M25 1/1; P19 P111–P124 (`gui.py`) 14/14. `test_mutation_suites_parse.py` passes for every
      suite it covers; it caught Q27's anchor going stale after the guard fix below.
    - **A guard caught a first cut.** `test_guards.py::test_no_state_is_set_outside_the_p2_
      primitive` rejects the text `state=` in `commands.py`, which a `tx.where(…,
      state='ACTIVE')` filter tripped. The filter reads the state in Python instead.
30. **The full run** (`tests/v1` plus `tests/test_p05_seams.py`, `ARCHEUS_E2E=1`, slices A–C):
    **2640 passed, 0 failed, 14 skipped, 3 xfailed** (31 min).
    - None of the known intermittents recurred in this run: `test_g03_one_model.py::
      test_every_client_agrees[http]` (slices A and B), `test_spa_marker`,
      `test_spa_resources`, `test_spa_halo`. **They keep their classification**; one clean
      run does not reclassify them.
    - Outside `tests/v1`: `test_cli_help.py`'s deferred-verb test (item 69) was not run and
      is unchanged.
31. **Evidence still needed for P20 exit from this slice.** The user approved both proposed
    manual checks on 2026-10-05; they are **C-M1** and **C-M2** in §10, with their procedure
    and expected result there. Nothing else of P20's §10 is affected by this slice.
32. **Status (the user, 2026-10-05): implemented, automated tests green, awaiting its manual
    gate checks (C-M1, C-M2).** Slice C is not P20, and P20 is not complete. The evidence, as
    recorded above:
    - full `tests/v1` + seams + E2E: 2640 passed, 0 failed, 14 skipped, 3 xfailed;
    - stream takeover: 6 integration + 3 unit tests; 30/30 consecutive runs of the takeover
      file after the handshake-race fix;
    - shell credential: 6 new tests; 10/10 consecutive runs of `test_gui_shell.py`;
    - client: 231/231, type check clean, both generator checks current;
    - mutants: Q18–Q33 16/16 killed; P15 (23/23), P16 M25 (1/1), P19 P111–P124 (14/14)
      re-run and killed.

    The known intermittents (`test_g03_one_model.py[http]`, `test_spa_marker`,
    `test_spa_resources`, `test_spa_halo`) keep their classification: they did not recur in
    this run, which neither clears nor reclassifies them. `test_cli_help` (item 69) is
    unchanged and was not run.
33. **The two deviations, and what they mean (no new requirement follows from either).**
    - **Pre-existing shell rows.** The marker is a new optional field in the device row's
      existing JSON body; no row was migrated. Consequence: a "desktop shell" row created
      before slice C carries no marker, holds no slot, and is never superseded. **It stays
      until the user revokes it by hand from Control → Clients.** No gate requires a
      migration (§6's "one migration" was the design's estimate of how a marker would be
      stored, not a requirement), so none is added.
    - **Independent streams from one client.** Three tabs of one client that do not share a
      single stream can close one another's streams, each reconnecting in turn. This is D2's
      policy applied as approved; the SPA's leader tab keeps a healthy browser to one stream.
      **Not redesigned**, and no slice takes it up unless an approved requirement asks.
34. **Authority boundaries: reviewed against the code and the tests.** Each statement, its
    evidence, and where the evidence is indirect:

    | Statement | Holds? | Evidence |
    |---|---|---|
    | Authentication happens before any stream takeover | **Yes** | `GET /v1/events/stream` is scope `observe` (`routes.py`); the server's pipeline authenticates (step 6, `401 unauthenticated`) before any handler runs, and `_register` is reached only from `serve`, the handler. `test_no_takeover_without_a_live_credential` |
    | A revoked or missing credential cannot take over a stream | **Yes** | Same test: an absent token, an unknown one and a revoked device's token are each `401`, and the presenting device's two held streams remain registered and still receive frames |
    | A per-device takeover affects only that device | **Yes** | `mine` is filtered by `device_id` under the pool's lock. `test_the_newest_wins_…_no_other_stream_is_touched` (another device's two streams unchanged and live), the unit test, mutant Q22 |
    | Global pool capacity still returns 429 | **Yes, precisely:** for a device *under* its own cap. A device already at its cap replaces its own oldest stream even when the pool is full, so the pool never grows past `MAX_STREAMS` (item 24's clarification) | `test_the_pools_cap_is_still_a_refusal_and_a_capped_device_still_takes_over`, the unit test, Q20, Q21 |
    | Shell supersession revokes the previous shell credential transactionally | **Yes, by construction**; the outcome is tested, atomicity is not fault-injected | The revocation runs inside `commands.register_device`, one writer command, which is one transaction with the new device's insert. Tested: a second launch revokes the first; 4 concurrent launches leave exactly one live shell; a crashed shell is revoked across a Core restart; Q26–Q28. **No test injects a failure between the revoke and the insert** to prove the rollback; that rests on the writer's existing one-command-one-transaction rule |
    | The local-token tray Emergency stop is independent of shell supersession | **Yes, by construction**; tested indirectly | `Shell.estop` is `gui.estop` → `main.estop()`, which reads the local token (`discovery.read_local_token()`) and never the shell's credential. `test_emergency_stop_is_archeus_estops_code` asserts the e-stop request carries the local token. **No test presses the tray e-stop on a shell whose credential was superseded**; independence follows from the e-stop never reading `_own` |

    No discrepancy was found. The two "by construction" rows are recorded so that a later
    slice does not mistake them for directly tested properties.

### Slice D — F6, the command bar's touch exit (2026-10-05)

Authorised by the user for slice D only. Decision used: D5 as recorded in §4.1. Nothing of D10,
slice I, O1–O3, D6, D11–D14, ADR-0021 or the §5 order after D was used or resolved; the
D10 / V2-3 mismatch (§14.F) is left exactly as recorded.

35. **As built (D5).** `clients/app/src/surfaces/CommandBar.tsx` gains:
    - a visible **Close** button (`btn secondary`, the existing small-button style) beside the
      input, in the same row; it calls the bar's existing `onClose`;
    - a **tap on the backdrop** closes the bar: a click whose target is the `<dialog>` itself and
      whose point lies outside the dialog's box. The geometry is one pure function,
      `onBackdrop(box, x, y)` in `state/palette.ts`, so a tap on the bar's own padding (also a
      click on the `<dialog>` element) closes nothing.
    - `app.css`: the bar's form lays the input and the button out in one row (`flex`, the input
      shrinks). Nothing else changed: the phone rule already gives every `.btn` the 44 px phone
      target, and the forced-colours and high-contrast rules already border every `.btn`.
    - **Unchanged:** Escape (the native `<dialog>` cancel), Ctrl/⌘+K, the opener button, every
      palette behaviour (arrows, actions by Core's verbs, Tell Archeus and its key reuse), and
      no new route, Core call, authority or motion.
36. **Focus return needed no code.** The native modal `<dialog>` restores focus to the element
    that had it when `showModal()` ran. Tested for Close and the backdrop on a 390 px touch
    context and for the backdrop on a desktop: focus is back on "Go to or tell…" each time.
37. **Authority boundaries: unchanged.** Slice D is presentation only. It adds no request and
    no state, and the bar's actions still go through the same Core verbs with the same
    `control`-scope and connection checks. The e-stop, re-arm, authentication, stream and
    shell-credential boundaries (§12 item 34) are untouched.
38. **Tests.**
    - `tests/v1/e2e/test_spa_command_close.py` (3, real browser, real Core):
      - at 390 × 844 with touch: Close is visible and at least 44 × 44 px; a tap on Close
        closes the bar and focus returns to the opener; a tap on the bar's own edge closes
        nothing; a backdrop tap closes it and focus returns; Escape still closes it;
      - on a desktop: Ctrl+K opens with the input focused; Close is shown; Escape closes; a
        backdrop click closes and focus returns;
      - under forced colours and under `prefers-contrast: more`: Close is visible, drawn with a
        border, and still closes the bar.
      - 5/5 consecutive runs green.
    - `clients/app/test/palette.test.ts`: one node test of `onBackdrop` (outside on all four
      sides; edges and inside are not the backdrop). Client 232/232, type check clean,
      `gen_ui.py --check` and `gen_api_docs.py --check` current.
    - Related: the palette, P16, appearance, offline-snapshot, About e-stop and strip E2E
      suites, the design gates, traceability and seams: **99 passed, 1 skipped**.
    - **A test-side correction during the slice:** the first cut measured Close with
      `bounding_box()` while the dialog's existing open animation was still scaling it (43.1 px
      read for a 44 px button); it now reads the layout size. The desktop test's check floor
      was first set one too high and corrected to the five checks it makes.
39. **Mutants.** `tools/mutate_p20.py` Q34–Q37 (ids provisional, D14), **4/4 killed**:
    Q34 the Close button is not there; Q35 Close closes nothing; Q36 a backdrop tap closes
    nothing; Q37 a tap on the bar's own padding closes it.
    - **A survivor, recorded:** Q34's first form added the `hidden` attribute to the button and
      **survived**, correctly. `.btn` sets `display: inline-flex`, which overrides the user
      agent's `[hidden] { display: none }`, so that mutant never hid anything (an equivalent
      mutant). Q34 now removes the element and is killed. Recorded because the same pattern
      would make any `hidden` on a `.btn` elsewhere a no-op; nothing in this slice uses it.
    - Re-run because their files changed: P19.5 N282–N288 (`CommandBar.tsx`, `palette.ts`)
      7/7 killed; P19 P15 (`CommandBar.tsx`) 1/1 killed. `test_mutation_suites_parse.py` passes
      for `mutate_p19`, `mutate_p19_5` and `mutate_p20` (6/6).
40. **The full run** (`tests/v1` plus `tests/test_p05_seams.py`, `ARCHEUS_E2E=1`, slices A–D):
    **2642 passed, 1 failed, 14 skipped, 3 xfailed** (28 min).
    - The failure is `test_spa_marker.py::test_the_marker_travels_once_from_the_execution_to_its_task`
      ("the marker begins at the execution: None"): the **known intermittent** (§3, item 22),
      with the same signature as before. In isolation afterwards it failed 1 of 3 runs. Slice D
      does not touch the graph or the marker. **Not fixed and not called green; its
      classification is unchanged.**
    - The other known intermittents (`test_g03_one_model.py[http]`, `test_spa_resources`,
      `test_spa_halo`) did not recur; that clears nothing. `test_cli_help` (item 69) was not run.
41. **Status: implemented, automated tests green apart from the known intermittent above,
    awaiting its manual check F6-M1 (§10).** P20 is not complete.

### Slice E — PV-10, ADR-0049's settings sources (2026-10-06)

Authorised by the user (2026-10-06) as the next P20 slice, with D6 approved **as written** in §4
(§4.1). Slices F, G, H, I and J were not started. Nothing of D10, slice I, O1–O3, D11–D14,
ADR-0021, the D13 breaker drills or the D10 / V2-3 mismatch (§14.F) was used or resolved, and
`test_spa_marker`'s classification is unchanged. Implementation: `97040dc`.

42. **As built: the store (D6, §6).**
    - Migration `0015_opt_ins.sql`: an `opt_ins` table of versioned rows with exactly one owner
      (`CHECK ((account_id IS NULL) <> (project_id IS NULL))`) and one row per owner, kind and
      name (a unique index). An opt-out is the same row's next version with `opted_in` false,
      never a second row and never a delete.
    - The entity `OptIn` (`opi_` ids; `domain-model.md` §8.9). Kinds `source`, `plugin`, `mcp`.
      A name matches `[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}`, so a path is never a name. An account
      may opt in only the `user` source and a project only `project` and `local`
      (`SOURCE_OWNERS`).
    - `core/application/optins.py`: `set_opt_in` is a Core command accepted from a **user
      device** only (ADR-0035's `data_class` pattern); an unchanged answer writes nothing; each
      change emits `opt_in.changed`. `effective(account, project)` is what an execution gets: its
      account's live opt-ins plus its project's, and no other owner's.
    - The inventory reference is `Execution.inventory_sha256` (a sha256, checked). It lives in
      the execution row's body, since nothing queries by it, so the one migration D6 names adds
      the table and no column.
43. **As built: the command and the reads (D6, §7).**
    - API: `GET /v1/opt-ins` (`observe`) and `POST /v1/opt-ins` (`admin`, an idempotency key
      required). The execution read carries `inventory`. Generated clients, `api-reference.md`
      and `testing-strategy.md` §1.1's contract ops (`set_opt_in`, `opt_ins`, `execution`) are
      updated.
    - CLI: `archeus executions opt-ins` and `archeus executions opt-in|opt-out <account|project>
      <source|plugin|mcp> <name>`; `claude_sessions/cli.py` passes `executions` through to V1.
    - SPA: a read-only opt-in table in Control → Resources, beside its Accounts section, that
      follows Core when a row changes (`invalidation.json`); the execution inspector shows the
      inventory beside its Why (`InventoryBlock`, `inventoryLines`). No form, route or
      destination was added.
    - TUI: the same opt-in list, read-only, and the inventory in the execution view
      (`inventory_lines`), parity-tested against the SPA's presenters.
44. **As built: the spawn and the inventory (D6).** `harnesses/sources.py`, stdlib only and
    read-only (ADR-0046):
    - `take(home, workdir, opt_ins)` builds one JSON inventory (version 1, `observed: false`):
      hook commands, plugins, skills, MCP server **names**, permission rules and CLAUDE.md
      hashes, each with its status (`excluded`, `opted_in`, `not_excludable`, `recorded_only`,
      `not_found`), the opt-ins it used, and the flags derived from them. It is bounded at 500
      items with a stated cut. It never holds an environment block, a server's definition or a
      file's contents.
    - The manager takes the inventory **before** the process exists, redacts it, stores it as an
      Artifact, references it from the execution and names it in `execution.prepared`. The spawn
      reads its flags from exactly what was stored, so the record and the argv cannot differ.
    - The argv always carries `--setting-sources <the opted-in sources, joined>`, empty when none
      is (left out, the CLI would load every source). It also carries `--strict-mcp-config`,
      plus `--mcp-config <run/exec/<id>/mcp.json>` holding only the opted-in servers of their own
      owner. `--disable-slash-commands` is passed unless a skill arrives through an opted-in
      source or plugin. It adds one `--plugin-dir` per opted-in plugin, resolved from
      `installed_plugins.json` (format 2) and refused when it lies outside `<home>/plugins`.
    - Managed settings are recorded `not_excludable`. CLAUDE.md files (the account's and the
      project's walk) are hashed and recorded `not_excludable` unless their source is opted in.
      No flag Archeus passes is aimed at them, and `--bare` cannot keep a subscription login.
    - ADR-0049 §2's fallback is `RECORDED_ONLY`: a source PV-19 finds cannot be narrowed is
      loaded and recorded `recorded_only`. It is **empty**, and nothing fills it by inference.
45. **As built: the deny form (D6).** `harnesses/hook.py`:
    - A deny is **exit code 2 with the reason on stderr**; allow keeps its JSON at exit 0; a
      halt keeps `{"continue": false}` at exit 0.
    - `guarded()` turns a hook crash into a halt, and Core never answering into a halt before
      Claude Code's own hook timeout (`HOOK_TIMEOUT_S = 120`, longer than the hook's deadline).
    - The process leaves through `os._exit` after its own flush, so the interpreter's exit flush
      can never replace the code.
    - Any other exit code is non-blocking in Claude Code [DOC], so none is ever produced.
    - The fake agent models those semantics: 2 blocks; any other code, a timeout or missing
      JSON proceeds and emits `hook_error`. It echoes its `argv` in `started`, so a test can see
      the flags a fail-open hook would have run under.
46. **Readings of D6, for the user's review (applied, not decided).**
    - **"Control → Accounts".** No Accounts tab exists; Control → Resources has an Accounts
      section, and the list sits beside it. §7 adds no route or destination, so none was added.
    - **`<account|project>` is the owner's id** (`acc_…` or `prj_…`), not a word followed by
      one.
    - **"CLI and TUI only" against §7.** D6's sentence can be read as the TUI also writing;
      §7 gives the TUI "the opt-in list and the inventory, for parity with the SPA's reads". The
      TUI is read-only and names the CLI command. A TUI write is a small addition if wanted.
    - **"unless a skill is opted in".** The command's kinds are `source|plugin|mcp`, with no
      `skill`. A skill counts as opted in when it arrives through an opted-in source or plugin.
      Whether a left-out source's skills load once the flag is dropped is undocumented, so they
      are then recorded `not_excludable`.
    - **A mission with no project** gets its account's opt-ins only.
    - **An inventory that cannot be taken** ends the execution `workspace`, charged, with the
      reason "the settings sources could not be inventoried: <error type>". The SPA and TUI show
      the stop reason's existing copy ("its workspace could not be made"). A dedicated stop
      reason would be a domain addition, so it was not invented (item 47).
47. **Found and fixed during the slice: an inventory failure re-dispatched forever.** The first
    cut ended a failed inventory `binding`, which is **uncharged**. The task was then
    re-dispatched on every tick: 41 executions in 40 ticks, measured. It now ends `workspace`,
    which P11 note 11 already charges for a workspace that cannot be made. A persistent failure
    therefore spends the task's attempts and stops. I09 asserts exactly `max_attempts`
    executions, each `ABANDONED`/`workspace`/charged with no pid and no stream, and the task
    `FAILED`; Q67 reverts it and is killed.
48. **Found, not changed (P11's, pre-existing): `SpawnFailed` has the same loop.** A process
    that cannot be started (a missing binary) ends `binding`, uncharged, and is re-dispatched on
    every tick: 40 executions in 40 ticks, measured with a scratch test since deleted. It
    predates slice E and is outside D6, so it is recorded for the user, not fixed.
49. **Verification items for PV-19 (D15), not facts.** The inventory says `observed: false`
    until an observed run:
    - Whether Claude Code 2.1.291 accepts an **empty `--setting-sources ""`**. Its help documents
      the list but not an empty one. If it refuses it, every execution fails to start, so this is
      the first thing PV-19 checks; ADR-0049's fallback applies.
    - Whether the account's login survives the narrowing.
    - What loads under the narrowed sources: skills with and without
      `--disable-slash-commands`, plugins through `--plugin-dir`, CLAUDE.md.
    - The exit-code-2 deny and the halt against the real CLI.
50. **Limitations, recorded.**
    - `run/exec/<id>/mcp.json` holds the **full definitions** of the opted-in servers (command,
      arguments, URL, environment), which may carry tokens. It is written only when a server is
      opted in and never enters the record. **Slice I's secrets review (D7) should list it.**
    - Local-scope MCP servers (`.claude.json` `projects[<path>].mcpServers`) are not inventoried.
    - An execution references its **latest** process's inventory; earlier processes' inventories
      are named in their `execution.prepared` events.
    - The ancestor CLAUDE.md walk stops below the filesystem root, as Claude Code documents.
51. **Authority boundaries.** Opt-ins are written only by a user device holding `admin`. A
    `control` client, an agent principal or another owner is refused (I04, H01, G6, Q38, Q44).
    Reads are `observe`. The e-stop, re-arm, authentication, stream and shell-credential
    boundaries (§12 item 34) are untouched. ADR-0052's "except opted-in servers" (slice F)
    reads this store; slice F is not built.
52. **Tests.**
    - `tests/v1/unit/test_settings_sources_units.py`, E01–E22 (33 collected): exclusion by
      default; the argv; managed and CLAUDE.md; per-owner sources; strict MCP; plugins and their
      containment; skills; the fallback; no secret; unreadable files; bounds; names; the deny
      exit code, allow and halt; crash and timeout fail closed; the fake agent's fail-open model;
      the spawn's flags equal the recorded ones; a hook that cannot write still denies.
    - `tests/v1/integration/test_settings_sources.py`, I01–I10, H01, H02 (12, real Core): the
      versioned row, ownership, no-op opt-outs, user-device and admin only, per-owner reach, the
      recorded inventory and the argv, no secret stored, the inventory failure (item 47), the
      exit-code-2 block reaching the agent, the HTTP scopes, and the CLI.
    - G6 (`test_g06_security.py`): two new scenarios, each over both judge bindings.
    - `tests/v1/e2e/test_spa_opt_ins.py` (2, real browser, real Core): the read-only list follows
      Core; the inspector shows the inventory beside its Why. Check floors on both.
    - Updated: `test_domain`, `test_execution_units`, `test_db_schema`, `test_core_client`,
      `test_api_structure`, `tests/v1/tui/test_parity.py`, the client's parity fixtures, and
      `test_spa_resources.py`'s one added wait (item 56).
    - Slice E's unit, integration, E2E and G6 suites together: **59 passed, 2 skipped, 5/5
      consecutive runs** (the skips are existing http-only judge cases). Focused suites: 407
      passed, 4 skipped. Client 232/232, type check clean, `gen_ui.py --check` and
      `gen_api_docs.py --check` current.
53. **Mutants.** `tools/mutate_p20.py` Q38–Q67 (ids provisional, D14), **30/30 killed**. They
    cover the store and its authority (Q38–Q44, Q66), the argv (Q45–Q52, Q55, Q64), the record
    and its redaction (Q53, Q54, Q57, Q58, Q65), the inventory failure (Q56, Q67) and the deny
    form (Q59–Q63). Q56's anchor moved with item 47 and was re-run, killed.
    - Re-run because their lines changed: P11 X17 and X36 (`manager.py`), **2/2 killed**.
      `test_mutation_suites_parse.py -k p20` passes (2/2).
54. **The full run** (`tests/v1` plus `tests/test_p05_seams.py`, `ARCHEUS_E2E=1`, slices A–E):
    - Run 1: **2700 passed, 1 failed, 14 skipped, 3 xfailed** (53 min). The failure is
      `test_spa_marker.py::test_the_marker_travels_once_from_the_execution_to_its_task` ("the
      marker begins at the execution: None"), the **known intermittent** (item 40), with the same
      signature. Slice E does not touch the graph or the marker. **Not fixed and not called
      green; its classification is unchanged.**
    - Run 2: **2700 passed, 1 failed, 14 skipped, 3 xfailed** (40 min). The failure is
      `test_spa_resources.py::test_an_accounts_policy_is_a_form_over_cores_route` ("timed out:
      the budget removed"), the known intermittent of items 22/48/90. `test_spa_marker` passed.
      This one was investigated (item 56), because slice E adds a read to the same section.
    - **`test_spa_marker`, measured** (alone, 20 runs each): **12/20 failed at `3b29661`** and
      **13/20 with slice E**. Same rate, so slice E does not change it. Its classification is
      unchanged. This is measurement only.
    - Run 3, on the tree as committed (item 56's wait and this record included): **2698
      passed, 3 failed, 14 skipped, 3 xfailed** (34 min). `test_spa_resources` passed.
      - `test_spa_marker`: the known intermittent, same signature.
      - `test_spa_arrival.py::test_reduced_motion_says_the_rise_and_pulses_nothing` ("timed
        out: the arrival is still announced"): P19 item 48's known intermittent. 0/10 alone.
      - `test_stream_takeover.py::test_a_concurrent_burst_keeps_exactly_the_last_two_registered`
        (`[63888, 63887] == [63887, 63888]`): **newly observed intermittent**, 0/20 alone. Core
        kept the right two streams; only the order differed. The test's spy appends the port
        after `_register` returns, outside the pool's lock, so two threads can append in the
        reverse of the pool's own order. That reads as a test-side race. It is slice C's test,
        and neither `sse.py` nor the test changed since `3b29661`. **Recorded, not fixed**
        (outside slice E).
    - Two earlier attempts were stopped by Claude Code for low system memory at about 79%, with
      other sessions' browsers running. They are not results.
    - `test_cli_help` (item 69) was not run.
56. **Found and fixed (test side): slice E widened `test_spa_resources`'s race.**
    - **Measured**, the test alone, 20 runs each: **1/20 failed at `3b29661`** (a detached
      worktree with its own SPA build) and **6/20 with slice E**. The intermittent predates
      slice E, but slice E made it more frequent.
    - **Cause**, captured on a failing run: the second save sent `budgets: {concurrency: 2}`
      (the blank was lost) and `project_allow: []` (the untick was kept). The first save's new
      version reaches the form through the `/v1/accounts` refetch, and `PolicyForm` resets its
      draft on `p.version`. The test then waited only for "Attempts at once" to read `2`, which
      it already did before the refetch. When the reset landed between `fill('')` and
      `uncheck()`, it wiped the first edit. Slice E's extra `/v1/opt-ins` read in the same
      section widens that window; the form itself is unchanged.
    - **Fix**: the test first waits until the form's `data-version` equals Core's version, then
      edits. Every check is kept; only a wait on the right condition is added. With the fix,
      **0/20 failed** (a scratch copy with the same wait: 0/20; deleted). The product
      behaviour (a version change resets the draft, so the form follows Core) is P19.5's design
      and is unchanged.
    - Re-run because the guarding test changed: P19.5 N271–N276 (`RES`), **6/6 killed**,
      N276 ("the form does not follow Core after a save") among them.
    - **For the user**: this changes how often a known intermittent fails, by fixing its cause.
      Items 22/48/90 list it; if the user prefers it kept as recorded, the fix is one `wait`
      to revert.
57. **Status: implemented, automated tests green apart from the known intermittent above.** No
    manual check was added. PV-19's observed run (D15, §14.E) is owed and NOT RUN, so PV-10's
    real-account half is unverified. P20 is not complete, and **slice F is not authorised**.

### Slice E closeout — PV-19 against the real CLI (2026-10-07)

Asked for by the user after slice E (2026-10-07): close out the evidence slice E owes, verify
against the real CLI without changing approved D6 behaviour, and mark OPEN anything that needs
a decision. **No code was changed.** Slice F was not started. ADR-0021 was not answered: no
`archeus terms` record was written and no Archeus Core ran the real harness.

58. **How it was run.** The assistant ran the real Claude Code CLI **2.1.291**
    (`C:\Users\mab\.local\bin\claude.exe`) directly, at the user's instruction:
    - 25 runs, all with `--model haiku`, on one account: `CLAUDE_CONFIG_DIR=C:\Users\mab\.claude`,
      a subscription OAuth login with no API key in the environment.
    - Every run used `subprocess.Popen` with a list argv, as `base.spawn` does, so the empty
      `--setting-sources` value reached the CLI as it would in production.
    - The ADR-0049 flags came from the shipped code: `sources.take` and `sources.flag_argv`,
      applied to a scratch project. That project holds a SessionStart hook in each of
      `.claude/settings.json` and `.claude/settings.local.json`, two `.mcp.json` servers, a
      project skill, and a `CLAUDE.md` canary.
    - The hook was the shipped `archeus/harnesses/hook.py`, installed through `--settings` as
      `adapter._settings` writes it. A scratch thread played Core on the hook mailbox.
    - Observation used the `init` event, `--include-hook-events`, `--debug-file`, marker files
      and a side-effect file. An `InstructionsLoaded` hook (also via `--settings`) logged every
      instruction file the CLI loaded.
    - The child environment dropped the parent session's `CLAUDECODE` / `CLAUDE_CODE_*` variables
      and carried `ARCHEUS_EXECUTION_ID`, as an execution's does.
    - **This is CLI-level verification, not D15's observed run**: no execution went through
      Core. The probe scripts and raw streams are in the session scratchpad (`pv19/`), not in the
      repository.
59. **PV-19 results.** PASS only where the run showed the property directly, never from the
    absence of an error.

    | # | Verification item | Result | Evidence |
    |---|---|---|---|
    | V1 | The CLI accepts an empty `--setting-sources ""` | **PASS** | 18 runs with the empty value: exit 0, `result: success`, no stderr |
    | V2 | The login survives the narrowing | **PASS** for this account | every run, under `""`, `user`, `project`, `local`, `--plugin-dir` and `--mcp-config`: `apiKeySource: "none"` and a completed model turn. Other accounts and API-key accounts: **NOT RUN** |
    | V3a | Hooks of an excluded source do not run; an opted-in source's do | **PASS** | markers: none under `""`; `project` alone under `project`; `local` alone under `local`; the user's SessionStart hooks only under `user` (8 `hook_started`) |
    | V3b | MCP: only opted-in servers, only through `--mcp-config` | **PASS** | `mcp_servers` empty under `""` and under `project`; `[pvmcp]` alone when `pvmcp` is opted in (`pvother` absent); the baseline without flags lists both plus 12 others |
    | V3c | Plugins: only through an opted-in source or `--plugin-dir` | **PASS**, with one finding | `--plugin-dir` for `caveman@caveman` loads `caveman` alone; the user source loads its 13. **Finding:** four built-in plugins (`cc-plugin-sec-default`, `-agents-md`, `-telemetry`, `-plugin-authoring`, all `@builtin`) load under every narrowing, and the inventory does not record them |
    | V3d | Skills: none with `--disable-slash-commands`; without it, only those of what is opted in | **PASS**, with one finding | none under `""`. With a plugin opted in, the plugin's skills load and the user's and the project's do not. **Finding:** without the flag, the CLI's own bundled skills (19: `deep-research`, `code-review`, `loop` …) load, and the inventory does not record them |
    | V3e | CLAUDE.md under the narrowing | **Observed rule** | an instruction file follows its setting source. Under `""`, **none** loads: `InstructionsLoaded` fires 0 times, the debug log says "project memory is off", and the canary is not known. `user` loads `~/.claude/CLAUDE.md` alone; `project` loads the project's file and every ancestor's (`C:\Users\mab\CLAUDE.md`, and `C:\Users\mab\.claude\CLAUDE.md` read as an ancestor's `.claude/CLAUDE.md`). Positive controls show the logging hook fires whenever a file loads |
    | V3f | The recorded inventory matches what loads | **FAIL** | the flags recorded are the flags given (the argv is derived from the record). The item statuses are not accurate. **Over-reported**: CLAUDE.md files (user, project, ancestors) and the skills of excluded sources are recorded `not_excludable` (loaded), but the CLI excludes them. **Omitted**: the four built-in plugins, the CLI's bundled skills, and an ancestor's `.claude/CLAUDE.md`. Hooks, plugins and MCP servers are recorded accurately |
    | V3g | Managed settings always apply | **NOT RUN** | no managed settings file exists on this machine (`C:\Program Files\ClaudeCode\` is absent) |
    | V4 | An opted-out source, plugin or MCP server is not loaded | **PASS** | V3a–V3d. Exclusion is the flags' work; exit code 2 is the hook's deny of a tool call (V5b), not how exclusion happens |
    | V5a | Allow: the `--settings` hook runs under `--setting-sources ""` and its allow lets the call through | **PASS** | `h_allow`: `PreToolUse:Bash` exit 0, the tool ran. This also confirms the premise that slice E's narrowing does not remove Archeus's own hook |
    | V5b | Deny: exit code 2, the reason on stderr, the call blocked | **PASS** | `h_deny`, `s_deny`: hook exit 2; the tool result is the reason verbatim ("PV19-DENY-REASON: not this one"); no side effect; the session continues. Claude Code labels it "hook error", which is cosmetic. (`s_deny_r2`: the model declined to call the tool, so that run is inconclusive and not counted) |
    | V5c | Halt: `{"continue": false}` stops the execution and the call it answers | **FAIL** | see item 60 |
    | V5d | A hook crash fails closed | **FAIL** (the hook's side behaves as built) | the hook itself is correct: `hook.py` raised `FileExistsError` and answered a halt at exit 0 with "the Archeus hook failed: FileExistsError". The CLI then ran the tool (`pv19-ran`), exactly as for a halt |
    | V5e | A Core that never answers fails closed | **FAIL** (the hook's side behaves as built) | the hook is correct: with `ARCHEUS_HOOK_WAIT=5` it halted at its own deadline and wrote `halted.json`. The CLI then ran the tool, as for a halt |
    | V5f | Premise: another exit code or a CLI timeout is non-blocking | **PASS** (confirms the premise) | `p_exit1`: exit 1, `outcome: error`, the tool ran. `p_timeout`: a 3 s timeout, `outcome: cancelled`, the tool ran. This is why the hook must never produce either, and it does not |
    | V5g | `guarded()`'s exit-2 fallback when even a halt cannot be written | **NOT RUN** against the real CLI | unit test E22 only |

60. **The halt finding (V5c–V5e); the halt measured on two commands, twice each; crash and timeout once each.** Claude Code 2.1.291 does not treat a
    PreToolUse `{"continue": false}` as a block of the call it answers:
    - **A tool the CLI allows by default** (`echo pv19-ran`, 3 runs: halt, crash, timeout):
      the tool **runs**, then the session ends (`terminal_reason: hook_stopped`).
    - **A tool the CLI's own permission check refuses** (`echo x > sidefx.txt`; a halt carries
      no allow, so the default mode refuses it), 2/2: the call is blocked by the permission
      check, but `continue: false` is **not honoured**. The model carries on, and the session
      ends `completed`.
    - **A candidate, probed for evidence and not implemented:** exit 0 with
      `{"continue": false, "stopReason": r, "hookSpecificOutput": {"hookEventName":
      "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": r}}`. It blocked
      the call (no side effect) and ended the session (`hook_stopped`), 2/2.
    - **Scope.** Every `halt` the hook answers is affected:
      - the global STOP sentinel and this execution's STOP, PAUSE and HANDOFF flags;
      - Core's `halt` decision;
      - a missing identity, a crash, and Core not answering.
    - **What a halt does in practice today.** Whatever the CLI would allow without asking runs
      once: read-only tools by default, plus anything an opted-in source's permission rules
      allow. When the CLI refuses a call, the session is not stopped.
    - **Not affected:** the Core-less e-stop's registry kill (slice A) and any path that kills
      the process. They do not depend on the hook's answer.
    - **The fake agent** models a halt as blocking before the tool runs, so every fake-harness
      test of a halt passes while the real CLI behaves differently. That is a fidelity gap,
      left as is: changing the fake before O4 is decided would choose a semantic.
    - **This contradicts two clauses of approved D6**: "halt keeps `continue: false`" and "a hook
      crash and a timeout are tested to fail closed". Choosing between them, or a form that
      satisfies both, is a new decision. It is **O4, OPEN**, and nothing was changed.
61. **The inventory's accuracy (V3f).** The flags, which are what decides what loads, are
    exact; the record's per-item statuses are not.
    - The statuses were slice E's reading of undocumented behaviour (item 44: "no flag Archeus
      passes is aimed at" CLAUDE.md; the skills reading in item 46).
    - V3e and V3d show the real rule: a CLAUDE.md or a skill follows its setting source.
    - Correcting `take()` to that rule, and recording the built-in plugins, bundled skills and
      ancestor `.claude/CLAUDE.md`, is a record-only change: the argv is identical.
    - This closeout was limited to the gate and its evidence, so it is **not applied**. It is
      **O5, OPEN** (the user's go-ahead), together with its tests and mutants.
    - The record over-reports (it says more may have loaded than did); it never hides a load
      from a settings source.
62. **What V3e means for executions (O6, OPEN).** With nothing opted in, an execution loads
    **no CLAUDE.md at all**: not the user's, the project's or any ancestor's.
    - That follows from approved D6 as the CLI implements it. It is not a defect of slice E.
    - The project's CLAUDE.md, which Archeus itself maintains, comes back only if the project
      opts in its whole `project` source, which also loads that source's hooks, permission rules
      and skills.
    - ADR-0049 listed this as a point to be observed ("whether user CLAUDE.md … survive[s] each
      narrowing"). Whether executions should be given the project's instructions some other way
      is the user's question.
63. **Review: an inventory that cannot be taken ends `workspace`, charged (item 47).**
    **Acceptable under the existing gate; no decision required.**
    - P11 note 11 sets the rule this follows: a failure to prepare what an execution runs in must
      be charged, because an uncharged end re-dispatches the task forever. That is what slice E
      measured (41 executions in 40 ticks) before the fix.
    - The inventory is part of that preparation: it is taken before the process exists, and
      nothing spawns without it.
    - The execution's own reason names the real cause ("the settings sources could not be
      inventoried: <error type>"). Only the stop reason's fixed copy ("its workspace could not
      be made") is approximate.
    - A dedicated stop reason would be a domain addition. It is available if the user wants it,
      and not needed for correctness.
64. **Review: P11's `SpawnFailed` re-dispatches forever (item 48). A decision is required:
    O7, OPEN.**
    - `manager.py` ends a spawn the node could not make with `stop_reason='binding'`, which is
      uncharged. P11 note 11 states that "`binding` again means only a stale plan binding (§7) or
      provider terms".
    - So the present behaviour contradicts P11's own definition, and it loops: 40 executions in
      40 ticks, measured in slice E.
    - It is not acceptable under the existing gate, and the fix is not implied. A missing binary
      is not plainly the task's own failure, which is what charging means. The options are:
      - a charged reason: the task fails after `max_attempts`;
      - an uncharged reason with a backoff or a harness breaker;
      - routing away from a harness that cannot spawn.
    - It is P11's code, outside slice E's authority. Nothing was changed.
65. **The secrets limitation, restated for slice I.** `run/exec/<id>/mcp.json` holds the
    **full** definitions of the opted-in MCP servers (command, arguments, URL, environment), so
    it may contain tokens.
    - It is written only when a server is opted in. It never enters the inventory, which records
      names only (E11, I08).
    - It belongs to **slice I's secrets review (D7)**: §14.B lists it there. It was not
      redesigned in E.
66. **Tests after the closeout.** No code changed, so only slice E's focused suites were re-run
    on `2a205a4`:
    - unit E01–E22, integration I01–I10 and H01–H02, G6, slice E's E2E, and
      `test_execution_units`: **148 passed, 2 skipped** (the existing http-only judge skips).
    - Known intermittents keep their classification:
      - `test_spa_marker` stays known;
      - the `test_stream_takeover` burst stays slice C's test-side race (item 54); nothing
        here re-examined it;
      - `test_cli_help` was not run.
    - No full run was made, because nothing changed since item 54's run 3.
67. **Status.** Slice E's code is unchanged and its automated evidence stands. **PV-19 is not
    passed.**
    - V1, V2 (this account), V3a–V3d, V4 and V5a–V5b PASS. V3e is recorded as an observed rule.
    - V3f and V5c–V5e FAIL. V3g, V5g and other accounts are NOT RUN.
    - D15's observed run through Core remains **NOT RUN**, gated by ADR-0021, which is still OPEN.
    - O4 (the halt) blocks a PV-19 sign-off and D6's fail-closed claim. O5–O7 are open.
    - P20 is not complete. **Slice F is not authorised and was not started.**

### Slice E closeout decisions — O4, O5, O6, O7 and the PV-19 rerun (2026-10-07)

Decided by the user on 2026-10-07 after items 58–67 (implementation: `6a09480`):
- **O4 approved**, as the minimal D6 correction the real CLI requires.
- **O5 approved**, as a record-correctness change only.
- **O6** recorded and not changed.
- **O7** deferred to P11.

Slice F was not started. ADR-0021 was not answered: no `archeus terms` record was written and no
Archeus Core ran the real harness. D15's observed run and the manual checks of §10 were not
run or altered.

68. **O4: every halt also denies the call it answers.**
    - `hook.decision('halt', r)` now returns `{"continue": false, "stopReason": r,
      "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
      "permissionDecisionReason": r}}` at exit 0.
    - **Rationale.** Item 60 measured that Claude Code 2.1.291 does not treat `continue: false`
      alone as a block of the call it answers:
      - a call the CLI allows by default runs first, and the session stops after it;
      - a call the CLI refuses itself is blocked, but the session goes on.
      The same probe showed that the two fields together block the call and stop the session.
    - **Scope.** This is the one function every halt answer goes through, so it covers every
      halt path D6 names:
      - the global e-stop sentinel;
      - this execution's PAUSE, STOP and HANDOFF flags;
      - Core's `halt` decision;
      - a missing identity, a hook crash, and Core not answering (the hook's own deadline).
      `guarded()`'s exit-2 fallback is unchanged.
    - **Unchanged:** what a halt means, which paths halt, `halted.json`, Core's handling of a
      halted process, and slice A's independent registry kill.
    - **The fake agent now models the real CLI.** `continue: false` with the deny blocks the
      call and halts. `continue: false` alone lets the call run, and the agent halts after it.
      E23 asserts both forms, so a halt that loses its deny fails in the fake-agent suite.
      PV-19 against the real CLI (item 70) stays the authoritative check.
    - **Tests changed:** E17 (exact halt JSON), E18, E19, E20's halt row (the call is not run),
      E47, E48 and E49 in `test_execution.py`, and `test_the_hook_speaks_claude_codes_vocabulary`.
    - **Mutants:** Q68 (the halt allows the call) and Q69 (the fake treats `continue: false`
      alone as a block) are killed.
69. **O5: the inventory records what loads (`inventory_version` 2).** `sources.take` now
    applies the rule PV-19 observed. The flags are untouched: `--setting-sources`,
    `--strict-mcp-config`, `--mcp-config`, `--disable-slash-commands` and `--plugin-dir` are
    derived exactly as before, and E25 asserts that recording more moves no flag.
    - **CLAUDE.md follows its setting source.**
      - The user's file follows `user`.
      - CLAUDE.md and `.claude/CLAUDE.md`, in the workdir **and in every ancestor**, follow
        `project`.
      - CLAUDE.local.md, in the workdir and every ancestor, follows `local`.
      - The ancestor `.claude/CLAUDE.md` and ancestor CLAUDE.local.md were missing and are now
        recorded. A probe on 2026-10-07 with a nested fixture observed each of these.
    - **A skill follows its source.** A skill from an excluded source is `excluded` even when
      `--disable-slash-commands` is dropped. Skills are also read from wherever a plugin declares
      them (its manifest's `skills`: one path or a list; each path is a skill, named by its
      SKILL.md, or a directory of skills). A declared path outside the plugin is not read (E25;
      Q76).
    - **What a plugin brings is recorded.** For a plugin opted in by name, and for one a settings
      source enables:
      - its skills and its hooks, including hooks declared inline in
        `.claude-plugin/plugin.json` (caveman's were missing), at that plugin's status;
      - its MCP servers, as `excluded`, because `--strict-mcp-config` keeps them out (observed
        for a plugin enabled by `user`);
      - `loads_as`, the manifest name the CLI reports it under (`vercel-plugin@vercel` loads as
        `vercel`).
    - **The account's synced skills** (`skills/synced/<id>/<name>`, which the CLI lists as
      `anthropic-skills:<name>`) are recorded under `user` with `via: synced`.
    - **The CLI's own** are recorded, not omitted, as two class items, because their names are
      the CLI's and cannot be read before the spawn:
      - `('cli', 'plugin', 'built-in plugins')`, `builtin`;
      - `('cli', 'skill', 'bundled skills')`, `builtin` when slash commands are on and `excluded`
        under `--disable-slash-commands`.
    - **Inventory semantics** (the `sources.py` docstring; the TUI and SPA say "no: predicted
      before the spawn, by the rule PV-19 observed" and label `builtin` "loaded, built into the
      CLI (outside Archeus's controls)"):
      1. **requested configuration**: `opt_ins` and `flags`, exactly what the process is given;
      2. **predicted loaded**: status `opted_in`, `recorded_only`, or `not_excludable` (now
         only managed settings);
      3. **not loaded**: `excluded`, or `not_found` (opted in, absent);
      4. **outside Archeus's source controls**: `builtin`.
      The record is taken before the spawn (`observed: false`). What a process **actually**
      loaded is its stream's `init` event together with the CLI's instruction-loading, and a PV
      compares the two (item 70's V3f does).
    - **Tests:** E01, E03, E04, E07 and E09 now assert the observed rule. E24 (the ancestor rule)
      and E25 (plugin contents, manifest hooks, declared skill paths, synced skills, plugin MCP
      under strict, `loads_as`, flags unchanged) are new. The G6 and E2E checks and the parity
      fixtures were updated.
    - **Mutants:** Q70–Q79 are killed. They cover:
      - a CLAUDE.md recorded as loaded whatever its source;
      - an excluded source's skills recorded as loaded;
      - the built-in plugins omitted;
      - the bundled skills recorded as loaded under the flag;
      - an ancestor's CLAUDE.local.md recorded under `project`;
      - manifest hooks, declared skill paths, synced skills, and an enabled plugin's contents
        ignored;
      - a plugin's MCP servers recorded as loaded.
      Q49's anchor moved with the restructured `skill_in` line; its mutation is unchanged.
70. **PV-19, rerun against the real CLI after O4 and O5.**
    - **Setup.** Claude Code 2.1.291, `--model haiku`, the same OAuth account
      (`C:\Users\mab\.claude`), the shipped `hook.py` and `sources.py`, and a stub Core on the
      hook mailbox.
    - **Runs.** 27 runs, all exit 0, `apiKeySource: "none"` and a successful result; 23 of them
      with `--setting-sources ""`.
    - **Fixture.** A project nested under a scratch ancestor, which holds a CLAUDE.md,
      CLAUDE.local.md and `.claude/CLAUDE.md` at both levels.
    - **Logging.** The `InstructionsLoaded` logger now writes one file per event. Item 59's
      single appended file lost a line when hooks ran in parallel, which first read as an
      ancestor CLAUDE.md not loading.
    - **Recorded result.** Every case: PASS or NOT RUN, none FAIL.

    | # | Item | Result | Evidence |
    |---|---|---|---|
    | V1 | Empty `--setting-sources ""` accepted | **PASS** | 23 runs, exit 0, success |
    | V2 | Login survives the narrowing | **PASS** for this account | every run: `""`, `user`, `project`, `local`, all three, `--mcp-config`, `--plugin-dir`. Other accounts and API-key accounts: **NOT RUN** |
    | V3a–V3d | Hooks, MCP, plugins and skills load only as opted in | **PASS** | as in item 59, re-observed in the seven cases below |
    | V3e | CLAUDE.md follows its source | **PASS** (observed rule) | per instruction-loading events, in all seven cases |
    | V3f | The recorded inventory matches what loads | **PASS**, 7/7 | an automatic comparison of every predicted-loaded item against the `init` event (MCP servers, plugins by `loads_as`, the built-in plugins, user/project skills, plugin skills, synced skills, the bundled skills), the instruction files loaded, and the hook markers. Cases: nothing opted in; `project`; `local`; `user`; all three; one MCP server; one plugin: **MATCH** in each |
    | V3g | Managed settings always apply | **NOT RUN** | no managed settings file on this machine |
    | V4 | An opted-out source, plugin or server does not load | **PASS** | V3a–V3f |
    | V5a | Allow, through the `--settings` hook under `""` | **PASS**, 2/2 | exit 0, the tool ran |
    | V5b | Deny: exit code 2, the reason on stderr | **PASS**, 2/2 | exit 2; the call blocked; the reason reaches the model; the session continues |
    | V5c | A halt blocks the call and stops the session | **PASS**, 4/4 | on a command the CLI allows by default (`echo`) and on one it would refuse (a write), twice each: the call not run, no side effect, `terminal_reason: hook_stopped`, no assistant text after. The hook's output was the O4 JSON |
    | V5d | A hook crash fails closed | **PASS**, 4/4 | the same two commands, twice each: "the Archeus hook failed: FileExistsError"; blocked and stopped |
    | V5e | Core never answering fails closed | **PASS**, 4/4 | `ARCHEUS_HOOK_WAIT=5`: "Archeus did not answer; denied and halted"; `halted.json` written; blocked and stopped |
    | V5f | Premise: another exit code, or a CLI hook timeout, is non-blocking | **characterised**, 2/2 each | exit 1 (`outcome: error`) and a 3 s CLI timeout (`outcome: cancelled`) both let the call run. That is why the hook never produces either; it does not rely on them |
    | V5g | `guarded()`'s exit-2 fallback against the real CLI | **NOT RUN** | it cannot be provoked from outside the hook. The exit-2 deny it produces is V5b's; unit E22 covers it |

71. **O6, recorded and not changed.** With no source opted in, an execution receives **no
    CLAUDE.md at all**, including the project's CLAUDE.md that Archeus itself maintains (V3e).
    - Restoring the project's CLAUDE.md today requires opting in the project's whole `project`
      source, which also brings that source's hooks, permission rules and skills.
    - D6 is not changed here. Changing the default would be a separate design decision.
72. **O7, deferred to P11.** P11 is not modified.
    - **Recorded for P11's follow-up:**
      - a process that cannot be started (`SpawnFailed`) ends its execution with
        `stop_reason='binding'`;
      - `binding` is uncharged, so no attempt is spent;
      - the task is therefore re-dispatched every tick, indefinitely (40 executions in 40 ticks,
        measured in slice E);
      - P11 note 11 defines `binding` as a stale plan binding or provider terms only.
    - The choice between charging, a backoff or breaker, and routing away from the harness is
      not made in P20.
73. **Tests after the closeout.**
    - Focused, on the closeout tree:
      - slice E's unit (E01–E25, 37), integration (I01–I10, H01–H02), G6, slice E's E2E,
        `test_execution_units`, `test_execution`, the e-stop drills and TUI parity: **330 passed, 2 skipped** (the
        existing http-only judge skips);
      - client: **232/232**, type check clean;
      - `gen_ui.py --check` and `gen_api_docs.py --check`: current.
    - Gate and traceability checks: `test_p05_seams`, `test_traceability`,
      `test_state_tables` and `test_mutation_suites_parse`, **100 passed, 1 skipped**; the
      design-gate and traceability selection of `tests/v1`, **44 passed**.
    - Mutants:
      - `mutate_p20`, after O4 and O5's first change: Q11, Q13, Q16, Q17, Q45–Q53, Q59–Q61,
        Q63, Q64 and Q68–Q74, **25/25 killed**;
      - after O5's second change (plugin contents, synced skills): Q45–Q53, Q64 and Q70–Q79,
        **20/20 killed**;
      - `mutate_p11` X10, `mutate_p16` M09/M13/M16, `mutate_p17` M07, `mutate_p19`
        P06/P07/P149 and `mutate_p19_5` N78–N82/N223/N259: **14/14 killed**;
      - the parse gate passes.
    - Known intermittents keep their classification (`test_spa_marker` known; the
      `test_stream_takeover` burst, slice C's test race; `test_cli_help` not run). A full run was
      not made: the closeout touches only the hook's halt answer, the fake agent, the inventory
      and its presenters, whose suites are above.
74. **Status: slice E is closed for its automated and CLI-level evidence.**
    - PV-19's real-CLI safety cases pass after O4 (V5c–V5e), and V3f passes after O5.
    - The focused and gate checks are green, and no new unexplained failure appeared.
    - **Still owed:**
      - D15's observed execution through Core (gated by ADR-0021, which is open);
      - V2 for other accounts, V3g and V5g (NOT RUN);
      - the manual checks of §10.
    - P20 is not complete. **Slice F is not authorised and was not started.**

## 13. As built
(Filled at the end of P20.)

## 14. Reconciliation after slice C (2026-10-05)

Asked for by the user before any slice D is proposed. **P20 is not complete.** Nothing here
decides anything; where a line needs a decision, it names whose.

### 14.A Completed (implemented and verified by automated tests)

| Item | Decision | Slice | State |
|---|---|---|---|
| Item 83, the e-stop with Core down; G5's `phase:P20` xfail removed; the e-stop drills (A01–A06, D13's e-stop half) | §4.1 item 83 | A | automated green; **A-M1 not run** |
| F7, Control → About states Core's answer | D3 | B | automated green; **B-M1, B-M2 not run** |
| F8, Control → About names the state, one action | D4 | B | automated green; **B-M1, B-M2 not run** |
| F4, a device's newest stream wins | D2 | C | automated green; **C-M2 not run** |
| Item 86, one desktop-shell credential at a time | D1 | C | automated green; **C-M1 not run** |
| F6, the command bar's Close button and backdrop tap | D5 | D | automated green (§12 item 40's known intermittent aside); **F6-M1 not run** |
| ADR-0049 exclusion, inventory, exit-code-2 deny (PV-10): the opt-in store and command | D6 | E | automated green (§12 item 54's known intermittents aside); **the real-account half is PV-19's (D15), NOT RUN** |
| Notifications out of P20 (to P21); plan and dependency records updated | D8 | records | done (`8fe7ce3`) |
| The Codex adapter to P23; G7's xfail re-marked `phase:P23` | D9 | records | done; no `phase:P20` xfail remains in `tests/` |

"Completed" here means implemented with its automated evidence. No slice is complete as a
gate while its manual checks are NOT RUN.

### 14.B Approved, not implemented

| Item | Decision | Slice (§5) | Note |
|---|---|---|---|
| The re-arm PIN step-up | D10 | its own slice (J's list) | approved **as proposed**: step-up on `POST /v1/rearm` from a **paired (non-local)** device, through the existing PIN path; rulebook §19 amended to "e-stop (confirm)". Not built. **Blocked** (the user, 2026-10-05) until the user reconciles it with V2-3 (§14.F); no interpretation is chosen here |
| The secrets review, with the DPAPI row amended if Core stores no API key | D7 (amendment) | I | not started; must list `run/exec/<id>/mcp.json` (the opted-in MCP servers' full definitions, possibly tokens; §12 item 65) |
| ADR-0052 tool removal (PV-22) | ADR-0052 (DECIDED) | F | not started and **not authorised**; its "except opted-in servers" part reads D6's opt-in store, which slice E built |
| ADR-0051 §2 boundary tests; the threat model | ADR-0051 (DECIDED) | G | not started |
| Remote-access threat-model review; dependency audit | plan §31.1 P20 | I | not started |
| Breaker drills, fuzzing | plan §31.1 P20 | H | **blocked on D12, D13** |

### 14.C Open decisions (the user's)

| # | Question | Blocks |
|---|---|---|
| O1 | Re-arm re-asks the plan gate for missions blocked only by the e-stop? (they stay BLOCKED today; P9's rule) | nothing in P20's slices; V2's stop-band copy (§14.F) |
| O2 | Does Pause all (strip, Work) get F7's post-action line? | nothing until answered |
| O3 / D14 | Are `Q01…` the suite's mutant ids? (Q01–Q67 used provisionally) | nothing; renaming is a text edit |
| Slice E's readings | §12 items 46 and 56: the readings of D6, the `test_spa_resources` wait. The `workspace` stop reason for an inventory failure was reviewed and is acceptable under P11 note 11 (item 63) | nothing; each is applied and reversible |
| O6 (recorded) | No CLAUDE.md reaches an execution by default (§12 item 71). Changing that default would be a separate design decision; none is pending in P20 | nothing in P20's slices |
| O7 (deferred) | P11's `SpawnFailed` re-dispatch loop: charge, backoff/breaker or routing (§12 item 72) | P11's follow-up; a live loop when a harness cannot spawn |
| D11 | Owners of R13-03 to R13-13 (none P20's as proposed) | the P21–P23 entries |
| D12 | Fuzzing: stdlib harness or `hypothesis` | slice H |
| D13 | The breaker drills (the e-stop half is built) | slice H |
| §5 order | The order of the slices after E | which slice is next |

### 14.D Manual verification outstanding

The six checks, with procedure, expected result and status, are the table in §10: **A-M1,
B-M1, B-M2, F6-M1, C-M1, C-M2**, all NOT RUN (C-M2 has a desktop and a phone sub-check, each
NOT RUN). F6-M1 can be run now that slice D exists. None was removed or downgraded.

### 14.E D15, the observed run

- **What it is.** D15 (approved) decides how P20 reports the real-account verification: built
  and tested against the fake harness and the recorded stream; the observed run on a real
  account is a manual check owed by the user under ADR-0021's permit; until it is done, P20 is
  at most **"ready except for the observed run"**, and every undocumented flag effect stays a
  verification item, never a fact.
- **What the run must show.**
  - **PV-19** (ADR-0049): one real execution per ADR-0049 source rule; the recorded inventory
    matches the flags; the account's login survives the narrowing, or the recorded fallback is
    shown; the exit-code-2 deny and the halt behaviour observed.
  - **ADR-0052 §7** (PV-22): one observed execution confirms that a removed tool is never
    offered or called, and shows how the `mcp__*` deny behaves beside an opted-in server.
- **What it needs first.** ADR-0021 answered for the harness (it is **OPEN**: `archeus terms
  claude_code permit` is the user's act); PV-10 built (slice E, **built**: §12 items 42–57,
  with its verification items in item 49); PV-22 built (slice F, not started).
- **Status: nothing has satisfied D15.** No observed run through Core has been performed and
  none is claimed. Slices A–D do not touch the execution boundary; slice E does, and every
  effect of its flags that the documentation does not state is recorded `observed: false`.
- **CLI-level verification (2026-10-07, §12 items 58–67).** The real CLI 2.1.291 was driven
  directly with the argv Archeus builds, the real `hook.py` and a stub Core, on one account.
  - **PASS:** the empty `--setting-sources`; the login under every narrowing; the exclusion of
    hooks, MCP servers, plugins and skills; the allow; the exit-code-2 deny.
  - **FAIL:** the halt, and therefore the crash and the timeout, does not block the call it
    answers (O4); the inventory's item statuses (O5).
  - **NOT RUN:** managed settings, other accounts, and the exit-2 fallback against the real CLI.
  - This does not replace the observed execution through Core, which stays gated by ADR-0021.
- **After O4 and O5 (2026-10-07, §12 item 70):** the rerun passes.
  - V5c–V5e: 4/4 each; the halt, crash and timeout block the call and stop the session.
  - V3f: 7/7; the inventory matches what the CLI loaded.
  - V1, V2 (this account), V3a–V3e, V4, V5a and V5b pass; V5f is characterised.
  - V3g, V5g and other accounts are NOT RUN.
  - **D15 is still not satisfied:** the observed execution through Core remains NOT RUN,
    gated by ADR-0021.

### 14.F P20 and the V2 product-design reassessment

The other session's V2 documents (uncommitted, not modified here) were read for this map:
`ARCHEUS_V2_PRODUCT_UX_REASSESSMENT.md`, `ARCHEUS_V2_LATER_UI_LV2_1_GATE.md`,
`ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md`, `ARCHEUS_V2_UI_ARCHITECTURE.md`, the LV2 rulebook, and
`lv2-dr2`/`lv2-dr8`. **The V2 direction is under reassessment by the user, who does not
consider the current prototype good enough** (hierarchy, visibility, explainability, a sense
of what Archeus is doing when opened, a deliberate mobile application, desktop identity). LV2-1's
automated results are **not** permission to implement the current V2 design, and nothing in
P20 relies on them.

**P20 items V2 depends on.** Every V2 production phase starts after P26 (LV2-2 plan), so all of
P20 precedes V2 production. Four P20 outcomes are load-bearing for V2's designs:
- **D10's re-arm step-up**: V2's "Resume work…" (SS-6) is designed on it.
- **O1**: what a resume does to the missions the stop blocked; V2's stop band says "stays
  blocked until you resume Archeus and unblock it", which is today's behaviour.
- **D7's secrets review and the remote-access review (slice I)**: DR-8 (check output stored
  unredacted in two places) and DR-2 (whether a paired phone sees local-path remotes) both
  name P20 as the owner of their at-rest and remote questions.
- **D3/D4's wording**: V2's safety-state vocabulary (below).

**V2 questions independent of P20.** The information architecture (LD-2), the three directions
(A, B, C) and the choice between them, visual hierarchy and identity, explainability and the
*what · where · why · evidence · next* frame, the phone as a deliberate application (LV2-3),
the day's light (LD-4), the budget (LD-1), and the data contracts DR-1, DR-3 and DR-4 apart from
any security question in them.

**V2 questions that must not alter P20's safety and security semantics.** Any V2 decision may
change words and placement; none may change, without a new gate:
- the e-stop's availability with Core down, and that only the tray and `archeus estop` hold
  that local authority (the page holds none, §12 item 15);
- "no new work until re-armed", and a re-arm counting only once Core confirms it;
- protection against accidental activation (item 83). LD-7's two-press interaction replaces
  slice B's confirmation after P26, so it must keep that requirement tested, as the LV2-2 plan
  says;
- D10's step-up on re-arm;
- authentication before any action; the stream cap and takeover scope (D2); the shell's slot
  and its separation from the local token (D1, §12 item 34);
- a notification never approves (the LV2 rulebook's rule 18 already agrees).

**Contradictions found (recorded, not resolved).**

| # | What disagrees | P20 side | V2 side | Whose decision |
|---|---|---|---|---|
| V2-1 | **"Armed" means opposite things.** | D4's approved copy: "Armed: Archeus accepts new work" (`present.ts` `armedText`), Re-arm | SS-1/SS-6: the safety state is never "armed"/"disarmed" and "re-arm" is not used; Core's `estop_armed()` and its policy reason ("emergency stop armed: every action is denied") use *armed* for **stopped**. The reassessment proposes this as a P20 follow-up (its Q3, V-4) | the user. P20's copy is unchanged |
| V2-2 | **The e-stop's confirmation.** | Slice B keeps a confirmation dialog (Cancel default); D10 amends rulebook §19 to "e-stop (confirm)" | LD-7 (approved): two presses, a 3 s lapse, **no dialog**, after P26 | the user, through LD-7's own production gate. Not a P20 semantics change if accidental activation stays tested; the §19 wording would need amending then |
| V2-3 | **Who needs a PIN to resume.** | D10 as approved: step-up on re-arm **from a paired (non-local) device**; the local desktop asks none | SS-4's hint says "resuming needs a PIN" and SS-6 applies on every surface, the local desktop included | the user: either V2's copy is device-specific, or D10's scope widens. P20 does not change D10 |
| V2-4 | **Push ownership.** | D8: notifications and push moved out of P20, to P21 | `ARCHEUS_V2_UI_ARCHITECTURE.md` ("P20: push, credentials") and the LV2-2 plan ("P20's push and credential review (LV2-3)") still name P20 | records only: D8 stands; the V2 documents are stale on this point and are not edited here |
| V2-5 | **DR-8's at-rest question.** | D7's approved scope: enumerate every secret written at rest | DR-8 asks whether its at-rest question (check output may hold secrets) is handed to D7 | the user: an open hand-off, not a conflict |

### 14.G Is there a defensible next slice? (written after slice C; slice D has since been done)

Yes, without any new decision: **D (F6, D5)** is approved, small, listed next in §5, confined to
V1's command bar and needed before F6-M1 can run. **I** (the secrets review, the remote-access
review and the dependency audit) is equally free of open decisions, touches no UI, and is what
DR-8 and DR-2 wait on. The D10 slice is approved but should start with the user confirming its
scope against V2-3. E, H and part of F wait on D6, D12 and D13. **The order is the user's (§5
order is open); nothing starts until the user authorises it.**

*After slice E (2026-10-06):* E is done (§12 items 42–57). F, G, H, I and J are not authorised.
I is still free of open decisions; F now has D6's store to read; H waits on D12 and D13.

*After slice E's closeout (2026-10-07):* PV-19's CLI-level run found O4, which needs the user's
decision before a fix can be built. Nothing is authorised by this note.

*After the closeout decisions (2026-10-07):* O4 and O5 are built and PV-19's CLI-level rerun
passes (§12 items 68–74). O6 is recorded and O7 is deferred to P11. F, G, H, I and J are not
authorised.

