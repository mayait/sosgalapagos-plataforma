/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE). */
/* Página «Descargar capas»: la misma lista que publica /mapas (capas.json y descargas.json),
   capa por capa, con sus enlaces en Shapefile y GeoJSON. No hay lista propia: una capa nueva
   que publique el repo de datos aparece aquí sola. */
(function () {
  'use strict';
  const SOS = window.SOS, cfg = SOS.cfg, x = SOS.escapar, base = cfg.capasUrl;
  const caja = document.getElementById('descargas');

  async function iniciar() {
    const { v, fecha } = await SOS.versionDeMapas();
    const [manifiesto, indice] = await Promise.all([
      fetch(base + 'capas.json', { cache: 'no-cache' }).then((r) => r.json()),
      fetch(base + 'descargas.json' + v, { cache: 'no-cache' }).then((r) => r.json()),
    ]);
    const variante = (indice.variantes || {})[cfg.capasVariante] || { archivos: {} };
    const enlace = (a, texto) => `<a href="${x(base + a.url + v)}" download>↓ ${x(texto)} <i>${x(a.tam || '')}</i></a>`;
    let h = '';
    if (fecha && !Number.isNaN(Date.parse(fecha))) {
      const cuando = new Date(fecha).toLocaleString('es-EC', { timeZone: 'Pacific/Galapagos', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
      h += `<p class="capas-version">Capas y modelos actualizados: <b>${x(cuando)} (hora de Galápagos)</b></p>`;
    }
    if (variante.todo) {
      h += `<div class="descarga-todo"><b>Todas las capas en un solo archivo</b><span class="capa-descargas todo">${enlace(variante.todo.shp, 'Shapefile')}${enlace(variante.todo.geojson, 'GeoJSON')}</span></div>`;
    }
    const vistos = new Set(); // una capa puede salir en dos grupos con el mismo archivo
    for (const g of manifiesto.grupos) {
      let filas = '';
      for (const c of g.capas) {
        const clave = c.archivo || (c.teselas ? 'teselas:' + c.teselas : 'raster:' + c.raster);
        const a = variante.archivos[clave];
        if (!a || vistos.has(clave)) continue;
        vistos.add(clave);
        filas += `<li><span class="descarga-nombre">${x(a.titulo || c.titulo)}<small>${x(c.fuente || '')}${a.elementos ? ' · ' + a.elementos.toLocaleString('es') + ' elementos' : ''}</small></span>
          <span class="capa-descargas todo">${a.shp ? enlace(a.shp, a.shp.formato || 'Shapefile') : ''}${a.geojson ? enlace(a.geojson, 'GeoJSON') : ''}${a.extra ? `<a href="${x(a.extra.url)}" target="_blank" rel="noopener">↓ ${x(a.extra.texto)}</a>` : ''}</span></li>`;
      }
      if (filas) h += `<h2 class="seccion-titulo descarga-grupo">${x(g.titulo)}</h2><ul class="lista descargas">${filas}</ul>`;
    }
    caja.innerHTML = h || '<p class="vacio">No hay capas publicadas en este momento.</p>';
    caja.removeAttribute('aria-busy');
  }
  iniciar().catch(() => { caja.innerHTML = '<p class="vacio">No se pudo cargar la lista de capas. Vuelve a intentarlo en un momento.</p>'; });
})();
