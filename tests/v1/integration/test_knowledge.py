"""P6 over a real database (p6-design-gate §12, N01–N24): the three passes, the
provider-terms gate in the call path, provenance, idempotency, relations,
supersession chains, forget, feedback, meetings, lessons and corroboration,
and every failure a call can have. Fake adapters only, plus the real adapters
against a stand-in runner: no real CLI is ever spawned."""

import os

import pytest

from archeus.core import engine, ports
from archeus.core.application import calls as C
from archeus.core.application import commands, lifecycle, queries
from archeus.core.application import knowledge as K
from archeus.core.calls import OwnCalls
from archeus.core.domain import entities
from archeus.core.knowledge import ingest
from archeus.core.knowledge.passes import Passes
from archeus.core.knowledge.worker import CONSUMER, Knowledge
from archeus.core.world import status as world_status
from archeus.harnesses import calls as real
from archeus.harnesses.fake import FakeCaller
from archeus.infra.db import rows
from v1.integration.test_world import NO_CORE_API, Harness

MS = commands.Missions(policy=ports.AllowAllPolicy())
GOOD = {'entities': [
    {'name': 'core', 'kind': 'module', 'module': 'app/core', 'summary': 'The domain.'},
    {'name': 'api', 'kind': 'module', 'module': 'app/api', 'summary': 'The HTTP layer.'}],
    'relations': [{'from': 'api', 'rel': 'depends_on', 'to': 'core'},
                  {'from': 'api', 'rel': 'uses', 'to': 'nowhere'}]}


class Real(FakeCaller):
    """A real-like adapter: scripted, but gated (the exemption is FakeCaller only)."""


class Rig(Harness):
    def __init__(self, db, parent, callers, preference=None):
        super().__init__(db, parent)
        self.callers = callers
        self.calls = OwnCalls(db, actor=self.system, callers=callers,
                              preference=preference or ports.FixedOwnCallPreference())
        self.passes = Passes(db, actor=self.system, calls=self.calls)
        self.knowledge = Knowledge(db, actor=self.system, passes=self.passes)

    def settle(self, limit=20):
        for _ in range(limit):
            moved = self.world.pass_once()['changed'] | self.knowledge.pass_once()['changed']
            if not moved:
                return
        raise AssertionError('did not settle')

    def kp(self, project_id):
        return self.read(world_status.knowledge_pass, project_id)

    def items(self, **eq):
        return self.read(lambda c: [r.entity for r in rows.where(c, entities.KnowledgeItem, **eq)])

    def count(self, cls):
        return self.read(lambda c: len(rows.where(c, cls)))


@pytest.fixture
def make(db, tmp_path):
    parent = tmp_path / 'repos'
    parent.mkdir()
    return lambda callers, preference=None: Rig(db, str(parent), callers, preference)


def fake(id_='fake', structured='native', **replies):
    return FakeCaller(id_, structured=structured, replies=replies or {
        'knowledge_extraction': [{'parsed': GOOD}]})


def project(r, constraints=()):
    repo = r.register('layered-python', list(constraints))
    r.settle()
    return repo


# ── N01–N04 the provider-terms gate, in the call path ──

def test_n01_a_real_adapter_is_never_called_before_the_user_permits_it(make):
    gated = Real('pi', replies={'knowledge_extraction': [{'parsed': GOOD}]})
    r = make([gated])
    repo = project(r)
    kp = r.kp(repo.project_id)
    assert (kp['state'], kp['items']) == ('gated', 0)
    assert gated.sent == []                                    # never invoked
    rd = r.read(queries.get_route_decision, kp['route_decision_id'])
    assert rd['selected'] is None and rd['usage'] == []
    assert rd['candidates'][0]['eliminated_at_step'] == 'provider_terms'


