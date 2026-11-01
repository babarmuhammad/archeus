"""T-325: the ten highest-risk gaps in archeus/core/domain/states.py, as tests.

The table is the only thing the persistence primitive trusts (writer.py's
`Tx.transition()` checks the edge, the version and the reason against it, and
refuses a guarded edge without a `TransitionProof`), so the gaps closed here are
the ones where the table could fail open or fail silently: a guarded edge that
silently stops being guarded, a machine or an edge that silently disappears from
`TABLE`, an unknown machine or state that is answered with `[]`/`{}` instead of a
refusal, a pseudo-state that leaks into the real states, an ambiguous initial
state that is chosen instead of refused, and a `TransitionProof` that is not the
frozen named edge the primitive compares against.

Same style and fixtures as tests/v1/unit/test_state_tables.py and
tests/v1/unit/test_guards.py: the module is imported directly, the table is read
through its own helpers, and every sweep is generated over `states.MACHINES`.
No file, process, network, clock or OS call is involved, so nothing here is
platform-specific; the only patched object is `states.TABLE`, always through
pytest's `monkeypatch`, and never a source file.
"""

import dataclasses
import re

import pytest

from archeus.core.domain import states

ALL_TRIGGERS = sorted({t for m in states.MACHINES
                       for _f, _to, t, _g in states.edges(m) if t})

#: The five machines that share the state name PENDING, and the review/verification
#: ones that share RUNNING: the row that makes them different is `row[0] == machine`.
SHARED_NAMES = {
    ('task', 'PENDING'): {'deps_satisfied': 'READY', 'skip': 'SKIPPED', 'cancel': 'CANCELLED'},
    ('approval', 'PENDING'): {'approve': 'APPROVED', 'reject': 'REJECTED',
                              'ttl_elapsed': 'EXPIRED', 'plan_replaced': 'SUPERSEDED'},
    ('verification', 'PENDING'): {'start': 'RUNNING', 'generic_verifier': 'AWAITING_HUMAN'},
    ('review', 'PENDING'): {'start': 'IN_REVIEW', 'user_reviews': 'IN_REVIEW'},
    ('integration', 'PENDING'): {'task_verified': 'MERGING'},
    ('task', 'READY'): {'dispatch': 'ROUTING', 'cancel': 'CANCELLED'},
    ('verification', 'RUNNING'): {'all_checks_pass': 'PASSED', 'a_check_fails': 'FAILED',
                                  'verifier_crashed': 'ERROR'},
    ('review', 'IN_REVIEW'): {'verdict_accept': 'ACCEPTED', 'verdict_changes':
                              'CHANGES_REQUESTED', 'verdict_reject': 'REJECTED'},
}

INITIAL = {
    'idea': 'CAPTURED', 'mission': 'CREATED', 'plan': 'DRAFT', 'task': 'PENDING',
    'execution': 'INTENT', 'session': 'OPEN', 'approval': 'PENDING',
    'verification': 'PENDING', 'review': 'PENDING', 'automation': 'DRAFT',
    'automation_run': 'CLAIMED', 'account_health': 'UNVERIFIED',
    'repository_inspection': 'SCHEDULED', 'architecture': 'UNKNOWN',
    'knowledge_item': 'CANDIDATE', 'device': 'PAIRING', 'execution_node': 'ONLINE',
    'integration': 'PENDING',
}

TERMINAL = {
    'idea': {'LEARNED'}, 'mission': {'COMPLETED', 'CANCELLED'},
    'plan': {'REJECTED', 'SUPERSEDED'},
    'task': {'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED'},
    'execution': {'ABANDONED', 'ENDED_OK', 'ENDED_ERROR', 'ENDED_KILLED', 'ENDED_HANDOFF',
                  'ENDED_REJECTED'},
    'session': set(), 'approval': {'REJECTED', 'EXPIRED', 'SUPERSEDED', 'CONSUMED'},
    'verification': {'PASSED', 'FAILED'},
    'review': {'ACCEPTED', 'CHANGES_REQUESTED', 'REJECTED'},
    'automation': {'ARCHIVED'},
    'automation_run': {'SKIPPED', 'ESCALATED', 'SUCCEEDED', 'FAILED'},
    'account_health': set(), 'repository_inspection': {'COMPLETED'}, 'architecture': set(),
    'knowledge_item': {'SUPERSEDED', 'RETRACTED'}, 'device': {'REVOKED'},
    'execution_node': set(), 'integration': {'MERGED', 'ABANDONED'},
}

