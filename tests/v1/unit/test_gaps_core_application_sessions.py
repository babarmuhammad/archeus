"""T-714: the highest-risk branches of `archeus/core/application/sessions.py` no
test reached — the denial and fail-closed paths first, then the boundary values,
then the error paths (p12-design-gate §7, §9, §10.2, §14, §17).

What the suite already walks lives in tests/v1/integration/test_sessions.py (the
machine, one happy resume, the brief, a hand-off artifact, the boot sweep, one
two-threaded launch race) and in tests/v1/unit/test_gaps_core_sessions_service.py
(the service *around* these commands, on recording seams). What is asserted here
is the command layer itself, on the real database: who is refused by which gate
and what is NOT written when it is, and which cursor, sequence, lineage or
transcript a stale, repeated or hostile report may never move.

Nothing below runs a process, a thread or a network and nothing reads the OS, so
the file answers the same on Linux and Windows: the seams are the one writer,
the one reader and the `ARCHEUS_HOME` under `tmp_path` that tests/v1/conftest.py
already gives every V1 test. The style and the seeded-world helper are copied
from tests/v1/unit/test_gaps_core_application_executions.py (T-301); where a row
the schema itself would refuse is needed (a lineage whose parent is gone) the
missing row is simulated by swapping `archeus.infra.db.rows.get`, the seam
tests/v1/unit/test_t144_checkpoint_consumption.py uses, and that test says so.
"""

import pytest

from archeus.core.application import authorization, lifecycle, queries, sessions as S
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.artifacts import store as artifacts
from archeus.infra.db import Database, rows
from archeus.infra.eventlog import outbox

USER = Ref('user_device', ids.new_id('principal'))
SYSTEM = Ref('system', ids.new_id('principal'))

#: who may neither change a session (`_user`) nor claim to be Core (`_core`)
OTHERS = ('system', 'brain', 'agent', 'harness', 'web')
AT = '2026-11-01T09:00:00Z'
NO_SUCH = 'ses_01GONEGONEGONEGONEGONEGONE'


def _seed(tx, *, add, subject, actor):
    """One writer command: insert *add* (`{'kind', 'fields'}`) in the order
    given, so every foreign key exists before the row that needs it. The event
    is the record the writer asks of any mutation."""
    for r in add:
        cls = getattr(entities, r['kind'])
        tx.insert(cls(**r['fields']), actor=actor)
    tx.append(new_event('mission.updated', Ref(subject[0], subject[1]), actor, payload={},
                        workspace=ids.GLOBAL_WORKSPACE))


