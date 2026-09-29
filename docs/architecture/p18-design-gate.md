# P18 design gate — spatial visualization

Status: **APPROVED** (A1–A17, the user, 2026-09-29, with the decisions recorded in §4.1).
Implementation follows §21. Anything that departs from an approved decision is recorded in §22
for the user's review, never applied silently.

Sources read, in precedence order: the plan (§23, §24, §31.1 P16–P19, §31.2, §31.3, §32, §33),
this repository at `b5f978f` (P17 pushed, CI run 36601924119 green), the user's P18 brief of
2026-09-29, [p16-design-gate.md](p16-design-gate.md) (whole, esp. §3 S8, §14, §16, §17, §18,
§20, §22, §24, §25, §30), [p17-design-gate.md](p17-design-gate.md) (A1, A2, §5, §19, §20),
[ui-architecture.md](ui-architecture.md) §2, §3, §5, §5.1, §6, §7,
[../design/ARCHEUS_V1_DESIGN_RESEARCH.md](../design/ARCHEUS_V1_DESIGN_RESEARCH.md) §22, §26,
[../design/ARCHEUS_V1_DESIGN_SYSTEM.md](../design/ARCHEUS_V1_DESIGN_SYSTEM.md) (graph view row,
motion, iconography), [decisions/ADR-0016.md](decisions/ADR-0016.md),
[p4-design-gate.md](p4-design-gate.md) (§3 ownership, "defers to P18"),
[p10-design-gate.md](p10-design-gate.md) (RouteDecision), [testing-strategy.md](testing-strategy.md)
§1, §2, and the code named in §1.

---

## 0. What P18 is, and what it is not

The plan's entry (§31.1): **"P18 — Spatial visualization. Depends: P16. New:
`clients/app/src/graph/*`, `/v1/world/graph`. Tests: encoding table ↔ renderer parity test;
keyboard traversal; 1,000-node budget; reduced motion. Acceptance: drill world → project →
mission → execution; list equivalent."** ADR-0016 fixes the form (2D fine-line, every visual
variable a domain fact, list equivalent, 3D after V1); research §26 fixes the encoding; P16 §20
fixes its place in the product (a **mode** of World and of the Relations tab, never a
destination, never the only way to a fact) and hands P18 two carry-forwards: G4 (ADAPT the legacy
renderer's mechanisms into `src/graph/`) and G32 (a focused, scope-checked query over the stored
repository import graph).

P18 builds **a read-only view of relationships Core already records**: one Core query that
assembles a bounded neighbourhood from existing columns and `Relation` rows, one for the stored
import graph, and a Canvas 2D renderer in the SPA that draws them with the P16 visual language.

**P18 owns** the spatial presentation of existing relationships in the SPA and the two read
routes that feed it. **P18 does not own**, and changes nothing in: the relationship model and its
only writer `relate()` (P6), policy and approvals (P9), routing and model × harness × account
selection (P10), execution (P11), sessions (P12), verification and review (P13), events and
automation (P14), identity, pairing, presence and scopes (P15), the SPA's information
architecture and visual system (P16), the TUI (P17), client unification (P19), the execution
trace view (P21), the legacy graph and its import (P22), the security audit (P24), user
documentation and the site (P25).

The P16 rule decides every conflict here: **the graph may only present authoritative rows. It
never decides, never infers a relationship, never writes, and is never a source of truth.**

## 1. What exists [V = verified at b5f978f]

### 1.1 Graph capabilities P18 reuses (P16 §20.1 numbering)

| # | Capability | Location | P18 role |
|---|---|---|---|
| G1 | import-graph builder | `claude_sessions/connections.py:build_hierarchy` | unchanged; its output is already inside G32 |
| G4 | legacy 2D renderer: radial seeding around the parent, cluster zones on a ring, grid-bucketed repulsion + collision, synchronous settle, `lift()` to the nearest visible ancestor, expand/collapse by parent, hover-neighbourhood dimming, search that expands ancestors, 250-node dot LOD | `connections.py:_HTML_TEMPLATE` (lines ~537–600, 739, 769, 820) | **ADAPT**: the mechanisms are ported as pure TypeScript with tests; the code is not copied (it is an inline template string, uses `Math.random`, pulses node radii with `sin(T)`, draws a bokeh background and never stops its rAF loop — all four are rejected, §4 A7/A9) |
| G22–G23 | `Relation` rows (tiered, indexed both ends) and `relate()` | `entities.Relation`, `application/knowledge.py:58` | the only non-column edges the graph draws; `relate()` stays the only writer |
| G24–G31 | supersession, plan DAG and lineage, automation causality, cause chains, session and execution lineage, verification lineage | P6–P14 columns | the column edges of §4 A1's table |
| G32 | stored import-graph payload `{files, edges, truncated, nested, extractor_version}`, content-addressed | `world/inspection.inspect`, `infra/artifacts/store`, `RepositoryInspection.payload_sha256`, `Repository.last_inspection_id` | read by the new repository-graph query (A5); never recomputed on a read |
| — | the list-form edge mapper | `clients/app/src/graph/relations.ts` (8 per-kind functions, `TIER_STYLE`) and its Python twin `archeus/cli/tui/present.py`, held equal by `clients/app/test/fixtures/parity.json` | the definition every graph edge must agree with (A1) |

### 1.2 Infrastructure P18 builds on

- Route table `archeus/api/routes.py` (`Route` namedtuple: method, path, handler, scope, …;
  per-path query allowlist at `:1011`), `schemas.py`, `tools/gen_api_docs.py` →
  `docs/architecture/api-reference.md` + `clients/app/src/api/generated.ts`;
  `tests/v1/judge/client.py` (`OPERATIONS`, `IMPLEMENTED`, both bindings).
- `tests/v1/unit/test_api_structure.py:300` forbids the word `graph` in any route path — the
  guard P16 left for P18 to lift deliberately.
- Auth: token scopes `observe/control/approve/admin`; **no project dimension** (`api/auth.py` has
  no notion of a project). One workspace per home.
- Stream frames carry `type` and `subject {kind, id}` only; `execution.progress` is coalesced to
  at most one per second per execution (`domain/events.py:36`).
- Invalidation: `clients/app/tokens/invalidation.json` → `src/data/rules.ts` and
  `archeus/cli/tui/_tables.py` (`tools/gen_ui.py`, P17 A1).
- Presentation: `presentation.json` maps every state of every machine to a class; the execution
  states in class `active` are INTENT, STARTING, RUNNING, HANDING_OFF (and the task's ROUTING,
  RUNNING).
- Hash router `src/nav/destinations.ts` (`#/world/<project>`, `#/o/<kind>/<id>[/<tab>]`);
  project ids are `prj_…`.
- Motion rules p16 §18.1: P16 has **no** `requestAnimationFrame` anywhere; "P18's renderer will
  own the one loop".
- `src/a11y/announce.ts` (rate-limited live region).
- Entities with tables that can be graph nodes: project, repository, mission, plan, task,
  execution, session, verification, review, approval, route_decision, policy_decision,
  context_package, knowledge_item, meeting, automation, automation_run. **Decision, Person and
  Organization are entity classes without a table** (`entities.py:235, 244, 384`); decisions are
  mirrored as DECISION-type knowledge items. `relate()` already writes `decided_in → meeting`
  and `learned_from → mission`.

### 1.3 Inventory and disposition of the existing graph modules (for P18)

The P16 inventory (§20.1, G1–G35) re-read for what P18 does with each. Terms: **retained** — used
as it is; **adapted** — its mechanism or data carried into P18 code with changes; **replaced** —
a V1 successor takes over its role (the original keeps serving its legacy consumer until its
retirement phase); **deprecated** — kept working, scheduled for removal by a named phase;
**rejected** — not used by V1, with the reason.

