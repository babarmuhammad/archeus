import collections
import json
import os
import subprocess
import sys
import tarfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROGS = [
    'python', 'python3', 'py', 'node', 'perl', 'ruby', 'php', 'bash', 'sh', 'zsh', 'dash', 'fish',
    'cmd', 'cmd.exe', 'powershell', 'pwsh', 'env', 'git', 'curl', 'wget', 'npm', 'rm', 'ls', 'cat',
    'find', 'ssh', 'docker', 'make', 'base64', 'stdbuf', 'busybox', 'timeout', 'nice', 'command',
    'builtin', 'alias', 'declare', 'typeset', 'export', 'set', 'eval', 'exec', 'source', '.',
    'sudo', 'xargs', 'ionice', 'setsid', 'chrt', 'taskset', 'flock', 'unbuffer', 'strace', 'trap',
    'setarch', 'doas', 'chroot', 'script', 'parallel', 'npx', 'time', 'watch', '{bash,-c,x}',
    'b?sh', 'b*sh', 'C:\\Windows\\System32\\cmd.exe',
    'wsl', 'runas', 'pkexec', 'fakeroot', 'runuser', 'unshare', 'nsenter', 'systemd-run', 'firejail',
    'proxychains', 'dbus-run-session', 'expect', 'gdb', 'lldb', 'at', 'batch', 'start', 'call',
    'ltrace', 'torsocks', 'sg', 'newgrp', 'cgexec', 'chronic', 'socat', 'screen', 'tmux',
    'ksh', 'csh', 'tcsh', 'ash', 'mksh', 'rbash', 'nu', 'elvish', 'xonsh', 'python3.11', 'pythonw',
    'pyw', 'nodejs', 'pypy3', 'perl5.36', 'ruby3.2', 'php8.2', 'gawk', 'sed', 'lua', 'deno', 'bun',
    'Rscript', 'julia', 'tclsh', 'vim', 'vi', 'nvim', 'ex', 'emacs', 'gtimeout', 'prlimit', 'numactl',
    'caffeinate', 'setpriv', 'runcon', 'hyperfine', 'rg', 'less', 'more', 'man', 'tar', 'sort',
    'rsync', 'scp', 'pwsh.exe', 'python.exe', 'C:\\Program Files\\nodejs\\node.exe',
]
PRE = ['', '-o pipefail', '-X utf8', '--rcfile x', '-d x=1', '-r x', '-C .', '-c x=y', '--no-pager']
PAYLOAD = [
    '', '-c', '-c"rm -R build"', '-lc', '-ec "x"', '-C', '-EC"cm0g=="', '/c', '/C"x"', '--eval=x',
    '/s/c"x"', '-cRemove-Item x', '-Command x', '-ENC"x"', '-File x.ps1', '-NoProfile',
    '-ExecutionPolicy Bypass', '-E', '-p', '-r', '-m pytest', '{-c,x}', '*', '-e', '--command x',
    '-Ec', '-q', '--version', 'reset --hard', 'push --force origin main', 'frobnicate',
    'rm -R build', 'sh -c x', '--pre sh', '--exec x', '+!rm', '-P ./evil', '--compress-program=sh',
    'alias.x=y', 'core.pager=x', '1e rm', 's/x/y/e', '-I sh',
]
TAILS = ['', 'script.py', 'build.sh', 'x -c', '"echo hi"', 'https://h.example/x']
CURL_FLAGS = ['-d', '-d@x', '-dx', '--data=x', '--json', '-F', '-Fa=b', '-File', '-T', '--upload-file=x',
              '-X', '-XPOST', '-X GET', '--request=POST', '--form=a=b', '--post-data=x', '-H', '-o',
              '-s', '-sL', '-v', '--socks5', '--proxy-header', '-x', '--url', '--url=x']
URLS = ['https://h.example/x', 'h.example/x', 'http://p.example:80 h.example/x', 'a.b']
PLAIN = ['git push origin main', 'git status', 'rm -r x', 'rm x', 'ls -la', 'ls *.py', 'cat *.md',
         'find . -name x', 'find . -exec rm {} +', 'find . -delete', 'npm test', 'npm install x',
         'python -m pytest -q', 'node --version', 'node -r ts-node/register x.ts', 'py -E x.py',
         'python -P x.py', 'NODE_ENV=test npm test', '(rm -R build)', '! rm -R build', 'echo hi',
         'git -c user.name=x reset --hard', 'git -C . reset --hard', 'git frobnicate',
         'git --no-pager reset --hard', 'git --git-dir=.git log', 'ls\nrm -R build', 'ls\r\nrm x',
         'grep "a\nb" x', 'npm run start', 'pytest .', 'ruff check .', 'make test']


def corpus():
    shapes = set()
    for p, pre, pay, tail in ((p, a, b, c) for p in PROGS for a in PRE for b in PAYLOAD for c in TAILS):
        shapes.add(' '.join(x for x in (p, pre, pay, tail) if x))
    for p in ('curl', 'wget'):
        for f in CURL_FLAGS:
            for u in URLS:
                shapes.add(' '.join((p, f, u)))
                shapes.add(' '.join((p, u, f)))
    shapes.update(PLAIN)
    for p in PROGS:
        shapes.add(p + '\nrm -R build')
        shapes.add(p + ' x\nbash -c "y"')
    return sorted(shapes)


