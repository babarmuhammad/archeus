# Archeus V2 — Living space

Architecture and visual concept · T-123 · 2026-10-20 · Author: Codex

**Recommendation: evolve Direction E into an inhabitable constellation. Archeus is the central star; projects are volumes of real work; missions and their executions occupy stable neighbourhoods around it. An explicit camera move takes the owner inside a project or mission. Obligations approach the owner, while the underlying constellation keeps its shape. A strong, finite entrance resolves into stillness. The luminous thread remains the signature of a recorded consequence.**

This is a design decision and reviewable proposal, not production authorisation. V1 changes nothing: no V1 code, schema, API, schedule, safety boundary or dependency is changed or required to change for this design. Missing facts constrain V2. Production remains after P26 and separate authorisation.

## 0. Authority, recovery and reference key

Read precedence: owner direction of 2026-10-20 → recovered X.3 §9/§9.7 → recovered reassessment §19 → older committed V2. Existing documents remain intact. The owner has already decided the central star, stronger entrance, immersive 3D and evolution of their constellation; those are not questions being asked again.

Citation prefixes below are literal path aliases, not missing sources:

| Key | Path and status |
|---|---|
| O | `D:/Archeus/.collab/T-123-owner-direction.md` — binding owner instruction |
| B | `D:/Archeus/.collab/BOARD.md` — T-123 at line 1655 |
| R | `C:/Users/mab/archeus-recovery/v2-rebuild/docs/design/` — read-only recovered directory |
| E | `R/ARCHEUS_V2_PRODUCT_UX_REASSESSMENT.md` — RECONSTRUCTED, 99%; register survives |
| X | `R/ARCHEUS_V2_LV2_X3_CORRECTION.md` — RECONSTRUCTED |
| L | `R/ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md` — RECONSTRUCTED; rewritten for E, not authorised |
| F | `R/ARCHEUS_V2_UI_ARCHITECTURE_EXPANSION_FRAGMENTS.md` — FRAGMENT; not a continuous later architecture |
| A | `docs/design/ARCHEUS_V2_UI_ARCHITECTURE.md` — committed architecture |
| V | `docs/design/ARCHEUS_V2_VISUAL_DIRECTION.md` — committed visual research and decisions |
| D | `T-123-reference-digest.md` — source digest; secondary evidence explicitly identified |
| DA | `T-123-digest-addendum.md` — later decision/recovery digest |

`R/name:line` expands to the absolute recovery directory above. Other paths are relative to this worktree. Recovery status comes from `C:/Users/mab/archeus-recovery/v2-rebuild/RECOVERY.md`, §2–3. The prototype is a reference behaviour recovered in parts, not a runnable complete artifact verified here. Its screenshots were lost. No recovery gap grants approval.

E's earlier acceptance is real (`E:795`), as is the later owner's dissatisfaction (`O:10`). The PARTIAL independent reset critique says optimisation displaced the objective (`R/ARCHEUS_V2_PRODUCT_DESIGN_RESET.md:36` in the recovered copy; original-source line numbers differ). This proposal answers that critique with a spatial product model while retaining E's operational decisions; it does not replace E with the reset's alternative navigation.

## 1. LS-1 — Constellation is the product model

**Options.** Restore the ambient legacy field; make a graph-shaped dashboard; or promote real objects and relations into navigable space. **Recommend the third.** The legacy's nested hulls, populated interiors and fine conduits supply form; V1 Relations supplies truth. The retired flow panel supplies the lesson that a relation is structure, not perpetual traffic. We adopt none of the legacy's hash-index bodies, spend-driven ambient speed or arbitrary account colours.

References: `D:245`–`D:313` (three historical artifacts, with original code citations); `docs/architecture/decisions/ADR-0024.md:8`; `docs/architecture/decisions/ADR-0025.md:23`; `clients/app/src/graph/encoding.ts:20`; `O:21`. Scope and deliverables follow `B:1660`–`:1667`. Owner decision: acknowledge LS-Q1's precise scope of the already-directed spatial promotion.

### Bodies and their truth

| Real thing | Spatial role and observable source | Limits / faithful words-only form |
|---|---|---|
| Archeus | Fixed central star, drawn from the existing mark and thread geometry. System aggregate of connection, confirmed safety, live execution count and obligations; no new domain entity or intelligence score | “Core connected · 1 running · 1 queued · 1 needs you.” Disconnected means unknown, not idle. No reactor, fake temperature or background heartbeat |
| Project | Nested faceted hull containing its recorded missions and knowledge; membership from Core and recorded graph edges; open-work count controls clamped size | Name and exact count; unknown count never becomes zero. Hull is a navigable container, not inferred community |
| Mission | Existing circle with state glyph, title, project and branch tail. Lives in its project's stable neighbourhood; enters near plane when it needs the owner | One identity across Overview, mission page and search. “Fix date test · Archeus · fix/date-test · Verifying” |
| Agent at work | Execution triangle adjacent to its recorded mission, labelled by recorded harness/agent identity if available | An execution, not an imaginary worker person. Multiple executions are not automatically distinct people or distinct agent identities. Unknown identity reads “Execution” |
| Idea | Captured idea record, a small neutral endpoint until its kind has a decided encoding; project link only if recorded | Existing idea text/state. No glowing seed growing by itself. Research/edit/comments remain DR-10 scope; no invented time estimate |
| Knowledge | Existing knowledge dot or decision diamond. Loaded on focus/search, with provenance link | A recorded relation can connect it to work; proximity alone never claims causality |
| Device | Endpoint in a separate presence layer: connected / recent / absent / revoked, from existing device/session facts | “Paired phone · recent” is not “owner online”. Presence is in memory; Core restart may report absent. No location, battery, attention or live screen invented |
| Owner | Viewpoint and “You · this session” label, not simulated avatar; local selection and authenticated session | Not an additional all-powerful actor. The camera changes no permissions |
| Other people | Future endpoint only when an authorised people/membership contract exists | Production omits missing people data. Concept explicitly labels future contract. No collaborator cursors, read receipts or assumed simultaneous editing |

Sources: `clients/app/src/graph/encoding.ts:21`–`:41`, `:63`; `X:247` (identity); `X:249` (live versus queued); `E:719`–`:736` (Ideas gaps); `D:589`–`:597` (presence and P22 people dependency); `docs/architecture/ARCHEUS_V2_ASSISTANT_LAYER.md:22`–`:29` (one existing system).

### A spatial grammar with no hidden telemetry

| Variable | Meaning and rule | Source / boundary |
|---|---|---|
| Position | Persistent project membership and deterministic object identity layout. Azimuth is an address, not a score. Existing graph hop depth remains relationship distance inside a focused neighbourhood | ADR-0025:23–29. No physics, drag-to-reassign or continuous layout |
| Depth | Camera focus plus a separately labelled owner-obligation foreground. Approvals, then errors, then live work, then history; depth does not assert a graph edge | S-5/S-6 at `E:841`; new depth/priority overlap explicitly LS-Q2 |
| Size | Project open work, clamped as ADR-0025 already specifies. Mission/agent glyph size identifies kind and zoom tier, not importance or percentage. Core has fixed visual anchor size | `ADR-0025.md:27`; unknown counts outlined and named |
| Light | Static live core dot/halo from a confirmed live execution. One finite pulse for newly recorded output, a thread only over an actual recorded link/cause | `ADR-0024.md:28`–`:40`; “live” is not proof of output or successful progress |
| Colour | Existing semantic tokens and presentation classes. State plus glyph/text; projects stay neutral. Brand violet is static shared ink, never a project category, priority scale or extra state | `encoding.ts:51`–`:60`; LS-Q3 for system-star state-light extension |
| Motion | Real change or explicit user navigation. A mission can approach on obligation arrival; executions never continuously orbit. “Orbit” means bounded relationship around the core, not perpetual revolution | `ADR-0024.md:20`; new camera contract LS-Q4 |
| Edge | Solid recorded, dashed suggested, dotted unclear only if that tier is loaded. Relation is not necessarily cause. The central star's composition tether is visibly distinct and labelled “system membership”, never stored as a fabricated relation | `ADR-0025.md:8`–`:22`; causal light requires explicit provenance |

Objects keep stable world coordinates. “Comes closer” is a labelled foreground projection of the **same object ID**, with its origin tether and breadcrumb; it never changes membership or duplicates a command target. While a user reads or acts, focus and hit targets stay locked. New obligations update a badge/near-plane slot after focus leaves; they never move Approve under a pointer. Owner can return to a project with Back, breadcrumb, Home or search; no flying skill required.

## 2. LS-2 — Alive at first sight, honest at rest

**Options.** Permanent ambient movement; a quiet status list; or a strong opening composition that settles and responds to real change. **Recommend the third**, as directed. No new faux “thinking” state. Strong presence comes from scale, nested space, central identity, meaningful near/far relations and one clear state sentence.

References: `O:10`–`:22`; `A:113`–`:131`; `E:841`–`:843`; `X:249`; `V:1124`–`:1182` as digested in `D:75`–`:120`. Owner decision: LS-Q5 governs repeat frequency; the strong entrance itself is already directed.

### The first second

Proposed story, not measured timing:

1. **0 ms:** safety, Tell, Stop, navigation and current state sentence are already usable. Cached facts say “as of …”; a blank first run says no work exists yet. No blocking splash.
2. **0–240 ms:** reveal the central Archeus mark and fixed project silhouette. This is user-open navigation, not a claim that Core just did work.
3. **240–600 ms:** reveal loaded project volumes and active mission bodies in a single composed expansion. A recorded changed-object thread may be shown only for an eligible fresh event; old events do not replay as new output.
4. **600–900 ms:** near-plane obligation and its Review affordance settle; camera stops. An empty system gets the same identity reveal around Tell, without fabricated bodies.

Any input ends choreography immediately and acts. No sound, flash, stars spawning, rotating cages or theatrical boot diagnostics. No waiting for network to finish an entrance. Default recommendation: full entrance on cold open or return after ≥4 h, matching handover eligibility; ordinary focus/reconnect gets static scene or ≤160 ms fade. Owner may prefer every explicit open, but that reopens K-1/F-3 frequency (LS-Q5). Quiet and reduced suppress the cinematic sequence; reduced gets final composition immediately.

### Reading from across the room

Persistent large sentence answers three questions in fixed positions: **“1 needs you · 1 running · 1 queued”**, then **“Fix date test — verifying”**. Numbers are fixture examples, not current repository telemetry. State text is never hidden behind the core. Amber near-plane approval answers what needs you; live mission's static halo answers where work is; task/action words answer what it is doing only if recorded.

Use accepted Display optical size on the hierarchy-opening sentence, not a global type increase (V-D5 / `F:36`; PR-4). Across-room acceptance is measured on the owner's actual display and viewing distance, not inferred from a PNG. Selecting any light opens its record and timestamp. If only mission state is known, say “Verifying”; do not guess “Running checks”.

Between output batches the picture stays still even while work runs. A retained live halo means execution remains recorded live, not that it is responsive. “No output since 14:32” is permissible only from a timestamped observation; “unresponsive” needs V2-U3's separate contract. No heartbeat animation substitutes for missing liveness facts.

Idle: **“Nothing running. Tell Archeus what to do.”** Keep today's recorded outcomes and projects (S-7); no empty black void. Stopped: **“Nothing runs until you resume.”** Offline: **“Core cannot be reached · state unknown · snapshot as of …”**, no live light or available remote commands. Reconnect redraws current truth without replaying entrance or output.

Sources: `A:520`–`:529`; `X:242`; `docs/design/ARCHEUS_V2_UI_RESEARCH.md:509`–`:519`; `ADR-0024.md:28`–`:40`.

## 3. LS-3 — Shared space is shared records with different authority

**Options.** A simulated agent office; synchronous multiplayer presence; or one Core-backed workspace, device-specific affordances and explicit availability. **Recommend the third.** This gives shared-space meaning today without claiming a new collaboration backend.

References: `docs/architecture/ARCHEUS_V2_ASSISTANT_LAYER.md:22`–`:31`, `:50`, `:100`–`:106`; `X:241`–`:250`; `D:589`–`:597`. Owner decision: LS-Q6 on future people/presence investment, not on bypassing current permissions.

