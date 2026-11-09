"""T-765: the highest-risk uncovered branches of archeus/core/application/public.py.

Fail-closed and denial first: an unregistered or near-miss event type never gets an
authored exemption (public.py:46 `EVENT_AUTHORED.get(..., ())`); a partial envelope
or a partial output read raises instead of returning an unprojected copy
(public.py:45-46, public.py:52); every PATH_KEYS value that *is* a registered home
becomes None (public.py:16-17 via public_value), a default account key becomes its
handle at any depth, and every other string gets the fallback scrub (public.py:18).
Then the boundary values: the `_key=_path[-1] if _path else None` ternary (a
top-level scalar is scrubbed, never denied), list items inheriting the parent key's
path while nested dicts extend it, tuples projecting to scrubbed lists unless they
sit under an authored path (deepcopy), non-string keys, scalars and empties. Then
idempotency and replay: public(public(x)) == public(x) for all three entry points,
two reads of the same request identical across freshly built Homes, the envelope
carried untouched, and deep copies so no projected output can reach the stored one.

Style and fixtures copied from tests/v1/unit/test_t144_event_surfaces.py (the
closest existing tests of this module): the same injected-`shorts` Homes seam, no
OS probing, no process, no network. Platform-neutral: homes are spelled in one
fixed flavour with `path_flavour='windows'`, all assertions are on in-memory
dicts/strings, nothing depends on the host OS or the environment.
"""

import copy

import pytest

from archeus.core.application import public
from archeus.core.homes import Homes, public_account_id

HOME = 'C:/Gaps/Public-Homes'
KEY = 'h:' + HOME.lower()
OTHER = 'C:/Gaps/Other-Claude'
OTHER_KEY = 'h:' + OTHER.lower()


def _homes():
    return Homes([HOME, OTHER], [('h', KEY, HOME), ('h', OTHER_KEY, OTHER)],
                 shorts=lambda _: None, path_flavour='windows')


@pytest.fixture
def homes():
    return _homes()


def envelope(type_, payload, kind='user_device'):
    return {'seq': 7, 'id': 'ev', 'type': type_, 'at': 'then',
            'actor': {'kind': kind, 'id': 'prn_x'}, 'cause_chain': [],
            'subject': {'kind': 'mission', 'id': 'mis_x'},
            'scope': {'workspace': 'w', 'project': None}, 'visibility': 'user',
            'payload': payload}


# --- fail-closed and denial paths -------------------------------------------------

NEAR_MISS = [('case', 'Mission.Created'), ('trail-space', 'mission.created '),
             ('dot', 'mission.created.'), ('short', 'mission.create'),
             ('lead-space', ' mission.created'), ('empty', ''), ('none', None)]


@pytest.mark.parametrize('type_', [t for _, t in NEAR_MISS], ids=[i for i, _ in NEAR_MISS])
def test_near_miss_event_type_never_gets_the_authored_exemption(homes, type_):
    # public.py:46 `EVENT_AUTHORED.get(envelope['type'], ())` taking the default:
    # a type that only *looks* registered falls back to the full scrub, so the
    # authored exemption can never be bought with a near-miss type name.
    env = envelope('mission.created', {'title': HOME, 'body': 'at ' + HOME})
    env['type'] = type_
    got = public.public_event(env, homes)['payload']
    assert got == {'title': 'its home', 'body': 'at its home'}
    # the registered type itself is the control: byte-for-byte under the exemption
    control = public.public_event(envelope('mission.created', {'title': HOME}), homes)
    assert control['payload'] == {'title': HOME}


def test_partial_envelope_raises_and_returns_nothing(homes):
    # public.py:45 `envelope['payload']` and public.py:46 `envelope['type']`:
    # a partial envelope fails closed with KeyError; it never yields a half-
    # projected copy that could carry a raw home or key out.
    with pytest.raises(KeyError):
        public.public_event({'type': 'mission.created', 'seq': 1}, homes)
    with pytest.raises(KeyError):
        public.public_event({'payload': {'title': HOME}, 'seq': 1}, homes)
    leaked = {'type': None, 'payload': {'title': HOME}}
    got = public.public_event(leaked, homes)  # type=None hits the get() default, not a crash
    assert got['payload'] == {'title': 'its home'}


