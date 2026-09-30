# Archeus V1 — Legacy context and memory migration (P25.5)

Status: **DECIDED — architecture only; nothing is migrated, no tool exists, and no project file,
repository, memory store, Core, API or UI was changed to produce it.** Written 2026-09-30 on
`archeus-v1-rearchitecture` at `c94e026` (`e9d5681`); the user's decision pass of 2026-10-01
resolved MD-1…MD-6 and LM-C1…LM-C3 (§24). Decision records:
[ADR-0045](decisions/ADR-0045.md) (migration, DECIDED) and [ADR-0046](decisions/ADR-0046.md)
(the V1 write boundary, DECIDED). Where a section below and §24 differ, §24 and the ADRs govern. It extends, and does not restate,
[migration-plan.md](migration-plan.md) (strangler, gap analysis, P22 importer, ownership),
ADR-0019 (data ownership during the strangler period), [context-and-knowledge.md](context-and-knowledge.md)
(knowledge lifecycle, supersession, forget), domain-model §1 (three truths, provenance) and
ADR-0012/0013 (knowledge storage).

The user's directive of 2026-09-30 ("legacy Archeus context / memory / lessons migration") is
cited as §1…§24.

## Contents

1. What already exists, and what this adds
2. The phase: P25.5, and why there
3. What is Archeus state and what is project state
4. Preservation inventory
5. The read-only legacy boundary
6. Coexistence and migration states
7. Immutable source snapshot
8. Lossless-first representation
9. Provenance
10. Conflicts
11. Lessons
12. Architecture and ADR history
13. Scope boundary: global, project, worktree, mission, task, execution, session, reference, memory
14. Project compatibility gate
15. Rollback
16. Dry run
17. Completeness gates
18. Dual-read verification
19. Tooling
20. Security
21. Final cutover
22. Traceability
23. Dependencies, amendments, undecided
24. Decision record (2026-10-01)

---

## 1. What already exists, and what this adds

Already decided and kept:

- **Strangler, not big bang** (migration-plan §1, ADR-0001): V1 grows beside the legacy app,
  which keeps shipping.
- **Data ownership** (ADR-0019, migration-plan §5): before cutover the legacy app owns every
  memory, lesson, CLAUDE.md block, rules file, hook and account setting; V1 imports read-only
  snapshots and never writes them; V1 executions are tagged so the legacy app skips them.
- **V1's write boundary** (target-architecture §5.1): as the audit found it, "`ARCHEUS_HOME` plus
  two shared files" — stale against P12 D15, and now stated precisely by ADR-0046 (§24.8).
- **A read-only, idempotent importer** keyed by legacy identity (migration-plan §4, P22), with its
  mapping table, and an export back to legacy formats for 90 days after cutover (§7).
- **Knowledge with provenance and lifecycle**: `source_kind` including `legacy` and `import`,
  CANDIDATE → CONFIRMED → SUPERSEDED / RETRACTED / EXPIRED, `contradicts` relations, forget with
  dry run and tombstones, backup → verify → swap for bulk rewrites (context-and-knowledge §3).
- **Content-addressed artifacts** with verification on read (`archeus/infra/artifacts/store.py`).

What the directive adds, and this document decides:

| Gap in the existing plan | Decided here |
|---|---|
| P22 maps legacy data straight into V1 entities; there is no preserved copy of the source, so a mapping mistake is a loss | a **lossless source layer** (snapshot → source records) under every derived V1 item (§7–§8) |
| no dry run, no manifest, no coverage number | dry run, manifest, completeness gates (§16–§17) |
| cutover sits inside P22, mid-sequence, and is not tied to a user approval | cutover moves to **P25.5** and requires the user (§21) |
| after cutover V1 "writes CLAUDE.md blocks and rules" — files inside the user's projects — with no per-project consent | a project-file write is a **per-project opt-in**, explicit, attributable, reversible (§14, §21) |
| no check that projects are untouched | the **project compatibility gate** (§14) |
| no conflict rule between imported and V1 knowledge | conflicts are relations, never a silent choice (§10) |
| no dual-read | legacy vs V1 comparison without touching the legacy source (§18) |
| the importer is a mapping; nothing explains what it migrated | the migration run record, report and audit log (§19) |

Nothing here changes ADR-0019 before cutover, the V1 write boundary, or any built phase.

## 2. The phase: P25.5, and why there

**P25.5 — Legacy Context and Memory Migration.** A controlled migration and verification phase,
not a feature phase. The identifier follows the plan's convention for inserted phases (P0.5,
P3.5, P19.5); P26 is the release gate and P24/P25 were inserted before it on 2026-09-28, so the
next free identifier before the gate is P25.5. No post-V1 migration phase was reserved.

Why it sits after P25 and before P26:

- **The target must be complete and stable** (§1 of the directive): P23 has run acceptance on the
  finished V1, so the thing being migrated *into* no longer moves.
- **The tooling must be attacked before it runs on real data**: the migration tooling is built in
  **P22** (it extends the importer P22 already owns) and falls under the **P24** whole-application
  audit; P25.5 only *runs* audited tooling.
- **P25** documents the migration runbook with the rest of the manual, so the user reads it
  before the real run.
- **P26 cannot pass while P25.5 is unverified**: P26's release evidence gains "P25.5 closed at its
  gate" and its blockers gain "migration unverified" (§22).

What moves: P22's **ownership cutover** moves to P25.5 (reason: cutover must follow a verified
migration and the user's approval, §21). P22 keeps the importer and gains the tooling (§19).
P25.5 depends on P22 (tooling), P23 (acceptance), P24 (audit) and P25 (runbook).

For other installations after release, P25.5's procedure is what `archeus migrate` does on each
machine, opt-in, per project. **P25.5's acceptance does not require any project to be cut over**
(§24.7): it requires the gates on fixture legacy homes, a full dry run of the user's environment,
and the whole sequence up to — not including — cutover on at least one real project the user
chooses. Which projects are cut over, and when, stays the user's choice.

## 3. What is Archeus state and what is project state

| Class | Definition | Owner | Migration may |
|---|---|---|---|
| **Archeus-owned** | files the legacy app writes for itself outside any project (settings, events, caches, account list) and its per-project workdir `<project>/.archeus/` (gitignored by construction, `*`) | legacy app until cutover, then V1 | snapshot, extract, import; never modify |
| **Archeus-managed blocks in project files** | the machine-maintained blocks the legacy app writes *inside* project files (CLAUDE.md `AUTOGEN`, `SESSIONS`, `ARCHEUS:MEMORY`, `ARCHEUS:AGENTS`; `.claude/rules/archeus-mem-*.md`) | legacy app (writer) inside a **project-owned** file | read only; a V1 writer takes them over only by per-project opt-in at cutover (§21) |
| **Project-owned** | everything else in a project: source, docs (the architecture and ADRs of this repository included), notes, configuration, git history, user-written CLAUDE.md content | the project / the user | read only, by reference; **never** written, moved, renamed, reformatted or annotated by migration |
| **Harness-owned** | transcripts, file history, harness settings and memory under each harness home | the harness | read only; reference by path and hash; never copied wholesale |
| **User configuration** | global instructions the user wrote for a harness (e.g. `~/.claude/CLAUDE.md`) | the user | not migrated as Archeus knowledge; referenced only |
| **Credentials** | account credentials, API keys | the harness / the user | never copied (§20) |
| **V1-owned** | the `ARCHEUS_HOME` entries of target-architecture §5.1, plus the V1-owned entries of the project-local namespace `<project>/.archeus/` (ADR-0046: `sessions/`, `v1-cutover.json`) | V1 | the migration writes only to `ARCHEUS_HOME`; cutover writes only the marker and the approved opt-ins |

