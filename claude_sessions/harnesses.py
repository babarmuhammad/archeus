"""Which agent CLI a session belongs to, and what that CLI can do.

A *provider* is an endpoint: `config.provider_env` repoints `ANTHROPIC_BASE_URL`
and the same `claude` binary talks to a different model. A *harness* is the
binary itself plus the conventions it keeps on disk — where its transcripts
live, what its hooks file is called, which instructions file it reads. The two
axes are orthogonal and the words are not interchangeable: OmniRoute is a
provider, Codex is a harness.

**A harness rides on `cfgdir`.** That is the whole design. `cfgdir` is already
threaded through ~40 HTTP endpoints, `store.project_folder`,
`sessions.account_folders_for`, `hooks.settings_path_for`, `config.account_env`
and the launcher's choice line, because it is how archeus already addresses one
Claude *account*. Codex's equivalent is `CODEX_HOME` and pi's is
`PI_CODING_AGENT_DIR`, so `of(cfgdir)` is a lookup rather than a new parameter
on every one of those call sites — and session ids stop being able to collide
across harnesses for free, since archeus's own per-session sidecars are already
keyed by the directory.

A capability is `(ok, why)`, never a bare bool: a surface a harness cannot do is
shown greyed WITH THE REASON, and a bare False leaves the UI nothing to print.
A descriptor lists only what it cannot do; everything else is `(True, '')`.
"""

import os

from . import config as _c

#: every capability the UI may gate on, with what it means on screen. A
#: descriptor naming a key that is not here is a typo that would otherwise read
#: as "supported".
CAPS = {
    'sessions':         'list past sessions',
    'resume':           'resume a session',
    'fork':             'fork a session',
    'archive':          'archive a session',
    'hooks':            'run scripts on lifecycle events',
    'recall':           'inject task-scoped memory per prompt',
    'skills':           'SKILL.md skills',
    'agents':           'subagent definitions',
    'rules':            'path-scoped rules files',
    'mcp':              'MCP servers',
    'plugins':          'plugins and marketplaces',
    'checkpoints':      'per-session file history',
    'statusline':       'a status line',
    'output_styles':    'output styles',
    'client_state':     'what the CLI records about itself',
    #: what was spent, counted out of the CLI's own transcripts. Every harness
    #: folds tokens into the same `usage_by_model` shape, so this is true for
    #: all three — it was off for two of them only because the page it gated
    #: also carried the rate-limit rail below, which is a different question.
    'usage':            'token spend, by day and by project',
    #: the plan's own windows and when they reset. Two sources, because the two
    #: CLIs that have windows publish them differently: Claude Code's come from
    #: the OAuth usage endpoint the poller hits, Codex's are recorded in its own
    #: rollout and are read from there — it has no endpoint and no subcommand
    #: that prints them. `codex doctor` was named here as the source and DOES
    #: NOT report limits; checked against the installed 0.142, whose sections
    #: are Notes / Environment / Configuration / Updates / Connectivity /
    #: Background Server. pi genuinely has none: it bills per provider.
    'plan_limits':      'plan usage and reset windows',
    'versions':         'install and update the CLI',
    'accounts':         'more than one login',
    'effort':           'a reasoning-effort setting',
    'permission_modes': 'permission modes',
    #: Codex's second axis. It is NOT the permission mode wearing another
    #: name: `-a` says when the model must ASK, `-s` says what a command may
    #: touch when it does not, and a Codex user changes the second far more
    #: often. Claude Code folds both into the permission mode.
    'sandbox':          'a filesystem sandbox level',
    'named_session':    'naming a session at launch',
    'worktree':         'launching into a git worktree',
    'budget_cap':       'a spend cap on one call',
    'headless_json':    'one-shot calls that return JSON',
}

#: the harness every existing installation is, and the default for anything
#: archeus cannot place.
DEFAULT = 'claude'


#: EVERY name a CLI's binary can have, on every platform, deliberately NOT
#: branched on `os.name`.
#:
#: The branch cost nothing in production and broke fifteen tests on POSIX: the
#: suite is written Windows-first (that is the primary platform and the fixtures
#: say `codex.exe`), so on Linux `exe()` could not find a fixture it had just
#: written and `is_inference(['C:/x/claude.exe', '-p', …])` answered False for a
#: call that plainly is one. The same argv got two different answers depending
#: on which machine asked, which is worse than either answer.
#:
#: Unconditional is free. `shutil.which('claude.exe')` on Linux is a miss and
#: the bare name matches on the next pass, so a real POSIX install resolves
#: exactly as before — and a file genuinely named `claude.exe` there (a mounted
#: Windows volume, WSL interop) is one this should find anyway. Same reasoning
#: as pinning `term.BACKEND` for the POSIX port: keep one shape everywhere
#: rather than re-scripting the tests that encode it.
def _claude_exe_names():
    return ('claude.exe', 'claude')


