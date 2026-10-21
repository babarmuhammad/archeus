"""P21 slice E, gate §12: how the Bash classifier moved against a baseline revision.

Generates a shape set (programs x pre-options x payload forms x tails, plus the curl and wget
send forms and a few plain commands), classifies every shape at the baseline revision (extracted
with git archive) and at the working tree, and prints the moves per (before, after, program).
A held-to-allowed move is printed as a violation and makes the exit code 1.

    py tools/p21_classifier_moves.py [baseline-rev]        (default f483f87)
"""
import collections
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile

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


def classify(root, shapes_path, out_path):
    sys.path.insert(0, root)
    from archeus.core.execution import canonical
    ctx = {'workdir': root, 'branch': 'main', 'remotes': {'origin': 'github.com'}}
    with open(shapes_path, encoding='utf-8') as f:
        shapes = json.load(f)
    out = []
    for cmd in shapes:
        try:
            acts, unc = canonical.canonicalise('Bash', cmd, ctx)
            out.append([bool(unc), [a.action_class for a in acts]])
        except Exception as e:                       # a shape that raises is recorded, not hidden
            out.append(['error', repr(e)])
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f)


def extract(rev, into):
    data = subprocess.run(['git', '-C', REPO, 'archive', rev, 'archeus'], check=True,
                          capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(into)
    return into


def label(res):
    if res[0] == 'error':
        return 'error'
    unclassified = 'U ' if res[0] else ''
    return unclassified + ('/'.join(res[1]) or 'none')


def program(cmd):
    words = cmd.split()
    head = words[0] if words else ''
    return head.replace('\\', '/').rsplit('/', 1)[-1].lower()


def main(argv):
    rev = argv[1] if len(argv) > 1 else 'f483f87'
    work = tempfile.mkdtemp(prefix='p21moves')
    shapes = corpus()
    shapes_path = os.path.join(work, 'shapes.json')
    with open(shapes_path, 'w', encoding='utf-8') as f:
        json.dump(shapes, f)
    base_root = extract(rev, os.path.join(work, 'base'))
    results = {}
    for name, root in (('base', base_root), ('new', REPO)):
        out = os.path.join(work, name + '.json')
        subprocess.run([sys.executable, os.path.abspath(__file__), 'classify', root, shapes_path, out],
                       check=True)
        with open(out, encoding='utf-8') as f:
            results[name] = json.load(f)
    moves = collections.Counter()
    violations = 0
    for cmd, b, n in zip(shapes, results['base'], results['new']):
        if label(b) == label(n):
            continue
        if b[0] is True and n[0] is False:
            violations += 1
        moves[(label(b), label(n), program(cmd))] += 1
    print('shapes', len(shapes), 'moved', sum(moves.values()), 'held-to-allowed', violations)
    for (before, after, prog), count in sorted(moves.items(), key=lambda kv: (-kv[1], kv[0])):
        print('%6d  %-22s -> %-22s %s' % (count, before, after, prog))
    return 1 if violations else 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'classify':
        classify(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        sys.exit(main(sys.argv))
