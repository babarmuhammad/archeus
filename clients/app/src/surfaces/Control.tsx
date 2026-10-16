// Control (p16-design-gate §6.11, §6.12, §6.9): how much Archeus may do and
// with what. Every change is an admin command Core judges; nothing here
// evaluates a policy, orders a route or starts a session by itself.
import { useEffect, useState } from 'react';
import {
  paths,
  api,
  type Account,
  type AccountList,
  type AutomationList,
  type DeviceList,
  type Health,
  type HarnessList,
  type OptInList,
  type PairingCode,
  type ProjectList,
  type Policies,
  type RouteDecisionList,
  type Session,
  type SessionBrief,
  type SessionList,
  type Simulation,
  type Sync,
} from '../api/generated';
import { clearToken } from '../api/transport';
import { store, useConn, useRead, type Snapshot } from '../data/cache';
import { canCommand } from '../data/connection';
import { motionMode, type MotionPref } from '../data/commands';
import { send } from '../data/core';
import { CONTROL_SECTIONS, INSPECTOR_TABS, TAB_LABEL, href, objectHref } from '../nav/destinations';
import { ago, armedText, estopSaid, presenceLabel, stepUpBlocked, templateText, triggerText, usageText } from '../state/present';
import { BUDGETS, draftBudgets, policyProblem, type PolicyDraft } from '../state/policy';
import { QR } from '../components/QR';
import { Relations } from '../components/Relations';
import { ActionButton, Changed, Details, Empty, Fresh, KV, Loadable, Prose, RefLabel, Resources, Section, StateBadge, Tabs, thread, useChanged, useMe } from '../components/ui';

export function ControlView({ section }: { section: string }) {
  const cur = CONTROL_SECTIONS.find((s) => s.id === section)?.id ?? 'autonomy';
  return (
    <div className="view">
      <h1 tabIndex={-1}>Control</h1>
      <nav aria-label="Control sections" className="subnav">
        {CONTROL_SECTIONS.map((s) => (
          <a key={s.id} href={href({ view: 'control', section: s.id })} aria-current={s.id === cur ? 'page' : undefined}>
            {s.label}
          </a>
        ))}
      </nav>
      {cur === 'autonomy' && <Autonomy />}
      {cur === 'automations' && <Automations />}
      {cur === 'resources' && <ResourcesSection />}
      {cur === 'sessions' && <Sessions />}
      {cur === 'devices' && <Devices />}
      {cur === 'appearance' && <Appearance />}
      {cur === 'about' && <About />}
    </div>
  );
}

// ── autonomy: the policy as it is, and a way to ask "what would happen" ──

/** The action classes are Core's: every profile names each one (P19 B6 added `mission.start`). */
const classesOf = (p: Policies | undefined) => Object.keys(Object.values(p?.profiles ?? {})[0] ?? {});