class World:
    """A real database with two projects, one mission of each, three accounts
    (one disabled, one of another harness), one plan, one task, two executions
    (one of them the hand-off's own predecessor), one context package and one
    headless session. Every session a test commands is added on top of that."""

    def __init__(self):
        self.db = Database.open()
        self.pid = ids.new_id('project')
        self.other_pid = ids.new_id('project')
        self.mid = ids.new_id('mission')
        self.other_mid = ids.new_id('mission')
        self.aid = ids.new_id('account')                 # fake_a, AVAILABLE
        self.off_aid = ids.new_id('account')             # fake_a, DISABLED
        self.b_aid = ids.new_id('account')               # fake_b, AVAILABLE
        self.tid = ids.new_id('task')
        self.plan_id = ids.new_id('plan')
        self.prev_eid = ids.new_id('execution')
        self.eid = ids.new_id('execution')
        self.prev_ses = ids.new_id('session')
        self.pkg = ids.new_id('context_package')
        self._attempt = 2                       # the two executions seeded below
        self.db.writer.execute(_seed, {'actor': SYSTEM, 'subject': ('mission', self.mid),
                                       'add': [
            {'kind': 'Project', 'fields': {'id': self.pid, 'workspace_id': ids.GLOBAL_WORKSPACE,
                                           'name': 'P'}},
            {'kind': 'Project', 'fields': {'id': self.other_pid,
                                           'workspace_id': ids.GLOBAL_WORKSPACE,
                                           'name': 'Other'}},
            {'kind': 'Mission', 'fields': {'id': self.mid, 'workspace_id': ids.GLOBAL_WORKSPACE,
                                           'project_id': self.pid, 'title': 'M',
                                           'objective': 'o'}},
            {'kind': 'Mission', 'fields': {'id': self.other_mid,
                                           'workspace_id': ids.GLOBAL_WORKSPACE,
                                           'project_id': self.other_pid, 'title': 'Other',
                                           'objective': 'o'}},
            {'kind': 'Account', 'fields': {'id': self.aid, 'harness_id': 'fake_a',
                                           'label': 'A', 'auth_kind': 'api_key',
                                           'health': 'AVAILABLE'}},
            {'kind': 'Account', 'fields': {'id': self.off_aid, 'harness_id': 'fake_a',
                                           'label': 'Off', 'auth_kind': 'api_key',
                                           'health': 'DISABLED'}},
            {'kind': 'Account', 'fields': {'id': self.b_aid, 'harness_id': 'fake_b',
                                           'label': 'B', 'auth_kind': 'api_key',
                                           'health': 'AVAILABLE'}},
            {'kind': 'Plan', 'fields': {'id': self.plan_id, 'mission_id': self.mid,
                                        'state': 'APPROVED'}},
            {'kind': 'Task', 'fields': {'id': self.tid, 'plan_id': self.plan_id,
                                        'mission_id': self.mid, 'key': 't1', 'title': 'T',
                                        'kind': 'code_change', 'state': 'RUNNING'}},
            {'kind': 'Session', 'fields': {'id': self.prev_ses, 'harness_id': 'fake_a',
                                           'workspace_id': ids.GLOBAL_WORKSPACE, 'cwd': 'w',
                                           'mode': 'headless', 'mission_id': self.mid,
                                           'project_id': self.pid, 'execution_id': self.prev_eid,
                                           'state': 'CLOSED', 'started_at': AT,
                                           'last_active_at': '2025-01-01T00:00:00Z'}},
            {'kind': 'Execution', 'fields': {'id': self.prev_eid, 'task_id': self.tid,
                                             'mission_id': self.mid, 'attempt': 1,
                                             'harness_id': 'fake_a',
                                             'session_id': self.prev_ses}},
            {'kind': 'Execution', 'fields': {'id': self.eid, 'task_id': self.tid,
                                             'mission_id': self.mid, 'attempt': 2,
                                             'harness_id': 'fake_a'}},
            {'kind': 'ContextPackage', 'fields': {'id': self.pkg,
                                                  'workspace_id': ids.GLOBAL_WORKSPACE,
                                                  'subject_kind': 'mission',
                                                  'subject_id': self.mid,
                                                  'project_id': self.pid, 'as_of_seq': 1}},
        ]})

    # ── the seams every one of these tests shares ───────────────────────────

    def do(self, command, who=USER, **kw):
        return self.db.writer.execute(command, dict(kw, actor=who))

    def row(self, cls, id_):
        with self.db.read() as r:
            return rows.get(r, cls, id_)

    def s(self, id_):
        return self.row(entities.Session, id_)

    def sessions(self):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, entities.Session)]

    def events(self, type_, subject_id=None):
        with self.db.read() as r:
            return [e for e in queries.events(r) if e['type'] == type_
                    and (subject_id is None or e['subject']['id'] == subject_id)]

    def session(self, **f):
        """A session row in exactly the state a test asks for, written by the
        same writer primitive a command uses (so the entity's own validation
        still judges it)."""
        f.setdefault('id', ids.new_id('session'))
        f.setdefault('harness_id', 'fake_a')
        f.setdefault('workspace_id', ids.GLOBAL_WORKSPACE)
        f.setdefault('cwd', 'w')
        f.setdefault('mode', 'manual')
        f.setdefault('state', 'OPEN')
        f.setdefault('started_at', AT)
        f.setdefault('last_active_at', AT)
        self.db.writer.execute(_seed, {'actor': SYSTEM, 'subject': ('mission', self.mid),
                                       'add': [{'kind': 'Session', 'fields': f}]})
        return f['id']

    def open(self, who=USER, **kw):
        kw.setdefault('harness_id', 'fake_a')
        kw.setdefault('cwd', 'w')
        kw.setdefault('mode', 'manual')
        return self.do(S.open_session, who=who, **kw)

    def execution(self, **f):
        self._attempt += 1
        f.setdefault('id', ids.new_id('execution'))
        f.setdefault('task_id', self.tid)
        f.setdefault('mission_id', self.mid)
        f.setdefault('attempt', self._attempt)
        self.db.writer.execute(_seed, {'actor': SYSTEM, 'subject': ('mission', self.mid),
                                       'add': [{'kind': 'Execution', 'fields': f}]})
        return f['id']

    def close(self):
        self.db.close()


@pytest.fixture
def world():
    made = []

    def make():
        w = World()
        made.append(w)
        return w
    yield make
    for w in made:
        w.close()


# ── denial first: only Core records what it observed of a session ───────────

def _core_case(w, name):
    return {'observe': ('observe', {'session_id': w.session()}),
            'launched': ('launched', {'session_id': w.session(launch_seq=1), 'launch_seq': 1}),
            'claim_launch': ('claim_launch', {'session_id': w.session(launch_seq=1),
                                              'launch_seq': 1}),
            'reappeared': ('reappeared', {'session_id': w.session(state='LOST')}),
            'expire_launches': ('expire_launches', {}),
            'headless_session': ('headless_session', {
                'execution': w.row(entities.Execution, w.eid).entity})}[name]


@pytest.mark.parametrize('cmd', ['observe', 'launched', 'claim_launch', 'reappeared',
                                 'expire_launches', 'headless_session'],
                         ids=['observe', 'launched', 'claim', 'reappeared', 'expire',
                              'headless'])
@pytest.mark.parametrize('kind', ['user_device', 'brain', 'agent', 'harness'],
                         ids=['user', 'brain', 'agent', 'harness'])
def test_only_core_records_what_it_observed_of_a_session(world, cmd, kind):
    """sessions.py:37-39 — `if actor.kind != 'system': raise NotPermitted`, the
    first line of every command in the `launched`/`observe`/`headless_session`
    group. Dropped, a user's own device — or any harness's agent, which is
    exactly who an adapter would be asked to report through — could mark its
    session seen again, settle or steal a launch, or write the headless session
    an execution owns, and each of those is what the boot sweep and the
    launcher trust without looking."""
    w = world()
    name, kw = _core_case(w, cmd)
    before = [(x.id, w.s(x.id).version) for x in w.sessions()]
    with pytest.raises(authorization.NotPermitted):
        w.do(getattr(S, name), who=Ref(kind, ids.new_id('principal')), **kw)
    assert [(x.id, w.s(x.id).version) for x in w.sessions()] == before
    assert w.events('session.observed') == []
    assert w.events('session.created') == []


@pytest.mark.parametrize('cmd', ['open_session', 'close', 'reopen', 'link', 'resume',
                                 'handoff'],
                         ids=['open', 'close', 'reopen', 'link', 'resume', 'handoff'])
