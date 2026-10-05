# P20 design gate — security and trust hardening

Status: **APPROVED IN PART** (the user, 2026-10-05): D1, D2, D3, D4, D5, D10 and D15 as
proposed; D7 as an amendment; D8 and D9 moved out of P20. **D6, D11, D12, D13 (breaker drills),
D14 and the order of §5 beyond slice A are not yet decided** and are not inferred (§4.1).
Implementation is authorised for **slice A only**, then stops for the user's review. Anything
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
| **D7** DPAPI | **Approved as an amendment.** First establish the evidence for what credentials and API keys Core stores. If Core stores no API key needing DPAPI, amend plan §27's obsolete requirement instead of manufacturing DPAPI work; record the evidence and rationale here (slice I) |
| **D8** notifications | **Moved out of P20** to a later phase; the plan and dependency records are updated. Owner: **P21** (attention and Health), whose design gate decides the push transport or records its deferral |
| **D9** Codex adapter | **Moved to P23.** No artificial evidence. It returns to discussion only if a real Codex installation and stream become available and the user reconsiders ownership. G7's xfail is re-marked `phase:P23` |
| **D10** mobile e-stop | **Approved as proposed.** No PIN before Emergency stop, which stays the fastest safety action. Re-arm is the privileged operation and requires the PIN step-up (built in its own slice, not in A) |
| **D15** observed run | **Approved.** No observed-run evidence is claimed before it is performed. P20 may complete its implementation and other evidence, but stays **"ready except for the observed run"** until ADR-0021 is resolved and the real run is done |
| **Item 83** | **Proceed exactly against the existing design** (execution-architecture §10 path 2, p11 §13.4, D26). Acceptance: the e-stop is available with Core down; the local safety action actually happens; no new work starts afterwards; re-arm restores starting work; the operation is safe against accidental activation; the STOP file and the process registry are reused, with no parallel mechanism. The requirement is not weakened because the mechanism exists |
| **Not decided** | D6 (ADR-0049 opt-in store and command), D11 (R13-03 to R13-13 owners), D12 (fuzz tooling), D13's breaker drills, D14 (mutant ids), the order of §5 after slice A |

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
- **Manual, owed by the user:** the tray Emergency stop with Core down on the real Windows
  display (item 83's M1 step 5, now expected to stop); F6 on a real phone; the observed runs
  (D15).

## 11. Deviations declared up front
- The plan's P20 entry does not list notifications, Codex or the re-arm step-up; this gate
  surfaces them (X1–X3) rather than silently including or dropping them.
- F7 is read as a missing result acknowledgement (X5); if the user meant a pre-confirmation on
  Pause all, D3 changes.

## 12. Deviations and new decisions for the user's review
(Filled during implementation.)

## 13. As built
(Filled at the end of P20.)
