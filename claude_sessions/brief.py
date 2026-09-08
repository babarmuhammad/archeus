"""Project brief — instant, local (no Claude call) situational awareness:
  • work_suggestions: ranked next-steps from lessons, graph importance, health,
    context freshness, the repo's own TODO/ponytail markers and untested
    modules — plus whatever the optional AI work-scan last found.
  • session_diff: what changed since the last session (git + session-log).
Both are token-frugal and automatic; surfaced in the memory hub.

The division of labour matters: RENDERING this list must never make a model
call. Local emitters run every time and cost nothing; `run_scan` is a button,
its findings are persisted into the memory graph, and `work_suggestions` only
ever reads them back. Anything on a per-render path pays its cost forever —
the lesson this codebase already learned from the recall hook's counters.
"""

import os
import subprocess

from . import memory

#: where a work-scan's findings live in the graph dict
SCAN_KEY = 'work_scan'
#: the item kinds the scan may emit, so a model inventing a new one cannot
#: smuggle an unstyled tag into the UI
SCAN_KINDS = ('bug', 'vuln', 'perf', 'idea')


def work_suggestions(project_path, proj_folder):
    """[(priority_str, text)] ranked next-steps. Pure local."""
    out = []
    mem = memory.load_memory(project_path, proj_folder)

    # 1. unresolved error_fix lessons → likely recurring pain
    fixes = [e for e in mem.get('entities', [])
             if e.get('type') == 'lesson' and e.get('kind') == 'error_fix'
             and e.get('status') in ('approved', 'pinned')]
    for l in fixes[:3]:
        out.append(('fix', f"recurring issue: {l.get('summary', l.get('name', ''))}"))

    # 2. pending lessons awaiting review
    try:
        from . import lessons
        pend = lessons.pending_sids(proj_folder, mem)
        if pend:
            out.append(('learn', f"{len(pend)} session(s) not yet learned — press L"))
    except Exception:
        pass

    # 3. most-connected modules (graph rank) → the project's backbone
    mods = {}
    for e in mem.get('entities', []):
        if e.get('type') == 'lesson':
            continue
        u = f"{e.get('repo')}/{e.get('module')}"
        mods[u] = max(mods.get(u, 0), e.get('rank', 0))
    top = sorted(mods.items(), key=lambda kv: -kv[1])[:3]
    for u, r in top:
        if r > 0:
            out.append(('core', f"central module: {u} (most-connected)"))

    # 4. open health issues
    try:
        from . import health
        for sev, msg, _hint in health.check_project(project_path, proj_folder):
            if sev == 'warn':
                out.append(('health', msg))
    except Exception:
        pass

    # 5. context the model is being given, and how far it has drifted. The
    #    freshness score was a number on a screen nobody acted on; here it is a
    #    line in the list you already read, with the key that clears it.
    for tag, text in _stale_items(project_path, proj_folder):
        out.append((tag, text))

    # 6-8. signals that are already in the repo and cost nothing to read
    for fn in (_todo_items, _untested_items, _debt_items):
        try:
            out += fn(project_path)
        except Exception:
            pass

    # 9. whatever the last AI work-scan found, if one has been run
    out += [(s.get('kind', 'idea'), s.get('text', ''))
            for s in stored_scan(mem) if s.get('text')]

    out = _dedupe(out)
    if not out:
        out.append(('info', 'no signals yet — build memory (m→b) and run a session'))
    return out


#: order the list is presented in — most actionable first. Anything unlisted
#: sorts last rather than disappearing, so a new tag is never silently hidden.
_TAG_ORDER = ('vuln', 'bug', 'fix', 'stale', 'health', 'todo', 'debt', 'perf',
              'test', 'idea', 'learn', 'core', 'info')
MAX_SUGGESTIONS = 24


def _dedupe(items):
    """Stable dedupe by text, then rank by tag. A cap, because a list of forty
    things to do is a list of none."""
    seen, uniq = set(), []
    for tag, text in items:
        t = (text or '').strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        uniq.append((tag, t))
    uniq.sort(key=lambda it: _TAG_ORDER.index(it[0]) if it[0] in _TAG_ORDER
              else len(_TAG_ORDER))
    return uniq[:MAX_SUGGESTIONS]


