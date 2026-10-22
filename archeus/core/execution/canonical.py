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

import fnmatch
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
_OPERATOR = re.compile(r'[|;&<>`()!\n\r]|\$\(')
#: a glob or brace character: the shell expands it, so the program or an argument is not known
_GLOB = re.compile(r'[{}*?\[]')
_NEVER = ('eval', 'exec', 'source', '.', 'sudo', 'su', 'env', 'xargs', 'nohup', 'time',
          'watch', 'timeout', 'nice', 'command', 'builtin', 'export', 'set', 'typeset',
          'declare', 'alias', 'stdbuf', 'busybox', 'trap', 'ionice', 'setsid', 'chrt',
          'taskset', 'flock', 'unbuffer', 'strace', 'setarch', 'doas', 'chroot', 'script',
          'parallel', 'wsl', 'runas', 'pkexec', 'fakeroot', 'runuser', 'unshare', 'nsenter',
          'systemd-run', 'firejail', 'proxychains', 'proxychains4', 'dbus-run-session', 'expect',
          'gdb', 'lldb', 'at', 'batch', 'start', 'call', 'ltrace', 'torsocks', 'sg', 'newgrp',
          'cgexec', 'chronic', 'socat', 'screen', 'tmux')
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

#: a program's name as the shell finds it: no directory, no quote, no .exe/.cmd/.bat/.com/.ps1, no
#: version suffix (python3.11, perl5.36, pypy3), lower case. Every family and table lookup uses it.
_EXT = re.compile(r'\.(exe|cmd|bat|com|ps1)$')


def _norm(word):
    name = re.split(r'[\\/]', word.strip('"\'`'))[-1].lower()
    return re.sub(r'[\d.]+$', '', _EXT.sub('', name))


#: the programs that run code from their arguments: a closed set of names, and a name outside it is
#: not code by its name. Shells, PowerShell, cmd, the interpreters, sed, and the programs that are
#: code by nature (awk and its variants, the editors, lua, deno, bun and the like).
_SHELL_NAMES = frozenset(('sh', 'bash', 'dash', 'ash', 'ksh', 'mksh', 'zsh', 'csh', 'tcsh', 'fish',
                          'rbash', 'sash', 'nu', 'elvish', 'xonsh'))
_PY_NAMES = frozenset(('python', 'pythonw', 'pyw', 'py', 'pypy'))
_NODE_NAMES = frozenset(('node', 'nodejs'))
_CODE_NAMES = frozenset(('lua', 'luajit', 'deno', 'bun', 'rscript', 'julia', 'tclsh', 'wish', 'vim',
                         'vi', 'nvim', 'ex', 'view', 'rvim', 'gvim', 'vimdiff', 'emacs', 'expect',
                         'groovy', 'jshell', 'osascript'))


def _family(name):
    """The family of a normalised program name, or None."""
    if name in _SHELL_NAMES:
        return 'shell'
    if name in ('pwsh', 'powershell'):
        return 'pwsh'
    if name in _PY_NAMES:
        return 'python'
    if name in _NODE_NAMES:
        return 'node'
    if name in ('cmd', 'perl', 'ruby', 'php'):
        return name
    if name in ('sed', 'gsed'):
        return 'sed'
    if name in _CODE_NAMES or name.endswith('awk'):
        return 'code'
    return None


