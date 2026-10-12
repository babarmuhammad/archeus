"""What a Claude Code execution loads from its settings sources (ADR-0049; P20 D6).

The rule, decided: the account home's (`user`), the project's (`project`) and
the local (`local`) settings sources are EXCLUDED by default, a source, plugin
or MCP server the account or the project has opted in is let back in, and every
execution records an INVENTORY of what its sources would load and what became
of each item. Managed settings always apply: recorded, never excluded.

    take(home, workdir, opt_ins)  -> the inventory, the spawn's flags inside it
    flag_argv(flags, exec_dir)    -> those flags as argv (writes the MCP config)

The argv is derived from the inventory that was recorded, never computed a
second time, so what the record says and what the process was given cannot
differ. Every read here is read-only (ADR-0046): files Archeus does not own.

What the inventory may hold: hook commands, plugin and skill names, MCP server
NAMES, permission rules and CLAUDE.md hashes. Never an environment block, an
MCP server's definition (its command, arguments, URL or environment) or a
file's contents: Core redacts the record again before it stores it.

What the inventory says (version 2; P20 O5). It is taken BEFORE the spawn, so
it is a prediction (`observed: false`) by the rule PV-19 observed on Claude Code
2.1.291 (p20-design-gate §12 items 59, 69):
  1. requested: `opt_ins` (what the owners let back in) and `flags` (exactly
     what the process is given);
  2. predicted loaded: an item's status `opted_in` or `recorded_only` (its
     source loads), or `not_excludable` (managed settings: always applied);
  3. not loaded: `excluded` (its source, plugin or server is not opted in, or
     the flag that would load it is not given), `not_found` (opted in, absent);
  4. outside Archeus's source controls: `builtin`, the CLI's own plugins and
     bundled skills, recorded as one class item each because their names are
     the CLI's and cannot be read before the spawn.
The rule: an item follows its setting source. That includes a CLAUDE.md: the
user's follows `user`; CLAUDE.md and .claude/CLAUDE.md in the workdir and in
every ancestor follow `project`; CLAUDE.local.md there follows `local`. A skill
loads only while slash commands are on and its own source (or plugin) loads.
What a process actually loaded is its stream's `init` event, never this record:
a PV compares the two. Any effect PV-19 has not observed is a verification
item, never a fact here. Stdlib only.

For an ISOLATED execution (Core's decision, ADR-0053 A2) every MCP server and
everything that lives in the account home is `excluded` with a `reason`, and
the flags pass none of it: that is what this record predicts, not proof of an
OS or CLI boundary, and managed settings are still recorded as applied.
"""

import hashlib
import json
import os
import re
import sys

SOURCES = ('user', 'project', 'local')
#: Sources that PV-19 found cannot be narrowed without breaking the account's
#: login: they are loaded and only recorded (ADR-0049 §2's fallback). Empty
#: until an observed run says otherwise; never filled by inference.
RECORDED_ONLY = ()
#: Where Claude Code reads managed (enterprise) settings, per platform [DOC]
MANAGED = {'win32': os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'),
                                 'ClaudeCode', 'managed-settings.json'),
           'darwin': '/Library/Application Support/ClaudeCode/managed-settings.json'}.get(
    sys.platform, '/etc/claude-code/managed-settings.json')
#: the most items one inventory records (an unbounded settings file must not
#: make an unbounded record); a cut is said, never silent
MAX_ITEMS = 500
NAME_MAX = 200
#: the statuses that predict an item loaded (managed's `not_excludable` aside)
LOADED = ('opted_in', 'recorded_only')
#: why an item does not load for an isolated execution (ADR-0053 A2): no MCP server
#: is admitted, and its CLAUDE_CONFIG_DIR is private, so nothing that lives in the
#: account home (its settings, skills, CLAUDE.md, plugins) is there until class-2
#: materialisation exists
ISOLATED_NO_MCP = 'isolated: no MCP server is admitted (ADR-0053 A2)'
ISOLATED_NOT_MATERIALISED = ('isolated: not materialised in the private configuration '
                             '(ADR-0053 A2)')
#: the flags when no inventory exists: every source excluded
DEFAULT_FLAGS = {'setting_sources': [], 'strict_mcp_config': True, 'mcp_servers': [],
                 'disable_slash_commands': True, 'plugin_dirs': []}


def _read(path):
    """(bytes or None, error or None): None/None when the file is absent."""
    try:
        with open(path, 'rb') as f:
            return f.read(), None
    except FileNotFoundError:
        return None, None
    except OSError as e:
        return None, type(e).__name__


