# Archeus V1 — UI Architecture

Status: IA and surfaces **DECIDED** (ADR-0014, ADR-0015); client stack **DECIDED** (ADR-0011);
library choices inside the SPA **PROPOSED**. Design rationale:
[../design/ARCHEUS_V1_DESIGN_RESEARCH.md](../design/ARCHEUS_V1_DESIGN_RESEARCH.md); visual
language: [../design/ARCHEUS_V1_DESIGN_SYSTEM.md](../design/ARCHEUS_V1_DESIGN_SYSTEM.md).

## 1. Clients and what they share

| | Desktop GUI | Web | Mobile | TUI / CLI |
|---|---|---|---|---|
| Code | the SPA in the Qt shell (existing `gui_qt.py` lineage; Edge `--app` / browser fallback kept) | the same SPA in a browser | the same SPA installed as a PWA over HTTPS | Python (`archeus/cli`) |
| Auth | device token from a local launch code (the shell cannot hand a page the local token) | device token from a local launch code | device token from pairing | local device token (`run/local-token`) |
| Transport | HTTP + SSE | HTTP + SSE | HTTPS (tunnel) + SSE | HTTP + SSE (TUI), HTTP only (CLI) |
| Business logic | none | none | none | none |

| Aspect | Shared | Adapted | Platform-specific |
|---|---|---|---|
| Domain vocabulary, state glyphs, copy | ✓ | | |
| API client + event handling | ✓ (generated TS client; Python client for TUI) | | |
| Navigation | concepts ✓ | sidebar (desktop) / bottom tabs (mobile) / number keys (TUI) | |
| Inspector | sections ✓ | column (desktop) / sheet (mobile) / pager (TUI) | |
| Density | | comfortable/compact desktop; comfortable mobile; dense TUI | |
| Notifications | events ✓ | | desktop toast, ntfy push, TUI status line |
| Tray / e-stop | | | desktop only |
| Step-up | | | PIN pad on mobile; re-auth prompt on desktop |

## 2. SPA structure (`clients/app/`)

```text
clients/app/
├── index.html                 no inline script (CSP script-src 'self')
├── tokens/tokens.json         design tokens (single source)
├── src/
│   ├── api/generated.ts       typed client generated from archeus/api/routes.py
│   ├── api/stream.ts          SSE via fetch stream, leader tab (Web Locks) + BroadcastChannel
│   ├── data/                  query cache: key = resource path; invalidated by event subject
│   ├── state/presentation.ts  generated domain-state → glyph/colour/label table
│   ├── nav/destinations.ts    ONE table: [id, label, icon, route, mobileTab?, shortcut]
│   ├── surfaces/              now/ work/ world/ control/ attention/ inspector/ command/
│   ├── components/            product components (design system §11)
│   ├── graph/                 2D fine-line graph (canvas 2D; WebGL later)
│   └── a11y/                  live-region announcer, focus management
└── vite.config.ts             outputs to ../../archeus/api/static
```

- P3.5b ships the minimal SPA of this structure: two lists (Now, Work), `api/generated.ts`,
  `api/stream.ts` (Web Locks leader + `BroadcastChannel`) and `api/transport.ts`, with no router
  and no query library — both are Q4, decided with P16's surfaces (p3.5b-design-gate.md D1).
  *As built (P16, [p16-design-gate.md](p16-design-gate.md) §30):* Q4 is decided — neither library;
  a keyed cache invalidated by event subject (`src/data/cache.ts`, `invalidation.ts`) and
  destinations held in the URL (`src/nav/destinations.ts`). The PROPOSED line below is superseded.