#: The guard table as the writer sees it: (machine, trigger) -> guarded. A name
#: lost here is an edge the primitive then takes with no proof at all.
GUARDED = {
    ('mission', name) for name in (
        'plan_auto_approved', 'plan_needs_approval', 'all_tasks_done', 'verified',
        'awaiting_human_acceptance', 'replan_budget_exhausted', 'task_failed_retryable',
        'unrecoverable', 'verification_failed', 'redispatch', 'accepted', 'approve',
        'plan_denied')} | {
    ('plan', 'ready'), ('approval', 'approve'), ('integration', 'task_verified')} | {
    ('architecture', name) for name in ('first_inspection', 'first_inspection_drift',
                                        'reinspected_no_drift', 'reinspected_drift')}


def _row(machine, frm, to, trig, guard=None):
    """One row of `TABLE`, the way the comprehension at states.py:388 builds it."""
    return (machine, frm, to, trig, guard)


# ── 1. an unknown machine is refused by name, never answered with an empty table ──

@pytest.mark.parametrize('machine', ['nope', 'missions', 'Mission', 'TASK', '', None, 0,
                                     'states', 'harness', 'task '])
def test_edges_refuses_a_machine_that_has_no_edges(machine):
    """states.py:401-402 — `if machine not in _EDGES: raise KeyError(machine)`.

    The refusal is by name, so the caller sees which machine it asked about. The
    list is not empty and no edge is allowed: a machine Core never declared has no
    transitions at all, `harness` included — it is a STATE_SETS entry, so `states`
    and `initial` answer for it while `edges` still refuses (see the STATE_SETS
    test below). Dropping the raise, or returning `[]` instead, turns every
    "unknown machine" into "this machine has no edges", which the primitive reads
    as a mere InvalidTransition and the schema reads as an empty enum."""
    with pytest.raises(KeyError) as err:
        states.edges(machine)
    assert err.value.args[0] == machine


def test_the_other_helpers_refuse_an_unknown_machine_rather_than_saying_nothing():
    """states.py:401-402 through 428 and 431-434.

    `terminal` and `targets` have no check of their own: they inherit the raise
    from `edges`. If either grew a silent `return frozenset()` / `return {}` — or if
    `edges` began returning `[]` — then `terminal('nope')` would report "nothing is
    terminal", `targets('nope', 'PENDING')` would report "no trigger is allowed",
    and a caller asking about a machine it misspelled could not tell the two apart
    from a real answer."""
    for call in (lambda: states.terminal('nope'), lambda: states.targets('nope', 'PENDING'),
                 lambda: states.terminal('harness'),
                 lambda: states.targets('harness', 'AVAILABLE'),
                 lambda: states.terminal('task ')):
        with pytest.raises(KeyError):
            call()
    # ... while a STATE OUTSIDE the machine really is answered, and answered closed
    assert states.targets('mission', 'NOT_A_STATE') == {}
    assert states.targets('mission', 'PENDING') == {}       # another machine's state
    assert states.targets('mission', 'pending') == {}       # not even a case-insensitive hit


# ── 2. the guard column: a lost guard is a fail-open, so it is pinned exactly ──

