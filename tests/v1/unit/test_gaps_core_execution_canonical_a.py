"""Gap tests for the command canonicaliser, `canonical.py` lines 1-470 (T-702).

Every test names, in its docstring, the branch of
``archeus/core/execution/canonical.py`` it exists to protect, and each one fails
when that branch is removed or inverted. The existing suite
(``test_execution_units.py``, ``test_command_allowlist_hook.py``) exercises the
happy table lookups and the ``isinstance(result, Held)`` shape hundreds of times,
so a canonicaliser that swallowed every OS error as a readable path, that handed
the shell's allowlist profile to a non-Bash executor, that answered a failed
``relpath`` with a workspace-relative name, that labelled an input the allowlist
never parsed, that dropped the sub-command from a labelled target, that measured
a Windows path in the wrong units, or that let a tool's carrier option through
unheld would have passed unchanged. Those are the branches covered here, refusals
first, then the limits, then the error paths.

Style follows ``test_execution_units.py`` and ``test_command_allowlist_hook.py``.
Nothing here runs a process, opens a file or touches the network: the OS is
reached only through the seams those files already patch (``os.path.realpath``,
``os.path.expanduser``, ``os.path.relpath``, ``os.name``), every path is a
literal or ``os.path.abspath`` of a name that does not exist, and no assertion
turns on the host platform - the Windows-only arms are reached by faking
``os.name``, so the expected answer is the same on every OS.
"""

import errno
import os
import posixpath

import pytest

from archeus.core.execution import canonical as C
from archeus.core.execution.command_allowlist import MAX_INPUT_LENGTH, Allowed, Held
from v1.unit.test_command_allowlist import CONTEXT

WD = os.path.abspath('workspace-root')
CTX = {'workdir': WD, 'branch': 'archeus/m/t', 'remotes': {'origin': 'github.com'}}
REFUSED = 'REFUSED'


def explode(*args, **kwargs):
    raise AssertionError('this path must not be resolved')


def outcome(path):
    """What `openable` makes of *path*: the string, or REFUSED."""
    try:
        return C.openable(path)
    except ValueError:
        return REFUSED


def absolute(path):
    """The realpath of *path*, '/'-separated: what P9 reads as never-inside."""
    return os.path.realpath(path).replace('\\', '/')


# ── refusals: the paths that must never come back readable ──────────────────

@pytest.mark.parametrize('tool,tool_input', (
    ('Read', {'file_path': 'a.py'}),
    ('Write', {'file_path': 'a.py', 'content': 'x'}),
    ('LS', {'path': 'src'}),
    ('Bash', {'command': 'cat a.py'}),
))
def test_an_os_that_refuses_to_resolve_a_path_denies_the_call(monkeypatch, tool, tool_input):
    """canonical.py:350 (`except (OSError, ValueError)`). `realpath` stopped
    raising on unreadable paths, so the OS seam itself is what fails here: an
    OSError must become one unclassified exec and never the read the tool
    asked for. Removing the handler, or narrowing it to ValueError, turns all
    four rows into an escaping OSError; widening it past the two types is what
    the partner test below denies."""
    def refuse(*args, **kwargs):
        raise OSError(errno.EACCES, 'the OS refuses to resolve this')
    monkeypatch.setattr(os.path, 'realpath', refuse)
    actions, unclassified = C.canonicalise(tool, tool_input, CTX)
    assert unclassified is True and len(actions) == 1
    action = actions[0]
    assert action.action_class == 'exec' and action.target == tool
    assert action.argv is None and action.paths is None and action.host is None


@pytest.mark.parametrize('error', (RuntimeError, TypeError, KeyError))
def test_any_other_error_from_the_canonicaliser_still_escapes(monkeypatch, error):
    """canonical.py:350 (`except (OSError, ValueError)`): only the two
    path-resolution errors are answered with a denial. A bare `except`, or one
    widened to `Exception`, turns a real bug into an unclassified exec that
    simply looks like a conservative answer."""
    def refuse(*args, **kwargs):
        raise error('a bug, not a path the OS refuses')
    monkeypatch.setattr(os.path, 'realpath', refuse)
    with pytest.raises(error):
        C.canonicalise('Read', {'file_path': 'a.py'}, CTX)


