"""Reading a JSON state file without destroying it.

Seven modules had each written the same three lines: open, `json.load`,
`except Exception: return {}`. That silently turns a corrupt file into the
default value — and every one of these files is then written back, so the
first truncated write is also the last time the data exists. The memory graph,
the usage cache and the settings file were all one interrupted write away from
being erased with no trace.

A file that is absent is a normal empty state. A file that is present and
unparseable is a fault: it is moved aside as `<name>.corrupt-<ts>` and
reported, never overwritten in place.
"""

import json
import os
import time

__all__ = ['load', 'save']

#: paths whose most recent read found a corrupt file, and where it was moved
last_corruption = {}


def load(path, default=None, *, expect=dict, quarantine=True):
    """Parsed JSON from *path*, or a copy of *default* when absent or corrupt.

    *expect* is the type the caller relies on — a file holding a list where a
    dict was expected is as unusable as a truncated one, and is treated the
    same way.
    """
    if default is None:
        default = expect()
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except FileNotFoundError:
        return _copy(default)
    except OSError:
        return _copy(default)
    except Exception:
        if quarantine:
            _quarantine(path)
        return _copy(default)
    if expect is not None and not isinstance(data, expect):
        if quarantine:
            _quarantine(path)
        return _copy(default)
    last_corruption.pop(os.path.abspath(path), None)
    return data


def save(path, data):
    # lazy: config.load_settings calls load() at import time, so a module-level
    # import here is a cycle
    from . import config as _c
    return _c.write_json_atomic(path, data)


def _copy(default):
    if isinstance(default, dict):
        return dict(default)
    if isinstance(default, list):
        return list(default)
    return default


def _quarantine(path):
    dest = '%s.corrupt-%d' % (path, int(time.time()))
    try:
        os.replace(path, dest)
    except OSError:
        dest = ''
    last_corruption[os.path.abspath(path)] = dest
    # `last_corruption` is in-memory, so the one thing a user needs to know
    # about — a state file moved aside — used to die with the process.
    try:
        from . import events
        events.record('jsonstore', 'moved a corrupt state file aside',
                      detail='%s -> %s' % (path, dest or '(move failed)'))
    except Exception:
        pass
    return dest
