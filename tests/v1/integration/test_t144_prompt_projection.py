"""T-144 slice 5: the two model prompts that were built from raw rows. The review prompt
carries the agent's own claim (a system-owned string, projected with the live homes and
capped after the projection); the intent brain's context lines project the project root
paths, a knowledge item's text and an Archeus or system turn, and leave what the user
typed (a user turn, mission and idea titles, a project name) as it is. Stored rows stay raw."""

from archeus.core.brain import intent as brain
from archeus.core.domain import entities, ids
from archeus.core.application import resources
from archeus.core.verification import reviewer
from archeus.infra.db import rows
from v1.integration.test_graph_query import WS, put
from v1.integration.test_intent import Rig as IntentRig, brain as brain_caller, make  # noqa: F401
from v1.integration.test_t144_leak_sweep import HomeCaller
from v1.integration.test_verification import (  # noqa: F401  (core is a fixture)
    FIX, Rig, SimpleNamespace, _mission, _write, core, pump, _state)


def test_the_review_prompt_projects_the_agent_claim_and_caps_it_after(core, monkeypatch, tmp_path):
    home = str(tmp_path / 'Review-Live-Only')
    db = core._core()
    registry, callers = db.writer.live
    db.writer.live = (registry, [*callers, HomeCaller(home, 'review-live')])
    claim = 'x' * 440 + ' read ' + home + '/settings.json and then ' + 'y' * 100
    _repo, mid = _mission(core, Rig(core), steps=[_write(FIX), {'emit': {
        'type': 'result', 'summary': claim}}])
    pump(core, lambda: _state(core, mid) == 'REVIEWING')
    seen = []
    monkeypatch.setattr(core._verify, 'calls', SimpleNamespace(
        run=lambda **ask: seen.append(ask) or SimpleNamespace(state='error')))
    core._verify._review(mid)
    text = seen[0]['prompt']
    (line,) = [x for x in text.split('\n') if 'CLAIM by the agent' in x]
    assert home not in text and 'Review-Live' not in text
    assert line.split(': ', 1)[1].startswith('x' * 440 + ' read its home/settings.json')
    assert len(line.split(': ', 1)[1]) == 500, 'the cap applies to the projected text'
    with db.read() as conn:
        assert any(r.entity.summary == claim for r in rows.where(conn, entities.Execution)), \
            'the stored summary stays raw'


def test_the_review_prompt_cap_never_leaves_a_prefix_of_a_home(core, tmp_path):
    home = str(tmp_path / 'Review-Cut-Home')
    db = core._core()
    claim = 'z' * (500 - 1 - (len(home) - 7)) + ' ' + home          # the raw cap lands inside the name
    _repo, mid = _mission(core, Rig(core), steps=[_write(FIX), {'emit': {
        'type': 'result', 'summary': claim}}])
    pump(core, lambda: _state(core, mid) == 'REVIEWING')
    registry, callers = db.writer.live
    db.writer.live = (registry, [*callers, HomeCaller(home, 'review-cut')])
    with db.read() as conn:
        m = rows.get(conn, entities.Mission, mid).entity
        text = reviewer.prompt(conn, m, None, resources.bound_homes(conn, db.writer.live))
    (line,) = [x for x in text.splitlines() if 'CLAIM by the agent' in x]
    assert 'Review-Cut' not in text and line.endswith(' its home')


def _describe(db, tmp_path, items, live):
    db.writer.live = (None, [HomeCaller(live, 'brain-live')])
    pkg = {'subject_id': 'none', 'items': [
        {'ref': {'kind': k, 'id': i}, 'type': 't', 'reason': 'r'} for k, i in items]}
    with db.read() as conn:
        return brain.describe(conn, pkg, resources.bound_homes(conn, db.writer.live))[0]


def test_the_brain_context_projects_roots_knowledge_and_system_turns_not_user_text(db, tmp_path):
    live = str(tmp_path / 'Brain-Live-Only')
    prj, kid, conv = ids.new_id('project'), ids.new_id('knowledge_item'), ids.new_id('conversation')
    umsg, amsg = ids.new_id('message'), ids.new_id('message')
    put(db, entities.Project(id=prj, workspace_id=WS, name='Atlas ' + live,
                             root_paths=[live + '/repo', '/plain/root']),
        entities.KnowledgeItem(id=kid, workspace_id=WS, type='FACT', title='seen in ' + live,
                               text='path ' + live + '/x', state='CONFIRMED'),
        entities.Conversation(id=conv, kind='primary'),
        entities.Message(id=umsg, conversation_id=conv, author='user',
                         text='please look at ' + live),
        entities.Message(id=amsg, conversation_id=conv, author='archeus',
                         text='I opened ' + live + '/settings.json'))
    lines = _describe(db, tmp_path, [('project', prj), ('knowledge_item', kid),
                                     ('message', umsg), ('message', amsg)], live)
    by = {x.split(']')[0][1:]: x.split('] ', 1)[1] for x in lines}
    assert by == {
        'p1': 'project: Atlas %s (its home/repo, /plain/root)' % live,
        'k1': 'FACT CONFIRMED: seen in its home. path its home/x',
        'u1': 'earlier user turn: please look at ' + live,
        'u2': 'earlier archeus turn: I opened its home/settings.json'}
    with db.read() as conn:
        assert rows.get(conn, entities.KnowledgeItem, kid).entity.text == 'path ' + live + '/x'


def test_the_brain_call_is_built_with_the_bound_homes(make, tmp_path):  # noqa: F811
    r = make([brain_caller(('Add a flag', {'kind': 'question', 'answer': [
        {'text': 'ok', 'refs': []}]}))])
    prj = r.register('layered-python').project_id
    with r.db.read() as conn:
        (root,) = rows.get(conn, entities.Project, prj).entity.root_paths
    r.db.writer.live = (None, [HomeCaller(root, 'intent-live')])
    r.say('Add a flag')
    _spec, prompt = r.callers[0].sent[-1]
    assert root not in prompt and 'its home' in prompt