| Participant / surface | Sees | Can do |
|---|---|---|
| Owner desktop | Full permitted work constellation, evidence and local presence status | Existing Tell, inspect/search, existing decision routes, existing two-press stop; commands remain in opaque controls outside canvas hit ambiguity |
| Execution / agent | Its actual assigned context and tool permissions | Existing execution only. Being visible does not grant an agent a new input channel or workspace control |
| Paired phone | Same permitted facts, compact E overview, pushed mission/approval page and confirmed safety | Existing mobile decisions and P20 step-up where supported; Cancel/Start prepare Tell per Q14, then require Send. No phone terminal/file/git/live desktop preview |
| Terminal | Same object IDs, counts, state sentence, phases, attention and reason/provenance links as text | Existing authorised terminal commands. No colour or camera needed to find or decide work |
| Another person | Nothing beyond current auth model; future concept is labelled | No assumed approvals or delegated ownership until a separate membership/permission contract is decided |

Selections and camera are local. No global camera that another device can move. An approval changed elsewhere becomes recorded current state, not a second executable approval; stale actions must revalidate through existing commands. Devices are neither agents nor security principals invented by drawing them.

Q12 stays: **no PIN on resume today**; phone PIN is only where existing step-up actually requires it. Q13 stays: new Tell work while stopped is **not accepted**, not queued secretly. Q16 stays: phone pushes concern approvals/emergency stop only, carry no mission/project name, and never approve on tap. Core-down stop authority remains existing tray / `archeus estop`; the canvas gains none.

## 4. LS-4 — Futuristic through Archeus, with binding limits

**Options.** Copy cinematic HUD materials; keep flat E; or use the owner's hull-of-populations, thread, depth and central star as functional architecture. **Recommend the third.** References contribute principles, not dependencies:

| Reference lineage | Adopt | Exclude |
|---|---|---|
| Owner constellation / ADR-0025 | Nested real work, cored active bodies, fine receding relations, stable fingerprint | Ambient hash-index population and continuously travelling packets |
| Huw Prosser | Precise meta column, type hierarchy and minimal separators in logs and lists | Monospace body or site personality copied wholesale |
| Thinking Orbs | Separately drawn recognisable state figures per size | Perpetual loop and inferred thinking/searching states |
| thisisreyy / hasibjaan / eadmin2 / bertrandmbanwi | Material restraint, measured visual cost, explicit action kinds, typed state-to-visual table | Fake audio/telemetry, reactors and bloom |
| openclaw / shaurya | User intensity ceiling, hidden-page parking, reduced-motion renderer stop | Fake idle waveform, reduced motion implemented only as lower DPR |
| Dix01 / kvdoe | Enforce brief with gates; use as failure comparison | Glow-everywhere, infinite animation, HUD font identity |
| Reels / film UI craft | Readable named states, stable places, one focal hierarchy | Movie spectacle without operational purpose |
| Libraries.dev / Anime.js / Three.js | Real mic amplitude principle only, if voice eventually exists; explicit performance question for 3D | Effect packs and animation dependencies; automatic Three.js adoption |

References: `D:19`–`:71` provides the closed research's repo-by-repo path/line evidence; `V:980`–`:1120` and `docs/design/ARCHEUS_V2_UI_RESEARCH.md:308`–`:369`. These are inherited research findings, not claims that external repositories were freshly audited today. Push-to-talk remains XR-10; voice adds no fake waveform.

### Renderer recommendation and parity

Use one domain projection feeding semantic DOM and a bounded spatial renderer. A true 3D model has x/y/z positions, camera and picking; it need not require WebGL. First prototype: native CSS perspective/transform planes for a small loaded neighbourhood, opaque DOM labels and SVG relation overlay, reusing the parking scheduler and generated tokens. This is a hypothesis, not a claim that arbitrarily many DOM bodies meet budget. Label placement is deterministic and frozen between explicit changes. No transparent full-screen particle layer.

Camera motion must not quietly animate SVG path/paint properties: prototype transformable edge geometry or a static overlay that settles at the destination, with all relation meaning preserved in text throughout. Whether the native approach can maintain legible cross-depth edges within the measured cap is an explicit LS-P2 question.

If it fails, a demand-rendered WebGL2 spike may be separately considered. Three.js is not selected by this document. If neither meets budgets, retain E's faithful static projection and report the immersive implementation blocked; do not call a 2D fallback completion of the owner's 3D request. No WebGPU/SwiftShader dependency. Renderer and budget choices require LS-Q4/LS-Q7 before production.

Phone stays E: five tabs, compact counters and waiting/error/running order; mission/project/idea push with Back and no tabs; fixed answer bar on approval page, not Overview. Default below 600 px is the semantic list. A small static location motif may show selected path only if LS-Q8 approves changing the hidden-graph rule; never put a mandatory 3D miniature above tasks. Phone sizes retain X.5: body 13/18, title 14/20, caption 12/16, label 11, input 16, buttons 40 px high, bars 48/50/42. The recovered claim that 40 px height meets a 44 pt floor is not accepted as proof: preserve density, propose ≥44×44 non-overlapping hit regions; verify actual geometry later. LS-Q8 records the discrepancy.

Reduced motion: no camera interpolation, orbit, travel, automatic approach or scale; final view on explicit navigation, same breadcrumbs, near-priority ordering, state glyph/text and record. Quiet retains bounded L2/L3 and removes L4. Forced colours uses outlines, tiers by line style and text; opaque panels replace translucent hull fill. Body contrast ≥4.5:1, state/non-text ≥3:1; colour never sole meaning. Preserve focus through navigation; no focusable hidden backfaces. DOM mirror is equivalent primary access, not a secondary stripped product.

Terminal example (illustrative fixture):

```text
ARCHEUS  Core connected | Not stopped — accepts new work
1 needs you | 1 running | 1 queued
Overview > Archeus
NEEDS YOU  Search provenance | Archeus | feat/search  [Review]
RUNNING    Fix date test      | Archeus | fix/date-test | Verify
EXECUTION  Codex | live; latest recorded result: tool completed
QUEUED     Index notes       | Notes   | feat/index | waits for agent
WHY        recorded relations / provenance (only when available)
```

### Hard budgets and unresolved measurements

Retain zero visual-driving timers, zero running animations and zero rAF at rest; park when hidden/blurred/minimised/context-lost, and on reduced motion. Repeated output never becomes a perpetual core pulse. Caps: one travelling thread, eight markers, twelve pulses, one finite orbit; pulse ≤1/object/2 s; orbit ≤1/5 s. Camera and entrance share one interruptible sequence; never compose competing camera and hero sequences.

Retain Qt integrated-GPU p95 ≤16.7 ms target, no motion-caused long task; phone 60 fps L2/L3 and no motion during scroll/background; DPR ≤2, ≤500 drawn nodes, no per-row offscreen canvas. The old 1,000-node/60 fps requirement conflicts with 500 drawn: prototype 1,000 source objects with a bounded ≤500 visible projection and report separately whether the legacy gate meant 1,000 simultaneously drawn (LS-Q7). Do not erase the discrepancy.

Committed budget is ≤10 KB gzip added visual work (`A:553`–`:567`). Recovery F:72–80 gives ~9.7–10.6 KB for U0; later evidence §9 gives ~9.2 KB repriced U0 and ~12.5 KB later visual work, with LV2-1 recording LD-1 closed (`R/ARCHEUS_V2_LATER_UI_LV2_1_GATE.md:22`). These measure different artifacts and pricing; they are not additive or interchangeable. Later owner budget approval does not prove 3D fits, nor silently amend every committed gate. LS-Q7 asks for one measured baseline and cap; until answered, use the stricter ≤10 KB as spike kill ceiling. No estimate here grants a new runtime dependency.

## 5. LS-5 — E's places are doors into one space

**Options.** Add “Space” as a sixth place; rename E back to Now/Work/World; or keep E and give its existing places spatial continuity. **Recommend the third.** Same stable IDs, viewport state and return paths; no parallel navigation system.

References: `E:832`–`:877`; `X:230`–`:250`; `L:63`–`:99`. Owner decision: LS-Q1/LS-Q2 for replacing the visual Overview and project timeboard primacy, not for renaming approved places.

| Older function | Direction E and spatial manifestation | What stays plain |
|---|---|---|
| Now | **Overview:** Archeus-centred whole space; near plane waits, then errors, middle live work, far context. Read order and DOM follow S-5 | Exact counts, reasons, deadlines; accessible ordered mirror |
| Work | **Missions:** bounded mission bodies and selected mission's six-phase line. Zoom opens the existing one-page mission, not a new detail route | Plan steps, decisions, verification checks, terminal-style activity log |
| World | **Projects** with recorded Relations inside project context; **Ideas** with current-Core capture/start subset | Project timeboard retained as direct view; idea text, provenance and details |
| Attention | Near-plane lens and “Waiting for you” entries inside Overview and Missions; not a sixth place | Full evidence and consequences on mission page. No acknowledge/snooze without Core record |
| Control | Fixed frame door, outside camera | Resources, pairing, policy, appearance, safety and permission forms; ceiling L2 |

S-2 stays: left places and project list always visible on desktop. Scene cannot swallow safety/navigation. S-3 stays: no mission spines on Overview or sidebar. S-8 is the later six-phase Understand → Plan → Approve → Run → Verify → Review, with completed ticks and failed cross; final completion is state/result, not a resurrected seventh Done station. S-17's phase-column project timeboard remains available, but proposing spatial project view first changes its primacy (LS-Q2). Record stays mission log and decision history; no new day-scoped Record place or revival of DR-7 by default.

Inspecting a body opens evidence; it never approves by proximity, dragging, zooming or clicking a star. Approvals retain S-9/S-10 as corrected by Q18. Q14b supersedes S-12/S-13's imagined Explain/Fix: only real resume actions for eligible blocked missions, no retry button for FAILED, no note forwarded to a nonexistent agent channel. Ideas keep Q14c's prepared Tell request; research/comments stay future DR-10. Time remains recorded size bands, no invented hours.

E's phase-change motion has a surviving **proposal and measured prototype**, not an owner decision: `R/ARCHEUS_V2_LV2_X2_REFINEMENT.md:260`–`:286` records a 600 ms head plus 240 ms landing and parked rest. This corrects the addendum's broader statement that E motion was not prototyped. The later plan still asks head versus fill/ring and bulk demotion (`L:520`, G-15). Recommend fill/ring until decided; LS-Q9 carries that choice. Existing stop lapse remains the decided **3 s**, not X.2's prototype 2 s (`L:67`).

## 6. Explicit supersessions and questions — no silent rule changes

| Existing decision / rule | Effect of binding owner direction or later recovery | Status / question |
|---|---|---|
| A V-3 at :53, no 3D; research reject-for-app at :92 | O:16–22 explicitly requires immersive navigable 3D | **Already superseded for V2 spatial main surface.** LS-Q4: renderer, camera constraints and gate amendment? V1 untouched |
| A:84–97 rejects invented central orb and uses three scale centres | Owner chooses Archeus core/star | **Already superseded in composition.** Core is existing system aggregate, not an invented entity. LS-Q3: extend state light to the mark while retaining thread signature? |
| V-D2, A:68–82: thread sole leading signature; constellation staged behind it | Owner promotes constellation to whole-app language | Thread stays action signature; constellation becomes structure. LS-Q1: accept this division, rather than silently replacing V-D2? |
| V-D1 narrow functional head/ring exemption; rejected decorative glow | Star light from confirmed activity could exceed narrow exemption | LS-Q3: permit only static live mark and event-bounded emission; reject bloom/ambient breathing? |
| A:149–156 depth=focus, vertical=priority; ADR-0025 depth=hop | Obligations come closer to owner | LS-Q2: authorise separate labelled obligation plane; keep graph-hop tiers inside neighbourhood? |
| Graph as inspection, A:498 hidden below 600; ADR-0016/0027 spatial-home tension in D:536–544 | Owner directs main immersive space | Spatial primary already directed desktop. Mirror remains coequal. LS-Q8: phone motif or strict list only? |
| K-1 first-open-after-4h; V-D4 four gated heroes; V-D3 quiet | Strong opening may imply every open | LS-Q5: preserve ≥4h/cold-open full sequence, ≤900 ms, quiet/reduced suppression? No fifth ungated hero |
| S-5/S-6 ordered Overview; S-17 timeboard first | Main scene replaces list-like composition and project foreground | LS-Q2: visual spatial ordering and project spatial-first accepted? DOM order, phase board and plain mirror retained |
| LD-2 / D-2 three places and V1 naming | S-1/Q2 accepted E's five names | **Already superseded**, not reopened (`E:817`, `:823`) |
| S-16 / SS-4/6 PIN on resume; S-11/12/13 Explain/Fix | Q12/Q14 authoritative real-Core subset | **Already superseded** (`X:241`–`:246`); no PIN-resume fiction or unsupported repair channel |
| S-9/S-21 no caption under buttons | Q18 consequence rows/outcome labels; L carries desktop and phone | **Already amended** (`X:250`; `L:78`, `:96`). Use outcome labels, not tooltips as sole consequence |
| V-D5 global display increase prototype gate | PR-4 accepted hierarchy sentence/headlines, not global scale | Keep limited variant; no new blanket size increase (`F:36`) |
| ≤10 KB vs later LD-1 ~12.5 KB, 500 vs 1,000 nodes | Different recovered measurements and an incompatible old gate | LS-Q7: reconcile explicitly; no automatic increase |
| PR-5 C/D and PR-6 human gate; Q6 still open | Acceptance exists but human identification/dogfood not established | LS-Q9: confirm which human gates carry forward. Never mark passed from recovery fragments |
| Old phone body 17 / ≥44 targets vs X.5 dense 13/18 / 40px buttons | Real-phone approval supersedes presentation scale; exact hit-floor proof disputed | LS-Q8: keep approved density with ≥44×44 hit regions? |
| A reduced/quiet, no idle motion, no fake telemetry, safety, no avatars/per-cluster hues | Owner retains faithful equivalents and calm after entrance | **Not superseded**. Cinematic presence does not authorise decorative loops, people surveillance or new commands |

