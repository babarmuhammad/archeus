// World (p16-design-gate §6.8, §6.5): projects with their repositories and
// architecture state, and what Archeus knows — with provenance, supersession
// and relations. List-first; the spatial view is P18's.
import { useState } from 'react';
import { api, type InspectionList, type KnowledgeDetail, type KnowledgeList, type Project, type ProjectList } from '../api/generated';
import { send } from '../data/core';
import { useRead } from '../data/cache';
import { knowledgeEdges } from '../graph/relations';
import { INSPECTOR_TABS, TAB_LABEL, objectHref } from '../nav/destinations';
import { ago } from '../state/present';
import { Relations } from '../components/Relations';
import { ActionButton, Empty, Fresh, KV, Loadable, Section, StateBadge, Tabs } from '../components/ui';

export function WorldView() {
  const p = useRead<ProjectList>('/v1/projects');
  const [kind, setKind] = useState<'projects' | 'knowledge'>('projects');
  return (
    <div className="view">
      <h1 tabIndex={-1}>World</h1>
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
                      <li key={x.id} className="row-item">
                        <a className="row-link" href={`#/world/${x.id}`}>
                          <span className="title">{x.name}</span>
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
                  <Empty>No project yet. Create one from Control or with the CLI.</Empty>
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
  return (
    <div className="view">
      <Loadable snap={p} what="the project">
        {(x) => (
          <>
            <h1 tabIndex={-1}>{x.name}</h1>
            <Fresh snap={p} />
            <p>
              <a href={`#/work/${x.id}`}>Its missions in Work</a> · roots <span className="mono">{x.root_paths.join(', ')}</span>
            </p>
            {(x.repositories ?? []).map((r) => (
              <Section key={r.id} title={`${r.kind} · ${r.path}`}>
                <div className="facts">
                  <StateBadge machine="architecture" state={r.architecture_state} />
                  {r.last_revision ? <span className="mono">at {String(r.last_revision).slice(0, 10)}</span> : null}
                </div>
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
                            {f.reason ?? '—'}
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
                <StateBadge machine="repository_inspection" state={i.state} /> <span className="mono">{String(i.revision ?? '').slice(0, 10)}</span>
                {i.failure ? ` — ${i.failure}` : ''}
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
                <li key={k.id} className="row-item" data-inactive={['SUPERSEDED', 'RETRACTED', 'EXPIRED'].includes(k.state) ? '' : undefined}>
                  <a className="row-link" href={objectHref('knowledge_item', k.id)}>
                    <StateBadge machine="knowledge_item" state={k.state} />
                    <span className="title">{k.title}</span>
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
  return (
    <Loadable snap={s} what="the knowledge item">
      {(k) => (
        <div className="inspector-body">
          <header className="insp-head">
            <h1 tabIndex={-1}>{String(k.title ?? k.id)}</h1>
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
          </header>
          <Tabs label="Knowledge item" current={current} onSelect={onTab} tabs={INSPECTOR_TABS.knowledge_item.map((t) => ({ id: t, label: TAB_LABEL[t] }))} />
          <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="panel">
            {current === 'detail' ? (
              <>
                <p className="prose">{String(k.text ?? '')}</p>
                <KV
                  rows={[
                    ['Origin', String(k.origin ?? '—')],
                    ['Source', `${String(k.source_kind ?? '—')} ${k.source_ref ? JSON.stringify(k.source_ref) : ''}`],
                    ['Observed', ago(k.observed_at as string | null)],
                    ['Produced by (route)', k.route_decision_id ? <a href={objectHref('route_decision', String(k.route_decision_id))}>{String(k.route_decision_id)}</a> : 'the user or a deterministic pass'],
                  ]}
                />
                <Section title="Supersession chain (oldest first)">
                  <ol className="list">
                    {k.chain.map((c) => (
                      <li key={c}>{c === id ? <strong>{c} (this item)</strong> : <a href={objectHref('knowledge_item', c)}>{c}</a>}</li>
                    ))}
                  </ol>
                </Section>
              </>
            ) : (
              <Relations edges={knowledgeEdges(k)} />
            )}
          </div>
        </div>
      )}
    </Loadable>
  );
}
