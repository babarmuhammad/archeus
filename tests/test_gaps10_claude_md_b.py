"""T-1381: branch gaps in claude_sessions/claude_md.py lines 628-681.

Covers _fence_in, _valid_compressed and assemble_with_manual. The contract:
the user's prose survives a rebuild, and a fenced region is never lost.
"""
from claude_sessions import claude_md as cm
from claude_sessions import config as _cfg

MS, ME = _cfg._MEMORY_START, _cfg._MEMORY_END
AS, AE = _cfg._AUTOGEN_START, _cfg._AUTOGEN_END
AI = _cfg._AI_MARKER
STEM = '@@K_'


def _patch_builders(monkeypatch):
    monkeypatch.setattr(cm, '_build_autogen_block', lambda *a, **k: 'AUTO BODY\n')
    monkeypatch.setattr(cm, '_build_sessions_block', lambda *a, **k: 'SESS BODY\n')


def _mem(body):
    return f'{MS}\n{body}\n{ME}\n'


def test_empty_manual_keeps_machine_blocks(monkeypatch, tmp_path):
    """Branch: assemble_with_manual with an empty manual. The prose is deleted, the
    MEMORY block of `existing` is carried verbatim. Caught by: a path that rebuilds
    from the manual only and drops _preserve_machine_blocks."""
    _patch_builders(monkeypatch)
    existing = '# P\n\nold prose\n\n' + _mem('DIGEST') + AS + '\nOLD\n' + AE + '\n'
    out = cm.assemble_with_manual('', existing, str(tmp_path), None)
    assert 'old prose' not in out
    assert _mem('DIGEST') in out, 'the MEMORY block was not carried verbatim'
    assert 'AUTO BODY' in out and 'OLD' not in out


def test_manual_prose_byte_identical(monkeypatch, tmp_path):
    """Branch: assemble_with_manual's manual goes through
    `manual.rstrip('\\n') + '\\n'` and is kept as text outside any block. Caught
    by: a rewrite or normalising of the manual bytes."""
    _patch_builders(monkeypatch)
    manual = '# P\n\nIntro  with  spaces.\n\n- item\n'
    existing = '# P\n\n' + AS + '\nOLD AUTO\n' + AE + '\n'
    out = cm.assemble_with_manual(manual, existing, str(tmp_path), None)
    assert out.startswith(manual), 'the manual bytes changed'
    assert 'OLD AUTO' not in out and 'AUTO BODY' in out


def test_dropped_marker_region_reappended():
    """Branch: _fence_in `else` arm, a stem is set but the model dropped the marker.
    The region goes at the end, the prose before it is kept. Caught by: removing the
    else arm (the region would be lost)."""
    region = '<!-- ARCHEUS:KEEP:START -->\nDO NOT REWORD\n<!-- ARCHEUS:KEEP:END -->'
    out = cm._fence_in('# P\n\nprose\n', [region], STEM)
    assert out == '# P\n\nprose\n\n' + region + '\n'


def test_no_stem_appends_all_regions_in_order():
    """Branch: _fence_in with stem None. Every region is appended in list order, each
    followed by a newline. Caught by: a reversed or merged append."""
    assert cm._fence_in('# P\n', ['R0', 'R1']) == '# P\n\nR0\n\nR1\n'


def test_marker_replaced_once():
    """Branch: _fence_in `out.replace(mark, region, 1)`. Only the first copy of the
    marker is replaced; a second copy typed by the user stays. Caught by: replacing
    every occurrence (the count argument removed)."""
    out = cm._fence_in(f'a {STEM}0@@ b {STEM}0@@ c', ['R0'], STEM)
    assert out == 'a R0 b @@K_0@@ c'


def test_fence_in_none_text_and_empty_kept():
    """Branch: _fence_in `text or ''` with no regions. Caught by: indexing or
    concatenating None."""
    assert cm._fence_in(None, []) == ''


def test_ai_marker_reinserted_after_title(monkeypatch, tmp_path):
    """Branch: assemble_with_manual AI marker re-insertion, the title found in the
    first five lines. The marker goes on the line after '# '. Caught by: inserting
    at a fixed index instead of after the title."""
    _patch_builders(monkeypatch)
    existing = '# P\n\n' + AI + '\n'
    out = cm.assemble_with_manual('# P\n\nprose\n', existing, str(tmp_path), None)
    assert out.split('\n')[:2] == ['# P', AI]


def test_ai_marker_no_title_inserts_at_one(monkeypatch, tmp_path):
    """Branch: assemble_with_manual AI marker re-insertion with no '# ' heading in
    the first five lines. insert_at stays 1. Caught by: inserting at 0 or at the end."""
    _patch_builders(monkeypatch)
    existing = AI + '\n'
    out = cm.assemble_with_manual('prose only\n', existing, str(tmp_path), None)
    assert out.split('\n')[:2] == ['prose only', AI]


def test_valid_compressed_80_boundary():
    """Branch: _valid_compressed length floor. Exactly 80 characters after lstrip is
    accepted, 79 is rejected. A refusal prefix is rejected even when long. Caught
    by: an off-by-one in `len(t) < 80`, or the refusal regex removed."""
    assert len('# ' + 'a' * 78) == 80
    assert cm._valid_compressed('# ' + 'a' * 78) is True
    assert cm._valid_compressed('# ' + 'a' * 77) is False
    assert cm._valid_compressed('# Here is the file ' + 'x' * 200) is False


def test_from_user_keeps_stray_marker_in_manual(monkeypatch, tmp_path):
    """Branch: assemble_with_manual forwards from_user to _preserve_machine_blocks,
    so a stray MEMORY START typed in the manual is kept as prose with from_user=True
    and removed with from_user=False. Caught by: not forwarding from_user."""
    _patch_builders(monkeypatch)
    existing = '# P\n\n' + _mem('OLD')
    manual = '# P\n\n' + MS + '\nstray prose\n\nTail\n'

    kept = cm.assemble_with_manual(manual, existing, str(tmp_path), None, from_user=True)
    assert 'stray prose' in kept and 'Tail' in kept and kept.count(MS) == 2

    echoed = cm.assemble_with_manual(manual, existing, str(tmp_path), None, from_user=False)
    assert 'stray prose' not in echoed and 'Tail' in echoed and echoed.count(MS) == 1
