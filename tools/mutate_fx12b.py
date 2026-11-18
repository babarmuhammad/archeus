"""The fix batch 12b mutation suite (the review of the int4 delta, R2 R3 S4): break each
guard the batch added to the redactor and the stream read, run the test that guards
it, and require it to fail.

    py tools/mutate_fx12b.py            every mutation
    py tools/mutate_fx12b.py K01        only these

Same runner as tools/mutate_p11.py. It edits sources: run it with nothing else running
against the tree. The broker listener's guards are in tools/mutate_mxc_broker.py (L25-L31).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its runner)

RED = 'archeus/core/redact.py'
BASE = 'archeus/harnesses/base.py'
T = 'tests/v1/unit/test_redact.py::'
A = 'tests/v1/integration/test_api_audit_fixes.py::'
S = 'tests/v1/integration/test_stream_redaction_red_team.py::'

MUTATIONS = [
    ('K01', 'a stream line does not carry a key on to the next line', [(BASE,
     r"""    text, state = redact.scrub(line, state, 'stderr')""",
     r"""    text = redact.scrub(line, state, 'stderr')[0]""")],
     [A + 'test_a_key_on_separate_stderr_lines_is_redacted_in_every_line']),
    ('K02', 'a read does not fold the stream before its offset', [(BASE,
     r"""        offset, state = _state_at(f, points, offset)""",
     r"""        state = None""")],
     [A + 'test_a_read_that_starts_inside_a_key_redacts_the_rest_of_it',
      A + 'test_a_window_cut_inside_a_key_redacts_the_rest_of_it']),
    ('K03', 'a checkpoint forgets the key state it was taken in', [(BASE,
     r"""        points.append((pos, state))""",
     r"""        points.append((pos, None))""")],
     [A + 'test_a_key_too_long_to_see_its_start_is_still_redacted']),
    ('K04', 'an oversized line does not carry a key on', [(BASE,
     r"""        return ev, n, redact.after(state, channel, mark)""",
     r"""        return ev, n, state""")],
     [A + 'test_a_key_that_begins_inside_an_oversized_line_is_redacted_after_it']),
    ('K05', 'a marker cut by the end of an oversized read is missed', [(BASE,
     r"""        seam = flat[-80:]""",
     r"""        seam = ''""")],
     [A + 'test_a_key_that_begins_inside_an_oversized_line_is_redacted_after_it']),
    ('K06', 'a fragment that ends the key is not closed', [(RED,
     r"""    m = _PEM_END_AT.search(text)""",
     r"""    m = None""")],
     [S + 'test_the_text_after_an_end_line_that_closes_a_key_is_kept']),
    ('K07', 'keys that redact to one name collapse', [(RED,
     r"""        clash = len(set(names)) < len(names)""",
     r"""        clash = False""")],
     [T + 'test_keys_that_redact_to_one_name_stay_distinct_fields']),
    ('K08', 'a key named like a redacted one takes its place', [(RED,
     r"""(name != keys[i] or '[redacted' in name)""",
     r"""(name != keys[i])""")],
     [T + 'test_keys_that_redact_to_one_name_stay_distinct_fields']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
