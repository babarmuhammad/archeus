// The one sender the app talks to Core with, set once it has a token.
import type { Send } from '../api/generated';

let current: Send | null = null;

export function setSend(s: Send) {
  current = s;
}

export function send(): Send {
  if (!current) throw new Error('not signed in');
  return current;
}
