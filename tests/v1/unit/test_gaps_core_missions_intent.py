"""T-734: the branches of the intent worker (`archeus/core/missions/intent.py`)
that no test in tests/v1 reached, as unit tests. Fail-closed and denial paths
first (an event whose message is gone, an Archeus turn read back as a user turn,
a card forged by a user, a reading that cannot be applied, a call that could not
run), then the boundary values (what the grammar may obey and what is the brain's,
what counts as an answer to a question, the one-read rule, the wait for what was
learned before a message), then the loop's own error paths (the worker surviving
a handler that failed, its wake, its boot sweep).

The rig is the one tests/v1/integration/test_intent.py built for this worker,
kept to what a unit test may hold (the style of
test_gaps_core_verification_worker.py): the real worker over a real database of
real rows, so the real grammar, the real `intent.v1` handles and validation and
the real conversation commands all still run, with a fake for the one thing the
worker asks out of the process: `OwnCalls.run`. An own call no test scripted
fails the test where it is made, so a worker that reached the model where it
must not (a control verb, a meeting date, a message already read) is caught here.

Platform-neutral: nothing here writes files, spawns a process, opens a socket,
reads the OS or sleeps — the worker's one wait (`Writer.wait_commit`) is recorded
in every test rather than slept, and no test waits on a clock.

Two findings are held as `xfail` rather than fixed here, both in what the worker
hands its answer to: an empty `Message.text` cannot be recorded as an `Intent`,
and `conversation.directive` pluralises a harness to `harnesss`.
"""

import logging

import pytest

from archeus.core import ports
from archeus.core.application import calls as C
from archeus.core.application import commands
from archeus.core.application.conversation import Conversations, post_message
from archeus.core.brain import intent as brain
from archeus.core.calls import Called
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.missions import intent as mi
from archeus.infra import paths
from archeus.infra.db import Database, rows
from archeus.infra.eventlog import consumers

#: a reading a model might answer with: work the user asked for
WORK = {'kind': 'new_work', 'title': 'Add a --version flag',
        'objective': 'The CLI prints the installed version.'}
#: and one that only answers: what the model says to a question
ASKED = {'kind': 'question', 'answer': [{'text': 'nothing is open yet', 'refs': []}]}
#: a control verb's words, so a test can tell the grammar's answer from the model's
CANCEL = 'cancel Ship it'


class _Calls:
    """`OwnCalls.run` as the worker sees it: every spec recorded, each answered
    from the script (a `Called`, or a callable of the spec), the last answer kept
    for any further call. An own call with nothing scripted fails the test where
    it is made — that the worker reached the model at all is the finding."""

    def __init__(self, *script, place=None):
        self.specs, self.left, self.answers, self.place = [], list(script), [], place

    def run(self, **spec):
        self.specs.append(spec)
        if not self.left:
            raise AssertionError('the worker made an own call no test scripted: %r'
                                 % (spec.get('source'),))
        got = self.left.pop(0) if len(self.left) > 1 else self.left[0]
        answer = got(spec) if callable(got) else got
        if answer.route_decision_id is None:
            # a call names the decision it was made under, as run() records one per call
            answer = answer._replace(route_decision_id=ids.new_id('route_decision'))
        if self.place is not None:
            self.place(answer)                # what run() did before it answered
        self.answers.append(answer)
        return answer

    @property
    def spec(self):
        assert len(self.specs) == 1, '%d own calls were made' % len(self.specs)
        return self.specs[0]

    @property
    def answer(self):
        assert len(self.answers) == 1, '%d own calls were made' % len(self.answers)
        return self.answers[0]


def reading(parsed, rd=None, usage=None, attempts=2, account_ref='harness:fake'):
    """What an own call answers with when the model answered. `rd` is the RouteDecision
    the call was made under, which the worker cites and never checks."""
    return Called(rd, 'ok', parsed, usage, '', attempts, account_ref)


def refused(state, detail, rd=None):
    """What an own call answers with when it did not run: the state it recorded and the
    reason it gave. The worker relays both to `decline` and writes nothing else."""
    return Called(rd, state, None, None, detail, 1, None)


