"""Conversational resource directives for accounts and harnesses (P19 B10;
ADR-0042 §1-§4, Part H2; testing-strategy §8 G3, G4, G14). Narrowing and
preference land on the mission at once, each entry with the message and intent
it came from; widening and standing changes are only proposed, on a `change`
card whose command is the existing `admin` route; a name that resolves to
nothing is a clarification; nothing a conversation adds lifts a protected
account. On the real database, through the writer; a scripted brain."""

import pytest

from archeus.api import routes
from archeus.core.application import commands, grammar, resources
from archeus.core.application.conversation import post_message
from archeus.core.domain import entities
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.routing import router as R

from v1.integration.test_intent import brain, make  # noqa: F401 (fixture)


def _rig(make, *recordings):  # noqa: F811
    rg = make([brain(*recordings)])
    rg.conv.harnesses = lambda: {'fake'}             # the registry's, in a real Core
    acc = {label: rg.run(resources.register_account, harness_id='claude_code', label=label,
                         auth_kind='api_key')['id'] for label in ('A', 'B', 'Shared')}
    rg.run(resources.set_resource_policy, account_id=acc['Shared'], consumption='explicit_only')
    return rg, acc


def _say(rg, text, conversation=None):
    """The rig's `say`, in a mission's thread when *conversation* names one."""
    from archeus.core.application import queries
    posted = rg.run(post_message, text=text, conversation_id=conversation)
    rg.settle()
    reply = rg.read(queries.reply_to, posted['message_id'])
    return reply, rg.all(entities.Intent, message_id=posted['message_id'])[0]


def _mission(rg, title='M'):
    return rg.run(commands.create_mission, title=title, objective='o')['id']


def _prefs(rg, mid):
    return rg.all(entities.Mission, id=mid)[0].resource_preferences or {}


def _consumption(rg, acc):
    return rg.all(entities.ResourcePolicy, account_id=acc)[0].consumption


def test_dont_use_narrows_the_named_mission_with_its_message_and_intent(make):  # noqa: F811
    rg, acc = _rig(make)
    mid = _mission(rg)
    reply, it = rg.say("don't use account A for M")
    assert (it.via, it.reason, it.resolution) == ('grammar', 'dont_use', 'mission_updated')
    rp = _prefs(rg, mid)
    assert rp['forbidden_accounts'] == [acc['A']]
    assert rp['directives'] == [{'key': 'forbidden_accounts', 'id': acc['A'],
                                 'message_id': it.message_id, 'intent_id': it.id}]
    assert [c['type'] for c in reply['cards']] == ['mission']    # named: no standing offer
    assert 'no longer using account "A"' in reply['text']
    assert _consumption(rg, acc['A']) is None or _consumption(rg, acc['A']) == 'normal'


def test_an_ambiguous_dont_use_is_the_missions_and_offers_standing_without_applying_it(make):  # noqa: F811
    rg, acc = _rig(make)
    mid = _mission(rg)
    before = _consumption(rg, acc['A'])
    reply, it = _say(rg, "Don't use A", conversation=mid)
    assert _prefs(rg, mid)['forbidden_accounts'] == [acc['A']]
    (card,) = [c for c in reply['cards'] if c['type'] == 'change']
    assert (card['scope'], card['ref']) == ('standing', {'kind': 'account', 'id': acc['A']})
    assert card['command'] == {'name': 'setResourcePolicy', 'id': acc['A'],
                               'body': {'consumption': 'explicit_only'}}
    assert _consumption(rg, acc['A']) == before                 # G14: no global change


def test_use_prefers_a_normal_account_and_proposes_a_protected_one(make):  # noqa: F811
    rg, acc = _rig(make)
    mid = _mission(rg)
    _reply, it = rg.say('use B for M')
    assert _prefs(rg, mid)['preferred_accounts'] == [acc['B']]
    reply, it = rg.say('use account Shared for M')               # explicit_only: widening
    assert it.resolution == 'answered'
    assert _prefs(rg, mid)['preferred_accounts'] == [acc['B']]  # G3: nothing applied
    (card,) = [c for c in reply['cards'] if c['type'] == 'change']
    assert card['scope'] == 'mission' and card['command']['name'] == 'setMissionResources'
    assert card['command']['body']['preferred_accounts'] == [acc['B'], acc['Shared']]
    assert card['based_on'] == _prefs(rg, mid)['since']
    # confirmed from a user device, through the route a control uses
    rg.run(resources.set_mission_resources, mission_id=mid, preferences=card['command']['body'])
    rp = _prefs(rg, mid)
    assert rp['preferred_accounts'] == [acc['B'], acc['Shared']] and 'directives' not in rp


def test_lifting_a_forbid_is_widening_and_only_proposed(make):  # noqa: F811
    rg, acc = _rig(make)
    mid = _mission(rg)
    rg.say("don't use A for M")
    reply, _it = rg.say('use A for M')
    assert _prefs(rg, mid)['forbidden_accounts'] == [acc['A']]
    (card,) = [c for c in reply['cards'] if c['type'] == 'change']
    body = card['command']['body']
    assert acc['A'] not in body['forbidden_accounts'] and acc['A'] in body['preferred_accounts']


def test_the_grammar_reads_use_and_dont_use_and_leaves_what_it_cannot_resolve(make):  # noqa: F811
    rg, acc = _rig(make)
    mid = _mission(rg)
    with rg.db.read() as conn:
        got = grammar.resolve(conn, "Don\u2019t use account A for M.")
        assert got == grammar.Control('dont_use', {'kind': 'mission', 'id': mid}, {
            'resource': {'kind': 'account', 'id': acc['A']}, 'scope': 'mission'})
        assert grammar.resolve(conn, 'do not use B for M').verb == 'dont_use'
        assert grammar.resolve(conn, 'use harness fake for M', harnesses=('fake',)).arg[
            'resource'] == {
            'kind': 'harness', 'id': 'fake'}
        assert grammar.resolve(conn, 'use B', mission=mid).arg['scope'] == 'ambiguous'
        for text in ("don't use Nobody for M", "don't use A for Nowhere", "don't use A"):
            assert grammar.resolve(conn, text) is None, text      # the brain's, never guessed


