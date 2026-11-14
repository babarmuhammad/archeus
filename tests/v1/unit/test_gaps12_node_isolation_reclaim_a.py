"""T-1441: the containment fault record, the reclaim of released and quarantined profiles, the stale
scan and the confined run's record-then-teardown order in `archeus/node/isolation.py`, lines 1420-1518
(`_contained`, `_reclaim_entry`, `_reclaim_stale`, `stale`, `run_confined`).

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. isolation.py:1420-1430  _contained: an OSError returns False and notes one 'isolation_fault'; the same
                            text again notes nothing; a success clears the fault and returns the value;
                            a non-OSError propagates unchanged
 2. isolation.py:1433-1437  _reclaim_entry, released and absent: the id joins _released, False, no delete
 3. isolation.py:1438-1444  _reclaim_entry, released and present or unknown: reported as
                            'released_but_<presence>', handed to _unowned, no delete or release
 4. isolation.py:1445-1451  _reclaim_entry, not released: _close_job runs before the record is read; an
                            'invalid' record returns False without a delete
 5. isolation.py:1452-1457  _reclaim_entry: wait=EXIT_WAIT_S only when the Job was closed; anything but
                            'torn_down' returns False; 'torn_down' releases and returns True
 6. isolation.py:1459-1461  _reclaim_stale: teardown with reason 'stale'; True only for a truthy result
                            whose profile is 'torn_down'
 7. isolation.py:1467-1485  stale: a non-.json name is skipped; a name principal() rejects is reported
                            ('not_an_execution_id' or 'not_a_verifier_key') and not returned; a live id is
                            excluded and a dead id returned
 8. isolation.py:1470-1473  stale: FileNotFoundError on a listing skips that prefix; PermissionError
                            propagates
 9. isolation.py:1489-1517  run_confined: a record() that raises propagates with no teardown, and the key
                            leaves _confined; with established False a clean record gets no teardown
10. isolation.py:1512-1514  run_confined: record(result) runs before the 'verified' teardown, once, and the
                            result is returned

Closest existing tests: tests/v1/unit/test_confined_run.py, test_fx32_isolation_stop.py and
test_pins_node_isolation_1_650.py (plus the 650-1300, 1300-1850 and 1850-2254 pins). Nothing before this
file calls _contained, _reclaim_entry, _reclaim_stale or run_confined directly with fakes for each helper.

Seams: Isolation is built with object.__new__ and only the attributes these methods read; every helper
they call is a recording fake. isolation_dir() is monkeypatched to tmp_path. No Job Object, AppContainer,
Win32, subprocess, user config or network.
"""

import os
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.node import isolation

RESULT = {'verdict': 'pass'}


@pytest.fixture
def iso(tmp_path, monkeypatch):
    obj = object.__new__(isolation.Isolation)
    obj.faults, obj._released, obj._confined = {}, set(), set()
    obj.notes, obj.reports = [], []
    obj._note = obj.notes.append
    obj._report_invalid = lambda key, problem: obj.reports.append((key, problem))
    monkeypatch.setattr(isolation, 'isolation_dir', lambda: str(tmp_path / 'isolation'))
    return obj


def _no_record(execution_id):
    raise AssertionError('the record must not be read')


def test_contained_notes_an_os_error_once_and_clears_it_on_success(iso):
    def failing():
        raise OSError('disk gone')
    assert iso._contained('e1', failing) is False
    assert iso.notes == [{'op': 'isolation_fault', 'execution_id': 'e1', 'reason': 'disk gone'}]
    assert iso._contained('e1', failing) is False
    assert len(iso.notes) == 1
    assert iso.faults == {'e1': 'disk gone'}
    assert iso._contained('e1', lambda: True) is True
    assert iso.faults == {}


def test_contained_lets_other_errors_propagate_unrecorded(iso):
    def broken():
        raise ValueError('not a disk error')
    with pytest.raises(ValueError, match='not a disk error'):
        iso._contained('e1', broken)
    assert iso.notes == [] and iso.faults == {}


def test_released_and_absent_settles_without_a_delete(iso, monkeypatch):
    monkeypatch.setattr(iso, '_presence', lambda e: 'absent')
    monkeypatch.setattr(iso, 'record', _no_record)
    monkeypatch.setattr(iso, '_delete_profile', _no_record)
    assert iso._reclaim_entry('e1', 3, {'op': 'released'}) is False
    assert 'e1' in iso._released
    assert iso.reports == []


@pytest.mark.parametrize('presence', ['present', 'unknown'])
def test_released_but_not_absent_is_reported_and_kept(iso, monkeypatch, presence):
    unowned, deletes = [], []
    monkeypatch.setattr(iso, '_presence', lambda e: presence)
    monkeypatch.setattr(iso, 'record', lambda e: isolation.IsolationRecord(
        execution_id=e, profile='p', state='established'))
    monkeypatch.setattr(iso, '_unowned', lambda rec: unowned.append(rec.execution_id))
    monkeypatch.setattr(iso, '_delete_profile', lambda *a, **k: deletes.append(a))
    assert iso._reclaim_entry('e1', 4, {'op': 'released'}) is False
    assert iso.reports == [('quarantine.jsonl:4', 'released_but_' + presence)]
    assert unowned == ['e1']
    assert deletes == [] and 'e1' not in iso._released


