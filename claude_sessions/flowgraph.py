"""A session as a flow graph: what it did, in what order, and where time went.

The transcript view answers "what was said". It cannot answer "this session ran
for three hours — which tool ate it", because a message list has no shape: every
turn is the same height and a tool call that blocked for 90 seconds looks exactly
like one that returned instantly.

So the same file is read a second way, as an append-only log of typed EVENTS laid
out on the session's own clock. Two clocks, kept apart on purpose:

* **content time** — the transcript's timestamps. It decides what is true at a
  given point and nothing else.
* **presentation time** — how long you spend watching. It drives the playhead and
  the animation, and is what lets a three-hour session scrub past in seconds.

Everything streams. `build_events` is a generator over `transcripts.iter_json`,
which is the one reader for these files; a transcript here reaches 100 MB and
nothing in this module may hold one. Text is truncated where it is read, not
where it is rendered, so a payload cannot grow with a file.

The behaviour — a live flow graph of a coding-agent session, follow or replay,
scrub, speed control, click a node to inspect it, content time kept separate from
presentation time — is adopted from **zoetrope** (MIT, (c) 2026 Furkan
Kalaycioglu, https://github.com/furkankly/zoetrope), which is Rust and does it in
a terminal and in WebAssembly. No code is taken from it: this is stdlib Python
rendering a self-contained canvas page, in the shape `connections.py` already
established here. See docs/credits.md.
"""

import html as _html
import os

from .transcripts import iter_json, iso_to_epoch

__all__ = ['build_events', 'tail_events', 'session_meta', 'render_flow_html',
           'harness_of', 'EVENT_COLORS', 'SUPPORTS']

#: How much of any one string ever reaches the page. A prompt can be a pasted
#: file and a tool result can be a 2 MB build log; the node shows a label and the
#: inspector shows an excerpt, so neither has a use for more than this.
TEXT_CAP = 400

#: Ceiling on how many events one page carries. 20k nodes is already past what a
#: canvas can usefully show; beyond it the answer is to scrub, not to draw more.
MAX_EVENTS = 20000

#: One colour per event type. Standalone page, so these are literal hex — it has
#: no access to the app's palette vars, exactly as connections.py's page does not.
EVENT_COLORS = {
    'prompt':    '#7dcfff',   # the user said something
    'assistant': '#a6adc8',   # the model answered
    'tool':      '#f9e2af',   # a tool was invoked
    'result':    '#94e2d5',   # …and came back
    'error':     '#f38ba8',
    'spawn':     '#cba6f7',   # a subagent was started
    'compact':   '#fab387',   # the context was compacted
    'model':     '#89b4fa',   # the model or turn context changed
}

#: What each harness's file actually carries. Drawn from the real files rather
#: than from what a harness could in principle record: Codex writes tool calls as
#: `response_item` function_call entries, which no Codex session on this machine
#: has yet produced, so the page SAYS the lane is unverified instead of drawing
#: an empty one and letting you conclude the session ran no tools.
SUPPORTS = {
    'claude': ('prompt', 'assistant', 'tool', 'result', 'error', 'spawn', 'compact'),
    'codex':  ('prompt', 'assistant', 'error', 'tool', 'result', 'model'),
    'pi':     ('prompt', 'assistant', 'error', 'tool', 'result', 'model'),
}

#: Bound on the two per-session maps below. Both are keyed by ids that only ever
#: grow, and this module may not hold a transcript — clearing is the cheapest
#: bound that stays correct: an unpaired tool call simply reports no duration,
#: and a sidechain that outlives the window restarts in a fresh lane.
_MAP_CAP = 4096


def harness_of(path):
    """Which CLI wrote this transcript — 'claude', 'codex' or 'pi'.

    `harnesses.of_path` places the FILE, which is the form every caller here
    holds, and is the same call `store.transcript_path` makes.
    """
    from . import harnesses
    return harnesses.of_path(path)['id']


def _ev(o, t, kind, **kw):
    """One event.

    `o` is the object index in the file, which is what a poll resumes from. An
    edge to an earlier event is a `ref` counted BACKWARDS in events, never an
    absolute index: a follow poll parses its own batch and knows nothing about
    how many events the page already holds, and two batches numbered from 1 each
    would collide the moment the page concatenated them.
    """
    e = {'o': o, 't': t, 'type': kind}
    for k, v in kw.items():
        if v not in (None, '', 0):
            e[k] = v
    return e


