"""Repository discovery, the cheap HEAD check and the deterministic
inspection pass (p4-design-gate §6.2, §6.3; context-and-knowledge §6).

Everything here reads the filesystem and nothing here writes Archeus state:
the world worker turns what it returns into writer commands. The import graph
is `connections.build_hierarchy`, reused as-is (migration-plan §2). Its
`.archeus/connections-cache.json` inside the inspected repository is derived,
non-authoritative state (D8): nothing reads it back, and the graph is always
rebuilt (`force=True`) because its cache key — file count and whole-second
mtime — cannot see an edit made in the same second.
"""

import json
import os
import re

from claude_sessions import connections, repos

#: Bumped whenever any extractor's output can change, so an inspection stored
#: by an older extractor is never taken for a current one.
EXTRACTOR_VERSION = 1

_SHA = re.compile(r'[0-9a-f]{40}([0-9a-f]{24})?')


class Unreadable(Exception):
    """The repository cannot be observed; `reason` is the failure recorded."""

    def __init__(self, reason, detail=''):
        super().__init__('%s%s' % (reason, ': %s' % detail if detail else ''))
        self.reason = reason


def path_key(path):
    """One key per directory on this machine: resolved links, case folded
    where the filesystem folds case (Windows)."""
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _read(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def head_revision(path):
    """HEAD's commit SHA, from `.git` alone: HEAD, then the ref in the gitdir,
    the common dir (a linked worktree keeps its refs there) and packed-refs;
    `git rev-parse HEAD` only when those cannot answer. Raises Unreadable."""
    if not os.path.isdir(path):
        raise Unreadable('repository_missing', path)
    gd = repos._gitdir(path)
    if not gd:
        raise Unreadable('head_unresolvable', 'no .git')
    try:
        head = _read(os.path.join(gd, 'HEAD')).strip()
    except OSError:
        head = ''
    if _SHA.fullmatch(head):
        return head
    if head.startswith('ref:'):
        ref = head[4:].strip()
        common = gd
        try:
            common = os.path.normpath(os.path.join(gd, _read(os.path.join(gd, 'commondir')).strip()))
        except OSError:
            pass
        for base in dict.fromkeys((gd, common)):
            try:
                sha = _read(os.path.join(base, *ref.split('/'))).strip()
            except OSError:
                continue
            if _SHA.fullmatch(sha):
                return sha
        try:
            for line in _read(os.path.join(common, 'packed-refs')).splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref and _SHA.fullmatch(parts[0]):
                    return parts[0]
        except OSError:
            pass
    out = (repos._git(['rev-parse', 'HEAD'], path, timeout=10) or '').strip()
    if _SHA.fullmatch(out):
        return out
    raise Unreadable('head_unresolvable', head[:80] or 'empty HEAD')


def discover(root_paths):
    """[(path, kind)] for every repository a project's roots hold: each root
    that is itself a repository, submodule or linked worktree, and the
    repositories and submodules below it (depth 4). Linked worktrees are found
    only when named as a root — `find_git_repos` skips them by design, so a
    repository's worktrees never count as extra repositories. Raises ValueError
    for a root that is not an absolute directory, or that holds no repository."""
    if not root_paths:
        raise ValueError('a project needs at least one root path')
    found = {}
    for root in root_paths:
        if not (isinstance(root, str) and os.path.isabs(root)):
            raise ValueError('root path %r is not absolute' % (root,))
        if not os.path.isdir(root):
            raise ValueError('root path %r is not a directory' % root)
        here = []
        kind = repos.classify(root)
        if kind == 'worktree':
            here.append((os.path.abspath(root), 'worktree'))
        here += [(p, repos.classify(p) or 'repo') for p in repos.find_git_repos(root)]
        if not here:
            raise ValueError('no git repository at or under %r' % root)
        for p, k in here:
            found.setdefault(path_key(p), (os.path.normpath(p), k))
    return sorted(found.values())


# ── the deterministic pass ─────────────────────────────────────────────────

_REQ_NAME = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$')
_FRAMEWORKS = {'django', 'flask', 'fastapi', 'starlette', 'pyramid', 'tornado', 'pytest',
               'react', 'react-dom', 'next', 'vue', 'nuxt', 'svelte', '@sveltejs/kit',
               'angular', '@angular/core', 'express', 'fastify', 'nestjs', '@nestjs/core',
               'vite', 'jest', 'vitest', 'playwright', '@playwright/test', 'electron',
               'actix-web', 'axum', 'rocket', 'tokio', 'gin', 'echo', 'fiber'}


def norm_package(name):
    return re.sub(r'[-_.]+', '-', name.strip().lower())


def _requirement(line, manifest):
    line = line.split('#', 1)[0].strip()
    if not line or line.startswith('-'):
        return None
    m = _REQ_NAME.match(line)
    if not m:
        return None
    spec = m.group(3).split(';', 1)[0].strip()
    return {'name': norm_package(m.group(1)), 'spec': spec, 'manifest': manifest}


def _pyproject(text):
    """`[project] dependencies = [...]` read with a regex, the same on every
    Python this package supports (3.10 has no tomllib, and two parsers would
    make an inspection depend on the interpreter)."""
    sect = re.search(r'^\[project\]\s*$(.*?)(?=^\[|\Z)', text, re.M | re.S)
    if not sect:
        return []
    block = re.search(r'^dependencies\s*=\s*\[(.*?)\]', sect.group(1), re.M | re.S)
    if not block:
        return []
    items = re.findall(r'"([^"]*)"|\'([^\']*)\'', block.group(1))
    return [d for d in (_requirement(a or b, 'pyproject.toml') for a, b in items) if d]


def _dependencies(root, notes):
    deps = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            continue
        try:
            if name == 'pyproject.toml':
                deps += _pyproject(_read(p))
            elif re.fullmatch(r'requirements.*\.txt', name):
                deps += [d for d in (_requirement(ln, name) for ln in _read(p).splitlines())
                         if d]
            elif name == 'package.json':
                data = json.loads(_read(p))
                for key in ('dependencies', 'devDependencies'):
                    for dep, spec in sorted((data.get(key) or {}).items()):
                        deps.append({'name': norm_package(dep), 'spec': str(spec),
                                     'manifest': 'package.json'})
            elif name == 'Cargo.toml':
                sect = re.search(r'^\[dependencies\]\s*$(.*?)(?=^\[|\Z)', _read(p), re.M | re.S)
                for dep, rest in re.findall(r'^([A-Za-z0-9_-]+)\s*=\s*(.+)$',
                                            sect.group(1) if sect else '', re.M):
                    v = re.search(r'"([^"]+)"', rest)
                    deps.append({'name': norm_package(dep), 'spec': v.group(1) if v else '',
                                 'manifest': 'Cargo.toml'})
            elif name == 'go.mod':
                for dep, ver in re.findall(r'^\s*(?:require\s+)?([\w./-]+\.[\w./-]+)\s+(v[\w.+-]+)',
                                           _read(p), re.M):
                    deps.append({'name': dep.lower(), 'spec': ver, 'manifest': 'go.mod'})
        except (OSError, ValueError) as e:
            notes.append('%s could not be read: %s' % (name, e))
    return deps


def _commands(root, deps):
    tests, builds = [], []
    try:
        scripts = json.loads(_read(os.path.join(root, 'package.json'))).get('scripts') or {}
    except (OSError, ValueError):
        scripts = {}
    if 'test' in scripts:
        tests.append('npm test')
    if 'build' in scripts:
        builds.append('npm run build')
    names = {d['name'] for d in deps}
    if 'pytest' in names or os.path.isdir(os.path.join(root, 'tests')) and (
            os.path.isfile(os.path.join(root, 'pyproject.toml'))
            or os.path.isfile(os.path.join(root, 'setup.py'))):
        tests.append('python -m pytest')
    if os.path.isfile(os.path.join(root, 'pyproject.toml')):
        builds.append('python -m build')
    if os.path.isfile(os.path.join(root, 'Cargo.toml')):
        tests.append('cargo test')
        builds.append('cargo build')
    if os.path.isfile(os.path.join(root, 'go.mod')):
        tests.append('go test ./...')
        builds.append('go build ./...')
    return tests, builds


def _inside(rel, prefixes):
    return any(rel == p or rel.startswith(p + '/') for p in prefixes)


def inspect(path):
    """(observation, payload) of the working tree at *path*. The observation
    is what the inspection row keeps; the payload — every file, every
    file-level import edge, the dependencies, whether the graph was truncated —
    is what drift is evaluated on and becomes a content-addressed artifact.
    Files of nested repositories (submodules) are excluded: each is its own
    Repository. Raises Unreadable when the tree cannot be read at all."""
    if not os.path.isdir(path):
        raise Unreadable('repository_missing', path)
    root = os.path.abspath(path)
    nested = sorted(os.path.relpath(p, root).replace(os.sep, '/')
                    for p in repos.find_git_repos(root) if path_key(p) != path_key(root))
    graph = connections.build_hierarchy(root, force=True)
    files = sorted(n['id'][5:] for n in graph['nodes']
                   if n['type'] == 'file' and not _inside(n['id'][5:], nested))
    fileset = set(files)
    edges = sorted({(e['source'][5:], e['target'][5:]) for e in graph['dep_edges']
                    if e['source'].startswith('file:') and e['target'].startswith('file:')
                    and e['source'][5:] in fileset and e['target'][5:] in fileset})
    notes = []
    deps = _dependencies(root, notes)
    tests, builds = _commands(root, deps)
    langs = {}
    for f in files:
        lang = connections._EXT_LANG.get(os.path.splitext(f)[1].lower())
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    top = sorted(os.listdir(root))
    status = repos._git(['status', '--porcelain'], root, timeout=15)
    if status is None:
        notes.append('git status failed: the working tree is treated as dirty')
    truncated = bool(graph['meta'].get('truncated'))
    observation = {
        'languages': sorted(([k, v] for k, v in langs.items()), key=lambda x: (-x[1], x[0])),
        'dependencies': deps,
        'frameworks': sorted({d['name'] for d in deps if d['name'] in _FRAMEWORKS}),
        'docs': [n for n in top if re.match(r'readme', n, re.I)]
                + (['docs/'] if os.path.isdir(os.path.join(root, 'docs')) else []),
        'agent_config': [n for n in ('CLAUDE.md', 'AGENTS.md', '.claude') if n in top],
        'test_commands': tests, 'build_commands': builds,
        'dirty': status is None or bool(status.strip()),
        'complete': not truncated,
        'notes': notes,
    }
    payload = {'extractor_version': EXTRACTOR_VERSION, 'files': files,
               'edges': [list(e) for e in edges], 'dependencies': deps,
               'truncated': truncated, 'nested': nested}
    return observation, payload


def diff(previous, payload, prev_obs=None, obs=None):
    """What changed since the previous inspection (context-and-knowledge §6.5)."""
    if previous is None:
        return None
    before, after = set(previous['files']), set(payload['files'])
    dep = lambda p: {d['name']: d['spec'] for d in p['dependencies']}
    db, da = dep(previous), dep(payload)
    out = {'files_added': len(after - before), 'files_removed': len(before - after),
           'dependencies_added': sorted(set(da) - set(db)),
           'dependencies_removed': sorted(set(db) - set(da)),
           'dependencies_changed': sorted(k for k in set(da) & set(db) if da[k] != db[k])}
    if prev_obs is not None and obs is not None:
        for k in ('test_commands', 'build_commands', 'agent_config', 'frameworks'):
            if list(prev_obs.get(k) or ()) != list(obs.get(k) or ()):
                out.setdefault('changed', []).append(k)
    return out