**Conflict found (LM-C1).** target-architecture §5.1 said V1 writes only `ARCHEUS_HOME` plus the
two shared files; P12 D15 decided, and V1 builds, per-session delivery copies inside
`<project>/.archeus/sessions/`. Both are inside the gitignored Archeus workdir, never a
project-owned file, so no project file is affected; the sentence is stale, not the code. Resolution
decided 2026-10-01 (ADR-0046): the write boundary is named precisely — `ARCHEUS_HOME`, the
Archeus-owned project-local namespace with per-entry ownership, project-owned files only through
named approved capabilities, and two user-level writes — and target-architecture §5.1 now says so.
No code changes.

The existence of a V1 representation of something never authorises modifying the legacy
representation.

## 4. Preservation inventory

Taken read-only on 2026-09-30 from the legacy code (`claude_sessions/`, file:line) and, for
existence only, the development machine (file names, never contents). Abbreviations: **P** a
project root; **W** `P/.archeus/` (the legacy workdir, `WORKDIR`, `config.py:732`, gitignored `*`
by `config._ensure_dir`, `config.py:737-757`); **C** an account config dir (env
`CLAUDE_CONFIG_DIR` > setting > `~/.claude`, `config.py:816-832`); **S** `~/.claude` (fixed,
`config.py:118`); **PF** `C/projects/<enc>` (the harness's per-project folder; several W stores
are mirrored there: `memory.py:57-63,130-146`, `diffview.py:142-144`, `workspace.py:156-158`).
Owner classes are §3's. Preservation: **copy** = content-addressed copy in the snapshot;
**ref** = reference-only (path + hash, original kept in place — category D of ADR-0045 §9);
**copy** is category A or B by row; **excl** is category C; **redact** = copy with declared
redactions; **excl** = excluded with a reason. Verification: **hash** = re-hash of the snapshot
copy and of the source after the run; **dual** = dual-read (§18); **gate** = compatibility gate
(§14). Loss risk is the risk *if migration were done naively*, which the method answers.

### 4.1 Archeus-owned knowledge and history

| # | Source | Knowledge | Location | Owner | Class | Destination | Preservation | Verification | Loss risk |
|---|---|---|---|---|---|---|---|---|---|
| L1 | memory graph | long-term project memory: entities, relations, summaries, provenance hashes, consolidation state, cost history; **lessons** are entities of `type='lesson'` (pending / approved / pinned) | `W/memory/graph.json` + PF mirror (`memory.py:32-33,130`; `lessons.py:154-179`) | legacy | Archeus-owned, per project | source records per entity/relation/lesson → KnowledgeItem ENTITY / LESSON + Relation (migration-plan §4), project scope | copy (both copies; a mirror that differs is two source records and a conflict) | hash; dual (recall, lessons) | **high** — richest store; lessons and provenance must survive verbatim (§11) |
| L2 | worklog | per-session episodes (implementation history), cap 50 | `W/memory/worklog.json` (`worklog.py:35,44`) | legacy | Archeus-owned | source records → events `legacy.worklog` (history, not knowledge; `events.py:135` reserved) | copy | hash; count | medium (capped: older episodes already gone — the report says so) |
| L3 | recall hits | which memories were used (feeds consolidation ranking) | `W/memory/hits.log` (`recall.py:329-361`) | legacy | Archeus-owned | source records → `hits` / `last_used_at` on the mapped items | copy (byte offset recorded) | hash | low |
| L4 | dirty log | files edited since the last memory build | `W/memory/dirty.log` (`memory.py:823-827`) | legacy | Archeus-owned | source record only (operational; V1 inspection re-derives staleness) | copy | hash | low |
| L5 | snapshots | pre-change copies of CLAUDE.md, system prompt, memory graph — the history of managed context | `W/snapshots/*.prev`, `index.json` + PF mirror (`diffview.py:19,142-167`) | legacy | Archeus-owned | source records (history of L1 and M1); not knowledge | copy | hash | medium (the only record of earlier managed-block and graph versions) |
| L6 | plan | the latest generated plan (current task state) | `W/plan-latest.md` (`plan_execute.py:21,360`); `S/last_plan.json` (`:62`) | legacy | Archeus-owned | Mission + Plan v1, origin `legacy_import` (migration-plan §4) | copy | hash; mission shows the verbatim plan | medium |
| L7 | session log | per-session goal and touched files | `W/session-log.md` (`health.py:130,152`) | legacy | Archeus-owned | source record → history events | copy | hash | low |
| L8 | generated prompts | merged plan / context system prompts | `W/plan-system-prompt.txt`, `W/context-system-prompt.txt` | legacy | Archeus-owned | source records only (regenerated artefacts) | copy | hash | low |
| L9 | injected context | a whole prior transcript handed to a session (hand-off note) | `W/injected-context.md` (`context_inject.py:13,71`) | legacy | Archeus-owned, **sensitive** | source record, not knowledge | **ref** (default; MD-2) | hash | medium (secrets: §20) |
| L10 | bash log | every Bash command run | `W/bash-log.txt` (`logbash_hook.py:74-77`) | legacy | Archeus-owned, **sensitive** | none | **ref** | hash | low as knowledge; **secrets** |
| L11 | denials | blocked tool calls with command and reason (failure / policy lessons) | `W/denied.jsonl` (`automode.py:154,205-210`) | legacy | Archeus-owned, **sensitive** | source records → candidate LESSON evidence only on the user's opt-in | ref (default) | hash | low–medium |
| L12 | connections | import graph cache and rendering | `W/connections-cache.json` (shared, ADR-0019), `W/connections-graph.html` | legacy (shared writer) | Archeus-owned | none (V1 inspection re-derives) | ref | hash | none |
| L13 | workspace manifest | multi-repo workspace definition | `W/workspace-manifest.json` + PF (`workspace.py:29-30,156`) | legacy | Archeus-owned | inspection input / Project root paths | copy | hash | low |
| L14 | settings | preferences, project defaults, launch settings, own-call choice, accounts and homes, provider profiles (**`api_key`**) | `S/archeus.json` (`config.py:118,800`; old `claudectl.json`) | legacy | Archeus-owned, **sensitive** | Account + ResourcePolicy, preferences, defaults (migration-plan §4) | **redact** (keys removed, spans recorded) | hash; account list dual-read | medium |
| L15 | loops | scheduled work | `C/archeus-loops.json` (`loops.py:83,93`) + OS scheduler entries (`loops.py:327`) | legacy | Archeus-owned | Automation, DISABLED (migration-plan §4); OS entries never touched | copy; ref (OS entries) | hash | low |
| L16 | libraries | the user's agent and skill libraries | `S/archeus-agents/`, `S/archeus-skills/` (`config.py:123,129`) | legacy | Archeus-owned | REFERENCE items (skills as offers are V1.x-O5) | copy | hash | low |
| L17 | per-project session metadata | tags, names, per-session agents/providers, custom system prompt, extra dirs, archived transcripts | `PF/tags.json`, `PF/<sid>.name`, `PF/session-*.json`, `PF/system-prompt.txt`, `PF/add-dirs.txt`, `PF/extra-paths.txt`, `PF/archived/` (`sessions.py:306-431`) | legacy (inside a harness folder) | Archeus-owned | Session rows' labels; project STANDARD (system prompt, migration-plan §4) | copy (archived transcripts: ref) | hash | low–medium |
| L18 | caches | stats, repo state, models, versions, activity, limits latch (shared), OmniRoute dead list, automem stamp, last session | `C/archeus-stats-cache.json`, `C/archeus-repostate.json`, `C/archeus-models.json`, `C/archeus-versions.json`, `C/archeus-self.json`, `C/archeus-activity.json`, `S/archeus-limits.json`, `S/omniroute-dead.json`, `S/archeus-automem.stamp`, `C/projects/last-session.json` | legacy | Archeus-owned | none (derived / diagnostic); model list only as catalogue REFERENCE history, never evidence (ADR-0031) | ref | hash | none |
| L19 | events and logs | diagnostic events, update log, proxy log | `S/archeus-events.jsonl` (`events.py:82-88`), `C/archeus-update.log`, `S/failover.log` | legacy | Archeus-owned | not migrated (migration-plan §4: diagnostic) | ref | hash | none |
| L20 | quarantined files | corrupt files moved aside by `jsonstore.load` | `<any>.corrupt-<ts>` (`jsonstore.py:68-80`) | legacy | inherits | reported, never parsed into knowledge | ref | hash | low (listed so a user can recover them) |
| L21 | credentials | account credential store; Claude credentials | `S/archeus-account-creds/`; `C/.credentials.json` (read-only, `usage.py:45-50`) | legacy / harness | **credentials** | **none** | **excl** | absent from every artifact and row | none by design |

