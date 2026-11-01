"""Regression tests for hostile-audit findings on archeus/core/planning/validate.py."""

import pytest

from archeus.core import engine
from archeus.core.planning import validate


@pytest.mark.parametrize('a,b', [
    ('src/app.py', './src/app.py'),
    ('src/app.py', 'src//app.py'),
    ('src', 'src/x.py'),
    ('src/', 'src/x.py'),
])
def test_two_spellings_of_one_path_overlap(a, b):
    assert validate.overlap(a, b) and validate.overlap(b, a)


def test_siblings_with_a_shared_name_prefix_do_not_overlap():
    assert not validate.overlap('src', 'srcfoo/x.py')


@pytest.mark.parametrize('a,b', [('src/app.py', './src/app.py'), ('src/app.py', 'src//app.py')])
def test_the_engine_conflicts_two_spellings_of_one_path(a, b):
    assert engine._overlap(a, b)
