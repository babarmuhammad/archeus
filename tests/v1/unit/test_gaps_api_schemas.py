"""T-309: the highest-risk uncovered branches of `archeus/api/schemas.py`.

`schemas.validate` is the whole request boundary in one line — `shapes.validate(
value, schema, field, types=TYPES)` — and before this file exactly two unit tests
had ever called it (test_presence_units.py, the P32 smuggling checks); everywhere
else it validated a live response inside an integration test. So a regression in a
*denial* path here was caught, if at all, by an end-to-end run on one platform.

The ten branches the card asked for, fail-closed first, are each named in the test
that owns it: the GLOBAL rule scope CREATE_RULE drops, the bounded launch scopes and
supersede slot, the never-null e-stop flag, the never-complete replay checkpoint and
the never-recorded external effect, the never-null approval decision, `True` is not an
integer, nullable-or-typed and never anything else, the dotted/indexed field path a 400
names, and the declared table the validator cannot check without raising `KeyError`
(a 500) instead of refusing.

Style follows tests/v1/unit/test_presence_units.py: plain functions, `parametrize`
with short ids, `pytest.raises(schemas.Invalid)`, literal payloads. Nothing here
touches the OS, the clock, a process, the network or an environment value, so the file
runs identically on Linux and Windows.
"""

import pytest

from archeus.api import routes, schemas
from archeus.core.context.levels import LEVELS, STORES
from archeus.core.domain import entities, states
from archeus.core.domain.values import ORIGINS

# ── the declared table, as the route table uses it ──


def _name_of(schema):
    """The module-level name a request body ships under ('CREATE_MISSION', …)."""
    return next(n for n, v in vars(schemas).items() if v is schema and n[:1].isupper())


def _request_bodies():
    out = {}
    for r in routes.ROUTES:
        if r.request_schema is not None:
            out[_name_of(r.request_schema)] = r.request_schema
    return out


BODIES = _request_bodies()
BODY_NAMES = sorted(BODIES)


def _sample(schema):
    """A value of exactly *schema*'s shape: every required field, the first enum member
    where one is declared, no optional field. Built from the declaration rather than
    copied, so a body that cannot be satisfied (a required name with no property, an
    empty enum) fails here instead of passing quietly."""
    if 'ref' in schema:
        return _sample(schemas.TYPES[schema['ref']])
    t = schema['type']
    if 'enum' in schema:
        return schema['enum'][0]
    if t == 'object':
        if 'properties' not in schema:
            return {}
        return {n: _sample(schema['properties'][n]) for n in schema.get('required', ())}
    return {'string': lambda: 'x', 'integer': lambda: 1, 'number': lambda: 1.5,
            'boolean': lambda: True, 'array': list}[t]()


def _with(base, **kw):
    return dict(base, **kw)


def _without(base, *names):
    return {k: v for k, v in base.items() if k not in names}


def _body_of(owner):
    """A declared shape by the name it carries in the module: 'CREATE_MISSION',
    'KEYED_VERSIONED', or 'TYPES.Ledger' for one of the named response types."""
    return schemas.TYPES[owner[6:]] if owner.startswith('TYPES.') else getattr(schemas, owner)


def _refuses(schema, value, want_field=None, why=None):
    """validate(*value*) at the top level and hand back the Invalid it raised (fails if
    it returns). The path a refusal names is the point of most of these tests, so it is
    asserted here rather than passed into the validator."""
    with pytest.raises(schemas.Invalid) as e:
        schemas.validate(value, schema)
    if want_field is not None:
        assert e.value.field == want_field, '%r: field was %r' % (value, e.value.field)
    if why is not None:
        assert e.value.why.startswith(why), '%r: why was %r' % (value, e.value.why)
    return e.value


# ── minimal valid payloads for the shapes these tests bend ──

CRITERION = {'text': 'the ui says so', 'check': 'automatic'}
WORKER = {'state': 'idle', 'pending': 0}
TASK = {'id': 'tsk_1', 'key': 't1', 'title': 'do it', 'kind': 'code_change', 'state': 'PENDING',
        'depends_on': [], 'acceptance': [{'text': 'the test passes', 'check': 'automatic'}]}
PLAN = {'id': 'pln_1', 'mission_id': 'msn_1', 'plan_version': 1, 'state': 'PROPOSED',
        'tasks': [TASK], 'waves': [['t1']], 'current': True, 'current_why': 'the plan in force'}
LEDGER = {'tokens_today': 12, 'cost_today': 0.25, 'running': 0,
          'complete': {'tokens': False, 'cost': False}}
HEALTH = {'core': {'pid': 4242, 'started_at': '2026-10-30T09:00:00+00:00', 'version': '1.0.0',
                   'schema': 7, 'ports': 'real'},
          'engine': {'state': 'running', 'observed_seq': 3, 'parked': 0},
          'world': {'state': 'idle', 'pending': 0},
          'knowledge': dict(WORKER), 'intent': dict(WORKER), 'plan': dict(WORKER),
          'policy': dict(WORKER), 'metrics': dict(WORKER), 'armed': True}
CHECKPOINT = {'id': 'chk_1', 'execution_id': 'exe_1', 'task_id': 'tsk_1',
              'files_changed': ['a.py'], 'files_are': 'paths', 'complete': False,
              'item_limit': 30, 'reason': 'at the task boundary'}
HISTORY = {'answer': 'RECORDED', 'reason': 'the event store answers', 'floor': 1, 'head': 9,
           'oldest_retained_at': None, 'event_days': 30, 'open_mission_extension': False,
           'gap': ''}
EXTERNAL_EFFECTS = {'answer': 'UNKNOWN', 'reason': 'external_effects_not_recorded'}

