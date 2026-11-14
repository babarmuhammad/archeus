"""Claude Code UserPromptSubmit / Notification / Stop / SessionEnd hook: what is this session doing.

Writes `<config dir>/archeus-status/<session id>.json` ({state, ts}) so the
session list can mark a session working, waiting for you, or idle. Stdlib only
and no archeus imports: it runs on every turn. Never blocks: exit 0 always.
SessionEnd deletes the session's file.

Installed by archeus (hooks.install_status_hook), opt-in from the hooks menu.
"""

import contextlib
import json
import os
import re
import sys
import time

DIRNAME = 'archeus-status'
WORKING, NEEDS_INPUT, IDLE = 'working', 'needs_input', 'idle'

#: a session killed mid-turn never writes its Stop, so a state this old is a ghost
TTL = 6 * 3600

_STATE_OF = {'UserPromptSubmit': WORKING, 'Stop': IDLE}
_SID = re.compile(r'[\w-]+')


def _cfgdir(data):
    tp = data.get('transcript_path') or ''
    if os.path.isabs(tp) and os.path.basename(os.path.dirname(os.path.dirname(tp))) == 'projects':
        return os.path.dirname(os.path.dirname(os.path.dirname(tp)))
    return os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(os.path.expanduser('~'), '.claude')


def _state(data):
    event = data.get('hook_event_name')
    if event != 'Notification':
        return _STATE_OF.get(event)
    kind = data.get('notification_type')
    if kind == 'auth_success':
        return None
    return IDLE if kind == 'idle_prompt' else NEEDS_INPUT


def handle(data):
    sid = str(data.get('session_id') or '')
    ended = data.get('hook_event_name') == 'SessionEnd'
    state = _state(data)
    if not (state or ended) or not _SID.fullmatch(sid):
        return
    d = os.path.join(_cfgdir(data), DIRNAME)
    path = os.path.join(d, f'{sid}.json')
    if ended:
        with contextlib.suppress(OSError):
            os.remove(path)
        return
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f'{sid}.{os.getpid()}.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'state': state, 'ts': time.time()}, f)
    os.replace(tmp, path)


def read_all(cfgdir):
    """{session id: state} for every fresh state file under one config dir."""
    d = os.path.join(cfgdir, DIRNAME)
    out = {}
    try:
        names = os.listdir(d)
    except OSError:
        return out
    now = time.time()
    for n in names:
        if not n.endswith('.json'):
            continue
        try:
            with open(os.path.join(d, n), encoding='utf-8') as f:
                v = json.load(f)
            if now - float(v['ts']) >= TTL:
                os.remove(os.path.join(d, n))
            elif v['state'] in (WORKING, NEEDS_INPUT, IDLE):
                out[n[:-5]] = v['state']
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def main():
    try:
        data = json.load(sys.stdin)
        if isinstance(data, dict):
            handle(data)
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
