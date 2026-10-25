from dataclasses import dataclass
from enum import Enum
from typing import Literal, Mapping


MAX_INPUT_LENGTH = 131072
_ALWAYS_FORBIDDEN = frozenset('$`\\{}*?[]~%!')
_OPERATORS = frozenset('|;&<>()#')
_PATH_CHARS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./ ')
_LITERAL_CHARS = _PATH_CHARS - frozenset('/')
_DEVICE_NAMES = frozenset(('CON', 'PRN', 'AUX', 'NUL',
                           *(f'COM{i}' for i in range(1, 10)),
                           *(f'LPT{i}' for i in range(1, 10))))


class Reason(str, Enum):
    INPUT = 'input'
    BUDGET = 'budget'
    CHARACTER = 'character'
    METACHARACTER = 'metacharacter'
    QUOTING = 'quoting'
    NO_ROW = 'no_row'
    OPERAND = 'operand'
    CONTEXT = 'context'
    PATH = 'path'


@dataclass(frozen=True)
class Allowed:
    row_id: str
    action_class: Literal['read', 'exec']
    paths: tuple[str, ...] = ()
    status: Literal['ALLOWED'] = 'ALLOWED'


@dataclass(frozen=True)
class Held:
    reason: Reason
    status: Literal['HELD'] = 'HELD'


@dataclass(frozen=True)
class PathEvidence:
    kind: Literal['file', 'directory']
    contained: bool = False
    descendants_contained: bool = False


@dataclass(frozen=True)
class TrustedContext:
    # Evidence is bound by the caller to authenticated cwd, workspace and execution.
    posix_shell: bool = False
    programs: frozenset[str] = frozenset()
    git_profile: bool = False
    paths: Mapping[str, PathEvidence] | None = None


@dataclass(frozen=True)
class Row:
    id: str
    program: str
    prefix: tuple[str, ...]
    options: tuple[tuple[str, ...], ...]
    operands: str
    action_class: Literal['read', 'exec'] = 'read'


ROWS = (
    Row('A01', 'pwd', (), ((),), 'none'),
    Row('A02', 'ls', (), ((), ('-l',), ('-a',), ('-a', '-l')), 'P*'),
    Row('A03', 'cat', (), ((),), 'F+'),
    Row('A04', 'head', (), ((), ('-n', '20')), 'F+'),
    Row('A05', 'tail', (), ((), ('-n', '20')), 'F+'),
    Row('A06', 'wc', (), ((), ('-l',), ('-c',), ('-w',)), 'F+'),
    Row('A07', 'rg', (), (('--no-config', '--fixed-strings'),
                           ('--no-config', '--fixed-strings', '--line-number')), 'search'),
    Row('A08', 'git', ('--no-pager', 'status'), ((), ('--short',), ('--porcelain=v1',)), 'none'),
    Row('A09', 'git', ('--no-pager', 'diff'),
        (('--no-ext-diff', '--no-textconv'), ('--no-ext-diff', '--no-textconv', '--stat'),
         ('--no-ext-diff', '--no-textconv', '--cached')), 'optional_paths'),
    Row('A10', 'git', ('--no-pager', 'log'),
        (('--max-count=20',), ('--max-count=20', '--oneline')), 'optional_head'),
    Row('A11', 'git', ('--no-pager', 'show'), (('--no-ext-diff', '--no-textconv'),), 'head'),
    Row('A12', 'git', ('--no-pager', 'ls-files'), ((),), 'optional_paths'),
    Row('A13', 'git', ('--no-pager', 'rev-parse'),
        (('--show-toplevel',), ('--is-inside-work-tree',)), 'none'),
    Row('A14', 'pytest', (), ((), ('-q',)), 'P*', 'exec'),
    Row('A15', 'python', ('-m', 'pytest'), ((), ('-q',)), 'P*', 'exec'),
    Row('A16', 'node', (), (('--version',),), 'none', 'exec'),
)


@dataclass(frozen=True)
class _Token:
    text: str
    quoted: bool


