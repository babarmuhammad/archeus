"""Action-stage canonicalisation (p11-design-gate §11, D17): a harness's tool
call -> the canonical actions P9 judges, and whether it could be classified.

Pure: `canonicalise(tool, tool_input, ctx)` reads nothing but its arguments.
`ctx` is what the execution manager read before asking (outside any
transaction): `workdir` (the execution's workspace), `branch` (HEAD there, or
None), `remotes` ({remote name: host}).

Never guessed permissive. A command with a shell operator outside quotes, an
interpreter payload, a parse error or an unknown tool is ONE `exec` action with
`unclassified` set, which P9 judges as every class the task holds plus `exec`,
strictest wins (p9-design-gate §6.3). The classifier is a convenience; capability
removal (execution-architecture §2) is the guarantee.
"""

import os
import posixpath
import re
import shlex
from urllib.parse import urlsplit

from ..domain.actions import Action

READ_TOOLS = ('Read', 'Glob', 'Grep', 'LS')
WRITE_TOOLS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')
#: the input field that names the path, per tool (Claude Code's names)
PATH_FIELDS = ('file_path', 'notebook_path', 'path')

#: a shell operator outside quotes makes a command unclassified
_OPERATOR = re.compile(r'[|;&<>`]|\$\(')
_SHELLS = ('sh', 'bash', 'zsh', 'dash', 'fish', 'cmd', 'cmd.exe', 'powershell', 'pwsh',
           'python', 'python3', 'py', 'node', 'perl', 'ruby', 'php')
_NEVER = ('eval', 'exec', 'source', '.', 'sudo', 'su', 'env', 'xargs', 'nohup', 'time',
          'watch', 'timeout', 'nice')

READ_COMMANDS = ('ls', 'cat', 'head', 'tail', 'wc', 'grep', 'rg', 'find', 'pwd', 'echo', 'which',
                 'file', 'stat', 'tree', 'dir', 'type', 'less', 'more', 'diff')
WRITE_COMMANDS = ('rm', 'mv', 'cp', 'mkdir', 'touch', 'rmdir', 'chmod', 'ln')
GIT_READ = ('status', 'log', 'diff', 'show', 'rev-parse', 'ls-files', 'branch', 'remote',
            'describe', 'blame', 'shortlog', 'tag')
GIT_WRITE = ('add', 'checkout', 'switch', 'restore', 'stash', 'merge', 'rebase', 'cherry-pick',
             'mv', 'rm', 'revert', 'init', 'config', 'worktree')
DEPLOY = {('terraform', 'apply'), ('kubectl', 'apply'), ('npm', 'publish'), ('yarn', 'publish'),
          ('pnpm', 'publish'), ('docker', 'push'), ('gh', 'release'), ('helm', 'install'),
          ('helm', 'upgrade'), ('twine', 'upload'), ('cargo', 'publish')}
DESTROY = {('terraform', 'destroy'), ('kubectl', 'delete'), ('helm', 'uninstall'),
           ('docker', 'rm'), ('docker', 'rmi')}
INSTALL = {'pip': ('install',), 'pip3': ('install',), 'npm': ('install', 'i', 'add'),
           'yarn': ('add', 'install'), 'pnpm': ('add', 'install', 'i'), 'cargo': ('install',),
           'go': ('get', 'install'), 'gem': ('install',), 'uv': ('add', 'pip'),
           'brew': ('install',), 'choco': ('install',), 'winget': ('install',)}
REMOTE = ('ssh', 'scp', 'rsync', 'sftp')
PROD = ('--prod', '--production', 'prod', 'production')


