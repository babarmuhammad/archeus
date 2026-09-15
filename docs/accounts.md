---
description: >-
  Run two or more Claude accounts side by side — named config dirs, per-launch account selection, merged project rows and cross-account context injection.
---

# Multiple Claude accounts

⚙ Accounts. Run two (or more) accounts with almost no friction — archeus owns the config
dir (`CLAUDE_CONFIG_DIR`), which is what decides the account:

- **Named accounts** — add an account (name + config dir; archeus creates it and can open `/login` right away), rename it, switch the active one, or **open it in a new terminal with one key** so both accounts run **at the same time**.
- **Per-launch account** — the launch-options screen has an **Account** field: pick which account this specific session starts under, without changing your default.
- **All accounts in the usage bar** — the plan-usage banner shows **one bar per account** (labeled by email/name) and updates dynamically, so you see every account's session/weekly limits at a glance. A single account stays a single compact bar.
- **One row per project, not per account** — if the same folder has sessions under two accounts, the project list shows a single row (default account primary, tagged `[+other-account]`) instead of a duplicate. Opening it merges every account's sessions into one list, foreign-account sessions marked inline (`[account-name]`); rename/archive/delete/fork/view all act on that session's own account, and resuming one launches under the right account automatically.
- **Hand off across accounts** (**Hand off** on a session row in the GUI, `⇧K` in the terminal UI) — start a new session seeded with the transcript of any prior session for this project, including ones from a different account. This is how you keep working when one account hits its limit: pick the session you were in, pick the other account, carry on. See [Context hand-off](context-handoff.md).
- **archeus's own calls move too** — when the active account's window is full and archeus wants to generate an agent, a skill, a CLAUDE.md or a memory cycle, it stops and offers the accounts that still have headroom rather than launching a call it knows will fail. Unattended work skips and records the reason instead of prompting. See [Rate limits and a second account](tui.md#rate-limits-and-a-second-account).
- **Account-accurate memory** — the memory graph lives under the project's real path (shared by every account), and the features that feed it now read **every** account's sessions: lesson extraction, the CLAUDE.md session-topics block, per-project usage stats, workspace freshness counts, and the recent-sessions quick-resume list. A project used under two accounts is one merged row in the usage dashboard, not two.

`archeus sync-accounts` levels every account up to what you have actually provisioned —
hooks, status line and settings placed once, applied everywhere.

## Automatic rotation

⚙ Accounts → **Account rotation** (terminal UI: Accounts → **Rotation**).

When the account in use fills its 5-hour or weekly window, the next account with headroom
takes over. You decide how much of that archeus does on its own:

| Mode | What happens |
|---|---|
| **Off** | Nothing rotates. The account you chose is the account you get. |
| **Semi-automatic** *(default)* | New work starts on the next account with headroom by itself — archeus's own Claude calls, a scheduled loop, a session you launch. A session you are **sitting in** is offered the move, one click. |
| **Fully automatic** | The same, and the successor session opens on its own. |

Two more controls sit beside the mode:

- **Switch away at** — the percentage at which an account stops being *chosen*, 98% by
  default. It is not the point at which an account stops *working*: 100% is what blocks a
  call, and an account at 99% is still perfectly spendable. This only stops archeus sending
  new work somewhere that is about to refuse it.
- **In rotation** — a checkbox per login. Opt-out, not opt-in: every account you have
  configured takes part unless you say otherwise. An account that is out is never chosen and
  never offered.

Every switch is written to the [Logs](tui.md#logs) page, and the last few show in the card.

### A running session cannot change account

Claude Code reads `CLAUDE_CONFIG_DIR` once, when it starts. There is no such thing as moving
a live session to another account — so "continue on the next account" means a **new** session
under the other account. The old one is left open; archeus cannot close it for you.

What the new session gets depends on why you moved, and the two reasons want different things:

- **Rotation** — the quota ran out and there is nothing wrong with the conversation, so the
  successor **resumes it**: `claude --resume <transcript> --fork-session`, which loads the real
  exchange rather than a summary of it. Forked, so the original account's transcript is never
  written to. Resuming by session *id* does not cross accounts — Claude Code searches the
  active config dir and answers "No conversation found" — which is why archeus passes the
  transcript's absolute path.
- **[Context hand-off](context-handoff.md)** (the **Hand off** button, `⇧K`) — the context
  window filled, so a fresh session reading `.archeus/injected-context.md` is the point.
  Resuming would start the new session at exactly the pressure that ended the old one.

### It never touches a credential

archeus rotates by launching the **unmodified** `claude` binary under each account's own
`CLAUDE_CONFIG_DIR` — the mechanism Anthropic documents for running several accounts side by
side. It never reads, stores, forwards or refreshes an OAuth token, so nothing here can log
an account out of Claude Code.

That is a deliberate design choice, not an omission. Tools that pool accounts by substituting
credentials into a local proxy have to refresh those tokens, and an Anthropic refresh token is
single-use: whichever program spends it first invalidates the copy the other one holds, which
is why third-party tools doing this have left people re-logging in daily. Signing your own
subscriptions into the real Claude Code binary is both the safe path and the supported one.

### What does not rotate

A session pointed at a [model provider](providers.md) is not spending an Anthropic account's
quota, so it is left alone. Codex and pi logins are not rotated either — their windows are not
Anthropic's and archeus has no headroom figure to compare.
