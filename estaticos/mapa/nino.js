/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
 * Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
 * Único original: el panel de /clima/ (repositorio de datos) carga este mismo archivo. */
/* El Niño en el panel de clima: tarjeta con la voz oficial (ERFEN), los índices de la NOAA como contexto
   y un mapa de la anomalía de temperatura (o del nivel) del mar con las regiones Niño, la ZCIT y las ondas.

   Uso (una línea en el panel de /clima/, que carga /riesgos/estaticos/mapa/nino.js y nino.css):
     NinoPanel.montar(document.getElementById("nino"));
   Lee nino.json, nino_mapa.json y zcit.json de la API de la plataforma (/riesgos/api/clima/), que los
   sirve desde CLIMA_SALIDA; los genera clima/nino.py y clima/zcit.py. Con {base: "otra/carpeta/"} los lee de otro sitio.
   Necesita Leaflet 1.9.4; si la página no lo cargó, lo carga solo. Estilos en nino.css. */
(function () {
  "use strict";
  const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const COLOR = {nino12: "var(--n-c12)", nino3: "var(--n-c3)", nino34: "var(--n-c34)", nino4: "var(--n-c4)"};
  const NOMBRE = {nino12: "Niño 1+2", nino3: "Niño 3", nino34: "Niño 3.4", nino4: "Niño 4"};

  // ── utilidades ──────────────────────────────────────────────────────────
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const num = (v, d = 1, signo = false) => v == null || isNaN(v) ? "—" : ((signo && v > 0 ? "+" : "") + v.toFixed(d)).replace(".", ",").replace("-", "−");
  const fecha = iso => { if (!iso) return "—"; const d = new Date(iso.length <= 10 ? iso + "T12:00:00Z" : iso); return d.getUTCDate() + " " + MESES[d.getUTCMonth()]; };
  const fechaHora = iso => { // hora de Galápagos (UTC−6)
    if (!iso) return "—"; const d = new Date(new Date(iso).getTime() - 6 * 3600e3);
    return d.getUTCDate() + " " + MESES[d.getUTCMonth()] + ", " + String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0");
  };
  const ICON = {
    escudo: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/></svg>',
    termo: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M14 14.8V4a2 2 0 1 0-4 0v10.8a4 4 0 1 0 4 0z"/></svg>',
    ola: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M2 12c2.5-3 5-3 7.5 0s5 3 7.5 0 3.5-2 5-1"/><path d="M2 18c2.5-3 5-3 7.5 0s5 3 7.5 0 3.5-2 5-1"/></svg>',
    globo: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18"/></svg>',
    barras: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M5 20V10M12 20V4M19 20v-7"/></svg>',
    info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
    nube: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0B4F8A" stroke-width="2" stroke-linecap="round"><path d="M7 17h10a4 4 0 0 0 .5-8 6 6 0 0 0-11.5 1.5A3.3 3.3 0 0 0 7 17z"/><path d="M9 20l-1 2M13 20l-1 2M17 20l-1 2"/></svg>',
    onda: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#7A4FB5" stroke-width="2.2" stroke-linecap="round"><path d="M12 2v20"/><path d="M8 6l4-4 4 4"/><path d="M3 14c3-2 6-2 9 0s6 2 9 0"/></svg>',
  };

  // Paletas: anomalía de temperatura (°C) y del nivel del mar (cm). [valor, r, g, b]
  const PAL_SST = [[-3, 33, 102, 172], [-1.5, 103, 169, 207], [-0.5, 209, 229, 240], [0, 247, 247, 247], [0.5, 253, 219, 199], [1.5, 244, 165, 130], [3, 214, 96, 77], [5, 178, 24, 43], [7, 103, 0, 31]];
  const PAL_SLA = [[-20, 33, 102, 172], [-8, 146, 197, 222], [0, 247, 247, 247], [10, 216, 218, 235], [25, 158, 154, 200], [40, 106, 81, 163], [60, 63, 0, 125]];
  function color(pal, v) {
    if (v <= pal[0][0]) return pal[0].slice(1);
    for (let i = 1; i < pal.length; i++) if (v <= pal[i][0]) {
      const a = pal[i - 1], b = pal[i], t = (v - a[0]) / (b[0] - a[0]);
      return [0, 1, 2].map(k => Math.round(a[k + 1] + t * (b[k + 1] - a[k + 1])));
    }
    return pal[pal.length - 1].slice(1);
  }
  const gradiente = pal => "linear-gradient(90deg," + pal.map((p, i) => `rgb(${p.slice(1)}) ${Math.round(100 * i / (pal.length - 1))}%`).join(",") + ")";

  // ── mini gráficos SVG ───────────────────────────────────────────────────
  function linea(valores, {ancho = 240, alto = 46, color = "currentColor", cero = true, area = true, puntos = false} = {}) {
    const v = valores.filter(x => x != null);
    if (v.length < 2) return "";
    let lo = Math.min(...v, cero ? 0 : Infinity), hi = Math.max(...v, cero ? 0 : -Infinity);
    if (hi - lo < 1e-6) hi = lo + 1;
    const x = i => (i / (valores.length - 1)) * ancho, y = val => alto - 3 - ((val - lo) / (hi - lo)) * (alto - 8);
    let d = "", ult = null;
    valores.forEach((val, i) => { if (val == null) return; d += (d ? "L" : "M") + x(i).toFixed(1) + " " + y(val).toFixed(1); ult = [x(i), y(val)]; });
    const base = y(Math.max(lo, Math.min(0, hi)));
    const relleno = area ? `<path d="${d}L${ult[0].toFixed(1)} ${base.toFixed(1)}L0 ${base.toFixed(1)}Z" fill="${color}" opacity=".13"/>` : "";
    const ceroL = cero && lo < 0 && hi > 0 ? `<line x1="0" x2="${ancho}" y1="${base}" y2="${base}" stroke="#999" stroke-width="1" stroke-dasharray="2 3"/>` : "";
    return `<svg viewBox="0 0 ${ancho} ${alto}" preserveAspectRatio="none">${ceroL}${relleno}<path d="${d}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>` +
      `<circle cx="${ult[0]}" cy="${ult[1]}" r="3.2" fill="${color}"/>${puntos ? "" : ""}</svg>`;
  }
  function barras(valores, {ancho = 240, alto = 46, umbral = 0.5} = {}) {
    const v = valores.filter(x => x != null); if (!v.length) return "";
    const hi = Math.max(2.5, ...v), lo = Math.min(-1, ...v), w = ancho / valores.length;
    const y = val => alto - 2 - ((val - lo) / (hi - lo)) * (alto - 4), y0 = y(0);
    return `<svg viewBox="0 0 ${ancho} ${alto}" preserveAspectRatio="none">` + valores.map((val, i) => {
      if (val == null) return "";
      const c = val >= 2 ? "#67001F" : val >= 1.5 ? "#B2182B" : val >= 1 ? "#D6604D" : val >= umbral ? "#F4A582" : val <= -umbral ? "#4393C3" : "#BBBBBB";
      return `<rect x="${(i * w + 0.6).toFixed(1)}" y="${Math.min(y(val), y0).toFixed(1)}" width="${(w - 1.2).toFixed(1)}" height="${Math.max(1, Math.abs(y(val) - y0)).toFixed(1)}" rx="1" fill="${c}"/>`;
    }).join("") + `</svg>`;
  }

  // Gráfico grande de índices semanales y diarios
  function grafIndices(sem, diario) {
    const W = Math.max(320, Math.min(1100, (document.documentElement.clientWidth || 720) - 72)), H = W < 500 ? 210 : 240, m = {l: 30, r: 8, t: 10, b: 22};
    if (!sem || sem.length < 2) return "";
    const t0 = Date.parse(sem[0].semana), dias = (diario && diario.serie) || [];
    const t1 = Math.max(Date.parse(sem[sem.length - 1].semana), dias.length ? Date.parse(dias[dias.length - 1].fecha) : 0);
    const todos = sem.flatMap(s => ["nino12", "nino3", "nino34"].map(k => s[k])).concat(dias.flatMap(d => [d.nino12, d.nino3, d.nino34])).filter(v => v != null);
    const hi = Math.ceil(Math.max(2.5, ...todos)), lo = Math.floor(Math.min(-0.5, ...todos));
    const X = t => m.l + ((t - t0) / (t1 - t0)) * (W - m.l - m.r), Y = v => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Índices Niño de las últimas semanas">`;
    // bandas de intensidad (umbrales de la NOAA)
    [[0.5, 1, "#FDF1EA"], [1, 1.5, "#FBE1D3"], [1.5, 2, "#F8CDB8"], [2, hi, "#F4B9A0"]].forEach(([a, b, c]) => {
      if (a < hi) s += `<rect x="${m.l}" width="${W - m.l - m.r}" y="${Y(Math.min(b, hi))}" height="${Y(a) - Y(Math.min(b, hi))}" fill="${c}" opacity=".55"/>`;
    });
    [[0.5, "débil"], [1.5, "fuerte"], [2, "muy fuerte"]].forEach(([v, t]) => { if (v < hi) s += `<text x="${W - m.r - 4}" y="${Y(v) - 3}" text-anchor="end" style="font-size:10px">${t}</text>`; });
    for (let v = lo; v <= hi; v++) s += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="${v === 0 ? "#999" : "#E8E8E8"}" stroke-width="1"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${v > 0 ? "+" : ""}${v}</text>`;
    // marcas de mes
    const d0 = new Date(t0); d0.setUTCDate(1); d0.setUTCMonth(d0.getUTCMonth() + 1);
    for (let d = d0; d.getTime() <= t1; d.setUTCMonth(d.getUTCMonth() + 1)) s += `<text x="${X(d.getTime())}" y="${H - 6}" text-anchor="middle">${MESES[d.getUTCMonth()]}</text>`;
    ["nino34", "nino3", "nino12"].forEach(k => {
      const p = sem.filter(x => x[k] != null).map(x => `${X(Date.parse(x.semana)).toFixed(1)},${Y(x[k]).toFixed(1)}`);
      s += `<polyline points="${p.join(" ")}" fill="none" stroke="${COLOR[k]}" stroke-width="2.6" stroke-linejoin="round"/>`;
      sem.forEach(x => { if (x[k] != null) s += `<circle cx="${X(Date.parse(x.semana))}" cy="${Y(x[k])}" r="2.4" fill="${COLOR[k]}"/>`; });
      if (dias.length) {
        const q = dias.filter(x => x[k] != null).map(x => `${X(Date.parse(x.fecha)).toFixed(1)},${Y(x[k]).toFixed(1)}`);
        s += `<polyline points="${q.join(" ")}" fill="none" stroke="${COLOR[k]}" stroke-width="1.6" stroke-dasharray="3 3" opacity=".9"/>`;
      }
    });
    return s + "</svg>";
  }

  // Rueda de la MJO (fases 1–8) con la trayectoria de los últimos días
  function ruedaMJO(serie) {
    const R = 62, C = 70, esc_ = 22;
    let s = `<svg viewBox="0 0 140 140" role="img" aria-label="Fase de la MJO">`;
    s += `<circle cx="${C}" cy="${C}" r="${R}" fill="#FAFAFA" stroke="#E3E3E3"/><circle cx="${C}" cy="${C}" r="${esc_}" fill="#fff" stroke="#DDD" stroke-dasharray="2 3"/>`;
    for (let i = 0; i < 4; i++) { const a = i * Math.PI / 4; s += `<line x1="${C - R * Math.cos(a)}" y1="${C - R * Math.sin(a)}" x2="${C + R * Math.cos(a)}" y2="${C + R * Math.sin(a)}" stroke="#EEE"/>`; }
    for (let f = 1; f <= 8; f++) { const a = (-180 + 45 * (f - 1) + 22.5) * Math.PI / 180; const r = R - 10; s += `<text x="${C + r * Math.cos(a)}" y="${C - r * Math.sin(a) + 3.5}" text-anchor="middle"${f === 8 || f === 1 ? ' style="fill:#B5161C"' : ""}>${f}</text>`; }
    const pts = (serie || []).slice(-30).map(d => { const x = d.pc2, y = -d.pc1, k = Math.min(1, (R - 4) / (esc_ * Math.hypot(x, y) || 1)); return [C + x * esc_ * k, C - y * esc_ * k]; });
    if (pts.length > 1) {
      s += `<polyline points="${pts.map(p => p.map(v => v.toFixed(1)).join(",")).join(" ")}" fill="none" stroke="#7A4FB5" stroke-width="1.8" opacity=".7"/>`;
      const u = pts[pts.length - 1]; s += `<circle cx="${u[0]}" cy="${u[1]}" r="5" fill="#7A4FB5" stroke="#fff" stroke-width="2"/>`;
    }
    return s + "</svg>";
  }

  // ── tarjeta de El Niño ──────────────────────────────────────────────────
  function promedioPuertos(puertos, campo, i) {
    const dias = {};
    Object.values(puertos || {}).forEach(p => (p[campo] || []).forEach(f => { if (f[i] != null) (dias[f[0]] = dias[f[0]] || []).push(f[i]); }));
    return Object.keys(dias).sort().map(d => [d, dias[d].reduce((a, b) => a + b, 0) / dias[d].length]);
  }

  function tarjeta(n) {
    const of = n.oficial, ix = n.indices || {}, gal = n.galapagos || {}, est = n.estado_noaa;
    const sstGal = promedioPuertos(n.puertos, "sst", 2), slaGal = promedioPuertos(n.puertos, "sla", 1);
    const oni = ix.oni || [], uOni = oni[oni.length - 1], dia = ix.diario, sem = ix.semanal || [];
    let h = `<div class="n-card"><div class="n-cab"><div><div class="n-kick">El Niño 2026 · el mar alrededor de Galápagos</div><h2>${gal.anom == null ? "El Niño y el mar" : gal.anom >= 2 ? "El mar está muy caliente" : gal.anom >= 0.5 ? "El mar está más caliente que lo normal" : gal.anom <= -0.5 ? "El mar está más frío que lo normal" : "El mar está cerca de lo normal"}</h2>` +
      `<p class="n-sub">Actualizado ${fechaHora(n.generado)} (hora de Galápagos)</p></div></div>`;
    // voz oficial
    if (of) {
      h += `<div class="n-of"><div class="ico">${ICON.escudo}</div><div><div class="inst"><b>ERFEN · VOZ OFICIAL</b><span>${esc(of.fuente || "Comité ERFEN")}${of.numero ? " · boletín " + esc(of.numero) : ""}${of.emitido ? " · " + fecha(of.emitido) : ""}</span>` +
        (of.nivel ? `<span class="niv">${esc(of.nivel)}</span>` : "") + `</div><p>${esc(of.resumen || of.titulo || "Hay un boletín ERFEN reciente.")}</p>` +
        (of.enlace ? `<a href="${esc(of.enlace)}" target="_blank" rel="noopener">Leer el boletín completo →</a>` : "") +
        (of.leido_por_modelo && !of.revisado ? `<div class="n-sub" style="margin-top:4px">Resumen hecho por un modelo de lenguaje a partir del PDF; manda el documento.</div>` : "") + `</div></div>`;
    } else {
      h += `<div class="n-of vacio"><div class="ico">${ICON.escudo}</div><div><div class="inst"><b>ERFEN · VOZ OFICIAL</b></div><p>Todavía no hay un boletín del comité ERFEN cargado. Lo que sigue son datos de satélite y boyas de la NOAA: contexto, no un pronunciamiento oficial.</p></div></div>`;
    }
    // cifras
    h += `<div class="n-cifras">`;
    h += `<div class="n-cif caliente"><span class="chip">satélite</span><div class="t">${ICON.termo} Mar en Galápagos</div><div class="v">${num(gal.anom, 1, true)}<small>°C</small></div>` +
      `<div class="d">${gal.anom != null && gal.anom < 0 ? "más frío" : "más caliente"} que lo normal de 1985–2012 · ${fecha(gal.fecha)}</div><div class="g">${linea(sstGal.map(x => x[1]), {color: "#B2182B"})}</div></div>`;
    h += `<div class="n-cif mar"><span class="chip">altimetría</span><div class="t">${ICON.ola} Nivel del mar</div><div class="v">${num(gal.sla_cm, 0, true)}<small>cm</small></div>` +
      `<div class="d">sobre el promedio: la pleamar sube más que en la tabla</div><div class="g">${linea(slaGal.map(x => x[1]), {color: "#3F007D"})}</div></div>`;
    if (dia) h += `<div class="n-cif"><span class="chip">diario</span><div class="t">${ICON.globo} Niño 1+2</div><div class="v">${num(dia.nino12, 1, true)}<small>°C</small></div>` +
      `<div class="d">frente a Ecuador y Perú · estimación propia al ${fecha(dia.fecha)}${ix.ultima_semana ? " · NOAA semanal " + num(ix.ultima_semana.nino12.anom, 1, true) : ""}</div>` +
      `<div class="g">${linea((dia.serie || []).map(x => x.nino12), {color: "#B5161C"})}</div></div>`;
    if (uOni) h += `<div class="n-cif"><span class="chip">mensual</span><div class="t">${ICON.barras} ONI (NOAA)</div><div class="v">${num(uOni.anom, 2, true)}<small>°C</small></div>` +
      `<div class="d">${esc(n.categoria_oni || "")} · ${uOni.temporada} ${uOni.anio}</div><div class="g">${barras(oni.slice(-36).map(x => x.anom))}</div></div>`;
    h += `</div>`;
    // estado de la NOAA
    if (est) h += `<div class="n-estado"><span class="n-pill"><span class="pt"></span><b>NOAA:</b> ${esc(est.estado)}${est.fecha ? " (" + fecha(est.fecha) + ")" : ""}</span>` +
      (est.intensidad_esperada ? `<span class="n-pill">Espera un evento <b>${esc(est.intensidad_esperada)}</b> hasta el verano</span>` : "") + `</div>`;
    // gráfico de índices
    if (sem.length > 1) h += `<div class="n-graf"><h3>Las regiones Niño, semana a semana</h3><div class="n-ley">` +
      ["nino12", "nino3", "nino34"].map(k => `<span><i style="background:${COLOR[k]}"></i>${NOMBRE[k]}</span>`).join("") +
      `<span><i style="background:repeating-linear-gradient(90deg,#666 0 3px,transparent 3px 6px)"></i>diario (estimación propia)</span></div>${grafIndices(sem, dia)}` +
      `<p class="n-sub">Anomalía en °C respecto de 1991–2020. Puntos: índice semanal de la NOAA. Las bandas marcan los umbrales de intensidad de la NOAA (con el ONI).</p></div>`;
    // boyas y MJO
    const boyas = Object.entries(n.boyas || {}).filter(([, b]) => b.d20 && b.d20.length);
    const mjo = n.mjo || {};
    if (boyas.length || mjo.ultimo) {
      h += `<div class="n-dos">`;
      if (boyas.length) {
        const fondo = 200;
        h += `<div class="n-sec"><h3>¿A qué profundidad empieza el agua fría?</h3><p>Isoterma de 20 °C en las boyas TAO. Con El Niño el agua cálida se hunde y el afloramiento frío ya no llega a la superficie.</p><div class="n-boyas">` +
          boyas.map(([k, b]) => {
            const act = b.d20[b.d20.length - 1][1], nor = b.normal_m;
            const nombre = k.replace(/^(\d+)([ns])(\d+)w$/, (_, a, hm, o) => (a === "0" ? "0°" : a + "° " + hm.toUpperCase()) + " · " + o + "° O");
            return `<div class="n-boya"><div class="col">` + (nor != null ? `<div class="nor" style="top:${Math.min(98, 100 * nor / fondo)}%"></div><span style="top:calc(${Math.min(98, 100 * nor / fondo)}% - 14px)">normal ${Math.round(nor)} m</span>` : "") +
              `<div class="act" style="top:${Math.min(99, 100 * act / fondo)}%"></div></div><b>${Math.round(act)} m</b>${esc(nombre)}</div>`;
          }).join("") + `</div><p class="n-sub" style="margin-top:8px">Último dato ${fecha(boyas[0][1].d20[boyas[0][1].d20.length - 1][0])}. Las boyas llegan con unas tres semanas de retraso. Normal: promedio del mismo mes, 1991–2020.</p></div>`;
      }
      if (mjo.ultimo) h += `<div class="n-sec"><h3>Oscilación de Madden-Julian</h3><div class="n-mjo">${ruedaMJO(mjo.serie)}<div><p>${esc(mjo.frase || "")}</p>` +
        `<p class="n-sub" style="margin-top:6px">Un pulso de nubes y lluvias que da la vuelta al trópico en 30 a 60 días. En las fases 8 y 1 (en rojo) pasa por el Pacífico este y puede sumar lluvias. Último dato ${fecha(mjo.ultimo.fecha)}.</p></div></div></div>`;
      h += `</div>`;
    }
    h += `<div class="n-aviso">${ICON.info}<div>${esc(n.aviso || "")}</div></div>`;
    const f = Object.entries(n.fuentes || {}).filter(([, ok]) => ok).map(([k]) => k);
    if (f.length) h += `<div class="n-fuentes">Fuentes: ${f.map(esc).join(" · ")}.</div>`;
    if (n.errores && Object.keys(n.errores).length) h += `<div class="n-error">Sin datos esta vez: ${Object.keys(n.errores).map(esc).join(", ")}.</div>`;
    return h + `</div>`;
  }

  // ── mapa ────────────────────────────────────────────────────────────────
  function cargarLeaflet() {
    if (window.L) return Promise.resolve();
    const css = document.createElement("link"); css.rel = "stylesheet"; css.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"; document.head.appendChild(css);
    return new Promise((ok, mal) => { const s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"; s.onload = ok; s.onerror = mal; document.head.appendChild(s); });
  }

  // Pinta la rejilla en un lienzo con las filas en Mercator (lo que usa Leaflet), para que cada celda quede en su sitio.
  function capaRejilla(r, pal) {
    const ancho = r.nlon, n = r.lat_n + r.paso_lat / 2, s = r.lat_n - (r.nlat - 0.5) * r.paso_lat;
    const merc = lat => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
    const yN = merc(n), yS = merc(s), alto = Math.max(r.nlat, Math.round(r.nlat * (yN - yS) / ((n - s) * Math.PI / 180)));
    const cv = document.createElement("canvas"); cv.width = ancho; cv.height = alto;
    const cx = cv.getContext("2d"), img = cx.createImageData(ancho, alto);
    for (let py = 0; py < alto; py++) {
      const y = yN - (py + 0.5) / alto * (yN - yS), lat = (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180 / Math.PI;
      const i = Math.min(r.nlat - 1, Math.max(0, Math.round((r.lat_n - lat) / r.paso_lat)));
      for (let j = 0; j < ancho; j++) {
        const v = r.valores[i * r.nlon + j], k = 4 * (py * ancho + j);
        if (v == null) continue;
        const c = color(pal, v / r.escala); img.data[k] = c[0]; img.data[k + 1] = c[1]; img.data[k + 2] = c[2]; img.data[k + 3] = 225;
      }
    }
    cx.putImageData(img, 0, 0);
    const o = r.lon_o - r.paso_lon / 2, e = r.lon_o + (r.nlon - 0.5) * r.paso_lon;
    return L.imageOverlay(cv.toDataURL(), [[s, o], [n, e]], {opacity: 0.92, interactive: false, className: "n-rejilla"});
  }
  function valorEn(r, lat, lon) {
    if (!r) return null;
    const i = Math.round((r.lat_n - lat) / r.paso_lat), j = Math.round((lon - r.lon_o) / r.paso_lon);
    if (i < 0 || j < 0 || i >= r.nlat || j >= r.nlon) return null;
    const v = r.valores[i * r.nlon + j]; return v == null ? null : v / r.escala;
  }
  const coordTxt = (lat, lon) => `${num(Math.abs(lat), 1)}° ${lat >= 0 ? "N" : "S"} · ${num(Math.abs(lon), 1)}° O`;

  function tarjetaMapa(m, z) {
    let h = `<div class="n-card"><div class="n-mapa-cab"><div><div class="n-kick">Mapa · Pacífico este</div><h2>¿Cuánto más caliente está el mar?</h2>` +
      `<p class="n-sub">${m.sst_anom ? "Satélite del " + fecha(m.sst_anom.fecha) : ""}${z && z.analisis ? " · ZCIT y ondas del análisis de las " + fechaHora(z.analisis) : ""}</p></div>` +
      `<div class="n-capas" role="group" aria-label="Capa del mapa"><button class="on" data-capa="sst">Temperatura</button>${m.sla ? '<button data-capa="sla">Nivel del mar</button>' : ""}</div></div>` +
      `<div class="n-mapa"><div class="n-lienzo" style="height:100%"></div><div class="n-cursor"></div><div class="n-lee"></div></div>`;
    if (z) {
      h += `<div class="n-zcit">` + (z.frases || []).map((f, i) => `<div class="f">${/onda/i.test(f) ? ICON.onda : ICON.nube}<div>${esc(f)}</div></div>`).join("");
      if (z.resumen_ia && z.resumen_ia.texto) h += `<div class="ia">${esc(z.resumen_ia.texto)} <span class="n-sub">(resumen automático del texto del NHC)</span></div>`;
      h += `</div>`;
    }
    h += `<div class="n-aviso">${ICON.info}<div>${esc(m.aviso || "")} ${z ? esc(z.aviso || "") : ""} El análisis de la ZCIT del NHC llega hasta 3,4° S: una rama al sur del ecuador puede no aparecer.</div></div></div>`;
    return h;
  }

  function leyenda(el, capa) {
    const sst = capa === "sst", pal = sst ? PAL_SST : PAL_SLA;
    el.innerHTML = `<b>${sst ? "Anomalía de temperatura del mar (°C)" : "Anomalía del nivel del mar (cm)"}</b><div class="barra" style="background:${gradiente(pal)}"></div>` +
      `<div class="esc">${pal.filter((_, i) => i % 2 === 0 || i === pal.length - 1).map(p => `<span>${p[0] > 0 ? "+" : ""}${p[0]}</span>`).join("")}</div>` +
      `<div style="margin-top:4px;display:flex;gap:10px;flex-wrap:wrap"><span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#0B4F8A" stroke-width="3" stroke-dasharray="6 4"/></svg> ZCIT</span>` +
      `<span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#7A4FB5" stroke-width="3"/></svg> onda tropical</span>` +
      `<span><svg width="14" height="10"><rect x="1" y="1" width="12" height="8" fill="none" stroke="#1D1D1B" stroke-width="1.5" stroke-dasharray="3 2"/></svg> región Niño</span></div>`;
  }

  function montarMapa(raiz, m, z) {
    const caja = raiz.querySelector(".n-lienzo"), cursor = raiz.querySelector(".n-cursor"), lee = raiz.querySelector(".n-lee");
    const tactil = matchMedia("(pointer:coarse)").matches;
    const mapa = L.map(caja, {scrollWheelZoom: false, dragging: !tactil, zoomSnap: 0.5, worldCopyJump: false, minZoom: 3, maxZoom: 10});
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {maxZoom: 16, attribution: "Esri · NOAA"}).addTo(mapa);
    const capas = {sst: L.layerGroup(), sla: L.layerGroup()};
    if (m.sst_anom) capas.sst.addLayer(capaRejilla(m.sst_anom, PAL_SST));
    if (m.sst_anom_islas) capas.sst.addLayer(capaRejilla(m.sst_anom_islas, PAL_SST));
    if (m.sla) capas.sla.addLayer(capaRejilla(m.sla, PAL_SLA));
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {maxZoom: 16, pane: "shadowPane"}).addTo(mapa);
    let activa = "sst"; capas.sst.addTo(mapa); leyenda(lee, "sst");

    // regiones Niño
    Object.values(m.regiones || {}).forEach(r => {
      L.rectangle([[r.s, r.o], [r.n, r.e]], {color: "#1D1D1B", weight: 1.5, dashArray: "5 4", fill: false, interactive: false}).addTo(mapa);
      L.marker([r.n, r.o], {icon: L.divIcon({className: "n-etq", html: esc(r.nombre), iconSize: null, iconAnchor: [-4, -4]}), interactive: false}).addTo(mapa);
    });
    // ZCIT, convección y ondas
    if (z) {
      (z.conveccion || []).forEach(c => L.rectangle([[c.s, c.o], [c.n, c.e]], {color: "#0B4F8A", weight: 0, fillColor: "#0B4F8A", fillOpacity: 0.12, interactive: false}).addTo(mapa));
      (z.lineas || []).forEach(l => {
        L.polyline(l.puntos, {color: "#fff", weight: 6, opacity: 0.8, interactive: false}).addTo(mapa);
        L.polyline(l.puntos, {color: "#0B4F8A", weight: 3, dashArray: l.tipo === "zcit" ? "8 6" : "2 6", lineCap: "round", interactive: false}).addTo(mapa);
      });
      const lz = (z.lineas || []).find(l => l.puntos.some(p => p[1] >= -100));
      if (lz) { const p = lz.puntos[Math.min(1, lz.puntos.length - 1)]; L.marker(p, {icon: L.divIcon({className: "n-etq zc", html: lz.tipo === "zcit" ? "ZCIT" : "Vaguada monzónica", iconSize: null, iconAnchor: [-6, 14]}), interactive: false}).addTo(mapa); }
      (z.ondas || []).forEach(o => {
        const s = o.lat_s != null ? o.lat_s : 0, n = o.lat_n != null ? o.lat_n : 15, pts = o.puntos && o.puntos.length > 1 ? o.puntos : [[s, o.lon], [n, o.lon]];
        L.polyline(pts, {color: "#fff", weight: 7, opacity: 0.8}).addTo(mapa);
        L.polyline(pts, {color: "#7A4FB5", weight: 3.5}).addTo(mapa).bindTooltip(`Onda tropical en ${Math.abs(o.lon)}° O` + (o.velocidad_kt ? `, ${o.velocidad_kt[0]}–${o.velocidad_kt[1]} nudos al oeste` : ""), {sticky: true});
      });
    }
    // boyas y puertos
    Object.entries(m.boyas || {}).forEach(([k, b]) => {
      if (!b.d20) return;
      L.circleMarker([b.lat, b.lon], {radius: 6, color: "#fff", weight: 2, fillColor: "#1D1D1B", fillOpacity: 1}).addTo(mapa)
        .bindTooltip(`Boya TAO ${k.toUpperCase()}: agua de 20 °C a ${Math.round(b.d20[1])} m${b.normal_m ? ` (normal ${Math.round(b.normal_m)} m)` : ""}, ${fecha(b.d20[0])}`);
    });
    Object.values(m.puertos || {}).forEach(p => L.circleMarker([p.lat, p.lon], {radius: 4, color: "#fff", weight: 1.5, fillColor: "#E11B22", fillOpacity: 1}).addTo(mapa).bindTooltip(esc(p.nombre)));

    mapa.fitBounds([[-12, -112], [10, -78]]);
    mapa.on("mousemove", ev => {
      const {lat, lng} = ev.latlng;
      const v = activa === "sst" ? (valorEn(m.sst_anom_islas, lat, lng) ?? valorEn(m.sst_anom, lat, lng)) : valorEn(m.sla, lat, lng);
      cursor.textContent = v == null ? "" : `${num(v, activa === "sst" ? 1 : 0, true)} ${activa === "sst" ? "°C" : "cm"} · ${coordTxt(lat, lng)}`;
    });
    mapa.on("mouseout", () => { cursor.textContent = ""; });
    raiz.querySelectorAll(".n-capas button").forEach(b => b.addEventListener("click", () => {
      if (b.dataset.capa === activa) return;
      mapa.removeLayer(capas[activa]); activa = b.dataset.capa; capas[activa].addTo(mapa); leyenda(lee, activa);
      raiz.querySelectorAll(".n-capas button").forEach(x => x.classList.toggle("on", x === b));
    }));
    return mapa;
  }

  // ── montar ──────────────────────────────────────────────────────────────
  async function montar(el, opciones = {}) {
    const base = opciones.base || "/riesgos/api/clima/", q = opciones.sinCache === false ? "" : "?t=" + Math.floor(Date.now() / 300e3);
    const leer = nombre => fetch(base + nombre + q, {cache: "no-cache"}).then(r => r.ok ? r.json() : null).catch(() => null);
    el.classList.add("nino");
    el.innerHTML = `<div class="n-card"><p class="n-sub">Cargando El Niño…</p></div>`;
    const [n, m, z] = await Promise.all([leer("nino.json"), leer("nino_mapa.json"), leer("zcit.json")]);
    if (!n && !m) { el.innerHTML = `<div class="n-card"><p class="n-sub">Los datos de El Niño no están disponibles ahora.</p></div>`; return null; }
    el.innerHTML = (n ? tarjeta(n) : "") + (m ? tarjetaMapa(m, z) : "");
    if (m && opciones.mapa !== false) {
      try { await cargarLeaflet(); return montarMapa(el, m, z); }
      catch (e) { const c = el.querySelector(".n-mapa"); if (c) c.innerHTML = `<p class="n-sub" style="padding:14px">No se pudo cargar el mapa.</p>`; }
    }
    return null;
  }

  window.NinoPanel = {montar, _interno: {color, linea, barras, valorEn}};
})();
