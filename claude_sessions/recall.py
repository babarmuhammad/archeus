"""Task-scoped memory retrieval — the engine behind archeus's token-efficient
injection. Scores the semantic graph against a query (IDF keyword overlap +
path match + dependency rank + relation expansion) and assembles a context
string cut to a hard token budget. Pure local — no Claude call, fast enough
for a per-prompt hook (<1s).

IMPORTANT: no ui/render imports at module level — this runs in the
UserPromptSubmit hook where latency matters.
"""

import os
import re
import math
import json

from . import memory


def tokens_estimate(text):
    return max(1, len(text or '') // 4)


_WORD = re.compile(r'[a-z0-9]+')
_CAMEL = re.compile(r'(?<=[a-z0-9])(?=[A-Z])')


def _tokenize(s):
    """Word set incl. camelCase/snake_case splits: 'UserPromptHook' →
    {userprompthook, user, prompt, hook}."""
    if not s:
        return set()
    out = set(_WORD.findall(s.lower()))
    for part in _CAMEL.sub(' ', s).replace('_', ' ').split():
        out.update(_WORD.findall(part.lower()))
    return out


# ── index ────────────────────────────────────────────────────

#: Words that carry no retrieval signal. The IDF below already pushes a
#: ubiquitous term to zero, but a stoplist is what stops a two-word prompt made
#: entirely of them from scoring at all — and English stopwords are not
#: project-specific, so nothing is lost by naming them.
STOPWORDS = frozenset("""
a an the this that these those and or but not is are was were be been being am
do does did doing have has had having will would shall should can could may
might must of in on at to from by for with about into over after before under
above then than so if it its it's as at i me my we our you your he she they them
what which who whom how why when where all any both each few more most other
some such only own same too very just now here there
one two three thing things way ways get gets got let lets please ok okay yes
sure thanks again really actually simply basically stuff something anything
""".split())

#: how many top-scoring tokens a query needs before memory is injected at all.
#: "the" used to return 33 entities.
MIN_QUERY_SIGNAL = 1


def build_index(mem):
    ents = mem.get('entities', [])
    df = {}
    toks = []
    lens = []
    n = 0
    for e in ents:
        t = _tokenize(e.get('name', '')) | _tokenize(e.get('summary', ''))
        toks.append(t)
        lens.append(max(1, len(t)))
        # Document frequency over what can actually be RETRIEVED. Invalidated
        # facts are kept as history and never injected — on this repo's own
        # graph they are 151 of 314 entities, so counting them inflated every
        # df and pushed the IDF of live terms down for no reason.
        if not e.get('valid', True):
            continue
        n += 1
        for tok in t:
            df[tok] = df.get(tok, 0) + 1
    n = max(1, n)
    # Proper BM25 IDF. The old `log(1 + n/df)` never reaches zero — it is
    # >= log(2) ~ 0.69 even for a token present in EVERY entity — and the only
    # gate downstream was `score > 0`, so `idf('the')` measured 2.08 on the live
    # graph and the query "the" alone returned 33 entities. This form goes
    # negative for a term more than half the corpus contains, which is what
    # makes "does this word distinguish anything" answerable at all.
    idf = {tok: math.log(1 + (n - c + 0.5) / (c + 0.5)) for tok, c in df.items()}

    rel_adj = {}
    for r in mem.get('relations', []):
        s, t = r.get('source'), r.get('target')
        if s and t:
            rel_adj.setdefault(s, []).append((t, r.get('rel', 'relates')))
            rel_adj.setdefault(t, []).append((s, r.get('rel', 'relates')))

    mod_adj = {}
    for e in mem.get('module_edges', []):
        s, t = e.get('source'), e.get('target')
        if s and t:
            mod_adj.setdefault(s, []).append(t)
            mod_adj.setdefault(t, []).append(s)

    return {'idf': idf, 'ent_tokens': toks, 'rel_adj': rel_adj, 'mod_adj': mod_adj,
            'ent_lens': lens, 'avg_len': (sum(lens) / len(lens)) if lens else 1.0}


def _path_segments(e):
    segs = set()
    for p in e.get('source_files', []) or []:
        for part in str(p).replace('\\', '/').split('/'):
            segs.add(part.lower())
            stem = os.path.splitext(part)[0].lower()
            segs.add(stem)
    for part in str(e.get('module', '')).split('/'):
        if part:
            segs.add(part.lower())
    return segs


#: BM25 term-saturation and length-normalisation constants (the standard pair).
BM25_K1 = 1.2
BM25_B = 0.75
#: Reciprocal-rank-fusion smoothing. 60 is the value from Cormack et al.; it
#: decides how sharply the top of each ranker outweighs its tail.
RRF_K = 60.0
#: per-signal weight in the fusion. Relative only — RRF combines POSITIONS, so
#: these never have to be commensurable the way the old added scores did.
RRF_WEIGHTS = {'lexical': 1.0, 'path': 0.8, 'rank': 0.35, 'lesson': 0.5}


def query_tokens(query):
    """Tokens worth retrieving on — content words only."""
    return {t for t in _tokenize(query) if t not in STOPWORDS and len(t) > 1}


def _bm25(qtok, etok, idf, floor, elen, avg_len):
    """Sum of BM25 term scores. Presence-only (no term frequency): an entity is
    a name plus one sentence, so a term occurs once or not at all.

    `floor` keeps a common-but-meaningful term contributing a little rather than
    nothing — it ranks below a rare term without vanishing."""
    total = 0.0
    denom_len = BM25_K1 * (1 - BM25_B + BM25_B * (elen / (avg_len or 1.0)))
    for t in qtok & etok:
        w = max(idf.get(t, 0.0), floor)
        total += w * (BM25_K1 + 1) / (1.0 + denom_len)
    return total


def score_entities(mem, index, query, path_hints=()):
    """[(score, entity)] descending, non-matching dropped.

    Four rankers fused by Reciprocal Rank Fusion rather than added together.
    The previous formula summed an IDF total, a flat `+4.0` for any path hit, a
    flat `+2.0` for being a lesson and `0.5*log2(1+rank)` — four quantities on
    four different scales, so the constants alone decided the order. Measured on
    the live graph, "fix the bug" returned four lessons and no code. RRF uses
    only each ranker's POSITION, so nothing needs calibrating and no single
    signal can drown the others.
    """
    qtok = query_tokens(query)
    hints = {h.lower() for h in path_hints}
    if len(qtok) < MIN_QUERY_SIGNAL and not hints:
        return []                                     # nothing to retrieve on
    idf, lens = index['idf'], index.get('ent_lens') or []
    avg_len = index.get('avg_len') or 1.0
    #: a term in most of the corpus still beats no term at all
    idf_floor = 0.05

    cand, lex, path, rank, lesson = [], [], [], [], []
    for i, (e, etok) in enumerate(zip(mem.get('entities', []), index['ent_tokens'])):
        if not e.get('valid', True):
            continue                                  # superseded fact — history only
        if e.get('type') == 'lesson' and e.get('status') not in ('approved', 'pinned'):
            continue                                  # pending never leaves the TUI
        ntok = _tokenize(e.get('name', ''))
        elen = lens[i] if i < len(lens) else len(etok) or 1
        # a hit in the NAME still counts for more than one in the summary
        kw = (_bm25(qtok, ntok, idf, idf_floor, elen, avg_len) * 2.0
              + _bm25(qtok, etok - ntok, idf, idf_floor, elen, avg_len))
        segs = _path_segments(e)
        seg_hit = len((qtok & segs) | (hints & segs))
        # Candidacy is TOKEN OVERLAP; IDF only ranks. A term the corpus is full
        # of ("memory" in this project's own graph) has a low or negative BM25
        # weight, and letting that exclude the entity outright made
        # "recall scoring budget" return nothing at all. The stoplist is what
        # keeps contentless prompts out; IDF decides order, not membership.
        if not (qtok & etok) and not seg_hit:
            continue                                  # no evidence at all
        k = len(cand)
        cand.append(e)
        if kw > 0:
            lex.append((kw, k))
        if seg_hit:
            path.append((seg_hit, k))
        if e.get('rank', 0):
            rank.append((e['rank'], k))
        if e.get('type') == 'lesson':
            # confidence finally matters: it was recorded and never once read
            # by the scorer, while every lesson got the same flat bonus
            lesson.append((float(e.get('confidence') or 0.5), k))

    fused = [0.0] * len(cand)
    for name, ranked in (('lexical', lex), ('path', path),
                         ('rank', rank), ('lesson', lesson)):
        w = RRF_WEIGHTS[name]
        ranked.sort(key=lambda x: -x[0])
        for pos, (_v, k) in enumerate(ranked):
            fused[k] += w / (RRF_K + pos + 1)

    out = [(fused[k], e) for k, e in enumerate(cand) if fused[k] > 0]
    out.sort(key=lambda x: (-x[0], x[1].get('name', '')))
    return out


def expand_relations(mem, index, seeds, hops=1, decay=0.5):
    """Neighbors of the seed entities via entity relations AND module edges,
    inheriting seed_score*decay per hop. Returns [(score, entity)] for NEW
    entities only (dedup keep-max)."""
    by_name = {}
    for e in mem.get('entities', []):
        by_name.setdefault(e.get('name'), e)
    unit_ents = {}
    for e in mem.get('entities', []):
        unit_ents.setdefault(f"{e.get('repo')}/{e.get('module')}", []).append(e)

    seen = {e.get('name') for _s, e in seeds}
    found = {}
    frontier = list(seeds)
    for _hop in range(hops):
        nxt = []
        for s, e in frontier:
            inherit = s * decay
            for other, _rel in index['rel_adj'].get(e.get('name'), []):
                oe = by_name.get(other)
                if oe is None or other in seen:
                    continue
                if oe.get('type') == 'lesson' and oe.get('status') not in ('approved', 'pinned'):
                    continue
                if inherit > found.get(other, (0, None))[0]:
                    found[other] = (inherit, oe)
                nxt.append((inherit, oe))
            unit = f"{e.get('repo')}/{e.get('module')}"
            for nunit in index['mod_adj'].get(unit, []):
                for oe in unit_ents.get(nunit, [])[:3]:   # top few from linked module
                    name = oe.get('name')
                    if name in seen or oe.get('type') == 'lesson':
                        continue
                    w = inherit * 0.5
                    if w > found.get(name, (0, None))[0]:
                        found[name] = (w, oe)
        frontier = nxt
        seen |= set(found)
    return sorted(found.values(), key=lambda x: -x[0])


# ── assembly ─────────────────────────────────────────────────

_HEADER = "PROJECT MEMORY (archeus) — task-relevant subset:"


def render_context(scored, mem, budget_tokens):
    """Compact context string cut to budget. Relations only among included
    entities; approved lessons under their own header."""
    if not scored:
        return '', 0
    lines = [_HEADER]
    used = tokens_estimate(_HEADER)
    included = []
    lessons = []
    for s, e in scored:
        if e.get('type') == 'lesson':
            line = f"! {e.get('name')}: {e.get('summary', '')}".rstrip()
        else:
            files = ', '.join((e.get('source_files') or [])[:2])
            line = (f"{e.get('module', '')}/{e.get('name')} ({e.get('type', '')}): "
                    f"{e.get('summary', '')}" + (f" [files: {files}]" if files else ''))
        # +1 for the newline this line will be joined with — the estimate
        # ignored them, so the rendered text ran over the budget it was cut to
        cost = tokens_estimate(line) + 1
        if used + cost > budget_tokens:
            # FIT, don't truncate. `break` meant one long summary discarded
            # every smaller, lower-ranked item behind it — the budget bought
            # fewer facts the more verbose the top hit happened to be.
            continue
        used += cost
        if e.get('type') == 'lesson':
            lessons.append(line)
        else:
            lines.append(line)
        included.append(e.get('name'))

    inc = set(included)
    rel_lines = []
    for r in mem.get('relations', []):
        if r.get('source') in inc and r.get('target') in inc:
            rl = f"{r['source']} -{r.get('rel', 'relates')}-> {r['target']}"
            cost = tokens_estimate(rl) + 1
            if used + cost > budget_tokens:
                continue
            used += cost
            rel_lines.append(rl)
    if rel_lines:
        lines.append("Relations: " + '; '.join(rel_lines))
    if lessons:
        lines.append("LESSONS:")
        lines.extend(lessons)
    text = '\n'.join(lines)
    # what was ACTUALLY emitted, so the caller credits reinforcement to the
    # entities Claude saw rather than to everything that merely ranked
    render_context.last_included = list(included)
    return text, tokens_estimate(text)


HITS_LOG = 'hits.log'


def hits_log_path(project_path, proj_folder):
    dirs = memory._mem_dirs(project_path, proj_folder)
    return os.path.join(dirs[0], HITS_LOG) if dirs else ''


def hits_pending(project_path, proj_folder):
    """Recall hits recorded but not yet folded into the graph.

    One line per entity injected into one prompt. The GUI showed the literal
    string 'folding in' derived from the graph's top-hits list, which is a
    different thing entirely and never changed. Reading is safe against a
    concurrent hook: each prompt appends its whole block in one write, so a
    reader sees a consistent prefix (same contract as memory.dirty_count)."""
    p = hits_log_path(project_path, proj_folder)
    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def _log_hits(project_path, proj_folder, names):
    p = hits_log_path(project_path, proj_folder)
    if not p or not names:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        # One append per prompt, opened 'a': concurrent sessions in the same
        # project interleave lines instead of losing each other's counts.
        with open(p, 'a', encoding='utf-8') as f:
            f.write('\n'.join(n for n in names if n) + '\n')
    except Exception:
        pass


def fold_hits(project_path, proj_folder, mem):
    """Apply the sidecar's counts to *mem* and clear it. Called by the memory
    build, which is already rewriting the graph — so the reinforcement costs
    nothing extra, instead of two atomic writes per prompt."""
    p = hits_log_path(project_path, proj_folder)
    if not p or not os.path.isfile(p):
        return False
    counts = {}
    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            for line in f:
                name = line.strip()
                if name:
                    counts[name] = counts.get(name, 0) + 1
    except OSError:
        return False
    for e in mem.get('entities', []):
        n = counts.get(e.get('name'))
        if n:
            e['hits'] = e.get('hits', 0) + n
            if e.get('type') == 'lesson':
                e['last_used'] = mem.get('session_counter', 0)
    try:
        os.remove(p)
    except OSError:
        pass
    return bool(counts)


def retrieve(project_path, proj_folder, query, budget_tokens=600, log=True):
    """Main entry: {'text', 'tokens', 'items', 'empty'}.

    `log=False` for a PREVIEW. Reinforcement must credit what Claude actually
    saw: `hits` is a term in the eviction score and in recall ranking, so a
    preview that logged would let looking at the memory reshape it — and both
    previews (TUI and GUI) are opened repeatedly on the same query.
    """
    mem = memory.load_memory(project_path, proj_folder)
    if not mem.get('entities') or not (query or '').strip():
        return {'text': '', 'tokens': 0, 'items': [], 'empty': True}
    index = build_index(mem)
    seeds = score_entities(mem, index, query)[:24]
    if not seeds:
        return {'text': '', 'tokens': 0, 'items': [], 'empty': True}
    scored = list(seeds)
    scored += expand_relations(mem, index, seeds[:8], hops=1)
    # second hop only when the budget is comfortably larger than the seed set
    seed_cost = sum(tokens_estimate(e.get('summary', '')) for _s, e in seeds)
    if seed_cost < budget_tokens * 0.5:
        scored += expand_relations(mem, index, seeds[:4], hops=2)
    # dedup keep-max
    best = {}
    for s, e in scored:
        k = e.get('name')
        if s > best.get(k, (0, None))[0]:
            best[k] = (s, e)
    ranked = sorted(best.values(), key=lambda x: (-x[0], x[1].get('name', '')))
    text, toks = render_context(ranked, mem, budget_tokens)
    # Reinforcement: which entities got injected, appended to a sidecar and
    # folded into the graph on the next build.
    #
    # This runs on EVERY UserPromptSubmit. Bumping the counters in the graph
    # here meant re-serialising it and calling memory.save_memory — which
    # performs TWO atomic writes — on every prompt, and two sessions in the
    # same project simply overwrote each other's counts. An append is
    # single-writer-safe and costs one line.
    #
    # Credit what was INJECTED, not everything that ranked: `ranked` is the
    # whole candidate list and render_context emits only what fits the budget,
    # so every prompt inflated `hits` for entities Claude never saw — and
    # `hits*2` is a term in the eviction score.
    included = getattr(render_context, 'last_included', None) or []
    if log and text and included:
        _log_hits(project_path, proj_folder, included)
    return {'text': text, 'tokens': toks, 'items': list(included),
            'empty': not text}


# ── surface estimation (launch UI) ───────────────────────────

def _rule_frontmatter(text):
    """(unit, glob, scoped) as the rule file itself declares them.

    `memrules._sanitize` maps every non-alnum char to '_', so the FILENAME is
    not reversible back to repo/module — two different units can produce the
    same name and '/' is indistinguishable from '-'. The file states both facts
    in its own frontmatter (`memrules.render_rule`), so read them from there.

    `scoped` is False for a file written with the old `globs:` key: Claude Code
    scopes on `paths:` alone and loads everything else into every session, so a
    file claiming a glob it does not honour must not be reported as lazy.
    """
    unit = glob = ''
    scoped = False
    for ln in text.splitlines()[:8]:
        ln = ln.strip()
        if ln == '---' and unit:
            break
        m = re.match(r'^description\s*:\s*"?archeus memory:\s*(.+?)"?\s*$', ln)
        if m:
            unit = m.group(1)
        if re.match(r'^paths\s*:', ln):
            scoped = True
            m = re.match(r'^paths\s*:\s*"?([^"\s].*?)"?\s*$', ln)   # inline form
            if m:
                glob = m.group(1)
        m = re.match(r'^-\s+"?(.+?)"?\s*$', ln)                     # list item
        if m and scoped and not glob:
            glob = m.group(1)
        m = re.match(r'^globs\s*:\s*"?(.+?)"?\s*$', ln)             # legacy, unscoped
        if m and not glob:
            glob = m.group(1)
    return unit, glob, scoped


def estimate_surfaces(project_path, proj_folder, settings):
    """What memory costs per session: digest (always), hook budget, lazy rules."""
    mem = memory.load_memory(project_path, proj_folder)
    digest = memory.build_digest_micro(mem) if mem.get('entities') else ''
    rules = []
    rules_dir = os.path.join(project_path or '', '.claude', 'rules')
    try:
        for nm in sorted(os.listdir(rules_dir)):
            if nm.startswith('archeus-mem-'):
                p = os.path.join(rules_dir, nm)
                txt = open(p, encoding='utf-8', errors='ignore').read()
                unit, glob, scoped = _rule_frontmatter(txt)
                # dicts, not tuples: a 2-tuple serialises as ["name", 12] and
                # every consumer has to know the order. Same fix conventions.py
                # already took for the same reason.
                rules.append({'file': nm, 'tokens': tokens_estimate(txt),
                              'unit': unit, 'glob': glob, 'scoped': scoped,
                              'path': p})
    except OSError:
        pass
    hook_on = bool(settings.get('memory_prompt_hook'))
    return {'digest_tokens': tokens_estimate(digest) if digest else 0,
            'hook_budget': settings.get('memory_budget', 600) if hook_on else None,
            'rules': rules}


def preview_screen(project_path, proj_folder, project_name):
    """What exactly gets injected, surface by surface, with token counts —
    plus a live 'type a prompt → see what the hook would inject' probe.
    TUI-only entry point (ui imports are local by design)."""
    from .ui import pager, text_input
    from .config import load_settings
    s = load_settings()
    est = estimate_surfaces(project_path, proj_folder, s)
    mem = memory.load_memory(project_path, proj_folder)
    digest = memory.build_digest_micro(mem) if mem.get('entities') else '(no memory yet)'

    lines = [f"ALWAYS LOADED — CLAUDE.md memory block  (~{est['digest_tokens']} tok)", '']
    lines += ['  ' + l for l in digest.splitlines()]
    lines += ['', f"LAZY — path-scoped rules ({len(est['rules'])} files, load only when touched)"]
    for r in est['rules']:
        lines.append(f"  {r['file']}  (~{r['tokens']} tok)"
                     + (f"  {r['glob']}" if r.get('glob') else ''))
    if not est['rules']:
        lines.append('  (none generated yet)')
    hook = est['hook_budget']
    lines += ['', "PER PROMPT — recall hook " +
              (f"(ON, budget {hook} tok)" if hook is not None else "(off)")]
    while True:
        key = pager(('ARCHEUS', project_name, 'MEMORY PREVIEW'), lines,
                    hint='t try a prompt   ESC back', extra_keys=('t',))
        if key != 't':
            return
        _try_prompt(project_path, proj_folder, project_name, s)


def _try_prompt(project_path, proj_folder, project_name, settings):
    from .ui import pager, text_input
    q = text_input("Prompt to test:")
    if not q:
        return
    r = retrieve(project_path, proj_folder, q, settings.get('memory_budget', 600),
                 log=False)
    body = r['text'].splitlines() if not r['empty'] else ['(nothing relevant — no injection)']
    pager(('ARCHEUS', project_name, f'HOOK WOULD INJECT (~{r["tokens"]} tok)'),
          body, hint='ESC back')


def memory_status_line(project_path, proj_folder, settings):
    """One-line summary for the launch options screen."""
    try:
        est = estimate_surfaces(project_path, proj_folder, settings)
    except Exception:
        return ''
    if not est['digest_tokens'] and not est['rules'] and est['hook_budget'] is None:
        return ''
    parts = [f"~{est['digest_tokens']} tok always"]
    if est['hook_budget'] is not None:
        parts.append(f"hook <={est['hook_budget']}/prompt")
    if est['rules']:
        parts.append(f"{len(est['rules'])} rules lazy")
    return "memory: " + ' · '.join(parts)
