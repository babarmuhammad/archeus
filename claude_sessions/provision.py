"""Level every account up to what the user has actually provisioned.

WHY THIS EXISTS
---------------
archeus treated "the account" as a process-global, so hooks, plugins,
marketplaces, user agents and the global CLAUDE.md all landed in whichever
config dir was active when the module was imported — in practice the default
one. Measured across five configured accounts:

    account     plugins  marketplaces  hooks  statusline  agents  CLAUDE.md
    default        3          3          18      yes         1       yes
    personal       0          1           0      yes         0        -
    Lorenzo        0          1           0      yes         0        -
    Gioele         0          1           0      yes         0        -
    Federico       0          1           0      yes         0        -

The statusline is the only row that reached everyone, and that is not luck: it
is the one feature with a real fan-out. This module generalises
`statusline.by_account()` to the rest of them.

DESIGN
------
`diff()` reports, never writes. `apply()` only ADDS — it levels an account up
to the union, and never removes anything an account has that others do not,
because there is no way to tell a deliberate per-account choice from a gap.
Re-running with nothing to do reports nothing to do.

No TUI import: the GUI must not drag `ui` in to install a plugin.
"""

import os

from . import config as _c

#: the surfaces a user provisions, in the order the report lists them
KINDS = ('marketplaces', 'plugins', 'hooks', 'statusline', 'agents', 'skills',
         'claude_md')


def _hooks_of(cfgdir):
    """Comparable keys for every enabled hook in one account.

    Keyed by (event, commands), so two entries running the same command on the
    same event collapse: you cannot install the same hook twice, and the diff is
    about what is MISSING. `_n_hooks` is what the report counts, so the number
    here agrees with the one the Hooks page shows.
    """
    from . import hooks as h
    out = {}
    for event, block in (h._load(cfgdir).get('hooks') or {}).items():
        for entry in (block if isinstance(block, list) else []):
            out[(event, tuple(h._cmd_keys(entry)))] = entry
    return out


def _n_hooks(cfgdir):
    from . import hooks as h
    return sum(len(b or []) for b in (h._load(cfgdir).get('hooks') or {}).values())


def _plugins_of(cfgdir):
    from . import plugins
    return {p['key'] for p in plugins.installed(cfgdir)}


def _marketplaces_of(cfgdir):
    from . import plugins
    return {m['name']: m for m in plugins.known_marketplaces(cfgdir)}


def _agents_of(cfgdir):
    from . import agents
    d = agents.user_agents_dir(cfgdir)
    if not os.path.isdir(d):
        return {}
    return {fn: os.path.join(d, fn) for fn in sorted(os.listdir(d))
            if fn.endswith('.md')}


def _skills_of(cfgdir):
    """Personal skills of one account: {name: dir}.

    The same shape as `_agents_of` and for the same reason — a skill you wrote
    is a property of you, not of whichever account happened to be active when
    you saved it. `<cfgdir>/skills` is what Claude Code actually loads.
    """
    from . import skills
    d = skills.personal_dir(cfgdir)
    return {os.path.basename(sd): sd for _n, _desc, sd in skills.list_skills(d)}


def _state(name, cfgdir):
    from . import statusline
    md = _c.global_claude_md_for(cfgdir)
    return {
        'name': name, 'dir': cfgdir,
        'marketplaces': _marketplaces_of(cfgdir),
        'plugins': _plugins_of(cfgdir),
        'hooks': _hooks_of(cfgdir),
        'n_hooks': _n_hooks(cfgdir),
        'agents': _agents_of(cfgdir),
        'skills': _skills_of(cfgdir),
        'statusline': statusline.is_installed(cfgdir),
        'claude_md': os.path.isfile(md) and bool(
            open(md, encoding='utf-8', errors='ignore').read().strip()),
        'claude_md_path': md,
    }


