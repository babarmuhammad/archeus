// The keyboard model (E20, E21): j and k move through a list, Enter and Space act on the focused row, Esc closes the top thing, ? lists the keys.
// The terminal view keeps its own keys, so nothing here runs inside it.
import { h } from './dom.js';
import { translate } from './i18n.js';
import * as motion from './motion.js';

const ROWS = 'a.mrow, button.tl-row, article.card[data-key]';
const typing = (t) => !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

export const KEYS = [
  ['j / k', 'Next and previous row in a list'],
  ['Enter', 'Open the focused row, or do the primary action of the focused card'],
  ['Space', 'The same as Enter on a row'],
  ['Esc', 'Close the open help, menu, question or details sheet'],
  ['Ctrl+K or Cmd+K', 'Search pages, actions and projects, and run them'],
  ['?', 'Show or hide this list'],
  ['Tab and Shift+Tab', 'Move between controls'],
  ['/ in the chat bar', 'Open the command list; Up, Down, Tab, Enter and Esc work inside it']
];
export const FOCUS_ORDER = 'Focus order: toolbar, navigation, page, chat bar, bottom bar, then the details sheet, which takes focus when it opens and gives it back when it closes.';

export function installKeys(ctx, app, page) {
  let help = null, from = null;
  const rows = () => [...page.querySelectorAll(ROWS)].filter((e) => e.offsetParent !== null);
  function closeHelp() { if (!help) return; help.remove(); help = null; if (from && from.isConnected) from.focus({ preventScroll: true }); from = null; }
  function openHelp() {
    from = document.activeElement;
    const close = h('button', { class: 'btn primary', type: 'button', onclick: closeHelp }, 'Close');
    help = h('div', { class: 'helpscrim', onclick: (e) => { if (e.target === help) closeHelp(); } },
      h('section', { class: 'helpbox', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'help-h' },
        h('h2', { id: 'help-h' }, 'Keyboard shortcuts'),
        h('dl', { class: 'keys' }, ...KEYS.flatMap(([k, d]) => [h('dt', null, h('kbd', null, k)), h('dd', null, d)])),
        h('p', { class: 'note' }, FOCUS_ORDER),
        h('p', { class: 'note' }, 'The terminal view has its own keys; press ? there.'),
        h('div', { class: 'actions' }, close)));
    app.append(help); translate(help); close.focus();
    motion.enter(help.firstElementChild, { y: 0, s: .98, dur: 1 });
  }
  document.addEventListener('keydown', (e) => {
    if (help) {
      if (e.key === 'Escape' || e.key === '?') { e.preventDefault(); e.stopImmediatePropagation(); closeHelp(); } else if (e.key === 'Tab') { e.preventDefault(); help.querySelector('button').focus(); }
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || ctx.route.name === 'terminal' || (e.target.closest && e.target.closest('.tui'))) return;
    if (e.key === '?') { e.preventDefault(); openHelp(); return; }
    const cur = document.activeElement && document.activeElement.closest ? document.activeElement.closest(ROWS) : null;
    if (e.key === 'j' || e.key === 'k') {
      const list = rows(); if (!list.length) return;
      const i = list.indexOf(cur), next = list[e.key === 'j' ? (i < 0 ? 0 : Math.min(list.length - 1, i + 1)) : (i < 0 ? list.length - 1 : Math.max(0, i - 1))];
      e.preventDefault();
      if (next.tagName === 'ARTICLE') next.tabIndex = -1;
      next.focus(); next.scrollIntoView({ block: 'nearest' });
    } else if (cur && (e.key === 'Enter' || e.key === ' ')) {
      if (cur.tagName === 'ARTICLE') { if (document.activeElement !== cur) return; const b = cur.querySelector('.btn.primary, a.btn, button'); if (b) { e.preventDefault(); b.click(); } } else if (e.key === ' ' && cur.tagName === 'A') { e.preventDefault(); cur.click(); }
    }
  });
  return { openHelp, closeHelp, isHelp: () => !!help };
}
