"""One guided tour, three surfaces.

archeus has nineteen global screens and nine project tabs, and every one of them
carries a one-line blurb in the table that declares it (`NAV` and `TABS` in
`app.js`, `MAIN_ACTIONS` in `main.py`). What none of those answer is the
question a new user actually has: *what is this for, and when would I reach for
it?* A blurb says what a screen shows. A tour says why you would open it.

So this file is NOT a copy of those tables and a parity test does not compare it
to them — it is the narrative layer above them, and the one place it is written.
The GUI runs it as an overlay, the terminal UI prints it as a screen, and
`tools/gen_tour.py` writes `www/lib/tour.ts` so the apex's Getting started page
is the same words. Same shape as `cluster_spec.py`: one spec, three renderers,
a generator and a gate.

Two tours, and the difference is not length for its own sake:

* **SHORT** is the first five minutes. It answers "what did I just install" and
  ends with a session actually launched. Nothing in it is optional.
* **LONG** is every function archeus has, one line each. It is a reference you
  can walk rather than read, which is why it is a tour and not a page of prose.

A step is a dict, and the keys are deliberately few:

    id      stable slug — the GUI uses it to resume where you left off
    title   four words or so; it is a heading in three different type scales
    body    ONE sentence, at most 25 words. What it is, and what it is for.
    page    the GUI page id this step is about (`NAV`'s first field), or ''
    tab     the project tab id, for steps about a project (`TABS`), or ''
    key     the terminal UI key that reaches the same thing, or ''
    docs    the manual page that goes deeper, without the .md, or ''

The one-sentence rule is a GATE, not a preference —
`tests/test_tour.py::test_every_step_is_one_short_sentence` counts the words and
the full stops. It used to be the opposite: a 25-word MINIMUM and two sentences,
which is why every body here was a paragraph and why the tour read as something
to get through rather than something to use. A coach-mark is read standing up,
beside the thing it points at; anything longer belongs in the manual, which is
what `docs` links to.

`page`/`tab`/`key`/`docs` are what make one narrative serve three surfaces: the
GUI navigates, the terminal UI prints the key, and the website links the manual.
A step that names a `page` MUST name one that exists — `tests/test_tour.py`
checks every one against the served `NAV`/`TABS`, because a tour that walks you
to a screen that is not there is worse than no tour.
"""

#: Where the manual lives. The tour links it rather than restating it: a second
#: copy of an explanation is a second explanation, and the second one is wrong.
#:
#: The two hosts have OPPOSITE URL shapes and this had both of them wrong at
#: once. The manual is MkDocs on its own subdomain and serves directory URLs, so
#: it is `docs.<host>/memory/` with the trailing slash; the apex is Next.js with
#: no trailing slash. Written as `<host>/docs/memory/` the links were a 404 on a
#: path the apex does not serve, which nothing in the app could have reported —
#: `tests/test_site_links.py` catches it, and only once the file is tracked.
DOCS_BASE = 'https://docs.claudectl.space'
SITE_TOUR = 'https://claudectl.space/getting-started'


def _s(id, title, body, page='', tab='', key='', docs=''):
    return {'id': id, 'title': title, 'body': body,
            'page': page, 'tab': tab, 'key': key, 'docs': docs}


# ── the first five minutes ───────────────────────────────────
#
# Seven steps, and the last one launches something. A getting-started tour that
# ends on a settings screen has not started anything.

SHORT = [
    _s('what', 'What archeus is',
       'The workspace layer around your coding CLI: per-project memory, every '
       'session you have had, and control over what the next one costs.',
       page='home', key='', docs='index'),
    _s('dashboard', 'The dashboard',
       "One screen for quota, today's burn, what is running now, and the "
       'session to continue.',
       page='home', docs='dashboard'),
    _s('projects', 'Open a project',
       'A directory archeus has seen a session in, opened as its own workspace '
       'of tabs.',
       page='home', key='Enter', docs='projects'),
    _s('sessions', 'Every session you have had',
       'Resume, rename, archive or export any conversation in this project, '
       'across every account.',
       tab='sessions', key='s', docs='sessions'),
    _s('memory', 'Memory that survives the session',
       'A graph of the project that archeus injects into every new session and '
       'refreshes on a schedule.',
       tab='memory', key='m', docs='memory'),
    _s('launch', 'Decide what a session costs',
       'Model, effort, permission mode and account are all decided before the '
       'window opens, and can be pinned per project.',
       page='settings', key='n', docs='configuration'),
    _s('go', 'Launch one',
       'archeus opens the real CLI with your choices applied, the memory '
       'digest injected and the status line running.',
       page='home', key='n', docs='quickstart'),
]


