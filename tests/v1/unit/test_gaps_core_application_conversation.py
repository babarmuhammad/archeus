"""T-302: the highest-risk uncovered branches of
`archeus/core/application/conversation.py`, as unit tests (no database, no model,
no process). Fail-closed and denial paths first (a directive from a foreign
principal, a bare `approve` word, the challenge-choice guards, the terminal
mission, the widening that may only be proposed, the one-read message, the
user-only turn, the post validation, the decline fallback, the feedback
promotion gates), then the boundary values and the error paths. Same style and
fakes as test_chat_start_units.py and test_intent_units.py: an in-memory `tx`,
monkeypatched seams (`C.end_call`, `K.record_feedback`), real entities so every
entity validation still runs. Platform-neutral: no files, no OS calls, no
network, no sleeps.
"""

import dataclasses

import pytest

from archeus.core.application import conversation as conv_mod
from archeus.core.application import lifecycle
from archeus.core.application.conversation import (Conversations, decide_by_message,
                                                   directive, post_message)
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref


# ── the in-memory tx (the writer Tx's interface, no database) ──

class Row:
    def __init__(self, entity, version=1):
        self.entity, self.version = entity, version


class Tx:
    """get/where/insert/update/append of infra.db.writer.Tx over dicts; update
    keeps the real rules that matter here (no id, no state, version bumps) and
    `dataclasses.replace` keeps every entity validation live."""

    def __init__(self):
        self.store = {}
        self.events = []
        self.now = '2026-10-30T12:00:00+00:00'
        self.conn = None
        self._seq = 0

    def seed(self, *ents):
        for e in ents:
            self.store.setdefault(type(e), {})[e.id] = Row(e)
        return ents[0] if len(ents) == 1 else ents

    def insert(self, entity, *, actor):
        self.store.setdefault(type(entity), {})[entity.id] = Row(entity)
        return Row(entity)

    def get(self, cls, entity_id):
        return self.store.get(cls, {}).get(entity_id)

    def where(self, cls, **eq):
        return [r for r in self.store.get(cls, {}).values()
                if all(getattr(r.entity, k, object()) == v for k, v in eq.items())]

    def update(self, cls, entity_id, fields, *, actor, expected_version=None, bump=True):
        row = self.get(cls, entity_id)
        if row is None:
            raise lifecycle.NotFound(entity_id)
        if set(fields) & ({'id'} | cls.state_fields()):
            raise ValueError('update may not set the id or the state; an edge does')
        stored = Row(dataclasses.replace(row.entity, **fields),
                     row.version + (1 if bump else 0))
        self.store[cls][entity_id] = stored
        return stored

    def append(self, event):
        self._seq += 1
        stored = dataclasses.replace(event, seq=self._seq)
        self.events.append(stored)
        return stored


@pytest.fixture
def tx():
    return Tx()


class FakeMissions:
    """The P3 `Missions` seam: records what conversation.py asked for, in order."""

    def __init__(self):
        self.calls = []

    def _ask(self, verb, mission_id, reason):
        self.calls.append((verb, mission_id, reason))

    def pause(self, tx, *, actor, mission_id, reason):
        self._ask('pause', mission_id, reason)

    def resume(self, tx, *, actor, mission_id, reason):
        self._ask('resume', mission_id, reason)

    def cancel(self, tx, *, actor, mission_id, reason):
        self._ask('cancel', mission_id, reason)


def conversations():
    return Conversations(missions=FakeMissions(), harnesses=lambda: ())


def actor_of(tx, kind='user_device'):
    p = tx.seed(entities.Principal(id=ids.new_id('principal'), kind=kind))
    return Ref(kind, p.id)


def user_turn(tx, text='do the thing', actor=None):
    return post_message(tx, actor=actor or actor_of(tx), text=text)


def msg_in(tx, conv_id, author='user', text='hi', **kw):
    return tx.seed(entities.Message(id=ids.new_id('message'), conversation_id=conv_id,
                                    author=author, text=text, **kw))


