# XR-14 Decision Brief — Claude Code tool allowlists

Internal architecture document (excluded from the published manual). Status: **the analysis
behind a decision.** **XR-14 was DECIDED on 2026-10-03:** Alternative 1 (§10), with unmapped
built-in tools excluded by default, recorded as
[ADR-0052](decisions/ADR-0052.md). The text below is the analysis as presented before the
decision and is kept unchanged. The "XR-14 remains OPEN" in §12 is historical. Date: 2026-10-03,
at HEAD `0a2a3af`.

Register entry: [ARCHEUS_V2_ASSISTANT_LAYER.md](ARCHEUS_V2_ASSISTANT_LAYER.md) §4 XR-14 · plan §33 Q22.

**Tags:**
- **[A]** Archeus code or decided document at `0a2a3af`;
- **[CLI]** `claude --help`, v2.1.287;
- **[DOC]** the Claude Code documentation as read on 2026-10-03: hooks (`code.claude.com/docs/en/hooks.md`), CLI reference (`…/cli-reference.md`), headless (`…/headless.md`), tools reference (`…/tools-reference.md`);
- **[I]** inference.

The [DOC] answers came through a documentation subagent that quoted the pages. Each one should
be re-read once before it is built on.

---

## 1. Current reality

### What constrains tools today [A]

1. **Per tool call: the Archeus `PreToolUse` hook.**
   - **Configuration:** `archeus/harnesses/hook.py`, wired by `--settings <exec dir>/settings.json`
     with matcher `*` and timeout 120 (`archeus/harnesses/claude_code/adapter.py:104-125`).
   - **Flow:** for every tool call it checks the STOP, PAUSE and HANDOFF flags, then asks Core
     through a file mailbox and waits up to `ARCHEUS_HOOK_WAIT` (default 60 s, `hook.py:30`).
   - **Core's answer** (`archeus/core/application/executions.py:583-629`) checks, in order:
     - the execution state;
     - the sequence number;
     - the hook token (`hmac.compare_digest`);
     - the disarm state;
     - the plan binding;
     - that the cwd is inside the workdir;
     - that HEAD is the execution's branch.
   - **Classification:** it then classifies the call with `archeus/core/execution/canonical.py`
     and evaluates **each canonical action** with P9 policy. Any DENY gives `deny`, any ASK gives
     `halt` (an approval is requested), and otherwise `allow`.
   - **Unknown tools.** A tool it does not know, a shell operator, an interpreter payload or a
     parse error becomes ONE unclassified `exec` action, judged as every class the task holds plus
     `exec`, strictest wins (`canonical.py:9-13`).
   - **Failure inside the hook process:** the hook denies and halts (`hook.py:132-140`; test E47).
2. **What Claude Code does when the hook answers nothing usable [DOC].**
   - A non-0, non-2 exit is a "Non-blocking error - tool call proceeds through normal permission
     flow".
   - On a timeout, "Hook is canceled; tool call proceeds through normal permission flow".
   - Invalid JSON on exit 0 is a non-blocking error, and the action proceeds.
   - **The fallback is the permission flow.** In `-p` with no host, permission requests "are
     denied either way" [DOC], and `--permission-prompts` defaults to `host` [CLI].
   - **So after a hook failure:**
     - a tool that needs no permission prompt runs;
     - a tool that needs one is denied, unless a permission rule pre-approves it.
   - **Permission rules today come from the account home, project and local settings sources.**
     The adapter does not narrow them yet; ADR-0049 is decided but not built.
3. **Environment and credential removal** (`archeus/core/execution/manager.py:59`;
   p11-design-gate §18): no push credentials, no git credential helper, no SSH agent. That limits
   what an allowed `Bash` can *achieve* against remotes; it does not decide which tools run.
4. **Harness-provided sandboxes** (ADR-0051): only for harnesses classed `sandbox` (Codex).
   Claude Code is hook-enforced and has none.

### What the hook guarantees [A]

For every tool call that reaches it and gets a well-formed answer, the call is judged by
current policy against:
- the execution's token, binding, workdir and branch;
- unknown tools as unclassified `exec`, strictest wins;
- STOP, PAUSE and HANDOFF honoured without Core.

