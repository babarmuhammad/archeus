"""Policy rules as data: the built-in floor, the autonomy profiles and the
predicates rules are made of (p9-design-gate §4-§6). Pure: no I/O, no clock
(the caller passes `now`), nothing but its arguments.

A rule here is a plain dict — the same shape for a built-in rule, an expanded
profile rule and a user's `PolicyRule` row (`from_entity`) — so a decision can
snapshot every rule it read and replay from the snapshot alone.
"""

import re

from ..domain.actions import ACTION_CLASSES

LEVELS = ('GLOBAL', 'USER', 'WORKSPACE', 'PROJECT', 'MISSION', 'TASK')
#: DENY > ASK > ALLOW_WITHIN_BOUNDARY > ALLOW (plan §13)
STRICTNESS = {'ALLOW': 0, 'ALLOW_WITHIN_BOUNDARY': 1, 'ASK': 2, 'DENY': 3}
#: an attribute the action does not carry matches only these (§6.1, D3)
RESTRICTIVE = ('ASK', 'DENY')
#: an ASK for these needs a step-up proof (domain-model §9.3)
STEP_UP_CLASSES = ('deploy', 'destructive')
#: what a task's capabilities make inevitable (§3.3, D6)
IMPLIED = {'code_edit': 'write_repo', 'shell': 'exec', 'web': 'web'}
COST_BANDS = ('low', 'medium', 'high')
PROFILES_VERSION = 1
ENGINE_VERSION = 1
#: the task's own workspace: its worktree, or the execution's own directory (§5.2)
WORKSPACE = '@workspace'

AWB = 'ALLOW_WITHIN_BOUNDARY'
_IN_WORKSPACE = {'paths': [WORKSPACE + '/**']}
_TASK_BRANCHES = {'branches': ['archeus/*']}


def _profile(overrides):
    table = {c: ('ASK', None) for c in ACTION_CLASSES}
    table.update(read=('ALLOW', None), web=('ALLOW', None))
    table.update(overrides)
    return table


#: The three autonomy profiles (§5.2): class -> (decision, boundary).
PROFILES = {
    'careful': _profile({}),
    'standard': _profile({'write_repo': (AWB, _IN_WORKSPACE), 'exec': (AWB, _IN_WORKSPACE),
                          'git_commit': (AWB, _TASK_BRANCHES)}),
    'autonomous': _profile({'write_repo': (AWB, _IN_WORKSPACE), 'exec': (AWB, _IN_WORKSPACE),
                            'git_commit': (AWB, _TASK_BRANCHES),
                            'git_push': (AWB, _TASK_BRANCHES)}),
}


def rule(*, id, scope_level, action_class, decision, scope_ref=None, locked=None, match=None,
         boundary=None, outside='ASK', source='user', expires_at=None, **_ignored):
    """The one rule shape the engine reads."""
    return {'id': id, 'scope_level': scope_level, 'scope_ref': scope_ref,
            'action_class': action_class, 'decision': decision,
            'locked': bool(decision == 'DENY' if locked is None else locked or decision == 'DENY'),
            'match': dict(match or {}), 'boundary': dict(boundary) if boundary else None,
            'outside': outside or 'ASK', 'source': source, 'expires_at': expires_at}


#: GLOBAL, locked, not a profile (plan §13 spec examples).
FLOOR = (
    rule(id='builtin:floor:destructive-prod', scope_level='GLOBAL', action_class='destructive',
         decision='DENY', match={'environment': 'prod'}, source='builtin'),
    rule(id='builtin:floor:deploy-prod', scope_level='GLOBAL', action_class='deploy',
         decision='ASK', locked=True, match={'environment': 'prod'}, source='builtin'),
)
#: the dispatch contract (§4.4): a class the task did not declare asks
TASK_CONTRACT = rule(id='builtin:task-contract', scope_level='TASK', action_class='read',
                     decision='ASK', locked=True, source='builtin')
ESTOP = rule(id='builtin:estop', scope_level='GLOBAL', action_class='read', decision='DENY',
             source='builtin')
MISSING = rule(id='builtin:policy-missing', scope_level='GLOBAL', action_class='read',
               decision='DENY', source='builtin')


def profile_rules(name, level, scope_ref=None):
    """A profile expanded at *level*: one unlocked rule per class."""
    return [rule(id='profile:%s@%d:%s:%s' % (name, PROFILES_VERSION, level, c),
                 scope_level=level, scope_ref=scope_ref, action_class=c, decision=d,
                 boundary=b, source='profile')
            for c, (d, b) in PROFILES[name].items()]


