"""T-401 hand-mutant pins for archeus/core/application/conversation.py.

Every test here pins a condition an existing test would still pass if it were
inverted, removed or loosened; the per-condition verdicts are in
/work/QWEN-DONE-T-401.md. Rows the phase never writes (an approval already
decided, an idea already implemented, a retracted knowledge item, an archeus
message carrying a card) are inserted through the same seams the P6/P7/P16
unit tests use: a real sqlite `Database` under the test's own `ARCHEUS_HOME`
(the `test_own_call_no_tools` pattern), commands through `db.writer.execute`,
the `test_ui_seams._tx` one-command insert. What the user "means" is scripted:
`proposal` dicts straight into `apply_intent`, a stub `decide` into
`decide_by_message`. No model, no process, no network, no sleep, nothing
OS-specific; every id comes from `ids.new_id`, never a path.
"""

import hashlib

import pytest

from archeus.core import ports
from archeus.core.application import commands, conversation as X
from archeus.core.application import queries, resources
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows
from archeus.infra.db.writer import NotFound

WS = ids.GLOBAL_WORKSPACE
MS = commands.Missions(policy=ports.AllowAllPolicy())


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


class Rig:
    """The `test_world.Harness` shape, minimal: principals, a Conversations,
    writer commands, reads and the event log."""

    def __init__(self, db):
        self.db = db

        def reg(kind, scopes):
            return db.writer.execute(commands.register_principal,
                                     {'kind': kind, 'scopes': scopes})['id']

        self.system = Ref('system', reg('system', ['system']))
        self.user = Ref('user_device', reg('user_device', ['observe', 'control', 'admin']))
        self.conv = X.Conversations(missions=MS)

    def run(self, command, who=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=who or self.user))

    def read(self, fn, *args):
        with self.db.read() as c:
            return fn(c, *args)

    def all(self, cls, **eq):
        return self.read(lambda c: [r.entity for r in rows.where(c, cls, **eq)])

    def events(self, etype):
        return [e for e in self.read(queries.events, 0) if e['type'] == etype]

    def texts(self, text):
        """Messages whose text equals *text* (`text` is body JSON, not a column)."""
        return [m for m in self.all(entities.Message) if m.text == text]

    def reply(self, out):
        """The archeus reply a command returned, read back as a row."""
        return self.all(entities.Message, id=out['reply_id'])[0]


@pytest.fixture
def rig(db):
    return Rig(db)


def _tx(db, fn):
    """The P16 seam (`test_ui_seams._tx`): one writer command inserting the
    row the phase never writes, carrying the event the writer demands."""
    def run(tx, **_):
        fn(tx)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            Ref('user_device', ids.new_id('principal')), payload={},
                            workspace=WS))
    return db.writer.execute(run, {})


def _mission(rig, title='M', **over):
    return rig.run(commands.create_mission, title=title, objective='o', **over)['id']


def _post(rig, text, **over):
    return rig.run(X.post_message, text=text, **over)


def _archeus_msg(rig, conv_id, text='ok', cards=(), author='archeus'):
    mid = ids.new_id('message')
    rig.db.writer.execute(_insert_msg, {'actor': rig.user, 'mid': mid,
                                        'conversation_id': conv_id, 'author': author,
                                        'text': text, 'cards': cards})
    return mid


def _insert_msg(tx, *, actor, mid, conversation_id, author, text, cards):
    tx.insert(entities.Message(id=mid, conversation_id=conversation_id, author=author,
                               text=text, cards=tuple(cards)), actor=actor)
    _noted(tx, actor, 'message', mid)


def _approval(rig, mission_id, state='PENDING'):
    aid = ids.new_id('approval')
    rig.db.writer.execute(_insert_approval, {'actor': rig.user, 'aid': aid,
                                             'mission_id': mission_id, 'state': state})
    return aid


