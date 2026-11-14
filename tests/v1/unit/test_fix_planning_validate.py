"""Regression tests for hostile-audit findings on archeus/core/planning/validate.py."""

from types import SimpleNamespace

import pytest

from archeus.core import engine
from archeus.core.planning import validate


@pytest.mark.parametrize('a,b', [
    ('src/app.py', './src/app.py'),
    ('src/app.py', 'src//app.py'),
    ('src', 'src/x.py'),
    ('src/', 'src/x.py'),
    ('C:\\Repo\\a.py', 'c:\\repo\\a.py'),
    ('SRC/*.py', 'src/a.py'),
    ('src/x/../a.py', 'src/a.py'),
    ('src/../docs/a.md', 'docs/a.md'),
    ('.', 'src/a.py'),
])
def test_two_spellings_of_one_path_overlap(a, b):
    assert validate.overlap(a, b) and validate.overlap(b, a)


def test_siblings_with_a_shared_name_prefix_do_not_overlap():
    assert not validate.overlap('src', 'srcfoo/x.py')


@pytest.mark.parametrize('a,b', [('src/app.py', './src/app.py'), ('src/app.py', 'src//app.py'),
                                 ('SRC/a.py', 'src/a.py'), ('src/x/../a.py', 'src/a.py'),
                                 ('.', 'src/a.py')])
def test_the_engine_conflicts_the_spellings_validate_overlaps(a, b):
    task = lambda g: SimpleNamespace(workspace_mode='worktree', touches=[g])
    assert engine._conflict(task(a), task(b))
