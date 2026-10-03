// Now (p16-design-gate §6.10, §5; ADR-0027 §4-5, rulebook §9): the operational
// surface — the state sentence, then at most seven blocks in ADR-0027's order:
// needs you, happening now, since you last looked, upcoming, recent decisions,
// the live map and the conversation. Composed from Core's reads (S5).
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { paths, api, type Approval, type ApprovalList, type Sync, type AutomationList, type Digest, type KnowledgeList, type Message, type MessageList, type MissionList, type RouteDecision, type RouteDecisionList, type Status } from '../api/generated';
import { announce } from '../a11y/announce';
import { send } from '../data/core';
import { store, useRead } from '../data/cache';
import { LiveMap } from '../graph/GraphView';
import { reducedMotion } from '../graph/loop';
import { MAP_MIN_WIDTH, useWide } from '../graph/wide';
import { objectHref } from '../nav/destinations';
import { activeMissions, automationLine, mapSeeds, recentDecisions, stateSentence, upcoming } from '../state/now';
import { ago } from '../state/present';
import { lineBetween, linksOf, messageHeard, targetOf, threadWords, type Ref } from '../state/thread';
import { timeline } from '../state/timeline';
import { ActionButton, Changed, Empty, Fresh, Loadable, RefLabel, Section, StateBadge, refName, thread, useChanged } from '../components/ui';
import { AttentionView } from './Attention';
import { MissionRow } from './Work';
import type { Attention as AttentionT } from '../api/generated';

// the messages a stream frame said arrived (message id → the frame's seq),
// waiting for the re-read that brings them; each is handled once
const heard = new Map<string, number>();
const handled = new Set<string>();
store.onFrame((f) => {
  const id = messageHeard(f);
  if (id && !handled.has(id)) heard.set(id, f.id!);
});

/** A linked object's row in *scope* (Now's main column, or a mission's Now
 * tab), when it is on screen: a mission's own row first, else any row that
 * names the object. */
function rowOf(r: Ref, scope: string): Element | null {
  const main = document.querySelector(scope);
  const all = (q: string) => (main ? [...main.querySelectorAll(q)] : []);
  const rows = [...(r.kind === 'mission' ? all(`li[data-mission="${r.id}"]`) : []), ...all(`[data-ref="${r.kind}:${r.id}"]`)];
  return rows.find((e) => {
    if (e.closest('.conversation')) return false; // a message's own card is not a row
    const b = e.getBoundingClientRect();
    return b.width > 0 && b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth;
  }) ?? null;
}

const HEADLINE: Record<string, string> = {
  needs_you: 'needs you',
  drift_found: 'drift found',
  failed: 'failed',
  completed: 'completed',
  drift_cleared: 'drift cleared',
  progressed: 'progressed',
};

export function NowView() {
  const missions = useRead<MissionList>(paths.listMissions());
  const att = useRead<AttentionT>(paths.attentionItems());
  const all = missions.data?.missions ?? [];
  const active = activeMissions(all);
  const next = upcoming(all);
  const needs = att.data?.count ?? 0;
  const mapFits = useWide(MAP_MIN_WIDTH);
  return (
    <div className="view now">
      <h1 tabIndex={-1}>Now</h1>
      <p className="state-sentence" data-state-sentence="" aria-live="off">
        {missions.data && att.data ? stateSentence(active.length, needs) : null}
      </p>
      <AutomationLine />
      <div className="now-grid">
        <div className="now-main">
          <Section title="Needs you">
            <AttentionView limit={3} heading={false} />
          </Section>
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
          <DigestSection />
          {next.length ? (
            <Section title="Upcoming">
              <ul className="rows" data-now="upcoming">
                {next.map((m) => (
                  <MissionRow key={m.id} m={m} />
                ))}
              </ul>
            </Section>
          ) : null}
          <Decisions />
        </div>
        <div className="now-side">
          {mapFits && active.length ? <MapSection missions={all} /> : null}
          <Conversation />
        </div>
      </div>
    </div>
  );
}