def _insert_approval(tx, *, actor, aid, mission_id, state):
    tx.insert(entities.Approval(
        id=aid, subject=Ref('plan', ids.new_id('plan')),
        action_hash=hashlib.sha256(aid.encode()).hexdigest(),
        requested_by=actor.id, kind='plan', mission_id=mission_id, plan_version=1,
        state=state, expires_at='2999-01-01T00:00:00.000Z'), actor=actor)
    _noted(tx, actor, 'approval', aid)


def _idea(rig, state='CAPTURED', promoted=None, text='an idea'):
    iid = ids.new_id('idea')
    rig.db.writer.execute(_insert_idea, {'actor': rig.user, 'iid': iid, 'state': state,
                                         'promoted': promoted, 'text': text})
    return iid


def _insert_idea(tx, *, actor, iid, state, promoted, text):
    tx.insert(entities.Idea(id=iid, workspace_id=WS, text=text, title='I', state=state,
                            promoted_mission_id=promoted), actor=actor)
    _noted(tx, actor, 'idea', iid)


def _knowledge(rig, state='CONFIRMED', title='the standing decision', ktype='DECISION'):
    kid = ids.new_id('knowledge_item')
    rig.db.writer.execute(_insert_knowledge, {'actor': rig.user, 'kid': kid,
                                              'state': state, 'title': title,
                                              'ktype': ktype})
    return kid


def _insert_knowledge(tx, *, actor, kid, state, title, ktype):
    tx.insert(entities.KnowledgeItem(id=kid, workspace_id=WS, type=ktype, title=title,
                                     state=state), actor=actor)
    _noted(tx, actor, 'knowledge_item', kid)


def _intent_row(rig, message_id):
    iid = ids.new_id('intent')
    rig.db.writer.execute(_insert_intent, {'actor': rig.user, 'iid': iid,
                                           'message_id': message_id})
    return iid


def _insert_intent(tx, *, actor, iid, message_id):
    tx.insert(entities.Intent(id=iid, message_id=message_id, utterance='x',
                              kind='control_verb', via='grammar'), actor=actor)
    _noted(tx, actor, 'intent', iid)


def _proposal(kind='new_work', **over):
    """A brain proposal as the read phase would hand it over (P6 seam)."""
    p = {'kind': kind, 'title': 'Pin title', 'objective': 'o', 'desired_outcome': None,
         'target': None, 'project': None, 'mentions': [], 'requirements': [],
         'constraints': [], 'ambiguities': [], 'conflicts': [], 'feedback': None,
         'answer': None, 'confidence': 0.9}
    return dict(p, **over)


def _open_call(tx, *, actor, purpose, source):
    """The P6 seam (`test_knowledge.open_call`): a decided route in the tx."""
    rd = entities.RouteDecision(id=ids.new_id('route_decision'),
                                subject=Ref('archeus_call', purpose), purpose=purpose,
                                decided_by='router', source=Ref(**source),
                                selected='fake', harness_id='fake', result='selected')
    tx.insert(rd, actor=actor)
    tx.append(new_event('route.decided', Ref('route_decision', rd.id), actor,
                        payload={'purpose': purpose, 'selected': 'fake'}))
    return {'route_decision_id': rd.id}


def _apply(rig, text, proposal, in_reply_to=None):
    """The P6 seam: post a user message, then apply a scripted reading."""
    posted = _post(rig, text, in_reply_to=in_reply_to)
    rd = rig.db.writer.execute(_open_call, {
        'actor': rig.system, 'purpose': 'brain',
        'source': {'kind': 'message', 'id': posted['message_id']}})
    out = rig.db.writer.execute(rig.conv.apply_intent, {
        'actor': rig.user, 'message_id': posted['message_id'], 'proposal': proposal,
        'called': {'route_decision_id': rd['route_decision_id'], 'attempts': 1,
                   'account_ref': None, 'usage': None, 'context_package_id': None}})
    return out, posted['message_id']


