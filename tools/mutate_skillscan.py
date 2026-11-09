import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

SCAN = 'claude_sessions/skillscan.py'
AGENTS = 'claude_sessions/agents.py'
T = 'tests/test_skillscan.py::'
CORPUS = T + 'test_the_lint_reports_exactly_what_each_fixture_sidecar_says'
NEVER = "re.compile('(?!)'),"

MUTATIONS = [
    ('SK01', 'an invisible character is never looked for', [(SCAN,
     'for m in _INVISIBLE.finditer(line):', "for m in _INVISIBLE.finditer(''):")],
     [CORPUS]),
    ('SK02', 'a bidi control is never looked for', [(SCAN,
     'm = _BIDI.search(line)', "m = _BIDI.search('')")],
     [CORPUS]),
    ('SK03', 'an instruction override is never matched', [(SCAN,
     "('instruction-override', 'med', _OVERRIDE,", "('instruction-override', 'med', " + NEVER)],
     [CORPUS]),
    ('SK04', 'fetch-and-execute is never matched', [(SCAN,
     "('fetch-and-execute', 'high', _FETCH,", "('fetch-and-execute', 'high', " + NEVER)],
     [CORPUS, T + 'test_every_finding_carries_a_rule_a_severity_a_line_and_a_reason']),
    ('SK05', 'a base64 run needs 2000 characters', [(SCAN,
     '{200,}={0,2}', '{2000,}={0,2}')],
     [CORPUS, T + 'test_an_image_data_uri_may_wrap_onto_base64_lines_but_a_bare_run_may_not']),
    ('SK06', 'an image data URI is not exempt from the base64 rule', [(SCAN,
     'if not any(a <= m.start() < b for a, b in uris):', 'if True:')],
     [CORPUS, T + 'test_an_image_data_uri_may_wrap_onto_base64_lines_but_a_bare_run_may_not']),
    ('SK07', 'a shell wrapper in an MCP entry passes', [(SCAN,
     'if _wraps_shell(toks) or _npx_yes_unpinned(toks):', 'if _npx_yes_unpinned(toks):')],
     [CORPUS, T + 'test_a_shell_wrapper_is_found_through_a_path_and_a_combined_flag']),
    ('SK08', 'npx -y of an unpinned package passes', [(SCAN,
     'if _wraps_shell(toks) or _npx_yes_unpinned(toks):', 'if _wraps_shell(toks):')],
     [CORPUS, T + 'test_npx_y_is_flagged_only_when_the_package_is_unpinned']),
    ('SK09', 'a pinned npx -y package is flagged too', [(SCAN,
     "return bool(pkgs) and not re.search(r'@\\d', pkgs[0].lstrip('@'))", 'return bool(pkgs)')],
     [T + 'test_npx_y_is_flagged_only_when_the_package_is_unpinned']),
    ('SK10', 'a hook through a shell wrapper passes', [(SCAN,
     'if _wraps_shell(cmd.split()):', 'if False:')],
     [CORPUS]),
    ('SK11', 'a server named like a built-in tool passes', [(SCAN,
     'if name in _BUILTIN_TOOLS:', 'if False:')],
     [CORPUS]),
    ('SK12', 'a changed description is not drift', [(SCAN,
     'if a and b and a[1] != b[1]:', 'if False:')],
     [CORPUS, T + 'test_a_description_that_changes_is_drift_and_one_that_stays_is_not']),
    ('SK13', 'a joiner inside an emoji sequence is hidden text', [(SCAN,
     "unicodedata.category(prev) == 'So'", "unicodedata.category(prev) == 'Zz'")],
     [T + 'test_a_family_emoji_joiner_and_a_leading_bom_are_not_hidden_text']),
    ('SK14', 'a leading byte order mark is hidden text', [(SCAN,
     'if (i == 1 and m.start() == 0) or (', 'if (False) or (')],
     [T + 'test_a_family_emoji_joiner_and_a_leading_bom_are_not_hidden_text']),
    ('SK15', 'the install review ignores the lint', [(SCAN,
     '        for f in lint(text):', '        for f in []:')],
     [T + 'test_the_install_review_shows_lint_findings_and_the_older_rule_is_not_doubled']),
    ('SK16', 'a finding the older rules report is shown twice', [(SCAN,
     'if _COVERED.get(f.rule) not in seen:', 'if True:')],
     [T + 'test_the_install_review_shows_lint_findings_and_the_older_rule_is_not_doubled']),
    ('SK17', 'a generated agent carries no warning', [(AGENTS,
     "warnings = [f'{f.rule} (line {f.line})' for f in skillscan.lint(md)]", 'warnings = []')],
     [T + 'test_a_generated_agent_with_a_finding_is_still_written_with_a_warning']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
