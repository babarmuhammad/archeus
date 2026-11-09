"""T-752: the highest-risk unasserted branches of the pure half of ADR-0047
(archeus/core/execution/pressure.py) that test_pressure_units.py and
test_context_capacity.py leave open: the fail-closed quality and describe
denials, the `0 is a measurement, not an unknown` and offset boundaries, the
shared-template isolation, the input-figure filter, and the hand-off reason at
the frozen threshold itself.

Pure module: no OS, no clock, no harness, no temp files. Unknown stays None —
every test below fails closed with the source: a basis that cannot be measured
must read `unavailable` with no number, never 0 and never a crash."""

from archeus.core.domain import entities, ids
from archeus.core.execution import pressure as P


def _e(ctx=None, offset=0, pressure=None):
    return entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                              mission_id=ids.new_id('mission'), context=ctx,
                              stream_offset=offset, pressure=pressure, state='RUNNING')


def _ctx(**over):
    """a basis as the record stores it, padded from the module's own template"""
    return dict(P._NONE, **over)


# ── fail-closed denials (quality and describe must refuse) ───────────────────

def test_quality_denies_reported_source_without_figure():
    """pressure.py:50 `ctx.get('used_tokens') is None`: a basis that claims a
    harness source but carries no figure is nothing, and `view` (pressure.py:
    99-100) must not subtract it from the window."""
    ctx = _ctx(usage_source='harness_reported', window=200000, at_seq=5)
    assert P.quality(ctx, 5) == 'unavailable'
    v = P.view(_e(ctx, offset=5, pressure=0.4))
    assert (v['quality'], v['remaining']) == ('unavailable', None)
    assert v['summary'] == 'context not measured by this harness'


def test_quality_denies_any_ratio_without_a_window():
    """pressure.py:51 `or not ctx.get('window')`: a used figure against no
    window — missing or 0 — is refused, and `view` keeps `remaining` None
    (pressure.py:99-100) instead of inventing 0 - 5000."""
    no_window = _ctx(usage_source='harness_reported', used_tokens=5000, at_seq=2)
    assert P.quality(no_window, 2) == 'unavailable'
    v = P.view(_e(no_window, offset=2))
    assert (v['quality'], v['remaining'], v['window']) == ('unavailable', None, None)
    zero = _ctx(usage_source='harness_reported', used_tokens=5000, window=0, at_seq=2)
    assert P.quality(zero, 2) == 'unavailable'
    assert P.view(_e(zero, offset=2))['remaining'] is None


def test_describe_denies_a_reported_source_with_no_figure():
    """pressure.py:78 `or used is None`: the wording refuses to quote a
    reported usage that was never measured, even when a window is present."""
    assert P.describe(_ctx(usage_source='harness_reported')) == \
        'context not measured by this harness'
    assert P.describe(_ctx(usage_source='harness_reported', window=100)) == \
        'context not measured by this harness'


def test_the_none_template_is_shared_by_nobody():
    """pressure.py:28 and :38 `dict(_NONE, ...)`: the template is copied, never
    written through. A signalled basis must not leak into the next unrelated
    report, and neither call may mutate the template or a caller's `prev`."""
    baseline = dict(P._NONE)
    sig = P.signalled(None, 7)
    assert (sig['signal'], sig['signal_seq']) == ('precompact', 7)
    ctx, p = P.reported({'input_tokens': 1}, 10, 'offer', 1)
    assert (ctx['signal'], ctx['signal_seq'], p) == ('none', None, 0.1)
    assert P.quality(ctx, 1) == 'reported'
    prev = {'used_tokens': 9}
    P.signalled(prev, 3)
    P.reported({'input_tokens': 2}, 10, 'offer', 4, prev)
    assert prev == {'used_tokens': 9}
    assert P._NONE == baseline


# ── boundaries (0, offsets, filters, the frozen threshold) ───────────────────

def test_zero_usage_is_a_measurement_not_unknown():
    """pressure.py:50 and :68 `is None` / truthiness: a measured zero must
    survive as 0 — quality `reported`, `remaining` the whole window, and the
    words '0 of 1,000 tokens' — not collapse into unavailable."""
    ctx, p = P.reported({'input_tokens': 0}, 1000, 'offer', 3)
    assert (ctx['used_tokens'], p) == (0, 0.0)
    assert P.quality(ctx, 3) == 'reported'
    v = P.view(_e(ctx, offset=3, pressure=p))
    assert (v['quality'], v['remaining']) == ('reported', 1000)
    assert v['summary'] == 'the harness reported 0 of 1,000 tokens; window from the offer'


def test_stale_boundaries():
    """pressure.py:53 `ctx.get('at_seq') is not None and (stream_offset or 0) >
    ...`: at_seq 0 must still go stale (truthiness would skip the compare), a
    missing offset reads as 0 and never stale, an unrecorded at_seq never
    stale however far the stream has run."""
    zero_seq, _p = P.reported({'input_tokens': 1}, 100, 'offer', 0)
    assert P.quality(zero_seq, 0) == 'reported'
    assert P.quality(zero_seq, 1) == 'stale'
    assert P.quality(zero_seq, None) == 'reported'
    no_seq, _p = P.reported({'input_tokens': 1}, 100, 'offer', None)
    assert P.quality(no_seq, 10 ** 9) == 'reported'


