// Attention (p16-design-gate §6.3): everything that waits on the user, from
// GET /v1/attention. Each item is decided through its own P9/P6/P13 command;
// nothing here judges eligibility — the row says whether it can be decided.
import { useEffect, useState } from 'react';
import { api, type Approval, type Attention as AttentionT, type AttentionItem, type Sync } from '../api/generated';
import { announceApproval } from '../a11y/announce';
import { decideBody } from '../data/commands';
import { send } from '../data/core';
import { useRead, useRefresh } from '../data/cache';
import { objectHref } from '../nav/destinations';
import { ago } from '../state/present';
import { ActionButton, Empty, Fresh, KV, Loadable, StateBadge, useMe } from '../components/ui';

const KIND_LABEL: Record<string, string> = {
  approval: 'Approval',
  verification: 'Waiting for your acceptance',
  mission: 'Planning asks you',
  knowledge: 'Knowledge proposal',
  drift: 'Architecture drift',
  automation: 'Automation suspended',
  account: 'Account needs signing in',
};

export function AttentionView({ limit, heading = true }: { limit?: number; heading?: boolean }) {
  const snap = useRead<AttentionT>('/v1/attention');
  const body = (
    <Loadable snap={snap} what="Attention">
      {(a) => {
        const items = limit ? a.items.slice(0, limit) : a.items;
        if (!a.items.length) return <Empty>Nothing waits on you.</Empty>;
        return (
          <>
            <ul className="attention">
              {items.map((i) => (
                <li key={i.kind + i.ref.id}>
                  <AttentionEntry item={i} />
                </li>
              ))}
            </ul>
            {limit && a.items.length > limit ? (
              <a href="#/attention">All {a.items.length} items that wait on you</a>
            ) : null}
          </>
        );
      }}
    </Loadable>
  );
  if (!heading) return body;
  return (
    <div className="view">
      <h1 tabIndex={-1}>Attention</h1>
      <Fresh snap={snap} />
      {body}
    </div>
  );
}

function AttentionEntry({ item }: { item: AttentionItem }) {
  const title = KIND_LABEL[item.kind] ?? item.kind;
  return (
    <article className="att" aria-label={title} data-kind={item.kind}>
      <header>
        <StateBadge machine={MACHINE[item.kind]} state={item.state} />
        <span className="att-kind">{title}</span>
        <span className="age">{ago(item.since)}</span>
      </header>
      {item.kind === 'approval' ? (
        <ApprovalCard id={item.ref.id} />
      ) : item.kind === 'verification' ? (
        <VerificationDecision item={item} />
      ) : item.kind === 'knowledge' ? (
        <KnowledgeProposal item={item} />
      ) : (
        <p>
          {item.reason ? <span>{item.reason} · </span> : null}
          <a href={LINK[item.kind]?.(item) ?? '#/attention'}>Open</a>
        </p>
      )}
    </article>
  );
}

const MACHINE: Record<string, string> = {
  approval: 'approval',
  verification: 'verification',
  mission: 'mission',
  knowledge: 'knowledge_item',
  drift: 'architecture',
  automation: 'automation',
  account: 'account_health',
};

const LINK: Record<string, (i: AttentionItem) => string> = {
  mission: (i) => objectHref('mission', i.ref.id),
  drift: (i) => (i.project_id ? `#/world/${i.project_id}` : '#/world'),
  automation: () => '#/control/automations',
  account: () => '#/control/resources',
};

/** The approval card (ui-architecture §4.10): the canonical action as Core
 * rendered it, why it asks, what each answer does, when it expires. */
