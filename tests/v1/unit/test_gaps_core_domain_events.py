"""T-720: the highest-risk uncovered branches of archeus/core/domain/events.py.

The envelope is the one place a wrong word or a wrong id becomes a stored and
published fact, so almost every branch here is a refusal: the closed vocabulary of
`TYPES` (an unregistered type, a subject of the wrong kind, a visibility outside
`VISIBILITIES`, an actor that is not a principal kind, an id that is not the id of
its kind), the payload's JSON contract, the writer cursor `seq`, the cause chain
bound, and the defaults of `from_envelope` / `new_event`.

Pure values only: no I/O, no OS, no thread, no process, no network, no sleep. The
one clock use is a bounded shape check on `now_iso()`. Same style and fixtures as
tests/v1/unit/test_gaps_core_domain_guards.py and the events block of
tests/v1/unit/test_domain.py; only the branches those files do not reach are
re-opened here. The `xfail(strict=True)` tests are source defects, not weakened
assertions — each is listed in the card report.
"""

import contextvars
import json
import pathlib
import re
import types
from datetime import datetime, timezone

import pytest

from archeus.core.domain import events, ids
from archeus.core.domain.values import PRINCIPAL_SCOPES, Ref

#: Pinned so every malformed variant below is a one-character edit of a known good id.
ULID = ids.new_ulid(at_ms=1_700_000_000_123, entropy=42)
PRN = 'prn_' + ULID
MSN = ids.new_id('mission')
#: The source line the duplicate-registration test anchors on; if it moves, that
#: test must fail loudly instead of silently checking nothing.
REGISTRY_LINE = 'REGISTRY = {row[0]: row for row in TYPES}'


def _subject_id(kind):
    """A plausible id for *kind*: minted for the kinds `ids` knows, a bare string
    for the three subject kinds that are not minted (harness, model,
    provider_terms — see ids.PREFIXES)."""
    return ids.new_id(kind) if kind in ids.PREFIXES else 'ref-%s-1' % kind


def _event(**kw):
    """A valid `mission.state_changed` event with one thing broken (or changed)."""
    kw.setdefault('type', 'mission.state_changed')
    kw.setdefault('id', ULID)
    kw.setdefault('at', events.now_iso())
    kw.setdefault('subject', Ref('mission', MSN))
    kw.setdefault('actor', Ref('user_device', PRN))
    return events.Event(**kw)


def _chain(n):
    return tuple(ids.new_ulid(at_ms=1_700_000_000_000 + i, entropy=i) for i in range(n))


def _refused(**kw):
    """Build an event that must be refused and return the message it refused with."""
    with pytest.raises(ValueError) as got:
        _event(**kw)
    return str(got.value)


def _raised(frame):
    """`from_envelope` of a frame that must be refused -> the message it refused with."""
    with pytest.raises(ValueError) as got:
        events.Event.from_envelope(frame)
    return str(got.value)


ALL_TYPES = [row[0] for row in events.TYPES]


# ── the payload's JSON contract (events.py:226-232) ──────────────────────────

@pytest.mark.parametrize('payload', [
    {'when': object()},                       # no JSON encoder for it
    {'when': {1, 2}},                          # a set is not JSON either
    {'nested': {'deeper': [object()]}},        # the try/except must reach inwards
], ids=['object', 'set', 'nested-object'])
def test_a_payload_the_encoder_cannot_write_is_refused(payload):
    """events.py:229-232: dropping the json.dumps probe (or the except) would let
    a command publish an event the writer's json.dumps(event.payload) then dies
    on — inside the transaction that is recording the fact."""
    assert 'payload is not JSON-serialisable' in _refused(payload=payload)


@pytest.mark.parametrize('payload', [
    [1, 2], 'a string', 7, 7.5, ('a',), {'a'}, object(), True,
], ids=['list', 'str', 'int', 'float', 'tuple', 'set', 'object', 'bool'])
def test_a_payload_that_is_not_a_mapping_is_refused(payload):
    """events.py:226-227: `not isinstance(payload, dict)` is the only thing that
    keeps a list or a bare string in the payload column, where every reader
    (`public_event`, the SSE frame, the automations projection) indexes it."""
    assert 'payload is a JSON object' in _refused(payload=payload)


@pytest.mark.parametrize('payload', [
    {}, {'from': 'CREATED', 'to': 'UNDERSTANDING'}, {'killed': 0}, {'flag': False},
    {'nothing': None}, {'list': [1, 'two', None, True]}, {'deep': {'x': [{'y': 1.5}]}},
    {'text': 'ünïcøde — 日本語'}, {'keys': {'a b': 'c/d'}},
], ids=['empty', 'state', 'zero', 'false', 'null', 'list', 'deep', 'unicode', 'odd-keys'])
def test_a_real_json_payload_is_kept_and_survives_the_wire(payload):
    """events.py:228-230 pass + 236-254: the accepted side of the JSON gate, and
    the round-trip the failures below are measured against."""
    ev = _event(payload=payload)
    assert ev.payload == payload
    assert events.Event.from_envelope(json.loads(json.dumps(ev.to_envelope()))) == ev


def _strict_json(text):
    """json.loads that refuses the non-JSON literals a browser's JSON.parse refuses."""
    def reject(name):
        raise ValueError('%r is not JSON' % name)
    return json.loads(text, parse_constant=reject)


