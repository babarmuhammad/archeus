"""Every entity of domain-model.md, with the minimal fields P1 needs.

The P1 rule (plan §31.1, L7): every entity exists and validates; the other
columns domain-model.md lists arrive with the phase that uses them. So these are
deliberately thin: identity, scope, lifecycle state and the few fields that
define what the thing IS. `version`, timestamps and provenance columns are rows
of the P2 schema, not of this module.

Entities are frozen: a state change is a new value produced by the P2
persistence primitive `Tx.transition()` (which P3's guarded, application-level
transition calls), never an attribute assignment. Validation is declarative (class
variables read by `Entity.__post_init__`) so a new entity is a field list, not
a new copy of the checks. `Event` lives in events.py beside its type registry.
"""

import dataclasses
import re
from dataclasses import dataclass, fields
from typing import ClassVar

from . import ids, states
from .actions import ACTION_CLASSES, DECISIONS, Action
from .values import ORIGINS, PRINCIPAL_SCOPES, Ref

_HEX64 = re.compile(r'[0-9a-f]{64}')


class Entity:
    """Declarative validation shared by every entity.

    _ID       id kind in ids.PREFIXES; None = a free-form string identity
    _STATE    (field, machine) validated against states.states(machine); a
              missing value defaults to the machine's initial state
    _TEXT     fields that must be non-empty strings
    _CHOICES  {field: allowed values}
    _REFS     {field: id kind or tuple of kinds} for foreign keys
    _NONNEG   integer fields that must be >= 0 (`_MIN1` for >= 1)
    None passes every check when it is the field's default (optional field).
    """
    _ID: ClassVar = None
    _STATE: ClassVar = None
    _TEXT: ClassVar = ()
    _CHOICES: ClassVar = {}
    _REFS: ClassVar = {}
    _NONNEG: ClassVar = ()
    _MIN1: ClassVar = ()

    def __post_init__(self):
        name = type(self).__name__
        optional = {f.name for f in fields(self) if f.default is None}
        for f in fields(self):                       # coerce what JSON flattens
            v = getattr(self, f.name)
            if isinstance(v, list):
                self._set(f.name, tuple(v))
            elif isinstance(v, dict) and f.type in (Ref, Action):
                self._set(f.name, f.type(**v))

        def bad(field, why):
            raise ValueError('%s.%s %s: %r' % (name, field, why, getattr(self, field)))

        if 'id' in {f.name for f in fields(self)}:
            if self._ID is not None:
                if not ids.is_id(self.id, self._ID):
                    bad('id', 'is not a %s id' % self._ID)
            elif not (isinstance(self.id, str) and self.id):
                bad('id', 'must be a non-empty string')
        if self._STATE:
            field, machine = self._STATE
            if getattr(self, field) is None:
                self._set(field, states.initial(machine))
            if getattr(self, field) not in states.states(machine):
                bad(field, 'is not a %s state' % machine)
        for field in self._TEXT:
            v = getattr(self, field)
            if not (isinstance(v, str) and v.strip()):
                if not (v is None and field in optional):
                    bad(field, 'must be a non-empty string')
        for field, allowed in self._CHOICES.items():
            v = getattr(self, field)
            if v not in allowed and not (v is None and field in optional):
                bad(field, 'must be one of %s' % (allowed,))
        refs = dict(self._REFS)
        for field in ('workspace_id', 'project_id'):
            if hasattr(self, field):
                refs.setdefault(field, field[:-3])
        for field, kinds in refs.items():
            v = getattr(self, field)
            if v is None and field in optional:
                continue
            if not any(ids.is_id(v, k) for k in ((kinds,) if isinstance(kinds, str) else kinds)):
                bad(field, 'is not a %s id' % (kinds,))
        for field in self._NONNEG + self._MIN1:
            v = getattr(self, field)
            low = 1 if field in self._MIN1 else 0
            if not (isinstance(v, int) and not isinstance(v, bool) and v >= low):
                bad(field, 'must be an integer >= %d' % low)
        self._check()

    def _check(self):
        """Per-entity invariants beyond the declarative ones."""

    def _set(self, field, value):
        object.__setattr__(self, field, value)      # frozen: only during __post_init__

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data):
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError('%s: unknown fields %s' % (cls.__name__, sorted(unknown)))
        return cls(**data)


