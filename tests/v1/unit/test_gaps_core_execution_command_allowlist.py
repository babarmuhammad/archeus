"""Gap tests for the closed command allowlist (T-300).

Every test here names, in its docstring, the branch of
``archeus/core/execution/command_allowlist.py`` it exists to protect, and each one
fails when that branch is removed or inverted. The existing suite asserts
``isinstance(result, Held)`` for hundreds of inputs without ever reading
``result.reason``, so a classifier that denied everything for one flat reason,
that accepted non-str commands, that leaked a path-evidence kind, or that let a
program outside the closed table through under a generous context would have
passed unchanged. Those are the branches covered here.

Style and fixtures follow ``tests/v1/unit/test_command_allowlist.py`` (the module's
own test file) and ``tests/v1/unit/test_command_allowlist_hook.py``. Everything is
platform-neutral: no OS call, no process, no filesystem, no network, no reliance on
case-insensitive names, and no ``?``/``:`` in any path. ``_path``, ``_operands`` and
``_Token`` are used only for the two defensive branches that a real command string
cannot produce (an empty word); production code already leans on the sibling private
seam ``command_allowlist._scan`` in ``archeus/core/execution/canonical.py``.
"""
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace

import pytest

from archeus.core.execution.command_allowlist import (
    MAX_INPUT_LENGTH, ROWS, Allowed, Held, PathEvidence, Reason, Row, TrustedContext,
    _Token, _operands, _path, classify,
)
from v1.unit.test_command_allowlist import CONTEXT, VECTORS

TABLE_PROGRAMS = frozenset(row.program for row in ROWS)
TABLE_ROWS = {row.id: row for row in ROWS}
# Names that must never be reachable through the table, no matter what the caller
# claims about the context. Every one of them is outside the closed table.
RISKY_PROGRAMS = (
    'rm', 'rmdir', 'del', 'erase', 'mv', 'cp', 'dd', 'chmod', 'curl', 'wget', 'ssh', 'scp',
    'sftp', 'rsync', 'tar', 'npm', 'sh', 'bash', 'zsh', 'cmd', 'powershell', 'pwsh', 'perl',
    'php', 'ruby', 'sed', 'find', 'xargs', 'make', 'env', 'nohup', 'taskkill', 'reg',
    'format', 'iex', 'Invoke-Expression', 'git3', 'python3', 'pip', 'nodejs', 'py',
)


class AnyEvidence(Mapping):
    """Evidence seam: every path the classifier asks about resolves, so only the
    classifier itself can deny. Used instead of a real filesystem."""

    def __init__(self, kind='file', contained=True, descendants=True, known=()):
        self.kind = kind
        self.contained = contained
        self.descendants_contained = descendants
        self._known = tuple(known)

    def __getitem__(self, key):
        if not isinstance(key, str) or not key:
            raise KeyError(key)
        return PathEvidence(self.kind, self.contained, self.descendants_contained)

    def __iter__(self):
        return iter(self._known)

    def __len__(self):
        return len(self._known)


ANY = AnyEvidence()
FILES = AnyEvidence('file', True, True, ('file.txt', 'tests', 'x'))
WITH_FILES = replace(CONTEXT, paths=FILES)
MAXIMAL = TrustedContext(True, TABLE_PROGRAMS | frozenset(RISKY_PROGRAMS), True, ANY)
EXEC_ROW_IDS = frozenset({'A14', 'A15', 'A16'})
FIXED_WORDS = frozenset(
    word for row in ROWS for options in row.options for word in (*row.prefix, *options))


class OutsideTable:
    """Non-str whose every dunder blows up: only the type check may touch it."""

    def __len__(self):
        raise AssertionError('len() of a non-str command must not run')

    def __iter__(self):
        raise AssertionError('a non-str command must not be scanned')

    def __str__(self):
        raise AssertionError('a non-str command must not be stringified')

    def __eq__(self, other):
        raise AssertionError('a non-str command must not be compared')

    def __hash__(self):
        return 3


class LyingStr(str):
    """A str subclass whose equality always succeeds."""

    def __eq__(self, other):
        return True

    def __hash__(self):
        return 1


NON_STRINGS = (
    None, True, False, 0, 1, 1.5, Ellipsis, object(), b'pwd', bytearray(b'pwd'),
    memoryview(b'pwd'), ['pwd'], ('pwd',), {'command': 'pwd'}, {'pwd'}, frozenset('pwd'),
    Held(Reason.PATH), Allowed('A01', 'read'), Row('X', 'pwd', (), ((),), 'none'),
    OutsideTable(),
)


def held(command, context=CONTEXT, reason=None):
    result = classify(command, context)
    assert not isinstance(result, Allowed), (command, result)
    assert isinstance(result, Held), (command, result)
    assert result.status == 'HELD'
    if reason is not None:
        assert result.reason is reason, (command, result.reason)
    return result