def test_n02_permitting_headless_use_runs_every_gated_pass_again(make):
    gated = Real('pi', replies={'knowledge_extraction': [{'parsed': GOOD}]})
    r = make([gated])
    repo = project(r)
    r.run(C.decide_provider_terms, harness_id='pi', headless='permitted')
    r.settle()
    kp = r.kp(repo.project_id)
    assert (kp['state'], kp['items']) == ('ok', 2) and len(gated.sent) == 1
    assert [e['payload']['headless'] for e in r.events('provider_terms.decided')] == [
        'permitted']


def test_n03_the_terms_are_read_again_immediately_before_the_spawn(make, monkeypatch):
    """Permitted at the election, refused by the time of the call: no call."""
    gated = Real('pi', replies={'knowledge_extraction': [{'parsed': GOOD}]})
    r = make([gated])
    r.run(C.decide_provider_terms, harness_id='pi', headless='permitted')
    reads = []
    real_terms = C.terms

    def flip(conn):
        reads.append(1)
        got = real_terms(conn)
        if len(reads) > 1:
            got['pi'] = entities.ProviderTerms(id='pi', headless='refused')
        return got
    monkeypatch.setattr(C, 'terms', flip)
    repo = project(r)
    kp = r.kp(repo.project_id)
    assert (kp['state'], kp['reason']) == ('gated', 'provider terms refused')
    assert gated.sent == []


def test_n04_only_the_user_answers_the_terms_question(make):
    r = make([fake()])
    with pytest.raises(ValueError, match='only the user'):
        r.db.writer.execute(C.decide_provider_terms, {'actor': r.system, 'harness_id': 'pi',
                                                     'headless': 'permitted'})
    out = r.run(C.decide_provider_terms, harness_id='pi', headless='refused', note='not ours')
    assert out['provider_terms']['headless'] == 'refused'
    out = r.run(C.decide_provider_terms, harness_id='pi', headless='permitted',
                rotation='refused')
    assert (out['provider_terms']['headless'], out['provider_terms']['rotation']) == (
        'permitted', 'refused')
    with pytest.raises(ValueError):
        r.run(C.decide_provider_terms, harness_id='pi', headless='maybe')


def test_n05_a_real_adapter_passes_the_gate_and_its_argv_is_the_harness_own(make, monkeypatch):
    """The whole path with the real pi adapter and a stand-in runner: terms
    permitted, pi's flags, pi's vocabulary, prompted schema, Core validation."""
    from claude_sessions import harnesses, llmcall
    seen = []
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: 'C:/x/pi.exe')
    monkeypatch.setattr(harnesses, 'disabled', lambda: set())
    import json
    monkeypatch.setattr(llmcall, 'run_headless', lambda cmd, stdin=None, **kw: (
        seen.append((cmd, stdin)), llmcall.Result(0, 'ok ' + json.dumps(GOOD), '', '', False))[1])
    r = make([real.PiCaller()], ports.FixedOwnCallPreference(model='spark/qwen3.8'))
    r.run(C.decide_provider_terms, harness_id='pi', headless='permitted')
    repo = project(r)
    kp = r.kp(repo.project_id)
    assert (kp['state'], kp['items']) == ('ok', 2)
    (cmd, stdin), = seen
    assert cmd[1:] == ['-p', '--no-session', '--tools', 'read,grep,find,ls', '--model',
                       'spark/qwen3.8']
    assert 'matching this JSON Schema' in stdin


# ── N06–N08 provenance, no execution, usage ──