HARNESSES = {
    'claude': {
        'id': 'claude',
        'label': 'Claude Code',
        'exe_names': _claude_exe_names(),
        'exe_setting': 'claude_exe',
        #: the environment variable that picks one home, and where it is by
        #: default. Claude Code's own precedence — env first — is mirrored by
        #: config.get_config_dir.
        'home_env': 'CLAUDE_CONFIG_DIR',
        #: RELATIVE to the user profile and resolved in home_dir(), never a
        #: module-level absolute: a constant derived from mutable state is a
        #: cache with no invalidation, and this one would bind to whatever
        #: HOME was set when the module happened to be imported.
        'home_rel': ('.claude',),
        'instructions_file': 'CLAUDE.md',
        #: what makes an argv an inference call for this harness. Claude Code
        #: takes a flag; Codex's headless mode is a SUBCOMMAND, which is why a
        #: flag-only test answered False for every one of its calls.
        'inference_flags': ('-p', '--print'),
        'inference_verbs': (),
        #: a key in the environment shadows the account login, so the CLI would
        #: authenticate as the key's owner whatever home it was pointed at.
        'env_pops': ('ANTHROPIC_API_KEY',),
        #: where the binary installs, RELATIVE to the user profile, with `%s`
        #: for the executable name. Relative and not `~` so the sandbox that
        #: repoints `_USERPROFILE` actually contains the search — an absolute
        #: `expanduser` would find the real installation from inside a test.
        'exe_globs': ('.local/bin/%s',),
        #: one transcript record -> the shared stats dict. Named rather than
        #: inlined in the parser because the record SHAPE is the harness's:
        #: `message.model`, `gitBranch` and `isApiErrorMessage` are Claude
        #: Code's field names, not a universal transcript's.
        'fold': 'sessions._fold_claude',
        #: the four other answers that are the harness's rather than archeus's,
        #: resolved the same late way. Each is what its seam calls once the
        #: file or the home has been placed: listing a project's sessions,
        #: naming one session's transcript, listing the projects a home knows,
        #: and answering whether it knows ONE — asked per project, so it may
        #: not be `enc in projects(home)`.
        'scan': 'sessions._scan_claude',
        'transcript_path': 'store._transcript_claude',
        'projects': 'store._projects_claude',
        'has_project': 'store._has_project_claude',
        #: the ONE harness whose argv is not a descriptor entry, because
        #: `main.build_launch_command` IS its builder — a hundred and forty
        #: lines of its flag vocabulary that the dispatch deliberately sits
        #: below rather than trying to generalise.
        'launch_argv': 'main.build_launch_command',
        #: where a SKILL.md goes, relative to the home and to a project.
        #: The FORMAT is the same everywhere — the Agent Skills standard —
        #: so a skill is installed by copying it into each harness's roots,
        #: not by translating it.
        'skills_rel': ('skills',),
        'project_skills_rel': ('.claude', 'skills'),
        #: the effort scale this CLI actually accepts, and where its model list
        #: comes from. Both are the harness's own: Claude Code's `--effort`
        #: takes `max` and `ultracode`, which Codex rejects, and a priced
        #: Anthropic model card means nothing next to `gpt-5.5`. '' is the
        #: leading 'default' stop in every scale.
        'efforts': ('', 'low', 'medium', 'high', 'xhigh', 'max', 'ultracode'),
        #: '' = the live Anthropic catalogue `gui` already ships; anything else
        #: is a dotted name resolved through `impl`.
        'models': '',
        #: `models` is what this install has RUN; `catalogue` is what it could.
        #: Two fields because they answer differently on a fresh machine — the
        #: first is empty and the second is not — and the picker shows both,
        #: labelled, rather than one list that cannot say where a row came from.
        #: '' here for the same reason `models` is: `gui` already ships
        #: Anthropic's priced cards in the boot payload.
        'catalogue': '',
        #: '' = `config.LAUNCH_PRESETS`, which is (model, effort) over Anthropic
        #: ids. Every other harness names its own tuple: a preset is a pair of
        #: values from THIS CLI's two scales, so it cannot be translated.
        'presets': (),
        #: '' = `versions.py`, which is Claude Code's own updater and already a
        #: page. The others each answer with one subprocess.
        'doctor': '',
        #: what to run to sign a home in, after the exe. Claude Code has no
        #: login SUBCOMMAND — you start it and type /login — so an empty
        #: tuple is 'just open the CLI there', which is what the accounts
        #: manager already did. A tuple rather than three functions because
        #: the difference between these CLIs is one argument.
        'login_argv': (),
        #: 'is this home signed in', resolved through `impl` like `doctor`.
        #: '' = read the OAuth token `usage`/`quota` already read.
        'auth_state': '',
        #: '' = this harness has no rollout to read windows out of; its source is
        #: the OAuth poller in `usage.py`.
        'rate_limits': '',
        #: '' = `config.PERMS` / `PERM_LABELS`, which are Claude Code's own.
        #: A permission vocabulary cannot be translated between CLIs, for the
        #: same reason `efforts` could not: `plan` has no Codex equivalent and
        #: `untrusted` has no Claude one.
        'perms': (), 'perm_labels': (),
        'sandboxes': (), 'sandbox_labels': (),
        #: the ONE thing Claude Code has no separate control for: its
        #: permission mode decides both when to ask and what a command may
        #: touch, where Codex splits the two across -a and -s.
        'caps': {'sandbox': (False, "Claude Code's permission mode covers "
                                    'this; it has no separate sandbox '
                                    'level.')},
    },
    'codex': {
        'id': 'codex',
        'label': 'Codex',
        'exe_names': ('codex.exe', 'codex'),   # see _claude_exe_names: not branched
        'exe_setting': 'codex_exe',
        'home_env': 'CODEX_HOME',
        'home_rel': ('.codex',),
        #: not CLAUDE.md. Codex reads `AGENTS.md`, and it does not document an
        #: import syntax, so the memory block is written into it rather than
        #: referenced from it.
        'instructions_file': 'AGENTS.md',
        #: no flag: `codex exec` IS the headless mode, `e` its alias, and
        #: `review` spends the same quota without being a session at all.
        'inference_flags': (),
        'inference_verbs': ('exec', 'e', 'review'),
        'env_pops': ('OPENAI_API_KEY',),
        #: Codex installs under a directory named by a hash of the build and
        #: leaves the previous one in place, so the newest match wins. This is
        #: the reason `exe()` may never cache: the path changes on every update.
        'exe_globs': ('.local/bin/%s', 'AppData/Local/OpenAI/Codex/bin/*/%s'),
        'fold': 'codex.fold',
        'scan': 'codex.scan',
        'transcript_path': 'codex.transcript_path',
        'projects': 'codex.projects',
        'has_project': 'codex.has_project',
        'launch_argv': 'codex.launch_argv',
        'skills_rel': ('skills',),
        #: `.agents/skills` is the CROSS-HARNESS convention, which is why
        #: pi names the same directory: one copy in a project serves both.
        'project_skills_rel': ('.agents', 'skills'),
        #: `minimal` at the bottom and no `max`/`ultracode` — read out of the
        #: binary's own enum, not assumed from Claude Code's.
        'efforts': ('', 'minimal', 'low', 'medium', 'high', 'xhigh'),
        'models': 'codex.models',
        'catalogue': 'codex.catalogue',
        'doctor': 'codex.doctor',
        'login_argv': ('login',),
        'auth_state': 'codex.auth_state',
        'rate_limits': 'codex.rate_limits',
        #: read out of `codex --help` on the installed 0.142, not mapped from
        #: Claude Code's. `on-failure` is offered by the binary and NOT here:
        #: its own help marks it DEPRECATED and says to prefer on-request.
        'perms': ('', 'untrusted', 'on-request', 'never'),
        'perm_labels': ('Codex default', 'trusted commands only',
                        'the model decides when to ask', 'never ask'),
        'sandboxes': ('', 'read-only', 'workspace-write', 'danger-full-access'),
        'sandbox_labels': ('Codex default', 'read only', 'write in the workspace',
                           'no sandbox'),
        #: three stops over Codex's OWN two scales, and every model id here is
        #: one the catalogue publishes rather than one typed from a blog post.
        #: A preset that names a model this install cannot reach is dropped by
        #: the picker rather than offered — see `gui_api.api_harness_models`.
        'presets': (
            ('Quick', 'Cheap and fast, for a small edit.',
             {'model': 'gpt-5.6-luna', 'effort': 'low'}),
            ('Everyday', 'The balance most sessions want.',
             {'model': 'gpt-5.6-terra', 'effort': 'medium'}),
            ('Deep', 'Slow and thorough, for a design or a hard bug.',
             {'model': 'gpt-6-astra', 'effort': 'xhigh'}),
        ),
        #: what archeus cannot do HERE, and why — the reason is what the screen
        #: prints, so each says which side the gap is on. The first group is
        #: structural (Codex has no such thing); the second is archeus reading
        #: and writing Claude Code's file for something Codex keeps elsewhere.
        'caps': {
            'output_styles': (False, 'Output styles are a Claude Code feature.'),
            'client_state':  (False, 'Codex records its own state in SQLite, '
                                     'not in .claude.json.'),
            #: `usage` is NOT here: `codex.fold` fills the same `usage_by_model`
            #: every other harness does, so the spend cards are real. What Codex
            #: does not publish is the WINDOW — its rate limits come back on the
            #: API response and `codex doctor` prints the rest, neither of which
            #: is the Anthropic OAuth endpoint the plan rail reads.
            #: `mcp`, `plugins` and `versions` are NOT here, and all three were
            #: WRONG rather than cautious — checked against the installed 0.142:
            #: `codex mcp list --json/add/remove` is full CRUD, `codex plugin
            #: list/marketplace` reads every marketplace, and `codex doctor`
            #: prints `updates X available (current Y)`. All three run offline
            #: and need no login.
            #: hooks is the one that survives the check. Codex's wire contract
            #: is byte-identical to Claude Code's — the binary carries the same
            #: `session_id`/`transcript_path`/`hook_event_name`/`stop_hook_active`
            #: payload field names — but every handler in `hooks.json` is gated
            #: on an undocumented `trusted_hash`, and a wrong one is REFUSED
            #: SILENTLY. A hook archeus writes that never fires and never says so
            #: is worse than no hook, so this stays off until the hash is known.
            'hooks':         (False, 'Codex gates each hook on an undocumented '
                                     'trusted_hash, and a wrong one fails '
                                     'silently rather than erroring.'),
            'agents':        (False, 'Codex keeps subagents in .agents, with no '
                                     'CLI to manage them.'),
            #: auto-memory's OTHER delivery. The digest reaches Codex fine —
            #: `instructions_files()` puts it in AGENTS.md — but the path-scoped
            #: half does not: `.claude/rules/*.md` with a `globs:` header is
            #: Claude Code's mechanism, and Codex has no config key for one
            #: (`model_instructions_file` and `project_doc_fallback_filenames`
            #: are whole files, not path-scoped). So the rule FILES are written
            #: for Claude Code and Codex gets the always-on digest instead.
            'rules':         (False, 'Codex has no path-scoped rules; it reads '
                                     'the memory digest in AGENTS.md instead.'),
            #: the launch modal's own gaps, checked against `codex --help` on
            #: the installed binary rather than assumed from Claude Code's
            #: flags. Codex HAS `-m`, `-a` and a reasoning-effort config key,
            #: so those three are not here.
            'named_session': (False, 'Codex names a session afterwards, with '
                                     '`thread name set`, not at launch.'),
            'worktree':      (False, 'Codex has no worktree flag; open the '
                                     'worktree as its own project.'),
        },
    },
    'pi': {
        'id': 'pi',
        'label': 'pi',
        #: npm installs a `.cmd` shim on Windows and a shebang script beside
        #: it; `shutil.which` finds whichever the shell would run.
        'exe_names': ('pi.cmd', 'pi.exe', 'pi'),   # see _claude_exe_names
        'exe_setting': 'pi_exe',
        'home_env': 'PI_CODING_AGENT_DIR',
        #: TWO components, unlike the other two: pi's home is `~/.pi/agent`,
        #: and `~/.pi` holds other things. `home_rel` was always a tuple for
        #: exactly this.
        'home_rel': ('.pi', 'agent'),
        #: pi reads AGENTS.md *and* CLAUDE.md, walking up the tree. AGENTS.md
        #: is what archeus writes: it is the file pi shares with Codex, so one
        #: block serves both, and writing CLAUDE.md here would put a second
        #: copy of the same block in front of Claude Code.
        'instructions_file': 'AGENTS.md',
        'inference_flags': ('-p', '--print'),
        'inference_verbs': (),
        #: pi resolves a key per provider and the flag is per provider too, so
        #: there is no single variable to clear the way ANTHROPIC_API_KEY
        #: shadows a Claude login. Its own `auth.json` under the home is the
        #: login, and pointing at a home therefore picks one.
        'env_pops': (),
        #: npm's global bin, on every platform it can be. Not `.local/bin`
        #: alone: pi ships as an npm package, and `npm prefix -g` is where its
        #: shim lands — which is `AppData/Roaming/npm` on Windows and one of the
        #: other two elsewhere. Unbranched for the reason `exe_names` is: the
        #: fixtures are Windows-shaped, so a branch here meant POSIX could not
        #: find a binary the test had just written, and the cost of carrying all
        #: three is one glob that misses.
        'exe_globs': ('AppData/Roaming/npm/%s',
                      '.local/bin/%s', '.npm-global/bin/%s'),
        'fold': 'pi.fold',
        'scan': 'pi.scan',
        'transcript_path': 'pi.transcript_path',
        'projects': 'pi.projects',
        'has_project': 'pi.has_project',
        'launch_argv': 'pi.launch_argv',
        #: archeus's OWN one-shot calls (memory, lessons, generation). Only a
        #: harness that names one can run them; Claude Code's is built in
        #: `llmcall.build_headless_args`. ponytail: Codex has none yet — `codex
        #: exec` logs progress on stderr, which the runner merges into the
        #: answer; add it with `--output-last-message` when a Codex user asks.
        'headless_argv': 'pi.headless_argv',
        'skills_rel': ('skills',),
        'project_skills_rel': ('.agents', 'skills'),
        #: `--thinking` takes a LEVEL, and the scale is its own: `off` at the
        #: bottom and `max` at the top, with no `ultracode`.
        'efforts': ('', 'off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'),
        'models': 'pi.models',
        'catalogue': 'pi.catalogue',
        'doctor': 'pi.doctor',
        #: no login subcommand; `pi` prompts on first use and writes auth.json
        'login_argv': (),
        #: pi bills per provider, so there is no one window to read.
        'auth_state': 'pi.auth_state',
        'rate_limits': '',
        'perms': (), 'perm_labels': (),
        'sandboxes': (), 'sandbox_labels': (),
        #: pi is provider-neutral, so its presets pick a PROVIDER as much as a
        #: model — `provider/id` is the form its own `--model` takes. Whichever
        #: of these the user has a key for survives the catalogue filter; the
        #: rest are dropped rather than offered as a login prompt.
        'presets': (
            ('Quick', 'Cheap and fast, for a small edit.',
             {'model': 'google/gemini-3.1-flash-lite', 'effort': 'low'}),
            ('Everyday', 'The balance most sessions want.',
             {'model': 'anthropic/claude-sonnet-5', 'effort': 'medium'}),
            ('Deep', 'Slow and thorough, for a design or a hard bug.',
             {'model': 'openai/gpt-5.5', 'effort': 'high'}),
        ),
        #: pi's gaps are wider than Codex's and differently shaped: it has no
        #: MCP and no hooks AT ALL (extensions are TypeScript modules it loads
        #: itself). `skills` is not listed because archeus installs into pi's
        #: own roots — NOT, as a first reading of its docs suggested, because pi
        #: reads `~/.claude/skills`: that is opt-in through its settings file,
        #: and a capability that depends on the user having configured something
        #: is not one archeus may claim.
        'caps': {
            'archive':       (False, 'pi has no archive; a session is deleted '
                                     'or kept.'),
            'checkpoints':   (False, 'pi branches inside one session file '
                                     'instead of snapshotting files.'),
            'hooks':         (False, 'pi has no hooks; it loads TypeScript '
                                     'extensions instead.'),
            'mcp':           (False, 'pi has no MCP client.'),
            'plugins':       (False, 'pi installs extension packages with '
                                     '`pi install`, not marketplaces.'),
            'agents':        (False, 'pi has no subagents.'),
            'output_styles': (False, 'Output styles are a Claude Code feature.'),
            'sandbox':       (False, 'pi has no sandbox flag; it asks per tool '
                                     'call instead.'),
            #: same split as Codex's, and for the same reason: pi walks the tree
            #: for AGENTS.md and CLAUDE.md, which is a whole file per directory,
            #: not a rule selected by the path you just opened.
            'rules':         (False, 'pi has no path-scoped rules; it reads the '
                                     'memory digest in AGENTS.md instead.'),
            'client_state':  (False, 'pi records no equivalent of '
                                     '.claude.json.'),
            #: same split as Codex's: `pi.fold` counts tokens, so the spend
            #: cards are real; what pi has no notion of is one PLAN with one
            #: window, because it bills per provider.
            #: the sentence no longer mentions "this rail reads Anthropic's":
            #: Codex publishes windows too now, read out of its rollout, so the
            #: rail is not Anthropic's alone and the contrast was misleading.
            #: pi's gap is structural rather than a source archeus cannot reach.
            'plan_limits':   (False, 'pi bills per provider, so there is no '
                                     'single plan window to report.'),
            #: `versions` is NOT here: `pi update` is a real command and the
            #: installed version comes back from `pi --version`.
            #: pi HAS `-n` and `--model` and a `--thinking` level, so naming,
            #: the model and effort all work. What it has no notion of is a
            #: permission MODE — `--approve` trusts project-local files, which
            #: is a different question — and a worktree.
            'permission_modes': (False, 'pi has no permission modes; it asks '
                                        'per tool call.'),
            'worktree':      (False, 'pi has no worktree flag; open the '
                                     'worktree as its own project.'),
            #: `recall` and `statusline` are NOT declared, though pi has
            #: neither. Both are already covered — recall by `hooks`, which is
            #: what runs it — and neither has a surface that could grey: the
            #: statusline card is per Claude ACCOUNT, and pi never appears on
            #: it. A capability nothing reads is a promise nothing keeps, which
            #: `test_a_capability_some_harness_lacks_is_consumed_by_something`
            #: is there to catch.
        },
    },
}


