# Archeus V1 — Legacy context and memory migration (P25.5)

Status: **DECIDED — architecture only; nothing is migrated, no tool exists, and no project file,
repository, memory store, Core, API or UI was changed to produce it.** Written 2026-09-30 on
`archeus-v1-rearchitecture` at `c94e026` (`e9d5681`); the user's decision pass of 2026-10-01
resolved MD-1…MD-6 and LM-C1…LM-C3 (§24); a validation pass the same day corrected MD-3, MD-5
and MD-6 and strengthened the compatibility gate and rollback (§25). Decision records:
[ADR-0045](decisions/ADR-0045.md) (migration, DECIDED) and [ADR-0046](decisions/ADR-0046.md)
(the V1 write boundary, DECIDED). Where sections differ, §25 governs, then §24 and the ADRs. It extends, and does not restate,
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
25. Architecture validation (2026-10-01, second pass)

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
| **Session** | the harness's conversation | the harness | the harness's | preserved as manifest entries; a Session row (mode `manual`) only by the user's action or an explicit per-run rule (§25.3) |
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

Gates MG-1…MG-19 are listed in testing-strategy §9.

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

*Corrected by §25.3: historical sessions stay source material; a Session row only by the user's
action or an explicit per-run rule.*

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

*Corrected by §25.4: the legacy app retires only by a release decision after P25.5, never while a
project still works through it.*

Per project: when the user closes its rollback window (§24.7). Of the legacy app: only when
migration-plan §6's retirement checklist passes **and** every known project is either retired from
legacy or explicitly left on it by the user — and only by the user's decision. **No date is set.**
The legacy app stays available during V1 development and for every project not cut over; P26 does
not require it to retire, and no retirement can invalidate an unmigrated project.

### 24.7 MD-6 — recovery material and its retention

*Corrected by §25.5: retention configurable per project above the ADR-0019 floor; the exporter
itself removed only by a release decision.*

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

The gates MG-1…MG-19 pass on the fixture legacy homes, including a four-project coexistence
fixture; a full dry run over the user's real environment passes (read only, 100% accounted); and the
sequence up to cutover — import, dual-read, compatibility gate, rollback drill — passes on at least
one real project the user chooses. **No cutover is required for acceptance.** P26 requires P25.5
closed and every known project in an explicit, recorded migration state.

### 24.11 Before P25.5 implementation may begin

P25.5 is a run of tooling, so "implementation" means two things with different preconditions.

**The P22 tooling** (fixture legacy homes only, never the user's real stores) may begin when: P21
is closed and P22 has started under its own design gate; that design gate carries this document's
tool design, MG-1…MG-19 and the legacy marker seam; and the user approves that gate.

**The P25.5 run** on the user's environment may begin only when all of: P22 tooling built with
MG-1…MG-19 mutation-verified; P23 closed (acceptance of the target); P24 closed with the tooling in
its scope and no open High finding; P25 closed (the runbook published); the ADR-0046 static gate
green on the release candidate; the user has read the dry-run plan; and the user issues the
command. Nothing in this pass authorises any of it.

## 25. Architecture validation (2026-10-01, second pass)

A validation of this document, ADR-0045, ADR-0046 and the orchestration decisions against the
user's validation brief of 2026-10-01. Verified at `d4bc009` (the brief named `e9d5681`; the
repository is authoritative). No hard stop condition was met: every legacy source can be read
without mutation (a SQLite store such as Codex's `state_*.sqlite` is category D — its bytes are
hashed, it is never opened as a database); every project-file ownership boundary is established by
ADR-0046; rollback never needs to overwrite user data (§25.7); V1 modifies no project before its
cutover; every provenance link is preservable. Three earlier decisions are **corrected** here
(§25.3–§25.5) and govern where §24 differs.

### 25.1 The cutover sequence, per project

1. **freeze input** — the snapshot's manifest fixes the exact bytes and log offsets read; later
   legacy writes are the next snapshot's, never this run's;
2. **immutable snapshot**; 3. **extract** into source records; 4. **transform** (named, versioned,
   pure); 5. **validate** (schema, categories, secrets, conflicts); 6. **dual-read** (§18);
7. **completeness** (§17, MG-15); 8. **project compatibility** (§14, strengthened in §25.6);
9. **rollback demonstrated** on this project's copy (§15, §25.7); 10. **the user's explicit
   authorisation**, per project, with the non-rollbackable register (§25.7) shown; 11. **cut over
   that project only** (marker + approved opt-ins); 12. **keep rollback and export** (§25.5);