def test_n06_every_learned_item_says_where_it_came_from_and_what_made_it(make):
    r = make([fake('fake_local', 'prompted')], ports.FixedOwnCallPreference(model='local/m'))
    repo = project(r)
    items = r.items(project_id=repo.project_id, type='ENTITY')
    assert sorted(i.title for i in items) == ['api', 'core']
    rd_id = items[0].route_decision_id
    rd = r.read(queries.get_route_decision, rd_id)
    insp = r.repo(repo.repository_id).last_inspection_id
    for i in items:
        assert (i.state, i.origin, i.source_kind) == ('CANDIDATE', 'inferred', 'inspection')
        assert (i.source_ref.kind, i.source_ref.id) == ('repository_inspection', insp)
        assert i.route_decision_id == rd_id and i.observed_at
        assert i.context_package_id == rd['context_package_id'] is not None
        assert i.confidence is None                    # never invented
    assert (rd['selected'], rd['model'], rd['decided_by']) == ('fake_local', 'local/m',
                                                              'pre_router')
    assert rd['account_ref'] is None and rd['outcome']['account_ref'] == 'fake:fake_local'
    pkg = r.read(queries.get_context_package, rd['context_package_id'])
    assert (pkg['subject_kind'], pkg['subject_id']) == ('project', repo.project_id)


def test_n07_an_own_call_is_no_execution_and_its_usage_is_on_its_route_decision(make):
    r = make([fake()])
    repo = project(r)
    assert r.count(entities.Execution) == 0 and r.count(entities.Mission) == 0
    rd = r.read(queries.get_route_decision, r.kp(repo.project_id)['route_decision_id'])
    (u,) = rd['usage']
    assert (u['route_decision_id'], u['execution_id'], u['tokens_in'], u['tokens_out']) == (
        rd['id'], None, 10, 5)
    assert [e['subject']['id'] for e in r.events('route.decided')] == [rd['id']]
    assert [e['payload']['outcome']['state'] for e in r.events('archeus_call.ended')] == ['ok']


def test_n08_relations_are_inferred_and_a_dangling_end_is_dropped_and_counted(make):
    r = make([fake()])
    repo = project(r)
    kp = r.read(queries.get_route_decision, r.kp(repo.project_id)['route_decision_id'])
    assert (kp['outcome']['relations'], kp['outcome']['dropped']) == (1, 1)
    (rel,) = r.read(lambda c: [x.entity for x in rows.where(c, entities.Relation)])
    by = {i.id: i.title for i in r.items(project_id=repo.project_id)}
    assert (by[rel.src_id], rel.rel, by[rel.dst_id], rel.confidence_tier) == (
        'api', 'depends_on', 'core', 'INFERRED')


def test_n09_contradicts_needs_an_item_the_call_was_shown_and_changes_no_state(make):
    r = make([fake(knowledge_extraction=[{'parsed': dict(GOOD, contradicts=[])}])])
    repo = r.register('layered-python', [NO_CORE_API])
    arch = r.items(project_id=repo.project_id, type='ARCHITECTURE')[0]
    r.callers[0]._replies['knowledge_extraction'] = [{'parsed': dict(GOOD, contradicts=[
        {'entity': 'api', 'existing': arch.id, 'why': 'core imports it'},
        {'entity': 'api', 'existing': 'kno_01J00000000000000000000000', 'why': 'unknown'}])}]
    r.settle()
    rels = r.read(lambda c: [x.entity for x in rows.where(c, entities.Relation,
                                                          rel='contradicts')])
    assert [(x.dst_id, x.confidence_tier) for x in rels] == [(arch.id, 'INFERRED')]
    assert r.items(project_id=repo.project_id, type='ARCHITECTURE')[0].state == 'CONFIRMED'


# ── N10–N12 idempotency ──

def test_n10_a_redelivered_event_learns_nothing_twice(make):
    r = make([fake()])
    repo = project(r)
    before = (r.count(entities.KnowledgeItem), r.count(entities.RouteDecision))
    def rewind(tx, *, actor):
        tx.execute('DELETE FROM consumer_effects WHERE consumer = ?', (CONSUMER,))
        tx.execute('UPDATE consumer_cursors SET last_seq = 0 WHERE name = ?', (CONSUMER,))
    r.db.writer.execute(rewind, {'actor': r.system})
    r.settle()
    assert (r.count(entities.KnowledgeItem), r.count(entities.RouteDecision)) == before


