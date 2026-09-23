"""Policy action classes, decisions and the canonical action (plan §13, domain-model §9).

The closed lists here are what policy rules, tasks and plans name. An Approval
binds to `action_hash(...)` — the canonical action plus the policy and plan
versions it was decided under — so it is valid for exactly that action.
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


@dataclass(frozen=True, kw_only=True)
class Action:
    """The canonical form of something an execution or Core wants to do."""
    action_class: str
    target: str
    argv: tuple = None
    diff_hash: str = None
    environment: str = None

    def __post_init__(self):
        if self.action_class not in ACTION_CLASSES:
            raise ValueError('unknown action class: %r' % (self.action_class,))
        if not (isinstance(self.target, str) and self.target):
            raise ValueError('an action needs a target')
        if self.argv is not None:
            object.__setattr__(self, 'argv', tuple(str(a) for a in self.argv))

    def canonical(self):
        """Stable JSON: same action -> same bytes, whatever order it was built in."""
        body = {'class': self.action_class, 'target': self.target}
        for k in ('argv', 'diff_hash', 'environment'):
            v = getattr(self, k)
            if v is not None:
                body[k] = list(v) if k == 'argv' else v
        return json.dumps(body, sort_keys=True, separators=(',', ':'))


def action_hash(action, policy_version, plan_version):
    """SHA-256 an Approval is bound to (domain-model §9.3)."""
    blob = '%s|policy:%s|plan:%s' % (action.canonical(), policy_version, plan_version)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()
