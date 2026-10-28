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

**Screens and devices** (the "Where" column): Screens `NOW`, `WORK` (Work, which also holds what Attention showed; `#/attention` redirects to `#/work`), `REP` (Replay), `CHAT`, `SEC` (Security, `#/security`), `HLT` (Health, `#/health`), `ACC` (Accounts, `#/accounts`), `USE` (Usage, `#/usage`), `EXT` (Extensions, `#/extensions`), `SET` (Settings), `MORE` (phone menu of the other screens), `TERM` (terminal view), `ALL` (every screen), `SHELL` (toolbar, frames, All devices view). Devices `P` phone 320 to 480, `T` tablet 600 to 1024, `D` desktop 1280 to 2560, `X` terminal.

**Slices.** S1 shell, simulation, tokens, probe (this one). S2 constellation and Now. S3 mission, spine, decisions. S4 chat, slash commands, Replay. S5 terminal view. S6 themes and motion polish, probes, zip.

**Source abbreviations.** `VL` docs/architecture/ARCHEUS_V2_VISUAL_LANGUAGE.md · `A54` ADR-0054 (spine) · `A55` ADR-0055 (motion) · `UIA` docs/design/ARCHEUS_V2_UI_ARCHITECTURE.md · `PLAN` .collab/V2-real-build-plan.md · `T153` .collab/T-153-slash-commands-spec.md · `CAT` .collab/CHAT-control-catalogue.md · `T149` .collab/T-149-chat-truth-check.md · `T148` .collab/CARD-DRAFT-T-148-replay.md · `RC` .collab/REPLAY-coverage.md · `PROTO` clients/v2-prototype (README, app.js, slash.js, check.mjs) · `V1` clients/app/src and tokens · `ST` archeus/core/domain/states.py · `BOARD` .collab/BOARD.md (read only).

`VL`, `A54` and `A55` live on branch `v2/real` (commit ce31dc7), not in this worktree. Nothing in this folder imports from another folder: the Core state words are a copy in `core-words.js`.

The owner's answers of 2026-10-25 are recorded in `.collab/V2-live-decisions.md` (abbreviation `VLD`); they override the brief where they differ and are rows A24 to A31 and section M.

## A. Owner decisions (2026-10-25 and before)

