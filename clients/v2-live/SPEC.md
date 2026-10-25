# V2 Live: feature inventory (source of truth for slices 2 to 6)

Written 2026-10-25, slice 1. Everything the owner has decided, designed, built in V1 or shown in the old prototype, with where it comes from and where V2 Live shows it.

**Status words** (the Status column):

| Word | Meaning |
|---|---|
| BUILT | exists in V1 code (`clients/app`, `archeus/`) on the V1 integration branch, as far as the cited source says |
| DESIGNED | decided or specified in a document, no code anywhere |
| PROTOTYPED | exists in `clients/v2-prototype` (fixtures and fake data) |
| SIMULATED | shown in V2 Live from the simulation (`sim.js`); never a Core |

A row can carry two words (for example `BUILT + SIMULATED`): built in V1 and simulated here. Rows marked `S1` are shown by slice 1; `S2` to `S6` are what later slices must add.

**Screens and devices** (the "Where" column): Screens `NOW`, `WORK`, `ATT` (Attention), `MAP`, `REP` (Replay), `CHAT`, `SET` (Settings), `TERM` (terminal view), `ALL` (every screen), `SHELL` (toolbar and frame). Devices `P` phone 320 to 480, `T` tablet 600 to 1024, `D` desktop 1280 to 2560, `X` terminal.

**Slices.** S1 shell, simulation, tokens, probe (this one). S2 constellation and Now. S3 mission, spine, decisions. S4 chat, slash commands, Replay. S5 terminal view. S6 themes and motion polish, probes, zip.

**Source abbreviations.** `VL` docs/architecture/ARCHEUS_V2_VISUAL_LANGUAGE.md · `A54` ADR-0054 (spine) · `A55` ADR-0055 (motion) · `UIA` docs/design/ARCHEUS_V2_UI_ARCHITECTURE.md · `PLAN` .collab/V2-real-build-plan.md · `T153` .collab/T-153-slash-commands-spec.md · `CAT` .collab/CHAT-control-catalogue.md · `T149` .collab/T-149-chat-truth-check.md · `T148` .collab/CARD-DRAFT-T-148-replay.md · `RC` .collab/REPLAY-coverage.md · `PROTO` clients/v2-prototype (README, app.js, slash.js, check.mjs) · `V1` clients/app/src and tokens · `ST` archeus/core/domain/states.py · `BOARD` .collab/BOARD.md (read only).

`VL`, `A54` and `A55` live on branch `v2/real` (commit ce31dc7), not in this worktree. Nothing in this folder imports from another folder: the Core state words are a copy in `core-words.js`.

## A. Owner decisions (2026-10-25 and before)

