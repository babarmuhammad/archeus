"""T-327: the highest-risk uncovered branches of `archeus/core/application/queries.py`
(query parameters, limits, redaction, unknown ids).

Style and fixtures follow tests/v1/unit/test_t144_stored_reads.py: every entity read is
faked on the one seam every query shares (`queries.rows`, the `archeus.infra.db.rows`
module) and the two raw `tokens` reads are answered by a connection double that honours
only the SQL clauses the query actually spells, so a clause dropped in the source
changes what the double answers. Nothing here opens a database, starts a process or
reads the OS: the only filesystem paths are the test's own `tmp_path` ones.
"""

import json
from types import SimpleNamespace

import pytest

from archeus.core.application import queries
from archeus.core.domain import entities, ids
from archeus.core.homes import Homes
from archeus.infra.artifacts import store
from archeus.infra.db.writer import NotFound
from archeus.infra.eventlog import outbox

HOME = 'C:/T327/Work-Claude'
KEY = 'h:' + HOME.lower()
AT = '2026-10-30T09:00:00.000Z'
MID = ids.new_id('mission')
OTHER_MID = ids.new_id('mission')
PLN = ids.new_id('plan')
OTHER_PLN = ids.new_id('plan')
TSK = ids.new_id('task')
VER_ID = ids.new_id('verification')
REV_ID = ids.new_id('review')
CNV = ids.new_id('conversation')
MSG = ids.new_id('message')
INT = ids.new_id('intent')
PRN = ids.new_id('principal')
DVC_A, DVC_B, DVC_C = (ids.new_id('device') for _ in range(3))
K_BASE, K_MID, K_NEXT = (ids.new_id('knowledge_item') for _ in range(3))
K_GONE_BACK, K_GONE_FWD = ids.new_id('knowledge_item'), ids.new_id('knowledge_item')
REL_OUT, REL_IN = ids.new_id('relation'), ids.new_id('relation')
SHA_A, SHA_B = 'a' * 64, 'b' * 64
PIN = 'pbkdf2$1000$00$0000000000000000000000=='


@pytest.fixture
def homes():
    return Homes([HOME], [('h', KEY, HOME)], shorts=lambda _: None, path_flavour='windows')


class Ent(SimpleNamespace):
    """An entity as the queries see it: a field bag plus the codec's `to_dict`."""

    def to_dict(self):
        return dict(vars(self))


def row(id_, at=AT, **fields):
    """An entity row: the fields the query reads plus the row metadata `view` adds."""
    return SimpleNamespace(entity=Ent(id=id_, **fields), version=1, created_at=at,
                           updated_at=at, created_by=PRN, updated_by=PRN)


class FakeRows:
    """`rows.get` / `rows.where` over in-memory rows, installed on the rows module
    every query (and `resources.homes`, and `commands.active_plan`) reads through."""

    def __init__(self, **tables):
        # keyed by the entity class, spelled by its name in each test
        self.tables = {(getattr(entities, k) if isinstance(k, str) else k): list(v)
                       for k, v in tables.items()}
        self.calls = []

    def get(self, conn, cls, entity_id):
        self.calls.append(('get', cls.__name__, entity_id))
        return next((r for r in self.tables.get(cls, ()) if r.entity.id == entity_id), None)

    def where(self, conn, cls, **eq):
        self.calls.append(('where', cls.__name__, dict(eq)))
        return [r for r in self.tables.get(cls, ())
                if all(getattr(r.entity, k, object()) == v for k, v in eq.items())]

    def install(self, monkeypatch):
        for name in ('get', 'where'):
            monkeypatch.setattr(queries.rows, name, getattr(self, name))
        return self


class Cursor:
    def __init__(self, got):
        self.got = got

    def fetchone(self):
        return self.got[0] if self.got else None

    def fetchall(self):
        return list(self.got)


