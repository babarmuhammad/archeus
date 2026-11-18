"""T-1414: the uncovered branches of `archeus/core/application/conversation.py` lines
667-742 inclusive (`_inferred`, `_stale_target`, `_pending_clarification`, `resolve_directive`)
at tip 6a32dc14 (re-located at 81d83030). No source file is edited. The `_mission` header
and PROTECTED are not claimed here (PROTECTED is enforced at conversation.py:798).

Ten selected branches, denial and fail-closed first, then boundaries, then error paths:

1. 668-669 _inferred: only 'inferred' items are listed; none gives ''; some give '; I inferred: a; b'.
   Catches: the origin filter removed, or the join separator changed.
2. 694-696 _stale_target: a proposal with no target returns [] without a store read.
   Catches: the None guard removed (the read would fail on a None target).
3. 697-699 _stale_target: a terminal mission target yields one message with title and state;
   a live mission yields []. Catches: the terminal test inverted or the message changed.
4. 701-704 _stale_target: an idea target is reported only for new_work and only outside PROMOTE_PATH.
   Catches: the kind test dropped, or the PROMOTE_PATH membership inverted.
5. 708-715 _pending_clarification: the first clarification or challenge card whose ref is an intent
   is returned; other types and ref kinds are skipped; no match gives None.
   Catches: the type or ref-kind filter widened or dropped.
6. 709-711 _pending_clarification: an unknown reply_to returns None without an exception.
   Catches: the None guard removed.
7. 730-732 resolve_directive: a falsy directive returns (None, []) with no store read.
   Catches: the early return removed.
8. 733-739 resolve_directive: a name resolving to one ref is appended to its side with its kind;
   a name resolving to None adds one question. Catches: the side mapping or the None branch.
9. 730-740 resolve_directive: an empty directive keeps empty prefer and forbid lists and an unknown
   side key is not copied to output. Catches: output built from the input dict.
10. 736-737 resolve_directive: the question wording is exact and the same for zero or several matches.
    Catches: the wording changed, or a second message for ambiguity.

Closest existing test: tests/v1/unit/test_gaps_core_application_conversation.py mentions the module
(no hit for these functions in the gap files). Fakes only: an in-memory tx with `get`, a fake
`grammar.resource` and fake entities with the fields these functions read. No database.
"""

from types import SimpleNamespace

import pytest

from archeus.core.application import conversation as conv
from archeus.core.application import grammar
from archeus.core.domain import entities, states


class Tx:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.conn = object()
        self.reads = []

    def get(self, cls, id_):
        self.reads.append((cls, id_))
        return self.rows.get((cls, id_))


def _row(entity):
    return SimpleNamespace(entity=entity)


def _msg(*cards):
    return SimpleNamespace(cards=list(cards))


def _card(type_, kind, id_):
    return {'type': type_, 'ref': {'kind': kind, 'id': id_}}


# 1. 668-669: only inferred items, joined in order
def test_inferred_is_empty_without_an_inferred_item():
    m = SimpleNamespace(requirements=({'text': 'a', 'origin': 'stated'},),
                        constraints=({'text': 'b', 'origin': 'stated'},))
    assert conv._inferred(m) == ''


def test_inferred_lists_only_inferred_items_across_requirements_and_constraints():
    m = SimpleNamespace(
        requirements=({'text': 'a', 'origin': 'inferred'}, {'text': 'b', 'origin': 'stated'}),
        constraints=({'text': 'c', 'origin': 'inferred'},))
    assert conv._inferred(m) == '; I inferred: a; c'


# 2. 694-696: no target, no store read
def test_stale_target_without_a_target_returns_empty_and_reads_nothing():
    tx = Tx()
    assert conv._stale_target(tx, {'kind': 'new_work', 'target': None}) == []
    assert tx.reads == []


# 3. 697-699: a terminal mission is stale; a live one is not
def test_stale_target_names_a_terminal_mission_with_its_title_and_state():
    ended = sorted(states.terminal('mission'))[0]
    tx = Tx({(entities.Mission, 'mission_1'): _row(SimpleNamespace(state=ended,
                                                                   title='Ship it'))})
    assert conv._stale_target(tx, {'kind': 'new_work',
                                   'target': {'kind': 'mission', 'id': 'mission_1'}}) == [
        'Mission "Ship it" has ended (%s); should this be new work?' % ended]


def test_stale_target_passes_a_live_mission():
    tx = Tx({(entities.Mission, 'mission_1'): _row(SimpleNamespace(state='UNDERSTANDING',
                                                                   title='Ship it'))})
    assert conv._stale_target(tx, {'kind': 'new_work',
                                   'target': {'kind': 'mission', 'id': 'mission_1'}}) == []