def entity(cls):
    return dataclass(frozen=True, kw_only=True)(cls)


# ── identity, principals, devices (domain-model §3) ─────────────────────────

@entity
class User(Entity):
    _ID = 'user'
    _TEXT = ('display_name',)
    id: str
    display_name: str


@entity
class Identity(Entity):
    _ID = 'identity'
    _REFS = {'user_id': 'user', 'default_workspace_id': 'workspace'}
    id: str
    user_id: str
    default_workspace_id: str = ids.GLOBAL_WORKSPACE


@entity
class Principal(Entity):
    _ID = 'principal'
    _CHOICES = {'kind': tuple(PRINCIPAL_SCOPES)}
    id: str
    kind: str
    scopes: tuple = ()

    def _check(self):
        extra = set(self.scopes) - set(PRINCIPAL_SCOPES[self.kind])
        if extra:
            raise ValueError('a %s principal cannot hold %s' % (self.kind, sorted(extra)))


@entity
class Device(Entity):
    _ID = 'device'
    _STATE = ('state', 'device')
    _TEXT = ('name',)
    _CHOICES = {'platform': ('desktop', 'web', 'ios', 'android', 'tui')}
    _REFS = {'principal_id': 'principal'}
    id: str
    principal_id: str
    name: str
    platform: str
    state: str = None


# ── world (domain-model §4) ─────────────────────────────────────────────────

@entity
class Workspace(Entity):
    _ID = 'workspace'
    _TEXT = ('name',)
    id: str
    name: str


@entity
class Organization(Entity):
    _ID = 'organization'
    _TEXT = ('name',)
    id: str
    workspace_id: str
    name: str


@entity
class Person(Entity):
    _ID = 'person'
    _TEXT = ('name',)
    id: str
    workspace_id: str
    name: str
    organization_id: str = None
    _REFS = {'organization_id': 'organization'}


@entity
class Project(Entity):
    _ID = 'project'
    _TEXT = ('name',)
    id: str
    workspace_id: str
    name: str
    root_paths: tuple = ()


@entity
class Repository(Entity):
    _ID = 'repository'
    _STATE = ('architecture_state', 'architecture')
    _TEXT = ('path',)
    _CHOICES = {'kind': ('repo', 'submodule', 'worktree')}
    id: str
    workspace_id: str
    project_id: str
    path: str
    kind: str = 'repo'
    architecture_state: str = None


@entity
class RepositoryInspection(Entity):
    _ID = 'repository_inspection'
    _STATE = ('state', 'repository_inspection')
    _REFS = {'repository_id': 'repository'}
    id: str
    repository_id: str
    revision: str = None
    state: str = None


@entity
class System(Entity):
    _ID = 'system'
    _TEXT = ('name',)
    _CHOICES = {'environment': ('dev', 'staging', 'prod')}
    id: str
    workspace_id: str
    name: str
    environment: str
    project_id: str = None


@entity
class Idea(Entity):
    _ID = 'idea'
    _STATE = ('state', 'idea')
    _TEXT = ('text',)
    id: str
    workspace_id: str
    text: str
    project_id: str = None
    state: str = None


@entity
class Meeting(Entity):
    _ID = 'meeting'
    _TEXT = ('name', 'held_at')
    id: str
    workspace_id: str
    name: str
    held_at: str
    project_id: str = None


@entity
class Decision(Entity):
    _ID = 'decision'
    _TEXT = ('statement',)
    _CHOICES = {'status': ('active', 'superseded', 'reversed')}
    _REFS = {'supersedes_id': 'decision'}
    id: str
    workspace_id: str
    statement: str
    status: str = 'active'
    project_id: str = None
    supersedes_id: str = None