def mission(tx, state='CREATED', **kw):
    kw.setdefault('title', 'Ship it')
    kw.setdefault('objective', 'Ship it once')
    return tx.seed(entities.Mission(id=ids.new_id('mission'),
                                    workspace_id=ids.GLOBAL_WORKSPACE, state=state, **kw))


def account(tx, label='claude home'):
    return tx.seed(entities.Account(id=ids.new_id('account'), harness_id='claude_code',
                                    label=label, auth_kind='api_key'))


def approval(tx, mission_id, requested_by):
    return tx.seed(entities.Approval(id=ids.new_id('approval'), subject=Ref('action', 'act_x'),
                                     action_hash='a' * 64, requested_by=requested_by,
                                     kind='action', mission_id=mission_id))


def intent(tx, msg, **kw):
    kw.setdefault('kind', 'control_verb')
    kw.setdefault('via', 'grammar')
    return tx.seed(entities.Intent(id=ids.new_id('intent'), message_id=msg.id,
                                   utterance=msg.text, **kw))


def proposal(**kw):
    p = {'kind': 'new_work', 'title': 'Add a flag', 'objective': 'It prints',
         'desired_outcome': '', 'target': None, 'project': None, 'mentions': [],
         'requirements': [], 'constraints': [], 'ambiguities': [], 'conflicts': [],
         'feedback': None, 'answer': None, 'confidence': None}
    p.update(kw)
    return p


def called_dict():
    return {'route_decision_id': ids.new_id('route_decision'),
            'context_package_id': ids.new_id('context_package'),
            'attempts': 1, 'account_ref': None, 'usage': None}


@pytest.fixture
def ends(monkeypatch):
    """The brain-call end: recorded, not executed (no RouteDecision rows here)."""
    seen = []
    monkeypatch.setattr(conv_mod.C, 'end_call', lambda tx, **kw: seen.append(kw))
    return seen


def reply_message(tx, out):
    return tx.get(entities.Message, out['reply_id']).entity


# ── 1. directive: only the poster's own user device may change what work uses ──

@pytest.mark.parametrize('kind', ['system', 'brain', 'execution'])
def test_directive_from_a_foreign_principal_changes_nothing(tx, kind):
    stranger = actor_of(tx, kind)
    user = actor_of(tx)
    m = mission(tx)
    acc = account(tx)
    posted = user_turn(tx, actor=user)
    conv_id = posted['conversation_id']
    # the message was posted by the stranger: the guard reads the poster, not the caller
    msg = msg_in(tx, conv_id, text='never use claude home', principal_id=stranger.id)
    it = intent(tx, msg)
    events_before = len(tx.events)
    text, resolution, cards, links = directive(
        tx, user, msg, it, m.id, prefer=(), forbid=({'kind': 'account', 'id': acc.id},))
    assert resolution == 'declined'
    assert 'Only a message from your own device' in text
    assert cards == [] and links == []
    row = tx.get(entities.Mission, m.id)
    assert row.version == 1 and row.entity.resource_preferences is None
    assert len(tx.events) == events_before       # a refusal writes nothing at all


def test_directive_missing_principal_row_is_refused_too(tx):
    user = actor_of(tx)                                          # row seeded...
    posted = user_turn(tx, actor=user)
    msg = msg_in(tx, posted['conversation_id'], text='never use it',
                 principal_id=ids.new_id('principal'))           # ...this one is not
    it = intent(tx, msg)
    m = mission(tx)
    text, resolution, cards, links = directive(
        tx, user, msg, it, m.id, prefer=(), forbid=({'kind': 'account', 'id':
                                                     account(tx).id},))
    assert (resolution, cards, links) == ('declined', [], [])
    assert tx.get(entities.Mission, m.id).version == 1


