# Handoff — rehaul the project Memory and CLAUDE.md tabs

## The ask (verbatim)

> my memory does not only consist of only claudemd so in the projects tab add all
> things related to memory which i build the users should be able to see what is
> being build and updated, rehaul the memory and claude md tabs

Read literally: the project view presents memory as *CLAUDE.md plus a few counters*,
but archeus actually builds and maintains **twelve distinct artifacts** per project.
Most are measured already and shown nowhere. The user wants to see what exists, what
is being written, and what it costs.

Everything below is cited to `file:line` and was verified against this repo's live
data on 2026-08-31. **No implementation has started.** Start fresh from here.

---

## 0. State of the tree before you begin

Released and pushed: **1.8.1** (PyPI + GitHub release, CI green on the full matrix).
`main` is at the 1.8.1 release commit; working tree clean.

Recently landed and directly relevant — do **not** redo:

- Auto-memory now converges: a capped cycle makes partial progress and the scheduler
  returns in `CATCHUP_INTERVAL` (`gui_api.py:470`) until the project is current.
- The scheduler starts from **both** interfaces (`main.py:267`, `gui.py:747`) and does
  a pass `STARTUP_DELAY` after launch (`gui_api.py:475`).
- Per-cycle cost is recorded (`memory.py:1045` `last_cost_usd`) and `last_extracted`
  / `auto_last` are stamped (`memory.py:1292`).
- Reinforcement works again (`hits` reached 32 on this repo; it was stuck at 1).
- Version history: 12 snapshots each of `claude_md` and `memory_graph`, restorable
  (`diffview.py:158` / `:250`), surfaced today **only** in the Audit tab.
- Rule globs are path-prefix correct (`memrules.py:27`); all 12 rules on disk are
  properly scoped, none is `**`.

Live numbers on `D:\Claude` for sanity-checking your work: 350 entities, 126 relations,
12 rule files, digest 117 tok, rules 4 288 tok total, worklog 10 entries, 28 snapshots.

---

## 1. What "memory" actually consists of

| # | Artifact | Path | Written by | Injected? |
|---|---|---|---|---|
| A1 | **Semantic graph** | `<proj>/.archeus/memory/graph.json` **and** the encoded mirror | `memory.save_memory` `memory.py:110` | never directly — source for A2/A3/A7/A11 |
| A2 | **CLAUDE.md digest** (`ARCHEUS:MEMORY`) | project `CLAUDE.md` | `memory.sync_to_claudemd` `memory.py:1422` → `claude_md.write_memory_block` `claude_md.py:71`; built by `build_digest_micro` `memory.py:1342` (≤250 tok) | **always-on, every turn** |
| A3 | **Path-scoped rules** | `<proj>/.claude/rules/archeus-mem-*.md` | `memrules.sync_rules` `memrules.py:93`; glob `memrules.py:27`; cap 400 tok `memrules.py:16` | **lazy** — only when Claude touches a matching path |
| A4 | **Worklog** | `<proj>/.archeus/memory/worklog.json` | `worklog.add_entry` `worklog.py:39` (cap 10) | **per session** (SessionStart) `worklog_hook.py:58` |
| A5 | **Hits sidecar** | `.../memory/hits.log` | `recall._log_hits` `recall.py:322`; folded + deleted by `fold_hits` `recall.py:336` | never (feedback channel) |
| A6 | **Dirty sidecar** | `.../memory/dirty.log` | `memdirty_hook.record` `memdirty_hook.py:55`; drained `memory.py:688` | never |
| A7 | **Cross-project conventions** | global `~/.claude/CLAUDE.md` block | `conventions.sync_to_global` `conventions.py:216` | **always-on, in every project on the account** |
| A8 | **Workspace manifest** | `<proj>/.archeus/workspace-manifest.json` | `workspace.update_manifest` `workspace.py:285`; score `workspace.py:396` | never — status only |
| A9 | **Lessons** | entities inside `graph.json` | `lessons.merge_lessons` `lessons.py:153`; decay `lessons.py:184` | count in digest; text per-prompt via recall |
| A10 | **AUTOGEN / SESSIONS blocks** | project `CLAUDE.md` | `claude_md.py:267` / `:194` | **always-on** |
| A11 | **Recall injection** | (runtime) | `recall.retrieve` `recall.py:365`, hook `recall_hook.py:52` | **per prompt**, ≤ `memory_budget` |
| A12 | **Snapshots** | `<proj>/.archeus/snapshots/` | `diffview.record` `diffview.py:158`, 12 versions/key `diffview.py:25` | never |

Also under `.archeus/`: `scan.lock` (live progress, `memory.py:274`), `bash-log.txt`,
`session-log.md`, `injected-context.md`, `plan-latest.md`, `connections-cache.json`.