def test_reported_counts_only_numeric_input_fields():
    """pressure.py:23-24 (the isinstance filter minus bool) and :27
    `int(sum(...))`: a string figure is not a figure, True is not one token,
    a float truncates only at the sum, and exactly the three INPUT_KEYS
    count — output_tokens never does."""
    assert P.INPUT_KEYS == ('input_tokens', 'cache_read_input_tokens',
                            'cache_creation_input_tokens')
    ctx, p = P.reported({'input_tokens': '1000', 'cache_read_input_tokens': True,
                         'cache_creation_input_tokens': 12.9, 'output_tokens': 99999},
                        100, 'offer', 1)
    assert (ctx['used_tokens'], p) == (12, 0.12)
    ctx, p = P.reported({'input_tokens': 10, 'cache_read_input_tokens': 20,
                         'cache_creation_input_tokens': 30, 'output_tokens': 999},
                        100, 'offer', 1)
    assert (ctx['used_tokens'], p) == (60, 0.6)
    assert P.reported({'output_tokens': 1, 'input_tokens': None}, 100, 'offer', 1) == (
        None, None)


def test_reason_at_the_exact_handoff_threshold():
    """pressure.py:89-90 at the frozen boundary: pressure == PRESSURE_HANDOFF
    reads '0.75 reached 0.75' — the hand-off limit is inclusive and the
    reason names its basis (ADR-0047 §9)."""
    assert (P.PRESSURE_HANDOFF, P.PRESSURE_PRECOMPACT) == (0.75, 0.9)
    ctx, p = P.reported({'input_tokens': 150000}, 200000, 'offer', 9)
    assert p == P.PRESSURE_HANDOFF == 0.75
    assert P.reason(ctx, p) == ('context pressure 0.75 reached 0.75: the harness reported '
                                '150,000 of 200,000 tokens; window from the offer')


# ── describe wordings no existing test pins ──────────────────────────────────

def test_describe_wording_of_a_report_with_no_window():
    """pressure.py:70-71 then :80-81 (and :70-71 feeding :77): the usage-with-
    no-window record must say 'against no known window' and, as a sentence,
    'context not measured' — never a bare None, and with thousands grouped."""
    assert P.describe({'used_tokens': 1234567, 'usage_source': 'harness_reported'}) == (
        'the harness reported 1,234,567 tokens, against no known window; '
        'context not measured')
    reported, _p = P.reported({'input_tokens': 1234567}, 0, 'none', 0)
    s = P.describe(P.signalled(reported, 0))
    assert ('last reported usage: 1,234,567 tokens, against no known window' in s)
    assert 'PreCompact) at offset 0, counted as 0.9 by policy' in s


def test_describe_tolerates_an_unknown_window_source():
    """pressure.py:84 `source.get(ctx['window_source'], '')`: a record from a
    source the code does not know is still readable — the clause goes empty
    instead of a KeyError, and `view` reads it normally."""
    ctx = _ctx(usage_source='harness_reported', used_tokens=10, window=100,
               window_source='guess', at_seq=0)
    assert P.quality(ctx, 0) == 'reported'
    assert P.describe(ctx) == 'the harness reported 10 of 100 tokens; '
    v = P.view(_e(ctx, offset=0, pressure=0.1))
    assert (v['quality'], v['remaining'], v['summary']) == (
        'reported', 90, 'the harness reported 10 of 100 tokens; ')


def test_signalled_from_nothing_at_offset_zero():
    """pressure.py:38-40 and :74-77 with signal_seq 0: the PreCompact signal
    alone is a complete basis — signalled quality, the policy stand-in in the
    words, 'last reported usage: none', nothing invented."""
    ctx = P.signalled(None, 0)
    assert (ctx['signal'], ctx['signal_seq']) == ('precompact', 0)
    assert (ctx['used_tokens'], ctx['window'], ctx['usage_source']) == (None, None, 'none')
    assert P.quality(ctx, 5) == 'signalled'
    assert P.describe(ctx) == (
        'the harness signalled it was about to compact its context (PreCompact) '
        'at offset 0, counted as 0.9 by policy; last reported usage: none')


# ── view and progressed: remaining read-path robustness ──────────────────────

def test_view_pads_a_partial_record_for_every_reader():
    """pressure.py:96 `dict(_NONE, ...(e.context or {}))`: a record missing
    keys must still come back with the full reader-facing shape (every
    template key plus quality/remaining/pressure/summary), and an empty basis
    reads unavailable, never 0."""
    v = P.view(_e({'used_tokens': 100, 'window': 200}, offset=0, pressure=0.5))
    assert v['quality'] == 'unavailable' and v['remaining'] is None
    assert v['signal'] == 'none' and v['signal_seq'] is None
    assert v['usage_source'] == 'none' and v['at_seq'] is None
    assert v['used_tokens'] == 100 and v['window'] == 200 and v['pressure'] == 0.5
    assert set(v) >= set(P._NONE) | {'quality', 'remaining', 'pressure', 'summary'}
    empty = P.view(_e({}, offset=0))
    assert (empty['quality'], empty['remaining']) == ('unavailable', None)


def test_progressed_container_boundaries():
    """pressure.py:108 `if artifacts:` and :112 `end_state not in set(earlier)`:
    any recorded artifact counts, even one whose name is the empty string;
    duplicated earlier links do not invent progress, and an unmeasured
    (None) earlier link does not block a measured one."""
    assert P.progressed(None, ('',), [])
    assert not P.progressed(None, (), [])
    assert not P.progressed('a', (), ['a', 'a'])
    assert not P.progressed('a', (), ('a',))
    assert P.progressed('a', (), [None])
