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
#: the input field that names the path, per tool (Claude Code's names); a tool reads
#: only its own, never another tool's field that happens to be present
PATH_FIELD = {'Read': 'file_path', 'Write': 'file_path', 'Edit': 'file_path',
              'MultiEdit': 'file_path', 'NotebookEdit': 'notebook_path',
              'Glob': 'path', 'Grep': 'path', 'LS': 'path'}
#: the tools whose path is optional (the workspace when absent)
OPTIONAL_PATH = ('Glob', 'Grep')

#: a shell operator outside quotes makes a command unclassified
_OPERATOR = re.compile(r'[|;&<>`]|\$\(')
_SHELLS = ('sh', 'bash', 'zsh', 'dash', 'fish', 'cmd', 'cmd.exe', 'powershell', 'pwsh',
           'python', 'python3', 'py', 'node', 'perl', 'ruby', 'php')
_NEVER = ('eval', 'exec', 'source', '.', 'sudo', 'su', 'env', 'xargs', 'nohup', 'time',
          'watch', 'timeout', 'nice', 'command', 'builtin', 'export', 'set', 'typeset',
          'declare', 'alias', 'stdbuf', 'busybox', 'trap', 'ionice', 'setsid', 'chrt',
          'taskset', 'flock', 'unbuffer', 'strace')

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
    try:
        return _canonicalise(tool, tool_input, ctx)
    except (OSError, ValueError):      # a path the OS refuses to resolve (NUL, too long)
        return [_unclassified(str(tool))], True


def _canonicalise(tool, tool_input, ctx):
    tool_input = tool_input if isinstance(tool_input, dict) else {'command': tool_input}
    # an input whose required field is missing, empty or not a string is one it
    # cannot parse: never a write on '.', a fetch with no host or str() of a list
    if tool in READ_TOOLS or tool in WRITE_TOOLS:
        given = [tool_input[k] for k in (PATH_FIELD[tool],) if k in tool_input]
        if given and not _text(given[0]) or not given and tool not in OPTIONAL_PATH:
            return [_unclassified(str(tool))], True
        rel = workspace_path(given[0] if given else '.', ctx.get('workdir'))
        cls = 'read' if tool in READ_TOOLS else 'write_repo'
        return [Action(action_class=cls, target=rel, paths=(rel,))], False
    if tool == 'WebFetch':
        url = tool_input.get('url')
        host = host_of(url) if _text(url) else None
        if host is None:
            return [_unclassified(str(tool))], True
        return [Action(action_class='web', target=url, host=host, chip_host=clear_host(url))], False
    if tool == 'WebSearch':
        return [Action(action_class='web', target='search')], False
    if tool == 'Bash':
        cmd = tool_input.get('command')
        return command(cmd, ctx) if _text(cmd) else ([_unclassified(str(tool))], True)
    return [_unclassified(str(tool))], True


def _text(v):
    return isinstance(v, str) and bool(v)


def _units(s):
    """Length as the OS limits it: UTF-16 units on Windows, bytes elsewhere."""
    return len(s.encode('utf-16-le')) // 2 if os.name == 'nt' else len(os.fsencode(s))


def openable(path):
    """*path* as a str, or ValueError when no OS could open it: a NUL, more than
    32767 units in all (Windows' ceiling, even \\\\?\\-prefixed) or a component of
    more than 255 (NTFS and the common POSIX filesystems). Checked before any
    resolution, because realpath stopped raising on these (CPython gh-106242)
    and returns them as if they were ordinary paths."""
    s = str(path)
    if '\x00' in s or _units(s) > 32767 or any(
            _units(c) > 255 for c in re.split(r'[\\/]' if os.name == 'nt' else '/', s)):
        raise ValueError('a path no OS can open')
    return s


def workspace_path(path, workdir):
    """*path* relative to the workspace, '/'-separated, or absolute when it is
    not provably inside (P9 treats absolute and `..` as never inside). A path
    no OS can open raises ValueError: canonicalise makes it one unclassified exec."""
    given = os.path.expanduser(str(path))
    if not workdir or str(path).startswith('~'):
        return posixpath.normpath(openable(given).replace('\\', '/'))
    full = os.path.realpath(openable(os.path.join(workdir, given)))
    root = os.path.realpath(openable(workdir))
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


#: the names a shell or interpreter runs code from (its payload flags, below)
_CURL_VALUE = frozenset((
    '-d', '--data', '--data-raw', '--data-binary', '--data-urlencode', '--data-ascii', '-H',
    '--header', '-u', '--user', '-F', '--form', '--form-string', '--oauth2-bearer', '-X',
    '--request', '-o', '--output', '-A', '--user-agent', '-b', '--cookie', '-c', '--cookie-jar',
    '-e', '--referer', '-m', '--max-time', '-T', '--upload-file', '-w', '--write-out', '-x',
    '--proxy', '--proxy-user', '-K', '--config', '-E', '--cert', '--key', '--cacert', '-r',
    '--range', '-C', '--continue-at', '--connect-timeout', '--resolve', '--json', '-Y',
    '--speed-limit', '-y', '--speed-time', '--limit-rate', '--retry', '--retry-delay'))