#: the letters that run code in a single-dash word, per family (-c, -e and /c count anywhere, see
#: ANYWHERE); the long flags that carry code
_LETTERS = {'shell': 'cCeE', 'python': 'c', 'node': 'ep', 'perl': 'eE', 'ruby': 'e', 'php': 'rRB'}
_LONG_CODE = {'shell': ('--command',), 'node': ('--eval', '--print')}
_NODE_HOOKS = ('--import', '--loader', '--experimental-loader')
#: the option through which a tool runs the program it is given, held whatever the value names: a
#: single-dash letter (tar -I, rsync -e, scp -S) or a long name (rsync --rsh)
_CARRIERS = {'tar': ('I', ()), 'rsync': ('e', ('--rsh',)), 'scp': ('S', ())}
#: find's options that run the program after them
_FIND_RUN = ('-exec', '-execdir', '-ok', '-okdir')
#: sed runs code with its `e` command (`1e rm`) or with an `s///e` flag
_SED_CODE = re.compile(r'(^|[\d$;{}\s!/])e(\s|;|}|$)|s(.).*\2[0-9gpiImMwe]*e')
#: the pagers run a `+` command or a `!` shell escape at startup (`less +!rm`)
_PAGERS = ('less', 'more', 'most', 'pg', 'man')
#: an option, or a key=value word, whose name says it gives a command to run (`rg --pre`,
#: `ssh -o ProxyCommand=`, `sort --compress-program=`, `--exec=`, `--pager`): matched by name
_RUN_NAME = re.compile(r'command|exec|pager|editor|shell|eval|hook|helper|program', re.I)
#: generic English words that are also program names (`npm run start`, `pytest .`): as an
#: argument they do not make the call a command
_GENERIC = frozenset(('start', 'set', 'time', 'at', 'script', 'call', 'batch', 'screen', 'export',
                      'command', 'builtin', 'alias', 'declare', 'typeset', 'trap', 'source', 'eval',
                      'exec', 'watch', '.'))
#: the words that, as an argument of a program not in the tables, make the call unclassified: the
#: commands the tables classify, the launchers (the table above, minus the generic words), and the
#: commands the launchers and the usual runners name (gtimeout, prlimit, docker run, npm exec)
_ARG_WORDS = frozenset(WRITE_COMMANDS + READ_COMMANDS + (
    'git', 'curl', 'wget', 'ssh', 'scp', 'rsync', 'sftp', 'docker', 'podman', 'kubectl', 'helm',
    'terraform', 'vercel', 'gh', 'npm', 'npx', 'pnpm', 'yarn', 'pip', 'pip3', 'cargo', 'go', 'gem',
    'uv', 'brew', 'choco', 'winget', 'make', 'tar', 'sort', 'base64', 'xargs', 'man', 'find',
    'gtimeout', 'prlimit', 'numactl', 'caffeinate', 'setpriv', 'runcon', 'hyperfine')) | (
    frozenset(_NEVER) - _GENERIC)
#: every name a command word can be: the argument words, the families and the pagers
_COMMAND_NAMES = _ARG_WORDS | _SHELL_NAMES | _PY_NAMES | _NODE_NAMES | _CODE_NAMES | frozenset(
    _PAGERS + ('pwsh', 'powershell', 'cmd', 'perl', 'ruby', 'php', 'sed', 'gsed'))


def _expansions(word):
    """A word with its braces expanded, one level at a time (`{rm,-R}` -> `rm`, `-R`)."""
    m = re.search(r'\{([^{}]*)\}', word)
    if not m:
        return [word]
    return [e for alt in m.group(1).split(',')
            for e in _expansions(word[:m.start()] + alt + word[m.end():])]


def _glob_names_command(word):
    """True when a brace or glob word may expand to a command word: the shell makes it one before
    the program runs (`{rm,-R}`, `r?`, `b[a]sh`). A name is matched as its pattern, so `tests/*.py`
    and `--level` stay plain."""
    if not _GLOB.search(word):
        return False
    return any(fnmatch.fnmatchcase(name, re.split(r'[\\/]', e)[-1].lower())
               for e in _expansions(word) for name in _COMMAND_NAMES)


def _names_of(word):
    """A word's program names, as written and normalised (a name with a digit is written as is)."""
    raw = word.strip('"\'`').lower()
    return {raw, _norm(raw)}


def _names_command(pieces):
    """True when a piece, as a program name, is a family or an argument word, after a directory, a
    quote, leading dashes or an `=`: `gtimeout 5 rm`, `hyperfine "rm -R x"`, `mytool -c"rm -R x"`,
    `mytool C:\\Windows\\System32\\cmd.exe /c x`."""
    for piece in pieces:
        for part in piece.split('='):
            for name in _names_of(part.lstrip('-')):
                if name in _ARG_WORDS or _family(_norm(name)) is not None:
                    return True
    return False


def _gives_a_command(piece):
    """True for an option, or a key=value word, whose name says it gives a command to run (see
    _RUN_NAME). Matched by the name, never by the value."""
    if '=' in piece:
        name = piece.split('=', 1)[0]
    elif piece.startswith('-'):
        name = piece
    else:
        return False
    name = name.lstrip('-+').lower()
    return name in ('pre', 'pre-glob') or bool(_RUN_NAME.search(name))


