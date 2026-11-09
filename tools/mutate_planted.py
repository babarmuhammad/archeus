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
EVD = 'archeus/core/verification/evidence.py'
T = 'tests/v1/unit/test_verification_planted.py::'

MUTATIONS = [
    ('PL01', 'a relative `which` result is run as Core\'s Git', [(LOCAL,
     "    if not exe or not os.path.isabs(exe):",
     "    if not exe:")],
     [T + 'test_git_exe_refuses_what_which_gives_that_is_not_absolute',
      T + 'test_git_exe_never_runs_a_git_planted_in_the_current_directory']),
    ('PL02', 'the store pin hands Git the inherited PATH', [(LOCAL,
     "    env.update(PATH=os.path.dirname(exe), HOME=empty,",
     "    env.update(PATH=os.environ.get('PATH', ''), HOME=empty,")],
     [T + 'test_the_store_pin_keeps_path_to_gits_own_directory_whatever_core_inherited']),
    ('PL03', 'a confined program found outside the staged toolchain is accepted', [(EVD,
     "    if found is None or os.path.normcase(os.path.dirname(os.path.abspath(found))) not in dirs:",
     "    if found is None:")],
     [T + 'test_confined_argv_never_returns_a_workspace_program']),
    ('PL04', 'a check runs with the workspace first on PATH', [(LOCAL,
     "        env.update(PYTHONDONTWRITEBYTECODE='1', GIT_TERMINAL_PROMPT='0')",
     "        env.update(PYTHONDONTWRITEBYTECODE='1', GIT_TERMINAL_PROMPT='0',\n"
     "                   PATH=workdir + os.pathsep + env.get('PATH', ''))")],
     [T + 'test_run_check_hands_the_program_and_path_on_unchanged']),
    ('PL05', 'the unconfined argv resolves nothing: a program is left to the platform', [(EVD,
     "    found = shutil.which(argv[0])\n    return [found or argv[0]] + argv[1:]",
     "    return argv")],
     [T + 'test_argv_of_finds_a_program_on_path_not_in_the_workspace']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