def _control(rig, text, verb, target=None, arg=''):
    posted = _post(rig, text)
    out = rig.db.writer.execute(rig.conv.apply_control, {
        'actor': rig.user, 'message_id': posted['message_id'], 'verb': verb,
        'target': target, 'arg': arg})
    return out


def _decide(rig, decide, text, approval_id):
    return rig.db.writer.execute(_decide_cmd, {
        'actor': rig.user, 'decide': decide, 'text': text, 'conversation_id': 'primary',
        'approval_id': approval_id, 'action_hash': '0' * 64})


def _decide_cmd(tx, *, actor, decide, text, conversation_id, approval_id, action_hash):
    return X.decide_by_message(tx, actor=actor, decide=decide, text=text,
                               conversation_id=conversation_id, approval_id=approval_id,
                               action_hash=action_hash)


# --- the turn itself: text, conversations, replies, one read per message -------

def test_post_message_demands_real_text(rig):
    # an empty text or a bare whitespace one is refused before anything is read,
    # and a value that is not text at all is refused as text
    for bad in ('', '   \n\t ', 42, None):
        with pytest.raises(ValueError, match='a message has text'):
            _post(rig, bad)
    ok = _post(rig, 'a real turn')
    assert rig.all(entities.Message, id=ok['message_id'])[0].text == 'a real turn'
    assert rig.texts('') == []                                 # the refusals wrote nothing


def test_post_message_routes_primary_and_refuses_an_invented_conversation(rig):
    first = _post(rig, 'first')
    second = _post(rig, 'second', conversation_id='primary')
    assert first['conversation_id'] == second['conversation_id']
    assert rig.all(entities.Conversation, kind='primary')    # the literal routed, not invented
    assert [m.text for m in rig.all(entities.Message)] == ['first', 'second']
    with pytest.raises(NotFound):
        _post(rig, 'nowhere', conversation_id=ids.new_id('conversation'))
    assert rig.texts('nowhere') == []
    assert len(rig.all(entities.Conversation)) == 1


def test_in_reply_to_must_name_a_message_of_the_same_conversation(rig):
    primary = _post(rig, 'primary turn')
    mid = _mission(rig)
    thread = _post(rig, 'thread turn', conversation_id=mid)
    assert thread['conversation_id'] != primary['conversation_id']
    with pytest.raises(ValueError, match='of this conversation'):
        _post(rig, 'crossing', conversation_id=mid, in_reply_to=primary['message_id'])
    with pytest.raises(ValueError, match='of this conversation'):
        _post(rig, 'crossing back', in_reply_to=thread['message_id'])
    with pytest.raises(ValueError, match='of this conversation'):
        _post(rig, 'replying to nothing', in_reply_to=ids.new_id('message'))
    good = _post(rig, 'a real answer', in_reply_to=primary['message_id'])
    assert rig.all(entities.Message, id=good['message_id'])[0].in_reply_to \
        == primary['message_id']
    assert rig.texts('crossing') == []


def test_only_a_user_turn_is_read(rig):
    posted = _post(rig, 'status')
    out = rig.db.writer.execute(rig.conv.apply_control, {
        'actor': rig.user, 'message_id': posted['message_id'], 'verb': 'status',
        'target': None, 'arg': ''})
    archeus_msg = out['reply_id']                             # archeus's own reply
    for command, kw in ((rig.conv.apply_control,
                         {'message_id': archeus_msg, 'verb': 'estop'}),
                        (rig.conv.decline,
                         {'message_id': archeus_msg, 'route_decision_id': None,
                          'state': 'gated'}),
                        (rig.conv.date_meeting,
                         {'message_id': archeus_msg, 'meeting_id': ids.new_id('meeting')})):
        with pytest.raises(ValueError, match='only a user turn'):
            rig.db.writer.execute(command, dict(kw, actor=rig.user))
    assert rig.all(entities.Intent, message_id=archeus_msg) == []   # never read, twice over