def _said(text):
    """One text block of a user turn, or '' if it is harness chatter.

    Per BLOCK, deliberately unlike `transcript._message`, which joins every block
    and then tests the result: a turn whose FIRST block is a `<system-reminder>`
    — which is most of them on an account with hooks — takes the real prompt down
    with it, and the reminder is a separate block, so nothing is lost by judging
    them one at a time.
    """
    t = (text or '').strip()
    if not t or t.startswith('<') or t.startswith('Caveat:'):
        return ''
    return t + ' '


def _clip(s):
    if not isinstance(s, str):
        return ''
    s = s.strip()
    return s[:TEXT_CAP]


def _blocks(content):
    """Content as a list of blocks. A user message pi (or Claude) did not have to
    structure is a plain string."""
    if isinstance(content, str):
        return [{'type': 'text', 'text': content}]
    return [b for b in (content or []) if isinstance(b, dict)]


#: Tool inputs, in the order a human reads them: what it acted ON beats how.
_TARGET_KEYS = ('file_path', 'notebook_path', 'path', 'command', 'pattern',
                'url', 'prompt', 'description', 'query')


def _target(inp):
    if not isinstance(inp, dict):
        return ''
    for k in _TARGET_KEYS:
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            return _clip(v)
    return ''


def _scan(path, offset):
    """(object index, object) from *offset* on. The index counts objects yielded
    by the one reader, which is the unit `iter_json`'s own offset takes — so a
    poll resumes exactly where the last one stopped."""
    return enumerate(iter_json(path, offset=offset), start=offset + 1)


# ── per-harness parsers ──────────────────────────────────────────────────────
# Dispatched by harness id rather than through a `harnesses.py` descriptor key,
# because that table is one of the files this work is fenced out of. `of_path`
# is the same placement the descriptor would have used.


def _claude(path, offset):
    """Claude Code: `{type, timestamp, uuid, parentUuid, isSidechain, message}`.

    Two things the file does NOT carry, both worth stating because assuming
    either produces a plausible-looking lie:

    * **No duration on anything.** A tool's duration is the gap between the
      assistant line that opened it (`tool_use.id`) and the user line that closed
      it (`tool_result.tool_use_id`), so it is known only when the result
      arrives — which is why the `result` event carries `dur` and points back at
      the call with `ref`, instead of the call being patched after the fact. A
      generator cannot reach back into what it has already yielded, and it is not
      going to buffer a transcript in order to.
    * **No compaction marker** anywhere in this machine's corpus. The two shapes
      Claude Code is known to have used are matched defensively; nothing here
      depends on seeing one.
    """
    lane_of = {}          # sidechain uuid -> lane
    open_calls = {}       # tool_use id -> (event index, content time)
    i = 0
    for o, obj in _scan(path, offset):
        t = iso_to_epoch(obj.get('timestamp'))
        kind = obj.get('type')
        msg = obj.get('message') if isinstance(obj.get('message'), dict) else {}

        if kind == 'summary' or obj.get('isCompactSummary'):
            i += 1
            yield _ev(o, t, 'compact', text=_clip(obj.get('summary') or ''))
            continue

        lane = 0
        if obj.get('isSidechain'):
            lane = lane_of.get(obj.get('parentUuid'))
            if lane is None:
                lane = len(lane_of) % 8 + 1
            if len(lane_of) > _MAP_CAP:
                lane_of.clear()
            lane_of[obj.get('uuid')] = lane

        if obj.get('isApiErrorMessage'):
            i += 1
            yield _ev(o, t, 'error', lane=lane,
                      text=_clip(_text_of(msg.get('content'))))
            continue

        role = msg.get('role') or obj.get('type')
        if role == 'user':
            said = ''
            for b in _blocks(msg.get('content')):
                if b.get('type') == 'tool_result':
                    call = open_calls.pop(b.get('tool_use_id'), None)
                    ok = not b.get('is_error')
                    i += 1
                    yield _ev(o, t, 'result' if ok else 'error', lane=lane,
                              ref=i - call[0] if call else None,
                              dur=round(t - call[1], 3) if call and t else None,
                              text=_clip(_result_text(obj, b)))
                elif b.get('type') == 'text':
                    said += _said(b.get('text'))
            said = _clip(said)
            if said:
                i += 1
                yield _ev(o, t, 'prompt', lane=lane, text=said)
            continue

        if role != 'assistant':
            continue

        use = msg.get('usage') if isinstance(msg.get('usage'), dict) else {}
        said = ''
        calls = []
        for b in _blocks(msg.get('content')):
            bt = b.get('type')
            if bt == 'text':
                said += b.get('text') or ''
            elif bt == 'thinking':
                said = said or _clip(b.get('thinking') or '')
            elif bt == 'tool_use':
                calls.append(b)
        tok_in = ((use.get('input_tokens') or 0)
                  + (use.get('cache_read_input_tokens') or 0)
                  + (use.get('cache_creation_input_tokens') or 0))
        # An assistant line that is ONLY a tool_use is not a turn of its own —
        # drawing it puts a blank grey node in front of every tool call in the
        # session. A real API response always carries usage, so this drops the
        # container and never the answer.
        if said or tok_in or use.get('output_tokens'):
            i += 1
            yield _ev(o, t, 'assistant', lane=lane, name=msg.get('model') or '',
                      text=_clip(said), tok_in=tok_in,
                      tok_out=use.get('output_tokens') or 0)
        for b in calls:
            name = b.get('name') or 'tool'
            i += 1
            # no `text`: for a call, the target IS the text, and sending both
            # printed the same command twice in the inspector
            yield _ev(o, t, 'spawn' if name == 'Task' else 'tool', lane=lane,
                      name=name, target=_target(b.get('input')))
            if len(open_calls) > _MAP_CAP:
                open_calls.clear()
            if b.get('id') and t:
                open_calls[b['id']] = (i, t)