def builtin():
    """Core's GLOBAL rules: the floor and the `careful` baseline."""
    return list(FLOOR) + profile_rules('careful', 'GLOBAL')


def from_entity(r):
    """A PolicyRule row as the engine's rule dict."""
    return rule(**{k: getattr(r, k) for k in (
        'id', 'scope_level', 'action_class', 'decision', 'scope_ref', 'locked', 'match',
        'boundary', 'outside', 'source', 'expires_at')})


def implied(action_classes, capabilities=()):
    """[(class, implied_by or None)]: the declared classes, then what the
    task's capabilities make inevitable, each once, in a stable order."""
    out = [(c, None) for c in dict.fromkeys(action_classes)]
    seen = {c for c, _ in out}
    for cap in capabilities:
        c = IMPLIED.get(cap)
        if c and c not in seen:
            out.append((c, cap))
            seen.add(c)
    return out


# ── predicates (§6) ─────────────────────────────────────────────────────────

def _norm(s):
    return str(s).replace('\\', '/')


def _regex(pattern):
    out, i, p = [], 0, _norm(pattern)
    while i < len(p):
        if p.startswith('**', i):
            out.append('.*')
            i += 2
        elif p[i] == '*':
            out.append('[^/]*')
            i += 1
        elif p[i] == '?':
            out.append('[^/]')
            i += 1
        else:
            out.append(re.escape(p[i]))
            i += 1
    return re.compile(''.join(out) + r'\Z')


def glob(pattern, value):
    """`*` stays within a path segment, `**` crosses them."""
    return _regex(pattern).match(_norm(value)) is not None


def _relative(path):
    p = _norm(path)
    return not (p.startswith('/') or re.match(r'[A-Za-z]:', p) or '..' in p.split('/'))


def inside(path, pattern):
    """Conservative containment of a path (or glob) in `base/**`, or in the
    workspace: provable or not inside, never guessed (§6.2)."""
    if not _relative(path):
        return False
    pat = _norm(pattern)
    if pat.startswith(WORKSPACE):
        pat = pat[len(WORKSPACE):].lstrip('/')
    p = _norm(path)
    while p.startswith('./'):
        p = p[2:]
    if not pat.endswith('**'):
        return p == pat
    base = pat[:-2].rstrip('/')
    if base == '':
        return True
    wild = re.search(r'[*?\[]', p)
    if wild:
        return p[:wild.start()].startswith(base + '/')
    return p == base or p.startswith(base + '/')


def _values(action, key):
    """What an action says about an attribute; None when it does not say."""
    if key in ('environment', 'environments'):
        return None if action.environment is None else [action.environment]
    if key in ('path_glob', 'paths'):
        return list(action.paths) if action.paths else None
    if key == 'command_glob':
        return [' '.join(action.argv)] if action.argv else None
    return None     # branch, host, cost band: only the action stage knows them (P11)


def matches(r, action):
    """Does rule *r* apply to *action*? A key the action says nothing about
    matches a restrictive rule and never a permissive one (D3)."""
    for key, want in (r.get('match') or {}).items():
        vals = _values(action, key)
        if not vals:
            if r['decision'] in RESTRICTIVE:
                continue
            return False
        wants = want if isinstance(want, (list, tuple)) else [want]
        if key == 'environment':
            ok = any(v in wants for v in vals)
        else:
            ok = any(glob(w, v) for w in wants for v in vals)
        if not ok:
            return False
    return True


def check_boundary(boundary, action, stage):
    """{checked, deferred, outside}: which predicates hold, which the plan
    stage cannot know yet (enforced later), and which do not hold."""
    out = {'checked': [], 'deferred': [], 'outside': []}
    for key in sorted(boundary):
        allowed = boundary[key]
        vals = _values(action, key)
        if not vals:
            out['deferred' if stage == 'plan' else 'outside'].append(key)
            continue
        if key == 'paths':
            ok = all(any(inside(v, a) for a in allowed) for v in vals)
        elif key == 'environments':
            ok = all(v in allowed for v in vals)
        elif key == 'max_cost_band':
            ok = all(COST_BANDS.index(v) <= COST_BANDS.index(allowed) for v in vals)
        else:
            ok = all(any(glob(a, v) for a in allowed) for v in vals)
        out['checked' if ok else 'outside'].append(key)
    return out
