"""An execution's output, read for a client (p16-design-gate D4; frozen to P16
by P3.5b D8 and P11 §14): the normalised events the harness adapter reads from
the process's stream file, from a byte offset, every string passed through the
one redactor. A read of the stream file, never a write; nothing here moves the
execution or trusts what the output says."""

import json
import os

from ...harnesses import base
from ...infra.paths import ExecPaths
from ..redact import redact

#: The most events one answer carries: a client tails, it does not archive.
MAX_EVENTS = 1000
#: The most stream bytes one answer reads: the newest whole lines, so a long
#: stream costs a tail's memory, not its own (a read from 0 skips the older part).
MAX_BYTES = 4 << 20


def _window(path, offset):
    """(start, cut): *offset*, or the first line start within MAX_BYTES of the end."""
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return offset, False
    if size - offset <= MAX_BYTES:
        return offset, False
    start = size - MAX_BYTES
    with open(path, 'rb') as f:
        f.seek(start - 1)
        f.readline(base.MAX_LINE)       # the rest of a line cut in two (or just the newline before start)
        return f.tell(), True


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
    start, cut = _window(ExecPaths(execution.id).stream, offset)
    snap = adapter.inspect(handle, start)
    events = [json.loads(redact(json.dumps(e, ensure_ascii=False))) for e in snap.events[-MAX_EVENTS:]]
    return dict(out, events=events, truncated=cut or len(snap.events) > MAX_EVENTS,
                next_offset=snap.offset, available=True)