def test_the_guard_column_is_exactly_the_guard_table_and_nothing_else():
    """states.py:388-390 — `trig if trig in _GUARDED.get(m, ()) else None`.

    Checked row by row against the source of truth it recomputes from, so an
    inversion (`not in`), a dropped machine argument to `get` (`trig in _GUARDED`)
    or a truthiness test instead of the `is not None` shape is caught. A row that
    should be guarded and is not is the fail-open the primitive cannot see: the
    writer's `if g is not None: raise InvalidTransition` simply never fires."""
    assert list(states.TABLE) == [
        _row(m, f, t, trig, trig if trig in states._GUARDED.get(m, ()) else None)
        for m in states.MACHINES for f, t, trig in states._EDGES[m]]
    assert {(m, g) for m, _f, _to, _t, g in states.TABLE if g is not None} == GUARDED
    # a guard is its own trigger's name, or nothing: never a foreign string
    assert all(g in (None, trig) for _m, _f, _to, trig, g in states.TABLE)
    assert all((g is None) == ((m, trig) not in GUARDED)
               for m, _f, _to, trig, g in states.TABLE)
    assert sum(1 for r in states.TABLE if r[4] is not None) == 22   # 20 triggers, two of
    # the mission's (`plan_needs_approval`, `plan_auto_approved`) fire from PLANNING and
    # from REPLANNING, so a guarded trigger is two rows and a row count is the check
    # that neither of them quietly became unguarded.


def test_no_guard_is_lost_by_a_typo_in_the_guard_table():
    """states.py:370-386 and 389 — a name in `_GUARDED` that matches no edge is
    silently unguarded, because TABLE only ever marks edges it finds.

    Each of the five machines must be a real machine, and each of its triggers must
    be a trigger that machine's edges actually carry. A mistyped machine key drops
    every guard of that machine at once (`_GUARDED.get(m, ())` then returns the
    empty default for it), and a mistyped trigger drops exactly one — in both cases
    the edge stays in the table, stays legal, and stops needing a proof."""
    assert set(states._GUARDED) <= set(states.MACHINES), 'a guarded machine is not a machine'
    for machine, triggers in states._GUARDED.items():
        assert isinstance(triggers, (set, frozenset)), machine
        assert triggers, machine
        assert all(isinstance(t, str) and re.fullmatch(r'[a-z][a-z_]*', t) for t in triggers), \
            (machine, triggers)
        declared = {t for _f, _to, t in states._EDGES[machine] if t}
        assert triggers <= declared, '%s guards triggers it does not have: %s' % (
            machine, sorted(triggers - declared))
    assert {(m, t) for m, ts in states._GUARDED.items() for t in ts} == GUARDED
    # the unguarded machines are unguarded on purpose, not by omission
    assert set(states.MACHINES) - set(states._GUARDED) == {
        'idea', 'task', 'execution', 'session', 'verification', 'review', 'automation',
        'automation_run', 'account_health', 'repository_inspection', 'knowledge_item',
        'device', 'execution_node'}


def test_the_denial_edges_are_guarded_and_stay_reachable():
    """states.py:389 for the edges whose guard is a refusal — a recorded denial
    (`plan_denied`), a real authorisation (`approve`, twice), the budget and failure
    guards, P8's validator (`ready`) and P13's merge check (`task_verified`).

    Each must exist exactly once, carry its guard, be offered from the one state
    that may fire it, and be refused from every other state of that machine: a
    trigger that is legal from two states is a second way to reach the same
    outcome without the guard being judged for that row."""
    for machine, frm, to, trig in (('mission', 'REASONING', 'BLOCKED', 'plan_denied'),
                                   ('mission', 'APPROVAL_REQUIRED', 'APPROVED', 'approve'),
                                   ('mission', 'REPLANNING', 'BLOCKED',
                                    'replan_budget_exhausted'),
                                   ('mission', 'EXECUTING', 'FAILED', 'unrecoverable'),
                                   ('mission', 'EXECUTING', 'REPLANNING',
                                    'task_failed_retryable'),
                                   ('mission', 'VERIFYING', 'BLOCKED',
                                    'awaiting_human_acceptance'),
                                   ('plan', 'DRAFT', 'PROPOSED', 'ready'),
                                   ('approval', 'PENDING', 'APPROVED', 'approve'),
                                   ('integration', 'PENDING', 'MERGING', 'task_verified')):
        rows = [r for r in states.edges(machine) if r[:3] == (frm, to, trig)]
        assert len(rows) == 1, (machine, frm, to, trig)
        assert rows[0][3] == trig, 'the edge %s.%s->%s lost its guard' % (machine, frm, trig)
        assert states.targets(machine, frm)[trig] == to
        # and the same trigger from any other state of the machine stays refused
        for other in states.states(machine):
            if other != frm:
                assert trig not in states.targets(machine, other), (machine, other, trig)


