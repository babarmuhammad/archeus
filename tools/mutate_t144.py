"""The T-144 slice 1 mutation suite (T-144 design §4; Z300-Z314, T-130 renumbers):
break each rule of the home spelling matcher, run the test that guards it, and
require it to fail.

    py tools/mutate_t144.py            every mutation
    py tools/mutate_t144.py Z300 Z305  only these

The runner is tools/mutate_p18.py's (tools/mutate_p11.py's snippet engine): each
mutation replaces exact snippets (each must occur once), runs its tests, and
restores the files whatever happens; a mutation the tests do not catch
("survived") fails the run. It edits sources: run it with nothing else running
against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402  (its runner)

HM = 'archeus/core/homes.py'
T = 'tests/v1/unit/test_homes.py::'
SUFFIX = T + 'test_a_spelling_of_the_home_is_replaced_and_its_suffix_kept'
LOOK = T + 'test_a_look_alike_is_left_byte_identical'

MUTATIONS = [
    ('Z300', 'the match ignores no case', [(HM,
     r"    return '(?i:%s)' % rx if win else rx",
     r"    return rx")],
     [SUFFIX]),
    ('Z301', 'the MSYS, Cygwin and WSL prefixes dropped', [(HM,
     r"prefixes = ['%s:' % head, '/%s' % head, '/cygdrive/%s' % head, '/mnt/%s' % head,",
     r"prefixes = ['%s:' % head,")],
     [SUFFIX]),
    ('Z302', 'the file: URL prefix dropped', [(HM,
     r"""[\\/]{2}[?.][\\/]%s:' % head, r'file:(?://localhost)?/{1,3}%s(?::|%%3A)' % head]""",
     r"""[\\/]{2}[?.][\\/]%s:' % head]""")],
     [SUFFIX]),
    ('Z303', 'the UNC prefixes dropped', [(HM,
     "            elif unc:",
     "            elif False:")],
     [T + 'test_a_unc_home_matches_its_family']),
    ('Z304', 'the 8.3 short-name alternative dropped', [(HM,
     "    forms = [c, quote(c), short]",
     "    forms = [c, quote(c)]")],
     [SUFFIX]),
    ('Z305', 'no boundary after the home', [(HM,
     "re.compile(_LEFT + '(?:%s)' % '|'.join(alts) + _RIGHT)",
     "re.compile(_LEFT + '(?:%s)' % '|'.join(alts))")],
     [LOOK]),
    ('Z306', 'no boundary before the home', [(HM,
     "re.compile(_LEFT + '(?:%s)' % '|'.join(alts) + _RIGHT)",
     "re.compile('(?:%s)' % '|'.join(alts) + _RIGHT)")],
     [LOOK]),
    ('Z307', 'the pattern keeps a trailing separator', [(HM,
     "''.join(sep + p for p in parts)))",
     "''.join(sep + p for p in parts) + '(?:%s)?' % sep))")],
     [SUFFIX]),
    ('Z308', 'a doubled separator no longer matches', [(HM,
     r"_SEP = r'[\\/]+'",
     r"_SEP = r'[\\/]'")],
     [SUFFIX]),
    ('Z309', 'a dotted sibling matches', [(HM,
     r"_RIGHT = r'(?![\w~-]|\.\w)'",
     r"_RIGHT = r'(?![\w~-])'")],
     [LOOK]),
    ('Z310', 'the replacement eats the separator', [(HM,
     "        text = p.sub(REPLACEMENT, text)",
     r"        text = re.sub(p.pattern + r'[\\/]?', REPLACEMENT, text)")],
     [SUFFIX]),
    ('Z311', 'the typed ~ spelling dropped', [(HM,
     "                        out.append(_win(os.name == 'nt', '~' + ''.join(_SEP + _comp(p) for p in parts[1:])))",
     "                        pass")],
     [T + 'test_a_typed_tilde_spelling_matches']),
    ('Z312', 'norm_path without normpath', [(HM,
     "    s = posixpath.normpath(s)",
     "    s = s.rstrip('/') or '/'")],
     [T + 'test_norm_path_gives_one_form_per_place']),
    ('Z313', 'the default key map is empty', [(HM,
     "        self.keys = account_key_map(default_accounts)",
     "        self.keys = {}")],
     [T + 'test_a_default_key_becomes_its_handle_whole_or_inside_text']),
    ('Z314', 'public_value rewrites every string', [(HM,
     "_key=k, _text=_text or k in text_keys) for k, v in x.items()}",
     "_key=k, _text=True) for k, v in x.items()}")],
     [T + 'test_public_value_maps_keys_and_nulls_home_paths_only_under_path_keys']),
    ('Z334', 'native POSIX names incorrectly become MSYS aliases', [(HM,
     "    if m and (path_flavour in ('windows', 'msys', 'cygwin', 'wsl') or path_flavour is None and platform == 'win32'):",
     "    if m:")],
     [T + 'test_native_posix_msys_names_stay_literal']),
    ('Z335', 'drive-relative paths are accepted', [(HM,
     "    if re.match(r'^[A-Za-z]:(?![\\\\/])', s):\n        return None",
     "    if re.match(r'^[A-Za-z]:(?![\\\\/])', s):\n        return s")],
     [T + 'test_drive_relative_paths_are_rejected']),
    ('Z336', 'localhost URL prefix is omitted', [(HM,
     r"r'file:(?://localhost)?/{1,3}%s(?::|%%3A)' % head",
     r"r'file:/{2,3}%s(?::|%%3A)' % head")],
     [T + 'test_localhost_url_prefix_keeps_suffix']),
    ('Z337', 'device prefix is omitted', [(HM,
     r"r'[\\/]{2}[?.][\\/]%s:' % head",
     r"r'[\\/]{2}[?][\\/]%s:' % head")],
     [T + 'test_device_prefix_keeps_suffix']),
    ('Z338', 'root structural separator is consumed', [(HM,
     "root = '(?:%s)' % '|'.join(prefixes) + '(?=%s)' % sep",
     "root = '(?:%s)' % '|'.join(prefixes) + sep")],
     [T + 'test_root_separator_is_structural_and_preserved']),
    ('Z344', 'distinct stored keys collapse to one id', [(HM,
     "return {key: public_account_id(key) for _, key, _ in default_accounts}",
     "return {key: public_account_id('default') for _, key, _ in default_accounts}")],
     [T + 'test_distinct_exact_stored_keys_have_distinct_public_ids']),
    ('Z345', 'same-key id changes across restart', [(HM,
     "hashlib.sha256(key.encode('utf-8')).hexdigest()",
     "hashlib.sha256(key.encode('utf-8') + os.urandom(16)).hexdigest()")],
     [T + 'test_same_key_id_survives_restart']),
    ('Z346', 'historical snapshot keys omitted from map', [(HM,
     "return {key: public_account_id(key) for _, key, _ in default_accounts}",
     "return {key: public_account_id(key) for _, key, _ in list(default_accounts)[:1]}")],
     [T + 'test_historical_keys_map_whole_and_embedded_without_mutation']),
    ('Z347', 'historical id derivation probes account homes', [(HM,
     "return {key: public_account_id(key) for _, key, _ in default_accounts}",
     "return {key: public_account_id(key) for _, key, home in default_accounts if not _win_short(home)}")],
     [T + 'test_historical_identity_never_probes_homes']),
    ('Z348', 'public id leaks stored key material', [(HM,
     "return 'account:' + hashlib.sha256(key.encode('utf-8')).hexdigest()",
     "return 'account:' + key")],
     [T + 'test_public_ids_reveal_no_home_or_key_material']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