export function ApprovalCard({ id }: { id: string }) {
  const snap = useRead<Approval>(`/v1/approvals/${id}`);
  const sync = useRead<Sync>('/v1/sync');
  useRefresh(`/v1/approvals/${id}`, 30000); // eligibility moves with the clock (expiry)
  const { can } = useMe();
  const [pin, setPin] = useState('');
  useEffect(() => {
    if (snap.data?.state === 'PENDING') announceApproval(id, `An approval waits for you: ${String((snap.data.presented as { scope?: string })?.scope ?? snap.data.kind)}.`);
  }, [id, snap.data?.state]);
  return (
    <Loadable snap={snap} what="the approval">
      {(a) => {
        const p = a.presented as {
          what?: { task: string; title?: string; class: string; target?: string; paths?: string[]; decision: string; why?: string }[];
          why?: string;
          scope?: string;
          against?: { mission?: { title: string }; plan?: { version: number; digest?: string; summary?: string; summary_by?: string } };
          consequences?: { approve?: string; reject?: string; request_changes?: string | null };
          reusable?: string;
        };
        const stepUp = !!a.step_up;
        const capability = sync.data?.client.capabilities.step_up;
        const needsPin = stepUp && capability === 'pin';
        const cannotStepUp = stepUp && capability === 'none' ? 'This client has no PIN: it cannot satisfy a step-up.' : null;
        const destructive = stepUp || (p.what ?? []).some((w) => ['destructive', 'deploy'].includes(w.class));
        const notEligible = a.state !== 'PENDING' ? `This approval is ${a.state.toLowerCase()}.` : !a.eligible ? `Not decidable now: ${a.eligible_why ?? 'no reason given'}.` : null;
        const decided = a.decided_by ? `Decided ${ago(String(a.decided_at))}${a.decided_by === sync.data?.client.principal_id ? ' on this client' : ' on another client'}` : null;
        const extra = () => ({ step_up: needsPin ? pin : undefined });
        const reread = [`/v1/approvals`, '/v1/attention', '/v1/missions'];
        const approve = (
          <ActionButton
            key="a"
            label={a.kind === 'plan' ? 'Approve plan' : 'Approve'}
            scope="approve"
            kind="primary"
            disabled={notEligible ?? cannotStepUp ?? (needsPin && pin.length < 6 ? 'Enter this client’s PIN first.' : null)}
            run={(key) => api.decideApproval(send(), a.id, decideBody(a, 'approve', key, extra()))}
            reread={reread}
          />
        );
        const reject = (
          <ActionButton
            key="r"
            label="Reject"
            scope="approve"
            kind={destructive ? 'danger' : 'secondary'}
            disabled={notEligible}
            run={(key) => api.decideApproval(send(), a.id, decideBody(a, 'reject', key))}
            reread={reread}
          />
        );
        return (
          <div className="approval" data-state={a.state}>
            <p className="ask">
              {p.scope ? <strong>Approve {p.scope}</strong> : null}
              {p.against?.mission ? <> for <a href={objectHref('mission', a.mission_id)}>{p.against.mission.title}</a></> : null}
              {p.against?.plan ? <> · plan v{p.against.plan.version}</> : null}
            </p>
            <table className="canonical">
              <caption className="sr">What exactly will happen</caption>
              <thead>
                <tr>
                  <th scope="col">Task</th>
                  <th scope="col">Class</th>
                  <th scope="col">Target</th>
                  <th scope="col">Policy</th>
                </tr>
              </thead>
              <tbody>
                {(p.what ?? []).map((w, i) => (
                  <tr key={i}>
                    <td className="mono">
                      {w.task}
                      {w.title ? ` · ${w.title}` : ''}
                    </td>
                    <td className="mono">{w.class}</td>
                    <td className="mono">{w.target ?? (w.paths ?? []).join(', ') ?? '—'}</td>
                    <td>
                      {w.decision}
                      {w.why ? ` — ${w.why}` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <KV
              rows={[
                ['Why it asks', p.why ?? '—'],
                ['If you approve', p.consequences?.approve ?? '—'],
                ['If you reject', p.consequences?.reject ?? '—'],
                ['Expires', `${a.expires_at} (${ago(a.expires_at)})`],
                ['Covers', p.reusable ?? '—'],
                ['Action hash', <span className="mono">{a.action_hash.slice(0, 16)}…</span>],
              ]}
            />
            {p.against?.plan?.summary ? (
              <p className="provenance">
                Plan summary, {p.against.plan.summary_by ?? 'model-written'}: {p.against.plan.summary}
              </p>
            ) : null}
            {needsPin && a.state === 'PENDING' ? (
              <label className="pin">
                This client’s PIN (step-up)
                <input inputMode="numeric" autoComplete="off" pattern="[0-9]*" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} maxLength={12} />
              </label>
            ) : null}
            {decided ? <p className="decided">{decided}</p> : null}
            <div className="row decide">{destructive ? [reject, approve] : [approve, reject]}</div>
            {a.kind === 'plan' && a.state === 'PENDING' && can('approve') ? (
              <RequestChanges approval={a} />
            ) : null}
          </div>
        );
      }}
    </Loadable>
  );
}

function RequestChanges({ approval }: { approval: Approval }) {
  const [note, setNote] = useState('');
  return (
    <div className="request-changes">
      <label>
        What should change? (the planner reads this)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
      </label>
      <ActionButton
        label="Request changes"
        scope="approve"
        disabled={note.trim() ? (approval.eligible ? null : 'Not decidable now.') : 'Say what should change.'}
        run={(key) => api.decideApproval(send(), approval.id, decideBody(approval, 'request_changes', key, { note }))}
        reread={['/v1/approvals', '/v1/attention', '/v1/missions']}
      />
    </div>
  );
}

function VerificationDecision({ item }: { item: AttentionItem }) {
  const [note, setNote] = useState('');
  const human = item.state === 'AWAITING_HUMAN';
  return (
    <div>
      <p>
        {human ? 'Nothing deterministic could check this: it waits for you to accept or reject the result.' : `The verifier broke (${item.reason ?? 'no reason'}) — this is not a failure of the work.`}{' '}
        <a href={objectHref('verification', item.ref.id)}>Evidence</a>
        {item.mission_id ? <> · <a href={objectHref('mission', item.mission_id, 'evidence')}>Mission</a></> : null}
      </p>
      {human ? (
        <>
          <label>
            Note (optional)
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="row">
            <ActionButton label="Accept result" scope="approve" kind="primary" run={(key) => api.decideVerification(send(), item.ref.id, { decision: 'accept', note, idempotency_key: key })} reread={['/v1/attention', '/v1/verifications', '/v1/missions']} />
            <ActionButton label="Reject result" scope="approve" run={(key) => api.decideVerification(send(), item.ref.id, { decision: 'reject', note, idempotency_key: key })} reread={['/v1/attention', '/v1/verifications', '/v1/missions']} />
          </div>
        </>
      ) : null}
    </div>
  );
}

function KnowledgeProposal({ item }: { item: AttentionItem }) {
  return (
    <div>
      <p>
        Remember: <strong>{item.reason}</strong> ({item.reason_code.toLowerCase()}) ·{' '}
        <a href={objectHref('knowledge_item', item.ref.id)}>Provenance</a>
      </p>
      <div className="row">
        <ActionButton label="Confirm" scope="control" kind="primary" run={(key) => api.confirmKnowledge(send(), item.ref.id, { idempotency_key: key })} reread={['/v1/attention', '/v1/knowledge']} />
        <ActionButton label="Dismiss" scope="control" run={(key) => api.rejectKnowledge(send(), item.ref.id, { idempotency_key: key })} reread={['/v1/attention', '/v1/knowledge']} />
      </div>
    </div>
  );
}
