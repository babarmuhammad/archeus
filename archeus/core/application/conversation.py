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
from ..domain.words import LABELS
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


def thread(tx, actor, mission_id):
    """A mission's own conversation (ADR-0015; P19 S1), made on first use. The
    one writer makes it, so a mission has at most one."""
    lifecycle.load(tx, entities.Mission, mission_id)
    got = tx.where(entities.Conversation, mission_id=mission_id)
    if got:
        return got[0].entity.id
    c = entities.Conversation(id=ids.new_id('conversation'), kind='mission',
                              mission_id=mission_id)
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
    worker); this only records it (api-and-realtime §2). A mission's id names
    its thread (P19 S1)."""
    if not (isinstance(text, str) and text.strip()):
        raise ValueError('a message has text')
    if conversation_id is None or conversation_id == 'primary':
        conversation_id = primary(tx, actor)
    elif ids.kind_of(conversation_id) == 'mission':
        conversation_id = thread(tx, actor, conversation_id)
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


def approval_card(tx, actor, approval, mission):
    """An approval asked for, said where the user talks to Archeus (P19 S3): a
    card naming the live approval, linked to its mission, so the mission's
    thread shows it as well. The card holds the ref only; a client reads the
    approval's hash and version from the approval itself."""
    scope = (approval.presented or {}).get('scope') or approval.kind
    _message(tx, actor, conversation_id=primary(tx, actor), author='archeus',
             text='"%s" needs your approval: %s.' % (mission.title, scope),
             cards=[_card('approval', 'approval', approval.id)],
             links=[{'ref': {'kind': 'mission', 'id': mission.id}},
                    {'ref': {'kind': 'approval', 'id': approval.id}}])


def decide_by_message(tx, *, actor, decide, text, conversation_id, approval_id, action_hash,
                      expected_version=None, step_up=None):
    """`approve` / `reject` sent with the card the user is looking at (P19 S3):
    the turn, its reading and the card's decision in one transaction, by the
    poster's principal — the same decision `/decide` makes (G1)."""
    from .grammar import parse
    p = parse(text)
    if p is None or p.verb not in ('approve', 'reject'):
        raise ValueError('a message carrying a decision says approve or reject')
    posted = post_message(tx, actor=actor, text=text, conversation_id=conversation_id)
    msg = tx.get(entities.Message, posted['message_id']).entity
    it = _intent(tx, actor, msg, kind='control_verb', via='grammar',
                 target_refs=({'kind': 'approval', 'id': approval_id},), reason=p.verb)
    out = decide(tx, actor=actor, approval_id=approval_id, decision=p.verb,
                 action_hash=action_hash, step_up=step_up, expected_version=expected_version)
    a = lifecycle.load(tx, entities.Approval, approval_id).entity
    m = lifecycle.load(tx, entities.Mission, a.mission_id).entity
    if out.get('denied'):
        words = 'The policy denies it now, so nothing was approved for "%s".' % m.title
    else:
        words = '%s for "%s".' % ('Approved' if p.verb == 'approve' else 'Rejected', m.title)
    it = _set(tx, actor, it, resolution='mission_updated' if out.get('changed', True)
              else 'answered')
    r = _reply(tx, actor, msg, it, words, cards=[_card('approval', 'approval', approval_id)],
               links=[{'ref': {'kind': 'mission', 'id': m.id}},
                      {'ref': {'kind': 'approval', 'id': approval_id}}])
    return dict(r, message_id=msg.id, conversation_id=posted['conversation_id'], decided=out)