def test_a_home_path_is_never_made_workspace_relative(monkeypatch):
    """canonical.py:406-407 (`if not workdir or str(path).startswith('~')`).
    The guard is read off the *written* path, so a `~` that expands into the
    workspace - the usual case for a home inside the checkout - is still never
    joined to it and never comes back as a workspace-relative name P9 would
    allow. Drop the `startswith('~')` disjunct and `~/x` becomes `x`."""
    monkeypatch.setattr(os.path, 'expanduser',
                        lambda p: WD + p[1:] if p.startswith('~') else p)
    assert C.workspace_path('x', WD) == 'x'                     # control: inside
    got = C.workspace_path('~/x', WD)
    assert got == posixpath.normpath(WD.replace('\\', '/') + '/x')
    assert got != 'x' and '~' not in got and not got.startswith('..')


def test_a_path_without_a_workspace_is_normalised_without_touching_the_os(monkeypatch):
    """canonical.py:406-407 (`not workdir`): with no workspace there is nothing
    to be inside of, so the path is normalised as written and never resolved -
    `realpath` here would be a call the caller cannot reason about (and, with a
    Windows drive letter in it, one that answers differently)."""
    monkeypatch.setattr(os.path, 'realpath', explode)
    assert C.workspace_path('sub/../x', '') == 'x'
    assert C.workspace_path('a\\b', '') == 'a/b'
    assert C.workspace_path('a//b/./c', None) == 'a/b/c'


def test_a_relpath_failure_is_never_answered_with_a_relative_path(monkeypatch):
    """canonical.py:411-413 (`except ValueError: # another drive`). Windows
    raises here for two paths on different drives; the answer must be the
    absolute path, because a bare or '.'-relative name is what P9 reads as
    *inside* the workspace. Removing the handler lets the ValueError escape
    (the caller sees a crash mid-approval); returning `rel` instead answers
    with a path that reads as inside."""
    assert C.workspace_path('sub/x', WD) == 'sub/x'             # control: inside
    expected = absolute(os.path.join(WD, 'sub/x'))

    def refuse(*args, **kwargs):
        raise ValueError('paths are on different drives')
    monkeypatch.setattr(os.path, 'relpath', refuse)
    got = C.workspace_path('sub/x', WD)
    assert got == expected and got != 'sub/x' and not got.startswith('sub')


@pytest.mark.parametrize('given', ('..', '../x', '../../x', 'a/../../x'))
def test_a_path_that_resolves_outside_the_workspace_is_returned_absolute(given):
    """canonical.py:414-415 (`rel == os.pardir or rel.startswith(pardir +
    os.sep)`). The exact-parent row is the one the `startswith` arm cannot
    catch on its own: `..` alone has no separator after it. Answering `..`
    hands P9 a name that is not absolute, and P9 only refuses absolute and
    `..`-prefixed paths by their shape."""
    got = C.workspace_path(given, WD)
    assert got == absolute(os.path.join(WD, given))
    assert got != given and not got.startswith('..')


def test_a_relative_path_that_comes_back_absolute_is_not_trusted(monkeypatch):
    """canonical.py:414 (`or os.path.isabs(rel)`): `relpath` can hand back an
    absolute path (a Windows path that leaves the drive), and the third disjunct
    is what stops it from being returned as the workspace-relative name P9 would
    then read as inside."""
    monkeypatch.setattr(os.path, 'relpath', lambda *a, **k: os.path.join(WD, 'outside'))
    got = C.workspace_path('sub/x', WD)
    assert got == absolute(os.path.join(WD, 'sub/x')) != os.path.join(WD, 'outside').replace('\\', '/')


