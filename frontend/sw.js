const CACHE = 'sales-agent-local-v1';
const ASSETS = ['./', './index.html', './styles.css', './app.js', './manifest.webmanifest', './icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // O painel é servido com Cache-Control: no-store e muda junto com a VPS.
  // Servir HTML/JS do cache prendia o operador numa versão antiga da
  // interface; para esses arquivos a rede vem primeiro e o cache só cobre
  // indisponibilidade.
  const pathname = new URL(event.request.url).pathname;
  if (event.request.mode === 'navigate' || /\.(?:js|css|html)$/.test(pathname)) {
    event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
