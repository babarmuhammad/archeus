"""A deferred import inside a branch must not reuse a module-level name.

`from .config import C_RESET` inside a function makes C_RESET a LOCAL of that
function, and every closure defined in it then resolves the name from this scope
instead of the module. That is harmless while the import runs on every call.
Put it inside a branch and the name is unbound on every call where the branch
does not run — and the failure surfaces somewhere else entirely:

    NameError: cannot access free variable 'C_RESET'
               where it is not associated with a value in enclosing scope

It shipped once, in `main.run()`, under `if _warn:` — a branch that only runs
while two packages are co-installed. It passed locally because they were, and
went red on all six CI jobs because they were not. `ruff`'s F821 does not see
it: the name IS bound, on some paths.

The rule is deliberately not "no local imports". Deferred imports are
load-bearing here — the statusline's import budget is built on them, and
`config` defers `events` to break a cycle. What is banned is the narrow shape
that actually breaks: a conditional import that shadows a module-level name
which is also READ outside that branch.

Mutation-verified: reintroducing the exact `main.run()` defect makes this fail
and reports `main.py:229 run -> C_RESET`; the clean tree reports nothing.
"""
import ast
import io
import os

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'claude_sessions')


def _module_level_names(tree):
    out = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out.add(a.asname or a.name.split('.')[0])
    return out


def test_no_conditional_import_shadows_a_name_used_outside_its_branch():
    offenders = []
    for fname in sorted(os.listdir(SRC)):
        if not fname.endswith('.py'):
            continue
        tree = ast.parse(io.open(os.path.join(SRC, fname), encoding='utf-8').read())
        top = _module_level_names(tree)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # a direct statement of the function body runs on every call, so it
            # binds the name before anything can read it — that shape is safe
            unconditional = {id(s) for s in fn.body}
            for branch in fn.body:
                inside = {id(n) for n in ast.walk(branch)}
                for imp in [n for n in ast.walk(branch)
                            if isinstance(n, (ast.Import, ast.ImportFrom))]:
                    if id(imp) in unconditional:
                        continue
                    for a in imp.names:
                        bound = a.asname or a.name.split('.')[0]
                        if bound not in top:
                            continue
                        read_outside = [n for n in ast.walk(fn)
                                        if isinstance(n, ast.Name) and n.id == bound
                                        and isinstance(n.ctx, ast.Load)
                                        and id(n) not in inside]
                        if read_outside:
                            offenders.append(
                                '%s:%d  %s() imports %r inside a branch, but it is '
                                'read at line %d outside it'
                                % (fname, imp.lineno, fn.name, bound,
                                   read_outside[0].lineno))
    assert not offenders, (
        'conditional imports shadowing a module-level name:\n  '
        + '\n  '.join(offenders)
        + '\n\nUse a name the module does not bind (`from . import config as _cfg`)'
          ' and read the attribute at use time.')
