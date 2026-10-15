"""Commands and queries: the only callers of the writer (target-architecture §3).

P2 holds exactly what its acceptance needs — registering a principal and
creating a mission (G1, G4 at the persistence level). P3 adds `lifecycle`
(the guarded, trigger-named transition over the P2 primitive) and the mission
actions (`commands.Missions`). P3.5 adds `work` (plan, task, execution,
verification and review commands) and reads the guard snapshot from their rows
(`commands.persisted_facts`). The rest of the command surface arrives with the
phase that owns it.
"""
