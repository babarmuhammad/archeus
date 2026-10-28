// One vocabulary for how a thing is going, after Linear's six agent states plus Cancelled. Each maps to the tone (colour token) and the glyph
// the kit already uses, and carries its own word: colour never says it alone. Machine states keep their own words through present() and badge().
export const STATES = {
  pending: { tone: 'paused', icon: 'clock', word: 'Pending' },
  active: { tone: 'active', icon: 'running', word: 'Running' },
  awaiting: { tone: 'attention', icon: 'needs_you', word: 'Needs you' },
  error: { tone: 'blocked', icon: 'blocked', word: 'Failed' },
  complete: { tone: 'ok', icon: 'done', word: 'Done' },
  stale: { tone: 'unknown', icon: 'minus', word: 'Stale' },
  cancelled: { tone: 'paused', icon: 'cancel', word: 'Cancelled' }
};
