import pytest

from archeus.core.verification import evidence


def _raw(*lines):
    return '\n'.join(lines) + '\n'


def _diff(path, *hunks, deleted=False, new=False):
    head = ['diff --git a/%s b/%s' % (path, path)]
    head.append('deleted file mode 100644' if deleted else 'new file mode 100644' if new
                else 'index 1111111..2222222 100644')
    head += ['--- /dev/null' if new else '--- a/%s' % path,
             '+++ /dev/null' if deleted else '+++ b/%s' % path]
    body = []
    for removed, added in hunks:
        body.append('@@ -1,%d +1,%d @@' % (len(removed), len(added)))
        body += ['-' + r for r in removed] + ['+' + a for a in added]
    return _raw(*head, *body)


@pytest.fixture(autouse=True)
def _no_privileged_side_effects(monkeypatch):
    calls = []

    def blocked(name):
        def _blocked(*args, **kw):
            calls.append(name)
            raise AssertionError('the diff parser touched a privileged seam: %s' % name)
        return _blocked

    for module, name in (('subprocess', 'Popen'), ('subprocess', 'run'), ('subprocess', 'call'),
                         ('os', 'system'), ('os', 'execv'), ('os', 'spawnv')):
        monkeypatch.setattr('%s.%s' % (module, name), blocked('%s.%s' % (module, name)))
    yield
    assert calls == []


def test_diff_text_before_the_first_diff_git_header_claims_no_file_and_no_deletion():
    d = _raw(
        'deleted file mode 100644',
        '--- a/tests/test_ghost.py', '+++ b/tests/test_ghost.py',
        '@@ -1,1 +0,0 @@',
        '-def test_ghost():', '-    assert secret()',
        'diff --git a/tests/test_a.py b/tests/test_a.py',
        'index 1111111..2222222 100644',
        '--- a/tests/test_a.py', '+++ b/tests/test_a.py',
        '@@ -1,1 +0,0 @@',
        '-def test_a():')
    files = evidence._parse_diff(d)
    assert [f['path'] for f in files] == ['tests/test_a.py']
    (only,) = files
    assert only['deleted'] is False
    assert only['hunks'] == [(['def test_a():'], [])]
    assert only['skipped'] == 0
    assert evidence.weakening(d) == ['test removed: tests/test_a.py::test_a']


def test_a_deleted_file_mode_line_inside_a_hunk_is_data_and_not_a_deletion():
    d = _raw(
        'diff --git a/tests/test_a.py b/tests/test_a.py',
        'index 1111111..2222222 100644',
        '--- a/tests/test_a.py', '+++ b/tests/test_a.py',
        '@@ -1,3 +1,0 @@',
        'deleted file mode 100644',
        '+++ /dev/null',
        '--- a/tests/test_a.py',
        '-    assert one()', '-    assert two()')
    (f,) = evidence._parse_diff(d)
    assert f['deleted'] is False
    assert f['path'] == 'tests/test_a.py'
    assert f['hunks'] == [(['-- a/tests/test_a.py', '    assert one()', '    assert two()'],
                           ['++ /dev/null'])]
    assert evidence.weakening(d) == ['assertions removed: tests/test_a.py (2 net)']


def test_a_diff_that_carries_no_a_or_b_prefix_claims_nothing_about_the_test_it_names():
    assert evidence._path('--- /dev/null') is None
    assert evidence._path('+++ /dev/null') is None
    assert evidence._path('--- tests/test_a.py') is None
    assert evidence._path('+++ b/tests/test_a.py') == 'tests/test_a.py'
    d = _raw('diff --git tests/test_a.py tests/test_a.py',
             'index 1111111..2222222 100644',
             '--- tests/test_a.py', '+++ tests/test_a.py',
             '@@ -1,2 +0,0 @@',
             '-def test_a():', '-    assert one()')
    (f,) = evidence._parse_diff(d)
    assert f == {'path': None, 'deleted': False, 'skipped': 0, 'hunks': [([], [])]}
    assert evidence.weakening(d) == []


