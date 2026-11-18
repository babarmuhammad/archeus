"""T-1430: idea promotion and mission continuation of archeus/core/application/conversation.py,
lines 480-528 at tip 026ea58e: _promote and _continue. Ranked, denial and fail-closed first:

1. 490-493 _promote: a state missing from PROMOTE_PATH fires no trigger and still records
   resolution 'mission_created'.
2. 490-493 _promote: CAPTURED fires clarify, plan, promote in that order; only promote carries
   {'promoted_mission_id': ...}, the others None.
3. 482-483 _promote: title falls back to idea.title then idea.text; objective to idea.text.
4. 484 _promote: project comes from idea.project_id, else p['project'] id; a None project is safe.
5. 495-498 _promote: the `then` callback's text and links are appended through _with.
6. 506-510 _continue: no requirements or constraints with `then`: the callback's
   (text, resolution, cards, links) are used and no mission.updated is appended.
7. 511-516 _continue: no requirements, constraints or `then`: resolution 'answered' with
   reason 'nothing to add to <id>', no mission write.
8. 505 _continue: extra_constraints follow the message constraints in the stored tuple.
9. 520-523 _continue: payload 'fields' lists only the non-empty groups; 'added' keeps both.
10. 517-519 _continue: stored requirements and constraints extend the existing tuples.

Fakes: lifecycle.load and lifecycle.fire record or return fixed entities, _mission and
_set are replaced, _reply returns its arguments. _items, _with, _card and new_event run
for real. The tx records update and append calls.
"""

import types

import pytest

from archeus.core.application import conversation as conv
from archeus.core.application import lifecycle
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref

ACTOR = Ref('user_device', ids.new_id('principal'))
MSG = types.SimpleNamespace(id='message_1')
INTENT = types.SimpleNamespace(id='intent_1')


class RecTx:
    def __init__(self):
        self.updates, self.appends = [], []

    def update(self, cls, entity_id, fields, *, actor, **kw):
        self.updates.append((cls, entity_id, fields))

    def append(self, event):
        self.appends.append(event)


@pytest.fixture
def rec(monkeypatch):
    calls = types.SimpleNamespace(fires=[], sets=[], missions=[], loads={})
    monkeypatch.setattr(lifecycle, 'fire',
                        lambda tx, cls, eid, trigger, **kw: calls.fires.append(
                            (trigger, kw.get('fields'))))
    monkeypatch.setattr(conv, '_set', lambda tx, actor, it, **fields: (
        calls.sets.append(fields) or it))
    monkeypatch.setattr(conv, '_reply', lambda tx, actor, msg, it, text, cards=(), links=(): (
        text, list(cards), list(links)))

    def mission(tx, actor, p, **kw):
        calls.missions.append((p, kw))
        return types.SimpleNamespace(id='mission_new', title=p['title'], requirements=(),
                                     constraints=())
    monkeypatch.setattr(conv, '_mission', mission)
    monkeypatch.setattr(lifecycle, 'load', lambda tx, cls, eid: types.SimpleNamespace(
        entity=calls.loads[cls]))
    return calls


def _idea(state='CAPTURED', title='idea title', text='idea text', project_id=None):
    return types.SimpleNamespace(id='idea_1', state=state, title=title, text=text,
                                 project_id=project_id)


def _promote(rec, idea, p=None, then=None):
    rec.loads[entities.Idea] = idea
    p = {'title': 'T', 'objective': 'O', 'project': None, **(p or {})}
    return conv.Conversations._promote(None, RecTx(), ACTOR, MSG, INTENT, p, idea.id, (),
                                       then=then)


def test_promote_from_a_state_outside_promote_path_fires_nothing_and_still_resolves(rec):
    _promote(rec, _idea(state='IMPLEMENTING'))
    assert rec.fires == []
    assert rec.sets == [{'resolution': 'mission_created'}]


def test_promote_from_captured_fires_clarify_plan_promote_in_order(rec):
    _promote(rec, _idea(state='CAPTURED'))
    assert [t for t, _ in rec.fires] == ['clarify', 'plan', 'promote']
    fields = {t: f for t, f in rec.fires}
    assert fields['clarify'] is None and fields['plan'] is None
    assert fields['promote'] == {'promoted_mission_id': 'mission_new'}


@pytest.mark.parametrize('p, idea_kw, want_title, want_objective', [
    ({'title': '', 'objective': ''}, {'title': 'ITitle', 'text': 'IText'}, 'ITitle', 'IText'),
    ({'title': '', 'objective': ''}, {'title': '', 'text': 'IText'}, 'IText', 'IText'),
    ({'title': 'PT', 'objective': 'PO'}, {'title': 'ITitle', 'text': 'IText'}, 'PT', 'PO'),
], ids=['idea-title', 'idea-text-title', 'payload-wins'])
def test_promote_title_and_objective_fall_back_one_key_at_a_time(rec, p, idea_kw, want_title,
                                                                want_objective):
    _promote(rec, _idea(**idea_kw), p=p)
    sent, _ = rec.missions[0]
    assert (sent['title'], sent['objective']) == (want_title, want_objective)