def home_dir(hid=None):
    """Where this harness keeps its state, by default."""
    return os.path.join(_c._USERPROFILE, *descriptor(hid)['home_rel'])


def ids():
    """Every harness archeus knows about, the default first."""
    return [DEFAULT] + [k for k in sorted(HARNESSES) if k != DEFAULT]


def descriptor(hid=None):
    """One descriptor by id. An unknown id is the default rather than an error:
    a harness id reaches this from settings written by another version."""
    return HARNESSES.get(hid or DEFAULT) or HARNESSES[DEFAULT]


def of(cfgdir=None):
    """The descriptor for the home *cfgdir* belongs to.

    Compared against each harness's known homes by resolved path, so a trailing
    slash or a different case cannot split one home into two. Anything archeus
    cannot place is Claude Code — every home that exists today is.
    """
    if cfgdir:
        want = os.path.normcase(os.path.abspath(os.path.expanduser(cfgdir)))
        for hid, home in _homes():
            if os.path.normcase(os.path.abspath(home)) == want:
                return descriptor(hid)
    return descriptor(DEFAULT)


def of_path(path):
    """The descriptor for whichever harness OWNS this file.

    A transcript is reached as a path far more often than as an account, and
    every one of them sits under a home — `<home>/projects/<enc>/<sid>.jsonl`
    for Claude Code, and whatever the rollout column says for Codex, which is
    also under its home. Placing the file rather than threading a harness id
    through `_parse_session` and its five callers is what keeps the hot path's
    signature alone.

    Only the OTHER harnesses' homes are compared, and that is still a
    measurement rather than a shortcut: Claude Code is the answer for anything
    unplaceable, so naming it would add nothing.

    It walks every home of those harnesses rather than only the built-in one.
    That costs one settings read on a function `store.transcript_path` calls
    per session row — but the alternative is that a transcript under a SECOND
    Codex home is placed as Claude Code's, which gets both its path and its
    token fold wrong while looking like it worked. The read is also not new to
    the row: `sessions.account_folders_for` calls `instances()` immediately
    before, and `_parse_session` opens a whole JSONL immediately after.

    ponytail: one settings read per row. Memoise `_homes()` per request if a
    very long session list ever measures slow.
    """
    if path:
        p = os.path.normcase(os.path.abspath(path))
        best = None
        for hid, home in _homes():
            if hid == DEFAULT:
                continue
            h = os.path.normcase(os.path.abspath(home))
            if p.startswith(h + os.sep) and (best is None or len(h) > len(best[1])):
                best = (hid, h)
        if best:
            return descriptor(best[0])
    return descriptor(DEFAULT)


