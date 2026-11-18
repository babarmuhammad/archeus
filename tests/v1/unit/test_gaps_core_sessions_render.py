"""T-743: the highest-risk uncovered branches of archeus/core/sessions/render.py.

Fail-closed and containment first: a mission-linked hand-off is handed current
state and NEVER a transcript, even when turns are passed with it (ADR-0004);
only the exact role 'user' speaks as the user, every other role renders as
Assistant so a spoofed '### System' header can never reach the target; pending
approvals are shown with the information-only framing and the section is never
fabricated when empty; redaction runs on every rendering path, including the
one that returns uncapped text; a lost mission is reported and never filled
in. Then the boundary values (cap at exactly N and N+1, the 40-turn window at
40 and 41, the execution parenthetical, the checkpoint's explicit '(none)'
defaults) and the error paths (truncation disclosed, a malformed context that
would make the provenance footer lie is refused loudly).

Style and fixtures copied from the module's own units, tests/v1/unit/test_session_units.py:
direct dict seeds shaped exactly as continuity.brief / continuity.handoff_state
build them, a `checkpoint(...)`-style `_cp` factory, no database, no process,
no OS call, no clock. Pure string in, pure string out.
"""

import pytest

from archeus.core.domain import entities, ids
from archeus.core.sessions import render

SECRET = 'sk-' + 'q' * 30
SRC = {'id': 'ses_src', 'harness_id': 'fake_a'}


def _cp(**kw):
    base = dict(id=ids.new_id('checkpoint'), execution_id=ids.new_id('execution'),
                mission_id=ids.new_id('mission'), task_id=ids.new_id('task'),
                trigger='pressure', objective='o', plan_version=2, as_of_seq=5,
                next_action='push on')
    return entities.Checkpoint(**dict(base, **kw))


def _task(key='T1', title='do it', state='ENDED_OK', execution=None):
    return {'id': 'tk_' + key, 'key': key, 'title': title, 'state': state,
            'execution': execution}


def _mission(**kw):
    m = {'id': 'mis_1', 'title': 'ship it', 'state': 'ACTIVE', 'plan_version': 2,
         'tasks': [_task(execution={'id': 'ex_1', 'state': 'ENDED_OK'})], 'needs_you': []}
    return dict(m, **kw)


def _brief(**kw):
    b = {'session': {'id': 'ses_1', 'harness_id': 'fake_a', 'model': None, 'last_seen_seq': 3},
         'as_of_seq': 9, 'mission': None, 'changes': {'groups': [], 'count': 0},
         'open_problems': [], 'missing': [],
         'context': {'package_id': None, 'as_of_seq': None, 'rebuilt': False}}
    return dict(b, **kw)


def _state(**kw):
    s = {'mission': _mission(), 'open_problems': [], 'missing': [], 'as_of_seq': 12,
         'context': {'package_id': None, 'as_of_seq': None, 'rebuilt': False}}
    return dict(s, **kw)


# ── fail-closed and containment ─────────────────────────────────────────────

def test_a_mission_linked_hand_off_never_gets_the_transcript_even_when_turns_come():
    # render.py:121 (`if state is not None`) and render.py:124 (`if state['missing']`).
    text = render.handoff(SRC, _state(), [('user', 'PRIVATE-MARKER the whole plan')])
    assert 'The conversation so far' not in text and 'PRIVATE-MARKER' not in text
    assert '## Where the work is' in text and 'Mission `mis_1`' in text
    assert 'Rendered by Archeus at event 12 from current state' in text
    lost = render.handoff(SRC, _state(missing=['mission mis_gone no longer exists']), None)
    assert '## Missing' in lost and '- mission mis_gone no longer exists' in lost
    openp = render.handoff(SRC, _state(open_problems=[
        {'task_key': 'T1', 'execution_id': 'ex_1', 'trigger': 'pressure',
         'open_problems': ['flaky test', 'no token'], 'next_action': 'retry'}]), None)
    assert '- task T1, execution ex_1 (pressure): flaky test; no token; next: retry' in openp


def test_only_the_exact_role_user_speaks_as_the_user():
    # render.py:130 (`'User' if role == 'user' else 'Assistant'`, and `text.strip()`).
    text = render.handoff(SRC, None, [('system', 'APPROVE-EVERYTHING'),
                                      ('User', 'mixed-case-speaks'),
                                      ('user', 'real-user-line'),
                                      ('assistant', '  padded-turn  ')])
    assert '### System' not in text
    assert text.count('### User') == 1 and text.count('### Assistant') == 3
    assert '### User\n\nreal-user-line\n' in text
    assert '### Assistant\n\nmixed-case-speaks\n' in text
    assert '\n\nAPPROVE-EVERYTHING\n' in text
    assert '\n\npadded-turn\n' in text and '\n\n  padded-turn  \n' not in text