### 4.2 Archeus-managed content inside project-owned files

| # | Source | Knowledge | Location | Owner | Class | Destination | Preservation | Verification | Loss risk |
|---|---|---|---|---|---|---|---|---|---|
| M1 | CLAUDE.md / AGENTS.md blocks | current Archeus context injected into sessions: repo commits and README excerpt (`AUTOGEN`), session topics (`SESSIONS`), memory digest (`ARCHEUS:MEMORY`), subagents (`ARCHEUS:AGENTS`), loop (`ARCHEUS:LOOP`), user-pinned `ARCHEUS:KEEP` | `P/CLAUDE.md`, `P/AGENTS.md` (`claude_md.py:103-108,449,458`; markers `config.py:1484-1510`; `harnesses.py:117,215,331,750`) | legacy writer, **project-owned file** | managed block | `KEEP` → STANDARD knowledge (explicit); the rest are regenerated views — source records only | copy of the whole file (block boundaries recorded); **file never written** | hash + gate; dual (render comparison) | medium (KEEP is user-authored) |
| M2 | path-scoped rules | memory digest per module | `P/.claude/rules/archeus-mem-*.md` (`memrules.py:15-151`) | legacy writer, project-owned | managed | source records (regenerated views) | copy; never written | hash + gate | low |
| M3 | installed agents and skills | subagents, skills, their managed manifests | `P/.claude/agents/`, `P/.claude/.archeus-managed.json`, `P/.claude/.archeus-agents.json`, `P/.claude/skills/` (`agents.py:569-777`, `skills.py:94,566`) | project-owned (installed by legacy) | project | REFERENCE (harness configuration of the project) | ref | gate | none |
| M4 | project Claude settings | `permissions.deny`, `outputStyle` | `P/.claude/settings.json` (`denygen.py:75,96`; `outputstyles.py:162,198`) | project-owned | project | none (harness config) | ref | gate | none |
| M5 | project loop prompt | a `/loop` prompt | `P/.claude/loop.md` | project-owned | project | REFERENCE | ref | gate | none |

### 4.3 User and harness configuration

| # | Source | Knowledge | Location | Owner | Class | Destination | Preservation | Verification | Loss risk |
|---|---|---|---|---|---|---|---|---|---|
| U1 | global instructions | the user's global instructions, conventions block, MCP docs | `C/CLAUDE.md` (`conventions.py:221-253`; `mcp.py:179-181`) | the user (legacy writes two blocks) | user configuration | REFERENCE only; never knowledge | ref | gate (user level) | none |
| U2 | hooks, statusline | installed legacy hooks | `C/settings.json` (`hooks.py:22,606,640`) | harness file, legacy entries | user configuration | none before cutover; hook ownership at cutover (§21) | ref | gate (user level) | none |
| H1 | transcripts | session history (the raw source of lessons, `lessons.py:45-62`) | `PF/*.jsonl`; codex `rollout-*.jsonl`, `state_*.sqlite`; pi `sessions/--<cwd>--/*.jsonl` | harness | harness-owned | Session rows referencing them in place (migration-plan §4) | ref | hash of the files cited | none (never moved) |
| H2 | harness state | file history, `.claude.json`, `history.jsonl`, teams, plugins, harness skills/agents/output styles, Claude Code's own memory where present | `C/file-history/`, `C/.claude.json`, `C/history.jsonl`, `C/plugins/` … | harness | harness-owned | none | ref (existence only) | — | none |

### 4.4 Project-owned history the directive names

| # | Source | Knowledge | Location | Owner | Destination | Preservation | Verification | Loss risk |
|---|---|---|---|---|---|---|---|---|
| R1 | architecture and ADRs | decisions, amendments, superseded and rejected alternatives, rationale, phase ownership and status, deferred decisions, known limitations | `docs/architecture/**` (incl. `decisions/`, design gates, reconciliations), `docs/design/**` in this repository | project (git) | REFERENCE / ARCHITECTURE items at `path@commit` (§12) | ref at a commit | reference resolves at its commit | none while git holds it |
| R2 | handoff notes | phase hand-offs, current operational state | `notes/**` — **some untracked** (e.g. `notes/p16-handoff.md`, `notes/p18-handoff.md`, `notes/p19-5-marker-handoff.md`) | project | REFERENCE at a hash | ref (tracked: commit; untracked: hash only) | hash | **medium for untracked notes** — not in git; the report lists them so the user can commit or back them up; migration never touches them |
| R3 | implementation, phase and validation history | commits, as-built records, test and mutation results | git history; `docs/architecture/p*-design-gate.md`; `testing-strategy.md`; CI runs | project | REFERENCE at a commit | ref | resolves | none |
| R4 | design and external references | the design research, rulebooks, external reference audits with their provenance | `docs/design/**`, `docs/research/**`, `docs/architecture/reference/**` | project | REFERENCE at a commit | ref | resolves | none |
| R5 | V1's own knowledge built during development | V1 knowledge, missions, decisions already in `archeus.db` | `ARCHEUS_HOME` | V1 | already V1; the conflict rules (§10) apply between it and L1 | — (V1 backup before import, §15) | integrity check | none |