def test_an_allowed_row_with_no_paths_still_carries_the_request_directory():
    """canonical.py:338 (`or (workspace_path(cwd, ctx.get('workdir')),)`). A row
    whose operands are none classifies `pwd`-like commands with an empty path
    list; an action with *no* paths gives P9's path rules nothing to check, so
    the request directory itself stands in. Change the fallback to `()` and the
    command is approved with nothing to confine."""
    (actions, unclassified), result = C.canonicalise_hook('Bash', 'pwd', CTX, CONTEXT)
    assert isinstance(result, Allowed) and not unclassified
    action = actions[0]
    assert action.paths == ('.',) and action.argv == ('pwd',) and action.target == 'pwd'


@pytest.mark.parametrize('command', (
    'rm ' + 'a' * (MAX_INPUT_LENGTH + 1),
    'rm ' + 'a' * (MAX_INPUT_LENGTH * 2),
), ids=('one_over', 'double'))
def test_an_input_the_allowlist_never_parsed_never_gets_a_policy_label(command):
    """canonical.py:323 (`tool == 'Bash' and isinstance(cmd, str) and
    len(cmd) <= command_allowlist.MAX_INPUT_LENGTH`). Past the classifier's own
    ceiling `_scan` has not read the input, so the label lookup must be skipped:
    a `destructive` label off a truncated scan is a *weaker* answer than
    unclassified (which is judged as every class at once). The partner case
    below keeps the label for an input of exactly the scanned size."""
    (actions, unclassified), result = C.canonicalise_hook('Bash', command, CTX)
    assert isinstance(result, Held) and unclassified is True
    action = actions[0]
    assert action.action_class == 'exec' and action.target == 'command'
    assert action.argv[0] == 'str' and action.argv[-1] == 'Bash'


def test_a_scanned_input_still_gets_its_label_and_its_subcommand_target():
    """canonical.py:323 and canonical.py:331 (`target = program + ' ' + sub`).
    One character under the ceiling the same `rm ...` is labelled, and a
    labelled action's target keeps the sub-command: an approval for `git push`
    must not be spendable on `git`, or on a different sub-command of the same
    program. Dropping the length guard holds this input unclassified too;
    dropping the sub-command from the target retargets all three rows."""
    under = 'rm ' + 'a' * (MAX_INPUT_LENGTH - 3)
    (actions, unclassified), result = C.canonicalise_hook('Bash', under, CTX)
    assert isinstance(result, Held) and unclassified is False
    assert actions[0].action_class == 'destructive' and actions[0].target == 'rm'

    for command, cls, target in (('git push origin main', 'git_push', 'git push'),
                                 ('git clean -fd', 'destructive', 'git clean'),
                                 ('rm file.txt', 'destructive', 'rm')):
        (labelled, held), _ = C.canonicalise_hook('Bash', command, CTX)
        assert not held and len(labelled) == 1
        action = labelled[0]
        assert action.action_class == cls and action.target == target
        assert action.argv == (command, 'Bash')
        assert not action.target.endswith(' ' + command.split(' ', 1)[1])


@pytest.mark.parametrize('tool,tool_input', (
    ('pwsh', 'pwd'),
    ('pwsh', {'command': 'pwd'}),
    ('Read', {'file_path': 'file.txt', 'command': 'pwd'}),
))
def test_the_shell_profile_is_never_handed_to_a_tool_that_is_not_bash(tool, tool_input):
    """canonical.py:320 (`command_context if tool == 'Bash' else None`). The
    allowlist profile says *posix shell, git worktree*: it describes what Bash
    runs, so any other executor - or a structured tool that smuggles a
    `command` field - must be classified with no profile at all. Passing the
    context through lets `pwd` through a row whose eligibility is a claim about
    a different program."""
    (actions, unclassified), result = C.canonicalise_hook(tool, tool_input, CTX, CONTEXT)
    assert isinstance(result, Held) and unclassified is True
    assert actions[0].action_class == 'exec' and actions[0].target == 'command'


