import { h, s } from './dom.js';
import { icon, P } from './icons.js';
import { coreMark, wordmark, lockup, faviconSVG, pwaIconSVG } from './brand.js';
import { illustration, facet } from './illustrations.js';

const root = document.querySelector('#gallery');
const themes = ['dark', 'light', 'dark-hc', 'light-hc', 'system', 'forced'];
const states = [['done', 'Done'], ['running', 'Running'], ['needs_you', 'Needs you'], ['blocked', 'Blocked'], ['paused', 'Paused'], ['thinking', 'Thinking']];
const params = new URLSearchParams(location.search);
const badge = (state, label) => h('span', { class: 'ds-badge', 'data-state': state }, icon(state, 16), label || states.find(([id]) => id === state)[1]);
const button = (label, variant = '', glyph, action) => h('button', { type: 'button', class: 'ds-btn ' + variant, onclick: action }, glyph ? icon(glyph, 20) : null, label);
const row = (...kids) => h('div', { class: 'ds-row' }, ...kids);
const stack = (...kids) => h('div', { class: 'ds-stack' }, ...kids);
const section = (title, n, ...kids) => h('section', { class: 'specimen-section', 'aria-label': title }, h('header', null, h('h2', null, title), h('span', null, n)), ...kids);
const caption = text => h('p', { class: 'ds-caption' }, text);
const stationNames = ['Understanding', 'Planning', 'Approval', 'Executing', 'Verifying', 'Reviewing'];

function spine(size = 'inspector', current = 4, state = 'running', unknown = false) {
  const text = unknown ? 'Blocked, position unknown.' : current === 6 ? 'Done, all 6 steps passed.' : (state === 'paused' ? 'Paused at ' : '') + stationNames[current] + ', step ' + (current + 1) + ' of 6.';
  const ol = h('ol', { class: 'ds-spine', 'data-size': size, 'data-state': state, 'data-unknown': String(unknown), 'aria-label': text });
  stationNames.forEach((name, i) => {
    let mark;
    if (unknown) mark = s('svg', { width: 16, height: 16, viewBox: '0 0 16 16', 'aria-hidden': 'true' }, s('circle', { cx: 8, cy: 8, r: 6, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5, 'stroke-dasharray': '1 2' }));
    else if (i < current) mark = s('svg', { width: 16, height: 16, viewBox: '0 0 16 16', 'aria-hidden': 'true' }, s('circle', { cx: 8, cy: 8, r: 7, fill: 'currentColor' }), s('path', { d: 'M4 8l3 3 5-6', fill: 'none', stroke: 'var(--s1)', 'stroke-width': 1.5 }));
    else if (i === current && state === 'running') mark = s('svg', { width: 16, height: 16, viewBox: '0 0 16 16', 'aria-hidden': 'true' }, s('circle', { cx: 8, cy: 8, r: 7, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5 }), s('circle', { cx: 8, cy: 8, r: 4, fill: 'currentColor' }));
    else mark = icon(i === current ? state : 'running', 16);
    ol.append(h('li', { class: 'ds-station', 'data-step': !unknown && i < current ? 'passed' : 'ahead', 'aria-current': !unknown && i === current ? 'step' : null }, mark, h('span', null, name)));
  });
  return stack(ol, size === 'row' ? h('span', { class: 'ds-sr' }, text) : caption(text));
}

function card(kind, state, title, description, ...extra) {
  return h('article', { class: 'ds-card', 'data-kind': kind, 'data-state': state }, row(icon(kind === 'decision' ? 'approval' : kind, 24), h('span', { class: 'ds-eyebrow' }, kind), badge(state, kind === 'knowledge' ? 'Confirmed' : undefined)), h('h3', null, title), h('p', { class: 'ds-muted' }, description), ...extra);
}