def test_a_message_is_read_exactly_once(rig):
    posted = _post(rig, 'status please')
    rig.db.writer.execute(rig.conv.apply_control, {
        'actor': rig.user, 'message_id': posted['message_id'], 'verb': 'status',
        'target': None, 'arg': ''})
    with pytest.raises(ValueError, match='already read'):
        rig.db.writer.execute(rig.conv.apply_control, {
            'actor': rig.user, 'message_id': posted['message_id'], 'verb': 'estop',
            'target': None, 'arg': ''})


# --- the bare `approve` short cut: pending, this mission's, ten at most -------

def test_a_bare_approve_lists_only_what_this_mission_still_has_to_decide(rig):
    mine = _mission(rig, 'Mine')
    other = _mission(rig, 'Other')
    decided = _approval(rig, mine, state='APPROVED')            # decided first, so a filter
    theirs = _approval(rig, other)                              # loosening would show it
    mine_ids = [_approval(rig, mine) for _ in range(12)]
    posted = _post(rig, 'approve', conversation_id=mine)
    out = rig.db.writer.execute(rig.conv.apply_control, {
        'actor': rig.user, 'message_id': posted['message_id'], 'verb': 'approve',
        'target': None, 'arg': ''})
    assert out['resolution'] == 'declined'
    reply = rig.reply(out)
    assert [c['ref']['id'] for c in reply.cards] == mine_ids[:10]     # pending, ours, 10
    assert decided not in [c['ref']['id'] for c in reply.cards]
    assert theirs not in [c['ref']['id'] for c in reply.cards]
    assert [l['ref']['id'] for l in reply.links] == mine_ids[:10]


def test_a_bare_approve_with_nothing_pending_says_so(rig):
    mid = _mission(rig, 'Quiet one')
    _approval(rig, mid, state='APPROVED')                      # decided is not pending
    _approval(rig, _mission(rig, 'Other'))                     # pending, but not ours
    posted = _post(rig, 'approve', conversation_id=mid)
    out = rig.db.writer.execute(rig.conv.apply_control, {
        'actor': rig.user, 'message_id': posted['message_id'], 'verb': 'approve',
        'target': None, 'arg': ''})
    assert out['resolution'] == 'declined'
    reply = rig.reply(out)
    assert reply.text == 'Nothing is waiting for your approval.'
    assert list(reply.cards) == []
    # the bare word was still read and answered, it just decided nothing
    assert [(i.kind, i.reason, i.resolution) for i in rig.all(entities.Intent)] \
        == [('control_verb', 'approve', 'declined')]


# --- deciding and stopping: the words and the card they must point at ---------

def test_a_decision_message_must_say_approve_or_reject(rig):
    mid = _mission(rig, 'Decide me')
    aid = _approval(rig, mid)
    seen = []

    def stub(tx, **kw):
        seen.append(kw['decision'])
        return {'changed': True}

    for text in ('pause', 'stop', 'yes'):
        with pytest.raises(ValueError, match='approve or reject'):
            _decide(rig, stub, text, aid)
    assert seen == []                                           # the decision was never taken
    assert rig.texts('pause') == []
    assert rig.all(entities.Intent) == []


def test_the_decision_reply_says_what_the_decision_was(rig):
    mid = _mission(rig, 'Decide me')
    aid = _approval(rig, mid)
    seen = []

    def denying(tx, **kw):
        seen.append(kw)
        return {'changed': True, 'denied': True}

    out = _decide(rig, denying, 'approve', aid)
    assert seen[0]['decision'] == 'approve' and seen[0]['approval_id'] == aid
    assert rig.reply(out).text \
        == 'The policy denies it now, so nothing was approved for "Decide me".'
    assert rig.all(entities.Intent, id=out['intent_id'])[0].resolution == 'mission_updated'

    out = _decide(rig, lambda tx, **kw: {'changed': False}, 'reject', aid)
    assert rig.reply(out).text == 'Rejected for "Decide me".'
    assert rig.all(entities.Intent, id=out['intent_id'])[0].resolution == 'answered'

    out = _decide(rig, lambda tx, **kw: {'changed': False}, 'approve', aid)
    assert rig.reply(out).text == 'Approved for "Decide me".'
    assert rig.all(entities.Intent, id=out['intent_id'])[0].resolution == 'answered'


