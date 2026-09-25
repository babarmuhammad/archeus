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
from .values import ORIGINS, PRINCIPAL_SCOPES, SOURCE_KINDS, Ref

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
    _NONNEG = ('last_ack_event_seq',)
    id: str
    display_name: str
    last_ack_event_seq: int = 0


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
    _CHOICES = {'state': ('ACTIVE', 'ARCHIVED')}
    id: str
    workspace_id: str
    name: str
    root_paths: tuple = ()
    state: str = 'ACTIVE'


@entity
class Repository(Entity):
    """A git working tree of a project. `path_key` is its identity on this
    machine (the real, case-folded path). The drift assessment is current
    state, so it lives here, not on an inspection: `findings` were evaluated
    against exactly `evaluated_constraints` (knowledge item id, version) on the
    observation `last_inspection_id` of revision `last_revision`, and the
    `architecture` machine's guards bind the state to those findings."""
    _ID = 'repository'
    _STATE = ('architecture_state', 'architecture')
    _TEXT = ('path', 'path_key')
    _CHOICES = {'kind': ('repo', 'submodule', 'worktree')}
    _REFS = {'last_inspection_id': 'repository_inspection'}
    id: str
    workspace_id: str
    project_id: str
    path: str
    path_key: str
    kind: str = 'repo'
    architecture_state: str = None
    last_inspection_id: str = None
    last_revision: str = None
    default_branch: str = None
    findings: tuple = ()
    evaluated_against: str = None
    evaluated_constraints: tuple = ()


@entity
class RepositoryInspection(Entity):
    """One observation of one repository at one revision by one extractor
    version (domain-model §4). The module graph and dependencies it read are
    the artifact `payload_sha256`; the row keeps what a query shows. `attempts`
    counts the failures that count against the retry cap (p4-design-gate §11)."""
    _ID = 'repository_inspection'
    _STATE = ('state', 'repository_inspection')
    _REFS = {'repository_id': 'repository'}
    _NONNEG = ('extractor_version', 'attempts')
    id: str
    repository_id: str
    extractor_version: int
    revision: str = None
    state: str = None
    attempts: int = 0
    inspected_at: str = None
    dirty: bool = None
    complete: bool = None
    languages: tuple = ()
    dependencies: tuple = ()
    frameworks: tuple = ()
    docs: tuple = ()
    agent_config: tuple = ()
    test_commands: tuple = ()
    build_commands: tuple = ()
    notes: tuple = ()
    payload_sha256: str = None
    diff_from_previous: dict = None
    failure: str = None
    failed_at: str = None

    def _check(self):
        if self.payload_sha256 is not None and not _HEX64.fullmatch(self.payload_sha256):
            raise ValueError('payload_sha256 is a sha256 hex digest')


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
    """Imported meeting notes (context-and-knowledge §8). The notes are an
    artifact; attendees are person ids, empty until P6+ knows any people."""
    _ID = 'meeting'
    _TEXT = ('name', 'held_at')
    id: str
    workspace_id: str
    name: str
    held_at: str
    project_id: str = None
    notes_artifact_id: str = None
    imported_from: str = None
    attendees: tuple = ()

    def _check(self):
        if self.notes_artifact_id is not None and not _HEX64.fullmatch(self.notes_artifact_id):
            raise ValueError('Meeting.notes_artifact_id is an artifact sha256')


@entity
class Decision(Entity):
    _ID = 'decision'
    _TEXT = ('statement',)
    _CHOICES = {'status': ('active', 'superseded', 'reversed'),
                'source_kind': ('meeting', 'mission', 'conversation')}
    _REFS = {'supersedes_id': 'decision', 'knowledge_item_id': 'knowledge_item'}
    id: str
    workspace_id: str
    statement: str
    status: str = 'active'
    project_id: str = None
    supersedes_id: str = None
    rationale: str = ''
    decided_at: str = None
    source_kind: str = None
    source_ref: Ref = None
    # its mirror: "every decision is mirrored as a DECISION knowledge item"
    knowledge_item_id: str = None


# ── knowledge (domain-model §5) ─────────────────────────────────────────────

KNOWLEDGE_TYPES = ('FACT', 'DECISION', 'LESSON', 'PREFERENCE', 'STANDARD',
                   'ARCHITECTURE', 'REFERENCE', 'ENTITY')
