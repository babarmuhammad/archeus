"""What a verifier observes itself (p13-design-gate §8): authoritative evidence
only — git facts read at verification time and the commands P4's inspection
found, run by Core in the workspace. The agent's own report is never read here.
"""

import json
import os
import shlex
import shutil

from ...infra.artifacts import store
from ...infra.db import rows
from ...infra.paths import ExecPaths, run_dir
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


def run_commands(node, workspace, cmds, *, verification_id, timeout_s):
    """One check per command (§8.3): exit 0 → pass, non-zero → fail, not found
    or timed out → error. Output is stored as an artifact (its last bytes)."""
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
        sha = store.put(r['output']) if r['output'] else None
        check = {'name': name, 'kind': 'command', 'argv': list(argv),
                 'exit_code': r['exit_code'], 'duration_ms': r['duration_ms'],
                 'output_sha256': sha, 'output_bytes': r['output_bytes'],
                 'truncated': r['truncated']}
        if r['error']:
            check.update(result='error', detail=r['error'])
        elif r['exit_code'] == 0:
            check.update(result='pass', detail='exit 0')
        else:
            check.update(result='fail', detail='exit %s' % r['exit_code'])
        checks.append(check)
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