def test_confirm_stop_needs_the_word_and_an_archeus_stop_card(rig):
    mid = _mission(rig, 'Stop me')
    conv_id = _post(rig, 'hello')['conversation_id']
    card = [{'type': 'stop', 'ref': {'kind': 'mission', 'id': mid}}]
    carded = _archeus_msg(rig, conv_id, cards=card)
    forged = _archeus_msg(rig, conv_id, cards=card, author='user')
    plain = _archeus_msg(rig, conv_id)

    def confirm(text, message_id):
        return rig.db.writer.execute(rig.conv.confirm_by_message, {
            'actor': rig.user, 'text': text, 'conversation_id': conv_id,
            'message_id': message_id})

    with pytest.raises(ValueError, match='says stop'):
        confirm('cancel', carded)                               # the word must be `stop`
    assert rig.all(entities.Mission, id=mid)[0].state == 'CREATED'
    for wrong in (forged, plain, ids.new_id('message')):        # not user-authored, cardless,
        with pytest.raises(ValueError, match='stop card'):      # or a reply to nothing else
            confirm('stop', wrong)                              # cancels nothing
    assert rig.all(entities.Mission, id=mid)[0].state == 'CREATED'
    assert rig.texts('cancel') == []
    out = confirm('stop', carded)
    assert out['resolution'] == 'mission_updated'
    assert rig.all(entities.Mission, id=mid)[0].state == 'CANCELLED'
    assert rig.reply(out).text == 'Stopped "Stop me": CREATED -> CANCELLED.'
    assert [c['type'] for c in rig.reply(out).cards] == ['mission']


# --- what a reading may do: challenges, continuations, feedback, boundaries ---

def test_a_conflicting_decision_challenges_work_but_never_a_captured_idea(rig):
    kid = _knowledge(rig)                                       # a DECISION, CONFIRMED
    conflict = {'ref': {'kind': 'knowledge_item', 'id': kid}, 'why': 'it forbids this'}
    out, _ = _apply(rig, 'idea: a nightly digest', _proposal('idea', conflicts=[conflict]))
    assert out['resolution'] == 'answered'
    assert [c['type'] for c in rig.reply(out).cards] == ['idea']
    assert rig.all(entities.Mission) == []                      # an idea is not challenged
    out, _ = _apply(rig, 'a sqlite digest then', _proposal(conflicts=[conflict]))
    assert out['resolution'] == 'clarification_requested'
    assert [c['type'] for c in rig.reply(out).cards] == ['challenge']
    it = rig.all(entities.Intent, id=out['intent_id'])[0]
    with pytest.raises(ValueError, match='proceed or drop'):
        rig.db.writer.execute(rig.conv.choose, {'actor': rig.user, 'intent_id': it.id,
                                                'choice': 'maybe'})
    assert rig.all(entities.Mission) == []                      # a rejected choice created none
    out = rig.db.writer.execute(rig.conv.choose, {'actor': rig.user, 'intent_id': it.id,
                                                  'choice': 'drop'})
    assert out['resolution'] == 'declined'
    assert rig.reply(out).text == 'Dropped. Nothing was created.'


def test_a_mission_title_is_collapsed_and_bounded(rig):
    out, _ = _apply(rig, 'build the thing',
                    _proposal('new_work', title='  build   the\n\ththing ' + 'x' * 300))
    assert out['resolution'] == 'mission_created'
    (m,) = rig.all(entities.Mission)
    assert m.title == 'build the hthing ' + 'x' * (120 - len('build the hthing '))
    assert len(m.title) == 120 and '  ' not in m.title and '\t' not in m.title


