"""T-1336: the highest-risk uncovered branches of claude_sessions/ctxaudit.py
lines 35-96 inclusive, at tip 6b1a30b8. Fail-closed and denial first, then
boundaries, then error paths.

Selected branches (source line, probe):
1. protect_section 50-52  a KEEP fence just above the needle: refused, no write
2. protect_section 53-56  empty needle: refused, no write
3. protect_section 46-49  unreadable file: refused, no write
4. protect_section 65-67  write failure: returns False
5. split_blocks 89-92     one sentinel of a pair only: block stays '' and the text stays prose
6. protect_section 57-62  the section ends at the next heading, sub-heading included
7. protect_section 57-59  needle on the heading line itself: the section starts there
8. split_blocks 83-96     prose on both sides of a machine block survives, in order
9. keep_regions 35-37     closed fences counted; unclosed fence and None count zero
10. split_blocks 89-92    PREMISE: end sentinel before start duplicates the text between them
"""

import pytest

from claude_sessions import config as _c
from claude_sessions import ctxaudit

KEEP = _c._KEEP_START
KEEP_END = _c._KEEP_END
AGENTS = _c._AGENTS_START + '\n| row |\n' + _c._AGENTS_END


@pytest.fixture
def writes(monkeypatch):
    calls = []

    def recorder(path, text, mode=None):
        calls.append((path, text))
        return True

    monkeypatch.setattr(_c, 'write_atomic', recorder)
    return calls


def test_protect_refuses_a_section_already_under_a_keep_fence(tmp_path, writes):
    md = tmp_path / 'CLAUDE.md'
    text = f'# proj\n{KEEP}\n## Notes\nkept\n{KEEP_END}\n\n## Deployment\nrun the deploy script\n'
    md.write_text(text, encoding='utf-8')
    assert ctxaudit.protect_section(str(md), 'run the deploy script') is False
    assert writes == []
    assert md.read_text(encoding='utf-8') == text


def test_protect_refuses_an_empty_needle(tmp_path, writes):
    md = tmp_path / 'CLAUDE.md'
    text = '# proj\n\n## Deployment\nrun the deploy script\n'
    md.write_text(text, encoding='utf-8')
    assert ctxaudit.protect_section(str(md), '') is False
    assert writes == []
    assert md.read_text(encoding='utf-8') == text


def test_protect_refuses_an_unreadable_file(tmp_path, writes):
    missing = tmp_path / 'absent' / 'CLAUDE.md'
    assert ctxaudit.protect_section(str(missing), 'anything') is False
    assert writes == []
    assert not missing.exists()


def test_protect_reports_false_when_the_write_fails(tmp_path, monkeypatch):
    md = tmp_path / 'CLAUDE.md'
    text = '# proj\n\n## Deployment\nrun the deploy script\n'
    md.write_text(text, encoding='utf-8')
    monkeypatch.setattr(_c, 'write_atomic', lambda path, body, mode=None: False)
    assert ctxaudit.protect_section(str(md), 'run the deploy script') is False
    assert md.read_text(encoding='utf-8') == text


def test_split_blocks_keeps_a_half_pair_as_prose():
    text = f'top\n{_c._AGENTS_START}\n| row |\nbottom\n'
    b = ctxaudit.split_blocks(text)
    assert b['agents'] == ''
    assert b['manual'] == text


def test_protect_fence_stops_at_a_subheading(tmp_path):
    md = tmp_path / 'CLAUDE.md'
    md.write_text('# proj\n\n## Deployment\nrun the deploy script\n\n'
                  '### Detail\nmore detail\n\n## Other\nunrelated\n', encoding='utf-8')
    assert ctxaudit.protect_section(str(md), 'run the deploy script') is True
    out = md.read_text(encoding='utf-8')
    body = out[out.index(KEEP):out.index(KEEP_END)]
    assert 'run the deploy script' in body
    assert 'more detail' not in body
    assert 'more detail' in out
    assert out.count(KEEP) == 1


def test_protect_on_the_heading_line_wraps_that_section(tmp_path):
    md = tmp_path / 'CLAUDE.md'
    md.write_text('# proj\n\n## Deployment\nrun the deploy script\n\n## Other\nunrelated\n',
                  encoding='utf-8')
    assert ctxaudit.protect_section(str(md), '## Deployment') is True
    out = md.read_text(encoding='utf-8')
    body = out[out.index(KEEP):out.index(KEEP_END)]
    assert '## Deployment' in body and 'run the deploy script' in body
    assert 'unrelated' not in body


def test_split_blocks_keeps_prose_on_both_sides_of_a_block():
    b = ctxaudit.split_blocks(f'before\n{AGENTS}\nafter\n')
    assert b['agents'] == AGENTS
    assert b['manual'] == 'before\n\nafter\n'


def test_keep_regions_counts_closed_fences_only():
    two = f'{KEEP}\na\n{KEEP_END}\nx\n{KEEP}\nb\n{KEEP_END}\n'
    assert ctxaudit.keep_regions(two) == 2
    assert ctxaudit.keep_regions(f'{KEEP}\nopen only\n') == 0
    assert ctxaudit.keep_regions(None) == 0


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/ctxaudit.py:89-92 split_blocks: an end sentinel before the "
    "start sentinel makes manual[j:] re-add the text between them"))
def test_split_blocks_with_end_before_start_does_not_duplicate_text():
    text = f'A\n{_c._AGENTS_END}\nmid\n{_c._AGENTS_START}\nB\n'
    b = ctxaudit.split_blocks(text)
    assert b['agents'] == ''
    assert b['manual'] == text
