from copy import deepcopy

from ..homes import public_value, scrub_text


def system_value(value, homes, *, authored=(), path_keys=(), _path=()):
    # Paths describe content provenance; actor identity and field names alone do not.
    if _path in authored:
        return deepcopy(value)
    if isinstance(value, dict):
        return {k: system_value(v, homes, authored=authored, path_keys=path_keys,
                                _path=(*_path, k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [system_value(v, homes, authored=authored, path_keys=path_keys,
                             _path=_path) for v in value]
    projected = public_value(value, homes, path_keys=path_keys,
                             _key=_path[-1] if _path else None)
    return scrub_text(projected, homes)


#: Authored payload leaves of an event, by type (T-144 O-8/O-10): what the user
#: typed, kept byte for byte (owner 2026-10-25: model-written text is scrubbed).
#: Provenance decides, never the event's actor:
#: every other string of every event is system-owned and gets the fallback scrub.
EVENT_AUTHORED = {
    'mission.created': (('title',),),
    'mission.updated': (('added', 'requirements'), ('added', 'constraints')),
    'idea.created': (('title',),),
    'feedback.received': tuple(('promoted', k) for k in ('title', 'text', 'anchors', 'constraint')),
    'meeting.imported': (('name',),),
    'automation.created': (('name',), ('trigger',)),
    'project.created': (('name',),),
    'repository.registered': (('path',),),
    'repository.model_added': (('path',),),
    'repository.file_added': (('path',),),
    'policy_rule.created': (('before',), ('after',)),
    'policy_rule.retired': (('before',),),
}
PATH_KEYS = ('account_ref', 'ref', 'home_ref', 'home_key')


def public_event(envelope, homes):
    """The envelope with its payload projected; the envelope is not touched."""
    return dict(envelope, payload=system_value(
        envelope['payload'], homes, path_keys=PATH_KEYS,
        authored=EVENT_AUTHORED.get(envelope['type'], ())))


def public_output(out, homes):
    """An execution's output read with every event string scrubbed: agent text
    is an approved scrub lane, and it is scrubbed before any truncation."""
    return dict(out, events=system_value(out['events'], homes, path_keys=PATH_KEYS))


def public_context(body, homes):
    return system_value(body, homes, authored=(('query',),))
