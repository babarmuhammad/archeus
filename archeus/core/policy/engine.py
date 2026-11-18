"""The policy engine (plan §13, ADR-0007; p9-design-gate §4.2). Pure and
deterministic: `evaluate_item(action, ctx)` reads nothing but its arguments,
so the same inputs give the same answer, and a recorded decision replays from
its own snapshot.

    0. e-stop armed                                   -> DENY
    1. applicable = rules on the scope chain, this class, matching, unexpired
       (+ the implicit TASK contract rule outside the plan stage)
    2. none                                           -> DENY policy_missing
    3. specific = the deepest applicable (explicit before profile at a level)
    4. effective = strictest(specific) + every LOCKED broader applicable rule
    5. decision = strictest(effective)
    6. ALLOW_WITHIN_BOUNDARY: inside every AWB boundary in effective, else
       the strictest `outside` (ASK | DENY)
    7. step_up = ASK on deploy / destructive

Whether an approval covers an ASK (the ACTION level) is the application's,
which holds the approvals (application/authorization.py). `ctx`:

    stage      plan | dispatch | action                      (default plan)
    chain      {USER, WORKSPACE, PROJECT, MISSION, TASK: ref}
    profiles   {USER: name, MISSION: name or None}           (default standard)
    rules      the user's active rule dicts (rules.from_entity)
    now        ISO time, for rule expiry
    estop      the STOP sentinel exists
    task_classes   the task's declared + implied classes (dispatch, action)
    unclassified   the action could not be classified (action stage, P11)
    candidates     replay: exactly these rules instead of the ones above
"""

from ..domain import entities, ids
from . import rules as R


def _depth(r):
    return 2 * R.LEVELS.index(r['scope_level']) + (1 if r['source'] == 'user' else 0)


def _order(r):
    """Precedence: deepest first, then strictest, then id (stable)."""
    return (-_depth(r), -R.STRICTNESS[r['decision']], r['id'])


def _on_chain(r, chain):
    level = r['scope_level']
    if level == 'GLOBAL' or r['source'] == 'profile':
        return True
    return r['scope_ref'] is not None and chain.get(level) == r['scope_ref']


def candidate_rules(ctx):
    """Every rule the context can see: built-in, expanded profiles, user rules.
    `ctx['candidates']` replaces all of them: a recorded decision's own
    `matched` snapshot, replayed (§9)."""
    if ctx.get('candidates') is not None:
        return [dict(r) for r in ctx['candidates']]
    profiles = dict({'USER': 'standard'}, **(ctx.get('profiles') or {}))
    chain = ctx.get('chain') or {}
    out = R.builtin()
    for level in ('USER', 'MISSION'):
        if profiles.get(level):
            out += R.profile_rules(profiles[level], level, chain.get(level))
    return out + [dict(r) for r in ctx.get('rules') or ()]


def _one(action, cls, ctx):
    stage = ctx.get('stage', 'plan')
    chain, now = ctx.get('chain') or {}, ctx.get('now')
    applicable = [
        r for r in candidate_rules(ctx)
        if r['action_class'] == cls and _on_chain(r, chain) and R.matches(r, action)
        and not (r.get('expires_at') and now and r['expires_at'] <= now)]
    task_classes = ctx.get('task_classes')
    if stage != 'plan' and task_classes is not None and cls not in task_classes:
        applicable.append(dict(R.TASK_CONTRACT, action_class=cls))
    if not applicable:
        miss = dict(R.MISSING, action_class=cls)
        return _result('DENY', cls, action, [miss], [miss], miss, [], None,
                       'no policy covers %s: denied (fail closed)' % cls)
    applicable.sort(key=_order)
    top_depth = _depth(applicable[0])
    specific = [r for r in applicable if _depth(r) == top_depth]
    conflicts = ([r['id'] for r in specific]
                 if len({r['decision'] for r in specific}) > 1 else [])
    effective = [specific[0]] + [r for r in applicable
                                 if r['locked'] and _depth(r) < top_depth]
    effective.sort(key=lambda r: (-R.STRICTNESS[r['decision']],) + _order(r))
    deciding = effective[0]
    decision, checks, boundary = deciding['decision'], None, None
    if decision == R.AWB:
        bounded = [r for r in effective if r['decision'] == R.AWB]
        checks = {'checked': [], 'deferred': [], 'outside': []}
        for r in bounded:
            c = R.check_boundary(r['boundary'], action, stage)
            for k in checks:
                checks[k] += [x for x in c[k] if x not in checks[k]]
        boundary = bounded[0]['boundary'] if len(bounded) == 1 else [r['boundary']
                                                                    for r in bounded]
        if checks['outside']:
            worst = max(bounded, key=lambda r: R.STRICTNESS[r['outside']])
            decision, deciding = worst['outside'], worst
    why = '%s %s: %s' % (decision, cls, '; '.join(
        '%s (%s, %s%s)' % (r['id'], r['decision'], r['scope_level'],
                           ', locked' if r['locked'] else '') for r in effective))
    if checks and checks['outside']:
        why += '; outside its boundary on %s' % ', '.join(checks['outside'])
    return _result(decision, cls, action, applicable, effective, deciding, conflicts,
                   (boundary, checks), why)


def _result(decision, cls, action, matched, effective, deciding, conflicts, bounded, why):
    boundary, checks = bounded if bounded else (None, None)
    return {'decision': decision, 'class': cls, 'action': action.canonical_dict(),
            'matched': matched, 'effective': [r['id'] for r in effective],
            'deciding_rule': deciding['id'], 'conflicts': conflicts,
            'boundary': boundary, 'checks': checks,
            'step_up': decision == 'ASK' and cls in R.STEP_UP_CLASSES, 'reason': why}


def evaluate_item(action, ctx):
    """The engine's answer for one canonical action in one context (a dict,
    everything that led to it included)."""
    if ctx.get('estop'):
        stop = dict(R.ESTOP, action_class=action.action_class)
        return _result('DENY', action.action_class, action, [stop], [stop], stop, [], None,
                       'emergency stop armed: every action is denied')
    if ctx.get('unclassified'):
        # the strictest of every class the task holds, and exec (§6.3)
        classes = sorted(set(ctx.get('task_classes') or ()) | {'exec'})
        results = [_one(action, c, ctx) for c in classes]
        worst = max(results, key=lambda r: (R.STRICTNESS[r['decision']], r['class']))
        return dict(worst, reason='unclassified action, judged as its strictest class: '
                    + worst['reason'])
    return _one(action, action.action_class, ctx)


class PolicyEngine:
    """The real Policy port (P9). `is_stub = False`: the one object that may
    say so (plan §31.1 P1) — the adapter registry reads it."""
    is_stub = False

    def evaluate(self, action, ctx):
        r = evaluate_item(action, ctx)
        return entities.PolicyDecision(
            id=ids.new_id('policy_decision'), decision=r['decision'], action=action,
            reason=r['reason'], stage=ctx.get('stage', 'plan'), items=(r,),
            policy_version=ctx.get('policy_version'), engine_version=str(R.ENGINE_VERSION),
            estop=bool(ctx.get('estop')))