def allowed(command, context, row_id, paths=None):
    result = classify(command, context)
    assert not isinstance(result, Held), (command, result)
    assert isinstance(result, Allowed), (command, result)
    assert result.status == 'ALLOWED'
    assert result.row_id == row_id
    assert result.action_class == ('exec' if row_id in EXEC_ROW_IDS else 'read'), row_id
    if paths is not None:
        assert result.paths == paths
    return result


# ----------------------------------------------------------------------------------
# Identity of the command object: line 195-196 (INPUT) and 202-203 (empty token).
# ----------------------------------------------------------------------------------
@pytest.mark.parametrize('command', NON_STRINGS, ids=lambda v: type(v).__name__)
def test_non_str_command_is_held_with_reason_input(command):
    """classify():195 `if not isinstance(command, str) or not command` → Held(INPUT).

    Also 205/230: a non-str never reaches the table, so the reason is INPUT and not
    the NO_ROW a stranger string would get."""
    held(command, CONTEXT, Reason.INPUT)
    held(command, None, Reason.INPUT)
    held(command, MAXIMAL, Reason.INPUT)


def test_type_check_decides_before_length_and_scan():
    """classify():195-199 ordering: INPUT is decided before len() (197) and _scan (199).

    OutsideTable raises from __len__/__iter__/__str__/__eq__; if any of those ran first
    the call would raise instead of denying."""
    for command in (OutsideTable(), [OutsideTable()], {'k': OutsideTable()}):
        held(command, CONTEXT, Reason.INPUT)


def test_only_the_characters_of_the_command_decide():
    """classify():195/206 — a str subclass with a lying __eq__ cannot open a row.

    The verdict must come from the characters, not from the object."""
    held(LyingStr('rm -rf build'), MAXIMAL, Reason.NO_ROW)
    held(LyingStr('cat file.txt CON'), MAXIMAL, Reason.OPERAND)
    allowed(LyingStr('cat file.txt'), WITH_FILES, 'A03', ('file.txt',))


@pytest.mark.parametrize('command,reason', (
    ('', Reason.INPUT), (' ', Reason.NO_ROW), ('\t', Reason.NO_ROW), (' \t ', Reason.NO_ROW),
))
def test_empty_command_is_input_and_blank_command_is_no_row(command, reason):
    """classify():195 (`not command` → INPUT) versus 202 (no tokens → NO_ROW)."""
    held(command, CONTEXT, reason)


def test_verdict_is_exactly_allowed_or_held():
    """Allowed/Held (lines 26-39): unrelated frozen types with fixed status literals.

    Callers test `isinstance(result, Allowed)`; making one a subclass of the other, or
    dropping the status literal, breaks every caller check."""
    result = classify('pwd', CONTEXT)
    assert type(result) is Allowed and result.status == 'ALLOWED'
    assert type(classify('nope', CONTEXT)) is Held
    assert not issubclass(Held, Allowed) and not issubclass(Allowed, Held)
    assert Allowed('A01', 'read') != Held(Reason.NO_ROW)
    assert Held(Reason.PATH).status == 'HELD' and Held(Reason.PATH).reason is Reason.PATH
    with pytest.raises(FrozenInstanceError):
        result.row_id = 'A99'
    assert classify('pwd', CONTEXT) == Allowed('A01', 'read', ())


# ----------------------------------------------------------------------------------
# The closed program-class table: 205-207, 208-213, 218-220 and the `failure`
# accumulator at 204/216/230.
# ----------------------------------------------------------------------------------
@pytest.mark.parametrize('command', (
    'rm -rf build', 'rmdir build', 'del file.txt', 'erase file.txt', 'mv a b', 'cp a b',
    'dd if=/dev/zero of=disk', 'chmod 777 x', 'curl h.example/x',
    'wget h.example/x', 'ssh h.example', 'scp a h.example/b', 'sftp h.example',
    'rsync a h:b', 'tar -cf a.tar d', 'npm install x', 'npm publish', 'sh -c pwd',
    'bash -c pwd', 'zsh -c pwd', 'cmd /c pwd', 'powershell -c pwd', 'pwsh -c pwd',
    'python -c x', 'python3 -m pytest', 'node --eval x', 'node -e x', 'perl -e x',
    'php -r x', 'ruby -e x', 'sed i s/a/b/ f', 'find . -deletex', 'xargs rm', 'make',
    'env pwd', 'nohup rm -rf build', 'git push origin main', 'git3 --no-pager status',
    'taskkill /f /im x', 'reg delete hkcu/x', 'format volume', 'iex x', 'Invoke-Expression x',
    'py -m pytest', 'pip install x', 'nodejs x', 'python -m pip install x',
    'python -m -q pytest', 'python -m pytestx', 'git --no-pager push origin main',
    'git --no-pager clean -fdx', 'git --no-pager reset --hard',
    'git --no-pager rebase -i HEAD', 'git --no-pager config core.pager sh',
    'git --no-pager branch -d x', 'git --no-pager checkout main',
    'git --no-pager worktree add x',
))
def test_risky_programs_stay_held_under_a_maximally_permissive_context(command):
    """classify():205-207/230 — the table is closed: a program no row names can never
    be allowed, even with posix_shell, membership for that very program, git_profile
    and evidence for every path."""
    held(command, MAXIMAL, Reason.NO_ROW)


