"""Claude Code plugins and marketplaces.

A plugin is now the canonical unit of distribution: a versioned bundle shipping
any of skills, subagents, slash commands, hooks, output styles and MCP servers
together. archeus manages every one of those individually and, until this
module, could not see the bundle that contained them.

THE PART THAT ONLY ARCHEUS CAN DO
-----------------------------------
Listing plugins is table stakes — `/plugin` already does it. What no other tool
is positioned to show is PROVENANCE: archeus's agent, skill and hook managers
present a flat list, so there is no way to tell what you installed deliberately
from what a bundle brought along. After a few marketplace installs that list is
a mystery, and the only safe-looking action — delete it — may break a plugin.

`provenance_index()` is therefore the point of this file. The rest is plumbing.

ON-DISK FORMAT
--------------
Read from the live files, not from the documentation, which describes a
`marketplaces.json` that this version does not write:

  ~/.claude/plugins/known_marketplaces.json   name -> {source, installLocation}
  ~/.claude/plugins/installed_plugins.json    {"version":2, "plugins": {
                                                 "<plugin>@<marketplace>": [
                                                   {scope, installPath, version,
                                                    installedAt, gitCommitSha}]}}
  ~/.claude/plugins/marketplaces/<name>/       the cloned marketplace
  ~/.claude/plugins/cache/<mkt>/<plugin>/<v>/  the installed plugin itself

Both files are read defensively and treated as advisory: they belong to Claude
Code, the shape has already changed once, and archeus showing a stale row is
strictly better than archeus crashing on an unfamiliar key.

TWO CLIs, ONE TABLE
-------------------
Codex has the same surface under different words — `plugin add` for install,
`plugin remove` for uninstall, `plugin marketplace upgrade` for update — so
three of the six operations differ and three do not, which no single rule
predicts. `PLUGIN_VERBS` is that table and `_cli` is the only place a binary and
a verb are chosen; a harness rides on `cfgdir`, exactly as everywhere else.
"""

import json
import os
import re

from . import config as _c

#: what a plugin can ship, and the directory each lives in. Order is the order
#: the UI lists them in.
KINDS = (('skills', 'skill'), ('agents', 'agent'),
         ('commands', 'command'), ('hooks', 'hook'))

#: what each CLI calls the six plugin operations. VERBS only — the arguments are
#: the same shape everywhere (a source, a `plugin@marketplace` id, a marketplace
#: name), which is why this is a table and not six functions per harness.
#:
#: An ABSENT key is a command that CLI does not have. Codex has no per-plugin
#: upgrade — its reference documents `plugin add`, `plugin list` and
#: `plugin remove` and nothing else — so archeus draws no Update button there
#: rather than shelling out to a verb that does not exist and reporting the
#: CLI's usage error as a failed update. That is also why this is a table rather
#: than a string substitution: the two CLIs disagree on three of the six words
#: (`update`/`upgrade`, `install`/`add`, `uninstall`/`remove`) and agree on the
#: rest, which no single rule predicts.
PLUGIN_VERBS = {
    'claude': {'mkt_add': ('plugin', 'marketplace', 'add'),
               'mkt_update': ('plugin', 'marketplace', 'update'),
               'mkt_remove': ('plugin', 'marketplace', 'remove'),
               'install': ('plugin', 'install'),
               'remove': ('plugin', 'uninstall'),
               # -y rides in the verb because it is not an argument: it is part
               # of what "update" means off a TTY, where the CLI cannot ask.
               'update': ('plugin', 'update', '-y')},
    'codex':  {'mkt_add': ('plugin', 'marketplace', 'add'),
               'mkt_update': ('plugin', 'marketplace', 'upgrade'),
               'mkt_remove': ('plugin', 'marketplace', 'remove'),
               'install': ('plugin', 'add'),
               'remove': ('plugin', 'remove')},
}

