"""T-1146 - the ten highest-risk uncovered branches of
`archeus/core/application/optins.py` (lines 1-89), as integration tests.

Source range read: the whole of `archeus/core/application/optins.py` 1-89 -
`_owner` 24-28, `_find` 31-34, `set_opt_in` 37-66 (the actor refusal 42-44, the
owner and the find 45-46, the write-free answer 48-49, the create 50-52, the
version-bound no-op 53-56, the flip 57-59, the event 60-65), `listing` 69-74 and
`effective` 77-89. Nothing outside that range is edited or owned here; the route, the
writer and the credential layer are only the seams the command is reached
through, and one test's docstring names the branch of *this* module it kills.

The ten, ranked by the risk of shipping the defect - fail-closed and denial
paths first, then boundary conditions, then error/fault paths (each test's
docstring cites the branch and the mutation that proves it is not covered
elsewhere):

 1. every falsy ask that is not `False` (48-49) - a create nobody asked for
 2. a truthy ask that is not a boolean (50-52, 63-65) - source defect, xfail
 3. `kind` being part of an opt-in's identity (31-34)
 4. the opt-out ask against an entry that is already out (53-56)
 5. who the change is recorded as being done by (58-59, 63-65)
 6. `expected_version` on the create path vs the no-op and flip paths (47-52,
    53-55)
 7. one name asked twice inside one transaction (31-34, 47-56)
 8. the replay of a write-free answer (48-49, with writer.py 470)
 9. an opt-in inside a transaction that then fails (50-52, 58-59, 63-65)
10. what a reader sees while a change is in flight (47-56, 83-89)

Six of the card's ten risk probes turned out to be already covered by
tests/v1/unit/test_gaps_core_application_optins.py (its 42-44 actor gate, its
26-28 owner grammar, its not-found path, the stale version on a real change,
the workspace scope of a project's event, and `effective` excluding a revoked
row), and were replaced rather than duplicated; the others are the boundary
cases numbered 1, 3, 4, 6 and 7 above. /work/QWEN-DONE-T-1146.md carries the
probe-by-probe disposition with the mutation evidence for each.

Seams, all of them existing ones - no socket, no worker, no OS. The `tc`
(TempCore) fixture of tests/v1/integration/conftest.py starts real sockets and
is deliberately not used.

* `Database.open()` on the `archeus_home` tmp_path of tests/v1/conftest.py
  (its autouse `archeus_home` fixture) and the `db`/`clock` fixtures of this
  directory's conftest.py; Core's worker is started by nothing here.
* the real `server.Api` (the object `Handler` reads) built over that database
  with a fake missions port, the fixture's fake clock, a static directory that
  does not exist and an origin backend that fails the test if anything reads
  the OS through it. No runtime, no listener, no transport, no adapter, no
  sentinel: none of them is started, so none of them can be reached.
* one request is the real `Handler._serve` driven by `_Request` below, whose
  `rfile`/`wfile` are `BytesIO` - the fake-transport pattern of
  tools/fuzz_p20.py's `_Request` (line 193) and
  tests/v1/unit/test_pins_api_server.py's `_serve` helper (line 155). The
  credential rides in the `Authorization` header, so `authenticate` and the
  per-route scope check really run.
"""

import io
import json
import os
import threading
from http.client import HTTPMessage
from types import SimpleNamespace

import pytest

from archeus.api import auth, server
from archeus.core.application import commands, lifecycle, optins
from archeus.core.domain import entities, ids
from archeus.core.domain.values import PRINCIPAL_SCOPES, Ref
from archeus.harnesses import sources
from archeus.infra import paths
from archeus.infra.db import rows

# Never bound: the fake transport below opens no socket, so this only has to be
# a number the Origin/Host checks of `Handler._serve` can compare against.
PORT = 8799
GLOBAL = ids.GLOBAL_WORKSPACE


# ---------------------------------------------------------------- fixtures ──

@pytest.fixture
def api(db, clock, tmp_path):
    """The real `Api` the handlers read, over the fixture's database and the
    fixture's fake clock (`tests/v1/integration/conftest.py`).

    Core's workers are started by nobody, so there is no worker, listener,
    transport, adapter, attestation daemon or e-stop sentinel to disable; the
    `missions` port is a `tests/v1/unit/test_pins_api_server.py`-style fake and
    `origin_backend` is an object that fails the test if the opt-in path ever
    asks the OS for a logon session (`Handler.transport_evidence`, server.py
    288-292, is only reached with origin enforcement on, and `Api`'s
    `origin_enforcement_enabled` defaults to archeus/api/origin.py's
    `ORIGIN_ENFORCEMENT_ENABLED`, which is False - the value the shipped Core
    runs with)."""
    return server.Api(db=db, missions=SimpleNamespace(policy=None), port=PORT,
                      health=None, version='gaps3', launch_clock=clock,
                      static_dir=str(tmp_path / 'static'), origin_backend=_NoOs())


class _NoOs:
    """An origin backend that must never be touched: any OS read fails the test."""

    def __getattr__(self, name):
        raise AssertionError('the opt-in path read the OS through origin_backend.%s' % name)


# ------------------------------------------------------- the fake transport ──