@pytest.mark.parametrize('command', (
    'ls -l --color=always .', 'wc -lw file.txt', 'head -n 5 file.txt',
    'tail -n 20 -f file.txt', 'pytest -p x', 'node --version x',
    'rg --no-config --fixed-strings --pre tool -- x .',
    'git --no-pager status --porcelain=v1 --cached',
    'cat file.txt file.txt CON',
    'head -n 20 -- file.txt',
))
def test_unsafe_options_on_a_table_program_hold_under_a_permissive_context(command):
    """classify():208-213/164-165 — a table program with an option outside its closed
    option vector still denies, and the denial is remembered as OPERAND (204/216/230),
    not flattened to NO_ROW."""
    held(command, MAXIMAL, Reason.OPERAND)


@pytest.mark.parametrize('command', (
    'PWD', 'Pwd', 'pWd', 'LS -l x', 'Ls -l file.txt', 'CAT file.txt', 'Cat file.txt',
    'CATALOG x', 'cats file.txt', 'PYTEST -q tests', 'PYTHON -m pytest -q tests',
    'Node --version', 'NODE --version', 'node.exe --version', 'GIT --no-pager STATUS',
    'Git --no-pager status', 'ls.exe -l x', 'cat.exe file.txt', 'pwd.exe', '/bin/ls -l x',
    './pwd', 'bin/pwd', 'rg2 --no-config --fixed-strings -- x .', 'wc3 -l file.txt',
))
def test_program_identity_is_exact(command):
    """classify():206 `if tokens[0].text != row.program` — matching is exact, so case
    folds, `.exe`/`.cmd` suffixes and path prefixes never resolve to a row. This is the
    Windows resolution risk: cmd.exe would run `PWD` as `pwd`."""
    held(command, MAXIMAL, Reason.NO_ROW)


@pytest.mark.parametrize('command', (
    '"pwd"', "'pwd'", '"python" -m pytest', '"node" --version',
    '"git" --no-pager status', '"ls" -l x', '"cat" file.txt', '"pytest" -q tests',
))
def test_quoted_program_name_never_matches_a_row(command):
    """classify():202 `if not tokens or tokens[0].quoted` → Held(NO_ROW): a quoted
    program name is data, never a row match, so quoting cannot launder a program."""
    held(command, MAXIMAL, Reason.NO_ROW)


@pytest.mark.parametrize('command', ('p"wd"', 'cat" file.txt', 'ls" -l x', 'py"thon" x'))
def test_a_word_spliced_onto_a_quote_is_a_quoting_error(command):
    """_scan():129-130 `elif buffer: return Held(Reason.QUOTING)` — a quote glued onto a
    program name is denied as QUOTING before the table is ever consulted."""
    held(command, MAXIMAL, Reason.QUOTING)


@pytest.mark.parametrize('command', (
    'cat "a\'b"', 'cat \'a"b\'', "rg --no-config --fixed-strings -- \"it's\" tests",
    'python -m pytest \'x"y\'', 'ls -l "d\'x"', 'git --no-pager status "a\'b"',
))
def test_a_quote_inside_a_quoted_word_is_a_quoting_error(command):
    """_scan():115-116 `elif char in "'\\"": return Held(Reason.QUOTING)` — a quote cannot
    be nested inside a quoted word, so no word can smuggle quote characters that a shell
    would later re-interpret."""
    held(command, MAXIMAL, Reason.QUOTING)


@pytest.mark.parametrize('command,reason', (
    pytest.param('git "--no-pager" status', Reason.NO_ROW, id='git-pager-option'),
    pytest.param('git --no-pager "status"', Reason.NO_ROW, id='git-subcommand'),
    pytest.param('git --no-pager "rev-parse" --show-toplevel', Reason.NO_ROW, id='git-rev-parse'),
    pytest.param('git "--no-pager" log "--max-count=20"', Reason.NO_ROW, id='git-log-option'),
    pytest.param('python "-m" pytest', Reason.NO_ROW, id='python-m'),
    pytest.param('node "--version"', Reason.NO_ROW, id='node-version'),
    pytest.param('rg "--no-config" --fixed-strings -- needle tests', Reason.NO_ROW,
                 id='rg-options'),
    pytest.param('pytest "-q" tests', Reason.OPERAND, id='pytest-option-is-a-path'),
    pytest.param('head "-n" 20 file.txt', Reason.OPERAND, id='head-count-is-a-path'),
))
def test_quoted_fixed_words_never_match_a_row(command, reason):
    """_word():142-143 `not token.quoted and token.text == word` — the fixed program name,
    subcommand and option words of a row must be given unquoted. Dropping the `quoted`
    half of this test would let `git "--no-pager" status` or `node "--version"` reach a
    row (and would turn the last two cases into an outright ALLOWED)."""
    held(command, MAXIMAL, reason)