def test_partial_output_read_raises_instead_of_returning_raw(homes):
    # public.py:52 `out['events']`: a read without its events list fails closed;
    # the caller never sees a dict that skipped projection.
    with pytest.raises(KeyError):
        public.public_output({'execution_id': 'e', 'offset': 0}, homes)
    with pytest.raises(KeyError):
        public.public_output({}, homes)


@pytest.mark.parametrize('key', ['account_ref', 'ref', 'home_ref', 'home_key'])
def test_every_path_key_denies_an_exact_registered_home(homes, key):
    # public.py:39 PATH_KEYS x public.py:16-17: dropping any one entry from the
    # tuple (or the `_key in path_keys` gate) leaks that key's home verbatim.
    # The key list is written out literally, not read from PATH_KEYS, so dropping
    # an entry fails here instead of silently shrinking the parametrization.
    got = public.public_event(envelope('x.unknown', {key: HOME, 'plain': HOME}), homes)['payload']
    assert got[key] is None
    assert got['plain'] == 'its home'


def test_path_keys_table_is_exactly_the_owner_list():
    # public.py:39: the denial table itself, pinned as data (see the note on the
    # parametrized test above about reading it from the module instead).
    assert set(public.PATH_KEYS) == {'account_ref', 'ref', 'home_ref', 'home_key'}


def test_path_key_denial_is_exact_membership_not_a_prefix(homes):
    # the None substitution fires only when the whole value canonicalises to a
    # registered home; a contained spelling is scrubbed like any system text and
    # a non-home under a path key stays exactly as stored.
    got = public.public_event(envelope('x.unknown', {
        'ref': HOME + '/sub', 'home_ref': 'C:/Gaps/Not-A-Home',
        'account_ref': 'c:\\Gaps\\PUBLIC-homes', 'home_key': OTHER}), homes)['payload']
    assert got['ref'] == 'its home/sub'
    assert got['home_ref'] == 'C:/Gaps/Not-A-Home'
    assert got['account_ref'] is None          # another spelling of the same home
    assert got['home_key'] is None


def test_default_account_key_is_denied_at_every_position(homes):
    # public.py:16-18 on every non-authored scalar: exact keys become handles via
    # public_value, contained keys via scrub_text's key regex; an unlisted nested
    # position can never keep a raw key (the fallback scrub always runs).
    got = public.public_event(envelope('x.unknown', {
        'a': KEY, 'b': [OTHER_KEY, ['x ' + KEY]],
        'c': {'d': 'running as ' + OTHER_KEY}, 'e': ' %s ' % KEY}), homes)['payload']
    assert got['a'] == public_account_id(KEY)
    assert got['b'] == [public_account_id(OTHER_KEY), ['x ' + public_account_id(KEY)]]
    assert got['c'] == {'d': 'running as ' + public_account_id(OTHER_KEY)}
    assert got['e'] == public_account_id(KEY)  # padded but still the whole value


# --- boundary values --------------------------------------------------------------

def test_top_level_scalar_is_scrubbed_never_denied(homes):
    # public.py:17 `_key=_path[-1] if _path else None` taking the None arm: a
    # bare string has no key, so path_keys must not deny it to None, but the
    # scrub (public.py:18) must still fire.
    assert public.system_value(HOME, homes, path_keys=public.PATH_KEYS) == 'its home'
    assert public.public_context(HOME, homes) == 'its home'
    assert public.public_context('', homes) == ''


def test_path_key_reaches_list_items_but_not_nested_dicts(homes):
    # public.py:14-15 keeps `_path` for list items (the path-key denial reaches
    # them) while public.py:11-12 extends `_path` with the dict key (a home two
    # dicts down under a path key is under some other key and gets the scrub).
    got = public.public_event(envelope('x.unknown', {
        'home_key': [HOME, [HOME, HOME + '/x']], 'home_ref': {'deep': HOME}}), homes)['payload']
    assert got['home_key'] == [None, [None, 'its home/x']]
    assert got['home_ref'] == {'deep': 'its home'}


def test_unauthored_tuple_is_projected_to_a_scrubbed_list(homes):
    # public.py:13 `(list, tuple)`: drop tuples from that isinstance and their
    # strings fall to the scalar arm, where public_value recurses WITHOUT the
    # public.py:18 scrub_text and a raw home survives.
    got = public.public_event(envelope('x.unknown', {'note': (HOME, (KEY,))}), homes)['payload']
    assert got['note'] == ['its home', [public_account_id(KEY)]]
    assert type(got['note']) is list and type(got['note'][1]) is list