# ── knowledge (domain-model §5) ─────────────────────────────────────────────

KNOWLEDGE_TYPES = ('FACT', 'DECISION', 'LESSON', 'PREFERENCE', 'STANDARD',
                   'ARCHITECTURE', 'REFERENCE', 'ENTITY')
RELATIONS = ('contains', 'depends_on', 'uses', 'calls', 'implements', 'mentions',
             'decided_in', 'constrains', 'motivated', 'produced', 'learned_from',
             'supersedes', 'contradicts', 'blocks', 'relates_to', 'owns', 'attended')
BODY_MAX_BYTES = 2048


@entity
class KnowledgeItem(Entity):
    _ID = 'knowledge_item'
    _STATE = ('state', 'knowledge_item')
    _TEXT = ('title',)
    _CHOICES = {'type': KNOWLEDGE_TYPES, 'origin': ORIGINS}
    _REFS = {'supersedes_id': 'knowledge_item'}
    id: str
    workspace_id: str
    type: str
    title: str
    body: str = ''
    origin: str = 'inferred'
    project_id: str = None
    supersedes_id: str = None
    state: str = None

    def _check(self):
        if len(self.body.encode('utf-8')) > BODY_MAX_BYTES:
            raise ValueError('knowledge body is over %d bytes; longer material is an '
                             'artifact' % BODY_MAX_BYTES)


@entity
class Relation(Entity):
    _ID = 'relation'
    _CHOICES = {'rel': RELATIONS,
                'confidence_tier': ('EXTRACTED', 'INFERRED', 'AMBIGUOUS')}
    id: str
    src: Ref
    rel: str
    dst: Ref
    confidence_tier: str = 'EXTRACTED'


# ── conversation and intent (domain-model §6) ───────────────────────────────

@entity
class Conversation(Entity):
    _ID = 'conversation'
    _CHOICES = {'kind': ('primary', 'mission')}
    _REFS = {'mission_id': 'mission'}
    id: str
    kind: str
    mission_id: str = None

    def _check(self):
        if (self.kind == 'mission') != (self.mission_id is not None):
            raise ValueError('a mission thread names its mission; the primary one does not')


@entity
class Message(Entity):
    _ID = 'message'
    _CHOICES = {'author': ('user', 'archeus', 'system')}
    _REFS = {'conversation_id': 'conversation'}
    id: str
    conversation_id: str
    author: str
    text: str = ''


@entity
class Intent(Entity):
    _ID = 'intent'
    _TEXT = ('utterance',)
    _CHOICES = {'kind': ('control_verb', 'question', 'new_work', 'continue_work',
                         'feedback', 'preference', 'idea')}
    _REFS = {'message_id': 'message'}
    id: str
    message_id: str
    utterance: str
    kind: str


# ── work (domain-model §7) ──────────────────────────────────────────────────

CRITERION_CHECKS = ('automatic', 'human')
COST_BANDS = ('low', 'medium', 'high')      # bands, never precise (domain-model §7.2)

