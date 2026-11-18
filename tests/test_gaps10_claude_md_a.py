"""T-1380: branch gaps in claude_sessions/claude_md.py lines 174-225.

Covers _preserve_block, _drop_blocks and _preserve_machine_blocks. The
contract: content outside the AUTOGEN/SESSIONS/ARCHEUS blocks never changes,
and a block carried across a rewrite keeps its bytes.
"""
from claude_sessions import claude_md as cm
from claude_sessions import config as _cfg

MS, ME = _cfg._MEMORY_START, _cfg._MEMORY_END
AGS, AGE = _cfg._AGENTS_START, _cfg._AGENTS_END
LS, LE = _cfg._LOOP_START, _cfg._LOOP_END
AS, AE = _cfg._AUTOGEN_START, _cfg._AUTOGEN_END


def _mem(body='DIGEST'):
    return f'{MS}\n{body}\n{ME}\n'


def _existing_with_all(body='B'):
    return ('# P\n\n' + _mem(body + '-mem')
            + f'{AGS}\n{body}-agents\n{AGE}\n'
            + f'{LS}\n{body}-loop\n{LE}\n')


def test_user_prose_stray_start_kept(monkeypatch):
    """Branch: _drop_blocks with strays=False (from_user=True) returns after the
    balanced-block removal, so a MEMORY START with no END in the user's prose is
    kept byte-for-byte. Caught by: a flipped `not from_user` in _preserve_block."""
    existing = _existing_with_all()
    final = '# P\n\nprose\n' + MS + '\nkept line\n\nAfter\n'
    out = cm._preserve_block(final, existing, MS, ME, from_user=True)
    assert out == final.rstrip('\n') + '\n\n' + _mem('B-mem')


def test_strays_false_leaves_unpaired_start():
    """Branch: _drop_blocks `if not strays: return text`. Only balanced blocks are
    removed; an unpaired START is returned untouched. Caught by: deleting the early
    return so the stray scan runs for user prose."""
    text = 'a\n' + MS + '\nb\n'
    assert cm._drop_blocks(text, MS, ME, strays=False) == text


def test_stray_start_stops_before_autogen():
    """Branch: _drop_blocks stray loop, stop match at a blank line. The paragraph
    under an echoed START goes; the AUTOGEN block after it survives. Caught by: a
    stop regex that runs past the blank line."""
    text = MS + '\necho line\n\n' + AS + '\nauto\n' + AE + '\n'
    assert cm._drop_blocks(text, MS, ME) == AS + '\nauto\n' + AE + '\n'


def test_stray_stops_at_next_marker_without_blank_line():
    """Branch: _STRAY_STOP alternative `\\n(?=<!--)`. A stray followed directly by a
    marker line stops there, with no blank line needed. Caught by: removing the
    lookahead alternative (the stray would then eat the AUTOGEN block)."""
    text = 'keep\n' + MS + '\necho\n' + AS + '\nauto\n' + AE + '\n'
    assert cm._drop_blocks(text, MS, ME) == 'keep\n' + AS + '\nauto\n' + AE + '\n'


def test_stray_without_stop_runs_to_eof():
    """Branch: _drop_blocks `if m else ''` when no stop match exists. The stray and
    everything after it is removed. Caught by: returning the text unchanged when
    no stop is found, which would leave the echoed START in place."""
    text = 'keep\n' + MS + '\nno stop here'
    assert cm._drop_blocks(text, MS, ME) == 'keep\n'


def test_drop_removes_every_balanced_block():
    """Branch: _drop_blocks first loop, repeated while block_span finds a block.
    Two balanced blocks are both removed. Caught by: a single split (not a loop)
    that leaves the second block in place."""
    text = 'a\n' + MS + '\nx\n' + ME + '\nmid\n' + MS + '\ny\n' + ME + '\nz'
    out = cm._drop_blocks(text, MS, ME)
    assert out == 'a\n\nmid\n\nz'


def test_preserve_block_absent_returns_final():
    """Branch: _preserve_block `span is None: return final`. With no block in
    `existing`, the final text is returned unchanged, no separator added. Caught
    by: appending an empty block or a stray '\\n\\n' separator."""
    final = '# P\n\nnew\n'
    assert cm._preserve_block(final, '# P\nno block') == final


def test_preserved_block_bytes_identical():
    """Branch: _preserve_block carries `existing[span[0]:_owned_stop]` verbatim after
    final.rstrip('\\n') + '\\n\\n'. A CRLF block keeps its \\r\\n bytes. Caught by:
    re-rendering the block or normalising its line endings."""
    block_bytes = (f'{MS}\r\nDIG\r\n{ME}\r\n').encode('utf-8')
    existing = ('# P\r\n\r\n').encode('utf-8') + block_bytes
    out = cm._preserve_block('# P\n\nnew\n', existing.decode('utf-8'), MS, ME)
    assert out.encode('utf-8') == ('# P\n\nnew\n\n').encode('utf-8') + block_bytes


def test_machine_blocks_all_carried_from_user():
    """Branch: _preserve_machine_blocks loops every entry of _MACHINE_BLOCKS in
    order and passes from_user to each. Caught by: dropping one entry, a reversed
    order, or not forwarding from_user (checked by the stray case below)."""
    existing = _existing_with_all('B')
    final = '# P\n\nprose\n'
    out = cm._preserve_machine_blocks(final, existing, from_user=True)
    assert out == ('# P\n\nprose\n\n' + _mem('B-mem').rstrip('\n') + '\n\n'
                   + f'{AGS}\nB-agents\n{AGE}\n\n'
                   + f'{LS}\nB-loop\n{LE}\n')

    stray_final = '# P\n\nprose\n' + LS + '\nstray tail\n'
    kept = cm._preserve_machine_blocks(stray_final, existing, from_user=True)
    assert 'stray tail' in kept and kept.count(LS) == 2
    echoed = cm._preserve_machine_blocks(stray_final, existing, from_user=False)
    assert 'stray tail' not in echoed and echoed.count(LS) == 1


def test_stray_scan_ignores_removed_blocks():
    """Branch: _drop_blocks stray scan runs AFTER balanced removal, so the markers
    of a block already removed are not counted as strays. A following AUTOGEN block
    is not eaten. Caught by: scanning the original text for strays before removal."""
    text = MS + '\nin\n' + ME + '\nmid\n' + AS + '\nauto\n' + AE + '\n'
    assert cm._drop_blocks(text, MS, ME) == '\nmid\n' + AS + '\nauto\n' + AE + '\n'
