"""T-1093 step 1 through Core: a consolidation the user asks for adds CANDIDATEs that
name what they would supersede and changes nothing else, once per project per day;
and a project's `context injection` opt-in, off unless set, is the only way the
mission's context package reaches an execution's prompt. Fake adapters only."""

import json

import pytest

from archeus.core.application import knowledge as K
from archeus.core.application import lifecycle
from archeus.core.domain import entities, ids
from archeus.infra.artifacts import store
from archeus.infra.db import rows
from archeus.infra.paths import ExecPaths

from v1.integration.test_knowledge import fake, make, project  # noqa: F401 (fixture)
from v1.integration.test_settings_sources import opt, ready_in, run_one, x  # noqa: F401

QUOTE = 'Module directories:'


def confirmed(r, project_id):
    for k in r.items(project_id=project_id, type='ENTITY'):
        r.run(K.confirm, knowledge_item_id=k.id)
    return {k.title: k for k in r.items(project_id=project_id, type='ENTITY')}


def consolidations(r, project_id):
    got = r.read(lambda c: rows.where(c, entities.RouteDecision, purpose='knowledge_extraction',
                                      project_id=project_id))
    return [d.entity for d in got if d.entity.source.kind == 'project']


def test_a_consolidation_only_adds_candidates_and_runs_once_a_day(make):  # noqa: F811
    caller = fake()
    r = make([caller])
    repo = project(r)
    pid = repo.project_id
    known = confirmed(r, pid)
    core, api = known['core'], known['api']
    caller._replies['knowledge_extraction'] = [{'parsed': {'items': [
        {'id': core.id, 'verdict': 'supersede', 'title': 'core', 'text': 'The domain, again.',
         'quote': QUOTE},
        {'id': api.id, 'verdict': 'supersede', 'title': 'api', 'text': 'x',
         'quote': 'words the facts never had'},
        {'id': ids.new_id('knowledge_item'), 'verdict': 'supersede', 'title': 'ghost',
         'quote': QUOTE}]}}]
    before = len(caller.sent)
    r.run(K.request_consolidation, project_id=pid, max_items=5)
    r.settle()
    assert len(caller.sent) == before + 1
    spec, prompt = caller.sent[-1]
    assert spec.no_tools is True and core.id in prompt and api.id in prompt
    (d,) = consolidations(r, pid)
    assert {k: d.outcome[k] for k in ('state', 'items', 'kept', 'flagged', 'dropped')} == {
        'state': 'ok', 'items': 1, 'kept': 0, 'flagged': [api.id], 'dropped': 1}
    (new,) = [k for k in r.items(project_id=pid) if k.supersedes_id]
    assert (new.state, new.supersedes_id, new.origin, new.source_kind) == (
        'CANDIDATE', core.id, 'inferred', 'inspection')
    assert new.route_decision_id == d.id and new.source_ref == core.source_ref
    states = {k.id: k.state for k in r.items(project_id=pid)}
    assert (states[core.id], states[api.id], len(states)) == ('CONFIRMED', 'CONFIRMED', 3)
    # a second ask that day: no call, nothing new
    r.run(K.request_consolidation, project_id=pid, max_items=5)
    r.settle()
    assert len(caller.sent) == before + 1 and len(consolidations(r, pid)) == 1
    # only the user's confirm makes the replacement take effect
    r.run(K.confirm, knowledge_item_id=new.id)
    assert {k.id: k.state for k in r.items(project_id=pid)}[core.id] == 'SUPERSEDED'


def test_a_flag_a_keep_and_a_second_replacement_for_the_same_item_change_nothing(make):  # noqa: F811
    caller = fake()
    r = make([caller])
    pid = project(r).project_id
    known = confirmed(r, pid)
    core, api = known['core'], known['api']
    caller._replies['knowledge_extraction'] = [{'parsed': {'items': [
        {'id': core.id, 'verdict': 'supersede', 'title': 'core 1', 'quote': QUOTE},
        {'id': core.id, 'verdict': 'supersede', 'title': 'core 2', 'quote': QUOTE},
        {'id': api.id, 'verdict': 'flag'}, {'id': api.id, 'verdict': 'keep'}]}}]
    r.run(K.request_consolidation, project_id=pid)
    r.settle()
    (d,) = consolidations(r, pid)
    assert (d.outcome['items'], d.outcome['kept'], d.outcome['flagged']) == (
        1, 1, [core.id, api.id])


def test_nothing_to_consolidate_makes_no_call(make):  # noqa: F811
    caller = fake()
    r = make([caller])
    pid = project(r).project_id                      # its items are CANDIDATEs
    before = len(caller.sent)
    r.run(K.request_consolidation, project_id=pid)
    r.settle()
    assert len(caller.sent) == before and consolidations(r, pid) == []


# ── the A/B switch: a project's context injection ──

def remembered(rig, title, text):
    def put(tx, *, actor):
        p = lifecycle.load(tx, entities.Project, rig.prj).entity
        k = K.new_item(tx, actor=actor, workspace_id=p.workspace_id, project_id=p.id,
                       type='STANDARD', title=title, text=text, origin='explicit',
                       source_kind='user')
        return K.confirm(tx, actor=actor, knowledge_item_id=k.id)
    return rig.do(put, who=rig.user)


def prompt_of(e):
    with open(ExecPaths(e.id).prompt, encoding='utf-8') as f:
        return f.read()


def test_injection_is_off_by_default_and_the_prompt_is_todays(x):  # noqa: F811
    remembered(x, 'Layering rule', 'api above core')
    e = run_one(x, ready_in(x, x.prj))
    assert 'Layering rule' not in prompt_of(e) and 'Project memory' not in prompt_of(e)


def test_a_projects_injection_puts_its_confirmed_memory_in_the_prompt_and_records_the_arm(x):  # noqa: F811
    remembered(x, 'Layering rule', 'api above core, key sk-' + 'q' * 30)
    opt(x, x.prj, 'context', 'injection')
    e = run_one(x, ready_in(x, x.prj))
    text = prompt_of(e)
    assert 'Project memory Archeus selected' in text and 'Layering rule' in text
    assert 'q' * 30 not in text
    inv = json.loads(store.get(e.inventory_sha256))
    assert {'owner': 'project', 'kind': 'context', 'name': 'injection'} in inv['opt_ins']
    opt(x, x.prj, 'context', 'injection', opted_in=False)
    e2 = run_one(x, ready_in(x, x.prj))
    assert 'Project memory' not in prompt_of(e2)


def test_an_injection_opt_in_belongs_to_a_project_only(x):  # noqa: F811
    with pytest.raises(ValueError):
        opt(x, x.acc, 'context', 'injection')
    with pytest.raises(ValueError):
        opt(x, x.prj, 'context', 'everything')
