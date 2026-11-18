"""T-333: the highest-risk uncovered branches of archeus/cli/tui/sync.py —
fail-closed and denial paths first, then boundary values, then error paths.
The shared parity cases (clients/app/test/fixtures/parity.json, run by
tests/v1/tui/test_parity.py) hold the happy table; the branches closed here
are the ones whose silent breakage is worst: a revoked client that looks
live, stale data that reads as current, commands sent on a dead connection,
retries and key reuses the caller never earned, and an invalidation match
that misses the path it was written for. Pure functions over dicts: no OS,
no clock, no network, no threads, nothing platform-specific."""

import uuid

import pytest

from archeus.cli.tui import sync as S


def st(conn, gen=0, since=0):
    return {'conn': conn, 'gen': gen, 'since': since}


def read(gen, has=True, **kw):
    return dict({'gen': gen, 'hasData': has}, **kw)


def frame(kind, sid=None):
    subject = {'kind': kind} if sid is None else {'kind': kind, 'id': sid}
    return {'event': 'x.y', 'data': {'subject': subject}}


# ── the connection: fail-closed and denial paths ─────────────────────────────

ALL_SIGNALS = ['online', 'offline', 'frame', 'stream_open', 'stream_lost', 'resync',
               'settled', 'unauthorized', 'self_revoked']


@pytest.mark.parametrize('conn', ['unauthenticated', 'revoked'])
@pytest.mark.parametrize('sig', ALL_SIGNALS)
def test_a_signed_out_client_freezes_under_every_signal(conn, sig):
    """sync.py:24-25: the freeze runs before every signal handler. Without it
    `stream_open` would take a revoked client to resynced/live and the screen
    would invite action from a client that can no longer act."""
    s = st(conn, 4, 1)
    assert S.next_state(s, sig, 9) is s


@pytest.mark.parametrize('sig', ['stream_opened', 'ONLINE', 'resync ', 'frame ', '', None, 0])
def test_an_unknown_signal_raises_instead_of_changing_nothing(sig):
    """sync.py:54: an unrecognised signal is a caller bug, refused loudly. If
    the raise were dropped the state machine would swallow typos and sit
    'live' through a condition nobody handled."""
    s = st('live', 2, 1)
    with pytest.raises(ValueError, match='unknown signal'):
        S.next_state(s, sig, 9)
    assert s == st('live', 2, 1)                       # the raise wrote nothing


@pytest.mark.parametrize('from_', ['connecting', 'live', 'reconnecting', 'resynced', 'offline'])
def test_the_offline_signal_silences_every_connected_state(from_):
    """sync.py:36-37: the operator marking the machine offline must be heard
    from any state; without the branch the connection stays live and commands
    keep flowing to a machine said to be unreachable."""
    s = st(from_, 3, 1)
    out = S.next_state(s, 'offline', 9)
    if from_ == 'offline':                              # already there: same state
        assert out is s
    else:
        assert out == {'conn': 'offline', 'gen': 3, 'since': 9}   # gen untouched
    assert S.can_command(out['conn']) is False


def test_the_way_back_from_offline_is_a_resync_not_a_live():
    """sync.py:45-48: the stream reopening after a drop (offline included) is
    a resync with a generation bump. If it went straight to 'live' without the
    bump, reads taken before the drop would still compare equal to c['gen']
    and freshness() would call them current while the machine was away."""
    back = S.next_state(st('offline', 3, 1), 'stream_open', 9)
    assert back == {'conn': 'resynced', 'gen': 4, 'since': 9}
    assert S.freshness(back, read(3)) == 'stale'       # what was read before is old
    assert S.next_state(st('reconnecting', 3, 1), 'stream_open', 9) == \
        {'conn': 'resynced', 'gen': 4, 'since': 9}


