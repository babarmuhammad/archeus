"""The event stream (api-and-realtime §4, p3.5b design gate §6).

    id: <seq>\\nevent: <type>\\ndata: {"subject": …, "scope": …}\\n\\n

Identities only: a client re-queries what it shows (ADR-0009), so a frame never
carries a payload. Replay is exactly `seq > cursor`, in order, read in pages of
at most 1000 from one short snapshot each; no transaction is held while a
stream waits. A cursor that cannot be honoured is refused BEFORE the 200 (400
malformed, 410 pruned/ahead); one that expires mid-stream gets an explicit
`cursor_expired` frame and the stream closes — it never skips silently.

Each stream writes its own socket from its own thread, so a slow client blocks
only itself; the writer never waits on a reader, it only notifies
(`Writer.wait_commit`). Streams have their own bounded pool (8, at most 2 per
device) apart from requests, so they cannot starve commands.
"""

import json
import socket
import threading
import time

from ..core.application import queries
from ..infra.eventlog import outbox
from . import auth
from .routes import Refused

MAX_STREAMS = 8
PER_DEVICE = 2


class TooManyStreams(RuntimeError):
    pass


class _Stream:
    def __init__(self, device_id):
        self.device_id = device_id
        self.closing = threading.Event()
        self.done = threading.Event()


def frame(event):
    data = json.dumps({'subject': {'kind': event.subject.kind, 'id': event.subject.id},
                       'scope': {'workspace': event.workspace, 'project': event.project}},
                      separators=(',', ':'))
    return ('id: %d\nevent: %s\ndata: %s\n\n' % (event.seq, event.type, data)).encode('utf-8')


class Streams:
    def __init__(self, db, *, heartbeat_s=15.0, stopping=lambda: False):
        self.db = db
        self.heartbeat_s = heartbeat_s
        self.stopping = stopping
        self._lock = threading.Lock()
        self._open = []

    def count(self):
        with self._lock:
            return len(self._open)

    def _register(self, device_id):
        with self._lock:
            if (len(self._open) >= MAX_STREAMS
                    or sum(s.device_id == device_id for s in self._open) >= PER_DEVICE):
                raise TooManyStreams()
            s = _Stream(device_id)
            self._open.append(s)
            return s

    def _unregister(self, s):
        with self._lock:
            if s in self._open:
                self._open.remove(s)
        s.done.set()

    def _close(self, match, timeout):
        with self._lock:
            targets = [s for s in self._open if match(s)]
        for s in targets:
            s.closing.set()
        self.db.writer.wake()
        for s in targets:
            s.done.wait(timeout)

    def close_device(self, device_id, timeout=5.0):
        """Close every stream of *device_id* and return once they are closed."""
        self._close(lambda s: s.device_id == device_id, timeout)

    def close_all(self, timeout=5.0):
        self._close(lambda s: True, timeout)

    def _page(self, cursor):
        with self.db.read() as conn:
            return outbox.events_after(conn, cursor, limit=outbox.MAX_LIMIT)

    def _still_valid(self, presented_hash):
        with self.db.read() as conn:
            return auth.live(queries.credential(conn, presented_hash), presented_hash)

    def serve(self, req, cursor):
        """Validate the cursor, then stream until the client goes, the device is
        revoked, or Core stops. Returns None: the response is already written."""
        with self.db.read() as conn:
            head = outbox.head(conn)
            if cursor is not None:
                outbox.events_after(conn, cursor, limit=1)     # 400 / 410 before the 200
        cursor = head if cursor is None else cursor
        try:
            stream = self._register(req.principal['device_id'])
        except TooManyStreams:
            raise Refused(429, 'too_many_streams') from None
        try:
            req.start_stream()
            self._loop(req, stream, cursor)
        finally:
            try:
                req.connection.shutdown(socket.SHUT_RDWR)   # EOF reaches the client now
            except OSError:
                pass
            self._unregister(stream)
        return None

    def _loop(self, req, stream, cursor):
        writer = self.db.writer
        last_write = time.monotonic()
        while True:
            if self.stopping():
                req.write(b'event: shutdown\ndata: {}\n\n')
                return
            if stream.closing.is_set():
                return
            seen = writer.commit_count
            while True:
                try:
                    page = self._page(cursor)
                except outbox.CursorExpired as e:
                    req.write(('event: cursor_expired\ndata: %s\n\n' % json.dumps(
                        {'reason': e.reason, 'floor': e.floor, 'head': e.head})).encode())
                    return
                if page:
                    req.write(b''.join(frame(e) for e in page))
                    cursor = page[-1].seq
                    last_write = time.monotonic()
                if len(page) < outbox.MAX_LIMIT:
                    break
            wait = self.heartbeat_s - (time.monotonic() - last_write)
            if wait <= 0:
                req.write(b': hb\n\n')
                last_write = time.monotonic()
                wait = self.heartbeat_s
            writer.wait_commit(seen, wait,
                               until=lambda: stream.closing.is_set() or self.stopping())
            # a revocation made any other way still closes within one wake
            if not self._still_valid(req.token_hash):
                return
