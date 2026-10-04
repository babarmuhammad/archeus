# Archeus V1 — Visual Architecture Reconciliation, Visual DNA and Design Traceability

**Status: APPROVED by the user, 2026-09-30 — the authoritative visual rulebook for the remaining
V1 work.** Decisions ADR-0024…0030 are DECIDED; P19.5 is approved and in progress; the P18 A8
amendment is approved (p18-design-gate §24) and built in P19.5. Q-A5 (browser-owned shortcuts)
is decided (§46.3). The V2 UI research boundary decisions (S-1…S-3, V-D1…V-D5) are recorded in §46.4. Still open from §46: Q-V6 (website, P25), Q-C1 (Classic appearance ownership), Q-C2
(reference archive). Date 2026-09-30. Branch
`archeus-v1-rearchitecture` at `5fa0bdb`.

This document is a **rulebook**, in the sense of the Anthropic migration kit (R5): a design
document that states what the V1 interface *is*, against which every later implementation phase
is judged. "If two agents could answer differently, it goes in the rulebook." An implementation
phase may not relax it; a change to it is an amendment the user approves (R5 standing rules 1
and 3: "The graded party does not relax its own grader"; "Do not proceed on inferred approval").

Nothing in the repository was changed to produce it except this file (untracked). No source,
CSS, TypeScript, Python, gate, ADR, test, route, security setting, launcher or git state was
touched. External repositories were read as shallow clones in the session scratchpad only.

---

## Contents

1. Purpose · 2. Source corpus · 3. Provenance · 4. Visual DNA · 5. Visual principles ·
6. Control-room / operational model · 7. Information hierarchy and density · 8. Shell ·
9. Now · 10. Work · 11. Relations · 12. Graph · 13. Knowledge · 14. Decisions · 15. Inspector ·
16. Devices / sessions · 17. Notifications, toasts, attention · 18. Command surface ·
19. Mobile and cross-device · 20. Accessibility · 21. Animation · 22. Performance · 23. Colour ·
24. Depth / materials / transparency · 25. Graph semantics and relationship confidence ·
26. Phase ownership · 27. Rejected concepts · 28. Conflict register · 29. Traceability matrix ·
30. Core / API dependencies · 31. Decisions requiring approval · 32. Current vs target ·
33. Generic-template adversarial review · 34. Manual visual acceptance · 35. Proposed ADR /
document changes · 36. Implementation roadmap · 37. Credits re-verified, skill collections,
claude-mem · 38. Final design tokens · 39. Component primitives · 40. Visual regression strategy ·
41. Additional discovery · 42. Surface state matrix · 43. Ideas and Resources · 44. Reference
archive strategy · 45. Validation results · Appendix A — method and evidence gaps ·
Appendix B — states: empty, loading, failure.

Vocabulary used throughout.

- **Final disposition** (per concept): **BUILT** (exists and stays) · **PRESERVED** (intent kept
  as specified, still to build) · **ADAPTED** (intent kept, mechanism changed) · **DEFERRED**
  (named later phase) · **REJECTED** (reason stated) · **NEEDS DECISION** (the user decides).
- **History status** (how V1 treated it so far): **A** explicitly rejected · **B** explicitly
  transformed · **C** explicitly deferred · **D** accidentally omitted · **E** never evaluated ·
  **F** partially implemented · **G** implemented · **H** contradicted by another document ·
  **I** currently unowned.
- **Provenance kind**: **INSP** inspiration · **PRIN** design principle · **TECH** visual
  technique · **IXP** interaction pattern · **IMPL** implementation (code actually reused) ·
  **DEP** dependency. No external code has been copied into the V1 client; every external row
  is INSP / PRIN / TECH / IXP unless it says otherwise.
- **P19.5** = the proposed new phase *Visual language and operational presence* (§26, Q-P1).

---

## 1. Purpose

V1's functional UI traces well; its visual and product character does not. The old architecture
(legacy GUI, constellation, stage, brand study, the credits) and the V1 references (five supplied
files, R1–R7) both asked for a *living system* that the user watches and steers. V1 rejected —
correctly, and with the user's approval — the old **implementations** (a perpetual loop,
`Math.random`, `sin(T)` breathing, bokeh, the ambient stage, skins and worlds). The **concepts**
those implementations carried (activity halos, travelling energy, the thread, the constellation,
controlled depth, operational presence, the brand mark) then disappeared without a decision.

This document restores them as **semantic, event-driven, bounded, deterministic, parking**
behaviour, gives each one meaning, provenance, an owner, an accessibility equivalent, a
performance budget and a test, and records every rejection with its reason.

The core principle, carried from the brand study's backdrop rule ("bounded, driven by real
state, and it stops") and the design system's "alive because things change, not because things
move":

```
DARK + STILL WHEN IDLE            zero scheduled frames, zero running animations
        ↓  a real backend event
ACTIVE + VISUALLY ALIVE           bounded, deterministic, capped, text-equivalent
        ↓  activity ends
QUIET AGAIN                        the last frame is the static state; the loop parks
```

---

## 2. Source corpus (outputs 1–4)

### 2.1 Generation 1a — the credits page (`docs/credits.md`, published at docs.claudectl.space/credits/#built-on)

| # | Credit | Contribution kind | Design contribution to V1 UI | Where it lands |
|---|---|---|---|---|
| C-01 | **Federico Coscia — the mark and banner** | branding | the gold **A** pierced by its orbit: "a bounded form with something in motion around it that never leaves" (brand-study §5.1) | §4 DNA-6, §8 |
| C-02 | microsoft/markitdown | architecture-only (ingestion) | none | — |
| C-03 | anthropics/claude-code `code-review` | workflow | none visual; confidence + threshold pattern echoes verification UX | Attention/verification copy (already built) |
| C-04 | thedotmack/claude-mem | memory / UX | *continuity between sessions* → "since you last looked" | §9 digest (BUILT) |
| C-05 | anthropics/claude-plugins-official | extensibility | none | — |
| C-06 | diegosouzapw/OmniRoute | architecture-only (routing) | none visual; routing explainability lives in P10 | — |
| C-07 | olsenbrands/fable-foreman | workflow | plan-then-delegate → mission plan / execution split | P6/P11 (BUILT) |
| C-08 | claudemarketplaces.com | extensibility | none | — |
| C-09 | VoltAgent/awesome-claude-code-subagents | extensibility | none | — |
| C-10 | topoteretes/cognee + Aider repo-map | memory / visualization | graph memory; token-budgeted retrieval → Relations and graph of record | §12, §25 (see also R4) |
| C-11 | DietrichGebert/ponytail | implementation-only (code minimisation) | none | — |
| C-12 | **furkankly/zoetrope** | visualization / interaction | a live flow graph of an agent session; **two clocks** (content time vs presentation time) | §21 rule M-R6, §12 P21 trace view |
| C-13 | starter skill collections (4) | extensibility | none | — |
| C-14 | Conventional Commits, Keep a Changelog | implementation-only | none | — |

Eleven of fourteen credits are not UI references and are recorded as such rather than forced into
the visual design.

### 2.2 Generation 1b — old architecture and old visual lineage

| # | Source | Inspected | What it contributes |
|---|---|---|---|
| L-A | `notes/brand-study.md` §5–8 | first-hand | mark tiers; `currentColor` glyph "the outstanding piece of work"; **"the app has no mark at all"** (a letter tile stands in); backdrop rule **"bounded, driven by real state, and it stops"**; "must not become a network diagram, a cloud, or a brain"; no tagline — the sidebar carries *context + a state line* (`N projects · M active`); "branding always defers to content" (citing HIG) |
| L-B | `notes/constellation-study.md` | first-hand | "nodes made of nodes" = the memory graph's own shape; trait 3 **white core inside a coloured halo, ring only on large hulls**; trait 10 **"something travels along the links… the clearest single statement that the links carry something rather than decorate something"**; trait 11 bloom on nodes only; trait 12 edge-to-edge |
| L-C | `notes/constellation-gap.md` | first-hand | gap 1 **"the hull is a translucent SOLID, not a bare wireframe — biggest miss"**: "in the 2D canvas the equivalent is a single filled convex path per hull at low alpha under the strokes"; gap 2 links are among the brightest things |
| L-D | `notes/cluster-handoff.md` | first-hand (quotes) | user judgements: "fine lines instead of all this mess"; "keep the complications… just remove the 3d part… a dot which has an outer circle"; inner web counter-rotation; rejected four-term node; **"the image is not the goal"** |
| L-E | `notes/cluster-spec.md`, `cluster.glb`, `connection.glb` | via AUDIT-1 | part list; conduit as coaxial triple (rejected by the flat pass) |
| L-F | `notes/reference/field-photo.jpeg` (FloatingPragma/observer-patch-holography) | viewed | the original constellation: fine wire cages, lit junctions, links |
| L-G | `notes/reference/cluster-render-single.png`, `-field.png`, `connection-render.png` | viewed | glowing glass cages, white-cored junctions, a conduit carrying gold/cyan beads — **travelling data inside a relation** |
| L-H | `notes/memory-ui-research.md` + rehaul notes | via AUDIT-1 | knowledge ordered by *when it is used* and what it costs; tables not cards; inline subtitle not tooltip; "too complicated — prioritise usability" |
| L-I | `notes/handoff-flowgraph.md`, `notes/parallel/track-b-session-flowgraph.md` | via AUDIT-1 | legacy `/flow` window built on zoetrope's behaviour |
| L-J | `claude_sessions/connections.py` (`/graph`) | via AUDIT-1 + P18 G4 | progressive disclosure, zones, lifting, search-expands-ancestors, rotating cage glyph, hulls α .05, particles on top-300 edges, pulsing halos, drag-to-move, expand/collapse-all, legend, tooltip |
| L-K | `claude_sessions/web/stage.js`, `motion.js`, `instruments.js` | via AUDIT-1 | `energy()` from running jobs; `shock()`/`impulse()`; five stops; one rAF that parks; the jobs banner's travelling `.beam` border; one-shot bursts |
| L-L | `claude_sessions/themes.py` | via AUDIT-1 | 39 palettes; "Terminal won because its transformation is in the chrome and its background is quiet. **Drama belongs in the interface, not the wallpaper.**"; graph world: "cards are nodes with connector stubs, rows are edges, the sidebar is a tree" |
| L-M | `references/*.png` (20 legacy captures) | `_doc_dash` viewed | the mark in the sidebar; a live cluster field behind translucent panels; instrument dashboard (rings, dial, equalizer) |
| L-N | `stash@{0}` → third-party dashboards (7 files) | 5 viewed | "Neon Stack Control" (build stream, container log, event bus, **code flow map with haloed live nodes**, deploy status, all ACTIVE-badged); Dreamgon HUD (**circuit traces ending in terminals**); sci-fi command deck (one centre, peripheral status); weather card dashboard (**the anti-pattern**); journey map (waypoints, upcoming vs done, "Resume"). `inline_image_preview.avif` not decodable; `large` is 0 bytes |
| L-O | `www/components/journey/scene.ts` | via AUDIT-1 | site constellation; "a node that blooms into a live graph"; copy is DOM so the page reads without WebGL |

### 2.3 Generation 2a — the five supplied V1 reference files (read first-hand, in full)

| File | UI/visual contribution (exact wording, location) |
|---|---|
| `Archeus_v1_prompt.txt` | "The GUI is a way to communicate with and inspect **a living system**" (142); "NOT merely a collection of CRUD pages" (144); home must show "what happened / what is happening / what needs attention / what Archeus is doing / what is blocked / what changed while the user was away / what decisions need the user / how to continue" (1299-1308); "Avoid turning the home screen into a metric dashboard" (1310); presence: "exists between conversations… active, paused, waiting, blocked, completed, changes while away, **upcoming work, background automation, recent decisions**, important events" (1367-1382); "Avoid artificial 'AI personality' gimmicks" (1384); spatial "may use clusters, nodes, fine-line relationships, **state-aware energy, depth, transparency, subtle motion**, spatial grouping" (1422-1431); "every visual metaphor must have semantic meaning" (1433); "The UI should make it clear that the assistant is **operating on the user's world**" (1338); "a serious premium tool" (1565); avoid "generic SaaS dashboards, excessive cards, meaningless gradients, excessive glassmorphism, noisy borders, generic AI chat UI, overuse of glowing elements, visual decoration without meaning, excessive 3D, fake 'futuristic' styling" (1567-1578); glow/glass/transparency/depth/gradients/energy/animation "must support hierarchy and meaning… coherent with the idea of a persistent intelligent operating layer" (1580-1592); "Do not simply adopt a generic shadcn, Material, Tailwind default, Apple clone, dashboard template" (1497-1505); wireframes/mockups + design review before implementation (1227-1228) |
| `Archeus_v1_System_Specification.md` | "The world model is a **living graph**" (91); home "should feel like Archeus is present" (886) with "ARCHEUS ● ACTIVE" (891) and the **only** "Good afternoon." (893); "Dashboard 68%" (903); world shows "projects, missions, systems, people, knowledge, agents, dependencies" (917-923); "Connections should be fine-line and visually light rather than heavy 3D tubes" (925); "Clusters should represent meaningful groups and state" (927); TUI "**pause all**" (942 — the only occurrence in all five files); do not copy "making a visual simulation the product itself" (1116); "Session 19 has 83k tokens" is the wrong copy (677-681) |
| `Archeus_v1_Implementation_Plan.md` | "Use the **existing Archeus visual direction** as a world-model visualization" (849); "clusters… fine-line connections… **transparent/lightweight relationships**… **state-aware glow/energy**… no heavy 3D tube effect… low-latency rendering… drill from world -> project -> mission -> execution" (853-859); "Visualization is an inspection layer, not the source of truth" (863); "remote stop… emergency circuit breaker… must work even when a long-running mission is executing" (907-910); "Mission blocked -> notify user" (751); the unification chain desktop→mobile→PC→desktop→TUI (878-890) |
| `…Design_and_Plan_FIXED.pdf` | "visualization is the primary way to **understand** the system" (p1, p9); "state changes as **light/energy**" (p10); "**fine-line, glass-like or transparent** relationship rendering" (p10); "Make state and activity legible without requiring the user to inspect raw logs" (p10); "fast enough for continuous monitoring" (p10); "The event system is the **nervous system** of Archeus" (p8); mobile may "Reprioritize missions and resource usage" (p9). Styling: light slate/navy, one amber accent |
| `…Architecture_Designs.pptx` | slide 9 "One core, multiple interfaces"; slide 10 progressive-disclosure stack; **slide 11 SPATIAL WORLD MODEL**: hub PROJECT CLUSTER with spokes MISSION · KNOWLEDGE · SYSTEM · PEOPLE · ARCHITECTURE · EXECUTION, "Fine-line relationships • transparent/lightweight geometry • state-aware energy"; slide 12 "Do not redesign the legacy UI first". Styling: `#161616` ground, monochrome grey rounded rects, 1.1 pt `#828282` lines, **no arrowheads, no colour, no glow** |

**Keyword facts** (first-hand sweep): "alive" and "pulse" appear in **none** of the five files.
The V1 vocabulary is *living system*, *living graph*, *nervous system*, *state-aware energy*,
*light/energy*, *subtle motion*. "Premium" appears once; "Good afternoon" once; "pause all" once.

### 2.4 Generation 2b — external references (inspected at source this session)

| Ref | Revision | Licence | What the source actually does (evidence) | Kind for Archeus |
|---|---|---|---|---|
| **R1 Munder Difflin** | v0.5.3 (2026-09-25) | MIT code; tiles under a separate asset licence | Electron + Pixi "desktop control room for the Claude Code agents you already run"; **two data planes** (PTY bytes + hook events) feed one renderer; "**An avatar walking *is* the status**"; "**every animation should actually tell you something**"; "**No ambient idle animations on static UI panels. Animation belongs to the game layer**"; status → behaviour table (working = seated + thought cloud with the live action; blocked = walks to the door with a blinking "!"; success = sparkle, and a cheer only if the busy stretch was long — "short turns do not celebrate over nothing"); **envelopes fly desk-to-desk on an arc for real messages, tinted by speech act, capped, one-shot**; a demo path that is "CAGED" (only when empty, stops at the first real process); ticker stops when hidden; selected-agent side panel with a **draggable width 320–1200**; command bar border turns by busy/blocked; **agent strip** of cards (status, model, context, current action); toasts stack, auto-dismiss only when non-blocking; OS notification when an agent blocks waiting for the human; "**animation is sugar, the ledger stays the truth**"; PR template requires BEFORE/AFTER captures of the real app. *Decorative idle life* (coffee breaks, errands) runs while agents are idle. Stations were specified and **superseded** in code by desk + thought cloud | PRIN, IXP, INSP |
| **R2 Vicoa** | main (2026-09) | AGPL-3.0 | multi-device control (web, Electron, Flutter, daemon); status enum with **left-border colour per session**; commit-then-broadcast realtime; socket-derived liveness, **offline machines greyed out**; mobile approvals "Allow once / Always / Deny", a question rendered as a picker; push with **badge = sessions awaiting your input**; continuity "Start at your desk. Steer from your pocket", **resume affordance at the dead end**, drafts retained, "Jump to unseen"; steer a queued message into a running turn; git diff, file browser, terminal beside the chat; task link drives status; automations with `next_run_at`; live preview and share links | IXP, PRIN |
| **R3 Graphify** | `1cd9a36c0c57` (2026-09-29) | Apache-2.0 / MIT | vis-network viewer: layout runs 200 iterations **then physics is disabled**; node size `10+30·degree/max`; labels only for nodes ≥ 15 % of max degree, others on hover; **EXTRACTED solid 2 px α .7, INFERRED/AMBIGUOUS dashed 1 px α .35** (indistinguishable from each other); relation text only in the tooltip `"{relation} [{confidence}]"`; community = colour only; **hyperedge hulls fill α .12**; sidebar search, info panel with clickable neighbours, **legend with a per-community show/hide checkbox**; `explain` and `path` are **text** tools (CLI/MCP): "--> Label [relation] [CONFIDENCE] file:loc", "Shortest path (N hops)", `max_hops` 8; bounded query by depth and **token budget**, seeds never cut | IXP, TECH |
| **R4 Cognee** | `ba3631f2ed36` (2026-09-29) | Apache-2.0 | `visualize_graph()` "renders a **bounded subgraph by default**": depth 2, 10 seeds, **max 500 nodes**; seeds from explicit ids > the answer's provenance ("the subgraph behind this answer") > query > top degree; truncation ranked by hop distance; force layout hard-stops; **memory map: "no force simulation, no randomness", "layout-once rule"**; timeline scrub "**as of run k**" changes **classes only, never positions**; feedback overlay `is-reinforced` / `is-weakened`; no graph-diff API | IXP, PRIN |
| **R5 code-migration-kit** | `cf91c9d5068d` (2026-07-08) | Apache-2.0 | a redesign migration makes "the rulebook… a **design document**"; "adversarial review of the design doc itself"; behavioural **judge** through the external interface that must fail on deliberately broken code; "Sign-off gates end the workflow… Do not proceed on inferred approval"; "Reviewers are adversarial, separate, and read-only"; "Unknown is an answer" | PRIN (process) |
| **R6 Apple Design Skill** | `6237cc12e323` (2026-09-29) | (skill) | five lenses in order (accessibility, platform, craft, interaction, content); the **point-of-view / template test** (quoted in §33); "Don't mistake delight for decoration"; "Is the boldness spent in one place? One signature element, everything around it quiet"; branding defers to content, don't repeat the logo; motion "never the only carrier of information", "avoid adding motion to UI interactions that occur frequently", "let people cancel motion"; alerts sparingly, destructive style always with Cancel; undo predictable, show its result; badges only for unread counts, never faked; no app-level appearance switch; targets mobile 44 pt (min 28), desktop 28 (min 20); text to 200 %; sidebar ≤ 2 levels; inspector titled by noun, updates with selection | PRIN |
| **R7 Ship Notes Components** | `550fb4c09db3` (2026-09-29) | MIT | easing `cubic-bezier(.22,.8,.18,1)` (ADOPTED by P16); one `_sync()` loop gate (connected / hidden / recording / context lost); **self-retiring loops** (stop below an energy threshold); frame-rate-independent smoothing `1-exp(-dt/τ)`; adaptive quality after N slow frames; **deterministic `renderAt(t)`** with no clock; its `filter: brightness()` dimming is a paint property and **must not be copied**; the orbs are *ambient by design* (they never self-retire while visible) | TECH, PRIN |