DECIDE_OK = {'decision': 'approve', 'action_hash': 'a1b2c3', 'idempotency_key': 'k1'}
RULE_OK = {'scope_level': 'USER', 'action_class': 'read', 'decision': 'ASK',
           'idempotency_key': 'k1'}


# ══ fail-closed and denial paths first ════════════════════════════════════════════════════════

def test_a_policy_rule_can_never_be_written_at_global_scope():
    """CREATE_RULE's `scope_level` (schemas.py:1114) is `SCOPE_LEVELS[1:]`: dropping
    GLOBAL is the only thing between a client and a rule that outranks every profile.
    Invert the slice, or hand-edit the enum, and this is what fails."""
    assert 'GLOBAL' in entities.SCOPE_LEVELS, 'the domain no longer names GLOBAL at all'
    enum = schemas.CREATE_RULE['properties']['scope_level']['enum']
    assert set(enum) == set(entities.SCOPE_LEVELS) - {'GLOBAL'}, enum
    _refuses(schemas.CREATE_RULE, _with(RULE_OK, scope_level='GLOBAL'), 'scope_level',
             'must be one of')
    _refuses(schemas.CREATE_RULE, _with(RULE_OK, scope_level=None), 'scope_level', 'is required')
    for level in entities.SCOPE_LEVELS[1:]:
        schemas.validate(_with(RULE_OK, scope_level=level), schemas.CREATE_RULE)


@pytest.mark.parametrize('scopes', [['observe', 'control', 'approve', 'admin'], ['observe'], []],
                         ids=['all', 'one', 'none'])
def test_a_launch_code_grants_only_the_scopes_the_table_names(scopes):
    """LAUNCH_CODE (schemas.py:1037-1042) is the body that mints authority; the item
    enum is its ceiling, and the minter's own scopes bound it further (P15 §6)."""
    schemas.validate({'scopes': scopes}, schemas.LAUNCH_CODE)
    assert set(schemas.LAUNCH_CODE['properties']['scopes']['items']['enum']) == {
        'observe', 'control', 'approve', 'admin'}


@pytest.mark.parametrize('scopes,field', [
    (['supervise'], 'scopes[0]'), (['observe', ''], 'scopes[1]'), ([None], 'scopes[0]'),
    ([True], 'scopes[0]'), ('observe', 'scopes'), ([['observe']], 'scopes[0]'),
    ([{'scope': 'admin'}], 'scopes[0]'),
], ids=['invented', 'blank', 'null', 'flag', 'not-a-list', 'nested-list', 'object-item'])
def test_a_launch_code_cannot_grant_a_scope_it_does_not_know(scopes, field):
    """shapes.py:35-39, 40 and 53 on the one array whose items are privilege names."""
    _refuses(schemas.LAUNCH_CODE, {'scopes': scopes}, field)


@pytest.mark.parametrize('slot,ok', [
    ('desktop shell', True), ('desktop shell page', True), (None, True),
    ('cli', False), ('web', False), ('desktop', False), ('', False), (0, False), (False, False),
], ids=['shell', 'page', 'null', 'cli', 'web', 'desktop', 'blank', 'zero', 'flag'])
def test_only_the_desktop_shell_may_supersede_a_launch_slot(slot, ok):
    """`supersede` (schemas.py:1041) is `entities.SUPERSEDE_SLOTS`: anything else is a
    client naming which credential its redemption replaces (P20 D1)."""
    if ok:
        schemas.validate({'supersede': slot}, schemas.LAUNCH_CODE)
    else:
        _refuses(schemas.LAUNCH_CODE, {'supersede': slot}, 'supersede')


@pytest.mark.parametrize('which', ['Rearmed', 'Estopped', 'Health'],
                         ids=['rearm', 'estop', 'health'])
def test_the_e_stop_flag_is_a_boolean_and_never_a_null(which):
    """`armed` on Rearmed (schemas.py:740), Estopped (739) and Health (109) is a plain
    required boolean: an unknown e-stop state must never be readable as disarmed, and a
    dropped `nullable` here is a silent "safe" on a field nobody measured."""
    base = {'Rearmed': {'armed': True},
            'Estopped': {'armed': False, 'stopped': ['exe_1']},
            'Health': HEALTH}[which]
    schemas.validate(base, schemas.TYPES[which])
    assert 'armed' in schemas.TYPES[which]['required'] and 'nullable' not in \
        schemas.TYPES[which]['properties']['armed'], which
    for bad in (None, 'false', 'False', 1, 0, [], {}):
        _refuses(schemas.TYPES[which], _with(base, armed=bad), 'armed')
    _refuses(schemas.TYPES[which], _without(base, 'armed'), 'armed', 'is required')


def test_a_replay_checkpoint_never_claims_its_file_list_is_complete():
    """`complete: {'type': 'boolean', 'enum': [False]}` (schemas.py:293) is the promise
    that `files_changed` is a lower bound: accepting True reports a truncated diff as
    the whole change, which is what an approval is then decided on."""
    schemas.validate(CHECKPOINT, schemas.TYPES['ReplayCheckpoint'])
    assert 'complete' in schemas.TYPES['ReplayCheckpoint']['required']
    for bad, why in ((True, 'must be one of False'), ('true', 'must be a boolean'),
                     (1, 'must be a boolean'), (None, 'is required')):
        _refuses(schemas.TYPES['ReplayCheckpoint'], _with(CHECKPOINT, complete=bad), 'complete',
                 why)
    _refuses(schemas.TYPES['ReplayCheckpoint'], _without(CHECKPOINT, 'complete'), 'complete',
             'is required')


