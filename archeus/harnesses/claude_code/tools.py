"""Claude Code tool removal (ADR-0052, PV-22; p20-design-gate slice F).

Beneath the hook, before the process exists: `--tools` names, in allow-form,
the built-in tools the task's action classes map to, and `--disallowedTools`
keeps out the MCP servers that were not opted in (ADR-0049). A tool absent from
`--tools` cannot be called, whatever a hook or a permission rule says: Claude
Code answers "No such tool available" and the hook never sees the call.
`--allowedTools` is never passed: it pre-approves rather than restricts.

    tool_argv(action_classes, inventory) -> the spawn's tool flags

The mapping (TOOLS, NO_TOOL) is ADR-0052 §2's, unchanged. What reaches
`--tools` is the mapping intersected with SNAPSHOT, the names the installed CLI
was read to offer (p20-design-gate C1): Claude Code drops a `--tools` name it
does not know without a word, so a stale name silently removes a tool and a
misspelt one can never add one. The snapshot is the guard, compared with the
installed CLI by tools/claude_tool_drift.py.

The MCP rule (C2): nothing opted in, `mcp__*`; something opted in, a deny per
excluded server the inventory names, in the name Claude Code gives it. An
excluded server whose name collides with an opted-in one's is not denied (L1),
and one the inventory cannot name (a local-scope server, a claude.ai connector,
a plugin's) is not named (L2): `--strict-mcp-config`, which loads only the
`--mcp-config` servers, is what keeps those out.
"""

import re

from ..sources import DEFAULT_FLAGS

#: ADR-0052 §2: the tools an action class makes available
TOOLS = {'read': ('Read', 'Glob', 'Grep', 'LS'),
         'write_repo': ('Write', 'Edit', 'MultiEdit', 'NotebookEdit'),
         'exec': ('Bash', 'PowerShell'),
         'web': ('WebFetch', 'WebSearch')}
#: ADR-0052 §2: no tool of their own; they act through Bash and are enforced
#: by the hook (P9, per canonical action) and credential removal only
NO_TOOL = ('git_commit', 'git_push', 'deploy', 'install', 'destructive', 'external_comm',
           'credential', 'spend', 'personal_data')
#: offered while an opted-in source or plugin brings a skill (D6; C3): the hook
#: judges every call to it as an unclassified `exec`
SKILL = 'Skill'

#: What the installed Claude Code offers: `init.tools` under the narrowest
#: settings sources, on a subscription login, for every model an execution may
#: name (p20-design-gate §12, F.0 and slice F). The set depends on the login,
#: the API host and the model, so it is read on the account an execution runs
#: on, model by model, never on an API key against another host.
SNAPSHOT = {
    'version': '2.1.292',
    'read': '2026-10-07',
    'models': ('haiku', 'sonnet', 'opus', 'fable'),
    #: offered with only these models (the union is `tools`)
    'model_only': {'TaskCreate': ('haiku',), 'TaskGet': ('haiku',), 'TaskList': ('haiku',),
                   'TaskUpdate': ('haiku',)},
    'tools': ('Bash', 'CronCreate', 'CronDelete', 'CronList', 'DesignSync', 'Edit',
              'EnterWorktree', 'ExitWorktree', 'Glob', 'Grep', 'ListAgents', 'Monitor',
              'NotebookEdit', 'PowerShell', 'PushNotification', 'Read', 'RemoteTrigger',
              'ReportFindings', 'ScheduleWakeup', 'SendMessage', 'ShareOnboardingGuide', 'Task',
              'TaskCreate', 'TaskGet', 'TaskList', 'TaskStop', 'TaskUpdate', 'ToolSearch',
              'WebFetch', 'WebSearch', 'Workflow', 'Write'),
    #: added only while slash commands are on (not under --disable-slash-commands)
    'with_slash_commands': ('Skill',),
    #: mapped by ADR-0052 §2, not offered by this CLI: never passed
    'mapped_not_offered': ('LS', 'MultiEdit'),
}
#: offered by the CLI, mapped by no class: excluded by default (ADR-0052 §3).
#: `ToolSearch` among them is also what keeps WebFetch and WebSearch callable:
#: with it in `--tools` they are deferred behind it (F.0)
EXCLUDED = ('CronCreate', 'CronDelete', 'CronList', 'DesignSync', 'EnterWorktree',
            'ExitWorktree', 'ListAgents', 'Monitor', 'PushNotification', 'RemoteTrigger',
            'ReportFindings', 'ScheduleWakeup', 'SendMessage', 'ShareOnboardingGuide', 'Task',
            'TaskCreate', 'TaskGet', 'TaskList', 'TaskStop', 'TaskUpdate', 'ToolSearch',
            'Workflow')
#: one tool under two names: `init` reports `Task`, the API and --tools say `Agent`
ALIASES = {'Agent': 'Task'}


def offered():
    return set(SNAPSHOT['tools']) | set(SNAPSHOT['with_slash_commands'])


def allowed(action_classes, *, skill=False):
    """The `--tools` names: mapped by a class the task holds, and offered."""
    have = offered()
    names = [t for c, tools in TOOLS.items() if c in action_classes for t in tools if t in have]
    return names + [SKILL] if skill else names


def mcp_name(server):
    """The name Claude Code gives *server* in its tools' names. Observed on
    2.1.292: `.` and `@` become `_`, `-` and case are kept; a deny written with
    the raw name matches nothing."""
    return re.sub(r'[^A-Za-z0-9_-]', '_', server)


def mcp_deny(inventory):
    """The `--disallowedTools` patterns for the MCP servers (C2)."""
    inv = inventory or {}
    opted = {mcp_name(s['name']) for s in (inv.get('flags') or DEFAULT_FLAGS)['mcp_servers']}
    if not opted:
        return ['mcp__*']
    return sorted({'mcp__' + mcp_name(i['name']) for i in inv.get('items') or ()
                   if i.get('type') == 'mcp_server' and i.get('status') == 'excluded'
                   and i.get('source') in ('user', 'project')
                   and mcp_name(i['name']) not in opted})


def tool_argv(action_classes, inventory):
    """`--tools` always (empty when nothing is mapped: left out, it would mean
    every tool), and `--disallowedTools` when there is an MCP server to deny."""
    flags = (inventory or {}).get('flags') or DEFAULT_FLAGS
    a = ['--tools', ','.join(allowed(action_classes, skill=not flags['disable_slash_commands']))]
    deny = mcp_deny(inventory)
    return a + ['--disallowedTools', ','.join(deny)] if deny else a