class Rig:
    """One intent worker over a Core of real rows: the real outbox, cursors, effects,
    grammar and conversation commands, a fake for the model call and no sleeping.

    One of these per test: they all read the one `ARCHEUS_HOME`, so two would read
    one database and each other's rows."""

    #: a wait that never ends is a bug in the worker, not a test that must wait
    MAX_WAITS = 20

    def __init__(self, *, after=None, wait_s=mi.LEARNED_WAIT_S, script=(), harnesses=()):
        self.db = Database.open()
        self.system = Ref('system', ids.new_id('principal'))
        # a turn is read as a device's own only when its principal row says so (P2
        # bootstrap registers it, as the in-process client does)
        self.user = Ref('user_device', self.db.writer.execute(
            commands.register_principal,
            {'kind': 'user_device', 'scopes': ('observe', 'control', 'approve')})['id'])
        self.calls = _Calls(*script, place=self._recorded)
        self.conversations = Conversations(
            missions=commands.Missions(policy=ports.AllowAllPolicy()),
            harnesses=lambda: tuple(harnesses))
        self.worker = mi.Intents(self.db, actor=self.system, calls=self.calls,
                                 conversations=self.conversations, after=after,
                                 wait_s=wait_s)
        # what the worker asked out of the process, and what it waited for
        self.waits, self.on_wait, self.wakes = [], [], []
        self.db.writer.wait_commit = self._wait
        self.worker.on_wake = lambda: self.wakes.append(len(self.wakes))
        self._tid, self._todo, self._seq = None, [], {}

    # ── the writer's commit notification, recorded rather than slept ──

    def _wait(self, seen, timeout, until=None):
        assert len(self.waits) < self.MAX_WAITS, 'the worker never stopped waiting'
        self.waits.append({'seen': seen, 'timeout': timeout, 'until': until})
        action = self.on_wait.pop(0) if self.on_wait else None
        if action is not None:
            action()
        return self.db.writer.commit_count

    # ── placing the rows an earlier pass left behind ──

    def run(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.user))

    def put(self, *items, events, actor=None):
        """One writer command placing rows with the events that record them (a
        mutation without its event is rolled back). Returns the events' seqs."""
        items = tuple(self._todo) + tuple(items)
        self._todo = []
        placed = []

        def commit(tx, *, actor):
            for x in items:
                tx.insert(x, actor=actor)
            for e in events:
                placed.append(tx.append(e))
        self.db.writer.execute(commit, {'actor': actor or self.system})
        for p in placed:
            self._seq[(p.subject.kind, p.subject.id)] = p.seq
        return [p.seq for p in placed]

    def seq_of(self, cls, entity_id):
        return self._seq[(cls._ID, entity_id)]

    def thread(self):
        """The primary conversation every turn of this rig is said in, made on first
        use exactly as `post_message` makes it (and by the same command as its first
        message, which is what its foreign key needs)."""
        if self._tid is None:
            self._tid = ids.new_id('conversation')
            self._todo = [entities.Conversation(id=self._tid, kind='primary')]
        return self._tid

    def post(self, text, in_reply_to=None, into=None):
        """A user turn through the real command, the way a client posts one. `into` is
        a mission id, which names that mission's own thread (P19 S1)."""
        kw = {'text': text, 'in_reply_to': in_reply_to}
        if into is not None:
            kw['conversation_id'] = into
        elif self._tid is not None:
            kw['conversation_id'] = self._tid
        got = self.run(post_message, **kw)
        if self._tid is None:
            self._tid, self._todo = got['conversation_id'], []
        self._seq[('message', got['message_id'])] = got['seq']
        return got

    def turn(self, author, text, cards=(), links=(), in_reply_to=None, says=None):
        """A turn placed as an earlier pass left it, with its `message.created` event.
        `says` is what that event *says* the author was, which is all the worker's
        handler trusts; the row is what the reading is made against, so a turn whose
        row and event disagree is the hostile case."""
        m = entities.Message(id=ids.new_id('message'), conversation_id=self.thread(),
                             author=author, text=text, cards=tuple(cards),
                             links=tuple(links), in_reply_to=in_reply_to,
                             principal_id=(self.user if author == 'user' else self.system).id)
        who = self.user if author == 'user' else self.system
        self.put(m, actor=who, events=[new_event(
            'message.created', Ref('message', m.id), who,
            payload={'author': says or author, 'conversation_id': m.conversation_id,
                     'in_reply_to': in_reply_to, 'cards': [dict(c) for c in m.cards]})])
        return m

    def ask(self, text, ref, kind='clarification', **extra):
        """The Archeus turn that asked something, carrying the card the worker reads
        an answer against (`ask_meeting_date` and `_clarify` write exactly these)."""
        card = dict(extra, type=kind, ref=dict(ref))
        links = [{'ref': dict(ref)}] if ref.get('kind') == 'meeting' else []
        return self.turn('archeus', text, cards=[card], links=links)

    def mission(self, title='Ship it', state='CREATED', **fields):
        m = entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                             title=title, objective='The thing, shipped', state=state,
                             **fields)
        self.put(m, events=[new_event('mission.created', Ref('mission', m.id), self.system,
                                      payload={'title': title, 'origin': m.origin})])
        return m

    def idea(self, mission_id, state='IMPLEMENTING', text='An idea worth having'):
        i = entities.Idea(id=ids.new_id('idea'), workspace_id=ids.GLOBAL_WORKSPACE, text=text,
                         title=text, state=state, promoted_mission_id=mission_id)
        self.put(i, events=[new_event('idea.created', Ref('idea', i.id), self.system,
                                      payload={'title': text})])
        return i

    def meeting(self, name='Kickoff', held_at=None):
        m = entities.Meeting(id=ids.new_id('meeting'), workspace_id=ids.GLOBAL_WORKSPACE,
                             name=name, held_at=held_at)
        self.put(m, events=[new_event('meeting.imported', Ref('meeting', m.id), self.system,
                                      payload={'name': name})])
        return m

    def knowledge(self, title='We ship on Fridays', type='DECISION', state='CONFIRMED',
                  text='Weekly, after the review.'):
        k = entities.KnowledgeItem(id=ids.new_id('knowledge_item'),
                                   workspace_id=ids.GLOBAL_WORKSPACE, title=title, text=text,
                                   type=type, state=state, source_kind='import')
        self.put(k, events=[new_event('knowledge_item.created',
                                      Ref('knowledge_item', k.id), self.system,
                                      payload={'title': title, 'type': type})])
        return k

    def open_call(self):
        """A call recorded before it ran (ADR-0022's INTENT rule), which is how the
        worker finds it again when it dies with the call open: the RouteDecision is
        there and has no outcome."""
        rd = entities.RouteDecision(id=ids.new_id('route_decision'),
                                    subject=Ref('archeus_call', 'brain'), purpose='brain',
                                    decided_by='router', account_ref='harness:fake',
                                    workspace_id=ids.GLOBAL_WORKSPACE)
        self.put(rd, events=[new_event('route.decided', Ref('route_decision', rd.id),
                                       self.system,
                                       payload={'purpose': 'brain', 'selected': None,
                                                'result': None, 'source': None})])
        return rd.id

    # ── what the call itself did before it answered ──

    def _recorded(self, c):
        """`OwnCalls.run` commits the decision before the adapter runs, and a call that
        did not run has already ended by the time it answers (`state` is 'ok' or an
        outcome run() wrote). So the fake places that row and ends a refused call
        here: a worker that ends one of these twice meets 'already has its outcome'."""
        if self.one(entities.RouteDecision, c.route_decision_id) is None:
            self.put(entities.RouteDecision(
                id=c.route_decision_id, subject=Ref('archeus_call', 'brain'),
                purpose='brain', decided_by='router', account_ref=c.account_ref,
                workspace_id=ids.GLOBAL_WORKSPACE),
                events=[new_event('route.decided', Ref('route_decision', c.route_decision_id),
                                  self.system, payload={'purpose': 'brain',
                                                         'selected': None, 'result': None,
                                                         'source': None})])
        if c.state != 'ok':
            self.run(C.end_call, route_decision_id=c.route_decision_id,
                     outcome={'state': c.state, 'reason': c.detail, 'attempts': c.attempts,
                              'account_ref': c.account_ref}, usage=c.usage or None)

    # ── the consumer's own rows ──
    def cursor(self, name=mi.CONSUMER):
        with self.db.read() as conn:
            return consumers.cursor(conn, name)

    def set_cursor(self, name, seq):
        """A cursor as a crash, a repair or an earlier pass left it."""
        def commit(tx, *, actor):
            tx.execute('INSERT INTO consumer_cursors (name, last_seq, updated_at) '
                       'VALUES (?, ?, ?) ON CONFLICT (name) DO UPDATE SET '
                       'last_seq = excluded.last_seq, updated_at = excluded.updated_at',
                       (name, seq, tx.now))
        self.db.writer.execute(commit, {'actor': self.system})

    def forget(self, seq):
        """One event's effect row, gone: what a pruned effects table leaves, which is
        what makes a re-delivered event run its handler again."""
        def commit(tx, *, actor):
            tx.execute('DELETE FROM consumer_effects WHERE consumer = ? AND event_seq = ?',
                       (mi.CONSUMER, seq))
        self.db.writer.execute(commit, {'actor': self.system})

    def effect(self, seq):
        with self.db.read() as conn:
            r = conn.execute('SELECT result FROM consumer_effects WHERE consumer = ? '
                             'AND event_seq = ?', (mi.CONSUMER, seq)).fetchone()
        return None if r is None else r[0]

    # ── reading what the worker wrote ──

    def rows(self, cls, **eq):
        with self.db.read() as conn:
            return [r.entity for r in rows.where(conn, cls, **eq)]

    def one(self, cls, entity_id):
        with self.db.read() as conn:
            r = rows.get(conn, cls, entity_id)
        return None if r is None else r.entity

    def intent(self, message_id):
        got = self.rows(entities.Intent, message_id=message_id)
        assert len(got) <= 1, 'a message is read at most once'
        return got[0] if got else None

    def reply(self, message_id):
        got = [m for m in self.rows(entities.Message, in_reply_to=message_id)
               if m.author == 'archeus']
        assert len(got) <= 1, 'one answer to one turn'
        return got[0] if got else None

    def pass_once(self):
        return self.worker.pass_once()

    def settle(self, limit=12):
        for _ in range(limit):
            if not self.pass_once()['changed']:
                return
        raise AssertionError('the outbox did not settle in %d passes' % limit)


