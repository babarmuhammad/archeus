from dataclasses import replace

import pytest

from archeus.core.execution.command_allowlist import Allowed, Held, Reason, classify
from v1.unit.test_command_allowlist import CONTEXT


@pytest.mark.parametrize('command', (
    pytest.param('curl -o out.txt https://h.example/x', id='Z151'),
    pytest.param('curl --output https://decoy.example/x https://h.example/x', id='Z176'),
    pytest.param('curl https://decoy.example/x https://h.example/x', id='Z197'),
    pytest.param('curl --proxy https://proxy.example/x https://h.example/x', id='Z213'),
    pytest.param('less +F file.txt', id='Z231'),
    pytest.param('vi file.txt', id='Z235'),
    pytest.param('mawk x', id='Z236'),
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
    pytest.param('(pwd)', 'pwd', id='Z207'),
    pytest.param('! pwd', 'pwd', id='Z208'),
    pytest.param('pwd\u2013\u2014\u2015', 'pwd', id='Z229'),
    pytest.param('C:\\tools\\pwd', 'pwd', id='Z230'),
    pytest.param('p"wd"', 'pwd', id='Z190'),
    pytest.param('{pwd}', 'pwd', id='Z204'),
    pytest.param('ls {file.txt}', 'ls file.txt', id='Z205'),
    pytest.param('pwd\n', 'pwd', id='Z215'),
    pytest.param('p""wd', 'pwd', id='Z242'),
    pytest.param('ls {file.txt}', 'ls file.txt', id='Z243'),
    pytest.param('ls -""l .', 'ls -l .', id='Z244'),
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
    pytest.param('find . -exec mytool {} +', id='Z209'),
    pytest.param('find . -exec rm {} +', id='Z241'),
))
def test_final_redefined_find_exec(command):
    context = replace(CONTEXT, programs=CONTEXT.programs | {'find'})
    assert isinstance(classify(command, context), Held)