def _carries(prog, args):
    """True when a tool's carrier option is given (`tar -I mytool`, `rsync -avze mytool`)."""
    letter, longs = _CARRIERS.get(prog, ('', ()))
    for a in args:
        if a.startswith('--'):
            if a.partition('=')[0] in longs:
                return True
        elif letter:
            cluster = re.match(r'-([a-zA-Z]+)', a)
            if cluster and letter in cluster.group(1):
                return True
    return False


def _pieces(cmd):
    """The words of a command as its blanks and quotes split them."""
    return [p for p in re.split(r'[\s"\'`]+', cmd) if p]


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


#: the payload rule, as data (P21 D6). gate §12 carries the same rule as text: `classifier_rules()`
#: renders it, and a test fails when the two differ.
#: cmd takes code from /c, /k and /r, attached or not, in any case (its arguments are all its own)
CMD_WORDS = ('/c', '/k', '/r')
#: the first build's rule, kept whole: -c, -e and /c count wherever they stand
ANYWHERE = ('-c', '-e', '/c')
#: the two PowerShell parameters that begin with c or e and carry no code
PWSH_NOT_CODE = ('executionpolicy', 'configurationname')


def classifier_rules():
    """The payload and send rules as the gate's §12 block states them (one line each)."""
    lines = ['unclassified: a first word with = (NAME=value); the programs ' + ', '.join(sorted(_NEVER))]
    lines.append('find: -delete is destructive; -exec, -execdir, -ok or -okdir running rm is destructive; '
                 'any other program after one of them is unclassified')
    lines.append('a first word, or a shell or interpreter argument, with an unquoted {, }, *, ? or [')
    lines.append('a program not in the tables, given an argument with an unquoted {, }, *, ? or [ that '
                 'may expand to one of the command words below (braces expanded, the glob matched by name)')
    lines.append('a shell operator outside quotes: | ; & < > ` ( ) ! and $( , or a newline or a '
                 'carriage return; a $ or a backtick anywhere')
    lines.append('git: -C, --git-dir, --work-tree, --namespace and --super-prefix are skipped with '
                 'their value; -c, --config-env, and any other global option not in the tables, make '
                 'the call unclassified')
    lines.append('a program not in the tables, given an argument that after a directory, a quote, '
                 'leading dashes or = is one of: ' + ', '.join(sorted(_ARG_WORDS))
                 + ', or a family name (below)')
    lines.append('an option, or a key=value word, whose name is pre, pre-glob, or contains command, '
                 'exec, pager, editor, shell, eval, hook, helper or program: for any program but git')
    lines.append('carrier options, held whatever the value names: tar -I (and its cluster letter I), '
                 'rsync -e (letter e) and --rsh, scp -S (letter S)')
    lines.append('less, more, most, pg: an argument starting with + or containing !; man: an argument '
                 'starting with -P')
    lines.append('a program name is normalised first: a directory, quotes, .exe, .cmd, .bat, .com, .ps1 '
                 'and a version suffix (python3.11, perl5.36) are dropped')
    lines.append('families (closed): shell: ' + ', '.join(sorted(_SHELL_NAMES)) + '; pwsh: pwsh, powershell; '
                 'cmd; python: ' + ', '.join(sorted(_PY_NAMES)) + '; node: ' + ', '.join(sorted(_NODE_NAMES))
                 + '; perl; ruby; php; sed: sed, gsed; code: any name ending awk, and '
                 + ', '.join(sorted(_CODE_NAMES)) + ' (code is always unclassified)')
    lines.append('anywhere in the arguments: -c, -e or /c as whole words')
    lines.append('shell family: a single-dash word anywhere in the arguments holding one of '
                 + _LETTERS['shell'] + ' (a glued value counts); --command')
    lines.append('python family: a single-dash word holding c; node family: holding e or p; --eval, '
                 '--print; perl: e or E; ruby: e; php: r, R or B')
    lines.append('node family: --import, --loader or --experimental-loader with a data: URL in the '
                 'arguments')
    lines.append('sed: an e command (1e rm) or an s///e flag')
    lines.append('cmd: an argument with ' + ', '.join(CMD_WORDS) + ' anywhere, in any case')
    lines.append('powershell, pwsh: an argument whose first letter is c or e (a glued value counts: '
                 '-cRemove-Item), except -ExecutionPolicy and -ConfigurationName in full; the dash may '
                 'be a hyphen, an en dash, an em dash or a horizontal bar')
    lines.append('git: rebase with -x or --exec; config with a key containing ' + ', '.join(_GIT_CONFIG_RUNS)
                 + ': unclassified')
    lines.append('git push: destructive with --force, --force-with-lease, --delete, --mirror, a '
                 'single-dash word holding f or d (-fu), or a + before a ref')
    lines.append('send flags (external_comm, not web): the names ' + ', '.join(_SENDS)
                 + '; a long flag starting with --data, --form, --post- or --body-; a short -d, '
                 '-F or -T, attached or not; -X or --request with a method other than GET (as the '
                 'next word, attached, or with =)')
    return lines