def test_unreleased_closes_the_job_before_reading_and_keeps_an_invalid_record(iso, monkeypatch):
    log = []
    monkeypatch.setattr(iso, '_close_job', lambda e: log.append('close') or True)
    monkeypatch.setattr(iso, 'record', lambda e: log.append('record') or isolation.IsolationRecord(
        execution_id=e, profile='p', state='invalid'))
    monkeypatch.setattr(iso, '_delete_profile', lambda *a, **k: log.append('delete'))
    assert iso._reclaim_entry('e1', 5, {'op': 'quarantined'}) is False
    assert log == ['close', 'record']


@pytest.mark.parametrize('closed, wait', [(True, isolation.EXIT_WAIT_S), (False, 0)])
def test_reclaim_waits_for_exit_only_when_the_job_was_closed(iso, monkeypatch, closed, wait):
    calls = []
    monkeypatch.setattr(iso, '_close_job', lambda e: closed)
    monkeypatch.setattr(iso, 'record', lambda e: isolation.IsolationRecord(
        execution_id=e, profile='p', state='quarantined'))
    monkeypatch.setattr(iso, '_delete_profile', lambda rec, *, reason, wait=0: (
        calls.append((reason, wait)) or 'torn_down'))
    monkeypatch.setattr(iso, 'release', lambda e: calls.append(('release', e)))
    assert iso._reclaim_entry('e1', 6, {'op': 'quarantined'}) is True
    assert calls == [('reclaimed', wait), ('release', 'e1')]


@pytest.mark.parametrize('outcome, released', [('kept', False), ('torn_down', True)])
def test_reclaim_releases_only_on_torn_down(iso, monkeypatch, outcome, released):
    released_calls = []
    monkeypatch.setattr(iso, '_close_job', lambda e: False)
    monkeypatch.setattr(iso, 'record', lambda e: isolation.IsolationRecord(
        execution_id=e, profile='p', state='quarantined'))
    monkeypatch.setattr(iso, '_delete_profile', lambda rec, *, reason, wait=0: outcome)
    monkeypatch.setattr(iso, 'release', lambda e: released_calls.append(e))
    assert iso._reclaim_entry('e1', 7, {'op': 'quarantined'}) is released
    assert (released_calls == ['e1']) is released
    assert ('e1' in iso._released) is released


@pytest.mark.parametrize('out, expected', [
    (None, False),
    ({}, False),
    ({'profile': 'kept'}, False),
    ({'profile': 'torn_down'}, True),
])
def test_reclaim_stale_is_true_only_for_a_torn_down_profile(iso, monkeypatch, out, expected):
    calls = []
    monkeypatch.setattr(iso, 'teardown', lambda e, *, reason='': calls.append((e, reason)) or out)
    assert iso._reclaim_stale('e1') is expected
    assert calls == [('e1', 'stale')]


def test_stale_skips_non_json_reports_unprincipled_names_and_excludes_live(iso, tmp_path):
    root = tmp_path / 'isolation'
    root.mkdir()
    live, dead = ids.new_id('execution'), ids.new_id('execution')
    for name in (live + '.json', dead + '.json', 'bad name.json', 'notes.txt'):
        (root / name).write_text('{}', encoding='utf-8')
    (root / 'verify').mkdir()
    (root / 'verify' / 'not-a-verifier.json').write_text('{}', encoding='utf-8')
    found = iso.stale([live])
    assert found == [dead]
    assert ('bad name.json', 'not_an_execution_id') in iso.reports
    assert ('verify/not-a-verifier.json', 'not_a_verifier_key') in iso.reports
    assert all('notes.txt' not in key for key, _ in iso.reports)


def test_stale_skips_a_missing_listing_but_propagates_other_os_errors(iso, monkeypatch):
    def missing(path):
        raise FileNotFoundError(path)
    monkeypatch.setattr(isolation.os, 'listdir', missing)
    assert iso.stale() == []

    def denied(path):
        raise PermissionError(path)
    monkeypatch.setattr(isolation.os, 'listdir', denied)
    with pytest.raises(PermissionError):
        iso.stale()


def _request():
    return SimpleNamespace(execution_id='e1')


def _run(iso, record):
    return iso.run_confined(_request(), [], env={}, timeout=1, out_path='o', stdin_path='i',
                            record=record, keep=False)


def test_run_confined_record_failure_propagates_with_no_teardown(iso, monkeypatch):
    calls = []
    monkeypatch.setattr(iso, '_run_confined', lambda *a: (RESULT, True))
    monkeypatch.setattr(iso, 'teardown', lambda key, *, reason='': calls.append(reason))

    def record(result):
        raise ValueError('record refused')
    with pytest.raises(ValueError, match='record refused'):
        _run(iso, record)
    assert calls == [] and 'e1' not in iso._confined


def test_run_confined_tears_down_only_when_established(iso, monkeypatch):
    calls, recorded = [], []
    monkeypatch.setattr(iso, '_run_confined', lambda *a: (RESULT, False))
    monkeypatch.setattr(iso, 'teardown', lambda key, *, reason='': calls.append(reason))
    assert _run(iso, recorded.append) == RESULT
    assert recorded == [RESULT] and calls == [] and 'e1' not in iso._confined


def test_run_confined_records_before_the_verified_teardown(iso, monkeypatch):
    log = []
    monkeypatch.setattr(iso, '_run_confined', lambda *a: (RESULT, True))
    monkeypatch.setattr(iso, 'teardown',
                        lambda key, *, reason='': log.append(('teardown', key, reason)))
    assert _run(iso, lambda result: log.append(('record', result))) == RESULT
    assert log == [('record', RESULT), ('teardown', 'e1', 'verified')]
    assert 'e1' not in iso._confined
