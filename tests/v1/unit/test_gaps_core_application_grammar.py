"""T-735: the highest-risk uncovered branches of
archeus/core/application/grammar.py — denial and fail-closed paths first
(every way a sentence must go to the brain instead of being obeyed), then the
boundary values (`all`, `stop` on a running mission, signed priorities, the
one verb that is not one word), then the error paths, then idempotency and
replay of the same request. Same style and seams as the sibling gap tests
(test_gaps_core_application_executions.py, test_gaps_core_application_resources.py):
the real database on the test's own ARCHEUS_HOME, rows written directly with
the writer — `resolve` reads one snapshot and writes nothing, so no command
layer, no brain, no process, no network, no sleep, nothing Windows-specific.
Each test names in its docstring the source branch whose removal or inversion
it would catch.
"""

import pytest

from archeus.core.application import grammar
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

ACTOR = Ref('user_device', ids.new_id('principal'))

#: entity kind -> a registered event type whose subject kind matches, for the
#: writer's event audit (see `_note`)
_SEED_EVENT = {'mission': 'mission.updated', 'project': 'project.created',
               'account': 'account.registered'}


def _note(tx, kind, entity_id):
    """The writer's one-law audit (writer.py:441-443): a transaction that mutates
    must record an event. Seeding rows for a read-only parse is not a domain
    move, so the seed helper records one registered, subject-matching event per
    transaction (same device as tests/v1/unit/test_gaps_core_application_
    executions.py, which appends a `mission.updated` next to its seed rows)."""
    tx.append(new_event(_SEED_EVENT[kind], Ref(kind, entity_id),
                        ACTOR, payload={}, workspace=ids.GLOBAL_WORKSPACE))


@pytest.fixture
def db():
    d = Database.open()
    yield d
    d.close()


def _write(db, *new):
    def run(tx, **_):
        for e in new:
            tx.insert(e, actor=ACTOR)
        _note(tx, type(new[0])._ID, new[0].id)
    db.writer.execute(run, {})


def _move_mission(db, entity_id, to):
    """Take the real `pause` edge EXECUTING -> PAUSED (unguarded, states.py:95):
    the replay test moves the world the same way the machine does."""
    def run(tx, **_):
        tx.transition(entities.Mission, entity_id, to, actor=ACTOR, reason='test')
    db.writer.execute(run, {})


def mission(title, state='CREATED', mid=None):
    return entities.Mission(id=mid or ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                            title=title, objective='o', state=state)


def project(name, state='ACTIVE', pid=None):
    return entities.Project(id=pid or ids.new_id('project'), workspace_id=ids.GLOBAL_WORKSPACE,
                            name=name, state=state)


def account(label, aid=None):
    return entities.Account(id=aid or ids.new_id('account'), harness_id='claude_code',
                            label=label, auth_kind='api_key')


def resolve(db, text, **kw):
    with db.read() as conn:
        return grammar.resolve(conn, text, **kw)


def one(db, cls, entity_id):
    with db.read() as conn:
        return rows.get(conn, cls, entity_id)


# ── denial and fail-closed first ─────────────────────────────────────────────

@pytest.mark.parametrize('text', ['use A for Ghost', "don't use A for Ghost",
                                  'use Ghost for M', "don't use Ghost for M",
                                  'use A', "don't use A", 'use', 'do not use'],
                         ids=['ghost-mission', 'ghost-mission-dont', 'ghost-resource',
                              'ghost-resource-dont', 'no-thread', 'no-thread-dont',
                              'bare-use', 'bare-dont'])
def test_a_use_that_does_not_resolve_is_the_brains(db, text):
    """grammar.py:126-127 — `if m is None or r is None: return None` (the
    comment's own words: what does not resolve is the brain's) and the parse
    refusal at 56-61 for `do not use` with no object. Were the gate dropped,
    a `use`/`don't use` naming no mission or no account would still become a
    Control, and the directive path would act on a half-resolved request —
    the fail-closed gate of P19 B10 / ADR-0042 §1."""
    _write(db, mission('M'), account('A'))
    assert resolve(db, text) is None


@pytest.mark.parametrize('verb', ['pause', 'resume', 'cancel', 'stop'],
                         ids=['pause', 'resume', 'cancel', 'stop'])
def test_a_bare_mission_verb_outside_a_mission_thread_is_the_brains(db, verb):
    """grammar.py:143 (`m = _mission(...) if p.arg else None`) then 146-147
    (`if m is None: return None`). Dropped, a bare `pause` in a thread that
    belongs to no mission would resolve to *something* — there is nothing to
    act on, so the only safe answer is the brain's."""
    assert resolve(db, verb) is None                      # no thread: nothing to pause


