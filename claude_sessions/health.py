"""Project health — launcher-side auto-mitigations for the most frequent
Claude Code problems (2026 field research: token burn, context bloat,
CLAUDE.md over-budget, silent MCP failures, context loss after /compact,
permission fatigue, Windows path pitfalls).

All checks are fast and local. Surfaced as a card in the workspace screen and
as pre-launch warnings.
"""

import os
import re
import json

from . import config as _c
from . import store
from .memory import tokens_estimate

CLAUDEMD_TOKEN_WARN = 1500
BURN_WARN_PCT = 70


# ── checks ───────────────────────────────────────────────────

def check_project(project_path, proj_folder):
    """[(severity 'warn'|'info', message, hint)] — cheap, no Claude calls."""
    out = []
    out += _check_claudemd(project_path)
    out += _check_memory(project_path, proj_folder)
    out += _check_dirs(proj_folder)
    out += _check_burn()
    out += _check_mcp()
    return out


def _check_claudemd(project_path):
    p = os.path.join(project_path or '', 'CLAUDE.md')
    if not os.path.isfile(p):
        return []
    try:
        raw = open(p, 'rb').read()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            return [('warn', 'CLAUDE.md is not valid UTF-8',
                     'Claude may misread it — re-save as UTF-8')]
        tok = tokens_estimate(text)
        if tok > CLAUDEMD_TOKEN_WARN:
            return [('warn', f'CLAUDE.md is heavy (~{tok} tok, loads EVERY session)',
                     'trim prose; memory digest is already micro — check AUTOGEN/SESSIONS size')]
    except Exception:
        pass
    return []


def _check_memory(project_path, proj_folder):
    from . import memory as memory_mod
    mem = memory_mod.load_memory(project_path, proj_folder)
    if not mem.get('entities'):
        return [('info', 'no semantic memory yet',
                 "press m → b to build it (Claude remembers the project)")]
    out = []
    if mem.get('pending_units'):
        # not an error any more: a cycle does what its budget allows and leaves
        # the rest queued, and with auto-memory on the next cycle takes them
        out.append(('info', f"{mem['pending_units']} module(s) still queued for memory",
                    'the next auto cycle takes them — or press m → b to finish now'))
    try:
        from .workspace import load_manifest
        man = load_manifest(project_path, proj_folder) or {}
        base = (man.get('operations') or {}).get('memory') or {}
        if base:
            from .repos import _git
            head = (_git(['rev-parse', 'HEAD'], project_path) or '').strip()
            if head and base.get('head_at_gen') and head != base['head_at_gen']:
                out.append(('info', 'memory may be stale (repo HEAD moved since build)',
                            'press m → b to refresh (incremental, cheap)'))
    except Exception:
        pass
    return out


def _check_dirs(proj_folder):
    from .sessions import load_add_dirs, load_extra_paths
    out = []
    try:
        for d in load_add_dirs(proj_folder) or []:
            if not os.path.isdir(d):
                out.append(('warn', f'--add-dir path missing: {d}', 'x to edit add-dirs'))
        for d in load_extra_paths(proj_folder) or []:
            if not os.path.isdir(d):
                out.append(('warn', f'extra PATH missing: {d}', 'p to edit paths'))
    except Exception:
        pass
    return out


def _check_burn():
    """Token-burn advisor: session window ≥70% → suggest cheaper launch opts."""
    try:
        from . import usage as usage_mod
        with usage_mod._lock:
            data = usage_mod._data
        if not data:
            return []
        for label, pct, _r in usage_mod._extract_windows(data):
            if label == 'session' and pct >= BURN_WARN_PCT:
                return [('warn', f'session window at {pct:.0f}%',
                         'consider model=sonnet / lower effort for routine work')]
    except Exception:
        pass
    return []


def _check_mcp():
    try:
        from . import mcp as mcp_mod
        if getattr(mcp_mod, '_mcp_ready', False) and getattr(mcp_mod, '_mcp_error', ''):
            return [('warn', f'MCP check failed: {mcp_mod._mcp_error}',
                     'servers may fail silently in-session')]
    except Exception:
        pass
    return []


