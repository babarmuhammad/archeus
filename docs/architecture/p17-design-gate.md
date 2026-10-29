# P17 design gate — the V1 TUI

Status: **APPROVED** (A1–A9, the user, 2026-09-29, with the clarifications recorded in §14.1).
Implementation follows §18. Anything that departs from an approved decision is recorded in §19
for the user's review, never applied silently.

Sources read, in precedence order: the plan (§23, §31.1 P16–P19, §31.2, §31.3, §33), this
repository at `c06fe14`, [ui-architecture.md](ui-architecture.md) §1, §3, §5, §5.1, §6, §7, §8,
[../design/ARCHEUS_V1_DESIGN_SYSTEM.md](../design/ARCHEUS_V1_DESIGN_SYSTEM.md) §1, §3, §7, §15,
§16, [../design/ARCHEUS_V1_DESIGN_RESEARCH.md](../design/ARCHEUS_V1_DESIGN_RESEARCH.md) §29 and
A.4, [p16-design-gate.md](p16-design-gate.md) (whole, esp. §3.3, §4.2, §6.4, §13, §14, §15,
§19, §20, §22, §30), [testing-strategy.md](testing-strategy.md) §1, §2 (G3),
[migration-plan.md](migration-plan.md) rows for `term.py`/`render.py`/`main.py` and §6,
[target-architecture.md](target-architecture.md) §2 (principles 7, 8) and §3,
[p11-design-gate.md](p11-design-gate.md) §6, §17, D9, §28, [p13-design-gate.md](p13-design-gate.md) D12,
[p15-design-gate.md](p15-design-gate.md) (Device, presence, local credentials).

---

## 0. What P17 is, and what it is not

The plan's entry (§31.1): **"P17 — TUI. Depends: P16 (shares nav table and presentation table).
New: `cli/tui/*`. Tests: scripted keys per screen; monochrome rendering; parity with nav table.
Acceptance: G3 (TUI part)."** §31.2 makes the full TUI a **V1 release** requirement (not a slice
requirement); the thin CLI already shipped.

P17 builds `archeus/cli/tui/`: a second *presentation* of the same backend, keyboard-first, on
the same API, the same stream, the same tables and the same rules as the P16 SPA.

**P17 owns** terminal presentation. **P17 does not own** authorization (P9), routing (P10),
execution (P11), sessions (P12), verification (P13), events/automation (P14), clients, pairing,
presence and access (P15), the information architecture (P16 — P17 consumes it), the spatial
graph and `/v1/world/graph` (P18), client unification and the generated client everywhere (P19).

The P16 rule carries over unchanged and decides every conflict here: **the TUI may only
*present* authoritative rows. It may never *decide*** — not whether something is allowed, where
it runs, whether it is done, or what state it is in.

## 1. What exists [V = verified at c06fe14]

### 1.1 P16 as delivered (the contracts P17 consumes)

P16 is complete: commits `544e4c6` (gate), `8b8cc93` (hidden console spawn), `661adb2`
(implementation), `c06fe14` (CI fixes). CI green on every job that runs on this branch
(`gui-smoke` and `mobile` are skipped by workflow conditions). Local: full suite 4,545 passed;
e2e + G3 GUI + design gates 33 passed; client units 38; `mutate_p16` 29/29; P8–P15 mutation
suites 215/215; wheel check passes and serves the SPA without Node; `mkdocs --strict` clean;
seam/boundary/traceability/packaging/parity tests 118 passed (run for this gate).

| P16 artifact | Form today | P17 use |
|---|---|---|
| IA: Now · Work · World · Attention · Control; Control sections; per-kind inspector tabs | `clients/app/src/nav/destinations.ts` — **hand-written TypeScript** (`DESTINATIONS`, `CONTROL_SECTIONS`, `INSPECTOR_TABS`, `TAB_LABEL`) | the same table; **not readable from Python** (A1) |
| presentation table (state → class/glyph/label, triggers per state) | `clients/app/tokens/presentation.json` (hand-written JSON) → `tools/gen_ui.py` → `state/presentation.ts` | the same JSON |
| tokens (hex, dark/light/high-contrast) | `clients/app/tokens/tokens.json` → `gen_ui.py` → CSS + TS | the same JSON; ANSI derivation is P17's (p16 §15.1) |
| invalidation table (subject kind → read paths) | `clients/app/src/data/invalidation.ts` — hand-written TS `RULES` | the same rules (A1) |
| connection machine, freshness per view | `src/data/connection.ts` (93 lines, logic) | same states and transitions (A2) |
| relation edges from authoritative fields | `src/graph/relations.ts` (115 lines, logic) | same edges (A2) |
| state explanation, `resourceLine` | `src/state/present.ts` (187 lines, logic) | same text (A2) |
| command keys, refusal wording | `src/data/commands.ts` (90 lines) | same behaviour (A2) |
| backend reads | `/v1/attention`, `/v1/missions/{id}/timeline`, `/v1/executions/{id}/stream` + every pre-existing read | used as-is; **no new route planned** (§6) |

**Packaging fact:** `clients/app/tokens/*.json` is **not** package-data; only the built SPA under
`archeus/api/static/` ships. An installed TUI therefore cannot read those JSON files at runtime —
the tables must be generated into Python modules inside `archeus/cli/tui/` (design system §16
already names `archeus/cli/tui/tokens.py` as a generated output).

### 1.2 The CLI and the Python side of the API [V]

- `archeus/cli/` is `__init__.py` + `main.py` (556 lines). `VERBS`: core, status, terms,
  approve (exits 2), pause, route, estop, pair, sessions, resume, handoff, verify, decide,
  automation, devices. `claude_sessions/cli.py:116-126` forwards these; **any other argv
  (including none) opens the legacy TUI**.
