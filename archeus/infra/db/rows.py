"""Entity <-> row: the one codec every write and every read shares.

An entity table holds `id`, the fields promoted to columns, the row metadata
(`META`) and `body` — every other field as JSON. Which fields are promoted is
read from the table itself (`PRAGMA table_info`), so a migration that adds a
column promotes that field with no code change here. A field is stored exactly
once: in its column or in `body`, never both, so the two cannot disagree.
"""

import json
from dataclasses import dataclass, fields

from ...core.domain import entities

#: Entity class -> table. The one declaration of which entities the current
#: schema persists; a phase that persists a new entity adds its row here and its
#: table in a migration.
TABLES = {
    entities.Principal: 'principals',
    entities.Device: 'devices',
    entities.Mission: 'missions',
}

#: Row metadata, never entity fields: optimistic-concurrency version, timestamps,
#: and the audit pair (the acting principal's id).
META = ('version', 'created_at', 'updated_at', 'created_by', 'updated_by')


@dataclass(frozen=True)
class Row:
    entity: object
    version: int
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str


def table(cls):
    try:
        return TABLES[cls]
    except KeyError:
        raise LookupError('%s has no table in the current schema' % cls.__name__) from None


def columns(conn, name):
    return tuple(r[1] for r in conn.execute('PRAGMA table_info(%s)' % name))


def encode(entity, cols):
    """(promoted {column: value}, body JSON) for an entity."""
    data = entity.to_dict()
    clash = set(data) & (set(META) | {'body'})
    if clash:
        raise ValueError('%s fields collide with row metadata: %s'
                         % (type(entity).__name__, sorted(clash)))
    promoted = {c: data.pop(c) for c in cols if c in data}
    return promoted, json.dumps(data, sort_keys=True)


def decode(cls, record):
    names = {f.name for f in fields(cls)}
    data = json.loads(record['body'])
    data.update({k: record[k] for k in record.keys() if k in names})
    return Row(cls.from_dict(data), *(record[m] for m in META))


def get(conn, cls, entity_id):
    """The current row of one entity, or None."""
    record = conn.execute('SELECT * FROM %s WHERE id = ?' % table(cls),
                          (entity_id,)).fetchone()
    return None if record is None else decode(cls, record)