def test_directive_from_a_user_device_applies_the_narrowing(tx):
    user = actor_of(tx)
    m = mission(tx)
    acc = account(tx)
    posted = user_turn(tx, actor=user)
    msg = msg_in(tx, posted['conversation_id'], text='never use claude home',
                 principal_id=user.id)
    it = intent(tx, msg)
    text, resolution, cards, links = directive(
        tx, user, msg, it, m.id, prefer=(), forbid=({'kind': 'account', 'id': acc.id},))
    assert resolution == 'mission_updated'
    rp = tx.get(entities.Mission, m.id).entity.resource_preferences
    assert rp['forbidden_accounts'] == [acc.id]
    assert rp['directives'] == [{'key': 'forbidden_accounts', 'id': acc.id,
                                 'message_id': msg.id, 'intent_id': it.id}]
    assert [c['type'] for c in cards] == ['mission']
    assert links == [{'ref': {'kind': 'mission', 'id': m.id}}]
    assert [(e.type, e.subject.id) for e in tx.events if e.type == 'mission.updated'] == [
        ('mission.updated', m.id)]


# ── 2. directive on a mission that has ended: refused, nothing written ──

@pytest.mark.parametrize('state', ['COMPLETED', 'CANCELLED'])
def test_directive_on_an_ended_mission_is_declined(tx, state):
    user = actor_of(tx)
    m = mission(tx, state=state)
    acc = account(tx)
    posted = user_turn(tx, actor=user)
    msg = msg_in(tx, posted['conversation_id'], text='never use it', principal_id=user.id)
    it = intent(tx, msg)
    text, resolution, cards, links = directive(
        tx, user, msg, it, m.id, prefer=(), forbid=({'kind': 'account', 'id': acc.id},))
    assert resolution == 'declined'
    assert 'nothing was changed' in text and state in text
    assert cards == [] and links == []
    assert tx.get(entities.Mission, m.id).version == 1


# ── 3. directive widening is proposed on a card, never applied in place ──

def test_directive_widening_only_offers_a_change_card(tx):
    user = actor_of(tx)
    a1, a2 = account(tx, label='forbidden one'), account(tx, label='last resort')
    tx.seed(entities.ResourcePolicy(id=ids.new_id('resource_policy'), account_id=a2.id,
                                    consumption='explicit_only'))
    m = mission(tx, resource_preferences={'forbidden_accounts': [a1.id]})
    posted = user_turn(tx, actor=user)
    msg = msg_in(tx, posted['conversation_id'], text='use both please', principal_id=user.id)
    it = intent(tx, msg)
    before = tx.get(entities.Mission, m.id)
    text, resolution, cards, links = directive(
        tx, user, msg, it, m.id,
        prefer=({'kind': 'account', 'id': a1.id}, {'kind': 'account', 'id': a2.id}), forbid=())
    assert resolution == 'answered'                              # nothing applied
    assert 'Confirm it on the card' in text
    after = tx.get(entities.Mission, m.id)
    assert after.version == 1
    assert after.entity.resource_preferences == before.entity.resource_preferences
    change = [c for c in cards if c['type'] == 'change']
    assert len(change) == 2
    for c in change:
        assert c['command']['name'] == 'setMissionResources' and c['scope'] == 'mission'
    says = ' '.join(c['says'] for c in change)
    assert 'forbidden for this mission' in says                   # the lift is explained
    assert 'when you name it' in says                             # explicit_only is explained
    assert [e.type for e in tx.events] == ['message.created']     # the user turn only


# ── 4. a bare approve/reject word decides nothing; only the card decides ──

@pytest.mark.parametrize('n_pending, expect_text', [
    (0, 'Nothing is waiting for your approval.'),
    (1, "To approve, use its card: it decides exactly the action it shows."),
    (11, "To approve, use the approval's card: it decides exactly the action it shows."),
])
def test_bare_approve_never_decides_an_approval(tx, n_pending, expect_text):
    m = mission(tx)
    asker = actor_of(tx, kind='execution')
    for _ in range(n_pending):
        approval(tx, m.id, asker.id)
    posted = user_turn(tx, text='approve')
    out = conversations().apply_control(tx, actor=actor_of(tx),
                                        message_id=posted['message_id'], verb='approve')
    assert out['resolution'] == 'declined'
    reply = reply_message(tx, out)
    assert reply.text == expect_text
    assert len(reply.cards) == min(n_pending, 10)                 # at most ten, named
    assert {c['type'] for c in reply.cards} <= {'approval'}
    got = tx.where(entities.Approval)
    assert len(got) == n_pending and all(r.entity.state == 'PENDING' for r in got)


