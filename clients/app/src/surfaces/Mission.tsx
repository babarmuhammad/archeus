// The mission inspector (p16-design-gate §6.1–§6.7): Outcome · Plan · Now ·
// Evidence · Why · Timeline · Relations. Every tab reads its own rows; the
// header's actions are offered only from states whose table has the trigger,
// and Core judges every press.
import { useEffect, useId, useState, type ReactNode } from 'react';
import {
  paths,
  api,
  TASK_KINDS,
  type Checkpoint,
  type ContextPackage,
  type Execution,
  type ExecutionList,
  type Mission,
  type MissionPlan,
  type PlanTaskSpec,
  type PolicyDecisionList,
  type ReviewList,
  type RouteDecisionList,

  type Task,
  type Timeline as TimelineT,
  type VerificationList,
} from '../api/generated';
import { send } from '../data/core';
import { useRead } from '../data/cache';
import { INSPECTOR_TABS, TAB_LABEL, objectHref } from '../nav/destinations';
import { ago, endReason, ended, explainState, inline, inventoryLines, offers, statusLine, technical } from '../state/present';
import { Relations } from '../components/Relations';
import { Conversation } from './Now';
import { AccountName, ActionButton, Details, Empty, Fresh, KV, Loadable, Prose, RefLabel, Resources, Section, StateBadge, Tabs } from '../components/ui';

export function MissionInspector({ id, tab, onTab }: { id: string; tab?: string; onTab: (t: string) => void }) {
  const m = useRead<Mission>(paths.getMission(id));
  const plan = useRead<MissionPlan>(paths.getMissionPlan(id));
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
            {ended('mission', mission.state) ? null : <Priority mission={mission} />}
            <MissionDetails m={mission} />
          </header>
          <Tabs label="Mission" current={current} onSelect={onTab} tabs={INSPECTOR_TABS.mission.map((t) => ({ id: t, label: TAB_LABEL[t] }))} />
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="panel">
            {current === 'outcome' && <Outcome m={mission} />}
            {current === 'plan' && <PlanTab snap={plan} mission={mission} />}
            {current === 'now' && <NowTab mission={mission} plan={plan.data} />}
            {current === 'evidence' && <Evidence id={id} m={mission} />}
            {current === 'why' && <Why m={mission} plan={plan.data} />}
            {current === 'timeline' && <TimelineTab id={id} />}
            {current === 'relations' && <Relations of={{ kind: 'mission', id: mission.id }} />}
          </div>
        </div>
      )}
    </Loadable>
  );
}

type Prefs = Partial<Record<'preferred_harnesses' | 'forbidden_harnesses' | 'preferred_accounts' | 'forbidden_accounts', string[] | null>> & {
  max_cost_band?: string | null;
  /** the entries a user's message added (P19 B10, ADR-0042 §3) */
  directives?: { key: string; id: string; message_id: string }[];
};

function MissionDetails({ m }: { m: Mission }) {
  const prefs = (m.resource_preferences ?? {}) as Prefs;
  return (
    <Details
      rows={[
        ['Mission id', m.id],
        ['Plan id', m.plan_id],
        ['Project id', m.project_id],
        ['Workspace id', m.workspace_id],
        ['Context package id', m.context_package_id as string | undefined],
        ['Pending approval id', m.pending_approval_id as string | undefined],
        ['Started from (id)', m.origin_ref as string | undefined],
        ['Mission branch (git)', m.integration_branch],
        ['Branch head (git)', m.integration_head],
        ['Preferred account ids', prefs.preferred_accounts],
        ['Avoided account ids', prefs.forbidden_accounts],
      ]}
    />
  );
}

/** The router preferences a mission carries, in words; accounts by label. */
function PrefsText({ p }: { p: Prefs }) {
  const parts: ReactNode[] = [];
  const list = (k: keyof Prefs) => ((p[k] as string[] | null | undefined) ?? []).filter(Boolean);
  const said = (k: string, id: string) => ((p.directives ?? []).some((d) => d.key === k && d.id === id) ? ' (from your message)' : '');
  for (const [k, word] of [['preferred_harnesses', 'prefers'], ['forbidden_harnesses', 'never']] as const)
    for (const h of list(k)) parts.push(`${word} ${h}${said(k, h)}`);
  for (const [k, word] of [['preferred_accounts', 'prefers account'], ['forbidden_accounts', 'never account']] as const)
    for (const a of list(k))
      parts.push(
        <>
          {word} <AccountName id={a} />
          {said(k, a)}
        </>,
      );
  if (p.max_cost_band) parts.push(`cost ceiling ${p.max_cost_band}`);
  if (!parts.length) return <>none</>;
  return (
    <>
      {parts.map((x, i) => (
        <span key={i}>
          {i ? ' · ' : ''}
          {x}
        </span>
      ))}
    </>
  );
}