def test_an_allowed_git_row_is_bound_to_its_subcommand_and_branch():
    """canonical.py:340-342 (`'git ' + row.prefix[1] if row.program == 'git'`).
    An allowed `git --no-pager status` is the *sub-command*, not `git`: a target
    of `git` would let one approval stand for every git row, and an action
    without the request's branch could be spent on another."""
    (actions, unclassified), result = C.canonicalise_hook(
        'Bash', 'git --no-pager status', CTX, CONTEXT)
    assert isinstance(result, Allowed) and not unclassified
    action = actions[0]
    assert action.target == 'git status' and action.argv == ('git', '--no-pager', 'status')
    assert action.branch == CTX['branch'] and action.action_class == result.action_class


def test_a_command_row_without_a_cwd_falls_back_to_the_workspace():
    """canonical.py:336 (`cwd = ctx.get('cwd') or ctx.get('workdir')`). A hook
    call with no `cwd` at all still resolves its row's paths, against the
    workspace; without the fallback `os.path.join(None, path)` raises a
    TypeError that no handler catches, and the tool call dies in the hook."""
    (actions, unclassified), result = C.canonicalise_hook(
        'Bash', 'cat file.txt', {'workdir': WD}, CONTEXT)
    assert isinstance(result, Allowed) and not unclassified
    assert actions[0].paths == ('file.txt',) and actions[0].target == 'cat'
    assert actions[0].branch is None                            # nothing named one


# ── the limits ──────────────────────────────────────────────────────────────

def test_a_command_of_exactly_the_storing_limit_is_stored_whole():
    """canonical.py:303 (`isinstance(cmd, str) and len(cmd) <=
    MAX_STORED_COMMAND`). The boundary is inclusive: a command of exactly the
    cap is stored as written (a 2-tuple, no digest), one character more takes
    the digest arm. An off-by-one either hashes a storable command (losing the
    exact text an approval binds to) or keeps an over-cap string verbatim."""
    cap = C.MAX_STORED_COMMAND
    exact, name = C._stored_command('a' * cap, 'Bash')
    assert name == 'Bash' and exact == 'a' * cap
    over = C._stored_command('a' * (cap + 1), 'Bash')
    assert over[0] == 'str' and over[-1] == 'Bash' and len(over) == 4
    assert len(over[1]) == cap - len('str') - 64 and len(over[2]) == 64


def test_a_truncated_stored_command_is_still_bound_by_its_digest():
    """canonical.py:305-307 (`digest = hashlib.sha256(value.encode('utf-8',
    errors='surrogatepass'))`). What is stored is a prefix, so the digest is
    the only thing binding the whole value: two commands that agree up to the
    truncation and differ after it must not share an approval identity. The
    surrogate-tolerant encode is the other half of the row - a lone surrogate
    in the payload (a decoded-then-redecoded argument) must not raise
    UnicodeEncodeError out of the hook, which nothing here catches."""
    cap = C.MAX_STORED_COMMAND
    head = 'a' * cap
    first, second = C._stored_command(head + '1', 'Bash'), C._stored_command(head + '2', 'Bash')
    assert first[1] == second[1] and first[2] != second[2]
    assert first[2] == C._stored_command(head + '1', 'Bash')[2]
    assert C._stored_command(head + '1', 'pwsh')[-1] == 'pwsh'        # the tool is stored too

    for tail in ('\ud800' * 5000, '\udfff\ud800' * 3000):
        (actions, unclassified), result = C.canonicalise_hook('Bash', 'rm ' + tail, CTX)
        assert isinstance(result, Held) and unclassified is True
        assert actions[0].argv[0] == 'str' and len(actions[0].argv[2]) == 64