**The sentence the UI never says:** CLAUDE.md carries ~117 always-on tokens of memory
digest, while ~4.3 KB of rules cost nothing until Claude opens a matching file.
`est.total_always` (`recall.py:427`) exists precisely to say that and is unused.

---

## 2. What the GUI renders today

`claude_sessions/web/app.js`. Tab list `app.js:1675-1684`; dispatch `app.js:1752-1754`.

**`drawMemory()` — `app.js:2012-2080`.** Fetches `/api/memory/state`, `/api/lessons`,
`/api/workspace-status`, `/api/worklog` (`:2015`). Four cards: *Project memory*
(`:2032-2060`, coverage ring + counters + 3 toggles + budget), *Lessons* (`:2061`),
*Recent work* (`:2066`), *Workspace status* (`:2076`, raw ANSI-stripped lines).
Helpers `:2081-2131`.

**`drawClaudeMd()` — `app.js:2134-2162`.** Fetches `/api/claude-md`, `/api/memory-map`,
then `/api/system-prompt`. Cards: *CLAUDE.md* (raw text + 5 buttons), *Memory files map*,
*loop.md* (prose only), *System prompt*. Dead code: `mf`/`have` at `:2139` are computed
and never used; `f.imports` is fetched and never rendered.

**`drawAudit()` — `app.js:2188-2217`** (overlaps heavily): context-weight table,
*History* panel (`drawHistory` `:2229-2241`), deny rules. `it.path` returned, unused.

**Elsewhere, though memory-related:** `drawConv()` `app.js:3236` (conventions — on the
*global* CLAUDE.md page, not the project), `drawBrief()` `app.js:2358` (Tools tab),
`drawArch()` `app.js:2376` (Tools tab).

---

## 3. Endpoints you can already use

Handlers in `gui_api.py`; GET table `:3273`, POST `:3352`.

| Endpoint | Handler | Key returns |
|---|---|---|
| `/api/memory/state` | `:1635` | `n_entities, n_lessons, n_pending, n_unscanned, hook_on, rules_on, auto_on, pending_units, last_extracted, last_cost_usd, auto_updated, budget, generated_at,` **`est`** |
| `/api/memory-map` | `:1930` | `files:[{label,path,exists,imports:[{ref,exists}]}]` |
| `/api/ctxaudit` | `:1794` | `items:[{label,tokens,lazy,warnings,path}], total` |
| `/api/lessons` | `:1760` | `lessons:[{id,name,summary,status,kind,confidence}]` |
| `/api/history` | `:1826` | `keys:[{key,title,versions:[{ts,added,removed,age}]}]` |
| `/api/conventions` | `:1322` | `conventions:[…], near:[…], block` |
| `/api/worklog` | `:1385` | `on, installed, entries` |
| `/api/workspace-status` | `:1895` | `lines[], score, safe` |
| `/api/memory/progress` | `:1662` | `progress, last:{ok,error,extracted,lessons,pending}` |
| `/api/recall-preview` | `:1903` | `context, tokens, empty` |
| `/api/graph-lite` | `:946` | `modules, edges, memory{…}, repos, languages` |

`est` = `{digest_tokens, hook_budget, rules:[(filename,tokens)], total_always}` from
`recall.estimate_surfaces` `recall.py:410`.

---

## 4. The gap — measured, never shown

A grep of `app.js` for `est|digest_tokens|total_always|evicted|module_edges|repo_summaries|provenance|auto_last|session_counter` returns **zero** memory hits.

1. **Per-rule token cost and glob.** `est.rules` is in the payload; `drawMemory` never
   touches `st.est`. Audit shows opaque `rule <filename>` rows with no module or glob.
2. **`evicted_names`** (`memory.py:1141`) — stored *specifically* so a user can check
   what eviction dropped. No endpoint, no renderer.
3. **`relations` / `module_edges` / `repo_summaries` / `provenance`** — the TUI prints
   relations and module links (`memhub.py:46`); the GUI shows entities only.
4. **hits / reinforcement** — drives eviction ranking and lesson `last_used`. Invisible.
   No "most-recalled" view, no pending-hits count.
5. **`dirty.log`** — no indicator that edits are queued, nor whether `memdirty_hook` is
   installed (contrast `/api/worklog`, which *does* return `installed`).
6. **Lesson decay state** — `last_used` vs `session_counter` vs `memory_lessons_ttl`
   (`lessons.py:184`). Table shows confidence but not "N sessions from eviction".
7. **`auto_last`** — the outcome dict `{graph,lessons,scanned,pending,extracted}` is
   stored and dropped; only the timestamp renders.
8. **Cumulative cost** — only the single most recent `last_cost_usd` exists on disk.
   Nothing accumulates, so total memory spend is unmeasurable. *Needs a writer change.*
9. **Conventions on the project tab** — computed, rendered only on a global page.
10. **Memory-map `imports`** — broken `@import` refs resolve with an `exists` flag that
    is fetched and silently discarded.
