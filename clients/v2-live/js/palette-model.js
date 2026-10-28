// Ranking for the command palette: pure, so it can be tested. An item is { id, group, label, words, pin }.
// A query scores a label by how it matches (start, word start, inside, scattered letters), then a keyword match; recent and pinned items win ties.
export const GROUPS = ['Pages', 'Actions', 'Projects'];

export function score(item, q) {
  const label = item.label.toLowerCase(), words = (item.words || '').toLowerCase();
  if (label === q) return 100;
  if (label.startsWith(q)) return 90;
  if (label.split(/[\s>/:-]+/).some((w) => w.startsWith(q))) return 75;
  if (label.includes(q)) return 60;
  if (words.split(/\s+/).some((w) => w.startsWith(q))) return 45;
  if (words.includes(q)) return 30;
  let i = 0; for (const c of label) if (c === q[i]) i++;
  return i === q.length ? 15 : 0;
}

// Items to show for a query. No query: recent first, then the pinned and the rest by group, projects capped. A query: best match first, recent breaking ties.
export function search(items, query, recent = [], { cap = 5, max = 30 } = {}) {
  const q = query.trim().toLowerCase(), r = (id) => (recent.includes(id) ? 1 : 0);
  if (q) {
    return items.map((item) => ({ item, s: score(item, q) })).filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s || r(b.item.id) - r(a.item.id) || GROUPS.indexOf(a.item.group) - GROUPS.indexOf(b.item.group)).slice(0, max).map((x) => x.item);
  }
  const used = recent.map((id) => items.find((i) => i.id === id)).filter(Boolean).slice(0, 4);
  const rest = items.filter((i) => !used.includes(i));
  const by = (g) => rest.filter((i) => i.group === g).sort((a, b) => (b.pin ? 1 : 0) - (a.pin ? 1 : 0));
  return [...used, ...by('Pages'), ...by('Actions'), ...by('Projects').slice(0, cap)];
}

// The shown items cut into labelled groups, in order: Recent (only with no query), then Pages, Actions, Projects.
export function sections(shown, query, recent = []) {
  const noQ = !query.trim(), out = [];
  const used = noQ ? shown.filter((i) => recent.includes(i.id)) : [];
  if (used.length) out.push(['Recent', used]);
  for (const g of GROUPS) { const list = shown.filter((i) => i.group === g && !used.includes(i)); if (list.length) out.push([g, list]); }
  return out;
}

// The ids kept as recent: the newest first, no repeats, at most n.
export const remember = (recent, id, n = 5) => [id, ...recent.filter((x) => x !== id)].slice(0, n);
