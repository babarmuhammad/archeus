// Which cached reads a stream frame makes stale (p16-design-gate §14.2).
// Frames carry identities only (ADR-0009): a frame never changes what is on
// screen, it only says which reads to repeat. A subject kind with no rule
// makes nothing stale — a view can be late, never wrong. Pure.

/** Per subject kind, the read paths it can change. `{id}` is the subject's id,
 * `*` one path segment, a trailing `**` any rest (query included). */
export const RULES: Record<string, string[]> = {
  mission: ['/v1/missions**', '/v1/attention', '/v1/digest', '/v1/status**'],
  plan: ['/v1/missions/*/plan', '/v1/missions/*/timeline**', '/v1/plans/{id}', '/v1/missions**'],
  task: ['/v1/missions/*/plan', '/v1/missions/*/timeline**', '/v1/tasks/{id}/executions', '/v1/digest'],
  execution: ['/v1/executions/{id}**', '/v1/tasks/*/executions', '/v1/missions/*/timeline**', '/v1/digest'],
  checkpoint: ['/v1/executions/*/checkpoints'],
  approval: ['/v1/approvals**', '/v1/attention', '/v1/missions**'],
  verification: ['/v1/verifications/{id}', '/v1/missions/*/verifications', '/v1/missions/*/timeline**', '/v1/attention', '/v1/digest'],
  review: ['/v1/missions/*/reviews', '/v1/missions/*/timeline**', '/v1/attention', '/v1/digest'],
  knowledge_item: ['/v1/knowledge**', '/v1/attention'],
  relation: ['/v1/knowledge/**'],
  feedback: ['/v1/knowledge**'],
  meeting: ['/v1/knowledge**'],
  decision: ['/v1/knowledge**'],
  project: ['/v1/projects**', '/v1/status**', '/v1/digest'],
  repository: ['/v1/projects**', '/v1/status**', '/v1/repositories/{id}/**', '/v1/attention', '/v1/digest'],
  repository_inspection: ['/v1/repositories/**', '/v1/projects**'],
  message: ['/v1/conversations/**'],
  idea: ['/v1/ideas**'],
  automation: ['/v1/automations**', '/v1/attention'],
  automation_run: ['/v1/automations**', '/v1/automation-runs/{id}'],
  account: ['/v1/accounts', '/v1/attention'],
  resource_policy: ['/v1/accounts'],
  harness: ['/v1/harnesses'],
  route_decision: ['/v1/route-decisions**'],
  policy_decision: ['/v1/policy-decisions**'],
  policy_rule: ['/v1/policies'],
  provider_terms: ['/v1/provider-terms'],
  session: ['/v1/sessions**'],
  context_package: ['/v1/context/{id}'],
  device: ['/v1/devices', '/v1/sync'],
  user: ['/v1/digest', '/v1/policies'],
  // the e-stop and its re-arm: everything that runs may have moved
  principal: ['/v1/**'],
  execution_node: [],
  model: [],
};

function compile(pattern: string, id: string): RegExp {
  const esc = (s: string) => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
  let rest = pattern;
  let tail = '(\\?.*)?';
  if (rest.endsWith('**')) {
    rest = rest.slice(0, -2);
    tail = '.*';
  }
  const body = rest
    .split('{id}')
    .map((part) => part.split('*').map(esc).join('[^/?]+'))
    .join(esc(id));
  return new RegExp('^' + body + tail + '$');
}

/** A predicate over cache keys (read paths) for one frame. */
export function staleBy(frame: { event: string; data?: unknown }): (path: string) => boolean {
  const subject = (frame.data as { subject?: { kind?: string; id?: string } } | undefined)?.subject;
  const rules = subject?.kind ? RULES[subject.kind] ?? [] : [];
  const rx = rules.map((p) => compile(p, subject?.id ?? ''));
  return (path) => rx.some((r) => r.test(path));
}
