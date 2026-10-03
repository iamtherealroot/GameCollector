const VERSION = 'bibo-v5.0.4';
const STATIC_CACHE = VERSION + '-static';
const PAGE_CACHE = VERSION + '-pages';
const APP_SHELL = [
  '/offline', '/scanner', '/offline-queue',
  '/static/style.css', '/static/offline-queue.js',
  '/static/vendor/html5-qrcode-2.3.8.min.js',
  '/static/manifest.webmanifest', '/static/favicon-bibo.ico',
  '/static/icon-192-bibo.png', '/static/icon-512-bibo.png',
  '/static/apple-touch-icon-bibo.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(STATIC_CACHE).then(cache =>
    Promise.allSettled(APP_SHELL.map(url => cache.add(url)))
  ).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => (key.startsWith('gamecollector-') || key.startsWith('bibo-')) && ![STATIC_CACHE, PAGE_CACHE].includes(key)).map(key => caches.delete(key))
  )).then(() => self.clients.claim()));
});

function excluded(url) {
  return ['/login', '/logout'].includes(url.pathname) ||
    url.pathname.startsWith('/admin/') || url.pathname.startsWith('/feedback') || url.pathname.startsWith('/top10') || url.pathname.startsWith('/account') ||
    url.pathname.startsWith('/export/') || url.pathname.startsWith('/api/');
}

function cacheablePage(url) {
  return url.pathname === '/' || url.pathname === '/scanner' || url.pathname === '/offline-queue' ||
    url.pathname.startsWith('/collection') || url.pathname.startsWith('/games') ||
    url.pathname.startsWith('/collector/') || url.pathname.startsWith('/hardware') ||
    url.pathname.startsWith('/accessories') || url.pathname.startsWith('/price-center') ||
    url.pathname.startsWith('/library');
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== location.origin || excluded(url)) return;

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(request).then(cached => {
      const refreshed = fetch(request).then(response => {
        if (response.ok) caches.open(STATIC_CACHE).then(cache => cache.put(request, response.clone()));
        return response;
      }).catch(() => cached);
      return cached || refreshed;
    }));
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then(response => {
      if (response.ok && cacheablePage(url)) caches.open(PAGE_CACHE).then(cache => cache.put(request, response.clone()));
      return response;
    }).catch(() => caches.match(request).then(cached => cached || caches.match(url.pathname).then(pathCached => pathCached || caches.match('/offline')))));
  }
});

self.addEventListener('sync', event => {
  if (event.tag !== 'gc-sync-captures') return;
  event.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(clients => {
    clients.forEach(client => client.postMessage({type: 'gc-sync-captures'}));
  }));
});

self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
  if (event.data && event.data.type === 'CLEAR_PRIVATE_CACHES') caches.delete(PAGE_CACHE);
});
