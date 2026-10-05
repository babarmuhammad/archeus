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
| **Not decided** | D6 (ADR-0049 opt-in store and command), D11 (R13-03 to R13-13 owners), D12 (fuzz tooling), D13's breaker drills, D14 (mutant ids), the order of §5 after slice A; and the questions §4.2 adds |

### 4.2 Open questions found during implementation (the user's, not inferred)

| # | Question | Found in | Status |
|---|---|---|---|
| O1 | Should a re-arm re-ask the plan gate for missions that `builtin:estop` blocked while Core was disarmed? Today they stay BLOCKED after the re-arm (P9's existing rule, both e-stop paths) | slice A, §12 item 5 | **open**; nothing changed |
| O2 | F7 also names the window's **Pause all** with nothing running. D3's approved text names only Control → About's Emergency stop. Does Pause all (strip, Work) get the same post-action line? | slice B, §12 item 17 | **open**; not built |
| O3 | D14: are `Q01…` the suite's ids? Slices A and B use them provisionally (Q01–Q17) | slices A, B | **open**; ids not renamed |

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
- **Manual, owed by the user:**
  - the tray Emergency stop with Core down on the real Windows display (item 83's M1 step 5,
    now expected to stop; §12 item 10);
  - Control → About in the real Qt shell and on a phone (slice B, §12 item 23);
  - F6 on a real phone;
  - the observed runs (D15). Until they are done, P20 is at most "ready except for the observed
    run".

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
31. **Evidence still needed for P20 exit from this slice.**
    - **Manual, owed by the user (proposed for §10; not yet in it until the user agrees):**
      - In the real Qt shell: quit and relaunch `archeus gui` (and once, end its process from
        Task Manager instead of quitting). Control → Clients then shows exactly one ACTIVE
        "desktop shell"; the tray's Pause all and Attention count work.
      - In a real browser and on a phone: reload twice quickly. The page reconnects at once
        (item 112's 19.9 s was measured that way).
    - **Pre-P20 shell rows** (item 26) stay until revoked by hand from Clients. Whether to
      sweep them is the user's call; nothing here does it.
    - Nothing else of P20's §10 is affected by this slice.

## 13. As built
(Filled at the end of P20.)

