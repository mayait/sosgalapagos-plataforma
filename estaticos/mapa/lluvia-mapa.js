/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
 * Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
 * Único original: el panel de /clima/ (repositorio de datos) carga este mismo archivo. */
/* Mapa de lluvia y viento de modelos, al estilo de Windy, para el panel de /clima/.
 *
 * Lee el JSON que escribe la plataforma (clima/lluvia_mapa.py → datos/lluvia-mapa.json): una rejilla
 * regular con la lluvia cada 3 h y el viento a 10 m de varios modelos, un byte por celda.
 * Dibuja la lluvia interpolada en un canvas (bilineal en el espacio, lineal en el tiempo), una línea
 * de tiempo con reproducción y, si se quiere, partículas de viento en un canvas propio.
 *
 * Es lluvia de MODELO, no medida ni oficial, y los modelos globales se quedan muy cortos en las islas.
 * El mapa lo dice a la vista («Lluvia de modelos» y cuánto subestima); el aviso general de cada página dice que no es oficial.
 *
 * Uso:
 *   <link rel="stylesheet" href="lluvia-mapa.css"><script src="lluvia-mapa.js"></script>
 *   LluviaMapa.montar(document.getElementById("lluvia"), {datos: "datos/lluvia-mapa.json"});
 * Necesita Leaflet 1.9 (window.L). Si no está, lo carga de cdnjs; con `leaflet: () => Promise<L>` se usa otro cargador.
 *
 * Reel (la portada): las próximas 24 horas animadas solas, sin controles, con el reloj, los puertos y la hora
 * de más lluvia en cada isla. Es el mapa del reel del clima (repositorio de datos, clima/reel/) hecho en vivo:
 *   LluviaMapa.reel(caja, {datos: "/riesgos/api/clima/lluvia-mapa.json?horas=24", islas: "islas.json"});
 * Devuelve null, sin tocar lo que haya en la caja, si los datos no cargan o ya no cubren las próximas horas.
 */
