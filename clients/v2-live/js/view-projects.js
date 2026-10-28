import {h, s, clear} from './dom.js';
import {areasOf} from './areas-model.js';
import {present} from '../core-words.js';
import {tr} from './i18n.js';
import {reducedMotion} from './store.js';
import {layoutProjects, projectsCore, projectsLegendBox, unit, INSET} from './constellation/geometry.js';
import {coreStar, projectPlateMarkup} from './constellation/nodeart.js';

export function projectState(missions) {
  const cls = missions.map(m => present('mission', m.state).cls);
  if (cls.some(c => ['needs_you', 'blocked', 'failed', 'reviewing'].includes(c))) return 'waiting';
  if (cls.some(c => ['active', 'planning', 'verifying'].includes(c))) return 'active';
  return missions.length && missions.every(m => m.state === 'COMPLETED') ? 'verified' : 'idle';
}

export function projectsLegend() {
  return h('div', {class: 'projects-legend', role: 'note'},
    ...['Recorded relation', 'Suggested relation'].map((label, i) => h('p', null, h('span', {class: 'projects-key' + (i ? ' suggested' : ''), 'aria-hidden': 'true'}), label)),
    h('div', {class: 'projects-states'}, ...['Active', 'Waiting', 'Verified'].map(label => h('span', null, h('i', {class: 'projects-dot ' + label.toLowerCase(), 'aria-hidden': 'true'}), label))));
}

export function render(ctx) {
  const S = areasOf(ctx.sim).S(), missions = Object.values(S.missions);
  const nodes = S.projects.map(p => ({id: p.id, kind: 'Project', label: p.name, project: p.id,
    missionCount: missions.filter(m => m.project === p.id).length, state: projectState(missions.filter(m => m.project === p.id))}));
  nodes.push(...S.ideas.filter(i => i.state === 'CAPTURED').map(i => ({id: i.id, kind: 'Idea', label: i.title, project: i.project, state: 'idle'})));
  const legend = projectsLegend();
  const scene = h('div', {class: 'projects-scene'}, legend);
  const root = h('div', {class: 'projects-page', 'data-quiet': String(reducedMotion())},
    h('header', {class: 'page-head'}, h('div', null, h('h1', null, 'Projects'), h('p', {class: 'sub'}, 'Select a project to see its phases, missions and ideas.'))),
    scene, nodes.length ? null : h('p', {class: 'empty'}, 'No projects yet.'));
  let lastSize;
  ctx.mounts.push(() => {
    const width = Math.floor(scene.clientWidth);
    const page = scene.closest('.main-col');
    const viewportHeight = page ? page.clientHeight - root.querySelector('.page-head').offsetHeight : 600;
    const size = `${width}:${viewportHeight}`;
    if (!width || size === lastSize) return;
    lastSize = size;
    const phone = width < 600, rows = phone ? nodes.length : Math.ceil(nodes.length / 2);
    const height = Math.max(viewportHeight, rows * 56 + (phone ? 120 : 0) + INSET.top + 142);
    scene.style.height = `${height}px`;
    legend.style.width = `${projectsLegendBox(width, height).width}px`;
    const placed = layoutProjects({nodes}, width, height), core = projectsCore(width, height), star = coreStar(phone ? 23 : 52 * Math.min(unit(width, height), (height - 142) / 400), phone ? 1 : 1.75);
    const svg = s('svg', {viewBox: `0 0 ${width} ${height}`, width, height, role: 'group', 'aria-label': tr('Projects scene')});
    if (!phone) {
      for (const fy of [.28, .65]) svg.append(s('path', {class: 'projects-plane', d: `M16 ${height * fy}L${width / 2} ${height * fy - Math.min(90, height * .14)}L${width - 16} ${height * fy}L${width / 2} ${height * fy + Math.min(90, height * .14)}Z`, 'aria-hidden': 'true'}));
    }
    for (const n of placed) {
      const parent = n.kind === 'Idea' ? placed.find(p => p.id === n.project) : core;
      if (!parent) continue;
      const side = n.x < parent.x ? 1 : -1;
      const x = phone ? n.x - n.width / 2 : n.x + side * n.width / 2;
      const fromX = n.kind === 'Idea' ? phone ? parent.x - parent.width / 2 : parent.x - side * parent.width / 2 : parent.x;
      const selected = ctx.route.id === 'prj-' + n.id || (n.kind === 'Idea' && ctx.route.id === n.id);
      const d = phone ? `M${fromX} ${parent.y}H${INSET.left}V${n.y}H${x}` : `M${fromX} ${parent.y}L${x} ${n.y}`;
      svg.append(s('path', {class: 'projects-relation' + (n.kind === 'Idea' ? ' suggested' : '') + (selected ? ' selected' : ''), d, 'aria-hidden': 'true'}), s('circle', {class: 'projects-joint', cx: x, cy: n.y, r: 2.5, 'aria-hidden': 'true'}));
    }
    svg.append(s('g', {class: 'projects-core', transform: `translate(${core.x} ${core.y})`, 'aria-hidden': 'true'},
      s('path', {d: star.threads, class: 'projects-threads'}), s('path', {d: star.spikes}),
      s('text', {y: phone ? 60 : 115, 'text-anchor': 'middle'}, 'ARCHEUS')));
    placed.forEach((n, i) => {
      const id = n.kind === 'Project' ? 'prj-' + n.id : n.id;
      const selected = ctx.route.id === id;
      const label = n.label + ' · ' + tr(n.kind === 'Idea' ? 'Captured' : `${n.missionCount} ${n.missionCount === 1 ? 'mission' : 'missions'}`) + (n.kind === 'Project' ? ' · ' + tr(({active: 'Active', waiting: 'Waiting', verified: 'Verified', idle: 'Nothing running in this project.'})[n.state]) : '');
      const anchor = s('a', {href: '#/projects/' + id, class: 'projects-node ' + n.state + (n.kind === 'Idea' ? ' projects-idea' : ''), transform: `translate(${n.x} ${n.y})`, 'aria-label': label, 'aria-current': selected ? 'true' : null, 'data-key': 'project-plate-' + id, style: `--plate-delay:${Math.min(i * 30, 150)}ms`});
      anchor.innerHTML = projectPlateMarkup(n, tr);
      svg.append(anchor);
    });
    const focused = scene.contains(document.activeElement) ? document.activeElement.dataset.key : null;
    clear(scene).append(svg, legend);
    if (focused) svg.querySelector(`[data-key="${focused}"]`)?.focus({preventScroll: true});
  });
  return root;
}
