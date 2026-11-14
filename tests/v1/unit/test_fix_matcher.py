import pytest

from archeus.core.automation import matcher as M

TYPES = {'mission.created'}
OK = {'title': 't', 'objective': 'o'}


@pytest.mark.parametrize('crit', [
    [{'text': 'x'}],
    [{'text': ' ', 'check': 'automatic'}],
    [{'text': 'x', 'check': 'auto'}],
    [{'text': 'x', 'check': 'automatic', 'budget': {}}],
    [{'text': 'x', 'check': 'human', 'origin': 'guessed'}],
])
def test_a_template_criterion_the_mission_would_refuse_is_refused_at_write(crit):
    with pytest.raises(M.Invalid):
        M.validate_template(dict(OK, success_criteria=crit))


def test_a_well_formed_criterion_is_kept():
    crit = [{'text': 'it passes', 'check': 'automatic'},
            {'text': 'a person looks', 'check': 'human', 'origin': 'inferred'}]
    assert M.validate_template(dict(OK, success_criteria=crit))['success_criteria'] == crit


@pytest.mark.parametrize('where', [[], '', 0, False])
def test_a_falsy_where_that_is_not_a_mapping_is_not_match_everything(where):
    with pytest.raises(M.Invalid):
        M.validate_trigger({'type': 'mission.created', 'where': where}, TYPES)


def test_an_absent_or_empty_where_still_matches_everything():
    for t in ({'type': 'mission.created'}, {'type': 'mission.created', 'where': None},
              {'type': 'mission.created', 'where': {}}):
        assert M.validate_trigger(t, TYPES)['where'] == {}