- Transport: `cli/main.py:_get` — stdlib `urllib`, bearer = `run/local-token`, **returns `None`
  on any error** (status, code and Core's reason are lost). Idempotency keys are generated per
  call. The CLI never opens the database.
- **No Python API client exists** outside tests (`tests/v1/judge/http.py:HttpClient`,
  `SSEClient`, `TempCore` are test-only). `tools/gen_api_docs.py` emits TS only.
- Local token = `LOCAL_SCOPES = SCOPES` (all four) (`api/auth.py:24-26`). `Device.client_type` ∈
  (`cli`, `spa`); `platform` already allows `tui` (`entities.py:205-206`).

### 1.3 Legacy terminal code (reuse candidates) [V]

| Module | What it is | Disposition for P17 |
|---|---|---|
| `claude_sessions/term.py` | the one platform key seam (msvcrt / termios, ESC timing, UTF-8), `BACKEND` swappable, `enable_vt()` | **REUSE AS-IS** (migration-plan row) |
| `claude_sessions/render.py` | pure width/trunc/pad/fit, `render_frame` diffing inside DECSET 2026 with a clear-and-print fallback, alt screen, line builders | **REUSE AS-IS** for the pure helpers and `render_frame`; line builders read legacy `config.C_*` colours, so V1 colour comes from the generated token module instead (§9) |
| `claude_sessions/themes.py:hex_to_x256` | hex → nearest non-system 256 colour (never 0–15) | **REUSE at build time** (the generator calls it; the TUI never imports `themes`) |
| `claude_sessions/ui.py` (1,682 lines), `session_menu.py`, `main.py`, `diffview.py` | legacy screens, widgets, prompts bound to legacy config | **NOT REUSED** (legacy TUI; retires at the migration-plan §6 gate). Patterns only: `wait_event`/`poll_event` with resize, `pager` |
| `tests/harness.py` | scripted scancodes through `term.BACKEND='windows'`, `CapturingStdout` (not a tty → clear-and-print path, `.plain`), `Sandbox` | **REUSE the pattern** in `tests/v1/tui/` (testing-strategy §1 names it) |

No `NO_COLOR` handling exists anywhere in the Python code today; the legacy fallback is 16-colour
+ reverse video when VT fails.

### 1.4 What P17 must turn green [V]

- `tests/v1/judge/test_g03_one_model.py:20` — `xfail(strict=True, reason="phase:P17")` on
  `test_the_tui_shows_the_mission_the_api_reports`: `rig.tui().mission_row(id)['state'] ==
  client.get_mission(id)['state']`, over both bindings.
- `tests/v1/judge/support.py:378` — `Rig.tui()` raises `_pending('the TUI driver','P17')`.
- `test_every_client_agrees` stays `phase:P19`.
- testing-strategy §1's **TUI layer** (`tests/v1/tui/`) does not exist yet.
- migration-plan §6: "TUI covers every destination with keyboard parity" (retirement gate item).

## 2. Scope

### 2.1 In scope

1. `archeus/cli/tui/`: app shell (top line, destination screens, status line, `?` help, `:`
   command line), one inspector per object kind with the P16 tab set, list screens with
   keyboard selection, commands with confirmation.
2. A stdlib Python API transport for the TUI (HTTP + SSE, errors carrying status/code/detail) —
   A3.
3. Generated Python tables (nav, presentation + triggers, invalidation, ANSI tokens) from the
   single sources — A1.
4. Terminal-specific rules: glyph probe + ASCII fallback, monochrome, widths, resize,
   escape-sequence sanitising of every server string (§10).
5. `tests/v1/tui/`, the G3 TUI driver, `tools/mutate_p17.py`, packaging (`archeus.cli.tui` in
   `packages`), an `archeus tui` verb (A4).

### 2.2 Explicit non-goals

- No new backend authority, route, event type, entity, migration or state (§6).
- No shadow policy, routing, execution, session, verification, presence or client system (§11).
- No porting of legacy TUI features (session launch/resume in Claude Code, hooks/agents/skills/
  MCP managers, memory screens, usage charts). Those are legacy capabilities; their V1 homes
  are decided by migration-plan §6 and P22, not by P17.
- No spatial graph, no ASCII node-link drawing, no `/v1/world/graph` (P18).
- No plan editor, per-mission threads, chat approve/reject verbs, `careful` confirmation, `/v1/now`,
  offline snapshot (S1–S6 of p16 §3.3 stay where p16 put them).
- No remote/paired TUI, no terminal QR (A5).
- No CLI rewrite: the existing verbs keep their behaviour; moving them onto the new transport is
  P19's "generated client everywhere" (A3).
- No retirement of the legacy TUI (`archeus` with no verb keeps opening it until P22).
- No motion (design system §15: "Motion: none").

## 3. Information architecture in the terminal

Same destinations, same order, same labels, same Control sections, same inspector tabs per kind
as the SPA — read from the one table, never restated (target-architecture principle 7).

| id | Label | TUI key | Notes |
|---|---|---|---|
| `now` | Now | `1` | digest groups (ack through `POST /v1/digest/ack`), active missions, attention summary |
| `work` | Work | `2` | missions grouped by what they wait on (the SPA's grouping, from row state only) — research A.4 layout |
| `world` | World | `3` | projects → repositories, knowledge |
| `control` | Control | `4` | sections: autonomy, automations, resources, sessions, devices ("Clients"), about |
| `attention` | Attention | `a` | approvals, blockers, acceptance, proposals (`/v1/attention`) |
| `command` | Command line | `:` | go to a destination/mission/project, or send text to the primary conversation (no client grammar) |

Top line (design system §15): `ARCHEUS ● 1 Now  2 Work  3 World  4 Control   ◆ 2 attention  HH:MM`
plus the connection/freshness word when not current. Global keys: `?` help (generated from the
key table), `q`/Ctrl+C quit (restores the terminal), `Esc` back / close inspector, `↑↓`/`j k`
move, `⏎` open, `[`/`]` a page up/down (`term.py` decodes no PgUp/PgDn). There is no manual
re-read key: the stream says what to read again, as in the SPA. **Keys never overlap by
construction**: destination keys (`1 2 3 4 a`) and the reserved `q ? :` are global; inspector
tab keys are lower-case letters unique within a kind (`gen_ui.py` refuses a clash); every
command is an **upper-case** letter shown on the hint bar (`[P] Pause  [R] Resume`), so a
command can never be pressed by the key of a tab or a destination.

**Inspector** = full-screen pager (design system §15), tabs from `INSPECTOR_TABS[kind]`. The
design system's key list `o p n e t w l` predates P16 as-built (it names a Thread tab P16 did not
build, D-deviation 10, and has no key for Relations). Proposal A6: keys are part of the generated
table — mission: `o` outcome, `p` plan, `n` now, `e` evidence, `w` why, `t` timeline, `r`
relations; other kinds get their tabs' initial letters, with a uniqueness test.

Deep links: `archeus tui --open <kind>/<id>` opens that inspector (the `/o/<kind>/<id>` idea);
a notification is out of scope.

## 4. Surfaces (what each screen reads, what it may send)

Every read is an existing route; every command is one existing Core command offered **only
where the presentation table's trigger list for the object's current state has it**, disabled
with the reason otherwise, and followed by a re-read (no optimistic state).

| Screen / tab | Reads | Commands (existing) |
|---|---|---|
| Now | `/v1/digest`, `/v1/missions?state=…`, `/v1/attention` | `digest/ack` |
| Work | `/v1/missions` | open; pause / resume / cancel with `expected_version` |
| World | `/v1/projects`, `/v1/projects/{id}`, `/v1/knowledge`, `/v1/knowledge/{id}` | knowledge confirm/retract/reject (as the SPA offers) |
| Attention | `/v1/attention`, `/v1/approvals/{id}` | `approvals/{id}/decide` echoing `action_hash`, confirmation in prose for irreversible actions |
| Mission inspector | `/v1/missions/{id}`, `/plan`, `/timeline`, `/verifications`, `/reviews`, `/why`, route/policy decisions | the mission's triggers |
| Execution inspector | `/v1/executions/{id}`, `/stream?from=` (redacted tail), `/checkpoints` | stop |
| Session (Control) | `/v1/sessions`, `/v1/sessions/{id}` (brief, lineage) | resume (model, effort — harness vocabulary), hand-off (target **harness** required; account/model/effort optional, separate fields) |
| Resources (Control) | `/v1/harnesses`, `/v1/accounts` | mission resource preferences (`POST /v1/missions/{id}/resources`: preferred/forbidden harnesses and accounts as separate lists, `max_cost_band`) |
| Automations (Control) | `/v1/automations`, `/runs`, `/v1/automation-runs/{id}` (causal chain) | enable/disable/run-now as the SPA offers |
| Clients (Control) | `/v1/devices` (with presence) | revoke (confirm); pairing start stays `archeus pair` (the code is printed as text; no QR — A5) |
| About | `/v1/version`, `/v1/health` | — |

The exact per-screen command set is **the SPA's as built** (P16 §6, §30): the TUI mirrors it and
adds none. Where the SPA offers a control the TUI cannot present well (the QR), the TUI names the
alternative instead of inventing one.

## 5. Graph capability in the TUI (ui-architecture §5.1, p16 §20)

The P16 inventory (§20.1, 35 capabilities) stands; **nothing in it is assigned to P17** and P17
changes no disposition. The graph requirement is met in the terminal by the **list equivalent**
of the relationship views, which P18's acceptance also requires to exist ("list equivalent"):

| Capability (p16 id) | TUI presentation | Source |
|---|---|---|
| Relations tab (G9 ADAPT, G22–G31 ADOPT) | a list grouped by relationship; each row: target kind letter (design system §7: `M P R D @ N K I A $`), name/id, the tier **word** (EXTRACTED / INFERRED / AMBIGUOUS — style alone is impossible in monochrome), "no longer current" for inactive, and the source field | the same edge mapping as `relations.ts` (A2), authoritative fields only |
| plan DAG + waves (G25), plan lineage (G26) | waves as numbered groups, each task with its `depends_on` ids; versions with `supersedes` | `/v1/plans/{id}`, `/v1/missions/{id}/plan` |
| automation causal chain (G27, G28) | an indented, top-to-bottom chain: event (with `cause_chain`) → automation → run → why → mission → plans/decisions/approvals/routes/executions/verifications/reviews | `/v1/automation-runs/{id}` |
| session hand-off lineage (G29, G30) | lineage list with each session's **harness** named | `/v1/sessions/{id}` |
| verification lineage (G31), drift (G33), digest (G34), context references (G35) | lists in their tabs | existing reads |
| spatial graph (G4 ADAPT → P18), `/v1/world/graph` (S8, G32) | **none** in P17 | P18 |
| legacy graph-lite (G11), `top_repos` (G2), legacy `/graph` (G5) | unchanged, legacy only (PRESERVE-BEHIND-UI) | legacy |

**Rejected for the TUI:** box-drawing node-link diagrams. They do not survive a screen reader or a
narrow terminal, and scale to a handful of nodes; the list carries every fact the diagram would.
Archeus is not presented as "everything is a graph": relationships appear where a row has an
authoritative edge, and nowhere else.

## 6. Backend surface

**Used as-is**: every route in §4, `GET /v1/events/stream` (SSE, `?project=`/`?type=`),
`GET /v1/events?after=` catch-up, `GET /v1/sync` anchor, `X-Archeus-Seq` (P15 §13).

**Built by P17: nothing.** If implementation finds a fact the TUI needs that no read exposes,
the rule is P16 §3.3's: name the missing seam in this gate and stop, never reconstruct it from
unrelated data. Known candidate, not proposed: none.

**Identity (A5):** the TUI authenticates with the local device token (`run/local-token`,
all four scopes, local origin) exactly as the CLI does; it registers no new client and adds no
`client_type`. Its SSE stream therefore shows as the local device's presence (P15 presence is
per credential). Core still judges every command (scope, step-up, policy).

