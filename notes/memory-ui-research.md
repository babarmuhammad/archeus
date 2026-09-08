# Research — how comparable tools structure a memory panel

Produced 2026-08-31 by the `Research memory UI best practice` agent, in answer to
"claude md section is confusing too, check online what's the best practise to
structure this". Kept because the session that commissioned it hit its session
limit before applying it, and it is cited work with live sources.

See `notes/memory-rehaul-open.md` for what of this is applied and what is not.

---

## Verdict on your labels (asked directly)

`always / when touched / per prompt / never` — three of four should change.

| Yours | Use instead | Why |
|---|---|---|
| always | **Every session** (group header: *Always on*) | Matches Cursor's "Always Apply", Continue's `alwaysApply`, Windsurf "Always On", Anthropic's "Session start". "Always" alone reads as frequency, not trigger. |
| when touched | **When Claude reads a matching file** | "Touched" is ambiguous about the actor — user edits vs agent reads. Anthropic is explicit: "Path-scoped rules trigger when Claude reads files matching the pattern, not on every tool use." |
| per prompt | **Every prompt** (keep, but make it the alarm row) | Fine wording. It is the only tier that multiplies by turn count — it deserves visual weight, not parity with the other three. |
| never | **On request** / *Stored, not loaded* | "Never" reads as broken or disabled. These items are retrievable — they cost zero context until asked for. That is a selling point you are currently labelling as a null. |

Umbrella pair for the panel's one-line intro: **always-on vs on-demand**. That is the de-facto 2025-26 framing, and it is Anthropic's own sentence: "Features range from **always-on context** that Claude sees every session, to **on-demand capabilities** you or Claude can invoke, to **background automation** that runs on specific events."

Do **not** borrow cognitive-science labels (semantic / episodic / procedural, short-term / long-term). Reason below in Disagreements.

---

## Prioritised recommendations

### P0 — the four that fix "confusing"

**1. One sentence at the top answering "who wrote this".** Anthropic's memory doc leads its comparison table with the row `| Who writes it | You | Claude |` — before scope, before load timing, before use case. That is the first question a first-time reader has, and your panel currently makes them infer it per row.
→ *Map:* header line "You write the prose in CLAUDE.md. archeus writes everything else on this page — all 12 items — and you can open, edit or delete any of them." Ownership badge on every row after that.
Source: [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)

