// The inspector's width (rulebook §15, design system §5): 360–560 px, chosen by
// the user with a thin divider and remembered in this browser only. Nothing is
// sent to Core; a missing or refusing storage leaves the default width.

export const INSPECTOR_MIN = 360;
export const INSPECTOR_MAX = 560;
export const INSPECTOR_STEP = 16;
const KEY = 'archeus:inspector-width';

/** A width the inspector may have: whole pixels within its bounds. */
export const clampWidth = (w: number) => Math.round(Math.min(INSPECTOR_MAX, Math.max(INSPECTOR_MIN, w)));

/** The width remembered in this browser, or null for the default. */
export function loadWidth(storage: Pick<Storage, 'getItem'> | null): number | null {
  try {
    const n = Number(storage?.getItem(KEY));
    return storage?.getItem(KEY) && Number.isFinite(n) ? clampWidth(n) : null;
  } catch {
    return null;
  }
}

export function saveWidth(storage: Pick<Storage, 'setItem'> | null, w: number) {
  try {
    storage?.setItem(KEY, String(clampWidth(w)));
  } catch {
    // refused: kept for this page only
  }
}

/** The width a key asks for on the divider (window-splitter pattern): the
 * divider is the inspector's left edge, so ← widens it and → narrows it. */
export function keyWidth(w: number, key: string): number | null {
  switch (key) {
    case 'ArrowLeft':
      return clampWidth(w + INSPECTOR_STEP);
    case 'ArrowRight':
      return clampWidth(w - INSPECTOR_STEP);
    case 'Home':
      return INSPECTOR_MIN;
    case 'End':
      return INSPECTOR_MAX;
    default:
      return null;
  }
}
