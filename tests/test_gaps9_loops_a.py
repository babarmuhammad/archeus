"""T-1350 · highest-risk test gaps in claude_sessions/loops.py 284-344.

Slice: `_interval_minutes`, `_runner_argv`, `_quote_win`, `schedule` and
`unschedule` (284-344) at tip 10d688c0, checked against worktree 2031f32a.

Candidate branches, ranked (denial and fail-closed first, then boundaries, then
error paths). Each entry: file:line, closest existing test, what that test misses.

 1. 328-330 — a refused `schtasks /create` is (False, stderr[:200]); a None
    result is (False, 'schtasks failed'). Closest: test_loops.py
    test_windows_registers_a_task_with_no_stored_password, success path only.
 2. 341-342 — Windows unschedule with no schtasks answer is (False, ...).
    Closest: none; test_loops.py only covers the POSIX unschedule.
 3. 338-340 — Windows unschedule argv is exactly /delete /tn <task> /f.
    Closest: test_gaps3_claude_sessions_migrate_b.py asserts only that a
    /delete happened, not its argv.
 4. 299-302 — pythonw substitution needs WINDOWS and an existing pythonw.exe.
    Closest: none.
 5. 304-305 — --cfgdir only when cfgdir is truthy. Closest: the truthy case in
    test_windows_registers_...; the falsy case is not asserted.
 6. 309-310 — _quote_win quotes only arguments containing a space.
    Closest: none directly.
 7. 287-289 — an unparseable interval ('soon', None) schedules hourly.
    Closest: test_loops.py test_the_interval_becomes_a_schedule..., which checks
    only '' at the minutes level and never the schedule argv.
 8. 291-292 — the floor for '0m' is one minute. Closest: test_loops.py checks
    '30s' and '999d' but not '0m'.
 9. 321-326 — schedule shape for daily, hourly with /mo, and minute with /mo.
    Closest: test_an_hourly_interval_is_scheduled_hourly checks /sc only.
10. 327-328 — /tr carries the cfgdir argument quoted when it contains a space.
    Closest: test_windows_registers_... asserts '--cfgdir' only.

Premise dropped, not xfailed: 336-337 (unschedule on Windows reports removal
after any non-zero `schtasks /delete`). The docstring pins it on purpose:
"Reporting success when it was already gone is correct: the caller asked for it
not to fire again." A non-zero delete is the already-gone case, so the probe is
not a defect as stated. Not probed here: a delete that fails while the task is
still present would need a query after the delete, which the source never makes.

Seams: loops.proc.run (recorder), loops.proc.WINDOWS, sys.executable pointed at
tmp_path. No schtasks, no crontab, no subprocess.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import loops


class _R:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _interpreter_without_pythonw(monkeypatch, tmp_path):
    exe = tmp_path / 'Scripts' / 'python.exe'
    exe.parent.mkdir()
    exe.write_bytes(b'')
    monkeypatch.setattr(sys, 'executable', str(exe))


@pytest.fixture
def schtasks(monkeypatch):
    calls = []
    answer = {'r': _R(0)}

    def fake(argv, **kw):
        calls.append(list(argv))
        return answer['r']
    monkeypatch.setattr(loops.proc, 'WINDOWS', True)
    monkeypatch.setattr(loops.proc, 'run', fake)
    return calls, answer


def _sched_args(argv):
    return argv[argv.index('/sc'):]


def test_a_refused_create_reports_failure_with_bounded_stderr(schtasks, monkeypatch):
    calls, answer = schtasks
    answer['r'] = _R(1, stderr='x' * 500)
    ok, msg = loops.schedule('abc123', '15m', '')
    assert ok is False
    assert msg == 'x' * 200, 'stderr is not trimmed to 200 characters'

    answer['r'] = None
    assert loops.schedule('abc123', '15m', '') == (False, 'schtasks failed')


def test_windows_unschedule_without_a_schtasks_answer_is_refused(schtasks):
    calls, answer = schtasks
    answer['r'] = None
    assert loops.unschedule('abc123') == (False, 'schtasks not available')


def test_windows_unschedule_deletes_only_this_loops_task(schtasks):
    calls, answer = schtasks
    assert loops.unschedule('abc123') == (True, 'Removed from Task Scheduler')
    assert calls == [['schtasks', '/delete', '/tn', 'archeus-loop-abc123', '/f']]


def test_pythonw_runs_the_loop_only_on_windows_with_pythonw_present(monkeypatch, tmp_path):
    exe_dir = tmp_path / 'Python Install'
    exe_dir.mkdir()
    py = exe_dir / 'python.exe'
    pyw = exe_dir / 'pythonw.exe'
    py.write_bytes(b'')
    pyw.write_bytes(b'')
    monkeypatch.setattr(sys, 'executable', str(py))

    monkeypatch.setattr(loops.proc, 'WINDOWS', True)
    assert loops._runner_argv('abc123', '')[0] == str(pyw)

    monkeypatch.setattr(loops.proc, 'WINDOWS', False)
    assert loops._runner_argv('abc123', '')[0] == str(py), 'pythonw used off Windows'

    monkeypatch.setattr(loops.proc, 'WINDOWS', True)
    pyw.unlink()
    assert loops._runner_argv('abc123', '')[0] == str(py), 'a missing pythonw was named'


def test_no_cfgdir_argument_when_the_cfgdir_is_empty_or_none(monkeypatch):
    monkeypatch.setattr(loops.proc, 'WINDOWS', True)
    base = [sys.executable, '-m', 'claude_sessions', '--loop-run', 'abc123']
    assert loops._runner_argv('abc123', '') == base
    assert loops._runner_argv('abc123', None) == base


def test_only_arguments_with_a_space_are_quoted_on_windows():
    assert loops._quote_win(['py', '-m', 'claude_sessions', 'abc123']) == \
        'py -m claude_sessions abc123'
    assert loops._quote_win(['C:/Program Files/py.exe', '--loop-run']) == \
        '"C:/Program Files/py.exe" --loop-run'


def test_an_unparseable_interval_schedules_hourly(schtasks):
    calls, _ = schtasks
    loops.schedule('abc123', 'soon', '')
    loops.schedule('abc123', None, '')
    assert [_sched_args(c) for c in calls] == [
        ['/sc', 'hourly', '/mo', '1'], ['/sc', 'hourly', '/mo', '1']]


def test_zero_and_sub_minute_intervals_floor_to_one_minute_and_the_cap_holds(schtasks):
    calls, _ = schtasks
    loops.schedule('abc123', '0m', '')
    loops.schedule('abc123', '30s', '')
    loops.schedule('abc123', '999d', '')
    assert [_sched_args(c) for c in calls] == [
        ['/sc', 'minute', '/mo', '1'],
        ['/sc', 'minute', '/mo', '1'],
        ['/sc', 'daily', '/mo', '7'],
    ]


def test_schedule_shape_follows_the_interval_unit(schtasks):
    calls, _ = schtasks
    for interval in ('1d', '2d', '120m', '90m'):
        loops.schedule('abc123', interval, '')
    assert [_sched_args(c) for c in calls] == [
        ['/sc', 'daily', '/mo', '1'],
        ['/sc', 'daily', '/mo', '2'],
        ['/sc', 'hourly', '/mo', '2'],
        ['/sc', 'minute', '/mo', '90'],
    ]


def test_a_cfgdir_with_a_space_is_quoted_inside_the_task_command(schtasks):
    calls, _ = schtasks
    loops.schedule('abc123', '15m', 'C:/My Accounts/work')
    tr = calls[0][calls[0].index('/tr') + 1]
    assert tr.endswith('--loop-run abc123 --cfgdir "C:/My Accounts/work"'), tr
    assert '/f' in calls[0] and '/ru' not in calls[0]
