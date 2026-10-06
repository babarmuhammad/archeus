// The offline shell (p16-design-gate D6, §13.5). It caches the page and its
// hashed assets so an installed app opens without the network, and says it
// is offline. It NEVER touches /v1/: no API answer, no token and no event is
// ever cached here — what Archeus knows is read from Core or not shown.
const SHELL = 'archeus-shell-v1';

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(['/'])));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/v1/')) return;
  if (url.pathname === '/') {
    // network first: an upgraded Core's page wins; the cached one is for offline
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          const copy = r.clone();
          caches.open(SHELL).then((c) => c.put('/', copy));
          return r;
        })
        .catch(() => caches.match('/')),
    );
  } else if (url.pathname.startsWith('/assets/')) {
    // hashed names never change content: cache first
    e.respondWith(
      caches.match(e.request).then(
        (hit) =>
          hit ||
          fetch(e.request).then((r) => {
            const copy = r.clone();
            caches.open(SHELL).then((c) => c.put(e.request, copy));
            return r;
          }),
      ),
    );
  }
});