# ── 3. no machine and no edge may vanish from TABLE in silence ──

def test_the_table_holds_every_declared_edge_of_every_machine():
    """states.py:388-390 — `for m in MACHINES for ... in _EDGES[m]`.

    The comprehension walks `MACHINES`, not `_EDGES`, so a machine added to `_EDGES`
    without a matching name in `MACHINES` disappears from the table completely: no
    error, no missing row anyone can see, and every transition of that machine then
    refused while `edges()` (which only checks `_EDGES`, states.py:401) reports an
    empty list instead of the KeyError that would say so."""
    assert list(states._EDGES) == list(states.MACHINES)      # same set, same order
    assert len(states.TABLE) == sum(len(v) for v in states._EDGES.values())
    assert [m for m in dict.fromkeys(r[0] for r in states.TABLE)] == list(states.MACHINES)
    for machine in states.MACHINES:
        assert [(f, t, trig, g) for f, t, trig, g in states.edges(machine)] == \
            [(f, t, trig, trig if trig in states._GUARDED.get(machine, ()) else None)
             for f, t, trig in states._EDGES[machine]]


def test_edges_returns_the_four_fields_and_a_fresh_list_each_time():
    """states.py:403 — `[row[1:] for row in TABLE if row[0] == machine]`.

    The machine column is stripped, the guard column is kept, and the result is a
    new list: the caller may sort it, empty it or pop it without moving the table
    for the next caller — the writer reads the table on every transition, so a
    shared mutable list is a way for one bad caller to open an edge for everyone."""
    first = states.edges('task')
    assert isinstance(first, list) and all(isinstance(r, tuple) and len(r) == 4 for r in first)
    assert [r[0] for r in first] != [] and 'task' not in first[0]
    assert first is not states.edges('task')
    first.append(('GONE', 'GONE', 'GONE', None))
    first.pop(0)
    assert states.edges('task') == [row[1:] for row in states.TABLE if row[0] == 'task']
    offered = states.targets('task', 'PENDING')
    offered['forge'] = 'NOWHERE'
    assert 'forge' not in states.targets('task', 'PENDING')


# ── 4. every transition allowed, every transition refused ──

@pytest.mark.parametrize('machine', states.MACHINES)
def test_every_transition_is_offered_exactly_where_the_table_declares_it(machine):
    """states.py:431-434 — `{t: to ... if frm == from_state and t is not None}`.

    The full grid of (real state x every trigger of the machine): a trigger the
    table declares from that state must be offered and must lead where the table
    says; every other one must be absent from the dict, which is the refusal the
    primitive acts on. Dropping `frm == from_state` lets a trigger fire from a
    state it was never declared for; dropping `t is not None` publishes the
    unlabelled `X --> [*]` rows as ordinary moves into `[*]`."""
    rows = states.edges(machine)
    assert [(f, to, trig) for f, to, trig, _g in rows] == \
        [(f, to, trig) for f, to, trig in states._EDGES[machine]], \
        '%s: edges() is not the declaration' % machine
    declared = {(f, trig): to for f, to, trig in states._EDGES[machine] if trig is not None}
    assert declared, machine
    real = [s for s in states.states(machine)]
    checked = 0
    for frm in real:
        offered = states.targets(machine, frm)
        assert offered == {trig: to for (f, trig), to in declared.items() if f == frm}
        for trig in ALL_TRIGGERS:                      # the refused half, one by one
            if (frm, trig) in declared:
                assert offered[trig] == declared[(frm, trig)], (machine, frm, trig)
            else:
                assert trig not in offered, '%s allows %s from %s' % (machine, trig, frm)
            checked += 1
    assert checked == len(real) * len(ALL_TRIGGERS)