**2. Group into 4 buckets by load trigger, not a flat 12-row table.** Order by cost descending; the last bucket is the reassurance.
- **Always on — every session** → CLAUDE.md digest, AUTOGEN/SESSIONS blocks, path-scoped rule files (see #12)
- **Every prompt** → per-prompt recall injection *(own bucket, one row, because it is the only per-turn cost)*
- **When relevant** → lessons, path-scoped rules if genuinely scoped
- **Stored, not loaded** → semantic graph, worklog, cross-project conventions, reinforcement log, edit log, workspace manifest, version snapshots

Progressive disclosure says defer what is rarely needed, and Nielsen's split criterion is frequency of use: "You must disclose everything that users frequently need up front, so that they have to progress to the secondary display only on rare occasions."
→ *Map:* buckets 1–3 always expanded. Bucket 4 collapsed by default with a summary line ("7 records — 0 tokens, read only when you or Claude ask").
Sources: [NN/g Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/), [Anthropic: Extend Claude Code](https://code.claude.com/docs/en/features-overview)

**3. Every row links to the actual file.** Anthropic: "Auto memory files are plain markdown you can edit or delete at any time." Cursor goes further — a background model *proposes* a memory and the user approves it before it is saved.
→ *Map:* per row: `Open` (opens the file in $EDITOR, same as `/memory`), plus `Regenerate` and `Turn off`. The single largest trust lever for machine-written memory is that the user can see and delete it.
Sources: [Claude Code memory](https://code.claude.com/docs/en/memory), [Cursor Memories guide](https://localskills.sh/blog/cursor-memories-guide)

**4. Per-item explanation = inline one-line subtitle. Never a tooltip.** NN/g is unambiguous: "Important information should always be on the page; therefore, tooltips shouldn't be essential for the tasks users need to accomplish" and "instructions or other directly actionable information … shouldn't be in a tooltip." Anthropic's own context-window timeline gives each of ~25 items exactly `label` + one-line `desc` + a deep link.
→ *Map:* row = **name** / **one-line subtitle** / **badge** / **cost** / **actions**. Reserve tooltips for a jargon glossary only ("semantic graph", "manifest"). Expandable detail is fine as a *third* level, but the subtitle must stand alone.
Sources: [NN/g Tooltip Guidelines](https://www.nngroup.com/articles/tooltip-guidelines/), [Explore the context window](https://code.claude.com/docs/en/context-window)

### P1 — cost, without alarm

**5. Lead with "what it is", not "what it costs" — and give cost its own section.** Anthropic's IA is the direct precedent: the feature table's columns are `Feature | What it does | When to use it | Example`, and context cost is a **separate later section** with its own table `Feature | When it loads | What loads | Context cost`. Two commands, two jobs: `/memory` shows what exists, `/context` shows what it costs.
→ *Map:* steal those exact four column headings for the panel's table. `When it loads` is your badge column; `Context cost` is the number.
Source: [Extend Claude Code](https://code.claude.com/docs/en/features-overview)

**6. Cost cell wording: copy the shape of Anthropic's values, which are prose, not just numbers.** Their cells read `Every request`, `Low (descriptions every request)`, `Low until a tool is used`, `Zero, unless hook returns additional context`, `Isolated from main session`. That is how you say "this costs tokens" without a red badge.
→ *Map:* `Every request · ~1,400 tok`, `Zero until you run archeus recall`, `Every prompt · ~180 tok`. Number plus a clause. Never a number alone.

**7. Show a budget with a stated target, not a raw total.** Anthropic ships concrete numbers a user can aim at: CLAUDE.md "target under 200 lines"; MEMORY.md loads "the first 200 lines or 25KB, whichever comes first"; skills capped at 5,000 tokens each / 25,000 total after compaction.
→ *Map:* one summary bar at top: "Always-on memory: 4.2k tokens — 2.1% of a 200k window." A percentage of the window is the honest denominator and it is small, which is the de-alarming fact.

**8. If you ever warn, use the 75 / 90 / 100 ladder.** That is GitHub's established budget-alert threshold set for Copilot premium requests, shown in-UI and by email.
→ *Map:* colour only the always-on total, only past a threshold you pick. Individual rows never turn red.
Source: [GitHub Docs — Budgets and alerts](https://docs.github.com/en/billing/concepts/budgets-and-alerts)

**9. Pair every cost with a lever.** NN/g on explainable AI: disclaimers work when they "pair with an action" and use "plain, direct language" — Claude's "Claude can make mistakes. Please double-check responses" is cited as the good example of actionable brevity.
→ *Map:* the cost cell is a control. High always-on cost → `Scope to paths`. Per-prompt recall → `Reduce to N lessons`. Never show a number the user cannot act on.
Source: [NN/g Explainable AI in Chat Interfaces](https://www.nngroup.com/articles/explainable-ai/)

**10. Stamp every machine-maintained row with "last written".** Anthropic added a `modified` ISO-8601 frontmatter field for exactly this: "The timestamp shows how current the fact is, both to you and to Claude when it reads the memory back."
→ *Map:* `updated 3 days ago` on each row. Answers "is this stale?" — the second question after "who wrote it?".

### P2 — table vs cards, and the 12-item layout

**11. Table (or dense row list), not cards.** The 12 items share the same four attributes, and comparison across items is the whole job. "Use a table when users must compare attributes across multiple items… Use a card grid when visual browsing matters more than strict side-by-side comparison." Cards "trade density for scannability." Anthropic uses tables for every one of these comparisons.
→ *Map:* keep the current tabular shape. If cards were the plan, drop them.
Source: [uxpatterns.dev — Table vs List vs Cards](https://uxpatterns.dev/pattern-guide/table-vs-list-vs-cards), [Smashing — Cards vs. Lists vs. Tables vs. Data Grids](https://smart-interface-design-patterns.com/articles/cards-vs-lists-vs-tables-vs-data-grids/)

**12. Do not accordion the 12 rows individually.** NN/g: when the audience needs most of the content, show it all — "accordions increase interaction cost and hiding content behind navigation diminishes people's awareness of it." Only bucket 4 (stored, not loaded) qualifies as rarely needed.
Source: [NN/g Accordions on Desktop](https://www.nngroup.com/articles/accordions-on-desktop/)

**13. Row name = content topic. Badge = load rule.** Two naming traditions exist and both are right for different axes: Cline's Memory Bank names files by *what is in them* (`projectbrief.md`, `activeContext.md`, `progress.md`, "current focus, recent changes, next steps"); Cursor/Continue/Anthropic name by *when it loads* ("Always Apply", `alwaysApply`, "Session start"). Your items are a mix of both, which is likely part of the confusion.
→ *Map:* "Lessons" is a topic name (good). "Per-prompt recall injection" is a load-rule name masquerading as a topic — rename to **"Recall"**, badge `Every prompt`, subtitle "the most relevant slice of the graph, added to each of your messages."
Sources: [Cline Memory Bank](https://docs.cline.bot/best-practices/memory-bank), [Cursor Rules](https://cursor.com/docs/rules)

**14. Verify your "path-scoped rule files" really are path-scoped.** Anthropic: rules **without** a `paths:` frontmatter field "are loaded unconditionally and apply to all files," at the same priority as `.claude/CLAUDE.md`. Your `.claude/rules/archeus-mem-*.md` files as visible in this session's injected context have no `paths:` frontmatter — so they are **always-on**, not conditional. A panel that badges them "when touched" is lying to the user about their cost.
→ *Map:* either add `paths:` frontmatter (and get the cost saving you are claiming) or move them to the Always-on bucket.

### P3 — CLAUDE.md ownership (your question 5)

**15. Use two-sided named markers, with the tool name and the prohibition inside the marker text.** This is a settled convention with four independent instances:
- Ansible `blockinfile`: `# BEGIN ANSIBLE MANAGED BLOCK` / `# END ANSIBLE MANAGED BLOCK`, default template `# {mark} ANSIBLE MANAGED BLOCK` — and the docs are explicit that **markers are required for idempotency**; without the `{mark}` variable the block gets re-inserted every run.
- all-contributors: `<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->` … `<!-- ALL-CONTRIBUTORS-LIST:END -->`
- doctoc: `<!-- START doctoc generated TOC please keep comment here to allow auto update -->` … `<!-- END doctoc -->`
- conda: `# >>> conda initialize >>>` / `# <<< conda initialize <<<`

The last three all solve *exactly* your problem: a human-authored markdown document with machine-maintained regions inside it.
→ *Map:* `<!-- archeus:AUTOGEN start — generated, do not edit. Regenerate: archeus memory build -->`
Sources: [ansible.builtin.blockinfile](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/blockinfile_module.html), [All Contributors CLI](https://allcontributors.org/en/cli/usage/)

**16. Add the Go header clause: by what, and how to regenerate.** The Go convention is `// Code generated by stringer -type Pill; DO NOT EDIT.` — machine-checkable against a fixed regexp, and it names the tool so the reader knows what to re-run. A bare "DO NOT EDIT" tells the reader to stop but not what to do instead.
Source: [go.dev/blog/generate](https://go.dev/blog/generate)

**17. The markers are free — put them in HTML comments.** Anthropic: "Block-level HTML comments (`<!-- maintainer notes -->`) in CLAUDE.md files are stripped before the content is injected into Claude's context… When you open a CLAUDE.md file directly with the Read tool, comments remain visible."
→ *Map:* marker text, regeneration command, timestamp and provenance all cost **zero tokens** if written as `<!-- -->`. There is no budget argument against verbose, self-explaining markers. This is the single most actionable finding for item 5.

**18. In the panel, render the hand-written part expanded and each generated block collapsed — GitHub's model.** `linguist-generated` in `.gitattributes` makes GitHub collapse generated files in diffs behind a "Generated file" banner, "but if you do need to see the diff, you can click through to have it loaded." Progressive disclosure applied to exactly the "which parts do I own" question.
→ *Map:* CLAUDE.md preview = your prose full-height, each AUTOGEN/SESSIONS region a one-line collapsed bar: `▸ AUTOGEN — generated by archeus · 412 tok · updated 3d ago · [Regenerate] [Open]`. Ownership readable at a glance without reading a word of content.
Sources: [thoughtbot — Automatically Collapse Generated Files in GitHub Diffs](https://thoughtbot.com/blog/github-diff-supression), [GitHub Linguist](https://github.com/github-linguist/linguist)

**19. Free adjacent win: add `linguist-generated` to your real `.gitattributes`** for `.claude/rules/archeus-mem-*.md` and the AUTOGEN'd docs. Their PR diffs collapse, and reviewers stop reviewing machine output. One line of config.

**20. A gutter stripe beats a legend.** Diff gutters already teach developers that a left-edge colour = provenance. Two colours, two words in a key above the preview: `yours` / `archeus`.

---

## What each tool actually calls it (reference)

| Tool | Split | UI vocabulary |
|---|---|---|
| **Claude Code** | CLAUDE.md vs auto memory; rules vs skills | `Who writes it` / `What it contains` / `Scope` / `Loaded into` / `Use for`. Scopes: **Managed policy, User instructions, Project instructions, Local instructions**. Auto-memory kinds: `user`, `feedback`, `project`, `reference`. Cost table: `When it loads` / `What loads` / `Context cost` |
| **Cursor** | Rules vs Memories | **Project Rules / User Rules / Team Rules / AGENTS.md**; application modes **Always Apply, Apply Intelligently, Apply to Specific Files, Apply Manually**; Memories proposed by a sidecar model, user approves |
| **Copilot** | Repo-wide vs path-specific | `.github/copilot-instructions.md` (repository custom instructions) vs `*.instructions.md` with `applyTo:` glob frontmatter; stack simultaneously |
| **Continue.dev** | One mechanism, three fields | `alwaysApply` true / false / undefined, `globs`, `description` — the cleanest reduction of the four Cursor modes to two knobs |
| **Windsurf** | Memories (auto) vs Rules (manual) | "Customizations" panel; `global_rules.md` vs `.windsurf/rules`; memories are per-workspace and never cross workspaces; rules capped at 12,000 chars |
| **Cline / Roo** | Content-topic files | **projectbrief, productContext, activeContext, systemPatterns, techContext, progress**; update command is literally "update memory bank" |
| **Letta / MemGPT** | Tiered by residency | **core memory** (in-context, always) / **recall memory** (past conversation, searchable) / **archival memory** (external, vector-retrieved); blocks have `label` / `description` / `value` / char limit |
| **Zep** | Tiered by abstraction | episodic nodes (raw messages) → semantic entities/facts with bi-temporal validity → community summaries; assembled into a **"context block"** |
| **mem0** | Cognitive taxonomy | working / semantic / episodic / procedural — **mostly aspirational**, see below |
| **claude-mem** | Compressed observations | hooks → "observations" (facts, concepts, file refs) in SQLite; markets itself on **"progressive disclosure"** to hold token cost down |

---

## Where sources disagree — flag these

**A. Group by owner, or by cost?** Anthropic's *memory* doc leads with `Who writes it`; Anthropic's *features* doc leads with load timing and puts cost in a separate table. **Resolution:** your 12 items are ~11 machine-written to 1 human, so owner is a terrible *grouping* (1-vs-11) but a mandatory *badge* and a mandatory *opening sentence*. Group by load trigger. This is rec 1 + rec 2 together, and they are not in conflict once you split "grouping" from "labelling".

**B. Should the tool ask before it remembers?** Cursor proposes a memory and waits for approval. Claude Code writes silently and reports "Saved 2 memories" after the fact, relying on "edit or delete at any time". Windsurf's docs specify no approval workflow at all. Genuinely unsettled. Cursor's Memories feature was reportedly removed in 2.1.17 per community reports — so the approval-gate approach has not obviously won. **Recommendation:** follow Claude Code (write silently, always show, always deletable). An approval queue on a reinforcement log that updates every session becomes a chore within a week.

**C. Cognitive-science memory taxonomy is not safe to borrow.** mem0's own docs say only `procedural_memory` is "a real, working value" — semantic and episodic are defined but raise validation errors. A vocabulary whose reference implementation is 1/3 built is not a de-facto standard, and developers reading "episodic" in a settings panel will not know what to do about it. Letta's core/recall/archival is coherent but is a *storage-residency* model that maps to a server, not to files on disk you can open. **Use the load-trigger vocabulary** (always-on / on-demand), which is what every coding-agent tool converged on.

**D. Progressive disclosure vs "show it all".** Nielsen (1995) says defer secondary options; NN/g's accordion research says when most content is relevant, showing everything beats hiding it, because accordions raise interaction cost and reduce awareness. **Resolution:** the 12 rows are all relevant to "what is my memory" — show them. Only the 7 zero-cost bookkeeping rows are rare-need — collapse that one bucket.

**E. AGENTS.md vs CLAUDE.md.** AGENTS.md is now the cross-tool de-facto standard (60k+ repos, 20+ tools, spec donated to the Linux Foundation's Agentic AI Foundation in Dec 2025), and Claude Code explicitly does *not* read it — it recommends `@AGENTS.md` as the first line of CLAUDE.md. Relevant to you: if your AUTOGEN blocks live in CLAUDE.md, a repo that later adopts AGENTS.md will have your blocks in the file the other agents ignore. Worth a decision, not necessarily a change.

---

## Proposed assignment for your 12 items

| Item | Bucket | Badge | Owner | Suggested subtitle |
|---|---|---|---|---|
| CLAUDE.md digest | Always on | Every session | archeus | "A summary of this project, inside the file Claude reads first." |
| AUTOGEN/SESSIONS blocks | Always on | Every session | archeus | "Recent commits and session topics, rewritten on each build." |
| Path-scoped rule files | Always on *(verify — see rec 14)* | Every session | archeus | "One file per module. Add `paths:` to load them only when Claude opens that module." |
| Recall (per-prompt injection) | Every prompt | Every prompt | archeus | "The slice of the graph most relevant to what you just typed." |
| Lessons | When relevant | When relevant | archeus | "85 things this project learned the hard way. Injected when they apply." |
| Semantic graph | Stored | On request | archeus | "The full map. Nothing is loaded until you run `archeus recall`." |
| Worklog | Stored | On request | archeus | "What each session did. Written once at session end." |
| Cross-project conventions | Stored | On request | archeus | "Patterns seen in your other repos." |
| Reinforcement log | Stored | Not loaded | archeus | "Which memories got used. Decides what survives the next consolidation." |
| Edit log | Stored | Not loaded | archeus | "What archeus changed, and when." |
| Workspace manifest | Stored | Not loaded | archeus | "Repo HEAD, hashes, freshness — how the tool knows memory is stale." |
| Version snapshots | Stored | Not loaded | archeus | "Every previous build. Roll back if a rebuild goes wrong." |

Bucket 4's collapsed summary line does the emotional work: **"7 records — 0 tokens. Read only when you or Claude ask."**

---

**Sources:**
- [How Claude remembers your project — Claude Code Docs](https://code.claude.com/docs/en/memory)
- [Explore the context window — Claude Code Docs](https://code.claude.com/docs/en/context-window)
- [Extend Claude Code — Claude Code Docs](https://code.claude.com/docs/en/features-overview)
- [Cursor — Rules](https://cursor.com/docs/rules)
- [Cursor Memories: How They Work vs Rules and Skills](https://localskills.sh/blog/cursor-memories-guide)
- [Adding repository custom instructions for GitHub Copilot — GitHub Docs](https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot)
- [Continue — How to Create and Manage Rules](https://docs.continue.dev/customize/deep-dives/rules)
- [Cline — Memory Bank](https://docs.cline.bot/best-practices/memory-bank)
- [Windsurf — Cascade Memories](https://docs.devin.ai/windsurf/plugins/cascade/memories)
- [Letta — Understanding memory management](https://docs.letta.com/concepts/memory-management/)
- [Mem0 — Memory Types](https://docs.mem0.ai/core-concepts/memory-types)
- [Zep — Graph overview](https://help.getzep.com/graph-overview)
- [Claude-Mem — Introduction](https://docs.claude-mem.ai/introduction)
- [NN/g — Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/)
- [NN/g — Tooltip Guidelines](https://www.nngroup.com/articles/tooltip-guidelines/)
- [NN/g — Accordions on Desktop: When and How to Use](https://www.nngroup.com/articles/accordions-on-desktop/)
- [NN/g — Accordions for Complex Website Content on Desktops](https://www.nngroup.com/articles/accordions-complex-content/)
- [NN/g — Explainable AI in Chat Interfaces](https://www.nngroup.com/articles/explainable-ai/)
- [uxpatterns.dev — Table vs List View vs Card Grid](https://uxpatterns.dev/pattern-guide/table-vs-list-vs-cards)
- [Smashing — Cards vs. Lists vs. Tables vs. Data Grids](https://smart-interface-design-patterns.com/articles/cards-vs-lists-vs-tables-vs-data-grids/)
- [GitHub Docs — Budgets and alerts](https://docs.github.com/en/billing/concepts/budgets-and-alerts)
- [ansible.builtin.blockinfile module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/blockinfile_module.html)
- [All Contributors — CLI usage](https://allcontributors.org/en/cli/usage/)
- [Go blog — Generating code](https://go.dev/blog/generate)
- [thoughtbot — Automatically Collapse Generated Files in GitHub Diffs](https://thoughtbot.com/blog/github-diff-supression)
- [github-linguist/linguist](https://github.com/github-linguist/linguist)
- [Terraform — Import: Generating Configuration](https://developer.hashicorp.com/terraform/language/import/generating-configuration)
- [AGENTS.md Spec (2026)](https://www.morphllm.com/agents-md-guide)</result>
<usage><subagent_tokens>144705</subagent_tokens><tool_uses>46</tool_uses><duration_ms>436967</duration_ms></usage>
</task-notification>
