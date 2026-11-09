"""What a verifier observes itself (p13-design-gate §8): authoritative evidence
only — git facts read at verification time and the commands P4's inspection
found, run by Core in the workspace. The agent's own report is never read here.
"""

import json
import os
import re
import shlex
import shutil

from ...infra.artifacts import store
from ...infra.db import rows
from ...infra.paths import ExecPaths, run_dir
from ..application.verification import CONFINED_VERIFIER
from ..domain import entities

#: how long one command may run (p13-design-gate §18); a test sets it lower
CHECK_TIMEOUT_S = 600
#: task kinds a CodeVerifier checks; every other kind is decided by a human (§13)
CODE_KINDS = ('code_change', 'inspection', 'verification')
#: how much of an execution's stream is read for a reported model (§22)
_STREAM_READ = 4 * 1024 * 1024


def commands(conn, project_id, root):
    """(test_commands, build_commands) of the latest COMPLETED inspection of
    the project's repository at *root* (P4); ((), ()) when there is none."""
    if project_id is None or root is None:
        return (), ()
    repos = [r.entity for r in rows.where(conn, entities.Repository, project_id=project_id)]
    key = os.path.normcase(os.path.abspath(root))
    repo = next((r for r in repos if os.path.normcase(os.path.abspath(r.path)) == key),
                repos[0] if repos else None)
    if repo is None:
        return (), ()
    done = [r.entity for r in rows.where(conn, entities.RepositoryInspection,
                                         repository_id=repo.id)
            if r.entity.state == 'COMPLETED']
    if not done:
        return (), ()
    last = done[-1]
    return tuple(last.test_commands), tuple(last.build_commands)


def project_root(conn, project_id):
    if project_id is None:
        return None
    p = rows.get(conn, entities.Project, project_id)
    roots = list(p.entity.root_paths) if p is not None else []
    return roots[0] if roots else None


def argv_of(command):
    """A command line as argv, its program resolved on PATH (so `npm` finds
    `npm.cmd` on Windows); None when it cannot be parsed."""
    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not argv:
        return None
    found = shutil.which(argv[0])
    return [found or argv[0]] + argv[1:]


def confined_argv(command, toolchain):
    """*command* as argv with its program found in the Core-staged *toolchain* and
    nowhere else (owner T-054 Q1 A), or None: it cannot run confined."""
    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not argv:
        return None
    found = shutil.which(argv[0], path=os.pathsep.join(toolchain))
    # which takes a program named with a directory as it is, and on Windows looks in
    # the current directory first: only a program inside the toolchain is one
    dirs = {os.path.normcase(os.path.abspath(d)) for d in toolchain}
    if found is None or os.path.normcase(os.path.dirname(os.path.abspath(found))) not in dirs:
        return None
    return [os.path.abspath(found)] + argv[1:]


def check_of(kind, command, argv, r):
    """The check for one run of *command* (§8.3): exit 0 → pass, non-zero →
    fail, not found or not finished → error. Its output is stored as an
    artifact (its last bytes); a confined run adds what confined it."""
    sha = store.put(r['output']) if r['output'] else None
    check = {'name': '%s: %s' % (kind, command), 'kind': 'command', 'argv': list(argv),
             'exit_code': r['exit_code'], 'duration_ms': r['duration_ms'],
             'output_sha256': sha, 'output_bytes': r['output_bytes'],
             'truncated': r['truncated']}
    if 'confinement' in r:
        check['confinement'] = r['confinement']
    if r['error']:
        check.update(result='error', detail=r['error'])
    elif r['exit_code'] == 0:
        check.update(result='pass', detail='exit 0')
    else:
        check.update(result='fail', detail='exit %s' % r['exit_code'])
    return check