function tabs() {
  const group = h('div', { class: 'ds-tabs', role: 'tablist', 'aria-label': 'Mission context' });
  const panel = h('div', { role: 'tabpanel', id: 'context-panel', 'aria-labelledby': 'context-tab-0', tabindex: 0 }, 'Plan approval required. Review sources before execution.');
  const contents = ['Plan approval required. Review sources before execution.', 'Archeus → Search provenance → Plan v1.', 'Source records and plan v1 are available. Checks have not run.'];
  const choose = i => {
    [...group.children].forEach((tab, j) => { tab.setAttribute('aria-selected', String(j === i)); tab.tabIndex = j === i ? 0 : -1; });
    panel.textContent = contents[i]; panel.setAttribute('aria-labelledby', 'context-tab-' + i);
  };
  ['Why', 'Relations', 'Evidence'].forEach((label, i) => group.append(h('button', { type: 'button', class: 'ds-tab', role: 'tab', id: 'context-tab-' + i, 'aria-controls': 'context-panel', 'aria-selected': String(i === 0), tabindex: i === 0 ? 0 : -1, onclick: () => choose(i), onkeydown: e => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault(); const next = e.key === 'Home' ? 0 : e.key === 'End' ? 2 : (i + (e.key === 'ArrowRight' ? 1 : 2)) % 3;
    choose(next); group.children[next].focus();
  } }, label)));
  return stack(group, panel);
}

function segmented() {
  const group = h('div', { class: 'ds-segmented', role: 'group', 'aria-label': 'Work filter' });
  const result = caption('Showing all work.');
  for (const label of ['All work', 'Live', 'Recorded']) group.append(h('button', { type: 'button', 'aria-pressed': String(label === 'All work'), onclick: e => {
    [...group.children].forEach(b => b.setAttribute('aria-pressed', String(b === e.currentTarget))); result.textContent = 'Showing ' + label.toLowerCase() + '.';
  } }, label));
  return stack(group, result);
}

function meter(label, value, limit = false) {
  return h('div', { class: 'ds-meter', 'data-limit': String(limit) }, h('div', { class: 'ds-row ds-spread' }, h('span', null, label), h('span', { class: 'ds-mono' }, value == null ? 'Unknown' : value + '%')),
    h('div', { class: 'ds-meter-track' + (value == null ? ' unknown' : ''), role: value == null ? 'img' : 'meter', 'aria-label': label + (value == null ? ': unknown' : ''), 'aria-valuemin': value == null ? null : 0, 'aria-valuemax': value == null ? null : 100, 'aria-valuenow': value, 'aria-valuetext': value == null ? null : value + '% used' }, h('div', { class: 'ds-meter-fill', style: '--value:' + (value || 0) + '%' })), caption(limit ? '◆ Review threshold reached · 20% weekly usage.' : 'Marks at 20%, 40%, 60%, 80%, 100%.'));
}

function sheet() {
  const stage = h('div', { class: 'ds-sheet-stage' });
  const launch = button('Open decision sheet', '', 'approval', () => { scrim.hidden = false; panel.hidden = false; close.focus(); });
  const dismiss = () => { scrim.hidden = true; panel.hidden = true; launch.focus(); };
  const close = button('Close', 'quiet', 'close', dismiss);
  const scrim = h('div', { class: 'ds-sheet-scrim', 'aria-hidden': 'true' });
  const panel = h('section', { class: 'ds-sheet', 'aria-label': 'Decision sheet specimen', onkeydown: e => { if (e.key === 'Escape') dismiss(); } }, h('div', { class: 'ds-grab', 'aria-hidden': 'true' }), h('header', { class: 'ds-sheet-head' }, h('h3', null, 'Review plan'), close), h('div', { class: 'ds-sheet-body' }, badge('needs_you'), h('p', null, 'Search recorded sources. Show provenance.'), caption('Plan approval required. Fixture decision only.'), spine('inspector', 2, 'needs_you')), h('footer', { class: 'ds-sheet-foot' }, button('Approve plan', 'primary', 'approve', () => { notice('Plan approved · fixture only.'); dismiss(); }), button('Reject', 'danger outline', 'reject', () => { notice('Plan rejected · fixture only.'); dismiss(); })));
  stage.append(scrim, panel);
  return stack(launch, stage, caption('Inline specimen, not a modal. Production dialog must trap focus and make background inert.'));
}

let noticeRegion;
function notice(text) {
  noticeRegion.replaceChildren(icon('info', 20), h('span', null, text), button('Dismiss', 'quiet', 'close', () => { noticeRegion.hidden = true; }));
  noticeRegion.hidden = false;
}