@pytest.mark.parametrize('payload', [
    {'x': float('nan')}, {'x': float('inf')}, {'x': float('-inf')},
    {'x': [float('nan')]}, {1: 'a'}, {'mixed': {2: 'b'}},
], ids=['nan', 'inf', '-inf', 'nan-in-list', 'integer-key', 'nested-integer-key'])
def test_a_payload_that_is_not_really_json_never_survives_the_wire(payload):
    """The fail-closed answer is a refusal; the test passes only when the event
    cannot be built at all, so a source that quietly accepts it (today) or that
    invents a wire value for it stays red."""
    with pytest.raises(ValueError) as got:
        ev = _event(payload=payload)
        frame = json.dumps(ev.to_envelope())
        assert events.Event.from_envelope(_strict_json(frame)) == ev
    assert 'payload' in str(got.value)


# ── the closed vocabulary of TYPES (events.py:200-209) ───────────────────────

@pytest.mark.parametrize('type_', [
    'mission.learned', 'mission.state_change', 'mission.state_Changed', 'Mission.created',
    'mission.created ', ' mission.created', 'mission.created\n', 'MISSION.CREATED',
    'execution.state-changed', 'core.estop', 'core.stop', 'session.resume',
    'task.statechange', 'approval.request', 'verification.changed', 'idea.state_changed ',
    'legacy.worklog2', '', 'none', 'null', 'unknown', None, 0, True, 1.5,
], ids=['learned', 'state-change', 'state-Changed', 'capital-M', 'trailing-space',
        'leading-space', 'trailing-newline', 'all-caps', 'hyphen', 'estop', 'stop', 'resume',
        'statechange', 'request', 'verification-changed', 'idea-trailing-space', 'worklog2',
        'empty', 'none-word', 'null-word', 'unknown-word', 'none-value', 'zero', 'true',
        'float'])
def test_a_word_that_is_not_in_the_registry_is_refused(type_):
    """events.py:200-202: REGISTRY.get is the only gate on what can happen; a
    near-miss word (or a non-string) that fell through would be stored, indexed
    and pushed to clients as a fact no phase ever declared."""
    assert 'unregistered event type' in _refused(type=type_)


def test_an_unregistered_type_is_refused_before_anything_else_is_checked():
    """events.py:201-202 raises before the problems loop (205-234): a garbage type
    must be named as the problem even when the rest is garbage too, so no caller
    can read the message as "the payload was the only issue"."""
    msg = _refused(type='mission.learned', id='nope', subject=Ref('task', 'tsk_x'),
                   actor=Ref('robot', 'x'), visibility='private', seq=0)
    assert msg.startswith('unregistered event type')
    for hidden in ('id is not a ULID', 'not a principal kind', 'visibility must be',
                   'seq is a positive integer'):
        assert hidden not in msg


def test_every_problem_of_one_event_is_reported_together_in_source_order():
    """events.py:205-234: `problems` accumulates and is joined once. Raising on
    the first problem (or reordering the checks) would hide the real cause of a
    rejected write behind whichever guard happened to fire first."""
    msg = _refused(id='nope', subject=Ref('task', ids.new_id('task')),
                   actor=Ref('robot', PRN), visibility='private')
    assert msg == ('invalid mission.state_changed event: id is not a ULID; %s is about a '
                   'mission, not a task; actor kind \'robot\' is not a principal kind; '
                   'visibility must be user or system' % 'mission.state_changed')


@pytest.mark.parametrize('type_', ALL_TYPES)
def test_every_registered_type_refuses_a_subject_of_the_wrong_kind(type_):
    """events.py:208-209 for all 80 declared types: `execution.ended` about a
    mission, or `mission.created` about a task, must be refused — the subject kind
    is what every read path (and the client's routing) keys on."""
    row = events.REGISTRY[type_]
    wrong = 'mission' if row[1] != 'mission' else 'task'
    msg = _refused(type=type_, subject=Ref(wrong, _subject_id(wrong)))
    assert msg == 'invalid %s event: %s is about a %s, not a %s' % (type_, type_, row[1], wrong)


@pytest.mark.parametrize('type_', ALL_TYPES)
def test_every_registered_type_is_accepted_about_its_own_subject(type_):
    """events.py:203-204 + 208: the mirror side — with the registry's own subject
    kind nothing else may refuse, and the visibility is the registry default
    because `visibility=None` means "whatever the row says"."""
    row = events.REGISTRY[type_]
    ev = _event(type=type_, subject=Ref(row[1], _subject_id(row[1])))
    assert ev.visibility == row[2] and ev.seq is None and ev.cause_chain == ()
    assert ev.payload == {} and ev.workspace == ids.GLOBAL_WORKSPACE and ev.project is None


#: Rows whose declared subject kind a reader would get wrong from the type name
#: alone (or right only by luck): the pairing the registry, not the word, decides.
TRAPS = {
    'integration.state_changed': 'task',        # about a Task, not an "Integration"
    'architecture.state_changed': 'repository',  # about a Repository, not an inspection
    'archeus_call.ended': 'route_decision',
    'route.decided': 'route_decision',
    'account_health.state_changed': 'account',
    'usage.observed': 'account',
    'user.digest_acked': 'user',
    'pause_batch.created': 'pause_batch',
    'artifact.recorded': 'artifact_record',
    'repository.model_added': 'repository',
    'project.changed': 'project',
    'device.stream_opened': 'device',
}