@pytest.mark.parametrize('kind', OTHERS, ids=list(OTHERS))
def test_only_a_user_device_changes_a_session(world, cmd, kind):
    """sessions.py:32-34 — `if actor.kind != 'user_device': raise NotPermitted`,
    the first line of every command here. Past it Core (or any harness agent)
    could open a session for a person, close the one they are using, move its
    mission link, or spend a resume and the launch behind it — which is what
    hands a terminal to the caller."""
    w = world()
    sid = w.session()
    kw = {'open_session': {'harness_id': 'fake_a', 'cwd': 'w', 'mode': 'manual'},
          'close': {'session_id': sid}, 'reopen': {'session_id': sid},
          'link': {'session_id': sid, 'mission_id': None},
          'resume': {'session_id': sid, 'request_id': 'r1'},
          'handoff': {'source_session_id': sid, 'request_id': 'h1', 'harness_id': 'fake_a',
                      'turns': [['user', 'carry on']]}}[cmd]
    before = [(x.id, w.s(x.id).version) for x in w.sessions()]
    with pytest.raises(authorization.NotPermitted):
        w.do(getattr(S, cmd), who=Ref(kind, ids.new_id('principal')), **kw)
    assert [(x.id, w.s(x.id).version) for x in w.sessions()] == before
    for t in ('session.created', 'session.resumed', 'session.linked', 'session.state_changed',
             'session.handed_off'):
        assert w.events(t) == []


# ── the scope gates: a foreign mission, a foreign or disabled account ───────

def test_a_session_never_continues_a_mission_of_another_project(world):
    """sessions.py:56-58 — `if m.workspace_id != workspace_id or m.project_id !=
    project_id: raise NotPermitted`. The workspace half is walked by
    test_sessions.py:T04; the project half is not, and it is the one that costs
    a person their privacy: dropped, a session of one project is linked to a
    mission of another and every later brief, context package and hand-off
    artifact of that session carries the other project's work."""
    w = world()
    sid = w.open(project_id=w.pid, mission_id=w.mid)['id']
    with pytest.raises(authorization.NotPermitted):
        w.do(S.link, session_id=sid, mission_id=w.other_mid)
    assert w.s(sid).entity.mission_id == w.mid
    assert w.events('session.linked') == []
    n = len(w.sessions())
    created = len(w.events('session.created'))
    with pytest.raises(authorization.NotPermitted):
        w.open(project_id=w.pid, mission_id=w.other_mid)
    assert len(w.sessions()) == n                                  # refused before insert
    assert len(w.events('session.created')) == created


def test_linking_a_session_to_the_mission_it_already_continues_records_nothing(world):
    """sessions.py:176-177 — `if s.mission_id == mission_id: return view_of(s)`.
    Without it, re-opening the same mission from the screen writes a row in
    which nothing changed and records a `session.linked` event `from X to X`: the
    version, `updated_by` and the change groups of every later brief then report
    a change that never happened."""
    w = world()
    sid = w.open(project_id=w.pid, mission_id=w.mid)['id']
    row = w.s(sid)
    out = w.do(S.link, session_id=sid, mission_id=w.mid)
    assert out['mission_id'] == w.mid
    assert w.s(sid).version == row.version
    assert w.events('session.linked') == []
    # and a real re-link is recorded once
    w.do(S.link, session_id=sid, mission_id=None)
    assert [(e['payload']['from'], e['payload']['to'])
            for e in w.events('session.linked')] == [(w.mid, None)]


def test_a_disabled_account_is_refused_before_anything_is_written(world):
    """sessions.py:68-69 — `if a.health == 'DISABLED': raise ValueError`. With
    it dropped, an account the user turned off is written onto a new session and
    onto its `session.created` event, and the launcher then asks that very
    account for argv after the command committed."""
    w = world()
    with pytest.raises(ValueError, match='is disabled'):
        w.open(account_id=w.off_aid)
    sid = w.session(mission_id=None)
    n = len(w.sessions())
    with pytest.raises(ValueError, match='is disabled'):
        w.do(S.handoff, source_session_id=sid, request_id='h1', harness_id='fake_a',
             account_id=w.off_aid, turns=[['user', 'carry on']])
    assert len(w.sessions()) == n
    assert w.events('session.created') == [] and w.events('session.handed_off') == []


def test_an_account_of_another_harness_is_refused(world):
    """sessions.py:66-67 — `if a.harness_id != harness_id: raise ValueError`.
    Without it a fake_a session carries fake_b's account: the router and the
    breaker judge one harness, the launcher asks another, and the home the
    provider reads is the wrong provider's."""
    w = world()
    n = len(w.sessions())
    with pytest.raises(ValueError, match='is not a fake_a account'):
        w.open(account_id=w.b_aid)
    with pytest.raises(ValueError, match='is not a fake_b account'):
        w.open(harness_id='fake_b', account_id=w.aid)
    assert len(w.sessions()) == n


def test_a_session_is_refused_a_model_or_effort_the_harness_does_not_offer(world):
    """sessions.py:73-78 and 102-103: `if value and value not in offered: raise
    ValueError`, whether or not the session is launched. A registered session's model
    is later put on the terminal command line, so a value the adapter does not offer
    is refused at registration too, never kept verbatim (ADR-0022); one it offers is
    kept as given."""
    w = world()
    n = len(w.sessions())
    for launch in (True, False):
        with pytest.raises(ValueError, match='does not offer model'):
            w.open(model='no-such-model', models=('real-model',), launch=launch)
        with pytest.raises(ValueError, match='does not offer effort'):
            w.open(effort='ultra', efforts=('low', 'high'), launch=launch)
        with pytest.raises(ValueError, match='does not offer model'):
            w.open(model='anything', models=(), launch=launch)
    assert len(w.sessions()) == n and w.events('session.created') == []
    s = w.open(model='real-model', effort='low', models=('real-model',), efforts=('low', 'high'))
    assert (s['model'], s['effort']) == ('real-model', 'low')
    assert s['launch_seq'] == 0                                    # registered, not launched


