"""Developer tooling: read this machine's Archeus project list (read-only) and write
clients/v2-live/local/projects.local.json, the "My projects" fixture of the V2 Live
prototype (`?projects=local`). The file holds only display name, slug and counts, is
gitignored and must never be committed or sent anywhere.

    py tools/v2_live_local_projects.py [--print]
"""
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'clients', 'v2-live', 'local', 'projects.local.json')
DAY = 86400
MISSION_CAP, IDEA_CAP, NAME_CAP = 30, 16, 48


def kind_of(days):
    return 'running' if days <= 3 else 'waiting' if days <= 21 else 'quiet'


def hints(sessions, recent, lessons):
    """Missions: every recent session plus a quarter of the older ones, square-root scaled so
    a project with a hundred sessions stays bigger than one with thirty. Ideas: the same
    scaling over the project's lessons when its memory has any, else a third of the sessions."""
    if not sessions:
        return 0, 0
    n = max(1, recent + (sessions - recent) // 4)
    return (min(MISSION_CAP, n, round(2 * n ** .5)),
            min(IDEA_CAP, round((lessons or sessions // 3) ** .5)))


def slugs(rows):
    seen = set()
    for r in rows:
        s = re.sub(r'[^a-z0-9]+', '-', r['name'].lower()).strip('-') or 'project'
        if s in seen:
            s += '-' + hashlib.sha1(r['enc'].encode()).hexdigest()[:4]
        seen.add(s)
        r['slug'] = s


def worktrees_of(parent, by_path, now, wt):
    """The linked worktrees of one project's repository, each folded into a short row: no paths leave this function."""
    base, out = os.path.basename(parent['path']).lower(), []
    for t in wt.list_worktrees(parent['path']):
        path = os.path.normcase(t['path'])
        if t['bare'] or path == os.path.normcase(os.path.normpath(parent['path'])):
            continue
        own = by_path.get(path)
        name = os.path.basename(t['path'])
        idle = now - max([own['mtime']] if own else [os.stat(t['path']).st_mtime if os.path.isdir(t['path']) else 0])
        out.append({'branch': t['branch'] or '(detached)',
                    'label': name[len(base) + 1:] if name.lower().startswith(base + '-') and len(name) > len(base) + 1 else name,
                    'owner': 'archeus' if t['branch'].startswith('worktree-') or name.lower().startswith(base + '-')
                    or '.claude' + os.sep + 'worktrees' in path.replace('/', os.sep) else 'linked',
                    'state': 'missing' if not os.path.isdir(t['path']) else 'stale' if idle > 30 * DAY else 'active',
                    'sessions': own['sessions'] if own else 0})
    return out


def collect():
    sys.path.insert(0, ROOT)
    from claude_sessions import gui, memory, sessions as sess, worktrees as wt
    now, projects = time.time(), []
    for p in gui.list_projects():
        if p['hidden']:
            continue
        mtimes = [m for _n, f in sess.account_folders_for(p['encoded'])
                  for m, _sid, _prev, _count in sess.scan_sessions(f)]
        projects.append(dict(p, mtimes=mtimes, sessions=len(mtimes), mtime=max(mtimes or [p['mtime']]),
                             norm=os.path.normcase(os.path.normpath(p['path']))))
    by_path = {p['norm']: p for p in projects}
    families = {}
    for p in projects:
        trees = wt.list_worktrees(p['path']) if os.path.isdir(p['path']) else []
        if trees:
            families.setdefault(os.path.normcase(trees[0]['path']), []).append(p)
    folded = {}
    for main, members in families.items():
        if len(members) > 1:
            parent = by_path.get(main) or max(members, key=lambda m: m['sessions'])
            for m in members:
                if m is not parent:
                    folded[m['norm']] = parent
    rows = []
    for p in projects:
        if p['norm'] in folded:
            continue
        kin = [p] + [m for m in projects if folded.get(m['norm']) is p]
        mtimes = [m for k in kin for m in k['mtimes']]
        try:
            mem = memory.load_memory(p['path'])
        except Exception:
            mem = {}
        lessons = sum(1 for e in mem.get('entities', []) if e.get('type') == 'lesson')
        modules = sum(1 for e in mem.get('entities', []) if e.get('type') != 'lesson' and e.get('valid', True))
        days = int((now - max(k['mtime'] for k in kin)) // DAY)
        recent = sum(1 for m in mtimes if now - m <= 30 * DAY)
        missions, ideas = hints(len(mtimes), recent, lessons)
        name = p['name'] if len(p['name']) <= NAME_CAP else p['name'][:NAME_CAP - 1] + '…'
        rows.append({'enc': p['encoded'], 'name': name, 'sessions': len(mtimes), 'recent_sessions': recent,
                     'memory_modules': modules, 'lessons': lessons, 'missions_hint': missions,
                     'ideas_hint': ideas, 'last_active_days': days, 'kind': kind_of(days),
                     'worktrees': worktrees_of(p, by_path, now, wt), 'folded': len(kin) - 1})
    slugs(rows)
    return [{k: v for k, v in r.items() if k != 'enc'} for r in rows]


if __name__ == '__main__':
    try:
        rows = collect()
    except Exception as e:
        sys.exit('project listing failed: %s: %s' % (type(e).__name__, e))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print('wrote %d projects' % len(rows))
    if '--print' in sys.argv:
        for r in rows:
            print('%-34s s=%-4d r=%-3d mod=%-3d les=%-3d -> m=%-2d i=%-2d %3dd %-8s wt=%d folded=%d' % (
                r['name'], r['sessions'], r['recent_sessions'], r['memory_modules'], r['lessons'],
                r['missions_hint'], r['ideas_hint'], r['last_active_days'], r['kind'], len(r['worktrees']), r['folded']))
