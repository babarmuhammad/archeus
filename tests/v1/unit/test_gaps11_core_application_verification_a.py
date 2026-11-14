"""T-1416: the uncovered branches of `archeus/core/application/verification.py`
lines 55-106: verdict_of, readings, verified_execution, performed_by, _get and
_where (the lineage comment sits in that span too).

Ten selected probes, denial and fail-closed first, then boundaries, then error paths:

1  verdict_of 61-62      a 'fail' result is FAILED even beside an error and a pass
                         -> test_a_failed_check_outranks_an_error_and_a_pass
2  verdict_of 63-64      no fail, one error -> ERROR -> test_an_errored_check_without_a_failure_is_error
3  verdict_of 65-66      no command check (automatic/manual only, or empty) -> ERROR, never PASSED
                         -> test_a_battery_without_a_command_check_is_error_never_passed
4  verdict_of 67         all pass with a command check -> PASSED -> test_passing_commands_make_passed
5  readings 72-75        automatic criteria take the state mapping; manual keeps its result
                         -> test_an_automatic_criterion_takes_the_verdict_mapping
                         -> test_a_manual_criterion_keeps_its_own_result
6  readings 73           a criterion neither automatic nor manual keeps its own result key,
                         never the mapping -> test_a_criterion_of_another_check_keeps_its_result
7  verified_execution 82-84  latest ENDED_OK by (attempt, id); ENDED_ERROR ignored; None
                         -> test_the_latest_ended_ok_execution_is_the_verified_one
                         -> test_no_ended_ok_execution_means_none
8  performed_by 89-93    seven identity keys, account_ref from the RouteDecision row only
                         when the id is set and the row exists -> test_performed_by_copies_the_identity_keys
9  performed_by 89       no route_decision_id reads no RouteDecision row -> account_ref None
                         -> test_no_route_decision_reads_no_row
10 _get/_where 96-104    _get returns the entity or None; _where forwards the filters
                         -> test_get_returns_the_entity_or_none, test_where_forwards_the_filters

Nothing here reads a database or the artifact store: `_where` and `_get` are replaced
(or `archeus.infra.db.rows` is, for the two helpers), and the lineage functions get
plain objects. Each branch above is caught by the removal or inversion named in its test.
"""

from types import SimpleNamespace

import pytest

from archeus.core.application import verification as ver
from archeus.core.domain import entities
from archeus.infra.db import rows


def _check(kind, result, name='c'):
    return {'name': name, 'kind': kind, 'result': result}


def _ex(id_, attempt, state, route_decision_id=None):
    return SimpleNamespace(id=id_, attempt=attempt, state=state, harness_id='h',
                           account_id='acct', model='m', effort='e',
                           route_decision_id=route_decision_id, session_id='s')


def _rows_of(*entities_):
    return [SimpleNamespace(entity=e) for e in entities_]


# ── verdict_of (55-67) ──────────────────────────────────────────────────────

def test_a_failed_check_outranks_an_error_and_a_pass():
    # removing the 'fail' branch (61-62) would return ERROR here; inverting it would
    # return PASSED for the battery that has a pass and no error
    checks = [_check('command', 'error'), _check('command', 'pass'), _check('command', 'fail')]
    assert ver.verdict_of(checks) == 'FAILED'
    assert ver.verdict_of(list(reversed(checks))) == 'FAILED'


def test_an_errored_check_without_a_failure_is_error():
    # removing 63-64 would fall through to the command check and return PASSED
    checks = [_check('command', 'pass'), _check('command', 'error')]
    assert ver.verdict_of(checks) == 'ERROR'


@pytest.mark.parametrize('checks', [
    [_check('automatic', 'pass'), _check('manual', 'pass')],
    [_check('manual', 'pass')],
    [],
], ids=['automatic-and-manual', 'manual-only', 'empty'])
def test_a_battery_without_a_command_check_is_error_never_passed(checks):
    # removing 65-66 turns each of these into PASSED
    assert ver.verdict_of(checks) == 'ERROR'


def test_passing_commands_make_passed():
    # the only path to PASSED: no fail, no error, at least one command check
    checks = [_check('command', 'pass'), _check('automatic', 'pass')]
    assert ver.verdict_of(checks) == 'PASSED'


# ── readings (70-75) ────────────────────────────────────────────────────────

@pytest.mark.parametrize('state, expected', [
    ('PASSED', 'satisfied'),
    ('FAILED', 'failed'),
    ('ERROR', 'unknown'),
    ('AWAITING_HUMAN', 'unknown'),
], ids=['passed', 'failed', 'error', 'awaiting'])
def test_an_automatic_criterion_takes_the_verdict_mapping(state, expected):
    # dropping the mapping (72) or the check test (73) changes these readings
    criteria = [{'check': 'automatic', 'text': 'tests pass', 'result': 'stale'}]
    (reading,) = ver.readings(criteria, state)
    assert reading['result'] == expected
    assert reading['text'] == 'tests pass'
    assert criteria[0]['result'] == 'stale'                 # the input is not mutated


def test_a_manual_criterion_keeps_its_own_result():
    # the manual branch of 74 (c.get('result', 'unknown')) ignores the state entirely
    criteria = [{'check': 'manual', 'text': 'looks right', 'result': 'satisfied'},
                {'check': 'manual', 'text': 'no result yet'}]
    kept, missing = ver.readings(criteria, 'FAILED')
    assert kept['result'] == 'satisfied'
    assert missing['result'] == 'unknown'


