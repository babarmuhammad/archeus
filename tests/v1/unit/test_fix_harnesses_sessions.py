"""Regression tests for hostile-audit findings on archeus/harnesses/sessions.py."""

import os

from archeus.harnesses.sessions import ClaudeCodeSessions


def test_locating_a_claude_session_reads_none_of_its_transcript(tmp_path, monkeypatch):
    """T-652#F12/F3: locate scanned the whole transcript for a model no caller reads."""
    from claude_sessions import paths, store, transcripts
    home, cwd = str(tmp_path / 'home'), str(tmp_path / 'work')
    folder = store.project_folder(home, paths.encode_component(cwd))
    os.makedirs(folder)
    with open(os.path.join(folder, 'abc.jsonl'), 'w', encoding='utf-8') as f:
        f.write('{"message": {"model": "claude-opus-5"}}\n')

    def read(*a, **kw):
        raise AssertionError('the transcript was read')
    monkeypatch.setattr(transcripts, 'iter_json', read)
    got = ClaudeCodeSessions().locate('abc', home, cwd)
    assert got.transcript_path == os.path.join(folder, 'abc.jsonl')


def test_zero_turns_is_no_turns(tmp_path):
    """T-652#F4: out[-0:] is the whole list."""
    import json
    from archeus.harnesses.sessions import FakeSessions
    path = str(tmp_path / 't.jsonl')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'role': 'user', 'text': 'hi'}) + '\n')
    assert FakeSessions().turns(path, 1) == [('user', 'hi')]
    assert FakeSessions().turns(path, 0) == []


def test_the_fake_sessions_keep_to_what_the_real_readers_do(archeus_home):
    """T-652#F6/F7/F8: an empty ref is a new session; a non-object line is skipped; a
    directory named like a transcript is not one."""
    from archeus.harnesses.sessions import FakeSessions, SessionSpec
    fake = FakeSessions()
    got = fake.launch_argv(SessionSpec('ses_1', '.', resume_ref=''))
    assert fake.locate(got.ref, None, '.') is not None
    with open(fake.path(got.ref), 'a', encoding='utf-8') as f:
        f.write('123\n"hi"\n{"role": "user", "text": "ok"}\n')
    assert fake.turns(fake.path(got.ref), 5) == [('user', 'ok')]
    os.makedirs(fake.path('adir'))
    assert fake.locate('adir', None, '.') is None
