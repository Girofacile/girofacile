/* Service worker di GiroFacile: rende installabili l'app autista e il portale mobile.
   Nessun dato in cache: le pagine si chiedono sempre al server; senza rete si mostra
   la pagina «Sei offline». Le API non passano di qui (dati sempre aggiornati e privati). */
const OFFLINE = '/static/offline.html';
const CACHE = 'gf-offline-v1';

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.add(OFFLINE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  if (event.request.mode !== 'navigate') return;  // solo l'apertura delle pagine
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
});