class Tokens:
    """The raw `tokens` reads of `credential` and `devices`. The double filters on a
    clause only when the SQL under test contains it, so dropping `kind = 'device'` or
    `principal_id = ?` from the source changes the answer it gets."""

    def __init__(self, *tokens):
        self.tokens = [dict(t) for t in tokens]
        self.calls = []

    def execute(self, sql, params=()):
        params = tuple(params)
        self.calls.append((sql, params))
        got = [t for t in self.tokens if self._holds(sql, params, t)]
        if 'ORDER BY created_at DESC LIMIT 1' in sql:
            got = sorted(got, key=lambda t: t['created_at'], reverse=True)[:1]
        return Cursor(got)

    @staticmethod
    def _holds(sql, params, t):
        if 'token_hash = ?' in sql and t['token_hash'] != params[0]:
            return False
        if "kind = 'device'" in sql and t['kind'] != 'device':
            return False
        if 'principal_id = ?' in sql and t['principal_id'] != params[0]:
            return False
        return True


def device_token(hash, principal, *, created_at='2026-01-01', scopes='["observe"]',
                 expires_at='2027-01-01T00:00:00.000Z', kind='device', revoked_at=None):
    return {'token_hash': hash, 'principal_id': principal, 'kind': kind, 'scopes': scopes,
            'expires_at': expires_at, 'revoked_at': revoked_at, 'created_at': created_at}


# ── query parameters: an unknown filter value is refused, never read as "no rows" ──

BAD_FILTER = [
    ('missions', lambda c: queries.list_missions(c, 'NOT_A_STATE')),
    ('knowledge_state', lambda c: queries.list_knowledge(c, state='NOT_A_STATE')),
    ('knowledge_type', lambda c: queries.list_knowledge(c, type='NOT_A_TYPE')),
    ('ideas', lambda c: queries.list_ideas(c, 'NOT_A_STATE')),
    ('approvals', lambda c: queries.list_approvals(c, state='NOT_A_STATE')),
    ('policy_stage', lambda c: queries.list_policy_decisions(c, stage='NOT_A_STAGE')),
]


@pytest.mark.parametrize('name,call', BAD_FILTER, ids=[b[0] for b in BAD_FILTER])
def test_an_unknown_filter_value_is_refused_not_read_as_no_rows(name, call, monkeypatch):
    db = FakeRows(Mission=[row(MID, state='RUNNING')], KnowledgeItem=[], Idea=[],
                  Approval=[], PolicyDecision=[]).install(monkeypatch)
    with pytest.raises(ValueError):
        call(None)
    assert db.calls == []                      # it fails before reading anything


# ── unknown ids: NotFound, not an empty list and not a body built from None ────────

UNKNOWN_ID = [
    ('mission', lambda c, h: queries.get_mission(c, MID, homes=h)),
    ('verifications', lambda c, h: queries.list_verifications(c, MID, homes=h)),
    ('verification', lambda c, h: queries.get_verification(c, VER_ID, homes=h)),
    ('reviews', lambda c, h: queries.list_reviews(c, MID, homes=h)),
    ('context_package', lambda c, h: queries.get_context_package(
        c, ids.new_id('context_package'), homes=h)),
    ('knowledge', lambda c, h: queries.get_knowledge(c, K_MID)),
    ('route_decision', lambda c, h: queries.get_route_decision(c, ids.new_id('route_decision'),
                                                               homes=h)),
    ('account', lambda c, h: queries.get_account(c, ids.new_id('account'))),
    ('intent', lambda c, h: queries.get_intent(c, INT)),
    ('approval', lambda c, h: queries.get_approval(c, ids.new_id('approval'), homes=h)),
    ('policy_decision', lambda c, h: queries.get_policy_decision(c, ids.new_id('policy_decision'),
                                                                 homes=h)),
    ('plan', lambda c, h: queries.get_plan(c, PLN)),
    ('mission_plan', lambda c, h: queries.mission_plan(c, MID)),
    ('conversation', lambda c, h: queries.messages(c, CNV)),
    ('thread_mission', lambda c, h: queries.messages(c, MID)),
]


