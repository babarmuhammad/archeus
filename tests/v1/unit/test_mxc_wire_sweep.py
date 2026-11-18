# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""A restart sweep never reads the journal of a launch that is starting under it: the sweep
and the claim of an execution id are ordered, whatever either reads first."""

import threading

from archeus.node import local

from .test_mxc_wire import args, journal_ops, native_parts, wire  # noqa: F401
from .test_mxc_wire_dupstart import OK, run


def test_a_start_that_begins_during_a_sweep_waits_for_it_and_is_not_quarantined(wire):
    h = wire(**OK)
    real, outcomes, starter = h.journal.journal.journals, [], []

    def journals():
        if not starter:             # the launch begins right after the sweep took its busy set
            starter.append(threading.Thread(target=run, args=(h.launch, h.job, outcomes)))
            starter[0].start()
            starter[0].join(0.5)
        return real()

    h.journal.journal.journals = journals
    local.mxc_reconcile(h.journal, lambda pid: None, lambda execution_id, owner: None)
    starter[0].join(10)
    assert outcomes == ['started']
    assert journal_ops(h.journal) == ['intent', 'ownership']
