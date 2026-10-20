"""Serve the later-V2 lab on loopback for the measurement scripts.

Prototype tooling, not product code. Binds 127.0.0.1 on an ephemeral port and serves
exactly two read-only roots: `prototypes/` (both labs, so later-V2 pages reuse the V2-U0
engine and figures as they are) and the V1 token stylesheet, so every prototype is judged
on the ground it would extend rather than on a copy of it.
"""
import functools
import http.server
import os
import posixpath
import threading
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(PROTO)
ROOTS = {'proto': PROTO, 'v1styles': os.path.join(REPO, 'clients', 'app', 'src', 'styles')}
RESULTS = os.path.join(os.path.dirname(HERE), 'results')


class _H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, path):
        parts = [p for p in posixpath.normpath(urllib.parse.unquote(path.split('?')[0])).split('/') if p]
        if not parts or parts[0] not in ROOTS or any(p in ('..', '.') for p in parts):
            return os.path.join(PROTO, '__missing__')
        return os.path.join(ROOTS[parts[0]], *parts[1:])


def serve():
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(_H))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return 'http://127.0.0.1:%d/proto/v2-later/lab/' % srv.server_address[1], srv


def results(*parts):
    p = os.path.join(RESULTS, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p
