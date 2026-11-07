/* Registra il service worker: con il manifest della pagina, l'app si può aggiungere alla schermata Home. */
(() => {
  'use strict';
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', {scope: '/'}).catch(error => console.warn('Service worker non registrato', error));
  });
})();