@pytest.mark.parametrize('type_', sorted(TRAPS))
def test_the_subject_kind_of_a_row_whose_word_does_not_name_it(type_):
    """events.py:152 (REGISTRY) + 208: these rows say one thing in the type and
    carry another in `subject_kind`; reading `row[1]` from the name would move the
    fact to the wrong object."""
    assert events.REGISTRY[type_][1] == TRAPS[type_]


def test_the_registry_is_a_closed_table_of_five_field_rows_with_one_entry_each():
    """events.py:152-153: REGISTRY is keyed by row[0]; a row that repeats a type
    (or a row that is not a 5-tuple) must be caught at import, before a phase can
    emit a type whose row was silently overwritten by a later one."""
    assert len(events.REGISTRY) == len(events.TYPES) == len(set(ALL_TYPES))
    for row in events.TYPES:
        assert len(row) == 5 and events.REGISTRY[row[0]] is row
        assert isinstance(row[3], bool) and row[2] in events.VISIBILITIES and row[4]


def _exec_events_source(extra=''):
    """Run events.py's own module source in a throwaway namespace, optionally with
    `extra` injected just above the REGISTRY line, so the module's OWN assert
    statement is what does (or fails to do) the work."""
    src = pathlib.Path(events.__file__).read_text(encoding='utf-8')
    assert REGISTRY_LINE in src, 'events.py no longer builds REGISTRY on its own line'
    ns = {'__name__': 'archeus.core.domain.events_under_test',
          '__package__': 'archeus.core.domain', '__file__': events.__file__}
    exec(compile(src.replace(REGISTRY_LINE, extra + REGISTRY_LINE, 1),
                 events.__file__, 'exec'), ns)
    return ns


def test_a_type_registered_twice_killsthe_module_at_import():
    """events.py:153 (`assert len(REGISTRY) == len(TYPES)`): with the assert
    removed, TYPES keeps both rows and REGISTRY keeps only the last one, so the
    first phase to register `mission.created` loses its subject kind and
    visibility to whoever registered the duplicate."""
    with pytest.raises(AssertionError) as got:
        _exec_events_source('TYPES = tuple(TYPES) + (TYPES[0],)\n')
    assert 'registered twice' in str(got.value)


def test_the_same_module_with_a_clean_registry_imports_and_agrees():
    """events.py:152-153, the passing side: the injected duplicate above must be
    the only reason that exec refuses, so the check is on the table and not on the
    exec machinery."""
    ns = _exec_events_source()
    assert len(ns['REGISTRY']) == len(ns['TYPES']) == len(events.TYPES)
    assert [r[0] for r in ns['TYPES']] == ALL_TYPES


# ── notify_default and visibility: who gets woken up (TYPES rows) ────────────

#: Only these three facts are allowed to ping a device. A fourth, or one of these
#: flipped to False, is a silent emergency stop or an unread approval.
MUST_NOTIFY = {'core.estopped', 'approval.requested', 'account.health_changed'}


def test_only_the_three_pings_notify_and_all_of_them_stay_user_visible():
    """events.py:203-204 reads row[2]; the notify_default of row[3] is the whole
    difference between an e-stop the owner is told about and one they discover: an
    inversion here is invisible everywhere but on the device."""
    assert {row[0] for row in events.TYPES if row[3]} == MUST_NOTIFY
    for type_ in MUST_NOTIFY:
        assert events.REGISTRY[type_][2] == 'user', type_


@pytest.mark.parametrize('type_, visibility', [
    ('core.estopped', 'user'), ('core.rearmed', 'user'),
    ('approval.requested', 'user'), ('approval.state_changed', 'user'),
    ('execution.intent', 'system'), ('execution.state_changed', 'user'),
    ('execution.started', 'user'), ('execution.progress', 'system'),
    ('execution.ended', 'user'), ('execution.prepared', 'system'),
    ('execution.hook', 'system'), ('execution.halted', 'system'),
    ('execution.adopted', 'user'), ('session.resumed', 'system'),
    ('session.created', 'user'), ('session.observed', 'system'),
    ('knowledge_item.purged', 'system'), ('message.created', 'user'),
    ('policy_decision.created', 'system'), ('route.decided', 'system'),
    ('automation_run.created', 'system'), ('device.stream_opened', 'system'),
    ('usage.observed', 'system'), ('principal.created', 'system'),
    ('legacy.worklog', 'system'),
], ids=lambda v: v if isinstance(v, str) and '.' in v else '')
def test_the_user_timeline_and_the_system_only_rows_are_who_the_registry_says(
        type_, visibility):
    """events.py:203-204: `visibility=None` takes row[2]; flipping `system` to
    `user` on execution.hook leaks internal decisions into the owner's timeline,
    and flipping `user` to `system` on execution.ended hides a finished run."""
    assert events.REGISTRY[type_][2] == visibility
    assert _event(type=type_, subject=Ref(events.REGISTRY[type_][1],
                                          _subject_id(events.REGISTRY[type_][1]))
                  ).visibility == visibility


@pytest.mark.parametrize('visibility', [
    'private', 'USER', 'User', 'user ', '', 'system ', 'everyone', 'sys', 'internal',
    'owner', True, False, 0, 1, ['user'],
], ids=['private', 'USER', 'User', 'user-space', 'empty', 'system-space', 'everyone', 'sys',
        'internal', 'owner', 'true', 'false', 'zero', 'one', 'list'])