def impl(key, hid=None):
    """The function one harness supplies for *key*, resolved late.

    A dotted name in the table rather than the function itself: `sessions` and
    `store` both import this module, so naming a function here directly would
    be a cycle.
    """
    mod, _dot, fn = descriptor(hid)[key].partition('.')
    import importlib
    return getattr(importlib.import_module('.' + mod, __package__), fn)


def homes(hid=None):
    """[(name, home dir)] for ONE harness — its built-in home first, then the
    extras the user added, deduped by resolved path.

    A home is what carries a login, for every one of these CLIs: Claude Code
    picks one with `CLAUDE_CONFIG_DIR`, Codex with `CODEX_HOME`, pi with
    `PI_CODING_AGENT_DIR`, and `config.account_env` already writes whichever the
    descriptor names. So "more than one account" is the same mechanism for all
    three, and this is the one place that says so.

    The built-in home is named after the harness LABEL rather than 'default',
    which is what keeps a single-home machine looking exactly as it did: this
    returns `('Codex', ~/.codex)` today and still will.
    """
    d = descriptor(hid)
    if d['id'] == DEFAULT:
        # via the module, never by value: the test sandbox patches this name
        return _c.all_config_dirs()
    return _c.named_dirs(d['label'], home_dir(d['id']),
                         (_c.load_settings().get('homes') or {}).get(d['id']))


