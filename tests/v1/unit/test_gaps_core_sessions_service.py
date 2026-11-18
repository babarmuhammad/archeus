"""T-313: the branches of `archeus/core/sessions/service.py` no test reached —
the fail-closed and denial paths first, then the boundary values, then the
error paths (p12-design-gate §9, §10.2, §14).

What is already covered lives in tests/v1/integration/test_sessions.py (the
machine, the happy resume, the brief, a hand-off's artifact, the boot sweep, one
real two-threaded launch race). What is asserted here is what that file never
walks into: who is refused and by which word, what is NOT written when a world
answer is missing, which principal signs each recorded command, what a lost
claim, a raising terminal and a swallowed `vanished` do to the caller, and which
ids, sequences and paths the launcher hands to the adapter.

Everything below is a unit. The writer, the reader, the node's terminal and the
harness adapters are the recording seams the suite already uses — `Terminal` as
in tests/v1/integration/test_sessions.py, `rows` swapped as in
tests/v1/unit/test_t144_checkpoint_consumption.py, `FakeSessions` from
archeus/harnesses/sessions.py — so the service's own decisions are the only code
under test, and no real process, thread, network or OS state is touched. Every
file written is inside the test's own `tmp_path` / `ARCHEUS_HOME`.
"""

import os
import threading
from contextlib import nullcontext

import pytest

from archeus.core.application import sessions as S
from archeus.core.application.world import Conflict
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.sessions import service as SV
from archeus.harnesses import base
from archeus.harnesses.sessions import FakeSessions, Located
from archeus.infra.artifacts import store as artifacts
from archeus.infra.db import rows
from archeus.infra.db.writer import NotFound

#: A timestamp in the field's real shape: what `_epoch` is handed, unvalidated.
STARTED = '2026-10-30T09:00:00Z'

USER = Ref('user_device', ids.new_id('principal'))
SYSTEM = Ref('system', ids.new_id('principal'))

MISSING = object()


# ── the seams ────────────────────────────────────────────────────────────────

class Call:
    def __init__(self, command, data, idempotency_key):
        self.command, self.data, self.idempotency_key = command, data, idempotency_key

    @property
    def name(self):
        return self.command.__name__

    def __repr__(self):
        return 'Call(%s, %r, key=%r)' % (self.name, self.data, self.idempotency_key)


class Recorder:
    """`db.writer`: records every command the service runs and answers from a
    table. An answer may be a value, a list of values consumed one per call (a
    claim that is won once and lost once), an exception instance to raise, or a
    callable of the command's data."""

    DEFAULTS = {'open_session': lambda: {'id': ids.new_id('session')},
                'resume': {'duplicate': False, 'artifact_sha': None},
                'handoff': lambda: {'duplicate': False, 'id': ids.new_id('session'),
                                    'handoff_artifact_sha': None},
                'claim_launch': {'won': True}, 'launched': {}, 'observe': {},
                'vanished': {}, 'reappeared': {}, 'expire_launches': {'expired': []}}

    def __init__(self):
        self.calls, self.answers = [], {}

    def answer(self, name, value):
        self.answers[name] = value

    def execute(self, command, kwargs=None, *, idempotency_key=None, timeout=None):
        call = Call(command, dict(kwargs or {}), idempotency_key)
        self.calls.append(call)
        got = self.answers.get(call.name, self.DEFAULTS[call.name])
        got = got() if callable(got) and not isinstance(got, (dict, list)) else got
        if isinstance(got, list):
            got = got.pop(0)
        if isinstance(got, BaseException):
            raise got
        return dict(got) if isinstance(got, dict) else got


class FakeDb:
    """`Database`: one writer recorder, and reads that see exactly the rows
    `FakeRows` holds. `reads` counts them: a branch that must not look at the
    database at all is asserted on the count."""

    def __init__(self, writer):
        self.writer, self.reads = writer, 0

    def read(self):
        self.reads += 1
        return nullcontext(self)


class FakeRows:
    """The `rows` module as the service sees it: the entities it reads, in memory."""

    def __init__(self):
        self.table = {entities.Session: {}, entities.Account: {}}

    def put(self, entity):
        self.table[type(entity)][entity.id] = entity
        return entity

    def get(self, conn, cls, entity_id):
        entity = self.table[cls].get(entity_id)
        return None if entity is None else rows.Row(entity, 1, '', '', '', '')

    def where(self, conn, cls, **eq):
        return [rows.Row(e, 1, '', '', '', '') for e in self.table[cls].values()]


