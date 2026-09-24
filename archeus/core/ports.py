"""The six seams later phases fill in, and the P1 stubs behind five of them.

Callers are written against these Protocols, so P9 (policy), P10 (router), P7
(brain) and P13 (verification, review) replace a stub without touching a
caller. The stubs are deliberately dumb and say so: they exist so the walking
skeleton and the judge have something to call, not as first drafts.

`Node` has no stub: the P3.5 walking skeleton (archeus/core/engine.py) drives
the fake harness through the adapter registry directly; the node contract gets
its local implementation with the execution manager (P11).

The second group of stubs (P3.5) is what the walking skeleton runs on: a policy
that answers one fixed decision, a brain that proposes one fixed plan, and a
verifier and a reviewer whose verdicts a test scripts. Each is deterministic.
"""

import copy
from typing import Mapping, Optional, Protocol, runtime_checkable

from .domain import entities, ids
from .domain.actions import Action
from .domain.values import Ref


@runtime_checkable
class Policy(Protocol):
    """May Archeus perform this exact action, in this context, right now? (plan §13)"""
    is_stub: bool

    def evaluate(self, action: Action, ctx: Mapping) -> entities.PolicyDecision: ...


@runtime_checkable
class Router(Protocol):
    """Deterministic resource selection (resource-router §5)."""

    def route(self, subject: Ref, now: float) -> entities.RouteDecision: ...


@runtime_checkable
class Brain(Protocol):
    """Tool-less structured-output calls, validated against a named schema
    (`intent.v1`, `plan.v1`, …). The brain proposes; it never approves."""

    def call(self, schema: str, prompt: str, *, context: Optional[Mapping] = None) -> dict: ...


@runtime_checkable
class Verifier(Protocol):
    def verify(self, subject: Ref) -> entities.Verification: ...


@runtime_checkable
class Review(Protocol):
    def review(self, mission: entities.Mission) -> entities.Review: ...


@runtime_checkable
class Node(Protocol):
    """Where executions run (execution-architecture §9): spawn, stop, pause and
    inspect are the node commands; V1 has one local, in-process node (P3.5)."""
    id: str

    def spawn(self, harness_id: str, spec): ...
    def stop(self, execution_id: str, *, grace_s: float) -> None: ...
    def pause(self, execution_id: str): ...
    def inspect(self, execution_id: str): ...


# ── stubs ───────────────────────────────────────────────────────────────────

class AllowAllPolicy:
    """Allows everything. `is_stub = True` is what keeps real adapters out
    (harnesses.registry); the P9 engine is the only thing that may say False."""
    is_stub = True

    def evaluate(self, action, ctx):
        return entities.PolicyDecision(
            id=ids.new_id('policy_decision'), action=action, decision='ALLOW',
            reason='stub policy (P1): allows everything until the P9 engine exists')


class FixedCandidateRouter:
    """Always selects the one candidate it was built with."""

    def __init__(self, selected):
        self.selected = selected

    def route(self, subject, now):
        return entities.RouteDecision(
            id=ids.new_id('route_decision'), subject=subject, selected=self.selected,
            explanation='stub router (P1): the only candidate is %s' % self.selected)


class ScriptedBrain:
    """Answers each schema from a script, in order; running out is an error,
    never an invented answer."""

    def __init__(self, script):
        self._script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def call(self, schema, prompt, *, context=None):
        self.calls.append((schema, prompt))
        queue = self._script.get(schema)
        if not queue:
            raise LookupError('scripted brain has no %s response left' % schema)
        return queue.pop(0)


class AutoPassVerifier:
    def verify(self, subject):
        return entities.Verification(id=ids.new_id('verification'), subject=subject,
                                     verifier='generic_human', independent=False,
                                     state='PASSED')


class AutoAcceptReview:
    def review(self, mission):
        return entities.Review(id=ids.new_id('review'), mission_id=mission.id,
                               reviewer='stub', independent=False, verdict='accept',
                               state='ACCEPTED')


# ── P3.5 walking-skeleton stubs ─────────────────────────────────────────────

class FixedPolicy:
    """One decision for every action, or per action class (`by_class`). A stub
    (`is_stub = True`): it keeps real adapters out exactly as AllowAllPolicy does."""
    is_stub = True

    def __init__(self, decision='ALLOW', by_class=None):
        self.decision, self.by_class = decision, dict(by_class or {})

    def evaluate(self, action, ctx):
        d = self.by_class.get(action.action_class, self.decision)
        return entities.PolicyDecision(
            id=ids.new_id('policy_decision'), action=action, decision=d,
            reason='stub policy (P3.5): %s for %s' % (d, action.action_class))


class FixedPlanBrain:
    """Answers `plan.v1` with the same plan every time (a fresh copy); any
    other schema is an error, never an invented answer."""

    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def call(self, schema, prompt, *, context=None):
        self.calls.append((schema, prompt))
        if schema != 'plan.v1':
            raise LookupError('the plan brain answers plan.v1 only, not %s' % schema)
        return copy.deepcopy(self.plan)


class ScriptedVerifier:
    """PASSED, unless the subject's id is in `failing` (a set the test edits)."""

    def __init__(self, failing=(), verifier='code'):
        self.failing, self.verifier = set(failing), verifier

    def verify(self, subject):
        return entities.Verification(
            id=ids.new_id('verification'), subject=subject, verifier=self.verifier,
            criterion=0 if subject.kind == 'mission' else None,
            state='FAILED' if subject.id in self.failing else 'PASSED')


REVIEW_END = {'accept': 'ACCEPTED', 'changes_requested': 'CHANGES_REQUESTED',
              'reject': 'REJECTED'}


class ScriptedReview:
    """`accept`, unless `verdicts[mission_id]` says otherwise (the test edits it)."""

    def __init__(self, verdicts=None):
        self.verdicts = dict(verdicts or {})

    def review(self, mission):
        v = self.verdicts.get(mission.id, 'accept')
        return entities.Review(id=ids.new_id('review'), mission_id=mission.id,
                               reviewer='stub', verdict=v, state=REVIEW_END[v])
