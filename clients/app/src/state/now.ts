// P19.5 R8: what Now composes from Core's reads (ADR-0027 §4-5, rulebook §6
// O-4-O-6, §9). Every word comes from a count or from Core's own records, and
// the live map holds live work only: the active missions and the attempts
// Core's `/v1/status` lists as live, each from the graph read around its mission.
import { paths, SETTLED, type Approval, type Automation, type KnowledgeItem, type Mission, type RouteDecision } from '../api/generated.ts';
import type { GEdge, GNode, GraphData, Hidden } from '../graph/model.ts';
import { present } from './present.ts';

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** ADR-0027 §5: a state sentence, never a greeting — two counts in words
 * (rulebook §9, Appendix B). */
export function stateSentence(active: number, needsYou: number): string {
  const doing = active ? `Archeus is working on ${count(active, 'mission', 'missions')}.` : 'Archeus is idle.';
  return `${doing} ${needsYou ? `${count(needsYou, 'needs', 'need')} you.` : 'Nothing needs you.'}`;
}

export const activeMissions = (ms: readonly Mission[]): Mission[] => ms.filter((m) => !SETTLED.includes(m.state));

/** Upcoming, step 1 (rulebook §9): approved and planning missions — the
 * states the screen calls Approved and Planning — until Core has schedules
 * (P21). */
export const UPCOMING: readonly string[] = ['approved', 'planning'];
export const upcoming = (ms: readonly Mission[]): Mission[] => ms.filter((m) => UPCOMING.includes(present('mission', m.state).cls));

/** The background automation line (rulebook §9): the enabled ones, which are
 * what watches for its trigger. */
export function automationLine(as: readonly Automation[]): string | null {
  const n = as.filter((a) => a.state === 'ENABLED').length;
  return n ? `${count(n, 'automation', 'automations')} watching` : null;
}

export interface Decided {
  kind: 'approval' | 'route_decision' | 'knowledge_item';
  id: string;
  at: string;
  words: string;
  mission?: string;
}

export const DECISIONS_SHOWN = 5;
const DECISION_WORDS: Record<string, string> = { approve: 'approved', reject: 'rejected', request_changes: 'changes requested' };

/** Recent decisions (rulebook §9, O-6), composed by the client: decided
 * approvals, route decisions that changed a route (a fallback), and confirmed
 * DECISION knowledge — newest first. */
export function recentDecisions(approvals: readonly Approval[], routes: readonly RouteDecision[], knowledge: readonly KnowledgeItem[], n = DECISIONS_SHOWN): Decided[] {
  const out: Decided[] = [
    ...approvals
      .filter((a) => a.decided_at && typeof a.decision === 'string')
      .map((a): Decided => ({ kind: 'approval', id: a.id, at: String(a.decided_at), words: DECISION_WORDS[a.decision as string] ?? String(a.decision), mission: a.mission_id })),
    ...routes.filter((r) => r.result === 'fallback').map((r): Decided => ({ kind: 'route_decision', id: r.id, at: String(r.created_at), words: 'fell back' })),
    ...knowledge
      .filter((k) => k.type === 'DECISION' && k.state === 'CONFIRMED')
      .map((k): Decided => ({ kind: 'knowledge_item', id: k.id, at: String(k.updated_at), words: 'decision' })),
  ];
  return out.sort((a, b) => b.at.localeCompare(a.at)).slice(0, n);
}

// ── the live map (O-4): bounded, live work only ──

export const MAP_CAP = 40;
export const MAP_PATH = 'now:live-map';
export const mapRead = (mission: string) => paths.worldGraph({ focus: `mission:${mission}`, depth: 1, limit: MAP_CAP });

/** The map's seeds: the active missions, at most the cap. */
export const mapSeeds = (ms: readonly Mission[]): string[] => activeMissions(ms).slice(0, MAP_CAP).map((m) => m.id);

/** One picture from the graph reads around each seed: the seed missions and
 * the attempts *live* names, the recorded edges between them, at most
 * MAP_CAP nodes (missions first); what the cap cut is counted, never drawn. */
export function liveMap(seeds: readonly string[], reads: readonly ({ nodes: GNode[]; edges: GEdge[] } | undefined)[], live: ReadonlySet<string>): GraphData {
  const seed = new Set(seeds);
  const found = new Map<string, GNode>();
  const edges = new Map<string, GEdge>();
  for (const r of reads) {
    for (const n of r?.nodes ?? [])
      if (!n.endpoint && ((n.kind === 'mission' && seed.has(n.id)) || (n.kind === 'execution' && live.has(n.id)))) found.set(`${n.kind}:${n.id}`, n);
    for (const e of r?.edges ?? []) edges.set(e.id, e);
  }
  const ranked = [...found.values()].sort((a, b) => Number(b.kind === 'mission') - Number(a.kind === 'mission'));
  const nodes = ranked.slice(0, MAP_CAP);
  const kept = new Set(nodes.map((n) => `${n.kind}:${n.id}`));
  const cut = new Map<string, number>();
  for (const n of ranked.slice(MAP_CAP)) cut.set(n.kind, (cut.get(n.kind) ?? 0) + 1);
  const hidden: Hidden[] = [...cut].map(([kind, c]) => ({ parent: { kind: 'workspace', id: MAP_PATH }, kind, count: c }));
  return {
    nodes,
    edges: [...edges.values()].filter((e) => kept.has(`${e.from.kind}:${e.from.id}`) && kept.has(`${e.to.kind}:${e.to.id}`)),
    hidden,
    truncated: hidden.length > 0,
  };
}
