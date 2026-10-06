// Work (p16-design-gate §4.1, §6.1): every mission, grouped by what it waits
// on; ideas; missions an automation started say so and link their run.
import { type Attention, type IdeaList, type Mission, type MissionList } from '../api/generated';
import { useRead } from '../data/cache';
import { objectHref } from '../nav/destinations';
import { ago, present, statusLine } from '../state/present';
import { Empty, Fresh, Loadable, Section, StateBadge } from '../components/ui';

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

export function MissionRow({ m, waiting }: { m: Mission; waiting?: boolean }) {
  return (
    <li className="row-item" data-mission={m.id} data-state={m.state}>
      <a href={objectHref('mission', m.id)} className="row-link">
        <StateBadge machine="mission" state={m.state} />
        <span className="title">{m.title}</span>
        {waiting ? <span className="tag attention">waiting on you</span> : null}
        <span className="status">{statusLine(m)}</span>
        {m.origin === 'automation' ? <span className="tag">from an automation</span> : null}
        <span className="age">{ago(m.updated_at)}</span>
      </a>
    </li>
  );
}

export function WorkView({ project }: { project?: string }) {
  const snap = useRead<MissionList>(project ? `/v1/missions?project=${project}` : '/v1/missions');
  const att = useRead<Attention>('/v1/attention');
  const waiting = new Set((att.data?.items ?? []).map((i) => i.mission_id).filter(Boolean) as string[]);
  return (
    <div className="view">
      <h1 tabIndex={-1}>Work</h1>
      <Fresh snap={snap} />
      <Loadable snap={snap} what="the missions">
        {(l) =>
          l.missions.length ? (
            <>
              {GROUPS.map((g) => {
                const ms = l.missions
                  .filter((m) => groupOf(m, waiting) === g.id)
                  .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
                return ms.length ? (
                  <Section key={g.id} title={`${g.title} · ${ms.length}`}>
                    <ul className="rows">
                      {ms.slice(0, PAGE).map((m) => (
                        <MissionRow key={m.id} m={m} waiting={waiting.has(m.id)} />
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

function Ideas() {
  const snap = useRead<IdeaList>('/v1/ideas');
  const ideas = snap.data?.ideas ?? [];
  if (!ideas.length) return null;
  return (
    <Section title={`Ideas · ${ideas.length}`}>
      <ul className="rows">
        {ideas.map((i) => (
          <li key={i.id} className="row-item">
            <StateBadge machine="idea" state={i.state} /> <span className="title">{i.title ?? i.text}</span>
            {i.promoted_mission_id ? (
              <a href={objectHref('mission', i.promoted_mission_id)}>its mission</a>
            ) : null}
          </li>
        ))}
      </ul>
    </Section>
  );
}
