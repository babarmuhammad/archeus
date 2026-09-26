"""The traceability table IS the judge's floor (testing-strategy §1.1, §2, §4).

docs/architecture/testing-strategy.md §2 maps every acceptance source to a test
file and a phase range. This file parses that table and fails when:

- a listed test file does not exist, or a judge test file is not listed;
- a row's files hold no test function (the floor is derived from the table,
  never typed as a number);
- an expected failure is not `xfail(strict=True, reason="phase:P<n>")`;
- a tag names a phase outside its row's range, or no function of a row carries
  the row's LAST phase while any is still pending (so a row cannot go green
  before the phase that finishes it);
- a judge scenario imports Core internals — it may use the CoreClient only.

`strict=True` is what turns "a function passed early" into a failure until its
marker is removed; this file makes sure every marker is shaped for that.
"""

import ast
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
V1 = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(V1))
DOC = os.path.join(ROOT, 'docs', 'architecture', 'testing-strategy.md')

TAG = re.compile(r'phase:(P\d+(?:\.5)?)$')
PHASE = re.compile(r'P(\d+(?:\.5)?)')


def phase_num(p):
    return float(p.lstrip('P'))


def _rows():
    """[(id, [test paths], (first, last), phases_text)] from the §2 table."""
    text = open(DOC, encoding='utf-8').read()
    body = text[text.index('## 2. Traceability'):]
    body = body[:body.index('\n## ', 1)]
    rows = []
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) != 5 or cells[0] in ('ID', '') or set(cells[0]) <= set('-'):
            continue
        rid, _req, _also, tests, phases = cells
        files = re.findall(r'`([^`]*test_[^`]*\.py)`', tests)
        nums = []
        for a, b in re.findall(r'P(\d+(?:\.5)?)(?:\s*[–-]\s*P(\d+(?:\.5)?))?', phases):
            nums += [float(a)] + ([float(b)] if b else [])
        assert files and nums, 'unparseable traceability row: %s' % line
        paths = [os.path.join(ROOT, f.replace('/', os.sep)) if '/' in f
                 else os.path.join(HERE, f) for f in files]
        rows.append((rid, paths, (min(nums), max(nums)), phases))
    return rows


def _xfail_reason(dec):
    """(strict, reason) of an `@pytest.mark.xfail(...)` decorator, else None."""
    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == 'xfail'):
        return None
    kw = {k.arg: k.value for k in dec.keywords}
    strict = isinstance(kw.get('strict'), ast.Constant) and kw['strict'].value is True
    reason = kw['reason'].value if isinstance(kw.get('reason'), ast.Constant) else None
    return strict, reason


def _functions(path):
    """[(name, tag or None, problem or None)] for every test function in a file."""
    tree = ast.parse(open(path, encoding='utf-8').read(), path)
    out = []
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith('test_')):
            continue
        marks = [m for m in map(_xfail_reason, node.decorator_list) if m]
        if not marks:
            out.append((node.name, None, None))
            continue
        (strict, reason), problem = marks[0], None
        m = TAG.match(reason or '')
        if len(marks) > 1:
            problem = 'more than one xfail marker'
        elif not strict:
            problem = 'xfail without strict=True'
        elif not m:
            problem = 'reason %r is not "phase:P<n>"' % (reason,)
        out.append((node.name, m.group(1) if m else None, problem))
    return out


ROWS = _rows()


def test_the_table_parses_into_every_row_the_strategy_names():
    ids = [r[0] for r in ROWS]
    assert len(ids) == len(set(ids)), 'a traceability id appears twice'
    for must in ('SK', 'S1', 'S15', 'SP3', 'G1', 'G8'):
        assert must in ids


def test_every_listed_test_file_exists():
    missing = [os.path.relpath(p, ROOT) for _r, paths, _rng, _t in ROWS
               for p in paths if not os.path.isfile(p)]
    assert not missing, 'traceability names test files that do not exist: %s' % missing


def test_every_judge_test_file_is_listed():
    listed = {os.path.normcase(p) for _r, paths, _rng, _t in ROWS for p in paths}
    here = {os.path.normcase(os.path.join(HERE, f)) for f in os.listdir(HERE)
            if f.startswith('test_') and f.endswith('.py') and f != 'test_traceability.py'}
    unlisted = sorted(os.path.basename(p) for p in here - listed)
    assert not unlisted, 'judge tests missing from the traceability table: %s' % unlisted


def test_the_floor_is_the_table():
    """At least one test function per row — so the judge's size can only
    shrink by deleting a row from the documented table."""
    empty = [rid for rid, paths, _rng, _t in ROWS
             if not sum(len(_functions(p)) for p in paths if os.path.isfile(p))]
    assert not empty, 'rows with no test function: %s' % empty
    total = sum(len(_functions(p)) for _r, paths, _rng, _t in ROWS for p in paths)
    assert total >= len(ROWS)


def test_every_pending_function_is_tagged_within_its_rows_phases():
    problems = []
    for rid, paths, (first, last), text in ROWS:
        tags = []
        for p in paths:
            for name, tag, problem in _functions(p):
                where = '%s %s::%s' % (rid, os.path.basename(p), name)
                if problem:
                    problems.append('%s: %s' % (where, problem))
                elif tag and not first <= phase_num(tag) <= last:
                    problems.append('%s: %s is outside %s' % (where, tag, text))
                if tag:
                    tags.append(phase_num(tag))
        if tags and max(tags) != last:
            problems.append('%s: still pending, but no function waits for its last '
                            'phase (%s)' % (rid, text))
    assert not problems, '\n'.join(problems)


def test_judge_scenarios_never_import_core_internals():
    """The judge runs against the public surface only, so it survives every
    refactor (testing-strategy intro). `archeus` belongs to the bindings."""
    offenders = []
    for f in sorted(os.listdir(HERE)):
        if not (f.startswith('test_') and f.endswith('.py')):
            continue
        tree = ast.parse(open(os.path.join(HERE, f), encoding='utf-8').read())
        for node in ast.walk(tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ''] if isinstance(node, ast.ImportFrom)
                     else [])
            if any(n == 'archeus' or n.startswith(('archeus.', 'claude_sessions'))
                   for n in names):
                offenders.append('%s:%d' % (f, node.lineno))
    assert not offenders, offenders
