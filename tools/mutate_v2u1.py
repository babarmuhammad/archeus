"""The V2-U1 mutation suite (V2 real build plan §4.4): break each invariant of the
bundle budget, the V2 tokens and the spine, run the test written for it, and
require it to fail.

    py tools/mutate_v2u1.py            every mutation
    py tools/mutate_v2u1.py U01 U05    only these

The runner is tools/mutate_p18.py's (tools/mutate_p11.py's snippet engine): each
mutation replaces exact snippets (each must occur once), runs its tests and
restores the files whatever happens; a mutation the tests do not catch
("survived") fails the run. A mutant guarded by the bundle budget or a browser
test rebuilds the SPA before the run and again after the restore. It edits
sources: run it with nothing else running against the tree.
"""

import base64
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402  (its runner)

MAIN = 'clients/app/src/main.tsx'
BUDGET = 'node:test/budget.test.ts'


def _padding(n):
    out, h = b'', hashlib.sha256(b'v2u1')
    while len(out) < n:
        h = hashlib.sha256(h.digest())
        out += h.digest()
    return base64.b64encode(out[:n]).decode()


MUTATIONS = [
    ('U01', 'a 50 KB incompressible string shipped in the bundle', [(MAIN,
     "import App from './App';",
     "import App from './App';\nconsole.log('" + _padding(50_000) + "');")],
     [BUDGET]),
]

_needs_build = mutate_p18._needs_build
mutate_p18._needs_build = lambda tests: _needs_build(tests) or BUDGET in tests

if __name__ == '__main__':
    unknown = set(sys.argv[1:]) - {m[0] for m in MUTATIONS}
    if unknown:
        raise SystemExit('Unknown mutant IDs: ' + ', '.join(sorted(unknown)))
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
