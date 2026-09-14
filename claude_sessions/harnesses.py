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
    'usage':            'account usage and rate limits',
    'versions':         'install and update the CLI',
    'accounts':         'more than one login',
    'effort':           'a reasoning-effort setting',
    'permission_modes': 'permission modes',
    'named_session':    'naming a session at launch',
    'worktree':         'launching into a git worktree',
    'budget_cap':       'a spend cap on one call',
    'headless_json':    'one-shot calls that return JSON',
}

#: the harness every existing installation is, and the default for anything
#: archeus cannot place.
DEFAULT = 'claude'


def _claude_exe_names():
    return ('claude.exe', 'claude') if os.name == 'nt' else ('claude',)


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
        'caps': {},                       # it can do everything; it is the model
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


def _homes():
    """[(harness id, home dir)] for every home archeus knows.

    Claude's come from the accounts list, because an account IS a home there.
    Other harnesses have exactly one each until something says otherwise.
    """
    out = [('claude', d) for _n, d in _c.all_config_dirs()]
    for hid in ids():
        if hid == 'claude':
            continue
        out.append((hid, home_dir(hid)))
    return out


def instances():
    """[(display name, home dir, harness id)] — every home, every harness.

    The harness-aware sibling of `config.all_config_dirs()`, which deliberately
    stays Claude-only: every one of ITS callers means "accounts", and fanning a
    Claude-shaped write across a Codex home would write a settings.json that
    Codex never reads.
    """
    out = [(n, d, 'claude') for n, d in _c.all_config_dirs()]
    for hid in ids():
        if hid == 'claude':
            continue
        if exe(hid):
            out.append((HARNESSES[hid]['label'], home_dir(hid), hid))
    return out


def exe(hid=None):
    """The binary for one harness, or None. Setting override > default install
    path > PATH, the shape `config.get_claude_exe` has always had — and
    RESOLVED EVERY TIME, never cached: Codex installs under a hashed directory
    that changes on every update, so a stored absolute path goes stale in
    silence."""
    import shutil
    d = descriptor(hid)
    override = (_c.load_settings().get(d.get('exe_setting') or '') or '')
    if override and os.path.exists(override):
        return override
    for name in d['exe_names']:
        default = os.path.join(_c._USERPROFILE, '.local', 'bin', name)
        if os.path.exists(default):
            return default
    for name in d['exe_names']:
        found = shutil.which(name)
        if found:
            return found
    return None


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
    try:
        first = os.path.basename(str(args[0] or '')).lower()
    except (IndexError, TypeError, KeyError):
        return False
    rest = list(args)[1:]
    for hid in ids():
        d = HARNESSES[hid]
        if not any(first == n.lower() or first == os.path.splitext(n)[0].lower()
                   for n in d['exe_names']):
            continue
        if any(a in d.get('inference_flags', ()) for a in rest):
            return True
        return bool(rest) and rest[0] in d.get('inference_verbs', ())
    return False
