"""The fix batch 11 mutation suite (the review of fix batches 9 and 10): break each
guard that batch added to the redactor and its boundaries, to step-up, the
answered-request memo, the daemon lock, the redirect guard and the settings
sources, run the test that guards it, and require it to fail.

    py tools/mutate_fx11.py            every mutation
    py tools/mutate_fx11.py R01 R05    only these

Same runner as tools/mutate_p11.py: each mutation replaces exact snippets (each
must occur once), runs its tests, and restores the files whatever happens; a
mutation the tests do not catch ("survived") fails the run. It edits sources:
run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its runner)

RED = 'archeus/core/redact.py'
T = 'tests/v1/unit/test_redact.py::'
B = 'tests/v1/unit/test_fix_batch11.py::'
NS = 'tests/test_netsafe.py::'
ROUTES = 'archeus/api/routes.py'
AUTH = 'archeus/api/auth.py'
LOCAL = 'archeus/node/local.py'
PB = 'claude_sessions/proxy_base.py'
NET = 'claude_sessions/netsafe.py'
SRC = 'archeus/harnesses/sources.py'
F4 = B + 'test_f4_no_guess_is_admitted_while_the_revoke_keeps_failing_and_the_retry_lands_it'

MUTATIONS = [
    ('R01', 'redact_json leaves a string as it is', [(RED,
     r"""            dst[k] = redact(v)
""",
     r"""            dst[k] = v
""")],
     [T + 'test_redact_json_keeps_every_other_value_and_redacts_keys_and_deep_strings']),
    ('R02', 'redact_json does not match a value with its key', [(RED,
     r"""                    new[shown] = pair[len(shown) + 2:] if pair.startswith(shown + ': ') else '[redacted]'""",
     r"""                    new[shown] = redact(x)""")],
     [T + 'test_a_secret_named_by_its_key_is_redacted_in_a_document',
      T + 'test_a_quoted_aws_key_keeps_its_name_and_loses_its_value']),
    ('R03', 'a PEM runs past its END line', [(RED,
     r"""(?:(?!' + _PEM_END + r')[\s\S])""",
     r"""[\s\S]""")],
     [T + 'test_a_key_is_redacted_whatever_prefixes_its_lines']),
    ('R04', 'a PEM stops at the first character a key does not hold', [(RED,
     r"""[\s\S]){0,%d}""",
     r"""[A-Za-z0-9+/=:,.\s\-]){0,%d}""")],
     [T + 'test_a_key_is_redacted_whatever_prefixes_its_lines']),
    ('R05', 'a PEM has no bound', [(RED,
     r"""PEM_MAX = 16384""",
     r"""PEM_MAX = 100000""")],
     [T + 'test_a_key_without_an_end_line_is_cut_at_the_bound_not_at_the_first_odd_character']),
    ('R06', 'a token after a literal escape has no left edge', [(RED,
     r"""_EDGE = r'(?:(?<![A-Za-z0-9_\-])|(?<=\\[nrt]))'""",
     r"""_EDGE = r'(?:(?<![A-Za-z0-9_\-]))'""")],
     [T + 'test_a_token_after_a_literal_escape_is_still_at_a_left_edge']),
    ('R07', 'an escaped quote hides the AWS secret', [(RED,
     r"""_QUOTE = r'''(?:\\*["'])?'''""",
     r"""_QUOTE = r'''(?:["'])?'''""")],
     [T + 'test_a_doubly_escaped_aws_secret_and_a_quoted_userinfo_password_are_redacted']),
    ('R08', 'a quote in a userinfo password ends the match', [(RED,
     r"""r'(?<=://)[^\s/:@]+:[^\s/@]+(?=@)'""",
     r"""r'(?<=://)[^\s/:@"\\]+:[^\s/@"\\]+(?=@)'""")],
     [T + 'test_a_doubly_escaped_aws_secret_and_a_quoted_userinfo_password_are_redacted']),
    ('R09', 'a -u after a literal escape has no left edge', [(RED,
     r"""r'(?:(?<!\S)|(?<=\\[nrt]))(?:-u|--user)""",
     r"""r'(?<!\S)(?:-u|--user)""")],
     [T + 'test_a_token_after_a_literal_escape_is_still_at_a_left_edge']),
    ('S03', 'the answered memo outlives the process', [(LOCAL,
     r"""        _ANSWERED.pop(handle.execution_id, None)
        paths = ExecPaths(handle.execution_id)""",
     r"""        paths = ExecPaths(handle.execution_id)""")],
     [B + 'test_f5_the_answered_memo_is_dropped_when_the_process_ends']),
    ('S04', 'the answered memo is unbounded', [(LOCAL,
     r"""        while len(_ANSWERED) > _ANSWERED_MAX:""",
     r"""        while False:""")],
     [B + 'test_f5_the_answered_memo_holds_at_most_a_bounded_number_of_executions']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