def test_a_replay_never_reports_an_external_effect_as_recorded():
    """`external_effects.answer` is the enum ['UNKNOWN'] (schemas.py:325-327): Core
    cannot prove an external effect happened, and the whole point of the replay view is
    that it says so rather than implying it did not."""
    props = schemas.TYPES['Replay']['properties']['external_effects']
    schemas.validate(EXTERNAL_EFFECTS, props)
    assert props['required'] == ['answer', 'reason']
    assert props['properties']['answer']['enum'] == ['UNKNOWN']
    for answer in ('RECORDED', 'NONE', 'unknown', 'MAY-HAVE-TAKEN-EFFECT', True):
        _refuses(props, _with(EXTERNAL_EFFECTS, answer=answer), 'answer')
    _refuses(props, _without(EXTERNAL_EFFECTS, 'answer'), 'answer', 'is required')
    _refuses(props, _with(EXTERNAL_EFFECTS, reason=None), 'reason', 'is required')


def test_the_event_history_never_extends_retention_for_an_open_mission():
    """`open_mission_extension: {'type': 'boolean', 'enum': [False]}` (schemas.py:310):
    while the window is not pinned open by an open mission, the API must say so — a True
    here is a promise that old events are still there."""
    schemas.validate(HISTORY, schemas.TYPES['ReplayHistory'])
    _refuses(schemas.TYPES['ReplayHistory'], _with(HISTORY, open_mission_extension=True),
             'open_mission_extension', 'must be one of False')
    _refuses(schemas.TYPES['ReplayHistory'], _with(HISTORY, open_mission_extension=None),
             'open_mission_extension', 'is required')


@pytest.mark.parametrize('field,value,why', [
    ('decision', None, 'is required'), ('decision', True, 'must be a string'),
    ('decision', 'APPROVE', 'must be one of'), ('decision', 'approve ', 'must be one of'),
    ('decision', '', 'must be one of'), ('decision', 1, 'must be a string'),
    ('action_hash', None, 'is required'), ('action_hash', True, 'must be a string'),
    ('action_hash', 123, 'must be a string'),
], ids=['null', 'flag', 'shout', 'trailing-space', 'blank', 'int', 'hash-null', 'hash-flag',
        'hash-int'])
def test_an_approval_is_never_decided_on_a_null_or_forged_decision(field, value, why):
    """DECIDE (schemas.py:1136-1141): the decision and the action hash it covers are both
    required and both non-nullable, so an approval can never be spent on a null decision
    nor on a body that dropped the hash and hopes."""
    schemas.validate(DECIDE_OK, schemas.DECIDE)
    assert schemas.DECIDE['required'][:2] == ['decision', 'action_hash']
    assert not any('nullable' in schemas.DECIDE['properties'][f] for f in ('decision',
                                                                           'action_hash'))
    _refuses(schemas.DECIDE, _with(DECIDE_OK, **{field: value}), field, why)
    _refuses(schemas.DECIDE, _without(DECIDE_OK, field), field, 'is required')


#: the fields a client may never choose for itself outside the session, account and
#: automation bodies that legitimately name them (p15-design-gate §15, P32)
SMUGGLED = ('model', 'harness_id', 'account_id', 'effort', 'resource_preferences', 'scopes',
            'principal', 'client_type', 'token', 'pin')
MAY_NAME_THEM = {
    'model': {'CREATE_SESSION', 'HANDOFF_SESSION', 'RESUME_SESSION'},
    'harness_id': {'CREATE_SESSION', 'HANDOFF_SESSION', 'REGISTER_ACCOUNT'},
    'account_id': {'CREATE_SESSION', 'HANDOFF_SESSION'},
    'effort': {'CREATE_SESSION', 'HANDOFF_SESSION', 'RESUME_SESSION'},
    'scopes': {'LAUNCH_CODE', 'PAIR_START'},
    'pin': {'PAIR_REDEEM'},
}


@pytest.mark.parametrize('name', BODY_NAMES, ids=BODY_NAMES)
@pytest.mark.parametrize('field', SMUGGLED, ids=SMUGGLED)
def test_a_body_names_a_choice_field_only_where_that_route_is_allowed_to(name, field):
    """The P32 check over the whole table instead of the two pairing bodies: a body
    outside MAY_NAME_THEM neither declares the field nor accepts it, so no request can
    carry a model, a harness, an account or a scope where the route does not take one."""
    declared = field in BODIES[name].get('properties', {})
    assert declared == (name in MAY_NAME_THEM.get(field, ())), (name, field)
    if not declared:
        _refuses(BODIES[name], _with(_sample(BODIES[name]), **{field: 'x'}), field,
                 'is not a known field')


@pytest.mark.parametrize('name', BODY_NAMES, ids=BODY_NAMES)
def test_a_closed_request_body_refuses_a_field_it_does_not_declare(name):
    """shapes.py:61-64's `raise` (not the `continue` two lines above): every one of the
    41 bodies is closed, which is what keeps any of them from growing a way to smuggle
    an argument past the boundary."""
    body = BODIES[name]
    assert 'open' not in body and 'properties' in body and 'required' in body, name
    _refuses(body, _with(_sample(body), **{'not_a_field': 1}), 'not_a_field',
             'is not a known field')


def test_an_empty_body_takes_no_field_at_all():
    """EMPTY (schemas.py:1035): `properties: {}` means the route that declares it takes
    a body of nothing; both refusals come from shapes.py:64."""
    _refuses(schemas.EMPTY, {'idempotency_key': 'k'}, 'idempotency_key', 'is not a known field')
    _refuses(schemas.EMPTY, {'any': None}, 'any', 'is not a known field')
    schemas.validate({}, schemas.EMPTY)