def _json(path):
    data, err = _read(path)
    if data is None:
        return None, err
    try:
        got = json.loads(data.decode('utf-8-sig'))
    except ValueError:
        return None, 'not JSON'
    return (got, None) if isinstance(got, dict) else (None, 'not a JSON object')


def _inside(path, root):
    try:
        a, b = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
        return os.path.commonpath([a, b]) == b
    except ValueError:
        return False


def _skills(root):
    """The skill names under *root* (`<name>/SKILL.md`)."""
    try:
        return sorted(n for n in os.listdir(root)
                      if os.path.isfile(os.path.join(root, n, 'SKILL.md')))
    except OSError:
        return []


def _plugin_skills(p, declared):
    """The skill names plugin directory *p* brings: `skills/<name>/SKILL.md`
    and every path its manifest declares (`skills`: one path or a list), each
    a skill itself (named by its SKILL.md) or a directory of them. A declared
    path outside the plugin is not read."""
    out = set(_skills(os.path.join(p, 'skills')))
    for rel in [declared] if isinstance(declared, str) else declared or ():
        d = os.path.normpath(os.path.join(p, rel)) if isinstance(rel, str) else None
        if not d or not _inside(d, p):
            continue
        md = os.path.join(d, 'SKILL.md')
        if os.path.isfile(md):
            got, _e = _read(md)
            m = re.search(rb'^name:\s*(\S.*?)\s*$', (got or b'').split(b'\n---', 1)[0], re.M)
            out.add(m.group(1).decode('utf-8', 'replace') if m else os.path.basename(d))
        else:
            out.update(_skills(d))
    return sorted(out)


def _settings_items(d):
    """(type, name) for the hooks, plugins and permission rules of one settings
    object. Its `env`, and everything else, is never read."""
    out = []
    for event, groups in sorted((d.get('hooks') or {}).items()) if isinstance(
            d.get('hooks'), dict) else ():
        for g in groups if isinstance(groups, list) else ():
            for h in (g.get('hooks') or ()) if isinstance(g, dict) else ():
                if isinstance(h, dict) and h.get('command'):
                    out.append(('hook', '%s: %s' % (event, h['command'])))
    plugins = d.get('enabledPlugins')
    for name, on in sorted(plugins.items()) if isinstance(plugins, dict) else ():
        if on:
            out.append(('plugin', name))
    perms = d.get('permissions')
    for key in ('allow', 'ask', 'deny'):
        for rule in (perms.get(key) or ()) if isinstance(perms, dict) else ():
            out.append(('permission', '%s: %s' % (key, rule)))
    return out


def _mcp_names(path):
    d, err = _json(path)
    servers = (d or {}).get('mcpServers')
    return (sorted(servers) if isinstance(servers, dict) else []), err


def plugin_dir(home, name):
    """The installed directory of plugin *name* in the account *home*, or None.
    Read from `plugins/installed_plugins.json` (format 2); a path outside the
    home's plugins directory is not a plugin of this account."""
    if not home:
        return None
    root = os.path.join(home, 'plugins')
    d, _err = _json(os.path.join(root, 'installed_plugins.json'))
    if not d or d.get('version') != 2 or not isinstance(d.get('plugins'), dict):
        return None
    for entry in d['plugins'].get(name) or ():
        p = entry.get('installPath') if isinstance(entry, dict) else None
        if isinstance(p, str) and os.path.isdir(p) and _inside(p, root):
            return os.path.realpath(p)
    return None


_MDS = (('CLAUDE.md', 'project'), (os.path.join('.claude', 'CLAUDE.md'), 'project'),
        ('CLAUDE.local.md', 'local'))


def _claude_mds(workdir):
    """(source, label, path) of every CLAUDE.md Claude Code would discover from
    *workdir*: its own and every ancestor's, each under the source it follows
    (PV-19: an ancestor's CLAUDE.md and .claude/CLAUDE.md follow `project`, its
    CLAUDE.local.md `local`). An ancestor's label is its full path."""
    out = []
    if not workdir:
        return out
    for rel, src in _MDS:
        out.append((src, rel.replace(os.sep, '/'), os.path.join(workdir, rel)))
    cur = os.path.dirname(os.path.abspath(workdir))
    while cur and os.path.dirname(cur) != cur:
        for rel, src in _MDS:
            out.append((src, os.path.join(cur, rel), os.path.join(cur, rel)))
        cur = os.path.dirname(cur)
    return out


def _isolated_why(source, type_):
    """Why an item cannot load for an isolated execution, or None (ADR-0053 A2)."""
    if type_ == 'mcp_server':
        return ISOLATED_NO_MCP
    if source in ('user', 'plugin') or source.startswith('plugin:') or (
            type_ == 'plugin' and source in ('project', 'local')):
        return ISOLATED_NOT_MATERIALISED
    return None


