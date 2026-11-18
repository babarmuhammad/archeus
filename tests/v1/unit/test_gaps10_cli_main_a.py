"""T-1395: the highest-risk uncovered branches of `archeus/cli/main.py`, lines 697-790 (`automation`, `_OPT`,
`opt_ins`, the start of `_flags`).

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. main.py:700-702   automation: an unknown verb prints USAGE to stderr and returns 2 before Core is asked.
 2. main.py:711-713   automation create: a file whose JSON is not an object returns 2 naming the file; Core is
                      not asked.
 3. main.py:706-710   automation create: an unreadable file, invalid JSON and JSON nested past the recursion
                      limit all return 2 with 'cannot read'.
 4. main.py:714-716   automation: _running None returns 1 before any _get, so no body is built or sent.
 5. main.py:717-728   automation create: the POST body is the file object plus a fresh 32-hex idempotency key.
 6. main.py:731-733   automation: a None answer prints 'Core refused or does not know <arg>' (or 'that' with no
                      arg) and returns 2.
 7. main.py:734-740   automation list: one row per automation and one line per quarantined event; 'no
                      automations' only when the automation list is empty.
 8. main.py:741-744   automation: show/why/simulate print JSON; any other verb prints 'id: state'.
 9. main.py:758-768   opt_ins 'opt-ins' with no rows prints the excluded-sources text and returns 0; _running
                      None returns 1 first.

Closest existing tests: tests/v1/unit/test_gaps_cli_main.py (the missing-file OSError arm, line 296, and the
pair refusal), tests/v1/unit/test_t150_gaps.py and tests/v1/integration/test_automation.py (the Core side). No
unit test calls automation or opt_ins with a fake _get before this file.

Seams: `main._running` returns a fake info or None; `main._get` records (method, path, body) and returns scripted
answers; `os.urandom` is patched for a fixed key; output is read with capsys; create files are written only
under tmp_path. No real Core token, discovery file, home or environment value is read.
"""

import json
import os

import pytest

from archeus.cli import main


def ask_nothing(*a, **k):
    pytest.fail('Core was asked')


def scripted(answers):
    calls = []

    def get(info, method, path, body=None, **kw):
        calls.append((method, path, body))
        return answers(method, path) if callable(answers) else answers

    return get, calls


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return str(p)


def test_an_unknown_verb_prints_usage_and_returns_two_before_core_is_asked(monkeypatch, capsys):
    monkeypatch.setattr(main, '_running', ask_nothing)
    assert main.automation('frobnicate', None) == 2
    assert capsys.readouterr().err.startswith('usage:')


def test_a_create_file_that_is_not_one_object_returns_two_and_names_the_file(tmp_path, monkeypatch,
                                                                             capsys):
    path = write(tmp_path, 'list.json', '[1, 2, 3]')
    monkeypatch.setattr(main, '_running', ask_nothing)
    assert main.automation('create', path) == 2
    assert '%s must hold one JSON object' % path in capsys.readouterr().err


