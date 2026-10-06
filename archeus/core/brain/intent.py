"""`intent.v1`: the brain's reading of one message (ADR-0006, plan §11 step 2; P7).

The model reads the message against the ContextPackage P5 assembled for it and
says what the user wants — never how to do it. It names objects only by the
HANDLES this module gives the package's items (`p1`, `m2`, `k1`, …), so an id
it could have invented never reaches Core: an unknown handle is invalid output
(retried once by `archeus_call`, then the call ends `invalid`). Everything the
answer decides is then decided again by Core, deterministically, in
`application/conversation.py`; this module only validates and resolves.

Nothing here writes, spawns or plans: no task, no plan, no route, no policy.
"""

from ...infra.db import rows
from ..domain import entities, states
from ..context.assemble import CHALLENGEABLE

KINDS = ('question', 'new_work', 'continue_work', 'feedback', 'preference', 'idea')
MENTION_KINDS = ('project', 'repository', 'mission', 'idea', 'person', 'organization',
                 'system')
#: handle letter per referenced kind (the message being read gets none)
LETTERS = {'message': 'u', 'project': 'p', 'mission': 'm', 'idea': 'i',
           'knowledge_item': 'k', 'meeting': 'g'}
#: feedback may be about these (knowledge.FEEDBACK_SUBJECTS that a message can name)
FEEDBACK_TARGETS = ('mission', 'knowledge_item', 'message')

_S = {'type': 'string', 'maxLength': 500}
_H = {'type': 'string', 'maxLength': 12, 'nullable': True}
_ITEMS = {'type': 'array', 'maxItems': 20, 'items': {'type': 'object', 'properties': {
    'text': _S, 'origin': {'type': 'string', 'enum': ['explicit', 'inferred']}},
    'required': ['text', 'origin']}}
SCHEMA = {'type': 'object', 'properties': {
    'kind': {'type': 'string', 'enum': list(KINDS)},
    'title': {'type': 'string', 'maxLength': 120, 'nullable': True},
    'objective': {'type': 'string', 'maxLength': 1000, 'nullable': True},
    'desired_outcome': {'type': 'string', 'maxLength': 500, 'nullable': True},
    'target': _H, 'project': _H,
    'mentions': {'type': 'array', 'maxItems': 20, 'items': {'type': 'object', 'properties': {
        'name': {'type': 'string', 'maxLength': 200},
        'kind': {'type': 'string', 'enum': list(MENTION_KINDS)}, 'ref': _H},
        'required': ['name', 'kind']}},
    'requirements': _ITEMS, 'constraints': _ITEMS,
    'ambiguities': {'type': 'array', 'maxItems': 10, 'items': {'type': 'object', 'properties': {
        'question': {'type': 'string', 'maxLength': 300}, 'material': {'type': 'boolean'}},
        'required': ['question', 'material']}},
    'conflicts': {'type': 'array', 'maxItems': 10, 'items': {'type': 'object', 'properties': {
        'ref': {'type': 'string', 'maxLength': 12}, 'why': _S}, 'required': ['ref', 'why']}},
    'feedback': {'type': 'object', 'nullable': True, 'properties': {
        'signal': {'type': 'string', 'enum': ['positive', 'negative', 'correction']},
        'title': {'type': 'string', 'maxLength': 200, 'nullable': True},
        'promote': {'type': 'string', 'enum': ['PREFERENCE', 'LESSON'], 'nullable': True},
        'supersedes': _H}, 'required': ['signal']},
    'answer': {'type': 'array', 'maxItems': 20, 'nullable': True, 'items': {
        'type': 'object', 'properties': {
            'text': _S, 'refs': {'type': 'array', 'maxItems': 10,
                                 'items': {'type': 'string', 'maxLength': 12}}},
        'required': ['text', 'refs']}},
    'confidence': {'type': 'number', 'nullable': True}},
    'required': ['kind']}

