"""The plan engine (P8; p8-design-gate): mission -> validated, immutable PlanVersion.

`validate` is pure (the graph, coverage, cost band, serialisation, digest),
`planner` holds `plan.v1` and resolves a model's answer, `worker` is the outbox
consumer that runs a planning round. Nothing here authorises, routes, executes,
verifies or reviews: those are P9-P13.
"""
