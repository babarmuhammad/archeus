"""Recent-work memory — a compact "what changed recently" log per project,
complementing the code-structure knowledge graph.

On session end a heuristic (token-free) capture records a one-line summary and
the files touched into a bounded ring buffer (.archeus/memory/worklog.json).
On session start the digest is injected so the next session knows what the last
few sessions did. Opt-in per project (project_defaults[enc]['worklog']).

Inspired by thedotmack/claude-mem's session-observation → summary →
SessionStart-injection pattern. Capture is deliberately heuristic (no Claude
call) so it never spends tokens on every Stop.
"""

import json
import os
import time

from . import config as _c

#: keep the most recent N sessions. 50, not 10: an episode is ~300 bytes, so
#: the whole ring is ~30 KB, and `recall` retrieves from it by relevance rather
#: than by recency — at 10 there was nothing to retrieve FROM, only the last
#: handful to replay. The injected digest still shows DIGEST_N.
CAP = 50
DIGEST_N = 5             # inject at most this many
DIGEST_BUDGET = 700      # char budget for the injected block
#: the playbook's 30-90 day band. The ring cap is the real bound; this is what
#: expires an episode on a project that went quiet, which is exactly when
#: nothing else would ever trim it.
TTL_DAYS = 60


def worklog_path(project_path):
    from . import store
    return store.workfile(os.path.abspath(project_path), 'memory', 'worklog.json')


def load_worklog(project_path):
    from . import jsonstore
    return jsonstore.load(worklog_path(project_path), expect=list)


def save_worklog(project_path, entries):
    return _c.write_json_atomic(worklog_path(project_path), entries[-CAP:])


def add_entry(project_path, entry):
    """Append (dedup by session_id) and trim to CAP. Returns the saved list."""
    entries = [e for e in load_worklog(project_path)
               if e.get('session_id') != entry.get('session_id')]
    entries.append(entry)
    entries = _fresh(entries)[-CAP:]
    save_worklog(project_path, entries)
    return entries


def _fresh(entries, days=None):
    """Drop episodes past the TTL, keeping anything undated.

    An undated entry is one written before the field existed, not one that has
    outlived its welcome — deleting it would be reading a missing value as an
    old one, which is the mistake `_parse_session` documents about timestamps.
    """
    cut = time.time() - (TTL_DAYS if days is None else days) * 86400
    out = []
    for e in entries:
        try:
            t = time.mktime(time.strptime(e.get('ended_at', ''),
                                          '%Y-%m-%dT%H:%M:%SZ'))
        except (ValueError, TypeError):
            out.append(e)
            continue
        if t >= cut:
            out.append(e)
    return out


def apply_ttl(project_path):
    """Expire old episodes. Returns how many were dropped.

    Called by the scheduled forgetting pass rather than only by a write: a
    project nobody has touched is exactly where nothing else would ever trim
    the log, and it is also where the entries are most likely to be stale.
    """
    entries = load_worklog(project_path)
    kept = _fresh(entries)
    if len(kept) != len(entries):
        save_worklog(project_path, kept)
    return len(entries) - len(kept)


# ── heuristic capture from a session transcript (no Claude call) ──

_EDIT_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}


def _rel(path, root):
    """A touched file as `module/name.py`, not as a bare basename.

    The basename is what a human reads in the digest, but it is also what
    `recall` retrieves on — and a basename has no module in it, so every path
    signal `recall._path_segments` scores was thrown away before the episode
    was ever stored.
    """
    if root:
        # normcase BEFORE splitting, never after: on Windows it rewrites '/' to
        # '\', so a prefix test against a slash-joined root compares two
        # different separators and never matches.
        r = os.path.normcase(os.path.abspath(root))
        ap = os.path.abspath(path)
        if os.path.normcase(ap).startswith(r.rstrip(os.sep) + os.sep):
            return ap[len(r.rstrip(os.sep)) + 1:].replace('\\', '/')
    return path.replace('\\', '/').rsplit('/', 1)[-1]


def _iter_json(transcript_path):
    from . import transcripts
    return transcripts.iter_json(transcript_path)