@pytest.mark.parametrize('name,call', UNKNOWN_ID, ids=[u[0] for u in UNKNOWN_ID])
def test_an_unknown_id_raises_instead_of_reading_as_no_rows(name, call, homes, monkeypatch):
    FakeRows().install(monkeypatch)            # an empty database answers every read
    with pytest.raises(NotFound):
        call(None, homes)


def test_an_unlisted_project_is_not_found_while_an_unfiltered_read_is_empty(monkeypatch):
    """`list_missions` fails closed on a project the user cannot have meant; a real
    project with no mission is the only thing that may answer `[]`."""
    FakeRows().install(monkeypatch)
    with pytest.raises(NotFound):
        queries.list_missions(None, project_id=ids.new_id('project'))


# ── verifications: only this mission's, whatever plan they sit under ───────────────

def _subject(kind, id_):
    return SimpleNamespace(kind=kind, id=id_)


def _verification(id_, subject, at, plan_id, **fields):
    return row(id_, at=at, subject=subject, plan_id=plan_id,
               checks=[{'name': 'tests', 'result': 'pass'}],
               criteria=[], performed_by={'account_ref': HOME, 'account_id': 'acc_registered'},
               **fields)


VERIFICATIONS = [
    _verification('ver_mine', _subject('mission', MID), '2026-10-30T09:00:02.000Z', PLN),
    _verification('ver_task', _subject('task', TSK), '2026-10-30T09:00:01.000Z', PLN),
    _verification('ver_other_mission', _subject('mission', OTHER_MID), AT, PLN),
    _verification('ver_other_task', _subject('task', ids.new_id('task')), AT, PLN),
    # the same mission's subject, recorded under another mission's plan: still not ours
    _verification('ver_other_plan', _subject('mission', MID), AT, OTHER_PLN),
]


def test_a_verification_of_another_mission_or_task_is_never_listed(homes, monkeypatch):
    db = FakeRows(Mission=[row(MID, state='RUNNING')],
                  Task=[row(TSK, mission_id=MID, plan_id=PLN, key='t1')],
                  Plan=[row(PLN, mission_id=MID, plan_version=1, state='APPROVED'),
                        row(OTHER_PLN, mission_id=OTHER_MID, plan_version=1,
                            state='APPROVED')],
                  Verification=VERIFICATIONS).install(monkeypatch)
    out = queries.list_verifications(None, MID, homes=homes)
    assert [v['id'] for v in out['verifications']] == ['ver_task', 'ver_mine']
    assert ('where', 'Verification', {'plan_id': OTHER_PLN}) not in db.calls
    # the private performer ref is gone, the account id stays (T-144)
    for v in out['verifications']:
        assert v['performed_by'] == {'account_id': 'acc_registered'}


def test_evidence_is_available_only_for_a_hash_whose_file_is_actually_there(
        homes, monkeypatch, tmp_path):
    present = tmp_path / 'present.bin'
    present.write_bytes(b'pass\n')
    absent = tmp_path / 'absent.bin'
    probed = []

    def path_for(sha, home=None):
        probed.append(sha)
        return str(present) if sha == SHA_A else str(absent)

    monkeypatch.setattr(store, 'path_for', path_for)
    FakeRows(Verification=[row(VER_ID, subject=_subject('mission', MID), checks=[
        {'name': 'tests', 'output_sha256': SHA_A},
        {'name': 'lint', 'output_sha256': SHA_B},
        {'name': 'review', 'output_sha256': None}])]).install(monkeypatch)
    out = queries.get_verification(None, VER_ID, homes=homes)
    assert [(e['check'], e['available']) for e in out['evidence']] == [
        ('tests', True), ('lint', False), ('review', False)]
    assert probed == [SHA_A, SHA_B]            # a missing hash is never sent to the store


# ── credentials and devices: nothing is invented, nothing secret is shown ──────────

