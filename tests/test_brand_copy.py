"""The positioning sentence, in one place, checked against every surface.

There is no single source for this string and there cannot be one: it has to
appear in `pyproject.toml`, `mkdocs.yml`, `CITATION.cff`, two `plugin.json`s and
an `index.html`, none of which can import Python, plus a TypeScript module the
Python build never runs. A generator would need a build step and a committed
artefact for each format, and the artefacts would be the thing that fell behind
— which is the same trap `docs/gui-audit.md` fell into by hand-maintaining a
copy of something the code already stated.

So this is a GATE instead of a generator. The sentence is defined once, here,
and every surface is asserted against it. That inverts the failure: drift fails
the build in the file that drifted rather than shipping a page that says
something the rest of the product no longer says.

The dead phrasings are asserted ABSENT from every tracked file, which is the
half that actually catches a miss — a surface nobody remembered to list is
invisible to the positive check, but not to this one.

Three files are exempt from the dead check, each for a stated reason:

  CHANGELOG.md          release notes describe the pitch a release really had,
                        including the change to this one. Same reason
                        `tools/_rename_brand.py` skips it for the old name.
  notes/brand-study.md  the document that records why the sentence changed. It
                        has to be able to quote what it replaced.
  this file             it defines the strings.
"""
import io
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The canonical pitch, verbatim. Short slots use the first sentence alone.
PITCH = 'The memory and workspace layer for AI coding agents.'
SUB = ('Persistent per-project memory, every session you have ever had, and '
       'control over what the next one costs. Works with Claude Code today.')

#: The pitch without its leading article and trailing period, so it can be
#: asserted inside running prose ("the Python memory and workspace layer for
#: AI coding agents"). Derived, not retyped — two spellings of one sentence is
#: two chances for them to disagree.
CANON = PITCH[len('The '):-1]

#: Stated separately and never as a feature. A roadmap sentence that reads as a
#: capability is a claim the product cannot honour.
GOAL = 'Claude Code is the first surface, not the boundary'

#: What the pitch used to be, in all three of the shapes it had drifted into.
#: `manager` came from the plugin manifests, which had never been updated when
#: `layer` replaced it; `Windows workspace manager` came from the pre-2.0
#: description and outlived the port to macOS and Linux.
DEAD = (
    'workspace layer for Claude Code',
    'workspace manager for Claude Code',
    'Windows workspace manager',
)

DEAD_EXEMPT = {
    'CHANGELOG.md',
    'notes/brand-study.md',
    'tests/test_brand_copy.py',
}

#: Surfaces that state the pitch as a pitch, and so carry the sentence whole.
PITCH_SLOTS = (
    'README.md',
    'pyproject.toml',
    'mkdocs.yml',
    'CITATION.cff',
    'CONTRIBUTING.md',
    'docs/index.md',
    'docs/getting-started.md',
    'docs/compare.md',
    'docs/llms.txt',
    'claude_sessions/cli.py',
    'plugin/.claude-plugin/plugin.json',
    '.claude-plugin/marketplace.json',
    'tools/make_og_card.py',
    'www/lib/site.ts',
    'www/lib/content.ts',
    'www/lib/faq.ts',
)

#: Surfaces where the positioning is stated in prose, so only the phrase itself
#: can be asserted — not the sentence with its article and full stop.
PROSE_SLOTS = (
    'www/README.md',
    'www/app/llms.txt/route.ts',
)

#: Slots too narrow for the sentence, with what they carry instead. A short form
#: is a decision, so it is pinned here rather than left to whoever edits the
#: markup next.
#:
#: EMPTY, and that is the decision. The GUI sidebar used to be the one entry:
#: a `.brand small` carrying "memory & workspace for AI agents" under the
#: product name. It is gone, and not for want of room — a tagline is a WEBSITE
#: device. Its audience is a reader who does not yet know what the thing is, and
#: nobody looking at this sidebar is that person: they installed it, launched it
#: and are looking at their own projects. It also failed the differentiation
#: test outright (every coding-agent tool could print it verbatim; no product
#: claims the opposite), and it cost ~70px above the search field people are
#: actually aiming at. The slot carries the switchable CONTEXT now — the Claude
#: Code account — with a line of state under it, which is what shadcn's sidebar
#: header, Notion, Linear, GitLab and Figma all put there.
#:
#: Kept as a table rather than deleted: the mechanism is the thing worth having,
#: and the next narrow surface should land in here rather than inventing its own
#: wording. test_no_slot_reintroduces_a_tagline is the other half.
SHORT_SLOTS = {}

#: Long-form slots, which carry the second sentence as well as the first.
LONG_SLOTS = (
    'README.md',
    'pyproject.toml',
    '.claude-plugin/marketplace.json',
    'www/lib/content.ts',
)


def _read(rel):
    with io.open(os.path.join(ROOT, rel.replace('/', os.sep)),
                 encoding='utf-8') as f:
        return f.read()


def _norm(text):
    """Collapse every run of whitespace to one space.

    Every surface here wraps: a YAML folded scalar, a Markdown paragraph and an
    HTML attribute all put line breaks inside the sentence, so a raw substring
    search would fail on correct copy and pass only on copy that happened to fit
    a line. Normalising is what makes the assertion about the words."""
    return ' '.join(text.split())


def _tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8', check=True).stdout
    return [r for r in out.splitlines() if r and r not in DEAD_EXEMPT]