@entity
class Mission(Entity):
    _ID = 'mission'
    _STATE = ('state', 'mission')
    _TEXT = ('title', 'objective')
    _CHOICES = {'origin': ('conversation', 'idea', 'automation', 'legacy_import')}
    _NONNEG = ('max_replans',)
    id: str
    workspace_id: str
    title: str
    objective: str
    origin: str = 'conversation'
    project_id: str = None
    priority: int = 0
    max_replans: int = 2            # `replan_budget_exhausted` (state-machines §2)
    # the state the mission was in when it last entered BLOCKED or PAUSED;
    # `resume` reads it (current state, never the event log, which retention
    # may prune)
    held_from: str = None
    # the plan_version the mission last decided (auto-approved or sent for
    # approval), recorded with that move: the plan gate never decides the same
    # plan twice, so REPLANNING (or PLANNING after request_changes) needs a new one
    decided_plan_version: int = None
    # each {text, check: automatic|human, origin: explicit|inferred}; the
    # `verified` guard reads their verifications (state-machines §2)
    success_criteria: tuple = ()
    state: str = None

    def _check(self):
        if self.held_from is not None and self.held_from not in states.states('mission'):
            raise ValueError('Mission.held_from is not a mission state: %r' % self.held_from)
        v = self.decided_plan_version
        if v is not None and not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
            raise ValueError('Mission.decided_plan_version is a plan_version >= 1: %r' % (v,))
        for c in self.success_criteria:
            if not (isinstance(c, dict) and isinstance(c.get('text'), str) and c['text'].strip()
                    and c.get('check') in CRITERION_CHECKS
                    and c.get('origin', 'explicit') in ORIGINS
                    and set(c) <= {'text', 'check', 'origin'}):
                raise ValueError('a success criterion is {text, check: automatic|human, '
                                 'origin?}: %r' % (c,))


@entity
class Plan(Entity):
    _ID = 'plan'
    _STATE = ('state', 'plan')
    _REFS = {'mission_id': 'mission'}
    _CHOICES = {'estimated_cost': COST_BANDS}
    _MIN1 = ('plan_version',)
    id: str
    mission_id: str
    # the plan's own number within its mission (1, 2, … per replan), which
    # `action_hash` binds approvals to — not the row's optimistic-concurrency
    # `version`, which the P2 schema owns for every table
    plan_version: int = 1
    summary: str = ''
    estimated_cost: str = None
    state: str = None


TASK_KINDS = ('code_change', 'research', 'document', 'presentation', 'inspection',
              'verification', 'human')


@entity
class Task(Entity):
    _ID = 'task'
    _STATE = ('state', 'task')
    _TEXT = ('key', 'title')
    _CHOICES = {'kind': TASK_KINDS}
    _REFS = {'plan_id': 'plan', 'mission_id': 'mission'}
    _MIN1 = ('max_attempts',)
    id: str
    plan_id: str
    mission_id: str
    key: str
    title: str
    kind: str
    depends_on: tuple = ()
    action_classes: tuple = ()
    max_attempts: int = 2
    # why the task FAILED, set with that move (`task_failed_retryable` reads it)
    failure_class: str = None
    state: str = None

    def _check(self):
        unknown = set(self.action_classes) - set(ACTION_CLASSES)
        if unknown:
            raise ValueError('unknown action classes: %s' % sorted(unknown))
        if self.key in self.depends_on:
            raise ValueError('a task cannot depend on itself')


@entity
class Execution(Entity):
    _ID = 'execution'
    _STATE = ('state', 'execution')
    _REFS = {'task_id': 'task', 'mission_id': 'mission'}
    _MIN1 = ('attempt',)
    _CHOICES = {'exit_reason': ('ok', 'error', 'killed', 'lost', 'abandoned')}
    id: str
    task_id: str
    mission_id: str
    attempt: int = 1
    harness_id: str = None
    # the process (pid + creation time guards against PID reuse) and its end
    pid: int = None
    create_time: object = None
    exit_reason: str = None
    exit_code: int = None
    summary: str = ''           # reported by the harness; never the completion signal
    state: str = None


@entity
class Session(Entity):
    _ID = 'session'
    _STATE = ('state', 'session')
    _TEXT = ('harness_id',)
    _REFS = {'account_id': 'account'}
    id: str
    harness_id: str
    account_id: str
    state: str = None


@entity
class Checkpoint(Entity):
    _ID = 'checkpoint'
    _CHOICES = {'trigger': ('task_boundary', 'pressure', 'account_change', 'pause', 'failure')}
    _REFS = {'execution_id': 'execution', 'mission_id': 'mission'}
    id: str
    execution_id: str
    mission_id: str
    trigger: str
    next_action: str = ''


