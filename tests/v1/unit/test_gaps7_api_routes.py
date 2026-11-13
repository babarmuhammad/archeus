"""T-1322 — the ten highest-risk uncovered branches of archeus/api/routes.py
lines 1360-1383 inclusive (tip d429bf96 has the same code at the same lines:
`_compile` 1360-1366, `_COMPILED` 1369, `match` 1372-1383).

The branches, denial and fail-closed first, then boundaries, then error paths:

 1. routes.py:1366  the terminal `\\Z` anchor, over EVERY static row, not four:
    a static path plus a trailing LF is unknown (404), so `$` for `\\Z` fails.
 2. routes.py:1362  the wildcard `/*` row keeps the exact remainder and refuses
    a newline inside it (group fidelity, not a bare truthy match).
 3. routes.py:1366  a literal suffix after a parameter plus a trailing LF does
    not match the exact template.
 4. routes.py:1374-1383  an unsupported method on an LF-suffixed static path is
    404, never the known-route 405 (`known` is only set by a real match).
 5. routes.py:1364  a `{parameter}` keeps an LF inside its VALUE whole: the
    `[^/]+` class allowance, not a truncation and not the terminal anchor.
 6. routes.py:1366  two terminal LFs refuse an exact literal too.
 7. routes.py:1366  a CRLF or a bare CR suffix refuses: no newline normalisation.
 8. routes.py:1362  an empty wildcard and a newline-only wildcard refuse alike;
    no wildcard semantics are invented beyond that.
 9. routes.py:1376-1380  an exact parameter route returns its complete named
    capture and the ROUTES row itself, unchanged by a second match.
10. routes.py:1383  a valid prefix plus a non-newline suffix is always 404: a
    prefix accept in place of `\\Z` would answer it.

Existing coverage, not copied: tests/v1/unit/test_gaps3_api_routes_f.py
(`test_a_path_that_only_adds_a_trailing_newline_is_not_the_rows_path` covers
four static paths, one wildcard and `/a.b` with one LF;
`test_a_path_known_only_through_a_parameter_answers_405_and_never_404` covers a
405 for parameter rows). That file's assertion on a parameter LF is explicitly
"not asserted here"; probe 5 pins the allowance as current behaviour and is not
a strict xfail: the anchor refuses the terminal LF, and the value class is a
separate owner decision (see the report). No strict xfail is kept by this file:
at this tip no probe disagrees with the source.

Platform-neutral: no path separator, no OS call, no environment read. Only the
route table and `match` are exercised; nothing listens, runs or writes.
"""

import pytest

from archeus.api import routes


def _refused(method, path):
    with pytest.raises(routes.Refused) as e:
        routes.match(method, path)
    return e.value


def _static_rows():
    return [r for r in routes.ROUTES
            if '{' not in r.path and not r.path.endswith('/*')]


def test_every_static_row_refuses_a_trailing_lf_as_unknown():
    """Kills: `$` in place of `\\Z` at routes.py:1366. `$` matches before a
    final newline, so `^/v1/digest$` would accept `/v1/digest\\n`. The existing
    regression names four static rows; this runs every one of them."""
    rows = _static_rows()
    assert len(rows) > 20, len(rows)
    for r in rows:
        assert routes.match(r.method, r.path)[0] is r, r.path   # control
        try:
            hit = routes.match(r.method, r.path + '\n')[0]
        except routes.Refused:
            continue
        assert hit is not r, r.path
        assert '{' in hit.path or hit.path.endswith('/*'), (r.path, hit.path)


def test_a_wildcard_keeps_the_exact_remainder_and_refuses_a_newline_inside_it():
    """Kills: changing the wildcard group at routes.py:1362 from `.+` to a
    truthy-only match, or dropping `\\Z`, which would let `a\\nb.js` through with
    the wrong capture. The remainder is compared exactly, slash included."""
    route, params = routes.match('GET', '/assets/a/b.js')
    assert route.path == '/assets/*'
    assert params == {'path': 'a/b.js'}, params
    e = _refused('GET', '/assets/a\nb.js')
    assert (e.status, e.code) == (404, 'not_found')


