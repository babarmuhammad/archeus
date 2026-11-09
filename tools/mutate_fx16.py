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
BASE = 'archeus/harnesses/base.py'
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
     r"""{16}(?:\\[nrt]|[^A-Za-z0-9+/=\n]){0,4}[ \t\r]*$'""",
     r"""{16}[ \t\r]*$'""")],
     [R + 'test_a_body_line_with_a_few_trailing_characters_is_held',
      R + 'test_a_body_line_used_as_a_field_name_with_a_colon_is_held']),
    ('H05', 'a body line followed by a literal backslash-n is not key material', [(RED,
     r"""(?:\\[nrt]|[^A-Za-z0-9+/=\n]){0,4}""",
     r"""(?:[^A-Za-z0-9+/=\n]){0,4}""")],
     [R + 'test_a_body_line_with_a_few_trailing_characters_is_held']),
    ('H06', 'an oversized line caught mid-write is cut where the read ended', [(BASE,
     r"""        if not rest:
            return None
        if rest.endswith(b'\n'):""",
     r"""        if not rest or rest.endswith(b'\n'):""")],
     [S + 'test_an_oversized_line_caught_mid_write_is_read_whole_once_it_ends']),
    ('H07', 'the head of an oversized line inside a key is shown', [(BASE,
     r"""'[redacted]' if state is not None or mark is not None else""",
     r"""'[redacted]' if mark is not None else""")],
     [S + 'test_the_head_of_an_oversized_line_inside_or_opening_a_key_is_masked']),
    ('H08', 'the head of an oversized line with its own marker is shown', [(BASE,
     r"""'[redacted]' if state is not None or mark is not None else""",
     r"""'[redacted]' if state is not None else""")],
     [S + 'test_the_head_of_an_oversized_line_inside_or_opening_a_key_is_masked']),
    ('H09', 'a blank escape is not read in an oversized line', [(BASE,
     r"""_ASCII = re.compile(r'\\u00([0-7][0-9a-fA-F])|\\[nrtbf]')""",
     r"""_ASCII = re.compile(r'\\u00([0-7][0-9a-fA-F])')""")],
     [S + 'test_an_oversized_line_whose_marker_has_escaped_blanks_opens_the_key']),
    ('H10', 'the head of a dropped line keeps the token cut at its end', [(BASE,
     r"""                _CUT.sub('', raw[:200].decode('utf-8', errors='replace')).strip())""",
     r"""                raw[:200].decode('utf-8', errors='replace').strip())""")],
     [S + 'test_the_head_cut_of_an_oversized_line_keeps_no_token_prefix']),
    ('H11', 'a marker in an oversized JSON line opens a stderr key', [(BASE,
     r"""        channel = 'json' if raw.lstrip""",
     r"""        channel = 'stderr' if raw.lstrip""")],
     [S + 'test_an_oversized_json_line_opens_a_key_that_json_prose_ends']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