13. **observe** — the rollback window, with dual-read repeatable on demand; 14. **close the
   migration of that project** only after verification and only by the user.

**Any failed gate: no cutover**, the project stays on legacy, and its legacy source stays exactly as
it was. One project failing never blocks another.

### 25.2 Dual-run: who may write what until a project's cutover

| Actor | Reads | Writes |
|---|---|---|
| legacy app | its stores | its stores — unchanged behaviour |
| V1 | V1 state; legacy stores read only (inspection, imports) | inside ADR-0046 only; the **only** V1 writes into legacy-owned files are the two ADR-0019 shared files, through the legacy app's own functions — declared, never hidden |
| migration tooling | legacy stores, read only | `ARCHEUS_HOME` only (snapshot, source records, V1 rows, reports) |
| dual-read | both sides | nothing but its report; legacy-side reads use the legacy formats on the snapshot, and rendered blocks are rendered in memory |

No write-through from V1 or from the tooling into legacy exists beyond the two declared files; MG-1
(tooling), MG-14 (V1) and MG-16 (dual-read) hold it.

### 25.3 MD-3 corrected — sessions stay source material unless a defined rule applies

§24.4 made every legacy session a Session row. That imports records whose meaning to V1 has not
been shown, which the brief rules out. Four classes, each handled differently:

| Class | Examples | Becomes |
|---|---|---|
| historical knowledge | lessons, entities, decisions, `KEEP` blocks | V1 knowledge (category A), with provenance to the session it came from |
| historical sessions | transcripts of past sessions | **preserved source material**: a manifest entry with identity (harness, account config dir, provider session id), path, size and hash (category D); no V1 row |
| currently active / relevant sessions | a session the user resumes, hands off or registers | a **Session** row, mode `manual`, through P12's registration path — created by the user's action at any time, never by the migration's choice |
| operational logs | bash log, denials, events | category D |

A session may become a Session row during a migration run only through an **explicit,
configurable, per-run rule** the user sets (`sessions: none | listed | window <from>…<to>`, default
`none`), recorded in the run. No session becomes an Execution for any reason (P12 D2), and none
becomes a Session row merely because of its date. A lesson's `sids` link to the manifest entries of
those sessions, so provenance is kept without any Session row.

### 25.4 MD-5 corrected — retiring the legacy app is a separate release decision after P25.5

§24.6 allowed retirement while a project was "explicitly left on legacy", which would break that
project. Corrected: the legacy app retires only by the user's **explicit release decision after
P25.5**, and only when every project the user names as required has, independently, passed
migration, demonstrated rollback, had its dual-read differences explained, passed its compatibility
gate and had its legacy export verified; every other project is either cut over too, or explicitly
declared by the user as no longer needing Archeus — its legacy state then stays preserved in place
and in a snapshot. While any project still works through the legacy app, the legacy app does not
retire.

### 25.5 MD-6 corrected — retention is configurable, with an existing floor

The architecture already defines one number: ADR-0019's "export back to legacy formats for 90 days
after cutover". That is kept as the **floor**, not invented here. Retention of a project's recovery
material is **configurable per project** at or above it, never expires by itself, and ends only by
the user closing the window. Separately, the **export capability** itself (the exporter in V1) is
removed only by an explicit release decision, never because a period elapsed. During retention the
snapshot plus the export are enough to reconstruct the legacy representation (§25.7 names what the
export cannot carry).

### 25.6 Project compatibility gate, strengthened

Detected, per project, in the before/after manifests: git `HEAD`, every ref, the index hash, every
tracked file, every untracked file, ignored files where practical (by path, size and hash; large
generated trees summarised by a directory hash), `CLAUDE.md`, `AGENTS.md`, `.claude/rules/`,
`.claude/settings.json` and the rest of `.claude/`, every entry of `.archeus/` (legacy-owned and
V1-owned separately), the harness session folders of the project, and `git worktree list`.

Every change is attributed to exactly one owner, **by positive evidence only**:

| Owner | Evidence |
|---|---|
| **V1 change** | an entry in V1's write ledger (ADR-0046: every write outside `ARCHEUS_HOME` is logged) |
| **approved mission change** | an Execution with its verified merge or worktree record |
| **migration change** | an entry in the migration run's write ledger — before cutover this can only be `ARCHEUS_HOME`, so any project change claiming it fails |
| **legacy change** | a change only inside a legacy-owned region: a legacy entry of `.archeus/`, the inside of a managed block's markers, a legacy-owned harness file |
| **user change** | anything else — **presumptive**: listed for the user to confirm; on fixture homes, where no user acts, a presumptive user change **fails** the gate |

