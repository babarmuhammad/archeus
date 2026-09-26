# Archeus V1 — Design Research

Status: design exploration for V1, written before any implementation. Architecture counterpart:
[../architecture/ARCHEUS_V1_REARCHITECTURE_PLAN.md](../architecture/ARCHEUS_V1_REARCHITECTURE_PLAN.md).
Visual language: [ARCHEUS_V1_DESIGN_SYSTEM.md](ARCHEUS_V1_DESIGN_SYSTEM.md).
Source documents (local, gitignored): `docs/architecture/reference/Archeus_v1_System_Specification.md`,
`Archeus_v1_Implementation_Plan.md`, `Archeus_v1_Architecture_Design_and_Plan_FIXED.pdf`,
`Archeus_v1_Architecture_Designs.pptx`.

Evidence labels used throughout: **[V]** verified in source or by direct inspection,
**[S]** secondary source, **[I]** our interpretation.

---

## 1. Product understanding

Archeus V1 is a **persistent AI colleague that operates on the user's world**: it keeps a
trustworthy picture of what is true now, turns what the user wants into missions it owns, finds
the context itself, plans, asks when policy says so, runs the work on the right resources,
proves the work, updates the picture, and learns.

The one-line promise: **Tell Archeus what you want. It figures out what needs to happen.**

What that implies for design [I]:

- The primary relationship is **user ↔ Archeus**, not user ↔ agents, sessions or accounts. The
  interface must make Archeus the addressee and the world the subject.
- **Trust is the product.** Nobody hands outcomes to a system whose state they cannot verify.
  Every surface must answer "is this true, how do you know, and what will you do next".
- **Most of the time the user is away.** The product is experienced as a *return*: "what
  happened, what needs me, what's next". Presence comes from continuity, not animation.
- Software is the first domain, not the only one: research, documents, presentations and
  automations share the same mission loop. Nothing in the IA may be code-specific at the top
  level.

## 2. Current UI archaeology

Inspected at `main` @ `b778226` (2026-09-23) [V].

| Surface | What exists | Size |
|---|---|---|
| Desktop GUI | stdlib HTTP server (`gui.py`) + vanilla SPA (`web/app.js` 8,317 lines, `app.css` 2,590, `stage.js` 2,670 three.js, `motion.js`, `instruments.js`) in a PyQt6 WebEngine shell with Edge/browser fallback | ~16k lines web |
| Navigation | `NAV` flat table of 20 pages grouped by `SECTIONS` into five: **Context** (Global CLAUDE.md, MCP), **Library** (Skills, Plugins), **Activity** (Usage, Loops, Logs), **Harnesses** (tabs: harness, accounts, client, output styles, agents, hooks), **Settings** (Launch, Appearance, Paths & limits, Models, Updates); off-nav Search (Ctrl+K) and Help (`?`) | |
| Project page | 9 tabs in 4 groups: Session (Sessions), Context (Memory, CLAUDE.md, Audit), Project (Tools, Usage, Repos), Actions (Plan → Execute, Code Review) | |
| Dashboard | three bands: *Spend* (quota ring, burn dial, MCP ring, jobs equaliser, per-account usage, token chart), *Work* (live sessions flow, continue, recent), *Workspace* (project node map + list) | |
| Jobs | inline banner (`#jban`) with a travelling-border "beam"; escalates to a modal only when a job parks at an approval gate (`status==='awaiting'`) | |
| Plan → Execute | plan with a headless model, edit, approve, launch an interactive session with the plan attached; own state machine `PE` with a stall watchdog | |
| TUI | keyboard-first terminal UI (`main.py`, `ui.py`, `term.py`) with the same five sections and a 29-key sessions screen (`session_menu.ACTIONS`) with palette `/` and help `?` | |
| Visuals | 39 hex palettes (32 visible), 8 skins (4 classic + 4 owned by locked "worlds": anime, cyber, deck, graph), ~30 `--sk-*` tokens reaching ~130 selectors, one full-viewport three.js "stage" behind the app driven by real job state | |
| Mobile / remote | none; loopback only | |

## 3. Current UX archaeology

The dominant user flow today [V]:

1. Open the app → dashboard of spend and sessions across projects.
2. Pick a project → Sessions tab → resume or launch a Claude Code session (model, effort,
   account, permission mode chosen in Launch settings or per launch).
3. Work happens **in the terminal**, in Claude Code, not in Archeus.
4. Archeus contributes around the session: memory injected per prompt (recall hook), CLAUDE.md
   blocks, lessons, worklog, account rotation when a limit hits, cost visibility.
5. For planned work: Plan → Execute produces a plan with a headless model and launches an
   interactive session with it.

So today Archeus is a **workspace and memory layer around sessions the user drives**. The user
is the orchestrator; Archeus is the quartermaster. V1 inverts this: Archeus orchestrates, the user
directs and decides [I].

## 4. Current information architecture

Organised by **Claude Code's configuration vocabulary** (CLAUDE.md, MCP, skills, plugins, hooks,
agents, output styles, loops) and by **infrastructure** (harnesses, accounts, models, usage).
Projects and sessions are the only world objects. There is no mission, no plan object beyond a
markdown file, no decision, no person, no meeting, no idea [V].

