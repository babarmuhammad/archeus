"""Settings-source opt-ins (P20 D6; ADR-0049 §2).

An execution excludes what its settings sources would load (the account
home's, the project's and the local settings: hooks, plugins, skills, MCP
servers, permissions) unless the account or the project it runs for has opted
that source, plugin or MCP server back in. This module holds the one command
that records an opt-in or an opt-out, and the reads: the list (Control →
Accounts, `archeus executions opt-ins`) and what applies to one execution.

The command is the user's: a user device, through an `admin` route (the
`data_class` pattern of ADR-0035). Nothing else writes an opt-in, and nothing
here runs, spawns or reads a settings file — the harness does that, at spawn.
"""

from ..domain import entities, ids
from ..domain.events import new_event
from ..domain.values import Ref
from . import authorization as A
from . import lifecycle
from .queries import view


def _owner(tx, owner_id):
    """('account' | 'project', its id field, the row) for an owner id."""
    for kind, cls in (('account', entities.Account), ('project', entities.Project)):
        if ids.is_id(owner_id, kind):
            return kind, lifecycle.load(tx, cls, owner_id)
    raise ValueError('an opt-in belongs to an account or a project: %r is neither' % (owner_id,))


def _find(conn_or_tx, owner, owner_id, kind, name):
    got = conn_or_tx.where(entities.OptIn, **{owner + '_id': owner_id, 'kind': kind,
                                              'name': name})
    return got[0] if got else None


def set_opt_in(tx, *, actor, owner_id, kind, name, opted_in, expected_version=None,
               digest=None):
    """Opt *name* of *kind* in (or out) for every execution of the account or
    project *owner_id*. The first opt-in inserts the row; every later change is
    the same row's next version. Asking for what already holds writes nothing
    and says so (`changed` False); an opt-out of what was never opted in too.
    A project's MCP opt-in pins *digest*, the sha256 of its .mcp.json: a new
    approval (a new digest) is a change of the same row."""
    if actor.kind != 'user_device':
        raise A.NotPermitted('only a user device opts a settings source, plugin or MCP '
                             'server in or out (ADR-0049)')
    if opted_in and not isinstance(opted_in, bool):
        raise ValueError('OptIn.opted_in is a boolean')
    owner, orow = _owner(tx, owner_id)
    pinned = owner == 'project' and kind == 'mcp'
    if digest is not None and not pinned:
        raise ValueError('only a project MCP opt-in pins a digest')
    row = _find(tx, owner, owner_id, kind, name)
    if row is None:
        if not opted_in:
            return {'opt_in': None, 'changed': False}
        o = entities.OptIn(id=ids.new_id('opt_in'), kind=kind, name=name, opted_in=True,
                           digest=digest, **{owner + '_id': owner_id})
        row = tx.insert(o, actor=actor)
    elif row.entity.opted_in == opted_in and (not opted_in or row.entity.digest == digest):
        if expected_version is not None and expected_version != row.version:
            raise lifecycle.VersionConflict(row.entity.id, expected_version, row.version)
        return {'opt_in': view(row), 'changed': False}
    else:
        fields = {'opted_in': opted_in, **({'digest': digest} if opted_in else {})}
        row = tx.update(entities.OptIn, row.entity.id, fields, actor=actor,
                        expected_version=expected_version)
    scope = {}
    if owner == 'project':
        scope = {'workspace': orow.entity.workspace_id, 'project': owner_id}
    tx.append(new_event('opt_in.changed', Ref('opt_in', row.entity.id), actor, payload={
        'owner': owner, 'owner_id': owner_id, 'kind': kind, 'name': name,
        'opted_in': opted_in, 'version': row.version}, **scope))
    return {'opt_in': view(row), 'changed': True}


def listing(conn):
    """Every opt-in row, in and out, with its owner named (read-only)."""
    from ...infra.db import rows
    return [dict(view(r), owner=r.entity.owner,
                 owner_id=r.entity.account_id or r.entity.project_id)
            for r in rows.where(conn, entities.OptIn)]


def _applying(conn, account_id, project_id):
    """The opted-in rows of exactly this account and exactly this project."""
    from ...infra.db import rows
    return [(owner, r.entity) for owner, oid in (('account', account_id), ('project', project_id))
            if oid is not None
            for r in rows.where(conn, entities.OptIn, **{owner + '_id': oid})
            if r.entity.opted_in]


def effective(conn, *, account_id, project_id):
    """What one execution may load: the opted-in rows of exactly its account
    and exactly its project, as (owner, kind, name). Another account's or
    project's opt-in never applies."""
    return tuple(sorted((owner, e.kind, e.name) for owner, e in
                        _applying(conn, account_id, project_id)))


def pins(conn, *, account_id, project_id):
    """The (owner, kind, name, digest) of each opt-in of this execution that pins
    a digest. An opt-in that pins none (written before the pin) is absent: the
    harness treats it as not approved."""
    return tuple(sorted((owner, e.kind, e.name, e.digest) for owner, e in
                        _applying(conn, account_id, project_id) if e.digest is not None))
