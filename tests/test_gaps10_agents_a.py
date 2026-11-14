"""T-1375 · Close the test gaps in claude_sessions/agents.py authoring parse and generation (305-381: _parse_md, generate_agent_ai).

Exact source slice: ``claude_sessions/agents.py`` lines 305-381 at tip ``73ad7a90``
(re-located at ``3885bc1d``). No source file is edited; no new dependency.

Ten candidate branches, ranked denial/fail-closed first, then boundaries, then
error paths. Selected probes and the source branch each test catches:

 1. agents.py:338-340  empty / whitespace model output -> refused, write not called
 2. agents.py:330-332  blank or missing name refused before the model is called
 3. agents.py:310-311  _parse_md, no closing fence -> body is the whole text
 4. agents.py:312-315  value keeps everything after the first colon
 5. agents.py:313      frontmatter line without a colon is ignored, block continues
 6. agents.py:309-311  bare "---\\n---" -> meta {} and body ''
 7. agents.py:333-337  model gets cwd None for an empty project, timeout 180, crumbs, label
 8. agents.py:334      empty role falls back to the name
 9. agents.py:341      success hands output and arguments to write_agent_raw and returns its dict
10. agents.py:330      name is stripped before use

The model seam (memory._claude_stdin, memory.why_failed) and write_agent_raw are
faked; no model, subprocess or user home is touched.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import agents, memory


@pytest.fixture
def model(monkeypatch):
    calls = []

    def fake_stdin(prompt, cwd, timeout=None, crumbs=None, label=None, **kw):
        calls.append({'prompt': prompt, 'cwd': cwd, 'timeout': timeout,
                      'crumbs': crumbs, 'label': label})
        return fake_stdin.output

    fake_stdin.output = '---\nname: x\n---\nbody\n'
    monkeypatch.setattr(memory, '_claude_stdin', fake_stdin)
    monkeypatch.setattr(memory, 'why_failed', lambda default='': 'why:' + default)
    return fake_stdin, calls


@pytest.fixture
def writes(monkeypatch, tmp_path):
    calls = []
    result = {'ok': True, 'path': str(tmp_path / 'x.md'), 'name': 'x',
              'error': '', 'warnings': []}

    def fake_write(md, name, scope='user', project_path=None, category=''):
        calls.append((md, name, scope, project_path, category))
        return result

    monkeypatch.setattr(agents, 'write_agent_raw', fake_write)
    monkeypatch.setattr(agents, 'user_agents_dir', lambda cfgdir=None: str(tmp_path / 'agents'))
    return calls, result


@pytest.mark.parametrize('out', ['', '   \n\t  '])
def test_empty_model_output_is_refused_and_nothing_is_written(model, writes, out):
    fake_stdin, _ = model
    calls, _ = writes
    fake_stdin.output = out
    got = agents.generate_agent_ai('Reviewer')
    assert got == {'ok': False, 'error': 'why:No output from Claude',
                   'path': '', 'name': 'Reviewer'}
    assert calls == []


@pytest.mark.parametrize('name', [None, '', '   '])
def test_blank_or_missing_name_is_refused_before_the_model_is_called(model, writes, name):
    _, calls_model = model
    calls_write, _ = writes
    got = agents.generate_agent_ai(name)
    assert got == {'ok': False, 'error': 'no agent name given', 'path': '', 'name': ''}
    assert calls_model == [] and calls_write == []


def test_unclosed_fence_is_not_stripped():
    text = '---\nname: x\ndescription: y\nbody without a closing fence\n'
    assert agents._parse_md(text) == ({}, text)


def test_a_value_keeps_everything_after_its_first_colon():
    meta, body = agents._parse_md('---\ndescription: a: b: c\n---\nBody\n')
    assert meta == {'description': 'a: b: c'}
    assert body == 'Body\n'


def test_a_frontmatter_line_without_a_colon_is_skipped_and_the_block_goes_on():
    meta, body = agents._parse_md('---\nname: x\njunk line\ntools: Read\n---\nBody\n')
    assert meta == {'name': 'x', 'tools': 'Read'}
    assert body == 'Body\n'


def test_bare_fence_pair_gives_empty_meta_and_empty_body():
    assert agents._parse_md('---\n---') == ({}, '')


@pytest.mark.parametrize('project, cwd', [('', None), (None, None)])
def test_an_empty_project_reaches_the_model_as_no_cwd(model, writes, project, cwd):
    _, calls = model
    agents.generate_agent_ai('Reviewer', project_path=project)
    assert calls[0]['cwd'] is cwd


def test_the_model_call_carries_the_project_timeout_crumbs_and_label(model, writes, tmp_path):
    _, calls = model
    proj = str(tmp_path / 'proj')
    agents.generate_agent_ai('Reviewer', project_path=proj)
    call = calls[0]
    assert call['cwd'] == proj
    assert call['timeout'] == 180
    assert call['crumbs'] == ('ARCHEUS', 'AGENTS', 'Reviewer')
    assert 'Reviewer' in call['label']


def test_an_empty_role_falls_back_to_the_name(model, writes, monkeypatch):
    seen = []
    monkeypatch.setattr(agents, 'build_ai_prompt',
                        lambda name, role, project_path=None: seen.append((name, role)) or 'P')
    agents.generate_agent_ai('Reviewer', role='')
    assert seen == [('Reviewer', 'Reviewer')]


def test_success_hands_the_output_to_write_agent_raw_and_returns_its_dict(model, writes):
    fake_stdin, _ = model
    calls, result = writes
    fake_stdin.output = '---\nname: x\n---\nbody\n'
    got = agents.generate_agent_ai('Reviewer', role='r', scope='project',
                                   project_path='/p', category='Tools')
    assert got is result
    assert calls == [('---\nname: x\n---\nbody\n', 'Reviewer', 'project', '/p', 'Tools')]


def test_the_name_is_stripped_before_it_is_used(model, writes):
    _, calls_model = model
    calls_write, _ = writes
    agents.generate_agent_ai('  Reviewer  ')
    assert calls_model[0]['crumbs'] == ('ARCHEUS', 'AGENTS', 'Reviewer')
    assert calls_write[0][1] == 'Reviewer'
