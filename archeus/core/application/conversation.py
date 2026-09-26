"""Conversation, intent and mission creation (P7; plan §11, domain-model §6,
ADR-0006, ADR-0015; p7-design-gate).

Every function here is a writer command. None calls a model: the brain's answer
arrives already validated and resolved (`core/brain/intent.py`), and what it
MEANS for the world is decided here, deterministically, on the rows as they
are in this transaction:

    control verb (grammar)          -> the mission action, status, why, remember
    question                        -> an answer whose every claim cites an object
    material ambiguity, or a named
      project/mission/idea not found -> a clarification; nothing else is written
    new_work / continue_work that
      goes against a decision        -> a challenge (the user chooses); no mission
    new_work                         -> a Mission in CREATED (or an idea promoted)
    continue_work                    -> the open mission's requirements grow
    idea                             -> an Idea in CAPTURED
    feedback / preference            -> Feedback, and a CANDIDATE it promotes

One message is read once (`intents.message_id` is unique), so a retried or
re-delivered message never makes a second mission. Missions move only through
`Missions` (P3), ideas only through `lifecycle.fire`; nothing here plans,
routes, authorises or executes.
"""

import re

from ..domain import entities, ids, states
from ..domain.events import new_event
from ..domain.values import Ref
from . import calls as C
from . import knowledge as K
from . import lifecycle

#: resolvable world kinds: one of these named and not found is never guessed
RESOLVABLE = ('project', 'mission', 'idea')
_DATE = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')


def primary(tx, actor):
    """The one primary conversation (domain-model §6), made on first use."""
    got = tx.where(entities.Conversation, kind='primary')
    if got:
        return got[0].entity.id
    c = entities.Conversation(id=ids.new_id('conversation'), kind='primary')
    tx.insert(c, actor=actor)
    return c.id


def _message(tx, actor, *, conversation_id, author, text, in_reply_to=None, cards=(),
             links=(), intent_id=None):
    m = entities.Message(id=ids.new_id('message'), conversation_id=conversation_id,
                         author=author, text=text, in_reply_to=in_reply_to,
                         cards=tuple(cards), links=tuple(links), intent_id=intent_id,
                         principal_id=actor.id)
    tx.insert(m, actor=actor)
    e = tx.append(new_event('message.created', Ref('message', m.id), actor, payload={
        'author': author, 'conversation_id': conversation_id, 'in_reply_to': in_reply_to,
        'cards': [dict(c) for c in m.cards]}))
    return m, e


def post_message(tx, *, actor, text, conversation_id=None, in_reply_to=None):
    """A user turn. Its interpretation arrives later, as the reply (the intent
    worker); this only records it (api-and-realtime §2)."""
    if not (isinstance(text, str) and text.strip()):
        raise ValueError('a message has text')
    if conversation_id is None or conversation_id == 'primary':
        conversation_id = primary(tx, actor)
    elif tx.get(entities.Conversation, conversation_id) is None:
        raise lifecycle.NotFound(conversation_id)
    if in_reply_to is not None:
        r = tx.get(entities.Message, in_reply_to)
        if r is None or r.entity.conversation_id != conversation_id:
            raise ValueError('in_reply_to is a message of this conversation')
    m, e = _message(tx, actor, conversation_id=conversation_id, author='user', text=text,
                    in_reply_to=in_reply_to)
    return {'message_id': m.id, 'conversation_id': conversation_id, 'seq': e.seq}


def ask_meeting_date(tx, *, actor, meeting_id, name):
    """Undated notes were imported (P7 D2): ask for the date in the primary
    conversation. The meeting keeps `held_at` empty until the user says."""
    _message(tx, actor, conversation_id=primary(tx, actor), author='archeus',
             text='The notes "%s" say nothing about when the meeting was held. When was it? '
                  'Reply to this message with the date (YYYY-MM-DD).' % name,
             cards=[{'type': 'clarification', 'ref': {'kind': 'meeting', 'id': meeting_id},
                     'asks': 'held_at'}],
             links=[{'ref': {'kind': 'meeting', 'id': meeting_id}}])