@pytest.fixture
def make():
    return lambda **kw: Rig(**kw)


# ── the event's failure, never the worker's death ────────────────────────────

def test_an_event_whose_message_is_gone_fails_that_event_alone(make):
    # _handle's `except`. The read raises inside the handler; the worker must answer
    # for that event, keep the cursor moving, and stay alive for the next one. Take
    # the `except` out and `pass_once` raises out of the consumer: the worker dies.
    r = make()
    m = r.mission(title='Ship it')
    dead = new_event('message.created', Ref('message', ids.new_id('message')), r.user,
                     payload={'author': 'user', 'conversation_id': None,
                               'in_reply_to': None, 'cards': []})
    (seq,) = r.put(events=[dead])                          # an event with no message
    posted = r.post(CANCEL)                                # and a real turn after it
    assert r.pass_once()['changed'] is True
    got = r.effect(seq)
    assert got.startswith('error: AttributeError:') and got != 'error: '
    assert r.effect(posted['seq']) == 'grammar:mission_updated'
    assert r.calls.specs == []                             # the model was never reached
    assert r.one(entities.Mission, m.id).state == 'CANCELLED'
    r.settle()                                       # the rest of the batch, worker alive
    assert r.pass_once()['changed'] is False
    assert r.reply(posted['message_id']).text.startswith('Cancelled "Ship it"')