@pytest.mark.parametrize('machine', states.MACHINES)
def test_the_pseudo_states_are_never_a_place_to_act_from(machine):
    """states.py:434 (`t is not None`) and 22 (`START = END = '[*]'`).

    `[*]` appears twice in every diagram, as the arrow in and as the arrow out.
    Neither may look like a state you can fire a trigger from: the START rows carry
    no trigger at all, and nothing leaves END. If the `t is not None` filter went
    the machine's initial state would offer `{None: 'X'}` and, worse, a state whose
    only exit is `--> [*]` would offer `[*]` as a destination."""
    assert states.START == states.END == '[*]'
    assert states.targets(machine, states.START) == {}
    assert states.targets(machine, states.END) == {}
    assert states.START not in states.states(machine)
    # no triggered edge walks into or out of a pseudo-state, except the one edge whose
    # whole meaning is ending the row: the device's expired pairing code (states.py:341)
    assert [r for r in states.edges(machine) if r[2] is not None
            and states.START in (r[0], r[1])] == (
        [('PAIRING', states.END, 'code_expired', None)] if machine == 'device' else [])


@pytest.mark.parametrize('machine', states.MACHINES)
def test_a_terminal_state_refuses_every_trigger_the_repo_knows(machine):
    """states.py:428 — `to == END and t is None`, read back through 431-434.

    A terminal state is one whose only edge is the unlabelled arrow out, so no
    trigger of any machine — its own or another's — may be offered from it. The
    `t is None` half is what makes the device's PAIRING non-terminal: `code_expired`
    ends the row, so it is a trigger, so PAIRING is not terminal and must still
    refuse every other trigger while offering that one."""
    ends = states.terminal(machine)
    assert ends == TERMINAL[machine], machine
    assert ends <= set(states.states(machine))
    checked = 0
    for state in sorted(ends):
        for trig in ALL_TRIGGERS:
            assert trig not in states.targets(machine, state), (machine, state, trig)
            checked += 1
    if machine == 'device':
        assert 'PAIRING' not in ends
        assert states.targets('device', 'PAIRING') == {'code_redeemed': 'ACTIVE',
                                                      'code_expired': states.END}
    assert checked == len(ends) * len(ALL_TRIGGERS)


def test_only_the_pairing_code_can_be_ended_by_a_trigger():
    """states.py:428/434 read over the whole table: the END edges split exactly in two.

    Every `X --> [*]` except the device's pairing row is unlabelled and so marks a
    terminal state; if the `t is None` test were dropped, `terminal()` would start
    reporting PAIRING as terminal (and `test_a_terminal_state_refuses...` would then
    fail on a state that still has a trigger), and a `t is not None` inversion would
    make `[*]` an ordinary target of every end edge."""
    to_end = [r for r in states.TABLE if r[2] == states.END]
    assert [r for r in to_end if r[3] is not None] == [
        ('device', 'PAIRING', states.END, 'code_expired', None)]
    assert all(r[3] is None for r in to_end if r[0] != 'device')
    assert sum(1 for r in to_end if r[3] is None) == sum(len(states.terminal(m))
                                                         for m in states.MACHINES) == 35
    # the terminal states are exactly the sources of those unlabelled edges
    for machine in states.MACHINES:
        assert states.terminal(machine) == {f for f, to, t, _g in states.edges(machine)
                                            if to == states.END and t is None}