def test_a_command_body_requires_the_key_the_route_replays_on():
    """server._body refuses a command with no key (server.py:380-383) before the shape is
    looked at, so the body's own `required` is the second line of the same defence — a
    body that stops requiring it tells its clients the key is optional. And a body that
    takes a key on a route nobody enforces is worse: the client believes its retry is
    protected when nothing deduplicates it."""
    for r in routes.ROUTES:
        if r.request_schema is None:
            continue
        name, body = _name_of(r.request_schema), r.request_schema
        declares = 'idempotency_key' in body.get('properties', {})
        requires = 'idempotency_key' in body.get('required', ())
        if r.idempotent == 'required':
            assert declares and requires, (name, r.path)
            _refuses(body, _without(_sample(body), 'idempotency_key'), 'idempotency_key',
                     'is required')
        else:
            assert not declares, ('%s is not idempotent but takes a key' % r.path)
    assert len(BODIES) == 41, len(BODIES)      # every body the walked tests below cover


#: every unvalidated pass-through object reachable from a client body — a
#: `{'type': 'object'}` with no properties: any dict goes through unchecked
PASS_THROUGH = {'CREATE_RULE.boundary', 'CREATE_RULE.match', 'CREATE_AUTOMATION.template',
                'CREATE_AUTOMATION.trigger', 'DECLARE_CONSTRAINT.spec', 'FORGET.selector',
                'RESOURCE_POLICY.budgets', 'SIMULATE.action', 'SIMULATE.extra_rules[]'}


def test_the_unvalidated_object_fields_of_a_request_body_are_exactly_the_declared_nine():
    """`{'type': 'object'}` with no properties is the widest door in the subset: what
    comes through becomes the handler's problem, not the boundary's (shapes.py:54 skips
    the whole object branch). Adding one is a design decision, so it is named here."""
    found = set()

    def walk(node, where):
        if 'ref' in node:
            return
        if node.get('type') == 'object' and 'properties' not in node:
            found.add(where)
        for k, sub in (node.get('properties') or {}).items():
            walk(sub, '%s.%s' % (where, k))
        if 'items' in node:
            walk(node['items'], '%s[]' % where)

    for name, body in BODIES.items():
        walk(body, name)
    assert found == PASS_THROUGH, sorted(found ^ PASS_THROUGH)


# ══ boundary values ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('owner,field', [
    ('REPRIORITIZE', 'priority'), ('TYPES.Ledger', 'cost_today'),
    ('TYPES.ContextState', 'pressure'), ('TYPES.TraceStep', 'result'),
    ('TYPES.Automation', 'rate_limit'),
], ids=['priority', 'cost', 'pressure', 'result', 'rate-limit'])
def test_a_boolean_is_never_accepted_where_a_number_is_declared(owner, field):
    """shapes.py:36-37: `bool` subclasses `int`, so the validator has to say so. Without
    that clause `{'priority': True}` quietly becomes priority 1 and reorders dispatch,
    and a `False` cost is a free 0."""
    schema, base = _body_of(owner), _sample(_body_of(owner))
    good = {'priority': 1, 'cost_today': 0.25, 'pressure': 0.5, 'result': 0, 'rate_limit': 3}
    base = _with(base, **{field: good[field]})
    schemas.validate(base, schema)
    for flag in (True, False):
        _refuses(schema, _with(base, **{field: flag}), field, 'must be')


def test_an_integer_takes_no_float_and_a_number_takes_both():
    """shapes.py:35-39 with `_PY` (shapes.py:21-22): 'integer' is `int` alone, so a
    float is refused rather than truncated; 'number' is `int` or `float`."""
    _refuses(schemas.TYPES['Ledger'], _with(LEDGER, tokens_today=1.0), 'tokens_today',
             'must be an integer')
    _refuses(schemas.TYPES['Ledger'], _with(LEDGER, tokens_today='12'), 'tokens_today',
             'must be an integer')
    schemas.validate(_with(LEDGER, cost_today=1), schemas.TYPES['Ledger'])
    schemas.validate(_with(LEDGER, cost_today=0.25), schemas.TYPES['Ledger'])
    _refuses(schemas.TYPES['Ledger'], _with(LEDGER, cost_today='0.25'), 'cost_today',
             'must be a number')
    _refuses(schemas.REPRIORITIZE, {'idempotency_key': 'k', 'priority': '1'}, 'priority',
             'must be an integer')
    # and a boolean is not an integer even where 0/1 would do
    _refuses(schemas.REPRIORITIZE, {'idempotency_key': 'k', 'priority': False}, 'priority',
             'must be an integer')


@pytest.mark.parametrize('owner,field,value,why', [
    ('CREATE_MISSION', 'title', 7, 'must be a string'),
    ('CREATE_MISSION', 'title', True, 'must be a string'),
    ('CREATE_MISSION', 'success_criteria', {'a': 1}, 'must be an array'),
    ('CREATE_PROJECT', 'root_paths', 'a,b', 'must be an array'),
    ('ACCOUNT_STATE', 'enabled', 'true', 'must be a boolean'),
    ('ACCOUNT_STATE', 'enabled', 1, 'must be a boolean'),
    ('ACCOUNT_STATE', 'enabled', None, 'is required'),
    ('FORGET', 'selector', 'x', 'must be an object'),
    ('KEYED_VERSIONED', 'expected_version', '3', 'must be an integer'),
    ('LAUNCH_CODE', 'supersede', ['desktop shell'], 'must be a string'),
], ids=['str-int', 'str-flag', 'arr-dict', 'arr-str', 'bool-str', 'bool-int', 'bool-null',
        'obj-str', 'int-str', 'slot-list'])