def _text_of(content):
    out = []
    for b in _blocks(content):
        if b.get('type') == 'text':
            out.append(b.get('text') or '')
    return ' '.join(out)


def _result_text(obj, block):
    """A tool result reads better from `toolUseResult` than from the block: the
    block is what the model was shown, the sidecar is what actually happened."""
    tur = obj.get('toolUseResult')
    if isinstance(tur, dict):
        for k in ('stdout', 'stderr', 'filePath', 'content'):
            v = tur.get(k)
            if isinstance(v, str) and v.strip():
                return v
    if isinstance(tur, str) and tur.strip():
        return tur
    c = block.get('content')
    return c if isinstance(c, str) else _text_of(c)


def _codex(path, offset):
    """Codex: `{timestamp, type, payload}`, verified against a real rollout.

    `token_count` is CUMULATIVE — the same reconstruction `codex.fold` already
    does, and reporting it raw would show a session spending its whole total on
    every turn. The `response_item` developer/environment preamble is skipped for
    the reason `codex.py` gives: it is the harness talking to itself.
    """
    open_calls = {}
    prev = {}
    last_agent = ''
    i = 0
    for o, obj in _scan(path, offset):
        t = iso_to_epoch(obj.get('timestamp'))
        pl = obj.get('payload') if isinstance(obj.get('payload'), dict) else {}
        kind, pt = obj.get('type'), pl.get('type')

        if kind == 'turn_context':
            m = pl.get('model')
            if m:
                i += 1
                yield _ev(o, t, 'model', name=m)
            continue

        if kind == 'event_msg':
            if pt == 'user_message':
                i += 1
                yield _ev(o, t, 'prompt', text=_clip(pl.get('message') or ''))
            elif pt == 'agent_message':
                last_agent = _clip(pl.get('message') or '')
                i += 1
                yield _ev(o, t, 'assistant', text=last_agent)
            elif pt == 'error':
                i += 1
                yield _ev(o, t, 'error',
                          text=_clip(pl.get('message') or str(pl.get('error') or '')))
            elif pt == 'token_count':
                info = pl.get('info') or {}
                tot = info.get('total_token_usage') or {}
                cur = {k: tot.get(k) or 0 for k in
                       ('input_tokens', 'cached_input_tokens', 'output_tokens')}
                if cur != prev and any(cur.values()):
                    i += 1
                    yield _ev(o, t, 'assistant', name='usage',
                              tok_in=cur['input_tokens'] - prev.get('input_tokens', 0),
                              tok_out=cur['output_tokens'] - prev.get('output_tokens', 0))
                    prev = cur
            continue

        if kind != 'response_item':
            continue
        if pt == 'message':
            # A rollout records a turn TWICE — once as the `event_msg` the UI
            # showed, once as the `response_item` the model was sent — and the
            # second copy also carries the developer preamble and
            # `<environment_context>` as more messages of the same shape. So the
            # user side comes from `event_msg` only (`codex.py` excludes
            # response_item from its turn count for the same reason), and the
            # assistant side is taken here only when no agent_message carried it:
            # the observed rollout has a reply in one form and not the other.
            if pl.get('role') != 'assistant':
                continue
            txt = _clip(_codex_text(pl.get('content')))
            if not txt or txt == last_agent:
                continue
            i += 1
            yield _ev(o, t, 'assistant', text=txt)
        elif pt in ('function_call', 'local_shell_call', 'custom_tool_call'):
            name = pl.get('name') or pt
            i += 1
            yield _ev(o, t, 'tool', name=name, target=_clip(_codex_args(pl)))
            cid = pl.get('call_id') or pl.get('id')
            if cid and t:
                if len(open_calls) > _MAP_CAP:
                    open_calls.clear()
                open_calls[cid] = (i, t)
        elif pt in ('function_call_output', 'local_shell_call_output',
                    'custom_tool_call_output'):
            call = open_calls.pop(pl.get('call_id') or pl.get('id'), None)
            out = pl.get('output')
            if isinstance(out, dict):
                out = out.get('content') or out.get('output') or ''
            i += 1
            yield _ev(o, t, 'result', ref=i - call[0] if call else None,
                      dur=round(t - call[1], 3) if call and t else None,
                      text=_clip(out if isinstance(out, str) else ''))