def test_a_visibility_outside_the_two_words_is_refused(visibility):
    """events.py:155 + 214-215: VISIBILITIES is an allowlist compared with `in`;
    a truthy or oddly cased lookalike must not reach the column, because the read
    path filters on equality with 'user'."""
    assert 'visibility must be user or system' in _refused(visibility=visibility)


def test_the_two_declared_visibilities_are_accepted_verbatim():
    """events.py:214: the passing side of the same comparison."""
    assert _event(visibility='user').visibility == 'user'
    assert _event(visibility='system').visibility == 'system'


# ── the actor is a principal, and only a principal (events.py:210-213) ───────

@pytest.mark.parametrize('kind', sorted(PRINCIPAL_SCOPES))
def test_every_principal_kind_may_act_with_a_principal_id(kind):
    """events.py:210: PRINCIPAL_SCOPES is the vocabulary, read from values.py so a
    new principal kind there is accepted here without a second list to forget."""
    assert _event(actor=Ref(kind, PRN)).actor.kind == kind


@pytest.mark.parametrize('kind', [
    'user', 'robot', 'mission', 'task', 'device', 'session', 'project', 'identity',
    'user_device_', 'userdevice', 'User_device', 'system_', 'automation_', 'NODE',
], ids=['user', 'robot', 'mission', 'task', 'device', 'session', 'project', 'identity',
        'user_device-', 'userdevice', 'User_device', 'system-', 'automation-', 'NODE'])
def test_a_kind_that_holds_no_scope_may_not_act(kind):
    """events.py:210-211: `user` is a subject kind and `identity`/`device` are id
    kinds, none of them principals; `User_device`, `system_` and `NODE` are the
    near-misses a hand-typed string produces. This is the field the audit trail
    and the authority check read, so a lookalike must never be accepted."""
    assert 'is not a principal kind' in _refused(actor=Ref(kind, PRN))


@pytest.mark.parametrize('actor_id', [
    'prn_', 'prn', PRN.lower(), PRN[:-1], PRN + 'A', 'prn_' + ULID.replace('0', 'O', 1),
    'prn_' + '9' + ULID[1:], 'ws_global', 'usr_' + ULID, 'exe_' + ULID, 'dvc_' + ULID,
    'prn_' + ULID[:13] + '_' + ULID[14:], MSN,
], ids=['prefix-only', 'bare-prn', 'lowercase', 'one-short', 'one-long', 'letter-O',
        'time-overflow', 'ws-global', 'usr', 'exe', 'dvc', 'inner-underscore', 'msn'])
def test_an_actor_id_that_is_not_a_minted_principal_id_is_refused(actor_id):
    """events.py:212-213: ids.is_id is called with 'principal', so the `ws_global`
    reserved-row bypass inside it must not reach the actor, an execution id must
    never act as a principal, and a Crockford-forbidden letter or a 48-bit time
    overflow is not an id."""
    assert 'is not a principal id' in _refused(actor=Ref('user_device', actor_id))


# ── the id rules of the envelope (events.py:206, 220-223) ────────────────────

@pytest.mark.parametrize('bad_id', [
    '', 'nope', ULID.lower(), ULID[:-1], ULID + 'A', ULID.replace('0', 'O', 1),
    ULID.replace('0', 'U', 1), ULID.replace('1', 'I', 1), '9' + ULID[1:], MSN,
    MSN[len('msn_'):].lower(), None, 42,
], ids=['empty', 'nope', 'lowercase', 'one-short', 'one-long', 'letter-O', 'letter-U',
        'letter-I', 'time-overflow', 'prefixed', 'prefixed-lower', 'none', 'int'])
def test_an_event_id_that_is_not_a_ulid_is_refused(bad_id):
    """events.py:206-207: the id is the ordering key before the writer hands out
    `seq`, so a 25-char, lowercase, I/L/O/U-bearing or time-overflowing id is
    refused rather than sorted into the wrong place in the log."""
    assert 'id is not a ULID' in _refused(id=bad_id)


def test_the_event_id_is_the_pinned_ulid_and_is_kept_verbatim():
    """events.py:206 passing side + 259: `new_event` mints one, an explicit one is
    kept as given (a replay must be able to re-emit the same id)."""
    assert _event(id=ULID).id == ULID
    assert events.new_event('mission.created', Ref('mission', MSN),
                            Ref('user_device', PRN), id=ULID).id == ULID


@pytest.mark.parametrize('workspace', [
    ids.GLOBAL_WORKSPACE, ids.new_id('workspace'), ids.new_id('workspace'),
], ids=['global', 'ws-1', 'ws-2'])
def test_the_two_kinds_of_workspace_id_are_accepted(workspace):
    """events.py:220-221: the reserved `ws_global` and a minted `ws_…` only —
    ids.is_id's one special case (ids.py:112-113) is reached through here."""
    assert _event(workspace=workspace).workspace == workspace


@pytest.mark.parametrize('workspace', [
    '', 'global', 'ws_global ', 'WS_GLOBAL', ' ws_global', 'ws_', 'ws_globalx', 'wsx_global',
    None, 42, ids.new_id('organization'), ids.new_id('project'), ids.new_id('system'), MSN,
], ids=['empty', 'global', 'global-space', 'GLOBAL', 'space-global', 'ws-', 'global-x',
        'wsx-global', 'none', 'int', 'org', 'prj', 'sys', 'msn'])