/** The background automation line (rulebook §9): quiet, and a link to them. */
function AutomationLine() {
  const a = useRead<AutomationList>(paths.listAutomations());
  const line = a.data ? automationLine(a.data.automations) : null;
  return line ? (
    <p className="automation-line" data-automation-line="">
      <a href="#/control/automations">{line}</a>
    </p>
  ) : null;
}

/** Recent decisions (rulebook §9, O-6): each row names its object and links it. */
function Decisions() {
  const ap = useRead<ApprovalList>(paths.listApprovals());
  const rd = useRead<RouteDecisionList>(paths.listRouteDecisions());
  const kn = useRead<KnowledgeList>(paths.listKnowledge({ type: 'DECISION', state: 'CONFIRMED' }));
  const changed = useChanged();
  const rows = ap.data && rd.data && kn.data ? recentDecisions(ap.data.approvals, rd.data.route_decisions, kn.data.knowledge) : [];
  return rows.length ? (
    <Section title="Recent decisions">
      <ul className="rows" data-now="decisions">
        {rows.map((d) => (
          <li key={d.kind + d.id} className="row-item" data-ref={`${d.kind}:${d.id}`} {...thread(changed(d.kind, d.id))}>
            <a href={objectHref(d.kind, d.id)}>
              <RefLabel kind={d.kind} id={d.id} />
            </a>
            {d.mission ? (
              <>
                {' '}
                for{' '}
                <a href={objectHref('mission', d.mission)}>
                  <RefLabel kind="mission" id={d.mission} />
                </a>
              </>
            ) : null}{' '}
            · {d.words} <span className="age">{ago(d.at)}</span>
            <Changed on={changed(d.kind, d.id)} />
          </li>
        ))}
      </ul>
    </Section>
  ) : null;
}

/** The live map's block: its seeds are the active missions, its live set the
 * attempts Core's status lists — the same derivation the strip counts. */
function MapSection({ missions }: { missions: MissionList['missions'] }) {
  const status = useRead<Status>(paths.status());
  const seeds = mapSeeds(missions);
  const ids = (status.data?.live ?? []).map((x) => x.id);
  const key = ids.join();
  const live = useMemo(() => new Set(ids), [key]);
  return (
    <Section title="Live map" actions={<Fresh snap={status} />}>
      <LiveMap seeds={seeds} live={live} />
    </Section>
  );
}