def test_a_continuation_that_adds_nothing_says_noted_and_writes_no_mission_event(rig):
    mid = _mission(rig, 'Open one')
    before = rig.events('mission.updated')
    out, _ = _apply(rig, 'more of that',
                    _proposal('continue_work', target={'kind': 'mission', 'id': mid}))
    assert out['resolution'] == 'answered'                      # not mission_updated
    assert 'asks nothing new' in rig.reply(out).text
    assert [e for e in rig.events('mission.updated')
            if e['subject']['id'] == mid] == before             # nothing fired
    assert rig.all(entities.Mission, id=mid)[0].requirements == ()


def test_an_idea_already_made_into_a_mission_cannot_be_made_into_one_again(rig):
    idea = _idea(rig, state='IMPLEMENTING', promoted=_mission(rig, 'Promoted'))
    out, _ = _apply(rig, 'turn the digest into a mission',
                    _proposal('new_work', target={'kind': 'idea', 'id': idea}))
    assert out['resolution'] == 'clarification_requested'
    assert 'cannot be made into a mission again' in rig.reply(out).text
    assert [m for m in rig.all(entities.Mission) if m.title == 'Pin title'] == []
    assert rig.all(entities.Idea, id=idea)[0].state == 'IMPLEMENTING'


def test_only_a_clarification_or_challenge_card_answers_an_intent(rig):
    mid = _mission(rig)
    conv_id = _post(rig, 'hello')['conversation_id']
    asked = ids.new_id('intent')
    mission_msg = _archeus_msg(rig, conv_id, cards=[
        {'type': 'mission', 'ref': {'kind': 'mission', 'id': mid}}])
    lookalike = _archeus_msg(rig, conv_id, cards=[
        {'type': 'clarification', 'ref': {'kind': 'mission', 'id': mid}}])
    statused = _archeus_msg(rig, conv_id, cards=[
        {'type': 'status', 'ref': {'kind': 'intent', 'id': asked}}])   # right kind wrong card
    asked_msg = _archeus_msg(rig, conv_id, cards=[
        {'type': 'clarification', 'ref': {'kind': 'intent', 'id': asked}}])
    question = _proposal('question', answer=[{'text': 'The web one.', 'refs': []}])
    for message_id in (mission_msg, lookalike, statused):       # right type wrong kind,
        out, _ = _apply(rig, 'the web one', question,            # right kind wrong type,
                        in_reply_to=message_id)                  # and a plain reply: nothing
        assert rig.all(entities.Intent, id=out['intent_id'])[0].answers_intent_id is None
    out, posted = _apply(rig, 'the web one', question, in_reply_to=asked_msg)
    assert rig.all(entities.Intent, id=out['intent_id'])[0].answers_intent_id == asked


def test_feedback_about_a_target_that_cannot_hold_it_lands_on_the_message(rig):
    mid = _mission(rig, 'Target')
    out, posted = _apply(rig, 'always four spaces', _proposal(
        'preference', target={'kind': 'mission', 'id': mid},
        feedback={'signal': 'positive', 'title': 'Four spaces'}))
    (fb,) = rig.all(entities.Feedback)
    assert (fb.subject.kind, fb.subject.id) == ('message', posted)   # a preference prefers
    assert [(k.state, k.type) for k in rig.all(entities.KnowledgeItem)
            if k.state == 'CANDIDATE'] == [('CANDIDATE', 'PREFERENCE')]
    _apply(rig, 'that project was wrong', _proposal(
        'feedback', target={'kind': 'project', 'id': ids.new_id('project')},
        feedback={'signal': 'negative'}))
    assert sorted(f.subject.kind for f in rig.all(entities.Feedback)) == ['message', 'message']
    _apply(rig, 'that mission was badly named', _proposal(
        'feedback', target={'kind': 'mission', 'id': mid}, feedback={'signal': 'negative'}))
    about = [(f.subject.kind, f.subject.id) for f in rig.all(entities.Feedback)
             if f.subject.kind == 'mission']
    assert about == [('mission', mid)]                           # feedback about a mission stays