# ── the fail-closed refusals of the commands themselves ─────────────────────

@pytest.mark.parametrize('turns', [None, [], ()], ids=['none', 'empty-list', 'empty-tuple'])
def test_a_session_that_continues_nothing_and_has_no_turns_hands_over_nothing(world, turns):
    """sessions.py:322-330 — the `else: raise IllegalTrigger` of the three-way
    hand-off. A target created past it would be launched on an artifact that
    says only 'this session continues no mission': the user is told to continue
    work Core cannot describe, and the artifact claims a continuity that was
    never there. An empty list and an empty tuple are the hostile form of the
    same thing — an adapter that read nothing must not look like a transcript."""
    w = world()
    sid = w.session(mission_id=None, project_id=w.pid)
    n = len(w.sessions())
    with pytest.raises(lifecycle.IllegalTrigger, match='nothing to hand over'):
        w.do(S.handoff, source_session_id=sid, request_id='h1', harness_id='fake_a',
             turns=turns)
    assert len(w.sessions()) == n
    assert w.events('session.created') == [] and w.events('session.handed_off') == []


def test_resuming_a_lost_session_is_refused_and_nothing_moves(world):
    """sessions.py:271-273 — `if s.state == 'LOST': raise IllegalTrigger`.
    Unreachable through the service (it refuses a missing provider session
    before the command and remounts a found one), so nothing tests it: past it a
    resume reopens a session whose provider transcript is gone, hands its caller
    a brief built on nothing and asks for a terminal on a dead ref."""
    w = world()
    sid = w.session(mission_id=w.mid)
    w.do(S.vanished, who=SYSTEM, session_id=sid, reason='the drive is gone')
    row = w.s(sid)
    assert row.entity.state == 'LOST'
    with pytest.raises(lifecycle.IllegalTrigger, match='provider session is gone'):
        w.do(S.resume, session_id=sid, request_id='r1')
    after = w.s(sid)
    assert (after.entity.state, after.entity.launch_seq, after.entity.last_request) == (
        'LOST', 0, None)
    assert after.version == row.version
    assert w.events('session.resumed') == []


@pytest.mark.parametrize('bad', ['', None], ids=['empty', 'none'])
def test_a_resume_or_a_hand_off_without_its_request_id_is_refused(world, bad):
    """sessions.py:262-263 and 305-306 — `if not request_id: raise ValueError`.
    The request id *is* the idempotency of both commands (D10): a resume
    compares `last_request` to it and a hand-off looks its target up by
    (source, request). An empty one makes every later resume from that session
    look like a replay of the first (so it is never launched), and every second
    hand-off from one source look like a duplicate of the first."""
    w = world()
    sid = w.session(mission_id=w.mid)
    other = w.session(mission_id=None)
    with pytest.raises(ValueError, match='names its request id'):
        w.do(S.resume, session_id=sid, request_id=bad)
    with pytest.raises(ValueError, match='names its request id'):
        w.do(S.handoff, source_session_id=other, request_id=bad, harness_id='fake_a',
             turns=[['user', 'carry on']])
    assert w.s(sid).version == 1 and w.s(other).version == 1
    assert w.events('session.resumed') == [] and w.events('session.handed_off') == []
    assert len(w.sessions()) == 3


# ── a launch settles once: reports and claims that change nothing ───────────

def test_a_launch_report_that_is_stale_or_already_settled_changes_nothing(world):
    """sessions.py:206-207 — both halves of `if launch_seq != s.launch_seq or
    s.launched_seq >= launch_seq: return view_of(s)`. A late report from the
    terminal of an older resume (the sequence half) would settle the *current*
    launch as if it had opened, so the user never gets the terminal they asked
    for; a replay of a settled one (the second half) overwrites what really
    happened with a later error, or with someone else's provider ref."""
    w = world()
    sid = w.session(launch_seq=2, launched_seq=0, provider_session_ref=None)
    stale = w.do(S.launched, who=SYSTEM, session_id=sid, launch_seq=1, error='old terminal',
                 provider_session_ref='ref-old')
    assert (stale['launched_seq'], stale['launch_error'], stale['provider_session_ref']) == (
        0, None, None)
    assert w.events('session.observed') == []
    good = w.do(S.launched, who=SYSTEM, session_id=sid, launch_seq=2, error=None,
                provider_session_ref='ref-2')
    assert (good['launched_seq'], good['launch_error'], good['provider_session_ref']) == (
        2, None, 'ref-2')
    replay = w.do(S.launched, who=SYSTEM, session_id=sid, launch_seq=2, error='boom',
                  provider_session_ref='ref-forged')
    assert (replay['launch_error'], replay['provider_session_ref']) == (None, 'ref-2')
    assert len(w.events('session.observed')) == 1


