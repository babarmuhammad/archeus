"""Translating gateway — speak Anthropic Messages to `claude`, OpenAI Chat
Completions upstream.

Most local model servers and every OpenAI-compatible host serve
`/v1/chat/completions` and nothing else. Claude Code only speaks
`POST /v1/messages`, so those backends are unreachable no matter how the base
URL is set. This module is the adapter.

It is a SIBLING of failover.py, never a mode of it. failover.py's contract is
that it forwards bytes verbatim and only ever rewrites a request's `model`;
this one owns response framing, because translating is exactly re-serializing.
Putting both behaviours in one module would make that contract unenforceable —
`test_failover_never_reserializes_a_response_body` is what keeps them apart.
The lock file, readiness handshake, spawn/stop and request guard are genuinely
shared and live in proxy_base.py.

Three things this deliberately does NOT try to preserve, because they cannot be:

  cache_control  — there is no equivalent. Dropped, and logged once per process
                   so the user learns their turns bill uncached rather than
                   wondering why the cost moved.
  thinking       — a thinking block carries a signature that must round-trip
                   byte-for-byte to the infrastructure that minted it. Historical
                   ones are dropped from request history UNCONDITIONALLY,
                   including on a session resumed after switching backends, which
                   is the case that produces "Invalid signature in thinking
                   block" long after the swap.
  web_search     — runs on Anthropic's own servers. Not representable at all.

The keepalive is the piece most easily built wrong. Claude Code aborts a stream
that goes quiet (~90s idle, 300s hard watchdog), and a local model doing
grammar-constrained tool-call decoding can go silent long AFTER real content has
started — so the ping timer is armed for the whole stream and reset by every
upstream chunk, not just until the first byte.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

from . import config as _c
from . import proxy_base as _proxy

_CONNECT_TIMEOUT = 15
_READ_TIMEOUT = 600        # a local model can be slow; the ping keeps the client alive
_PING_EVERY = 20           # well inside Claude Code's ~90s idle abort
_CHUNK = 65536

#: ONE DAEMON PER PROFILE, named after it — same reasoning as failover.py: the
#: lock file and the readiness marker are derived from the name, and a singleton
#: on a fixed port re-reading the global settings per request is what let one
#: session's turns reach another profile's upstream with another profile's key.
def _daemon(prof):
    return _proxy.Daemon('gateway-%s' % (prof or {}).get('id', ''),
                         '--gateway-serve', 'gateway')


#: the profile THIS process serves, pinned by argv at spawn. See failover.py.
_SERVING = ''


def _serving_daemon():
    return _daemon({'id': _SERVING})


def _marker_path():
    return _serving_daemon().marker_path

#: The gateway substitutes the user's own upstream credential into everything it
#: forwards. Pointing it at Anthropic would mean a archeus-built request
#: wearing Anthropic's endpoint — the exact shape of the harness traffic
#: Anthropic has taken enforcement action against elsewhere. It costs nothing to
#: refuse, and refusing here means nobody can later "generalize" this module into
#: that without deleting a line that says why.
_FORBIDDEN_HOSTS = ('api.anthropic.com', 'claude.ai', 'www.anthropic.com')

_warned = set()
_print_lock = threading.Lock()


def enabled(prof):
    return bool((prof or {}).get('gateway_kind'))


def base_url(prof):
    return 'http://127.0.0.1:%d' % _c.gateway_port_of(prof or {})


def target_error(url):
    """'' when *url* is a usable upstream, else why not. Checked at startup so a
    misconfiguration is a refusal to run, not a session that dies mid-turn."""
    host = (urllib.parse.urlsplit(url or '').hostname or '').lower()
    if not host:
        return 'no gateway target configured'
    if host in _FORBIDDEN_HOSTS or host.endswith('.anthropic.com'):
        return ('refusing to target %s — the gateway forwards your own provider '
                'credential and must never impersonate the Anthropic client' % host)
    return ''


def ensure_running(prof):
    if not prof:
        return False, 'no provider profile'
    why = target_error(prof.get('gateway_target_base_url'))
    if why:
        return False, why
    return _daemon(prof).ensure(_c.gateway_port_of(prof),
                                quiet=bool(prof.get('failover_quiet')),
                                on_ready=lambda: base_url(prof),
                                extra_args=[prof['id']])


def stop_running(prof):
    return _daemon(prof).stop()


def _emit(line):
    with _print_lock:
        try:
            print(line, flush=True)
        except Exception:
            pass


def _warn_once(key, line):
    if key not in _warned:
        _warned.add(key)
        _emit(line)


# ── translation: Anthropic request -> OpenAI request ─────────

def to_openai_request(body):
    """Anthropic Messages payload -> OpenAI Chat Completions payload.

    The system field is an ARRAY in what Claude Code sends (its attribution
    block is the first entry) and a single message upstream, so it is flattened
    rather than dropped — dropping it would remove the whole system prompt."""
    out = {'model': body.get('model') or '', 'messages': []}
    sys_text = _flatten_text(body.get('system'))
    if sys_text:
        out['messages'].append({'role': 'system', 'content': sys_text})

    for msg in body.get('messages') or []:
        role = msg.get('role') or 'user'
        content = msg.get('content')
        if isinstance(content, str):
            out['messages'].append({'role': role, 'content': content})
            continue
        text_parts, tool_calls, tool_results = [], [], []
        for blk in content or []:
            t = blk.get('type')
            if t == 'text':
                text_parts.append(blk.get('text') or '')
            elif t == 'thinking' or t == 'redacted_thinking':
                continue        # never replayable off the infrastructure that signed it
            elif t == 'tool_use':
                tool_calls.append({
                    'id': blk.get('id') or '',
                    'type': 'function',
                    'function': {'name': blk.get('name') or '',
                                 'arguments': json.dumps(blk.get('input') or {})},
                })
            elif t == 'tool_result':
                tool_results.append({
                    'role': 'tool',
                    'tool_call_id': blk.get('tool_use_id') or '',
                    'content': _flatten_text(blk.get('content')),
                })
            elif t:
                # There was no else branch, so an `image` block — or a document,
                # or a web_search result — left the request with nothing said
                # anywhere: a vision model behind the gateway simply stopped
                # seeing the picture. cache_control below already had the right
                # treatment; this is the same, keyed per type so each one is
                # reported once rather than every turn.
                _warn_once('blk:' + t,
                           'gateway: %s block dropped — no OpenAI-shape '
                           'translation, the model never sees it' % t)
        if role == 'assistant':
            m = {'role': 'assistant', 'content': '\n'.join(p for p in text_parts if p) or None}
            if tool_calls:
                m['tool_calls'] = tool_calls
            out['messages'].append(m)
        else:
            # tool results are their own messages upstream and must precede any
            # remaining user text, or the call/result pairing breaks
            out['messages'].extend(tool_results)
            joined = '\n'.join(p for p in text_parts if p)
            if joined:
                out['messages'].append({'role': 'user', 'content': joined})

    tools = body.get('tools') or []
    if tools:
        out['tools'] = [{'type': 'function',
                         'function': {'name': t.get('name') or '',
                                      'description': t.get('description') or '',
                                      'parameters': t.get('input_schema') or {}}}
                        for t in tools if t.get('name')]
    if body.get('max_tokens'):
        out['max_tokens'] = body['max_tokens']
    if body.get('temperature') is not None:
        out['temperature'] = body['temperature']
    if body.get('stream'):
        out['stream'] = True
    if _has_cache_control(body):
        _warn_once('cache', 'gateway: cache_control dropped — turns bill uncached '
                            '(no OpenAI-shape equivalent exists)')
    return out


def _flatten_text(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    parts = []
    for blk in v:
        if isinstance(blk, str):
            parts.append(blk)
        elif isinstance(blk, dict) and blk.get('type') == 'text':
            parts.append(blk.get('text') or '')
    return '\n'.join(p for p in parts if p)


def _has_cache_control(body):
    for blk in body.get('system') or []:
        if isinstance(blk, dict) and blk.get('cache_control'):
            return True
    for msg in body.get('messages') or []:
        for blk in (msg.get('content') if isinstance(msg.get('content'), list) else []):
            if isinstance(blk, dict) and blk.get('cache_control'):
                return True
    return False


# ── translation: OpenAI response -> Anthropic response ───────

_STOP = {'stop': 'end_turn', 'length': 'max_tokens', 'tool_calls': 'tool_use',
         'function_call': 'tool_use', 'content_filter': 'end_turn'}


def to_anthropic_response(data, model):
    choice = ((data.get('choices') or [{}])[0]) or {}
    msg = choice.get('message') or {}
    content = []
    if msg.get('content'):
        content.append({'type': 'text', 'text': msg['content']})
    for i, call in enumerate(msg.get('tool_calls') or []):
        fn = call.get('function') or {}
        content.append({'type': 'tool_use',
                        'id': call.get('id') or ('call_%d' % i),
                        'name': fn.get('name') or '',
                        'input': _loads_or_empty(fn.get('arguments'))})
    usage = data.get('usage') or {}
    return {
        'id': data.get('id') or 'msg_gateway',
        'type': 'message',
        'role': 'assistant',
        'model': data.get('model') or model,
        'content': content,
        'stop_reason': _STOP.get(choice.get('finish_reason') or 'stop', 'end_turn'),
        'stop_sequence': None,
        'usage': {'input_tokens': usage.get('prompt_tokens') or 0,
                  'output_tokens': usage.get('completion_tokens') or 0},
    }


def _loads_or_empty(s):
    """A model that emits malformed tool arguments is common enough on local
    backends that it must not take the turn down: an empty input reaches the tool
    and comes back as a normal tool error the model can react to."""
    try:
        v = json.loads(s or '{}')
        return v if isinstance(v, dict) else {'value': v}
    except Exception:
        return {}


# ── streaming ────────────────────────────────────────────────

def iter_sse(fp):
    """Yield parsed `data:` payloads from an SSE body, stopping at [DONE].
    Kept separate from the HTTP call so a test can drive it off a byte buffer."""
    for raw in fp:
        line = raw.decode('utf-8', 'replace').strip()
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if payload == '[DONE]':
            return
        try:
            yield json.loads(payload)
        except Exception:
            continue


class StreamTranslator:
    """OpenAI streaming deltas -> the Anthropic SSE event sequence Claude Code
    expects. Returns a list of already-encoded SSE frames per upstream chunk, so
    the caller owns every write (and therefore the write lock)."""

    def __init__(self, model):
        self.model = model
        self.started = False
        self.text_open = False
        self.index = 0
        self.tools = {}         # openai tool index -> {id, name, args}
        self.stop = 'end_turn'
        self.usage = {'input_tokens': 0, 'output_tokens': 0}

    def start(self):
        return [_sse('message_start', {
            'type': 'message_start',
            'message': {'id': 'msg_gateway', 'type': 'message', 'role': 'assistant',
                        'model': self.model, 'content': [], 'stop_reason': None,
                        'stop_sequence': None, 'usage': self.usage}})]

    def feed(self, chunk):
        out = []
        if not self.started:
            self.started = True
            out += self.start()
        u = chunk.get('usage') or {}
        if u:
            self.usage = {'input_tokens': u.get('prompt_tokens') or 0,
                          'output_tokens': u.get('completion_tokens') or 0}
        choice = ((chunk.get('choices') or [{}])[0]) or {}
        delta = choice.get('delta') or {}
        if delta.get('content'):
            if not self.text_open:
                self.text_open = True
                out.append(_sse('content_block_start', {
                    'type': 'content_block_start', 'index': self.index,
                    'content_block': {'type': 'text', 'text': ''}}))
            out.append(_sse('content_block_delta', {
                'type': 'content_block_delta', 'index': self.index,
                'delta': {'type': 'text_delta', 'text': delta['content']}}))
        for call in delta.get('tool_calls') or []:
            i = call.get('index') or 0
            slot = self.tools.setdefault(i, {'id': '', 'name': '', 'args': ''})
            if call.get('id'):
                slot['id'] = call['id']
            fn = call.get('function') or {}
            if fn.get('name'):
                slot['name'] = fn['name']
            if fn.get('arguments'):
                slot['args'] += fn['arguments']
        if choice.get('finish_reason'):
            self.stop = _STOP.get(choice['finish_reason'], 'end_turn')
        return out

    def finish(self):
        out = []
        if not self.started:
            out += self.start()
            self.started = True
        if self.text_open:
            out.append(_sse('content_block_stop',
                            {'type': 'content_block_stop', 'index': self.index}))
            self.index += 1
            self.text_open = False
        # Tool arguments arrive as partial JSON fragments that are only valid
        # once concatenated, so the block is emitted whole at the end rather
        # than streamed — a half-parsed argument object is not something the
        # client can do anything useful with anyway.
        for i in sorted(self.tools):
            slot = self.tools[i]
            if not slot['name']:
                continue
            out.append(_sse('content_block_start', {
                'type': 'content_block_start', 'index': self.index,
                'content_block': {'type': 'tool_use', 'id': slot['id'] or ('call_%d' % i),
                                  'name': slot['name'], 'input': {}}}))
            out.append(_sse('content_block_delta', {
                'type': 'content_block_delta', 'index': self.index,
                'delta': {'type': 'input_json_delta',
                          'partial_json': slot['args'] or '{}'}}))
            out.append(_sse('content_block_stop',
                            {'type': 'content_block_stop', 'index': self.index}))
            self.index += 1
            self.stop = 'tool_use'
        out.append(_sse('message_delta', {
            'type': 'message_delta',
            'delta': {'stop_reason': self.stop, 'stop_sequence': None},
            'usage': {'output_tokens': self.usage.get('output_tokens', 0)}}))
        out.append(_sse('message_stop', {'type': 'message_stop'}))
        return out


def _sse(event, obj):
    # compact separators: this runs per streamed token, and the default
    # `", "`/`": "` padding is pure wire cost on every frame
    return ('event: %s\ndata: %s\n\n'
            % (event, json.dumps(obj, separators=(',', ':')))).encode('utf-8')


PING = _sse('ping', {'type': 'ping'})


# ── server ───────────────────────────────────────────────────

def serve_cli(port, pid=''):
    """The detached daemon's entry point. *pid* is the profile id it translates
    for. A missing profile is a refusal, never a fall back — see
    failover.serve_cli for why guessing here is the failure this design removes."""
    global _SERVING
    prof = _c.provider_profile(pid) if pid else _c.active_provider()
    if not prof:
        _emit('archeus gateway: no such provider profile %r — refusing to start'
              % (pid or '(active)'))
        return 1
    _SERVING = prof['id']
    port = int(port or _c.gateway_port_of(prof))
    why = target_error(prof.get('gateway_target_base_url'))
    if why:
        _emit('archeus gateway: %s' % why)
        return 1
    try:
        srv = make_server(port)
    except Exception as e:
        _emit('archeus gateway: cannot bind port %d: %s' % (port, e))
        return 1
    _daemon(prof).write_lock(port)
    _emit('')
    _emit('archeus gateway  :%d  %s -> %s (openai-chat)'
          % (port, prof.get('name') or '?', prof.get('gateway_target_base_url')))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _daemon(prof).clear_lock()
    return 0


def make_server(port=0):
    return _proxy.make_server(port, _Handler, 'gateway')


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _profile(self):
        """THIS daemon's profile, re-read per request but looked up by the id
        pinned at spawn — see failover._profile."""
        return _c.provider_profile(_SERVING)

    def _guard(self):
        # the PROFILE's key, not a global one: `claude` was handed this
        # profile's api_key as ANTHROPIC_AUTH_TOKEN, and the gateway stands
        # where its provider would. Guarding with another profile's key is a
        # 403 that reads like a bug in Claude Code.
        return _proxy.guard(self, (self._profile() or {}).get('api_key'),
                            _marker_path(), 'gateway')

    def do_GET(self):
        if _serving_daemon().serves_marker(self):
            return
        if not self._guard():
            return
        _proxy.write_json(self, 404, {'type': 'error', 'error': {
            'type': 'not_found_error', 'message': 'gateway serves POST /v1/messages'}})

    def do_POST(self):
        if not self._guard():
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b''
        try:
            body = json.loads(raw.decode('utf-8', 'replace') or '{}')
        except Exception:
            return _proxy.write_json(self, 400, {'type': 'error', 'error': {
                'type': 'invalid_request_error', 'message': 'body is not JSON'}}) and None

        if path.endswith('/v1/messages/count_tokens'):
            # No OpenAI-shape equivalent. Claude Code falls back gracefully when
            # the endpoint is absent, but it asks first, so answer with the same
            # estimate the rest of archeus uses rather than 404 on every turn.
            return _proxy.write_json(self, 200, {'input_tokens': _estimate_tokens(body)})
        if not path.endswith('/v1/messages'):
            return _proxy.write_json(self, 404, {'type': 'error', 'error': {
                'type': 'not_found_error', 'message': 'unsupported path %s' % path}})

        prof = self._profile()
        why = target_error((prof or {}).get('gateway_target_base_url'))
        if why:
            return _proxy.write_json(self, 502, {'type': 'error', 'error': {
                'type': 'api_error', 'message': why}})
        if body.get('stream'):
            self._stream(body, prof)
        else:
            self._once(body, prof)

    # ── upstream ──

    def _upstream_call(self, body, prof):
        url = ((prof or {}).get('gateway_target_base_url') or '').rstrip('/') + '/chat/completions'
        payload = json.dumps(to_openai_request(body)).encode('utf-8')
        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        key = (prof or {}).get('gateway_target_api_key') or ''
        if key:
            req.add_header('Authorization', 'Bearer ' + key)
        return urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT)

    def _once(self, body, prof):
        try:
            with self._upstream_call(body, prof) as r:
                data = json.loads(r.read().decode('utf-8', 'replace') or '{}')
        except Exception as e:
            return _proxy.write_json(self, 502, {'type': 'error', 'error': {
                'type': 'api_error', 'message': 'gateway upstream: %s' % e}})
        _proxy.write_json(self, 200, to_anthropic_response(data, body.get('model') or ''))

    def _stream(self, body, prof):
        try:
            resp = self._upstream_call(body, prof)
        except Exception as e:
            return _proxy.write_json(self, 502, {'type': 'error', 'error': {
                'type': 'api_error', 'message': 'gateway upstream: %s' % e}})
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'close')
        self.end_headers()

        # ONE writer: the ping thread and the relay loop share this socket, and
        # an interleaved write lands inside another frame.
        lock = threading.Lock()
        done = threading.Event()
        last = [time.time()]

        def write(frames):
            with lock:
                for f in frames:
                    self.wfile.write(f)
                try:
                    self.wfile.flush()
                except Exception:
                    pass

        def pinger():
            """Armed for the WHOLE stream, not just until the first byte. A local
            model doing grammar-constrained tool-call decoding goes quiet in the
            MIDDLE of a turn, and Claude Code cannot tell that from a dead
            connection — it aborts either way. `last` is reset by every upstream
            chunk, so a talkative stream never pays for a ping."""
            while not done.wait(1):
                if time.time() - last[0] >= _PING_EVERY:
                    last[0] = time.time()
                    try:
                        write([PING])
                    except Exception:
                        return

        t = threading.Thread(target=pinger, daemon=True)
        t.start()
        tr = StreamTranslator(body.get('model') or '')
        try:
            for chunk in iter_sse(resp):
                last[0] = time.time()
                frames = tr.feed(chunk)
                if frames:
                    write(frames)
            write(tr.finish())
        except Exception as e:
            _emit('gateway: stream failed: %s' % e)
        finally:
            done.set()
            try:
                resp.close()
            except Exception:
                pass


def _estimate_tokens(body):
    """chars//4, the same floor archeus uses everywhere it cannot ask. No
    dependency-free exact counter exists across providers, and a wrong-but-close
    number beats a 404 the client has to special-case."""
    n = len(_flatten_text(body.get('system')))
    for msg in body.get('messages') or []:
        c = msg.get('content')
        n += len(c) if isinstance(c, str) else len(_flatten_text(c))
    for t in body.get('tools') or []:
        n += len(json.dumps(t.get('input_schema') or {}))
    return max(1, n // 4)
