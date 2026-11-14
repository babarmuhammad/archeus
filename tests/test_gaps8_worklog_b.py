"""T-1334 — capture_session in claude_sessions/worklog.py, lines 207-246.

Selected branches (highest risk first):
  1. :220-221  no summary and no files returns None, writes nothing and asks stats nothing
  2. :229-230  a headless call returns None and leaves an earlier episode for the same session alone
  3. :243-244  get_session_stats raising still records the entry, without stats keys
  4. :232-233  duration_s is set only when last is at or after first
  5. :241-242  tokens are recorded only when the in+out sum is non-zero
  6. :236-237  api_errors is stored as int when present and truthy, absent when zero
  7. :245 with :47-55  recapture of one session replaces its row; other rows keep their order
  8. :222-225, :225  entry carries session_id, UTC ended_at, summary, files and the merged marks
  9. :234-235  branch is stored only when stats report one (control)
 10. :49-50  PREMISE, strict xfail: a non-dict stored row makes add_entry raise and the new episode is lost

Seams: worklog.summarize_transcript, sessions.get_session_stats and stats._sum_usage are
monkeypatched. The store is a project under tmp_path. No transcript, stats cache or subprocess.
"""

import os
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import sessions, stats, worklog

UTC_FORMAT = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


@pytest.fixture
def stub(monkeypatch, tmp_path):
    state = {'summary': ('Fix loader', ['a/b.py'], {}), 'stats': {}, 'usage': {},
             'stats_calls': 0}

    def get_stats(path):
        state['stats_calls'] += 1
        if isinstance(state['stats'], Exception):
            raise state['stats']
        return dict(state['stats'])

    monkeypatch.setattr(worklog, 'summarize_transcript',
                        lambda transcript_path, root='': state['summary'])
    monkeypatch.setattr(sessions, 'get_session_stats', get_stats)
    monkeypatch.setattr(stats, '_sum_usage', lambda st: dict(state['usage']))
    proj = tmp_path / 'proj'
    proj.mkdir()
    return SimpleNamespace(proj=str(proj), tp=str(tmp_path / 's.jsonl'), state=state)


def _rows(stub):
    return worklog.load_worklog(stub.proj)


def test_no_summary_and_no_files_returns_none_and_touches_nothing(stub):
    stub.state['summary'] = ('', [], {})
    assert worklog.capture_session(stub.proj, 'sid', stub.tp) is None
    assert stub.state['stats_calls'] == 0
    assert not os.path.exists(worklog.worklog_path(stub.proj))


def test_headless_call_keeps_the_earlier_episode_for_its_session(stub):
    prior = {'session_id': 'sid', 'ended_at': '2026-11-01T10:00:00Z',
             'summary': 'real work', 'files': ['x.py']}
    worklog.add_entry(stub.proj, prior)
    stub.state['stats'] = {'headless': True}
    assert worklog.capture_session(stub.proj, 'sid', stub.tp) is None
    assert _rows(stub) == [prior]


def test_stats_miss_still_records_the_episode_without_stats_keys(stub):
    stub.state['stats'] = RuntimeError('stats cache unreadable')
    entry = worklog.capture_session(stub.proj, 'sid', stub.tp)
    assert entry is not None
    assert _rows(stub) == [entry]
    for key in ('duration_s', 'branch', 'api_errors', 'tokens'):
        assert key not in entry


def test_duration_is_stored_when_last_is_before_first_is_not(stub):
    stub.state['stats'] = {'first_ts': 100.0, 'last_ts': 40.0}
    assert 'duration_s' not in worklog.capture_session(stub.proj, 'a', stub.tp)
    stub.state['stats'] = {'first_ts': 100.0, 'last_ts': 100.0}
    assert worklog.capture_session(stub.proj, 'b', stub.tp)['duration_s'] == 0


def test_tokens_are_stored_only_when_nonzero(stub):
    stub.state['usage'] = {'in': 0, 'out': 0}
    assert 'tokens' not in worklog.capture_session(stub.proj, 'a', stub.tp)
    stub.state['usage'] = {'in': 3, 'out': 4}
    assert worklog.capture_session(stub.proj, 'b', stub.tp)['tokens'] == 7


def test_api_errors_is_an_int_when_truthy_and_absent_when_zero(stub):
    stub.state['stats'] = {'api_errors': '3'}
    entry = worklog.capture_session(stub.proj, 'a', stub.tp)
    assert entry['api_errors'] == 3 and type(entry['api_errors']) is int
    stub.state['stats'] = {'api_errors': 0}
    assert 'api_errors' not in worklog.capture_session(stub.proj, 'b', stub.tp)


def test_recapture_replaces_its_row_and_keeps_other_rows_in_order(stub):
    other = {'session_id': 'other', 'ended_at': '2026-11-01T10:00:00Z',
             'summary': 'other work', 'files': []}
    worklog.add_entry(stub.proj, other)
    worklog.capture_session(stub.proj, 'sid', stub.tp)
    stub.state['summary'] = ('second pass', ['c.py'], {})
    worklog.capture_session(stub.proj, 'sid', stub.tp)
    rows = _rows(stub)
    assert [r['session_id'] for r in rows] == ['other', 'sid']
    assert rows[-1]['summary'] == 'second pass'


def test_entry_carries_identity_time_summary_files_and_merged_marks(stub):
    stub.state['summary'] = ('Fix loader', ['a/b.py'],
                             {'tool_errors': 2, 'last_error': 'boom', 'outcome': 'error'})
    entry = worklog.capture_session(stub.proj, 'sid-1', stub.tp)
    assert entry['session_id'] == 'sid-1'
    assert UTC_FORMAT.match(entry['ended_at'])
    assert entry['summary'] == 'Fix loader'
    assert entry['files'] == ['a/b.py']
    assert (entry['tool_errors'], entry['last_error'], entry['outcome']) == (2, 'boom', 'error')
    assert _rows(stub) == [entry]


def test_branch_is_stored_only_when_stats_report_one(stub):
    stub.state['stats'] = {'branch': 'main'}
    assert worklog.capture_session(stub.proj, 'a', stub.tp)['branch'] == 'main'
    stub.state['stats'] = {}
    assert 'branch' not in worklog.capture_session(stub.proj, 'b', stub.tp)


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/worklog.py:50 add_entry calls e.get on every stored row, so a non-dict row "
    "raises AttributeError; capture_session (worklog.py:245) does not catch it and the new "
    "episode is never saved"))
def test_non_dict_stored_row_does_not_lose_the_new_episode(stub):
    worklog.save_worklog(stub.proj, ['not a dict'])
    entry = worklog.capture_session(stub.proj, 'sid', stub.tp)
    assert entry is not None
    saved = [r for r in _rows(stub) if isinstance(r, dict)]
    assert [r['session_id'] for r in saved] == ['sid']
