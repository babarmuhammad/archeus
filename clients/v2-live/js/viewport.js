// The one place that knows what a phone is and where the visual viewport is. Everything else asks isPhone() or reads the attributes and properties set here:
//   <html data-phone="true|false">, #device[data-phone]   the phone shell is on (a frame or window under 600 px, or a phone held sideways)
//   <html data-kb="open">                                 the on-screen keyboard is up
//   --vv-h, --vv-bottom                                   visual viewport height, and the height the keyboard (or a browser bar) takes at the bottom
// The measure is the #device frame, not the window, so a 390 px frame on a desktop window is a phone and a 1440 px one is not.
import { phoneBox, keyboard, LANDSCAPE_QUERY } from './phone-model.js';

const root = document.documentElement;
const device = document.getElementById('device');
const sideways = window.matchMedia(LANDSCAPE_QUERY);
const listeners = new Set();
let phone = false;

export const isPhone = () => phone;

// fn(isPhone) runs whenever the shell flips between phone and desktop. Returns the function that stops it.
export function onPhoneChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

function measure() {
  const w = device ? device.clientWidth : innerWidth;
  if (!w) return; // the All devices view hides the frame: keep what we had
  const next = phoneBox({ frameW: w, landscape: sideways.matches });
  if (next === phone && root.dataset.phone) return;
  const flipped = next !== phone;
  phone = next;
  root.dataset.phone = String(phone);
  if (device) device.dataset.phone = String(phone);
  if (flipped) listeners.forEach((fn) => fn(phone));
}

const vv = window.visualViewport;
let frame = 0;
function viewport() {
  frame = 0;
  const editing = !!document.activeElement && document.activeElement.matches('input, textarea, select, [contenteditable=""], [contenteditable="true"]');
  const k = keyboard({ innerH: innerHeight, vvH: vv.height, vvTop: vv.offsetTop, scale: vv.scale, editing });
  root.style.setProperty('--vv-h', Math.round(vv.height) + 'px');
  root.style.setProperty('--vv-bottom', k.bottom + 'px');
  if (k.open) root.dataset.kb = 'open'; else delete root.dataset.kb;
}
const schedule = () => { if (!frame) frame = requestAnimationFrame(viewport); };

// The browser chrome follows the in-app theme, which can differ from the OS scheme the two meta tags answer to.
function themeColour() {
  const c = getComputedStyle(root).getPropertyValue('--bg').trim();
  if (c) document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute('content', c));
}

measure();
sideways.addEventListener('change', measure);
if (device && typeof ResizeObserver !== 'undefined') new ResizeObserver(measure).observe(device); else addEventListener('resize', measure);
if (vv) {
  vv.addEventListener('resize', schedule); vv.addEventListener('scroll', schedule);
  addEventListener('focusin', schedule);
  addEventListener('focusout', () => setTimeout(viewport, 120)); // iOS keeps a stale offset until the field has really lost focus
  viewport();
}
new MutationObserver(themeColour).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
themeColour();
