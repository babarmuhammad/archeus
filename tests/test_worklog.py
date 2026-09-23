"""Recent-work memory: heuristic capture, bounded ring buffer, digest budget,
and the hook installer round-trip.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox
from claude_sessions import worklog, hooks


def _transcript(path, title='', first_user='do the thing', edits=('a.py', 'b.py')):
    """A transcript in the shape Claude Code ACTUALLY writes.

    The fixture used to emit `{'role': 'user', 'content': …}` — a shape Claude
    Code has never produced — so `summarize_transcript`'s user-message test was
    green here and false on every real file. Every entry in this repo's own
    worklog.json had an empty summary as a result. The record below is the real
    one: `type` at the top level and `role`/`content` nested under `message`.
    """
    lines = []
    if title:
        lines.append({'type': 'ai-title', 'title': title})
    if first_user:
        lines.append({'type': 'user',
                      'message': {'role': 'user', 'content': first_user}})
    content = [{'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': f}}
               for f in edits]
    lines.append({'type': 'assistant', 'message': {'role': 'assistant', 'content': content}})
    with open(path, 'w', encoding='utf-8') as f:
        for o in lines:
            f.write(json.dumps(o) + '\n')


def test_summarize_transcript(tmp_path):
    tp = tmp_path / 's.jsonl'
    _transcript(str(tp), title='Add auth flow', edits=('login.py', 'auth.py'))
    summary, files, _marks = worklog.summarize_transcript(str(tp))
    assert summary == 'Add auth flow'
    assert files == ['auth.py', 'login.py']


def test_an_episode_from_a_real_transcript_has_a_task_and_files(tmp_path):
    """The amnesia test, against the record shape production emits.

    This is the one that failed before the fixture was corrected: a nested
    `message.content` returned no summary at all.
    """
    tp = tmp_path / 's.jsonl'
    _transcript(str(tp), title='', first_user='fix the parser bug',
                edits=('login.py',))
    summary, files, _marks = worklog.summarize_transcript(str(tp))
    assert summary == 'fix the parser bug'
    assert files == ['login.py']


def test_the_task_is_the_first_message_not_the_last(tmp_path):
    """`_parse_session` keeps the LAST good user message as a row's preview.
    An episode wants the task, and the task is what you opened with."""
    tp = tmp_path / 's.jsonl'
    with open(tp, 'w', encoding='utf-8') as f:
        for text in ('add a login page', 'now also add logout'):
            f.write(json.dumps({'type': 'user',
                                'message': {'role': 'user', 'content': text}}) + '\n')
    assert worklog.summarize_transcript(str(tp))[0] == 'add a login page'


def test_archeus_own_prompts_are_not_the_task(tmp_path):
    """A headless call archeus made is not work the user did."""
    from claude_sessions import sessions
    tp = tmp_path / 's.jsonl'
    with open(tp, 'w', encoding='utf-8') as f:
        for text in (sessions.HEADLESS_MARK + ' extract entities from this module',
                     'rename the config loader'):
            f.write(json.dumps({'type': 'user',
                                'message': {'role': 'user', 'content': text}}) + '\n')
    assert worklog.summarize_transcript(str(tp))[0] == 'rename the config loader'


def test_a_touched_file_keeps_its_module(tmp_path):
    """A basename has no module in it, and the module is what `recall` scores
    a path on — so storing basenames threw the signal away before the episode
    was written."""
    proj = tmp_path / 'proj'
    (proj / 'claude_sessions').mkdir(parents=True)
    tp = tmp_path / 's.jsonl'
    _transcript(str(tp), title='t',
                edits=(str(proj / 'claude_sessions' / 'recall.py'),))
    assert worklog.summarize_transcript(str(tp), str(proj))[1] == \
        ['claude_sessions/recall.py']
    # outside the project it degrades to the basename rather than leaking an
    # absolute path into a file that gets injected into a prompt
    assert worklog.summarize_transcript(str(tp), str(tmp_path / 'other'))[1] == \
        ['recall.py']


def test_capture_and_ring_buffer(tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    # write more than CAP sessions
    for i in range(worklog.CAP + 4):
        tp = tmp_path / f's{i}.jsonl'
        _transcript(str(tp), title=f'session {i}', edits=(f'f{i}.py',))
        worklog.capture_session(str(proj), f'sid-{i}', str(tp))
    entries = worklog.load_worklog(str(proj))
    assert len(entries) == worklog.CAP                  # trimmed
    assert entries[-1]['summary'] == f'session {worklog.CAP + 3}'  # newest kept


def test_capture_dedups_by_session(tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    tp = tmp_path / 's.jsonl'
    _transcript(str(tp), title='first', edits=('a.py',))
    worklog.capture_session(str(proj), 'same-sid', str(tp))
    _transcript(str(tp), title='second', edits=('b.py',))
    worklog.capture_session(str(proj), 'same-sid', str(tp))
    entries = worklog.load_worklog(str(proj))
    assert len(entries) == 1 and entries[0]['summary'] == 'second'


def test_capture_skips_empty(tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    tp = tmp_path / 'e.jsonl'
    _transcript(str(tp), title='', first_user='', edits=())
    assert worklog.capture_session(str(proj), 'sid', str(tp)) is None
    assert worklog.load_worklog(str(proj)) == []


def test_render_digest_budget(tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    for i in range(6):
        worklog.add_entry(str(proj), {'session_id': f's{i}',
                                      'ended_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                                      'summary': f'work {i}', 'files': ['x.py']})
    dig = worklog.render_digest(str(proj))
    assert dig.startswith('## Recent work')
    assert 'work 5' in dig                              # newest first
    assert len(dig) <= worklog.DIGEST_BUDGET + 80       # within budget (+header)


def test_render_digest_empty(tmp_path):
    assert worklog.render_digest(str(tmp_path)) == ''


def test_worklog_hook_install_roundtrip(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(hooks, 'settings_path', str(tmp_path / 'settings.json'))
    assert not hooks.worklog_hook_installed()
    assert hooks.install_worklog_hook()
    assert hooks.worklog_hook_installed()
    # both events registered
    d = json.load(open(tmp_path / 'settings.json', encoding='utf-8'))
    # SessionEnd, not Stop: Stop fires every turn and re-streams the whole
    # transcript for a capture that only needs to happen once.
    assert 'SessionStart' in d['hooks'] and 'SessionEnd' in d['hooks']
    assert 'Stop' not in d['hooks']
    # idempotent
    hooks.install_worklog_hook()
    assert hooks.worklog_hook_installed()
    # uninstall
    assert hooks.uninstall_worklog_hook()
    assert not hooks.worklog_hook_installed()


# ── what an episode records beyond "it happened" ─────────────

def _rec(kind, **kw):
    return {'type': kind, 'message': {'role': kw.pop('role', 'assistant'), **kw}}


def _with_result(path, *blocks):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'type': 'ai-title', 'title': 'do a thing'}) + '\n')
        f.write(json.dumps({'type': 'assistant',
                            'message': {'role': 'assistant',
                                        'content': list(blocks)}}) + '\n')


def test_an_episode_records_what_failed(tmp_path):
    """A log of what was DONE cannot stop the next session walking into the
    same wall. What went wrong is the half worth the characters."""
    tp = tmp_path / 's.jsonl'
    _with_result(str(tp),
                 {'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'a.py'}},
                 {'type': 'tool_result', 'is_error': True,
                  'content': 'ModuleNotFoundError: no module named yaml'},
                 {'type': 'tool_result', 'is_error': False, 'content': 'ok'})
    _s, _f, marks = worklog.summarize_transcript(str(tp))
    assert marks['tool_errors'] == 1
    assert 'ModuleNotFoundError' in marks['last_error']
    # the LAST result succeeded, and something was edited
    assert marks['outcome'] == 'ok'


def test_a_session_that_ended_on_an_error_says_so(tmp_path):
    tp = tmp_path / 's.jsonl'
    _with_result(str(tp),
                 {'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'a.py'}},
                 {'type': 'tool_result', 'is_error': True, 'content': 'boom'})
    assert worklog.summarize_transcript(str(tp))[2]['outcome'] == 'error'


def test_the_error_text_survives_either_block_shape(tmp_path):
    tp = tmp_path / 's.jsonl'
    _with_result(str(tp), {'type': 'tool_result', 'is_error': True,
                           'content': [{'type': 'text', 'text': 'nested boom'}]})
    assert 'nested boom' in worklog.summarize_transcript(str(tp))[2]['last_error']


def test_the_sessionstart_digest_carries_what_failed_last_time(tmp_path):
    """The continuity test. A digest that only lists topics is a table of
    contents; the next session needs the dead end."""
    proj = tmp_path / 'proj'
    proj.mkdir()
    worklog.add_entry(str(proj), {
        'session_id': 's1', 'ended_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'summary': 'wire the parser', 'files': ['p.py'],
        'outcome': 'error', 'tool_errors': 2, 'last_error': 'boom'})
    dig = worklog.render_digest(str(proj))
    assert 'ended on an error' in dig and '2 failed' in dig


def test_an_episode_past_its_ttl_is_forgotten(tmp_path):
    """The staleness test. The ring cap bounds a busy project; the TTL is what
    expires an episode on one that went quiet, which is where nothing else
    would ever trim it."""
    import time as _t
    proj = tmp_path / 'proj'
    proj.mkdir()
    old = _t.strftime('%Y-%m-%dT%H:%M:%SZ',
                      _t.gmtime(_t.time() - (worklog.TTL_DAYS + 5) * 86400))
    new = _t.strftime('%Y-%m-%dT%H:%M:%SZ', _t.gmtime())
    worklog.save_worklog(str(proj), [
        {'session_id': 'old', 'ended_at': old, 'summary': 'ancient'},
        {'session_id': 'new', 'ended_at': new, 'summary': 'recent'},
        {'session_id': 'undated', 'summary': 'written before the field existed'}])
    assert worklog.apply_ttl(str(proj)) == 1
    kept = {e['session_id'] for e in worklog.load_worklog(str(proj))}
    # an undated entry predates the field; that is not the same as being old
    assert kept == {'new', 'undated'}


def test_a_headless_call_is_not_an_episode(tmp_path):
    """archeus's own `claude -p` calls are it talking to itself. They used to
    be captured as work the user did."""
    from claude_sessions import sessions
    proj = tmp_path / 'proj'
    proj.mkdir()
    tp = tmp_path / 'h.jsonl'
    _transcript(str(tp), title='extract entities', edits=('x.py',))
    monkey = sessions.get_session_stats
    try:
        sessions.get_session_stats = lambda p: {'headless': True}
        assert worklog.capture_session(str(proj), 'sid', str(tp)) is None
    finally:
        sessions.get_session_stats = monkey
    assert worklog.load_worklog(str(proj)) == []