def test_a_workspace_that_is_not_a_workspace_id_is_refused(workspace):
    """events.py:220-221: an organisation, project or system id in the workspace
    column would scope the event — and every subscriber that filters by it — to
    rows it does not own."""
    assert 'workspace is not a workspace id' in _refused(workspace=workspace)


@pytest.mark.parametrize('project', [None, ids.new_id('project'), ids.new_id('project')],
                         ids=['none', 'prj-1', 'prj-2'])
def test_a_project_is_optional_and_otherwise_a_minted_project_id(project):
    """events.py:222: `project is not None and ...` — None is the unscoped case
    and must stay valid (an event with no project is a workspace-wide fact)."""
    assert _event(project=project).project is project


@pytest.mark.parametrize('project', [
    '', 'prj_', ids.new_id('mission'), ids.new_id('task'), 'ws_global', 'ws_' + ULID,
    'prj_' + ULID.lower(), 42,
], ids=['empty', 'prefix-only', 'msn', 'tsk', 'ws-global', 'ws', 'lowercase', 'int'])
def test_a_project_that_is_not_a_project_id_is_refused(project):
    """events.py:222-223: `ws_global` is a workspace id and nothing else; letting
    it through as a project would put a reserved row in the project filter."""
    assert 'project is not a project id' in _refused(project=project)


# ── the cause chain: its bound and its contents (events.py:166, 216-219) ─────

@pytest.mark.parametrize('n, ok', [(0, True), (1, True), (15, True), (16, True),
                                   (17, False), (40, False)],
                         ids=['0', '1', 'fifteen', 'sixteen', 'seventeen', 'forty'])
def test_the_cause_chain_boundary_is_exactly_max_cause_chain(n, ok):
    """events.py:216-217: `> MAX_CAUSE_CHAIN` — an off-by-one here either refuses
    the deepest legal chain a consumer can produce (breaking every deep trace) or
    accepts an unbounded one the writer has to store."""
    assert events.MAX_CAUSE_CHAIN == 16
    if ok:
        assert _event(cause_chain=_chain(n)).cause_chain == _chain(n)
    else:
        assert 'cause_chain is longer than 16' in _refused(cause_chain=_chain(n))


@pytest.mark.parametrize('entry', [
    '', 'msn_notanevent', MSN, ULID.lower(), ULID[:-1], ULID + 'A', None, 42, True,
], ids=['empty', 'msn-word', 'msn-id', 'lowercase', 'one-short', 'one-long', 'none', 'int',
        'bool'])
def test_a_cause_chain_holding_anything_but_a_ulid_is_refused(entry):
    """events.py:218-219: the chain is walked back through the log, so a mission
    id (or a lowercase/truncated id) in it is a dead end that turns a trace into a
    partial answer."""
    assert 'cause_chain holds event ids (ULIDs)' in _refused(cause_chain=(ULID, entry, ULID))


def test_a_cause_chain_of_one_mixed_in_entry_and_its_two_good_neighbours_is_still_refused():
    """events.py:218: `all(...)` over the chain — replacing it with `any(...)` (or
    dropping the loop) would keep a poisoned chain in a otherwise valid event."""
    assert 'cause_chain holds event ids (ULIDs)' in _refused(cause_chain=[ULID, 'x' * 26, ULID])


def test_a_cause_chain_handed_in_as_a_list_becomes_a_tuple():
    """events.py:197: the coercion is what keeps a frozen event hashable and the
    chain immutable against the caller's own list; without it the same list object
    could be mutated after validation."""
    given = list(_chain(3))
    ev = _event(cause_chain=given)
    assert isinstance(ev.cause_chain, tuple) and ev.cause_chain == _chain(3)
    given.append(ULID)
    assert ev.cause_chain == _chain(3)


@pytest.mark.parametrize('n', list(range(0, events.MAX_CAUSE_CHAIN + 1)),
                         ids=[str(i) for i in range(0, events.MAX_CAUSE_CHAIN + 1)])
def test_caused_by_always_emits_a_chain_the_next_writer_may_use(n):
    """events.py:164-166: `(... + (event.id,))[-MAX_CAUSE_CHAIN:]` is the only
    thing that keeps a consumer's appends inside the bound at 216; drop the slice
    and the 17th generation of events is refused mid-transaction, and dropping the
    `+ (event.id,)` loses the causal link of the whole chain."""
    parent = _event(cause_chain=_chain(n))
    chain = events.caused_by(parent)
    assert isinstance(chain, tuple) and len(chain) == min(n + 1, events.MAX_CAUSE_CHAIN)
    assert chain[-1] == parent.id                       # the parent itself is in it
    assert chain == tuple(list(_chain(n)) + [parent.id])[-events.MAX_CAUSE_CHAIN:]
    assert _event(cause_chain=chain).cause_chain == chain        # still legal
    if n:
        assert chain[0] == _chain(n)[max(0, n - events.MAX_CAUSE_CHAIN + 1)]  # oldest dropped


def test_caused_by_bounds_what_it_emits_whatever_the_chain_it_was_handed():
    """events.py:166: the `[-MAX_CAUSE_CHAIN:]` slice alone keeps the emitted chain
    inside the bound — an Event cannot even carry 40 causes (216 refuses it), so
    this is the truncation tested on its own, without the validator in the way."""
    given, own = _chain(40), ULID
    chain = events.caused_by(types.SimpleNamespace(id=own, cause_chain=given))
    assert len(chain) == events.MAX_CAUSE_CHAIN == 16
    assert chain[-1] == own and chain[0] == given[len(given) - (events.MAX_CAUSE_CHAIN - 1)]