@pytest.mark.parametrize(('machine', 'state'), sorted(SHARED_NAMES))
def test_machines_that_share_a_state_name_do_not_bleed_into_each_other(machine, state):
    """states.py:403 (`row[0] == machine`) and 431-434 (`frm == from_state`).

    Five machines spell their initial state PENDING and more than one spells a later
    state RUNNING. With the machine filter dropped,
    `states.targets('task', 'PENDING')` would gain `start` from verification and
    review and `task_verified` from integration — an edge nobody declared, taken
    through a state name that happens to be spelled the same. These are the literal
    answers of each of those states, so a leak in either direction is a failure."""
    assert states.targets(machine, state) == SHARED_NAMES[(machine, state)]
    for other in states.MACHINES:
        if other != machine and state in states.states(other):
            assert states.targets(other, state) != SHARED_NAMES[(machine, state)], \
                '%s and %s answer %s identically' % (machine, other, state)


# ── 5. the state list, its order, and the STATE_SETS shortcut ──

@pytest.mark.parametrize('machine', states.MACHINES)
def test_the_state_list_is_the_declaration_in_first_seen_order(machine):
    """states.py:406-415 — the dedup loop and `if s != START`.

    `api/schemas.py` publishes `list(states.states('architecture'))` as an enum in
    that order and `test_replay.py` compares the whole (machine, state) set against
    it, so both the order and the exclusion are load-bearing: the pseudo-state
    `[*]` must never reach a client, and a state must appear exactly once at the
    first place the table mentions it. Inverting the membership test duplicates a
    state; dropping the `s != START` test puts `[*]` in the enum."""
    seen = []
    for frm, to, _t, _g in states.edges(machine):
        for s in (frm, to):
            if s != states.START and s not in seen:
                seen.append(s)
    got = states.states(machine)
    assert isinstance(got, tuple) and got == tuple(seen)
    assert len(set(got)) == len(got) and states.END not in got
    assert all(re.fullmatch(r'[A-Z][A-Z_0-9]*', s) for s in got), machine
    assert states.initial(machine) == got[0], '%s does not start at its first state' % machine


def test_a_state_set_entry_is_read_verbatim_and_is_not_a_machine():
    """states.py:394-396, 408-409 and 420-421 — the STATE_SETS shortcut.

    `harness` has states and an initial state but no edges, so `states()` and
    `initial()` answer for it from `STATE_SETS` while `edges()`/`terminal()`/
    `targets()` keep raising. The shortcut is a `machine in STATE_SETS` test taken
    BEFORE any table lookup, so the sets must not overlap the machines: were
    'mission' ever added there, `states('mission')` would return that tuple instead
    of the table's states and every schema enum and entity validation for missions
    would silently start refusing the real ones."""
    assert states.STATE_SETS == {'harness': ('AVAILABLE', 'MISSING', 'MISCONFIGURED')}
    assert states.states('harness') == ('AVAILABLE', 'MISSING', 'MISCONFIGURED')
    assert states.initial('harness') == 'AVAILABLE'          # first of the set, by position
    assert not set(states.STATE_SETS) & set(states.MACHINES)
    assert not set(states.STATE_SETS) & set(states._EDGES)
    for name, values in states.STATE_SETS.items():
        assert isinstance(values, tuple) and len(set(values)) == len(values) > 0
        assert all(re.fullmatch(r'[A-Z][A-Z_0-9]*', s) for s in values), name
        with pytest.raises(KeyError):
            states.edges(name)


# ── 6. the initial state: exactly one, or nothing is answered ──

@pytest.mark.parametrize('machine', states.MACHINES)
def test_the_initial_state_is_the_single_state_the_machine_starts_in(machine):
    """states.py:418-423 — `(first,) = [to ... if frm == START]`.

    Exactly one `[*] -->` row per machine, and `initial()` is its target: an entity
    is created at that state (`entities.py` seeds it) so a second start row is not
    a choice to make, it is a contradiction to refuse. The unpacking is what refuses,
    so the same test pins the row count, that the initial state is never itself
    terminal, and that no trigger from it reaches the pseudo-state."""
    starts = [to for f, to, _t, _g in states.edges(machine) if f == states.START]
    assert len(starts) == 1, '%s has %d start edges' % (machine, len(starts))
    first = states.initial(machine)
    assert first == starts[0] == INITIAL[machine]
    assert first not in states.terminal(machine), '%s starts terminal' % machine
    assert first in states.states(machine)
    assert states.START not in states.targets(machine, first)