def _homes():
    """[(harness id, home dir)] for every home archeus knows, of every harness."""
    return [(hid, d) for hid in ids() for _n, d in homes(hid)]


def disabled():
    """The harness ids the user has switched off, as a set.

    A harness turned off here is off EVERYWHERE — not only in the launch
    picker, but in the project list, the sessions list, the usage table and the
    instructions files that get a memory block. Hiding it from one surface and
    leaving it in the others is what makes a setting feel broken.

    `DEFAULT` can never be in it. Claude Code is not only a harness archeus
    lists: it is the binary archeus itself shells out to for memory extraction,
    lessons, CLAUDE.md generation and every other AI feature, so switching it
    off would hide the app's own engine while it kept running.
    """
    got = _c.load_settings().get('harnesses_disabled') or []
    return {h for h in got if h != DEFAULT}


def instances():
    """[(display name, home dir, harness id)] — every home, every harness the
    machine has and the user has not switched off.

    The harness-aware sibling of `config.all_config_dirs()`, which deliberately
    stays Claude-only: every one of ITS callers means "accounts", and fanning a
    Claude-shaped write across a Codex home would write a settings.json that
    Codex never reads.
    """
    off = disabled()
    out = []
    for hid in ids():
        if hid in off or (hid != DEFAULT and not exe(hid)):
            continue
        out += [(n, d, hid) for n, d in homes(hid)]
    return out