function DigestSection() {
  const d = useRead<Digest>(paths.digest());
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
                reread={[paths.digest()]}
              />
            }
          >
            {g.truncated ? <p className="hint">Some older events are no longer kept; this is what remains.</p> : null}
            <ul className="digest">
              {g.groups.map((x) => (
                <li key={x.ref.kind + x.ref.id} data-headline={x.headline} data-ref={`${x.ref.kind}:${x.ref.id}`} className="thread-rule">
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

/** A conversation (§5): the primary one on Now, a mission's own thread on its
 * Now tab (P19 S1; a mission's id names its thread). A surface, not the
 * application. A card shows the live row its ref names, never a copy. */
export function Conversation({ conversation = 'primary', scope = '.now-main', title = 'Conversation', label = 'Conversation with Archeus' }: { conversation?: string; scope?: string; title?: string; label?: string }) {
  const msgs = useRead<MessageList>(paths.listMessages(conversation));
  const [text, setText] = useState('');
  const [sent, setSent] = useState<string | null>(null);
  const list = msgs.data?.messages ?? [];
  const shown = list.slice(-100);
  const [line, setLine] = useState<{ key: string; to: Ref } | null>(null);
  const endLine = useCallback(() => setLine(null), []);
  // T1: a message heard arriving, now read, is said in words and, when a row
  // of what it touched is on screen, draws its line — once, one at a time
  useEffect(() => {
    for (const m of list) {
      const seq = heard.get(m.id);
      if (seq === undefined) continue;
      heard.delete(m.id);
      handled.add(m.id);
      const links = m.author === 'archeus' ? linksOf(m.links) : [];
      if (!links.length) continue;
      void Promise.all(links.map((l) => refName(l.kind, l.id))).then((names) => announce(threadWords(names)));
      const target = targetOf(links, (r) => rowOf(r, scope) !== null);
      if (!target || !timeline.start('thread-travel', 'message:' + m.id, seq, performance.now(), reducedMotion())) continue;
      setLine({ key: m.id, to: target });
    }
  }, [list, scope]);
  return (
    <section className="conversation" aria-label={label}>
      <h2>{title}</h2>
      <Loadable snap={msgs} what="the conversation">
        {() =>
          shown.length ? (
            <ol className="messages">
              {list.length > shown.length ? <li className="hint">{list.length - shown.length} older messages are not shown.</li> : null}
              {shown.map((m) => (
                <MessageRow key={m.id} m={m} conversation={conversation} />
              ))}
            </ol>
          ) : (
            <Empty>No messages yet. Tell Archeus what you want.</Empty>
          )
        }
      </Loadable>
      {line ? <ThreadLine key={line.key} from={line.key} to={line.to} scope={scope} onEnd={endLine} /> : null}
      {sent ? <p className="hint" role="status">Sent — Archeus is reading it.</p> : null}
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
        }}
      >
        <label htmlFor={composerId(conversation)} className="sr">
          Tell Archeus what you want
        </label>
        <textarea id={composerId(conversation)} rows={2} value={text} placeholder="Tell Archeus what you want…" onChange={(e) => setText(e.target.value)} />
        <ActionButton
          label="Send"
          scope="control"
          kind="primary"
          disabled={text.trim() ? null : 'Write a message first.'}
          run={(key) => api.postMessage(send(), conversation, { text, idempotency_key: key })}
          reread={[paths.listMessages(conversation)]}
          onDone={() => {
            setSent(text);
            setText('');
          }}
        />
      </form>
    </section>
  );
}

/** The composer's id: the primary one keeps the id it always had. */
const composerId = (c: string) => (c === 'primary' ? 'composer' : `composer-${c}`);

/** The line itself, measured in the layout pass just before it is painted, so
 * it starts where the message and the row are when it first shows. */
function ThreadLine({ from, to, scope, onEnd }: { from: string; to: Ref; scope: string; onEnd: () => void }) {
  const el = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    // placed again whenever the page moves under it (a re-read adding a row
    // above the target): its place is set, never animated
    const place = () => {
      const a = document.querySelector(`[data-message="${from}"]`);
      const b = rowOf(to, scope);
      if (!a || !b || !el.current) return false;
      const l = lineBetween(a.getBoundingClientRect(), b.getBoundingClientRect());
      Object.assign(el.current.style, { left: `${l.x}px`, top: `${l.y}px`, width: `${l.length}px` });
      el.current.style.setProperty('--angle', `${l.angle}rad`);
      return true;
    };
    if (!place()) return onEnd();
    const ro = new ResizeObserver(() => void place());
    const mo = new MutationObserver(() => void place());
    document.querySelectorAll(`${scope}, .conversation`).forEach((e) => {
      ro.observe(e);
      mo.observe(e, { childList: true, subtree: true });
    });
    return () => {
      ro.disconnect();
      mo.disconnect();
    };
  }, [from, to, onEnd]);
  // in the body: a size container (the inspector) is the containing block of a
  // fixed descendant, which would place the line by the panel, not the viewport
  return createPortal(<span ref={el} className="thread-line" data-thread-line={from} aria-hidden="true" onAnimationEnd={onEnd} />, document.body);
}

