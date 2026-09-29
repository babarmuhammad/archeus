// The mission inspector (p16-design-gate §6.1–§6.7): Outcome · Plan · Now ·
// Evidence · Why · Timeline · Relations. Every tab reads its own rows; the
// header's actions are offered only from states whose table has the trigger,
// and Core judges every press.
import { useState } from 'react';
import {
  api,
  type Checkpoint,
  type ContextPackage,
  type Execution,
  type ExecutionList,
  type Mission,
  type MissionPlan,
  type PolicyDecisionList,
  type ReviewList,
  type RouteDecisionList,
  type SessionList,
  type Task,
  type Timeline as TimelineT,
  type VerificationList,
} from '../api/generated';
import { send } from '../data/core';
import { useRead } from '../data/cache';
import { executionEdges, missionEdges, taskDependencies, verificationEdges } from '../graph/relations';
import { INSPECTOR_TABS, TAB_LABEL, objectHref } from '../nav/destinations';
import { ago, explainState, offers, statusLine } from '../state/present';
import { Relations } from '../components/Relations';
import { ActionButton, Empty, Fresh, KV, Loadable, Resources, Section, StateBadge, Tabs } from '../components/ui';

export function MissionInspector({ id, tab, onTab }: { id: string; tab?: string; onTab: (t: string) => void }) {
  const m = useRead<Mission>(`/v1/missions/${id}`);
  const plan = useRead<MissionPlan>(`/v1/missions/${id}/plan`);
  const current = tab && INSPECTOR_TABS.mission.includes(tab) ? tab : 'outcome';
  return (
    <Loadable snap={m} what="the mission">
      {(mission) => (
        <div className="inspector-body">
          <header className="insp-head">
            <h1 tabIndex={-1}>{mission.title}</h1>
            <div className="meta">
              <StateBadge machine="mission" state={mission.state} />
              <span>{statusLine({ ...mission, pending_approval: mission.pending_approval_id ? { kind: 'plan' } : null, tasks: plan.data?.plan?.tasks }) || null}</span>
              {mission.project_id ? <a href={`#/world/${mission.project_id}`}>project</a> : null}
              <Fresh snap={m} />
            </div>
            <MissionActions mission={mission} />
          </header>
          <Tabs label="Mission" current={current} onSelect={onTab} tabs={INSPECTOR_TABS.mission.map((t) => ({ id: t, label: TAB_LABEL[t] }))} />
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="panel">
            {current === 'outcome' && <Outcome m={mission} />}
            {current === 'plan' && <PlanTab snap={plan} />}
            {current === 'now' && <NowTab plan={plan.data} />}
            {current === 'evidence' && <Evidence id={id} m={mission} />}
            {current === 'why' && <Why m={mission} plan={plan.data} />}
            {current === 'timeline' && <TimelineTab id={id} />}
            {current === 'relations' && <MissionRelations m={mission} plan={plan.data} />}
          </div>
        </div>
      )}
    </Loadable>
  );
}

function MissionActions({ mission }: { mission: Mission }) {
  const reread = [`/v1/missions/${mission.id}`, '/v1/missions', '/v1/attention'];
  const v = { expected_version: mission.version };
  return (
    <div className="row actions">
      {offers('mission', mission.state, 'pause') ? (
        <ActionButton label="Pause" scope="control" run={(key) => api.pauseMission(send(), mission.id, { idempotency_key: key, ...v })} reread={reread} />
      ) : null}
      {offers('mission', mission.state, 'resume', 'unblock') ? (
        <ActionButton label="Resume" scope="control" kind="primary" run={(key) => api.resumeMission(send(), mission.id, { idempotency_key: key, ...v })} reread={reread} />
      ) : null}
      {mission.state === 'EXECUTING' || mission.state === 'PAUSED' ? (
        <ActionButton
          label="Stop"
          scope="control"
          kind="danger"
          confirm="Stop every execution of this mission now. Their processes are killed; the mission waits for you, blocked, and resuming it dispatches the work again."
          run={(key) => api.stopMission(send(), mission.id, { idempotency_key: key })}
          reread={reread}
        />
      ) : null}
    </div>
  );
}

