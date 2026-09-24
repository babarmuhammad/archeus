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

## 6. TUI architecture

`archeus/cli/tui/` is a new, thin client on the API, reusing `claude_sessions/term.py` (the
platform seam for keys, POSIX + Windows) and `render.py` (ANSI rendering). Screens mirror
destinations; the event stream drives re-queries exactly like the SPA. The legacy TUI
(`claude_sessions/main.py`) remains until the retirement gate. The thin CLI (`archeus status |
approve | pause | route why | estop | pair`) ships first (V1 slice) because it is also the
scripting and emergency interface.

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
