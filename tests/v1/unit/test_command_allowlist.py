from dataclasses import replace
from itertools import product
from random import Random
from time import perf_counter

import pytest

from archeus.core.execution.command_allowlist import (
    MAX_INPUT_LENGTH, ROWS, Allowed, Held, PathEvidence, Reason, TrustedContext, classify,
)


CONTEXT = TrustedContext(
    posix_shell=True,
    programs=frozenset(row.program for row in ROWS),
    git_profile=True,
    paths={
        'file.txt': PathEvidence('file', True),
        'two words.txt': PathEvidence('file', True),
        '.': PathEvidence('directory', True, True),
        'tests': PathEvidence('directory', True, True),
    },
)
VECTORS = (
    ('A01', 'pwd'),
    ('A02', 'ls -a -l .'),
    ('A03', 'cat file.txt'),
    ('A04', 'head -n 20 file.txt'),
    ('A05', 'tail -n 20 file.txt'),
    ('A06', 'wc -l file.txt'),
    ('A07', 'rg --no-config --fixed-strings --line-number -- "some text" tests'),
    ('A08', 'git --no-pager status --porcelain=v1'),
    ('A09', 'git --no-pager diff --no-ext-diff --no-textconv --cached -- file.txt'),
    ('A10', 'git --no-pager log --max-count=20 --oneline HEAD'),
    ('A11', 'git --no-pager show --no-ext-diff --no-textconv HEAD'),
    ('A12', 'git --no-pager ls-files -- file.txt'),
    ('A13', 'git --no-pager rev-parse --show-toplevel'),
    ('A14', 'pytest -q tests'),
    ('A15', 'python -m pytest -q tests'),
    ('A16', 'node --version'),
)


@pytest.mark.parametrize('row_id,command', VECTORS)
def test_each_row(row_id, command):
    result = classify(command, CONTEXT)
    assert isinstance(result, Allowed)
    assert result.row_id == row_id
    assert result.status == 'ALLOWED'
    assert result.action_class == ('exec' if row_id in ('A14', 'A15', 'A16') else 'read')


def test_table_inventory():
    assert [row.id for row in ROWS] == [f'A{i:02}' for i in range(1, 17)]
    assert {row.program for row in ROWS}.isdisjoint({'curl', 'wget'})


@pytest.mark.parametrize('row', ROWS, ids=lambda row: row.id)
def test_every_complete_option_vector(row):
    operands = {
        'none': '', 'P*': 'tests', 'F+': 'file.txt',
        'search': '-- needle tests', 'optional_paths': '-- file.txt',
        'optional_head': 'HEAD', 'head': 'HEAD',
    }
    for options in row.options:
        command = ' '.join((row.program, *row.prefix, *options, operands[row.operands])).strip()
        assert isinstance(classify(command, CONTEXT), Allowed), command


@pytest.mark.parametrize('row_id,command', VECTORS)
@pytest.mark.parametrize('mutation', (
    lambda s: s + ' --extra',
    lambda s: s + ' {}',
    lambda s: s + ' *',
    lambda s: s + ' > file.txt',
    lambda s: s + ' $(pwd)',
    lambda s: 'X=1 ' + s,
    lambda s: s + '\npwd',
    lambda s: s + '\u0085',
    lambda s: s.replace(' ', '.exe ', 1) if ' ' in s else s + '.exe',
    lambda s: s.replace(' ', '.cmd ', 1) if ' ' in s else s + '.cmd',
    lambda s: './' + s,
    lambda s: '/bin/' + s,
    lambda s: 'C:\\tools\\' + s,
    lambda s: s.split(' ', 1)[0][:-1] + (' ' + s.split(' ', 1)[1] if ' ' in s else ''),
))
def test_per_row_near_misses(row_id, command, mutation):
    assert isinstance(classify(mutation(command), CONTEXT), Held)


@pytest.mark.parametrize('command', (
    'ls -la .', 'ls -l -a .', 'ls -a -a .', 'ls --all .',
    'head -n20 file.txt', 'head -n 2 file.txt', 'tail -f file.txt',
    'wc -lc file.txt', 'rg --no-conf --fixed-strings -- needle tests',
    'rg --fixed-strings --no-config -- needle tests',
    'git --no-pager stat', 'git --no-pager status --porc',
    'git --no-pager diff --no-ext-diff --no-textconv --sta',
    'git --no-pager log --max-count=2', 'git --no-pager log --max-count=20 main',
    'git --no-pager show --no-ext-diff --no-textconv main',
    'git --no-pager ls-files file.txt', 'git --no-pager rev-parse --show-top',
    'pytest -qq tests', 'python -m pytest -qq tests', 'node --ver',
    'py -m pytest', 'python3 -m pytest', 'python3.11 -m pytest',
    'PWD', 'cmd /c pwd', 'powershell pwd', 'pwsh pwd',
    "'pwd'", 'p""wd', 'ls "-l" .', 'ls -""l .',
    'cat ""', 'cat "file.txt', 'cat file.txt""', "cat 'file\".txt'",
    'cat -', 'cat ../file.txt', 'cat /file.txt', 'cat a//b', 'cat file.txt/',
    'cat @file.txt', 'cat file.txt:stream', 'cat https://x',
    'cat " file.txt"', 'cat "file.txt "', 'cat tests',
    'rg --no-config --fixed-strings -- "x|y" tests',
    'rg --no-config --fixed-strings -- "x=y" tests',
    'rg --no-config --fixed-strings -- needle',
    'git --no-pager diff --no-ext-diff --no-textconv --',
    'env pwd', 'X=1 pwd', 'pwd\r', 'pwd\x00', 'pwd\x7f', 'pwd\u00a0',
))
def test_grammar_and_exact_options(command):
    assert isinstance(classify(command, CONTEXT), Held)