class Terminal:
    """The node's terminal opener, recorded instead of opened, as the
    integration rig's `Terminal`. `fail` answers a launch error; `raises` makes
    the node blow up instead."""

    def __init__(self):
        self.opened, self.fail, self.raises = [], None, None

    def open_terminal(self, argv, *, cwd, env, title=''):
        if self.raises is not None:
            raise self.raises
        self.opened.append({'argv': list(argv), 'cwd': cwd, 'env': dict(env), 'title': title})
        return (None, self.fail) if self.fail else (object(), None)


class StubSessions(FakeSessions):
    """`FakeSessions` with the world's answers under the test's control and a
    record of every question asked: `MISSING` keeps the real file-backed rule."""

    def __init__(self, id, *, models=('fake-model', 'fake-large'), efforts=('low', 'high'),
                 installed=True, caps=None):
        super().__init__(id, models=models, efforts=efforts, installed=installed)
        self.caps = caps
        self.located, self.found, self.turns_value, self.failed = MISSING, MISSING, \
            MISSING, None
        self.asked, self.accounts_asked = [], []

    def capabilities(self, account=None):
        self.accounts_asked.append(account)
        return super().capabilities(account) if self.caps is None else self.caps

    def locate(self, ref, home, cwd):
        self.asked.append(('locate', ref, home, cwd))
        return super().locate(ref, home, cwd) if self.located is MISSING else self.located

    def find(self, home, cwd, since):
        self.asked.append(('find', None, home, cwd, since))
        return super().find(home, cwd, since) if self.found is MISSING else self.found

    def turns(self, transcript_path, limit):
        self.asked.append(('turns', transcript_path, limit))
        return super().turns(transcript_path, limit) if self.turns_value is MISSING \
            else self.turns_value

    def launch_argv(self, spec):
        if self.failed is not None:
            raise self.failed
        return super().launch_argv(spec)

    def kinds(self):
        return [a[0] for a in self.asked]


class Rig:
    def __init__(self, cwd):
        self.cwd = str(cwd)
        self.rows, self.writes = FakeRows(), Recorder()
        self.db = FakeDb(self.writes)
        self.term = Terminal()
        self.fa = StubSessions('fake_a')
        self.fb = StubSessions('fake_b', models=('b-small', 'b-large'), efforts=('min', 'max'))
        self.service = SV.SessionService(self.db, system=SYSTEM, adapters=[self.fa, self.fb],
                                         node=self.term)

    # ── what the service reads ──
    def session(self, **kw):
        base = dict(id=ids.new_id('session'), harness_id='fake_a',
                    workspace_id=ids.GLOBAL_WORKSPACE, cwd=self.cwd, mode='manual',
                    state='OPEN', provider_session_ref='ref-1', started_at=STARTED,
                    last_active_at=STARTED)
        base.update(kw)
        if base.get('mode') == 'headless' and base.get('execution_id') is None:
            base['execution_id'] = ids.new_id('execution')
        return self.rows.put(entities.Session(**base))

    def account(self, **kw):
        base = dict(id=ids.new_id('account'), harness_id='fake_a', label='one',
                    auth_kind='api_key', home_ref='home-one')
        base.update(kw)
        return self.rows.put(entities.Account(**base))

    def target(self, **kw):
        """The session a hand-off's command answer names: the launcher has to be
        able to read it, as a real one would exist by then."""
        base = dict(harness_id='fake_b', mode='interactive_attached', launch_seq=1,
                    provider_session_ref=None)
        base.update(kw)
        return self.session(**base)

    def provider(self, adapter, ref, turns=(('user', 'hi'),)):
        """The provider session a real harness would have left behind; returns
        the transcript path the session row has to carry to stay up to date."""
        adapter.write(ref, turns)
        return adapter.path(ref)

    # ── what the service writes ──
    def answer(self, command, value):
        self.writes.answer(command.__name__, value)

    def calls(self, command):
        name = command.__name__
        return [c for c in self.writes.calls if c.name == name]

    def data(self, command):
        (call,) = self.calls(command)
        return call.data

    def names(self):
        return [c.name for c in self.writes.calls]

    def delivery(self, sid):
        return SV.delivery_path(self.cwd, sid)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    work = tmp_path / 'work'
    work.mkdir()
    r = Rig(work)
    monkeypatch.setattr(SV, 'rows', r.rows)          # the service's only reader
    return r


# ── create ───────────────────────────────────────────────────────────────────

