"""P7 over a real database (p7-design-gate §12, I01–I20): the intent pipeline —
grammar, the brain call through `archeus_call`, Core's validation and the
deterministic application — and every boundary it keeps. Fake adapters only:
no real CLI is ever spawned."""

import pytest

from archeus.core import ports
from archeus.core.application import commands, grammar, queries
from archeus.core.application import knowledge as K
from archeus.core.application.conversation import Conversations, post_message
from archeus.core.domain import entities, ids
from archeus.core.knowledge import ingest
from archeus.core.missions.intent import CONSUMER, Intents
from archeus.harnesses.fake import FakeCaller
from archeus.infra.db import rows
from v1.integration.test_knowledge import Real, Rig as KRig

MS = commands.Missions(policy=ports.AllowAllPolicy())


class Rig(KRig):
    def __init__(self, db, parent, callers, preference=None):
        super().__init__(db, parent, callers, preference)
        self.conv = Conversations(missions=MS)
        self.intents = Intents(db, actor=self.system, calls=self.calls,
                               conversations=self.conv)

    def settle(self, limit=30):
        for _ in range(limit):
            moved = (self.world.pass_once()['changed'] | self.knowledge.pass_once()['changed']
                     | self.intents.pass_once()['changed'])
            if not moved:
                return
        raise AssertionError('did not settle')

    def say(self, text, key=None, in_reply_to=None):
        """Post a user turn, settle, and return (the reply, the intent)."""
        posted = self.run(post_message, key=key, text=text, in_reply_to=in_reply_to)
        self.settle()
        reply = self.read(queries.reply_to, posted['message_id'])
        it = self.read(lambda c: [r.entity for r in rows.where(
            c, entities.Intent, message_id=posted['message_id'])])
        return reply, (it[0] if it else None)

    def all(self, cls, **eq):
        return self.read(lambda c: [r.entity for r in rows.where(c, cls, **eq)])


@pytest.fixture
def make(db, tmp_path):
    parent = tmp_path / 'repos'
    parent.mkdir()
    return lambda callers, preference=None: Rig(db, str(parent), callers, preference)


def brain(*recordings, id_='fake', structured='native', **extra):
    """A fake harness answering intent.v1 from (utterance, parsed) pairs."""
    replies = {'brain': [{'when': 'The message:\n' + u, 'parsed': p} for u, p in recordings]}
    replies.update(extra)
    return FakeCaller(id_, structured=structured, replies=replies)


WORK = {'kind': 'new_work', 'title': 'Add a --version flag', 'objective': 'The CLI prints it.',
        'requirements': [{'text': 'a --version flag', 'origin': 'explicit'},
                         {'text': 'it prints the installed version', 'origin': 'inferred'}]}


# ── I01–I02 a question is not work; work is one mission ──

def test_i01_a_question_about_work_is_answered_and_makes_no_mission(make):
    r = make([brain(('Can you add a flag, in principle?', {
        'kind': 'question', 'answer': [{'text': 'Yes; nothing is open yet.', 'refs': []}]}),
        ('How would pausing work?', {'kind': 'question', 'answer': [
            {'text': 'Say pause and the mission title.', 'refs': ['u1']}]}))])
    r.run(post_message, text='hello')                 # an earlier turn to cite
    reply, it = r.say('How would pausing work?')
    assert (it.kind, it.resolution, it.via) == ('question', 'answered', 'brain')
    assert reply['links'] and not r.all(entities.Mission)
    # a claim citing nothing is not an answer: invalid twice, declined
    reply, it = r.say('Can you add a flag, in principle?')
    assert it.resolution == 'declined' and not r.all(entities.Mission)


def test_i02_an_explicit_request_is_one_mission_with_its_provenance(make):
    r = make([brain(('Add a --version flag to the CLI', WORK))])
    reply, it = r.say('Add a --version flag to the CLI')
    (m,) = r.all(entities.Mission)
    assert (m.state, m.origin, m.origin_ref, it.resolution) == (
        'CREATED', 'conversation', reply['in_reply_to'], 'mission_created')
    assert [(c['text'], c['origin']) for c in m.requirements] == [
        ('a --version flag', 'explicit'), ('it prints the installed version', 'inferred')]
    rd = r.read(queries.get_route_decision, it.route_decision_id)
    assert (rd['purpose'], rd['outcome']['state'], rd['source']['kind']) == (
        'brain', 'ok', 'message')
    pkg = r.read(queries.get_context_package, it.context_package_id)
    assert (pkg['subject_kind'], pkg['subject_id']) == ('message', reply['in_reply_to'])
    assert rd['context_package_id'] == pkg['id']
    assert [c['type'] for c in reply['cards']] == ['mission_proposal']


