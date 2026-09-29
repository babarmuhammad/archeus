// Now (p16-design-gate §6.10, §5): the return — the presence line, what
// changed since you last looked (the digest), what is happening, the top of
// Attention, and the conversation. Composed from three reads (S5).
import { useState } from 'react';
import { api, SETTLED, type Digest, type Message, type MessageList, type MissionList } from '../api/generated';
import { send } from '../data/core';
import { useRead } from '../data/cache';
import { objectHref } from '../nav/destinations';
import { ago } from '../state/present';
import { ActionButton, Empty, Fresh, Loadable, RefLabel, Section, StateBadge } from '../components/ui';
import { AttentionView } from './Attention';
import { MissionRow } from './Work';
import type { Attention as AttentionT } from '../api/generated';

const HEADLINE: Record<string, string> = {
  needs_you: 'needs you',
  drift_found: 'drift found',
  failed: 'failed',
  completed: 'completed',
  drift_cleared: 'drift cleared',
  progressed: 'progressed',
};

export function NowView() {
  const missions = useRead<MissionList>('/v1/missions');
  const att = useRead<AttentionT>('/v1/attention');
  const active = (missions.data?.missions ?? []).filter((m) => !SETTLED.includes(m.state));
  const needs = att.data?.count ?? 0;
  return (
    <div className="view now">
      <h1 tabIndex={-1}>Now</h1>
      <p className="presence" aria-live="off">
        Archeus · {active.length} {active.length === 1 ? 'mission' : 'missions'} active · {needs} {needs === 1 ? 'thing needs' : 'things need'} you
      </p>
      <div className="now-grid">
        <div className="now-main">
          <DigestSection />
          <Section title="Happening now" actions={<Fresh snap={missions} />}>
            <Loadable snap={missions} what="the missions">
              {() =>
                active.length ? (
                  <ul className="rows">
                    {active.map((m) => (
                      <MissionRow key={m.id} m={m} />
                    ))}
                  </ul>
                ) : (
                  <Empty>Nothing is in progress. Tell Archeus what you want below.</Empty>
                )
              }
            </Loadable>
          </Section>
          <Section title="Needs you">
            <AttentionView limit={3} heading={false} />
          </Section>
        </div>
        <Conversation />
      </div>
    </div>
  );
}

function DigestSection() {
  const d = useRead<Digest>('/v1/digest');
  return (
    <Loadable snap={d} what="the digest">
      {(g) =>
        g.count === 0 ? null : (
          <Section
            title={`Since you last looked · ${g.count} ${g.count === 1 ? 'change' : 'changes'}`}
            actions={
              <ActionButton
                label="Dismiss"
                scope="control"
                run={() => api.ackDigest(send(), { up_to_seq: g.up_to_seq })}
                reread={['/v1/digest']}
              />
            }
          >
            {g.truncated ? <p className="hint">Some older events are no longer kept; this is what remains.</p> : null}
            <ul className="digest">
              {g.groups.map((x) => (
                <li key={x.ref.kind + x.ref.id} data-headline={x.headline} className="thread-rule">
                  <a href={objectHref(x.ref.kind, x.ref.id)}>
                    <RefLabel kind={x.ref.kind} id={x.ref.id} />
                  </a>{' '}
                  {HEADLINE[x.headline] ?? x.headline} · {x.count} {x.count === 1 ? 'event' : 'events'}
                </li>
              ))}
            </ul>
          </Section>
        )
      }
    </Loadable>
  );
}

/** The primary conversation (§5): a surface, not the application. A card shows
 * the live row its ref names, never a copy from the message. */