### 2.5 Generation 3 — current V1 (verified this session, file:line)

- **Shell:** `span.brand` "Archeus", text only (`App.tsx:208-221`); **the app icon is a diamond identical to the Attention nav icon** (`public/assets/icon-192.png`, `App.tsx:285`).
- **Thread:** `.thread-rule` static 2 px rule on Now digest rows only (`app.css:508`, `Now.tsx:83`). **`Message.links` — Core's record of "the world objects it touched" — is ignored by the SPA** (`Now.tsx:151-167`; Core writes it at `conversation.py:109-118`).
- **Energy:** one 240 ms opacity step on the live execution's edge, ≤ 1 per 2 s (`graph/model.ts:243-269`).
- **Loop:** `graph/loop.ts` only rAF caller; parks on hidden, blur, reduced motion, context loss, idle (P18 A9).
- **Animations:** `state-in` 160, `slide-in` 220, `sheet-in` 280, `dialog-in` 160, button press; `--dur-row/-pulse/-toast` defined and unused.
- **States:** text-only empties with no action; "Reading X…" (no skeleton); connection banner and `Fresh`; disabled-with-reason buttons; six confirm dialogs; **no undo anywhere**.
- **Graph:** 19 shapes; no legend; no expand/collapse-all; hover label; path; pin; search; tier dashes; **AMBIGUOUS is never written by Core** (`knowledge.py`), EXTRACTED for deterministic facts, INFERRED for model-described relations.
- **Terminology leaks:** raw ids, raw JSON, hashes and lowercased enums in many places; "Dismiss" and "Accept result" each name two commands; "Create one from Control" vs "from World".
- **Colour collision (measured this session):** `--focus #FFD166` vs `--state-attention #F2B544`, **CIE76 ΔE 12.3** — the design system's own ΔE ≥ 30 rule for thread tints is violated by the focus ring itself. The focused graph node's ring reads as "needs you".
- **Red misuse:** the narrow-graph note and every `Loadable` failure use `.unavailable` → `--state-blocked`.

### 2.6 Generation 4 — explicit decisions (what was rejected, and whether concept or mechanism)

| Decision | Authority | Rejected the CONCEPT or the MECHANISM | User-approved |
|---|---|---|---|
| ambient background stage not carried | ADR-0016 | mechanism (DR §7 keeps "one surface behind, driven by state" as principle) | ADR convention |
| 2D in V1, 3D later | ADR-0016, PLAN §31.2 | deferral | yes (P18) |
| skins / worlds not carried; palettes "survive as accent choices" | ADR-0017 | mechanism; text **contradicted** by DS §3.3 ("only as thread tints") | Q7 not recorded as the user's |
| no hue accent | PLAN App. B B.1 | concept (deliberate) | self-review |
| breathing glyph → one pulse per batch | PLAN App. B B.5 | mechanism | self-review |
| "no glow, no ambient motion" | P16 §20.10 | ambient/decorative glow; silent on "state-aware" | P16 gate |
| `Math.random`, `sin(T)` breathing, bokeh, never-parking loop, tween-into-layout | P18 L56, L104, A7, A9 | **mechanisms**, named | **yes, 2026-09-29** |
| energy = one 240 ms opacity step | P18 A8 | *narrowed* DR §26's "light pulse travelling along a line or a node halo" — the narrowing is **not** recorded as a deviation | A8 approved; narrowing unrecorded |
| no blur / backdrop-filter / blend / surface gradients | DS §6 | mechanism (Qt readback tearing, contrast) — not transparency | DS DECIDED |
| graph hidden < 600 px | P18 A12 | mechanism (a shrunken graph) | yes |
| motion never carries state alone; hidden reasoning never animated | P16 §18.1 r7–8 | concepts | P16 gate |

---

## 3. Provenance (output 25)

Every major concept, where it came from, and what kind of debt Archeus owes. "IMPL" appears only
where code was reused; in V1 that is only Archeus's own legacy mechanisms (P18 G4 ported them as
fresh TypeScript — IMPL of *our own* design, not of any external source).

| Concept | Old credits | Old arch / research | Old screenshots | V1 refs | R1 | R2 | R3 | R4 | R6 | R7 | Kind |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Activity halo | — | constellation t3; connections halos | graph world | IP "state-aware glow/energy" | work glow on the seated avatar | status dot + rail | ring overlay (preferred/contested) | — | — | orb state shape | INSP, PRIN |
| Execution pulse | — | stage `energy()`; B.5 | equalizer | DS §8 | — | — | — | — | "motion never only carrier" | self-retiring loop | PRIN, TECH |
| Travelling energy | — | constellation t10; conduits; connections particles | cluster render beads | PDF "light/energy" | **envelopes on arcs for real messages** | — | — | — | — | — | INSP, TECH |
| Thread | — | jobs `.beam`; "rows are edges" | — | PROMPT 1338 "operating on the user's world"; DS §2 | envelope to the door = escalation | "Jump to unseen" | — | provenance "subgraph behind this answer" | "boldness spent in one place" | — | PRIN |
| Constellation / clusters | FloatingPragma photo (uncredited) | study, gap, handoff | graph world field | SP 927, PPTX s.11 | the office floor as one map | — | communities | — | — | — | INSP |
| Hull as volume | — | gap 1 "biggest miss" | — | "transparent/lightweight geometry" | — | — | hyperedge hull α .12 | — | — | — | TECH |
| Depth by distance | — | trait 5, haze | — | PROMPT "depth" | — | — | — | truncation by hop distance | "avoid animating depth changes" | depth alpha | TECH |
| Mark + orbit as presence | **Coscia mark** | brand-study §5, §6 | sidebar mark | SP "ARCHEUS ● ACTIVE" | "portrait becomes the brand mark" | tray daemon status | — | — | "branding defers to content" | — | PRIN |
| Operations strip | — | brand-study state line | usage bar | PROMPT presence list | **agent strip** | session list, tray | — | — | — | — | IXP |
| Live map (operations map) | — | stage as instrument | graph world | PDF "visualization… to understand" | **the floor as status display** | — | — | bounded default view | — | — | PRIN, IXP |
| Command bar | — | Ctrl+K legacy | — | PROMPT "command interface" | command bar + input-state border | `#` references | — | — | search rules | — | IXP |
| Inspector (resizable) | — | list + detail | — | DS 360–560 | **side panel 320–1200 draggable** | — | info panel | — | inspector rules | — | IXP |
| Confidence styling | — | — | — | DR §26 | — | — | **EXTRACTED solid / INFERRED dashed** | — | — | — | TECH |
| Legend with filter | — | connections legend | — | — | — | — | **legend + show/hide** | — | — | — | IXP |
| Bounded neighbourhood | — | lifting, LOD | — | — | — | — | query depth + token budget | **seed + k-hop + cap 500** | — | — | PRIN |
| Layout once, never re-run | — | connections synchronous settle | — | — | — | — | physics off after stabilisation | **"layout-once rule"** | — | — | PRIN |
| Two clocks / replay | **zoetrope** | `/flow` | — | — | — | — | — | "as of run k", classes only | — | `renderAt(t)` | PRIN |
| Ephemeral activity chips | zoetrope (tool chips TTL) | — | activity eq job list | — | thought cloud with the live action | — | — | — | — | — | IXP |
| Resume at the dead end | claude-mem continuity | — | — | IP unification chain | — | **resume affordance** | — | — | — | — | IXP |
| Real-app evidence | — | "read the pages" lesson | legacy re-shoots | — | **BEFORE/AFTER on the real app** | — | — | — | — | — | PRIN (process) |
| Idle decoration | — | stage ambient | bokeh | — | coffee breaks | — | — | — | "delight ≠ decoration" | orbs ambient | **REJECTED** |

---

## 4. ARCHEUS VISUAL DNA (output 10)

**The one sentence.** *Archeus is a constellation of real work — clusters of things made of
things, joined by fine lines — that is dark and still until Archeus acts; then it shows exactly
where the work is (halo), that it is producing (pulse), which way it flows (travelling light),
and what Archeus's hand touched (the thread); and when the work stops, it is still again.*

The **one signature element** (R6: "boldness spent in one place") is the **thread**: the visible
link between what Archeus said or did and the world object that changed. Halo, pulse and
travelling light are the thread's grammar in the spatial view and in lists. The mark's orbit is
the thread's smallest form — the system itself, in motion only while working.

| # | DNA element | Communicates | Provenance | Today | P18 rejected… | Final | Owner | A11y equivalent | Performance |
|---|---|---|---|---|---|---|---|---|---|
| DNA-1 | **The thread** (ink line, list rule, spatial trace, tint) | Archeus's action → the object it changed | DS §2; PROMPT 1338; legacy `.beam`, "rows are edges"; R1 envelopes | rule on Now digest only; `Message.links` unused | nothing | **PRESERVED** | P19.5 | live-region sentence; row "changed" description | 1 travelling at a time |
| DNA-2 | **Activity halo** | this object has live work now | constellation t3; connections halos; IP "state-aware glow/energy"; Neon flow map; R1 work glow | none | the *pulsing* halo (mechanism) | **ADAPTED** — static ring | P19.5 | "running" in label and mirror | static layer, 0 frames |
| DNA-3 | **Execution pulse** | new output just arrived | DS §8; B.5; stage `energy()`; zoetrope `●` | graph edge only | breathing (mechanism) | **PRESERVED** + extended to rows | P19.5 | "output 4 s ago" | ≤ 12 concurrent |
| DNA-4 | **Travelling light** | work flowing along a real relation | constellation t10; conduit beads; PDF "light/energy"; R1 envelopes; Dreamgon traces | reduced to opacity step | ambient particles (mechanism) | **ADAPTED** — one marker per batch | P19.5 (A8 amendment) | mirror "live along *attempt of* → task" | ≤ 8 concurrent |
| DNA-5 | **Constellation** — cluster hull as a volume, fine receding lines, depth by graph distance, cored live nodes, static project cage | context, grouping, proximity | photo, renders, study, gap, handoff; SP 925-927; PPTX s.11; R3 hulls; R4 bounded views | clusters + 1 px lines | bokeh, random, rotation (mechanisms) | **ADAPTED** | P19.5 | mirror hops, grouping | static layer |
| DNA-6 | **Mark and orbit** as system presence | Archeus is present / working / needs you / disconnected | Coscia mark; brand-study §5-6; SP "ARCHEUS ● ACTIVE" | text only; icon = attention diamond | nothing | **ADAPTED** (Q-V2) | P19.5 | strip sentence | 1 one-shot ≤ 900 ms, ≤ 1 / 5 s |
| DNA-7 | **Operations strip** | persistent situational awareness | brand-study state line; R1 agent strip; R2 tray/status; PROMPT presence list | none | nothing | **PRESERVED** | P19.5 | `nav` landmark, throttled announce | DOM, one line |
| DNA-8 | **Operations map** | the "map in the middle" of live work | PDF thesis; R1 floor; R4 bounded view; command-deck ref | none | nothing | **NEEDS DECISION** (Q-A2) | P19.5 | the list beside it | ≤ 40 nodes |
| DNA-9 | **Quiet instrument** — neutral surfaces, colour only for state, red only for problems | trust at a glance | DS §1; ADR-0017; "Drama belongs in the interface, not the wallpaper" | yes, two violations (§23) | — | **BUILT** (defects to fix) | done / P19.5 | glyph + word | — |
| DNA-10 | **Silence at idle** | nothing is happening — truthfully | brand "it stops"; P18 A9; R1 "no ambient idle animations on static panels" | yes | — | **BUILT**, made an invariant test | P19.5 | — | 0 frames |

What is *not* DNA, and why: glow/bloom (reads as decoration, readback cost), glass blur (Qt
tearing, contrast), bokeh, per-cluster hues (colour belongs to state), rotation, 3D tubes, an
instrument dashboard, ambient backgrounds, idle "life" (R1 coffee breaks; R7 orbs) — §27.

---

## 5. Archeus V1 visual principles (derived, with provenance)

1. **An operational workspace, not a CRUD dashboard.** PROMPT 142-144, 1310; SP 21; legacy
   dashboard rejection; weather-card anti-pattern. *Test: no surface is a grid of metric cards.*
2. **Every visual variable states a fact.** PROMPT 1396, 1433; ADR-0016. *Test: every variable has
   a row in `encoding.ts` / `presentation.json`.*
3. **Motion is semantic, and motion is sugar over the record.** DS §1.3; P16 §18.1; R1 "animation
   is sugar, the ledger stays the truth". *Test: every animation has a trigger that is a backend
   event and a text equivalent.*
4. **Real activity looks alive.** PROMPT "living system", SP "living graph", PDF "nervous system";
   stage `energy()`. *Test: a live execution is visible on every surface that shows its object.*
5. **Idle is dark and still.** brand-study "it stops"; P18 A9; R1. *Test: zero frames and zero
   running animations for 10 s with nothing happening.*
6. **Space encodes context and causality.** constellation-study; PPTX s.11; R4. Distance = graph
   distance; travel = a real flow.
7. **One signature, spent in one place.** R6; DS §2. The thread; everything else is craft.
8. **Identity from the mark, the thread and the constellation — never from hue.** credits;
   themes.py lesson.
9. **Progressive disclosure, bounded by default.** PPTX s.10; R4 "bounded subgraph by default";
   R3 token budget.
10. **Accessibility and reduced motion are first-class.** PROMPT 1543-1557; R6 lens 1.
11. **Performance bounds every effect.** legacy flicker diagnosis; IP 858; PDF p10.
12. **Mobile keeps the language, not the layout.** PROMPT 1483; P18 A12; R2.
13. **Name things by what people control, never by internals.** SP 677-681; R6 content lens. No
    raw ids, JSON or enums in the primary reading path.
14. **Every effect answers "what does this communicate?"** or is removed (DS §2 removal test;
    R6 "remove one accessory").
15. **Drama belongs in the interface, not the wallpaper** (themes.py, verbatim).
16. **The record is replayable; animation is not replayed.** zoetrope's two clocks; R4 "classes
    only". A re-read or a seek never re-fires an animation.

---

## 6. Control-room / operational model (output 11)

What the user must be able to perceive, and where. R1's lesson governs: a control room is a
**status display in which the representation is the status**; R2's lesson governs continuity;
the weather-dashboard reference is the explicit failure mode.

| Question | Answer carrier | Surface | Data (exists?) |
|---|---|---|---|
| What is happening now? | Operations strip count + Happening now rows with halo | shell, Now | `/v1/status` (unused today), missions reads ✓ |
| What is running? | rows with ● + halo + recent-output chip | Now, Work, graph | executions ✓, `execution.*` frames ✓ |
| What is waiting? | Work groups by what they wait on | Work | ✓ |
| What needs attention? | Attention badge + Needs you (top 3) + strip | shell, Now, Attention | `/v1/attention` ✓ |
| What changed? | thread rule on rows | every list | `/v1/digest` ✓ |
| Where did it change? | thread line to the row / spatial trace | Now, graph | `Message.links` ✓ (unused), frame subjects ✓ |
| What caused it? | "because" line in the row / Why tab | inspector | `cause_chain` for automations only ✓; general cause ✗ (Q-B1) |
| What did it affect? | Relations + trace | inspector, graph | recorded relations ✓; execution→object ✗ (Q-B1) |
| What is next? | Upcoming | Now | ✗ no schedules / `next_run` (Q-B2); approximated by APPROVED/PLANNING missions |
| What was decided? | Recent decisions | Now, Attention → Decided | approvals `decided_at` ✓, policy/route decisions ✓; Decision entity never written |
| Which resources? | compact resource line on execution rows + Control → Resources | Work, inspector, Control | route decisions ✓ |
| What is connected? | device count in strip + Clients | shell, Control | presence (in memory) ✓ |

**Mechanisms (not widgets):**

- **O-1 Operations strip** (shell, one line): mark with orbit state · "2 running · 1 needs you ·
  3 clients" · freshness · **Pause all** (Core-required) · Emergency stop behind confirm. R1 agent
  strip → compressed into counts because Archeus's unit is the mission, not the agent (SP 1114
  "do not treat agents as the primary abstraction").
- **O-2 Happening now** rows = R1's agent card translated to missions: state, title, *current
  action* as an ephemeral chip (zoetrope chips: TTL 2.5 s, ≤ 3 per row), progress as a fraction,
  resource line in metadata. The chip text comes from `execution.*` frames re-read (never from the
  frame payload — ADR-0009).