def _pending_approvals(tx, mission_id=None):
    return [r.entity for r in tx.where(entities.Approval) if r.entity.state == 'PENDING'
            and (mission_id is None or r.entity.mission_id == mission_id)]


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

    def __init__(self, *, missions, harnesses=lambda: ()):
        self.missions = missions
        # the execution harness ids a directive may name (the adapter registry's)
        self.harnesses = harnesses

    # ── the deterministic grammar ──

    def apply_control(self, tx, *, actor, message_id, verb, target=None, arg=''):
        """A control verb the grammar recognised and resolved (no model call)."""
        msg = _user(tx, message_id)
        it = _intent(tx, actor, msg, kind='control_verb', via='grammar',
                     target_refs=(target,) if target else (), reason=verb)
        cards, links, resolution = [], [], 'answered'
        if target:
            links.append(_link(target))
        if verb in ('approve', 'reject'):
            # a bare word binds to no card: it never guesses which approval (S3)
            conv = tx.get(entities.Conversation, msg.conversation_id).entity
            pending = _pending_approvals(tx, conv.mission_id)
            for a in pending[:10]:
                cards.append(_card('approval', 'approval', a.id))
                links.append({'ref': {'kind': 'approval', 'id': a.id}})
            resolution = 'declined'
            text = ('Nothing is waiting for your approval.' if not pending else
                    'To %s, use %s card: it decides exactly the action it shows.'
                    % (verb, 'its' if len(pending) == 1 else 'the approval\'s'))
        elif verb in ('pause', 'resume', 'cancel'):
            text, resolution = self._mission_verb(tx, actor, verb, target['id'], msg)
            cards.append(_card('mission', 'mission', target['id']))
        elif verb in ('use', 'dont_use'):
            ref = [arg['resource']]
            text, resolution, more, also = directive(
                tx, actor, msg, it, target['id'], prefer=ref if verb == 'use' else (),
                forbid=ref if verb == 'dont_use' else (), scope=arg['scope'])
            cards += more
            links += also
        elif verb == 'estop':
            # asked, never done from the words: the card runs the strip's command
            text = ('An emergency stop kills every running execution now and refuses new work '
                    'until a device re-arms it; missions wait, nothing is lost. Confirm it on '
                    'the card.')
            cards.append(_card('estop', 'workspace', ids.GLOBAL_WORKSPACE))
        elif verb == 'stop_running':
            m = lifecycle.load(tx, entities.Mission, target['id']).entity
            text = ('Stopping "%s" pauses it, then cancels it; a cancelled mission does not '
                    'come back. Confirm it on the card.' % m.title)
            cards.append(_card('stop', 'mission', m.id))
        elif verb in ('pause_all', 'resume_all'):
            text, resolution, moved = self._all_verb(tx, actor, verb, msg)
            for mid in moved:
                cards.append(_card('mission', 'mission', mid))
                links.append({'ref': {'kind': 'mission', 'id': mid}})
        elif verb == 'reprioritise':
            text, resolution = self._reprioritise(tx, actor, target['id'], arg, msg)
            cards.append(_card('mission', 'mission', target['id']))
        elif verb == 'status':
            text, more = _status(tx, target)
            links += more
            cards.append(_card('status', target['kind'] if target else 'workspace',
                               target['id'] if target else ids.GLOBAL_WORKSPACE))
        elif verb == 'why':
            text, rd = _why(tx, target, bare=not arg)
            if not arg:
                cards.append(_card('mission', 'mission', target['id']))
            elif rd is not None:              # the card is the record (G5); the text its words
                cards.append(_card('route_explanation', 'route_decision', rd))
                links.append({'ref': {'kind': 'route_decision', 'id': rd}})
        else:                                               # remember
            text, k = _remember(tx, actor, arg, msg)
            cards.append(_card('knowledge', 'knowledge_item', k))
            links.append({'ref': {'kind': 'knowledge_item', 'id': k}})
        it = _set(tx, actor, it, resolution=resolution)
        return _reply(tx, actor, msg, it, text, cards, links)

    def confirm_by_message(self, tx, *, actor, text, conversation_id, message_id):
        """Confirm on a `stop` card (P19 B10, C-33): the turn, its reading and
        the stop — pause if it runs, then cancel — in one transaction, by the
        poster's principal. The mission is the card's, never the words'; a
        mission that can no longer be cancelled writes nothing."""
        from .grammar import parse
        p = parse(text)
        if p is None or p.verb != 'stop':
            raise ValueError('a message confirming a stop card says stop')
        row = tx.get(entities.Message, message_id)
        stop = [c for c in (row.entity.cards if row else ()) if c['type'] == 'stop']
        if row is None or row.entity.author != 'archeus' or not stop:
            raise ValueError('confirm names an Archeus message carrying a stop card')
        mid = stop[0]['ref']['id']
        posted = post_message(tx, actor=actor, text=text, conversation_id=conversation_id)
        msg = tx.get(entities.Message, posted['message_id']).entity
        it = _intent(tx, actor, msg, kind='control_verb', via='grammar',
                     target_refs=({'kind': 'mission', 'id': mid},), reason='stop')
        m = lifecycle.load(tx, entities.Mission, mid).entity
        why = 'stop: confirmed in message %s' % msg.id
        if m.state == 'EXECUTING':
            self.missions.pause(tx, actor=actor, mission_id=mid, reason=why)
        self.missions.cancel(tx, actor=actor, mission_id=mid, reason=why)
        it = _set(tx, actor, it, resolution='mission_updated')
        r = _reply(tx, actor, msg, it, 'Stopped "%s": %s -> CANCELLED.' % (m.title, m.state),
                   cards=[_card('mission', 'mission', mid)],
                   links=[{'ref': {'kind': 'mission', 'id': mid}}])
        return dict(r, message_id=msg.id, conversation_id=posted['conversation_id'])

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

    def _all_verb(self, tx, actor, verb, msg):
        """`pause all` / `resume all`: the same commands as the controls."""
        out = getattr(self.missions, verb)(tx, actor=actor,
                                           reason='%s: asked in message %s' % (
                                               verb.replace('_', ' '), msg.id))
        moved = [m['id'] for m in out['missions']]
        if verb == 'pause_all':
            text = ('Paused %d running mission(s); "resume all" resumes exactly these.'
                    % len(moved) if moved else 'Nothing is running: nothing was paused.')
        else:
            text = ('Resumed %d mission(s) the last Pause all paused.' % len(moved) if moved
                    else 'Nothing the last Pause all paused is still paused.')
        return text, 'mission_updated' if out['changed'] else 'answered', moved

    def _reprioritise(self, tx, actor, mission_id, arg, msg):
        m = lifecycle.load(tx, entities.Mission, mission_id).entity
        if not arg:
            return ('Say the new priority for "%s" as a number, higher first (now %d): '
                    '"reprioritise %s to 5".' % (m.title, m.priority, m.title), 'declined')
        try:
            out = self.missions.reprioritise(tx, actor=actor, mission_id=mission_id,
                                             priority=int(arg))
        except lifecycle.IllegalTrigger as e:
            return 'I cannot reprioritise "%s": %s.' % (m.title, e), 'declined'
        if not out['changed']:
            return '"%s" already has priority %d.' % (m.title, m.priority), 'answered'
        return ('Priority of "%s": %d -> %d (dispatch order only).'
                % (m.title, m.priority, int(arg)), 'mission_updated')

    # ── the brain's reading ──

    def decline(self, tx, *, actor, message_id, route_decision_id, state, detail=''):
        """The brain could not read the message (gated, no harness, invalid
        output twice, …). The call already ended; the reply says why, and
        nothing else is written (ADR-0006: then the user is asked)."""
        msg = _user(tx, message_id)
        it = _intent(tx, actor, msg, kind='question', route_decision_id=route_decision_id,
                     resolution='declined', reason='%s: %s' % (state, detail))
        why = {'gated': 'no harness is permitted to make the call yet (provider terms: '
                        '`archeus terms <harness> permit`)',
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
        d, unnamed = resolve_directive(tx, p.get('resource_directive'), self.harnesses())
        if unresolved or material or stale or unnamed:
            return self._clarify(tx, actor, msg, it, unresolved, material, stale + unnamed)
        if d is not None and (d['scope'] == 'standing'
                              or kind not in ('new_work', 'continue_work')):
            return self._directive_alone(tx, actor, msg, it, d)
        if kind in ('new_work', 'continue_work') and p['conflicts']:
            return self._challenge(tx, actor, msg, it, p)
        return self._commit(tx, actor, msg, it, p)

    def _commit(self, tx, actor, msg, it, p, extra_constraints=()):
        kind = p['kind']
        if kind in ('new_work', 'continue_work'):
            # a directive applies to the mission the request creates or continues
            d = resolve_directive(tx, p.get('resource_directive'), self.harnesses())[0]
            then = None if d is None else (lambda mid, it: directive(
                tx, actor, msg, it, mid, prefer=d['prefer'], forbid=d['forbid'],
                scope=d['scope']))
            return (self._new_work if kind == 'new_work' else self._continue)(
                tx, actor, msg, it, p, extra_constraints, then)
        if kind == 'idea':
            return self._idea(tx, actor, msg, it, p)
        return self._feedback(tx, actor, msg, it, p)

    def _directive_alone(self, tx, actor, msg, it, d):
        """A directive with no request around it: standing, or for the mission
        whose thread it was said in; with neither, which mission is asked."""
        conv = tx.get(entities.Conversation, msg.conversation_id).entity
        if d['scope'] != 'standing' and conv.mission_id is None:
            q = 'Which mission should this apply to? Say "%s ... for <mission>".' % (
                'don\'t use' if d['forbid'] else 'use')
            return self._clarify(tx, actor, msg, it, [], [], [q])
        text, resolution, cards, links = directive(
            tx, actor, msg, it, conv.mission_id, prefer=d['prefer'], forbid=d['forbid'],
            scope=d['scope'])
        it = _set(tx, actor, it, resolution=resolution)
        return _reply(tx, actor, msg, it, text, cards, links)

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

    def _new_work(self, tx, actor, msg, it, p, extra_constraints, then=None):
        target = p['target']
        if target is not None:                             # an idea made into work
            return self._promote(tx, actor, msg, it, p, target['id'], extra_constraints, then)
        project = None if p['project'] is None else p['project']['id']
        m = _mission(tx, actor, p, project=project, origin='conversation', origin_ref=msg.id,
                     msg=msg, extra_constraints=extra_constraints)
        it = _set(tx, actor, it, resolution='mission_created')
        links = [{'ref': {'kind': 'mission', 'id': m.id}}]
        if project:
            links.append({'ref': {'kind': 'project', 'id': project}})
        return _reply(tx, actor, msg, it, *_with(then, m.id, it, (
            'I have taken this on as a mission: "%s" (%s)%s.' % (m.title, m.id, _inferred(m)),
            [_card('mission_proposal', 'mission', m.id)], links)))

    def _promote(self, tx, actor, msg, it, p, idea_id, extra_constraints, then=None):
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
        return _reply(tx, actor, msg, it, *_with(then, m.id, it, (
            'Idea %s is now mission "%s" (%s)%s.' % (idea.id, m.title, m.id, _inferred(m)),
            [_card('mission_proposal', 'mission', m.id), _card('idea', 'idea', idea.id)],
            [{'ref': {'kind': 'mission', 'id': m.id}}, {'ref': {'kind': 'idea', 'id': idea.id}}])))

    def _continue(self, tx, actor, msg, it, p, extra_constraints, then=None):
        mid = p['target']['id']
        row = lifecycle.load(tx, entities.Mission, mid)
        m = row.entity
        req = _items(p['requirements'], msg)
        con = _items(p['constraints'], msg) + list(extra_constraints)
        if not (req or con):
            if then is not None:            # the directive is what it asks
                text, resolution, cards, links = then(mid, it)
                it = _set(tx, actor, it, resolution=resolution)
                return _reply(tx, actor, msg, it, text, cards, links)
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
        return _reply(tx, actor, msg, it, *_with(then, mid, it, (
            'Added to mission "%s" (%s): %s.' % (m.title, mid,
                                                 '; '.join(c['text'] for c in req + con)),
            [_card('mission', 'mission', mid)], [{'ref': {'kind': 'mission', 'id': mid}}])))

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


# ── resource directives (ADR-0042 §2-§4, H2; P19 B10: accounts and harnesses) ──

#: the account classes a preference cannot reach without a confirmation
PROTECTED = ('last_resort', 'explicit_only')


def resolve_directive(tx, d, harnesses=()):
    """(the brain's `resource_directive` with every name resolved to one
    `{kind, id}`, the questions for names that resolve to none or several)."""
    from .grammar import resource
    if not d:
        return None, []
    out, asked = {'scope': d['scope'], 'prefer': [], 'forbid': []}, []
    for side in ('prefer', 'forbid'):
        for kind in ('account', 'harness'):
            for name in (d.get(side) or {}).get(kind + 's') or ():
                ref = resource(tx.conn, name, (kind,), harnesses)
                if ref is None:
                    asked.append('I do not know exactly one %s called "%s". Which one do you '
                                 'mean?' % (kind, name))
                else:
                    out[side].append(ref)
    return out, asked


def _consumption(tx, ref):
    if ref['kind'] != 'account':
        return None
    got = tx.where(entities.ResourcePolicy, account_id=ref['id'])
    return got[0].entity.consumption if got else None


def _name(tx, ref):
    if ref['kind'] == 'account':
        return 'account "%s"' % lifecycle.load(tx, entities.Account, ref['id']).entity.label
    return 'harness %s' % ref['id']


def directive(tx, actor, msg, intent, mission_id, *, prefer=(), forbid=(), scope='mission'):
    """A directive from the user's own message (ADR-0042 §3): narrowing and
    preference apply to the mission now, recorded with the message and intent
    they came from; widening (a protected account, or lifting a forbid) and
    standing changes are proposed on a `change` card that runs the existing
    `admin` route when a user device confirms it. Nothing here removes an
    elimination. (text, resolution, cards, links)."""
    p = tx.get(entities.Principal, msg.principal_id) if msg.principal_id else None
    if p is None or p.entity.kind != 'user_device':
        return ('Only a message from your own device can change what work may use; nothing '
                'was changed.', 'declined', [], [])
    cards, said = [], []
    if scope == 'standing':
        for ref in forbid:
            if ref['kind'] == 'account':
                cards.append(_standing_card(tx, ref))
            else:
                said.append('A standing rule for %s cannot be set from the conversation; '
                            'forbid it per mission instead.' % _name(tx, ref))
        for ref in prefer:
            said.append('A standing preference for %s cannot be set from the conversation; '
                        'prefer it per mission instead.' % _name(tx, ref))
        if cards:
            said.insert(0, 'Confirm on the card to make this standing.')
        return ' '.join(said), 'answered', cards, []
    m = lifecycle.load(tx, entities.Mission, mission_id).entity
    if m.state in states.terminal('mission'):
        return ('"%s" has ended (%s); nothing was changed.' % (m.title, m.state),
                'declined', [], [])
    rp = dict(m.resource_preferences or {})
    lists = {k: list(rp.get(k) or ()) for k in entities.RESOURCE_PREFERENCE_KEYS[:4]}
    applied, widen = [], []
    for ref in forbid:                                   # narrowing: always, at once
        fk, pk = 'forbidden_%ss' % ref['kind'], 'preferred_%ss' % ref['kind']
        if ref['id'] in lists[pk]:
            lists[pk].remove(ref['id'])
        if ref['id'] not in lists[fk]:
            lists[fk].append(ref['id'])
            applied.append((fk, ref))
            said.append('no longer using %s' % _name(tx, ref))
    for ref in prefer:
        fk, pk = 'forbidden_%ss' % ref['kind'], 'preferred_%ss' % ref['kind']
        if ref['id'] in lists[fk] or _consumption(tx, ref) in PROTECTED:
            widen.append(ref)                            # widening: proposed only
        elif ref['id'] not in lists[pk]:
            lists[pk].append(ref['id'])
            applied.append((pk, ref))
            said.append('preferring %s' % _name(tx, ref))
    since = rp.get('since')
    if applied:
        kept = [d for d in rp.get('directives') or () if d['id'] in lists[d['key']]]
        prefs = dict(rp, **lists, since=tx.now, directives=kept + [
            {'key': k, 'id': r['id'], 'message_id': msg.id, 'intent_id': intent.id}
            for k, r in applied])
        entities.Mission(**dict(m.to_dict(), resource_preferences=prefs))      # validate
        tx.update(entities.Mission, m.id, {'resource_preferences': prefs}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', m.id), actor, payload={
            'fields': ['resource_preferences'], 'resource_preferences': prefs,
            'message_id': msg.id, 'intent_id': intent.id},
            workspace=m.workspace_id, project=m.project_id))
        since, rp = tx.now, prefs
    text = ('For "%s": %s.' % (m.title, '; '.join(said))) if said else (
        'For "%s": nothing new to apply.' % m.title if not widen else '')
    if applied and scope == 'task':
        text += ' Until task-level preferences exist this applies to the whole mission.'
    for ref in widen:
        lists2 = {k: list(v) for k, v in lists.items()}
        fk, pk = 'forbidden_%ss' % ref['kind'], 'preferred_%ss' % ref['kind']
        if ref['id'] in lists2[fk]:
            lists2[fk].remove(ref['id'])
        lists2[pk].append(ref['id'])
        why = ('it is forbidden for this mission' if ref['id'] in lists[fk] else
               'it is used only %s' % ('when nothing else can run' if _consumption(tx, ref) ==
                                        'last_resort' else 'when you name it'))
        says = 'Use %s for "%s": %s, so this widens what it may use.' % (_name(tx, ref), m.title,
                                                                         why)
        body = dict(lists2)
        if rp.get('max_cost_band'):
            body['max_cost_band'] = rp['max_cost_band']
        cards.append(dict(_card('change', 'mission', m.id), scope='mission', says=says,
                          command={'name': 'setMissionResources', 'id': m.id, 'body': body},
                          based_on=since))
        text = (text + ' ' if text else '') + says + ' Confirm it on the card.'
    if scope == 'ambiguous':                 # read as the mission's; offered as standing
        for ref in forbid:
            if ref['kind'] == 'account':
                cards.append(_standing_card(tx, ref))
                text += ' To make it standing, confirm it on the card.'
    if applied:
        cards.insert(0, _card('mission', 'mission', m.id))
    return (text.strip(), 'mission_updated' if applied else 'answered', cards,
            [{'ref': {'kind': 'mission', 'id': m.id}}])


