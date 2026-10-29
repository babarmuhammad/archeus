# P20 design gate — security and trust hardening

Status: **APPROVED IN PART** (the user, 2026-10-05): D1, D2, D3, D4, D5, D10 and D15 as
proposed; D7 as an amendment; D8 and D9 moved out of P20. **D6 approved as written** (the user,
2026-10-06). **D11, D12, D13 (breaker drills), D14 and the order of §5 after slice F are not yet
decided** and are not inferred (§4.1). Implementation was authorised one slice at a time: **A, B,
C, D, E and F are implemented with automated evidence; A–D await their manual checks (§10). E is
closed for its automated and CLI-level evidence (2026-10-07, §12 items 68–74): O4 and O5 were
approved and built, and PV-19's real-CLI cases pass. F is closed for its automated and CLI-level
evidence (2026-10-07, §12 items 75–91): F.0 probed Claude Code 2.1.292, C1, C2 (L1, L2) and C3
were decided and built, and the tool removal was verified against the real CLI with no model
call. D15's observed run through Core is NOT RUN (ADR-0021 open). **G was started and is PAUSED**:
its verification found two Critical OS-confinement findings (G1 credential reach, G2 local-token
reach, §12 items 92–97), so ADR-0051 §2 is not satisfied as built; these are OS-boundary issues,
not P11 defects, remediated by PV-20 (prerequisite PV-13 study delivered 2026-10-07; PV-20:
decisions recorded and approved, ADR-0053; its open questions resolved except implementation and
evidence dependencies and P11's O7; implementation not started; verification not performed — §12
item 98; the final architecture audit's blockers A1–A6 decided and A7 corrected, ADR-0053 §7 —
§12 item 99; A2 and A5 confirmed — §12 item 100; slice S0, the Gap A three-state sentinel
determination, built 2026-10-08 as the only authorised PV-20 slice, the isolation mechanism not
started — §12 item 101). P23 owns the network-egress gap (G3). P20 is not complete; no slice
after F is authorised, and H–K were not started** (§14).
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
  or `--disallowedTools`, and no `--add-dir`. *(Verified state at `59281ac`. Under PV-20, ADR-0053
  §7 A2 — not implemented — an isolated execution never receives the account home: its
  `CLAUDE_CONFIG_DIR` is a fresh per-execution directory with no provider login, and the settings
  file is Core-write / execution-read; §12 item 99.)*
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
| **Slice F** (ADR-0052 PV-22) | **Authorised** (the user, 2026-10-07) after F.0 (§12 item 76), with: **C1** Variant 1, the mapping intersected with a version-stamped snapshot of the installed CLI's names, ADR-0052's completeness language unchanged, `LS`/`MultiEdit` recorded as mapped but not offered; **C2** `mcp__*` with nothing opted in, otherwise a deny per excluded server in Claude Code's normalised name; **L1** a name colliding with an opted-in server's is not denied; **L2** an unnameable source is left to `--strict-mcp-config`; **C3** `Skill` allowed exactly when an opted-in source or plugin brings a skill, judged as an unclassified `exec`. As recorded in §12 item 77; as built, items 78–89 |
| **Not decided** | D11 (R13-03 to R13-13 owners), D12 (fuzz tooling), D13's breaker drills, D14 (mutant ids), the order of §5 after slice F; and the questions §4.2 adds |

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

   *Under PV-20 (ADR-0053 R6-A; not implemented; §12 item 99):* for an isolated execution the
   drill's first step inverts — Core's death ends the isolated tree, so no process lives on for
   the e-stop to kill. `test_A06` and A-M1 stay valid for executions that are not isolated and gain
   an isolated variant when PV-20 is built.

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
   which is PV-20's ground, not P20's. *Qualified 2026-10-07 (ADR-0053 R6-A; §12 item 99):* under
   PV-20 only Core holds a Job, so the handle-based kill closes the gap when Core is up (Core ends
   the Job) or dead (kill-on-close). The Core-less `archeus estop` path holds no Job reference and
   keeps this ceiling.
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
      *Under PV-20 (ADR-0053 §7 A2; not implemented): no MCP opt-in is admitted to an isolated
      execution, so this file is not written for one; §12 item 99.*
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
    - *Under PV-20 (ADR-0053 §7 A2; not implemented):* **no MCP opt-in is admitted to an isolated
      execution** (confirmed by the owner, 2026-10-07; §12 item 100), so the file is not written for
      one; it stays a secrets-review item for executions that are not isolated (§12 item 99).
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

### Slice F authorisation pass and F.0 (2026-10-07)

Asked for by the user after slice E's closeout: establish slice F from this gate, then probe the
installed CLI (F.0, record-only), then decide. Nothing was changed in either pass.

75. **Slice F's scope, from this gate, with nothing added.**
    - §5 item 6: ADR-0052 PV-22, the CLI's tool names read first, the mapping, the argv,
      completeness, drift, the execution-architecture §2 amendment, p11 §18's as-built note.
    - ADR-0052 §1–§6 and §8, PV-22's row, the plan's P20 entry ("Tool removal") and §1.5 ("its
      version is read at the start of slice F").
    - It depends on slice E alone: the opt-in store (the D6 row of §4.1 keeps "except opted-in
      servers" for F) and the argv E's flags already build.
    - Not F's: ADR-0052 §7's observed run (D15) and the live measurement of what excluding the
      subagent and todo tools changes.
76. **F.0: Claude Code 2.1.292, record-only, no model call** (the user's authorisation,
    2026-10-07). 60 cases, scripts and streams in the session scratchpad (`f0/`), not the
    repository.
    - **How there was no model call.** 21 cases ran on the account's own subscription login and
      the first-party host, with every HTTPS connection refused through a proxy (each debug log: 6
      refused connections, no response), stopped at `init`. 39 ran against a local stub of the
      Messages API on loopback, with a dummy key and a scratch account home holding only the real
      one's cached feature flags; the stub scripted the model's tool calls and recorded which tools
      the CLI offered.
    - **The tool set** under slice E's flags is 32 names, identical to 2.1.291's: Bash,
      CronCreate, CronDelete, CronList, DesignSync, Edit, EnterWorktree, ExitWorktree, Glob, Grep,
      ListAgents, Monitor, NotebookEdit, PowerShell, PushNotification, Read, RemoteTrigger,
      ReportFindings, ScheduleWakeup, SendMessage, ShareOnboardingGuide, Task, TaskCreate,
      TaskGet, TaskList, TaskStop, TaskUpdate, ToolSearch, WebFetch, WebSearch, Workflow, Write.
      `Skill` is added while slash commands are on. **`LS` and `MultiEdit`, both in ADR-0052 §2
      and in the canonicaliser, are not offered.**
    - **`--tools`** drops an unknown or wrongly cased name without a word (exit 0, no stderr):
      `--tools LS` is no tool at all. `--tools ""` is accepted and means no tool. Each mapped set
      loads exactly as named. `Task` (as `init` names it) and `Agent` (the API's name, which
      `--tools` also accepts) are one tool.
    - **`--disallowedTools`** with a bare name removes the tool exactly as absence from `--tools`
      does: never offered, "No such tool available", and the hook never sees the call. `--tools`
      does not affect MCP tools.
    - **MCP patterns.** `mcp__*` removes every MCP tool, an opted-in server's too.
      `mcp__<server>`, `mcp__<server>__*` and `mcp__<server>__<tool>` each remove one server's.
      `mcp__pv` is not a prefix; `mcp__pvo*` is a glob. Comma-joined patterns all apply; a
      pattern for a server that is not loaded is accepted silently.
    - **MCP names.** A tool's name normalises its server's: `.` and `@` become `_`; `-` and case
      are kept. A deny written with the raw name matches nothing. Two servers whose names
      normalise alike are both removed by one deny.
    - **No allow overrides a deny**: a hook allow, `--allowedTools`, a settings allow, or a
      narrower allow under `mcp__*`.
    - **Skill** exists only while slash commands are on, and any `--tools` without it removes it.
      An opted-in skill still loads (it is in `init.skills`), but a call to it is refused.
    - **WebFetch and WebSearch.** On the subscription login tool search is on (`mode=tst`) and 18
      tools are deferred, these two among them. A `--tools` without `ToolSearch` defers nothing:
      both are offered directly and both were called. With `ToolSearch` listed they are deferred
      again.
    - **The set depends on the login and the host**: an API key against another host is offered
      29 (no RemoteTrigger, ShareOnboardingGuide or ToolSearch).
    - **Outside the repository**, the CLI created an empty `memory` folder under the account's
      `projects/` for the scratch directory, and its own project entry. Left for the user.
77. **The decisions (the user, 2026-10-07), recorded as given.**
    - **C1, Variant 1.** ADR-0052's mapping and completeness language stay as written. The
      installed CLI is authoritative for the names passed: the mapping is intersected with a
      checked-in, version-stamped snapshot of what it offers, and a mapped name it does not offer
      is never passed. The canonicaliser is not changed to drop `LS` or `MultiEdit`. The
      completeness test stays (every canonicaliser tool has a mapping). The snapshot records `LS`
      and `MultiEdit` as mapped but not offered. Every tool in the snapshot is mapped or explicitly
      excluded by default. `Task` and `Agent` are one tool. **Not** "mapped or retired".
    - **C2, the normalised MCP deny.** Nothing opted in: `--disallowedTools "mcp__*"`. Something
      opted in: `--strict-mcp-config`, `--mcp-config` holding only the opted-in servers, and a
      deny for each excluded server the inventory names, in Claude Code's normalised name; never
      a raw name holding `.` or `@`; never relying on an allow overriding a deny.
    - **L1.** An excluded server that collides with an opted-in one after normalisation is left
      out of the deny, `--strict-mcp-config` and the opted-in-only `--mcp-config` stay, and the
      collision is recorded as a limitation of the deny list. No new D6 rule rejects the opt-in.
    - **L2.** A source the inventory cannot name (a local-scope `.claude.json` server, a claude.ai
      connector) gets no invented name and no fake rule: `--strict-mcp-config` excludes it, and
      that is documented as a limitation. D6 is not changed.
    - **C3, `Skill` conditionally.** `Skill` is allowed exactly when an opted-in source or plugin
      brings a skill, never otherwise, and `--disable-slash-commands` is kept as it was. The hook
      judges `Skill` as an unclassified `exec`. No other CLI tool is added because it is offered.
    - **Slice F authorised**, alone; G to K not.

### Slice F — PV-22, ADR-0052's tool removal (2026-10-07)

Authorised by the user (2026-10-07) with C1, C2 (L1, L2) and C3 as item 77 records them. Nothing
of G to K, D10, P11's `SpawnFailed` (O7), P21, P22, ADR-0037 or V2 was touched; the inventory is
slice E's version 2, unchanged.

78. **As built: `archeus/harnesses/claude_code/tools.py`**, stdlib only.
    - `TOOLS` and `NO_TOOL` are ADR-0052 §2's rows, unchanged, `LS` and `MultiEdit` included.
    - `SNAPSHOT` holds the version (2.1.292), the date read, the models read, the 32 names, what
      only some models offer (`model_only`, item 80), what slash commands add (`Skill`) and what
      is mapped but not offered (`LS`, `MultiEdit`). `EXCLUDED` names the 22 offered tools no
      class maps. `ALIASES` makes `Agent` and `Task` one tool.
    - `tool_argv(action_classes, inventory)`: `--tools` always, the classes' tools intersected
      with the snapshot, in the mapping's order, plus `Skill` (item 83); `""` when nothing is
      mapped, because left out it would mean every tool. Then `--disallowedTools` per C2
      (item 82), when there is something to deny.
    - The Claude Code adapter appends it after slice E's flags. `--settings` (the hook) is passed
      as before, always; `--allowedTools` never.
79. **C1 as built.** Only offered names are passed; the canonicaliser is untouched; the
    completeness test is ADR-0052 §6's, unchanged (F10: every action class is mapped or has no
    tool of its own; every tool the canonicaliser names is mapped, to the class it classifies
    it as). F11 holds the drift rule: every offered name, `Task`/`Agent` as one, is mapped,
    `Skill`, or excluded by default, with no overlap; mapped minus offered is exactly the
    snapshot's `LS` and `MultiEdit`. A stale or misspelt name in the snapshot can only remove a
    tool, never add one, and the live comparison (item 81) reports it.
80. **Found during the slice: the tool set also depends on the model.** On 2.1.292, `haiku`
    offers TaskCreate, TaskGet, TaskList and TaskUpdate; `sonnet`, `opus` and `fable` do not
    (the default model of the account, `opus`, among them). Every mapped tool is offered on all
    four. The snapshot records the four as `model_only`; all four are excluded by default, so no
    decision moves. F11 fails if `claude_models()` gains a model the snapshot was not read for.
81. **The live drift comparison: `tools/claude_tool_drift.py`**, record-only by F.0's method,
    with no model call.
    - For each model it reads `init.tools` with slash commands off and on.
    - Once more it reads `init.tools` with `--tools` naming every mapped name plus `Skill`, which
      proves the CLI keeps exactly the offered ones.
    - It compares everything with the snapshot and exits 1 on any drift.
    - Run 2026-10-07 on 2.1.292: **no drift on any of the four models**.
    - It is a tool, not a suite test: CI has no CLI and no account, and nothing in CI claims the
      comparison.
82. **C2 as built.**
    - **Nothing opted in:** `mcp__*`.
    - **Something opted in:** one `mcp__<name>` per MCP server the recorded inventory holds as
      `excluded` under `user` or `project`, sorted. `mcp_name` turns every character but letters,
      digits, `_` and `-` into `_`; that covers every character a D6 name may hold.
    - **L1:** a name that normalises to an opted-in server's is left out. Nothing is written at
      run time, because the inventory stays version 2 (item 85). The collision is visible in the
      record itself: an excluded and an opted-in server whose names normalise alike.
    - **L2:** a plugin's MCP server is not named either. Claude Code's tool-name form for a
      plugin's server was never observed, because `--strict-mcp-config` kept every one out (E25,
      PV-19, F.0). A local-scope server and a claude.ai connector are not in the inventory at all.
      `--strict-mcp-config` is what excludes all three.
83. **C3 as built.**
    - `Skill` is added exactly when the recorded inventory's `disable_slash_commands` is false,
      which is slice E's own rule: a skill arrives through an opted-in source or plugin. The
      record decides both flags, so they cannot disagree.
    - The canonicaliser does not know `Skill`, so the hook judges every call to it as one
      unclassified `exec` (F09). It does the same for `PowerShell` and every opted-in MCP tool.
    - **A consequence, for the user's attention:** P9 never ALLOWs an unclassified action (it
      asks), so every call to an opted-in skill or MCP server waits for an approval. R03–R05
      approve one and see it run.
84. **The fake.**
    - `FakeHarness(tools=True)` passes the same `tool_argv`.
    - The fake agent honours the tool flags as F.0 observed them: a tool absent from `--tools`, a
      bare or `mcp__<server>` or glob deny, an MCP server `--strict-mcp-config` did not load from
      `--mcp-config`, and `Skill` under `--disable-slash-commands` all emit `tool_unavailable`.
      Such a call never reaches the hook and never runs, and the agent goes on.
    - **A reading, applied:** removal has its own switch, not slice E's `sources`. The judge's
      default Core and the integration rigs keep `sources=True` alone. Several existing scenarios
      script a tool their task does not hold: G6's locked deny scripts `Bash` under the default
      plan's `write_repo`, and S05 scripts `git push`. They test the hook beneath removal, which
      removal would never let those calls reach. A judge scenario marked `tool_removal` gets
      both.
    - The fake agent's `Skill` refusal under `--disable-slash-commands` applies to the `sources`
      fake as well. No existing scenario scripts `Skill`.
