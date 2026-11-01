// Pure part of the keyboard model: Alt+1, Alt+2 and Alt+3 pick the three Overview views in the order of the view switch.
export const OVERVIEW_VIEWS = ['territories', 'rings', 'network'];
export function overviewKey(e) {
  if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return null;
  const m = /^(?:Digit|Numpad)([123])$/.exec(e.code || '');
  return m ? OVERVIEW_VIEWS[m[1] - 1] : null;
}

export const KEYS = [
  ['j / k', 'Next and previous row in a list'],
  ['Enter', 'Open the focused row, or do the primary action of the focused card'],
  ['Space', 'The same as Enter on a row'],
  ['Esc', 'Close the open help, menu, question or details sheet'],
  ['Ctrl+K or Cmd+K', 'Search pages, actions and projects, and run them'],
  ['Alt+1, Alt+2, Alt+3', 'On the Overview: Territories, Rings, Network'],
  ['Ctrl+Enter or Cmd+Enter', 'In the chat bar: steer the running mission (Enter queues a message)'],
  ['?', 'Show or hide this list'],
  ['Tab and Shift+Tab', 'Move between controls'],
  ['/ in the chat bar', 'Open the command list; Up, Down, Tab, Enter and Esc work inside it']
];
export const FOCUS_ORDER = 'Focus order: toolbar, navigation, page, chat bar, bottom bar, then the details sheet, which takes focus when it opens and gives it back when it closes.';
