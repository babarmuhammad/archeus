const CACHE = 'archeus-v2-proto-d2';
const SHELL = ['./', './index.html', './style.css', './app.js', './manifest.json', './icon-192.png', './icon-512.png', './icon-maskable-512.png', './art/desktop-now-base.webp', './fonts/LibreCaslonText-wght.ttf', './fonts/SourceSans3-wght.ttf'];

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
