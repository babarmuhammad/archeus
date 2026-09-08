"""Compile the semantic memory graph into path-scoped Claude Code rules.

Each repo/module unit becomes <project>/.claude/rules/archeus-mem-*.md with a
`globs:` frontmatter — Claude Code loads the rule ONLY when it touches matching
files. Zero always-on token cost; per-module detail appears exactly when
relevant. Prunes only its own (prefix-scoped) files — user rules are never
touched.
"""

import os
import re

from .memory import tokens_estimate

RULE_PREFIX = 'archeus-mem-'
RULE_MAX_TOKENS = 400


def _sanitize(s):
    return re.sub(r'[^A-Za-z0-9_-]+', '_', s or '').strip('_') or 'root'


def rule_filename(repo, module):
    return f"{RULE_PREFIX}{_sanitize(repo)}-{_sanitize(module)}.md"


def _unit_glob(entities, module=''):
    """Project-relative glob for a unit, derived from its entities' files.

    The common prefix is taken over PATH SEGMENTS, not characters.
    `os.path.commonprefix` is a string operation, so `{tests/, tools/}` produced
    the prefix `"t"` and the glob `"t/**"` — which matches nothing, so that
    rule's ~375 tokens could never load. And any unit whose files diverged at
    the first segment collapsed to `"**"`, i.e. ALWAYS loaded, in a module whose
    whole purpose is path-scoped laziness. Both were on disk in this repo.

    `module` is the fallback scope: it is the unit's own directory, which is a
    better answer than "everything" when the entities' files disagree.
    """
    dirs = set()
    for e in entities:
        for f in e.get('source_files', []) or []:
            if not str(f).strip():
                continue
            # A file at the repo ROOT has an empty dirname, and dropping it
            # meant the prefix was computed from the unit's *other* files: the
            # `(root)` unit here holds README.md plus claude_sessions/__init__.py
            # and came out scoped `claude_sessions/**` — firing on a tree it is
            # not about and never on the root files it IS about. Kept as a
            # first-level entry so the common prefix correctly collapses.
            dirs.add(os.path.dirname(str(f).replace('\\', '/')).strip('/'))
    common = []
    if dirs and '' not in dirs:
        parts = [d.split('/') for d in dirs]
        for seg in zip(*parts):
            if len(set(seg)) != 1:
                break
            common.append(seg[0])
    mod = str(module or '').strip('/')
    scoped_mod = mod and mod not in ('(root)', '.')
    if common:
        prefix = '/'.join(common)
        # The prefix must never be NARROWER than the unit it describes. The
        # entities' `source_files` are a representative SAMPLE (MODULE_MAX_FILES
        # caps it), so a unit whose sample happened to sit in one subdirectory
        # scoped itself to that subdirectory: `Claude/plugin/skills` — a rule
        # about all eight skills — came out `plugin/skills/changelog/**` and
        # would fire for one of them. Harmless while every rule loaded
        # unconditionally; load-bearing the moment `paths:` actually scopes.
        if scoped_mod and prefix.startswith(mod + '/'):
            return f"{mod}/**"
        return prefix + '/**'
    if scoped_mod:
        return f"{mod}/**"
    # A unit that genuinely spans the repo root gets a glob that still SCOPES —
    # '**' is indistinguishable from an always-on rule and defeats the point.
    return '*'


def render_rule(repo, module, summary, entities, relations):
    glob = _unit_glob(entities, module)
    # `paths:`, NOT `globs:`. Claude Code scopes a rule file on `paths:` alone —
    # "rules without a paths field are loaded unconditionally and apply to all
    # files" — and `globs:` is the Cursor spelling, which it does not recognise.
    # Every rule file this wrote was therefore loaded into EVERY session, ~3.9k
    # tokens on this repo, while archeus's own audit reported them as lazy.
    # Verified empirically: all 11 files appeared in a fresh session's context
    # with no matching file opened. Documented list form, one pattern per item.
    lines = [
        '---',
        f'description: "archeus memory: {repo}/{module}"',
        'paths:',
        f'  - "{glob}"',
        '---',
        f"# {repo}/{module}" + (f" — {summary}" if summary else ''),
    ]
    for e in entities:
        s = (e.get('summary') or '').strip()
        lines.append(f"- {e.get('name')} ({e.get('type', '')})" + (f" — {s}" if s else ''))
    names = {e.get('name') for e in entities}
    rels = [f"{r['source']} {r.get('rel', 'relates')} {r['target']}"
            for r in relations if r.get('source') in names and r.get('target') in names]
    if rels:
        lines.append("Relations: " + '; '.join(rels))
    text = '\n'.join(lines)
    while tokens_estimate(text) > RULE_MAX_TOKENS and len(lines) > 6:
        lines.pop(-2 if rels else -1)
        text = '\n'.join(lines)
    return text + '\n'


def sync_rules(project_path, proj_folder, mem):
    """Write one rule per unit with >=2 entities; prune stale archeus-mem-*
    files. Returns list of written filenames. Best-effort."""
    from .config import load_settings
    if not load_settings().get('memory_rules', True):
        return []
    rules_dir = os.path.join(project_path, '.claude', 'rules')
    by_unit = {}
    for e in mem.get('entities', []):
        if e.get('type') == 'lesson' or not e.get('valid', True):
            continue
        by_unit.setdefault((e.get('repo', ''), e.get('module', '')), []).append(e)

    written = []
    try:
        os.makedirs(rules_dir, exist_ok=True)
        keep = set()
        for (repo, module), ents in by_unit.items():
            if len(ents) < 2:
                continue
            name = rule_filename(repo, module)
            keep.add(name)
            summary = (mem.get('summaries', {}) or {}).get(f"{repo}/{module}", '')
            body = render_rule(repo, module, summary, ents, mem.get('relations', []))
            p = os.path.join(rules_dir, name)
            old = ''
            if os.path.isfile(p):
                try:
                    old = open(p, encoding='utf-8', errors='ignore').read()
                except Exception:
                    old = ''
            if old != body:
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(body)
            written.append(name)
        # prune ONLY our own stale files
        for nm in os.listdir(rules_dir):
            if nm.startswith(RULE_PREFIX) and nm not in keep:
                try:
                    os.remove(os.path.join(rules_dir, nm))
                except OSError:
                    pass
    except Exception:
        from . import config as _c
        _c.log.exception('memrules: sync failed')
    return written