def test_n11_the_same_pass_run_again_finds_what_it_already_knows(make):
    r = make([fake()])
    repo = project(r)
    insp = r.repo(repo.repository_id).last_inspection_id
    assert r.passes.knowledge(insp) == 'ok'
    rds = r.read(lambda c: queries.route_decisions(c, insp))
    assert (rds[-1]['outcome']['items'], rds[-1]['outcome']['duplicates']) == (0, 2)
    assert len(r.items(project_id=repo.project_id, type='ENTITY')) == 2


def test_n12_a_later_inspection_does_not_queue_a_second_initial_pass(make):
    r = make([fake()])
    repo = project(r)
    repo.commit('more', {'app/core/y.py': 'x = 1\n'})
    r.settle()
    assert len(r.read(lambda c: queries.route_decisions(c, purpose='knowledge_extraction'))) == 1


# ── N13–N17 failures: each is named, none is success, none fails the project ──

@pytest.mark.parametrize('reply,state', [
    ({'error': 'model_unavailable', 'detail': 'no such model'}, 'model_unavailable'),
    ({'error': 'timeout', 'detail': 'slow'}, 'timeout'),
    ({'error': 'failed', 'detail': 'crashed'}, 'failed'),
    ({'text': 'no json here'}, 'invalid'),
    ({'parsed': {'entities': [{'name': ' ', 'kind': 'module', 'summary': 's'}]}}, 'invalid'),
], ids=['model', 'timeout', 'failed', 'malformed', 'invalid'])
def test_n13_a_failed_call_learns_nothing_and_says_why(make, reply, state):
    r = make([fake(knowledge_extraction=[reply])])
    repo = project(r)
    kp = r.kp(repo.project_id)
    assert (kp['state'], kp['items']) == (state, 0)
    assert r.items(project_id=repo.project_id, state='CANDIDATE') == []
    assert r.read(lambda c: rows.get(c, entities.Project, repo.project_id)).entity.state == \
        'ACTIVE'


def test_n14_no_harness_installed_is_unavailable(make):
    r = make([FakeCaller('gone', installed=False)])
    assert r.kp(project(r).project_id)['state'] == 'unavailable'


def test_n15_an_account_that_cannot_be_spent_is_unavailable(make):
    class Spent(FakeCaller):
        def account(self, *, rotation):
            return self._acct, 'account rate-limited by Claude'
    s = Spent('fake')
    s._acct = __import__('archeus.harnesses.base', fromlist=['AccountRef']).AccountRef('a')
    r = make([s])
    r.run(C.decide_provider_terms, harness_id='fake', headless='permitted')
    kp = r.kp(project(r).project_id)
    assert (kp['state'], kp['reason']) == ('unavailable', 'account rate-limited by Claude')
    assert s.sent == []


def test_n16_an_adapter_that_raises_is_a_failed_call_not_a_dead_worker(make):
    class Broken(FakeCaller):
        def call(self, spec):
            raise RuntimeError('boom')
    r = make([Broken('fake')])
    r.run(C.decide_provider_terms, harness_id='fake', headless='permitted')
    kp = r.kp(project(r).project_id)
    assert (kp['state'], kp['reason']) == ('failed', 'RuntimeError: boom')


def test_n17_a_result_that_cannot_be_recorded_leaves_nothing_and_ends_the_call(make,
                                                                               monkeypatch):
    def fail(tx, **kw):
        K.new_item(tx, actor=kw['actor'], workspace_id='ws_global', type='ENTITY', title='x')
        raise RuntimeError('disk full')
    monkeypatch.setattr(K, 'record_knowledge_pass', fail)
    r = make([fake()])
    repo = project(r)
    kp = r.kp(repo.project_id)
    assert kp['state'] == 'failed' and 'disk full' in kp['reason']
    assert r.items(type='ENTITY') == []                          # the transaction rolled back