def test_an_unreadable_invalid_or_too_deep_create_file_is_cannot_read_and_returns_two(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(main, '_running', ask_nothing)
    broken = write(tmp_path, 'broken.json', '{"a": ')
    deep = write(tmp_path, 'deep.json', '[' * 100000 + ']' * 100000)
    for path in (broken, deep, str(tmp_path / 'absent.json')):
        assert main.automation('create', path) == 2
        assert 'cannot read' in capsys.readouterr().err


def test_no_running_core_returns_one_before_any_request_is_built(tmp_path, monkeypatch):
    path = write(tmp_path, 'ok.json', '{"name": "nightly"}')
    get, calls = scripted(None)
    monkeypatch.setattr(main, '_running', lambda: None)
    monkeypatch.setattr(main, '_get', get)
    assert main.automation('create', path) == 1
    assert calls == []


def test_the_create_body_is_the_file_object_plus_a_fresh_idempotency_key(tmp_path, monkeypatch,
                                                                         capsys):
    path = write(tmp_path, 'ok.json', '{"name": "nightly", "trigger": {"type": "schedule"}}')
    get, calls = scripted({'id': 'au1', 'state': 'DRAFT'})
    monkeypatch.setattr(main, '_running', lambda: {'port': 9})
    monkeypatch.setattr(main, '_get', get)
    monkeypatch.setattr(os, 'urandom', lambda n: b'\x01' * n)
    assert main.automation('create', path) == 0
    assert calls == [('POST', main.endpoints.create_automation(),
                      {'name': 'nightly', 'trigger': {'type': 'schedule'},
                       'idempotency_key': '01' * 16})]
    assert capsys.readouterr().out == 'au1: DRAFT\n'


def test_a_refused_or_unknown_answer_names_the_argument_and_returns_two(monkeypatch, capsys):
    monkeypatch.setattr(main, '_running', lambda: {'port': 9})
    monkeypatch.setattr(main, '_get', scripted(None)[0])
    assert main.automation('show', 'a1') == 2
    assert capsys.readouterr().err.strip().endswith('Core refused or does not know a1')
    assert main.automation('show', None) == 2
    assert capsys.readouterr().err.strip().endswith('Core refused or does not know that')


def test_list_prints_one_row_per_automation_and_quarantine_and_says_none_only_when_empty(
        monkeypatch, capsys):
    monkeypatch.setattr(main, '_running', lambda: {'port': 9})
    answer = {'automations': [{'id': 'au1', 'state': 'ON', 'trigger': {'type': 'schedule'},
                               'name': 'nightly'}],
              'quarantined': [{'seq': 7, 'error': 'bad trigger'}]}
    monkeypatch.setattr(main, '_get', scripted(answer)[0])
    assert main.automation('list', None) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith('au1  ON')
    assert 'quarantined event 7: bad trigger' in out
    assert 'no automations' not in out

    monkeypatch.setattr(main, '_get', scripted({'automations': [],
                                                 'quarantined': [{'seq': 3, 'error': 'x'}]})[0])
    assert main.automation('list', None) == 0
    out = capsys.readouterr().out
    assert 'quarantined event 3: x' in out and out.splitlines()[-1] == 'no automations'


def test_show_prints_json_and_another_verb_prints_id_and_state(monkeypatch, capsys):
    monkeypatch.setattr(main, '_running', lambda: {'port': 9})
    answer = {'id': 'au1', 'runs': []}
    monkeypatch.setattr(main, '_get', scripted(answer)[0])
    assert main.automation('show', 'au1') == 0
    assert json.loads(capsys.readouterr().out) == answer

    get, calls = scripted({'id': 'au1', 'state': 'DISABLED'})
    monkeypatch.setattr(main, '_get', get)
    monkeypatch.setattr(os, 'urandom', lambda n: b'\x02' * n)
    assert main.automation('disable', 'au1') == 0
    assert capsys.readouterr().out == 'au1: DISABLED\n'
    assert calls[0][2] == {'idempotency_key': '02' * 16, 'action': 'disable'}


def test_opt_ins_with_no_rows_says_what_is_excluded_and_returns_zero(monkeypatch, capsys):
    monkeypatch.setattr(main, '_running', lambda: {'port': 9})
    monkeypatch.setattr(main, '_get', scripted({'opt_ins': []})[0])
    assert main.opt_ins('opt-ins') == 0
    out = capsys.readouterr().out
    assert 'no opt-ins' in out and 'hooks, plugins, skills and MCP servers' in out


def test_opt_ins_without_a_running_core_returns_one_before_any_request(monkeypatch):
    get, calls = scripted(None)
    monkeypatch.setattr(main, '_running', lambda: None)
    monkeypatch.setattr(main, '_get', get)
    assert main.opt_ins('opt-ins') == 1
    assert calls == []