def _card(type_, kind, id_, **extra):
    return dict(extra, type=type_, ref={'kind': kind, 'id': id_})


def _link(ref):
    return {'ref': {'kind': ref['kind'], 'id': ref['id']}}


def _intent(tx, actor, msg, **fields):
    if tx.where(entities.Intent, message_id=msg.id):
        raise ValueError('message %s was already read' % msg.id)
    it = entities.Intent(id=ids.new_id('intent'), message_id=msg.id, utterance=msg.text,
                         **fields)
    tx.insert(it, actor=actor)
    return it


def _reply(tx, actor, msg, intent, text, cards=(), links=()):
    seen, uniq = set(), []
    for link in links:
        k = (link['ref']['kind'], link['ref']['id'])
        if k not in seen:
            seen.add(k)
            uniq.append(link)
    m, e = _message(tx, actor, conversation_id=msg.conversation_id, author='archeus',
                    text=text, in_reply_to=msg.id, cards=cards, links=uniq,
                    intent_id=intent.id)
    return {'reply_id': m.id, 'intent_id': intent.id, 'resolution': intent.resolution,
            'seq': e.seq}


def _set(tx, actor, intent, **fields):
    tx.update(entities.Intent, intent.id, fields, actor=actor)
    return tx.get(entities.Intent, intent.id).entity


def _user(tx, message_id):
    msg = lifecycle.load(tx, entities.Message, message_id).entity
    if msg.author != 'user':
        raise ValueError('only a user turn is read for intent')
    return msg


