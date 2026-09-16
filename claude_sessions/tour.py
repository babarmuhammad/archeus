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
* **LONG** is every function archeus has, each with what it does, what it is
  FOR, and the thing people miss about it. It is a reference you can walk
  rather than read, which is why it is a tour and not a page of prose.

A step is a dict, and the keys are deliberately few:

    id      stable slug — the GUI uses it to resume where you left off
    title   four words or so; it is a heading in three different type scales
    body    two or three sentences. What it does, then what it is FOR.
    page    the GUI page id this step is about (`NAV`'s first field), or ''
    tab     the project tab id, for steps about a project (`TABS`), or ''
    key     the terminal UI key that reaches the same thing, or ''
    docs    the manual page that goes deeper, without the .md, or ''

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
       'archeus is the workspace layer around your coding CLI. Your projects '
       'stop being a stream of chats and become workspaces that remember: '
       'per-project memory, every session you have ever had, and control over '
       'what the next one costs. It drives Claude Code, OpenAI Codex and pi, '
       'and it never replaces them — it launches the real binary.',
       page='home', key='', docs='index'),
    _s('dashboard', 'The dashboard',
       'One screen for the state of everything: quota and burn as gauges, what '
       'is running right now, your projects by recent spend, and the session '
       'you were last in. Start here when you sit down — the Continue tile '
       'usually knows what you want before you do.',
       page='home', docs='dashboard'),
    _s('projects', 'Open a project',
       'A project is a directory archeus has seen a session in. Picking one '
       'opens its own set of tabs — its sessions, its memory, its CLAUDE.md, '
       'its spend. Nothing is configured to make a directory a project; run a '
       'session in it once and it is one.',
       page='home', key='Enter', docs='projects'),
    _s('sessions', 'Every session you have had',
       'Resume, rename, archive or export any conversation in the project, '
       'across every account. This is the reason archeus exists: a transcript '
       'you cannot find is a transcript you paid for twice.',
       tab='sessions', key='s', docs='sessions'),
    _s('memory', 'Memory that survives the session',
       'archeus builds a semantic graph of the project — its modules, its '
       'services, the lessons it has learned — and injects the task-relevant '
       'part into every new session. Build it once from the Memory tab and it '
       'keeps itself current on a schedule.',
       tab='memory', key='m', docs='memory'),
    _s('launch', 'Decide what a session costs',
       'Model, effort, permission mode, thinking budget and which account it '
       'runs under are all decided before the window opens. The same choices '
       'can be pinned per project, so the expensive project and the cheap one '
       'do not get the same defaults by accident.',
       page='settings', key='n', docs='configuration'),
    _s('go', 'Launch one',
       'Pick a project and start a session. archeus opens the unmodified CLI '
       'in its own window with your choices applied, the memory digest '
       'injected and the status line reporting context, spend and quota as you '
       'work.',
       page='home', key='n', docs='quickstart'),
]


# ── every function, and what it is for ───────────────────────
#
# Ordered the way you meet them, not the way the sidebar lists them: what you do
# to a project, then what you install once, then what it all costs, then the
# machinery. Each body says what it IS and then what it is FOR, because the
# second half is the half the screen's own blurb cannot carry.