function Outcome({ m }: { m: Mission }) {
  const crit = (m.success_criteria as { text: string; check: string; origin?: string }[] | undefined) ?? [];
  const reqs = (m.requirements as { text: string; origin?: string }[] | undefined) ?? [];
  const prefs = m.resource_preferences as Record<string, unknown> | undefined;
  return (
    <>
      <Section title="Objective">
        <p className="prose">{m.objective}</p>
      </Section>
      <Section title="Success criteria">
        {crit.length ? (
          <ul className="list">
            {crit.map((c, i) => (
              <li key={i}>
                {c.text} <span className="tag">{c.check}</span>
                {c.origin === 'inferred' ? <span className="tag inferred">inferred</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No success criteria recorded yet.</Empty>
        )}
      </Section>
      {reqs.length ? (
        <Section title="Requirements">
          <ul className="list">
            {reqs.map((r, i) => (
              <li key={i}>
                {r.text} {r.origin === 'inferred' ? <span className="tag inferred">inferred</span> : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Section title="Scope and control">
        <KV
          rows={[
            ['Origin', `${String(m.origin ?? '—')}`],
            ['Autonomy profile', String(m.autonomy_profile ?? 'the user default')],
            ['Replans allowed', String(m.max_replans ?? '—')],
            ['Mission branch', <span className="mono">{String(m.integration_branch ?? '—')}</span>],
            ['Resource preferences', prefs && Object.keys(prefs).length ? <span className="mono">{JSON.stringify(prefs)}</span> : 'none'],
          ]}
        />
        <ResourcePreferences m={m} />
      </Section>
    </>
  );
}

/** Preferences the router reads (P10): separate harness and account lists and
 * a cost ceiling — never a merged "model" picker; the router still decides. */
function ResourcePreferences({ m }: { m: Mission }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ preferred_harnesses: '', forbidden_harnesses: '', preferred_accounts: '', forbidden_accounts: '', max_cost_band: '' });
  const list = (s: string) => (s.trim() ? s.split(',').map((x) => x.trim()).filter(Boolean) : null);
  if (!open)
    return (
      <button type="button" className="btn link" onClick={() => setOpen(true)}>
        Set routing preferences…
      </button>
    );
  return (
    <form className="form" onSubmit={(e) => e.preventDefault()}>
      <p className="hint">These are preferences for the router (P10). It still checks capability, policy, health and allocation, and records why it chose what it chose.</p>
      {(['preferred_harnesses', 'forbidden_harnesses', 'preferred_accounts', 'forbidden_accounts'] as const).map((k) => (
        <label key={k}>
          {k.replace('_', ' ')} (comma-separated ids)
          <input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
        </label>
      ))}
      <label>
        Cost ceiling
        <select value={f.max_cost_band} onChange={(e) => setF({ ...f, max_cost_band: e.target.value })}>
          <option value="">unchanged</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
      </label>
      <ActionButton
        label="Save preferences"
        scope="admin"
        run={(key) =>
          api.setMissionResources(send(), m.id, {
            idempotency_key: key,
            preferred_harnesses: list(f.preferred_harnesses),
            forbidden_harnesses: list(f.forbidden_harnesses),
            preferred_accounts: list(f.preferred_accounts),
            forbidden_accounts: list(f.forbidden_accounts),
            max_cost_band: (f.max_cost_band || null) as 'low' | 'medium' | 'high' | null,
          })
        }
        reread={[`/v1/missions/${m.id}`]}
        onDone={() => setOpen(false)}
      />
    </form>
  );
}

/** Plan versions as a lineage; tasks by wave. Proposed, approved and running
 * are three facts, never one badge. */
function PlanTab({ snap }: { snap: ReturnType<typeof useRead<MissionPlan>> }) {
  return (
    <Loadable snap={snap} what="the plan">
      {(mp) => {
        if (!mp.plan) return <Empty>No plan yet: the mission is still being understood or planned.</Empty>;
        const p = mp.plan;
        const byKey = Object.fromEntries(p.tasks.map((t) => [t.key, t]));
        return (
          <>
            <Section title={`Plan v${p.plan_version}`}>
              <div className="facts">
                <StateBadge machine="plan" state={p.state} />
                {p.estimated_cost ? <span className="tag">cost band: {p.estimated_cost}</span> : null}
                <span className="tag">{p.in_force ? 'in force' : 'not in force'}</span>
                {!p.current ? <span className="tag stale">planned from context that has changed: {p.current_why}</span> : null}
              </div>
              {typeof p.summary === 'string' ? <p className="provenance">Summary (planner, model-written): {p.summary}</p> : null}
              <ol className="waves">
                {p.waves.map((wave, i) => (
                  <li key={i}>
                    <span className="wave-label">Step {i + 1}{wave.length > 1 ? ` · ${wave.length} in parallel` : ''}</span>
                    <ul>
                      {wave.map((k) => (
                        <TaskRow key={k} t={byKey[k]} byKey={byKey} />
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
              {(p.serialised ?? []).length ? (
                <p className="hint">
                  Added by Core so tasks that may touch the same files run one after the other:{' '}
                  {(p.serialised ?? []).map((s) => `${String(s.after)} → ${String(s.task)}`).join(', ')}
                </p>
              ) : null}
            </Section>
            <Section title="Versions">
              <ol className="versions" reversed>
                {[...mp.versions].reverse().map((v) => (
                  <li key={v.id} data-inactive={v.state === 'SUPERSEDED' || v.state === 'REJECTED' ? '' : undefined}>
                    <a href={objectHref('plan', v.id)}>v{v.plan_version}</a> <StateBadge machine="plan" state={v.state} />
                    {v.supersedes_plan_id ? <span className="hint"> replaces v{mp.versions.find((x) => x.id === v.supersedes_plan_id)?.plan_version ?? '?'}</span> : null}
                    {v.id === p.id && p.in_force ? <span className="tag">in force</span> : null}
                  </li>
                ))}
              </ol>
            </Section>
          </>
        );
      }}
    </Loadable>
  );
}

function TaskRow({ t, byKey }: { t: Task | undefined; byKey: Record<string, Task> }) {
  if (!t) return null;
  const deps = taskDependencies(t, byKey);
  return (
    <li className="task" data-task={t.key}>
      <StateBadge machine="task" state={t.state} />
      <span className="mono">{t.key}</span> <span>{t.title}</span> <span className="tag">{t.kind}</span>
      {deps.length ? <span className="hint"> after {(t.depends_on ?? []).join(', ')}</span> : null}
      {t.integration_state ? <span className="tag">merge: {t.integration_state.toLowerCase()}</span> : null}
    </li>
  );
}

/** Tasks in flight and their executions (§6.6). */
function NowTab({ plan }: { plan?: MissionPlan }) {
  const tasks = plan?.plan?.tasks ?? [];
  const live = tasks.filter((t) => ['ROUTING', 'RUNNING', 'AWAITING_APPROVAL', 'VERIFYING', 'PAUSED', 'BLOCKED'].includes(t.state));
  const shown = live.length ? live : tasks;
  if (!shown.length) return <Empty>Nothing is running: there is no plan in force yet.</Empty>;
  return (
    <>
      {!live.length ? <p className="hint">Nothing is running now. Every task of the plan in force:</p> : null}
      {shown.map((t) => (
        <Section key={t.id} title={`${t.key} · ${t.title}`}>
          <StateBadge machine="task" state={t.state} />
          <Executions taskId={t.id} />
        </Section>
      ))}
    </>
  );
}

function Executions({ taskId }: { taskId: string }) {
  const ex = useRead<ExecutionList>(`/v1/tasks/${taskId}/executions`);
  return (
    <Loadable snap={ex} what="the executions">
      {(l) =>
        l.executions.length ? (
          <ul className="executions">
            {[...l.executions].reverse().map((e) => (
              <ExecutionRow key={e.id} e={e} />
            ))}
          </ul>
        ) : (
          <Empty>No attempt yet.</Empty>
        )
      }
    </Loadable>
  );
}

export function ExecutionRow({ e }: { e: Execution }) {
  return (
    <li className="execution" data-execution={e.id}>
      <a href={objectHref('execution', e.id)}>attempt {e.attempt}</a> <StateBadge machine="execution" state={e.state} />
      <Resources r={e} />
      {e.handoff_from ? <span className="hint">continues <a href={objectHref('execution', String(e.handoff_from))}>an earlier execution</a> (hand-off)</span> : null}
      {e.stop_reason || e.exit_reason ? <span className="hint">{String(e.stop_reason ?? e.exit_reason)}</span> : null}
    </li>
  );
}

function Evidence({ id, m }: { id: string; m: Mission }) {
  const v = useRead<VerificationList>(`/v1/missions/${id}/verifications`);
  const r = useRead<ReviewList>(`/v1/missions/${id}/reviews`);
  return (
    <>
      <Section title="Verification">
        <Loadable snap={v} what="the verifications">
          {(l) =>
            l.verifications.length ? (
              <ul className="verifications">
                {l.verifications.map((x) => (
                  <li key={x.id}>
                    <StateBadge machine="verification" state={x.state} /> <a href={objectHref('verification', x.id)}>{x.subject.kind === 'mission' ? `criterion ${String(x.criterion ?? '')}` : 'task check'}</a>{' '}
                    <span className="tag">{x.verifier}</span>
                    {x.revision ? <span className="mono"> at {String(x.revision).slice(0, 10)}</span> : null}
                    <ul className="checks">
                      {x.checks.map((c, i) => (
                        <li key={i} data-result={c.result}>
                          <span aria-hidden="true">{c.result === 'pass' ? '✓' : c.result === 'fail' ? '✕' : '!'}</span> {c.name} — {c.result}
                          {c.exit_code != null ? ` (exit ${c.exit_code})` : ''}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nothing has been verified yet.</Empty>
            )
          }
        </Loadable>
      </Section>
      <Section title="Review">
        <Loadable snap={r} what="the reviews">
          {(l) =>
            l.reviews.length ? (
              <ul className="reviews">
                {l.reviews.map((x) => (
                  <li key={x.id}>
                    <StateBadge machine="review" state={x.state} /> {x.reviewer} · verdict {x.verdict ?? '—'}
                    {!x.independent ? <p className="hint">Reviewed on the same resource — no other was free.</p> : null}
                    {(x.requirements_missing as string[] | undefined)?.length ? <p>Missing: {(x.requirements_missing as string[]).join('; ')}</p> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No review yet.</Empty>
            )
          }
        </Loadable>
        {m.state === 'REVIEWING' ? <UserReview id={id} /> : null}
      </Section>
    </>
  );
}

function UserReview({ id }: { id: string }) {
  const [note, setNote] = useState('');
  const reread = [`/v1/missions/${id}`, '/v1/missions', '/v1/attention'];
  return (
    <div className="form">
      <p className="hint">Your review is recorded as a review of its own; accepting completes the mission (P13).</p>
      <label>
        Note
        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <div className="row">
        <ActionButton label="Accept result" scope="approve" kind="primary" run={(key) => api.reviewMission(send(), id, { verdict: 'accept', note, idempotency_key: key })} reread={reread} />
        <ActionButton label="Request changes" scope="approve" run={(key) => api.reviewMission(send(), id, { verdict: 'changes_requested', note, idempotency_key: key })} reread={reread} />
        <ActionButton label="Reject" scope="approve" kind="danger" run={(key) => api.reviewMission(send(), id, { verdict: 'reject', note, idempotency_key: key })} reread={reread} />
      </div>
    </div>
  );
}

function Why({ m, plan }: { m: Mission; plan?: MissionPlan }) {
  const pd = useRead<PolicyDecisionList>(`/v1/policy-decisions?mission=${m.id}`);
  const rd = useRead<RouteDecisionList>(`/v1/route-decisions?source=${m.id}`);
  const ctx = m.context_package as ContextPackage | null | undefined;
  const lastPolicy = pd.data?.policy_decisions.at(-1);
  // a task's route explains the work; an own call (a lesson pass after the end) does not
  const lastRoute = rd.data?.route_decisions.filter((d) => (d.subject as { kind?: string } | undefined)?.kind === 'task').at(-1);
  const why = explainState({
    mission: m,
    policy: lastPolicy ? { decision: lastPolicy.decision, reason: lastPolicy.reason } : null,
    route: lastRoute ? { result: lastRoute.result as string | null, explanation: lastRoute.explanation, unblock_at: lastRoute.unblock_at as string | null } : null,
  });
  return (
    <>
      <Section title="Why it is in this state">
        <ul className="list">
          {why.map((w, i) => (
            <li key={i}>
              {w.text} <span className="field">({w.source})</span>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Context used">
        {ctx ? (
          <>
            <p className="hint">
              Package <a href={objectHref('context_package', ctx.id)}>{ctx.id}</a> · as of event {ctx.as_of_seq} · {ctx.budget.used_tokens} of {ctx.budget.limit_tokens} tokens
            </p>
            <table className="grid">
              <thead>
                <tr>
                  <th scope="col">Level</th>
                  <th scope="col">Item</th>
                  <th scope="col">Freshness</th>
                  <th scope="col">Why it was included</th>
                </tr>
              </thead>
              <tbody>
                {ctx.items.map((it, i) => (
                  <tr key={i}>
                    <td>{it.level}</td>
                    <td>
                      <a href={objectHref(it.ref.kind, it.ref.id)}>{it.type}</a> <span className="hint">{it.store}</span>
                    </td>
                    <td data-fresh={it.freshness}>{it.freshness}</td>
                    <td>{it.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {ctx.excluded.length ? (
              <details>
                <summary>{ctx.excluded.length} excluded</summary>
                <ul className="list">
                  {ctx.excluded.map((x, i) => (
                    <li key={i}>
                      {x.ref.kind} {x.ref.id} ({x.freshness}): {x.reason}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            {ctx.conflicts.map((c, i) => (
              <p key={i} className="warn">
                Conflict ({c.kind}): {c.reason} — preferred {c.preferred}
              </p>
            ))}
          </>
        ) : (
          <Empty>No context package recorded yet.</Empty>
        )}
      </Section>
      <Section title="Policy decisions">
        <Loadable snap={pd} what="the policy decisions">
          {(l) =>
            l.policy_decisions.length ? (
              <ul className="list">
                {l.policy_decisions.map((d) => (
                  <li key={d.id}>
                    <span className="mono">{d.stage}</span> · <strong>{d.decision}</strong>
                    {d.outcome ? ` (${d.outcome})` : ''} — {d.reason} · <a href={objectHref('policy_decision', d.id)}>record</a>
                    {d.approval_id ? <> · <a href={objectHref('approval', String(d.approval_id))}>its approval</a></> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No policy decision yet.</Empty>
            )
          }
        </Loadable>
      </Section>
      <Section title="Where the work was routed">
        <Loadable snap={rd} what="the route decisions">
          {(l) =>
            l.route_decisions.length ? (
              <ul className="list">
                {l.route_decisions.map((d) => (
                  <li key={d.id}>
                    <a href={objectHref('route_decision', d.id)}>{String(d.purpose ?? (d.subject as { kind?: string })?.kind ?? 'route')}</a> · {String(d.result ?? (d.selected ? 'selected' : 'none'))}
                    <Resources r={d} />
                    <p className="hint">{d.explanation}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nothing was routed yet.</Empty>
            )
          }
        </Loadable>
        {plan?.plan ? null : null}
      </Section>
    </>
  );
}

function TimelineTab({ id }: { id: string }) {
  const [before, setBefore] = useState<number[]>([]);
  return (
    <>
      <TimelinePage id={id} before={undefined} />
      {before.map((b) => (
        <TimelinePage key={b} id={id} before={b} />
      ))}
      <MoreButton id={id} pages={before} onMore={(b) => setBefore([...before, b])} />
    </>
  );
}

function TimelinePage({ id, before }: { id: string; before?: number }) {
  const t = useRead<TimelineT>(`/v1/missions/${id}/timeline?limit=50${before ? `&before=${before}` : ''}`);
  return (
    <Loadable snap={t} what="the timeline">
      {(l) =>
        l.events.length ? (
          <ol className="timeline">
            {l.events.map((e) => (
              <li key={e.seq}>
                <span className="mono seq">{e.seq}</span> <span className="type">{e.type}</span>{' '}
                <a href={objectHref(e.subject.kind, e.subject.id)}>{e.subject.kind}</a>
                {typeof e.payload.reason === 'string' ? <span className="hint"> — {e.payload.reason}</span> : null}
                {typeof e.payload.to === 'string' ? <span className="hint"> → {e.payload.to}</span> : null}
                <span className="age"> {ago(e.at)}</span>
                {e.cause_chain.length ? <span className="hint"> · caused by {e.cause_chain.length} earlier event(s)</span> : null}
              </li>
            ))}
          </ol>
        ) : before ? null : (
          <Empty>No events yet.</Empty>
        )
      }
    </Loadable>
  );
}

function MoreButton({ id, pages, onMore }: { id: string; pages: number[]; onMore: (b: number) => void }) {
  const last = pages.at(-1);
  const t = useRead<TimelineT>(`/v1/missions/${id}/timeline?limit=50${last ? `&before=${last}` : ''}`);
  const nb = t.data?.next_before;
  return nb ? (
    <button type="button" className="btn secondary" onClick={() => onMore(nb)}>
      Load older events
    </button>
  ) : null;
}

function MissionRelations({ m, plan }: { m: Mission; plan?: MissionPlan }) {
  const s = useRead<SessionList>(`/v1/sessions?mission=${m.id}`);
  return <Relations edges={missionEdges(m, plan ?? null, s.data?.sessions ?? [])} />;
}

// ── execution detail (§6.6) ──

export function ExecutionInspector({ id, tab, onTab }: { id: string; tab?: string; onTab: (t: string) => void }) {
  const e = useRead<Execution>(`/v1/executions/${id}`);
  const current = tab && INSPECTOR_TABS.execution.includes(tab) ? tab : 'output';
  return (
    <Loadable snap={e} what="the execution">
      {(x) => (
        <div className="inspector-body">
          <header className="insp-head">
            <h1 tabIndex={-1}>Execution · attempt {x.attempt}</h1>
            <div className="meta">
              <StateBadge machine="execution" state={x.state} />
              <a href={objectHref('mission', x.mission_id, 'now')}>mission</a>
              <Fresh snap={e} />
            </div>
            <Resources r={x} />
            <div className="row actions">
              {['STARTING', 'RUNNING', 'PAUSING', 'HANDING_OFF'].includes(x.state) ? (
                <ActionButton label="Stop" scope="control" kind="danger" confirm="Stop this execution now: its process is killed. The task and mission respond as Core decides (P11)." run={(key) => api.stopExecution(send(), x.id, { idempotency_key: key })} reread={[`/v1/executions/${x.id}`]} />
              ) : null}
              {x.state === 'RUNNING' ? (
                <ActionButton label="Hand off" scope="control" run={(key) => api.handoffExecution(send(), x.id, { idempotency_key: key })} reread={[`/v1/executions/${x.id}`]} />
              ) : null}
            </div>
          </header>
          <Tabs label="Execution" current={current} onSelect={onTab} tabs={INSPECTOR_TABS.execution.map((t) => ({ id: t, label: TAB_LABEL[t] }))} />
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="panel">
            {current === 'output' && <Output id={x.id} />}
            {current === 'checkpoints' && <Checkpoints id={x.id} />}
            {current === 'relations' && <Relations edges={executionEdges(x)} />}
          </div>
        </div>
      )}
    </Loadable>
  );
}

const TAIL = 200;

/** The output tail (D4, D16): read only while this is open; Core redacts it;
 * rendered as text, never as markup. */
function Output({ id }: { id: string }) {
  const out = useRead<{ events: Record<string, unknown>[]; truncated: boolean; available: boolean; next_offset: number }>(`/v1/executions/${id}/stream`);
  return (
    <Loadable snap={out} what="the output">
      {(o) =>
        !o.available ? (
          <Empty>No output yet: the process has not started, or its harness is not available here.</Empty>
        ) : (
          <>
            {o.truncated || o.events.length > TAIL ? <p className="hint">Showing the last {Math.min(TAIL, o.events.length)} events.</p> : null}
            <ol className="output" aria-label="Execution output">
              {o.events.slice(-TAIL).map((ev, i) => (
                <li key={i} data-type={String(ev.type)}>
                  <span className="type">{String(ev.type)}</span> <span className="text">{typeof ev.text === 'string' ? ev.text : JSON.stringify(ev)}</span>
                </li>
              ))}
            </ol>
          </>
        )
      }
    </Loadable>
  );
}

function Checkpoints({ id }: { id: string }) {
  const c = useRead<{ checkpoints: Checkpoint[] }>(`/v1/executions/${id}/checkpoints`);
  return (
    <Loadable snap={c} what="the checkpoints">
      {(l) =>
        l.checkpoints.length ? (
          <ul className="list">
            {l.checkpoints.map((k) => (
              <li key={k.id}>
                <KV
                  rows={[
                    ['Trigger', k.trigger],
                    ['Next action', k.next_action ?? '—'],
                    ['Files changed', ((k.files_changed as string[] | undefined) ?? []).join(', ') || '—'],
                    ['Open problems', ((k.open_problems as string[] | undefined) ?? []).join('; ') || '—'],
                    ['As of event', String(k.as_of_seq ?? '—')],
                  ]}
                />
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No checkpoint: one is derived when an execution that ran ends.</Empty>
        )
      }
    </Loadable>
  );
}

export { verificationEdges };