def test_the_cause_chain_of_the_root_event_is_only_its_own_id():
    """events.py:166 with an empty chain: a route command outside a consumer stays
    its own root, so it must not inherit an empty tuple (which would make it
    untraceable) nor anything else's id."""
    ev = _event()
    assert ev.cause_chain == ()
    assert events.caused_by(ev) == (ev.id,)


def test_the_ambient_cause_of_a_consumer_lives_in_its_own_context():
    """events.py:161: CAUSE is a ContextVar, read by the writer; a chain set for
    one consumer must be invisible to the next one, or unrelated events inherit
    someone else's causes."""
    assert events.CAUSE.get() == ()
    chain = _chain(2)
    outer = contextvars.copy_context()

    def inner():
        token = events.CAUSE.set(chain)
        try:
            assert events.CAUSE.get() == chain
        finally:
            events.CAUSE.reset(token)
        assert events.CAUSE.get() == ()

    outer.run(inner)
    assert events.CAUSE.get() == ()


# ── seq: the writer's cursor (events.py:224-225) ─────────────────────────────

@pytest.mark.parametrize('seq', [None, 1, 2, 9, 2 ** 62],
                         ids=['none', 'one', 'two', 'nine', 'huge'])
def test_an_unassigned_or_strictly_positive_seq_is_kept(seq):
    """events.py:224: None (before the P2 writer) and any positive int are the two
    legal shapes of the SSE cursor."""
    assert _event(seq=seq).seq is seq


@pytest.mark.parametrize('seq', [0, -1, -99, 0.5, 1.0, 1.5, '1', '', ()],
                         ids=['zero', 'negative', 'very-negative', 'half', 'float-one',
                              'float-one-half', 'str', 'empty-str', 'tuple'])
def test_a_seq_that_is_not_a_positive_integer_is_refused(seq):
    """events.py:224-225: `seq` is what a client resumes after; 0 and a negative
    would replay the whole log, and a float or a string cannot be compared to the
    writer's integer cursor."""
    assert 'seq is a positive integer' in _refused(seq=seq)


def test_a_bool_is_not_a_sequence_number():
    with pytest.raises(ValueError) as got:
        _event(seq=True)
    assert 'seq is a positive integer' in str(got.value)


# ── the envelope both ways (events.py:194-199, 236-254) ───────────────────────

def test_an_event_made_from_wire_dicts_holds_real_refs_and_no_shared_dict():
    """events.py:194-196: the dict -> Ref coercion is what lets `subject.kind` at
    208 work on a decoded envelope; storing the dict instead would keep a mutable,
    key-typo-prone object inside a frozen event, and copying it by reference would
    let the caller change the subject after validation."""
    actor, subject = {'kind': 'user_device', 'id': PRN}, {'kind': 'mission', 'id': MSN}
    ev = _event(actor=actor, subject=subject)
    assert isinstance(ev.actor, Ref) and isinstance(ev.subject, Ref)
    actor['id'] = ids.new_id('principal')
    subject['kind'] = 'task'
    assert ev.actor.id == PRN and ev.subject.kind == 'mission'
    assert str(_refused(actor={'kind': 'user_device', 'id': 'nope'})) \
        .endswith("actor id 'nope' is not a principal id")


@pytest.mark.parametrize('field, ref', [
    ('actor', {'kind': 'user_device', 'id': ''}),
    ('actor', {'kind': '', 'id': PRN}),
    ('actor', {'kind': 'user_device', 'id': None}),
    ('actor', {'kind': None, 'id': PRN}),
    ('actor', {'kind': 'user_device', 'id': 42}),
    ('subject', {'kind': 'mission', 'id': ''}),
    ('subject', {'kind': '', 'id': MSN}),
    ('subject', {'kind': 'mission', 'id': 42}),
], ids=['actor-id-empty', 'actor-kind-empty', 'actor-id-none', 'actor-kind-none',
        'actor-id-int', 'subject-id-empty', 'subject-kind-empty', 'subject-id-int'])
def test_a_wire_ref_that_is_not_a_typed_reference_is_refused(field, ref):
    """events.py:194-196 builds the Ref from the frame's dict, so the Ref's own
    rule (values.py:13-14: a non-empty kind and id, both strings) is the envelope's
    rule too: a frame with `"actor": {"kind": "", "id": ""}` must never become an
    event whose actor no authority check can classify."""
    with pytest.raises(ValueError) as got:
        _event(**{field: ref})
    assert 'Ref needs a non-empty kind and id' in str(got.value)


def test_a_missing_payload_becomes_an_empty_dict_and_not_none():
    """events.py:198-199: every reader indexes payload (public.py:44-46 projects
    it); None would raise far from here, and a shared default dict would let one
    event's payload leak into the next."""
    a, b = _event(payload=None), _event()
    assert a.payload == {} and b.payload == {}
    assert a.payload is not b.payload
    a.payload['killed'] = 1
    assert b.payload == {}