def launch_targets():
    """[{key, kind, label, hid, cfgdir, provider, caps}] — everything a new
    session can start ON, in the order the picker shows them.

    ONE list for two axes that are genuinely different questions, which is why
    the rows carry `kind` rather than being two lists: a HARNESS is a different
    binary with a different flag vocabulary, and a PROVIDER is the same binary
    pointed at a different endpoint. The target decomposes back into `cfgdir`
    and `provider` — the two fields `/api/launch` has always carried — so a tab
    strip over these rows needs no new field on the launch payload at all.

    A Claude account is NOT a row: an account is which login, not which tool,
    and the modal has had its own account chips since long before there was a
    second harness. Splitting five accounts into five tabs would bury the
    question this strip exists to ask.
    """
    settings = _c.load_settings()
    off = disabled()
    off_p = set(settings.get('providers_disabled') or [])
    rows = []
    for hid in ids():
        if hid in off or (hid != DEFAULT and not exe(hid)):
            continue
        # `cfgdir` is what the launch payload carries and `of()` is what turns
        # it back into a harness, so a non-Claude row names its home here.
        # Claude Code's stays EMPTY on purpose: that is the row whose account
        # chips pick the home, and pinning one would override the choice.
        rows.append({'key': hid, 'kind': 'harness', 'label': descriptor(hid)['label'],
                     'hid': hid, 'cfgdir': '' if hid == DEFAULT else home_dir(hid),
                     'provider': '',
                     'caps': {k: list(cap(hid, k)) for k in CAPS}})
    for prof in (settings.get('providers') or []):
        pid = prof.get('id') or ''
        if not pid or pid in off_p:
            continue
        # a provider RIDES on Claude Code — it repoints the base URL of the
        # same binary — so it inherits that harness's capabilities wholesale.
        rows.append({'key': 'provider:' + pid, 'kind': 'provider',
                     'label': prof.get('name') or '(unnamed)',
                     'hid': DEFAULT, 'cfgdir': '', 'provider': pid,
                     'caps': {k: list(cap(DEFAULT, k)) for k in CAPS}})
    return rows