def test_a_failing_handler_says_so_in_the_effects_table_and_in_the_log(make, caplog):
    # _handle's `except`: the result becomes the event's effect, and the exception is
    # logged. Drop the log and a Core whose every message fails looks healthy.
    r = make()
    dead = new_event('message.created', Ref('message', ids.new_id('message')), r.user,
                     payload={'author': 'user'})
    with caplog.at_level(logging.WARNING, logger='archeus.core'):
        (seq,) = r.put(events=[dead])
        assert r.pass_once()['changed'] is True
    assert r.effect(seq).startswith('error: AttributeError')
    assert 'intent for event %d failed' % seq in caplog.text


def test_what_archeus_said_is_never_read_back_as_a_turn(make):
    # _handle's `author == 'user'` guard, inverted: every reply the worker writes makes
    # a `message.created` event of its own, so reading one would have Archeus answer
    # itself forever and read its own words as requests.
    r = make()
    m = r.mission(title='Ship it')
    said = r.turn('archeus', 'Add a --version flag to the CLI')
    assert r.pass_once()['changed'] is True
    assert r.effect(r.seq_of(entities.Message, said.id)) == ''
    assert r.intent(said.id) is None and r.calls.specs == []
    assert r.one(entities.Mission, m.id).state == 'CREATED'


def test_a_mission_that_neither_finished_nor_stopped_carries_no_idea_with_it(make):
    # _handle's `to in ('COMPLETED', 'CANCELLED')`: a PAUSED mission drags nothing, and
    # an event with no `to` in its payload is not a finish either. Invert it and an
    # idea is pulled out of IMPLEMENTING by a pause.
    r = make()
    m = r.mission(state='EXECUTING')
    i = r.idea(m.id)
    for payload in ({'from': 'EXECUTING', 'to': 'PAUSED'}, {}, None):
        (seq,) = r.put(events=[new_event('mission.state_changed', Ref('mission', m.id),
                                         r.system, payload=payload or {})])
        assert r.pass_once()['changed'] is True
        assert r.effect(seq) == ''
        assert r.one(entities.Idea, i.id).state == 'IMPLEMENTING'
    # and the two that do move an idea still do
    (seq,) = r.put(events=[new_event('mission.state_changed', Ref('mission', m.id),
                                     r.system, payload={'from': 'EXECUTING',
                                                        'to': 'CANCELLED'})])
    assert r.pass_once()['changed'] is True
    assert r.effect(seq).startswith('ideas:') and i.id in r.effect(seq)
    assert r.one(entities.Idea, i.id).state == 'PLANNED'


# ── a reading that cannot be applied; a call that could not run ─────────────

def test_a_reading_that_cannot_be_applied_ends_its_call_and_is_never_left_open(make):
    # _brain's `except`: the apply raised after the call was made, so the RouteDecision
    # must still end `failed` with the reason, the usage it reported must still be
    # ledgered, nothing it wrote may survive, and the failure must surface. Delete the
    # end_call and the call hangs open with no outcome; delete the `raise` and the
    # message is answered by silence and never read again.
    r = make()
    rd = r.open_call()
    usage = {'tokens_in': 11, 'tokens_out': 3, 'cache_read': 0, 'cache_write': 0,
             'cost_usd': 0.002}
    # a reading citing a handle this message's package never gave the model
    r.calls.left = [reading({'kind': 'question',
                             'answer': [{'text': 'a', 'refs': ['k7']}]}, rd=rd, usage=usage)]
    posted = r.post('what do we hold about releases?')
    assert r.pass_once()['changed'] is True
    assert r.effect(posted['seq']).startswith('error: KeyError:')
    got = r.one(entities.RouteDecision, rd)
    assert got.outcome['state'] == 'failed'
    assert got.outcome['reason'].startswith('could not apply the reading: KeyError')
    assert (got.outcome['attempts'], got.outcome['account_ref']) == (2, 'harness:fake')
    assert r.intent(posted['message_id']) is None          # nothing it wrote survives
    assert r.reply(posted['message_id']) is None           # and the user was not answered
    led = r.rows(entities.UsageLedger)
    assert [u.basis for u in led] == ['partial'] and led[0].tokens_in == 11
    assert [m.id for m in r.rows(entities.Message)] == [posted['message_id']]  # nothing added


def test_what_the_event_calls_a_user_turn_the_row_may_still_refuse(make):
    # The same branch, reached the hostile way: the handler reads the author off the
    # event, and `apply_intent` reads it off the row. The row wins: the call ends
    # `failed` with what the row says, and no answer of the worker's is written.
    r = make()
    rd = r.open_call()
    r.calls.left = [reading(WORK, rd=rd)]
    forged = r.turn('archeus', 'Add a --version flag to the CLI', says='user')
    assert r.pass_once()['changed'] is True
    assert r.effect(r.seq_of(entities.Message, forged.id)) == \
        'error: ValueError: only a user turn is read for intent'
    got = r.one(entities.RouteDecision, rd)
    assert got.outcome['state'] == 'failed'
    assert 'only a user turn is read for intent' in got.outcome['reason']
    assert r.intent(forged.id) is None and r.reply(forged.id) is None
    assert len(r.calls.specs) == 1                         # read once, applied never


