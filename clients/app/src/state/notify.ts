// T-1076: a browser notification when something new waits on the user and the
// tab is hidden. Local only (the browser's Notification API, nothing is sent
// anywhere), off until the user turns it on in Control -> Appearance, and
// switched off again there. The permission is asked for in that click, never
// at load. A read of Attention sets the baseline, which never notifies; each
// approval, verification or planning question that arrives after it is
// notified once, whether or not the setting was on when it arrived. The title
// is the item's fixed label; the body is Core's own reason, with every id it
// names said as its kind.
import type { AttentionItem } from '../api/generated.ts';
import { attentionLabel, mentions } from './present.ts';

export const NOTIFY_KEY = 'archeus-notify';
export const NOTIFY_KINDS: readonly string[] = ['approval', 'verification', 'mission'];
export const BODY_MAX = 140;

export interface Note {
  key: string;
  title: string;
  body: string;
}

export interface NotifyHost {
  enabled: () => boolean;
  hidden: () => boolean;
  show: (n: Note) => void;
}

export function noteOf(i: AttentionItem): Note {
  const text = mentions(i.reason ?? '')
    .map((p) => (typeof p === 'string' ? p : p.kind.replace(/_/g, ' ')))
    .join('')
    .trim();
  return {
    key: `${i.kind}:${i.ref.id}`,
    title: attentionLabel(i),
    body: text.length > BODY_MAX ? `${text.slice(0, BODY_MAX - 1)}…` : text,
  };
}

export class Notifier {
  private seen: Set<string> | undefined;
  private at = -Infinity;
  private host: NotifyHost;

  constructor(host: NotifyHost) {
    this.host = host;
  }

  /** A read of Attention's *items*, taken at Core's *seq*. */
  read(items: readonly AttentionItem[], seq: number | undefined) {
    if (seq === undefined || seq <= this.at) return;
    this.at = seq;
    const baseline = this.seen === undefined;
    const seen = (this.seen ??= new Set());
    const fresh: Note[] = [];
    for (const i of items) {
      const n = NOTIFY_KINDS.includes(i.kind) ? noteOf(i) : null;
      if (!n || seen.has(n.key)) continue;
      seen.add(n.key);
      fresh.push(n);
    }
    if (baseline || !this.host.enabled() || !this.host.hidden()) return;
    fresh.forEach((n) => this.host.show(n));
  }
}

export function browserStorage(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

export const notifyWanted =(s: Pick<Storage, 'getItem'> | null) => {
  try {
    return s?.getItem(NOTIFY_KEY) === 'on';
  } catch {
    return false;
  }
};

export function setNotifyWanted(s: Pick<Storage, 'setItem'> | null, on: boolean) {
  try {
    s?.setItem(NOTIFY_KEY, on ? 'on' : 'off');
  } catch {
    /* without storage the setting stays off */
  }
}

/** Whether notifications may show: the user asked for them and the browser still allows them. */
export const mayNotify = (wanted: boolean, permission: string | undefined) => wanted && permission === 'granted';

export type NotifyState = 'unsupported' | 'blocked' | 'on' | 'off';

/** What the setting says, from the browser's permission (undefined: no Notification API). */
export const notifyState = (wanted: boolean, permission: string | undefined): NotifyState =>
  permission === undefined ? 'unsupported' : permission === 'denied' ? 'blocked' : mayNotify(wanted, permission) ? 'on' : 'off';