# ── 5. the challenge choice guards: only proceed/drop on a waiting intent ──

def _waiting_challenge(tx, conflicts=True):
    posted = user_turn(tx, text='restyle the report')
    conflict = ({'ref': {'kind': 'knowledge_item',
                         'id': ids.new_id('knowledge_item')},
                 'why': 'it goes against your confirmed decision'},)
    return intent(tx, tx.get(entities.Message, posted['message_id']).entity,
                  kind='new_work', via='brain',
                  resolution='clarification_requested' if conflicts else 'answered',
                  conflicts=conflict if conflicts else (),
                  proposal=proposal(kind='new_work', title='Restyle',
                                    objective='Look better',
                                    requirements=[{'text': 'a restyle',
                                                   'origin': 'explicit'}],
                                    constraints=[]))


def test_choose_refuses_any_other_word_and_any_intent_not_waiting(tx):
    convs = conversations()
    it = _waiting_challenge(tx)
    with pytest.raises(ValueError):
        convs.choose(tx, actor=actor_of(tx), intent_id=it.id, choice='ship it')
    settled = _waiting_challenge(tx, conflicts=False)
    with pytest.raises(ValueError):
        convs.choose(tx, actor=actor_of(tx), intent_id=settled.id, choice='proceed')
    done = _waiting_challenge(tx)                                 # a chosen intent...
    convs.choose(tx, actor=actor_of(tx), intent_id=done.id, choice='drop')
    with pytest.raises(ValueError):                               # ...cannot be chosen again
        convs.choose(tx, actor=actor_of(tx), intent_id=done.id, choice='proceed')
    assert not tx.where(entities.Mission)                         # none of it created work


def test_choose_drop_declines_and_creates_nothing(tx):
    it = _waiting_challenge(tx)
    out = conversations().choose(tx, actor=actor_of(tx), intent_id=it.id, choice='drop')
    assert out['resolution'] == 'declined'
    assert 'Nothing was created' in reply_message(tx, out).text
    assert not tx.where(entities.Mission)


def test_choose_proceeds_only_with_the_conflict_noted_as_a_constraint(tx):
    it = _waiting_challenge(tx)
    out = conversations().choose(tx, actor=actor_of(tx), intent_id=it.id, choice='proceed')
    assert out['resolution'] == 'mission_created'
    (m,) = [r.entity for r in tx.where(entities.Mission)]
    assert [c['text'] for c in m.requirements] == ['a restyle']
    (con,) = m.constraints
    assert con['origin'] == 'explicit' and con['source_ref'] == it.message_id
    assert 'goes against' in con['text']


# ── 6. only a user turn is read for intent ──

def test_an_archeus_reply_can_never_be_read_as_a_user_turn(tx):
    posted = user_turn(tx)
    archeus_msg = msg_in(tx, posted['conversation_id'], author='archeus', text='pause it')
    convs = conversations()
    with pytest.raises(ValueError):
        convs.apply_control(tx, actor=actor_of(tx), message_id=archeus_msg.id, verb='estop')
    with pytest.raises(ValueError):
        convs.decline(tx, actor=actor_of(tx), message_id=archeus_msg.id,
                      route_decision_id=ids.new_id('route_decision'), state='gated')
    # the guard fires before anything is written
    assert not tx.where(entities.Intent)


# ── 7. one message is read once: a replayed read raises ──