#: A relation's confidence tier (domain-model §5.2): labels, not probabilities.
CONFIDENCE_TIERS = ('EXTRACTED', 'INFERRED', 'AMBIGUOUS')
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
    _REFS = {'supersedes_id': 'knowledge_item', 'superseded_by_id': 'knowledge_item',
             'route_decision_id': 'route_decision', 'context_package_id': 'context_package'}
    id: str
    workspace_id: str
    type: str
    title: str
    text: str = ''          # domain-model's `body`: that name is the row codec's column
    origin: str = 'inferred'
    project_id: str = None
    supersedes_id: str = None
    state: str = None
    constraint: dict = None
    # provenance (domain-model §5.1): what produced it, from what, and when. A
    # model-derived item also names the RouteDecision of the call (its harness,
    # account and model) and the ContextPackage the call was given (P6).
    source_kind: str = None
    source_ref: Ref = None
    observed_at: str = None
    confidence: float = None
    route_decision_id: str = None
    context_package_id: str = None
    valid_until: str = None
    superseded_by_id: str = None
    anchors: tuple = ()
    purged: bool = False

    def _check(self):
        if self.source_kind is not None and self.source_kind not in SOURCE_KINDS:
            raise ValueError('KnowledgeItem.source_kind must be one of %s' % (SOURCE_KINDS,))
        c = self.confidence
        if c is not None and not (isinstance(c, (int, float)) and not isinstance(c, bool)
                                  and 0 <= c <= 1):
            raise ValueError('KnowledgeItem.confidence is a number in 0..1')
        if len(self.text.encode('utf-8')) > BODY_MAX_BYTES:
            raise ValueError('knowledge text is over %d bytes; longer material is an '
                             'artifact' % BODY_MAX_BYTES)
        if self.constraint is not None:
            if self.type not in ('ARCHITECTURE', 'DECISION'):
                raise ValueError('only an ARCHITECTURE or DECISION item carries a constraint')
            check_constraint(self.constraint)


#: The checkable constraint kinds (context-and-knowledge §6). `doc_matches_code`
#: is accepted and reported as uncheckable: it has no deterministic definition.
CONSTRAINT_SPECS = {
    'forbid_dependency': {'from': str, 'to': str},
    'require_layering': {'layers': list},
    'module_exists': {'path': str},
    'framework_pinned': {'package': str, 'version': (str, type(None))},
    'doc_matches_code': {'doc': str, 'code': str},
}


def check_glob(pattern):
    """A repository-relative, `/`-separated pattern that cannot leave the
    repository: no drive, no leading `/`, no backslash, no `..` segment."""
    if not (isinstance(pattern, str) and pattern.strip()):
        raise ValueError('a path pattern is a non-empty string')
    if (pattern.startswith('/') or '\\' in pattern or re.match(r'[A-Za-z]:', pattern)
            or '..' in pattern.split('/')):
        raise ValueError('%r must be relative to the repository, with / separators and '
                         'no ..' % pattern)


def check_constraint(c):
    """`{kind, spec}`: a known kind and exactly its spec keys, typed."""
    if not isinstance(c, dict) or set(c) != {'kind', 'spec'}:
        raise ValueError('a constraint is {kind, spec}')
    want = CONSTRAINT_SPECS.get(c['kind'])
    if want is None:
        raise ValueError('unknown constraint kind %r (known: %s)'
                         % (c['kind'], ', '.join(CONSTRAINT_SPECS)))
    spec = c['spec']
    required = {k for k, t in want.items() if not (isinstance(t, tuple) and type(None) in t)}
    if not isinstance(spec, dict) or not required <= set(spec) <= set(want):
        raise ValueError('a %s spec has exactly %s' % (c['kind'], ', '.join(sorted(want))))
    for k, t in want.items():
        if k in spec and not isinstance(spec[k], t):
            raise ValueError('%s.%s has the wrong type' % (c['kind'], k))
    if c['kind'] == 'require_layering':
        if len(spec['layers']) < 2:
            raise ValueError('require_layering needs at least two layers')
        for g in spec['layers']:
            check_glob(g)
    for k in ('from', 'to', 'path', 'doc', 'code'):
        if k in spec:
            check_glob(spec[k])
    if c['kind'] == 'framework_pinned' and not spec['package'].strip():
        raise ValueError('framework_pinned needs a package name')


@entity
class Relation(Entity):
    """`(src_kind, src_id) -rel-> (dst_kind, dst_id)` (domain-model §5.2), flat
    so both ends are indexed columns. A relation never changes the state of
    either end: `contradicts` is evidence for a person to judge, not a
    supersession (P5's constraint conflicts are a separate, deterministic
    thing that needs no relation)."""
    _ID = 'relation'
    _TEXT = ('src_kind', 'src_id', 'dst_kind', 'dst_id')
    _CHOICES = {'rel': RELATIONS, 'confidence_tier': CONFIDENCE_TIERS}
    _REFS = {'route_decision_id': 'route_decision'}
    id: str
    src_kind: str
    src_id: str
    rel: str
    dst_kind: str
    dst_id: str
    confidence_tier: str = 'EXTRACTED'
    project_id: str = None
    source_kind: str = None
    source_ref: Ref = None
    route_decision_id: str = None
    valid_until: str = None

    def _check(self):
        if self.source_kind is not None and self.source_kind not in SOURCE_KINDS:
            raise ValueError('Relation.source_kind must be one of %s' % (SOURCE_KINDS,))


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
    _REFS = {'context_package_id': 'context_package'}
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
    # the package the mission's `context_ready` move recorded (P5)
    context_package_id: str = None
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
    """History (domain-model §7.8): promoting it into a PREFERENCE or LESSON is
    an explicit step that yields a CANDIDATE."""
    _ID = 'feedback'
    _CHOICES = {'signal': ('positive', 'negative', 'correction')}
    _REFS = {'principal_id': 'principal', 'promoted_knowledge_id': 'knowledge_item'}
    id: str
    subject: Ref
    signal: str
    text: str = ''
    workspace_id: str = None
    project_id: str = None
    principal_id: str = None
    promoted_knowledge_id: str = None


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