_WGET_VALUE = frozenset((
    '--header', '--post-data', '--post-file', '--body-data', '--body-file', '--password',
    '--http-password', '--user', '--http-user', '--proxy-user', '--proxy-password', '-U',
    '--user-agent', '--referer', '-e', '--execute', '--load-cookies', '--save-cookies', '-o',
    '-O', '--output-file', '--output-document', '-P', '--directory-prefix', '-t', '--tries',
    '-T', '--timeout', '-w', '--wait', '--method', '--ca-certificate', '--certificate',
    '--private-key', '-B', '--base', '-i', '--input-file', '-A', '--accept', '-R', '--reject'))
#: the flags that send a body, in the spelling the first build knew; `_sends` adds the rest
_SENDS = ('-d', '-F', '-T', '--data', '--data-raw', '--data-binary', '--data-urlencode',
          '--data-ascii', '--upload-file', '--form', '--form-string', '--json', '--post-data',
          '--post-file', '--body-data', '--body-file')
_HOST = re.compile(r'[a-z0-9.-]{1,253}')


def _program(cmd):
    """The program's name as the shell reads its first word: a quoted or a bare Windows path
    keeps its basename (shlex has already dropped the backslashes of a bare one), lowercased,
    .exe dropped. Only the payload and wrapper checks read it; the rest keep the old name."""
    m = re.match(r'\s*("[^"]*"|\'[^\']*\'|\S+)', cmd)
    word = m.group(1).strip('"\'') if m else ''
    name = re.split(r'[\\/]', word)[-1].lower()
    return name[:-4] if name.endswith('.exe') else name


#: the payload rule, as data (P21 D6, the owner's fail-closed unclassified set). gate §12 carries
#: the same rule as text: `classifier_rules()` renders it, and a test fails when the two differ.
SHELL_TOOLS = ('sh', 'bash', 'zsh', 'dash', 'fish')
#: a shell runs code from a single-dash cluster holding one of these letters (-c, -lc, -e, -C)
SHELL_LETTERS = 'cCeE'
#: an interpreter runs code from the same kind of cluster, its own letters (python -c; node -e -p;
#: perl -e -E; ruby -e; php -r -R -B). -r for node and -E or -P for python are not code: exempt.
INTERP_LETTERS = {'python': 'c', 'python3': 'c', 'py': 'c', 'node': 'ep', 'perl': 'eE',
                  'ruby': 'e', 'php': 'rRB'}
#: the long flags that carry code (a prefix match: --eval=x counts)
LONG_CODE = {'sh': ('--command',), 'bash': ('--command',), 'zsh': ('--command',),
             'dash': ('--command',), 'fish': ('--command',), 'node': ('--eval', '--print')}
#: cmd takes code from /c, /k and /r, attached or not, in any case (its arguments are all its own)
CMD_WORDS = ('/c', '/k', '/r')
#: PowerShell takes code from -Command and -EncodedCommand, by any prefix of the name
PWSH_WORDS = ('command', 'encodedcommand')
#: the first build's rule, kept whole: -c, -e and /c count wherever they stand
ANYWHERE = ('-c', '-e', '/c')


def classifier_rules():
    """The payload and send rules as the gate's §12 block states them (one line each)."""
    lines = ['unclassified: a first word with = (NAME=value); the programs ' + ', '.join(sorted(_NEVER))]
    lines.append('anywhere in the arguments: -c, -e or /c as whole words')
    lines.append('shells (' + ', '.join(SHELL_TOOLS) + '): a single-dash flag before the first '
                 'positional holding one of ' + SHELL_LETTERS + '; --command')
    for name in sorted(INTERP_LETTERS):
        longs = LONG_CODE.get(name, ())
        lines.append(name + ': a single-dash flag before the first positional holding one of '
                     + INTERP_LETTERS[name] + ((('; ' + ', '.join(longs)) if longs else '')))
    lines.append('cmd: an argument starting with ' + ', '.join(CMD_WORDS) + ' in any case')
    lines.append('powershell, pwsh: an argument whose leading letters are a prefix of '
                 + ' or '.join(PWSH_WORDS) + ', or ec, or start with com or enc (a glued value '
                 'counts: -ENCx)')
    lines.append('send flags (external_comm, not web): the names ' + ', '.join(_SENDS)
                 + '; a long flag starting with --data, --form, --post- or --body-; a short -d, '
                 '-F or -T, attached or not; -X or --request with a method other than GET (as the '
                 'next word, attached, or with =)')
    return lines