def summarize_transcript(transcript_path, root=''):
    """Return (summary, files, marks) from a session jsonl, in ONE pass.

    Summary = the AI title if present, else the first real user message. Files =
    paths from Edit/Write tool uses, relative to *root*. `marks` carries what
    went wrong: `tool_errors`, `last_error` and a heuristic `outcome`. Tolerant
    of shape variations.

    The user-message test used to be `obj['role'] == 'user'` with a string
    `obj['content']`, and a real Claude Code record is
    `{"type":"user","message":{"role":"user","content":…}}` — no top-level
    `role`, no top-level `content`. So it was never once true in production and
    every entry on disk had an empty summary, while the test asserted a shape
    Claude Code does not emit. `sessions._extract_texts` has handled both all
    along; this reuses it rather than carrying a third reading of the format.

    The FIRST good message, not the last: `_parse_session` keeps the last one
    as `preview` because that is the row's best label, but an episode wants the
    task, and the task is what you opened the session with.
    """
    from .sessions import _extract_texts, _good_text, is_headless_text
    title = ''
    first_user = ''
    files = set()
    tool_errors = 0
    last_error = ''
    edits = 0
    tail_error = False
    for obj in _iter_json(transcript_path):
        if not isinstance(obj, dict):
            continue
        if obj.get('type') == 'ai-title' and obj.get('title'):
            title = str(obj['title'])
        msg = obj.get('message') if isinstance(obj.get('message'), dict) else obj
        role = obj.get('role') or (msg.get('role', '') if isinstance(msg, dict) else '')
        if role == 'user' and not first_user:
            for text in _extract_texts(obj):
                if _good_text(text) and not is_headless_text(text):
                    first_user = text
                    break
        # tool_use blocks live inside assistant message content
        content = msg.get('content') if isinstance(msg, dict) else None
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get('type') == 'tool_use' and block.get('name') in _EDIT_TOOLS:
                    fp = (block.get('input') or {}).get('file_path') \
                        or (block.get('input') or {}).get('notebook_path')
                    if fp:
                        edits += 1
                        files.add(_rel(str(fp), root))
                # what FAILED, in the same pass. An episode that does not say
                # what went wrong cannot stop the next session walking into it,
                # which is the one thing this log exists to do.
                elif block.get('type') == 'tool_result':
                    bad = bool(block.get('is_error'))
                    tail_error = bad
                    if bad:
                        tool_errors += 1
                        last_error = _err_text(block.get('content'))[:120]
    summary = (title or first_user or '').strip().replace('\n', ' ')
    if len(summary) > 120:
        summary = summary[:117] + '…'
    return summary, sorted(files), {
        'tool_errors': tool_errors, 'last_error': last_error,
        # ponytail: a trailing-state heuristic, not a real outcome — it reads
        # the LAST tool result and whether anything was edited. The upgrade path
        # is the lesson pass, which already makes one Claude call per session
        # over the same transcript and is where a judged outcome belongs.
        'outcome': 'error' if tail_error else ('ok' if edits else '')}


def _err_text(content):
    """The text of a failed tool_result, whichever shape it arrived in."""
    if isinstance(content, str):
        return content.strip().replace('\n', ' ')
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get('type') == 'text':
                return str(b.get('text', '')).strip().replace('\n', ' ')
            if isinstance(b, str):
                return b.strip().replace('\n', ' ')
    return ''


def capture_session(project_path, session_id, transcript_path):
    """Record one session's work. Returns the entry, or None if nothing useful
    (no summary and no files touched — don't clutter the log), and None for a
    headless call, which is archeus talking to itself rather than work you did.

    Every field is free. `get_session_stats` is cached by (mtime, size, schema)
    and the transcript is FINAL at session end, so this parse is paid once and
    warms the cache the sessions list would otherwise pay for later — a net win
    rather than a new cost. Nothing here spends a token: the log competes with
    the user for quota nowhere, which is the constraint the whole design is
    under (the event log records 53 refused calls in a fortnight).
    """
    summary, files, marks = summarize_transcript(transcript_path, project_path)
    if not summary and not files:
        return None
    entry = {'session_id': session_id,
             'ended_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             'summary': summary, 'files': files}
    entry.update(marks)
    try:
        from .sessions import get_session_stats
        st = get_session_stats(transcript_path) or {}
        if st.get('headless'):
            return None
        first, last = st.get('first_ts'), st.get('last_ts')
        if first and last and last >= first:
            entry['duration_s'] = int(last - first)
        if st.get('branch'):
            entry['branch'] = st['branch']
        if st.get('api_errors'):
            entry['api_errors'] = int(st['api_errors'])
        from .stats import _sum_usage
        u = _sum_usage(st)
        tok = (u.get('in') or 0) + (u.get('out') or 0)
        if tok:
            entry['tokens'] = tok
    except Exception:
        pass                       # a stats miss must never lose the episode
    add_entry(project_path, entry)
    return entry


# ── digest for injection ─────────────────────────────────────

def _ago(iso):
    try:
        t = time.mktime(time.strptime(iso, '%Y-%m-%dT%H:%M:%SZ'))
        secs = max(0, time.time() - t)
    except Exception:
        return ''
    for unit, n in (('d', 86400), ('h', 3600), ('m', 60)):
        if secs >= n:
            return f"{int(secs // n)}{unit} ago"
    return 'just now'


def render_digest(project_path, n=DIGEST_N, budget=DIGEST_BUDGET):
    """A tight markdown 'Recent work' block, or '' if the log is empty."""
    entries = load_worklog(project_path)
    if not entries:
        return ''
    lines = ["## Recent work (archeus — last sessions)"]
    for e in reversed(entries[-n:]):
        when = _ago(e.get('ended_at', ''))
        files = e.get('files') or []
        ftail = f" — {', '.join(files[:5])}" + ('…' if len(files) > 5 else '') if files else ''
        summ = e.get('summary') or '(no summary)'
        # what FAILED is the half worth the characters: a list of what was done
        # cannot stop the next session walking into the same wall.
        mark = ''
        if e.get('outcome') == 'error':
            mark = ' [ended on an error'
            if e.get('tool_errors'):
                mark += f", {e['tool_errors']} failed"
            mark += ']'
        elif e.get('tool_errors'):
            mark = f" [{e['tool_errors']} tool error{'' if e['tool_errors'] == 1 else 's'}]"
        line = f"- {when + ': ' if when else ''}{summ}{ftail}{mark}"
        if sum(len(x) + 1 for x in lines) + len(line) > budget:
            break
        lines.append(line)
    return '\n'.join(lines) if len(lines) > 1 else ''
