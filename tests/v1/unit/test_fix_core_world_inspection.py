"""Regression tests for hostile-audit findings on archeus/core/world/inspection.py."""

import os

import pytest

from archeus.core.world import inspection


@pytest.mark.parametrize('ref', ['../../secret', 'refs/../../secret', 'refs/../../../secret'])
def test_a_head_ref_cannot_point_outside_the_gitdir(tmp_path, ref):
    gd = tmp_path / 'r' / '.git'
    os.makedirs(gd)
    for d in (tmp_path, tmp_path / 'r'):
        (d / 'secret').write_text('a' * 40)
    (gd / 'HEAD').write_text('ref: ' + ref)
    with pytest.raises(inspection.Unreadable):
        inspection.head_revision(str(tmp_path / 'r'))
