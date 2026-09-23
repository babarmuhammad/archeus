"""The state table and the diagrams are one declaration (state-machines §0).

Parses every `stateDiagram-v2` block of docs/architecture/state-machines.md
and fails when a diagram edge is missing from `states.TABLE` or vice versa —
so a lifecycle cannot be changed in one place and not the other.
"""

import os
import re
from collections import Counter

import pytest

from archeus.core.domain import states

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
DOC = os.path.join(ROOT, 'docs', 'architecture', 'state-machines.md')

EDGE = re.compile(r'^\s*(\[\*\]|[A-Z_]+)\s*-->\s*(\[\*\]|[A-Z_]+)\s*(?::\s*([a-z_]+))?\s*$')


def _diagrams():
    text = open(DOC, encoding='utf-8').read()
    blocks = re.findall(r'```mermaid\n(stateDiagram-v2\n.*?)```', text, re.S)
    out = []
    for block in blocks:
        edges = []
        for line in block.splitlines()[1:]:
            if not line.strip():
                continue
            m = EDGE.match(line)
            assert m, 'unparseable state-diagram line: %r' % line
            edges.append(m.groups())
        out.append(edges)
    return out


def test_one_diagram_per_machine_in_document_order():
    assert len(_diagrams()) == len(states.MACHINES)


@pytest.mark.parametrize('i,machine', list(enumerate(states.MACHINES)))
def test_the_table_and_the_diagram_hold_the_same_edges(i, machine):
    drawn = Counter(_diagrams()[i])
    table = Counter((f, t, g) for f, t, g, _guard in states.edges(machine))
    assert table == drawn, ('%s: only in the table %s; only in the diagram %s'
                            % (machine, sorted(table - drawn), sorted(drawn - table)))


def test_missions_have_no_learned_state():
    """Learning is an outbox consumer stamping `learned_at`; a failed learning
    pass must never be able to reopen a completed mission."""
    assert 'LEARNED' not in states.states('mission')
    assert all('LEARNED' not in (f, t) for f, t, _g, _x in states.edges('mission'))
    assert 'LEARNED' in states.states('idea')      # the one machine that has it


@pytest.mark.parametrize('machine', states.MACHINES)
def test_machine_invariants(machine):
    rows = states.edges(machine)
    starts = [t for f, t, _g, _x in rows if f == states.START]
    assert len(starts) == 1, 'exactly one initial state'
    names = states.states(machine)
    assert all(re.fullmatch(r'[A-Z][A-Z_]*', s) for s in names if s != states.END)
    assert all(re.fullmatch(r'[a-z][a-z_]*', g) for f, _t, g, _x in rows
               if g and f != states.START)
    # a trigger picks at most one target from a given state
    keys = [(f, g) for f, _t, g, _x in rows if g]
    assert len(keys) == len(set(keys)), 'a trigger is ambiguous from one state'
    # terminal states are terminal
    for s in states.terminal(machine):
        assert not states.targets(machine, s), '%s is terminal but has exits' % s
    # every state is reachable from the initial one
    seen, todo = set(), [states.initial(machine)]
    while todo:
        s = todo.pop()
        if s in seen or s == states.END:
            continue
        seen.add(s)
        todo += list(states.targets(machine, s).values())
    assert set(names) - {states.END} <= seen, 'unreachable: %s' % (set(names) - seen)


def test_guards_name_edges_that_exist():
    for machine, frm, to, trig, guard in states.TABLE:
        assert guard in (None, trig), (machine, frm, to)
    assert {g for m, *_rest, g in states.TABLE if m == 'mission' and g} == {
        'plan_auto_approved', 'all_tasks_done', 'verified', 'awaiting_human_acceptance',
        'replan_budget_exhausted', 'task_failed_retryable', 'unrecoverable'}


def test_initial_and_terminal_helpers():
    assert states.initial('mission') == 'CREATED'
    assert states.initial('execution') == 'INTENT'
    assert states.terminal('mission') == {'COMPLETED', 'CANCELLED'}
    assert states.initial('plan') == 'DRAFT'          # an undiagrammed state set
    assert states.targets('execution', 'INTENT') == {
        'spawn': 'STARTING', 'spawn_failed': 'ABANDONED', 'spawn_unconfirmed': 'LOST'}
    with pytest.raises(KeyError):
        states.edges('nope')