PREFIX = (
    "You are the intent reader of Archeus, a system that carries out work for its user. Read "
    "the user's latest message against the context below and say what the user wants. You "
    "do not do the work, plan it, choose who does it, approve it or report it done.\n"
    "Kinds: question (they want information, even when it mentions work), new_work (they "
    "ask Archeus to take on a piece of work; set target to an idea's handle when they want "
    "that idea made into work), continue_work (more for, or a correction of, an open "
    "mission: target is its handle), feedback (an evaluation of something Archeus did or "
    "holds: target is its handle), preference (how they want things done from now on; put "
    "the preference in feedback.title, and when it replaces an earlier one set "
    "feedback.supersedes to that preference's handle, or to the handle of the earlier "
    "message that stated it), idea (a thought to keep, not yet a commitment).\n"
    "Refer to things ONLY by the handles in brackets below; never invent one. A project, "
    "repository, person or other thing the user names that you cannot find goes in mentions "
    "with ref null. Separate what the user said (origin explicit) from what you infer "
    "(origin inferred). List an ambiguity as material only when the two readings would be "
    "materially different work. List under conflicts the handles of items the request goes "
    "against, and say why; an item marked not confirmed is still listed, it stays not "
    "confirmed. For a question, answer in claims, each citing the handles it rests on.\n")


def handles(pkg):
    """[(handle, ref)] for the package's items, in its order; the subject gets none."""
    counts, out = {}, []
    for it in pkg['items']:
        ref = it['ref']
        letter = LETTERS.get(ref['kind'])
        if letter is None or ref['id'] == pkg['subject_id']:
            continue
        counts[letter] = counts.get(letter, 0) + 1
        out.append(('%s%d' % (letter, counts[letter]), {'kind': ref['kind'], 'id': ref['id']}))
    return out


def describe(conn, pkg):
    """(prompt lines, {handle: facts}) for a package: what each handle is, read
    from the rows the package cites. Facts carry what `check` judges."""
    items = {it['ref']['id']: it for it in pkg['items']}
    lines, facts = [], {}
    for h, ref in handles(pkg):
        it, kind = items[ref['id']], ref['kind']
        f = dict(ref, type=it['type'], reason=it['reason'])
        if kind == 'knowledge_item':
            k = rows.get(conn, entities.KnowledgeItem, ref['id']).entity
            f.update(state=k.state, ktype=k.type, source_kind=k.source_kind)
            label = '%s %s' % (k.type, 'CONFIRMED' if k.state == 'CONFIRMED'
                               else 'not confirmed (%s)' % k.state.lower())
            text = '%s. %s' % (k.title, k.text) if k.text else k.title
        elif kind == 'mission':
            m = rows.get(conn, entities.Mission, ref['id']).entity
            f.update(state=m.state)
            label, text = 'mission %s' % m.state, '%s: %s' % (m.title, m.objective)
        elif kind == 'idea':
            i = rows.get(conn, entities.Idea, ref['id']).entity
            f.update(state=i.state)
            label, text = 'idea %s' % i.state, i.title or i.text
        elif kind == 'project':
            p = rows.get(conn, entities.Project, ref['id']).entity
            label, text = 'project', '%s (%s)' % (p.name, ', '.join(p.root_paths))
        elif kind == 'message':
            m = rows.get(conn, entities.Message, ref['id']).entity
            # a user turn is known by what its reply produced, too
            replies = [r.entity for r in rows.where(conn, entities.Message,
                                                     in_reply_to=m.id)]
            f.update(author=m.author, cards=[dict(c) for x in [m] + replies for c in x.cards])
            label, text = 'earlier %s turn' % m.author, m.text
        else:
            mt = rows.get(conn, entities.Meeting, ref['id']).entity
            label, text = 'meeting', '%s, %s' % (mt.name, mt.held_at or 'undated')
        facts[h] = f
        lines.append('[%s] %s: %s' % (h, label, ' '.join(text.split())[:400]))
    return lines, facts


def prompt(utterance, lines, answering=None):
    parts = [PREFIX, 'Context:', *(lines or ['(nothing relevant is recorded)'])]
    if answering:
        parts += ['', 'This message answers Archeus\'s question: %s' % answering]
    return '\n'.join(parts + ['', 'The message:', utterance])


def _live_mission(f):
    return f['kind'] == 'mission' and f.get('state') not in states.terminal('mission')


def _challengeable(f):
    return f['kind'] == 'knowledge_item' and f.get('ktype') in CHALLENGEABLE and (
        f.get('state') == 'CONFIRMED' or (f.get('state') == 'CANDIDATE' and f['ktype'] == 'DECISION'
                                          and f.get('source_kind') == 'import'))