function controls() {
  const chips = row(...['All', 'Missions', 'Ideas'].map((label, i) => h('button', { class: 'ds-chip', type: 'button', 'aria-pressed': String(i === 0), onclick: e => { const target = e.currentTarget; [...target.parentElement.children].forEach(b => b.setAttribute('aria-pressed', String(b === target))); } }, label)));
  const tip = h('span', { class: 'ds-tip-wrap', onkeydown: e => { if (e.key === 'Escape') e.currentTarget.dataset.dismissed = 'true'; }, onmouseleave: e => { e.currentTarget.dataset.dismissed = 'false'; }, onfocusin: e => { e.currentTarget.dataset.dismissed = 'false'; } }, h('button', { class: 'ds-btn quiet', type: 'button', 'aria-label': 'Pin mission', 'aria-describedby': 'pin-tip', onclick: () => notice('Mission pinned · fixture only.') }, icon('pin', 20)), h('span', { class: 'ds-tooltip', role: 'tooltip', id: 'pin-tip' }, 'Keep this mission close'));
  return stack(row(button('Approve', 'primary', 'approve', () => notice('Approval recorded · fixture only.')), button('Open', '', 'open', () => notice('Open action preview.')), button('Pause', 'quiet', 'pause', () => notice('Paused · fixture only.')), button('Stop', 'danger', 'estop', () => notice('Stop preview · no Core connected.')), h('button', { class: 'ds-btn', type: 'button', disabled: true }, 'Unavailable'), tip), chips, segmented(), tabs(), h('label', { class: 'ds-toggle' }, h('input', { type: 'checkbox', role: 'switch', checked: true }), h('span', null, 'Decision notes')), h('label', { class: 'ds-toggle' }, h('input', { type: 'checkbox', role: 'switch', disabled: true }), h('span', null, 'Unavailable setting')));
}

function chat() {
  const input = h('textarea', { rows: 1, 'aria-label': 'Tell Archeus', placeholder: 'Tell Archeus what to do…' });
  const commands = h('ul', { class: 'ds-slash', 'aria-label': 'Slash commands' });
  for (const [name, detail, glyph] of [['mission', 'Start with a goal', 'mission'], ['idea', 'Capture a possibility', 'idea'], ['replay', 'Read recorded steps', 'replay']]) commands.append(h('li', null, h('button', { type: 'button', onclick: () => { input.value = '/' + name + ' '; input.focus(); } }, icon(glyph, 20), h('span', null, '/' + name, h('small', null, detail)))));
  const form = h('form', { class: 'ds-chat', onsubmit: e => { e.preventDefault(); if (input.value.trim()) { notice('Message captured in gallery · ' + input.value.trim()); input.value = ''; } } }, input, h('button', { class: 'ds-btn primary', type: 'submit', 'aria-label': 'Send message' }, icon('send', 20)));
  return stack(h('label', { class: 'ds-field' }, 'Mission title', h('input', { class: 'ds-input', placeholder: 'Give this mission a name' })), h('label', { class: 'ds-field' }, 'Project', h('select', { class: 'ds-select' }, h('option', null, 'Archeus'), h('option', null, 'Notes'))), h('label', { class: 'ds-field' }, 'Invalid input', h('input', { class: 'ds-input', 'aria-invalid': 'true', 'aria-describedby': 'title-error', value: '  ' }), h('span', { id: 'title-error', class: 'ds-caption' }, '✕ Enter a mission title.')), h('label', { class: 'ds-field' }, 'Context', h('textarea', { class: 'ds-textarea', placeholder: 'What should Archeus know?' })), commands, form);
}

function constellation() {
  const at = (x, y, kids) => s('g', { transform: 'translate(' + x + ' ' + y + ')' }, ...kids);
  const node = (x, y, r, n, state, glyph) => s('g', { style: 'color:var(--' + state + ')' }, at(x, y, [facet(0, 0, r, n, 0), s('circle', { r: r * .6, fill: 'var(--bg)', stroke: 'none' }), icon(glyph, 16)].map((el, i) => { if (i === 2) { el.setAttribute('x', -8); el.setAttribute('y', -8); } return el; })));
  const svg = s('svg', { viewBox: '0 0 480 250', class: 'ds-constellation-art', 'aria-hidden': 'true', fill: 'none', stroke: 'var(--text-3)', 'stroke-width': .8 },
    s('path', { d: 'M38 124L112 28 304 20 446 108 390 220 164 234Z M38 124L304 20 390 220 112 28 164 234 446 108M112 28L390 220', opacity: '.35' }),
    s('path', { d: 'M240 120L112 166', stroke: 'var(--attention)', 'stroke-width': 1.2 }), s('path', { d: 'M240 120L352 84M352 84L404 150', stroke: 'var(--active)', 'stroke-width': 1.2 }),
    node(112, 166, 34, 7, 'attention', 'evidence'), node(352, 84, 34, 7, 'active', 'task'), node(404, 166, 24, 3, 'active', 'terminal'));
  for (const [cx, cy] of [[38, 124], [112, 28], [304, 20], [446, 108], [390, 220], [164, 234]]) svg.append(s('circle', { cx, cy, r: 2, fill: 'var(--text-2)', stroke: 'none' }));
  const label = (x, y, state, title, sub) => h('div', { class: 'ds-node-label', 'data-state': state, style: 'left:' + (x / 4.8).toFixed(1) + '%;top:' + (y / 2.5).toFixed(1) + '%' }, h('b', null, title), sub && h('span', null, sub));
  return h('figure', { class: 'ds-constellation' }, svg, h('div', { class: 'ds-constellation-core' }, coreMark()),
    label(240, 156, 'idle', 'Archeus'), label(112, 206, 'needs_you', 'Search provenance', 'Review plan'),
    label(352, 14, 'running', 'Fix date test', 'Verifying'), label(404, 196, 'running', 'Codex', 'Execution'),
    h('figcaption', { class: 'ds-sr' }, 'Search provenance needs you. Fix date test is verifying, with Codex execution. The mission cards contain the same facts.'));
}

