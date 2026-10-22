const CACHE = 'archeus-v2-proto-final';
const SHELL = ['./', './index.html', './style.css', './app.js', './slash.js', './layout-r10c.js', './manifest.json', './icon-192.png', './icon-512.png', './icon-maskable-512.png',
  './art/phone-1-base.webp', './art/phone-1-layout.js', './art/phone-1-type.js', './art/phone-2-base.webp', './art/phone-2-layout.js', './art/phone-2-type.js', './art/phone-3-base.webp', './art/phone-3-layout.js', './art/phone-3-type.js',
  './art/desktop-now-base.webp', './art/replay-base.webp', './art/mission-base.webp', './art/shared-base.webp', './fonts/LibreCaslonText-VF.ttf', './fonts/SourceSans3-wght.ttf', './fonts/Inter-VF.ttf', './fonts/RobotoMono-wght.ttf'];
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
