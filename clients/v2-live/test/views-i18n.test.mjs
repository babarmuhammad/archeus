import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { search: '?lang=it' };
const { tr } = await import('../js/i18n.js');
const { CHAPTERS } = await import('../js/autopilot-script.js');

const EN_WORDS = /\b(Territories|Rings?|Network|Project|Needs you|missions?|Open work)\b/;
const IT_WORDS = /\b(Territori|Anelli|Rete|Progetto|Ti serve|missione|missioni|Apri il lavoro)\b/;
const names = { 'Territories view': 'Vista a territori', 'Rings view': 'Vista ad anelli', 'Network view': 'Vista a rete' };

test('each view name renders in one language: the Italian name carries no English view word', () => {
  for (const [en, it] of Object.entries(names)) {
    assert.equal(tr(en), it);
    assert.doesNotMatch(tr(en), EN_WORDS);
    assert.doesNotMatch(en, IT_WORDS);
  }
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
  assert.equal(tr('1 need you'), '1 ti serve');
  assert.equal(tr('2 need you'), '2 ti servono');
});