| # | Module / capability | P16 disposition | P18 disposition | What P18 does with it |
|---|---|---|---|---|
| G1 | `connections.build_hierarchy` | ADOPT | **retained** | untouched; its output is the stored payload A5 reads |
| G2 | `connections.top_repos` | PRESERVE-BEHIND-UI | **retained** (legacy) | not used by V1 |
| G3 | `connections.build_memory_hierarchy` | PRESERVE-BEHIND-UI | **deprecated** → P22 | untouched; graph.json is imported by P22 |
| G4 | legacy 2D renderer (`_HTML_TEMPLATE`) | ADAPT → P18 | **adapted** (mechanisms) | radial seeding, zones, grid repulsion/collision, synchronous settle, lifting, expand/collapse, neighbourhood dimming, search-expands-ancestors, 250 LOD ported to `src/graph/`; **rejected parts**: `Math.random` phases, `sin(T)` node breathing, bokeh background, the never-parking loop, the position tween into a freshly settled layout on every refresh |
| G5 | legacy `/graph` route | PRESERVE-BEHIND-UI | **deprecated** → P22 | untouched; the V1 graph replaces it for V1 users |
| G6 | `memory.py` graph.json | PRESERVE-BEHIND-UI | **deprecated** → P22 | untouched |
| G7 | `recall.expand_relations` | PRESERVE-BEHIND-UI | **retained** (legacy) | a retrieval algorithm, not a view |
| G8 | BM25 | ADOPT | **retained** | not used by the graph |
| G9 | entity one-hop drill-down pattern | ADAPT → P16 | **retained** (as P16's Relations tab) | the graph's list equivalent and mirror follow it |
| G10 | memory state counts | PRESERVE-BEHIND-UI | **retained** (legacy) | — |
| G11 | graph-lite | PRESERVE-BEHIND-UI | **retained** (legacy TUI) | — |
| G12–G13 | flowgraph + flow page | DEFER → P21 | **retained**, deferred to P21 | not a relationship graph; P21's trace view |
| G14–G15 | live strip, workspace node map | REJECT | **rejected** | metrics-home instruments (P16) |
| G16 | background three.js scene | REJECT (3D lineage deferred) | **rejected** for P18 | 3D after V1 (ADR-0016) |
| G17 | cluster spec + generator | PRESERVE; pattern ADOPTED | **retained** | its one-table pattern is `encoding.ts` |
| G18–G21 | site scene, graph skin, CLAUDE.md import map, GIF tool | PRESERVE / REJECT | unchanged | not V1 app surfaces |
| G22–G23 | `Relation` rows, `relate()` | ADOPT | **retained** | the only non-column edges; `relate()` stays the only writer |
| G24–G31 | supersession, plan DAG/lineage, automation causality, cause chains, session/execution/verification lineage | ADOPT | **retained** | the columns `graph.py`'s `EDGES` reads |
| G32 | stored import-graph payload | PRESERVE → P18 | **adapted** (exposed) | read by `GET /v1/repositories/{id}/graph` (A5) |
| G33–G35 | drift, digest folding, context references | ADOPT | **retained** | not graph edges beyond the §4 A1 table |
| — | `src/graph/relations.ts` (P16) | built by P16 | **retained**, vocabulary extracted to `EDGE_WORDS` | the list mapper; parity reference for `graph.py` until P19 |
| — | `components/Relations.tsx` (P16) | built by P16 | **retained** | the list form; the < 600 px view |
| — | `archeus/cli/tui/present.py` edge functions (P17) | built by P17 | **retained** until P19 | the TUI list; parity reference |

Nothing is **replaced** by P18 in the code sense: the V1 graph supersedes G5's role only for V1
users; the legacy page keeps working until P22 retires it.

## 2. Scope and non-goals

**In scope:** `GET /v1/world/graph`; `GET /v1/repositories/{id}/graph`; the Core query module
behind them; the SPA graph mode on World and on the Relations tab (`src/graph/*`); the accessible
mirror; invalidation rules for the two new read paths; tests, boundary scans, mutation suite
`tools/mutate_p18.py`; as-built docs.

**Non-goals (each recorded, none "for later" without an owner):**

| Not in P18 | Owner / when |
|---|---|
| 3D mode, WebGL | after V1 (plan §31.2, ADR-0016) |
| moving the Relations list and the TUI onto the graph route; removing the client edge mappers | P19 (§4 A1) |
| per-project or per-device authorization of reads | not in V1's auth model; audited by P24 (§4 A15) |
| a server-side path finder, graph search, graph database, similarity or inferred edges | never (§4 A13, P16 §20.7) |
| writes of any kind from the graph (no edge, pin, layout or view state persisted in Core) | never |
| a spatial view in the TUI | not planned; the TUI's Relations list is the list equivalent (P17 §5) |
| the execution trace / flow view (G12–G13) | P21 |
| importing the legacy `graph.json` and retiring `/graph` | P22 |
| lists for meetings / decisions / people (S9) | P22 / later |
| user documentation of the graph | P25 |
| the five known P17 issues | owners in §18.3; none blocks P18 |

## 3. Ownership boundaries and dependencies

| Phase | What P18 reads from it | What P18 never does to it |
|---|---|---|
| P4 | projects, repositories, `last_inspection_id`, `architecture_state`, the stored payload | re-inspect, walk a working tree, recompute an import graph |
| P6 | `Relation` rows, knowledge items, supersession | write, dedupe, infer or re-tier an edge |
| P7–P8 | missions, plans, tasks, `depends_on` | plan, replan, edit |
| P9 | approvals, policy decisions (as nodes, ids and state) | authorize, show a command |
| P10 | route decisions: `harness_id`, `account_id`, `model`, `effort`, `result`, `fallback_from`, the number of eliminated candidates | rank, select, re-run routing, show `explanation`, `requirements`, `candidates` detail or `input_snapshot` (the Why → Route tab already does) |
| P11 | executions, their state and the live class | start, stop, pause (no command in the graph) |
| P12 | sessions and hand-off lineage | create or resume a session |
| P13 | verifications and reviews as rows | infer a verdict |
| P14 | automation runs and their mission edge | fire, simulate |
| P15 | the `observe` scope, the stream | new scopes, project scoping |
| P16 | shell, cache, connection machine, invalidation, presentation and token tables, `relations.ts`, Relations component, motion rules | a new destination, a new visual language, a second cache/invalidation system |
| P17 | the shared generated tables (`gen_ui.py`) | a TUI change beyond regenerating `_tables.py` |

**Where P18 touches a file another phase owns, and why the change is P18's:**
`invalidation.json` (P16/P17): every phase that adds a read path adds its invalidation rule —
the graph routes are P18's reads. `relations.ts` (P16): P18 extracts the edge wording into one
exported table so the graph and the list say the same words (A1); behaviour unchanged, guarded
by the existing relations tests, `parity.json` and `mutate_p16` (anchors move with the text, as
P17 did). `test_api_structure.py` (P3.5–P16): P16 left `graph` forbidden *for P18*; P18 replaces
the blanket ban with an exact allowlist of its two paths (A14).

## 4. Decisions requiring approval

Each: problem · design · alternatives · fit · owner/dependency · test.

### A1 — Graph route ownership (who assembles edges)

**Problem.** Edges are built today in the SPA (`relations.ts`) and in the TUI (`present.py`) from
several reads. The plan requires `/v1/world/graph`, which needs edges assembled in Core. Three
implementations of one edge set is the drift the repository keeps paying for.

**Design.** Core is the **authoritative assembler for the graph routes**:
`archeus/core/application/graph.py` (read-only). It holds one table, `EDGES`, with one row per
edge definition: holder kind, field, referent kind, how the id is read (column, list column,
`Relation` row), inactive rule, containment flag. Each per-kind edge function in `relations.ts`
has an equivalent over that table, and the route emits edges as

```
{id, from:{kind,id}, to:{kind,id}, field, rel, tier, inactive, structural}
```

`from` is always the row that holds the field ("holder → referent"); `id` is
`field|from|to` (stable); `rel` is the `Relation.rel` for relation rows and `null` for columns;
`tier` only on relation rows; `structural` marks the two containment edges that no list
function emits (`tasks.plan_id`, `repositories.project_id`); they carry the hierarchy the G4
mechanisms need (A7). Words are **not** in Core: `relations.ts` exports `EDGE_WORDS[field] = [holderWord,
referentWord]` (its own existing strings, e.g. `'handed off from'` / `'handed off to'`) and its
functions read from it, so the list and the graph show the same words.

**The temporary duplication, stated.** Until P19 there are three edge implementations: Core
`graph.py` (the graph route), `relations.ts` (the SPA Relations list), `present.py` (the TUI).
**Parity is proven** three ways: (1) `graph.py`'s per-kind edges run against every case of the
existing `parity.json` (the same file already holding `relations.ts` and `present.py` equal);
(2) an integration test builds a Core with a fixture mission (plans, tasks, executions, a
hand-off, a verification, knowledge relations, an automation run) and asserts that for every
node the route returns, the edges incident to it equal `present.py`'s edges for that row, read
through the same routes the SPA uses; (3) a TS test asserts `EDGE_WORDS` covers every `field`
Core can emit. **Why it is safe:** all three read the same authoritative columns; none writes;
the fixture file fails the build the moment one differs. **What P19 removes:** the Relations tab
and the TUI read `/v1/world/graph?focus=<object>&depth=1` instead of assembling edges, and
`relations.ts`'s functions and `present.py`'s edge functions are deleted (their cases move to the
route's tests). Recorded as deviation V2 and as a P19 carry-forward in the plan.

**Alternatives.** (b) The client assembles the graph by fanning out existing reads — no route;
contradicts the plan, costs N reads per hop, cannot bound or truncate server-side. (c) Move the
Relations list onto the route now — P19's scope (user's instruction). (d) Core emits the words —
puts English copy (presentation) in the API.

**Fit.** The route is a query over rows like `/v1/attention` or the timeline (P16 D3/D5); edge
definitions stay one table in Core, which is where P19 wants them.

**Owner.** P18 (route), P19 (consolidation). **Tests.** parity (1)–(3); M01, M02, M22.

### A2 — Node kinds

**Problem.** The graph must show only what exists; research §26 names kinds (person, decision)
that have no table.

**Design.** A node is a row of a table: `project, repository, mission, plan, task, execution,
session, verification, review, approval, route_decision, policy_decision, context_package,
knowledge_item, meeting, automation, automation_run`, plus `workspace` as the world-level focus.
A node is

```
{kind, id, label, machine?, state?, parent?:{kind,id}, project_id?, counts?, attrs?}
```

`label` ≤ 120 characters (§A6); `machine`/`state` only where the kind has a machine; `parent` is
the containment field (§A7 hierarchy: repository/mission/session/knowledge_item/meeting →
project; plan → mission; task → plan; execution → task; verification → plan; review, approval →
mission; route_decision → task, else mission; others → none); `attrs` only for route decisions
(`harness_id, account_id, model, effort, result, fallback_from, eliminated` — the last a count).
A reference to a kind with no table (decision, person, organization) or to a row that does not
exist is an **endpoint**, not a node: `{kind, id, endpoint: true, label: "<kind> <short id>"}`,
drawn with its own glyph, never inspectable, never given state. Credentials, devices, principals,
users, tokens, events, accounts and usage are never nodes (accounts appear only as an attribute
of a route decision — P16 §20.2 "attributes, not nodes").

**Alternatives.** Nodes for accounts/harnesses (P16 decided attributes); synthesising person
nodes from meeting attendees (inventing entities).

**Fit.** P16 §20.2's mapping, table by table. **Owner.** P18. **Tests.** unit: kind allowlist,
endpoint for a dangling or tableless reference; M10, M11.

### A3 — Shape mapping (the encoding table)

**Problem.** ADR-0016 / research §26 say ring = **person**; P16 §20.10 says ring = **session**;
V1 has no person table. The encoding must be one table the renderer is tested against.

**Design.** `src/graph/encoding.ts`, one `ENCODING` table, the only place the renderer reads a
visual variable from:

| Domain fact | Visual (only this) |
|---|---|
| project | cluster hull + label; at world level a large hollow circle with its counts |
| mission | filled circle, state colour |
| task | small filled circle, state colour |
| execution | small triangle, state colour; live → energy (A8) |
| plan (version) | short bar; inactive versions at `text-3` |
| repository | square |
| session | **ring** (P16 §20.10; deviation V1 against research §26/ADR-0016 "person") |
| knowledge item | small dot; type DECISION → **diamond** (the decision's record; no Decision table) |
| verification | hexagon outline, neutral |
| review | filled hexagon, neutral |
| approval | outline diamond, neutral |
| policy decision | outline square with a notch, neutral |
| route decision | chevron, neutral; its A2 attrs in the label on focus |
| context package | bracket pair, neutral |
| meeting | rounded rectangle, neutral |
| automation | circle with a centre dot, neutral |
| automation run | small circle with a tick, neutral |
| endpoint (no table / missing row) | hollow dotted circle, label only |
| edge | 1 px line; EXTRACTED solid, INFERRED dashed, AMBIGUOUS dotted (`TIER_STYLE`); column edges solid; inactive at `text-3`; lifted edges width `1 + log2(count)` capped at 3 px |
| distance | graph proximity to the focus (layout, A7) |
| energy | a live execution (A8); nothing else animates |

Colours come from the token table and presentation classes (no new colour). Every shape is also
named in the mirror (A11), so shape never carries meaning alone.

**Alternatives.** Keep "ring = person" (no such node can exist in V1); invent a person node from
meeting attendees (rejected, A2).

**Fit.** P16 is the later, implementation-level authority; the ADR's intent ("node shape = kind")
is kept. **Owner.** P18; P25 updates the published design docs. **Tests.** encoding ↔ renderer
parity (a recording 2D context asserts each kind draws its shape and each tier its dash array);
M04.

### A4 — World and focus semantics

**Problem.** "cluster = project" suggests drawing every project's contents; P16 says start
focused and never load the world.

**Design.** The graph **always has a focus**. The world level is the focus
`workspace:<the workspace>`: its nodes are the projects only, each **collapsed** with `counts`
(missions by presentation class, repositories, sessions, knowledge items) computed by `COUNT …
GROUP BY` — no child row is returned. Focusing (or expanding) a project is a new query focused
on that project, `depth 1`: its repositories, missions, project-level sessions, knowledge items
and meetings, capped and ordered (A6). Focusing a mission (`depth 2`) returns its plans, tasks,
executions, sessions, approvals, verifications, reviews, route decisions and relations. That is
the plan's drill: world → project → mission → execution, each step a URL:

- `#/world/graph` — world level;
- `#/world/graph/<kind>/<id>` — focused (from World's toggle or from an object's Relations tab);
- `#/world/graph/repository/<id>/modules[/<path>]` — the import graph (A5);
- Enter on a node → `#/o/<kind>/<id>` (the canonical inspector, over the graph, P16 D7);
  Back returns to the graph URL.

`graph` can never be a project id (`prj_…`), and the parser test asserts the three graph forms
and that `#/world/<prj_id>` is unchanged.

**Alternatives.** Load every project's missions at world level (the whole-database dump P16
forbids); a separate `#/graph` destination (P16: a mode, not a destination).

**Fit.** ADR-0016's cluster = project holds at every level (a project is drawn as its cluster);
P16 §20.15 holds (never load the world). **Owner.** P18. **Tests.** A18-01..03 (§16); M06, M07.

### A5 — Repository import graph (G32)

**Problem.** P16 promised a focused, scope-checked query over the stored import graph; there must
be no second import-graph representation.

**Design.** `GET /v1/repositories/{id}/graph?focus=<path>&depth=<1|2>&limit=<n>` (observe).
Source: the payload of `Repository.last_inspection_id` (a COMPLETED inspection), read with
`artifacts.get(payload_sha256)`; parsed payloads are cached in-process by sha (content-addressed,
immutable; `functools.lru_cache(maxsize=4)`). Nodes: the directory tree implied by the payload's
`files` paths below `focus` (empty = the repository root), `depth` levels down, each directory
with `counts {files, dirs}` when collapsed; a file is a node. Edges: the payload's file→file
import edges **aggregated** to the returned nodes (`count` = number of file edges), with an edge
whose other end lies outside the focus subtree ending at that end's top-level directory (an
endpoint labelled with the path). Directory containment is structural (a path prefix), not an
inferred relation. Response carries `revision`, `inspected_at`, `extractor_version`,
`extractor_truncated` (the payload's own `truncated`), `stale` (`architecture_state == STALE`
or `last_revision != inspection.revision`) and `available`.

