"""Resources and routing (P10; resource-router, p10-design-gate §5-§9).

Commands that register accounts, set their resource policies and a mission's
resource preferences; the gatherer that builds the router's snapshot from the
database, the adapters and the usage feed; the command that records a
RouteDecision; and `ResourceRouter`, the Router port a task's dispatch uses.

What this module never does: authorise (a task reaches the router only with
a current `covered` P9 dispatch decision, checked again here), approve, change
a policy rule, or run anything. `ask` is recorded; asking the user is P9's
`authorization.request_route`, called by the dispatch command.
"""

import time
from datetime import datetime, timedelta, timezone

from ...infra.db import rows
from ..domain import actions, entities, ids, states
from ..domain.events import new_event
from ..domain.values import Ref
from ..routing import router as R
from . import authorization as A
from . import lifecycle
from .queries import view

#: A registered account's policy before the user sets one (resource-router §2).
REGISTER_DEFAULTS = {'allocation_pct': 80, 'reserve_pct': 10, 'brain_reserve_pct': 10,
                     'fallback': 'ask'}
POLICY_FIELDS = ('priority', 'allocation_pct', 'reserve_pct', 'brain_reserve_pct', 'fallback',
                 'budgets', 'project_allow', 'project_deny')
#: How long a fallback question waits for its answer (as a task approval does).
ROUTE_TTL = timedelta(hours=24)
_LIVE_EXEC = tuple(s for s in states.states('execution') if s not in states.terminal('execution'))


class NotAuthorised(PermissionError):
    """Routing refused: the task has no current `covered` P9 dispatch decision
    (policy before routing: the router never routes what P9 did not authorise)."""


def _user(actor, what):
    if actor.kind != 'user_device':
        raise A.NotPermitted('only a user device %s' % what)