The IA is coherent *for what the product is today* — the five-section regrouping replaced a
15-row wall, and flat tables with id references keep it testable. It is the wrong IA for V1
because every top-level item is a noun of the implementation, which principle 22 ("avoid exposing
infrastructure complexity unless relevant") forbids [I].

## 5. Current interaction model

- Page navigation + tabs; every page is a renderer painting `#content`; guarded so a slow fetch
  cannot paint over the page you moved to [V].
- Polling (dashboard 10 s, heartbeat 2.5 s, jobs 0.6→4 s back-off) [V].
- Long operations are jobs with inline progress; approvals are diff gates in a modal [V].
- The TUI and GUI reach the same backend functions; parity is enforced by tests because logic is
  partly duplicated [V].

## 6. Current visual language

Dark, instrument-like, dense. Gauges (ring, dial, spark, equaliser, flow) are canvas geometry
with DOM readouts. A single WebGL stage behind the app, calmed by a luminance ceiling after a
bloom-heavy first version was judged "overstimulating". Worlds (anime/cyber/deck/graph) are
locked bundles because mixable loud skins "could commit to nothing". The `graph` world is an
homage to the project's own architecture graph and is the closest ancestor of V1's spatial
view [V].

## 7. Current strengths (keep)

1. **Discipline that produced a stable app** [V]: animate only transform/opacity; no
   backdrop-filter (tears the Qt GPU surface); container queries rather than window media
   queries; one rAF chain that parks when hidden; motion driven by real state, never ambient.
2. **One flat declaration per concept** with everything derived (NAV, TABS, ACTIONS, PALETTES,
   cluster spec) and tests that fail on drift.
3. **Jobs inline, escalate to modal only on a real approval gate** — exactly the V1 attention
   model in miniature.
4. **The stage as "one surface behind, driven by state"** — the right principle for presence.
5. **Hex-first palettes with enforced contrast floors** (4.5:1 body, 3:1 secondary) and ANSI
   derivation for the TUI.
6. **Gates that read what ships** (overflow and dead-space audits, SEO checks on built HTML) and
   are mutation-verified.
7. **Real capabilities worth preserving:** multi-account rotation, quota latching, usage polling,
   memory graph + BM25 recall, lessons, worktree board, provider failover proxies, notifications.

## 8. Current problems (fix by design, not by patching)

| Problem | Evidence | V1 answer |
|---|---|---|
| Home is a metrics dashboard | spend band first | Now: presence, attention, continuation |
| No object for "work" | plan is `.archeus/plan-latest.md` | Mission / Plan / Task / Execution |
| Infrastructure is top-level | Harnesses, Models, Accounts, Hooks, Plugins in nav | Control → Resources, disclosed |
| State is inferred by polling many endpoints | 2.5 s heartbeat cycles | one event stream + re-query |
| Approval UX tied to a job modal | `#jovl` gate | Attention tray, approvals on any device |
| Visual identity split across 39 palettes × 8 skins | themes.py | one product language; state colours fixed |
| Decorative risk of the worlds | anime/cyber skins | spatial view with semantics only |
| Logic reachable only through TUI prompts | `_install_bridge` monkeypatching | clients hold no logic |

## 9. Anthropic redesign methodology findings

**Source trail.** The supplied X post (`x.com/dani_avila7/status/2102212844238275030`) returned
HTTP 402 to direct fetch. Read through the fxtwitter mirror API [S]: Daniel San, 2026-09-22,
sharing *"Anthropic's repository for code migrations with Claude Code"*, noting that AI makes
migration "simpler, not easy", and that the kit provides structure through rules, dependency
mapping, behavior verification and configuration constraints. The linked repository
`anthropics/code-migration-kit-with-claude-code` was inspected directly at `cf91c9d`
(2026-07-08) [V]. It is described as a companion to the post *How Anthropic runs large-scale code
migrations with Claude Code* (not fetched) and is marked "reference code, not actively
maintained". The source documents cite a *different* post
(`x.com/claudedevs/status/2097369738968195513`, 2026-09-08, read via the same mirror [S]): an
article on reducing Claude Platform cost — prompt-cache hit rate, removing prompt anti-patterns
when upgrading models, calibrating effort ("a stronger model at low effort can be cheaper than a
weaker model working hard").

**Methodology extracted from the kit [V] and how it changed this redesign [I]:**

| Kit principle (verified) | How it shaped Archeus V1 |
|---|---|
| Feasibility first; "don't migrate" is a valid verdict | P0 has a real gate, including the OPEN subscription-terms question; the plan names what would stop V1 |
| "No judge, no exit condition": behaviour matching through the public surface, built before translating | the acceptance scenarios and a fake harness are written in P1, before domain code; legacy retirement needs a capability checklist judge |
| **For redesigns: the rulebook becomes a design document; the bakeoff is invalid; substitute adversarial review of the design plus disposable full runs; unit of work = subsystem; behaviour matching still works** | this document set *is* the rulebook; it was red-teamed before being written up (25 findings folded in); implementation phases are subsystems; the walking skeleton (P3.5) is the first disposable full run |
| "You don't fix the code — you fix the process that produced it"; a failure seen three times is a rule bug | the task machine's three-strikes rule; lessons attach to process, not to instances |
| Sign-off gates: a phase runs to completion, returns evidence, stops; sign-off is starting the next phase; queues defined by what exists on disk | each phase ends at a gate with explicit acceptance criteria; Archeus's own mission engine adopts the same "plan → approve → execute → evidence" gate shape |
| Model tier by blast radius (largest for rules, mid for volume, small for mechanical) | router tier-fit rule |
| Guardrails installed by the human, never self-installed; deviations logged | policy changes only by user devices; approvals single-use; deviation log section in the plan |
| Cost as bands, never precise numbers | plan `estimated_cost` is a band |

## 10. Apple Design Skill findings

Installed from `github.com/dickwu/apple-design-skill` (cloned into the user's skill directory,
outside the repo) [V]. It is a review methodology grounded in 124 generated HIG pages with five
lenses and severity tags. What V1 takes from it:

- **Order of work:** accessibility → platform conventions → craft → interaction → content, and
  "build the token system before layout".
- **Numbers adopted as floors:** text contrast 4.5:1 (≤ 17 pt) and 3:1 (≥ 18 pt or bold); targets
  44×44 pt mobile (28 minimum), 28×28 desktop (20 minimum); body type 17 pt mobile / 13 pt desktop
  default; sidebars at most two levels.
- **Template check:** the skill flags three looks that dominate generated UI; one of them is
  *near-black with an acid-green or vermilion accent*. Today's graph world is near-black with a
  saturated cyan — close enough that V1 must justify its dark theme by meaning (state colours,
  the thread) — resolved in design review B.1 by removing the hue accent entirely [I].
- **"One signature element, everything else quiet"** and the **removal test** → the thread
  (design system §2).
- **Generative-AI guidance (HIG *Generative AI*, updated 2026-06-08) [V]:** keep people in
  control; make it easy to refine or revert results and acknowledge corrections; ask before
  irreversible actions; give *specific* progress text ("Summarising key themes from your notes",
  not "Processing…"); disclose where AI is used; offer a non-AI path where possible; voluntary,
  non-interrupting feedback. These map directly to cards with Undo, approvals, activity phrasing,
  deterministic control verbs, and thumbs on results.
- **Cross-platform translation:** tab bar ↔ bottom navigation on mobile; sidebar ↔ desktop; menu
  bar/tray commands on desktop; size classes ↔ container queries (which the repo already uses).

## 11. Lessons from Munder Difflin

`chaitanyagiri/munder-difflin` @ `c7c8921` (MIT) [V]: an Electron app running a "hive" of agents
with a supervisor ("god") agent, per-agent memory, inbox/outbox directories, an append-only
`log.jsonl`, a single git committer, hook-based control and a visual office floor.

Adopted: single writer + router; append-only log with per-consumer cursors; **hook-return
control** (deny / inject context / halt) rather than typing into terminals; a pure circuit
breaker moving one level per beat; the four-part dispatch contract (objective / output / tools /
boundaries) as the Task contract; backup → verify → swap for LLM memory rewrites.
Rejected: git as the event store (they already untrack files to fight bloat); orchestration
policy in a system-prompt string (untestable); silent drop at the hop cap (their docs claim
escalation; the code drops); forced continuation at Stop (they removed it for safety and cost);
the office-floor visual as the product (principle 21: visuals must mean something).
**Meta-lesson:** the strongest signal is what a project removed.

## 12. Lessons from Vicoa

`vicoa-ai/vicoa` @ `8933edb` (**AGPL-3.0 — design ideas only, no code reuse**) [V]: FastAPI +
Postgres backend, a machine daemon per computer, Next.js web, Electron desktop, Flutter mobile,
tasks and automations, remote control.

Validates: the Core/node split; mobile as a control surface; one daemon per machine;
outbound-connecting nodes; worktrees outside the repository at daemon-computed paths.
Adopted patterns: wake-and-requery event delivery; typed revocable tokens; credentials never in
query strings; claim-and-advance scheduling with a run table; socket-as-liveness; a local-only
mode speaking the same protocol. Challenges we accept: Vicoa's in-memory connection manager
forces a single replica — Archeus V1 is single-user and single-Core by design, so this is fine
and documented. Rejected: terminal-scraping permission detectors; self-reported status as truth
(they removed a UI sweep that faked COMPLETED); a split identity stack.

## 13. Lessons from Graphify

`Graphify-Labs/graphify` @ `a5957aa` (Apache-2.0) [V]: tree-sitter extraction → NetworkX graph →
clustering → reports, with MCP query tools.

Adopted: deterministic pass before any model; edge confidence **EXTRACTED / INFERRED /
AMBIGUOUS** (AMBIGUOUS goes to human review); token-budgeted subgraph rendering; blast-radius
queries; content-hash caches with extractor-versioned invalidation; manifest written only on
success; lessons that need corroboration and decay. Rejected: one big JSON graph as the store
(fine for one repo, wrong for a persistent multi-project world); rubric confidence treated as
probability. Relevance: repository understanding and the World graph — but **not every Archeus
use case needs a graph database**; relational tables with recursive queries suffice for V1.

## 14. Lessons from Cognee

`topoteretes/cognee` @ `663a2dc` (Apache-2.0) [V]: remember / recall / improve / forget over graph
+ vector stores with pluggable backends.

Adopted: session memory vs permanent memory with a debounced, watermarked bridge; staged improve
passes that skip cheaply; idempotent feedback reinforcement (EMA) — DEFERRED past the V1 slice;
contradiction as an *added* edge, never an overwrite; one `forget` entry point with dry-run;
rule-based query routing with no model call. Rejected: twenty search types; LLM-heavy
"cognify" for code (Graphify's AST path is cheaper and deterministic); document-level pruning as
the only decay; adopting a memory runtime wholesale.

## 15. Archeus design principles

The prompt's 22 principles condensed into eight design rules that can be checked in review:

1. **Talk to Archeus; look at the world.** Conversation is how you direct; the world view is how
   you verify. Every screen is one or the other, or a split of both.
2. **State before story.** Show what is true (state, owner, next step) before narrative. Prose
   from a model never replaces a structured fact on screen.
3. **Every consequential thing answers "why".** Context used, policy decision, route decision,
   verification evidence — one tap away, generated from records.
4. **Attention is scarce and earned.** Only things that need the human reach the Attention tray
   or a notification. Everything else is in the feed.
5. **Missions, not machinery.** Harness/account/model/session appear only in Control and in the
   Why tab, never as the default unit of a list.
6. **One colour means one thing.** State colours are fixed across themes and are
   the only hues on screen; primary actions are neutral fills, the thread is near-white ink.
7. **Motion reports change.** Things move because something happened; nothing loops for
   ambience (repo lesson, and the HIG's "purposeful, brief, rare").
8. **Undo or approve.** Every Archeus action is either reversible from where it is shown, or it
   was approved before it happened.

## 16. User mental model

```text
      I tell ARCHEUS what I want ───────────────► Archeus turns it into MISSIONS
             ▲                                           │
             │                                           ▼
  I decide when it asks  ◄──── ATTENTION ◄──── it works on my WORLD (projects, repos,
             │                                           │        decisions, people…)
             ▼                                           ▼
  I adjust how it behaves ────► CONTROL        it tells me what changed (NOW)
```

The user holds four ideas: **Archeus** (who), **Missions** (what it's doing for me),
**World** (what it knows and works on), **Control** (how much I let it do and with what).
Attention is not a place; it is Archeus tapping the user's shoulder.

## 17. Information architecture proposal

**Evaluated options:**

| Option | Verdict |
|---|---|
| Spec §24's seven: Conversation, Current World, Missions, Projects/Ideas, World/Knowledge, Control, Infrastructure | too many top-levels; "Current World" and "Conversation" are the same moment (arriving); Projects/Ideas and World/Knowledge split one world in two; Infrastructure is a subset of Control |
| pptx slide 10's six (Conversation, Current World, Missions, World, Control, Infrastructure) | better; still separates arriving from talking, and gives Infrastructure a top-level slot principle 22 argues against |
| Conversation-only (everything through chat) | fails trust: state must be inspectable without asking; fails mobile glanceability |
| Dashboard + chat panel | the thing we are replacing |
| **Four destinations + two global layers (chosen)** | matches the mental model one-to-one; fits a four-tab mobile bar; keeps sidebar at one level (≤ 2 with sub-sections) |

**Chosen IA (ADR-0014):**

| Destination | Contains | Replaces (spec / pptx) |
|---|---|---|
| **Now** | presence line, since-you-left digest, what's happening, what needs you (top of Attention), the primary conversation and composer, activity timeline | Conversation + Current World |
| **Work** | missions (Active · Needs you · Blocked · Done), ideas lane, automation runs, manual sessions | Missions + Ideas |
| **World** | projects, repositories, systems, people, meetings, decisions, knowledge; list and graph views | Projects + World/Knowledge |
| **Control** | Autonomy & policy, Automations, Resources & routing (harnesses, accounts, models, sessions, nodes), Devices, Notifications, Appearance, About | Control + Infrastructure |
| Global: **Attention** | approvals, blockers, acceptance items, knowledge proposals, drift proposals | — |
| Global: **Command bar** (Ctrl/⌘+K) | intent box + jump-to-object + control verbs | Search |

Mapping of today's pages: Sessions → Work (manual sessions) and mission inspector (executions);
Memory, CLAUDE.md, Audit → World → project → Knowledge and Context; Plan → Execute → a mission;
Code Review → a mission template ("review what we've built"); Usage → Control → Resources;
Loops → Automations; Logs → Now activity (system filter); Skills/Plugins/Hooks/Agents/MCP/Output
styles → Control → Resources → *Claude Code* harness detail (they are that harness's
configuration); Accounts/Models/Harnesses → Control → Resources; Launch settings → Control →
Autonomy (defaults) and Resources (model defaults); Appearance → Control → Appearance.

## 18. Conversation model

- **One primary conversation** on Now, persistent across devices (ADR-0015). Each mission also
  has its own thread (mission inspector → Thread). A message in the primary conversation that
  acts on a mission is linked into that mission's thread, so the history of a mission reads
  whole.
- **Cards, not walls of text.** Replies carry typed cards bound to live objects: *Mission
  proposal* (objective, inferred assumptions highlighted, Start / Edit / Not now), *Plan* (tasks,
  approval points, cost band, Approve / Change), *Approval* (canonical action, Approve / Reject),
  *Route explanation*, *Diff*, *Verification result*, *Digest*. A card updates when its object
  changes; it never shows a stale copy.
- **Archeus can disagree.** A reply may contain a *Challenge* block: "Before I start: the meeting
  decided against server-side rendering; you are asking for it. Keep the decision, or supersede
  it?" with both choices as buttons.
- **Specific progress language** (HIG): "Reading Monday's notes and the dashboard module",
  never "Thinking…".
- **Control verbs work without a model**: `pause dashboard`, `resume`, `stop all`, `approve`,
  `why account B`, `status`. Typed in the composer or the command bar, parsed deterministically,
  answered from records. When every account is exhausted, Archeus can still be stopped,
  inspected and redirected.
- **Disclosure:** Archeus's messages are marked as AI-generated in the accessibility tree and
  carry the model used in their info popover (HIG transparency).

## 19. Mission UX

A mission has one inspector with fixed sections: **Outcome** (objective, success criteria,
explicit vs *inferred* requirements), **Plan** (DAG as a vertical list with parallel lanes,
current step highlighted), **Now** (active executions in plain language, progress computed from
the DAG), **Evidence** (verification checks, review verdict, diffs, artifacts), **Thread**,
**Why** (context package, policy decisions, route decisions), **Timeline** (events).

Mission list rows show: state glyph + label, title, project, one-line status ("Implementing chart
components — 3 of 7 tasks"), who it's waiting on, age. Never token counts or session ids.

Actions in context: Pause/Resume, Reprioritise (drag in list or priority menu), Change plan,
Accept result, Request changes, Cancel, Give feedback. Destructive ones confirm; everything else
is reversible from the timeline.

## 20. Project UX

A project page is a **status page for a living thing**: status line (one sentence Archeus
maintains), health (on track / at risk / blocked / idle), active missions, open decisions,
architecture state (consistent / stale / drifted), repositories with last inspection, knowledge
highlights, people, recent activity. Tabs: Overview · Missions · Knowledge · Architecture ·
Repositories · Sessions (manual) · Settings (project policy and resource rules).

## 21. Idea UX

Capture is frictionless ("I have an idea…" in the composer, or `+ Idea` anywhere). The idea card
shows its lifecycle stage as a compact stepper (Captured → Understood → Explored → Validated →
Concept → Planned → Scheduled → Implementing → Completed → Learned) with skipped stages greyed.
Archeus proposes the next step ("Explore: research how three products solve this — 1 small task,
web allowed") rather than jumping to execution. Promote → becomes a mission; the idea keeps a
link and follows its state.

## 22. World UX

List-first. Filters by kind (Projects, Repositories, Systems, People, Meetings, Decisions,
Knowledge) and by scope. Every object opens the same inspector pattern (header, state, relations,
provenance, timeline). **Graph view** is a toggle on the same data: focus an object → its 1–2
hop neighbourhood with fine lines; edge style encodes confidence (solid EXTRACTED, dashed
INFERRED, dotted AMBIGUOUS). See §26.

## 23. Knowledge UX

Knowledge items are shown with type, scope, confidence, provenance ("from Monday's meeting",
"inspected at 3f2a9c1", "you said on 12 Sep"), state (candidate / confirmed / superseded) and
their supersession chain. Proposals (candidates) arrive in Attention as one-line cards: "Remember:
*use Recharts for dashboards* (from the dashboard mission review)? Confirm · Edit · Dismiss".
Forget is explicit, shows a dry-run of what disappears from future context, and is undoable for
30 days.

## 24. Automation UX

Automations are written in plain language and shown back as a rule the user can read:
**When** a model file is added in *Payments* **and** it isn't under `tests/` → **Archeus will**
document it using *Documentation standard* → **Needs approval for**: commit to main → **Notify**:
when done. Before enabling, a *simulation* runs the trigger against the last 30 days of events
("would have fired 4 times"). Runs appear in Work with their missions; a suspended automation
(loop guard) is an Attention item with the reason.

## 25. Resource / control UX

Control → **Autonomy**: three profiles (Careful, Standard, Autonomous) as a starting point, then
a table of action classes × scope with ALLOW / ASK / WITHIN BOUNDARY / DENY, locked rows marked,
and a *simulate* box ("What if a mission tries to push to main in Payments?" → shows the
decision and the matching rules).

Control → **Resources**: accounts as rows grouped by harness with priority handles (drag),
allocation slider (ceiling %) with the reserve shown as a hatched band, live utilisation bar per
window, health state, fallback setting, project rules. A "preview route" box answers "where
would a large code task in Payments go right now, and why". Harness detail pages hold that
harness's configuration (for Claude Code: hooks, plugins, skills, agents, MCP, output styles —
today's pages, relocated).

## 26. Spatial UX

The spatial view is **an inspection instrument for relationships and state**, not a backdrop.

| Visual | Meaning (only this) |
|---|---|
| Cluster | a project (or a workspace at the widest zoom) |
| Node | a world object; shape by kind (circle mission, square repository, diamond decision, ring person, small dot knowledge) |
| Fine line | a real Relation; solid EXTRACTED, dashed INFERRED, dotted AMBIGUOUS |
| Energy (a light pulse travelling along a line or a node halo) | a live execution acting on that object right now — nothing else animates |
| Colour | the fixed state colours on missions; neutral for everything else |
| Distance | graph proximity from the focused object, not decoration |

Default is 2D fine-line (legible, accessible, cheap). A 3D mode may reuse the flat graph-scene
lineage from today's `stage.js` later; it is not in the V1 slice. Drill-down: world → project →
mission → execution by focusing. Every node is reachable by keyboard and the view has a list
equivalent (screen readers get the list).

## 27. Desktop UX

Three-column at regular widths: **sidebar** (Now, Work, World, Control; Attention badge; recent
missions pinned) · **main** · **inspector** (object detail, slides in, resizable). The composer
docks at the bottom of Now and is summoned anywhere by the command bar. Desktop conventions: tray
icon with *Pause all*, *Emergency stop*, *Open Archeus* (nothing critical at the bottom of the
sidebar — `sidebars.md`); native notifications; standard
shortcuts; right-click menus on list rows; hover states everywhere.

## 28. Mobile UX

Mobile is a **control and presence surface**. Bottom tab bar: **Now · Work · World · Attention**
(Control lives behind the avatar menu — it is rare on a phone). Approvals open as sheets showing
the canonical action and step-up PIN for destructive ones. Mission inspector collapses to
Outcome, Now, Evidence and Thread; Why is one tap. Pause/Resume/Stop are always reachable from
the mission sheet. 44 pt targets, safe areas, system text scaling.

## 29. TUI UX

Same four destinations as screens (`1` Now, `2` Work, `3` World, `4` Control, `a` Attention,
`:` command line). Dense rows with state glyphs and labels; the command line accepts the same
control verbs and intents as the composer. Colours come from the same tokens via ANSI derivation
(extending `themes.ansi_palette()`); every state is also a glyph so monochrome terminals work.

## 30. Visual language

"**Quiet instrument, living thread.**" Calm, dense-when-needed surfaces; typography and spacing
carry hierarchy; colour is reserved for state and for the one signature element. Appearance
follows the operating system (dark, light, increased contrast); the dark appearance is tuned
for long peripheral watching. Depth is used only to separate layers (base, surface,
inspector, sheet), never for decoration. Details in the design system.

## 31. Design tokens

Defined in [ARCHEUS_V1_DESIGN_SYSTEM.md](ARCHEUS_V1_DESIGN_SYSTEM.md) §3–9, generated from one
table (`clients/app/tokens/tokens.json`) into CSS variables, TypeScript constants and TUI ANSI
values.

## 32. Accessibility

Designed in, checked by gates (design system §15): contrast floors per theme with a High Contrast
theme; full keyboard operation with visible focus; screen-reader semantics for cards, live
regions for streaming progress (polite) and approvals (assertive); no colour-only state (glyph +
label); text scaling to 200% without loss; reduced motion removes the thread's travel animation
and all spatial motion; reduced transparency makes every surface opaque; targets per platform
floors; the spatial view always has a list equivalent.

## 33. Interaction / state model

Every visible object is one of a small set of **presentational states**, each mapped from domain
states (design system §10):

| Presentational state | Domain states (examples) | Glyph | Colour role |
|---|---|---|---|
| Active | EXECUTING, RUNNING, VERIFYING, REVIEWING | ● filled, animated only when output is flowing | `state.active` |
| Needs you | APPROVAL_REQUIRED, AWAITING_APPROVAL, acceptance BLOCKED | ◆ | `state.attention` |
| Blocked | BLOCKED (not waiting on the user) | ■ | `state.blocked` |
| Paused | PAUSED, PAUSING | ‖ | `state.paused` |
| Planning | UNDERSTANDING … PLANNING, REPLANNING | ◌ | `state.thinking` |
| Done | COMPLETED, SUCCEEDED | ✓ | `state.done` |
| Failed | FAILED, ENDED_ERROR | ✕ | `state.blocked` (red = a problem to resolve; glyph distinguishes) |
| Idle / archived | CANCELLED, ARCHIVED | – | neutral |

## 34. Key user flows

Each flow lists what the user does, what Archeus does, and what the system records. Phase
references point at the roadmap in the rearchitecture plan.

1. **Simple coding mission.** User: "Fix the flaky date test in Payments." → Grammar: not a
   control verb → brain with an L0–L1 package → Mission card (inferred: "flaky = fails on
   month boundaries") → plan of 2 tasks, all ALLOW within the project boundary → auto-approved →
   router picks Account A (P1) → execution in a worktree → CodeVerifier runs pytest → Review
   (different model) accepts → merge-back needs `git_commit` on main = ASK → Attention → user
   approves → COMPLETED; project status line updated; lesson candidate if the cause was
   non-obvious.
2. **Long-running coding mission.** "Build the dashboard" → plan of 9 tasks with a DAG, two
   parallel lanes, approval point before any dependency install → user approves plan → tasks run
   over hours; Now shows progress from the DAG; checkpoints at each task boundary.
3. **Mission survives session rotation.** Task 5's execution reaches pressure 0.78 → HANDING_OFF
   → Core derives a checkpoint (diff, checks, decisions, next action) → ENDED_HANDOFF → new
   execution on the same account (affinity) → user sees "continuing", mission state unchanged.
4. **Multiple accounts/models configured.** Control → Resources: A (P1, 100%), B (P2, 80%), C
   (P3, 50%); Codex account D for sandboxed tasks. Preview route shows where a large task would go.
5. **Router selects Account A.** RouteDecision records all candidates; mission Why tab shows
   "A: priority 1, 35% of 5-hour window, ceiling 80%".
6. **Account A reaches a limit.** Limit error → A LIMITED until 16:05 → checkpoint → re-route.
7. **Policy-controlled fallback selects B.** B `fallback: allow` → continue on B; Now:
   "Continuing on Account B — A is limited until 16:05". If B were `ask`, an approval card instead.
8. **Human approval required.** Execution tries `git push` → hook → policy ASK → approval bound to
   the action hash → execution halts → Attention + notification.
9. **Human approves remotely.** Phone notification (ntfy deep link) → PWA sheet shows the exact
   action (`git push origin archeus/msn_…`, 4 commits, diff hash) → Approve with idempotency
   key → Core performs the push itself (executions have no push credentials) → approval CONSUMED.
10. **Verification fails.** pytest fails on 2 tests → task VERIFYING → READY (retry with the
    failure output in L0) → fails again → FAILED → mission REPLANNING.
11. **Archeus replans.** Brain gets the failing evidence and the previous plan → plan v2 adds
    "reproduce locale bug" task → policy re-evaluates; approvals of v1 are SUPERSEDED; if still
    all ALLOW, auto-approved; replan budget 2.
12. **Repository re-inspected.** HEAD moved → architecture_state STALE → scheduled inspection
    (deterministic pass) → diff: new `api/` module importing `core/` internals.
13. **Architecture drift detected.** Constraint "core must not import api" violated → DRIFTED →
    Attention: *Update architecture* / *Accept change* / *Create fix mission*.
14. **Meeting notes become context.** User drops `2026-09-21-standup.md` → Meeting + artifact +
    decision candidates → later "use Monday's notes" → pinned into the mission's context; Why tab
    shows "included because you referenced it; contains decision D-12 about chart library".
15. **User gives feedback.** Thumbs-down on a plan with "don't add new dependencies for charts" →
    Feedback row → candidate PREFERENCE (project scope).
16. **Feedback becomes durable knowledge.** User confirms the proposal → CONFIRMED PREFERENCE;
    next plan's context package includes it at L1 with reason "your preference, 23 Sep".
17. **Event triggers automation.** `repository.model_added` in Payments → matcher → conditions
    true → policy (commit to main = ASK) → mission from template → documentation written →
    DocumentVerifier → approval for the commit → done → notification.
18. **User controls work from mobile.** On the phone: Now shows 2 active missions → user pauses
    *Dashboard* → PAUSING (cooperative) → PAUSED within one tool call → later Resume → executions
    resume with `--resume`.
19. **"Why did you choose this model/account?"** Control verb `why` → latest RouteDecision
    rendered from its record; no model call.
20. **"What is the current state?"** Deterministic status: per project status line, active
    missions with progress, needs-you count, resource health; optional one-paragraph summary by
    the brain on top, with every claim linked.
21. **"What changed while I was away?"** Digest from events after the per-user acknowledged
    cursor, grouped by mission/project; acknowledging on any device clears it everywhere.
22. **Idea → mission.** "I have an idea: a weekly digest email of mission outcomes." → Idea
    CAPTURED → Archeus asks two clarifying questions → UNDERSTOOD → proposes exploration → user
    says "plan it" → PLANNED → Promote → Mission with the idea linked.

## 35. Design decisions

| Decision | Status |
|---|---|
| IA = Now / Work / World / Control + Attention + command bar | DECIDED (ADR-0014) |
| One primary conversation + mission threads; typed live cards | DECIDED (ADR-0015) |
| Control verbs deterministic, no model | DECIDED (ADR-0006) |
| Fixed semantic state colours; skins/worlds not carried into V1 | DECIDED (ADR-0017) |
| Signature element: the thread | DECIDED (design system §2) |
| Spatial: 2D fine-line first, semantics only; 3D later | DECIDED (ADR-0016) |
| Mobile = PWA control surface with bottom tabs | PROPOSED (ADR-0010) |
| Approvals show canonical actions, never model prose alone | DECIDED (ADR-0007) |

## 36. Rejected alternatives

- **Chat-only UI** — state not inspectable; nothing to glance at; accessibility of long
  transcripts is poor.
- **Dashboard-first home with a chat side panel** — the current product's shape; puts metrics
  before meaning.
- **Agents as the primary list** (Munder Difflin's office floor, Vicoa's session list) — violates
  "work over agents"; users care about outcomes.
- **Keeping 32 palettes × 8 skins in V1** — cannot keep "one colour means one thing"; palettes
  survive as thread tints only.
- **3D world as the default home** — beautiful and slow to read; fails reduced-motion and screen
  readers; kept as an optional view later.
- **Native iOS app first** — needs a Mac and a paid developer account; the PWA over HTTPS
  reaches iOS and Android with one codebase.

## 37. Open questions

| # | Question | Owner | Blocks |
|---|---|---|---|
| D1 | Does the user want a spoken/voice channel (JARVIS model) in V1 or later? | user | nothing in V1 slice |
| D2 | Mobile PWA vs a thin native wrapper for push reliability on iOS (ntfy covers it for V1) | user | P15 |
| D3 | Should the legacy worlds survive as a "Classic" appearance of the V1 app? | user | P16 |
| D4 | Language(s) of the UI copy at launch (today English; user writes Italian too) | user | P16 copy |
| D5 | Onboarding: import everything from the current app automatically, or let the user choose projects? | user | P22 |

## 38. Implementation implications

- The client is a **new TypeScript/React SPA** (`clients/app/`), not a refactor of `web/app.js`;
  the legacy GUI keeps running until the retirement gate.
- The SPA must hold no business logic, render only from the API, subscribe to one event stream,
  and ship with no inline script (strict CSP).
- The repo's GUI gates are carried over as V1 gates: keyframes limited to transform/opacity,
  no backdrop-filter, container queries for component layout, overflow/dead-space audits,
  mutation-verified, with a floor on how much they checked.
- Tokens are generated from one table for CSS, TS and TUI.
- Every flow in §34 is an acceptance test in the V1 judge (testing strategy §2).

---

## Appendix A — Wireframes

Low-fidelity, structure only. Glyphs are the state glyphs of §33. `━━` marks the thread (the
signature line linking an Archeus message to the object it touched).

### A.1 Desktop — Now (regular width)

```text
┌──────────────┬───────────────────────────────────────────────────────┬──────────────────────────┐
│ ARCHEUS  ●   │  Now                          ⏸ Pause all   ◆ 2 need you│ Inspector (closed)       │
│              │                                                        │                          │
│ ▸ Now        │  Since you left · 3h                        [Dismiss]  │                          │
│   Work    4  │   ✓ Dashboard: 3 tasks done (5 → 8 of 9)               │                          │
│   World      │   ✓ Docs automation documented 2 new models            │                          │
│   Control    │   ◆ Auth: plan v2 waits for your approval              │                          │
│              │   ■ Payments: Account A limited until 16:05 → on B     │                          │
│ ◆ Attention 2│                                                        │                          │
│              │  Happening now                                         │                          │
│ Pinned       │   ● Dashboard  Implementing chart components  8/9 ━━┓  │                          │
│  Dashboard   │   ◆ Auth       Waiting: approve plan v2              ┃  │                          │
│  Auth        │                                                    ┃  │                          │
│              │  ─────────────────────── conversation ─────────────┃─ │                          │
│              │  You  Use Monday's notes for the dashboard.        ┃  │                          │
│              │  Archeus  Pinned "Standup 21 Sep" (decision D-12:  ┃  │                          │
│              │           Recharts, no SSR) into Dashboard. ━━━━━━━┛  │                          │
│              │           [Mission card: Dashboard · 8/9 · open]       │                          │
│              │                                                        │                          │
│              │  ┌──────────────────────────────────────────────────┐  │                          │
│              │  │ Tell Archeus what you want…            ⌘K  ⏎     │  │                          │
└──────────────┴──┴──────────────────────────────────────────────────┴──┴──────────────────────────┘
```

### A.2 Desktop — Mission inspector

```text
┌ Dashboard ─────────────────────────────── ● Active · P2 · Payments ──── [Pause] [⋯] ┐
│ Outcome   Plan   Now   Evidence   Thread   Why   Timeline                           │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Plan v1 (approved 09:12 by you)                                 cost band: medium    │
│  ✓ 1 Inspect dashboard module                                                        │
│  ✓ 2 Extract requirements from Standup 21 Sep                                        │
│  ✓ 3 Data layer ─┬─ ✓ 4 Chart components                                            │
│                  └─ ● 5 Filters   Claude Code · Account A · sonnet · 00:14:02        │
│  ○ 6 Tests      ○ 7 Presentation video (◆ human acceptance)     ○ 8 Review          │
│                                                                                      │
│ Why this account?  A is priority 1, 42% of 5-hour window, ceiling 80%. [details]     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### A.3 Mobile — Now and an approval sheet

```text
┌──────────────────────────┐   ┌──────────────────────────┐
│ Archeus ●     ◆2         │   │ ▔▔▔ (grabber)            │
│ Since you left · 3h      │   │ Approve push?            │
│ ✓ Dashboard 8/9          │   │ Mission: Auth            │
│ ◆ Auth needs approval    │   │ git push origin          │
│ ■ Payments on Account B  │   │  archeus/msn_7Q…/t3      │
│                          │   │ 4 commits · diff 9e1c…   │
│ Happening now            │   │ Policy: push = ASK       │
│ ● Dashboard   ▰▰▰▰▰▰▰▱▱ │   │ (Project rule, locked)   │
│                          │   │                          │
│ ┌──────────────────────┐ │   │ [ Reject ]  [ Approve ]  │
│ │ Tell Archeus…      ⏎ │ │   │ Step-up PIN required     │
│ └──────────────────────┘ │   └──────────────────────────┘
│ Now  Work  World  ◆Attn  │
└──────────────────────────┘
```

### A.4 TUI — Work

```text
 ARCHEUS ● 1 Now  2 Work  3 World  4 Control   ◆ 2 attention                    14:02
 ─ Work ─ Active ───────────────────────────────────────────────────────────────────────
 ● Dashboard        Payments   Implementing chart components           8/9   A·sonnet
 ◆ Auth             Identity   Waiting: approve plan v2                         —
 ‖ Docs refresh     Docs       Paused by you 11:40                     2/5   —
 ─ Blocked ─────────────────────────────────────────────────────────────────────────────
 ■ Migrate billing  Payments   All eligible accounts at ceiling · resets 16:05
 ───────────────────────────────────────────────────────────────────────────────────────
 :why dashboard                                        ⏎ open  p pause  a approve  ? help
```