# ── I03 continuation ──

def test_i03_a_continuation_updates_the_open_mission_and_never_duplicates_it(make):
    r = make([brain(('Add a --version flag to the CLI', WORK),
                    ('Also print the git hash.', {
                        'kind': 'continue_work', 'target': 'm1',
                        'requirements': [{'text': 'print the git hash', 'origin': 'explicit'}]}))])
    r.say('Add a --version flag to the CLI')
    reply, it = r.say('Also print the git hash.')
    (m,) = r.all(entities.Mission)
    assert it.resolution == 'mission_updated'
    assert [c['text'] for c in m.requirements][-1] == 'print the git hash'
    (e,) = r.events('mission.updated')
    assert e['subject']['id'] == m.id and e['payload']['fields'] == ['requirements']


def test_i03b_a_continuation_must_name_an_open_mission(make):
    r = make([brain(('More of that.', {'kind': 'continue_work', 'target': 'p1'}))])
    reply, it = r.say('More of that.')
    assert it.resolution == 'declined' and not r.all(entities.Mission)


# ── I04–I05 ambiguity and world references ──

def test_i04_material_ambiguity_asks_and_writes_no_mission(make):
    r = make([brain(('Redo the dashboard.', dict(WORK, ambiguities=[
        {'question': 'The web dashboard or the TUI one?', 'material': True}])),
        ('Redo the dashboard, the web one.', dict(WORK, ambiguities=[
            {'question': 'Keep the colours?', 'material': False}])))])
    reply, it = r.say('Redo the dashboard.')
    assert it.resolution == 'clarification_requested' and not r.all(entities.Mission)
    assert [c['type'] for c in reply['cards']] == ['clarification']
    assert 'web dashboard or the TUI' in reply['text']
    _reply, it = r.say('Redo the dashboard, the web one.')
    assert it.resolution == 'mission_created' and len(r.all(entities.Mission)) == 1


def test_i05_a_project_is_resolved_to_its_row_and_an_unknown_one_is_never_invented(make):
    r = make([brain(('Fix the layered dashboard.', dict(WORK, project='p1')),
                    ('Fix the Archeus dashboard.', dict(WORK, mentions=[
                        {'name': 'Archeus', 'kind': 'project', 'ref': None}])))])
    repo = r.register('layered-python')
    _reply, it = r.say('Fix the layered dashboard.')
    (m,) = r.all(entities.Mission)
    assert (m.project_id, it.project_id) == (repo.project_id, repo.project_id)
    reply, it = r.say('Fix the Archeus dashboard.')
    assert it.resolution == 'clarification_requested'
    assert 'project called "Archeus"' in reply['text']
    assert len(r.all(entities.Project)) == 1 and len(r.all(entities.Mission)) == 1


# ── I06 challenge ──

def _decision(r, title, confirmed=True):
    k = r.run(K.new_item, workspace_id=ids.GLOBAL_WORKSPACE, type='DECISION', title=title,
              origin='explicit', source_kind='user')['id']
    if confirmed:
        r.run(K.confirm, knowledge_item_id=k)
    return k


def test_i06_a_request_against_a_confirmed_decision_is_challenged_until_you_choose(make):
    conflict = dict(WORK, conflicts=[{'ref': 'k1', 'why': 'the decision forbids it'}])
    r = make([brain(('Query SQLite from the core.', conflict))])
    dec = _decision(r, 'The core never talks to the database directly')
    reply, it = r.say('Query SQLite from the core.')
    assert it.resolution == 'clarification_requested' and not r.all(entities.Mission)
    (card,) = reply['cards']
    assert (card['type'], card['against'], card['choices']) == ('challenge', [dec],
                                                                 ['proceed', 'drop'])
    assert 'the confirmed decision' in reply['text']
    sent = len(r.callers[0].sent)
    out = r.run(r.conv.choose, intent_id=it.id, choice='proceed')
    (m,) = r.all(entities.Mission)
    assert out['resolution'] == 'mission_created' and len(r.callers[0].sent) == sent
    assert any(dec in c['text'] and c['origin'] == 'explicit' for c in m.constraints)
    with pytest.raises(ValueError):
        r.run(r.conv.choose, intent_id=it.id, choice='proceed')     # chosen once