def test_promote_project_comes_from_the_idea_then_the_payload_then_none(rec):
    _promote(rec, _idea(project_id='proj_idea'), p={'title': 'T', 'objective': 'O',
                                                    'project': {'id': 'proj_payload'}})
    assert rec.missions[-1][1]['project'] == 'proj_idea'
    _promote(rec, _idea(project_id=None), p={'title': 'T', 'objective': 'O',
                                             'project': {'id': 'proj_payload'}})
    assert rec.missions[-1][1]['project'] == 'proj_payload'
    _promote(rec, _idea(project_id=None), p={'title': 'T', 'objective': 'O', 'project': None})
    assert rec.missions[-1][1]['project'] is None


def test_promote_appends_the_then_callback_text_and_links(rec):
    then = lambda mid, it: ('Then more.', 'answered', [], [{'ref': {'kind': 'task',
                                                                    'id': 'task_9'}}])
    text, cards, links = _promote(rec, _idea(), then=then)
    assert text.endswith('Then more.')
    assert {'ref': {'kind': 'task', 'id': 'task_9'}} in links


def test_continue_with_nothing_new_uses_the_then_callback_and_writes_no_mission(rec):
    rec.loads[entities.Mission] = types.SimpleNamespace(
        id='mission_1', title='M', workspace_id=ids.GLOBAL_WORKSPACE, project_id=None, requirements=(),
        constraints=())
    tx = RecTx()
    then = lambda mid, it: ('Directive done.', 'declined', [{'type': 'x'}], [])
    out = conv.Conversations._continue(None, tx, ACTOR, MSG, INTENT,
                                       {'target': {'id': 'mission_1'}, 'requirements': [],
                                        'constraints': []}, (), then=then)
    assert out == ('Directive done.', [{'type': 'x'}], [])
    assert rec.sets == [{'resolution': 'declined'}]
    assert tx.updates == [] and tx.appends == []


def test_continue_with_nothing_new_and_no_callback_answers_and_names_the_mission(rec):
    rec.loads[entities.Mission] = types.SimpleNamespace(
        id='mission_1', title='M', workspace_id=ids.GLOBAL_WORKSPACE, project_id=None, requirements=(),
        constraints=())
    tx = RecTx()
    text, cards, links = conv.Conversations._continue(
        None, tx, ACTOR, MSG, INTENT,
        {'target': {'id': 'mission_1'}, 'requirements': [], 'constraints': []}, ())
    assert rec.sets == [{'resolution': 'answered', 'reason': 'nothing to add to mission_1'}]
    assert text == 'Noted for mission "M" (mission_1); it asks nothing new of it.'
    assert tx.updates == [] and tx.appends == []


def _continue_mission(rec, requirements=(), constraints=()):
    rec.loads[entities.Mission] = types.SimpleNamespace(
        id='mission_1', title='M', workspace_id=ids.GLOBAL_WORKSPACE, project_id=None,
        requirements=requirements, constraints=constraints)
    return RecTx()


def test_continue_puts_extra_constraints_after_the_message_constraints(rec):
    tx = _continue_mission(rec)
    extra = [{'text': 'from-extra', 'origin': 'explicit', 'source_ref': 'x'}]
    conv.Conversations._continue(None, tx, ACTOR, MSG, INTENT,
                                 {'target': {'id': 'mission_1'}, 'requirements': [],
                                  'constraints': [{'text': 'from-msg', 'origin': 'explicit'}]},
                                 extra)
    _, _, fields = tx.updates[0]
    assert [c['text'] for c in fields['constraints']] == ['from-msg', 'from-extra']


@pytest.mark.parametrize('req, con, want_fields', [
    ([{'text': 'r', 'origin': 'explicit'}], [], ['requirements']),
    ([], [{'text': 'c', 'origin': 'explicit'}], ['constraints']),
], ids=['requirements-only', 'constraints-only'])
def test_continue_event_lists_only_the_groups_it_added(rec, req, con, want_fields):
    tx = _continue_mission(rec)
    conv.Conversations._continue(None, tx, ACTOR, MSG, INTENT,
                                 {'target': {'id': 'mission_1'}, 'requirements': req,
                                  'constraints': con}, ())
    [event] = tx.appends
    assert event.payload['fields'] == want_fields
    assert set(event.payload['added']) == {'requirements', 'constraints'}


def test_continue_extends_the_stored_tuples_and_keeps_earlier_entries(rec):
    old_r = ({'text': 'old-r', 'origin': 'explicit'},)
    old_c = ({'text': 'old-c', 'origin': 'explicit'},)
    tx = _continue_mission(rec, requirements=old_r, constraints=old_c)
    conv.Conversations._continue(None, tx, ACTOR, MSG, INTENT,
                                 {'target': {'id': 'mission_1'}, 'requirements': [
                                     {'text': 'new-r', 'origin': 'explicit'}],
                                  'constraints': []}, ())
    _, _, fields = tx.updates[0]
    assert fields['requirements'][:1] == old_r
    assert [r['text'] for r in fields['requirements']] == ['old-r', 'new-r']
    assert fields['constraints'] == old_c
