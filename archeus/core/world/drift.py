"""Architecture drift (p4-design-gate §6.4; context-and-knowledge §6 step 6).

`evaluate` is a pure function of an inspection payload and the project's
CONFIRMED constraints: every constraint gets one finding — `violated`,
`satisfied` or `unchecked` with its reason — and nothing is assumed
satisfied that could not be checked. Patterns are repository-relative and
matched with `fnmatch` on `/`-separated paths, so `*` also crosses `/`
(`app/core/*` and `app/core/**` both mean everything under `app/core/`).

`token` names the exact constraint set an assessment was made against, so a
constraint declared after the evaluation cannot pass for one it saw.
"""

import hashlib
import json
import re
from fnmatch import fnmatchcase

from .inspection import norm_package

MAX_LISTED = 20


def token(constraints):
    """The identity of a constraint set: its (id, version) pairs."""
    pairs = sorted([c['id'], c['version']] for c in constraints)
    return hashlib.sha256(json.dumps(pairs).encode('utf-8')).hexdigest()


def _finding(c, status, reason=None, violations=()):
    violations = sorted(violations)
    return {'constraint_id': c['id'], 'constraint': c['statement'],
            'kind': (c['constraint'] or {}).get('kind'), 'status': status, 'reason': reason,
            'violations': [list(v) for v in violations[:MAX_LISTED]],
            'violation_count': len(violations)}


def _edges_finding(c, payload, bad):
    if bad:
        return _finding(c, 'violated', '%d import(s) break it' % len(bad), bad)
    if payload['truncated']:
        return _finding(c, 'unchecked', 'graph_truncated')
    return _finding(c, 'satisfied')


def _version_of(spec):
    m = re.search(r'\d+(?:\.\d+)*', spec or '')
    return m.group(0) if m else None


def _pins(spec, version):
    """Does a declared specifier name *version* (itself, or a release of it:
    `19` is pinned by `^19.3.0`)? No resolver: the first version-like token."""
    got = _version_of(spec)
    return got is not None and (got == version or got.startswith(version + '.'))


def evaluate(payload, constraints):
    """One finding per constraint, in constraint-id order. *constraints* are
    `{id, version, statement, constraint}` (`constraint` None: prose)."""
    files, edges = payload['files'], [tuple(e) for e in payload['edges']]
    out = []
    for c in sorted(constraints, key=lambda x: x['id']):
        con = c['constraint']
        if con is None:
            out.append(_finding(c, 'unchecked', 'prose: cannot check automatically'))
            continue
        kind, spec = con['kind'], con['spec']
        if kind == 'forbid_dependency':
            bad = [(s, d) for s, d in edges
                   if fnmatchcase(s, spec['from']) and fnmatchcase(d, spec['to'])]
            out.append(_edges_finding(c, payload, bad))
        elif kind == 'require_layering':
            def layer(path, layers=spec['layers']):
                return next((i for i, g in enumerate(layers) if fnmatchcase(path, g)), None)
            bad = [(s, d) for s, d in edges
                   if layer(s) is not None and layer(d) is not None and layer(d) < layer(s)]
            out.append(_edges_finding(c, payload, bad))
        elif kind == 'module_exists':
            if any(fnmatchcase(f, spec['path']) for f in files):
                out.append(_finding(c, 'satisfied'))
            elif payload['truncated']:
                out.append(_finding(c, 'unchecked', 'graph_truncated'))
            else:
                out.append(_finding(c, 'violated', 'no file matches %s' % spec['path']))
        elif kind == 'framework_pinned':
            want = norm_package(spec['package'])
            found = [d for d in payload['dependencies'] if d['name'] == want]
            if not found:
                out.append(_finding(c, 'violated', '%s is not a dependency' % want))
            elif spec.get('version') is None:
                out.append(_finding(c, 'satisfied'))
            else:
                v = spec['version']
                ok = [d for d in found if _pins(d['spec'], v)]
                out.append(_finding(c, 'satisfied') if ok else _finding(
                    c, 'violated', '%s is declared as %r, not %s'
                    % (want, ', '.join(d['spec'] or '(unpinned)' for d in found), v)))
        else:           # doc_matches_code: no deterministic definition exists
            out.append(_finding(c, 'unchecked', '%s: cannot check automatically' % kind))
    return out


def violated(findings):
    return any(f['status'] == 'violated' for f in findings)