def test_a_registered_session_writes_one_row_and_launches_nothing(rig):
    """service.py:110-112 — `register` asks for NO capability (`need=()`) and
    never reaches the launcher; inverting `need=()` to the default, or letting a
    registration launch, both fail here."""
    s = rig.session()
    rig.fa.caps = base.Capabilities(frozenset(), 'none')      # declares nothing at all
    rig.answer(S.open_session, {'id': s.id})
    out = rig.service.register(USER, harness_id='fake_a', cwd=rig.cwd)
    assert out == {'id': s.id}                                # the command's own answer
    (call,) = rig.calls(S.open_session)
    assert call.data['mode'] == 'manual' and call.data['actor'] == USER
    assert 'launch' not in call.data and 'models' in call.data   # no launch; the vocabulary checks model and effort
    assert rig.names() == ['open_session'] and rig.term.opened == []


def test_a_harness_that_is_not_installed_refuses_before_anything_is_written(rig):
    """service.py:79-81 — `a is None or not a.discover().installed`: an unknown
    harness id AND a known harness that discovery says is gone are both refused
    as 409, and neither reaches the writer."""
    rig.fa.installed = False
    for harness in ('no_such_harness', 'fake_a', 'gone_a'):
        rig.writes.calls[:] = []
        with pytest.raises(SV.Refused, match='%s is not installed' % harness) as got:
            rig.service.register(USER, harness_id=harness, cwd=rig.cwd)
        assert isinstance(got.value, Conflict)                # the 409 mapping
        assert rig.writes.calls == []                         # nothing written, fail-closed
        assert rig.fa.asked == [] and rig.fb.asked == []      # not even asked of the world


def test_a_harness_that_does_not_declare_resume_cannot_be_resumed(rig):
    """service.py:85-87 — `missing = [c for c in need if c not in caps.capabilities]`:
    a resume of an adapter missing the `resume` capability is refused by name,
    records nothing and opens no terminal; the same adapter still registers."""
    s = rig.session()
    rig.fa.caps = base.Capabilities(frozenset({'interactive'}), 'none', ('fake-model',))
    with pytest.raises(SV.Refused, match='does not declare resume'):
        rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert rig.names() == [] and rig.term.opened == [] and rig.fa.launched == []
    rig.answer(S.open_session, {'id': s.id})
    assert rig.service.register(USER, harness_id='fake_a', cwd=rig.cwd) == {'id': s.id}


def test_the_models_a_launch_may_use_are_this_account_s_and_nobody_else_s(rig):
    """service.py:82-88 — `home = home or self._home(account_id)` and the
    `AccountRef(...) if home else None` argument: the capabilities are asked OF
    the launching account's own home, and its model ids (ModelInfo or bare
    strings) are what the command is offered."""
    acct = rig.account(home_ref='home-a')
    s = rig.session(account_id=acct.id, provider_session_ref=None, mode='interactive_attached',
                    launch_seq=1)
    rig.fa.caps = base.Capabilities(frozenset({'interactive', 'resume'}), 'none',
                                    (base.ModelInfo('mine-large'), 'mine-small'),
                                    efforts=('low',))
    rig.answer(S.open_session, {'id': s.id})
    out = rig.service.launch(USER, harness_id='fake_a', cwd=rig.cwd, account_id=acct.id)
    assert out['launch']['launched']
    (call,) = rig.calls(S.open_session)
    assert call.data['models'] == ['mine-large', 'mine-small'] and call.data['efforts'] == ['low']
    assert call.data['mode'] == 'interactive_attached' and call.data['launch'] is True
    assert rig.fa.accounts_asked == [base.AccountRef(acct.id, 'home-a')]
    assert rig.term.opened != [] and rig.fa.launched[-1].home == 'home-a'


def test_a_launch_with_no_account_asks_the_harness_for_its_own_defaults(rig):
    """service.py:69-71 + 82-84 — `_home(None)` returns None WITHOUT a read and
    `capabilities` is then asked nothing (`if home else None`): a session with no
    account is launched on the harness's own home, never on some account's."""
    s = rig.session(mode='interactive_attached', launch_seq=1)
    rig.answer(S.open_session, {'id': s.id})
    rig.service.launch(USER, harness_id='fake_a', cwd=rig.cwd)
    reads_after_launch = rig.db.reads                        # one read: the launcher's session
    assert rig.fb.accounts_asked == [] and rig.fa.accounts_asked == [None]
    assert reads_after_launch == 1
    assert rig.fa.launched[-1].home is None