def diff():
    """{'accounts': [...], 'union': {...}, 'clean': bool} — read-only.

    Every account row carries `missing`, which is what the confirmation screen
    shows before anything is copied.
    """
    from . import hooks
    accts = [_state(n, d) for n, d in hooks.account_dirs()]
    union = {
        'marketplaces': {},
        'plugins': set(),
        'hooks': {},
        'agents': {},
        'skills': {},
        'statusline': any(a['statusline'] for a in accts),
        'claude_md': next((a['claude_md_path'] for a in accts if a['claude_md']), ''),
    }
    for a in accts:
        union['marketplaces'].update(a['marketplaces'])
        union['plugins'] |= a['plugins']
        union['hooks'].update(a['hooks'])
        union['agents'].update(a['agents'])
        union['skills'].update(a['skills'])

    rows = []
    for a in accts:
        missing = {
            'marketplaces': sorted(set(union['marketplaces']) - set(a['marketplaces'])),
            'plugins': sorted(union['plugins'] - a['plugins']),
            'hooks': sorted('%s %s' % (e, ' '.join(k)[:40])
                            for e, k in set(union['hooks']) - set(a['hooks'])),
            'agents': sorted(set(union['agents']) - set(a['agents'])),
            'skills': sorted(set(union['skills']) - set(a['skills'])),
            'statusline': union['statusline'] and not a['statusline'],
            'claude_md': bool(union['claude_md']) and not a['claude_md'],
        }
        rows.append({
            'name': a['name'], 'dir': a['dir'],
            'have': {'marketplaces': len(a['marketplaces']), 'plugins': len(a['plugins']),
                     'hooks': a['n_hooks'], 'agents': len(a['agents']),
                     'skills': len(a['skills']),
                     'statusline': a['statusline'], 'claude_md': a['claude_md']},
            'missing': missing,
            'todo': sum(len(v) if isinstance(v, list) else int(bool(v))
                        for v in missing.values()),
        })
    return {'accounts': rows, 'clean': not any(r['todo'] for r in rows),
            'plugin_sources': {p: _plugin_source(union['marketplaces'], p)
                               for p in sorted(union['plugins'])}}


def _plugin_source(marketplaces, key):
    """`<plugin>@<marketplace>` splits on the last '@'; keep the marketplace
    only when it is one the union actually knows, so an install cannot be
    pointed at a name nothing registered."""
    name, _, mkt = key.rpartition('@')
    return mkt if name and mkt in marketplaces else ''


def report(d=None):
    """The diff as lines, in the table shape the plan's Context section used."""
    d = d or diff()
    head = ('account', 'plugins', 'mkts', 'hooks', 'stline', 'agents', 'skills',
            'CLAUDE.md')
    out = ['  %-12s %8s %6s %6s %7s %7s %7s %10s' % head,
           '  ' + '-' * 70]
    for r in d['accounts']:
        h = r['have']
        out.append('  %-12s %8d %6d %6d %7s %7d %7d %10s'
                   % (r['name'][:12], h['plugins'], h['marketplaces'], h['hooks'],
                      'yes' if h['statusline'] else '-', h['agents'], h['skills'],
                      'yes' if h['claude_md'] else '-'))
    out.append('')
    if d['clean']:
        out.append('  Every account already has everything. Nothing to do.')
        return out
    for r in d['accounts']:
        if not r['todo']:
            continue
        out.append('  %s — %d to add' % (r['name'], r['todo']))
        m = r['missing']
        for kind in ('marketplaces', 'plugins', 'agents', 'skills', 'hooks'):
            if m[kind]:
                out.append('      %-13s %s' % (kind + ':', ', '.join(m[kind])[:90]))
        if m['statusline']:
            out.append('      statusline:   install')
        if m['claude_md']:
            out.append('      CLAUDE.md:    copy global instructions')
    return out