def test_a_preference_supersedes_only_an_item_that_is_still_live(rig):
    dead = _knowledge(rig, state='RETRACTED', title='two spaces')
    out, _ = _apply(rig, 'four spaces instead', _proposal(
        'preference', feedback={'signal': 'correction', 'title': 'four spaces',
                                'supersedes': dead}))
    assert out['resolution'] == 'answered'
    assert 'would replace' not in rig.reply(out).text            # no promised replacement
    promoted = [k for k in rig.all(entities.KnowledgeItem) if k.state == 'CANDIDATE'][0]
    assert (promoted.type, promoted.supersedes_id) == ('PREFERENCE', None)
    assert rig.all(entities.KnowledgeItem, id=dead)[0].state == 'RETRACTED'


def test_a_remembered_preference_is_stated_as_the_user_said_it_within_a_bound(rig):
    words = 'prefer four spaces over two. ' * 20                 # 560 characters
    out = _control(rig, 'remember that', 'remember', arg=words)
    assert out['resolution'] == 'answered'
    (k,) = rig.all(entities.KnowledgeItem)
    assert (k.state, k.origin, k.type) == ('CONFIRMED', 'explicit', 'PREFERENCE')
    assert k.title == words[:200] and len(k.title) == 200
    assert rig.reply(out).text.startswith('Remembered: "%s"' % words[:200])


# --- resources, status, meetings and the mission thread ----------------------

def test_a_conversation_never_widens_a_last_resort_account_or_touches_an_ended_mission(rig):
    scarce = rig.run(resources.register_account, harness_id='fake', label='Scarce',
                     auth_kind='api_key')['id']
    normal = rig.run(resources.register_account, harness_id='fake', label='Normal',
                     auth_kind='api_key')['id']
    _set_consumption(rig, scarce, 'last_resort')
    mid = _mission(rig, 'Work')
    msg_id = _post(rig, 'use Scarce for Work')['message_id']
    iid = _intent_row(rig, msg_id)

    def directive(**kw):
        return rig.db.writer.execute(_directive_cmd, dict(
            {'actor': rig.user, 'msg_id': msg_id, 'intent_id': iid, 'mission_id': mid}, **kw))

    text, resolution, cards, links = directive(prefer=[_account_ref(scarce)])
    assert resolution == 'answered' and [c['type'] for c in cards] == ['change']
    assert cards[0]['command']['name'] == 'setMissionResources'
    prefs = rig.all(entities.Mission, id=mid)[0].resource_preferences or {}
    assert 'preferred_accounts' not in prefs                     # it only asked, at most
    text, resolution, cards, links = directive(prefer=[_account_ref(normal)])
    assert resolution == 'mission_updated'
    assert rig.all(entities.Mission, id=mid)[0].resource_preferences['preferred_accounts'] \
        == [normal]
    rig.run(MS.cancel, mission_id=mid)
    text, resolution, cards, links = directive(forbid=[_account_ref(normal)])
    assert resolution == 'declined' and 'has ended' in text
    assert cards == [] and links == []
    prefs = rig.all(entities.Mission, id=mid)[0].resource_preferences or {}
    assert normal not in (prefs.get('forbidden_accounts') or [])


def _account_ref(account_id):
    return {'kind': 'account', 'id': account_id}


def _directive_cmd(tx, *, actor, msg_id, intent_id, mission_id, prefer=(), forbid=()):
    return X.directive(tx, actor, tx.get(entities.Message, msg_id).entity,
                       tx.get(entities.Intent, intent_id).entity, mission_id,
                       prefer=prefer, forbid=forbid, scope='mission')