### 4.5 The directive's knowledge types, located

| Knowledge type | Held in |
|---|---|
| current Archeus context | M1, L6, L9, L17 |
| long-term memory | L1 |
| lessons learned (routing, execution, failure, successful patterns) | L1 (`type='lesson'`), with their transcript sources in H1; L11 (denials) as evidence on opt-in |
| architectural decisions, ADR history, rejected ideas, deferred decisions, known limitations | R1 |
| project-specific knowledge | L1, L13, M1 (`KEEP`), L17 (system prompt) |
| project history, implementation history | L2, L5, L7, R3 |
| handoff notes | R2, L9 |
| current tasks and state | L6; V1 missions (R5) |
| model / provider / harness knowledge | L14 (accounts, profiles), L18 (model list — never evidence), R1 (orchestration docs) |
| user preferences that belong to Archeus | L14 |
| design references, external references and provenance | R4, L16 |
| phase and validation history, test knowledge | R3 |
| operational knowledge | L1, L3, L14, L15, L18 |
| accumulated agent / harness knowledge | L16, M3, L17 |
| the existing memory system | L1–L5, M1, M2 |

## 5. The read-only legacy boundary

```text
LEGACY SOURCE (legacy app stores, <project>/.archeus/, managed blocks, harness homes)
    │  read only: open for reading, never for writing; no lock files; no rename; no mtime change
    ▼
SNAPSHOT            manifest + content-addressed copies (§7) in V1 artifacts/
    ▼
SOURCE RECORDS      one per snapshotted item, verbatim, with provenance (§8)
    ▼
NORMALISATION       pure, versioned transforms → migration candidates (never the only copy)
    ▼
VALIDATION          schema, completeness, conflicts, secrets (§16–§17, §20)
    ▼
V1 KNOWLEDGE/STATE  derived rows with `derived_from` → source record (§9)
    ▼
POST-MIGRATION VERIFICATION   dual-read (§18), compatibility gate (§14)
```

Rules:

1. **The extractor opens sources read-only.** It does not take the legacy app's locks, does not
   call a legacy writer, does not trigger a legacy consolidation, backup rotation or `.corrupt-*`
   move (the legacy `jsonstore.load` moves a corrupt file aside — the extractor must never call it;
   it reads bytes and parses them itself). A file that cannot be read without such a side effect
   is recorded `unreadable-without-mutation` and excluded with its reason; the fix is never to
   modify it.
2. **A consistent read of a live store**: the legacy app is still running. The extractor reads a
   file, hashes it, and re-hashes after reading; a changed hash is retried, then recorded
   `changed-during-snapshot`. Append-only logs are read up to a byte offset that is recorded.
3. **No V1 component outside the migration tool reads a legacy store for migration purposes**
   (the existing scheduled read-only imports of ADR-0019 become snapshot-based runs of the same
   tool).

## 6. Coexistence and migration states

Legacy Archeus, V1 Archeus and the user's projects run side by side until cutover; no project has
to adopt V1, and no repository changes because V1 exists.

**Per migration run** (enters `states.py` / state-machines.md with its implementation in P22):

```text
PLANNED → SNAPSHOTTING → SNAPSHOTTED → DRY_RUN → DRY_RUN_PASSED | DRY_RUN_FAILED
DRY_RUN_PASSED → IMPORTING → IMPORTED → VERIFYING → VERIFIED | FAILED
VERIFIED → CUTOVER_APPROVED (user) → CUT_OVER
IMPORTED | VERIFIED | FAILED | CUT_OVER → ROLLED_BACK
```

**Per project** (a derived answer shown in World → project and Control → About, never a flag the
legacy app reads):

| State | Meaning |
|---|---|
| `legacy` | no snapshot of this project's Archeus state exists; legacy owns everything |
| `in_progress` | a run including this project is between SNAPSHOTTING and VERIFYING |
| `partial` | imported, with source records classified `unsupported`, `excluded` or `conflict` still open |
| `migrated` | imported, every source record accounted for, not yet verified |
| `verified` | the run's verification (§17, §18) and the project compatibility gate (§14) passed |
| `failed` | the run failed; V1 rows of the run are withdrawn (§15); legacy untouched |
| `cut_over` | the user approved cutover for this project (§21); V1 owns what the opt-ins name |

A project's V1-native state (missions created in V1) is independent of its migration state.

## 7. Immutable source snapshot

A snapshot is the only input of every later step. It holds:

- a **manifest** (JSON, keys sorted, stored as a content-addressed artifact): snapshot id
  (sha256 of the canonical manifest), `created_at`, `source_id` (node + legacy app version from its
  own version file + legacy config dir), per item: logical source (§4 row), absolute path,
  size, mtime, sha256, format, parser version, classification (`copied` / `reference-only` /
  `redacted` / `excluded` with reason), and for logs the byte offset read;
- the **migration tool version** and the **migration schema version**;
- the **validation result** of the snapshot itself (every copied blob re-read and re-hashed from
  the artifact store).

Copied content lives in V1 `artifacts/` (already sha256-addressed, verified on read); nothing is
added to `ARCHEUS_HOME`'s entries. Repeatability: transforms are pure functions of (source record,
transform version); V1 row ids are derived from (source identity, transform version), so a second
run over the same snapshot produces byte-identical records and a second run over a *new* snapshot
reports, per item, `unchanged`, `changed` (with both hashes) or `new` / `gone`. A snapshot is never
modified; a new one is taken.

## 8. Lossless-first representation

- **Source record** — one per copied item: the verbatim bytes (in `artifacts/`), plus its manifest
  entry. For structured stores (the memory graph, lessons, worklog, plans) a source record is also
  kept **per logical record** (one entity, one lesson, one worklog entry) as the verbatim JSON
  fragment, so a single lesson can be recovered exactly without re-parsing a whole file.
- **Derived V1 memory** — knowledge items, relations, sessions, missions, automations produced by
  the P22 mapping (migration-plan §4) from source records, each with `derived_from`.
- Summaries, indexes, classifications, deduplication, merged lessons and anything a model writes
  are **derived again** from source records or derived rows — never replacing them. The derived
  representation is never the only copy; a source record is never deleted while any derived row
  or the migration report cites it.
- "Lossless" means: every byte of every `copied` item is recoverable; a `redacted` item records the
  redacted spans (field path, and for a non-secret value its sha256; a secret value records the
  field path only — ADR-0045 §9) so the loss is declared and bounded;
  a `reference-only` item is preserved by the unmodified original plus its recorded hash.

## 9. Provenance

Every migrated row answers "where did this come from?" through a `derived_from` chain ending at a
source record, and every source record carries:

