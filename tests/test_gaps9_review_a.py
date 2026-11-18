"""T-1357: claude_sessions/review.py lines 29-80 at tip 10d688c0 (get_diff
diff selection, gather_guidance CLAUDE.md and lesson guidance).

Selected candidates, not measured coverage. Ranked denial/fail-closed first,
then boundaries, then error paths:

1.  39-41  a base starting with '-' returns '' and proc.git is never called
    -> test_get_diff_refuses_option_shaped_base_without_calling_git
       (closest existing: tests/test_review.py::test_a_base_that_is_an_option_is_refused_not_passed_to_git,
       which runs real git and checks only the return value and the absence of a file)
2.  42     base builds exactly `<base>...HEAD` as one argv word
    -> test_get_diff_base_builds_one_three_dot_argv_word
3.  43-44  staged uses only `diff --staged`, no HEAD argument
    -> test_get_diff_staged_runs_only_diff_staged
4.  46-48  default: empty HEAD diff triggers the plain `diff` fallback; a
           non-empty HEAD diff does not
    -> test_get_diff_default_falls_back_to_plain_diff_only_when_head_empty
       test_get_diff_default_keeps_head_diff_when_non_empty
5.  33-36  proc.git returning None gives '' so the caller's strip() works
    -> test_get_diff_treats_failed_git_as_empty_text
6.  49     the result is truncated to MAX_DIFF_CHARS
    -> test_get_diff_truncates_to_max_diff_chars
7.  57-64  a CLAUDE.md read error is skipped; the text is capped at 8000 characters
    -> test_gather_guidance_skips_unreadable_claude_md
       test_gather_guidance_caps_claude_md_at_8000_characters
8.  66-73  only approved or pinned lessons are included, at most 20
    -> test_gather_guidance_includes_only_approved_or_pinned_lessons_capped_at_20
9.  74-75  a load_memory failure is swallowed and CLAUDE.md guidance still returned
    -> test_gather_guidance_survives_load_memory_failure
10. 39     base '' is treated as no base, not as `...HEAD`
    -> test_get_diff_empty_base_is_treated_as_no_base

Seams: review.proc.git is replaced by a recorder returning synthetic text or
None; review.memory.load_memory is faked; review.open is shadowed (module-level
name lookup) to simulate a read error. tmp_path holds the synthetic project.
No real git and no subprocess.
"""

import pytest

import claude_sessions.proc as proc
import claude_sessions.review as review


class GitRecorder:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, args, cwd, timeout=15):
        self.calls.append(list(args))
        if callable(self.reply):
            return self.reply(list(args))
        return self.reply


def _install_git(monkeypatch, reply):
    rec = GitRecorder(reply)
    monkeypatch.setattr(proc, 'git', rec)
    return rec


def test_get_diff_refuses_option_shaped_base_without_calling_git(monkeypatch, tmp_path):
    rec = _install_git(monkeypatch, 'should not be used')
    assert review.get_diff(str(tmp_path), base='--output=evil.diff') == ''
    assert rec.calls == []


def test_get_diff_base_builds_one_three_dot_argv_word(monkeypatch, tmp_path):
    rec = _install_git(monkeypatch, 'diff text')
    assert review.get_diff(str(tmp_path), base='main') == 'diff text'
    assert rec.calls == [['diff', 'main...HEAD']]


def test_get_diff_staged_runs_only_diff_staged(monkeypatch, tmp_path):
    rec = _install_git(monkeypatch, 'staged text')
    assert review.get_diff(str(tmp_path), staged=True) == 'staged text'
    assert rec.calls == [['diff', '--staged']]


def test_get_diff_default_falls_back_to_plain_diff_only_when_head_empty(monkeypatch, tmp_path):
    def reply(args):
        return '   \n' if args == ['diff', 'HEAD'] else 'plain diff'

    rec = _install_git(monkeypatch, reply)
    assert review.get_diff(str(tmp_path)) == 'plain diff'
    assert rec.calls == [['diff', 'HEAD'], ['diff']]