def test_the_idempotency_key_of_a_launch_reaches_the_writer(rig):
    """service.py:53-54 — `execute(command, dict(kw, actor=actor),
    idempotency_key=key)`: a launch that loses its key would let the same
    request open two terminals."""
    s = rig.session(mode='interactive_attached', launch_seq=1)
    rig.answer(S.open_session, {'id': s.id})
    rig.service.launch(USER, key='k1', harness_id='fake_a', cwd=rig.cwd)
    assert [c.idempotency_key for c in rig.writes.calls] == ['k1', None, None]
    assert rig.calls(S.claim_launch)[0].data['actor'] == SYSTEM   # Core signs its own records


# ── unknown ids ──────────────────────────────────────────────────────────────

def test_an_unknown_session_id_is_not_found_before_the_world_is_asked_or_written(rig):
    """service.py:56-61 — `if row is None: raise NotFound(session_id)`: every
    operation that names a session fails on the id first, with no command
    recorded and no adapter consulted."""
    for what in ('resume', 'handoff', 'launch_of_unknown'):
        rig.writes.calls[:] = []
        rig.fa.asked[:] = []
        with pytest.raises(NotFound):
            if what == 'resume':
                rig.service.resume(USER, session_id='ses_missing', request_id='r1')
            elif what == 'handoff':
                rig.service.handoff(USER, source_session_id='ses_missing', request_id='h1',
                                    harness_id='fake_b')
            else:
                rig.service._launch('ses_missing')
        assert rig.writes.calls == [] and rig.fa.asked == [] and rig.term.opened == []


def test_a_session_whose_account_row_is_gone_is_launched_on_no_home(rig):
    """service.py:64-66 — `home = a.entity.home_ref if a else None`: a session
    still naming a deleted account resumes on NOTHING rather than on a stale or
    borrowed home."""
    s = rig.session(account_id=ids.new_id('account'))           # the account row is gone
    rig.provider(rig.fa, 'ref-1')
    out = rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert out['launch']['launched']
    assert rig.fa.accounts_asked == [None]                # no account: the harness's own home
    assert rig.fa.launched[-1].home is None


# ── resume ───────────────────────────────────────────────────────────────────

def test_a_session_whose_provider_session_was_never_seen_is_refused_and_left_open(rig):
    """service.py:97-100 + 129-130 — a ref-less session whose harness `find`
    answers nothing is refused 'not known yet' and is NOT marked lost: absence of
    evidence is not evidence of absence, and nothing is launched."""
    s = rig.session(provider_session_ref=None)
    rig.fa.found = None
    with pytest.raises(SV.Refused, match='not known yet'):
        rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert rig.names() == [] and rig.calls(S.vanished) == [] and rig.term.opened == []
    assert s.state == 'OPEN'
    assert ('find', None, None, rig.cwd, SV._epoch(STARTED)) in rig.fa.asked


def test_a_provider_session_the_harness_named_itself_is_observed_then_resumed(rig):
    """service.py:97-101 — when no ref is recorded, `adapter.find` is asked (with
    the session's own start as the boundary) and a found ref is recorded through
    `S.observe` BEFORE the resume command runs."""
    s = rig.session(provider_session_ref=None, started_at=STARTED,
                    transcript_path='/transcripts/ref-found.jsonl')
    rig.fa.found = 'ref-found'
    rig.fa.located = Located('/transcripts/ref-found.jsonl')
    rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert rig.names() == ['observe', 'resume', 'claim_launch', 'launched']
    observe = rig.data(S.observe)
    assert observe['provider_session_ref'] == 'ref-found' and observe['actor'] == SYSTEM
    assert ('find', None, None, rig.cwd, SV._epoch(STARTED)) in rig.fa.asked


def test_a_moved_transcript_is_observed_and_an_unchanged_one_is_never_written(rig):
    """service.py:102-105 — `got.transcript_path != s.transcript_path`: the guard
    both ways; an unchanged path records no `observe` at all."""
    s = rig.session(transcript_path='/transcripts/old.jsonl')
    rig.fa.located = Located('/transcripts/new.jsonl')
    rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert [c.data['transcript_path'] for c in rig.calls(S.observe)] == ['/transcripts/new.jsonl']
    rig.writes.calls[:] = []
    rig.fa.located = Located('/transcripts/new.jsonl')
    s2 = rig.session(transcript_path='/transcripts/new.jsonl')
    rig.service.resume(USER, session_id=s2.id, request_id='r1')
    assert rig.calls(S.observe) == []


def test_a_lost_session_still_missing_is_refused_but_never_lost_twice(rig):
    """service.py:131-133 — `if s.state == 'OPEN': self._vanish(...)`: a LOST
    session whose provider session is still gone is refused, and no second
    `vanished` is fired (the machine has no LOST->LOST edge: firing one raises)."""
    s = rig.session(state='LOST')
    rig.fa.located = None
    with pytest.raises(SV.Refused, match='is gone'):
        rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert rig.calls(S.vanished) == [] and rig.calls(S.reappeared) == []
    assert rig.names() == [] and rig.term.opened == []


