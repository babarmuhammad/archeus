# Simplification log

One section per module: what the code-simplifier agent proposed, what was accepted, what was
rejected and why. Each accepted module is its own commit, so any regression bisects to one file.

Standing rejection rules, applied to every proposal:

- Anything that removes a guard, a validation, an error path, a security check, an
  `encoding=`/`errors=` argument, or a comment explaining *why*.
- Any docstring trimming. The long docstrings here are institutional memory, not verbosity.
- "Consistency" rewrites: a large diff with no behaviour change.
- The agent's TypeScript/React house style, which does not apply to this codebase.

Baseline before any change: `2335 passed, 1 skipped` in 4m38s, `ruff` clean, `smoke_gui` exit 0.

## claude_sessions

### hookrules.py — nothing proposed

Two constants and a docstring that is the whole point of the file.

### notify.py — 1 proposed, 1 accepted

Accepted: the hand-written `q()` XML escaper is `xml.sax.saxutils.escape`, which does the same
three substitutions and names the operation. The local import keeps it off the module import path,
which matters because hook entry points import this.

### denygen.py — 1 proposed, 1 accepted

Accepted: the `out` list plus a parallel `seen` set, maintained in lockstep to dedupe by deny
pattern, becomes one dict keyed by the pattern. `sorted(out.items())` returns exactly what
`sorted(out)` did — the patterns are unique, so the sort never reached the tuple's second element.

### search.py — 2 proposed, 2 accepted

Accepted: `global_search` re-projected each dict row from `build_search_index` into a positional
7-tuple, then recomputed `os.path.basename(ppath) or ppath` and `format_age(mtime).strip()` once
per keystroke — both already stored on the row. It reads the fields now, and the comment that
existed to explain the positional indices goes with them. Accepted: the unused `C_SEL` import
(not caught by the lint set, which is deliberately bug-finding rules only).

### health.py — 3 proposed, 3 accepted

Accepted: `Counter` instead of a hand-rolled tally, and one `.split()` per Bash block instead of
two — this is the hot loop over every transcript in a project. `most_common()` is
`sorted(..., reverse=True)`, which is stable, so ties keep the order the old `key=lambda kv: -kv[1]`
gave them. Accepted: the dead `_TOOL_RE` (nothing references it; the prefilter does that job).
Accepted: the allowlist proposal built its `permissions` dict by copying twice through
`setdefault`; one literal keeps the same no-mutation guarantee.

### skillscan.py — 1 proposed, 1 accepted

Accepted, and it is the only thing worth touching in a security scanner: the zero-width/bidi
character class was written out twice — once in the rule that FLAGS it, once in the sanitiser that
strips it from the excerpt. Those two must never drift, or the report re-emits the character it
just warned about. `_HIDDEN_CHARS` is the one definition. Nothing else was proposed against, and
`_RULES`, `_MAX_BYTES`, the manifest-first ordering, the disclaimer and `review_gate` are untouched.

### conventions.py — 3 proposed, 3 accepted

Accepted: the 0.6 token-overlap threshold and its formula were written twice, in `_candidates` and
in `pin_convention`, while the module's contract is that pinning pins exactly what the clustering
counted. `CLUSTER_OVERLAP` and `_same_rule()` are the one copy. `lessons._jaccard` was deliberately
NOT reused: it takes strings and re-tokenises per comparison, and the two thresholds are
independent policy. Accepted: the promotion sentence, which nested a conditional inside an f-string
that was then concatenated with a second conditional. Accepted: the block markers are found once
instead of six times across two branches.

### review.py — 3 proposed, 3 accepted

Accepted: the findings-shape chained ternary becomes if/elif/else — the branch structure is the
point. Accepted: `_supports_color()` was called once per printed line, inside the print argument,
where it also straddled the `'  ' +` concatenation; it is sampled once. Accepted: the `--staged`
branch in the arg loop was a no-op — the flag is read before the loop, and it starts with `--`, so
it could never reach the path branch.

### diffview.py — 4 proposed, 4 accepted

Accepted: the same six-line lenient read was written three times and all three left the handle to
the garbage collector; `_read_text()` is the one copy, with a `with` block and the same `''` on
every failure. Accepted: `confirm()`'s `pending` variable was never assigned anything but `None` —
half of `claude_md.py`'s input lookahead, copied without the half that sets it, which made the loop
look like it buffered input. Accepted: the function-local `import json as _json` beside a
module-level `json`. Accepted: `last_change`'s `if idx:` only added nesting, since `reversed([])`
iterates zero times.

### render.py — 3 proposed, 3 accepted

