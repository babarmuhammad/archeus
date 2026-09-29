"""The TUI against the shared parity cases (p17-design-gate A2): the SPA's
clients/app/test/parity.test.ts holds the TypeScript side to the same outputs,
so the two presentations cannot drift apart silently."""

import json
import os

import pytest

from archeus.cli.tui import present as P, sync as S

CASES = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'clients', 'app', 'test',
                     'fixtures', 'parity.json')
with open(CASES, encoding='utf-8') as _f:
    ALL = json.load(_f)['cases']

FN = {
    'missionEdges': P.mission_edges, 'planEdges': P.plan_edges,
    'taskDependencies': P.task_dependencies, 'executionEdges': P.execution_edges,
    'verificationEdges': P.verification_edges, 'sessionEdges': P.session_edges,
    'knowledgeEdges': P.knowledge_edges, 'runEdges': P.run_edges,
    'present': P.present, 'badge': P.badge, 'isDone': P.is_done, 'offers': P.offers,
    'presenceLabel': P.presence_label, 'resourceLine': P.resource_line,
    'statusLine': P.status_line, 'explainState': P.explain_state, 'ago': P.ago,
    'next': S.next_state, 'freshness': S.freshness, 'canCommand': S.can_command,
    'explain': S.explain, 'decideBody': S.decide_body, 'retryable': S.retryable,
    'keyAfter': lambda prev, outcome: S.key_after(prev, outcome, lambda: 'NEW'),
    'staleBy': lambda frame, path: S.stale_by(frame)(path),
}


@pytest.mark.parametrize('case', ALL, ids=lambda c: c['fn'])
def test_every_shared_parity_case_gives_the_recorded_output(case):
    assert FN[case['fn']](*case['args']) == case['out'], (case['fn'], case['args'])


def test_every_function_held_to_parity_has_cases_and_every_case_names_one():
    named = {c['fn'] for c in ALL}
    assert named == set(FN)
