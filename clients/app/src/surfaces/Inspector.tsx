// The inspector (p16-design-gate §4.1): one per object kind, opened by a deep
// link `#/o/<kind>/<id>` over whichever destination the user was on. Kinds
// without a dedicated view show their row's fields as Core returned them.
import type { ReactNode } from 'react';
import type { AutomationExplanation, Plan, RouteDecision, Verification } from '../api/generated';
import { useRead } from '../data/cache';
import { planEdges, runEdges, verificationEdges } from '../graph/relations';
import { INSPECTOR_TABS, TAB_LABEL, objectHref } from '../nav/destinations';
import { ApprovalCard } from './Attention';
import { SessionInspector } from './Control';
import { ExecutionInspector, MissionInspector } from './Mission';
import { KnowledgeInspector } from './World';
import { Relations } from '../components/Relations';
import { Fresh, KV, Loadable, Resources, Section, StateBadge, Tabs } from '../components/ui';

const PATH: Record<string, (id: string) => string> = {
  plan: (id) => `/v1/plans/${id}`,
  verification: (id) => `/v1/verifications/${id}`,
  route_decision: (id) => `/v1/route-decisions/${id}`,
  policy_decision: (id) => `/v1/policy-decisions/${id}`,
  context_package: (id) => `/v1/context/${id}`,
  automation_run: (id) => `/v1/automation-runs/${id}`,
  project: (id) => `/v1/projects/${id}`,
  repository: (id) => `/v1/repositories/${id}/inspections`,
};

export function Inspector({ kind, id, tab, onTab }: { kind: string; id: string; tab?: string; onTab: (t: string) => void }) {
  if (kind === 'mission') return <MissionInspector id={id} tab={tab} onTab={onTab} />;
  if (kind === 'execution') return <ExecutionInspector id={id} tab={tab} onTab={onTab} />;
  if (kind === 'session') return <SessionInspector id={id} tab={tab} onTab={onTab} />;
  if (kind === 'knowledge_item') return <KnowledgeInspector id={id} tab={tab} onTab={onTab} />;
  if (kind === 'approval')
    return (
      <div className="inspector-body">
        <h1 tabIndex={-1}>Approval</h1>
        <ApprovalCard id={id} />
      </div>
    );
  if (!PATH[kind])
    return (
      <div className="inspector-body">
        <h1 tabIndex={-1}>
          {kind.replace('_', ' ')} <span className="mono">{id}</span>
        </h1>
        <p className="unavailable">This client has no view of a {kind.replace('_', ' ')} yet.</p>
      </div>
    );
  return <RowInspector kind={kind} id={id} tab={tab} onTab={onTab} />;
}

function RowInspector({ kind, id, tab, onTab }: { kind: string; id: string; tab?: string; onTab: (t: string) => void }) {
  const snap = useRead<Record<string, unknown>>(PATH[kind](id));
  const tabs = INSPECTOR_TABS[kind] ?? ['detail'];
  const current = tab && tabs.includes(tab) ? tab : tabs[0];
  return (
    <Loadable snap={snap} what={`the ${kind.replace('_', ' ')}`}>
      {(row) => (
        <div className="inspector-body">
          <header className="insp-head">
            <h1 tabIndex={-1}>{TITLE[kind] ?? kind.replace('_', ' ')}</h1>
            <div className="meta">
              {typeof row.state === 'string' && MACHINE[kind] ? <StateBadge machine={MACHINE[kind]} state={row.state} /> : null}
              <span className="mono">{id}</span>
              <Fresh snap={snap} />
            </div>
          </header>
          {tabs.length > 1 ? <Tabs label={kind} current={current} onSelect={onTab} tabs={tabs.map((t) => ({ id: t, label: TAB_LABEL[t] }))} /> : null}
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={tabs.length > 1 ? `tab-${current}` : undefined} className="panel">
            {current === 'relations' ? <Relations edges={EDGES[kind]?.(row) ?? []} /> : DETAIL[kind]?.(row) ?? <Fields row={row} />}
          </div>
        </div>
      )}
    </Loadable>
  );
}

