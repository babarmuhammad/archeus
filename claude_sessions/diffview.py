"""Git-like colored diffs for generated/updated files.

Shows what changed (old → new) after CLAUDE.md / system-prompt / global MCP
updates, and snapshots the previous version under <project>/.archeus/snapshots
(fallback ~/.claude/projects/<encoded>/.archeus/snapshots) so the last change
can be reviewed later from the workspace screen. All helpers are best-effort —
a diff/snapshot failure never blocks the operation that triggered it.
"""

import os
import json
import time
import difflib

from . import config as _c
from . import render
from . import store

_SNAP_SUBDIR = os.path.join(store.WORKDIR, 'snapshots')
_INDEX = 'index.json'
#: how many versions of each key to keep on disk. The index already remembered
#: the last 20 CHANGES, but only one `<key>.prev` file ever existed — so the
#: history listed edits whose content had already been overwritten. Versions are
#: stored as `<key>.<ts>.prev` now, and `<key>.prev` is kept as the newest one
#: so every existing load_prev() caller keeps working untouched.
KEEP_VERSIONS = 12
TITLES = {'claude_md': 'CLAUDE.md', 'system_prompt': 'system prompt',
          'global_claude_md': 'global CLAUDE.md', 'memory_graph': 'memory graph'}


# ── pure diff helpers ────────────────────────────────────────

def unified(old, new, label='file'):
    return list(difflib.unified_diff(
        (old or '').splitlines(), (new or '').splitlines(),
        fromfile=f'{label} (before)', tofile=f'{label} (after)', lineterm=''))


def stat(old, new):
    added = removed = 0
    for ln in unified(old, new):
        if ln.startswith('+') and not ln.startswith('+++'):
            added += 1
        elif ln.startswith('-') and not ln.startswith('---'):
            removed += 1
    return added, removed


def colorize(diff_lines):
    out = []
    for ln in diff_lines:
        if ln.startswith('+++') or ln.startswith('---'):
            out.append(f"{_c.C_DIM}{ln}{_c.C_RESET}")
        elif ln.startswith('@@'):
            out.append(f"{_c.C_ACCENT}{ln}{_c.C_RESET}")
        elif ln.startswith('+'):
            out.append(f"{_c.C_OK}{ln}{_c.C_RESET}")
        elif ln.startswith('-'):
            out.append(f"{_c.C_ERR}{ln}{_c.C_RESET}")
        else:
            out.append(ln)
    return out


# ── display ──────────────────────────────────────────────────

def show(old, new, title):
    """Open a colored unified diff in the pager. ESC/ENTER dismiss."""
    from .ui import pager
    label = title
    if (old or '') == (new or ''):
        pager(('ARCHEUS', title, 'DIFF'),
              [f"{_c.C_DIM}(no changes){_c.C_RESET}"], hint='ESC back')
        return
    added, removed = stat(old, new)
    header = [f"{_c.C_OK}+{added}{_c.C_RESET}  {_c.C_ERR}-{removed}{_c.C_RESET}"
              f"   {_c.C_DIM}{label}{_c.C_RESET}"]
    body = colorize(unified(old, new, label))
    pager(('ARCHEUS', title, 'DIFF'), body, header_lines=header, hint='ESC back')


def confirm(old, new, title):
    """Preview a proposed change BEFORE writing: shows the colored diff
    (old → new) so the user approves/rejects based on what changed. `f`
    toggles between the diff and the full proposed content. ENTER approve,
    ESC reject. Returns True (approve) / False (reject)."""
    from .ui import flush_input, wait_event
    has_old = bool((old or '').strip()) and old != new
    added, removed = stat(old, new) if has_old else (0, 0)
    diff_body = colorize(unified(old, new, title)) if has_old else []
    full_body = (new or '').splitlines()
    mode_diff = has_old

    flush_input()
    top = 0
    pending = None
    while True:
        body = diff_body if mode_diff else full_body
        page = max(4, render.frame_height() - 7)
        top = max(0, min(top, max(0, len(body) - page)))
        at_end = top + page >= len(body)
        if has_old:
            hdr = (f"{_c.C_OK}+{added}{_c.C_RESET}  {_c.C_ERR}-{removed}{_c.C_RESET}   "
                   f"{_c.C_DIM}{title} — {'diff' if mode_diff else 'full proposed'}{_c.C_RESET}")
        else:
            hdr = f"{_c.C_DIM}{title} — new content (nothing to compare){_c.C_RESET}"
        frame = [render.header('ARCHEUS', title, 'REVIEW'), '', '  ' + hdr, render.hline()]
        for ln in body[top:top + page]:
            frame.append(render.fit('  ' + ln, render.content_width()))
        frame.append('')
        keys = [('↑↓', 'scroll'), ('←→/SPACE', 'page')]
        if has_old:
            keys.append(('f', 'full' if mode_diff else 'diff'))
        keys += [('ENTER', 'approve & write'), ('ESC', 'reject')]
        frame.append(render.hint_keys(
            keys, prefix=f"{min(top + page, len(body))}/{len(body)}"
                         + ("  (end)" if at_end else "")))
        render.render_frame(frame)

        ev = pending if pending else wait_event()
        pending = None
        if ev[0] == 'up':
            top -= 1
        elif ev[0] == 'down':
            top += 1
        elif ev[0] == 'left':
            top -= page
        elif ev[0] == 'right' or (ev[0] == 'char' and ev[1] == ' '):
            top += page
        elif ev[0] == 'char' and ev[1] == 'f' and has_old:
            mode_diff = not mode_diff
            top = 0
        elif ev[0] == 'enter':
            return True
        elif ev[0] == 'esc':
            return False


