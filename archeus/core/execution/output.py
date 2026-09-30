"""An execution's output, read for a client (p16-design-gate D4; frozen to P16
by P3.5b D8 and P11 §14): the normalised events the harness adapter reads from
the process's stream file, from a byte offset, every string passed through the
one redactor. A read of the stream file, never a write; nothing here moves the
execution or trusts what the output says."""

import json

from ...harnesses import base
from ...infra.paths import ExecPaths
from ..redact import redact

#: The most events one answer carries: a client tails, it does not archive.
MAX_EVENTS = 1000


def read(execution, adapter, offset=0):
    """`{events, offset, next_offset, truncated, available}` for *execution*
    (an Execution entity) from byte *offset*; no process yet, or no adapter
    for its harness, is an empty, `available: false` answer."""
    out = {'execution_id': execution.id, 'offset': offset, 'next_offset': offset,
           'events': [], 'truncated': False, 'available': False}
    if execution.pid is None or adapter is None:
        return out
    handle = base.ProcessHandle(execution.id, execution.pid, execution.create_time,
                                ExecPaths(execution.id).dir)
    snap = adapter.inspect(handle, offset)
    # ponytail: the adapter reads everything after the offset; a byte cap is the
    # upgrade if a client ever asks for a long history instead of a tail
    events = [json.loads(redact(json.dumps(e, ensure_ascii=False))) for e in snap.events]
    return dict(out, events=events[-MAX_EVENTS:], truncated=len(events) > MAX_EVENTS,
                next_offset=snap.offset, available=True)