# ── context-loss insurance (session log) ─────────────────────

SESSION_LOG = os.path.join(store.WORKDIR, 'session-log.md')
_LOG_MAX_LINES = 400


def append_session_log(project_path, proj_folder, sid):
    """Append a 5-line summary of the finished session (goal + files touched)
    to .archeus/session-log.md — local, no Claude call. Next session can
    recall what happened even after /compact killed the context."""
    try:
        from .sessions import session_changed_files, get_session_info
        jsonl = os.path.join(proj_folder, f'{sid}.jsonl')
        if not os.path.isfile(jsonl):
            return False
        preview, _cnt = get_session_info(jsonl)
        files = session_changed_files(jsonl)[:5]
        from datetime import datetime
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        lines = [f"## {stamp} — {sid[:8]}",
                 f"goal: {(preview or '?')[:160]}"]
        if files:
            lines.append("touched: " + ', '.join(p for p, _n in files))
        lines.append('')
        p = os.path.join(project_path, SESSION_LOG)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        old = ''
        if os.path.isfile(p):
            old = open(p, encoding='utf-8', errors='ignore').read()
        new = old + '\n'.join(lines) + '\n'
        # keep the log bounded — drop oldest entries
        all_lines = new.splitlines()
        if len(all_lines) > _LOG_MAX_LINES:
            new = '\n'.join(all_lines[-_LOG_MAX_LINES:]) + '\n'
        with open(p, 'w', encoding='utf-8') as f:
            f.write(new)
        return True
    except Exception:
        _c.log.exception('health: session log failed')
        return False


# ── permission allowlist from history ────────────────────────

_TOOL_RE = re.compile(r'"name"\s*:\s*"Bash"')


def frequent_bash_commands(proj_folder, min_count=3, top_k=10):
    """Most frequent first-word Bash commands across this project's
    transcripts → allowlist candidates [('git', 42), ...]."""
    counts = {}
    if not proj_folder or not os.path.isdir(proj_folder):
        return []
    from . import transcripts
    for nm in transcripts.session_files(proj_folder):
        for obj in transcripts.iter_json(os.path.join(proj_folder, nm),
                                         prefilter='"Bash"'):
            for block in (obj.get('message', {}).get('content') or []):
                if (isinstance(block, dict) and block.get('type') == 'tool_use'
                        and block.get('name') == 'Bash'):
                    cmd = str((block.get('input') or {}).get('command', '')).strip()
                    word = cmd.split()[0].lower() if cmd.split() else ''
                    if word and re.fullmatch(r'[a-z0-9_.-]+', word):
                        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [(w, c) for w, c in ranked if c >= min_count][:top_k]


def propose_allowlist(project_path, proj_folder):
    """Diff-previewed permissions.allow additions to <project>/.claude/settings.json.
    Returns (n_added, err) — user approves via diffview before write."""
    cands = frequent_bash_commands(proj_folder)
    if not cands:
        return 0, 'no repeated Bash commands found in history'
    sp = os.path.join(project_path, '.claude', 'settings.json')
    cur = {}
    if os.path.isfile(sp):
        try:
            cur = json.load(open(sp, encoding='utf-8'))
        except Exception:
            cur = {}
    allow = list((cur.get('permissions') or {}).get('allow') or [])
    new_rules = [f"Bash({w}:*)" for w, _c2 in cands
                 if f"Bash({w}:*)" not in allow]
    if not new_rules:
        return 0, 'all frequent commands already allowed'
    proposed = dict(cur)
    proposed.setdefault('permissions', {})
    proposed['permissions'] = dict(proposed['permissions'])
    proposed['permissions']['allow'] = allow + new_rules
    old_text = json.dumps(cur, indent=2) if cur else ''
    new_text = json.dumps(proposed, indent=2)
    from . import diffview
    if not diffview.confirm(old_text, new_text, 'PERMISSIONS ALLOWLIST (project settings.json)'):
        return 0, 'rejected'
    if not _c.write_atomic(sp, new_text):
        return 0, 'could not write %s' % sp
    return len(new_rules), ''