def _pwsh_word(a):
    """-c, -co, -e, -ec, -enc, -Command, -EncodedCommand, and the same with a value glued on
    (`-ENC"x"` arrives as `-ENCx`): the leading letters decide, -ExecutionPolicy does not."""
    m = re.match(r'[-/]([a-zA-Z]+)', a)
    run = m.group(1).lower() if m else ''
    return run in ('c', 'e', 'ec') or run[:3] in ('com', 'enc') or any(
        w.startswith(run) for w in PWSH_WORDS if run)


def _payload(prog, args):
    """A shell or interpreter, or cmd or PowerShell, runs code from its arguments (see
    `classifier_rules`). A flag before a shell's or an interpreter's first positional is its
    own; the first positional is the script (or the -m module), and what follows it is the
    script's."""
    if any(a in ANYWHERE for a in args):
        return True
    if prog == 'cmd':
        return any(a[:2].lower() in CMD_WORDS for a in args)
    if prog in ('powershell', 'pwsh'):
        return any(_pwsh_word(a) for a in args)
    letters = SHELL_LETTERS if prog in SHELL_TOOLS else INTERP_LETTERS.get(prog, '')
    longs = LONG_CODE.get(prog, ())
    if not letters and not longs:
        return False
    for a in args:
        if a.startswith('--'):
            if longs and a.lower().startswith(longs):
                return True
            continue
        if not a.startswith('-'):
            return False
        m = re.match(r'-([a-zA-Z]+)', a)
        if m and letters and any(ch in letters for ch in m.group(1)):
            return True
    return False


def _sends(args):
    """A call that sends a body, in every spelling: long, with `=`, attached, or -X with a method
    other than GET. A superset of the first build's list, so no call becomes a read of a page."""
    for i, a in enumerate(args):
        name, eq, val = a.partition('=')
        if name in _SENDS or name.startswith(('--data', '--form', '--post-', '--body-')):
            return True
        if name in ('-X', '--request'):
            method = val if eq else (args[i + 1] if i + 1 < len(args) else 'GET')
            if method.upper() != 'GET':
                return True
        elif a.startswith('-X') and not a.startswith('--') and len(a) > 2 and a[2:].upper() != 'GET':
            return True
        elif a[:2] in ('-d', '-F', '-T') and not a.startswith('--'):
            return True
    return False


def _url_arg(prog, args):
    """The first positional that names its scheme (`://`, or a leading `//`) and is not the
    value of a flag: the one URL a chip may name the host of."""
    values = _WGET_VALUE if prog == 'wget' else _CURL_VALUE
    skip = False
    found = []
    for i, a in enumerate(args):
        if skip:
            skip = False
        elif a == '--url' and i + 1 < len(args):
            found.append(args[i + 1])
        elif a in values:
            skip = True
        elif a.startswith('-'):
            continue
        elif '://' in a or a.startswith('//'):
            found.append(a)
    # two URLs, or one URL and a decoy in a flag this list does not know: no host is named
    return found[0] if len(found) == 1 else ''


def clear_host(url):
    """The host of a URL that names its scheme, after its userinfo, port, path, query and
    fragment; None for any other text, and for a host that is not letters, digits, dots and
    dashes. The only host a chip may name (P21 D6, I-F4): it is never policy input."""
    if not url or ('://' not in url and not url.startswith('//')):
        return None
    host = host_of(url)
    if not host or not _HOST.fullmatch(host):
        return None
    labels = host.split('.')
    return '.'.join(['…' if _token_like(x) else x for x in labels[:-1]] + labels[-1:])


def _token_like(label):
    """A host label that can carry a secret: longer than 20 characters, or with a letter and
    a digit and longer than 4. Shown as an ellipsis; the TLD and the plain words stay."""
    return len(label) > 20 or (len(label) > 4 and bool(re.search(r'\d', label))
                               and bool(re.search(r'[a-z]', label)))


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
    # NAME=value cmd: the name is no program, and its value may be a secret (never a target)
    if '=' in argv[0]:
        return [_unclassified('command', argv)], True
    shell = _program(cmd)
    if prog in _NEVER or shell in _NEVER or (prog in _SHELLS and _payload(prog, args)) or (
            shell in _SHELLS and _payload(shell, args)):
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
        # the policy host is the first build's pick (a dotted word counts), so no decision moves
        # with the chip's host; the chip names only a URL that says its scheme
        url = next((a for a in args if not a.startswith('-') and ('.' in a or '//' in a)), '')
        return [Action(action_class='external_comm' if _sends(args) else 'web', target=url or prog,
                       argv=tv, host=host_of(url), chip_host=clear_host(_url_arg(prog, args)))], False
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
        push = Action(action_class='git_push', target=remote, argv=argv, branch=ref, host=host,
                      chip_host=clear_host(remote))
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
        return [Action(action_class=cls, target=remote, argv=argv, host=host, branch=branch,
                       chip_host=clear_host(remote))]
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