def test_the_pitch_appears_whole_in_every_pitch_slot():
    missing = [rel for rel in PITCH_SLOTS if PITCH not in _norm(_read(rel))]
    assert not missing, 'the pitch is missing from: %s' % missing


def test_the_positioning_appears_in_every_prose_slot():
    missing = [rel for rel in PITCH_SLOTS + PROSE_SLOTS
               if CANON not in _norm(_read(rel))]
    assert not missing, 'the positioning is missing from: %s' % missing


def test_the_narrow_slots_carry_the_agreed_short_form():
    """A short slot is still a surface. Left unchecked it is the one place the
    old wording survives, which is exactly how `workspace manager` outlived
    `workspace layer` in the two plugin manifests."""
    missing = [rel for rel, short in SHORT_SLOTS.items()
               if short not in _norm(_read(rel))]
    assert not missing, 'the short form is missing from: %s' % missing


def test_the_app_chrome_carries_no_tagline():
    """The GUI is not a landing page. A descriptor under the product name in the
    sidebar is a tagline, and a tagline addresses someone who has not decided to
    use the thing yet — which is nobody who is looking at this window.

    Asserted as an ABSENCE because that is the failure mode: the line was
    removed once and the pressure to put "something explanatory" back into the
    top of the sidebar does not go away. The positioning has plenty of surfaces
    (PITCH_SLOTS, LONG_SLOTS); the app's own chrome is not one of them."""
    # comments stripped first: the note explaining why the line is gone quotes
    # the line, and a gate that forbids explaining itself is a gate that gets
    # its reasoning deleted the first time someone hits it
    html = _norm(re.sub(r'<!--.*?-->', ' ',
                        _read('claude_sessions/web/index.html'), flags=re.S))
    for dead in ('workspace for AI agents', 'workspace for Claude Code',
                 'memory &amp; workspace', 'memory & workspace'):
        assert dead not in html, f'a tagline is back in the sidebar: {dead!r}'
    # and the slot that replaced it is the account, with state under it
    assert 'id="brandName"' in html and 'id="brandSub"' in html
    assert 'id="acctMenu"' in html, 'the row switches nothing'
    js = _read('claude_sessions/web/app.js')
    assert 'function drawBrand()' in js
    assert "b.textContent=act?act.name:'archeus';" in js


def test_the_long_form_slots_state_what_it_does_and_what_it_works_with():
    """The second sentence is not decoration: it is the only place the pitch
    says what you get and which agent it runs against today. A slot with room
    for it and without it is a claim with no substance behind it."""
    missing = [rel for rel in LONG_SLOTS if SUB not in _norm(_read(rel))]
    assert not missing, 'the second sentence is missing from: %s' % missing


def test_the_direction_is_stated_as_a_goal_and_not_as_a_feature():
    """Provider-neutral memory does not exist. It is a goal, so every surface
    that mentions it has to say so in the same breath — and the README, the
    docs, the LLM-facing text and the FAQ are the four places someone forms an
    expectation from."""
    for rel in ('README.md', 'docs/getting-started.md', 'docs/llms.txt',
                'www/lib/faq.ts', 'www/lib/content.ts'):
        text = _norm(_read(rel))
        assert GOAL in text, '%s does not state the direction' % rel
        assert re.search(r'long-term (goal|direction)', text), \
            '%s states the direction without calling it a goal' % rel


def test_the_pypi_keywords_are_not_a_claude_monopoly():
    """The whole list used to be `claude*`, which names the surface archeus
    drives rather than the thing it is. `claude-code` stays — it IS the
    surface — but it cannot be the only way to find this."""
    text = _read('pyproject.toml')
    block = text.split('keywords = [', 1)[1].split(']', 1)[0]
    for kw in ('ai-agents', 'agent-memory', 'coding-agent'):
        assert '"%s"' % kw in block, 'pyproject keywords dropped %r' % kw
    assert '"claude-code"' in block, 'claude-code is still the surface'


def test_the_two_single_source_slots_hold_the_sentence_and_not_a_comment():
    """`site.ts` is the tagline every page, the manifest, both llms.txt routes
    and the OG image alt read from; `make_og_card.TAG` is the picture social
    previews show. Both files also *discuss* the sentence in a comment, so a
    substring check would pass on the comment alone after the value itself had
    been changed."""
    assert "tagline: '%s'" % PITCH in _read('www/lib/site.ts')
    assert "TAG = '%s'" % PITCH in _read('tools/make_og_card.py')


def test_no_tracked_file_still_carries_a_dead_pitch():
    bad = []
    for rel in _tracked():
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        try:
            with io.open(path, encoding='utf-8') as f:
                text = _norm(f.read())
        except (OSError, UnicodeDecodeError):
            continue                    # binary — .ico, .png and friends
        for dead in DEAD:
            if dead in text:
                bad.append('%s: %r' % (rel, dead))
    assert not bad, 'a dead pitch survives in:\n  ' + '\n  '.join(bad)


def test_every_listed_surface_exists():
    """The lists above are the gate's whole coverage, so a renamed file must
    fail loudly rather than silently stop being checked."""
    listed = set(PITCH_SLOTS) | set(PROSE_SLOTS) | set(SHORT_SLOTS) | set(LONG_SLOTS)
    missing = [rel for rel in sorted(listed)
               if not os.path.isfile(os.path.join(ROOT, rel.replace('/', os.sep)))]
    assert not missing, 'listed surfaces that do not exist: %s' % missing