def test_exactly_one_request_claims_a_launch(world):
    """sessions.py:226-227 — both halves of `if launch_seq != s.launch_seq or
    max(s.launched_seq, s.launch_claimed_seq) >= launch_seq: return {'won':
    False}`. This is the one-terminal guarantee (T-116) on the real row: with
    `max` narrowed to `launched_seq` a duplicate resume opens a second terminal
    for one launch, and with the sequence test dropped a stale or forged claim
    spends a launch nobody asked for (and the boot sweep then never expires it)."""
    w = world()
    sid = w.session(launch_seq=2, launched_seq=0, launch_claimed_seq=0)
    assert w.do(S.claim_launch, who=SYSTEM, session_id=sid, launch_seq=2) == {'won': True}
    assert w.s(sid).entity.launch_claimed_seq == 2
    assert w.do(S.claim_launch, who=SYSTEM, session_id=sid, launch_seq=2) == {'won': False}
    assert w.do(S.claim_launch, who=SYSTEM, session_id=sid, launch_seq=1) == {'won': False}
    assert w.do(S.claim_launch, who=SYSTEM, session_id=sid, launch_seq=3) == {'won': False}
    assert w.s(sid).entity.launch_claimed_seq == 2                     # nothing moved
    assert len(w.events('session.observed')) == 1
    w.do(S.launched, who=SYSTEM, session_id=sid, launch_seq=2, error=None)
    assert w.do(S.claim_launch, who=SYSTEM, session_id=sid, launch_seq=2) == {'won': False}
    assert w.s(sid).entity.launch_claimed_seq == 2


def test_a_repeated_resume_changes_nothing_at_all(world):
    """sessions.py:265-266 — `if s.last_request == request_id: return dict(
    view_of(s), duplicate=True, brief=None, artifact_sha=None)`. That answer is
    what stops the service launching again; were the command to fall through,
    the replay would write a second brief artifact, move the cursor to head —
    erasing the changes the first resume had shown nobody — and spend a launch
    number, so the second request opens a terminal on a brief nobody was given."""
    w = world()
    sid = w.session(mission_id=w.mid)
    first = w.do(S.resume, session_id=sid, request_id='r1')
    assert first['duplicate'] is False and first['artifact_sha'] and first['brief']
    row = w.s(sid)
    again = w.do(S.resume, session_id=sid, request_id='r1')
    assert again['duplicate'] is True and again['brief'] is None
    assert again['artifact_sha'] is None
    after = w.s(sid)
    assert (after.entity.launch_seq, after.entity.last_seen_seq) == (1, first['last_seen_seq'])
    assert (after.entity.context_package_id, after.entity.last_request) == (
        first['context_package_id'], 'r1')
    assert after.version == row.version
    assert len(w.events('session.resumed')) == 1
    assert artifacts.get(first['artifact_sha'])              # exactly one brief, and readable


# ── what Core observed is recorded once, never overwritten ─────────────────

def test_what_core_observed_is_recorded_once_and_never_overwritten(world):
    """sessions.py:189-192 — `if provider_session_ref and not s.provider_session_ref`
    against `if transcript_path and transcript_path != s.transcript_path`: the
    ref is written once and by no one again, the path follows what is on disk.
    With the ref guard dropped, any later guess by Core re-points the session at
    another provider conversation and the next resume opens *that* transcript in
    the user's own window."""
    w = world()
    sid = w.session(provider_session_ref=None, transcript_path=None)
    out = w.do(S.observe, who=SYSTEM, session_id=sid, provider_session_ref='ref-1',
               transcript_path='t/one.jsonl')
    assert out['provider_session_ref'] == 'ref-1'
    assert 'transcript_path' not in out                            # stays inside Core
    assert w.s(sid).entity.transcript_path == 't/one.jsonl'
    again = w.do(S.observe, who=SYSTEM, session_id=sid, provider_session_ref='ref-forged',
                 transcript_path='t/two.jsonl')
    assert again['provider_session_ref'] == 'ref-1'
    assert w.s(sid).entity.transcript_path == 't/two.jsonl'
    assert len(w.events('session.observed')) == 2
    quiet = w.do(S.observe, who=SYSTEM, session_id=sid, provider_session_ref='x',
                 transcript_path='t/two.jsonl')
    assert quiet['provider_session_ref'] == 'ref-1'
    assert len(w.events('session.observed')) == 2                  # nothing to record
    assert w.s(sid).version == 3                                   # 1 + the two recorded moves


@pytest.mark.parametrize('given,kept', [(None, 't/one.jsonl'), ('t/two.jsonl', 't/two.jsonl')],
                         ids=['none-kept', 'given-wins'])
def test_reappearing_keeps_the_transcript_core_already_found(world, given, kept):
    """sessions.py:166-167 — `{'transcript_path': transcript_path or
    s.transcript_path}`. With `or s.transcript_path` dropped, a session found
    again after a remounted drive is recorded as having no transcript at all,
    and the next sweep calls it vanished again for a file that is only unread
    from a blank field."""
    w = world()
    sid = w.session(state='LOST', transcript_path='t/one.jsonl')
    out = w.do(S.reappeared, who=SYSTEM, session_id=sid, transcript_path=given)
    assert out['state'] == 'OPEN' and 'transcript_path' not in out
    assert w.s(sid).entity.transcript_path == kept