def test_a_message_already_read_cannot_be_read_again(tx):
    convs = conversations()
    posted = user_turn(tx, text='stop everything')
    mid = posted['message_id']
    convs.apply_control(tx, actor=actor_of(tx), message_id=mid, verb='estop')
    with pytest.raises(ValueError):
        convs.apply_control(tx, actor=actor_of(tx), message_id=mid, verb='estop')
    with pytest.raises(ValueError):
        convs.decline(tx, actor=actor_of(tx), message_id=mid,
                      route_decision_id=ids.new_id('route_decision'), state='gated')
    assert len(tx.where(entities.Intent)) == 1                    # the replay wrote nothing


# ── 8. post_message: an empty turn, an unknown conversation, a cross-thread reply ──

@pytest.mark.parametrize('text', ['', '   ', '\n\t', None, 7, ['a']])
def test_a_turn_must_have_text(tx, text):
    with pytest.raises(ValueError):
        post_message(tx, actor=actor_of(tx), text=text)
    assert not tx.where(entities.Message)


def test_posting_to_an_unknown_conversation_is_not_found(tx):
    with pytest.raises(lifecycle.NotFound):
        post_message(tx, actor=actor_of(tx), text='hello',
                     conversation_id=ids.new_id('conversation'))


def test_a_reply_must_belong_to_the_same_conversation(tx):
    a = user_turn(tx, text='first here')
    other = tx.seed(entities.Conversation(id=ids.new_id('conversation'), kind='primary'))
    with pytest.raises(ValueError):
        post_message(tx, actor=actor_of(tx), text='answering over there',
                     conversation_id=other.id, in_reply_to=a['message_id'])
    assert len(tx.where(entities.Message)) == 1                   # the refusal wrote nothing


# ── 9. decline: the user is always told why, even for a state not in the table ──

@pytest.mark.parametrize('state, detail, needle', [
    ('gated', '', 'no harness is permitted'),
    ('invalid', '', 'did not pass validation twice'),
    ('harness_down', 'socket closed', 'harness_down (socket closed)'),
])
def test_decline_says_why_and_writes_only_the_reply(tx, state, detail, needle):
    posted = user_turn(tx, text='what now?')
    out = conversations().decline(tx, actor=actor_of(tx), message_id=posted['message_id'],
                                 route_decision_id=ids.new_id('route_decision'),
                                 state=state, detail=detail)
    assert out['resolution'] == 'declined'
    assert needle in reply_message(tx, out).text
    (it,) = [r.entity for r in tx.where(entities.Intent)]
    assert (it.kind, it.resolution) == ('question', 'declined')
    assert len(tx.where(entities.Message)) == 2                   # turn + reply, nothing else


# ── 10. feedback: a candidate needs a title and a live item to replace ──

def patch_feedback(monkeypatch, promoted=None):
    seen = []

    def fake(tx, *, actor, subject, signal, text, promote):
        seen.append({'subject': subject, 'signal': signal, 'text': text, 'promote': promote})
        return {'feedback_id': ids.new_id('feedback'), 'promoted': promoted}
    monkeypatch.setattr(conv_mod.K, 'record_feedback', fake)
    return seen


@pytest.mark.parametrize('kind, target_kind', [('feedback', 'project'), ('feedback', 'idea')])
def test_a_model_named_subject_outside_the_allowed_set_falls_back_to_the_message(
        tx, ends, monkeypatch, kind, target_kind):
    kinds = {'project': 'project', 'idea': 'idea'}
    target = {'kind': kinds[target_kind], 'id': ids.new_id(kinds[target_kind])}
    seen = patch_feedback(monkeypatch)
    posted = user_turn(tx, text='I dislike this, prefer %s work' % target_kind)
    convs = conversations()
    out = convs.apply_intent(tx, actor=actor_of(tx), message_id=posted['message_id'],
                             called=called_dict(),
                             proposal=proposal(kind=kind, target=target,
                                               feedback={'signal': 'positive',
                                                         'title': '   ',           # blank!
                                                         'promote': 'PREFERENCE',
                                                         'supersedes': None}))
    assert out['resolution'] == 'answered'
    assert seen[0]['subject'] == {'kind': 'message', 'id': posted['message_id']}
    # a blank title never promotes: the model's word alone cannot mint a candidate
    assert seen[0]['promote'] is None
    reply = reply_message(tx, out)
    assert reply.text.startswith('Noted as feedback (')
    assert reply.cards == ()