@pytest.mark.parametrize('verb', ['pause', 'resume', 'cancel', 'stop'],
                         ids=['pause', 'resume', 'cancel', 'stop'])
def test_in_a_mission_thread_a_bare_mission_verb_is_about_that_mission(db, verb):
    """grammar.py:144-145 — `if m is None and mission and not p.arg: m =
    rows.get(...).entity`. Inverted or dropped, `pause` in a mission's own
    thread (P19 S1) would go to the brain instead of resolving to the thread's
    mission."""
    m = mission('M')
    _write(db, m)
    assert resolve(db, verb, mission=m.id) == grammar.Control(
        'cancel' if verb == 'stop' else verb, {'kind': 'mission', 'id': m.id}, '')


def test_a_mission_reference_must_be_exactly_one_open_mission(db):
    """grammar.py:70-71 (`_one`: len == 1 or nothing) through grammar.py:80 —
    two live missions titled `Ship It` (case and spacing aside) make `pause
    Ship it` ambiguous, and an unknown title matches none. Inverting `_one` to
    `matches[0]` would silently pick whichever was inserted first."""
    _write(db, mission('Ship It'), mission('  ship   it  '))
    assert resolve(db, 'pause Ship it') is None
    assert resolve(db, 'cancel ship IT') is None
    assert resolve(db, 'pause Something else') is None


def test_a_finished_mission_is_not_a_reference_by_title_but_stays_one_by_id(db):
    """grammar.py:75-76 (live = state not in states.terminal('mission')) and
    77-79 (an id reference falls back to the terminal row). By title a
    CANCELLED mission is not open, so `pause Old` must be the brain's; by its
    own id it still resolves — resolve is a read, the refusal of an
    out-of-state transition belongs to the command layer (docstring: `resolve`
    reads one snapshot and writes nothing)."""
    dead = mission('Old', state='CANCELLED')
    done = mission('Done', state='COMPLETED')
    _write(db, dead, done)
    assert resolve(db, 'pause Old') is None
    assert resolve(db, 'cancel Done') is None
    assert resolve(db, 'pause ' + dead.id) == grammar.Control(
        'pause', {'kind': 'mission', 'id': dead.id}, dead.id)
    # a terminal twin does not make the live one ambiguous either (76 filters
    # before 80 counts): the docstring's "one OPEN mission"
    _write(db, mission('Twin'))
    assert resolve(db, 'pause Twin').verb == 'pause'


def test_only_the_exact_words_emergency_stop_ask_for_the_estop(db):
    """grammar.py:130-132 — `return Control('estop', None, '') if key(p.arg)
    == 'stop' else None`. Inverted or loosened, `emergency halt` (or any
    sentence beginning `emergency ...`) would put the e-stop CARD in front of
    the user — and that card, once confirmed, pauses everything (P19 B10)."""
    assert resolve(db, 'emergency stop') == grammar.Control('estop', None, '')
    assert resolve(db, 'EMERGENCY STOP!') == grammar.Control('estop', None, '')
    assert resolve(db, 'emergency halt') is None
    assert resolve(db, 'emergency') is None
    assert resolve(db, 'emergency stop now') is None
    assert resolve(db, 'emergency  ALL') is None          # estop has no all-scope
    assert resolve(db, 'stop emergency') is None          # not an emergency at all


def test_pause_all_wins_over_a_mission_titled_all_but_that_mission_keeps_its_id(db):
    """grammar.py:133-134 — `if p.verb in ALL_VERBS and key(p.arg) == 'all':
    return Control(ALL_VERBS[...], None, '')` runs BEFORE the mission lookup.
    Move it below the mission branch (or drop it) and `pause all` with a
    mission titled `all` becomes a single pause instead of the pause-everything
    card (P19.5); the comment also promises the title stays reachable by id."""
    m = mission('all')
    _write(db, m)
    assert resolve(db, 'pause all') == grammar.Control('pause_all', None, '')
    assert resolve(db, 'PAUSE  ALL .') == grammar.Control('pause_all', None, '')
    assert resolve(db, 'resume all') == grammar.Control('resume_all', None, '')
    assert resolve(db, 'pause ' + m.id) == grammar.Control(
        'pause', {'kind': 'mission', 'id': m.id}, m.id)
    assert resolve(db, 'pause all of them') is None       # not `all`, no such title


