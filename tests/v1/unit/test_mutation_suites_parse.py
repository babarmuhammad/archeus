"""Every mutant of every phase suite parses — and type-checks, for an SPA source —
once applied (p18-design-gate §22.1 F7, §22.2.1).

A mutant that does not parse fails every test that loads it, whatever that test
asserts, so a runner counting it as killed reports an invariant as guarded when
nothing checked it (P18's M17 was such a mutant). `mutate_p11._apply` refuses a
broken mutant before any run for the suites built on it (P11-P18); this gate
covers all eleven, P8-P10's own engines included. TypeScript is checked only where
node and clients/app/node_modules exist (the Node-free test job checks Python)."""

import importlib
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import mutate_p11  # noqa: E402

SUITES = ['mutate_p%d' % n for n in range(8, 19)]
TS_OK = bool(shutil.which('node')) and os.path.isdir(
    os.path.join(ROOT, 'clients', 'app', 'node_modules', 'typescript'))


def _mutants(name):
    for m in importlib.import_module(name).MUTATIONS:
        if len(m) == 6:                                  # P8-P10: (id, what, rel, old, new, tests)
            yield m[0], [(m[2], m[3], m[4])]
        else:                                            # P11+: (id, what, edits, tests)
            yield m[0], m[2]


def _mutated(edits):
    files = {}
    for rel, old, new in edits:
        if rel not in files:
            with open(os.path.join(ROOT, rel), encoding='utf-8', newline='') as f:
                files[rel] = f.read()
        assert files[rel].count(old) == 1, (rel, old)
        files[rel] = files[rel].replace(old, new)
    return files


@pytest.mark.parametrize('suite', SUITES)
def test_every_mutant_parses_once_applied(suite):
    broken, ts = [], []
    for mid, edits in _mutants(suite):
        for rel, text in _mutated(edits).items():
            if rel.endswith(('.ts', '.tsx')):
                if TS_OK:
                    ts.append((mid, rel, text))
                continue
            err = mutate_p11.parse_error(rel, text)
            if err:
                broken.append('%s %s: %s' % (mid, rel, err))
    # an SPA source is type-checked as the build would (noUnusedLocals included)
    for (mid, rel, _t), err in zip(ts, mutate_p11.ts_errors([(r, t) for _m, r, t in ts]) if ts else []):
        if err:
            broken.append('%s %s: %s' % (mid, rel, err))
    assert not broken, broken


def test_a_broken_mutant_is_refused_before_it_can_count():
    assert mutate_p11.parse_error('x.py', 'if x:\n    pass\nelse y\n')
    assert mutate_p11.parse_error('x.py', 'if x:\n    pass\n') is None
    assert mutate_p11.parse_error('x.json', '{"a": 1,}')
    if TS_OK:
        # P18's M17 as first written: the `if` replaced, its `else` left dangling
        assert mutate_p11.parse_error('loop.ts', 'function f() {\n  g();\n  else h();\n}\n')
        assert mutate_p11.parse_error('loop.ts', 'function f(): void {\n  g();\n}\n') is None
        assert mutate_p11.parse_error('v.tsx', 'const a = <div>{x}</div>;\n') is None
        assert mutate_p11.parse_error('v.tsx', 'const a = <div>{x}</span>;\n')
        # an SPA source must also type-check as the build does: an import left unused
        loop = os.path.join('clients', 'app', 'src', 'graph', 'loop.ts')
        src = open(os.path.join(ROOT, loop), encoding='utf-8').read()
        assert mutate_p11.parse_error(loop, src) is None
        assert 'never read' in mutate_p11.parse_error(loop, 'const unused = 1;\n' + src)
