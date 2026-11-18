"""Headless-text, Anthropic-model and text-gate branches of claude_sessions/sessions.py (lines 34-96)."""
import pytest

from claude_sessions import sessions as s


def test_marker_anywhere_in_text_is_headless():
    assert s.is_headless_text('please run ' + s.HEADLESS_MARK + ' now') is True


def test_opener_after_leading_space_is_headless():
    assert s.is_headless_text('   ' + s.HEADLESS_OPENERS[0] + ' the repo') is True


def test_opener_mid_sentence_is_not_headless():
    assert s.is_headless_text('my notes say ' + s.HEADLESS_OPENERS[0]) is False


def test_every_opener_matches_after_leading_whitespace():
    for opener in s.HEADLESS_OPENERS:
        assert s.is_headless_text('\n\t' + opener) is True


def test_headless_none_and_blank_are_false():
    assert s.is_headless_text(None) is False
    assert s.is_headless_text('') is False
    assert s.is_headless_text('   ') is False


def test_used_provider_missing_models_key_is_false():
    assert s._used_provider({}) is False
    assert s._used_provider({'models': None}) is False
    assert s._used_provider({'models': []}) is False


def test_used_provider_one_foreign_id_among_anthropic_is_true():
    assert s._used_provider({'models': ['claude-opus-4-7', 'big-pickle']}) is True
    assert s._used_provider({'models': ['claude-opus-4-7', 'sonnet']}) is False


def test_synthetic_and_empty_ids_count_as_anthropic():
    assert s._is_anthropic_model(None) is True
    assert s._is_anthropic_model('') is True
    assert s._is_anthropic_model('   ') is True
    assert s._is_anthropic_model('<synthetic>') is True
    assert s._is_anthropic_model('opus-mini') is True
    assert s._is_anthropic_model('big-pickle') is False


def test_claude_substring_in_foreign_slug_is_anthropic():
    # Documents the current substring rule: a foreign slug that contains
    # 'claude' hides as Anthropic, so the provider flag stays off for it.
    assert s._is_anthropic_model('acme/claude-clone-7b') is True
    assert s._used_provider({'models': ['acme/claude-clone-7b']}) is False


def test_good_text_length_boundary_is_five():
    assert s._good_text('hell') is False
    assert s._good_text('hello') is True
    assert s._good_text(None) is False
    assert s._good_text('') is False


def test_good_text_prefix_and_contains_each_reject_alone(monkeypatch):
    monkeypatch.setattr(s, 'BAD_PREFIXES', ('zzz',))
    monkeypatch.setattr(s, 'BAD_CONTAINS', [])
    assert s._good_text('zzzabc def') is False
    assert s._good_text('abc zzz def') is True

    monkeypatch.setattr(s, 'BAD_PREFIXES', ())
    monkeypatch.setattr(s, 'BAD_CONTAINS', ['qqq'])
    assert s._good_text('abc QQQ def') is False
    assert s._good_text('zzzabc def') is True


def test_bad_contains_entries_are_lower_case():
    assert all(b == b.lower() for b in s.BAD_CONTAINS)