def test_an_ambiguous_or_missing_initial_state_is_an_error_not_a_pick(monkeypatch):
    """states.py:422 — the `(first,) =` unpacking, on all three shapes.

    Two start edges, no start edge, or a start edge that is not the machine's first
    row: the helper must raise, or must still pick the row that actually starts the
    machine. If the unpacking were relaxed to `[0]`, a duplicated start edge would
    hand out whichever row came first, and a row insert at the top of `_EDGES` would
    silently decide where every new mission begins."""
    real = states.TABLE
    ghost = _row('verification', states.START, 'GHOST', None)
    monkeypatch.setattr(states, 'TABLE', real + (ghost,))
    with pytest.raises(ValueError):
        states.initial('verification')
    without = tuple(r for r in real if not (r[0] == 'verification' and r[1] == states.START))
    monkeypatch.setattr(states, 'TABLE', without)
    with pytest.raises(ValueError):
        states.initial('verification')
    # the START row is found by its pseudo-state, not by being the machine's first row
    reordered = tuple(r for r in real if r[0] != 'verification') + (
        _row('verification', 'PASSED', 'RUNNING', 'stale', None),
        _row('verification', states.START, 'PENDING', None, None))
    monkeypatch.setattr(states, 'TABLE', reordered)
    assert states.initial('verification') == 'PENDING'
    # and `states()` walks the table it is given rather than a copy made at import:
    # the first state it reports is the first the (patched) table mentions
    assert states.states('verification')[0] == 'PASSED'
    assert 'PENDING' in states.states('verification')


# ── 7. the proof the primitive compares itself against ──

def test_a_transition_proof_is_a_frozen_named_edge_in_a_fixed_order():
    """states.py:25-40 — `@dataclass(frozen=True)`, the field order and the defaults.

    The writer compares `(proof.entity_id, proof.version, proof.frm, proof.to)` and
    `(proof.trigger, proof.guard)` against the row it is about to change. Positional
    construction is what the field order is for: reorder the fields and a proof
    built by position binds a row id where a version belongs, and the comparison
    still "matches" for whatever the caller passed. `guard` defaults to None so a
    proof for an unguarded edge cannot claim a guard, and `frozen` is what stops a
    proof judged against one row being rewritten to point at another."""
    proof = states.TransitionProof('mission/1', 7, 'PLANNING', 'APPROVED',
                                   'plan_auto_approved')
    assert (proof.entity_id, proof.version, proof.frm, proof.to, proof.trigger) == (
        'mission/1', 7, 'PLANNING', 'APPROVED', 'plan_auto_approved')
    assert (proof.guard, proof.guard_reason) == (None, None)
    assert [f.name for f in dataclasses.fields(proof)] == [
        'entity_id', 'version', 'frm', 'to', 'trigger', 'guard', 'guard_reason']
    with pytest.raises(dataclasses.FrozenInstanceError):
        proof.version = 8
    with pytest.raises(dataclasses.FrozenInstanceError):
        proof.to = 'EXECUTING'
    assert proof == states.TransitionProof('mission/1', 7, 'PLANNING', 'APPROVED',
                                           'plan_auto_approved')
    assert proof != states.TransitionProof('mission/1', 8, 'PLANNING', 'APPROVED',
                                           'plan_auto_approved')
    # the table's guard for the trigger is the proof's guard: None where unguarded
    assert {(m, trig) for m, _f, _to, trig, g in states.TABLE if g is None} >= {
        ('task', 'dispatch'), ('session', 'close'), ('integration', 'conflict')}
    assert all(g == trig for m, f, to, trig, g in states.TABLE if g is not None)