class _Request(server.Handler):
    """One request through the real `Handler._serve`, no socket and no thread.

    `tools/fuzz_p20.py`'s `_Request` (line 193) and
    `tests/v1/unit/test_pins_api_server.py`'s `_serve` (line 155): the fields
    BaseHTTPRequestHandler reads are set directly, `rfile`/`wfile` are BytesIO,
    and the answer is read back out of `wfile`. The status, the parsed body and
    the `X-Archeus-Replayed` flag are what the assertions use."""
    replayed = None

    def __init__(self, api, method, path, raw=b'', token=None):
        self.server = SimpleNamespace(api=api)
        self.command, self.path, self.request_version = method, path, 'HTTP/1.1'
        self.requestline = '%s %s HTTP/1.1' % (method, path)
        self.headers = HTTPMessage()
        for k, v in (('Host', api.origin.host), ('Content-Type', 'application/json'),
                     ('Content-Length', str(len(raw)))):
            self.headers[k] = v
        if token is not None:
            self.headers['Authorization'] = 'Bearer ' + token
        self.rfile, self.wfile = io.BytesIO(raw), io.BytesIO()
        self.client_address = ('127.0.0.1', 54321)
        self._serve()

    def json(self):
        return json.loads(self.wfile.getvalue().partition(b'\r\n\r\n')[2])


def get(api, token, path):
    return _Request(api, 'GET', path, token=token)


def post(api, token, key=None, **body):
    """POST /v1/opt-ins with `body`; the idempotency key is part of the body, as
    routes.py's `set_opt_in` requires (server.py 325-341 reads it from there)."""
    raw = json.dumps(dict(body, idempotency_key=key or 'k-' + ids.new_id('device')))
    return _Request(api, 'POST', '/v1/opt-ins', raw.encode('utf-8'), token)


# ------------------------------------------------------------ the fixtures' ──
# ------------------------------------------------------- data, through seams ──

def principal(db, kind, scopes=None):
    """A registered principal of `kind`, with the scopes that kind may hold
    (entities.py 186-190 refuses any others)."""
    return db.writer.execute(commands.register_principal, {
        'kind': kind, 'scopes': list(PRINCIPAL_SCOPES[kind] if scopes is None else scopes)
    })['id']


def user(db):
    """The actor the command-seam tests write as: a real user device principal.
    `set_opt_in` is the public command surface of the slice and takes it as the
    `actor` keyword - the route hands it the authenticated principal
    (routes.py 590-596), which is what test 5 pins."""
    return Ref('user_device', principal(db, 'user_device'))


def credential(db, secret, kind='user_device'):
    """A live device credential for `kind`: the principal, its ACTIVE client row
    and the token's hash - the three things `auth.live` reads. Built the way
    tests/v1/judge/http.py's `_issue_principal` (line 40) builds one, through
    the writer."""
    pid, actor = principal(db, kind), None
    token = 'dev_' + secret
    actor = Ref(kind, pid)

    def run(tx):
        d = entities.Device(id=ids.new_id('device'), principal_id=pid, name=secret,
                            platform='desktop')
        tx.insert(d, actor=actor)
        lifecycle.fire(tx, entities.Device, d.id, 'code_redeemed', actor=actor,
                       reason='gaps3 handed out a credential')
        tx.insert_token(token_hash=auth.token_hash(token), kind='device', principal_id=pid,
                        scopes=list(PRINCIPAL_SCOPES[kind]), actor=actor)
    db.writer.execute(run, {})
    return (token, pid)


def account(db, actor, label='acct'):
    """An account the opt-in can belong to, through the writer (the shape
    tests/v1/unit/test_gaps_core_application_optins.py's `account` uses, with the
    `account.registered` event no read side of this file needs)."""
    pid = ids.new_id('account')

    def run(tx):
        tx.insert(entities.Account(id=pid, harness_id='fake', label=label, auth_kind='api_key'),
                  actor=actor)
        tx.append(new_account_event(pid, actor, label))
    db.writer.execute(run, {})
    return pid


def project(db, actor, name='p', workspace_id=GLOBAL):
    """A project the opt-in can belong to, in `workspace_id` (the global workspace
    by default, as every existing test of the module uses)."""
    pid = ids.new_id('project')

    def run(tx):
        tx.insert(entities.Project(id=pid, workspace_id=workspace_id, name=name, root_paths=()),
                  actor=actor)
        tx.append(new_project_event(pid, actor, name, workspace_id))
    db.writer.execute(run, {})
    return pid


def new_account_event(pid, actor, label):
    from archeus.core.domain.events import new_event
    return new_event('account.registered', Ref('account', pid), actor, payload={'label': label})


def new_project_event(pid, actor, name, workspace_id):
    from archeus.core.domain.events import new_event
    return new_event('project.created', Ref('project', pid), actor, payload={'name': name},
                     workspace=workspace_id, project=pid)


def ask(db, actor, owner_id, kind, name, opted_in, expected_version=None):
    """`set_opt_in` as any caller calls it: one command, one transaction, on the
    writer (tests/v1/unit/test_gaps_core_application_optins.py's `opt`)."""
    return db.writer.execute(optins.set_opt_in, dict(
        actor=actor, owner_id=owner_id, kind=kind, name=name, opted_in=opted_in,
        expected_version=expected_version))


def opt_rows(db, **eq):
    """Every opt-in row, oldest first, optionally filtered - `rows.where` on a
    read connection, as the unit tests of the module do."""
    with db.read() as r:
        out = rows.where(r, entities.OptIn)
    return [x for x in out if all(getattr(x.entity, k) == v for k, v in eq.items())]


def changes(db, **eq):
    """The `opt_in.changed` events, oldest first, payload parsed: the audit trail
    `set_opt_in` appended (0001_init.sql's events columns)."""
    with db.read() as r:
        out = [dict(rec) for rec in r.execute(
            "SELECT type, at, subject_kind, subject_id, actor_kind, actor_id, workspace_id,"
            " project_id, payload FROM events WHERE type = 'opt_in.changed' ORDER BY seq"
        ).fetchall()]
    for rec in out:
        rec['payload'] = json.loads(rec['payload'])
    return [rec for rec in out if all(rec.get(k) == v for k, v in eq.items())]


def state(db):
    """The whole opt-in state as the read answers see it, in one snapshot: what
    `listing` returns, plus the rows behind it."""
    with db.read() as r:
        return optins.listing(r)


