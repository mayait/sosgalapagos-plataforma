/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE). */
{% load reportes_extras %}/* Service worker del mapa. Guarda la interfaz, el mapa base y las capas ya vistas,
   para que la app instalada abra sin señal. Los reportes van siempre a la red:
   el mapa guarda la última respuesta por su cuenta y muestra de qué hora es. */
const VERSION = 'sos-v24';
const E = '{{ estaticos }}';
const INTERFAZ = [
  '/riesgos/', '/riesgos/reportar/',
  "{% propio 'mapa/estilos.css' %}", "{% propio 'mapa/comun.js' %}", "{% propio 'mapa/base.js' %}", "{% propio 'mapa/capas.js' %}", "{% propio 'mapa/buscar.js' %}", "{% propio 'mapa/mapa.js' %}", "{% propio 'mapa/reportar.js' %}",
  E + 'terceros/maplibre-gl.js', E + 'terceros/maplibre-gl.css', E + 'terceros/pmtiles.js', E + 'terceros/basemaps.js',
  E + 'terceros/htmx.min.js', E + 'terceros/alpine.min.js',
  E + 'marca/ZalandoSansExpanded.ttf', E + 'marca/usfq-galapagos-color.svg',
  E + 'base/iconos/light.json', E + 'base/iconos/light.png', E + 'base/iconos/light@2x.json', E + 'base/iconos/light@2x.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(INTERFAZ)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const pedido = e.request;
  const url = new URL(pedido.url);
  if (pedido.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/riesgos/api/') || url.pathname.startsWith('/riesgos/admin/') || url.pathname.startsWith('/riesgos/medios/') || url.pathname.startsWith('/riesgos/relieve3d/')) return; // siempre a la red

  // El mapa base se pide por trozos (Range). Se guarda el archivo entero una vez y de ahí se corta.
  if (url.pathname.endsWith('.pmtiles')) { e.respondWith(trozo(pedido)); return; }

  // Lo que casi nunca cambia (librerías, mapa base, marca, archivos de capas): primero lo guardado.
  // El manifiesto y el índice de descargas de /mapas van a la red, para ver enseguida una capa nueva.
  // El código propio (mapa/) va primero a la red, para que un cambio se vea al instante.
  const estatico = ['terceros/', 'base/', 'marca/', 'app/'].some((d) => url.pathname.startsWith(E + d)) || url.pathname.startsWith('/mapas/datos/') || url.pathname.startsWith('/mapas/teselas/');
  if (estatico) {
    // Primero lo guardado, y se refresca por detrás.
    e.respondWith(
      caches.open(VERSION).then(async (c) => {
        const guardado = await c.match(pedido);
        const red = fetch(pedido).then((r) => {
          if (r.ok) { c.put(pedido, r.clone()); if (url.search) podar(c, url); }
          return r;
        }).catch(() => guardado);
        return guardado || red;
      }),
    );
    return;
  }
  // Páginas y fragmentos: primero la red; sin señal, lo último guardado.
  // «no-cache» obliga a preguntar al servidor si el archivo cambió (responde «sin cambios» si no):
  // sin esto el navegador puede servir un JavaScript viejo de su propia memoria.
  e.respondWith(
    fetch(pedido, url.pathname.startsWith(E) ? { cache: 'no-cache' } : undefined).then((r) => {
      const guardar = pedido.mode === 'navigate' || url.pathname.startsWith(E);
      if (r.ok && guardar) { const copia = r.clone(); caches.open(VERSION).then((c) => c.put(url.pathname, copia)); }
      return r;
    }).catch(() => caches.match(pedido).then((r) => r || caches.match(url.pathname, { ignoreSearch: true })).then((r) => r || new Response('', { status: 503 }))),
  );
});

// Las capas de /mapas llevan versión en la dirección. Al guardar una versión nueva de un
// archivo se quitan del teléfono las versiones anteriores de ese mismo archivo.
async function podar(cache, url) {
  for (const k of await cache.keys()) {
    const u = new URL(k.url);
    if (u.pathname === url.pathname && u.search !== url.search) cache.delete(k);
  }
}

async function trozo(pedido) {
  const cache = await caches.open(VERSION);
  const clave = new URL(pedido.url).pathname;
  let entero = await cache.match(clave);
  if (!entero) {
    try {
      const r = await fetch(clave);
      if (!r.ok) return fetch(pedido);
      await cache.put(clave, r.clone());
      entero = r;
    } catch (err) { return fetch(pedido); }
  }
  const rango = /bytes=(\d+)-(\d*)/.exec(pedido.headers.get('Range') || '');
  if (!rango) return entero;
  const datos = await entero.arrayBuffer();
  const desde = Number(rango[1]);
  const hasta = rango[2] ? Math.min(Number(rango[2]), datos.byteLength - 1) : datos.byteLength - 1;
  return new Response(datos.slice(desde, hasta + 1), {
    status: 206,
    headers: { 'Content-Range': `bytes ${desde}-${hasta}/${datos.byteLength}`, 'Content-Length': String(hasta - desde + 1), 'Content-Type': 'application/octet-stream' },
  });
}

// ── Avisos (Web Push) ───────────────────────────────────────────────────────
// Llegan aunque la app esté cerrada. Solo traen lo que ya es público en el mapa.
self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { cuerpo: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.titulo || 'SOS Galápagos', {
    body: d.cuerpo || 'Hay un aviso nuevo en el mapa de riesgos.',
    icon: E + 'app/icono-192.png', badge: E + 'app/icono-192.png',
    tag: d.etiqueta || undefined, data: { enlace: d.enlace || '/riesgos/' },
  }));
});
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const enlace = (e.notification.data && e.notification.data.enlace) || '/riesgos/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((ventanas) => {
    const abierta = ventanas.find((v) => new URL(v.url).pathname.startsWith('/riesgos/'));
    if (abierta) { abierta.navigate(enlace); return abierta.focus(); }
    return self.clients.openWindow(enlace);
  }));
});