def test_the_envelope_is_json_with_the_shape_of_api_section_3_1():
    """events.py:236-245: the ten keys, the two nested ref dicts, the scope pair,
    `list(cause_chain)` (241) and the resolved visibility. Returning the Refs or
    the tuple directly makes json.dumps of a frame fail; leaking `None` for
    visibility gives a client a filter value that matches nothing."""
    ev = _event(type='execution.hook', subject=Ref('execution', ids.new_id('execution')),
                cause_chain=_chain(2), seq=7, project=ids.new_id('project'),
                payload={'seq': 3, 'decision': 'ALLOW'})
    env = json.loads(json.dumps(ev.to_envelope()))
    assert set(env) == {'seq', 'id', 'type', 'at', 'actor', 'cause_chain', 'subject',
                        'scope', 'visibility', 'payload'}
    assert env['seq'] == 7 and env['type'] == 'execution.hook'
    assert env['actor'] == {'kind': 'user_device', 'id': PRN}
    assert env['subject'] == {'kind': 'execution', 'id': ev.subject.id}
    assert env['scope'] == {'workspace': ids.GLOBAL_WORKSPACE, 'project': ev.project}
    assert env['visibility'] == 'system' and env['payload'] == {'seq': 3, 'decision': 'ALLOW'}
    assert isinstance(ev.to_envelope()['cause_chain'], list)
    given = ev.to_envelope()
    given['cause_chain'].append('junk')
    assert ev.cause_chain == _chain(2)


@pytest.mark.parametrize('missing', ['id', 'type', 'at', 'actor', 'subject'],
                         ids=['id', 'type', 'at', 'actor', 'subject'])
def test_an_envelope_missing_a_required_field_is_refused_as_an_invalid_event(missing):
    env = _event().to_envelope()
    env.pop(missing)
    with pytest.raises(ValueError):
        events.Event.from_envelope(json.loads(json.dumps(env)))


@pytest.mark.parametrize('missing', ['id', 'type', 'at', 'actor', 'subject'],
                         ids=['id', 'type', 'at', 'actor', 'subject'])
def test_a_frame_missing_a_required_field_never_decodes_to_an_event(missing):
    """events.py:249-254, the part that holds whatever else changes: no Event may
    come out of a frame that carries no id, no type, no time, no actor or no
    subject — an `env.get(k, <fresh>)` here would invent one and publish it. (The
    xfail above pins that the refusal is the ValueError every other refusal is.)"""
    env = _event().to_envelope()
    env.pop(missing)
    with pytest.raises(Exception):
        events.Event.from_envelope(json.loads(json.dumps(env)))


@pytest.mark.parametrize('broken', [
    ({'actor': {'kind': 'user_device'}}, 'actor without an id'),
    ({'actor': None}, 'a null actor'),
    ({'subject': 'msn_x'}, 'a bare subject string'),
    ({'scope': 'ws_global'}, 'a scope that is not an object'),
    ({'cause_chain': 7}, 'a cause chain that is not iterable'),
], ids=['actor-no-id', 'actor-null', 'subject-string', 'scope-string', 'chain-int'])
def test_an_envelope_whose_fields_are_the_wrong_shape_is_refused_as_an_invalid_event(broken):
    over, _why = broken
    env = _event().to_envelope()
    env.update(over)
    with pytest.raises(ValueError):
        events.Event.from_envelope(json.loads(json.dumps(env)))


@pytest.mark.parametrize('field, value', [
    ('cause_chain', ULID),                        # tuple(26 chars) -> 26 one-char entries
    ('cause_chain', {'a': ULID}),                 # tuple(dict) -> its keys
    ('payload', 'a string'),
    ('seq', '7'),
    ('visibility', 'USER'),
    ('scope.project', 'prj_nope'),
], ids=['chain-bare-id', 'chain-dict', 'payload-str', 'seq-str', 'visibility-USER',
        'project-bad'])
def test_a_frame_carrying_a_field_of_the_wrong_type_is_refused_by_the_same_rules(field, value):
    """events.py:247-254 is the same constructor, not a bypass: whatever the frame
    claims, 206-232 has to agree. Reading `cause_chain` straight into the field
    (or trusting `payload` / `seq` / `visibility` from the wire) is how a client
    gets a trace that dies on the first walk-back or a cursor it cannot compare."""
    env = _event(project='prj_' + ULID).to_envelope()
    if field.startswith('scope.'):
        env['scope'][field.split('.')[1]] = value
    else:
        env[field] = value
    with pytest.raises(ValueError):
        events.Event.from_envelope(json.loads(json.dumps(env)))


@pytest.mark.parametrize('over, workspace, project', [
    ({'scope': None}, ids.GLOBAL_WORKSPACE, None),            # env.get('scope') or {}
    ({'scope': {}}, ids.GLOBAL_WORKSPACE, None),
    ({'scope': {'project': None}}, ids.GLOBAL_WORKSPACE, None),
    ({'scope': {'workspace': ids.GLOBAL_WORKSPACE}}, ids.GLOBAL_WORKSPACE, None),
], ids=['scope-null', 'scope-empty', 'scope-project-null', 'scope-global'])
def test_the_defaults_of_from_envelope_are_the_defaults_of_the_event(over, workspace, project):
    """events.py:249-253: a null scope is the same as no scope (`or {}`), and an
    absent workspace is the reserved global row — the two shapes a peer sends for
    "not scoped to a workspace". A missing key here must never mean None."""
    env = _event(project=None).to_envelope()
    env.update(over)
    back = events.Event.from_envelope(json.loads(json.dumps(env)))
    assert back.workspace == workspace and back.project == project