def test_a_vanished_that_cannot_be_recorded_still_refuses_the_resume(rig):
    """service.py:167-171 — `_vanish` swallows a rejected transition: the caller
    must still get the 409 Refused, not the writer's error."""
    s = rig.session()
    rig.fa.located = None
    rig.answer(S.vanished, RuntimeError('no vanished edge from CLOSED'))
    with pytest.raises(SV.Refused, match='is gone'):
        rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert len(rig.calls(S.vanished)) == 1 and rig.term.opened == []


def test_a_provider_session_found_again_brings_the_session_back_before_resuming(rig):
    """service.py:134-136 — `if s.state == 'LOST': self._do(S.reappeared, ...)`
    (a remounted drive): the session is reopened with the found transcript, as
    Core, and only then resumed."""
    s = rig.session(state='LOST', transcript_path='/transcripts/back.jsonl')
    rig.fa.located = Located('/transcripts/back.jsonl')
    out = rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert out['launch']['launched']
    assert rig.names() == ['reappeared', 'resume', 'claim_launch', 'launched']
    assert rig.data(S.reappeared) == {'actor': SYSTEM, 'session_id': s.id,
                                      'transcript_path': '/transcripts/back.jsonl'}


def test_a_headless_session_is_never_asked_of_the_world(rig):
    """service.py:126 — `s.mode != 'headless'`: an execution's session carries no
    provider session to look for, so the adapters are not asked at all."""
    s = rig.session(mode='headless')
    rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert rig.fa.kinds() == [] and rig.fb.kinds() == []
    assert rig.names() == ['resume', 'claim_launch', 'launched']


def test_the_request_a_session_was_last_resumed_on_rereads_nothing(rig):
    """service.py:126 — `s.last_request != request_id`: a replayed request asks
    the harness nothing; the command alone decides whether it is a duplicate."""
    s = rig.session(last_request='r1')
    rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert rig.fa.kinds() == []


def test_a_duplicate_resume_returns_the_command_answer_and_opens_nothing(rig):
    """service.py:139-140 — `if out['duplicate']: return out`: the duplicate's
    answer carries no launcher at all, so a replayed request can never open a
    second terminal nor claim a launch."""
    path = rig.provider(rig.fa, 'ref-1')
    s = rig.session(transcript_path=path)
    rig.answer(S.resume, {'duplicate': True, 'artifact_sha': None, 'brief': None})
    out = rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert out == {'duplicate': True, 'artifact_sha': None, 'brief': None}
    assert 'launch' not in out
    assert rig.names() == ['resume'] and rig.term.opened == [] and rig.fa.launched == []


def test_the_brief_is_delivered_only_when_the_caller_asked_for_it(rig):
    """service.py:141 — `out['artifact_sha'] if deliver_brief else None`: a resume
    that did not ask for the brief writes no delivery copy even though the
    command produced one; asking for it puts those exact bytes in the copy."""
    path = rig.provider(rig.fa, 'ref-1')
    s = rig.session(transcript_path=path)
    sha = artifacts.put(b'THE BRIEF BYTES')
    rig.answer(S.resume, {'duplicate': False, 'artifact_sha': sha})
    rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert not os.path.exists(rig.delivery(s.id))            # not asked for: nothing delivered
    assert rig.fa.launched[-1].opening is None               # and no opening line pointing at it
    rig.service.resume(USER, session_id=s.id, request_id='r2', deliver_brief=True)
    with open(rig.delivery(s.id), 'rb') as f:
        assert f.read() == b'THE BRIEF BYTES'
    assert rig.delivery(s.id) in rig.fa.launched[-1].opening


def test_a_session_with_an_unparsable_start_still_resumes(rig):
    """service.py:230-236 — `_epoch` degrades a missing or malformed timestamp to
    0.0 instead of raising out of the world read in front of a resume."""
    assert SV._epoch('') == 0.0 and SV._epoch(None) == 0.0
    assert SV._epoch('yesterday') == 0.0
    assert SV._epoch(STARTED) > 0
    s = rig.session(provider_session_ref=None, started_at='not-a-timestamp')
    rig.fa.found = None
    with pytest.raises(SV.Refused):
        rig.service.resume(USER, session_id=s.id, request_id='r1')
    assert ('find', None, None, rig.cwd, 0.0) in rig.fa.asked