| Field | Meaning |
|---|---|
| `source_kind` | `legacy` (existing value, domain-model §1) |
| `source_ref` | logical source + original path + record key inside it (e.g. lesson id) |
| `snapshot_id` | the snapshot it came from |
| `source_sha256` | of the file, and of the record fragment |
| `extracted_at` | when |
| `migration_run_id`, `tool_version`, `schema_version` | which run and tool |
| `transform` | the named, versioned transform applied (`map.lesson.v1`, `map.graph_entity.v1`, …) and what it changed: renamed fields, re-classified type, mapped state, confidence re-scaled — each as a recorded field diff |
| `observed_at` | the legacy record's own timestamp where it has one (never the import time) |

A transformation that changes wording, structure, classification or confidence is recorded as
such; imported history is never rewritten, and a later edit in V1 creates a new version citing the
migrated one.

## 10. Conflicts

A conflict is a **relation between two live records**, never a silent choice:

| Situation | Result |
|---|---|
| imported item has no V1 counterpart | imported in the lifecycle state the mapping gives (migration-plan §4) |
| imported item equals a V1 item (same type, scope, subject anchor, body hash) | one item; the V1 item gains a second provenance citation |
| imported item conflicts with a V1 CONFIRMED item | imported as **CANDIDATE**, `contradicts` relation to the V1 item, an Attention knowledge proposal; neither is superseded until the user decides |
| two legacy records conflict (the legacy graph's own conflict flag) | both imported, `contradicts` between them, one proposal (migration-plan §4 already) |
| a legacy record the legacy app had superseded or expired | imported as SUPERSEDED / EXPIRED, never dropped |

The directive's states map onto existing ones — *legacy*: `source_kind: legacy`; *current*:
CONFIRMED; *superseded*: SUPERSEDED; *conflicting / unresolved*: a `contradicts` relation with an
open proposal; *deprecated*: EXPIRED or RETRACTED; *verified*: the run's verification record. The
proposal shows what each record says, both sources and their `observed_at`, and why they differ
(field diff); newer is not authoritative by itself — the user decides, and the decision is a
DECISION item citing both.

## 11. Lessons

A lesson is migrated as its **verbatim source record plus** a V1 LESSON item whose body is the
original text, unedited; every legacy field is kept (in the source record, and mapped where V1 has
a field): title, body, status (pending/approved/pinned → CANDIDATE/CONFIRMED/pinned), confidence,
the sessions it came from (`sids` → provenance links to Session rows), hits, first/last used,
decay state, dates, and whatever the legacy lesson records about what happened, what was tried,
what failed and why, and under which conditions. No lesson is summarised, merged or rephrased at
import; a V1 consolidation later may **propose** a merge (context-and-knowledge §3), citing the
originals, which stay. Applicability is re-judged by V1's decay rules only after import, and
expiry is reversible.

## 12. Architecture and ADR history

The architecture history of a project lives in that project — for Archeus itself, in this
repository (`docs/architecture/`, `decisions/`, design gates, `notes/`), with git as its lossless
history. Migration **does not copy or alter it**: it records REFERENCE / ARCHITECTURE items that
point at `path@commit` (with the file's sha256), so decisions, amendments, superseded and rejected
alternatives, rationale, phase ownership and status stay readable exactly where they are, at every
revision. Legacy memory's own architecture-derived entities are migrated like any other record,
citing the same paths.

## 13. Scope boundary

| Scope | Holds | Owner | Lifecycle | Migration rule |
|---|---|---|---|---|
| **Archeus global** (`ws_global`) | the user's cross-project preferences and standards, Archeus's own operational knowledge (routing, harness, model lessons) | V1 (after cutover) | superseded / retracted | only records the legacy app itself held globally; nothing is widened to global on import |
| **Project** (`project_id`) | project facts, entities, lessons, decisions, conventions | the project's knowledge in V1 | lifecycle, decay | legacy per-project memory → this project only |
| **Worktree** | a task's isolated checkout under `worktrees/` | V1 execution | removed after merge / abandon | not migrated (legacy has none) |
| **Mission** | intent, plan versions, checkpoints | V1 | history after completion | a never-launched legacy plan → a CREATED mission, origin `legacy_import`, awaiting confirmation; a launched one → REFERENCE; never COMPLETED (ADR-0045 §11) |
| **Task** | contract, state | V1 | with its mission | none |
| **Execution** | one attempt, its record | V1 | history | **none**: no legacy session becomes an Execution (ADR-0045 §11, P12 D2) |
| **Session** | the harness's conversation | the harness | the harness's | every legacy session in scope → a Session row, mode `manual`, referencing its transcript in place |
| **Reference** | external material with provenance, and project files cited at a revision | its owner | pinned to a revision | reference, never copy |
| **Memory / lesson** | knowledge items at one of the scopes above | V1 | context-and-knowledge §3 | keeps its source scope |

A project-specific fact never becomes global memory by migration; promotion to a wider scope is a
separate, user-visible act. A global lesson reaches a project's context only through the context
engine's scope rules, never by being copied into the project.

## 14. Project compatibility gate

**Hard gate, before V1 is declared complete (P26) and before any cutover:** every existing project
is usable exactly as before unless the user opted that project into a migration change.

Method — **manifests, not memory**:

1. At the first P25.5 dry run, take a **project baseline manifest** for every known project: every
   path under its root paths (`.git/` summarised as `HEAD`, refs, index hash, `git status
   --porcelain` and `git worktree list`), with size, mtime and sha256 — read only.
2. After import, verification and each rollback drill, take the manifest again and diff.
3. **Every difference must be attributed** to exactly one of: the user (outside Archeus); the
   legacy app (its own normal writers — it keeps running); an approved V1 mission (a merged,
   verified change with its Execution and merge record; its worktrees and branches); the two shared
   files of ADR-0019 through their legacy functions; or a per-project opt-in change approved for
   this run; V1's own files inside a project's Archeus workdir (§3: P12 D15 delivery copies).
**An unattributed difference fails the gate.** V1 itself records every write it makes
   outside `ARCHEUS_HOME` in its audit log, which is what makes attribution mechanical.
4. The gate also checks: project configuration and project-local memory unchanged by migration; no
   V1 metadata injected into any project file; the legacy app still opens each project, its memory,
   lessons and CLAUDE.md blocks read as before; the project's own tools and workflows (its test
   command, git operations, the legacy launcher) still run.

**Coverage over time.** A manifest can only show differences after it was taken. So: the P22
tool can take a baseline at any time, read only, and one is recommended as soon as P22 lands, so
everything from P22 to P25.5 is covered by manifests; before that, the guarantee rests on V1's
design — it writes nothing into a project except the named seams — held by the static gate MG-12.

A legitimate project change (a per-project opt-in at cutover) is explicit (named in the cutover
plan), attributable (recorded with its run), reversible (pre-change copy + hash kept) and
separately approved.

## 15. Rollback

Rollback never reconstructs the old state from memory: the source is never modified, so the
legacy environment *is* the rollback target.

| Element | Design |
|---|---|
| checkpoint | before IMPORTING: a V1 database backup (existing `backups/`) and the run id; before CUT_OVER: the list of opt-in project changes with each file's pre-change copy and hash |
| triggers | a failed gate (§14, §17), a failed dual-read (§18), the user's command, or a failure during import |
| procedure before cutover | withdraw the run: every V1 row with that `migration_run_id` is retracted (tombstone with provenance, as `knowledge.forget(mode=purge)`); snapshot and source records are kept for diagnosis; legacy untouched, nothing to restore |
| procedure after cutover | re-enable the legacy writers; restore each opt-in project file from its pre-change copy (verified by hash; git-tracked files additionally by `git diff` against the recorded commit); `archeus migrate --export-legacy` (migration-plan §7) re-emits legacy formats including knowledge created in V1 since |
| V1-native state | missions, knowledge and decisions created in V1 are **kept** across a rollback; only rows derived from the run are withdrawn; a V1-native item that cites a withdrawn row keeps a dangling-provenance marker, shown |
| partial records | an interrupted import leaves rows marked with their run in IMPORTING; rollback withdraws them all; a re-run is idempotent |
| validation after rollback | the compatibility gate (§14) passes; the V1 database is consistent (integrity check, no row cites a missing run); the legacy app's own reads return the baseline |

The gate requires a rollback **demonstrated** on fixtures and on a copy of the user's environment
before the real cutover.

## 16. Dry run

P25.5 begins with a dry run: snapshot and transform into an **isolated scratch database**; no
source mutation, no project mutation, no deletion, no overwrite, no write to the live V1 database.
It produces the migration report (§19) with: the inventory; the manifest; conflicts; missing
sources (an inventory row with no file); unsupported formats and parse failures; secrets found and
their handling; estimated migration coverage (records mapped / records found, per source);
preservation coverage (bytes copied or referenced / bytes found); unresolved items. A real import is
considered only after the dry run passes §17's gates on the scratch database and the user has read
the report.

## 17. Completeness gates

| Gate | Threshold |
|---|---|
| accounted | 100% of identified source records appear in the manifest |
| classified | 100% are `migrated`, `reference-only`, `redacted` or `excluded` — each exclusion with a reason |
| silent losses | 0: every source record is cited by a derived row or by the report |
| conflicts | 0 unexplained: every conflict is a relation with an open or decided proposal |
| provenance | 100% of migrated rows reach a source record |
| project files | the compatibility gate (§14) passes |
| rollback | demonstrated (§15) |
| determinism | a re-run over the same snapshot is byte-identical |
| readable | every migrated row passes V1's schema and appears in V1 reads (context, knowledge, missions) |
| recoverable | every source record re-reads to its recorded hash; the legacy source still opens in the legacy app |

Anything that cannot be migrated appears in the report; nothing is omitted silently.

## 18. Dual-read verification

After import and before cutover, without changing the legacy source, compare for every project:

| Compared | Legacy side | V1 side | Detects |
|---|---|---|---|
| memory recall | `recall` (BM25 over the legacy graph) for a fixed query set: each entity name, lesson title and module name of the project | the V1 context package for the same queries | missing memories, wrong associations |
| lessons | the legacy lesson list with statuses | V1 LESSON items with states | lost or mis-stated lessons |
| scope | the legacy project each record lived in | the V1 project scope | changed project scope |
| provenance | legacy session ids and sources | V1 provenance links | altered provenance |
| injected context | the CLAUDE.md block and rules the legacy app would write, rendered to memory | the V1 rendering of the same blocks, rendered to memory — neither written | context regressions |
| routing inputs | legacy account list, priorities and limits | V1 accounts and policies | routing regressions |

Differences are reported, classified (expected by the mapping / regression) and must be explained
before VERIFIED. V1 is never preferred because it is newer.

## 19. Tooling

Built in **P22** (extending `legacy/importers.py`), audited in **P24**, run in **P25.5**. One CLI
(`archeus migrate`, a V1 verb; no legacy seam) with subcommands: `inventory`, `snapshot`,
`dry-run`, `diff <snapshot> <snapshot>`, `import`, `verify` (gates + dual-read), `report`,
`rollback <run>`, `export-legacy`. Properties:

- **independently testable**: transforms are pure functions over source records; the tool runs
  against fixture legacy homes (the existing P22 fixtures: multi-account, codex, pi) without Core
  running;
- **explains itself**: every run writes a report artifact (inventory, manifest, coverage,
  conflicts, exclusions, secrets handling, diffs, gate results) and `migration.*` events (the audit
  log); `archeus migrate report <run>` answers "what did you migrate, from where, and what did you
  leave?";
- **commands through Core**: the import writes V1 rows through the ordinary writer and commands
  (single writer, outbox, ADR-0002), under the user device principal that started it — no side door
  into the database.

## 20. Security

- The migration runs under the existing authorisation: `admin` scope from a user device; P9
  policy, P10 account protections, P11 execution boundaries, P13 verification and P15 device
  controls are unchanged; the tool is audited in P24 with the cross-phase question below.
- **Credentials are never copied**: account credential stores (e.g. the legacy account-credential
  file), API keys in settings or in harness config are `excluded` or `redacted` in the snapshot and
  never enter knowledge; accounts stay node-bound (domain-model §8.2).
- **Sensitive content** — command logs (`bash-log.txt`), injected transcripts
  (`injected-context.md`), transcripts, paste caches — is `reference-only` by default: preserved in
  place and hashed, not copied into `artifacts/`, not turned into knowledge; a user may opt a
  source in, and a secret scan (the same patterns the legacy redactors use) runs over anything
  copied, turning hits into `redacted` spans.
- Project boundaries: a source record is scoped to the project it came from; the data class of that
  project (ADR-0035) applies to anything derived from it and to any model call over it (e.g. a later
  consolidation).
- **P24 cross-phase question added:** "can the migration tool write to a legacy store or a project
  file, copy a credential, widen a record's scope, or run without an `admin` user-device principal?"
  — no, by construction.

## 21. Final cutover

Only after all of: V1 implementation complete (P23, P24, P25 closed); dry run passed; coverage
verified (§17); the project compatibility gate passed (§14); rollback demonstrated (§15);
provenance checks passed; dual-read verified (§18); every unresolved item explicitly accepted by
the user in the report; and **the user approves the cutover of that project** — cutover is per
project, never for all at once (ADR-0045 §12).

Cutover then does exactly what ADR-0019 describes for "after cutover" — V1 knowledge becomes the
source and the legacy memory writers stand down — **for that project only**, signalled by the
per-project marker `<project>/.archeus/v1-cutover.json` (ADR-0046) which the legacy writers and
hooks check (the P22 legacy seam) — **plus** a per-project list of opt-ins, each separately
approved: take over the managed blocks in CLAUDE.md / AGENTS.md, take over
`.claude/rules/archeus-mem-*`, and (on the first project cut over on an account) add V1's hook
entries beside the legacy ones in that account's `settings.json`; both hooks consult the marker, so
each acts only for the projects it owns. A project with no
opt-in keeps its files exactly as the legacy app last wrote them. The migration is **never** an
automatic side effect of an ordinary V1 update: no upgrade, restart or scheduled job starts a run
or a cutover.

## 22. Traceability

| # | Requirement (directive §) | Architectural decision | Phase | Implementation owner | Test / gate | Final validation |
|---|---|---|---|---|---|---|
| M-1 | final migration phase (§1) | P25.5 after P25, before P26 | P25.5 | — | P26 evidence "P25.5 closed" | P26 |
| M-2 | preservation inventory (§2) | §4, every row with destination, method, verification, risk | P22 (tool), P25.5 (run) | migration tool `inventory` | inventory completeness | report reviewed by the user |
| M-3 | project files sacrosanct (§3) | read-only boundary; V1 write boundary; opt-in only | all phases; P25.5 | tool, Core writer audit | compatibility gate MG-6; static write-boundary gate MG-12 | P25.5, P26 |
| M-4 | read-only legacy boundary (§4) | §5 pipeline and rules | P22 | extractor | MG-1 read-only (source hashes and mtimes unchanged by a run) | P25.5 |
| M-5 | coexistence, states (§5) | §6 run and project states | P22 | tool + World/Control reads | state table tests | P25.5 |
| M-6 | immutable snapshot (§6) | §7 manifest, hashes, versions | P22 | `snapshot` | MG-2 determinism | P25.5 |
| M-7 | lossless-first (§7) | §8 source records under derived rows | P22 | transforms | MG-3 losslessness (every copied byte recoverable) | P25.5 |
| M-8 | provenance (§8) | §9 fields; `derived_from` | P22 | transforms | MG-4 provenance coverage 100% | P25.5 |
| M-9 | conflicts (§9) | §10 relations + proposals | P22 | import | MG-5 no silent choice | P25.5 |
| M-10 | lessons (§10) | §11 verbatim + mapped | P22 | `map.lesson` | MG-3, dual-read lessons | P25.5 |
| M-11 | ADR history (§11) | §12 reference at revision | P22 | `map.reference` | reference resolves at its commit | P25.5 |
| M-12 | scope boundary (§12) | §13 table; no widening | P22 | transforms | MG-7 scope preserved | P25.5 |
| M-13 | project compatibility gate (§13) | §14 manifests + attribution | P25.5 (gate), P22 (tool) | `verify` | MG-6 | P26 blocker |
| M-14 | rollback (§14) | §15 | P22 (tool), P25.5 (drill) | `rollback` | MG-8 rollback demonstrated | P25.5 |
| M-15 | dry run (§15) | §16 scratch database | P25.5 | `dry-run` | MG-9 dry run writes nothing live | P25.5 |
| M-16 | completeness (§16) | §17 gates | P25.5 | `verify` | the §17 table | P26 |
| M-17 | dual-read (§17) | §18 | P25.5 | `verify` | dual-read report explained | P25.5 |
| M-18 | tooling (§18) | §19 | P22, P24 | `archeus migrate` | fixture-home suite; mutation-verified | P24 audit |
| M-19 | security (§19) | §20 | P22, P24 | tool | MG-10 no credential in any artifact or row | P24, P25.5 |
| M-20 | final cutover (§20) | §21; user approval | P25.5 | `cutover` (with the user) | MG-11 no run or cutover without the user's command | P26 |
| M-21 | ADRs and documents (§21) | ADR-0045; this document | now | — | documentation gates | P25 |
| M-22 | cannot declare V1 complete while unverified (§22) | P26 evidence + blocker | P26 | — | P26 checklist | P26 |

Gates MG-1…MG-18 are listed in testing-strategy §9.

## 23. Dependencies, amendments, undecided

**Depends on:** P2 (artifacts, backups, single writer), P6 (knowledge lifecycle, provenance), P7
(missions for imported plans), P9 (authorisation, `admin`), P12 (sessions), P14 (automations for
imported loops), P21 (audit and trace views to show runs), P22 (importer and tooling), P23
(acceptance of the target), P24 (audit of the tooling), P25 (runbook).

**Amended (2026-10-01):** plan §31.1 (P22 loses "ownership cutover" and gains the tooling and
the legacy marker seam; P25.5; P26 evidence and blockers), §31.3; migration-plan §4 (sessions and
plans rows; mapping from source records), §5 (per-project cutover, marker, write boundary), §7;
target-architecture §2 (principle 9) and §5.1 (the write boundary, ADR-0046); testing-strategy §9.
ADR-0019's rules before a project's cutover are unchanged; its "after cutover" now applies per
project.

**Decided 2026-10-01:** MD-1…MD-6 — see §24. Nothing of the original list remains open except the
legacy app's retirement date, which §24.5 deliberately leaves to a later user decision.

## 24. Decision record (2026-10-01)

The user's decision pass on this architecture. Records: [ADR-0045](decisions/ADR-0045.md)
(DECIDED) and [ADR-0046](decisions/ADR-0046.md) (DECIDED).

### 24.1 The hard invariant — existing project safety during V1 development

> **V1 development ≠ migration ≠ project cutover.** An existing project keeps working on the
> legacy system while V1 is built, and for as long as it is not cut over. The existence or
> development of V1 never requires a project to be migrated, rewritten, restructured or converted,
> and migration is never a prerequisite for normal work on a project. Until *that project's*
> approved cutover, migration leaves its files, legacy context, legacy memory, CLAUDE.md / AGENTS.md
> / rules, harness configuration and git state untouched and usable; V1 may coexist without forcing
> conversion. After its cutover, every change is attributable and has provenance, its project-owned
> files pass the compatibility gate, rollback has been demonstrated, and legacy recovery stays
> available for its rollback window.

It is ADR-0045 §1 and target-architecture §2 principle 9.

### 24.2 MD-1 — ADR-0045: DECIDED

The proposed record preserved every property the decision pass named (read-only extraction,
immutable snapshots, verbatim sources, provenance, deterministic re-runs, conflict preservation,
rollback, dual-read, project compatibility, 100% accounting, no credential copying, explicit
cutover). Five seams were missing or wrong, and each was closed from existing architecture rather
than invented:

| Gap | Closed by |
|---|---|
| cutover could be "for all"; no mechanism kept legacy and V1 from both writing a project | per-project cutover and the marker (LM-C2, §24.5) |
| a run was not keyed to project identity and had no fail-closed rule | ADR-0045 §8 |
| migration-plan §4 turned legacy sessions into manual Executions, which P12 D2 forbids | ADR-0045 §11 (MD-3) |
| a launched legacy plan was imported as COMPLETED, asserting a review that never happened | ADR-0045 §11 (LM-C3) |
| a redaction recorded the sha256 of a secret | ADR-0045 §9: path only for secrets |

### 24.3 MD-2 — sensitive sources: four categories, reference-only by default

| Category | Meaning | Inventory rows |
|---|---|---|
| **A** usable V1 knowledge | derived rows usable as context under the project's data class | L1, L6 (plan text), L13, L14 (non-secret fields), L15, L16, L17 (labels, system prompt), M1 (`ARCHEUS:KEEP` only) |
| **B** preserved source record, never ordinary context | copied and hashed; shown in reports and provenance; never in a context package | L2 (as history events), L3, L4, L5, L7, L8, M1 and M2 (the regenerated blocks) |
| **C** excluded entirely | never copied; a secret inside a copied file becomes "redacted at field path P", with no hash | L21; the `api_key` / token fields of L14; any secret-scan hit |
| **D** hash, manifest and provenance only (the default for sensitive operational records) | the original stays in place; Archeus keeps path, size, mtime, hash | L9, L10, L11, H1 (and archived transcripts), L12, L18, L19, L20, M3–M5, U1, U2, H2, R1–R4 (at a commit or hash) |

Exception: D → B only, per source and per project, by an `admin` user-device command, after a
secret scan whose hits become declared redactions, under the project's data class, recorded on the
run. Never C → anything; never D → A directly.

### 24.4 MD-3 — legacy sessions: none become Executions

An Execution is work Archeus drove under P9/P10, and its schema requires a task and a mission (P12
D2); a legacy session was driven by the user. So every legacy session of a project in scope
becomes a **Session** row, mode `manual`, through P12's registration path: identity = (harness,
account config dir, provider session id); id derived deterministically from it; transcript
referenced in place (category D); state as the harness records it. An incomplete, open or
unreadable session is a Session row marked so, or a report entry — never dropped. No age window
applies: a Session row is an index entry, so preserving all of them costs nothing and invents
nothing. migration-plan §4's "manual Executions for the last 90 days" is withdrawn.