def superseded(f):
    """The knowledge item id a `feedback.supersedes` handle names, or None: a
    PREFERENCE/LESSON item, or the one an earlier message's feedback produced."""
    if f['kind'] == 'knowledge_item' and f.get('ktype') in ('PREFERENCE', 'LESSON'):
        return f['id']
    if f['kind'] == 'message':
        made = [c['ref']['id'] for c in f.get('cards', ()) if c['type'] == 'knowledge']
        return made[-1] if made else None
    return None


def check(parsed, facts):
    """Core's checks beyond the schema: every handle is one this package gave,
    of a kind that makes sense where it is used, and each kind carries what it
    needs. A list of problems; empty when the answer holds."""
    p, bad = parsed, []

    def known(h, where, ok=lambda f: True, what='a known handle'):
        if h is None:
            return None
        f = facts.get(h)
        if f is None or not ok(f):
            bad.append('%s: %r is not %s' % (where, h, what))
            return None
        return f

    def blank(v):
        return not (isinstance(v, str) and v.strip())

    kind = p['kind']
    known(p.get('project'), 'project', lambda f: f['kind'] == 'project', 'a project handle')
    for i, m in enumerate(p.get('mentions') or ()):
        known(m.get('ref'), 'mentions[%d].ref' % i,
              lambda f, k=m['kind']: f['kind'] == k, 'a %s handle' % m['kind'])
    for i, c in enumerate(p.get('conflicts') or ()):
        known(c['ref'], 'conflicts[%d].ref' % i, _challengeable,
              'a decision, architecture, standard or preference item')
    t = p.get('target')
    if kind == 'continue_work':
        if known(t, 'target', _live_mission, 'an open mission') is None and t is None:
            bad.append('continue_work names the open mission it continues (target)')
    elif kind == 'new_work':
        known(t, 'target', lambda f: f['kind'] == 'idea', 'an idea handle')
    elif kind == 'feedback':
        known(t, 'target', lambda f: f['kind'] in FEEDBACK_TARGETS,
              'a mission, knowledge item or message handle')
    else:
        known(t, 'target')
    if kind in ('new_work', 'idea') and t is None and blank(p.get('objective')):
        bad.append('%s states its objective' % kind)
    if kind == 'new_work' and t is None and blank(p.get('title')):
        bad.append('new_work has a title')
    fb = p.get('feedback')
    if kind in ('feedback', 'preference') and fb is None:
        bad.append('%s carries its feedback' % kind)
    if kind == 'preference' and fb is not None and blank(fb.get('title')):
        bad.append('a preference states itself in feedback.title')
    if fb is not None and fb.get('supersedes') is not None:
        known(fb['supersedes'], 'feedback.supersedes', lambda f: superseded(f) is not None,
              'a preference or lesson, or the earlier message that stated one')
    if kind == 'question':
        claims = p.get('answer') or []
        if not claims:
            bad.append('a question is answered in claims')
        for i, c in enumerate(claims):
            if not c['refs']:
                bad.append('answer[%d] cites nothing' % i)
            for h in c['refs']:
                known(h, 'answer[%d].refs' % i)
    c = p.get('confidence')
    if c is not None and not 0 <= c <= 1:
        bad.append('confidence is 0..1')
    return bad


def resolve(parsed, facts):
    """The answer with every handle replaced by the `{kind, id}` it names —
    what Core applies (and stores as the Intent's proposal)."""
    def ref(h):
        return None if h is None else {'kind': facts[h]['kind'], 'id': facts[h]['id']}
    p = dict(parsed)
    for k in ('target', 'project'):
        p[k] = ref(p.get(k))
    p['mentions'] = [dict(m, ref=ref(m.get('ref'))) for m in p.get('mentions') or ()]
    p['conflicts'] = [dict(c, ref=ref(c['ref']), state=facts[c['ref']]['state'])
                      for c in p.get('conflicts') or ()]
    fb = p.get('feedback')
    if fb is not None:
        sup = fb.get('supersedes')
        p['feedback'] = dict(fb, supersedes=None if sup is None else superseded(facts[sup]))
    p['answer'] = [{'text': c['text'], 'refs': [ref(h) for h in c['refs']]}
                   for c in p.get('answer') or ()]
    for k in ('requirements', 'constraints', 'ambiguities'):
        p[k] = list(p.get(k) or ())
    return p
