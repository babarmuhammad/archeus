// The live map as vector SVG, laid out in the pixels of its own box (crisp at any size and DPR, redrawn on resize).
// Core mark at the centre, one hub per project, missions fanned outward from their hub, executions and decisions beside their mission.
// Shape carries the fact (circle mission, ring hub, triangle execution, diamond decision), colour confirms it. No text is drawn inside it:
// names live in the list beside it (the text mirror), which is also where selection happens in slice 1.
import { s } from './dom.js';
import { present } from '../core-words.js';

export function drawMap(svg, box, sim, selectedId) {
  const w = Math.max(160, box.clientWidth), hh = Math.max(160, box.clientHeight);
  svg.setAttribute('viewBox', '0 0 ' + w + ' ' + hh);
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const st = sim.state, cx = w / 2, cy = hh / 2, R = Math.min(w, hh) / 2;
  const unit = Math.max(0.75, Math.min(1.6, R / 150));
  const projects = st.projects;
  const edges = s('g'), nodes = s('g');
  svg.append(edges, nodes);
  const execsOf = (mid) => Object.values(st.executions).filter((x) => x.mission === mid && present('execution', x.state).cls === 'active');
  const apprOf = (mid) => Object.values(st.approvals).some((a) => a.mission === mid && a.state === 'PENDING');
  // a wide box spreads the hubs on an ellipse, a square one on a circle
  const rx = Math.min(R * 0.62, w * 0.34), ry = Math.min(R * 0.62, hh * 0.34);
  projects.forEach((p, pi) => {
    const ang = -Math.PI / 2 + (pi * 2 * Math.PI) / projects.length;
    const hx = cx + Math.cos(ang) * rx * (w > hh * 1.3 ? 1.5 : 1), hy = cy + Math.sin(ang) * ry;
    edges.append(s('line', { class: 'map-edge', x1: cx + Math.cos(ang) * 46 * unit, y1: cy + Math.sin(ang) * 46 * unit, x2: hx, y2: hy }));
    const ms = Object.values(st.missions).filter((m) => m.project === p.id);
    const out = Math.atan2(hy - cy, hx - cx), spread = Math.min(Math.PI * 0.9, 0.5 * ms.length), step = ms.length > 1 ? spread / (ms.length - 1) : 0;
    ms.forEach((m, i) => {
      const a = out - spread / 2 + i * step + (ms.length === 1 ? spread / 2 : 0);
      const dist = (R * 0.27 + (i % 2) * R * 0.07) * 1;
      const mx = hx + Math.cos(a) * dist, my = hy + Math.sin(a) * dist;
      const cls = present('mission', m.state).cls;
      edges.append(s('line', { class: 'map-edge' + (m.state === 'COMPLETED' || m.state === 'CANCELLED' ? ' dash' : ''), x1: hx, y1: hy, x2: mx, y2: my }));
      const g = s('g', { 'data-c': cls, 'data-id': m.id }, s('title', null, m.title + ', ' + present('mission', m.state).label));
      g.append(s('circle', { class: 'nd' + (m.id === selectedId ? ' sel' : ''), cx: mx, cy: my, r: 6.5 * unit }));
      execsOf(m.id).slice(0, 3).forEach((x, k) => {
        const ea = a + (k - 1) * 0.55, ex = mx + Math.cos(ea) * 17 * unit, ey = my + Math.sin(ea) * 17 * unit, r = 4.5 * unit;
        g.append(s('line', { class: 'map-edge', x1: mx, y1: my, x2: ex, y2: ey }), s('polygon', { class: 'nd', 'data-c': 'active', points: [ex, ey - r, ex + r, ey + r * 0.8, ex - r, ey + r * 0.8].join(' ') }));
      });
      if (apprOf(m.id)) {
        const ax = mx + Math.cos(a + Math.PI * 0.5) * 15 * unit, ay = my + Math.sin(a + Math.PI * 0.5) * 15 * unit, r = 5 * unit;
        g.append(s('polygon', { class: 'nd', 'data-c': 'needs_you', points: [ax, ay - r, ax + r, ay, ax, ay + r, ax - r, ay].join(' ') }));
      }
      nodes.append(g);
    });
    nodes.append(s('g', { 'data-id': p.id }, s('title', null, p.name), s('circle', { class: 'hub', cx: hx, cy: hy, r: 12 * unit })));
  });
}