def test_authored_tuple_is_deepcopied_byte_for_byte(homes):
    # public.py:8-9: the authored arm wins before the container arms, so a tuple
    # under an authored path keeps its exact type and bytes.
    env = envelope('mission.created', {'title': ('keep ' + HOME, (KEY,))})
    got = public.public_event(env, homes)['payload']
    assert got == {'title': ('keep ' + HOME, (KEY,))}
    assert type(got['title']) is tuple and type(got['title'][1]) is tuple


@pytest.mark.parametrize('value', [None, 0, False, True, 1.5, ''],
                         ids=['none', 'zero', 'false', 'true', 'float', 'empty'])
def test_scalars_and_empties_pass_through_every_entry_point(homes, value):
    # public.py:16-18 with a non-container, non-string value, and the empty
    # input of every command/query: nothing is invented, nothing crashes, and
    # public_output carries the other read keys through untouched (public.py:52).
    assert public.system_value(value, homes, authored=(('q',),),
                               path_keys=public.PATH_KEYS) == value
    got = public.public_context(value, homes)
    assert got == value and type(got) is type(value)
    assert public.public_event(envelope('x.unknown', {'v': value}), homes)['payload'] == {'v': value}
    out = {'events': [], 'execution_id': value}
    assert public.public_output(out, homes) == {'events': [], 'execution_id': value}
    assert out == {'events': [], 'execution_id': value}


def test_deeply_nested_system_string_is_still_scrubbed(homes):
    # the recursion of public.py:10-15 must not stop early: at depth 30 the
    # scalar arm (public.py:16-18) still runs.
    node = HOME
    for _ in range(30):
        node = {'a': [node]}
    got = public.public_event(envelope('x.unknown', {'p': node}), homes)['payload']['p']
    for _ in range(30):
        got = got['a'][0]
    assert got == 'its home'


def test_non_string_payload_keys_survive_and_values_are_projected(homes):
    # public.py:10-12 keys are carried, not stringified: turning the key into a
    # str would either break the round-trip or (worse) match path_keys by name.
    got = public.public_event(envelope('x.unknown', {
        7: 'x ' + HOME, None: KEY, ('a', 'b'): HOME}), homes)['payload']
    assert got == {7: 'x its home', None: public_account_id(KEY), ('a', 'b'): 'its home'}


# --- idempotency and replay -------------------------------------------------------

def test_public_output_projects_only_events_never_the_rest_of_the_read(homes):
    # public.py:52 `dict(out, events=...)`: events are projected (path denial and
    # scrub included), every other read key is carried as the reader made it, and
    # mutating the projection cannot reach the stored read (fresh containers from
    # public.py:10-15, deepcopy only for authored).
    out = {'execution_id': 'e', 'offset': 2, 'available': True, 'error': HOME, 'events': [
        {'type': 'assistant', 'text': 'cd ' + HOME},
        {'type': 'tool', 'input': {'ref': HOME, 'note': KEY}}]}
    before = copy.deepcopy(out)
    got = public.public_output(out, homes)
    assert got['events'][0]['text'] == 'cd its home'
    assert got['events'][1]['input'] == {'ref': None, 'note': public_account_id(KEY)}
    assert got['error'] == HOME and got['offset'] == 2 and got['available'] is True
    assert public.public_output(out, homes) == got          # replay: identical again
    got['events'].append('x')
    got['events'][1]['input']['note'] = 'mutated'
    assert out == before                                      # the read was not touched


REPLAY_SHAPES = [
    ('authored', envelope('mission.created', {'title': HOME, 'note': 'at ' + HOME})),
    ('denials', envelope('x.unknown', {'ref': HOME, 'k': KEY, 'note': HOME + '/x'})),
    ('nested', envelope('mission.updated', {
        'added': {'requirements': [HOME + '/r', KEY]}, 'notes': 'seen at ' + OTHER})),
]