@pytest.mark.parametrize('state, expected',
                         [('EXECUTING', 'stop_running'), ('PAUSED', 'cancel'),
                          ('CREATED', 'cancel'), ('BLOCKED', 'cancel')],
                         ids=['executing', 'paused', 'created', 'blocked'])
def test_stop_is_one_card_only_while_the_mission_runs(db, state, expected):
    """grammar.py:149-152 — `verb = 'stop_running' if m.state == 'EXECUTING'
    else 'cancel'` (C-33). Inverted, a running mission gets a plain `cancel`
    — which has no edge from EXECUTING — or a paused one gets the pause-then-
    cancel card, and the command layer breaks either way."""
    m = mission('M', state=state)
    _write(db, m)
    assert resolve(db, 'stop M').verb == expected
    assert resolve(db, 'cancel M').verb == 'cancel'       # cancel never becomes stop_running


def test_why_never_guesses_a_target(db):
    """grammar.py:160-162 (bare `why`: the thread's mission, or the brain when
    there is no thread — R13-05) and 163-164 (a `why` whose argument is not a
    well-formed id resolves to nothing: `why rte_01` is not a reference).
    Dropping the id check would make `why` accept titles, where one misspelled
    title silently asks about the wrong object."""
    m = mission('M')
    _write(db, m)
    assert resolve(db, 'why') is None                     # no thread: nothing to explain
    assert resolve(db, 'why', mission=m.id) == grammar.Control(
        'why', {'kind': 'mission', 'id': m.id}, '')
    assert resolve(db, 'why M') is None                   # a title is not an id
    assert resolve(db, 'why rte_01') is None              # not even a well-formed one
    assert resolve(db, 'why ' + m.id) == grammar.Control(
        'why', {'kind': 'mission', 'id': m.id}, m.id)
    assert resolve(db, 'why ws_global') == grammar.Control(
        'why', {'kind': 'workspace', 'id': 'ws_global'}, 'ws_global')


def test_status_targets_one_project_or_the_whole_board(db):
    """grammar.py:154-158 — bare `status` is Control('status', None, ''), but
    a named status needs exactly one project (83-87 through _one), or it is
    the brain's. Dropped, `status Ghost` would render some board as if it had
    been asked for."""
    p = project('archeus')
    _write(db, p, project('Two'), project('two'), project('Old', state='ARCHIVED'))
    assert resolve(db, 'status') == grammar.Control('status', None, '')
    assert resolve(db, 'Status   ARCHIVED .') is None     # no such name
    assert resolve(db, 'status Ghost') is None
    assert resolve(db, 'status Two') is None              # two projects, one name
    assert resolve(db, 'status archeus') == grammar.Control(
        'status', {'kind': 'project', 'id': p.id}, 'archeus')


def test_reprioritise_refuses_what_it_cannot_pin_down(db):
    """grammar.py:135-141 — a bare `reprioritise`, or one whose mission part
    does not resolve, is the brain's (137-139); and the priority group is only
    carried when _PRIORITY actually matched (141). Inverting 138-139 would
    reprioritise nothing, or whatever the sentence meant without the number."""
    m = mission('M')
    _write(db, m)
    assert resolve(db, 'reprioritise') is None
    assert resolve(db, 'reprioritise Ghost to 3') is None
    assert resolve(db, 'reprioritise M to') is None       # no digits: no match, no mission
    assert resolve(db, 'reprioritise M') == grammar.Control(
        'reprioritise', {'kind': 'mission', 'id': m.id}, '')


@pytest.mark.parametrize('text, arg',
                         [('reprioritise M to 3', '3'), ('reprioritise M 3', '3'),
                          ('reprioritize M to -2', '-2'), ('reprioritise m TO +7', '+7')],
                         ids=['to-3', 'bare-3', 'negative', 'plus'])
def test_the_priority_is_carried_verbatim_when_the_shape_matches(db, text, arg):
    """grammar.py:136 + 141 (`got.group(2) if got else ''`) with the _PRIORITY
    regex of line 36: the `to` is optional and the sign is part of the value.
    A lost sign or a lost number silently moves a mission to the wrong rank."""
    m = mission('M')
    _write(db, m)
    assert resolve(db, text).arg == arg


# ── parse: what is and is not a control verb (beyond the U01 table) ────────

@pytest.mark.parametrize('text', ['pause2 x', 'pause-all x', 'resume7', 'statuses archeus',
                                  '123', 'why3 x'],
                         ids=['pause2', 'pause-all', 'resume7', 'statuses', 'digits', 'why3'])