- **O-3 Since you last looked** with the thread rule (BUILT, extend).
- **O-4 Operations map** (NEEDS DECISION): a bounded spatial view of *currently active* missions
  and their executions (R4 seed = active missions, depth 1, cap 40), ≥ 1000 px only, click-through
  to the full graph. R1's floor translated into Archeus's graph of record — no avatars, no office.
- **O-5 Upcoming** and **O-6 Recent decisions** (§9).
- **O-7 Activity stream** (typed events in words, each linking its object): Control → Activity
  list in P19.5; the replayable trace in P21.
- **O-8 Devices / sessions presence** (§16).

Disposition of R1's control-room elements:

| R1 element | Underlying principle | Archeus disposition |
|---|---|---|
| desktop control room | one place to watch and steer real processes | **ADAPTED** — Now + strip + map |
| 2D operational floor | the map *is* the status | **ADAPTED** — operations map over the graph of record (Q-A2) |
| avatars tied to real processes | representation = state | **ADAPTED** — nodes/rows with halo + chip; **avatars REJECTED** (personality gimmick, PROMPT 1384; agents are not the primary abstraction, SP 1114) |
| stations | semantic activity zones | **REJECTED** as zones (R1 itself superseded them); intent carried by the action chip |
| selected-object side panel | detail beside the map | **BUILT** (inspector) + resizable (**PRESERVED**) |
| raw terminal in the panel | authenticity | **ADAPTED** — execution Output tab (BUILT); a live PTY is out of V1 scope |
| command bar with input state | intent entry that shows readiness | **ADAPTED** (§18) |
| agent strip | fleet at a glance | **ADAPTED** — operations strip counts + Happening now |
| layered z-structure | predictable layering | **PRESERVED** — z tokens (§24) |
| right panel → drawer | responsive detail | **BUILT** (inspector replaces main < 1000, sheet < 600) |
| toasts | off-screen completion | **PRESERVED** (§17) |
| tooltips | on-hover detail | **ADAPTED** — hover label (BUILT) + legend; no tooltip-only information (R6) |
| brand consistency, real-app evidence | one mark, BEFORE/AFTER captures | **PRESERVED** (§8, §34) |
| idle decorative life | "lingering feels purposeful" | **REJECTED** (principle 5) |
| envelopes for real messages | a message travelling between actors | **ADAPTED** as DNA-4 / thread T1 |
| caged demo path | a demo that can never impersonate real state | **PRESERVED** as a rule: any fixture/demo motion is impossible while real Core data is present |

---

## 7. Information hierarchy and density

### 7.1 Hierarchy (every surface, in this order of visual weight)

1. **Attention** — something needs you (amber ◆, earned, never more than three on Now).
2. **Active work** — what is running (● active blue, halo, chip).
3. **Change** — what moved since you looked (thread rule).
4. **System presence** — persistent but the quietest element on screen (strip).
5. **Relationships** — Relations / graph.
6. **Context** — project, resource, knowledge used.
7. **Detail** — inspector tabs.
8. **History** — timeline, activity stream, trace.

Presence is *always visible and always quiet*; attention is *rarely visible and always loud*.
That inversion is the control-room rule (the command-deck reference: one centre, peripheral
status).

### 7.2 Density

The current UI spends density badly: Work at 1440 × 900 is two 33 px rows over ~700 px of
nothing; Now leaves its right half empty below a 180 px conversation panel. The target is
**operational density**, not whitespace:

| Element | Target |
|---|---|
| list row | two lines when live (title + state; chip + fraction + age), one line otherwise; 32 px comfortable single line |
| Now | two columns ≥ 1280 px: left = needs you / happening / since you looked / upcoming / decisions; right = operations map over conversation |
| Work | groups collapse when empty; a live group shows its execution chips; right column shows the selected mission's plan rail when the inspector is closed ≥ 1440 px |
| strip | one line, ≤ 6 facts |
| graph | labels on tier 0–1; LOD dots > 250 (BUILT) |
| inspector | key-value blocks at 13 px caption labels; no raw JSON in the default tab |
| compact density | **DEFERRED** (V1.x) — DS names it; V1 ships one tuned density |

---

## 8. Shell and brand (output 16)

| Place | Target | Today | Owner |
|---|---|---|---|
| header left | the **mark** (monochrome `currentColor` glyph of the A + orbit, 20 px) + "Archeus" | text only | P19.5 |
| mark orbit node | presence indicator: neutral = idle · `active` = executions running · `attention` = needs you · hollow = disconnected. On a batch of activity the node travels once round the orbit (≤ 900 ms, ≤ 1 per 5 s) and parks. Reduced motion: colour only | none | P19.5 (Q-V2) |
| header centre | operations strip (O-1) | banner only | P19.5 |
| header right | command bar button (BUILT) | ✓ | — |
| app icon / favicon / PWA | the dark tile mark (`docs/assets/logo.png` via `tools/make_icon.py` tiers) — **replacing the diamond, which collides with Attention** | attention diamond | P19.5 |
| loading (boot) | mark + "Connecting to Archeus…" | "Connecting…" | P19.5 |
| empty states | no mark (R6: "don't repeat the logo"); identity carried by the state sentence and one action | text | P19.5 |
| elsewhere | nowhere else | — | — |

Why the glyph is the cluster/cage and not a letter: brand-study §8 — "cut *after*
constellation-study lands, from the cluster" — so the in-app mark and the static project cage
(§12) are one figure at two scales, as the site already treats them. The gold/cream artwork
stays artwork (credits); the in-app glyph is monochrome (the app has no hue accent, B.1).

---

## 9. Now

| Element | Status | Disposition | Data | Owner |
|---|---|---|---|---|
| **state sentence** in the display role ("Archeus is working on 2 missions. 1 needs you.") replacing "Archeus · 2 missions active · 0 things need you" | F | **ADAPTED** — resolves the greeting conflict; no time-of-day personality (PROMPT 1384) | counts ✓ | P19.5 (Q-V4) |
| Needs you (top 3) | G | BUILT | ✓ | — |
| Happening now with halo + chip + fraction | F | **PRESERVED** | ✓ + frames | P19.5 |
| Since you last looked + thread rule | G | BUILT; stop showing raw repository ids | ✓ | P19.5 (copy) |
| **Upcoming** (APPROVED / PLANNING missions now; scheduled automation runs when Core has schedules) | I | **PRESERVED** in two steps | partial ✓; schedules ✗ | P19.5 (list) · P21 (Q-B2, ADR-0030) |
| **Recent decisions** (decided approvals, route decisions that changed a route, DECISION knowledge) | I | **PRESERVED** (client-composed) | ✓ approx | P19.5 |
| operations map | E | **NEEDS DECISION** | graph ✓ | P19.5 (Q-A2) |
| conversation with typed cards + **thread T1 from `Message.links`** | F | **PRESERVED** | ✓ | P19.5 |
| composer preview "Archeus will…" | recorded not built | **DEFERRED** | intent preview needs Core | P21 |
| background automation line ("2 automations watching") | I | **PRESERVED** | automations ✓ | P19.5 |

Must be visible without navigating: state sentence, needs you, happening now, since you looked.
One scroll away: upcoming, decisions, conversation history.

---

## 10. Work

| Element | Status | Disposition | Dependency | Owner |
|---|---|---|---|---|
| groups by what it waits on | G | BUILT | — | — |
| live row: halo, pulse, chip, fraction, resource line | F | **PRESERVED** | frames ✓ | P19.5 |
| thread rule on changed rows | D | **PRESERVED** | digest ✓ | P19.5 |
| pins | D | **ADAPTED (D-9, §46.1)**: a Pinned group at the top of Work at every width, not the sidebar (local preference, never sent) | none | P19.5 |
| context menu (desktop, same actions as visible buttons; Shift+F10) | D | **PRESERVED** | none | P19.5 |
| reprioritise | D | **ADAPTED (D-14, §46.1)**: an absolute "Priority N" set by Core's one command; drag and Alt+↑/↓ are a recorded deviation, waiting for a later Core reorder verb | **Core**: set mission priority (built, `cde51b3`) | P19.5 (R10b) |
| Pause all | D | **PRESERVED** | **Core**: bulk pause verb; e-stop is kill + BLOCKED, not pause (Q-B3) | Core first, then P19.5 |
| approval / verification inline state | G | BUILT | — | — |
| ideas stepper (CAPTURED → UNDERSTOOD → … → LEARNED, states exist in `states.py:53-73`) | D | **ADAPTED (D-11, §46.1)**: read-only — no transition API | ✓ | P19.5 |
| operational density | F | §7.2 | — | P19.5 |

---

## 11. Relations (the list form)

Relations stays the **authoritative accessible representation** of the graph (P16 §20.13) and the
mobile form (A12). Target additions: the legend's line styles as swatches (BUILT) with the tier
word replaced by plain language ("recorded" / "suggested by Archeus"); "live" and "changed since
you looked" marks on rows (thread T2/T3 equivalents); relation explanation text ("Archeus linked
these because…") where the record carries one. P19 moves Relations onto `/v1/world/graph`
(already planned); P19.5 adds the marks. No second relation model.

---

## 12. Graph / constellation (output 12)

| Aspect | Target | Provenance | Status → Final | Owner |
|---|---|---|---|---|
| node identity | shape = kind (19, BUILT); **live node gets a light core dot** ("a dot which has an outer circle") | handoff quote; t3 | F → ADAPTED | P19.5 |
| state | state colour on mission/task/execution (BUILT) | DS | G → BUILT | — |
| activity | **halo** (DNA-2) | §4 | D → ADAPTED | P19.5 |
| energy | **travelling marker** (DNA-4) + existing pulse as degraded form | §4 | B → ADAPTED | P19.5 (A8 amendment) |
| relationship | recorded relations only; straight; no arrowheads (PPTX has none) | P18 A3 | G → BUILT | — |
| confidence | §25 | R3 | F → ADAPTED | P19.5 |
| focus | ring in **thread ink**, not amber (§23) | ΔE measurement | defect | P19.5 |
| context / depth | 3 opacity tiers by hop distance (100 / 64 / 36 %) | t5; R4 | F → ADAPTED | P19.5 |
| cluster | project hull as a **filled volume** (neutral ≤ 6 %, focused 10 %), one path under the strokes | gap 1; R3 hull α .12 | D → ADAPTED | P19.5 |
| project glyph | **static** 12-junction cage at world level ≥ 48 px; circle below; **no rotation** | connections.py; brand | D → NEEDS DECISION (Q-V3) | P19.5 |
| grouping | project = cluster (BUILT); community detection **REJECTED** (the graph infers nothing) | P18 | — | — |
| important nodes | size = **open work** (missions not settled, tasks running), long-tail clamped; not degree | R3 degree sizing, adapted to a real magnitude | E → ADAPTED | P19.5 |
| search | BUILT (expands ancestors, centres) | connections, R3 | BUILT | — |
| path | BUILT; add the **text form** in the mirror ("3 steps: A → implements → B …") | R3 path output | F → ADAPTED | P19.5 |
| explain this node | "Why is this here?" = the inspector's Relations tab with the relation's recorded reason; no model call | R3 `explain` | E → ADAPTED | P19.5 |
| pin | BUILT (in memory) | — | BUILT | — |
| legend | generated from `encoding.ts`; collapsible; **each kind/tier row toggles visibility** | connections legend; R3 legend checkbox | D → PRESERVED | P19.5 |
| expand all / collapse all | two buttons + keys | connections.py | D → PRESERVED | P19.5 |
| tooltips | hover label (BUILT) + state word; nothing only in a tooltip | R6 | F → ADAPTED | P19.5 |
| selection → inspector | Enter/double-click (BUILT); the camera does not move on open | P18 | BUILT | — |
| bounded loading | depth 1/2 (BUILT); cap + "+N more" (BUILT) | R4 | BUILT | — |
| layout | deterministic once, static; never re-runs by itself | P18 A7; R3; R4; zoetrope ("jumpy") | BUILT | — |
| drag-to-move | **REJECTED** (§27) | — | — | — |
| scrub "as of" / replay | classes only, never positions; two clocks | R4; zoetrope | E → DEFERRED | **P21** trace view |
| operations map mode | a bounded, live-only view reusing the same renderer | §6 O-4 | E → NEEDS DECISION | P19.5 |
| 3D mode | lineage of the flat graph scene | ADR-0016 | C → DEFERRED | **V1.x-3D** |

---

## 13. Knowledge

Target: rows show type, state, provenance and **when it is used** (always in context / when
relevant / stored) plus "updated N ago" (legacy memory-UI lesson), and the forget flow uses Core's
existing **dry run** (`/v1/knowledge/forget`, dry_run defaults true) as its preview. **No undo is
offered**: RETRACTED is terminal and purge blanks content; P16 §18.3 forbids simulating an
inverse Core does not have. "When used" may need a Core field (Q-B6, verify before building).
Confirm/reject marks follow R4's reinforced/weakened idea as a one-shot state change (A-01), not a
new overlay. Owner P19.5. People/organisation knowledge as graph nodes: **DEFERRED to P22**
(no person table).

## 14. Decisions

A **Recent decisions** block on Now and a **Decided** section in Attention, composed on the client
from `/v1/approvals?state=` (`decided_by`, `decided_at`), `/v1/route-decisions`,
`/v1/policy-decisions` and DECISION-type knowledge, each row linking its inspector. A true unified
decision log (the `Decision` entity is defined and never written; no `since`/paging) is a Core
dependency (Q-B7) — the client version is honest about being "recent approvals and route choices".
Owner P19.5.

## 15. Inspector

| Aspect | Target | Source | Owner |
|---|---|---|---|
| width | **resizable** 360–560 (DS), thin divider, keyboard resize (Alt+←/→), remembered locally | DS §5; R1 320–1200; R6 split views | P19.5 |
| title | a noun phrase naming the object, never an id | R6 | P19.5 |
| live state | header shows state + halo + freshness | DNA-2 | P19.5 |
| relationship summary | Relations tab (BUILT) | — | — |
| provenance / why | Why tab (BUILT); cause line "caused by automation X" where `cause_chain` exists | Core ✓ for automations | P19.5 |
| actions | same verbs as rows; destructive with Cancel default (BUILT for six; add for Reject approval, Reject review) | R6 alerts | P19.5 |
| raw data | ids, hashes and JSON move behind a "Details" disclosure | SP 677; R6 | P19.5 |
| not a second navigation | no nested inspectors; a link inside opens the object *in place* and Back returns | UIA | rule |

## 16. Devices / sessions

Clients list with presence (connected / recent / absent / revoked — BUILT), "last seen", and the
session each client is on; **offline clients greyed** (R2); the strip counts connected clients.
Presence is in memory in Core (a restart reads everyone absent) — acceptable, noted. **Resume
affordance at the dead end** (R2): an ended or handed-off session shows "Continue on …" where
P12's continuity permits it. Sessions stay under Control (ADR-0004). Owner P19.5 (UI), P12/P15
already own the mechanics.

## 17. Notifications, toasts, attention

| Signal | Belongs in | Rule | Dependency | Owner |
|---|---|---|---|---|
| approval required | Attention + badge + strip; push later | badge = count of items that need you, never faked (R6, R2) | ✓ | BUILT / P19.5 |
| agent/mission needs input | Attention (planning block) | same | ✓ | BUILT |
| task/mission complete | the row's state change; **toast only if off-screen** | R6 "confirm only significant completions" | ✓ | P19.5 |
| error / failure | inline next to the thing; red only if it needs resolving | DS §9; R6 | ✓ | BUILT |
| recoverable command refusal | inline reason (BUILT) | — | — | — |
| destructive confirm | modal dialog, Cancel default | R6 | ✓ | BUILT (+2) |
| undo | only where Core has an inverse (none today) | P16 §18.3 | Core per verb | rule |
| system / OS notification (desktop) | only for approval required and e-stop, while the window is hidden | R1 notifies when blocked on the human | Core `notify_default` is dead metadata (Q-B5) | P20 |
| mobile push | same two classes | P15 D20 | Core notification record + transport (Q-B5) | P20 |
| attention arrival | one 240 ms pulse on the badge when the count increases | A-08 | ✓ | BUILT (P19.5, §46.2) |

## 18. Command surface

