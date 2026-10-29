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