def test_a_device_credential_never_reads_a_user_token_or_invents_a_device(monkeypatch):
    conn = Tokens(device_token(SHA_A, PRN, scopes='["observe","write"]'),
                  device_token(SHA_B, PRN, kind='user', created_at='2026-01-02'))
    db = FakeRows(Device=[row(DVC_A, principal_id=PRN, state='ACTIVE', origin='paired')])
    db.install(monkeypatch)

    got = queries.credential(conn, SHA_A)
    assert got == {'token_hash': SHA_A, 'principal_id': PRN, 'device_id': DVC_A,
                   'device_state': 'ACTIVE', 'device_origin': 'paired',
                   'scopes': ('observe', 'write'),
                   'expires_at': '2027-01-01T00:00:00.000Z', 'revoked_at': None}
    sql, params = conn.calls[0]
    assert 'token_hash = ?' in sql and "kind = 'device'" in sql
    assert params == (SHA_A,) and SHA_A not in sql        # bound, never interpolated

    assert queries.credential(conn, SHA_B) is None         # a user token is no credential
    assert queries.credential(conn, 'c' * 64) is None      # unknown hash
    db.tables[entities.Device] = []                        # its device was revoked away
    gone = queries.credential(conn, SHA_A)
    assert (gone['device_id'], gone['device_state'], gone['device_origin']) == (None,) * 3


def _device(id_, origin, platform, *, pin=None, client_type=None, at=AT, principal=PRN):
    return row(id_, at=at, principal_id=principal, name='n-' + id_, platform=platform,
               origin=origin, client_type=client_type, host_label=None, state='ACTIVE',
               pin_hash=pin)


def test_a_device_without_a_credential_has_no_scopes_and_shows_no_pin(monkeypatch):
    lonely = ids.new_id('principal')
    FakeRows(Device=[_device(DVC_A, 'local', 'web', at='2026-01-01'),
                     _device(DVC_B, 'paired', 'web', pin=PIN, at='2026-01-02'),
                     _device(DVC_C, 'paired', 'tui', at='2026-01-03', principal=lonely)]
                 ).install(monkeypatch)
    conn = Tokens(device_token('a' * 64, PRN, scopes='["observe"]', expires_at='E1',
                               created_at='2026-01-01'),
                  device_token('b' * 64, PRN, scopes='["observe","write"]', expires_at='E2',
                               created_at='2026-01-02'),
                  device_token('d' * 64, PRN, kind='user', created_at='2026-01-03'))

    a, b, c = queries.devices(conn)
    assert [d['id'] for d in (a, b, c)] == [DVC_A, DVC_B, DVC_C]      # (created_at, id)
    assert (a['capabilities']['step_up'], a['client_type']) == ('local', 'spa')
    assert b['capabilities']['step_up'] == 'pin'
    assert (c['capabilities']['step_up'], c['client_type']) == ('none', 'cli')
    assert (a['scopes'], a['expires_at']) == (['observe', 'write'], 'E2')   # newest token
    assert (c['scopes'], c['expires_at']) == ([], None)                     # no credential
    body = json.dumps([a, b, c])
    assert PIN not in body and 'a' * 64 not in body and 'd' * 64 not in body
    assert not {'pin_hash', 'token_hash'} & set(a)


# ── the event read: paging, the caller's limit, and no homes for an empty page ─────

class Envelope:
    def __init__(self, seq):
        self.seq = seq

    def to_envelope(self):
        return {'seq': self.seq, 'id': 'ev_%d' % self.seq, 'type': 'mission.state_changed',
                'at': AT, 'actor': {'kind': 'system', 'id': PRN}, 'cause_chain': [],
                'subject': {'kind': 'mission', 'id': MID},
                'scope': {'workspace': 'w', 'project': None}, 'visibility': 'user',
                'payload': {'reason': 'waiting on ' + HOME}}


FULL = [Envelope(s) for s in range(1, outbox.MAX_LIMIT + 1)]
TAIL = [Envelope(outbox.MAX_LIMIT + 1)]