The web UI keeps its command bar (BUILT) and becomes a real **palette**: arrow-key selection
(today every option is `aria-selected=false` and only the first hit is reachable), server-backed
search over missions/projects/knowledge (today cache-only — **D-12, §46.1: stays cache-only in
P19.5; server search is P21's**), **object-scoped actions** ("Pause
*Dashboard*", "Open *Atlas* as a graph") that call the same Core verbs as the buttons, and the
effect preview UIA §5 specifies ("Pause *Dashboard* — 2 executions will halt"). The input border
shows readiness (R1): neutral when live, amber when reconnecting, disabled with a reason when a
scope is missing. "Tell Archeus: …" stays and adopts the keyed-retry idempotency pattern (today a
fresh UUID per click). **No policy or authorisation in the palette** — every action routes through
Core (P9–P14). Owner P19.5; the TUI's `:` command already shares the vocabulary (P17).

## 19. Mobile and cross-device (output 18)

- **One architecture** (P15 PWA): no second mobile model.
- **Survives:** state glyphs; halo as a ring on the row's glyph; pulse on rows; thread rule;
  compact strip (mark + counts); approval cards; PIN step-up; sheets; 44 px targets; safe areas.
- **List-based:** graph < 600 px (A12) with live/changed marks; operations map hidden.
- **Gestures:** long-press = context menu; **swipe reveals a row's actions and never performs
  one** (ADAPTED, P19.5, §46 — an accidental approve or defer is a safety cost; never from a
  screen edge, where iOS owns back-swipe); **pull-to-refresh REJECTED** (mobile browsers own the
  pull-down reload gesture, and the stream plus freshness keep the screen current).
- **Continuity (R2):** "Start at your desk, steer from your pocket" is Archeus's P19 unification
  scenario; add the **resume affordance** and "Jump to unseen" (digest) on mobile Now.
- **Mobile operator controls:** pause/resume mission, Pause all (Core), e-stop (confirm + PIN).
  Mobile policy/routing edits: read + limited, admin scope (UIA, as built) — the references
  disagree among themselves (§28 X-11).
- **Notifications:** P20 (push) — §17.
- **Live preview, share links, file browser, git diff, terminal on mobile (R2): REJECTED for V1**
  (out of Archeus's role: mobile "controls and observes", SP 826-828; share links are a new
  exposure surface for P20/P24 to reason about, not a visual feature).

## 20. Accessibility (output 19)

The graph mirror remains authoritative. Every visual concept has a non-visual form:

| Visual | Equivalent |
|---|---|
| pulse | "output 3 s ago" (text updates, throttled; nothing announced per pulse) |
| halo | "running" in the row/node label and the mirror |
| travelling light | mirror row "live along *attempt of* → *task*" |
| thread T1 | polite live region "Archeus updated *Dashboard*"; the card/link |
| thread rule | "changed since you last looked" in the accessible description |
| colour | glyph + word (BUILT) |
| glow / focus | `aria-selected` / focus ring in thread ink |
| spatial proximity / depth | "2 steps from *focus*" in the mirror |
| hull / cluster | "in project *Atlas*" |
| orbit presence | strip sentence (`role=status`, change-only, ≤ 1 / 30 s) |
| attention pulse | count in the tab name + polite announce |
| toast | `role=status`, never the only signal (the row changed too) |
| reprioritise | a number field with its label ("Priority"), D-14 — no drag is built |
| context menu | Shift+F10 / menu key; same actions visible elsewhere |
| legend toggles | real checkboxes |
| forced colours | halos → 1 px solid ring; thread → 2 px `Highlight` |
| reduced transparency | all §24 alphas → opaque |

R6 floors also adopted: text to 200 %; desktop targets ≥ 28 px (min 20), phone ≥ 44 px (BUILT);
motion cancellable (no one waits for an animation — markers never block input); **Ctrl+1/2/3 and
Ctrl+J collide with browser tab/downloads shortcuts** (R6 "never repurpose standard shortcuts")
→ Q-A5, DECIDED 2026-10-03: Alt+1/2/3 and Alt+J (§46.3).

## 21. Animation architecture (output 13)

**One registry** (generated `motion.json`, read by SPA and gates). An animation not in it fails
the build.

| ID | Animation | Meaning | Trigger (backend) | Duration | Repeat | Concurrent cap | Surfaces | Cost | Idle | Reduced motion | A11y equivalent | Mobile | Test |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A-01 | state change | state changed | row state ≠ last render | 160 ms | once | per row | all lists, inspector | CSS opacity/transform | never | instant | glyph + word | same | e2e state flip |
| A-02 | execution pulse | output produced now | `execution.*` frame for a visible object | 240 ms opacity | ≤ 1 / object / 2 s | 12 canvas; DOM unbounded (compositor) | rows, graph | canvas: 1 path; DOM: compositor | never | removed | "output N s ago" | rows | fake clock: frame → exactly one pulse; rate limit |
| A-03 | activity halo | live work here | presentation class `active` | static | — | unlimited | graph, row glyph | static layer | **static, 0 frames** | kept | "running" | ring on glyph | unit: halo ⇔ active; idle 0 frames |
| A-04 | travelling light | work flowing along this relation | `execution.*` frame on a drawn live edge | ≤ 600 ms, constant speed along the edge (source execution → task/mission) | once / batch | 8 (oldest dropped) | graph, operations map | 1 short path over static-layer copy | never | removed; live edge 2 px | mirror "live along…" | none (< 600 px no canvas) | deterministic `renderAt(t)`; cap; RM zero |
| A-05 | thread travel (T1) | Archeus acted on this object | a new Archeus message with `links[]` whose target row is on screen | ≤ 600 ms draw-on | once | 1 (queue drops) | Now, mission Now tab | CSS/WAAPI transform/opacity | never | rule appears, no travel | live region | rule only | e2e: link → correct row, once |
| A-06 | thread rule fade | seen | digest ack | 200 ms | once | — | lists | CSS | never | instant | — | same | e2e |
| A-07 | orbit presence | Archeus working | batch of `execution.*` frames | ≤ 900 ms | ≤ 1 / 5 s | 1 | shell | CSS transform | never | colour only | strip text | same | frame-count |
| A-08 | attention arrival | something new needs you | attention count increased | 240 ms | once | 1 | nav badge | CSS | never | removed | announce | tab badge | e2e |
| A-09 | hover | affordance | pointer (fine) | 160 ms | — | — | controls | CSS | — | instant | focus ring | none | — |
| A-10 | selection | selected | user | instant | — | — | lists, graph | — | — | — | `aria-selected` | same | — |
| A-11 | focus | keyboard focus | user | instant | — | — | all | — | — | — | ring | same | axe |
| A-12 | loading | shape of what is coming | request pending | static skeleton | — | — | lists | none | static | same | "Loading X" | same | e2e |
| A-13 | toast | done off-screen | success not visible | 160 / 4000 / 160 ms | once | 1 | shell | CSS | never | no fade | `role=status` | top of sheet | e2e |
| A-14 | camera settle | where you moved | focus / search / fit | ≤ 240 ms | once | 1 | graph | loop | never | jump | focus announce | — | BUILT |
| A-15 | layer open | layer changed | open/close | 220 / 280 / 160 ms | once | — | inspector, sheet, dialog | CSS | never | instant | focus moves | sheet | BUILT |
| A-16 | graph layout | — | — | **none**: computed once, static; never re-runs by itself | — | — | graph | CPU once | — | — | — | — | BUILT |
| A-17 | activity chip | current action | frame → re-read execution | fade in 160, TTL 2.5 s (4 s on error) | per action | 3 / row | rows | CSS | never | no fade | chip text | same | fake clock |

**Hard rules (gated):**

- **When idle:** zero continuous animation, zero perpetual loops, zero physics — an invariant
  test: no live execution, no arriving change, no input → 0 rAF callbacks and 0 running
  `Animation` objects over 10 s.
- **When active:** only registry animations; bounded (caps); deterministic (a pure function of
  the event and presentation time — `renderAt(t)` testable, R7); **degrade under load**
  (`Loop.degraded` → markers become A-02 pulses, chips stop fading); reduced-motion equivalent
  for every row.
- **Two clocks (zoetrope):** state is read from the record; animation ages in presentation time,
  forward only, **never replayed** on a re-read, resync or seek. A resync redraws state, it does not
  re-fire pulses.
- transform/opacity only; no `infinite`, no iteration > 1, no `steps()`; one rAF caller
  (`graph/loop.ts`); CSS/WAAPI finite animations for DOM; `Math.random` banned in animation, rendering, layout and presentation state (`src/graph/`, `src/state/`; ADR-0024 §4);
  **`filter:` is never animated** (R7's `brightness()` dimming is the example of what not to copy).
- Demo/fixture motion is caged (R1): impossible while real Core data is present.

## 22. Performance architecture (output 20)

P18's model is preserved without weakening: 1,000 visible nodes at 60 fps on integrated graphics
(manual evidence still owed), static layer + dynamic layer, frame-time degrade, parking loop.

| Effect | Cost | Cap | Degradation | Mobile | Test |
|---|---|---|---|---|---|
| halo | redraw of static layer only | none | forced-colors → 1 px ring | ring on DOM glyph | 0 frames at idle with N halos |
| hull fill | one filled path per project in static layer | ≤ projects visible | reduced transparency → none | — | pixel read (framebuffer, not screenshot) |
| depth tiers | alpha per node in static layer | — | — | — | unit |
| pulse | 1 path / pulse | 12 | degraded → none (as built) | CSS opacity | frame count |
| travelling light | 1 short path / marker / frame | 8 | degraded → pulse | none | ≤ 4 ms/frame at 1,000 nodes on CI proxy; manual 60 fps iGPU |
| thread T1 | 1 DOM element, compositor | 1 | RM → static | rule only | e2e |
| orbit | 1 DOM transform | 1 / 5 s | RM → colour | same | frame count |
| chips | DOM fade | 3 / row | degraded → no fade | same | fake clock |
| operations map | same renderer, ≤ 40 nodes | 40 | hidden < 1000 px | hidden | perf proxy |

"Works on one fixture" is not acceptance: every row above is measured on the P18 1,000-node
fixture and a 12-concurrent-execution fixture, and on real hardware for §34.

## 23. Colour

Base palette, state colours and "no hue accent" stay as DS §3 and P16 D11 froze them. Decisions:

| Item | Decision | Evidence | Approval |
|---|---|---|---|
| base | Archeus Dark / Light / High Contrast. ~~following the OS; no app switch~~ **Superseded by ADR-0044 (D-21; R13-15, the user, 2026-10-04):** the OS preference by default, with a per-client choice in Control → Appearance (theme, contrast, motion), as built by P19 B9 | DS; R6; ADR-0044 | — |
| state | active blue (running, halo, energy, markers) · attention amber (needs you, only) · **blocked/failed red — only a problem requiring resolution** · paused grey · thinking violet (planning, never "AI thinking") · done green | DS §3.2 | — |
| **focus** | move from `#FFD166` to **thread ink** (`#F4F1EA` dark / `#11151C` light), 2 px + offset | **ΔE 12.3 vs attention** (measured); a focused node reads as "needs you" | Q-V5 |
| thread | near-white ink; optional **thread tint** from a curated list of legacy palette accents passing 3:1 and ΔE ≥ 30 from every state colour — the only survival route of the 39 palettes | DS §3.3; MIG L173 | Q-V1 |
| red misuse | `.unavailable` for the narrow-graph note and for `Loadable` failures that are not problems (a read that will retry) → neutral `hint`; red stays for failures needing action | DS §3.2 | defect |
| app icon | not the attention diamond | §8 | Q-V2 |
| per-cluster hues | REJECTED in app; kept on the site | §27 | Q-V6 |

## 24. Depth / materials / transparency (output 17)

Tokens only; no ad-hoc values; no glass showcase.

| Token | Value | Use | Reduced transparency / HC |
|---|---|---|---|
| `--elev-0/1/2` | base (`surface-1`, no border) · raised (`surface-2`, 1 px `line`, `0 1px 2px`) · overlay (`surface-3`, 1 px `line-strong`, `0 8px 24px`) | BUILT (DS §6) | same |
| overlays | **opaque** (resolves DS 92–96 % vs P16 "opaque") | — | opaque |
| `--alpha-recede` | .40 | unfocused edges | 1 |
| `--alpha-tier1/2` | .64 / .36 | depth by hop distance | 1 / .64 |
| `--hull` / `--hull-focus` | `text` at .06 / .10 | cluster volume | 0 (stroke only) |
| `--halo-outer/inner` | `state-active` at .35 / .70 as two strokes | activity halo | one solid 1 px ring |
| `--z-canvas/chrome/drawer/toast/modal/tooltip` | 0 / 10 / 20 / 30 / 40 / 50 | layering (R1 §15.2) | same |
| blur / backdrop-filter / blend / surface gradient | **REJECTED** (Qt readback tearing; R6: glass only on a floating functional layer, and Archeus has none that needs it) | — | — |
| the only gradient | the thread's travelling highlight (DS §6) | T1 | removed |

## 25. Graph semantics and relationship confidence

Archeus has real semantics for **two** of the three tiers (Core audit): `EXTRACTED` = written by
deterministic code (supersedes, decided-in, learned-from, column edges); `INFERRED` = a relation a
model call described in the knowledge pass. `AMBIGUOUS` exists in the enum and is **never
written**. So:

| Tier | Line | List | A11y | Legend | Mobile |
|---|---|---|---|---|---|
| recorded (EXTRACTED, column edges) | solid, 1–3 px by bundle | swatch "recorded" | "recorded relationship" | shown | list word |
| suggested by Archeus (INFERRED) | dashed `[6,4]`, `--alpha-recede` | swatch "suggested by Archeus" + a *confirm/reject* affordance where knowledge allows | "suggested" | shown | list word |
| AMBIGUOUS | dotted (BUILT) | — | — | **hidden until Core writes it** | — |

This makes the distinction *stronger* (R3 draws inferred at half width and a third of the opacity)
without inventing a category. Nothing is inferred by the client (P18 rule kept).

---

## 26. Phase ownership (output 23)

**Q-P1 proposal:** insert **P19.5 — Visual language and operational presence** after P19 (which
unifies the clients and moves Relations/TUI onto the graph route) and before P20 (which then
hardens the new Core verbs). Alternative: fold into P19. Post-V1 phase **V1.x-3D** is named for
the 3D lineage. Core verbs needed by P19.5 are listed as prerequisites (§30); they are *not* built
in this task.

| Feature | Source | Design intent | Current | Final | Owner | Dependencies | Accessibility | Performance | Test |
|---|---|---|---|---|---|---|---|---|---|
| thread T1 message→object | DS §2; PROMPT 1338; R1 | Archeus's hand | none (`links` ignored) | PRESERVED | P19.5 | none (client) | live region | 1 | e2e |
| thread T2 list rule everywhere | DS §2 | what changed | Now only | PRESERVED | P19.5 | digest ✓ | description | static | e2e |
| thread T3 spatial trace | DS §2 | live traversal | pulse | ADAPTED | P19.5 | A8 amendment | mirror | = A-04 | unit |
| thread tint | DS §3.3 | identity | none | NEEDS DECISION | P19.5 / P22 | ADR-0017 | never meaning | — | contrast + ΔE gate |
| activity halo | §4 | live work | none | ADAPTED | P19.5 | A8 amendment | "running" | static | unit + idle |
| execution pulse on rows | DS §8 | output now | graph only | PRESERVED | P19.5 | — | "output Ns ago" | ≤12 | fake clock |
| travelling light | §4 | flow | none | ADAPTED | P19.5 | A8 amendment | mirror | ≤8 | renderAt |
| activity chips | zoetrope; R1 | current action | none | ADAPTED | P19.5 | re-read executions | chip text | 3/row | fake clock |
| hull volume, depth tiers, receding lines, cored live node | study/gap; R3/R4 | context | partial | ADAPTED | P19.5 | — | mirror | static | pixel read |
| static project cage | legacy; brand | identity | none | NEEDS DECISION | P19.5 | Q-V3 | — | world only | pixel read |
| legend + toggles; expand/collapse-all | connections; R3 | orientation | none | PRESERVED | P19.5 | — | checkboxes | — | e2e |
| confidence plain words | R3 | provenance | lowercase enum | ADAPTED | P19.5 | — | words | — | unit |
| mark in shell, app icon | credits; brand | identity | text; diamond | PRESERVED | P19.5 | Q-V2 | name | — | e2e + asset |
| orbit presence | brand | presence | none | NEEDS DECISION | P19.5 | Q-V2 | strip text | 1/5s | frame count |
| operations strip | L-A; R1 | awareness | none | PRESERVED | P19.5 | e-stop armed read (Q-B3) | landmark | DOM | e2e + axe |
| Pause all | SP 942; B.2 | control | none | PRESERVED | Core verb → P19.5 | **Q-B3** | button | — | contract + e2e |
| operations map | PDF; R1; R4 | overview | none | NEEDS DECISION | P19.5 | Q-A2 | list beside | ≤40 | perf |
| state sentence | SP; DS §4 | presence | counts | ADAPTED | P19.5 | Q-V4 | status | — | copy test |
| upcoming | PROMPT 1379 | the future | none | PRESERVED (2 steps) | P19.5 · Core | **Q-B2** | list | — | e2e |
| recent decisions | PROMPT 1381 | decisions | none | PRESERVED | P19.5 | approx ✓; log Q-B7 | list | — | e2e |
| background automation line | PROMPT 1380 | automation | none | PRESERVED | P19.5 | ✓ | text | — | e2e |
| toasts, skeletons | DS §9 | feedback | none | PRESERVED | P19.5 | — | status | — | e2e |
| pinned missions, context menus, resizable inspector | RS-23; R1 | desktop craft | none | PRESERVED | P19.5 | — | keyboard | — | e2e |
| drag reprioritise | REF-2 | priorities | none | PRESERVED | Core verb → P19.5 | **Q-B4** | Alt+↑/↓ | — | contract + e2e |
| resource ceilings UI | RS-17 | control | read-only | PRESERVED | P19.5 | none (route exists) | form | — | e2e |
| ideas stepper | RS-14 | idea flow | list | PRESERVED | P19.5 | ✓ | steps | — | e2e |
| knowledge forget (dry-run preview, no undo) | RS-16 | safe forgetting | none | ADAPTED | P19.5 | ✓ | dialog | — | e2e |
| knowledge "when used" | memory-UI research | cost of context | none | NEEDS DECISION | P19.5 | Q-B6 | text | — | — |
| command palette upgrade | UIA; R1 | intent entry | partial | ADAPTED | P19.5 | — | listbox keys | — | e2e |
| terminology / id hygiene | SP 677; R6 | plain language | many leaks | ADAPTED | P19.5 | — | — | — | copy gate |
| focus colour change, red misuse fixes | DS; ΔE | colour honesty | defects | ADAPTED | P18 closure or P19.5 (Q-P2) | — | — | — | colour-role gate |
| confirm on Reject approval / review | R6 | safety | none | PRESERVED | P19.5 | — | dialog | — | e2e |
| resume affordance, Jump to unseen | R2 | continuity | none | PRESERVED | P19.5 | P12 ✓ | link | — | e2e |
| per-mission threads | ADR-0015 | conversation | none | DEFERRED | **P19** | S1 | — | — | P19 gate |
| activity stream list | IP; R1 | log in words | none | PRESERVED | P19.5 | `/v1/events` ✓ | `role=log` | — | e2e |
| trace view, replay, scrub "as of" | zoetrope; R4 | history | none | DEFERRED | **P21** | — | list form | classes only | P21 gate |
| causality marker execution → produced object | DR §26 | causality | none | DEFERRED | **P21** | **Q-B1** | mirror | ≤8 | contract |
| composer "Archeus will…" preview | DS §11 | intent preview | none | DEFERRED | **P21** | Core intent preview | — | — | — |
| OS / push notifications | P15; R1; R2 | interrupt when needed | none | DEFERRED | **P20** | **Q-B5** | — | — | P20 gate |
| people / organisation nodes | PROMPT 296; PPTX s.11 | world | endpoints | DEFERRED | **P22** | person table | — | — | — |
| palette → tint migration | MIG L173 | continuity | presumes feature | DEFERRED | **P22** | Q-V1 | — | — | importer |
| PWA install, physical touch, WT/conhost, 60 fps | P15/P18 | evidence | owed | DEFERRED | **P18 closure / P23** | devices | — | — | manual record |
| site ↔ app DNA mapping, screenshots | C22 | one identity | legacy scene | DEFERRED | **P25** | Q-V6 | — | — | site gates |
| independent adversarial design review | R5; PLAN §34 | the rulebook is judged | self-review | PRESERVED | **P19.5 exit, P26** | — | — | — | recorded review |
| 3D mode, inner-web counter-rotation, system nodes | ADR-0016 | depth | none | DEFERRED | **V1.x-3D** | — | — | — | — |
| swipe reveals row actions (never performs one; §46); compact density | DS; directive §19 | — | none | ADAPTED (swipe, P19.5) · DEFERRED (density, V1.x) | **P19.5 / V1.x** | — | — | — | — |
| systems / agents as nodes | SP 917 | world | none | ADAPTED | P19.5 | — | badge/attribute (§12) | — | — |

No retained concept is unowned, and no deferred concept lacks a named phase.

## 27. Rejected concepts (with reasons)

| Concept | Reason |
|---|---|
| perpetual / ambient loops, background motion, idle "life" (R1 coffee breaks, R7 orbs) | principle 5; fails "what does this communicate?"; the brand rule "it stops" |
| `Math.random`, `sin(T)` breathing, uncontrolled physics, layout re-runs | nondeterministic; destroys spatial memory (zoetrope "jumpy"; R4 layout-once) |
| bokeh, blur, backdrop-filter, blend modes, glass showcase | Qt readback tearing; contrast; R6 glass only for floating functional layers |
| glow / bloom as decoration | PROMPT 1576 "overuse of glowing elements"; "state-aware glow" is carried by the halo. *Clarified for V2 (the user, 2026-10-04, V-D1, §46.4):* the luminous thread's moving head and its landing ring are **functional state light**, not decorative glow. Each is one-shot (≤ 600 ms head, ≤ 240 ms ring), fires only on a Core-recorded Archeus action, and is transform/opacity only. Glow, bloom and light that report nothing stay rejected. Not built in V1 |
| per-cluster hues in the app | colour belongs to state (DS); kept on the website |
| rotating cage, counter-rotating web in 2D | perpetual rotation; the web deferred to 3D |
| drag-to-move nodes | positions are deterministic and shared across clients; pin covers "keep this here" |
| community detection / inferred grouping in the client | the graph infers nothing (P18) |
| avatars, office/Sims metaphor, stations as zones | personality gimmick (PROMPT 1384); agents are not the primary abstraction (SP 1114); R1 itself superseded stations |
| instrument dashboard as home, metric cards | PROMPT 1310; the weather-dashboard anti-pattern |
| skins, worlds, 39 palettes as surfaces | ADR-0017 (fixed state semantics) — pending the Q7 ownership record |
| pull-to-refresh | the stream keeps the view current; the gesture implies staleness |
| mobile live preview, share links, mobile file/git/terminal | outside mobile's role (SP 826-828); share links are an exposure surface for P20/P24, not a visual feature |
| "thinking" orb / shimmer for model reasoning | P16 §18.1 r8 |
| simulated undo | P16 §18.3 |
| `filter: brightness()` dimming (R7) | animates a paint property |

## 28. Conflict register (output 24)

| # | Topic | Source A | Source B | Actual disagreement | Resolution | Evidence | Approval |
|---|---|---|---|---|---|---|---|
| X-1 | palette | ADR-0017 "accent choices" | DS §3.3 "only thread tints"; P16 "only legacy"; MIG → tint | survival route | thread tints only; amend ADR-0017 | DS B.1 has no accent | **Q-V1** |
| X-2 | thread travel | DS §2 ≤ 600 ms near-white | P18 A8 240 ms opacity | form and colour of spatial energy | both, distinct meanings: pulse (active blue, output) + marker/trace (thread ink, flow) | §21 | **Q-A1** |
| X-3 | glow | IP 856 "state-aware glow/energy" | P16 §20.10 "no glow"; PROMPT 1576 | the word | decorative glow rejected; state-aware light = halo + marker | §4 | **Q-A1** |
| X-4 | transparency / glass | PDF p10, PPTX s.11, PROMPT 1429 | DS §6 opaque, no blur | the word | transparency as tokens; blur rejected; overlays opaque | §24 | **Q-V7** |
| X-5 | greeting | SP 893 "Good afternoon." | PROMPT 1384 no personality; DS never personality text | presence form | state sentence in the display role | §9 | **Q-V4** |
| X-6 | cluster scene | site keeps the legacy constellation | PLAN P25 "uses the P16 design language" | two visual systems | one DNA, two expressions: brand (site, 3D) and instrument (app, 2D) | §4 | **Q-V6** |
| X-7 | Classic appearance | DR D3 open, owner user | PLAN Q7 DECIDED via P16 D12 | who decided | record as the user's or reopen | P16 D12 not marked user | **Q-C1** |
| X-8 | visualization primary | PDF p1/p9 "primary way to understand" | UIA §5.1 lists primary | primacy | lists primary for *control*; spatial primary for *overview* via the operations map; SP 1154 "not the primary control mechanism" supports the split | §6 | **Q-A2** |
| X-9 | energy | DR §26 travelling light or halo | P18 A8 opacity step (reduction unrecorded) | reduction | restore both as ADAPTED; record the P18 deviation | §4 | **Q-A1** |
| X-10 | pulse | DR §33 "animated while output flows" | B.5 one pulse per batch; DS §8 still says "breathing" | loop vs batch | B.5 governs; delete "breathing" | DS | doc |
| X-11 | mobile policy/routing | PROMPT 1468, SP 837-838 edits | IP 784-795 omits; UIA limited + admin | scope | UIA as built (read + limited, admin scope) | UIA | doc |
| X-12 | motion philosophy | legacy "alive = moving" | V1 "alive because things change" | definition of alive | §1 principle; the registry | §21 | **Q-A3** |
| X-13 | website vs app language | site copy/scene | app | = X-6 | = X-6 | — | Q-V6 |
| X-14 | IA counts | 7 (PROMPT/SP), 8 (IP), 6 (PPTX) | ADR-0014 4 + 2 | surfaces | ADR-0014 (evaluated in DR §17) | — | — |
| X-15 | node kinds | SP agents/systems/people; PPTX system/people/architecture | P18 17 kinds | vocabulary | §12 carriers; people P22 | Core tables | — |
| X-16 | existing visual direction | IP 849 use it | PROMPT 34, PPTX s.12 don't assume it | reuse | reuse the *direction* (constellation, energy), not the legacy UI | §4 | **Q-A1** |
| X-17 | focus colour | DS focus `#FFD166` | DS attention `#F2B544`, ΔE ≥ 30 rule | collision | focus → thread ink | ΔE 12.3 measured | **Q-V5** |
| X-18 | overlay opacity | DS 92–96 % | P16 opaque | value | opaque | — | doc |
| X-19 | shortcuts | DS ⌘1–4; UIA ⌘1–3/⌘J/⌘, | browser owns Ctrl+1–3, Ctrl+J (R6) | collision | Alt+1/2/3 and Alt+J (§46.3) | — | **Q-A5** (decided 2026-10-03) |
| X-20 | tiers | DR/ADR "INFERRED dashed, AMBIGUOUS dotted" | Core never writes AMBIGUOUS | third style | hide AMBIGUOUS from the legend until written | Core audit | doc |
| X-21 | Pause all | SP 942; DS §13; B.2 | Core has only per-mission pause and e-stop (kill + BLOCKED) | semantics | new Core verb; e-stop stays distinct | Core audit | **Q-B3** |
| X-22 | red | DS "red = problem needing resolution" | `.unavailable` on informational notes | usage | neutral hint | code | defect |
| X-23 | app icon | brand mark (credits) | icon = attention diamond | identity | mark tile | asset | **Q-V2** |
| X-24 | tray / Pause all location | DS §13 | P16 → P19 tray | timing | tray P19, strip P19.5 | — | — |
| X-25 | 3D timing | P16 G16 "P18 optional 3D" | PLAN §31.2 after V1 | stale | V1.x-3D | — | doc |
| X-26 | flowgraph owner | P16 G12 P19/P21 | §20.3 P21 | owner | P21 | — | doc |
| X-27 | per-mission threads vs thread line | ADR-0015; DS §2 | P16 S1 defers threads only | scope | threads P19, line P19.5 | — | — |
| X-28 | pulse carrier | DS §8 glyph pulse | P18 edges only | carrier | both (A-02) | — | Q-A1 |
| X-29 | toasts | DS §9, P16 §18.2 | not built, not deviated | omission | PRESERVED P19.5 | — | — |
| X-30 | undo | DS / RS-16 30-day undo | Core RETRACTED terminal | inverse | dry-run preview, no undo | Core audit | doc |

(X-1…X-30 subsume AUDIT-1's C1–C27; the mapping is C1→X-1, C2→X-7, C6→X-2, C10→M-13 in §4 DNA-6,
C15→X-27, C19→X-28, C21→X-18, C22→X-6, C23→X-8, C24→X-3, C25→X-4, C26→X-5; the rest are stale-text
items listed in §35.)

## 29. Traceability matrix (output 7) — REFERENCE → INTENT → V1 ARCHITECTURE → IMPLEMENTATION → TEST → OWNER

| Reference | Intent | V1 architecture | Implementation today | Test | Owner |
|---|---|---|---|---|---|
| credits: Coscia mark | bounded form, motion that never leaves | DNA-6, §8 | none; icon collides | asset + frame count | P19.5 |
| credits: zoetrope | live session graph; two clocks | §21 two-clocks rule; P21 trace | none | registry gate; P21 | P19.5 / P21 |
| credits: claude-mem | continuity | digest | BUILT | e2e digest | done |
| credits: cognee, repo-map | graph memory | Relations, graph of record | BUILT | P18 suite | done |
| credits: others (10) | not UI | — | — | — | n/a |
| FloatingPragma photo, renders | constellation | DNA-5 | clusters + lines | pixel read | P19.5 |
| brand-study | mark; "it stops"; state line | DNA-6, DNA-7, DNA-10 | none | idle invariant | P19.5 |
| constellation-study t3, t10 | halo; links carry something | DNA-2, DNA-4 | none | unit, renderAt | P19.5 |
| constellation-gap 1 | hull volume | §12 hull | none | pixel read | P19.5 |
| cluster-handoff quotes | fine lines; dot with outer circle | §12 cored node | fine lines BUILT | — | P19.5 |
| memory-UI research | when-used, usability | §13 | none | — | P19.5 |
| connections.py | legacy graph mechanisms | §12 | ported (G4) | P18 suite | done / P19.5 |
| stage.js / motion.js | state-driven presence; one loop | DNA-6/10, §21 | loop BUILT | gates | done / P19.5 |
| themes.py | "drama in the interface" | principle 15; tint | none | ΔE gate | P19.5 |
| legacy captures | mark, state line | §8 | none | — | P19.5 |
| stash third-party refs | control program; traces; journey | §6, A-04, plan rail | none | — | P19.5 |
| site scene.ts | brand constellation | X-6 | legacy | site gates | P25 |
| PROMPT 142, 1338, 1367-1382, 1422-1437, 1565-1592 | living system; operating on your world; presence; spatial vocabulary; quality bar | §4, §6, §9, §12, §33 | partial | e2e + review | P19.5 |
| SP 886-929, 942 | present home; fine light lines; clusters; pause all | §9, §12, §10 | partial | e2e | P19.5 |
| IP 849-863, 907-910 | existing visual direction; glow/energy; transparent; drill; remote stop | §4, §24, §10 | drill BUILT; e-stop BUILT | P18 suite | done / P19.5 |
| PDF p1, p9, p10 | visualization to understand; light/energy; glass-like | X-8, DNA-4, §24 | none | — | P19.5 |
| PPTX s.9–12 | one core; stack; spatial world model; core first | §12, §11 | partial | — | P19.5 |
| R1 Munder Difflin | representation = state; envelopes; strip; side panel; caged demo; real-app evidence | §6 table, A-04, §15, §34 | partial | §34 | P19.5 |
| R2 Vicoa | status rail; offline grey; resume; badge = awaiting input; push | §16, §17, §19 | partial | e2e | P19.5 / P20 |
| R3 Graphify | confidence styling; legend toggles; path/explain text | §25, §12 | dashes BUILT | unit | P19.5 |
| R4 Cognee | bounded by default; layout once; classes-only scrub | §12, §21 | bounded BUILT | P18 / P21 | done / P21 |
| R5 migration kit | rulebook; adversarial review; judge; no inferred approval | this document; §34 | — | recorded review | P19.5 exit / P26 |
| R6 Apple skill | lenses; template test; floors | §20, §33 | floors partly BUILT | axe, contrast | P19.5 |
| R7 Ship Notes | easing; loop gate; renderAt | §21 | easing, loop BUILT | loop tests | done / P19.5 |
| P16 | IA, motion table | §21 | mostly BUILT | P16 suite | done |
| P17 | TUI parity | TUI: `●` live mark; no motion. The changed marker is `│`, built by P19 B2 (p19-design-gate §12 item 1; accepted R13-16), not by P17 and not `›` (R13-15) | BUILT | P17 suite; P19 B2 | done |
| P18 | graph A1–A17 | §12; A8 amendment | BUILT | P18 suite | done / P19.5 |

## 30. Core / API dependencies (output 21)

| Feature | Verdict | What exists | What is missing | Owner of the Core work |
|---|---|---|---|---|
| thread T1 | **CLIENT ONLY** | `Message.links` = "the world objects it touched" | SPA rendering | — |
| list pulse, halo, travelling light | **CLIENT ONLY** | `execution.*` frames with subject; executions read | — | — |
| resource ceilings UI | **CLIENT ONLY** | `POST /v1/resource-policies/{id}` (allocation, reserve, budgets) | form; budgets not shown | — |
| recent decisions (approximate) | **CLIENT ONLY** | approvals `decided_at`, route/policy decisions, DECISION knowledge | a unified log (`Decision` never written; no `since`) — Q-B7 | P21 (optional) |
| strip: counts, connection, clients | **CLIENT ONLY** | `/v1/status` (unused), attention, presence | — | — |
| strip: e-stop armed state | **CORE** | e-stop sentinel | a readable field in Health/status | P19.5 prerequisite |
| **Pause all** | **CORE** | per-mission pause; e-stop = kill + BLOCKED | a bulk pause verb (ADR-0006), its policy stage and events | P19.5 prerequisite (P11/P14 owners' rules) |
| **reprioritise** | **CORE** | `Mission.priority` field (never set or read) | set-priority command; the router/scheduler reading it | P19.5 prerequisite (P10) |
| **upcoming work** | **CORE** | APPROVED/PLANNING missions; idea SCHEDULED state (no date) | schedule triggers + `next_run` (P14 D14 deferred them) | P21 (ADR-0030) |
| **event cause (general)** | **CORE** | `actor`, `cause_chain` (automation path only); `/v1/events` returns them | cause for non-automation commands; SSE frames carry no cause | P21 |
| **execution → produced object** | **CORE** | checkpoint `files_changed`, `Task.merged_revision`; `produced` relation type unused | a produced/affected record | P21 |
| **notifications / push** | **CORE** | `notify_default` column (never read); attention rules | notification record + transport | P20 |
| knowledge forget | **CLIENT ONLY** (preview) / **CORE** (undo) | dry-run default | an inverse for RETRACTED — **not requested**; no undo is offered | — |
| knowledge "when used" | **VERIFY** | context packages record inclusion | a per-item "used" summary | Q-B6 |
| operational summary | **CLIENT ONLY** | `/v1/status`, `/v1/digest`, `/v1/attention` | — | — |

No backend change is made by this task.

## 31. Decisions requiring the user's approval (output 30)

**Architecture**
- **Q-A1** Amend P18 A8 (explicit amendment, not silent): keep the opacity pulse, add the static
  **activity halo** and the event-driven **travelling light**; record that P18 rejected the
  *mechanisms* (loop, random, breathing, bokeh, ambient stage), not the concepts; carry the
  "existing visual direction" (IP 849) as direction, not legacy UI.
- **Q-A2** Resolve "visualization is the primary way to understand" as: lists for control,
  spatial for overview — via a bounded **operations map** on Now (≥ 1000 px).
- **Q-A3** Adopt the animation registry, the idle invariant and the two-clocks rule as binding
  gates (new ADR-0024).
- **Q-A5** Replace Ctrl+1/2/3 and Ctrl+J (browser-owned) with non-colliding shortcuts.
  *Decided 2026-10-03 (§46.3):* Alt+1, Alt+2, Alt+3 and Alt+J.

**Identity**
- **Q-V1** Legacy palettes survive only as thread tints; amend ADR-0017.
- **Q-V2** The mark enters the shell and replaces the attention-diamond app icon; its orbit node
  becomes the presence indicator; the favicon shows the same state statically (claude-mem, §37).
- **Q-V3** Static cage glyph for project clusters at world level (one figure with the mark).
- **Q-V4** State sentence replaces the greeting and the current presence line.
- **Q-V5** Focus colour moves to thread ink (ΔE 12.3 vs attention).
- **Q-V6** Website keeps the constellation as the brand expression of the same DNA (P25).
- **Q-V7** Transparency as tokens; blur rejected; overlays opaque.

**Phases**
- **Q-P1** Insert **P19.5** (or fold into P19); name **V1.x-3D** and **V1.x**.
- **Q-P2** Allow, as P18 closure, doc-only deviation rows (A8 narrowing; unported G4 items) and the
  two colour defects (red misuse, focus colour) — otherwise both move to P19.5. P18 is not
  otherwise reopened.
- **Q-P3** Confirm rejections (pull-to-refresh, drag-to-move, avatars/stations, mobile live
  preview/share) and deferrals (swipe = decide later, compact density).

**Core dependencies (to be built before the matching UI, never in this task)**
- **Q-B1** general event cause + execution → produced-object record (P21).
- **Q-B2** schedules / `next_run` for upcoming work (P21, ADR-0030).
- **Q-B3** Pause all verb + readable e-stop state.
- **Q-B4** set mission priority, read by routing/scheduling.
- **Q-B5** notification record + push transport (P20).
- **Q-B6** knowledge "when used" (verify first).
- **Q-B7** unified decision log (optional).

**Records**
- **Q-C1** Record "no Classic appearance" (Q7) as your decision, or reopen it.
- **Q-C2** A durable private home for the at-risk references (`stash@{0}` dashboards, the five
  gitignored V1 files, `notes/reference/`).

---

## 32. Current V1 vs target V1 (output 22)

| Surface | Exists | Missing | Changes | Stays | Added | Phase |
|---|---|---|---|---|---|---|
| Shell | text brand, banner, Ctrl+K, nav, attention badge | mark, presence, strip, Pause all, icon | icon; focus colour; shortcuts | nav table, banner | strip, orbit | P19.5 |
| Now | presence line, digest, happening, needs you, conversation | state sentence, halo, chips, thread T1, upcoming, decisions, map | presence line → sentence; ids → names | digest, needs you | T1, upcoming, decisions, map (decision) | P19.5 |
| Work | groups, ideas list | live row detail, rule, pins, menus, reprioritise, Pause all, stepper | row density | groups | chips, rule, stepper | P19.5 (+ Core) |
| Relations | list, swatches, tier word | live/changed marks, plain words, explanation | tier words | list as a11y authority | marks | P19 / P19.5 |
| Graph | shapes, lines, pulse, search, path, pin, LOD, mirror | halo, marker, hull, depth tiers, cored node, legend, expand-all, cage | focus ring colour; unfocused alpha | layout, loop, mirror | map mode | P19.5 |
| Knowledge | list, filters, confirm/reject/retract | when used, forget with dry-run | enum words | provenance | forget flow | P19.5 |
| Decisions | — (scattered) | recent decisions | — | — | block + section | P19.5 |
| Inspector | tabs, slide, Esc | resize, noun titles, live header, Details disclosure | raw data hidden | tabs | resize | P19.5 |
| Devices / sessions | presence, pairing | offline grey, resume | — | Control location | resume | P19.5 |
| Notifications | banner, badge | toast, OS, push | — | badge | toast | P19.5 / P20 |
| Command | cache search, Tell Archeus | arrow keys, server search, object actions, effect preview | idempotency | Ctrl+K | actions | P19.5 |
| Mobile | tabs, sheets, 44 px, PWA | row cues, resume, Jump to unseen | — | A12 list | cues | P19.5 / P23 |
| Empty / loading / failure | text | skeleton, action per empty, neutral retryable failures | red → neutral where not a problem | copy discipline | skeleton | P19.5 |

## 33. Generic-template adversarial review (output 26)

R6's test, applied without a score: *"Name the one thing this design would be remembered by."*
Today, looking at the real renders (`desk-dark-now`, `-work`, `-graph-mission`), **nothing**: the
design's own signature — the thread — is a 2 px rule most users will read as a bullet. *"Would
you have produced this same plan for a similar brief about a different product?"* — the current
shell, yes.

Concrete weaknesses:

1. **Generic shell.** A text wordmark, a 232 px sidebar of five outline icons, a secondary button
   top-right: the frame of every generated admin app. The Apple template list's "near-black with
   one accent" is avoided only because there is no accent at all; the result reads as a dark
   GitHub-style utility (`#0E1116` ground, system font, hairline rows).
2. **Missing identity.** No mark anywhere in the product; the app icon is the Attention diamond.
3. **Static state.** Two missions are executing in the Now render and nothing on screen moves,
   glows or changes; "Executing" is a 10 px blue word. The system is *running* and *looks idle* —
   the opposite of principle 4.
4. **No operational presence.** Presence is one grey line; nothing persists across pages; no
   answer to "is Archeus working right now?" outside Now.
5. **Weak hierarchy on sparse data.** Work at 1440 px: two rows and ~700 px of nothing; Now: the
   right column ends at 300 px.
6. **No spatial storytelling.** The graph is circles and grey lines on an empty field; the focused
   node's ring is attention-amber; nothing says what is live or where work flows.
7. **Insufficient feedback.** No toast, no skeleton, no pulse on rows, no thread line.
8. **Infrastructure leaks.** `rep_01M3S3W6…` on the Now digest; ids, JSON, hashes and enums in
   inspectors — SP 677-681's exact anti-example.
9. **Copy inconsistencies.** "Dismiss" and "Accept result" each mean two commands; contradictory
   "create a project" hints.

What the references provide against each:

| Weakness | Remedy | From |
|---|---|---|
| 1, 2 | the mark + orbit in the shell; mark tile as the icon | credits, brand-study, R1 brand mark |
| 3 | halo, pulse, travelling light, chips — only while real work runs | constellation t3/t10, zoetrope chips, R1 "the representation is the status" |
| 4 | operations strip | brand-study state line, R1 agent strip, R2 tray |
| 5 | operational density, two-line live rows, map | command-deck ref, R1 floor |
| 6 | hull volume, depth tiers, cored live nodes, legend, focus in ink | constellation-gap, R3, R4 |
| 7 | toast, skeleton, thread T1 | DS §9, R1 toasts |
| 8, 9 | plain-language rule, Details disclosure, copy gate | SP 677-681, R6 content lens |

What must **not** be the remedy: a hue accent, gradients, glass, cards-as-dashboard, a greeting
with personality, avatars. The distinctiveness must come from the DNA, spent in one place.

## 34. Manual visual acceptance (output 27)

Evidence rule (R1 + the repo's own "read the pages" lesson): **BEFORE/AFTER captures of the real
app on a real Core**, plus an innerText read, plus measurement (framebuffer reads for canvas —
headless screenshots of WebGL/canvas prove nothing). Each item is signed off by the user (R5: "Do
not proceed on inferred approval").

| Feature | Accept when | Reject when |
|---|---|---|
| activity halo | a real execution running → halo on its mission/execution in graph and rows; ended → halo gone within one read; reduced motion → halo still shown, static | halo while idle; halo on a non-live object |
| execution pulse | real output → one pulse per batch, never more than 1 / 2 s per object; no output → none | pulse on re-read/resync; pulse under reduced motion |
| travelling light | real output → one marker from the execution along its drawn edge; ≤ 8 at once with 12 executions; degraded → pulses | marker without a frame; marker on a non-live edge |
| thread T1 | an Archeus reply with links → the line reaches the correct row once; tint correct; the live region says what changed; offscreen target → rule on the link, no line | wrong row; replays on refresh |
| thread rule | changed rows marked on every list; cleared by acknowledgement | marks surviving acknowledgement |
| mark / presence | idle → still, neutral; working → orbit travels once per batch; needs you → attention colour; disconnected → hollow | moving while idle |
| operations strip | active work, needs-you count, clients and freshness visible on every page; Pause all works (after Core) | a number with no link to its list |
| operations map (if approved) | shows only live work, ≤ 40 nodes, legible; activity obvious | a decorative map |
| graph | spatial relationships understandable without the docs (legend); focus obvious and not amber; activity obvious; 60 fps at 1,000 nodes on integrated graphics with markers running | focus confused with attention; frame drops |
| idle | 10 s with nothing happening → no motion anywhere, measured | any motion |
| accessibility | screen-reader pass over Now, Work, graph mirror with live work running; forced colours; 200 % text | information only in motion or colour |
| mobile | physical device: rows show live cues; approval with PIN; resume affordance | shrunken desktop |
| template test | the reviewer can name the one thing the design is remembered by (the thread) | "it looks like an admin template" |

## 35. Proposed ADR / document changes (output 28) — listed, not made

| ID | Document | Change |
|---|---|---|
| DOC-1 | new **ADR-0024** "Semantic motion, the living thread and the idle invariant" | §4, §21 as binding; mechanisms vs concepts recorded |
| DOC-2 | ADR-0016 | presence principle moves to the orbit + strip; transparency tokens; operations map (if Q-A2) |
| DOC-3 | ADR-0017 | "thread tints", not "accent choices"; Q7 ownership |
| DOC-4 | DS §2, §3, §4, §6, §7, §8, §9, §11, §13 | thread forms; focus colour; state sentence; opaque overlays + tokens; icon list; delete "breathing"; halo/marker/chip rows; strip; toasts |
| DOC-5 | DR §7, §26, §30 | cite Gen-1 notes and Gen-2 lines by name; dispositions |
| DOC-6 | UIA §4, §5.1 | strip, map, mobile cues; lists-for-control / spatial-for-overview |
| DOC-7 | PLAN | P19.5 (or P19 extension); V1.x-3D, V1.x; P21 trace + causality; P20 notifications; P21 schedules; P22 tint migration; P23 PWA checklist |
| DOC-8 | P18 gate §22 (doc-only) | deviation rows: A8 narrowing; unported G4 items and their dispositions; colour defects |
| DOC-9 | P16 gate | "specified, not built" list with owners |
| DOC-10 | testing-strategy | idle invariant, motion registry gate, marker budget, text-equivalent gate, two-clocks test, copy/id gate, manual acceptance record |
| DOC-11 | `docs/research/external-references.md` | R1–R7 updated with this session's source revisions and observations (§2.4) |
| DOC-12 | this document | becomes the design rulebook after approval; implementation phases are judged against it |
| DOC-13 | stale-text pass | DS header PROPOSED→frozen, ⌘1–4, Thread tab, ring = person, P16 "P18 optional 3D", G12 owner |

## 36. Implementation roadmap (output 29) — for approval later; nothing started

| Step | Concepts | Phase | Prerequisites | Components | Backend | Tests | Manual evidence | Perf |
|---|---|---|---|---|---|---|---|---|
| R0 | DOC-1…DOC-13 | doc | §31 answers | — | — | doc checks | — | — |
| R1 | motion registry, idle invariant, two-clocks, copy/id gate | P19.5 | R0 | `state/`, gates | — | mutation-verified gates | — | — |
| R2 | colour defects, legend, expand/collapse-all, plain tier words | P18 closure / P19.5 | Q-P2 | `GraphView`, `encoding.ts`, tokens | — | colour-role gate, e2e | — | none |
| R3 | halo, cored node, hull, depth tiers, receding lines | P19.5 | R1 | `render.ts`, tokens | — | encoding + framebuffer read | 60 fps iGPU | static layer |
| R4 | travelling light (A8 amendment) | P19.5 | R3, Q-A1 | `model.ts`, `render.ts`, `loop.ts` | — | renderAt, caps, RM | 60 fps iGPU | ≤ 8 |
| R5 | row pulse, chips, thread rule everywhere | P19.5 | R1 | `ui.tsx`, surfaces | — | fake clock e2e | — | CSS |
| R6 | thread T1 from `Message.links`, tint | P19.5 | R5, P19 threads | `Now.tsx`, `Mission.tsx` | — | e2e, HC, RM | SR pass | 1 |
| R7 | mark, icon, orbit, strip | P19.5 | R1 | shell, assets | e-stop read (Q-B3) | e2e + axe | — | 1 / 5 s |
| R8 | Now: sentence, upcoming (step 1), decisions, automation line, map | P19.5 | R3, R7, Q-A2 | `Now.tsx`, `GraphView` map mode | — | e2e | — | ≤ 40 |
| R9 | toasts, skeletons, menus, pins, resizable inspector, confirms, Details disclosure, resume | P19.5 | R1 | shell, surfaces | — | e2e + keyboard | — | — |
| R10 | Pause all, reprioritise (absolute priority, D-14) | Core → P19.5 | Q-B3, Q-B4 | Work, strip, inspector | **Core verbs** | contract + e2e | — | — |
| R11 | resources form, ideas stepper, forget flow, palette upgrade | P19.5 | R1 | Control, Work, World, CommandBar | — | e2e | — | — |
| R12 | static cage glyph | P19.5 | R3, Q-V3 | `render.ts` | — | framebuffer read | — | world only |
| R13 | independent adversarial design review against this rulebook | P19.5 exit, after P19 and its three carried behaviours (§46.3) | R1–R12 | — | — | recorded | reviewer + user | — |
| R14 | upcoming step 2 | P21 | Q-B2 | Now | schedules | contract | — | — |
| R15 | notifications, push | P20 | Q-B5 | shell, sw.js | notification record | P20 gate | devices | — |
| R16 | trace view, replay, causality markers, activity stream full | P21 | Q-B1 | new view | cause + produced | P21 gate | — | classes only |
| R17 | tint migration, people nodes | P22 | Q-V1 | importers | person table | importer | — | — |
| R18 | PWA / touch / WT / 60 fps records | P18 closure + P23 | — | — | — | — | devices | — |
| R19 | site DNA mapping, screenshots | P25 | R3–R8, Q-V6 | www, docs | — | site gates | — | — |
| R20 | 3D, inner web, system nodes | V1.x-3D | V1 released | WebGL | — | — | — | — |

---

## 37. Credits re-verified, starter skill collections, claude-mem viewer (additional audit)

The live credits page (docs.claudectl.space/credits/#built-on, fetched 2026-09-30) matches
`docs/credits.md` exactly: eleven "Built on" entries, four skill collections, the Coscia visual
identity credit. No reference was missing from §2.1.

| Source (revision, licence) | Useful contribution | Kind | Disposition | Where |
|---|---|---|---|---|
| **claude-mem** viewer (`a077975`, Apache-2.0) | one reverse-chronological feed merging observations, summaries and prompts; **settings with a live preview of the exact injected context**; **processing shown in the chrome** (queue-depth bubble beside the logo, favicon state); logs drawer; refused delete shown inline with `role=alert`; cross-tab deletion through one removal path | IXP | feed → activity stream (O-7, P19.5); **context preview** → project constraints / knowledge edits show the context package Archeus will assemble (`/v1/context/preview` exists — CLIENT ONLY, P19.5); **chrome presence** → the mark's orbit + a **static favicon state** (idle / working / needs you; no spinning — its spinner and `pulse … infinite` are REJECTED, and it has no reduced-motion handling) | §8, §6 |
| **obra/superpowers** (`8ca22db`, MIT) | brainstorming gate "**A reply approves the stage actually presented**"; one-way ratchet; spec self-review (placeholders, consistency, scope, ambiguity); verification-before-completion "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE", revert-must-fail | PRIN (process) | ADOPTED as process for this rulebook and for P19.5 exit (§34, §36 R13) | §0 header, §34 |
| **khalilbenaz** `design-critique` (`72e0e90`, MIT) | 5-second test (what does it do / for whom / what now?); blur test for hierarchy; "≤ 200 ms for feedback on repeated interactions"; ≤ 3 distinct greys; one primary action per view; findings as *problem → impact → fix* with P1/P2/P3 | PRIN | ADOPTED as the rubric of the P19.5 independent design review | §34 |
| khalilbenaz `user-flow-designer` | edge-case matrix (timeout → auto retry + toast; empty → state + suggested action; back mid-flow → local persistence) | IXP | ADOPTED into Appendix B / §42 state matrix; composer draft kept locally | §42 |
| khalilbenaz `responsive-design-helper` | container queries for components; `auto-fit`+`minmax`+`clamp`; `100dvh`; ≤ 4–5 breakpoints | TECH | confirms BUILT practice | — |
| alirezarezvani `observability-designer` (`19392f7`, MIT) | drill-down Overview → Service → Component; **7 ± 2 panels per screen**; alert state shown on the relevant panel; **hysteresis** (different thresholds for firing and resolving); "every alert must have a clear response action" | PRIN | ADOPTED: Now holds ≤ 7 blocks; attention rows always carry their action (BUILT); **halo hysteresis** — appears on the first `active` read, clears only after a read shows the execution ended (never on a transient reconnect) | §9, §21 A-03 |
| alirezarezvani `a11y-audit` | "the live region container must exist in the DOM *before* content is injected"; `role=log` for activity feeds; WCAG 2.2 2.5.7 dragging needs a single-pointer alternative | PRIN | ADOPTED: announcer regions mounted at boot (BUILT, `announce.ts`); activity stream `role=log`; reprioritise has a non-drag path (Alt+↑/↓, "Move to…") | §20 |
| alirezarezvani `apple-hig-expert` | measured scorecard with confidence tags (tool-verified / needs device / assumed) | PRIN | ADOPTED for §34 records: every acceptance item states how it was verified | §34 |
| ComposioHQ `artifacts-builder` (Apache-2.0) | anti-"AI slop": no excessive centred layouts, purple gradients, uniform rounded corners, Inter | PRIN | ADOPTED as template-test items (§33) | §33 |
| ComposioHQ `canvas-design` | "refine what is already here, do not add more" | PRIN | ADOPTED (matches the flat-pass lesson "go back to fine lines is not draw less") | principle 14 |
| alirezarezvani `epic-design`, khalilbenaz `pencil-ui-designer` | depth layers, hero hierarchy — but mandate infinite float loops, animated `filter`, backdrop blur, "never a flat background", CDN scripts | TECH | **REJECTED** for the app (violates principles 5, §21, §24, offline/CDN rule); depth-layer idea only for the website (P25) | §27 |
| remaining skills (tokens generators, theme factories, Anthropic brand) | generic or not Archeus's | — | not applicable (recorded, not forced) | — |

## 38. Final design tokens (output 4)

One source (`tokens/tokens.json` → `tokens.css`, `tokens.py` for the TUI), gated by the
existing contrast test. Values marked **Δ** change from today; everything else is as built.

| Group | Token | Dark | Light | Rule |
|---|---|---|---|---|
| surfaces | `bg`, `surface-1/2/3` | `#0E1116`, `#141922`, `#1A2130`, `#202838` | `#F7F8FA`, `#FFFFFF`, … (as built) | opaque |
| lines | `line`, `line-strong` | as built | as built | separators only |
| text | `text`, `text-2`, `text-3` | as built (14.6:1, 8.3:1, ≥ 3:1) | as built | contrast gate |
| primary | neutral fill | `#E6EAF0` on `#0E1116` | `#11151C` | no hue accent |
| state | `state-active/attention/blocked/paused/thinking/done` | `#5AA9FF #F2B544 #F07178 #A7B0BD #B79CFF #5FD08B` | `#0B63CE #8A5600 #B3261E #5B6472 #6A45C9 #1E7F45` | fixed across themes; red only for problems |
| **focus** Δ | `focus` | `#F4F1EA` (thread ink) | `#11151C` | ≥ 3:1 vs control and surface; ΔE ≥ 20 from every state colour (the state-separation floor; see ADR-0028) |
| thread | `thread` | `#F4F1EA` | `#11151C` | the only non-state ink |
| thread tints Δ | `thread-tint-*` | curated list from legacy palettes | same | 3:1 on `surface-1`; ΔE ≥ 30 from state colours **and focus**; never carries meaning |
| activity Δ | `halo-outer`, `halo-inner` | `state-active` @ .35 / .70 | same | two strokes, no gradient |
| volume Δ | `hull`, `hull-focus` | `text` @ .06 / .10 | `text` @ .05 / .09 | reduced transparency → 0 |
| depth Δ | `alpha-recede`, `alpha-tier1`, `alpha-tier2` | .40, .64, .36 | same | reduced transparency → 1 / 1 / .64 |
| edges Δ | `edge-recorded`, `edge-suggested` | solid 1–3 px `line-strong`; dashed `[6,4]` @ `alpha-recede` | same | AMBIGUOUS token exists, unused until Core writes it |
| marker Δ | `marker` | thread ink, 3 px head + 12 px tail | same | ≤ 8 concurrent |
| elevation | `elev-0/1/2` | as built (DS §6) | as built | opaque overlays |
| z Δ | `z-canvas/chrome/drawer/toast/modal/tooltip` | 0/10/20/30/40/50 | same | — |
| motion | `dur-state 160`, `dur-row 200`, `dur-inspector 220`, `dur-sheet 280`, `dur-pulse 240`, `dur-toast 160`, **Δ** `dur-travel 600`, `dur-orbit 900`, `ttl-chip 2500`, `ease cubic-bezier(.22,.8,.18,1)` | — | — | registry-bound (§21) |
| type, spacing, radius, targets | as built (DS §4–5; `target-desktop 28`, `target-phone 44`) | — | — | R6 floors |

## 39. Component primitives (output 5, implementation quality rule)

Reusable primitives, each owning its tokens; no one-off visual hacks. "Exists" names today's
file; everything else is P19.5.

| Primitive | Responsibility | Exists | Consumes |
|---|---|---|---|
| `StateBadge` | glyph + word + A-01 | `components/ui.tsx:15-33` | state tokens |
| `AttentionMark` | ◆ + reason + action; badge counts only needs-you | partial (`Attention.tsx`) | `state-attention` |
| `ActivityHalo` | ring on a DOM glyph; canvas halo via encoding | — | halo tokens, hysteresis |
| `PulseTarget` | one A-02 per batch, rate-limited, two-clocks | graph only (`model.ts:243-269`) | `dur-pulse` |
| `ActivityChip` | current action, TTL, ≤ 3 per row | — | `ttl-chip` |
| `ThreadRule` / `ThreadLine` | T2 rule; T1 draw-on from `Message.links` | rule only (`app.css:508`) | thread tokens |
| `graph/encoding` node + edge | shapes, halo, core dot, hull, tiers, depth | `graph/encoding.ts`, `render.ts` | graph tokens |
| `Legend` | generated from `encoding.ts`, toggles | — | — |
| `ProjectGlyph` | static cage ≥ 48 px, circle below | — | `text-2` |
| `Mark` (+ orbit) | shell mark, favicon state | — | `currentColor` |
| `StatusStrip` | O-1 | — | status/attention/presence reads |
| `OperationRow` | live mission/execution row (state, title, chip, fraction, resource line) | partial (`Now.tsx`, `Work.tsx`) | — |
| `EventRow` | activity stream row in words, `role=log` container | — | `/v1/events` |
| `Inspector` | resizable, noun title, live header, Details disclosure | `surfaces/Inspector.tsx` (fixed width) | `inspector-min/max` |
| `Toast` | one at a time, off-screen only | — | `dur-toast`, `z-toast` |
| `Skeleton` | static row shapes | — | surfaces |
| `ConfidenceSwatch` | recorded / suggested, plain words | partial (`Relations.tsx:271-276`) | edge tokens |
| `ActionButton` | disabled-with-reason, busy text, confirm | `ui.tsx:97-196` | — |
| `Fresh` | freshness | `ui.tsx:35-62` | — |

## 40. Visual regression strategy (output 15)

1. **Deterministic rendering first** (R7 `renderAt(t)`): the graph renderer and every registry
   animation are pure functions of (state, presentation time); unit tests assert frames at fixed t.
2. **Framebuffer reads, not screenshots, for the canvas** (the repo's WebGL/canvas lesson): pixel
   probes at node positions assert halo / hull / focus colours and alphas.
3. **Playwright captures at a frozen fake clock** of every surface × {dark, light, forced colours,
   reduced motion} × {1440, 1000, 390} against the P18 fixture Core and a
   12-concurrent-execution fixture; diffs reviewed by a human, never auto-accepted.
4. **Computed-style gates**: focus ring colour ≠ attention colour (ΔE), no `filter`/`backdrop`
   animations, registry-only keyframes, idle invariant (0 rAF, 0 running `Animation`s over 10 s).
5. **innerText read** of every page (the "read the pages" lesson): no raw ids / JSON / hashes in the
   default view; consistent command names.
6. **BEFORE / AFTER on the real app** (R1): every P19.5 change ships both captures from a real Core.
7. **Mutation-verify every new gate** (revert the fix, the gate must fail).

## 41. Additional reference discovery — newly identified useful ideas

| Idea | Source | Disposition | Owner |
|---|---|---|---|
| **impact / blast radius** from a changed object over *recorded* relations, bounded by hops | R3 `affected.py`; R4 bounded views | ADAPTED — a "What does this affect?" toggle on a focused node reusing the existing BFS over loaded edges; no inference | P19.5 |
| completion feedback only after real work ("short turns do not celebrate") | R1 cheer threshold | ADOPTED — A-13 toast only for off-screen completions of work that ran ≥ 10 s | P19.5 |
| the left edge of a row belongs to the thread | R2 status rail collides with DS thread rule | RULE — state never uses a left rail; state stays glyph + word | P19.5 |
| composer draft retained locally | R2 drafts | ADOPTED (per-viewer localStorage) | P19.5 |
| "Jump to unseen" | R2 | ADOPTED (digest cursor) | P19.5 |
| queued-message steering into a running mission | R2 steer | DEFERRED with per-mission threads | P19 |
| idle-gap markers and failures revealed as the playhead passes | zoetrope | DEFERRED | P21 |
| follow-camera mode | zoetrope | DEFERRED (opt-in only, P21 trace) | P21 |
| reinforced / weakened marks after feedback | R4 | ADAPTED as A-01 on confirm/reject | P19.5 |
| context preview beside the edit that shapes it | claude-mem | ADOPTED | P19.5 |
| favicon reflects presence (static) | claude-mem | ADOPTED | P19.5 |
| halo hysteresis | observability-designer | ADOPTED | P19.5 |
| ≤ 7 blocks on Now | observability-designer | ADOPTED | P19.5 |
| "a reply approves the stage actually presented" | obra | ADOPTED (process) | now |

## 42. Surface state matrix (output 6 detail)

Every cell names the carrier; "—" means the state cannot occur on that surface.

| Surface | Initial | Loading | Empty | Active | Success | Attention | Error | Recovery | Offline | Disabled |
|---|---|---|---|---|---|---|---|---|---|---|
| Shell | mark + "Connecting to Archeus…" | same | — | orbit + strip counts | — | badge + strip | "Archeus could not start: …" + retry | banner "Back — read again" | banner + strip hollow | commands disabled with reason |
| Now | skeleton blocks | skeleton | state sentence + composer focus | halo rows, chips, map | toast if off-screen | Needs you (≤ 3) | inline per block, neutral while retrying | resync redraws, no replay | banner; last read shown with "as of" | Send disabled with reason |
| Work | skeleton rows | skeleton | sentence + "Tell Archeus" | live rows | row state change | group "Needs you" | inline | same | same | actions disabled with scope reason |
| Graph | skeleton frame | "Reading the neighbourhood…" | sentence + legend + "Open in list" | halo, pulse, marker | state change | attention glyph on node | neutral note; red only if action needed | redraw once | static last frame + banner | < 600 px → list |
| Relations | skeleton rows | skeleton | "No recorded relationships." | live/changed marks | — | — | inline | same | same | — |
| Knowledge | skeleton | skeleton | "Nothing known yet." + how knowledge arrives | — | A-01 on confirm/reject | candidate count | inline | same | same | forget disabled without scope |
| Attention | skeleton | skeleton | "Nothing waits on you." | — | card leaves with A-01 | every card: what, why, action, what next | inline refusal (BUILT) | same | same | PIN step-up reason (BUILT) |
| Inspector | skeleton header | per tab | per-tab sentence | live header | — | approval card | inline | same | same | — |
| Control | skeleton | skeleton | per-section sentence | — | saved ✓ | e-stop armed (Core) | inline | same | same | admin-scope reason |
| Mobile | same carriers, sheets | same | same | row cues | same | tab badge | same | same | banner full width | same |

## 43. Ideas and Resources (explicit)

- **Ideas** (Work → Ideas; **D-11, §46.1: read-only — the transition buttons below are a recorded
  deviation until Core has an idea-transition command**): a stepper over Core's real states — CAPTURED → UNDERSTOOD → EXPLORED →
  VALIDATED → CONCEPT → PLANNED → SCHEDULED → IMPLEMENTING → COMPLETED → LEARNED, with PARKED /
  DISCARDED as side exits and *revive* — each step showing its evidence (the linked knowledge and
  mission) and the one transition available now. Conversion "idea → mission" is the existing
  PLANNED → IMPLEMENTING edge. CLIENT ONLY. P19.5.
- **Resources** (Control → Resources; **D-7, §46.1: built in P19.5**): a form over the existing `POST /v1/resource-policies/{id}`
  (priority, allocation ceiling, reserve, brain reserve, fallback, budgets tokens/cost/concurrency,
  project allow/deny) with the **route preview** (`/v1/route-decisions`) beside it and current
  usage where the account read provides it. Admin scope; disabled with a reason otherwise.
  CLIENT ONLY. P19.5. Nothing the backend does not support is exposed.

## 44. Reference archive strategy (output 35)

Today the at-risk material lives in a stash (`stash@{0}` third-party dashboards), gitignored
folders (`docs/architecture/reference/` via the user's uncommitted `.gitignore` edit,
`notes/reference/`, `references/`), and scratchpads. Proposed (Q-C2):

1. **A private companion repository** `archeus-design-references`, following the existing private
   `claudectl-growth` precedent (private tooling kept out of the public repo). It holds the five V1
   reference files, `notes/reference/*` (renders, `.glb`, the FloatingPragma still), `references/*`
   legacy captures, the stash's third-party dashboards (licences unknown — **private only**, never
   published) and this session's extraction notes.
2. **A tracked manifest in the public repo** (`docs/design/REFERENCES.md`): one row per file —
   path in the private repo, SHA-256, size, source/author, licence, date supplied, and which
   sections of this document cite it. Excluded from the site like the rest of `docs/design/`.
3. **Nothing is moved or deleted** from the current locations without the user's explicit
   approval; the manifest is written first and verified against the files on disk.

## 45. Validation results (this session)

Recorded in §45.1 after the runs completed. Only documentation changed, so these are a
**baseline**: they prove the current code is green before any P19.5 work, not that any feature in
this document exists.

### 45.1 Results

| Check | Command | Result |
|---|---|---|
| SPA type-check + build | `npm run build` (clients/app; output is gitignored `archeus/api/static`) | pass (395 kB JS, 17 kB CSS) |
| client unit tests | `npm test` | **76 / 76 pass** |
| Python lint | `ruff check .` | pass |
| V1 suite incl. e2e | `ARCHEUS_E2E=1 pytest tests/v1` (two runs: `-x` to the first stop, then the files after it) | **2,278 passed**, 13 skipped, 6 xfailed; **1 teardown error** (below) |
| manual site | `mkdocs build --strict` | pass (`docs/design/` stays excluded) |

**The one error is not a product failure.** `test_w22_missions_are_scoped_to_registered_projects`
passed its body; the suite-wide guard `tests/conftest.py:354` then found
`~/.claude-Federico/settings.json` changed during the test (the test never touches Claude
settings; the most likely writer is a live Claude Code session on that account) and **restored the
pre-test content**. If another session wrote to that file in that window, its change was reverted
by the guard. That is recorded for the user; the guard's restore-on-any-change behaviour when
another process writes a shared user file is a test-harness issue outside this task.

Not run here: Playwright visual captures and the manual checks (60 fps on integrated graphics,
Windows Terminal, conhost, physical touch device, PWA install) — they remain owed (§34, R18).

## 46. Decision register after the 2026-09-30 directive

The directive states most of §31's answers in its own words; those are recorded as DECIDED in the
ADRs. What it leaves conditional stays open. Nothing below was inferred beyond the directive's text.

| §31 item | Directive wording (section) | Now | Record |
|---|---|---|---|
| Q-A1 P18 A8 amendment | "If approved by the architecture: Amend P18 A8… Record the amendment" (§29) | **recorded, awaiting approval** | ADR-0030; p18-design-gate §24 |
| Q-A2 operations map | "Include an operations strip / compact live map" (§6) | DECIDED | ADR-0027 |
| Q-A3 motion registry, idle invariant, two clocks | "Create one authoritative motion registry… IDLE = zero animation loops"; "content time != presentation time" (§16, §17) | DECIDED | ADR-0024 |
| Q-A5 browser-owned shortcuts | not addressed | DECIDED (the user, 2026-10-03) | §46.3 |
| Q-V1 thread tints only | "must NOT become skins; themes; appearance modes" (§4.5) | DECIDED | ADR-0026 |
| Q-V2 mark, orbit, favicon | "The actual Archeus mark must appear… mark/orbit can communicate system presence"; favicon states (§4.10, §8) | DECIDED | ADR-0027 |
| Q-V3 static project cage | "static project cage glyph where useful" (§4.6) | DECIDED | ADR-0025 |
| Q-V4 state sentences | "Do not use generic greetings" (§7) | DECIDED | ADR-0027 |
| Q-V5 focus ≠ attention | "Resolve the current focus-vs-attention amber collision" (§18) | DECIDED (focus → thread ink) | ADR-0028 |
| Q-V6 website constellation | not addressed | **open** (P25) | §31 |
| Q-V7 transparency as tokens, no blur | "Transparency may exist as fixed design tokens" (§4.9) | DECIDED | ADR-0028 |
| edge semantics incl. dotted-ready | "EXTRACTED solid, INFERRED dashed, AMBIGUOUS dotted… do not fake it" (§4.7) | DECIDED | ADR-0025 |
| impact view | "What does this affect?" (§4.8) | DECIDED | ADR-0025 |
| red reserved; narrow-graph note | "must be corrected" (§21) | DECIDED | ADR-0028 |
| visual regression | §30 | DECIDED | ADR-0029 |
| Q-P1 P19.5 vs fold into P19; V1.x-3D | "If required, define P19.5… or incorporate into P19" (§28) | **recommended P19.5, awaiting approval** | ADR-0030; PLAN (PROPOSED block) |
| Q-P2 P18 closure scope | "Do not claim P18 is closed until… recorded" (§33) | recorded; colour-defect timing **open** | p18-design-gate §24 |
| Q-P3 rejections | directive §23 REJECT list matches §27 | DECIDED | §27 |
| Q-B1…B7 Core dependencies | "document the required Core contract; assign it" (§12, §27) | owners proposed | ADR-0030 |
| Q-C1 Classic appearance ownership | not addressed | **open** | ADR-0017 amendment note |
| Q-C2 reference archive | "Use the proposed private archive strategy if approved" (§35) | **open** | §44 |

**Conflicts between the directive and this rulebook, resolved:**

| Topic | Directive | Rulebook before | Resolution |
|---|---|---|---|
| pull-to-refresh | "support where useful" but "do not add mobile gestures that conflict with browser/platform gestures" (§19) | REJECTED | **stays REJECTED**: mobile browsers own the pull-down gesture (native reload), and the stream + freshness keep the view current |
| swipe | "support swipe interactions where useful" (§19) | DEFERRED V1.x | **ADAPTED, P19.5**: a horizontal swipe on a row *reveals* that row's actions and never performs one; never from a screen edge (iOS back-swipe); physical check in P23 |
| forget / undo | "forget/undo where the architecture permits" (§11) | dry run, no undo | unchanged: RETRACTED is terminal in Core, so no undo is offered (P16 §18.3 forbids simulating one) |
| TUI | "same state vocabulary… do not reproduce the graphical language" (§20) | P17 as built | unchanged: glyph + word per state (`●` working, `◆` needs you, `✕` failed, `■` blocked/stopped, `│` changed — P19 B2, accepted R13-16, amended R13-15); no motion in the TUI |
| schedules | "upcoming work when Core supports it" (§6) | "P14 follow-up" (not a phase) | owner **P21** proposed (ADR-0030): ADR-0020 decided schedule triggers; P14 D14 deferred them with no owner |

### 46.1 P19.5 interaction decisions (the user, 2026-10-03)

The six questions that blocked R9, R10b and R11 were answered by the user on 2026-10-03. Their
identifiers are the P19.5 register's (D-7, D-8, D-9, D-11, D-12, D-14); they are **not** the
plan's D-1…D-26 or the conversational-orchestration D-7…D-14, which are other decisions. Each
answer is recorded here as given; nothing below widens it.

| Decision | Question | Answer | What it changes | Recorded deviation |
|---|---|---|---|---|
| **D-14** | How does a user reprioritise a mission? | **(b) absolute "Priority N"**: one command sets the mission's absolute priority — Core's existing `POST /v1/missions/{id}/reprioritize` (integer, default 0, higher first; ordering the engine pass only, never routing) | §10 drag-to-reprioritise and Alt+↑/↓ are **not built** in P19.5; the mission inspector's header and its context menu set "Priority" as a number | **Yes — from §10 and §20** (drag, Alt+↑/↓, "Move to…"). Relative ordering waits for a later Core capability (a reorder / relative-move verb), which P19.5 does **not** add. P19.5 resolves no question about ordering scope (within a Work group or global) beyond what the absolute-priority model already is: one integer per mission, read by the engine. Work's grouping and its order within a group are unchanged |
| **D-8** | When does a toast appear? | **(b)** when work that ran **≥ 10 s** finishes **off screen** | `motion.json` `toast` trigger reworded to this; no toast for a successful command | No — `motion.json` is aligned to §17/§41/§47; the "command succeeded off screen" trigger is not built |
| **D-9** | Where do pinned missions live? | **(b)** a **Pinned** group at the top of Work | at every supported width, including a phone; a local preference, never sent to Core | **Yes — from §10's "sidebar pinned missions"** (the sidebar is not where pins live) |
| **D-7** | Resources form: P19.5 or P22? | **(a)** P19.5 builds the §43 fields over the existing `POST /v1/resource-policies/{id}` | priority, allocation ceiling, reserve, own-call reserve, fallback, the three budgets, project allow/deny, beside the route preview | No. P22 keeps "the Resources UI for every ADR-0041 field" beyond §43 (the consumption class, `limits` by subject and tier, project defaults) |
| **D-11** | Ideas stepper without a transition API? | **(a)** a **read-only** stepper: Core's states and each idea's evidence, no transition buttons | Work → Ideas shows where each idea is on the path and what it links to | **Yes — from §43's "the one transition available now"**: Core has no idea-transition command, and none is added to make the stepper interactive |
| **D-12** | Palette search without server support? | **(a)** upgrade the palette now — arrow-key selection, object-scoped actions on the same Core verbs as the buttons, the effect preview — with search **cache-only** | the command bar searches what this client has already read | **Yes — from §18's "server-backed search"**. Server-side search over missions, projects and knowledge is owned by **P21** (Observability views — its acceptance is "every question in §28 answerable from the UI"), as a Core read route; P19.5 adds no search parameter |

### 46.2 Disposition of the P19.5 items with no slice (2026-10-03)

The user asked for each item the 2026-10-03 audit found with no slice to be built now, deferred
with a named owner, or recorded as an exception, with none left open. The user's instruction
named the three possible dispositions; the choice for each item below was made against this
rulebook's own owners and the Core record each item would need. Each row can be reversed by the
user like any other entry in this register.

| Item | Disposition | Why | Owner and dependency |
|---|---|---|---|
| **A-17 activity chip** (R5) | **DEFERRED** | Its text is "the current action", and no Core record holds one: `Execution` (entities.py) records harness, route, process, usage, pressure and the end, never a current tool or step; ADR-0043's `live_work` names live executions, not what each is doing. A chip written from the client's guess would break the Core-read rule (§5, R2) | **P21** (Observability views; `live_work` and the activity stream are P21's): first a Core record of an execution's current action, then the chip. The registry entry stays `approved` with its values |
| **Thread tints** (R6) | **DEFERRED** | The curated list does not exist (legacy palette accents that pass 3:1 and ΔE ≥ 30 from every state colour, §23), and choosing a tint belongs to Control → Appearance, which is P19's (ADR-0044) | **P22**, with R17 (palette → tint migration): the importer brings the legacy palettes the list is drawn from; the contrast + ΔE gate lands with the list |
| **Mission Now tab** (R6) | **DEFERRED** | It is the per-mission conversation, P16 seam S1, which P19 owns and has not built | **P19** (S1). A-05 thread travel extends to it there; its registry entry already names the surface |
| **A-08 attention arrival** | **BUILD NOW** (P19.5) | Fully specified (§17, §20, §21: 240 ms once, cap 1, nav badge, CSS; reduced motion removes it; announced; the count in the tab name) and its only input, Attention's count, is read from Core today | this phase |
| **row-change** (design system §8 "Row insert/remove") | **EXCEPTION** (not built in V1) | §21's table, the authoritative list, has no row for it, and §26 gives it no owner. Animating a removal keeps a row on screen after Core's read has dropped it, and animating an insertion repeats on the same row what the thread rule T2 and A-01 already say. Rows appear and leave at once, which was already its reduced-motion form | none. The registry entry is removed and design system §8 records the exception; adding it later means a new entry with new approval |
| **Q-A5** browser-owned shortcuts | **EXCEPTION until the user answers** — answered 2026-10-03, §46.3; **built 2026-10-04** (Alt+1/2/3 and Alt+J, p19-design-gate §12 item 108), so the text after this cell describes the bindings before then | The client still binds Ctrl/⌘+1, 2, 3 and J (`tokens/navigation.json`, the client tables of P17). In a browser tab Ctrl+1–3 switch tabs and Ctrl+J opens downloads, which goes against R6's "never repurpose standard shortcuts" (§20). Choosing replacement keys is the user's decision (§31) and is not made here. The bindings stay as they are, and every destination stays reachable from the nav, the phone tabs and the command bar | the user's decision; it must be answered before **P26**, and R13 lists it |
| **Pause-all wording** (design system §13) | **DEVIATION**, wording amended | Design system §13 put Pause all in "the Now header, the tray and the command bar". R10a built it in the operations strip, which sits in the shell header on every page, Now included, and on Work, which is where a phone has it. The tray belongs to the Qt shell attach, P19's S7. The command bar's actions are object-scoped under D-12, so it has no Pause all | design system §13 now states what was built. The tray: **P19** (S7). The command bar: none in V1 |

**Sequencing, not decided here.** P19.5 depends on P19 (§31.3: P19 → P19.5 → P20), and no P19
work has been built. Three of P19.5's surfaces are recorded as waiting for it: the mission Now tab
above, T2 on the Relations list and the TUI (testing-strategy §7), and the tray. Whether R13 runs
before P19, with those rows carried into P19, or after it is the user's call. *Decided by the
user, 2026-10-03:* after it (§46.3).

### 46.3 R13 timing and Q-A5 (the user, 2026-10-03)

Both questions §46.2 left open were answered by the user on 2026-10-03. Each answer is recorded
here as given; nothing below widens it, and no §46.1 or §46.2 disposition is reopened by it.

| Decision | Question | Answer | What it changes | Recorded deviation |
|---|---|---|---|---|
| **R13 timing** | Does R13 run before P19, with the waiting rows carried, or after it? | **After P19.** R13, the independent design review, does not run yet. The order is **P19 → the three carried behaviours implemented and integrated → R13**. The three are the mission Now tab, the changed-row marker (T2) on the Relations list and the TUI, and Pause all in the tray | R13 (§36) stays the P19.5 exit, and P19.5 is **not exited** until it has run. R13 is not run against a deliberately incomplete surface. The three carried behaviours are **not** P19.5 implementation failures, and their §46.2 dispositions stand | No. §31.3's P19 → P19.5 → P20 is unchanged; this fixes where R13 sits inside it |
| **Q-A5** | Which keys replace the browser-owned shortcuts? | Archeus replaces the browser-owned **Ctrl+1, Ctrl+2, Ctrl+3 and Ctrl+J** bindings with **Alt+1, Alt+2, Alt+3 and Alt+J** respectively. These are application shortcuts and must not interfere with browser-reserved combinations. Ctrl+Shift combinations are **not** substituted | Q-A5 is **resolved for P19.5**. The new keys must be verified against the supported browser/OS matrix before **P26**. This record does not change the bindings in `tokens/navigation.json` or the client tables (P17); making that change is part of the work verified before P26 | No. It applies R6's "never repurpose standard shortcuts" (§20) |

**Q-A5, the user's readings and the build (2026-10-04).** No Alt+1/2/3 on Linux (Firefox selects
tabs with them there); Alt+J is bound everywhere. Alt alone, matched by the physical key, never
while focus is in a text field. Built in `44b60cc` (p19-design-gate §12 item 108), with the conflict
evidence recorded there. Still owed before P26: the check on a real Mac and on Linux, and a written
supported browser/OS matrix, which no document defines yet.

### 46.4 The V2 UI research boundary decisions (the user, 2026-10-04)

The V2 UI research (`ARCHEUS_V2_UI_RESEARCH.md` §11.2, `ARCHEUS_V2_VISUAL_DIRECTION.md` §18.1)
asked for three V1 boundary decisions and five V2 direction decisions. The user gave direction on
2026-10-04, recorded here. Nothing was built when it was recorded. No §46.1–§46.3 disposition is
reopened by it.

**V1 corrections:**

| Id | Decision | What it changes | Owner |
|---|---|---|---|
| **S-1** | **V1 correction.** The approval card's "What exactly will happen" table must become readable **labelled rows** (Task / Class / Target / Policy, each a key–value pair) when its container is too narrow for four columns, instead of crushing to "Cl / as / s" at 390 px | One component's CSS, keyed to its own container with a container query (DS §5; the codebase's container rule). No copy, verb or order change. Acceptance: at 390 px every label and value reads whole; the existing 390 px overflow/axe e2e plus one assertion that each value sits under its label | The R13 §8 follow-up, before P26 |
| **S-2** | **V1 correction.** The live map on Now drops the visible three-line graph-key caption. It lists the full graph's 14 key groups, and the map uses only the arrow keys and Enter | Discoverability stays, in three places: (1) the map canvas keeps its own `aria-label`, which already says "Arrow keys walk the edges, Enter opens the full graph there", and stops pointing `aria-describedby` at the full key list; (2) when the map canvas has keyboard focus (`:focus-visible`), a one-line hint shows the map's own keys — "↑ ↓ → ← walk · Enter open in the full graph"; (3) the full graph keeps the full caption unchanged. This removes noise from Now (≤ 7 blocks) and keeps explanation where the keys work | The R13 §8 follow-up, before P26 |
| **S-3** | **V1 correction.** The TUI's Now header uses the same state sentence as the SPA (ADR-0027 §5) in place of "Archeus · N missions active · N things need you" | Wording constraint: the TUI renders **the identical sentence** the SPA's `stateSentence` produces: "Archeus is working on N mission(s)." or "Archeus is idle.", then "N need(s) you." or "Nothing needs you." The TUI does not paraphrase it. The counts come from the same reads (active missions, attention count), pluralised the same way. It is painted as the screen's headline (`text`, not `text-2`). No greeting and no glyph is added. A parity test pins the sentence for 0/1/2 of each count across both clients | The R13 §8 follow-up, before P26 |

**Built 2026-10-04** (p19-design-gate §12 items 105–107): S-3 in `df42b37`, S-2 in `ce4a7b6`, S-1 in
`7c95c7c`. S-1's threshold is 51em, measured (item 107). S-2's premise that the map takes only the
arrow keys and Enter is not literally true; the map still accepts the full graph's keys, recorded
as a decision for the user (item 106).

**V2 design direction** (recorded as direction, not as V1 work):

| Id | Decision |
|---|---|
| **V-D1** | Yes. The luminous thread's head and landing ring are functional state light, not prohibited glow. §27 now says so |
| **V-D2** | Yes. The luminous thread is the leading V2 visual signature. Not implemented |
| **V-D3** | Yes. A quiet-motion mode is a V2 design rule: everything except hero moments. Not implemented |
| **V-D4** | Yes, prototype-gated. The four hero moments are V2 candidates, subject to PR-1…PR-6 |
| **V-D5** | Yes, prototype-gated. The larger Segoe UI Variable display treatment is investigated. Typography is not increased globally until PR-4 and its readability measurements pass |

The governing V2 document is `ARCHEUS_V2_UI_ARCHITECTURE.md`. It does not amend any V1 rule
except the §27 clarification above.

## 47. Component map — directive names → primitives

The directive's component list (§22) mapped to §39. Names that would duplicate an existing
component are merged into it rather than created.

| Directive name | Rulebook primitive | Exists today | Note |
|---|---|---|---|
| ArcheusMark, PresenceIndicator | `Mark` (+ orbit) | no | one component; favicon state from the same state |
| ActivityHalo | `ActivityHalo` + graph encoding | no | canvas and DOM forms |
| ExecutionPulse | `PulseTarget` | graph only | extended to rows |
| TravellingMarker | graph `render.ts` marker layer | no | canvas only |
| Thread, ThreadedRow | `ThreadRule` / `ThreadLine` | rule only | `ThreadedRow` is `OperationRow` with the rule, not a new component |
| ConstellationGraph, GraphEdge | `graph/*` (`GraphView`, `encoding`, `render`) | yes | extended, not replaced |
| GraphLegend | `Legend` | no | generated from `encoding.ts` |
| ImpactView | graph mode + mirror list | no | reuses path BFS |
| MissionCard, ExecutionState | `OperationRow`, `StateBadge` | partial / yes | no card grid (lists over cards) |
| AttentionBadge | `AttentionMark` | partial | counts `/v1/attention` only |
| OperationsStrip | `StatusStrip` | no | — |
| LiveMap | `GraphView` bounded live mode | no | ≤ 40 nodes |
| StateSentence | Now header | no | derived from counts |
| ContextPreview | Knowledge / constraints preview | no | `/v1/context/preview` exists |
| DecisionSummary | Recent decisions block | no | client-composed |
| ResourceCeilingForm | Control → Resources form | no | existing route |
| CompletionToast | `Toast` | no | ≥ 10 s of real work, off-screen only |
| OfflineState, RecoveryState | `Fresh` + banner + state matrix | yes | extended |
| Inspector, MobileInspector | `Inspector` | yes (fixed width) | one component; sheet < 600 px as built |

## 48. Traceability matrix — REFERENCE → IDEA → DISPOSITION → COMPONENT → PHASE → TEST → DOCUMENTATION

| Reference | Idea | Disposition | Component | Phase | Test | Documentation |
|---|---|---|---|---|---|---|
| credits: Coscia mark | bounded form, motion that never leaves | KEEP | `Mark` | P19.5 | favicon/orbit gate | ADR-0027 |
| credits: zoetrope | two clocks; activity chips; trace | KEEP / ADAPT / DEFER (trace) | registry, `ActivityChip` | P19.5 / P21 | no-replay gate | ADR-0024 |
| credits: claude-mem | recent-work continuity; context preview; presence in chrome | KEEP / ADAPT | digest, ContextPreview, `Mark` | done / P19.5 | e2e | ADR-0027, §37 |
| credits: cognee + repo-map | graph memory, budgets | KEEP | Relations, graph | done | P18 suite | ADR-0013, ADR-0025 |
| credits: other 8 entries | not UI | n/a | — | — | — | §2.1 |
| skill collections | design-critique rubric, observability 7 ± 2, a11y live regions, anti-slop list, verification discipline | ADAPT (process + rules) | review rubric; Now cap; announcer | P19.5 | Now gate; review record | §37 |
| field photo, renders, .glb | constellation, halos, beads in conduits | ADAPT | graph treatment | P19.5 / V1.x-3D | framebuffer probes | ADR-0025 |
| brand-study | mark; "it stops"; state line | KEEP | `Mark`, `StatusStrip` | P19.5 | idle invariant | ADR-0027 |
| constellation-study / gap | halo; travelling packets; hull volume; bright links | ADAPT | halo, marker, hull | P19.5 | lifecycle, caps | ADR-0024/0025 |
| cluster-handoff | fine lines; dot with outer circle; "the image is not the goal" | KEEP | cored node | P19.5 | encoding test | ADR-0025 |
| memory-UI research | when used; usability | ADAPT / verify Core | Knowledge rows | P19.5 / P21 | — | §13 |
| connections.py | legend, expand-all, hulls; rotating cage, drag | ADAPT / REJECT | Legend, cage | P19.5 | e2e | p18 §24 |
| stage.js, motion.js | state-driven presence; one loop | ADAPT | orbit, loop | P19.5 | idle invariant | ADR-0024 |
| themes.py | palettes; "drama in the interface" | ADAPT (tints) | tint tokens | P19.5 / P22 | ΔE gate | ADR-0026 |
| stash dashboards | control program; circuit traces; journey | ADAPT | strip, marker, plan rail | P19.5 | captures | §6 |
| PROMPT / SP / IP / PDF / PPTX | living system; presence; energy; glass-like; fine lines; clusters; upcoming; decisions; pause all | ADAPT | §4 DNA, Now | P19.5 (+ Core owners) | §7 gates | ADR-0024…0030 |
| R1 Munder Difflin | representation is status; envelopes; caged demo; strip; side panel; evidence | ADAPT / REJECT (avatars, office) | marker, strip, Inspector | P19.5 | captures | ADR-0027, ADR-0029 |
| R2 Vicoa | awaiting badge; offline grey; resume; drafts | ADAPT | `AttentionMark`, Clients, composer | P19.5 | e2e | ADR-0027 |
| R3 Graphify | confidence styles; legend filter; blast radius | KEEP | edges, Legend, ImpactView | P19.5 | confidence + impact gates | ADR-0025 |
| R4 Cognee | bounded views; layout once; classes-only scrub | KEEP / DEFER (scrub) | graph | done / P21 | P18 suite | ADR-0025 |
| R5 migration kit | rulebook; adversarial review; judge | KEEP (process) | — | P19.5 exit, P26 | review record | this document |
| R6 Apple skill | template test; floors; motion rules | KEEP | all | P19.5 | axe, contrast, §33 | ADR-0028 |
| R7 Ship Notes | easing; loop gate; `renderAt(t)` | KEEP / REJECT (`filter` dimming) | registry | done / P19.5 | determinism gate | ADR-0024 |

## Appendix A — method and evidence gaps

- **First-hand this session:** credits; brand-study §5–8; constellation-study (traits 3, 10–12);
  constellation-gap §1–2; cluster-handoff quotes; four reference images and the legacy dashboard
  capture; five decodable `stash@{0}` references (copied read-only via `git show`; the stash is
  untouched); the three current V1 renders; DS, ADR-0016/0017, DR §7/§26/§30, P16 §18/§20.10-12,
  P18 §1.1/A8/A9, PLAN P19–P26; SPA and Core code (via a read-only audit agent, file:line);
  the five V1 reference files read in full (via a read-only agent, line-cited); R1–R7 and zoetrope
  read at source as shallow clones in the scratchpad (via read-only web-research agents).
- **Measured:** focus vs attention ΔE 12.3 (CIE76, sRGB→Lab D65).
- **Gaps:** `inline_image_preview.avif` not decodable; R1's web pages (munderdiffl.in,
  harnessmd.com) and Vicoa's subpages not fetched; Graphify tree/callflow viewers only grepped;
  Cognee's React frontend not traced; zoetrope's marching-ant animation seen in docs only; legacy
  `cluster-spec.md` and `.glb` not re-read; R7 timings read from source, not measured. None of
  these would change a disposition above; each is recorded rather than assumed.
- **Git state preserved:** branch, `5fa0bdb`, the user's `.gitignore` edit, both untracked notes,
  both stashes, all worktrees, `main`, PR #6. The only change is this untracked document.

## Appendix B — states: empty, loading, failure (target)

Every state keeps the identity through its **sentence and its one action**, not through
decoration. Red only when the user must resolve something.

| State | Today | Target |
|---|---|---|
| empty Now | "Nothing is in progress. Tell Archeus what you want below." | state sentence "Archeus is idle. Nothing needs you." + focus the composer |
| no missions | "No missions yet. Tell Archeus what you want on Now." | same + button "Tell Archeus" (opens composer) |
| no attention | "Nothing waits on you." | keep (it is the good state) |
| no graph data | "Nothing recorded around this object yet." | + "Open in list" and the legend, so the view still teaches its language |
| no project | contradictory "Control" / "World" | one sentence, one link to the real form (World) |
| loading | "Reading X…" | static skeleton rows in the shape of the list; progress text only in controls |
| stale / reconnecting / offline | banner + `Fresh` | keep; strip shows the same state |
| permission denied | disabled + reason | keep; the reason names the scope in plain words |
| Core unavailable | `Loadable` red "unavailable" | neutral "Core is not answering — retrying" while retrying; red only after retries stop and action is needed |
| failed execution | ✕ red + raw exit code | ✕ red + plain reason; raw code under Details |
| verification pending | ◆ "Waiting for your acceptance" / ● verifying | keep; halo on the verifying node |
| destructive action | six confirms | + Reject approval, Reject review; Cancel default; no simulated undo |