function appFrame() {
  const nav = (id, label, current) => h('a', { class: 'ds-nav', href: '#components', 'aria-current': current ? 'page' : null }, icon(id, 20), h('span', null, label));
  const links = () => [nav('now', 'Now', true), nav('work', 'Work'), nav('attention', 'Attention'), nav('chat', 'Chat')];
  return h('div', { class: 'ds-frame' }, h('nav', { class: 'ds-rail', 'aria-label': 'App navigation' }, wordmark(), ...links()), h('div', { class: 'ds-main' }, h('span', { class: 'ds-eyebrow' }, 'Now · simulated'), h('p', { class: 'ds-state-sentence' }, '1 needs you · 1 verifying'), caption('Your work, in context.'), constellation(), h('div', { class: 'ds-grid' }, card('mission', 'running', 'Fix date test', 'Archeus · fix/date-test', spine('card')), card('approval', 'needs_you', 'Search provenance', 'Review the plan before execution.', button('Review plan', 'primary', 'open', () => notice('Decision specimen below.'))))), h('aside', { class: 'ds-inspector', 'aria-label': 'Mission inspector' }, h('h2', null, 'Fix date test'), badge('running', 'Verifying'), spine(), caption('Latest record'), h('p', null, 'Tool result received.'), caption('Task: not recorded.')), h('nav', { class: 'ds-bottom', 'aria-label': 'Phone navigation' }, ...links()));
}

