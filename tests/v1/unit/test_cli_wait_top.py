"""`archeus wait` and `archeus top --once` (T-1098): clients of the local Core only. The
Core is a fake: `_core_or_say` and `_get` answer, and every request is recorded."""

import ast
import inspect

import pytest

from archeus.cli import main as cli
from archeus.cli._api import endpoints


def _core(monkeypatch, *answers, up=True):
    """`_get` replays *answers* (a dict is Core's answer, a refusal dict has a `code`);
    the last one repeats."""
    got = []

    def fake(info, method, path, body=None, refusal=None):
        a = answers[min(len(got), len(answers) - 1)]
        got.append((method, path))
        if 'code' in a:
            if refusal is not None:
                refusal.update(a)
            return None
        return a

    monkeypatch.setattr(cli, '_core_or_say', lambda: {'port': 9001} if up else None)
    monkeypatch.setattr(cli, '_get', fake)
    return got


def _m(state):
    return {'id': 'msn_1', 'state': state, 'title': 'Add retry'}


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def _wait(argv):
    c = Clock()
    opts = cli._flags(argv[1:])
    return cli.wait(argv[0], opts.get('until'), opts.get('timeout', '60'),
                    sleep=c.sleep, clock=lambda: c.now), c


def test_a_state_reached_on_the_first_poll_prints_the_status_line_and_exits_0(monkeypatch, capsys):
    got = _core(monkeypatch, _m('COMPLETED'))
    code, c = _wait(['msn_1'])
    assert code == 0 and c.sleeps == []
    assert got == [('GET', endpoints.get_mission('msn_1'))]
    assert capsys.readouterr().out == 'msn_1: COMPLETED (Add retry)\n'


def test_it_polls_every_two_seconds_until_the_state_is_reached(monkeypatch):
    got = _core(monkeypatch, _m('EXECUTING'), _m('VERIFYING'), _m('COMPLETED'))
    code, c = _wait(['msn_1'])
    assert code == 0 and c.sleeps == [2, 2] and len(got) == 3


def test_a_wait_that_runs_out_of_time_exits_4(monkeypatch, capsys):
    _core(monkeypatch, _m('EXECUTING'))
    code, c = _wait(['msn_1', '--timeout', '5'])
    assert code == 4 and c.now >= 5
    assert 'timed out after 5s: msn_1 is still EXECUTING' in capsys.readouterr().err


def test_core_not_running_is_exit_1_and_asks_nothing(monkeypatch, capsys):
    got = _core(monkeypatch, _m('COMPLETED'), up=False)
    assert _wait(['msn_1'])[0] == 1 and got == []
    assert 'Core is not running' in capsys.readouterr().err


def test_core_going_away_mid_wait_is_exit_1(monkeypatch):
    _core(monkeypatch, _m('EXECUTING'), {'code': 'network', 'status': 0, 'detail': {}})
    assert _wait(['msn_1'])[0] == 1


@pytest.mark.parametrize('refusal', [{'code': 'unauthorized', 'status': 401, 'detail': {}},
                                     {'code': 'http_502', 'status': 502, 'detail': {}},
                                     {'code': 'network', 'status': 0, 'detail': {}},
                                     {'code': None}])
def test_a_core_that_refuses_or_drops_a_poll_is_asked_again_until_it_answers(refusal, monkeypatch):
    got = _core(monkeypatch, _m('EXECUTING'), refusal, _m('COMPLETED'))
    assert _wait(['msn_1'])[0] == 0 and len(got) == 3


@pytest.mark.parametrize('error', [ValueError('bad json'), TimeoutError('read')])
def test_an_unreadable_answer_is_asked_again(error, monkeypatch):
    answers = iter([error, _m('COMPLETED')])

    def fake(*a, **k):
        x = next(answers)
        if isinstance(x, Exception):
            raise x
        return x
    _core(monkeypatch)
    monkeypatch.setattr(cli, '_get', fake)
    assert _wait(['msn_1'])[0] == 0


def test_ctrl_c_ends_the_wait_with_130(monkeypatch):
    _core(monkeypatch, _m('EXECUTING'))

    def interrupt(_s):
        raise KeyboardInterrupt
    assert cli.wait('msn_1', sleep=interrupt, clock=lambda: 0.0) == 130


def test_the_last_sleep_stops_at_the_deadline(monkeypatch):
    _core(monkeypatch, _m('EXECUTING'))
    code, c = _wait(['msn_1', '--timeout', '3'])
    assert code == 4 and c.sleeps == [2, 1] and c.now == 3


def test_a_title_cannot_drive_the_terminal_and_any_title_survives_a_cp1252_pipe(monkeypatch):
    import io
    import sys
    out = io.TextIOWrapper(io.BytesIO(), encoding='cp1252', newline='')
    monkeypatch.setattr(sys, 'stdout', out)
    _core(monkeypatch, dict(_m('COMPLETED'),
                            title='Fix caf\u00e9 \u2713 \u4e2d\x1b]52;c;SGk=\x07\u202e'))
    assert cli.main(['wait', 'msn_1']) == 0
    out.flush()
    text = out.buffer.getvalue().decode('utf-8')
    assert text == 'msn_1: COMPLETED (Fix caf\u00e9 \u2713 \u4e2d)\n'


def test_an_unknown_mission_is_exit_2(monkeypatch):
    _core(monkeypatch, {'code': 'not_found', 'status': 404, 'detail': {}})
    assert _wait(['msn_gone'])[0] == 2


