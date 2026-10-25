import { s } from './dom.js';

const P = {
  now: ['circle:12,12,7', 'circle:12,12,2.2:f'],
  work: ['path:M4 7h16M4 12h16M4 17h10'],
  attention: ['path:M12 3l9 9-9 9-9-9z'],
  map: ['circle:6,7,2.4', 'circle:18,8,2.4', 'circle:12,18,2.4', 'path:M8 8l8 0M7 9l4 7M17 10l-4 6'],
  replay: ['path:M4 12a8 8 0 1 0 3-6.2', 'path:M4 4v5h5', 'path:M12 8v4l3 2'],
  chat: ['path:M4 5h16v11H9l-5 4z'],
  settings: ['path:M4 7h9M17 7h3M4 17h3M11 17h9', 'circle:15,7,2', 'circle:9,17,2'],
  terminal: ['path:M4 5h16v14H4z', 'path:M7 10l3 2-3 2M12 15h5'],
  menu: ['path:M4 7h16M4 12h16M4 17h16'],
  device: ['path:M4 5h16v11H4z', 'path:M9 20h6M12 16v4'],
  theme: ['circle:12,12,8', 'path:M12 4a8 8 0 0 1 0 16z:f'],
  motion: ['path:M3 12c3-6 6-6 9 0s6 6 9 0'],
  sim: ['path:M7 5l12 7-12 7z'],
  pause: ['path:M8 5v14M16 5v14'],
  close: ['path:M6 6l12 12M18 6L6 18'],
  chevron: ['path:M9 6l6 6-6 6']
};

export function icon(name, size) {
  const d = size || 22;
  const svg = s('svg', { width: d, height: d, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false' });
  for (const part of P[name] || []) {
    const [kind, rest, flag] = part.split(':'), fill = flag === 'f' ? 'currentColor' : 'none';
    if (kind === 'path') svg.append(s('path', { d: rest, fill }));
    else { const [cx, cy, r] = rest.split(',').map(parseFloat); svg.append(s('circle', { cx, cy, r, fill })); }
  }
  return svg;
}
