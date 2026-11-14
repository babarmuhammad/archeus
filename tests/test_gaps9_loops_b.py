"""T-1351 · highest-risk test gaps in claude_sessions/loops.py 347-379.

Slice: `is_scheduled` (347-352), `_cron_tag` and `_cron_write` (355-379) at tip
10d688c0, checked against worktree 2031f32a.

Candidate branches, ranked (denial and fail-closed first, then boundaries, then
error paths). Each entry: file:line, closest existing test, what that test misses.

 1. 369 — PREMISE, strict xfail: the tag test is a substring test, so unscheduling
    loop '1' also removes the line of loop '12'. Closest: test_loops.py
    test_posix_rewrites_the_crontab_and_keeps_everyone_elses_lines, which uses one id.
 2. 365-367 — `crontab -l` unavailable returns (False, ...) and writes nothing.
    Closest: none for the cron path (test_gaps3 covers the is_scheduled guard in migrate).
 3. 368-369 — foreign lines, including comments and an own-looking line for
    another loop, pass through verbatim and in order; our old line is replaced.
    Closest: test_loops.py and test_migration.py assert only that a foreign line
    survives, not order or position.
 4. 370 — argv None (unschedule) adds no line and returns 'Removed from cron'.
    Closest: test_loops.py checks the line is gone, not the message or the absence of a new line.
 5. 371-373 — spec boundaries: 59 min '*/59', 60 min '0 */1', 1440 min '0 3 */1'.
    Closest: test_loops.py checks '*/15 * * * *' only.
 6. 375 — an empty remaining tab writes a single newline.
    Closest: none.
 7. 376-378 — `crontab -` failure is (False, stderr[:200]); None is 'crontab failed'.
    Closest: test_gaps3 covers the migrate caller only, not the message.
 8. 350-352 — is_scheduled on cron: non-zero `crontab -l` is False even when the tag is in stdout.
    Closest: none.
 9. 347-350 — is_scheduled on Windows is True only for schtasks /query returncode 0.
    Closest: test_gaps3 and test_migration fake /query returning None or a non-query path only.
10. 379 — success text is 'Scheduled every N min' for argv and 'Removed from cron' otherwise.
    Closest: test_loops.py asserts ok only, never the message.

Seams: loops.proc.run (recorder: `crontab -l` returns synthetic text, `crontab -`
records stdin, `schtasks /query` returns a fake result), loops.proc.WINDOWS.
No real crontab, no schtasks, no subprocess.
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


class _Tab:
    def __init__(self, monkeypatch, text='', listing=None):
        self.text = text
        self.listing = listing
        self.writes = []
        self.write_result = _R(0)
        self.calls = []
        monkeypatch.setattr(loops.proc, 'WINDOWS', False)
        monkeypatch.setattr(loops.proc, 'run', self._run)

    def _run(self, argv, **kw):
        self.calls.append(list(argv))
        if argv == ['crontab', '-l']:
            return self.listing if self.listing is not None else _R(0, self.text)
        if argv == ['crontab', '-']:
            self.writes.append(kw.get('stdin'))
            return self.write_result
        raise AssertionError('unexpected call: %r' % (argv,))


@pytest.fixture(autouse=True)
def _interpreter(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'python'))


def test_removing_loop_one_leaves_loop_twelve_alone(monkeypatch):
    tab = _Tab(monkeypatch,
               '*/15 * * * * one # archeus-loop-1\n'
               '*/15 * * * * two # archeus-loop-12\n')
    loops.unschedule('1')
    assert tab.writes and '# archeus-loop-12' in tab.writes[0], \
        'loop 12 was unscheduled with loop 1'


def test_no_crontab_listing_means_refusal_and_no_write(monkeypatch):
    tab = _Tab(monkeypatch)
    monkeypatch.setattr(loops.proc, 'run',
                        lambda argv, **kw: None if argv == ['crontab', '-l'] else tab._run(argv, **kw))
    ok, msg = loops.schedule('abc123', '15m', '')
    assert ok is False and msg
    assert loops.unschedule('abc123')[0] is False
    assert tab.writes == [], 'a crontab was written without reading it'


def test_foreign_lines_survive_verbatim_and_in_order(monkeypatch):
    tab = _Tab(monkeypatch,
               'SHELL=/bin/sh\n'
               '# nightly housekeeping\n'
               '0 4 * * * backup.sh --all\n'
               '*/5 * * * * probe.sh # archeus-loop-abc123\n'
               '0 1 * * * sync.sh # archeus-note\n')
    ok, _ = loops.schedule('abc123', '15m', '')
    assert ok
    lines = tab.writes[0].splitlines()
    assert lines[:4] == ['SHELL=/bin/sh', '# nightly housekeeping',
                         '0 4 * * * backup.sh --all', '0 1 * * * sync.sh # archeus-note']
    assert len(lines) == 5, 'the old line for this loop was kept'
    assert lines[4].endswith('# archeus-loop-abc123')
    assert lines[4].startswith('*/15 * * * * ')


def test_unschedule_adds_no_line_and_says_removed_from_cron(monkeypatch):
    tab = _Tab(monkeypatch, 'keep me\n*/15 * * * * run # archeus-loop-abc123\n')
    assert loops.unschedule('abc123') == (True, 'Removed from cron')
    assert tab.writes[0] == 'keep me\n'


def test_the_spec_changes_at_the_minute_and_day_boundaries(monkeypatch):
    tab = _Tab(monkeypatch)
    for interval in ('59m', '60m', '1440m'):
        loops.schedule('abc123', interval, '')
    specs = [' '.join(w.splitlines()[-1].split()[:5]) for w in tab.writes]
    assert specs == ['*/59 * * * *', '0 */1 * * *', '0 3 */1 * *'], specs


def test_an_empty_remaining_crontab_is_one_newline_not_a_blank_tail(monkeypatch):
    tab = _Tab(monkeypatch, '*/15 * * * * run # archeus-loop-abc123\n')
    loops.unschedule('abc123')
    assert tab.writes == ['\n']


def test_a_failed_crontab_write_is_refused_with_bounded_stderr(monkeypatch):
    tab = _Tab(monkeypatch, '0 9 * * * backup.sh\n')
    tab.write_result = _R(1, stderr='y' * 300)
    assert loops.schedule('abc123', '15m', '') == (False, 'y' * 200)

    tab.write_result = None
    assert loops.schedule('abc123', '15m', '') == (False, 'crontab failed')


def test_a_non_zero_crontab_listing_means_not_scheduled_even_with_the_tag(monkeypatch):
    _Tab(monkeypatch, listing=_R(1, stdout='*/15 * * * * run # archeus-loop-abc123\n'))
    assert loops.is_scheduled('abc123') is False


def test_windows_is_scheduled_only_when_schtasks_query_returns_zero(monkeypatch):
    answers = []
    monkeypatch.setattr(loops.proc, 'WINDOWS', True)
    monkeypatch.setattr(loops.proc, 'run', lambda argv, **kw: answers.pop(0))
    answers[:] = [_R(0)]
    assert loops.is_scheduled('abc123') is True
    answers[:] = [_R(1)]
    assert loops.is_scheduled('abc123') is False
    answers[:] = [None]
    assert loops.is_scheduled('abc123') is False


def test_the_success_text_names_the_interval_only_when_scheduling(monkeypatch):
    _Tab(monkeypatch)
    assert loops.schedule('abc123', '15m', '') == (True, 'Scheduled every 15 min')
    assert loops.unschedule('abc123') == (True, 'Removed from cron')
