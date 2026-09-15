# Simplification log

One section per module: what the code-simplifier agent proposed, what was accepted, what was
rejected and why. Each accepted module is its own commit, so any regression bisects to one file.

Standing rejection rules, applied to every proposal:

- Anything that removes a guard, a validation, an error path, a security check, an
  `encoding=`/`errors=` argument, or a comment explaining *why*.
- Any docstring trimming. The long docstrings here are institutional memory, not verbosity.
- "Consistency" rewrites: a large diff with no behaviour change.
- The agent's TypeScript/React house style, which does not apply to this codebase.