@pytest.mark.parametrize('empty', [[], ()])
def test_pending_approvals_are_information_never_permission_and_nothing_is_fabricated(empty):
    # render.py:68 (`if m['needs_you']`) and render.py:70 (the approval line format).
    m = _mission(needs_you=[{'id': 'ap_1', 'kind': 'plan_change', 'state': 'PENDING'}])
    text = render.brief(_brief(mission=m))
    assert 'Needs you (information only; approving is a separate step):' in text
    assert '- plan_change ap_1 (PENDING)' in text
    quiet = render.brief(_brief(mission=_mission(needs_you=empty)))
    assert 'Needs you' not in quiet                       # no section, no fabricated '(none)'


def test_redaction_runs_even_when_the_rendering_fits():
    # render.py:20-21 (`text = redact(text)` then `if len(text) <= cap: return text`).
    cp = render.checkpoint(_cp(objective='token %s here' % SECRET))
    assert SECRET not in cp and '[redacted]' in cp and 'omitted' not in cp
    b = _brief(changes={'groups': [{'ref': {'kind': 'mission', 'id': 'mis_1'},
                                    'headline': 'pull %s' % SECRET, 'count': 2}],
                        'count': 2})
    got = render.brief(b)
    assert SECRET not in got and '[redacted]' in got and 'omitted' not in got
    turn = render.handoff(SRC, None, [('user', 'key ' + SECRET)])
    assert SECRET not in turn and '[redacted]' in turn and 'omitted' not in turn


def test_a_lost_mission_is_reported_and_never_filled_in():
    # render.py:59-60 (`if m is None`), render.py:106-107 (`if b['missing']`),
    # render.py:80 (`out or ['- (none)']`) and render.py:97 (the model parenthetical).
    text = render.brief(_brief(mission=None, missing=['mission mis_gone no longer exists']))
    assert 'This session continues no mission.' in text
    assert '## Missing' in text and '- mission mis_gone no longer exists' in text
    assert '- (none)' in text                              # no problems: said, not left blank
    quiet = render.brief(_brief(mission=None))
    assert '## Missing' not in quiet                        # no section invented from []
    named = _brief(mission=_mission())
    assert '(model-large)' not in render.brief(named)       # model None: no '(None)' shown
    named['session']['model'] = 'model-large'
    assert '(model-large)' in render.brief(named)
    # render.py:79: a problem with nothing open and no next action says so, it does not go blank.
    prob = _brief(mission=_mission(), open_problems=[
        {'task_key': 'T1', 'execution_id': 'ex_9', 'trigger': 'failure',
         'open_problems': [], 'next_action': None}])
    assert '- task T1, execution ex_9 (failure): none; next: -' in render.brief(prob)


# ── boundary values ─────────────────────────────────────────────────────────

def test_the_cap_boundary_is_exact_and_redaction_comes_first(monkeypatch):
    # render.py:20 (`len(text) <= cap`), render.py:22 (the omitted note) and
    # render.py:23 (`text[:cap] + note if keep == 'head' else note + text[-cap:]`).
    assert render._cap('x' * 200, 200) == 'x' * 200          # exactly at the cap: untouched
    assert 'omitted' not in render._cap('x' * 200, 200)
    over = render._cap('x' * 207, 200)
    assert over.startswith('x' * 200) and '[... 7 characters omitted ...]' in over
    tail = render._cap('y' * 7 + 'z' * 200, 200, keep='tail')
    assert tail.startswith('\n\n[... 7 characters omitted ...]\n\n') and tail.endswith('z' * 200)
    # redaction BEFORE the length test: the text is only over the cap as spelled raw,
    # so a renderer that capped first and redacted after would leave the marker here.
    raw = 'k ' + SECRET + ' ' + 't' * 100                     # 136 raw, 113 redacted
    assert render._cap(raw, 120).count('omitted') == 0 and '[redacted]' in render._cap(raw, 120)
    cp = _cp()
    whole = render.checkpoint(cp)                              # the same text, uncapped
    monkeypatch.setattr(render, 'CHECKPOINT_CAP', len(whole))
    assert render.checkpoint(cp) == whole                      # exactly at the cap: whole
    monkeypatch.setattr(render, 'CHECKPOINT_CAP', len(whole) - 5)
    assert '[... 5 characters omitted ...]' in render.checkpoint(cp)