# ──────────────────────────────────────────────── 01. every falsy ask that is not `False`

def test_01_no_falsy_ask_that_is_not_false_creates_an_opt_in(db):
    """optins.py 48-49: `if not opted_in: return {'opt_in': None, 'changed':
    False}` - the write-free answer for an entry that does not exist.

    Closest existing tests: `test_an_opt_out_of_what_was_never_opted_in_writes`
    (…nothing_even_hostile) of tests/v1/unit/test_gaps_core_application_optins.py
    (line 172) and `test_I03_an_opt_out_of_what_was_never_opted_in_writes_nothing`
    of test_settings_sources.py (line 140) - both only ever ask `False`, and the
    unit file's `test_a_non_boolean_opted_in_never_reaches_the_row` (line 378)
    does ask the falsy `0`, but only with a row already present, where line 48 is
    never evaluated and the entity's check at the update does the work.

    Killing it: tightening 48 to `if opted_in is False:` - the "be strict about
    the opt-out" edit - sends every falsy value that is not `False` (`0`, `0.0`,
    `''`, `[]`, `{}`, `None`, an empty byte string) past the early return into
    50-52, which *creates a live, opted-in row for a source nobody opted in*: a
    fail-open on the exact gate this whole feature is. That mutation leaves all
    14 unit tests and I01-I05 green, because none of them asks for an absent
    entry with a falsy non-`False` value.

    The second half pins the other side of the same line: once a row exists those
    same values are refused by the entity instead of revoking it (which is why
    the boundary above cannot be "fixed" by treating them as opt-outs)."""
    actor = user(db)
    acc = account(db, actor)
    for i, value in enumerate((0, 0.0, '', [], (), {}, None, set(), b'')):
        name = 'falsy%d' % i
        assert ask(db, actor, acc, 'mcp', name, value) == {'opt_in': None, 'changed': False}, \
            repr(value)
    assert opt_rows(db) == []
    assert changes(db) == []
    with db.read() as r:
        assert optins.effective(r, account_id=acc, project_id=None) == ()
        assert optins.listing(r) == []

    # the same names, asked honestly, are still opt-in-able - the falsy asks left
    # no half-written row behind
    assert ask(db, actor, acc, 'mcp', 'falsy0', True)['changed'] is True
    (row,) = opt_rows(db, name='falsy0')
    assert (row.entity.opted_in, row.version) == (True, 1)
    # ...and from here the falsy-not-False asks are refusals, not revocations
    for i, value in enumerate((0, 0.0, '', [], {}, None)):
        with pytest.raises(ValueError, match=r'OptIn\.opted_in is a boolean'):
            ask(db, actor, acc, 'mcp', 'falsy0', value)
    (row,) = opt_rows(db, name='falsy0')
    assert (row.entity.opted_in, row.version) == (True, 1)
    assert len(changes(db)) == 1


# ───────────────────────────────────────── 02. a truthy ask that is not a boolean

def test_02_a_truthy_ask_that_is_not_a_boolean_is_refused_before_anything_is_written(db):
    """optins.py 50-52 (`tx.insert(entities.OptIn(..., opted_in=True ...))`) and
    63-65 (`payload = {..., 'opted_in': opted_in ...}`).

    Closest existing test: `test_a_non_boolean_opted_in_never_reaches_the_row` of
    tests/v1/unit/test_gaps_core_application_optins.py (line 378) - it starts from
    an *existing* row, so it exercises the flip at 57-59, where the entity check
    does fire. No test of this module starts from *no row*, which is the half in
    which `opted_in='false'` - the value a client that forgot to parse a form
    field sends - becomes a live opt-in for a source nobody opted in.

    Asserted here is the contract, not the current behaviour: the ask is refused
    the way the flip path refuses it, and neither a row nor an event survives it."""
    actor = user(db)
    acc = account(db, actor)
    for i, value in enumerate(('false', 'False', 'no', 'off', 'true', 1, 1.5, [0], {'k': 0})):
        with pytest.raises(ValueError):        # the entity's check, or a new Invalid
            ask(db, actor, acc, 'mcp', 'truthy%d' % i, value)
        assert opt_rows(db) == []
        assert changes(db) == []
        with db.read() as r:
            assert optins.effective(r, account_id=acc, project_id=None) == ()
            assert optins.listing(r) == []


# ───────────────────────────────────────────── 03. `kind` is part of an opt-in's identity