**A change is never attributed to the migration because it happened during a migration run.** An
unattributed or unconfirmed change fails the gate.

### 25.7 Rollback, and the non-rollbackable register

Rollback restores legacy compatibility, keeps every V1-native record and all migration provenance,
restores opt-in project files from their verified pre-change copies, re-enables the legacy writers
(removes the marker) and re-emits legacy formats where supported. It **never blindly overwrites a
newer user change**: a file is restored only if its current hash equals the hash V1 last wrote;
otherwise the three versions (pre-change, V1's, current) are shown and the user decides.

Artifacts whose rollback is not complete are listed in a **non-rollbackable register** shown before
the cutover authorisation (§25.1 step 10), which the user must accept explicitly:

| Artifact | Limit |
|---|---|
| V1-native knowledge created after cutover | re-emitted only in the fields the legacy format has (no lifecycle state history, no V1 provenance beyond a source note); the rest stays in V1 |
| missions run in V1 after cutover | their merged code stays in the user's git history (the user's work, not migration state); the legacy app has no representation of a mission |
| a legacy loop and its imported V1 automation | the automation is imported DISABLED and stays so until the user stops the legacy loop, so the two never both run; rollback leaves the legacy loop as the user left it |

Nothing outside this register is non-rollbackable.

### 25.8 The preservation matrix, completed

§4 gives, per source, the owner class, location, destination, method, verification and loss risk.
The remaining columns the brief names — scope, current format, target representation,
transformation, provenance key and fallback — are these, keyed by §4's ids:

| Id | Scope | Format | Target V1 representation | Transformation | Provenance key | Fallback if the transform fails |
|---|---|---|---|---|---|---|
| L1 | project | JSON graph | KnowledgeItem ENTITY / LESSON, Relation | `map.graph.v1`, `map.lesson.v1` | project, file, entity id | source record kept; items `unsupported`; project `partial`; no cutover without acceptance |
| L2 | project | JSON list | history events `legacy.worklog` | `map.worklog.v1` | project, file, entry index + timestamp | source record kept |
| L3 | project | text log | `hits` / `last_used_at` on mapped items | `map.hits.v1` | file, byte range | source record kept; counters left at 0 and flagged |
| L4, L7, L8 | project | text | none (category B) | `copy.v1` | file, hash | — |
| L5 | project | text copies + index | none (category B, history of L1 and M1) | `copy.v1` | file, timestamp in name | — |
| L6 | project | markdown | CREATED mission awaiting confirmation (never launched) or REFERENCE (launched) | `map.plan.v1` | file, hash | source record kept; REFERENCE only |
| L9, L10, L11 | project | text / JSONL | none (category D) | `ref.v1` | path, size, hash | original in place |
| L12, L18, L19, L20 | project / account | JSON / logs | none (category D) | `ref.v1` | path, hash | — |
| L13 | project | JSON | Project root paths, inspection input | `map.workspace.v1` | file, hash | source record kept; roots confirmed by the user |
| L14 | global / account | JSON | Account, ResourcePolicy defaults, preferences; legacy theme only as a *suggestion* (§25.11) | `map.settings.v1` (secrets → category C) | file, key path | source record kept; the user sets accounts by hand |
| L15 | project / account | JSON + OS scheduler | Automation, DISABLED | `map.loops.v1` | file, loop id | source record kept |
| L16 | global | markdown | REFERENCE (skills as offers: V1.x-O5) | `map.library.v1` | file, hash | source record kept |
| L17 | project / session | JSON / text | labels on Session rows when those exist; project STANDARD (system prompt) | `map.session_meta.v1` | file, session id | source record kept |
| L21 | account | credential files | none (category C) | `excl.v1` | path only, no hash | — |
| M1 | project (file project-owned) | managed blocks in markdown | `KEEP` → STANDARD (explicit); the rest none (category B) | `map.keep_block.v1` | file, block marker, hash | source record kept; file never written |
| M2 | project | markdown | none (category B) | `copy.v1` | file, hash | — |
| M3, M4, M5 | project | markdown / JSON | REFERENCE (harness configuration of the project) | `ref.v1` | path, hash | original in place |
| U1, U2 | user | markdown / JSON | REFERENCE only | `ref.v1` | path, hash | original in place |
| H1 | project / session | JSONL / SQLite | manifest entries (§25.3); Session rows only by the user's action or the run's explicit rule | `ref.v1` | harness, config dir, session id, path, hash | original in place |
| H2 | account | harness files | none | `ref.v1` (existence) | path | — |
| R1, R3, R4 | project (git) | markdown, git | REFERENCE / ARCHITECTURE at `path@commit` | `ref.commit.v1` | path, commit, hash | resolves in git |
| R2 | project | markdown, **some untracked** | REFERENCE; untracked notes are **copied** into the snapshot (category B) so a recovery path exists (§25.9) | `copy.v1` + `ref.v1` | path, hash (+ commit when tracked) | original in place |
| R5 | V1 | SQLite | unchanged; conflicts with L1 per §10 | — | row ids | V1 backup before import |