def test_every_field_type_refuses_a_value_of_the_wrong_type(owner, field, value, why):
    """shapes.py:35-39 for each of the six declared types, on a field the route table
    actually reads: the message is what the client sees, so it is asserted too."""
    schema = _body_of(owner)
    _refuses(schema, _with(_sample(schema), **{field: value}), field, why)


@pytest.mark.parametrize('owner,field', [
    ('CREATE_MISSION', 'project_id'), ('REARM', 'step_up'), ('KEYED_VERSIONED',
                                                             'expected_version'),
    ('DECIDE', 'note'), ('PROVIDER_TERMS', 'rotation'), ('MISSION_RESOURCES', 'max_cost_band'),
], ids=['project', 'step-up', 'version', 'note', 'rotation', 'cost-band'])
def test_a_nullable_field_takes_null_or_a_value_of_its_type_and_never_anything_else(owner,
                                                                                    field):
    """shapes.py:27 (null and nullable: return) and 31-34 (null without it: refuse).
    `nullable` widens a field to null-or-typed; it never turns it into anything-goes,
    and the field stays optional."""
    schema = _body_of(owner)
    prop = schema['properties'][field]
    assert prop.get('nullable') is True, (owner, field)
    base = _sample(schema)
    schemas.validate(_with(base, **{field: None}), schema)
    schemas.validate(_without(base, field), schema)
    wrong = {'string': 1, 'integer': 1.5, 'number': 'x', 'boolean': 'true',
             'array': {}, 'object': 'x'}[prop['type']]
    _refuses(schema, _with(base, **{field: wrong}), field, 'must be')


def test_a_nullable_enum_takes_null_and_only_the_words_it_lists():
    """A nullable enum (18 of them) is the one combination where both the null branch and
    the enum branch must hold: null passes, a word outside the list does not."""
    _refuses(schemas.RESOURCE_POLICY, _with(_sample(schemas.RESOURCE_POLICY), consumption='yes'),
             'consumption', 'must be one of')
    _refuses(schemas.CREATE_RULE,
             _with(_sample(schemas.CREATE_RULE), outside='sometimes'), 'outside',
             'must be one of')
    for owner, field, value in (('RESOURCE_POLICY', 'consumption', 'last_resort'),
                                ('CREATE_RULE', 'outside', 'DENY'),
                                ('CLARIFY', 'choice', 'proceed'),
                                ('PROVIDER_TERMS', 'rotation', 'permitted')):
        schema = _body_of(owner)
        schemas.validate(_with(_sample(schema), **{field: value}), schema)


@pytest.mark.parametrize('which,field,value,why', [
    ('Mission', 'version', 'not a number', 'must be an integer'),
    ('AttentionItem', 'since', 7, 'must be a string'),
    ('OptIn', 'version', 'x', 'must be an integer'),
    ('RepositoryGraph', 'depth', None, 'is required'),
], ids=['mission', 'attention', 'opt-in', 'repo-graph'])
def test_an_open_type_takes_an_undeclared_field_but_still_checks_a_declared_one(which, field,
                                                                                value, why):
    """shapes.py:61-63: the `continue` is for an unknown name only. If it ever widened to
    the whole object, an open type's own declared fields would stop being validated —
    `Mission` is open precisely because clients carry extra keys on it."""
    open_type = schemas.TYPES[which]
    assert open_type.get('open') is True, which
    base = _sample(open_type)
    schemas.validate(_with(base, **{'a_field_that_is_not_there': {'nested': [1, 2]}}), open_type)
    _refuses(open_type, _with(base, **{field: value}), field, why)


@pytest.mark.parametrize('which', ['TraceStep', 'Client', 'Transition', 'CommandResult'],
                         ids=['step', 'client', 'transition', 'command'])
def test_a_closed_named_type_refuses_a_field_of_its_own_making(which):
    """The same branch's other side: a closed type refuses an invented key, so a client
    cannot answer a response shape with a field of its own and have it stored."""
    closed = schemas.TYPES[which]
    assert 'open' not in closed, which
    _refuses(closed, _with(_sample(closed), **{'invented': 1}), 'invented', 'is not a known field')


@pytest.mark.parametrize('name', BODY_NAMES, ids=BODY_NAMES)
def test_the_smallest_legal_body_is_exactly_the_required_fields(name):
    """shapes.py:56-58 names the missing required field by its bare name at the top
    level; and because the payloads are built from the declaration, a body that requires
    a name it never declared — one that 400s on every request — fails here as well."""
    body = BODIES[name]
    full = _sample(body)
    schemas.validate(full, body)
    assert set(full) == set(body['required']), name
    for missing in body['required']:
        _refuses(body, _without(full, missing), missing, 'is required')


# ══ the error path: what a 400 names ══════════════════════════════════════════════════════════

@pytest.mark.parametrize('body,owner,field', [
    ({'text': 'go on', 'idempotency_key': 'k', 'decision': {'approval_id': 'apr_1'}},
     'POST_MESSAGE', 'decision.action_hash'),
    ({'text': 'go on', 'idempotency_key': 'k',
      'decision': {'approval_id': 'a', 'action_hash': 'h', 'extra': 1}},
     'POST_MESSAGE', 'decision.extra'),
    ({'subject': {'kind': 'mission'}, 'signal': 'positive', 'idempotency_key': 'k'},
     'FEEDBACK', 'subject.id'),
    ({'subject': {'kind': 'mission', 'id': 'm', 'extra': 1}, 'signal': 'positive',
      'idempotency_key': 'k'}, 'FEEDBACK', 'subject.extra'),
    ({'subject': {'kind': 'mission', 'id': 'm'}, 'signal': 'sideways', 'idempotency_key': 'k'},
     'FEEDBACK', 'signal'),
    ({'action': {}, 'stage': 'nowhere'}, 'SIMULATE', 'stage'),
    ({'subject': {'kind': 'mission', 'id': 'm'}, 'levels': ['L0', 'nope']}, 'CONTEXT_PREVIEW',
     'levels[1]'),
    ({'owner_id': 'acc_1', 'kind': 'mcp', 'name': 'x', 'opted_in': 'yes',
      'idempotency_key': 'k'}, 'SET_OPT_IN', 'opted_in'),
], ids=['decision-hash', 'decision-extra', 'subject-id', 'subject-extra', 'signal-enum',
        'stage-enum', 'levels-item', 'opted-in-flag'])