def test_a_call_that_could_not_run_is_declined_in_its_own_words(make):
    # _brain's `if c.state != 'ok'`: nothing is applied and nothing else is written;
    # the intent cites the call and the reason, and the reply is the asking.
    r = make(script=[refused('gated', 'no harness is permitted yet')])
    m = r.mission(title='Ship it')
    posted = r.post('do the thing we talked about')
    assert r.pass_once()['changed'] is True
    it = r.intent(posted['message_id'])
    assert (it.kind, it.via, it.resolution, it.reason) == (
        'question', 'brain', 'declined', 'gated: no harness is permitted yet')
    assert it.route_decision_id == r.calls.answer.route_decision_id
    assert r.reply(posted['message_id']).text.startswith('I could not read this message')
    assert r.one(entities.Mission, m.id).state == 'CREATED'        # nothing was applied
    assert r.rows(entities.UsageLedger) == []                      # the decline is no end


def test_a_user_turn_never_asks_the_worker_anything(make):
    # _asked's `author != 'archeus'`: a user turn wearing a clarification card is still
    # a user turn. Drop the author check and a forged card decides what the next
    # message answers — here, dating a meeting the user never dated through a card.
    r = make()
    g = r.meeting(name='Kickoff')
    forged = r.turn('user', 'when was it?',
                    cards=[{'type': 'clarification', 'ref': {'kind': 'meeting', 'id': g.id},
                            'asks': 'held_at'}])
    r.calls.left = [reading(ASKED)]
    asked = r.post('It was 2026-09-20.', in_reply_to=forged.id)
    assert r.pass_once()['changed'] is True
    assert r.one(entities.Meeting, g.id).held_at is None, 'a forged card asked nothing'
    assert r.intent(asked['message_id']).via == 'brain'           # read, not dated
    assert len(r.calls.specs) == 2                                # both turns, by the brain


# ── what the grammar may obey, and what is the brain's ──────────────────────

def test_a_control_verb_never_reaches_the_model(make):
    # read's `if control is not None`: the verb is obeyed with no call at all, and the
    # intent is the grammar's own. Route a control verb through the brain and the verb
    # is whatever a model said it was.
    r = make()
    m = r.mission(title='Ship it')
    posted = r.post(CANCEL)
    assert r.pass_once()['changed'] is True
    assert r.calls.specs == []
    assert r.one(entities.Mission, m.id).state == 'CANCELLED'
    it = r.intent(posted['message_id'])
    assert (it.kind, it.via, it.resolution, it.reason) == (
        'control_verb', 'grammar', 'mission_updated', 'cancel')
    assert it.target_refs == ({'kind': 'mission', 'id': m.id},)


@pytest.mark.parametrize('text', [
    'stopwatch the review of Ship it',            # begins like a verb, is not one
    'status of the whole world',                  # a verb whose object does not resolve
    'pause all about the Ship it mission',        # not the all-scope verb either
])
def test_a_turn_that_only_begins_like_a_control_verb_is_read(make, text):
    # `grammar.resolve -> None` is the whole safety of the grammar: a sentence that
    # happens to begin with a verb word is read, not obeyed. Route it to apply_control
    # and a mission is cancelled on a pun.
    r = make()
    m = r.mission(title='Ship it')
    r.calls.left = [reading(WORK)]
    posted = r.post(text)
    assert r.pass_once()['changed'] is True
    assert len(r.calls.specs) == 1
    assert r.one(entities.Mission, m.id).state == 'CREATED'
    assert r.intent(posted['message_id']).via == 'brain'


def test_a_bare_verb_in_a_mission_s_own_thread_is_about_that_mission(make):
    # read's `mission=conv.mission_id`: in a mission's thread a verb with no object is
    # that mission's. Never pass the thread and a bare "cancel" is a sentence for the
    # brain, and the mission the user was standing in is never cancelled.
    r = make()
    m = r.mission(title='Ship it')
    posted = r.post('cancel', into=m.id)
    assert r.pass_once()['changed'] is True
    assert r.calls.specs == []
    assert r.one(entities.Mission, m.id).state == 'CANCELLED'
    it = r.intent(posted['message_id'])
    assert (it.via, it.resolution, it.reason) == ('grammar', 'mission_updated', 'cancel')
    assert it.target_refs == ({'kind': 'mission', 'id': m.id},)


def test_an_object_that_resolves_to_two_missions_is_obeyed_as_neither(make):
    # grammar's `_one`: two live missions of one title name none of them, so the turn
    # is the brain's. Return the first match and "cancel Twin" cancels one of twins.
    r = make()
    a, b = r.mission(title='Twin'), r.mission(title='twin')
    r.calls.left = [reading(ASKED)]
    r.post('cancel Twin')
    assert r.pass_once()['changed'] is True
    assert len(r.calls.specs) == 1
    assert [r.one(entities.Mission, x.id).state for x in (a, b)] == ['CREATED', 'CREATED']


def test_what_the_execution_port_names_the_grammar_names_without_a_model(make):
    # read's `harnesses=self.conv.harnesses()`: a harness the execution port has is a
    # resource the grammar may name, and naming it is never a model's guess. Ask the
    # port for nothing and the same words are read instead (just below).
    r = make(harnesses=('fake',))
    m = r.mission(title='Ship it')
    r.post('use fake for Ship it')
    assert r.pass_once()['changed'] is True
    assert r.calls.specs == []                             # the model was not asked
    assert r.one(entities.Mission, m.id).state == 'CREATED'