function MessageRow({ m, conversation }: { m: Message; conversation: string }) {
  const archeus = m.author === 'archeus';
  const changed = useChanged();
  // a link no card already shows is shown as one: the thread's object, by name
  const bare = linksOf(m.links).filter((l) => !m.cards.some((c) => c.ref.kind === l.kind && c.ref.id === l.id));
  return (
    <li className={`msg ${m.author}`} data-message={m.id} aria-roledescription={archeus ? 'AI-generated message' : undefined}>
      <span className="who">{archeus ? 'Archeus' : m.author === 'user' ? 'You' : 'System'}</span>
      <p className="text">{m.text}</p>
      {m.cards.length || bare.length ? (
        <div className="cards">
          {m.cards.map((c, i) => (
            <CardRef key={i} type={c.type} kind={c.ref.kind} id={c.ref.id} intent={m.intent_id ?? undefined} changed={changed(c.ref.kind, c.ref.id)} conversation={conversation} message={m.id} />
          ))}
          {bare.map((l) => (
            <a key={l.kind + l.id} className="card" href={objectHref(l.kind, l.id)} data-ref={`${l.kind}:${l.id}`} {...thread(changed(l.kind, l.id))}>
              <RefLabel kind={l.kind} id={l.id} />
              <Changed on={changed(l.kind, l.id)} />
            </a>
          ))}
        </div>
      ) : null}
      <span className="age">{ago(String(m.created_at ?? ''))}</span>
    </li>
  );
}

/** A card is a link to the live object, labelled by its type. Challenge and
 * clarification cards answer through P7's command. */
function CardRef({ type, kind, id, intent, changed, conversation, message }: { type: string; kind: string; id: string; intent?: string; changed: boolean; conversation: string; message: string }) {
  const [answer, setAnswer] = useState('');
  if ((type === 'challenge' || type === 'clarification') && kind === 'intent') {
    return (
      <article className="card" aria-label={type}>
        <p>{type === 'challenge' ? 'Archeus disagrees with what is recorded. Keep going, or drop it?' : 'Archeus needs an answer before it can start.'}</p>
        {type === 'challenge' ? (
          <div className="row">
            <ActionButton label="Proceed anyway" scope="control" run={(key) => api.clarifyIntent(send(), id, { choice: 'proceed', idempotency_key: key })} reread={[paths.listMessages(conversation)]} />
            <ActionButton label="Drop it" scope="control" run={(key) => api.clarifyIntent(send(), id, { choice: 'drop', idempotency_key: key })} reread={[paths.listMessages(conversation)]} />
          </div>
        ) : (
          <div className="row">
            <label>
              Your answer
              <input value={answer} onChange={(e) => setAnswer(e.target.value)} />
            </label>
            <ActionButton label="Answer" scope="control" disabled={answer.trim() ? null : 'Write an answer first.'} run={(key) => api.clarifyIntent(send(), id, { text: answer, idempotency_key: key })} reread={[paths.listMessages(conversation)]} />
          </div>
        )}
        {intent ? null : null}
      </article>
    );
  }
  if (type === 'approval' && kind === 'approval') return <ChatApproval id={id} conversation={conversation} />;
  if (type === 'estop') return <ChatEstop />;
  if (type === 'stop' && kind === 'mission') return <ChatStop id={id} conversation={conversation} message={message} />;
  if (type === 'route_explanation' && kind === 'route_decision') return <ChatRouteExplanation id={id} />;
  return (
    <a className="card" href={objectHref(kind, id)} data-ref={`${kind}:${id}`} {...thread(changed)}>
      <span className="card-type">{type.replace('_', ' ')}</span> {kind === 'mission' ? <LiveMission id={id} /> : <RefLabel kind={kind} id={id} />}
      <Changed on={changed} />
    </a>
  );
}

/** An approval asked for, in the conversation (P19 S3): Approve or Reject
 * here sends the turn with this card's hash and version, and Core decides it
 * exactly as Attention's buttons do (G1). A step-up is given in Attention. */
