"""T-143 mutation suite. Run alone through testlock; sources restored by runner.

    py tools/mutate_t143.py
    py tools/mutate_t143.py Z638
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

C = 'archeus/core/execution/canonical.py'
T = 'tests/v1/integration/test_t143_policy_hosts.py::'
K = T + 'test_retained_k1_to_k4'
V = T + 'test_option_values_are_not_destinations'


def mutant(mid, name, old, new, *tests):
    return (mid, name, [(C, old, new)], list(tests))


MUTATIONS = [
    mutant('Z638', 'M1 long value flag does not consume next word',
           '                    mode = name\n            elif eq or',
           '                    mode = None\n            elif eq or', V),
    mutant('Z639', 'M2 short value is never skipped',
           "                if ch in letters:\n                    name = '-' + ch",
           "                if False:\n                    name = '-' + ch", V),
    mutant('Z640', 'M3 --url ignored',
           "        elif name == '--url':\n            positional(value)",
           "        elif name == '--url':\n            pass", K),
    mutant('Z641', 'M4 only first host kept',
           '    return result\n\n\ndef clear_host',
           '    return result[:1]\n\n\ndef clear_host', K),
    mutant('Z642', 'M5 any positional word resolves as a URL',
           'host = _policy_host(value) if _POLICY_URL.fullmatch(value) else None',
           'host = _policy_host(value)', T + 'test_unclassified_positional_destination_holds'),
    mutant('Z643', 'M6 equals option consumes next URL',
           '                if eq:\n                    take(name, val)',
           '                if eq:\n                    mode = name', K),
    mutant('Z644', 'M7 options parsed after --',
           '            bare = True\n        elif bare',
           '            bare = False\n        elif bare', K),
    mutant('Z645', 'M8 sending class lost',
           "cls, shown = 'external_comm' if _sends(args) else 'web', _url_arg(prog, args)",
           "cls, shown = 'web', _url_arg(prog, args)", T + 'test_class_and_chip_stay_separate'),
    mutant('Z646', 'M9 chip host copied to every action',
           'chip_host=clear_host(u) if u and u == shown else None)',
           'chip_host=clear_host(shown))', T + 'test_class_and_chip_stay_separate'),
    mutant('Z647', 'M10 fake first-word host when no URL',
           "        result.append(('', None))",
           "        result.append(('', host_of(next((a for a in args if not a.startswith('-')), ''))))", K),
    mutant('Z648', 'M12 dotted shape relaxed to any nonblank word',
           'host = _policy_host(value) if _POLICY_URL.fullmatch(value) else None',
           "host = _policy_host(value) if re.fullmatch(r'\\S+', value) else None",
           T + 'test_unclassified_positional_destination_holds'),
    mutant('Z649', 'restore old line 606 first-word pick',
           'for u, h in _policy_urls(prog, args)], False',
           "for u in [next((a for a in args if not a.startswith('-') and ('.' in a or '//' in a)), '')]\n"
           '                for h in [host_of(u)]], False', V,
           'tests/v1/integration/test_p21_activity.py::test_E10_the_policy_input_of_a_curl_or_wget_call_is_the_first_builds'),
    mutant('Z650', 'schemed destinations no longer sorted first',
           "for u, h in sorted(found, key=lambda p: '//' not in p[0]):",
           'for u, h in found:', K),
    mutant('Z651', 'M13 unresolved_file_allowed',
           '        if name in files:\n            unresolved = True',
           '        if name in files:\n            pass', T + 'test_unresolved_destination_files_hold'),
    mutant('Z652', 'M14 proxy_destination_ignored',
           '        elif name in proxies:\n            host =',
           '        elif name in proxies:\n            return\n            host =',
           T + 'test_proxy_destinations_judged_or_held'),
    mutant('Z653', 'M15 unknown_cluster_scans_on',
           '                if ch not in switches:\n                    unresolved = True\n                    break',
           '                if ch not in switches:\n                    continue',
           T + 'test_unknown_short_cluster_stops_and_holds'),
    mutant('Z654', 'M16 unknown_positional_dropped',
           '            unresolved = True\n\n    for a in args:',
           '            pass\n\n    for a in args:', T + 'test_unclassified_positional_destination_holds'),
    mutant('Z655', 'wget proxy setting ignored',
           "            if eq and key in ('http_proxy', 'https_proxy', 'ftp_proxy'):",
           '            if False:', T + 'test_proxy_destinations_judged_or_held'),
    mutant('Z656', 'enabled proxy without named destination allowed',
           '        proxy_enabled and (not proxy_named or bool(schemes - proxy_named)))',
           '        False)', T + 'test_wget_unresolved_proxy_setting_holds'),
    mutant('Z657', 'a root dot makes a different host',
           "host = (parsed.hostname or '').rstrip('.')",
           "host = parsed.hostname or ''", T + 'test_a_root_dot_is_not_a_different_host'),
    mutant('Z658', 'a port that is not one is not checked',
           '        parsed.port\n    except ValueError',
           '    except ValueError', T + 'test_a_port_that_is_not_one_leaves_the_destination_unresolved'),
    mutant('Z659', 'an attached or abbreviated long option value is ignored',
           '            elif eq or any(o.startswith(name) for o in (*values, *files, *extra, *proxies)):\n                unresolved = True',
           '            elif False:\n                unresolved = True',
           T + 'test_an_attached_or_abbreviated_option_value_keeps_the_destination_unresolved'),
    mutant('Z660', 'a proxy of another protocol resolves the enabled proxy',
           '(not proxy_named or bool(schemes - proxy_named))', '(not proxy_named)',
           T + 'test_a_named_proxy_resolves_only_its_own_protocol'),
    mutant('Z661', 'a host with ; or backslash in its netloc is still judged',
           r"    if re.search(r'[;\\]', parsed.netloc):" + "\n        return None\n",
           '', T + 'test_a_host_spelled_so_the_fetcher_reads_it_differently_is_unresolved'),
    mutant('Z662', 'a host outside the DNS alphabet is still judged',
           '    if not _HOST.fullmatch(host):\n        return None',
           '    if False:\n        return None', T + 'test_a_host_spelled_so_the_fetcher_reads_it_differently_is_unresolved'),
    mutant('Z663', 'a numeric host spelling is still judged',
           r"if re.fullmatch(r'(?:0x[0-9a-f]+|\d+)(?:\.(?:0x[0-9a-f]+|\d+)){0,3}', host) and not",
           'if False and not', T + 'test_a_host_spelled_so_the_fetcher_reads_it_differently_is_unresolved'),
]

if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