def take(home, workdir, opt_ins, *, recorded_only=None, managed=None, isolated=False):
    """The inventory of one execution: *home* is the account's config dir
    (None: none), *workdir* where it runs, *opt_ins* the (owner, kind, name)
    that apply to it — exactly its account's and its project's. *isolated* is
    Core's isolation decision for it, never the execution's."""
    recorded_only = tuple(RECORDED_ONLY if recorded_only is None else recorded_only)
    managed = MANAGED if managed is None else managed
    opted_sources = {n for _o, k, n in opt_ins if k == 'source'}
    opted_plugins = sorted({n for _o, k, n in opt_ins if k == 'plugin'})
    opted_mcp = sorted({(o, n) for o, k, n in opt_ins if k == 'mcp'})
    if isolated:
        # an isolated CLI reads its private config dir, not the home: the home's
        # own source cannot load there, opted in or not
        opted_sources.discard('user')
        recorded_only = tuple(s for s in recorded_only if s != 'user')

    def status(src):
        if src in recorded_only:
            return 'recorded_only'
        return 'opted_in' if src in opted_sources else 'excluded'

    roots = {'user': home, 'project': workdir, 'local': workdir}
    files = {'user': ('settings.json',),
             'project': (os.path.join('.claude', 'settings.json'),),
             'local': (os.path.join('.claude', 'settings.local.json'),)}
    items = []

    def add(source, type_, name, st, **extra):
        why = isolated and _isolated_why(source, type_)
        if why:
            st, extra = ('excluded' if st in LOADED else st), dict(extra, reason=why)
        items.append(dict({'source': source, 'type': type_, 'name': str(name)[:NAME_MAX],
                           'status': st}, **extra))

    def plugin(src, name, st, **extra):
        """Plugin *name* and what it brings, at *st*: its skills and its hooks
        (hooks/hooks.json or its manifest's own), and its MCP servers, which
        --strict-mcp-config keeps out whatever *st* is (PV-19). `loads_as` is
        the name the CLI reports it under (its manifest's). True when it
        brings a skill."""
        p = plugin_dir(home, name)
        man = (_json(os.path.join(p, '.claude-plugin', 'plugin.json'))[0] or {}) if p else {}
        add(src, 'plugin', name, st if p or src != 'plugin' else 'not_found', **dict(
            extra, **({'loads_as': str(man['name'])[:NAME_MAX]} if isinstance(
                man.get('name'), str) else {})))
        if not p:
            return False
        tag = 'plugin:' + name
        skills = _plugin_skills(p, man.get('skills'))
        for s in skills:
            add(tag, 'skill', s, st)
        hooks = [_json(os.path.join(p, 'hooks', 'hooks.json'))[0] or {}]
        if isinstance(man.get('hooks'), dict):
            hooks.append({'hooks': man['hooks']})
        for hd in hooks:
            for type_, hname in _settings_items(hd):
                if type_ == 'hook':
                    add(tag, 'hook', hname, st)
        mcp = _mcp_names(os.path.join(p, '.mcp.json'))[0]
        if isinstance(man.get('mcpServers'), dict):
            mcp += sorted(man['mcpServers'])
        for m in mcp:
            add(tag, 'mcp_server', m, 'excluded')
        return bool(skills)

    # the three sources' settings files: hooks, enabled plugins, permissions
    for src in SOURCES:
        for rel in files[src] if roots[src] else ():
            d, err = _json(os.path.join(roots[src], rel))
            if err:
                add(src, 'unreadable', rel.replace(os.sep, '/'), status(src), error=err)
            for type_, name in _settings_items(d or {}):
                if type_ == 'plugin' and name in opted_plugins:
                    add(src, type_, name, 'opted_in', via='plugin_dir')
                elif type_ == 'plugin':
                    plugin(src, name, status(src))
                else:
                    add(src, type_, name, status(src))
    # managed settings: always applied, so recorded and never excluded
    d, err = _json(managed)
    if d is not None or err:
        add('managed', 'managed_settings', os.path.basename(managed), 'not_excludable',
            **({'error': err} if err else {}))
        for type_, name in _settings_items(d or {}):
            add('managed', type_, name, 'not_excludable')
    # plugins opted in by name: loaded for this session from their directory
    dirs = []
    dir_skills = False
    for name in opted_plugins:
        brings_skill = plugin('plugin', name, 'opted_in', via='plugin_dir')
        if not isolated:
            dirs.append({'name': name, 'path': plugin_dir(home, name)})
            dir_skills = brings_skill or dir_skills
    # MCP servers: --strict-mcp-config loads only the ones passed [DOC]
    servers, seen = [], set()
    for owner, src, path in (('account', 'user', os.path.join(home, '.claude.json') if home
                              else None),
                             ('project', 'project', os.path.join(workdir, '.mcp.json')
                              if workdir else None)):
        names, err = _mcp_names(path) if path else ([], None)
        if err:
            add(src, 'unreadable', os.path.basename(path), 'excluded', error=err)
        for n in names:
            seen.add((owner, n))
            on = (owner, n) in opted_mcp
            add(src, 'mcp_server', n, 'opted_in' if on else 'excluded')
            if on and not isolated:
                servers.append({'owner': owner, 'name': n})
    for owner, n in opted_mcp:
        if (owner, n) not in seen:
            add('user' if owner == 'account' else 'project', 'mcp_server', n, 'not_found')
    # skills: --disable-slash-commands disables every one [DOC], so it stays
    # unless a skill arrives with something opted in; without it a skill still
    # loads only if its own source does (PV-19)
    found = [(src, s) for src, root in (('user', os.path.join(home, 'skills') if home else None),
                                        ('project', os.path.join(workdir, '.claude', 'skills')
                                         if workdir else None)) if root for s in _skills(root)]
    skill_in = any(status(src) != 'excluded' for src, _s in found) or dir_skills
    for src, s in found:
        add(src, 'skill', s, status(src))
    # the account's synced skills (skills/synced/<id>/<name>) come with `user`
    synced = os.path.join(home, 'skills', 'synced') if home else ''
    for d in sorted(os.listdir(synced)) if synced and os.path.isdir(synced) else ():
        for s in _skills(os.path.join(synced, d)):
            add('user', 'skill', s, status('user'), via='synced')
    # CLAUDE.md follows its setting source (PV-19): none loads with none opted in
    mds = [('user', 'CLAUDE.md', os.path.join(home, 'CLAUDE.md'))] if home else []
    for src, label, path in mds + _claude_mds(workdir):
        data, err = _read(path)
        if data is None and not err:
            continue
        add(src, 'claude_md', label, status(src), **({'sha256': hashlib.sha256(data).hexdigest()}
                                                     if data is not None else {'error': err}))
    # the CLI's own, which no settings source or flag of Archeus's reaches
    # except --disable-slash-commands for the bundled skills (PV-19)
    add('cli', 'plugin', 'built-in plugins', 'builtin')
    add('cli', 'skill', 'bundled skills', 'builtin' if skill_in else 'excluded')
    flags = {'setting_sources': [s for s in SOURCES if s in opted_sources or s in recorded_only],
             'strict_mcp_config': True,
             'mcp_servers': servers,
             'disable_slash_commands': not skill_in,
             'plugin_dirs': dirs}
    return {'inventory_version': 2, 'observed': False,
            'opt_ins': [{'owner': o, 'kind': k, 'name': n} for o, k, n in opt_ins],
            'recorded_only': list(recorded_only),
            'flags': flags, 'items': items[:MAX_ITEMS], 'truncated': len(items) > MAX_ITEMS}