def test_a_stored_tool_name_is_cut_to_the_reporting_limit():
    """canonical.py:302 (`name = str(tool)[:MAX_TOOL_NAME]`). The tool name is
    part of the identity - it is what stops one shell's approval covering
    another - so it is stored, and a harness-supplied name of any length is cut
    to the cap rather than growing the canonical blob without bound. A non-str
    tool name goes through `str()` first, and an unhashable one still stores."""
    assert C._stored_command('rm x', 'T' * 200)[1] == 'T' * C.MAX_TOOL_NAME
    assert C._stored_command('rm x', 'Bash')[1] == 'Bash'
    assert C._stored_command('rm x', 7)[1] == '7'
    (actions, _), _ = C.canonicalise_hook('Bash', 'mytool x', {'workdir': WD, 'cwd': WD})
    assert actions[0].argv[-1] == 'Bash'


def test_the_windows_path_limits_are_measured_the_way_windows_counts_them(monkeypatch):
    """canonical.py:385 (`_units`: UTF-16 units on Windows, bytes elsewhere)
    and canonical.py:396 (`re.split(r'[\\/]' if os.name == 'nt' else '/', s)`).
    Windows limits a *component* to 255 UTF-16 units and the whole path to
    32767, and separates on both slashes - so two 200-character components
    behind a backslash are fine there and are a single over-long component
    anywhere else, and a 128-character astral component is 256 units (refused)
    where it is 508 bytes (also refused, for the other reason). Measuring in
    bytes on Windows would wave through a path CreateFile rejects; splitting
    on '/' only would refuse one it accepts."""
    def check(**cases):
        return {key: outcome(path) for key, path in cases.items()}

    two = 'a' * 200 + '\\' + 'b' * 200
    astral = '\U0001F600'
    under = '\\'.join(['a' * 200] * 163)             # 32762 units
    exact = under + 'x' * 5                           # 32767: the ceiling itself
    over = under + 'x' * 6                            # 32768: one unit over
    with monkeypatch.context() as m:
        m.setattr(C.os, 'name', 'nt')
        nt = check(two=two, astral_over=astral * 128, astral_under=astral * 127,
                   under=under, exact=exact, over=over)
    with monkeypatch.context() as m:
        m.setattr(C.os, 'name', 'posix')
        plain = check(two=two, astral_under=astral * 127)
    assert nt['two'] == two and nt['astral_under'] == astral * 127
    assert nt['astral_over'] == REFUSED and nt['over'] == REFUSED
    assert nt['under'] == under and nt['exact'] == exact
    assert plain['two'] == REFUSED and plain['astral_under'] == REFUSED


def test_an_openable_check_happens_before_any_resolution(monkeypatch):
    """canonical.py:395-397 (the three refusals in `openable`). A NUL, a
    whole-path over the ceiling and an over-long component are refused from the
    string alone: `realpath` no longer raises on these (CPython gh-106242) and
    returns them as if they were ordinary, so a check after resolution would
    hand P9 a path no OS can open. `realpath` is patched to explode, which is
    what makes this about the check and not about the OS; the expected answers
    are the same whichever OS the check itself runs on."""
    monkeypatch.setattr(os.path, 'realpath', explode)
    assert outcome('a\x00b') == REFUSED and outcome('\x00') == REFUSED
    assert outcome('a' * 255) == 'a' * 255 and outcome('a' * 256) == REFUSED
    assert outcome('/'.join(['b' * 200] * 160)) == '/'.join(['b' * 200] * 160)
    assert outcome('/'.join(['b' * 200] * 164)) == REFUSED


@pytest.mark.parametrize('tool,tool_input', (
    ('Glob', {'path': ''}),
    ('Grep', {'pattern': 'needle', 'path': ''}),
))
def test_an_optional_path_that_is_present_but_empty_denies_the_call(tool, tool_input):
    """canonical.py:359-361 (`if given and not _text(given[0]) or not given and
    tool not in OPTIONAL_PATH`). The two arms read the same way at a glance and
    do opposite things: a `path` key that is *absent* means the whole workspace
    for a tool whose path is optional, while a `path` key that is *there but
    empty* is an input that cannot be parsed - it must never silently become a
    read of `.`. Losing the first arm turns both rows into a read of '.'."""
    actions, unclassified = C.canonicalise(tool, tool_input, CTX)
    assert unclassified is True and len(actions) == 1
    assert actions[0].action_class == 'exec' and actions[0].target == tool
    assert actions[0].paths is None
    found, found_unc = C.canonicalise(tool, dict(tool_input, path='.'), CTX)
    assert found_unc is False and found[0].action_class == 'read' and found[0].paths == ('.',)