| ID | Decision or request | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| A01 | Build a prototype that simulates the real app experience on all devices and shows everything decided and built | owner request 2026-10-25 | SIMULATED | ALL, SHELL | S1 |
| A02 | Fully responsive 1280 to 2560 wide, plus tablet and phone; no fixed-size concept images, no absolutely positioned controls | owner 2026-10-25, PLAN | SIMULATED | ALL · P/T/D | S1 (probe 0 defects), S6 |
| A03 | Vector constellation map (crisp at any size and DPR), no overlap at any size, working interactions | owner 2026-10-25 | SIMULATED | NOW, MAP | S1 (placeholder map), S2 |
| A04 | Six modes: Dark and Light, each standard and high contrast, plus System, plus forced colours | VL §1 (Q3) | SIMULATED | SHELL, SET | S1 (menu, tokens), S6 (polish) |
| A05 | Reduced motion is Quiet (no third setting) | A55 §3, VL §1 (Q5) | SIMULATED | SHELL, SET | S1 |
| A06 | The core breath is the one allowed loop: scale 1 to 1.018 to 1 over 6000 ms, core mark only, static twin under Reduced | A55 §3 | SIMULATED | NOW, MAP | S1 (mark and rules), S2 (on the live map) |
| A07 | Done is green; V1 blocked red `#F07178` in dark | VL §3.3, A54 §3 | SIMULATED | ALL | S1 |
| A08 | Dark focus colour `#FFF3CF` | VL §1 | SIMULATED | ALL | S1 |
| A09 | No `backdrop-filter`: solid materials only | VL §8 (Q10) | SIMULATED | ALL | S1 |
| A10 | Serif display font (Libre Caslon Text) for the state-sentence line only | VL §6 (Q4) | SIMULATED | NOW | S1 |
| A11 | Targets 44 px, 48 px for desktop primary controls | VL §7 (Q6), owner brief | SIMULATED | ALL | S1 (probe checks both) |
| A12 | The core mark sits on the live map centre on Now | VL §1 (Q5), A55 §3 | SIMULATED | NOW | S1 (centre of the placeholder map), S2 |
| A13 | Six-station spine, labels from Core's own state words | A54 §1 (Q11) | SIMULATED | NOW, WORK, ATT, MAP, TERM | S1 (components), S3 (full use) |
| A14 | Prototype palette taken as the V2 base (ground `#0C0811`, ivory, amber, blue, green) | VL §1 (Q2) | SIMULATED | ALL | S1 |
| A15 | Every simulated element labelled SIMULATED and the app says nothing is connected to a Core | owner brief | SIMULATED | ALL | S1 (badge, page header, terminal line) |
| A16 | Chat: "reads and creates, not effects" (run, spend, settings, delete are cards the owner approves) | owner 2026-10-21, CAT | DESIGNED | CHAT | S4 |
| A17 | Slash commands: read and create shortcuts direct, effects only as cards or the two-step confirm; English names canonical with Italian aliases | owner 2026-10-22, T153 | PROTOTYPED | CHAT | S4 |
| A18 | `/usa` (usage) answers `unknown` until the usage read card exists; usage shown as numbers and reset times, never a token | owner 2026-10-22, T153 | PROTOTYPED | CHAT, SET | S4 (SET shows unknown today) |
| A19 | Replay and Recovery is a V2 surface plus a V1 read; nothing builds a reversal or an operator retry | owner 2026-10-21, T148 | DESIGNED | REP | S4 |
| A20 | V2 production code waits for P26; this prototype and the `v2/real` branch do not merge before it | PLAN §0.8, UIA §S | DESIGNED | none | none |
| A21 | A project made in chat is a record only (folders, clones and access are proposals) | PROTO README (owner answers) | PROTOTYPED | CHAT | S4 |
| A22 | No camera move for a creation off screen: a receipt with "Show" | PROTO README | PROTOTYPED | CHAT, MAP | S4 |
| A23 | Text weight 400 for body text; one material for chat and replies, with a solid fallback | PROTO README (owner 2026-10-23) | PROTOTYPED | CHAT | S4 (solid only, see A09) |

## B. Visual language and tokens

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| B01 | Dark token set (bg `#0C0811`, surfaces `#0E131C` `#151C2A` `#1C2536`, text `#EFE9DA` `#BDB7A8` `#ABA699`, six state colours) | VL §3.1 | SIMULATED | ALL | S1 (`css/tokens.css`) |
| B02 | Light token set derived by hue-keeping (bg `#F4EFE4`, ink `#14101A`, states darkened to 4.5:1) | VL §3.2 | SIMULATED | ALL | S1 |
| B03 | High contrast Dark and Light: per-theme overrides, 7:1 text and states, 2 px lines | VL §4 | SIMULATED | ALL | S1 |
| B04 | System theme follows `prefers-color-scheme` and `prefers-contrast` | VL §1, ADR-0044 | SIMULATED | SHELL | S1 |
| B05 | Forced colours: system colours, hairline in place of the attention tint, glyph plus word for state | VL §5 | SIMULATED | ALL | S1 (simulated palette and a real `forced-colors` block), S6 (review on a real forced-colors run) |
| B06 | Fixed state colours across themes: one colour, one meaning; never the only carrier (glyph and word too) | ADR-0017, UIA §G | BUILT + SIMULATED | ALL | S1 |
| B07 | State figures ◌ ○ ◆ ◇ ● ■ ‖ ✕ ✓ · – with ASCII twins | VL §9, `presentation.json` | BUILT + SIMULATED | ALL, TERM | S1 (`core-words.js`) |
| B08 | Node shapes: circle mission, ring project hub, triangle execution, diamond decision (one shape, one fact) | VL §9, V1 `graph/encoding.ts` | BUILT + SIMULATED | MAP, NOW | S1 (placeholder), S2 |
| B09 | Attention band: static tint at 12 % of amber over the row, never a left edge; the word is ink, the ◆ carries colour; off in high contrast and forced colours | VL §8 | SIMULATED | NOW, ATT | S1 |
| B10 | Line-style vocabulary: solid recorded or passed, filled current, dashed not reached or suggested, hollow not started, dotted unknown | VL §8 | SIMULATED | spine, MAP | S1 (spine), S2 (map edges) |
| B11 | Type scale: body 13/20 desktop and 17/24 phone, caption 12 and 13, display 28/34; system fonts; mono for terminal and times | VL §6, V1 `tokens.json` | BUILT + SIMULATED | ALL | S1 |
| B12 | Solid material: overlays are opaque surface-3, elevation by surface step plus line, no shadows added | VL §8 | SIMULATED | menus, sheets | S1 |
| B13 | Compact density (24 px rows) and the meta column | VL §7, §12 | DESIGNED (not decided) | none | owner question |
| B14 | Tints (teal, rose, lilac) are thread tints only, never state | VL §3.3, ADR-0044 | DESIGNED | none | not planned |
| B15 | Focus ring 3 px, never removed | VL §5, UIA §P | SIMULATED | ALL | S1 |