def test_i06b_dropping_a_challenge_writes_nothing_and_a_candidate_is_labelled(make):
    conflict = dict(WORK, conflicts=[{'ref': 'k1', 'why': 'notes say otherwise'}])
    r = make([brain(('Query SQLite from the core.', conflict))])
    dec = r.run(K.new_item, workspace_id=ids.GLOBAL_WORKSPACE, type='DECISION',
                title='The core never talks to the database', source_kind='import')['id']
    reply, it = r.say('Query SQLite from the core.')
    assert 'not confirmed' in reply['text']
    assert r.all(entities.KnowledgeItem)[0].state == 'CANDIDATE'        # still a candidate
    pkg = r.read(queries.get_context_package, it.context_package_id)
    (item,) = [i for i in pkg['items'] if i['ref']['id'] == dec]
    assert item['signals']['auth'] == 0.3 and 'not confirmed' in item['reason']
    out = r.run(r.conv.choose, intent_id=it.id, choice='drop')
    assert out['resolution'] == 'declined' and not r.all(entities.Mission)


def test_i06c_only_deciding_items_can_be_challenged_against(make):
    ent = dict(WORK, conflicts=[{'ref': 'k1', 'why': 'x'}])
    r = make([brain(('Do the thing.', ent))])
    k = r.run(K.new_item, workspace_id=ids.GLOBAL_WORKSPACE, type='FACT', title='a fact',
              origin='explicit', source_kind='user')['id']
    r.run(K.confirm, knowledge_item_id=k)
    _reply, it = r.say('Do the thing.')
    assert it.resolution == 'declined' and not r.all(entities.Mission)


# ── I07 ideas ──

def test_i07_an_idea_is_captured_not_committed_and_promotion_follows_the_idea_machine(make):
    r = make([brain(('Idea: a digest email.', {'kind': 'idea', 'title': 'Digest',
                                                'objective': 'a digest email'}),
                    ('Make the digest idea a mission.', {'kind': 'new_work', 'target': 'i1'}))])
    reply, it = r.say('Idea: a digest email.')
    (idea,) = r.all(entities.Idea)
    assert (idea.state, it.resolution) == ('CAPTURED', 'answered') and not r.all(entities.Mission)
    r.say('Make the digest idea a mission.')
    (m,) = r.all(entities.Mission)
    (idea,) = r.all(entities.Idea)
    assert (m.origin, m.origin_ref, idea.state, idea.promoted_mission_id) == (
        'idea', idea.id, 'IMPLEMENTING', m.id)
    moves = [e['payload']['trigger'] for e in r.events('idea.state_changed')]
    assert moves == ['clarify', 'plan', 'promote']
    r.run(MS.cancel, mission_id=m.id)
    r.settle()
    assert r.all(entities.Idea)[0].state == 'PLANNED'        # mission_cancelled


# ── I08 feedback, preferences, candidate lineage ──

def test_i08_feedback_is_history_and_a_preference_is_only_ever_a_candidate(make):
    r = make([brain(('Add a --version flag to the CLI', WORK),
                    ('That mission was badly named.', {'kind': 'feedback', 'target': 'm1',
                                                       'feedback': {'signal': 'negative'}}),
                    ('Use tabs.', {'kind': 'preference', 'feedback': {
                        'signal': 'positive', 'title': 'Indent with tabs'}}),
                    ('No, I meant four spaces.', {'kind': 'preference', 'feedback': {
                        'signal': 'correction', 'title': 'Indent with four spaces',
                        'supersedes': 'u1'}}))])
    r.say('Use tabs.')         # first: `u1` is then the earliest turn, this one
    (tabs,) = r.all(entities.KnowledgeItem)
    assert (tabs.state, tabs.origin, tabs.type) == ('CANDIDATE', 'explicit', 'PREFERENCE')
    reply, it = r.say('No, I meant four spaces.')
    spaces = [k for k in r.all(entities.KnowledgeItem) if k.id != tabs.id][0]
    assert (spaces.state, spaces.supersedes_id) == ('CANDIDATE', tabs.id)
    assert r.all(entities.KnowledgeItem, type='PREFERENCE')[0].state == 'CANDIDATE'
    assert 'would replace' in reply['text']
    # confirming the newer rejects the older candidate; neither is SUPERSEDED
    out = r.run(K.confirm, knowledge_item_id=spaces.id)
    assert (out['superseded'], out['replaced']) == (None, tabs.id)
    old = [k for k in r.all(entities.KnowledgeItem) if k.id == tabs.id][0]
    assert (old.state, old.superseded_by_id) == ('RETRACTED', spaces.id)
    assert r.read(queries.get_knowledge, spaces.id)['chain'] == [tabs.id, spaces.id]
    moved = [e for e in r.events('knowledge_item.state_changed')
             if e['subject']['id'] == tabs.id]
    assert moved[-1]['payload']['reason'].startswith(K.REPLACED)
    r.say('Add a --version flag to the CLI')
    _reply, it = r.say('That mission was badly named.')
    (fb,) = [f for f in r.all(entities.Feedback) if f.subject.kind == 'mission']
    assert (fb.signal, fb.promoted_knowledge_id) == ('negative', None)
    assert len(r.all(entities.Mission)) == 1                   # feedback is not new work


