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
