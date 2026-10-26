import {s, text, line, missionPoly, projectPoly, executionTriangle, core, projectHexagon, decisionMarker, reviewButton} from './nodeart.js';

const identity = (key, fallback) => fallback;
function at(el, x, y) { const g = s('g', {transform: `translate(${x} ${y})`}, el); return g; }
function activate(el, id, label, bounds, emit) {
  el.setAttribute('class', `${el.getAttribute('class') || ''} action`);
  el.setAttribute('tabindex', '0'); el.setAttribute('role', 'button'); el.setAttribute('aria-label', label);
  el.append(s('rect', {class: 'hit', x: bounds[0], y: bounds[1], width: bounds[2], height: bounds[3]}));
  const run = () => emit(id);
  el.addEventListener('click', run);
  el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); run(); } });
  return el;
}
function relation(layer, a, b, {label, square = false, state = '', arrow = false, opacity = .45} = {}) {
  const g = s('g', {class: `state-${state}`, 'aria-hidden': 'true'}, line(a, b, opacity));
  for (const [cx, cy] of [a, b]) g.append(square ? s('rect', {x: cx - 4, y: cy - 4, width: 8, height: 8, fill: 'var(--scene-bg, #0C0811)', stroke: 'currentColor', 'stroke-width': .8, 'vector-effect': 'non-scaling-stroke'}) : s('circle', {cx, cy, r: 2, fill: 'currentColor'}));
  if (arrow) { const angle = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI; g.append(s('path', {d: 'M-9-4 0 0-9 4', transform: `translate(${b}) rotate(${angle})`, fill: 'none', stroke: 'currentColor', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'})); }
  if (label) g.append(text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 12, label, 'relation-label', 'middle'));
  layer.append(g);
}
function draw(container, options, kind) {
  const {t = identity, onselect, onreview} = options;
  const host = document.createElement('div'); host.className = 'live-scene';
  if (options.theme) host.dataset.theme = options.theme;
  container.append(host);
  const emit = id => { onselect?.(id); host.dispatchEvent(new CustomEvent('scene-select', {detail: {id}, bubbles: true})); };
  const review = () => { onreview?.('search-provenance'); host.dispatchEvent(new CustomEvent('scene-review', {detail: {id: 'search-provenance'}, bubbles: true})); };
  function render() {
    const width = options.width ?? container.clientWidth ?? 1440, height = options.height ?? container.clientHeight ?? 900;
    const narrow = width < 600, W = narrow ? Math.max(280, width) : 1320, H = narrow ? (kind === 'calm' ? 1900 : kind === 'mission' ? 1810 : 1450) : 840;
    const svg = s('svg', {class: 'scene', xmlns: 'http://www.w3.org/2000/svg', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid meet', role: 'group', 'aria-label': t(`scene.${kind}`, `${kind === 'now' ? 'Now' : kind === 'calm' ? 'Calm' : 'Mission'} constellation — concept fixture`)});
    if (narrow) { svg.style.height = `${H}px`; svg.style.minWidth = '280px'; }
    const edges = s('g'), nodes = s('g'); svg.append(edges, nodes);
    const center = narrow ? [W / 2, 60] : kind === 'now' ? [570, 340] : kind === 'calm' ? [580, 345] : [600, 85];
    nodes.append(at(core({scale: narrow ? .32 : kind === 'mission' ? .4 : kind === 'calm' ? .86 : .67, t, tagline: kind === 'calm' ? 'UNDERSTAND · PLAN · DO' : 'Your projects. In context.'}), ...center));
    const label = (g, x, y, key, fallback, subtitle, eyebrow = 'MISSION', anchor = 'start') => {
      if (eyebrow) g.append(text(x, y, t(`kind.${eyebrow}`, eyebrow), 'eyebrow', anchor));
      g.append(text(x, y + 30, t(key, fallback), 'title', anchor));
      if (subtitle) g.append(text(x, y + 55, t(`${key}.subtitle`, subtitle), 'subtitle', anchor));
    };
    const poly = (id, x, y, size, state, glyph, title, sub, eyebrow = 'MISSION', below = false) => {
      const group = s('g');
      group.append(missionPoly({seed: id, size, sides: id === 'fix-date-test' ? 8 : 7, state, icon: glyph}));
      const ly = below ? size / 2 + 18 : -size / 2 - 88;
      label(group, below ? 0 : -size / 2 + 8, ly, `node.${id}`, title, sub, eyebrow, below ? 'middle' : 'start');
      const hit = Math.max(size, 44 / Math.min(width / W, height / H));
      activate(group, id, `${t(`node.${id}`, title)}. ${t(`node.${id}.subtitle`, sub)}`, [-hit / 2, -size / 2, hit, size], emit);
      nodes.append(at(group, x, y));
    };
    if (kind === 'now') {
      const left = narrow ? [W / 2, 350] : [230, 365], right = narrow ? [W / 2, 710] : [875, 430];
      const project = narrow ? [W / 2, 1010] : [1030, 150], agent = narrow ? [W / 2, 1270] : [855, 635];
      relation(edges, narrow ? [W / 2, 174] : [480, 340], [left[0] + (narrow ? 0 : 108), left[1] - (narrow ? 180 : 0)], {state: 'waiting', opacity: .8});
      relation(edges, narrow ? [W / 2, 540] : [660, 340], [right[0] - (narrow ? 0 : 104), right[1] - (narrow ? 180 : 20)], {state: 'active', opacity: .8});
      if (!narrow) {
        const routes = [[[30, 410], [230, 365]], [[30, 410], [130, 540]], [[130, 540], [560, 610]], [[560, 610], [855, 688]], [[338, 365], [405, 155]], [[405, 155], [570, 340]], [[570, 340], [690, 70]], [[690, 70], [1030, 80]], [[1100, 175], [1170, 490]], [[975, 440], [1170, 490]], [[875, 520], [560, 610]], [[570, 340], [1030, 150]]];
        routes.forEach(([a, b]) => relation(edges, a, b, {opacity: .2}));
      }
      poly('search-provenance', ...left, 220, 'waiting', 'doc-search', 'Search provenance', 'Review plan');
      nodes.append(at(decisionMarker(), left[0] - 112, left[1] - 167));
      nodes.append(at(reviewButton({t, onactivate: review, hitHeight: Math.max(44, 44 / (narrow ? 1 : Math.min(width / W, height / H)))}), left[0], left[1] + 145));
      poly('fix-date-test', ...right, 210, 'verifying', 'doc', 'Fix date test', 'Verify');
      const notes = s('g', {}, projectPoly({seed: 'notes'}));
      label(notes, narrow ? 0 : 88, narrow ? 97 : -65, 'node.notes', 'Notes', 'Research and capture', 'PROJECT', narrow ? 'middle' : 'start');
      if (!narrow) notes.append(text(88, 13, t('notes.context', 'evolving context.'), 'subtitle'));
      activate(notes, 'notes', t('node.notes', 'Notes'), [-75, -75, 150, 150], emit); nodes.append(at(notes, ...project));
      relation(edges, [right[0], right[1] + 105], [agent[0], agent[1] - 75], {state: 'active'});
      const codex = s('g', {}, executionTriangle({size: 145}));
      label(codex, 0, 80, 'node.codex', 'Codex', 'checks running', 'AGENT EXECUTION', 'middle');
      activate(codex, 'codex', t('codex.label', 'Codex, checks running'), [-75, -75, 150, 130], emit); nodes.append(at(codex, ...agent));
    } else if (kind === 'calm') {
      const positions = narrow ? Array.from({length: 5}, (_, i) => [W / 2, 340 + i * 335]) : [[230, 175], [990, 175], [1070, 445], [950, 650], [190, 590]];
      ['Notes', 'Archeus', 'Website', 'Research', 'Project Alpha'].forEach((title, i) => {
        const [x, y] = positions[i];
        if (narrow) relation(edges, [x, i ? y - 190 : 180], [x, y - 130], {square: true});
        else { const sign = x < 580 ? 1 : -1, start = [x + sign * 125, y + 5], bend = [(x + 580) / 2, (y + 345) / 2]; relation(edges, start, bend, {square: true}); relation(edges, bend, [580 + (x < 580 ? -80 : 80), 345], {square: true}); }
        const panel = projectHexagon({title, t, items: [{title: 'Fix date test', key: 'item.fixDate', state: 'done'}, {title: 'Offline capture', key: 'item.capture', state: 'recorded'}]});
        activate(panel, `project-${i}`, t(`project.${title}`, title), [-125, -130, 250, 275], emit); nodes.append(at(panel, x, y));
      });
      if (!narrow) for (const [a, b] of [[ [355, 110], [470, 175]], [[470, 175], [650, 95]], [[650, 95], [765, 235]], [[765, 235], [865, 180]], [[65, 350], [120, 440]]]) relation(edges, a, b, {square: true, opacity: .24});
    } else {
      const positions = narrow ? [[W / 2, 350], [W / 2, 680], [W / 2, 990], [W / 2, 1300], [W / 2, 1610]] : [[600, 350], [200, 310], [1000, 310], [380, 635], [830, 635]];
      const specs = [['fix-date-test', 240, 'verifying', 'prompt', 'Fix date test', 'Project: Archeus · Verifying', 'MISSION'], ['execution', 190, 'idle', 'doc', 'Codex', 'Runs checks, collects evidence', 'AGENT EXECUTION'], ['verification', 180, 'idle', 'shield-check', 'Verification', 'Confirms behaviour', 'VERIFICATION'], ['suite', 145, 'idle', 'doc', 'Date test suite', 'Test definitions and inputs', 'KNOWLEDGE'], ['results', 145, 'idle', 'bars', 'Results', 'Test outputs and status', 'RESULT']];
      specs.forEach(([id, size, state, glyph, title, sub, eyebrow], i) => poly(id, ...positions[i], size, state, glyph, title, sub, eyebrow, true));
      if (narrow) { relation(edges, [W / 2, 170], [W / 2, 220], {label: t('relation.orchestrates', 'ORCHESTRATES'), arrow: true}); for (let i = 1; i < 5; i++) relation(edges, [W / 2, positions[i - 1][1] + 210], [W / 2, positions[i][1] - specs[i][1] / 2 - 15], {opacity: .3}); }
      else {
        const links = [[[600, 170], [600, 225], 'ORCHESTRATES'], [[295, 310], [475, 340], 'EXECUTES'], [[720, 350], [905, 315], 'RESULTS IN'], [[540, 450], [410, 560], 'USES'], [[670, 450], [800, 560], 'PRODUCES'], [[875, 570], [970, 405], 'VERIFIES']];
        links.forEach(([a, b, name]) => relation(edges, a, b, {label: t(`relation.${name.toLowerCase().replaceAll(' ', '-')}`, name), arrow: true, state: name === 'PRODUCES' || name === 'RESULTS IN' ? 'active' : '', opacity: .8}));
      }
    }
    host.replaceChildren(svg);
  }
  render();
  const observer = new ResizeObserver(render); observer.observe(container);
  return {element: host, resize: render, setTheme(theme) { host.dataset.theme = theme; }, destroy() { observer.disconnect(); host.remove(); }};
}
export function sceneNow(container, options = {}) { return draw(container, options, 'now'); }
export function sceneCalm(container, options = {}) { return draw(container, options, 'calm'); }
export function sceneMission(container, options = {}) { return draw(container, options, 'mission'); }
