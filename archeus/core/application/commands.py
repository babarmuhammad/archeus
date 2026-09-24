"""Commands: `command(tx, **kwargs) -> response`, run by the writer.

Each writes its rows and the events recording them through the `Tx` it is
given, so both commit together. The response is what the API will return for
the command: the new version and the resulting event seq (api-and-realtime §1).
"""

from ..domain import entities, ids
from ..domain.events import new_event
from ..domain.values import Ref


def register_principal(tx, *, kind, scopes=()):
    """A new actor, which is its own actor on its `principal.created` event.

    P2 BOOTSTRAP, not the security model: the only caller is the in-process
    client registering itself on first use, so persistence can run before any
    auth exists. Nothing here checks who may register a principal or with which
    scopes — that belongs to the auth layer (P3.5 local bootstrap, pairing) and
    policy (P9), which will gate this command rather than trust its caller."""
    p = entities.Principal(id=ids.new_id('principal'), kind=kind, scopes=tuple(scopes))
    actor = Ref(kind, p.id)
    tx.insert(p, actor=actor)
    e = tx.append(new_event('principal.created', Ref('principal', p.id), actor,
                            payload={'kind': kind, 'scopes': list(p.scopes)}))
    return {'id': p.id, 'version': 1, 'seq': e.seq}


def create_mission(tx, *, actor, title, objective, project_id=None,
                   workspace_id=ids.GLOBAL_WORKSPACE):
    m = entities.Mission(id=ids.new_id('mission'), workspace_id=workspace_id,
                         project_id=project_id, title=title, objective=objective)
    row = tx.insert(m, actor=actor)
    e = tx.append(new_event('mission.created', Ref('mission', m.id), actor,
                            payload={'title': title}, workspace=workspace_id,
                            project=project_id))
    return {'id': m.id, 'state': m.state, 'version': row.version, 'seq': e.seq}