def test_table_shape_is_closed():
    """ROWS (60-89) plus 205-229: the table itself is the whole policy surface."""
    assert [row.id for row in ROWS] == [f'A{i:02}' for i in range(1, 17)]
    assert len({row.id for row in ROWS}) == len(ROWS)
    assert len({(row.program, row.prefix, row.options) for row in ROWS}) == len(ROWS)
    assert {row.operands for row in ROWS} == {
        'none', 'P*', 'F+', 'search', 'head', 'optional_head', 'optional_paths'}
    assert {row.id for row in ROWS if row.action_class == 'exec'} == {'A14', 'A15', 'A16'}
    assert {row.program for row in ROWS if row.action_class == 'exec'} == {
        'pytest', 'python', 'node'}
    assert {row.program for row in ROWS if row.action_class == 'read'}.isdisjoint(
        {'pytest', 'python', 'node'})
    for row in ROWS:
        assert row.action_class in ('read', 'exec')
        assert isinstance(row.program, str) and row.program
        assert row.program == row.program.strip().lower()
        assert not any(char in row.program for char in ' \\/.')
        assert isinstance(row.prefix, tuple) and isinstance(row.options, tuple)
        assert row.options and all(isinstance(options, tuple) for options in row.options)
        assert len({options for options in row.options}) == len(row.options)
        for options in row.options:
            for word in (*row.prefix, *options):
                assert isinstance(word, str) and word == word.strip()
                assert not set(word) & set(' \t\\/|&;<>$`\'"*?(){}!#~\x00')
        if row.program in ('head', 'tail'):
            for options in row.options:
                assert '-n' not in options or options[-2:] == ('-n', '20')
        with pytest.raises(FrozenInstanceError):
            row.program = 'rm'
    # Every fixed word of every row is pinned: widening `-n 20` or the git subcommand
    # surface has to be an explicit edit to this assertion too.
    assert {word for word in FIXED_WORDS if not word.startswith('-')} == {
        '20', 'pytest', 'status', 'diff', 'log', 'show', 'ls-files', 'rev-parse'}
    # A git row is always a read: no row may hand git a write or exec subcommand.
    assert all(row.action_class == 'read' for row in ROWS if row.program == 'git')
    assert all(row.prefix[0] == '--no-pager' for row in ROWS if row.program == 'git')
    assert {row.program for row in ROWS} == {
        'pwd', 'ls', 'cat', 'head', 'tail', 'wc', 'rg', 'git', 'pytest', 'python', 'node'}


# ----------------------------------------------------------------------------------
# Reserved names and path boundaries: 146-159.
# ----------------------------------------------------------------------------------
@pytest.mark.parametrize('name', (
    *[name for name in ('CON', 'con', 'PRN', 'prn', 'AUX', 'aux', 'NUL', 'nul')],
    *tuple(f'COM{i}' for i in range(1, 10)), *tuple(f'com{i}' for i in range(1, 10)),
    *tuple(f'LPT{i}' for i in range(1, 10)), *tuple(f'lpt{i}' for i in range(1, 10)),
    'CON.txt', 'nul.tar.gz', 'COM1.log', 'lpt9.txt', 'dir/CON.txt', 'dir/nul',
    'a/b/NUL.log', 'CON .txt', 'NUL .x', 'src/NuL.txt', 'src/com1 .log',
))
def test_windows_reserved_names_hold_even_with_evidence_for_every_path(name):
    """_path():156-158 `part.split('.')[0].rstrip(' .').upper() in _DEVICE_NAMES` →
    None → _operands():188-189 → Held(OPERAND). Evidence is granted for every path, so
    only the reserved-name check can deny; dropping `.upper()` or the extension strip
    lets a device namespace through."""
    held('cat "' + name + '"', MAXIMAL, Reason.OPERAND)
    held('cat ' + name, MAXIMAL, Reason.OPERAND)


@pytest.mark.parametrize('name', (
    'COM0', 'LPT0', 'COM10', 'COM1a', 'CONS.txt', 'NULX', 'AUX1', 'AUXI.txt', 'PRINTME',
    'conclusion.md', 'modal.dat', 'assistant/log', 'LPT10.log', 'COM99.log', 'PRN2',
))
def test_names_that_only_look_reserved_stay_allowed(name):
    """_path():156-157 — the device check is an exact-name match, not a prefix match:
    widening it to a prefix test fails here."""
    allowed('cat ' + name, MAXIMAL, 'A03', (name,))


