"""The application-level transition (state-machines §0, plan §31.1 P3).

An *action* is what a caller asks for, named by the trigger of the edge it
wants (`pause`, `verified`, …). `fire()` turns it into a *transition* and the
P2 primitive records the *event*:

    resolve the edge (current state + trigger)   -> IllegalTrigger (422)
    check expected_version                       -> VersionConflict (409)
    evaluate the edge's guard, if it has one     -> GuardFailed (422)
    Tx.transition(..., proof=TransitionProof)    -> the row, version + 1, event

All of it runs inside the caller's writer transaction, on the row as it is in
that transaction, so a guard is judged on exactly the version it lets through
(the primitive re-checks that binding) and a refusal writes nothing.

The boundary with P2: guard *semantics* live in domain/guards.py and are run
only here; the persistence primitive checks a generic `TransitionProof` (edge,
row, version) against the P1 table and never imports a guard.

Trigger *legality* is decided here; whether an actor may *ask* for a trigger
is authorisation — the auth layer (P3.5) and policy (P9) — and is not.

An illegal trigger and a failed guard are different answers: the first means
the machine has no such move from here, the second that it has one and the
facts do not allow it yet.
"""

from ...infra.db.writer import InvalidTransition, NotFound, VersionConflict
from ..domain import guards, states


class IllegalTrigger(InvalidTransition):
    """The machine has no edge for this trigger from the current state.
    `to` is where the trigger leads elsewhere in the machine, when that is one
    place; None when it leads nowhere or to several."""

    def __init__(self, machine, frm, trigger, why=None):
        dests = {to for f, to, t, _g in states.edges(machine) if t == trigger}
        to = next(iter(dests)) if len(dests) == 1 else None
        super().__init__(machine, frm, to, why or 'no %r edge from %s' % (trigger, frm))
        self.trigger = trigger


class GuardFailed(RuntimeError):
    """The edge exists and its guard refused it (`422 guard_failed`)."""

    def __init__(self, machine, frm, to, trigger, result):
        super().__init__('%s: %s -> %s: guard %s refused: %s'
                         % (machine, frm, to, result.guard, result.reason))
        self.machine, self.frm, self.to, self.trigger = machine, frm, to, trigger
        self.result = result


def resolve(machine, frm, trigger):
    """(to, guard_name) for *trigger* from *frm*, or IllegalTrigger. A trigger
    that ends the machine (`--> [*]`) removes the row; that is not a state
    change, so it is not resolved here."""
    for f, to, t, g in states.edges(machine):
        if f == frm and t == trigger:
            if to == states.END:
                raise IllegalTrigger(machine, frm, trigger,
                                     '%r ends the machine; that removes the row and is '
                                     'not a state change' % trigger)
            return to, g
    raise IllegalTrigger(machine, frm, trigger)


def load(tx, cls, entity_id):
    row = tx.get(cls, entity_id)
    if row is None:
        raise NotFound(entity_id)
    return row


def check(machine, row, trigger, facts):
    """(to, GuardResult or None) for *trigger* on *row*, raising IllegalTrigger
    or GuardFailed. Writes nothing. *facts* may be a callable `facts(row)`, so
    a snapshot is gathered only for an edge that has a guard to read it."""
    field = row.entity._STATE[0]
    frm = getattr(row.entity, field)
    to, g = resolve(machine, frm, trigger)
    if g is None:
        return to, None
    if callable(facts):
        facts = facts(row)
    result = guards.evaluate(machine, trigger, row.entity, facts, version=row.version)
    if not result.passed:
        raise GuardFailed(machine, frm, to, trigger, result)
    return to, result


def fire(tx, cls, entity_id, trigger, *, actor, reason, facts=None,
         expected_version=None, cause=(), fields=None):
    """Take the *trigger* edge of *entity_id*'s machine. *facts* is the guard
    snapshot, or a callable building it from the row (only used when the edge
    is guarded). *fields* — a dict, or `fields(row, to)` — are other fields of
    the entity written with the move. Returns (Row, Event)."""
    if not cls._STATE:
        raise TypeError('%s has no state machine' % cls.__name__)
    if not (isinstance(reason, str) and reason.strip()):
        raise ValueError('a transition needs a reason (the audit trail)')
    field, machine = cls._STATE
    row = load(tx, cls, entity_id)
    if expected_version is not None and expected_version != row.version:
        raise VersionConflict(entity_id, expected_version, row.version)
    to, result = check(machine, row, trigger, facts)
    proof = states.TransitionProof(
        entity_id=entity_id, version=row.version, frm=getattr(row.entity, field), to=to,
        trigger=trigger, guard=result and result.guard, guard_reason=result and result.reason)
    if callable(fields):
        fields = fields(row, to)
    return tx.transition(cls, entity_id, to, actor=actor, reason=reason, cause=cause,
                         expected_version=row.version, proof=proof, fields=fields)