NO_CHANGE = [('live', 'frame'), ('live', 'stream_open'), ('live', 'online'),
             ('live', 'settled'), ('reconnecting', 'frame'), ('reconnecting', 'online'),
             ('connecting', 'online'), ('resynced', 'frame'), ('offline', 'stream_lost')]


@pytest.mark.parametrize('conn,sig', NO_CHANGE, ids=['%s+%s' % c for c in NO_CHANGE])
def test_a_signal_that_changes_nothing_returns_the_very_same_state(conn, sig):
    """sync.py:29-30 and the `else s` arms of 39, 41, 49, 51, 53: a signal that
    asks for the state already held must not rebuild it — a rebuilt state would
    carry the signal's `now` into `since` and reset the age of the screen."""
    s = st(conn, 5, 1)
    assert S.next_state(s, sig, 9) is s


def test_the_first_state_is_connecting_and_may_not_send():
    """sync.py:18-19: the client starts not-live at generation 0; starting
    'live' would send commands before a frame was ever seen and start the
    generation ladder where a real resync cannot be told from zero."""
    assert S.initial(7) == {'conn': 'connecting', 'gen': 0, 'since': 7}
    assert S.can_command(S.initial(7)['conn']) is False


SENDABLE = [('live', True), ('resynced', True), ('connecting', False),
            ('reconnecting', False), ('offline', False), ('unauthenticated', False),
            ('revoked', False), ('', False), ('live ', False), ('Live', False)]


@pytest.mark.parametrize('conn,allowed', SENDABLE,
                         ids=[c.replace(' ', '-') or 'empty' for c, _ in SENDABLE])
def test_commands_are_allowed_only_on_live_or_resynced(conn, allowed):
    """sync.py:59: the send gate is an allowlist. Widening it to e.g. offline
    or unauthenticated posts commands that cannot land, or that must not."""
    assert S.can_command(conn) is allowed


# ── freshness: what may be shown as current ──────────────────────────────────

@pytest.mark.parametrize('conn', ['offline', 'unauthenticated', 'revoked', 'broken'])
def test_no_connection_means_no_read_is_current(conn):
    """sync.py:69-70: anything that is not live/resynced downgrades data to
    stale and an empty view to unavailable; an unhandled connection value
    falls into this denial too, never past it into 'current'."""
    c = st(conn, 2)
    assert S.freshness(c, read(2)) == 'stale'
    assert S.freshness(c, read(2, has=False)) == 'unavailable'


def test_while_connecting_reads_look_like_a_drop():
    """sync.py:67-68: nothing has been shown yet on a first connection, so a
    view with data says 'reconnecting', not 'current', and an empty one says
    'unavailable'."""
    c = st('connecting', 0)
    assert S.freshness(c, read(0)) == 'reconnecting'
    assert S.freshness(c, read(0, has=False)) == 'unavailable'


def test_freshness_checks_run_in_the_written_order():
    """sync.py:65-73: the four checks are ordered, and the order is behaviour.
    An error with no data is 'unavailable' even on a live connection (an error
    alone must never read as stale-but-shown); an error behind data does not
    preempt the drop reporting 'reconnecting'; and on a live connection data
    with an error or pending flag is 'stale', never 'current'."""
    live = st('live', 2)
    assert S.freshness(live, read(2, has=False, error='boom')) == 'unavailable'
    assert S.freshness(st('reconnecting', 2), read(2, error='boom')) == 'reconnecting'
    assert S.freshness(live, read(2, error='boom')) == 'stale'
    assert S.freshness(live, read(2, pending=True)) == 'stale'
    assert S.freshness(live, read(1, pending=True, error='boom')) == 'stale'
    assert S.freshness(live, read(2)) == 'current'


def test_a_read_only_ages_by_generation():
    """sync.py:71: the comparison is `<`, not `<=` and not `!=` — a read from
    the current generation is current, one from a later generation (already
    re-read) is still current, and only an older one is stale."""
    c = st('live', 5)
    assert S.freshness(c, read(5)) == 'current'
    assert S.freshness(c, read(6)) == 'current'        # a future read is not stale
    assert S.freshness(c, read(4)) == 'stale'
    assert S.freshness(c, read(0)) == 'stale'
    assert S.freshness(st('resynced', 5), read(5)) == 'current'


