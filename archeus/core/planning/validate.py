"""Core's plan validator (p8-design-gate §7, §11): pure functions, no I/O, no model.

The model proposes; Core decides everything derived from a plan. This module
is where that happens, for a model's answer and for a stub plan alike:

- `problems()`   the structural contract: a task list that fails it is invalid
                 output (retried by `archeus_call`) and never becomes a row
- `order()`      a topological order; the key order `t1…tN` follows it
- `serialise()`  Core-added dependencies between parallel tasks whose `touches`
                 may overlap, each recorded with its reason (D8)
- `cost_band()`  the authoritative cost band (D9) — the model's estimate of a
                 band is never read
- `digest()`     the sha256 of a version's content, which the plan `ready`
                 guard re-checks
- `waves()`      the parallel groups, derived and never stored

A task here is a dict with `key` (a model label or a task key), `depends_on`,
`kind`, `action_classes`, `acceptance`, `touches` and the other contract fields.
"""

import fnmatch
import hashlib
import json

from ..domain import entities
from ..domain.actions import ACTION_CLASSES

MAX_TASKS = 50
#: D9, frozen in the P8 contract: `score = Σ tier weight × estimate`; the band
#: is the first whose ceiling the score does not exceed, else `high`.
TIER_WEIGHT = {'small': 1, 'mid': 2, 'large': 4}
DEFAULT_TIER = 'mid'        # a task that names no tier is costed as well-specified work
BAND_CEILINGS = (('low', 6), ('medium', 20))
BAND_ABOVE = 'high'


def find_cycle(tasks):
    """The keys of one dependency cycle, first repeated (['t2', 't4', 't2']),
    or None. Unknown dependencies are ignored here (`problems` reports them)."""
    deps = {t['key']: [d for d in t.get('depends_on', ()) if d != t['key']] for t in tasks}
    colour, stack = {}, []

    def visit(k):
        colour[k] = 1
        stack.append(k)
        for d in deps.get(k, ()):
            if d not in deps:
                continue
            if colour.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if colour.get(d) is None:
                found = visit(d)
                if found:
                    return found
        colour[k] = 2
        stack.pop()
        return None

    for t in tasks:
        if colour.get(t['key']) is None:
            found = visit(t['key'])
            if found:
                return found
    return None


def order(tasks):
    """The tasks in dependency order, stable in the given order: a task comes
    after everything it depends on, and otherwise keeps its position. The
    graph must be valid (`problems` empty)."""
    done, out, left = set(), [], list(tasks)
    while left:
        for t in left:
            if set(t.get('depends_on', ())) <= done:
                out.append(t)
                done.add(t['key'])
                left.remove(t)
                break
        else:
            raise ValueError('the dependency graph has a cycle')
    return out


def _prefix(glob):
    cut = [i for i, ch in enumerate(glob) if ch in '*?[']
    return glob[:cut[0]] if cut else glob


def overlap(a, b):
    """May two path globs name a common file? Conservative (ponytail: literal
    prefixes and fnmatch both ways; a false yes costs parallelism, never
    correctness — upgrade to a real glob intersection if that ever matters)."""
    a, b = a.replace('\\', '/'), b.replace('\\', '/')
    if a == b or fnmatch.fnmatchcase(a, b) or fnmatch.fnmatchcase(b, a):
        return True
    pa, pb = _prefix(a), _prefix(b)
    wild = (pa != a) or (pb != b)
    return wild and (pa.startswith(pb) or pb.startswith(pa))


def _reaches(deps, frm, to):
    """Does *frm* depend, directly or not, on *to*?"""
    seen, todo = set(), list(deps[frm])
    while todo:
        k = todo.pop()
        if k == to:
            return True
        if k not in seen:
            seen.add(k)
            todo += deps.get(k, [])
    return False


def serialise(tasks):
    """(tasks with Core-added dependencies, [{task, after, because}]) — D8.
    *tasks* are in dependency order; for every pair with no path between them
    whose `touches` may overlap, the later one is made to depend on the earlier
    one. The added edge always points backwards in the order, so the order and
    acyclicity hold; every added edge is returned with its reason, and the
    planner's own edges are exactly the ones not listed."""
    deps = {t['key']: list(t.get('depends_on', ())) for t in tasks}
    added = []
    for j, later in enumerate(tasks):
        for earlier in tasks[:j]:
            a, b = earlier['key'], later['key']
            if _reaches(deps, b, a) or _reaches(deps, a, b):
                continue
            clash = next(((x, y) for x in earlier.get('touches', ())
                          for y in later.get('touches', ()) if overlap(x, y)), None)
            if clash:
                deps[b].append(a)
                added.append({'task': b, 'after': a,
                              'because': 'touches overlap: %s ~ %s' % clash})
    return [dict(t, depends_on=tuple(deps[t['key']])) for t in tasks], added