@pytest.mark.parametrize('command', (
    'git push --{},force} origin main', 'rm -{},R} build',
    'git branch -{},D} x', 'find . -{},delete}',
    'sed \'s/' + '\\a' * 26 + "' f",
    'sed \'s/' + 'a\\/' * 4000 + "/b/' f",
    'rm --r build', 'rm --rec build', 'rm --recursiv build',
    'git branch --d x', 'git branch --del x', 'git branch -vd x',
    'git branch -fD x', 'git --u x', 'git ls-remote --u x ./nonexist',
    'git clone --u x URL', 'git push --m origin', 'git push --e x origin main',
    "sed --expr='e x' f", 'tar --rmt=mytool -cf h:a b', 'man --pa=x f',
    'curl -sd x https://h.example/x', 'curl -fsSLd x URL', 'curl -vXPOST URL',
    'wget -e use_askpass=mytool https://h.example/x',
    'wget -euse_askpass=mytool URL', 'wget -qe use_askpass=mytool URL',
    'npm pu', 'npm pub', 'npm publ', 'npm publi', 'npm inst x',
))
def test_six_required_review_families(command):
    start = perf_counter()
    assert isinstance(classify(command, CONTEXT), Held)
    assert perf_counter() - start < 0.25


@pytest.mark.parametrize('command', (None, 1, [], '', ' \t'))
def test_invalid_input(command):
    assert isinstance(classify(command, CONTEXT), Held)


def test_budget_and_linear_adversarial_scan():
    command = 'cat ' + 'a' * (100000 - 4)
    start = perf_counter()
    assert isinstance(classify(command, CONTEXT), Held)
    assert perf_counter() - start < 0.25
    assert classify('x' * (MAX_INPUT_LENGTH + 1), CONTEXT) == Held(Reason.BUDGET)
    assert classify('x' * MAX_INPUT_LENGTH, CONTEXT).reason != Reason.BUDGET


def test_context_is_required_and_bound_to_program():
    assert classify('pwd') == Held(Reason.CONTEXT)
    assert classify('pwd', TrustedContext()) == Held(Reason.CONTEXT)
    assert classify('pwd', replace(CONTEXT, posix_shell=False)) == Held(Reason.CONTEXT)
    assert classify('pwd', replace(CONTEXT, programs=frozenset({'git'}))) == Held(Reason.CONTEXT)
    assert classify('git --no-pager status', replace(CONTEXT, git_profile=False)) == Held(Reason.CONTEXT)


@pytest.mark.parametrize('evidence', (
    None, PathEvidence('file'), PathEvidence('directory', True),
    PathEvidence('directory', False, True),
))
def test_unknown_or_unsafe_path_evidence(evidence):
    paths = {} if evidence is None else {'tests': evidence}
    assert classify('ls tests', replace(CONTEXT, paths=paths)) == Held(Reason.PATH)
    assert classify('ls tests', replace(CONTEXT, paths=None)) == Held(Reason.PATH)


def test_typed_operands_and_normalization():
    result = classify('rg --no-config --fixed-strings -- needle ./tests', CONTEXT)
    assert isinstance(result, Allowed)
    assert result.paths == ('tests',)
    assert classify('cat "two words.txt"', CONTEXT).paths == ('two words.txt',)
    assert classify('cat ./file.txt', CONTEXT).paths == ('file.txt',)
    assert classify('pwd\t', CONTEXT).row_id == 'A01'


def test_unquoted_metacharacter_property():
    # Exhaust every insertion boundary, row and forbidden metacharacter, including quoted operand boundaries.
    metacharacters = '$`\\{}*?[]~%!|;&<>()#'
    for (_, command), char in product(VECTORS, metacharacters):
        for index in range(len(command) + 1):
            prefix = command[:index]
            if prefix.count('"') % 2:
                continue
            mutated = prefix + char + command[index:]
            assert isinstance(classify(mutated, CONTEXT), Held), mutated


@pytest.mark.parametrize('char', '$`\\{}*?[]~%!')
def test_always_forbidden_even_inside_quotes(char):
    assert isinstance(classify(f'rg --no-config --fixed-strings -- "x{char}y" tests', CONTEXT), Held)



def test_generated_unquoted_metacharacter_property():
    random = Random(128)
    alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789 -_=./\t'
    for _ in range(1000):
        text = ''.join(random.choices(alphabet, k=random.randrange(200)))
        index = random.randrange(len(text) + 1)
        char = random.choice('$`\\{}*?[]~%!|;&<>()#')
        assert isinstance(classify(text[:index] + char + text[index:], CONTEXT), Held)


def test_implicit_listing_directory_needs_evidence():
    assert classify('ls', replace(CONTEXT, paths={})) == Held(Reason.PATH)
    assert isinstance(classify('ls ./', CONTEXT), Allowed)


@pytest.mark.parametrize('command', (
    'ls', 'pytest', 'python -m pytest',
    'git --no-pager diff --no-ext-diff --no-textconv',
    'git --no-pager log --max-count=20', 'git --no-pager ls-files',
))
def test_optional_operands_can_be_absent(command):
    assert isinstance(classify(command, CONTEXT), Allowed)
