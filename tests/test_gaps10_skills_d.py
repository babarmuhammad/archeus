"""T-1379: claude_sessions/skills.py lines 256-290 (_quality, _row).

Selected branches, denial and fail-closed first:
  263      disable-model-invocation given as 'True', ' yes ' or '1' turns auto off
  263      'false' or a missing key keeps auto on
  263      a non-string True is coerced with str() and read as 'true', so auto is off
  265      weak when the description is under 25 characters OR has fewer than 4 words
  265      a missing, empty or None description is weak and does not crash
  274      use.get(command) overrides the defaults; a command missing from use keeps them
  280-283  the namesake plugin skill ('caveman:caveman') counts the plugin token and sets via;
           a non-namesake plugin skill ('caveman:review') does not count the plugin name
  280      the folder basename is a token: a row whose folder differs from its command counts it
  286      sessions is the MAX over the tokens, not the sum
  273      of_sessions comes from act['of'] and is 0 when act is None
  287      extra keyword arguments are merged last and win over computed fields

The hits keys are not probed for mixed case: clientstate._tokens lowercases every token before
it reaches hits, so the lookup at 286 cannot miss a mixed-case key.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import skills


@pytest.mark.parametrize('value', ['True', ' yes ', '1'])
def test_disable_flag_spellings_turn_auto_invocation_off(value):
    assert skills._quality({'disable-model-invocation': value})[0] is False


@pytest.mark.parametrize('meta', [{'disable-model-invocation': 'false'}, {}])
def test_false_or_missing_disable_flag_keeps_auto_invocation_on(meta):
    assert skills._quality(meta)[0] is True


def test_boolean_true_disable_flag_is_read_as_disabled():
    assert skills._quality({'disable-model-invocation': True})[0] is False


def test_thirty_char_three_word_description_is_still_weak():
    assert skills._quality({'description': 'continuous integration pipeline'}) == (True, True)


def test_four_word_description_over_25_chars_is_not_weak():
    assert skills._quality({'description': 'deploys the production build'}) == (True, False)


@pytest.mark.parametrize('meta', [{}, {'description': ''}, {'description': None}])
def test_missing_or_empty_description_is_weak_without_crashing(meta):
    assert skills._quality(meta) == (True, True)


def test_command_missing_from_use_keeps_defaults_and_present_use_overrides(tmp_path):
    d = os.path.join(str(tmp_path), 'alone')

    r = skills._row('alone', '', d, 'personal', 'alone', {})
    assert (r['uses'], r['last_used']) == (0, '')

    r = skills._row('alone', '', d, 'personal', 'alone',
                    {'alone': {'uses': 7, 'last_used': '2d'}})
    assert (r['uses'], r['last_used']) == (7, '2d')


def test_namesake_plugin_skill_counts_plugin_token_and_non_namesake_does_not(tmp_path):
    hits = {'caveman': 5}

    namesake = skills._row('caveman', '', os.path.join(str(tmp_path), 'caveman'), 'plugin',
                           'caveman:caveman', {}, {'hits': hits})
    assert (namesake['sessions'], namesake['via']) == (5, 'caveman')

    other = skills._row('review', '', os.path.join(str(tmp_path), 'review'), 'plugin',
                        'caveman:review', {}, {'hits': hits})
    assert (other['sessions'], other['via']) == (0, '')


def test_folder_name_token_counts_when_it_differs_from_the_command(tmp_path):
    r = skills._row('alias', '', os.path.join(str(tmp_path), 'deploy'), 'personal',
                    'p:alias', {}, {'hits': {'deploy': 4}})

    assert r['sessions'] == 4


def test_sessions_is_the_max_over_tokens_not_the_sum(tmp_path):
    r = skills._row('x', '', os.path.join(str(tmp_path), 'beta'), 'personal',
                    'alpha', {}, {'hits': {'alpha': 2, 'beta': 5}})

    assert r['sessions'] == 5


def test_of_sessions_comes_from_act_and_is_zero_without_it(tmp_path):
    d = os.path.join(str(tmp_path), 'x')

    assert skills._row('x', '', d, 'personal', 'x', {}, {'of': 4})['of_sessions'] == 4
    assert skills._row('x', '', d, 'personal', 'x', {}, None)['of_sessions'] == 0


def test_extra_keyword_arguments_win_over_computed_fields(tmp_path):
    r = skills._row('n', '', os.path.join(str(tmp_path), 'n'), 'personal', 'n', {},
                    {'hits': {'n': 3}}, sessions=9, shadowed=True)

    assert r['sessions'] == 9
    assert r['shadowed'] is True