def test_a_criterion_of_another_check_keeps_its_result():
    # with state PASSED the mapping would say 'satisfied'; the criterion is not automatic,
    # so it keeps the key it has (here: none -> 'unknown'), never the mapping
    criteria = [{'check': 'other', 'text': 'x'}, {'check': 'other', 'text': 'y', 'result': 'failed'}]
    no_key, own = ver.readings(criteria, 'PASSED')
    assert no_key['result'] == 'unknown'
    assert own['result'] == 'failed'


# ── verified_execution (80-84) ──────────────────────────────────────────────

@pytest.fixture
def executions(monkeypatch):
    box = {}

    def fake_where(conn, cls, **eq):
        box['call'] = (cls, eq)
        return box['rows']

    monkeypatch.setattr(ver, '_where', fake_where)
    return box


def test_the_latest_ended_ok_execution_is_the_verified_one(executions):
    # attempt 2 beats attempt 1; between the two attempt-2 ENDED_OK rows the larger id
    # wins; the ENDED_ERROR rows (one of them at a higher attempt) are ignored
    executions['rows'] = _rows_of(_ex('e1', 1, 'ENDED_OK'), _ex('e2', 2, 'ENDED_OK'),
                                  _ex('e3', 2, 'ENDED_OK'), _ex('e9', 2, 'ENDED_ERROR'),
                                  _ex('e8', 3, 'ENDED_ERROR'))
    task = SimpleNamespace(id='t1')
    got = ver.verified_execution(object(), task)
    assert got.id == 'e3'
    assert executions['call'] == (entities.Execution, {'task_id': 't1'})


def test_no_ended_ok_execution_means_none(executions):
    executions['rows'] = _rows_of(_ex('e1', 1, 'ENDED_ERROR'), _ex('e2', 2, 'RUNNING'))
    assert ver.verified_execution(object(), SimpleNamespace(id='t1')) is None
    executions['rows'] = []
    assert ver.verified_execution(object(), SimpleNamespace(id='t1')) is None


# ── performed_by (87-93) ────────────────────────────────────────────────────

IDENTITY_KEYS = {'harness_id', 'account_id', 'account_ref', 'model', 'effort',
                 'route_decision_id', 'session_id'}


def test_performed_by_copies_the_identity_keys(monkeypatch):
    seen = []

    def fake_get(conn, cls, eid):
        seen.append((cls, eid))
        return SimpleNamespace(account_ref='acct-ref-1')

    monkeypatch.setattr(ver, '_get', fake_get)
    out = ver.performed_by(object(), _ex('e1', 1, 'ENDED_OK', route_decision_id='rd1'))
    assert set(out) == IDENTITY_KEYS
    assert out['account_ref'] == 'acct-ref-1'
    assert out['route_decision_id'] == 'rd1' and out['account_id'] == 'acct'
    assert seen == [(entities.RouteDecision, 'rd1')]


def test_a_missing_route_decision_row_gives_no_account_ref(monkeypatch):
    # the row must exist: _get answering None (line 91 `if rd is not None`) gives None,
    # not an AttributeError on the absent row
    monkeypatch.setattr(ver, '_get', lambda conn, cls, eid: None)
    out = ver.performed_by(object(), _ex('e1', 1, 'ENDED_OK', route_decision_id='rd1'))
    assert out['account_ref'] is None
    assert set(out) == IDENTITY_KEYS


def test_no_route_decision_reads_no_row(monkeypatch):
    # line 89: a falsy route_decision_id must not reach _get at all
    def boom(conn, cls, eid):
        raise AssertionError('no RouteDecision row is read without a route_decision_id')

    monkeypatch.setattr(ver, '_get', boom)
    out = ver.performed_by(object(), _ex('e1', 1, 'ENDED_OK', route_decision_id=None))
    assert out['account_ref'] is None
    assert out['route_decision_id'] is None


# ── _get and _where (96-104) ────────────────────────────────────────────────

@pytest.fixture
def db_rows(monkeypatch):
    calls = {'get': [], 'where': []}
    answers = {'get': None, 'where': []}

    def fake_get(conn, cls, eid):
        calls['get'].append((conn, cls, eid))
        return answers['get']

    def fake_where(conn, cls, **eq):
        calls['where'].append((conn, cls, eq))
        return answers['where']

    monkeypatch.setattr(rows, 'get', fake_get)
    monkeypatch.setattr(rows, 'where', fake_where)
    return SimpleNamespace(calls=calls, answers=answers)


def test_get_returns_the_entity_or_none(db_rows):
    conn = object()
    db_rows.answers['get'] = SimpleNamespace(entity='the-entity')
    assert ver._get(conn, entities.RouteDecision, 'rd1') == 'the-entity'
    db_rows.answers['get'] = None
    assert ver._get(conn, entities.RouteDecision, 'rd2') is None
    assert db_rows.calls['get'] == [(conn, entities.RouteDecision, 'rd1'),
                                    (conn, entities.RouteDecision, 'rd2')]


def test_where_forwards_the_filters(db_rows):
    conn = object()
    sentinel = ['row']
    db_rows.answers['where'] = sentinel
    got = ver._where(conn, entities.Execution, task_id='t1', attempt=2)
    assert got is sentinel
    assert db_rows.calls['where'] == [(conn, entities.Execution, {'task_id': 't1', 'attempt': 2})]