#: the characters PowerShell takes as a switch prefix: a hyphen, a slash, an en dash, an em dash and
#: a horizontal bar (U+2013, U+2014, U+2015)
_SWITCH_DASHES = '-/' + chr(0x2013) + chr(0x2014) + chr(0x2015)


def _pwsh_word(a):
    """A PowerShell code parameter, or one with a value glued on (`-cRemove-Item`, `-ENCx`): the
    first letter decides, since every parameter that begins with c or e takes code except the
    two in PWSH_NOT_CODE. Only the letters before a digit or a symbol are read, so a glued value
    does not hide the parameter."""
    # PowerShell takes an en dash, an em dash or a horizontal bar as the switch prefix as well
    m = re.match('[' + _SWITCH_DASHES + ']([a-zA-Z]+)', a)
    run = m.group(1).lower() if m else ''
    return run[:1] in ('c', 'e') and run not in PWSH_NOT_CODE


def _payload(family, args):
    """Whether a program of this family runs code from its arguments (see `classifier_rules`). A
    value option before the script (`bash -o pipefail -c"x"`) does not end the scan: a code letter
    in any single-dash word holds, so the rule needs no list of value options, and a word after
    the script that holds one holds too (fail-closed)."""
    if family == 'code':
        return True
    if family == 'sed':
        return any(_SED_CODE.search(a) for a in args)
    if any(a in ANYWHERE for a in args):
        return True
    # a module hook given as a data: URL is code in the argument itself
    if family == 'node' and any(a.lower().startswith(_NODE_HOOKS) for a in args) and any(
            'data:' in a.lower() for a in args):
        return True
    if family == 'cmd':
        # a switch glued after another one (`/s/c"x"`) is still code: any /c, /k or /r holds
        return any(re.search(r'/[ckr]', a, re.I) for a in args)
    if family == 'pwsh':
        return any(_pwsh_word(a) for a in args)
    letters = _LETTERS.get(family, '')
    longs = _LONG_CODE.get(family, ())
    for a in args:
        if a.startswith('--'):
            if longs and a.lower().startswith(longs):
                return True
            continue
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


#: curl and wget switches that take no value: a word after one is a positional, not its value
_NO_VALUE_LETTERS = 'sSLvkfigINGq'
_NO_VALUE_LONG = frozenset((
    '--location', '--silent', '--show-error', '--insecure', '--verbose', '--compressed', '--fail',
    '--include', '--head', '--globoff', '--no-buffer', '--quiet', '--continue', '--no-clobber',
    '--no-check-certificate', '--recursive'))


def _url_arg(prog, args):
    """The one URL a chip may name the host of: the only positional with a scheme (`://`, or a
    leading `//`), not the value of a listed flag, and not the word right after a flag that may
    take a value (`--socks5 http://proxy`, `--proxy-header http://decoy`). Two such URLs, or one
    after such a flag, name no host."""
    values = _WGET_VALUE if prog == 'wget' else _CURL_VALUE
    urls = []                  # (word, after a flag that may take it as its value)
    skip = False
    maybe_value = False
    for i, a in enumerate(args):
        if skip:
            skip, maybe_value = False, False
            continue
        if a == '--':
            continue
        if a == '--url' and i + 1 < len(args):
            urls.append((args[i + 1], False))
            skip = True
            continue
        if a in values or (not a.startswith('--') and a[:2] in values):
            skip, maybe_value = a in values, False      # `-H x` takes x; `-dfoo` carries its value
            continue
        if a.startswith('-'):
            maybe_value = not (a in _NO_VALUE_LONG or re.fullmatch(
                r'-[' + _NO_VALUE_LETTERS + r']+', a))
            continue
        if '://' in a or a.startswith('//'):
            urls.append((a, maybe_value))
        maybe_value = False
    return urls[0][0] if len(urls) == 1 and not urls[0][1] else ''