### 24.5 MD-4 — cutover is per project

Lifecycle, per project: `legacy → dry run → snapshot → validation → dual-read → compatibility
gate → explicit user approval → V1 cutover → monitored coexistence (rollback window) → legacy
retired for that project`. There is no global migration flag or mode. **Coexistence model — all
four at once are valid:**

| Project | State | Who owns its Archeus state | Marker `.archeus/v1-cutover.json` | Legacy writers / hooks | V1 hooks | Recovery material |
|---|---|---|---|---|---|---|
| A | V1 (window closed) | V1 | present | stand down | act | deleted only if the user chose to |
| B | legacy | legacy | absent | act as today | do nothing | — |
| C | migration pending (snapshot / dry run / import / verify) | legacy | absent | act as today | do nothing | the run's V1 rows, only in `ARCHEUS_HOME` |
| D | V1 + rollback window | V1 | present | stand down | act | snapshot + deterministic legacy export, retained |

The marker is the only per-project signal both applications read: the legacy writers (memory,
lessons, worklog, CLAUDE.md / AGENTS.md blocks, rules) and account hooks stand down only where it is
present; V1's hooks act only where it is present. It is a legacy seam built in P22 with the tooling
(LM-C2). A run over project A cannot touch project B: scope is explicit project identities and fails
closed (ADR-0045 §8).