def _epoch(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(
        timespec='milliseconds').replace('+00:00', 'Z')


# ── accounts and policies (resource-router §2) ─────────────────────────────

def register_account(tx, *, actor, harness_id, label, auth_kind, home_ref=None, auth=None):
    """A new account, UNVERIFIED, with the first-run policy (priority in
    registration order); `auth` is the adapter's probe, made before this
    command by the caller ({'ok', 'detail'}, or None when no adapter can
    probe it: it stays UNVERIFIED and is not routed to)."""
    _user(actor, 'registers an account')
    a = entities.Account(id=ids.new_id('account'), harness_id=harness_id, label=label,
                         auth_kind=auth_kind, home_ref=home_ref)
    tx.insert(a, actor=actor)
    tx.append(new_event('account.registered', Ref('account', a.id), actor,
                        payload={'harness_id': harness_id, 'label': label,
                                 'auth_kind': auth_kind}))
    p = entities.ResourcePolicy(id=ids.new_id('resource_policy'), account_id=a.id,
                                priority=len(tx.where(entities.ResourcePolicy)) + 1,
                                **REGISTER_DEFAULTS)
    tx.insert(p, actor=actor)
    if auth is not None:
        lifecycle.fire(tx, entities.Account, a.id, 'auth_ok' if auth['ok'] else 'auth_failed',
                       actor=actor, reason=auth.get('detail') or 'the adapter probed the login')
    return account_view(tx.conn, tx.get(entities.Account, a.id))


def set_account_enabled(tx, *, actor, account_id, enabled, auth=None):
    """The user disables an account (never routed to) or enables it again
    (UNVERIFIED, then the probe's answer)."""
    _user(actor, 'enables or disables an account')
    lifecycle.fire(tx, entities.Account, account_id, 'user_enables' if enabled
                   else 'user_disables', actor=actor,
                   reason='enabled on request' if enabled else 'disabled on request')
    if enabled and auth is not None:
        lifecycle.fire(tx, entities.Account, account_id,
                       'auth_ok' if auth['ok'] else 'auth_failed', actor=actor,
                       reason=auth.get('detail') or 'the adapter probed the login')
    return account_view(tx.conn, lifecycle.load(tx, entities.Account, account_id))


def set_resource_policy(tx, *, actor, account_id, expected_version=None, **fields):
    """Change an account's priority, allocation, reserves, fallback, budgets or
    project restrictions. A ceiling, never a quota Archeus must spend."""
    _user(actor, 'changes a resource policy')
    lifecycle.load(tx, entities.Account, account_id)
    (row,) = tx.where(entities.ResourcePolicy, account_id=account_id)
    got = {k: v for k, v in fields.items() if k in POLICY_FIELDS and v is not None}
    if set(fields) - set(POLICY_FIELDS):
        raise ValueError('a resource policy has only %s' % (POLICY_FIELDS,))
    entities.ResourcePolicy(**dict(row.entity.to_dict(), **got))            # validate
    out = tx.update(entities.ResourcePolicy, row.entity.id, got, actor=actor,
                    expected_version=expected_version)
    tx.append(new_event('resource_policy.updated', Ref('resource_policy', row.entity.id), actor,
                        payload={'account_id': account_id, 'fields': dict(got)}))
    return view(out)


def set_mission_resources(tx, *, actor, mission_id, preferences):
    """The mission's own resource choices (resource-router §10 D): preferred
    and forbidden accounts and harnesses, and the plan gate's auto-approve
    ceiling. Only a user device sets them: `max_cost_band` loosens what may be
    approved without asking. Setting them clears the mission's affinity."""
    _user(actor, "sets a mission's resources")
    m = lifecycle.load(tx, entities.Mission, mission_id).entity
    prefs = dict(preferences, since=tx.now)
    entities.Mission(**dict(m.to_dict(), resource_preferences=prefs))       # validate
    out = tx.update(entities.Mission, mission_id, {'resource_preferences': prefs}, actor=actor)
    tx.append(new_event('mission.updated', Ref('mission', mission_id), actor,
                        payload={'resource_preferences': prefs},
                        workspace=m.workspace_id, project=m.project_id))
    return view(out)


# ── usage (resource-router §4) ─────────────────────────────────────────────

def latest_usage(conn, account_id):
    """The newest stored snapshot of each window, as a feed reading, or None."""
    newest = {}
    for r in rows.where(conn, entities.UsageSnapshot, account_id=account_id):
        newest[r.entity.window] = r.entity                  # oldest first: last wins
    if not newest:
        return None
    return {'windows': {w: s.utilisation_pct for w, s in newest.items()},
            'resets_at': {w: s.resets_at for w, s in newest.items() if s.resets_at},
            'observed_at': max(_epoch(s.observed_at) for s in newest.values()),
            'source': sorted({s.source for s in newest.values()})[0]}


def observe(tx, *, actor, readings):
    """Record what the feed said about registered accounts, when it differs
    from the newest stored snapshot of that window (observed truth)."""
    for account_id, rd in sorted((readings or {}).items()):
        if not rd:
            continue
        have = latest_usage(tx.conn, account_id) or {'windows': {}}
        at = _iso(rd['observed_at'])
        # the same value, observed again within the staleness window, is not news
        fresh = have.get('observed_at') is not None and (
            rd['observed_at'] - have['observed_at'] <= R.STALE_S)
        for w, pct in sorted(rd['windows'].items()):
            if have['windows'].get(w) == pct and fresh:
                continue
            s = entities.UsageSnapshot(id=ids.new_id('usage_snapshot'), account_id=account_id,
                                       window=w, utilisation_pct=pct, source=rd['source'],
                                       observed_at=at, resets_at=rd['resets_at'].get(w))
            tx.insert(s, actor=actor)
            tx.append(new_event('usage.observed', Ref('account', account_id), actor,
                                payload={'window': w, 'pct': pct, 'source': rd['source']},
                                visibility='system'))


def ledger_totals(conn, account_id, today):
    """What Archeus consumed on *account_id* since *today* (an ISO date), and
    how many of its executions are live (the budget path, §4)."""
    tokens = cost = 0
    for r in rows.where(conn, entities.UsageLedger, account_id=account_id):
        if r.created_at >= today:
            tokens += r.entity.tokens_in + r.entity.tokens_out
            cost += r.entity.cost_usd or 0
    running = sum(1 for r in rows.where(conn, entities.Execution)
                  if r.entity.account_id == account_id and r.entity.state in _LIVE_EXEC)
    return {'tokens_today': tokens, 'cost_today': round(cost, 6), 'running': running}


# ── the snapshot (resource-router §5: everything a decision is made from) ──

def _models(caps):
    out = []
    for m in caps.models:
        if isinstance(m, str):
            out.append({'id': m, 'tier': None, 'context_window': None})
        else:
            out.append({'id': m.id, 'tier': m.tier, 'context_window': m.context_window})
    return out


def harness_view(adapter, exempt):
    info = adapter.discover()
    caps = adapter.capabilities(None) if info.installed else None
    return {'id': adapter.id, 'installed': bool(info.installed),
            'capabilities': sorted(caps.capabilities) if caps else [],
            'enforcement': caps.enforcement if caps else None,
            'structured_output': caps.structured_output if caps else None,
            'efforts': list(caps.efforts) if caps else [],
            'models': _models(caps) if caps else [], 'exempt': bool(exempt)}


def _terms(conn):
    """Every ADR-0021 answer, through P6's one reader (`calls.terms`)."""
    from .calls import terms
    return {h: {'headless': t.headless, 'rotation': t.rotation}
            for h, t in sorted(terms(conn).items())}


def _registered(conn, harness_ids, feed, now):
    """The registered accounts of *harness_ids*, with policy, usage and ledger.
    Returns (entries, readings): the feed's readings are recorded by the
    decision's command (`observe`)."""
    policies = {r.entity.account_id: r.entity for r in rows.where(conn, entities.ResourcePolicy)}
    today = _iso(now)[:10]
    out, readings = [], {}
    for r in rows.where(conn, entities.Account):
        a = r.entity
        if a.harness_id not in harness_ids:
            continue
        fed = feed.read({'id': a.id, 'harness_id': a.harness_id, 'home_ref': a.home_ref})
        if fed:
            readings[a.id] = fed
        rd = fed or latest_usage(conn, a.id)
        usage = None if not rd else {
            'windows': dict(rd['windows']), 'resets_at': dict(rd.get('resets_at') or {}),
            'observed_at': _iso(rd['observed_at']),
            'age_s': max(0, round(now - rd['observed_at'], 3)), 'source': rd['source']}
        p = policies[a.id]
        out.append({'id': a.id, 'ref': a.home_ref or a.id, 'home_ref': a.home_ref,
                    'harness': a.harness_id, 'label': a.label, 'auth_kind': a.auth_kind,
                    'registered': True, 'health': a.health, 'why_not': None,
                    'policy': {k: getattr(p, k) for k in POLICY_FIELDS} | {
                        'budgets': dict(p.budgets or {}),
                        'project_allow': list(p.project_allow),
                        'project_deny': list(p.project_deny)},
                    'usage': usage, 'ledger': ledger_totals(conn, a.id, today)})
    return out, readings


def call_snapshot(conn, *, callers, feed, preference, purpose, schema, project_id, min_tier,
                  now=None):
    """(requirements, snapshot, readings) for one of Archeus's own calls
    (ADR-0022): every own-call adapter; a harness with no registered account
    offers its own, as its adapter names it (P6), with the adapter's reason
    when it cannot be spent."""
    from ...harnesses.fake import is_fake_caller
    now = time.time() if now is None else now
    terms = _terms(conn)
    hs = [harness_view(a, is_fake_caller(a)) for a in sorted(callers, key=lambda a: a.id)]
    accounts, readings = _registered(conn, {h['id'] for h in hs}, feed, now)
    have = {a['harness'] for a in accounts}
    for a, h in zip(sorted(callers, key=lambda a: a.id), hs):
        if h['installed'] and 'headless' in h['capabilities'] and a.id not in have:
            try:
                ref, why = a.account(rotation=(terms.get(a.id) or {}).get('rotation')
                                     == 'permitted')
            except Exception as e:          # an adapter bug is an unusable account
                ref, why = None, '%s: %s' % (type(e).__name__, e)
            accounts.append({'id': None, 'ref': ref and ref.account_id,
                             'home_ref': ref and ref.home_ref, 'harness': a.id,
                             'label': a.id, 'auth_kind': None, 'registered': False,
                             'health': None, 'why_not': why or None, 'policy': None,
                             'usage': None, 'ledger': None})
    models = {h['id']: preference.model_for(h['id']) for h in hs
              if preference.model_for(h['id'])}
    req = {'subject': 'archeus_call', 'purpose': purpose, 'project_id': project_id,
           'capabilities': ['headless'], 'structured_output': schema is not None,
           'min_model_tier': min_tier, 'min_context_window': None, 'models': models,
           'model_required': False, 'effort': None, 'effort_required': False,
           'preferred': {'harnesses': [preference.harness] if preference.harness else [],
                         'accounts': []},
           'forbidden': {}, 'required': {}, 'size': None, 'policy': None}
    snap = {'now': _iso(now), 'harnesses': hs, 'accounts': accounts, 'terms': terms,
            'affinity': None, 'approved_fallbacks': []}
    return req, snap, readings


def current_authorization(conn, task, plan, policy_decision_id):
    """The P9 dispatch decision that authorises *task* now, or NotAuthorised:
    it must exist, be a `covered` dispatch decision of this exact task, plan
    version and digest, carry no DENY, and be the task's latest dispatch
    decision (a later one supersedes it). Routing never creates or widens it."""
    row = policy_decision_id and rows.get(conn, entities.PolicyDecision, policy_decision_id)
    if not row:
        raise NotAuthorised('task %s has no authorisation to route' % task.key)
    d = row.entity
    if (d.stage, d.outcome, d.task_id) != ('dispatch', 'covered', task.id):
        raise NotAuthorised('decision %s does not authorise task %s to dispatch (%s %s)'
                            % (d.id, task.key, d.stage, d.outcome))
    if (d.plan_id, d.plan_digest) != (plan.id, plan.digest):
        raise NotAuthorised('decision %s is for another plan version' % d.id)
    if d.decision == 'DENY' or any(i.get('decision') == 'DENY' for i in d.items):
        raise NotAuthorised('decision %s denies an item of task %s' % (d.id, task.key))
    latest = [r.entity for r in rows.where(conn, entities.PolicyDecision, task_id=task.id)
              if r.entity.stage == 'dispatch']
    if latest[-1].id != d.id:
        raise NotAuthorised('decision %s was superseded by %s' % (d.id, latest[-1].id))
    return d


def _affinity(conn, mission):
    """Where the mission's work last ran (§5 step 1), unless the user set its
    resources since (that clears affinity)."""
    since = (mission.resource_preferences or {}).get('since') or ''
    got = [r for r in rows.where(conn, entities.RouteDecision, mission_id=mission.id)
           if r.entity.subject.kind == 'task' and r.entity.result in ('selected', 'fallback')
           and r.created_at > since]
    if not got:
        return None
    rd = got[-1].entity
    return {'harness': rd.harness_id, 'account': rd.account_id or rd.account_ref}


def _approved_fallbacks(conn, task, plan):
    return sorted({a.entity.items[0]['resource']['account']
                   for a in rows.where(conn, entities.Approval, task_id=task.id)
                   if a.entity.kind == 'route' and a.entity.state == 'APPROVED'
                   and a.entity.plan_id == plan.id})


def task_snapshot(conn, *, adapters, feed, mission, plan, task, decision, now):
    """(requirements, snapshot, readings) for an authorised task: the execution
    adapters (the registry's), whose own account is the harness's default."""
    from ...harnesses.registry import _is_fake
    rp = mission.resource_preferences or {}
    hs = [harness_view(a, _is_fake(a)) for a in sorted(adapters, key=lambda a: a.id)]
    accounts, readings = _registered(conn, {h['id'] for h in hs}, feed, now)
    have = {a['harness'] for a in accounts}
    for h in hs:
        if h['installed'] and h['id'] not in have:
            accounts.append({'id': None, 'ref': '%s:default' % h['id'], 'home_ref': None,
                             'harness': h['id'], 'label': h['id'], 'auth_kind': None,
                             'registered': False, 'health': None, 'why_not': None,
                             'policy': None, 'usage': None, 'ledger': None})
    req = {'subject': 'task', 'purpose': None, 'mission_id': mission.id, 'task_id': task.id,
           'project_id': mission.project_id,
           'capabilities': sorted(task.capabilities_required), 'structured_output': False,
           'min_model_tier': task.min_model_tier, 'min_context_window': None, 'models': {},
           'model_required': False, 'effort': None, 'effort_required': False,
           'preferred': {'accounts': list(rp.get('preferred_accounts') or ()),
                         'harnesses': list(rp.get('preferred_harnesses') or ())},
           'forbidden': {'accounts': list(rp.get('forbidden_accounts') or ()),
                         'harnesses': list(rp.get('forbidden_harnesses') or ())},
           'required': {}, 'size': R.size_of(task.estimate),
           'policy': {'decision_id': decision.id, 'outcome': decision.outcome,
                      'items': [{'class': i['class'], 'decision': i['decision'],
                                 'boundary': i.get('boundary')} for i in decision.items]}}
    snap = {'now': _iso(now), 'harnesses': hs, 'accounts': accounts, 'terms': _terms(conn),
            'affinity': _affinity(conn, mission),
            'approved_fallbacks': _approved_fallbacks(conn, task, plan)}
    return req, snap, readings


# ── the decision (resource-router §8, §9) ──────────────────────────────────

def record_route(tx, *, actor, subject, requirements, snapshot, decision, readings=None,
                 source=None, purpose=None, workspace_id=None, project_id=None,
                 context_package_id=None):
    """Insert the immutable RouteDecision and `route.decided`, and record the
    usage readings it was decided on. Returns the Row."""
    observe(tx, actor=actor, readings=readings)
    d = decision
    rd = entities.RouteDecision(
        id=ids.new_id('route_decision'), subject=subject, selected=d['selected'],
        explanation=R.explain(d, requirements), purpose=purpose, decided_by='router',
        workspace_id=workspace_id, project_id=project_id, source=source,
        requirements=requirements, candidates=tuple(d['candidates']),
        account_ref=d['account_ref'], model=d['model'], input_snapshot=snapshot,
        context_package_id=context_package_id, mission_id=requirements.get('mission_id'),
        task_id=requirements.get('task_id'), harness_id=d['harness_id'],
        account_id=d['account_id'], effort=d['effort'], result=d['result'],
        fallback_from=tuple(d['fallback_from']),
        policy_decision_id=(requirements.get('policy') or {}).get('decision_id'),
        unblock_at=d['unblock_at'])
    row = tx.insert(rd, actor=actor)
    tx.append(new_event('route.decided', Ref('route_decision', rd.id), actor, payload={
        'purpose': purpose, 'selected': rd.selected, 'model': rd.model, 'result': rd.result,
        'harness_id': rd.harness_id, 'account_id': rd.account_id, 'task_id': rd.task_id,
        'mission_id': rd.mission_id,
        'source': None if source is None else {'kind': source.kind, 'id': source.id}},
        workspace=workspace_id or ids.GLOBAL_WORKSPACE, project=project_id))
    return row


def record_call_route(tx, *, actor, purpose, source, workspace_id, project_id, requirements,
                      snapshot, decision, readings=None, context_package_id=None):
    """An own call's decision, committed before anything runs (P6's INTENT rule)."""
    row = record_route(tx, actor=actor, subject=Ref('archeus_call', purpose),
                       requirements=requirements, snapshot=snapshot, decision=decision,
                       readings=readings, source=Ref(**source), purpose=purpose,
                       workspace_id=workspace_id, project_id=project_id,
                       context_package_id=context_package_id)
    return {'route_decision_id': row.entity.id}


def replay(route_decision):
    """Route a recorded decision again from its own record (§9)."""
    return R.replay({'requirements': route_decision.requirements,
                     'input_snapshot': route_decision.input_snapshot})


def terms_permit(conn, adapter):
    """ADR-0021's second check, immediately before an adapter runs: a fresh
    read. Scripted adapters (FakeCaller, FakeHarness by class) are exempt."""
    from ...harnesses.fake import is_fake_caller
    from ...harnesses.registry import _is_fake
    if is_fake_caller(adapter) or _is_fake(adapter):
        return True
    t = rows.get(conn, entities.ProviderTerms, adapter.id)
    return t is not None and t.entity.headless == 'permitted'


class ResourceRouter:
    """The Router port for tasks (ports.Router): `route(subject, now, tx=,
    actor=, authorization=, mission=, plan=, task=)` checks the authorisation
    is current, routes over the registry's execution adapters and records the
    decision in the dispatching transaction. Returns the RouteDecision."""

    def __init__(self, registry, feed):
        self.registry, self.feed = registry, feed

    def adapters(self):
        return [self.registry.get(i) for i in self.registry.ids()]

    def route(self, subject, now, *, tx, actor, authorization, mission, plan, task):
        decision = current_authorization(tx.conn, task, plan,
                                         (authorization or {}).get('policy_decision_id'))
        req, snap, readings = task_snapshot(tx.conn, adapters=self.adapters(), feed=self.feed,
                                            mission=mission, plan=plan, task=task,
                                            decision=decision, now=now)
        d = R.route(req, snap)
        return record_route(tx, actor=actor, subject=subject, requirements=req, snapshot=snap,
                            decision=d, readings=readings, source=Ref('mission', mission.id),
                            workspace_id=mission.workspace_id,
                            project_id=mission.project_id).entity


def request_route(tx, *, actor, mission, plan, task, route):
    """Ask for the user's consent to run *task* on the fallback account a
    RouteDecision answered `ask` for (resource-router §7): a PENDING `route`
    approval of exactly (this task of this plan version, that harness and
    account), the same thing asked twice finding the same row. It authorises
    no action — the task's next dispatch is judged by P9 again — and it is only
    ever decided by a user device, through P9's `decide`. The pure router never
    calls this: the dispatch command that recorded the `ask` does. It lives here,
    not in P9's module, because it names a resource and policy never does
    (p9-design-gate §14.1)."""
    key = route.account_id or route.account_ref
    items = [{'task': task.key, 'resource': {'harness': route.harness_id, 'account': key}}]
    h = actions.action_hash('route', A.bind(plan, task), items)
    got = A.live_approval(tx.conn, h)
    if got is not None:
        return got.entity, False
    a = entities.Approval(
        id=ids.new_id('approval'), kind='route', subject=Ref('task', task.id), action_hash=h,
        requested_by=actor.id, mission_id=mission.id, plan_id=plan.id,
        plan_version=plan.plan_version, plan_digest=plan.digest, task_id=task.id,
        presented={'what': [{'task': task.key, 'title': task.title,
                             'harness': route.harness_id, 'account': key}],
                   'why': [route.explanation],
                   'against': {'mission': {'id': mission.id, 'title': mission.title},
                               'task': {'id': task.id, 'key': task.key, 'title': task.title},
                               'route_decision': route.id},
                   'scope': 'this task of this plan version, on this account',
                   'consequences': {'approve': 'the task runs on %s' % key,
                                    'reject': 'the task stays blocked for you to resume or '
                                              'cancel'},
                   'reusable': 'task-lifetime'},
        items=tuple(items), expires_at=A._plus(tx.now, ROUTE_TTL),
        policy_decision_id=route.policy_decision_id)
    tx.insert(a, actor=actor)
    tx.append(new_event('approval.requested', Ref('approval', a.id), actor, payload={
        'kind': 'route', 'mission_id': mission.id, 'plan_id': plan.id, 'task_id': task.id,
        'action_hash': h, 'step_up': False, 'expires_at': a.expires_at},
        workspace=mission.workspace_id, project=mission.project_id))
    return a, True


class Resources:
    """What a transport needs beyond the database: the adapters. `probe` asks
    the harness's adapter whether a login works (cheap, no inference) BEFORE
    the registering command runs — a side effect never happens inside a
    transaction; `harnesses` lists every adapter Core knows and what it
    declares."""

    def __init__(self, *, registry, callers):
        self.registry, self.callers = registry, list(callers)

    def _adapters(self, harness_id):
        exe = [self.registry.get(i) for i in self.registry.ids() if i == harness_id]
        return exe + [c for c in self.callers if c.id == harness_id]

    def probe(self, harness_id, home_ref=None):
        """{'ok', 'detail'} from the first adapter of *harness_id* that can
        authenticate, or None: nothing can tell, so the account stays UNVERIFIED."""
        from ...harnesses import base
        for a in self._adapters(harness_id):
            if callable(getattr(a, 'authenticate', None)):
                try:
                    st = a.authenticate(base.AccountRef(harness_id, home_ref))
                except Exception as e:          # an adapter bug is a failed probe
                    return {'ok': False, 'detail': '%s: %s' % (type(e).__name__, e)}
                return {'ok': bool(st.ok), 'detail': st.detail or ''}
        return None

    def harnesses(self):
        from ...harnesses.fake import is_fake_caller
        from ...harnesses.registry import _is_fake
        out = {}
        for a in [self.registry.get(i) for i in self.registry.ids()]:
            out[a.id] = dict(harness_view(a, _is_fake(a)), execution=True, calls=False)
        for a in self.callers:
            v = out.get(a.id) or dict(harness_view(a, is_fake_caller(a)), execution=False)
            out[a.id] = dict(v, calls=True)
        return [out[k] for k in sorted(out)]


# ── views ──────────────────────────────────────────────────────────────────

def account_view(conn, row):
    (p,) = rows.where(conn, entities.ResourcePolicy, account_id=row.entity.id)
    return dict(view(row), resource_policy=view(p), usage=latest_usage(conn, row.entity.id))


def accounts(conn):
    return [account_view(conn, r) for r in rows.where(conn, entities.Account)]