def test_a_rename_like_diff_git_header_is_read_from_its_first_half_only():
    gone = _raw('diff --git a/tests/test_a.py b/src/helper_a.py',
                'deleted file mode 100644',
                'Binary files a/x and /dev/null differ')
    (f,) = evidence._parse_diff(gone)
    assert f['path'] == 'tests/test_a.py'
    assert f['deleted'] is True and f['hunks'] == []
    assert evidence.weakening(gone) == ['test file deleted: tests/test_a.py']
    made = _raw('diff --git a/src/helper.py b/tests/test_new.py',
                'new file mode 100644',
                'Binary files /dev/null and b/x differ')
    (g,) = evidence._parse_diff(made)
    assert g['path'] == 'src/helper.py b'
    assert g['deleted'] is False
    assert evidence.weakening(made) == []


def test_a_hunk_line_of_exactly_the_maximum_length_is_read_and_one_more_is_only_counted():
    body = '    assert ' + 'x' * (evidence._LINE_MAX - 1 - len('    assert '))
    assert len('-' + body) == evidence._LINE_MAX
    at_cap = _diff('tests/test_a.py', ([body], []))
    (kept,) = evidence._parse_diff(at_cap)
    assert kept['hunks'] == [([body], [])] and kept['skipped'] == 0
    assert evidence.weakening(at_cap) == ['assertions removed: tests/test_a.py (1 net)']
    over = _diff('tests/test_a.py', ([body + 'x'], []))
    assert len('-' + body + 'x') == evidence._LINE_MAX + 1
    (cut,) = evidence._parse_diff(over)
    assert cut['hunks'] == [([], [])] and cut['skipped'] == 1
    assert evidence.weakening(over) == ['1 changed line(s) too long to inspect: '
                                        'tests/test_a.py']


def test_a_path_of_exactly_the_byte_cap_is_whole_and_one_byte_more_is_cut_at_a_character():
    exact = 'tests/' + 'é' * 184 + 'x' + 'test_a.py'
    assert len(exact.encode('utf-8')) == evidence._PATH_BYTES
    assert evidence._render_path(exact) == exact
    one_more = exact + 'y'
    assert len(one_more.encode('utf-8')) == evidence._PATH_BYTES + 1
    cut = evidence._render_path(one_more)
    assert cut != one_more and cut.startswith('tests/') and cut.endswith(']')
    prefix, omitted = cut.split('... [path cut: ')
    assert int(omitted.split()[0]) == len(one_more.encode('utf-8')) - len(prefix.encode('utf-8'))
    whole = 'tests/' + 'a' * (evidence._PATH_BYTES - 64 - len('tests/') - 1)
    straddles = whole + 'é' * 30 + 'test_a.py'
    assert len(whole.encode('utf-8')) == evidence._PATH_BYTES - 64 - 1
    assert len(straddles.encode('utf-8')) > evidence._PATH_BYTES
    kept = evidence._render_path(straddles)
    assert '\ufffd' not in kept and not kept.startswith(whole + 'é')
    assert kept.startswith(whole)
    head, count = kept.split('... [path cut: ')
    assert head == whole
    assert int(count.split()[0]) == len(straddles.encode('utf-8')) - len(whole.encode('utf-8'))
    (finding,) = evidence.weakening(_diff(straddles, (['def test_a():'], [])))
    assert finding == 'test removed: %s::test_a' % kept