def test_a_nested_object_refusal_names_the_dotted_path_the_client_sent(body, owner, field):
    """shapes.py:60 and 65: the name a 400 carries is the whole path, not the leaf, so
    the client can find the box to fix. `sub` is built once, at the parent."""
    _refuses(_body_of(owner), body, field)


def test_a_list_refusal_names_the_index_of_the_bad_item():
    """shapes.py:53: `field[i]` — and for a list of lists the path is built twice, so
    `waves[0][1]` is the only way Core can point at one broken wave edge."""
    _refuses(schemas.CREATE_MISSION,
             {'title': 't', 'objective': 'o', 'idempotency_key': 'k',
              'success_criteria': [dict(CRITERION), {'text': 'x', 'check': 'maybe'}]},
             'success_criteria[1].check', 'must be one of automatic, human')
    _refuses(schemas.PAIR_START, {'scopes': ['observe', None]}, 'scopes[1]', 'is required')
    _refuses(schemas.TYPES['Plan'], _with(PLAN, waves=[['t1', 2]]), 'waves[0][1]',
             'must be a string')
    _refuses(schemas.CREATE_PROJECT, {'name': 'p', 'root_paths': ['a', 1],
                                      'idempotency_key': 'k'}, 'root_paths[1]',
             'must be a string')


def test_a_top_level_refusal_names_no_field_and_calls_it_the_body():
    """shapes.py:34's else-branch — the message a null carries when there is no field to
    name. A route cannot reach it with a body of `[]` or `"x"`, because server.py:377-378
    refuses a non-object body first; what does reach it is Core's own use of the same
    validator on a model's structured answer, and every `Invalid` text on a 400."""
    bad = _refuses(schemas.CREATE_MISSION, None, why='a JSON object is required')
    assert bad.field is None and str(bad) == 'body: a JSON object is required', str(bad)
    assert str(schemas.Invalid('title', 'is required')) == 'title: is required'


def test_a_missing_required_field_at_the_top_level_is_named_bare():
    """shapes.py:58 `name if field is None`: at the top the field is the name alone, so
    the detail says 'title', not '.title' and not 'body.title'."""
    _refuses(schemas.CREATE_MISSION, _without(_sample(schemas.CREATE_MISSION), 'title'), 'title',
             'is required')


@pytest.mark.parametrize('which,field,is_nullable', [
    ('MissionPlan', 'plan', True), ('LiveItem', 'handoff', True), ('LiveItem', 'context', True),
    ('Mission', 'project_id', True), ('FeedbackRecorded', 'promoted', True),
    ('KnowledgeChanged', 'knowledge_item', False), ('Execution', 'context', False),
    ('ConstraintDeclared', 'knowledge_item', False), ('ProjectCreated', 'project', False),
], ids=['plan', 'handoff', 'context-state', 'mission-project', 'promoted', 'item-null',
        'exec-context', 'constraint-item', 'project'])
def test_a_named_type_takes_null_only_when_the_field_says_it_may(which, field, is_nullable):
    """shapes.py:27-28 (a nullable `ref` returns before the ref is resolved — drop that
    line and every null named type is refused) and 29-34 (a required one falls through
    the ref and refuses null as `is required`)."""
    schema = schemas.TYPES[which]
    assert bool(schema['properties'][field].get('nullable')) is is_nullable, which
    base = _sample(schema)
    if is_nullable:
        schemas.validate(_with(base, **{field: None}), schema)
    else:
        _refuses(schema, _with(base, **{field: None}), field, 'is required')


def test_a_named_type_that_is_not_in_types_is_a_programmer_error_not_a_refusal():
    """shapes.py:30 indexes TYPES with no default, so a typo'd `ref` raises KeyError —
    which `server.translate` has no row for: a 500, not a 400. That is why the whole
    table is walked below instead of being trusted."""
    with pytest.raises(KeyError):
        schemas.validate({'kind': 'mission', 'id': 'm'}, {'ref': 'NoSuchType'})


def test_the_whole_declared_table_is_something_the_validator_can_check():
    """Every way `validate` can raise anything other than Invalid on a real payload: an
    unknown `type` (shapes.py:35), a missing `items` (52-53), an unresolvable `ref` (30),
    an unsatisfiable `required` (56-58), an empty enum or one whose members are not of
    its own declared type (40), and a key the validator reads as something else (54)."""
    allowed = {'type', 'enum', 'nullable', 'items', 'properties', 'required', 'open',
               'maxLength', 'maxItems', 'ref', 'description'}
    py = {'string': str, 'integer': int, 'number': (int, float), 'boolean': bool,
          'array': list, 'object': dict}
    walked = []

    def walk(node, where):
        assert isinstance(node, dict), where
        assert not set(node) - allowed, (where, sorted(set(node) - allowed))
        if 'ref' in node:
            assert node['ref'] in schemas.TYPES, (where, node['ref'])
            assert set(node) <= {'ref', 'nullable'}, (where, sorted(node))
            walked.append(where)
            return
        assert 'type' in node, where
        t = node['type']
        assert t in py, (where, t)
        if t == 'array':
            assert 'items' in node, where                       # shapes.py:53 KeyError
            walk(node['items'], '%s[]' % where)
        if 'properties' in node:
            assert t == 'object', where
            assert set(node.get('required', ())) <= set(node['properties']), where
            for k, sub in node['properties'].items():
                walk(sub, '%s.%s' % (where, k))
        if 'enum' in node:
            assert node['enum'], where
            for m in node['enum']:
                assert isinstance(m, py[t]) and not (t in ('integer', 'number')
                                                     and isinstance(m, bool)), (where, m)
            assert None not in node['enum'] or node.get('nullable'), where
            assert len({repr(m) for m in node['enum']}) == len(node['enum']), where
        walked.append(where)

    for name, declared in schemas.TYPES.items():
        walk(declared, 'TYPES.' + name)
    for name, body in BODIES.items():
        walk(body, name)
    assert len(walked) > 700, len(walked)          # the walk really covered the table