def test_the_boot_sweep_expires_only_a_launch_never_settled(world):
    """sessions.py:240-245 — `if s.launch_seq > s.launched_seq:` inside
    `expire_launches`. Fired on every session it stamps `launch_error` and a
    `session.observed` onto sessions whose terminal opened fine and reports them
    to whoever boots Core as expired; with the guard dropped, a restarted Core
    re-settles — and so, through the service's own retry, replays — launches
    that are already answered (D21)."""
    w = world()
    pending = w.session(launch_seq=1, launched_seq=0)
    settled = w.session(launch_seq=1, launched_seq=1)
    never_asked = w.session()
    half = w.session(launch_seq=3, launched_seq=2)
    out = w.do(S.expire_launches, who=SYSTEM)
    assert sorted(out['expired']) == sorted([pending, half])
    assert w.s(pending).entity.launch_error == 'launch_expired'
    assert w.s(pending).entity.launched_seq == 1
    assert w.s(half).entity.launch_error == 'launch_expired'
    assert w.s(half).entity.launched_seq == 3                        # settled at its own number
    assert w.s(settled).entity.launch_error is None                # opened: nothing to say
    assert w.s(never_asked).entity.launch_error is None
    assert len(w.events('session.observed')) == 2
    assert w.do(S.expire_launches, who=SYSTEM) == {'expired': []}  # the sweep, twice
    assert len(w.events('session.observed')) == 2                  # and it wrote nothing again


# ── the headless session an execution ran in ───────────────────────────────

def test_the_session_an_execution_ran_in_is_written_and_closed_in_one_transaction(world):
    """sessions.py:123-136 — the `or` fallbacks (124 `execution.harness_id or
    'unknown'`, 125 `execution.workdir or '.'`, 129 `execution.started_at or
    _now()`), the close fired in the same transaction (135) and the execution
    told its own session (136). Without the close a session an execution owned
    stays OPEN and anyone could resume a dead run; without 136 nothing finds the
    record again; without the fallbacks the row is written with NULLs no reader
    is prepared for."""
    w = world()
    eid = w.execution(harness_id=None, workdir=None, started_at=None, model='m', effort='e',
                      account_id=w.aid, handoff_from=w.prev_eid)
    out = w.do(S.headless_session, who=SYSTEM, execution=w.row(entities.Execution, eid).entity,
               provider_session_ref='ref-h')
    s = w.s(out['id'])
    assert (s.entity.mode, s.entity.state, s.entity.execution_id) == ('headless', 'CLOSED', eid)
    assert s.entity.harness_id == 'unknown' and s.entity.cwd == '.'
    assert (s.entity.model, s.entity.effort, s.entity.account_id) == ('m', 'e', w.aid)
    assert (s.entity.mission_id, s.entity.project_id) == (w.mid, w.pid)
    assert s.entity.started_at and s.entity.last_active_at          # both filled, not NULL
    assert s.entity.handoff_from_session_id == w.prev_ses           # the hand-off's own session
    assert s.entity.launch_seq == 0 and s.entity.closed_reason == 'execution ended'
    assert w.row(entities.Execution, eid).entity.session_id == out['id']
    assert len(w.events('session.created')) == 1
    assert [(e['payload']['from'], e['payload']['to']) for e in
            w.events('session.state_changed')] == [('OPEN', 'CLOSED')]
    assert out['transcript_path'] is None        # nothing of the transcript is claimed


@pytest.mark.parametrize('predecessor', ['no-record', 'gone-row'], ids=['no-record', 'gone-row'])
def test_a_head_off_line_that_leads_nowhere_is_recorded_as_no_line(world, predecessor):
    """sessions.py:121-122 — `prev = tx.get(entities.Execution, execution.handoff_from);
    source = prev.entity.session_id if prev else None`. Either way the line must
    not be invented: a headless session shown as continuing a session nobody can
    read is a lineage the user is told to trust that was never there. The
    `gone-row` id is well-formed and simply has no row, which is what a pruned
    or never-written predecessor looks like."""
    w = world()
    if predecessor == 'no-record':
        bare = w.execution()                                        # never ran a session
        eid = w.execution(handoff_from=bare)
    else:
        eid = w.execution(handoff_from=ids.new_id('execution'))
    out = w.do(S.headless_session, who=SYSTEM, execution=w.row(entities.Execution, eid).entity,
               provider_session_ref=None)
    assert w.s(out['id']).entity.handoff_from_session_id is None
    assert [e['payload']['handoff_from'] for e in w.events('session.created')] == [None]


def test_no_view_of_a_session_shows_the_transcript_or_an_unsettled_claim(world):
    """sessions.py:355-356 — the two `pop`s of `view_of`. The transcript path is
    a file on the owner's disk and `launch_claimed_seq` is an internal race
    token (T-116): either reaching the API tells a caller something they can act
    on — which private file to read, which launch is still unclaimed."""
    w = world()
    sid = w.session(transcript_path='t/private.jsonl', launch_seq=2, launch_claimed_seq=1,
                    provider_session_ref='ref-1')
    with w.db.read() as r:
        out = S.view(r, sid)
        listed = [s for s in S.listing(r) if s['id'] == sid]
    assert 'transcript_path' not in out and 'launch_claimed_seq' not in out
    assert out['provider_session_ref'] == 'ref-1' and out['version'] == 1
    assert listed and 'transcript_path' not in listed[0]
    assert 'launch_claimed_seq' not in listed[0]


# ── the reads: lineage depth, a gone parent, the listing, the preview ──────

def test_a_lineage_that_never_ends_is_walked_fifty_deep_and_no_further(world):
    """sessions.py:370 — `while cur.handoff_from_session_id is not None and
    len(lineage) < 50:`. The bound is all that stands between a long (or, since
    nothing here forbids a cycle among these rows, a circular) hand-off chain
    and a read that never answers; dropped, `view` spins instead of answering 50
    links, and the request that called it holds a read transaction forever."""
    w = world()
    chain, to_add = [], []
    for _ in range(60):
        parent = chain[-1] if chain else None
        sid = ids.new_id('session')
        to_add.append({'kind': 'Session', 'fields': {
            'id': sid, 'harness_id': 'fake_a', 'workspace_id': ids.GLOBAL_WORKSPACE,
            'cwd': 'w', 'mode': 'manual', 'state': 'OPEN', 'started_at': AT,
            'last_active_at': AT, 'handoff_from_session_id': parent}})
        chain.append(sid)
    w.db.writer.execute(_seed, {'actor': SYSTEM, 'subject': ('mission', w.mid),
                                'add': to_add})
    with w.db.read() as r:
        out = S.view(r, chain[-1])
    assert len(out['lineage']) == 50
    assert out['lineage'][0] == chain[-2] and out['lineage'][-1] == chain[9]


