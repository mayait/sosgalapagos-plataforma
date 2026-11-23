/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito. */
/* Buscador y «Mis puntos».

   Buscador: la lupa junto a «Capas». Busca calles, barrios, lugares, cruces y puntos de los
   estudios, además de islas y coordenadas. Lo que se puede buscar lo dice el manifiesto de
   capas (clave «buscar»); cada archivo se baja la primera vez que alguien busca.

   Mis puntos: marcas propias de cada persona. Se guardan solo en su navegador (localStorage)
   y nunca se envían al servidor. Usan la misma clave y el mismo formato que el visor anterior
   de /mapas, así que quien tenía puntos guardados allí los sigue viendo aquí. */
(function () {
  'use strict';
  const SOS = window.SOS;
  const x = (v) => SOS.escapar(v);
  const sinTildes = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  let mapa = null;

  // ── Buscador ──────────────────────────────────────────────────────────────
  let indice = null, resultados = [], elegido = -1, marca = null;

  function cajaDe(geometria) {
    const b = [Infinity, Infinity, -Infinity, -Infinity];
    (function recorrer(c) {
      if (typeof c[0] === 'number') {
        b[0] = Math.min(b[0], c[0]); b[1] = Math.min(b[1], c[1]); b[2] = Math.max(b[2], c[0]); b[3] = Math.max(b[3], c[1]);
      } else c.forEach(recorrer);
    })(geometria.coordinates);
    return b;
  }

  function construirIndice() {
    if (indice) return indice;
    indice = (async () => {
      const m = SOS.capas.manifiesto() || {};
      const salida = [];
      for (const [nombre, v] of Object.entries(m.islas || {})) {
        const b = v.bounds; // [[lat, lon], [lat, lon]]
        salida.push({ n: sinTildes(nombre), texto: sinTildes(nombre), nombre, tipo: 'Isla o poblado', detalle: '', caja: [b[0][1], b[0][0], b[1][1], b[1][0]] });
      }
      await Promise.all((m.buscar || []).map(async (b) => {
        let gj;
        try { gj = await fetch(SOS.capas.conV(SOS.capas.datos() + b.archivo)).then((r) => (r.ok ? r.json() : null)); } catch (e) { return; }
        if (!gj || !gj.features) return;
        const grupos = new Map();
        for (const f of gj.features) {
          if (!f.geometry) continue;
          const p = f.properties || {};
          const nombre = b.campos.map((c) => p[c]).find((v) => v != null && v !== '' && v !== '(sin nombre)');
          if (!nombre) continue;
          const detalle = (b.detalle || []).map((c) => p[c]).filter((v) => v && v !== nombre && v !== '(sin nombre)').join(' · ');
          const texto = sinTildes(b.campos.map((c) => p[c] ?? '').join(' ') + ' ' + detalle);
          // Una calle viene partida en tramos: se juntan en un solo resultado por nombre e isla.
          const clave = b.agrupar ? nombre + '|' + (p.isla ?? '') : Symbol('uno');
          const caja = cajaDe(f.geometry);
          const g = grupos.get(clave);
          if (g) {
            g.caja = [Math.min(g.caja[0], caja[0]), Math.min(g.caja[1], caja[1]), Math.max(g.caja[2], caja[2]), Math.max(g.caja[3], caja[3])];
            g.elementos.push(f);
          } else {
            grupos.set(clave, { n: sinTildes(nombre), texto, nombre: String(nombre), tipo: b.tipo, detalle, caja, elementos: [f], punto: f.geometry.type === 'Point' });
          }
        }
        const vistos = new Set(); // mismo nombre y detalle: un solo resultado
        for (const g of grupos.values()) {
          const k = g.n + '|' + g.tipo + '|' + g.detalle;
          if (!vistos.has(k)) { vistos.add(k); salida.push(g); }
        }
      }));
      return salida;
    })();
    return indice;
  }

  // Acepta «-0.7430, -90.3097», con coma decimal («-0,7430 -90,3097») y también lon, lat.
  function coordenadas(q) {
    const s = q.trim();
    let m = s.match(/^(-?\d+),(\d+)\s*[;,]?\s+(-?\d+),(\d+)$/);
    let a, b;
    if (m) { a = +(m[1] + '.' + m[2]); b = +(m[3] + '.' + m[4]); } else {
      m = s.match(/^(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)$/);
      if (!m) return null;
      a = +m[1]; b = +m[2];
    }
    if (Math.abs(a) > 60 && Math.abs(b) <= 10) [a, b] = [b, a];
    if (Math.abs(a) > 90 || Math.abs(b) > 180) return null;
    return { lat: a, lng: b };
  }

  const ORDEN_TIPO = { 'Isla o poblado': 0, Barrio: 1, Calle: 2, Lugar: 3 };
  function puntuar(e, t, palabras) {
    const n = e.n, trozos = n.split(/[\s.,\-–()]+/);
    if (n === t) return 0;
    if (n.startsWith(t)) return 1;
    if ((' ' + n).includes(' ' + t)) return 2;
    if (palabras.every((w) => trozos.some((z) => z.startsWith(w)))) return 3;
    if (n.includes(t)) return 4;
    if (palabras.every((w) => e.texto.includes(w) || n.includes(w))) return 5;
    return 9;
  }

  const el = (id) => document.getElementById(id);
  let turno = 0;
  async function buscar(q) {
    const ul = el('buscar-resultados');
    const mio = ++turno;
    elegido = -1;
    if (!q.trim()) { ul.hidden = true; resultados = []; return; }
    const ll = coordenadas(q);
    if (ll) {
      resultados = [{ nombre: `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}`, tipo: 'Coordenadas', detalle: '', lngLat: [ll.lng, ll.lat], punto: true }];
    } else {
      if (!ul.children.length) { ul.innerHTML = '<li class="vacio">Buscando…</li>'; ul.hidden = false; }
      const idx = await construirIndice();
      if (mio !== turno) return; // ya se escribió otra cosa
      const t = sinTildes(q), palabras = t.split(/\s+/).filter(Boolean);
      const orden = (e) => ORDEN_TIPO[e.tipo] ?? 4;
      resultados = idx.map((e) => [puntuar(e, t, palabras), e]).filter(([s]) => s < 9)
        .sort((a, b) => a[0] - b[0] || orden(a[1]) - orden(b[1]) || a[1].nombre.length - b[1].nombre.length)
        .slice(0, 12).map(([, e]) => e);
    }
    ul.innerHTML = resultados.length
      ? resultados.map((r, i) => `<li role="option" data-i="${i}"><span>${x(r.nombre)}</span><small>${x(r.tipo)}${r.detalle ? ' · ' + x(r.detalle) : ''}</small></li>`).join('')
      : '<li class="vacio">Sin resultados. Prueba con otro nombre o con coordenadas (lat, lon).</li>';
    ul.hidden = false;
  }

  function resaltar(r) {
    const datos = { type: 'FeatureCollection', features: r.elementos && !r.punto ? r.elementos : [] };
    if (mapa.getSource('busqueda')) mapa.getSource('busqueda').setData(datos);
    else {
      mapa.addSource('busqueda', { type: 'geojson', data: datos });
      mapa.addLayer({ id: 'busqueda-area', type: 'fill', source: 'busqueda', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#0b5cad', 'fill-opacity': 0.08 } });
      mapa.addLayer({ id: 'busqueda-linea', type: 'line', source: 'busqueda', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#0b5cad', 'line-width': 7, 'line-opacity': 0.55 } });
    }
  }
  function quitarResultado() {
    if (marca) { marca.remove(); marca = null; }
    if (mapa.getSource('busqueda')) mapa.getSource('busqueda').setData({ type: 'FeatureCollection', features: [] });
  }

  // La marca de una calle va sobre la calle: el vértice más cercano al centro de su caja.
  function sobreElTrazo(elementos, centro) {
    let mejor = centro, minima = Infinity;
    for (const f of elementos || []) {
      if (!/LineString/.test(f.geometry.type)) return centro; // un área se marca en su centro
      (function recorrer(c) {
        if (typeof c[0] !== 'number') { c.forEach(recorrer); return; }
        const d = (c[0] - centro[0]) ** 2 + (c[1] - centro[1]) ** 2;
        if (d < minima) { minima = d; mejor = [c[0], c[1]]; }
      })(f.geometry.coordinates);
    }
    return mejor;
  }

  function ir(r) {
    if (!r) return;
    el('buscar-resultados').hidden = true;
    el('buscar-texto').blur();
    quitarResultado();
    resaltar(r);
    let centro = r.lngLat;
    if (!centro && r.punto) centro = r.elementos[0].geometry.coordinates;
    const abajo = SOS.esMovil() ? 110 : 0;
    if (centro) mapa.easeTo({ center: centro, zoom: Math.max(mapa.getZoom(), 17), padding: { bottom: abajo }, duration: 600 });
    else {
      const c = r.caja;
      mapa.fitBounds([[c[0], c[1]], [c[2], c[3]]], { maxZoom: 17, padding: { top: 70, bottom: abajo + 40, left: 40, right: 40 }, duration: 600 });
      centro = sobreElTrazo(r.elementos, [(c[0] + c[2]) / 2, (c[1] + c[3]) / 2]);
    }
    if (r.tipo === 'Isla o poblado') return; // una isla no lleva marca
    const caja = document.createElement('div');
    caja.className = 'marca-busqueda';
    marca = new maplibregl.Marker({ element: caja, anchor: 'bottom' }).setLngLat(centro)
      .setPopup(new maplibregl.Popup({ className: 'aqui', offset: 30, maxWidth: '240px' }).setHTML(
        `<b class="globo-titulo">${x(r.nombre)}</b><small class="globo-tipo">${x(r.tipo)}${r.detalle ? ' · ' + x(r.detalle) : ''}</small>`
        + `<button type="button" class="enlace-boton" data-guardar-punto="${centro[1]},${centro[0]}" data-nombre="${x(r.tipo === 'Coordenadas' ? '' : r.nombre)}">Guardar en mis puntos</button>`))
      .addTo(mapa);
    marca.togglePopup();
  }

  function abrirBuscador() {
    el('buscar').hidden = false;
    el('buscar-abrir').hidden = true;
    document.body.classList.add('buscando');
    el('buscar-texto').focus();
    construirIndice(); // se adelanta la descarga mientras la persona escribe
  }
  function cerrarBuscador() {
    el('buscar').hidden = true;
    el('buscar-abrir').hidden = false;
    document.body.classList.remove('buscando');
    el('buscar-texto').value = '';
    el('buscar-resultados').hidden = true;
    quitarResultado();
  }

  function iniciarBuscador() {
    const campo = el('buscar-texto'), ul = el('buscar-resultados');
    el('buscar-abrir').addEventListener('click', abrirBuscador);
    el('buscar-cerrar').addEventListener('click', cerrarBuscador);
    let espera;
    campo.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(() => buscar(campo.value), 140); });
    campo.addEventListener('focus', () => { if (resultados.length) ul.hidden = false; });
    campo.addEventListener('keydown', (e) => {
      const filas = ul.querySelectorAll('li[data-i]');
      if (e.key === 'Escape') { cerrarBuscador(); return; }
      if (e.key === 'Enter') { e.preventDefault(); ir(resultados[Math.max(elegido, 0)]); return; }
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      e.preventDefault();
      if (!filas.length) return;
      elegido = (elegido + (e.key === 'ArrowDown' ? 1 : -1) + filas.length) % filas.length;
      filas.forEach((li, i) => li.classList.toggle('elegido', i === elegido));
      filas[elegido].scrollIntoView({ block: 'nearest' });
    });
    ul.addEventListener('click', (e) => {
      const li = e.target.closest('li[data-i]');
      if (li) ir(resultados[+li.dataset.i]);
    });
  }

  // ── Mis puntos ────────────────────────────────────────────────────────────
  const CLAVE = 'sosgalapagos-mapas-mis-puntos-v1'; // la misma del visor anterior de /mapas
  const MAXIMO = 300, LARGO_NOMBRE = 60, LARGO_NOTA = 280;
  let mios = [], seGuarda = true;
  const marcas = new Map();
  const idNuevo = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

  function limpiar(p) {
    const lat = +(p && p.lat), lng = +(p && p.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
    return {
      id: String(p.id || idNuevo()).slice(0, 40), lat, lng,
      nombre: String(p.nombre ?? '').slice(0, LARGO_NOMBRE), nota: String(p.nota ?? '').slice(0, LARGO_NOTA),
      creado: String(p.creado ?? new Date().toISOString()).slice(0, 30),
    };
  }
  function leer() {
    try {
      const a = JSON.parse(localStorage.getItem(CLAVE) || '[]');
      return Array.isArray(a) ? a.map(limpiar).filter(Boolean).slice(0, MAXIMO) : [];
    } catch (e) { seGuarda = false; return []; }
  }
  function guardar() {
    try { localStorage.setItem(CLAVE, JSON.stringify(mios)); seGuarda = true; } catch (e) { seGuarda = false; }
    pintarLista();
  }

  function marcar(p) {
    const caja = document.createElement('button');
    caja.type = 'button';
    caja.className = 'mi-punto';
    caja.innerHTML = '<i></i><span></span>';
    const m = new maplibregl.Marker({ element: caja, anchor: 'bottom', draggable: true }).setLngLat([p.lng, p.lat]).addTo(mapa);
    let arrastrado = false;
    m.on('dragstart', () => { arrastrado = true; });
    m.on('dragend', () => {
      const ll = m.getLngLat();
      p.lat = +ll.lat.toFixed(6); p.lng = +ll.lng.toFixed(6);
      guardar();
      setTimeout(() => { arrastrado = false; }, 0);
    });
    caja.addEventListener('click', (e) => { e.stopPropagation(); if (!arrastrado) abrirPunto(p.id); });
    marcas.set(p.id, m);
    rotular(p);
  }
  function rotular(p) {
    const m = marcas.get(p.id);
    if (!m) return;
    m.getElement().querySelector('span').textContent = p.nombre;
    m.getElement().setAttribute('aria-label', p.nombre ? `Mi punto: ${p.nombre}` : 'Mi punto');
  }

  function agregar(lat, lng, nombre) {
    if (mios.length >= MAXIMO) { window.alert(`Máximo ${MAXIMO} puntos. Borra alguno o expórtalos.`); return; }
    const p = limpiar({ lat: +(+lat).toFixed(6), lng: +(+lng).toFixed(6), nombre: nombre || '' });
    if (!p) return;
    mios.push(p);
    marcar(p);
    guardar();
    abrirPunto(p.id);
  }

  function abrirPunto(id) {
    const p = mios.find((q) => q.id === id);
    if (!p) return;
    SOS.mostrarDetalle(`
      <div class="mi-ficha" data-mi-punto="${x(p.id)}">
        <button class="ficha-volver" type="button" data-cerrar-ficha>← Volver a la lista</button>
        <h2>Mi punto</h2>
        <p class="mi-coordenadas">${p.lat.toFixed(5)}, ${p.lng.toFixed(5)} · arrastra la marca para moverla</p>
        <label>Nombre<input type="text" data-campo="nombre" maxlength="${LARGO_NOMBRE}" value="${x(p.nombre)}" placeholder="Por ejemplo: casa de mi abuela"></label>
        <label>Nota<textarea data-campo="nota" maxlength="${LARGO_NOTA}" rows="3" placeholder="Lo que quieras recordar de este lugar">${x(p.nota)}</textarea></label>
        <p class="mi-privado">${seGuarda ? 'Se guarda solo en este navegador. No se envía a nadie ni aparece en el mapa de los demás.' : 'Este navegador no deja guardar: el punto se perderá al cerrar la página. Expórtalo si lo necesitas.'}</p>
        <div class="mi-acciones">
          <a class="boton" href="${SOS.cfg.reportar}?lat=${p.lat.toFixed(6)}&lon=${p.lng.toFixed(6)}">Reportar aquí</a>
          <button type="button" class="boton" data-borrar-punto>Borrar punto</button>
        </div>
      </div>`, [p.lng, p.lat]);
  }

  function exportar() {
    const gj = {
      type: 'FeatureCollection',
      features: mios.map((p) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [p.lng, p.lat] }, properties: { nombre: p.nombre, nota: p.nota, creado: p.creado } })),
    };
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(gj, null, 1)], { type: 'application/geo+json' }));
    a.download = `mis-puntos-${new Date().toISOString().slice(0, 10)}.geojson`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }

  function pintarLista() {
    const caja = el('mis-puntos');
    if (!caja) return;
    if (!mios.length) {
      caja.innerHTML = '<p class="mis-ayuda">Para guardar un lugar propio, mantén pulsado el mapa (o clic derecho) y elige «Guardar en mis puntos».</p>';
      return;
    }
    caja.innerHTML = `
      <h2 class="mis-titulo">Mis puntos <small>${mios.length} · solo en este navegador</small></h2>
      <ul class="mis-lista">${mios.map((p) => `<li><button type="button" data-ver-punto="${x(p.id)}"><i></i>${x(p.nombre || `${p.lat.toFixed(4)}, ${p.lng.toFixed(4)}`)}</button></li>`).join('')}</ul>
      <button type="button" class="enlace-boton" data-exportar-puntos>Descargar mis puntos (GeoJSON)</button>`;
  }

  function iniciarPuntos() {
    mios = leer();
    mios.forEach(marcar);
    pintarLista();
    document.body.addEventListener('click', (e) => {
      const g = e.target.closest('[data-guardar-punto]');
      if (g) {
        const [lat, lng] = g.dataset.guardarPunto.split(',');
        document.querySelectorAll('.maplibregl-popup.aqui').forEach((n) => n.remove());
        quitarResultado();
        agregar(lat, lng, g.dataset.nombre);
        return;
      }
      const v = e.target.closest('[data-ver-punto]');
      if (v) { abrirPunto(v.dataset.verPunto); return; }
      if (e.target.closest('[data-exportar-puntos]')) { exportar(); return; }
      if (e.target.closest('[data-borrar-punto]')) {
        const ficha = e.target.closest('[data-mi-punto]');
        const id = ficha.dataset.miPunto;
        if (!window.confirm('¿Borrar este punto? No se puede deshacer.')) return;
        mios = mios.filter((p) => p.id !== id);
        const m = marcas.get(id);
        if (m) { m.remove(); marcas.delete(id); }
        guardar();
        ficha.querySelector('[data-cerrar-ficha]').click();
      }
    });
    document.body.addEventListener('input', (e) => {
      const campo = e.target.closest('[data-mi-punto] [data-campo]');
      if (!campo) return;
      const p = mios.find((q) => q.id === campo.closest('[data-mi-punto]').dataset.miPunto);
      if (!p) return;
      p[campo.dataset.campo] = campo.value;
      rotular(p);
      guardar();
    });
    // Si la persona cambia sus puntos en otra pestaña, esta se pone al día.
    window.addEventListener('storage', (e) => {
      if (e.key !== CLAVE) return;
      marcas.forEach((m) => m.remove());
      marcas.clear();
      mios = leer();
      mios.forEach(marcar);
      pintarLista();
    });
  }

  SOS.buscador = {
    iniciar(m) {
      mapa = m;
      iniciarBuscador();
      iniciarPuntos();
    },
  };
})();
