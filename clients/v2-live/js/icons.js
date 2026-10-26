import { s } from './dom.js';

export const P = {
  now: ['circle:12,12,8', 'circle:12,12,2:f'],
  work: ['path:M5 6h14M5 12h14M5 18h9'],
  attention: ['path:M12 3l9 9-9 9-9-9zM12 8v5M12 16v.1'],
  map: ['circle:6,6,2', 'circle:18,8,2', 'circle:11,18,2', 'path:M8 6l8 2M7 8l3 8M17 10l-5 6'],
  replay: ['path:M4 10a8 8 0 1 1 1 7M4 4v6h6M12 7v5l3 2'],
  chat: ['path:M4 5h16v11H9l-5 4zM8 9h8M8 12h5'],
  settings: ['path:M4 7h8M16 7h4M4 17h4M12 17h8', 'circle:14,7,2', 'circle:10,17,2'],
  terminal: ['path:M4 5h16v14H4zM7 9l3 3-3 3M13 15h4'],
  menu: ['path:M4 6h16M4 12h16M4 18h16'],
  device: ['path:M3 4h18v12H3zM8 20h8M12 16v4'],
  theme: ['circle:12,12,8', 'path:M12 4a8 8 0 0 1 0 16z:f'],
  motion: ['path:M3 12c3-7 6-7 9 0s6 7 9 0'],
  sim: ['path:M8 4l12 8-12 8z'],
  pause: ['path:M8 5v14M16 5v14'],
  close: ['path:M6 6l12 12M18 6L6 18'],
  security: ['path:M12 3l8 3v5c0 5-4 8-8 10-4-2-8-5-8-10V6zM9 12l2 2 4-5'],
  health: ['path:M3 12h4l2-6 5 12 2-6h5'],
  accounts: ['circle:12,8,3', 'path:M5 20c0-7 14-7 14 0'],
  all: ['path:M4 4h6v16H4zM14 4h6v7h-6zM14 15h6v5h-6z'],
  lang: ['circle:12,12,8', 'path:M4 12h16M12 4c4 4 4 12 0 16-4-4-4-12 0-16'],
  note: ['path:M5 4h14v12l-5 4H5zM14 20v-4h5M8 8h8M8 12h6'],
  chevron: ['path:M9 6l6 6-6 6'],
  home: ['path:M3 11l9-8 9 8M5 9v11h5v-6h4v6h5V9'],
  back: ['path:M14 5l-7 7 7 7'],
  forward: ['path:M10 5l7 7-7 7'],
  search: ['circle:10,10,6', 'path:M15 15l6 6'],
  done: ['circle:12,12,7:f'],
  running: ['circle:12,12,7'],
  needs_you: ['circle:12,12,8', 'circle:12,12,3:f'],
  blocked: ['path:M7 3h10l4 4v10l-4 4H7l-4-4V7zM8 8l8 8M16 8l-8 8'],
  paused: ['path:M8 5v14M16 5v14'],
  thinking: ['circle:5,12,1.5:f', 'circle:12,12,1.5:f', 'circle:19,12,1.5:f'],
  approve: ['path:M5 12l4 4L19 6'],
  reject: ['path:M6 6l12 12M18 6L6 18'],
  resume: ['path:M8 5l11 7-11 7z'],
  cancel: ['circle:12,12,8', 'path:M6 6l12 12'],
  estop: ['path:M8 3h8l5 5v8l-5 5H8l-5-5V8zM9 9h6v6H9z'],
  retry: ['path:M20 10a8 8 0 1 0 0 5M20 4v6h-6'],
  replan: ['path:M4 5h9M4 10h6M4 15h4M14 9l5 5-5 5M10 14h9'],
  open: ['path:M14 4h6v6M20 4l-9 9M10 4H4v16h16v-6'],
  pin: ['path:M9 3h6l-1 6 4 4v2H6v-2l4-4zM12 15v6'],
  mission: ['circle:12,12,8', 'circle:12,12,3'],
  task: ['path:M5 4h14v16H5zM8 9l2 2 5-4M8 15h8'],
  plan: ['path:M8 5h13M8 12h13M8 19h13', 'circle:3,5,1:f', 'circle:3,12,1:f', 'circle:3,19,1:f'],
  status: ['circle:12,12,8', 'path:M8 12h2l2-4 2 8 2-4h1'],
  execution: ['path:M12 4l9 16H3zM10 10l5 4-5 3'],
  approval: ['path:M12 3l9 9-9 9-9-9zM8 12l3 3 5-6'],
  idea: ['path:M8 15a6 6 0 1 1 8 0l-1 3H9zM10 21h4M12 8v5'],
  knowledge: ['path:M4 5c3-1 5 0 8 2 3-2 5-3 8-2v14c-3-1-5 0-8 2-3-2-5-3-8-2zM12 7v14'],
  project: ['path:M3 6h7l2 3h9v11H3z'],
  repository: ['path:M5 3h14v18H5zM5 17h14M9 7h6M9 10h4'],
  account: ['circle:12,8,3', 'path:M5 20c0-7 14-7 14 0'],
  model: ['path:M12 3l9 5v8l-9 5-9-5V8zM3 8l9 5 9-5M12 13v8'],
  hook: ['path:M7 3v11a5 5 0 0 0 10 0v-3l-3 3M17 11l3 3'],
  mcp: ['path:M8 3v5M16 3v5M5 8h14v4a7 7 0 0 1-14 0zM12 19v3'],
  agent: ['path:M6 7h12v12H6zM12 3v4M3 11h3M18 11h3M9 16h6', 'circle:9,11,1:f', 'circle:15,11,1:f'],
  usage: ['path:M5 20V10M12 20V4M19 20v-7M3 20h18'],
  offline: ['path:M3 8c5-4 13-4 18 0M6 12c3-3 9-3 12 0M9 16c2-1 4-1 6 0M3 3l18 18', 'circle:12,20,1:f'],
  phone: ['path:M7 3h10v18H7zM10 6h4M11 18h2'],
  tablet: ['path:M4 3h16v18H4zM11 18h2'],
  sun: ['circle:12,12,4', 'path:M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1M18 18l1 1M5 19l1-1M18 6l1-1'],
  moon: ['path:M20 15A8 8 0 0 1 9 4a8 8 0 1 0 11 11z'],
  language: ['path:M3 5h12M9 3v2M5 5c0 6 4 10 9 12M13 5c0 6-4 10-9 12M14 21l4-11 4 11M16 17h4'],
  plus: ['path:M12 5v14M5 12h14'],
  minus: ['path:M5 12h14'],
  send: ['path:M3 3l19 9-19 9 4-9zM7 12h15'],
  attach: ['path:M8 13l7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2M6 15l9-9'],
  copy: ['path:M8 8h12v13H8zM16 8V3H3v13h5'],
  link: ['path:M10 7l3-3a5 5 0 0 1 7 7l-3 3M14 17l-3 3a5 5 0 0 1-7-7l3-3M8 16l8-8'],
  evidence: ['path:M5 3h10l4 4v14H5zM15 3v5h4M8 13l2 2 5-5M8 18h8'],
  relations: ['circle:12,5,2', 'circle:5,19,2', 'circle:19,19,2', 'path:M12 7v5M5 17v-5h14v5'],
  why: ['circle:12,12,9', 'path:M9 9a3 3 0 1 1 4 3c-1 0-1 1-1 2M12 17v.1'],
  clock: ['circle:12,12,8', 'path:M12 7v5l4 2'],
  lock: ['path:M5 10h14v11H5zM8 10V7a4 4 0 0 1 8 0v3M12 14v3'],
  warning: ['path:M12 3l10 18H2zM12 9v5M12 17v.1'],
  info: ['circle:12,12,8', 'path:M12 11v6M12 7v.1'],
  more: ['circle:5,12,1:f', 'circle:12,12,1:f', 'circle:19,12,1:f'],
  filter: ['path:M3 5h18l-7 8v6l-4 2v-8z'],
  sort: ['path:M7 4v16M3 16l4 4 4-4M14 5h7M14 10h5M14 15h3'],
  download: ['path:M12 3v12M7 10l5 5 5-5M4 16v5h16v-5'],
  expand: ['path:M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5'],
  extensions: ['path:M9 4h6v4h4v6h-4v6H9v-6H5V8h4z']
};

export function icon(name, size = 22) {
  const svg = s('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false' });
  for (const part of P[name] || []) {
    const [kind, value, flag] = part.split(':');
    const fill = flag === 'f' ? 'currentColor' : 'none';
    if (kind === 'path') svg.append(s('path', { d: value, fill }));
    else { const [cx, cy, r] = value.split(',').map(Number); svg.append(s('circle', { cx, cy, r, fill })); }
  }
  return svg;
}

// Core presentation classes and the areas' tones, drawn as the kit's state glyphs. The word beside it still comes from present(); the shape only repeats it.
const STATE_ICON = { needs_you: 'needs_you', attention: 'needs_you', active: 'running', verifying: 'running', reviewing: 'running', proposed: 'running', blocked: 'blocked', failed: 'blocked', paused: 'paused', planning: 'thinking', thinking: 'thinking', done: 'done', ok: 'done', approved: 'approval', neutral: 'minus', inactive: 'minus', unknown: 'minus' };
export const glyph = (state, size = 14) => icon(STATE_ICON[state] || 'minus', size);
