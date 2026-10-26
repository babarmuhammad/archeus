import {sceneNow, sceneCalm, sceneMission} from './scenes.js';

const gallery = document.querySelector('#gallery'), scenes = [];
const t = (key, fallback) => fallback;
for (const [name, create] of [['Now — concept 02', sceneNow], ['Calm — concept 07', sceneCalm], ['Mission — concept 03', sceneMission]]) {
  for (const [width, height] of [[1440, 900], [768, 1024], [390, 844]]) {
    const section = document.createElement('section'), heading = document.createElement('h2'), pair = document.createElement('div');
    heading.textContent = t(`gallery.${name}`, `${name} · ${width} × ${height}`); pair.className = 'pair'; section.append(heading, pair);
    for (const theme of ['dark', 'light']) {
      const figure = document.createElement('figure'), caption = document.createElement('figcaption'), frame = document.createElement('div'), container = document.createElement('div');
      caption.textContent = t(`theme.${theme}`, theme === 'dark' ? 'Dark' : 'Light'); frame.className = 'frame'; frame.style.width = `${width}px`; frame.style.height = `${height}px`;
      frame.append(container); figure.append(caption, frame); pair.append(figure);
      const api = create(container, {width, height, theme, t}); scenes.push({api, theme});
    }
    gallery.append(section);
  }
}
document.querySelector('#contrast').addEventListener('change', event => {
  for (const {api, theme} of scenes) api.setTheme(`${theme}${event.target.checked ? '-hc' : ''}`);
});
for (const name of ['scene-select', 'scene-review']) gallery.addEventListener(name, event => {
  document.querySelector('#selection').textContent = t('gallery.event', `${event.type}: ${event.detail.id} (fixture only; no action executed)`);
});