export function MissionActions({ mission }: { mission: Mission }) {
  const reread = [paths.getMission(mission.id), paths.listMissions(), paths.attentionItems()];
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

/** Reprioritise (P19.5 R10b; D-14, rulebook §46.1): the mission's absolute
 * priority, set by Core's one command. Higher is dispatched first when
 * missions wait for capacity; routing never reads it. Drag and Alt+↑/↓ are a
 * recorded deviation: Core has no relative move. Offered until the mission
 * ends, which is when Core stops accepting it. */
export function Priority({ mission }: { mission: Mission }) {
  const now = String(mission.priority ?? 0);
  const [v, setV] = useState(now);
  const id = useId();
  useEffect(() => setV(now), [now]);
  const whole = /^-?\d+$/.test(v.trim());
  return (
    <div className="priority" data-priority-form="">
      <label htmlFor={id}>Priority</label>
      <input id={id} type="number" step={1} inputMode="numeric" value={v} onChange={(e) => setV(e.target.value)} aria-describedby={id + 'h'} />
      <ActionButton
        label="Set priority"
        scope="control"
        disabled={whole ? null : 'A priority is a whole number.'}
        run={(key) => api.reprioritiseMission(send(), mission.id, { priority: Number(v), expected_version: mission.version, idempotency_key: key })}
        reread={[paths.getMission(mission.id), paths.listMissions(), paths.status()]}
      />
      <p className="hint" id={id + 'h'}>
        Higher is started first when missions wait for capacity. Every mission starts at 0.
      </p>
    </div>
  );
}

function Outcome({ m }: { m: Mission }) {
  const crit = (m.success_criteria as { text: string; check: string; origin?: string }[] | undefined) ?? [];
  const reqs = (m.requirements as { text: string; origin?: string }[] | undefined) ?? [];
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
            ['Resource preferences', <PrefsText p={(m.resource_preferences ?? {}) as Prefs} />],
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
        reread={[paths.getMission(m.id)]}
        onDone={() => setOpen(false)}
      />
    </form>
  );
}

/** Plan versions as a lineage; tasks by wave. Proposed, approved and running
 * are three facts, never one badge. */
