// Service worker minimal : cache-first pour le shell statique (HTML/CSS/JS/icônes),
// jamais de cache pour /api/* — les données financières doivent toujours être fraîches.
// Le cache étant servi en priorité, ce nom doit changer à chaque modification
// du shell : l'ancien cache est purgé à l'activation et le nouveau code arrive.
const CACHE_NAME = 'dashboard-fi-shell-v2';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/api/')) return;
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) return cached;
      return fetch(event.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      });
    }).catch(() => caches.match(event.request))
  );
});