Every category the brief lists has a row: memory (L1), lessons (L1), knowledge (L1, M1 `KEEP`),
recall history (L3), worklog (L2), session history (H1, L17), plans (L6), generated prompts (L8),
project context (M1, L13, L17), global context (U1, L14), agent and skill definitions (M3, L16),
hooks (U2), rules (M2), managed blocks (M1), project settings (M4), architecture knowledge and ADRs
(R1), implementation and validation history (R3, L2, L5), handoff notes (R2, L9), design
references (R4), harness-specific context (L17, H2), provenance (every row), unresolved decisions
and known failures (R1, L1 lessons, L11), operational knowledge (L1, L3, L14, L15, L18).

### 25.9 Untracked handoff notes

`notes/p16-handoff.md`, `notes/p18-handoff.md` and `notes/p19-5-marker-handoff.md` are untracked
in this repository: **they have no git recovery path today**, and being untracked does not make them
safe. They are recorded as **preservation candidates**: every migration inventory lists them; the
snapshot copies them (category B, secret-scanned) rather than only referencing them, which gives
them their first recovery path; they are never moved, rewritten, committed or deleted by Archeus. In
general, a project's untracked files are listed in the baseline manifest by hash, and copied only
when they are recognised notes (`notes/**/*.md`, `*handoff*.md`) or the user selects them. Until
the first snapshot exists, only the user can protect them (commit or back up) — this pass does
neither.

### 25.10 Model, harness, account and routing knowledge

Migration preserves what routing needs **without turning history into policy**:

| Legacy knowledge | In V1 | Never becomes |
|---|---|---|
| accounts and homes (identity: harness, config dir — matched by canonical home, never a second Account for a home already registered, ADR-0048 §2) | Account rows, V1 defaults, `consumption: normal` | a protection or a rotation permission — the import report asks the user to set each account's class before ADR-0021 `rotation` is permitted (the AP-1 edge) |
| `rotate_threshold`, own-call CLI and model | shown on the report / a preference (migration-plan §4) | an allocation or a constraint |
| provider profiles | accounts to review; keys excluded | provider terms — ADR-0021 answers are the user's, per harness, and stay `unknown` until given |
| legacy model list, `MODEL_PROFILES` | at most REFERENCE history | capability evidence (ADR-0031, P22) |
| lessons about models, harnesses, routing | LESSON knowledge with provenance | a routing rule — evidence orders or excludes only under the user's named rule (ADR-0033) |
| models recorded in transcripts | reachable through the session manifest | OBSERVED evidence — that class is Archeus-driven, verified outcomes only (ADR-0032) |
| project preferences, restrictions | project defaults to confirm (ADR-0041 §4) | a policy the user did not confirm |

A historical preference stays distinguishable from a current policy (its provenance says
`legacy`), a lesson from an authorisation, evidence from a rule. Legacy has no execution history
(its sessions were not Executions), no task families and no route decisions, so none is fabricated;
harness, account and model identities survive on every reference. There is no Agent entity.

### 25.11 Conversation, themes and deployment

- **Conversation (JARVIS).** Legacy has no Conversation entity; V1's conversation starts with the
  migrated knowledge, plans, `KEEP` blocks, session manifest and references behind it. Nothing is
  flattened: source records stay recoverable, and a historical transcript reaches a live
  conversation through P12's explicit hand-off rendering or registration, on the user's action.
  "What happened, why, what was learned, what the user decided" is answered from knowledge with
  provenance, the worklog history and the referenced sources; "what is happening now" from V1
  state (ADR-0043).