# 4. 701-704: an idea is stale only for new_work and only outside PROMOTE_PATH
def test_stale_target_reports_a_parked_idea_for_new_work():
    tx = Tx({(entities.Idea, 'idea_1'): _row(SimpleNamespace(id='idea_1', state='PARKED'))})
    assert conv._stale_target(tx, {'kind': 'new_work',
                                   'target': {'kind': 'idea', 'id': 'idea_1'}}) == [
        'Idea idea_1 is PARKED and cannot be made into a mission again.']


@pytest.mark.parametrize('kind, state', [('new_work', 'CAPTURED'), ('other', 'PARKED')])
def test_stale_target_passes_a_promotable_idea_or_another_kind(kind, state):
    tx = Tx({(entities.Idea, 'idea_1'): _row(SimpleNamespace(id='idea_1', state=state))})
    assert conv._stale_target(tx, {'kind': kind, 'target': {'kind': 'idea', 'id': 'idea_1'}}) == []


# 5. 708-715: the first clarification or challenge intent card
def test_pending_clarification_returns_the_first_intent_question_card():
    cards = [_card('note', 'intent', 'i0'), _card('clarification', 'mission', 'm1'),
             _card('challenge', 'intent', 'i2'), _card('clarification', 'intent', 'i3')]
    tx = Tx({(entities.Message, 'msg_1'): _row(_msg(*cards))})
    assert conv._pending_clarification(tx, 'msg_1') == 'i2'


def test_pending_clarification_is_none_without_a_matching_card():
    cards = [_card('note', 'intent', 'i0'), _card('clarification', 'mission', 'm1')]
    tx = Tx({(entities.Message, 'msg_1'): _row(_msg(*cards))})
    assert conv._pending_clarification(tx, 'msg_1') is None


# 6. 709-711: an unknown message is None, not an exception
def test_pending_clarification_is_none_for_an_unknown_message():
    assert conv._pending_clarification(Tx(), 'msg_missing') is None


# 7. 730-732: a falsy directive reads nothing
@pytest.mark.parametrize('directive', [None, {}])
def test_resolve_directive_returns_nothing_for_a_falsy_directive(monkeypatch, directive):
    monkeypatch.setattr(grammar, 'resource', lambda *a, **k: pytest.fail('no lookup'))
    assert conv.resolve_directive(Tx(), directive) == (None, [])


# 8-10. 730-740: names resolve per side; unknown and ambiguous names become one question
@pytest.fixture
def resource(monkeypatch):
    table = {'fast': {'kind': 'account', 'id': 'acc_1'},
             'codex': {'kind': 'harness', 'id': 'codex'}}
    calls = []

    def fake(conn, name, kinds=('account', 'harness'), harnesses=()):
        calls.append((name, tuple(kinds)))
        ref = table.get(name)
        return ref if ref is not None and ref['kind'] in kinds else None

    monkeypatch.setattr(grammar, 'resource', fake)
    return calls


def test_resolve_directive_appends_each_resolved_name_to_its_side(resource):
    d = {'scope': 'mission', 'prefer': {'accounts': ['fast']},
         'forbid': {'harnesses': ['codex']}}
    assert conv.resolve_directive(Tx(), d) == (
        {'scope': 'mission', 'prefer': [{'kind': 'account', 'id': 'acc_1'}],
         'forbid': [{'kind': 'harness', 'id': 'codex'}]}, [])


def test_resolve_directive_asks_one_exact_question_for_a_name_that_resolves_to_none(resource):
    d = {'scope': 'mission', 'prefer': {'accounts': ['ghost']}}
    out, asked = conv.resolve_directive(Tx(), d)
    assert out == {'scope': 'mission', 'prefer': [], 'forbid': []}
    assert asked == ['I do not know exactly one account called "ghost". Which one do you mean?']


def test_resolve_directive_keeps_empty_lists_and_ignores_unknown_side_keys(resource):
    d = {'scope': 'session', 'prefer': {}, 'forbid': None, 'allow': {'accounts': ['fast']}}
    out, asked = conv.resolve_directive(Tx(), d)
    assert out == {'scope': 'session', 'prefer': [], 'forbid': []}
    assert asked == []
    assert resource == []


def test_resolve_directive_words_an_ambiguous_name_like_an_unknown_one(monkeypatch):
    monkeypatch.setattr(grammar, 'resource', lambda *a, **k: None)
    d = {'scope': 'mission', 'forbid': {'accounts': ['twin']}}
    out, asked = conv.resolve_directive(Tx(), d)
    assert out['forbid'] == []
    assert asked == ['I do not know exactly one account called "twin". Which one do you mean?']