@pytest.mark.parametrize('name', ('a.', 'a..', 'dir/b.', 'a. ', '"a."', '"a.. "',
                                  '"a "', '"dir/b."', 'file.txt.', 'dir/b. ', '". "',
                                  '"a/. "', '"./ "'))
def test_trailing_dot_or_space_holds(name):
    """_path():156 `part.endswith(('.', ' '))` → None → Held(OPERAND)."""
    held('cat ' + name, MAXIMAL, Reason.OPERAND)


@pytest.mark.parametrize('command,expected', (
    pytest.param('ls ././.', ('.',), id='dot-only-listing'),
    pytest.param('ls ./.', ('.',), id='dot-dir'),
))
def test_a_path_of_only_dot_segments_normalises_to_one_dot(command, expected):
    """_path():159 `'/'.join(...) or '.'` — the empty-join fallback to '.'; the caller
    then has to re-check that single dot against the evidence."""
    allowed(command, MAXIMAL, 'A02', expected)


def test_a_dot_only_file_operand_still_needs_file_evidence():
    """_path():159 empty-join fallback feeding classify():226-227 — `cat ././.` collapses
    to '.', which the context records as a directory, so the F+ row must deny it."""
    directory = {'.': PathEvidence('directory', True, True)}
    held('cat ././.', replace(CONTEXT, paths=directory), Reason.PATH)
    held('cat ./.', replace(CONTEXT, paths=directory), Reason.PATH)
    held('head -n 20 ././.', replace(CONTEXT, paths=directory), Reason.PATH)
    allowed('cat ././.', replace(CONTEXT, paths={'.': PathEvidence('file', True)}),
            'A03', ('.',))
    held('wc ././.', CONTEXT, Reason.PATH)


@pytest.mark.parametrize('name', ('../file.txt', './../file.txt', '..', '/etc/passwd', 'a//b',
                                  'a/', 'file.txt/', '".."', '"a/.."', '"a/../b"', '"./../x"',
                                  'a/./../b', '" /etc/passwd"', '"././../x"'))
def test_traversal_and_absolute_paths_hold_with_reason_operand(name):
    """_path():148-155 (leading `-`/`/`/space, empty or `..` segment) → None →
    _operands():188-189 → Held(OPERAND)."""
    held('cat ' + name, MAXIMAL, Reason.OPERAND)


@pytest.mark.parametrize('name', (
    'a,b', 'a,b.txt', '"a,b"', '"file@host"', 'a=b', '"a=b"', 'a+b', '"a+b"', 'a^b', '"a^b"',
    '"a;b"', '"a|b"', '"a&b"', '"a<b"', '"a>b"', '"a#b"', '"a(b"',
))
def test_paths_are_limited_to_the_documented_character_set(name):
    """_path():147-149 `any(char not in _PATH_CHARS for char in value)` → None →
    Held(OPERAND). Characters such as `,`, `=`, `+`, `^` and the operator set pass the
    scanner inside quotes, so the path alphabet is the only thing that can deny them."""
    held('cat ' + name, MAXIMAL, Reason.OPERAND)


def test_the_documented_path_alphabet_is_accepted():
    """_path():147 — the positive half of the same condition: every character the
    allowlist advertises must survive, or whole rows would deny real files."""
    allowed('cat "a-b_c.1/xY9"', MAXIMAL, 'A03', ('a-b_c.1/xY9',))


def test_path_predicate_rejects_an_empty_word():
    """_path():148 `not value` → None. classify() cannot produce an empty token (the
    scanner denies it), so this defensive branch is reached only through the seam."""
    assert _path(_Token('', False)) is None
    assert _path(_Token('', True)) is None
    assert _path(_Token('con', False)) is None
    assert _path(_Token('.', False)) == '.'
    assert _path(_Token('./.', False)) == '.'


# ----------------------------------------------------------------------------------
# Scanner branches no existing test reaches: 123-124 and 126-127.
# ----------------------------------------------------------------------------------
@pytest.mark.parametrize('command', (
    'cat "" x', 'ls "" .', 'pwd ""', 'pytest "" tests',
    'rg --no-config --fixed-strings -- "" needle tests', 'git --no-pager status ""',
    'python -m pytest "" tests', 'cat "" ""',
))
def test_empty_quoted_word_followed_by_a_space_is_a_quoting_error(command):
    """_scan():123-124 `elif closed: return Held(Reason.QUOTING)` — an empty quoted word
    may not be glued to another word; today no test in the suite reaches this line."""
    held(command, MAXIMAL, Reason.QUOTING)