## C. Motion

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| C01 | One motion registry: nothing animates without an entry; transform and opacity only | A55, ADR-0024 | BUILT | ALL | S1 (V2 Live has exactly one animation) |
| C02 | Duration classes: instant, quick 160, standard 240, layer 200 to 280, travel 600, orbit 900, breath 6000 | A55 §1 | DESIGNED | ALL | S6 |
| C03 | Idle invariant: zero running animations at idle; with live work exactly one, `core-breath` | A55 §3 | SIMULATED | NOW, MAP | S1 (checked in a script, see report) |
| C04 | Breath runs only while a fresh read shows an active execution, the tab is visible and motion is full; never for a queued mission or a fixture | A55 §3 | SIMULATED | NOW, MAP | S1 (driven by the simulation's live work) |
| C05 | Static twin: scale 1 and the text "N running" under Reduced or Quiet | A55 §3 | SIMULATED | NOW, MAP | S1 |
| C06 | Still moments written down: arriving rows, thinking, failing, reconnecting, scrolling | A55 §2 | DESIGNED | ALL | S6 |
| C07 | State change: 160 ms cross-fade of the badge; failure has no shake or pulse | A55, UIA §D | BUILT | ALL | S6 |
| C08 | Output pulse (once per batch, at most one per 2 s per object) and the travelling marker (600 ms) | UIA §C.2, V1 motion registry | BUILT | MAP, NOW | S2 |
| C09 | Luminous thread: a line from what Archeus said to what it changed, drawn once, then a rule | UIA §B, §J, ADR-0026 | BUILT (T1/T2) | CHAT, NOW | S4 |
| C10 | Creation beats from chat: reply 0, appear 160, relation 240, label 180 (dropped), accent gone by 800; Quiet shows all at once | PROTO README, A55 §4 | PROTOTYPED | CHAT, MAP | S4 |
| C11 | Hero moments (handover, plan arming, resolution, causality path), gated and skippable | UIA §K | DESIGNED | NOW, WORK | not planned (prototype-gated PR-6) |
| C12 | View transitions between routes | A55 §2 | DESIGNED | ALL | S6 (optional) |
| C13 | E-stop drops every halo and trace to rest in one 160 ms step | UIA §K | DESIGNED | MAP, NOW | S2 |
| C14 | Prototype breath by WAAPI infinite animation | PROTO app.js ~2533 | PROTOTYPED | NOW | replaced: V2 Live uses the CSS keyframe of A55 |

## D. The spine (ADR-0054)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| D01 | Six stations: Understanding, Planning, Approval, Executing, Verifying, Reviewing; no Done station | A54 §1 | SIMULATED | WORK, NOW, ATT, MAP, TERM | S1 (`spine-model.js`, tested) |
| D02 | State to station table for all 17 mission states | A54 §2 | SIMULATED | same | S1 |
| D03 | Never guess: BLOCKED or PAUSED without a valid `held_from` draws every station unknown; CANCELLED ignores `held_from` | A54 §3 | SIMULATED | same | S1 |
| D04 | Marks by presentation class; passed solid with a check; only COMPLETED turns the spine green | A54 §3, §4 | SIMULATED | same | S1 |
| D05 | Row size: six 8 px marks, 64 by 12 px, no labels | A54 §5 | SIMULATED | WORK, NOW, MAP | S1 |
| D06 | Card size: six 10 px marks, about 120 px, current station label | A54 §5 | SIMULATED | NOW, ATT | S1 |
| D07 | Inspector size: 16 px marks, all six labels, `ol` with `aria-current='step'`, vertical below 480 px container width | A54 §5 | SIMULATED | inspector, sheet | S1 |
| D08 | Time at each station on the inspector spine (omitted when events are pruned) | A54 §5 | DESIGNED | inspector | S3 |
| D09 | Text equivalent sentence generated from Core's word and the table | A54 §6 | SIMULATED | all spines (visually hidden text) | S1 |
| D10 | Terminal form `✓✓✓●○○ Executing` and ASCII `+++*oo Executing` | A54 §7 | SIMULATED | TERM | S1 |
| D11 | Offline view draws the row spine from kept missions, outlined, with "as of" | A54 §8, UIA §O | DESIGNED | NOW (offline) | S3 |
| D12 | Spine on Attention rows by joining the missions read, not a request per row | A54 §9 | SIMULATED | ATT | S1 |
| D13 | Prototype six-station stepper at fixed x positions on one frame | PROTO `phases(m)` | PROTOTYPED | none | replaced by D05 to D07 |

## E. V1 surfaces (BUILT) and what V2 Live shows of them

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| E01 | Navigation table: Now, Work, World, Attention, Control; shortcuts Alt+1/2/3/J, Ctrl+, and Ctrl+K | V1 `tokens/navigation.json` | BUILT | SHELL | S1 (routes; shortcuts S6) |
| E02 | Now: state sentence, Needs you (at most 3 Decide rows), Happening now, Upcoming, Live map, Recent decisions, Since you last looked digest | V1 `Now.tsx` | BUILT + SIMULATED | NOW | S1 (all but the digest), S2 |
| E03 | Work: missions grouped by what they wait on (Needs you, Active, Planning, Blocked, Paused, Done, Failed or cancelled), Pinned, Ideas | V1 `Work.tsx` | BUILT + SIMULATED | WORK | S1 (no pins), S3 |
| E04 | Attention: flat Core list of approvals, verification, mission, knowledge, drift, automation, account items; V2 groups Decide, Review, Unblock | V1 `Attention.tsx`, UIA §H | BUILT + SIMULATED | ATT | S1 |
| E05 | World: Projects and Knowledge tabs, repositories, inspections, supersession chain | V1 `World.tsx` | BUILT | MAP, SET | S1 (knowledge in the simulation only), S2 |
| E06 | Control sections: Autonomy, Automations, Resources, Sessions, Clients, Appearance, About, Emergency stop | V1 `Control.tsx`, navigation.json | BUILT + SIMULATED | SET | S1 (accounts, harnesses, automations, clients, hooks, MCP, agents), S5 |
| E07 | Mission inspector tabs: Outcome, Plan, Now, Evidence, Why, Timeline, Relations | V1 `Mission.tsx`, navigation.json | BUILT + SIMULATED | WORK, MAP, ATT inspector | S1 (five tabs), S3 (Why, Relations) |
| E08 | Other inspectors: execution (Output, Checkpoints), session (Brief, Lineage), knowledge, automation run, approval, plan, verification, route decision, policy decision, context package, project, repository | V1 navigation.json | BUILT | inspector | S3 |
| E09 | Approval card: canonical action, why, consequence of reject, expiry; decide needs the approve scope and step-up | V1 `Attention.tsx` ApprovalCard, T149 | BUILT + SIMULATED | ATT, NOW, inspector | S1 (decision sheet), S3 |
| E10 | Command bar and palette (Ctrl+K), grammar of ADR-0042 | V1 `CommandBar.tsx`, `state/palette.ts` | BUILT | CHAT | S4 |
| E11 | Conversation thread with cards: approval, e-stop, stop mission, route explanation, change card | V1 `Now.tsx` Conversation | BUILT | CHAT | S4 |
| E12 | Offline Now: kept missions, "as of hh:mm", Decide rows read-only | V1 `OfflineNow`, UIA §O | BUILT | NOW | S3 |
| E13 | Live map with halo, travelling marker, hulls, depth alpha, search, legend and text mirror (Canvas 2D) | V1 `graph/` | BUILT | NOW, MAP | S2 (V2 Live draws SVG, same facts, text mirror kept) |
| E14 | Phone: graph hidden below 600 px, the list stands in | UIA §M, V1 P18 A12 | BUILT | NOW, MAP · P | S1 (map shown small, list under it), S2 |
| E15 | Toasts and the polite announcer (at most one per 5 s) | V1 `toast.ts`, `a11y/announce.ts` | BUILT | ALL | S1 (one status toast), S6 |
| E16 | Pins and saved views | V1 `pins.ts` | BUILT | WORK, MAP | S3 |
| E17 | Idea path stepper (Captured to Learned) | V1 `Work.tsx` IdeaPath | BUILT | WORK | S3 |
| E18 | Digest "since you last looked", acknowledge cursor | V1 `Now.tsx` DigestSection | BUILT | NOW | S3 |
| E19 | Fresh/stale readings with age ("no output for 12 min"), never a client timer | UIA §D, A55 §3 | BUILT + SIMULATED | WORK, NOW, TERM | S1 |
| E20 | Obligation groups Decide, Review, Unblock; at most 3 Decide rows on Now; acknowledge and snooze need a Core ADR | UIA §H, PLAN §5 | DESIGNED | ATT, NOW | S1 (groups), S3 (keys, snooze not built) |
| E21 | Keyboard model: Enter primary, Ctrl+Enter secondary, j/k, `?` lists keys | PLAN U2-c | DESIGNED | ALL · D | S6 |

## F. Chat and slash commands

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| F01 | Chat bar entry on Now with placeholder "Tell Archeus what you need...", SIMULATED tag on every reply | PROTO build steps 1 to 3 | PROTOTYPED | NOW, CHAT | S1 (own screen, scripted reply labelled), S4 |
| F02 | Message creates: message, mission, idea, remembered preference, feedback candidate, mission thread, narrowing directive | T149 §1 | BUILT | CHAT | S4 |
| F03 | Under the `standard` profile a new-work message starts and dispatches without a card (G1, an owner-rule breach) | T149 §1, §4 | BUILT (flagged) | CHAT | S4 (must be labelled, never shown as owner-approved) |
| F04 | General (non-project) questions cannot be answered today (G5); replies are scripted | T149 §2, §4 | DESIGNED | CHAT | S4 (label as faked) |
| F05 | Create a project from chat has no path in V1 | T149 §1 | PROTOTYPED | CHAT | S4 (label as faked) |
| F06 | Comment on a mission or plan: no comment object, only messages | T149 §1 | BUILT (limit) | CHAT | S4 |
| F07 | Route classes: 58 READ, 6 CREATE, 36 PROPOSE, 7 NEVER of 107 routes; chat calls READ and CREATE directly, drafts PROPOSE as cards, never calls NEVER | CAT | DESIGNED | CHAT | S4 |
| F08 | NEVER routes: device launch and pair, approvals decide, verifications decide, missions review | CAT | DESIGNED | CHAT | S4 |
| F09 | Stop mission: confirm card; e-stop: card then control scope; pause all, resume all, reprioritise: direct, no card | T149 §1 | BUILT | CHAT | S4 |
| F10 | Approve from chat only on the card on screen with its hash; a bare "approve" is declined | T149 §1 | BUILT | CHAT | S4 |
| F11 | Slash menu: `/` opens a combobox listbox above the bar; Up, Down, Tab, Enter, Escape; `?` lists by class; `//name` sends text | T153, PROTO slash.js | PROTOTYPED | CHAT | S4 |
| F12 | READ and NAVIGATE: /help /status /usage /projects /missions /needs /digest /ideas /plan /why /search /trace /replay /open /focus /clear /theme /motion (Italian aliases /aiuto /stato /usa /progetti /missioni /attesa /riepilogo /idee /piano /perche /cerca /traccia /rigioca /apri /vai /pulisci /tema /movimento) | T153 §3.1, PROTO | PROTOTYPED | CHAT | S4 |
| F13 | CREATE: /mission /idea /feedback /remember /tell /general (/remember is a confirm card naming the scope) | T153 §3.2, PROTO | PROTOTYPED | CHAT | S4 |
| F14 | PROPOSE (card or two-step confirm, decides nothing): /start /stop /estop /pause /resume /cancel /review /approve /reject /account | T153, PROTO | PROTOTYPED | CHAT | S4 |
| F15 | Refused before sending: extra arguments, bad choices, unknown names, text that looks like a secret (`sk-`, `ghp_`, `AKIA`, `Bearer `) | PROTO README slash | PROTOTYPED | CHAT | S4 |
| F16 | `@` mentions; 2 s duplicate-send prompt and rate limit (Core side) | T153 | DESIGNED | CHAT | S4 (mentions), not built (Core) |
| F17 | Phone chat sheet follows `visualViewport` (keyboard) and expands | PROTO step 2 | PROTOTYPED | CHAT · P | S4 |
| F18 | Chat delay and error fixtures, General routing, Review plan | PROTO steps 4 to 6 | PROTOTYPED | CHAT | S4 |
| F19 | Usage in chat: `/usage` answers `unknown` until T-154 | T153 owner answers | PROTOTYPED | CHAT | S4 |
| F20 | Subscription token read by `claude_sessions/usage.py` conflicts with AGENT-RULES item 6 (G2) | T149 §4 | BUILT (flagged) | none | owner decision, never shown |

## G. Replay and Recovery

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| G01 | Eight Replay categories: INTENDED, AUTHORIZED, RECORDED, MAY-HAVE-TAKEN-EFFECT, UNCERTAIN, SUSPENDED, RECONCILED, NONE; plus UNKNOWN for "cannot tell" | RC, T148 | DESIGNED | REP | S1 (all nine drawn), S4 |
| G02 | 130 states over 19 machines classified (INTENDED 29, RECORDED 46, SUSPENDED 16, MAY-HAVE-TAKEN-EFFECT 12, AUTHORIZED 9, UNCERTAIN 5, RECONCILED 5, UNKNOWN 5, NONE 3) | RC Part A | DESIGNED | REP | S1 (the machines the simulation uses), S4 (rest) |
| G03 | `GET /v1/missions/{id}/replay` from rows, not the event log; a state with no entry answers UNKNOWN | T148 R1 | DESIGNED | REP | S1 (simulated read), S4 |
| G04 | Evidence rows labelled by real strength (checkpoint lists capped at 30 are summaries, an ERROR verification is not a verdict) | T148 R2 | DESIGNED | REP | S4 |
| G05 | `settled_by` core, device or unknown from the event actor, never a new record | T148 R3 | DESIGNED | REP | S1 |
| G06 | Retention honesty: events kept 180 days; a pruned range answers UNKNOWN with a reason, never "nothing happened" | T148 R4, RC gap 6 | DESIGNED | REP | S1 (pruned note) |
| G07 | "NOT RECORDED": external effects, starting digest, operator reconciliation, complete history, reasoning transcript, file snapshots, cost provenance, confinement proof | RC gaps, PROTO REPLAY_GAPS | PROTOTYPED | REP | S1 |
| G08 | Five example rows (task initiated, files changed, tests passed, external response lost, workflow suspended) | RC Part B | DESIGNED | REP | S4 |
| G09 | Prototype Replay: 13 source-labelled entries for Fix date test, pointer and keyboard cursor, a failed verification and a LOST execution, no autoplay | PROTO README | PROTOTYPED | REP | S1 (cursor via Earlier and Later), S4 |
| G10 | Recovery choices create explicit approval cards only; approval changes a receipt, never the evidence; retry and owner-question drafts editable | PROTO README | PROTOTYPED | REP | S4 |
| G11 | Never claim an external effect can be reversed; no operator spawn, adopt or retry; no second spawn (retry is a new execution id) | T148 N7, `harnesses/base.py` | DESIGNED | REP | S4 |
| G12 | Four other meanings of "replay" stay separate: router replay, stream replay from Last-Event-ID, queued command resend, Trace tab two-clock playback | T148 N4 | BUILT | none | naming only |
| G13 | Mission Trace tab (P21 slice C-read) | BOARD T-119 | BUILT | WORK inspector | S3 (Timeline tab today) |

## H. Platform facts shown as simulated state

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| H01 | Mission machine, 17 states, with edges from `states.py`; `held_from` on BLOCKED and PAUSED | ST, A54 | BUILT + SIMULATED | WORK, ATT, spine | S1 (`sim.js` edge table, tested) |
| H02 | Execution machine (INTENT to ENDED_*, LOST, adopted, reconciled_kill), task, plan, approval, verification, review machines | ST | BUILT + SIMULATED | WORK inspector, REP | S1 |
| H03 | Account health states (UNVERIFIED, AVAILABLE, CONSTRAINED, LIMITED, DEGRADED, OPEN, UNAUTHENTICATED) and usage windows; unknown shown as "unknown", never 0 | ST, UIA, BOARD T-125 (review branch) | states BUILT; consumption read on a review branch + SIMULATED | SET | S1 |
| H04 | Spawn breaker O7: per harness, trips at 3 failures in 10 min, doubling wait 15 s to 5 min, half-open after 5 min, visible as "cannot start" | BOARD T-106 | BUILT on branch fix/t106 (in review, production dispatch switch off) + SIMULATED | SET, WORK | S1 (inject a spawn failure), S3 |
| H05 | Execution quiet reading ("no output for N min") and LOST then adopted recovery | A55, ST, BOARD T-125/T-128 | LOST and adopted BUILT in ST; the quiet reading and activity chip BUILT on review branches + SIMULATED | WORK, NOW | S1 |
| H06 | Verification pass and fail; failed verification replans; replan budget then BLOCKED | ST, BOARD | BUILT + SIMULATED | WORK, REP | S1 |
| H07 | Hook asks before an action: execution AWAITING_APPROVAL, approval card, reject blocks the mission | ST, T149 | BUILT + SIMULATED | ATT (trigger an approval) | S1 |
| H08 | Automations (ENABLED, PENDING_APPROVAL, SUSPENDED by the loop guard), schedule triggers and next_run | ST, BOARD T-129 | BUILT + SIMULATED | SET, ATT | S1 |
| H09 | Hooks, MCP servers and agents managers (lists, enable and disable) | V1 Control, BOARD T-099 | BUILT (lists) + SIMULATED | SET | S1 (read-only lists), S5 |
| H10 | Accounts and models: harnesses, per-account usage, models by tier | BOARD T-125, PLAN | BUILT + SIMULATED | SET | S1 |
| H11 | Clients (paired devices) with revoke | V1 Control, BOARD | BUILT + SIMULATED | SET | S1 |
| H12 | Knowledge items (CANDIDATE, CONFIRMED, RETRACTED, SUPERSEDED), confirm or reject | ST, V1 World | BUILT + SIMULATED | ATT, SET | S1 (candidates in Attention) |
| H13 | Ideas with their own states | ST, V1 Work | BUILT + SIMULATED | WORK | S1 |
| H14 | P20 security and isolation (PV-20 AppContainer, broker, origin gate): physical reach not built in V1, switches off | BOARD T-131 to T-138 | DESIGNED | SET (About) | S5 (state it, never simulate isolation) |
| H15 | P21: trace, health (Control, About), activity chip, schedules, search, notifications, privacy | BOARD T-118 to T-130 | trace, search and notifications merged at f483f87; provenance, health, activity chip and schedules built on review branches (T-130 integrates) | WORK, SET | S3 |
| H16 | Usage limits and Pause all, Resume all, Emergency stop | V1 Control, T149 | BUILT | SET, NOW | S3 |
| H17 | Themes in V1: dark and light with contrast aliases; the "6 themes" were confirmed in VL §1 | V1 tokens.json, VL | BUILT + SIMULATED | SET | S1 |

## I. Prototype features (clients/v2-prototype)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| I01 | Overview hub with chat bar, zoomable projects (`#/now/harbor`) | PROTO README | PROTOTYPED | NOW, MAP | S2 |
| I02 | Mission screen: chain, phase stepper, tabbed inspector, Tell and Stop | PROTO README | PROTOTYPED | WORK | S3 |
| I03 | Shared: agents and devices as endpoints, tabbed inspector | PROTO README | PROTOTYPED | SET, MAP | S3 |
| I04 | Plan approval screen: What, Why, Core consequence, Approve, Request changes, Reject; local receipt only | PROTO README | PROTOTYPED | ATT | S1 (Approve, Reject), S3 |
| I05 | Decision sheet with two-step confirm on the phone | PROTO README | PROTOTYPED | ATT · P | S1 (one step), S3 |
| I06 | Fixtures: 3 projects (Archeus, Notes, Ideas) and 5 missions (Search provenance, Fix date test, Docs refresh, Offline capture, Export backup) | PROTO app.js | PROTOTYPED | ALL | S1 (extended to 8 missions) |
| I07 | Terminal screens (overview, mission, replay) as a text grid; keys 1 2 3, p, y, Left and Right | PROTO README | PROTOTYPED | TERM | S1 (Now, Work, Attention, Replay), S5 |
| I08 | Phone frames: hub, Review, slim sheet, chat sheet | PROTO README | PROTOTYPED | P | S1 (real layout instead of art) |
| I09 | Concept art rasters at fixed pixel coordinates, `CONCEPT_LAYOUT` tables | PROTO | PROTOTYPED | none | not ported (owner complaint) |
| I10 | Hit probe by `elementFromPoint`, 44 pt phone and 48 CSS px desktop | PROTO `tools/v2_hit_probe.py` | PROTOTYPED | ALL | S1 (`tools/v2_live_layout_probe.py`) |
| I11 | Service worker and PWA | PROTO sw.js | PROTOTYPED | none | optional, default off |

## J. Responsive shell and the tool chrome (new in V2 Live)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| J01 | Desktop at 1024 and wider: rail, main, optional right inspector | owner brief | SIMULATED | ALL · D | S1 |
| J02 | Tablet 600 to 1023: collapsible rail, inspector as a right sheet | owner brief | SIMULATED | ALL · T | S1 |
| J03 | Phone under 600: bottom navigation, sheets, thumb-reachable decisions | owner brief, UIA §M | SIMULATED | ALL · P | S1 |
| J04 | Terminal view as a device switch and as `#/terminal` | owner brief | SIMULATED | TERM · X | S1 |
| J05 | Device preview: Auto, Phone, Tablet, Desktop, Terminal; frames scale down to fit | owner brief | SIMULATED | SHELL | S1 |
| J06 | Theme menu, Reduced motion toggle, simulation menu in a thin toolbar | owner brief | SIMULATED | SHELL | S1 |
| J07 | Fonts: Libre Caslon Text VF copied from the prototype with its OFL notice (127 KB) | VL §6 | SIMULATED | NOW | S1 |
| J08 | Layout probe: 14 viewports by every route and overlay by dark and light | owner brief | SIMULATED | none | S1 |
| J09 | localStorage only inside try/catch; URL parameters `theme`, `device`, `motion`, `sim`, `speed`, `seed`, `advance` | owner brief | SIMULATED | SHELL | S1 |

## K. Simulation (sim.js)

| ID | Item | Where | Slice |
|---|---|---|---|
| K01 | Seeded and deterministic: same seed and calls, same event log, whatever the chunking | all | S1 (tested) |
| K02 | Controls: play, pause, speed x0.5 to x8, trigger an approval, inject a failure (execution, verification or spawn), reset | SHELL, SET | S1 |
| K03 | Events a UI subscribes to, with Core event names (`mission.state_changed`, `approval.requested`, `execution.progress`) | all | S1 |
| K04 | Owner actions go through the same edges: approve, reject, accept, request changes, unblock, resume, replan, pause, cancel, confirm, retract, enable | ATT, WORK | S1 |
| K05 | Bounded log with a pruned flag, so Replay can say UNKNOWN | REP | S1 |
| K06 | Scripted story: a theme audit mission planned and auto-approved; a quiet execution lost and adopted; a verification that fails once; a plan waiting for the owner; a mission blocked on a question | all | S1 |

## L. Not decided or not planned (do not simulate as decided)

| ID | Item | Source | Status | Note |
|---|---|---|---|---|
| L01 | Compact density, the meta column | VL §12 | DESIGNED (open) | owner question |
| L02 | Size and drawing of the core mark (place is decided) | VL §12 | DESIGNED (open) | placeholder mark in S1 |
| L03 | Headings and wordmark in the display font | VL §12 | DESIGNED (open) | wordmark uses it today, a stand-in |
| L04 | Flow strip against "spatial primary"; e-stop placement; state precedence for aggregates | UIA §T | DESIGNED (open) | not simulated |
| L05 | Acknowledge and snooze Core records | UIA §H, PLAN G0-7 | DESIGNED (open) | not simulated |
| L06 | Voice, sound, OS-level presence, 3D and XR | UIA §S "Later" | DESIGNED (later) | not simulated |
| L07 | Which Replay rows come from a broker (external effects) | T148 N7, PV-20 broker | DESIGNED (blocked on P20) | shown as NOT RECORDED |

## Counts

169 rows: A 23 owner decisions · B 15 tokens · C 14 motion · D 13 spine · E 21 V1 surfaces · F 20 chat and slash · G 13 Replay · H 17 platform facts · I 11 prototype features · J 9 shell · K 6 simulation · L 7 open.
By status word (a row can carry two): BUILT 50 · DESIGNED 34 · PROTOTYPED 32 · SIMULATED 77 (all of K counts as simulated).
Slice 1 shows 98 rows (the Slice column names S1, fully or in part); the rest, and the "part" rows, are the later slices' to-do list.