def mcp_config(home, workdir, servers):
    """The definitions of the opted-in *servers*, read from where they live
    (account: the home's `.claude.json`; project: the workdir's `.mcp.json`) —
    for the `--mcp-config` file only, never for the record."""
    out = {}
    for s in servers:
        path = (os.path.join(home, '.claude.json') if s['owner'] == 'account' and home else
                os.path.join(workdir, '.mcp.json') if s['owner'] == 'project' and workdir
                else None)
        d, _err = _json(path) if path else (None, None)
        got = ((d or {}).get('mcpServers') or {}).get(s['name'])
        if isinstance(got, dict) and s['name'] not in out:
            out[s['name']] = got
    return {'mcpServers': out}


def flag_argv(flags, *, home, workdir, exec_dir):
    """The spawn's ADR-0049 flags. `--setting-sources` is ALWAYS passed — left
    out it would mean every source — and empty when nothing is opted in."""
    a = ['--setting-sources', ','.join(flags['setting_sources']), '--strict-mcp-config']
    if flags['mcp_servers']:
        path = os.path.join(exec_dir, 'mcp.json')
        os.makedirs(exec_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(mcp_config(home, workdir, flags['mcp_servers']), f)
        a += ['--mcp-config', path]
    if flags['disable_slash_commands']:
        a.append('--disable-slash-commands')
    for d in flags['plugin_dirs']:
        if d.get('path'):
            a += ['--plugin-dir', d['path']]
    return a