Other open questions stay owned: Q3 “armed” vocabulary remains V1/P20's, with V2 using confirmed words; Q9/DR-9 agent messages, Q10/DR-10 Ideas, Q11 duration require later contracts, not V1 changes. Website constellation ownership Q-V6, Classic Q-C1 and archive Q-C2 remain outside this app proposal. No decision here claims them.

## 7. LS-6 — Build path and truthful V1 reads

**Options.** Rebuild all V2; add a renderer before checking meaning; or replay E's known fixtures and semantics, then prove each spatial addition. **Recommend the third.** Prototype specifications below are future work; no tests or prototype executions were run for this card.

References: `L:18`–`:38`, `:539`–`:555`; `F:60`–`:80`; `E:804`–`:811`; `docs/design/ARCHEUS_V2_UI_RESEARCH.md:165`–`:170`. Owner decision: LS-Q9 carries human gates; LS-Q4/7 gate implementation mechanisms. Restoring E behaviour is reference recovery, not authority to start LV2-2.

### Read boundary

V2 reads existing mission/task/execution state through presentation classes, approvals and recorded decisions, plan steps, verification, project membership, knowledge and loaded relation confidence, device/session presence and `Message.links`. Current evidence stream `/v1/executions/{id}/stream` has redacted agent text/tool call/result records, **not tool output and not event timestamps**; Timeline provides times. Join by an actual identifier only. Tool output remains DR-8. Source: `E:635`–`:651`; `D:413`–`:440`.

P21 trace, events, server search, current-action facts, live_work and explicit execution→produced-object provenance are **capability-dependent reads**, not assumed endpoints ready in this branch. The digest predates ongoing integration; this design neither certifies nor blocks that integration. At V2 implementation time, inspect the shipped read contracts and capability availability:

| Read | Purpose | Missing / stale behaviour |
|---|---|---|
| P21 trace + timestamped events | Show recorded action and phase history, bounded “since you looked” and trace inspection | State only; “action not recorded”. No synthetic task name or timestamp from text stream |
| Explicit cause/provenance + Message.links | Thread from actual intent/action to changed object, Explain why | Show recorded relationship as relationship; no causal travel guessed from adjacency |
| P21 search | Find a mission/project/knowledge and enter its loaded neighbourhood | Existing supported local search explicitly labelled with scope; no claim of global completeness |
| Status live_work / execution records | Core counts and action labels; separate queued from live | Render only available facts; missing status is unknown. EXECUTING without live execution is queued only when both reads are authoritative |
| Presence | Device layer and freshness | Absent/unknown as recorded; never infer a person from recent device |

Read adapter is a V2 view projection, not a second router, memory, mission system or event store. Keep record time distinct from presentation time; re-read/seek/reconnect never emits historical motion. Trace replay, if available, is clearly “as of” inspection. No V1 work is requested to make missing fields exist; V2 hides or labels unsupported features and waits for independently shipped facts.

### Reuse measured PR work without inventing completion

| Gate | Recovered evidence | Reuse and future pass / kill |
|---|---|---|
| PR-1 | PASS WITH VARIANT: signature thread, pen on light theme; p95 target/no tearing/idle recorded (`F:33`, `:64`) | Keep thread/pen. Re-measure in new scene: p95 ≤16.7 ms, no tearing, idle zero; tearing or >20 ms kills richer treatment, retains prior thread |
| PR-2 | Hand-built spatial transition passed; native View Transitions **STOP** in Qt (`F:34`, `:65`) | Reuse hand-built approach where recovered; do not resurrect native API by citing old architecture. New camera must pass; failure uses cut/≤160 ms fade |
| PR-3 | Layered recede variant, application scale stopped, ~1.1 KB (`F:35`, `:66`) | Keep opaque/scrim inspector; no whole-app shrinking. Any discomfort kills camera interpolation/recede, not access to object |
| PR-4 | Display accepted for opening sentence/headlines, ~0.24 KB (`F:36`) | Keep that scope; Qt/HC/200% no clipping or layout shift. Fail → 28/34 at 600 fallback |
| PR-5 | Accepted state-figure direction, conflicting C/D fragments; identification gate unresolved (`F:38`, `:67`) | Recover actual glyph catalogue before selection. Every state identifiable without colour at 12/16/20 px; failure redraws. A treatment letter is not a decision |
| PR-6 | K1–K3 ≤900 ms; Qt p95 16.7–16.8, 27–96 ms CPU/occurrence, rest 0 px; K4 design only awaiting P21; **0/14 human days** (`F:68`) | Keep conditional candidate, not global pass: 16.8 does not strictly meet 16.7. Human fortnight per existing gate unless owner amends Q6; any disabled hero demotes to L3. K4 needs explicit cause |

### Additional spatial prototypes — proposed, not run

| Prototype | Pass criteria | Kill / honest fallback |
|---|---|---|
| LS-P1: E → space semantic replay | Same object IDs, exact counts and actions across normal/idle/queued/failed/expired/stopped/offline; every fact known/derived/not recorded; keep E's 174/174 capture, 24/24 mutations, 11/11 motion, 24/24 shell comparison as historical baselines (`X:267`–`:270`), not new results | Any invented fact or unsafe action kills spatial treatment of that fact; retain E component |
| LS-P2: immersive camera and bounded renderer | Explicit zoom into project then mission, Back returns same location; zero drift at rest; input interruptible; p95 ≤16.7 ms integrated Qt; ≤500 drawn/DPR2; known 20-mission stress fixture plus 1,000-source-object case; measure gzip + heap, no retained scene growth | Any cap breach or discomfort: cut/static spatial projection; if immersive contract remains unmet, report blocked rather than declare victory. WebGL spike requires separate go-ahead |
| LS-P3: opening / across-room comprehension | ≤900 ms, facts and Stop usable at frame zero, no replay on focus/reconnect. Owner plus existing comparison-set participants identify core, running work and next owner obligation in 5 s; target ≥90% correct, no synthetic work | If owner finds it list-like, lifeless or generic HUD, reject art direction. If fatigue, shorten/demote choreography, preserving spatial model |
| LS-P4: priority approach | E order holds; focused object/hit target never moves; no selection loss; record explains why object approaches; resolution returns object to stable address | Failure → fixed priority shelf with explicit origin, no automatic depth travel |
| LS-P5: parity and access | Phone approved density retained; each fact/action reachable by text, keyboard, screen reader, HC, reduced motion, 200% text; no hover-only proof; real phone no accidental decision and Stop always available | Remove spatial input dependence/motif; never remove facts or supported authority |
| LS-P6: sustained-use integrity | Replay uses real recorded causes, renderer parks between changes; accepted hero governor and 14-day owner log remain unless LS-Q9 changes them | Any fake activity or hero rejected by owner → remove/demote effect. Never add idle motion to repair subjective liveness |

Sequence: recover/reference E behaviour and missing treatment identity → static semantic scene and parity → bounded camera/renderer spike → entrance and meaningful event light → owner visual judgement and relevant human gates → production planning after V1/P26 and explicit authorisation. Do not reimpose the intentionally skipped LV2-1 W2 programme (`E:804`, `:807`); new visual judgement and already-open PR gates are distinct.

## 8. Concept artifacts and interpretation

See `v2-concepts/README.md` for file-by-file prompts, decision mapping and limitations. Images are proposed compositions with **declared sample work**, not captures of current Core or implemented UI. Their rendered text, line tier, phone spacing and lighting are illustrative; this document wins where image generation diverges. Image generation is not a performance, accessibility or product-authorisation gate.

## 9. Decisions the owner must take

Already binding: improve recovered E; central Archeus star; navigable immersive space; cinematic entrance then calm; owner's constellation language, no generic HUD. Remaining questions concern concrete scope and unresolved old decisions:

| ID | Decision | Recommendation |
|---|---|---|
| LS-Q1 | Record constellation-as-structure alongside V-D2, and replace list-first desktop Overview without adding a place? | Yes: E's five doors, thread remains consequence signature; coequal semantic mirror |
| LS-Q2 | Amend focus/priority depth grammar and S-17 spatial-first project view? | Labelled owner-obligation foreground; stable coordinates and focus lock; timeboard directly available |
| LS-Q3 | Extend narrow V-D1 state-light permission to central Archeus mark? | Static live mark plus finite recorded-output pulse only; no glow field/heartbeat |
| LS-Q4 | Renderer and navigation contract under owner-directed 3D? | Bounded native perspective prototype first; explicit zoom, no scroll-flight/inertia; any WebGL dependency separately justified |
| LS-Q5 | Full entrance every open or K-1-style eligibility? | Cold open / ≥4h return, ≤900 ms, immediately usable; quiet/reduced static; never reconnect replay |
| LS-Q6 | Shared records first or new people/presence contracts? | Existing owner/execution/device facts first; other people await P22/later authorised contracts |
| LS-Q7 | Which measured budget governs, and does 1,000-node gate mean drawn or source? | Reconcile later LD-1 with ≤10 KB gate on one shipped baseline; no automatic increase; ≤500 drawn from 1,000 source pending clarification |
| LS-Q8 | Phone static locator and touch-floor discrepancy? | Strict E list by default; optional locator only if approved; preserve dense type with ≥44×44 separated hit regions |
| LS-Q9 | Carry Q6/PR-5 identification and PR-6 fortnight, resolve C/D identity, and decide G-15 phase head / bulk demotion? | Keep human gates open until verified or amended; locate catalogue rather than guess; phase fill/ring until head decided; do not reopen skipped W2 |
| LS-Q10 | Carry Q9/DR-9, Q10/DR-10 and Q11 into new V2 scope now? | Hold new contracts; ship existing truthful subset, recorded size bands, no invented duration/agent messaging |

No tests, installation, commit or push forms part of this design delivery.

## Owner decisions 2026-10-20

Authority: updated `O`, “Answers to ARCHEUS_V2_LIVING_SPACE.md section 9” and “Phone and terminal”. This dated addendum takes precedence over conflicting recommendations above; earlier sections remain as the Round 1 record. It changes V2 design only, not V1 commands or production authorisation.

| Question | Binding answer and effect |
|---|---|
| LS-Q1 / LS-Q2 | **“Si, lo spazio sostituisce la panoramica (Codex)”**. Opening lands in the space; constellation is structure and thread remains consequence signature. The list remains the equivalent mirror for accessibility, phone and terminal, not the mandatory phone opening. Apply §1's labelled owner-obligation foreground, stable membership and focus lock; retain direct project timeboard access (§5). This resolves the list-first/spatial-first and focus/priority conflicts recorded in §6. |
| LS-Q3 | **“Respira mentre lavora”**. The core **BREATHES slowly while work is running**, driven only by the real running fact; it pulses on newly recorded events and stays still at rest. Reduced motion keeps a static running cue plus text. Running is neither queued, connected nor inferred from a mission phase; missing/stale facts mean unknown and stop the breath. This explicitly supersedes §1 grammar's static live core light and motion-only-on-change restriction **for the core only**; §2's “Between output batches the picture stays still even while work runs”; §6's proposed “static live mark and event-bounded emission; reject … ambient breathing”; §9 LS-Q3's “Static live mark plus finite recorded-output pulse only”; and §4 “Hard budgets” zero-animation/zero-rAF rule **while confirmed running work exists**. It also amends the earlier V-D1/ADR-0024 no-continuous-motion restriction to this single factual running cue. It does not permit revolving missions, fake heartbeat, bloom, activity speed tied to spend, or decorative loops. |
| LS-Q4 | **“Prima prototipo leggero (Codex)”**. Bounded native perspective prototype first, explicit zoom, no free flight. WebGL dependency only if prototype evidence shows need; none selected now (§4, LS-P2). |
| LS-Q5 | **“All'avvio o dopo assenza (Codex)”**. Cold open or return after **≥4 h**, entrance **≤900 ms**, controls usable immediately, never on reconnect. Reduced motion receives final composition immediately (§2). |