## 7. Realtime, freshness and reconnect

Identical semantics to p16 §13–§14, one implementation of the rules (A1/A2):

- one SSE stream per TUI process; frames carry identities only and **only invalidate** cached
  reads by the shared `RULES`; a frame never changes what is on screen by itself;
- one connection machine (`current · stale · reconnecting · unavailable`), shown on the top line
  as a word, never colour alone;
- reconnect: `Last-Event-ID` replay; a `410`/cursor-expired or a restarted Core → `/v1/sync`
  anchor → re-read everything visible ("Back — read again" in the status line);
- Core not running at start: one screen saying so and naming `archeus core`; the TUI never
  starts Core itself (that is `archeus core --open`'s job) — flagged, see A4;
- re-queries are coalesced per render tick; no per-row requests.

## 8. Commands

- One idempotency key per **user action**, reused on retry (as `commands.ts`);
- `expected_version` wherever Core takes it; a stale version shows Core's refusal verbatim and
  re-reads;
- irreversible actions (cancel, reject, revoke, e-stop if offered) ask in prose and require a typed
  `y`; the default is no;
- no optimistic state: after a command the screen shows the result of the re-read only;
- refusals: Core's `code` and `detail` verbatim, with the P16 explanation wording (A2).

## 9. Visual system in the terminal (design system §15, §16)

- **Glyphs**: the glyphs of `presentation.json`'s 13 classes (11 distinct: `◌ ○ ◆ ◇ ● ■ ‖ ✕ ✓ · –`;
  active, verifying and reviewing share `●` and are told apart by label, as in the SPA). A
  startup probe (can the output encoding encode them; `ARCHEUS_TUI_ASCII=1` forces it) selects
  ASCII: the design system's `* ! # = ~ + x` for active, needs-you, blocked, paused, planning, done,
  failed, plus ASCII for proposed, approved, neutral and inactive, added to `presentation.json`
  so the mapping has one home. Glyph → ASCII must stay injective (tested).
