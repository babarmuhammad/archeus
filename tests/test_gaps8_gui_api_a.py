"""T-1345 — highest-risk uncovered branches of claude_sessions/gui_api.py
lines 868-977 (tip 6b1a30b8; re-located at the worktree tip, same lines).

Candidate list, denial and fail-closed first:
 1. 912      _managed_path_ok prefix boundary: a sibling whose name starts with a
              home name is refused (card probe 1 was a PREMISE that a home root
              is deletable; the _managed_path_ok docstring lists a harness home
              as a managed location, so that premise is not kept as an xfail)
 2. 914      _managed_path_ok: no home prefix and no managed name is refused
 3. 890-892  _cfgdir_ok: a child of an enumerated home is refused
 4. 942-945  check_params: None and '' skip; non-string and unknown-home refuse
 5. 928-933  PARAM_CHECKS: 'path' is not checked (documented)
 6. 956-957  call: body is checked before the endpoint runs
 7. 960-965  call: a KeyError naming a request parameter becomes BadRequest
 8. 966      call: a KeyError naming an internal key is re-raised (500 path)
 9. 909-914  _managed_path_ok normalises '..' before comparing (control)
10. 938-939  check_params: non-dict params return without checks (control)

Closest existing tests: tests/test_security_fixes.py
test_skill_remove_refuses_a_directory_outside_a_managed_root and
test_a_target_cfgdir_the_accounts_do_not_know_is_refused (HTTP level, one
outside path, one bad target_cfgdir value).
Those cover the outside-refusal and the target_cfgdir rejection, not the boundary
branches above, the None/'' skip, the body-before-fn ordering or the KeyError
translation.

Seams: harnesses._homes and harnesses.managed_dir_names are monkeypatched to
synthetic tmp_path homes; endpoints are plain functions passed to gui_api.call.
No server, no real home, no subprocess, no network.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import gui_api
from claude_sessions import harnesses as _harnesses


@pytest.fixture()
def homes(monkeypatch, tmp_path):
    root = tmp_path / 'synth-home'
    root.mkdir()
    managed = {'.agents'}
    monkeypatch.setattr(_harnesses, '_homes',
                        lambda: [('synth', str(root))])
    monkeypatch.setattr(_harnesses, 'managed_dir_names', lambda: set(managed))
    return root


# 912 — a sibling sharing the home's name as a prefix is not inside it
def test_managed_path_refuses_sibling_sharing_home_name_prefix(homes):
    sibling = str(homes) + 'x'
    assert gui_api._managed_path_ok(os.path.join(str(homes), 'child')) is True
    assert gui_api._managed_path_ok(sibling) is False


# 914 — outside every home and without a managed name: refused; under a managed
# name it is accepted
def test_managed_path_refuses_outside_path_and_accepts_managed_name(homes, tmp_path):
    outside = tmp_path / 'elsewhere' / 'notes'
    assert gui_api._managed_path_ok(str(outside)) is False
    project_skill = tmp_path / 'elsewhere' / 'proj' / '.agents' / 'skills' / 'x'
    assert gui_api._managed_path_ok(str(project_skill)) is True


# 890-892 — equality, not prefix: a child of an enumerated home is refused
def test_cfgdir_refuses_child_of_enumerated_home(homes):
    child = homes / 'projects'
    child.mkdir()
    assert gui_api._cfgdir_ok(str(child)) is False
    with pytest.raises(gui_api.BadRequest, match='invalid cfgdir'):
        gui_api.check_params({'cfgdir': str(child)})


# 942-945 — None and '' are skipped; non-string and unknown-home values refuse
def test_check_params_skips_empty_and_refuses_non_string_or_unknown(homes):
    gui_api.check_params({'cfgdir': None, 'enc': '', 'sid': None})
    with pytest.raises(gui_api.BadRequest, match='invalid cfgdir'):
        gui_api.check_params({'cfgdir': 7})
    with pytest.raises(gui_api.BadRequest, match='invalid enc'):
        gui_api.check_params({'enc': 'not encoded!'})


# 928-933 — 'path' is documented as unchecked: an arbitrary path reaches the endpoint
def test_check_params_leaves_path_unchecked(homes, tmp_path):
    arbitrary = str(tmp_path / 'does-not-exist' / 'anywhere')
    gui_api.check_params({'path': arbitrary})
    seen = []
    gui_api.call(lambda q, b: seen.append(q['path']), {'path': arbitrary}, None)
    assert seen == [arbitrary]


# 956-957 — body is checked before the endpoint runs, so a bad body value
# never reaches the endpoint
def test_call_checks_body_before_endpoint_runs(homes, tmp_path):
    calls = []
    body = {'target_cfgdir': str(tmp_path / 'not-a-home')}
    with pytest.raises(gui_api.BadRequest, match='invalid target_cfgdir'):
        gui_api.call(lambda q, b: calls.append((q, b)), {}, body)
    assert calls == []


# 960-965 — a KeyError naming a request parameter is the caller's fault: 400
def test_call_turns_missing_request_parameter_into_bad_request(homes):
    def endpoint(q, b):
        return q['enc']

    with pytest.raises(gui_api.BadRequest, match='missing parameter: enc'):
        gui_api.call(endpoint, {}, None)


# 966 — a KeyError naming an internal key is a real fault and propagates
def test_call_reraises_internal_keyerror(homes):
    def endpoint(q, b):
        return {}['internal_index']

    with pytest.raises(KeyError, match='internal_index'):
        gui_api.call(endpoint, {}, None)


# 909-914 — the path is normalised before comparison: a '..' that climbs out of
# the home is refused, a redundant separator inside it is accepted
def test_managed_path_normalises_traversal_before_comparing(homes, tmp_path):
    escape = os.path.join(str(homes), 'sub', '..', '..', 'elsewhere')
    assert gui_api._managed_path_ok(escape) is False
    inside = os.path.join(str(homes), 'sub', '.', 'x')
    assert gui_api._managed_path_ok(inside) is True


# 938-939 — non-dict params return without checks and reach the endpoint as given
def test_call_passes_non_dict_params_through_unchecked(homes):
    seen = []
    gui_api.call(lambda q, b: seen.append(q), ['enc'], None)
    assert seen == [['enc']]
    gui_api.check_params(['cfgdir', 'enc'])
