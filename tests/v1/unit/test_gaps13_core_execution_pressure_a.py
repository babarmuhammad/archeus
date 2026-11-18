"""T-1453: the branches of `archeus/core/execution/pressure.py` that
test_pressure_units.py and test_gaps_core_execution_pressure.py leave open: a
usage source other than the harness's own fails closed (quality 50-52), a signal
writes nothing into the basis it is given and works with no basis (signalled
35-40), and a window of None is as unknown as 0 (reported 29-32).
"""

from types import SimpleNamespace

import pytest

from archeus.core.execution import pressure as P


@pytest.mark.parametrize('source', ['none', 'estimated', None],
                         ids=['none', 'estimated', 'absent'])
def test_a_usage_source_other_than_the_harness_is_unavailable_with_a_figure(source):
    """pressure.py:50-52 — the figure and the window are both there, so only the
    source test stops it being 'reported'. Dropping the `!= 'harness_reported'`
    term leaves a number that nothing measured labelled as measured."""
    ctx, _p = P.reported({'input_tokens': 10}, 100, 'offer', 1)
    ctx = dict(ctx, usage_source=source)
    assert P.quality(ctx, 1) == 'unavailable'
    assert P.view(SimpleNamespace(context=ctx, stream_offset=1, pressure=0.1))['remaining'] is None


def test_a_signal_writes_nothing_into_the_basis_it_was_given():
    """pressure.py:37-39 — `dict(_NONE, **prev)` is a copy, so the signal sets
    signal and signal_seq on the copy and leaves the stored report as it was. An
    in-place update here would rewrite the context of the execution the next
    report is read against."""
    prev, _p = P.reported({'input_tokens': 50000}, 200000, 'offer', 10)
    before = dict(prev)
    ctx = P.signalled(prev, 30)
    assert prev == before
    assert ctx is not prev
    assert (ctx['used_tokens'], ctx['window'], ctx['signal'], ctx['signal_seq']) == \
        (50000, 200000, 'precompact', 30)


def test_a_signal_with_no_earlier_report_is_signalled_and_measures_nothing():
    """pressure.py:35-40 with prev None — the `prev or {}` branch: the basis is
    the empty template plus the signal, and no figure is invented."""
    ctx = P.signalled(None, 5)
    assert (ctx['used_tokens'], ctx['window'], ctx['usage_source']) == (None, None, 'none')
    assert P.quality(ctx, 5) == 'signalled'


def test_a_window_of_None_is_as_unknown_as_zero():
    """pressure.py:29-32 — `window or None` and `if window else` treat None like 0:
    the window stays unknown, its source is 'none', and no ratio is computed."""
    ctx, p = P.reported({'input_tokens': 5000}, None, 'offer', 3)
    assert (ctx['window'], ctx['window_source'], p) == (None, 'none', None)
    assert P.quality(ctx, 3) == 'unavailable'
