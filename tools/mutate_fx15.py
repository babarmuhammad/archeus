"""The fix batch 15 mutation suite (the review of pv20-int8): break each rule the batch
added, run the test that guards it, and require it to fail.

    py tools/mutate_fx15.py            every mutation
    py tools/mutate_fx15.py G01 G05    only these

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
ROUTER = 'archeus/core/routing/router.py'
E = 'tests/v1/unit/test_effort_selection.py::'

MUTATIONS = [
    ('G01', 'a field name does not carry the key state to the fields after it', [(RED,
     r"""            dst[k], state = _name(v, state)""",
     r"""            dst[k] = _name(v, state)[0]""")],
     [R + 'test_a_marker_used_as_a_json_field_name_opens_the_key_for_later_fields',
      R + 'test_a_key_line_used_as_a_json_field_name_is_held']),
    ('G02', 'a field name is read after the value that follows it', [(RED,
     r"""                entries += [(key, slot, 0, _KEY, depth + 1), (x, slot, 1, key, depth + 1)]""",
     r"""                entries += [(x, slot, 1, key, depth + 1), (key, slot, 0, _KEY, depth + 1)]""")],
     [R + 'test_a_field_name_is_read_before_its_own_value']),
    ('G03', 'a short fragment of an open key is shown', [(RED,
     r""" or not name and _short(text):""",
     r""":""")],
     [R + 'test_a_short_key_fragment_in_an_open_key_is_held',
      R + 'test_a_short_fragment_is_held_in_the_stderr_channel_too']),
    ('G04', 'a plain field name is masked as a short fragment', [(RED,
     r""" or not name and _short(text):""",
     r""" or _short(text):""")],
     [R + 'test_a_plain_field_name_stays_while_a_key_is_open']),
    ('G05', 'a string with one base64 line is a short fragment', [(RED,
     r"""    return bool(lines) and all(_LINE.fullmatch(x) for x in lines)""",
     r"""    return bool(lines) and any(_LINE.fullmatch(x) for x in lines)""")],
     [R + 'test_a_string_of_a_base64_line_and_prose_is_not_a_short_fragment']),
    ('G06', 'an empty string is a short fragment', [(RED,
     r"""    return bool(lines) and all(""",
     r"""    return all(""")],
     [R + 'test_an_empty_string_is_not_masked_while_a_key_is_open']),
    ('G07', 'an escaped character of a marker in an oversized line is not read', [(BASE,
     r"""        flat = _BLANKS.sub(' ', _ASCII.sub(lambda m: chr(int(m[1], 16)),
                                           seam + rest.decode('utf-8', errors='replace')))""",
     r"""        flat = _BLANKS.sub(' ', seam + rest.decode('utf-8', errors='replace'))""")],
     [S + 'test_an_oversized_json_line_with_an_escaped_marker_opens_the_key',
      S + 'test_an_escape_cut_by_the_read_boundary_still_opens_the_key']),
    ('G08', 'blanks of an oversized line are not folded', [(BASE,
     r"""        flat = _BLANKS.sub(' ', _ASCII.sub(lambda m: chr(int(m[1], 16)),
                                           seam + rest.decode('utf-8', errors='replace')))""",
     r"""        flat = _ASCII.sub(lambda m: chr(int(m[1], 16)), seam + rest.decode('utf-8', errors='replace'))""")],
     [S + 'test_a_marker_whose_blanks_span_a_read_boundary_opens_the_key',
      S + 'test_a_marker_whose_blanks_end_at_the_first_read_boundary']),
    ('G09', 'a model whose efforts its harness lacks keeps the requested effort', [(ROUTER,
     r"""            c['effort'] = None""",
     r"""            pass""")],
     [E + 'test_a_model_that_states_efforts_its_harness_lacks_takes_no_effort']),
    ('G10', 'a required effort no common level can take is not refused', [(ROUTER,
     r"""            if req.get('effort_required'):
                return 'model %s accepts none""",
     r"""            if False:
                return 'model %s accepts none""")],
     [E + 'test_a_required_effort_a_model_with_no_common_level_cannot_take_eliminates_it']),
    ('G11', 'a model that states no efforts is held to none', [(ROUTER,
     r"""        if stated and not allowed:""",
     r"""        if not allowed:""")],
     [E + 'test_the_router_clamps_effort_to_the_chosen_model_and_records_it']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
