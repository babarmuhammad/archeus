// Work (p16-design-gate §4.1, §6.1): every mission, grouped by what it waits
// on; ideas; missions an automation started say so and link their run.
import { paths, api, type Attention, type IdeaList, type Mission, type MissionList, type Status } from '../api/generated';
import { useRead, type Snapshot } from '../data/cache';
import { send } from '../data/core';
import { objectHref } from '../nav/destinations';
import { ago, present, statusLine } from '../state/present';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ActionButton, ActivityChips, ChipAnnouncer, Changed, Empty, Fresh, Loadable, RefLabel, RowPulse, Section, StateBadge, thread, useChanged } from '../components/ui';
import { pins } from '../state/pins';
import { ideaSteps } from '../state/ideas';
import { MissionActions } from './Mission';

const GROUPS: { id: string; title: string; classes: string[] }[] = [
  { id: 'needs', title: 'Needs you', classes: ['needs_you'] },
  { id: 'active', title: 'Active', classes: ['active', 'verifying', 'reviewing', 'approved'] },
  { id: 'planning', title: 'Planning', classes: ['planning'] },
  { id: 'blocked', title: 'Blocked', classes: ['blocked'] },
  { id: 'paused', title: 'Paused', classes: ['paused'] },
  { id: 'done', title: 'Done', classes: ['done'] },
  { id: 'ended', title: 'Failed or cancelled', classes: ['failed', 'inactive'] },
];
const PAGE = 50;

/** A mission's group: its state's class — except that a mission Attention
 * holds an item for is under Needs you, whatever its state says (§6.1). */
export function groupOf(m: Mission, waiting: Set<string>): string {
  const cls = present('mission', m.state).cls;
  if (waiting.has(m.id) && cls !== 'done' && cls !== 'inactive' && cls !== 'failed') return 'needs';
  return GROUPS.find((g) => g.classes.includes(cls))?.id ?? 'ended';
}

function usePinned(id: string): boolean {
  return useSyncExternalStore(
    (l) => pins.subscribe(l),
    () => pins.has(id),
  );
}

/** Pin or unpin a mission (D-9): a local preference, never sent to Core. */
export function PinButton({ m }: { m: Mission }) {
  const on = usePinned(m.id);
  return (
    <button type="button" className="btn secondary pin" aria-pressed={on} aria-label={`${on ? 'Unpin' : 'Pin'} “${m.title}”`} onClick={() => pins.toggle(m.id)}>
      {on ? 'Unpin' : 'Pin'}
    </button>
  );
}

/** A row's actions as a menu (rulebook §10, §20): right-click, Shift+F10 or
 * the menu key — the browser sends all three as one contextmenu event. It holds exactly what is offered elsewhere — Open, Pin and the
 * inspector's own Pause / Resume / Stop, by the same buttons — so nothing is
 * only here. Esc or leaving it closes it; Esc returns to the row. */