def test_i08b_remember_is_the_explicit_path_and_confirms_itself(make):
    fake = brain()
    r = make([fake])
    reply, it = r.say('remember that releases go out on Fridays')
    (k,) = r.all(entities.KnowledgeItem)
    assert (k.state, k.origin, k.title, it.via) == (
        'CONFIRMED', 'explicit', 'releases go out on Fridays', 'grammar')
    assert fake.sent == []                                       # no model call


# ── I09–I12 context, structured output, harnesses, the terms gate ──

def test_i09_the_brain_is_shown_the_p5_package_and_only_its_handles(make):
    r = make([brain(('Add a --version flag to the CLI', WORK))])
    r.register('layered-python')
    r.run(commands.create_mission, title='Open work', objective='o')
    _reply, it = r.say('Add a --version flag to the CLI')
    spec, prompt = r.callers[0].sent[-1]
    assert spec.purpose == 'brain' and '[p1] project' in prompt and '[m1] mission' in prompt
    pkg = r.read(queries.get_context_package, it.context_package_id)
    assert {i['ref']['kind'] for i in pkg['items']} >= {'message', 'project', 'mission'}


@pytest.mark.parametrize('structured', ['native', 'prompted'])
def test_i10_native_and_prompted_structured_output_both_apply(make, structured):
    r = make([brain(('Add a --version flag to the CLI', WORK), structured=structured)])
    _reply, it = r.say('Add a --version flag to the CLI')
    assert it.resolution == 'mission_created'


def test_i11_any_headless_harness_reads_intent_and_none_means_declined(make):
    r = make([FakeCaller('cc', headless=False), brain(('Add a --version flag to the CLI', WORK),
                                                      id_='other')])
    _reply, it = r.say('Add a --version flag to the CLI')
    rd = r.read(queries.get_route_decision, it.route_decision_id)
    assert rd['selected'] == 'other' and it.resolution == 'mission_created'
    r2 = make([FakeCaller('only', headless=False)])
    _reply, it = r2.say('Add another flag')
    assert (it.resolution, it.reason.split(':')[0]) == ('declined', 'unavailable')


def test_i12_a_gated_harness_is_never_called_and_nothing_is_created(make):
    gated = Real('pi', replies={'brain': [{'parsed': WORK}]})
    r = make([gated])
    reply, it = r.say('Add a --version flag to the CLI')
    assert gated.sent == [] and not r.all(entities.Mission)
    assert (it.resolution, it.reason.split(':')[0]) == ('declined', 'gated')
    assert 'provider terms' in reply['text']


# ── I13–I14 invalid output ──

def test_i13_an_unknown_handle_is_retried_once_then_writes_nothing(make):
    bad = dict(WORK, project='p9')
    r = make([FakeCaller('fake', replies={'brain': [{'parsed': bad}, {'parsed': WORK}]})])
    _reply, it = r.say('first')
    assert it.resolution == 'mission_created'                  # invalid, then valid
    r2 = make([FakeCaller('fake', replies={'brain': [{'parsed': bad}]})])
    _reply, it = r2.say('second')
    rd = r2.read(queries.get_route_decision, it.route_decision_id)
    assert (rd['outcome']['state'], it.resolution) == ('invalid', 'declined')
    assert len(r2.all(entities.Mission)) == 1                  # only r's (same database)