#: What a context package can be assembled for (p5-design-gate §3).
CONTEXT_SUBJECTS = ('mission', 'project')


@entity
class ContextPackage(Entity):
    """An assembled context package (context-and-knowledge §2.3). Immutable: no
    state machine and no command that edits it; a new assembly is a new row.
    Items are references with provenance and reasons, never copies of what they
    point at (the rendering is its first consumer's, P7)."""
    _ID = 'context_package'
    _CHOICES = {'subject_kind': CONTEXT_SUBJECTS}
    _NONNEG = ('as_of_seq',)
    id: str
    workspace_id: str
    subject_kind: str
    subject_id: str
    project_id: str = None
    as_of_seq: int = 0
    as_of_at: str = None
    query: str = ''
    levels: tuple = ()
    budget: dict = None
    scoring: dict = None
    items: tuple = ()
    excluded: tuple = ()
    conflicts: tuple = ()
    assumptions: tuple = ()
    missing_information: tuple = ()

    def _check(self):
        if not ids.is_id(self.subject_id, self.subject_kind):
            raise ValueError('ContextPackage.subject_id is not a %s id' % self.subject_kind)


# ── resources (domain-model §8) ─────────────────────────────────────────────

#: What one of Archeus's own calls is for (resource-router §3; ADR-0022).
CALL_PURPOSES = ('knowledge_extraction', 'lesson', 'generation', 'brain', 'planner')
#: A provider-terms answer (ADR-0021).
TERMS = ('unknown', 'permitted', 'refused')


@entity
class ProviderTerms(Entity):
    """The user's ADR-0021 answer for one harness: may Archeus make real
    automated headless calls on its accounts, and rotate across several
    subscriptions of it. `unknown` is the default and blocks exactly as
    `refused` does; only an explicit decision by the user changes it."""
    _CHOICES = {'headless': TERMS, 'rotation': TERMS}
    id: str                     # the harness id
    headless: str = 'unknown'
    rotation: str = 'unknown'
    note: str = ''

    def _check(self):
        if not _HARNESS_ID.fullmatch(self.id):
            raise ValueError('ProviderTerms.id is a harness id: %r' % self.id)

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
    """What Archeus itself consumed. A row for one of Archeus's own calls has
    no execution: it carries its `route_decision_id` instead (ADR-0022), and
    before P10 persists accounts, the account is the harness home it ran on."""
    _ID = 'usage_ledger'
    _REFS = {'execution_id': 'execution', 'account_id': 'account',
             'route_decision_id': 'route_decision'}
    _NONNEG = ('tokens_in', 'tokens_out', 'cache_read', 'cache_write')
    id: str
    execution_id: str = None
    route_decision_id: str = None
    account_id: str = None
    account_ref: str = None
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float = None

    def _check(self):
        if (self.execution_id is None) == (self.route_decision_id is None):
            raise ValueError('a usage row belongs to an execution or to a route decision, '
                             'exactly one')


@entity
class RouteDecision(Entity):
    """One routing decision (domain-model §8.6). For Archeus's own calls the
    subject is `archeus_call` with its purpose (ADR-0022) and, before P10, the
    pre-router election made it (`source`: what the call is about). `outcome`
    is written once, when the call ended; everything else never changes."""
    _ID = 'route_decision'
    _CHOICES = {'purpose': CALL_PURPOSES, 'decided_by': ('pre_router', 'router')}
    _REFS = {'context_package_id': 'context_package'}
    id: str
    subject: Ref
    selected: str = None          # None: no candidate survived (blocked / ask)
    explanation: str = ''
    purpose: str = None
    decided_by: str = None
    workspace_id: str = None
    project_id: str = None
    source: Ref = None
    requirements: dict = None
    candidates: tuple = ()
    account_ref: str = None
    model: str = None
    input_snapshot: dict = None
    context_package_id: str = None
    outcome: dict = None


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
