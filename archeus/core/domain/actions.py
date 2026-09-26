"""Policy action classes, decisions and the canonical action (plan §13, domain-model §9).

The closed lists here are what policy rules, tasks and plans name. An Approval
binds to `action_hash(...)` — the exact identity of what is authorised: its
kind, the mission, the plan version (id, number and content digest), the task,
the execution and the canonical actions (p9-design-gate §7, D7). The policy
version it was decided under is recorded beside the hash, never in it: every
use re-evaluates the current policy instead (§8.4).
"""

import hashlib
import json
from dataclasses import dataclass

ACTION_CLASSES = (
    'read', 'web', 'write_repo', 'exec', 'git_commit', 'git_push', 'deploy',
    'external_comm', 'destructive', 'spend', 'personal_data', 'install', 'credential',
)

#: The four policy decisions, used everywhere (state-machines §0).
DECISIONS = ('ALLOW', 'ASK', 'ALLOW_WITHIN_BOUNDARY', 'DENY')

#: What an approval or a decision can be about (p9-design-gate §8.1).
APPROVAL_KINDS = ('plan', 'task', 'action')
#: The identity an authorisation is bound to (§7.2): exactly these keys.
BINDING_KEYS = ('mission_id', 'plan_id', 'plan_version', 'plan_digest', 'task_id',
                'task_key', 'execution_id')
#: The closed vocabularies of a rule's `match` and `boundary` (§6).
MATCH_KEYS = ('environment', 'path_glob', 'branch_glob', 'host_glob', 'command_glob',
              'min_cost_band')
BOUNDARY_KEYS = ('paths', 'branches', 'hosts', 'environments', 'max_cost_band')


@dataclass(frozen=True, kw_only=True)
class Action:
    """The canonical form of something an execution or Core wants to do."""
    action_class: str
    target: str
    argv: tuple = None
    diff_hash: str = None
    environment: str = None
    # project-relative globs the action touches (a plan-level item: its task's
    # `touches`); None when unknown (p9-design-gate §3.3)
    paths: tuple = None

    def __post_init__(self):
        if self.action_class not in ACTION_CLASSES:
            raise ValueError('unknown action class: %r' % (self.action_class,))
        if not (isinstance(self.target, str) and self.target):
            raise ValueError('an action needs a target')
        for k in ('argv', 'paths'):
            if getattr(self, k) is not None:
                object.__setattr__(self, k, tuple(str(a) for a in getattr(self, k)))

    def canonical_dict(self):
        body = {'class': self.action_class, 'target': self.target}
        for k in ('argv', 'diff_hash', 'environment', 'paths'):
            v = getattr(self, k)
            if v is not None:
                body[k] = list(v) if k in ('argv', 'paths') else v
        return body

    def canonical(self):
        """Stable JSON: same action -> same bytes, whatever order it was built in."""
        return _json(self.canonical_dict())


def _json(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'))


def binding(*, mission_id, plan_id, plan_version, plan_digest, task_id=None, task_key=None,
            execution_id=None):
    """The exact plan version (and task, and execution) an authorisation is for."""
    return {'mission_id': mission_id, 'plan_id': plan_id, 'plan_version': plan_version,
            'plan_digest': plan_digest, 'task_id': task_id, 'task_key': task_key,
            'execution_id': execution_id}


def item(task_key, action):
    """One authorisable item: an action of a task, in canonical form."""
    return {'task': task_key, 'action': action.canonical_dict()}


def action_hash(kind, bind, items):
    """SHA-256 of the exact identity an Approval or a PolicyDecision is bound to
    (p9-design-gate §7.2): the kind, the binding and the canonical items. The
    policy version is deliberately NOT part of it (D7): it is recorded beside
    the hash, and every use of an approval re-evaluates the current policy."""
    if kind not in APPROVAL_KINDS:
        raise ValueError('unknown approval kind: %r' % (kind,))
    if set(bind) != set(BINDING_KEYS):
        raise ValueError('a binding names exactly %s' % (BINDING_KEYS,))
    if not (bind['mission_id'] and bind['plan_id'] and bind['plan_digest']):
        raise ValueError('a binding names its mission, plan and plan digest')
    body = {'v': 1, 'kind': kind, 'binding': dict(bind),
            'items': sorted((dict(i) for i in items), key=_json)}
    return hashlib.sha256(_json(body).encode('utf-8')).hexdigest()