class Conversations:
    """The commands of the intent pipeline. `missions` is the P3 `Missions`:
    the only way a mission moves (pause, resume, cancel)."""

    def __init__(self, *, missions):
        self.missions = missions

    # ── the deterministic grammar ──

    def apply_control(self, tx, *, actor, message_id, verb, target=None, arg=''):
        """A control verb the grammar recognised and resolved (no model call)."""
        msg = _user(tx, message_id)
        it = _intent(tx, actor, msg, kind='control_verb', via='grammar',
                     target_refs=(target,) if target else (), reason=verb)
        cards, links, resolution = [], [], 'answered'
        if target:
            links.append(_link(target))
        from .grammar import NOT_YET
        if verb in NOT_YET:
            text = '"%s" is recognised, but acting on it arrives with %s.' % (verb,
                                                                            NOT_YET[verb])
            resolution = 'declined'
        elif verb in ('pause', 'resume', 'cancel'):
            text, resolution = self._mission_verb(tx, actor, verb, target['id'], msg)
            cards.append(_card('mission', 'mission', target['id']))
        elif verb == 'status':
            text, more = _status(tx, target)
            links += more
            cards.append(_card('status', target['kind'] if target else 'workspace',
                               target['id'] if target else ids.GLOBAL_WORKSPACE))
        elif verb == 'why':
            text = _why(tx, target)
        else:                                               # remember
            text, k = _remember(tx, actor, arg, msg)
            cards.append(_card('knowledge', 'knowledge_item', k))
            links.append({'ref': {'kind': 'knowledge_item', 'id': k}})
        it = _set(tx, actor, it, resolution=resolution)
        return _reply(tx, actor, msg, it, text, cards, links)

    def _mission_verb(self, tx, actor, verb, mission_id, msg):
        m = lifecycle.load(tx, entities.Mission, mission_id).entity
        try:
            getattr(self.missions, verb)(tx, actor=actor, mission_id=mission_id,
                                         reason='%s: asked in message %s' % (verb, msg.id))
        except (lifecycle.IllegalTrigger, lifecycle.GuardFailed) as e:
            return ('I cannot %s "%s": it is %s (%s).' % (verb, m.title, m.state, e),
                    'declined')
        now = lifecycle.load(tx, entities.Mission, mission_id).entity.state
        done = {'pause': 'Paused', 'resume': 'Resumed', 'cancel': 'Cancelled'}[verb]
        return '%s "%s": %s -> %s.' % (done, m.title, m.state, now), 'mission_updated'

    # ── the brain's reading ──

    def decline(self, tx, *, actor, message_id, route_decision_id, state, detail=''):
        """The brain could not read the message (gated, no harness, invalid
        output twice, …). The call already ended; the reply says why, and
        nothing else is written (ADR-0006: then the user is asked)."""
        msg = _user(tx, message_id)
        it = _intent(tx, actor, msg, kind='question', route_decision_id=route_decision_id,
                     resolution='declined', reason='%s: %s' % (state, detail))
        why = {'gated': 'no harness is permitted to make the call yet (provider terms, '
                        'ADR-0021: `archeus terms <harness> permit`)',
               'invalid': 'the reading did not pass validation twice',
               'unavailable': 'no harness that can make the call is installed'}
        return _reply(tx, actor, msg, it, 'I could not read this message: %s. Please '
                      'rephrase it, or use a control verb (pause, resume, status, why, '
                      'remember).' % why.get(state, '%s (%s)' % (state, detail)))

    def apply_intent(self, tx, *, actor, message_id, proposal, called):
        """Apply a validated, resolved reading and end its call, in one
        transaction: either all of it — intent, reply, and whatever the intent
        makes — or none, and the call ends `failed` instead."""
        msg = _user(tx, message_id)
        p = proposal
        _end(tx, actor, called, kind=p['kind'])
        answering = None
        if msg.in_reply_to is not None:
            answering = _pending_clarification(tx, msg.in_reply_to)
        it = _intent(tx, actor, msg, kind=p['kind'], via='brain',
                     project_id=None if p['project'] is None else p['project']['id'],
                     target_refs=tuple(r for r in [p['target'], p['project']] if r),
                     ambiguities=tuple(p['ambiguities']), conflicts=tuple(p['conflicts']),
                     confidence=p.get('confidence'), proposal=p,
                     route_decision_id=called['route_decision_id'],
                     context_package_id=called['context_package_id'],
                     answers_intent_id=answering)
        kind = p['kind']
        if kind == 'question':
            return self._answer(tx, actor, msg, it, p)
        unresolved = [m for m in p['mentions'] if m['ref'] is None and m['kind'] in RESOLVABLE]
        material = [a for a in p['ambiguities'] if a['material']]
        stale = _stale_target(tx, p)
        if unresolved or material or stale:
            return self._clarify(tx, actor, msg, it, unresolved, material, stale)
        if kind in ('new_work', 'continue_work') and p['conflicts']:
            return self._challenge(tx, actor, msg, it, p)
        return self._commit(tx, actor, msg, it, p)

    def _commit(self, tx, actor, msg, it, p, extra_constraints=()):
        kind = p['kind']
        if kind == 'new_work':
            return self._new_work(tx, actor, msg, it, p, extra_constraints)
        if kind == 'continue_work':
            return self._continue(tx, actor, msg, it, p, extra_constraints)
        if kind == 'idea':
            return self._idea(tx, actor, msg, it, p)
        return self._feedback(tx, actor, msg, it, p)

    def _answer(self, tx, actor, msg, it, p):
        it = _set(tx, actor, it, resolution='answered')
        links = [_link(r) for c in p['answer'] for r in c['refs']]
        return _reply(tx, actor, msg, it, ' '.join(c['text'] for c in p['answer']),
                      links=links)

    def _clarify(self, tx, actor, msg, it, unresolved, material, stale):
        qs = ['I do not know a %s called "%s". Which one do you mean?' % (m['kind'], m['name'])
              for m in unresolved]
        qs += [a['question'] for a in material] + stale
        it = _set(tx, actor, it, resolution='clarification_requested',
                  reason='; '.join(qs))
        return _reply(tx, actor, msg, it, 'Before I act on this: ' + ' '.join(qs),
                      cards=[_card('clarification', 'intent', it.id, questions=qs)])

    def _challenge(self, tx, actor, msg, it, p):
        parts, against = [], []
        for c in p['conflicts']:
            k = lifecycle.load(tx, entities.KnowledgeItem, c['ref']['id']).entity
            against.append(k.id)
            label = ('the confirmed %s' % k.type.lower() if k.state == 'CONFIRMED'
                     else 'a %s recorded in meeting notes (not confirmed)' % k.type.lower())
            parts.append('%s "%s" (%s): %s' % (label, k.title, k.id, c['why']))
        it = _set(tx, actor, it, resolution='clarification_requested',
                  reason='challenged: ' + ', '.join(against))
        return _reply(tx, actor, msg, it,
                      'This goes against %s. Should I proceed anyway, or drop it?'
                      % '; and '.join(parts),
                      cards=[_card('challenge', 'intent', it.id, against=against,
                                   choices=['proceed', 'drop'])],
                      links=[{'ref': {'kind': 'knowledge_item', 'id': k}} for k in against])

    def _new_work(self, tx, actor, msg, it, p, extra_constraints):
        target = p['target']
        if target is not None:                             # an idea made into work
            return self._promote(tx, actor, msg, it, p, target['id'], extra_constraints)
        project = None if p['project'] is None else p['project']['id']
        m = _mission(tx, actor, p, project=project, origin='conversation', origin_ref=msg.id,
                     msg=msg, extra_constraints=extra_constraints)
        it = _set(tx, actor, it, resolution='mission_created')
        links = [{'ref': {'kind': 'mission', 'id': m.id}}]
        if project:
            links.append({'ref': {'kind': 'project', 'id': project}})
        return _reply(tx, actor, msg, it, 'I have taken this on as a mission: "%s" (%s)%s.'
                      % (m.title, m.id, _inferred(m)),
                      cards=[_card('mission_proposal', 'mission', m.id)], links=links)

    def _promote(self, tx, actor, msg, it, p, idea_id, extra_constraints):
        idea = lifecycle.load(tx, entities.Idea, idea_id).entity
        m = _mission(tx, actor, dict(p, title=p.get('title') or idea.title or idea.text,
                                     objective=p.get('objective') or idea.text),
                     project=idea.project_id or (p['project'] or {}).get('id'),
                     origin='idea', origin_ref=idea.id, msg=msg,
                     extra_constraints=extra_constraints)
        why = 'made into mission %s (message %s)' % (m.id, msg.id)
        # the diagram's allowed shortcuts only (state-machines §1): understood
        # from the brain's reading, planned by the user's decision, promoted
        for trigger in PROMOTE_PATH.get(idea.state, ()):
            fields = {'promoted_mission_id': m.id} if trigger == 'promote' else None
            lifecycle.fire(tx, entities.Idea, idea.id, trigger, actor=actor, reason=why,
                           fields=fields)
        it = _set(tx, actor, it, resolution='mission_created')
        return _reply(tx, actor, msg, it, 'Idea %s is now mission "%s" (%s)%s.'
                      % (idea.id, m.title, m.id, _inferred(m)),
                      cards=[_card('mission_proposal', 'mission', m.id),
                             _card('idea', 'idea', idea.id)],
                      links=[{'ref': {'kind': 'mission', 'id': m.id}},
                             {'ref': {'kind': 'idea', 'id': idea.id}}])

    def _continue(self, tx, actor, msg, it, p, extra_constraints):
        mid = p['target']['id']
        row = lifecycle.load(tx, entities.Mission, mid)
        m = row.entity
        req = _items(p['requirements'], msg)
        con = _items(p['constraints'], msg) + list(extra_constraints)
        if not (req or con):
            it = _set(tx, actor, it, resolution='answered',
                      reason='nothing to add to %s' % mid)
            return _reply(tx, actor, msg, it, 'Noted for mission "%s" (%s); it asks nothing '
                          'new of it.' % (m.title, mid),
                          cards=[_card('mission', 'mission', mid)],
                          links=[{'ref': {'kind': 'mission', 'id': mid}}])
        tx.update(entities.Mission, mid, {'requirements': m.requirements + tuple(req),
                                          'constraints': m.constraints + tuple(con)},
                  actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor, payload={
            'fields': [f for f, v in (('requirements', req), ('constraints', con)) if v],
            'added': {'requirements': req, 'constraints': con}, 'message_id': msg.id},
            workspace=m.workspace_id, project=m.project_id))
        it = _set(tx, actor, it, resolution='mission_updated')
        return _reply(tx, actor, msg, it, 'Added to mission "%s" (%s): %s.' % (
            m.title, mid, '; '.join(c['text'] for c in req + con)),
            cards=[_card('mission', 'mission', mid)],
            links=[{'ref': {'kind': 'mission', 'id': mid}}])

    def _idea(self, tx, actor, msg, it, p):
        project = None if p['project'] is None else p['project']['id']
        idea = entities.Idea(id=ids.new_id('idea'), workspace_id=_workspace(tx, project),
                             project_id=project, text=msg.text,
                             title=(p.get('title') or p.get('objective') or '').strip(),
                             origin_message_id=msg.id)
        tx.insert(idea, actor=actor)
        tx.append(new_event('idea.created', Ref('idea', idea.id), actor,
                            payload={'title': idea.title, 'message_id': msg.id},
                            workspace=idea.workspace_id, project=project))
        it = _set(tx, actor, it, resolution='answered', reason='captured idea %s' % idea.id)
        return _reply(tx, actor, msg, it, 'Captured as an idea: "%s" (%s). It is not a '
                      'commitment; ask me to make it a mission when you want it done.'
                      % (idea.title or idea.text, idea.id),
                      cards=[_card('idea', 'idea', idea.id)],
                      links=[{'ref': {'kind': 'idea', 'id': idea.id}}])

    def _feedback(self, tx, actor, msg, it, p):
        """Feedback and preferences land on P6's `record_feedback`: history,
        and at most a CANDIDATE (never confirmed from a model's reading)."""
        fb, target = p['feedback'], p['target']
        subject = target if (p['kind'] == 'feedback' and target
                             and target['kind'] in K.FEEDBACK_SUBJECTS) else {
            'kind': 'message', 'id': msg.id}
        promote_type = 'PREFERENCE' if p['kind'] == 'preference' else fb.get('promote')
        promote = None
        note = ''
        if promote_type and (fb.get('title') or '').strip():
            promote = {'type': promote_type, 'title': fb['title'].strip()}
            sup = fb.get('supersedes')
            if sup is not None:
                old = tx.get(entities.KnowledgeItem, sup)
                if old is not None and old.entity.state in ('CANDIDATE', 'CONFIRMED'):
                    promote['supersedes_id'] = sup
                    note = '; it would replace "%s" (%s)' % (old.entity.title, sup)
        out = K.record_feedback(tx, actor=actor, subject=subject, signal=fb['signal'],
                                text=msg.text, promote=promote)
        it = _set(tx, actor, it, resolution='answered',
                  reason='feedback %s' % out['feedback_id'])
        k = out['promoted']
        if k is None:
            return _reply(tx, actor, msg, it, 'Noted as feedback (%s).' % out['feedback_id'],
                          links=[{'ref': dict(subject)}])
        return _reply(tx, actor, msg, it, 'Noted as a proposed %s: "%s" (%s), not confirmed '
                      'yet%s.' % (k['type'].lower(), k['title'], k['id'], note),
                      cards=[_card('knowledge', 'knowledge_item', k['id'])],
                      links=[{'ref': {'kind': 'knowledge_item', 'id': k['id']}},
                             {'ref': dict(subject)}])

    # ── choices and answers ──

    def choose(self, tx, *, actor, intent_id, choice):
        """The user's choice on a challenge: `proceed` applies the recorded
        reading as it was validated (no second model call), noting the
        conflict as an explicit constraint; `drop` declines it."""
        if choice not in ('proceed', 'drop'):
            raise ValueError('a challenge is answered proceed or drop')
        it = lifecycle.load(tx, entities.Intent, intent_id).entity
        if it.resolution != 'clarification_requested' or not it.conflicts:
            raise ValueError('intent %s is not waiting for a challenge choice' % intent_id)
        msg = lifecycle.load(tx, entities.Message, it.message_id).entity
        if choice == 'drop':
            it = _set(tx, actor, it, resolution='declined', reason='dropped after the '
                      'challenge')
            return _reply(tx, actor, msg, it, 'Dropped. Nothing was created.')
        noted = tuple({'text': 'proceeding although it goes against %s (%s)'
                               % (c['ref']['id'], c['why']),
                       'origin': 'explicit', 'source_ref': msg.id} for c in it.conflicts)
        return self._commit(tx, actor, msg, it, it.proposal, extra_constraints=noted)

    def date_meeting(self, tx, *, actor, message_id, meeting_id):
        """The user's reply to "when was it held?": its ISO date becomes the
        meeting's `held_at` (recorded by the reply's `message.created`)."""
        msg = _user(tx, message_id)
        mt = lifecycle.load(tx, entities.Meeting, meeting_id).entity
        it = _intent(tx, actor, msg, kind='control_verb', via='grammar',
                     target_refs=({'kind': 'meeting', 'id': meeting_id},), reason='held_at')
        d = _DATE.search(msg.text)
        if d is None or mt.held_at is not None:
            it = _set(tx, actor, it, resolution='declined')
            why = ('it already has a date (%s)' % mt.held_at if mt.held_at
                   else 'I found no date like 2026-09-20 in your reply')
            return _reply(tx, actor, msg, it, 'I did not date "%s": %s.' % (mt.name, why))
        held = '%s-%s-%s' % d.groups()
        tx.update(entities.Meeting, meeting_id, {'held_at': held}, actor=actor)
        it = _set(tx, actor, it, resolution='answered')
        return _reply(tx, actor, msg, it, 'Dated "%s": held %s.' % (mt.name, held),
                      links=[{'ref': {'kind': 'meeting', 'id': meeting_id}}])

    def follow_mission(self, tx, *, actor, mission_id, to):
        """An idea follows the mission it was promoted to (state-machines §1:
        `mission_completed` / `mission_cancelled` are event-driven)."""
        trigger = {'COMPLETED': 'mission_completed', 'CANCELLED': 'mission_cancelled'}[to]
        moved = []
        for r in tx.where(entities.Idea):
            if (r.entity.promoted_mission_id == mission_id
                    and r.entity.state == 'IMPLEMENTING'):
                lifecycle.fire(tx, entities.Idea, r.entity.id, trigger, actor=actor,
                               reason='its mission %s is %s' % (mission_id, to))
                moved.append(r.entity.id)
        return {'ideas': moved}