def _standing_card(tx, ref):
    """"Never use account A": its consumption becomes `explicit_only`, through
    the resource policy route (`admin`) when a user device confirms it."""
    return dict(_card('change', 'account', ref['id']), scope='standing',
                says='Never use %s unless you name it: its consumption becomes explicit_only.'
                     % _name(tx, ref),
                command={'name': 'setResourcePolicy', 'id': ref['id'],
                         'body': {'consumption': 'explicit_only'}},
                based_on=None)


def _with(then, mission_id, intent, reply):
    """(text, cards, links) of a reply, with its directive's outcome appended."""
    text, cards, links = reply
    if then is None:
        return text, cards, links
    more, _resolution, extra, also = then(mission_id, intent)
    return ((text + ' ' + more).strip(), list(cards) + [c for c in extra if c not in cards],
            list(links) + list(also))


def _running(w):
    """One item of live work, in words (R13-06)."""
    if w['kind'] == 'own_call':
        return 'an own call for the %s (%s)' % (w['purpose'].replace('_', ' '),
                                                 w['account_id'] or w['harness_id'] or 'no account')
    return '%s attempt %d (%s, context %s%s)' % (
        w['task_key'], w['attempt'], _said('execution', w['state']), w['context']['quality'],
        '' if w['context']['remaining'] is None
        else ', %s tokens left' % '{:,}'.format(w['context']['remaining']))