85. **Why slice E's inventory stays version 2.** ADR-0052 does not require recording the tool
    flags, and D6's inventory list does not include them; only the XR-14 brief's estimate (§8)
    said so, and that is analysis, not a decision. The tool flags are reproducible from records:
    the task's `action_classes`, plus the recorded inventory's MCP items and its slash-commands
    flag. The evidence is the argv (the fake's `started` event) and the CLI's own `init`
    (item 89). G6 asserts the inventory is still version 2 with no tool flag in it.
86. **No new failure path.** Claude Code accepts every argv F builds (item 89) and drops an
    unknown name rather than refusing to start. So F adds nothing that could reach P11's
    `SpawnFailed` loop (O7), which stays deferred and untouched.
87. **Tests.**
    - `tests/v1/unit/test_tool_removal_units.py`, F01–F14 (34 collected), cover:
      - every one of the 8192 sets of action classes;
      - `--tools` always present, `--settings` always, `--allowedTools` never;
      - the empty `--tools ""`;
      - the MCP deny, normalised names and the collision rule;
      - `Skill` against real inventories;
      - unclassified `exec` for `Skill`, `PowerShell` and an MCP tool;
      - completeness against `ACTION_CLASSES` and the canonicaliser, and the snapshot's drift
        rule;
      - the fake agent's `--tools`, MCP and `Skill` model.
    - `tests/v1/integration/test_tool_removal.py`, R01–R05 (real Core):
      - a removed tool never runs and never reaches the hook;
      - a held tool is still judged, and denied by a DENY made after the start;
      - an opted-in MCP server is asked, approved and run while the excluded ones are denied by
        name;
      - the L1 collision;
      - `Skill` off, and on through an opted-in `user` source.
    - G6 (`test_g06_security.py`): one `tool_removal` scenario, over both judge bindings.
    - **Focused run: 382 passed, 2 skipped, 1 xfailed.** It covered F's and E's unit and
      integration suites, G6, slice E's E2E, `test_execution_units`, `test_execution`, the adapter
      contract, the e-stop drills and TUI parity. The skips are the existing http-only judge cases;
      the xfail is the contract's Codex case (`phase:P23`). Slice E's own tests are unchanged and
      pass.
    - **Gates:**
      - `test_p05_seams`, `test_traceability`, `test_state_tables` and
        `test_mutation_suites_parse`: 100 passed, 1 skipped.
      - `-k "traceab or design_gate or doc"` over `tests/v1`: 56 passed. The same expression at
        `a55855a` also gives 56, so nothing was added or lost; item 73's "44" was counted on
        another selection.
      - `gen_ui.py --check` and `gen_api_docs.py --check`: current.
      - The client suite was not run: no client file or inventory presentation changed.
88. **Mutants.**
    - `tools/mutate_p20.py` Q80–Q99 (ids provisional, D14): **20/20 killed**. They are:
      - a mapping row removed;
      - `--allowedTools` added;
      - the MCP deny removed;
      - `--settings` removed;
      - the empty `--tools` left out;
      - an excluded tool mapped;
      - `Skill` always, never, or on the wrong flag;
      - the raw MCP name used;
      - the collision denied;
      - `mcp__*` used beside an opt-in;
      - a plugin's server named;
      - a not-offered name passed;
      - the fake agent ignoring `--tools`, `--disallowedTools` or strict MCP;
      - the adapter or the fake passing no tool flags;
      - the snapshot losing `LS`.
    - Re-run because their argv, file or guard changed: Q45–Q53, Q62, Q63, Q68 and Q69, **13/13
      killed**; `mutate_p8` M15 (`fake.py`), **1/1**. The parse gate passes.
89. **Real-CLI validation under the implemented argv** (2026-10-07; Claude Code 2.1.292).
    - What was run: the argv `ClaudeCodeAdapter.argv()` builds, the real `hook.py`, and a stub
      Core on its mailbox. By F.0's method, so no model call: `init` on the subscription login with
      every connection refused, and behaviour against the loopback stub.
    - This is F's own check that the new flags do not regress slice E's closed behaviour. It does
      not reopen PV-19, and it is not D15's observed run.

    | Check | Result | Evidence |
    |---|---|---|
    | `init.tools` is the mapped set, filtered by the CLI's names | **PASS** | read+write+exec: the 8 mapped; all four classes: the 10; read with a skill opted in: Read, Glob, Grep, Skill. Never LS or MultiEdit |
    | Empty `--tools` accepted | **PASS** | no class, and `deploy`+`git_push`: `--tools ""`, exit clean, `init.tools` empty |
    | Excluded tools do not execute | **PASS** | a read-only task's Bash, Write, Agent and WebFetch: "No such tool available"; the hook asked once, for Read |
    | Opted-in MCP usable | **PASS** | `pvmcp` and `pv_dot` run through the hook's allow (their markers written) |
    | Excluded MCP unavailable | **PASS** | `gh` and `pv@at` (as `mcp__pv_at`): refused. Loaded past `--strict-mcp-config` by a second `--mcp-config`, they are still refused by the deny, by their normalised names |
    | Normalised names | **PASS** | the deny is `mcp__gh,mcp__pv_at`, never a raw `.` or `@` |
    | Collision (L1) | **PASS** | the account's excluded `pv.dot` is not denied; the opted-in `pv_dot` stays usable (it answered the call) |
    | Opted-in Skill usable | **PASS** | "Launching skill: f0skill", through the hook |
    | Skill unavailable when not opted in | **PASS** | refused; the hook not asked |
    | Slice E's allow | **PASS** | Bash ran (its side effect written) |
    | Slice E's deny (exit 2) | **PASS** | blocked, no side effect, the reason reaches the model, the session goes on |
    | Slice E's halt (O4) | **PASS** | blocked, no side effect, `halted.json`, `terminal_reason: hook_stopped` |
    | A Core that never answers | **PASS** | "Archeus did not answer; denied and halted"; blocked and stopped |
    | A hook crash | **PASS** | "the Archeus hook failed: FileExistsError"; blocked and stopped |

    And `tools/claude_tool_drift.py`: no drift on haiku, sonnet, opus or fable (item 81).
90. **The full run** (`tests/v1` plus `tests/test_p05_seams.py`, `ARCHEUS_E2E=1`, on `17a4d10`):
    **2744 passed, 2 failed, 14 skipped, 3 xfailed** (41 min). Both failures are
    `test_spa_arrival.py`, a file items 22, 48 and 90 of p19-design-gate record as intermittent:
    - `test_reduced_motion_says_the_rise_and_pulses_nothing` ("timed out: the arrival is still
      announced"): P19 item 48's known intermittent, the same signature as §12 item 54's run 3.
      Measured alone, 10 runs each: 3/10 failed on `17a4d10` and 2/10 on `a55855a`.
    - `test_a_rise_in_what_needs_you_pulses_the_badge_once` ("timed out: the arrival is
      announced"): **newly seen failing in a full run**, the same file and the same kind of timeout
      on the announcer. Measured alone, 30 runs each: **2/30 failed on `17a4d10` and 3/30 on
      `a55855a`**. It is not slice F's: it fails as often before F, and F touches no client file,
      no announcer and no attention path.
    - Neither is fixed and neither is called green. Their classification is the file's existing
      one; this item adds the second test's name and rates. The base measurements used a detached
      worktree of `a55855a` with the same SPA build, since F changed no client file.
    - `test_spa_marker` and the `test_stream_takeover` burst passed in this run. `test_cli_help`
      (item 69, outside `tests/v1`) was not run.
91. **Status: slice F is closed for its automated and CLI-level evidence.**
    - All of these are in: the implementation (`17a4d10`); the unit, integration, G6, focused and
      gate checks; the 20 new mutants and the 14 re-run; the real-CLI validation under the
      implemented argv (item 89); the live drift comparison (item 81); and the full run, whose two
      failures are intermittents measured as pre-existing (item 90).
    - **Still owed:**
      - D15's observed execution through Core, which covers PV-19 and ADR-0052 §7 alike and is
        gated by ADR-0021, still OPEN;
      - the manual checks of §10;
      - V2 for accounts other than the one used, and API-key accounts (the tool set depends on
        the login, item 76).
    - **For the user's attention:** every call to an opted-in MCP server or skill waits for an
      approval (item 83).
    - **A stale record, not edited:** the V2 register's PV-22 row in
      `ARCHEUS_V2_ASSISTANT_LAYER.md` still says "decided; waiting for P20". That is a V2
      document, left as the user's instruction requires.
    - P20 is not complete. **G, H, I, J and K are not authorised and were not started.**

### Slice G — paused on two Critical OS-confinement findings (2026-10-07)

Slice G (ADR-0051 §2 boundary tests; the threat model) was started and **stopped before any
implementation.** Its verification probes, run read-only, found that the boundary ADR-0051 §2
asserts is contradicted in practice. HEAD is unchanged; nothing in the repository's code moved.
These are recorded at the boundary / capability / evidence / impact level — no procedure, no real
secret, no enumerated store — per the user's safety constraint for this work. The full
remediation design is in [pv13-windows-os-confinement-study.md](pv13-windows-os-confinement-study.md)
and [pv20-execution-isolation-design.md](pv20-execution-isolation-design.md).

92. **Finding G1, Critical — an execution reaches user-owned credential authorities.** Under the
    default `standard` profile, `write_repo` and `exec` are allowed within the worktree, and the
    boundary check reads only the command line, so an execution can write and run self-authored
    code with no approval. That code runs with the user's OS identity and therefore keeps the
    user's reach into credential authorities and stores whose secrets would authorise pushing,
    publishing or registry/SSH access. **This contradicts ADR-0051 §2's "finds no push
    credential."** P11's `CAPABILITY_ENV` works as designed — the secrets do not live in the
    environment but in stores the OS identity owns, which clearing an environment variable cannot
    remove.
93. **Finding G2, Critical — an execution reaches the local Core control boundary.** The execution
    can reach the privileged local token and `run/` control state, which to Core's loopback API is
    the full-scope local principal past step-up — enough to defeat approval, policy and the e-stop
    if used. Established from code and a readable-file check; **not** exercised against the live
    Core.
94. **Finding G3, Medium — network egress — is P23's.** A task whose policy denies `web`, or that
    never declared it, can still reach the network through an in-boundary `exec`. The fix (routing
    such tasks to a `sandbox` harness) is P23's, with Codex (D9). PV-20 records it as a dependency
    and does not solve it.
95. **Root cause and framing.** All three are the ADR-0051 §3 OS-confinement gap: nothing below
    the per-tool hook limits what a process with the user's identity can physically reach.
    **These are OS-boundary issues, not P11 environment-hygiene defects** — P11's four settings
    function as designed, and the findings must not be rewritten as a P11 bug. Changing P11's
    environment cannot fix them, because the material sits in stores the OS identity owns.
96. **Disposition.** **Slice G is PAUSED, not closed.** ADR-0051 §2 is not satisfied (the
    credential-removal bullet and the workdir isolation are contradicted by G1 and G2). The
    remediation is **PV-20**, whose prerequisite **PV-13 study is now delivered** (2026-10-07,
    recommending AppContainer + a Job object, with a separate-user escalation path). Any ADR-0051
    §2 boundary test written against the current identity would assert the wrong thing, so G's
    credential/workdir tests are deferred into PV-20's suite (xfail today, flipping under
    isolation). The P20 acceptance rule forbids an open Critical and defines **no** accepted-
    Critical state. The disposition is now ruled (ADR-0051 superseding decision — timing, 2026-10-07;
    PV-20 §6.4): OS confinement is a **V1.x security remediation**; G stays **PAUSED and NOT CLOSED**;
    G1 and G2 stay **Critical and open**, neither waived nor accepted. **G's still-valid boundaries, cited
    unchanged** (orthogonal to the OS gap): A's sentinel + registry kill, E's ADR-0049
    exclusion/inventory and the O4 fail-closed hook, F's tool removal. *(Qualified 2026-10-07, §12
    item 98: A's sentinel stays valid under PV-20 only with the explicit three-state determination,
    which must land no later than PV-20's sentinel/mailbox separation; today its fail-closed result
    under an inaccessible sentinel comes from the mailbox write failing beside it. A's registry kill
    stays the only Core-less stop mechanism.)*
97. **Status: slice G is paused; H, I, J and K are not authorised and were not started.** No
    `mcp__*` / credential procedure and no harvested value is recorded here or anywhere in the
    repository. The probes were read-only scratchpad scripts; no git state, no Core state and no
    secret was written. ADR-0051 carries a dated note distinguishing the accepted V1 limitations
    from the security properties PV-20 must establish.
98. **PV-20 architecture decisions approved and recorded (2026-10-07; documentation only).** The
    owner approved PV-20's six blocking decisions in the direction the decision matrix
    recommended, and they are recorded in **ADR-0053** (the PV-20 ADR ADR-0051 Decision 5 requires)
    and PV-20 §6 items 12–17: **R4b** a confined verification identity (execution-influenced code
    never runs under the user's identity; an unavailable verifier is missing evidence, never
    PASSED); **R4a** a separate execution repository imported as data; **R1** OS-attested execution
    origin (R1-B only by a new owner decision); **R3** Core-brokered provider access as the target
    (R3-A only by a separate owner security decision; until one is viable, isolated execution fails
    closed); **R5** H2 (Core-authoritative halt state; hook records are untrusted reports); **R6**
    Core-only Job ownership (a live isolated process is never re-adopted). R2 and R7 are
    implementation constraints; O7 stays P11's (§4.2). This gate's records are reconciled with it:
    - **The status** reads "decisions recorded and approved; resolved except implementation and
      evidence dependencies and O7; implementation not started; verification not performed".
    - **Item 96's "A's sentinel"** is qualified: valid under PV-20 only with the explicit three-state
      determination, landed no later than the sentinel/mailbox separation.
    - **D10 is not PV-20's re-arm control.** PV-20 §3.6 and its acceptance row 5 no longer cite D10
      as what refuses an execution's re-arm; an execution origin is refused by the effect boundary
      (R1-A). D10 stays exactly as approved and blocked (§14.B, V2-3): the paired-device rule only.
    - **Item 83 stands unchanged.** The STOP file plus the process registry remains the only
      Core-down stop mechanism; under PV-20 the Job is the execution lifetime boundary, not a second
      Core-down authority (PV-20 §3.7).
    Nothing was implemented, probed or committed in this pass; no production code changed. **G
    stays PAUSED and NOT CLOSED; G1 and G2 stay Critical and open.**
99. **PV-20 blocker decisions recorded (2026-10-07; documentation only).** A final read-only
    architecture audit found seven blockers (A1–A7). The owner approved A1–A6 in the direction the
    blocker decision matrix recommended; A7 is a documentation correction. All are recorded in
    **ADR-0053 §7** and PV-20 §6 items 18–24:
    - **A4 (H-1):** every production-dispatched execution, whatever its harness, runs under the
      PV-20 identity inside a Core-held Job; a harness that cannot is not eligible; fake/test
      harnesses are not production-dispatchable. Codex is not installed (§1.5), so no harness
      loses eligibility today.
    - **A1 (A1-1):** a Core-established workspace for every isolated execution of every task kind;
      `workspace_mode: in_place` withdrawn for isolated executions; non-git project roots refused
      **before dispatch**. That keeps a structural impossibility out of the `SpawnFailed` per-tick
      re-dispatch of items 48, 64 and 72; only a transient workspace failure is O7's.
    - **A5 (G-4):** copy seed of the base revision only; Core never runs git against an execution
      repository as the user; working-tree import into a Core-owned repository whose pinned import
      commit is the canonical revision; Core-pinned configuration for every Core git operation over
      execution-derived content. *Confirmed by the owner, 2026-10-07 (item 100):* no
      repository-controlled hook (the user's own included), filter, fsmonitor, diff/merge driver,
      submodule, LFS transfer mechanism or other execution-derived git extension executes in those
      operations, and Core pushes no content whose publication requires one.
    - **A6 (V-1):** one fresh verifier principal per verification, never reused; authority a subset
      of the execution's runtime/tool grants plus its checkout and scratch, network only if P23
      permits; no persistent or shared cache.
    - **A2 (A2-1):** a fresh per-execution `CLAUDE_CONFIG_DIR` with no provider login, never the
      account home (§1.5); Core-authored spawn configuration Core-write / execution-read; opt-ins
      only as Core-materialised data carrying no credential authority; **no MCP opt-in admitted to
      an isolated execution** (confirmed by the owner, item 100; items 50 and 65; ADR-0049 "PV-20
      consequence").
    - **A3:** R1-A as an allowlist with a hop rule and a deputy rule; a trusted local §3.6 request
      needs both the attested user-origin condition and an approved trusted path; the verifier,
      forwarding hops, proxies, undetermined origins and execution-influenced deputies get no §3.6
      authority (p15-design-gate §6.6, p9-design-gate D16).
    - **A7:** state-machines §4, p11-design-gate §15.3–§15.4 and execution-architecture §4–§5
      corrected: ENDED_OK is an execution-level fact from Core's own observed exit 0; a stream
      result is never an exit; a Core-written `ended` tombstone is; the one-shot-allow token is
      withdrawn in favour of the as-built Core-side approval consumption.

    This gate's records are reconciled with it: §1.5 and items 50 and 65 (A2); slice A item 4,
    `test_A06` and A-M1 (their "process lives on" step inverts for isolated executions under R6-A);
    slice A item 7 (the Core-less path keeps its pid-recycle ceiling under R6-A). Still open and
    external: **P11's O7** (§4.2), **P23** (egress, verification network, broker loopback reach,
    forwarding-hop reach), **ADR-0021** (gates every real-CLI evidence run). Nothing was
    implemented, probed or committed; no production code changed. **G stays PAUSED and NOT
    CLOSED; G1 and G2 stay Critical and open; PV-20 is not implemented and not verified.**
100. **A5 and A2 confirmed by the owner (2026-10-07; documentation only).** The two readings item
    99 recorded for confirmation are confirmed, and ADR-0053 §7, PV-20 §3.1, §3.2 and §6 items
    20 and 22, p13-design-gate §12.1, execution-architecture §2 and §7, ADR-0049 and items 65 and
    99 now state them as rules:
    - **A5:** no repository-controlled or execution-derived git extension executes during a Core
      git operation on execution-derived content — repository-controlled hooks (the user's own
      included), filters, fsmonitor, diff and merge drivers, submodules, LFS transfer mechanisms,
      and any other execution-derived git extension. Core does not push content whose publication
      requires executing one of them; that capability needs a separate owner decision.
    - **A2:** **no MCP opt-in is admitted to an isolated execution.** The rule is not limited to
      credential-bearing servers; changing it needs a new owner decision.

    No other architectural change was made. Nothing was implemented or probed. **G stays PAUSED
    and NOT CLOSED; G1 and G2 stay Critical and open; PV-20 is not implemented and not verified.**
101. **PV-20 slice S0 — Gap A, the three-state sentinel determination (2026-10-08).** The owner
    authorised S0 as the **first and only** PV-20 implementation slice; no other slice is
    authorised, and S1–S7 each need their own authorization naming the slice and confirming its
    prerequisites.
    - **Built.** `archeus/harnesses/hook.py` gains `_sentinel()`, and all five sentinel reads go
      through it: the global STOP before the request, the execution's STOP, PAUSE and HANDOFF
      flags, and the global STOP inside the wait loop. A successful `os.lstat` is **present** (a
      dangling link included, which `os.path.exists` read as absent); `FileNotFoundError` is
      **absent**; every other `OSError` is **indeterminate** and halts with its own reason,
      "cannot determine the <sentinel>'s state; halted (fail closed)". The reasons for a present
      sentinel are unchanged. Stdlib only; the module still imports no package.
    - **Tests** (`tests/v1/unit/test_execution_units.py`, injected errors only — no ACL, no
      confinement): each of the five reads × absent, present, dangling link, `PermissionError` and
      another `OSError` (25 cases), and PV-20 row 7's own case — the sentinel undeterminable while
      the mailbox stays writable halts, and asks Core nothing. Five mutants were each killed:
      `lstat` → `stat` (15 failed), the two-state `os.path.exists` read (16), indeterminate treated
      as absent (11), the wait-loop read reverted (3), the flag reads reverted (9).
    - **Validation** (no real CLI, no model call, no network, `ARCHEUS_REAL_HARNESS` unset): the
      execution, e-stop, fake-agent, settings-source, tool-removal and G5 suites, 252 passed and 1
      xfailed. The full suite (`pytest tests/ -m "not real_process"`, 5,342 tests, 45 minutes): 5,320
      passed, 15 skipped, 3 xfailed, **4 failed**. **The full suite is not green.** The four
      failures are pre-existing and unrelated to S0; the owner directed that they stay unfixed in
      this slice:
      - `tests/test_cli_help.py::test_a_deferred_v1_verb_imports_only_its_dispatcher` predates
        S0. It fails every run because `archeus approve` now imports `archeus.cli._api`. It
        depends only on `archeus/cli/*` and the test, all unchanged by S0.
      - `tests/v1/e2e/test_spa_arrival.py::test_a_rise_in_what_needs_you_pulses_the_badge_once`
        (the SPA arrival "rise pulses the badge once") passed when re-run alone.
      - `tests/v1/e2e/test_spa_motion.py::test_a_historical_event_heard_again_never_replays_or_restarts`
        (the SPA motion "historical event never replays") passed when re-run alone.
      - `tests/v1/e2e/test_spa_arrival.py::test_reduced_motion_says_the_rise_and_pulses_nothing`
        (the SPA arrival "reduced motion") is intermittent and reproduces independently of S0.
        It times out waiting for the live-region announcement:
        - with the baseline `hook.py` it passed 6 of 6 runs; with the S0 version it failed
          intermittently;
        - its `deploy` Core has no executor, so no execution runs;
        - with `hook.py` replaced by a stub that writes a marker if loaded, the failure still
          reproduced and the marker never appeared.

        The test therefore never loads `hook.py`, and the failure is not attributable to S0.

      After those checks the S0-built `hook.py` was restored and verified by file hash. The docs
      and hook tests re-run afterwards passed: 191 tests. `ruff check` is clean on the two
      S0-modified files. **The 29 repo-wide `ruff` findings predate S0 and are outside its
      scope, and remain unresolved:** 25 in the untracked `prototypes/` (V2) and 4 B023 in
      `tests/v1/integration/test_stream_takeover.py`, `tests/v1/e2e/test_spa_estop_about.py` and
      `tests/v1/e2e/test_spa_command_close.py`, none touched here.
    - **Unchanged, as the authorization requires:** no AppContainer, Job, identity, ACE or ACL;
      no path, layout or directory change and no mailbox/sentinel split; the sentinel writers and
      Core's `estop_armed()`; the hook protocol and exit codes; `_reserve`, `WAIT_S` and the
      PreCompact path; no H2 Core-owned halt state; no retry or backoff.
    - **Not solved:** a `halted.json` the execution cannot write is still lost, so Core can still
      record ENDED_OK after a halt it did not ask for (PV-20 §7.4 Gap B). That stays with the
      Core-authoritative halt state (R5 / H2, PV-20 row 15).
    - **Status.** **S0: implemented and validated within its defined scope**, and complete with
      its commit. PV-20 row 7 stays implementation-blocked, on the sentinel/mailbox separation
      (PV-20 §7.5) and on isolated-identity evidence that a denied lookup is reported as an error,
      never as not-found. **PV-20 is not verified overall. G stays PAUSED and NOT CLOSED; G1 and
      G2 stay Critical and open.** P11's O7, P23 and ADR-0021 stay unresolved; AppContainer and
      Job evidence stays outstanding. No later slice is authorised.
**PV-20 MXC backend decision and bounded feasibility evidence — 2026-10-29.** The owner selected Microsoft MXC `processcontainer` as the implementation of ADR-0053’s unchanged AppContainer + Core-held Job mechanism. `.collab/PV20-mxc-feasibility.md` records the separately authorized eight-check smoke and Claude 2.1.312 version/help addendum. N1–N5 were not started. Read/write denial, blocked local network and short tree termination observations do not close acceptance rows 1–15. G1/G2 remain Critical and open; G remains PAUSED and NOT CLOSED. Production activation, UI policy, principal separation, hostile-object/handle exclusion, credential-authority denial, broker/origin proof and full lifecycle evidence remain gated. Historical hand-built implementation entries retain provenance but are not evidence for the MXC implementation.

102. **PV-20 slice S1 — the isolated-execution path, accepted with recorded limitations
    (2026-10-09) and committed (2026-10-12, `77008db`).** The owner's acceptance record is
    `PV20-S1-ACCEPTANCE-2026-10-09.md`; it authorises neither S2 nor production enablement.
    - **Committed unchanged** from the reviewed working tree, which had not been modified since
      2026-10-09: `archeus/node/isolation.py`, its callers in the execution manager, the local
      node and the harness base, `archeus/infra/paths.py`, the synthetic unit suite and the
      opt-in Windows suite (`ARCHEUS_REAL_BOUNDARY=1`).
    - **Posture:** `PRODUCTION_DISPATCH_ENABLED = False`, `A4_ENFORCED = False`,
      `CAPABILITIES = ()`. No grant or ACE is applied, and no grant code exists.
    - **Verified at commit:** `tests/v1/unit/test_pv20_isolation.py`, 277 passed. The Windows
      suite was not run.
    - **Open (the acceptance's four limitations, unchanged):** C6 product-path evidence;
      genuine quarantine recovery; the production-shaped environment; grant application.
103. **PV-20 S2-L — the class directories inside each execution (committed 2026-10-12,
    `13c1172`, branch `pv20-s2`; not accepted).** The work already in the S2-L worktree,
    committed on top of item 102 so that it can be reviewed commit by commit. **A commit is not
    an acceptance:** S2-L's acceptance remains the owner's decision.
    - **Built.** An execution's directory gains `req/` (class 1, written by the execution:
      requests, `halted.json`, `precompact.json`), `res/` (class 2, written by Core: answers,
      `settings.json`, `mcp.json`), `ctl/` (class 3, Core's STOP, PAUSE and HANDOFF flags) and
      `own/work` and `own/state` (class 7: the no-project workspace and runtime state). The
      directory itself and its contract files stay Core's (class 4). The layout applies to every
      execution, isolated or not. The isolation plan carries each mailbox class as its own row,
      and the boundary check requires the three classes to be separate directories, outside one
      another, Core's state and the workspace, with the spawn configuration inside class 2.
    - **Verified:** `test_pv20_isolation`, `test_execution_units`, `test_paths`,
      `test_settings_sources_units`, `test_context_capacity` and `test_execution`: 553 passed.
    - **Left out:** `tests/v1/integration/test_pv20_writer_fixture.py`, whose current state has
      never been reviewed and which performs an ACL write when run.
104. **PV-20 S-HR — `DeleteAppContainerProfile`'s answer compared unsigned (2026-10-12,
    `16f5a0a`, `pv20-s2`).** The function is bound with restype `c_int`, so a failure HRESULT
    arrives negative and `hr not in (0, 0x80070490)` could never match not-found: a profile
    already gone raised `profile_delete` instead of counting as released. The answer is masked to
    32 bits before the comparison, as `create_profile` already did. The accepted set is unchanged
    (S_OK, not-found). Tests use a fake Win32 function; 301 passed, and without the mask the
    not-found case fails.
105. **PV-20 S2-G preparatory — refusals only (2026-10-12, `ef42204`, `pv20-s2`).** Two
    defects in S1's record handling, fixed without any ACL write or new spawn path.
    - **D1.** `Isolation.establish` reset any prior record to pending and created the profile
      again. A Core that crashed after quarantining an identity, and before refusing its
      execution, would resume a PAUSED execution under the quarantined identity. `establish` now
      refuses a prior record that is not `pending` or `established`, or that carries a failure,
      with `record_unsettled`, before any write. `established` (a PAUSED resume) and `pending`
      (the retry of a resume that died, Finding 1) stay allowed.
    - **D2.** The cleanup after a failed establishment quarantined the profile and overwrote the
      record's reason, so the record lost why establishment failed and the restart
      reconciliation, which keyed on `state == 'failed'`, no longer saw it. The record gains
      `failure`, which `_fail` sets and cleanup never touches, and the reconciliation refuses on
      it, uncharged, as before.
    - The static gate also recognises the handle-based security setters (`*SetSecurityObject`,
      `SetUserObjectSecurity`, `SetServiceObjectSecurity`); none appears in production code.
    - **Verified:** the item 103 set, 575 passed; eight mutants (each change, the record type check
      and the read-back), all caught.
    - **S2-G itself is not started and is blocked on an owner decision.** Codex's readiness record
      of 2026-10-11 found that an execution chooses the descriptor of the objects it creates, so
      the current construction cannot promise peer exclusion for execution-created descendants
      when the owning execution itself names a peer. The options are prepared for the owner
      (Core-created mailbox objects; a privileged namespace; an ADR narrowing R7 to
      non-consensual access; or the first and third together). None is decided here.
106. **Item 101's four pre-existing full-suite failures fixed (2026-10-12, `f6abc4d`, on
    `archeus-v1-rearchitecture`).** All four had test-side causes; no product code changed.
    - `test_cli_help`: `archeus approve` also imports `archeus.cli._api`, the generated route-path
      builder, which imports only `urllib.parse`. J3 still holds, and the expected list names it.
    - The two SPA arrival tests: the load's connection banner opens the polite region's 5 s
      window, inside which only the latest offer is kept (p16 §17), so the thread update riding
      the same Core event could replace the arrival unsaid. Both now wait that window out. The
      post-pulse check fails only on the pulse itself or an unbounded animation, and then waits
      for the bounded thread-draw to end.
    - The SPA motion test's final idle check now settles first, as every other one does.
    - `mkdocs.yml` excludes `docs/project-context/` (private agent context), which the nav gate
      had failed on.
    - **Verified:** the three SPA tests 12 of 12 runs green (before: 2 of 6 and 2 of 10 runs
      failing). The full suite: 5,600 passed, 16 skipped, 3 xfailed and 1 failed, the failure
      being the docs nav gate that the same commit fixes. The full suite was not rerun after that
      one-line fix.
    - **Open, not changed:** under §17's latest-wins rule a thread update can replace an arrival
      announcement in real use too. Whether arrivals take priority is a design decision.
107. **Corrections to items 103, 105 and 106 (2026-10-12, after review of `3489a39`).** Those
    items stand as written; where they conflict with this one, this one holds.
    - **Item 103, "Left out".** The writer fixture's current state is not unreviewed. Its
      SHA-256 on 2026-10-12, `B23BBA61A5C2D4E175C9155F228D7796AC45D108FFB88366C0D084D96FC72EF8`,
      is the source Codex reviewed and ran on 2026-10-11 (Codex's writer/creator closeout of that
      date). That evidence covers the bounded fixture only: not the product writer, recovery or
      concurrency. The file stays uncommitted, and whether it is kept, integrated or deleted is the
      owner's decision. Nothing was rerun for this correction.
    - **Item 105, the options.** The option called "an ADR narrowing R7 to non-consensual access"
      took its wording from an analysis note whose review found that an execution naming a peer
      in a descriptor it creates is that execution's action, not the owner's consent. The note is
      being corrected. The list in item 105 names prepared alternatives, not a design position,
      and R7 is unchanged.
    - **Item 106, the full suite.** It was rerun on `f6abc4d` after the `mkdocs.yml` fix, separately
      from the authoring session: `py -m pytest tests/ -m "not real_process" -q`, 5,601 passed,
      16 skipped, 2 deselected, 3 xfailed, 1 warning (a local log outside the repository). This is
      reported evidence; the review of `f6abc4d` read the log and did not rerun it.

### Slice I — secrets review (D7), remote-access threat model, dependency audit (2026-10-15)

Built on the T-072 integration candidate `91cbb0c`. Nothing of G, H, J, K, D10, P21 or V2 was
touched. No ACL was written, no Windows isolation or profile API was called, and no OS or user
credential store was read: this review covers Archeus's own files and code only.

108. **The order after slice F, D12, D13 and D14 decided (the owner, 2026-10-15).** Recorded as
     given (AskUserQuestion answers in the Claude session):
     - Order: "I then H, beside G (Recommended)". Slice I runs first, then H, both while G
       (PV-20) waits on T-004, each slice with its own commits and gate items. This lifts §4.1's
       "F, G, H, I and J not in parallel" for I and H beside G only; J and K are unchanged.
     - D12: "Stdlib harness (Recommended)". That is `random.Random(seed)` plus a recorded corpus
       and structured mutation in `tools/fuzz_p20.py`, with a fixed seed and a small budget in CI
       and a large budget on demand. No new dependency.
     - D13 and D14: "Approve both as written (Recommended)". The drills and the mutant ids are
       exactly as §4 states them.
109. **Secrets at rest, by writer and protection (D7).** Every credential Archeus issues starts
     as a CSPRNG draw (`secrets.*` or `os.urandom`). The table below follows each draw to where
     its value goes; draws that are not secrets are listed under it.

     | Secret | At rest in | Form | Writer | Protection |
     |---|---|---|---|---|
     | Local token: the CLI's device credential, every scope | `run/local-token` | plaintext | `infra/discovery.py:205` `write_local_token`, called from `core/runtime.py:546` | Created `O_CREAT\|O_EXCL`, mode `0600`. POSIX: Core refuses to start when `run/` or the file is readable by group or others (`discovery.py:177` `token_protection`). Windows: inherits the ARCHEUS_HOME DACL, with T-089's warning when a broad principal may write the home (`discovery.py:159`) |
     | Device-token hashes: the local token, launch-code and paired clients | DB `tokens.token_hash` | sha256 | `infra/db/writer.py:124` `Tx.insert_token`, from `runtime.py:545`, `api/routes.py:235`, `:283` and `core/application/commands.py:147` | Hash only, and the writer has no plaintext parameter. Compared with `hmac.compare_digest` (`api/auth.py:79`) |
     | Hook-token hash | DB execution row `hook_token_hash` | sha256 | `core/application/executions.py:141` | Cleared to `None` on every end path (`executions.py:196`, `:345`, `:351`, `:357`, `:380`, `:456`, `:675`, `:710`). Stripped from reads (`:929`, `:977`) |
     | Hook token, plaintext | `run/exec/<id>/req/<seq>.req.json` | plaintext JSON field `token` | the hook process, `harnesses/hook.py:160` via `_reserve` (`:109`) | Inherits the execution directory's ACL. Dead once the execution ends, because its hash is cleared and a hashless execution refuses every token (`executions.py:741`). Not deleted (item 111) |
     | Step-up PIN | DB device row `pin_hash` | `pbkdf2_sha256`, 200,000 iterations, 16-byte salt | `core/application/commands.py:96` `hash_pin`, from `api/routes.py:286` | `entities.PIN_HASH` refuses any other shape (`entities.py:194`, `:229`). Compared with `hmac.compare_digest` |
     | The Qt shell page's device token | the Qt shell's persistent QtWebEngine profile, `QtWebEngine/archeus` in the home (the legacy Qt shell's entry, target-architecture §5.1), its IndexedDB | plaintext | the SPA, `clients/app/src/api/transport.ts:38` `saveToken`, under `claude_sessions/gui_qt.py:171-173` and `archeus/cli/gui.py:38` | Inherits the ARCHEUS_HOME DACL (item 111) |
     | Database backups | the backup directory | copies of the DB, so the hashes above | `infra/db/backup.py:56` | As the rows they copy |

     - **Memory only:** launch codes (60 s) and pairing codes (120 s), held as sha256 keys
       (`api/auth.py:165`); the desktop shell's own credential (`cli/gui.py` module docstring,
       p20 D1).
     - **Not stored by Archeus:** a device token returned once by `launch/redeem` or
       `pair/redeem`. It lives in that client's own storage, on the client's device.
     - **Not secrets:** a 500 answer's reference (`api/server.py:169`); the Core instance id
       (`:206`); ULID entropy (`core/domain/ids.py`); a staging temp name (`node/staging.py:226`);
       CLI and shell idempotency keys and request ids (`cli/main.py`, `cli/gui.py:150`).
     - **Gate:** `tests/v1/unit/test_p20_secrets.py`.
       - It fails when a draw or a caller of `auth.new_token()` appears that this table does not
         name, or when a row's draw is gone.
       - It checks the local token's `O_EXCL` and `0600` from the source, so the check holds on
         Windows as well as POSIX. POSIX also has the behavioural test in `test_core_lifecycle`.
       - It checks that `insert_token` takes only a hash, that the hook-token hash is the
         execution's only token field, and that a PIN is accepted only as a pbkdf2 record.
       - Mutation-verified on a `git archive` copy, 5 of 5 caught, restored passes: an unlisted
         draw; a new `new_token()` caller; the token file's mode loosened to `0644`; `O_EXCL`
         dropped; a plaintext `token` parameter on `insert_token`.
110. **D7 concluded: Core stores no API key.**
     - `Account` has no secret field (`core/domain/entities.py:1363`): `home_ref` is a path,
       and the `accounts` table holds that entity's body.
     - No draw or writer above produces an API key.
     - The Claude Code adapter removes `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` from an
       execution's environment rather than supplying them (`harnesses/claude_code/adapter.py:168`).
     - An account's login, API key or OAuth, lives in the harness's own home, which Archeus does
       not write.
     - So, as D7 directs, plan §27's DPAPI requirement is amended rather than built. The
       amendment is appended to plan §27. The local token stays under the profile ACL, as p3.5b
       D5 accepted; DPAPI remains an option, not built.
     - Not examined here: what the adapters' login probe reads in the account's home
       (`harnesses/calls.py:79-82`, via `claude_sessions.usage._creds`). That is the user's own
       credential store, outside this review's limits. It concerns reach, not storage, and is
       recorded on T-093 for routing.
111. **Findings.** None is High; each is the owner's to dispose of.
     - **I-F1, Medium: on Windows the home check reads write, while the local token's threat is
       read.**
       - `token_protection` warns on Windows only when `broad_writer` finds a broad principal
         with a write-like allow ACE (`isolation.py:1763`).
       - `run/local-token` holds every scope. A home whose DACL lets a broad principal read but
         not write gives no warning, while that principal can read the token.
       - The default home, `%LOCALAPPDATA%\Archeus`, is under the user profile. The case needs a
         non-default ARCHEUS_HOME.
       - Options: also warn on a broad read-like ACE; or accept it, with a documentation note.
     - **I-F2, Medium: a second plaintext credential at rest that the documentation does not
       name.**
       - The Qt shell's page keeps its device token, with the scopes its launch code granted (D2), in the persistent
         QtWebEngine profile under ARCHEUS_HOME.
       - `discovery.py`'s docstring and plan §27 both describe `run/local-token` as the only
         plaintext secret at rest.
       - Its protection is the same as the local token's, so I-F1 applies to it too.
       - Options: document it as accepted; or make the shell's page credential memory-only
         (an off-the-record page credential, which would change D2's restart behaviour).
     - **I-F3, Low: plaintext hook tokens stay in each execution's `req/` directory after it
       ends.** Nothing removes `run/exec/<id>`. Each token is dead, because its hash is cleared.
       The residue grows with the number of executions.
     - **I-F4, Low: raw execution output at rest is not redacted.** Whatever an agent printed is
       kept as written, and every read path redacts it (`core/execution/output.py:30`). It is
       third-party content, not an Archeus credential.

112. **Remote-access threat-model review (P15).**
     - **Where it lives.** ADR-0051 §3 assigns the threat model document to slice G, which is
       paused (item 96). The review therefore lives here. That document can take it over by
       reference when G resumes.
     - **Method.** Each row of p15-design-gate §8.4, plus §8.1's environments, read against the
       code at `91cbb0c`. Nothing was exercised through a real tunnel.

     | Surface / threat | Control as built | Evidence |
     |---|---|---|
     | Exposure | Core binds `127.0.0.1` only; a tunnel is opt-in via `--remote-host` | `api/server.py:448`; `auth.Origin` (`api/auth.py:99`) |
     | DNS rebinding, origin abuse | Exact Host allowlist, then fetch metadata (`Sec-Fetch-Site` ∈ same-origin/none) and an Origin matching the Host's own origin | `server.py:330`, `:333`; `auth.py:112`, `:125` |
     | Token in URL or logs | `token`/`access_token` in a query → `401 token_in_url`. The stdlib request log is silenced. Core's own line has method, route template, status, duration and device id: no header, query or body | `server.py:337`, `:266`, `:412` |
     | CSRF, WebSocket hijack | Bearer header only, no cookie. The stream is a `fetch` with the header, not a WebSocket | `server.py:361`; `clients/app/src/api/transport.ts` `sender` |
     | Local credential through the tunnel | A non-paired credential is honoured on the loopback Host only | `server.py:369-375` |
     | Paired credential's privileged effects | Only through a configured remote host, on scoped routes, after authentication and scope checks. `launch/redeem` and `pair/redeem` are unscoped (T-083 correction) | `server.py:376-381` |
     | Pairing code replay, brute force | Single use, 120 s; more than 10 failed redemptions in 60 s burn every live code and lock for 60 s | `auth.py:34`, `:202-234` |
     | Launch code | Single use, 60 s, memory only; a local-only route needs a loopback peer and the loopback Host (§8.3) | `auth.py:30`, `:154-196` |
     | Stale or revoked credential | `auth.live` on every request; a stream re-checks its token on every wake; revoke closes the device's streams before answering | `auth.py:75-84`; `api/sse.py:148`, `:223`; `api/routes.py:951-953` |
     | Stolen device | 180-day paired expiry; revoke; step-up PIN as a pbkdf2 record (item 109) | `auth.py:36`; `routes.py:742-748` |
     | Replayed or queued mutation | Idempotency keys on keyed commands; a command replayed from an offline queue is refused unless declared replayable | `server.py:17` (step 8), `:388-394` |
     | Stream exhaustion | 8 stream slots; at a device's cap, the newest stream wins (D2) | `sse.py:31`, `:99` |
     | Script injection | CSP `script-src 'self'`, `nosniff`, `no-referrer` on every response | `auth.py:40-46`; `server.py:254`, `:285` |
     | Process origin (R1-A) | The attestor takes every peer as the user until R1-A is activated (T-057); `origin_refused` cannot yet fire | `auth.py:93-96`; `server.py:353-358` |

     - **GAPs.** No High was found on the remote path.
       - The R1-A attestor is inert by design until PV-20 activates it. It is a local-process
         control, owned by PV-20, not by P15.
       - I-F1 and I-F2 (item 111) bear on a local reader of the home, not on a remote client.
     - **Not run:** a real tunnel (Tailscale Serve or another), a paired phone, or an
       adversarial client. The manual checks of §10 stay as they are.

113. **Dependency audit.**
     - **Python runtime: stdlib only.** `pyproject.toml`'s `[project]` has no `dependencies` key.
       The extras are `dev = ["pytest"]` and `gui = ["PyQt6", "PyQt6-WebEngine"]`
       (`pyproject.toml:79-81`), the latter for the optional desktop shell. No Python audit tool
       was run on the extras; that is not run.
     - **The SPA's lockfile.** `clients/app/package-lock.json`, lockfileVersion 3: 51 packages,
       by npm's own count 5 prod, 47 dev, 27 optional.
     - **The offline audit is not evidence.**
       - `npm audit --offline --package-lock-only` (npm 11.12.1) answered "found 0
         vulnerabilities" on `91cbb0c`.
       - That same lockfile pins `source-map-js` 1.2.1, the version GHSA-68fv-2mgg-jv7q names.
         The advisory failed CI's `npm audit --audit-level=high` on `f6abc4d` (T-073), and
         `3d98f84` raised it to 1.2.2 on the branch.
       - An offline audit has no advisory data, so its zero is vacuous.
     - **The networked audit, from CI.** Run 38646019877 on `b26225a`, the branch head carrying
       `3d98f84`. Job `v1-client`, step "Build and audit the SPA" (`npm ci`, `npm run build`,
       `npm audit --audit-level=high`, `.github/workflows/ci.yml:225`): **success**. It gates
       high and critical only.
     - **Finding I-F5, Medium until the next candidate rebuild: the integration candidate lacks
       `3d98f84`.** `91cbb0c` was built on `f6abc4d` + `3257dd0` and still pins `source-map-js`
       1.2.1. The next T-072 rebuild must take `3d98f84` from the branch. It closes with that
       merge and needs no separate change.

114. **Slice I verified, and its status (2026-10-15).**
     - **Ran, on this slice's head:**
       - `tests/v1/unit`, `tests/v1/judge/test_traceability.py`, `tests/test_p05_seams.py`, the
         integration files `test_core_lifecycle`, `test_estop_drills`, `test_presence` and
         `test_stream_takeover`, and the contract files `test_core_client` and
         `test_adapter_contract`, with `-m "not real_process"`: 2,644 passed, 5 skipped,
         1 xfailed.
       - `ruff check . --extend-exclude prototypes`: clean. `git diff --check`: clean.
       - The mutants of item 109: 5 of 5 caught.
     - **A correction inside this slice.** The first run failed one test:
       `test_paths::test_the_ownership_table_is_the_declaration`. Item 109's table had written
       the Qt profile as a `<ARCHEUS_HOME>/` path, a form that test reserves for V1-owned
       entries. The cell now names the entry without that form; nothing else in the table
       changed.
     - **Not run:** POSIX; the SPA, browser and e2e suites; native tests; a real tunnel or
       paired phone; a Python audit of the optional extras; the networked `npm audit` (the CI
       result of item 113 stands in for it).
     - **§10 against this slice.** The secrets review, the remote-access review and the
       dependency audit are committed, and none of their findings is High. The threat model
       document itself remains slice G's (item 112). I-F1, I-F2 and I-F5 are Medium and are
       the owner's to dispose of: I-F5 closes with the next candidate rebuild.
     - Slice H is next (item 108).

### Slice H — drills, fuzzing, mutants (2026-10-15)

Built on slice I's head `853f63f`, under item 108's order and D12, D13 and D14 as decided there.
Fakes only: no real provider call, no Windows isolation, profile or ACL API, no network.

115. **D13, the breaker drills: each breaker of §1.6 tripped on purpose and its recovery
     observed** (`407438b`). What existed was mapped first; a drill was added only where the
     trip or the recovery had no test.
     - **The execution breaker** (per account, resource and auth failures). E32 covered the trip
       only. `test_execution.py::test_D13_the_execution_breaker_trips_opens_cools_and_recovers`
       walks the whole Account cycle on the real machine: a storm of non-resource failures moves
       nothing; a resource/auth storm gives DEGRADED; errors that persist past a beat give OPEN;
       nothing moves before the cooldown and DEGRADED after it; a successful probe gives
       AVAILABLE; and the recovered account is routed again. Synthetic ended executions reach
       `accounts_tick` through the transaction's own read, so every boundary is exact.
     - **The pairing breaker** (`PairingLocked`). Its trip and its reopening after the window
       were already covered (`test_presence.py::test_R4_…` and
       `test_presence_units.py::test_the_failure_breaker_burns_every_code_and_reopens_after_its_window`);
       nothing was added.
     - **Five wrong PINs revoke a client.** R1 covered the trip.
       `test_presence.py::test_D13_the_pin_breaker_resets_on_a_right_pin_and_a_new_pairing_recovers`
       adds the recovery: four wrong PINs and a right one approve and reset the count; after the
       fifth wrong PIN in a row revokes the client, a new pairing decides the approval that was
       still pending.
     - **The loop guard** (S10b). E16 covered the suspension and the re-arm without replay.
       `test_automation.py::test_D13_a_reenabled_automation_fires_again` adds that a re-enabled
       automation acts on the next event.
     - **The e-stop drills** were slice A's (A01–A06, E24, E25, E49). The one case D13 names that
       none covered was the e-stop with Core running against the other enforcement kind:
       `test_execution.py::test_D13_the_estop_with_core_running_kills_a_registry_only_execution`
       stops an execution of a harness with no hook (enforcement `none`, routed only for ALLOW
       work) through the registry kill, uncharged, like E24's hooked one.
     - **Finding H-F1, for the owner (not changed).** The loop guard counts the escalated and
       rate-limited runs of the last hour including those before a re-enable. Observed: an
       automation suspended by three escalations and re-enabled fires again, then is suspended
       again by its first new escalation; one suspended by three rate-limited runs and re-enabled
       inside the hour is suspended again by its very next event and fires nothing. p14-design-gate
       §10 says "re-enabling re-arms it"; whether re-arming also clears the window it counts is
       not stated. The drill asserts only what is: the re-enabled automation acts on its next
       event. If re-arming should clear the count, the change is to count runs after the
       automation's `armed_seq` in `automations._guard`.

116. **D12, the fuzz harness** (`fa381b0`). `tools/fuzz_p20.py` is stdlib only.
     - **Routes.** Every command route, meaning the 51 with a request schema, gets bodies built
       from its own schema and then mutated: a type swapped, a required field dropped, an
       unknown field added, a huge or control-character string, an out-of-range number, deep
       nesting. The endpoint floor's recorded junk bodies are the corpus' other half. Each request
       runs through the real route table and `server.Handler._serve` in process, with no socket
       per request, so a large budget does not run into the ephemeral-port limit
       (p11-design-gate D31). The peer is attested as the user because attestation is not the
       fuzz target; it is tested where it was built (T-057).
     - **The canonicaliser.** Mutated inputs for every tool ADR-0052's mapping names, plus Skill,
       the aliases and unknown names. For an input it cannot parse it must answer the
       conservative class: one unclassified `exec`.
     - **The property** for both targets is the one D12 states: no 500 and no unhandled
       exception.
     - **CI**: `tests/v1/integration/test_p20_fuzz.py`, seed 20, with 3000 route requests and
       10000 canonicaliser calls, in about 3 s. On demand: `py tools/fuzz_p20.py --seed S --budget N`.
     - **What it found, both fixed in their own commits inside the accepted design:**
       - `d3812ca`: `POST /v1/policies/simulate` built the Action and each extra rule straight
         from the request's dicts. An empty action, an unknown field or an empty rule raised
         TypeError, which §5.5's table does not map, so the route answered 500. A TypeError
         there is the request's fault now: 400 `invalid_request`.
         `test_policy_http.py::test_H04b_…` covers three bodies.
       - `e34fd9c`: `canonicalise` let `realpath` raise for a NUL anywhere in a path, and on
         Windows for a path too long to resolve. The manager fails closed on any exception, so
         the hook answered halt and the execution ended instead of P9 judging the call. The
         module's own rule, a parse failure is one unclassified `exec`, now applies to these
         errors at its single entry, which covers the file tools and a command's path arguments
         alike. `test_execution_units.py::test_a_path_the_os_cannot_resolve_is_unclassified_not_an_error`
         covers it; the long-path case runs on Windows only, because POSIX `realpath` does not
         refuse a long name.
     - With either fix reverted, the CI fuzz test fails. Seeds 1–5 at a budget of 3000 per
       target are clean after both fixes.

117. **D14, the mutants** (`52d2137`). There are 11 new mutants in `tools/mutate_p20.py`.
     - Q100–Q103 break slice I's secrets gate: the local token created without O_EXCL, the
       local token readable by others, a cheap PIN record, a secret drawn where the table does
       not name it.
     - Q104–Q108 break the recoveries item 115 observes.
     - Q109 and Q110 put back item 116's two defects.
     - Results, each kill named by the test written for it:
       - The new set: 11/11 killed.
       - The whole suite: Q01–Q110, 110/110 killed, including the eleven e2e-guarded mutants,
         which rebuild the SPA.
       - P19's tray e-stop mutants P126–P131: 6/6 killed.
     - The SPA build needed `clients/app/node_modules`. It was installed with
       `npm ci --ignore-scripts --offline` from the local cache; no network was used.

118. **Slice H verified, and its status (2026-10-15).**
     - **Ran, on this slice's head**, all with `-m "not real_process"`:
       - Unit: `test_execution_units`, `test_p20_secrets`, `test_mutation_suites_parse`,
         `test_presence_units` and `test_automation_units`.
       - Integration: `test_execution`, `test_presence`, `test_automation`,
         `test_policy_http`, `test_p20_fuzz` and `test_estop_drills`.
       - Judge: `test_traceability`.
       - Result: 548 passed. Separately, `test_api_errors` (the endpoint floor) and
         `test_api_structure` gave 129 passed. `ruff`: clean.
       - With the SPA's dependencies installed, `test_mutation_suites_parse` type-checks the
         TypeScript mutants. That is most of the 769 s run; it is not slice H's cost.
     - **Not run:** the full `tests/v1`; POSIX; native tests; the SPA and browser e2e suites
       outside the mutants that rebuild the SPA.
     - **§10 against this slice:** every Q-mutant is killed and the affected P19 mutants were
       re-run. H-F1 is the owner's. Slice J (only if D8, D9 or D10 put it in P20) and slice K
       remain; G stays paused on T-004.
119. **H-F1 decided and built (2026-10-15).** The owner's answer, verbatim: "Re-enable clears
     count (Recommended)". `automations._armed_window` returns an automation's runs in the
     hour for events after its `armed_seq`, and both the rate limit and the loop guard count
     only those. Re-enabling sets `armed_seq` to the head, so a re-enabled automation starts
     both counts afresh; a real loop still trips the guard on its third new escalation.
     - Tests: `test_D13_a_reenabled_automation_fires_again` now also asserts it stays
       ENABLED after one and two new escalations and is suspended by the third;
       `test_H_F1_a_rate_limited_automation_reenabled_within_the_hour_fires` re-enables a
       rate-limit-suspended automation inside the hour and asserts its next event asks for a
       mission.
     - Mutants, each caught: the window ignoring `armed_seq` (both tests fail), only the
       guard ignoring it (the D13 test fails), only the rate count ignoring it (the H-F1
       test fails).
120. **Correction 2026-10-15 (T-093 review) to slice I, items 109-112.** The independent review
     of slice I (`.collab/reviews/T-093-853f63f.claude.md`, CHANGES) found the records below
     wrong or incomplete. Nothing above is reworded; this item supersedes the parts it names.
     - **D7 is overturned for third-party keys (supersedes item 110's heading and its second
       and fourth bullets, and item 109's opening sentence).** Core writes third-party API keys
       at rest. For an execution with an opted-in MCP server, `harnesses/sources.py:384-388`
       `flag_argv` copies the server's full definition from the account's `.claude.json` or the
       project's `.mcp.json`, `env` and `headers` included, into `run/exec/<id>/res/mcp.json` in
       plaintext, and nothing deleted it. Those fields are where users put their keys. §14.B
       had already said the secrets review must list this file (item 65); item 109 did not.
       D7 stands for harness-account keys only: `Account` holds no secret, and the adapter
       still removes `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.
       - **The owner's decision, 2026-10-15** (verbatim): "The last decision i was writing when
         you gave me options to choose , choose you reccomended option". That is "Delete at
         end + sweep": the file exists only while the execution's process runs, it is deleted
         on every end path, and a boot sweep removes what a crash left. DPAPI cannot help,
         because the CLI reads the file in plaintext.
       - **Built in T-099**, outside this slice's commits: `56e4c8b`, `b2dbf4c` and `c1cc825`
         in the detached checkout `D:/archeus-p20-mcp`, reviewed by an independent Claude
         reviewer (APPROVE on `b2dbf4c`). While a process runs the keys are still on disk, and
         after a Core-less e-stop the file stays until the next boot's sweep.
       - **Item 109's table gains a row:** opted-in MCP servers' definitions, at
         `run/exec/<id>/res/mcp.json`, plaintext JSON, written by `sources.flag_argv`,
         protected by the execution directory's inherited ACL and deleted when the execution's
         process ends (T-099).
     - **The secrets gate is rebuilt (supersedes item 109's "Gate" bullet).** As committed, it
       counted draw sites as a set, so all seven of the reviewer's writer mutants survived: a
       second draw in a listed function, `from secrets import`, an aliased `secrets`, `uuid4`
       used as a secret, the local token copied to a second file, `chmod` after the exclusive
       open, and an aliased `new_token`. `47404c1` replaces it with two exact censuses:
       - sources, counted per (file, scope, source) with every import form resolved, `uuid.uuid4`
         and `random.SystemRandom` added, and module bodies, class bodies and lambdas included;
       - secret writes, followed from a secret source, an external secret (an MCP definition, the
         hook token read back from the environment) or a writer helper's secret parameter,
         through assignments, to a content sink or a writer helper.
       It also fails on any mode change in `archeus/`. Its docstring names what it still cannot
       see: a secret kept on an attribute or a container and written by another scope, a second
       hop through an unlisted function, a subprocess or shell write, and a new external source.
       All seven reviewer mutants and the five earlier ones are caught on a `git archive` copy.
       `tools/mutate_p20.py` gains Q113 and Q114 for the write and mode gates.
     - **The Windows `0600` claim is narrowed (supersedes item 109's "holds on Windows as well as
       POSIX").** On Windows `os.open`'s mode sets only the read-only attribute, so `0o600`
       does nothing there. The test checks the POSIX mode literal on every platform and is
       renamed `test_the_local_token_file_is_created_exclusively_with_a_posix_owner_only_mode`.
       On Windows the file's protection is the home DACL (I-F1, T-096).
     - **I-F2 is corrected (supersedes its heading and first two sub-bullets).**
       - The documentation does name the token: `archeus/cli/gui.py:38-42` `profile_dir` says the
         profile holds "the device token". The conflict is with `discovery.py`'s docstring and
         plan §27 only.
       - The credential is stronger than "the scopes its launch code granted" says. The shell's
         launch code is minted with `observe`, `control`, `approve` and `admin`
         (`cli/main.py:258-260`). The device token it redeems for has no expiry and no supersede
         slot (`api/routes.py:224-231`, `core/application/commands.py:131-148`), so each
         `archeus gui` start leaves one more live admin-scope device credential. Whether older
         values linger in the profile's LevelDB files was not examined. T-096 owns the fix.
     - **I-F3 widens (supersedes its heading).** Each `run/exec/<id>/req/<seq>.req.json` also
       holds the raw tool `input` (`harnesses/hook.py:160-161`): Bash commands and file
       contents, unredacted and kept after the execution ends, with whatever secret an agent
       typed. Low, as before.
     - **Item 110's last-but-one bullet is narrowed.** Core (`archeus/`) does not write an
       account's home. The legacy engine does: `claude_sessions/hooks.py:639-640` `_save`
       read-modify-writes `settings.json` in each account's config directory, with no
       credential in it.
     - **Item 112 is incomplete; these rows complete it.** Its "Method" said each row of p15
       §8.4 was read; four were not, and neither was §8.2's tunnel assumption.

       | Surface / threat | Control as built | Evidence |
       |---|---|---|
       | Emergency stop | No PIN, by D10: the stop stays the fastest safety action | `api/routes.py:1075` (`POST /v1/estop`, `control`) |
       | Re-arm | **GAP.** `POST /v1/rearm` is a plain `control` route with no step-up, and a paired client's default scopes include `control`. D10 approved a PIN step-up on re-arm from a paired device; it is not built, and §14.B records it as blocked by the user until it is reconciled with V2-3. A stolen paired phone, through the configured remote host, can re-arm after the user pressed Emergency stop | `api/routes.py:634-637`, `:1076`; `core/application/executions.py:568-573`; `api/auth.py:35`; card T-098 |
       | Stolen device (corrects item 112's row) | Step-up applies today to the three human approval decisions only (`api/routes.py:742-748`), not to re-arm | as the row above |
       | Cloned client (token copied) | By design indistinguishable: a bearer token is the identity. Visible as unexpected presence or actions; revoke | p15 §8.4 |
       | Malicious client with a valid token | Can do what its scopes allow, through P9 like any client: every command is the route's application command, guarded as for the local CLI | p15 §8.4, §9 |
       | Cross-user | V1 has one owner; every `user_device` principal acts for that owner. Non-user principals hold no `observe` scope and cannot read or subscribe | p15 §8.4 (P19) |
       | Cross-project | A client sees the owner's whole workspace; a stream may be narrowed to projects, which is a subscription, not a permission | p15 §8.4, §11 |
       | Tunnel Host passthrough (§8.2) | **Stated assumption, GAP in the user documentation.** The local/remote split (`api/server.py:369-375`) and the local-only check (`api/routes.py:100-105`) rest on the request's `Host`, because a tunnel forwards from loopback. A proxy that rewrites `Host` to `127.0.0.1` makes every remote request local. p15 §8.2 says "the runbook says so"; no such runbook text was found in `docs/` (searched for the requirement in every `docs/*.md` and `docs/architecture/*.md`). Under PV-20 (ADR-0053 §7 A3) a tunnel-forwarded request is never direct local origin, but that attestor is inert until PV-20 activates it | p15 §8.2; this review |

       "No High was found on the remote path" (item 112) stands only with the re-arm GAP above
       stated beside it; whether that gap is High is the owner's to say through D10 and V2-3.

### Slice J — D10, the re-arm step-up from a paired client (2026-10-15)

121. **V2-3 resolved and slice J authorised (the owner, 2026-10-15).** Asked who needs a PIN to
     re-arm, the owner answered, verbatim: "Paired devices only (Recommended)". That is D10 as
     approved on 2026-10-05: `POST /v1/rearm` from a paired (non-local) client needs a valid
     step-up proof; a local client re-arms by being local; Emergency stop asks no PIN anywhere.
     The V2 copy (SS-4, SS-6) becomes device-specific (§14.F). This lifts §14.B's block on D10.
122. **Built (card T-098).** One mechanism, the one the three human approval decisions already
     use: `executions.rearm` calls P9's `authorization._step_up_valid`, which decides "paired"
     from Core's own record of how the client registered (`Device.origin == 'paired'`, or the
     pre-P15 platform rule), never from the request's address. A paired client without a PIN
     cannot satisfy it. A refused re-arm is `422 guard_failed` with the guard `step_up` (machine
     `core`, `disarmed` -> `armed`, trigger `rearm`), so the sentinel stays and Core stays
     disarmed. The route counts a wrong proof toward the same revocation as an approval's
     (`_step_up_failed`: the fifth in a row revokes the client) and resets the count on a right
     one. A proof is per request: a re-arm carries no step-up into the next one. Schema
     `REARM` adds an optional `step_up`; the generated client and the API reference are
     regenerated. The SPA's Control → About shows a PIN field above Re-arm when this client's
     `capabilities.step_up` is `pin`, and says a client with no PIN cannot re-arm and should
     re-arm on the desktop; the tray, the TUI and the local SPA are unchanged (all local).
123. **Verified (2026-10-15).** `test_presence.py` J01-J03: a paired client's e-stop asks no PIN;
     its re-arm without a proof, or with a wrong one, is refused and leaves Core disarmed; with
     its PIN it re-arms; the next re-arm asks again; the local desktop re-arms with none; a
     paired client without a PIN cannot re-arm; five wrong re-arm PINs revoke the client.
     Mutants Q115-Q117 (`tools/mutate_p20.py`): 3 of 3 killed. Focused set 379 passed
     (presence, e-stop drills, judge G5, execution, execution over HTTP, P19.5 core, start
     confirmation, API structure and generated client, API errors and auth, design gates, the
     fuzz harness); `test_spa_estop_about.py` 3 passed against a fresh SPA build; the client's
     node tests 233 of 234 (the one failure is the known CRLF working-copy case in
     `rowpulse.test.ts`). **Not run:** an end-to-end test of the PIN field with a paired browser
     (no e2e pairs a browser), POSIX, the full `tests/v1`. Item 112's re-arm GAP and item 120's
     re-arm row are closed by this slice.

### Slice H corrected after its review (2026-10-15)

124. **Correction 2026-10-15 (T-094 review) to slice H, items 115-117.** The independent review
     (`reviews/T-094-36160ba.claude.md`) returned CHANGES with two Medium findings. All six
     findings are answered here; items 115-117 are not reworded.
     - **Finding 1 (Medium), `faa53d1`.** `POST /v1/policies/simulate` still answered 500 for an
       extra rule whose decision is outside the vocabulary or whose `expires_at` is a number.
       Item 116's harness could not see it, because the schema types `action` and
       `extra_rules[]` as bare objects. The simulator now builds each extra rule through the
       `PolicyRule` entity `create_rule` uses. A USER rule with no `scope_ref` is given the
       owner's, and a GLOBAL user rule is refused as it is there. `PolicyRule` checks
       `expires_at`; `Action` checks its string fields. The harness gains `RECORDED` (valid
       bodies for the seven routes with a bare-object field) and `poke()` (one leaf replaced,
       chosen uniformly). With the fix reverted, the CI seed finds the 500, and so do 8 of 10
       seeds at budget 3000. The stronger corpus found two more 500s, both fixed in the same
       commit and pinned in `test_api_errors`: a `knowledge/forget` selector id that is not a
       string reached SQLite's binding, and an automation trigger type that is not a string
       reached the event registry's set lookup. Eleven seeds at budget 3000 are clean.
     - **Finding 2 (Medium), `87790fe`.** Item 116's property ("for an input it cannot parse it
       must answer the conservative class") held only for Bash and unknown tools. Write or Edit
       with a missing or non-string path came out `write_repo` on `.`, and WebFetch with a
       non-string URL as `web` with no host. Now a path tool whose required path is missing,
       empty or not a string (Glob and Grep may omit theirs), a fetch whose URL is not a string
       with a host, and a command that is not a string are each one unclassified `exec`. The
       harness's oracle asks that of every parsed tool, judged from the input. With the old
       canonicaliser it fails on about 700 inputs per seed. `mutate_p11`'s X12 follows the
       rewritten line and is still killed.
     - **Finding 3 (Low), `9dd1a57`.** Q118-Q124 name the gates no mutant named and the defects
       above: the CLI-draws test, the hashes-only test, the simulated rule, the path tool, the
       forget id and the trigger type. The registry-only e-stop drill could not be named as it
       stood: the e-stop reaches the kill twice (the command's stop and the manager's disarmed
       check), and the rig's 0.3 s stop grace made "now" and "after the grace" look the same.
       A mutant on either path, or on the kill itself, survived. The drill now runs with a 120 s
       grace and a 20 s wait, so only the immediate kill ends a hookless execution in time.
       Q120 (the kill under the e-stop waits out the grace) is killed by it and also names E24.
       Q118-Q124: 7 of 7 killed, run in a copy of the working tree. The slice A-F tests the
       review listed as named by no Q mutant stay recorded there; they are not mapped here.
     - **Finding 4 (Low, optional): not taken.** The fallback's unclassified `exec` carries the
       tool's name, not its input, so the approval shows no command and its single-use hash is
       not bound to one. What reaches that fallback (a NUL, a path the OS refuses, a missing
       field) cannot run as written anyway.
     - **Finding 5 (Low): answered by T-103.** The rate-limit trip's recovery is drilled by
       `test_H_F1_a_rate_limited_automation_reenabled_within_the_hour_fires` (`88a857b`,
       item 119), killed by Q112.
     - **Finding 6 (nit), two wordings.** In item 115, "through the registry kill" is, with Core
       running, the manager's handle kill (`manager._control` to `LocalNode.kill` to
       `adapter.stop(handle)`). It is not the `run/processes.jsonl` sweep that Core-down uses.
       In item 117, Q103 does not draw a secret at an unlisted site. It changes the draw call at
       a site the table already names (`token_urlsafe` to `token_hex` in the hook-token draw),
       and is killed on the call's text.
     - **Verified (2026-10-15).** Unit tests, policy, knowledge, automation, execution,
       execution security, API errors and the fuzz harness, `-m "not real_process"`: 1,090
       passed before the mutation-suite parse check. That check failed on X12's stale anchor,
       which was fixed, and all 32 suites then parse. Focused reruns after each commit passed:
       332, then 240. Revert experiments on archive copies: each fix reverted fails its own new
       test. **Not run:** the full `tests/v1`, POSIX, the full Q01-Q124 suite.
125. **Correction 2026-10-15 (T-103 review) to items 119 and 120.** The independent review
     (`reviews/T-103-7c92b10.claude.md`) found H-F1 sound and item 120 accurate, but the
     rebuilt static census claimed sinks it could never match: all 9 of its new mutants
     survived. Items 119 and 120 are not reworded.
     - **Finding 1 (Medium) and finding 2 (Low), `0199238`.** `write_atomic` and
       `write_json_atomic` are only ever called dotted (`config.write_json_atomic`), and the
       matcher compared bare names. Now `_name` resolves a dotted chain of any length, so a
       fully dotted `archeus.api.auth.new_token()` is a source. The atomic writers match on their
       last segment. `.writelines`, `print(..., file=...)` and a logging call on a logger are
       sinks. In a scope that writes a secret, a file copy is one more write. The CLI's draws,
       which the table exempts, no longer taint its own output. The docstring now names what
       stays unseen. Of 21 mutants (the T-093 reviewer's 7, the original 5, and this review's
       N1-N9), 20 are caught. The 21st, N8, stores a token as a device's name: a database row,
       out of the census's reach by construction.
     - **The runtime gate, `883e11d`.** `tests/v1/integration/test_p20_secrets_runtime.py`
       records every `secrets.token_urlsafe` draw with its kind, decided by the function that
       asked for it, and plants an opted-in MCP server's keys (an env var and a header) and an
       account settings secret. After two lifecycles (pairing, a launch redemption, a mission, a
       stream and a revocation over HTTP; an execution with two opted-in servers and a hooked
       tool call), every file under ARCHEUS_HOME is read as bytes, the database, its WAL and
       core.log included. Each secret may appear only where its kind is kept: the local token in
       `run/local-token`, the hook token in `run/exec/*/req/*.req.json`, the MCP keys in
       `run/exec/*/res/mcp.json`; device tokens, codes and the settings secret nowhere. Each
       lifecycle also asserts that what it expects to find is found. Q125-Q128: 4 of 4 killed.
       Q125 and Q127 (a token through the dotted atomic writer, an aliased chmod) are killed by
       the static census; Q126 and Q128 (a token logged to core.log, a token stored as a
       launch-redeemed device's name) by the runtime gate. That corrects `883e11d`'s message,
       which credited the runtime gate with "the last two".
     - **Finding 3 (Low), `0199238`.** The no-mode-change test runs through the import aliases
       and covers `copymode`, `copystat` and the shutil copies that carry mode bits.
     - **Finding 4 (Low).** Item 119's rate limit is per arm, and every enable moves
       `armed_seq`: a plain DISABLED -> ENABLED also restarts both counts, not only
       SUSPENDED -> ENABLED. Only a user device holding `admin` can enable. p14-design-gate §10
       gains a dated amendment saying so.
     - **Findings 5 and 6 (Low).** Plan §27 gains a correction: "since T-099 it exists only
       while the execution's process runs" holds once T-099 is integrated, and the hook token in
       `req.json` is the third plaintext credential Archeus issues and keeps. In item 120,
       "Item 110's last-but-one bullet" means item 110's fourth bullet of six, the one about the
       harness home "which Archeus does not write"; the last-but-one is "So, as D7 directs".
     - **Verified (2026-10-15).** `-m "not real_process"`, 850 passed. The set: both secrets
       gates, the fuzz harness, policy over HTTP and in process, the canonicaliser units,
       automation, e-stop drills, execution, execution security, API errors and auth, presence,
       knowledge over HTTP, judge G5, the doc gates. Mutants ran on copies of the working tree.
       **Not run:** the full `tests/v1`, POSIX, e2e.
126. **Correction 2026-10-16 (T-098 review) to slice J, items 122 and 123.** The independent
     review (`reviews/T-098-d6877a2.claude.md`) found the server side of D10 sound and asked for
     three fixes. Items 122 and 123 are not reworded.
     - **Finding 1 (Medium).** Re-arm had no disabled rule, so with nothing typed it sent
       `step_up: ""`, which Core counts as a wrong proof: five impatient taps revoked the client.
       The approval card's rule is now one helper, `stepUpBlocked` in `state/present.ts`, and
       both the approval card and Re-arm use it. A client with no PIN, or fewer than six digits
       typed, is not offered the button and is told why.
     - **Finding 2 (Low-Medium).** The PIN stayed in the e-stop section's state after a re-arm,
       so the next e-stop showed it already filled in. The field is emptied as soon as the
       re-arm returns, whatever Core answered.
     - **Finding 5 (Low).** Item 122's "resets the count on a right one" had no test for re-arm.
       `test_J03b`: four wrong PINs, a right one, an e-stop, four more wrong ones, and the client
       is still ACTIVE.
     - **Finding 6 (doc).** D10's amendment of the rulebook's §19 to "e-stop (confirm)" is
       appended there (`ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md` §19).
     - Findings 3 and 4 (a replayed key re-arms again; the PIN is recoverable from the stored
       request hash) predate slice J and are card T-107's, in another checkout.
     - **Verified (2026-10-16).** No e2e pairs a browser, so
       `test_spa_estop_about.py::test_a_pin_client_re_arms_only_with_six_digits_and_the_pin_never_stays`
       answers `/v1/sync` with Core's own answer and `step_up: pin`, and passes the re-arm on to
       the real (local) Core without its PIN after recording it. It checks that Re-arm is not
       offered with no PIN or five digits and is with six, that the PIN went with the request,
       and that the field is empty after a re-arm Core accepted and after one it refused. The
       real paired path stays covered at the server by J01-J03b. A node case covers the
       helper's four answers. Mutants Q129-Q131: 3 of 3 killed (Re-arm ignoring the client's
       capability and the PIN left in the field, both by the e2e; the reset deleted, by J03b),
       and Q115-Q117 are still 3 of 3 killed. `-m "not real_process"`: presence, e-stop drills,
       judge G5, the e-stop e2e, API structure and auth, 118 passed; the approval card's e2e
       files (copy, mission thread, P16, unification), 21 passed; the client's node tests 234 of
       235 (the known CRLF case in `rowpulse.test.ts`); `tsc --noEmit` clean; the doc gates
       (paths, traceability, design) 73 passed and the P20 mutation suite parses. **Not run:** a
       real paired browser, POSIX, the full `tests/v1`.
127. **Correction 2026-10-16 (T-094 re-review) to slice H, item 124.** The independent re-review
     (`reviews/T-094-2f93182.claude.md`) found finding 1's class still open one level down:
     `POST /v1/policies/simulate` answered 500 for a rule whose boundary VALUE is malformed
     (`{"paths": 5}`, `{"hosts": 5}`, `{"branches": 5}`, `{"environments": 5}`,
     `{"paths": null}`). `PolicyRule` checked a boundary's keys, not its values, and
     `rules.check_boundary` iterates each value. Pre-existing at slice H's head. Worse,
     `POST /v1/policies/rules` STORED such a rule (200), after which every evaluation of its
     class raised: simulate answered 500 and the hook path would halt every matching tool call.
     - **Fix.** `PolicyRule` refuses a boundary value `check_boundary` cannot read: `paths`,
       `hosts`, `branches` and `environments` are lists of non-empty strings, `max_cost_band` is
       one of the cost bands. Both `create_rule` and the simulator build through it, so both
       answer 400 `invalid_request`. A row is decoded through the same entity, so a rule stored
       before this change with such a value would now fail every read of the policy rules rather
       than one class's evaluation; no in-tree client writes a boundary and V1 Core has not
       shipped (it is on no released branch), so no migration is added.
     - **Pinned.** `test_H04b` holds the five bodies plus a `max_cost_band` outside the bands, and
       asserts the refusal names the check it is about; its decision and `expires_at` cases are
       now WORKSPACE-scoped, so they reach the check they name rather than failing on a missing
       owner (re-review non-blocking 1). `test_a_bad_value_inside_a_free_form_field_is_a_400_not_a_500`
       gains the stored-rule body. Q132 removes the check.
     - **The harness reaches it.** `poke()` now replaces a container as well as a leaf, and the
       simulate corpus holds an `ALLOW_WITHIN_BOUNDARY` rule. A second reach problem surfaced on
       the way: the route fuzz fires `POST /v1/estop`, and while the sentinel stands every
       evaluation is DENY before the engine reads a rule, so most of a run never reached policy
       (with the corpus change alone, the CI seed found nothing even at budget 10000). The fuzz
       now clears the sentinel after each request. With the fix reverted the CI test fails on a
       simulate 500, and so do 10 of 11 seeds (0-9 and 20) at budget 3000, a fresh Core per seed
       as `fuzz_p20.main` builds it; with the fix, seeds 0-11 and 20 at budget 3000 are clean (run
       in turn on one Core).
     - **Item 124's seed count.** "8 of 10 seeds at budget 3000" is 7 of 10 when measured the
       same way (seeds 0-9, `authorization.py` at `d6877a2`, the harness at `2f93182`, a fresh
       Core per seed): seeds 5, 6 and 7 find none. The CI seed finds it either way.
     - **Left for the card:** the simulated USER rule's misleading message on a Core with no owner
       yet, and the canonicaliser taking the first path field present whatever the tool
       (re-review non-blocking 2 and 3).

128. **Correction 2026-10-16 (Codex review of D7 and the threat model) to items 110, 112, 120,
     125 and 126.** Codex reviewed only D7 as amended and the credential threat model
     (`reviews/T-103-ec90967.md`, CHANGES, four findings). Nothing below changes code; it narrows
     what the earlier items claim and names what is still open.
     - **MCP keys are a non-isolated behaviour only.** Item 120's plaintext
       `run/exec/<id>/res/mcp.json` describes executions without isolation, which is all this
       tree runs. ADR-0053 admits no MCP opt-in inside an isolated execution, and nothing here
       changes that: an isolated execution receives no MCP definition and no key. Admitting MCP
       servers under isolation would need a new owner decision; the owner's "Delete at end +
       sweep" answer of 2026-10-15 (item 120) covers the non-isolated file only.
     - **Readers, current and target.** An inherited ACL is not a reader boundary. Today any
       process running as the same user can read every plaintext credential below; another user
       can read one only if ARCHEUS_HOME's ACL lets them. Core writes no ACL. In this tree it warns
       on a broad principal that can WRITE the home (T-089, `3bdc485`); the warning for a broad
       READER of the home and of `run/local-token` is T-096 (`a2be0f4`, `D:/archeus-p20-f`) and
       is not in this tree. The PV-20 target, not in force while isolation is not enforced: an
       isolated execution reads only its own hook request, never `run/local-token`, another
       execution's files or any MCP key. No item claims isolation protects these files today.
     - **Inventory, file retention and credential validity** (two different lifetimes):
       - *Local token*, `run/local-token`: the local scopes, no expiry. Core reuses it across
         restarts while it is live and mints a new one only when it is not
         (`core/runtime.py`); the file is not removed when Core stops. Valid until revoked.
       - *Hook token*, `run/exec/<id>/req/*.req.json`: one per execution, valid while the
         execution is live. The files outlive the token; nothing in this tree deletes an
         execution directory (I-F3).
       - *MCP keys*, `run/exec/<id>/res/mcp.json`: in this tree the file persists indefinitely.
         With T-099 (not in this tree) it is deleted on every end path and swept at boot, but a
         crash or a Core-less e-stop leaves it until the next boot, and no deletion can expire a
         third-party key once copied; rotating it is the key owner's, outside archeus.
       - *Desktop shell page token* (missing from item 125's list): in this tree the Qt shell's
         page credential is a device token with observe, control, approve and admin scopes and no
         expiry, persisted in the Qt profile's IndexedDB under ARCHEUS_HOME, and older copies may
         remain (I-F2). T-096 (not in this tree) keeps it in memory only and revokes an old
         stored one on first launch; the revoked value's bytes can remain, dead, in the profile's
         LevelDB log.
       - *PIN-derived request hashes*: in this tree a command carrying a step-up proof stores a
         plain sha256 of its arguments, PIN included, in the idempotency table for 24 h, and a
         6-digit PIN is recoverable from it (T-098 review finding 5). T-107
         (`D:/archeus-p20-idem`, not in this tree) keeps proofs out of the hash and migration
         0016 drops the old rows.
     - **Backups.** A backup is an SQLite online-backup copy of the database only
       (`infra/db/backup.py`), so no file under `run/` is in one. The database holds token
       hashes, not tokens; in this tree it also holds the PIN-derived hashes above while they
       are kept, and a backup taken in that window keeps them for the backup's life.
     - **Item 125's runtime gate is bounded by what it exercises.** "Device tokens, codes and the
       settings secret nowhere" holds for the paths its two lifecycles reach. It launches no Qt
       shell, so it says nothing of the page token; its HTTP mission step is refused
       (`403 remote_host_required`, unchecked; T-103 re-review finding 6), so no mission is
       created; the rig execution writes no `core.log`, and the user's PIN is not among the
       scanned values (re-review findings 1 and 3).
     - **Still open, unchanged:** no Core-held rotation of the local token; no deletion of
       finished execution directories; no expiry or rotation for the page token in this tree.
     - **Item 126, corrected (T-098 re-review, Low).** "No e2e pairs a browser" is wrong:
       `tests/v1/e2e/test_unification.py` (lines 141-197) pairs a phone page through `Tunnel`
       with origin `paired` and approves with its PIN. The stubbed e2e item 126 describes is
       still a valid gate for the Re-arm rule; a real paired re-arm case on that fixture was
       not added.
     - **Correction to the PIN-derived bullet above** (Codex re-check, `reviews/T-103-cbc0ee6.md`).
       "For 24 h" is how long a stored answer replays, not how long its row is kept. A row is
       deleted only when its own key is used again after it expired (`writer._recall`);
       `infra/eventlog/retention.prune` deletes expired rows, but nothing in `archeus/` calls it.
       So in this tree a PIN-derived hash can stay in the database indefinitely and be in any
       later backup, not only in one taken within 24 h. With T-107 no new row holds a proof and
       0016 drops the old ones; the idempotency table's unbounded retention for every other
       command stays open.

### T-096 — I-F1 and I-F2 as built (2026-10-15)

These items are numbered T-096.1 to T-096.4 here. Slices H and J were appended to this section in another
checkout, and the next candidate rebuild (T-072) gives these items their place in the sequence.

T-096.1. **I-F1: the home check reads read access as well as write** (`a2be0f4`).
     - `DaclReaders.broad_reader` sits beside `broad_writer` and shares its ACE walk. There is
       no second parser.
     - Read means an allow ACE carrying `GENERIC_READ`, `GENERIC_ALL` or `FILE_READ_DATA`.
     - The check reads the home, then `run/local-token` once it exists. Write is reported
       before read.
     - It warns only. No ACL is written, and the static gate holds.
     - The default home under `%LOCALAPPDATA%` gets no new warning (read-only measurement). A
       home under `D:\` reports Authenticated Users.
     - This disposes of item 111's I-F1 by its first option.

T-096.2. **I-F2: the shell's page keeps its device token in memory only** (`9abca6c`).
     - **Decision.** The owner, 2026-10-15 (AskUserQuestion answer, verbatim): "Memory-only
       (Recommended)". The other options offered were "Memory-only, many windows" and "Keep
       on disk".
     - **The slot.** The launch codes the shell asks for take the slot `desktop shell page`
       (`SUPERSEDE_SLOTS`), so each page credential revokes the one before it.
     - **Memory mode.** The page is told `memory=1` and holds its token in a module variable.
       `sessionStorage` holds only the flag, and IndexedDB is never written.
     - **Reload.** A reload in the shell is answered with a fresh launch address (`?r=N`), so
       the page stays signed in. With Core down, the page shows B7's snapshot.
     - **Unchanged.** `core --open` and the legacy GUI's "Open Archeus V1" take no slot and
       still store their token in that browser.
     - **Owner-accepted consequence.** A second concurrent `archeus gui` signs out the first
       window's page.
     - **Not off-the-record.** The same profile keeps the appearance choice and B7's snapshot
       across restarts.
     - **What it reverses.** p19 item 81's "the device token … survive[s] a restart", amended
       in that document.
     - **Authority.** D1 does not cover this credential: D1 is the shell's own credential,
       item 86. The owner's answer above is the authority.

T-096.3. **A page token an earlier shell stored is revoked before it is deleted** (`2d2f3b0`).
     - **Why.** Such a device was redeemed before the slot existed, so no later page
       credential supersedes it. It keeps observe, control, approve and admin with no expiry.
       Deleting the IndexedDB key alone revoked nothing, and a QtWebEngine probe found the
       deleted value still in the profile's LevelDB log and tables.
     - **The order.** On its first memory-mode load the page reads its own device id from
       `GET /v1/sync` with that token, revokes the device with
       `POST /v1/devices/{id}/revoke`, and then deletes the key.
     - **Already dead (401).** The key is deleted with no revoke.
     - **Core down or refusing.** The token stays where it is and the next launch tries
       again. Deleting the only copy of a live admin token is the one outcome that cannot be
       undone.
     - **What may remain on disk is a dead token.** LevelDB keeps a deleted value's bytes
       until it compacts, and no page can force that.
     - **Deleting both databases was tried and not used.** Deleting `archeus` together with
       `archeus-snapshot` empties the origin's store. That erased the bytes in a standalone
       probe. In the real shell flow, with both deletes reported successful, the bytes
       survived the next launch. It would also cost B7's snapshot for an erasure it does not
       deliver.
     - **Tests.** The real-Qt e2e seeds a legacy page token the way an earlier shell stored
       it. After the first launch that device is REVOKED, and after the second its token
       answers 401. Node cases cover revoke before delete, Core down and an already-dead
       token. Mutants: 4 of 4 caught.

T-096.4. **Items 109 and 111, corrected by this append.**
     - **Item 109's local-token Protection cell** names write only. With T-096.1 the check
       also warns when the home or `run/local-token` can be read.
     - **Item 109's row "The Qt shell page's device token"** (IndexedDB, plaintext)
       describes the shell before T-096. The page now holds that token in memory only
       (T-096.2). A token an earlier shell left is revoked and then deleted (T-096.3).
     - **Item 111's I-F1 and I-F2** are disposed of by T-096.1 and T-096.2.
     - **Unchanged.** The page token keeps the D2 grant (observe, control, approve, admin)
       with no expiry (p19 B8, p16 D2). Changing that is a new owner decision.

129. **Integration round 5 and T-109 as built (2026-10-19, cards T-108, T-109).** Recorded after
     the candidate was rebuilt; nothing earlier in this section is reworded.
     - **Order of this section.** The round-5 merge kept both sides of section 12 and renumbered
       nothing: items 115-128 (slices H and J and their corrections, merged first) are followed
       by T-096.1-T-096.4 (merged after), which keep their own numbers. This item follows both.
     - **The candidate (T-108).** Detached checkout `D:/archeus-pv20-int5`, built from round 4's
       `91cbb0c` by `--no-ff` merges naming each producer: `8829255` (T-092 + T-080, `44cbb47`),
       `1dc0bf6` (T-083, `4eb7ca5`), `046d3b9` (T-089, `02007f1`), `b63fed4` (slices H, I, J;
       T-093, T-094, T-098, T-103; `2b6e852`), `99028da` (T-099, T-101, T-102, T-105; `b73f875`),
       `688443f` (T-096, `e7141c1`), `832e704` (T-107, `1b87969`); then `cherry-pick -x` of the
       CI cards' own commits (T-091 `b1ff4a0`, `cbb2c78`, `b8754a0`, `7bca0b5`; T-095 `4cb0513`;
       T-104 `f5ccea9`, `e4e3ce4`). `3d98f84` (a clients/app dependency bump on the pushed
       branch, in no CI card) was not taken; that is the owner's call.
     - **Union resolutions.** `688443f`: this section (above) and `target-architecture.md` (the
       T-089 qualification, then T-096's read amendment). `832e704`: `test_presence.py` (J03b,
       then J04, J07, J05, J06). `routes.py` merged cleanly to T-107's side, so a replayed re-arm
       returns before T-098's step-up reset and before the sentinel is cleared.
     - **Two fixes the merge needed** (new commits, not union). `9a34e65`: with T-099 merged,
       `mark_ended` deletes `res/mcp.json`, so item 125's runtime gate now also scans just before
       `drop_mcp_config` and asserts the keys are gone after the execution ends. `ca123e5`: T-102
       re-raised a failed removal of a stale halt report as a new `OSError`, so the refusal's
       cause was the wrapper and two S2-L unit tests failed on T-102's own head; the removal now
       refuses with `SpawnWriteFailed` carrying the original error, and T-102's `workspace`
       charging is unchanged.
     - **Verified on `ca123e5`.** Filtered `tests/v1` 4430 passed, 114 skipped, 3 xfailed,
       0 failed (round 4: 4323, 112, 3; the two new skips are SPA e2e tests needing a built SPA).
       Reviewed: `reviews/T-108-ca123e5.claude.md` APPROVE and `reviews/T-108-ca123e5.md`
       (Codex, the section-12 union and `ca123e5`) APPROVE.
     - **T-109 as built** (`1adbd8e`..`cddec29`, fast-forwarded onto the candidate,
       `reviews/T-109-cddec29.claude.md` APPROVE). (a) `test_presence.py` J04b builds the
       busy-retry shape (a keyed re-arm answered 503 that commits later; the same-key retry
       answers armed false and Core stays disarmed) and J04 replays while armed. (b) In memory
       mode the shell page's `clearToken` no longer deletes the IndexedDB copy, which stays
       `retire()`'s alone; node cases keep the stored token when Core refuses. (c) Item 125's
       runtime gate logs the rig through Core's logger so `core.log` is scanned, scans a
       12-digit PIN, fails on a file it cannot read instead of skipping it, and its HTTP mission
       step now runs under the local token and asserts 200. (d) An unparsable registry line is
       logged and skipped instead of failing every boot, and the no-adapter kill logs whether a
       kill was actually issued. (e) A paired client with no PIN reads one reason it cannot
       re-arm, not two.
     - **Item 128, corrected for this tree.** Its "in this tree" statements described the slice H
       checkout. In the candidate: the broad-READER warning (T-096.1) is present; the shell page
       keeps its token in memory only (T-096.2, T-096.3); MCP keys are deleted when the
       execution's process ends and swept at boot (T-099), still on disk while it runs and after a
       crash or a Core-less e-stop until the next boot; no new idempotency row holds a step-up
       proof and migration 0016 dropped the old ones (T-107), while the table's unbounded
       retention for every other command stays open. Its runtime-gate bullet is corrected by
       T-109 (c): the HTTP mission step is no longer refused, `core.log` is scanned and the PIN is
       among the scanned values; the Qt shell is still not exercised.

130. **Built (card T-116, 2026-10-19): a launch opens one terminal.** T-113's probe found that
     two concurrent resume requests, or two hand-off requests, carrying one idempotency key
     opened two terminals (3 of 3 runs): the second request received the writer's stored answer
     (`duplicate: False`) and went on to `_launch`, whose `launched_seq < launch_seq` guard was
     read before the first launch was recorded. The owner chose "Claim in the writer
     (Recommended)" (2026-10-19, verbatim) over a per-session lock.
     - **As built.** `SessionService._launch` first runs a writer command, `claim_launch`; only
       the request whose claim wins opens a terminal, every other one answers "nothing to
       launch". The writer runs one command at a time, so the claim is atomic and holds across
       threads and HTTP requests alike. The claim is a new `Session` field, `launch_claimed_seq`
       (non-negative, never above `launch_seq`; kept out of the API view, so the schema and
       `generated.ts` are unchanged), and records a `session.observed` event as the launch
       outcome does. No migration: entity rows are JSON bodies and a missing field reads 0.
     - **A crash between claim and terminal.** The claim is settled at boot exactly as an
       unclaimed unsettled launch was: `expire_launches` sees `launch_seq > launched_seq` and
       records `launch_expired`; a restarted Core opens no terminal nobody asks for now (D21),
       and the next resume launches normally.
     - **Verified.** `test_sessions.py` T35 (concurrent same-key resume and hand-off: one
       terminal; 5 of 5 repeated runs), T36 (a replay after the launch opens nothing, a new
       request does), T37 (claimed, crashed, expired at boot, next resume launches). Mutant
       Q133 (a second claimant wins) is killed by T35.

131. **Built (card T-106, 2026-10-21): O7's start wait and spawn breaker.** O7 (items 64, 72)
     was decided 2026-10-08 as uncharged with a bounded backoff and a breaker; the mechanism
     was left open. A permanent start failure re-dispatched without bound (T-102's review: 63
     executions in 4 s; 33 in 2 s on f483f87 in T-106's first test). T-110 listed what the
     decision left open; the owner answered all ten on 2026-10-21 (AskUserQuestion, verbatim):
     Q1 "Per CLI on this machine (Recommended)", Q2 "3 (Recommended)", Q3 "10 minutes
     (Recommended)", Q4 "Doubling, 15 s up to 5 min (Recommended)", Q5 "Automatic trial after
     5 min (Recommended)", Q6 "CLI status + mission reason + notification (Recommended)", Q7
     "Yes, both the same way (Recommended)", Q8 "Router: don't dispatch to that CLI
     (Recommended)", Q9 "Yes, build now, switch stays off (Recommended)", Q10 "Rebuilt from
     recorded failures (Recommended)".
     - **The fact recorded.** A start that creates no process (`SpawnFailed`, isolated or not;
       not `SpawnWriteFailed`, still the charged `workspace` of T-102, and not
       `AlreadySpawned`, still `binding`) ends its execution with the new uncharged stop
       reason `spawn`, its reason kept in the execution's `summary`. Nothing else is stored:
       no counter, no deadline, no breaker row.
     - **Derived from it** (`executions.py`). A harness's streak is its `spawn` ends since its
       last execution that started. Three within 600 s open the breaker; it stays open 300 s
       after the latest failure, then is half-open: one task may be dispatched, and while
       that one has not started every other waits 15 s more. A start closes it; a failed
       trial opens it for another 300 s. A task's own wait after n failed starts in a row is
       15 s × 2^(n-1), at most 300 s. A restart derives the same state from the same records
       and gives nothing back.
     - **Where it acts.** The router (P10) has a new elimination step `breaker`, after
       `restriction` and before `health`, reading the harness's `breaker` in the decision's
       snapshot: an open harness is not a candidate ("cannot start: <reason>") and its
       `until` is the decision's `unblock_at`. A snapshot without the field routes as before,
       so recorded decisions replay unchanged. When nothing else could run the task,
       `dispatch_task` records that decision and leaves the task READY and its mission
       EXECUTING (it no longer fires `dispatch` before routing, so nothing moves); the
       engine's admission skips a task inside its own wait or inside such a decision's
       `unblock_at`. A task another harness can run goes there. No unisolated fallback, no
       A4 bypass, `PRODUCTION_DISPATCH_ENABLED` unchanged, no S1 component.
     - **Visible.** `GET /v1/harnesses` carries each harness's `breaker` (`state`, `until`,
       `error`; null when closed; schema `HarnessBreaker`), shown by the TUI's resources
       section and the SPA's Harnesses table as "cannot start". The waiting task's reason is
       its recorded route ("Nothing could run this until … Not used: fake — cannot start:
       …"). The trip appends one `harness.state_changed` (payload `breaker: open`), the
       registered type's first use; the Qt tray says "<harness> cannot start a process;
       Archeus tries again in 5 minutes" for it (D1 extended by Q6), and only for the trip,
       not for a failed trial.
     - **Verified.** `test_spawn_breaker.py` (the loop bounded, the per-task wait doubling,
       the trip once with its notice and a READY wait, replay, a restart rebuilding the same
       state, a half-open trial closing it, a failed trial reopening it without a second
       notice, another harness taking the task), the O7 unit tests in
       `test_execution_units.py` and `test_routing_units.py`. Mutants Q134-Q141.
     - **Left as it was.** A reconcile that finds an INTENT whose isolation record says
       `failed` (a Core that died between the failure and its refusal) still refuses it as
       `binding`, so it does not count toward the breaker.

132. **Correction r1 to item 131 (card T-106, 2026-10-21, after the review of 7d54856).**
     - **Core's loop wakes a waiting mission.** `EngineLoop` parks a mission whose step changed
       nothing and stepped it again only when a command moved it; a task waiting out its start
       wait or an open breaker moves nothing when the wait ends, so under Core's own loop the
       retry (Q4) and the trial (Q5) never came. `Engine.step` now reports `wake_at`, the
       earliest end of such a wait among the mission's READY tasks, and `EngineLoop` steps the
       parked mission again at that time (its idle wait is shortened to it). Tested with the
       real `EngineLoop._pass` and the manager's pass, rows untouched (Q142).
     - **Counted as `spawn` too** (Q7, Q10): an establishment failure found at a restart
       (`_reconcile_isolated`, item 131's "left as it was" withdrawn), an isolation decision
       that could not be taken, and a hook stage that could not be made (Q143, Q147, Q148).
       `AlreadySpawned` stays `binding`: the marker means a process may exist and the end goes
       to reconciliation; a test pins it (Q150).
     - **Bounded reads.** A harness's executions are read newest first, in SQL only the rows the
       streak reads (a failed start, a start, an INTENT), and the read stops at its last
       start; a task's route wait reads only its latest decision, and parses its `unblock_at`
       only once the decision is known to be the breaker's (Q151, Q152). Measured on an
       in-memory SQLite 3.37 table of executions (this PC): 2 ms per harness with 10k
       executions older than the last start, 7 ms with 30k, 6 ms with 30k never-started rows
       after it. The cost is the rows SQLite scans (json_extract per row, about 0.2 µs), not
       the rows decoded. Upgrade path, not built: an index or a stored harness column, when
       that scan shows up in a profile. **Superseded by item 133:** these figures are for
       the rowid order that r2 replaced; item 133 has the current cost.
     - **Time order.** Failure times are sorted before the window and the cooldown are judged:
       an INTENT that waited can fail after a later one (Q144, Q145).
     - **The trial.** An INTENT counts as the half-open trial only while its mission is
       EXECUTING, so one parked by a pause or a block no longer holds every other task back
       (Q146). **Known limit:** a resume (PAUSED to STARTING through `resume_checked`) is not
       seen as a trial; a resume and a dispatched trial can both start while half-open.
     - **Words.** The SPA's end reasons say `spawn` ("stopped: its agent CLI could not start a
       process; Archeus tries again"). p11-design-gate and p21-design-gate carry dated
       as-built appends for the stop reason list and the tray notice.
     - **Mutants:** Q142-Q152; Q149 and Q150 are the review's ad-hoc M1 and M2.

133. **Correction r2 to items 131-132 (card T-106, 2026-10-21, after the review of 6a6faab).**
     - **A reset in the past is never a wait (review N1, a hot loop).** A blocked route's
       `unblock_at` was the earliest of the provider resets and the breaker's time, with no
       check against now; a reset already past made the task routed again on every pass.
       The router now takes only the readable times after its own `now` (`_ahead`): the
       breaker's time when it is after now, a provider reset only when it is a future time
       (Q153, with a real `EngineLoop` test that counts the passes' route decisions).
     - **A malformed provider reset never stops Core (N3, r3 finding 1).** Provider resets
       are free text. `reset_at` catches a value that does not parse; it compares as aware
       datetimes and never calls `timestamp()` on a naive value (on Windows that raises
       OSError outside 1970-2038). Q154 is the parse catch (the `not a time` case); Q159 is
       the platform call put back, killed on every platform by a unit test. The
       parametrized test also covers '1 hour' (sorts before the digits), naive 1960 and 9999,
       an offset-suffixed pair and a five-digit year.
     - **One zone-independent parse of `unblock_at` (r4 finding 1).** A naive reset is UTC
       by rule, not the machine's local time. The router writes the instant with its offset
       (`reset_at`, `_ahead`), and `route_wait` reads that string through the same
       `reset_at`, so the two sites agree in any zone. Before r4 the router returned the
       naive string and `route_wait` read it in local time: east of UTC the wait came out
       in the past (a hot loop up to the breaker's window), west of UTC hours late. Q162
       puts both halves of that back; the subprocess test runs under two TZ values of
       opposite signs. The zone of a provider's reset is not known to the code: if a feed
       sends local times, that is a feed fact the owner must confirm.
     - **A non-mapping `resets_at` is no wait, not an error (r4 finding 4).** The router
       and the snapshot read the value as a mapping only (Q163).
     - **The streak is cut by the time it was decided, not by creation order (N2).** A
       failed start's end, a start, or a trial's creation; rowid only breaks ties. Creation
       order gave a false trip: an INTENT that waited, then started after three failures
       were created, cut the streak too late. `julianday()` compares the three formats
       (`created_at` has milliseconds, the others whole seconds). **Trade-off, recorded:** a
       backward wall-clock step misorders the cut by the recorded times (a failure recorded
       before a start that happened earlier counts as older). Q155, Q156; the unit tests
       cover out-of-order rowids, a clock step and mixed precision. **A backward clock step
       (r4 finding 2, replacing the r3 cap, which bounded only the reported value):** a spawn
       end, a start or a trial recorded after now is not history yet, so the streak, the
       breaker and a task's wait ignore it (Q160, Q161). The open window is then always
       one cooldown from the latest counted failure, which is at most now: at any call time
       the breaker is open until at most now + 5 min, and a task waits at most its own wait
       from now. Once real time passes the recorded times they count like any other failure.
       Cost of this choice: a failure recorded ahead of the clock that really happened is
       not counted until the clock catches up. **Same-second ties
       (r3 finding 3):** `started_at` and `ended_at` have whole seconds, so a failure and a
       start in one second compare equal and fall back to rowid; the window of that is one
       second. Storing milliseconds would close it; not done (it changes stored formats).
     - **Cost (measured, in-memory SQLite 3.37, this PC).** The time order sorts every
       started, failed or trial execution of the harness per routing decision: about 10 ms
       at 10k successful starts and 33 ms at 30k (the streak itself still stops at the last
       start). Upgrade path, not built: a promoted harness column with an index, or a
       read bounded to the last window. Ceiling recorded here, not in code.
     - **The idle wait is cut to the deadline (N4).** Tested with a 30 s idle (Q157).
     - **The streak stops reading at its start (N5).** Counted at the cursor, not by the
       decoder (Q158).
     - **Not changed, by reasoning (N1 part b).** The breaker branch in `dispatch_task`
       does not re-check `unblock_at` against now: the router is the only writer, and it
       now returns only future times.
     - **Correction r5 (review of c290b87).** The trip is read at the failure's own end,
       not at the command's start: `refuse` stamps whole seconds inside the command, so a
       second boundary between the two hid the trip-making failure and its notice (Q164).
       `_ahead` truncates to milliseconds before the comparison (Q165). A provider limit is
       stored as the router reads it, written with Z, and `accounts_tick` compares it the
       same way, so a naive reset releases the account at one instant in any zone (Q166,
       Q167). A task's wait reads a success by its start, as the breaker does (Q168).
     - **Correction r6 (review of 5e8102d).** A provider reset already past, or not a time
       at store time, holds the default window (1 h): released on the next tick it is
       refused again, uncharged, on every pass, an unbounded loop (Q169, Q172). A stored
       limit that is not a time releases the account without raising (owner-accepted,
       one-off, legacy rows only; Q170, Q171). A stored text with no offset is a row written
       before r5 and is read in local time, as the pre-r5 tick read it, because the UTC
       reading would release a West-of-UTC account early and the local reading releases
       nothing early that was not already released (Q167; the r5 "one instant in any zone"
       claim holds for rows written since r5 only). Correction r7 (review of 098d0d3): a
       legacy value outside the platform's range (naive 1900 or 9999 on Windows, where
       timestamp() raises OSError) releases without raising (Q173); a reset equal to now
       holds the default window (Q174).
     - **Known, recorded (N6).** An INTENT created before a trip, whose mission was paused,
       can start when the mission resumes while the breaker is open; a start closes the
       breaker. Bounded by the INTENTs dispatched before the trip.
     - **Owner-accepted limit 6ii** (a resume is not a trial) stays as item 132 states.
     - **Mutants:** Q153-Q163. Q152 is redefined in r4: the breaker check dropped from
       `route_wait` (a health-blocked decision is waited on); the test uses a valid future
       time, so the parse cannot hide it. Q145 and Q153 follow the current lines.
134. **Correction r8 to items 131-133 (card T-106, 2026-10-22, after the review of b50fcd9).**
     - **Owner sign-off, 2026-10-22: "Accept read-all, cap 600".** The streak reads the
       harness's 600 newest execution rows by creation (`LIMIT 600`), decodes each and
       orders them in Python. This replaces the read that stopped at the start (N5 and
       item 131's "the read stops at its start"). **Ceiling:** 600 rows per harness per
       routing decision and per task admission check; a streak longer than 600 rows is
       cut at its 600th row. Upgrade path, not built: a promoted `decided_at` column with
       an index, or json1 once the SQLite floor allows it.
     - **The pre-filter matches the body's own key** (`"harness_id": "<id>"`, the JSON the
       row was written with). Registered ids are ASCII literals (`claude_code`, `pi`,
       `fake`), so an escaped id is not reachable today; it is tested anyway. The bare-text
       match let other harnesses' rows (a summary that says `pi`) take the 600 slots.
     - **A replayed decision judges its resets as the builder does (review of b50fcd9,
       Required 1).** `resources.replay` writes each stored reset as `instants.ahead`
       against the recorded `now` before the router reads it, so a decision recorded before
       item 133's written instants replays as it was decided: a reset equal to now is no
       wait, a future reset is the same instant as 533e3e9 (a non-UTC
       reset keeps its offset, as `instants.ahead` writes it).
     - **The builder keeps the original assertion on raw provider text**
       (`test_T106r8_the_builder_writes_raw_resets_as_instants_and_names_the_earliest`);
       the router test feeds written instants.
     - **Mutants:** Q175-Q179.
135. **Correction r9 to items 133-134 (card T-106, 2026-10-22, after the review of d684947).**
     - **Offset readings order by instant (review R1).** Item 133's router compared the
       written texts as strings, and a non-UTC text does not sort by its instant: a reset of
       13:00+02:00 (11:00Z) lost to 12:00Z, and a reset of 09:30-01:00 (10:30Z, ahead of
       now) was no wait. A reset is now {at, key}: `at` is the text a decision carries
       (offset kept, as 533e3e9 wrote it), `key` the same instant in UTC (ms, Z). The router
       takes the waits by `key`, compares `key` with `now`, and writes `at` of the earliest.
       The router still imports nothing (B1). Replayed decisions keep their text: each
       reset recorded as text is written again, and one already written is kept.
     - **Cases A and B, on the router, the live builder and the replay alike** (the
       `_RESET_CASES` table in tests/v1/unit/test_routing_units.py, expected values
       checked against 533e3e9). Mutants Q180-Q183.
     - **The cap is by creation order (review S1, probed).** Creation order and decided
       time can disagree: a failure created first and ended last falls outside the 600
       newest rows. Ordering the SQL by decided time needs json_extract, which the SQLite
       3.31 floor forbids, so the owner's "cap 600 by creation" stands as written and is
       pinned by test_O7_the_cap_is_by_creation_order.
136. **Correction r11 to item 135 (card T-106, 2026-10-23, after the review of 65dd37c).**
     The 600 cap counts counting rows only. It took the harness's 600 newest rows before
     the Python filter dropped those that are neither a failed start, a start nor an
     INTENT, so 600 newer `binding` refusals pushed a tripped breaker's failures out of
     the read and it read closed. The SQL now keeps only `state = 'INTENT'` or a body
     with `"stop_reason": "spawn"` or `"started_at": "` (the encoding `rows.encode`
     writes; SQLite 3.31 has no json_extract), so a non-counting row takes no slot. The
     Python filter stays for the harness check. The replay text is unchanged; the other
     nits (the unused `instants.written`, the "same text" wording above, the `_newest`
     docstring) are one-line fixes. Mutant Q184
     (test_O7_rows_that_cannot_count_take_no_slot_of_the_cap).

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
| ADR-0052 tool removal (PV-22): `--tools` from the action classes and the CLI snapshot, the normalised MCP deny, the conditional `Skill` | ADR-0052; C1, C2, C3 (§4.1) | F | automated green and CLI-level verified (§12 items 87–90); **ADR-0052 §7's observed run is D15's, NOT RUN** |
| Notifications out of P20 (to P21); plan and dependency records updated | D8 | records | done (`8fe7ce3`) |
| The Codex adapter to P23; G7's xfail re-marked `phase:P23` | D9 | records | done; no `phase:P20` xfail remains in `tests/` |

"Completed" here means implemented with its automated evidence. No slice is complete as a
gate while its manual checks are NOT RUN.

### 14.B Approved, not implemented

| Item | Decision | Slice (§5) | Note |
|---|---|---|---|
| The re-arm PIN step-up | D10 | its own slice (J's list) | approved **as proposed**: step-up on `POST /v1/rearm` from a **paired (non-local)** device, through the existing PIN path; rulebook §19 amended to "e-stop (confirm)". Not built. **Blocked** (the user, 2026-10-05) until the user reconciles it with V2-3 (§14.F); no interpretation is chosen here |
| The secrets review, with the DPAPI row amended if Core stores no API key | D7 (amendment) | I | not started; must list `run/exec/<id>/mcp.json` (the opted-in MCP servers' full definitions, possibly tokens; §12 item 65) |
| ADR-0051 §2 boundary tests; the threat model | ADR-0051 (DECIDED) | G | **PAUSED** — slice G's verification found two Critical OS-confinement findings (G1 credential reach, G2 local-token reach); ADR-0051 §2 is not satisfied as built; remediation is PV-20 (PV-13 study delivered 2026-10-07; PV-20 decisions approved and recorded in ADR-0053; implementation not started). §12 items 92–98 |
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
| §5 order | The order of the slices after F (F was chosen after E, §4.1) | which slice is next |

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
  with its verification items in item 49); PV-22 built (slice F, **built**: §12 items 78–90,
  verified at CLI level in item 89).
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
- **After slice F (2026-10-07, §12 item 89):** ADR-0052 §7's two properties were shown at CLI
  level, under the argv F builds:
  - a removed tool is never offered or called;
  - the MCP deny leaves an opted-in server usable and keeps the excluded ones out, even when
    loaded past `--strict-mcp-config`.

  Slice E's allow, deny, halt, timeout and crash answers still hold under the new argv. The
  observed execution through Core, for PV-19 and ADR-0052 §7 alike, is still NOT RUN and gated
  by ADR-0021.

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

**V2-3 resolved (the owner, 2026-10-15).** "Paired devices only (Recommended)": D10 stands as
approved, re-arm asks a PIN only from a paired client, and the V2 copy (SS-4's hint, SS-6) is to
say so per device rather than "resuming needs a PIN" everywhere. The copy change is the V2
work's; slice J (§12 items 121-123) built the P20 side.

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

*After slice F (2026-10-07):* F was authorised after F.0 and is built and verified (§12 items
75–91). G, H, I, J and K are not authorised and were not started. G's ADR-0051 §2 boundary tests
now have F's tool removal to test, and H's fuzzing has F's mapping to fuzz over. I is still free
of open decisions. H waits on D12 and D13; J waits on D10 and V2-3.

*After slice G started and was paused (2026-10-07):* G's verification pass found two Critical
OS-confinement findings (G1, G2; §12 items 92–97) and was **stopped before any implementation.**
ADR-0051 §2 is not satisfied as built: a Claude Code execution runs with the user's OS identity
and so keeps the user's reach into user-owned credential authorities (G1) and the local Core
control boundary (G2). These are OS-boundary issues, **not** P11 environment-hygiene defects.
The remediation is **PV-20**; its prerequisite **PV-13 study is delivered**
([pv13-windows-os-confinement-study.md](pv13-windows-os-confinement-study.md), 2026-10-07,
recommending AppContainer + a Job object with a separate-user escalation path), and PV-20's design
is prepared ([pv20-execution-isolation-design.md](pv20-execution-isolation-design.md)) as a design
decision, **not** an implementation authorization. *(Later the same day: PV-20's decisions were
recorded and approved in ADR-0053 — §12 item 98; implementation not started, verification not
performed.)* P23 owns the separate network-egress gap (G3).
G stays paused; H, I, J, K are not authorised. P20 cannot complete while the two Criticals are
open, and P20 defines no accepted-Critical state — per ADR-0051's superseding timing decision and
PV-20, G1 and G2 stay Critical and open (not waived or accepted), and OS confinement is a **V1.x
security remediation**.