(function () {
  "use strict";

  const ZONA = "Pacific/Galapagos"; // UTC−6, sin horario de verano
  const LEAFLET = ["https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
                   "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"];
  const SUBMUESTREO = 8;      // píxeles del canvas por celda de la rejilla
  const SEG_POR_CUADRO = 0.9; // al reproducir: segundos por cada 3 h

  // Paletas (valor, [r, g, b, a]) sobre fondo claro: azul → verde → amarillo → naranja → rojo → magenta → morado oscuro.
  // La lluvia débil arranca en un azul con cuerpo y lo más intenso termina oscuro, para que ambos se lean sobre el mapa claro.
  const PALETAS = {
    hora: {unidad: "mm/h · prom. 3 h", marcas: [1, 3, 10, 20, 40], max: 60, paradas: [
      [0.1, [95, 155, 230, 0]], [0.3, [95, 155, 230, 140]], [0.7, [60, 120, 220, 185]], [1.5, [40, 90, 205, 210]],
      [3, [40, 175, 205, 210]], [5, [55, 190, 95, 220]], [8, [235, 220, 55, 230]], [13, [245, 150, 40, 235]],
      [20, [230, 55, 45, 240]], [32, [205, 40, 150, 245]], [50, [130, 50, 200, 250]], [60, [70, 20, 110, 250]]]},
    dia: {unidad: "mm en 24 h", marcas: [5, 20, 50, 100, 150], max: 200, paradas: [
      [0.5, [95, 155, 230, 0]], [1.5, [95, 155, 230, 140]], [4, [60, 120, 220, 185]], [8, [40, 90, 205, 210]],
      [14, [40, 175, 205, 210]], [22, [55, 190, 95, 220]], [35, [235, 220, 55, 230]], [55, [245, 150, 40, 235]],
      [80, [230, 55, 45, 240]], [115, [205, 40, 150, 245]], [160, [130, 50, 200, 250]], [200, [70, 20, 110, 250]]]},
  };
  // El reel usa la paleta «por hora» con la lluvia extrema (más de 20 mm/h) en rojo oscuro: en las piezas de la marca no hay morado.
  PALETAS.reel = {max: 60, paradas: PALETAS.hora.paradas.slice(0, 9).concat([[32, [181, 22, 28, 245]], [50, [130, 14, 20, 250]], [60, [90, 8, 14, 250]]])};
  const N_LUT = 512;
  const ENCUADRE_PUERTOS = [[-1.1, -91.5], [-0.3, -89.2]];  // el sur de Isabela, Santa Cruz y San Cristóbal

  // Escala de la paleta: raíz cuadrada (como la codificación), para dar detalle a la lluvia débil.
  const aEscala = (v, max) => Math.sqrt(Math.max(0, v) / max);

  function tabla(p) {
    const lut = new Uint8ClampedArray(N_LUT * 4);
    for (let i = 0; i < N_LUT; i++) {
      const v = Math.pow(i / (N_LUT - 1), 2) * p.max;
      let k = 0;
      while (k < p.paradas.length - 1 && p.paradas[k + 1][0] < v) k++;
      const [v0, c0] = p.paradas[k], [v1, c1] = p.paradas[Math.min(k + 1, p.paradas.length - 1)];
      const f = v <= v0 ? 0 : v1 === v0 ? 1 : Math.min(1, (v - v0) / (v1 - v0));
      for (let c = 0; c < 4; c++) lut[i * 4 + c] = v < p.paradas[0][0] ? 0 : c0[c] + (c1[c] - c0[c]) * f;
    }
    return lut;
  }
  Object.values(PALETAS).forEach(p => { p.lut = tabla(p); });

  // ── Formatos de hora (siempre en hora de Galápagos) ──────────────────────
  const fHora = new Intl.DateTimeFormat("es-EC", {timeZone: ZONA, hour: "2-digit", minute: "2-digit", hourCycle: "h23"});
  const fDia = new Intl.DateTimeFormat("es-EC", {timeZone: ZONA, weekday: "short", day: "numeric", month: "short"});
  const fDiaCorto = new Intl.DateTimeFormat("es-EC", {timeZone: ZONA, weekday: "short", day: "numeric"});
  const fCorrida = new Intl.DateTimeFormat("es-EC", {timeZone: ZONA, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23"});
  const diaLocal = t => new Date(t - 6 * 3600e3).toISOString().slice(0, 10);
  const num = (v, d = 1) => v.toLocaleString("es-EC", {maximumFractionDigits: d, minimumFractionDigits: 0});
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const PUNTOS_CARDINALES = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"];

  function cargarLeaflet() {
    if (window.L && window.L.version) return Promise.resolve(window.L);
    return new Promise((ok, mal) => {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = LEAFLET[1]; document.head.appendChild(css);
      const s = document.createElement("script");
      s.src = LEAFLET[0]; s.onload = () => ok(window.L); s.onerror = () => mal(new Error("No se pudo cargar Leaflet"));
      document.head.appendChild(s);
    });
  }

  // ── Datos ────────────────────────────────────────────────────────────────
  function decodificar(b64) {
    const s = atob(b64), a = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);
    return a;
  }

  class Datos {
    constructor(j) {
      this.j = j;
      this.g = j.rejilla;
      this.n = this.g.nlat * this.g.nlon;
      this.horas = j.horas.map(h => Date.parse(h));
      this.cache = new Map();
    }
    modelo(id) { return this.j.modelos.find(m => m.id === id) || this.j.modelos[0]; }
    // mm en las 3 h que terminan en horas[i] (NaN = sin dato)
    lluvia3h(id, i) {
      const k = "l" + id + i;
      if (!this.cache.has(k)) {
        const b = decodificar(this.modelo(id).lluvia[i]), a = new Float32Array(this.n);
        for (let c = 0; c < this.n; c++) a[c] = b[c] === 255 ? NaN : (b[c] / 10) ** 2;
        this.cache.set(k, a);
      }
      return this.cache.get(k);
    }
    // mm/h promedio del periodo de 3 h
    porHora(id, i) {
      const k = "h" + id + i;
      if (!this.cache.has(k)) {
        const a = this.lluvia3h(id, i), r = new Float32Array(this.n);
        for (let c = 0; c < this.n; c++) r[c] = a[c] / 3;
        this.cache.set(k, r);
      }
      return this.cache.get(k);
    }
    // mm en las 24 h que terminan en horas[i] (los 8 periodos de 3 h)
    acumulado24(id, i) {
      const k = "d" + id + i;
      if (!this.cache.has(k)) {
        const r = new Float32Array(this.n);
        for (let j = Math.max(0, i - 7); j <= i; j++) {
          const a = this.lluvia3h(id, j);
          for (let c = 0; c < this.n; c++) r[c] += a[c];
        }
        this.cache.set(k, r);
      }
      return this.cache.get(k);
    }
    viento(id, i) {
      const k = "v" + id + i;
      if (!this.cache.has(k)) {
        const m = this.modelo(id), bu = decodificar(m.u[i]), bv = decodificar(m.v[i]);
        const u = new Float32Array(this.n), v = new Float32Array(this.n);
        for (let c = 0; c < this.n; c++) {
          u[c] = bu[c] === 255 ? 0 : (bu[c] - 128) / 4;
          v[c] = bv[c] === 255 ? 0 : (bv[c] - 128) / 4;
        }
        this.cache.set(k, [u, v]);
      }
      return this.cache.get(k);
    }
  }

  // Interpolación lineal entre dos campos
  function mezclar(a, b, f, destino) {
    if (f <= 0 || a === b) { destino.set(a); return destino; }
    for (let c = 0; c < a.length; c++) destino[c] = a[c] + (b[c] - a[c]) * f;
    return destino;
  }

  // Valor bilineal en coordenadas de rejilla (x: columna, y: fila desde el norte)
  function muestrear(campo, nlon, nlat, x, y) {
    if (x < 0 || y < 0 || x > nlon - 1 || y > nlat - 1) return NaN;
    const x0 = Math.min(Math.floor(x), nlon - 2), y0 = Math.min(Math.floor(y), nlat - 2);
    const fx = x - x0, fy = y - y0, i = y0 * nlon + x0;
    return (campo[i] * (1 - fx) + campo[i + 1] * fx) * (1 - fy) + (campo[i + nlon] * (1 - fx) + campo[i + nlon + 1] * fx) * fy;
  }

  // ── Piezas que comparten el mapa completo y el reel ─────────────────────
  // Lluvia: un canvas pequeño estirado sobre la rejilla. El navegador lo suaviza al ampliarlo.
  // Devuelve pintar(campo, paleta).
  function capaLluvia(L, mapa, g, limites) {
    const W = (g.nlon - 1) * SUBMUESTREO + 1, H = (g.nlat - 1) * SUBMUESTREO + 1;
    const lienzo = document.createElement("canvas");
    lienzo.width = W; lienzo.height = H;
    const ctx = lienzo.getContext("2d");
    const img = ctx.createImageData(W, H);
    const CapaLienzo = L.ImageOverlay.extend({
      _initImage() {
        this._image = this._url;
        L.DomUtil.addClass(this._image, "leaflet-image-layer");
        if (this._zoomAnimated) L.DomUtil.addClass(this._image, "leaflet-zoom-animated");
        L.DomUtil.addClass(this._image, "lm-lluvia");
        this._image.onselectstart = L.Util.falseFn;
        this._image.onmousemove = L.Util.falseFn;
      },
    });
    new CapaLienzo(lienzo, limites, {opacity: 0.88, interactive: false}).addTo(mapa);
    // Desvanece el borde de la rejilla (una celda y media) para que no se vea un rectángulo
    const borde = new Float32Array(W * H), ANCHO = SUBMUESTREO * 1.5;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const d = Math.min(x, y, W - 1 - x, H - 1 - y) / ANCHO;
      borde[y * W + x] = d >= 1 ? 1 : d * d * (3 - 2 * d);
    }
    return function pintar(c, p) {
      const lut = p.lut, px = img.data, nlon = g.nlon;
      for (let y = 0; y < H; y++) {
        const gy = y / SUBMUESTREO, y0 = Math.min(Math.floor(gy), g.nlat - 2), fy = gy - y0;
        for (let x = 0; x < W; x++) {
          const gx = x / SUBMUESTREO, x0 = Math.min(Math.floor(gx), nlon - 2), fx = gx - x0, i = y0 * nlon + x0;
          const v = (c[i] * (1 - fx) + c[i + 1] * fx) * (1 - fy) + (c[i + nlon] * (1 - fx) + c[i + nlon + 1] * fx) * fy;
          const o = (y * W + x) * 4;
          if (!(v > 0)) { px[o + 3] = 0; continue; }
          const k = Math.min(N_LUT - 1, Math.round(aEscala(v, p.max) * (N_LUT - 1))) * 4;
          px[o] = lut[k]; px[o + 1] = lut[k + 1]; px[o + 2] = lut[k + 2]; px[o + 3] = lut[k + 3] * borde[y * W + x];
        }
      }
      ctx.putImageData(img, 0, 0);
    };
  }

  // Partículas de viento en un canvas propio: cada una deja una estela que se desvanece.
  // `ajustes` se puede cambiar después (el reel adapta la rapidez al ancho del mapa).
  function capaViento(mapa, g, op) {
    const ajustes = Object.assign({desvanecer: 0.90, ancho: 1.1, color: "rgba(25,35,55,0.55)", K: 0.22, vida: 90, maximo: 2200, area: 220}, op);
    const cv = document.createElement("canvas");
    cv.className = "lm-particulas";
    mapa.getContainer().appendChild(cv);
    const cx = cv.getContext("2d");
    let parts = [], dpr = 1;
    function nueva() {
      const s = mapa.getSize();
      return {x: Math.random() * s.x, y: Math.random() * s.y, edad: Math.floor(Math.random() * (ajustes.vida - 10))};
    }
    function reiniciar() {
      const s = mapa.getSize();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      cv.width = s.x * dpr; cv.height = s.y * dpr; cv.style.width = s.x + "px"; cv.style.height = s.y + "px";
      cx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.round(Math.min(ajustes.maximo, s.x * s.y / ajustes.area));
      parts = Array.from({length: n}, nueva);
    }
    // Un paso: desvanece lo dibujado y, si `activo`, avanza cada partícula con el viento (u, v) de su celda.
    function paso(u, v, activo) {
      const s = mapa.getSize();
      cx.globalCompositeOperation = "destination-in";
      cx.fillStyle = `rgba(0,0,0,${ajustes.desvanecer})`;
      cx.fillRect(0, 0, s.x, s.y);
      cx.globalCompositeOperation = "source-over";
      if (!activo) return;
      cx.lineWidth = ajustes.ancho;
      cx.strokeStyle = ajustes.color;  // sobre fondo claro, el viento va en tinta
      cx.beginPath();
      const K = ajustes.K; // px por cuadro por cada m/s
      for (const p of parts) {
        const ll = mapa.containerPointToLatLng([p.x, p.y]);
        const gx = (ll.lng - g.oeste) / g.paso, gy = (g.norte - ll.lat) / g.paso;
        const uu = muestrear(u, g.nlon, g.nlat, gx, gy), vv = muestrear(v, g.nlon, g.nlat, gx, gy);
        if (!(uu === uu) || p.edad++ > ajustes.vida) { Object.assign(p, nueva(), {edad: 0}); continue; }
        const nx = p.x + uu * K, ny = p.y - vv * K;
        cx.moveTo(p.x, p.y); cx.lineTo(nx, ny);
        p.x = nx; p.y = ny;
        if (nx < 0 || ny < 0 || nx > s.x || ny > s.y) Object.assign(p, nueva(), {edad: 0});
      }
      cx.stroke();
    }
    return {ajustes, reiniciar, paso, limpiar() { cx.clearRect(0, 0, cv.width, cv.height); }};
  }

  function baseEsri(L, mapa) {
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      {maxNativeZoom: 16, attribution: "Mapa Esri"}).addTo(mapa);
    mapa.createPane("lmEtiquetas").style.zIndex = 460;
    mapa.getPane("lmEtiquetas").style.pointerEvents = "none";
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
      {maxNativeZoom: 16, pane: "lmEtiquetas", opacity: 0.85}).addTo(mapa);
  }

  // ── Componente ───────────────────────────────────────────────────────────
  async function montar(raiz, op = {}) {
    raiz.classList.add("lm");
    raiz.innerHTML = `<div class="lm-mapa"></div>`;
    let L, j;
    try {
      [L, j] = await Promise.all([(op.leaflet || cargarLeaflet)(), fetch(op.datos || "datos/lluvia-mapa.json", {cache: "no-cache"}).then(r => {
        if (!r.ok) throw new Error("HTTP " + r.status); return r.json();
      })]);
    } catch (e) {
      raiz.insertAdjacentHTML("beforeend", `<div class="lm-error">No se pudo cargar el mapa de lluvia de los modelos (${esc(e.message)}).</div>`);
      return null;
    }
    if (!j.modelos || !j.modelos.length) {
      raiz.insertAdjacentHTML("beforeend", `<div class="lm-error">Todavía no hay datos de los modelos.</div>`);
      return null;
    }
    const D = new Datos(j), g = D.g;
    const sur = g.norte - (g.nlat - 1) * g.paso, este = g.oeste + (g.nlon - 1) * g.paso;
    const limites = [[sur, g.oeste], [g.norte, este]];
    const E = {
      modelo: op.modelo && j.modelos.some(m => m.id === op.modelo) ? op.modelo : j.modelos[0].id,
      modo: op.modo === "dia" ? "dia" : "hora",
      viento: op.viento !== false,  // encendido siempre al abrir (lo pidió Julián); se apaga con el botón «Viento»
      t: 0, jugando: false,
    };
    // Cuadro inicial: el periodo de 3 h que contiene «ahora» (o el primero que se muestra)
    const ahora = Date.now();
    const tMin = j.inicio || 0, tMax = D.horas.length - 1;
    let t0 = D.horas.findIndex(h => h > ahora);
    E.t = t0 < tMin || t0 < 0 ? tMin : t0;

    // Mapa
    const divMapa = raiz.querySelector(".lm-mapa");
    const mapa = L.map(divMapa, {zoomControl: false, attributionControl: true,
      minZoom: 6, maxZoom: 12, maxBounds: L.latLngBounds(limites).pad(0.6), zoomSnap: 0.25, worldCopyJump: false});
    mapa.attributionControl.setPrefix(false);
    if (!matchMedia("(pointer: coarse)").matches) L.control.zoom({position: "topright"}).addTo(mapa);
    // Encuadre inicial: las tres islas pobladas, con Puerto Villamil, Puerto Ayora y Puerto Baquerizo
    // Moreno) con sus partes altas. Se puede alejar para ver todo el archipiélago.
    mapa.fitBounds(op.encuadre || ENCUADRE_PUERTOS, {paddingTopLeft: [90, 40], paddingBottomRight: [50, 115]});  // leyenda a la izquierda, botones arriba, línea de tiempo abajo
    baseEsri(L, mapa);
    mapa.attributionControl.addAttribution("Lluvia y viento: Open-Meteo (CC BY 4.0) · ECMWF, NOAA, DWD");

    const pintarLluvia = capaLluvia(L, mapa, g, limites);
    const campo = new Float32Array(D.n);

    function campoActual() {
      const f0 = Math.floor(E.t), f1 = Math.min(f0 + 1, tMax), w = E.t - f0;
      const de = E.modo === "dia" ? D.acumulado24.bind(D) : D.porHora.bind(D);
      return mezclar(de(E.modelo, f0), de(E.modelo, f1), w, campo);
    }

    function pintar() { pintarLluvia(campoActual(), PALETAS[E.modo]); }

    // ── Partículas de viento ──────────────────────────────────────────────
    const viento = capaViento(mapa, g);
    const u = new Float32Array(D.n), v = new Float32Array(D.n);

    function vientoActual() {
      const f0 = Math.floor(E.t), f1 = Math.min(f0 + 1, tMax), w = E.t - f0;
      const [u0, v0] = D.viento(E.modelo, f0), [u1, v1] = D.viento(E.modelo, f1);
      mezclar(u0, u1, w, u); mezclar(v0, v1, w, v);
    }
    function aRejilla(ll) { return [(ll.lng - g.oeste) / g.paso, (g.norte - ll.lat) / g.paso]; }

    // ── Controles ─────────────────────────────────────────────────────────
    const modelos = j.modelos.map(m => `<option value="${esc(m.id)}">${esc(m.nombre)}</option>`).join("");
    raiz.insertAdjacentHTML("beforeend", `
      <div class="lm-caja lm-arriba">
        <div class="lm-caja lm-titulo">Lluvia de modelos</div>
        <div class="lm-caja lm-grupo" role="group" aria-label="Qué lluvia mostrar">
          <button type="button" data-modo="hora">Por hora</button><button type="button" data-modo="dia"><span class="lm-largo">Acumulado </span>24 h</button>
        </div>
        <select class="lm-select" aria-label="Modelo">${modelos}</select>
        <span class="lm-espacio"></span>
        <div class="lm-caja lm-grupo"><button type="button" class="lm-viento" aria-pressed="true" title="Partículas de viento a 10 m">Viento</button></div>
      </div>
      <div class="lm-caja lm-leyenda" aria-hidden="true"><b></b><div class="lm-escala"><canvas width="1" height="150"></canvas><div class="lm-marcas"></div></div></div>
      <div class="lm-caja lm-lectura"></div>
      <div class="lm-caja lm-abajo">
        <div class="lm-tiempo">
          <button type="button" class="lm-play" aria-label="Reproducir"></button>
          <div class="lm-pista">
            <div class="lm-hora"><b></b><span></span></div>
            <input class="lm-rango" type="range" aria-label="Hora del pronóstico">
            <div class="lm-dias"></div>
          </div>
        </div>
        <div class="lm-aviso"></div>
      </div>`);
    const $ = s => raiz.querySelector(s);
    const rango = $(".lm-rango"), play = $(".lm-play"), sel = $(".lm-select"), lectura = $(".lm-lectura");
    sel.value = E.modelo;
    rango.min = tMin; rango.max = tMax; rango.step = 1 / 3; // un paso = una hora
    rango.value = E.t;

    // Marcas de día en la pista
    (function () {
      const dias = $(".lm-dias"), span = D.horas[tMax] - D.horas[tMin];
      let html = "", previo = null;
      for (let h = D.horas[tMin] - 3 * 3600e3; h <= D.horas[tMax]; h += 3600e3) {
        const d = diaLocal(h);
        if (previo && d !== previo) {
          const pct = (h - D.horas[tMin]) / span * 100;
          if (pct >= 0 && pct < 92) html += `<span style="left:${pct}%">${esc(fDiaCorto.format(h))}</span>`;
        }
        previo = d;
      }
      dias.innerHTML = html;
    })();

    function leyenda() {
      const p = PALETAS[E.modo], c = $(".lm-leyenda canvas"), movil = matchMedia("(max-width:640px)").matches;
      const N = 150;
      c.width = movil ? N : 1; c.height = movil ? 1 : N;
      const x = c.getContext("2d"), im = x.createImageData(c.width, c.height);
      for (let k = 0; k < N; k++) {
        const fr = movil ? k / (N - 1) : 1 - k / (N - 1);
        const li = Math.round(fr * (N_LUT - 1)) * 4;
        const a = Math.max(p.lut[li + 3], 60);
        im.data.set([p.lut[li], p.lut[li + 1], p.lut[li + 2], a], k * 4);
      }
      x.putImageData(im, 0, 0);
      $(".lm-leyenda b").textContent = p.unidad;
      $(".lm-leyenda .lm-marcas").innerHTML = p.marcas.map(m => {
        const f = aEscala(m, p.max) * 100;
        return movil ? `<span style="left:${f}%">${num(m)}</span>` : `<span style="bottom:${f}%">${num(m)}</span>`;
      }).join("");
    }

    function rotulos() {
      const f0 = Math.floor(E.t), w = E.t - f0;
      const fin = D.horas[f0] + Math.round(w * 3) * 3600e3; // fin de la hora mostrada
      const m = D.modelo(E.modelo);
      if (E.modo === "dia") {
        $(".lm-hora b").textContent = `${fDia.format(fin)} · ${fHora.format(fin)}`;
        $(".lm-hora span").textContent = "lluvia de las 24 h anteriores";
      } else {
        $(".lm-hora b").textContent = `${fDia.format(fin)} · ${fHora.format(fin - 3600e3)}–${fHora.format(fin)}`;
        $(".lm-hora span").textContent = "mm/h, promedio de cada bloque de 3 h";
      }
      const corrida = m.corrida ? `corrida del ${fCorrida.format(Date.parse(m.corrida))}` : "corrida sin fecha conocida";
      $(".lm-aviso").innerHTML = `<b>Modelo ${esc(m.nombre)}</b>, ${corrida} (hora de Galápagos). ` +
        `<b>Subestima mucho la lluvia en las islas</b> (35–45 mm menos al día): no ve su relieve.`;
      rango.style.setProperty("--p", ((E.t - tMin) / (tMax - tMin || 1) * 100) + "%");
      raiz.querySelectorAll("[data-modo]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.modo === E.modo)));
      $(".lm-viento").setAttribute("aria-pressed", String(E.viento));
      play.innerHTML = E.jugando
        ? `<svg viewBox="0 0 14 14"><rect x="2" y="1" width="3.5" height="12" rx="1" fill="currentColor"/><rect x="8.5" y="1" width="3.5" height="12" rx="1" fill="currentColor"/></svg>`
        : `<svg viewBox="0 0 14 14"><path d="M3 1.5v11l9.5-5.5z" fill="currentColor"/></svg>`;
      play.setAttribute("aria-label", E.jugando ? "Pausar" : "Reproducir");
    }

    let ultimaLectura = null;
    function leer(ll, punto) {
      ultimaLectura = [ll, punto];
      const [gx, gy] = aRejilla(ll);
      const val = muestrear(campoActual(), g.nlon, g.nlat, gx, gy);
      if (!(val === val)) { lectura.style.display = "none"; return; }
      vientoActual();
      const uu = muestrear(u, g.nlon, g.nlat, gx, gy), vv = muestrear(v, g.nlon, g.nlat, gx, gy);
      const rap = Math.hypot(uu, vv), desde = (Math.atan2(-uu, -vv) * 180 / Math.PI + 360) % 360;
      const txtLluvia = E.modo === "dia" ? `${num(val, val < 10 ? 1 : 0)} mm en 24 h` : `${num(val, val < 1 ? 2 : 1)} mm/h`;
      lectura.innerHTML = `<b>${val < 0.05 && E.modo === "hora" ? "sin lluvia" : txtLluvia}</b> · viento ${num(rap * 3.6, 0)} km/h del ${PUNTOS_CARDINALES[Math.round(desde / 22.5) % 16]}`;
      lectura.style.left = punto.x + "px"; lectura.style.top = punto.y + "px"; lectura.style.display = "block";
    }

    function actualizar(rehacerLectura = true) {
      pintar(); vientoActual(); rotulos();
      if (rehacerLectura && ultimaLectura && lectura.style.display === "block") leer(...ultimaLectura);
    }

    // Eventos
    rango.addEventListener("input", () => { E.t = +rango.value; parar(); actualizar(); });
    sel.addEventListener("change", () => { E.modelo = sel.value; actualizar(); });
    raiz.querySelectorAll("[data-modo]").forEach(b => b.addEventListener("click", () => { E.modo = b.dataset.modo; leyenda(); actualizar(); }));
    $(".lm-viento").addEventListener("click", () => { E.viento = !E.viento; rotulos(); });
    mapa.on("mousemove", e => leer(e.latlng, e.containerPoint));
    mapa.on("click", e => leer(e.latlng, e.containerPoint));
    mapa.getContainer().addEventListener("mouseleave", () => { lectura.style.display = "none"; });
    mapa.on("movestart zoomstart", () => { viento.limpiar(); lectura.style.display = "none"; });
    mapa.on("moveend zoomend resize", viento.reiniciar);
    window.addEventListener("resize", leyenda);

    // Reproducción: avanza el tiempo de forma continua (el campo se interpola entre cuadros)
    let previo = 0, rafId = 0, visible = true;
    function parar() { E.jugando = false; }
    play.addEventListener("click", () => {
      E.jugando = !E.jugando;
      if (E.jugando && E.t >= tMax) E.t = tMin;
      rotulos();
    });
    function bucle(ts) {
      rafId = requestAnimationFrame(bucle);
      if (!visible) return;
      const dt = previo ? Math.min(0.1, (ts - previo) / 1000) : 0;
      previo = ts;
      if (E.jugando) {
        E.t += dt / SEG_POR_CUADRO;
        if (E.t >= tMax) { E.t = tMax; E.jugando = false; }
        rango.value = E.t;
        actualizar(false);
      }
      viento.paso(u, v, E.viento);
    }
    // No gastar batería si el mapa no se ve
    if ("IntersectionObserver" in window) new IntersectionObserver(es => { visible = es[0].isIntersecting; previo = 0; }).observe(raiz);

    leyenda(); viento.reiniciar(); actualizar();
    rafId = requestAnimationFrame(bucle);

    return {
      mapa,
      ir(t) { E.t = Math.max(tMin, Math.min(tMax, t)); rango.value = E.t; actualizar(); },
      estado: () => ({...E, hora: new Date(D.horas[Math.floor(E.t)]).toISOString()}),
      destruir() { cancelAnimationFrame(rafId); mapa.remove(); raiz.innerHTML = ""; },
    };
  }

  // ── Reel: las próximas horas, animadas solas (portada) ───────────────────
  // Es el mapa del reel del clima, en vivo: el contorno de las islas en vez de teselas, el reloj, un punto
  // rojo en cada puerto que crece con la lluvia del modelo, y la tira «¿A qué hora llueve más en cada isla?».
  // No muestra milímetros: los del modelo sirven para ver cuándo llueve, no cuánto.
  const ENCUADRE_REEL = [[-1.35, -91.85], [0.35, -89.08]];   // las tres islas pobladas, con sitio arriba para el reloj
  const ISLAS_REEL = [["Isabela", -0.30, -91.33], ["Santa Cruz", -0.40, -90.33], ["San Cristóbal", -0.62, -89.42]];
  const PUERTOS_REEL = [["Puerto Ayora", -0.743, -90.31], ["Pto. Baquerizo", -0.901, -89.61], ["Pto. Villamil", -0.958, -90.965]];
  // La parte alta de cada isla, donde más llueve: ahí se lee la lluvia del modelo para la tira.
  const ALTAS_REEL = [["Santa Cruz", -0.655, -90.404], ["San Cristóbal", -0.893, -89.5], ["Isabela", -0.86, -91.03]];
  const DIAS_CORTOS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const horaLocal = t => new Date(t - 6 * 3600e3).getUTCHours();
  const diaCorto = t => { const d = new Date(t - 6 * 3600e3); return `${DIAS_CORTOS[d.getUTCDay()]} ${d.getUTCDate()}`; };
  const franja = h => h < 6 ? "madrugada" : h < 12 ? "mañana" : h < 18 ? "tarde" : "noche";
  const dos = n => String(n).padStart(2, "0");
  const ICONO_PAUSA = `<svg viewBox="0 0 14 14" aria-hidden="true"><rect x="2" y="1" width="3.5" height="12" rx="1" fill="currentColor"/><rect x="8.5" y="1" width="3.5" height="12" rx="1" fill="currentColor"/></svg>`;
  const ICONO_PLAY = `<svg viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.5v11l9.5-5.5z" fill="currentColor"/></svg>`;

  async function reel(raiz, op = {}) {
    let L, j, islas;
    try {
      [L, j, islas] = await Promise.all([
        (op.leaflet || cargarLeaflet)(),
        fetch(op.datos || "datos/lluvia-mapa.json", {cache: "no-cache"}).then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }),
        op.islas ? fetch(op.islas).then(r => r.ok ? r.json() : null).catch(() => null) : null,
      ]);
    } catch (e) {
      return null;
    }
    if (!j.modelos || !j.modelos.length || !j.horas || j.horas.length < 3) return null;
    const D = new Datos(j), g = D.g, H = D.horas, n = H.length, P = (j.paso_h || 3) * 3600e3;
    const modelo = D.modelo(op.modelo), id = modelo.id;
    // Si el reloj del teléfono está muy lejos del de la plataforma, manda el de la plataforma.
    const recibido = Date.now(), desfase = j.ahora ? Date.parse(j.ahora) - recibido : 0;
    const ahora = () => Date.now() + (Math.abs(desfase) > 15 * 60e3 ? desfase : 0);
    const TRAMO = (op.horas || 24) * 3600e3;
    // El tramo que se anima: de la hora en punto actual a 24 h después, o hasta donde lleguen los datos.
    let T0 = 0, T1 = 0;
    function ventana() {
      const a = Math.max(Math.floor(ahora() / 3600e3) * 3600e3, H[0] - P), b = Math.min(a + TRAMO, H[n - 1]);
      if (b - a < 6 * 3600e3) return false;
      T0 = a; T1 = b;
      return true;
    }
    if (!ventana()) return null;

    if (raiz._lmReel) raiz._lmReel.destruir();
    raiz.classList.add("lr");
    raiz.innerHTML = `
      <div class="lr-caja">
        <div class="lr-mapa" role="img" aria-label="Mapa animado de la lluvia y el viento que calcula el modelo ${esc(modelo.nombre)} para las próximas ${Math.round(TRAMO / 3600e3)} horas en Isabela, Santa Cruz y San Cristóbal."></div>
        <div class="lr-rotulos" aria-hidden="true"></div>
        <div class="lr-reloj" aria-hidden="true"><b></b><span></span></div>
        <button type="button" class="lr-play"></button>
        <div class="lr-leyenda" aria-hidden="true"><div><span>menos lluvia</span><span>más</span></div><canvas width="160" height="1"></canvas></div>
        <div class="lr-credito">Modelo ${esc(modelo.nombre)}</div>
      </div>
      <div class="lr-tira">
        <h3>¿A qué hora llueve más en cada isla?</h3>
        <div class="lr-filas"></div>
        <div class="lr-eje" aria-hidden="true"></div>
      </div>`;
    const $ = sel => raiz.querySelector(sel);
    const mapa = L.map($(".lr-mapa"), {zoomControl: false, attributionControl: false, zoomSnap: 0, fadeAnimation: false, zoomAnimation: false,
      dragging: false, touchZoom: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false, tap: false});
    const encuadrar = () => mapa.fitBounds(op.encuadre || ENCUADRE_REEL, {animate: false});
    encuadrar();
    if (islas && islas.features && islas.features.length) {
      mapa.createPane("lrTierra").style.zIndex = 300;
      mapa.createPane("lrCosta").style.zIndex = 420;   // la costa va encima de la lluvia
      L.geoJSON(islas, {interactive: false, pane: "lrTierra", style: {fillColor: "#f3efe4", fillOpacity: 1, stroke: false}}).addTo(mapa);
      L.geoJSON(islas, {interactive: false, pane: "lrCosta", style: {fill: false, color: "#1b2a33", weight: 1.2}}).addTo(mapa);
    } else {
      baseEsri(L, mapa);
    }
    const sur = g.norte - (g.nlat - 1) * g.paso, este = g.oeste + (g.nlon - 1) * g.paso;
    const pintarLluvia = capaLluvia(L, mapa, g, [[sur, g.oeste], [g.norte, este]]);
    const viento = capaViento(mapa, g, {desvanecer: 0.93, color: "rgba(20,30,50,0.62)", vida: 110, maximo: 3400, area: 240});
    const campo = new Float32Array(D.n), u = new Float32Array(D.n), v = new Float32Array(D.n);
    const enPunto = (c, x, y) => { const val = muestrear(c, g.nlon, g.nlat, x, y); return val > 0 ? val : 0; };
    const aRejilla = (la, lo) => [(lo - g.oeste) / g.paso, (g.norte - la) / g.paso];

    // Rótulos y puertos: van encima de las partículas, así que se colocan a mano y no como marcadores del mapa.
    const rotulos = $(".lr-rotulos");
    const poner = (clase, texto) => { const e = document.createElement("span"); e.className = clase; e.textContent = texto; rotulos.appendChild(e); return e; };
    const nombres = ISLAS_REEL.map(([nombre, la, lo]) => ({la, lo, el: poner("lr-isla", nombre)}));
    const puertos = PUERTOS_REEL.map(([nombre, la, lo]) => {
      const [gx, gy] = aRejilla(la, lo);
      return {la, lo, gx, gy, anillos: [poner("lr-anillo", ""), poner("lr-anillo", "")], punto: poner("lr-punto", ""), rotulo: poner("lr-puerto", nombre)};
    });
    const altas = ALTAS_REEL.map(([nombre, la, lo]) => { const [x, y] = aRejilla(la, lo); return {nombre, x, y}; });
    let escala = 1;
    function colocar() {
      const ancho = mapa.getSize().x;
      escala = Math.max(0.5, Math.min(1, ancho / 680));
      rotulos.style.setProperty("--lr-bajo", ((7 + 24) * escala + 3).toFixed(1) + "px");   // el nombre del puerto, justo debajo del punto más grande
      viento.ajustes.K = Math.max(0.1, 0.42 * ancho / 1080);   // la misma rapidez sobre el mapa que en el reel, sea cual sea el ancho
      viento.ajustes.ancho = ancho < 500 ? 1.1 : 1.4;
      // Un rótulo centrado en su punto no se sale de la caja: en un teléfono estrecho, «San Cristóbal» se corre hacia dentro.
      const dentro = (e, x) => { const medio = e.offsetWidth / 2 + 6; return Math.max(medio, Math.min(ancho - medio, x)); };
      for (const r of nombres) { const p = mapa.latLngToContainerPoint([r.la, r.lo]); r.el.style.left = dentro(r.el, p.x) + "px"; r.el.style.top = p.y + "px"; }
      for (const q of puertos) {
        const p = mapa.latLngToContainerPoint([q.la, q.lo]);
        for (const e of [q.punto, ...q.anillos]) { e.style.left = p.x + "px"; e.style.top = p.y + "px"; }
        q.rotulo.style.left = dentro(q.rotulo, p.x) + "px"; q.rotulo.style.top = p.y + "px";
      }
    }

    // Leyenda: del azul claro al rojo de la paleta, sin cifras.
    (function () {
      const c = $(".lr-leyenda canvas").getContext("2d"), lut = PALETAS.reel.lut;
      for (let x = 0; x < 160; x++) {
        const k = Math.round((0.07 + 0.55 * x / 159) * (N_LUT - 1)) * 4;
        c.fillStyle = `rgba(${lut[k]},${lut[k + 1]},${lut[k + 2]},${Math.max(lut[k + 3], 90) / 255})`;
        c.fillRect(x, 0, 1, 1);
      }
    })();

    // La tira: lluvia del modelo en la parte alta de cada isla, en los bloques de 3 h que toca el tramo.
    const filas = $(".lr-filas"), eje = $(".lr-eje");
    let k0 = 0, k1 = 0, ini = 0, fin = 0, ref = 0.5, pico = 0, hoy = "", manana = "", barras = [], cursor = null, yaPintados = -1;
    function tira() {
      k0 = H.findIndex(h => h > T0);
      k1 = n - 1;
      while (k1 > k0 && H[k1] - P >= T1) k1--;
      ini = H[k0] - P; fin = H[k1];
      hoy = diaLocal(T0); manana = diaLocal(T0 + 24 * 3600e3);
      // Referencia de tamaño del punto de cada puerto: la lluvia más fuerte del modelo en los puertos en este tramo.
      ref = 0.5;
      for (let i = k0; i <= k1; i++) for (const q of puertos) ref = Math.max(ref, enPunto(D.porHora(id, i), q.gx, q.gy));
      const porIsla = altas.map(a => { const b = []; for (let i = k0; i <= k1; i++) b.push(enPunto(D.porHora(id, i), a.x, a.y)); return b; });
      const tope = Math.max(0.8, ...porIsla.map(b => Math.max(...b)));
      const media = porIsla[0].map((_, p) => porIsla.reduce((suma, b) => suma + b[p], 0) / porIsla.length);
      pico = H[k0 + media.indexOf(Math.max(...media))] - P / 2;   // el centro del bloque con más lluvia en las tres islas
      const cuando = i => {
        const t = H[i] - P, h = horaLocal(t), d = diaLocal(t);
        return `${d === hoy ? "hoy" : d === manana ? "mañana" : diaCorto(t)}, ${dos(h)}–${dos(h + 3)} h`;
      };
      filas.innerHTML = porIsla.map((b, k) => {
        const pk = b.indexOf(Math.max(...b)), hay = b[pk] >= 0.1;   // menos de 0,1 mm/h en todo el tramo: casi no llueve
        return `<div class="lr-fila"><b>${esc(altas[k].nombre)}<span>${hay ? cuando(k0 + pk) : "casi sin lluvia"}</span></b><div class="lr-barras">` +
          b.map((val, p) => `<i class="${hay && p === pk ? "lr-pico" : ""}" style="height:${Math.max(6, Math.sqrt(val / tope) * 82).toFixed(1)}%"></i>`).join("") + "</div></div>";
      }).join("") + `<i class="lr-cursor"></i>`;
      barras = Array.from(filas.querySelectorAll(".lr-barras")).map(f => Array.from(f.children));
      cursor = filas.querySelector(".lr-cursor");
      yaPintados = -1;
      let marcas = "";
      for (let t = ini; t <= fin; t += P) {
        const h = horaLocal(t), pct = (t - ini) / (fin - ini) * 100;
        if (h % 6) continue;
        marcas += `<span class="${h === 0 ? "lr-dia" : ""}${pct < 5 ? " lr-ini" : pct > 95 ? " lr-fin" : ""}" style="left:${pct.toFixed(2)}%">${h === 0 ? esc(diaCorto(t)) : dos(h) + " h"}</span>`;
      }
      eje.innerHTML = marcas;
    }

    function campos(T) {
      // La lluvia de un cuadro es la de las 3 h que terminan en su hora: su centro va hora y media antes. El viento es el de esa hora.
      let t = Math.max(0, Math.min(n - 1, (T - H[0]) / P + 0.5)), f0 = Math.floor(t);
      mezclar(D.porHora(id, f0), D.porHora(id, Math.min(f0 + 1, n - 1)), t - f0, campo);
      t = Math.max(0, Math.min(n - 1, (T - H[0]) / P)); f0 = Math.floor(t);
      const [u0, v0] = D.viento(id, f0), [u1, v1] = D.viento(id, Math.min(f0 + 1, n - 1));
      mezclar(u0, u1, t - f0, u); mezclar(v0, v1, t - f0, v);
    }
    const reloj = $(".lr-reloj b"), cuandoEl = $(".lr-reloj span");
    let textoHora = "", textoCuando = "", quieto = false;
    function dibujar(T) {
      campos(T);
      pintarLluvia(campo, PALETAS.reel);
      const pulso = quieto ? 0 : performance.now() / 870;
      for (const q of puertos) {
        const f = Math.min(1, Math.pow(enPunto(campo, q.gx, q.gy) / ref, 0.7)), r = (7 + 24 * f) * escala;
        q.punto.style.width = q.punto.style.height = (2 * r).toFixed(1) + "px";
        q.anillos.forEach((a, k) => {
          const fase = (pulso + k / 2) % 1, rr = r * (1 + (0.5 + 1.1 * f) * fase);
          a.style.width = a.style.height = (2 * rr).toFixed(1) + "px";
          a.style.borderWidth = ((2.5 + 4 * f) * escala).toFixed(1) + "px";
          a.style.opacity = quieto ? 0 : ((0.3 + 0.45 * f) * (1 - fase)).toFixed(2);
        });
      }
      const t10 = Math.floor(T / 600e3) * 600e3, hora = fHora.format(t10), cuando = `${diaCorto(t10)} · ${franja(horaLocal(t10))}`;
      if (hora !== textoHora) reloj.textContent = textoHora = hora;
      if (cuando !== textoCuando) cuandoEl.textContent = textoCuando = cuando;
      let ya = 0;
      for (let i = k0; i <= k1; i++) if (H[i] - P < T) ya++;
      if (ya !== yaPintados) { yaPintados = ya; for (const fila of barras) fila.forEach((b, p) => b.classList.toggle("lr-ya", p < ya)); }
      cursor.style.setProperty("--f", ((T - ini) / (fin - ini)).toFixed(4));
    }
    // Una imagen quieta: el campo de esa hora y las rayas del viento ya dibujadas, sin nada que se mueva.
    function fijar(T) {
      quieto = true;
      dibujar(T);
      viento.limpiar();
      for (let k = 0; k < 60; k++) viento.paso(u, v, true);
    }

    // Reproducción: el tramo completo en unos 10 segundos, una pausa al final y vuelta a empezar.
    const DURA = (op.segundos || 10) * 1000, ANTES = 500, DESPUES = 1500;
    const reducir = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const play = $(".lr-play");
    let jugando = !reducir && op.reproducir !== false, fase = 0, previo = 0, visible = true, rafId = 0, vivo = true, pedido = 0;
    const tiempo = () => T0 + Math.max(0, Math.min(1, (fase - ANTES) / DURA)) * (T1 - T0);
    function boton() {
      play.innerHTML = jugando ? ICONO_PAUSA : ICONO_PLAY;
      play.setAttribute("aria-label", jugando ? "Pausar la animación" : "Reproducir la animación");
    }
    play.addEventListener("click", () => {
      jugando = !jugando;
      if (jugando) { quieto = false; previo = 0; } else fijar(tiempo());
      boton();
    });
    // Con datos de hace más de media hora, se piden de nuevo. Si llegan, este reel se reemplaza; si no, sigue con los que tiene.
    function renovar() {
      if (Date.now() - recibido < 30 * 60e3 || Date.now() - pedido < 5 * 60e3) return;
      pedido = Date.now();
      reel(raiz, op).catch(() => {});
    }
    function bucle(ts) {
      if (!vivo) return;
      rafId = requestAnimationFrame(bucle);
      if (!visible || document.hidden || !jugando) { previo = 0; return; }
      fase += previo ? Math.min(100, ts - previo) : 0;
      previo = ts;
      if (fase >= ANTES + DURA + DESPUES) {
        fase = 0;
        if (ventana()) tira();
        renovar();
      }
      dibujar(tiempo());
      viento.paso(u, v, true);
    }
    function ajustar() {
      mapa.invalidateSize({animate: false});
      encuadrar();
      viento.reiniciar();
      colocar();
      if (!jugando) fijar(tiempo());
    }
    const observadores = [];
    if ("IntersectionObserver" in window) {
      const o = new IntersectionObserver(es => { visible = es[0].isIntersecting; previo = 0; });
      o.observe(raiz); observadores.push(o);
    }
    if ("ResizeObserver" in window) {
      let ancho = mapa.getSize().x;
      const o = new ResizeObserver(() => { const a = $(".lr-mapa").clientWidth; if (a && a !== ancho) { ancho = a; ajustar(); } });
      o.observe($(".lr-mapa")); observadores.push(o);
    }

    tira(); viento.reiniciar(); colocar(); boton();
    if (jugando) {
      campos(T0);
      for (let k = 0; k < 40; k++) viento.paso(u, v, true);   // que el viento ya se vea en el primer cuadro
      dibujar(T0);
    } else {
      fase = ANTES + DURA * (Math.max(T0, Math.min(T1, pico)) - T0) / (T1 - T0);   // sin animación: la hora de más lluvia
      fijar(tiempo());
    }
    rafId = requestAnimationFrame(bucle);

    const api = {
      mapa,
      estado: () => ({jugando, desde: new Date(T0).toISOString(), hasta: new Date(T1).toISOString(), hora: new Date(tiempo()).toISOString(), modelo: id}),
      destruir() { vivo = false; cancelAnimationFrame(rafId); observadores.forEach(o => o.disconnect()); mapa.remove(); raiz._lmReel = null; },
    };
    raiz._lmReel = api;
    return api;
  }

  window.LluviaMapa = {montar, reel};
})();