def canonicalise(tool, tool_input, ctx):
    """(actions, unclassified) for one tool call."""
    tool_input = tool_input if isinstance(tool_input, dict) else {'command': tool_input}
    if tool in READ_TOOLS or tool in WRITE_TOOLS:
        path = next((tool_input[k] for k in PATH_FIELDS if isinstance(tool_input.get(k), str)),
                    '.')
        rel = workspace_path(path, ctx.get('workdir'))
        cls = 'read' if tool in READ_TOOLS else 'write_repo'
        return [Action(action_class=cls, target=rel, paths=(rel,))], False
    if tool == 'WebFetch':
        url = str(tool_input.get('url') or '')
        return [Action(action_class='web', target=url or 'web', host=host_of(url))], False
    if tool == 'WebSearch':
        return [Action(action_class='web', target='search')], False
    if tool == 'Bash':
        return command(str(tool_input.get('command') or ''), ctx)
    return [_unclassified(str(tool))], True


def workspace_path(path, workdir):
    """*path* relative to the workspace, '/'-separated, or absolute when it is
    not provably inside (P9 treats absolute and `..` as never inside)."""
    if not workdir or str(path).startswith('~'):
        return posixpath.normpath(os.path.expanduser(str(path)).replace('\\', '/'))
    full = os.path.realpath(os.path.join(workdir, os.path.expanduser(str(path))))
    root = os.path.realpath(workdir)
    try:
        rel = os.path.relpath(full, root)
    except ValueError:                  # another drive (Windows)
        return full.replace('\\', '/')
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        return full.replace('\\', '/')
    return rel.replace('\\', '/')


def host_of(url):
    try:
        got = urlsplit(url if '//' in url else '//' + url).hostname
    except ValueError:
        return None
    return got or None


def _unclassified(target, argv=None):
    return Action(action_class='exec', target=target or 'command', argv=argv)


def command(cmd, ctx):
    """A shell command -> (actions, unclassified)."""
    if not cmd.strip():
        return [_unclassified('command')], True
    # expansion happens inside double quotes too, so `$` and a backtick make a
    # command unclassified wherever they appear (a variable can name any path)
    if '$' in cmd or '`' in cmd or _OPERATOR.search(_outside_quotes(cmd)):
        return [_unclassified('shell', (cmd,))], True
    try:
        argv = shlex.split(cmd, posix=True)
    except ValueError:
        return [_unclassified('shell', (cmd,))], True
    if not argv:
        return [_unclassified('command')], True
    prog = os.path.basename(argv[0]).lower()
    if prog.endswith('.exe'):
        prog = prog[:-4]
    args = argv[1:]
    if prog in _NEVER or '=' in argv[0] or (prog in _SHELLS and ('-c' in args or '-e' in args
                                                                 or '/c' in args)):
        return [_unclassified(prog, argv)], True
    if prog == 'base64' and ('-d' in args or '--decode' in args):
        return [_unclassified(prog, argv)], True
    env = 'prod' if any(a.lower() in PROD for a in args) else None
    tv = tuple(argv)
    if prog == 'git':
        return _git(args, tv, ctx), False
    sub = args[0].lower() if args else ''
    if (prog, sub) in DESTROY or (prog == 'rm' and _recursive(args)):
        return [Action(action_class='destructive', target=prog, argv=tv, environment=env,
                       paths=_paths(args, ctx) if prog == 'rm' else None)], False
    if (prog, sub) in DEPLOY or prog == 'vercel':
        return [Action(action_class='deploy', target=prog, argv=tv, environment=env)], False
    if sub in INSTALL.get(prog, ()):
        return [Action(action_class='install', target=prog, argv=tv)], False
    if prog in ('curl', 'wget'):
        url = next((a for a in args if not a.startswith('-') and ('.' in a or '//' in a)), '')
        sends = any(a in ('-d', '-F', '--data', '--data-raw', '--data-binary', '--upload-file',
                          '-T', '--form') or a.startswith('--data') for a in args) or any(
            args[i] in ('-X', '--request') and args[i + 1].upper() != 'GET'
            for i in range(len(args) - 1))
        return [Action(action_class='external_comm' if sends else 'web', target=url or prog,
                       argv=tv, host=host_of(url))], False
    if prog in REMOTE:
        dest = next((a for a in args if not a.startswith('-') and ('@' in a or ':' in a)), '')
        host = dest.split('@')[-1].split(':')[0] or None
        return [Action(action_class='external_comm', target=prog, argv=tv, host=host)], False
    if prog in READ_COMMANDS:
        if prog == 'find' and any(a in ('-exec', '-execdir', '-delete', '-ok') for a in args):
            return [Action(action_class='write_repo', target=prog, argv=tv,
                           paths=_paths(args, ctx))], False
        return [Action(action_class='read', target=prog, argv=tv,
                       paths=_paths(args, ctx))], False
    if prog in WRITE_COMMANDS:
        return [Action(action_class='write_repo', target=prog, argv=tv,
                       paths=_paths(args, ctx))], False
    return [Action(action_class='exec', target=prog, argv=tv, paths=('.',))], False