def test_a_tool_that_names_itself_nothing_is_still_one_deniable_action():
    """canonical.py:428 (`target=target or 'command'`). An unnameable tool
    (the empty string) has no target to give, and an action with an empty
    target is refused by the domain - a ValueError raised *inside* the
    canonicaliser's own except arm escapes as a crash in the hook rather than
    as a denial. The fallback is what keeps the answer one exec."""
    actions, unclassified = C.canonicalise('', {'command': 'x'}, CTX)
    assert unclassified is True and len(actions) == 1
    assert actions[0].action_class == 'exec' and actions[0].target == 'command'


# ── the words that hand a tool a program to run ─────────────────────────────

@pytest.mark.parametrize('args', (
    ['-o', 'ProxyCommand=mytool'], ['-o', 'ProxyCommand mytool'], ['-oLocalCommand=x'],
    ['-o\nProxyCommand=mytool'], ['-vo', 'Match exec mytool'], ['-o', 'Match', 'exec', 'x'],
    ['-o', 'match exec x'], ['-o', 'PermitLocalCommand=yes -oProxyCommand=x'],
))
def test_an_ssh_option_that_names_a_program_is_held(args):
    """canonical.py:245-255 (`_o_runs`). ssh-family `-o` runs what its first
    word names, whether the value is glued on, in a cluster (`-vo`), on the
    next word, or behind a newline (the `re.S` on the option match is what
    keeps `-o\nProxyCommand=x` a value at all), and `Match exec` runs it from
    the word after."""
    assert C._o_runs(args) is True


@pytest.mark.parametrize('args', (
    [], ['-o'], ['-p', '-o'], ['-X', 'o'], ['-o', 'StrictHostKeyChecking=yes'],
    ['-o', 'IdentityFile=/x/y'], ['--o', 'ProxyCommand=x'], ['-o', 'Compression=yes'],
))
def test_an_ssh_option_that_names_no_program_is_not_held(args):
    """canonical.py:250-253 (`_o_runs`): the plain rows, and `-o` as the last
    word - the `args[i + 1] if i + 1 < len(args) else ''` guard, whose removal
    turns a trailing `-o` into an IndexError inside the classifier."""
    assert C._o_runs(args) is False


@pytest.mark.parametrize('prog,args', (
    ('tar', ['cIf', 'mytool']), ('tar', ['cIf9', 'x']), ('tar', ['-I', 'mytool']),
    ('gtar', ['-I', 'mytool']), ('bsdtar', ['--to-command', 'mytool']),
    ('tar', ['--checkpoint-a', 'exec:mytool']), ('tar', ['--use-compress-program=mytool']),
    ('rsync', ['-avze', 'mytool']), ('rsync', ['--rsh=mytool']), ('scp', ['-S', 'mytool']),
    ('sftp', ['-D', 'mytool']), ('wget', ['--execute=x']), ('wget', ['--exec']),
))
def test_a_carrier_option_is_held_whatever_it_carries(prog, args):
    """canonical.py:258-273 (`_carries`) with canonical.py:236-242 (`_abbrev`).
    tar's old-style bundle (`cIf` - a first word that is letters, no dash), its
    letters in a cluster, and the long spellings through any prefix of two
    letters or more: these options run the program the command line names, so
    the call is held before anything looks at the value."""
    assert C._carries(prog, args) is True