def _said(machine, state):
    # the generated copy of presentation.json's words (R13-06: "use the same words")
    return LABELS.get(machine, {}).get(state, state)


def _status(tx, target):
    from ..world import status as world_status
    st = world_status.status(tx.conn, target['id'] if target else None)
    live = [m for m in st['missions'] if m['state'] not in states.terminal('mission')]
    text = '%d project(s), %d open mission(s)%s, %d drift finding(s).' % (
        len(st['projects']), len(live),
        '' if not live else ': ' + '; '.join('%s (%s)' % (m['title'], _said('mission', m['state']))
                                             for m in live[:10]),
        len(st['drift']))
    links = [{'ref': {'kind': 'mission', 'id': m['id']}} for m in live[:10]]
    from .live import live_work
    work = live_work(tx.conn, target['id'] if target else None)
    if work:
        more = len(work) - 10
        text += ' Running now: %s%s.' % ('; '.join(_running(w) for w in work[:10]),
                                         ' (+%d more)' % more if more > 0 else '')
        links += [{'ref': {'kind': 'execution', 'id': w['id']}} for w in work[:10]
                  if w['kind'] == 'execution']
    return text, links


#: why a mission exists, from its origin (R13-05): said as a person would
_ORIGIN = {'conversation': 'you asked for it in a conversation',
           'idea': 'it was made from one of your ideas',
           'automation': 'one of your automations started it',
           'legacy_import': 'it was brought over from the earlier app'}


