# Shared workspace: Claude, Codex, Qwen

Local coordination for archeus v1. Excluded from git through `.git/info/exclude`, never committed.

- `BOARD.md` is the task board. One card per unit of work. It is the only queue.
- `reviews/T-NNN.md` holds Codex's verdict on a card, one file per review round (`T-NNN.md`, `T-NNN.r2.md`, ...).
- `review.py` runs a headless Codex review of a card and writes that file.

## Roles

| Agent | Runs as | Does | Never |
|---|---|---|---|
| **Owner** (Babar) | — | Authorizes cards, routes blocked cards, approves pushes | — |
| **Claude** | Claude Code in `D:\Claude` | Implements most cards: code, tests, local commits, card upkeep | Push; reassign a card; run Windows isolation/profile/ACL APIs without that exact authorization on the card |
| **Codex** | `codex exec -s read-only` via `review.py` | Architecture-level, read-only review of each card's commits against the canonical docs | Edit files, run tests, commit |
| **Qwen** (qwen3.8-flash-next on Spark, through `pi`) | `pi --model spark/qwen3.8-flash-next` | Cards the owner assigns to it, usually ones Claude reported as blocked | Push; take a card not assigned to it; anything outside the card's scope |

The roles in the root `AGENTS.md` (Codex reviews, does not implement) still hold. This file adds Qwen and the board.

## Card lifecycle

```
proposed ──owner auth──▶ ready ──▶ doing ──commit──▶ review ──Codex──▶ done
                                      │                 │
                                      ▼                 └──▶ changes ──▶ doing
                                   blocked ──owner routes──▶ ready (owner: claude | qwen)
```

- **proposed**: written by anyone; no code until the owner fills `auth:`.
- **ready**: `auth:` holds the owner's words and date. A historical approval in another document is not authorization for a card.
- **doing**: the implementer sets this and lists every file it will touch in `scope:`. No two `doing` cards share a file.
- **review**: the implementer committed, listed the SHAs in `commits:`, ran the tests named in `verify:` and recorded the result.
- **changes**: Codex's verdict was CHANGES. The implementer addresses each finding, commits, and returns the card to `review`.
- **done**: Codex APPROVED, or the owner accepted it explicitly. ESCALATE goes to the owner, never back to the implementer alone.
- **blocked**: see below.

## When an agent is blocked

A block is any refusal, safety-classifier stop, permission denial, or a question only the owner can answer.

1. Set the card to `blocked`.
2. Under `notes:` paste the exact block message, what is done, and what remains, with file and function names.
3. Stop work on that card and continue with the next `ready` card.

Only the owner moves a blocked card. Routing it to Qwen means setting `owner: qwen` and status `ready`. No agent reassigns a card to another agent on its own.

## Hard rules (every agent, every card)

These come from `AGENTS.md`, `docs/project-context/archeus-chatgpt.md` and incidents already paid for.

- **Git.** Stage files by name (`git add <path>`), never `git add -A` or `git add .`. The tree holds uncommitted work that belongs to no card. No push, no `git clean`, no `reset --hard`, no `checkout -- <file>`, no branch switch.
- **Windows isolation, profile and ACL APIs** (AppContainer create/delete, `icacls`, `SetNamedSecurityInfo`, job objects on real processes) run only when the card's `auth:` names that operation. Writing code that calls them is a different permission from executing it.
- **Never grant or change ACLs on a tree archeus does not own.** `WindowsBoundary.grant()` enforces `require_core_owned` (inside `ARCHEUS_HOME`, no hardlinks). Do not bypass it, and never point a probe at the Python install, the user profile or a repo root: an ungated grant there blacked out the archeus GUI once already.
- **Production switches stay off** unless the card says otherwise: `PRODUCTION_DISPATCH_ENABLED`, `A4_ENFORCED`, `CAPABILITIES` in `archeus/node/isolation.py`.
- **Canonical documents are read, not rewritten**: PV-20 design, ADRs, `p*-design-gate.md`, the S1 gate and acceptance. Material conflict between the code and a canonical document goes to the owner as a `blocked` card.
- **Evidence claims stay exact.** Report what ran, on what, with what result. A test not run is "not run".

## Card format

```
### T-NNN · <title>
owner: claude | qwen · status: proposed | ready | doing | review | changes | blocked | done
auth: <owner's words, YYYY-MM-DD> | —
scope: <files>
refs: <canonical docs or gate items this must satisfy>
accept: <what done means, checkable>
verify: <exact test command(s)>
commits: <sha, sha>
review: <reviews/T-NNN.md verdict>
notes: <blocks, decisions, open questions>
```

Cards meant for Qwen must stand alone: name the files, functions, acceptance and test command. It does not share Claude's context.

## Commands

From `D:\Claude`, in PowerShell or Git Bash:

```
py .collab\review.py T-012            # Codex reviews T-012's commits, writes reviews\T-012.md
py .collab\review.py --pending        # review every card in status review that has no verdict yet
pi --model spark/qwen3.8-flash-next "Read .collab/README.md, then do card T-012 in .collab/BOARD.md."
```

When Codex is out of quota, `review.py` exits non-zero and writes nothing. The card stays in `review` and the next `--pending` run picks it up. Implementation does not wait for review; it continues on the next `ready` card whose scope does not overlap.