def test_a_harness_nobody_offered_is_a_sentence_rather_than_a_directive(make):
    # The same words, and the port names no harness: what does not resolve is the
    # brain's, and the model reads it as prose. Name an unoffered resource here and a
    # typo sets a mission's resources by a sentence nobody could honour.
    r = make(script=[reading(ASKED)])
    m = r.mission(title='Ship it')
    posted = r.post('use fake for Ship it')
    assert r.pass_once()['changed'] is True
    assert len(r.calls.specs) == 1
    assert r.intent(posted['message_id']).via == 'brain'
    assert r.one(entities.Mission, m.id).resource_preferences is None


def test_a_harness_named_in_the_words_is_the_mission_s_own_preference(make):
    # The obeyed turn above, to the end: the directive is recorded against the message
    # and the intent that asked for it, with no model in between. (The worker's part —
    # that these words are the grammar's — holds today, and is the test above; what
    # cannot be recorded is what `directive` does with the ref it is given.)
    r = make(harnesses=('fake',))
    m = r.mission(title='Ship it')
    posted = r.post('use fake for Ship it')
    assert r.pass_once()['changed'] is True
    assert r.calls.specs == []
    it = r.intent(posted['message_id'])
    assert (it.kind, it.via, it.reason) == ('control_verb', 'grammar', 'use')
    assert it.target_refs == ({'kind': 'mission', 'id': m.id},)
    rp = r.one(entities.Mission, m.id).resource_preferences
    assert rp['preferred_harnesses'] == ['fake']
    assert [d['message_id'] for d in rp['directives']] == [posted['message_id']]


def test_an_empty_turn_is_the_brain_s_and_is_still_read(make):
    # The grammar with nothing in it: no words to obey, so the message is neither
    # skipped, nor answered from nothing, nor an invented control. It is read, and the
    # reading is recorded — which today it cannot be, and the worker's only answer for
    # the event is the ValueError the record raised.
    r = make()
    r.calls.left = [reading(ASKED)]
    m = r.turn('user', '')
    assert r.pass_once()['changed'] is True
    got = r.effect(r.seq_of(entities.Message, m.id))
    assert not got.startswith('error:'), got                     # never the worker's death
    if r.calls.specs:                    # read: over this message's package, with no verbs
        assert len(r.calls.specs) == 1 and got.startswith('brain:')
        assert r.calls.spec['prompt'].endswith('The message:\n')
        assert 'Context:' in r.calls.spec['prompt']
        assert r.intent(m.id) is not None                        # and the reading recorded
    else:                                # or skipped whole, as an empty turn deserves
        assert got == '' and r.intent(m.id) is None


# ── an answer to a question is not a command ────────────────────────────────

def test_an_answer_to_a_question_is_never_obeyed_as_a_control_verb(make):
    # read's `None if ask else grammar.resolve`: Archeus asked, and the answer happens
    # to read as a verb. Delete the `None if ask` and the answer to a question cancels
    # a mission.
    r = make()
    m = r.mission(title='Ship it')
    asked = r.ask('Should I cancel it, or leave it running?',
                  {'kind': 'intent', 'id': ids.new_id('intent')}, asks='cancel or keep')
    r.calls.left = [reading(ASKED)]
    posted = r.post(CANCEL, in_reply_to=asked.id)
    assert r.pass_once()['changed'] is True
    assert len(r.calls.specs) == 1
    assert "This message answers Archeus's question:" in r.calls.spec['prompt']
    assert asked.text in r.calls.spec['prompt']                   # what it answers
    assert r.one(entities.Mission, m.id).state == 'CREATED'       # never obeyed
    it = r.intent(posted['message_id'])
    assert (it.via, it.answers_intent_id) == ('brain', asked.cards[0]['ref']['id'])


def test_an_ordinary_earlier_turn_does_not_shield_a_control_verb(make):
    # _asked: an Archeus turn carrying no clarification or challenge card asked
    # nothing, so the grammar still runs. Return its cards unfiltered and a plain
    # reply shields a verb from the grammar.
    r = make()
    m = r.mission(title='Ship it')
    said = r.turn('archeus', 'Ship it is running.',
                  cards=[{'type': 'status', 'ref': {'kind': 'mission', 'id': m.id}}])
    posted = r.post(CANCEL, in_reply_to=said.id)
    assert r.pass_once()['changed'] is True
    assert r.calls.specs == []
    assert r.one(entities.Mission, m.id).state == 'CANCELLED'
    assert r.intent(posted['message_id']).via == 'grammar'


def test_a_reply_naming_a_meeting_dates_it_without_the_model(make):
    # read's `ask['kind'] == 'meeting'` branch: the date is read out of the turn by the
    # command, with no call, and the worker answers `dated:`. Route it through the
    # brain and a model dates a meeting the user never dated.
    r = make()
    g = r.meeting(name='Kickoff')
    asked = r.ask('When was the Kickoff meeting held?', {'kind': 'meeting', 'id': g.id},
                  asks='held_at')
    posted = r.post('It was 2026-09-20, I was there.', in_reply_to=asked.id)
    assert r.pass_once()['changed'] is True
    assert r.calls.specs == []
    assert r.one(entities.Meeting, g.id).held_at == '2026-09-20'
    it = r.intent(posted['message_id'])
    assert (it.kind, it.via, it.resolution, it.reason) == (
        'control_verb', 'grammar', 'answered', 'held_at')
    assert it.target_refs == ({'kind': 'meeting', 'id': g.id},)


