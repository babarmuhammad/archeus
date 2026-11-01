// The objects the chat has just made, kept while their New tag lasts. The clock is the wall clock: a paused simulation must not keep a tag for ever.
import { BORN_MS } from './constellation/born.js';

export function createBornLog(now = () => performance.now()) {
  const log = new Map();
  return {
    // Only an event the owner's device made (the chat) counts; the simulation's own creations are never tagged.
    note(ev) {
      const m = /^(project|mission|idea)\.created$/.exec(ev.type);
      if (!m || ev.actor !== 'device') return false;
      log.set(ev.subject.id, { id: ev.subject.id, kind: m[1], project: ev.project, until: now() + BORN_MS });
      return true;
    },
    live() {
      const t = now();
      for (const [id, b] of log) if (b.until <= t) log.delete(id);
      return [...log.values()].map(({ id, kind, project }) => ({ id, kind, project }));
    }
  };
}