- **Themes.** migration-plan §4 mapped a legacy theme to a thread tint; a migration that set it
  would write a client preference, which ADR-0044 keeps per client. Corrected: the legacy palette
  becomes a **suggested** thread tint shown once in Control → Appearance; migration never writes a
  client's theme, contrast or tint, and never sets an application theme. The 39 palettes stay
  thread tints; application themes stay System / Dark / Light / High Contrast.
- **Deployment.** Browser tab, Edge `--app`, PWA, Qt shell and TUI are unaffected: migration has no
  client component, and each client's appearance stays in its own storage.

### 25.12 Advertised vs usable models (C-22) — the four distinctions are represented

| The brief's distinction | ADR-0036 (PROPOSED) |
|---|---|
| CATALOGUED | a `Model` row (rung 1) — shown as catalogue, never as an offer |
| AVAILABLE TO THIS ACCOUNT | an offer exists: the account's configured provider addresses the model (rung 2), and the account is enabled (rung 3) |
| AVAILABLE THROUGH THIS HARNESS | the harness is installed and serves the subject (rung 4, descriptor `serves`, ADR-0037) |
| CURRENTLY RUNNABLE | credentials, reachability and capacity pass (rungs 5–7: `AVAILABLE`); for a given piece of work, "executable" is the router's preview |

The UI requirement is already assigned (orchestration plan D2: state and reason per offer, the
catalogue as a separate count, P22). No documentation change was needed; the fix remains the C-22
slice, awaiting the orchestration plan's D-2.

### 25.13 Remaining decisions, classified

A = already decided and consistent · B = needs the user · C = needs a new ADR · D = can safely stay
deferred.

| Decision | Class | Note |
|---|---|---|
| ADR-0036…0040 (orchestration plan D-1) | **B** | still PROPOSED |
| D-2 C-22 slice timing | **B** | recommended first |
| D-3 pi execution adapter | **B** | recommended V1.x-O4 |
| D-4 user-declared self-hosted tier | **B** | |
| D-5 location values | **B** | the location kind of ADR-0042 directives waits on it |
| D-6 harness-shipped catalogue rung · D-7 probes · D-8 material substitution · D-9 evaluation evidence apart · D-10 architecture changes by replan · D-11 Attention items | **B** | each inside ADR-0036…0040 |
| D-12: ADR-0021 provider terms (incl. rotation) | **B** | OPEN; rotation is now bound to AP-1 |
| D-12: C-15 research-record correction | **B** | outstanding |
| D-12: "DECIDED (direction set by …)" wording on ADR-0031…0035 | **D** | cosmetic |
| D-13…D-24 | **A** | decided in `c94e026` |
| MD-1, MD-2, MD-4 | **A** | as decided in `d4bc009` |
| MD-3, MD-5, MD-6 | **A** | as corrected in §25.3–§25.5 |
| legacy app retirement date | **D** | a later release decision (§25.4) |
| Classic appearance (rulebook Q-C1) | **D** | blocks nothing; untouched by ADR-0044 |
| harness-internal subagent visibility | **D** | not proposed; never an Archeus agent |
| non-Claude usage windows | **D** | each adapter's; Codex's with the Codex adapter (V1 release) |
| voice | **D** | post-V1, same pipeline (ADR-0042 §7) |
| remote workers | **D** | post-V1 (ADR-0008) |
| ADR-0010 (remote access over a tunnel) | **B** | deliberately PROPOSED: P15 built the tunnel-agnostic parts and left the tunnel choice (Q2) and ntfy (Q3) to the user (p15-design-gate, as-built item 8, D20) — not an inconsistency |

No decision needs a new ADR (class C is empty). ADR-0045 is amended in place for MD-3, MD-5 and
MD-6.

### 25.14 Orchestration requirements re-validated

- **Visibility** without an Agent entity: ADR-0043's `live_work` gives mission, plan step, harness,
  account, model and revision, worktree, state, what it waits on, what it produced and why it was
  routed (the RouteDecision); the mission stays the unit.
- **Architecture → implementation → review**: requirements → capabilities → policy → account
  availability → project constraints → preferences → a RouteDecision that explains itself; pins
  stay possible; no product is bound to a role (conversational-orchestration H5).
- **Account control**: "don't use" (forbid / `explicit_only`), "only if necessary" (`last_resort`),
  "never automatically" (`explicit_only`), "keep capacity" (`reserve_pct`), "prefer" (preference /
  priority), "account B for this mission" (mission preference; confirmed if B is protected), "not
  the shared account unless I approve" (`last_resort` with `fallback: ask`). No silent rotation:
  rotation stays unpermitted until AP-1 lands (ADR-0041).