**Coverage [DOC]:** hooks fire for tool calls inside subagents ("The same configured hooks fire
as in the main conversation") and for MCP tools (`mcp__<server>__<tool>`).

### What it does not guarantee

- **Hook failure without output.** If the hook process cannot start or exits non-0/non-2 before
  writing (for example `sys.executable` is gone, `manager.py:207`), Claude Code proceeds with the
  permission flow [DOC]. **Read-only tools then run with no Archeus judgement** [I: they need no
  prompt], including `Read` of paths outside the worktree. Tools needing a prompt are denied
  unless a permission rule allows them.
- **Timeout.** The hook bounds itself at 60 s, inside Claude Code's 120 s. A hook that blocks
  before reaching its own timer (for example on filesystem I/O) is cancelled at 120 s, and the
  tool proceeds through the permission flow [DOC].
- **What a held tool does once allowed.** An allowed `Bash` running `python x.py` is classified
  `exec` with `paths: ['.']`, and what the script then does is outside every Archeus layer. This
  is the OS-level gap recorded in ADR-0051.
- **Precedence against other hooks.**
  - Not documented [DOC].
  - ADR-0049 moves the deny to exit code 2, which is documented as unconditional. That is
    decided, not yet built.
- **Precedence of a hook `allow` against `permissions.deny` / `--disallowedTools`:** NOT
  DOCUMENTED [DOC].

### Is there a second independent layer today?

- **For tool *selection*: no Archeus-built one.**
- **Claude Code's own permission flow is a de facto fallback.** It is not configured by Archeus,
  and it is weakened by any permission rule inherited from the settings sources.
- Credential removal is independent, but it constrains effects, not tools.

### Documented versus implemented

| Claim | Where | Implemented? |
|---|---|---|
| Claude Code `--allowedTools`/`--disallowedTools` derived from action classes | execution-architecture §2 "Tools" | **no** (`adapter.py:117-126` passes neither) |
| "the execution environment has only the capabilities policy allows (no push credentials, sandbox flags, tool allowlists)" | ADR-0007 Decision, enforcement (2) (DECIDED) | push credentials yes; tool allowlists **no** |
| "The classifier is a convenience; capability removal (§18) is the guarantee" | p11-design-gate §11; `canonical.py:12-13` | §18 contains no tool removal, so the "guarantee" for tools does not exist |
| Hook asks `POST /v1/hook/evaluate`, Core unreachable at a 5 s timeout | execution-architecture §5 | **differs:** file mailbox, 60 s default |
| Hook at `harnesses/claude_code/hooks/policy_hook.py` | execution-architecture §1 | **differs:** `archeus/harnesses/hook.py` |
| Own calls with write tools disallowed | `archeus/harnesses/calls.py:52`; legacy `llmcall` (`tests/test_p05_seams.py:55`) | yes (own calls only, not executions) |

No test asserts any tool restriction on an execution. E47/E48/E49 and S03–S07 test the hook and
Core's answer.

## 2. What execution-architecture §2 requires

> **Tools** — Claude Code `--allowedTools` / `--disallowedTools` derived from action classes
> (e.g. no `Bash` for a pure `document` task)

This sits in a table introduced as: "Before spawn, the manager builds the environment from the
task's evaluated policy — this is the **primary** enforcement layer (ADR-0007); hooks are
secondary."

**The intended relationship [A]:**

| Layer | What it is | Role |
|---|---|---|
| Action classes | what a task holds | the policy vocabulary |
| Environment (credentials, workdir, tools) | built from those classes before spawn | primary layer: removes what the task does not hold |
| The hook | judges each remaining call against policy | secondary layer |
| The harness sandbox | where one exists | contains effects |

The hook is meant to refine *within* what removal left, not to be the only thing standing.

**A defect in §2's own wording [DOC]:**
- `--allowedTools` lists "Tools that execute without prompting for permission… To restrict which
  tools are available, use `--tools` instead."
- So `--allowedTools` *pre-approves*; it does not remove.
- Taken literally, §2 would make every listed tool run without a prompt **when the hook fails**,
  which is weaker than today's fallback, where such tools are denied in `-p` with no host.
- Any option that builds the allowlists has to read §2's intent (removal), not its flag name.

## 3. Option 1 — build the allowlists in P20

### What changes

| Area | Change |
|---|---|
| Adapter invocation | `ClaudeCodeAdapter.argv()` (`adapter.py:117-126`) derives the tool set from `spec.task_contract['action_classes']`, which already reaches the adapter (`manager.py:209`) |
| Restriction flags | `--tools <list>`, a named allow-form availability list, plus `--disallowedTools "mcp__*"` (`--tools` "doesn't affect MCP tools") except opted-in MCP servers (ADR-0049) |
| `--allowedTools` | **never passed**, because it pre-approves |
| Prompt fallback (optionally) | `--permission-prompts none` [CLI], which makes "anything that would prompt is denied automatically" explicit instead of relying on the absence of a host |

**The mapping lives in the adapter.** It is Claude Code's tool vocabulary, so it belongs there,
not in orchestration, which ADR-0037 §4 forbids from branching on harness ids.

### How action classes map to tools [A][I]

| Action class | Claude Code tools it can make available |
|---|---|
| `read` | Read, Glob, Grep, LS |
| `write_repo` | Write, Edit, MultiEdit, NotebookEdit |
| `exec` | Bash; on Windows also the PowerShell tool, which the CLI's `--restricted` help names [CLI] and the canonicaliser does not know |
| `web` | WebFetch, WebSearch |
| `git_commit`, `git_push`, `deploy`, `install`, `destructive`, `external_comm`, `credential`, `spend`, `personal_data` | **no tool of their own:** they happen *through* Bash. An allowlist cannot express them; only the hook (and credential removal) can |

**Consequence:** for any task that holds `exec`, which is most code tasks, the allowlist removes
nothing that matters for the risky classes. It is decisive only for tasks without `exec`,
`write_repo` or `web`, and for tools outside the mapping.

### Tools with no action-class mapping

Examples: the subagent tool, todo and plan tools, the PowerShell tool, REPL, notebook tools, MCP,
and any future tool.

**Sub-decision this option creates:**

| Choice | Effect |
|---|---|
| exclude unmapped tools by default | fail closed; may remove tools Claude Code relies on for normal work (the impact is unmeasured) |
| keep a reviewed list of harmless built-ins | each entry needs an argument |

Subagent tool calls fire the same hooks [DOC], so including the subagent tool does not bypass
the hook.

### Fail-closed behaviour

- **A tool absent from `--tools` cannot be called at all** [DOC: `--tools` restricts which tools
  Claude can call], so a hook failure cannot let it run. This is the property today's
  architecture claims and does not have.
- **For tools present in the list,** a hook failure still falls to the permission flow. Option 1
  does not change that.

### Interaction with ADR-0049

- **Complementary.** ADR-0049 removes what the settings sources *add*: hooks, plugins, skills,
  MCP, permission rules. Option 1 removes what the task does not *hold*.
- **Opted-in tools.** An opted-in MCP server or plugin tool needs an action-class mapping, or it
  is unclassified `exec` at the hook and absent from `--tools`.
- **Undocumented interaction:** whether an inherited `permissions.allow` or a hook `allow` can
  re-enable a tool removed by `--tools` or denied by `--disallowedTools` [DOC Q4]. For `--tools`
  this is unlikely [I: an absent tool produces no call to allow], but it is unverified.

### Interaction with the harness boundary

- No change for `sandbox` harnesses.
- For Claude Code, option 1 narrows the tool surface but contains nothing a held `Bash` does.
  The ADR-0051 gap is unchanged.

### Testing and mutation

1. **A unit test of `argv()`** for each class set:
   - a `document` task gets no Bash, Write or web;
   - `mcp__*` is denied;
   - `--allowedTools` is never present.
2. **A mapping test:** every `ACTION_CLASSES` entry is either mapped or explicitly listed as
   "no tool of its own", and every tool the canonicaliser names is mapped. This fails when a
   class or tool is added.
3. **Mutation checks:** remove one mapping row; add `--allowedTools`; drop `mcp__*`. Each must
   fail a test.
4. **A live run** (PV-19 class, gated by ADR-0021) confirming that a tool absent from `--tools`
   is never offered or called.

### Threat-model implications

The tool *surface* becomes two layers (removal plus hook) for tools outside the task's classes,
and stays one layer (hook plus the permission fallback) for the tools it holds.

### Independent defence or duplication?

- **Independent** where the hook answers nothing usable, or where the canonicaliser misclassifies
  an unmapped tool. Removal acts before the model and the hook exist in the call path.
- **Duplication** for every action class that rides on Bash.

### New assumptions it introduces

1. Claude Code's tool names are a contract the adapter tracks. They are NOT DOCUMENTED as stable
   [DOC Q9], and a test must catch drift.
2. Removing a tool does not break Claude Code's normal operation for the task kinds Archeus
   runs. This is unmeasured.
3. `--tools` keeps its "restrict" meaning across CLI versions. The descriptor's
   `installed_version` (ADR-0037) is where that would be tracked.

## 4. Option 2 — the hook as the sole tool gate

### What would be amended (each a recorded amendment, never a silent edit)

- **execution-architecture §2:** replace the "Tools" row with "Claude Code: the full built-in tool
  set is available; the per-tool hook is the tool gate (§5); `--allowedTools` is never passed;
  MCP is governed by ADR-0049".
- **ADR-0007** (DECIDED): an "Amended" section removing "tool allowlists" from enforcement (2)
  for hook-enforced harnesses.
- **p11-design-gate §11** and the `canonical.py` docstring: "capability removal is the guarantee"
  no longer holds for tool selection. Changing the docstring touches a code file (comments only).
- **ADR-0051 §2:** state the hook as the sole tool gate.

### The guarantee the hook provides

The guarantee in §1 above: every tool call that reaches a working hook is judged, including
unknown, subagent and MCP calls.

### Guarantees lost by removing the allowlist requirement

| Lost guarantee | Under option 2, depends on |
|---|---|
| A tool a task does not hold cannot run when the hook fails | the permission fallback |
| A new Claude Code tool is unavailable until reviewed | the canonicaliser treating it as unclassified `exec` (only while the hook works) |
| Two independent layers for tool selection, as ADR-0007 states | — |

### Can the hook be bypassed on a supported path?

| Path | Assessment |
|---|---|
| Subagents and MCP | **No** [DOC: hooks fire] |
| A hook failure without output, or a timeout before its own timer | **Yes:** the call proceeds through the permission flow [DOC]. Read-only tools run unjudged; prompt-requiring tools are denied in `-p` unless a permission rule allows them |
| Another hook's decision overriding Archeus's | **Not established** [DOC] |
| Missing `--settings` or a wrong hook path through an adapter mistake | the call proceeds unjudged into the permission flow. Today there is no test that `argv()` always carries `--settings` with the hook [A: none found] |

### The harness boundary

The same in both options: the hook judges calls, not effects. ADR-0051 records the gap.

### Tests required to establish the guarantee

1. `argv()` always carries `--settings` with the hook and never `--allowedTools` (a mutation:
   drop `--settings` must fail).
2. The hook's failure paths all produce a blocking answer:
   - an import error;
   - the interpreter missing;
   - an unwritable mailbox;
   - an oversized payload.
3. The hook bounds itself below Claude Code's timeout (60 < 120 today; assert it).
4. With ADR-0049 built, no inherited permission rule pre-approves anything.
5. A live run (gated by ADR-0021) showing that a hook that cannot start leaves `Bash` and `Edit`
   denied in `-p`, and showing what `Read` does.

### Threat-model language that would change

- "Tool selection for Claude Code executions has one Archeus-controlled layer (the hook). Its
  failure falls back to Claude Code's permission flow, which denies prompt-requiring tools in a
  headless run and lets prompt-free tools (read-only) run."
- The ADR-0007 "primary layer" statement is narrowed to credentials, the workdir and limits.

## 5. Option 3 — defer to P24

### What stays inconsistent until P24

- ADR-0007, execution-architecture §2 and p11 §11 keep claiming a removal layer for tools that
  does not exist.
- ADR-0051 §2 keeps naming the gap.
- P23 acceptance runs against a one-layer tool gate while the documents describe two.

### Can P20 proceed?

Yes, mechanically. ADR-0049 (exclusion, inventory, exit-2 deny) and ADR-0051 (boundary tests,
threat model) do not need XR-14's answer.

### What P20 must preserve for P24 to decide later

- **Argv in one place:** tool-related argv stays built only in `ClaudeCodeAdapter.argv()`.
- **Inputs at the adapter:** `task_contract.action_classes` keeps reaching it.
- **No pre-approval:** `--allowedTools` is never introduced, under any option.
- **A recorded tool set:** the inventory ADR-0049 adds records the tool flags passed (none), so
  P24 can see the actual surface.
- **Honest threat model:** it states the one-layer reality, not the documented two.

### Debt and ambiguity

- **Implementation debt:** small, since the surface in §8 is small.
- **Security ambiguity:** real. The decided documents and the build disagree, and an auditor
  reading ADR-0007 would assume a layer that is absent.

## 6. Security boundary analysis

For each failure mode: which layer detects or prevents it.

| Failure mode | Option 1 (removal + hook) | Option 2 (hook only) | Option 3 (until P24) |
|---|---|---|---|
| Model picks a tool the task does not hold (Write in a read-only task) | **prevented** by removal (the tool is absent); the hook would also deny | the hook denies (P9: class not held) | as option 2 |
| Model uses a held tool for an unheld action (Bash `git push` without `git_push`) | the hook (P9) plus credential removal; removal cannot express it | the same | the same |
| Hook failure without output (cannot start, crash before stdout, invalid JSON, timeout) | tools absent from `--tools`: **cannot run**. Held tools: permission fallback | **all** tools: permission fallback. Prompt-free tools (Read…) run unjudged | as option 2 |
| Hook bypass by subagent or MCP | none: hooks fire [DOC]; MCP is also denied by `mcp__*` unless opted in | none: hooks fire; MCP governed by ADR-0049 | as option 2 |
| Another hook overriding Archeus's decision | the exit-2 deny (ADR-0049) for the deny path; removal for absent tools | the exit-2 deny only | as option 2 |
| Adapter mistake (no `--settings`, wrong hook path) | absent tools still cannot run; held tools fall to the permission flow | every tool falls to the permission flow | as option 2 |
| Inherited configuration (permission allows, foreign hooks, MCP) | ADR-0049 exclusion; removal for absent tools | ADR-0049 exclusion | as option 2 |
| Harness escape (an allowed Bash runs a program; Read outside the worktree) | **neither layer:** ADR-0051 gap; PV-20 | the same | the same |
| Future action class added | the mapping test fails until it is mapped, so it fails closed at build time | the hook judges the new class; there is no build-time signal about tools | as option 2 |
| Misclassified action (canonicaliser error) | removal still bounds the tool set; inside held tools, the error stands | the error stands | the same |
| Claude Code adds or renames a tool | new tool: **absent** from the allow-form `--tools`, so fail closed. Renamed tool: the task loses the tool (fails safe, may break work); the drift test catches it | new or renamed tool: unclassified `exec` at the hook (strictest), safe while the hook works; on hook failure it falls to the permission flow | as option 2 |

## 7. Architectural consistency

| Record | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| ADR-0007 (DECIDED: "tool allowlists" in enforcement (2)) | consistent | **contradicts**: needs an Amended section | inconsistent until P24 |
| execution-architecture §2 | consistent with its *intent*; its flag name (`--allowedTools`) must be corrected to `--tools`/`--disallowedTools`, a recorded amendment | contradicts: the row is amended | inconsistent until P24 |
| p11-design-gate §11, §18; `canonical.py` docstring | consistent with "removal is the guarantee"; §18 as built gains tool removal | §11's sentence becomes false and must be amended | inconsistent until P24 |
| ADR-0051 | §2's gap is closed by P20 | §2 is restated as "the hook is the sole tool gate" | §2's gap stays open |
| ADR-0049 | complementary (sources vs held classes); opted-in tools need a mapping | independent | independent |
| ADR-0021 | the live verification is gated by it (as PV-19) | the same | the same |
| P20 scope | adds argv mapping and tests | adds hook failure-path tests and amendments | adds nothing for XR-14; an honest threat model |
| V2 assistant boundary (ADR-0050 §6) | consistent: capabilities come through descriptor and policy | consistent | consistent |

**Contradictions found and not fixed here** (recorded so the user sees them):
1. execution-architecture §2 names `--allowedTools`, which pre-approves rather than restricts
   [DOC].
2. execution-architecture §5 says the hook calls `POST /v1/hook/evaluate` with a 5 s timeout. The
   build uses a file mailbox and 60 s.
3. execution-architecture §1 names `harnesses/claude_code/hooks/policy_hook.py`. The build uses
   `archeus/harnesses/hook.py`.
4. ADR-0007 and p11 §11 claim a tool-removal guarantee that §18 and the adapter never built.

Items 2 and 3 are not XR-14's question. Each is a stale description of a working hook, and
belongs to whichever pass corrects execution-architecture.

## 8. Implementation surface (estimates; nothing modified)

| | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| Code | `archeus/harnesses/claude_code/adapter.py` (`argv`, a mapping table); possibly `archeus/harnesses/base.py` if the descriptor exposes the mapping | `canonical.py` (docstring only); optionally `hook.py` hardening if a failure-path test finds a gap | none |
| Contracts / schemas | none new: `task_contract.action_classes` already carries the input; the ADR-0049 inventory records the tool flags | none | the ADR-0049 inventory records "no tool flags" |
| Tests | `tests/v1/unit/test_execution_units.py` or a new `test_claude_code_tools.py` (argv per class set, mapping completeness, `--allowedTools` never, `mcp__*`); mutation entries in the P20 mutation tool; a live test beside `tests/v1/integration/test_claude_code_live.py` (gated by ADR-0021) | hook failure-path tests next to E47–E49 (`tests/v1/integration/test_execution.py`); an `argv` always-carries-the-hook test; a timeout-bound assertion; a live test (gated) | none for XR-14; a threat-model test is documentation |
| Docs / ADRs | execution-architecture §2 (flag correction, as an amendment); p11 §18 as-built note; ADR-0051 §2; testing-strategy G6 rows; a new ADR recording the decision | ADR-0007 Amended; execution-architecture §2 amended; p11 §11 amended; ADR-0051 §2; G6 rows; a new ADR | ADR-0051 §2 unchanged; a P24 entry naming XR-14 |

## 9. Decision framework (questions, not a ranking)

1. **Independent layers.** For tool *selection*, must Claude Code executions have two independent
   layers, as ADR-0007 states, or is one sufficient?
2. **Hook failure.** What should happen when the hook answers nothing usable? Is Claude Code's
   permission fallback (prompt-requiring tools denied in `-p`; prompt-free tools run) an
   acceptable floor?
3. **Machine-enforced mapping.** Must every action class have a machine-checked mapping to
   Claude Code tools, even though nine of the thirteen classes have no tool of their own?
4. **Future tools.** Should a future or renamed Claude Code tool be unavailable until reviewed
   (allow-form `--tools`), or available and judged at the hook as unclassified `exec`?
5. **Unmapped built-ins.** Are you willing to accept the sub-decision Option 1 creates about them
   (exclude all, or a reviewed list)?
6. **Ownership.** Is P20, whose acceptance (G6) this affects, the right owner, or should the
   question wait for P24's whole-application audit, accepting documents that disagree with the
   build until then?
7. **Documented intent.** Do you want ADR-0007's decided text to remain true as written, which
   means option 1, or to be amended, which means option 2?

**Whatever the choice:** `--allowedTools` must never be introduced as a "restriction", because it
pre-approves.

## 10. Proposed ADR text (three alternatives; none selected)

### Alternative 1 — "ADR-0052: Claude Code executions get tool removal derived from action classes, beneath the hook"

- **Context:**
  - ADR-0007 enforcement (2) and execution-architecture §2 require tool allowlists; they were
    never built (p11 §18, `adapter.py:117-126`), so the hook was the only tool gate.
  - A failed hook falls to Claude Code's permission flow [DOC].
  - `--allowedTools` pre-approves and does not restrict [DOC].
- **Decision:**
  1. The Claude Code adapter derives `--tools` (allow-form) from the task's action classes,
     through a mapping table owned by the adapter.
  2. It passes `--disallowedTools "mcp__*"` except for MCP servers opted in under ADR-0049.
  3. It never passes `--allowedTools`.
  4. Classes with no tool of their own are enforced by the hook and credential removal only.
  5. Unmapped built-in tools are [excluded by default | limited to a reviewed list — the user
     chooses].
  6. Execution-architecture §2's flag names are corrected accordingly (Amended).
- **Consequences:** two layers for the tool surface; the tool names become a tracked contract;
  Claude Code's behaviour without the removed tools must be measured.
- **Security boundary:** removal bounds which tools exist; the hook judges every call to what
  remains; credential removal bounds effects. None of it contains a held tool's effects
  (ADR-0051).
- **Testing:** argv per class set; mapping completeness against `ACTION_CLASSES` and the
  canonicaliser's tools; `--allowedTools` never present; mutations on each; a live check gated by
  ADR-0021.
- **Relationship to P20 and P24:** built and accepted in P20 (G6); attacked in P24.

### Alternative 2 — "ADR-0052: for Claude Code executions the per-tool hook is the sole tool gate"

- **Context:** as above.
- **Decision:**
  1. Claude Code executions keep the full built-in tool set.
  2. The fail-closed hook is the sole Archeus tool gate.
  3. `--allowedTools` is never passed.
  4. MCP is governed by ADR-0049.
  5. ADR-0007 enforcement (2) is amended to drop tool allowlists for hook-enforced harnesses.
  6. Execution-architecture §2, p11 §11 and the canonicaliser docstring are amended to say so.
- **Consequences:**
  - one layer for tool selection;
  - on hook failure, the floor is Claude Code's permission flow, so prompt-free tools run
    unjudged;
  - no tool-name contract to track.
- **Security boundary:**
  - the hook (with the exit-2 deny) judges every call;
  - the permission fallback denies prompt-requiring tools in `-p`;
  - credential removal bounds effects;
  - the ADR-0051 gap is unchanged.
- **Testing:**
  - argv always carries the hook and never `--allowedTools`;
  - every hook failure path yields a blocking answer;
  - the hook's own timeout stays below Claude Code's;
  - no inherited permission rule pre-approves (with ADR-0049);
  - a live check of the fallback, gated by ADR-0021.
- **Relationship to P20 and P24:** amendments and tests in P20; P24 attacks the single layer.

### Alternative 3 — "ADR-0052: the tool-allowlist question is deferred to the P24 audit"

- **Context:** as above.
- **Decision:**
  1. P20 neither builds tool removal nor amends ADR-0007.
  2. P20 preserves: tool argv built only in `ClaudeCodeAdapter.argv()`;
     `task_contract.action_classes` at the adapter; `--allowedTools` never introduced; the
     ADR-0049 inventory recording the tool flags passed.
  3. P20's threat model states that tool selection has one Archeus layer today.
  4. P24 decides between Alternatives 1 and 2 from its audit.
- **Consequences:**
  - ADR-0007, execution-architecture §2 and p11 §11 disagree with the build until P24;
  - P23 accepts the one-layer system.
- **Security boundary:** as Alternative 2, until P24.
- **Testing:** the P20 preservation points asserted; nothing for removal.
- **Relationship to P20 and P24:** P20 preserves; P24 owns the decision. This must be decided
  before P26.

## 11. Impact on V2

### Direct consequences

- **V2-A4 (browser) and V2-A5 (desktop):**
  - their capability ADRs add new tools and action classes;
  - under Alternative 1, each must add a mapping row, or its tools are absent from `--tools`;
  - under Alternatives 2 and 3, their tools reach the hook as unclassified `exec` until the
    canonicaliser learns them.
  - Either way, the capability ADRs must say how their tools are classified. That is now a named
    prerequisite whichever option is chosen.
- **ADR-0050 §6** (capabilities only through descriptor and policy): consistent with all three.
  No amendment is needed.

### Possible future considerations

- **Future action classes:** Alternative 1 makes every new class a build-time mapping decision.
  Alternative 2 makes it a canonicaliser decision only.
- **PV-20, the OS sandbox, is orthogonal:** it bounds effects, which no option here does.

## 12. Stop condition

**Facts established:**
- **The hook is the only Archeus tool gate today.** It is strong when it answers (P9 per action;
  unknown tools as strictest `exec`; it fires in subagents and for MCP).
- **When it answers nothing usable, Claude Code falls back to its permission flow:**
  prompt-requiring tools are denied in `-p`, prompt-free tools run [DOC].
- **The documents claim a second layer that was never built:** ADR-0007, execution-architecture
  §2, p11 §11 and `canonical.py`.
- **§2's named flag, `--allowedTools`, would pre-approve rather than restrict** [DOC]. The
  restricting flags are `--tools` and `--disallowedTools`, and `--tools` does not cover MCP.
- **The input a removal layer needs already reaches the adapter.**
- **Most risky action classes have no tool of their own,** so removal cannot express them.

**Unresolved question:** for tool selection in Claude Code executions, does Archeus require an
independent removal layer beneath the hook, or is the hook (plus Claude Code's permission
fallback) the accepted boundary?

**The options:**
1. Build removal in P20 (`--tools` + `--disallowedTools`; never `--allowedTools`).
2. Declare the hook the sole gate and amend ADR-0007, execution-architecture §2 and p11 §11.
3. Defer to P24, with P20 preserving the listed invariants.

**The decision you need to make:** XR-14 = 1, 2 or 3. If 1, also the unmapped-built-ins
sub-choice (exclude all, or a reviewed list).

XR-14 remains **OPEN**.
