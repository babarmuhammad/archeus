"""T-758: the ten highest-risk uncovered branches of
archeus/core/application/optins.py, as unit tests.

Denial and fail-closed paths first (who may write an opt-in at all, the two
optimistic-concurrency refusals, the write-free opt-out of what never existed,
the owner-scoped find, the exact scope of the recording event), then the
boundary values (the owner-id namespace, absent owners, what `effective`
includes and orders), then the error paths (a refused value must roll the
whole command back, event included). Same style and seams as the module's
closest unit tests (test_settings_sources_units.py) and the earlier gap files
(test_gaps_core_application_resources.py): the real database on the test's own
ARCHEUS_HOME from tests/v1/conftest.py, commands through the real writer, and
no OS at all — no process, no network, no sleep, no filesystem beyond the
fixture-owned database, nothing that reads the platform.
"""

import json

import pytest

from archeus.core.application import commands, lifecycle, optins
from archeus.core.application.authorization import NotPermitted
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import PRINCIPAL_SCOPES, Ref
from archeus.infra.db import Database, rows
from archeus.infra.db.writer import IdempotencyConflict


@pytest.fixture
def db():
    d = Database.open()
    yield d
    d.close()


def principal(db, kind):
    """A registered principal of *kind* as an actor Ref (what the commands take)."""
    pid = db.writer.execute(commands.register_principal, {
        'kind': kind, 'scopes': list(PRINCIPAL_SCOPES[kind])})['id']
    return Ref(kind, pid)


@pytest.fixture
def user(db):
    return principal(db, 'user_device')


def account(db, actor, label='A'):
    """One registered Account row, written through the writer like every command."""
    aid = ids.new_id('account')

    def run(tx):
        tx.insert(entities.Account(id=aid, harness_id='fake', label=label,
                                   auth_kind='api_key'), actor=actor)
        tx.append(new_event('account.registered', Ref('account', aid), actor,
                            payload={'harness_id': 'fake', 'label': label,
                                     'auth_kind': 'api_key'}))
    db.writer.execute(run, {})
    return aid


def project(db, actor, name='p', workspace_id=None):
    """One registered Project row (no repositories: discovery is the world
    worker's, and nothing in opt-ins reads it)."""
    pid = ids.new_id('project')
    ws = ids.GLOBAL_WORKSPACE if workspace_id is None else workspace_id

    def run(tx):
        tx.insert(entities.Project(id=pid, workspace_id=ws, name=name,
                                   root_paths=()), actor=actor)
        tx.append(new_event('project.created', Ref('project', pid), actor,
                            payload={'name': name, 'repositories': 0},
                            workspace=ws, project=pid))
    db.writer.execute(run, {})
    return pid


def opt(db, actor, owner_id, kind, name, opted_in, **kw):
    """The command exactly as the routes give it: through the one writer."""
    return db.writer.execute(optins.set_opt_in, dict(
        actor=actor, owner_id=owner_id, kind=kind, name=name, opted_in=opted_in, **kw))


def opt_rows(db, **eq):
    with db.read() as r:
        return rows.where(r, entities.OptIn, **eq)


def recorded_events(db, type_='opt_in.changed'):
    """The stored events of one type, envelope columns and raw payload: what
    the command appended, not a projection of it."""
    with db.read() as r:
        return [dict(rec, payload=json.loads(rec['payload']),
                     cause_chain=json.loads(rec['cause_chain']))
                for rec in r.execute('SELECT * FROM events ORDER BY seq').fetchall()
                if rec['type'] == type_]


# ── 1. optins.py:42-44 — only a user device may write an opt-in ─────────────