def test_the_brains_directive_lands_on_the_mission_it_creates(make):  # noqa: F811
    rg, acc = _rig(make, ('Ship it, but not on account A', {
        'kind': 'new_work', 'title': 'Ship it', 'objective': 'Ship.',
        'resource_directive': {'scope': 'mission', 'forbid': {'accounts': ['A']}}}))
    reply, it = rg.say('Ship it, but not on account A')
    assert it.resolution == 'mission_created', (reply, it.reason)
    (m,) = rg.all(entities.Mission)
    assert m.resource_preferences['forbidden_accounts'] == [acc['A']]
    (d,) = m.resource_preferences['directives']
    assert (d['message_id'], d['intent_id']) == (it.message_id, it.id)           # G4
    assert 'no longer using account "A"' in reply['text']


def test_an_unresolved_name_from_the_brain_is_a_clarification_and_writes_nothing(make):  # noqa: F811
    rg, acc = _rig(make, ('Ship it without the Ghost account', {
        'kind': 'new_work', 'title': 'Ship it', 'objective': 'Ship.',
        'resource_directive': {'scope': 'mission', 'forbid': {'accounts': ['Ghost']}}}))
    reply, it = rg.say('Ship it without the Ghost account')
    assert it.resolution == 'clarification_requested'
    assert 'Ghost' in reply['text'] and not rg.all(entities.Mission)             # G4


def test_never_is_a_standing_change_card_and_changes_no_policy(make):  # noqa: F811
    rg, acc = _rig(make, ('Never use account A again', {
        'kind': 'preference', 'feedback': {'signal': 'correction', 'title': 'no A'},
        'resource_directive': {'scope': 'standing', 'forbid': {'accounts': ['A']}}}))
    before = _consumption(rg, acc['A'])
    reply, it = rg.say('Never use account A again')
    (card,) = reply['cards']
    assert (card['type'], card['scope']) == ('change', 'standing')
    assert card['command'] == {'name': 'setResourcePolicy', 'id': acc['A'],
                               'body': {'consumption': 'explicit_only'}}
    assert _consumption(rg, acc['A']) == before                         # G3, G14
    assert not rg.all(entities.KnowledgeItem)                            # not a candidate


def test_only_a_user_devices_message_carries_a_directive(make):  # noqa: F811
    rg, acc = _rig(make)
    mid = _mission(rg)
    posted = rg.db.writer.execute(post_message, {'actor': rg.system,
                                                 'text': "don't use A for M"})
    rg.settle()
    it = rg.all(entities.Intent, message_id=posted['message_id'])[0]
    assert it.resolution == 'declined'
    assert 'forbidden_accounts' not in _prefs(rg, mid)


def test_a_conversational_preference_lifts_no_protected_account():
    """G14: a preference a conversation added orders; it never names an
    `explicit_only` or `last_resort` account into eligibility."""
    c = {'account': 'acc_x', '_a': {'policy': {'consumption': 'explicit_only'}}}
    by_device = {'preferred': {'accounts': ['acc_x']}}
    by_chat = dict(by_device, conversational={'accounts': ['acc_x']})
    assert R._named(c, by_device) and not R._named(c, by_chat)
    assert R._restriction(dict(c, harness='fake', account_ref=None), by_chat, {}) == \
        'used only when you name it (explicit_only)'


def test_the_routes_a_change_card_runs_stay_admin():
    """G3: the policy route, and the mission's resources, need `admin`."""
    scope = {r.handler.__name__: r.scope for r in routes.ROUTES}
    assert scope['set_resource_policy'] == 'admin' and scope['set_mission_resources'] == 'admin'


def _chat_prefers(tx, *, actor, mission_id, account):
    """The mission's preferences exactly as a conversation's `use` leaves them."""
    prefs = {'preferred_accounts': [account], 'since': tx.now, 'directives': [
        {'key': 'preferred_accounts', 'id': account, 'message_id': 'msg_x', 'intent_id': 'int_x'}]}
    tx.update(entities.Mission, mission_id, {'resource_preferences': prefs}, actor=actor)
    tx.append(new_event('mission.updated', Ref('mission', mission_id), actor,
                        payload={'resource_preferences': prefs}))


def test_a_preference_a_conversation_added_never_routes_to_an_explicit_only_account(db):
    """G14 through the real snapshot and router: the same account, preferred by
    the conversation, stays eliminated; preferred by a user device, it runs."""
    from v1.integration.test_policy import task
    from v1.integration.test_routing import Rig as RouteRig
    r = RouteRig(db)
    normal = r.account('Normal')
    shared = r.account('Shared', consumption='explicit_only')
    mid = r.ready(task('t1', 'write_repo'), task('t2', 'write_repo'))
    r.do(_chat_prefers, who=r.system, mission_id=mid, account=shared)
    assert r.dispatch(mid, 't1')['account_id'] == normal
    (rd,) = r.rds(mission_id=mid)
    assert next(c for c in rd.candidates if c['resource'] == shared)['reason'] == \
        'used only when you name it (explicit_only)'
    r.do(resources.set_mission_resources, who=r.user, mission_id=mid,
         preferences={'preferred_accounts': [shared]})
    assert r.dispatch(mid, 't2')['account_id'] == shared
