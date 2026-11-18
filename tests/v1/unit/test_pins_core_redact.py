"""T-829: pins for every security-relevant condition in archeus/core/redact.py that
no other test in tests/v1 would fail on if the condition were inverted, removed
or loosened. Each test names the branch it pins and fails when that branch is
mutated."""

import pytest

from archeus.core.redact import redact


def test_node_branch_redacts_a_secret():
    assert redact('use node_a1-B2_c3d4 now') == 'use [redacted] now'


@pytest.mark.parametrize('pfx', ['hook_', 'dev_', 'node_', 'sk-'],
                         ids=['hook', 'dev', 'node', 'sk'])
def test_shortest_matched_body_is_eight(pfx):
    assert redact(pfx + 'a' * 7) == pfx + 'a' * 7
    assert redact(pfx + 'a' * 8) == '[redacted]'


@pytest.mark.parametrize('pfx', ['hook_', 'dev_', 'node_'], ids=['hook', 'dev', 'node'])
def test_body_allows_underscore_and_hyphen(pfx):
    assert redact('key %s!' % (pfx + 'ab-1_2cd')) == 'key [redacted]!'


@pytest.mark.parametrize('pfx', ['gho_', 'ghu_', 'ghs_', 'ghr_'],
                         ids=['gho', 'ghu', 'ghs', 'ghr'])
def test_gh_family_prefixes_redact(pfx):
    assert redact(pfx + 'Ab1cD2eF') == '[redacted]'


def test_gh_prefix_set_excludes_other_letters():
    assert redact('ghx_Ab1cD2eF') == 'ghx_Ab1cD2eF'


def test_gh_body_takes_digits():
    assert redact('ghp_a1B2c3D4') == '[redacted]'


def test_github_pat_body_takes_uppercase_digits_underscore():
    assert redact('github_pat_Ab1_2cd3') == '[redacted]'


def test_akia_body_takes_digits():
    assert redact('AKIA0A1B2C3D4E5F') == '[redacted]'


def test_akia_shortest_matched_body_is_twelve():
    assert redact('AKIA' + 'B' * 11) == 'AKIA' + 'B' * 11
    assert redact('AKIA' + 'B' * 12) == '[redacted]'


@pytest.mark.parametrize('word', ['Bearer', 'bearer', 'BEARER', 'BeArEr'],
                         ids=['cap', 'low', 'up', 'mixed'])
def test_bearer_matches_any_case(word):
    assert redact(word + ' abcdefgh') == '[redacted]'


def test_case_insensitivity_covers_only_bearer():
    for text in ['akiaabcdefghijklmnop', 'HOOK_aaaaaaaa', 'SK-aaaaaaaa', 'GHP_aaaaaaaa']:
        assert redact(text) == text


@pytest.mark.parametrize('sep', [' ', '\t', '\n', '  '], ids=['sp', 'tab', 'nl', 'dbl'])
def test_bearer_separator_variants(sep):
    assert redact('Bearer' + sep + 'a1.B2c3d4') == '[redacted]'


def test_bearer_body_takes_dot_hyphen_underscore():
    assert redact('Bearer ab-1_.2cd') == '[redacted]'


def test_every_match_becomes_the_exact_literal():
    assert redact('hook_aaaaaaaa mid sk-bbbbbbbb') == '[redacted] mid [redacted]'
