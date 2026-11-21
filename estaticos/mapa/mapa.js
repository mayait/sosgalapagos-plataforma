/* Mapa de reportes: pines por estado, clusters, desteñido por edad, fichas de tiempo,
   lista de lo que hay cerca y ficha del reporte. */
(function () {
  'use strict';
  const SOS = window.SOS, cfg = SOS.cfg;
  const COLOR = { por_verificar: '#6b7280', confirmado: '#e11b22', bajando: '#d97706', cerrado: '#b4b4b4', bueno: '#f2b400', ayuda: '#000000' };
  const SONDEO_MS = 4000;       // cada cuánto se pregunta si hay reportes nuevos
  const OPACIDAD_MINIMA = 0.4;  // un reporte a punto de vencer no desaparece del todo

  // Enlace a un punto, igual que en /mapas: /riesgos/#lat,lon,zoom
  const enlace = (() => {
    const m = decodeURIComponent(location.hash.slice(1)).match(/^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)(?:,(\d+(?:\.\d+)?))?$/);
    return m && Math.abs(+m[1]) <= 90 && Math.abs(+m[2]) <= 180 ? { centro: [+m[2], +m[1]], zoom: Math.min(19, +(m[3] || 16)) } : null;
  })();

  const mapa = new maplibregl.Map({
    container: 'mapa',
    style: SOS.estiloBase(),
    center: enlace ? enlace.centro : cfg.centro,
    zoom: enlace ? enlace.zoom : cfg.zoom,
    minZoom: 7,
    maxZoom: 19,
    maxPitch: 75,
    maxBounds: [[-93.2, -2.4], [-88.0, 1.6]],
    attributionControl: { compact: true },
    fadeDuration: 0,              // menos trabajo en teléfonos lentos
    dragRotate: false,
    pitchWithRotate: false,
    cooperativeGestures: false,
  });
  mapa.touchZoomRotate.disableRotation();
  mapa.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  SOS.mapa = mapa;

  let periodo = 'ahora', etiqueta = null, coleccion = { type: 'FeatureCollection', features: [] };

  // ── Iconos de los tipos: se toman del SVG de la página y se pintan en blanco ──
  function cargarIconos() {
    const simbolos = document.querySelectorAll('#iconos symbol[id^="i-"]');
    return Promise.all([...simbolos].map((s) => {
      const nombre = s.id.slice(2);
      const pintar = (color, sufijo) => new Promise((listo) => {
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${s.innerHTML}</svg>`;
        const img = new Image(48, 48);
        img.onload = () => { if (!mapa.hasImage(nombre + sufijo)) mapa.addImage(nombre + sufijo, img, { pixelRatio: 2 }); listo(); };
        img.onerror = listo;
        img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      });
      return Promise.all([pintar('#ffffff', ''), pintar('#6b7280', '-gris'), pintar('#1d1d1b', '-tinta')]);
    }));
  }

  // ── Edad: qué fracción del plazo ya pasó. Se recalcula aquí, sin pedir datos. ──
  function conEdad(datos) {
    const ahora = Date.now() / 1000;
    for (const f of datos.features) {
      const p = f.properties;
      const plazo = Math.max(1, p.vence - p.visto);
      p.frac = p.estado === 'cerrado' ? 1 : Math.min(1, Math.max(0, (ahora - p.visto) / plazo));
    }
    return datos;
  }

  function pintarReportes() {
    const fuente = mapa.getSource('reportes');
    if (fuente) fuente.setData(conEdad(coleccion));
    actualizarVacio();
  }

  async function traerReportes(forzar) {
    try {
      const cabeceras = etiqueta && !forzar ? { 'If-None-Match': etiqueta } : {};
      const r = await fetch(`${cfg.vivos}?periodo=${periodo}`, { headers: cabeceras, cache: 'no-store' });
      avisarConexion(null);
      if (r.status === 304) return;
      if (!r.ok) return;
      etiqueta = r.headers.get('ETag');
      coleccion = await r.json();
      try { localStorage.setItem('sos-reportes', JSON.stringify({ t: Date.now(), datos: coleccion })); } catch (e) { /* sin espacio */ }
      pintarReportes();
    } catch (e) {
      // Sin señal: se muestra lo último que se guardó, con su hora.
      const guardado = JSON.parse(localStorage.getItem('sos-reportes') || 'null');
      if (guardado && !coleccion.features.length) { coleccion = guardado.datos; pintarReportes(); }
      avisarConexion(guardado ? guardado.t : 0);
    }
  }

  function avisarConexion(t) {
    const caja = document.getElementById('sin-conexion');
    if (t === null) { caja.hidden = true; return; }
    const hora = t ? new Date(t).toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' }) : null;
    caja.textContent = hora ? `Sin conexión. Reportes de las ${hora}.` : 'Sin conexión.';
    caja.hidden = false;
  }

  function actualizarVacio() {
    if (!mapa.getLayer('reportes-pin')) return;
    const hay = mapa.queryRenderedFeatures({ layers: ['reportes-pin', 'reportes-grupo'] }).length > 0;
    document.getElementById('sin-reportes').hidden = hay;
  }

  function ponerCapasDeReportes() {
    mapa.addSource('reportes', {
      type: 'geojson', data: conEdad(coleccion),
      cluster: true, clusterRadius: 46, clusterMaxZoom: 15,
      clusterProperties: { graves: ['+', ['case', ['all', ['==', ['get', 'clase'], 'riesgo'], ['==', ['get', 'gravedad'], 'peligro_vida']], 1, 0]] },
    });
    const suelto = ['!', ['has', 'point_count']];
    const opacidad = ['interpolate', ['linear'], ['get', 'frac'], 0, 1, 1, OPACIDAD_MINIMA];
    const esPeligro = ['==', ['get', 'clase'], 'riesgo'];
    const radio = ['case', esPeligro, ['match', ['get', 'gravedad'], 'peligro_vida', 17, 'no_pasar', 14.5, 12.5], 13.5];

    // Grupos: círculo negro con el número. Borde rojo si dentro hay peligro de vida.
    mapa.addLayer({
      id: 'reportes-grupo', type: 'circle', source: 'reportes', filter: ['has', 'point_count'],
      paint: {
        'circle-color': '#000000',
        'circle-radius': ['step', ['get', 'point_count'], 15, 5, 18, 20, 22],
        'circle-stroke-color': ['case', ['>', ['get', 'graves'], 0], '#e11b22', '#ffffff'],
        'circle-stroke-width': 3,
      },
    });
    mapa.addLayer({
      id: 'reportes-grupo-numero', type: 'symbol', source: 'reportes', filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Medium'], 'text-size': 13, 'text-allow-overlap': true },
      paint: { 'text-color': '#ffffff' },
    });
    // Anillo negro: peligro de vida.
    mapa.addLayer({
      id: 'reportes-anillo', type: 'circle', source: 'reportes',
      filter: ['all', suelto, esPeligro, ['==', ['get', 'gravedad'], 'peligro_vida'], ['!=', ['get', 'estado'], 'cerrado']],
      paint: { 'circle-radius': 22, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#000000', 'circle-stroke-width': 2.5, 'circle-stroke-opacity': opacidad },
    });
    // Pin: relleno según el estado. «Por verificar» va hueco, con borde gris.
    mapa.addLayer({
      id: 'reportes-pin', type: 'circle', source: 'reportes', filter: suelto,
      paint: {
        'circle-radius': radio,
        // Sin verificar, hueco. Cerrado, gris. Lo bueno, amarillo; donar o colaborar, negro.
        // Los peligros, según su estado: rojo confirmado, ámbar bajando.
        'circle-color': ['case',
          ['==', ['get', 'estado'], 'por_verificar'], '#ffffff',
          ['==', ['get', 'estado'], 'cerrado'], COLOR.cerrado,
          ['==', ['get', 'clase'], 'bueno'], COLOR.bueno,
          ['==', ['get', 'clase'], 'ayuda'], COLOR.ayuda,
          ['==', ['get', 'estado'], 'bajando'], COLOR.bajando,
          COLOR.confirmado],
        'circle-stroke-color': ['match', ['get', 'estado'], 'por_verificar', COLOR.por_verificar, '#ffffff'],
        'circle-stroke-width': ['match', ['get', 'estado'], 'por_verificar', 2.5, 2],
        'circle-opacity': opacidad, 'circle-stroke-opacity': opacidad,
      },
    });
    mapa.addLayer({
      id: 'reportes-icono', type: 'symbol', source: 'reportes', filter: suelto,
      layout: {
        'icon-image': ['case',
          ['==', ['get', 'estado'], 'por_verificar'], ['concat', ['get', 'icono'], '-gris'],
          ['all', ['==', ['get', 'clase'], 'bueno'], ['!=', ['get', 'estado'], 'cerrado']], ['concat', ['get', 'icono'], '-tinta'], // sobre amarillo, icono oscuro
          ['get', 'icono']],
        'icon-size': ['match', ['get', 'gravedad'], 'peligro_vida', 0.85, 'no_pasar', 0.72, 0.62],
        'icon-allow-overlap': true, 'icon-ignore-placement': true,
      },
      paint: { 'icon-opacity': opacidad },
    });
  }

  // ── Hoja inferior y ficha ─────────────────────────────────────────────────
  const hoja = document.getElementById('hoja');
  const detalle = document.getElementById('detalle');
  const cerca = document.getElementById('cerca');
  const lista = document.getElementById('lista'); // lo que se ve cuando no hay ficha abierta
  // La hoja tiene tres alturas: asomada, media y abierta. Se arrastra o se toca el asa.
  const ASOMADA = 96;
  let alturaHoja = ASOMADA;
  const alturas = () => {
    const total = Math.round(hoja.parentElement.clientHeight * 0.88);
    return [ASOMADA, Math.round(total * 0.7), total];
  };
  function ponerHoja(px, animar = true) {
    alturaHoja = px;
    hoja.classList.toggle('arrastrando', !animar);
    hoja.style.setProperty('--hoja-visible', px + 'px');
    hoja.classList.toggle('abierta', px > ASOMADA + 10);
  }
  // true abre a media altura (o deja como está si ya está más arriba); false la asoma.
  const abrirHoja = (si) => ponerHoja(si ? Math.max(alturaHoja, alturas()[1]) : ASOMADA);
  SOS.abrirHoja = abrirHoja;

  let arrastre = null;
  function alTomar(e) {
    if (!SOS.esMovil() || e.target.closest('a, .reportar')) return;
    arrastre = { y: e.clientY, inicio: alturaHoja, movido: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function alArrastrar(e) {
    if (!arrastre) return;
    const d = arrastre.y - e.clientY;
    if (Math.abs(d) > 6) arrastre.movido = true;
    const [min, , max] = alturas();
    ponerHoja(Math.min(max, Math.max(min, arrastre.inicio + d)), false);
  }
  function alSoltar(e) {
    if (!arrastre) return;
    const { movido, inicio } = arrastre;
    arrastre = null;
    const pasos = alturas();
    if (!movido) { // un toque en el asa: sube un paso, y desde arriba vuelve a asomarse
      if (e.target.closest('#hoja-asa')) ponerHoja(inicio >= pasos[1] - 10 ? ASOMADA : pasos[1]);
      else ponerHoja(inicio);
      return;
    }
    // Se queda en la altura más cercana, con algo de impulso hacia donde iba el dedo.
    const meta = alturaHoja + (alturaHoja - inicio) * 0.25;
    ponerHoja(pasos.reduce((a, b) => (Math.abs(b - meta) < Math.abs(a - meta) ? b : a)));
  }
  for (const el of [document.getElementById('hoja-asa')]) {
    el.addEventListener('pointerdown', alTomar);
    el.addEventListener('pointermove', alArrastrar);
    el.addEventListener('pointerup', alSoltar);
    el.addEventListener('pointercancel', alSoltar);
  }
  window.addEventListener('resize', () => ponerHoja(Math.min(alturaHoja, alturas()[2])));

  function abrirFicha(id) {
    htmx.ajax('GET', cfg.ficha + id + '/', { target: '#detalle', swap: 'innerHTML' });
  }
  function cerrarFicha() {
    detalle.innerHTML = '';
    lista.hidden = false;
    history.replaceState(null, '', location.pathname + location.hash);
  }
  // Las capas de /mapas con fotos o texto largo (reportes de campo) se leen aquí, no en un globo.
  SOS.mostrarDetalle = function (html, lngLat) {
    detalle.innerHTML = html;
    lista.hidden = true;
    abrirHoja(true);
    hoja.querySelector('.hoja-cuerpo').scrollTop = 0;
    if (lngLat) centrarEn(lngLat);
  };
  document.body.addEventListener('htmx:afterSwap', (e) => {
    if (e.target !== detalle) return;
    const ficha = detalle.querySelector('[data-ficha]');
    lista.hidden = Boolean(ficha);
    if (!ficha) return;
    abrirHoja(true);
    hoja.querySelector('.hoja-cuerpo').scrollTop = 0;
    history.replaceState(null, '', '?r=' + ficha.dataset.ficha + location.hash);
  });
  document.body.addEventListener('click', (e) => {
    if (e.target.closest('[data-cerrar-ficha]')) cerrarFicha();
    const fila = e.target.closest('[data-abrir-ficha]');
    if (fila) centrarEn([Number(fila.dataset.lon), Number(fila.dataset.lat)]);
  });
  // ── Visor de fotos ────────────────────────────────────────────────────────
  const visor = document.getElementById('visor');
  let fotos = [], actual = 0;
  function pintarFoto() {
    const f = fotos[actual];
    document.getElementById('visor-img').src = f.url;
    document.getElementById('visor-img').alt = f.pie || 'Foto del reporte';
    document.getElementById('visor-pie').textContent = f.pie || '';
    document.getElementById('visor-cuenta').textContent = fotos.length > 1 ? `${actual + 1} de ${fotos.length}` : '';
    for (const id of ['visor-anterior', 'visor-siguiente']) document.getElementById(id).hidden = fotos.length < 2;
  }
  const pasar = (d) => { actual = (actual + d + fotos.length) % fotos.length; pintarFoto(); };
  const cerrarVisor = () => { visor.hidden = true; document.getElementById('visor-img').src = ''; };
  SOS.verFotos = function (lista, indice) {
    if (!lista.length) return;
    fotos = lista; actual = indice || 0;
    pintarFoto();
    visor.hidden = false;
  };
  document.getElementById('visor-cerrar').addEventListener('click', cerrarVisor);
  document.getElementById('visor-anterior').addEventListener('click', () => pasar(-1));
  document.getElementById('visor-siguiente').addEventListener('click', () => pasar(1));
  document.addEventListener('keydown', (e) => {
    if (visor.hidden) return;
    if (e.key === 'Escape') cerrarVisor();
    if (e.key === 'ArrowLeft') pasar(-1);
    if (e.key === 'ArrowRight') pasar(1);
  });
  // Deslizar con el dedo: a los lados cambia de foto.
  let toqueX = null;
  visor.addEventListener('touchstart', (e) => { toqueX = e.touches.length === 1 ? e.touches[0].clientX : null; }, { passive: true });
  visor.addEventListener('touchend', (e) => {
    if (toqueX === null || fotos.length < 2) return;
    const d = e.changedTouches[0].clientX - toqueX;
    if (Math.abs(d) > 50) pasar(d < 0 ? 1 : -1);
    toqueX = null;
  }, { passive: true });
  // Cualquier foto de una ficha se abre en el visor, con todas las de ese reporte.
  document.body.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-foto]');
    if (!boton) return;
    const todas = [...boton.closest('.ficha, #detalle').querySelectorAll('[data-foto]')];
    SOS.verFotos(todas.map((b) => ({ url: b.dataset.foto, pie: b.dataset.pie || '' })), todas.indexOf(boton));
  });

  // Tras «sigue ahí» o «ya bajó», el mapa se actualiza al instante.
  document.body.addEventListener('reportes-cambiaron', () => traerReportes(true));

  // En el teléfono la hoja tapa la parte baja: el punto se centra en lo que queda visible.
  function centrarEn(lngLat, zoom) {
    const abajo = SOS.esMovil() ? Math.min(alturaHoja, Math.round(mapa.getContainer().clientHeight * 0.6)) : 0;
    mapa.easeTo({ center: lngLat, zoom: Math.max(mapa.getZoom(), zoom || 16), padding: { bottom: abajo }, duration: 500 });
  }

  function pedirCerca() {
    const c = mapa.getCenter();
    htmx.ajax('GET', `${cfg.cerca}?lat=${c.lat.toFixed(5)}&lon=${c.lng.toFixed(5)}`, { target: '#cerca', swap: 'innerHTML' });
  }
  let espera = null, zonaLluvia = null;
  function alMover() {
    actualizarVacio();
    clearTimeout(espera);
    espera = setTimeout(() => {
      // La URL sigue al mapa (lat,lon,zoom), para poder copiar el enlace de lo que se está viendo.
      const v = mapa.getCenter();
      history.replaceState(null, '', `${location.pathname}${location.search}#${v.lat.toFixed(5)},${v.lng.toFixed(5)},${Math.round(mapa.getZoom() * 10) / 10}`);
      pedirCerca();
      // La franja de lluvia cambia solo si el mapa pasó a otra zona de clima.
      const c = mapa.getCenter();
      const zona = c.lng < -90.7 ? 'i' : c.lng > -89.9 ? 'c' : c.lat > -0.7 ? 'a' : 'b';
      if (zona !== zonaLluvia) {
        zonaLluvia = zona;
        htmx.ajax('GET', `${cfg.lluvia}?lat=${c.lat.toFixed(4)}&lon=${c.lng.toFixed(4)}`, { target: '#lluvia', swap: 'innerHTML' });
      }
    }, 500);
  }

  // ── Fichas de tiempo ──────────────────────────────────────────────────────
  document.querySelector('.tiempo').addEventListener('click', (e) => {
    const b = e.target.closest('[data-periodo]');
    if (!b) return;
    periodo = b.dataset.periodo;
    for (const x of document.querySelectorAll('[data-periodo]')) x.setAttribute('aria-pressed', String(x === b));
    traerReportes(true);
  });

  // ── Mi ubicación ──────────────────────────────────────────────────────────
  let yo = null;
  document.getElementById('ubicarme').addEventListener('click', () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((p) => {
      const punto = [p.coords.longitude, p.coords.latitude];
      if (!yo) {
        const el = document.createElement('div');
        el.style.cssText = 'width:16px;height:16px;border-radius:50%;background:#000;border:3px solid #fff;box-shadow:0 0 0 2px rgba(0,0,0,.25)';
        yo = new maplibregl.Marker({ element: el }).setLngLat(punto).addTo(mapa);
      } else yo.setLngLat(punto);
      centrarEn(punto, 16);
    }, () => {}, { enableHighAccuracy: true, timeout: 8000 });
  });

  // ── Pista al pasar el ratón: qué es cada punto, en chiquito ───────────────
  // Solo donde hay ratón; en el teléfono se toca el punto y se abre su ficha.
  const NOMBRES = {
    gravedad: { cuidado: 'Pasar con cuidado', no_pasar: 'No pasar', peligro_vida: 'Peligro de vida' },
    estado: { por_verificar: 'por verificar', confirmado: 'confirmado', bajando: 'bajando', cerrado: 'cerrado' },
  };
  function haceCuanto(segundos) {
    const min = Math.max(0, Math.round((Date.now() / 1000 - segundos) / 60));
    if (min < 1) return 'hace un momento';
    if (min < 60) return `hace ${min} min`;
    const h = Math.floor(min / 60);
    return h < 24 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} d`;
  }
  function pistaDe(punto) {
    if (mapa.getLayer('reportes-pin')) {
      const f = mapa.queryRenderedFeatures(punto, { layers: ['reportes-pin', 'reportes-grupo'] })[0];
      if (f && f.properties.cluster) return { titulo: `${f.properties.point_count} reportes`, detalle: 'Toca para acercarte' };
      if (f) {
        const p = f.properties;
        const partes = [p.clase === 'riesgo' ? NOMBRES.gravedad[p.gravedad] : '', haceCuanto(p.visto), NOMBRES.estado[p.estado]];
        return { titulo: p.tipo_nombre, detalle: partes.filter(Boolean).join(' · ') };
      }
    }
    return SOS.capas.pista(punto);
  }
  if (window.matchMedia('(hover: hover)').matches) {
    const globito = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'pista', offset: 12, maxWidth: '240px' });
    let pendiente = null, ultima = '';
    const quitar = () => { globito.remove(); ultima = ''; mapa.getCanvas().style.cursor = ''; };
    mapa.on('mousemove', (e) => {
      if (pendiente) return;
      pendiente = requestAnimationFrame(() => {
        pendiente = null;
        const t = pistaDe(e.point);
        if (!t) { if (ultima) quitar(); return; }
        mapa.getCanvas().style.cursor = 'pointer';
        const clave = t.titulo + '|' + t.detalle;
        if (clave !== ultima) {
          ultima = clave;
          globito.setHTML(`<b>${SOS.escapar(t.titulo)}</b>${t.detalle ? `<span>${SOS.escapar(t.detalle)}</span>` : ''}`);
        }
        globito.setLngLat(e.lngLat).addTo(mapa);
      });
    });
    mapa.on('mouseout', quitar);
    mapa.on('movestart', quitar);
    mapa.on('click', quitar);
  }

  // ── Vista 3D ──────────────────────────────────────────────────────────────
  // Relieve del terreno y edificios con altura. Se enciende a pedido, porque pesa más.
  // La cota sale de las teselas propias que publica /mapas (DTM de 1 m de la SGIAR en
  // Santa Cruz y Copernicus en el resto; sosgalapagos-datos, 37_teselas_relieve3d.py).
  // Si todavía no están publicadas, se usa Terrain Tiles (AWS), de unos 30 m.
  // La exageración multiplica la altura del terreno. Santa Cruz es de pendiente suave: con
  // menos de ×2 casi no se nota el relieve. Se puede subir y bajar con los controles.
  const RELIEVE = { exageracion: 2.4, minima: 1, maxima: 4, paso: 0.4, inclinacion: 64 };
  let exageracion = RELIEVE.exageracion;
  let en3d = false, cota = null;
  async function fuenteDeCota() {
    if (cota) return cota;
    // Primero el relieve que sirve la propia plataforma; si no está, el que publique /mapas.
    for (const base of [cfg.relieveUrl, `${cfg.capasUrl}teselas/relieve3d/`]) {
      try {
        const t = await fetch(SOS.capas.conV(base + 'teselas.json')).then((r) => (r.ok ? r.json() : null));
        if (t && t.cota && t.cota.codificacion === 'terrarium') {
          const [[sur, oeste], [norte, este]] = t.limites;
          return (cota = {
            type: 'raster-dem', encoding: 'terrarium', tileSize: 256,
            tiles: [SOS.capas.conV(location.origin + base + t.cota.url)], minzoom: t.cota.zoom_min, maxzoom: t.cota.zoom_max,
            bounds: [oeste, sur, este, norte], attribution: t.atribucion,
          });
        }
      } catch (e) { /* se prueba la siguiente fuente */ }
    }
    return (cota = {
      type: 'raster-dem', encoding: 'terrarium', tileSize: 256, maxzoom: 14,
      tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
      attribution: 'Relieve: Terrain Tiles (Mapzen, AWS)',
    });
  }
  async function alternar3d() {
    en3d = !en3d;
    document.getElementById('relieve').setAttribute('aria-pressed', String(en3d));
    document.getElementById('controles3d').hidden = !en3d;
    document.body.classList.toggle('en-3d', en3d);
    if (en3d) {
      const fuente = await fuenteDeCota();
      if (!en3d) return; // se apagó mientras cargaba
      if (!mapa.getSource('elevacion')) mapa.addSource('elevacion', fuente);
      mapa.setTerrain({ source: 'elevacion', exaggeration: exageracion });
      // Sombreado para que el relieve se lea. Usa su propia fuente, como pide MapLibre.
      if (!mapa.getSource('elevacion-sombras')) mapa.addSource('elevacion-sombras', Object.assign({}, fuente, { attribution: '' }));
      if (!mapa.getLayer('sombras-3d')) {
        mapa.addLayer({
          id: 'sombras-3d', type: 'hillshade', source: 'elevacion-sombras',
          paint: { 'hillshade-exaggeration': 0.45, 'hillshade-shadow-color': '#5b6166', 'hillshade-highlight-color': '#ffffff', 'hillshade-accent-color': '#8a9095' },
        }, 'ancla-raster');
      }
      if (!mapa.getLayer('edificios-3d')) {
        mapa.addLayer({
          id: 'edificios-3d', type: 'fill-extrusion', source: 'base', 'source-layer': 'buildings', minzoom: 15,
          paint: {
            'fill-extrusion-color': '#d6d5d1', 'fill-extrusion-opacity': 0.9,
            'fill-extrusion-height': ['coalesce', ['get', 'height'], 4],
            'fill-extrusion-base': ['coalesce', ['get', 'min_height'], 0],
          },
        }, 'ancla-raster');
      }
      mapa.dragRotate.enable();
      mapa.touchZoomRotate.enableRotation();
      mapa.easeTo({ pitch: RELIEVE.inclinacion, bearing: mapa.getBearing() || -18, duration: 900 });
    } else {
      mapa.easeTo({ pitch: 0, bearing: 0, duration: 600 });
      mapa.setTerrain(null);
      for (const id of ['edificios-3d', 'sombras-3d']) if (mapa.getLayer(id)) mapa.removeLayer(id);
      mapa.dragRotate.disable();
      mapa.touchZoomRotate.disableRotation();
    }
  }
  document.getElementById('relieve').addEventListener('click', alternar3d);

  // Controles del 3D: girar, volver al norte, inclinar y exagerar el relieve.
  const marcarExageracion = () => {
    document.getElementById('exageracion').textContent = '×' + exageracion.toFixed(1).replace('.', ',');
  };
  marcarExageracion();
  document.getElementById('controles3d').addEventListener('click', (e) => {
    const b = e.target.closest('[data-3d]');
    if (!b || !en3d) return;
    const hacer = b.dataset['3d'];
    if (hacer === 'girar-izq') mapa.easeTo({ bearing: mapa.getBearing() - 30, duration: 350 });
    if (hacer === 'girar-der') mapa.easeTo({ bearing: mapa.getBearing() + 30, duration: 350 });
    if (hacer === 'norte') mapa.easeTo({ bearing: 0, duration: 400 });
    if (hacer === 'inclinar-mas') mapa.easeTo({ pitch: Math.min(mapa.getMaxPitch(), mapa.getPitch() + 10), duration: 300 });
    if (hacer === 'inclinar-menos') mapa.easeTo({ pitch: Math.max(0, mapa.getPitch() - 10), duration: 300 });
    if (hacer === 'relieve-mas' || hacer === 'relieve-menos') {
      const d = hacer === 'relieve-mas' ? RELIEVE.paso : -RELIEVE.paso;
      exageracion = Math.round(Math.min(RELIEVE.maxima, Math.max(RELIEVE.minima, exageracion + d)) * 10) / 10;
      mapa.setTerrain({ source: 'elevacion', exaggeration: exageracion });
      marcarExageracion();
    }
  });
  // La «N» gira con el mapa: señala siempre el norte.
  mapa.on('rotate', () => { document.getElementById('brujula').style.transform = `rotate(${-mapa.getBearing()}deg)`; });

  // ── Arranque ──────────────────────────────────────────────────────────────
  mapa.on('load', async () => {
    // En el teléfono la atribución arranca plegada (se abre con su botón «i»).
    if (SOS.esMovil()) document.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
    await cargarIconos();
    ponerCapasDeReportes();
    await traerReportes(true);
    SOS.capas.iniciar(mapa);

    mapa.on('click', 'reportes-pin', (e) => { e.preventDefault(); abrirFicha(e.features[0].properties.id); });
    mapa.on('click', 'reportes-grupo', async (e) => {
      e.preventDefault();
      const f = e.features[0];
      const zoom = await mapa.getSource('reportes').getClusterExpansionZoom(f.properties.cluster_id);
      mapa.easeTo({ center: f.geometry.coordinates, zoom });
    });
    mapa.on('click', (e) => { if (!e.defaultPrevented) SOS.capas.globo(e); });
    for (const capa of ['reportes-pin', 'reportes-grupo']) {
      mapa.on('mouseenter', capa, () => (mapa.getCanvas().style.cursor = 'pointer'));
      mapa.on('mouseleave', capa, () => (mapa.getCanvas().style.cursor = ''));
    }
    mapa.on('moveend', alMover);
    mapa.on('idle', actualizarVacio);

    // Enlace directo a un reporte: /riesgos/?r=<id>
    const id = new URLSearchParams(location.search).get('r');
    if (id) {
      const f = coleccion.features.find((x) => x.properties.id === id);
      if (f) centrarEn(f.geometry.coordinates, 17);
      abrirFicha(id);
    }

    setInterval(() => { if (!document.hidden) traerReportes(); }, SONDEO_MS);
    setInterval(pintarReportes, 60000); // el desteñido avanza cada minuto
    document.addEventListener('visibilitychange', () => { if (!document.hidden) traerReportes(); });
  });

  // Si el teléfono no puede dibujar el mapa, se dice en vez de dejar la pantalla vacía.
  mapa.on('error', (e) => {
    if (e && e.error && /webgl/i.test(String(e.error.message))) {
      document.getElementById('mapa').innerHTML = '<p style="padding:24px">Este teléfono no puede mostrar el mapa. Abajo está la lista de reportes.</p>';
      abrirHoja(true);
    }
  });
})();