- Stack: TypeScript + React 19 + Vite (DECIDED). Data layer: **TanStack Query** for the cache
  with event-driven invalidation (PROPOSED — it does exactly "cache by key, invalidate by
  subject"; a hand-rolled cache would be reinvented). Routing: a small router (React Router)
  (PROPOSED). No UI component kit; components are ours (design system).
- One rAF-driven animation loop for the graph and the thread, parked when hidden/blurred (repo
  rule). Everything else is CSS transitions on transform/opacity.
- Build: `npm ci && npm run build` in `release.yml` before the wheel; the wheel ships only
  `archeus/api/static/*`; a packaging test asserts no `node_modules`, sources or maps ship.
- Toolchain: Node is a **build-time** dependency only (the Node LTS the website already builds
  with, pinned in `clients/app/package.json` `engines` and `.nvmrc`). `archeus/api/static/` is
  generated and gitignored; a fresh clone runs `npm ci && npm run build` in `clients/app/` once
  before opening the V1 UI, and Core serves a plain "SPA not built" page (not an error) when the
  directory is empty. CI: a `v1-client` job (from P3.5) runs `npm ci`, `npm run build`, the
  generated-client freshness check and the Playwright skeleton test; the Python `test` job stays
  Node-free.
- Authentication: the SPA obtains its device token through the local launch-code bootstrap
  ([api-and-realtime.md §5.1](api-and-realtime.md)) or, on a phone, through pairing.

## 3. Navigation model

`nav/destinations.ts` is the only navigation table (the repo's NAV lesson):

| id | Label | Desktop | Mobile | TUI | Shortcut |
|---|---|---|---|---|---|
| `now` | Now | sidebar | tab 1 | `1` | Ctrl/⌘+1 |
| `work` | Work | sidebar | tab 2 | `2` | Ctrl/⌘+2 |
| `world` | World | sidebar | tab 3 | `3` | Ctrl/⌘+3 |
| `attention` | Attention | sidebar badge + tray popover | tab 4 | `a` | Ctrl/⌘+J |
| `control` | Control | sidebar | avatar menu | `4` | Ctrl/⌘+, |
| `command` | Command bar | overlay | top search field on Now | `:` | Ctrl/⌘+K |

*As built (P16 table, P17 column):* `clients/app/tokens/navigation.json` holds these rows; `key`
is the SPA's Ctrl/⌘ shortcut and `tui` the TUI key, and both clients read the one file (A1).

Control sub-sections (the only second level): Autonomy · Automations · Resources · Devices ·
Notifications · Appearance · About. Resources → harness detail pages hold harness-specific
configuration (Claude Code: hooks, plugins, skills, agents, MCP, output styles — today's pages,
relocated, not redesigned in V1).

Deep links: every object has a URL `/o/<kind>/<id>` that opens the inspector over the current
destination (so notifications and cards link anywhere).

## 4. Surfaces

For each: user need · information · actions · Core relationship · interaction · desktop ·
mobile · TUI.

### 4.1 Now (home + conversation)
- **Need:** "What happened, what's happening, what needs me, and let me tell Archeus something."
- **Information:** presence line; since-you-left digest (events after the per-user cursor);
  happening now (active missions with specific progress text); top 3 attention items; primary
  conversation; activity timeline (filterable, system events hidden by default).
- **Actions:** type intent/control verb; act on cards; dismiss digest; open any object.
- **Core:** `GET /v1/now`, conversation queries, `POST /v1/conversations/{id}/messages`,
  `/v1/now/ack`; events `mission.*`, `message.created`, `approval.*`.
- **Interaction:** composer always focused on arrival (desktop); while Archeus works the
  message area shows specific progress text, and the reply arrives as a **whole message** row
  with cards when `message.created` fires (events are ids-only, so V1 does not stream reply
  tokens); the thread links replies to objects.
- **Desktop:** wireframe A.1. **Mobile:** digest + happening now + composer; conversation below.
  **TUI:** screen `1`, conversation in a scroll pane, `:` command line.

### 4.2 Work
- **Need:** "What is Archeus doing for me, and in what order?"
- **Information:** missions grouped Active · Needs you · Blocked · Planning · Done (7 days);
  ideas lane; automation runs; manual sessions (user-launched sessions tracked as manual
  executions, with launch/attach actions from today's Sessions tab).
- **Actions:** open, pause/resume, reprioritise (drag / menu), cancel, capture idea, promote idea,
  launch or attach a manual session.
- **Core:** `/v1/missions`, `/v1/ideas`, `/v1/automations/*/runs`, execution commands.
- **Desktop:** list + inspector. **Mobile:** grouped list, sheets. **TUI:** screen `2`
  (wireframe A.4).

### 4.3 Mission inspector (any mission, from anywhere)
- Tabs: Outcome · Plan · Now · Evidence · Thread · Why · Timeline (research §19, wireframe A.2).
- Plan edit creates a new plan version (and supersedes approvals), never edits in place.
- Execution detail opens *within* the Now tab (live tail subscribed only while open), showing
  harness/account/model as metadata, not headline.

### 4.4 World
- **Need:** "What does Archeus know about my world, and is it right?"
- **Information:** filterable list of projects, repositories, systems, people, meetings,
  decisions, knowledge, ideas; per-object inspector with relations, provenance, timeline; graph
  toggle.
- **Actions:** create/archive project, import meeting notes, inspect repository now, confirm /
  retract / supersede knowledge, link objects, forget (dry-run).
- **Core:** `/v1/projects`, `/v1/world/graph`, `/v1/knowledge`, `/v1/repositories/*`.
- **Project page:** tabs Overview · Missions · Knowledge · Architecture · Repositories ·
  Sessions · Settings (research §20).
- **Mobile:** list and inspector only; graph view hidden below 600 px width (list equivalent is
  the default anyway). **TUI:** screen `3`, tree + inspector pager.

### 4.5 Attention (global layer)
- **Need:** "What needs my decision, in order of urgency?"
- **Information:** approvals (with canonical action + expiry), blocked items waiting on the user,
  human-acceptance verifications, knowledge proposals, drift proposals, suspended automations,
  account re-auth requests.
- **Actions:** approve/reject (step-up where required), accept/reject result, confirm/dismiss
  proposal, choose drift resolution, re-enable automation.
- **Core:** `/v1/attention`, `/v1/approvals/{id}/decide` with idempotency key.
- **Desktop:** sidebar entry with badge + popover from the tray. **Mobile:** tab 4; approvals as
  sheets (wireframe A.3). **TUI:** `a` screen; `A` approves the focused item after a confirm line.

### 4.6 Control
- **Autonomy:** profiles + policy grid + simulate (research §25).
- **Automations:** list, rule reader, simulation, runs.
- **Resources:** harnesses, accounts (priority, ceiling, reserve, budgets, fallback, project
  rules, live usage, health), models, route preview, sessions (infrastructure view), nodes.
- **Devices:** paired devices, pair a phone (local only), revoke, remote access setup guide
  (Tailscale Serve), emergency stop / re-arm.
- **Notifications:** channels (desktop, ntfy), which events notify.
- **Appearance:** thread tint, density, motion (light/dark/contrast follow the OS).
- **Mobile:** read + limited edits (pause automations, change fallback, revoke device); policy
  edits require the `admin` scope. **TUI:** screen `4`.

### 4.7 Command bar
Same grammar as the composer: control verbs (answered without a model), jump to object by name,
"new mission …", "idea …". Shows what will happen before Enter ("Pause *Dashboard* — 2 executions
will halt at their next step").

### 4.8 Search
World list filters + command bar cover object search. Full-text search over *transcripts* (today's
Search page) moves to Control → Resources → Sessions (infrastructure) and to the knowledge
query; it is not a top-level destination.

### 4.9 Notifications
In-app via Attention and toasts; desktop toasts via the Core notifier; mobile via ntfy deep links
into `/o/approval/<id>`. Notification settings per event class in Control.

### 4.10 Approval UX (cross-surface contract)
1. The item shows **what exactly** will happen (canonical action in mono), **why it needs
   approval** (matched rule, scope, locked?), **what happens if rejected**, and **expiry**.
2. Buttons: *Approve* and *Reject* equal size; destructive → Reject leading, step-up required.
3. Decisions are idempotent; a second device showing the same approval updates live to
   "Approved on Phone 14:02".
4. Approved actions show CONSUMED with the resulting event linked.

## 5. Spatial interface

`src/graph/`: 2D canvas renderer (Canvas 2D; WebGL optional later) over
`GET /v1/world/graph?focus=<ref>&depth=2`. Encoding per research §26. Force layout computed
once per focus change (deterministic seed), then static; only energy pulses on edges with live
executions animate (transform/opacity of overlay sprites). Level of detail: cluster labels only
below zoom 0.5; node labels on hover/focus; keyboard: arrow keys move focus along edges, Enter
opens inspector. Reduced motion: no pulses; live edges drawn thicker instead. Performance
budget: 1,000 nodes at 60 fps on integrated graphics; beyond that, clusters collapse.

The current `stage.js` three.js background is **not** carried into V1 as ambient decoration
(ADR-0016). Its flat graph-scene lineage is the candidate for the later optional 3D mode.

*As built (P18, [p18-design-gate.md](p18-design-gate.md) §23):* routes `#/world/graph`,
`#/world/graph/<kind>/<id>` and `#/world/graph/repository/<id>/modules[/<path>]` over
`GET /v1/world/graph?focus=<kind>:<id>&depth=` (depth 1 for the world and a project, 2
otherwise) and `GET /v1/repositories/{id}/graph`. The encoding is `src/graph/encoding.ts`
(A3: a session is a ring, a DECISION-type knowledge item a diamond; state colour on missions,
tasks and executions only). Layout: seeded, 120 iterations once per focus, positions kept
across refreshes. Energy: one 240 ms opacity pulse on a live execution's task edge per frame
about it, at most every 2 s; under reduced motion the live edge is drawn 2 px instead. Keys:
↑/↓ choose an edge, → follow, ← back, Enter open, F focus the graph there, Space expand or
collapse, `+`/`-`, `0`, `/`, P marks a path end. Below 600 px the Relations list is the view.
The 1,000-node, 60 fps budget is CI proxies plus manual evidence on integrated graphics.

### 5.1 P16 carry-forward: graph capability preservation

*Done by P16* ([p16-design-gate.md](p16-design-gate.md)): the inventory, classification and
relations view are in the gate; the text below is the requirement as supplied.

Supplied 2026-09-28 as a P16 addendum. Nothing is implemented, inspected or refactored for it
before P16 begins; P13–P15 are untouched by it. It adds to the P16 requirements and weakens none
of them (ontology, external-reference evaluation, visual, motion, accessibility, responsive,
performance). The renderer choice in §5 above is provisional until step 1 below is done: P16 does
not start by choosing a graph library or copying a visual style.

**The requirement.** Graph is a first-class Archeus capability where relationships, lineage,
dependencies, provenance, topology or connected knowledge are the primary information — not a
look applied to every screen. Archeus does not become a graph application: lists, timelines,
detail views, forms and the command bar remain the primary UI, a user can work without ever
opening a graph, and the graph is never the only way to reach any fact. Graph is treated twice
and the two are kept apart: (a) existing technical/product capability to inventory and preserve;
(b) a visual/interaction language that may inform the design system.

**Order.** ontology → existing graph capability inventory → information architecture → decide
where graph belongs → visual design system (graph visual language) → motion & interaction system
(graph interaction/motion) → implementation. Inspect first, design second, reuse/adapt third,
implement last.

**Discovery.** Inventory before deciding any fate: every graph-related module, data structure,
domain model, query, builder, visualization, API/route, derived relationship, persistence and
serialization format, interaction mechanism, screen/component, test and fixture, consumer,
dependency, performance characteristic, document, and any relationship semantics the graph
already encodes. A module is not obsolete because its current UI is legacy. Known starting points
— **not** the inventory, which P16 owes by inspection: `claude_sessions/connections.py`,
`flowgraph.py`, `cluster_spec.py` (+ its generated `web/cluster-spec.js`, `www/lib/cluster-spec.ts`),
the semantic memory graph and recall subgraph (`memory.py`, `recall.py`, `recall_hook.py`,
`archeus/core/knowledge`), the legacy `/graph` route and `stage.js` graph scene,
`www/components/journey/scene.ts`, `archeus/core/world`, and `/v1/world/graph` (§5, P18).

**The P16 design gate gains a section "Graph Capability & Graph Interaction System"** containing:

1. Existing graph capability inventory — table `| Existing capability | Technical location | What
   it represents | Current consumer | Current UI exposure | Architectural value | P16 disposition |
   Reason |`, disposition ∈ ADOPT / ADAPT / PRESERVE-BEHIND-UI / DEFER / REJECT, decided by what the
   capability does. Presentation that does not fit the new UI is not grounds for REJECT.
2. Graph-to-ontology mapping over at least: projects, repositories, worktrees, missions, tasks,
   requirements, plans, plan versions, actions, executions, sessions, context, evidence,
   verification, reviews, approvals, world state, knowledge, decisions, feedback, model/harness
   selection, resources, accounts, dependencies, lineage, events, automation — stating which are
   genuinely graph relationships and which stay lists/tables/timelines/detail views. Nothing is
   forced into a graph.
3. Capability preservation assessment, answering explicitly: which graph work is preserved and
   reused; which needs adaptation because its presentation belongs to the legacy UI; which stays
   internal/backend capability rather than exposed directly. Answered from the implementation, not
   from aesthetics.
4. The dispositions themselves, with reasons.
5. IA role: whether a first-class relationship view exists and which focused chains it serves
   (candidates, not commitments: mission → task → requirement → plan → action → execution →
   evidence → verification → review; project → repository → worktree → mission → session;
   task → model/harness selection → execution → evidence → verification; knowledge → decision →
   feedback → later learning). Meaningful relationships, never the whole database.
6. Navigation model: node → canonical entity view (mission, execution, verification detail), edge
   → relationship/provenance explanation, focus, expand/collapse neighbourhood, filter by entity
   and relationship type, search, path/lineage/causation/dependency/provenance tracing, pin, back
   to previous graph context, deep links. One navigation model, not a second incompatible one.
7. Provenance (P13): graph may render plan → action → execution → evidence → verification →
   review, but only authoritative backend relationships — no inferred edges, stale/superseded
   entities visibly distinct, verification stays P13-owned, graph is never a source of truth.
8. Event causality (P14): event → automation → action request → execution → verification →
   resulting event, as an investigation target, not one giant event graph; no private model
   reasoning.
9. Model/harness selection: task → requirements → selected model × harness → account/resource →
   execution → verification, showing what was selected, alternatives where appropriate, the
   constraints that decided it, what actually ran and whether a fallback occurred — structured
   selection rationale only, never chain-of-thought.
10. Visual graph language: nodes, edges, relationship emphasis, depth/focus, grouping, progressive
    disclosure, state-based node appearance, lineage/dependency rendering — strongest where
    relationships are the information, calm everywhere else.
11. Interaction model.
12. Motion model: motion for focus, expansion, collapse, traversal, state change, causal
    progression, selection. No ambient or perpetual graph motion, no constantly moving nodes, no
    live layout animation, no animation storms, no per-item animation across long or live lists;
    `transform`/`opacity` only, reduced motion honoured (design system §8, repo flicker rules).
13. Accessibility: not mouse-only — keyboard traversal, focus, node selection, edge inspection,
    screen readers, touch, reduced motion; a selected node exposes its relationships as a
    structured, navigable list that does not depend on spatial position.
14. Responsive/mobile: not the desktop graph shrunk — focused neighbourhood, bottom sheet/detail
    panel, tap-to-expand, relationship lists, simplified topology, graph-to-detail transitions;
    same relationships, different representation.
15. Performance/scaling: node/edge counts, density, layout cost, incremental and live updates,
    culling/virtualization, filtering, progressive expansion, memory, mobile. Start focused →
    expand deliberately → filter → inspect → navigate; never load, render and animate everything.
16. Migration/reuse strategy for each ADOPT/ADAPT/PRESERVE-BEHIND-UI item.
17. Tests and acceptance criteria.

**External references.** Munder Difflin, Vicoa, Graphify, Cognee, Anthropic redesign methodology,
Apple Design Skill, Ship Notes (R7) and anything supplied before P16 are evaluated for graph ideas
as inputs, not templates ([../research/external-references.md](../research/external-references.md)).
Ship Notes is a motion/interaction reference and not an authority on graph design; no copied code
without license review. The ontology and the existing graph capabilities stay authoritative.

**Acceptance question — P16 implementation is not approved until the gate answers it:** *How are
we preserving the substantial graph work already built into Archeus rather than accidentally
throwing it away during the UI rearchitecture?* The answer names concrete modules and capabilities
and their future role. "The graph can be rebuilt later" is not an answer; valuable graph
functionality is reused or adapted where technically appropriate, not replaced for visual reasons.

P16's outcome is IA + visual design system + motion & interaction system + the graph/relationship
experience — native to Archeus, a distinct mode for relationship-heavy work. P18 then builds the
spatial view against what this section decides.

## 6. TUI architecture

`archeus/cli/tui/` is a new, thin client on the API, reusing `claude_sessions/term.py` (the
platform seam for keys, POSIX + Windows) and `render.py` (ANSI rendering). Screens mirror
destinations; the event stream drives re-queries exactly like the SPA. The legacy TUI
(`claude_sessions/main.py`) remains until the retirement gate. The thin CLI (`archeus status |
approve | pause | route why | estop | pair`) ships first (V1 slice) because it is also the
scripting and emergency interface.

*As built (P17, [p17-design-gate.md](p17-design-gate.md) §20):* `archeus tui [--open KIND/ID]
[--once] [--light]`, a client of a running Core on the local token only (it never starts Core).
The navigation, presentation, trigger and invalidation tables are the SPA's JSON, generated into
`archeus/cli/tui/_tables.py` and `tokens.py` by `tools/gen_ui.py` (A1); the SPA's pure
presentation logic has a Python twin held to it by shared cases in
`clients/app/test/fixtures/parity.json` (A2); `client.py` is a stdlib HTTP + SSE transport that
keeps Core's refusals whole (A3). Every Core string passes one sanitiser before it is laid out.
Relationships are Core-supplied edge lists; nothing spatial is drawn (P18).

## 7. UI quality gates (carried from the repo, applied to the SPA)

| Gate | Carried from |
|---|---|
| keyframes may animate only transform/opacity; no `steps()` | `test_gui_flicker.py` |
| no `backdrop-filter`, `filter: blur`, `mix-blend-mode` | Qt GPU tear lesson |
| component layout rules use container queries | `test_a_container_shaped_rule_is_never_a_media_query` |
| overflow + dead-space audit over every surface at 390, 768, 1280, 1920 px | `tools/shot_gui.py` `SPACE_JS` |
| smoke run: every destination and inspector tab renders against the fake Core; animation loop parks | `tools/smoke_gui.py`, with a floor on checks run |
| contrast gate over tokens × themes | `tests/test_themes.py` floors |
| no inline handlers / inline script | `test_inline_handlers.py` (stricter: CSP forbids them) |
| nav table ↔ routes ↔ TUI screens parity | `test_parity_gate.py` idea, now trivially true because both read one table |
| screenshots for docs regenerated after UI changes | existing `--docs` pipeline |

## 8. Legacy UI during the strangler period

The legacy GUI and TUI keep working unchanged against `claude_sessions`. The V1 SPA is served by
Core at its own port. Onboarding offers "Open Archeus V1" from the legacy GUI once P16 ships.
Retirement follows the capability checklist in [migration-plan.md §6](migration-plan.md).