function Autonomy() {
  const s = useRead<Policies>(paths.getPolicies());
  const changed = useChanged();
  return (
    <Loadable snap={s} what="the policy">
      {(p) => (
        <>
          <Section title="Your default profile" actions={<Fresh snap={s} />}>
            <p>
              <strong>{p.user_profile}</strong>
            </p>
            <Details rows={[['Policy version (digest)', p.policy_version]]} />
            <div className="row">
              {(['careful', 'standard', 'autonomous'] as const).map((name) => (
                <ActionButton
                  key={name}
                  label={`Use ${name}`}
                  scope="admin"
                  disabled={p.user_profile === name ? 'This is the profile in force.' : null}
                  run={(key) => api.setProfile(send(), { scope: 'user', profile: name, idempotency_key: key })}
                  reread={[paths.getPolicies()]}
                />
              ))}
            </div>
            <table className="grid">
              <caption className="sr">What each profile decides per action class</caption>
              <thead>
                <tr>
                  <th scope="col">Action class</th>
                  {Object.keys(p.profiles).map((n) => (
                    <th key={n} scope="col">
                      {n}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {classesOf(p).map((c) => (
                  <tr key={c}>
                    <th scope="row" className="mono">
                      {c}
                    </th>
                    {Object.entries(p.profiles).map(([n, table]) => (
                      <td key={n}>{String(((table as Record<string, { decision?: string }>)[c] ?? {}).decision ?? '—')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
          <Section title={`Your rules · ${p.rules.length}`}>
            {p.rules.length ? (
              <ul className="list">
                {p.rules.map((r) => (
                  <li key={r.id} data-rule={r.id} data-inactive={r.retired_at ? '' : undefined} {...thread(changed('policy_rule', r.id))}>
                    <Changed on={changed('policy_rule', r.id)} />
                    <span className="mono">{r.scope_level}</span> · {r.action_class} → <strong>{r.decision}</strong> {r.locked ? <span className="tag">locked</span> : null} {r.retired_at ? <span className="tag">retired</span> : null}
                    {!r.retired_at ? <ActionButton label="Retire" scope="admin" run={(key) => api.retireRule(send(), r.id, { idempotency_key: key })} reread={[paths.getPolicies()]} /> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No rule of your own: the profile decides.</Empty>
            )}
          </Section>
          <Simulate />
        </>
      )}
    </Loadable>
  );
}

function Simulate() {
  const policies = useRead<Policies>(paths.getPolicies());
  const [cls, setCls] = useState<string>('git_push');
  const [target, setTarget] = useState('');
  const [got, setGot] = useState<Simulation | null>(null);
  return (
    <Section title="What would happen if…">
      <form className="form" onSubmit={(e) => e.preventDefault()}>
        <label>
          Action class
          <select value={cls} onChange={(e) => setCls(e.target.value)}>
            {classesOf(policies.data).map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label>
          Target (optional)
          <input value={target} onChange={(e) => setTarget(e.target.value)} className="mono" />
        </label>
        <ActionButton
          label="Simulate"
          scope="observe"
          run={() => api.simulatePolicy(send(), { action: { class: cls, target: target || null } })}
          onDone={(out) => setGot(out as Simulation)}
        />
      </form>
      {got ? (
        <p role="status">
          The policy would decide <strong>{got.decision}</strong>: <Prose text={got.reason} /> (nothing was done)
        </p>
      ) : null}
    </Section>
  );
}

// ── automations (§L): rules and their runs; a run links the mission it made ──

function Automations() {
  const s = useRead<AutomationList>(paths.listAutomations());
  const changed = useChanged();
  return (
    <Loadable snap={s} what="the automations">
      {(l) =>
        l.automations.length ? (
          <>
            {l.automations.map((a) => (
              <Section key={a.id} title={a.name} actions={<StateBadge machine="automation" state={a.state} />} changed={changed('automation', a.id)}>
                <KV
                  rows={[
                    ['When', triggerText(a.trigger)],
                    ['Archeus will', templateText(a.template)],
                    ['Depth limit · rate limit', `${String(a.max_depth ?? '—')} · ${String(a.rate_limit ?? '—')} per hour`],
                  ]}
                />
                <div className="row">
                  {a.state === 'ENABLED' ? <ActionButton label="Disable" scope="admin" run={(key) => api.setAutomationState(send(), a.id, { action: 'disable', expected_version: a.version, idempotency_key: key })} reread={[paths.listAutomations()]} /> : null}
                  {['DRAFT', 'DISABLED', 'SUSPENDED'].includes(a.state) ? <ActionButton label="Enable" scope="admin" run={(key) => api.setAutomationState(send(), a.id, { action: 'enable', expected_version: a.version, idempotency_key: key })} reread={[paths.listAutomations(), paths.attentionItems()]} /> : null}
                  {['ENABLED', 'DISABLED'].includes(a.state) ? <ActionButton label="Archive" scope="admin" confirm="Archive this automation: it never fires again. It cannot be undone." kind="danger" run={(key) => api.setAutomationState(send(), a.id, { action: 'archive', expected_version: a.version, idempotency_key: key })} reread={[paths.listAutomations()]} /> : null}
                </div>
                <Details rows={[['Automation id', a.id], ['Project id', a.project_id]]} />
                <AutomationRuns id={a.id} />
              </Section>
            ))}
          </>
        ) : (
          <Empty>No automation yet. One is written with the CLI (`archeus automation`) or by an admin client.</Empty>
        )
      }
    </Loadable>
  );
}

function AutomationRuns({ id }: { id: string }) {
  const s = useRead<{ runs?: { id: string; state: string; depth: number; reason?: string | null; mission_id?: string | null; triggering_event_seq: number }[] }>(paths.getAutomation(id));
  const runs = s.data?.runs ?? [];
  const changed = useChanged();
  return runs.length ? (
    <ul className="list">
      {runs.slice(-20).reverse().map((r) => (
        <li key={r.id} data-run={r.id} {...thread(changed('automation_run', r.id))}>
          <Changed on={changed('automation_run', r.id)} />
          <StateBadge machine="automation_run" state={r.state} /> <a href={objectHref('automation_run', r.id)}>run on event {r.triggering_event_seq}</a> · depth {r.depth}
          {r.reason ? <> · <Prose text={r.reason} /></> : ''}
          {r.mission_id ? <> · <a href={objectHref('mission', r.mission_id)}>its mission</a></> : null}
        </li>
      ))}
    </ul>
  ) : (
    <Empty>It has not fired yet.</Empty>
  );
}

// ── resources (§6.4): harness, account and model are three things ──

function ResourcesSection() {
  const h = useRead<HarnessList>(paths.listHarnesses());
  const a = useRead<AccountList>(paths.listAccounts());
  const r = useRead<RouteDecisionList>(paths.listRouteDecisions());
  const o = useRead<OptInList>(paths.listOptIns());
  const changed = useChanged();
  return (
    <>
      <Section title="Harnesses" actions={<Fresh snap={h} />}>
        <Loadable snap={h} what="the harnesses">
          {(l) => (
            <table className="grid">
              <thead>
                <tr>
                  <th scope="col">Harness</th>
                  <th scope="col">Installed</th>
                  <th scope="col">Runs executions</th>
                  <th scope="col">Own calls</th>
                  <th scope="col">Policy enforcement</th>
                  <th scope="col">Models it offers</th>
                </tr>
              </thead>
              <tbody>
                {l.harnesses.map((x) => (
                  <tr key={x.id}>
                    <th scope="row" className="mono" data-harness={x.id} {...thread(changed('harness', x.id))}>
                      {x.id}
                      <Changed on={changed('harness', x.id)} />
                    </th>
                    <td>{x.installed ? 'yes' : 'no'}</td>
                    <td>{x.execution ? 'yes' : 'no'}</td>
                    <td>{x.calls ? 'yes' : 'no'}</td>
                    <td>{x.enforcement ?? '—'}</td>
                    <td className="mono">{x.models.map((m) => String(m.id ?? m.model ?? '')).filter(Boolean).join(', ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Loadable>
      </Section>
      <Section title="Accounts">
        <Loadable snap={a} what="the accounts">
          {(l) =>
            l.accounts.length ? (
              <ul className="list">
                {l.accounts.map((x) => (
                  <li key={x.id} data-account={x.id} {...thread(changed('account', x.id))}>
                    <Changed on={changed('account', x.id)} />
                    <StateBadge machine="account_health" state={x.health} /> <strong>{x.label}</strong> · harness <span className="mono">{x.harness_id}</span> · {x.auth_kind}
                    <KV
                      rows={[
                        ['Priority', String(x.resource_policy.priority)],
                        ['Allocation ceiling', `${x.resource_policy.allocation_pct}% (reserve ${x.resource_policy.reserve_pct}%, own-call reserve ${x.resource_policy.brain_reserve_pct}%)`],
                        ['Fallback to it', x.resource_policy.fallback],
                        ['Latest usage', usageText(x.usage as Parameters<typeof usageText>[0])],
                      ]}
                    />
                    <Details rows={[['Account id', x.id], ['Home (config directory)', x.home_ref as string | undefined]]} />
                    <PolicyForm a={x} />
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No account registered.</Empty>
            )
          }
        </Loadable>
      </Section>
      {/* P20 D6 (ADR-0049): read-only; `archeus executions opt-in|opt-out` sets them */}
      <Section title="What executions may load from their settings sources" actions={<Fresh snap={o} />}>
        <p className="hint">
          Every execution excludes its account's, project's and local settings (hooks, plugins, skills, MCP servers) unless an opt-in below lets it back in. Set with “archeus executions opt-in|opt-out”; read-only here.
        </p>
        <Loadable snap={o} what="the opt-ins">
          {(l) =>
            l.opt_ins.length ? (
              <table className="grid" data-opt-ins="">
                <thead>
                  <tr>
                    <th scope="col">Kind</th>
                    <th scope="col">Name</th>
                    <th scope="col">Belongs to</th>
                    <th scope="col">State</th>
                    <th scope="col">Version</th>
                  </tr>
                </thead>
                <tbody>
                  {l.opt_ins.map((x) => (
                    <tr key={x.id} data-opt-in={x.id}>
                      <td>{x.kind}</td>
                      <th scope="row" className="mono">{x.name}</th>
                      <td>
                        {x.owner} <span className="mono">{x.owner_id}</span>
                      </td>
                      <td>{x.opted_in ? 'opted in' : 'opted out'}</td>
                      <td>{x.version}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Empty>Nothing is opted in: every settings source is excluded.</Empty>
            )
          }
        </Loadable>
      </Section>
      <Section title="Recent routing decisions">
        <Loadable snap={r} what="the route decisions">
          {(l) =>
            l.route_decisions.length ? (
              <ul className="list">
                {l.route_decisions.slice(-20).reverse().map((d) => (
                  <li key={d.id}>
                    <a href={objectHref('route_decision', d.id)}>{String(d.purpose ?? 'task')}</a> · {String(d.result ?? '—')}
                    <Resources r={d} />
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nothing was routed yet.</Empty>
            )
          }
        </Loadable>
      </Section>
    </>
  );
}

/** An account's resource policy as a form (rulebook §43; D-7, §46.1): the
 * fields Core's existing `POST /v1/resource-policies/{id}` takes — priority,
 * allocation ceiling, the two reserves, fallback, the three budgets and the
 * projects it may or may not serve. Admin scope. A ceiling, never a quota
 * Archeus must spend. P22 adds the rest of ADR-0041's fields. */
function PolicyForm({ a }: { a: Account }) {
  const p = a.resource_policy as Account['resource_policy'] & { project_allow?: string[]; project_deny?: string[] };
  const budgets = (p.budgets ?? {}) as Record<string, number>;
  const projects = useRead<ProjectList>(paths.listProjects());
  const start = (): PolicyDraft => ({
    priority: String(p.priority),
    allocation_pct: String(p.allocation_pct),
    reserve_pct: String(p.reserve_pct),
    brain_reserve_pct: String(p.brain_reserve_pct),
    tokens_per_day: budgets.tokens_per_day === undefined ? '' : String(budgets.tokens_per_day),
    cost_per_day: budgets.cost_per_day === undefined ? '' : String(budgets.cost_per_day),
    concurrency: budgets.concurrency === undefined ? '' : String(budgets.concurrency),
  });
  const [d, setD] = useState<PolicyDraft>(start);
  const [fallback, setFallback] = useState(p.fallback);
  const [allow, setAllow] = useState<string[]>([...(p.project_allow ?? [])]);
  const [deny, setDeny] = useState<string[]>([...(p.project_deny ?? [])]);
  useEffect(() => {
    setD(start());
    setFallback(p.fallback);
    setAllow([...(p.project_allow ?? [])]);
    setDeny([...(p.project_deny ?? [])]);
  }, [p.version]);
  const num = (k: keyof PolicyDraft, label: string, hint?: string) => (
    <label>
      {label}
      {hint ? <span className="hint"> {hint}</span> : null}
      <input type="number" inputMode="numeric" min={k === 'priority' ? undefined : 0} value={d[k]} onChange={(e) => setD({ ...d, [k]: e.target.value })} />
    </label>
  );
  const toggle = (list: string[], set: (v: string[]) => void, id: string) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  return (
    <details className="form policy" data-policy-form={a.id} data-version={p.version}>
      <summary>Change this account's policy…</summary>
      {num('priority', 'Priority', '— a lower number is tried first')}
      {num('allocation_pct', 'Allocation ceiling, % of the provider window', '— work starts only below it')}
      {num('reserve_pct', 'Reserve, %', '— kept free for you')}
      {num('brain_reserve_pct', "Own-call reserve, %", "— kept for Archeus's own calls")}
      <label>
        Fallback — when nothing else can run it, may work run here past the ceiling?
        <select value={fallback} onChange={(e) => setFallback(e.target.value as typeof fallback)}>
          <option value="allow">yes (allow)</option>
          <option value="ask">ask me first (ask)</option>
          <option value="deny">never (deny)</option>
        </select>
      </label>
      <fieldset>
        <legend>Budgets — blank for none</legend>
        {BUDGETS.map(([k, label]) => (
          <span key={k}>{num(k, label)}</span>
        ))}
      </fieldset>
      {(projects.data?.projects ?? []).length ? (
        <>
          <fieldset>
            <legend>Only these projects — none ticked: any project</legend>
            {(projects.data?.projects ?? []).map((x) => (
              <label key={x.id} className="check">
                <input type="checkbox" checked={allow.includes(x.id)} onChange={() => toggle(allow, setAllow, x.id)} /> {x.name}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Never these projects</legend>
            {(projects.data?.projects ?? []).map((x) => (
              <label key={x.id} className="check">
                <input type="checkbox" checked={deny.includes(x.id)} onChange={() => toggle(deny, setDeny, x.id)} /> {x.name}
              </label>
            ))}
          </fieldset>
        </>
      ) : null}
      <ActionButton
        label="Save policy"
        scope="admin"
        kind="primary"
        disabled={policyProblem(d)}
        run={(key) =>
          api.setResourcePolicy(send(), a.id, {
            priority: Number(d.priority),
            allocation_pct: Number(d.allocation_pct),
            reserve_pct: Number(d.reserve_pct),
            brain_reserve_pct: Number(d.brain_reserve_pct),
            fallback,
            budgets: draftBudgets(d),
            project_allow: allow,
            project_deny: deny,
            expected_version: p.version,
            idempotency_key: key,
          })
        }
        reread={[paths.listAccounts(), paths.listRouteDecisions()]}
      />
    </details>
  );
}

// ── sessions (P12, §6.9): infrastructure; continuity is reconstruction ──

function Sessions() {
  const s = useRead<SessionList>(paths.listSessions());
  const changed = useChanged();
  return (
    <Section title="Sessions" actions={<Fresh snap={s} />}>
      <p className="hint">A session is one provider conversation on one harness and account. It is not a mission: a mission may continue across several sessions and harnesses.</p>
      <Loadable snap={s} what="the sessions">
        {(l) =>
          l.sessions.length ? (
            <ul className="rows">
              {[...l.sessions].reverse().map((x) => (
                <li key={x.id} className="row-item" data-session={x.id} {...thread(changed('session', x.id))}>
                  <a className="row-link" href={objectHref('session', x.id)}>
                    <StateBadge machine="session" state={x.state} />
                    <span className="title">{x.harness_id} session</span>
                    <Changed on={changed('session', x.id)} />
                    <span className="status">{x.mode}</span>
                    <Resources r={x} />
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No session is known to Archeus yet.</Empty>
          )
        }
      </Loadable>
    </Section>
  );
}

export function SessionInspector({ id, tab, onTab }: { id: string; tab?: string; onTab: (t: string) => void }) {
  const s = useRead<Session & { lineage?: Session[]; targets?: Session[] }>(paths.getSession(id));
  const current = tab && INSPECTOR_TABS.session.includes(tab) ? tab : 'brief';
  const changed = useChanged();
  return (
    <Loadable snap={s} what="the session">
      {(x) => (
        <div className="inspector-body">
          <header className="insp-head">
            <h1 tabIndex={-1}>Session</h1>
            <div className="meta">
              <StateBadge machine="session" state={x.state} />
              <span>{x.mode}</span>
              <Fresh snap={s} />
            </div>
            <Resources r={x} />
            <Details
              rows={[
                ['Session id', x.id],
                ['Account id', x.account_id],
                ['Mission id', x.mission_id],
                ['Project id', x.project_id],
                ['Workspace id', x.workspace_id],
                ['Continues session (id)', x.handoff_from_session_id],
              ]}
            />
            <SessionActions x={x} later={((x.targets ?? []) as unknown as string[]).at(-1)} />
          </header>
          <Tabs label="Session" current={current} onSelect={onTab} tabs={INSPECTOR_TABS.session.map((t) => ({ id: t, label: TAB_LABEL[t] }))} />
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="panel">
            {current === 'brief' && <Brief id={id} />}
            {current === 'lineage' && (
              <ol className="list">
                {[...(x.lineage ?? []), x, ...(x.targets ?? [])].map((y) => (
                  <li key={y.id} {...thread(changed('session', y.id))}>
                    <Changed on={changed('session', y.id)} />
                    {y.id === x.id ? <strong>this session</strong> : <a href={objectHref('session', y.id)}>{(x.lineage ?? []).includes(y) ? 'an earlier session' : 'a later session'}</a>} · harness <span className="mono">{y.harness_id}</span> · <StateBadge machine="session" state={y.state} />
                  </li>
                ))}
              </ol>
            )}
            {current === 'relations' && <Relations of={{ kind: 'session', id: x.id }} />}
          </div>
        </div>
      )}
    </Loadable>
  );
}

/** What mattered, what changed, what is unresolved, what to see next — built
 * by Core from current state (P12), never a replay of the transcript. */
function Brief({ id }: { id: string }) {
  const b = useRead<SessionBrief>(paths.sessionBrief(id));
  return (
    <Loadable snap={b} what="the brief">
      {(x) => {
        const m = x.mission as { title?: string; objective?: string; state?: string; id?: string } | null | undefined;
        const ch = x.changes as { count?: number; groups?: { ref: { kind: string; id: string }; headline: string; count: number }[] } | undefined;
        const ctx = x.context as { stale?: boolean; package_id?: string; missing_information?: string[] } | undefined;
        return (
          <>
            <p className="hint">As of event {x.as_of_seq}. This is rebuilt from current state; the transcript is not replayed.</p>
            <Section title="What mattered">
              {m ? (
                <p>
                  <a href={objectHref('mission', String(m.id))}>{m.title}</a> — {m.objective} {m.state ? <StateBadge machine="mission" state={m.state} /> : null}
                </p>
              ) : (
                <Empty>This session continues no mission.</Empty>
              )}
            </Section>
            <Section title="What changed since this session last looked">
              {ch?.groups?.length ? (
                <ul className="list">
                  {ch.groups.map((g) => (
                    <li key={g.ref.id}>
                      <a href={objectHref(g.ref.kind, g.ref.id)}><RefLabel kind={g.ref.kind} id={g.ref.id} /></a> · {g.headline} · {g.count}
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>Nothing changed.</Empty>
              )}
            </Section>
            <Section title="What is unresolved">
              {ctx?.missing_information?.length ? (
                <ul className="list">
                  {ctx.missing_information.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              ) : (
                <Empty>No missing information recorded.</Empty>
              )}
              {ctx?.stale ? <p className="warn">The context this session had is stale: resuming rebuilds it.</p> : null}
            </Section>
            <Section title="What to see next">
              {m?.id ? <a href={objectHref('mission', m.id, 'why')}>Why the mission is where it is</a> : <Empty>Nothing waits here.</Empty>}
            </Section>
          </>
        );
      }}
    </Loadable>
  );
}

/** A session's actions, and its way on (rulebook §16): one that was handed
 * off says where it continued; one that cannot be resumed — lost, or an
 * execution's own (it continues by hand-off) — offers the hand-off first. */
function SessionActions({ x, later }: { x: Session; later?: string }) {
  const resumable = x.state !== 'LOST' && x.mode !== 'headless';
  // Core's `targets` are the ids of the sessions this one was handed off to
  const next = useRead<Session>(later ? paths.getSession(later) : null);
  const h = useRead<HarnessList>(paths.listHarnesses());
  const [harness, setHarness] = useState('');
  const [account, setAccount] = useState('');
  const [model, setModel] = useState('');
  const [reason, setReason] = useState('');
  const reread = [paths.listSessions()];
  const rid = () => crypto.randomUUID();
  return (
    <div className="session-actions">
      {later ? (
        <p className="continue" data-continue="">
          Continued on <a href={objectHref('session', later)}>{next.data ? `the ${next.data.harness_id} session` : 'a later session'}</a>.
        </p>
      ) : null}
      {resumable ? (
        <ActionButton label="Resume" scope="control" kind="primary" run={(key) => api.resumeSession(send(), x.id, { request_id: rid(), deliver_brief: true, idempotency_key: key })} reread={reread} />
      ) : null}
      {x.state === 'OPEN' ? <ActionButton label="Close" scope="control" run={(key) => api.closeSession(send(), x.id, { idempotency_key: key })} reread={reread} /> : null}
      {!resumable && !later ? (
        <p className="hint" data-dead-end="">
          {x.state === 'LOST' ? 'Its provider session is gone, so it cannot be resumed.' : 'This session belongs to an execution: it continues by hand-off, not by resume.'}
        </p>
      ) : null}
      <details className="form" open={!resumable && !later}>
        <summary>{!resumable && !later ? 'Continue on another harness…' : 'Hand off to another harness…'}</summary>
        <p className="hint">A new session starts on the harness you choose, with what Core renders of the current state. This session is not changed.</p>
        <label>
          Target harness (required)
          <select value={harness} onChange={(e) => setHarness(e.target.value)}>
            <option value="">choose…</option>
            {(h.data?.harnesses ?? []).map((y) => (
              <option key={y.id} value={y.id}>
                {y.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          Account (optional)
          <input value={account} onChange={(e) => setAccount(e.target.value)} className="mono" />
        </label>
        <label>
          Model (optional, in that harness’s own names)
          <input value={model} onChange={(e) => setModel(e.target.value)} className="mono" />
        </label>
        <label>
          Reason
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <ActionButton
          label="Hand off"
          scope="control"
          disabled={harness ? null : 'Choose the target harness.'}
          run={(key) => api.handoffSession(send(), x.id, { request_id: rid(), harness_id: harness, account_id: account || null, model: model || null, reason: reason || null, idempotency_key: key })}
          reread={reread}
        />
      </details>
    </div>
  );
}

// ── clients (P15, §6.12): registrations, presence, pairing, revocation ──

function Devices() {
  const d = useRead<DeviceList>(paths.listDevices());
  const me = useRead<Sync>(paths.sync());
  const { local } = useMe();
  return (
    <>
      <Section title="Clients" actions={<Fresh snap={d} />}>
        <p className="hint">A client is one registered installation of an Archeus app. “Connected” means an event stream is open — not that someone is using it. The platform is what the client declared.</p>
        <Loadable snap={d} what="the clients">
          {(l) => {
            const groups = new Map<string, typeof l.devices>();
            for (const x of l.devices) {
              const k = x.host_label ?? 'unlabelled';
              groups.set(k, [...(groups.get(k) ?? []), x]);
            }
            return (
              <>
                {[...groups.entries()].map(([label, ds]) => (
                  <div key={label} className="device-group">
                    <h3>{label}</h3>
                    <ul className="list">
                      {ds.map((x) => (
                        <li key={x.id} data-device={x.id} data-presence={x.presence.state}>
                          <strong>{x.name}</strong> {x.id === me.data?.client.id ? <span className="tag">this client</span> : null} · {x.client_type} · platform {x.platform} (declared) · {x.origin === 'paired' ? 'paired' : 'on this computer'}
                          <br />
                          <StateBadge machine="device" state={x.state} /> · {presenceLabel(x.presence)}
                          {x.presence.last_seen_at ? ` · last seen ${ago(x.presence.last_seen_at)}` : ''} · scopes {x.scopes.join(', ')} · step-up {x.capabilities.step_up}
                          {x.expires_at ? ` · expires ${x.expires_at.slice(0, 10)}` : ''}
                          {x.state === 'ACTIVE' ? (
                            <ActionButton
                              label="Revoke"
                              scope="admin"
                              kind="danger"
                              confirm="This client loses access at once and its open streams close. It cannot be undone: the client must be paired again."
                              run={(key) => api.revokeDevice(send(), x.id, { idempotency_key: key })}
                              reread={[paths.listDevices()]}
                              onDone={() => {
                                if (x.id === me.data?.client.id) {
                                  void clearToken();
                                  store.signal('self_revoked');
                                }
                              }}
                            />
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </>
            );
          }}
        </Loadable>
      </Section>
      {local ? <PairStart /> : <p className="hint">Pairing a new client starts on the computer running Archeus.</p>}
    </>
  );
}

function PairStart() {
  const [name, setName] = useState('');
  const [label, setLabel] = useState('');
  const [admin, setAdmin] = useState(false);
  const [code, setCode] = useState<PairingCode | null>(null);
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (!code) return;
    const until = Date.now() + code.expires_in * 1000;
    const t = setInterval(() => {
      const s = Math.max(0, Math.round((until - Date.now()) / 1000));
      setLeft(s);
      if (!s) setCode(null);
    }, 1000);
    setLeft(code.expires_in);
    return () => clearInterval(t);
  }, [code]);
  return (
    <Section title="Pair a client">
      <form className="form" onSubmit={(e) => e.preventDefault()}>
        <label>
          Name (what the new client is called here)
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Host label (your name for the machine or phone it runs on)
          <input value={label} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <label className="check">
          <input type="checkbox" checked={admin} onChange={(e) => setAdmin(e.target.checked)} /> Also grant admin (policy, resources, clients) — usually not for a phone
        </label>
        <ActionButton
          label="Start pairing"
          scope="admin"
          run={() => api.pairStart(send(), { name: name || null, host_label: label || null, scopes: admin ? ['observe', 'control', 'approve', 'admin'] : ['observe', 'control', 'approve'] })}
          onDone={(out) => setCode(out as PairingCode)}
        />
      </form>
      {code ? (
        <div className="pairing" role="status">
          <p>
            Valid for <strong>{left} s</strong>, once. Scopes: {code.scopes.join(', ')}.
          </p>
          {code.url ? (
            <>
              <QR text={code.url} label="QR code of the pairing link" />
              <p className="mono break">{code.url}</p>
            </>
          ) : (
            <p className="hint">
              No remote host is configured, so a phone cannot reach this computer yet: start Core with <span className="mono">archeus core --remote-host &lt;name&gt;</span> behind an HTTPS tunnel. On this computer, open <span className="mono">{`${location.origin}/#pair=${code.code}`}</span>.
            </p>
          )}
        </div>
      ) : null}
    </Section>
  );
}

// ── appearance: theme, contrast and motion, this client's own (ADR-0044) ──

export const MOTION_KEY = 'archeus-motion';

export function readMotionPref(): MotionPref {
  try {
    return localStorage.getItem(MOTION_KEY) === 'reduced' ? 'reduced' : 'system';
  } catch {
    return 'system';
  }
}

export function applyMotion() {
  const sys = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.documentElement.dataset.motion = motionMode(sys, readMotionPref());
}

type Theme = 'system' | 'dark' | 'light';
type Contrast = 'system' | 'standard' | 'high';
type AppearancePref = { theme: Theme; contrast: Contrast };

declare global {
  /** The appearance boot's own function (src/state/appearance.js): stores a choice, applies what is stored. */
  function archeusAppearance(next?: AppearancePref): AppearancePref;
}

function Appearance() {
  const [look, setLook] = useState<AppearancePref>(() => archeusAppearance());
  const [pref, setPref] = useState<MotionPref>(readMotionPref());
  const choose = (next: AppearancePref) => setLook(archeusAppearance(next));
  return (
    <>
      <p className="hint">Kept by this client only: another browser, the desktop app or a phone chooses its own. Windows contrast themes always win.</p>
      <Section title="Theme">
        <label>
          <select aria-label="Theme" value={look.theme} onChange={(e) => choose({ ...look, theme: e.target.value as Theme })}>
            <option value="system">Follow the system</option>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>
      </Section>
      <Section title="Contrast">
        <label>
          <select aria-label="Contrast" value={look.contrast} onChange={(e) => choose({ ...look, contrast: e.target.value as Contrast })}>
            <option value="system">Follow the system</option>
            <option value="standard">Standard</option>
            <option value="high">High</option>
          </select>
        </label>
      </Section>
      <Section title="Motion">
        <label>
          <select
            aria-label="Motion"
            value={pref}
            onChange={(e) => {
              const v = e.target.value as MotionPref;
              setPref(v);
              try {
                localStorage.setItem(MOTION_KEY, v);
              } catch {
                /* a display preference: without storage it follows the system */
              }
              applyMotion();
            }}
          >
            <option value="system">Follow the system</option>
            <option value="reduced">Reduced: no movement, changes appear at once</option>
          </select>
        </label>
      </Section>
    </>
  );
}

// ── about: this Core, this client ──

function About() {
  const h = useRead<Health>(paths.health());
  const s = useRead<Sync>(paths.sync());
  return (
    <>
      <Section title="This Core">
        <Loadable snap={h} what="Core's health">
          {(x) => (
            <KV
              rows={[
                ['Version', x.core.version],
                ['Schema', String(x.core.schema)],
                ['Started', ago(x.core.started_at)],
                ['Engine', `${x.engine.state} (${x.engine.parked} parked)`],
                ['Workers', `world ${x.world.state} · knowledge ${x.knowledge.state} · intent ${x.intent.state} · plan ${x.plan.state} · policy ${x.policy.state}`],
              ]}
            />
          )}
        </Loadable>
      </Section>
      <Section title="This client">
        <Loadable snap={s} what="this client">
          {(x) => (
            <>
            <Details rows={[['Core instance', x.core.instance], ['This client (device id)', x.client.id], ['Principal id', x.client.principal_id as string | undefined]]} />
            <KV
              rows={[
                ['Registered as', `${x.client.name} (${x.client.origin})`],
                ['Scopes', x.client.scopes.join(', ')],
                ['Events kept', `${x.floor_seq} – ${x.head_seq}`],
              ]}
            />
            </>
          )}
        </Loadable>
      </Section>
      <Estop health={h} />
    </>
  );
}

/** The emergency stop (P20 F7, F8): the state Core reports, in words, and only
 * the action that applies to it. Nothing is guessed while Core cannot be
 * reached, and the one status line is what Core answered, shown while the
 * state it describes holds. */
function Estop({ health }: { health: Snapshot<Health> }) {
  const conn = useConn();
  const [said, setSaid] = useState<ReturnType<typeof estopSaid> | null>(null);
  const [pin, setPin] = useState('');
  // D10 (V2-3, 2026-10-15): a paired client re-arms with its PIN; a local one by being local
  const stepUp = useRead<Sync>(paths.sync()).data?.client.capabilities.step_up;
  const armed = canCommand(conn.conn) ? health.data?.armed : undefined;
  const shown = said && (said.when === undefined || said.when === armed) ? said : null;
  return (
    <Section title="Emergency stop">
      <p data-armed={armed === undefined ? 'unknown' : String(armed)}>
        {armed === false ? <span className="tag blocked">{armedText(armed)}</span> : armedText(armed)}
      </p>
      {armed === true ? (
        <div className="row">
          <ActionButton label="Emergency stop" scope="control" kind="danger" confirm="Every running execution is killed now and Archeus refuses new work until you re-arm it. Missions are not lost; they wait." run={(key) => api.estop(send(), { idempotency_key: key })} reread={['/v1']} report={(o) => setSaid(estopSaid('estop', o))} />
        </div>
      ) : armed === false ? (
        <>
          {stepUp === 'pin' ? (
            <label className="pin">
              This client’s PIN (re-arming from a paired client needs it)
              <input inputMode="numeric" autoComplete="off" pattern="[0-9]*" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} maxLength={12} />
            </label>
          ) : stepUp === 'none' ? (
            <p className="hint">This client has no PIN, so it cannot re-arm: re-arm on the desktop.</p>
          ) : null}
          <div className="row">
            <ActionButton label="Re-arm" scope="control" disabled={stepUpBlocked(stepUp, pin)} run={(key) => api.rearm(send(), { idempotency_key: key, step_up: stepUp === 'pin' ? pin : undefined })} reread={['/v1']} report={(o) => { setPin(''); setSaid(estopSaid('rearm', o)); }} />
          </div>
        </>
      ) : null}
      <p className="hint" role="status" data-estop-said>
        {shown && !shown.alert ? shown.text : null}
      </p>
      {shown?.alert ? (
        <p className="err" role="alert" data-estop-said>
          {shown.text}
        </p>
      ) : null}
    </Section>
  );
}
