// Preferences. localStorage only inside try/catch; the URL (?theme=dark&device=phone&motion=reduced) wins and is never stored.
export const THEMES = [
  { id: 'dark', label: 'Dark' }, { id: 'light', label: 'Light' }, { id: 'dark-hc', label: 'Dark, high contrast' },
  { id: 'light-hc', label: 'Light, high contrast' }, { id: 'system', label: 'System' }, { id: 'forced', label: 'Forced colours (simulated)' }
];
export const DEVICES = [
  { id: 'auto', label: 'Auto', note: 'Fills the window' }, { id: 'phone', label: 'Phone', w: 390, note: '390 px' },
  { id: 'tablet', label: 'Tablet', w: 820, note: '820 px' }, { id: 'desktop', label: 'Desktop', w: 1440, note: '1440 px' }, { id: 'terminal', label: 'Terminal', note: 'Text mode' }, { id: 'all', label: 'All devices', note: 'Side by side' }
];
const KEY = 'archeus-v2-live';
const defaults = { theme: 'dark', motion: 'system', device: 'auto', lang: 'en', notes: 'on', heronotes: 'off', tools: 'closed', overview: 'projects', projsort: 'attention' };

function read() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
function write(p) { try { localStorage.setItem(KEY, JSON.stringify(p)); } catch (e) { /* private window or blocked storage: the app still works */ } }

const q = new URLSearchParams(location.search);
const prefs = Object.assign({}, defaults, read());
for (const k of Object.keys(defaults)) if (q.get(k)) prefs[k] = q.get(k);
if (!THEMES.some((t) => t.id === prefs.theme)) prefs.theme = defaults.theme;
if (!DEVICES.some((d) => d.id === prefs.device)) prefs.device = defaults.device;
if (!['system', 'full', 'reduced'].includes(prefs.motion)) prefs.motion = defaults.motion;
if (!['en', 'it'].includes(prefs.lang)) prefs.lang = defaults.lang;
if (!['on', 'off'].includes(prefs.notes)) prefs.notes = defaults.notes;
if (!['on', 'off'].includes(prefs.heronotes)) prefs.heronotes = defaults.heronotes;
if (!['open', 'closed'].includes(prefs.tools)) prefs.tools = defaults.tools;
if (!['projects', 'network'].includes(prefs.overview)) prefs.overview = defaults.overview;
if (!['attention', 'recent', 'name'].includes(prefs.projsort)) prefs.projsort = defaults.projsort;

export const get = (k) => prefs[k];
export function set(k, v) { prefs[k] = v; write(Object.fromEntries(Object.keys(defaults).map((x) => [x, prefs[x]]))); apply(); }

export function reducedMotion() {
  if (prefs.motion === 'reduced') return true;
  if (prefs.motion === 'full') return false;
  return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}
export function apply() {
  const r = document.documentElement;
  r.dataset.theme = prefs.theme;
  r.dataset.motion = prefs.motion === 'system' ? 'system' : prefs.motion;
  r.dataset.notes = prefs.notes;
  r.dataset.heronotes = prefs.heronotes;
  r.lang = prefs.lang;
}
