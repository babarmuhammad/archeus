"""T-1459: gap probes for archeus/core/automation/matcher.py lines 84-146 that the
existing matcher tests do not assert: the placeholders '{payload.}' and '{unknown}'
are refused in the title and the objective, and the allowed placeholders still pass.
The schedule period, next-due grid and extra-key checks are already asserted by
test_gaps_core_automation_matcher.py and test_automation_units.py and are not repeated.
Pure values in and out; no clock, no I/O.
"""

import pytest

from archeus.core.automation import matcher as M


@pytest.mark.parametrize('name', ['{payload.}', '{unknown}'])
@pytest.mark.parametrize('field', ['title', 'objective'])
def test_an_empty_payload_key_or_an_unknown_name_is_not_a_placeholder(field, name):
    # matcher.py:124-127 _ALLOWED.fullmatch rejects 'payload.' (needs \w+) and any name
    # outside the allowed set
    template = {'title': 't', 'objective': 'o'}
    template[field] = 'x %s y' % name
    with pytest.raises(M.Invalid, match='is not a placeholder'):
        M.validate_template(template)


def test_an_allowed_placeholder_is_accepted_in_the_title_and_the_objective():
    # matcher.py:124-127 the allowed set passes through unchanged into the stored template
    t = M.validate_template({'title': 'on {event.type}', 'objective': 'for {payload.path}'})
    assert t == {'title': 'on {event.type}', 'objective': 'for {payload.path}',
                 'success_criteria': []}