def _stale_items(project_path, proj_folder):
    """Freshness checks that are genuinely failing, with their remedy."""
    try:
        from . import workspace
        _m, _live, checks, _score, _safe = workspace.compute_status(project_path,
                                                                    proj_folder)
    except Exception:
        return []
    out = []
    for c in checks:
        if not c.get('applicable', True) or c['state'] == 'fresh':
            continue
        if c['name'] not in workspace._WEIGHTS:
            continue
        fix = workspace._FIXES.get(c['name'], '')
        out.append(('stale', f"{c['detail']}"
                             f"{' — ' + fix if fix else ''}"
                             f" (+{workspace._WEIGHTS[c['name']]}% freshness)"))
    return out


#: markers worth surfacing. Deliberately not a code scanner — these are notes
#: the repo's own authors left, which is a far better signal than a heuristic.
_TODO_RE = r'\b(TODO|FIXME|XXX|HACK)\b'


def _todo_items(project_path, cap=4):
    """TODO/FIXME markers, from ONE `git grep` over tracked files.

    Tracked-only is the point: node_modules and vendored bundles are full of
    other people's TODOs, and `git grep` skips them for free."""
    from .repos import _git
    out = _git(['grep', '-nIE', '--no-color', _TODO_RE], project_path)
    if not out:
        return []
    rows = []
    for ln in out.splitlines():
        parts = ln.split(':', 2)
        if len(parts) < 3 or '/vendor/' in parts[0].replace('\\', '/'):
            continue
        note = parts[2].strip().lstrip('#/*- ').strip()
        rows.append(('todo', f"{parts[0]}:{parts[1]} — {note[:110]}"))
    if len(rows) > cap:
        extra = len(rows) - cap
        rows = rows[:cap] + [('todo', f"…and {extra} more TODO/FIXME marker(s)")]
    return rows


def _debt_items(project_path, cap=3):
    """`ponytail:` comments — shortcuts this codebase deliberately marked as
    deferred. Written down and then never looked at again is how they rot."""
    from .repos import _git
    out = _git(['grep', '-nI', '--no-color', 'ponytail:'], project_path)
    if not out:
        return []
    rows = []
    for ln in out.splitlines():
        parts = ln.split(':', 2)
        if len(parts) < 3:
            continue
        note = parts[2].split('ponytail:', 1)[-1].strip()
        rows.append(('debt', f"{parts[0]}:{parts[1]} — deferred: {note[:110]}"))
    return rows[:cap]


def _untested_items(project_path, cap=3):
    """Modules with no test file named after them.

    Only fires where the repo already follows that convention, measured rather
    than assumed: if most modules have no matching test, this is not the
    project's convention and the check says nothing at all."""
    import glob
    tests_dir = os.path.join(project_path, 'tests')
    if not os.path.isdir(tests_dir):
        return []
    have = set()
    for p in glob.glob(os.path.join(tests_dir, 'test_*.py')):
        have.add(os.path.basename(p)[5:-3])
    if not have:
        return []
    missing = []
    for pkg in sorted(glob.glob(os.path.join(project_path, '*', '__init__.py'))):
        d = os.path.dirname(pkg)
        for p in sorted(glob.glob(os.path.join(d, '*.py'))):
            nm = os.path.basename(p)[:-3]
            if nm.startswith('_'):
                continue
            if not any(h == nm or h.startswith(nm + '_') or nm in h for h in have):
                missing.append(nm)
    # a project that mostly doesn't do this has not forgotten — it has chosen
    if not missing or len(missing) > len(have):
        return []
    head = ', '.join(missing[:cap])
    more = f" (+{len(missing) - cap} more)" if len(missing) > cap else ''
    return [('test', f"no test file for: {head}{more}")]


# ── AI work scan (a button, never a render) ──────────────────

def stored_scan(mem):
    """The findings of the last scan, minus the ones you dismissed."""
    rec = (mem or {}).get(SCAN_KEY) or {}
    gone = set(rec.get('dismissed') or [])
    return [i for i in (rec.get('items') or [])
            if i.get('text') and i['text'] not in gone]


def scan_age(mem):
    """ISO timestamp of the last scan, or '' — so the UI can say how old this
    advice is instead of presenting it as current."""
    return ((mem or {}).get(SCAN_KEY) or {}).get('at', '')