def run_commands(node, workspace, cmds, *, verification_id, timeout_s, verifier_version):
    """One unconfined check per command (§8.3). A row the sink stamped confined
    never gets here: it runs only through `run_confined_check` (A6-4)."""
    if verifier_version == CONFINED_VERIFIER:
        raise ValueError('verification %s runs only confined' % verification_id)
    checks = []
    base = os.path.join(run_dir(), 'verify', verification_id)
    for i, (kind, command) in enumerate(cmds):
        name = '%s: %s' % (kind, command)
        argv = argv_of(command)
        if argv is None:
            checks.append({'name': name, 'kind': 'command', 'result': 'error',
                           'detail': 'the command line cannot be parsed'})
            continue
        r = node.run_check(workspace, argv, timeout=timeout_s,
                           out_path=os.path.join(base, '%d.log' % i))
        checks.append(check_of(kind, command, argv, r))
    return checks


def changes_check(node, root, base, revision):
    """`changes`: a code change changed something (§8.3). A diff proves only
    that something was written; it is never an outcome check."""
    if base is None or revision is None:
        return {'name': 'changes', 'kind': 'git', 'result': 'error',
                'detail': 'no base revision to compare with'}
    stat = node.git_numstat(root, base, revision)
    if stat is None:
        return {'name': 'changes', 'kind': 'git', 'result': 'error',
                'detail': 'git could not diff %s..%s' % (base[:12], revision[:12])}
    if not stat:
        return {'name': 'changes', 'kind': 'git', 'result': 'fail',
                'detail': 'the task changed nothing (%s..%s)' % (base[:12], revision[:12])}
    return {'name': 'changes', 'kind': 'git', 'result': 'pass',
            'detail': '%d file(s) changed' % len(stat), 'files': [p for _a, _d, p in stat][:50]}


#: name of the advisory check `weakening_check` records
WEAKENING = 'test weakening (advisory)'

#: how a test file of each language is told, and its tests, assertions and the
#: markers that switch a test off; the language is the file's own extension
_SHAPES = {
    'py': {
        'file': re.compile(r'(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$|(^|/)tests?/.+\.py$'),
        'test': re.compile(r'^\s*(?:async\s+)?def\s+(?P<name>test\w*)\s*\('),
        'assertion': re.compile(r'^\s*assert\b|\bself\.assert\w+\(|\bpytest\.raises\('),
        'marker': re.compile(r'@pytest\.mark\.(?:skip|skipif|xfail)\b|\bpytest\.(?:skip|xfail)\('
                             r'|@unittest\.(?:skip\w*|expectedFailure)\b')},
    'ts': {
        'file': re.compile(r'\.(?:test|spec)\.[cm]?[jt]sx?$|(^|/)__tests__/.+\.[cm]?[jt]sx?$'),
        'test': re.compile(r'^\s*(?:it|test)(?:\.\w+)*\s*\(\s*(?P<q>[\'"`])(?P<name>.+?)(?P=q)'),
        'assertion': re.compile(r'\bexpect\s*\(|\bassert(?:\.\w+)?\s*\('),
        'marker': re.compile(r'\b(?:it|test|describe)(?:\.\w+)*\.(?:only|skip|todo|fixme)\b'
                             r'|\b(?:xit|xtest|xdescribe|fit|fdescribe)\s*\(')}}
#: a bound a test file states as `name = 12`, `name: 12` or `name(12)`
_BOUND = re.compile(r'(timeout|threshold|tolerance|deadline)\w*["\']?\s*[=:(]\s*(\d[\d_]*(?:\.\d+)?)',
                    re.I)
_FINDINGS_KEPT = 50


def _shape_of(path):
    return next((s for s in _SHAPES.values() if path and s['file'].search(path)), None)


def _parse_diff(diff):
    """[{path, deleted, hunks: [(removed, added)]}] of a `git diff -U0`: the lines of
    each hunk, never the headers (a removed `-- x` line reads like one)."""
    files, cur, in_hunk = [], None, False
    for line in diff.splitlines():
        if line.startswith('diff --git '):
            cur, in_hunk = {'path': None, 'deleted': False, 'hunks': []}, False
            files.append(cur)
        elif cur is None:
            continue
        elif line.startswith('@@ '):
            cur['hunks'].append(([], []))
            in_hunk = True
        elif in_hunk:
            if line[:1] in ('-', '+'):
                cur['hunks'][-1][line[0] == '+'].append(line[1:])
        elif line.startswith('deleted file mode'):
            cur['deleted'] = True
        elif line.startswith(('--- a/', '+++ b/')):
            cur['path'] = line[6:].split('\t')[0]
    return files


