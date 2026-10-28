// Pure helpers for the Extensions page: the five kinds, which kind an id belongs to, and the search match.
export const EXT_TABS = [['hooks', 'Hooks'], ['mcp', 'MCP servers'], ['agents', 'Agents'], ['automations', 'Automations'], ['clients', 'Clients']];
const PREFIX = [['mcp-', 'mcp'], ['h-', 'hooks'], ['ag-', 'agents'], ['au-', 'automations'], ['d-', 'clients']];
export const tabOf = (id) => { const p = id && PREFIX.find(([x]) => id.startsWith(x)); return p ? p[1] : null; };

export const matches = (q, text) => !q || text.includes(q.trim().toLowerCase());