def test_a_literal_suffix_after_a_parameter_refuses_a_trailing_lf():
    """Kills: the literal `re.escape(p)` pieces of routes.py:1364-1366 being
    dropped or made optional, and the `\\Z` anchor. Each row has a literal
    suffix after its `{parameter}`, so the template is exact only without the LF."""
    for template in ('/v1/missions/{id}/timeline', '/v1/executions/{id}/stream',
                     '/v1/sessions/{id}/brief', '/v1/knowledge/{id}/confirm'):
        method = next(r.method for r in routes.ROUTES if r.path == template)
        path = template.replace('{id}', 'abc')
        route, params = routes.match(method, path)
        assert (route.path, params) == (template, {'id': 'abc'}), path
        e = _refused(method, path + '\n')
        assert (e.status, e.code) == (404, 'not_found'), path


def test_an_unsupported_method_on_an_lf_path_is_404_and_never_405():
    """Kills: setting `known = True` before the anchored match at routes.py:1376
    (or dropping the `if m:` guard), which would turn a path no row names into
    a 405 that lists a method for a route that does not exist."""
    assert _refused('DELETE', '/v1/missions').status == 405   # control
    e = _refused('DELETE', '/v1/missions\n')
    assert (e.status, e.code) == (404, 'not_found')
    e = _refused('PATCH', '/v1/digest\n')
    assert (e.status, e.code) == (404, 'not_found')


def test_a_parameter_keeps_an_lf_inside_its_value_whole_and_the_anchor_is_not_the_cause():
    """Kills: a `[^/]+` replaced by a narrower class, or a capture truncated at
    the newline. The class allows a newline in a VALUE by design, so the value
    is the whole `abc\\n`; it is pinned here, and the terminal anchor still
    refuses the same LF after a literal suffix (see the test above)."""
    route, params = routes.match('GET', '/v1/missions/abc\n')
    assert route.path == '/v1/missions/{id}'
    assert params == {'id': 'abc\n'}, params


def test_two_terminal_lfs_refuse_an_exact_literal():
    """Kills: a mutation that strips one trailing newline before matching
    (`path.rstrip` or `path[:-1]`), which would accept `/v1/digest\\n` from
    `/v1/digest\\n\\n` as well."""
    e = _refused('GET', '/v1/digest\n\n')
    assert (e.status, e.code) == (404, 'not_found')
    assert routes.match('GET', '/v1/digest')[0].path == '/v1/digest'   # control


def test_a_crlf_or_bare_cr_suffix_refuses_and_nothing_normalises_the_line_end():
    """Kills: a line-end normalisation added to `match`. `\\r\\n` and `\\r` are
    not `\\Z`, so neither reaches a row; the bare path still does."""
    for path in ('/v1/digest\r\n', '/v1/digest\r'):
        e = _refused('GET', path)
        assert (e.status, e.code) == (404, 'not_found'), repr(path)
    assert routes.match('GET', '/v1/digest')[0].path == '/v1/digest'


def test_an_empty_wildcard_and_a_newline_only_wildcard_refuse_alike():
    """Kills: a wildcard that accepts an empty or newline-only remainder
    (`.+` to `.*`, or a DOTALL flag). The contract is only that both refuse the
    same way; no capture is asserted for them."""
    a = _refused('GET', '/assets/')
    b = _refused('GET', '/assets/\n')
    assert (a.status, a.code) == (b.status, b.code) == (404, 'not_found')


def test_an_exact_parameter_route_returns_its_whole_capture_and_leaves_the_row_alone():
    """Kills: returning a copy of the row, a capture keyed by the wrong group
    name, or a second match that reads state the first one left (routes.py:1376
    to 1380). The returned row is the ROUTES entry itself, identical each time."""
    first_route, first_params = routes.match('GET', '/v1/missions/abc')
    again_route, again_params = routes.match('GET', '/v1/missions/abc')
    assert first_params == again_params == {'id': 'abc'}
    assert first_route is again_route
    assert any(first_route is r for r in routes.ROUTES)
    assert first_route.path == '/v1/missions/{id}'


def test_a_valid_prefix_with_a_nonnewline_suffix_is_always_404():
    """Kills: dropping `\\Z` at routes.py:1366 or the `re.match` anchor at
    routes.py:1376 in favour of a prefix search. Each prefix is a real row, so
    only the end anchor separates the exact path from the extended one."""
    for path in ('/v1/digest/extra', '/v1/health/x', '/v1/missions/abc/extra',
                 '/v1/missions/abc/timeline/x', '/manifest.webmanifest/x'):
        e = _refused('GET', path)
        assert (e.status, e.code) == (404, 'not_found'), path
