"""T-143: policy destinations, independently of activity-chip URL selection."""

import pytest

from archeus.core.execution import canonical
from archeus.core.policy import engine, rules

G = 'https://good.example/x'
E = 'https://evil.example/x'


def actions(cmd):
    acts, unknown = canonical.canonicalise('Bash', cmd, {'workdir': '.'})
    assert unknown is False
    assert all(a.argv == acts[0].argv for a in acts)
    return acts


def allowed(acts, policy):
    rs = []
    for cls in ('web', 'external_comm'):
        rs.append(rules.rule(id='base:' + cls, scope_level='USER', scope_ref='u',
                             action_class=cls, decision='ALLOW' if policy == 'd' else 'ASK'))
        kw = ({'decision': 'DENY', 'match': {'host_glob': 'evil.example'}} if policy == 'd'
              else {'decision': 'ALLOW', 'match': {'host_glob': 'good.example'}} if policy == 'a'
              else {'decision': 'ALLOW_WITHIN_BOUNDARY', 'boundary': {'hosts': ['good.example']},
                    'outside': 'DENY'})
        rs.append(rules.rule(id='mission:' + cls, scope_level='MISSION', scope_ref='m',
                             action_class=cls, **kw))
    answers = [engine.evaluate_item(a, {
        'stage': 'action', 'chain': {'USER': 'u', 'MISSION': 'm'}, 'rules': rs,
        'profiles': {'USER': None},
    }) for a in acts]
    return all(r['decision'] in ('ALLOW', 'ALLOW_WITHIN_BOUNDARY') for r in answers)


# Every option-value row must independently kill restoration of the old first-word pick.
@pytest.mark.parametrize('prefix', [
    'curl -H "X: a.b"', "curl -H 'X: a.b'", 'curl --header "X: a.b"',
    'curl -sH "X: a.b"', 'curl -sSLH "X: a.b"', 'curl -H X:a.b',
    'curl -H @hdrs.txt', 'curl -e a.b', 'curl -A agent.v2',
    'curl --user-agent "Mozilla/5.0 a.b"', 'curl -u user:pass.word',
    'curl --user user:a.b', 'curl -d a.b', 'curl -d "k=a.b"',
    'curl --data-raw a.b', 'curl --data-binary @a.json', 'curl --data-urlencode q=a.b',
    'curl --json \'{"a":"b.c"}\'', 'curl -F file=@a.txt', 'curl -T a.txt',
    'curl -o out.txt', 'curl -oout.txt', 'curl -b a.b=c', 'curl -c jar.txt',
    'curl -w "%{http_code} a.b"', 'curl --max-time 1.5',
    'curl --retry 3 --retry-delay 1.5', 'curl --proxy-user u:p.w',
    'curl --cacert ca.pem', 'curl --cert c.pem --key k.pem',
    'wget -O out.txt', 'wget --header "X: a.b"', 'wget --post-data a=b.c',
    'wget --user u --password p.w', 'wget -U agent.v2', 'wget --referer a.b',
    'wget -P out.d', 'wget --body-file b.txt --method POST',
    'wget --http-user u --http-password p.w', 'wget --post-file p.txt',
    'wget --proxy-user u --proxy-password p.w',
])
@pytest.mark.parametrize('url, host', [(G, 'good.example'), (E, 'evil.example')])
def test_option_values_are_not_destinations(prefix, url, host):
    acts = actions(prefix + ' ' + url)
    assert [a.host for a in acts] == [host]
    assert [allowed(acts, p) for p in 'dab'] == ([True] * 3 if url == G else [False] * 3)


@pytest.mark.parametrize('cmd, hosts', [
    (f'curl {G} {E}', ['good.example', 'evil.example']),
    (f'wget {G} {E}', ['good.example', 'evil.example']),
    (f'curl --url {G} {E}', ['good.example', 'evil.example']),
    (f'curl --url={G}', ['good.example']),
    (f'curl --resolve evil.example:443:127.0.0.1 {G}', ['good.example']),
    (f'curl --connect-to evil.example:443:other.example:443 {G}', ['good.example']),
    (f'curl --resolve good.example:443:127.0.0.1 {E}', ['evil.example']),
    (f'curl --header=a.b {G}', ['good.example']),
    (f'curl --pass hunter2.x {G}', ['good.example', 'hunter2.x']),
    (f'curl --proxy-header http://decoy.example {G}', ['decoy.example', 'good.example']),
    (f'curl --interface eth0.1 {G}', ['good.example', 'eth0.1']),
    (f'wget --ftp-password hunter2.x ftp://good.example/x', ['good.example', 'hunter2.x']),
    ('curl evil.example/x', ['evil.example']),
    (f'curl {G} {G}', ['good.example']),
    (f'curl {G} https://other.example/x', ['good.example', 'other.example']),
    ('curl -d a.b', [None]), ('curl -o x.y', [None]),
    ('curl -H "X: a.b"', [None]),
    (f'curl -- -H {E}', ['evil.example', None]),
    ('curl -- "-oout.example"', [None]),
])
def test_retained_k1_to_k4(cmd, hosts):
    acts = actions(cmd)
    assert [a.host for a in acts] == hosts
    for p in 'dab':
        expected = (None not in hosts and 'evil.example' not in hosts if p == 'd'
                    else set(hosts) == {'good.example'})
        assert allowed(acts, p) == expected