def test_only_a_user_device_may_opt_a_source_plugin_or_mcp_server(db, user):
    """optins.py:42-44 — `if actor.kind != 'user_device': raise A.NotPermitted`.
    Were the gate removed or `kind` read from the wrong place, every one of the
    refusals below would instead insert its row (or flip one), and the account
    or project would load hooks, plugins and MCP servers its user never
    allowed. The last two assertions pin the order too: permission is judged
    before existence, so a stranger gets no id-probe oracle either."""
    acc = account(db, user)
    for kind in ('system', 'brain', 'execution', 'automation', 'node'):
        with pytest.raises(NotPermitted, match='only a user device'):
            opt(db, principal(db, kind), acc, 'mcp', 'gh', True)
    with pytest.raises(NotPermitted, match='only a user device'):     # not even a principal kind
        opt(db, Ref('user', ids.new_id('principal')), acc, 'mcp', 'gh', True)
    with pytest.raises(NotPermitted, match='only a user device'):     # the opt-out side too
        opt(db, principal(db, 'brain'), acc, 'mcp', 'gh', False)
    assert opt_rows(db) == [] and recorded_events(db) == []
    with pytest.raises(NotPermitted):                                  # before _owner, not after
        opt(db, principal(db, 'system'), ids.new_id('account'), 'mcp', 'gh', True)
    assert opt(db, user, acc, 'mcp', 'gh', True)['changed'] is True    # the user may


# ── 2. optins.py:53-56 — even the write-free answer checks the version ──────

def test_asking_for_what_already_holds_with_the_wrong_version_is_refused(db, user):
    """optins.py:54-55 — `if expected_version is not None and expected_version
    != row.version: raise VersionConflict` on the no-op path. With that check
    dropped — or written `if expected_version` so a caller asking for version
    0 is answered as if it asked for nothing — a device that raced the row
    would be told `changed False, this is the state` for a state it has never
    seen, and would believe it."""
    acc = account(db, user)
    oid = opt(db, user, acc, 'mcp', 'gh', True)['opt_in']['id']
    for stale in (0, 2, 99):
        with pytest.raises(lifecycle.VersionConflict) as ei:
            opt(db, user, acc, 'mcp', 'gh', True, expected_version=stale)
        assert (ei.value.entity_id, ei.value.expected, ei.value.current) == (oid, stale, 1)
    out = opt(db, user, acc, 'mcp', 'gh', True, expected_version=1)
    assert out['changed'] is False and out['opt_in']['version'] == 1
    assert [(r.entity.id, r.version) for r in opt_rows(db)] == [(oid, 1)]
    assert len(recorded_events(db)) == 1                                # nothing written or said


# ── 3. optins.py:57-59 — a stale version refuses the flip, row untouched ────

def test_a_stale_expected_version_refuses_the_flip_and_writes_nothing(db, user):
    """optins.py:57-59 — `tx.update(..., expected_version=expected_version)`:
    the writer checks the version inside the transaction, so a lost race comes
    back VersionConflict and NOTHING of the command commits — not the flipped
    column, not the bumped version, not the event. If the version were checked
    but the transaction still committed, the account would silently lose an
    opt-in the other writer never overwrote, and the audit trail would claim
    it happened."""
    acc = account(db, user)
    oid = opt(db, user, acc, 'mcp', 'gh', True)['opt_in']['id']
    with pytest.raises(lifecycle.VersionConflict) as ei:
        opt(db, user, acc, 'mcp', 'gh', False, expected_version=7)
    assert (ei.value.entity_id, ei.value.expected, ei.value.current) == (oid, 7, 1)
    (r,) = opt_rows(db)
    assert (r.entity.id, r.version, r.entity.opted_in) == (oid, 1, True)   # rolled back whole
    assert [(e['payload']['opted_in'], e['payload']['version']) for e in recorded_events(db)] == [
        (True, 1)]
    out = opt(db, user, acc, 'mcp', 'gh', False, expected_version=1)       # the winner may
    assert out['changed'] is True and out['opt_in']['version'] == 2
    assert out['opt_in']['opted_in'] is False and out['opt_in']['id'] == oid
    assert [(e['payload']['opted_in'], e['payload']['version']) for e in recorded_events(db)] == [
        (True, 1), (False, 2)]


# ── 4. optins.py:47-49 — an opt-out of nothing writes nothing, even hostile ─