def test_a_header_name_is_read_up_to_the_tab_and_its_timestamp_is_dropped():
    stamp = '2026-11-13 10:00:00.000000000 +0000'
    assert evidence._path('--- a/tests/test_a.py\t' + stamp) == 'tests/test_a.py'
    assert evidence._path('+++ "b/tests/a\\tb.py"\t' + stamp) == 'tests/a\tb.py'
    d = _raw('diff --git a/tests/test_a.py b/tests/test_a.py',
             'index 1111111..2222222 100644',
             '--- a/tests/test_a.py\t' + stamp, '+++ b/tests/test_a.py\t' + stamp,
             '@@ -1,1 +0,0 @@',
             '-    assert one()')
    (f,) = evidence._parse_diff(d)
    assert f['path'] == 'tests/test_a.py'
    assert evidence.weakening(d) == ['assertions removed: tests/test_a.py (1 net)']
    quoted = _raw('diff --git "a/tests/a\\tb.py" "b/tests/a\\tb.py"',
                  'index 1111111..2222222 100644',
                  '--- "a/tests/a\\tb.py"\t' + stamp, '+++ "b/tests/a\\tb.py"\t' + stamp,
                  '@@ -1,1 +0,0 @@',
                  '-    assert one()')
    (g,) = evidence._parse_diff(quoted)
    assert g['path'] == 'tests/a\tb.py'
    assert evidence.weakening(quoted) == ['assertions removed: tests/a\tb.py (1 net)']


def test_a_quoted_header_of_octal_escapes_is_read_as_the_utf8_name_it_stands_for():
    assert evidence._path('--- "a/tests/test_\\303\\251.py"') == 'tests/test_é.py'
    assert evidence._path('+++ "b/tests/test_\\303\\251.py"') == 'tests/test_é.py'
    d = _raw('diff --git "a/tests/test_\\303\\251.py" "b/tests/test_\\303\\251.py"',
             'index 1111111..2222222 100644',
             '--- "a/tests/test_\\303\\251.py"', '+++ "b/tests/test_\\303\\251.py"',
             '@@ -1,2 +0,0 @@',
             '-def test_é():', '-    assert one()')
    (f,) = evidence._parse_diff(d)
    assert f['path'] == 'tests/test_é.py'
    assert f['hunks'] == [(['def test_é():', '    assert one()'], [])]
    assert evidence.weakening(d) == ['test removed: tests/test_é.py::test_é',
                                     'assertions removed: tests/test_é.py (1 net)']


def test_a_non_test_file_keeps_no_line_and_counts_nothing_but_still_exists():
    too_long = 'x' * (evidence._LINE_MAX + 1)
    other_long = 'y' * (evidence._LINE_MAX + 500)
    d = (_diff('src/app.js', ([too_long, 'const a = 1'], ['const b = 2']))
         + _diff('tests/test_a.py', ([other_long, '    assert one()'], [])))
    app, test = evidence._parse_diff(d)
    assert app == {'path': 'src/app.js', 'deleted': False, 'skipped': 0, 'hunks': [([], [])]}
    assert test['path'] == 'tests/test_a.py'
    assert test['hunks'] == [(['    assert one()'], [])] and test['skipped'] == 1
    assert evidence.weakening(d) == ['1 changed line(s) too long to inspect: tests/test_a.py',
                                     'assertions removed: tests/test_a.py (1 net)']


def test_a_quoted_header_that_is_not_valid_utf8_keeps_a_replacement_name_not_a_crash():
    broken = 'tests/test_\ufffd\ufffd.py'
    assert evidence._path('--- "a/tests/test_\\255\\255.py"') == broken
    d = _raw('diff --git "a/tests/test_\\255\\255.py" "b/tests/test_\\255\\255.py"',
             'index 1111111..2222222 100644',
             '--- "a/tests/test_\\255\\255.py"', '+++ "b/tests/test_\\255\\255.py"',
             '@@ -1,1 +0,0 @@',
             '-    assert one()')
    (f,) = evidence._parse_diff(d)
    assert f['path'] == broken
    assert f['hunks'] == [(['    assert one()'], [])] and f['skipped'] == 0
    assert evidence.weakening(d) == ['assertions removed: %s (1 net)' % broken]