@pytest.mark.parametrize('prefix', [
    'curl -K cfg.txt', 'curl -Kcfg.txt', 'curl --config cfg.txt', 'curl --config=cfg.txt',
    'wget -i urls.txt', 'wget -iurls.txt', 'wget --input-file urls.txt',
    'wget --input-file=urls.txt', 'wget -B http://good.example/ -i urls.txt',
])
@pytest.mark.parametrize('suffix', ['', ' ' + G, ' ' + E])
def test_unresolved_destination_files_hold(prefix, suffix):
    acts = actions(prefix + suffix)
    assert [a.host for a in acts] == ([suffix.split('//')[1].split('/')[0]] if suffix else []) + [None]
    assert not any(allowed(acts, p) for p in 'dab')


@pytest.mark.parametrize('option', [
    '-x', '--proxy', '--proxy1.0', '--preproxy', '--socks4', '--socks4a', '--socks5', '--socks5-hostname',
    'wget-http', 'wget-https', 'wget-ftp',
])
@pytest.mark.parametrize('proxy, host', [
    ('http://user:pw@proxy.example:8080', 'proxy.example'),
    ('evil.example:80', 'evil.example'), ('good.example:80', 'good.example'), ('', None),
])
@pytest.mark.parametrize('form', ['separate', 'attached'])
def test_proxy_destinations_judged_or_held(option, proxy, host, form):
    if option.startswith('wget-'):
        value = option[5:] + '_proxy=' + proxy
        flag = '-e ' if form == 'separate' else '-e'
        fetched = {'http': 'http://good.example/x', 'https': G, 'ftp': 'ftp://good.example/x'}[option[5:]]
        cmd = f'wget -e use_proxy=yes {flag}"{value}" {fetched}'
    else:
        flag = option + (' ' if form == 'separate' else '' if option == '-x' else '=')
        cmd = f'curl {flag}"{proxy}" {G}'
    acts = actions(cmd)
    assert [a.host for a in acts] == (['good.example'] if host == 'good.example' else ['good.example', host])
    assert [allowed(acts, p) for p in 'dab'] == ([False] * 3 if host in (None, 'evil.example')
                                                             else [True, host == 'good.example', host == 'good.example'])
    assert all(a.chip_host in (None, 'good.example') for a in acts)
    assert all('pw' not in (a.chip_host or '') for a in acts)


@pytest.mark.parametrize('cluster', ['-zH', '-szH', '-?H'])
def test_unknown_short_cluster_stops_and_holds(cluster):
    acts = actions(f'curl {cluster} {E} {G}')
    assert [a.host for a in acts] == ['evil.example', 'good.example', None]
    assert not any(allowed(acts, p) for p in 'dab')
    good = actions(f'curl {cluster} {G}')
    assert [a.host for a in good] == ['good.example', None]
    assert not any(allowed(good, p) for p in 'dab')


def test_known_short_cluster_control():
    acts = actions(f'curl -sSLH "X: a.b" {G}')
    assert [a.host for a in acts] == ['good.example']
    assert all(allowed(acts, p) for p in 'dab')


@pytest.mark.parametrize('word', ['localhost:8080', 'k=a.b', '"X: a.b"', 'user@a.b',
                                  '"https://[bad"', '"https://"'])
@pytest.mark.parametrize('suffix', ['', ' ' + G])
def test_unclassified_positional_destination_holds(word, suffix):
    acts = actions('curl ' + word + suffix)
    assert [a.host for a in acts] == (['good.example'] if suffix else []) + [None]
    assert not any(allowed(acts, p) for p in 'dab')


def test_class_and_chip_stay_separate():
    acts = actions(f'curl --pass hunter2.x {G}')
    assert [a.chip_host for a in acts] == ['good.example', None]
    assert [a.action_class for a in actions(f'curl -d a.b {G} {E}')] == ['external_comm'] * 2
    assert [a.action_class for a in actions(f'curl {G} {E}')] == ['web'] * 2

