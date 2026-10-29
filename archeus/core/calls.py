"""`archeus_call`: one of Archeus's own tool-less structured calls (ADR-0022,
plan §31.4; p6-design-gate §5, p10-design-gate §8).

    caller states what it needs  (purpose, prompt, schema, source)
      -> the router              (P10: every own-call adapter and account,
                                  eliminated by capability, model, provider
                                  terms, health and allocation; ordered by
                                  preference, priority and tier fit)
      -> RouteDecision committed (before anything runs)
      -> provider-terms re-check (immediately before the spawn, ADR-0021)
      -> adapter.call()          (native or prompted structured output, on the
                                  account and model the decision chose)
      -> Core validation         (the schema, then the caller's own checks;
                                  retried once, ADR-0006)
      -> the caller records the result and ends the call in one command

Nothing here knows a harness by name. The pre-router election P6 shipped
(the user's choice, else Claude Code, else the first) is gone: the router
replaced it (plan §31.1 P10), and it has no rule naming a harness.
"""

import os
from collections import namedtuple

from ..harnesses.fake import is_fake_caller
from ..infra.paths import stop_sentinel
from .routing import router as R
from .routing.usage import NoUsageFeed
from .application import calls as C
from .application import resources
from .domain import shapes

#: What `run()` returns. `state` is 'ok' or an outcome state `run()` already
#: recorded; on 'ok' the caller records its result and calls `C.end_call`.
Called = namedtuple('Called', 'route_decision_id state parsed usage detail attempts account_ref')

DEFAULT_TIMEOUT_S = 600
#: Invalid structured output is retried once, then the call fails (ADR-0006:
#: "retry once, then ask"; the asking surface is P7/P16).
ATTEMPTS = 2
#: The model tier a purpose needs (plan §12: a plan error replicates into every
#: task, so the planner runs on a `large` model); a purpose not named has no
#: minimum. Enforced by the router's `model` step (P10).
CALL_TIERS = {'planner': 'large'}


def _terms_state(terms, harness_id):
    t = terms.get(harness_id)
    return 'unknown' if t is None else t.headless


