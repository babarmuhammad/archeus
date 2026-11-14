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
     r"""            dst[k], state = scrub(v, state, 'json', plain)
""",
     r"""            dst[k] = v
""")],
     [T + 'test_redact_json_keeps_every_other_value_and_redacts_keys_and_deep_strings']),
    ('R02', 'redact_json does not match a value with its key', [(RED,
     r"""                plain = pair[len(name) + 2:] if pair.startswith(name + ': ') else '[redacted]'""",
     r"""                plain = None""")],
     [T + 'test_a_secret_named_by_its_key_is_redacted_in_a_document',
      T + 'test_a_quoted_aws_key_keeps_its_name_and_loses_its_value']),
    ('R03', 'a PEM runs past its END line', [(RED,
     r"""[\s\S]*?(?:%s|\Z)""",
     r"""[\s\S]*(?:%s|\Z)""")],
     [T + 'test_a_key_is_redacted_whatever_prefixes_its_lines']),
    ('R04', 'a PEM stops at the first character a key does not hold', [(RED,
     r"""[\s\S]*?(?:%s|\Z)""",
     r"""[A-Za-z0-9+/=:,.\s\-]*?(?:%s|\Z)""")],
     [T + 'test_a_key_is_redacted_whatever_prefixes_its_lines']),
    ('R05', 'a key with no END line ends at its first line', [(RED,
     r"""[\s\S]*?(?:%s|\Z)""",
     r"""[\s\S]*?(?:%s|\n)""")],
     [T + 'test_a_key_of_any_size_is_redacted_to_its_end_line_or_to_the_end_of_the_text']),
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
    ('S01', 'a locked-out device does not retry its revoke', [(ROUTES,
     r"""        if req.api.step_up.locked(device):""",
     r"""        if False:""")], [F4]),
    ('S02', 'the lockout is never reported', [(AUTH,
     r"""            return self._n.get(device_id, 0) >= self.LIMIT""",
     r"""            return False""")], [F4]),
    ('S03', 'the answered memo outlives the process', [(LOCAL,
     r"""        _ANSWERED.pop(handle.execution_id, None)
        paths = ExecPaths(handle.execution_id)""",
     r"""        paths = ExecPaths(handle.execution_id)""")],
     [B + 'test_f5_the_answered_memo_is_dropped_when_the_process_ends']),
    ('S04', 'the answered memo is unbounded', [(LOCAL,
     r"""        while len(_ANSWERED) > _ANSWERED_MAX:""",
     r"""        while False:""")],
     [B + 'test_f5_the_answered_memo_holds_at_most_a_bounded_number_of_executions']),
    ('S05', 'a lock older than its pid is never cleared', [(PB,
     r"""            if started is not None and os.path.getmtime(self.lock_path()) < started - 2:""",
     r"""            if False:""")],
     [B + 'test_f6_a_lock_older_than_its_pid_is_cleared_and_the_stranger_left_alone']),
    ('S06', 'a lock the pid may have written is cleared', [(PB,
     r"""os.path.getmtime(self.lock_path()) < started - 2:""",
     r"""os.path.getmtime(self.lock_path()) < started + 3600:""")],
     [B + 'test_f6_a_lock_the_pid_may_have_written_is_kept_and_the_refusal_names_the_way_out']),
    ('S07', 'a failed kill blames the lock', [(PB,
     r"""        return False, 'could not stop pid %s' % pid""",
     r"""        return False, 'pid %s is not the %s that wrote the lock' % (pid, self.label)""")],
     [B + 'test_f6_a_kill_that_fails_on_the_recorded_process_says_so']),
    ('S08', 'an https upgrade may change host', [(NET,
     r""" and old[1] == new[1]""", r"""""")],
     [NS + 'test_f7_a_same_host_upgrade_to_https_keeps_the_credential_and_a_downgrade_or_host_change_does_not']),
    ('S09', 'an https upgrade may change port', [(NET,
     r"""(old[0], new[0], old[2], new[2]) == ('http', 'https', 80, 443)""",
     r"""(old[0], new[0]) == ('http', 'https')""")],
     [NS + 'test_f7_a_same_host_upgrade_to_https_keeps_the_credential_and_a_downgrade_or_host_change_does_not']),
    ('S10', 'a URL that does not parse is followed', [(NET,
     r"""    except ValueError:
        return False""",
     r"""    except ValueError:
        return True""")],
     [NS + 'test_f9_a_location_with_a_bad_port_is_a_refusal_not_an_exception']),
    ('S11', 'a deeply nested settings file raises', [(SRC,
     r"""    except (ValueError, RecursionError):""",
     r"""    except ValueError:""")],
     [B + 'test_f8_a_settings_file_nested_past_the_parser_depth_is_not_json']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