#: an idea's legal way to IMPLEMENTING, from where it is (state-machines §1)
PROMOTE_PATH = {'CAPTURED': ('clarify', 'plan', 'promote'), 'UNDERSTOOD': ('plan', 'promote'),
                'EXPLORED': ('validate', 'plan', 'promote'), 'VALIDATED': ('plan', 'promote'),
                'CONCEPT': ('plan', 'promote'), 'PLANNED': ('promote',),
                'SCHEDULED': ('promote',)}


def _end(tx, actor, called, **counts):
    C.end_call(tx, actor=actor, route_decision_id=called['route_decision_id'],
               outcome={'state': 'ok', 'attempts': called['attempts'],
                        'account_ref': called['account_ref'], **counts},
               usage=called['usage'] or None)


def _workspace(tx, project_id):
    if project_id is None:
        return ids.GLOBAL_WORKSPACE
    return lifecycle.load(tx, entities.Project, project_id).entity.workspace_id


def _items(items, msg):
    return [{'text': c['text'].strip(), 'origin': c['origin'], 'source_ref': msg.id}
            for c in items if c['text'].strip()]


def _inferred(m):
    inf = [c['text'] for c in m.requirements + m.constraints if c['origin'] == 'inferred']
    return '' if not inf else '; I inferred: %s' % '; '.join(inf)


