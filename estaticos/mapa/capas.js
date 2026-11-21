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
  const GUARDADO = 'sos-capas-4';
  const BASE_GUARDADA = 'sos-base'; // lo que la persona dejó encendido se recuerda en su teléfono
  const datosUrl = () => `${SOS.cfg.capasUrl}datos/${SOS.cfg.capasVariante}/`;
  // Otro equipo actualiza los modelos y las capas mientras el mapa está abierto. Cada
  // publicación de /mapas tiene una versión; se pega a todas las direcciones (?v=…) para que
  // el navegador nunca muestre un archivo viejo, y se vuelve a consultar cada dos minutos.
  const CONSULTA_MS = 120000;
  const conV = (u) => (estado.version ? `${u}${u.includes('?') ? '&' : '?'}v=${encodeURIComponent(estado.version.id)}` : u);
  // Se guarda lo encendido y también qué capas existían: así una capa nueva que el otro
  // equipo publique encendida aparece aunque la persona ya tuviera su elección guardada.
  const recordar = () => {
    try { localStorage.setItem(GUARDADO, JSON.stringify({ encendidas: [...estado.encendidas], conocidas: estado.capas.map((c) => c.id) })); } catch (e) { /* sin espacio */ }
  };
  const texto = (v) => ['to-string', ['get', v]];

  // Expresión que elige un valor del estilo según la clase del elemento.
  function porClase(capa, clave, defecto) {
    const c = capa.clasificar;
    let base = (capa.estilo && capa.estilo[clave]) ?? defecto;
    if (!c) return base;
    if (c.rangos) {
      // Rangos numéricos (p. ej. población por manzana): gana el primero cuyo tope alcanza al valor.
      if (!c.rangos.some((r) => r[clave] != null)) return base;
      const n = ['coalesce', ['to-number', ['get', c.propiedad], 0], 0];
      return ['case', ...c.rangos.flatMap((r) => [['<=', n, r.hasta], r[clave] ?? base]), base];
    }
    if (c.otro && c.otro[clave] != null) base = c.otro[clave]; // clase para lo que no entra en ninguna
    const pares = [];
    for (const [valor, estilo] of Object.entries(c.valores || {})) {
      if (estilo[clave] != null) pares.push(valor, estilo[clave]);
    }
    return pares.length ? ['match', texto(c.propiedad), ...pares, base] : base;
  }
  const trazo = (d) => (d ? d.split(/[ ,]+/).map(Number) : null);

  // Condición de una regla «estilo_si» del manifiesto (igual_a / distinto_de) como expresión.
  function condicionDe(regla) {
    return regla.igual_a !== undefined ? ['==', ['get', regla.propiedad], regla.igual_a] : ['!=', ['get', regla.propiedad], regla.distinto_de];
  }

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
  // Significan lo mismo que en /mapas, que los dibuja como gotas:
  //   cámara = trae fotos · triángulo = aviso sin foto · casa verde = refugio
  //   borde punteado oscuro = ubicación aproximada o por confirmar
  const VERDE_REFUGIO = '#16a34a';
  const GLIFOS = {
    foto: (color, tinta) => `<path d="M4.5 9.2h3l1.5-2.2h6l1.5 2.2h3v8.6h-15z" fill="${tinta}" stroke="none"/><circle cx="12" cy="13.3" r="2.7" fill="${color}" stroke="none"/>`,
    aviso: (color, tinta) => `<path d="M12 5.6l7 12.2H5z" fill="${tinta}" stroke="${tinta}" stroke-width="1.2" stroke-linejoin="round"/><rect x="11.2" y="9.8" width="1.6" height="4.2" fill="${color}" stroke="none"/><circle cx="12" cy="15.8" r="1" fill="${color}" stroke="none"/>`,
    refugio: (color, tinta) => `<path d="M4.5 12L12 6l7.5 6" stroke="${tinta}"/><path d="M7 10.5V18h10v-7.5" stroke="${tinta}"/>`,
    corazon: (color, tinta) => `<path d="M12 19s-7-4.3-7-9.6A4 4 0 0 1 12 7.2a4 4 0 0 1 7 2.2C19 14.7 12 19 12 19z" fill="${tinta}" stroke="none"/>`,
  };
  // Capas que /mapas dibuja con un marcador propio. Aquí todas van en cuadrado redondeado:
  //   reporte  = reportes ciudadanos, con cámara, triángulo o casa y el color de su gravedad
  //   corazon  = buenas noticias y ayuda, con un corazón y el color de la capa (rosa)
  const CON_MARCADOR = ['reporte', 'corazon'];
  const conMarcador = (capa) => CON_MARCADOR.includes(capa.marcador);
  const esAproximada = (capa) => ['case', ['in', ['coalesce', ['get', 'precision'], ''],
    ['literal', capa.marcador === 'corazon' ? ['aproximada', 'por_confirmar', 'barrio'] : ['aproximada', 'por_confirmar']]], '-aprox', ''];
  function clasesDe(capa) {
    const c = capa.clasificar || {};
    const lista = Object.entries(c.valores || {}).map(([valor, v]) => [valor, v.fillColor || '#888888']);
    lista.push(['otro', (c.otro && c.otro.fillColor) || (capa.estilo && capa.estilo.fillColor) || '#888888']);
    return lista;
  }
  function prepararMarcadores(capa) {
    const tareas = [];
    let variantes;
    if (capa.marcador === 'corazon') {
      variantes = [['unico', (capa.estilo && capa.estilo.fillColor) || '#db2777', 'corazon']];
    } else {
      variantes = clasesDe(capa).flatMap(([valor, color]) => ['foto', 'aviso'].map((g) => [valor, color, g]));
      variantes.push(['refugio', VERDE_REFUGIO, 'refugio']);
    }
    for (const [valor, color, glifo] of variantes) {
      for (const aprox of [false, true]) {
        const nombre = `marc-${capa.id}-${valor}-${glifo}${aprox ? '-aprox' : ''}`;
        if (estado.mapa.hasImage(nombre)) continue;
        const tinta = color.toLowerCase() === '#facc15' ? '#422006' : '#ffffff'; // sobre amarillo, tinta oscura
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 28 28">
          <rect x="2" y="2" width="24" height="24" rx="7" fill="${color}" stroke="#ffffff" stroke-width="2.4"/>
          ${aprox ? '<rect x="2" y="2" width="24" height="24" rx="7" fill="none" stroke="#111111" stroke-width="1.3" stroke-dasharray="3 2.5"/>' : ''}
          <g transform="translate(2 2)" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${GLIFOS[glifo](color, tinta)}</g></svg>`;
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
    const tamano = ['interpolate', ['linear'], ['zoom'], 12, 0.7, 16, 1];
    if (capa.marcador === 'corazon') {
      return {
        id: fuente + '-marcador', type: 'symbol',
        layout: { 'icon-image': ['concat', `marc-${capa.id}-unico-corazon`, esAproximada(capa)], 'icon-size': tamano, 'icon-allow-overlap': true, 'icon-ignore-placement': true },
      };
    }
    const c = capa.clasificar;
    const valores = c ? Object.keys(c.valores || {}) : [];
    const esRefugio = ['==', ['get', 'tipo'], 'refugio'];
    const clase = ['case', esRefugio, 'refugio', valores.length ? ['match', texto(c.propiedad), valores, texto(c.propiedad), 'otro'] : 'otro'];
    const conFotos = ['all', ['has', 'fotos'], ['>', ['length', ['get', 'fotos']], 0]];
    const glifo = ['case', esRefugio, 'refugio', conFotos, 'foto', 'aviso'];
    const aprox = esAproximada(capa);
    return {
      id: fuente + '-marcador', type: 'symbol',
      layout: { 'icon-image': ['concat', `marc-${capa.id}-`, clase, '-', glifo, aprox], 'icon-size': ['interpolate', ['linear'], ['zoom'], 12, 0.7, 16, 1], 'icon-allow-overlap': true, 'icon-ignore-placement': true },
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
      mapa.addSource(fuente, { type: 'geojson', data: conV(datosUrl() + capa.archivo), tolerance: 0.5 });
    }
    const e = capa.estilo || {};

    if (capa.tipo === 'poligono') {
      if (capa.patron) {
        ponerRayado(mapa, capa.patron);
        agregar({ id: fuente + '-relleno', type: 'fill', paint: { 'fill-pattern': capa.patron.id } });
      } else if (e.fill !== false && ((e.fillOpacity ?? 0.2) > 0 || capa.clasificar)) {
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
        // «estilo_si» con trazo discontinuo (áreas por validar): esas entidades van en su propia
        // capa, porque MapLibre no admite el trazo por elemento.
        const regla = (capa.estilo_si || []).find((r) => r.estilo && r.estilo.dashArray);
        if (regla) {
          const cond = condicionDe(regla);
          agregar({ id: fuente + '-borde', type: 'line', filter: filtro ? ['all', filtro, ['!', cond]] : ['!', cond], paint: pintura });
          agregar({ id: fuente + '-borde-si', type: 'line', filter: filtro ? ['all', filtro, cond] : cond, paint: Object.assign({}, pintura, { 'line-dasharray': trazo(regla.estilo.dashArray) }) });
        } else agregar({ id: fuente + '-borde', type: 'line', paint: pintura });
      }
    }

    if (capa.tipo === 'linea') {
      const forma = { 'line-cap': 'round', 'line-join': 'round' };
      // Una capa de líneas puede traer áreas (el agua empozada del flujo observado): se rellenan.
      if (capa.clasificar && Object.values(capa.clasificar.valores || {}).some((v) => v.fillColor)) {
        agregar({
          id: fuente + '-area', type: 'fill', filter: ['==', ['geometry-type'], 'Polygon'],
          paint: { 'fill-color': porClase(capa, 'fillColor', 'rgba(0,0,0,0)'), 'fill-opacity': porClase(capa, 'fillOpacity', 0.2) },
        });
      }
      if (capa.borde) {
        agregar({ id: fuente + '-halo', type: 'line', layout: forma, paint: { 'line-color': capa.borde.color, 'line-width': capa.borde.weight, 'line-opacity': capa.borde.opacity ?? 1 } });
      }
      // MapLibre no admite trazo discontinuo por elemento: las clases con trazo van en su propia capa.
      const conTrazo = capa.clasificar ? Object.entries(capa.clasificar.valores || {}).filter(([, v]) => v.dashArray) : [];
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

    if (capa.tipo === 'punto' && conMarcador(capa)) {
      agregar(capaDeMarcadores(capa, fuente));
    } else if (capa.tipo === 'punto' && !capa.solo_rotulo) {
      agregar({
        id: fuente + '-punto', type: 'circle',
        paint: {
          'circle-radius': e.radius || 6, 'circle-color': porClase(capa, 'fillColor', '#3388ff'),
          // Borde oscuro y grueso: el punto cae en susceptibilidad alta o media (igual que en /mapas).
          'circle-stroke-color': ['case', ['to-boolean', ['get', 'en_susc_alta_media']], '#111827', '#ffffff'],
          'circle-stroke-width': ['case', ['to-boolean', ['get', 'en_susc_alta_media']], 2.5, 1.5],
        },
      });
      const simbolos = capa.clasificar ? Object.entries(capa.clasificar.valores || {}).filter(([, v]) => v.simbolo) : [];
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
          type: 'image', url: conV(`${datosUrl()}raster/${clave}_${capa.raster}.png`),
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
        type: 'raster', tiles: [conV(`${location.origin}${SOS.cfg.capasUrl}teselas/${capa.teselas}/${t.relieve.url}`)], tileSize: 256,
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
      estado.limites = await fetch(conV(datosUrl() + 'raster/limites.json')).then((r) => r.json()).catch(() => ({}));
    }
    if (capa.tipo === 'teselas' && !estado.teselas[capa.teselas]) {
      estado.teselas[capa.teselas] = await fetch(conV(`${SOS.cfg.capasUrl}teselas/${capa.teselas}/teselas.json`)).then((r) => r.json()).catch(() => null);
    }
    if (conMarcador(capa)) await prepararMarcadores(capa);
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
    if (a.shp) h += `<a href="${x(conV(u + a.shp.url))}" download>↓ ${x(a.shp.formato || 'Shapefile')} <i>${x(a.shp.tam)}</i></a>`;
    if (a.geojson) h += `<a href="${x(conV(u + a.geojson.url))}" download="${x(capa.archivo || '')}">↓ GeoJSON <i>${x(a.geojson.tam)}</i></a>`;
    if (a.extra) h += `<a href="${x(a.extra.url)}" target="_blank" rel="noopener">↓ ${x(a.extra.texto)}</a>`;
    return h + '</span>';
  }
  function elementosDe(capa) {
    const a = estado.descargas[capa.archivo];
    return a && a.elementos ? ` · ${a.elementos.toLocaleString('es')} elementos` : '';
  }

  // ── Leyendas ──────────────────────────────────────────────────────────────
  function leyenda(capa) {
    if (capa.solo_rotulo) return [];
    if (capa.leyenda) return capa.leyenda.map(([color, t]) => ({ forma: 'cuadro', color, texto: t }));
    const c = capa.clasificar, e = capa.estilo || {};
    if (capa.marcador === 'corazon') {
      const color = e.fillColor || '#db2777';
      return [
        { forma: 'marcador', color, glifo: 'corazon', texto: 'Corazón: buena noticia o ayuda' },
        { forma: 'marcador', color, aprox: true, texto: 'Borde punteado: ubicación aproximada o del barrio' },
      ];
    }
    if (!c) return [];
    if (capa.marcador === 'reporte') {
      return Object.values(c.valores || {}).concat(c.otro ? [c.otro] : [])
        .map((v) => ({ forma: 'marcador', color: v.fillColor || '#888', texto: v.etiqueta }))
        .concat([
          { forma: 'marcador', color: '#6b7280', glifo: 'foto', texto: 'Cámara: reporte con foto' },
          { forma: 'marcador', color: '#6b7280', glifo: 'aviso', texto: 'Triángulo: reporte sin foto' },
          { forma: 'marcador', color: VERDE_REFUGIO, glifo: 'refugio', texto: 'Casa: refugio' },
          { forma: 'marcador', color: '#6b7280', aprox: true, texto: 'Borde punteado: ubicación aproximada o por confirmar' },
        ]);
    }
    const forma = capa.tipo === 'punto' ? 'punto' : capa.tipo === 'linea' ? 'linea' : 'cuadro';
    const clases = (c.rangos || Object.values(c.valores || {})).concat(c.otro ? [c.otro] : []);
    const lista = clases.map((v) => ({
      forma, color: (forma === 'linea' ? v.color || e.color : v.fillColor || v.color || e.fillColor || e.color) || '#888',
      simbolo: v.simbolo, discontinua: Boolean(v.dashArray), texto: v.etiqueta,
    }));
    for (const r of capa.estilo_si || []) {
      if (r.etiqueta) lista.push({ forma: 'linea', color: '#6b7280', discontinua: Boolean(r.estilo && r.estilo.dashArray), texto: r.etiqueta });
    }
    return lista;
  }
  function muestra(l) {
    const c = SOS.escapar(l.color);
    if (l.forma === 'marcador') {
      const dibujo = l.glifo ? `<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${GLIFOS[l.glifo](l.color, '#ffffff')}</svg>` : '';
      return `<i class="muestra marcador${l.glifo ? ' grande' : ''}${l.aprox ? ' aprox' : ''}" style="background:${c}">${dibujo}</i>`;
    }
    if (l.forma === 'punto') return `<i class="muestra punto" style="background:${c}">${SOS.escapar(l.simbolo || '')}</i>`;
    if (l.forma === 'linea') return `<i class="muestra linea" style="border-top-color:${c};border-top-style:${l.discontinua ? 'dashed' : 'solid'}"></i>`;
    return `<i class="muestra cuadro" style="background:${c}"></i>`;
  }

  // ── Panel ─────────────────────────────────────────────────────────────────
  function pintar() {
    const m = estado.manifiesto;
    const zoom = estado.mapa.getZoom();
    const x = SOS.escapar;
    let h = '<div class="capas-titulo">Ir a</div><div class="pildoras"><button type="button" data-ir="Archipiélago">Archipiélago</button>';
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
          h += '</div>';
        }
        h += '</div>';
      }
      h += '</div>';
    }
    if (estado.version && estado.version.texto) h = `<p class="capas-version">Capas y modelos actualizados: <b>${x(estado.version.texto)}</b></p>` + h;
    if (estado.todo) {
      const u = SOS.cfg.capasUrl;
      h += `<div class="capas-grupo"><div class="capas-titulo">Descargar todas las capas</div><span class="capa-descargas todo">
        <a href="${x(conV(u + estado.todo.shp.url))}" download>↓ Shapefile <i>${x(estado.todo.shp.tam)}</i></a>
        <a href="${x(conV(u + estado.todo.geojson.url))}" download>↓ GeoJSON <i>${x(estado.todo.geojson.tam)}</i></a></span>
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
      const [[s, o], [n, este]] = b.dataset.ir === 'Archipiélago' ? lugares().archipielago : m.islas[b.dataset.ir].bounds;
      estado.mapa.fitBounds([[o, s], [este, n]], { padding: 30, duration: 600 });
      history.replaceState(null, '', location.pathname + location.search + '#' + claveLugar(b.dataset.ir));
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
    // Se busca en un cuadrito alrededor del dedo, no en un solo píxel. Si en ese lugar hay un
    // reporte de campo (con sus fotos), gana el reporte aunque tenga encima otro punto: antes
    // se abría el punto de control del modelo y las fotos no aparecían.
    const r = 9, caja = [[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]];
    const capaDe = (x) => estado.capas.find((c) => x.layer.source === 'capa-' + c.id);
    const tocados = estado.mapa.queryRenderedFeatures(caja, { layers: ids }).filter((x) => { const c = capaDe(x); return c && c.popup; });
    if (!tocados.length) return false;
    const enElPunto = estado.mapa.queryRenderedFeatures(e.point, { layers: ids });
    const f = tocados.find((x) => conMarcador(capaDe(x)))
      || tocados.find((x) => x.geometry.type === 'Point')
      || enElPunto.find((x) => { const c = capaDe(x); return c && c.popup; })
      || tocados[0];
    const capa = capaDe(f);
    const p = capa.popup, datos = f.properties;
    let fotos = p.fotos ? datos[p.fotos] : null;
    if (typeof fotos === 'string') { try { fotos = JSON.parse(fotos); } catch (err) { fotos = null; } }
    // Todo se lee en la hoja (teléfono) o en el panel (escritorio), nunca en un globo:
    // un globo con texto largo se sale de la pantalla del teléfono.
    SOS.mostrarDetalle(fichaDeCapa(capa, datos, Array.isArray(fotos) ? fotos : []), f.geometry.type === 'Point' ? f.geometry.coordinates : null);
    return true;
  }

  // ── Pista al pasar el ratón ───────────────────────────────────────────────
  // Texto corto que dice qué es un punto o una línea de una capa, sin tener que tocarlo.
  // Devuelve { titulo, detalle } o null. Los polígonos no dan pista: cubren casi todo el mapa.
  function pista(punto) {
    // Solo las capas de puntos y de líneas; el borde de un área no cuenta.
    const ids = estado.capas.filter((c) => c.tipo === 'punto' || c.tipo === 'linea')
      .flatMap((c) => estado.puestas[c.id] || [])
      .filter((id) => estado.mapa.getLayer(id) && !id.endsWith('-halo') && !id.endsWith('-rotulo') && !id.endsWith('-simbolo') && !id.endsWith('-area'));
    if (!ids.length) return null;
    const r = 5, caja = [[punto.x - r, punto.y - r], [punto.x + r, punto.y + r]];
    const tocados = estado.mapa.queryRenderedFeatures(caja, { layers: ids });
    const f = tocados.find((x) => x.geometry.type === 'Point') || tocados[0];
    if (!f) return null;
    const capa = estado.capas.find((c) => f.layer.source === 'capa-' + c.id);
    if (!capa) return null;
    const datos = f.properties, c = capa.clasificar, p = capa.popup || {};
    // La clase del elemento («Prioridad alta», «Gravedad 3: grave»…), si la capa clasifica.
    let clase = '';
    if (c && c.rangos) clase = (c.rangos.find((x) => (Number(datos[c.propiedad]) || 0) <= x.hasta) || {}).etiqueta || '';
    else if (c) clase = ((c.valores || {})[String(datos[c.propiedad])] || c.otro || {}).etiqueta || '';
    const nombre = datos[p.titulo] != null && String(datos[p.titulo]).length <= 70 ? String(datos[p.titulo]) + (p.sufijo_titulo || '') : '';
    const queEs = capa.corto || capa.titulo;
    // Un código («SC-020», «CR-SCZ-0006») no explica nada: ahí manda qué es el punto.
    const esCodigo = /^[A-Z0-9_-]+$/i.test(nombre) && /\d/.test(nombre);
    if (!nombre || esCodigo) return { titulo: queEs, detalle: [clase, nombre].filter(Boolean).join(' · ') };
    return { titulo: nombre, detalle: [clase, queEs].filter(Boolean).join(' · ') };
  }

  // Ficha de un elemento de una capa, con sus fotos (rutas relativas a capa.fotos_base).
  function fichaDeCapa(capa, datos, fotos) {
    const p = capa.popup, x = SOS.escapar, base = datosUrl() + (capa.fotos_base || '');
    const titulo = (datos[p.titulo] ?? p.titulo_defecto ?? capa.titulo) + (datos[p.titulo] != null ? p.sufijo_titulo || '' : '');
    let h = `<article class="ficha"><button class="ficha-volver" type="button" data-cerrar-ficha>← Volver a la lista</button>`;
    // Primero las fotos: es lo que la persona viene a ver. La primera va grande.
    if (fotos.length) {
      h += '<div class="fotos">';
      fotos.forEach((f, i) => {
        const pie = (f.hora && !(f.pie || '').startsWith(f.hora) ? f.hora + ' · ' : '') + (f.pie || '');
        h += `<figure><button type="button" data-foto="${x(base + f.archivo)}" data-pie="${x(pie)}" aria-label="Ver la foto en grande">
          <img ${i ? 'loading="lazy" ' : ''}src="${x(base + (i ? f.mini || f.archivo : f.archivo))}" alt="${x(f.pie || 'Foto del reporte')}"></button>
          <figcaption>${x(pie)}</figcaption></figure>`;
      });
      h += '</div>';
      if (fotos.length > 1) h += `<p class="fotos-cuenta">${fotos.length} fotos. Toca una para verla en grande.</p>`;
    }
    h += `<p class="ficha-capa">${x(capa.titulo)}</p><h2 class="ficha-titulo">${x(titulo)}</h2><ul class="ficha-datos">`;
    for (const [campo, etiqueta] of Object.entries(p.campos || {})) {
      if (datos[campo] != null && datos[campo] !== '') h += `<li><span>${x(etiqueta)}</span> ${x(datos[campo])}</li>`;
    }
    h += '</ul>';
    if (p.texto && datos[p.texto]) h += `<p class="ficha-texto">${x(datos[p.texto])}</p>`;
    return h + `<p class="ficha-pie">${x(capa.fuente || '')}</p></article>`;
  }

  // ── Versión de lo publicado en /mapas y actualización en vivo ─────────────
  // version.txt lo escribe servidores/publicar.sh en cada publicación: «<commit> <fecha>».
  // Si no existe, sirve de versión la huella (ETag) del manifiesto.
  async function versionPublicada(respuestaManifiesto) {
    try {
      const t = await fetch(SOS.cfg.capasUrl + 'version.txt', { cache: 'no-cache' }).then((r) => (r.ok ? r.text() : ''));
      const [commit, fecha] = t.trim().split(/\s+/);
      if (commit && fecha && !Number.isNaN(Date.parse(fecha))) {
        const texto = new Date(fecha).toLocaleString('es-EC', { timeZone: 'Pacific/Galapagos', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
        return { id: `${commit}-${Date.parse(fecha) / 1000}`, texto: `${texto} (hora de Galápagos)` };
      }
    } catch (e) { /* se usa la huella del manifiesto */ }
    const huella = respuestaManifiesto.headers.get('ETag') || respuestaManifiesto.headers.get('Last-Modified') || '';
    return huella ? { id: huella.replace(/[^\w-]/g, ''), texto: '' } : null;
  }

  // Trae el manifiesto y el índice de descargas, y deja anotada la versión. Devuelve el manifiesto o null.
  async function traer() {
    try {
      const r = await fetch(SOS.cfg.capasUrl + 'capas.json', { cache: 'no-cache' });
      if (!r.ok) return null;
      const m = await r.json();
      estado.version = await versionPublicada(r);
      const d = await fetch(conV(SOS.cfg.capasUrl + 'descargas.json'), { cache: 'no-cache' }).then((x) => x.json()).catch(() => null);
      const variante = d && d.variantes && d.variantes[SOS.cfg.capasVariante];
      if (variante) { estado.descargas = variante.archivos || {}; estado.todo = variante.todo || null; }
      return m;
    } catch (e) { return null; }
  }

  // Capas con las que se arranca: la elección guardada de la persona, más las capas nuevas
  // que /mapas publique encendidas desde su última visita.
  function arranqueCon(elegidas) {
    if (Array.isArray(elegidas)) return elegidas; // formato anterior
    if (!elegidas || !Array.isArray(elegidas.encendidas)) return estado.iniciales;
    const conocidas = new Set(elegidas.conocidas || []);
    const nuevas = estado.iniciales.filter((id) => !conocidas.has(id));
    return elegidas.encendidas.concat(nuevas);
  }

  function quitarFuentes(capa) {
    const base = 'capa-' + capa.id;
    for (const id of Object.keys(estado.mapa.getStyle().sources)) {
      if (id === base || id.startsWith(base + '-')) estado.mapa.removeSource(id);
    }
  }

  function ordenar(m) {
    estado.manifiesto = m;
    estado.capas = m.grupos.flatMap((g) => g.capas);
    // Abajo imágenes y áreas, luego líneas, luego puntos y, encima de todo, los reportes de campo.
    const altura = (c) => (conMarcador(c) ? 4 : { raster: 0, teselas: 0, poligono: 1, linea: 2, punto: 3 }[c.tipo]);
    estado.orden = estado.capas.map((c, i) => [c, i]).sort((a, b) => (altura(a[0]) - altura(b[0])) || (a[1] - b[1])).map(([c]) => c);
    const movil = SOS.esMovil(), siempre = SOS.cfg.capasSiempreGrupos || [], apagadas = SOS.cfg.capasApagadasAlAbrir || [];
    estado.iniciales = m.grupos.flatMap((g) => g.capas
      .filter((c) => c.visible && !apagadas.includes(c.id) && (!movil || c.visible_movil !== false || siempre.includes(g.id)))
      .map((c) => c.id));
  }

  // Pregunta si /mapas publicó algo nuevo. Si sí, vuelve a dibujar lo encendido con los datos
  // nuevos, enciende las capas nuevas que vengan visibles y avisa.
  let revisando = false;
  async function revisar() {
    if (revisando || !estado.manifiesto) return;
    revisando = true;
    try {
      const antes = estado.version && estado.version.id;
      const conocidas = new Set(estado.capas.map((c) => c.id));
      const viejas = estado.orden.slice();
      const versionVieja = estado.version;
      const m = await traer();
      if (!m) { estado.version = versionVieja; return; }
      if (!estado.version || estado.version.id === antes) return;
      const encendidas = [...estado.encendidas];
      for (const capa of viejas) { apagar(capa); quitarFuentes(capa); }
      estado.encendidas.clear(); estado.puestas = {}; estado.limites = null; estado.teselas = {};
      ordenar(m);
      const nuevas = estado.iniciales.filter((id) => !conocidas.has(id));
      const quedan = new Set(encendidas.concat(nuevas));
      for (const capa of estado.orden) {
        if (quedan.has(capa.id)) { estado.encendidas.add(capa.id); await encender(capa); }
      }
      recordar();
      if (!panel().hidden) pintar();
      avisar(nuevas.length ? `Capas actualizadas. ${nuevas.length === 1 ? 'Hay una capa nueva' : `Hay ${nuevas.length} capas nuevas`}.` : 'Capas y modelos actualizados.');
    } finally { revisando = false; }
  }
  function avisar(textoAviso) {
    const caja = document.getElementById('aviso-capas');
    if (!caja) return;
    caja.textContent = textoAviso;
    caja.hidden = false;
    clearTimeout(avisar.t);
    avisar.t = setTimeout(() => { caja.hidden = true; }, 7000);
  }

  // ── Enlaces a un lugar, iguales a los de /mapas ───────────────────────────
  //   /riesgos/#ptoayora   /riesgos/#la-cascada   /riesgos/#-0.7365,-90.3135,16 (lat,lon,zoom)
  // Las coordenadas las atiende mapa.js al abrir; aquí van los nombres, que salen del manifiesto.
  const claveLugar = (t) => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
  function lugares() {
    const l = { archipielago: [[-1.6, -92.1], [0.8, -89.1]], lacascada: [[-0.7362, -90.3168], [-0.7322, -90.3105]], bellavista: [[-0.7, -90.333], [-0.689, -90.32]] };
    for (const [nombre, v] of Object.entries((estado.manifiesto && estado.manifiesto.islas) || {})) l[claveLugar(nombre)] = v.bounds;
    for (const [alias, k] of Object.entries({ ptoayora: 'puertoayora', ayora: 'puertoayora', cascada: 'lacascada', galapagos: 'archipielago' })) if (l[k]) l[alias] = l[k];
    return l;
  }
  function irSegunURL() {
    let h = '';
    try { h = decodeURIComponent(location.hash.slice(1)); } catch (e) { return false; }
    const m = h.match(/^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)(?:,(\d+(?:\.\d+)?))?$/);
    if (m && Math.abs(+m[1]) <= 90 && Math.abs(+m[2]) <= 180) {
      estado.mapa.jumpTo({ center: [+m[2], +m[1]], zoom: Math.min(19, +(m[3] || 16)) });
      return true;
    }
    const b = lugares()[claveLugar(h)];
    if (!b) return false;
    estado.mapa.fitBounds([[b[0][1], b[0][0]], [b[1][1], b[1][0]]], { padding: 20, duration: 0 });
    return true;
  }

  const panel = () => document.getElementById('capas-panel');
  function abrir() { panel().hidden = false; document.getElementById('capas-abrir').hidden = true; pintar(); }
  function cerrar() { panel().hidden = true; document.getElementById('capas-abrir').hidden = false; }

  SOS.capas = {
    globo, revisar, conV, pista,
    async iniciar(mapa) {
      estado.mapa = mapa;
      document.getElementById('capas-abrir').addEventListener('click', abrir);
      document.getElementById('capas-cerrar').addEventListener('click', cerrar);
      document.getElementById('capas-cuerpo').addEventListener('click', alHacerClic);
      const m = await traer();
      if (!m) {
        document.getElementById('capas-abrir').hidden = true; // sin manifiesto no hay panel
        return;
      }
      ordenar(m);
      // Mapa base al abrir: el que la persona eligió la última vez o, si no, el de los ajustes
      // (calles). Sin conexión se queda la base gris, que está guardada en el teléfono.
      let base = SOS.cfg.baseInicial || 'gris';
      try { base = localStorage.getItem(BASE_GUARDADA) || base; } catch (err) { /* sin acceso */ }
      const def = (m.mapas_base || []).find((x) => x.id === base);
      if (def && navigator.onLine !== false) { estado.base = base; SOS.ponerBase(mapa, def); }
      // Si la persona ya eligió capas en una visita anterior, se respeta su elección.
      let elegidas = null;
      try { elegidas = JSON.parse(localStorage.getItem(GUARDADO)); } catch (e) { /* nada guardado */ }
      const arranque = arranqueCon(elegidas);
      for (const capa of estado.orden) {
        if (arranque.includes(capa.id)) { estado.encendidas.add(capa.id); await encender(capa); }
      }
      if (location.hash.length > 1 && !/^#-?\d/.test(location.hash)) irSegunURL(); // nombre de lugar
      window.addEventListener('hashchange', irSegunURL);
      setInterval(() => { if (!document.hidden) revisar(); }, CONSULTA_MS);
      document.addEventListener('visibilitychange', () => { if (!document.hidden) revisar(); });
      let anterior = Math.floor(mapa.getZoom());
      mapa.on('zoomend', () => {
        const z = Math.floor(mapa.getZoom());
        if (z !== anterior && !panel().hidden) pintar();
        anterior = z;
      });
    },
  };
})();
