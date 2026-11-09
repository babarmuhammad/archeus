// Pinned missions (rulebook §10, §32; D-9, §46.1): a local preference, kept in
// this browser only and never sent to Core. Pins are the missions' ids; Work
// shows the pinned ones it lists as a Pinned group at its top, at every width.
// The storage may be missing, full or refused (a private window): pins then
// last for the page's life and nothing fails.

const KEY = 'archeus:pins';

export interface PinStorage {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
}

export class Pins {
  private ids: string[];
  private listeners = new Set<() => void>();
  private storage: PinStorage | null;

  constructor(storage: PinStorage | null) {
    this.storage = storage;
    this.ids = [];
    try {
      const v = JSON.parse(storage?.getItem(KEY) ?? '[]');
      if (Array.isArray(v)) this.ids = v.filter((x): x is string => typeof x === 'string');
    } catch {
      // unreadable: start with none
    }
  }

  has(id: string): boolean {
    return this.ids.includes(id);
  }

  /** The pinned ids, oldest pin first. */
  list(): string[] {
    return this.ids;
  }

  toggle(id: string) {
    this.ids = this.has(id) ? this.ids.filter((x) => x !== id) : [...this.ids, id];
    try {
      this.storage?.setItem(KEY, JSON.stringify(this.ids));
    } catch {
      // refused: kept for this page only
    }
    this.listeners.forEach((l) => l());
  }

  subscribe(l: () => void): () => void {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
}

function browserStorage(): PinStorage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

/** The page's one pin set. */
export const pins = new Pins(browserStorage());
