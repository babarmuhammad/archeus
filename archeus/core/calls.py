"""`archeus_call`: one of Archeus's own tool-less structured calls (ADR-0022,
plan §31.4; p6-design-gate §5).

    caller states what it needs  (purpose, prompt, schema, source)
      -> pre-router election     (installed, `headless`, provider terms; then
                                  the user's choice, else Claude Code, else the
                                  first installed `headless` harness)
      -> RouteDecision committed (before anything runs)
      -> provider-terms re-check (immediately before the spawn, ADR-0021)
      -> the harness's account   (its own rule: rotate/quota for Claude Code)
      -> adapter.call()          (native or prompted structured output)
      -> Core validation         (the schema, then the caller's own checks;
                                  retried once, ADR-0006)
      -> the caller records the result and ends the call in one command

Nothing here knows a harness by name except the election's documented
Claude Code rule. No P10 router: the election is the pre-router one, and its
RouteDecision says so (`decided_by: pre_router`).
"""

import dataclasses
from collections import namedtuple

from ..harnesses.fake import is_fake_caller
from .application import calls as C
from .domain import shapes

#: What `run()` returns. `state` is 'ok' or an outcome state `run()` already
#: recorded; on 'ok' the caller records its result and calls `C.end_call`.
Called = namedtuple('Called', 'route_decision_id state parsed usage detail attempts account_ref')

DEFAULT_TIMEOUT_S = 600
#: Invalid structured output is retried once, then the call fails (ADR-0006:
#: "retry once, then ask"; the asking surface is P7/P16).
ATTEMPTS = 2


def _terms_state(terms, harness_id):
    t = terms.get(harness_id)
    return 'unknown' if t is None else t.headless


def elect(callers, terms, preference):
    """(selected adapter or None, candidates, why, gated): pure, deterministic
    in the adapters' ids. `gated` is True when nothing was selected and at
    least one otherwise-eligible harness was stopped by the provider terms."""
    cands, eligible = [], []
    for a in sorted(callers, key=lambda a: a.id):
        info, caps = a.discover(), a.capabilities(None)
        if not info.installed:
            step, why = 'installed', 'not installed'
        elif 'headless' not in caps.capabilities:
            step, why = 'headless', 'does not declare headless (it cannot make a tool-less call)'
        elif not is_fake_caller(a) and _terms_state(terms, a.id) != 'permitted':
            step, why = 'provider_terms', 'provider terms %s (ADR-0021): no real call until ' \
                'you permit automated headless use' % _terms_state(terms, a.id)
        else:
            step, why = None, None
            eligible.append(a)
        cands.append({'resource': a.id, 'eliminated_at_step': step, 'reason': why,
                      'structured_output': caps.structured_output})
    ids_ = [a.id for a in eligible]
    if preference.harness in ids_:
        pick, why = preference.harness, 'your choice for Archeus\'s own calls'
    elif 'claude_code' in ids_:
        pick, why = 'claude_code', 'Claude Code is installed (no usable choice of yours)'
    elif ids_:
        pick, why = ids_[0], 'the first installed harness that can make the call'
    else:
        pick, why = None, None
    for c in cands:
        if c['eliminated_at_step'] is None and c['resource'] != pick:
            c['eliminated_at_step'], c['reason'] = 'election', 'not elected: %s was' % pick
    gated = pick is None and any(c['eliminated_at_step'] == 'provider_terms' for c in cands)
    return next((a for a in eligible if a.id == pick), None), cands, why, gated


def explain(selected, model, why, candidates):
    """The explanation, generated from the record (resource-router §8)."""
    others = ['%s: %s' % (c['resource'], c['reason']) for c in candidates
              if c['resource'] != selected]
    if selected is None:
        head = 'No harness could make this call.'
    else:
        head = 'Used %s (%s) because %s.' % (selected, model or 'its default model', why)
    return head + ('' if not others else ' Not used: ' + '; '.join(others) + '.')


class OwnCalls:
    """Runs own calls for one Core: `callers` are the own-call adapters (fake
    in tests, `harnesses.calls.real_callers()` in production), `preference` the
    own-call preference port."""

    def __init__(self, db, *, actor, callers, preference, timeout_s=DEFAULT_TIMEOUT_S):
        self.db, self.actor, self.callers = db, actor, list(callers)
        self.preference, self.timeout_s = preference, timeout_s

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
            terms = C.terms(conn)
        pref = self.preference.get()
        adapter, cands, why, gated = elect(self.callers, terms, pref)
        model = None if adapter is None else pref.model_for(adapter.id)
        rd = self._do(C.decide_route, purpose=purpose, source=dict(source),
                      workspace_id=workspace_id, project_id=project_id,
                      selected=None if adapter is None else adapter.id, account_ref=None,
                      model=model, candidates=cands,
                      requirements={'capabilities': ['headless'],
                                    'structured_output': schema is not None},
                      input_snapshot={'preference': dataclasses.asdict(pref),
                                      'terms': {k: v.headless for k, v in sorted(terms.items())}},
                      explanation=explain(None if adapter is None else adapter.id, model, why,
                                          cands),
                      context_package_id=context_package_id)['route_decision_id']
        if adapter is None:
            state = 'gated' if gated else 'unavailable'
            self._end(rd, state, reason='no eligible harness')
            return Called(rd, state, None, None, 'no eligible harness', 0, None)
        if not is_fake_caller(adapter):
            with self.db.read() as conn:                # immediately before the spawn
                now = _terms_state(C.terms(conn), adapter.id)
            if now != 'permitted':
                self._end(rd, 'gated', reason='provider terms %s' % now)
                return Called(rd, 'gated', None, None, 'provider terms %s' % now, 0, None)
        rotation = (terms.get(adapter.id) is not None
                    and terms[adapter.id].rotation == 'permitted')
        account, why_not = adapter.account(rotation=rotation)
        if why_not:
            self._end(rd, 'unavailable', reason=why_not, account_ref=account.account_id)
            return Called(rd, 'unavailable', None, None, why_not, 0, account.account_id)
        from ..harnesses import base
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
