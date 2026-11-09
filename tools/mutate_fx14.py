"""The fix batch 14 mutation suite (the red-team round on redaction): break each rule
the batch added to the redactor's patterns, its walk of a JSON document, the key
state carried over strings and the fold that gives a read from any offset that state,
run the test that guards it, and require it to fail.

    py tools/mutate_fx14.py            every mutation
    py tools/mutate_fx14.py F01 F05    only these

Same runner as tools/mutate_p11.py. It edits sources: run it with nothing else running
against the tree. The broker reader's guards are in tools/mutate_mxc_broker.py (L29-L31).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its runner)

RED = 'archeus/core/redact.py'
BASE = 'archeus/harnesses/base.py'
OUT = 'archeus/core/execution/output.py'
R = 'tests/v1/unit/test_redact_red_team.py::'
S = 'tests/v1/integration/test_stream_redaction_red_team.py::'
A = 'tests/v1/integration/test_api_audit_fixes.py::'

MUTATIONS = [
    ('F01', 'a key marker has one case', [(RED,
     r"""_MARK = r'(?<!-)-{4,}(?i:(%s)""",
     r"""_MARK = r'(?<!-)-{4,}(?:(%s)""")],
     [R + 'test_pem_marker_variants']),
    ('F02', 'a key marker needs five dashes', [(RED,
     r"""_MARK = r'(?<!-)-{4,}""",
     r"""_MARK = r'(?<!-)-{5,}""")],
     [R + 'test_pem_marker_variants']),
    ('F03', 'the words of a key marker are spaced by one space', [(RED,
     r"""(%s)\s+(?:[A-Z0-9]+\s+){0,4}PRIVATE\s+KEY)""",
     r"""(%s) (?:[A-Z0-9]+ ){0,4}PRIVATE KEY)""")],
     [R + 'test_pem_marker_variants']),
    ('F04', 'a JWT glued to a word or with no signature is let through', [(RED,
     r"""    r'\.eyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]*',
""", '')],
     [R + 'test_jwt_glued_to_a_word_character', R + 'test_jwt_empty_signature_alg_none']),
    ('F05', 'a quote before the colon hides a Basic header', [(RED,
     r"""    r'(?i:authorization)' + _QUOTE + r'\s*[:=]""",
     r"""    r'(?i:authorization)' + r'\s*[:=]""")],
     [R + 'test_basic_auth_forms', R + 'test_nested_json_in_a_string_with_basic_auth']),
    ('F06', 'curl -u needs a blank before its user', [(RED,
     r"""(?:-u|--user)[\s=]*' + _QUOTE""",
     r"""(?:-u|--user)[\s=]+' + _QUOTE""")],
     [R + 'test_curl_user_forms']),
    ('F07', 'a quoted curl user hides its password', [(RED,
     r"""(?:-u|--user)[\s=]*' + _QUOTE + r'''""",
     r"""(?:-u|--user)[\s=]*' + r'''""")],
     [R + 'test_curl_user_forms']),
    ('F08', 'a bare userinfo token is let through', [(RED,
     r"""    r'(?<=://)[^\s/:@]{8,}(?=@)',
""", '')],
     [R + 'test_url_userinfo']),
    ('F09', 'a list is walked from its last item', [(RED,
     r"""for i in reversed(range(len(items))))""",
     r"""for i in range(len(items)))""")],
     [R + 'test_pem_split_over_two_strings_of_a_list', S + 'test_key_as_lines_of_a_tool_input_array']),
    ('F10', 'a dict is walked from its last entry', [(RED,
     r"""            todo.extend(reversed(entries))""",
     r"""            todo.extend(entries)""")],
     [R + 'test_pem_split_over_two_values_of_a_dict']),
    ('F11', 'a shared or cyclic container is walked again', [(RED,
     r"""        elif isinstance(v, _CONTAINERS) and id(v) in seen:""",
     r"""        elif False:""")],
     [R + 'test_a_cyclic_structure_returns', R + 'test_shared_substructure_is_walked_once']),
    ('F12', 'a tuple or a set is not walked', [(RED,
     r"""        elif isinstance(v, _CONTAINERS):
            items""",
     r"""        elif isinstance(v, list):
            items""")],
     [R + 'test_tuple_set_and_bytes_are_redacted']),
    ('F13', 'bytes are not redacted', [(RED,
     r"""        if isinstance(v, (bytes, bytearray)):""",
     r"""        if False:""")],
     [R + 'test_tuple_set_and_bytes_are_redacted']),
    ('F14', 'a key that is not a string or a number is kept as it is', [(RED,
     r"""    return k if k is None or isinstance(k, (int, float)) else redact(str(k))""",
     r"""    return k""")],
     [R + 'test_tuple_set_and_bytes_are_redacted']),
    ('F15', 'the stream has no depth cap', [(BASE,
     r"""            return redact.scrub_json(json.loads(line), state, MAX_DEPTH)""",
     r"""            return redact.scrub_json(json.loads(line), state)""")],
     [S + 'test_an_event_nested_past_the_depth_cap_is_a_stderr_line']),
    ('F16', 'the depth cap is never checked', [(RED,
     r"""        if max_depth is not None and depth > max_depth:""",
     r"""        if False:""")],
     [S + 'test_an_event_nested_past_the_depth_cap_is_a_stderr_line']),
    ('F17', 'an END mentioned in the other channel closes the key', [(RED,
     r"""        return None if state in (None, channel) else state""",
     r"""        return None""")],
     [S + 'test_an_end_mentioned_in_a_json_event_does_not_close_a_stderr_key']),
    ('F18', 'prose ends a key printed on stderr', [(RED,
     r"""    if state is None or state == channel == 'stderr' or text is None""",
     r"""    if state is None or text is None""")],
     [S + 'test_a_stderr_key_runs_to_its_end_line_whatever_its_lines_say']),
    ('F19', 'a short line of a stderr key is shown', [(RED,
     r"""        elif state == channel == 'stderr' or _BODY.search(text):""",
     r"""        elif _BODY.search(text):""")],
     [S + 'test_a_stderr_key_runs_to_its_end_line_whatever_its_lines_say']),
    ('F20', 'key material outside its own stderr channel is shown', [(RED,
     r"""        elif state == channel == 'stderr' or _BODY.search(text):""",
     r"""        elif state == channel == 'stderr':""")],
     [S + 'test_key_begin_in_one_event_body_in_the_next',
      S + 'test_key_begin_in_a_json_event_body_in_stderr_lines']),
    ('F21', 'prose never ends a key of the json channel', [(RED,
     r"""    return None if state == channel and _PROSE.search(text) else state""",
     r"""    return state""")],
     [S + 'test_prose_ends_a_key_of_the_json_channel_from_any_offset']),
    ('F22', 'a header line is prose', [(RED,
     r"""_PROSE = re.compile(r'^(?![ \t]*[A-Za-z][A-Za-z0-9-]*:)[ \t]*""",
     r"""_PROSE = re.compile(r'^[ \t]*""")],
     [S + 'test_a_key_over_json_strings_keeps_its_armor_headers_inside_it']),
    ('F23', 'prose in the other channel ends the key', [(RED,
     r"""    return None if state == channel and _PROSE.search(text) else state""",
     r"""    return None if _PROSE.search(text) else state""")],
     [S + 'test_prose_in_an_event_does_not_end_a_key_printed_on_stderr']),
    ('F24', 'the fold skips a line whose marker is escaped', [(BASE,
     r"""    return b'----' not in raw and b'\\u' not in raw""",
     r"""    return b'----' not in raw""")],
     [S + 'test_an_escaped_marker_in_a_json_line_opens_the_key_for_a_paged_read']),
    ('F25', 'the fold skips a block that holds a marker', [(BASE,
     r"""            if cut and _quiet(block[:cut]):""",
     r"""            if cut:""")],
     [S + 'test_key_across_a_read_window_that_starts_at_each_line_held']),
    ('F26', 'the fold skips blocks while a json key is open', [(BASE,
     r"""        if state != 'json':
            block""",
     r"""        if True:
            block""")],
     [S + 'test_prose_ends_a_key_of_the_json_channel_from_any_offset']),
    ('F27', 'the fold skips the lines of an open json key', [(BASE,
     r"""    if not emit and state != 'json' and _quiet(raw):""",
     r"""    if not emit and _quiet(raw):""")],
     [S + 'test_prose_ends_a_key_of_the_json_channel_from_any_offset']),
    ('F28', 'a read from inside a line starts there', [(BASE,
     r"""    return pos, state


def read_stream""",
     r"""    return offset, state


def read_stream""")],
     [S + 'test_a_read_from_inside_a_line_starts_at_the_next_one']),
    ('F29', 'a stream written anew keeps its old checkpoints', [(BASE,
     r"""        if not head.startswith(seen['head']) or f.read(min(32, last)) != seen['tail']:""",
     r"""        if False:""")],
     [S + 'test_a_stream_written_anew_is_folded_anew']),
    ('F30', 'the fold remembers every stream', [(BASE,
     r"""        while len(_SEEN) > _SEEN_MAX:""",
     r"""        while False:""")],
     [S + 'test_the_fold_remembers_a_bounded_number_of_streams']),
    ('F31', 'an over-long line forgets a marker of its earlier part', [(BASE,
     r"""errors='replace')) or mark""",
     r"""errors='replace'))""")],
     [A + 'test_a_key_that_begins_inside_an_oversized_line_is_redacted_after_it']),
    ('F32', 'the stream is read unredacted', [(BASE,
     r"""            return redact.scrub_json(json.loads(line), state, MAX_DEPTH)""",
     r"""            return json.loads(line), state""")],
     [S + 'test_the_result_summary_is_redacted']),
    ('F33', 'a window of tiny lines is read whole', [(OUT,
     r"""    return start + end + 1, True""",
     r"""    return start, start > offset""")],
     [S + 'test_a_window_of_tiny_lines_reads_only_the_newest_lines']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