LONG = [
    _s('long-what', 'What archeus is',
       'The memory and workspace layer for AI coding agents. It sits beside '
       'Claude Code, Codex and pi rather than in front of them — it launches '
       'the real binary with your settings, reads what those tools record, and '
       'adds the three things none of them keep: memory per project, a history '
       'you can search, and a budget you can see.',
       page='home', docs='index'),

    # ── the project ──
    _s('long-dashboard', 'Dashboard',
       'Quota, today\'s burn, tooling health and live activity as four gauges, '
       'over the sessions running right now, your projects and the one to '
       'continue. Use it as the answer to "where was I" and "what is this '
       'costing me" without opening anything.',
       page='home', docs='dashboard'),
    _s('long-live', 'Live sessions',
       'Every session being worked in at this moment, one row each: the '
       'project, who is on it, what tool call it is blocked on this second, '
       'and the shape of its recent activity as coloured ticks. For watching '
       'several agents at once — click a row for the full flow graph.',
       page='home', docs='dashboard'),
    _s('long-sessions', 'Sessions',
       'Every conversation in this project, across every account: resume it, '
       'fork it, rename it, archive it, export it to Markdown, or replay it as '
       'a flow graph. Use rename early — a session called "continue" is a '
       'session you will never find again.',
       tab='sessions', key='s', docs='sessions'),
    _s('long-flow', 'Flow graph',
       'A session replayed on its own clock: prompts, model turns, tool calls, '
       'results, errors and subagent lanes, with play, scrub and zoom. Idle '
       'gaps are clamped, so a twelve-hour session plays in seconds. Use it to '
       'see where a run actually spent its time.',
       tab='sessions', docs='sessions'),
    _s('long-memory', 'Memory',
       'A semantic graph of the project — entities, relations and lessons — '
       'built by Claude and injected into every new session as a compact '
       'digest, with `archeus recall "<topic>"` for the detail. It is what '
       'stops every session starting by re-reading the same eight files.',
       tab='memory', key='m', docs='memory'),
    _s('long-lessons', 'Lessons',
       'What went wrong and what fixed it, mined out of your own transcripts '
       'and held for review before anything is written. Approve one and it '
       'joins the memory graph, so the next session in that project starts '
       'already knowing it.',
       tab='memory', docs='memory'),
    _s('long-claudemd', 'CLAUDE.md',
       'The instruction file block by block, what each block costs in tokens, '
       'which blocks archeus maintains, and every version it has replaced. Use '
       'it when the file has grown past the point where anyone reads it — the '
       'cost column is the argument.',
       tab='claudemd', docs='memory'),
    _s('long-audit', 'Context audit',
       'What ONE turn costs across every surface at once: this project\'s '
       'CLAUDE.md, your global one, the memory digest, the hooks, the MCP tool '
       'definitions. Run it before you wonder why a short question cost so '
       'much.',
       tab='audit', docs='usage'),
    _s('long-review', 'Review',
       'A code review over the working tree, the staged changes or a branch, '
       'run by Claude with the project\'s own memory in scope. For the pass you '
       'want before a commit, not instead of one.',
       tab='review', docs='plan-execute'),
    _s('long-planexec', 'Plan → Execute',
       'One model writes a plan, you approve or edit it, another executes it '
       'step by step with a gate between. For work too big for one turn, where '
       'the expensive mistake is the plan rather than the code.',
       tab='planexec', docs='plan-execute'),
    _s('long-pusage', 'This project\'s spend',
       'The same token history as the account-wide page, narrowed to one '
       'project and one timeline. It is the number to bring to the question '
       'nobody can answer from a monthly total — whether the work this '
       'repository needs is worth what it costs to do it here.',
       tab='pusage', docs='usage'),
    _s('long-repos', 'Repos',
       'Every git repo, submodule and linked worktree under the project, with '
       'branch, dirty count and ahead/behind, read from `.git` without '
       'spawning git. For a workspace that is a parent of repositories rather '
       'than a repository.',
       tab='worktrees', docs='projects'),
    _s('long-tools', 'Tools',
       'The architecture graph of the project as an interactive cluster, '
       'Claude Code\'s own record of it, and the loop file. The graph is worth '
       'opening once per project: it is the shape of the codebase as archeus '
       'understands it, which is also what it injects.',
       tab='tools', docs='architecture'),

    # ── what you install once ──
    _s('long-globalmd', 'Global CLAUDE.md',
       'The instructions read in every session on an account, with the '
       'conventions archeus has noticed in your projects offered for promotion '
       'into it. For the rules that are about YOU rather than about one '
       'codebase.',
       page='globalmd', key='g', docs='memory'),
    _s('long-agents', 'Agents',
       'Subagent definitions — browse the library, write one by hand, or have '
       'Claude draft one from a description. A good subagent is a specialist '
       'you delegate to; the description field is what decides whether it is '
       'ever picked.',
       page='agents', key='a', docs='agents'),
    _s('long-skills', 'Skills',
       'SKILL.md skills: the bundled starters, your own library and the ones '
       'installed in a project. A skill is a procedure you want followed the '
       'same way every time — a release runbook, a review checklist.',
       page='skills', docs='agent-library'),
    _s('long-hooks', 'Hooks',
       'Claude Code hooks per account, from a template or your own: block a '
       'command, format on write, inject context at session start. archeus '
       'installs its own three here too, and can repair them when a path '
       'moves.',
       page='hooks', key='h', docs='hooks'),
    _s('long-mcp', 'MCP servers',
       'Every MCP server configured, its status, and the tool documentation it '
       'can write into your global CLAUDE.md. Worth auditing: an MCP server '
       'you forgot about is tool definitions in every single turn.',
       page='mcp', key='c', docs='mcp'),
    _s('long-plugins', 'Plugins',
       'The marketplaces you have registered and every plugin installed from '
       'them, with what each one contributes. Every install goes through a '
       'review gate first — a plugin is code that runs in your sessions.',
       page='plugins', docs='plugin'),
    _s('long-ostyles', 'Output styles',
       'The output styles Claude Code can wear, and which is active. A style '
       'changes how answers are written, not what the model is; it is the '
       'cheapest way to stop fighting the tone.',
       page='ostyles', docs='configuration'),

    # ── what it costs ──
    _s('long-usage', 'Usage & cost',
       'Token spend and rate limits across every account, by day, by project '
       'and by model, with the plan windows as they actually stand. The '
       'question it answers is which project is expensive, which is rarely the '
       'one you would guess.',
       page='usage', key='u', docs='usage'),
    _s('long-accounts', 'Accounts',
       'Every login, each with its own config directory, credentials, quota, '
       'hooks and plugins. Add a second one and a full 5-hour window stops '
       'being the end of the afternoon.',
       page='accounts', docs='accounts'),
    _s('long-rotation', 'Account rotation',
       'When the account in use fills its window, the next one with headroom '
       'takes over — new work by itself, and a session you are sitting in '
       'either offered the move or moved for you. The status line warns before '
       'the window is spent; a hook catches it if you are already stuck.',
       page='accounts', docs='accounts'),
    _s('long-models', 'Models & providers',
       'The backends a session can run against — Anthropic, a local server, '
       'OpenRouter or OmniRoute — each with its own model and failover list. '
       'For routing the cheap work somewhere cheap without changing how you '
       'work.',
       page='models', docs='providers'),
    _s('long-loops', 'Loops',
       'Start a `/loop` in its own session, watch it fire on its schedule, and '
       'end it. For the recurring job that does not need you: a nightly '
       'review, a metrics refresh.',
       page='loops', docs='configuration'),
    _s('long-statusline', 'Status line',
       'Model, account, git state, context pressure, memory age, spend and '
       'both plan windows, on two lines under your prompt, on every turn. It '
       'is the one surface that tells you a session is going wrong while there '
       'is still time to do something.',
       page='updates', docs='statusline'),

    # ── the machinery ──
    _s('long-harness', 'Harnesses',
       'Every coding CLI archeus drives — whether it is installed, how it is '
       'configured, and the screens only it has. One project list, one memory '
       'graph, three CLIs: a Codex session and a Claude session in the same '
       'directory are the same workspace.',
       page='harness', docs='harnesses'),
    _s('long-client', 'Claude Code\'s own record',
       'What the CLI keeps about itself: versions, how much disk its '
       'transcripts and caches have taken, the background agents it is '
       'running, and its own settings. Read-only, and the first place to look '
       'when the tool disagrees with what you think you configured.',
       page='client', docs='troubleshooting'),
    _s('long-handoff', 'Context hand-off',
       'When the context window fills, hand the conversation to a fresh '
       'session — optionally under another account — seeded with what it needs '
       'rather than with the whole transcript. The successor starts clear '
       'instead of starting where the last one ran out of room.',
       page='home', key='K', docs='context-handoff'),
    _s('long-search', 'Search',
       'Full-text search across every transcript on the machine, every account '
       'and every CLI. For "I solved this three weeks ago and I cannot '
       'remember where".',
       page='searchp', docs='sessions'),
    _s('long-logs', 'Logs',
       'What archeus itself did and why it failed — its own Claude calls, '
       'background jobs, the scheduler, the proxy. The first place to look '
       'when something did not happen, which is harder to notice than '
       'something that broke.',
       page='logs', docs='troubleshooting'),
    _s('long-paths', 'Paths & limits',
       'Where archeus finds your editor and your CLIs, what its own Claude '
       'calls may spend, and how large the memory graph may grow. The spend '
       'cap is the one to set on day one.',
       page='paths', docs='configuration'),
    _s('long-appearance', 'Appearance',
       'Thirty-two palettes, eight skins and four worlds — a palette answers '
       '"what colours", a skin answers "what is this application". Motion and '
       'the background scene both have an off switch, and both honour '
       '`prefers-reduced-motion`.',
       page='appearance', docs='desktop'),
    _s('long-updates', 'Updates & schedules',
       'Versions of archeus, of your CLIs and of the model catalogue, plus '
       'what archeus does on its own: update checks, notifications and the '
       'auto-memory schedule. Auto-memory is the setting that makes memory '
       'something you stop thinking about.',
       page='updates', docs='installation'),
    _s('long-tui', 'The terminal UI',
       'Everything here exists in the terminal too — `archeus` with no '
       'arguments — and the two are kept in parity by a test rather than by '
       'intention. Press `?` there for every key.',
       page='helpp', key='?', docs='tui'),
    _s('long-plugin', 'The plugin',
       'archeus also installs as a Claude Code plugin, so a session can reach '
       'its own project\'s memory and history without leaving the terminal. It '
       'ships no hooks on purpose — the hook manager already owns those, and '
       'one settings entry with two owners is a bug waiting to happen.',
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