def test_an_opt_out_of_what_was_never_opted_in_writes_nothing_even_hostile(db, user):
    """optins.py:47-49 — `if row is None: if not opted_in: return {'opt_in':
    None, 'changed': False}` before any value is built. An opt-out is never a
    row, whatever the kind or name says: if that early return were lost, every
    one of these hostile names would reach `entities.OptIn(...)` or, worse,
    insert a row (`opt-out` recorded as opted_in False or True) that a later
    inventory read could never undo. The True-side refusals prove the same
    inputs are refused at command level, transaction and all (no row, no
    event), not merely by the entity's own constructor."""
    acc = account(db, user)
    assert opt(db, user, acc, 'mcp', 'never', False) == {'opt_in': None, 'changed': False}
    hostile = [('bogus', 'x'), ('mcp', '../../evil'), ('mcp', ''),
               ('mcp', 'has space'), ('source', 'local'),        # the account holds 'user' only
               ('plugin', 'a' * 129)]                             # the grammar ends at 128
    for kind, name in hostile:
        assert opt(db, user, acc, kind, name, False) == {'opt_in': None, 'changed': False}
        with pytest.raises(ValueError):
            opt(db, user, acc, kind, name, True)
    assert opt_rows(db) == [] and recorded_events(db) == []
    assert opt(db, user, acc, 'mcp', 'gh', True)['changed'] is True    # nothing poisoned


# ── 5. optins.py:31-34,46 — the find is owner-scoped, not global ────────────

def test_the_same_kind_and_name_under_two_owners_are_two_rows(db, user):
    """optins.py:31-34 + 46 — `_find` filters `{owner + '_id': owner_id,
    'kind': kind, 'name': name}`. Drop the owner from that filter and the
    account opting in `mcp gh` after its project would find the project's row,
    be told `changed False`, and the account's own opt-in would be lost for
    every execution of it — a silent isolation bug in both directions. The
    flip assertion is the mirror: updating one owner's row must not bump or
    flip the other's, and what `effective` answers for one pair proves the
    rows really are two."""
    acc, prj = account(db, user), project(db, user)
    p = opt(db, user, prj, 'mcp', 'gh', True)
    a = opt(db, user, acc, 'mcp', 'gh', True)                          # same (kind, name)
    assert a['changed'] is True and a['opt_in']['id'] != p['opt_in']['id']
    assert (a['opt_in']['account_id'], a['opt_in']['project_id']) == (acc, None)
    assert (p['opt_in']['account_id'], p['opt_in']['project_id']) == (None, prj)
    assert len(opt_rows(db)) == 2 and len(recorded_events(db)) == 2
    opt(db, user, prj, 'mcp', 'gh', False)
    by_id = {r.entity.id: r for r in opt_rows(db)}
    assert (by_id[p['opt_in']['id']].version, by_id[p['opt_in']['id']].entity.opted_in) == (
        2, False)
    assert (by_id[a['opt_in']['id']].version, by_id[a['opt_in']['id']].entity.opted_in) == (
        1, True)
    with db.read() as r:
        assert optins.effective(r, account_id=acc, project_id=prj) == (
            ('account', 'mcp', 'gh'),)                                 # only the live one


# ── 6. optins.py:77-89 — effective: exactly this pair, opted-in only, sorted ─

