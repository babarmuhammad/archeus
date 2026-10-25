import {createMap, edgeId} from './map.js';

if (new URLSearchParams(location.search).has('embed')) document.body.classList.add('embed');

const projects = [{id: 'archeus', label: 'Archeus'}, {id: 'notes', label: 'Notes'}, {id: 'horizon', label: 'Horizon'}];
const labels = [
  'Archeus', 'Search provenance', 'Fix date test', 'Review plan', 'Source index', 'Docs refresh', 'Execution record', 'Release notes', 'Trust boundary',
  'Notes', 'Offline capture', 'Reading list', 'Export backup', 'Research trail', 'Memory outline', 'Collected sources', 'Daily reflection',
  'Horizon', 'First sketch', 'Shared context', 'Review direction', 'A quieter workspace', 'Interaction study', 'Field notes', 'Next conversation'
];
export const fixture = {
  projects,
  nodes: labels.map((label, i) => ({id: `n${i}`, label, project: projects[i < 9 ? 0 : i < 17 ? 1 : 2].id,
    kind: [0, 9, 17].includes(i) ? 'Project' : i % 5 === 0 ? 'Idea' : i % 3 === 0 ? 'Knowledge' : 'Mission',
    state: [1, 20].includes(i) ? 'needs-you' : [2, 6].includes(i) ? 'running' : i === 12 ? 'blocked' : i % 4 === 0 ? 'done' : 'idle',
    weight: [0, 9, 17].includes(i) ? 7 : [1, 2, 20].includes(i) ? 4 : 1 + i % 3})),
  edges: labels.slice(1).map((_, j) => {
    const i = j + 1;
    return {from: `n${[9, 17].includes(i) ? 0 : i < 9 ? 0 : i < 17 ? 9 : 17}`, to: `n${i}`, kind: 'contains'};
  }).concat([{from: 'n1', to: 'n3', kind: 'proposes'}, {from: 'n2', to: 'n6', kind: 'produces'}, {from: 'n14', to: 'n22', kind: 'informs'}])
};
const map = createMap(document.querySelector('#map'), {graph: fixture, seed: 'v2-live-2026', live: true});
let selected = 'n1', counter = 25, reduced = false;
map.setSelection(selected);
map.on('select', id => {
  selected = id;
  const node = fixture.nodes.find(n => n.id === id);
  document.querySelector('#selection').textContent = node ? `${node.label} · ${node.kind} · ${node.state}` : 'No selection';
});
document.querySelector('#state').addEventListener('click', () => {
  const node = fixture.nodes.find(n => n.id === selected) || fixture.nodes[1];
  const states = ['idle', 'running', 'needs-you', 'blocked', 'done'];
  node.state = states[(states.indexOf(node.state) + 1) % states.length]; map.update(fixture);
});
document.querySelector('#add').addEventListener('click', () => {
  const id = `n${counter++}`;
  fixture.nodes.push({id, label: `New observation ${counter - 25}`, kind: 'Idea', state: 'idle', project: 'horizon', weight: 2});
  fixture.edges.push({from: 'n17', to: id, kind: 'contains'}); map.update(fixture); map.setSelection(id);
});
document.querySelector('#pulse').addEventListener('click', () => map.pulse(edgeId(fixture.edges.find(e => e.to === selected) || fixture.edges[0])));
document.querySelector('#motion').addEventListener('click', event => {
  reduced = !reduced; map.setReducedMotion(reduced); event.currentTarget.setAttribute('aria-pressed', String(reduced));
});
document.querySelector('#theme').addEventListener('change', event => map.setTheme(event.target.value));
document.querySelector('#width').addEventListener('input', event => {
  document.querySelector('#map').style.width = `${event.target.value}px`;
  document.querySelector('#size').value = `${event.target.value} px`;
});
document.querySelector('#responsive').addEventListener('click', () => {
  document.querySelector('#map').style.width = '100%'; document.querySelector('#size').value = 'Responsive';
});
window.map = map;
window.mapFixture = fixture;