const TITLE: Record<string, string> = {
  plan: 'Plan version',
  verification: 'Verification',
  route_decision: 'Route decision',
  policy_decision: 'Policy decision',
  context_package: 'Context package',
  automation_run: 'Automation run',
};

const MACHINE: Record<string, string> = { plan: 'plan', verification: 'verification', automation_run: 'automation_run' };

const EDGES: Record<string, (r: Record<string, unknown>) => ReturnType<typeof planEdges>> = {
  plan: planEdges,
  verification: verificationEdges,
  automation_run: (r) => runEdges((r as unknown as AutomationExplanation).run as unknown as Record<string, unknown>),
};

const DETAIL: Record<string, (r: Record<string, unknown>) => ReactNode> = {
  plan: (r) => {
    const p = r as unknown as Plan;
    return (
      <>
        <KV rows={[['Version', `v${p.plan_version}`], ['In force', String(p.in_force)], ['Cost band', String(p.estimated_cost ?? '—')], ['Digest', <span className="mono">{String(p.digest ?? '—')}</span>]]} />
        <ul className="list">
          {p.tasks.map((t) => (
            <li key={t.id}>
              <StateBadge machine="task" state={t.state} /> <span className="mono">{t.key}</span> {t.title}
            </li>
          ))}
        </ul>
      </>
    );
  },
  verification: (r) => {
    const v = r as unknown as Verification & { evidence?: { check: string; available: boolean }[] };
    return (
      <>
        <KV rows={[['Verifier', v.verifier], ['Revision checked', <span className="mono">{String(v.revision ?? '—')}</span>], ['Of execution', v.execution_id ? <a href={objectHref('execution', v.execution_id)}>{v.execution_id}</a> : 'none recorded'], ['Decided by', String(v.decided_by ?? '—')]]} />
        <ul className="checks">
          {v.checks.map((c, i) => (
            <li key={i} data-result={c.result}>
              {c.name}: {c.result} {c.detail ? `— ${c.detail}` : ''} {v.evidence?.find((e) => e.check === c.name)?.available ? '(evidence kept)' : '(no evidence file)'}
            </li>
          ))}
        </ul>
      </>
    );
  },
  route_decision: (r) => {
    const d = r as unknown as RouteDecision;
    return (
      <>
        <Resources r={d} />
        <KV rows={[['Result', String(d.result ?? '—')], ['Fell back from', String(d.fallback_from ?? '—')], ['Decided by', String(d.decided_by ?? '—')]]} />
        <p className="prose">{d.explanation}</p>
        <Section title="Candidates">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">Candidate</th>
                <th scope="col">Eliminated at</th>
                <th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody>
              {d.candidates.map((c, i) => (
                <tr key={i}>
                  <td className="mono">{JSON.stringify(c.resource ?? c.candidate ?? c)}</td>
                  <td>{String(c.eliminated_at_step ?? c.eliminated_at ?? 'kept')}</td>
                  <td>{String(c.reason ?? '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      </>
    );
  },
  automation_run: (r) => {
    const x = r as unknown as AutomationExplanation;
    return (
      <>
        <Section title="Triggering event">
          {x.event ? <KV rows={[['Type', String(x.event.type)], ['Event', String(x.event.seq)], ['Caused by', `${((x.event.cause_chain as string[]) ?? []).length} earlier event(s)`]]} /> : <p>The event is no longer kept.</p>}
        </Section>
        <Section title="The run">
          <StateBadge machine="automation_run" state={x.run.state} />
          <KV rows={[['Depth', String(x.run.depth)], ['Reason', String(x.run.reason ?? '—')], ['Why', <span className="mono">{JSON.stringify(x.why)}</span>]]} />
        </Section>
        <Section title="What it caused">{x.mission ? <a href={objectHref('mission', String(x.mission.id))}>{String(x.mission.title ?? x.mission.id)}</a> : <p>No mission.</p>}</Section>
      </>
    );
  },
};

function Fields({ row }: { row: Record<string, unknown> }) {
  return <KV rows={Object.entries(row).map(([k, v]) => [k, <span className="mono">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>])} />;
}