def test_a_control_verb_is_a_whole_word(text):
    """grammar.py:59-61 — `_WORDS` must match WHOLE (`([A-Za-z]+)...\\s*$`) and
    the word must be in VERBS. Relaxed (e.g. `re.match` without the end
    anchor, or a prefix lookup), `pause-all x` would issue a pause."""
    assert grammar.parse(text) is None


@pytest.mark.parametrize('text', ["don't use A", 'dont use A', 'do not  use A',
                                  "Don\u2019t use A.", 'DO NOT USE A!'])
def test_dont_use_is_the_one_verb_that_is_not_one_word(text):
    """grammar.py:56-58 — the _DONT branch (regex 44): the curly apostrophe and
    the spelled-out `do not` are the same verb, and the trailing `.`/`!` of the
    sentence is stripped with the rest of the arg (63). Miss it and `don't use
    A` is read by the brain instead of narrowing the mission's resources."""
    assert grammar.parse(text) == grammar.Parsed('dont_use', 'A')


@pytest.mark.parametrize('text', ["don use A", 'cannot use A', 'do not use', 'not use A'],
                         ids=['don', 'cannot', 'no-object', 'not'])
def test_a_nearly_dont_use_is_not_a_directive(text):
    """grammar.py:56 (`_DONT.match` fails) then 60 (`don`, `cannot`, `not` are
    not verbs): both fall through to None — the brain reads them."""
    assert grammar.parse(text) is None


def test_remember_keeps_what_only_looks_like_that(db):
    """grammar.py:64-66 — `re.sub(r'^that\\b', ...)` strips only the standalone
    lead-in: `remember thatch roof work` must keep `thatch` (a `^that` without
    the word boundary would eat it), and a remember with nothing left after
    stripping is not a control verb at all."""
    assert grammar.parse('remember thatch roof work') == grammar.Parsed(
        'remember', 'thatch roof work')
    assert grammar.parse('remember THAT tabs matter') == grammar.Parsed('remember', 'tabs matter')
    assert grammar.parse('remember that') is None
    assert resolve(db, 'remember that') is None           # the 66 None reaches resolve too


def test_the_arg_keeps_inner_punctuation_and_drops_only_trailing_dot_and_bang(db):
    """grammar.py:63 — `.strip().rstrip('.!')`: `cancel v1.2` keeps the inner
    dot (a mission is titled `v1.2`), trailing `!` goes; anything else that
    trails (`?`) stays, because the title must still match it. Loosening the
    strip would break the title match of the 80 line."""
    assert grammar.parse('cancel v1.2') == grammar.Parsed('cancel', 'v1.2')
    assert grammar.parse('pause Ship it!!') == grammar.Parsed('pause', 'Ship it')
    assert grammar.parse('pause Ship it?') == grammar.Parsed('pause', 'Ship it?')
    m = mission('v1.2')
    _write(db, m)
    assert resolve(db, 'cancel v1.2!') == grammar.Control(
        'cancel', {'kind': 'mission', 'id': m.id}, 'v1.2')


# ── resource: exactly one thing, or nothing (the use/dont_use argument) ────

def test_resource_names_exactly_one_thing_or_none(db):
    """grammar.py:94-104 — the `account`/`harness` prefix narrowing (95-97),
    the case/whitespace-insensitive match on id OR label (100-101), a harness
    only among the harnesses Core has (102-103), and `_one` (104): a bare name
    matching both an account label and a harness is refused, never guessed."""
    a = account('A')
    shared = account('The  Shared  Box')
    ghost = account('ghost')                                # label collides with a harness
    _write(db, a, shared, ghost)
    with db.read() as conn:
        def r(name, **kw):
            return grammar.resource(conn, name, **kw)
        assert r('A') == {'kind': 'account', 'id': a.id}
        assert r(a.id) == {'kind': 'account', 'id': a.id}   # by id, key-normalised
        assert r('the shared box') == {'kind': 'account', 'id': shared.id}
        assert r('THE   SHARED   BOX') == {'kind': 'account', 'id': shared.id}
        assert r('account A') == {'kind': 'account', 'id': a.id}
        assert r('account A', harnesses=('A',)) == {'kind': 'account', 'id': a.id}
        assert r('harness fake', harnesses=('fake',)) == {'kind': 'harness', 'id': 'fake'}
        assert r('harness fake', harnesses=('other',)) is None
        assert r('fake') is None                            # label AND harness: ambiguous
        assert r('A', harnesses=('fake',)) == {'kind': 'account', 'id': a.id}
        assert r('ghost', harnesses=('ghost',)) is None     # ambiguous again, id path
        assert r('no one') is None
        assert r('harness ghost', harnesses=('ghost',)) == {'kind': 'harness', 'id': 'ghost'}
        assert r('fake', kinds=('account',), harnesses=('fake',)) is None
        assert r('account ghost', harnesses=('ghost',)) == {'kind': 'account', 'id': ghost.id}
        assert r('fake', harnesses=('fake', 'FAKE')) is None    # twin harnesses: _one