- **Colour**: generated `archeus/cli/tui/tokens.py` holds SGR strings per role per theme, derived
  at build time with `themes.hex_to_x256` (never 0–15). Theme (A7): dark by default; `light` by
  setting/env; **monochrome** when `NO_COLOR` is set (any value), `TERM=dumb`, stdout is not a
  tty, or VT cannot be enabled. Monochrome loses nothing: every state is glyph + label, focus is a
  `›`/`>` marker plus bold, never reverse video alone.
- **Authority** (p16 §15.4): Core-computed values plain; client-derived text (relative times,
  status line) never styled as data; model-produced text carries its provenance line
  ("from the planner · route rd_…"); stale shows the word "stale"/"as of …".
- **Density**: dense rows (research A.4); minimum 80 columns designed, 60 degraded (columns drop
  in a fixed order), resize re-renders; no line exceeds the width (`render.disp_width`, wide
  characters counted).
- **Motion**: none. Status-line messages last 4 s (design system §15); nothing blinks or spins.

## 10. Security (TUI-specific)

1. **Terminal escape injection.** Every string that came from Core — mission titles, model-written
   summaries, knowledge text, file names, branch names, harness output tail, refusal detail — is
   stripped of C0/C1 control characters (except none; `\t` expanded, newlines only where the
   layout splits lines) and of ESC/CSI/OSC/DCS sequences **before** layout. Otherwise a string can
   set the terminal title, write the clipboard (OSC 52), hide text, or forge Archeus's own
   prompts. One function, used by the one row/line builder; a static test forbids writing
   response text any other way.
2. **The token** is read from `run/local-token` per request path (as the CLI), never printed,
   logged, put in an error, an argv, an environment or the screen; a mutation prints it.
3. **Loopback only**: the TUI connects only to the address `discovery.discover()` returns for
   `127.0.0.1` with the recorded port and sends the token nowhere else (no `--host`).
4. **Redaction** is Core's (`core/redact.py` via `/stream`); the TUI never reads execution files
   or anything under `ARCHEUS_HOME` except the token and `run/core.json` (static test).
5. **Confirmation** for irreversible actions (§8) and the exact `action_hash` echo for approvals.
6. **Scope/step-up refusals** are shown, never worked around (no retry with another token).
7. Terminal restore on every exit path (exception, Ctrl+C, SIGTERM on POSIX) so a crash cannot
   leave the user's terminal in raw/no-echo mode.

## 11. Boundaries — the TUI holds no shadow system

| Temptation | What the TUI does instead | Test |
|---|---|---|
| decide if an action is allowed (P9) | trigger table + Core's refusal | static: no policy terms/evaluation under `archeus/cli/tui/` |
| pick or order resources (P10) | shows RouteDecision: selected harness · account · model · effort, result, `fallback_from`, candidates with eliminating step and reason, Core's explanation — **never model reasoning** | `resource_line` three-field test; no sort of candidates |
| infer execution state (P11) | renders Execution rows; `ENDED_OK` is never ✓ | presentation mutation |
| build a session from a connection (P12) / a client from presence (P15) | connection state touches neither | mutation |
| infer verification (P13) | "Done" only for COMPLETED | mutation |
| treat an event payload as state (P14) | frames only invalidate | stream test reads `type`/`subject` only |
| optimistic state | re-read after every command | scripted test counts GETs |
| client grammar | `:` text goes to the primary conversation unparsed; only "go to" matching is local | static: no verb table |
| import Core | HTTP only; imports allowed: stdlib, `archeus.cli.tui.*`, `archeus.infra.discovery`, `claude_sessions.term`, `claude_sessions.render` | AST import test |

## 12. Tests