def _paged(calls):
    def events_after(conn, cursor, *, limit):
        calls.append((cursor, limit))
        page = FULL if cursor == 0 else TAIL if cursor == outbox.MAX_LIMIT else []
        return page[:limit]
    return events_after


def test_events_pages_from_the_last_seq_read_and_stops_at_a_short_page(homes, monkeypatch):
    calls = []
    monkeypatch.setattr(outbox, 'events_after', _paged(calls))
    got = queries.events(None, 0, homes=homes)
    assert [e['seq'] for e in got] == list(range(1, outbox.MAX_LIMIT + 2))
    assert calls == [(0, outbox.MAX_LIMIT), (outbox.MAX_LIMIT, outbox.MAX_LIMIT)]
    assert got[0]['payload']['reason'] == 'waiting on its home'

    calls.clear()
    assert [e['seq'] for e in queries.events(None, 0, limit=3, homes=homes)] == [1, 2, 3]
    assert calls == [(0, 3)]                       # the caller's limit is one page, not a loop

    calls.clear()
    def never():
        pytest.fail('an empty page built homes')
    assert queries.events(None, outbox.MAX_LIMIT + 1, homes=never) == []
    assert calls == [(outbox.MAX_LIMIT + 1, outbox.MAX_LIMIT)]


# ── knowledge: a dangling supersession link ends the chain, relations read both ways

def test_a_dangling_supersession_link_ends_the_chain_instead_of_failing(monkeypatch):
    FakeRows(KnowledgeItem=[
        row(K_BASE, type='FACT', title='base', supersedes_id=K_GONE_BACK,
            superseded_by_id=K_MID),
        row(K_MID, type='FACT', title='mid', supersedes_id=K_BASE, superseded_by_id=K_NEXT),
        row(K_NEXT, type='FACT', title='next', supersedes_id=K_MID,
            superseded_by_id=K_GONE_FWD)],
        Relation=[
            row(REL_OUT, src_kind='knowledge_item', src_id=K_MID, dst_kind='mission',
                dst_id=MID),
            row(REL_IN, src_kind='mission', src_id=MID, dst_kind='knowledge_item',
                dst_id=K_MID)]).install(monkeypatch)
    out = queries.get_knowledge(None, K_MID)
    assert out['chain'] == [K_BASE, K_MID, K_NEXT]        # both dangling links broke out
    assert [r['id'] for r in out['relations']] == [REL_OUT, REL_IN]   # outgoing then incoming


# ── messages: a cursor is a cursor ────────────────────────────────────────────────

MESSAGES = [row('msg_%d' % i, conversation_id=CNV, author='user', body='m%d' % i)
            for i in (1, 2, 3)]


def test_an_unknown_after_cursor_is_not_found_while_an_empty_thread_is_empty(monkeypatch):
    FakeRows(Conversation=[row(CNV, kind='normal', mission_id=None)],
             Message=MESSAGES).install(monkeypatch)
    assert [m['id'] for m in queries.messages(None, CNV, after='msg_1')] == ['msg_2', 'msg_3']
    assert queries.messages(None, CNV, after='msg_3') == []       # after the last: nothing
    with pytest.raises(NotFound):
        queries.messages(None, CNV, after=ids.new_id('message'))  # a typo is not "everything"
    assert queries.messages(None, 'primary') == []   # no primary conversation yet: nothing


# ── the answer card only ever belongs to an intent that is waiting ─────────────────

def test_a_question_card_is_only_ever_the_reply_of_an_intent_waiting_for_an_answer(
        monkeypatch):
    intent = row(INT, message_id=MSG, resolution='clarification_requested')
    reply = row('msg_reply', conversation_id=CNV, author='archeus', in_reply_to=MSG)
    db = FakeRows(Intent=[intent], Message=[reply]).install(monkeypatch)
    assert queries.question_of(None, INT)['id'] == 'msg_reply'

    intent.entity.resolution = 'proposed'
    with pytest.raises(ValueError):
        queries.question_of(None, INT)
    intent.entity.resolution = 'clarification_requested'
    reply.entity.author = 'user'
    with pytest.raises(ValueError):
        queries.question_of(None, INT)          # the user's own message is not the card
    reply.entity.author = 'archeus'
    db.tables[entities.Message] = []
    with pytest.raises(ValueError):
        queries.question_of(None, INT)          # no reply yet