Breath proposal: one restrained core-only expansion/contraction over roughly 6 seconds, no opacity blink; exact amplitude/cadence remains a prototype judgement, not another telemetry field. Events retain finite, rate-limited pulses; an event pulse yields to the breath rather than multiplying loops. Pause motion when hidden, backgrounded, scrolling or when the owner disables it. Offer a persistent motion preference: slow running breath can exceed five seconds, so §4/earlier architecture's claim that finite durations remove any need for a pause control no longer applies. Still-at-rest means **nothing confirmed running**, not merely a quiet output stream. Reduced/quiet static running mark carries exactly the same fact; no prediction of progress. LS-P2/LS-P6 must distinguish running animation cost from genuinely idle parking.

**Still open: LS-Q6, LS-Q7, LS-Q8, LS-Q9 and LS-Q10.** Respectively: people/presence contracts; measured budgets/source versus drawn nodes; phone locator and touch-floor reconciliation; old human gates/treatment identity/phase motion; carried Q9–Q11 contracts. Owner has now rejected dense list-first phone direction: LS-Q8 no longer asks whether to preserve that design. Its remaining choice is the concrete live-remote composition/accessibility fallback and measured geometry. This is a proposed resolution, not a claim that LS-Q8 or any old human gate passed.

## LS-7 Phone: the live remote

Owner verdict on recovered phone and concept 05: **“a long list, the space is not visible, too dense / small, not pleasant to look at.”** Replace the phone composition from scratch while retaining E's records, permissions and action semantics. A reduced constellation is the first view, not a miniature desktop dashboard or a list with a decorative star above it.

### Options and recommendation

| Option | What opens | Trade-off |
|---|---|---|
| A. **Core and near plane — recommended** | Large Archeus thread-star, current work sentence, two or three labelled work bodies in a bounded spatial composition; one owner obligation projects into a stable foreground zone | Space visible immediately; direct action without a crowded graph. Overflow uses a named count and one-tap full mirror. |
| B. Core and one mission | Core plus a single selected mission, with explicit Previous/Next work controls | Largest type and simplest one-hand reading, but conceals simultaneous work; total counts remain necessary. |
| C. Full pocket constellation | Whole project neighbourhood with explicit zoom | Richer navigation, more label collisions and harder one-hand use. Keep as a one-tap optional space inspection, not home. |

Recommend A in either PWA or native shell. No free camera on phone. Core occupies the upper-middle visual field, work/action sentence directly beneath it, obligation foreground just above the thumb controls. Projects remain sparse neutral hull fragments, not coloured planets. Only recorded mission/execution labels appear. Main screen has no scroll dependency for core, current work, highest-priority request or Stop. At large text sizes, prioritise those essentials and allow vertical scroll for supporting detail; never shrink type to preserve artwork.

Proposal at a 390 CSS-pixel reference viewport: headline 30/36, work title 24/30, body 18/26, secondary text 16/22; controls at least 48×48 CSS pixels with separated hit regions and safe-area padding. These deliberately replace §4's X.5 body 13/18, title 14/20 and 40-pixel controls. Actual platform units, contrast and text reflow still need device measurement. No 11-pixel operational text.

### Four screens, one moment of work

All names/counts below are fixtures, not current telemetry. Moment M: Core connected, not stopped; **Fix date test** has one live execution in **Verify**; **Search provenance** has one pending plan decision when it arrives. No queued work in M. A moment before arrival, only the running mission is present.

1. **Remote / running, no owner request.** Header: Archeus and connection. Large core with slow running breath, neutral Archeus hull and blue mission glyph. “1 running” / “Fix date test — Verifying”. “Nothing waiting for you.” Tap mission body or its title opens mission; tap core opens system state. Lower dock: Tell, Places, Stop. Places opens all five E destinations in one tap, with search and the text mirror; these are navigation choices, not a sixth product place. No stacked mission feed.
2. **Remote / needs you.** Same world coordinates and same running fact. Amber **Search provenance — Review plan** approaches the foreground with origin “Archeus”. Readable “1 needs you · 1 running”. Foreground shows what and why in short recorded words and **Review**; tap Review opens the complete decision. The core remains visible above it. More obligations appear as “2 more need you”, opening the ordered mirror in one tap. New arrivals never replace the request under a finger or move focused controls; update count until focus leaves.
3. **Decision / deliberate one gesture.** Full-page decision, Back and persistent Stop. Show mission, branch, plan version, exact proposed tasks/targets, recorded reason and consequences, then an explicit **Approve plan** button in thumb reach. For an eligible non-step-up decision whose current V1 route permits direct approval, one tap on that labelled button is the gesture. No swipe across the constellation, hold-to-confirm theatre or invisible gesture. One gesture applies to the **decision after review**, not permission to approve unseen material from home. Supporting evidence can scroll; action never implies unseen plan content is safe.
4. **Mission opened from remote.** Back returns to same remote selection. “Fix date test / Archeus / fix/date-test”, large “Verifying”, mission circle with linked “Codex — execution” triangle, six phases Understand / Plan / Approve / Run / Verify / Review in readable wrapped text. Below: recorded task if available, latest evidence and Activity/Plan/Why links. No terminal emulator, file/git controls, fabricated tool output, predicted completion or fake percentage. Tell and Stop remain reachable without scrolling.

**Safety contract wins over gesture count.** Read `clients/app/src/surfaces/Attention.tsx` and §3/§5: pending/eligible checks, required scope, current approval identity and `action_hash`, plan binding, existing idempotency key and step-up remain mandatory. A changed/expired/decided-elsewhere request disables the action and rereads; retry cannot create another decision. Display Core's own consequences, never “Approve & run” unless that consequence is actually true. Step-up enters the supported PIN path before final action, or explains why this device cannot decide. Where binding rules require confirmation, show prose confirmation with Cancel default; no gesture bypass. Reject retains its explicit confirmation and “A decided approval cannot be changed.” No approval undo window is offered: V1 has no approval inverse. Do not invent a five-second cancellation toast. A future action gets Undo only if its real inverse and binding window exist. Sources: §5 S-9/S-10/Q18; `docs/design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md` undo rule; existing Attention implementation. Approval receipt says submitted until Core records outcome, then shows recorded result.

Stop is a persistent opaque lower-corner control on home, decision, mission, navigation sheet and error states, clear of OS edge gestures and keyboard; retain existing two-press stop with **3-second** lapse (§5), no swipe-to-stop. When disconnected, label remote Stop unavailable and explain existing local tray/`archeus estop` route; a native app cannot stop an unreachable Core by implication. New Tell while stopped remains rejected. An approval notification only opens the request and revalidates it; never decides.

### What E contributes, what owner replaces

**Reuse:** five destinations and names; ordered waiting/error/running semantic mirror; pushed mission/project/idea/decision pages with Back and no tabs; decision answer area on decision page only; existing Q12 no PIN-on-resume, Q13 stopped behaviour, Q14 prepared Tell plus Send, Q16 approval/emergency-only anonymous push, Q18 visible consequences; same object IDs and scopes. Keep list mirror as a first-class one-tap choice and optional remembered accessibility home.

**Replace:** §3 compact E phone overview; §4 hidden graph below 600 pixels, strict-list default and X.5 density; §6/§9 LS-Q8 recommendation to preserve dense type; LS-P5's “approved density retained”; concept 05 and README's dense-phone recommendation. Five permanent home tabs become a one-tap Places sheet in this proposal; E destinations are preserved. Small locator becomes an actual bounded core/work scene. Counts become a readable sentence, not a compact counters bar. Owner selected live-remote role; exact dock/locator and hit geometry remain LS-Q8 review items. No desktop navigation change follows from this phone proposal.

### Accessibility and motion

Reading/focus order: connection and safety, core summary, needs-you summary and Review, running work, navigation, Stop; dedicated Stop landmark/shortcut available without traversing the graph. Every glyph has a named semantic control; decorative edges hidden from assistive technology. Text mirror exposes all work and the same actions, with stable IDs and reasons. Do not announce every breathing cycle or stream record. Politely announce a new request once; never steal focus. High contrast uses opaque surfaces and glyph/text state; minimum proposed text contrast 4.5:1 and controls 3:1 must be measured. Support 200% text, screen-reader activation, switch access, visible focus and keyboard operation. No action requires dragging or precision tracing. Reduced motion removes entrance/approach/breath/travel and presents static core running cue plus the same foreground priority and text. Paused animation never hides running status. Quiet uses the static cue. Pressed targets stay still.

### Web/PWA versus native — owner choice after concepts

These are implementation options, not claims that either notification/backend contract is built. Both use the same four compositions, paired authority and existing command validation. A plain browser tab differs from an installed PWA.

| Concern | Responsive web / installed PWA | Native app |
|---|---|---|
| Notifications | Web Push where supported and authorised. iOS/iPadOS Home Screen web apps support it from 16.4; installation/permission is part of onboarding. Plain iOS tab is not equivalent. | Platform notification integration; separate permission, delivery and backend work. Native does not guarantee timely delivery or authorise lock-screen decisions. |
| Gestures and feel | Large labelled taps meet this design; browser/OS edge gestures need accommodation. No required custom gesture or haptic dependency. | Platform navigation, gesture and haptic integration can be designed deliberately; still expose labelled controls and accessible alternatives. |
| Offline | Service worker can cache shell and expressly permitted snapshot. Stale facts show “as of”; no approval/Stop queue or background command replay. | Can persist permitted snapshot in app storage. Same unknown-state and no-offline-command rules; offline app is not offline Core authority. |
| Pairing and security | Existing paired-device flow over authenticated secure connection; design token/session handling, revocation, expiry and cache clearing explicitly. Never place secrets in URLs or cache credentials/decision payloads as static assets. | Same scopes and step-up, plus platform secure-storage integration to design and review. Native shell is not extra authority or a bypass for pairing/revocation. |
| Reachability | Owner must be able to reach Core through the existing authorised route; installation does not expose Core publicly. | Same network requirement. No new relay, tunnel or cloud service implied. |
| Effort | Reuse semantic DOM, tokens and phone routes; add install/offline/push lifecycle and real-device checks. Lower expected initial effort; this is an estimate, not a delivery promise. | Additional client/platform lifecycle, packaging/distribution, secure-storage and notification integration. Higher expected maintenance; no framework chosen. |

**Recommendation:** judge visual direction on platform-neutral concepts, then prototype PWA first unless owner requires native integration that the prototype cannot satisfy. Do not select platform by claiming a native-only look: this core/foreground/tap design works on both. Owner question **LS-Q11 (new, open)**: after seeing the four screens, choose installed PWA first or a dedicated native app, and name the native-only requirement if any. This does not reopen LS-Q1–5.