def test_a_lineage_that_names_a_row_that_is_gone_stops_there(world, monkeypatch):
    """sessions.py:372-374 — `prev = rows.get(...); if prev is None: break`.
    Without the break the walk reads `.entity` off None and the read dies on a
    session whose source has been pruned; and it must stop *with* the link it
    still has, not answer a shorter lineage than there is. A session row whose
    parent key is missing cannot be written (the sessions table refuses the
    key), so the missing parent is simulated at the read seam, the way
    tests/v1/unit/test_t144_checkpoint_consumption.py does."""
    w = world()
    a = w.session()
    b = w.session(handoff_from_session_id=a)
    real = rows.get

    def gone(conn, cls, id_):
        return None if (cls is entities.Session and id_ == a) else real(conn, cls, id_)
    monkeypatch.setattr('archeus.infra.db.rows.get', gone)
    with w.db.read() as r:
        out = S.view(r, b)
    assert out['lineage'] == [a]


def test_the_listing_answers_a_blank_clock_and_filters_on_every_key(world):
    """sessions.py:382-385 — the `if v is not None` of the filter comprehension
    and `key=lambda s: (s.last_active_at or '', s.id), reverse=True`. Drop the
    `is not None` and `listing(conn)` becomes a listing of nothing (every filter
    compares to None); drop `or ''` and the sort raises TypeError on a session
    that has never been active, which is every session registered but never
    resumed — the exact list a user opens the screen for."""
    w = world()
    old = w.session(last_active_at='2026-01-01T00:00:00Z', state='OPEN', project_id=w.pid,
                    mission_id=w.mid)
    new = w.session(last_active_at='2026-06-01T00:00:00Z', state='CLOSED', project_id=w.pid,
                    mission_id=w.mid)
    blank = w.session(last_active_at=None, state='OPEN', project_id=w.other_pid)
    twin = w.session(last_active_at='2026-06-01T00:00:00Z', state='OPEN', project_id=w.pid)
    with w.db.read() as r:
        assert [s['id'] for s in S.listing(r)] == [twin, new, old, w.prev_ses, blank]
        assert [s['id'] for s in S.listing(r, state='CLOSED')] == [new, w.prev_ses]
        assert [s['id'] for s in S.listing(r, project_id=w.other_pid)] == [blank]
        assert [s['id'] for s in S.listing(r, project_id=w.pid, state='CLOSED')] == [
            new, w.prev_ses]
        assert [s['id'] for s in S.listing(r, mission_id=w.mid)] == [new, old, w.prev_ses]
        assert S.listing(r, mission_id=ids.new_id('mission')) == []


def test_a_preview_of_a_package_that_is_gone_is_still_answered(world):
    """sessions.py:398-401 — `if s.context_package_id is not None:` and the inner
    `if p is not None:`. A session whose package has been pruned, or which never
    had one, must be answered with the empty context (exactly the shape
    `continuity.package()` gives a session that continues nothing) and not by a
    crash on `None`; the read must not go looking for a key it knows it does not
    hold; and it must record nothing of its own (it is the read the screen
    calls, and the cursor must not move)."""
    w = world()
    live = w.session(mission_id=w.mid, context_package_id=w.pkg)
    missing_pkg = ids.new_id('context_package')            # well-formed, and no row
    gone = w.session(mission_id=w.mid, context_package_id=missing_pkg)
    none = w.session(mission_id=w.mid, context_package_id=None)
    seen = []
    real = rows.get

    def spying(conn, cls, id_):
        seen.append((cls.__name__, id_))
        return real(conn, cls, id_)
    rows.get = spying
    try:
        with w.db.read() as r:
            head = outbox.head(r)
            b = S.preview_brief(r, live)
            assert b['context']['package_id'] == w.pkg and b['context']['fresh'] in (True, False)
            assert b['as_of_seq'] == head and b['missing'] == [] and b['mission']['id'] == w.mid
            b2 = S.preview_brief(r, gone)
            assert b2['context'] == {'package_id': None, 'as_of_seq': None, 'rebuilt': False}
            assert b2['mission']['id'] == w.mid
            assert S.preview_brief(r, none)['context'] == b2['context']   # the same shape
            assert ('ContextPackage', None) not in seen    # it never looks for a key it does not
    finally:
        rows.get = real
    with w.db.read() as r:
        assert w.s(gone).entity.context_package_id == missing_pkg          # fixes nothing
        assert w.s(live).version == 1 and w.s(none).version == 1
        with pytest.raises(lifecycle.NotFound):
            S.preview_brief(r, NO_SUCH)


# ── the error paths: no such mode, no such row, no such edge ───────────────

@pytest.mark.parametrize('mode', ['headless', 'auto', '', None, 'MANUAL'],
                         ids=['headless', 'auto', 'empty', 'none', 'case'])
