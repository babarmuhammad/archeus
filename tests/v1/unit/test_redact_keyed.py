"""T-1089 (owner item 100): the keyed-secret rules of archeus/core/redact.py. A value named
as a secret is masked and its name kept; the corpus rows (tests/fixtures/persisted_secrets)
pin whole commands, these pin each rule alone. Every value is synthetic."""

import json
import time

import pytest

from archeus.core.redact import SECRET, redact, redact_json

S = 'SYNTHsecret9'


@pytest.mark.parametrize('text, kept', [
    ('PGPASSWORD=' + S, 'PGPASSWORD='), ('db_passwd=' + S, 'db_passwd='),
    ('Password: ' + S, 'Password: '),
])
def test_a_password_name(text, kept):
    assert redact(text) == kept + '[redacted]'


@pytest.mark.parametrize('text, kept', [
    ('export TOKEN=' + S, 'export TOKEN='), ('"access_token": "' + S + '"', '"access_token": "'),
    ('X-Auth-Token: ' + S, 'X-Auth-Token: '),
])
def test_a_token_name(text, kept):
    assert redact(text).startswith(kept + '[redacted]') and S not in redact(text)


@pytest.mark.parametrize('text', ['CLIENT_SECRET=' + S, 'SECRET_KEY=' + S, 'secret: ' + S])
def test_a_secret_name(text):
    assert redact(text) == text[:-len(S)] + '[redacted]'


@pytest.mark.parametrize('text', ['API_KEY=' + S, 'apikey=' + S, 'x-api-key: ' + S])
def test_an_api_key_name(text):
    assert redact(text) == text[:-len(S)] + '[redacted]'


def test_an_access_key_name():
    assert redact('ACCESS_KEY=' + S) == 'ACCESS_KEY=[redacted]'


def test_a_private_key_name():
    assert redact('private_key=' + S) == 'private_key=[redacted]'


@pytest.mark.parametrize('text', ['MYSQL_PWD=' + S, 'SMTP_PASS=' + S, 'db.pass=' + S])
def test_a_pass_or_pwd_after_a_separator(text):
    assert redact(text) == text[:-len(S)] + '[redacted]'


@pytest.mark.parametrize('text', ['export OLDPWD=/home/app', 'PWD=/home/app make', 'export BYPASS=1',
                                  'max_tokens=100000', 'export TOKENIZER_MODE=fast', 'password_hint=blue'])
def test_a_name_that_only_contains_a_secret_word_is_left_alone(text):
    assert redact(text) == text


@pytest.mark.parametrize('text, out', [
    ('docker login --password ' + S + ' r.example.com', 'docker login --password [redacted] r.example.com'),
    ('vault login --db-token ' + S, 'vault login --db-token [redacted]'),
    ('tool --api-key ' + S, 'tool --api-key [redacted]'),
    ('--secret ' + S, '--secret [redacted]'),
])
def test_a_long_flag_with_its_value_after_a_blank(text, out):
    assert redact(text) == out


@pytest.mark.parametrize('text', ['docker login --password-stdin r.example.com', 'gh auth login --with-token < t.txt',
                                  'x--password ' + S, 'tool --token-file t.txt', 'tool --password -v'])
def test_a_long_flag_that_carries_no_value_is_left_alone(text):
    assert redact(text) == text


@pytest.mark.parametrize('text', ['Authorization: Token ' + S, 'authorization: Digest ' + S,
                                  'Authorization: Bearer abc'])
def test_an_authorization_header_of_any_scheme(text):
    assert redact(text) == 'Authorization: [redacted]'.replace('Authorization', text[:13])


def test_a_cookie_header_is_masked_to_the_end_of_its_line():
    assert redact('Cookie: sid=' + S + '; theme=dark\nnext') == 'Cookie: [redacted]\nnext'


def test_a_set_cookie_header_is_masked():
    assert redact('Set-Cookie: sid=' + S + '; Path=/') == 'Set-Cookie: [redacted]'


@pytest.mark.parametrize('text', ['Authorization: none', 'cookie: off'])
def test_a_header_word_with_no_credential_is_left_alone(text):
    assert redact(text) == text