def test_a_declared_bound_is_enforced_where_a_schema_declares_one():
    """shapes.py:47-48 and 50-51. Only the idempotency `KEY` declares `maxLength` and
    nothing declares `maxItems` today — they are the only size bound a shape can carry, and the model-output schemas
    that share this validator (archeus/core/planning/planner.py) depend on both branches,
    so they are pinned through this module's own entry point."""
    bounded = {'type': 'object', 'properties': {
        'title': {'type': 'string', 'maxLength': 20},
        'tags': {'type': 'array', 'maxItems': 3, 'items': {'type': 'string'}}},
        'required': ['title', 'tags']}
    schemas.validate({'title': 'x' * 20, 'tags': ['a', 'b', 'c']}, bounded)
    _refuses(bounded, _with({'title': 'x' * 20, 'tags': []}, title='x' * 21), 'title',
             'is longer than 20 characters')
    _refuses(bounded, {'title': 'ok', 'tags': ['a'] * 4}, 'tags', 'has more than 3 items')
    # the index still leads the client to the bad element of a bounded list
    _refuses(bounded, {'title': 'ok', 'tags': ['a', 'b', 3]}, 'tags[2]', 'must be a string')


def test_a_string_that_is_not_utf8_text_is_refused_wherever_the_validator_runs():
    """A lone surrogate survives JSON decoding, then breaks every later file write."""
    shape = {'type': 'object', 'properties': {'t': {'type': 'string'}}, 'required': ['t']}
    schemas.validate({'t': 'caf\u00e9 \U0001f600'}, shape)               # a real pair is text
    _refuses(shape, {'t': '\ud83dbroken'}, 't', 'is not valid text')


# ══ the enums are still the domain's own ══════════════════════════════════════════════════════

STATE_ENUMS = [
    ('Mission', 'state', 'mission'), ('Task', 'state', 'task'),
    ('Task', 'integration_state', 'integration'), ('Plan', 'state', 'plan'),
    ('Execution', 'state', 'execution'), ('Session', 'state', 'session'),
    ('Approval', 'state', 'approval'), ('Verification', 'state', 'verification'),
    ('Review', 'state', 'review'), ('Automation', 'state', 'automation'),
    ('AutomationRun', 'state', 'automation_run'), ('Account', 'health', 'account_health'),
    ('Inspection', 'state', 'repository_inspection'),
    ('Repository', 'architecture_state', 'architecture'),
    ('KnowledgeItem', 'state', 'knowledge_item'), ('Idea', 'state', 'idea'),
]


@pytest.mark.parametrize('type_name,field,machine', STATE_ENUMS,
                         ids=['%s-%s' % (t, f) for t, f, _m in STATE_ENUMS])
def test_a_state_enum_is_the_machines_own_states_verbatim(type_name, field, machine):
    """Half these enums are `sorted(states.states('<machine>'))`: rename a machine in
    states.TABLE and the import breaks loudly, but hand-edit one of these lists — or
    drop a state — and the API starts refusing a state Core legitimately holds, which is
    a hard failure on every read of that type."""
    enum = schemas.TYPES[type_name]['properties'][field]['enum']
    assert set(enum) == set(states.states(machine)), (type_name, field)
    assert enum and all(isinstance(s, str) and s == s.strip() for s in enum)


VOCAB_ENUMS = [
    ('Criterion', 'check', entities.CRITERION_CHECKS),
    ('Criterion', 'origin', ORIGINS),
    ('ContextItem', 'level', LEVELS), ('ContextItem', 'store', STORES),
    ('ContextPreview', 'levels[]', LEVELS),
    ('ContextExcluded', 'freshness', ('current', 'stale', 'superseded')),
    ('Task', 'kind', entities.TASK_KINDS),
    ('PlanTaskSpec', 'kind', entities.TASK_KINDS),
    ('PlanTaskSpec', 'action_classes[]', entities.ACTION_CLASSES),
    ('PlanTaskSpec', 'capabilities_required[]', entities.CAPABILITIES),
    ('PlanTaskSpec', 'min_model_tier', entities.MODEL_TIERS),
    ('PlanTaskSpec', 'workspace_mode', entities.WORKSPACE_MODES),
    ('OptIn', 'kind', entities.OPT_IN_KINDS),
    ('Account', 'auth_kind', entities.AUTH_KINDS),
    ('ResourcePolicy', 'consumption', entities.CONSUMPTION),
    ('ProviderTerms', 'headless', entities.TERMS),
    ('ProviderTerms', 'rotation', entities.TERMS),
    ('Message', 'author', ('user', 'archeus', 'system')),
    ('Client', 'origin', ('local', 'paired')),
    ('Client', 'client_type', ('cli', 'spa')),
    ('Card', 'type', entities.CARD_TYPES),
    ('Intent', 'kind', entities.INTENT_KINDS),
    ('Intent', 'resolution', entities.RESOLUTIONS),
    ('Session', 'mode', entities.SESSION_MODES),
    ('Checkpoint', 'trigger', entities.CHECKPOINT_TRIGGERS),
    ('Check', 'kind', entities.CHECK_KINDS),
    ('Check', 'result', entities.CHECK_RESULTS),
    ('Policies', 'user_profile', entities.AUTONOMY_PROFILES),
    ('Execution', 'served_level', entities.PROVENANCE_LEVELS),
    ('Finding', 'kind', entities.CONSTRAINT_SPECS),
    ('Finding', 'status', ('violated', 'satisfied', 'unchecked')),
    ('ReplayBinding', 'answer', ('RECORDED', 'UNKNOWN')),
    ('ReplayCheckpoint', 'files_are', ('summary', 'paths', 'unknown')),
    ('HarnessBreaker', 'state', ('open', 'half_open')),
    ('LiveItem', 'kind', ('execution', 'own_call')),
    ('TraceStep', 'type', ('assistant', 'tool', 'tool_result')),
    ('DigestGroup', 'headline', ('needs_you', 'drift_found', 'failed', 'completed',
                                 'drift_cleared', 'progressed', 'new_messages')),
    ('Status', 'source', ('deterministic',)),
    ('Forgotten', 'mode', ('retract', 'purge')),
    ('CurrentAction', 'decision', ('allow', 'deny', 'halt')),
    ('ResourcePolicy', 'fallback', ('allow', 'ask', 'deny')),
]