def _git(args, argv, ctx):
    sub = next((a for a in args if not a.startswith('-')), '')
    rest = args[args.index(sub) + 1:] if sub in args else []
    branch = ctx.get('branch')
    if sub == 'push':
        pos = [a for a in rest if not a.startswith('-')]
        remote = pos[0] if pos else 'origin'
        ref = pos[1] if len(pos) > 1 else branch
        deletes = bool(ref) and ref.startswith(':')          # `:main` deletes main
        if ref and ':' in ref:
            ref = ref.split(':')[-1] or ref.split(':')[0]
        host = (ctx.get('remotes') or {}).get(remote) or host_of(remote)
        push = Action(action_class='git_push', target=remote, argv=argv, branch=ref, host=host)
        if deletes or any(a in ('-f', '--force', '--force-with-lease', '--delete', '-d',
                                '--mirror') or a.startswith('--force') for a in rest):
            return [push, Action(action_class='destructive', target='git push', argv=argv,
                                 branch=ref, host=host)]
        return [push]
    if sub == 'commit':
        return [Action(action_class='git_commit', target=branch or 'HEAD', argv=argv,
                       branch=branch)]
    if (sub == 'reset' and '--hard' in rest) or (sub == 'clean' and any(
            a.startswith('-') and 'f' in a for a in rest)) or (
            sub == 'branch' and any(a in ('-D', '--delete', '-d') for a in rest)):
        return [Action(action_class='destructive', target='git ' + sub, argv=argv,
                       branch=branch)]
    if sub in ('clone', 'fetch', 'pull', 'ls-remote'):
        pos = [a for a in rest if not a.startswith('-')]
        remote = pos[0] if pos else 'origin'
        host = (ctx.get('remotes') or {}).get(remote) or host_of(remote)
        cls = 'web' if sub != 'pull' else 'write_repo'
        return [Action(action_class=cls, target=remote, argv=argv, host=host, branch=branch)]
    if sub in GIT_READ:
        return [Action(action_class='read', target='git ' + sub, argv=argv, branch=branch)]
    if sub in GIT_WRITE:
        return [Action(action_class='write_repo', target='git ' + sub, argv=argv,
                       branch=branch, paths=('.',))]
    return [_unclassified('git', argv)]


def _recursive(args):
    return any(a in ('-r', '-R', '--recursive') or (a.startswith('-') and not a.startswith('--')
                                                    and ('r' in a or 'R' in a)) for a in args)


def _paths(args, ctx):
    got = tuple(workspace_path(a, ctx.get('workdir')) for a in args if not a.startswith('-'))
    return got or ('.',)


def _outside_quotes(cmd):
    """*cmd* with quoted spans removed (an operator inside quotes is text)."""
    out, quote, i = [], None, 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == '\\' and quote == '"' and i + 1 < len(cmd):
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in ('"', "'"):
            quote = c
        elif c == '\\' and i + 1 < len(cmd):
            out.append(' ')
            i += 2
            continue
        else:
            out.append(c)
        i += 1
    if quote:                           # an unterminated quote: not parseable
        return '|'
    return ''.join(out)
