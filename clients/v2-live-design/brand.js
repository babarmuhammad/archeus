import { h, s } from './dom.js';

export function coreMark(running = false, count = 1) {
  return h('div', { class: 'ds-core', 'data-live': String(running), 'data-core': 'idle' },
    s('svg', { class: 'core-breath', viewBox: '0 0 96 96', width: 96, height: 96, 'aria-hidden': 'true', focusable: 'false', fill: 'none', stroke: 'currentColor', 'stroke-width': 1 },
      s('path', { d: 'M48 4L58 38 92 48 58 58 48 92 38 58 4 48 38 38Z' }),
      s('path', { d: 'M20 20L48 34 76 20 62 48 76 76 48 62 20 76 34 48Z', opacity: '.5' }),
      s('path', { d: 'M48 4V92M4 48H92M38 38L58 58M58 38L38 58', opacity: '.7' }),
      s('circle', { cx: 48, cy: 48, r: 2, fill: 'currentColor' })),
    h('span', { class: 'ds-core-static' }, '◉ ', count + ' running'),
    h('span', { class: 'ds-sr' }, running ? count + ' running' : 'Nothing running'));
}

export function wordmark() {
  return h('span', { class: 'ds-wordmark', 'aria-label': 'Archeus V2' }, 'ARCHEUS ', h('span', null, 'V2'));
}

export function lockup() {
  return h('div', { class: 'ds-lockup' }, coreMark(), wordmark());
}

export const faviconSVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0C0811"/><path d="M32 7L38 26 57 32 38 38 32 57 26 38 7 32 26 26Z" fill="none" stroke="#EFE9DA" stroke-width="2"/></svg>';
export const pwaIconSVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="#0C0811"/><g fill="none" stroke="#EFE9DA" stroke-width="6"><path d="M256 112L288 224 400 256 288 288 256 400 224 288 112 256 224 224Z"/><path d="M168 168L256 212 344 168 300 256 344 344 256 300 168 344 212 256Z" opacity=".5"/></g></svg>';