def test_i14_malformed_or_misshapen_output_cannot_mutate_a_mission(make):
    r = make([FakeCaller('fake', replies={'brain': [{'text': 'not json at all'}]})])
    r.run(commands.create_mission, title='Keep', objective='o')
    before = r.all(entities.Mission)
    _reply, it = r.say('Also print the git hash.')
    assert it.resolution == 'declined' and r.all(entities.Mission) == before
    r2 = make([FakeCaller('fake', replies={'brain': [{'parsed': {'kind': 'delete_everything'}}]})])
    _reply, it = r2.say('whatever')
    assert it.resolution == 'declined' and r2.all(entities.Mission) == before


# ── I15 idempotency ──

def test_i15_a_retried_or_redelivered_message_never_makes_a_second_mission(make):
    r = make([brain(('Add a --version flag to the CLI', WORK))])
    a = r.run(post_message, key='k1', text='Add a --version flag to the CLI')
    b = r.run(post_message, key='k1', text='Add a --version flag to the CLI')
    assert a['message_id'] == b['message_id']
    r.settle()
    r.db.writer.execute(lambda tx: tx.execute(                # redeliver every event
        'DELETE FROM consumer_effects WHERE consumer = ?', (CONSUMER,)) and None)
    r.db.writer.execute(lambda tx: tx.execute(
        'UPDATE consumer_cursors SET last_seq = 0 WHERE name = ?', (CONSUMER,)) and None)
    r.settle()
    assert len(r.all(entities.Mission)) == 1 and len(r.all(entities.Intent)) == 1
    with pytest.raises(ValueError, match='already read'):
        r.run(r.conv.decline, message_id=a['message_id'], route_decision_id=None,
              state='failed')


# ── I16–I18 lifecycle, no execution, no plan, the grammar ──

def test_i16_the_mission_moves_only_through_its_lifecycle(make):
    r = make([brain(('Add a --version flag to the CLI', WORK))])
    reply, it = r.say('Add a --version flag to the CLI')
    (m,) = r.all(entities.Mission)
    r.run(MS.fire, mission_id=m.id, trigger='start', reason='t')
    out = r.run(MS.understand, mission_id=m.id)
    (e,) = [x for x in r.events('mission.state_changed') if x['payload']['trigger'] == 'understood']
    assert out['state'] == 'CONTEXT_GATHERING' and it.id in e['payload']['reason']
    reply, it = r.say('pause Add a --version flag')           # CONTEXT_GATHERING has no pause
    assert it.via == 'grammar' and it.resolution == 'declined'
    assert r.all(entities.Mission)[0].state == 'CONTEXT_GATHERING'


def test_i17_reading_intent_creates_no_execution_task_plan_or_other_route(make):
    r = make([brain(('Add a --version flag to the CLI', WORK))])
    r.say('Add a --version flag to the CLI')
    for cls in (entities.Execution, entities.Task, entities.Plan):
        assert r.all(cls) == []
    assert {d.purpose for d in r.all(entities.RouteDecision)} == {'brain'}


def test_i18_control_verbs_never_call_the_model(make):
    fake = brain()
    r = make([fake])
    m = r.run(commands.create_mission, title='Ship it', objective='o')
    _reply, it = r.say('cancel Ship it')
    assert (it.via, it.kind, it.resolution) == ('grammar', 'control_verb', 'mission_updated')
    assert r.all(entities.Mission)[0].state == 'CANCELLED'
    reply, it = r.say('status')
    assert it.resolution == 'answered' and reply['cards'][0]['type'] == 'status'
    reply, it = r.say('why %s' % m['id'])
    assert 'nothing to explain' in reply['text']
    _reply, it = r.say('approve')
    assert it.resolution == 'declined'
    assert fake.sent == []


# ── I19–I20 undated notes, a reading gone stale ──

def test_i19_undated_notes_are_imported_undated_and_the_date_is_asked(make, tmp_path):
    notes = tmp_path / 'review.md'
    notes.write_text('# Review\nnothing dated\n', encoding='utf-8')
    r = make([brain()])
    with pytest.raises(ValueError, match='no date'):
        ingest.import_file(r.db, r.user, str(notes))            # not opted in
    out = ingest.import_file(r.db, r.user, str(notes), allow_undated=True)
    assert out['meeting']['held_at'] is None
    (ask,) = [m for m in r.read(queries.messages, 'primary') if m['author'] == 'archeus']
    assert ask['cards'][0]['asks'] == 'held_at'
    reply, it = r.say('It was 2026-09-20.', in_reply_to=ask['id'])
    assert r.all(entities.Meeting)[0].held_at == '2026-09-20' and it.via == 'grammar'
    assert r.callers[0].sent == [c for c in r.callers[0].sent if c[0].purpose != 'brain']


