"""The T-1064 mutation suite: break each defence against a program planted in the
workspace (H5, H6), run the tests written for it, and require them to fail.

    py tools/mutate_planted.py            every mutation
    py tools/mutate_planted.py PL01 PL03  only these

Same runner as tools/mutate_p11.py; it edits archeus/node/local.py and
archeus/core/verification/evidence.py and restores them whatever happens: run it
with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (one runner)

LOCAL = 'archeus/node/local.py'
PROC = 'claude_sessions/proc.py'
EVD = 'archeus/core/verification/evidence.py'
T = 'tests/v1/unit/test_verification_planted.py::'

MUTATIONS = [
    ('PL01', 'a relative `which` result is run as Core\'s Git', [(LOCAL,
     "    if not exe or not os.path.isabs(exe):",
     "    if not exe:")],
     [T + 'test_git_exe_refuses_what_which_gives_that_is_not_absolute',
      T + 'test_git_exe_never_runs_a_git_planted_in_the_current_directory']),
    ('PL02', 'the store pin hands Git the inherited PATH', [(LOCAL,
     "}\n    env.update(PATH=os.path.dirname(exe), HOME=empty,",
     "}\n    env.update(PATH=os.environ.get('PATH', ''), HOME=empty,")],
     [T + 'test_the_store_pin_keeps_path_to_gits_own_directory_whatever_core_inherited']),
    ('PL03', 'a confined program found outside the staged toolchain is accepted', [(EVD,
     "    found = proc.which(argv[0], path=os.pathsep.join(toolchain))",
     "    found = proc.which(argv[0])")],
     [T + 'test_confined_argv_never_returns_a_workspace_program']),
    ('PL04', 'a check runs with the workspace first on PATH', [(LOCAL,
     "        env.update(PYTHONDONTWRITEBYTECODE='1', GIT_TERMINAL_PROMPT='0')",
     "        env.update(PYTHONDONTWRITEBYTECODE='1', GIT_TERMINAL_PROMPT='0',\n"
     "                   PATH=workdir + os.pathsep + env.get('PATH', ''))")],
     [T + 'test_run_check_hands_the_program_and_path_on_unchanged']),
    ('PL05', 'the unconfined argv resolves nothing: a program is left to the platform', [(EVD,
     "    found = proc.which(argv[0], avoid=[workspace])\n    return [found] + argv[1:] if found else None",
     "    return argv")],
     [T + 'test_argv_of_finds_a_program_on_path_not_in_the_workspace']),
    ('PL06', 'the unconfined argv falls back to the bare name when PATH lacks it', [(EVD,
     "    return [found] + argv[1:] if found else None\n\n\ndef confined_argv",
     "    return [found or argv[0]] + argv[1:]\n\n\ndef confined_argv")],
     [T + 'test_argv_of_skips_a_workspace_directory_on_path_and_fails_closed']),
    ('PL07', 'the resolver searches the current directory', [(PROC,
     "        if (not os.path.isabs(d) or a == cwd\n",
     "        if (not os.path.isabs(d)\n")],
     [T + 'test_which_never_searches_the_current_directory_or_a_relative_entry']),
    ('PL08', 'the resolver searches a relative PATH entry', [(PROC,
     "        if (not os.path.isabs(d) or a == cwd\n",
     "        if (a == cwd\n")],
     [T + 'test_which_never_searches_the_current_directory_or_a_relative_entry']),
    ('PL09', 'the resolver searches a directory inside the workspace', [(PROC,
     "                or any(a == b or a.startswith(b.rstrip(os.sep) + os.sep) for b in barred)):",
     "                ):")],
     [T + 'test_argv_of_skips_a_workspace_directory_on_path_and_fails_closed']),
    ('PL10', 'a bare program is left to the platform search when proc.run spawns it', [(PROC,
     "        exe = which(args[0], avoid=[cwd])\n        if exe is None:\n            return None\n        args = [exe, *args[1:]]",
     "        pass")],
     [T + 'test_a_bare_git_call_of_core_resolves_to_path_when_core_is_elsewhere']),
    ('PL11', 'a bare program PATH lacks outside the workspace is still spawned by name', [(PROC,
     "        if exe is None:\n            return None\n        args = [exe, *args[1:]]",
     "        args = [exe or args[0], *args[1:]]")],
     [T + 'test_a_bare_git_call_fails_closed_when_only_the_workspace_holds_git']),
    ('PL12', 'a project Git call runs a Git that lies inside the repository', [(LOCAL,
     "    exe = proc.which('git', avoid=[root])\n",
     "    exe = proc.which('git')\n")],
     [T + 'test_a_project_git_call_fails_closed_when_the_git_on_path_is_inside_the_repository']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