- **No completed inspection:** `200 {available: false, reason: "not_inspected"}` — nothing is
  scheduled by a read.
- **Payload missing from the artifact store:** `200 {available: false, reason:
  "payload_missing"}`; logged once per sha.
- **Stale:** served with `stale: true`; the view says "from revision <r>, inspected <ago>".
- **Unknown repository:** 404. **Unknown `focus` path:** 404 `not_found` (field `focus`).
- Deterministic order: directories before files, then path (byte order).
- Caps: `limit` ≤ 1,000 nodes (default 500), ≤ 4,000 aggregated edges; `truncated` +
  per-directory hidden counts.

The client renders it with the same renderer and G4 mechanisms (lifting, expand/collapse,
search-expands-ancestors are exactly what the legacy page did for this data).

**Alternatives.** (b) Defer again — rejected: P16 committed it and the data and extractor
already exist. (c) Recompute from the working tree on request — a second representation and a
filesystem walk on a read (rejected). (d) A node per module package — the payload has files, not
packages; inventing a package level would be inference.

**Fit.** Reads P4's record exactly as drift does. **Owner.** P18; P4 unchanged. **Tests.**
unit over payload fixtures (focus, depth, aggregation counts, outside endpoints, stale, missing,
ordering, cap); M21, M29; A18-23, A18-24.

### A6 — Query contract of `GET /v1/world/graph`

| Parameter | Meaning |
|---|---|
| `focus` | `<kind>:<id>`; omitted = `workspace:<the workspace>` |
| `depth` | 1 or 2; default 1 for `workspace` and `project`, 2 otherwise; anything else 400 |
| `limit` | node cap, 1..1,000, default 500; anything else 400 |