def test_03_one_name_under_two_kinds_is_two_rows_and_revoking_one_leaves_the_other(db):
    """optins.py 31-34: `_find` filters on `account_id`/`project_id`, `kind` *and*
    `name`, and 47-52 creates when it finds nothing.

    Closest existing tests: `test_the_same_kind_and_name_under_two_owners_are`
    (…two_rows) of tests/v1/unit/test_gaps_core_application_optins.py (line 196)
    separates two *owners* by one (kind, name), and `test_I05_...` of
    test_settings_sources.py (line 166) gives one project a `source` and an `mcp`
    row - but always under *different* names. No existing test asks one owner for
    the same name under two kinds, which is the case that matters: `name` is only
    unique per kind (`SOURCE_OWNERS`, entities.py 1524 - a project may have the
    `source` literally named `project` and an MCP server named `project`), so the
    name alone is not an identity and only `_find`'s `kind` filter keeps them two.

    Killing it: dropping `'kind'` from `_find`'s filter at 32 makes the second
    ask find the first row and answer "already opted in" - no row, no event, the
    plugin silently never opted in, and revoking it reports `changed False` while
    the MCP server of the same name stays live for every execution of the owner.
    Every existing test of the module survives that mutation (none has one owner
    with two kinds under one name); `effective`'s own filter is untouched by it,
    so the read never notices the row that was never written."""
    actor = user(db)
    acc = account(db, actor)
    mcp = ask(db, actor, acc, 'mcp', 'gh', True)
    plugin = ask(db, actor, acc, 'plugin', 'gh', True)
    assert (mcp['changed'], plugin['changed']) == (True, True)
    assert mcp['opt_in']['id'] != plugin['opt_in']['id']
    assert [(r.entity.kind, r.entity.opted_in, r.version) for r in opt_rows(db)] == [
        ('mcp', True, 1), ('plugin', True, 1)]
    assert [(e['payload']['kind'], e['payload']['name']) for e in changes(db)] == [
        ('mcp', 'gh'), ('plugin', 'gh')]

    revoked = ask(db, actor, acc, 'plugin', 'gh', False)
    assert (revoked['changed'], revoked['opt_in']['version']) == (True, 2)
    assert [(r.entity.kind, r.entity.opted_in, r.version) for r in opt_rows(db)] == [
        ('mcp', True, 1), ('plugin', False, 2)]
    with db.read() as r:
        assert optins.effective(r, account_id=acc, project_id=None) == (('account', 'mcp', 'gh'),)
        assert [(x['kind'], x['opted_in']) for x in optins.listing(r)] == [('mcp', True),
                                                                          ('plugin', False)]

    # the same name as a *source* of a project and as a server of the same project
    prj = project(db, actor, 'p1')
    assert ask(db, actor, prj, 'source', 'project', True)['changed'] is True
    assert ask(db, actor, prj, 'mcp', 'project', True)['changed'] is True
    with db.read() as r:
        assert optins.effective(r, account_id=None, project_id=prj) == (
            ('project', 'mcp', 'project'), ('project', 'source', 'project'))
    assert len(changes(db)) == 5


# ─────────────────────────────── 04. the opt-out ask against an entry that is already out

def test_04_an_opt_out_ask_against_an_entry_already_out_is_that_rows_own_answer(db):
    """optins.py 53-56: the `elif row.entity.opted_in == opted_in` branch answers a
    no-change ask with the row's own view and binds it to `expected_version` at
    54-55 - in both directions, including the one 48-49 cannot catch because a row
    does exist: the entry is already out and the ask is to take it out.

    Closest existing tests: `test_asking_for_what_already_holds_with_the_wrong_
    version_is_refused` (line 125) of
    tests/v1/unit/test_gaps_core_application_optins.py binds the version on the
    *live* row asked True, and `test_the_same_request_twice_is_one_row_and_a_replay
    _writes_nothing` (line 295) asks the revoked row again and looks only at
    `['changed']`; `test_I01`/`test_I03` of test_settings_sources.py (113/140)
    cover the real flip and the absent entry. Nothing asserts what the no-change
    opt-out ask must answer (the row, with its version, not `None`) or that it is
    version-bound.

    Killing it: narrowing 54-55 to the opt-in direction - `if expected_version is
    not None and opted_in is True and expected_version != row.version` - the "an
    opt-out ask can never conflict" edit. A device that revokes from a stale view
    then gets `changed False` instead of the conflict, and the version it
    mis-remembered is never reported: two devices, one of which believes it is
    withdrawing a version nobody has seen since, is exactly the case the optimistic
    version exists for. The same narrowing on the row-less side of 48-49 is why
    the two answers are asserted side by side here: an entry that is out has a
    row, a version and a revocation to report, and answering it like an entry that
    never existed would erase the difference between never trusted and withdrawn."""
    actor = user(db)
    acc = account(db, actor, 'A')

    # the two real changes: in at version 1, out at version 2
    assert ask(db, actor, acc, 'mcp', 'gh', True)['opt_in']['version'] == 1
    out = ask(db, actor, acc, 'mcp', 'gh', False)
    assert (out['changed'], out['opt_in']['version'], out['opt_in']['opted_in']) == (
        True, 2, False)
    row_id = out['opt_in']['id']
    assert [(e['payload']['version'], e['payload']['opted_in']) for e in changes(db)] == [
        (1, True), (2, False)]

    # the same ask again: the row's own answer, not the answer for an entry that
    # was never here, and it still carries the version the audit was written at
    again = ask(db, actor, acc, 'mcp', 'gh', False)
    assert again['changed'] is False
    assert again['opt_in'] is not None, 'a revoked entry is not a missing one'
    assert sorted(again['opt_in']) == ['account_id', 'created_at', 'digest', 'id', 'kind',
                                       'name', 'opted_in', 'project_id', 'updated_at', 'version']
    assert (again['opt_in']['id'], again['opt_in']['opted_in'], again['opt_in']['version']
            ) == (row_id, False, 2)

    # an expectation that matches is a no-op; one that does not is a conflict, in
    # the opt-out direction exactly as in the opt-in direction
    assert ask(db, actor, acc, 'mcp', 'gh', False, expected_version=2)['changed'] is False
    for stale in (1, 0, 3, 99):
        with pytest.raises(lifecycle.VersionConflict) as refused:
            ask(db, actor, acc, 'mcp', 'gh', False, expected_version=stale)
        assert (refused.value.entity_id, refused.value.expected, refused.value.current) == (
            row_id, stale, 2)

    # nothing any of those asks changed: one row, still at version 2, still out,
    # and no third event for an ask that changed nothing
    (row,) = opt_rows(db, name='gh')
    assert (row.entity.opted_in, row.version, row.entity.id) == (False, 2, row_id)
    assert len(changes(db)) == 2

    # side by side: the entry that was never here. There is no version to be
    # wrong about, so no expectation can conflict - and no row to report
    never = ask(db, actor, acc, 'mcp', 'other', False, expected_version=7)
    assert never == {'opt_in': None, 'changed': False}
    assert opt_rows(db, name='other') == []
    assert len(changes(db)) == 2