def test_a_reply_to_a_date_question_that_says_a_verb_dates_nothing_and_cancels_nothing(make):
    # Both guards of that branch at once: the ask beats the grammar, AND the date is
    # only what a date looks like. Drop the ask and the verb is obeyed; drop the date
    # check and any sentence at all dates the meeting.
    r = make()
    g = r.meeting(name='Kickoff')
    m = r.mission(title='Ship it')
    asked = r.ask('When was the Kickoff meeting held?', {'kind': 'meeting', 'id': g.id},
                  asks='held_at')
    posted = r.post(CANCEL, in_reply_to=asked.id)
    assert r.pass_once()['changed'] is True
    assert r.calls.specs == []
    assert r.one(entities.Meeting, g.id).held_at is None
    assert r.one(entities.Mission, m.id).state == 'CREATED'
    it = r.intent(posted['message_id'])
    assert (it.resolution, it.reason) == ('declined', 'held_at')


# ── how the call is asked for, and what its answer must pass ────────────────

def test_the_call_is_asked_for_as_a_tool_less_call_over_this_message_s_package(make):
    # _brain: `no_tools`, the purpose, the source, the package it recorded and the
    # caller's own check, bound to THIS message's handles. Those are the whole
    # containment of the model: a handle the package never gave must be a problem,
    # and one it gave must not.
    r = make()
    k = r.knowledge()
    said = r.turn('archeus', 'Ask me anything about the release.')
    posted = r.post('what do we hold about releases?')
    r.calls.left = [reading({'kind': 'question', 'answer': [{'text': 'Fridays', 'refs': []}]})]
    assert r.pass_once()['changed'] is True
    spec = r.calls.spec
    assert (spec['purpose'], spec['no_tools'], spec['workspace_id'], spec['project_id']) == (
        'brain', True, ids.GLOBAL_WORKSPACE, None)
    assert spec['source'] == {'kind': 'message', 'id': posted['message_id']}
    assert spec['schema'] is brain.SCHEMA and spec['workdir'] is paths.fresh_call_dir
    it = r.intent(posted['message_id'])
    assert spec['context_package_id'] == it.context_package_id
    pkg = r.one(entities.ContextPackage, it.context_package_id)
    assert (pkg.subject_kind, pkg.subject_id) == ('message', posted['message_id'])
    give = [h for h, ref in brain.handles({'items': [dict(i) for i in pkg.items],
                                           'subject_id': pkg.subject_id})]
    assert give, 'the package gave the model nothing to cite'
    assert k.title in spec['prompt'] and said.text in spec['prompt']
    good = {'kind': 'question', 'answer': [{'text': 'Fridays', 'refs': give}]}
    assert spec['check'](good) == []
    bad = spec['check']({'kind': 'question', 'answer': [{'text': 'x', 'refs': ['zz9']}]})
    assert bad and 'zz9' in bad[0]


def test_the_application_is_cited_to_the_call_it_belongs_to(make):
    # _brain's `called`: the intent cites the call that read it, and that call ends `ok`
    # with the counts it was given. Swap the ids and a reading is owned by a message
    # that never asked for it; drop the usage and the consumption hides.
    r = make()
    rd = r.open_call()
    usage = {'tokens_in': 4, 'tokens_out': 2, 'cache_read': 0, 'cache_write': 0,
             'cost_usd': 0.001}
    r.calls.left = [reading(WORK, rd=rd, usage=usage, attempts=1, account_ref='harness:x')]
    posted = r.post('Add a --version flag to the CLI')
    assert r.pass_once()['changed'] is True
    it = r.intent(posted['message_id'])
    assert (it.via, it.resolution, it.route_decision_id) == ('brain', 'mission_created', rd)
    assert it.context_package_id == r.calls.spec['context_package_id'] != rd
    got = r.one(entities.RouteDecision, rd)
    assert got.outcome['state'] == 'ok' and got.outcome['kind'] == 'new_work'
    assert (got.outcome['attempts'], got.outcome['account_ref']) == (1, 'harness:x')
    assert [u.basis for u in r.rows(entities.UsageLedger)] == ['reported_total']


# ── once is the database's ───────────────────────────────────────────────────

def test_a_message_is_read_once_even_when_its_event_is_delivered_again(make):
    # read's `already read`: the effect row is gone but the intent row is there, so a
    # second delivery must answer `already read` with no second call, no second intent
    # and no second mission. Delete the check and a crash between the call and the
    # effect doubles every mission the user asked for.
    r = make()
    r.calls.left = [reading(WORK), reading({'kind': 'idea', 'title': 'Second',
                                            'objective': 'Another thing entirely.'})]
    posted = r.post('Add a --version flag to the CLI')
    assert r.pass_once()['changed'] is True
    assert len(r.calls.specs) == 1 and r.effect(posted['seq']) == 'brain:mission_created'
    first = r.intent(posted['message_id']).id
    r.set_cursor(mi.CONSUMER, 0)                       # the same event again
    r.forget(posted['seq'])                            # as if its effect row were pruned
    assert r.pass_once()['changed'] is True
    assert r.effect(posted['seq']) == 'already read'
    assert len(r.calls.specs) == 1
    assert [i.id for i in r.rows(entities.Intent)] == [first]
    assert len(r.rows(entities.Mission)) == 1


# ── reading a message against what was learned before it ────────────────────