@pytest.mark.parametrize('command', (
    'cat "x"y', 'ls -"l".', 'python -m pytest "q"tests', 'rg --no-config --fixed-strings '
    '-- "n"needle tests', 'git --no-pager status "s"hort', 'cat ""x', 'cat "x"x',
))
def test_text_glued_to_a_closing_quote_is_a_quoting_error(command):
    """_scan():126-127 `elif closed: return Held(Reason.QUOTING)` — a word cannot be
    spliced onto a closing quote; no existing test reaches this line either."""
    held(command, MAXIMAL, Reason.QUOTING)


# ----------------------------------------------------------------------------------
# Operand grammar boundaries: 162-191.
# ----------------------------------------------------------------------------------
@pytest.mark.parametrize('literal', ('-x', '-', '--version', '-n', '"-l"'))
def test_search_literal_cannot_start_with_a_dash(literal):
    """_operands():173 `literal.startswith('-')` → Held(OPERAND): a literal may not be
    smuggled into an option for rg."""
    held('rg --no-config --fixed-strings -- ' + literal + ' tests', MAXIMAL, Reason.OPERAND)


def test_search_literal_cannot_be_empty_even_for_a_synthetic_token():
    """_operands():173 `not literal` → Held(OPERAND). classify() can never hand over an
    empty token, so this defensive half of the condition is reached only via the seam."""
    row = TABLE_ROWS['A07']
    assert _operands(row, (_Token('--', False), _Token('', False), _Token('tests', False))) \
        == Held(Reason.OPERAND)
    assert _operands(row, (_Token('--', False), _Token('n', True), _Token('tests', False))) \
        == ('tests',)


@pytest.mark.parametrize('command', (
    'rg --no-config --fixed-strings --', 'rg --no-config --fixed-strings -- needle',
    'rg --no-config --fixed-strings needle tests',
    'rg --no-config --fixed-strings needle tests more',
    'rg --no-config --fixed-strings --line-number needle tests more',
    'rg --no-config --fixed-strings --line-number --',
))
def test_search_needs_a_separator_and_a_path(command):
    """_operands():170-171 `len(tokens) < 3 or not _word(tokens[0], '--')` →
    Held(OPERAND)."""
    held(command, MAXIMAL, Reason.OPERAND)


@pytest.mark.parametrize('command', (
    'git --no-pager ls-files file.txt', 'git --no-pager ls-files --',
    'git --no-pager diff --no-ext-diff --no-textconv -',
    'git --no-pager diff --no-ext-diff --no-textconv --',
    'git --no-pager ls-files -- ..', 'git --no-pager ls-files " -- " file.txt',
    'git --no-pager diff --no-ext-diff --no-textconv -- --',
))
def test_optional_paths_need_the_double_dash_separator(command):
    """_operands():180-181 `len(tokens) < 2 or not _word(tokens[0], '--')` →
    Held(OPERAND); a quoted `--` is not a separator."""
    held(command, MAXIMAL, Reason.OPERAND)


@pytest.mark.parametrize('command', (
    'git --no-pager show --no-ext-diff --no-textconv main',
    'git --no-pager show --no-ext-diff --no-textconv head',
    'git --no-pager show --no-ext-diff --no-textconv HEAD HEAD',
    'git --no-pager show --no-ext-diff --no-textconv',
    'git --no-pager log --max-count=20 head',
    'git --no-pager log --max-count=20 HEAD HEAD',
    'git --no-pager log --max-count=20 --oneline origin/main',
))
def test_head_operand_is_an_exact_word(command):
    """_operands():166-168 `valid = len(tokens) == 1 and tokens[0].text == 'HEAD'` →
    Held(OPERAND) for every other head operand."""
    held(command, MAXIMAL, Reason.OPERAND)


@pytest.mark.parametrize('command', (
    'pwd extra', 'node --version x', 'git --no-pager rev-parse --show-toplevel x',
    'git --no-pager status --short x', 'cat', 'wc', 'head -n 20', 'tail -n 20',
))
def test_rows_that_take_no_or_required_operands_denied(command):
    """_operands():164-165 (`none` with anything left) and 183-184 (`F+` with nothing):
    both → Held(OPERAND)."""
    held(command, MAXIMAL, Reason.OPERAND)


def test_operand_failure_survives_the_rest_of_the_table():
    """classify():204/216/230 — the last operand failure is remembered as `failure` and
    returned instead of NO_ROW, so a caller can tell "wrong arguments" from "unknown
    program"."""
    for command, reason in (
        ('git --no-pager status --short extra', Reason.OPERAND),
        ('git --no-pager rev-parse --is-inside-work-tree x', Reason.OPERAND),
        ('ls -l ../x', Reason.OPERAND),
        ('git --no-pager status', Reason.CONTEXT),
        ('totally-unknown --short extra', Reason.NO_ROW),
    ):
        assert classify(command, None).reason is reason, command


