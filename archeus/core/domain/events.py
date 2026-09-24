"""The event type registry and the event envelope (api-and-realtime §3).

`TYPES` is the one declaration of what can happen: `(type, subject_kind,
visibility, notify_default, description)`. P1 registers the types the design
documents name; a phase that emits a new fact adds its row here first.

An `Event` is the envelope of api-and-realtime §3.1. `seq` is None until the P2
writer assigns it in the same transaction as the state change the event records
— this module builds and validates events, it never stores them, and the legacy
diagnostic log (`claude_sessions.events`) is not the source of truth for V1.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from . import ids
from .values import PRINCIPAL_SCOPES, Ref

TYPES = (
    # (type, subject_kind, visibility, notify_default, description)
    ('mission.created', 'mission', 'user', False, 'a mission row was created'),
    ('mission.state_changed', 'mission', 'user', False, 'a mission moved state (payload: from, to, reason)'),
    ('task.state_changed', 'task', 'user', False, 'a task moved state'),
    ('execution.intent', 'execution', 'system', False, 'an execution was committed before spawn'),
    ('execution.started', 'execution', 'user', False, 'its process exists (pid, create_time)'),
    ('execution.progress', 'execution', 'system', False, 'coalesced stream progress, at most 1/s'),
    ('execution.ended', 'execution', 'user', False, 'the process exited (payload: exit_reason)'),
    ('approval.requested', 'approval', 'user', True, 'an action or plan needs a decision'),
    ('review.requested', 'review', 'user', False, 'a mission result awaits review'),
    ('feedback.received', 'feedback', 'user', False, 'the user gave feedback'),
    ('decision.created', 'decision', 'user', False, 'a decision was recorded'),
    ('meeting.imported', 'meeting', 'user', False, 'meeting notes were imported'),
    ('message.created', 'message', 'user', False, 'a conversation message was written'),
    ('project.changed', 'project', 'user', False, 'repo HEAD moved or files changed (debounced)'),
    ('repository.file_added', 'repository', 'user', False, 'a file appeared in a repository'),
    ('repository.model_added', 'repository', 'user', False, 'inspection found a new model/schema file'),
    ('catalog.model_released', 'model', 'user', False, 'a provider released a new model'),
    ('account.health_changed', 'account', 'user', True, 'an account moved health state'),
    ('harness.state_changed', 'harness', 'user', False, 'a harness appeared, vanished or broke'),
    ('node.state_changed', 'execution_node', 'user', False, 'a node went online/grace/offline'),
    ('device.stream_opened', 'device', 'system', False, 'a device opened the event stream'),
    ('device.stream_closed', 'device', 'system', False, 'a device closed the event stream'),
    ('principal.created', 'principal', 'system', False, 'an actor was registered'),
    ('legacy.worklog', 'project', 'system', False, 'a legacy worklog entry, imported as history'),
)

REGISTRY = {row[0]: row for row in TYPES}
assert len(REGISTRY) == len(TYPES), 'an event type is registered twice'

VISIBILITIES = ('user', 'system')
MAX_CAUSE_CHAIN = 16


def now_iso():
    """UTC, millisecond precision, `Z` suffix — the envelope's `at` format."""
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


@dataclass(frozen=True, kw_only=True)
class Event:
    id: str
    type: str
    at: str
    # The principal that caused this (domain-model §9.5 `actor_principal_id`):
    # `actor.id` is always a `prn_…` id and `actor.kind` that principal's kind.
    # An execution acts through its own principal; the execution id itself
    # (`exe_…`) is provenance, and belongs in `subject`, `cause_chain` or the
    # payload — never here.
    actor: Ref
    subject: Ref
    workspace: str = ids.GLOBAL_WORKSPACE
    project: str = None
    cause_chain: tuple = ()
    visibility: str = None      # None -> the registry's default for the type
    payload: dict = None
    seq: int = None             # assigned by the P2 writer; the SSE cursor

    def __post_init__(self):
        for f, cls in (('actor', Ref), ('subject', Ref)):
            if isinstance(getattr(self, f), dict):
                object.__setattr__(self, f, cls(**getattr(self, f)))
        object.__setattr__(self, 'cause_chain', tuple(self.cause_chain))
        if self.payload is None:
            object.__setattr__(self, 'payload', {})
        row = REGISTRY.get(self.type)
        if row is None:
            raise ValueError('unregistered event type: %r' % (self.type,))
        if self.visibility is None:
            object.__setattr__(self, 'visibility', row[2])
        problems = []
        if not ids.is_ulid(self.id):
            problems.append('id is not a ULID')
        if self.subject.kind != row[1]:
            problems.append('%s is about a %s, not a %s' % (self.type, row[1], self.subject.kind))
        if self.actor.kind not in PRINCIPAL_SCOPES:
            problems.append('actor kind %r is not a principal kind' % self.actor.kind)
        if not ids.is_id(self.actor.id, 'principal'):
            problems.append('actor id %r is not a principal id' % self.actor.id)
        if self.visibility not in VISIBILITIES:
            problems.append('visibility must be user or system')
        if len(self.cause_chain) > MAX_CAUSE_CHAIN:
            problems.append('cause_chain is longer than %d' % MAX_CAUSE_CHAIN)
        if not all(ids.is_ulid(c) for c in self.cause_chain):
            problems.append('cause_chain holds event ids (ULIDs)')
        if not ids.is_id(self.workspace, 'workspace'):
            problems.append('workspace is not a workspace id')
        if self.project is not None and not ids.is_id(self.project, 'project'):
            problems.append('project is not a project id')
        if self.seq is not None and not (isinstance(self.seq, int) and self.seq > 0):
            problems.append('seq is a positive integer')
        if not isinstance(self.payload, dict):
            problems.append('payload is a JSON object')
        else:
            try:
                json.dumps(self.payload)
            except (TypeError, ValueError):
                problems.append('payload is not JSON-serialisable')
        if problems:
            raise ValueError('invalid %s event: %s' % (self.type, '; '.join(problems)))

    def to_envelope(self):
        """The wire shape of api-and-realtime §3.1."""
        return {
            'seq': self.seq, 'id': self.id, 'type': self.type, 'at': self.at,
            'actor': {'kind': self.actor.kind, 'id': self.actor.id},
            'cause_chain': list(self.cause_chain),
            'subject': {'kind': self.subject.kind, 'id': self.subject.id},
            'scope': {'workspace': self.workspace, 'project': self.project},
            'visibility': self.visibility, 'payload': self.payload,
        }

    @classmethod
    def from_envelope(cls, env):
        scope = env.get('scope') or {}
        return cls(seq=env.get('seq'), id=env['id'], type=env['type'], at=env['at'],
                   actor=env['actor'], subject=env['subject'],
                   workspace=scope.get('workspace', ids.GLOBAL_WORKSPACE),
                   project=scope.get('project'), cause_chain=env.get('cause_chain', ()),
                   visibility=env.get('visibility'), payload=env.get('payload'))


def new_event(type, subject, actor, payload=None, **kw):
    """An event with a fresh ULID and the current time (both overridable)."""
    kw.setdefault('id', ids.new_ulid())
    kw.setdefault('at', now_iso())
    return Event(type=type, subject=subject, actor=actor, payload=payload, **kw)