function PlanTab({ snap, mission }: { snap: ReturnType<typeof useRead<MissionPlan>>; mission: Mission }) {
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
                {p.edited_by ? <span className="tag">edited by a person</span> : null}
                {!p.current ? <span className="tag stale">planned from context that has changed: <Prose text={p.current_why} /></span> : null}
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
              {p.in_force && p.state === 'PROPOSED' && offers('mission', mission.state, 'request_changes') ? <PlanEditor key={p.id} p={p} mission={mission.id} /> : null}
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

/** The task fields a plan edit carries: the planner's own task shape (P19 S2). */
const SPEC = ['key', 'title', 'kind', 'objective', 'expected_output', 'boundaries', 'depends_on', 'action_classes', 'capabilities_required', 'min_model_tier', 'workspace_mode', 'touches', 'refs', 'serves', 'inputs', 'acceptance', 'estimate'] as const;
type Crit = { text: string; check: 'automatic' | 'human' };

/** Edit the plan awaiting approval (P19 S2; p19-design-gate B4): rename,
 * reorder, describe, set acceptance, add or remove a task, change what it
 * waits for. Saving sends the whole list to Core, which keys it, validates it
 * and decides it as it would a planner's version — and asks again if it must. */
function PlanEditor({ p, mission }: { p: NonNullable<MissionPlan['plan']>; mission: string }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<PlanTaskSpec[]>(() => p.tasks.map((t) => Object.fromEntries(SPEC.filter((k) => t[k] != null).map((k) => [k, t[k]])) as unknown as PlanTaskSpec));
  const [added, setAdded] = useState(0);
  if (!open)
    return (
      <button type="button" className="btn link" onClick={() => setOpen(true)}>
        Edit plan…
      </button>
    );
  const set = (i: number, patch: Partial<PlanTaskSpec>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const move = (i: number, by: number) => {
    const next = [...rows];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    setRows(next);
  };
  const remove = (i: number) => setRows(rows.filter((_, j) => j !== i).map((r) => ({ ...r, depends_on: (r.depends_on ?? []).filter((d) => d !== rows[i].key) })));
  const crits = (r: PlanTaskSpec): Crit[] => r.acceptance ?? [];
  return (
    <form className="form plan-editor" onSubmit={(e) => e.preventDefault()}>
      <p className="hint">Your edit becomes the next version of this plan. Core checks it as it checks the planner's, numbers the tasks in this order, and asks for approval again if the plan still needs it.</p>
      <ol className="list">
        {rows.map((r, i) => (
          <li key={r.key} data-edit-task={r.key}>
            <fieldset>
              <legend>Task {i + 1}</legend>
              <label>
                Title
                <input value={r.title} onChange={(e) => set(i, { title: e.target.value })} />
              </label>
              <label>
                Kind
                <select value={r.kind} onChange={(e) => set(i, { kind: e.target.value as PlanTaskSpec['kind'] })}>
                  {TASK_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Description
                <textarea rows={2} value={r.objective ?? ''} onChange={(e) => set(i, { objective: e.target.value })} />
              </label>
              <fieldset>
                <legend>Acceptance</legend>
                {crits(r).map((c, n) => (
                  <div className="row" key={n}>
                    <input aria-label={`Criterion ${n + 1}`} value={c.text} onChange={(e) => set(i, { acceptance: crits(r).map((x, m) => (m === n ? { ...x, text: e.target.value } : x)) })} />
                    <select aria-label={`How criterion ${n + 1} is checked`} value={c.check} onChange={(e) => set(i, { acceptance: crits(r).map((x, m) => (m === n ? { ...x, check: e.target.value as Crit['check'] } : x)) })}>
                      <option value="automatic">automatic</option>
                      <option value="human">human</option>
                    </select>
                    <button type="button" className="btn link" onClick={() => set(i, { acceptance: crits(r).filter((_, m) => m !== n) })}>
                      Remove criterion
                    </button>
                  </div>
                ))}
                <button type="button" className="btn link" onClick={() => set(i, { acceptance: [...crits(r), { text: '', check: 'automatic' }] })}>
                  Add criterion
                </button>
              </fieldset>
              {rows.length > 1 ? (
                <fieldset>
                  <legend>Waits for</legend>
                  {rows
                    .filter((o) => o.key !== r.key)
                    .map((o) => (
                      <label key={o.key} className="check">
                        <input type="checkbox" checked={(r.depends_on ?? []).includes(o.key)} onChange={(e) => set(i, { depends_on: e.target.checked ? [...(r.depends_on ?? []), o.key] : (r.depends_on ?? []).filter((d) => d !== o.key) })} />
                        {o.title || o.key}
                      </label>
                    ))}
                </fieldset>
              ) : null}
              <div className="row">
                <button type="button" className="btn link" disabled={i === 0} onClick={() => move(i, -1)}>
                  Move up
                </button>
                <button type="button" className="btn link" disabled={i === rows.length - 1} onClick={() => move(i, 1)}>
                  Move down
                </button>
                <button type="button" className="btn link" onClick={() => remove(i)}>
                  Remove task
                </button>
              </div>
            </fieldset>
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="btn link"
        onClick={() => {
          setRows([...rows, { key: `new${added + 1}`, title: '', kind: 'research', objective: '', acceptance: [{ text: '', check: 'automatic' }] }]);
          setAdded(added + 1);
        }}
      >
        Add task
      </button>
      <div className="row">
        <ActionButton
          label="Save plan"
          scope="approve"
          kind="primary"
          run={(key) => api.editPlan(send(), p.id, { tasks: rows, expected_version: p.version, idempotency_key: key })}
          reread={[paths.getMissionPlan(mission), paths.getMission(mission), paths.listApprovals({ mission }), paths.attentionItems()]}
          onDone={() => setOpen(false)}
        />
        <button type="button" className="btn link" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function TaskRow({ t, byKey }: { t: Task | undefined; byKey: Record<string, Task> }) {
  if (!t) return null;
  return (
    <li className="task" data-task={t.key}>
      <StateBadge machine="task" state={t.state} />
      <span className="mono">{t.key}</span> <span>{t.title}</span> <span className="tag">{t.kind}</span>
      {(t.depends_on ?? []).some((k) => byKey[k]) ? <span className="hint"> after {(t.depends_on ?? []).join(', ')}</span> : null}
      {t.integration_state ? <span className="tag">merge: {t.integration_state.toLowerCase()}</span> : null}
    </li>
  );
}

/** Tasks in flight and their executions (§6.6). */
/** The mission's Now tab (P19 S1; p19-design-gate B3, §4.1): its own thread —
 * what it was asked and answered, A-05 travel to a row here — above what is
 * running for it. */
function NowTab({ mission, plan }: { mission: Mission; plan?: MissionPlan }) {
  return (
    <div className="mission-now">
      <Conversation conversation={mission.id} scope=".mission-now" title="This mission's conversation" label="Conversation with Archeus about this mission" />
      <NowWork plan={plan} />
    </div>
  );
}

function NowWork({ plan }: { plan?: MissionPlan }) {
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
  const ex = useRead<ExecutionList>(paths.listTaskExecutions(taskId));
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
    <li className="execution" data-execution={e.id} data-ref={`execution:${e.id}`}>
      <a href={objectHref('execution', e.id)}>attempt {e.attempt}</a> <StateBadge machine="execution" state={e.state} />
      <Resources r={e} />
      {e.handoff_from ? <span className="hint">continuing in a fresh session: it continues <a href={objectHref('execution', String(e.handoff_from))}>an earlier execution</a> (hand-off)</span> : null}
      {endReason(e) ? <span className="err" data-end-reason="">{endReason(e)}</span> : null}
      {e.context ? <span className="hint" data-context={e.context.quality}>context {e.context.quality}</span> : null}
    </li>
  );
}

/** ADR-0047 §9: an execution's context as Core recorded it — the basis, its
 * quality and what is left only when both were measured; unknown is shown as
 * unknown, never as 0. Every word comes from Core. */
function ContextBlock({ x }: { x: Execution }) {
  const c = x.context;
  const n = (v: number | null) => (v === null ? 'unknown' : v.toLocaleString('en'));
  return (
    <KV
      rows={[
        ['Context', <span data-context={c.quality}>{c.quality} — <Prose text={c.summary} /></span>],
        ['Pressure', c.pressure === null ? 'unknown' : c.pressure.toFixed(2)],
        ['Tokens used / window / left', `${n(c.used_tokens)} / ${n(c.window)} / ${n(c.remaining)}`],
        ['Window source', c.window_source],
        ['Usage source', c.usage_source],
        ['Hand-off', x.handoff?.from ? <>continues <a href={objectHref('execution', x.handoff.from)}><RefLabel kind="execution" id={x.handoff.from} /></a> ({x.handoff.count} before it){x.handoff.reason ? <>: <Prose text={x.handoff.reason} /></> : ''}</> : 'none'],
        ['Why', x.why ? <Prose text={x.why} /> : '—'],
      ]}
    />
  );
}

/** P20 (ADR-0049): beside the Why, what this execution's settings sources load
 * and what became of each item, as Core recorded it at the spawn. */
function InventoryBlock({ x }: { x: Execution }) {
  // a label repeats (one row per hook, skill, server…), so rows key by position
  return (
    <dl className="kv" data-inventory="" aria-label="What it inherited from its settings sources">
      {inventoryLines(x.inventory).map(([k, v], i) => (
        <div key={i}>
          <dt>{k}</dt>
          <dd>
            <Prose text={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Evidence({ id, m }: { id: string; m: Mission }) {
  const v = useRead<VerificationList>(paths.listVerifications(id));
  const r = useRead<ReviewList>(paths.listReviews(id));
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
  const reread = [paths.getMission(id), paths.listMissions(), paths.attentionItems()];
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
        <ActionButton
          label="Reject"
          scope="approve"
          kind="danger"
          confirm="Reject this result. The rejection is recorded and cannot be changed; the mission stays in review for you to decide what comes next."
          run={(key) => api.reviewMission(send(), id, { verdict: 'reject', note, idempotency_key: key })}
          reread={reread}
        />
      </div>
    </div>
  );
}

function Why({ m, plan }: { m: Mission; plan?: MissionPlan }) {
  const pd = useRead<PolicyDecisionList>(paths.listPolicyDecisions({ mission: m.id }));
  const rd = useRead<RouteDecisionList>(paths.listRouteDecisions({ source: m.id }));
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
              <Prose text={w.text} /> <span className="field">({w.source})</span>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Context used">
        {ctx ? (
          <>
            <p className="hint">
              <a href={objectHref('context_package', ctx.id)}>The context package</a> · as of event {ctx.as_of_seq} · {ctx.budget.used_tokens} of {ctx.budget.limit_tokens} tokens
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
                    <td><Prose text={it.reason} /></td>
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
                      <RefLabel kind={x.ref.kind} id={x.ref.id} /> ({x.freshness}): <Prose text={x.reason} />
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            {ctx.conflicts.map((c, i) => (
              <p key={i} className="warn">
                Conflict ({c.kind}): <Prose text={c.reason} /> — preferred <Prose text={String(c.preferred)} />
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
                    {d.outcome ? ` (${d.outcome})` : ''} — <Prose text={d.reason} /> · <a href={objectHref('policy_decision', d.id)}>record</a>
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
                    <p className="hint"><Prose text={d.explanation} /></p>
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
  const t = useRead<TimelineT>(paths.missionTimeline(id, { limit: 50, before: before || undefined }));
  return (
    <Loadable snap={t} what="the timeline">
      {(l) =>
        l.events.length ? (
          <ol className="timeline">
            {l.events.map((e) => (
              <li key={e.seq}>
                <span className="mono seq">{e.seq}</span> <span className="type">{e.type}</span>{' '}
                <a href={objectHref(e.subject.kind, e.subject.id)}>{e.subject.kind}</a>
                {typeof e.payload.reason === 'string' ? <span className="hint"> — <Prose text={e.payload.reason} /></span> : null}
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
  const t = useRead<TimelineT>(paths.missionTimeline(id, { limit: 50, before: last || undefined }));
  const nb = t.data?.next_before;
  return nb ? (
    <button type="button" className="btn secondary" onClick={() => onMore(nb)}>
      Load older events
    </button>
  ) : null;
}

// ── execution detail (§6.6) ──

export function ExecutionInspector({ id, tab, onTab }: { id: string; tab?: string; onTab: (t: string) => void }) {
  const e = useRead<Execution>(paths.getExecution(id));
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
            <Details
              rows={[
                ['Execution id', x.id],
                ['Task id', x.task_id],
                ['Mission id', x.mission_id],
                ['Session id', x.session_id as string | undefined],
                ['Account id', x.account_id],
                ['Route decision id', x.route_decision_id as string | undefined],
                ['Policy decision id', x.policy_decision_id as string | undefined],
                ['Continues execution (id)', x.handoff?.from ?? (x.handoff_from as string | undefined)],
                ['Process id', x.pid],
                ['Exit code', x.exit_code as number | undefined],
                ['How it ended (Core)', x.exit_reason],
                ['Why it was stopped (Core)', x.stop_reason],
                ['Failure class (Core)', x.failure as string | undefined],
                ['End-state digest', x.end_state_digest],
              ]}
            />
            {endReason(x) ? (
              <p className="err" data-end-reason="">
                ✕ {endReason(x)}
              </p>
            ) : null}
            <ContextBlock x={x} />
            <InventoryBlock x={x} />
            <div className="row actions">
              {['STARTING', 'RUNNING', 'PAUSING', 'HANDING_OFF'].includes(x.state) ? (
                <ActionButton label="Stop" scope="control" kind="danger" confirm="Stop this execution now: its process is killed. The task and mission respond as Core decides (P11)." run={(key) => api.stopExecution(send(), x.id, { idempotency_key: key })} reread={[paths.getExecution(x.id)]} />
              ) : null}
              {x.state === 'RUNNING' ? (
                <ActionButton label="Hand off" scope="control" run={(key) => api.handoffExecution(send(), x.id, { idempotency_key: key })} reread={[paths.getExecution(x.id)]} />
              ) : null}
            </div>
          </header>
          <Tabs label="Execution" current={current} onSelect={onTab} tabs={INSPECTOR_TABS.execution.map((t) => ({ id: t, label: TAB_LABEL[t] }))} />
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="panel">
            {current === 'output' && <Output id={x.id} />}
            {current === 'checkpoints' && <Checkpoints id={x.id} />}
            {current === 'relations' && <Relations of={{ kind: 'execution', id: x.id }} />}
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
  const out = useRead<{ events: Record<string, unknown>[]; truncated: boolean; available: boolean; next_offset: number }>(paths.executionStream(id));
  return (
    <Loadable snap={out} what="the output">
      {(o) =>
        !o.available ? (
          <Empty>No output yet: the process has not started, or its harness is not available here.</Empty>
        ) : (
          <>
            {o.truncated || o.events.length > TAIL ? <p className="hint">Showing the last {Math.min(TAIL, o.events.length)} events.</p> : null}
            <ol className="output" aria-label="Execution output">
              {o.events.slice(-TAIL).map((ev, i) => {
                // an event without text is its fields in words; its identifiers and digests behind Details
                const { type, text, ...rest } = ev;
                const [fields, ids] = technical(rest);
                return (
                  <li key={i} data-type={String(type)}>
                    <span className="type">{String(type)}</span> <span className="text">{typeof text === 'string' ? text : inline(fields)}</span>
                    <Details rows={ids} />
                  </li>
                );
              })}
            </ol>
          </>
        )
      }
    </Loadable>
  );
}

function Checkpoints({ id }: { id: string }) {
  const c = useRead<{ checkpoints: Checkpoint[] }>(paths.listCheckpoints(id));
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