@entity
class Verification(Entity):
    _ID = 'verification'
    _STATE = ('state', 'verification')
    _CHOICES = {'verifier': ('code', 'research', 'document', 'presentation',
                             'automation', 'generic_human')}
    _REFS = {'plan_id': 'plan'}
    id: str
    subject: Ref
    verifier: str
    independent: bool = False
    # the plan in force when it ran: a verification counts for that plan only
    plan_id: str = None
    # for a mission: the index of the success criterion it checks
    criterion: int = None
    state: str = None

    def _check(self):
        if self.subject.kind not in ('task', 'mission'):
            raise ValueError('a verification is of a task or a mission')
        if (self.criterion is not None) != (self.subject.kind == 'mission'):
            raise ValueError('a mission verification names its criterion; a task one does not')
        if self.criterion is not None and not (
                isinstance(self.criterion, int) and not isinstance(self.criterion, bool)
                and self.criterion >= 0):
            raise ValueError('Verification.criterion is an index >= 0: %r' % (self.criterion,))


@entity
class Review(Entity):
    _ID = 'review'
    _STATE = ('state', 'review')
    _TEXT = ('reviewer',)
    _CHOICES = {'verdict': ('accept', 'changes_requested', 'reject')}
    _REFS = {'mission_id': 'mission', 'plan_id': 'plan'}
    id: str
    mission_id: str
    reviewer: str
    independent: bool = False
    verdict: str = None
    plan_id: str = None         # the plan whose result was reviewed
    state: str = None


@entity
class Feedback(Entity):
    _ID = 'feedback'
    _CHOICES = {'signal': ('positive', 'negative', 'correction')}
    id: str
    subject: Ref
    signal: str
    text: str = ''


@entity
class Artifact(Entity):
    """Content-addressed: the id IS the sha256."""
    _TEXT = ('media_type',)
    _NONNEG = ('size',)
    id: str
    media_type: str
    size: int

    def _check(self):
        if not _HEX64.fullmatch(self.id):
            raise ValueError('an artifact id is its lowercase hex sha256')


# ── resources (domain-model §8) ─────────────────────────────────────────────

_HARNESS_ID = re.compile(r'[a-z][a-z0-9_]*(:[A-Za-z0-9_.-]+)?')


@entity
class Harness(Entity):
    _STATE = ('state', 'harness')
    _CHOICES = {'enforcement': ('hook', 'sandbox', 'none')}
    id: str
    enforcement: str = 'none'
    state: str = None

    def _check(self):
        if not _HARNESS_ID.fullmatch(self.id):
            raise ValueError('harness id %r (e.g. claude_code, generic_cli:aider)' % self.id)


@entity
class Account(Entity):
    _ID = 'account'
    _STATE = ('health', 'account_health')
    _TEXT = ('harness_id', 'label')
    _CHOICES = {'auth_kind': ('subscription_oauth', 'api_key', 'provider_proxy')}
    _REFS = {'node_id': 'execution_node'}
    id: str
    harness_id: str
    label: str
    auth_kind: str
    node_id: str
    health: str = None


@entity
class Model(Entity):
    _TEXT = ('family',)
    _CHOICES = {'tier': ('large', 'mid', 'small')}
    _MIN1 = ('context_window',)
    id: str
    family: str
    tier: str
    context_window: int


@entity
class ModelOffer(Entity):
    _TEXT = ('model_id',)
    _REFS = {'account_id': 'account'}
    account_id: str
    model_id: str
    available: bool = True


@entity
class ResourcePolicy(Entity):
    _ID = 'resource_policy'
    _CHOICES = {'fallback': ('allow', 'ask', 'deny')}
    _REFS = {'account_id': 'account'}
    _NONNEG = ('allocation_pct', 'reserve_pct', 'brain_reserve_pct')
    _MIN1 = ('priority',)
    id: str
    account_id: str
    priority: int = 1
    allocation_pct: int = 100
    reserve_pct: int = 0
    brain_reserve_pct: int = 0
    fallback: str = 'ask'

    def _check(self):
        if self.allocation_pct > 100:
            raise ValueError('allocation_pct is a share of the provider window (<= 100)')
        if self.reserve_pct + self.brain_reserve_pct > self.allocation_pct:
            raise ValueError('reserves exceed the allocation: nothing would ever route here')


