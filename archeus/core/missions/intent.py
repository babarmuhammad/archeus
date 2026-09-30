"""The intent worker (P7; plan §11, p7-design-gate §5): an outbox consumer
(`consumers.deliver`, at-least-once, handler outside any transaction) that
reads each user message once.

    user message.created
      -> a reply to "when was that meeting?"  -> date it          (no model)
      -> the control grammar resolves it     -> apply the verb    (no model)
      -> otherwise: record the message's ContextPackage (P5)
         -> archeus_call(purpose brain, intent.v1)   (ADR-0022 election, the
            ADR-0021 gate re-checked before the spawn, Core validation with
            one retry — P6's call path, unchanged)
         -> ok:  resolve the handles, apply in ONE command with the call's end
         -> not: the reply says why; nothing else is written
    mission.state_changed to COMPLETED / CANCELLED
      -> the idea it was promoted from follows it

"Once" is the database's: `intents.message_id` is unique, and a message that
already has an intent is skipped, so a re-delivered event (a crash between the
call and the consumer's effect) never reads a message twice or makes a second
mission. A Core that died mid-call leaves a RouteDecision with no outcome,
which the knowledge worker's boot sweep ends `failed`; the message is then read
again when its event is re-delivered.

A message is read against what was learned BEFORE it: with `after` set (the
Core runtime names the knowledge consumer), reading waits until that consumer
has handled every earlier event — so notes imported and then asked about are
known when the question is read — for at most LEARNED_WAIT_S, after which it
reads with what there is. The in-process judge binding pumps the knowledge
worker first, which gives the same order without a wait.
"""

import logging
import time

from ...infra import paths
from ...infra.db import rows
from ...infra.eventlog import consumers, outbox
from ..application import calls as C
from ..application import commands, grammar
from ..brain import intent as brain
from ..domain import entities, ids

log = logging.getLogger('archeus.core')

CONSUMER = 'intent'
#: the longest a message waits for the knowledge learned before it
LEARNED_WAIT_S = 300.0


class Intents:
    """Reads messages for one Core: `calls` is its `OwnCalls`, `conversations`
    its `application.conversation.Conversations`."""

    def __init__(self, db, *, actor, calls, conversations, after=None,
                 wait_s=LEARNED_WAIT_S):
        self.db, self.actor, self.calls, self.conv = db, actor, calls, conversations
        self.after, self.wait_s = after, wait_s
        self.on_wake = None
        self.stopping = lambda: False

    def _do(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.actor))

    def pending(self):
        with self.db.read() as conn:
            n = outbox.head(conn) - consumers.cursor(conn, CONSUMER)
        if n and self.on_wake is not None:
            self.on_wake()
        return n

    def sweep(self):
        return []           # open calls are the knowledge worker's boot sweep (P6)

    def pass_once(self):
        return {'changed': consumers.deliver(self.db, CONSUMER, self._handle) > 0}

    def _handle(self, e):
        try:
            if e.type == 'message.created' and e.payload.get('author') == 'user':
                self._learned(e.seq)
                return self.read(e.subject.id)
            to = (e.payload or {}).get('to')
            if e.type == 'mission.state_changed' and to in ('COMPLETED', 'CANCELLED'):
                return 'ideas:%s' % self._do(self.conv.follow_mission,
                                             mission_id=e.subject.id, to=to)['ideas']
            return ''
        except Exception as x:          # this event's failure, never the worker's death
            log.exception('intent for event %d failed', e.seq)
            return 'error: %s: %s' % (type(x).__name__, x)

    def _learned(self, seq):
        if self.after is None:
            return
        deadline = time.monotonic() + self.wait_s
        while not self.stopping():
            seen = self.db.writer.commit_count
            with self.db.read() as conn:
                if consumers.cursor(conn, self.after) >= seq - 1:
                    return
            left = deadline - time.monotonic()
            if left <= 0:
                log.warning('message event %d is read before %s caught up', seq, self.after)
                return
            self.db.writer.wait_commit(seen, min(left, 1.0), until=self.stopping)

    def read(self, message_id):
        with self.db.read() as conn:
            msg = rows.get(conn, entities.Message, message_id).entity
            if rows.where(conn, entities.Intent, message_id=message_id):
                return 'already read'
            ask = _asked(conn, msg.in_reply_to)
            control = None if ask else grammar.resolve(conn, msg.text)
        if ask and ask['kind'] == 'meeting':
            return 'dated:%s' % self._do(self.conv.date_meeting, message_id=message_id,
                                         meeting_id=ask['id'])['resolution']
        if control is not None:
            return 'grammar:%s' % self._do(self.conv.apply_control, message_id=message_id,
                                           verb=control.verb, target=control.target,
                                           arg=control.arg)['resolution']
        return 'brain:%s' % self._brain(msg, ask)

    def _brain(self, msg, ask):
        pkg = self._do(commands.record_context_package, subject_kind='message',
                       subject_id=msg.id)
        with self.db.read() as conn:
            lines, facts = brain.describe(conn, pkg)
            answering = None
            if ask:
                q = rows.get(conn, entities.Message, msg.in_reply_to).entity
                answering = q.text
        c = self.calls.run(purpose='brain', source={'kind': 'message', 'id': msg.id},
                           workspace_id=ids.GLOBAL_WORKSPACE, project_id=None,
                           prompt=brain.prompt(msg.text, lines, answering),
                           schema=brain.SCHEMA, check=lambda p: brain.check(p, facts),
                           workdir=paths.archeus_home(), context_package_id=pkg['id'])
        if c.state != 'ok':
            return self._do(self.conv.decline, message_id=msg.id,
                            route_decision_id=c.route_decision_id, state=c.state,
                            detail=c.detail)['resolution']
        called = {'route_decision_id': c.route_decision_id, 'attempts': c.attempts,
                  'account_ref': c.account_ref, 'usage': c.usage,
                  'context_package_id': pkg['id']}
        try:
            return self._do(self.conv.apply_intent, message_id=msg.id,
                            proposal=brain.resolve(c.parsed, facts),
                            called=called)['resolution']
        except Exception as e:
            # nothing it wrote survives (one transaction); the call still ends
            self._do(C.end_call, route_decision_id=c.route_decision_id,
                     outcome={'state': 'failed', 'reason': 'could not apply the reading: '
                              '%s: %s' % (type(e).__name__, e), 'attempts': c.attempts,
                              'account_ref': c.account_ref}, usage=c.usage or None)
            raise


def _asked(conn, reply_to):
    """What the Archeus message being replied to asked about: the ref of its
    clarification or challenge card, or None."""
    if reply_to is None:
        return None
    r = rows.get(conn, entities.Message, reply_to)
    if r is None or r.entity.author != 'archeus':
        return None
    for c in r.entity.cards:
        if c['type'] in ('clarification', 'challenge'):
            return c['ref']
    return None