# ── hand-off ─────────────────────────────────────────────────────────────────

def test_a_handoff_of_a_mission_session_reads_no_transcript_at_all(rig):
    """service.py:149-156 — `if src.mission_id is None:` a hand-off is read-only
    on its source (invariant 6) and takes the transcript only for a session that
    continues no mission; a mission session's turns stay in the transcript."""
    s = rig.session(mission_id=ids.new_id('mission'), provider_session_ref='ref-1')
    rig.provider(rig.fa, 'ref-1', (('user', 'SECRET-LINE'),))
    tgt = rig.target()
    rig.answer(S.handoff, {'duplicate': False, 'id': tgt.id, 'handoff_artifact_sha': None})
    rig.service.handoff(USER, source_session_id=s.id, request_id='h1', harness_id='fake_b')
    assert rig.fa.kinds() == []                                # never located, never read
    assert rig.data(S.handoff)['turns'] is None


def test_a_handoff_carries_the_source_turns_read_by_the_source_adapter(rig):
    """service.py:153-156 — the turns come from the SOURCE harness's adapter,
    capped at 400, and only when both the adapter and the ref exist; a source
    whose harness is gone or which never had a ref hands over no turns rather
    than raising."""
    s = rig.session()
    rig.provider(rig.fa, 'ref-1', (('user', 'fix the login'),))
    tgt = rig.target()
    rig.answer(S.handoff, {'duplicate': False, 'id': tgt.id, 'handoff_artifact_sha': None})
    rig.service.handoff(USER, source_session_id=s.id, request_id='h1', harness_id='fake_b')
    assert ('turns', rig.fa.path('ref-1'), 400) in rig.fa.asked
    assert rig.data(S.handoff)['turns'] == [['user', 'fix the login']]
    assert rig.fb.launched[-1].session_id == tgt.id       # the target is launched, not the source
    for kw in ({'provider_session_ref': None}, {'harness_id': 'no_such_harness'}):
        src = rig.session(**kw)
        rig.writes.calls[:] = []
        rig.service.handoff(USER, source_session_id=src.id, request_id='h2', harness_id='fake_b')
        assert rig.data(S.handoff)['turns'] is None


def test_a_duplicate_handoff_launches_no_second_target(rig):
    """service.py:161-162 — `if out['duplicate']: return out` before the
    launcher: the replayed hand-off answer is returned as the command wrote it."""
    s = rig.session()
    rig.answer(S.handoff, {'duplicate': True, 'id': 'ses_target', 'handoff_artifact_sha': None})
    out = rig.service.handoff(USER, source_session_id=s.id, request_id='h1', harness_id='fake_b')
    assert out == {'duplicate': True, 'id': 'ses_target', 'handoff_artifact_sha': None}
    assert rig.names() == ['handoff'] and rig.term.opened == [] and rig.fb.launched == []


# ── the launcher ─────────────────────────────────────────────────────────────

def test_the_launch_that_loses_its_claim_opens_nothing_and_records_nothing(rig):
    """service.py:176-179 — `if not self._do(S.claim_launch, ...)['won']`: two
    requests carrying one launch, one terminal. The loser builds no argv, opens
    no terminal, writes no delivery copy and — the part a wrong `return` here
    would break — reports NO launch outcome for a launch it never owned."""
    s = rig.session(launch_seq=3)
    rig.answer(S.claim_launch, [{'won': True}, {'won': False}])
    first = rig.service._launch(s.id, None)
    assert first['launched'] and first['launch_seq'] == 3
    assert rig.data(S.claim_launch) == {'actor': SYSTEM, 'session_id': s.id, 'launch_seq': 3}
    rig.writes.calls[:], rig.term.opened[:] = [], []
    second = rig.service._launch(s.id, artifacts.put(b'BRIEF'))
    assert second == {'launched': False, 'reason': 'nothing to launch'}
    assert rig.names() == ['claim_launch'] and rig.term.opened == []
    assert rig.fb.launched == [] and rig.fa.launched[-1].opening is None
    assert not os.path.exists(rig.delivery(s.id))


