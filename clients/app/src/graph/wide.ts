// Whether the window is wide enough for the spatial view (p18-design-gate A12):
// below 600 px it is not drawn, and the Relations list is the view. A window
// rule, read the one way by the view and by every link to it.
import { useSyncExternalStore } from 'react';

export const MIN_WIDTH = 600;
const QUERY = `(min-width: ${MIN_WIDTH}px)`;

export function isWide(): boolean {
  return typeof matchMedia === 'undefined' ? true : matchMedia(QUERY).matches;
}

export function useWide(): boolean {
  return useSyncExternalStore((l) => {
    const q = matchMedia(QUERY);
    q.addEventListener('change', l);
    return () => q.removeEventListener('change', l);
  }, isWide);
}