def test_n18_a_call_left_open_by_a_dead_core_is_ended_at_the_next_start(make):
    r = make([fake()])
    rd = r.db.writer.execute(C.decide_route, {
        'actor': r.system, 'purpose': 'lesson', 'source': {'kind': 'mission', 'id': 'msn_x'},
        'workspace_id': 'ws_global', 'project_id': None, 'selected': 'fake',
        'account_ref': None, 'model': None, 'candidates': [], 'requirements': {},
        'input_snapshot': {}, 'explanation': 'x'})['route_decision_id']
    assert r.knowledge.sweep() == [rd]
    assert r.read(queries.get_route_decision, rd)['outcome'] == {'state': 'failed',
                                                                 'reason': 'core_restarted'}


# ── N19–N21 the lifecycle: supersession chains, forget, feedback ──

def test_n19_a_supersession_chain_keeps_every_link_and_deletes_nothing(make):
    r = make([fake()])
    repo = project(r, [NO_CORE_API])
    (a,) = r.items(project_id=repo.project_id, type='ARCHITECTURE')
    b = r.run(K.supersede, knowledge_item_id=a.id, title='core never imports api or db')
    c = r.run(K.supersede, knowledge_item_id=b['knowledge_item']['id'],
              title='core imports nothing outside core')
    got = {i.id: i for i in r.items(project_id=repo.project_id, type='ARCHITECTURE')}
    bid, cid = b['knowledge_item']['id'], c['knowledge_item']['id']
    assert (got[a.id].state, got[bid].state, got[cid].state) == (
        'SUPERSEDED', 'SUPERSEDED', 'CONFIRMED')
    assert (got[a.id].superseded_by_id, got[bid].superseded_by_id) == (bid, cid)
    assert got[a.id].valid_until and got[cid].valid_until is None
    assert r.read(queries.get_knowledge, bid)['chain'] == [a.id, bid, cid]
    # only a CONFIRMED item can be superseded
    with pytest.raises(ValueError, match='only a CONFIRMED item'):
        r.run(K.supersede, knowledge_item_id=a.id, title='again')


def test_n20_forget_is_a_dry_run_by_default_and_purge_keeps_a_tombstone(make):
    r = make([fake()])
    repo = project(r)
    sel = {'project_id': repo.project_id, 'type': 'ENTITY'}
    before = [(i.id, i.state, i.title) for i in r.items(**{'type': 'ENTITY'})]
    dry = r.run(K.forget, selector=sel, mode='purge')
    assert dry['dry_run'] and len(dry['changes']) == 2 and not dry['changed']
    assert [(i.id, i.state, i.title) for i in r.items(type='ENTITY')] == before
    out = r.run(K.forget, selector=sel, mode='purge', dry_run=False)
    assert out['changed']
    for i in r.items(type='ENTITY'):
        assert (i.state, i.title, i.text, i.purged) == ('RETRACTED', '[purged]', '', True)
        assert i.route_decision_id and i.source_ref is not None      # provenance kept
    assert len(r.events('knowledge_item.purged')) == 2
    assert r.run(K.forget, selector=sel, mode='purge', dry_run=False)['changes'] == []


def test_n21_feedback_promotes_a_candidate_that_supersedes_only_once_confirmed(make):
    r = make([fake()])
    repo = project(r, [NO_CORE_API])
    (a,) = r.items(project_id=repo.project_id, type='ARCHITECTURE')
    fb = r.run(K.record_feedback, subject={'kind': 'knowledge_item', 'id': a.id},
               signal='correction', text='we changed our mind',
               promote={'type': 'PREFERENCE', 'title': 'prefer a flat layout',
                        'supersedes_id': a.id})
    new = fb['promoted']
    assert (new['state'], new['origin'], new['supersedes_id']) == ('CANDIDATE', 'explicit',
                                                                  a.id)
    (e,) = r.events('feedback.received')
    assert e['payload']['promoted']['id'] == new['id']
    assert r.items(type='ARCHITECTURE')[0].state == 'CONFIRMED'        # not yet
    r.run(K.confirm, knowledge_item_id=new['id'])
    assert r.items(type='ARCHITECTURE')[0].state == 'SUPERSEDED'
    with pytest.raises(ValueError):
        r.run(K.record_feedback, subject={'kind': 'repository', 'id': 'rep_x'},
              signal='positive')


