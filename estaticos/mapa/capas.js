/* Panel «Capas» y dibujo de las capas de riesgo.

   Lee el manifiesto capas.json que genera el repo sosgalapagos-datos. Ese
   manifiesto describe los estilos con opciones de Leaflet (color, weight,
   fillOpacity, dashArray…); aquí se traducen a capas de MapLibre.
   Cada capa se descarga solo al encenderla y se dibuja debajo de los pines. */
(function () {
  'use strict';
  const SOS = window.SOS;
  const ZOOM_ROTULOS = 15; // los rótulos de barrios y calles solo se ven de cerca

  const estado = { mapa: null, manifiesto: null, capas: [], encendidas: new Set(), puestas: {}, base: 'gris', limites: null };
  const texto = (v) => ['to-string', ['get', v]];

  // Expresión que elige un valor del estilo según la clase del elemento.
  function porClase(capa, clave, defecto) {
    const c = capa.clasificar;
    const base = (capa.estilo && capa.estilo[clave]) ?? defecto;
    if (!c) return base;
    const pares = [];
    for (const [valor, estilo] of Object.entries(c.valores)) {
      if (estilo[clave] != null) pares.push(valor, estilo[clave]);
    }
    return pares.length ? ['match', texto(c.propiedad), ...pares, base] : base;
  }
  const trazo = (d) => (d ? d.split(/[ ,]+/).map(Number) : null);

  function filtroDe(capa) {
    const f = capa.filtro;
    return f ? ['in', ['get', f.propiedad], ['literal', f.en]] : null;
  }

  // Rayado diagonal para los polígonos con «patron» (el Parque Nacional).
  function ponerRayado(mapa, p) {
    if (mapa.hasImage(p.id)) return;
    const n = Math.max(8, Math.round(p.separacion * 2));
    const lienzo = document.createElement('canvas');
    lienzo.width = lienzo.height = n;
    const g = lienzo.getContext('2d');
    g.globalAlpha = p.opacidad_fondo ?? 0.3;
    g.fillStyle = p.fondo || '#ffffff';
    g.fillRect(0, 0, n, n);
    g.globalAlpha = p.opacidad ?? 0.6;
    g.strokeStyle = p.color;
    g.lineWidth = p.grosor * 1.4;
    for (const d of [-n, 0, n]) {
      g.beginPath(); g.moveTo(d, n); g.lineTo(d + n, 0); g.stroke();
    }
    mapa.addImage(p.id, g.getImageData(0, 0, n, n), { pixelRatio: 2 });
  }

  // Devuelve las capas de MapLibre que dibujan una capa del manifiesto.
  function construir(capa) {
    const mapa = estado.mapa;
    const fuente = 'capa-' + capa.id;
    const minzoom = capa.zoom_min || 0;
    const filtro = filtroDe(capa);
    const lista = [];
    const agregar = (def) => {
      def.source = fuente; def.minzoom = def.minzoom ?? minzoom;
      if (filtro && !def.filter) def.filter = filtro;
      lista.push(def);
    };

    if (capa.tipo === 'raster') return construirRaster(capa);

    if (!mapa.getSource(fuente)) {
      mapa.addSource(fuente, { type: 'geojson', data: SOS.cfg.capasUrl + capa.archivo, tolerance: 0.5 });
    }
    const e = capa.estilo || {};

    if (capa.tipo === 'poligono') {
      if (capa.patron) {
        ponerRayado(mapa, capa.patron);
        agregar({ id: fuente + '-relleno', type: 'fill', paint: { 'fill-pattern': capa.patron.id } });
      } else if ((e.fillOpacity ?? 0.2) > 0 || capa.clasificar) {
        agregar({
          id: fuente + '-relleno', type: 'fill',
          paint: {
            'fill-color': porClase(capa, 'fillColor', e.color || '#3388ff'),
            'fill-opacity': porClase(capa, 'fillOpacity', 0.2),
          },
        });
      }
      if ((e.weight ?? 1) > 0) {
        const pintura = { 'line-color': porClase(capa, 'color', '#3388ff'), 'line-width': porClase(capa, 'weight', 1.5), 'line-opacity': e.opacity ?? 1 };
        if (e.dashArray) pintura['line-dasharray'] = trazo(e.dashArray);
        agregar({ id: fuente + '-borde', type: 'line', paint: pintura });
      }
    }

    if (capa.tipo === 'linea') {
      const forma = { 'line-cap': 'round', 'line-join': 'round' };
      if (capa.borde) {
        agregar({ id: fuente + '-halo', type: 'line', layout: forma, paint: { 'line-color': capa.borde.color, 'line-width': capa.borde.weight, 'line-opacity': capa.borde.opacity ?? 1 } });
      }
      // MapLibre no admite trazo discontinuo por elemento: las clases con trazo van en su propia capa.
      const conTrazo = capa.clasificar ? Object.entries(capa.clasificar.valores).filter(([, v]) => v.dashArray) : [];
      const pintura = { 'line-color': porClase(capa, 'color', '#3388ff'), 'line-width': porClase(capa, 'weight', 2), 'line-opacity': porClase(capa, 'opacity', 1) };
      if (e.dashArray) pintura['line-dasharray'] = trazo(e.dashArray);
      const solidas = { id: fuente + '-linea', type: 'line', layout: e.dashArray ? {} : forma, paint: pintura };
      if (conTrazo.length) {
        const valores = conTrazo.map(([v]) => v);
        const prop = texto(capa.clasificar.propiedad);
        solidas.filter = ['!', ['in', prop, ['literal', valores]]];
        agregar(solidas);
        for (const [valor, v] of conTrazo) {
          agregar({
            id: fuente + '-linea-' + valor.replace(/\W+/g, '_'), type: 'line', filter: ['==', prop, valor],
            paint: { 'line-color': v.color || e.color || '#3388ff', 'line-width': v.weight || e.weight || 2, 'line-opacity': v.opacity ?? e.opacity ?? 1, 'line-dasharray': trazo(v.dashArray) },
          });
        }
      } else agregar(solidas);
    }

    if (capa.tipo === 'punto' && !capa.solo_rotulo) {
      agregar({
        id: fuente + '-punto', type: 'circle',
        paint: { 'circle-radius': e.radius || 6, 'circle-color': porClase(capa, 'fillColor', '#3388ff'), 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5 },
      });
      const simbolos = capa.clasificar ? Object.entries(capa.clasificar.valores).filter(([, v]) => v.simbolo) : [];
      if (simbolos.length) {
        agregar({
          id: fuente + '-simbolo', type: 'symbol',
          layout: { 'text-field': ['match', texto(capa.clasificar.propiedad), ...simbolos.flatMap(([k, v]) => [k, v.simbolo]), ''], 'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-allow-overlap': true },
          paint: { 'text-color': '#ffffff' },
        });
      }
    }

    if (capa.rotulo) {
      const r = capa.rotulo;
      const campo = r.sufijo ? ['concat', texto(r.propiedad), r.sufijo] : texto(r.propiedad);
      const enLinea = capa.tipo === 'linea';
      const def = {
        id: fuente + '-rotulo', type: 'symbol', minzoom: Math.max(minzoom, r.zoom_min || ZOOM_ROTULOS),
        filter: ['has', r.propiedad],
        layout: { 'text-field': campo, 'text-font': [enLinea ? 'Noto Sans Regular' : 'Noto Sans Medium'], 'text-size': enLinea ? 10.5 : 11.5, 'symbol-placement': enLinea ? 'line' : 'point', 'text-max-width': 7 },
        paint: { 'text-color': enLinea ? '#374151' : '#7c2d12', 'text-halo-color': '#ffffff', 'text-halo-width': 1.6 },
      };
      if (filtro) def.filter = ['all', filtro, ['has', r.propiedad]];
      agregar(def);
    }
    return lista;
  }

  // Relieve y pendientes: una imagen por isla, con los límites de raster/limites.json.
  function construirRaster(capa) {
    const lista = [];
    for (const [clave, isla] of Object.entries(estado.limites || {})) {
      const id = `capa-${capa.id}-${clave}`;
      const [[s, o], [n, e]] = isla.bounds;
      if (!estado.mapa.getSource(id)) {
        estado.mapa.addSource(id, {
          type: 'image', url: `${SOS.cfg.capasUrl}raster/${clave}_${capa.raster}.png`,
          coordinates: [[o, n], [e, n], [e, s], [o, s]],
        });
      }
      lista.push({ id, type: 'raster', source: id, paint: { 'raster-opacity': capa.opacidad ?? 0.6, 'raster-fade-duration': 0 } });
    }
    return lista;
  }

  // Conserva el apilado del manifiesto: una capa va debajo de la siguiente que ya esté puesta.
  function siguientePuesta(id) {
    const i = estado.capas.findIndex((c) => c.id === id);
    for (const c of estado.capas.slice(i + 1)) {
      const puestas = estado.puestas[c.id];
      if (puestas && puestas.length) return puestas[0];
    }
    return 'ancla-capas';
  }

  async function encender(capa) {
    if (capa.tipo === 'raster' && !estado.limites) {
      estado.limites = await fetch(SOS.cfg.capasUrl + 'raster/limites.json').then((r) => r.json()).catch(() => ({}));
    }
    const antes = siguientePuesta(capa.id);
    const ids = [];
    for (const def of construir(capa)) {
      if (!estado.mapa.getLayer(def.id)) estado.mapa.addLayer(def, antes);
      ids.push(def.id);
    }
    estado.puestas[capa.id] = ids;
  }

  function apagar(capa) {
    for (const id of estado.puestas[capa.id] || []) if (estado.mapa.getLayer(id)) estado.mapa.removeLayer(id);
    estado.puestas[capa.id] = [];
  }

  function alternar(id) {
    const capa = estado.capas.find((c) => c.id === id);
    if (estado.encendidas.has(id)) { estado.encendidas.delete(id); apagar(capa); } else { estado.encendidas.add(id); encender(capa); }
    pintar();
  }

  // ── Leyendas ──────────────────────────────────────────────────────────────
  function leyenda(capa) {
    if (capa.leyenda) return capa.leyenda.map(([color, t]) => ({ forma: 'cuadro', color, texto: t }));
    if (!capa.clasificar) return [];
    const e = capa.estilo || {};
    return Object.values(capa.clasificar.valores).map((v) => ({
      forma: capa.tipo === 'punto' ? 'punto' : capa.tipo === 'linea' ? 'linea' : 'cuadro',
      color: v.fillColor || v.color || e.fillColor || e.color || '#888',
      simbolo: v.simbolo, discontinua: Boolean(v.dashArray), texto: v.etiqueta,
    }));
  }
  function muestra(l) {
    const c = SOS.escapar(l.color);
    if (l.forma === 'punto') return `<i class="muestra punto" style="background:${c}">${SOS.escapar(l.simbolo || '')}</i>`;
    if (l.forma === 'linea') return `<i class="muestra linea" style="border-top-color:${c};border-top-style:${l.discontinua ? 'dashed' : 'solid'}"></i>`;
    return `<i class="muestra cuadro" style="background:${c}"></i>`;
  }

  // ── Panel ─────────────────────────────────────────────────────────────────
  function pintar() {
    const m = estado.manifiesto;
    const zoom = estado.mapa.getZoom();
    const x = SOS.escapar;
    let h = '<div class="capas-titulo">Ir a</div><div class="pildoras">';
    for (const nombre of Object.keys(m.islas || {})) h += `<button type="button" data-ir="${x(nombre)}">${x(nombre)}</button>`;
    h += '</div><div class="capas-titulo">Mapa base</div><div class="selector">';
    h += `<button type="button" data-base="gris" aria-pressed="${estado.base === 'gris'}">Gris</button>`;
    for (const b of m.mapas_base || []) {
      if (b.id === 'claro') continue; // la base gris propia ocupa su lugar
      h += `<button type="button" data-base="${x(b.id)}" aria-pressed="${estado.base === b.id}">${x(b.titulo)}</button>`;
    }
    h += '</div>';
    for (const g of m.grupos) {
      h += `<div class="capas-grupo"><div class="capas-titulo">${x(g.titulo)}</div>`;
      for (const c of g.capas) {
        const on = estado.encendidas.has(c.id);
        h += `<div class="capa"><button type="button" class="capa-interruptor" role="switch" aria-checked="${on}" data-capa="${x(c.id)}">
          <span class="interruptor"></span><span class="capa-nombre">${x(c.titulo)}${c.fuente ? `<span class="capa-fuente">${x(c.fuente)}</span>` : ''}</span></button>`;
        if (on) {
          h += '<div class="capa-detalle">';
          if (c.zoom_min && zoom < c.zoom_min) h += '<span class="capa-lejos">Acércate para verla.</span>';
          if (c.descripcion) h += `<em>${x(c.descripcion)}</em>`;
          for (const l of leyenda(c)) h += `<span>${muestra(l)}${x(l.texto)}</span>`;
          h += '</div>';
        }
        h += '</div>';
      }
      h += '</div>';
    }
    document.getElementById('capas-cuerpo').innerHTML = h;
  }

  function alHacerClic(e) {
    const b = e.target.closest('button');
    if (!b) return;
    const m = estado.manifiesto;
    if (b.dataset.capa) return alternar(b.dataset.capa);
    if (b.dataset.ir) {
      const [[s, o], [n, este]] = m.islas[b.dataset.ir].bounds;
      estado.mapa.fitBounds([[o, s], [este, n]], { padding: 30, duration: 600 });
      if (SOS.esMovil()) cerrar();
    }
    if (b.dataset.base) {
      estado.base = b.dataset.base;
      SOS.ponerBase(estado.mapa, (m.mapas_base || []).find((x) => x.id === estado.base));
      pintar();
    }
  }

  // Globo con los datos del elemento al tocar una capa.
  function globo(e) {
    const ids = Object.values(estado.puestas).flat().filter((id) => estado.mapa.getLayer(id) && !id.endsWith('-halo') && !id.endsWith('-rotulo'));
    if (!ids.length) return false;
    const f = estado.mapa.queryRenderedFeatures(e.point, { layers: ids })[0];
    if (!f) return false;
    const capa = estado.capas.find((c) => f.layer.source === 'capa-' + c.id);
    if (!capa || !capa.popup) return false;
    const p = capa.popup, x = SOS.escapar, datos = f.properties;
    const titulo = (datos[p.titulo] ?? p.titulo_defecto ?? capa.titulo) + (datos[p.titulo] != null ? p.sufijo_titulo || '' : '');
    let h = `<div class="globo-titulo">${x(titulo)}</div><table class="globo-tabla">`;
    for (const [campo, etiqueta] of Object.entries(p.campos || {})) {
      if (datos[campo] != null && datos[campo] !== '') h += `<tr><td>${x(etiqueta)}</td><td>${x(datos[campo])}</td></tr>`;
    }
    new maplibregl.Popup({ maxWidth: '260px' }).setLngLat(e.lngLat).setHTML(h + '</table>').addTo(estado.mapa);
    return true;
  }

  const panel = () => document.getElementById('capas-panel');
  function abrir() { panel().hidden = false; document.getElementById('capas-abrir').hidden = true; pintar(); }
  function cerrar() { panel().hidden = true; document.getElementById('capas-abrir').hidden = false; }

  SOS.capas = {
    globo,
    async iniciar(mapa) {
      estado.mapa = mapa;
      document.getElementById('capas-abrir').addEventListener('click', abrir);
      document.getElementById('capas-cerrar').addEventListener('click', cerrar);
      document.getElementById('capas-cuerpo').addEventListener('click', alHacerClic);
      let m;
      try {
        m = await fetch(SOS.cfg.capasUrl + 'capas.json').then((r) => r.json());
      } catch (e) {
        document.getElementById('capas-abrir').hidden = true; // sin manifiesto no hay panel
        return;
      }
      estado.manifiesto = m;
      estado.capas = m.grupos.flatMap((g) => g.capas);
      // En el teléfono arrancan menos capas: pesan y tapan los reportes.
      const iniciales = SOS.esMovil() ? SOS.cfg.capasEncendidasMovil : SOS.cfg.capasEncendidas;
      for (const capa of estado.capas) {
        if (iniciales.includes(capa.id)) { estado.encendidas.add(capa.id); await encender(capa); }
      }
      let anterior = Math.floor(mapa.getZoom());
      mapa.on('zoomend', () => {
        const z = Math.floor(mapa.getZoom());
        if (z !== anterior && !panel().hidden) pintar();
        anterior = z;
      });
    },
  };
})();
