/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE). */
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

  // Versión de lo que publica /mapas (version.txt: «<commit> <fecha>»). Se pega a las
  // direcciones de capas y descargas para no mostrar archivos viejos. { v, fecha } o { v: '' }.
  SOS.versionDeMapas = async () => {
    try {
      const t = await fetch(SOS.cfg.capasUrl + 'version.txt', { cache: 'no-cache' }).then((r) => (r.ok ? r.text() : ''));
      const [commit, fecha] = t.trim().split(/\s+/);
      if (commit && fecha && !Number.isNaN(Date.parse(fecha))) return { v: `?v=${encodeURIComponent(commit)}-${Date.parse(fecha) / 1000}`, fecha };
    } catch (e) { /* sin versión */ }
    return { v: '', fecha: '' };
  };

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
    return fetch(SOS.cfg.reportar || '/riesgos/reportar/', {
      method: 'POST', body: cuerpo, headers: { 'X-CSRFToken': SOS.galleta('csrftoken') },
    });
  };

  window.addEventListener('online', () => SOS.cola.enviarPendientes());
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/riesgos/sw.js', { scope: '/riesgos/' }).catch(() => {});
      SOS.cola.enviarPendientes();
    });
  }
})();

/* Compartir un reporte: el menú del teléfono si existe; si no, copia el enlace y ofrece WhatsApp. */
document.addEventListener('click', async (e) => {
  const boton = e.target.closest('[data-compartir]');
  if (!boton) return;
  const url = new URL('/riesgos/?r=' + encodeURIComponent(boton.dataset.compartir), location.origin).href;
  const texto = boton.dataset.texto || boton.dataset.titulo || '';
  if (navigator.share) {
    try { await navigator.share({ title: boton.dataset.titulo, text: texto, url }); } catch (err) { /* la persona cerró el menú */ }
    return;
  }
  const aviso = boton.parentElement.querySelector('.ficha-compartido');
  try { await navigator.clipboard.writeText(url); } catch (err) { /* sin permiso: queda el enlace de WhatsApp */ }
  if (aviso) {
    aviso.querySelector('[data-whatsapp]').href = 'https://wa.me/?text=' + encodeURIComponent(texto + ' ' + url);
    aviso.hidden = false;
  }
});