@pytest.mark.parametrize('case', ['named', 'thread', 'nowhere', 'bare harness'],
                         ids=['named', 'thread', 'nowhere', 'bare'])
def test_a_use_names_its_scope_by_how_its_mission_got_there(db, case):
    """grammar.py:121-129 — `for <mission>` makes the scope 'mission' (129),
    no `for` in a mission's thread reads the thread's mission and the 'ambiguous'
    scope (123-124, 129: ADR-0042 §1), and with neither mission nor resource the
    whole thing is the brain's (126-127)."""
    m = mission('M')
    _write(db, m, account('A'))
    aid = a_id(db, 'A')
    if case == 'named':
        assert resolve(db, 'use account A for M') == grammar.Control(
            'use', {'kind': 'mission', 'id': m.id},
            {'resource': {'kind': 'account', 'id': aid}, 'scope': 'mission'})
    elif case == 'thread':
        assert resolve(db, 'use A', mission=m.id) == grammar.Control(
            'use', {'kind': 'mission', 'id': m.id},
            {'resource': {'kind': 'account', 'id': aid}, 'scope': 'ambiguous'})
    elif case == 'nowhere':
        assert resolve(db, 'use A') is None                # no thread, no `for`
        assert resolve(db, 'use harness fake', harnesses=('fake',)) is None
    else:
        got = resolve(db, 'use harness fake for M', harnesses=('fake',))
        assert got == grammar.Control('use', {'kind': 'mission', 'id': m.id},
                                      {'resource': {'kind': 'harness', 'id': 'fake'},
                                       'scope': 'mission'})


def a_id(db, label):
    with db.read() as conn:
        for r in rows.where(conn, entities.Account):
            if r.entity.label == label:
                return r.entity.id
    raise AssertionError('no account ' + label)


# ── purity, idempotency, replay ─────────────────────────────────────────────

def test_the_same_request_replays_identically_and_writes_nothing(db):
    """`parse` is pure, `resolve` reads one snapshot and writes nothing
    (module docstring, lines 18-19): the same request on the same snapshot is
    the same Control (idempotent replay — a retried message must not become a
    second, different card), and the rows keep the version the writer gave
    them (grammar.py:111-165 contains no write; any slipped `tx` use would
    bump the version the test reads here)."""
    m = mission('M', state='EXECUTING')
    _write(db, m, account('A'))
    before = one(db, entities.Mission, m.id)
    first = resolve(db, 'stop M')
    again = resolve(db, 'stop M')
    assert first == again == grammar.Control('stop_running', {'kind': 'mission', 'id': m.id}, 'M')
    assert resolve(db, "don't use A for M").arg['scope'] == 'mission'
    after = one(db, entities.Mission, m.id)
    assert (after.version, after.created_at, after.created_by) == \
           (before.version, before.created_at, before.created_by)


def test_a_replayed_request_follows_the_rows_not_a_cache(db):
    """Replay across a state change: the same text resolves differently once
    the world has moved (152 reads the row's CURRENT state — a cache, or a
    resolve that trusted an earlier snapshot, would keep handing out the
    stop_running card for a mission that has already paused."""
    m = mission('M', state='EXECUTING')
    _write(db, m)
    assert resolve(db, 'stop M').verb == 'stop_running'
    _move_mission(db, m.id, 'PAUSED')
    assert resolve(db, 'stop M').verb == 'cancel'
    assert resolve(db, 'stop M') == resolve(db, 'stop M')


def test_a_thread_whose_mission_row_is_gone_is_the_brains_not_a_crash(db):
    """grammar.py:144-145 — a bare `pause` in a thread whose mission id no
    longer resolves to a row must be the brain's, like every other reference
    that does not resolve (compare 143 + 146-147 for the named path); today it
    raises AttributeError on None.entity."""
    ghost = ids.new_id('mission')
    assert resolve(db, 'pause', mission=ghost) is None


def test_a_use_in_a_thread_whose_mission_row_is_gone_is_the_brains(db):
    """grammar.py:123-124 — same contract, the P19 B10 branch: `use A` with no
    `for` reads the thread's mission, and a thread id with no row must go to
    the brain, not crash."""
    _write(db, account('A'))
    ghost = ids.new_id('mission')
    assert resolve(db, 'use A', mission=ghost) is None