@pytest.mark.parametrize('prog,args', (
    ('tar', ['cf', 'x']), ('tar', ['-cf', 'x']), ('tar', ['--checkpoint', '60']),
    ('tar', ['--c', 'x']), ('tar', ['--', 'cIf']), ('rsync', ['-avl', 'x']),
    ('wget', ['-e']), ('wget', ['--exec-foo']), ('scp', ['-p', 'x']), ('mytool', ['-e', 'x']),
))
def test_a_lookalike_option_is_not_a_carrier(prog, args):
    """canonical.py:260-261 (`re.fullmatch(r'[A-Za-z0-9]+', args[0]) and any(ch
    in args[0] ...)`) and canonical.py:241 (`len(name) >= 2 and name !=
    'checkpoint'`). `tar cf` bundles the letters without I or F; `--checkpoint`
    is an option of its own and not an abbreviation of `--checkpoint-action`;
    a one-letter prefix is below the floor; wget has no carrier letter, so its
    `-e` is not read as one; a program outside the carriers is not read at all.
    Each of these held without the guard would be an over-refusal of a command
    the allowlist rows exist to allow."""
    assert C._carries(prog, args) is False


@pytest.mark.parametrize('piece', (
    '--pre', '--pre-glob', '--compress-program', '--exec=x', '-exec', '--pager',
    '--evaluate', '--hook', '--helper', '--shell', 'RUST_EDITOR=vim', 'PRE=x', '--no-pager',
))
def test_an_option_whose_name_says_it_runs_something_is_held(piece):
    """canonical.py:223-233 (`_gives_a_command`). The *name* of the option, or
    of the key before its `=`, is what is matched - `--no-pager` is held for
    what it can be pointed at, whatever it is pointed at."""
    assert C._gives_a_command(piece) is True


@pytest.mark.parametrize('piece', (
    'vim', 'mytool', 'exec', '--file=evil-program', '--format=xargs', '+exec', '-',
    '--prefix', 'data', 'RUST_LOG=vim',
))
def test_an_argument_or_a_value_that_merely_names_a_program_is_not_a_carrier(piece):
    """canonical.py:226-230 (`else: return False`) and canonical.py:224-225
    (`name = piece.split('=', 1)[0]`). A bare word is an argument, not an
    option, and the half after the `=` is a value: matching there would hold
    every command that mentions a program anywhere, and matching on a `+` word
    would hold what `less +F` is."""
    assert C._gives_a_command(piece) is False


@pytest.mark.parametrize('word', (
    'r?', 'b[a]sh', 'sh.*', 'RM*', '*/less', '*', 'ba?h', '[b]ash', 'gtar.*',
))
def test_a_glob_that_may_expand_to_a_program_is_held(word):
    """canonical.py:194-202 (`_glob_names_command`). The word is matched as a
    pattern against every known name with each of the suffixes a shell or
    Windows finds a program under, lowercased, directory kept out: `sh.*`
    reaches `sh.exe`, `RM*` reaches `rm`, and a globbed directory in front of
    `less` still names `less`."""
    assert C._glob_names_command(word) is True


@pytest.mark.parametrize('word', (
    'tests/*.py', '*.py', '--level', 'data*', 'README*', 'src/**/*.js', 'list*', 'ls',
    'notes.*', 'a{b,c}',
))
def test_a_glob_that_cannot_name_a_program_stays_plain(word):
    """canonical.py:198-201 (`if not _GLOB.search(word)` and the name/suffix
    cross-product). `tests/*.py` and `src/**/*.js` cannot expand to a program
    because no known name takes those suffixes, and a word with no glob
    character is never tested at all - holding these would make the ordinary
    `rg **/*.py` search a denial."""
    assert C._glob_names_command(word) is False


@pytest.mark.parametrize('cmd', (
    'mytool gtimeout 5 x', 'mytool -c"rm -R x"', 'mytool --flag=rm', 'mytool "rm"',
    'mytool C:\\Windows\\System32\\cmd.exe /c x', 'mytool --interpreter=python',
    'mytool hyperfine x', 'mytool xargs rm',
))
def test_a_word_that_is_a_program_name_after_a_quote_a_dash_or_an_equals(cmd):
    """canonical.py:211-220 (`_names_command`) over canonical.py:276-278
    (`_pieces`): the name is read after a directory, a quote, a run of dashes
    or the `=` of a key, and either as written or through `_norm`. Without the
    normalisation `-c"rm -R x"` and a quoted or backslashed path are plain
    arguments of an unknown tool."""
    assert C._names_command(C._pieces(cmd)) is True