def _mission(tx, actor, p, *, project, origin, origin_ref, msg, extra_constraints=()):
    if project is not None and tx.get(entities.Project, project) is None:
        raise lifecycle.NotFound(project)
    title = ' '.join((p.get('title') or '').split())[:120]
    objective = (p.get('objective') or '').strip()
    m = entities.Mission(id=ids.new_id('mission'), workspace_id=_workspace(tx, project),
                         project_id=project, title=title, objective=objective,
                         origin=origin, origin_ref=origin_ref,
                         desired_outcome=(p.get('desired_outcome') or '').strip(),
                         requirements=tuple(_items(p['requirements'], msg)),
                         constraints=tuple(_items(p['constraints'], msg))
                         + tuple(extra_constraints))
    tx.insert(m, actor=actor)
    tx.append(new_event('mission.created', Ref('mission', m.id), actor,
                        payload={'title': m.title, 'origin': origin, 'origin_ref': origin_ref},
                        workspace=m.workspace_id, project=project))
    return m


def _stale_target(tx, p):
    """What changed between the reading and now that makes it unsafe to apply:
    a mission that has since ended, an idea already promoted."""
    t = p['target']
    if t is None:
        return []
    if t['kind'] == 'mission':
        m = tx.get(entities.Mission, t['id']).entity
        if m.state in states.terminal('mission'):
            return ['Mission "%s" has ended (%s); should this be new work?' % (m.title, m.state)]
    if t['kind'] == 'idea' and p['kind'] == 'new_work':
        i = tx.get(entities.Idea, t['id']).entity
        if i.state not in PROMOTE_PATH:
            return ['Idea %s is %s and cannot be made into a mission again.' % (i.id, i.state)]
    return []