# ── the command lifecycle: keys and retries after failures ───────────────────

def test_only_a_network_failure_reuses_the_key():
    """sync.py:103-106 and new_key at 93-94: after a network failure nobody
    knows whether Core applied the action, so the retry must carry the same
    key; after any answer the key must be a fresh uuid4. Inverting the test
    either replays a completed action (new key after network) or has Core drop
    the retry as a duplicate (reused key after an answer)."""
    assert S.key_after('k1', 'network') == 'k1'
    assert S.key_after('k1', 'network', fresh=lambda: 'F') == 'k1'
    assert S.key_after('k1', 'ok', fresh=lambda: 'F') == 'F'
    for outcome in ('ok', 'refused', 'version_conflict', '', None, 'Network'):
        key = S.key_after('k1', outcome)
        assert key != 'k1'
        assert uuid.UUID(key).version == 4             # the default fresh=new_key
    assert S.key_after('k1', 'ok') != S.key_after('k1', 'ok')


RETRY_CODES = [('busy', True), ('core_starting', True), ('network', False),
               ('version_conflict', False), ('not_permitted', False),
               ('unauthenticated', False), ('refused', False), ('Busy', False),
               ('busy ', False)]


@pytest.mark.parametrize('code,ok', RETRY_CODES,
                         ids=['busy', 'core-starting', 'network', 'version-conflict',
                              'not-permitted', 'unauthenticated', 'refused', 'Busy',
                              'busy-space'])
def test_only_busy_and_core_starting_ask_for_a_retry(code, ok):
    """sync.py:109-111: retry once, automatically, exactly when Core asked for
    it. Adding 'network' would resend an action of unknown fate; dropping
    'core_starting' would surface a transient as a failure."""
    assert S.retryable({'status': 0, 'code': code, 'detail': {}}) is ok


# ── explain: refusals in words, from untrustworthy responses ─────────────────

NO_DETAIL = [
    ({'status': 403, 'code': 'scope_required'}, 'This client does not hold the “” scope.'),
    ({'status': 403, 'code': 'not_permitted'}, 'Not permitted: '),
    ({'status': 422, 'code': 'guard_failed'}, 'Refused: a guard refused'),
    ({'status': 422, 'code': 'policy_denied'}, 'The policy denies it: '),
    ({'status': 409, 'code': 'approval_not_eligible'}, 'This approval cannot be decided now: '),
    ({'status': 409, 'code': 'invalid_transition'}, 'Not possible from .'),
    ({'status': 400, 'code': 'invalid_request'}, 'Invalid: '),
    ({'status': 409, 'code': 'refused'}, 'Refused: '),
]


@pytest.mark.parametrize('r,wanted', NO_DETAIL, ids=[r['code'] for r, _ in NO_DETAIL])
def test_explain_survives_a_response_with_no_detail(r, wanted):
    """sync.py:120 (`r.get('detail') or {}`) and _s at 114-115: a response with
    no detail at all — key missing, None, or {} — must not crash and must not
    print 'None'; a refusal is still explained."""
    for response in (r, dict(r, detail=None), dict(r, detail={})):
        assert S.explain(response) == wanted


def test_an_unknown_code_shows_only_status_and_code():
    """sync.py:159: the fallback quotes Core's own two safe fields and drops
    the detail, which for an unknown code is unvetted — printing it could put
    a server-side value on screen unexplained."""
    said = S.explain({'status': 418, 'code': 'teapot', 'detail': {'secret': 'sk-1'}})
    assert said == '418 teapot'
    assert 'sk-1' not in said