@pytest.mark.parametrize('proxy', ['http://[bad', 'proxy.example:bad', '"bad proxy"'])
def test_malformed_proxy_retains_uncertainty(proxy):
    for cmd in (f'curl --proxy {proxy} {G}', f'wget -e http_proxy={proxy} {G}'):
        acts = actions(cmd)
        assert [a.host for a in acts] == ['good.example', None]
        assert not any(allowed(acts, p) for p in 'dab')


def test_generated_option_values_cannot_hide_an_explicit_destination():
    import json
    import random
    import shlex
    from tools import fuzz_p20

    rnd = random.Random(143)
    for value in fuzz_p20.WEIRD:
        for candidate in (value, json.dumps(fuzz_p20.mutate(rnd, value))):
            cmd = f'curl -H {shlex.quote(candidate)} {E} {G}'
            acts, unknown = canonical.canonicalise('Bash', cmd, {'workdir': '.'})
            assert fuzz_p20.conservative('Bash', cmd, acts, unknown) is None
            if not unknown:
                assert [a.host for a in acts] == ['evil.example', 'good.example']
                assert not any(allowed(acts, p) for p in 'dab')

@pytest.mark.parametrize('cmd', [
    'curl --proxy good.example:80', 'curl --socks5 good.example:80',
    'wget -e http_proxy=good.example:80',
])
def test_proxy_without_fetch_url_retains_unknown_destination(cmd):
    acts = actions(cmd)
    assert [a.host for a in acts] == ['good.example', None]
    assert not any(allowed(acts, p) for p in 'dab')


@pytest.mark.parametrize('cmd', [
    f'curl {E} {G}', f'wget {E} {G}', f'curl -s -- {E} {G}',
    f'curl -H "Referer: {G}" {E}',
])
def test_action_only_changes_still_judge_each_destination(cmd):
    acts = actions(cmd)
    expected = ['evil.example'] if '-H ' in cmd else ['evil.example', 'good.example']
    assert [a.host for a in acts] == expected
    assert not any(allowed(acts, p) for p in 'dab')

@pytest.mark.parametrize('cmd', [
    'curl --config', 'curl -K', 'wget --input-file', 'wget -i',
    'curl --proxy', 'curl --url', 'curl -H',
])
def test_missing_option_value_is_unknown(cmd):
    acts = actions(cmd)
    assert [a.host for a in acts] == [None]
    assert not any(allowed(acts, p) for p in 'dab')