#: A short starting set, per harness. Editorial and deliberately SHORT: the
#: official marketplace carries nearly three hundred plugins, and a page that
#: lists them all is a catalogue rather than a recommendation.
#:
#: Each row says why ARCHEUS recommends it. The plugin's own description is read
#: live from the marketplace manifest when the marketplace is registered, so
#: this table never restates one and cannot drift from it.
#:
#: `claude-md-management` is deliberately NOT here although it is first-party
#: and good: archeus's own CLAUDE.md tab writes that file, and two tools
#: rewriting one file is the conflict, not a gap.
RECOMMENDED = {
    'claude': (
        ('code-review', 'claude-plugins-official',
         'Reviews a diff or a PR with several specialised agents.'),
        ('code-simplifier', 'claude-plugins-official',
         'Cuts a change back to what it needs to be.'),
        ('commit-commands', 'claude-plugins-official',
         'commit, push and open a PR as one step.'),
        ('security-guidance', 'claude-plugins-official',
         'Warns on a risky edit as it is made.'),
        ('frontend-design', 'claude-plugins-official',
         'Front-end work that comes out looking designed.'),
        ('claude-code-setup', 'claude-plugins-official',
         'Reads a codebase and proposes the hooks and commands it wants.'),
        ('codex', 'openai-codex',
         'Delegate a review or a task to Codex from inside Claude Code.'),
    ),
    #: EMPTY on purpose, and that is a fact about Codex rather than a gap:
    #: `codex plugin list` reports every plugin its marketplaces OFFER, not only
    #: the installed ones, so the list above already IS the catalogue. The card
    #: says so rather than rendering blank.
    'codex': (),
}

#: the source each recommended marketplace is added FROM, so a row whose
#: marketplace is not registered yet can offer "add it, then install" in one
#: press instead of failing at install with "no such plugin".
RECOMMENDED_SOURCES = {
    'claude-plugins-official': 'anthropics/claude-plugins-official',
    'openai-codex': 'openai/codex-plugin-cc',
}

#: filenames that live alongside a plugin's content without being content
_NOT_CONTENT = {'readme', 'license', 'licence', 'package', 'package-lock',
                'changelog', 'contributing', '.gitignore', 'tsconfig'}


def plugins_dir(cfg_dir=None):
    return os.path.join(cfg_dir or _c.config_dir, 'plugins')


def _read_json(path, default):
    try:
        with open(path, encoding='utf-8-sig') as f:
            d = json.load(f)
        return d if isinstance(d, (dict, list)) else default
    except Exception:
        return default


def known_marketplaces(cfg_dir=None):
    """[{name, repo, source, path, updated}] — registered marketplaces."""
    raw = _read_json(os.path.join(plugins_dir(cfg_dir), 'known_marketplaces.json'), {})
    out = []
    for name, v in (raw.items() if isinstance(raw, dict) else []):
        src = (v or {}).get('source') or {}
        out.append({
            'name': name,
            'source': src.get('source', ''),
            'repo': src.get('repo') or src.get('url') or '',
            'path': (v or {}).get('installLocation', ''),
            'updated': (v or {}).get('lastUpdated', ''),
        })
    out.sort(key=lambda r: r['name'].lower())
    return out


def installed(cfg_dir=None):
    """[{key, name, marketplace, scope, version, path, installed_at, sha}].

    The key is `<plugin>@<marketplace>` and a plugin may legitimately appear
    more than once (different scopes), so each install is its own row rather
    than being collapsed — collapsing would hide a user-scope plugin shadowing
    a project-scope one, which is exactly the kind of thing you open this list
    to find out.
    """
    raw = _read_json(os.path.join(plugins_dir(cfg_dir), 'installed_plugins.json'), {})
    out = []
    for key, entries in ((raw.get('plugins') or {}).items()
                         if isinstance(raw, dict) else []):
        name, _, mkt = str(key).partition('@')
        for e in (entries if isinstance(entries, list) else [entries]):
            e = e or {}
            out.append({
                'key': key, 'name': name, 'marketplace': mkt,
                'scope': e.get('scope', ''),
                'version': str(e.get('version', ''))[:12],
                'path': e.get('installPath', ''),
                'installed_at': e.get('installedAt', ''),
                'sha': str(e.get('gitCommitSha', ''))[:12],
            })
    out.sort(key=lambda r: (r['marketplace'].lower(), r['name'].lower()))
    return out


