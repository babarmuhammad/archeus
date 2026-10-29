import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { search: '?lang=it' };
const { tr, translate } = await import('../js/i18n.js');
const { CHAPTERS } = await import('../js/autopilot-script.js');

const EN_WORDS = /\b(Territories|Rings?|Network|Project|Needs you|missions?|Open work)\b/;
const IT_WORDS = /\b(Territori|Anelli|Rete|Progetto|Richiede la tua attenzione|missione|missioni|Apri il lavoro)\b/;
const names = {
  'Territories: one cell per project': 'Territori: una cella per progetto',
  'Rings: a lane per state': 'Anelli: una corsia per stato',
  'Network: missions around each project': 'Rete: le missioni attorno a ogni progetto'
};

test('each view name renders in one language: the Italian name carries no English view word', () => {
  for (const [en, it] of Object.entries(names)) {
    assert.equal(tr(en), it);
    assert.doesNotMatch(tr(en), EN_WORDS);
    assert.doesNotMatch(en, IT_WORDS);
  }
});

test('Italian Tell title and placeholder use the owner wording', () => {
  assert.equal(tr('Tell Archeus'), 'Dimmi cosa fare…');
  assert.equal(tr('Tell Archeus what to do…'), 'Dimmi cosa fare…');
});

test('the focus caption strings translate whole: no English word is left beside the Italian', () => {
  for (const en of ['Project', 'Open work', '1 mission', '20 missions']) {
    const it = tr(en);
    assert.notEqual(it, en);
    assert.doesNotMatch(it, EN_WORDS);
  }
  assert.equal(tr('20 missions'), '20 missioni');
});

test('the Autopilot view chapter keeps its English and Italian text apart', () => {
  const ch = CHAPTERS.find((c) => c.id === 'ov-network');
  for (const [en, it] of [ch.t, ch.c]) {
    assert.notEqual(en, it);
    assert.doesNotMatch(en, IT_WORDS);
    assert.doesNotMatch(it, EN_WORDS);
  }
});


test('territory state words and composed counts translate fully in Italian', () => {
  for (const en of ['Needs you', 'Running', 'Done', 'Blocked', 'Quiet', 'Paused', 'Planning',
    '1 need you', '2 need you', '1 running', '2 running',
    '1 idea captured', '2 ideas captured', '1 idea captured, no missions yet', '2 ideas captured, no missions yet',
    '1 projects. 1 need you.', '2 projects. 2 need you.']) {
    assert.notEqual(tr(en), en, en);
    assert.doesNotMatch(tr(en), /\b(need you|running|ideas|captured|projects?|missions?|yet)\b/i, en);
  }
  assert.equal(tr('1 worktree'), '1 worktree');
  assert.equal(tr('2 worktrees'), '2 worktree');
  assert.equal(tr('1 need you'), '1 richiede la tua attenzione');
  assert.equal(tr('2 need you'), '2 richiedono la tua attenzione');
});

test('owner attention wording covers zero, one and many in composed captions and map instructions', () => {
  for (const n of [0, 1, 2]) {
    const phrase = n + (n === 1 ? ' richiede' : ' richiedono') + ' la tua attenzione';
    for (const en of [`${n} need you`, `${n} needs you`, `Work, ${n} need you`, `${n} need you · 1 running`]) {
      assert.ok(tr(en).includes(phrase), en);
      assert.doesNotMatch(tr(en), /\b(need|needs|you|running|Work)\b/, en);
    }
    assert.equal(tr(`${n} projects. ${n} need you.`), n + (n === 1 ? ' progetto. ' : ' progetti. ') + (n === 0 ? 'Nessuno richiede la tua attenzione.' : phrase + '.'));
    for (const tail of ['Tab through the stars, Enter to select.', 'Tab through the projects in the order of the lanes, Enter to select.']) {
      const en = `${n} nodes across ${n} projects. ${n} need you. ${tail}`;
      assert.ok(tr(en).startsWith(n + (n === 1 ? ' nodo in 1 progetto. ' : ` nodi in ${n} progetti. `) + phrase + '.'), en);
      assert.doesNotMatch(tr(en), /\b(nodes|across|projects|need|you|through|lanes|stars)\b/, en);
    }
  }
  assert.equal(tr('Nothing needs you'), 'Niente richiede la tua attenzione');
  assert.equal(tr('Nothing needs you.'), 'Niente richiede la tua attenzione.');
  assert.equal(tr('needs you'), 'richiede la tua attenzione');
});

test('policy section and phase words keep their context during DOM translation', () => {
  const previousDocument = globalThis.document, previousFilter = globalThis.NodeFilter;
  const nodes = [
    ['Active', 'project-phase-word', 'Attiva'], ['Active', 'wt-state', 'Attivo'],
    ['Active', 'am-focus-wt-state', 'Attivo'], ['Policy', 'security-nav-policy', 'Regole'],
    ['Policy', 'technical', 'Policy']
  ].map(([value, kind, expected]) => ({nodeType: 3, nodeValue: value, expected, parentElement: {
    classList: {contains: c => c === kind}, closest: selector => selector === '[data-key="security-nav-policy"]' && kind === 'security-nav-policy'
  }}));
  try {
    globalThis.NodeFilter = {SHOW_TEXT: 4, SHOW_ELEMENT: 1};
    globalThis.document = {createTreeWalker: () => { let i = 0; return {currentNode: nodes[0], nextNode: () => nodes[++i]}; }};
    translate(nodes[0]);
    for (const n of nodes) assert.equal(n.nodeValue, n.expected);
  } finally {
    if (previousDocument === undefined) delete globalThis.document; else globalThis.document = previousDocument;
    if (previousFilter === undefined) delete globalThis.NodeFilter; else globalThis.NodeFilter = previousFilter;
  }
});

test('subentro, reduced motion and Core follow owner terminology', () => {
  assert.equal(tr('Failover'), 'Subentro');
  assert.equal(tr('Quiet motion'), 'Movimento ridotto');
  assert.equal(tr('Quiet'), 'Quieto');
  assert.equal(tr('In failover order within Codex. No account can take new work.'), 'In ordine di subentro dentro Codex. Nessun account può prendere nuovo lavoro.');
  assert.match(tr('Work graph: missions and decisions as nodes round the core. The list has the same content.'), /attorno al Core/);
  for (const ch of CHAPTERS) for (const [en, it] of [ch.t, ch.c]) {
    assert.doesNotMatch(it, /ti serv[eo]|Ne serv|politica|failover|nucleo/i, ch.id);
    assert.doesNotMatch(en, IT_WORDS, ch.id);
  }
});

test('English source remains unchanged by translation, including contextual words', async () => {
  const {set} = await import('../js/store.js');
  const previousDocument = globalThis.document;
  try {
    globalThis.document = {documentElement: {dataset: {}}};
    set('lang', 'en');
    for (const en of ['1 need you', '0 projects. 0 need you.', 'Work, 2 need you', 'Needs you · 2', 'Quiet motion', 'Failover', 'Policy', 'Active']) {
      assert.equal(tr(en), en);
      assert.equal(tr(en, 'phase:'), en);
      assert.equal(tr(en, 'nav:'), en);
    }
    for (const ch of CHAPTERS) for (const [en] of [ch.t, ch.c]) assert.equal(tr(en), en);
  } finally {
    set('lang', 'it');
    if (previousDocument === undefined) delete globalThis.document; else globalThis.document = previousDocument;
  }
});
