// Whether the window is wide enough for the spatial view (p18-design-gate A12):
// below 600 px it is not drawn, and the Relations list is the view. A window
// rule, read the one way by the view and by every link to it. Now's live map
// asks for more (rulebook §22: hidden below 1000 px).
import { useSyncExternalStore } from 'react';

export const MIN_WIDTH = 600;
export const MAP_MIN_WIDTH = 1000;

export function isWide(min = MIN_WIDTH): boolean {
  return typeof matchMedia === 'undefined' ? true : matchMedia(`(min-width: ${min}px)`).matches;
}

export function useWide(min = MIN_WIDTH): boolean {
  return useSyncExternalStore(
    (l) => {
      const q = matchMedia(`(min-width: ${min}px)`);
      q.addEventListener('change', l);
      return () => q.removeEventListener('change', l);
    },
    () => isWide(min),
  );
}