def contents(install_path):
    """{kind: [names]} — what a plugin actually places.

    Directory listing, not a manifest read: the manifest declares intent and the
    directory is the truth, and provenance is only useful if it matches what is
    really on disk.
    """
    out = {}
    for folder, kind in KINDS:
        d = os.path.join(install_path or '', folder)
        if not os.path.isdir(d):
            continue
        names = []
        try:
            for fn in sorted(os.listdir(d)):
                full = os.path.join(d, fn)
                stem = os.path.splitext(fn)[0]
                # packaging files sit in these folders too. Listing README and
                # package as if they were hooks makes the provenance index lie,
                # and a wrong provenance label is worse than none — it is the
                # one thing this list exists to be trusted about.
                if stem.lower() in _NOT_CONTENT:
                    continue
                if os.path.isdir(full):
                    names.append(fn)                       # skills/<name>/
                elif fn.lower().endswith(('.md', '.json')):
                    names.append(stem)                     # agents/<name>.md
        except Exception:
            continue
        if names:
            out[kind] = names
    if os.path.isfile(os.path.join(install_path or '', '.mcp.json')):
        out['mcp'] = ['(mcp servers)']
    return out


def provenance_index(cfg_dir=None):
    """{kind: {name: plugin_key}} — "where did this come from?".

    THE reason this module exists. The agent, skill and hook managers show flat
    lists; without this a user cannot tell their own work from a bundle's, and
    the obvious action on something unrecognised — delete it — may quietly break
    a plugin.

    Matching is by name because that is what the managers display and what the
    filesystem gives them. Two plugins shipping the same skill name is a real
    collision; last-writer-wins here mirrors what Claude Code itself does, and
    the row is still labelled, which is the point.
    """
    idx = {}
    for p in installed(cfg_dir):
        for kind, names in contents(p['path']).items():
            bucket = idx.setdefault(kind, {})
            for n in names:
                bucket[n] = p['key']
    return idx


def summary(cfg_dir=None):
    """One payload for the GUI: marketplaces, installs, and what each ships.

    Per HOME, and the home decides which CLI is asked. Codex has its own
    marketplaces — `codex plugin list` reads every one of them and their
    manifests sit at `<source>/.agents/plugins/marketplace.json`, the same
    `.agents` convention archeus already writes project skills into — so the
    page that was declared meaningless there answers with real rows.

    `can` is the one field that differs, and it is the verb table rather than a
    judgement: it lists the operations THIS CLI has a command for, so the page
    hides exactly the buttons that would have nothing to run. Codex has no
    per-plugin upgrade and so gets no Update button; it has every other verb,
    which is why the page is no longer read-only there.
    """
    from . import harnesses as _h
    d = _h.of(cfg_dir)
    can = sorted(PLUGIN_VERBS.get(d['id']) or {})
    if d['id'] == 'codex':
        from . import codex
        rows, seen = [], {}
        for p in codex.plugins(_c.resolve_config_dir(cfg_dir)):
            name = p['name'].split('@', 1)[0]
            seen.setdefault(p['marketplace'],
                            {'name': p['marketplace'], 'source': p['manifest'],
                             'plugins': 0})
            seen[p['marketplace']]['plugins'] += 1
            # `name@marketplace` is the stable id both `plugin add` and
            # `plugin remove` document, and the PLUGIN column is a bare name —
            # so the key is BUILT rather than taken, or every mutation would
            # name a plugin without saying which marketplace it came from.
            rows.append({'key': '%s@%s' % (name, p['marketplace']), 'name': name,
                         'marketplace': p['marketplace'],
                         'version': p['version'], 'path': p['path'],
                         'enabled': 'enabled' in p['status'],
                         'installed': 'not installed' not in p['status'],
                         'provides': {}, 'missing': False})
        return {'marketplaces': list(seen.values()), 'plugins': rows,
                'dir': _c.resolve_config_dir(cfg_dir),
                'readonly': not can, 'can': can}
    mkts = known_marketplaces(cfg_dir)
    inst = installed(cfg_dir)
    for p in inst:
        p['provides'] = contents(p['path'])
        p['missing'] = not (p['path'] and os.path.isdir(p['path']))
    return {'marketplaces': mkts, 'plugins': inst,
            'dir': plugins_dir(cfg_dir), 'readonly': not can, 'can': can}


