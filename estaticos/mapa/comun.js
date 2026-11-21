/* Utilidades compartidas: configuración, CSRF y cola de reportes sin señal. */
(function () {
  'use strict';
  const nodo = document.getElementById('configuracion');
  const SOS = (window.SOS = { cfg: nodo ? JSON.parse(nodo.textContent) : {} });

  SOS.galleta = (nombre) => {
    const m = document.cookie.match(new RegExp('(?:^|; )' + nombre + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : '';
  };
  SOS.esMovil = () => window.matchMedia('(max-width: 1023px)').matches;
  SOS.escapar = (v) =>
    String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  // HTMX manda el token CSRF en cada petición. Se lee de la cookie en el momento,
  // para que sirva también en páginas guardadas por el service worker.
  document.addEventListener('htmx:configRequest', (e) => {
    e.detail.headers['X-CSRFToken'] = SOS.galleta('csrftoken');
  });

  // ── Cola de reportes sin señal (IndexedDB) ────────────────────────────────
  const BD = 'sos-cola';
  function abrir() {
    return new Promise((ok, mal) => {
      const p = indexedDB.open(BD, 1);
      p.onupgradeneeded = () => p.result.createObjectStore('reportes', { autoIncrement: true });
      p.onsuccess = () => ok(p.result);
      p.onerror = () => mal(p.error);
    });
  }
  function operar(modo, fn) {
    return abrir().then(
      (bd) =>
        new Promise((ok, mal) => {
          const t = bd.transaction('reportes', modo);
          const r = fn(t.objectStore('reportes'));
          t.oncomplete = () => ok(r && r.result);
          t.onerror = () => mal(t.error);
        }),
    );
  }
  SOS.cola = {
    guardar: (campos) => operar('readwrite', (s) => s.add(campos)),
    contar: () => operar('readonly', (s) => s.count()).catch(() => 0),
    async enviarPendientes() {
      const pendientes = await operar('readonly', (s) => {
        const lista = [];
        const c = s.openCursor();
        c.onsuccess = () => {
          if (c.result) { lista.push([c.result.key, c.result.value]); c.result.continue(); }
        };
        return { get result() { return lista; } };
      }).catch(() => []);
      let enviados = 0;
      for (const [clave, campos] of pendientes) {
        try {
          const r = await SOS.enviarReporte(campos);
          // Si el servidor lo rechaza por los datos, no tiene sentido reintentar.
          if (r.ok || (r.status >= 400 && r.status < 500 && r.status !== 429)) {
            await operar('readwrite', (s) => s.delete(clave));
            if (r.ok) enviados++;
          }
        } catch (e) { break; } // sigue sin señal
      }
      return enviados;
    },
  };

  SOS.enviarReporte = (campos) => {
    const cuerpo = new FormData();
    for (const [k, v] of Object.entries(campos)) {
      if (v == null || v === '') continue;
      if (v instanceof Blob) cuerpo.append(k, v, 'foto.jpg'); else cuerpo.append(k, v);
    }
    return fetch(SOS.cfg.reportar || '/mapa/reportar/', {
      method: 'POST', body: cuerpo, headers: { 'X-CSRFToken': SOS.galleta('csrftoken') },
    });
  };

  window.addEventListener('online', () => SOS.cola.enviarPendientes());
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/mapa/sw.js', { scope: '/mapa/' }).catch(() => {});
      SOS.cola.enviarPendientes();
    });
  }
})();