#: The one rich frame the optional-field decode tests below each lose one key from.
RICH = dict(type='execution.hook', subject=Ref('execution', 'exe_' + ULID), id=ULID,
            actor=Ref('user_device', PRN), at='2027-01-01T00:00:00.000Z', cause_chain=(ULID,),
            seq=7,
            project='prj_' + ULID, payload={'decision': 'ALLOW'})


@pytest.mark.parametrize('optional', ['seq', 'project', 'cause_chain', 'payload', 'visibility'],
                         ids=['seq', 'project', 'cause_chain', 'payload', 'visibility'])
def test_a_frame_that_omits_an_optional_field_decodes_to_the_event_with_its_default(optional):
    """events.py:250-254: every optional field of the envelope is read through a
    default (`env.get('seq')`, `env.get('cause_chain', ())`, `env.get('payload')`,
    `env.get('visibility')`). Drop one of those defaults and `None` (or, for the
    chain, `tuple(None)` which is a TypeError) reaches the constructor, so a frame
    from a peer that simply leaves the field out — the normal shape of a minimal
    event — stops decoding at all."""
    env = events.Event(**RICH).to_envelope()
    if optional == 'project':
        env['scope'].pop('project')                     # the scope object carries it
    else:
        env.pop(optional)
    wanted = {k: v for k, v in RICH.items() if k != optional}
    assert events.Event.from_envelope(json.loads(json.dumps(env))) == events.Event(**wanted)


def test_from_envelope_takes_the_registered_visibility_when_the_frame_omits_it():
    """events.py:203-204 through 254: an omitted visibility is not the string
    'None' and not 'user' by accident — it is re-read from the registry, so a frame
    cannot downgrade a system event by leaving the field out."""
    env = _event(type='execution.prepared',
                 subject=Ref('execution', ids.new_id('execution'))).to_envelope()
    env.pop('visibility')
    assert events.Event.from_envelope(env).visibility == 'system'


def test_from_envelope_refuses_a_frame_that_breaks_the_rules():
    """events.py:247-254 -> 200-234: the decoder is not a bypass, it is the same
    constructor: a bad type, visibility, actor or seq in a frame is refused."""
    good = _event().to_envelope()
    assert 'unregistered event type' in _raised(dict(good, type='x.created'))
    assert 'visibility must be user or system' in _raised(dict(good, visibility='private'))
    assert 'is not a principal id' in _raised(
        dict(good, actor={'kind': 'user_device', 'id': 'exe_' + ULID}))
    assert 'seq is a positive integer' in _raised(dict(good, seq=0))


# ── new_event and now_iso (events.py:169-171, 257-261) ────────────────────────

ISO_MS = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')


def test_the_events_clock_is_utc_milliseconds_with_a_z_and_no_offset():
    """events.py:169-171: `timespec='milliseconds'` and the `.replace('+00:00', 'Z')`
    are both load-bearing — a client that compares `at` strings, or parses them as
    RFC 3339, rejects microseconds and a '+00:00' suffix, and a local-time stamp
    would put a future event on the timeline."""
    stamp = events.now_iso()
    assert ISO_MS.fullmatch(stamp), stamp
    assert '+' not in stamp
    parsed = datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 300


def test_the_events_clock_never_goes_backwards_as_a_string():
    """events.py:171: the format is fixed-width, so `at` sorts as text; dropping
    the millisecond field (or the leading zeros it implies) makes a same-second
    pair of events sort in the wrong order."""
    stamps = [events.now_iso() for _ in range(20)]
    assert stamps == sorted(stamps)
    assert all(ISO_MS.fullmatch(s) for s in stamps)


def test_new_event_mints_an_id_and_a_time_and_honours_the_ones_it_is_given():
    """events.py:259-260: both are `setdefault`, so a replay can pin id and at
    while ordinary callers still get a fresh, monotonic ULID (an id minted twice
    would collide in the log's unique index)."""
    a = events.new_event('idea.created', Ref('idea', ids.new_id('idea')),
                         Ref('user_device', PRN))
    b = events.new_event('idea.created', Ref('idea', ids.new_id('idea')),
                         Ref('user_device', PRN))
    assert ids.is_ulid(a.id) and a.id != b.id and a.id <= b.id
    assert ISO_MS.fullmatch(a.at) and a.payload == {}
    pinned = events.new_event('idea.created', Ref('idea', ids.new_id('idea')),
                              Ref('user_device', PRN), id=ULID, at='2027-01-01T00:00:00.000Z',
                              payload={'captured': True})
    assert (pinned.id, pinned.at, pinned.payload) == (ULID, '2027-01-01T00:00:00.000Z',
                                                      {'captured': True})


def test_new_event_refuses_a_bad_event_through_the_same_door():
    """events.py:257-261 forwards to Event.__post_init__: the convenience wrapper
    must not be a way to emit an undeclared type or a non-principal actor."""
    with pytest.raises(ValueError) as got:
        events.new_event('mission.approved', Ref('mission', MSN), Ref('user_device', PRN))
    assert 'unregistered event type' in str(got.value)
    with pytest.raises(ValueError) as got:
        events.new_event('mission.created', Ref('mission', MSN),
                         Ref('user_device', ids.new_id('device')))
    assert 'is not a principal id' in str(got.value)