def test_two_callers_ask_for_the_same_launch_and_one_terminal_opens(rig):
    """service.py:176-179 under two threads — the claim is what decides, so two
    callers on one session and one `launch_seq` produce exactly one argv, one
    terminal and one recorded outcome. Deterministic whatever the interleaving:
    the writer answers `won` once, and a loser has nothing to report."""
    s = rig.session(launch_seq=1)
    lock = threading.Lock()
    left = {'claims': 1}

    def claim():                                    # the machine's one-winner rule
        with lock:
            won = left['claims'] > 0
            left['claims'] -= 1
        return {'won': won}

    rig.answer(S.claim_launch, claim)
    barrier = threading.Barrier(2)
    results = []

    def ask():
        barrier.wait(5)
        results.append(rig.service._launch(s.id, None))

    threads = [threading.Thread(target=ask, name='caller-%d' % n) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(results) == 2                        # both callers got an answer
    assert sorted(r['launched'] for r in results) == [False, True]
    assert len(rig.calls(S.claim_launch)) == 2 and len(rig.calls(S.launched)) == 1
    assert len(rig.fa.launched) == 1 and len(rig.term.opened) == 1


def test_the_delivery_copy_is_written_once_and_never_overwritten(rig):
    """service.py:182-188 — `if not os.path.exists(path)`: the copy is a delivery
    (D15), never a rewrite; the user's file stands and the opening line still
    points at it, and the first copy holds the artifact's exact bytes."""
    s = rig.session(launch_seq=1)
    sha = artifacts.put(b'THE CONTEXT')
    rig.service._launch(s.id, sha, 'the context handed over')
    with open(rig.delivery(s.id), 'rb') as f:
        assert f.read() == b'THE CONTEXT'
    assert rig.fa.launched[-1].opening.startswith('Before anything else, read ')
    with open(rig.delivery(s.id), 'wb') as f:
        f.write(b'WHAT THE USER WROTE')
    rig.service._launch(s.id, sha, 'the context handed over')
    with open(rig.delivery(s.id), 'rb') as f:
        assert f.read() == b'WHAT THE USER WROTE'


def test_a_terminal_that_raises_is_reported_as_a_launch_and_never_raised(rig):
    """service.py:194-201 — `except Exception as e: got, err = None, ...`: a node
    that explodes does not fail the resume; the outcome is recorded as Core with
    the error text and no provider ref, and the caller is told it did not launch."""
    s = rig.session(launch_seq=2)
    rig.term.raises = OSError('no terminal for you')
    out = rig.service._launch(s.id)
    assert out == {'launched': False, 'error': 'OSError: no terminal for you', 'launch_seq': 2}
    assert rig.data(S.launched) == {'actor': SYSTEM, 'session_id': s.id, 'launch_seq': 2,
                                    'provider_session_ref': None,
                                    'error': 'OSError: no terminal for you'}


def test_a_node_that_reports_a_failure_settles_the_launch_without_raising(rig):
    """service.py:196-202 — the node's own `(proc, err)` answer rather than an
    exception: a reported failure is recorded as the launch's outcome (with the
    ref the harness will use) and handed back as `launched: False`, so the resume
    that asked for it still returns to its caller."""
    rig.provider(rig.fa, 'ref-1')
    s = rig.session(last_request='r1', launch_seq=4)
    rig.term.fail = 'the terminal would not open'
    out = rig.service._launch(s.id)
    assert out == {'launched': False, 'error': 'the terminal would not open', 'launch_seq': 4}
    assert rig.data(S.launched) == {'actor': SYSTEM, 'session_id': s.id, 'launch_seq': 4,
                                    'provider_session_ref': 'ref-1',
                                    'error': 'the terminal would not open'}
    assert len(rig.term.opened) == 1                        # the node was asked, and said no


def test_an_adapter_that_cannot_build_the_command_is_reported_the_same_way(rig):
    """service.py:194-199 — the same guard covers the adapter's own failure: the
    exception type and text become the launch error, and the recorded outcome
    settles the launch rather than leaving it claimed and unanswered."""
    s = rig.session(launch_seq=1)
    rig.fa.failed = ValueError('no argv for that model')
    out = rig.service._launch(s.id)
    assert out['error'] == 'ValueError: no argv for that model' and not out['launched']
    assert rig.data(S.launched)['error'] == 'ValueError: no argv for that model'
    assert rig.data(S.launched)['provider_session_ref'] is None


def test_only_a_session_that_was_resumed_is_launched_as_a_resume(rig):
    """service.py:191-193 — `resume_ref=s.provider_session_ref if s.last_request
    else None`: a session that was created and never resumed opens NEW, even
    though a provider ref is recorded; only a session whose last resume named a
    request reopens its own provider session."""
    fresh = rig.session(provider_session_ref='ref-1', last_request=None)
    rig.service._launch(fresh.id)
    assert rig.fa.launched[-1].resume_ref is None
    assert rig.data(S.launched)['provider_session_ref'] not in (None, 'ref-1')
    rig.writes.calls[:] = []
    resumed = rig.session(provider_session_ref='ref-2', last_request='r1', model='fake-large',
                          effort='high')
    rig.provider(rig.fa, 'ref-2')
    rig.service._launch(resumed.id)
    spec = rig.fa.launched[-1]
    assert (spec.resume_ref, spec.model, spec.effort, spec.cwd, spec.session_id) == (
        'ref-2', 'fake-large', 'high', rig.cwd, resumed.id)
    assert rig.data(S.launched)['provider_session_ref'] == 'ref-2'


def test_the_delivery_copy_lives_inside_the_project_and_grants_nothing(rig):
    """service.py:34-45 — `delivery_path` stays inside the project's `.archeus/
    sessions/` (the directory whose `.gitignore` is `*`), and `opening` names the
    copy, the session and the fact that it grants no permission."""
    path = SV.delivery_path(rig.cwd, 'ses_1')
    assert path == os.path.join(rig.cwd, '.archeus', 'sessions', 'ses_1.md')
    assert os.path.isdir(os.path.dirname(os.path.dirname(path)))
    text = SV.opening('ses_1', path, 'the brief')
    assert path in text and 'ses_1' in text and 'grants no permission' in text


# ── boot ─────────────────────────────────────────────────────────────────────

def test_the_sweep_moves_no_session_whose_harness_it_cannot_ask(rig):
    """service.py:216-218 — `if a is None or not a.discover().installed:
    continue`: a harness Core cannot ask is NOT evidence, so its OPEN session is
    left OPEN rather than vanished. The fail-open reading of an unknown harness
    (locate -> None -> LOST) is what this pins down."""
    kept = rig.session(harness_id='no_such_harness', state='OPEN')
    lost = rig.session(harness_id='fake_b', state='OPEN')
    rig.fb.installed = False
    rig.answer(S.expire_launches, {'expired': ['ses_x']})
    out = rig.service.sweep()
    assert out == {'expired': ['ses_x'], 'moved': []}
    assert rig.calls(S.vanished) == [] and rig.calls(S.reappeared) == []
    assert rig.fb.asked == [] and kept.state == 'OPEN' and lost.state == 'OPEN'


def test_the_sweep_asks_only_about_live_user_sessions_that_have_a_ref(rig):
    """service.py:210-213 — the three-part filter: a CLOSED session, a headless
    one and one with no provider ref are none of the sweep's business, so their
    adapters are never asked and nothing can move them."""
    closed = rig.session(state='CLOSED')
    headless = rig.session(mode='headless')
    nameless = rig.session(provider_session_ref=None)
    out = rig.service.sweep()
    assert out['moved'] == [] and rig.fa.asked == [] and rig.term.opened == []
    assert (closed.state, headless.state, nameless.state) == ('CLOSED', 'OPEN', 'OPEN')
    assert rig.names() == ['expire_launches']


def test_the_sweep_moves_a_session_only_in_the_two_directions_that_have_evidence(rig):
    """service.py:219-226 — OPEN + not found -> LOST (through `vanished`), LOST +
    found -> OPEN (through `reappeared`, with the transcript), and the other two
    combinations move nothing: an answer that agrees with the state records
    nothing."""
    gone = rig.session(state='OPEN', provider_session_ref='ref-gone')
    back = rig.session(state='LOST', provider_session_ref='ref-back')
    agrees_open = rig.session(state='OPEN', provider_session_ref='ref-here')
    agrees_lost = rig.session(state='LOST', provider_session_ref='ref-missing')
    rig.provider(rig.fa, 'ref-back')
    rig.provider(rig.fa, 'ref-here')
    out = rig.service.sweep()
    assert sorted(out['moved']) == sorted([(gone.id, 'LOST'), (back.id, 'OPEN')])
    assert [c.data['session_id'] for c in rig.calls(S.vanished)] == [gone.id]
    assert rig.calls(S.vanished)[0].data['actor'] == SYSTEM
    assert [c.data['session_id'] for c in rig.calls(S.reappeared)] == [back.id]
    assert rig.data(S.reappeared)['transcript_path'] == rig.fa.path('ref-back')


def test_a_session_the_sweep_moves_asks_no_launcher_and_opens_no_terminal(rig):
    """service.py:206-227 — the boot sweep settles and reports: it never launches
    what a previous Core was asked for (D21), so the node stays untouched and no
    launch outcome is recorded while a session changes state."""
    gone = rig.session(state='OPEN')
    rig.fa.located = None
    out = rig.service.sweep()
    assert out['moved'] == [(gone.id, 'LOST')] and rig.term.opened == []
    assert rig.fa.launched == [] and rig.calls(S.launched) == []