# ── provider terms: "we were never told" is an answer, not an omission ─────────────

def test_a_named_harness_with_no_answer_is_answered_unknown_not_left_out(monkeypatch):
    FakeRows(ProviderTerms=[row('claude', headless='yes', rotation='no', note='kept')]
             ).install(monkeypatch)
    got = queries.provider_terms(None, ('codex', 'claude', 'codex'))
    assert [g['id'] for g in got] == ['claude', 'codex']
    assert got[0]['note'] == 'kept' and got[0]['headless'] == 'yes'      # never overwritten
    assert got[1] == {'id': 'codex', 'headless': 'unknown', 'rotation': 'unknown', 'note': '',
                      'version': 0, 'created_at': None, 'updated_at': None}
    assert [g['id'] for g in queries.provider_terms(None)] == ['claude']


# ── homes: built from the connection when not given, built once when lazy ──────────

def test_a_lazy_homes_builder_is_called_once_and_its_result_is_the_projection(
        homes, monkeypatch):
    calls = []

    def builder():
        calls.append(1)
        return homes
    FakeRows(Mission=[row(MID, state='RUNNING')],
             Review=[row(REV_ID, mission_id=MID, summary=HOME, new_system_field=HOME)]
             ).install(monkeypatch)
    (out,) = queries.list_reviews(None, MID, homes=builder)['reviews']
    assert calls == [1]                                   # one read, one build
    assert out['summary'] == HOME                         # authored: kept byte for byte
    assert out['new_system_field'] == 'its home'


def test_a_read_with_no_homes_builds_them_from_the_connection_so_nothing_leaks(
        monkeypatch, tmp_path):
    home = str(tmp_path / 'account-home')
    conn = SimpleNamespace(homes_cache=None)
    FakeRows(Mission=[row(MID, state='RUNNING')],
             Review=[row(REV_ID, mission_id=MID, summary='ok', new_system_field=home)],
             Account=[row(ids.new_id('account'), home_ref=home)]).install(monkeypatch)
    (out,) = queries.list_reviews(conn, MID)['reviews']       # homes=None
    assert out['new_system_field'] == 'its home'          # built from the Account row
    assert out['summary'] == 'ok'


# ── search: the limit cuts each kind on its own; only the listed keys appear ────────

def test_search_cuts_each_kind_to_its_limit_and_shows_only_the_listed_keys(monkeypatch):
    missions = [row(ids.new_id('mission'), title='Alpha %d' % i, state='RUNNING',
                    home_ref=HOME) for i in range(5)]
    projects = [row(ids.new_id('project'), name='Alpha project')]
    knowledge = [row(ids.new_id('knowledge_item'), type='FACT', title='alpha note')]
    FakeRows(Mission=missions, Project=projects, KnowledgeItem=knowledge).install(monkeypatch)

    got = queries.search(None, 'ALPHA', limit=2)
    assert [m['title'] for m in got['missions']] == ['Alpha 0', 'Alpha 1']   # case ignored
    assert [p['id'] for p in got['projects']] == [projects[0].entity.id]
    assert [k['title'] for k in got['knowledge']] == ['alpha note']
    assert set(got['missions'][0]) == {'id', 'title', 'state', 'version'}
    assert set(got['projects'][0]) == {'id', 'name'} and set(got['knowledge'][0]) == {'id',
                                                                                       'title'}
    assert HOME not in json.dumps(got)                    # an unlisted field never appears
    assert len(queries.search(None, 'alpha')['missions']) == 5   # SEARCH_LIMIT cuts nothing