function ChatApproval({ id, conversation }: { id: string; conversation: string }) {
  const s = useRead<Approval>(paths.getApproval(id));
  const me = useRead<Sync>(paths.sync());
  const a = s.data;
  if (!a) return <RefLabel kind="approval" id={id} />;
  // a local client's step-up is being local; a PIN is asked for in Attention
  const capability = me.data?.client.capabilities.step_up;
  const stepUp = !a.step_up ? null : capability === 'pin' ? 'It needs this client’s PIN, which Attention asks for.' : capability === 'none' ? 'This client has no PIN: it cannot satisfy a step-up.' : null;
  const scope = typeof a.presented.scope === 'string' ? a.presented.scope : a.kind;
  const closed =
    a.state !== 'PENDING' ? `This approval is ${a.state.toLowerCase()}.` : !a.eligible ? `Not decidable now: ${a.eligible_why ?? 'no reason given'}.` : stepUp;
  const decision = { approval_id: a.id, action_hash: a.action_hash, expected_version: a.version };
  const reread = [paths.listMessages(conversation), paths.getApproval(id), paths.attentionItems(), paths.listMissions()];
  return (
    <article className="card" aria-label="approval" data-approval={a.id} data-state={a.state}>
      <p>Approve {scope}?</p>
      {closed ? (
        <p className="hint">
          {closed} {a.state === 'PENDING' && capability === 'pin' && a.step_up ? <a href="#/attention">Open Attention</a> : null}
        </p>
      ) : (
        <div className="row">
          <ActionButton label="Approve" scope="approve" kind="primary" run={(key) => api.postMessage(send(), conversation, { text: 'approve', decision, idempotency_key: key })} reread={reread} />
          <ActionButton label="Reject" scope="approve" confirm="Reject what this approval asks. A decided approval cannot be changed." run={(key) => api.postMessage(send(), conversation, { text: 'reject', decision, idempotency_key: key })} reread={reread} />
        </div>
      )}
    </article>
  );
}

/** `emergency stop` said in the conversation (P19 B10): the card is its
 * confirmation and runs the strip's own command (G2). */
function ChatEstop() {
  const st = useRead<Status>(paths.status());
  return (
    <article className="card" aria-label="emergency stop">
      <p>Every running execution is killed now and Archeus refuses new work until you re-arm it. Missions are not lost; they wait.</p>
      {st.data && !st.data.armed ? (
        <p className="hint">The emergency stop is engaged.</p>
      ) : (
        <div className="row">
          <ActionButton label="Emergency stop" scope="control" kind="danger" run={(key) => api.estop(send(), { idempotency_key: key })} reread={['/v1']} />
        </div>
      )}
    </article>
  );
}

/** `stop` on a running mission (P19 B10, C-33): one card that, confirmed,
 * pauses then cancels it; Core does both in the confirming turn. */
function ChatStop({ id, conversation, message }: { id: string; conversation: string; message: string }) {
  const m = useRead<{ state: string; title: string }>(paths.getMission(id));
  const open = m.data && (m.data.state === 'EXECUTING' || m.data.state === 'PAUSED');
  return (
    <article className="card" aria-label="stop mission" data-ref={`mission:${id}`}>
      <p>
        Stop {m.data ? `“${m.data.title}”` : 'this mission'}: it is paused, then cancelled. A cancelled mission does not come back.
      </p>
      {m.data && !open ? (
        <p className="hint">
          This mission is {m.data.state.toLowerCase()}. <StateBadge machine="mission" state={m.data.state} />
        </p>
      ) : (
        <div className="row">
          <ActionButton label="Stop mission" scope="control" kind="danger" run={(key) => api.postMessage(send(), conversation, { text: 'stop', confirm: { message_id: message }, idempotency_key: key })} reread={[paths.listMessages(conversation), paths.getMission(id), paths.listMissions()]} />
        </div>
      )}
    </article>
  );
}

/** `why`'s card (P19 B10, G5): the RouteDecision itself, read from Core. */
function ChatRouteExplanation({ id }: { id: string }) {
  const rd = useRead<RouteDecision>(paths.getRouteDecision(id));
  return (
    <a className="card" href={objectHref('route_decision', id)} data-ref={`route_decision:${id}`} aria-label="route explanation">
      <span className="card-type">route explanation</span> {rd.data ? rd.data.explanation : <RefLabel kind="route_decision" id={id} />}
    </a>
  );
}

function LiveMission({ id }: { id: string }) {
  const m = useRead<{ state: string; title: string }>(paths.getMission(id));
  return m.data ? (
    <span>
      {' '}
      · {m.data.title} <StateBadge machine="mission" state={m.data.state} />
    </span>
  ) : null;
}