@pytest.mark.parametrize('argv', [['msn_1', '--until', 'DONE'], ['msn_1', '--until', 'COMPLETED,x'],
                                  ['msn_1', '--until', ''],
                                  ['msn_1', '--timeout', '0'], ['msn_1', '--timeout', 'soon']])
def test_a_bad_state_or_timeout_is_refused_before_any_request(argv, monkeypatch, capsys):
    got = _core(monkeypatch, _m('COMPLETED'))
    monkeypatch.setattr(cli, '_core_or_say', lambda: pytest.fail('Core was asked'))
    assert _wait(argv)[0] == 2 and got == []
    assert 'mission states' in capsys.readouterr().err


@pytest.mark.parametrize('state,until,code', [
    ('COMPLETED', None, 0), ('PAUSED', None, 0), ('APPROVAL_REQUIRED', None, 0),
    ('FAILED', None, 5), ('BLOCKED', None, 5), ('CANCELLED', None, 5),
    ('BLOCKED', 'COMPLETED,BLOCKED', 0), ('FAILED', 'failed', 0),
    ('CANCELLED', 'COMPLETED', 5)])
def test_the_exit_code_says_whether_the_state_was_wanted(state, until, code, monkeypatch):
    _core(monkeypatch, _m(state))
    opts = ['--until', until] if until else []
    assert _wait(['msn_1'] + opts)[0] == code


def test_a_state_that_is_not_listed_and_not_final_does_not_end_the_wait(monkeypatch):
    got = _core(monkeypatch, _m('FAILED'), _m('REPLANNING'), _m('COMPLETED'))
    assert _wait(['msn_1', '--until', 'COMPLETED'])[0] == 0 and len(got) == 3


def test_main_routes_wait_and_a_malformed_wait_is_usage(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(cli, 'wait', lambda *a: seen.append(a) or 0)
    assert cli.main(['wait', 'msn_1', '--until', 'COMPLETED', '--timeout', '9']) == 0
    assert seen == [('msn_1', 'COMPLETED', '9')]
    for argv in (['wait'], ['wait', 'msn_1', '--by', 'x'], ['wait', 'msn_1', '--until']):
        assert cli.main(argv) == 2
    assert 'archeus wait' in capsys.readouterr().err


def test_wait_and_top_only_read_and_never_touch_credentials_or_rotation():
    src = inspect.getsource(cli)
    fns = [ast.unparse(n) for n in ast.walk(ast.parse(src))
           if isinstance(n, ast.FunctionDef) and n.name in ('wait', 'top')]
    assert len(fns) == 2
    for body in fns:
        assert "'POST'" not in body and 'read_local_token' not in body
        assert not any(w in body for w in ('credentials', 'rotate'))
    imported = ' '.join(ast.unparse(n) for n in ast.walk(ast.parse(src))
                        if isinstance(n, (ast.Import, ast.ImportFrom)))
    assert not any(w in imported for w in ('claude_sessions', 'rotate', 'usage'))


# ── top ──

ROWS = {'by': 'account', 'rows': [
    {'account': 'account:abc', 'calls': 2, 'tokens_in': 150, 'tokens_out': 10, 'cache_read': None,
     'cache_write': 4, 'cost_usd': None, 'complete': True},
    {'account': None, 'calls': 1, 'tokens_in': None, 'tokens_out': None, 'cache_read': None,
     'cache_write': None, 'cost_usd': 0.25, 'complete': False}]}


def test_top_prints_one_table_with_dashes_for_what_nobody_reported(monkeypatch, capsys):
    got = _core(monkeypatch, ROWS)
    assert cli.main(['top', '--once']) == 0
    assert got == [('GET', endpoints.usage_by(by='account'))]
    head, a, none = capsys.readouterr().out.splitlines()
    assert head.split() == ['account', 'calls', 'tokens_in', 'tokens_out', 'cache_read',
                            'cache_write', 'cost_usd', 'complete']
    assert a.split() == ['account:abc', '2', '150', '10', '-', '4', '-', 'yes']
    assert none.split() == ['(none)', '1', '-', '-', '-', '-', '0.2500', 'no']


def test_top_by_mission_asks_for_missions_and_an_empty_ledger_says_so(monkeypatch, capsys):
    got = _core(monkeypatch, {'by': 'mission', 'rows': []})
    assert cli.main(['top', '--once', '--by', 'mission']) == 0
    assert got == [('GET', endpoints.usage_by(by='mission'))]
    assert capsys.readouterr().out.splitlines()[-1] == 'no usage recorded'


def test_top_without_core_is_exit_1_and_core_refusing_is_exit_2(monkeypatch):
    _core(monkeypatch, ROWS, up=False)
    assert cli.main(['top', '--once']) == 1
    _core(monkeypatch, {'code': 'invalid', 'status': 400, 'detail': {}})
    assert cli.main(['top', '--once', '--by', 'model']) == 2


@pytest.mark.parametrize('argv', [['top'], ['top', '--by', 'mission'], ['top', '--once', 'x'],
                                  ['top', '--once', '--for', 'x']])
def test_top_other_than_once_is_usage_and_asks_nothing(argv, monkeypatch, capsys):
    got = _core(monkeypatch, ROWS)
    assert cli.main(argv) == 2 and got == []
    assert 'archeus top' in capsys.readouterr().err