| ID | Decision or request | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| A01 | Build a prototype that simulates the real app experience on all devices and shows everything decided and built | owner request 2026-10-25 | SIMULATED | ALL, SHELL | S1 |
| A02 | Fully responsive 1280 to 2560 wide, plus tablet and phone; no fixed-size concept images, no absolutely positioned controls | owner 2026-10-25, PLAN | SIMULATED | ALL · P/T/D | S1 (probe 0 defects), S6 done (layout probe full matrix, 14 viewports, dark and light, EN and IT: see the final report for the run) |
| A03 | Vector constellation map (crisp at any size and DPR), no overlap at any size, working interactions | owner 2026-10-25 | SIMULATED | NOW | S1 (placeholder map), S2 BUILT (js/constellation module on #/now; the separate Map screen was removed on 2026-10-27, `#/map` redirects to `#/now`; probes: 732 map checks and the layout probe, 0 defects) |
| A04 | Six modes: Dark and Light, each standard and high contrast, plus System, plus forced colours | VL §1 (Q3) | SIMULATED | SHELL, SET | S1 (menu, tokens), S6 done in Chromium: Light contrast checked by the probe on every route (owner approved the Light look as is, 2026-10-26), forced colours swept by computed contrast; not run on a real Windows High Contrast or a phone |
| A05 | Reduced motion is Quiet (no third setting) | A55 §3, VL §1 (Q5) | SIMULATED | SHELL, SET | S1 |
| A06 | The core breath: scale 1 to 1.018 to 1 over 6000 ms, core mark only, static twin under Reduced. Since 2026-10-27 it is no longer the only loop in V2 Live (see Q03) | A55 §3 | SIMULATED | NOW | S1 (mark and rules), S2 BUILT (the map's own core mark; breath only for a playing simulation with fresh output) |
| A07 | Done is green; V1 blocked red `#F07178` in dark | VL §3.3, A54 §3 | SIMULATED | ALL | S1 |
| A08 | Dark focus colour `#FFF3CF` | VL §1 | SIMULATED | ALL | S1 |
| A09 | No `backdrop-filter`: solid materials only | VL §8 (Q10) | SIMULATED | ALL | S1 |
| A10 | Serif display font (Libre Caslon Text) for the state-sentence line only | VL §6 (Q4) | SIMULATED | NOW | S1 |
| A11 | Targets 44 px, 48 px for desktop primary controls | VL §7 (Q6), owner brief | SIMULATED | ALL | S1 (probe checks both) |
| A12 | The core mark sits on the live map centre on Now | VL §1 (Q5), A55 §3 | SIMULATED | NOW | S1 (centre of the placeholder map), S2 BUILT (core at the centre of the module) |
| A13 | Six-station spine, labels from Core's own state words | A54 §1 (Q11) | SIMULATED | NOW, WORK, ATT, TERM | S1 (components), S3 (done: full use) |
| A14 | Concepts are the visual authority: flat near-black ground `#0B090E` (S0 token), ivory, amber, blue, green; no nebula/bloom/blur (was ground `#0C0811`) | owner 2026-10-26, concept authority + consolidated S0 tokens | SIMULATED | ALL | S1 |
| A15 | Every simulated element labelled SIMULATED and the app says nothing is connected to a Core | owner brief | SIMULATED | ALL | S1 (badge, page header, terminal line) |
| A16 | Chat: "reads and creates, not effects" (run, spend, settings, delete are cards the owner approves) | owner 2026-10-21, CAT | DESIGNED | CHAT | S1, S4 built (cards for every effect; refusals) |
| A17 | Slash commands: read and create shortcuts direct, effects only as cards or the two-step confirm; English names canonical with Italian aliases | owner 2026-10-22, T153 | PROTOTYPED | CHAT | S1, S4 built (34 commands, two-step confirms) |
| A18 | `/usa` (usage) answers `unknown` until the usage read card exists; usage shown as numbers and reset times, never a token | owner 2026-10-22, T153 | PROTOTYPED | CHAT, SET | S1, S4 built (`/usage` answers Unknown) |
| A19 | Replay and Recovery is a V2 surface plus a V1 read; nothing builds a reversal or an operator retry | owner 2026-10-21, T148 | DESIGNED | REP | S1, S4 built (Replay page, recovery cards) |
| A20 | V2 production code waits for P26; this prototype and the `v2/real` branch do not merge before it | PLAN §0.8, UIA §S | DESIGNED | none | none |
| A21 | A project made in chat is a record only (folders, clones and access are proposals) | PROTO README (owner answers) | PROTOTYPED | CHAT | S4 built (`Create a project called X` is a record only, labelled) |
| A22 | No camera move for a creation off screen: a receipt with "Show" | PROTO README | PROTOTYPED | CHAT | S4 partly: the receipt names the project; no camera move (map module) |
| A23 | Text weight 400 for body text; one material for chat and replies, with a solid fallback | PROTO README (owner 2026-10-23) | PROTOTYPED | CHAT | S4 built (solid surfaces) |
| A24 | Language: English UI with an Italian switch for the main surfaces (Now, Work, Attention, spine words, slash aliases); toggle in the toolbar, persisted in try/catch localStorage | VLD (Language) | SIMULATED | ALL, SHELL | S1 (chrome, state words, spine, menus, slash aliases; fixture text and the terminal stay English) |
| A25 | Areas that must be in V2 Live: Now/Work/Attention/spine/decisions; Chat/slash/Replay; Security, health, usage, accounts; Terminal view and themes | VLD (Areas) | SIMULATED | see section M | S1 (a route for each) |
| A26 | Look: match the concepts' mood (dark, glowing constellation) but crisp vector; layout follows content | VLD (Look) | SIMULATED | ALL | S1 (dark palette, vector map), S2 BUILT (glow, hulls, crystals, serif labels, six themes) |
| A27 | Simulation: scripted story plus the owner's actions; approve, reject, chat, slash commands and Replay change state accordingly | VLD (Simulation) | SIMULATED | ATT, CHAT, REP, WORK | S1 |
| A28 | Devices: toolbar switch plus an All devices side-by-side view, all driven by one simulation instance | VLD (Devices) | SIMULATED | SHELL | S1 |
| A29 | Audience: the owner only, internal review: short toggleable inline decision notes name the decision each choice implements | VLD (Audience) | SIMULATED | ALL | S1 (notes on every main screen, toggle in the Theme menu and Settings), S2 to S6 (extend) |
| A30 | Viewing: `start.cmd` on this PC only (127.0.0.1:8000), nothing hosted | VLD (Viewing) | SIMULATED | none | S1 |
| A31 | Stop all work at 20 % weekly usage, meter read every 15 minutes; do not start other cards | VLD standing instructions | DESIGNED (process rule) | none | none |

## B. Visual language and tokens

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| B01 | Dark token set: concept near-black bg `#0B090E`, same-hue S0 surfaces `#0E0C12` `#141118` `#1A171F`, text `#EFE9DA` `#BDB7A8` `#ABA699`, six state colours (was bg `#0C0811`, surfaces `#0E131C` `#151C2A` `#1C2536`) | owner 2026-10-26, concept authority + consolidated S0 tokens | SIMULATED | ALL | S1 (`css/tokens.css`) |
| B02 | Approved derived Light token set: bg `#FDFCF8`, ink `#1B1530`, states darkened to 4.5:1; contrast verification only (was bg `#F4EFE4`, ink `#14101A`) | owner 2026-10-25 Slice 1 “Approve as is”; reaffirmed 2026-10-26 | SIMULATED | ALL | S1 |
| B03 | High contrast Dark and Light: per-theme overrides, 7:1 text and states, 2 px lines | VL §4 | SIMULATED | ALL | S1 |
| B04 | System theme follows `prefers-color-scheme` and `prefers-contrast` | VL §1, ADR-0044 | SIMULATED | SHELL | S1 |
| B05 | Forced colours: system colours, hairline in place of the attention tint, glyph plus word for state | VL §5 | SIMULATED | ALL | S1 (simulated palette and a real `forced-colors` block), S6 done with Chromium's `forced_colors` emulation (Now, Map, Chat, Security, Terminal and eight more routes: borders visible, no ink on ink, a 3 px Highlight line on every selected item); a real OS run is not done |
| B06 | Fixed state colours across themes: one colour, one meaning; never the only carrier (glyph and word too) | ADR-0017, UIA §G | BUILT + SIMULATED | ALL | S1 |
| B07 | State figures ◌ ○ ◆ ◇ ● ■ ‖ ✕ ✓ · – with ASCII twins | VL §9, `presentation.json` | BUILT + SIMULATED | ALL, TERM | S1 (`core-words.js`) |
| B08 | Node shapes: circle mission, ring project hub, triangle execution, diamond decision (one shape, one fact) | VL §9, V1 `graph/encoding.ts` | BUILT + SIMULATED | NOW | S1 (placeholder), S2 BUILT (module draws mission disc or crystal, project hexagon, execution triangle, decision diamond) |
| B09 | Attention band: static tint at 12 % of amber over the row, never a left edge; the word is ink, the ◆ carries colour; off in high contrast and forced colours | VL §8 | SIMULATED | NOW, WORK | S1, B (Needs you rows on Work) |
| B10 | Line-style vocabulary: solid recorded or passed, filled current, dashed not reached or suggested, hollow not started, dotted unknown | VL §8 | SIMULATED | spine | S1 (spine), S2 BUILT (map edges: contains, runs, asks; accent colour for needs-you and running) |
| B11 | Type scale: body 13/20 desktop and 17/24 phone, caption 12 and 13, display 28/34; system fonts; mono for terminal and times | VL §6, V1 `tokens.json` | BUILT + SIMULATED | ALL | S1 |
| B12 | Solid material: overlays are opaque surface-3, elevation by surface step plus line, no shadows added | VL §8 | SIMULATED | menus, sheets | S1 |
| B13 | Compact density (24 px rows) and the meta column | VL §7, §12 | DESIGNED (not decided) | none | owner question |
| B14 | Tints (teal, rose, lilac) are thread tints only, never state | VL §3.3, ADR-0044 | DESIGNED | none | not planned |
| B15 | Focus ring 3 px, never removed | VL §5, UIA §P | SIMULATED | ALL | S1 |

## C. Motion

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| C01 | One motion registry: nothing animates without an entry; transform and opacity only | A55, ADR-0024 | BUILT + SIMULATED | ALL | S1, S2 (breath, arrival fades and travelling marker: `js/constellation/map.js`; chevron transition: `css/inspector.css`) |
| C02 | Duration classes: instant, quick 160, standard 240, layer 200 to 280, travel 600, orbit 900, breath 6000 | A55 §1 | DESIGNED | ALL | not built (the durations in `tokens.css` are used where an animation exists; no duration-class table) |
| C03 | Idle invariant: zero running animations at idle (paused simulation, hidden tab, Reduced, off the map); with a playing simulation only the Q03 list (`core-breath`, `am-drift`, `am-ring`, `am-travel`), each infinite, 3.6 s or longer, transform or opacity only | A55 §3 | SIMULATED | NOW | S1 (checked in a script, see report), S2 BUILT (layout probe checks it on the Overview; amended for the Q03 list) |
| C04 | Breath runs only while a fresh read shows an active execution, the tab is visible and motion is full; never for a queued mission or a fixture | A55 §3 | SIMULATED | NOW | S1 (driven by the simulation's live work), S2 BUILT (playing, RUNNING and not stuck, output under 2 min old) |
| C05 | Static twin: scale 1 and the text "N running" under Reduced or Quiet | A55 §3 | SIMULATED | NOW | S1, S2 BUILT ("N running" at the map's core) |
| C06 | Still moments written down: arriving rows, thinking, failing, reconnecting, scrolling | A55 §2 | DESIGNED | ALL | not built (no still-moment rules beyond Quiet) |
| C07 | State change: 160 ms cross-fade of the badge; failure has no shake or pulse | A55, UIA §D | BUILT | ALL | not verified in S6 |
| C08 | Output pulse (once per batch, at most one per 2 s per object) and the travelling marker (600 ms) | UIA §C.2, V1 motion registry | BUILT | NOW | S2 BUILT (pulse on execution start, end and output) |
| C09 | Luminous thread: a line from what Archeus said to what it changed, drawn once, then a rule | UIA §B, §J, ADR-0026 | BUILT (T1/T2) | CHAT, NOW | S4 |
| C10 | Creation beats from chat: reply 0, appear 160, relation 240, label 180 (dropped), accent gone by 800; Quiet shows all at once | PROTO README, A55 §4 | PROTOTYPED | CHAT | S4 |
| C11 | Hero moments (handover, plan arming, resolution, causality path), gated and skippable | UIA §K | DESIGNED | NOW, WORK | not planned (prototype-gated PR-6) |
| C12 | View transitions between routes | A55 §2 | DESIGNED | ALL | not built (optional) |
| C13 | E-stop drops every halo and trace to rest in one 160 ms step | UIA §K | SIMULATED | NOW | S2 (drift, rings and travelling markers stop when the emergency stop is engaged: `js/map.js` passes `playing and not engaged` to the map; the nodes snap to rest, there is no 160 ms tween) |
| C14 | Prototype breath by WAAPI infinite animation | PROTO app.js ~2533 | PROTOTYPED | NOW | replaced: V2 Live uses the CSS keyframe of A55 |

## D. The spine (ADR-0054)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| D01 | Six stations: Understanding, Planning, Approval, Executing, Verifying, Reviewing; no Done station | A54 §1 | SIMULATED | WORK, NOW, ATT, TERM | S1 (`spine-model.js`, tested) |
| D02 | State to station table for all 17 mission states | A54 §2 | SIMULATED | same | S1 |
| D03 | Never guess: BLOCKED or PAUSED without a valid `held_from` draws every station unknown; CANCELLED ignores `held_from` | A54 §3 | SIMULATED | same | S1 |
| D04 | Marks by presentation class; passed solid with a check; only COMPLETED turns the spine green | A54 §3, §4 | SIMULATED | same | S1 |
| D05 | Row size: six 8 px marks, 64 by 12 px, no labels | A54 §5 | SIMULATED | WORK, NOW | S1 |
| D06 | Card size: six 10 px marks, about 120 px, current station label | A54 §5 | SIMULATED | NOW, ATT | S1 |
| D07 | Inspector size: 16 px marks, all six labels, `ol` with `aria-current='step'`, vertical below 480 px container width | A54 §5 | SIMULATED | inspector, sheet | S1 |
| D08 | Time at each station on the inspector spine (omitted when events are pruned) | A54 §5 | SIMULATED | inspector | S3 (done: `js/inspector-mission.js`, `js/areas-model.js`) |
| D09 | Text equivalent sentence generated from Core's word and the table | A54 §6 | SIMULATED | all spines (visually hidden text) | S1 |
| D10 | Terminal form `✓✓✓●○○ Executing` and ASCII `+++*oo Executing` | A54 §7 | SIMULATED | TERM | S1 |
| D11 | Offline view draws the row spine from kept missions, outlined, with "as of" | A54 §8, UIA §O | DESIGNED | NOW (offline) | S3 (done: built) |
| D12 | Spine on Attention rows by joining the missions read, not a request per row | A54 §9 | SIMULATED | WORK | S1 |
| D13 | Prototype six-station stepper at fixed x positions on one frame | PROTO `phases(m)` | PROTOTYPED | none | replaced by D05 to D07 |

## E. V1 surfaces (BUILT) and what V2 Live shows of them

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| E01 | Navigation table: Now, Work, World, Attention, Control; shortcuts Alt+1/2/3/J, Ctrl+, and Ctrl+K | V1 `tokens/navigation.json` | BUILT | SHELL | S1 (routes); the shortcuts Alt+1/2/3/J, Ctrl+, and Ctrl+K are not built (S6 built j, k, Enter, Space, Esc and ? instead: E21) |
| E02 | Now: state sentence, Needs you (at most 3 Decide rows), Happening now, Upcoming, Live map, Recent decisions, Since you last looked digest | V1 `Now.tsx` | BUILT + SIMULATED | NOW | S1 (all but the digest), S2 BUILT (live map is the module), S3 (digest built) |
| E03 | Work: one page with its own graph (`js/constellation/workgraph.js`, concepts 03/04/08: missions and the decisions they ask for as nodes grouped by what they wait on, project as a faint label, Review button on the first needs-you node) over the list Needs you, Active, Blocked, Done, then Pinned and Ideas; project filter chips; graph and list follow the route id, so selecting in one marks the other and opens the inspector | V1 `Work.tsx`, concepts 03, 04, 08 | BUILT + SIMULATED | WORK | S1 (no pins), S3 (done: built), B (graph and merged page) |
| E04 | Attention items (now the Needs you and Blocked sections of Work): flat Core list of approvals, verification, mission, knowledge, drift, automation, account items; V2 groups Decide, Review, Unblock | V1 `Attention.tsx`, UIA §H | BUILT + SIMULATED | WORK | S1 (`sim.js`: all listed kinds except drift), B (merged into Work; the Attention nav item is gone) |
| E05 | World: Projects and Knowledge tabs, repositories, inspections, supersession chain | V1 `World.tsx` | BUILT | SET | S1 (knowledge in the simulation only), S2 |
| E06 | Control sections: Autonomy, Automations, Resources, Sessions, Clients, Appearance, About, Emergency stop | V1 `Control.tsx`, navigation.json | BUILT + SIMULATED | SET | S1 (accounts, harnesses, automations, clients, hooks, MCP, agents), S3 (Automations, Resources, Clients, hooks, MCP and agents as the Extensions, Usage and Accounts pages), S5 done in TERM (`4` Control: accounts and usage, automations, clients with hooks, MCP and agents, security, health, appearance, about; Autonomy, Sessions and Resources are not simulated) |
| E07 | Mission inspector tabs: Outcome, Plan, Now, Evidence, Why, Timeline, Relations | V1 `Mission.tsx`, navigation.json | BUILT + SIMULATED | WORK, ATT inspector | S1 (five tabs), S3 (done: Why, Relations) |
| E08 | Other inspectors: execution (Output, Checkpoints), session (Brief, Lineage), knowledge, automation run, approval, plan, verification, route decision, policy decision, context package, project, repository | V1 navigation.json | BUILT | inspector | S3 partly (`js/inspectors.js`, `js/inspectors2.js`; session, policy decision, context package and repository not simulated) |
| E09 | Approval card: canonical action, why, consequence of reject, expiry; decide needs the approve scope and step-up | V1 `Attention.tsx` ApprovalCard, T149 | BUILT + SIMULATED | WORK, NOW, inspector | S1 (decision sheet), S3 (done: built) |
| E10 | Command bar and palette (Ctrl+K), grammar of ADR-0042 | V1 `CommandBar.tsx`, `state/palette.ts` | BUILT | CHAT | S4 built (bar, slash combobox; no Ctrl+K palette) |
| E11 | Conversation thread with cards: approval, e-stop, stop mission, route explanation, change card | V1 `Now.tsx` Conversation | BUILT | CHAT | S4 built (thread with start, confirm, approval, plan, status, remember cards) |
| E12 | Offline Now: kept missions, "as of hh:mm", Decide rows read-only | V1 `OfflineNow`, UIA §O | BUILT | NOW | S3 (done: built) |
| E13 | Live map with halo, travelling marker, hulls, depth alpha, search, legend and text mirror (Canvas 2D) | V1 `graph/` | BUILT | NOW | S2 BUILT (V2 Live draws SVG with the module: hulls, travelling marker, legend, text mirror and node table; search not built) |
| E14 | Phone: graph hidden below 600 px, the list stands in | UIA §M, V1 P18 A12 | BUILT | NOW · P | S1 (map shown small, list under it), S2 BUILT (map kept on the phone as a sparse 240 px scene on the Overview) |
| E15 | Toasts and the polite announcer (at most one per 5 s) | V1 `toast.ts`, `a11y/announce.ts` | BUILT | ALL | S1 (one status toast), S6 built: info toasts leave after 4.5 s, an error or a toast with an action stays until Dismiss (role alert for errors); the at-most-one-per-5-s announcer is not built |
| E16 | Pins and saved views | V1 `pins.ts` | BUILT | WORK | S3 (done: built) |
| E17 | Idea path stepper (Captured to Learned) | V1 `Work.tsx` IdeaPath | BUILT | WORK | S3 (done: built) |
| E18 | Digest "since you last looked", acknowledge cursor | V1 `Now.tsx` DigestSection | BUILT | NOW | S3 (done: built) |
| E19 | Fresh/stale readings with age ("no output for 12 min"), never a client timer | UIA §D, A55 §3 | BUILT + SIMULATED | WORK, NOW, TERM | S1 |
| E20 | Obligation groups Decide, Review, Unblock; at most 3 Decide rows on Now; acknowledge and snooze need a Core ADR | UIA §H, PLAN §5 | DESIGNED | ATT, NOW | S3 (groups kept), S6 built the j and k keys on cards and rows; acknowledge and snooze stay unbuilt (need a Core ADR) |
| E21 | Keyboard model: Enter primary, Ctrl+Enter secondary, j/k, `?` lists keys | PLAN U2-c | DESIGNED | ALL · D | S6 built: j and k move through rows and cards, Enter acts on the focused row or card, Space opens a row, Esc closes the help, menu, ask-first question or sheet, `?` lists the keys in EN and IT and states the focus order, visible focus is 3 px `#FFF3CF` in dark; Ctrl+Enter is not built (a one-key Reject is unsafe) |

## F. Chat and slash commands

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| F01 | Tell opens a chat overlay (phone sheet), placeholder "Tell Archeus what you need…", SIMULATED tag on every reply | PROTO build steps 1 to 3 | PROTOTYPED + SIMULATED | NOW, CHAT | S4 built (`js/app.js`, `js/chat.js`, `js/chat-cards.js`) |
| F02 | Message creates: message, mission, idea, remembered preference, feedback candidate, mission thread, narrowing directive | T149 §1 | BUILT | CHAT | S4 built (message, mission, idea, remembered preference, feedback candidate) |
| F03 | Under the `standard` profile a new-work message starts and dispatches without a card (G1, an owner-rule breach) | T149 §1, §4 | BUILT (flagged) | CHAT | S4 built (a chat mission is held; labelled, never shown as owner-approved) |
| F04 | General (non-project) questions cannot be answered today (G5); replies are scripted | T149 §2, §4 | DESIGNED | CHAT | S4 built (scripted General answers, labelled) |
| F05 | Create a project from chat has no path in V1 | T149 §1 | PROTOTYPED | CHAT | S4 built (labelled simulated) |
| F06 | Comment on a mission or plan: no comment object, only messages | T149 §1 | BUILT (limit) | CHAT | S4 built (a comment is a message) |
| F07 | Route classes: 58 READ, 6 CREATE, 36 PROPOSE, 7 NEVER of 107 routes; chat calls READ and CREATE directly, drafts PROPOSE as cards, never calls NEVER | CAT | DESIGNED | CHAT | S4 partly (`slash.js`, `chat-engine.js`: local command classes, not the 107-route catalogue) |
| F08 | NEVER routes: device launch and pair, approvals decide, verifications decide, missions review | CAT | DESIGNED | CHAT | S4 (`slash.js`, `chat-engine.js`: pair refused; approval and review commands open cards, decide nothing; no Core routes called) |
| F09 | Stop mission: confirm card; e-stop: card then control scope; pause all, resume all, reprioritise: direct, no card | T149 §1 | BUILT | CHAT | S4 built (stop, estop: two steps; pause, resume: card) |
| F10 | Approve from chat only on the card on screen with its hash; a bare "approve" is declined | T149 §1 | BUILT | CHAT | S4 built (bare approve declined; card needs a step-up) |
| F11 | Slash menu: `/` opens a list above the bar; `?` lists by class; `//name` sends text; keyboard combobox (Up, Down, Tab, Enter, Escape, `aria-activedescendant`) | T153, PROTO slash.js | PROTOTYPED | CHAT | S4 built (combobox: Up, Down, Tab, Enter, Esc, aria-activedescendant, five rows then +N more, recents, `//`) |
| F12 | READ and NAVIGATE: /help /status /usage /projects /missions /needs /digest /ideas /plan /why /search /trace /replay /open /focus /clear /theme /motion (Italian aliases /aiuto /stato /usa /progetti /missioni /attesa /riepilogo /idee /piano /perche /cerca /traccia /rigioca /apri /vai /pulisci /tema /movimento) | T153 §3.1, PROTO | PROTOTYPED | CHAT | S4 built (all 18, Italian aliases; READ and NAVIGATE are local, not recorded) |
| F13 | CREATE: /mission /idea /feedback /remember /tell /general (/remember is a confirm card naming the scope) | T153 §3.2, PROTO | PROTOTYPED | CHAT | S4 built (/remember is a confirm card naming the scope) |
| F14 | PROPOSE (card or two-step confirm, decides nothing): /start /stop /estop /pause /resume /cancel /review /approve /reject /account | T153, PROTO | PROTOTYPED | CHAT | S4 built (/start /stop /estop /pause /resume /cancel /review /approve /reject; /account unavailable) |
| F15 | Refused before sending: extra arguments, bad choices, unknown names, text that looks like a secret (`sk-`, `ghp_`, `AKIA`, `Bearer `) | PROTO README slash | PROTOTYPED | CHAT | S4 built (extra arguments, bad choices, unknown names, secrets) |
| F16 | `@` mentions; 2 s duplicate-send prompt and rate limit (Core side) | T153 | DESIGNED | CHAT | S4 built (`@` mentions, 2 s duplicate prompt; rate limit is Core side, not built) |
| F17 | Phone chat sheet follows `visualViewport` (keyboard) and expands | PROTO step 2 | PROTOTYPED | CHAT · P | S4 built (visualViewport, simulated keyboard, Expand, Back) |
| F18 | Chat delay and error fixtures, General routing, Review plan | PROTO steps 4 to 6 | PROTOTYPED | CHAT | S4 built (slow and failed send fixtures, General routing; Review plan stays on the decision sheet) |
| F19 | Usage in chat: `/usage` answers `unknown` until T-154 | T153 owner answers | PROTOTYPED | CHAT | S1, S4 built |
| F21 | Chat page: one centred thread under a bar (scope picker, mission picker, mission state in one line, link to what waits for you, More menu for privacy and the simulation switches) and three sections (Conversation, Receipts, Context); the scope picker is the conversation list (General, then projects that need you, then the rest, searchable above 8); starter based empty state; the composer is one component on the page, the Overview dock and the phone sheet | owner 2026-10-28 | PROTOTYPED + SIMULATED | CHAT | Replaces the rail, the context column, the pins and the page title; `js/chat.js`, `js/picker.js`, `css/chat.css`, `css/picker.css`; delivery stays project scoped |
| F22 | Chat motion: arrival of a new message (6 px, 180 ms), height change of an inline card, working dots, tab underline (180 ms), picker open (100 ms fade); all transform and opacity, static under Reduced motion | owner 2026-10-27 | PROTOTYPED | CHAT | Page and picker CSS; OS and app Reduced motion honoured |
| F20 | Subscription token read by `claude_sessions/usage.py` conflicts with AGENT-RULES item 6 (G2) | T149 §4 | BUILT (flagged) | none | owner decision, never shown |

## G. Replay and Recovery

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| G01 | Eight Replay categories: INTENDED, AUTHORIZED, RECORDED, MAY-HAVE-TAKEN-EFFECT, UNCERTAIN, SUSPENDED, RECONCILED, NONE; plus UNKNOWN for "cannot tell" | RC, T148 | DESIGNED | REP | S4 built (all nine, with definitions) |
| G02 | 130 states over 19 machines classified (INTENDED 29, RECORDED 46, SUSPENDED 16, MAY-HAVE-TAKEN-EFFECT 12, AUTHORIZED 9, UNCERTAIN 5, RECONCILED 5, UNKNOWN 5, NONE 3) | RC Part A | DESIGNED | REP | S4 built (130 states, 19 machines, totals pinned by a test) |
| G03 | `GET /v1/missions/{id}/replay` from rows, not the event log; a state with no entry answers UNKNOWN | T148 R1 | DESIGNED | REP | S4 built (read from rows and events; no entry answers UNKNOWN) |
| G04 | Evidence rows labelled by real strength (checkpoint lists capped at 30 are summaries, an ERROR verification is not a verdict) | T148 R2 | DESIGNED | REP | S4 built (evidence labelled Recorded, Reported, Summary, NOT RECORDED, UNKNOWN) |
| G05 | `settled_by` core, device or unknown from the event actor, never a new record | T148 R3 | DESIGNED | REP | S4 built (read only, with its reason) |
| G06 | Retention honesty: events kept 180 days; a pruned range answers UNKNOWN with a reason, never "nothing happened" | T148 R4, RC gap 6 | DESIGNED | REP | S4 built (180 days, extension not built, pruned answers UNKNOWN) |
| G07 | "NOT RECORDED": external effects, starting digest, operator reconciliation, complete history, reasoning transcript, file snapshots, cost provenance, confinement proof | RC gaps, PROTO REPLAY_GAPS | PROTOTYPED | REP | S4 built (eight gaps, NOT RECORDED) |
| G08 | Five example rows (task initiated, files changed, tests passed, external response lost, workflow suspended) | RC Part B | DESIGNED | REP | S4 built (five example rows with strengths) |
| G09 | Prototype Replay: 13 source-labelled entries for Fix date test, pointer and keyboard cursor, a failed verification and a LOST execution, no autoplay | PROTO README | PROTOTYPED | REP | S4 built; 2026-10-27 timeline-first redesign implemented, runtime validation pending: time-positioned category ticks, six-station mission spine, nine count filters, event stack and adjacent evidence with source record; phone evidence sheet; Quiet/Reduced motion disables transitions |
| G10 | Recovery choices create explicit approval cards only; approval changes a receipt, never the evidence; retry and owner-question drafts editable | PROTO README | PROTOTYPED | REP | S4 built; 2026-10-27 recovery placed after collapsed reference section, every option and proposal labelled SIMULATED; existing fixture approval behavior retained |
| G11 | Never claim an external effect can be reversed; no operator spawn, adopt or retry; no second spawn (retry is a new execution id) | T148 N7, `harnesses/base.py` | DESIGNED | REP | S4 built (never list on the recovery panel) |
| G12 | Four other meanings of "replay" stay separate: router replay, stream replay from Last-Event-ID, queued command resend, Trace tab two-clock playback | T148 N4 | BUILT | none | naming only |
| G13 | Mission Trace tab (P21 slice C-read) | BOARD T-119 | BUILT | WORK inspector | S3 (done: Timeline tab today) |

## H. Platform facts shown as simulated state

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| H01 | Mission machine, 17 states, with edges from `states.py`; `held_from` on BLOCKED and PAUSED | ST, A54 | BUILT + SIMULATED | WORK, ATT, spine | S1 (`sim.js` edge table, tested) |
| H02 | Execution machine (INTENT to ENDED_*, LOST, adopted, reconciled_kill), task, plan, approval, verification, review machines | ST | BUILT + SIMULATED | WORK inspector, REP | S1 |
| H03 | Account health states (UNVERIFIED, AVAILABLE, CONSTRAINED, LIMITED, DEGRADED, OPEN, UNAUTHENTICATED) and usage windows; unknown shown as "unknown", never 0 | ST, UIA, BOARD T-125 (review branch) | states BUILT; consumption read on a review branch + SIMULATED | ACC | S1, S3 (done: rings that empty, the 20% line, per-account, climbing with the simulation) |
| H04 | Spawn breaker O7: per harness, trips at 3 failures in 10 min, doubling wait 15 s to 5 min, half-open after 5 min, visible as "cannot start" | BOARD T-106 | BUILT on branch fix/t106 (in review, production dispatch switch off) + SIMULATED | SEC, HLT, WORK | S1 (inject a spawn failure, dispatch waits), S3 (done: built) |
| H05 | Execution quiet reading ("no output for N min") and LOST then adopted recovery | A55, ST, BOARD T-125/T-128 | LOST and adopted BUILT in ST; the quiet reading and activity chip BUILT on review branches + SIMULATED | WORK, NOW | S1 |
| H06 | Verification pass and fail; failed verification replans; replan budget then BLOCKED | ST, BOARD | BUILT + SIMULATED | WORK, REP | S1 |
| H07 | Hook asks before an action: execution AWAITING_APPROVAL, approval card, reject blocks the mission | ST, T149 | BUILT + SIMULATED | ATT (trigger an approval) | S1 |
| H08 | Automations (ENABLED, PENDING_APPROVAL, SUSPENDED by the loop guard), schedule triggers and next_run | ST, BOARD T-129 | BUILT + SIMULATED | ACC, ATT | S1 |
| H09 | Hooks, MCP servers and agents managers (lists, enable and disable) | V1 Control, BOARD T-099 | BUILT (lists) + SIMULATED | ACC | S1 (lists), S3 (done: Extensions page, switches with confirm, details sheet, last run and calls from the simulation), S5 done in TERM (lists in `4` Control; no enable or disable); overhaul 2026-10-28 (second pass): a state sentence (needs you, off), a Needs you band only when something waits, one tab per kind (Hooks, MCP servers, Agents, Automations, Clients) with a count and a dot where something needs you, one 64 px row for every kind (name and what it does, status word only where it says more than On or Off, last activity as Today 08:34 or Never, a switch or one action in a fixed 96 px column), the whole row opening its sheet, search above 12 items, the chosen tab kept for the session, arrow keys between tabs, Undo in the toast after a switch-off |
| H10 | Accounts and models: harnesses, per-account usage, models by tier | BOARD T-125, PLAN | BUILT + SIMULATED | ACC | S1, S3 (done: Accounts page with failover order, default model, per-project launch settings with a live preview; Usage page) |
| H11 | Clients (paired devices) with revoke | V1 Control, BOARD | BUILT + SIMULATED | ACC | S1, S3 (done: Clients rows and a details sheet; revoke stays a step-up note) |
| H12 | Knowledge items (CANDIDATE, CONFIRMED, RETRACTED, SUPERSEDED), confirm or reject | ST, V1 World | BUILT + SIMULATED | WORK, SET | S1 (candidates under Needs you on Work) |
| H13 | Ideas with their own states | ST, V1 Work | BUILT + SIMULATED | WORK | S1 |
| H14 | P20 security and isolation (PV-20 AppContainer, broker, origin gate): physical reach not built in V1, switches off | BOARD T-131 to T-138 | DESIGNED | SEC | S1, S3 (done: two boundaries, isolated and not isolated, eight boundaries, privileges, switches, log), S5 done in TERM (`g s`, same list and words) |
| H15 | P21: trace, health (Control, About), activity chip, schedules, search, notifications, privacy | BOARD T-118 to T-130 | trace, search and notifications merged at f483f87; provenance, health, activity chip and schedules built on review branches (T-130 integrates) | HLT, WORK | S1 (Health checks derived from readings, unknown stays unknown), S3 (done: built) |
| H16 | Usage limits and Pause all, Resume all, Emergency stop | V1 Control, T149 | BUILT | SET, NOW | S3 (the usage line and failover rules), integration (Pause all, Resume all and Emergency stop: one sim action each, `pause_all`, `resume_all`, `estop`, used by the Settings page, the terminal `E` key and the `/estop` card; Emergency stop ends every running execution and leaves each mission Blocked as "Emergency stop"; re-arming and a dispatch block are not modelled) → S6: re-arm and the dispatch block are modelled (owner decision 2026-10-26); the stop can be engaged while nothing runs; Pause all, Resume all and Emergency stop with an ask-first step are also on Now |
| H17 | Themes in V1: dark and light with contrast aliases; the "6 themes" were confirmed in VL §1 | V1 tokens.json, VL | BUILT + SIMULATED | SET | S1 |

## I. Prototype features (clients/v2-prototype)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| I01 | Overview hub with chat bar, zoomable projects (`#/now/harbor`) | PROTO README | PROTOTYPED | NOW | S2 |
| I02 | Mission screen: chain, phase stepper, tabbed inspector, Tell and Stop | PROTO README | PROTOTYPED | WORK | S3 (done: built) |
| I03 | Shared: agents and devices as endpoints, tabbed inspector | PROTO README | PROTOTYPED | SET | S3 (done: built) |
| I04 | Plan approval screen: What, Why, Core consequence, Approve, Request changes, Reject; local receipt only | PROTO README | PROTOTYPED | ATT | S1 (Approve, Reject), S3 (done: built) |
| I05 | Decision sheet with two-step confirm on the phone | PROTO README | PROTOTYPED | ATT · P | S1 (one step), S3 (done: built) |
| I06 | Fixtures: 3 projects (Archeus, Notes, Ideas) and 5 missions (Search provenance, Fix date test, Docs refresh, Offline capture, Export backup) | PROTO app.js | PROTOTYPED | ALL | S1 (extended to 8 missions) |
| I07 | Terminal screens (overview, mission, replay) as a text grid; keys 1 2 3, p, y, Left and Right | PROTO README | PROTOTYPED | TERM | S1 (Now, Work, Attention, Replay), S5 done (also World, Control, mission with seven tabs, the decision card, help; keys follow the real TUI, see section N) |
| I08 | Phone frames: hub, Review, slim sheet, chat sheet | PROTO README | PROTOTYPED | P | S1 (real layout instead of art) |
| I09 | Concept art rasters at fixed pixel coordinates, `CONCEPT_LAYOUT` tables | PROTO | PROTOTYPED | none | not ported (owner complaint) |
| I10 | Hit probe by `elementFromPoint`, 44 pt phone and 48 CSS px desktop | PROTO `tools/v2_hit_probe.py` | PROTOTYPED | ALL | S1 (`tools/v2_live_layout_probe.py`) |
| I11 | Service worker and PWA | PROTO sw.js | PROTOTYPED | none | optional, default off |

## J. Responsive shell and the tool chrome (new in V2 Live)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| J01 | Desktop at 1024 and wider: rail, main, optional right inspector | owner brief | SIMULATED | ALL · D | S1; overhaul 2026-10-28: the safety status is top-left in the top bar, the rail has three labelled groups (Work: Overview, Work, Chat, Replay, Terminal view; Govern: Security, Health, Usage; Configure: Accounts, Extensions, Settings), only Work carries a count (what needs you), and it lists at most 4 projects (needs you first, then running, the selected one always) with an All N projects row; the Tools tray shares the SIMULATED row instead of adding one |
| J02 | Tablet 600 to 1023: collapsible rail, inspector as a right sheet | owner brief | SIMULATED | ALL · T | S1 |
| J03 | Phone under 600: Tell, Places and Stop bar, navigation in the Places sheet, thumb-reachable decisions | owner brief, UIA §M | SIMULATED | ALL · P | S1, S6 done (`js/phone.js`, `css/phone.css`); overhaul 2026-10-28: bar 64 px, Places sheet slides up once (180 ms, none under Reduced motion), project list capped at 5 with an All N projects row |
| J04 | Terminal view as a device switch and as `#/terminal` | owner brief | SIMULATED | TERM · X | S1 |
| J05 | Device preview: Auto, Phone, Tablet, Desktop, Terminal; frames scale down to fit | owner brief | SIMULATED | SHELL | S1 |
| J10 | All devices: phone, tablet, desktop and terminal side by side, each a real document at its own width in an iframe, all sharing the parent's simulation instance | VLD (Devices) | SIMULATED | SHELL | S1 |
| J11 | Italian switch (`js/i18n.js`): the DOM is translated by exact string after each render, with regex rules for counts and spine sentences | VLD (Language) | SIMULATED | ALL | S1 |
| J12 | Decision notes: `.dnote` blocks naming the SPEC row each choice implements; toggle persisted | VLD (Audience) | SIMULATED | ALL | S1 |
| J13 | More remains at `#/more`; phone navigation uses Places (bottom bar: Tell, Places, Stop) | owner brief | SIMULATED | MORE, SHELL · P | S1, S6 done (`js/views2.js`, `js/phone.js`) |
| J06 | Theme menu, Reduced motion toggle, simulation menu in a thin toolbar | owner brief | SIMULATED | SHELL | S1 |
| J07 | Fonts: Libre Caslon Text VF copied from the prototype with its OFL notice (127 KB) | VL §6 | SIMULATED | NOW | S1 |
| J08 | Layout probe: 14 viewports by every route and overlay by dark and light | owner brief | SIMULATED | none | S1 |
| J09 | localStorage only inside try/catch; URL parameters `theme`, `device`, `motion`, `sim`, `speed`, `seed`, `advance` | owner brief | SIMULATED | SHELL | S1 |
| J14 | Toolbar Notes toggle: independent `heronotes` switch for Overview and Map, default off; global notes switch still applies | `js/app.js`, `js/store.js`, `css/shell.css` | SIMULATED | SHELL, NOW | S6 done |
| J15 | Device and Theme trays: radio choices, device size hints, scaling note and System / forced-colours note | `js/app.js` | SIMULATED | SHELL | S6 done |
| J16 | Extra URL options: `story=calm`, `embed=1` (shared parent simulation); terminal `look=app/ansi/hc/mono`, `ascii=1`, `sr=1` (Read) | `js/app.js`, `js/tui/view.js` | SIMULATED | SHELL, NOW, TERM | S6 done |

## K. Simulation (sim.js)

| ID | Item | Where | Slice |
|---|---|---|---|
| K01 | Seeded and deterministic: same seed and calls, same event log, whatever the chunking | all | S1 (tested) |
| K02 | Controls: play, pause, speed x0.5 to x8, trigger an approval, inject an execution failure, break the harness (spawn), Go offline / Reconnect, reset | SHELL, SET | S1 (`js/views.js`, `js/app.js`) |
| K03 | Events a UI subscribes to, with Core event names (`mission.state_changed`, `approval.requested`, `execution.progress`) | all | S1 |
| K04 | Owner actions go through the same edges: approve, reject, accept, request changes, unblock, resume, replan, pause, cancel, confirm, retract, enable | ATT, WORK | S1 |
| K05 | Bounded log with a pruned flag, so Replay can say UNKNOWN | REP | S1 |
| K06 | Scripted story: a theme audit mission planned and auto-approved; a quiet execution lost and adopted; a verification that fails once; a plan waiting for the owner; a mission blocked on a question | all | S1 |

## M. Areas the owner requires in V2 Live (VLD, "Areas in V2 Live: all four")

| ID | Area | Screens that show it | Route | Slice |
|---|---|---|---|---|
| M01 | Now, Work, Attention, spine, decisions | NOW, WORK (graph, Needs you, Active, Blocked, Done), inspector and decision sheet | `#/now`, `#/work/<id>` (decisions too: `#/work/a-1`; `#/attention/<id>` redirects here) | S1 shell and lists, S2 Now, S3 mission and decisions |
| M02 | Chat and slash commands | CHAT | `#/chat` | S1, S4 built |
| M03 | Replay | REP | `#/replay/<id>` | S1, S4 built |
| M04 | Security: posture sentence, held action decisions, project policy, boundaries, security events, emergency controls; physical isolation explicitly not built | SEC | `#/security`, `#/security/policy`, `#/security/boundaries`, `#/security/activity`, `#/security/emergency` | S1, S3; 2026-10-27 posture-first structure; 2026-10-28 overhaul (state sentence first, privileges grouped by outcome and sorted worst first, approval mode grouped by mode, with projects that use the default under "Default", so 100 projects stay one screen, Emergency controls in a sticky side rail). S5 in TERM (`#/terminal/security`) |
| M05 | Health: checks and readings | HLT | `#/health`, `#/health/attention`, `#/health/unknown`, `#/health/ok` | S1, S3 (done: built) |
| M06 | Usage meters, accounts and models | ACC | `#/accounts` (`/models`, `/failover`, `/launch`), `#/usage` (`/windows`, `/history`) | S1, S3 (done: #/usage and #/accounts), S5 done in TERM (`#/terminal/accounts`) |
| M07 | Hooks, MCP servers, agents managers; automations; clients | ACC | `#/accounts` | S1, S3 (done: #/extensions), S5 done in TERM (`#/terminal/clients`) |
| M08 | Terminal view | TERM | `#/terminal`, device switch | S1, S5 done (section O) |
| M09 | Themes (six looks), reduced motion, language, device preview | SET, SHELL | `#/settings`, toolbar | S1, S6 done (see A04 and B05); overhaul 2026-10-28: sections with a left nav (Safety, Appearance, Prototype, About; a tab row on a phone), one shown at a time and linked as `#/settings/<section>`, Safety first |

## N. S3 additions (2026-10-26)

Routes added: `#/usage`, `#/extensions`; any inspector opens on `#/<area>/<id>` (ids: m- mission, t- task, x- execution, p- plan, a- approval, v- verification, r- review, k- knowledge, i- idea, prj- project, au- automation, acc- account, mdl- model, h- hook, mcp- MCP server, ag- agent, d- client, bk- breaker, sec- boundary, chk- health check, rd- route decision).

| ID | Item | Status | Where | Devices |
|---|---|---|---|---|
| N01 | Mission inspector: Outcome, Plan, Now, Evidence, Why, Timeline (bounded attempts), Relations; pin | SIMULATED | inspector | P T D |
| N02 | Task, route decision, execution (Output, Checkpoints), plan, verification, review, idea path, knowledge, project inspectors | SIMULATED | inspector | P T D |
| N03 | Decision sheet: What, Why, Core next, Policy, Relations; Approve, Request changes, Reject; two-step confirm on a phone, Reject always twice | SIMULATED | ATT, inspector | P T D |
| N04 | Offline: stale read with the last-seen time, outlined spines, Decide rows read only, Reconnect (Sim menu, "Go offline") | SIMULATED | NOW, WORK, ATT | P T D |
| N05 | Digest: since you last looked and today, mark as seen | SIMULATED | NOW | P T D |
| N06 | Security in five parts, each its own link: Overview (held action cards with Allow once / Deny, a tally of what Archeus may do, the three weakest boundaries, the latest 5 events), Policy (nine actions with scope and source, approval mode by project, read only), Boundaries (eight boundaries, policy notes, switches), Activity (every security event, 12 then Show all, relative time with the exact time on hover), Emergency (stop and re-arm, spawn breakers); the posture sentence and the isolation warning stay on every part; Re-arm links to Emergency | SIMULATED | SEC | P T D; layout probe 0 defects 2026-10-28 |
| N07 | Health as a status filter that is a set of links: All, Needs attention, Unknown, OK (plain totals on the tabs, a dot on Needs attention, "Showing 1 of 6" under a filter, an empty state with Show all checks); a header with Last run (relative, exact on hover), Stale after 30 minutes, and Run all; each row opens to cause, fix, a changed-from line, Checked time, Check again and Readings; the Fix action is the primary button; driven by the simulation | SIMULATED | HLT | P T D |
| N08 | Usage in three parts, each its own link: Accounts (one row per account with two 56 px rings, state pill, reset time, and a forecast line "At this rate you reach the limit at HH:MM"), Windows (every account per 5 hour window and per week, and the 20% line with a link to Failover), History (the last hour as a sparkline per account); first 12 rows then Show all, "Showing 12 of 48"; unknown stays unknown; climbing story | SIMULATED | USE | P T D |
| N09 | Accounts in four parts, each its own link: Accounts (failover order, a login belongs to you and no token is shown), Models (default model), Failover (each switch saves as you flip it; switching one off offers Undo), Launch settings (one Default row and a row only for a project whose settings differ; Use the default offers Undo; a select gives another project its own); the sentence names the account that takes the next mission | SIMULATED | ACC | P T D |
| N10 | Extensions: hooks, MCP servers, agents, automations, clients, each with a switch and a details sheet | SIMULATED | EXT | P T D |
| N11 | Mission graph uses the map's shared node art and recorded relations; shown on desktop and phone, hidden on tablet | SIMULATED | inspector (`js/inspector-mission.js`, `js/constellation/scene.js`, `css/inspector.css`) | P D |

S3 story additions (sim.js, additive): the Codex spawn breaker trips at +8 min and recovers; the personal 5 hour window reaches 94% at +12 min; the work week reaches the 20% line at +24 min; a plan decision can be sent back (Request changes).

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

## O. Terminal view (slice 5)

The terminal renders the same simulation as the GUI, in the same words (checked by `test/tui.test.mjs`, the "parity" tests). Code: `js/tui/` (cells, screens, controller, cmd: DOM free; view: DOM), `css/tui.css`. Key map: the real TUI's (`archeus/cli/tui/app.py`: 1 2 3 a 4, j k and arrows, Enter, Esc, Tab, `[ ]`, `:`, `?`, `q`, upper case = actions, y confirms) plus the concept's (`/` find, `g` places, `t` tell, `b` back).

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| O01 | Now: state line (nonzero need-you, running and stopped counts; "Nothing needs you." when empty), the constellation in text (Core, project hubs, mission nodes with the state glyph and `▲` for a live execution, box lines, columns or a tree by width), Needs you, Happening now, Upcoming, Recent, Conversation | concept 13, E02, A03 | SIMULATED | TERM | S5 done (`sim.js`, `js/tui/screens.js`) |
| O02 | Six-station spine as `✓✓◆○○○ Approval` on every row, station labels on the mission and decision cards, the generated sentence for a screen reader | A54 §7 (D10) | SIMULATED | TERM | S5 done |
| O03 | Work (groups by what a mission waits on, ideas), World (projects, what Archeus knows), Attention (Decide, Review, Unblock) | E03, E04 | SIMULATED | TERM | S5 done |
| O04 | Mission inspector with the seven real tabs (o Outcome, p Plan, n Now, e Evidence, w Why, t Timeline, r Relations); Why built from `reason`, `held_from`, the approval and a lost execution, never guessed | E07, V1 `Mission.tsx` | SIMULATED | TERM | S5 done |
| O05 | Decision card (what, why it asks, what Core does next, expiry, where the mission is); A approve and R reject ask `y` first, any other key cancels | E09, V1 TUI | SIMULATED | TERM | S5 done |
| O06 | Mission actions by state (P pause, R resume or replan or answer and unblock, A accept, C request changes, X cancel, E emergency stop = pause every running mission), all through the same sim edges | K04 | SIMULATED | TERM | S5 done |
| O07 | Replay: nine categories as text with a count per category, the meaning of the selected one, trigger, settled by, record, NOT RECORDED, the pruned note; `n` and `N` change mission | G01 to G07 | SIMULATED | TERM | S5 done |
| O08 | Control: Accounts and usage (text meters, `unknown` never 0), Automations, Clients with hooks, MCP and agents, Security, Health, Appearance, About; Tab cycles sections; `g s`, `g h`, `g u` | H03, H08, H09, H14, H15 | SIMULATED | TERM | S5 done |
| O09 | Command line (`:` or `/`): go to a place or a mission, slash commands with completion (English names, Italian aliases, the table in `sim.js`), plain text to Archeus; the reply, its cards and links shown as an overlay with `y`, `n` and Enter; secret-looking text refused | F11 to F15, T153 | SIMULATED | TERM | S5 done |
| O10 | Help overlay (`?`) and places overlay (`g`); key hints and navigation in Italian when the language is Italian | A24 | SIMULATED | TERM | S5 done |
| O11 | Responsive character grid: 40, 80, 120 and 160+ columns (tiers at 60, 110 and 150 columns), whole pixels per cell, two panes with Tab from 110 columns, rows follow the height, deep links `#/terminal/<screen, section, mission or approval id>` | A02, J04 | SIMULATED | TERM | S5 done |
| O12 | Looks: App colours (follows the six modes), ANSI 16, High contrast, Monochrome (reverse video for the selection); ASCII only (presentation.json twins, 1:1 text folding); Windows forced colours through system colours | A04, B05, B07 | SIMULATED | TERM | S5 done |
| O13 | Reduced motion: nothing animates in the terminal; the one slow mark is the core glyph swapping between `◎` and `◉` every 3 s under full motion with live work, static under Quiet (the real TUI does not move at all: owner question) | A05, A06, C05 | SIMULATED | TERM | S5 done |
| O14 | Linear mode (Read): the screen as headings and lists, glyphs spoken as words, no box characters, the selection marked with `aria-current`; a polite live region for the selection and the status line; Esc then Tab leaves the grid (no keyboard trap) | UIA §P | SIMULATED | TERM | S5 done |
| O15 | Mouse and touch: click selects and a second click opens; tabs, navigation and action text are clickable; wheel moves; a key bar of 44 px buttons below 900 px with the actions of the selected thing; a real input for the command line | A11 | SIMULATED | TERM | S5 done |
| O16 | Window frame (dots, name, Colours, ASCII, Read, Keys) in the V2 Live visual language: solid surfaces, 3 px focus ring, 2 px hairline in high contrast | A09, B15 | SIMULATED | TERM | S5 done |

## P. S6 additions (2026-10-26)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| P01 | Now counters in the Details strip: needs you, running, stopped, verifying; phone hides verifying and zero stopped counts | concepts 09, 10 | SIMULATED | NOW · P/T/D | S6 done (`js/view-now.js`, `css/now.css`) |
| P02 | Phone mission inspector spine in two rows of three with the short names | concept 12, VLD (narrow inspectors) | SIMULATED | WORK, ATT · P | S6 done |
| P03 | "No Undo. Decision cannot be changed." banner with a warning icon on an open decision | concept 11 | SIMULATED | ATT, NOW | S6 done |
| P04 | Pause all, Resume all and Emergency stop in the top-bar safety dialog and Settings; ask-first for the stop, Esc cancels, re-arm in place | H16, VLD (E-stop) | SIMULATED | SHELL, SET | S6 done (`js/app.js`, `js/views.js`, `js/view-settings.js`) |
| P05 | Tell, Places and Stop as three round buttons on the phone | concepts 09, 10 | SIMULATED | SHELL · P | S6 done (`js/phone.js`, `css/phone.css`; Stop becomes Re-arm when engaged) |
| P06 | Toasts: info leaves after 4.5 s, errors and toasts with a link stay until an explicit Dismiss; a toast with an Undo leaves after 7 s; one toast at a time (a new one replaces the old); pointing at or focusing a toast keeps it, and it leaves 2 s after the pointer does | VLD (toasts, 2026-10-26) | SIMULATED | ALL | S6 done; 2026-10-28: sits in the top-bar band left of Tell and Stop at 1280 px and wider (under the bar otherwise), enters in 100 ms and leaves in 180 ms (opacity and a 6 px move), no motion under Reduced motion |
| P07 | Keyboard help overlay (`?`) in EN and IT with the shortcut list and the focus order | E21 | SIMULATED | ALL · D | S6 done |
| P08 | All devices: panes do not overlap, a click in a pane hits that pane's content, one simulation drives all panes (`tools/v2_live_alldevices_probe.py`) | A01, J-section | SIMULATED | ALL, SHELL | S6 done |
| P09 | Forced colours: a selected item has a 3 px Highlight line; state icons use ink | B05 | SIMULATED | ALL | S6 done |
| P10 | Package: `Archeus-V2-Live.zip` from `tools/v2_live_package.py` (the app folder, `start.cmd`, `README-FIRST.txt`) | owner, 2026-10-26 | SIMULATED | SHELL | S6 done |
| P11 | Italian review list of every builder-written Italian string, all marked to review (`IT-REVIEW.md`) | VLD (Italian) | SIMULATED | ALL | S6 done |
| P12 | Calm Now: `?story=calm` seeds finished work; "Nothing needs you." selects the calm band with Tell, Today and known projects | concept 07, `sim.js` | SIMULATED | NOW · P/T/D | S6 done (`js/view-now.js`) |
| P13 | Phone Overview Review card: first Decide or Review item, title, origin, What, Why for approvals, link to the decision or mission | `js/view-now.js`, `css/now.css` | SIMULATED | NOW · P | S6 done |
| P14 | Places sheet: destinations, Terminal, projects and the count of what needs you (on Work); modal dialog, close button, Esc and scrim dismiss | `js/phone.js`, `js/app.js` | SIMULATED | SHELL · P | S6 done |
| P15 | Safety status opens a dialog: Not stopped / accepts new work or Stopped / new work blocked; focus kept inside, Esc and outside click dismiss | `js/app.js` | SIMULATED | SHELL | S6 done |
| P16 | One state vocabulary: pending, active, awaiting you, error, complete, stale and cancelled, each a glyph and a word, coloured by tone (colour never alone); `stateMark(kind, label?)` and `mark(tone, word)` in `js/views.js`, the table in `js/state-vocab.js`. Machine states keep `badge()` and their own words from `present()`. Extensions rows use `mark` | research 2026-10-28 (Linear agent states) | SIMULATED | ALL | node test |
| P17 | Command palette: Ctrl+K or Cmd+K (also the Search button in the top bar) opens a centred dialog with 48 px rows; groups Recent (used this session), Pages, Actions (Stop all, Pause all, Resume all, Tell Archeus, Settings: Safety, Appearance, Prototype, Language, Keyboard shortcuts) and Projects (searched across all, five shown without a query); pinned first, arrow keys, Enter runs, Esc closes and gives focus back; opens in 100 ms (opacity and scale .98 to 1), nothing moves under Reduced motion; not in the terminal view, which keeps Ctrl+K for the shell; Stop all asks to confirm like the Stop button | research 2026-10-28 (Raycast, Superhuman) | SIMULATED | ALL | node test (ranking), browser check |
| P18 | Times as the owner reads them: Today 08:34, Yesterday 23:10, Mon 14:20 within the week, then a date, Never; the exact local time is the title (hover); `js/time-model.js`. Used by Extensions; the simulated day is Wednesday 2026-10-28 | research 2026-10-28 | SIMULATED | ALL | node test |

## Q. Overview rework (2026-10-27, owner feedback after the n/q builds)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| Q01 | Details is a sheet over the scene, never a squeeze: a right side sheet at 900 px and wider, a bottom sheet under that, the status strip stays the bottom edge; the map lays itself out in the area that is left; rows stack so no column collapses to a letter per line; Esc and the Details button close it; the layout probe fails a panel or row column under 120 px and a squeezed scene (`now~details`) | owner 2026-10-27 ("details is broken") | SIMULATED | NOW · T/D | `js/view-now.js`, `css/now.css`, `tools/v2_live_layout_probe.py` |
| Q02 | Tell dock on the Overview: anchored at the bottom centre of the scene (about 760 px or 92 percent), slim single line (destination chip, field, slash, Send), flat translucent ground fill with a hairline and no blur, grows upward for the slash menu and replies, the map reserves its footprint, phone keeps the Tell, Places, Stop bar | owner 2026-10-27 | SIMULATED | NOW · T/D | `js/chat.js` (`dockNode`), `js/view-now.js`, `css/now.css` |
| Q03 | Liveliness (V2 Live only, ADR-0055 still binds the real app): seeded drift of nodes (1.5 to 3 px, 9 to 17 s), soft ring on needs-you and running nodes (3.6 s), travelling markers on running relations (3.7 to 7 s); transform or opacity only; only for a playing simulation with full motion in a visible tab and map; never in the calm scene; Reduced motion shows the static twin; no state by motion alone | owner 2026-10-27 ("a bit more liveliness") | SIMULATED | NOW | `js/constellation/map.js`, `map.css`, layout probe motion invariant |
| Q04 | Nodes lift 7 percent under the pointer and keyboard focus, new nodes grow in from 90 percent over 160 ms with a 30 ms stagger, the hairlines of the selected or hovered node brighten | owner 2026-10-27, Emil Kowalski craft notes (advice only) | SIMULATED | NOW | `js/constellation/map.js`, `map.css` |
| Q05 | Map is not a menu item: Overview is the map (zoom out, zoom in and Fit stay on it, in a column at the bottom right); `#/map` redirects to `#/now`; 11 destinations in the sidebar and the Places sheet | owner 2026-10-27 ("map in menu is obsolete") | SIMULATED | SHELL, NOW | `js/app.js`, `js/views.js` |
| Q06 | One needs-you count: the headline, the status strip, the Work badge and the Places badge all count every attention item except knowledge, so they never disagree (the badge counted Decide and Review only and read 4 against the headline's 5) | critique 2026-10-28 (consistency) | SIMULATED | SHELL, NOW | `js/app.js`, `sim.js` counts |
| Q07 | Disclosures keep their open state across re-renders (Health checks, Launch settings rows, Chat privacy and fixtures, Replay reference); a simulation tick or a confirmation never snaps one shut under the pointer | probe and functional runs 2026-10-28 | SIMULATED | HEALTH, ACCOUNTS, CHAT, REPLAY | `ctx.ui.hlOpen`, `ctx.ui.lnOpen`, `P.open`, `rp.referenceOpen` |
| Q08 | Replay timeline marks sit in three lanes and nudge sideways when crowded, so no two marks overlap at any width; the Overview state sentence is 32 to 42 px (concept size; B11 stays an owner question) | probe 2026-10-28, concept 02 | SIMULATED | REPLAY, NOW | `js/replay.js`, `css/now.css` |
| QN01 | Network view (`?overview=network`): each project is a hub on a staggered lattice of cells round the core, neutral two-letter code and serif name (identity is the code and the place, never a state colour), its missions orbit it as crystals, executions and decisions hang off their mission; edges only hub to mission, mission to child and core to hub (no cross-project mesh, no ambient field). Cells nearest the core go to the projects that need you, then recent activity, and keep their slot for the session; the density level (10 cell sizes) only steps down as projects are added, and 100 projects collapse to hub marks with attention satellites and "+N quiet" | owner 2026-10-28, `js/constellation/geometry.js` `layout` and `plan` | SIMULATED | NOW | Network clusters (`layout.test.mjs`: no overlap for 1 to 100 projects at six sizes, determinism, stability, order) |
| QN02 | Network labels and hover: only hubs (name, state word, last action, "+N quiet") and the first few attention or running nodes carry a label; every node speaks on hover and focus with the Overview preview card (180 ms dwell, at once on focus, Esc closes); the project's cluster stays lit and the rest dims in 100 ms and restores in 180 ms, opacity only, nothing under Reduced motion | owner 2026-10-28 | SIMULATED | NOW | `js/constellation/map.js`, `map.css` |
| QN03 | Network core shrinks with the project count (1, 0.85, 0.7, 0.5) and drops its tagline under 0.7 so the clusters stay close to what it acts on | owner 2026-10-28 | SIMULATED | NOW | `coreScaleFor`, `taglineOn` |

## R. Overview territories (2026-10-28, owner feedback on space, attribution and scale)

| ID | Item | Source | Status | Where | Slice |
|---|---|---|---|---|---|
| R01 | Overview map = one territory per project, stable slot after first placement, neutral two-letter project code as identity (never the state colour), state as outline colour plus a word; 1 to 100 projects fit without overlap (full, compact, mark levels) | owner 2026-10-28, Codex map-scale spec | SIMULATED | NOW | S7 |
| R02 | Attribution: each territory says what Archeus did there last ("Archeus completed “title”" with time); a ledger line under the headline says what Archeus finished today and in which projects | owner 2026-10-28 | SIMULATED | NOW | S7 |
| R03 | Headline counts coloured by state (needs you amber, running blue, stopped red), each with its word; generic lede and eyebrow removed; phone keeps the three counters | owner 2026-10-28 | SIMULATED | NOW, NOW · P | S7 |
| R04 | Bottom band: translucent dock and Details button share one row (no separate strip, no zoom cluster on Projects view) | owner 2026-10-28 | SIMULATED | NOW | S7 |
| R05 | Hover: other territories dim in 100 ms and restore in 180 ms, ease-out, no lift or scale; preview card after 180 ms dwell, at once on keyboard focus, Escape closes; Reduced motion = instant | Codex map-scale spec | SIMULATED | NOW | S7 |
| R06 | Click on a territory focuses the project: its missions as 48 px rows with Review on each one that needs the user, Open work in the header, All projects (or Escape) goes back; mission crystals stay pointer-only, keyboard users get the rows | owner 2026-10-28 | SIMULATED | NOW | S7 |
| R07 | Projects / Network switch beside the headline (preference `overview`, URL `?overview=network`): Network is the node-link map kept as an alternative view | owner 2026-10-28 | SIMULATED | NOW | S7 |
| R08 | Test fixtures `?story=many` (12 projects, 36 missions, 20 ideas) and `?story=huge` (100 projects, 248 missions, 125 ideas), deterministic | Codex map-scale spec | SIMULATED | sim.js | S7 |
## Projects concept rebuild (2026-10-27)

| ID | Requirement | Source | Status | Area | Implementation |
|---|---|---|---|---|---|
| PR01 | Projects index at `#/projects`: one cell per project (code, name, state word, last thing Archeus did, counts, Open work), grouped Needs you / Running / Quiet, quiet group folded above 12 projects, search above 8, captured ideas listed; phone one column; project inspector with Recent / Phases / Ideas, Missions, Ideas, Details | concept 04 (`04-projects-ideas.png`), owner 2026-10-28 | SIMULATED | PROJECTS · P/T/D | `js/view-projects.js`, `css/projects.css`, `js/inspectors.js`, `css/components.css`; checked at `?story=many` and `huge` |
| PW01 | (superseded by WP01 to WP03 for the layout; the filter, caps and hover rules still hold) Work: project filter is chips up to 6 projects and one select above; Active, Needs you and Blocked show their first 8 rows with Show all, Done folds; the graph says when it shows the first 12 missions; row hover is a 100 ms in, 180 ms out opacity overlay | owner 2026-10-28 | SIMULATED | WORK | `js/view-work.js`, `css/work.css` |
| PW02 | (superseded by WP04 to WP06 for the page structure) Replay: events list on the left (largest, top-left), overview (stations, plot, scrubber with Earlier and Later) and selected step on the right, mission picked from a select, categories with no events hidden, recovery cards side by side, decision notes at the end | owner 2026-10-28 | SIMULATED | REP | `js/replay.js`, `css/replay.css` |
| PW03 | Chat page: one composer row (destination, field, slash, Send; Stop stays in the top bar), conversations rail shows the missions of the selected project only above 8 projects, command reference folded | owner 2026-10-28 | SIMULATED | CHAT | `js/chat.js`, `css/chat.css` |
| PW04 | Overview Tell dock: 48 px, nearly clear at rest (16 % ground), 45 % on hover, 85 % while typing, fill fades by opacity only, spans the scene up to the Details button | owner 2026-10-28 | SIMULATED | NOW | `css/now.css` |
| PW05 | Mission inspector: six stations in one row with short names at 420 px, tabs fit without scrolling to the edge | owner 2026-10-28 | SIMULATED | WORK | `css/inspector.css` |
| WP01 | Work is a list with a detail pane (graph is a second layout, `?as=graph`): saved views Needs you, Running, Blocked, Done, All as underline links with counts, in the address (`#/work?view=running&project=notes`); a project filter that is chips up to 6 projects and a searchable picker with a count per project above; the count line says `12 of 48` when narrowed; the address wins, a bare `#/work` keeps the filter another page set | owner 2026-10-28, research 6.2 | SIMULATED | WORK | `js/view-work.js`, `page-model.js`, `css/work.css`, `test/page.test.mjs` |
| WP02 | Work rows: state word with glyph (the shared vocabulary awaiting input, active, pending, error, complete, stale is on the row as `data-vocab` and in the pane), project, branch, relative time (`3m ago`, exact time on hover), spine; j and k move, Enter opens; hover after 120 ms or focus fills the detail pane with what Archeus did (last four events) and the primary action | research 3, 4 | SIMULATED | WORK | `js/view-work.js`, `css/work.css` |
| WP03 | Work empty states say what to do next (see what is running, Tell Archeus what to do, Show all projects); Pause in the pane is reversible with an Undo toast (7 s); Cancel mission keeps its confirm because it cannot be undone | research 4 | SIMULATED | WORK | `js/view-work.js` |
| WP04 | Replay modes are in the address (`#/replay/m-date?mode=compact&detail=verbose&section=recovery`): Timeline or Compact (neighbouring steps of one machine become one row), Normal, Thinking or Verbose detail; the choice stays for the next mission | research 3, 6.3 | SIMULATED | REP | `js/replay.js`, `page-model.js` |
| WP05 | Replay opens on the failed or awaiting step when the mission still needs you, otherwise on its last step; a what-changed line (steps recorded, time span, last step, steps that need a look) sits above the stations and the scrubber | research 6.3 | SIMULATED | REP | `js/replay.js` |
| WP06 | Replay sections Events, Evidence, Recovery, Reference with a sticky in-page nav (scroll-spy; a click changes the address and scrolls); Events and Evidence sit side by side when wide | research 3 (sticky in-page nav) | SIMULATED | REP | `js/replay.js`, `css/replay.css` |
| WP07 | Projects: inspector tabs Overview, Missions (count), Ideas (count), Activity, Settings are part of the address (`#/projects/prj-notes/missions`; any inspector tab is `#/<page>/<id>/<tab>`, set with replaceState); sort Attention (grouped by need), Recent or Name (one list), remembered in preferences; search above 4 projects; times are relative with the exact time on hover | owner 2026-10-28, research 6.1 | SIMULATED | WORK | `js/inspectors.js`, `js/view-projects.js`, `js/store.js`, `page-model.js` |
| WP08 | Overview Attention strip: only when something needs the owner, under the ledger, at most three project chips (code, name, count) and a `+N more` link; a chip focuses that project on the territory map (or opens its Needs you view in Network view) | owner 2026-10-28, research 6.1 | SIMULATED | NOW | `js/view-now.js`, `css/now.css` |
| PW01 | Work: project filter is chips up to 6 projects and one select above; Active, Needs you and Blocked show their first 8 rows with Show all, Done folds; the graph says when it shows the first 12 missions; row hover is a 100 ms in, 180 ms out opacity overlay | owner 2026-10-28 | SIMULATED | WORK | `js/view-work.js`, `css/work.css` |
| PW02 | Replay: events list on the left (largest, top-left), overview (stations, plot, scrubber with Earlier and Later) and selected step on the right, mission picked from a select, categories with no events hidden, recovery cards side by side, decision notes at the end | owner 2026-10-28 | SIMULATED | REP | `js/replay.js`, `css/replay.css` |
| PW03 | Chat page: no rail, no right column, no page title; one composer (scope chip, field, slash, Send; Stop stays in the top bar); Receipts and Context are sections of the page; the command reference lives in Context | owner 2026-10-28 | SIMULATED | CHAT | `js/chat.js`, `css/chat.css` |
| PW04 | Overview Tell dock: 48 px, nearly clear at rest (16 % ground), 45 % on hover, 85 % while typing, fill fades by opacity only, spans the scene up to the Details button | owner 2026-10-28 | SIMULATED | NOW | `css/now.css` |
| PW05 | Mission inspector: six stations in one row with short names at 420 px, tabs fit without scrolling to the edge | owner 2026-10-28 | SIMULATED | WORK | `css/inspector.css` |
| PW06 | One accessible picker (`js/picker.js`) replaces every native select in Chat, Work and Replay: button plus listbox in the top layer, arrows, Home, End, PageUp, PageDown, type-ahead, Enter and Space, Escape returns focus, 48 px rows, search above 8 items, groups, opaque surface token and a hairline, 2 px focus outline on the active row, legible in all six themes | owner 2026-10-28 | SIMULATED | CHAT | `js/picker.js`, `css/picker.css` |
| PW07 | Chat Receipts: what Archeus did in the scope, newest first, relative time with the exact time as tooltip, what waits for you on top; Context: the project's missions with their spine and a searchable command reference that fills the composer | owner 2026-10-28 | SIMULATED | CHAT | `js/chat.js` |
| PW08 | Composer queue and steer, on the page, the dock and the phone sheet: while a mission runs in the scope, Enter (and Send) queues a plain message for the end of the step (a Queued chip, a count on the composer, removable), Cmd or Ctrl+Enter steers it (a Steering chip until Core acknowledges); with nothing running, or for a command, both just send. The key hint shows only while a mission runs. Steer is simulated: a request event (Replay category INTENDED) and an acknowledgement event (RECORDED) appear in Receipts and Replay, and the reply says a real Core would record the boundary; neither claims the mission changed course. Announced in a polite live region | owner 2026-10-28 | SIMULATED | CHAT | `chat-engine.js`, `sim.js`, `replay-model.js`, `js/chat.js`, `js/chat-cards.js`, `test/chat.test.mjs` |

## Counts

Projects rebuild adds PR01 and the Network view adds QN01 to QN03: four SIMULATED rows beyond the historical slice-6 counts below.

227 rows, recounted from the Status column of the tables by script after slice 6: A 31 owner decisions · B 15 tokens · C 14 motion · D 13 spine · E 21 V1 surfaces · F 20 chat and slash · G 13 Replay · H 17 platform facts · I 11 prototype features · J 13 shell · K 6 simulation · L 7 open · M 9 required areas · N 10 S3 additions · O 16 terminal view (S5) · P 11 S6 additions.
By status word (a row can carry two; K counts as simulated, M is a map of areas and carries none): BUILT 50 · DESIGNED 36 · PROTOTYPED 32 · SIMULATED 124. Earlier lines said BUILT 51: counting the Status column gives 50 (a row whose Slice cell says "BUILT" is not a BUILT row). Slice 6 added section P (10 simulated rows and P05, a DESIGNED row that is not built) and changed only the Slice column of A02, A04, B05, C02, C06, C07, C12, E01, E15, E20, E21, H16 and M09, so no existing row moved between BUILT, DESIGNED, PROTOTYPED and SIMULATED.
S6 left unbuilt, honestly: C02 and C06 (duration-class table, still-moment rules), C12 (view transitions), E01 shortcuts Alt+1/2/3/J, Ctrl+, and Ctrl+K, E21 Ctrl+Enter, the E15 one-per-5-s announcer, P05 round buttons, and real-device checks (Windows High Contrast, touch, screen reader).
Slice 2 (map integration) builds 13 of these rows (A03, A06, A12, A26, B08, B10, C03, C04, C05, C08, E02, E13, E14).
Slice 1 shows 126 rows (the Slice column names S1, fully or in part); the rest, and the "part" rows, are the later slices' to-do list. Slice 5 adds section O (16 rows, all done) and completes the S5 part of E06, H09, H14, I07, M04, M06, M07 and M08. Slice 3 adds section N. The integration adds H16 (pause all, resume all, emergency stop).

Overview rework 2026-10-27 adds section Q (5 rows, Q01 to Q05). The row counts above are from before it.