# ──────────────────────────────────────── 05. who the change is recorded as being done by

def test_05_the_credential_writes_the_opt_in_and_no_field_of_the_body_claims_it(api, db,
                                                                                archeus_home,
                                                                                monkeypatch):
    """optins.py 57-59 (`tx.update(..., actor=actor)` -> `updated_by`, writer.py
    189/203) and 63-65 (`new_event(..., actor, ...)` -> the event's `actor_id`).

    Closest existing test: `test_H01_opt_ins_are_admin_written_and_observe_read`
    of this directory's test_settings_sources.py (line 866) is the only one that
    posts `/v1/opt-ins` at all, and it asserts the status, `changed`, `version`
    and the list projection - never who the row and the change event name as
    their author; the unit file reaches the command directly with `actor=`
    (its `test_a_command_that_cannot_record_its_actor_writes_nothing`, line 438,
    pins only that the id must be *a* principal id). No existing test has an
    entry whose creator and last changer are different principals, so nothing
    pins `updated_by` or the event actor of a flip at all.

    Killing it: making the flip report the row's original creator instead of the
    acting credential (`actor=actor` at 59 -> `actor=Ref('user_device',
    row.created_by)`, and the same at 64) - an opt-in revoked by one device then
    reads as if the person who first opened it revoked it, which is exactly the
    accountability a revocation is audited for. Both mutations leave every
    existing test of the module green, because there the author never changes.

    Also pins the absence of privileged side effects: the opt-in path reads no
    harness settings file, spawns nothing, touches nothing under the runtime
    root and never asks the OS for a logon session (`_NoOs`)."""
    def trip(*args, **kwargs):
        raise AssertionError('an opt-in command read a harness settings file')
    monkeypatch.setattr(sources, 'take', trip)
    monkeypatch.setattr(sources, 'mcp_config', trip)
    before = _home_state(archeus_home)

    token_a, a = credential(db, 'a' * 32)
    token_b, b = credential(db, 'b' * 32)
    acc = account(db, Ref('user_device', a), 'A')

    made = post(api, token_a, key='k-1', owner_id=acc, kind='mcp', name='gh', opted_in=True)
    assert made._status == 200
    assert made.json()['changed'] is True
    # what the answer describes: the account's row, opted in, version 1, and no
    # field naming anybody as its author (routes.py 590-596 sends no actor)
    assert sorted(made.json()['opt_in']) == ['account_id', 'created_at', 'digest', 'id', 'kind',
                                            'name', 'opted_in', 'project_id', 'updated_at',
                                            'version']
    assert made.json()['opt_in']['opted_in'] is True and made.json()['opt_in']['version'] == 1
    (row,) = opt_rows(db)
    assert (row.entity.account_id, row.entity.project_id) == (acc, None)
    assert (row.created_by, row.updated_by) == (a, a)
    (event,) = changes(db)
    assert (event['actor_kind'], event['actor_id']) == ('user_device', a)
    assert event['subject_kind'] == 'opt_in' and event['subject_id'] == row.entity.id

    # a second credential of the same kind: the flip says who flipped it, and
    # leaves the creator's name on the row
    flipped = post(api, token_b, key='k-2', owner_id=acc, kind='mcp', name='gh', opted_in=False)
    assert flipped._status == 200 and flipped.json()['changed'] is True
    (row,) = opt_rows(db)
    assert (row.created_by, row.updated_by, row.version) == (a, b, 2)
    assert [(e['actor_id'], e['payload']['opted_in']) for e in changes(db)] == [(a, True),
                                                                                (b, False)]

    # the body cannot name the actor: those fields are refused before the command
    # is submitted, so nothing is written and nothing is appended
    for field in ('actor', 'actor_id', 'created_by', 'updated_by', 'principal_id'):
        refused = post(api, token_a, key='k-claim-' + field, owner_id=acc, kind='mcp',
                       name='gh', opted_in=True,
                       **{field: {'kind': 'system', 'id': ids.new_id('principal')}})
        assert refused._status == 400, field
        assert refused.json() == {'error': 'invalid_request',
                                 'detail': {'field': field, 'why': 'is not a known field'}}
    assert [(r.created_by, r.updated_by, r.version) for r in opt_rows(db)] == [(a, b, 2)]
    assert len(changes(db)) == 2

    # and a credential of any kind that is not a user device never reaches the
    # command at all: the route's `admin` scope is one no such principal may hold
    for kind in sorted(set(PRINCIPAL_SCOPES) - {'user_device'}):
        token, pid = credential(db, ('z' * 32)[:24] + kind[:8], kind=kind)
        denied = post(api, token, key='k-' + kind, owner_id=acc, kind='mcp', name='never',
                      opted_in=True)
        assert denied._status == 403, kind
        assert denied.json() == {'error': 'scope_required', 'detail': {'scope': 'admin'}}
    assert [(r.created_by, r.updated_by, r.version) for r in opt_rows(db)] == [(a, b, 2)]
    assert len(changes(db)) == 2

    # and the list the user is shown is the state the command left behind
    got = get(api, token_b, '/v1/opt-ins')
    assert got._status == 200
    assert got.json() == {'opt_ins': [{
        'id': row.entity.id, 'kind': 'mcp', 'name': 'gh', 'account_id': acc, 'digest': None,
        'project_id': None, 'opted_in': False, 'version': 2,
        'created_at': row.created_at, 'updated_at': row.updated_at,
        'owner': 'account', 'owner_id': acc}]}

    # nothing privileged happened on the way
    assert _home_state(archeus_home) == before
    assert not os.path.exists(paths.processes_registry())
    assert not os.path.exists(paths.stop_sentinel())