@pytest.mark.parametrize('cmd', (
    'mytool start', 'mytool time', 'mytool watch', 'mytool --flag=3', 'mytool ./data.json',
))
def test_a_generic_word_or_a_number_as_an_argument_names_no_program(cmd):
    """canonical.py:215-219 (`_names_of(part.lstrip('-'))` and the closed
    `_ARG_WORDS | family` test). `start`, `time` and `watch` are program names
    that are also ordinary English, and they are argued out of the set by
    `_GENERIC`: an unknown tool taking `start` as an argument is not thereby
    running something. Adding them back holds the whole allowlist's worth of
    everyday commands."""
    assert C._names_command(C._pieces(cmd)) is False


@pytest.mark.parametrize('word,family', (
    ('bash', 'shell'), ('zsh.9', 'shell'), ('C:\\Windows\\System32\\cmd.EXE', 'cmd'),
    ('python3.11', 'python'), ('nodejs', 'node'), ('nodejs2', 'node'), ('gsed', 'sed'),
    ('gawk', 'code'), ('myawk', 'code'), ('nvim', 'code'), ('pwsh.exe', 'pwsh'),
    ('/usr/bin/perl5.36', 'perl'),
))
def test_a_program_family_is_read_from_a_closed_set_of_names(word, family):
    """canonical.py:126-142 (`_family`) over canonical.py:109-111 (`_norm`):
    every lookup goes through the normalised name - directory, quotes, the
    executable suffix, the trailing version digits - and the families are
    closed lists plus the `awk` suffix, so a name outside them is not code by
    its name."""
    assert C._family(C._norm(word)) == family


@pytest.mark.parametrize('word', ('awkward', 'shellx', 'runner', 'py3x', 'sedlike', 'nodejsx'))
def test_a_name_outside_the_families_is_not_code_by_its_name(word):
    """canonical.py:135-142 (`return None`): the closed-set promise. `awkward`
    only *starts* with awk and `py3x` keeps its digits (they come off a
    *trailing* run only); a family test that fell through to a substring match
    would call an unknown tool an interpreter."""
    assert C._family(C._norm(word)) is None


@pytest.mark.parametrize('cmd,program', (
    ('"C:\\Program Files\\Tool\\Py.exe" -c x', 'py'),
    ("'rm' -rf x", 'rm'),
    ('  /bin/BASH -c x  ', 'bash'),
    ('grep -n x', 'grep'),
    ('   ', ''),
    ('', ''),
))
def test_the_first_word_is_the_program_as_the_shell_reads_it(cmd, program):
    """canonical.py:453-459 (`_program`). The first word, quoted or not, keeps
    its basename, lowercased and with `.exe` gone; a command with no first word
    has no program at all. This is what the payload and wrapper rules read, so
    a quoted path to an interpreter must not read as an unknown tool."""
    assert C._program(cmd) == program


def test_a_windows_path_that_reached_argv_without_its_backslashes_is_read_back():
    """canonical.py:462-470 (`_prog_name`). shlex has already eaten the
    backslashes of a bare Windows path, so argv's basename is
    `C:WindowsSystem32tar.exe`, which no table knows; only the raw first word's
    basename is, and that is what the tables must be given. Dropping the
    fallback judges `C:\\Windows\\System32\\tar.exe -cf x` as an unknown
    program, and using the raw word always would let argv's name be overridden
    by what the command line merely mentions."""
    assert C._prog_name('C:WindowsSystem32tar.exe',
                        'C:\\Windows\\System32\\tar.exe -cf x') == 'tar'
    assert C._prog_name('GREP.EXE', 'rm -rf /') == 'grep'          # argv wins
    assert C._prog_name('ls', 'ls -l') == 'ls'
    assert C._prog_name('', 'mytool x') == ''