def test_a_worker_told_to_wait_for_nothing_waits_for_nothing(make):
    # _learned's `if self.after is None: return` (the binding the in-process judge
    # uses): the named consumer is never consulted and no wait is ever asked for.
    # Honour `after` anyway here and this waits until the rig gives up.
    r = make(after=None, wait_s=30.0)
    r.knowledge()
    r.set_cursor('knowledge', 0)                         # behind everything it posts
    m = r.mission(title='Ship it')
    posted = r.post(CANCEL)
    assert r.pass_once()['changed'] is True
    assert r.waits == [] and r.intent(posted['message_id']) is not None
    assert r.one(entities.Mission, m.id).state == 'CANCELLED'


def test_a_message_that_is_already_caught_up_waits_no_time(make):
    # _learned's `cursor >= seq - 1`, at its boundary: the message's own event is
    # `seq`, so a cursor at the event before it is enough and nothing is waited for.
    # Offside it by one and every message of a live Core spends its 30 s here.
    r = make(after='knowledge', wait_s=30.0)
    r.knowledge()
    posted = r.post('remember that we ship on Fridays')
    r.set_cursor('knowledge', posted['seq'] - 1)          # learned up to the turn before
    assert r.pass_once()['changed'] is True
    assert r.waits == [] and r.intent(posted['message_id']) is not None


def test_a_message_waits_for_the_lesson_before_it_in_slices_that_end_at_a_stop(make):
    # _learned's wait: behind, the worker waits on the writer's commit signal, in
    # slices of at most a second, with `stopping` as the way out — and catches up as
    # soon as the consumer it waits for moves. A slice longer than 1.0 s, or a wait
    # without the stop, is the finding; nothing is slept here.
    r = make(after='knowledge', script=[reading(ASKED)], wait_s=30.0)
    r.knowledge(title='We ship on Fridays')               # the lesson it must wait for
    posted = r.post('what did the notes say?')
    r.set_cursor('knowledge', 0)                          # learned none of it
    caught_up = lambda: r.set_cursor('knowledge', posted['seq'] - 1)      # noqa: E731
    r.on_wait = [caught_up]
    assert r.pass_once()['changed'] is True
    assert r.waits and all(0 < w['timeout'] <= 1.0 for w in r.waits)
    assert r.waits[0]['until'] is r.worker.stopping
    assert r.cursor('knowledge') == posted['seq'] - 1
    assert r.intent(posted['message_id']) is not None


def test_a_message_that_outwaits_the_lesson_is_read_anyway_and_says_so(make, caplog):
    # _learned's `if left <= 0`: the bound is reached, so the message is read with what
    # there is, once, and the warning is written. Make it fail closed instead and a
    # stuck knowledge consumer stops every message on the Core; drop the warning and
    # a Core reading stale context looks healthy.
    r = make(after='knowledge', script=[reading(ASKED)], wait_s=0.0)
    r.knowledge(title='We ship on Fridays')
    r.set_cursor('knowledge', 0)                          # and it never moves
    posted = r.post('what did the notes say?')
    with caplog.at_level(logging.WARNING, logger='archeus.core'):
        assert r.pass_once()['changed'] is True
    assert r.waits == []
    assert 'is read before knowledge caught up' in caplog.text
    assert r.intent(posted['message_id']) is not None


def test_a_worker_that_is_stopping_stops_waiting(make):
    # _learned's `while not self.stopping()`: the stop ends the wait at once and the
    # message is still read afterwards. Ignore stopping and the worker sits in its own
    # wait through its shutdown.
    r = make(after='knowledge', script=[reading(ASKED)], wait_s=30.0)
    r.knowledge(title='We ship on Fridays')
    r.set_cursor('knowledge', 0)
    posted = r.post('what did the notes say?')
    r.worker.stopping = lambda: True
    assert r.pass_once()['changed'] is True
    assert r.waits == [] and r.intent(posted['message_id']) is not None


# ── the loop's own boundary values ──────────────────────────────────────────

def test_the_worker_arms_its_engine_only_when_there_is_something_to_read(make):
    # pending's `if n and self.on_wake is not None`, called on every pass of the loop:
    # an idle worker must never arm the engine (that is a spin), and a backlog must
    # arm it once, or a Core sleeps through a turn.
    r = make()
    r.settle()                                             # what booting the rig wrote
    assert r.worker.pending() == 0 and r.wakes == []
    r.post('hello there')
    assert r.worker.pending() > 0 and len(r.wakes) == 1
    r.settle()
    assert r.worker.pending() == 0 and len(r.wakes) == 1


def test_a_pass_says_whether_the_cursor_moved(make):
    # pass_once's `> 0`: `changed` is what the engine loop sleeps on, so a pass that
    # reports movement when nothing moved is a busy loop, and one that misses movement
    # never reads a message at all.
    r = make()
    r.settle()                                             # what booting the rig wrote
    assert r.pass_once() == {'changed': False}
    r.post('hello there')
    assert r.pass_once() == {'changed': True}
    r.settle()
    assert r.pass_once() == {'changed': False}


def test_the_boot_sweep_holds_nothing_because_open_calls_are_not_the_worker_s(make):
    # sweep's `return []`: a RouteDecision left open by a dead Core is the knowledge
    # worker's boot sweep (P6); return anything here and the runtime re-opens calls
    # this worker never made, and ends them twice.
    r = make()
    rd = r.open_call()
    assert r.worker.sweep() == []
    assert r.one(entities.RouteDecision, rd).outcome is None