def _home_state(home):
    """Every path under the runtime root: an opt-in that spawned, registered or
    wrote anything would show up here."""
    found = []
    for dirpath, dirs, files in os.walk(home):
        found += [os.path.relpath(os.path.join(dirpath, n), home) for n in dirs + files]
    return sorted(found)


# ──────────────────────────────────────── 06. expected_version: create vs flip (the race)

def test_06_an_expected_version_cannot_be_brought_to_an_opt_in_that_does_not_exist_yet(db):
    """optins.py 47-52 against 53-56: the `expected_version` check lives in the
    `elif` of 53-55, the branch taken only when `_find` returned a row; the create
    path of 47-52 never looks at it.

    Closest existing tests: `test_asking_for_what_already_holds_with_the_wrong_
    version_is_refused` (line 125) and `test_a_stale_expected_version_refuses_the_
    flip_and_writes_nothing` (line 146) of tests/v1/unit/test_gaps_core_application
    _optins.py, and `test_I04` of test_settings_sources.py (line 145) - all three
    pass `expected_version` only when a row is already there. No test of the
    module has ever passed it for an entry that does not exist yet, so nothing
    pins which side of 47/53 that number belongs on.

    Killing it: adding the same guard to the create path (`if expected_version is
    not None and expected_version != 0: raise VersionConflict` inside 47) - the
    "bind the create too" edit, which looks safer than it is - makes the first
    opt-in of a source un-creatable for any client that sends the version it
    believes (every conditional writer's "I expect nothing here" is 7, 99, or the
    number a stale read gave it): the entry can never be opened, and the refusal
    is reported as a conflict about a row that does not exist. Part (b) is the
    other side: two asks that both believe no row exists, submitted before either
    is awaited - the writer serialises them, so the second *has* a row by the time
    it runs and 53-55 must refuse it rather than answer "no change needed"; the
    loser's honest retry is then the truthful no-op."""
    actor = user(db)
    acc = account(db, actor)

    # (a) there is nothing to match when there is no row: an expectation cannot
    #     block a create, whatever number it carries
    for name, expected in (('a', None), ('b', 0), ('c', 7), ('d', 99)):
        out = ask(db, actor, acc, 'mcp', name, True, expected_version=expected)
        assert (out['changed'], out['opt_in']['version']) == (True, 1), name

    # (b) two asks that both believe no row exists, submitted before either is
    #     awaited: the writer serialises them, the second now *has* a row, and its
    #     expectation of an absent entry is a conflict
    args = dict(actor=actor, owner_id=acc, kind='mcp', name='race', opted_in=True,
                expected_version=0)
    first = db.writer.submit(optins.set_opt_in, args, idempotency_key='race-1')
    second = db.writer.submit(optins.set_opt_in, args, idempotency_key='race-2')
    won = first.result(60)
    assert (won['changed'], won['opt_in']['version']) == (True, 1)
    with pytest.raises(lifecycle.VersionConflict) as refused:
        second.result(60)
    assert (refused.value.entity_id, refused.value.expected, refused.value.current) == (
        won['opt_in']['id'], 0, 1)
    (row,) = [r for r in opt_rows(db, name='race')]
    assert (row.entity.opted_in, row.version, row.created_by) == (True, 1, actor.id)
    assert [(e['payload']['name'], e['payload']['version']) for e in changes(db)
            if e['payload']['name'] == 'race'] == [('race', 1)]

    # the loser asking honestly is told the truth, and that answer writes nothing
    honest = ask(db, actor, acc, 'mcp', 'race', True)
    assert (honest['changed'], honest['opt_in']['version']) == (False, 1)
    assert (row.entity.opted_in, row.version) == (True, 1)
    assert len(changes(db)) == 5
    # the no-op path of an existing row honours the same expectation too
    with pytest.raises(lifecycle.VersionConflict):
        ask(db, actor, acc, 'mcp', 'race', True, expected_version=99)
    assert len(changes(db)) == 5


# ──────────────────────────────────────── 07. one name asked twice inside one transaction

def test_07_two_asks_for_one_name_inside_one_transaction_are_one_row_and_one_change(db):
    """optins.py 31-34: `_find(tx, ...)` is handed *the transaction itself* (46),
    so an ask must see the row an earlier ask of the same transaction inserted,
    and 47-56 must answer from it.

    Closest existing tests: `test_the_same_request_twice_is_one_row_and_a_replay
    _writes_nothing` (line 295) and `test_a_projects_change_is_recorded_in_its_
    own_workspace` (line 264) of tests/v1/unit/test_gaps_core_application_optins
    .py both ask twice - but through `writer.execute`, so every ask is its own
    committed transaction, and `test_I01` of test_settings_sources.py (line 113)
    likewise. Nothing asks one name twice inside one transaction, which is what a
    batched command does (opt a source in, then opt in the plugin that provides
    it, in one command).

    Killing it: pointing `_find` at the committed state instead of the
    transaction - `got = Database.open().read().where(entities.OptIn, **own)` for
    `got = conn_or_tx.where(entities.OptIn, **own)` at 32-33, the one-line
    "read from the pool" change - makes the second ask of the batch insert the
    same row again and die on the UNIQUE index of 0015_opt_ins.sql (`opt_ins_one`),
    so the batch loses its first change too. Every existing test survives that
    mutation because each ask runs in its own transaction."""
    actor = user(db)
    acc = account(db, actor)

    def batch(tx):
        first = optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='gh',
                                 opted_in=True)
        again = optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='gh',
                                 opted_in=True)
        off = optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='gh',
                                opted_in=False)
        on = optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='gh',
                               opted_in=True)
        return ([first['changed'], again['changed'], off['changed'], on['changed']],
                [first['opt_in'] and first['opt_in']['version'],
                 again['opt_in'] and again['opt_in']['version'],
                 off['opt_in']['version'], on['opt_in']['version']],
                optins.listing(tx))

    changed, versions, listed = db.writer.execute(batch, {})
    assert changed == [True, False, True, True]
    assert versions == [1, 1, 2, 3]
    # the transaction's own read sees its own write, once, at its own version
    assert [(x['name'], x['opted_in'], x['version']) for x in listed] == [('gh', True, 3)]
    (row,) = opt_rows(db)
    assert (row.entity.name, row.entity.opted_in, row.version) == ('gh', True, 3)
    assert (row.created_by, row.updated_by) == (actor.id, actor.id)
    # one no-op wrote nothing: three changes, three events, one row
    assert [(e['payload']['opted_in'], e['payload']['version']) for e in changes(db)] == [
        (True, 1), (False, 2), (True, 3)]