Platform references, checked 2026-10-20: [WebKit: Web Push for Web Apps on iOS and iPadOS](https://webkit.org/blog/13878/); [MDN: Offline and background operation](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Offline_and_background_operation). Native integration and relative effort above are design assessments, not measured delivery evidence.

## LS-8 Terminal: the constellation in text

Owner direction: **“the same language, in text.”** Use a small text constellation first, then fast ordered lists. Do not substitute an ASCII dashboard full of boxes or a terminal rendering of a phone. All examples are exact plain-text fixtures; production colour is optional and carries no unique information.

### Layout and grammar

80×24: two fixed status lines, about seven lines of sparse constellation, one owner-obligation foreground sentence, then ordered keyboard list and persistent key/help line. No side panes at this size. Reserve bottom command/status rows so Stop never scrolls away. At wide widths (proposed ≥120 columns), keep the same bounded constellation on left and one focused detail/evidence pane on right, separated by whitespace; do not scale a starfield to fill width. Narrower than 80: collapse diagram to named core/project path and keep all records accessible in list. Overflow is counted, never silently omitted.

| Glyph | Meaning | Colour / monochrome |
|---|---|---|
| `*` | Archeus core, a crossing-thread anchor | Ivory; explicit `RUNNING 1`, `IDLE` or `UNKNOWN` word carries state |
| `o` | Mission | Blue only for confirmed running; label names phase/state |
| `^` | Execution linked to mission | State colour where known; `execution` word distinguishes it |
| `!` | Needs-owner foreground marker attached to a mission | Amber plus `NEEDS YOU`; attention marker, not a new domain kind |
| `.` | Loaded knowledge record | Neutral and labelled; no decorative star dust |
| `/` `\` `-` | Sparse composition tether or recorded relation | Label `member` for membership composition; label actual relation type for edges. Do not infer causal traffic. |
| `>` | Focused list entry | Text focus marker remains in monochrome; inverse optional |

Project names are neutral text anchors, not additional state glyphs. Terminal projections can adapt the app's kind figures to ASCII but must include kind/state words: never claim ASCII `!` is the canonical approval shape. Suggested/unclear edges are omitted unless loaded and named explicitly in focused detail. No box-drawing borders, animated spinner, true-colour dependency, emoji or ambiguous-width Unicode requirement. Honour terminal theme/contrast and no-colour setting; 16-colour fallback and plain text preserve every fact. Diagram coordinates describe membership/focus, never progress, attention score or inferred people presence.

For normal motion, a slow low-amplitude colour emphasis of the single `*` may mirror the real-running breath without moving text or cursor; terminal palette limitations fall back to static `* RUNNING 1`. Event pulse may briefly bold the affected named row once, only on a recorded new event. Never repaint whole terminal per frame. Reduced motion, quiet, monochrome and noninteractive output are static. This is the faithful text equivalent allowed by owner direction, not a fabricated animation substitute.

### Exact 80-column-friendly overview — moment M

```text
ARCHEUS  Core connected | Not stopped - accepts new work
1 needs you | 1 running | 0 queued                  CONCEPT FIXTURE

                         * ARCHEUS  RUNNING 1
                        / member
                 Archeus
                 /     \
   o Search provenance   o Fix date test - Verifying
       ! NEEDS YOU           ^ Codex - execution

NEEDS YOU  Search provenance - Review plan
Why: Plan approval required.  Enter opens what you approve.

> 1 ! Search provenance  Archeus  Review plan
  2 o Fix date test     Archeus  Verifying

j/k select  Enter open  / find  g places  t Tell  s Stop  ? help
```

The diagram and first list row refer to the same mission ID; there is only one actionable focus/command target. Tether “member” expresses system composition, not a stored causal edge. Counts are M's exact fixture counts. No extra project or unknown population implied.

### Exact mission frame — same running mission

```text
ARCHEUS  Core connected | Not stopped - accepts new work
Overview / Archeus / Fix date test                 CONCEPT FIXTURE

* ARCHEUS - member - Archeus - member - o Fix date test
                                             \
                                              ^ Codex - execution

Fix date test   fix/date-test
Verifying | 1 live execution
Understand / Plan / Approve / Run / [Verify] / Review

Latest record: Tool result received
Task: not recorded

> Activity
  Plan
  Why / recorded relations

Enter inspect  b Back  / find  g places  t Tell  s Stop  ? help
```

“Task: not recorded” avoids treating a phase label or tool result as proof of current action. No timestamp manufactured from the untimestamped stream (§7). Six phases stay mission-only.

### Exact decision frame — no silent single-key approval

```text
ARCHEUS  Core connected | Not stopped - accepts new work
Overview / Archeus / Search provenance             CONCEPT FIXTURE

* ARCHEUS     o Search provenance  ! NEEDS YOU

Review plan v1 | feat/search
What: Search recorded sources; show provenance.
Why: Plan approval required.
Consequence: use the exact consequence recorded by Core.
A decided approval cannot be changed. No Undo is available.

Approve selected. Confirm only after reading current plan.
Confirm this decision? Type y to confirm; any other key cancels.

s Stop remains available outside the confirmation input
```

This last frame specifies confirmation layout, not an invented Core consequence. Replace placeholder consequence from the actual approval before enabling confirm; missing required consequence is explained and does not become permission to guess. Stop is a global named action outside text-input capture (see keys below); typing `s` at confirmation cancels first and invokes Stop's existing first press, never approves.

### Keys, safety and parity

`j/k` or arrows select; Enter opens only; `/` searches; `g` opens five destinations; `b`/Esc returns; `t` opens Tell, never sends; `?` exposes all keys. Selection does not execute. On a decision page, `A` selects Approve and opens the prose confirm; `R` selects Reject and opens its confirm; request changes appears only where supported. Typed `y` confirms the currently bound decision, any other key cancels (existing terminal contract at `docs/architecture/p17-design-gate.md`, R5). Step-up stays supported-path-only. Do not equate one terminal key with the phone's eligible reviewed button tap; terminal's existing confirmation remains.

`s` invokes the global Stop control from navigation/decision states; repeat within the existing 3-second lapse to confirm, otherwise disarm. In Tell/search/PIN text inputs, literal characters remain text: Esc leaves input, then `s` invokes Stop. Always show that escape route alongside text entry; no undocumented Ctrl-C repurposing. Confirmation is not a freeform input and `s` cancels it before Stop. No command queues while offline. Receipt and errors use Core records, not optimistic success. Final keybindings remain prototype proposals except binding V1 safety/terminal confirmation behaviour.

Desktop, phone and terminal share IDs, project membership, pending/eligible approval identity, phase vocabulary, counts, stale-state rules, reasons and recorded consequences. Core state, highest owner request and current work are visible immediately on each. Opening a node/row goes to the same record, never a different authority. Desktop zoom, phone tap and terminal Enter are equivalent inspection; each surface retains its binding command and confirmation path. Back restores local selection; no global shared camera. Lists remain rapid access and full semantic mirror, not the terminal's sole visual identity.

## Round 2 artifact status

Design additions above are reviewable; no production implementation, tests, installs, commit or push was performed. Requested seven new raster concepts are pending the generated-output-only exception: imagegen documents automatic writes outside the worktree and exposes no destination parameter. Under the current strict write boundary, calling it would violate the owner instruction. Exact per-image prompts/captions are recorded in `v2-concepts/ROUND2_PROMPTS.md`; these are **not generated images** and no missing asset is linked as present. Existing 01–08 remain unchanged; concept 05 is historical and superseded for phone design.

## Owner decisions 2026-10-21

| Question | Binding answer and effect |
|---|---|
| LS-Q11 | **"i am fine with a pwa app for now"** (owner, 2026-10-21, after the round 2 phone concepts 09–12 were delivered in 7c67958). The phone live remote is prototyped first as an installed PWA, under LS-7's web/PWA column: Web Push where supported, no offline command queue, the existing paired-device flow. "For now" keeps native open: it is revisited only if the prototype cannot meet a named requirement. |

**Still open: LS-Q6, LS-Q7, LS-Q8, LS-Q9 and LS-Q10.**

## Round 3: reviewer feedback and design response (2026-10-21)

Labels used below. **Reviewer feedback** is the opinion of Federico Coscia, a colleague, quoted from `D:/Archeus/.collab/V2-feedback-Federico-2026-10-21.md`. It is not an owner decision. **Design proposal** is this response; it stays open until the owner answers §5 or a later dated decision. **Owner decision** means only the dated decisions above; this round records none. Vote words are his: "Mi piace" (like), "Così così" (so-so), "Non mi piace" (dislike).

### 1. Feedback by image

**Reviewer feedback.** Overall: "Voglia di usarlo sì decisamente", with the space structure "molto bella". The gap he names: "Manca forse poi tutta la parte di come far partire poi i task job, e far fare le cose ad archeus. Qui si vede solo l'interazione con lavoro già fatto o in corso."

| Image | File | Vote | His words (quoted) | Response |
|---|---|---|---|---|
| 01 | 01-entrance-storyboard | Non mi piace | "Molto crowded, compattato … troppo denso e piatto, font peggiori e disegno di figure troppo semplificato" | §3 |
| 02 | 02-now | Mi piace | "This is peak"; "molto bello il design delle stelle costellazioni figure geometriche" | §2 |
| 03 | 03-mission | Mi piace | "This is also nice, should then be integrated with the design of … 02" | §2 |
| 04 | 04-projects-ideas | Così così | none | no change this round |
| 05 | 05-phone (first version) | none | none | superseded by LS-7 (owner, 2026-10-20) |
| 06 | 06-shared | Mi piace | "The 3d visualization should always be consistent with one style." | §2 |
| 07 | 07-calm | Così così | none | no change this round |
| 08 | 08-day-attention | Così così | "I would make a dedicated section for a plan that has to be approved, where we can give feed back on the plan, on to change it etc." | §4 |
| 09 | 09-phone-remote-running | Non mi piace | none | §3 |
| 10 | 10-phone-needs-you | Così così | the constellation "con archeus in mezzo" with small task bodies; review "più in linea con lo stile stellare", "slim, trasparenza" | §3 |
| 11 | 11-phone-one-gesture | Così così | "Un po' sproporzionate le dimensioni, farei i testi più piccoli" | §3 |
| 12 | 12-phone-mission | Non mi piace | none | §3 |
| 13 | 13-terminal-constellation | Mi piace | "Io preferisco questo di tutti"; "chiaro il disegno in ascii"; the dimmed command row "scurita" | §2 |
| 14 | 14-terminal-mission | Non mi piace | "Non è chiaro cosa sia e cosa voglia dire, dove uno dovrebbe leggere" | §3 |
| 15 | 15-same-moment | Non mi piace | "Troppo semplificato, sembra versione giocattolo, non è chiaro cosa dovrebbe fare e cosa ogni cosa fa" | §3 |
| T1 | term-overview | Così così | "Questo non male ma è un po' troppo compattato" | §3 |
| T2 | term-mission | Non mi piace | none | §3 |
| T3 | term-decision | Non mi piace | none | §3, §4 |

The reviewer gives no words for 09, 12, T2 and T3. Grouping them as "unclear or toy-like" is this response's reading of the dislike votes, not something he wrote. The "terzo esempio" he refers to for the dimmed command row is not identified; §2 assumes the key line of the LS-8 frames.

### 2. Kept, and the rules they set

**Design proposal.** Images 02, 03, 06 and 13 are kept. Each keeps its direction and becomes a rule for every view.

- **R-1, one 3D style everywhere.** Reviewer feedback (06): "The 3d visualization should always be consistent with one style." The rule: one projection and depth tier scheme, one glyph set (§1 encoding table), one hull treatment (sparse neutral boundary lines), one line-tier rule and one thread rule. Overview, Missions, Shared, Calm, the phone and the reduced-motion variants all use it. A view may crop or move the camera; it may not restyle.
- **R-2, mission inside the space language (03).** Reviewer feedback: 03 "should then be integrated with the design of" 02. The mission view is the same scene seen from inside its project, through the explicit camera move in LS-1. Same hulls, glyphs, state colours and thread; the core stays a small orientation anchor. It is not a second visual system.
- **R-3, devices in the space (06).** Reviewer feedback: "it also shows the paired phone and connected devices in the space." Devices stay endpoints in the presence layer of LS-1 and LS-3 ("This desktop · connected", "Paired phone · recent"). They are not agents or principals. "Other people" remains a labelled future contract.
- **R-4, the terminal constellation as reference text form (13).** Reviewer feedback: "chiaro il disegno in ascii" and "la riga dei comandi scurita". Design proposal: the key/help line is dimmed to the secondary text token and still meets 4.5:1. The state sentence, the Stop row and every key stay at full strength. Dimming never hides a binding.
- **R-5, narrow navigation (02).** Reviewer feedback: the small side tab "lascia molto spazio alla pagina". S-2 already requires this; no change.

### 3. Reworked

Each item gives the reviewer's point, then the design change. Where the reviewer gives no words, the change is this response's.

**01 Entrance (LS-2).** Feedback: crowded, too dense and flat, worse fonts, figures too simple.
Proposal: at most one core, two project hulls and three bodies per frame. Depth comes from three real scale tiers (near, middle, far), not from flat placement. Glyphs use the §1 encoding sizes and are not simplified. Labels keep at least one glyph diameter of clear space. Headline and labels use the same UI type as 02 at the accepted optical size (PR-4), not a lighter cut. Timing stays 0, 240 and 800 ms, inside LS-5's 900 ms.

**09 Phone, remote running (LS-7, screen 1).** Feedback: dislike, no comment.
Proposal: the same composition as 10 without a request. Archeus thread-star in the upper middle; one blue mission body labelled "Fix date test · Verifying"; a project hull fragment labelled Archeus; one recorded relation line. Sentence beneath: "1 running" and "Nothing waiting for you." Dock with text-labelled Tell, Places and Stop. Every body carries a name and state word, so nothing reads as decoration.

**10 Phone, needs you (LS-7, screen 2).** Feedback: constellation with Archeus in the middle and small task bodies around it is liked; he imagines it "si avvicinerebbe magari in 3d alla "stella" di quel task", then a "pannello review, con un design più slim, trasparenza".
Proposal:
- Archeus at the centre. Two or three task bodies around it at stable addresses, each a small labelled star with its state word. Overflow stays a named count ("2 more need you").
- Only the obligation body is amber. Review performs one bounded step to that body's star (about 400 ms, interruptible; reduced motion: immediate). No pan, no pinch, no free camera (LS-7 stands). Owner question 3.
- The review sheet is slim, rising about 40% of the screen, with What, Why, Core's consequence line and Open decision. Translucency is decided (2026-10-21, §7, Q2): a tint only where text keeps 4.5:1 over the worst background behind it; opaque under reduced transparency and high contrast.

**11 Phone, one gesture (LS-7, screen 3).** Feedback: "Un po' sproporzionate le dimensioni, farei i testi più piccoli."
Proposal: reduce the LS-7 proposal at a 390 CSS-pixel viewport: headline 30/36 to 26/32; work title 24/30 to 20/26; body 18/26 to 16/24; secondary 16/22 to 14/20. No operational text below 14 px, which keeps LS-7's no-11-pixel rule. Controls stay at least 48×48 so the reduced text does not shrink the Approve control. Decided 2026-10-21 (§7, Q1, "Yes, cut it"): body 16/24, headline 26/32, minimum 14 px, controls 48 px, verified on a real phone before build. The work title 20/26 and secondary 14/20 are as written here; the owner's answer did not name them.

**12 Phone, mission (LS-7, screen 4).** Feedback: dislike, no comment.
Proposal: replace the wrapped horizontal phase text with a vertical list of six rows (Understand, Plan, Approve, Run, Verify, Review), each with a tick, cross or current marker and a state word. Every block has a text heading: Latest record, Task, Evidence, Activity, Plan, Why. Tell and Stop stay docked. The facts match the LS-8 mission frame.

**14 Terminal mission (LS-8).** Feedback: "Non è chiaro cosa sia e cosa voglia dire, dove uno dovrebbe leggere."
Proposal: 14 and T2 are one image. The exact LS-8 mission frame (T2) is the reference, with fixed headings in the frame's order and a single key line at the foot. 14 is not regenerated as a separate free rendering.

**15 Same moment (LS-7 and LS-8 parity).** Feedback: "Troppo semplificato, sembra versione giocattolo, non è chiaro cosa dovrebbe fare e cosa ogni cosa fa."
Proposal: three labelled panels, each named by its job in words: Desktop (space and inspection), Phone (live remote), Terminal (text constellation and lists). Under each: the same four facts in the same order (Core state, needs you, running, queued) and the same mission ID. Footer: "Same IDs, same authority, different inspection." Every glyph gets a text label; decorative marks go.

**T1 Terminal overview (LS-8).** Feedback: "un po' troppo compattato."
Proposal: the 80×24 text in LS-8 remains the canonical content. The artwork uses the wide layout (120 columns or more): the bounded constellation on the left, a focused detail on the right, and a blank line between the status lines, constellation, obligation sentence, list and key row. Spacing is not added inside the 80×24 fixture, which would break its 24-row limit.

**T2 Terminal mission (LS-8).** Feedback: dislike, no comment. See 14 above: T2 is the reference frame.

**T3 Terminal decision (LS-8).** Feedback: dislike, no comment.
Proposal: replace the one-key confirmation frame with the plan review page of §4.2, in text: plan tasks, Core consequence lines, keys A, C, R, and the typed-y confirmation as a separate second frame with Cancel as the default. Existing terminal rules stand (p17 R5).

### 4. Starting work and approving plans (new)

**Reviewer feedback** names the gap quoted in §1. **Design proposal:** accept it. This section adds a start flow and a plan review page. Each row below says whether V1 already has the capability. Nothing here is a V1 change; no V1 capability is assumed beyond the routes named.

Principle: nothing appears before Core records it. No optimistic star, no queued send, no ghost body.

#### 4.1 Starting a task (design proposal)

| Step | Owner does | Surface shows | V1 today |
|---|---|---|---|
| 1. Open | `t` on desktop or in the terminal, Tell dock on phone, or "New mission" in a project inspector | Prepared empty Tell field, project chip set to the focused project, Cancel visible. Nothing sent | Tell is prepared, not sent (Q14). Whether Tell accepts a project scope is unverified; check the Tell contract before building the chip |
| 2. Compose | Writes what to do; may change the project and add success criteria lines | Field stays editable; Stop stays visible | `POST /v1/conversations/{id}/messages` (control). Mission create: `POST /v1/missions` with title, objective, project_id, success_criteria |
| 3. Send | Presses Send | "Sending to Core…" | Explicit send (Q14) |
| 4. Clarify | Answers Core's question if it asks | Core's question verbatim with Proceed anyway, Drop it, Answer | Intent clarification exists: `POST /v1/intents/{id}/clarify` |
| 5. Record | Nothing further | A neutral outlined body appears in the chosen project with state word "Planning". One finite reveal near its project, 600 ms at most; immediate under reduced motion | Mission reaches CREATED then PLANNING in Core. Body, reveal and placement are new |
| 6. Plan | Reviews if asked | Either the recorded line "plan v1 approved within policy" and the body moves to running, or the body turns amber with "Plan ready · review" | Auto-approval within policy and plan_needs_approval are recorded in Core. Amber placement is new |

Start path, owner decision 2026-10-21 (§7, Q4): Tell first, the project form second. Tell's project-scope check (above) still applies before the chip is built.

Stopped: Tell is rejected, not queued (Q13). Offline: Send is disabled with its reason; no queue (LS-3). Ideas start only through the prepared Tell request decided under Q14c; nothing further this round (DR-10).

#### 4.2 Plan review (design proposal)

Entry: Review on the amber body (desktop and phone), the decision row (terminal), or `A`, `C`, `R` on the decision frame. One page, three layouts: right inspector, pushed page without tabs, text frame. Content in this order:

1. Identity: mission, project, branch, "Plan v{N}", and the version list. Older versions are read-only.
2. Why: Core's recorded reason ("Plan approval required").
3. The plan: ordered tasks with the targets Core records. No silent truncation; a count names anything hidden.
4. Consequences: Core's own text for approve, request changes and reject. A missing consequence disables the action and says why.
5. Actions (footer on desktop, fixed bar on phone, key line in terminal):
   - **Approve plan.** Explicit label, as in the V1 terminal. Phone: one tap for an eligible non-step-up decision (LS-7). PIN first where step-up applies. Desktop and terminal: prose confirmation with Cancel as default. Bound to the action hash and the plan version on screen.
   - **Request changes.** Opens the note field with V1's wording: "What should change? (the planner reads this)". Submitting records the decision; the mission is planned again.
   - **Edit plan.** The owner edits the task list; saving makes the next version. Before saving the page says: "Saving makes plan v{N+1}. Approval of v{N} no longer applies." The approval of the previous version is superseded, as V1 does today.
   - **Reject.** Cancels the mission under Core's consequence text. "A decided approval cannot be changed." No undo.
6. Rules: no approval from a list, home screen, push notification or swipe (LS-3, LS-7). The Approve control disables and rereads if the plan changed or was decided elsewhere (LS-7 stale rule).

The reviewer's request for "feed back on the plan" is answered by Request changes and Edit plan, both existing. Per-task comments are not in V1. The owner decided on 2026-10-21 that they are wanted now (§7, Q5), so their contract is proposed in §8, not built.

#### 4.3 What V1 supports and what is new

| Capability | V1 today | Status in this design |
|---|---|---|
| Read plan and versions | `GET /v1/missions/{id}/plan`, `GET /v1/plans/{id}`; the terminal lists plan versions | Exists. The version list on the review page is new |
| Approve, reject, request changes | `POST /v1/approvals/{id}/decide` (approve scope) with action_hash, optional note, step_up, expected_version | Exists. The review page layout is new |
| Note to the planner | Request-changes note; mission planned again | Exists |
| Edit plan as next version | `POST /v1/plans/{id}/edit` (approve scope), superseding the prior version's approvals; PlanEditor on the mission page | Exists. The save warning copy is new |
| Auto-approval within policy | plan_auto_approved decision, recorded | Exists. Shown as a recorded fact, never as a silent approval |
| Core consequence text | Consequence strings for each decision | Exists. Used as given |
| Start by Tell | `POST /v1/conversations/{id}/messages` (control); clarification at `POST /v1/intents/{id}/clarify` | Exists. The prepared-send panel and any project scope are new or unverified |
| Start a mission in a project | `POST /v1/missions` (control): title, objective, project_id, success_criteria | Route exists. The project-inspector form is new |
| Per-task comments on a plan | None | New. Owner decision 2026-10-21 (§7, Q5): wanted now. Contract proposed in §8, not built |
| Question to the planner without changing the plan | None; the request-changes note is the only channel | New. Not proposed this round |
| Undo an approval | None | Not proposed |

Authority: deciding and editing plans need the approve scope; starting missions and Tell need control. V2 adds no authority. Step-up stays where V1 already requires it.

### 5. Owner questions

Each question needs an owner answer. Recommended answers are proposals.

1. **Phone type scale (§3, 11).** *Answered 2026-10-21: yes, cut it (§7).* The reviewer asks for smaller text; the owner called the earlier phone "too dense / small". Recommended: body 16/24, title 20/26, headline 26/32, nothing under 14 px, controls 48×48. Verify on a real phone before accepting.
2. **Translucent review sheet (§3, 10).** *Answered 2026-10-21: tint only if readable (§7).* The reviewer asks for a slim, transparent panel; the concept README and §4 reject translucent glass panels. Recommended: allow a translucent tint only where text meets 4.5:1 over the worst background behind it, and go opaque under reduced transparency and high contrast.
3. **One zoom step on the phone (§3, 10).** *Answered 2026-10-21: yes, one bounded step (§7).* LS-7 says no free camera on phone. Recommended: allow one bounded step to the chosen task star, no pan or pinch, immediate under reduced motion.
4. **Primary way to start work (§4.1).** *Answered 2026-10-21: Tell first, form second (§7).* Tell (free text, Core clarifies) or a structured mission form in the project. Recommended: Tell first, the project form second. Both use existing routes. Confirm first that Tell can carry a project scope.
5. **Comments on a plan (§4.2).** *Answered 2026-10-21: per-task comments now. This rejects the recommendation below (§7, §8).* A per-task comment thread would be a new contract and the planner would have to read it. Recommended (rejected): ship the existing note and plan edit now; decide per-task comments as a separate contract later.
6. **Do per-task comments reach the planner? (§8.3).** *Answered 2026-10-21: only with request-changes (§7).* Recommended: yes, but only inside a request-changes decision, so one decision carries the note and the selected comments. A comment never reaches the planner on its own.

### 6. Round 3 image brief

**Design proposal, for Codex image generation later.** Thirteen images: nine reworked (01, 09, 10, 11, 12, 15, T1, T2, T3) and four new (N1 to N4). Every image carries a CONCEPT FIXTURE label and fixture names and counts. Every glyph carries a text label. Same glyph set, type scale (§3) and state colours as the rest. No glow, bloom, orbit, reactor, glass or decorative particles. The review sheet in R3-10 is rendered opaque in this brief; the translucency rule decided on 2026-10-21 (§7, Q2) applies only once the 4.5:1 check passes on the real background.

**R3-01 Entrance (reworked from 01).** Three equal frames labelled 0 ms, 240 ms and 800 ms, each in the same desktop shell: "Not stopped · accepts new work", Tell, Stop, narrow left navigation. At most three bodies per frame. The first frame shows the Archeus star at centre and the state sentence. The second adds the Archeus project hull with "Fix date test · Verifying" in blue and a "Codex · execution" triangle. The third adds amber "Search provenance · Review plan" nearer, with a Review button. Three depth tiers by scale; headline "1 needs you · 1 verifying" in the 02 type.

**R3-09 Phone, remote running (reworked from 09).** Portrait app screenshot, no device frame, 390×844 proportions. Archeus thread-star in the upper middle, one blue body "Fix date test · Verifying" at a second position, a project hull fragment labelled Archeus, one recorded relation line. Beneath: "1 running" and "Nothing waiting for you." Bottom dock with text-labelled Tell, Places and Stop.

**R3-10 Phone, needs you (reworked from 10).** The R3-09 composition with an obligation. Archeus stays centre; two or three labelled task stars around it; amber "Search provenance · Review plan" nearer with a Review button. Sentence "1 needs you · 1 running". A slim opaque sheet at the bottom shows What and Why in short words and the Review button. "2 more need you" appears as a named count only if a second obligation exists.

**R3-11 Phone, one gesture (reworked from 11).** Full-page decision at 390×844: Back, "Search provenance", mission and branch, "Plan v1 of 1", three task rows, Core's Why and Consequence lines. One "Approve plan" button, 48 px high, in thumb reach; "Request changes" and "Reject" as secondary buttons; Stop in the lower corner. Body 16 px, headline 26 px. No Undo text.

**R3-12 Phone, mission (reworked from 12).** Back, "Fix date test", "Archeus · fix/date-test", "Verifying" large. Six-row vertical phase list with tick, current and empty markers and state words. "Latest record: Tool result received" and "Task: not recorded". A linked "Codex · execution" triangle. Links Activity, Plan and Why. Tell and Stop docked.

**R3-15 Same moment (reworked from 15).** Three labelled panels: Desktop (space and inspection), Phone (live remote), Terminal (text constellation and lists). Under each, the same four facts in the same order (Core state, 1 needs you, 1 running, 0 queued) and the same mission ID. Footer: "Same IDs, same authority, different inspection."

**R3-T1 Terminal overview (reworked from T1).** Wide layout at 120 columns: bounded constellation left, focused detail right. The LS-8 80×24 text content, with a blank line between blocks. Key/help row dimmed; Stop row and state sentence at full strength.

**R3-T2 Terminal mission (reworked from T2; replaces 14).** The LS-8 mission frame as exact text with its headings in order: scope, identity, state, six phases with Verify marked, Latest record, Task, links, key line. Monospace, no decorative colour; state words carry meaning.

**R3-T3 Terminal plan review (reworked from T3).** Two frames. The first: "Review plan v1 | feat/search", What, Why, Core's consequence lines, the task list, and keys "A approve · C request changes · R reject · Esc back · s Stop". The second, after A: "Confirm this decision? Type y to confirm; any other key cancels." with Cancel as the default.

**R3-N1 Start a task, desktop (new).** The overview scene at reduced opacity behind a prepared Tell panel along the lower edge. Field "Tell Archeus what to do", project chip "Project: Archeus", Send and Cancel. Line beneath: "Nothing is sent until you press Send." No preview body in the scene. Stop visible.

**R3-N2 Start a task, phone (new).** Tell as a full sheet from the dock: text field, project line, Send and Cancel. Above it the core is visible and smaller. One state line "Sending to Core…". No new body yet. Stop in the lower corner.

**R3-N3 Plan review, desktop (new).** Scene at reduced width on the left; opaque right inspector "Review plan v1 · Search provenance". Header, Why, ordered tasks, Core consequence lines, version list with v1 current. Footer: Approve plan, Request changes, Edit plan, Reject. With Request changes selected: the note field "What should change? (the planner reads this)".

**R3-N4 Plan review, phone (new).** Pushed page with no tabs and Back at the top. Title, Why, task rows, Core consequence lines. Fixed bottom bar: Approve plan (48 px) and Request changes. Stop in the lower corner. Plan v1 of 1.

No owner decision is recorded in this section; the 2026-10-21 decisions are in §7. Everything marked design proposal stays open until §5 is answered, except where §7 decides it.

### 7. Owner decisions 2026-10-21, round 3

Recorded from the owner's AskUserQuestion answers, 2026-10-21. The answer column is verbatim. The effect column is this document's reading of it, and §3 and §4 now follow it.

| Question | Owner answer (verbatim) | Effect recorded here |
|---|---|---|
| Q1 phone type scale (§5.1) | "Yes, cut it (Recommended)" | Body 16/24, headline 26/32, minimum 14 px, controls 48 px. Verify on a real phone before build. Work title 20/26 and secondary 14/20 stay as §3 wrote them; the answer did not name them. |
| Q2 review panel translucency (§5.2) | "Tint only if readable (Recommended)" | Translucency only where text keeps 4.5:1 over the worst background behind it. Opaque under reduced transparency. |
| Q3 phone review zoom (§5.3) | "Yes, one bounded step (Recommended)" | One bounded step to the task star, no pan or pinch, immediate under reduced motion (§3, 10). |
| Q6 plan comments reach the planner (§5.6, §8.3) | "Only with request-changes (Recommended)" | Option A: comments reach the planner only inside a request-changes decision, which names the selected comment ids. A comment never reaches the planner on its own. |
| Q4 start work (§5.4) | "Tell first, form second (Recommended)" | Tell is the first start path; the project form is second. Both use existing routes (§4.1). Tell's project-scope check still needed. |
| Q5 plan comments (§5.5) | "Per-task comments now" | Rejects the recommendation "ship existing now". Per-task comments are wanted before the prototype. Contract proposed in §8, not built. |

Sections changed by these decisions, each marked in place: §3 items 10 and 11; §4.1 (start path paragraph); §4.2 (comments sentence); §4.3 (per-task comments row); §5 (status on items 1, 2, 3, 4, 5, and new item 6); §6 (R3-10 opacity note); the closing line of §6.

Still open: none. Q3 and Q6 are answered above.

### 8. Plan comments contract (proposal, not built)

**Status.** PROPOSED. It follows owner decision Q5 (§7). No part of it exists in V1. Each statement carries one label:

- **PINNED**: cited to V1 code, path and line, in this worktree.
- **PROPOSED**: this design's choice; V1 has no such thing.
- **UNKNOWN**: not verified, with the check named.

**Snapshot caveat.** The PINNED citations are from `D:/archeus-t123/archeus/`, branch `v2/living-space` at tip 5db3ac0. That is an older snapshot. V1 at the current tip of `archeus-v1-rearchitecture` (last seen at f483f87 in the session git status) may differ. Check before build against the v1 branch. `D:/Archeus/.collab/p21-design-gate.md` does not exist in `D:/Archeus/.collab/` (glob, no match), so the P21 gate's location is UNKNOWN. Find it on the v1 branch before citing it.

#### 8.1 What V1 has today

- PINNED. A plan version is immutable; a replan or edit is a new row (`archeus/core/domain/entities.py:802-805`). Its identity is `plan_version` and `digest` (`entities.py:819`, `830`).
- PINNED. Task rows are frozen per plan version. Their `key` is unique within that plan (`entities.py:885-898`). Core assigns keys `t1`…`tN` in order on every edit (`archeus/core/application/work.py:271-272`). So a task key means something only inside one version.
- PINNED. `Plan.edited_by` records the principal whose edit made a version (`entities.py:845`). The task spec the API accepts (`PlanTaskSpec`, `archeus/api/schemas.py:722-744`) has no comment or note field.
- PINNED. Approval decisions are `POST /v1/approvals/{id}/decide` with approve scope (`archeus/api/routes.py:1132`). Body: `decision` (approve, reject, request_changes), `action_hash`, optional `note`, `step_up`, `expected_version` (`archeus/api/schemas.py:928-933`).
- PINNED. The plan's action hash covers the plan contents (`archeus/core/application/authorization.py:190-191`). A decision for a plan whose digest changed is refused as superseded (`authorization.py:609-610`). A hash mismatch is refused (`authorization.py:588-592`).
- PINNED. Request changes writes the note into the approval's `decision_note` (`authorization.py:685-687`). It also sends the mission back with the note as its reason (`authorization.py:659-662`, `673-676`; `archeus/core/application/commands.py:497-500`).
- PINNED. The mission event reason becomes the planner's round reason (`archeus/core/planning/worker.py:80-84`). The planner prompt renders it as "This is a new plan: …" (`archeus/core/planning/planner.py:168-169`). The single "What should change?" note is the only path from a person to the planner today.
- PINNED. The UI copy reads "What should change? (the planner reads this)" (`archeus/cli/tui/screens.py:647-651`).
- UNKNOWN. That the live planner actually receives the note on a real round. The code path is PINNED; no run was made. Check with a replan on a test mission.
- PINNED. Plan edit is `POST /v1/plans/{id}/edit` with approve scope (`routes.py:983-984`; `schemas.py:936-939`). `Work.edit_plan` accepts only the plan in force on a mission in APPROVAL_REQUIRED (`work.py:253-257`). It sends the mission back and proposes the next version with `edited_by` set (`work.py:277-283`). Live approvals of the superseded version end with it (`authorization.py:456-458`).
- PINNED. Plan events are `plan.created` and `plan.state_changed` (`archeus/core/domain/events.py:33-34`).
- PINNED. Entities map to tables through one table map (`archeus/infra/db/rows.py`, e.g. `entities.Feedback: 'feedback'` at line 36).
- PINNED. No comment entity appears in `entities.py` (grep for comment, note, reason).
- UNKNOWN. The next migration number. The latest in this snapshot is `0016_idempotency_proofs.sql`; recheck on the v1 branch.

#### 8.2 Data shape of a per-task comment (PROPOSED)

A separate row, not a field on `Task` or `Plan`. Both are immutable per version (`entities.py:803-805`, `895-898`).

| Field | Type | Rule |
|---|---|---|
| `id` | string | New id with its own prefix, like `ids.new_id('approval')` (PINNED pattern, `resources.py:569`) |
| `mission_id` | ref mission | Required |
| `plan_id` | ref plan | The version the comment was written on. Required |
| `plan_version` | int | Copied from the plan, for display ("on v2") |
| `task_key` | string | Must be a key in that plan version's task list, checked at write |
| `task_id` | ref task, nullable | Link to the Task row of that version, for navigation |
| `author_id` | ref principal | Same pattern as `Plan.edited_by` (PINNED `entities.py:810`) |
| `body` | text | Fixed at insert. Length limit UNKNOWN; proposed 2000 characters |
| `state` | open / addressed / withdrawn | Changed only by events. `addressed` when a request-changes decision carries it; `withdrawn` by its author |
| `decision_id` | ref approval, nullable | The request-changes decision that carried it |

Writes follow the decision-row pattern: content frozen at insert, state written once by the transition that moves it (`entities.py:1741-1745` describes this for Approval, PINNED).

#### 8.3 Relation to approval authority and the change note

- **Scope (PROPOSED).** Writing and withdrawing a comment needs approve scope, the scope that already edits plans (`routes.py:983`). Reading needs observe scope. V2 adds no authority (§4.3).
- **Where it is allowed (PROPOSED).** Only on the plan in force, while its mission is APPROVAL_REQUIRED. This mirrors the check in `work.py:253-257`. A comment on a decided, superseded or older version is refused.
- **Not a decision (PROPOSED invariant).** A comment changes no Approval row, no `action_hash`, no `plan_digest` and no plan content. An approval is still given only by an explicit decide call that echoes the displayed `action_hash` (`routes.py:854-861`).
- **The change note stays (PINNED).** "What should change?" remains the single free-text note on request changes. Comments do not replace it.
- **Edit stays the way to change tasks (PROPOSED).** A comment never edits a task. A person who wants a task changed uses Edit plan, which makes the next version (`work.py:237-283`).
- **No carry-forward (PROPOSED).** Comments belong to the version they were written on. A new version does not inherit them, because keys are reassigned (`work.py:271-272`) and tasks can change. The page shows them as "on v{N}" and, after a new version, as "not in v{N+1}" when the key is gone.
- **Supersession (PINNED plus PROPOSED).** When version N is superseded, its approvals end (`authorization.py:456-458`). Its open comments become read-only history.
- **Planner delivery (open, Q6).** Option A, recommended: comments reach the planner only inside a request-changes decision. The decision body names the selected comment ids. The replan prompt renders them under the change note (`planner.py:157-180`, change PROPOSED). Option B: comments stay human-only. Then the UI copy "the planner reads this" must not cover them. Rejected: sending a comment on its own, since that starts a planning round with no decision.
- **No silent approval (PROPOSED invariant).** Approve is never implied by a comment, a request-changes decision, a withdrawal or an edit. Approve needs its own decide call with the displayed hash. Open comments show as a count on the review page before approve. They do not block approve (UNKNOWN whether the owner wants a block; see §8.6).
- **Auto-approval unaffected (PROPOSED).** Auto-approval runs in PLANNING (`archeus/core/domain/guards.py:133-146`). Comments exist only where approval is awaited, so the two cannot meet. A regression test checks this (§8.5).

#### 8.4 Surfaces (names only, PROPOSED)

- Routes, same `Route(...)` shape as `routes.py:983-984`: `POST /v1/plans/{id}/comments` (approve, idempotency key); `GET /v1/plans/{id}/comments` (observe); `POST /v1/plan-comments/{id}/withdraw` (approve).
- Schemas: `PLAN_COMMENT`, `PLAN_COMMENT_WITHDRAW`. `DECIDE` (`schemas.py:928`) gains an optional `comment_ids` list, used only with `request_changes`.
- Events: `plan_comment.created`, `plan_comment.withdrawn`, `plan_comment.addressed`, added to the table at `events.py:33-35`.
- Table and entity: migration `NNNN_plan_comments.sql` (number UNKNOWN); a `PlanComment` entity; one entry in the table map (`rows.py`).
- Planner: a comment block in `planner.prompt` (`planner.py:157-180`), used only when option A is chosen.
- Clients: two helpers beside the plan helpers at `archeus/cli/_api.py:47-51`; one action on the approval screen next to Request changes (`screens.py:646-651`). Web and phone surfaces follow §4.2.

#### 8.5 Mutations and tests (names only, PROPOSED)

Mutations: `Work.add_plan_comment`, `Work.withdraw_plan_comment`, `Work.address_plan_comments` (called inside request changes); `PlanComment` entity and migration; the three routes; `PLAN_COMMENT` and `PLAN_COMMENT_WITHDRAW` schemas; `DECIDE.comment_ids`; three events; the planner comment block; the two CLI helpers; the screen action.

Tests:

- `test_comment_leaves_approval_state_unchanged`
- `test_comment_leaves_action_hash_and_plan_digest_unchanged`
- `test_comment_refused_on_superseded_or_decided_plan`
- `test_comment_task_key_must_exist_in_its_version`
- `test_comments_do_not_carry_to_next_version`
- `test_request_changes_carries_only_selected_comments`
- `test_withdrawn_comment_never_reaches_planner`
- `test_comment_write_needs_approve_scope`
- `test_approve_refused_when_plan_changed_after_review`
- `test_auto_approval_unaffected_by_comments`

#### 8.6 Scope: P21, P22, and a new card candidate

- PINNED. P21 is "observability views": breaker drills, secrets review, trace UI, metrics, plus push transport (`docs/architecture/ARCHEUS_V1_REARCHITECTURE_PLAN.md:433`, `~1218-1224`). Its commits in the session git status are the mission trace view and the route table, which match that.
- PINNED. P22 is legacy capabilities and the migration tooling (`ARCHEUS_V1_REARCHITECTURE_PLAN.md:1226-1232`).
- PINNED. Plan editing belongs to P19 S2 (`routes.py:982`, `schemas.py:935`). Neither P21 nor P22 covers plan comments.
- PROPOSED. A new V1 card candidate: "plan review page and per-task comments". It bundles the §4.2 page with §8, because comments anchor to the page's task list. It should land after P19 S2 and before the prototype the owner asked for. Its place in the phase order is UNKNOWN until the P21 gate is found and checked.
- UNKNOWN. P22's current scope on the v1 branch. Check before placing the card.

#### 8.7 Open items

- UNKNOWN. Whether the live planner reads the change note on a real round (§8.1).
- UNKNOWN. Comment body limit and comments per plan. Proposed 2000 characters; no count cap.
- UNKNOWN. Whether open comments should block approve until addressed. Proposed: no block, a visible count only. The owner decides.
- UNKNOWN. How a comment on a task that version N+1 removes is shown. Proposed: "task not in v{N+1}".
- Question Q6 (§5.6) asks option A or B. Recommended: A.

## Round 4: chat bar, Replay view, and what is real (2026-10-21)

Status: prototype only (`clients/v2-prototype`, fake data, nothing sent to Core). No V1 change. Labels as in round 3: **Owner decision** is only a dated owner answer. Everything below marked PROPOSED is this document's design, not an owner decision.

### 1. Owner decisions, recorded verbatim

| Question | Owner answer (verbatim) | Effect here |
|---|---|---|
| Replay view | "Yes, design now (Recommended)" | Replay is designed and prototyped (§3). Not in V1. |
| Visuals priority | "Adopt, keep V2 visuals priority" | Recorded as given. The question wording was not in this round's brief, so it is UNKNOWN here. |
| Chat role | "Both, chat is a front door (Recommended)" | The chat bar is the way in to start and control. The Start screen is removed. |
| Model account | "Your configured account via official CLI (Recommended)" | Model calls go through the official CLI on the owner's chosen account. |
| Chat authority | "Reads and creates, not effects (Recommended)" | Reads and creates happen directly. Effects are proposed (§2). |

Earlier answers that bind this round (round 3, §7): start path "Tell first, form second (Recommended)"; plan comments "Per-task comments now"; phone review zoom "Yes, one bounded step (Recommended)"; translucency "Tint only if readable (Recommended)".

Owner direction, verbatim (Italian), 2026-10-21:

> "in now voglio la chat bar trasparente per parlare al volo con archeus che mi risponde crea progetti, mission e tutto altro e devo vederle create in tempo reale con animazioni ecc... invece di avere un menu start, e queste cose deve vedere insieme alla vista costellazione e devo vederle rappresentate in tempo reale che vengono create nella costellazione le varie cose"

> "voglio poter controller tutto dal core e chat di archeus, quindi se gli chiedo domande anche per altre cose non riguardante ai progetti deve poter rispondere"

Reading in English (the design's, not the owner's): a transparent chat bar at the bottom of Now, used to talk to Archeus; it creates projects, missions and other things, and the owner sees them appear in the constellation in real time. It replaces a Start menu. Archeus must also answer questions that have nothing to do with projects.

### 2. Rules for the chat bar (PROPOSED)

- **R-C1 Reads and creates are direct.** A project-bound message may create a project, mission, idea or plan. Each new object appears in the constellation as it is recorded, with a short grow-in. Reduced motion shows it at once.
- **R-C2 Effects are proposed, never silent.** Anything that runs work, spends, changes a setting, an account, a hook or a provider becomes a PROPOSED card. Approve is an explicit control. The confirm box's Cancel is the default. A bare chat word is never an approval (V1 already declines a bare `approve`; T-149 §2).
- **R-C3 General thread.** A question outside projects is answered in its own thread style, labelled "General, not project memory". It is never written to project memory. The "Promote to project memory" control is off by default and promotes one answer when turned on.
- **R-C4 Model and tokens.** Replies come from the official CLI on the owner's chosen account. Archeus never reads, stores, copies, injects or relays tokens (AGENT-RULES item 6). **Open conflict:** T-149 G2 shows that `claude_sessions/usage.py` reads the OAuth access token and sends it to the usage endpoint. The rule is therefore not met today. It needs an owner decision (§6) before anyone claims compliance.
- **R-C5 One bar, two surfaces.** On the phone, Tell opens the same bar. There is no separate start form.
- **R-C6 Motion follows fact.** An object animates only once it exists. In V1 that means after its SSE frame and a re-read of the object (T-149 §5). The prototype animates from its own simulated creation, and says so in the bar's tag.

### 3. Replay view (PROPOSED)

A replay is a forensic timeline for one mission inside its project. The project stays the core object; the replay is the mission's record. It answers five questions per event: what the agent **intended**, what was **authorized**, what was **recorded**, what **may have taken effect**, and where state is **uncertain**. A sixth state, **suspended**, marks a workflow stopped for operator reconciliation.

- **RP-1** Each state has a shape and a word. Colour is never the only signal.
- **RP-2** A lost response is UNCERTAIN, not failed. There is no automatic retry. The workflow is SUSPENDED until an operator reconciles it.
- **RP-3 Reconcile** records the operator's observation of what happened on the external side. It does not push, retry or reverse anything.
- **RP-4 Restore** resets only what a checkpoint covers (for example the local branch). It never claims an undo of an external effect.
- **RP-5 Never claim full reversal.** Copy says "a replay never claims that every external effect can be reversed".
- **Sample data.** The 09:00–09:25 example from the strategy report (`docs/architecture/archeus_strategy_report.html`, section 6): task initiated (scope, authority and starting state captured); files changed (artifacts linked); tests passed (validation evidence); external response lost (classed UNCERTAIN, may have taken effect); workflow suspended (no unsafe retry, reconciliation required).
- **Layout.** Timeline on the left (time, marker, title, state chips, notes, linked artifact). Inspector on the right in the 03 mission style: facts, a status line, a legend, Reconcile and Restore. Reached from the mission inspector ("Open replay") and from the rail.

### 4. Real versus faked, reconciled with the T-149 truth check

Source: `D:\Archeus\.collab\T-149-chat-truth-check.md` (read 2026-10-21, code reading only, nothing run). "G" numbers are its gap IDs.

| Item in the prototype | How the prototype shows it | What V1 does today (T-149) | Label |
|---|---|---|---|
| Chat answers | Scripted, keyword-routed, fixed delay | A reply must cite a Core handle; with none it is declined (§2a) | FAKED (G5) |
| Create a project from chat ("Atlas") | Star appears in the constellation | No chat path for projects (§1, Project) | FAKED (G7) |
| Create a mission from chat | Mission appears | `new_work` creates a Mission and a message | REAL in V1. The prototype's creation and animation are simulated |
| Create an idea from chat | Idle figure labelled "Idea" | `idea.created` is real | REAL in V1. Shown here as an idle mission, a simplification |
| Plan v1 with 3 steps | Plan page with per-task comment forms | Plans come only from the planner after a mission starts; no chat command for a plan | FAKED as a chat command. Plan objects are real downstream |
| Run Index notes (card) | PROPOSED card; approve starts it | New work starts without a card under the default profile (G1, P0) | FAKED. The card is the design; V1 does not show it yet |
| Change the daily spend limit (card) | PROPOSED card; approve changes nothing | No chat path for settings; a resource-directive card exists for narrowing (§1) | FAKED |
| General answer | Separate General thread, fixed text | Not possible (G5); no general conversation kind (§3) | FAKED |
| Promote to project memory | Checkbox, page-only | Nothing separates memory; `remember` writes confirmed global memory silently (G4) | FAKED (design rule) |
| Replay: five states, suspended | Sample 09:00–09:25 events | Events exist (`mission.state_changed`, `execution.*`); no side-effect state is recorded | FAKED |
| Reconcile, Restore | Confirm box only | No V1 route | FAKED |
| Owner's configured account for chat | Text only | Not chat-selectable; the router elects the account (G8) | FAKED |
| Token rule | Stated as the design rule | `usage.py` reads and sends the token (G2) | OPEN conflict, rule not met |
| Constellation motion | Local, after simulated events | Only real frames drive motion (T-149 §5) | SIMULATED |

### 5. What the prototype fakes (plain list)

- Every chat reply: scripted by keyword, with a fixed delay. No model is called and nothing is sent to Core.
- Every creation (project, mission, idea, plan) and its animation. They live in the page only; a reload resets them.
- Atlas: fixed id, name and position on the scene.
- Ideas: drawn as idle missions. Plan steps are invented text.
- Approve on a card: changes the page only. Nothing runs, spends, changes a setting or touches an account.
- General answers: two fixed texts. Promote: a checkbox that changes a label.
- Replay: sample data only. Reconcile and Restore: confirm box, then nothing.
- Stop, Tell and plan Approve keep their round 3 fake behaviour.

### 6. Owner questions (recommendations from T-149 §7, plus one from this round)

1. **Missions started from chat:** wait for a start card? Recommend yes (G1, P0). Today they start by themselves under the default profile.
2. **Subscription tokens in `claude_sessions/usage.py`:** stop reading and sending the access token, or accept it as a stated exception? Recommend that status comes from the CLI or shows "unknown". This is security-relevant and the owner decides (G2, P0).
3. **Narrowing from chat** (forbidding an account for one mission): silent or a card? Recommend a card when it blocks work (G3).
4. **`remember`:** confirmed global memory, or a candidate plus one-tap confirm? Recommend a candidate (G4).
5. **General thread:** may it write project memory? Recommend no (§3 of T-149).
6. **Chat model account:** a per-account choice for the chat's own calls, or the router only? Recommend a per-account preference (G8).
7. **New, from this round:** should V1 change to match R-C2 (every run proposed), or should the prototype show today's auto-start? The prototype shows the design rule and labels it. The owner decides which one goes into the V2 spec.
