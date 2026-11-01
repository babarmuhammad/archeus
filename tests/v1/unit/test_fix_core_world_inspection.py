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


def test_a_commented_out_pyproject_dependency_is_not_a_dependency():
    text = '[project]\ndependencies = [\n  # "django>=4.2",\n  "fastapi>=0.110",\n]\n'
    assert [d['name'] for d in inspection._pyproject(text)] == ['fastapi']


@pytest.mark.parametrize('body', ['[]', '"x"', '123', '{"dependencies": ["a"]}'])
def test_a_package_json_that_is_not_the_expected_shape_is_a_note_not_a_crash(tmp_path, body):
    (tmp_path / 'package.json').write_text(body)
    notes = []
    inspection._dependencies(str(tmp_path), notes)
    inspection._commands(str(tmp_path), [])