# ────────────────────────────────────────────────── 08. the replay of a write-free answer

def test_08_a_replayed_write_free_answer_stays_that_answer_and_undoes_nothing(api, db):
    """optins.py 48-49 again, but through the writer's replay gate: a command whose
    answer was "nothing to do" has written nothing, so replaying it must stay that
    answer whatever the state has become since.

    Closest existing tests: `test_the_same_request_twice_is_one_row_and_a_replay_
    writes_nothing` (line 295) replays an ask that *did* write, and `test_I03` of
    test_settings_sources.py (line 140) asks the write-free ask once. Nothing
    replays the write-free answer while the state moved underneath it, which is
    exactly what a retried HTTP request does: Control's "revoke it" times out, the
    user opts it in from another device, the retry comes back.

    Killing it: the answer being remembered only for a command that actually
    wrote - `if key is not None and tx.mutated:` for the unconditional
    `if key is not None:` at writer.py 470, which looks right because a command
    that wrote nothing has nothing to remember. The retry then re-executes against
    the *new* state and walks 48-49 there: the source the other device opted in
    meanwhile is put back out, reported as `changed True` by a request whose answer
    was "nothing to do", with no event for a revocation nobody asked for.
    Asserted from the route, because the route is where a retry arrives and where
    the answer is what Control acts on: byte for byte the earlier answer,
    `replayed` True (server.py 335-340), the other device's row untouched at
    version 1, one event still.

    The last block pins the other half of the key's job: a spent key cannot be
    spent on a *different* ask, so a client bug cannot be answered with somebody
    else's "nothing to do"."""
    acc = account(db, user(db))
    token_a, _ = credential(db, 'r' * 32)
    token_b, _ = credential(db, 's' * 32)

    first = post(api, token_a, key='wk-1', owner_id=acc, kind='mcp', name='gh', opted_in=False)
    assert first._status == 200
    assert first.json() == {'opt_in': None, 'changed': False}
    assert first.replayed is not True
    assert opt_rows(db) == [] and changes(db) == []

    # the entry is opted in meanwhile, by another credential and another key
    opted_in = post(api, token_b, key='wk-2', owner_id=acc, kind='mcp', name='gh', opted_in=True)
    assert opted_in.json()['changed'] is True
    (row,) = opt_rows(db)
    assert (row.entity.opted_in, row.version) == (True, 1)

    again = post(api, token_a, key='wk-1', owner_id=acc, kind='mcp', name='gh', opted_in=False)
    assert again._status == 200
    assert again.json() == first.json()                 # byte for byte the earlier answer
    assert again.replayed is True                        # server.py 335-340
    (row,) = opt_rows(db)
    assert (row.entity.opted_in, row.version) == (True, 1)   # ...and nothing was undone
    assert len(changes(db)) == 1

    # a spent key buys its own ask, never somebody else's
    clash = post(api, token_a, key='wk-1', owner_id=acc, kind='mcp', name='other', opted_in=True)
    assert clash._status == 400
    assert clash.json()['error'] == 'invalid_request'
    assert clash.json()['detail']['field'] == 'idempotency_key'
    assert 'already used' in clash.json()['detail']['why']
    assert [r.entity.name for r in opt_rows(db)] == ['gh']
    assert len(changes(db)) == 1


# ───────────────────────────────────── 09. an opt-in inside a transaction that then fails