11. **Snapshot history** — `memory_graph` versions live in `/api/history` but the Memory
    tab has no link; a graph shrink is discoverable only from another tab.
12. **Workspace checks are flattened to strings** — `gui_api.py:1899` ANSI-strips
    `_evaluate`'s structured `checks[{name,state,detail,applicable}]` (`workspace.py:396`),
    so per-check state, `_WEIGHTS` and `_FIXES` (`workspace.py:49`) never reach the GUI.
13. **`/api/recall-preview` drops `items[]`** (`gui_api.py:1912`) — the preview cannot
    show *why* each entity was picked.
14. **`ctxaudit` item `path`** returned, unused — audit rows are not clickable.
15. **Worklog `session_id`** stored, not rendered — a line can't open its session.

---

## 5. Suggested shape (not prescriptive)

The repo's own recorded lesson is *"users report archeus is great but too complicated
— prioritise usability over feature expansion."* So this is a **consolidation**, not
more cards. Two tabs with one job each:

**Memory = "what archeus knows, and what it costs."** One inventory of the twelve
artifacts, each row: name · what writes it · when it last changed · size/tokens ·
whether it reaches a session (always-on / lazy / per-prompt / never) · an action. Then
the live state: last cycle (`auto_last` + cost), what is queued (`pending_units`,
dirty log), what was evicted, most-reinforced entities, lessons with decay distance.

**CLAUDE.md = "the file, block by block."** Show it as its *blocks* — manual prose,
KEEP-fenced regions, AUTOGEN, SESSIONS, MEMORY digest — each with its token cost and
the button that regenerates just that one, plus the imports map with broken refs
flagged, and the version history inline (it is about this file).

Move the token-weight table out of Audit or make Audit purely the "what will a session
cost me" view; today all three tabs overlap.

**Cheapest high-value wins if scope must shrink:** (1) render `est` — per-rule cost and
globs, with the always-on vs lazy split stated; (2) `auto_last` + evicted names + dirty
count; (3) structured workspace checks instead of ANSI strings.

---

## 6. Repo conventions you must follow

These are load-bearing here; all are documented in `CLAUDE.md` and enforced by tests.

- **Only `paint()`/`paintNow()` may write `#content`.** Take `const nav=paintNow(LOADING)`
  before the await and `if(!paint(nav,html))return;` after. `test_no_page_can_paint_over_the_one_you_are_on` counts raw writes.
- **A job's `onDone` must not repaint** — use `redraw:`. `test_gui_flicker.py` greps for it
  and it caught exactly this during the auto-memory work.
- **Animate `transform`/`opacity` only**; no `backdrop-filter`, no `mix-blend-mode`.
- **CSS override blocks stay at the END of `app.css`** — `@media` and `html.skin-*` add no
  specificity; source order decides.
- **Reuse instruments** (`INST.ring/dial/spark/eq/flow`) rather than adding gauge types;
  size by explicit height, never `aspect-ratio`.
- **Feed from data the renderer already fetched** — instruments never fetch.
- Ponytail: least code that works; reuse before adding. Prefer widening an existing
  endpoint over inventing one.
- **Every new gate must be mutation-verified**: revert the fix, confirm the test goes red,
  restore. A gate nobody has watched fail is not a gate.
- Feature work updates `tools/smoke_gui.py` stubs, `docs/`, and regenerates
  `docs/api.md` (`python tools/gen_api_docs.py`) — a test fails when it is stale.

---

## 7. Verification

1. `python -m pytest tests/ -q` — currently **1676 passed, 1 skipped**.
2. `python -m ruff check .`
3. `python tools/smoke_gui.py` — must stay above its floor of 85 checks; add stubs for
   any new endpoint or the page renders a spinner and the audit proves nothing.
4. `python tools/shot_gui.py` — overflow audit across every skin for the new cards.
5. `python tools/gen_api_docs.py` if routes changed.
6. On this repo: the Memory tab must account for all 12 rule files, 350 entities,
   126 relations, the 28 snapshots and the $0.1237 last-cycle cost.

---

## 8. Adjacent findings (not part of the ask)

- **`site/` and `notes/` are being indexed into memory.** `connections.SKIP_DIRS`
  (`connections.py:21`) has no `site`, and the walk does not consult `.gitignore` —
  so mkdocs build output became a memory unit with its own rule file
  (`archeus-mem-Claude-site_assets.md`, glob `site/assets/javascripts/**`, 396 tok).
  That is a Claude call and a rule file spent on generated output. Worth adding `site`
  to `SKIP_DIRS`, or honouring `.gitignore` in the walk.
- **`_bg_scan_cli` notification wording** differs from the GUI toast; both now report
  real outcomes, but they are two strings for one event.
- `provision.py:302` still has an unguarded `sys.stdout.reconfigure` (the `sync-accounts`
  CLI). Harmless from a console, would fail under `pythonw`.