def waves(tasks):
    """[[keys]]: each wave depends only on earlier waves (the parallel groups)."""
    level = {}
    for t in order(tasks):
        level[t['key']] = 1 + max((level[d] for d in t.get('depends_on', ())), default=-1)
    out = [[] for _ in range(1 + max(level.values(), default=-1))]
    for t in tasks:
        out[level[t['key']]].append(t['key'])
    return out


def cost_band(tasks):
    """The authoritative band (D9): Σ tier weight × estimate over the tasks."""
    score = sum(TIER_WEIGHT[t.get('min_model_tier') or DEFAULT_TIER] * int(t.get('estimate', 1))
                for t in tasks)
    return next((band for band, ceiling in BAND_CEILINGS if score <= ceiling), BAND_ABOVE)


def problems(tasks, *, criteria=(), explicit=(), asked=()):
    """Every way *tasks* break the structural contract (§11.1-§11.2), as
    sentences; empty when it holds. *criteria* are the mission-level success
    criteria the plan will run under, *explicit* the handles of the mission's
    explicit requirements, *asked* those a blocking question is about (D16)."""
    out = []
    if not tasks:
        return ['a plan has at least one task']
    if len(tasks) > MAX_TASKS:
        out.append('a plan has at most %d tasks' % MAX_TASKS)
    keys = [t.get('key') for t in tasks]
    if any(not (isinstance(k, str) and k.strip()) for k in keys):
        out.append('every task has a label')
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        out.append('task labels repeat: %s' % ', '.join(map(str, dup)))
    known = set(keys)
    for t in tasks:
        k = t.get('key')
        for d in t.get('depends_on', ()):
            if d == k:
                out.append('task %s depends on itself' % k)
            elif d not in known:
                out.append('task %s depends on %s, which is not in the plan' % (k, d))
        if t.get('kind') not in entities.TASK_KINDS:
            out.append('task %s has an unknown kind %r' % (k, t.get('kind')))
        bad = sorted(set(t.get('action_classes', ())) - set(ACTION_CLASSES))
        if bad:
            out.append('task %s has unknown action classes %s' % (k, bad))
        bad = sorted(set(t.get('capabilities_required', ())) - set(entities.CAPABILITIES))
        if bad:
            out.append('task %s has unknown capabilities %s' % (k, bad))
        tier = t.get('min_model_tier')
        if tier is not None and tier not in entities.MODEL_TIERS:
            out.append('task %s has an unknown model tier %r' % (k, tier))
        est = t.get('estimate', 1)
        if isinstance(est, bool) or not isinstance(est, int) or not 1 <= est <= 5:
            out.append('task %s has an estimate outside 1-5' % k)
        checks = [c.get('check') for c in t.get('acceptance', ())]
        if t.get('kind') == 'human':
            if any(c != 'human' for c in checks):
                out.append('task %s is a human task, so its acceptance is human' % k)
        elif not checks:
            out.append('task %s has no acceptance criterion' % k)
    if not dup and not any('depends on' in p for p in out):
        cycle = find_cycle(tasks)
        if cycle:
            out.append('the dependencies form a cycle: %s' % ' -> '.join(cycle))
    seen = {}
    for t in tasks:
        sig = ((t.get('title') or '').strip().lower(), (t.get('objective') or '').strip().lower())
        if sig in seen:
            out.append('tasks %s and %s are the same task' % (seen[sig], t.get('key')))
        seen.setdefault(sig, t.get('key'))
    served = {r for t in tasks for r in t.get('serves', ())}
    for r in explicit:
        if r not in served and r not in asked:
            out.append('explicit requirement %s is served by no task and asked about by no '
                       'question' % r)
    if (any(c.get('check') == 'automatic' for c in criteria)
            and all(t.get('kind') == 'human' for t in tasks)):
        out.append('an automatic success criterion needs at least one non-human task')
    return out


_PLAN_SKIP = ('id', 'state', 'digest')
_TASK_SKIP = ('id', 'state', 'failure_class', 'plan_id')


def digest(plan, tasks):
    """sha256 of a version's canonical content: the Plan entity's fields but its
    id, state and digest, and every task's contract (by key)."""
    body = {'plan': {k: v for k, v in plan.to_dict().items() if k not in _PLAN_SKIP},
            'tasks': sorted(({k: v for k, v in t.to_dict().items() if k not in _TASK_SKIP}
                             for t in tasks), key=lambda t: t['key'])}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'))
                          .encode('utf-8')).hexdigest()