def _codex_text(content):
    if isinstance(content, str):
        return content
    out = []
    for b in _blocks(content):
        if b.get('type') in ('input_text', 'output_text', 'text'):
            out.append(b.get('text') or '')
    return ' '.join(out)


def _codex_args(pl):
    a = pl.get('arguments')
    if isinstance(a, str):
        return a
    if isinstance(a, dict):
        return _target(a) or ''
    return str(pl.get('command') or pl.get('input') or '')


def _pi(path, offset):
    """pi: `{type, id, parentId, timestamp, message}`.

    Its usage split is per message and already four-way, so nothing is
    reconstructed. Tool blocks are matched in both spellings the ecosystem uses:
    no pi session on this machine has run a tool, so the shape is not verified
    here and guessing ONE spelling would silently draw nothing.
    """
    open_calls = {}
    i = 0
    for o, obj in _scan(path, offset):
        t = iso_to_epoch(obj.get('timestamp'))
        kind = obj.get('type')
        if kind == 'model_change':
            m = obj.get('modelId')
            if m:
                i += 1
                yield _ev(o, t, 'model', name=m)
            continue
        if kind != 'message':
            continue
        m = obj.get('message') if isinstance(obj.get('message'), dict) else {}
        role = m.get('role')
        use = m.get('usage') if isinstance(m.get('usage'), dict) else {}

        said = ''
        for b in _blocks(m.get('content')):
            bt = b.get('type')
            if bt == 'text':
                said += b.get('text') or ''
            elif bt in ('toolUse', 'tool_use', 'toolCall'):
                name = b.get('name') or b.get('toolName') or 'tool'
                i += 1
                yield _ev(o, t, 'tool', name=name,
                          target=_target(b.get('input') or b.get('args')))
                cid = b.get('id') or b.get('toolUseId') or b.get('callId')
                if cid and t:
                    if len(open_calls) > _MAP_CAP:
                        open_calls.clear()
                    open_calls[cid] = (i, t)
            elif bt in ('toolResult', 'tool_result'):
                cid = b.get('toolUseId') or b.get('tool_use_id') or b.get('callId')
                call = open_calls.pop(cid, None)
                i += 1
                yield _ev(o, t, 'result', ref=i - call[0] if call else None,
                          dur=round(t - call[1], 3) if call and t else None,
                          text=_clip(b.get('text') or b.get('output') or ''))

        if m.get('stopReason') == 'error' or m.get('errorMessage'):
            i += 1
            yield _ev(o, t, 'error', text=_clip(m.get('errorMessage') or 'error'))
        elif role in ('user', 'assistant'):
            i += 1
            yield _ev(o, t, 'prompt' if role == 'user' else 'assistant',
                      name=m.get('model') or '', text=_clip(said),
                      tok_in=(use.get('input') or 0) + (use.get('cacheRead') or 0)
                             + (use.get('cacheWrite') or 0),
                      tok_out=use.get('output') or 0)