# ── snapshot store ───────────────────────────────────────────

def _candidate_dirs(project_path, proj_folder):
    out = []
    if project_path:
        out.append(os.path.join(project_path, _SNAP_SUBDIR))
    if proj_folder:
        out.append(os.path.join(proj_folder, _SNAP_SUBDIR))
    return out


def _read_index(d):
    try:
        with open(os.path.join(d, _INDEX), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def record(project_path, proj_folder, key, old, new):
    """Persist the pre-update version + an index entry. Best-effort.

    Writes BOTH `<key>.<ts>.prev` (the browsable history) and `<key>.prev` (the
    newest, which every existing caller already reads). Older versions past
    KEEP_VERSIONS are removed here rather than by a separate sweep, because a
    cleanup nobody runs is a disk leak."""
    added, removed = stat(old, new)
    ts = time.time()
    for d in _candidate_dirs(project_path, proj_folder):
        try:
            os.makedirs(d, exist_ok=True)
            if not (_c.write_atomic(os.path.join(d, f'{key}.{int(ts)}.prev'), old or '')
                    and _c.write_atomic(os.path.join(d, f'{key}.prev'), old or '')):
                continue
            idx = _read_index(d)
            idx.append({'ts': ts, 'key': key, 'added': added, 'removed': removed})
            _c.write_json_atomic(os.path.join(d, _INDEX), idx[-40:])
            _trim_versions(d, key)
            return True
        except Exception:
            continue
    return False


def _version_files(d, key):
    """[(ts, path)] newest first for one key in one snapshot dir."""
    out = []
    try:
        for nm in os.listdir(d):
            if nm.startswith(key + '.') and nm.endswith('.prev'):
                mid = nm[len(key) + 1:-len('.prev')]
                if mid.isdigit():
                    out.append((int(mid), os.path.join(d, nm)))
    except Exception:
        return []
    return sorted(out, reverse=True)


def _trim_versions(d, key):
    for _ts, p in _version_files(d, key)[KEEP_VERSIONS:]:
        try:
            os.remove(p)
        except OSError:
            pass


def versions(project_path, proj_folder, key):
    """[{'ts','added','removed'}] newest first — the versions whose CONTENT is
    still on disk, joined to their index stats. An entry with no file left is
    not offered, because offering a restore that cannot happen is worse than
    showing a shorter list."""
    for d in _candidate_dirs(project_path, proj_folder):
        files = _version_files(d, key)
        if not files:
            continue
        stats = {int(e['ts']): e for e in _read_index(d) if e.get('key') == key}
        return [{'ts': ts, 'added': stats.get(ts, {}).get('added', 0),
                 'removed': stats.get(ts, {}).get('removed', 0)}
                for ts, _p in files]
    return []


def read_version(project_path, proj_folder, key, ts):
    """The stored text of one version, or '' if it is gone."""
    try:
        ts = int(float(ts))
    except (TypeError, ValueError):
        return ''
    for d in _candidate_dirs(project_path, proj_folder):
        for vts, p in _version_files(d, key):
            if vts == ts:
                try:
                    return open(p, encoding='utf-8', errors='ignore').read()
                except Exception:
                    return ''
    return ''


def target_path(project_path, proj_folder, key):
    """The live file a snapshot key restores into, or '' if it has none."""
    if key == 'claude_md':
        return os.path.join(project_path, 'CLAUDE.md') if project_path else ''
    if key == 'system_prompt':
        return os.path.join(proj_folder, 'system-prompt.txt') if proj_folder else ''
    if key == 'memory_graph':
        from .memory import _mem_dirs, GRAPH_NAME
        dirs = _mem_dirs(project_path, proj_folder)
        return os.path.join(dirs[0], GRAPH_NAME) if dirs else ''
    return ''


def restore(project_path, proj_folder, key, ts):
    """Put a stored version back. Returns (ok, message).

    Snapshots the CURRENT content first, so restoring is itself undoable — an
    undo you cannot undo is just a second way to lose the file."""
    p = target_path(project_path, proj_folder, key)
    if not p:
        return False, f'nothing to restore for {key}'
    text = read_version(project_path, proj_folder, key, ts)
    if not text:
        return False, 'that version is no longer on disk'
    cur = ''
    if os.path.isfile(p):
        try:
            cur = open(p, encoding='utf-8', errors='ignore').read()
        except Exception:
            cur = ''
    if cur == text:
        return True, 'already at that version'
    record(project_path, proj_folder, key, cur, text)
    if key == 'memory_graph':
        # the graph lives in TWO mirrored locations and load_memory takes
        # whichever it finds first — restoring one of them would leave the
        # other to win the next read
        import json as _json
        from .memory import save_memory
        try:
            data = _json.loads(text)
        except ValueError:
            return False, 'that snapshot is not valid JSON'
        return (True, 'restored memory graph') if save_memory(
            project_path, proj_folder, data) else (False, 'write failed')
    os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
    if not _c.write_atomic(p, text):
        return False, 'write failed'
    return True, f'restored {TITLES.get(key, key)}'


def load_prev(project_path, proj_folder, key):
    for d in _candidate_dirs(project_path, proj_folder):
        p = os.path.join(d, f'{key}.prev')
        if os.path.isfile(p):
            try:
                return open(p, encoding='utf-8', errors='ignore').read()
            except Exception:
                return ''
    return ''


def last_change(project_path, proj_folder, key):
    """Latest index entry for `key`, or None."""
    for d in _candidate_dirs(project_path, proj_folder):
        idx = _read_index(d)
        if idx:
            for e in reversed(idx):
                if e.get('key') == key:
                    return e
    return None