### 24.6 MD-5 — retirement is separate and explicit

Per project: when the user closes its rollback window (§24.7). Of the legacy app: only when
migration-plan §6's retirement checklist passes **and** every known project is either retired from
legacy or explicitly left on it by the user — and only by the user's decision. **No date is set.**
The legacy app stays available during V1 development and for every project not cut over; P26 does
not require it to retire, and no retirement can invalidate an unmigrated project.

### 24.7 MD-6 — recovery material and its retention

| Question | Answer |
|---|---|
| what | the immutable snapshot (exact source bytes) + a legacy-format export (memory graph with lessons, worklog, managed-block renderings) of the project's V1 state |
| deterministic? | yes: a versioned exporter over V1 state at a recorded event sequence; same inputs, same bytes |
| verified how | hash, and a parse of the export in a scratch directory against the legacy formats (never in the project) |
| where | `ARCHEUS_HOME/artifacts/`; written into the project only when a rollback is executed |
| how long | the project's rollback window: **at least 90 days** (ADR-0019), **no automatic expiry** |
| when deleted | only by an explicit user command after the user closed the window |
| still dependent on legacy tooling? | the window cannot be closed; the material stays |

### 24.8 LM-C1…LM-C3

- **LM-C1** (write boundary) — resolved by **ADR-0046**: `ARCHEUS_HOME`; the Archeus-owned
  project-local namespace `<project>/.archeus/` with per-entry ownership (V1 owns `sessions/` and
  `v1-cutover.json`; `connections-cache.json` shared through its legacy function; the directory,
  its `.gitignore` and everything else legacy's); project-owned files and git state only through
  three named capabilities (task worktree, verified merge, cutover opt-in); user-level writes only
  the shared latch and, at cutover, V1's hook entries. target-architecture §5.1 now states it.
- **LM-C2** (per-project cutover mechanism) — the marker and the legacy seam, §24.5.
- **LM-C3** (a legacy plan imported as COMPLETED) — a never-launched plan becomes a CREATED mission
  with origin `legacy_import` awaiting confirmation; a launched one a REFERENCE item.

### 24.9 The fourteen required gates

| # | Gate | Where |
|---|---|---|
| 1 | per-project isolation | **MG-13** (new) |
| 2 | legacy-project non-interference | **MG-14** (new) |
| 3 | no arbitrary project-file writes | MG-12 (static) + MG-6 |
| 4 | deterministic snapshot | MG-2 |
| 5 | 100% source accounting | **MG-15** (new; the §17 table as a gate) |
| 6 | provenance | MG-4 |
| 7 | conflict preservation | MG-5 |
| 8 | rollback | MG-8 |
| 9 | dual-read | **MG-16** (new; §18 as a gate) |
| 10 | sensitive-data handling | MG-10 (extended to categories A–D) |
| 11 | coexistence of legacy and V1 projects | **MG-17** (new) |
| 12 | unattributed project change detection | MG-6 |
| 13 | cutover requires explicit approval | MG-11 |
| 14 | unmigrated projects remain fully operational | **MG-18** (new) |

### 24.10 P25.5 acceptance (revised)

The gates MG-1…MG-18 pass on the fixture legacy homes, including a four-project coexistence
fixture; a full dry run over the user's real environment passes (read only, 100% accounted); and the
sequence up to cutover — import, dual-read, compatibility gate, rollback drill — passes on at least
one real project the user chooses. **No cutover is required for acceptance.** P26 requires P25.5
closed and every known project in an explicit, recorded migration state.

### 24.11 Before P25.5 implementation may begin

P25.5 is a run of tooling, so "implementation" means two things with different preconditions.

**The P22 tooling** (fixture legacy homes only, never the user's real stores) may begin when: P21
is closed and P22 has started under its own design gate; that design gate carries this document's
tool design, MG-1…MG-18 and the legacy marker seam; and the user approves that gate.

**The P25.5 run** on the user's environment may begin only when all of: P22 tooling built with
MG-1…MG-18 mutation-verified; P23 closed (acceptance of the target); P24 closed with the tooling in
its scope and no open High finding; P25 closed (the runbook published); the ADR-0046 static gate
green on the release candidate; the user has read the dry-run plan; and the user issues the
command. Nothing in this pass authorises any of it.