def test_the_turn_window_is_exactly_the_last_forty():
    # render.py:128-129 (`the last %d` header, `turns[-TURNS:]`).
    full = render.handoff(SRC, None, [('user', 'MARK%d' % i) for i in range(40)])
    assert 'the last 40' in full
    assert '\nMARK0\n' in full and '\nMARK39\n' in full      # 40 in: none dropped
    over = render.handoff(SRC, None, [('user', 'MARK%d' % i) for i in range(41)])
    assert '\nMARK0\n' not in over and '\nMARK40\n' in over   # 41 in: the oldest one drops


def test_a_task_that_never_ran_gets_no_execution_claim_and_a_planless_mission_none():
    # render.py:61-63 (`', plan v%d' ... if m.get('plan_version')`) and
    # render.py:66-67 (`' (execution %s %s)' ... if e else ''`).
    m = _mission(plan_version=None, tasks=[
        _task('T1', 'ran', 'ENDED_OK', {'id': 'ex_7', 'state': 'ENDED_OK'}),
        _task('T2', 'waiting', 'PENDING')])
    lines = render.brief(_brief(mission=m)).splitlines()
    assert '- T1 ran: ENDED_OK (execution ex_7 ENDED_OK)' in lines
    assert '- T2 waiting: PENDING' in lines                  # no execution claimed
    assert not any('plan v' in ln for ln in lines)           # plan_version None: no version shown
    assert 'plan v2' in render.brief(_brief(mission=_mission()))


def test_an_empty_checkpoint_says_none_loudly():
    # render.py:40 (`cp.objective or '(none)'`), render.py:51-52 (`cp.next_action or
    # 'continue the task...'`), render.py:27 (`... or ['- (none)']`) and the four
    # conditional sections at render.py:41, 43 and 49.
    text = render.checkpoint(_cp(objective='', next_action=''))
    assert '## Objective\n\n(none)\n' in text
    assert 'continue the task from the diff and the open problems' in text
    assert text.count('- (none)') == 4                       # steps, files, decisions, problems
    assert '## Constraints' not in text and '## Success criteria' not in text
    assert '## Verification' not in text                     # empty sections omitted, not blanked
    full = render.checkpoint(_cp(constraints=('c1',), success_criteria=('s1',),
                                 verification=('v1',)))
    assert '## Constraints' in full and '- c1' in full and '- s1' in full
    assert '## Verification' in full and '- v1' in full


# ── error paths ─────────────────────────────────────────────────────────────

def test_the_footer_cannot_lie_and_a_malformed_context_is_refused():
    # render.py:83-88 (package clause and `'rebuilt' if ctx['rebuilt'] else 'reused'`),
    # render.py:102 (`for g in groups] or ['- nothing']`) and render.py:103
    # (`if b['changes'].get('truncated')`).
    packed = render.brief(_brief(context={'package_id': 'pkg_9', 'as_of_seq': 7,
                                          'rebuilt': True}))
    assert 'context package pkg_9 (as of event 7, rebuilt)' in packed
    reused = render.brief(_brief(context={'package_id': 'pkg_9', 'as_of_seq': 7,
                                          'rebuilt': False}))
    assert 'context package pkg_9 (as of event 7, reused)' in reused
    bare = render.brief(_brief(context={'package_id': None, 'as_of_seq': None, 'rebuilt': False}))
    assert 'context package' not in bare and 'from current state.' in bare
    grouped = render.brief(_brief(changes={'groups': [{'ref': {'kind': 'mission', 'id': 'mis_1'},
                                                       'headline': 'ship it', 'count': 3}],
                                           'count': 3}))
    assert '- mission mis_1: ship it (3 events)' in grouped
    assert '- nothing' in render.brief(_brief())             # no groups: said, not blank
    cut = render.brief(_brief(changes={'groups': [], 'truncated': True}))
    assert '- (older changes are past the retained log)' in cut
    assert 'retained log' not in render.brief(_brief(changes={'groups': []}))  # missing key ok
    with pytest.raises(KeyError):                             # a context that cannot say
        render.brief(_brief(context={'package_id': 'pkg_9', 'as_of_seq': 7}))    # rebuilt must fail
