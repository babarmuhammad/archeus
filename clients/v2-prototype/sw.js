const CACHE = 'archeus-v2-proto-ms1';
const SHELL = ['./', './index.html', './style.css', './app.js', './layout-r10c.js', './manifest.json', './icon-192.png', './icon-512.png', './icon-maskable-512.png',
  './art/mission-base.webp', './art/shared-base.webp', './fonts/LibreCaslonText-wght.ttf', './fonts/SourceSans3-wght.ttf'];

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
