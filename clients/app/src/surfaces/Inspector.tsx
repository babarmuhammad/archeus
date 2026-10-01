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
import { Details, Fresh, KV, Loadable, Prose, RefLabel, Resources, Section, StateBadge, Tabs, useMe } from '../components/ui';
import { firedText, inline, technical, words } from '../state/present';

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
        <h1 tabIndex={-1}>{words(kind)}</h1>
        <Details rows={[[`${words(kind)} id`, id]]} />
        <p className="unavailable">This client has no view of a {kind.replace('_', ' ')} yet.</p>
      </div>
    );
  return <RowInspector kind={kind} id={id} tab={tab} onTab={onTab} />;
}

function RowInspector({ kind, id, tab, onTab }: { kind: string; id: string; tab?: string; onTab: (t: string) => void }) {
  const snap = useRead<Record<string, unknown>>(PATH[kind](id));
  const { me } = useMe();
  const tabs = INSPECTOR_TABS[kind] ?? ['detail'];
  const current = tab && tabs.includes(tab) ? tab : tabs[0];
  return (
    <Loadable snap={snap} what={`the ${kind.replace('_', ' ')}`}>
      {(row) => (
        <div className="inspector-body">
          <header className="insp-head">
            <h1 tabIndex={-1}>{TITLE[kind] ?? words(kind)}</h1>
            <div className="meta">
              {typeof row.state === 'string' && MACHINE[kind] ? <StateBadge machine={MACHINE[kind]} state={row.state} /> : null}
              <Fresh snap={snap} />
            </div>
            <Details rows={[[`${TITLE[kind] ?? words(kind)} id`, id], ...(DETAIL[kind] ? IDS[kind]?.(row) ?? [] : technical(row)[1].filter(([k]) => k !== 'Id'))]} />
          </header>
          {tabs.length > 1 ? <Tabs label={kind} current={current} onSelect={onTab} tabs={tabs.map((t) => ({ id: t, label: TAB_LABEL[t] }))} /> : null}
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={tabs.length > 1 ? `tab-${current}` : undefined} className="panel">
            {current === 'relations' ? <Relations of={{ kind, id }} edges={EDGES[kind]?.(row) ?? []} /> : DETAIL[kind]?.(row, me?.principal_id) ?? <Fields row={row} />}
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

/** The identifiers each dedicated view keeps out of its default reading, by
 * what they name. */
const IDS: Record<string, (r: Record<string, unknown>) => [string, string | null | undefined][]> = {
  plan: (r) => [['Mission id', r.mission_id as string], ['Replaces plan id', r.supersedes_plan_id as string], ['Plan digest', r.digest as string]],
  verification: (r) => [
    ['Execution id', r.execution_id as string],
    ['Plan id', r.plan_id as string],
    ['Revision checked (git)', r.revision as string],
    ['Decided by (principal id)', r.decided_by as string],
  ],
  route_decision: (r) => [
    ['Selected resource', r.selected as string],
    ['Account id', r.account_id as string],
    ['Fell back from', ((r.fallback_from as string[] | undefined) ?? []).join(', ')],
  ],
  automation_run: (r) => {
    const x = r as unknown as AutomationExplanation;
    return [['Automation id', String(x.automation.id ?? '')], ['Mission id', x.mission ? String(x.mission.id) : null]];
  },
};

const DETAIL: Record<string, (r: Record<string, unknown>, me?: string) => ReactNode> = {
  plan: (r) => {
    const p = r as unknown as Plan;
    return (
      <>
        <KV rows={[['Version', `v${p.plan_version}`], ['In force', p.in_force ? 'yes' : 'no'], ['Cost band', String(p.estimated_cost ?? '—')]]} />
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
  verification: (r, me) => {
    const v = r as unknown as Verification & { evidence?: { check: string; available: boolean }[] };
    return (
      <>
        <KV
          rows={[
            ['Verifier', v.verifier],
            ['Of execution', v.execution_id ? <a href={objectHref('execution', v.execution_id)}><RefLabel kind="execution" id={v.execution_id} /></a> : 'none recorded'],
            ['Decided by', !v.decided_by ? '—' : v.decided_by === me ? 'you, on this client' : 'another client'],
          ]}
        />
        <ul className="checks">
          {v.checks.map((c, i) => (
            <li key={i} data-result={c.result}>
              {c.name}: {c.result} {c.detail ? <>— <Prose text={c.detail} /></> : ''} {v.evidence?.find((e) => e.check === c.name)?.available ? '(evidence kept)' : '(no evidence file)'}
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
        <KV rows={[['Result', String(d.result ?? '—')], ['Fell back', ((d.fallback_from as string[] | undefined) ?? []).length ? 'yes — what it fell back from is in Details' : 'no'], ['Decided by', String(d.decided_by ?? '—')]]} />
        <p className="prose"><Prose text={d.explanation} /></p>
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
                  <td>
                    {String(c.label ?? c.harness ?? '—')}
                    {c.harness && c.label !== c.harness ? <span className="hint"> on {String(c.harness)}</span> : null}
                  </td>
                  <td>{String(c.eliminated_at_step ?? c.eliminated_at ?? 'kept')}</td>
                  <td>{c.reason ? <Prose text={String(c.reason)} /> : '—'}</td>
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
          <KV rows={[['Depth', String(x.run.depth)], ['Reason', x.run.reason ? <Prose text={x.run.reason} /> : '—'], ['Why', firedText(x.why as Parameters<typeof firedText>[0])]]} />
        </Section>
        <Section title="What it caused">{x.mission ? <a href={objectHref('mission', String(x.mission.id))}>{String(x.mission.title ?? 'its mission')}</a> : <p>No mission.</p>}</Section>
      </>
    );
  },
};

/** A row with no dedicated view: its fields as words, nested values as
 * nested lists; its identifiers are in the header's Details. */
function Fields({ row }: { row: Record<string, unknown> }) {
  return <Value v={technical(row)[0]} />;
}

function Value({ v }: { v: unknown }): ReactNode {
  if (Array.isArray(v) && v.some((x) => x && typeof x === 'object'))
    return (
      <ol className="list">
        {v.map((x, i) => (
          <li key={i}>
            <Value v={x} />
          </li>
        ))}
      </ol>
    );
  if (v && typeof v === 'object' && !Array.isArray(v)) return <KV rows={Object.entries(v).map(([k, x]) => [words(k), <Value v={x} />])} />;
  return typeof v === 'string' && v ? <Prose text={v} /> : inline(v);
}