def _enum_of(type_name, field):
    node = schemas.TYPES[type_name]['properties']
    node = node[field[:-2]]['items'] if field.endswith('[]') else node[field]
    return node['enum']


@pytest.mark.parametrize('type_name,field,vocab', VOCAB_ENUMS,
                         ids=['%s-%s' % (t, f.rstrip('[]')) for t, f, _v in VOCAB_ENUMS])
def test_a_vocabulary_enum_is_the_domains_whole_vocabulary(type_name, field, vocab):
    """The same risk on the `list(entities.X)` and literal enums: when the domain gains a
    value and the shape is not regenerated, the boundary refuses what Core legitimately
    produces — a refusal nobody asked for, on a read path."""
    assert set(_enum_of(type_name, field)) == set(vocab), (type_name, field)


def test_the_request_bodies_that_take_an_enum_use_the_same_words_as_their_types():
    """A body and a type naming the same thing must not drift: CREATE_RULE's action
    classes are CurrentAction's and the domain's, SET_OPT_IN's kinds are OptIn's, the two
    grant bodies share their scope words, and the platform enums differ on purpose (a
    launch code redeems from a browser or the desktop shell only, a pairing code from a
    phone too)."""
    assert (set(schemas.CREATE_RULE['properties']['action_class']['enum'])
            == set(schemas.TYPES['CurrentAction']['properties']['action_class']['enum'])
            == set(entities.RULE_CLASSES))
    assert (set(schemas.CREATE_RULE['properties']['decision']['enum'])
            == set(entities.DECISIONS))
    assert (set(schemas.SET_OPT_IN['properties']['kind']['enum'])
            == set(schemas.TYPES['OptIn']['properties']['kind']['enum'])
            == set(entities.OPT_IN_KINDS))
    assert (set(schemas.PAIR_START['properties']['scopes']['items']['enum'])
            == set(schemas.LAUNCH_CODE['properties']['scopes']['items']['enum']))
    assert set(schemas.REDEEM['properties']['platform']['enum']) == {'web', 'desktop'}
    assert set(schemas.PAIR_REDEEM['properties']['platform']['enum']) == {
        'web', 'desktop', 'ios', 'android'}
    for owner, field in (('DECIDE', 'decision'), ('SET_PROFILE', 'scope'),
                         ('USER_REVIEW', 'verdict'), ('CLARIFY', 'choice'),
                         ('AUTOMATION_STATE', 'action'), ('DECIDE_VERIFICATION', 'decision'),
                         ('RESOURCE_POLICY', 'fallback'), ('SIMULATE', 'stage')):
        enum = _body_of(owner)['properties'][field]['enum']
        assert enum and all(isinstance(e, str) and e == e.strip().lower() for e in enum), \
            '%s.%s' % (owner, field)


def test_an_open_object_with_no_properties_takes_any_dict():
    """The documented leniency the module docstring names (`{'type': 'object'}` with no
    properties: any JSON object) — shapes.py:54 never enters the object branch. Pinned on
    the two that guard a write: FORGET's selector and SIMULATE's action."""
    schemas.validate({'selector': {'anything': [1, {'x': None}]}, 'idempotency_key': 'k'},
                     schemas.FORGET)
    schemas.validate({'action': {'action_class': 'whatever', 'unheard_of': True}},
                     schemas.SIMULATE)
    _refuses(schemas.FORGET, _with(_sample(schemas.FORGET), selector=[]), 'selector',
             'must be an object')
    _refuses(schemas.SIMULATE, _with(_sample(schemas.SIMULATE), action='x'), 'action',
             'must be an object')


def test_the_e_stop_read_and_the_command_agree_on_what_armed_means():
    """Health.armed (schemas.py:109), Estopped.armed (739) and Rearmed.armed (740) are
    read and written by the same pair of routes; if one of the three becomes nullable or
    a string the console shows an e-stop state that is not the one Core holds."""
    armed = [schemas.TYPES[w]['properties']['armed'] for w in ('Health', 'Estopped', 'Rearmed')]
    assert all(a == {'type': 'boolean'} for a in armed), armed
    assert all('armed' in schemas.TYPES[w]['required'] for w in ('Health', 'Estopped',
                                                                 'Rearmed'))
