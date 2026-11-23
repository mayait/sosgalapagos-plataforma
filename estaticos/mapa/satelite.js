/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
 * Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
 * Único original: el panel de /clima/ (repositorio de datos) carga este mismo archivo. */
/* Mapa del satélite del panel de /clima/: fondo animado y lluvia estimada.
 *
 * - Fondo: la imagen GeoColor de GOES-East (NOAA) que sirve NASA GIBS, cada 10 min en las últimas 3 h
 *   disponibles (llega con ~60 min de retraso). En color de día, infrarrojo de noche. Es una imagen,
 *   no un dato de lluvia. La plantilla y las horas las da la plataforma: /riesgos/api/clima/satelite-capas.
 * - Lluvia estimada: PDIR-Now (CHRS, UC Irvine), horaria, celdas de 0,04°: /riesgos/api/clima/pdirnow.json.
 *   Es una ESTIMACIÓN por infrarrojo, no medida ni oficial: no ve la garúa ni la lluvia de nubes bajas.
 *   Solo se muestra: no entra en la señal satelital ni en el nivel de lluvia.
 *
 * Uso (Leaflet 1.9 ya cargado):
 *   const s = SateliteMapa.montar(mapa, L, {capas: "/riesgos/api/clima/satelite-capas"});
 *   s.lluvia(datosPdir | null);   // dibuja (o quita) la lluvia de PDIR-Now
 * Si la API falla, el mapa sigue como estaba (sin fondo animado).
 */