def recommendations(cfg_dir=None):
    """[{name, marketplace, why, source, desc, installed, registered}] — the
    curated starting set for whichever CLI owns this home.

    A fresh account has one registered marketplace with hundreds of plugins in
    it and nothing saying which few are worth having. This is that answer, and
    it is deliberately a handful.

    `desc` is read from the marketplace's OWN manifest when the marketplace is
    on disk, so this never carries a second copy of a description to keep in
    step; `why` is archeus's reason for the row and is the only editorial text
    here. A row whose marketplace is not registered carries its `source`, so the
    UI can offer to add it rather than failing at install with "no such plugin".
    """
    from . import harnesses as _h
    from . import versions
    hid = _h.of(cfg_dir)['id']
    have = {p['key'] for p in installed(cfg_dir)}
    known = {m['name'] for m in known_marketplaces(cfg_dir)}
    entries = versions._marketplace_entries(cfg_dir)
    out = []
    for name, mkt, why in RECOMMENDED.get(hid) or ():
        key = '%s@%s' % (name, mkt)
        out.append({'name': name, 'marketplace': mkt, 'why': why,
                    'source': RECOMMENDED_SOURCES.get(mkt, ''),
                    'desc': str((entries.get(key) or {}).get('description', ''))[:200],
                    'installed': key in have, 'registered': mkt in known})
    return out


# ── mutations ────────────────────────────────────────────────
# Delegated to the CLI rather than reimplemented. These files are the CLI's: it
# resolves marketplace sources, verifies manifests, handles scopes and updates
# its own caches. Writing them directly would work until the format moved —
# which it already has once — and would then corrupt the state of the tool
# archeus exists to support.

#: a plugin id (`name` or `name@marketplace`) and a marketplace name, as the
#: argument of a command. NOT a politeness check: these values come from a text
#: box now, and a value starting `-` lands in an option position whether or not
#: a shell is involved — the same reason `add_marketplace` validates its source.
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*(@[A-Za-z0-9][A-Za-z0-9._-]*)?$')


def _run(argv, timeout=120, cfgdir=None):
    """Run WHICHEVER CLI owns this home, with a ready argv.

    The binary is resolved per harness (`harnesses.exe`) rather than assumed to
    be Claude Code's: a harness rides on `cfgdir` everywhere else in archeus and
    this is no exception.

    The env is the other half and is the whole reason this is one function.
    Without it the CLI lands on whatever home archeus inherited — normally
    unset, i.e. the default account — while every reader in this module resolves
    `cfgdir`. Read and write then named different accounts: with archeus
    switched to another account the Plugins page listed that account's plugins
    and Install wrote into default.
    """
    from . import harnesses as _h
    from . import proc
    d = _h.of(cfgdir)
    exe = _h.exe(d['id'])
    if not exe:
        return False, '%s not found' % d['exe_names'][0]
    r = proc.run([exe] + list(argv), env=_c.account_env(cfgdir), timeout=timeout)
    if r is None:
        return False, 'could not run %s' % d['id']
    out = ((r.stdout or '') + (r.stderr or '')).strip()
    return r.returncode == 0, out[:400]


def _cli(op, args, cfgdir=None, timeout=120):
    """One plugin operation, in the vocabulary of the CLI that owns this home.

    The verb comes from `PLUGIN_VERBS` and an op that is not in it is REFUSED
    here rather than sent: a CLI asked for a subcommand it does not have answers
    with its usage text and a non-zero exit, which the UI would report as a
    failed update instead of as a command that never existed.
    """
    from . import harnesses as _h
    d = _h.of(cfgdir)
    verb = (PLUGIN_VERBS.get(d['id']) or {}).get(op)
    if not verb:
        return False, '%s has no %s command' % (d['label'], op.replace('_', ' '))
    return _run(list(verb) + list(args), timeout=timeout, cfgdir=cfgdir)