def skill_roots():
    """[(display name, directory)] — the personal skills root of every home an
    installed, enabled harness has.

    The shape `install_personal` already fanned over, one axis wider: a skill
    you wrote is a property of YOU, not of whichever login — or now, whichever
    CLI — happened to be active when you saved it. The format is the same
    everywhere (the Agent Skills standard), so this is a copy per root rather
    than a translation.
    """
    return [(name, os.path.join(home, *descriptor(hid)['skills_rel']))
            for name, home, hid in instances()]


def auth_state(cfgdir=None):
    """'ok' | 'missing' | 'unknown' — is THIS home signed in?

    Per home rather than per harness, because that is the question the accounts
    list asks once per row. Claude Code's answer is the OAuth token `quota`
    already reads, which is a file read and not a request — the rule that
    archeus never writes `.credentials.json` and never refreshes a token holds
    here too.
    """
    d = of(cfgdir)
    if d['auth_state']:
        return impl('auth_state', d['id'])(_c.resolve_config_dir(cfgdir))
    from . import usage
    try:
        if not usage._read_token(cfgdir):
            return 'missing'
        return 'expired' if usage._token_expired(cfgdir) else 'ok'
    except Exception:
        return 'unknown'


def login_argv(hid=None):
    """The argv that signs a home in. The home itself comes from
    `config.account_env`, which already writes the right variable."""
    d = descriptor(hid)
    exe_path = exe(d['id'])
    return ([exe_path] + list(d['login_argv'])) if exe_path else []


def managed_dir_names():
    """The directory names that mark a path as archeus-managed.

    DERIVED from the registry rather than written out, because the literal
    `'.claude'` that stood here was the whole list and `.agents` — which BOTH
    Codex and pi declare for project-scoped skills — was missing, so a
    project-scoped Codex skill could not be deleted. A fourth CLI registering
    its own needs no edit here.
    """
    return ({d['project_skills_rel'][0] for d in HARNESSES.values()}
            | {_c.WORKDIR})


def project_skill_roots(project_path):
    """Every directory a project skill has to land in, DEDUPED.

    `.agents/skills` is the cross-harness convention and both Codex and pi read
    it, so a project with all three installed gets two directories, not three —
    and the deduplication is by path rather than by harness, because which
    harnesses happen to share one is theirs to decide.
    """
    out = []
    for _n, _home, hid in instances():
        d = os.path.join(project_path, *descriptor(hid)['project_skills_rel'])
        if d not in out:
            out.append(d)
    return out


