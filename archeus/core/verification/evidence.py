"""What a verifier observes itself (p13-design-gate §8): authoritative evidence
only — git facts read at verification time and the commands P4's inspection
found, run by Core in the workspace. The agent's own report is never read here.
"""

import codecs
import json
import os
import re
import shlex

from claude_sessions import proc
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


def argv_of(command, workspace=None):
    """A command line as argv, a bare program resolved on PATH (so `npm` finds
    `npm.cmd` on Windows) outside the current directory and *workspace*; None
    when it cannot be parsed or the program is not found there. A program named
    with a directory is the project's own script and is kept as written."""
    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not argv:
        return None
    if os.path.dirname(argv[0]):
        return argv
    found = proc.which(argv[0], avoid=[workspace])
    return [found] + argv[1:] if found else None


def confined_argv(command, toolchain):
    """*command* as argv with its program found in the Core-staged *toolchain* and
    nowhere else (owner T-054 Q1 A), or None: it cannot run confined."""
    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not argv:
        return None
    found = proc.which(argv[0], path=os.pathsep.join(toolchain))
    return [found] + argv[1:] if found else None


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
        argv = argv_of(command, workspace)
        if argv is None:
            checks.append({'name': name, 'kind': 'command', 'result': 'error',
                           'detail': 'the command line cannot be parsed or its program is '
                                     'not on PATH outside the workspace'})
            continue
        r = node.run_check(workspace, argv, timeout=timeout_s,
                           out_path=os.path.join(base, '%d.log' % i))
        checks.append(check_of(kind, command, argv, r))
    return checks


#: what a failed test check is called by the same command's result at the base (T-1068)
BASE_LABELS = {'pass': 'regressed', 'fail': 'also fails in a clean base checkout'}


def base_of(check, base):
    """What one run of a command at revision *base* showed, as kept on the
    failed check it explains (T-1068): the command's result, never a verdict."""
    return {'revision': base, 'result': check['result'], 'exit_code': check.get('exit_code'),
            'output_sha256': check.get('output_sha256'), 'detail': check.get('detail'),
            'label': BASE_LABELS.get(check['result'])}


def with_base(check, base):
    """*check* with what its command showed at the base, when it failed and a
    base run is known. Advisory: its result stays as it is, so no verdict moves;
    the label names the whole command, not which of its tests regressed."""
    if base is None or check.get('result') != 'fail':
        return check
    out = dict(check, baseline=base)
    if base['label'] is not None:
        out['detail'] = '%s; %s (%s)' % (check.get('detail'), base['label'], base['revision'][:12])
    return out


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
_LINE_MAX = 2000


def _shape_of(path):
    return next((s for s in _SHAPES.values() if path and s['file'].search(path)), None)


def _path(header):
    """The path of a `--- a/x` or `+++ b/x` line, unquoted; None for /dev/null."""
    p = header[4:].split('\t')[0]
    if p.startswith('"') and p.endswith('"'):
        p = codecs.escape_decode(p[1:-1].encode('utf-8'))[0].decode('utf-8', 'replace')
    return p[2:] if p[:2] in ('a/', 'b/') else None


def _parse_diff(diff):
    """[{path, deleted, skipped, hunks: [(removed, added)]}] of a `git diff -U0`: the
    lines of each hunk, never the headers (a removed `-- x` line reads like one).
    Only a test file's hunks are kept, and a line longer than _LINE_MAX is counted
    as skipped instead (the patterns are not linear in it: a minified line would
    stall the verifier)."""
    files, cur, in_hunk, keep = [], None, False, False
    for line in diff.split('\n'):
        if line.startswith('diff --git '):
            # both names are the same one (no renames), so the first half is `a/<path>`:
            # a file Git shows as binary has no `---` line to read it from
            names = line[len('diff --git '):]
            cur, in_hunk = {'path': _path('--- ' + names[:len(names) // 2]), 'deleted': False,
                            'skipped': 0, 'hunks': []}, False
            files.append(cur)
        elif cur is None:
            continue
        elif line.startswith('@@ '):
            cur['hunks'].append(([], []))
            in_hunk, keep = True, _shape_of(cur['path']) is not None
        elif in_hunk:
            if keep and line[:1] in ('-', '+'):
                if len(line) <= _LINE_MAX:
                    cur['hunks'][-1][line[0] == '+'].append(line[1:])
                else:
                    cur['skipped'] += 1
        elif line.startswith('deleted file mode'):
            cur['deleted'] = True
        elif line.startswith(('--- ', '+++ ')):
            cur['path'] = _path(line) or cur['path']
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
    and timeouts or thresholds raised, and how many changed lines were too long to
    inspect. Pure; a finding is a claim to check, not a verdict."""
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
        if f['skipped']:
            found.append('%d changed line(s) too long to inspect: %s' % (f['skipped'], f['path']))
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


def memory_check(conn, mission_id):
    """`memory`: advisory, never `fail`. `pass` when a knowledge row cites the mission
    (a lesson learned from it), `skip` when none does yet; the verdict ignores both."""
    n = sum(r.entity.valid_until is None for r in rows.where(
        conn, entities.Relation, src_kind='knowledge_item', rel='learned_from',
        dst_kind='mission', dst_id=mission_id))
    if n:
        return {'name': 'memory', 'kind': 'state', 'result': 'pass',
                'detail': '%d knowledge relation(s) cite this mission' % n}
    return {'name': 'memory', 'kind': 'state', 'result': 'skip',
            'detail': 'no knowledge, decision or lesson row cites this mission yet'}


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
