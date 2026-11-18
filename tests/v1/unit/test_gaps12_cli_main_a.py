"""T-1443: the launch code, the launch URL, the provider-terms answer, the route explanation and the Core
discovery helper of `archeus/cli/main.py`, lines 332-414 (`_launch_code`, `launch_url`, `terms`,
`route_why`, `_core_or_say`).

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. main.py:335-341  _launch_code: the body always carries the four scopes, 'supersede' only for a truthy
                     slot; a None answer prints to stderr and returns None; otherwise the 'code' field
 2. main.py:352-354  launch_url: None without a code; the code sits after '#launch=' in the fragment, and
                     '&memory=1' only with a slot
 3. main.py:387-396  route_why: a Core that is not running prints and returns 1 without calling Core
 4. main.py:397-401  route_why: a route id uses get_route_decision; any other ref takes the LAST decision of
                     the listing; an empty listing or a None answer gives no decision
 5. main.py:402-404  route_why: no decision prints and returns 2; a refused listing (None) does not raise
 6. main.py:405-406  route_why: '<id> (<result or selected>): <explanation>' and return 0
 7. main.py:409-414  _core_or_say: None unless discovery says 'running', then the info; no Core call
 8. main.py:362-373  terms list: a None answer prints 'Core did not answer' and returns 2; one row per term
 9. main.py:374-384  terms decide: body has headless and a 32-hex key from os.urandom(16); rotation only
                     when given; a None answer prints 'Core refused the answer' and returns 2
10. main.py:362-365  terms: a non-running Core returns 1 before any answer is asked, in list and decide

Closest existing tests: tests/v1/unit/test_gaps_cli_main.py and tests/v1/unit/test_gaps10_cli_main_a.py
(the automation and opt-ins helpers, which use the same _get fake). Nothing before this file calls
_launch_code, launch_url, route_why or _core_or_say with fakes for discovery and _get.

Seams: archeus.infra.discovery.discover is replaced with a fixed state; main._get is a recording fake that
returns scripted answers; ids.is_id is replaced for the route-id branch; os.urandom is fixed for the key.
Output is read with capsys. The launch code is a fake string and is only ever compared, never printed by
the test itself. No real Core, HTTP, token, user config or network.
"""

import os
from types import SimpleNamespace

import pytest

from archeus.cli import main as cli_main
from archeus.core.domain import ids
from archeus.infra import discovery

INFO = {'port': 1234}
CODE = 'FAKE-LAUNCH-CODE'
ROUTE_ID = 'rd_fake_route'


@pytest.fixture
def core(monkeypatch):
    core = SimpleNamespace(calls=[], answers=[], discovered=('running', INFO))

    def fake_get(info, method, path, body=None, **_):
        core.calls.append((info, method, path, body))
        return core.answers.pop(0) if core.answers else None
    monkeypatch.setattr(cli_main, '_get', fake_get)
    monkeypatch.setattr(discovery, 'discover', lambda: core.discovered)
    return core


def test_launch_code_carries_full_grant_and_supersede_only_for_a_slot(core, capsys):
    core.answers = [{'code': CODE}, {'code': CODE}]
    assert cli_main._launch_code(INFO) == CODE
    assert cli_main._launch_code(INFO, 'shell') == CODE
    (_, _, _, plain), (_, _, _, slotted) = core.calls
    assert plain == {'scopes': ['observe', 'control', 'approve', 'admin']}
    assert slotted == {'scopes': ['observe', 'control', 'approve', 'admin'], 'supersede': 'shell'}


def test_launch_code_refusal_prints_and_returns_none(core, capsys):
    core.answers = [None]
    assert cli_main._launch_code(INFO) is None
    err = capsys.readouterr().err
    assert err == 'could not get a launch code from Core on port 1234\n'


def test_launch_url_puts_the_code_in_the_fragment_and_memory_only_with_a_slot(core):
    core.answers = [{'code': CODE}, {'code': CODE}]
    plain = cli_main.launch_url(INFO)
    slotted = cli_main.launch_url(INFO, 'shell')
    assert plain == 'http://127.0.0.1:1234/#launch=' + CODE
    assert slotted == 'http://127.0.0.1:1234/#launch=' + CODE + '&memory=1'
    assert '?' not in plain and '?' not in slotted