Semantics:
- Breadth-first from the focus over the `EDGES` table in both directions (holder → referent by
  the row's own column; referent ← holders by the indexed reverse column), one batched `IN (…)`
  query per edge definition per hop, inside **one** `db.read()` (one snapshot; `as_of_seq` in
  the body and `X-Archeus-Seq`).
- **Ordering** (the cap is applied in this order, so a nearer node is never dropped for a
  farther one): hop distance; then kind rank (mission, execution, task, plan, session,
  verification, review, approval, route_decision, repository, knowledge_item, meeting,
  automation_run, automation, policy_decision, context_package); then presentation-class rank
  (needs you, active, blocked, …, done, inactive); then `updated_at` descending where the table
  has it; then `id` (a ULID, so creation order breaks every remaining tie).
  Edges are sorted by `id`. The same database gives the same bytes.
- **Truncation:** `truncated: true` and `hidden: [{parent:{kind,id}, kind, count}]` for every
  parent whose children were cut; the client draws one "+N" stub per (parent, kind) that
  re-focuses on the parent when opened.
- Response: `{focus, depth, limit, as_of_seq, nodes, edges, truncated, hidden}` (schema
  `WorldGraph`).
- **Errors:** unknown kind or a kind that is never a node → 400 `invalid` (field `focus`);
  malformed id → 400; well-formed id with no row → 404 `not_found`; no `observe` → 401/403 as
  every route.
- **Out-of-scope focus.** There is no project dimension to be out of: a focus is in scope when
  its kind is a node kind (A2) and its row exists in this home's one workspace. A credential,
  device, principal, token or event id as focus is 400; a row of another workspace (none exist
  in V1) is 404, never revealed. See A15.
- **Labels:** the row's title/name/statement (never a body), `core/redact.py` applied, control
  characters stripped, truncated to 120 characters with `…`.
- **Never serialised** (field allowlist per kind, not a denylist): bodies, knowledge `body`,
  message text, plan task text, output tails, checkpoints, `explanation`, `requirements`,
  `candidates` detail, `input_snapshot`, `outcome`, any usage figure, any token, any path outside
  a repository's own `path`.
- **Read-only:** the handler opens `db.read()` only and appends nothing.

**Alternatives.** `focus_kind` + `focus_id` as two parameters (equivalent; one parameter keeps
the URL and the cache key one string); unbounded depth (rejected); server-side pagination of a
neighbourhood (a cap with stubs is the P16 progressive-disclosure model).

**Fit.** Same shape and bounds discipline as `/v1/attention` and the timeline. **Owner.** P18.
**Tests.** unit (ordering, cap, hidden, depth, focus, errors, allowlist, redaction); integration
(HTTP, scopes, read-only); M06–M12, M27, M31.

### A7 — Layout

**Problem.** A refresh must not make the graph jump; the legacy layout seeded with
`Math.random` and never stopped.

**Design.** `src/graph/layout.ts`, pure, **main thread**:
- deterministic: a seeded PRNG (mulberry32) whose seed is a hash of the focus key; no
  `Math.random`, no clock (static test);
- the G4 mechanisms: children seeded radially around their parent in id order; project zones on
  a ring sized by population; grid-bucketed repulsion (O(n) per iteration) + collision; a fixed
  iteration count, run **synchronously once per focus**, then static;
- **stable positions**: a per-focus position cache (in memory, per tab) keyed by node id; on an
  ordinary refresh existing nodes keep their positions and are fixed during a local settle of
  only the new nodes; removed nodes are dropped; nothing animates into place;
- **focus change** → a new layout for the new focus key (the old focus's cache is kept, so Back
  returns to the same picture); the camera moves with one transform tween ≤ 240 ms (none under
  reduced motion);
- **expand/collapse** → new children seeded around the parent and settled with everything else
  fixed; they appear with one opacity step (none under reduced motion);
- **truncated** → "+N" stubs are laid out like children.

Main thread, not a Worker: the budget (A10) is met by the O(n) grid; a Worker would add a CSP
`worker-src` change and a message protocol for no measured need. If the CI proxy ever exceeds
the budget the build fails; it does not silently move to a Worker.

**Alternatives.** A continuous force simulation (legacy; perpetual motion — rejected by P16
§20.12); d3-force (a dependency — rejected, A10); a Worker (above).

**Owner.** P18. **Tests.** same input twice → identical coordinates; a refresh adding one node
moves no existing node; layout time proxy (A10); static bans; M13, M28.

### A8 — Live execution and energy; invalidation

**Problem.** Energy must come from backend state, not invented animation state, and the graph
must refresh through the existing invalidation system.

**Design.**
- An execution node is **live** when its presentation class is `active` (from its `state` in the
  read). Live edges are the execution's `executions.task_id` edge (or the edge it is lifted into).
- A **pulse**: when a stream frame of type `execution.*` arrives whose subject is a loaded live
  execution, that edge gets **one** 240 ms opacity step, at most once per 2 s per edge (P16
  §18.1 rule 4). Nothing else pulses; a node never animates for existing.
- **Reduced motion** (OS or setting): no pulse, no tween, no fade; live edges are drawn 2 px,
  static.
- **Invalidation** (`invalidation.json`, regenerated for the SPA and the TUI by `gen_ui.py`):
  `/v1/world/graph**` is added to the rules of `project, repository, mission, plan, task,
  execution, session, verification, review, approval, route_decision, policy_decision,
  context_package, knowledge_item, relation, meeting, automation, automation_run`; the import
  graph is already covered by `repository → /v1/repositories/{id}/**` and
  `repository_inspection → /v1/repositories/**` (asserted, not re-added). The TUI never reads
  these paths, so the rules are inert there. No second invalidation system and no frame payload
  is read as state (P14).

A live execution's coalesced progress (≤ 1 frame/s) therefore re-reads the focused graph at most
once a second through the cache's existing 50 ms batching; an identical response changes no
position and redraws only the pulse. The server cost of that read is a CI proxy (A10).

**Alternatives.** Animate from the frame payload (rejected, P14/M08 of P17); a type-level
invalidation filter (a schema change to `invalidation.json` for both clients — not needed at
this cost; recorded as a limitation).

**Owner.** P18 (rules for its reads); P16/P17 own the table format (unchanged). **Tests.** TS:
pulse only on `active`, never on ENDED; no pulse under reduced motion; invalidation cases for the
new rules; `gen_ui.py --check`; M18, M30, M32.

### A9 — The animation loop

**Problem.** P16 has no rAF; P18 owns the only one and it must park.

**Design.** `src/graph/loop.ts` is the **only** `requestAnimationFrame` caller in
`clients/app/src` (static test). It holds a set of finite animations (camera tween, fades,
pulses); a draw request schedules **one** frame; the chain reschedules only while an animation is
unfinished. It parks — schedules nothing, and cancels a pending frame — when the document is
hidden (`visibilitychange`), the window is blurred (`blur`), reduced motion is on (no animation
is ever enqueued; state changes draw once), the canvas context is lost (`contextlost`; redraw
once on `contextrestored`), or no animation exists. The legacy renderer's ambient node pulsing,
bokeh background and never-ending loop are rejected (G4 note, §1.1).

**Alternatives.** A per-component loop (two loops the moment two graphs mount); CSS animation on
DOM nodes (a 1,000-node DOM is the cost Canvas avoids).

**Fit.** The repository's one-loop-that-parks rule (CLAUDE.md "Motion is transitional") and
Ship Notes R7's loop lifecycle (ADOPT, p16 §22 — the recorded evaluation; no source fetched).
**Owner.** P18. **Tests.** TS with a fake window and a fake rAF: parks on each of the five
conditions, resumes on focus/visible, zero frames after settle; static single-caller test;
e2e: `document.hidden` emulation and a dispatched `contextlost` leave no pending frame; M17–M19.

### A10 — LOD and performance

**Problem.** P16's budget: 1,000 nodes at 60 fps on integrated graphics, dots above 250 visible
nodes, clusters collapse beyond the budget, layout once per focus. Headless CI cannot measure a
real GPU (CLAUDE.md: under SwiftShader a frame-time number measures the rasteriser).

**Design.**
- **LOD:** ≤ 250 visible nodes: shapes + labels for the focus, its neighbours and the hovered or
  keyboard-selected node; > 250: every node a 2 px dot, batched into one path per colour, labels
  only for the focus and the selection; zoom < 0.5: cluster labels only. The client never holds
  more than 1,000 visible nodes: an expand that would exceed it collapses the farthest expanded
  cluster first and says so.
- **Frame-time degrade** (R7 ADAPT, p16 §22): three consecutive frames over 20 ms during an
  animation drop pulses and non-focus labels until the animation ends.
- **Plain Canvas 2D, no dependency** (no d3, no graph library) — the architecture satisfies the
  requirement with the ported mechanisms; any dependency would need the user's approval.
- **CI proxies (deterministic, gated):** (1) layout of the 1,000-node fixture completes within a
  fixed iteration count and under a wall-time ceiling calibrated on the CI runner with a 3×
  margin (a regression gate, not a GPU claim); (2) draw work per frame counted on a recording
  context: > 250 visible nodes → path count O(colours), not O(nodes); (3) visible nodes after
  LOD and the 1,000 client cap; (4) the server builds a 1,000-node, depth-2 response within a
  ceiling measured the same way; (5) rendering never allocates per frame proportional to nodes
  during a pulse (only the pulsed edge is redrawn over the static layer).
- **Manual evidence (required before as-built, not claimable from CI):** 60 fps during a
  focus-change tween and a pulse over the 1,000-node fixture on representative integrated
  graphics (Intel UHD class) in Chrome/Edge, frame deltas recorded from DevTools, with the
  machine named.

**Alternatives.** WebGL (ADR-0016: later); a graph library (a runtime dependency for mechanisms
the repo already designed); claiming 60 fps from headless Chromium (would be misleading).

**Owner.** P18; manual evidence by the user. **Tests.** proxies (1)–(5); M20.

### A11 — Accessibility

**Problem.** A canvas is invisible to assistive technology; P16 promised `role=application` with
an off-screen list mirror.

**Design.**
- The canvas is `role="application"` with an `aria-label` naming the focus and an
  `aria-describedby` pointing at the key help; **one tab stop**.
- **Mirror:** a visually hidden region after the canvas, built from **the same loaded graph
  object** the canvas draws (no second read): the focus first, then one group per relationship
  (`EDGE_WORDS`), each neighbour a link to `#/o/<kind>/<id>` with its kind, state label and
  endpoint mark; "+N more" stubs are listed with their counts. A test asserts mirror ids ==
  loaded node ids.
- **Keyboard** (keyboard equals pointer, P16 §20.11): ↑/↓ select the previous/next edge of the
  focused node in edge order (the edge is highlighted and announced); → moves the focus across
  the selected edge; ← steps back along the traversal; Enter opens the focused node's inspector;
  Space expands/collapses; `+`/`-` zoom; `0` fits; `/` opens the search field; Esc clears search,
  then selection; Home returns to the query focus.
- **Announcements** through `a11y/announce.ts` (its rate limit): "Mission ‹title›, executing,
  6 relationships", "decided in → meeting ‹name›, 2 of 5".
- **Focus order:** toolbar (list/graph toggle, search, relationship chips) → canvas → the page;
  opening an inspector moves focus to its heading; closing it returns focus to the canvas with
  the same node selected.
- **Screen readers** get the mirror and the visible Relations list toggle; the canvas is not
  the only representation of anything.
- **Reduced motion:** as A8/A9.

**Alternatives.** A DOM/SVG node per graph node (accessible by construction but 1,000 DOM nodes
per frame); no mirror, Relations list only (P16 promised both).

**Owner.** P18. **Tests.** TS: mirror equality, keyboard reducer visits every edge in order;
e2e: keyboard journey, axe-core on the graph view; M14, M15.

### A12 — Mobile and responsive

**Design.** Below 600 px of viewport width the graph toggle is not rendered; a graph URL opened
there shows the focused object's Relations list (the list equivalent) with one line saying the
spatial view needs a wider window. The decision reads `matchMedia('(min-width: 600px)')` — a
chrome rule about the window, not a component rule (P16's `@container` rule does not apply).
Touch at ≥ 600 px: tap selects, double-tap opens the inspector, pinch zooms; targets never under
44 px for the toolbar.

**Alternatives.** A shrunken desktop graph (P16 §20.14 forbids). **Owner.** P18. **Tests.** e2e
at 390 px: no canvas, list present; M33.

### A13 — Search, pin, path, filters

**Design.**
- **Search** (`/`): matches labels of **loaded** nodes only, including children loaded but
  collapsed; a match expands its ancestors (G4) and centres it. It never calls Core; global
  search stays the command bar.
- **Pin:** client view state only (in memory, per tab, never persisted, never in Core, not in
  the URL); a pinned node stays fixed in layout and is never auto-collapsed.
- **Path:** select two loaded nodes (`p` on each) → breadth-first over loaded edges only →
  highlight; otherwise "no path within the loaded neighbourhood". No server path, no inferred
  edge, no load triggered.
- **Filters:** chips by relationship field or `rel`, client-side over loaded edges (P16 §20.6).

**Alternatives.** Server search / path endpoints (a hidden traversal engine — rejected).
**Owner.** P18. **Tests.** TS model: search expands ancestors, path over loaded edges only,
filters hide only edges; static: the graph module calls no route but the two reads; M16.

### A14 — API and client generation

**Design.** Two rows in `routes.py` (GET, `observe`, not idempotent-keyed) with schemas
`WorldGraph` and `RepositoryGraph`, their query parameters added to the allowlist; regenerate
`api-reference.md` and `generated.ts` with `gen_api_docs.py`; `tests/v1/judge/client.py` gains
`world_graph` and `repository_graph` in `OPERATIONS` and `IMPLEMENTED` on both bindings.
`test_api_structure.py`: `'graph'` leaves the forbidden-word tuple and is replaced by an exact
assertion — the paths containing `graph` are exactly the two above, both `GET`, both `observe` —
plus a `P18` route pin. No other structure assertion changes. **CLI: unchanged** (no requirement
found). **TUI: unchanged** except the regenerated `_tables.py`.

**Alternatives.** Lift the ban wholesale (weakens the guard); a CLI `graph` verb (no requirement).
**Owner.** P18. **Tests.** structure test, `gen_api_docs.py --check`, `gen_ui.py --check`,
`test_core_client.py`; A18-32.

### A15 — Scope and security boundary

**Current semantics, stated plainly.** A token carries scopes, not projects. `observe` reads the
whole workspace through every existing list route; the graph routes are `observe` and therefore
**expose nothing an `observe` token cannot already list**, in a different shape.

**Protected:** no read without a valid token and `observe`; no write reachable (GET, `db.read()`,
no event); a bounded cost per request (depth ≤ 2, ≤ 1,000 nodes, ≤ 4,000 edges, batched queries);
credentials, devices, principals, tokens, events, usage and accounts never become nodes; bodies,
output tails, reasoning-adjacent fields never serialised (allowlist); every label redacted and
cleaned; the repository route reads only the stored artifact of a registered repository — never
a filesystem path from the request (`focus` is matched against the payload's `files`, so it
cannot traverse).

**Not protected (and not claimed):** per-project isolation between two users or two paired
devices (V1 has one user and no project scopes); hiding one project from a paired observe
device. **P24 must audit** graph/API data leakage (its own list names it), aggregation effects
(does a neighbourhood reveal more than the lists do together), and the reverse-lookup cost bounds.

**Owner.** P15 (scopes), P18 (the routes), P24 (audit). **Tests.** integration: 401/403,
read-only (event seq and every table's row count unchanged across 20 reads), focus kinds refused;
unit: allowlist, redaction, traversal-proof `focus`; M10, M11, M23, M31.

### A16 — Mutation strategy

**Design.** `tools/mutate_p18.py` on the P16/P17 runner pattern (exact, unique snippets; every
guarding test green before; files restored whatever happens; SPA mutants rebuilt where the test
needs the build). Each mutant names the **direct** test that owns its invariant (§15); a mutant
killed only by an unrelated safeguard is a failure of the suite and gets a direct test. P8–P17
suites are re-run after implementation.

**Owner.** P18. **Tests.** the suite itself; the kill table in the as-built section.

### A17 — Acceptance evidence

**Design.** P18 is complete only with every item of §20: the acceptance scenarios A18-01..32
(§16) passing, the mutation suite fully killed, the full suite and the P8–P17 mutation suites
green, the manual 60 fps and Windows-console items recorded, CI green on every job after the
user approves the push, and the as-built section written with every deviation. **Owner.** P18;
manual items by the user.

### 4.1 Approval (2026-09-29) — the decisions that bind implementation

A1–A17 approved as written. The user's decisions, binding:

1. **A1–A17** approved.
2. **`EDGE_WORDS`**: the shared edge vocabulary moves into `relations.ts`; P16 behaviour and
   unrelated P16 code do not change.
3. **V6** approved: `GET /v1/repositories/{id}/graph` is implemented in P18; the import graph is
   not deferred again.
4. **A15** approved: an `observe` credential may read every project's graph under V1's
   one-workspace model. **P24 must audit this explicitly** for information leakage and
   project-isolation implications.
5. **A8** approved: live execution state may refresh the focused graph up to once a second,
   within the existing invalidation, animation and performance rules. It is **not** a general
   polling architecture: no timer re-reads anything.
6. **A10**: the 60 fps figure is manual evidence, never an artificial CI GPU gate. The user also
   performs the Windows Terminal/conhost check carried from P17.
7. **A3**: the glyph set as specified, consistent with the design system; no decorative shape.

P16 requirements restated as binding on the implementation: existing graph work is used where
appropriate rather than replaced; the implementation carries an inventory and disposition of the
existing graph modules (§1.3) distinguishing **retained, adapted, replaced, deprecated,
rejected**; the graph never becomes a second domain, policy, routing or execution system;
backend data is the source of truth; no reasoning, hidden model reasoning, credential or other
prohibited field is exposed; below 600 px the Relations list is the view; no graph library unless
a later measured requirement proves Canvas insufficient (and the user approves it).

## 5. State model

No domain state, machine, table or event type is added.

Client view state (in memory only):

| State | Meaning |
|---|---|
| `loading` | the focus's read is in flight (the previous picture stays, marked) |
| `current` / `stale` / `reconnecting` / `unavailable` | the P16 connection machine's freshness for the graph key, shown the same way as every view |
| `not_found` | 404 for the focus; the view offers World |
| `no_payload` | import graph `available: false` with Core's reason |
| loop `parked` ↔ `running` | A9 |

View-only state: expanded set, pinned set, selection, traversal stack, search query, chips,
position caches per focus key. None is persisted or sent to Core.

## 6. Data model and storage impact

None. No migration, no column, no index. Reverse lookups go only along columns that are already
indexed, verified at `b5f978f` (an explicit index or the implicit index of a `UNIQUE`
constraint): `missions (workspace_id, project_id, state)`, `repositories.project_id`,
`knowledge_items (project_id, …)`, `plans (mission_id, plan_version)`, `tasks (plan_id, key)`,
`executions (task_id, attempt)`, `sessions.mission_id`, `sessions.project_id`,
`sessions (handoff_from_session_id, …)`, `verifications.plan_id`, `reviews.plan_id`,
`approvals (mission_id, state)`, `policy_decisions (mission_id, stage)`,
`route_decisions.task_id`, `automation_runs.mission_id`, `relations_from`, `relations_to`. Two
columns the list mapper reads are **not** indexed — `executions.mission_id` and
`verifications.execution_id` — so the query reaches those rows through the indexed path instead
(a mission's executions via its tasks; an execution's verifications via its plan, filtered), and
never scans. If implementation finds another unindexed reverse column it is recorded in §22 and
brought to the user (an index is a migration), not scanned. The in-process payload cache holds at
most four parsed payloads.

## 7. API, CLI, UI and TUI impact

- **API:** + `GET /v1/world/graph`, + `GET /v1/repositories/{id}/graph` (A6, A5). Nothing else.
- **CLI:** none. **TUI:** none beyond regenerated tables.
- **SPA:** `src/graph/{relations.ts (EDGE_WORDS extracted), encoding.ts, model.ts (visibility,
  lifting, expand/collapse, search, path, dimming — pure), layout.ts, render.ts, loop.ts,
  mirror.tsx, GraphView.tsx}`; a toggle on World and on the Relations tab; routes of A4. No new
  destination, no new token, no new colour.
- **Build:** no new runtime or dev dependency.

## 8. Failure modes

| Failure | Behaviour |
|---|---|
| Core down / reconnecting | the last picture stays with the P16 stale mark; commands are not offered in the graph anyway |
| focus row absent | 404 → "This object is not in the graph"; link to World |
| import payload absent or not inspected | `available: false` with Core's reason; nothing is scheduled |
| payload stale | drawn with the stale line (A5) |
| huge neighbourhood | cap + "+N" stubs; client cap 1,000 visible |
| relation to a tableless kind or a missing row | endpoint glyph |
| canvas unavailable / context lost | the Relations list is shown; the loop parks; redraw on restore |
| layout over budget on a slow machine | layout is a fixed iteration count, so it ends; frame-time degrade drops pulses |
| an edge definition references an unknown field | build fails (`EDGE_WORDS` coverage test) |

## 9. Concurrency and races

- One `db.read()` per response: the nodes and edges are one snapshot (`as_of_seq`). The payload
  read happens after the snapshot but is content-addressed and immutable.
- Rapid focus changes: responses are cached by path, so a late answer for an old focus lands in
  its own key and never overwrites the current view (P16's cache rule).
- Refresh during a tween: positions are merged by id (A7); the running tween's target is kept.
- Resync after a `410`: every key is invalidated (P16), the graph re-reads once.
- The writer is never contended: reads do not take the write lock.

## 10. Security considerations

A15 is the boundary. Additionally: the SPA's graph code performs no `POST` (static test); labels
are drawn with `fillText` (no HTML), and in the mirror they are React text (never
`dangerouslySetInnerHTML`); the canvas never loads an external resource; no new CSP directive.

## 11. Compatibility, migration, upgrade, rollback

- Existing routes, schemas, responses, the Relations list and the TUI are unchanged in behaviour.
- `EDGE_WORDS` extraction is behaviour-preserving (P16 relations tests and `parity.json`).
- **Migration/upgrade:** none. **Rollback:** revert the P18 commits; there is no data to undo,
  no schema, and no persisted view state. The legacy `/graph` page is untouched until P22.

## 12. Observability and audit

Reads are not audited as events, like every other `GET`. Core's existing request log (method,
route template, status, duration — `api/server.py`) covers the two routes. Responses carry `as_of_seq`, `truncated`, `hidden`; the view exposes
`data-graph-focus`, `data-graph-nodes`, `data-graph-lod`, `data-graph-loop` (running/parked)
for tests and for a user reporting a problem. No telemetry.

## 13. Testing strategy

| Layer | File (new unless noted) | What |
|---|---|---|
| unit (Python) | `tests/v1/unit/test_graph_query.py` | `EDGES` over every `parity.json` case; BFS depth/cap/ordering/hidden; workspace counts without children; endpoints; kind allowlist; field allowlist per kind; redaction and label cap; route decision attrs only; import graph over payload fixtures (focus, depth, aggregation, outside endpoints, stale, not inspected, missing payload, ordering, cap, traversal-proof focus) |
| integration (HTTP) | `tests/v1/integration/test_graph_routes.py` | TempCore: scopes, 400/404, `X-Archeus-Seq`, read-only (seq and row counts unchanged), route ↔ `present.py` parity over a fixture mission (A1 (2)), the 1,000-node server proxy |
| TS unit | `clients/app/test/graph-*.test.ts` | encoding ↔ renderer (recording context); model: lifting, expand/collapse, dimming sets, search-expands-ancestors, path over loaded edges only, filters; layout determinism, stability, budget proxy; LOD and draw-work proxy; loop parking (five conditions) and single caller; energy rules; mirror equality; keyboard reducer; routes of A4; `EDGE_WORDS` coverage; invalidation cases for the new rules |
| e2e | `tests/v1/e2e/test_spa_p18.py` (Playwright) | the drill world → project → mission → execution; Enter → inspector URL and back; zoom, fit, search via keys; reduced-motion emulation; hidden page and dispatched `contextlost` park the loop; 390 px list fallback; axe-core on the graph view; overflow audit at 768/1280/1920 |
| design | `tests/v1/design/test_design_gates.py` (existing) | the single `requestAnimationFrame` caller; no `Math.random`/`Date.now` in `layout.ts`; no keyframe outside transform/opacity |
| boundaries | `tests/v1/unit/test_graph_boundaries.py` | `graph.py` imports only domain/infra read helpers (no `cli`, no `connections`, no `inspection.inspect`, no writer); no `tx`/insert/append in it; the SPA graph code references only the two graph reads |
| structure | `test_api_structure.py` (changed) | exactly two `graph` paths, GET, observe; `P18` pin |
| generation | `gen_ui.py --check`, `gen_api_docs.py --check`, `test_core_client.py` | fresh generated files; client binding parity |
| regression | full suite (short `--basetemp`), P8–P17 mutation suites, SPA build/`tsc`/`npm test`, e2e + G3, Ruff, mkdocs `--strict`, wheel check | unchanged behaviour elsewhere |

## 14. Boundary tests (the invariants that make P18 a view)

1. No write: handler uses `db.read()`; event seq and row counts unchanged (integration) and no
   writer import (static).
2. No inference: every edge's `field` is in `EDGES`, and its endpoints equal the holder's column
   value or the `Relation` row's ends (unit over a fixture with near-miss rows).
3. No routing: `graph.py` imports nothing from `core/routing`; route decision nodes carry only the
   A2 attrs (static + unit).
4. No second import graph: the repository route reads `artifacts.get(payload_sha256)` and never
   `connections`/`inspection.inspect`/the filesystem (static + a fixture payload containing a
   file absent from disk).
5. One loop, one invalidation system, one cache (static + TS).
6. No project-isolation claim: a test documents that an observe token reads every project's
   graph (so a future change to that is deliberate).

## 15. Mutation suite `tools/mutate_p18.py` — every mutant must be killed by its direct test

| # | Mutation | Direct test |
|---|---|---|
| M01 | an edge emitted when its field is empty | unit: no edge without a value |
| M02 | wrong relation: `continues` read from `task_id` | unit parity over `parity.json` |
| M03 | every `Relation` tier emitted as EXTRACTED | unit: tier per row |
| M04 | `INFERRED` drawn solid | TS encoding ↔ renderer |
| M05 | inactive plan versions omitted instead of marked | unit: inactive kept and marked |
| M06 | workspace focus returns projects' children | unit: world level has projects only |
| M07 | focus ignored (BFS from the workspace) | unit: first node is the focus |
| M08 | depth cap removed | unit: no node beyond depth |
| M09 | node cap ignored | unit: `len(nodes) ≤ limit` with `truncated` |
| M10 | a `device` focus accepted | unit + integration: 400 |
| M11 | route decision `explanation` serialised | unit: per-kind field allowlist |
| M12 | ordering by set iteration (sort removed) | unit: exact expected order, two databases same bytes |
| M13 | layout seeded with `Math.random` | TS: two runs identical (+ static ban) |
| M14 | mirror lists only the focus's neighbours | TS: mirror ids == loaded ids |
| M15 | keyboard ↓ skips the last edge (off by one) | TS keyboard reducer |
| M16 | search does not expand ancestors | TS model |
| M17 | loop reschedules with no animation | TS loop: zero frames after settle |
| M18 | pulse enqueued under reduced motion | TS energy |
| M19 | `render.ts` calls `requestAnimationFrame` | static single-caller test |
| M20 | LOD threshold 250 → ∞ | TS draw-work proxy |
| M21 | repository graph built from a filesystem walk | unit: fixture payload with a file not on disk appears (+ static) |
| M22 | an inferred "same plan" sibling edge added | unit: every edge's field ∈ `EDGES` and matches its column |
| M23 | the route appends an event / opens a write | integration: seq and row counts unchanged |
| M24 | `lift()` lifts to the root instead of the nearest visible ancestor | TS model |
| M25 | dimming set excludes the focus's neighbours | TS model |
| M26 | collapse leaves a grandchild visible | TS model |
| M27 | `hidden` counts omitted on truncation | unit |
| M28 | refresh reseeds existing nodes | TS layout stability |
| M29 | stale payload not flagged | unit |
| M30 | `execution` frames stop invalidating `/v1/world/graph` | TS invalidation (+ `gen_ui --check` for the TUI copy) |
| M31 | labels not redacted | unit |
| M32 | pulse on an ENDED execution | TS energy |
| M33 | canvas rendered below 600 px | TS responsive rule + e2e |

## 16. Acceptance scenarios

| # | Scenario | Test |
|---|---|---|
| A18-01 | world level: projects as collapsed clusters with counts, no child rows | unit + e2e |
| A18-02 | project focus: its missions, repositories, sessions, knowledge; URL `#/world/graph/project/<id>` | e2e |
| A18-03 | mission focus: plans, tasks, executions, sessions, approvals, verifications | e2e |
| A18-04 | Relations tab ↔ graph: same edges for the object | integration (A1 (2)) + TS |
| A18-05 | keyboard traversal visits every edge of the focus in order | TS + e2e |
| A18-06 | Enter opens `#/o/<kind>/<id>`; Back returns to the same picture | e2e |
| A18-07 | `+`/`-` zoom | e2e |
| A18-08 | `0` fits | e2e |
| A18-09 | `/` search finds a loaded node | TS + e2e |
| A18-10 | search expands collapsed ancestors | TS |
| A18-11 | focus + context dimming | TS |
| A18-12 | expand/collapse by parent | TS |
| A18-13 | edge lifting to the nearest visible ancestor, with counts | TS |
| A18-14 | a live execution's edge pulses once per frame batch; none when ended | TS + e2e (fake harness) |
| A18-15 | reduced motion: no tween, fade or pulse; live edge static 2 px | TS + e2e emulation |
| A18-16 | hidden or blurred page parks the loop | TS + e2e |
| A18-17 | canvas context loss parks; restore redraws once | TS + e2e (dispatched event) |
| A18-18 | 1,000-node fixture within the CI proxies; manual 60 fps recorded | TS/unit + manual |
| A18-19 | > 250 visible nodes → dots, batched draw | TS |
| A18-20 | truncation → `truncated`, `hidden`, "+N" stubs that refocus | unit + TS |
| A18-21 | deterministic ordering (same bytes) | unit |
| A18-22 | deterministic layout; refresh moves no existing node | TS |
| A18-23 | repository import graph: focus, depth, aggregation, outside endpoints | unit + e2e |
| A18-24 | stale / not inspected / payload missing | unit + e2e |
| A18-25 | unknown focus → 404, view says so | integration + e2e |
| A18-26 | a non-node kind as focus → 400 | integration |
| A18-27 | accessible mirror == loaded graph; axe clean | TS + e2e |
| A18-28 | below 600 px: Relations list, no canvas | e2e |
| A18-29 | no graph mutation (read-only) | integration + static |
| A18-30 | no model/harness reasoning: route decision attrs only | unit |
| A18-31 | no inferred relationships | unit |
| A18-32 | API/client generation parity | `gen_api_docs --check`, structure, `test_core_client` |

## 17. Documentation requirements

As built, in this repository's architecture docs only (P25 owns user docs and the site): this
gate's §23 as-built; the plan's P18 entry and a P19 carry-forward line (A1 consolidation);
ui-architecture §5 (the encoding table of A3, the routes of A4, loop and budget as built);
design research §26 and ADR-0016 get a dated note pointing at deviation V1 (the originals are not
rewritten); design system graph-view row; testing-strategy (P18 row, mutation suite);
`api-reference.md` regenerated.

## 18. Known limitations, deferrals and tracked issues

### 18.1 Limitations

1. No project-level isolation (A15).
2. A live execution re-reads the focused graph up to once a second (A8).
3. The 60 fps target is manual evidence, not a CI fact (A10).
4. `contextlost` on a 2D canvas is Chromium behaviour; elsewhere a lost context is only noticed
   as a blank canvas (the list toggle remains).
5. Layout is main-thread; a Worker is not planned without a measured need.
6. Words for structural edges and referent-side words are new copy in `EDGE_WORDS` (English
   only, Q8).

### 18.2 Deferred (owner named)

A1 consolidation → P19; 3D → after V1; per-project scopes → post-V1, audited by P24; trace view
→ P21; legacy graph import/retirement → P22; meetings/decisions/people lists (S9) → P22/later;
user docs → P25.

### 18.3 The five known P17 issues — not P18's, still tracked

| Issue | Owner | Blocks P18? |
|---|---|---|
| `python -m claude_sessions tui` does not reach V1 verbs | P19/P22 | no |
| P16 keyboard e2e once over its deadline under load | test infrastructure | no — but P18 adds e2e to the same job; a repeat is reported, never widened |
| presence cannot tell TUI from CLI | P15/P19 | no |
| top-level `archeus --help` misses newer V1 verbs | P22/P25 | no |
| manual Windows Terminal/conhost check | user | no |

## 19. Deviations from the architecture (declared up front)

| # | Source | What it says | P18 does | Why |
|---|---|---|---|---|
| **V1** | ADR-0016, research §26 | ring = person | ring = **session** (P16 §20.10) | V1 has no person table; P16 is the later implementation authority |
| **V2** | principle 7 (one declaration) | one edge definition | three until P19 (Core `graph.py`, `relations.ts`, `present.py`) | P19 owns the consolidation; parity proven by one fixture file and a route test (A1) |
| **V3** | ADR-0016 "cluster = project" | clusters show projects' contents | world level = collapsed project clusters with counts; contents only on focus | P16 §20.15 "never load the world" (A4) |
| **V4** | P16 §20.15 budget | 60 fps on integrated graphics | CI gates proxies; 60 fps is manual evidence | headless CI measures the rasteriser, not the GPU (A10) |
| **V5** | P16 §20.16 "scope-checked" | scope-checked query | `observe` + existence in the one workspace; no project isolation | the auth model has no project dimension (A15) |
| **V6** | plan §31.1 | only `/v1/world/graph` is new | also `/v1/repositories/{id}/graph` | G32's commitment (P16 §20.16) is a separate query over P4's record, not a node kind of the world graph (A5) |
| **V7** | research §26 "diamond decision" | a decision node | diamond = DECISION-type knowledge item | Decision has no table; its knowledge item is its record (A2/A3) |
| **V8** | P16 §20.2 lists | the Relations list shows every edge | two structural edges (`tasks.plan_id`, `repositories.project_id`) and lifted edges (aggregates of real edges, with their count) appear in the graph and its mirror, not in the Relations tab | they carry the hierarchy the G4 mechanisms need; the mirror is their list equivalent; P19 unifies |
| **V9** | ui-architecture §5 | layout "computed once per focus" | once per focus, plus a local settle of new nodes only on expand/refresh | stability without a full relayout (A7) |

## 20. Evidence required before P18 is declared complete

1. All A18-01..32 pass; each names its test in as-built.
2. `mutate_p18` fully killed with its direct tests; P8–P17 suites re-run, all killed.
3. Full suite green locally (short `--basetemp`); SPA build, `tsc`, `npm test`; e2e + G3 with
   `ARCHEUS_E2E=1`; Ruff; `gen_ui.py --check`; `gen_api_docs.py --check`; mkdocs `--strict`;
   wheel built, installed in a clean venv, SPA served with Node off PATH.
4. Manual: 60 fps on named integrated graphics (A10); the graph checked in Edge on Windows.
5. CI green on every job after the user approves the push; each job reported; any flake
   distinguished from a defect and never cured by a widened threshold.
6. As-built section with every deviation (§22) and the file list.

## 21. Implementation order and commits (after approval)

1. `docs: P18 design gate` — this file with the approved decisions.
2. `P18: the graph query` — `core/application/graph.py`, the two routes, schemas, API docs and
   generated client, `test_api_structure` allowlist, CoreClient binding; Python tests.
3. `P18: shared edge words and invalidation` — `EDGE_WORDS` in `relations.ts`, the rules in
   `invalidation.json`, regenerated SPA/TUI tables, `mutate_p16` anchors if moved.
4. `P18: the spatial view` — `src/graph/*`, the World and Relations toggles, routes.
5. `P18: tests, boundaries and mutations` — TS/e2e/boundary tests, `tools/mutate_p18.py`.
6. `docs: P18 as built`.

Push only after local validation and the user's confirmation; then watch CI.

## 22. Deviations and new decisions for the user's review

Recorded during implementation as they arise; none is applied silently.

| # | Where | What was approved | What was done, and why | Status |
|---|---|---|---|---|
| **I1** | A6 ordering | order by hop, kind rank, **presentation-class** rank, `updated_at`, id | Core orders an **open** row (a state with a way out in `states.py`) before a **settled** one instead of by presentation class. The presentation table is client data (`presentation.json`); Core reading it would put presentation into the API, the thing A1 keeps out. The domain table gives the same practical order (a running attempt before an ended one — tested). | approved 2026-09-29 |
| **I2** | A4, A1 | a mission focus returns its approvals | Only the **pending** approval, as the list shows it (`missionEdges`' "waiting on approval"). A membership edge for every approval would have held `approvals.mission_id` from two directions, and one field cannot have one pair of words from both ends; decided approvals are history, read in the mission's inspector. | approved 2026-09-29 |
| **I3** | A1, V8 | two structural edges (`tasks.plan_id`, `repositories.project_id`) | Four: also `knowledge_items.project_id` (so a project focus reaches its knowledge, as A4 requires) and `reviews.plan_id` (so a mission focus reaches its reviews). Each is a real column, marked `structural`, drawn at half weight and listed in the mirror; none is on a Relations tab until P19. | approved 2026-09-29 |
| **I4** | A4 | a project focus returns its meetings | Meetings are reached through their relations only: `meetings.project_id` has no index, and §6 forbids a scan. | recorded |
| **I5** | A11 | Enter opens the inspector; `+/-`, `0`, `/` | Also **F** — focus the graph on the selected node, which is the drill (world → project → mission → execution) — and **P** to mark a path end. Double-click opens, a click selects. Enter keeps its approved meaning. | approved 2026-09-29 |
| **I6** | A7 | children appear with one opacity step | They appear at once, with no fade: less motion than approved, never more. The focus-change camera move is not built either (§22.1 D5; this row said it was). | recorded |
| **I7** | §8 | "This object is not in the graph" | P16's existing wording for a 404 read ("the graph is unavailable: It no longer exists."), so one read failure reads the same everywhere. | recorded |
| **I8** | A2 allowlist | node fields `kind, id, label, parent, machine, state, attrs, counts, endpoint, missing` | A knowledge item also carries its `type` — the classification the DECISION diamond (A3, V7) is drawn from; never its body. | recorded |
| **I9** | A13 | chips by relationship field | Chips by the relationship's **words**: two fields can share them ("of mission"), and a person filters by what they read. | recorded |
| **I10** | A8 | the view reacts to frames | P16's cache gains `store.onFrame()`: listeners get a frame's type and subject after it invalidated what it makes stale. The graph uses it to pulse a live edge; no payload is read as state. It is the one change to `cache.ts` and `App.tsx`. | recorded |
| **I11** | A5 | `focus` matched against the payload | Also refused before any read when it names `..`, `.`, a backslash or exceeds 1,024 characters (400), so a path can never be traversal-shaped even though it is only ever compared with stored paths. | recorded |
| **I12** | A6 | a neighbourhood from holders' edges | A holder row found by a reverse lookup is loaded **only if it holds an edge to the node** (found by reading the approval → mission path, where the mission's edge exists only while the approval is pending); a node is never drawn unconnected by accident. | recorded |
| **I13** | §12.3-style regression | P16/P17 mutation suites re-run unchanged | P18's new first entry in the mission and approval invalidation rules moved the text P16's M28 and P17's M11 are anchored on; both runners refused before mutating anything. The anchors now include the new entry; the mutants are the same. | recorded |

### 22.1 Post-audit corrections (2026-09-29)

A pre-push audit of the built view against §1–§21 found seven gaps (F1–F7) and eight places
where this gate's text does not describe what was built (D1–D8). The user decided them on
2026-09-29: fix F1–F7, add the 390 px overflow regression, and fold D1–D8 in without turning any
of them into a new architecture decision. The approved sections above are **not rewritten**: an
item where the build differs from an approved design is recorded here and held for review.

| # | Gate decision it serves | What changed | Test (mutants) | Architecture? | Status |
|---|---|---|---|---|---|
| **F1** | A13 pin | `.` (and a toolbar **Pin/Unpin** button, `aria-pressed`, for the pointer) toggles the selected node in a per-tab, in-memory map keyed by the read path — never stored, never sent, not in the URL; the layout receives the set as fixed; the mirror says "(pinned)". Every node already placed keeps its position (A7) and nothing auto-collapses (D6), so both of A13's guarantees hold for every node today; the pin is what keeps them for this one if either ever changes. | TS `pin: "." toggles…` (M35, M36); e2e `test_closing_the_inspector_returns_to_the_canvas_and_a_pin_is_never_stored` (a reload forgets it; no storage key) | no — completes A13. The `.` key is new, like I5's F and P | key: approved 2026-09-29 |
| **F2** | A10 frame-time degrade | `Loop` measures the time between frames of a running animation; three consecutive frames over 20 ms set `degraded` until the animation ends, and one more frame then draws everything again. A degraded frame draws no pulse and no label but the focus's. | TS `three slow frames…` (M37, M46), `degraded, a frame draws…` (M38) | no — completes A10 | fixed |
| **F3** | A10 proxy (5) | `render.frame()` keeps a **static layer**: an offscreen canvas (never in the DOM) holding everything but the pulses, redrawn only when `staticSig()` — model, visible keys, drawn edges, positions, camera, focus, selection, dimming, path, live set, reduced motion, degrade, size, theme — changes. A frame in which only a pulse moved is one `drawImage` plus one path per pulse (edges looked up by id, indexed once per drawn list). Pulses are drawn **over** the nodes now, as §A10 says. A lost context drops the layer. The proxy is not weakened: it is gated at 1,000 nodes. | TS `a pulse frame reuses the static layer…` (M39, M40, M47); e2e zoom test asserts the copied layer shows the graph (M47) | no — completes A10 | fixed |
| **F4** | A11 focus order | Closing an inspector (Close, Esc or Back) whose page is a graph returns focus to the canvas, which stayed mounted under the inspector and kept its walk (the same node selected). A two-line rule in `App.tsx`'s focus effect; every other page still focuses `main h1` (P16 §17). | e2e (same test as F1) (M41) | no — completes A11 | fixed |
| **F5** | A3 plan row | A plan version whose presentation class is `inactive` (superseded, rejected) is drawn at `--text-3`, not only its edge. | TS `a superseded or rejected plan version…` (M34) | no — completes A3 | fixed |
| **F6** | A8, A18-14 | The pulse decision is one pure function, `model.pulseFor(frame, drawn, live, lastPulse, now, reduced)`, which the view calls. | TS `a pulse: only an execution.* frame…` (M42, M43), with M18 and M32 | no | fixed |
| **F7** | §15 mutation integrity | M17 left a dangling `else`, so it did not parse and "killed" by a crash. It is a valid mutant now. `mutate_p11._apply` (the engine of P11–P18) refuses a mutant that does not parse, before any run, as **BROKEN MUTANT**, so it can never count. `test_mutation_suites_parse.py` checks every mutant of all eleven suites. `mutate_p18` prints the failing test that names each mutant. A mutant that fails the SPA's type check stops the run in the same way (M41 did once and was corrected). | `test_mutation_suites_parse.py`; M17 killed by `a redraw is one frame…` | no — test infrastructure | fixed (`4ca892d`) |
| **R390** | A12, A18-28 | The below-600 px test asserts `scrollWidth − innerWidth ≤ 0` at 390 px for a mission graph URL and the world graph URL, not only that the canvas is absent. | e2e `test_below_600_px_the_relations_list_is_the_view` (M45) | no | fixed |
| **D1** | A1, A6 text | A1 and A6 describe one `EDGES` table that the breadth-first walk reads. As built, `graph.py` holds the same fields as a per-kind `held_edges()` plus `relation_edge()` and the reverse lookups in `_holders()` (the parity cases hold them equal to the list mappers). "`structural` marks two" is four since I3. | parity and query tests, unchanged | no | recorded |
| **D2** | A2 parent list | As built, a session's parent is its mission, else its project; a review's is its **plan** (A2 says mission; this follows approved I3); a policy decision's is its mission; a context package's and an automation's is its project; an automation run's is its automation (A2 says "others → none"). Each is the row's own column. | query tests, unchanged | differs from A2's text | approved as recorded, 2026-09-29 |
| **D3** | A5 | "payload missing → logged once per sha" was not built. It is now: one `archeus.core` warning per missing sha; the view still says "missing" on every read. | `test_a_missing_payload_is_logged_once_per_sha` (M44) | no — completes A5 | fixed |
| **D4** | A6, A10 proxy (4), A15 | The walk queries **per node** (`rows.where` per id, all inside the one `db.read()`), not "one batched `IN (…)` per edge definition per hop". A response's cost is therefore bounded by the size of the neighbourhoods it reads, not by the node cap: a project with 10,000 knowledge items reads them all before the cap cuts (measured 0.10 s for 1,100). The node cap and the depth cap hold. Proposed: add this to P24's audit of graph cost and aggregation. | `test_a_thousand_node_neighbourhood_is_built_within_budget`, unchanged | differs from A6's text | approved as recorded, 2026-09-29; a P24 audit item |
| **D5** | A7 focus change | A focus change is a new read, so the view remounts and the camera **jumps** to the new fit: the ≤ 240 ms focus-change tween is not built (zoom and fit do tween). Less motion than approved, never more. I6 above wrongly said it was built; corrected. | — | differs from A7's text | approved as recorded, 2026-09-29 |
| **D6** | A10 client cap | "An expand that would exceed 1,000 collapses the farthest expanded cluster first" is not built. It cannot happen: a view holds one read (the client sends no `limit`, so at most 500 nodes) plus one "+N" stub per parent and kind, and expanding only shows nodes already loaded. A stub re-focuses instead. | TS stub test, unchanged | differs from A10's text | approved as recorded, 2026-09-29 |
| **D7** | §13 design row | The single `requestAnimationFrame` caller and the `layout.ts` clock/random bans were only in the TS suite. They are now also in `test_design_gates.py`, as §13 says, so they run in the Node-free `test` job. | `test_the_graph_loop_is_the_only_animation_frame_caller` (M49), `test_the_layout_reads_no_clock_and_no_random` (M48) | no — completes §13 | fixed |
| **D8** | §23 | §23 said everything was built as written except I1–I13, and that "the pulse itself is TS-tested". Both corrected below: what is not built is listed, and the pulse test exists (F6). | — | no | fixed |

M17's anchor moved again with F2's degrade branch; the mutant is the same (the loop always
schedules another frame).

**Decisions (the user, 2026-09-29).** F2–F7, D3, D7, the 390 px regression and the mutation
engine's parse and type-check protections are accepted as described. F1 is approved as built:
the `.` key, the Pin/Unpin button, pins per tab and in memory only, shown in the mirror, no
persistence. D2, D4, D5 and D6 are approved **as recorded here**: A2, A6, A7 and A10 keep their
original wording and these rows are the record of what was built instead; no tween (D5) and no
farthest-cluster collapse (D6) is added to match the original text; D4 is a P24
security/performance audit item (plan, P24 entry) and the query is not redesigned in P18.

### 22.2 Consistency pass (2026-09-29): found, not changed

A last read of A1–A17, §5–§14 and V1–V9 against the code, after §22.1. Nothing here was changed:
the first group is description only; the second is approved behaviour that is not built, and each
needs the user's decision (build it, or accept it as recorded).

**Description differences (recorded).**

| # | Where | The gate says | What is built |
|---|---|---|---|
| C1 | A4 | project `counts` are "missions by presentation class" | missions by **state** (`mission_states`), for the reason of I1: the class table is client data |
| C2 | A7 | children seeded "in id order" | in the read's order (hop, kind rank, open before settled, `updated_at`, id — A6/I1) |
| C3 | A8 | "an identical response changes no position and redraws only the pulse" | no position moves; each re-read is a new object, so the static layer (F3) is redrawn once per re-read — at most once a second (A8) — and every pulse frame between re-reads is the layer copy plus the pulse |
| C4 | §5 `loading` | "the previous picture stays, marked" | true for a re-read of the same focus; a focus change is a new read and a remount (D5), so it shows the loading state |
| C5 | §7 | `mirror.tsx`; "a toggle on World and on the Relations tab" | `mirror.ts` (plus `keys.ts`, `wide.ts`); the graph is reached by a link (`GraphLink`), the list by the **List** chip |
| C6 | §8 | context lost → "the Relations list is shown" | the loop parks and the canvas stays; the **List** chip remains (as §18.1 item 4 says) |
| C7 | §13 | `tests/v1/unit/test_graph_query.py`; `clients/app/test/graph-*.test.ts` | `tests/v1/integration/test_graph_query.py`; one `clients/app/test/graph.test.ts` (§23's table is right) |
| C8 | A12 | a graph URL below 600 px shows the focused object's Relations list | for a mission (any object with a Relations tab) it does; for the world level and a project focus, which have no Relations tab, it shows the note and a link to the list page |

**Approved behaviour not built (for the user's decision).**

| # | Where | Approved | Built |
|---|---|---|---|
| N1 | A3 project, A4 | the world-level cluster is drawn "with its counts" | Core returns `counts`; the client shows them nowhere — not on the canvas, not in the mirror (the label only) |
| N2 | A3 route decision | "its A2 attrs in the label on focus" | Core returns `attrs`; the client shows only the label |
| N3 | A10 labels | ≤ 250: labels for the focus, its neighbours and the **hovered** or keyboard-selected node; > 250: the focus and the selection | there is no hover; labels follow the walk's current node and its neighbours; above 250 only the walk's current node is labelled, not the query focus when the walk has moved |
| N4 | A13 search | a match expands its ancestors "and centres it" | it expands and selects the match; the camera does not move to it |
| N5 | A13 path | otherwise "no path within the loaded neighbourhood" | no message: an unconnected pair highlights nothing |
| N6 | A11 Esc | "clears search, then selection" | clears the search and the path marks; the selection stays |
| N7 | A12 touch | pinch zooms; toolbar targets never under 44 px at ≥ 600 px | no touch-pinch handling (a trackpad pinch arrives as a wheel and zooms); chips are `--target-desktop` (28 px) with no coarse-pointer rule. Double-tap relies on the browser's `dblclick`, not verified on a touch device |

## 23. As built

Everything in §1–§21 is built as written and approved (§4.1), except the implementation
decisions recorded in §22 (I1–I13) and the post-audit corrections of §22.1. **Not built as
written, held for review and then approved as recorded (§22.1, the user, 2026-09-29):** D2
(A2's parent list), D4 (A6's batched per-hop query; cost bounded by the neighbourhoods read,
not the cap — a P24 audit item), D5 (no focus-change camera tween) and D6 (no farthest-cluster
collapse, which one read of at most 500 nodes cannot need); the pin key `.` (F1) likewise.
**Found in the final consistency pass and not changed (§22.2):** eight description differences
(C1–C8) and seven approved behaviours that are not built (N1–N7), awaiting the user's decision. Commits: `ecfbacd` (this gate, approved), `20c26ec` (the
graph query and its two routes), `5bada10` (`EDGE_WORDS` and the invalidation rules),
`711a052` (the spatial view), `67ae6b6` (tests, boundaries and the mutation suite),
`24d6190` (the P16/P17 anchors, I13), `f9ad2ee` (as built), and after the audit `4ca892d`
(F7: broken mutants), `f29fc5e` (F1–F6), `c3deabc` (the 390 px overflow regression),
`7eabdc9` (D3, D7), `bba3544` (the drill waits for the graph it checks) and the docs commit
recording §22 and §22.1.

**Backend (two read routes; no migration, no state, no event type).** New:
`archeus/core/application/graph.py` — `world_graph()` (A4, A6: a breadth-first neighbourhood over
the columns and `Relation` rows Core records, each edge held by the row holding its field, the
world level every project collapsed with counts) and `repository_graph()` (A5: the stored
inspection payload, focused, aggregated, with `stale` / `not_inspected` / `payload_missing`).
Changed: `api/routes.py` (the two `observe` GET rows, `focus`/`depth`/`limit` validation, the
query allowlist), `api/schemas.py` (`GraphNode`, `GraphEdge`, `GraphHidden`, `WorldGraph`,
`RepositoryGraph`), `tools/gen_api_docs.py` (two query parameter types). The route table went
from 97 to 99 rows. Generated: `api-reference.md`, `generated.ts`.

**Shared vocabulary and invalidation.** `clients/app/src/graph/relations.ts` gains `EDGE_WORDS`
and `edgeWords()`; its list functions read their words from it with every output unchanged
(`parity.json`, the relations tests). `invalidation.json`: `/v1/world/graph**` on the 18 kinds a
node or edge is read from; regenerated into `rules.ts` and the TUI's `_tables.py`.
`tools/mutate_p16.py`'s M11/M12 anchors moved with the text.

**Client.** `clients/app/src/graph/`: `encoding.ts` (the A3 table and the one `tracePath`),
`model.ts` (visibility, lifting, expand/collapse, focus + context, search, path, "+N" stubs,
live executions), `layout.ts` (seeded, fixed 120 iterations, positions kept), `render.ts`
(Canvas 2D, batched per style, dots above 250), `loop.ts` (the client's only
`requestAnimationFrame` caller), `keys.ts` (traversal), `mirror.ts` (the accessible rows),
`wide.ts` (the 600 px rule), `GraphView.tsx`. Changed: `App.tsx` (the world graph routes; the
frame notification), `data/cache.ts` (`onFrame`, I10), `nav/destinations.ts` (three graph route
forms), `components/Relations.tsx` (`GraphLink`), `surfaces/{World,Mission,Control,Inspector}.tsx`
(the links), `styles/app.css` (graph styles; no animation, no media query). No dependency added.
Build: 390 KB JS, 119 KB gzip (was 360 KB), 17 KB CSS.

**Tests.**

| Layer | File | Count |
|---|---|---|
| Core edges vs the shared cases; vocabulary coverage | `tests/v1/unit/test_graph_parity.py` | 17 |
| query over a real database | `tests/v1/integration/test_graph_query.py` | 26 |
| routes over a real Core; route ↔ TUI list parity | `tests/v1/integration/test_graph_routes.py` | 4 |
| boundaries (static) | `tests/v1/unit/test_graph_boundaries.py` | 6 |
| client units | `clients/app/test/graph.test.ts` | 30 |
| browser | `tests/v1/e2e/test_spa_p18.py` | 9 |
| the loop and the layout, Node-free (D7) | `tests/v1/design/test_design_gates.py` | 2 |
| every mutant of P8–P18 parses (F7) | `tests/v1/unit/test_mutation_suites_parse.py` | 12 |
| changed | `test_api_structure.py` (the `graph` allowlist, `P18` pin), `test_core_client.py` and both bindings (`world_graph`, `repository_graph`) | — |

`tools/mutate_p18.py`: **49/49 killed** — M01–M33 of §15, and M34–M49 for the §22.1
corrections (F1 M35–M36, F2 M37, M38, M46, F3 M39, M40, M47, F4 M41, F5 M34, F6 M42–M43, D3
M44, the 390 px regression M45, D7 M48–M49). The runner prints the failing test that names
each mutant, and refuses a mutant that does not parse (F7); a mutant guarded by a browser test
rebuilds the SPA.

**Acceptance scenarios (§16), each with its test.** 
| # | Scenario | Test |
|---|---|---|
| A18-01 | world level: projects collapsed with counts, no child row | `test_the_world_level_is_projects_only_collapsed_with_counts`; e2e drill |
| A18-02 | project focus | `test_a_project_focus_reaches_its_missions_sessions_and_knowledge`; e2e drill (`F` on the project) |
| A18-03 | mission focus | e2e drill (`F` on the mission): plan and execution in the mirror |
| A18-04 | Relations ↔ graph parity | `test_core_edges_equal_the_list_mapper_on_every_shared_case` (15 cases); `test_the_route_and_the_tui_list_show_the_same_edges` (real mission) |
| A18-05 | keyboard traversal visits every edge in order | `↓ visits every edge of the focus…` (TS); e2e drill |
| A18-06 | Enter → `#/o/<kind>/<id>`, Back → the graph; closing returns focus to the canvas | e2e drill; `test_closing_the_inspector_returns_to_the_canvas_and_a_pin_is_never_stored` (F4) |
| A18-07/08 | zoom, fit | e2e `test_zoom_fit_and_the_loop_parking` |
| A18-09/10 | search; search expands ancestors | TS `search finds loaded nodes and expands their ancestors`; e2e drill |
| A18-11 | focus + context | TS |
| A18-12 | expand/collapse | TS `collapse hides every descendant…` |
| A18-13 | edge lifting with counts | TS `edges lift to the nearest visible ancestor…` |
| A18-14 | live execution | TS `only an execution Core says is active is live…`; TS `a pulse: only an execution.* frame about a live execution, once per 2 s per edge, never reduced` (F6); e2e `test_a_running_execution_is_live_on_its_edge` (the live edge) |
| A18-15 | reduced motion | TS loop test; e2e `test_reduced_motion_moves_nothing` (a zoom is exactly one frame) |
| A18-16/17 | hidden page, lost context park the loop | TS loop tests; e2e (`visibilitychange`, dispatched `contextlost`/`contextrestored`) |
| A18-18 | 1,000-node budget | TS layout proxy; `test_a_thousand_node_neighbourhood_is_built_within_budget` (0.10 s measured, gate 1.5 s); TS `a pulse frame reuses the static layer…` (proxy 5, F3) and the frame-time degrade tests (F2); 60 fps manual (below) |
| A18-19 | > 250 → dots, batched | TS `above 250 visible nodes every node is a dot…` |
| A18-20 | truncation, `hidden`, "+N" | `test_the_cap_holds_and_hidden_counts_what_it_cut`; TS stub test |
| A18-21 | deterministic ordering | `test_nodes_come_in_hop_then_kind_rank_order_and_the_same_bytes_twice`, `test_edges_are_sorted_and_ids_are_stable` |
| A18-22 | deterministic, stable layout | TS layout tests |
| A18-23 | import graph | `test_the_repository_graph_*` (4); e2e `test_the_repository_import_graph` |
| A18-24 | stale / not inspected / payload missing | `test_stale_not_inspected_and_missing_payload_are_said_not_guessed` |
| A18-25 | unknown focus | `test_an_unknown_focus_is_not_found`; routes 404; e2e `test_an_unknown_focus_says_so` |
| A18-26 | non-node kind as focus | `test_the_graph_needs_a_credential_and_refuses_what_is_not_a_node` |
| A18-27 | mirror; axe | TS mirror test; e2e `test_axe_and_no_sideways_scroll_on_the_graph` |
| A18-28 | < 600 px | e2e `test_below_600_px_the_relations_list_is_the_view` (no canvas, the list, and no sideways scroll at 390 px) |
| A18-29 | no mutation | `test_the_graph_routes_write_nothing`; boundary scans |
| A18-30 | no reasoning exposed | `test_a_route_decision_shows_recorded_selection_facts_only`, `test_every_node_carries_only_allowlisted_keys` |
| A18-31 | no inferred relationships | `test_every_edge_is_a_recorded_column_or_relation_row` |
| A18-32 | API/client generation parity | `gen_api_docs.py --check`, `test_api_structure.py`, `test_core_client.py` |


**Regression (after the §22.1 corrections, 2026-09-29, on `bba3544`).** Full suite (`--basetemp` short): **4,817 passed, 0 failed** (15 skipped, 6 xfailed). Two earlier runs of the same list each stopped on one timing failure, both load-dependent and both from a test reading the moment before an asynchronous step lands: the P18 drill read `data-graph-focus` before the new graph rendered (fixed in `bba3544`, which waits for it as the project step already did), and P15's `test_R5_presence_is_traced_on_transitions_only_with_the_connection` read the events between `sse._unregister` lowering the count and `_trace` appending `device.stream_closed` (passes 16/16 alone; P15's test, not changed here — tracked). Mutation suites, every mutant killed and none broken: P8 22/22, P9 36/36, P10 37/37, P11 36/36, P12 28/28, P13 16/16, P14 21/21, P15 23/23, P16 29/29, P17 28/28, **P18 49/49**. e2e + G3 with `ARCHEUS_E2E=1`: 28 passed, 3 skipped (the GUI/TUI functions over the in-process binding), 1 xfailed (P19). `npm test` 70/70; `tsc` and `vite build` clean (392 KB JS, 120 KB gzip; 17 KB CSS); `gen_ui.py`, `gen_api_docs.py` and `gen_plugin.py --check`, Ruff and mkdocs `--strict` clean; the wheel built, installed in a clean venv, `check_wheel.py` passes (the SPA served with Node off PATH) and the installed Core lists both graph routes, `GET`, `observe`. CI: after the push (§20 item 5).

**Manual evidence still owed by the user (not claimable from CI).**

1. *A10 — 60 fps on integrated graphics.* On a machine with integrated graphics (Intel UHD
   class), in Edge or Chrome on Windows: start Core, create or import enough data for a
   neighbourhood near the cap (or open `#/world/graph/project/<id>` on the largest project),
   open DevTools → Performance, record while pressing `+`, `-` and `0` a few times and while a
   running execution pulses; the frame chart must hold 60 fps (frames ≤ 16.7 ms) during the
   camera moves and pulses, and show no frames at all while idle (the loop parks). Record the
   machine, browser, node count shown (`data-graph-nodes`) and the worst frame in §22.
2. *P17 carry-over — Windows Terminal and conhost.* With Core running (`archeus core`): in
   Windows Terminal and in a classic conhost window (`conhost.exe powershell`), run `archeus
   tui`; check the state glyphs render (or the ASCII set with `ARCHEUS_TUI_ASCII=1`), the
   colours follow the dark default and `--light`, a resize redraws without stray lines, `1`–`4`
   and `a` switch destinations, an inspector opens with Enter and `q` quits and leaves the
   prompt usable. Record any difference between the two consoles.

**Known limitations** as §18.1, plus: the pulse needs `execution.*` frames about a live
execution while the graph is open; a live execution with no progress in that time shows its
thick-static or plain edge only.

**DESIGN_GATE = IMPLEMENTED** once the push is approved and CI is green on every job
(I1, I2, I3 and I5 approved by the user, 2026-09-29; the `.` pin key, D2, D4, D5 and D6
approved as recorded the same day, §22.1; N1–N7 await the user's decision, §22.2).