function RowMenu({ m, close }: { m: Mission; close: (back: boolean) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const modal = () => !!box.current?.querySelector('dialog[open]');
  // focus moves in, so leaving it — a press outside, Tab — is a blur
  useEffect(() => box.current?.querySelector<HTMLElement>('a, button:not([disabled])')?.focus(), []);
  return (
    <div
      ref={box}
      className="row-menu"
      role="dialog"
      aria-label={`Actions for “${m.title}”`}
      data-row-menu=""
      onKeyDown={(e) => {
        if (e.key !== 'Escape' || modal()) return;
        e.stopPropagation();
        close(true);
      }}
      onBlur={(e) => !box.current?.contains(e.relatedTarget as Node) && !modal() && close(false)}
    >
      <a href={objectHref('mission', m.id)}>Open</a>
      <PinButton m={m} />
      <MissionActions mission={m} />
    </div>
  );
}

export function MissionRow({ m, waiting, actions, pinned }: { m: Mission; waiting?: boolean; actions?: boolean; pinned?: boolean }) {
  const changed = useChanged()('mission', m.id);
  const [menu, setMenu] = useState(false);
  const link = useRef<HTMLAnchorElement>(null);
  const close = (back: boolean) => {
    setMenu(false);
    if (back) link.current?.focus();
  };
  return (
    <li
      className="row-item"
      data-mission={m.id}
      data-state={m.state}
      data-pinned={pinned || undefined}
      {...thread(changed)}
      onContextMenu={actions ? (e) => (e.preventDefault(), setMenu(true)) : undefined}
    >
      <RowPulse mission={m.id} />
      <a
        ref={link}
        href={objectHref('mission', m.id)}
        className="row-link"
        aria-keyshortcuts={actions ? 'Shift+F10' : undefined}
      >
        <StateBadge machine="mission" state={m.state} />
        <span className="title">{m.title}</span>
        {waiting ? <span className="tag attention">waiting on you</span> : null}
        <span className="status">{statusLine(m)}</span>
        <ActivityChips mission={m.id} />
        {m.origin === 'automation' ? <span className="tag">from an automation</span> : null}
        {m.priority ? <span className="tag" data-priority={m.priority}>priority {m.priority}</span> : null}
        <span className="age">{ago(m.updated_at)}</span>
        <Changed on={changed} />
      </a>
      <ChipAnnouncer mission={m.id} />
      {actions ? <PinButton m={m} /> : null}
      {menu ? <RowMenu m={m} close={close} /> : null}
    </li>
  );
}

const ALL_REREAD = [paths.listMissions(), paths.status(), paths.attentionItems(), paths.digest()];

/** Pause all and Resume all (P19.5 R10a): Core's two workspace verbs, the same
 * on the strip and on Work. Pause all pauses the missions executing now; it is
 * not the emergency stop, and an approved mission may still start after it.
 * Resume all is offered only while Core's status names missions it would
 * resume (`resumable`, the newest Pause all's missions still paused by it);
 * the client keeps nothing about batches. */
export function PauseAll({ status }: { status: Snapshot<Status> }) {
  return (
    <>
      <ActionButton label="Pause all" scope="control" run={(key) => api.pauseAll(send(), { idempotency_key: key })} reread={ALL_REREAD} />
      {status.data?.resumable.length ? (
        <ActionButton label="Resume all" scope="control" run={(key) => api.resumeAll(send(), { idempotency_key: key })} reread={ALL_REREAD} />
      ) : null}
    </>
  );
}

export function WorkView({ project }: { project?: string }) {
  const snap = useRead<MissionList>(project ? paths.listMissions({ project: project }) : paths.listMissions());
  const att = useRead<Attention>(paths.attentionItems());
  const status = useRead<Status>(paths.status());
  const waiting = new Set((att.data?.items ?? []).map((i) => i.mission_id).filter(Boolean) as string[]);
  return (
    <div className="view">
      <h1 tabIndex={-1}>Work</h1>
      <Fresh snap={snap} />
      {/* both verbs are workspace-wide: a project's Work does not offer them */}
      {project ? null : (
        <div className="row actions" data-pause-all>
          <PauseAll status={status} />
        </div>
      )}
      <Loadable snap={snap} what="the missions">
        {(l) =>
          l.missions.length ? (
            <>
              <Pinned missions={l.missions} waiting={waiting} />
              {GROUPS.map((g) => {
                const ms = l.missions
                  .filter((m) => groupOf(m, waiting) === g.id)
                  .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
                return ms.length ? (
                  <Section key={g.id} title={`${g.title} · ${ms.length}`}>
                    <ul className="rows">
                      {ms.slice(0, PAGE).map((m) => (
                        <MissionRow key={m.id} m={m} waiting={waiting.has(m.id)} actions />
                      ))}
                    </ul>
                    {ms.length > PAGE ? <p className="hint">{ms.length - PAGE} more not shown.</p> : null}
                  </Section>
                ) : null;
              })}
            </>
          ) : (
            <Empty>No missions yet. Tell Archeus what you want on Now.</Empty>
          )
        }
      </Loadable>
      <Ideas />
    </div>
  );
}

/** D-9: the pinned missions Work lists, at its top, oldest pin first — the
 * same rows, also in their own groups. */
function Pinned({ missions, waiting }: { missions: Mission[]; waiting: Set<string> }) {
  const ids = useSyncExternalStore(
    (l) => pins.subscribe(l),
    () => pins.list(),
  );
  const ms = ids.map((id) => missions.find((m) => m.id === id)).filter((m): m is Mission => !!m);
  return ms.length ? (
    <Section title={`Pinned · ${ms.length}`} id="pinned">
      <ul className="rows">
        {ms.map((m) => (
          <MissionRow key={m.id} m={m} waiting={waiting.has(m.id)} actions pinned />
        ))}
      </ul>
    </Section>
  ) : null;
}

/** Where an idea is on Core's path (rulebook §43; D-11): read-only — Core has
 * no idea-transition command, so no step is a button. */
function IdeaPath({ state }: { state: string }) {
  const { path, aside } = ideaSteps(state);
  return (
    <>
      <ol className="stepper" aria-label="Where this idea is on its path" data-stepper="">
        {path.map((s) => (
          <li key={s.state} data-step={s.state} data-at={s.at} aria-current={s.at === 'now' ? 'step' : undefined}>
            {s.label}
          </li>
        ))}
      </ol>
      {aside ? <p className="hint" data-aside="">Set aside: {aside.toLowerCase()}. Reviving it takes it back to Captured.</p> : null}
    </>
  );
}

function Ideas() {
  const snap = useRead<IdeaList>(paths.listIdeas());
  const ideas = snap.data?.ideas ?? [];
  const changed = useChanged();
  if (!ideas.length) return null;
  return (
    <Section title={`Ideas · ${ideas.length}`}>
      <ul className="rows">
        {ideas.map((i) => (
          <li key={i.id} className="row-item" data-idea={i.id} {...thread(changed('idea', i.id))}>
            <StateBadge machine="idea" state={i.state} /> <span className="title">{i.title || i.text}</span>
            <Changed on={changed('idea', i.id)} />
            <IdeaPath state={i.state} />
            <p className="hint" data-idea-evidence="">
              {i.origin_message_id ? 'Captured from the conversation.' : 'Captured.'}{' '}
              {i.promoted_mission_id ? (
                <>
                  Made into <a href={objectHref('mission', i.promoted_mission_id)}><RefLabel kind="mission" id={i.promoted_mission_id} /></a>.
                </>
              ) : null}
            </p>
          </li>
        ))}
      </ul>
    </Section>
  );
}