def _set_consumption(rig, account_id, value):
    with rig.db.read() as c:
        pid = rows.where(c, entities.ResourcePolicy, account_id=account_id)[0].entity.id

    def command(tx, *, actor):
        tx.update(entities.ResourcePolicy, pid, {'consumption': value}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            actor, payload={}, workspace=WS))
    return rig.db.writer.execute(command, {'actor': rig.user})


def test_the_status_line_counts_and_links_only_open_missions(rig):
    live = _mission(rig, 'Live one')
    gone = _mission(rig, 'Gone one')
    rig.run(MS.cancel, mission_id=gone)
    out = _control(rig, 'status', 'status')
    reply = rig.reply(out)
    assert '0 project(s), 1 open mission(s)' in reply.text
    assert 'Live one' in reply.text and 'Gone one' not in reply.text
    assert [l['ref']['id'] for l in reply.links if l['ref']['kind'] == 'mission'] == [live]


def test_a_meeting_is_dated_once_and_only_from_a_real_date(rig):
    mt = ids.new_id('meeting')
    rig.db.writer.execute(_insert_meeting, {'actor': rig.user, 'mt': mt})
    undated = _post(rig, 'it was last tuesday')['message_id']
    out = rig.db.writer.execute(rig.conv.date_meeting, {
        'actor': rig.user, 'message_id': undated, 'meeting_id': mt})
    assert out['resolution'] == 'declined'
    assert 'no date like' in rig.reply(out).text
    assert rig.all(entities.Meeting, id=mt)[0].held_at is None
    dated = _post(rig, 'it was 2026-09-20')['message_id']
    out = rig.db.writer.execute(rig.conv.date_meeting, {
        'actor': rig.user, 'message_id': dated, 'meeting_id': mt})
    assert out['resolution'] == 'answered'
    assert rig.reply(out).text == 'Dated "Weekly": held 2026-09-20.'
    assert rig.all(entities.Meeting, id=mt)[0].held_at == '2026-09-20'
    again = _post(rig, 'actually 1999-01-01')['message_id']
    out = rig.db.writer.execute(rig.conv.date_meeting, {
        'actor': rig.user, 'message_id': again, 'meeting_id': mt})
    assert out['resolution'] == 'declined'
    assert 'already has a date' in rig.reply(out).text
    assert rig.all(entities.Meeting, id=mt)[0].held_at == '2026-09-20'


def _noted(tx, actor, kind, entity_id):
    """The event the writer demands for any mutation (`test_ui_seams._tx` shape),
    a registered type no conversation command emits, about a row no test reads."""
    tx.append(new_event('checkpoint.created',
                        Ref('checkpoint', ids.new_id('checkpoint')), actor,
                        payload={'why': 'fixture row %s/%s' % (kind, entity_id)},
                        workspace=WS))


def _insert_meeting(tx, *, actor, mt):
    tx.insert(entities.Meeting(id=mt, workspace_id=WS, name='Weekly'), actor=actor)
    _noted(tx, actor, 'meeting', mt)


def test_follow_mission_moves_only_the_idea_that_mission_promoted(rig):
    mid = _mission(rig, 'Promoted one')
    other = _mission(rig, 'The other')
    mine = _idea(rig, state='IMPLEMENTING', promoted=mid)
    wrong_mission = _idea(rig, state='IMPLEMENTING', promoted=other)
    wrong_state = _idea(rig, state='PLANNED', promoted=mid)
    out = rig.db.writer.execute(rig.conv.follow_mission, {'actor': rig.user,
                                                          'mission_id': mid,
                                                          'to': 'CANCELLED'})
    assert out == {'ideas': [mine]}
    assert rig.all(entities.Idea, id=mine)[0].state == 'PLANNED'
    assert rig.all(entities.Idea, id=wrong_mission)[0].state == 'IMPLEMENTING'
    assert rig.all(entities.Idea, id=wrong_state)[0].state == 'PLANNED'
