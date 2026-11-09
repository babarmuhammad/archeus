"""The fix batch 16 mutation suite (the review of pv20-fx15): break each rule the batch
added, run the test that guards it, and require it to fail.

    py tools/mutate_fx16.py            every mutation
    py tools/mutate_fx16.py H01 H05    only these

Same runner as tools/mutate_p11.py. It edits sources: run it with nothing else running
against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its runner)

RED = 'archeus/core/redact.py'
R = 'tests/v1/unit/test_redact_red_team.py::'
S = 'tests/v1/integration/test_stream_redaction_red_team.py::'

MUTATIONS = [
    ('H01', 'a lowercase word of an event is masked as a short fragment', [(RED,
     r"""_LINE.fullmatch(x) and not (x.isalpha() and x.islower())""",
     r"""_LINE.fullmatch(x)""")],
     [R + 'test_the_structural_words_of_an_event_stay_while_a_key_is_open',
      S + 'test_a_result_after_an_open_key_keeps_its_usage_summary_and_error']),
    ('H02', 'any alphabetic word is let through an open key', [(RED,
     r"""not (x.isalpha() and x.islower())""",
     r"""not x.isalpha()""")],
     [R + 'test_a_short_fragment_that_is_not_a_lowercase_word_is_still_held']),
    ('H03', 'a field name that reads as prose ends the key', [(RED,
     r"""last_mark(text), None if name else text)""",
     r"""last_mark(text), text)""")],
     [R + 'test_a_field_name_that_reads_as_prose_does_not_end_the_key']),
    ('H04', 'a body line followed by a few characters is not key material', [(RED,
     r"""{16}[^A-Za-z0-9+/=\n]{0,4}[ \t\r]*$'""",
     r"""{16}[ \t\r]*$'""")],
     [R + 'test_a_body_line_with_a_few_trailing_characters_is_held',
      R + 'test_a_body_line_used_as_a_field_name_with_a_colon_is_held']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