def scan_prompt(project_path, mem):
    """One prompt, built from what archeus already knows.

    Deliberately fed the memory graph rather than the source tree: the graph is
    the compressed, already-paid-for description of this project, and asking a
    model to re-read the repo is the expensive way to learn what archeus has
    been recording all along."""
    from .repos import _git
    ents = [e for e in (mem.get('entities') or []) if e.get('type') != 'lesson']
    ents.sort(key=lambda e: -(e.get('rank', 0)))
    graph = '\n'.join(f"- {e.get('name')} ({e.get('type')}, {e.get('module')}): "
                      f"{(e.get('summary') or '')[:150]}" for e in ents[:40])
    lessons = '\n'.join(f"- {e.get('summary', '')[:180]}"
                        for e in (mem.get('entities') or [])
                        if e.get('type') == 'lesson')[:2000]
    stat = (_git(['diff', '--stat', 'HEAD~5', '--'], project_path) or '')[:1500]
    return (
        "You are reviewing a software project to produce a short, concrete work "
        "list. You are given its architecture graph, the lessons its own tooling "
        "has recorded, and a recent diffstat — not the source. Reason from those.\n\n"
        "Output one line per item, at most 10 lines, in this exact form:\n"
        "<kind>|<one concrete sentence, under 160 characters>\n\n"
        f"<kind> is exactly one of: {', '.join(SCAN_KINDS)}.\n"
        "  bug  — something that looks incorrect and would misbehave\n"
        "  vuln — a security weakness: an unvalidated input, a missing "
        "authorization check, a secret or path handled unsafely\n"
        "  perf — work repeated per request/turn that need not be\n"
        "  idea — a function or capability worth building next\n\n"
        "Rules: no numbering, no headings, no commentary, no code fences. Each "
        "line must name the module or component it is about. Say nothing you "
        "cannot support from the material below — an empty list is a valid "
        "answer and is better than a plausible invention.\n\n"
        f"ARCHITECTURE:\n{graph}\n\nRECORDED LESSONS:\n{lessons}\n\n"
        f"RECENT CHANGES:\n{stat}\n"
    )


def parse_scan(text):
    """`kind|text` lines → [{'kind','text'}]. Unknown kinds become `idea`
    rather than being dropped: the sentence is the value, the tag is a label."""
    out = []
    for line in (text or '').splitlines():
        line = line.strip().lstrip('-*0123456789. ').strip()
        if '|' not in line:
            continue
        kind, _, msg = line.partition('|')
        kind, msg = kind.strip().strip('`').lower(), msg.strip()
        if len(msg) < 12:
            continue
        out.append({'kind': kind if kind in SCAN_KINDS else 'idea',
                    'text': msg[:220]})
    return out[:10]


def save_scan(project_path, proj_folder, items):
    """Persist a scan's findings, keeping any dismissals already made."""
    from datetime import datetime, timezone
    mem = memory.load_memory(project_path, proj_folder)
    prev = mem.get(SCAN_KEY) or {}
    mem[SCAN_KEY] = {
        'at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'items': items,
        # a dismissal survives a re-scan; being told the same thing you already
        # said no to is how a suggestion list stops being read
        'dismissed': list(prev.get('dismissed') or []),
    }
    memory.save_memory(project_path, proj_folder, mem)
    return mem[SCAN_KEY]


def dismiss_scan_item(project_path, proj_folder, text):
    mem = memory.load_memory(project_path, proj_folder)
    rec = mem.get(SCAN_KEY) or {'items': [], 'dismissed': []}
    d = list(rec.get('dismissed') or [])
    if text not in d:
        d.append(text)
    rec['dismissed'] = d[-200:]
    mem[SCAN_KEY] = rec
    memory.save_memory(project_path, proj_folder, mem)
    return len(d)


def run_scan(project_path, proj_folder):
    """One Claude call → persisted findings. Called from a job, never a render."""
    mem = memory.load_memory(project_path, proj_folder)
    out = memory._claude_stdin(scan_prompt(project_path, mem),
                               os.path.abspath(project_path or '.'),
                               crumbs=('ARCHEUS', 'WORK SCAN'),
                               label='Scanning for work...')
    items = parse_scan(out)
    if not items:
        raise RuntimeError('Scan returned nothing usable')
    rec = save_scan(project_path, proj_folder, items)
    return {'ok': True, 'items': items, 'at': rec['at']}