class OwnCalls:
    """Runs own calls for one Core: `callers` are the own-call adapters (fake
    in tests, `harnesses.calls.real_callers()` in production), `preference` the
    own-call preference port."""

    def __init__(self, db, *, actor, callers, preference, timeout_s=DEFAULT_TIMEOUT_S,
                 usage=None):
        self.db, self.actor, self.callers = db, actor, list(callers)
        self.preference, self.timeout_s = preference, timeout_s
        self.usage = usage or NoUsageFeed()

    def _do(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.actor))

    def _end(self, rd_id, state, *, usage=None, **detail):
        self._do(C.end_call, route_decision_id=rd_id, outcome=dict(detail, state=state),
                 usage=usage)

    def run(self, *, purpose, source, workspace_id, project_id, prompt, schema, check,
            workdir, context_package_id=None, forbidden=None, no_tools=False):
        """Route and make one call. `check(parsed)` is the caller's own
        validation beyond the schema: a list of problems, empty when it holds.
        `forbidden` ({harnesses, accounts}) keeps resources out of the election
        (P13: a review is routed away from the accounts that did the work).
        `no_tools` is CallSpec's. A callable `workdir` is made from the route
        decision id only once the call is about to run (K-O2: a fresh directory
        per call, none for a call that never runs); if it raises, the call ends
        `failed` with nothing spawned."""
        with self.db.read() as conn:
            req, snap, readings = resources.call_snapshot(
                conn, callers=self.callers, feed=self.usage, preference=self.preference.get(),
                purpose=purpose, schema=schema, project_id=project_id,
                min_tier=CALL_TIERS.get(purpose), forbidden=forbidden,
                max_run_s=ATTEMPTS * self.timeout_s, no_tools=no_tools)
        # decided inside the transaction that records it, over fresh ledgers:
        # two calls cannot both take an account's last slot (ADR-0048 D-25.4)
        got = self._do(resources.record_call_route, purpose=purpose, source=dict(source),
                       workspace_id=workspace_id, project_id=project_id, requirements=req,
                       snapshot=snap, readings=readings,
                       context_package_id=context_package_id)
        rd, d, snap = got['route_decision_id'], got['decision'], got['snapshot']
        if d['result'] not in ('selected', 'fallback'):
            gated = d['result'] == 'blocked' and any(
                c['eliminated_at_step'] == 'provider_terms' for c in d['candidates'])
            state = 'gated' if gated else 'unavailable'
            # the reason of the candidate that got furthest: the most specific why-not
            far = max(d['candidates'], default=None,
                      key=lambda c: R.STEPS.index(c['eliminated_at_step']))
            # (AP-1: a protection or a full budget is named, so "why is my planner
            # waiting" is answered from the record)
            why = (far['reason'] if far is not None and far['eliminated_at_step'] in (
                'restriction', 'health', 'allocation', 'partition') else 'no eligible harness')
            if d['result'] == 'ask':
                why = '%s; only your approval could use it, which an own call never asks' % why
            self._end(rd, state, reason=why)
            return Called(rd, state, None, None, why, 0, None)
        adapter = next(a for a in self.callers if a.id == d['harness_id'])
        if os.path.exists(stop_sentinel()):             # disarmed (P11 §13): nothing runs
            self._end(rd, 'unavailable', reason='emergency stop')
            return Called(rd, 'unavailable', None, None, 'emergency stop', 0, None)
        if not is_fake_caller(adapter):
            with self.db.read() as conn:                # immediately before the spawn
                now = _terms_state(C.terms(conn), adapter.id)
            if now != 'permitted':
                self._end(rd, 'gated', reason='provider terms %s' % now)
                return Called(rd, 'gated', None, None, 'provider terms %s' % now, 0, None)
        acct = next(a for a in snap['accounts'] if a['harness'] == d['harness_id']
                    and (a['id'] or a['ref']) == (d['account_id'] or d['account_ref']))
        model = d['model']
        from ..harnesses import base
        account = base.AccountRef(d['account_id'] or d['account_ref'], acct.get('home_ref'))
        if callable(workdir):
            try:
                workdir = workdir(rd)
            except OSError as e:
                why = 'no working directory for the call: %s' % e
                self._end(rd, 'failed', reason=why)
                return Called(rd, 'failed', None, None, why, 0, None)
        spec = base.CallSpec(route_decision_id=rd, purpose=purpose, prompt=prompt,
                             workdir=workdir, account=account, schema=schema, model=model,
                             limits={'timeout_s': self.timeout_s}, no_tools=no_tools)
        usage, problems = {}, []
        for attempt in range(1, ATTEMPTS + 1):
            try:
                res = adapter.call(spec)
            except Exception as e:          # an adapter bug is a failed call, never a crash
                res = base.CallResult(error='failed', detail='%s: %s' % (type(e).__name__, e))
            usage = _add(usage, res.usage or {}, first=attempt == 1)
            if res.error is not None:
                # no binary: nothing ran, so there is nothing to ledger
                self._end(rd, res.error, usage=None if res.error == 'unavailable' else usage,
                          reason=res.detail,
                          attempts=attempt, account_ref=account.account_id)
                return Called(rd, res.error, None, usage, res.detail, attempt, account.account_id)
            problems = _problems(res.parsed, schema, check)
            if not problems:
                return Called(rd, 'ok', res.parsed, usage, '', attempt, account.account_id)
        self._end(rd, 'invalid', usage=usage, reason='; '.join(problems[:5]),
                  attempts=ATTEMPTS, account_ref=account.account_id)
        return Called(rd, 'invalid', None, usage, '; '.join(problems[:5]), ATTEMPTS,
                      account.account_id)


def _add(have, got, *, first):
    """The attempts' figures summed. A figure one attempt reported and another
    did not is no longer a total, so it is dropped: unknown, never a part read
    as the whole (ADR-0048 §3)."""
    nums = {k: v for k, v in got.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}
    if first:
        return nums
    return {k: have[k] + nums[k] for k in set(have) & set(nums)}


def _problems(parsed, schema, check):
    if parsed is None:
        return ['the answer carried no JSON']
    if schema is not None:
        try:
            shapes.validate(parsed, schema)
        except shapes.Invalid as e:
            return [str(e)]
    return list(check(parsed) or ())