# ----------------------------------------------------------------------------------
# Path evidence gates: 221-228.
# ----------------------------------------------------------------------------------
@pytest.mark.parametrize('kind', (
    'symlink', 'link', 'dir', 'directory-with-data', 'FILE', 'Directory', 'file ', '',
    'device', 'pipe', 'socket', None, 0,
))
def test_evidence_kind_outside_file_or_directory_holds(kind):
    """classify():225 `evidence.kind not in ('file', 'directory')` → Held(PATH).

    No existing test ever builds a PathEvidence with a kind outside the two literals,
    so this whole denial line is dead in the current suite: a symlink or a bogus kind
    would be allowed."""
    context = replace(CONTEXT, paths={'file.txt': PathEvidence(kind, True, True)})
    held('cat file.txt', context, Reason.PATH)
    held('ls file.txt', context, Reason.PATH)


def test_evidence_of_the_wrong_shape_holds_for_each_row_family():
    """classify():224-227 — missing evidence, uncontained evidence, a directory without
    descendant containment, and a directory where F+ needs a file."""
    uncontained = replace(CONTEXT, paths={
        'file.txt': PathEvidence('file', False, False),
        'tests': PathEvidence('directory', False, True)})
    held('cat file.txt', uncontained, Reason.PATH)
    held('ls tests', uncontained, Reason.PATH)
    held('pytest tests', uncontained, Reason.PATH)
    # A directory is evidence for a listing row but never for an F+ row.
    directory = replace(CONTEXT, paths={'file.txt': PathEvidence('directory', True, True)})
    held('cat file.txt', directory, Reason.PATH)
    allowed('ls file.txt', directory, 'A02', ('file.txt',))
    # A directory that is not descendant-contained can never back a listing either.
    shallow = replace(CONTEXT, paths={'tests': PathEvidence('directory', True, False)})
    held('ls tests', shallow, Reason.PATH)
    held('pytest tests', shallow, Reason.PATH)
    held('cat tests', shallow, Reason.PATH)
    held('cat file.txt', replace(CONTEXT, paths=None), Reason.PATH)


@pytest.mark.parametrize('command,row_id', (
    ('pwd', 'A01'), ('git --no-pager status', 'A08'),
    ('git --no-pager rev-parse --show-toplevel', 'A13'), ('node --version', 'A16'),
))
def test_rows_that_take_no_paths_need_no_evidence(command, row_id):
    """Rows with no operand grammar read no directory: no evidence is asked of them."""
    allowed(command, replace(CONTEXT, paths={}), row_id, ())
    allowed(command, replace(CONTEXT, paths=None), row_id, ())


@pytest.mark.parametrize('command', ('ls', 'pytest', 'pytest -q', 'python -m pytest',
                                     'python -m pytest -q'))
def test_an_operand_free_P_star_row_needs_evidence_for_its_implicit_root(command):
    """classify():221 `paths or (('.',) if row.operands == 'P*' else ())` — `ls` lists and
    pytest discovers beneath cwd, so the implicit '.' needs the same contained-directory
    and descendant evidence an explicit `.` does."""
    held(command, replace(CONTEXT, paths={}), Reason.PATH)
    held(command, replace(CONTEXT, paths=None), Reason.PATH)
    held(command, replace(CONTEXT, paths={'.': PathEvidence('directory', True, False)}),
         Reason.PATH)
    held(command, replace(CONTEXT, paths={'.': PathEvidence('directory', False, True)}),
         Reason.PATH)
    held(command + ' .', replace(CONTEXT, paths={}), Reason.PATH)


def test_ls_implicit_directory_needs_a_contained_directory():
    """classify():221-227 for the implicit '.' of a bare `ls`."""
    held('ls', replace(CONTEXT, paths={'.': PathEvidence('directory', True, False)}),
         Reason.PATH)
    held('ls', replace(CONTEXT, paths={'.': PathEvidence('directory', False, True)}),
         Reason.PATH)
    allowed('ls', replace(CONTEXT, paths={'.': PathEvidence('directory', True, True)}),
           'A02', ())


def test_git_profile_is_required_only_for_git_rows():
    """classify():218-219 `row.program == 'git' and not context.git_profile` →
    Held(CONTEXT), and the same field must be irrelevant to every other row."""
    no_git = replace(CONTEXT, git_profile=False)
    for command in ('git --no-pager status', 'git --no-pager diff --no-ext-diff '
                                               '--no-textconv -- file.txt',
                    'git --no-pager log --max-count=20', 'git --no-pager show '
                    '--no-ext-diff --no-textconv HEAD'):
        held(command, no_git, Reason.CONTEXT)
    for command, row_id in (('cat file.txt', 'A03'), ('pytest tests', 'A14'),
                            ('python -m pytest -q tests', 'A15'), ('node --version', 'A16'),
                            ('ls -a -l .', 'A02'), ('wc -l file.txt', 'A06')):
        allowed(command, no_git, row_id)


