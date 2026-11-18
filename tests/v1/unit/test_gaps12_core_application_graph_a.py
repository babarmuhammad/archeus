"""T-1434 - graph.py 52-136 (_terminal, clean_label, _label, _parent, _edge),
round-15 gap probes. Lines 261-330 belong to T-1392 and are not probed here.

Selected branches, in rank order:
  1 _terminal(None) is empty                                  (graph.py:54-55)
  2 a state with a non-END edge is moving; no-edge state terminal (56-57)
  3 an edge to END does not make its source moving            (56)
  4 _terminal on an unknown machine raises KeyError           (54-57, error path)
  5 clean_label trims leading and trailing whitespace         (65)
  6 clean_label of only whitespace and controls is ''         (65)
  7 clean_label keeps printable non-ASCII text                (65)
  8 redact runs before the length cut                         (66-67)
  9 _edge emits the default field shape                       (131-133)
 10 _edge extras override the defaults                        (133-135)
"""

import pytest

from archeus.core.application import graph as G
from archeus.core.domain import states


def _machine(monkeypatch, edges, all_states):
    monkeypatch.setattr(G.states, 'edges', lambda machine: edges)
    monkeypatch.setattr(G.states, 'states', lambda machine: all_states)


def test_a_machine_with_no_machine_has_no_terminal_states():
    """graph.py:54-55 - None means no machine: the empty set, not a lookup.
    Removed, states.edges(None) would raise for a kind that has no state."""
    assert G._terminal(None) == frozenset()


def test_a_state_with_a_non_end_edge_is_moving_and_a_state_with_no_edge_is_terminal(
        monkeypatch):
    """graph.py:56-57 - A has an edge to B (not END), so it is moving and not
    terminal; C has no edge at all, so it is terminal. Inverted, the open row
    would rank as settled and the closed one as open."""
    _machine(monkeypatch, [('A', 'B', 'go', None)], ('A', 'B', 'C'))
    assert G._terminal('M') == frozenset({'B', 'C'})


def test_an_edge_to_end_does_not_make_its_source_moving(monkeypatch):
    """graph.py:56 - the `to != states.END` filter: B's only edge leads to END,
    so B is terminal. Removed, B counts as moving and a finished row ranks open."""
    _machine(monkeypatch, [('A', 'B', 'go', None), ('B', states.END, 'end', None)], ('A', 'B'))
    assert G._terminal('M') == frozenset({'B'})


def test_an_unknown_machine_raises_rather_than_guessing_terminal_states():
    """graph.py:54-57 - an unknown machine name propagates KeyError from
    states.edges; no terminal set is guessed for a machine that does not exist."""
    with pytest.raises(KeyError):
        G._terminal('NO_SUCH_MACHINE')


def test_clean_label_trims_leading_and_trailing_whitespace():
    """graph.py:65 - ' '.join(split()) drops both ends. Removed or replaced with a
    plain collapse, a label would carry a leading or trailing gap into the row."""
    assert G.clean_label('  \t hello world \n ') == 'hello world'


def test_clean_label_of_only_whitespace_and_controls_is_empty():
    """graph.py:65 - controls that are not whitespace survive split() and are then
    dropped by isprintable(); what is left is ''. Removed, a control-only label
    would render as an invisible non-empty string."""
    assert G.clean_label(' \x00\x07 \t') == ''


def test_clean_label_keeps_printable_non_ascii_text():
    """graph.py:65 - isprintable() drops controls, not letters: accented and CJK
    text stays. Replaced by an ASCII filter, a non-English title would vanish."""
    assert G.clean_label('café 日本 ✓') == 'café 日本 ✓'


def test_clean_label_redacts_before_it_cuts_to_length(monkeypatch):
    """graph.py:66-67 - redact runs on the collapsed text before the length check,
    so a redaction that grows the text is cut like any other text. Reversed, the
    cut would happen first and the output could exceed LABEL_MAX."""
    seen = []

    def grow(s):
        seen.append(s)
        return s + 'Z' * 200

    monkeypatch.setattr(G, 'redact', grow)
    out = G.clean_label('a   b')
    assert seen == ['a b']
    assert len(out) == G.LABEL_MAX and out.endswith('…')


def test_an_edge_carries_the_default_field_shape():
    """graph.py:131-133 - the default dict: rel and tier None, inactive and
    structural False, with the target as {'kind', 'id'}. Removed or renamed, the
    renderer reads a missing key on every emitted edge."""
    out = []
    G._edge(out, {'kind': 'mission', 'id': 'm1'}, 'missions.project_id', 'project', 'p1')
    assert out == [{'from': {'kind': 'mission', 'id': 'm1'},
                    'to': {'kind': 'project', 'id': 'p1'}, 'field': 'missions.project_id',
                    'rel': None, 'tier': None, 'inactive': False, 'structural': False}]


def test_an_edge_extra_overrides_the_default_of_the_same_name():
    """graph.py:133-135 - dict(defaults, **extra): the extras are merged last, so a
    caller's rel, tier, inactive and structural replace the defaults. Reversed, a
    caller could not mark an edge inactive or structural."""
    out = []
    G._edge(out, {'kind': 'a', 'id': '1'}, 'f', 'b', 'x', rel='owns', tier=2,
            inactive=True, structural=True)
    assert (out[0]['rel'], out[0]['tier'], out[0]['inactive'], out[0]['structural']) == (
        'owns', 2, True, True)