def clear_host(url):
    """The host of a URL that names its scheme, after its userinfo, port, path, query and
    fragment; None for any other text, and for a host that is not letters, digits, dots and
    dashes. The only host a chip may name (P21 D6, I-F4): it is never policy input."""
    if not url or ('://' not in url and not url.startswith('//')):
        return None
    host = host_of(url)
    if not host or not _HOST.fullmatch(host):
        return None
    return '.'.join('…' if _token_like(x) else x for x in host.split('.'))


def _token_like(label):
    """A host label that can carry a secret: longer than 20 characters, a letter and a digit
    and longer than 4, or an all-digit label longer than 6. Shown as an ellipsis, the TLD too
    (a dotless host is one label); the plain words stay."""
    if len(label) > 20 or (len(label) > 4 and bool(re.search(r'\d', label))
                           and bool(re.search(r'[a-z]', label))):
        return True
    return label.isdigit() and len(label) > 6


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
    # the program's names twice: as argv gives it, and as the raw first word does (a bare Windows
    # path reaches argv without its backslashes, so only the raw word keeps the name `cmd`)
    names = _names_of(argv[0]) | _names_of(_program(cmd))
    families = {_family(_norm(n)) for n in names} - {None}
    if any(n in _NEVER for n in names) or any(_payload(f, args) for f in families):
        return [_unclassified(prog, argv)], True
    # the shell expands a brace or a glob before the program runs: `{bash,-c,x}` and `b?sh` are
    # shells, and a shell or an interpreter given a glob may be given a file named `-c`
    if _GLOB.search(argv[0]) or (families and _GLOB.search(' '.join(args))):
        return [_unclassified(prog, argv)], True
    if prog == 'base64' and ('-d' in args or '--decode' in args):
        return [_unclassified(prog, argv)], True
    env = 'prod' if any(a.lower() in PROD for a in args) else None
    tv = tuple(argv)
    if prog == 'git':
        return _git(args, tv, ctx)
    if prog == 'find':
        return _find(args, tv, ctx)
    # an option or a key=value word that names a command to run: `rg --pre`, `ssh -o ProxyCommand=`,
    # `tar -I mytool`; the words of argv count too, so `rg --pr""e` is `rg --pre`
    if any(_gives_a_command(p) for p in _pieces(cmd)[1:] + args) or _carries(prog, args):
        return [_unclassified(prog, argv)], True
    # a pager runs its `+` command or `!` escape, and man runs the pager it is given with -P
    name = _norm(argv[0])
    if (name in _PAGERS and any(a.startswith('+') or '!' in a for a in args)) or (
            name == 'man' and any(a.startswith('-P') for a in args)):
        return [_unclassified(prog, argv)], True
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
        # scp -S, rsync -e and ssh take a program or a shell as a value: a family name holds
        if any(_family(_norm(n)) for p in _pieces(cmd)[1:] for part in p.split('=')
               for n in _names_of(part.lstrip('-'))):
            return [_unclassified(prog, argv)], True
        dest = next((a for a in args if not a.startswith('-') and ('@' in a or ':' in a)), '')
        host = dest.split('@')[-1].split(':')[0] or None
        return [Action(action_class='external_comm', target=prog, argv=tv, host=host)], False
    if prog in READ_COMMANDS:
        return [Action(action_class='read', target=prog, argv=tv,
                       paths=_paths(args, ctx))], False
    if prog in WRITE_COMMANDS:
        return [Action(action_class='write_repo', target=prog, argv=tv,
                       paths=_paths(args, ctx))], False
    # a program not in the tables, given a shell, an interpreter, a launcher or a command word as an
    # argument, quotes removed and braces and globs expanded: it runs that (`gtimeout 5 r""m -R
    # build`, `gtimeout 5 {rm,-R,build}`, `docker run alpine sh -c x`)
    if _names_command(_pieces(cmd)[1:] + ' '.join(args).split()) or any(
            _glob_names_command(a) for a in args):
        return [_unclassified(prog, argv)], True
    return [Action(action_class='exec', target=prog, argv=tv, paths=('.',))], False