def test_effective_names_exactly_this_accounts_and_this_projects_opted_in_rows(db, user):
    """optins.py:83-89 — the three filters are the whole security property of
    the read: `if oid is None: continue` (a missing owner contributes nothing,
    never everything), `**{owner + '_id': oid}` (another account's or project's
    row, or a row nobody owns, never applies), `if r.entity.opted_in` (an
    opt-out must vanish: inverted, a revoked MCP server is handed back to the
    execution), and `tuple(sorted(out))` (the insertion order below
    deliberately contradicts the sorted order). Empty and hostile inputs too:
    no rows, no owners, ids that are nobody — always `()`, never an error."""
    with db.read() as r:                                   # no database contents at all
        assert optins.effective(r, account_id=None, project_id=None) == ()
    acc, prj = account(db, user), project(db, user)
    with db.read() as r:                                   # real owners, no rows
        assert optins.effective(r, account_id=acc, project_id=prj) == ()
    opt(db, user, acc, 'plugin', 'aa@m', True)             # inserted against the sorted order
    opt(db, user, acc, 'mcp', 'zz', True)
    opt(db, user, prj, 'source', 'project', True)
    opt(db, user, prj, 'mcp', 'db', True)
    opt(db, user, prj, 'mcp', 'db', False)                 # the same row, opted back out
    opt(db, user, acc, 'mcp', 'gh', True)                  # same name...
    opt(db, user, prj, 'mcp', 'gh', True)                  # ...under both owners
    with db.read() as r:
        eff = optins.effective(r, account_id=acc, project_id=prj)
        assert isinstance(eff, tuple)
        assert eff == (('account', 'mcp', 'gh'), ('account', 'mcp', 'zz'),
                       ('account', 'plugin', 'aa@m'), ('project', 'mcp', 'gh'),
                       ('project', 'source', 'project'))   # opted-out 'db' is gone; sorted
        assert optins.effective(r, account_id=acc, project_id=None) == eff[:3]
        assert optins.effective(r, account_id=None, project_id=prj) == eff[3:]
        # another account's rows never apply, and a well-formed id of nobody is simply empty
        assert optins.effective(r, account_id=ids.new_id('account'), project_id=prj) == eff[3:]
        assert optins.effective(r, account_id=acc, project_id=ids.new_id('project')) == eff[:3]
        # hostile shapes are nobody's: empty, never an error and never a row
        assert optins.effective(r, account_id='acc_not-a-ulid', project_id='what') == ()
        assert optins.effective(r, account_id='', project_id=prj) == eff[3:]


# ── 7. optins.py:60-65 — the event says its owner's own scope ───────────────

def test_a_projects_change_is_recorded_in_its_own_workspace(db, user):
    """optins.py:60-65 — `if owner == 'project': scope = {'workspace':
    orow.entity.workspace_id, 'project': owner_id}` and the one event per
    change. If the project branch read the default workspace (or dropped the
    project id), every scoped reader of that project — the digest, the SSE
    streams filtered by workspace — loses the record that its settings source
    was opened; if the no-op path started appending, the trail would lie about
    changes that never happened."""
    ws = ids.new_id('workspace')                           # a project NOT in the global space
    prj = project(db, user, workspace_id=ws)
    got = opt(db, user, prj, 'source', 'project', True)['opt_in']
    (e,) = recorded_events(db)
    assert (e['type'], e['subject_kind'], e['subject_id']) == (
        'opt_in.changed', 'opt_in', got['id'])
    assert (e['actor_kind'], e['actor_id']) == (user.kind, user.id)
    assert (e['workspace_id'], e['project_id']) == (ws, prj)
    assert e['visibility'] == 'user'
    assert e['payload'] == {'owner': 'project', 'owner_id': prj, 'kind': 'source',
                            'name': 'project', 'opted_in': True, 'version': 1}
    opt(db, user, prj, 'source', 'project', True)          # the write-free answer says nothing
    assert len(recorded_events(db)) == 1
    acc = account(db, user)
    opt(db, user, acc, 'mcp', 'gh', True)
    e = recorded_events(db)[-1]
    assert (e['workspace_id'], e['project_id']) == (ids.GLOBAL_WORKSPACE, None)
    assert e['payload'] == {'owner': 'account', 'owner_id': acc, 'kind': 'mcp',
                            'name': 'gh', 'opted_in': True, 'version': 1}


# ── 8. optins.py:53-56 + writer replay — the same request, one answer ───────