def _pending_clarification(tx, reply_to):
    r = tx.get(entities.Message, reply_to)
    if r is None:
        return None
    for c in r.entity.cards:
        if c['type'] in ('clarification', 'challenge') and c['ref']['kind'] == 'intent':
            return c['ref']['id']
    return None


def _status(tx, target):
    from ..world import status as world_status
    st = world_status.status(tx.conn, target['id'] if target else None)
    live = [m for m in st['missions'] if m['state'] not in states.terminal('mission')]
    text = '%d project(s), %d open mission(s)%s, %d drift finding(s).' % (
        len(st['projects']), len(live),
        '' if not live else ': ' + '; '.join('%s (%s)' % (m['title'], m['state'])
                                             for m in live[:10]),
        len(st['drift']))
    links = [{'ref': {'kind': 'mission', 'id': m['id']}} for m in live[:10]]
    return text, links


def _why(tx, target):
    got = [r.entity for r in tx.where(entities.RouteDecision)
           if r.entity.id == target['id']
           or (r.entity.source is not None and r.entity.source.id == target['id'])]
    if not got:
        return 'No resource was chosen for %s, so there is nothing to explain yet.' % (
            target['id'],)
    return got[-1].explanation


def _remember(tx, actor, text, msg):
    """`remember …` is the user's explicit statement (§3): a PREFERENCE with
    origin explicit that confirms itself, citing the message. Only the grammar
    makes one — a model's reading never does."""
    k = K.new_item(tx, actor=actor, workspace_id=ids.GLOBAL_WORKSPACE, type='PREFERENCE',
                   title=text[:200], origin='explicit', source_kind='user',
                   source_ref=Ref('message', msg.id))
    K.confirm(tx, actor=actor, knowledge_item_id=k.id, reason='stated by you (remember)')
    return 'Remembered: "%s" (%s).' % (k.title, k.id), k.id