def test_launch_url_is_none_when_no_code_comes_back(core, capsys):
    core.answers = [None]
    assert cli_main.launch_url(INFO) is None
    assert CODE not in capsys.readouterr().out


def test_route_why_refuses_when_core_is_not_running(core, capsys):
    core.discovered = ('stopped', None)
    assert cli_main.route_why(ROUTE_ID) == 1
    assert core.calls == []
    assert 'Core is not running' in capsys.readouterr().err


def test_route_why_uses_the_id_route_or_the_last_listed_decision(core, monkeypatch, capsys):
    monkeypatch.setattr(ids, 'is_id', lambda value, kind: value == ROUTE_ID)
    core.answers = [{'id': ROUTE_ID, 'explanation': 'by id'}]
    assert cli_main.route_why(ROUTE_ID) == 0
    assert core.calls[0][2] == cli_main.endpoints.get_route_decision(ROUTE_ID)
    core.answers = [{'route_decisions': [{'id': 'rd_a', 'explanation': 'old'},
                                         {'id': 'rd_b', 'explanation': 'latest'}]}]
    assert cli_main.route_why('msn_x') == 0
    assert core.calls[1][2] == cli_main.endpoints.list_route_decisions(source='msn_x')
    out = capsys.readouterr().out
    assert 'latest' in out and 'old' not in out


@pytest.mark.parametrize('answer', [{'route_decisions': []}, None])
def test_route_why_reports_no_decision_without_raising(core, monkeypatch, capsys, answer):
    monkeypatch.setattr(ids, 'is_id', lambda value, kind: False)
    core.answers = [answer]
    assert cli_main.route_why('msn_x') == 2
    assert capsys.readouterr().err == 'no route decision for msn_x\n'


def test_route_why_prints_selected_when_no_result_and_returns_zero(core, monkeypatch, capsys):
    monkeypatch.setattr(ids, 'is_id', lambda value, kind: True)
    core.answers = [{'id': ROUTE_ID, 'result': None, 'explanation': 'kept it'}]
    assert cli_main.route_why(ROUTE_ID) == 0
    assert capsys.readouterr().out == f'{ROUTE_ID} (selected): kept it\n'


def test_core_or_say_returns_info_only_while_running(core):
    assert cli_main._core_or_say() == INFO
    core.discovered = ('stopped', None)
    assert cli_main._core_or_say() is None
    assert core.calls == []


def test_terms_list_reports_silence_and_prints_one_row_per_term(core, capsys):
    core.answers = [None]
    assert cli_main.terms() == 2
    assert 'Core did not answer' in capsys.readouterr().err
    core.answers = [{'provider_terms': [{'id': 'claude', 'headless': 'yes', 'rotation': 'ok'},
                                        {'id': 'codex', 'headless': 'no', 'rotation': 'due'}]}]
    assert cli_main.terms() == 0
    rows = capsys.readouterr().out.splitlines()
    assert len(rows) == 2 and rows[0].startswith('claude')


def test_terms_decide_sends_a_fresh_key_and_rotation_only_when_given(core, monkeypatch, capsys):
    monkeypatch.setattr(os, 'urandom', lambda n: bytes(range(16)))
    key = bytes(range(16)).hex()
    core.answers = [{'provider_terms': {'id': 'claude', 'headless': True, 'rotation': None}},
                    {'provider_terms': {'id': 'claude', 'headless': True, 'rotation': 'r1'}}]
    assert cli_main.terms(harness='claude', headless=True) == 0
    assert cli_main.terms(harness='claude', headless=True, rotation='r1') == 0
    assert core.calls[0][3] == {'headless': True, 'idempotency_key': key}
    assert core.calls[1][3] == {'headless': True, 'idempotency_key': key, 'rotation': 'r1'}
    assert len(key) == 32


def test_terms_decide_refusal_prints_and_returns_two(core, capsys):
    core.answers = [None]
    assert cli_main.terms(harness='claude', headless=False) == 2
    assert capsys.readouterr().err == 'Core refused the answer for claude\n'


@pytest.mark.parametrize('harness', [None, 'claude'])
def test_terms_refuses_first_when_core_is_not_running(core, capsys, harness):
    core.discovered = ('stopped', None)
    assert cli_main.terms(harness=harness, headless=True) == 1
    assert core.calls == []
    assert 'Core is not running' in capsys.readouterr().err
