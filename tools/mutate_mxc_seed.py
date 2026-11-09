"""The PV20 B5 and B8 mutation suite: break each property of the copy seed's destination
and of the manager's isolated project workspace that the seed, staged-seed, wire-seed,
execution-unit and repository-store tests hold, run the test written for it, and require it
to fail.

    py tools/mutate_mxc_seed.py                 every mutation
    py tools/mutate_mxc_seed.py MS01 MS10       only these

It edits archeus/node/seed.py and archeus/core/execution/manager.py, and restores them
whatever happens: run it with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

SEED = 'archeus/node/seed.py'
MGR = 'archeus/core/execution/manager.py'
LOCAL = 'archeus/node/local.py'
T = 'tests/v1/unit/test_seed.py::'
G = 'tests/v1/unit/test_staging_seed.py::'
W = 'tests/v1/unit/test_mxc_wire_seed.py::'
U = 'tests/v1/unit/test_execution_units.py::'
R = 'tests/v1/integration/test_repo_store.py::'

IN_PLACE = T + 'test_an_existing_empty_directory_is_seeded_in_place_and_scanned'
NOT_EMPTY = T + 'test_an_existing_directory_with_anything_in_it_is_refused_untouched'
ALIAS = T + 'test_an_existing_destination_that_is_an_alias_is_refused_before_anything_is_written'
FIRST = U + 'test_an_isolated_first_process_is_seeded_from_the_store_and_never_runs_in_the_root'
RETRY = U + 'test_a_retry_or_continuation_is_seeded_from_the_base_core_recorded'
RESUME = U + 'test_a_resume_keeps_the_recorded_workspace_and_base_and_resolves_nothing'
LOST = U + 'test_a_resume_without_its_recorded_seed_or_workspace_is_refused_with_no_spawn'
REFUSED = U + 'test_a_continuation_with_nothing_to_continue_is_a_charged_import_failure_with_no_spawn'
CHAIN = R + 'test_the_managers_chain_gives_a_workspace_the_launch_can_grant_and_a_resume_reuses_it'

MUTATIONS = [
    ('MS01', 'an existing destination is not checked to be a plain directory', [(SEED,
     "    _entry(root, '.', True)\n    if _list(root, '.'):",
     "    if _list(root, '.'):")], [ALIAS, G + 'test_seed_refuses_an_existing_folder_that_is_a_file']),
    ('MS02', 'an existing destination may hold anything', [(SEED,
     "    if _list(root, '.'):\n        raise SeedError('the destination already exists and is not empty')",
     "    if False:\n        raise SeedError('the destination already exists and is not empty')")],
     [NOT_EMPTY, G + 'test_seed_into_an_existing_folder_with_anything_in_it_refused']),
    ('MS03', 'a destination that exists is created again', [(SEED,
     '    if not exists:\n        os.mkdir(root)', '    if True:\n        os.mkdir(root)')],
     [IN_PLACE, W + 'test_the_empty_workspace_is_granted_then_seeded_in_place_then_the_launch_ends_clean']),
    ('MS04', 'an absent destination is believed to exist and never created', [(SEED,
     '    except FileNotFoundError:\n        return root, False',
     '    except FileNotFoundError:\n        return root, True')],
     [T + 'test_seed_copy_writes_a_fresh_tree_byte_for_byte']),
    ('MS05', 'an existing destination is never listed, so a full one passes', [(SEED,
     "    if _list(root, '.'):\n        raise SeedError('the destination already exists and is not empty')\n    return root, True",
     "    return root, True")],
     [NOT_EMPTY, T + 'test_a_second_seed_into_the_filled_directory_is_refused']),
    ('MS06', 'the workspace is seeded even when it already holds something', [(SEED,
     "    root, exists = _fresh(dest_root, scan)",
     "    root, exists = _root(dest_root), os.path.exists(dest_root)")],
     [NOT_EMPTY, ALIAS]),
    ('MS07', 'a resume resolves and seeds again instead of reusing the record', [(MGR,
     '        if e.process_seq:\n            if e.seed_revision is None', '        if False:\n            if e.seed_revision is None')],
     [RESUME]),
    ('MS08', 'a resume trusts a workdir other than the one recorded', [(MGR,
     'if e.seed_revision is None or e.workdir != work or not os.path.isdir(work):',
     'if e.seed_revision is None or not os.path.isdir(work):')], [LOST]),
    ('MS09', 'a resume trusts a workspace that is gone', [(MGR,
     'if e.seed_revision is None or e.workdir != work or not os.path.isdir(work):',
     'if e.seed_revision is None or e.workdir != work:')], [LOST]),
    ('MS10', 'a resume with no recorded base goes on', [(MGR,
     'if e.seed_revision is None or e.workdir != work or not os.path.isdir(work):',
     'if e.workdir != work or not os.path.isdir(work):')], [LOST]),
    ('MS11', 'a resume forgets the base it recorded', [(MGR,
     '            return work, e.branch, e.seed_revision', '            return work, e.branch, None')],
     [RESUME]),
    ('MS12', 'a resume forgets the branch it recorded', [(MGR,
     '            return work, e.branch, e.seed_revision', '            return work, None, e.seed_revision')],
     [RESUME]),
    ('MS13', 'a retry takes the base from the user refs again', [(MGR,
     '            base = X.seed_base(r, e)', '            base = None')], [RETRY]),
    ('MS14', 'a first attempt takes no base from the user repository', [(MGR,
     '        if base is None:\n            name, base = self.node.resolve_base(',
     '        if True:\n            name, base = self.node.resolve_base(')], [RETRY]),
    ('MS15', 'the base is resolved against another branch than the mission branch', [(MGR,
     'self.node.resolve_base(root, mission_branch(m.id), workdirs=workdirs)',
     "self.node.resolve_base(root, 'HEAD', workdirs=workdirs)")], [FIRST]),
    ('MS16', 'the base is never fetched into the store', [(MGR,
     '            self.node.store_fetch(project_id, root, name, base, seed_ref(e.id),\n'
     '                                  workdirs=workdirs, **fetch_options)\n',
     '            pass\n')], [FIRST]),
    ('MS17', 'the base is fetched into a ref that is not the execution seed ref', [(MGR,
     'self.node.store_fetch(project_id, root, name, base, seed_ref(e.id),',
     "self.node.store_fetch(project_id, root, name, base, 'refs/archeus/seed',")], [FIRST]),
    ('MS18', 'the store calls are made with no recorded workdirs', [(MGR,
     '        project_id, workdirs = self._store_inputs(e)\n        with self.db.read() as r:\n',
     '        project_id, workdirs = self._store_inputs(e)[0], []\n'
     '        with self.db.read() as r:\n')],
     [FIRST]),
    ('MS19', 'the execution branch is not the task branch', [(MGR,
     "        branch = 'archeus/%s.%s' % (m.id, t.key)", "        branch = 'archeus/%s' % m.id")],
     [FIRST]),
    ('MS20', 'an isolated project execution gets the worktree path again', [(MGR,
     '        if isolated:\n            return self._seeded(e, m, t, root)',
     '        if False:\n            return self._seeded(e, m, t, root)')], [FIRST]),
    ('MS21', 'the recorded seed is not handed to the preparation', [(MGR,
     '                       seed_revision=seed, inventory_sha256=sha,',
     '                       seed_revision=None, inventory_sha256=sha,')], [FIRST, RETRY]),
    ('MS22', 'a refused seed base is a plain workspace failure', [(MGR,
     "stop_reason='workspace', failure_class=err.failure_class)", "stop_reason='workspace')")],
     [REFUSED]),
    ('MS23', 'a refused seed base is not caught and stops the pass', [(MGR,
     '        except X.SeedRefused as err:', '        except ZeroDivisionError as err:')],
     [REFUSED]),
    ('MS24', 'the seeded workspace is the project root', [(MGR,
     '        return (self.node.seed_workspace(project_id, e.id, base, branch, workdirs=workdirs),\n'
     '                branch, base)',
     '        return (root, branch, base)')], [CHAIN, FIRST]),
    ('MS25', 'a seeded name is checked only for its shape, not for git or device names', [(SEED,
     "        if refused_component(part):\n            raise SeedError('refused path segment: %s' % value)",
     "        if part in ('', '.'):\n            raise SeedError('refused path segment: %s' % value)")],
     [T + 'test_a_name_git_or_windows_treats_specially_is_never_seeded_or_imported']),
    ('MS26', 'the ancestors of the destination are not checked for aliases', [(SEED,
     '    root = _root(dest_root)\n    _ancestors(root)\n', '    root = _root(dest_root)\n')],
     [T + 'test_a_junction_above_the_destination_is_refused_before_anything_is_written']),
    ('MS27', 'the ancestors of a source are not checked for aliases', [(SEED,
     '        _ancestors(src)\n', '')],
     [T + 'test_a_junction_above_the_import_source_is_refused',
      T + 'test_a_junction_between_the_source_root_and_the_file_is_refused']),
    ('MS28', 'only the parent directory is checked for an alias', [(SEED,
     '        path, ancestor = ancestor, os.path.dirname(ancestor)', '        break')],
     [T + 'test_a_junction_above_the_destination_is_refused_before_anything_is_written']),
    ('MS29', 'any failure reading the mission branch falls back to the project HEAD', [(LOCAL,
     "        except NoSuchRevision:\n            try:        # a ref naming",
     "        except StoreError:\n            try:        # a ref naming")],
     [R + 'test_only_an_absent_mission_branch_falls_back_to_head']),
    ('MS30', 'a mission branch naming a missing object is read as absent', [(LOCAL,
     "            raise StoreError('the mission branch %s names no commit' % mission_branch)",
     "            return 'HEAD', LocalNode.store_resolve_base(root, 'HEAD', workdirs=workdirs)")],
     [R + 'test_a_corrupt_mission_branch_is_refused_not_read_as_absent']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