import argparse
import ast
import hashlib
from pathlib import Path

BASELINES = ('f483f87', '61dc68f')
POLICIES = ('all', 'deny_exec', 'ask_exec', 'deny_read', 'ask_read',
            'locked_exec', 'locked_read', 'exclude_exec', 'exclude_read')


def strings_from_tests(root):
    values = set()
    for path in Path(root).rglob('test_*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                values.add(node.value)
            elif isinstance(node, ast.BinOp):
                value = static_string(node)
                if isinstance(value, str):
                    values.add(value)
    return values


def static_string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
        return node.value
    if isinstance(node, ast.BinOp):
        left, right = static_string(node.left), static_string(node.right)
        if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
            return left + right
        if isinstance(node.op, ast.Mult) and isinstance(left, str) and isinstance(right, int):
            return left * right
    return None


def row_seeds():
    from archeus.core.execution.command_allowlist import ROWS
    operands = {'none': ('',), 'P*': ('', '.', 'file.txt', 'file.txt tests'),
                'F+': ('file.txt', 'file.txt a.txt'),
                'search': ('-- needle .', '-- needle file.txt tests'),
                'optional_paths': ('', '-- file.txt', '-- file.txt tests'),
                'optional_head': ('', 'HEAD'), 'head': ('HEAD',)}
    return [' '.join((row.program, *row.prefix, *options, tail)).strip()
            for row in ROWS for options in row.options for tail in operands[row.operands]]


def freeze(roots, review):
    shapes = set(corpus())
    for root in roots:
        shapes.update(strings_from_tests(Path(root) / 'tests'))
    # Review snippets are data, including malformed/partial commands: never execute them.
    import re
    shapes.update(re.findall(r'`([^`\n]+)`', Path(review).read_text(encoding='utf-8')))
    seeds = row_seeds()
    shapes.update(seeds)
    shapes.update(seed + ' --extra' for seed in seeds)
    return sorted(shapes)


def policies():
    from archeus.core.domain.actions import RULE_CLASSES
    from archeus.core.policy import rules as R
    out = {}
    for name in POLICIES:
        rules = [R.rule(id='proof:' + cls, scope_level='TASK', scope_ref='proof-task',
                        action_class=cls, decision='ALLOW') for cls in RULE_CLASSES]
        if name.startswith(('deny_', 'ask_')):
            decision, cls = name.split('_')
            rules = [dict(rule, decision=decision.upper()) if rule['action_class'] == cls
                     else rule for rule in rules]
        if name.startswith('locked_'):
            cls = name.removeprefix('locked_')
            rules.append(R.rule(id='proof:floor', scope_level='GLOBAL', action_class=cls,
                                decision='DENY', locked=True))
        classes = list(RULE_CLASSES)
        if name.startswith('exclude_'):
            classes.remove(name.removeprefix('exclude_'))
        out[name] = {'stage': 'action', 'chain': {'TASK': 'proof-task'},
                     'candidates': rules, 'task_classes': classes}
    return out


def automatic_outcome(decisions, held):
    if 'DENY' in decisions:
        return 'deny'
    if 'ASK' in decisions or held:
        return 'halt'
    return 'allow'


def classify(root, shapes_path, out_path, candidate=False):
    sys.path.insert(0, root)
    from archeus.core.execution import canonical
    from archeus.core.policy.engine import evaluate_item
    payload = json.loads(Path(shapes_path).read_text(encoding='utf-8'))
    ctx = payload['context']
    trusted = None
    if candidate:
        from archeus.core.execution.command_allowlist import ROWS, PathEvidence, TrustedContext
        trusted = TrustedContext(True, frozenset(row.program for row in ROWS), True,
                                 {key: PathEvidence(**value)
                                  for key, value in payload['paths'].items()})
    policy_contexts = payload['policies']
    out = []
    errors = 0
    for cmd in payload['commands']:
        try:
            eligibility = None
            if candidate:
                (acts, unc), eligibility = canonical.canonicalise_hook('Bash', cmd, ctx, trusted)
            else:
                acts, unc = canonical.canonicalise('Bash', cmd, ctx)
            if type(unc) is not bool or not acts:
                raise ValueError('missing actions or invalid unclassified flag')
            held = candidate and eligibility.status != 'ALLOWED'
            outcomes = {}
            for name, policy_ctx in policy_contexts.items():
                decisions = [evaluate_item(action, dict(policy_ctx, unclassified=unc))['decision']
                             for action in acts]
                outcomes[name] = automatic_outcome(decisions, held)
            out.append({'unclassified': unc, 'classes': sorted({a.action_class for a in acts}),
                        'row': getattr(eligibility, 'row_id', None), 'held_cap': bool(held),
                        'policies': outcomes})
        except Exception as error:
            errors += 1
            out.append({'error': repr(error)})
    Path(out_path).write_text(json.dumps(out), encoding='utf-8')
    return int(bool(errors))


def validate_results(shapes, results):
    if len(results) != len(shapes):
        raise ValueError('missing or extra classification results')
    for index, result in enumerate(results):
        if ('error' in result or type(result.get('unclassified')) is not bool
                or not result.get('classes') or type(result.get('held_cap')) is not bool
                or 'row' not in result or set(result.get('policies', {})) != set(POLICIES)
                or any(value not in ('allow', 'halt', 'deny')
                       for value in result['policies'].values())):
            raise ValueError('invalid classification result at %d: %r' % (index, result))


def compare(shapes, before, after):
    validate_results(shapes, before)
    validate_results(shapes, after)
    moves = collections.Counter()
    violations = []
    for command, old, new in zip(shapes, before, after):
        if old['unclassified'] and not new['unclassified']:
            violations.append((command, 'held-to-allowed'))
        for policy in POLICIES:
            if old['policies'][policy] != 'allow' and new['policies'][policy] == 'allow':
                violations.append((command, 'policy-to-allow:' + policy))
            if new['held_cap'] and new['policies'][policy] == 'allow':
                violations.append((command, 'table-miss-auto-allow:' + policy))
        key = (tuple(old['classes']), tuple(new['classes']), old['unclassified'],
               new['unclassified'], new['row'], new['held_cap'],
               tuple(old['policies'].items()), tuple(new['policies'].items()))
        moves[key] += 1
    return moves, violations


def extract_archive(archive, into):
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            target = (Path(into) / member.name).resolve()
            if not target.is_relative_to(Path(into).resolve()) or not (member.isfile() or member.isdir()):
                raise ValueError('unsafe archive member: ' + member.name)
        tar.extractall(into)
    if not (Path(into) / 'archeus/core/execution/canonical.py').is_file():
        raise ValueError('baseline archive unavailable/incomplete: ' + str(archive))
    if not (Path(into) / 'tests').is_dir():
        raise ValueError('baseline archive must include old tests: ' + str(archive))
    return str(into)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', nargs=2, action='append', required=True, metavar=('REV', 'ARCHIVE'))
    parser.add_argument('--review', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args(argv[1:])
    if sorted(rev for rev, _ in args.baseline) != sorted(BASELINES):
        parser.error('supply exactly f483f87 and 61dc68f archives')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    roots = {rev: extract_archive(archive, output / rev) for rev, archive in args.baseline}
    sys.path.insert(0, REPO)
    shapes = freeze([REPO, *roots.values()], args.review)
    fixture = output / 'workspace'
    fixture.mkdir(exist_ok=True)
    paths = {name: {'kind': 'file', 'contained': True} for name in
             ('file.txt', 'a.txt', 'two words.txt')}
    paths.update({name: {'kind': 'directory', 'contained': True, 'descendants_contained': True}
                  for name in ('.', 'tests', 'src')})
    for name, evidence in paths.items():
        if evidence['kind'] == 'file':
            (fixture / name).write_text('proof fixture\n', encoding='utf-8')
        else:
            (fixture / name).mkdir(exist_ok=True)
    payload = {'commands': shapes, 'paths': paths, 'policies': policies(),
               'context': {'workdir': str(fixture), 'cwd': str(fixture), 'branch': 'main',
                           'remotes': {'origin': 'github.com'}}}
    frozen = output / 'corpus.json'
    frozen.write_text(json.dumps(payload, sort_keys=True), encoding='utf-8')
    print('frozen-corpus', len(shapes), 'sha256', hashlib.sha256(frozen.read_bytes()).hexdigest(), flush=True)
    results = {}
    for name, root in [*roots.items(), ('candidate', REPO)]:
        target = output / (name + '.json')
        subprocess.run([sys.executable, os.path.abspath(__file__), 'classify', root,
                        str(frozen), str(target), str(int(name == 'candidate'))],
                       check=True, timeout=args.timeout)
        results[name] = json.loads(target.read_text(encoding='utf-8'))
        validate_results(shapes, results[name])
    failed = False
    for rev in BASELINES:
        moves, violations = compare(shapes, results[rev], results['candidate'])
        print(rev, 'held-to-allowed', sum(reason == 'held-to-allowed' for _, reason in violations),
              'violations', len(violations))
        report = {'baseline': rev, 'count': len(shapes),
                  'concrete_moves': [{'command': cmd, 'before': old, 'after': new}
                                     for cmd, old, new in zip(shapes, results[rev], results['candidate'])
                                     if old != new],
                  'moves': [{'classes_before': key[0], 'classes_after': key[1],
                             'unclassified_before': key[2], 'unclassified_after': key[3],
                             'row': key[4], 'held_cap': key[5], 'policies_before': key[6],
                             'policies_after': key[7], 'count': count}
                            for key, count in moves.items()], 'violations': violations}
        (output / (rev + '-moves.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
        for command, reason in violations:
            print(reason, repr(command))
        failed |= bool(violations)
    return int(failed)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'classify':
        sys.exit(classify(sys.argv[2], sys.argv[3], sys.argv[4], bool(int(sys.argv[5]))))
    sys.exit(main(sys.argv))
