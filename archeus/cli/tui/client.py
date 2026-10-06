"""The TUI's transport to Core (p17-design-gate A3): HTTP and the event stream,
stdlib only. It invents no API semantics: a read returns Core's answer and the
event head it was read at, a refusal keeps Core's status, code and detail, and a
frame is handed on as it arrived. Loopback only: the address is 127.0.0.1 and
the port the discovery file names, and the token goes nowhere else.
"""

import json
import socket
import threading
import urllib.error
import urllib.request

LOOPBACK = '127.0.0.1'
STREAM_PATH = '/v1/events/stream'
#: a marker `events()` yields when the stream answers, never a frame Core sends
OPENED = ' opened'
TIMEOUT_S = 10
#: longer than Core's heartbeat (15 s), so a quiet stream is not a lost one
STREAM_TIMEOUT_S = 45


class CoreError(Exception):
    """Core refused, or could not be reached (status 0, code `network`)."""

    def __init__(self, status, code, detail=None):
        super().__init__('%s %s' % (status, code))
        self.status, self.code, self.detail = status, code, detail or {}

    def refusal(self):
        return {'status': self.status, 'code': self.code, 'detail': self.detail}


def _error(e):
    try:
        body = json.loads(e.read() or b'{}')
    except ValueError:
        body = {}
    return CoreError(e.code, body.get('error') or 'http_%d' % e.code, body.get('detail'))


class Core:
    """One Core on this computer, reached with the local token."""

    def __init__(self, port, token):
        self.base = 'http://%s:%d' % (LOOPBACK, port)
        self._token = token

    @classmethod
    def local(cls):
        """(Core, None) for the running Core, or (None, why) — the TUI never
        starts Core itself (A4)."""
        from ...infra import discovery
        state, info = discovery.discover()
        if state == 'not_running':
            return None, 'not_running'
        if state == 'unreadable':
            return None, 'unreadable'
        token = discovery.read_local_token()
        if token is None:
            return None, 'no_token'
        return cls(info['port'], token), None

    def _open(self, method, path, body=None, headers=None, timeout=TIMEOUT_S):
        data = json.dumps(body).encode('utf-8') if method == 'POST' else None
        h = {'Authorization': 'Bearer ' + self._token, 'Accept': 'application/json'}
        if data is not None:
            h['Content-Type'] = 'application/json'
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            raise _error(e) from None
        except (urllib.error.URLError, OSError) as e:
            raise CoreError(0, 'network', {'why': type(e).__name__}) from None

    def get(self, path):
        """(Core's answer, the event head it was read at)."""
        with self._open('GET', path) as r:
            seq = r.headers.get('X-Archeus-Seq')
            return json.loads(r.read() or b'null'), int(seq) if seq else None

    def post(self, path, body):
        with self._open('POST', path, body) as r:
            return json.loads(r.read() or b'null')

    def events(self, last_id=None):
        """The raw event stream: yields frames {id?, event, data?}; a comment line
        is a heartbeat. Raises CoreError for a refused stream (401, 410)."""
        headers = {'Accept': 'text/event-stream'}
        if last_id is not None:
            headers['Last-Event-ID'] = str(last_id)
        with self._open('GET', STREAM_PATH, headers=headers, timeout=STREAM_TIMEOUT_S) as r:
            yield {'event': OPENED}            # the stream answered 200, before any frame
            frame, seen, comment = {'event': 'message'}, False, False
            for raw in r:
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                if line:
                    if line.startswith(':'):
                        comment = True
                        continue
                    k, _, v = line.partition(': ')
                    seen = True
                    if k == 'id':
                        frame['id'] = int(v)
                    elif k == 'event':
                        frame['event'] = v
                    elif k == 'data':
                        frame['data'] = json.loads(v)
                    continue
                if seen:
                    yield frame
                elif comment:
                    yield {'event': 'heartbeat'}
                frame, seen, comment = {'event': 'message'}, False, False


class Stream(threading.Thread):
    """Keeps the one event stream open (the SPA's `lead`, api/stream.ts) and
    posts what happens to *out*: ('signal', name) for the connection machine,
    ('frame', frame) for invalidation. Reconnects with Last-Event-ID; a 410 or a
    `cursor_expired` frame means re-read everything (a resync)."""

    def __init__(self, core, out):
        super().__init__(daemon=True, name='archeus-tui-stream')
        self.core, self.out = core, out
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        last, delay = None, 0.25
        while not self._stop.is_set():
            try:
                for f in self.core.events(last):
                    if self._stop.is_set():
                        return
                    if f['event'] == OPENED:
                        delay = 0.25
                        self.out.put(('signal', 'stream_open'))
                    elif f['event'] == 'cursor_expired':
                        last = None
                        self.out.put(('signal', 'resync'))
                    elif f['event'] != 'shutdown':
                        if f.get('id') is not None:
                            last = f['id']
                        self.out.put(('frame', f))
                        self.out.put(('signal', 'frame'))
            except CoreError as e:
                if e.status == 401:
                    self.out.put(('signal', 'unauthorized'))
                    return
                if e.status == 410:
                    last = None
                    self.out.put(('signal', 'resync'))
            except (OSError, socket.timeout, ValueError):
                pass
            if self._stop.is_set():
                return
            self.out.put(('signal', 'stream_lost'))
            self._stop.wait(delay)
            delay = min(delay * 2, 8.0)