def test_get_diff_default_keeps_head_diff_when_non_empty(monkeypatch, tmp_path):
    rec = _install_git(monkeypatch, '+changed line')
    assert review.get_diff(str(tmp_path)) == '+changed line'
    assert rec.calls == [['diff', 'HEAD']]


def test_get_diff_treats_failed_git_as_empty_text(monkeypatch, tmp_path):
    rec = _install_git(monkeypatch, None)
    assert review.get_diff(str(tmp_path)) == ''
    assert rec.calls == [['diff', 'HEAD'], ['diff']]
    assert review.get_diff(str(tmp_path), base='main') == ''
    assert review.get_diff(str(tmp_path), staged=True) == ''


def test_get_diff_truncates_to_max_diff_chars(monkeypatch, tmp_path):
    big = 'x' * (review.MAX_DIFF_CHARS + 500)
    _install_git(monkeypatch, big)
    out = review.get_diff(str(tmp_path), staged=True)
    assert len(out) == review.MAX_DIFF_CHARS
    assert out == big[:review.MAX_DIFF_CHARS]


def _no_memory(monkeypatch):
    monkeypatch.setattr(review.memory, 'load_memory', lambda *a, **k: {'entities': []})


def test_gather_guidance_skips_unreadable_claude_md(monkeypatch, tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('rule one\n', encoding='utf-8')
    _no_memory(monkeypatch)

    def failing_open(*args, **kwargs):
        raise OSError('cannot read')

    monkeypatch.setattr(review, 'open', failing_open, raising=False)
    assert review.gather_guidance(str(tmp_path)) == ''


def test_gather_guidance_caps_claude_md_at_8000_characters(monkeypatch, tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('a' * 9000, encoding='utf-8')
    _no_memory(monkeypatch)
    out = review.gather_guidance(str(tmp_path))
    assert out.startswith('# PROJECT RULES (from CLAUDE.md')
    body = out.split('\n', 1)[1]
    assert body == 'a' * 8000


def test_gather_guidance_includes_only_approved_or_pinned_lessons_capped_at_20(monkeypatch, tmp_path):
    entities = [{'type': 'lesson', 'name': 'DRAFT', 'summary': 's', 'status': 'draft'},
                {'type': 'concept', 'name': 'CONCEPT', 'summary': 's', 'status': 'approved'}]
    entities += [{'type': 'lesson', 'name': f'L{i}', 'summary': f's{i}',
                  'status': 'approved' if i % 2 == 0 else 'pinned'}
                 for i in range(25)]
    monkeypatch.setattr(review.memory, 'load_memory',
                        lambda *a, **k: {'entities': entities})
    out = review.gather_guidance(str(tmp_path))
    assert '# LEARNED LESSONS' in out
    assert 'DRAFT' not in out
    assert 'CONCEPT' not in out
    bullets = [ln for ln in out.splitlines() if ln.startswith('- ')]
    assert len(bullets) == 20
    assert bullets[0] == '- L0: s0'
    assert bullets[-1] == '- L19: s19'


def test_gather_guidance_survives_load_memory_failure(monkeypatch, tmp_path):
    (tmp_path / 'CLAUDE.md').write_text('rule one', encoding='utf-8')

    def boom(*a, **k):
        raise RuntimeError('memory store corrupt')

    monkeypatch.setattr(review.memory, 'load_memory', boom)
    out = review.gather_guidance(str(tmp_path))
    assert out == '# PROJECT RULES (from CLAUDE.md — enforce these)\nrule one'


def test_get_diff_empty_base_is_treated_as_no_base(monkeypatch, tmp_path):
    rec = _install_git(monkeypatch, '')
    review.get_diff(str(tmp_path), base='')
    assert rec.calls == [['diff', 'HEAD'], ['diff']]
    assert not any('...HEAD' in a for call in rec.calls for a in call)