def _last_session_stamp(project_path):
    """ISO-ish date of the most recent session-log entry, or ''."""
    from .health import SESSION_LOG
    p = os.path.join(project_path, SESSION_LOG)
    if not os.path.isfile(p):
        return ''
    try:
        for line in reversed(open(p, encoding='utf-8', errors='ignore').read().splitlines()):
            if line.startswith('## '):
                # "## 2026-07-05 14:30 — <sid>"
                return line[3:].split('—')[0].strip().split()[0]
    except Exception:
        pass
    return ''


def _git_repos(project_path, proj_folder):
    """Every git repo for this project: the root if it's one, plus any nested
    repos (a workspace often holds several sub-project repos, none at the root)."""
    repos = []
    try:
        from . import connections
        # no `isdir('.git')` filter: _discover_repos already returns repos, and
        # re-testing for a .git DIRECTORY here dropped every submodule again
        for r in connections._discover_repos(os.path.abspath(project_path), proj_folder):
            if r not in repos:
                repos.append(r)
    except Exception:
        pass
    return repos


#: (key) -> (expires_at, result). Opening the Tools tab ran `git log` AND
#: `git status` in every repo of the project — twenty subprocesses on a
#: ten-repo workspace, every single click, for an answer that cannot
#: meaningfully change between two clicks a few seconds apart.
#:
#: A TTL rather than a filesystem signature, deliberately: `dirty` comes from
#: `git status`, and editing a file touches NOTHING under .git, so no signature
#: can see it — the same limitation repos.state already documents. The cache
#: lives in the process, so it is empty on every launch and a stale answer can
#: never outlive the app.
_DIFF_TTL = 90.0
_diff_cache = {}


def session_diff_rows(project_path, proj_folder, refresh=False):
    """Structured 'since last session': one row per repo that moved.

    {'repos': [{'label','path','commits':[...],'dirty':N}], 'since': str|None,
     'note': str}  — `note` is set INSTEAD of repos when there is nothing to
    show, so a caller never has to tell an empty list from a failure.

    This is the source; session_diff() below is a formatter over it. The GUI
    renders per repo and needs the counts, and re-deriving them by parsing the
    '▸ ' prefix off a formatted line is exactly the sort of round trip that
    breaks the first time the format changes.

    Cached for _DIFF_TTL seconds; pass refresh=True for the explicit reload.
    """
    import time
    key = (os.path.abspath(project_path), proj_folder or '')
    if not refresh:
        hit = _diff_cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]

    def _done(result):
        _diff_cache[key] = (time.time() + _DIFF_TTL, result)
        return result

    since = _last_session_stamp(project_path)
    repos = _git_repos(project_path, proj_folder)
    if not repos:
        return _done({'repos': [], 'since': since,
                      'note': '(no git repo here or in sub-projects — nothing to diff)'})

    from .repos import _git as _repo_git

    def _git(cwd, args):
        return (_repo_git(args, cwd, timeout=8) or '').strip()

    root = os.path.abspath(project_path)
    out = []
    for repo in repos:
        label = os.path.basename(repo.rstrip(os.sep)) or repo
        log_args = ['log', '--oneline', f'--since={since}'] if since else ['log', '--oneline', '-10']
        commits = _git(repo, log_args)
        dirty = _git(repo, ['status', '--porcelain'])
        if not commits and not dirty:
            continue                                 # quiet repo — skip
        out.append({
            'label': label if (len(repos) > 1 or repo != root) else '',
            'path': repo,
            'commits': commits.splitlines()[:10] if commits else [],
            'dirty': len(dirty.splitlines()) if dirty else 0,
        })
    if not out:
        return _done({'repos': [], 'since': since,
                      'note': f"(no changes since {since or 'the last session'})"})
    return _done({'repos': out, 'since': since, 'note': ''})


def session_diff(project_path, proj_folder):
    """'Since last session' as flat lines, for the TUI and the memory hub.
    A formatter over session_diff_rows — one place decides what 'moved' means."""
    data = session_diff_rows(project_path, proj_folder)
    if data['note']:
        return [data['note']]
    lines = []
    for r in data['repos']:
        lines.append(f"▸ {r['label']}" if r['label'] else 'commits:')
        lines += ['  ' + c for c in r['commits']]
        if r['dirty']:
            lines.append(f"  ({r['dirty']} uncommitted file(s))")
        lines.append('')
    return lines
