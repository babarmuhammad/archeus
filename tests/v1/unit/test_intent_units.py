"""P7 units (p7-design-gate §12, U01, U03–U08; U02 is I21, it needs a database): the control grammar's table, the
intent.v1 schema, Core's checks and handle resolution, and the import
boundaries that keep planning, policy, routing, execution and every provider
out of the intent path."""

import ast
import os
import subprocess
import sys

import pytest

from archeus.core.application import grammar
from archeus.core.brain import intent as brain
from archeus.core.domain import shapes

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


# ── U01 the grammar table: every control verb, and what is not one ──

@pytest.mark.parametrize('text, verb, arg', [
    ('pause Ship it', 'pause', 'Ship it'), ('resume Ship it.', 'resume', 'Ship it'),
    ('stop Ship it', 'cancel', 'Ship it'), ('cancel  Ship   it!', 'cancel', 'Ship it'),
    ('status', 'status', ''), ('Status archeus', 'status', 'archeus'),
    ('why rte_01', 'why', 'rte_01'), ('approve', 'approve', ''), ('reject', 'reject', ''),
    ('reprioritize x', 'reprioritise', 'x'), ('reprioritise', 'reprioritise', ''),
    ('remember that tabs are wrong', 'remember', 'tabs are wrong'),
    ('Remember releases are on Friday', 'remember', 'releases are on Friday'),
])
def test_u01_every_control_verb_parses(text, verb, arg):
    assert grammar.parse(text) == grammar.Parsed(verb, arg)


@pytest.mark.parametrize('text', ['Add a --version flag', 'Idea: a digest', 'what is the status?',
                                  'remember', 'remember that', '', '   ', 'stopwatch it'])
def test_u01b_what_is_not_a_control_verb(text):
    assert grammar.parse(text) is None


# ── U03 the schema ──

FULL = {'kind': 'new_work', 'title': 't', 'objective': 'o', 'desired_outcome': None,
        'target': None, 'project': 'p1',
        'mentions': [{'name': 'x', 'kind': 'person', 'ref': None}],
        'requirements': [{'text': 'r', 'origin': 'explicit'}], 'constraints': [],
        'ambiguities': [{'question': 'q', 'material': False}],
        'conflicts': [{'ref': 'k1', 'why': 'w'}], 'feedback': None, 'answer': None,
        'confidence': 0.5}


def test_u03_the_schema_takes_a_full_reading_and_refuses_what_is_not_one():
    shapes.validate(FULL, brain.SCHEMA)
    for bad in ({'kind': 'plan_it'}, dict(FULL, tasks=[]), {'title': 't'},
                dict(FULL, requirements=[{'text': 'r', 'origin': 'guessed'}])):
        with pytest.raises(shapes.Invalid):
            shapes.validate(bad, brain.SCHEMA)


# ── U04 Core's checks: handles, kinds, and what each kind needs ──

FACTS = {
    'p1': {'kind': 'project', 'id': 'prj_1'},
    'm1': {'kind': 'mission', 'id': 'msn_1', 'state': 'EXECUTING'},
    'm2': {'kind': 'mission', 'id': 'msn_2', 'state': 'COMPLETED'},
    'i1': {'kind': 'idea', 'id': 'ida_1', 'state': 'CAPTURED'},
    'k1': {'kind': 'knowledge_item', 'id': 'kno_1', 'state': 'CONFIRMED', 'ktype': 'DECISION',
           'source_kind': 'user'},
    'k2': {'kind': 'knowledge_item', 'id': 'kno_2', 'state': 'CANDIDATE', 'ktype': 'DECISION',
           'source_kind': 'import'},
    'k3': {'kind': 'knowledge_item', 'id': 'kno_3', 'state': 'CANDIDATE', 'ktype': 'DECISION',
           'source_kind': 'inspection'},
    'k4': {'kind': 'knowledge_item', 'id': 'kno_4', 'state': 'CONFIRMED', 'ktype': 'ENTITY',
           'source_kind': 'inspection'},
    'k5': {'kind': 'knowledge_item', 'id': 'kno_5', 'state': 'CANDIDATE', 'ktype': 'PREFERENCE'},
    'u1': {'kind': 'message', 'id': 'msg_1', 'cards': [
        {'type': 'knowledge', 'ref': {'kind': 'knowledge_item', 'id': 'kno_5'}}]},
    'u2': {'kind': 'message', 'id': 'msg_2', 'cards': []},
}