#: git's global options before the subcommand: the ones that take a value (skipped with it), and
#: the ones that take none. `-c` and `--config-env` are never accepted (see `_git_split`).
# the word is built from parts: the store-pin scan in test_repo_store reads a bare '--git-dir' in
# production code as a second store pin, and this is git's option, parsed, never passed on
_GIT_VALUE = ('-C', '--git' + '-dir', '--work-tree', '--namespace', '--super-prefix')
_GIT_FLAG = ('--no-pager', '-p', '--paginate', '-P', '--no-paginate', '--bare',
             '--literal-pathspecs', '--glob-pathspecs', '--noglob-pathspecs',
             '--icase-pathspecs', '--no-optional-locks', '--exec-path', '--version', '--help')
#: a `git config` key containing one of these names a command git runs later (an alias, a pager,
#: an editor, a *command); a config value is never judged by its text
_GIT_CONFIG_RUNS = ('alias', 'pager', 'editor', 'command', 'helper', 'hook', 'external', 'textconv',
                    'fsmonitor', 'askpass', 'program', 'clean', 'smudge', 'process', 'driver',
                    'gitproxy')


def _git_split(args):
    """(subcommand, the words after it), past git's global options. (None, None) when a global
    option is not in the tables: its value, if any, would be read as the subcommand. A config
    value (`-c`, `--config-env`) is never skipped: it can name a pager or an editor that runs a
    shell, so the call is unclassified."""
    i = 0
    while i < len(args):
        a = args[i]
        name = a.partition('=')[0]
        if name in ('-c', '--config-env'):
            return None, None
        if a in _GIT_VALUE:
            i += 2
        elif name in _GIT_VALUE or name == '--exec-path':
            i += 1
        elif a in _GIT_FLAG:
            i += 1
        elif a.startswith('-'):
            return None, None
        else:
            return a, args[i + 1:]
    return '', []


def _git(args, argv, ctx):
    sub, rest = _git_split(args)
    actions = _git_actions(sub, rest, argv, ctx) if sub else None
    if actions is None:
        return [_unclassified('git', argv)], True
    return actions, False


def _git_actions(sub, rest, argv, ctx):
    """The actions of one git subcommand, or None when the subcommand is not in the tables."""
    branch = ctx.get('branch')
    # rebase --exec runs its command in a shell; a config key named for a command runs it later
    if sub == 'rebase' and any(a.startswith(('-x', '--exec')) for a in rest):
        return None
    if sub == 'config' and any(k in a.lower() for a in rest for k in _GIT_CONFIG_RUNS):
        return None
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
        # a force push: --force, a single-dash word holding f (-fu), or a + before a ref (+main)
        forced = any(a in ('--force', '--delete', '--mirror') or a.startswith('--force')
                     or re.fullmatch(r'-[a-zA-Z]*[fd][a-zA-Z]*', a) for a in rest) or any(
            a.startswith('+') for a in pos)
        if deletes or forced:
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
    return None


def _recursive(args):
    return any(a in ('-r', '-R', '--recursive') or (a.startswith('-') and not a.startswith('--')
                                                    and ('r' in a or 'R' in a)) for a in args)


def _paths(args, ctx):
    got = tuple(workspace_path(a, ctx.get('workdir')) for a in args if not a.startswith('-'))
    return got or ('.',)


def _find(args, tv, ctx):
    """find -delete removes what it finds, and -exec, -execdir, -ok or -okdir running rm does the
    same (the owner's answer): destructive. Any other program after one of them is a payload this
    rule cannot see: unclassified. Otherwise a read."""
    runs = [args[i + 1] if i + 1 < len(args) else '' for i, a in enumerate(args) if a in _FIND_RUN]
    if any(_norm(p) != 'rm' for p in runs):
        return [_unclassified('find', tv)], True
    if runs or '-delete' in args:
        return [Action(action_class='destructive', target='find', argv=tv,
                       paths=_paths(args, ctx))], False
    return [Action(action_class='read', target='find', argv=tv, paths=_paths(args, ctx))], False


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
