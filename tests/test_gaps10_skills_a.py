"""T-1372: claude_sessions/skills.py lines 103-165 (parse_skill, write_skill, list_skills).

Selected branches, denial and fail-closed first:
  113-114  unclosed frontmatter: parse_skill returns ({}, whole text)
  108-111  unreadable SKILL.md (a directory at that path): ({}, '')
  125-127  folded block `description: >-` joins its continuation lines
  128-134  a non-indented, non-key line ends the key; the indented line after it is dropped
  132      literal and folded markers '|' and '|-' read as ''
  140-142  write_skill order name, description, allowed-tools, then extra keys; falsy values omitted
  144-150  write_skill returns False when skill_dir is a regular file, nothing else written
  143      write then parse round-trips meta and body; body keeps one trailing newline
  119-127  a blank line inside a folded block is continuation, not a stray key
  156-162  list_skills: None or missing dir gives [], subdir without SKILL.md skipped,
           name falls back to the directory name, output sorted by directory name
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import skills


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(data)


def _skill(root, name, text):
    d = os.path.join(root, name)
    _write_bytes(os.path.join(d, 'SKILL.md'), text.encode('utf-8'))
    return d


def test_unclosed_frontmatter_is_not_parsed_into_metadata(tmp_path):
    text = '---\nname: broken\ndescription: never closed\n\nbody line\n'
    d = _skill(str(tmp_path), 'x', text)

    assert skills.parse_skill(d) == ({}, text)


def test_unreadable_skill_md_gives_empty_meta_and_body(tmp_path):
    d = tmp_path / 'x'
    os.makedirs(os.path.join(str(d), 'SKILL.md'))

    assert skills.parse_skill(str(d)) == ({}, '')


def test_folded_block_joins_its_continuation_lines(tmp_path):
    text = '---\nname: f\ndescription: >-\n  first part\n  second part\n---\n\nbody\n'
    d = _skill(str(tmp_path), 'f', text)

    meta, body = skills.parse_skill(d)

    assert meta == {'name': 'f', 'description': 'first part second part'}
    assert body == 'body\n'


def test_non_indented_non_key_line_ends_the_key_and_its_indented_follower_is_dropped(tmp_path):
    text = '---\ndescription: keep me\nstray words\n  indented words\n---\n\nbody\n'
    d = _skill(str(tmp_path), 's', text)

    meta, _ = skills.parse_skill(d)

    assert meta == {'description': 'keep me'}


def test_literal_and_folded_markers_read_as_empty_values(tmp_path):
    text = '---\nname: a\ndescription: |\nallowed-tools: >\n---\n\nb\n'
    d = _skill(str(tmp_path), 'm', text)

    meta, _ = skills.parse_skill(d)

    assert meta == {'name': 'a', 'description': '', 'allowed-tools': ''}


def test_write_skill_orders_known_keys_first_and_omits_falsy_values(tmp_path):
    d = str(tmp_path / 'w')

    assert skills.write_skill(d, {'extra': 'x', 'description': '',
                                  'allowed-tools': 'Read', 'name': 'w'}, 'body') is True

    with open(os.path.join(d, 'SKILL.md'), encoding='utf-8') as fh:
        assert fh.read() == '---\nname: w\nallowed-tools: Read\nextra: x\n---\n\nbody\n'


def test_write_skill_refuses_a_regular_file_as_the_skill_dir_and_leaves_it_alone(tmp_path):
    p = tmp_path / 'plain'
    p.write_text('keep', encoding='utf-8')

    assert skills.write_skill(str(p), {'name': 'x'}, 'body') is False

    assert p.read_text(encoding='utf-8') == 'keep'
    assert not os.path.exists(os.path.join(str(p), 'SKILL.md'))


def test_write_then_parse_round_trips_meta_and_trims_body_to_one_newline(tmp_path):
    d = str(tmp_path / 'rt')
    meta = {'name': 'rt', 'description': 'a description long enough to read'}

    skills.write_skill(d, meta, 'line one\n\nline two\n\n\n')

    assert skills.parse_skill(d) == (meta, 'line one\n\nline two\n')


def test_blank_line_inside_a_folded_block_is_continuation_not_a_stray_key(tmp_path):
    text = '---\nname: b\ndescription: >-\n  first\n\n  second\n---\n\nx\n'
    d = _skill(str(tmp_path), 'b', text)

    meta, _ = skills.parse_skill(d)

    assert meta == {'name': 'b', 'description': 'first second'}


def test_list_skills_handles_none_missing_and_unlisted_dirs(tmp_path):
    root = tmp_path / 'skills'
    _skill(str(root), 'beta', '---\nname: Beta\ndescription: b\n---\n')
    _skill(str(root), 'alpha', '---\ndescription: no name here\n---\n')
    os.makedirs(str(root / 'empty'))
    (root / 'loose.md').write_text('not a skill', encoding='utf-8')

    assert skills.list_skills(None) == []
    assert skills.list_skills(str(tmp_path / 'missing')) == []
    assert skills.list_skills(str(root)) == [
        ('alpha', 'no name here', os.path.join(str(root), 'alpha')),
        ('Beta', 'b', os.path.join(str(root), 'beta')),
    ]