(function () {
  "use strict";

  const ZONA = "Pacific/Galapagos"; // UTC−6, sin horario de verano
  const MS_CUADRO = 600;            // al reproducir
  const fHora = new Intl.DateTimeFormat("es-EC", {timeZone: ZONA, hour: "2-digit", minute: "2-digit", hourCycle: "h23"});
  const fDia = new Intl.DateTimeFormat("es-EC", {timeZone: ZONA, weekday: "short", day: "numeric", month: "short"});
  const num = (v, d = 1) => v.toLocaleString("es-EC", {maximumFractionDigits: d, minimumFractionDigits: d});

  // Paleta azul de lluvia (mm/h), por tramos, sobre la imagen del satélite (clara de día, oscura de noche)
  const TRAMOS = [[0.1, [190, 220, 250, 150]], [1, [134, 182, 239, 200]], [5, [57, 135, 229, 225]], [10, [28, 92, 171, 240]], [20, [13, 54, 107, 250]]];
  const LEYENDA = [["0,1", TRAMOS[0][1]], ["1", TRAMOS[1][1]], ["5", TRAMOS[2][1]], ["10", TRAMOS[3][1]], ["20+", TRAMOS[4][1]]];
  const color = mm => { let c = null; for (const [u, k] of TRAMOS) if (mm >= u) c = k; return c; };
  const decodificar = b => b === 255 ? null : (b / 10) ** 2;

  const CSS = `
.sm-ctrl{background:rgba(255,255,255,.93);border:1px solid rgba(0,0,0,.14);border-radius:9px;box-shadow:0 1px 5px rgba(0,0,0,.18);
  padding:5px 7px;font:12px/1.3 "Helvetica Neue",Helvetica,Arial,system-ui,sans-serif;color:#141414;width:min(250px,calc(100vw - 90px));opacity:.95}
.sm-fila{display:flex;align-items:center;gap:8px}
.sm-play{flex:none;width:30px;height:30px;border-radius:50%;border:0;background:#141414;color:#fff;cursor:pointer;display:grid;place-items:center;padding:0}
.sm-play svg{width:12px;height:12px}
.sm-play:focus-visible,.sm-rango:focus-visible{outline:2px solid #2f6fb3;outline-offset:1px}
.sm-pista{flex:1;min-width:0}
.sm-hora{font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sm-hora b{font-size:13px}
.sm-rango{width:100%;margin:2px 0 0;accent-color:#141414;cursor:pointer}
.sm-sub{color:#4b5058;font-size:10.5px;margin-top:2px}
@media (max-width:640px){.sm-sub{display:none}}
.sm-ley{display:flex;align-items:center;gap:2px;margin-top:4px;font-size:10px;color:#3a3f45}
.sm-ley i{display:inline-block;width:16px;height:8px;border-radius:2px}
.sm-ley span{margin-right:4px}
.leaflet-pane.sm-lluvia img{image-rendering:pixelated;image-rendering:crisp-edges}`;

  function estilos() {
    if (document.getElementById("sm-estilos")) return;
    const s = document.createElement("style");
    s.id = "sm-estilos"; s.textContent = CSS; document.head.appendChild(s);
  }

  const ICONO_PLAY = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 1l9 5-9 5z" fill="currentColor"/></svg>';
  const ICONO_PAUSA = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 1h3v10H2zM7 1h3v10H7z" fill="currentColor"/></svg>';

  // ── Lluvia de PDIR-Now: una imagen por hora (un píxel por celda), sobre los bordes del recorte ──
  function imagenHora(d, h) {
    const plano = atob(h.b64), cv = document.createElement("canvas");
    cv.width = d.columnas; cv.height = d.filas;
    const cx = cv.getContext("2d"), img = cx.createImageData(d.columnas, d.filas);
    let hay = false;
    for (let i = 0; i < plano.length; i++) {
      const mm = decodificar(plano.charCodeAt(i)), c = mm == null ? null : color(mm);
      if (c) { img.data.set(c, i * 4); hay = true; }
    }
    cx.putImageData(img, 0, 0);
    return hay ? cv.toDataURL() : null;
  }

  function valorEn(d, h, lat, lon) {
    const i = Math.floor((d.norte - lat) / d.paso), j = Math.floor((lon - d.oeste) / d.paso);
    if (i < 0 || j < 0 || i >= d.filas || j >= d.columnas) return undefined;
    return decodificar(atob(h.b64).charCodeAt(i * d.columnas + j));
  }

  /** La hora de PDIR-Now que corresponde a t (ms): la que lo contiene o, si no hay, la última anterior. */
  function horaPara(d, t) {
    if (!d || !d.horas || !d.horas.length) return null;
    let mejor = null;
    for (const h of d.horas) if (Date.parse(h.inicio) <= t) mejor = h;
    return mejor;
  }

  function montar(mapa, L, opciones = {}) {
    estilos();
    if (!mapa.getPane("smFondo")) {
      mapa.createPane("smFondo").style.zIndex = 250;        // sobre el mapa base (200)
      const p = mapa.createPane("smLluvia"); p.style.zIndex = 380; p.classList.add("sm-lluvia"); p.style.pointerEvents = "none";
    }
    const E = {capas: null, frames: [], i: -1, jugando: false, timer: null, pdir: null, imagenes: {}, overlay: null, overlayHora: null};
    const raiz = L.DomUtil.create("div", "sm-ctrl");
    raiz.innerHTML = `<div class="sm-fila"><button type="button" class="sm-play" aria-label="Reproducir">${ICONO_PLAY}</button>
      <div class="sm-pista"><div class="sm-hora"><b>—</b> <span></span></div><input class="sm-rango" type="range" min="0" max="0" value="0" aria-label="Hora de la imagen del satélite"></div></div>
      <div class="sm-sub"></div><div class="sm-ley" hidden></div>`;
    L.DomEvent.disableClickPropagation(raiz);
    L.DomEvent.disableScrollPropagation(raiz);
    const $ = s => raiz.querySelector(s);
    const ctrl = L.control({position: "bottomleft"});
    ctrl.onAdd = () => raiz;
    $(".sm-ley").innerHTML = "<span>mm/h</span>" + LEYENDA.map(([t, c]) => `<i style="background:rgba(${c[0]},${c[1]},${c[2]},${(c[3] / 255).toFixed(2)})"></i><span>${t}</span>`).join("");

    function tiempoActual() {
      return E.frames[E.i] ? E.frames[E.i].t : (E.pdir && E.pdir.horas.length ? Date.parse(E.pdir.horas[E.pdir.horas.length - 1].fin) - 1 : Date.now());
    }

    function pintarLluvia() {
      const h = horaPara(E.pdir, tiempoActual());
      if (h === E.overlayHora && (E.overlay || !h)) return;
      if (E.overlay) { mapa.removeLayer(E.overlay); E.overlay = null; }
      E.overlayHora = h;
      if (!h) return;
      if (!(h.inicio in E.imagenes)) E.imagenes[h.inicio] = imagenHora(E.pdir, h);
      const url = E.imagenes[h.inicio];
      if (url) E.overlay = L.imageOverlay(url, [[E.pdir.sur, E.pdir.oeste], [E.pdir.norte, E.pdir.este]], {pane: "smLluvia", opacity: 0.85, interactive: false}).addTo(mapa);
    }

    function rotulo() {
      const f = E.frames[E.i], h = horaPara(E.pdir, tiempoActual());
      $(".sm-hora b").textContent = f ? fHora.format(f.t) : "—";
      $(".sm-hora span").textContent = f ? `${fDia.format(f.t)} · hora de Galápagos` : "sin imagen del satélite";
      const partes = [];
      if (f) partes.push("Imagen GeoColor: color de día, infrarrojo de noche");
      if (E.pdir) partes.push(h ? `lluvia estimada (PDIR-Now) de ${fHora.format(Date.parse(h.inicio))} a ${fHora.format(Date.parse(h.fin))}` : "sin lluvia estimada para esta hora");
      $(".sm-sub").textContent = partes.join(" · ");
      $(".sm-ley").hidden = !E.pdir;
      const r = $(".sm-rango");
      r.value = Math.max(0, E.i);
    }

    function ir(i) {
      if (!E.frames.length) { E.i = -1; pintarLluvia(); rotulo(); return; }
      i = (i + E.frames.length) % E.frames.length;
      E.frames.forEach((f, k) => f.capa.setOpacity(k === i ? 1 : 0));
      E.i = i;
      pintarLluvia();
      rotulo();
      if (opciones.alCambiar) opciones.alCambiar(E.frames[i].t);
    }

    function jugar(si) {
      E.jugando = si;
      $(".sm-play").innerHTML = si ? ICONO_PAUSA : ICONO_PLAY;
      $(".sm-play").setAttribute("aria-label", si ? "Pausar" : "Reproducir");
      clearInterval(E.timer);
      if (si) E.timer = setInterval(() => ir(E.i + 1 === E.frames.length ? 0 : E.i + 1), MS_CUADRO);
    }

    $(".sm-play").addEventListener("click", () => { if (E.frames.length > 1) jugar(!E.jugando); });
    $(".sm-rango").addEventListener("input", e => { jugar(false); ir(+e.target.value); });

    // Clic: lluvia estimada en esa celda
    mapa.on("click", e => {
      const h = horaPara(E.pdir, tiempoActual());
      if (!h) return;
      const v = valorEn(E.pdir, h, e.latlng.lat, e.latlng.lng);
      if (v === undefined) return;
      L.popup({maxWidth: 240}).setLatLng(e.latlng).setContent(
        `<b>Lluvia estimada: ${v == null ? "sin dato" : num(v, 1) + " mm/h"}</b><br>PDIR-Now, ${fHora.format(Date.parse(h.inicio))}–${fHora.format(Date.parse(h.fin))} (hora de Galápagos).<br>` +
        `<span style="color:#5f6670">Estimación por satélite, no medida ni oficial. No ve la garúa ni la lluvia de nubes bajas.</span>`).openOn(mapa);
    });

    ctrl.addTo(mapa);
    rotulo();

    const listo = (opciones.capas ? fetch(opciones.capas).then(r => r.ok ? r.json() : null).catch(() => null) : Promise.resolve(null)).then(c => {
      E.capas = c;
      if (!c || !c.plantilla || !(c.tiempos || []).length) { rotulo(); return api; }
      E.frames = c.tiempos.map(t => ({
        t: Date.parse(t),
        capa: L.tileLayer(c.plantilla.replace("{t}", t), {pane: "smFondo", opacity: 0, maxNativeZoom: c.zoom_max || 7, maxZoom: 18,
          updateWhenIdle: true, keepBuffer: 1, attribution: c.atribucion || ""}).addTo(mapa),
      }));
      $(".sm-rango").max = E.frames.length - 1;
      ir(E.frames.length - 1);
      return api;
    });

    const api = {
      listo,
      /** Datos de pdirnow.json (o null para quitar la capa). */
      lluvia(d) {
        E.pdir = d && d.horas && d.horas.length ? d : null;
        E.overlayHora = undefined;
        if (!E.pdir && E.overlay) { mapa.removeLayer(E.overlay); E.overlay = null; }
        pintarLluvia();
        rotulo();
      },
      tiempos: () => E.frames.map(f => f.t),
      detener: () => jugar(false),
    };
    return api;
  }

  window.SateliteMapa = {montar, horaPara, valorEn, decodificar};
})();