@pytest.mark.parametrize('name,env', REPLAY_SHAPES, ids=[n for n, _ in REPLAY_SHAPES])
def test_event_projection_is_idempotent_and_deterministic(homes, name, env):
    # public.py:42-46 read twice: 'its home' and handles are fixed points of the
    # projection and authored raw text stays raw through a replay; two reads of
    # the same request are identical.
    once = public.public_event(copy.deepcopy(env), homes)
    assert public.public_event(copy.deepcopy(once), homes) == once
    assert once == public.public_event(copy.deepcopy(env), homes)


def test_all_entry_points_replay_identically_across_freshly_built_homes():
    # handles come from the run-dir secret: two Homes built from the same inputs
    # must project identically, or a replay after a rebuild would drift.
    a, b = _homes(), _homes()
    env = envelope('mission.created', {'title': HOME + ' ' + KEY, 'note': 'at ' + OTHER})
    assert public.public_event(env, a) == public.public_event(env, b)
    body = {'query': HOME, 'items': [{'text': 'on ' + KEY}]}
    assert public.public_context(body, a) == public.public_context(body, b)
    out = {'events': [{'text': 'cd ' + HOME}]}
    assert public.public_output(out, a) == public.public_output(out, b)


def test_context_query_exemption_is_the_exact_path_only(homes):
    # public.py:8 `_path in authored` with public.py:56 authored=(('query',),):
    # exact tuple membership, not a last-key match — a nested or case-mismatched
    # 'query' is system-owned text and must be scrubbed.
    got = public.public_context({
        'query': HOME, 'items': [{'query': HOME}, {'text': 'at ' + KEY}],
        'Query': HOME, 'query2': HOME}, homes)
    assert got['query'] == HOME
    assert got['items'][0]['query'] == 'its home'
    assert got['items'][1]['text'] == 'at ' + public_account_id(KEY)
    assert got['Query'] == 'its home'
    assert got['query2'] == 'its home'
    assert public.public_context(public.public_context({'query': HOME}, homes), homes) \
        == {'query': HOME}                                # replay keeps authored bytes


def test_authored_leaves_are_deep_copies_that_cannot_reach_the_envelope(homes):
    # public.py:9 `deepcopy(value)`: returning the live object (or a shallow
    # copy) lets a mutation of the projected payload corrupt the stored event.
    env = envelope('mission.created', {'title': {'deep': [HOME, KEY]}, 'note': HOME})
    before = copy.deepcopy(env)
    got = public.public_event(env, homes)
    assert got['payload']['title'] == {'deep': [HOME, KEY]}   # byte for byte, nested too
    assert got['payload']['note'] == 'its home'
    got['payload']['title']['deep'].append('injected')
    got['payload']['title']['deep'][0] = 'REPLACED'
    assert env == before


def test_envelope_is_carried_untouched_and_only_the_payload_is_replaced(homes):
    # public.py:44 `dict(envelope, payload=...)`: dropping a key from the merge
    # (or projecting the envelope itself, which is the caller's/DB's shape) is
    # caught here; the projected payload is a fresh structure, never the input's.
    env = envelope('x.unknown', {'title': HOME})
    env['origin'] = {'kind': 'mxc', 'ref': OTHER_KEY}
    got = public.public_event(env, homes)
    assert {k: v for k, v in got.items() if k != 'payload'} == \
        {k: v for k, v in env.items() if k != 'payload'}
    assert got['origin'] == env['origin']                  # the envelope is not touched
    assert got['payload'] is not env['payload']
    assert env['payload'] == {'title': HOME}


# --- empty everything -------------------------------------------------------------

def test_nothing_registered_projects_without_crash_or_invented_denial():
    # public.py:16-18 with the empty Homes seam (no patterns, no keys, no norms):
    # projection is the identity — no invented 'its home', no None denial — and
    # none of the entry points crashes on the empty input of a command or query.
    h = Homes()
    env = envelope('mission.updated', {'added': {'requirements': [HOME]}, 'note': 'x ' + KEY})
    assert public.public_event(env, h)['payload'] == {
        'added': {'requirements': [HOME]}, 'note': 'x ' + KEY}
    assert public.public_context({'query': HOME, 'i': [{'t': 'x ' + HOME}]}, h) == \
        {'query': HOME, 'i': [{'t': 'x ' + HOME}]}
    assert public.public_event(envelope('mission.created', {}), h)['payload'] == {}
    assert public.public_event(envelope('mission.updated', []), h)['payload'] == []
    assert public.public_output({'events': []}, h) == {'events': []}