# ── N22–N23 meetings and decisions ──

def test_n22_a_meeting_is_imported_once_and_its_decisions_are_candidates(make, tmp_path):
    notes = tmp_path / 'planning-2026-09-20.md'
    notes.write_text('# Planning\nDECISION: the dashboard ships dark-first.\n',
                     encoding='utf-8')
    r = make([fake(knowledge_extraction=[{'parsed': {'decisions': [
        {'statement': 'The dashboard ships dark-first', 'rationale': 'most use is at night'}]}}])])
    first = ingest.import_file(r.db, r.user, str(notes))
    again = ingest.import_file(r.db, r.user, str(notes))
    assert (first['changed'], again['changed']) == (True, False)
    assert first['meeting']['id'] == again['meeting']['id']
    assert (first['meeting']['name'], first['meeting']['held_at']) == ('Planning', '2026-09-20')
    r.settle()
    (d,) = r.items(type='DECISION')
    assert (d.state, d.origin, d.source_kind, d.source_ref.id) == (
        'CANDIDATE', 'inferred', 'import', first['meeting']['id'])
    (rel,) = r.read(lambda c: [x.entity for x in rows.where(c, entities.Relation,
                                                           rel='decided_in')])
    assert (rel.dst_id, rel.confidence_tier) == (first['meeting']['id'], 'EXTRACTED')
    assert len(r.events('meeting.imported')) == 1


def test_n23_notes_with_no_date_are_refused_rather_than_guessed(tmp_path):
    p = tmp_path / 'notes.md'
    p.write_text('# Sync\nnothing dated\n', encoding='utf-8')
    with pytest.raises(ValueError, match='no date'):
        ingest.read_notes(str(p))
    assert ingest.read_notes(str(p), held_at='2026-09-01')['held_at'] == '2026-09-01'


# ── N24 lessons and corroboration ──

def test_n24_a_lesson_confirms_itself_only_when_two_missions_corroborate_it(archeus_home):
    """Three missions run to COMPLETED on the walking-skeleton engine; the
    lesson pass follows each. The same lesson from two distinct missions
    confirms itself; a differently titled one does not; model confidence is
    not an input at all."""
    from v1.judge.client import InProcessClient
    lesson = {'lessons': [{'title': 'Pin the formatter', 'text': 'it drifts',
                           'outcome': 'failed'}]}
    other = {'lessons': [{'title': 'Pin the formatter version', 'text': 'x',
                          'outcome': 'worked'}]}
    c = InProcessClient(archeus_home, callers=[fake(lesson=[
        {'parsed': lesson}, {'parsed': other}, {'parsed': lesson}])],
        preference=ports.FixedOwnCallPreference(),
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN))      # about lessons, not planning

    def finish(title):
        mid = c.create_mission(title=title, objective='o')['id']
        for _ in range(200):
            if c._idle() and c.get_mission(mid)['state'] == 'COMPLETED':
                return mid
        raise AssertionError('mission %s did not complete' % mid)

    def lessons():
        return {i['title']: i for i in c.list_knowledge(state=None) if i['type'] == 'LESSON'}
    try:
        m1 = finish('one')
        assert [x['state'] for x in lessons().values()] == ['CANDIDATE']
        finish('two')
        assert sorted(x['state'] for x in lessons().values()) == ['CANDIDATE', 'CANDIDATE']
        m3 = finish('three')
        got = lessons()
        assert got['Pin the formatter']['state'] == 'CONFIRMED'
        assert got['Pin the formatter version']['state'] == 'CANDIDATE'
        rels = {r['dst_id'] for r in c._read(queries.get_knowledge,
                                             got['Pin the formatter']['id'])['relations']
                if r['rel'] == 'learned_from'}
        assert rels == {m1, m3}
        assert len(lessons()) == 2
    finally:
        c.close()