def add_marketplace(source, cfgdir=None):
    """`<cli> plugin marketplace add <repo|url|path>`.

    The three shapes the CLI documents are the three shapes accepted, because
    this value is fetched by git underneath: a bare `ext::sh -c …` is a real git
    transport that executes on clone, and a value starting `-` lands in an
    option position. Neither needs a shell to be a problem.
    """
    from . import proc
    source = (source or '').strip()
    if not source:
        return False, 'No source given'
    if not (re.match(r'^[\w.-]+/[\w.-]+$', source)         # owner/repo
            or proc.remote_url_ok(source)                  # a git remote URL
            or os.path.isdir(source)):                     # a local marketplace
        return False, 'not an owner/repo, a git URL, or a directory that exists'
    return _cli('mkt_add', [source], cfgdir=cfgdir)


def remove_marketplace(name, cfgdir=None):
    name = (name or '').strip()
    if not _ID.match(name):
        return False, 'not a marketplace name'
    return _cli('mkt_remove', [name], cfgdir=cfgdir)


def update_marketplaces(name='', cfgdir=None):
    """Fetch every registered marketplace from its source again — what makes a
    plugin's `available` version move.

    No name means all of them, which both CLIs document. It lives here rather
    than in `versions.py` because it is a plugin MUTATION: the version module
    reads and compares, this writes a clone.
    """
    name = (name or '').strip()
    if name and not _ID.match(name):
        return False, 'not a marketplace name'
    return _cli('mkt_update', [name] if name else [], cfgdir=cfgdir, timeout=600)


def install_plugin(name, marketplace='', cfgdir=None):
    """Install one plugin by its `name@marketplace` id.

    A plugin ships agents and hooks straight into the auto-discovery surfaces,
    so it is the same exposure as `install_from_git` with more moving parts —
    which is what `review_plugin` is for on the paths that can draw a screen.
    """
    spec = f'{name}@{marketplace}' if marketplace else (name or '')
    spec = spec.strip()
    if not _ID.match(spec):
        return False, 'not a plugin name — use name or name@marketplace'
    return _cli('install', [spec], cfgdir=cfgdir)


def remove_plugin(key, cfgdir=None):
    key = (key or '').strip()
    if not _ID.match(key):
        return False, 'not a plugin name — use name or name@marketplace'
    return _cli('remove', [key], cfgdir=cfgdir)


def update_plugin(key, cfgdir=None):
    """Move one plugin to whatever its marketplace now offers.

    There is no version target: the marketplace entry decides what latest is.
    Claude Code alone has this — see PLUGIN_VERBS — so on any other CLI this
    answers with the verb table's refusal rather than a subprocess.
    """
    key = (key or '').strip()
    if not _ID.match(key):
        return False, 'not a plugin name — use name or name@marketplace'
    return _cli('update', [key], cfgdir=cfgdir, timeout=600)


def review_plugin(name, marketplace, cfg_dir=None):
    """Scan a marketplace's copy of a plugin before installing it.

    Returns True to proceed. Reuses skillscan, so the report, the wording and
    the approval gate are identical to the git-bundle path — one review screen,
    not two that drift.
    """
    from . import skillscan
    mkt = next((m for m in known_marketplaces(cfg_dir)
                if m['name'] == marketplace), None)
    root = ''
    for cand in ([os.path.join(mkt['path'], 'plugins', name)] if mkt and mkt['path'] else []):
        if os.path.isdir(cand):
            root = cand
            break
    if not root:
        # nothing local to inspect — say so rather than implying it was checked
        from . import diffview
        return bool(diffview.confirm(
            '', f'{name}@{marketplace}\n\nThis plugin is not cloned locally yet, so '
                'nothing could be inspected before installing.\n\nInstall only from a '
                'source you would give your shell to.',
            'Install without review?'))
    plan = []
    for base, _dirs, files in os.walk(root):
        for fn in files:
            full = os.path.join(base, fn)
            rel = os.path.relpath(full, root).replace('\\', '/')
            kind = 'agent' if rel.startswith('agents/') else 'skill'
            plan.append((rel, f'(plugin {name}@{marketplace}) {rel}', kind))
    return skillscan.review_gate(root, plan, source=f'{name}@{marketplace}')
