-- 0016: the stored request hash no longer covers a step-up proof (T-107).
--
-- Until now a keyed command's request_hash was a plain sha256 over all of its
-- arguments, `step_up` (a paired device's 6-digit PIN) included, so for a day
-- the PIN could be recovered from the row by trying every value. The hash now
-- leaves proof arguments out (writer.PROOF_ARGS). The rows the three commands
-- that take a proof wrote before this are dropped: they hold a recoverable PIN,
-- and they would no longer match a retry anyway. A retry of one of them across
-- this upgrade runs the command again instead of replaying it.

DELETE FROM idempotency_keys
 WHERE command IN ('archeus.core.application.executions.rearm',
                   'archeus.core.application.authorization.Authorization.decide',
                   'archeus.core.application.authorization.Authorization.decide_by_message');