def _scan(command: str) -> tuple[_Token, ...] | Held:
    tokens = []
    buffer = []
    quote = None
    quoted = False
    closed = False
    for char in command:
        code = ord(char)
        if code > 126 or code < 32 and char != '\t' or code == 127:
            return Held(Reason.CHARACTER)
        if char in _ALWAYS_FORBIDDEN or quote is None and char in _OPERATORS:
            return Held(Reason.METACHARACTER)
        if quote is not None:
            if char == quote:
                quote = None
                closed = True
            elif char in "'\"":
                return Held(Reason.QUOTING)
            else:
                buffer.append(char)
        elif char in ' \t':
            if buffer:
                tokens.append(_Token(''.join(buffer), quoted))
                buffer = []
            elif closed:
                return Held(Reason.QUOTING)
            quoted = closed = False
        elif closed:
            return Held(Reason.QUOTING)
        elif char in "'\"":
            if buffer:
                return Held(Reason.QUOTING)
            quote = char
            quoted = True
        else:
            buffer.append(char)
    if quote is not None or closed and not buffer:
        return Held(Reason.QUOTING)
    if buffer:
        tokens.append(_Token(''.join(buffer), quoted))
    return tuple(tokens)


def _word(token: _Token, word: str) -> bool:
    return not token.quoted and token.text == word


def _path(token: _Token) -> str | None:
    value = token.text
    if (not value or value[0] in '-/ ' or value[-1] == ' '
            or any(char not in _PATH_CHARS for char in value)):
        return None
    if value in ('.', './'):
        return '.'
    parts = value.split('/')
    if any(part in ('', '..') for part in parts):
        return None
    if any(part != '.' and (part.startswith(' ') or part.endswith(('.', ' '))
            or part.split('.')[0].upper() in _DEVICE_NAMES) for part in parts):
        return None
    return '/'.join(part for part in parts if part != '.') or '.'


def _operands(row: Row, tokens: tuple[_Token, ...]) -> tuple[str, ...] | Held:
    mode = row.operands
    if mode == 'none':
        return () if not tokens else Held(Reason.OPERAND)
    if mode in ('head', 'optional_head'):
        valid = len(tokens) == 1 and tokens[0].text == 'HEAD'
        return () if valid or mode == 'optional_head' and not tokens else Held(Reason.OPERAND)
    if mode == 'search':
        if len(tokens) < 3 or not _word(tokens[0], '--'):
            return Held(Reason.OPERAND)
        literal = tokens[1].text
        if (not literal or literal.startswith('-')
                or any(char not in _LITERAL_CHARS for char in literal)):
            return Held(Reason.OPERAND)
        tokens = tokens[2:]
    elif mode == 'optional_paths':
        if not tokens:
            return ()
        if len(tokens) < 2 or not _word(tokens[0], '--'):
            return Held(Reason.OPERAND)
        tokens = tokens[1:]
    if mode == 'F+' and not tokens:
        return Held(Reason.OPERAND)
    paths = []
    for token in tokens:
        path = _path(token)
        if path is None:
            return Held(Reason.OPERAND)
        paths.append(path)
    return tuple(paths)


def classify(command: object, context: TrustedContext | None = None) -> Allowed | Held:
    if not isinstance(command, str) or not command:
        return Held(Reason.INPUT)
    if len(command) > MAX_INPUT_LENGTH:
        return Held(Reason.BUDGET)
    tokens = _scan(command)
    if isinstance(tokens, Held):
        return tokens
    if not tokens or tokens[0].quoted:
        return Held(Reason.NO_ROW)
    failure = Held(Reason.NO_ROW)
    for row in ROWS:
        if tokens[0].text != row.program:
            continue
        for options in row.options:
            fixed = row.prefix + options
            if len(tokens) < 1 + len(fixed):
                continue
            if not all(_word(token, word) for token, word in zip(tokens[1:], fixed)):
                continue
            paths = _operands(row, tokens[1 + len(fixed):])
            if isinstance(paths, Held):
                failure = paths
                continue
            if (context is None or not context.posix_shell or row.program not in context.programs
                    or row.program == 'git' and not context.git_profile):
                return Held(Reason.CONTEXT)
            evidence_paths = paths or (('.',) if row.program == 'ls' else ())
            for path in evidence_paths:
                evidence = context.paths.get(path) if context.paths is not None else None
                if (evidence is None or not evidence.contained
                        or evidence.kind not in ('file', 'directory')
                        or row.operands == 'F+' and evidence.kind != 'file'
                        or evidence.kind == 'directory' and not evidence.descendants_contained):
                    return Held(Reason.PATH)
            return Allowed(row.id, row.action_class, paths)
    return failure

