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

from collections import namedtuple

from ..harnesses.fake import is_fake_caller
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
            workdir, context_package_id=None):
        """Route and make one call. `check(parsed)` is the caller's own
        validation beyond the schema: a list of problems, empty when it holds."""
        with self.db.read() as conn:
            req, snap, readings = resources.call_snapshot(
                conn, callers=self.callers, feed=self.usage, preference=self.preference.get(),
                purpose=purpose, schema=schema, project_id=project_id,
                min_tier=CALL_TIERS.get(purpose))
        d = R.route(req, snap)
        rd = self._do(resources.record_call_route, purpose=purpose, source=dict(source),
                      workspace_id=workspace_id, project_id=project_id, requirements=req,
                      snapshot=snap, decision=d, readings=readings,
                      context_package_id=context_package_id)['route_decision_id']
        if d['result'] not in ('selected', 'fallback'):
            gated = d['result'] == 'blocked' and any(
                c['eliminated_at_step'] == 'provider_terms' for c in d['candidates'])
            state = 'gated' if gated else 'unavailable'
            # the reason of the candidate that got furthest: the most specific why-not
            far = max(d['candidates'], default=None,
                      key=lambda c: R.STEPS.index(c['eliminated_at_step']))
            why = ('the only account left needs your approval, which an own call never asks'
                   if d['result'] == 'ask' else far['reason'] if far is not None
                   and far['eliminated_at_step'] in ('health', 'allocation')
                   else 'no eligible harness')
            self._end(rd, state, reason=why)
            return Called(rd, state, None, None, why, 0, None)
        adapter = next(a for a in self.callers if a.id == d['harness_id'])
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
        spec = base.CallSpec(route_decision_id=rd, purpose=purpose, prompt=prompt,
                             workdir=workdir, account=account, schema=schema, model=model,
                             limits={'timeout_s': self.timeout_s})
        usage, problems = {}, []
        for attempt in range(1, ATTEMPTS + 1):
            try:
                res = adapter.call(spec)
            except Exception as e:          # an adapter bug is a failed call, never a crash
                res = base.CallResult(error='failed', detail='%s: %s' % (type(e).__name__, e))
            for k, v in (res.usage or {}).items():
                usage[k] = usage.get(k, 0) + v if isinstance(v, (int, float)) else v
            if res.error is not None:
                self._end(rd, res.error, usage=usage or None, reason=res.detail,
                          attempts=attempt, account_ref=account.account_id)
                return Called(rd, res.error, None, usage, res.detail, attempt, account.account_id)
            problems = _problems(res.parsed, schema, check)
            if not problems:
                return Called(rd, 'ok', res.parsed, usage, '', attempt, account.account_id)
        self._end(rd, 'invalid', usage=usage or None, reason='; '.join(problems[:5]),
                  attempts=ATTEMPTS, account_ref=account.account_id)
        return Called(rd, 'invalid', None, usage, '; '.join(problems[:5]), ATTEMPTS,
                      account.account_id)


def _problems(parsed, schema, check):
    if parsed is None:
        return ['the answer carried no JSON']
    if schema is not None:
        try:
            shapes.validate(parsed, schema)
        except shapes.Invalid as e:
            return [str(e)]
    return list(check(parsed) or ())
