// Pure helpers for the Extensions page: the five kinds, which kind an id belongs to, the short time form, and the search match.
export const EXT_TABS = [['hooks', 'Hooks'], ['mcp', 'MCP servers'], ['agents', 'Agents'], ['automations', 'Automations'], ['clients', 'Clients']];
const PREFIX = [['mcp-', 'mcp'], ['h-', 'hooks'], ['ag-', 'agents'], ['au-', 'automations'], ['d-', 'clients']];
export const tabOf = (id) => { const p = id && PREFIX.find(([x]) => id.startsWith(x)); return p ? p[1] : null; };

const DAY = 86400000, START = 9 * 3600000; // the simulated day starts at 09:00 (HOUR0 in sim.js)
const day = (ms) => Math.floor((ms + START) / DAY);
// 'Today 08:34', 'Yesterday 23:10', or 'Never' when there is no time; label(ms) gives HH:MM.
export function whenShort(t, clock, label) {
  if (t == null) return 'Never';
  const d = day(clock) - day(t);
  return (d <= 0 ? 'Today ' : d === 1 ? 'Yesterday ' : 'Earlier ') + label(t);
}
export const matches = (q, text) => !q || text.includes(q.trim().toLowerCase());
