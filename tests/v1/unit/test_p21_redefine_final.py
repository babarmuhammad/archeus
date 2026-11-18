from dataclasses import replace

import pytest

from archeus.core.execution.command_allowlist import Allowed, Held, Reason, classify
from v1.unit.test_command_allowlist import CONTEXT


@pytest.mark.parametrize('command', (
    pytest.param('curl -o out.txt https://h.example/x', id='Z417'),
    pytest.param('curl --output https://decoy.example/x https://h.example/x', id='Z431'),
    pytest.param('curl https://decoy.example/x https://h.example/x', id='Z441'),
    pytest.param('curl --proxy https://proxy.example/x https://h.example/x', id='Z456'),
    pytest.param('less +F file.txt', id='Z231'),
    pytest.param('vi file.txt', id='Z464'),
    pytest.param('mawk x', id='Z465'),
    pytest.param('mywrap eval rm', id='Z260'),
    pytest.param('tar --to-c sh -cf a.tar d', id='Z267'),
    pytest.param('sed s:a:b:e', id='Z278'),
    pytest.param('sed -es/a/b/e', id='Z279'),
    pytest.param('less.exe +F file.txt', id='Z289'),
))
def test_final_redefined_rows(command):
    context = replace(CONTEXT, programs=CONTEXT.programs | {command.split()[0]})
    assert classify(command, context) == Held(Reason.NO_ROW)


@pytest.mark.parametrize('command,plain', (
    pytest.param('p"wd"', 'pwd', id='Z189'),
    pytest.param('(pwd)', 'pwd', id='Z450'),
    pytest.param('! pwd', 'pwd', id='Z451'),
    pytest.param('pwd\u2013\u2014\u2015', 'pwd', id='Z229'),
    pytest.param('C:\\tools\\pwd', 'pwd', id='Z230'),
    pytest.param('p"wd"', 'pwd', id='Z435'),
    pytest.param('{pwd}', 'pwd', id='Z447'),
    pytest.param('ls {file.txt}', 'ls file.txt', id='Z448'),
    pytest.param('pwd\n', 'pwd', id='Z458'),
    pytest.param('p""wd', 'pwd', id='Z471'),
    pytest.param('ls {file.txt}', 'ls file.txt', id='Z472'),
    pytest.param('ls -""l .', 'ls -l .', id='Z473'),
    pytest.param('ls {{file.txt}}', 'ls file.txt', id='Z250'),
    pytest.param('p*wd', 'pwd', id='Z251'),
    pytest.param('C:\\Windows\\System32\\pwd', 'pwd', id='Z252'),
    pytest.param('ls {file.txt}', 'ls file.txt', id='Z266'),
))
def test_final_redefined_guards(command, plain):
    assert isinstance(classify(plain, CONTEXT), Allowed)
    assert isinstance(classify(command, CONTEXT), Held)


def test_final_redefined_quoted_ssh_carrier():
    context = replace(CONTEXT, programs=CONTEXT.programs | {'ssh'})
    assert classify('ssh -o "Match exec x" h', context) == Held(Reason.NO_ROW)


@pytest.mark.parametrize('command', (
    pytest.param('find . -exec mytool {} +', id='Z452'),
    pytest.param('find . -exec rm {} +', id='Z470'),
))
def test_final_redefined_find_exec(command):
    context = replace(CONTEXT, programs=CONTEXT.programs | {'find'})
    assert isinstance(classify(command, context), Held)