@entity
class UsageSnapshot(Entity):
    _ID = 'usage_snapshot'
    _CHOICES = {'window': ('5h', '7d', 'monthly'),
                'source': ('usage_api', 'rate_limit_headers', 'rollout_file')}
    _REFS = {'account_id': 'account'}
    id: str
    account_id: str
    window: str
    utilisation_pct: float
    source: str

    def _check(self):
        if not (isinstance(self.utilisation_pct, (int, float)) and self.utilisation_pct >= 0):
            raise ValueError('utilisation_pct must be a number >= 0')


@entity
class UsageLedger(Entity):
    _ID = 'usage_ledger'
    _REFS = {'execution_id': 'execution', 'account_id': 'account'}
    _NONNEG = ('tokens_in', 'tokens_out')
    id: str
    execution_id: str
    account_id: str
    tokens_in: int = 0
    tokens_out: int = 0


@entity
class RouteDecision(Entity):
    _ID = 'route_decision'
    id: str
    subject: Ref
    selected: str = None          # None: no candidate survived (blocked / ask)
    explanation: str = ''


@entity
class ExecutionNode(Entity):
    _ID = 'execution_node'
    _STATE = ('state', 'execution_node')
    _TEXT = ('name',)
    _CHOICES = {'kind': ('local', 'remote')}
    id: str
    name: str
    kind: str = 'local'
    state: str = None


# ── control (domain-model §9) ───────────────────────────────────────────────

SCOPE_LEVELS = ('GLOBAL', 'USER', 'WORKSPACE', 'PROJECT', 'MISSION', 'TASK')


@entity
class PolicyRule(Entity):
    _ID = 'policy_rule'
    _CHOICES = {'scope_level': SCOPE_LEVELS, 'action_class': ACTION_CLASSES,
                'decision': DECISIONS}
    id: str
    scope_level: str
    action_class: str
    decision: str
    scope_ref: str = None
    locked: bool = None           # None -> derived: DENY is always locked

    def _check(self):
        if self.locked is None:
            self._set('locked', self.decision == 'DENY')
        if self.decision == 'DENY' and not self.locked:
            raise ValueError('DENY is always locked')


@entity
class PolicyDecision(Entity):
    _ID = 'policy_decision'
    _CHOICES = {'decision': DECISIONS}
    id: str
    action: Action
    decision: str
    reason: str = ''


@entity
class Approval(Entity):
    _ID = 'approval'
    _STATE = ('state', 'approval')
    _REFS = {'requested_by': 'principal'}
    id: str
    subject: Ref
    action_hash: str
    requested_by: str
    step_up: bool = False
    state: str = None

    def _check(self):
        if not (isinstance(self.action_hash, str) and _HEX64.fullmatch(self.action_hash)):
            raise ValueError('action_hash is the hex sha256 of the canonical action')


@entity
class Automation(Entity):
    _ID = 'automation'
    _STATE = ('state', 'automation')
    _TEXT = ('name',)
    _MIN1 = ('max_depth', 'rate_limit')
    id: str
    workspace_id: str
    name: str
    max_depth: int = 3
    rate_limit: int = 6
    project_id: str = None
    state: str = None


@entity
class AutomationRun(Entity):
    _ID = 'automation_run'
    _STATE = ('state', 'automation_run')
    _REFS = {'automation_id': 'automation'}
    _NONNEG = ('triggering_event_seq',)
    id: str
    automation_id: str
    triggering_event_seq: int
    state: str = None


#: Every entity class, for the tests that walk them all. `Event` is in events.py.
ENTITIES = tuple(c for c in list(globals().values())
                 if isinstance(c, type) and issubclass(c, Entity) and c is not Entity)