def default_target():
    """The key `launch_targets()` row the picker opens on.

    Claude Code unless the user says otherwise, and it falls back to Claude Code
    by NAME rather than to `rows[0]` when the saved key names something that is
    gone. The two are the same answer today — `ids()` puts the default first and
    nothing filters it out — which is exactly why naming it is worth the
    characters: a machine that had Codex uninstalled should open on the harness
    it still has, not on whatever happens to sort first if that order ever
    changes.
    """
    want = (_c.load_settings().get('launch_default') or '').strip()
    return want if want in [r['key'] for r in launch_targets()] else DEFAULT


def exe(hid=None):
    """The binary for one harness, or None. Setting override > default install
    path > PATH, the shape `config.get_claude_exe` has always had — and
    RESOLVED EVERY TIME, never cached: Codex installs under a hashed directory
    that changes on every update, so a stored absolute path goes stale in
    silence."""
    import glob as _glob
    import shutil
    d = descriptor(hid)
    override = (_c.load_settings().get(d.get('exe_setting') or '') or '')
    if override and os.path.exists(override):
        return override
    for name in d['exe_names']:
        found = []
        for pat in d.get('exe_globs', ()):
            found += _glob.glob(os.path.normpath(
                os.path.join(_c._USERPROFILE, pat % name)))
        if found:
            # Codex's install directory is named by a hash of the build and the
            # previous one is left behind, so the newest match is the one that
            # `codex update` just wrote.
            return max(found, key=os.path.getmtime)
    for name in d['exe_names']:
        found = shutil.which(name)
        if found:
            return found
    return None


def instructions_files():
    """Every instructions file an INSTALLED harness reads, deduped, Claude
    Code's first.

    The memory digest goes into each of them, which is the whole point of one
    graph behind three CLIs: the block is archeus's, the graph is the project's,
    and which binary is about to read it is not the memory layer's business.

    Gated on `instances()` rather than on the table, so a machine with no Codex
    never grows an `AGENTS.md` it has no reader for. pi reads BOTH files and
    therefore needs no entry of its own beyond the one it declares — writing a
    second copy of the same block for it is what a per-harness fan-out would
    have done.
    """
    out = []
    for _n, _d, hid in instances():
        f = descriptor(hid)['instructions_file']
        if f not in out:
            out.append(f)
    return out or [descriptor(DEFAULT)['instructions_file']]


def cap(hid, key):
    """(ok, why) for one capability. Unlisted means supported."""
    if key not in CAPS:
        raise KeyError('no such capability: %r' % (key,))
    got = descriptor(hid)['caps'].get(key)
    return got if got else (True, '')


def home_env(cfgdir=None):
    """{var: dir} selecting one home for a child process of that harness."""
    d = of(cfgdir)
    return {d['home_env']: _c.resolve_config_dir(cfgdir)}


def of_argv(args):
    """The descriptor for the binary this argv names, or None.

    Split out of `is_inference` because "which harness is this call" and "does
    this call spend quota" are two questions and only the second one was
    answerable: `quota` had to read `CLAUDE_CONFIG_DIR` out of a prepared env to
    guess the account, and that variable is AMBIENT — `account_env` copies
    `os.environ` — so a Codex call resolved to a real, unrelated Claude account
    rather than to nothing.
    """
    try:
        # split on BOTH separators, never `os.path.basename`: it splits on the
        # platform's own, so `C:\…\pi.cmd` was ONE long basename on Linux and
        # macOS and matched no harness — an inference call that went ungated on
        # exactly the platforms nobody develops on. `conftest._starts_claude`
        # carries this same fix and the same comment, which is the tell that it
        # belongs in the one place both could have called.
        first = str(args[0] or '').replace('\\', '/').rsplit('/', 1)[-1].lower()
    except (IndexError, TypeError, KeyError):
        return None
    for hid in ids():
        d = HARNESSES[hid]
        if any(first == n.lower() or first == os.path.splitext(n)[0].lower()
               for n in d['exe_names']):
            return d
    return None


def is_inference(args):
    """True if this argv spends model quota, for whichever harness it names.

    Kept as an argv test rather than a flag on the call: the five wrappers that
    reach `quota.preflight` each spawn BOTH inference and management commands
    (`claude -p` and `claude mcp list` go through the same
    `ui.run_with_progress`), so the caller does not always know. What was wrong
    with it was never the sniff — it was that the shape it sniffed for was one
    harness's, hardcoded: Codex's headless verb is `exec`, not a flag, so under
    a second harness this answered False for every inference call and the
    account-quota guard silently stopped applying.
    """
    d = of_argv(args)
    if d is None:
        return False
    rest = list(args)[1:]
    if any(a in d.get('inference_flags', ()) for a in rest):
        return True
    return bool(rest) and rest[0] in d.get('inference_verbs', ())