| Layer | Where | What |
|---|---|---|
| TUI screens | `tests/v1/tui/` (new) | scripted keys through `term.BACKEND` against `TempCore` (HTTP binding): every destination by its key, every inspector tab per kind, help, command line, resize, quit restores |
| parity | `tests/v1/tui/test_parity.py` | generated nav table ↔ TUI screens ↔ SPA (both read one source); inspector tabs per kind; key uniqueness |
| rendering | `tests/v1/tui/test_render.py` | monochrome (no SGR colour under `NO_COLOR`/non-tty), ASCII fallback injective, widths 60/80/120/200 with wide chars, sanitiser |
| shared logic | golden fixtures (A2) | the same JSON cases run by `node --test` and pytest: edges, explanations, `resource_line`, connection transitions, invalidation matches |
| transport | `tests/v1/tui/test_client.py` | errors keep status/code/detail; idempotency key reused on retry; SSE reconnect + `410` resync |
| generators | `tools/gen_ui.py --check` | Python outputs current, like the TS ones |
| judge | `test_g03_one_model.py` | the P17 function passes over both bindings (`rig.tui()` = `TuiDriver`: runs the TUI in-process under the scripted backend, opens Work, reads the mission's row); `phase:P17` marker removed |
| boundaries | `tests/v1/unit/` | import allowlist, no DB, no file reads beyond discovery, no policy/verb tables |
| packaging | `tests/test_packaging.py`, `tools/check_wheel.py` | `archeus.cli.tui` listed; generated modules in the wheel; `archeus tui --help` from the installed wheel |
| legacy | `tests/test_tui_*.py` (12 files) | unchanged and green |

### 12.1 Acceptance scenarios (T-series)

- **T01** G3 TUI: the state the TUI shows for a mission equals the API's, in every state the fake
  Core can reach (the judge's mission).
- **T02** keyboard parity: every destination and Control section reachable by its key; every
  inspector tab by its key; `?` lists exactly the key table.
- **T03** approve a plan from Attention: confirmation in prose, `action_hash` echoed, one key per
  action (a retry reuses it), state shown only after the re-read.
- **T04** pause → resume with `expected_version`; a stale version shows Core's refusal and re-reads.
- **T05** Why on a mission: route decision as three fields + result + candidates + Core's text; no
  reasoning field is read or printed (static + render).
- **T06** execution output tail: redacted by Core, resumed from the byte offset, escape sequences
  in the tail neutralised.
- **T07** Core restarts under the TUI: reconnecting → resync → current; nothing stale is shown as
  current.
- **T08** Core not running: one explanatory screen, exit code non-zero on `--once`.
- **T09** monochrome and ASCII: the Work screen of every state is distinguishable with no colour and
  no Unicode.
- **T10** widths 60/80/120/200 and a live resize: no line over width, no lost state label.
- **T11** command line: go-to a mission by title; free text is posted to the primary conversation
  unparsed.
- **T12** automation run inspector renders the causal chain top to bottom.
- **T13** session hand-off: target harness required, account/model/effort separate optional fields.
- **T14** a restricted token (observe only, injected by the test): every command is offered and shown
  **disabled with the reason from Core's own `/v1/sync` row** ("This client does not hold the
  “control” scope."), exactly as the SPA's `ActionButton` does; nothing is hidden and nothing is
  guessed. Core's refusal of a command that is sent (version conflict, invalid transition) is
  shown verbatim (T04). See §19 R2.
- **T15** 1,000 missions: first render within budget, only visible rows built, one GET per list.

### 12.2 Mutation suite `tools/mutate_p17.py` (every mutation must be killed)

M01 sanitiser bypassed for a title · M02 `NO_COLOR` ignored · M03 two ASCII glyphs collide ·
M04 a destination dropped from the TUI screen map · M05 `ENDED_OK` rendered ✓ · M06 route
candidates sorted client-side · M07 `resource_line` merges model into harness · M08 a frame
payload rendered as state · M09 optimistic "approved" before the re-read · M10 idempotency key
regenerated on retry · M11 invalidation rule for `approval` dropped · M12 token printed in an
error · M13 a non-loopback host accepted · M14 irreversible action without confirmation · M15 a
command offered where the state has no trigger · M16 generated Python table stale · M17 an
inspector tab missing for a kind · M18 reconnect without resync after `410` · M19 unknown subject
kind makes everything stale (rule: nothing) · M20 width truncation removed · M21 G3 row state
derived by the client · M22 `archeus.core` imported · M23 a file under `ARCHEUS_HOME/` read ·
M24 relation tier word dropped · M25 a verb parsed in the command line · M26 presence treated as
a session · M27 all rows of a long list rendered · M28 terminal left raw after an exception.

### 12.3 Regression obligations

Full suite green (with a **short** `--basetemp`: a long one breaks `git worktree add`, see §15);
legacy TUI tests unchanged; after A1's table relocation the SPA builds, `npm test`, e2e + G3 GUI,
design gates and `mutate_p16` stay green (its anchors that read `destinations.ts` as text move to
the source table); P8–P16 mutation suites re-run; CLI verbs unchanged; wheel check; CI green.

## 13. Packaging, API, CLI, migration

- **Packaging:** add `archeus.cli.tui` to `pyproject` `packages` (does not recurse;
  `test_packaging` enforces). Generated modules are committed (like `generated.ts`) and checked
  by `gen_ui.py --check`. No runtime dependency (stdlib only, as the rest of `archeus`).
- **CLI:** new verb `archeus tui [--open kind/id] [--once]` (A4); `claude_sessions/cli.py`'s
  forwarding list gains `tui`. `archeus` with no argument keeps opening the legacy TUI until P22.
- **API:** no new route, schema or scope; `docs/architecture/api-reference.md` unchanged.
- **Migration:** none (no schema, no state, no event type).
- **Docs:** ui-architecture §6 as-built, design system §15 key list (A6), testing-strategy G3 row,
  plan P17 as-built entry. User docs for the V1 TUI are P25.
- **CI:** no workflow change expected — `tests/v1/tui/` and the G3 file run in the existing test
  job on Windows, macOS and Linux. If a change turns out to be needed it is asked for first.

## 14. Decisions requiring approval

| # | Decision | Proposal | Alternatives |
|---|---|---|---|
| **A1** | Where the shared client tables live | Move nav (`DESTINATIONS`, `CONTROL_SECTIONS`, `INSPECTOR_TABS`, `TAB_LABEL`, + a `tui_key` column) and invalidation `RULES` into JSON next to `tokens.json`/`presentation.json`; `gen_ui.py` emits the TS the SPA already imports **and** Python modules in `archeus/cli/tui/_tables.py`. SPA behaviour unchanged. | (b) TUI hand-writes Python copies, a parity test reads the TS as text — two declarations, violates principle 7. |
| **A2** | Pure presentation *logic* (edges, explanations, `resource_line`, connection machine, refusal wording) | Thin Python implementations, **gated by shared golden fixtures** (one JSON case file per function, run by `node --test` and pytest) so the two cannot disagree silently. | (b) rewrite the TS as interpreters of declarative specs generated for both (purer, larger P16 rewrite); (c) have Core return presentation (moves presentation into the API — rejected). |
| **A3** | Python API transport | New stdlib module `archeus/cli/tui/client.py` (HTTP with status/code/detail errors, SSE with `Last-Event-ID`, idempotency helper). Used by the TUI only; the CLI keeps `_get` until P19. | (b) generate a typed Python client from `routes.py` now (P19's "generated client everywhere"); (c) promote the test `HttpClient` into the package. |
| **A4** | Entry point | `archeus tui`; the TUI never starts Core (shows how to). | (b) bare `archeus` opens V1 TUI now (breaks legacy users before P22); (c) TUI starts Core if absent. |
| **A5** | Identity and reach | Local token only (as the CLI); no new `client_type`; no remote/paired TUI, no terminal QR in P17. | (b) register the TUI as its own client (`client_type='tui'`, a P15 entity change); (c) paired TUI over a tunnel (needs a non-browser pairing redeem). |
| **A6** | Inspector keys | Generated per tab from the table; mission `o p n e w t r`; update design system §15 (no Thread tab exists). | keep §15's `o p n e t w l` and add a Relations key. |
| **A7** | Theme selection | dark default; `light` via setting/env; mono on `NO_COLOR`/`TERM=dumb`/non-tty/no VT; `ARCHEUS_TUI_ASCII=1` forces ASCII glyphs. | detect background via `COLORFGBG`/OSC 11 query (unreliable on Windows). |
| **A8** | The worktree retry defect (§15) | Record it as a **P11 as-built defect** now; fix in its own commit, separate from P17, after approval of the D9 part. | leave for P20 breaker drills. |
| **A9** | Surface scope | Every P16 surface and command the SPA offers, minus the QR (text code instead) and motion. | a reduced TUI (Now/Work/Attention/inspector only), rest in P19 — would fail migration-plan §6's "every destination with keyboard parity". |

### 14.1 Approval (2026-09-29) — the clarifications that bind implementation

A1–A9 approved as proposed. The user's clarifications, binding:

- **A1**: one navigation authority; the known key/documentation mismatch (ui-architecture §3's
  TUI keys vs the SPA table's shortcuts) is fixed deliberately, as a column, not by accident; the
  Thread-tab correction is explicit (P16 never built that tab).
- **A2**: thin, deterministic Python implementations; shared fixtures for parity; **no
  cross-language framework or extra abstraction layer**.
- **A3**: preserve Core's status, code and reason; the CLI helper is untouched until P19; the TUI
  invents no API semantics.
- **A4/A5**: `archeus tui`; bare `archeus` stays legacy until P22; the TUI never starts Core;
  local token only; consume P15's reconnect/resync and presence contracts; no parallel session,
  presence, authentication, routing, policy, execution or verification system.
- **A7**: widths 60–200 and resize tested; keyboard navigation works without colour.
- **Graph**: inspect the existing capabilities before building any relationship view; keep every
  P16 disposition unless a documented reason changes it; Core-supplied edges only; no graph
  database, authority, inference engine or second graph model; keep provenance, event causality,
  task/mission relationships, automation cause chains, session hand-off lineage and model ×
  harness selection distinct; tiers as words.
- **Model × harness**: *P10 decides → Core records → the TUI presents.* The TUI may display
  selected harness, account, model, effort, the relevant requirements Core recorded, fallback,
  eliminated candidates, the stored explanation and the resulting usage/outcome; it never
  chooses, ranks or infers a routing decision, and never shows reasoning.
- **Security**: sanitising covers at least titles, model text, file names, output tails, routing
  explanations, graph/relationship labels and error/refusal messages, with tests and mutations.
- **Mutations**: each of M01–M28 is tied to a test that targets its invariant directly, not to an
  unrelated safeguard that happens to fail.
- **A8**: the P11 fix is a separate commit before P17; changing uncharged-retry semantics is a
  P11 contract change with docs, regression and mutation coverage; no unrelated P11 refactor.

## 15. Known defect found during P16 validation (not P17's) — for A8

**Symptom:** a task whose worktree creation fails after git created the branch is retried
forever (395 attempts in one run): the first failure was `fatal: '$GIT_DIR' too big` (a long
`--basetemp` path), every later one `fatal: a branch named 'archeus/<mission>.t1' already exists;
not charged (binding)`.

**Owner: P11** (with P13's base branch). Evidence:

- `archeus/node/local.py:245-257` `add_worktree` checks only `isdir(path)` and always runs
  `git worktree add -b`; its sibling `mission_worktree` (`:336-346`) already handles an existing
  branch by omitting `-b`. Worktree creation is p11-design-gate §17; the base is P13 D12.
- `archeus/core/execution/manager.py:175-178` refuses the execution with `stop_reason='binding'`,
  which is in `UNCHARGED` (`application/executions.py:37-39`); `_respond` (`:320-323`) fires
  `execution_failed_retry` with no counter, cap or backoff. Charging rules are p11 D9; §28 note 7
  already added charging for two other "would retry forever" cases, and note 5 foresaw
  "`worktree add -b` would then fail on the branch left behind".
- No test covers a failed `worktree add`; no gate or plan entry lists it.

**Fixed** in its own commit before P17 (`10667ed`, p11-design-gate §28 note 11), as approved in A8
and with the refinement recorded in §19 R1: an existing task branch that holds nothing its base
lacks is recreated at the base, one with unmerged commits is refused and never moved, and a
workspace that cannot be made is the new, charged `stop_reason='workspace'`. Mutations X33–X36.

## 16. Ship Notes (R7) and the P16 requirements, for a terminal

R7 was inspected by P16 (c1b70d0, MIT, patterns only, no code — p16 §22); P17 inspects nothing new.

| R7 pattern family | P17 decision | Reason |
|---|---|---|
| entry/exit, hover/press, expand/collapse, list and navigation transitions, springs, decorative motion | **REJECT** (not applicable) | design system §15: the TUI has no motion |
| status/loading transitions reporting real state | **ADAPT** as text: the state word changes on the re-read; a 4 s status-line message; no spinner | motion only reports change; here change is reported by text |
| reduced-motion handling | **REFERENCE-ONLY** | nothing moves, so there is nothing to reduce |
| component patterns (pull-lamp, orbs) | **REJECT** | decorative, not state |

The other P16 requirements carried into the terminal: IA first (§3), visual system second (§9),
motion last (none); backend truth only (§11); provenance, causality and selection as text (§5,
§11); no reasoning exposed (§11, T05); accessibility by glyph + label, keyboard-only by
construction, linear output a screen reader can follow, monochrome safe; "responsive" = widths
and resize (§9, T10); performance = windowed lists, coalesced re-reads (T15).

## 17. Risks and unresolved issues

1. **A1 touches P16 files.** Mitigation: generated TS keeps the exact exports; all P16 gates re-run;
   `mutate_p16` anchors move with the source.
2. **A2 keeps two implementations** of ~480 lines of pure logic. Mitigation: golden fixtures;
   upgrade path (b) if drift appears.
3. **Windows console**: VT and UTF-8 output on older consoles (`term.enable_vt()` handles VT; the
   output encoding decides the glyph probe). CI covers Windows/macOS/Linux, but not a real console
   — manual check on Windows Terminal and conhost before as-built.
4. **Screen readers in terminals** are uneven; P17 guarantees linear, glyph+label output, not a
   specific reader's behaviour.
5. **Step-up for local origin**: how the SPA handles a `step_up_required` refusal for a local
   credential must be read before the TUI's wording is fixed (the TUI shows the refusal; it has
   no PIN pad).
6. **Presence**: TUI + CLI share the local credential, so presence cannot tell them apart (A5).
7. **Long `--basetemp` paths** break the verification tests locally (the §15 trigger); use a short
   basetemp for full runs.

## 18. Implementation order and commit structure (after approval)

1. *(A8, separate, before or beside P17)* `P11 as-built: reuse an existing task branch; bound
   repeated uncharged spawn refusals` — tests first, mutation-checked; p11 gate note.
2. `docs: P17 design gate` — this file with the approved decisions.
3. `P17: generate the shared client tables for the SPA and the TUI` (A1) — no behaviour change;
   all P16 gates green.
4. `P17: the TUI transport, stream and connection machine` (A2/A3) with golden fixtures.
5. `P17: the TUI` — shell, screens, inspector, commands, sanitiser, `archeus tui`, packaging.
6. `P17: TUI tests, G3 TUI driver and mutation suite` (may fold into 5 if smaller).
7. `docs: P17 as built` — gate §As built, plan entry, ui-architecture §6, design system §15,
   testing-strategy G3.

Push only after local validation and the user's confirmation; watch CI.

## 19. Deviations and new decisions for the user's review

Recorded as they arise; none is applied silently.

| # | Where | What was approved | What was done, and why | Status |
|---|---|---|---|---|
| **R1** | A8 (P11) | "reuse an existing branch"; "bound repeated uncharged spawn refusals" | (a) The branch is reused only when it holds nothing its base lacks, and is then **recreated at the base** (`worktree add -B`); a branch with commits its base does not have is refused, never moved. Reason: a second trigger was found — P13 keeps a task branch after its merge (p13 §12.1) and every plan version numbers its tasks from `t1`, so a replan meets the old branch; plain reuse would start the new task from the old tip, not from the mission branch P13 D12 requires. (b) Instead of a generic cap on all uncharged ends, a workspace failure gets its own `stop_reason='workspace'`, which is **charged** (bounded by `max_attempts`), the same shape as p11 §28 note 7's two rules. A generic cap would also have changed hand-off, e-stop, cancel and stale-binding semantics (P12/P9 contracts) — the "no unrelated P11 refactor" clarification. Other uncharged `binding` refusals (provider terms, "the process did not start") are unchanged. | for review |
| **R2** | T14 | "every command is refused by Core … the TUI does not hide the buttons on its own guess" | Commands are offered and shown **disabled with Core's scope reason** from `/v1/sync` (the client row Core returns), which is what the SPA's `ActionButton` does; sending a command Core has already said this client may not send would only turn a stated reason into a refusal. Nothing is hidden, and the reason is Core's, not a guess. | for review |
| **R3** | §1.2 / the report of 2026-09-28 | "the TUI keys already differ from ui-architecture §3 (`j`/`,` vs `a`/`4`)" | A correction, not a change: the SPA table's `key` is the **Ctrl/⌘ shortcut**, and ui-architecture §3's shortcut column (Ctrl+J, Ctrl+,) matches it. What was missing is the TUI column (`a`, `4`), now `tui` in `navigation.json`. | recorded |
| **R4** | §3 | `PgUp/PgDn`, `r` re-read | `[`/`]` page (the key seam decodes no PgUp/PgDn); no `r` re-read (it would clash with the Relations tab, and the stream already drives re-reads); commands are upper-case letters. | recorded |
| **R5** | §8, T03 | the SPA's command set, as the SPA offers it | The TUI asks for a typed `y` before **approve and reject**, which the SPA sends on one click. The gate required a prose confirmation on every decision (T03, M14), and in a terminal a single mistyped upper-case key is easier to hit than a button. The confirmation quotes Core's own `consequences` for that decision when the approval carries them (a fixed sentence otherwise); any key but `y` cancels and sends nothing. | for review |
| **R6** | A7 | "`light` via setting/env" | `--light` or `ARCHEUS_TUI_THEME=light`. V1 clients have no settings store (the SPA's appearance is per browser), so a "setting" would have been a TUI-only file under `ARCHEUS_HOME`, which §11 forbids the TUI to read. | for review |
| **R7** | §12, T01 | `TuiDriver` reads the mission's row and G3 compares it with the API's | The G3 TUI function compares only when **two API reads either side of the TUI read agree**. The TUI reads fast enough to catch the fake harness's mission between two states (one run read REASONING while the API, a moment later, read EXECUTING); bracketing keeps the comparison exact without slowing the mission or loosening what "equal" means. | for review |

## 20. As built

Everything in §1–§18 is built as written, except the deviations recorded in §19 (R1–R7) and the
notes below. Commits: `10667ed` (A8, P11), `f0e701e` (this gate), `2607cc9` (A1), `042611d`
(A2/A3), `1bfbd5d` (the TUI), `e9489dc` (fixes its tests found), `bd59b4b` (tests, G3 driver,
mutations), and this as-built commit.

**Backend: none.** No route, schema, scope, migration, state or event type. The route table and
`api-reference.md` are unchanged (`gen_api_docs.py --check` clean). The only Core-side change of
the phase is A8's P11 fix, in its own commit (§15, R1).

**Shared tables (A1).** `clients/app/tokens/navigation.json` (destinations, Control sections,
inspector tabs per kind, tab labels, with a `key` column for the SPA's Ctrl/⌘ shortcut and a `tui`
column) and `clients/app/tokens/invalidation.json` (the frame → read-path rules) join
`tokens.json` and `presentation.json` (which gains the ASCII glyph of every presentation class).
`tools/gen_ui.py` emits `clients/app/src/nav/table.ts` and `src/data/rules.ts`, which
`destinations.ts` and `invalidation.ts` now import with their exports unchanged, and
`archeus/cli/tui/_tables.py` + `tokens.py` for the TUI; `--check` covers both languages. The SPA
build is unchanged in size (360 KB JS, 109 KB gzip; 16 KB CSS).

**Shared logic (A2).** `archeus/cli/tui/present.py` (states, badges, `resource_line`,
explanations, edges) and `sync.py` (connection transitions and freshness, idempotency keys,
refusal wording, invalidation matching) are thin Python twins of the SPA's `present.ts`,
`relations.ts`, `connection.ts`, `commands.ts` and `invalidation.ts`, with no framework between
them:
`clients/app/test/fixtures/parity.json` (generated by `parity-inputs.mjs` from the TypeScript) is
run by `node --test` (`parity.test.ts`) and by pytest (`tests/v1/tui/test_parity.py`, 118 cases).

**Transport (A3).** `archeus/cli/tui/client.py`: stdlib HTTP whose errors keep Core's status,
code and detail; the stream thread, which reconnects with `Last-Event-ID` and turns a `410` into a resync; the
per-action idempotency key reused on a retry. The CLI's `_get` is untouched (P19).

**The TUI.** `archeus/cli/tui/{app,screens,view}.py`: `archeus tui [--open KIND/ID] [--once]
[--light]` (A4) — every P16 destination, Control section and inspector tab by its generated key,
the command line (`:` go-to by title; any other text goes to the primary conversation
unparsed), help generated from the key table, windowed lists, upper-case command keys with the
disabled reason from Core's `/v1/sync` row (R2), confirmations in prose (R5). `view.py` holds the
one sanitiser every Core string passes before layout (every 7- and 8-bit escape sequence,
C0/C1 controls, DEL, line breaks, bidirectional overrides), the one styler (dark / light / monochrome on `NO_COLOR`,
`TERM=dumb`, a non-tty or no VT; ASCII glyphs when the output encoding cannot carry the symbols
or `ARCHEUS_TUI_ASCII=1`) and width fitting. Packaging: `archeus.cli.tui` in `pyproject`
`packages`; `tui` in both verb lists (`archeus/cli/main.py`, `claude_sessions/cli.py`).

**Tests.**

| Layer | File | Count |
|---|---|---|
| acceptance T02–T15 | `tests/v1/tui/test_acceptance.py` | 29 |
| T07 through the whole TUI | `tests/v1/tui/test_restart.py` | 1 |
| terminal injection (§10) | `tests/v1/tui/test_security.py` — titles, model text, file names, output tails, routing explanations, relationship labels, refusal messages, on every screen and inspector tab | 19 |
| boundaries (§11) | `tests/v1/tui/test_boundaries.py` — import allowlist, no `ARCHEUS_HOME` read, no verb table | 7 |
| transport | `tests/v1/tui/test_client.py` (against a real `TempCore`) | 10 |
| parity (A2) | `tests/v1/tui/test_parity.py` + `clients/app/test/parity.test.ts` | 118 + 2 |
| judge | `test_g03_one_model.py::test_the_tui_shows_the_mission_the_api_reports` (`rig.tui()` = `TuiDriver`, which reads the Work row from the rendered frame; P17 marker removed). HTTP binding only — §12 said "both bindings", but the in-process binding has no server for a client to open, the same as the GUI function | 1 |
| changed | `tests/v1/e2e/test_spa_p16.py` (reads the generated table), `tests/v1/judge/support.py` (`TuiDriver`) | — |

`tools/mutate_p17.py`: **28/28 killed** (M01–M28 of §12.2, each guarded by the test named for its
invariant; M16 and M28's anchors are the generated files). `mutate_p11.py` gained X33–X36 for A8:
36/36.

**Regression (§12.3).** Full suite at `bd59b4b`: 4,737 passed, 0 failed (short `--basetemp`).
P8–P16 mutation suites re-run: all killed. On the final tree: `gen_ui.py --check`,
`gen_api_docs.py --check` and Ruff clean; `vite build` and `tsc` clean; `npm test` 40/40;
e2e + G3 with `ARCHEUS_E2E=1`: 19 passed, 3 skipped (the GUI and TUI functions over the in-process binding), 1 xfailed (`test_every_client_agrees`, P19); mkdocs `--strict` clean; the wheel built, installed in a clean venv and read back: `check_wheel.py` passes (the SPA served with Node off PATH), `archeus.cli.tui._tables` imports from site-packages, the installed `archeus tui --help` prints its usage and `archeus tui --once` with no Core prints the T08 screen and exits 1; `tests/v1/tui/` 184/184.

**Notes (not deviations).**

1. Without VT (or with `--once`) frames are written as plain lines, never through
   `render.render_frame`, whose legacy fallback clears an old console with a subprocess.
2. `archeus tui --once` waits for the stream's first frame before it renders, so a one-shot frame
   is never "reconnecting" merely for having been fast.
3. A key the decoder does not map returns `None` and is ignored (found by the scripted tests).

**Known and not fixed.**

1. `python -m claude_sessions tui` does not reach the V1 verbs; only the `archeus` console script
   does. True of every V1 verb since P3.5, not introduced here.
2. `test_spa_p16.py::test_keyboard_only_navigation` failed once under full-suite load (31 ms over
   its deadline) and passed 12/12 alone: a timing margin, recorded rather than widened.
3. Presence cannot tell the TUI from the CLI: they share the local credential (A5, §17 risk 6).
4. The top-level `archeus --help` (`claude_sessions/cli.py`) still lists only `core` and `status`
   under V1: every V1 verb added since is missing there, `tui` included. `archeus/cli/main.py`'s
   usage and `archeus tui --help` list it. For P25's user docs or P22's switch.
5. §17 risk 3 — a manual look on Windows Terminal and conhost — is the user's; CI covers the
   three platforms but not a real console.

**DESIGN_GATE = IMPLEMENTED** (R1, R2, R5, R6 and R7 await the user's review).