def test_supersedes_is_recorded_only_for_a_live_item(tx, ends, monkeypatch):
    live = tx.seed(entities.KnowledgeItem(id=ids.new_id('knowledge_item'), type='DECISION',
                                          title='Always tabs', workspace_id=ids.GLOBAL_WORKSPACE,
                                          state='CONFIRMED'))
    gone = tx.seed(entities.KnowledgeItem(id=ids.new_id('knowledge_item'), type='DECISION',
                                          title='Dead rule', workspace_id=ids.GLOBAL_WORKSPACE,
                                          state='SUPERSEDED'))
    promoted = {'type': 'PREFERENCE', 'title': 'Use tabs', 'id': ids.new_id('knowledge_item')}
    seen = patch_feedback(monkeypatch, promoted=promoted)
    convs = conversations()
    user = actor_of(tx)

    def read(about):
        posted = user_turn(tx, text='actually use tabs', actor=user)
        out = convs.apply_intent(
            tx, actor=user, message_id=posted['message_id'], called=called_dict(),
            proposal=proposal(kind='preference',
                              feedback={'signal': 'positive', 'title': 'Use tabs',
                                        'supersedes': about}))
        return out
    read(gone.id)
    assert 'supersedes_id' not in seen[0]['promote']              # a dead item is not replaced
    out = read(live.id)
    assert seen[1]['promote']['supersedes_id'] == live.id
    words = reply_message(tx, out).text
    assert 'not confirmed yet' in words and 'it would replace "Always tabs"' in words
    assert [c['type'] for c in reply_message(tx, out).cards] == ['knowledge']


# ── 11. a stale target is asked about, never applied ──

def test_continuing_an_ended_mission_asks_instead_of_writing(tx, ends):
    m = mission(tx, state='COMPLETED', requirements=({'text': 'kept', 'origin': 'explicit'},))
    posted = user_turn(tx, text='also print the hash')
    convs = conversations()
    out = convs.apply_intent(tx, actor=actor_of(tx), message_id=posted['message_id'],
                             called=called_dict(),
                             proposal=proposal(kind='continue_work',
                                               target={'kind': 'mission', 'id': m.id},
                                               requirements=[{'text': 'the hash',
                                                              'origin': 'explicit'}]))
    assert out['resolution'] == 'clarification_requested'
    after = tx.get(entities.Mission, m.id)
    assert after.version == 1 and [c['text'] for c in after.entity.requirements] == ['kept']
    assert [e.type for e in tx.events].count('mission.updated') == 0   # nothing touched it
    qs = reply_message(tx, out).cards[0]['questions']
    assert 'has ended (COMPLETED)' in qs[0]


def test_promoting_an_already_implementing_idea_asks_instead_of_creating(tx, ends):
    idea = tx.seed(entities.Idea(id=ids.new_id('idea'), workspace_id=ids.GLOBAL_WORKSPACE,
                                 text='a digest', state='IMPLEMENTING'))
    posted = user_turn(tx, text='make the digest a mission')
    out = conversations().apply_intent(
        tx, actor=actor_of(tx), message_id=posted['message_id'], called=called_dict(),
        proposal=proposal(kind='new_work', target={'kind': 'idea', 'id': idea.id}))
    assert out['resolution'] == 'clarification_requested'
    assert not tx.where(entities.Mission)                         # no second mission
    assert 'cannot be made into a mission again' in reply_message(tx, out).cards[0][
        'questions'][0]


# ── 12. a decision by message: a policy denial is said, and nothing is approved ──

