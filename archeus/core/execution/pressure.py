"""Context pressure with its basis (ADR-0047 §2, §5, §9): what an execution's
context consumption was measured from, the quality read from that, the reason
a hand-off gives, and whether a pressure continuation made progress.

Pure: no I/O, no clock. The basis is what `record_progress` stores on the
Execution (`context`); the quality is derived here at read time, never stored.
Unknown stays None — nothing here turns a missing reading into 0.
"""

#: p12-design-gate D20 (FROZEN): the pressure that hands an execution off, and
#: the policy stand-in for the PreCompact signal — not a measured ratio
PRESSURE_HANDOFF, PRESSURE_PRECOMPACT = 0.75, 0.9
#: the usage fields whose sum is the next turn's input (execution-architecture §6)
INPUT_KEYS = ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
QUALITIES = ('signalled', 'unavailable', 'stale', 'estimated', 'reported')
_NONE = {'used_tokens': None, 'window': None, 'window_source': 'none', 'usage_source': 'none',
         'at_seq': None, 'signal': 'none', 'signal_seq': None}


def reported(usage, window, window_source, at_seq, prev=None):
    """(basis, pressure) for one usage report, or (prev, None) when the report
    carries no input figure. `pressure` is None when the window is unknown."""
    got = [usage.get(k) for k in INPUT_KEYS
           if isinstance(usage.get(k), (int, float)) and not isinstance(usage.get(k), bool)]
    if not got:
        return prev, None
    used = int(sum(got))
    ctx = dict(_NONE, **(prev or {}))
    ctx.update(used_tokens=used, window=window or None,
               window_source=window_source if window else 'none',
               usage_source='harness_reported', at_seq=at_seq)
    return ctx, (used / float(window) if window else None)


def signalled(prev, at_seq):
    """The basis once the harness signalled its own compaction (PreCompact):
    what real reports said stays, and nothing is added to it."""
    ctx = dict(_NONE, **(prev or {}))
    ctx.update(signal='precompact', signal_seq=at_seq)
    return ctx


def quality(ctx, stream_offset):
    """The first of signalled / unavailable / stale / estimated / reported
    that holds. Stale compares offsets, so it needs no clock."""
    if not ctx:
        return 'unavailable'
    if ctx.get('signal') == 'precompact':
        return 'signalled'
    if ctx.get('usage_source') != 'harness_reported' or ctx.get('used_tokens') is None \
            or not ctx.get('window'):
        return 'unavailable'
    if ctx.get('at_seq') is not None and (stream_offset or 0) > ctx['at_seq']:
        return 'stale'
    if ctx.get('window_source') == 'harness_smallest':
        return 'estimated'
    return 'reported'


def _tokens(n):
    return '{:,}'.format(n)


def describe(ctx):
    """The basis in words, from the record alone."""
    ctx = dict(_NONE, **(ctx or {}))
    used, window = ctx['used_tokens'], ctx['window']
    if used is not None and window:
        last = '%s of %s tokens' % (_tokens(used), _tokens(window))
    elif used is not None:
        last = '%s tokens, against no known window' % _tokens(used)
    else:
        last = None
    if ctx['signal'] == 'precompact':
        return ('the harness signalled it was about to compact its context (PreCompact) at '
                'offset %s, counted as %.1f by policy; last reported usage: %s'
                % (ctx['signal_seq'], PRESSURE_PRECOMPACT, last or 'none'))
    if ctx['usage_source'] != 'harness_reported' or used is None:
        return 'context not measured by this harness'
    if not window:
        return 'the harness reported %s; context not measured' % last
    source = {'offer': 'window from the offer',
              'harness_smallest': 'window estimated: the smallest this harness declares'}
    return 'the harness reported %s; %s' % (last, source.get(ctx['window_source'], ''))


def reason(ctx, pressure):
    """A pressure hand-off's reason, naming its basis (ADR-0047 §9)."""
    return 'context pressure %.2f reached %.2f: %s' % (pressure, PRESSURE_HANDOFF,
                                                      describe(ctx))


def view(e):
    """`context` as every reader sees it: the recorded basis, its quality and
    `remaining` only when the window and a reported usage are both known."""
    ctx = dict(_NONE, **(e.context or {}))
    q = quality(e.context, e.stream_offset)
    left = None
    if q not in ('signalled', 'unavailable'):
        left = ctx['window'] - ctx['used_tokens']
    return dict(ctx, quality=q, remaining=left, pressure=e.pressure, summary=describe(ctx))


def progressed(end_state, artifacts, earlier):
    """Whether a pressure continuation made progress (ADR-0047 §5): it recorded
    an artifact, or its measured end state is one no earlier link of its chain
    ended in. Unmeasurable is no progress (guards fail closed)."""
    if artifacts:
        return True
    if end_state is None:
        return False
    return end_state not in set(earlier)
