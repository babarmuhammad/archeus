"""T-1333 — transcript summary and touched-file paths in claude_sessions/worklog.py, lines 97-205.

Selected branches (highest risk first):
  1. :176-181  a failed tool_result sets tool_errors and last_error, clipped to 120 characters
  2. :178      a later successful tool_result clears the trailing error, so outcome is not 'error'
  3. :156-160  the first good, non-headless user text is the summary; a headless text is skipped
  4. :149-151  non-dict rows are skipped and parsing continues with the next row
  5. :167-172  only Edit, Write, MultiEdit and NotebookEdit count; notebook_path counts; Read does not
  6. :152-153  an ai-title row wins over the first user message
  7. :182-184  newlines collapse to spaces; a summary over 120 characters is cut to 117 plus an ellipsis
  8. :109-113  a file outside root keeps only its basename; sibling prefix 'proj2' is not inside 'proj'
  9. :194-204  _err_text reads the first text block of a list and accepts plain string items
 10. :154-155  a role inside the message dict is honoured (control)

Seams: transcripts.iter_json is monkeypatched to yield synthetic record dicts, so no real
transcript is read. Paths are built under tmp_path; no file is written and no subprocess runs.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import transcripts, worklog
from claude_sessions.sessions import HEADLESS_MARK


@pytest.fixture
def feed(monkeypatch):
    rows = []
    monkeypatch.setattr(transcripts, 'iter_json', lambda *a, **k: iter(rows))
    return rows


def _summarize(tmp_path, root=None):
    return worklog.summarize_transcript(str(tmp_path / 't.jsonl'),
                                        str(root) if root is not None else '')


def _user(text):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


def _tool(name, key, value):
    return {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
        {'type': 'tool_use', 'name': name, 'input': {key: value}}]}}


def _result(content, error=False):
    block = {'type': 'tool_result', 'content': content}
    if error:
        block['is_error'] = True
    return {'type': 'user', 'message': {'role': 'user', 'content': [block]}}


def test_failed_tool_result_is_counted_and_last_error_clipped_to_120(feed, tmp_path):
    feed.extend([_user('Refactor the loader module'), _result('x' * 200, error=True)])
    summary, files, marks = _summarize(tmp_path)
    assert marks['tool_errors'] == 1
    assert marks['last_error'] == 'x' * 120
    assert marks['outcome'] == 'error'


def test_later_successful_result_clears_trailing_error(feed, tmp_path):
    feed.extend([
        _user('Refactor the loader module'),
        _tool('Edit', 'file_path', os.path.join(str(tmp_path), 'a.py')),
        _result('boom', error=True),
        _result('fine'),
    ])
    summary, files, marks = _summarize(tmp_path, tmp_path)
    assert marks['tool_errors'] == 1
    assert marks['last_error'] == 'boom'
    assert marks['outcome'] == 'ok'


def test_first_good_non_headless_user_text_is_summary(feed, tmp_path):
    feed.extend([
        _user(HEADLESS_MARK + '\nYou are building a knowledge graph of this project'),
        _user('You are building a knowledge graph of this project'),
        _user('Real task: fix the parser'),
        _user('A later request that must not win'),
    ])
    summary, _files, _marks = _summarize(tmp_path)
    assert summary == 'Real task: fix the parser'


def test_non_dict_rows_are_skipped_and_parsing_continues(feed, tmp_path):
    feed.extend(['junk', 42, None, ['list'], _user('Refactor the loader module')])
    summary, _files, _marks = _summarize(tmp_path)
    assert summary == 'Refactor the loader module'


def test_only_edit_tools_count_and_notebook_path_counts(feed, tmp_path):
    root = tmp_path / 'proj'
    feed.extend([
        _tool('Edit', 'file_path', str(root / 'src' / 'a.py')),
        _tool('Write', 'file_path', str(root / 'b.py')),
        _tool('MultiEdit', 'file_path', str(root / 'c.py')),
        _tool('NotebookEdit', 'notebook_path', str(root / 'nb' / 'n.ipynb')),
        _tool('Read', 'file_path', str(root / 'read_only.py')),
    ])
    summary, files, marks = _summarize(tmp_path, root)
    assert files == ['b.py', 'c.py', 'nb/n.ipynb', 'src/a.py']
    assert marks['outcome'] == 'ok'


def test_ai_title_wins_over_first_user_message(feed, tmp_path):
    feed.extend([
        _user('Fix the parser bug now'),
        {'type': 'ai-title', 'title': 'Parser fix'},
    ])
    summary, _files, _marks = _summarize(tmp_path)
    assert summary == 'Parser fix'


def test_summary_newlines_collapse_to_spaces(feed, tmp_path):
    feed.append({'type': 'ai-title', 'title': 'line one\nline two'})
    summary, _files, _marks = _summarize(tmp_path)
    assert summary == 'line one line two'


def test_summary_over_120_characters_is_cut_to_117_and_ellipsis(feed, tmp_path):
    feed.append({'type': 'ai-title', 'title': 'a' * 130})
    summary, _files, _marks = _summarize(tmp_path)
    assert summary == 'a' * 117 + '…'
    assert len(summary) == 118


def test_file_outside_root_keeps_basename_and_sibling_prefix_is_not_inside(feed, tmp_path):
    root = tmp_path / 'proj'
    feed.extend([
        _tool('Edit', 'file_path', str(root / 'src' / 'a.py')),
        _tool('Edit', 'file_path', str(tmp_path / 'proj2' / 'x.py')),
        _tool('Edit', 'file_path', str(tmp_path / 'elsewhere' / 'y.py')),
    ])
    summary, files, _marks = _summarize(tmp_path, root)
    assert files == ['src/a.py', 'x.py', 'y.py']


def test_err_text_reads_first_text_block_and_accepts_plain_strings():
    assert worklog._err_text([
        {'type': 'image', 'source': 'x'},
        {'type': 'text', 'text': '  boom\nhere '},
    ]) == 'boom here'
    assert worklog._err_text(['plain failure']) == 'plain failure'
    assert worklog._err_text([{'type': 'image'}]) == ''


def test_role_inside_message_dict_is_honoured(feed, tmp_path):
    feed.extend([
        {'type': 'assistant', 'message': {'role': 'assistant',
                                          'content': 'I will refactor the loader now'}},
        _user('Refactor the loader module'),
    ])
    summary, _files, _marks = _summarize(tmp_path)
    assert summary == 'Refactor the loader module'
