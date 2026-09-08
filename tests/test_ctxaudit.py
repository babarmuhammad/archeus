"""Step 0 + F1 — CLAUDE.md caps/prune and the context-weight audit."""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, ESC, ENTER, RIGHT, make_jsonl, run_flow, typed

from claude_sessions import claude_md, ctxaudit, memory
from claude_sessions.config import (_AUTOGEN_START, _AUTOGEN_END,
                                    _SESSIONS_START, _SESSIONS_END,
                                    _MEMORY_START, _MEMORY_END)


def _many_sessions(sb, folder, n):
    for i in range(n):
        sid = f'bbbb{i:04d}-0000-0000-0000-00000000{i:04d}'
        make_jsonl(os.path.join(folder, f'{sid}.jsonl'),
                   preview=f'topic number {i}')
        t = time.time() - (n - i) * 60          # i=n-1 newest
        os.utime(os.path.join(folder, f'{sid}.jsonl'), (t, t))


# ── Step 0: caps ─────────────────────────────────────────────

def test_sessions_block_capped_to_setting(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    _many_sessions(sb, folder, 15)
    block = claude_md._build_sessions_block(folder, {})
    lines = [l for l in block.splitlines() if l.startswith('- ')]
    assert len(lines) == 10                     # default cap
    assert 'topic number 14' in block           # newest kept
    assert 'topic number 0' not in block        # oldest dropped

    with open(sb.settings, 'w', encoding='utf-8') as f:
        json.dump({'claude_md_sessions_cap': 3}, f)
    block = claude_md._build_sessions_block(folder, {})
    assert len([l for l in block.splitlines() if l.startswith('- ')]) == 3

    block = claude_md._build_sessions_block(folder, {}, cap=0)   # 0 = unlimited
    assert len([l for l in block.splitlines() if l.startswith('- ')]) == 15


def test_prune_claude_md_shrinks_and_preserves_manual_and_memory(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    _many_sessions(sb, folder, 12)
    old_sessions = '\n'.join(f'- **old{i}** (2 msgs): stale topic {i}' for i in range(30))
    manual = "# alpha\n\n## Project context\nHand-written notes stay.\n\n"
    mem_block = f"{_MEMORY_START}\nsemantic digest line\n{_MEMORY_END}\n"
    md = (manual
          + f"{_AUTOGEN_START}\nold autogen\n{_AUTOGEN_END}\n"
          + f"{_SESSIONS_START}\n## Session topics\n{old_sessions}\n{_SESSIONS_END}\n"
          + mem_block)
    md_path = os.path.join(actual, 'CLAUDE.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)

    res = claude_md.prune_claude_md(actual, folder)
    assert res is not None
    old_tok, new_tok = res
    assert new_tok < old_tok
    out = open(md_path, encoding='utf-8').read()
    assert 'Hand-written notes stay.' in out
    assert f"{_MEMORY_START}\nsemantic digest line\n{_MEMORY_END}" in out
    lines = [l for l in out.splitlines() if l.startswith('- **')]
    assert len(lines) == 10                     # capped
    assert 'stale topic 29' not in out          # old accumulated entries pruned


# ── F1: audit items ──────────────────────────────────────────

def _seed_audit_project(sb):
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    _many_sessions(sb, folder, 3)
    md = ("# alpha\n\nManual notes here.\n\n"
          + f"{_AUTOGEN_START}\nrepo block " + "x " * 300 + f"\n{_AUTOGEN_END}\n"
          + f"{_SESSIONS_START}\n## Session topics\n- **s1** (2 msgs): t\n"
            f"- **s2** (2 msgs): t\n{_SESSIONS_END}\n"
          + f"{_MEMORY_START}\ndigest\n{_MEMORY_END}\n")
    with open(os.path.join(actual, 'CLAUDE.md'), 'w', encoding='utf-8') as f:
        f.write(md)
    from claude_sessions import config as config_mod
    with open(config_mod.global_claude_md, 'w', encoding='utf-8') as f:
        f.write('global conventions ' * 60)                 # > 500 tok? no, ~285
    rules = os.path.join(actual, '.claude', 'rules')
    os.makedirs(rules, exist_ok=True)
    with open(os.path.join(rules, 'lazy-rule.md'), 'w', encoding='utf-8') as f:
        f.write('---\npaths:\n  - "src/**"\n---\nrule body\n')
    with open(os.path.join(rules, 'always-rule.md'), 'w', encoding='utf-8') as f:
        f.write('always-on rule body\n')
    # claims a glob in the Cursor spelling. Claude Code does not read `globs:`,
    # so this file loads into EVERY session — the audit must not call it lazy.
    with open(os.path.join(rules, 'globs-rule.md'), 'w', encoding='utf-8') as f:
        f.write('---\nglobs: "src/**"\n---\nrule body\n')
    with open(os.path.join(folder, 'system-prompt.txt'), 'w', encoding='utf-8') as f:
        f.write('be terse\n')
    return actual, folder


def test_audit_items_labels_tokens_lazy(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, folder = _seed_audit_project(sb)
    items = ctxaudit.audit_items(actual, folder)
    by = {i['label']: i for i in items}
    assert 'CLAUDE.md · manual content' in by
    assert by['CLAUDE.md · autogen (repos/commits)']['tokens'] > 100
    assert 'CLAUDE.md · session topics (2)' in by
    assert 'CLAUDE.md · memory digest' in by
    assert 'global ~/.claude/CLAUDE.md' in by
    assert by['rule lazy-rule.md']['lazy'] is True
    assert by['rule always-rule.md']['lazy'] is False
    # `globs:` is the Cursor key. Claude Code scopes on `paths:` alone and loads
    # everything else unconditionally, so counting a globs-only file as lazy
    # understated the always-on total by its whole size — on this repo, by the
    # ~3.9k tokens of all eleven memory rules at once.
    assert by['rule globs-rule.md']['lazy'] is False
    assert 'system-prompt.txt (--system-prompt-file)' in by
    mcp_rows = [l for l in by if l.startswith('MCP servers (1)')]
    assert mcp_rows and by[mcp_rows[0]]['tokens'] == ctxaudit.MCP_TOKENS_PER_SERVER
    # lazy rules excluded from the always-on total
    assert ctxaudit.audit_total(items) == sum(
        i['tokens'] for i in items if not i['lazy'] and i['tokens'])
    assert by['rule lazy-rule.md']['tokens'] not in (None, 0)
    # compact-instructions hint present (no section in the seeded file)
    manual_warns = ' '.join(by['CLAUDE.md · manual content']['warnings'])
    assert 'Compact instructions' in manual_warns


def test_audit_warns_on_long_claude_md_and_uncapped_sessions(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    entries = '\n'.join(f'- **e{i}** (2 msgs): topic' for i in range(25))
    md = ("# alpha\n" + 'filler line\n' * 220
          + f"{_SESSIONS_START}\n## Session topics\n{entries}\n{_SESSIONS_END}\n")
    with open(os.path.join(actual, 'CLAUDE.md'), 'w', encoding='utf-8') as f:
        f.write(md)
    items = ctxaudit.audit_items(actual, folder)
    warns = ' | '.join(w for i in items for w in i['warnings'])
    assert 'compress' in warns
    assert '25 session entries' in warns


def test_audit_screen_smoke_and_prune_flow(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, folder = _seed_audit_project(sb)
    _many_sessions(sb, folder, 12)
    entries = '\n'.join(f'- **old{i}** (2 msgs): stale topic {i}' for i in range(30))
    md_path = os.path.join(actual, 'CLAUDE.md')
    md = open(md_path, encoding='utf-8').read().replace(
        '- **s1** (2 msgs): t\n- **s2** (2 msgs): t', entries)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)

    # p → confirm Yes (RIGHT, ENTER) → back on audit screen → ESC out
    _ret, cap, _ex = run_flow(monkeypatch, [*typed('p'), *RIGHT, *ENTER, *ESC],
                              ctxaudit.audit_screen, actual, folder, 'alpha')
    assert 'CONTEXT WEIGHT' in cap.plain
    assert 'total always-on' in cap.plain
    out = open(md_path, encoding='utf-8').read()
    assert 'stale topic 29' not in out           # pruned on disk
    assert len([l for l in out.splitlines() if l.startswith('- **')]) == 10


def test_append_compact_section(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    md_path = os.path.join(actual, 'CLAUDE.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"# alpha\nnotes\n{_MEMORY_START}\nd\n{_MEMORY_END}\n")
    assert ctxaudit.append_compact_section(actual) is True
    out = open(md_path, encoding='utf-8').read()
    assert '# Compact instructions' in out
    assert f"{_MEMORY_START}\nd\n{_MEMORY_END}" in out       # sentinels untouched
    assert ctxaudit.append_compact_section(actual) is False  # idempotent
    # audit hint disappears once present
    items = ctxaudit.audit_items(actual, folder)
    by = {i['label']: i for i in items}
    warns = ' '.join(by['CLAUDE.md · manual content']['warnings'])
    assert 'Compact instructions' not in warns


def test_protect_fences_a_whole_section(monkeypatch, tmp_path):
    """A heading and the prose under it are one idea; fencing half of it
    protects half of it."""
    from claude_sessions import ctxaudit
    from claude_sessions.config import _KEEP_START, _KEEP_END
    md = tmp_path / 'CLAUDE.md'
    md.write_text('# proj\n\n## Deployment\nrun the deploy script first\nthen tag\n'
                  '\n## Other\nunrelated\n', encoding='utf-8')
    assert ctxaudit.protect_section(str(md), 'deploy script') is True
    out = md.read_text(encoding='utf-8')
    assert _KEEP_START in out and _KEEP_END in out
    body = out[out.index(_KEEP_START):out.index(_KEEP_END)]
    assert '## Deployment' in body and 'then tag' in body
    assert '## Other' not in body, 'the fence stops at the next heading'
    assert ctxaudit.keep_regions(out) == 1
    # already protected → no double fence
    assert ctxaudit.protect_section(str(md), 'deploy script') is False
    assert ctxaudit.keep_regions(md.read_text(encoding='utf-8')) == 1


def test_protected_regions_are_reported_in_the_audit(monkeypatch, tmp_path):
    """You should be able to SEE what compression cannot touch before pressing
    compress, not find out afterwards."""
    from claude_sessions import ctxaudit
    from claude_sessions.config import _KEEP_START, _KEEP_END
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    with open(os.path.join(actual, 'CLAUDE.md'), 'w', encoding='utf-8') as f:
        f.write(f'# proj\n\n{_KEEP_START}\n## Keep\nsecret\n{_KEEP_END}\n\n## Rest\nx\n')
    labels = [i['label'] for i in ctxaudit.audit_items(actual, folder)]
    assert any('protected' in l for l in labels), labels


def test_the_headless_openers_still_match_the_prompts_we_send():
    """The opener list is how transcripts written before HEADLESS_MARK existed
    are recognised. It can only rot one way — a prompt gets reworded — so pin
    each opener to the source of the prompt that produces it.

    It rots the *other* way too, and this test cannot see that: a new headless
    prompt whose opener nobody adds. That cost one row (`agents.sharpen_prompt`,
    listed as a session topic under "Rewrite the `description` field…"). The
    structural answer is HEADLESS_MARK, which `memory._claude_stdin` appends to
    every prompt regardless of who wrote it — so a missing opener now only
    affects transcripts recorded before the marker existed, and ages out."""
    import inspect
    from claude_sessions import (sessions, lessons, claude_md as cmd, review,
                                 brief, agents)
    src = '\n'.join(inspect.getsource(m)
                    for m in (memory, lessons, cmd, review, brief, agents))
    for opener in sessions.HEADLESS_OPENERS:
        assert opener in src, f'no prompt starts with {opener!r} any more — update HEADLESS_OPENERS'


def test_archeus_talking_to_itself_is_not_a_session_topic(monkeypatch, tmp_path):
    """`claude -p` writes a transcript into ~/.claude/projects exactly like a
    session you had, so archeus's own calls were listed back as "session
    topics" — always-on CLAUDE.md tokens spent describing archeus extracting
    a module, distilling lessons, and compressing this very file."""
    from claude_sessions import sessions, claude_md as cmd
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')

    # one real session, one legacy headless call (no marker), one marked one
    for sid, text in (
            ('aaaaaaaa', 'fix the launch bug on windows'),
            ('bbbbbbbb', 'You are distilling durable LESSONS from a coding-session '
                         'transcript so future sessions start smarter.'),
            ('cccccccc', 'Summarise the diff below.\n\n' + sessions.HEADLESS_MARK)):
        make_jsonl(os.path.join(folder, sid + '.jsonl'), n_msgs=2, preview=text)

    block = cmd._build_sessions_block(folder, {})
    assert 'fix the launch bug' in block
    assert 'distilling durable LESSONS' not in block, 'a lessons scan was listed as a session'
    assert 'Summarise the diff' not in block, 'HEADLESS_MARK did not exclude the call'


def test_headless_lines_already_in_the_file_are_dropped(monkeypatch, tmp_path):
    """The block is rebuilt by MERGING with what CLAUDE.md already holds, so
    filtering only the fresh scan would leave every historical one in place."""
    from claude_sessions import claude_md as cmd
    Sandbox(monkeypatch, tmp_path)
    existing = {
        'f48befd7': "- **f48befd7** (74 msgs): i don't see my accounts anymore",
        'dbe1a401': '- **dbe1a401** (2 msgs): You are distilling durable LESSONS from a transcript',
        '34df1808': '- **34df1808** (3 msgs): Compress this CLAUDE.md project-instructions file. It is',
    }
    block = cmd._build_sessions_block('', existing)
    assert 'accounts anymore' in block
    assert 'distilling durable LESSONS' not in block
    assert 'Compress this CLAUDE.md' not in block


def test_every_headless_prompt_leaves_marked(monkeypatch, tmp_path):
    """One seam, so marking cannot be forgotten at a new call site: everything
    that shells out to `claude -p` goes through memory._claude_stdin."""
    from claude_sessions import sessions
    Sandbox(monkeypatch, tmp_path)
    seen = {}
    monkeypatch.setattr(memory, 'extract_model', lambda: '')
    monkeypatch.setattr(memory._c, 'get_claude_exe', lambda: 'claude.exe')
    monkeypatch.setattr(memory._tls, 'silent', True, raising=False)

    def fake(args, input_text=None, cwd=None, timeout=None):
        seen['prompt'] = input_text
        return '{}'
    import claude_sessions.gui_api as ga
    monkeypatch.setattr(ga, '_run_cancellable', fake)

    memory._claude_stdin('extract this module', str(tmp_path))
    assert sessions.HEADLESS_MARK in seen['prompt']
    assert seen['prompt'].startswith('extract this module')