def test_a_user_registers_or_launches_only_a_manual_or_interactive_session(world, mode):
    """sessions.py:91-92 — `if mode not in ('manual', 'interactive_attached'):
    raise ValueError`. A user must not register the mode only an execution's end
    writes (`headless`, which `entities.Session._check` binds to an execution id
    the caller would not have) or invent one no machine edge knows, because a
    resume, a close or a sweep of that session would then be judged against
    nothing."""
    w = world()
    n = len(w.sessions())
    with pytest.raises(ValueError, match='manual or interactive'):
        w.open(mode=mode)
    assert len(w.sessions()) == n and w.events('session.created') == []


def test_an_unknown_project_is_never_taken_for_a_session(world):
    """sessions.py:93-94 (`if project_id is not None: lifecycle.load(...)`) and
    95-96 (the same for the mission, through `_mission_in_scope`'s load at
    55). Dropped, a session is written under a project that does not exist: its
    brief then reports no mission and no changes forever, and the project filter
    of `listing` never returns it to the person who owns it."""
    w = world()
    n = len(w.sessions())
    with pytest.raises(lifecycle.NotFound):
        w.open(project_id=ids.new_id('project'))
    with pytest.raises(lifecycle.NotFound):
        w.open(project_id=w.pid, mission_id=ids.new_id('mission'))
    assert len(w.sessions()) == n and w.events('session.created') == []


@pytest.mark.parametrize('cmd', ['close', 'reopen', 'vanished', 'observe', 'launched',
                                 'claim_launch', 'resume', 'link'],
                         ids=['close', 'reopen', 'vanished', 'observe', 'launched', 'claim',
                              'resume', 'link'])
def test_a_command_of_a_session_that_is_not_there_says_so(world, cmd):
    """The `lifecycle.load(tx, entities.Session, session_id)` of every command
    (144, 151, 159, 165, 173, 187, 205, 225, 264) reaching `lifecycle.load`'s
    `if row is None: raise NotFound` (lifecycle.py:68-70). A command that
    answered None instead would go on to record a `session.*` event about a
    session that does not exist — and the reads would show a phantom."""
    w = world()
    kw = {'close': {'session_id': NO_SUCH},
          'reopen': {'session_id': NO_SUCH},
          'vanished': {'session_id': NO_SUCH, 'reason': 'gone'},
          'observe': {'session_id': NO_SUCH, 'provider_session_ref': 'ref'},
          'launched': {'session_id': NO_SUCH, 'launch_seq': 1},
          'claim_launch': {'session_id': NO_SUCH, 'launch_seq': 1},
          'resume': {'session_id': NO_SUCH, 'request_id': 'r1'},
          'link': {'session_id': NO_SUCH, 'mission_id': w.mid}}[cmd]
    who = SYSTEM if cmd in ('vanished', 'observe', 'launched', 'claim_launch') else USER
    with pytest.raises(lifecycle.NotFound):
        w.do(getattr(S, cmd), who=who, **kw)
    assert w.events('session.created') == [] and w.events('session.observed') == []
    assert len(w.sessions()) == 1


@pytest.mark.parametrize('cmd,state', [('close', 'CLOSED'), ('reopen', 'OPEN'),
                                       ('vanished', 'CLOSED'), ('reappeared', 'OPEN')],
                         ids=['close-closed', 'reopen-open', 'vanished-closed',
                              'reappeared-open'])
def test_a_transition_the_machine_has_no_edge_for_is_refused(world, cmd, state):
    """sessions.py:47-50 (`_fire` -> `lifecycle.fire` -> `resolve`, which raises
    IllegalTrigger for a state with no such edge, states.py:210-216): close from
    CLOSED, reopen from OPEN, vanish a CLOSED session, "find" an OPEN one.
    Answered as a no-op instead of a refusal, a second close would rewrite
    `closed_reason` and a second reopen clear it, each recording a state change
    that never happened."""
    w = world()
    sid = w.session(state=state)
    kw = {'session_id': sid}
    if cmd in ('close', 'vanished'):
        kw['reason'] = 'again'
    if cmd == 'reappeared':
        kw['transcript_path'] = 't/new.jsonl'
    who = SYSTEM if cmd in ('vanished', 'reappeared') else USER
    with pytest.raises(lifecycle.IllegalTrigger):
        w.do(getattr(S, cmd), who=who, **kw)
    assert w.s(sid).version == 1 and w.s(sid).entity.state == state
    assert w.s(sid).entity.transcript_path is None
    assert w.events('session.state_changed') == []


def test_a_hand_off_of_a_mission_source_never_reads_a_transcript(world):
    """sessions.py:318-326 — the `if src.mission_id is not None:` branch, and so
    the `elif turns:` under it. A session that continues a mission is handed
    over as current state read from the rows; the caller's `turns` must be
    ignored there, or a caller could put its own words into the artifact of a
    session that continues real work (and the source row stays untouched,
    ADR-0023)."""
    w = world()
    sid = w.session(mission_id=w.mid)
    out = w.do(S.handoff, source_session_id=sid, request_id='h1', harness_id='fake_a',
               turns=[['user', 'FORGED LINE OF A TRANSCRIPT']])
    assert out['duplicate'] is False and out['handoff_from_session_id'] == sid
    assert (out['launch_seq'], out['launched_seq'], out['mode']) == (1, 0, 'interactive_attached')
    text = artifacts.get(out['handoff_artifact_sha']).decode('utf-8')
    assert 'FORGED LINE OF A TRANSCRIPT' not in text and w.mid in text
    assert w.s(sid).version == 1                                   # the source is not written
    assert [(e['payload']['from'], e['payload']['to']) for e in
            w.events('session.handed_off')] == [(sid, out['id'])]
