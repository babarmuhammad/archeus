// World (p16-design-gate §6.8, §6.5): projects with their repositories and
// architecture state, and what Archeus knows — with provenance, supersession
// and relations. List-first; the spatial view is P18's.
import { useState } from 'react';
import { api, type Forgotten, type InspectionList, type KnowledgeDetail, type KnowledgeList, type Project, type ProjectList } from '../api/generated';
import { CoreError } from '../api/transport';
import { explain, newKey } from '../data/commands';
import { canCommand } from '../data/connection';
import { useConn } from '../data/cache';
import { send } from '../data/core';
import { useRead } from '../data/cache';
import { INSPECTOR_TABS, TAB_LABEL, objectHref } from '../nav/destinations';
import { ago } from '../state/present';
import { GraphLink, Relations } from '../components/Relations';
import { useWide } from '../graph/wide';
import { ActionButton, Changed, Details, Empty, Fresh, KV, Loadable, Prose, RefLabel, Section, StateBadge, Tabs, thread, useChanged, useMe } from '../components/ui';

export function WorldView() {
  const p = useRead<ProjectList>('/v1/projects');
  const [kind, setKind] = useState<'projects' | 'knowledge'>('projects');
  const changed = useChanged();
  return (
    <div className="view">
      <h1 tabIndex={-1}>World</h1>
      <WorldGraphLink />
      <Tabs label="World" current={kind} onSelect={(k) => setKind(k as typeof kind)} tabs={[{ id: 'projects', label: 'Projects' }, { id: 'knowledge', label: 'Knowledge' }]} />
      <div role="tabpanel" id={`panel-${kind}`} aria-labelledby={`tab-${kind}`}>
        {kind === 'projects' ? (
          <>
            <Fresh snap={p} />
            <Loadable snap={p} what="the projects">
              {(l) =>
                l.projects.length ? (
                  <ul className="rows">
                    {l.projects.map((x) => (
                      <li key={x.id} className="row-item" data-project={x.id} {...thread(changed('project', x.id))}>
                        <a className="row-link" href={`#/world/${x.id}`}>
                          <span className="title">{x.name}</span>
                          <Changed on={changed('project', x.id)} />
                          <span className="status">
                            {(x.repositories ?? []).length} {(x.repositories ?? []).length === 1 ? 'repository' : 'repositories'}
                          </span>
                          {(x.repositories ?? []).map((r) => (
                            <StateBadge key={r.id} machine="architecture" state={r.architecture_state} />
                          ))}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty>No project yet. Create one below or with the CLI.</Empty>
                )
              }
            </Loadable>
            <NewProject />
          </>
        ) : (
          <KnowledgeList />
        )}
      </div>
    </div>
  );
}

function ModulesLink({ id }: { id: string }) {
  if (!useWide()) return null;
  return (
    <a className="graph-toggle" href={`#/world/graph/repository/${encodeURIComponent(id)}/modules`}>
      Modules as a graph
    </a>
  );
}

function WorldGraphLink() {
  if (!useWide()) return null;
  return (
    <p>
      <a className="graph-toggle" href="#/world/graph">
        Show the world as a graph
      </a>
    </p>
  );
}

function NewProject() {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  return (
    <details className="form">
      <summary>New project</summary>
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Root path on the computer running Archeus
        <input value={path} onChange={(e) => setPath(e.target.value)} className="mono" />
      </label>
      <ActionButton
        label="Create project"
        scope="admin"
        disabled={name.trim() && path.trim() ? null : 'Give a name and a root path.'}
        run={(key) => api.createProject(send(), { name, root_paths: [path], idempotency_key: key })}
        reread={['/v1/projects']}
      />
    </details>
  );
}

export function ProjectPage({ id }: { id: string }) {
  const p = useRead<Project>(`/v1/projects/${id}`);
  const changed = useChanged();
  return (
    <div className="view">
      <Loadable snap={p} what="the project">
        {(x) => (
          <>
            <h1 tabIndex={-1}>{x.name}</h1>
            <Fresh snap={p} />
            <Details rows={[['Project id', x.id], ['Workspace id', x.workspace_id as string | undefined]]} />
            <p>
              <a href={`#/work/${x.id}`}>Its missions in Work</a> · <GraphLink kind="project" id={x.id} /> · roots <span className="mono">{x.root_paths.join(', ')}</span>
            </p>
            {(x.repositories ?? []).map((r) => (
              <Section key={r.id} title={`${r.kind} · ${r.path}`} changed={changed('repository', r.id)}>
                <div className="facts">
                  <StateBadge machine="architecture" state={r.architecture_state} />
                  <ModulesLink id={r.id} />
                </div>
                <Details rows={[['Repository id', r.id], ['Last inspected revision (git)', r.last_revision as string | undefined]]} />
                {(r.findings ?? []).length ? (
                  <table className="grid">
                    <caption className="sr">Constraint findings</caption>
                    <thead>
                      <tr>
                        <th scope="col">Constraint</th>
                        <th scope="col">Status</th>
                        <th scope="col">Why</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(r.findings ?? []).map((f) => (
                        <tr key={f.constraint_id} data-status={f.status}>
                          <td>{f.constraint}</td>
                          <td>{f.status}</td>
                          <td>
                            {f.reason ? <Prose text={f.reason} /> : '—'}
                            {f.violations.length ? (
                              <ul className="list mono">
                                {f.violations.slice(0, 10).map((v, i) => (
                                  <li key={i}>{v.join(' → ')}</li>
                                ))}
                              </ul>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty>No declared constraint has been checked here.</Empty>
                )}
                <Inspections repo={r.id} />
              </Section>
            ))}
            <DeclareConstraint project={x.id} />
          </>
        )}
      </Loadable>
    </div>
  );
}

function Inspections({ repo }: { repo: string }) {
  const s = useRead<InspectionList>(`/v1/repositories/${repo}/inspections?limit=5`);
  return (
    <details>
      <summary>Recent inspections</summary>
      <Loadable snap={s} what="the inspections">
        {(l) => (
          <ul className="list">
            {l.inspections.map((i) => (
              <li key={i.id}>
                <StateBadge machine="repository_inspection" state={i.state} /> {i.inspected_at ? `inspected ${ago(String(i.inspected_at))}` : `attempt ${i.attempts}`}
                {i.failure ? <> — <Prose text={i.failure} /></> : null}
                <Details rows={[['Inspection id', i.id], ['Revision inspected (git)', i.revision]]} />
              </li>
            ))}
          </ul>
        )}
      </Loadable>
    </details>
  );
}

function DeclareConstraint({ project }: { project: string }) {
  const [text, setText] = useState('');
  return (
    <details className="form">
      <summary>Declare an architecture constraint</summary>
      <label>
        The rule, in words (a checkable rule needs a kind and spec; the CLI takes those)
        <input value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <ActionButton
        label="Declare"
        scope="control"
        disabled={text.trim() ? null : 'Write the rule first.'}
        run={(key) => api.declareConstraint(send(), project, { statement: text, idempotency_key: key })}
        reread={[`/v1/projects/${project}`]}
      />
    </details>
  );
}

function KnowledgeList() {
  const [state, setState] = useState<string>('');
  const s = useRead<KnowledgeList>(state ? `/v1/knowledge?state=${state}` : '/v1/knowledge');
  const changed = useChanged();
  return (
    <>
      <label className="filter">
        State
        <select value={state} onChange={(e) => setState(e.target.value)}>
          <option value="">all</option>
          {['CANDIDATE', 'CONFIRMED', 'SUPERSEDED', 'RETRACTED', 'EXPIRED'].map((x) => (
            <option key={x} value={x}>
              {x.toLowerCase()}
            </option>
          ))}
        </select>
      </label>
      <Fresh snap={s} />
      <Loadable snap={s} what="the knowledge">
        {(l) =>
          l.knowledge.length ? (
            <ul className="rows">
              {l.knowledge.map((k) => (
                <li key={k.id} className="row-item" data-knowledge={k.id} data-inactive={['SUPERSEDED', 'RETRACTED', 'EXPIRED'].includes(k.state) ? '' : undefined} {...thread(changed('knowledge_item', k.id))}>
                  <a className="row-link" href={objectHref('knowledge_item', k.id)}>
                    <StateBadge machine="knowledge_item" state={k.state} />
                    <span className="title">{k.title}</span>
                    <Changed on={changed('knowledge_item', k.id)} />
                    <span className="tag">{k.type.toLowerCase()}</span>
                    <span className="status">{String(k.source_kind ?? '')}</span>
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Nothing known yet.</Empty>
          )
        }
      </Loadable>
    </>
  );
}

export function KnowledgeInspector({ id, tab, onTab }: { id: string; tab?: string; onTab: (t: string) => void }) {
  const s = useRead<KnowledgeDetail>(`/v1/knowledge/${id}`);
  const current = tab && INSPECTOR_TABS.knowledge_item.includes(tab) ? tab : 'detail';
  const reread = [`/v1/knowledge`, '/v1/attention'];
  const changed = useChanged();
  return (
    <Loadable snap={s} what="the knowledge item">
      {(k) => (
        <div className="inspector-body">
          <header className="insp-head">
            <h1 tabIndex={-1}>{String(k.title ?? 'Knowledge item')}</h1>
            <div className="meta">
              <StateBadge machine="knowledge_item" state={k.state} />
              <span className="tag">{String(k.type ?? '').toLowerCase()}</span>
              <Fresh snap={s} />
            </div>
            <div className="row actions">
              {k.state === 'CANDIDATE' ? (
                <>
                  <ActionButton label="Confirm" scope="control" kind="primary" run={(key) => api.confirmKnowledge(send(), id, { idempotency_key: key, expected_version: Number(k.version) })} reread={reread} />
                  <ActionButton label="Reject" scope="control" run={(key) => api.rejectKnowledge(send(), id, { idempotency_key: key, expected_version: Number(k.version) })} reread={reread} />
                </>
              ) : null}
              {k.state === 'CONFIRMED' ? (
                <ActionButton label="Retract" scope="control" kind="danger" confirm="Retract this item: it stops being used as context. The row and its provenance are kept." run={(key) => api.retractKnowledge(send(), id, { idempotency_key: key, expected_version: Number(k.version) })} reread={reread} />
              ) : null}
            </div>
            <Forget id={k.id} />
            <Details
              rows={[
                ['Knowledge item id', k.id],
                ['Source (id)', (k.source_ref as { id?: string } | null | undefined)?.id],
                ['Produced by route decision (id)', k.route_decision_id as string | undefined],
                ...k.chain.map((c, i): [string, string] => [`Version ${i + 1} id`, c]),
              ]}
            />
          </header>
          <Tabs label="Knowledge item" current={current} onSelect={onTab} tabs={INSPECTOR_TABS.knowledge_item.map((t) => ({ id: t, label: TAB_LABEL[t] }))} />
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="panel">
            {current === 'detail' ? (
              <>
                <p className="prose">{String(k.text ?? '')}</p>
                <KV
                  rows={[
                    ['Origin', String(k.origin ?? '—')],
                    ['Source', <SourceRef k={k} />],
                    ['Observed', ago(k.observed_at as string | null)],
                    ['Produced by (route)', k.route_decision_id ? <a href={objectHref('route_decision', String(k.route_decision_id))}>a model call</a> : 'the user or a deterministic pass'],
                  ]}
                />
                <Section title="Supersession chain (oldest first)">
                  <ol className="list">
                    {k.chain.map((c) => (
                      <li key={c} {...thread(changed('knowledge_item', c))}>
                        {c === id ? <strong>this item</strong> : <a href={objectHref('knowledge_item', c)}><RefLabel kind="knowledge_item" id={c} /></a>}
                        <Changed on={changed('knowledge_item', c)} />
                      </li>
                    ))}
                  </ol>
                </Section>
              </>
            ) : (
              <Relations of={{ kind: 'knowledge_item', id: k.id }} />
            )}
          </div>
        </div>
      )}
    </Loadable>
  );
}

const MODES = {
  retract: 'Stop using it — the item and its provenance are kept (retract)',
  purge: 'Erase its content — only a tombstone with its provenance is kept (purge)',
} as const;

/** What a forget would change, in words, from Core's dry run. */
export function forgetWords(f: Forgotten): string[] {
  return f.changes.map((c) => {
    const to = c.to !== c.from ? `it stops being used as context (${String(c.from).toLowerCase()} → ${String(c.to).toLowerCase()})` : null;
    return [to, c.purge ? 'its content is erased; its provenance stays' : null].filter(Boolean).join('; ');
  });
}

/** Forget (rulebook §13): Core's one forget entry point. The preview is Core's
 * own dry run — it changes nothing — and Forget sends the same selector and
 * mode for real, behind a confirmation. No undo is offered: a retracted item
 * stays retracted and a purged one keeps only its tombstone (P16 §18.3). */
function Forget({ id }: { id: string }) {
  const [mode, setMode] = useState<keyof typeof MODES>('retract');
  const [preview, setPreview] = useState<{ mode: string; out: Forgotten } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const conn = useConn();
  const { can } = useMe();
  const why = !can('control') ? 'This client does not hold the “control” scope.' : !canCommand(conn.conn) ? 'Not connected — nothing is sent while reconnecting.' : null;
  const shown = preview?.mode === mode ? preview.out : null;
  async function dryRun() {
    setErr(null);
    try {
      setPreview({ mode, out: await api.forgetKnowledge(send(), { selector: { ids: [id] }, mode, dry_run: true, idempotency_key: newKey() }) });
    } catch (e) {
      setErr(explain(e instanceof CoreError ? e : new CoreError(0, 'network', {})));
    }
  }
  return (
    <details className="form forget" data-forget="">
      <summary>Forget…</summary>
      <fieldset>
        <legend>How to forget it</legend>
        {(Object.keys(MODES) as (keyof typeof MODES)[]).map((m) => (
          <label key={m} className="check">
            <input type="radio" name={`forget-${id}`} value={m} checked={mode === m} onChange={() => setMode(m)} /> {MODES[m]}
          </label>
        ))}
      </fieldset>
      <button type="button" className="btn secondary" disabled={!!why} title={why ?? undefined} onClick={() => void dryRun()}>
        See what would change
      </button>
      {why ? <span className="why">{why}</span> : null}
      {err ? <p className="err" role="alert">{err}</p> : null}
      {shown ? (
        <div role="status" data-forget-preview="">
          {shown.changes.length ? (
            <>
              <p>Forgetting would change {shown.changes.length === 1 ? 'this item' : `${shown.changes.length} items`}:</p>
              <ul className="list">
                {forgetWords(shown).map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </>
          ) : (
            <p>Nothing would change: it is already forgotten this way.</p>
          )}
        </div>
      ) : null}
      <ActionButton
        label="Forget"
        scope="control"
        kind="danger"
        disabled={!shown ? 'See what would change first.' : !shown.changes.length ? 'Nothing would change.' : null}
        confirm={`Forget it: ${mode === 'purge' ? 'its content is erased and only a tombstone with its provenance is kept' : 'it stops being used as context'}. This cannot be undone.`}
        run={(key) => api.forgetKnowledge(send(), { selector: { ids: [id] }, mode, dry_run: false, idempotency_key: key })}
        reread={['/v1/knowledge', '/v1/attention']}
        onDone={() => setPreview(null)}
      />
    </details>
  );
}

/** Where a knowledge item came from: the object it was learnt from, named. */
function SourceRef({ k }: { k: KnowledgeDetail }) {
  const ref = k.source_ref as { kind: string; id: string } | null | undefined;
  if (!ref) return <>{String(k.source_kind ?? '—')}</>;
  return (
    <>
      {String(k.source_kind ?? '')}{' '}
      <a href={objectHref(ref.kind, ref.id)}>
        <RefLabel kind={ref.kind} id={ref.id} />
      </a>
    </>
  );
}
