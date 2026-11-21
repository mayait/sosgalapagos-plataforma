/* Panel «Capas» y dibujo de las capas de riesgo.

   Mantiene los principios de /mapas: toda capa se puede encender, apagar y
   descargar. Para eso lee lo mismo que publica /mapas (repo sosgalapagos-datos):
     capas.json      grupos, capas, estilos y leyendas
     descargas.json  enlaces en Shapefile y GeoJSON de cada capa
   El manifiesto describe los estilos con opciones de Leaflet (color, weight,
   fillOpacity, dashArray…); aquí se traducen a capas de MapLibre.
   Cada capa se baja solo al encenderla y se dibuja debajo de los pines. */
(function () {
  'use strict';
  const SOS = window.SOS;
  const ZOOM_ROTULOS = 15; // los rótulos de barrios y calles solo se ven de cerca

  const estado = { mapa: null, manifiesto: null, descargas: {}, todo: null, capas: [], orden: [], encendidas: new Set(), iniciales: [], puestas: {}, base: 'gris', limites: null, teselas: {} };
  const GUARDADO = 'sos-capas-3';
  const BASE_GUARDADA = 'sos-base'; // lo que la persona dejó encendido se recuerda en su teléfono
  const datosUrl = () => `${SOS.cfg.capasUrl}datos/${SOS.cfg.capasVariante}/`;
  const recordar = () => { try { localStorage.setItem(GUARDADO, JSON.stringify([...estado.encendidas])); } catch (e) { /* sin espacio */ } };
  const texto = (v) => ['to-string', ['get', v]];

  // Expresión que elige un valor del estilo según la clase del elemento.
  function porClase(capa, clave, defecto) {
    const c = capa.clasificar;
    let base = (capa.estilo && capa.estilo[clave]) ?? defecto;
    if (!c) return base;
    if (c.otro && c.otro[clave] != null) base = c.otro[clave]; // clase para lo que no entra en ninguna
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

  // ── Marcadores de los reportes de campo ───────────────────────────────────
  // Las capas con «marcador: reporte» (los reportes ciudadanos que publica /mapas) no se
  // dibujan como círculos: llevan un cuadrado redondeado con un iconito. Así no se confunden
  // con los pines de los reportes nuevos, que son redondos.
  //   cámara = trae fotos · casa = refugio · signo de admiración = aviso sin foto
  const GLIFOS = {
    foto: (color) => `<path d="M4.5 9.2h3l1.5-2.2h6l1.5 2.2h3v8.6h-15z" fill="#ffffff" stroke="none"/><circle cx="12" cy="13.3" r="2.7" fill="${color}" stroke="none"/>`,
    refugio: () => '<path d="M4.5 12L12 6l7.5 6"/><path d="M7 10.5V18h10v-7.5"/>',
    aviso: () => '<path d="M12 6.5v7" stroke-width="2.6"/><path d="M12 17.2v.3" stroke-width="2.6"/>',
  };
  function clasesDe(capa) {
    const c = capa.clasificar || { valores: {} };
    const lista = Object.entries(c.valores).map(([valor, v]) => [valor, v.fillColor || '#888888']);
    lista.push(['otro', (c.otro && c.otro.fillColor) || (capa.estilo && capa.estilo.fillColor) || '#888888']);
    return lista;
  }
  function prepararMarcadores(capa) {
    const tareas = [];
    for (const [valor, color] of clasesDe(capa)) {
      for (const [glifo, trazo] of Object.entries(GLIFOS)) {
        const nombre = `marc-${capa.id}-${valor}-${glifo}`;
        if (estado.mapa.hasImage(nombre)) continue;
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 28 28">
          <rect x="2" y="2" width="24" height="24" rx="7" fill="${color}" stroke="#ffffff" stroke-width="2.4"/>
          <g transform="translate(2 2)" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${trazo(color)}</g></svg>`;
        tareas.push(new Promise((listo) => {
          const img = new Image(56, 56);
          img.onload = () => { if (!estado.mapa.hasImage(nombre)) estado.mapa.addImage(nombre, img, { pixelRatio: 2 }); listo(); };
          img.onerror = listo;
          img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
        }));
      }
    }
    return Promise.all(tareas);
  }
  function capaDeMarcadores(capa, fuente) {
    const c = capa.clasificar;
    const valores = c ? Object.keys(c.valores) : [];
    const clase = c ? ['match', texto(c.propiedad), valores, texto(c.propiedad), 'otro'] : 'otro';
    const conFotos = ['all', ['has', 'fotos'], ['>', ['length', ['get', 'fotos']], 0]];
    const glifo = ['case', ['==', ['get', 'tipo'], 'refugio'], 'refugio', conFotos, 'foto', 'aviso'];
    return {
      id: fuente + '-marcador', type: 'symbol',
      layout: { 'icon-image': ['concat', `marc-${capa.id}-`, clase, '-', glifo], 'icon-size': ['interpolate', ['linear'], ['zoom'], 12, 0.7, 16, 1], 'icon-allow-overlap': true, 'icon-ignore-placement': true },
    };
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
    if (capa.tipo === 'teselas') return construirTeselas(capa);

    if (!mapa.getSource(fuente)) {
      mapa.addSource(fuente, { type: 'geojson', data: datosUrl() + capa.archivo, tolerance: 0.5 });
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

    if (capa.tipo === 'punto' && capa.marcador === 'reporte') {
      agregar(capaDeMarcadores(capa, fuente));
    } else if (capa.tipo === 'punto' && !capa.solo_rotulo) {
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
          type: 'image', url: `${datosUrl()}raster/${clave}_${capa.raster}.png`,
          coordinates: [[o, n], [e, n], [e, s], [o, s]],
        });
      }
      lista.push({ id, type: 'raster', source: id, paint: { 'raster-opacity': capa.opacidad ?? 0.6, 'raster-fade-duration': 0 } });
    }
    return lista;
  }

  // Teselas de imagen (el relieve del DTM de 1 m): su descripción está en teselas.json.
  function construirTeselas(capa) {
    const t = estado.teselas[capa.teselas];
    if (!t) return [];
    const id = 'capa-' + capa.id;
    const [[s, o], [n, e]] = t.limites;
    if (!estado.mapa.getSource(id)) {
      estado.mapa.addSource(id, {
        type: 'raster', tiles: [`${location.origin}${SOS.cfg.capasUrl}teselas/${capa.teselas}/${t.relieve.url}`], tileSize: 256,
        minzoom: t.relieve.zoom_min, maxzoom: t.relieve.zoom_max, bounds: [o, s, e, n], attribution: t.atribucion,
      });
    }
    return [{ id, type: 'raster', source: id, paint: { 'raster-opacity': capa.opacidad ?? 0.85, 'raster-fade-duration': 0 } }];
  }

  // Apilado: abajo las imágenes y los polígonos, luego las líneas y arriba los puntos, para que
  // un punto (un reporte con fotos) nunca quede tapado por un área. Dentro de cada tipo manda
  // el orden del manifiesto. Una capa va debajo de la siguiente que ya esté puesta.
  function siguientePuesta(id) {
    const i = estado.orden.findIndex((c) => c.id === id);
    for (const c of estado.orden.slice(i + 1)) {
      const puestas = estado.puestas[c.id];
      if (puestas && puestas.length) return puestas[0];
    }
    return 'ancla-capas';
  }

  async function encender(capa) {
    if (capa.tipo === 'raster' && !estado.limites) {
      estado.limites = await fetch(datosUrl() + 'raster/limites.json').then((r) => r.json()).catch(() => ({}));
    }
    if (capa.tipo === 'teselas' && !estado.teselas[capa.teselas]) {
      estado.teselas[capa.teselas] = await fetch(`${SOS.cfg.capasUrl}teselas/${capa.teselas}/teselas.json`).then((r) => r.json()).catch(() => null);
    }
    if (capa.marcador === 'reporte') await prepararMarcadores(capa);
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
    recordar();
    pintar();
  }

  // Deja encendidas exactamente las capas de la lista, en el orden del manifiesto.
  async function dejarEncendidas(ids) {
    for (const capa of estado.orden) {
      const debe = ids.includes(capa.id), esta = estado.encendidas.has(capa.id);
      if (esta && !debe) { estado.encendidas.delete(capa.id); apagar(capa); }
      if (!esta && debe) { estado.encendidas.add(capa.id); await encender(capa); }
    }
    recordar();
    pintar();
  }

  // Enlaces de descarga de una capa, tomados del índice que publica /mapas.
  function descargasDe(capa) {
    const clave = capa.archivo ?? (capa.teselas ? 'teselas:' + capa.teselas : 'raster:' + capa.raster);
    const a = estado.descargas[clave];
    if (!a) return '';
    const x = SOS.escapar, u = SOS.cfg.capasUrl;
    let h = '<span class="capa-descargas">';
    if (a.shp) h += `<a href="${x(u + a.shp.url)}" download>↓ ${x(a.shp.formato || 'Shapefile')} <i>${x(a.shp.tam)}</i></a>`;
    if (a.geojson) h += `<a href="${x(u + a.geojson.url)}" download="${x(capa.archivo || '')}">↓ GeoJSON <i>${x(a.geojson.tam)}</i></a>`;
    if (a.extra) h += `<a href="${x(a.extra.url)}" target="_blank" rel="noopener">↓ ${x(a.extra.texto)}</a>`;
    return h + '</span>';
  }
  function elementosDe(capa) {
    const a = estado.descargas[capa.archivo];
    return a && a.elementos ? ` · ${a.elementos.toLocaleString('es')} elementos` : '';
  }

  // ── Leyendas ──────────────────────────────────────────────────────────────
  function leyenda(capa) {
    if (capa.leyenda) return capa.leyenda.map(([color, t]) => ({ forma: 'cuadro', color, texto: t }));
    if (!capa.clasificar) return [];
    const e = capa.estilo || {};
    const clases = Object.values(capa.clasificar.valores).concat(capa.clasificar.otro ? [capa.clasificar.otro] : []);
    return clases.map((v) => ({
      forma: capa.marcador === 'reporte' ? 'marcador' : capa.tipo === 'punto' ? 'punto' : capa.tipo === 'linea' ? 'linea' : 'cuadro',
      color: v.fillColor || v.color || e.fillColor || e.color || '#888',
      simbolo: v.simbolo, discontinua: Boolean(v.dashArray), texto: v.etiqueta,
    }));
  }
  function muestra(l) {
    const c = SOS.escapar(l.color);
    if (l.forma === 'marcador') return `<i class="muestra marcador" style="background:${c}"></i>`;
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
    h += `</div><div class="capas-acciones"><button type="button" data-accion="apagar">Apagar todas las capas</button><button type="button" data-accion="iniciales">Volver a las capas iniciales</button></div>`;
    for (const g of m.grupos) {
      const activas = g.capas.filter((c) => estado.encendidas.has(c.id)).length;
      h += `<div class="capas-grupo"><div class="capas-titulo">${x(g.titulo)}${activas ? `<span class="capas-activas">${activas} activa${activas > 1 ? 's' : ''}</span>` : ''}</div>`;
      if (g.descripcion) h += `<p class="capas-nota">${x(g.descripcion)}</p>`;
      if (g.enlace) h += `<p class="capas-nota"><a href="${x(g.enlace.url)}">${x(g.enlace.texto)} →</a></p>`;
      for (const c of g.capas) {
        const on = estado.encendidas.has(c.id);
        h += `<div class="capa"><button type="button" class="capa-interruptor" role="switch" aria-checked="${on}" data-capa="${x(c.id)}">
          <span class="interruptor"></span><span class="capa-nombre">${x(c.titulo)}<span class="capa-fuente">${x(c.fuente || '')}${elementosDe(c)}</span></span></button>${descargasDe(c)}`;
        if (on) {
          h += '<div class="capa-detalle">';
          if (c.zoom_min && zoom < c.zoom_min) h += '<span class="capa-lejos">Acércate para verla.</span>';
          if (c.descripcion) h += `<em>${x(c.descripcion)}</em>`;
          for (const l of leyenda(c)) h += `<span>${muestra(l)}${x(l.texto)}</span>`;
          if (c.marcador === 'reporte') h += '<span class="capa-glifos">Cámara: con fotos · Casa: refugio · Signo «!»: aviso sin foto</span>';
          h += '</div>';
        }
        h += '</div>';
      }
      h += '</div>';
    }
    if (estado.todo) {
      const u = SOS.cfg.capasUrl;
      h += `<div class="capas-grupo"><div class="capas-titulo">Descargar todas las capas</div><span class="capa-descargas todo">
        <a href="${x(u + estado.todo.shp.url)}" download>↓ Shapefile <i>${x(estado.todo.shp.tam)}</i></a>
        <a href="${x(u + estado.todo.geojson.url)}" download>↓ GeoJSON <i>${x(estado.todo.geojson.tam)}</i></a></span>
        <p class="capas-nota">Coordenadas WGS 84 (EPSG:4326). Cada archivo trae su fuente y su licencia. Los modelos son estimaciones propias, no datos oficiales. Visor completo en <a href="${x(u)}">/mapas</a>.</p></div>`;
    }
    const cuerpo = document.getElementById('capas-cuerpo'), altura = cuerpo.scrollTop;
    cuerpo.innerHTML = h;
    cuerpo.scrollTop = altura; // no saltar al principio al encender una capa
  }

  function alHacerClic(e) {
    const b = e.target.closest('button');
    if (!b) return;
    const m = estado.manifiesto;
    if (b.dataset.capa) return alternar(b.dataset.capa);
    if (b.dataset.accion === 'apagar') return dejarEncendidas([]);
    if (b.dataset.accion === 'iniciales') return dejarEncendidas(estado.iniciales);
    if (b.dataset.ir) {
      const [[s, o], [n, este]] = m.islas[b.dataset.ir].bounds;
      estado.mapa.fitBounds([[o, s], [este, n]], { padding: 30, duration: 600 });
      if (SOS.esMovil()) cerrar();
    }
    if (b.dataset.base) {
      estado.base = b.dataset.base;
      SOS.ponerBase(estado.mapa, (m.mapas_base || []).find((x) => x.id === estado.base));
      try { localStorage.setItem(BASE_GUARDADA, estado.base); } catch (err) { /* sin espacio */ }
      pintar();
    }
  }

  // Al tocar un elemento de una capa, sus datos se abren en la hoja o el panel.
  function globo(e) {
    const ids = Object.values(estado.puestas).flat().filter((id) => estado.mapa.getLayer(id) && !id.endsWith('-halo') && !id.endsWith('-rotulo'));
    if (!ids.length) return false;
    const f = estado.mapa.queryRenderedFeatures(e.point, { layers: ids })[0];
    if (!f) return false;
    const capa = estado.capas.find((c) => f.layer.source === 'capa-' + c.id);
    if (!capa || !capa.popup) return false;
    const p = capa.popup, datos = f.properties;
    let fotos = p.fotos ? datos[p.fotos] : null;
    if (typeof fotos === 'string') { try { fotos = JSON.parse(fotos); } catch (err) { fotos = null; } }
    // Todo se lee en la hoja (teléfono) o en el panel (escritorio), nunca en un globo:
    // un globo con texto largo se sale de la pantalla del teléfono.
    SOS.mostrarDetalle(fichaDeCapa(capa, datos, Array.isArray(fotos) ? fotos : []), f.geometry.type === 'Point' ? f.geometry.coordinates : null);
    return true;
  }

  // Ficha de un elemento de una capa, con sus fotos (rutas relativas a capa.fotos_base).
  function fichaDeCapa(capa, datos, fotos) {
    const p = capa.popup, x = SOS.escapar, base = datosUrl() + (capa.fotos_base || '');
    const titulo = (datos[p.titulo] ?? p.titulo_defecto ?? capa.titulo) + (datos[p.titulo] != null ? p.sufijo_titulo || '' : '');
    let h = `<article class="ficha"><button class="ficha-volver" type="button" data-cerrar-ficha>← Volver a la lista</button>
      <p class="ficha-capa">${x(capa.titulo)}</p><h2 class="ficha-titulo">${x(titulo)}</h2><ul class="ficha-datos">`;
    for (const [campo, etiqueta] of Object.entries(p.campos || {})) {
      if (datos[campo] != null && datos[campo] !== '') h += `<li><span>${x(etiqueta)}</span> ${x(datos[campo])}</li>`;
    }
    h += '</ul>';
    if (p.texto && datos[p.texto]) h += `<p class="ficha-texto">${x(datos[p.texto])}</p>`;
    if (fotos.length) {
      h += '<div class="fotos">';
      for (const f of fotos) {
        h += `<figure><a href="${x(base + f.archivo)}" target="_blank" rel="noopener"><img loading="lazy" src="${x(base + (f.mini || f.archivo))}" alt="${x(f.pie || 'Foto del reporte')}"></a>
          <figcaption>${f.hora && !(f.pie || '').startsWith(f.hora) ? `<b>${x(f.hora)}</b> ` : ''}${x(f.pie || '')}</figcaption></figure>`;
      }
      h += '</div>';
    }
    return h + `<p class="ficha-pie">${x(capa.fuente || '')}</p></article>`;
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
        const d = await fetch(SOS.cfg.capasUrl + 'descargas.json').then((r) => r.json()).catch(() => null);
        const variante = d && d.variantes && d.variantes[SOS.cfg.capasVariante];
        if (variante) { estado.descargas = variante.archivos || {}; estado.todo = variante.todo || null; }
      } catch (e) {
        document.getElementById('capas-abrir').hidden = true; // sin manifiesto no hay panel
        return;
      }
      estado.manifiesto = m;
      // Mapa base al abrir: el que la persona eligió la última vez o, si no, el de los ajustes
      // (satélite). Sin conexión se queda la base gris, que está guardada en el teléfono.
      let base = SOS.cfg.baseInicial || 'gris';
      try { base = localStorage.getItem(BASE_GUARDADA) || base; } catch (err) { /* sin acceso */ }
      const def = (m.mapas_base || []).find((x) => x.id === base);
      if (def && navigator.onLine !== false) { estado.base = base; SOS.ponerBase(mapa, def); }
      estado.capas = m.grupos.flatMap((g) => g.capas);
      const altura = { raster: 0, teselas: 0, poligono: 1, linea: 2, punto: 3 };
      estado.orden = estado.capas.map((c, i) => [c, i]).sort((a, b) => (altura[a[0].tipo] - altura[b[0].tipo]) || (a[1] - b[1])).map(([c]) => c);
      // Arrancan encendidas las capas que el manifiesto de /mapas marca como visibles.
      // En el teléfono se respetan las que /mapas apaga por pesadas, salvo el riesgo
      // modelado y las quebradas, que salen siempre.
      const movil = SOS.esMovil(), siempre = SOS.cfg.capasSiempreGrupos || [], apagadas = SOS.cfg.capasApagadasAlAbrir || [];
      estado.iniciales = m.grupos.flatMap((g) => g.capas
        .filter((c) => c.visible && !apagadas.includes(c.id) && (!movil || c.visible_movil !== false || siempre.includes(g.id)))
        .map((c) => c.id));
      // Si la persona ya eligió capas en una visita anterior, se respeta su elección.
      let elegidas = null;
      try { elegidas = JSON.parse(localStorage.getItem(GUARDADO)); } catch (e) { /* nada guardado */ }
      const arranque = Array.isArray(elegidas) ? elegidas : estado.iniciales;
      for (const capa of estado.orden) {
        if (arranque.includes(capa.id)) { estado.encendidas.add(capa.id); await encender(capa); }
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