def test_i20_a_reading_whose_mission_ended_meanwhile_asks_instead(make):
    r = make([brain()])
    m = r.run(commands.create_mission, title='Old', objective='o')
    r.run(MS.cancel, mission_id=m['id'])
    posted = r.run(post_message, text='more for Old')
    rd = r.run(lambda tx, actor: __import__('archeus.core.application.calls',
                                            fromlist=['x']).decide_route(
        tx, actor=actor, purpose='brain', source={'kind': 'message', 'id': posted['message_id']},
        workspace_id=ids.GLOBAL_WORKSPACE, project_id=None, selected='fake', account_ref=None,
        model=None, candidates=[], requirements={}, input_snapshot={}, explanation='t'))
    proposal = {'kind': 'continue_work', 'target': {'kind': 'mission', 'id': m['id']},
                'project': None, 'mentions': [], 'conflicts': [], 'ambiguities': [],
                'requirements': [{'text': 'x', 'origin': 'explicit'}], 'constraints': [],
                'answer': [], 'feedback': None}
    out = r.run(r.conv.apply_intent, message_id=posted['message_id'], proposal=proposal,
                called={'route_decision_id': rd['route_decision_id'], 'attempts': 1,
                        'account_ref': None, 'usage': None, 'context_package_id': None})
    assert out['resolution'] == 'clarification_requested'
    assert r.all(entities.Mission)[0].requirements == ()


# ── I21 (U02) grammar resolution: an id or one exact title, else the brain's ──

def test_i21_a_grammar_reference_resolves_to_exactly_one_object_or_to_nothing(db):
    from archeus.core.application import commands
    from archeus.core.domain.values import Ref
    actor = Ref('system', db.writer.execute(commands.register_principal,
                                            {'kind': 'system', 'scopes': ['system']})['id'])
    a = db.writer.execute(commands.create_mission, {'actor': actor, 'title': 'Ship it',
                                                    'objective': 'o'})['id']
    for t in ('Twin', 'Twin'):
        db.writer.execute(commands.create_mission, {'actor': actor, 'title': t,
                                                    'objective': 'o'})
    with db.read() as c:
        assert grammar.resolve(c, 'pause ship  IT') == grammar.Control(
            'pause', {'kind': 'mission', 'id': a}, 'ship  IT'.replace('  ', ' '))
        assert grammar.resolve(c, 'pause %s' % a).target['id'] == a
        assert grammar.resolve(c, 'pause Twin') is None            # two: the brain's
        assert grammar.resolve(c, 'pause nothing like it') is None
        assert grammar.resolve(c, 'stop everything please') is None
        assert grammar.resolve(c, 'status') == grammar.Control('status', None, '')
        assert grammar.resolve(c, 'status of the world') is None
        assert grammar.resolve(c, 'why not') is None
        assert grammar.resolve(c, 'approve').verb == 'approve'


def test_i22_a_continuation_updates_exactly_the_mission_it_names(make):
    r = make([brain()])
    old = r.run(commands.create_mission, title='Older', objective='o')['id']
    new = r.run(commands.create_mission, title='Newer', objective='o')['id']
    posted = r.run(post_message, text='more for the older one')
    rd = r.run(lambda tx, actor: __import__('archeus.core.application.calls',
                                            fromlist=['x']).decide_route(
        tx, actor=actor, purpose='brain', source={'kind': 'message', 'id': posted['message_id']},
        workspace_id=ids.GLOBAL_WORKSPACE, project_id=None, selected='fake', account_ref=None,
        model=None, candidates=[], requirements={}, input_snapshot={}, explanation='t'))
    proposal = {'kind': 'continue_work', 'target': {'kind': 'mission', 'id': old},
                'project': None, 'mentions': [], 'conflicts': [], 'ambiguities': [],
                'requirements': [{'text': 'x', 'origin': 'explicit'}], 'constraints': [],
                'answer': [], 'feedback': None}
    r.run(r.conv.apply_intent, message_id=posted['message_id'], proposal=proposal,
          called={'route_decision_id': rd['route_decision_id'], 'attempts': 1,
                  'account_ref': None, 'usage': None, 'context_package_id': None})
    got = {m.id: [c['text'] for c in m.requirements] for m in r.all(entities.Mission)}
    assert got == {old: ['x'], new: []}
