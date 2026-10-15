"""One renderer for everything P12 hands to a harness or shows a returning
user (p12-design-gate §12.1): a checkpoint, a continuity brief, a hand-off
artifact. Markdown, deterministic from its inputs, harness-neutral, redacted,
capped, with a provenance footer. Nothing ever parses what these produce: a
rendering is a delivery, never a source of truth and never a grant.
"""

from ..redact import redact

CHECKPOINT_CAP = 12000
ARTIFACT_CAP = 24000
TURNS = 40
#: what a brief or an artifact deliberately leaves out (§11.4)
NOT_INCLUDED = ('the transcript of any session', 'tool calls and their output',
                'earlier briefs', 'any approval as a permission: every action is judged again')


def _cap(text, cap, keep='head'):
    text = redact(text)
    if len(text) <= cap:
        return text
    note = '\n\n[... %d characters omitted ...]\n\n' % (len(text) - cap)
    return text[:cap] + note if keep == 'head' else note + text[-cap:]


def _lines(items, fmt=str):
    return ['- %s' % fmt(x) for x in items] or ['- (none)']


def checkpoint(cp):
    """The markdown of one checkpoint: what the next execution's prompt ends with."""
    out = ['# Checkpoint %s' % cp.id, '',
           'Continuing task `%s` of mission `%s` (plan v%s), from execution `%s` (%s).'
           % (cp.task_id, cp.mission_id, cp.plan_version, cp.execution_id, cp.trigger), '',
           '## Objective', '', cp.objective or '(none)', '']
    if cp.constraints:
        out += ['## Constraints', ''] + _lines(cp.constraints) + ['']
    if cp.success_criteria:
        out += ['## Success criteria', ''] + _lines(cp.success_criteria) + ['']
    out += ['## Tasks so far', ''] + _lines(cp.completed_steps) + ['']
    out += ['## Files changed', ''] + _lines(cp.files_changed) + ['']
    out += ['## Decisions', ''] + _lines(cp.decisions) + ['']
    out += ['## Open problems', ''] + _lines(cp.open_problems) + ['']
    if cp.verification:
        out += ['## Verification', ''] + _lines(cp.verification) + ['']
    out += ['## Next action', '', cp.next_action or 'continue the task from the diff and the '
            'open problems', '', '---',
            'Derived by Archeus at event %d from the execution\'s records, never from a '
            'transcript.' % cp.as_of_seq]
    return _cap('\n'.join(out), CHECKPOINT_CAP)


def _mission(m):
    if m is None:
        return ['This session continues no mission.']
    out = ['Mission `%s` — %s: **%s**%s.' % (m['id'], m['title'], m['state'],
                                              ', plan v%d' % m['plan_version']
                                              if m.get('plan_version') else '')]
    for t in m['tasks']:
        e = t.get('execution')
        out.append('- %s %s: %s%s' % (t['key'], t['title'], t['state'],
                                      ' (execution %s %s)' % (e['id'], e['state']) if e else ''))
    if m['needs_you']:
        out += ['', 'Needs you (information only; approving is a separate step):']
        out += _lines(m['needs_you'], lambda a: '%s %s (%s)' % (a['kind'], a['id'], a['state']))
    return out


def _problems(problems):
    out = []
    for p in problems:
        out.append('- task %s, execution %s (%s): %s; next: %s' % (
            p['task_key'], p['execution_id'], p['trigger'],
            '; '.join(p['open_problems']) or 'none', p['next_action'] or '-'))
    return out or ['- (none)']


def _footer(ctx, head):
    pkg = ctx.get('package_id')
    return ['---', 'Rendered by Archeus at event %d from current state%s. Not included: %s.'
            % (head, '; context package %s (as of event %d, %s)'
               % (pkg, ctx['as_of_seq'], 'rebuilt' if ctx['rebuilt'] else 'reused')
               if pkg else '', '; '.join(NOT_INCLUDED))]


def brief(b):
    """The continuity brief: where the work is, what needs the user, what
    changed since this session last saw it, what is open."""
    s = b['session']
    out = ['# Since you left', '',
           'Session `%s` on %s%s, last seen at event %d.' % (
               s['id'], s['harness_id'], ' (%s)' % s['model'] if s.get('model') else '',
               s['last_seen_seq']), '', '## Where the work is', ''] + _mission(b['mission'])
    out += ['', '## What changed', '']
    groups = b['changes']['groups']
    out += ['- %s %s: %s (%d events)' % (g['ref']['kind'], g['ref']['id'], g['headline'],
                                         g['count']) for g in groups] or ['- nothing']
    if b['changes'].get('truncated'):
        out.append('- (older changes are past the retained log)')
    out += ['', '## Open problems', ''] + _problems(b['open_problems'])
    if b['missing']:
        out += ['', '## Missing', ''] + _lines(b['missing'])
    out += [''] + _footer(b['context'], b['as_of_seq'])
    return _cap('\n'.join(out), ARTIFACT_CAP)


def handoff(source, state, turns):
    """The artifact a hand-off target opens on: the mission from current state
    (when the source continues one) or the source's text turns (when it does
    not — the one stated exception to ADR-0004), never the source's
    provider-private state."""
    out = ['# Handed over from session %s' % source['id'], '',
           'You are continuing work that was started in another session (%s). '
           'Everything below is what Archeus handed over; the other session\'s own '
           'history is not available to you.' % source['harness_id'], '']
    if state is not None:
        out += ['## Where the work is', ''] + _mission(state['mission'])
        out += ['', '## Open problems', ''] + _problems(state['open_problems'])
        if state['missing']:
            out += ['', '## Missing', ''] + _lines(state['missing'])
        out += [''] + _footer(state['context'], state['as_of_seq'])
        return _cap('\n'.join(out), ARTIFACT_CAP)
    body = ['## The conversation so far (text turns only, the last %d)' % TURNS, '']
    for role, text in turns[-TURNS:]:
        body += ['### %s' % ('User' if role == 'user' else 'Assistant'), '', text.strip(), '']
    tail = _cap('\n'.join(body), ARTIFACT_CAP, keep='tail')
    return '\n'.join(out) + tail + '\n\n---\nDerived from the source session\'s text turns; ' \
        'tool calls, tool output and thinking were left out.'