def _why(tx, target, bare=False):
    """(the words, the RouteDecision they explain or None). A bare `why` (only
    the thread's mission is its target) asks why the mission exists."""
    if bare:
        row = tx.get(entities.Mission, target['id'])
        if row is None:
            return 'There is no mission %s.' % target['id'], None
        m = row.entity
        return 'This mission exists because %s: "%s".' % (_ORIGIN[m.origin],
                                                         m.objective or m.title), None
    if target['kind'] == 'execution':
        from .live import explain
        row = tx.get(entities.Execution, target['id'])
        if row is None:
            return 'There is no execution %s.' % target['id'], None
        return explain(tx.conn, row.entity), row.entity.route_decision_id
    got = [r.entity for r in tx.where(entities.RouteDecision)
           if r.entity.id == target['id']
           or (r.entity.source is not None and r.entity.source.id == target['id'])]
    if not got:
        return 'No resource was chosen for %s, so there is nothing to explain yet.' % (
            target['id'],), None
    return got[-1].explanation, got[-1].id


def _remember(tx, actor, text, msg):
    """`remember …` is the user's explicit statement (§3): a PREFERENCE with
    origin explicit that confirms itself, citing the message. Only the grammar
    makes one — a model's reading never does."""
    k = K.new_item(tx, actor=actor, workspace_id=ids.GLOBAL_WORKSPACE, type='PREFERENCE',
                   title=text[:200], origin='explicit', source_kind='user',
                   source_ref=Ref('message', msg.id))
    K.confirm(tx, actor=actor, knowledge_item_id=k.id, reason='stated by you (remember)')
    return 'Remembered: "%s" (%s).' % (k.title, k.id), k.id