@pytest.mark.parametrize('command', (
    'pytest tests', 'pytest -q tests', 'python -m pytest tests',
    'python -m pytest -q tests', 'node --version',
))
def test_exec_rows_need_the_shell_and_the_program(command):
    """classify():218 `context is None or not context.posix_shell or row.program not in
    context.programs` → Held(CONTEXT) for the three exec rows."""
    held(command, None, Reason.CONTEXT)
    held(command, replace(CONTEXT, posix_shell=False), Reason.CONTEXT)
    held(command, replace(CONTEXT, programs=frozenset(TABLE_PROGRAMS - {'python', 'node',
                                                                        'pytest'})),
         Reason.CONTEXT)
    allowed(command, CONTEXT, TABLE_ROWS[TABLE_FOR[command]].id)


TABLE_FOR = {
    'pytest tests': 'A14', 'pytest -q tests': 'A14', 'python -m pytest tests': 'A15',
    'python -m pytest -q tests': 'A15', 'node --version': 'A16',
}


# ----------------------------------------------------------------------------------
# Budget boundary: 197-198.
# ----------------------------------------------------------------------------------
def test_budget_boundary_is_exclusive_and_decided_before_scanning():
    """classify():197-198 `len(command) > MAX_INPUT_LENGTH` → Held(BUDGET): exactly at
    the limit is allowed, one over is held, and the check runs before the scanner so an
    over-long command with forbidden characters is still BUDGET and never CHARACTER."""
    allowed('cat ' + 'a' * (MAX_INPUT_LENGTH - 4), WITH_FILES, 'A03')
    held('cat ' + 'a' * (MAX_INPUT_LENGTH - 3), WITH_FILES, Reason.BUDGET)
    held('x' * (MAX_INPUT_LENGTH + 1), CONTEXT, Reason.BUDGET)
    held('$' + 'x' * MAX_INPUT_LENGTH, CONTEXT, Reason.BUDGET)
    held('x' * MAX_INPUT_LENGTH + '\x00', CONTEXT, Reason.BUDGET)


# ----------------------------------------------------------------------------------
# The reason itself, and stability of the verdict.
# ----------------------------------------------------------------------------------
@pytest.mark.parametrize('command,reason', (
    pytest.param('pwd\x01', Reason.CHARACTER, id='control-char'),
    pytest.param('pwd\u00a0', Reason.CHARACTER, id='non-ascii'),
    pytest.param('pwd\x7f', Reason.CHARACTER, id='del'),
    pytest.param('pwd;pwd', Reason.METACHARACTER, id='pipe-operator'),
    pytest.param('cat file.txt > out.txt', Reason.METACHARACTER, id='redirect'),
    pytest.param('cat "a$%b"', Reason.METACHARACTER, id='always-forbidden-in-quotes'),
    pytest.param('cat "a', Reason.QUOTING, id='unterminated-quote'),
    pytest.param('cat "" x', Reason.QUOTING, id='empty-quoted-word'),
    pytest.param('cat "x"y', Reason.QUOTING, id='glued-word'),
    pytest.param('cat', Reason.OPERAND, id='missing-required-operand'),
    pytest.param('pwd extra', Reason.OPERAND, id='extra-operand'),
    pytest.param('cat CON', Reason.OPERAND, id='reserved-name'),
    pytest.param('nope --version', Reason.NO_ROW, id='unknown-program'),
    pytest.param('cat file.txt', Reason.CONTEXT, id='no-context'),
    pytest.param('cat file.txt', Reason.PATH, id='no-evidence'),
))
def test_every_denial_reason_is_reported_exactly(command, reason):
    """classify():194-230 — the reason is part of the contract: INPUT, BUDGET,
    CHARACTER, METACHARACTER, QUOTING, NO_ROW, OPERAND, CONTEXT and PATH are all
    distinguishable. Collapsing any of them onto another reason fails here."""
    context = (None if reason is Reason.CONTEXT
               else replace(CONTEXT, paths={}) if reason is Reason.PATH else CONTEXT)
    held(command, context, reason)


def test_verdict_is_stable_and_paths_are_normalised():
    """classify():214/229 and _operands():185-191 — the same input always gives the
    same verdict, and reported paths are the normalised ones, never the raw token."""
    for _, command in VECTORS:
        first, second = classify(command, CONTEXT), classify(command, CONTEXT)
        assert first == second and type(first) is type(second)
    result = classify('rg --no-config --fixed-strings -- needle ./tests ././tests', CONTEXT)
    assert isinstance(result, Allowed) and result.paths == ('tests', 'tests')
    assert classify('cat ./file.txt', CONTEXT) == Allowed('A03', 'read', ('file.txt',))
    assert classify('ls ./', CONTEXT) == Allowed('A02', 'read', ('.',))