def _bounds(line):
    return {m.group(1).lower(): float(m.group(2).replace('_', '')) for m in _BOUND.finditer(line)}


def _clip(text, n=80):
    text = text.strip()
    return text if len(text) <= n else text[:n - 3] + '...'


def weakening(diff):
    """What a `git diff -U0` does to the tests it touches, as a list of findings:
    test files deleted, test functions removed (and named nowhere in what was
    added), assertions removed (net per file), skip/xfail/`.only` markers added
    and timeouts or thresholds raised. Pure; a finding is a claim to check, not a
    verdict."""
    kept = [(f, _shape_of(f['path'])) for f in _parse_diff(diff)]
    added_names = {m.group('name') for f, s in kept if s and not f['deleted']
                   for _r, adds in f['hunks'] for a in adds if (m := s['test'].match(a))}
    found = []
    for f, s in kept:
        if s is None:
            continue
        if f['deleted']:
            found.append('test file deleted: %s' % f['path'])
            continue
        removed = [r for rs, _a in f['hunks'] for r in rs]
        added = [a for _r, adds in f['hunks'] for a in adds]
        for r in removed:
            m = s['test'].match(r)
            if m and m.group('name') not in added_names:
                found.append('test removed: %s::%s' % (f['path'], _clip(m.group('name'))))
        net = (sum(bool(s['assertion'].search(r)) for r in removed)
               - sum(bool(s['assertion'].search(a)) for a in added))
        if net > 0:
            found.append('assertions removed: %s (%d net)' % (f['path'], net))
        gone = {r.strip() for r in removed}
        for a in added:
            if s['marker'].search(a) and a.strip() not in gone:
                found.append('skip/xfail/only marker added: %s: %s' % (f['path'], _clip(a)))
        for rs, adds in f['hunks']:
            for r, a in zip(rs, adds):
                old, new = _bounds(r), _bounds(a)
                found += ['%s raised: %s (%g -> %g)' % (k, f['path'], old[k], new[k])
                          for k in new if k in old and new[k] > old[k]]
    return found


def weakening_check(node, root, base, revision):
    """The advisory `git` check of what the change did to the tests, or None when
    it did nothing to them. Always `pass`: it informs the review and the trace and
    never decides the verdict. Reads Git facts only."""
    diff = node.git_diff(root, base, revision)
    if diff is None:
        return {'name': WEAKENING, 'kind': 'git', 'result': 'pass',
                'detail': 'git could not read the diff of %s..%s' % (base[:12], revision[:12])}
    found = weakening(diff)
    if not found:
        return None
    return {'name': WEAKENING, 'kind': 'git', 'result': 'pass',
            'detail': '%d finding(s), advisory' % len(found), 'findings': found[:_FINDINGS_KEPT]}


def reported_model(execution_id):
    """The last model the execution's own stream names, or None (§22):
    corroborating evidence, compared with the routed model, never trusted."""
    path = ExecPaths(execution_id).stream
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            f.seek(max(0, size - _STREAM_READ))
            data = f.read()
    except OSError:
        return None
    found = None
    for line in data.decode('utf-8', 'replace').splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        m = ev.get('model')
        if not isinstance(m, str):
            msg = ev.get('message')
            m = msg.get('model') if isinstance(msg, dict) else None
        if isinstance(m, str) and m:
            found = m
    return found


def provenance(e):
    """{routed_model, reported_model, match} for execution *e* (§22)."""
    reported = reported_model(e.id)
    return {'routed_model': e.model, 'reported_model': reported,
            'match': reported is None or e.model is None or reported == e.model}