def test_the_same_request_twice_is_one_row_and_a_replay_writes_nothing(db, user):
    """optins.py:53-56 (`row.entity.opted_in == opted_in` → `changed False`,
    the same row's same view) and the writer's replay of a keyed request
    (writer.py `_one`/`_recall`): a device that retries — twice as a fresh
    command, or twice under one idempotency key — must produce ONE row at ONE
    version with ONE event, and the second answer must equal the first. If the
    no-op branch fell through to `tx.update`, a retry would bump the version
    and post an `opt_in.changed` that changed nothing, and every reader of the
    trail would see a change that never was."""
    acc = account(db, user)
    first = opt(db, user, acc, 'mcp', 'gh', True)
    again = opt(db, user, acc, 'mcp', 'gh', True)
    assert again['changed'] is False and again['opt_in'] == first['opt_in']
    assert [(r.entity.id, r.version) for r in opt_rows(db)] == [(first['opt_in']['id'], 1)]
    assert len(recorded_events(db)) == 1
    out = opt(db, user, acc, 'mcp', 'gh', False)           # the row is reused, never recreated
    assert out['changed'] is True and out['opt_in']['id'] == first['opt_in']['id']
    assert out['opt_in']['version'] == 2
    assert opt(db, user, acc, 'mcp', 'gh', False)['changed'] is False   # second opt-out too
    assert len(opt_rows(db)) == 1 and len(recorded_events(db)) == 2
    # the same mutating request replayed under one idempotency key: answered from the
    # stored row, the command never runs again, so no third version and no third event
    args = {'actor': user, 'owner_id': acc, 'kind': 'plugin', 'name': 'p@m',
            'opted_in': True}
    f1 = db.writer.submit(optins.set_opt_in, args, idempotency_key='req-p@m')
    out1 = f1.result()
    assert f1.replayed is False and out1['changed'] is True
    f2 = db.writer.submit(optins.set_opt_in, dict(args), idempotency_key='req-p@m')
    out2 = f2.result()
    assert f2.replayed is True and out2 == out1
    (row,) = [r for r in opt_rows(db) if r.entity.kind == 'plugin']
    assert row.version == 1
    assert len([e for e in recorded_events(db) if e['payload']['kind'] == 'plugin']) == 1
    with pytest.raises(IdempotencyConflict):               # the key is not a licence for other args
        db.writer.execute(optins.set_opt_in, dict(args, name='other'),
                          idempotency_key='req-p@m')
    assert len([r for r in opt_rows(db) if r.entity.kind == 'plugin']) == 1


# ── 9. optins.py:26-28 — the owner-id namespace is account or project ───────

def test_an_owner_id_that_is_neither_an_account_nor_a_project_is_refused(db, user):
    """optins.py:26-28 — the `_owner` loop matches `acc_` and `prj_` ids only,
    and its ValueError is the last thing standing between a mistyped route
    argument and an opt-in owned by nothing. Every shape below is refused for
    the mutating ask AND for the write-free opt-out (the owner is resolved
    first, so no hostile id is ever used as a row filter). The lowercase and
    corrupt-ULID cases are pure string facts about the id grammar — nothing
    here reads the OS or its file-name case rules."""
    good = ids.new_id('account')
    assert ids.is_id(good, 'account')
    bad = [None, '', 'account', 'acc_', good.lower(), 'acc_' + '0' * 25 + 'U',
           ids.new_id('mission'), ids.new_id('opt_in'), ids.new_id('principal'),
           'hook_' + '0' * 26,        # a hook-token shape: a credential, never an owner id
           42]
    for owner in bad:
        with pytest.raises(ValueError, match='neither'):
            opt(db, user, owner, 'mcp', 'gh', True)
        with pytest.raises(ValueError, match='neither'):
            opt(db, user, owner, 'mcp', 'gh', False)       # the no-write path checks too
    assert opt_rows(db) == [] and recorded_events(db) == []


# ── 10. optins.py:27 — a well-formed owner that does not exist is NotFound ──

def test_a_wellformed_owner_that_does_not_exist_is_not_found(db, user):
    """optins.py:27 — `lifecycle.load(tx, cls, owner_id)` inside `_owner`: a
    syntactically perfect id with no row is NotFound, for BOTH owner kinds (a
    dangling `acc_` and a dangling `prj_` alike), on the opt-in side and on
    the opt-out side. Without the load, an opt-in would happily attach to a
    vanished owner's id (the table's CHECK only demands one of the two
    columns), and executions of a deleted project would keep loading whatever
    was parked there."""
    for kind in ('account', 'project'):
        with pytest.raises(lifecycle.NotFound):
            opt(db, user, ids.new_id(kind), 'mcp', 'gh', True)
        with pytest.raises(lifecycle.NotFound):            # even the write-free answer
            opt(db, user, ids.new_id(kind), 'mcp', 'gh', False)
    assert opt_rows(db) == [] and recorded_events(db) == []