function renderSpecimen() {
  document.body.classList.add('ds-container');
  const skin = params.get('theme'); document.documentElement.dataset.theme = themes.includes(skin) ? skin : 'dark';
  document.documentElement.dataset.motion = params.get('motion') === 'reduced' ? 'reduced' : 'full';
  noticeRegion = h('div', { class: 'ds-toast', role: 'status', 'aria-live': 'polite', hidden: true });
  const empty = (name, title, body, action) => h('div', { class: 'ds-empty' }, illustration(name), h('h3', null, title), h('p', null, body), action ? button(action, '', name === 'error' ? 'retry' : 'plus', () => notice(action + ' · fixture only.')) : null);
  const cards = h('div', { class: 'ds-grid' },
    card('mission', 'running', 'Fix date test', 'Verifying · latest output 12 seconds ago.', spine('card')),
    card('decision', 'needs_you', 'Search provenance', 'What: Search recorded sources. Why: Plan approval required.', button('Review plan', 'primary', 'approval', () => notice('Review the sheet specimen below.'))),
    card('approval', 'needs_you', 'Allow repository access?', 'Read scope · archeus · approval required.', row(button('Approve', 'primary', 'approve', () => notice('Approved · fixture only.')), button('Reject', 'danger outline', 'reject', () => notice('Rejected · fixture only.')))),
    card('status', 'blocked', 'Execution blocked', 'Harness unavailable. No output has been received.', button('Retry', '', 'retry', () => notice('Retry requested · fixture only.'))),
    card('plan', 'thinking', 'Plan v1', 'Three proposed steps. Nothing has run.', h('ol', { class: 'ds-list' }, ...['Search recorded sources', 'Extract provenance', 'Compile report'].map((text, i) => h('li', null, h('span', { class: 'ds-mono' }, String(i + 1).padStart(2, '0')), text)))),
    card('idea', 'paused', 'Offline capture', 'Capture paused. This possibility is kept for later; no mission is scheduled.'),
    card('knowledge', 'done', 'Search provenance', 'Recorded source · updated today.', caption('Confirmed · provenance attached.')));
  const table = h('div', { class: 'ds-table-wrap', tabindex: 0, role: 'region', 'aria-label': 'Mission table, scroll if needed' }, h('table', { class: 'ds-table' }, h('caption', { class: 'ds-sr' }, 'Recorded missions'), h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Mission'), h('th', { scope: 'col' }, 'State'), h('th', { scope: 'col' }, 'Project'))), h('tbody', null, ...[['Fix date test', 'running', 'Verifying'], ['Search provenance', 'needs_you', 'Needs you'], ['Offline capture', 'done', 'Done']].map(([title, state, label]) => h('tr', null, h('td', null, title), h('td', null, badge(state, label)), h('td', null, 'Archeus'))))));
  const skeleton = h('div', { class: 'specimen-skeleton', role: 'status', 'aria-label': 'Loading mission details', 'aria-busy': 'true' }, h('span', { class: 'ds-sr' }, 'Loading mission details'), ...['60%', '100%', '85%'].map(width => h('div', { class: 'ds-skeleton', style: 'width:' + width, 'aria-hidden': 'true' })));
  root.replaceChildren(h('div', { class: 'specimen', id: 'components' },
    h('header', { class: 'specimen-hero' }, h('div', null, wordmark(), h('p', { class: 'ds-state-sentence' }, 'A calm space for work.'), caption('Design specimens · fixture data · no Core connected')), coreMark(true, 1)),
    section('App regions', '01', appFrame()),
    section('Cards', '02', cards),
    section('States, actions & selection', '03', row(...states.map(([id, label]) => badge(id, label))), controls(), noticeRegion),
    section('Inputs & conversation', '04', chat()),
    section('Sheet / side sheet / inspector', '05', sheet()),
    section('Usage', '06', meter('Weekly usage', 12), meter('Weekly review threshold', 20, true), meter('Provider usage', null)),
    section('Six-station spine', '07', caption('Row · 8 px marks'), spine('row'), caption('Card · 10 px marks'), spine('card'), caption('Inspector · 16 px marks'), spine(), caption('Hold · known position'), spine('inspector', 3, 'paused'), caption('Hold · unknown position'), spine('inspector', 0, 'blocked', true), caption('Completed mission'), spine('inspector', 6, 'done')),
    section('Tables, lists & scrolling', '08', table, h('div', { class: 'ds-scroll', tabindex: 0, role: 'region', 'aria-label': 'Recorded activity' }, h('ul', { class: 'ds-list' }, ...Array.from({ length: 12 }, (_, i) => h('li', null, icon('note', 18), 'Recorded event ' + (i + 1), h('span', { class: 'ds-muted ds-mono' }, '10:' + String(i).padStart(2, '0')))))), h('hr', { class: 'ds-divider' })),
    section('Feedback & loading', '09', h('div', { class: 'ds-toast' }, icon('approve', 20), h('span', null, 'Plan saved. Ready for review.'), button('Dismiss', 'quiet', 'close', e => { e.currentTarget.parentElement.hidden = true; })), h('div', { class: 'ds-banner', 'data-state': 'paused' }, icon('offline', 24), stack(h('strong', null, 'Offline · showing saved work'), caption('As of 10:24. New actions wait for connection.'))), h('div', { class: 'ds-banner', 'data-state': 'blocked' }, icon('warning', 24), stack(h('strong', null, 'Could not read this mission'), caption('Last saved state remains available. Retry when connection returns.'))), skeleton, button('Preview one-shot shimmer', 'quiet', 'motion', () => { skeleton.querySelectorAll('.ds-skeleton').forEach(el => { const next = el.cloneNode(); next.dataset.shimmer = 'once'; el.replaceWith(next); }); }), caption('Static by default per ADR-0055. Optional 600 ms shimmer requires adoption approval.')),
    section('Empty states', '10', h('div', { class: 'ds-grid' }, empty('missions', 'No missions yet', 'Start with a goal. The plan comes next.', 'Create mission'), empty('clear', 'Nothing needs you', 'All decisions are clear. Your space is quiet.'), empty('offline', 'Your space is still here', 'Offline · saved records as of 10:24.'), empty('error', 'This part could not load', 'Your saved work is safe. Try reading it again.', 'Retry'), empty('first', 'Begin with a thought', 'Tell Archeus what you want to move forward.', 'Tell Archeus'))),
    section('Brand', '11', h('div', { class: 'specimen-brand' }, lockup(), coreMark(false), coreMark(true, 1), h('img', { src: 'data:image/svg+xml,' + encodeURIComponent(faviconSVG), alt: 'Favicon specimen' }), h('img', { src: 'data:image/svg+xml,' + encodeURIComponent(pwaIconSVG), alt: 'PWA icon specimen' })), caption('Static and running twins. Fixture gallery never starts breath. Quiet reveals running count.')),
    section('Palette & type', '12', h('div', { class: 'specimen-swatches' }, ...['bg', 's1', 's2', 's3', 'text', 'active', 'attention', 'blocked', 'paused', 'thinking', 'done', 'focus'].map(name => h('div', { class: 'specimen-swatch' }, h('i', { style: 'background:var(--' + name + ')' }), name))), h('p', { class: 'ds-state-sentence' }, '1 needs you · 1 verifying'), h('h2', null, 'A clear heading'), h('p', null, 'Body text keeps the next action close.'), caption('Caption · source · last updated'), h('p', { class: 'ds-mono' }, 'VERIFYING · fix/date-test')),
    section('Terminal equivalent', '13', h('pre', { class: 'specimen-terminal' }, '* ARCHEUS · Core disconnected · fixture\n\n! Search provenance — NEEDS YOU\no Fix date test — Verifying\n^ Codex — execution\n\n+ + + + o o  Verifying · step 5 of 6\n\nEnter inspect · t Tell · s Stop')),
    section('Icon library', '14', caption(Object.keys(P).length + ' icons · 24 px grid · 1.5 px stroke · currentColor'), h('div', { class: 'specimen-icons' }, ...Object.keys(P).map(name => h('div', { class: 'specimen-icon' }, icon(name, 24), h('span', null, name)))))
  ));
  window.addEventListener('message', e => {
    if (e.source !== parent || e.origin !== location.origin || e.data?.type !== 'archeus-design-theme') return;
    if (themes.includes(e.data.theme)) document.documentElement.dataset.theme = e.data.theme;
    document.documentElement.dataset.motion = e.data.motion === 'reduced' ? 'reduced' : 'full';
  });
}

function renderAtlas() {
  const theme = h('select', { class: 'ds-select', 'aria-label': 'Theme' }, ...themes.map(id => h('option', { value: id }, ({ 'dark-hc': 'Dark · high contrast', 'light-hc': 'Light · high contrast', system: 'System', forced: 'Forced colors · simulation', dark: 'Dark', light: 'Light' })[id])));
  const quiet = h('input', { type: 'checkbox', role: 'switch' });
  const sync = () => {
    document.documentElement.dataset.theme = theme.value;
    document.documentElement.dataset.motion = quiet.checked ? 'reduced' : 'full';
    document.querySelectorAll('iframe').forEach(frame => frame.contentWindow.postMessage({ type: 'archeus-design-theme', theme: theme.value, motion: quiet.checked ? 'reduced' : 'full' }, location.origin));
  };
  theme.addEventListener('change', sync); quiet.addEventListener('change', sync);
  root.replaceChildren(h('header', { class: 'atlas-head' }, wordmark(), h('h1', null, 'The shape of a calmer workspace.'), h('p', { class: 'ds-muted' }, 'V2 Live design atlas · 25 October 2026 · internal review'), h('div', { class: 'atlas-controls' }, h('label', { class: 'ds-field' }, 'Appearance', theme), h('label', { class: 'ds-toggle' }, quiet, 'Reduced motion · Quiet'), h('a', { href: './DESIGN.md' }, 'Adoption notes')), caption('Every component repeats at each width. Scroll horizontally to compare; each frame scrolls independently. All actions are local fixtures.')),
    h('div', { class: 'atlas-stage', tabindex: 0, role: 'region', 'aria-label': 'Side-by-side device specimens; scroll horizontally' }, h('div', { class: 'atlas-devices' }, ...[['Phone', 390], ['Tablet', 768], ['Desktop', 1280]].map(([name, width]) => h('section', { class: 'atlas-device' }, h('h2', null, name + ' / ' + width + ' px'), h('iframe', { title: name + ' component specimens', width, src: './gallery.html?specimen=1', onload: sync }))))), h('footer', { class: 'atlas-foot' }, 'No Core connection. No telemetry. No remote fonts. Core breath intentionally inactive for fixture data.'));
}

if (params.has('specimen')) renderSpecimen(); else renderAtlas();