function Conversation() {
  const msgs = useRead<MessageList>('/v1/conversations/primary/messages');
  const [text, setText] = useState('');
  const [sent, setSent] = useState<string | null>(null);
  const list = msgs.data?.messages ?? [];
  const shown = list.slice(-100);
  return (
    <section className="conversation" aria-label="Conversation with Archeus">
      <h2>Conversation</h2>
      <Loadable snap={msgs} what="the conversation">
        {() =>
          shown.length ? (
            <ol className="messages">
              {list.length > shown.length ? <li className="hint">{list.length - shown.length} older messages are not shown.</li> : null}
              {shown.map((m) => (
                <MessageRow key={m.id} m={m} />
              ))}
            </ol>
          ) : (
            <Empty>No messages yet. Tell Archeus what you want.</Empty>
          )
        }
      </Loadable>
      {sent ? <p className="hint" role="status">Sent — Archeus is reading it.</p> : null}
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
        }}
      >
        <label htmlFor="composer" className="sr">
          Tell Archeus what you want
        </label>
        <textarea id="composer" rows={2} value={text} placeholder="Tell Archeus what you want…" onChange={(e) => setText(e.target.value)} />
        <ActionButton
          label="Send"
          scope="control"
          kind="primary"
          disabled={text.trim() ? null : 'Write a message first.'}
          run={(key) => api.postMessage(send(), 'primary', { text, idempotency_key: key })}
          reread={['/v1/conversations/primary/messages']}
          onDone={() => {
            setSent(text);
            setText('');
          }}
        />
      </form>
    </section>
  );
}

function MessageRow({ m }: { m: Message }) {
  const archeus = m.author === 'archeus';
  return (
    <li className={`msg ${m.author}`} aria-roledescription={archeus ? 'AI-generated message' : undefined}>
      <span className="who">{archeus ? 'Archeus' : m.author === 'user' ? 'You' : 'System'}</span>
      <p className="text">{m.text}</p>
      {m.cards.length ? (
        <div className="cards">
          {m.cards.map((c, i) => (
            <CardRef key={i} type={c.type} kind={c.ref.kind} id={c.ref.id} intent={m.intent_id ?? undefined} />
          ))}
        </div>
      ) : null}
      <span className="age">{ago(String(m.created_at ?? ''))}</span>
    </li>
  );
}

/** A card is a link to the live object, labelled by its type. Challenge and
 * clarification cards answer through P7's command. */
function CardRef({ type, kind, id, intent }: { type: string; kind: string; id: string; intent?: string }) {
  const [answer, setAnswer] = useState('');
  if ((type === 'challenge' || type === 'clarification') && kind === 'intent') {
    return (
      <article className="card" aria-label={type}>
        <p>{type === 'challenge' ? 'Archeus disagrees with what is recorded. Keep going, or drop it?' : 'Archeus needs an answer before it can start.'}</p>
        {type === 'challenge' ? (
          <div className="row">
            <ActionButton label="Proceed anyway" scope="control" run={(key) => api.clarifyIntent(send(), id, { choice: 'proceed', idempotency_key: key })} reread={['/v1/conversations/primary/messages']} />
            <ActionButton label="Drop it" scope="control" run={(key) => api.clarifyIntent(send(), id, { choice: 'drop', idempotency_key: key })} reread={['/v1/conversations/primary/messages']} />
          </div>
        ) : (
          <div className="row">
            <label>
              Your answer
              <input value={answer} onChange={(e) => setAnswer(e.target.value)} />
            </label>
            <ActionButton label="Answer" scope="control" disabled={answer.trim() ? null : 'Write an answer first.'} run={(key) => api.clarifyIntent(send(), id, { text: answer, idempotency_key: key })} reread={['/v1/conversations/primary/messages']} />
          </div>
        )}
        {intent ? null : null}
      </article>
    );
  }
  return (
    <a className="card" href={objectHref(kind, id)} aria-label={`${type.replace('_', ' ')}: ${kind} ${id}`}>
      <span className="card-type">{type.replace('_', ' ')}</span> <span className="mono">{kind} {id}</span>
      {kind === 'mission' ? <LiveMission id={id} /> : null}
    </a>
  );
}

function LiveMission({ id }: { id: string }) {
  const m = useRead<{ state: string; title: string }>(`/v1/missions/${id}`);
  return m.data ? (
    <span>
      {' '}
      · {m.data.title} <StateBadge machine="mission" state={m.data.state} />
    </span>
  ) : null;
}