_PARSERS = {'claude': _claude, 'codex': _codex, 'pi': _pi}


def build_events(path, *, harness='claude', limit=None, offset=0):
    """Stream one transcript as typed events, oldest first.

    A GENERATOR, and it must stay one: these files reach 100 MB and every caller
    here is either paging or capped. `offset` and the `o` on each event are in
    the same unit — objects consumed — so a live poll resumes without re-emitting
    what it already has.
    """
    fn = _PARSERS.get(harness) or _claude
    n = 0
    for e in fn(path, offset):
        yield e
        n += 1
        if limit is not None and n >= limit:
            return


def tail_events(path, offset, *, harness='claude', limit=MAX_EVENTS):
    """(new events, next offset) — what a follow poll asks for.

    Re-READS the file from the start, because the one reader takes an object
    offset rather than a byte offset; it never re-emits and never materialises,
    which is the property that actually matters. Same contract `transcript.page`
    has carried since it was written.
    """
    out = list(build_events(path, harness=harness, limit=limit, offset=offset))
    return out, (out[-1]['o'] if out else offset)


def session_meta(path, events, *, harness='claude', sid='', project=''):
    """What the page needs about the session itself, derived from what it read."""
    ts = [e['t'] for e in events if e.get('t')]
    models = []
    for e in events:
        n = e.get('name')
        if e['type'] in ('assistant', 'model') and n and n not in models \
                and not n.startswith('<'):
            models.append(n)
    return {
        'sid': sid, 'harness': harness, 'project': project,
        'file': os.path.basename(path),
        'supports': list(SUPPORTS.get(harness, ())),
        'models': models[:4],
        'first': min(ts) if ts else 0, 'last': max(ts) if ts else 0,
        'n': len(events),
        'capped': len(events) >= MAX_EVENTS,
        'offset': events[-1]['o'] if events else 0,
    }


# ── the page ─────────────────────────────────────────────────────────────────

_TEMPLATE = r"""<!doctype html>
<meta charset="utf-8">
<title>__TITLE__ — session flow</title>
<style>__CSS__</style>
<div id="top">
  <b id="ttl">__TITLE__</b>
  <span id="meta"></span>
  <span class="grow"></span>
  <button id="play" title="Play / pause (space)">▶</button>
  <label>speed <select id="speed">
    <option value="1">1×</option><option value="4">4×</option>
    <option value="16" selected>16×</option><option value="64">64×</option>
    <option value="0">all</option></select></label>
  <label id="folbox"><input type="checkbox" id="follow"> follow</label>
</div>
<div id="wrap">
  <canvas id="c"></canvas>
  <aside id="side"><div id="sidebody" class="empty">Click a node to inspect it.</div></aside>
</div>
<div id="bar"><input type="range" id="scrub" min="0" max="1000" value="1000"><span id="clock"></span></div>
<script>
const FLOW=__FLOW_JSON__, META=__META_JSON__, COLORS=__COLORS_JSON__, POLL=__POLL_JSON__;
__JS__
</script>
"""


def render_flow_html(events, meta, *, poll=''):
    """One self-contained page. No <script src>, no vendored library, no palette
    vars — same standalone contract as `connections.render_html`, and the same
    `_script_json` for every blob, because the inline-script escaping rule has
    one correct form and a second copy is a second chance to get it wrong."""
    from .connections import _script_json
    from .gui_html import _read       # the cached web/ reader; one file loader
    title = meta.get('project') or meta.get('sid') or 'session'
    return (_TEMPLATE
            .replace('__CSS__', _read('flow.css'))
            .replace('__JS__', _read('flow.js'))
            .replace('__FLOW_JSON__', _script_json(events))
            .replace('__META_JSON__', _script_json(meta))
            .replace('__COLORS_JSON__', _script_json(EVENT_COLORS))
            .replace('__POLL_JSON__', _script_json(poll))
            .replace('__TITLE__', _html.escape(str(title))))
