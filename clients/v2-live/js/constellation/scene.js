import {bodyMarkup, coreStar} from './nodeart.js';

// The mission graph, drawn with the same node art and tokens as the live map. Pure: a model in, a scene (positions, arrows) and SVG markup out.
// Only relations that exist in the record are drawn: a node without a record is left out together with its arrows.
export const BOX = Object.freeze({width: 800, height: 640});
const esc = t => String(t).replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`), fx = v => +v.toFixed(1);
const SLOT = {main: {x: 400, y: 280, radius: 100}, exec: {x: 110, y: 280, radius: 68}, result: {x: 690, y: 280, radius: 68}, task: {x: 235, y: 505, radius: 56}, out: {x: 565, y: 505, radius: 56}};
const CORE = {x: 400, y: 52, radius: 26};

// model: {id, title, lines[], state, exec?: {title, lines[], state}, result?: {title, lines[], state}, task?: {title, lines[], state}, out?: bool}
export function missionScene(model) {
  const nodes = [{id: model.id, role: 'main', kind: 'Mission', icon: 'terminal', meta: 'MISSION', title: model.title, lines: model.lines || [], state: model.state, ...SLOT.main}];
  const arrows = [{from: 'core', to: model.id, label: 'ORCHESTRATES'}];
  const add = (slot, id, icon, meta, part) => nodes.push({id, role: slot, kind: 'Mission', icon, meta, title: part.title, lines: part.lines || [], state: part.state || 'idle', ...SLOT[slot]});
  if (model.exec) { add('exec', `${model.id}:exec`, 'code', 'EXECUTION', model.exec); arrows.push({from: `${model.id}:exec`, to: model.id, label: 'EXECUTES'}); }
  if (model.result) { add('result', `${model.id}:result`, 'shield', model.result.meta || 'VERIFICATION', model.result); arrows.push({from: model.id, to: `${model.id}:result`, label: 'RESULTS IN'}); }
  if (model.task) { add('task', `${model.id}:task`, 'doc', 'TASK', model.task); arrows.push({from: model.id, to: `${model.id}:task`, label: 'USES'}); }
  if (model.task && model.result && model.out) {
    add('out', `${model.id}:out`, 'chart', 'OUTPUT', {title: 'Results', lines: []});
    arrows.push({from: model.id, to: `${model.id}:out`, label: 'PRODUCES'});
    if (model.result.meta !== 'REVIEW') arrows.push({from: `${model.id}:out`, to: `${model.id}:result`, label: 'VERIFIES'});
  }
  const at = new Map([['core', CORE], ...nodes.map(n => [n.id, n])]);
  return {box: BOX, core: CORE, nodes, arrows: arrows.map(a => {
    const p = at.get(a.from), q = at.get(a.to), d = Math.hypot(q.x - p.x, q.y - p.y), ux = (q.x - p.x) / d, uy = (q.y - p.y) / d, gap = 9;
    const x1 = p.x + ux * (p.radius + gap), y1 = p.y + uy * (p.radius + gap), x2 = q.x - ux * (q.radius + gap), y2 = q.y - uy * (q.radius + gap);
    const side = Math.abs(ux) < .3, k = ux > 0 ? 1 : -1, t = side || Math.abs(ux) > .9 ? .5 : uy > 0 ? .68 : .42, mx = x1 + (x2 - x1) * t, my = y1 + (y2 - y1) * t;
    return {...a, x1: fx(x1), y1: fx(y1), x2: fx(x2), y2: fx(y2), lx: fx(side ? mx + 12 : mx + uy * k * 16), ly: fx(side ? my + 4 : my - ux * k * 16 + 3), anchor: side ? 'start' : 'middle'};
  })};
}

export function sceneMarkup(scene, t = x => x) {
  const star = coreStar(scene.core.radius, 1.7), c = scene.core;
  let out = '<defs><marker id="am-arrowhead" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="9" markerHeight="9" orient="auto"><path d="M1 1L7 4L1 7" class="am-arrowhead"/></marker></defs>';
  out += `<g class="am-arrows">${scene.arrows.map(a => `<line class="am-arrow" x1="${a.x1}" y1="${a.y1}" x2="${a.x2}" y2="${a.y2}" marker-end="url(#am-arrowhead)"/><text class="am-arrow-label" x="${a.lx}" y="${a.ly}" text-anchor="${a.anchor}">${esc(t(a.label))}</text>`).join('')}</g>`;
  out += `<g class="am-core am-state-core" transform="translate(${c.x} ${c.y})"><path class="am-core-chords" d="${star.threads}"/><path class="am-core-thread" d="${star.spikes}"/><path class="am-core-dot" d="${star.tips}"/><text class="am-wordmark" x="2" y="${c.radius + 30}" text-anchor="middle" style="font-size:13px">ARCHEUS</text></g>`;
  for (const n of scene.nodes) {
    out += `<g transform="translate(${n.x} ${n.y})">${bodyMarkup(n, n.icon)}</g>`;
    const rows = [n.title, ...n.lines], big = n.role === 'main';
    out += `<g class="am-label am-state-${n.state === 'needs-you' || n.state === 'running' || n.state === 'done' || n.state === 'blocked' ? n.state : 'idle'}" data-node-id="${esc(n.id)}"><text class="am-label-meta" x="${n.x}" y="${n.y + n.radius + 24}" text-anchor="middle" style="font-size:11px">${esc(t(n.meta))}</text>`
      + rows.map((r, i) => `<text class="${i ? 'am-label-sub' : 'am-label-title'}" x="${n.x}" y="${n.y + n.radius + 48 + i * 19 - (i ? 0 : 0)}" text-anchor="middle" style="font-size:${i ? 13 : big ? 22 : 18}px">${esc(r)}</text>`).join('') + '</g>';
  }
  return out;
}