def apply(d=None, kinds=KINDS, review=None, progress=None):
    """Level every account up to the union. Returns [(account, kind, detail, ok)].

    `review(name, marketplace)` gates every plugin install — a plugin ships
    agents and hooks straight into the auto-discovery surfaces, so installing
    into four more accounts is four more exposures. None means no gate, which
    only the tests use.
    """
    import shutil
    from . import plugins, statusline, hooks as h
    d = d or diff()
    union_md = next((os.path.join(r['dir'] or _c.config_dir, 'CLAUDE.md')
                     for r in d['accounts'] if r['have']['claude_md']), '')
    # re-read the union's own objects; the diff only carried their names
    full = {n: _state(n, dd) for n, dd in h.account_dirs()}
    u_mkt, u_hooks, u_agents, u_skills = {}, {}, {}, {}
    for a in full.values():
        u_mkt.update(a['marketplaces'])
        u_hooks.update(a['hooks'])
        u_agents.update(a['agents'])
        u_skills.update(a['skills'])

    done = []

    def step(name, kind, detail, ok):
        done.append((name, kind, detail, bool(ok)))
        if progress:
            progress(name, kind, detail, bool(ok))

    for row in d['accounts']:
        name, cfgdir = row['name'], row['dir']
        m, want = row['missing'], set(kinds)

        for mkt in (m['marketplaces'] if 'marketplaces' in want else []):
            source = (u_mkt.get(mkt) or {}).get('repo') or (u_mkt.get(mkt) or {}).get('source')
            if not source:
                step(name, 'marketplaces', '%s (no source recorded)' % mkt, False)
                continue
            ok, msg = plugins.add_marketplace(source, cfgdir=cfgdir)
            step(name, 'marketplaces', mkt if ok else '%s: %s' % (mkt, msg), ok)

        for key in (m['plugins'] if 'plugins' in want else []):
            pname, _, _ = key.rpartition('@')
            mkt = d['plugin_sources'].get(key, '')
            if review and not review(pname or key, mkt):
                step(name, 'plugins', '%s (review declined)' % key, False)
                continue
            ok, msg = plugins.install_plugin(pname or key, mkt, cfgdir=cfgdir)
            step(name, 'plugins', key if ok else '%s: %s' % (key, msg), ok)

        if 'hooks' in want and m['hooks']:
            s = h._load(cfgdir)
            have = set(_hooks_of(cfgdir))
            added = 0
            for (event, keys), entry in u_hooks.items():
                if (event, keys) in have:
                    continue
                s.setdefault('hooks', {}).setdefault(event, []).append(entry)
                added += 1
            ok = h._save(s, cfgdir) if added else True
            step(name, 'hooks', '%d hook(s)' % added, ok)

        if 'statusline' in want and m['statusline']:
            ok, msg = statusline.install(cfgdir)
            step(name, 'statusline', msg, ok)

        for fn in (m['agents'] if 'agents' in want else []):
            dest_dir = os.path.join(cfgdir or _c.config_dir, 'agents')
            os.makedirs(dest_dir, exist_ok=True)
            try:
                shutil.copyfile(u_agents[fn], os.path.join(dest_dir, fn))
                step(name, 'agents', fn, True)
            except OSError as e:
                step(name, 'agents', '%s: %s' % (fn, e), False)

        for sk in (m['skills'] if 'skills' in want else []):
            from . import skills as skills_mod
            dest = skills_mod.install_skill(u_skills[sk], skills_mod.personal_dir(cfgdir))
            step(name, 'skills', sk if dest else '%s: copy failed' % sk, bool(dest))

        if 'claude_md' in want and m['claude_md'] and union_md:
            text = open(union_md, encoding='utf-8', errors='ignore').read()
            ok = _c.write_atomic(_c.global_claude_md_for(cfgdir), text)
            step(name, 'claude_md', os.path.basename(union_md), ok)

    return done


def main(argv=None):
    """`archeus sync-accounts [--yes] [--dry-run]` — show the diff, then level up.

    `--yes` IS the review gate on this path, which is why the report above it
    names every plugin and marketplace by hand. The GUI and TUI pass
    `plugins.review_plugin` instead, because they can draw the screen it needs;
    a CLI cannot prompt for it without turning a scriptable command into an
    interactive one.
    """
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    yes = '--yes' in argv or '-y' in argv
    dry = '--dry-run' in argv or '-n' in argv
    sys.stdout.reconfigure(encoding='utf-8')
    d = diff()
    print('\n'.join(report(d)))
    if d['clean'] or dry:
        return 0
    if not yes:
        print('\n  Re-run with --yes to copy the missing items into every account.')
        return 0
    print()
    for name, kind, detail, ok in apply(d, progress=lambda *a: None):
        print('  %s %-12s %-12s %s' % ('OK ' if ok else 'ERR', name, kind, detail))
    return 0