@pytest.mark.parametrize('reading, problem', [
    (dict(FULL, project='p9'), 'project'),
    (dict(FULL, project='m1'), 'project'),
    (dict(FULL, conflicts=[{'ref': 'k3', 'why': 'w'}]), 'conflicts'),     # candidate, not notes
    (dict(FULL, conflicts=[{'ref': 'k4', 'why': 'w'}]), 'conflicts'),     # not deciding
    ({'kind': 'continue_work'}, 'continue_work names'),
    ({'kind': 'continue_work', 'target': 'm2'}, 'open mission'),
    (dict(FULL, target='m1'), 'idea handle'),
    ({'kind': 'new_work', 'objective': 'o'}, 'title'),
    ({'kind': 'idea'}, 'objective'),
    ({'kind': 'question'}, 'claims'),
    ({'kind': 'question', 'answer': [{'text': 'x', 'refs': []}]}, 'cites nothing'),
    ({'kind': 'question', 'answer': [{'text': 'x', 'refs': ['z9']}]}, 'answer[0].refs'),
    ({'kind': 'preference', 'feedback': {'signal': 'positive'}}, 'feedback.title'),
    ({'kind': 'preference', 'feedback': {'signal': 'correction', 'title': 't',
                                         'supersedes': 'u2'}}, 'supersedes'),
    ({'kind': 'feedback'}, 'carries its feedback'),
    ({'kind': 'feedback', 'target': 'p1', 'feedback': {'signal': 'positive'}}, 'target'),
    (dict(FULL, mentions=[{'name': 'x', 'kind': 'project', 'ref': 'm1'}]), 'mentions'),
])
def test_u04_core_refuses_a_reading_it_cannot_apply(reading, problem):
    got = brain.check(reading, FACTS)
    assert got and any(problem in p for p in got), got


def test_u04b_a_well_formed_reading_holds():
    assert brain.check(FULL, FACTS) == []
    assert brain.check(dict(FULL, conflicts=[{'ref': 'k2', 'why': 'notes'}]), FACTS) == []
    assert brain.check({'kind': 'preference', 'feedback': {
        'signal': 'correction', 'title': 't', 'supersedes': 'u1'}}, FACTS) == []
    assert brain.check({'kind': 'continue_work', 'target': 'm1'}, FACTS) == []


# ── U05 resolution replaces every handle with the object it names ──

def test_u05_resolve_names_objects_never_handles():
    p = brain.resolve(dict(FULL, feedback={'signal': 'correction', 'title': 't',
                                           'supersedes': 'u1'}), FACTS)
    assert p['project'] == {'kind': 'project', 'id': 'prj_1'}
    assert p['conflicts'][0]['ref'] == {'kind': 'knowledge_item', 'id': 'kno_1'}
    assert p['feedback']['supersedes'] == 'kno_5'       # the message's promoted item
    assert p['mentions'][0]['ref'] is None


def test_u06_handles_skip_the_subject_and_count_per_kind():
    pkg = {'subject_id': 'msg_0', 'items': [
        {'ref': {'kind': 'message', 'id': 'msg_0'}}, {'ref': {'kind': 'message', 'id': 'msg_1'}},
        {'ref': {'kind': 'project', 'id': 'prj_1'}}, {'ref': {'kind': 'event', 'id': 'e'}},
        {'ref': {'kind': 'project', 'id': 'prj_2'}}]}
    assert [h for h, _r in brain.handles(pkg)] == ['u1', 'p1', 'p2']


# ── U07–U08 boundaries ──

P7_FILES = [os.path.join(ROOT, *p) for p in (
    ('archeus', 'core', 'brain', 'intent.py'), ('archeus', 'core', 'missions', 'intent.py'),
    ('archeus', 'core', 'application', 'conversation.py'),
    ('archeus', 'core', 'application', 'grammar.py'))]
#: what the intent path must never reach: providers, processes, legacy UI and
#: memory, and the later phases' engines
BANNED = ('subprocess', 'llmcall', 'memory', 'gui_api', 'ui', 'tui', 'rotate', 'quota',
          'harnesses', 'planning', 'planner', 'policy', 'router', 'engine', 'work', 'node')


def test_u07_the_intent_path_imports_no_provider_process_ui_or_later_phase():
    for path in P7_FILES:
        tree = ast.parse(open(path, encoding='utf-8').read())
        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] + [getattr(n, 'module', None) or '']
                for name in names:
                    assert not any(b in name.split('.') for b in BANNED), (path, name)


def test_u08_importing_the_intent_path_loads_no_ui_memory_or_harness_runner():
    code = ('import sys; import archeus.core.missions.intent, archeus.core.brain.intent, '
            'archeus.core.application.conversation; '
            "bad=[m for m in sys.modules if m.split('.')[-1] in ('gui_api','memory','ui',"
            "'llmcall','rotate','quota') or m.startswith('archeus.harnesses.calls')]; "
            'print(bad); sys.exit(1 if bad else 0)')
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