def test_09_an_opt_in_of_a_transaction_that_fails_leaves_neither_row_nor_event(db):
    """optins.py 50-52, 58-59 and 63-65: the insert, the version-bumping update and
    the `opt_in.changed` event are one transaction with the rest of the command.

    Closest existing tests: `test_a_stale_expected_version_refuses_the_flip_and_
    writes_nothing` (line 146), `test_a_non_boolean_opted_in_never_reaches_the_row`
    (line 378) and `test_a_name_of_128_okay_characters_is_written_and_129_rolls_
    back` (line 397) of tests/v1/unit/test_gaps_core_application_optins.py all
    roll a transaction back - but in each the failing statement is the *only*
    statement, so nothing that had already succeeded has to be taken back. The
    failure that comes *after* a successful change is the shape of every compound
    command (opt a source in and register the plugin that provides it, one
    command), and nothing covers it: the doomed transaction below holds a
    successful insert *and* a successful flip, and the one after it holds two
    successful changes plus a refusal.

    Killing it: detaching the audit from the write - removing 63-65 leaves the
    rows of the control transaction with no `opt_in.changed` event at all, which
    this test's control block catches on the committed run before it catches the
    doomed one - or a version of the write that commits ahead of the transaction
    (a row live for executions while its command was reported as having failed).
    Every assertion below is about the state the doomed transaction must leave
    *behind it*, which no existing test of the module observes."""
    actor = user(db)
    acc, prj = account(db, actor, 'A'), project(db, actor, 'p1')

    # the control: this transaction does complete, and shows the row and the event
    def whole(tx):
        optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='ctl', opted_in=True)
        optins.set_opt_in(tx, actor=actor, owner_id=prj, kind='source', name='project',
                          opted_in=True)
    db.writer.execute(whole, {})
    assert [(r.entity.name, r.entity.opted_in, r.version) for r in opt_rows(db)] == [
        ('ctl', True, 1), ('project', True, 1)]
    assert len(changes(db)) == 2

    class Sentinel(Exception):
        """The second statement of the same command failing for its own reason."""

    def doomed(tx):
        optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='gone', opted_in=True)
        optins.set_opt_in(tx, actor=actor, owner_id=prj, kind='source', name='project',
                          opted_in=False)
        raise Sentinel('a statement after the opt-ins failed')

    with pytest.raises(Sentinel):
        db.writer.execute(doomed, {})
    # nothing of the doomed transaction survived: neither row nor event
    assert [(r.entity.name, r.entity.opted_in, r.version) for r in opt_rows(db)] == [
        ('ctl', True, 1), ('project', True, 1)]
    assert [(e['payload']['name'], e['payload']['version']) for e in changes(db)] == [
        ('ctl', 1), ('project', 1)]
    with db.read() as r:
        assert optins.effective(r, account_id=acc, project_id=prj) == (
            ('account', 'mcp', 'ctl'), ('project', 'source', 'project'))
        assert len(optins.listing(r)) == 2

    # and the same when the failure is optins.py 40-41 refusing the *third* ask, in
    # a transaction whose first two would have committed
    def pair(tx):
        optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='good', opted_in=True)
        optins.set_opt_in(tx, actor=actor, owner_id=prj, kind='plugin', name='ok', opted_in=True)
        optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='x' * 129,
                          opted_in=True)

    with pytest.raises(ValueError, match='an opt-in names a source, plugin or MCP server'):
        db.writer.execute(pair, {})
    assert [r.entity.name for r in opt_rows(db)] == ['ctl', 'project']
    assert len(changes(db)) == 2
    # the writer and the reader are both still usable after the rolled back work
    assert ask(db, actor, acc, 'mcp', 'good', True)['changed'] is True
    assert [r.entity.name for r in opt_rows(db)] == ['ctl', 'project', 'good']


# ─────────────────────────────────────────── 10. what a reader sees while it is in flight

def test_10_a_reader_sees_no_opt_in_until_it_commits_and_exactly_one_after_it_has(db):
    """optins.py 47-56 answered from inside the transaction and 83-89 read by
    `effective`: a change is visible to a reader exactly once, as a row *and* its
    event together.

    Closest existing tests: `test_effective_names_exactly_this_accounts_and_this_
    projects_opted_in_rows` (line 225) of
    tests/v1/unit/test_gaps_core_application_optins.py and `test_I05_an_opt_in_
    applies_to_exactly_its_own_account_and_project` (line 166) of
    test_settings_sources.py both read *after* every command has committed, and
    `test_a_stale_expected_version_refuses_the_flip_and_writes_nothing` (line 146)
    checks only the after-state of a refused write. Nothing observes the state
    while a change is in flight - the window in which a mid-command commit, the
    obvious "make the dashboard snappier" edit to 50-52, shows a reader a live
    opted-in row whose `opt_in.changed` event does not exist yet (and the same
    edit at 63-65, an event whose row is not there). An execution admitted by a
    row that a later rollback removes is the fail-open this window hides.

    Deterministic, no sleeps: a raw transaction function hands over through two
    `threading.Event`s, so the read either observes the in-flight transaction or
    the test times out loudly, and row/event counts are compared at every
    observation point rather than only at the end."""
    actor = user(db)
    acc = account(db, actor)
    entered, release = threading.Event(), threading.Event()

    def in_flight(tx):
        entered.set()
        if not release.wait(60):
            raise AssertionError('the writer was never released')
        return optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='gh',
                                 opted_in=True)

    future = db.writer.submit(in_flight, {})
    assert entered.wait(60)
    with db.read() as r:
        assert optins.listing(r) == []
        assert optins.effective(r, account_id=acc, project_id=None) == ()
        assert r.execute("SELECT count(*) AS c FROM events WHERE type = 'opt_in.changed'"
                         ).fetchone()['c'] == 0
    release.set()
    out = future.result(60)
    assert (out['changed'], out['opt_in']['version']) == (True, 1)

    with db.read() as r:
        assert [(x['name'], x['opted_in'], x['version']) for x in optins.listing(r)] == [
            ('gh', True, 1)]
        assert optins.effective(r, account_id=acc, project_id=None) == (('account', 'mcp', 'gh'),)
    # row and event arrived as one: never a row without the change it reports
    assert len(opt_rows(db)) == len(changes(db)) == 1

    # and the same again for the flip, so the observation is not one-shot
    entered2, release2 = threading.Event(), threading.Event()

    def revoke(tx):
        entered2.set()
        if not release2.wait(60):
            raise AssertionError('the writer was never released')
        return optins.set_opt_in(tx, actor=actor, owner_id=acc, kind='mcp', name='gh',
                                 opted_in=False)

    future = db.writer.submit(revoke, {})
    assert entered2.wait(60)
    with db.read() as r:
        assert optins.effective(r, account_id=acc, project_id=None) == (('account', 'mcp', 'gh'),)
        assert [(x['name'], x['opted_in'], x['version']) for x in optins.listing(r)] == [
            ('gh', True, 1)]
    release2.set()
    assert (future.result(60)['changed'], future.result(60)['opt_in']['version']) == (True, 2)
    with db.read() as r:
        assert optins.effective(r, account_id=acc, project_id=None) == ()
        assert [(x['name'], x['opted_in'], x['version']) for x in optins.listing(r)] == [
            ('gh', False, 2)]
    assert len(opt_rows(db)) == 1 and len(changes(db)) == 2