def test_falsy_detail_values_are_printed_as_they_are():
    """sync.py:114-115 (_s): the distinction is None vs not-None, not falsy vs
    truthy — Core sending reason 0 or why False must print '0'/'False', not an
    empty string."""
    assert S.explain({'status': 403, 'code': 'policy_denied',
                      'detail': {'reason': 0}}) == 'The policy denies it: 0'
    assert S.explain({'status': 403, 'code': 'not_permitted',
                      'detail': {'why': False}}) == 'Not permitted: False'
    assert S.explain({'status': 409, 'code': 'invalid_transition',
                      'detail': {'from': 0, 'trigger': 'go'}}) == 'Not possible from 0 (go).'


@pytest.mark.parametrize('detail,wanted', [
    ({'reason': '', 'guard': 'g'}, 'Refused: '),
    ({'reason': None, 'guard': 'g'}, 'Refused: g'),
    ({'guard': 'g'}, 'Refused: g'),
    ({'reason': 'r', 'guard': 'g'}, 'Refused: r'),
    ({'reason': 0, 'guard': 'g'}, 'Refused: 0'),
], ids=['empty-reason', 'none-reason', 'guard-only', 'both', 'zero-reason'])
def test_guard_failure_reads_reason_then_guard_then_the_fallback(detail, wanted):
    """sync.py:128-131: the pick is over `is not None`, not truthiness — an
    empty-string reason is Core's answer and outranks the guard name; only an
    absent reason falls through, and only two absences reach the fallback."""
    assert S.explain({'status': 422, 'code': 'guard_failed', 'detail': detail}) == wanted


def test_a_falsy_trigger_is_left_out_of_an_invalid_transition():
    """sync.py:132-134: the parenthetical is gated on the trigger being
    present-and-truthy; inverting it would index d['trigger'] on a response
    that has none (KeyError) or print '(0)'."""
    assert S.explain({'status': 409, 'code': 'invalid_transition',
                      'detail': {'from': 'LIVE', 'trigger': 0}}) == 'Not possible from LIVE.'
    assert S.explain({'status': 409, 'code': 'invalid_transition',
                      'detail': {'from': 'LIVE', 'trigger': 'go'}}) == \
        'Not possible from LIVE (go).'


def test_a_falsy_field_is_left_out_of_an_invalid_request():
    """sync.py:151-152: the 'field ' prefix is gated on the field being
    present-and-truthy, the reason is _s'd; field 0 prints as no field, and a
    missing why still prints 'Invalid: <field> ' rather than crash."""
    assert S.explain({'status': 400, 'code': 'invalid_request',
                      'detail': {'field': 0, 'why': 'bad'}}) == 'Invalid: bad'
    assert S.explain({'status': 400, 'code': 'invalid_request',
                      'detail': {'field': 'model', 'why': 'x'}}) == 'Invalid: model x'


# ── invalidation: which reads a frame makes stale ────────────────────────────

def test_a_star_never_crosses_a_segment_or_a_query():
    """sync.py:168 ('[^/?]+'): one '*' is exactly one non-empty path segment,
    and a query is the tail's only job. Loosening the class to allow '/' lets
    a '*' match across segments; allowing '?' lets a segment swallow the
    boundary the tail is anchored to. 'checkpoint' is used because none of its
    rules carry a '**' prefix that would mask a miss by over-matching."""
    stale = S.stale_by(frame('checkpoint', 'ck_1'))
    assert stale('/v1/executions/e1/checkpoints') is True
    assert stale('/v1/executions/e1/x/checkpoints') is False
    assert stale('/v1/executions//checkpoints') is False          # '*' needs one char
    assert stale('/v1/executions/?x/checkpoints') is False        # segment can't start '?'
    assert stale('/v1/executions/e1/checkpoints?x=1') is True
    assert stale('/v1/missions/m/trace') is True
    assert stale('/v1/missions/m/a/trace') is False


