"""The one reader for Claude Code's .jsonl transcripts.

Eight modules used to open these files themselves, and four of them called
`readlines()` — which materialises the whole file. A single project directory
here holds transcripts past 100 MB, and `/api/dashboard` polls every 10 s, so
that pattern is both the memory ceiling and the latency floor of the app.

Everything streams. One decoding policy (`errors='replace'` — a transcript is
user data and must never raise), one timestamp parser, and a `prefilter`
substring test applied to the raw line so the common case (a caller that wants
only the lines mentioning `"Bash"` or `file_path`) never pays for a
`json.loads` it is going to discard.
"""

import json
import os

__all__ = ['iter_json', 'iso_to_epoch', 'session_files']


def iter_json(path, *, limit=None, offset=0, max_bytes=None, prefilter=None):
    """Yield each line of *path* decoded as JSON, skipping blanks and garbage.

    limit/offset count YIELDED objects, not lines — a caller paging messages
    means messages. max_bytes caps how much of the file is read at all, so a
    preview of a 200 MB transcript costs the first megabyte. prefilter is a
    substring (or tuple of substrings) required in the raw line before it is
    parsed at all.
    """
    if limit == 0:
        return
    if isinstance(prefilter, str):
        prefilter = (prefilter,)
    read = 0
    seen = 0
    try:
        fh = open(path, 'r', encoding='utf-8', errors='replace')
    except OSError:
        return
    with fh:
        for line in fh:
            if max_bytes is not None:
                read += len(line.encode('utf-8'))
                if read > max_bytes:
                    return
            if prefilter and not any(p in line for p in prefilter):
                continue
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            seen += 1
            if seen <= offset:
                continue
            yield obj
            if limit is not None and seen - offset >= limit:
                return


def iso_to_epoch(ts):
    """Claude Code's ISO-8601 timestamps → epoch seconds, or None."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
    except Exception:
        return None


def session_files(folder, *, newest_first=True, limit=None):
    """The .jsonl transcripts in a project folder, newest first."""
    try:
        names = [n for n in os.listdir(folder) if n.endswith('.jsonl')]
    except OSError:
        return []
    def mtime(n):
        try:
            return os.path.getmtime(os.path.join(folder, n))
        except OSError:      # a session can end between listdir and stat
            return 0.0

    names.sort(key=mtime, reverse=newest_first)
    return names[:limit] if limit else names