def test_destination_files_are_never_opened(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('classifier must not read destination files')

    got = []
    with monkeypatch.context() as m:        # only while classifying: pytest itself opens files in teardown
        m.setattr('builtins.open', forbidden)
        for cmd in (f'curl --config cfg.txt {G}', f'wget -i urls.txt {G}'):
            got.append([a.host for a in actions(cmd)])
    assert got == [['good.example', None]] * 2

@pytest.mark.parametrize('setting', ['use_proxy=yes', 'use_proxy=on', 'http_proxy=', 'unknown_setting=x'])
def test_wget_unresolved_proxy_setting_holds(setting):
    acts = actions(f'wget -e {setting} {G}')
    assert [a.host for a in acts] == ['good.example', None]
    assert not any(allowed(acts, p) for p in 'dab')


@pytest.mark.parametrize('cmd', [
    'curl https://evil.example./x', 'wget https://evil.example./x',
    'curl --proxy evil.example.:8080 https://good.example/x',
])
def test_a_root_dot_is_not_a_different_host(cmd):
    acts = actions(cmd)
    assert 'evil.example' in [a.host for a in acts] and 'evil.example.' not in [a.host for a in acts]
    assert not any(allowed(acts, p) for p in 'dab')


@pytest.mark.parametrize('cmd', [
    'curl https://good.example:bad/x', 'curl https://good.example:99999/x',
    'curl good.example:99999/x', 'wget https://good.example:0x50/x',
])
def test_a_port_that_is_not_one_leaves_the_destination_unresolved(cmd):
    acts = actions(cmd)
    assert [a.host for a in acts] == [None]
    assert not any(allowed(acts, p) for p in 'dab')


@pytest.mark.parametrize('cmd, hosts', [
    ('wget --input=urls.txt ' + G, ['good.example', None]),
    ('wget --input urls.txt ' + G, ['good.example', 'urls.txt', None]),
    ('wget --input-fi=urls.txt ' + G, ['good.example', None]),
    ('curl --conf=cfg.txt ' + G, ['good.example', None]),
    ('curl --pass=hunter2.x ' + G, ['good.example', None]),
    ('wget --config good.example ' + G, ['good.example', None]),
    ('wget --conf=cfg.txt ' + G, ['good.example', None]),
])
def test_an_attached_or_abbreviated_option_value_keeps_the_destination_unresolved(cmd, hosts):
    acts = actions(cmd)
    assert [a.host for a in acts] == hosts
    assert not any(allowed(acts, p) for p in 'dab')


@pytest.mark.parametrize('cmd, hosts', [
    ('curl http://[0:0:0:0:0:0:0:1]/x', ['::1']),
    ('curl "http://[0000:0000:0000:0000:0000:0000:0000:0001]/x"', ['::1']),
    ('curl "http://[::ffff:127.0.0.1]/x"', [None]),
    ('curl https://bad..example/x ' + G, ['good.example', None]),
    ('curl https://good.example../x', [None]),
    ('curl https://good.example../x ' + G, ['good.example', None]),
    ("curl 'http://[fe80::1%25eth0]/x'", [None]),
    ("curl 'http://[fe80::1%eth0]/x'", [None]),
    ("curl 'http://[::1%25lo]/x'", [None]),
    ('curl https://-bad.example/x', [None]),
    ('curl https://bad-.example/x', [None]),
    ('curl https://' + 'a' * 64 + '.example/x', [None]),
])
def test_an_address_has_one_spelling_and_a_name_must_be_a_valid_dns_name(cmd, hosts):
    acts = actions(cmd)
    assert [a.host for a in acts] == hosts
    assert not any(allowed(acts, p) for p in 'dab' if hosts == [None] or None in hosts)


def test_a_deny_on_the_loopback_address_meets_every_spelling():
    for cmd in ('curl http://[0:0:0:0:0:0:0:1]/x', 'curl http://[::1]/x'):
        rs = [rules.rule(id='b', scope_level='USER', scope_ref='u', action_class='web', decision='ALLOW'),
              rules.rule(id='d', scope_level='MISSION', scope_ref='m', action_class='web', decision='DENY',
                         match={'host_glob': '::1'})]
        r = engine.evaluate_item(actions(cmd)[0], {'stage': 'action', 'chain': {'USER': 'u', 'MISSION': 'm'}, 'rules': rs, 'profiles': {'USER': None}})
        assert r['decision'] == 'DENY'


@pytest.mark.parametrize('cmd', ["curl 'http://[::1%25lo]/x'", "curl 'http://[::1%lo]/x'"])
def test_a_scoped_loopback_is_never_allowed_past_a_deny_on_the_address(cmd):
    rs = [rules.rule(id='b', scope_level='USER', scope_ref='u', action_class='web', decision='ALLOW'),
          rules.rule(id='d', scope_level='MISSION', scope_ref='m', action_class='web', decision='DENY',
                     match={'host_glob': '::1'})]
    for act in actions(cmd):
        r = engine.evaluate_item(act, {'stage': 'action', 'chain': {'USER': 'u', 'MISSION': 'm'}, 'rules': rs, 'profiles': {'USER': None}})
        assert r['decision'] != 'ALLOW'


@pytest.mark.parametrize('cmd, held', [
    ('wget -e use_proxy=yes -e ftp_proxy=good.example:80 ' + G, True),
    ('wget -e use_proxy=yes -e http_proxy=good.example:80 ' + G, True),
    ('wget -e use_proxy=yes -e https_proxy=good.example:80 ' + G, False),
    ('wget -e use_proxy=yes -e http_proxy=good.example:80 http://good.example/x', False),
])
def test_a_named_proxy_resolves_only_its_own_protocol(cmd, held):
    acts = actions(cmd)
    assert ('None' in [str(a.host) for a in acts]) == held
    assert [allowed(acts, p) for p in 'dab'] == ([False] * 3 if held else [True] * 3)


@pytest.mark.parametrize('cmd', [
    "curl 'https://{evil.example,good.example}/x'", 'curl https://evil%2eexample/x',
    'curl https://\uff45vil.example/x', 'curl http://2852039166/x', 'curl http://0xa9fea9fe/x',
    'curl http://0251.0376.0251.0376/x', "wget 'https://evil.example;@good.example/x'",
    "curl 'https://evil.example\\@good.example/x'",
])
def test_a_host_spelled_so_the_fetcher_reads_it_differently_is_unresolved(cmd):
    acts = actions(cmd)
    assert [a.host for a in acts] == [None]
    assert not any(allowed(acts, p) for p in 'dab')


def test_a_plain_dotted_quad_and_an_ipv6_literal_are_still_judged():
    assert [a.host for a in actions('curl http://169.254.169.254/x')] == ['169.254.169.254']
    assert [a.host for a in actions('curl http://[::1]:8080/x')] == ['::1']