@pytest.mark.parametrize('text, out', [
    ('sshpass -p ' + S + ' ssh app@example.com', 'sshpass -p [redacted] ssh app@example.com'),
    ('az login -u app -p ' + S, 'az login -u app -p [redacted]'),
    ('docker login -u app -p ' + S + ' r.example.com', 'docker login -u app -p [redacted] r.example.com'),
])
def test_a_short_p_flag_of_a_login_command(text, out):
    assert redact(text) == out


def test_redis_cli_a_flag():
    assert redact('redis-cli -h c -a ' + S + ' ping') == 'redis-cli -h c -a [redacted] ping'


@pytest.mark.parametrize('text, out', [
    ('mysql -u app -p' + S + ' app', 'mysql -u app -p[redacted] app'),
    ('/usr/bin/mysqldump -p"' + S + '" db', '/usr/bin/mysqldump -p"[redacted]" db'),
    ('mysql -u app\t-p' + S, 'mysql -u app\t-p[redacted]'),
])
def test_a_glued_p_flag_of_a_mysql_command(text, out):
    assert redact(text) == out


@pytest.mark.parametrize('text', ['mysql -u app -p app', 'xmysql -p8080', 'docker run -p 8080:80 img',
                                  'mkdir -p out', 'ssh -p 22 h', 'mysql -u app; ls -p'])
def test_a_short_flag_of_any_other_command_is_left_alone(text):
    assert redact(text) == text


def test_aws_configure_set_with_a_blank():
    assert redact('aws configure set aws_session_token ' + S) == \
        'aws configure set aws_session_token [redacted]'


def test_echo_piped_to_password_stdin():
    assert redact('echo ' + S + ' | docker login --password-stdin r') == \
        'echo [redacted] | docker login --password-stdin r'
    assert redact('echo hello | grep h') == 'echo hello | grep h'


def test_a_value_starting_with_a_dash_is_left_to_the_pem_rule():
    key = '-----BEGIN RSA PRIVATE KEY-----\nSYNTHBODY0123\n-----END RSA PRIVATE KEY-----'
    assert 'SYNTHBODY0123' not in redact('secret: ' + key)
    assert 'SYNTHBODY0123' not in redact_json({'private_key': key})


def test_redacted_text_matches_no_pattern_again():
    for text in ['PGPASSWORD=' + S, 'X-Auth-Token: ' + S, '--password ' + S]:
        once = redact(text)
        assert not SECRET.search(once) and redact(once) == once


def test_a_json_field_named_as_a_secret_is_masked_and_its_name_kept():
    out = redact_json({'password': S, 'user': 'app', 'headers': {'Cookie': 'sid=' + S}})
    assert out == {'password': '[redacted]', 'user': 'app', 'headers': {'Cookie': '[redacted]'}}
    assert S not in redact(json.dumps({'api_key': S}))


@pytest.mark.parametrize('text', ['docker run -u app:app img', 'rsync -u build:/out/ ./out/',
                                  'rsync -u h:~/x .'])
def test_curl_user_rule_leaves_uid_gid_and_paths(text):
    assert redact(text) == text


def test_curl_user_rule_still_masks_a_password():
    assert redact('curl -u admin:' + S + ' https://x') == 'curl [redacted] https://x'


_N = 120_000
_WORST = ['password' * (_N // 8), 'password=' + ' ' * _N, 'token:' + ' ' * _N + 'x', 'Pa' * (_N // 2),
          '_pwd' * (_N // 4), ' --' + 'a' * _N, ' --token' + ' ' * _N, (' --' + 'tokenx') * (_N // 9),
          'cookie:' + ' ' * _N, 'authorization: a' + ' ' * _N + '"', 'sshpass ' * (_N // 8),
          'mysql -' * (_N // 7), 'redis-cli ' + 'x ' * _N, 'echo x ' * (_N // 7) + '|',
          'aws configure set ' + 'secret' * (_N // 6), '-u a:' + 'a' * _N, ' -u ab:ab' * (_N // 9)]


@pytest.mark.parametrize('i', range(len(_WORST)))
def test_every_keyed_rule_is_linear_on_its_worst_input(i):
    t = time.perf_counter()
    redact(_WORST[i])
    assert time.perf_counter() - t < 0.5, _WORST[i][:40]


def test_a_quoted_basic_header_is_still_masked_whole_by_its_own_rule():
    assert redact('{"Authorization": "Basic dXNlcjpwYXNzd29yZA=="}') == '{"[redacted]"}'
