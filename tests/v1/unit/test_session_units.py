"""P12 units (p12-design-gate §8, §12, §13.3): the checkpoint trigger table, the
renderer's redaction, caps and provenance, and the session adapters' argv —
the real ones built through `build_launch_command`, with no CLI installed."""

import pytest

from archeus.core.domain import entities, ids
from archeus.core.execution import checkpoint
from archeus.core.sessions import render
from archeus.harnesses.sessions import ClaudeCodeSessions, FakeSessions, PiSessions, SessionSpec

SECRET = 'sk-' + 'x' * 30


def _e(state, stop_reason=None):
    return entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                              mission_id=ids.new_id('mission'), state=state,
                              stop_reason=stop_reason, process_seq=1)


def test_the_trigger_of_every_end():
    assert checkpoint.trigger_of(_e('ENDED_OK')) == 'task_boundary'
    assert checkpoint.trigger_of(_e('ENDED_ERROR')) == 'failure'
    assert checkpoint.trigger_of(_e('ENDED_KILLED', 'user')) == 'failure'
    assert checkpoint.trigger_of(_e('ENDED_KILLED', 'pause_timeout')) == 'pause'
    for reason, trig in (('pressure', 'pressure'), ('limit', 'account_change'),
                         ('ceiling', 'account_change'), ('handoff_user', 'user')):
        assert checkpoint.trigger_of(_e('ENDED_HANDOFF', reason)) == trig
    assert not checkpoint.ran(_e('ABANDONED')) and not checkpoint.ran(_e('ENDED_REJECTED'))
    assert checkpoint.ran(_e('ENDED_KILLED'))


def _cp(**kw):
    base = dict(id=ids.new_id('checkpoint'), execution_id=ids.new_id('execution'),
                mission_id=ids.new_id('mission'), trigger='pressure', objective='o')
    return entities.Checkpoint(**dict(base, **kw))


def test_a_checkpoint_rendering_is_redacted_capped_and_says_where_it_came_from():
    text = render.checkpoint(_cp(decisions=('use %s' % SECRET,), open_problems=('x' * 20000,)))
    assert SECRET not in text and '[redacted]' in text
    assert len(text) <= render.CHECKPOINT_CAP + 100 and 'omitted' in text
    short = render.checkpoint(_cp())
    assert 'never from a transcript' in short and 'Next action' in short


def test_a_transcript_artifact_keeps_the_tail_and_leaves_the_rest_out():
    turns = [('user', 'turn %d' % i) for i in range(100)] + [('assistant', 'key ' + SECRET)]
    text = render.handoff({'id': 'ses_x', 'harness_id': 'fake_a'}, None, turns)
    assert 'turn 99' in text and 'turn 10\n' not in text
    assert SECRET not in text and 'tool calls, tool output and thinking were left out' in text


def test_a_brief_names_what_it_deliberately_leaves_out():
    b = {'session': {'id': 's', 'harness_id': 'h', 'model': None, 'last_seen_seq': 3},
         'as_of_seq': 9, 'mission': None, 'changes': {'groups': [], 'count': 0},
         'open_problems': [], 'missing': [], 'context': {'package_id': None}}
    text = render.brief(b)
    for thing in render.NOT_INCLUDED:
        assert thing in text


def test_the_fake_session_adapter_records_and_never_launches(archeus_home):
    a = FakeSessions('fake_a')
    got = a.launch_argv(SessionSpec('ses_1', '/w', model='fake-large', effort='high'))
    assert got.argv[:3] == ['fake-session', '--ref', got.ref] and a.locate(got.ref, None, '/w')
    resumed = a.launch_argv(SessionSpec('ses_1', '/w', resume_ref=got.ref, opening='read it'))
    assert resumed.ref == got.ref and resumed.argv[-1] == 'read it'


@pytest.fixture
def exes(monkeypatch):
    from claude_sessions import harnesses, launch
    monkeypatch.setattr(launch, 'get_claude_exe', lambda: 'claude.exe')
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: '%s.exe' % hid)


def test_claude_code_resumes_its_own_session_on_its_model_and_effort(exes, tmp_path):
    a = ClaudeCodeSessions()
    got = a.launch_argv(SessionSpec('ses_1', str(tmp_path), home=str(tmp_path / 'cfg'),
                                    model='opus', effort='high', resume_ref='abc-123'))
    argv = got.argv
    assert argv[0] == 'claude.exe' and argv[argv.index('-r') + 1] == 'abc-123'
    assert argv[argv.index('--model') + 1] == 'opus' and argv[argv.index('--effort') + 1] == 'high'
    assert got.env['CLAUDE_CONFIG_DIR'] == str(tmp_path / 'cfg')
    new = a.launch_argv(SessionSpec('ses_2', str(tmp_path), home=str(tmp_path / 'cfg'),
                                    opening='Read .archeus/sessions/ses_2.md'))
    assert new.ref and new.argv[new.argv.index('--session-id') + 1] == new.ref
    assert new.argv[-1] == 'Read .archeus/sessions/ses_2.md'


def test_pi_gets_pi_vocabulary_and_never_a_claude_model(exes, tmp_path):
    from claude_sessions import harnesses
    home = harnesses.home_dir('pi')
    got = PiSessions().launch_argv(SessionSpec('ses_1', str(tmp_path), home=home,
                                               model='claude-opus-5', effort='high',
                                               resume_ref='pi-sess'))
    assert got.argv[0] == 'pi.exe' and 'pi-sess' in got.argv
    assert 'claude-opus-5' not in got.argv                   # a bare Claude id is dropped