# ── every function, and what it is for ───────────────────────
#
# Ordered the way you meet them, not the way the sidebar lists them: what you do
# to a project, then what you install once, then what it all costs, then the
# machinery. One line each — the step that needs a paragraph is the step whose
# `docs` link is doing its job.

LONG = [
    _s('long-what', 'What archeus is',
       'The memory and workspace layer beside Claude Code, Codex and pi: it '
       'launches the real binary, never replaces it.',
       page='home', docs='index'),

    # ── the project ──
    _s('long-dashboard', 'Dashboard',
       'Quota, burn, tooling health and live activity as four gauges, over '
       'your projects and the session to continue.',
       page='home', docs='dashboard'),
    _s('long-live', 'Live sessions',
       'Every session being worked in right now, one row each, showing what '
       'tool call it is blocked on.',
       page='home', docs='dashboard'),
    _s('long-sessions', 'Sessions',
       'Every conversation in this project, across every account: resume, '
       'fork, rename, archive, export or replay it.',
       tab='sessions', key='s', docs='sessions'),
    _s('long-flow', 'Flow graph',
       'A session replayed on its own clock with idle gaps clamped, so a '
       'twelve-hour run plays in seconds.',
       tab='sessions', docs='sessions'),
    _s('long-memory', 'Memory',
       "A graph of the project's entities, relations and lessons, injected "
       'into every new session as a compact digest.',
       tab='memory', key='m', docs='memory'),
    _s('long-lessons', 'Lessons',
       'What went wrong and what fixed it, mined from your transcripts and '
       'held for review before anything is written.',
       tab='memory', docs='memory'),
    _s('long-claudemd', 'CLAUDE.md',
       'The instruction file block by block, what each block costs, and an '
       'editor for the half you wrote.',
       tab='claudemd', docs='memory'),
    _s('long-audit', 'Context audit',
       'What one turn costs across every surface at once, plus this '
       "project's health and what the CLI records.",
       tab='audit', docs='usage'),
    _s('long-review', 'Code Review',
       'A code review over the working tree, staged changes or a branch, with '
       "the project's memory in scope.",
       tab='review', docs='plan-execute'),
    _s('long-planexec', 'Plan → Execute',
       'One model writes a plan you approve or edit, another executes it step '
       'by step with a gate between.',
       tab='planexec', docs='plan-execute'),
    _s('long-pusage', "This project's spend",
       'The same token history as the account-wide page, narrowed to one '
       'project and one timeline.',
       tab='pusage', docs='usage'),
    _s('long-repos', 'Repos',
       'Every git repo, submodule and linked worktree under the project, with '
       'branch and dirty count, read without spawning git.',
       tab='worktrees', docs='projects'),
    _s('long-tools', 'Tools',
       'What this project launches with — its agents, directories and PATH — '
       'beside the commands it has actually run.',
       tab='tools', docs='configuration'),

    # ── what you install once ──
    _s('long-globalmd', 'Global CLAUDE.md',
       'The instructions read in every session on an account, with conventions '
       'from your projects offered for promotion into it.',
       page='globalmd', key='g', docs='memory'),
    _s('long-agents', 'Agents',
       'Subagent definitions you browse, write by hand or have Claude draft; '
       'the description decides whether one is ever picked.',
       page='agents', key='a', docs='agents'),
    _s('long-skills', 'Skills',
       'A procedure you want followed the same way every time: a release '
       'runbook, a review checklist, a house style.',
       page='skills', docs='agent-library'),
    _s('long-hooks', 'Hooks',
       'Claude Code hooks per account: block a command, format on write, '
       'inject context when a session starts.',
       page='hooks', key='h', docs='hooks'),
    _s('long-mcp', 'MCP servers',
       'Every MCP server configured and its status; one you forgot about is '
       'tool definitions in every single turn.',
       page='mcp', key='c', docs='mcp'),
    _s('long-plugins', 'Plugins',
       'The marketplaces you registered and every plugin installed from them, '
       'each through a review gate before it runs.',
       page='plugins', docs='plugin'),
    _s('long-ostyles', 'Output styles',
       'Output styles change how answers are written, not which model writes '
       'them, and it is the cheapest tone fix.',
       page='ostyles', docs='configuration'),

    # ── what it costs ──
    _s('long-usage', 'Usage & cost',
       'Token spend and rate limits across every account, by day, project and '
       'model, with the plan windows as they stand.',
       page='usage', key='u', docs='usage'),
    _s('long-accounts', 'Accounts',
       'Every login with its own config directory, credentials, quota, hooks '
       'and plugins, switchable per launch.',
       page='accounts', docs='accounts'),
    _s('long-rotation', 'Account rotation',
       'When the account in use fills its window, the next one with headroom '
       'takes over instead of stopping you.',
       page='accounts', docs='accounts'),
    _s('long-models', 'Models & providers',
       'The backends a session can run against — Anthropic, a local server, '
       'OpenRouter or OmniRoute — each with its own failover list.',
       page='models', docs='providers'),
    _s('long-loops', 'Loops',
       'Start a recurring job in its own session, watch it fire on schedule, '
       'and end it when you are done.',
       page='loops', docs='configuration'),
    _s('long-statusline', 'Status line',
       'Model, account, git state, context pressure, memory age and both plan '
       'windows, under your prompt on every turn.',
       page='updates', docs='statusline'),

    # ── the machinery ──
    _s('long-harness', 'Harnesses',
       'One project list and one memory graph across three CLIs, so a Codex '
       'and a Claude session share a workspace.',
       page='harness', docs='harnesses'),
    _s('long-client', "Claude Code's own record",
       'What the CLI keeps about itself: versions, disk used, background '
       'agents and its own settings, all read-only.',
       page='client', docs='troubleshooting'),
    _s('long-handoff', 'Context hand-off',
       'Hand a full conversation to a fresh session, optionally under another '
       'account, seeded with what it needs.',
       page='home', key='K', docs='context-handoff'),
    _s('long-search', 'Search',
       'Full-text search across every transcript on the machine, every '
       'account and every CLI.',
       page='searchp', docs='sessions'),
    _s('long-logs', 'Logs',
       'What archeus itself did and why it failed: its own Claude calls, '
       'background jobs, the scheduler and the proxy.',
       page='logs', docs='troubleshooting'),
    _s('long-paths', 'Paths & limits',
       'Where archeus finds your editor and CLIs, what its own Claude calls '
       'may spend, and how large memory may grow.',
       page='paths', docs='configuration'),
    _s('long-appearance', 'Appearance',
       'Thirty-two palettes, eight skins and four worlds, with an off switch '
       'for motion and for the background scene.',
       page='appearance', docs='desktop'),
    _s('long-updates', 'Updates & schedules',
       'Versions of archeus, your CLIs and the model catalogue, plus the '
       'update checks and auto-memory schedule it runs alone.',
       page='updates', docs='installation'),
    _s('long-tui', 'The terminal UI',
       'Everything here exists in the terminal too, kept in parity by a test '
       'rather than by intention.',
       page='helpp', key='?', docs='tui'),
    _s('long-plugin', 'The plugin',
       'archeus installs as a Claude Code plugin as well, so a session can '
       "reach its own project's memory and history.",
       page='plugins', docs='plugin'),
]

TOURS = {'short': SHORT, 'long': LONG}


def steps(which='short'):
    """The steps of one tour. Unknown name -> the short one, never an error."""
    return TOURS.get(str(which or '').lower(), SHORT)


def names():
    return list(TOURS)


def docs_url(step):
    """The manual page a step points at, or '' when it points nowhere.

    Trailing slash: MkDocs publishes directory URLs, so the form without it is a
    redirect before it arrives.
    """
    return '%s/%s/' % (DOCS_BASE, step['docs']) if step.get('docs') else ''
