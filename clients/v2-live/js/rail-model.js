// Which projects the rail and the Places sheet list. A few projects keep their given order; many projects list the ones that
// need you first, then the running ones, capped, with the selected one always shown. The rest sit behind "All N projects".
const RANK = { needs_you: 0, running: 1, idle: 2, done: 3 };
export function railProjects(projects, stateOf, selected, cap) {
  if (projects.length <= cap) return { shown: projects, more: 0 };
  const ranked = projects.map((p, i) => ({ p, i, r: RANK[stateOf(p)] ?? 2 })).sort((a, b) => a.r - b.r || a.i - b.i).map((x) => x.p);
  let shown = ranked.slice(0, cap);
  const sel = projects.find((p) => p.id === selected);
  if (sel && !shown.includes(sel)) shown = [...shown.slice(0, cap - 1), sel];
  return { shown, more: projects.length - shown.length };
}
