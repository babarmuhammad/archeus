"""The fix batch 12b mutation suite (the review of the int4 delta, R2 R3 S4): break each
guard the batch added to the redactor and the stream read, run the test that guards
it, and require it to fail.

    py tools/mutate_fx12b.py            every mutation
    py tools/mutate_fx12b.py K01        only these

Same runner as tools/mutate_p11.py. It edits sources: run it with nothing else running
against the tree. The broker listener's guards are in tools/mutate_mxc_broker.py (L27, L28).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its runner)

RED = 'archeus/core/redact.py'
BASE = 'archeus/harnesses/base.py'
T = 'tests/v1/unit/test_redact.py::'
A = 'tests/v1/integration/test_api_audit_fixes.py::'

MUTATIONS = [
    ('K01', 'a stream line does not carry a key on to the next line', [(BASE,
     r"""                line, inside = close_pem(line, inside)""",
     r"""                line = close_pem(line, False)[0]""")],
     [A + 'test_a_key_on_separate_stderr_lines_is_redacted_in_every_line']),
    ('K02', 'a read does not look before its offset', [(BASE,
     r"""        inside = offset > 0 and _inside_key(f, offset)""",
     r"""        inside = False""")],
     [A + 'test_a_read_that_starts_inside_a_key_redacts_the_rest_of_it',
      A + 'test_a_window_cut_inside_a_key_redacts_the_rest_of_it']),
    ('K03', 'a key too long to see its start is let through', [(BASE,
     r"""    return start > 0 and '-----' not in text and""",
     r"""    return False and""")],
     [A + 'test_a_key_too_long_to_see_its_start_is_still_redacted']),
    ('K04', 'an oversized line does not carry a key on', [(BASE,
     r"""                inside = pem_open((seam + rest).decode('utf-8', errors='replace'), inside)
                    seam""",
     r"""                inside = inside
                    seam""")],
     [A + 'test_a_key_that_begins_inside_an_oversized_line_is_redacted_after_it']),
    ('K05', 'a marker cut by the end of an oversized read is missed', [(BASE,
     r"""                    seam = rest[-80:]""",
     r"""                    seam = b''""")],
     [A + 'test_a_key_that_begins_inside_an_oversized_line_is_redacted_after_it']),
    ('K06', 'a fragment that ends the key is not closed', [(RED,
     r"""    m = _PEM_END_AT.search(text)""",
     r"""    m = None""")],
     [A + 'test_a_key_on_separate_stderr_lines_is_redacted_in_every_line']),
    ('K07', 'keys that redact to one name collapse', [(RED,
     r"""            clash = len(set(names)) < len(names)""",
     r"""            clash = False""")],
     [T + 'test_keys_that_redact_to_one_name_stay_distinct_fields']),
    ('K08', 'a key named like a redacted one takes its place', [(RED,
     r"""(name != key or '[redacted' in key)""",
     r"""(name != key)""")],
     [T + 'test_keys_that_redact_to_one_name_stay_distinct_fields']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