def test_matched_paths_are_anchored_end_to_end():
    """sync.py:164-170: '**' at the end may match nothing ('/v1/missions'
    under 'missions**'), the compiled regex is anchored '^'...'\\Z' with the
    query tail, so a longer path ('pln_1x', 'attentionz') does not match a
    rule written for the shorter one. Dropping the end anchor makes every
    rule a prefix match — reads never go stale when they should."""
    stale = S.stale_by(frame('plan', 'pln_1'))
    assert stale('/v1/plans/pln_1') is True
    assert stale('/v1/plans/pln_1?x=1') is True
    assert stale('/v1/plans/pln_1x') is False
    assert stale('/v1/plans/pln_1/?x') is False
    m = S.stale_by(frame('mission', 'm1'))
    assert m('/v1/missions') is True                           # '**' matches nothing
    assert m('/v1/attention?x') is True
    assert m('/v1/attentionz') is False


def test_a_subject_only_stales_reads_that_name_exactly_it():
    """sync.py:168 (re.escape of the id): a subject id is data, not a pattern.
    'a.c' must stale '/v1/verifications/a.c' and never 'aXc'; dropping the
    escape turns every dot in an id into a wildcard."""
    stale = S.stale_by(frame('verification', 'a.c'))
    assert stale('/v1/verifications/a.c') is True
    assert stale('/v1/verifications/a.c?from=1') is True
    assert stale('/v1/verifications/aXc') is False
    assert stale('/v1/missions/m/verifications') is True


def test_frames_without_a_usable_subject_stale_nothing_or_everything():
    """sync.py:177-179: a frame missing its data, its subject or its kind (or
    a kind with no rules at all) invalidates nothing — over-invalidating on
    noise would re-read the whole world on every frame. A known kind with no
    id still stales whatever its rules ask for without one: '{id}' compiles
    the empty id exactly, so '/v1/plans/pln_9' stays unmatched while the bare
    '/v1/plans/' and the id-free rules re-read — the surviving re-reads lean
    over-invalidate, never under."""
    unusable = [{'event': 'x'}, {'event': 'x', 'data': None}, {'event': 'x', 'data': {}},
                {'event': 'x', 'data': {'subject': None}},
                {'event': 'x', 'data': {'subject': {'id': 'msn_1'}}},
                frame('model', 'm1'), frame('no_such_kind', 'x')]
    paths = ('/v1/missions', '/v1/missions/msn_1/plan', '/v1/world/graph', '/v1/anything')
    for f in unusable:
        stale = S.stale_by(f)
        assert not [p for p in paths if stale(p)], f
    stale = S.stale_by(frame('plan'))                          # kind, no id
    assert stale('/v1/plans/') is True                          # empty id, exactly
    assert stale('/v1/plans/pln_9') is False                    # not a wildcard
    assert stale('/v1/missions/msn_1/plan') is True             # the id-free rules
    assert stale('/v1/world/graph') is True


def test_a_decision_body_is_the_card_s_four_fields_plus_only_what_is_added():
    """sync.py:97-100: with the default extra=None the `or {}` arm must hold
    (dropping it is a TypeError on every decision), the body echoes the
    action_hash and version of the card displayed (P9 X02), and the merge
    writes no caller's dict — the action dict keeps its own keys."""
    a = {'action_hash': 'abc', 'version': 4, 'title': 'not echoed'}
    body = S.decide_body(a, 'approve', 'k1')
    assert body == {'decision': 'approve', 'action_hash': 'abc',
                    'expected_version': 4, 'idempotency_key': 'k1'}
    extra = {'note': 'ok'}
    merged = S.decide_body(a, 'reject', 'k2', extra)
    assert merged == {'decision': 'reject', 'action_hash': 'abc',
                      'expected_version': 4, 'idempotency_key': 'k2', 'note': 'ok'}
    assert extra == {'note': 'ok'}
    assert a == {'action_hash': 'abc', 'version': 4, 'title': 'not echoed'}
    assert body is not a and merged is not a