def test_a_denied_decision_by_message_says_so_and_leaves_the_approval_pending(tx):
    m = mission(tx)
    a = approval(tx, m.id, actor_of(tx, kind='system').id)
    asked = []

    def decide(tx, *, actor, approval_id, decision, action_hash, step_up, expected_version):
        asked.append({'approval_id': approval_id, 'decision': decision,
                      'action_hash': action_hash})
        return {'denied': True, 'changed': False}
    out = decide_by_message(
        tx, actor=actor_of(tx), decide=decide, text='approve', conversation_id='primary',
        approval_id=a.id, action_hash='a' * 64)
    assert asked == [{'approval_id': a.id, 'decision': 'approve', 'action_hash': 'a' * 64}]
    assert out['decided'] == {'denied': True, 'changed': False}
    assert out['resolution'] == 'answered'
    assert 'The policy denies it now, so nothing was approved for "Ship it".' == \
        reply_message(tx, out).text
    assert tx.get(entities.Approval, a.id).entity.state == 'PENDING'
    assert [c['type'] for c in reply_message(tx, out).cards] == ['approval']


def test_a_decision_by_message_with_other_words_writes_nothing(tx):
    m = mission(tx)
    a = approval(tx, m.id, actor_of(tx, kind='system').id)
    before = len(tx.where(entities.Message))
    with pytest.raises(ValueError):
        decide_by_message(
            tx, actor=actor_of(tx), decide=lambda tx, **kw: {'changed': True},
            text='sounds good to me', conversation_id='primary', approval_id=a.id,
            action_hash='a' * 64)
    assert len(tx.where(entities.Message)) == before


# ── 13. confirming a stop card: only that card, only stop, and it pauses then cancels ──

def test_confirm_stop_pauses_an_executing_mission_then_cancels_it(tx):
    convs = conversations()
    m = mission(tx, state='EXECUTING')
    posted = user_turn(tx, text='hello')
    card_msg = msg_in(tx, posted['conversation_id'], author='archeus', text='stop it?',
                      cards=[{'type': 'stop', 'ref': {'kind': 'mission', 'id': m.id}}])
    out = convs.confirm_by_message(tx, actor=actor_of(tx), text='stop it',
                                   conversation_id=posted['conversation_id'],
                                   message_id=card_msg.id)
    verbs = [(c[0], c[1]) for c in convs.missions.calls]
    assert verbs == [('pause', m.id), ('cancel', m.id)]           # in that order, both asked
    assert all('stop: confirmed in message' in c[2] for c in convs.missions.calls)
    assert out['resolution'] == 'mission_updated'
    assert 'EXECUTING -> CANCELLED' in reply_message(tx, out).text


@pytest.mark.parametrize('bad', [
    'pause it',                                                    # not the stop verb
    'stop it',                                                     # a user message, not Archeus
])
def test_confirm_stop_refuses_anything_but_an_archeus_stop_card(tx, bad):
    convs = conversations()
    m = mission(tx, state='EXECUTING')
    posted = user_turn(tx)
    cards = [{'type': 'stop', 'ref': {'kind': 'mission', 'id': m.id}}] if bad == 'stop it' \
        else [{'type': 'mission', 'ref': {'kind': 'mission', 'id': m.id}}]
    card_msg = msg_in(tx, posted['conversation_id'], author='user' if bad == 'stop it'
                      else 'archeus', text='confirm?', cards=cards)
    with pytest.raises(ValueError):
        convs.confirm_by_message(tx, actor=actor_of(tx), text=bad,
                                 conversation_id=posted['conversation_id'],
                                 message_id=card_msg.id)
    assert convs.missions.calls == []                              # nothing was asked of P3


def test_confirm_stop_names_an_existing_message(tx):
    convs = conversations()
    posted = user_turn(tx)
    with pytest.raises(ValueError):
        convs.confirm_by_message(tx, actor=actor_of(tx), text='stop it',
                                 conversation_id=posted['conversation_id'],
                                 message_id=ids.new_id('message'))