Accepted: `disp_width` and `trunc` each spelled out the combining/east-asian width rule that every
width calculation in the TUI depends on, one of them as a line-continued nested ternary;
`_char_width()` is the single copy. Accepted: `hint_keys`'s inner helper was named `fit` and
shadowed the module-level `fit()` for the rest of the function — it is `pack` now. Accepted: an
`f'...'` separator with no placeholders.

### migrate.py — 1 proposed across 674 lines, 1 accepted

Accepted: `not stale` inside a comprehension whose result is `+=`'d onto `stale` reads as a
per-item test against a growing list; it is a constant, because the right-hand side is built before
`__iadd__` runs. Said with an `if` now.

Nothing else, and the reason is worth keeping: `tools/_mut_migration.py` stores ~30 **exact source
strings** from this module as mutation anchors and fails with "anchor not found" if one moves.
Every other candidate landed on one of them, so the "small" diff was really a two-file diff against
a gate. Separately, hoisting the duplicated enc-folder walk would reorder `_migrate_project`
against `paths.find_actual_path`, whose cache keys on that folder's mtime — so it would not have
been behaviour-preserving either.

**Flagged, not changed** (it is a behaviour change, so it fails the brief): `migrate.py:253`
compares the repointed string against the **raw** dict value — `fixed = _repoint(str(h.get('command', '')), …)`
then `if fixed != h.get('command')`. A hook whose `command` is missing or not a string therefore
always compares unequal, is coerced to `''`, records a bogus `moved` entry and triggers one
`hooks._save` on a start-up path. The statusLine branch twelve lines below already does it the safe
way (`cur = str(...)`, compared against `cur`). It self-heals after one write, so it is a wart
rather than a bug — for whoever owns the module to decide.

## tools

### gen_api_docs.py — 2 proposed, 1 accepted

Accepted: copy-then-`update` for the two route tables is one merge literal with the same
precedence. **Rejected**: moving the eight hand-appended job-route lines into a module-level
markdown constant. It is a generator for a committed file, the win is cosmetic, and the proposal
carried a transcription hazard (the trailing `parts.append('')` has to disappear into the literal's
final newline) — a diff whose only risk is transcription, for no complexity removed.

### gen_cluster_spec.py — 2 proposed, 1 accepted

Accepted: `payload()` built a dict that `_body()` immediately re-keyed with the same `CS.EXPORTED`
loop, and nothing else called it. **Rejected**: splitting `main()` into a write path and a check
path — a medium diff on a generator for a clarity-only win, and the existing loop is twenty
readable lines.

### gen_plugin.py — 2 proposed, 2 accepted

Accepted: `io.open` **is** `builtins.open` on Python 3 — a Python 2 shim in a tool run as `py -3`.
Every `encoding=` and `newline=` argument kept verbatim, so `plugin/skills/**` bytes do not move
(`--check` confirms). Accepted: `_wanted`'s `body` holds the file split into lines and is used to
separate the frontmatter *from* the body, so it is `lines`. One rename site was missed on the first
pass and `ruff`'s `F821` caught it before anything ran — which is the argument for the narrow lint
set, in miniature.

### make_icon.py — 1 proposed, 1 accepted

Accepted: `l, t, r, b` → `left, top, right, bottom`. `l` is the name that reads as `1`, and this is
the one piece of arithmetic in the file anyone will need to re-derive. Identical crop box.

### verify_model_routing.py — 3 proposed, 3 accepted

Accepted: `model and model not in SYNTHETIC` was written four times, twice inside 130-character set
comprehensions; `_reported()` is the one copy. Accepted: `if not m: return False` below the
`SYNTHETIC` check could never fire, because `SYNTHETIC` contains the empty string. Accepted: the
PASS/FAIL if/else expressed one boolean twice; same stdout line, same exit codes.

### inspect_cluster.py — 1 proposed, 1 accepted

Accepted, and it was a live defect rather than a simplification: the two `sys.path` entries were
hardcoded to `D:\Claude`, so in any other checkout the tool imported the OTHER tree's `stage.js`
and `gui.py` — it graded a copy, which is exactly what its docstring says it exists to avoid.

### capture_graph_gif.py — 1 proposed, 1 accepted

Accepted: `os.path.dirname(os.path.abspath(x))` is never empty, so the `or '.'` fallback could not
be taken.

### probe_layout_qt.py — 2 proposed, 2 accepted

Accepted: `tries = [0]` is a Python 2 closure workaround; `nonlocal` says what it is and stops
`tries[0] > 60` reading as an index. Same 60-poll budget, same 250 ms re-poll. Accepted: `chr(10)`
in a plain string is a newline written the long way.

### indexnow.py — nothing proposed

The tri-state `key_is_served` return is deliberately printed, the retry branch carries its measured
justification, and every guard is load-bearing.