# ── extra error paths: a refused command leaves nothing behind ──────────────

def test_a_non_boolean_opted_in_never_reaches_the_row(db, user):
    """optins.py:57-59 through entities.OptIn._check (`isinstance(self.opted_in,
    bool)` via dataclasses.replace in tx.update): the flip carries ONLY
    `opted_in`, and the entity refuses a truthy/falsy string. The row keeping
    version 1 and `opted_in True`, with one event, proves the whole command
    rolled back — had the update committed its own way first, the trail and the
    row would now disagree with the answer the caller got."""
    acc = account(db, user)
    oid = opt(db, user, acc, 'mcp', 'gh', True)['opt_in']['id']
    for hostile in ('no', 'false', 0):                     # 0 is falsy: the pre-flip...
        with pytest.raises(ValueError, match='boolean'):
            opt(db, user, acc, 'mcp', 'gh', hostile)       # ...branch takes it as an opt-out ask
    with pytest.raises(ValueError, match='boolean'):
        opt(db, user, acc, 'mcp', 'gh', 'yes-but-really-no')
    (r,) = opt_rows(db)
    assert (r.entity.id, r.version, r.entity.opted_in) == (oid, 1, True)
    assert len(recorded_events(db)) == 1


def test_a_name_of_128_okay_characters_is_written_and_129_rolls_back(db, user):
    """optins.py:50-52 through entities.OptIn._check and `_OPT_IN_NAME` —
    `[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}`, so the boundary is 128 characters:
    exactly 128 is a row; one more is a refused command that wrote nothing (no
    row, no event — the transaction rolls back, the audit included). A
    name-vs-boundary off-by-one would either truncate a marketplace name or
    let arbitrary-length junk into a promoted, indexed column."""
    acc = account(db, user)
    ok = 'a' + 'b' * 127
    assert len(ok) == 128
    assert opt(db, user, acc, 'mcp', ok, True)['changed'] is True
    (row,) = [r for r in opt_rows(db) if r.entity.kind == 'mcp']
    assert row.entity.name == ok and row.version == 1
    with pytest.raises(ValueError):
        opt(db, user, acc, 'mcp', ok + 'c', True)           # 129: refused
    assert len(opt_rows(db)) == 1 and len(recorded_events(db)) == 1


def test_listing_shows_every_row_in_and_out_with_its_owner_named(db, user):
    """optins.py:69-74 — `listing`: every row (the opted-out ones included:
    dropping them would hide a revocation from Control → Accounts), with
    `owner` naming which column owns it and `owner_id` its value (inverted,
    an account row would be shown as a project's and granted to the wrong
    executions), plus the row metadata from `view`. On an empty database: [],
    not None, not an error."""
    with db.read() as r:
        assert optins.listing(r) == []                     # empty input, plain empty answer
    acc, prj = account(db, user), project(db, user)
    opt(db, user, acc, 'mcp', 'gh', True)
    opt(db, user, prj, 'source', 'project', True)
    opt(db, user, prj, 'source', 'project', False)         # revoked: still listed, at v2
    with db.read() as r:
        got = optins.listing(r)
    assert [(g['owner'], g['owner_id'], g['kind'], g['name'], g['opted_in'], g['version'])
            for g in got] == [
                ('account', acc, 'mcp', 'gh', True, 1),
                ('project', prj, 'source', 'project', False, 2)]
    assert all(g['id'].startswith('opi_') and {'created_at', 'updated_at'} <= set(g)
               for g in got)


def test_a_command_that_cannot_record_its_actor_writes_nothing(db, user):
    """optins.py:50-52 through tx.insert (`created_by must be a principal id`):
    the user-device gate reads only `kind`; the id must still be a principal
    id or the insert — and with it the event and the row — is refused whole.
    Were the audit check skipped, an opt-in would exist that nobody can prove
    anyone asked for, and every later "who opened this source?" reads a hole."""
    acc = account(db, user)
    with pytest.raises(ValueError, match='principal'):
        opt(db, Ref('user_device', 'not-a-principal'), acc, 'mcp', 'gh', True)
    assert opt_rows(db) == [] and recorded_events(db) == []
