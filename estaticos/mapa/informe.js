/* Informe: línea del tiempo con todos los reportes y cuánto ha llovido, con filtros.

   Reúne tres fuentes, todas ya públicas:
     - los reportes hechos en este mapa (también los cerrados);
     - los reportes de campo que publica /mapas (capas con «marcador: reporte»);
     - la lluvia por hora de una estación, tal como la publica /clima.
   No hay dos ejes en un mismo gráfico: la lluvia y los reportes van en dos gráficos
   apilados que comparten el eje del tiempo. */
(function () {
  'use strict';
  const SOS = window.SOS, cfg = SOS.cfg, x = SOS.escapar;
  const HORA = 3600000, DIA = 24 * HORA;
  const UTC_GALAPAGOS = -6; // Galápagos no cambia de hora
  const COLOR = { lluvia: '#2f6fb3', reportes: '#c8151b' }; // par validado (daltonismo y contraste)
  const CLASES = { campo: 'Reporte de campo', buena: 'Buena noticia o ayuda (de campo)', riesgo: 'Peligro', bueno: 'Algo bueno', ayuda: 'Donar o colaborar' };
  const ESTACION_POR_ISLA = { 'Santa Cruz': 'ambient/evolucion', 'San Cristóbal': 'gsc/mirador', Isabela: 'darwin/puerto_villamil' };

  const $ = (id) => document.getElementById(id);
  const estado = { reportes: [], estaciones: [], lluvia: { inicio: null, mm: [] }, filtros: { isla: '', zona: '', clase: '', desde: null, hasta: null, estacion: '' } };

  // ── Fechas en hora de Galápagos ───────────────────────────────────────────
  const aLocal = (ms) => new Date(ms + UTC_GALAPAGOS * HORA); // se lee con los métodos getUTC*
  const dosCifras = (n) => String(n).padStart(2, '0');
  const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const horaDe = (ms) => { const d = aLocal(ms); return `${dosCifras(d.getUTCHours())}:${dosCifras(d.getUTCMinutes())}`; };
  const diaCorto = (ms) => { const d = aLocal(ms); return `${d.getUTCDate()} ${MESES[d.getUTCMonth()]}`; };
  const diaLargo = (ms) => { const d = aLocal(ms); return `${DIAS[d.getUTCDay()]} ${d.getUTCDate()} de ${MESES[d.getUTCMonth()]}`; };
  const claveDia = (ms) => { const d = aLocal(ms); return `${d.getUTCFullYear()}-${dosCifras(d.getUTCMonth() + 1)}-${dosCifras(d.getUTCDate())}`; };
  const inicioDelDia = (clave) => Date.parse(`${clave}T00:00:00-06:00`);
  const mm = (v) => (v >= 100 ? Math.round(v).toLocaleString('es') : (Math.round(v * 10) / 10).toLocaleString('es'));

  function islaDe(lon, lat) {
    if (lon < -90.7) return 'Isabela';
    if (lon > -89.9) return 'San Cristóbal';
    if (lat < -1.15) return 'Floreana';
    return 'Santa Cruz';
  }

  // ── Carga ─────────────────────────────────────────────────────────────────
  async function cargarPropios() {
    const d = await fetch(cfg.todos, { cache: 'no-store' }).then((r) => r.json());
    return d.features.map((f) => {
      const p = f.properties, [lon, lat] = f.geometry.coordinates;
      const estados = { por_verificar: 'por verificar', confirmado: 'confirmado', bajando: 'bajando', cerrado: 'cerrado' };
      return {
        t: p.visto * 1000, clase: p.clase, titulo: p.tipo_nombre, lugar: p.zona || '', zona: p.zona || '', isla: p.isla || islaDe(lon, lat),
        detalle: estados[p.estado] || '', texto: '', foto: '', nFotos: 0, lon, lat, enlace: `${cfg.mapa}?r=${encodeURIComponent(p.id)}`,
      };
    });
  }

  // Los reportes de campo salen de las capas de /mapas marcadas como reporte. La fecha del
  // evento va en la carpeta de fotos de la capa (reportes/AAAA-MM-DD/) y cada reporte trae su hora.
  async function cargarDeCampo() {
    const base = cfg.capasUrl;
    const { v } = await SOS.versionDeMapas();
    const manifiesto = await fetch(base + 'capas.json', { cache: 'no-cache' }).then((r) => r.json());
    const capas = manifiesto.grupos.flatMap((g) => g.capas).filter((c) => ['reporte', 'corazon'].includes(c.marcador) && c.archivo);
    const lista = [];
    for (const capa of capas) {
      const fecha = ((capa.fotos_base || '').match(/\d{4}-\d{2}-\d{2}/) || [])[0];
      if (!fecha) continue;
      const datos = `${base}datos/${cfg.capasVariante}/`;
      const d = await fetch(datos + capa.archivo + v).then((r) => r.json()).catch(() => ({ features: [] }));
      for (const f of d.features) {
        const p = f.properties, [lon, lat] = f.geometry.coordinates;
        if (!/^\d{1,2}:\d{2}$/.test(p.hora || '')) continue;
        const fotos = Array.isArray(p.fotos) ? p.fotos : [];
        lista.push({
          t: Date.parse(`${fecha}T${p.hora.padStart(5, '0')}:00-06:00`), clase: capa.marcador === 'corazon' ? 'buena' : 'campo', titulo: p.titulo || capa.titulo,
          lugar: p.lugar || '', zona: p.barrio || '', isla: islaDe(lon, lat),
          detalle: p.gravedad_txt ? 'gravedad ' + p.gravedad_txt.toLowerCase() : [p.estado_txt, p.autor].filter(Boolean).join(' · '),
          texto: p.descripcion || '', foto: fotos.length ? datos + (capa.fotos_base || '') + (fotos[0].mini || fotos[0].archivo) : '',
          nFotos: fotos.length, lon, lat, enlace: `${cfg.mapa}#${lat.toFixed(5)},${lon.toFixed(5)},17.5`,
        });
      }
    }
    return lista;
  }

  async function cargarLluvia() {
    const f = estado.filtros;
    const q = `?desde=${new Date(f.desde).toISOString()}&hasta=${new Date(f.hasta).toISOString()}&estacion=${encodeURIComponent(f.estacion)}`;
    try {
      const d = await fetch(cfg.lluviaHoraria + q).then((r) => r.json());
      estado.estaciones = d.estaciones || [];
      estado.lluvia = { inicio: d.inicio ? Date.parse(d.inicio) : null, mm: d.mm || [], nota: d.nota || '' };
    } catch (e) { estado.lluvia = { inicio: null, mm: [], nota: '' }; }
  }

  // ── Filtros ───────────────────────────────────────────────────────────────
  function filtrados() {
    const f = estado.filtros;
    return estado.reportes.filter((r) => r.t >= f.desde && r.t < f.hasta
      && (!f.isla || r.isla === f.isla) && (!f.zona || r.zona === f.zona) && (!f.clase || r.clase === f.clase))
      .sort((a, b) => b.t - a.t);
  }
  function opciones(select, valores, todas, elegido) {
    select.innerHTML = `<option value="">${x(todas)}</option>` + valores.map((v) => {
      const [valor, texto] = Array.isArray(v) ? v : [v, v];
      return `<option value="${x(valor)}"${valor === elegido ? ' selected' : ''}>${x(texto)}</option>`;
    }).join('');
  }
  function pintarFiltros() {
    const f = estado.filtros;
    const enIsla = estado.reportes.filter((r) => !f.isla || r.isla === f.isla);
    opciones($('f-isla'), [...new Set(estado.reportes.map((r) => r.isla).concat(estado.estaciones.map((e) => e.isla)).filter(Boolean))].sort(), 'Todas las islas', f.isla);
    opciones($('f-zona'), [...new Set(enIsla.map((r) => r.zona).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es')), 'Todas las zonas', f.zona);
    opciones($('f-clase'), Object.entries(CLASES), 'Todo', f.clase);
    const estaciones = estado.estaciones.filter((e) => !f.isla || e.isla === f.isla);
    $('f-estacion').innerHTML = estaciones.map((e) => `<option value="${x(e.id)}"${e.id === f.estacion ? ' selected' : ''}>${x(e.nombre.split(' · ')[0])}${f.isla ? '' : ' (' + x(e.isla) + ')'}</option>`).join('')
      || '<option value="">Sin estaciones con lluvia por hora</option>';
    $('f-desde').value = claveDia(f.desde);
    $('f-hasta').value = claveDia(f.hasta - 1);
    for (const b of document.querySelectorAll('[data-dias]')) b.setAttribute('aria-pressed', String(Number(b.dataset.dias) === f.atajo));
  }

  // ── Gráficos ──────────────────────────────────────────────────────────────
  // Por hora hasta 5 días; con más, por día. Cada tramo es { t, lluvia, sinDato, reportes }.
  function tramos(lista) {
    const f = estado.filtros, porDia = f.hasta - f.desde > 5 * DIA, paso = porDia ? DIA : HORA;
    const n = Math.round((f.hasta - f.desde) / paso);
    const ts = Array.from({ length: n }, (_, i) => ({ t: f.desde + i * paso, lluvia: 0, horas: 0, reportes: 0 }));
    const { inicio, mm: serie } = estado.lluvia;
    if (inicio !== null) {
      serie.forEach((v, i) => {
        const k = Math.floor((inicio + i * HORA - f.desde) / paso);
        if (k >= 0 && k < n && v != null) { ts[k].lluvia += v; ts[k].horas++; }
      });
    }
    for (const r of lista) { const k = Math.floor((r.t - f.desde) / paso); if (k >= 0 && k < n) ts[k].reportes++; }
    return { ts, porDia, paso };
  }
  const techo = (v) => { // tope redondo para el eje
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    return [1, 2, 5, 10].map((m) => m * p).find((m) => m >= v);
  };

  function grafico(svg, ts, campo, color, unidad, porDia) {
    // El dibujo mide lo mismo que el hueco en pantalla: así la letra de los ejes no se encoge en el teléfono.
    const W = Math.max(280, Math.round(svg.getBoundingClientRect().width) || 720), H = 150, m = { i: 30, d: 6, a: 8, b: 22 };
    const ancho = W - m.i - m.d, alto = H - m.a - m.b, n = ts.length;
    const max = techo(Math.max(...ts.map((t) => t[campo]), 0));
    const w = ancho / n, grosor = Math.max(1, Math.min(18, w - 2)); // barras delgadas, con 2 px de aire
    const y = (v) => m.a + alto - (v / max) * alto;
    let h = '';
    // Rejilla discreta: tres líneas. En los conteos pequeños, solo las de números enteros.
    for (const v of (campo === 'reportes' && max % 2 ? [0, max] : [0, max / 2, max])) {
      h += `<line x1="${m.i}" x2="${W - m.d}" y1="${y(v)}" y2="${y(v)}" stroke="#e5e5e5" stroke-width="1"/>`;
      h += `<text x="${m.i - 6}" y="${y(v) + 3.5}" text-anchor="end" class="eje">${max >= 4 || v === 0 ? Math.round(v) : v.toLocaleString('es')}</text>`;
    }
    ts.forEach((t, i) => {
      const cx = m.i + i * w + w / 2;
      if (t[campo] > 0) {
        const alt = Math.max(1.5, (t[campo] / max) * alto), r = Math.min(3, grosor / 2, alt);
        // Extremo redondeado arriba y base recta sobre la línea cero.
        h += `<path d="M${cx - grosor / 2} ${m.a + alto}v${-(alt - r)}q0 ${-r} ${r} ${-r}h${grosor - 2 * r}q${r} 0 ${r} ${r}v${alt - r}z" fill="${color}"/>`;
      } else if (campo === 'lluvia' && t.horas === 0) {
        h += `<line x1="${cx - grosor / 2}" x2="${cx + grosor / 2}" y1="${m.a + alto - 3}" y2="${m.a + alto - 3}" stroke="#bdbdbd" stroke-width="1.5" stroke-dasharray="2 2"/>`; // sin dato
      }
      // Marcas del eje del tiempo: cada 6 h (o cada día), y el día al empezar.
      const d = aLocal(t.t), hora = d.getUTCHours();
      const cada = Math.max(1, Math.ceil(n * (porDia ? 46 : 40) / ancho)); // sitio para una etiqueta cada tantos tramos
      const marca = porDia ? i % cada === 0 : hora % ([3, 6, 12, 24].find((p) => p >= cada) || 24) === 0;
      if (marca) {
        const texto = porDia ? diaCorto(t.t) : hora === 0 ? diaCorto(t.t) : dosCifras(hora) + ' h';
        h += `<text x="${cx - (porDia ? 0 : w / 2)}" y="${H - 6}" text-anchor="middle" class="eje${!porDia && hora === 0 ? ' fuerte' : ''}">${texto}</text>`;
        if (!porDia && hora === 0) h += `<line x1="${cx - w / 2}" x2="${cx - w / 2}" y1="${m.a}" y2="${m.a + alto}" stroke="#d4d4d4" stroke-width="1"/>`;
      }
    });
    h += `<line x1="${m.i}" x2="${W - m.d}" y1="${m.a + alto}" y2="${m.a + alto}" stroke="#8a8a8a" stroke-width="1"/>`;
    h += `<rect class="cursor" x="0" y="${m.a}" width="${Math.max(1, w)}" height="${alto}" fill="#000" opacity="0" pointer-events="none"/>`;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.innerHTML = h;
    svg._geo = { m, w, n, W };
  }

  // Al pasar el dedo o el ratón: una franja sobre el tramo y el detalle de ese momento.
  function conectarCursor(ts, porDia) {
    const pista = $('pista-grafico');
    const svgs = [$('g-lluvia'), $('g-reportes')];
    const mover = (e, svg) => {
      const g = svg._geo, caja = svg.getBoundingClientRect();
      const px = ((e.touches ? e.touches[0].clientX : e.clientX) - caja.left) / caja.width * g.W;
      const i = Math.min(g.n - 1, Math.max(0, Math.floor((px - g.m.i) / g.w)));
      const t = ts[i];
      for (const s of svgs) { const c = s.querySelector('.cursor'); c.setAttribute('x', s._geo.m.i + i * s._geo.w); c.setAttribute('opacity', '0.07'); }
      const cuando = porDia ? diaLargo(t.t) : `${diaCorto(t.t)}, ${horaDe(t.t)} a ${horaDe(t.t + HORA)}`;
      const lluvia = t.horas === 0 ? 'sin dato de lluvia' : `${mm(t.lluvia)} mm de lluvia`;
      pista.innerHTML = `<b>${x(cuando)}</b><span><i style="background:${COLOR.lluvia}"></i>${lluvia}</span><span><i style="background:${COLOR.reportes}"></i>${t.reportes} ${t.reportes === 1 ? 'reporte' : 'reportes'}</span>`;
      pista.hidden = false;
      const marco = $('graficos').getBoundingClientRect();
      const izq = caja.left - marco.left + (g.m.i + (i + 0.5) * g.w) / g.W * caja.width;
      pista.style.left = Math.min(marco.width - pista.offsetWidth - 4, Math.max(4, izq - pista.offsetWidth / 2)) + 'px';
    };
    const salir = () => { pista.hidden = true; for (const s of svgs) s.querySelector('.cursor').setAttribute('opacity', '0'); };
    for (const svg of svgs) {
      svg.onmousemove = (e) => mover(e, svg);
      svg.ontouchstart = svg.ontouchmove = (e) => mover(e, svg);
      svg.onmouseleave = salir;
    }
  }

  // ── Lista: la línea del tiempo ────────────────────────────────────────────
  function linea(lista) {
    if (!lista.length) return '<p class="vacio"><b>Sin reportes</b> con estos filtros. Prueba con más días o con todas las islas.</p>';
    let h = '', dia = '';
    for (const r of lista) {
      const d = claveDia(r.t);
      if (d !== dia) { if (dia) h += '</ol>'; dia = d; h += `<h3 class="dia">${x(diaLargo(r.t))}<span>${lista.filter((q) => claveDia(q.t) === d).length}</span></h3><ol class="linea">`; }
      const sub = [r.lugar, r.detalle].filter(Boolean).join(' · ');
      h += `<li class="hito clase-${r.clase}"><time>${horaDe(r.t)}</time><a href="${x(r.enlace)}">
        ${r.foto ? `<img src="${x(r.foto)}" alt="" loading="lazy">` : ''}
        <span class="hito-texto"><span class="hito-clase">${x(CLASES[r.clase] || '')}${r.nFotos > 1 ? ` · ${r.nFotos} fotos` : ''}</span>
        <b>${x(r.titulo)}</b>${sub ? `<span class="hito-sub">${x(sub)}</span>` : ''}${r.texto ? `<span class="hito-desc">${x(r.texto)}</span>` : ''}</span></a></li>`;
    }
    return h + '</ol>';
  }

  function pintar() {
    const lista = filtrados(), { ts, porDia } = tramos(lista);
    const total = ts.reduce((s, t) => s + t.lluvia, 0), conDato = ts.some((t) => t.horas > 0);
    const pico = ts.reduce((a, t) => (t.lluvia > a.lluvia ? t : a), ts[0]);
    const est = estado.estaciones.find((e) => e.id === estado.filtros.estacion);
    $('cifra-lluvia').textContent = conDato ? mm(total) + ' mm' : 'sin dato';
    $('cifra-lluvia-sub').textContent = conDato && pico.lluvia > 0 ? `más fuerte: ${mm(pico.lluvia)} mm ${porDia ? 'el ' + diaCorto(pico.t) : 'a las ' + horaDe(pico.t) + ' del ' + diaCorto(pico.t)}` : 'en el periodo';
    $('cifra-reportes').textContent = lista.length.toLocaleString('es');
    $('cifra-reportes-sub').textContent = lista.length ? `con fotos: ${lista.filter((r) => r.nFotos).length}` : 'en el periodo';
    $('titulo-lluvia').textContent = `Lluvia por ${porDia ? 'día' : 'hora'} (mm)${est ? ' · ' + est.nombre.split(' · ')[0] : ''}`;
    $('titulo-reportes').textContent = `Reportes por ${porDia ? 'día' : 'hora'}`;
    grafico($('g-lluvia'), ts, 'lluvia', COLOR.lluvia, 'mm', porDia);
    grafico($('g-reportes'), ts, 'reportes', COLOR.reportes, 'n.º', porDia);
    conectarCursor(ts, porDia);
    $('linea').innerHTML = linea(lista);
    $('nota-lluvia').textContent = estado.lluvia.nota || '';
  }

  async function actualizar(recargarLluvia) {
    if (recargarLluvia) await cargarLluvia();
    pintarFiltros();
    pintar();
  }

  function rango(dias) {
    const f = estado.filtros;
    f.hasta = inicioDelDia(claveDia(Date.now())) + DIA; // hasta el final de hoy
    f.desde = dias ? f.hasta - dias * DIA : Math.min(inicioDelDia('2026-10-30'), ...estado.reportes.map((r) => inicioDelDia(claveDia(r.t))));
    if (f.hasta - f.desde > 62 * DIA) f.desde = f.hasta - 62 * DIA;
    f.atajo = dias;
  }

  async function iniciar() {
    const [propios, campo] = await Promise.all([cargarPropios().catch(() => []), cargarDeCampo().catch(() => [])]);
    estado.reportes = propios.concat(campo);
    rango(3);
    await cargarLluvia();
    const f = estado.filtros;
    f.estacion = ESTACION_POR_ISLA['Santa Cruz'];
    if (!estado.estaciones.some((e) => e.id === f.estacion)) f.estacion = (estado.estaciones[0] || {}).id || '';
    await actualizar(true);
    $('informe').removeAttribute('aria-busy');

    $('f-isla').onchange = (e) => {
      f.isla = e.target.value; f.zona = '';
      const propia = ESTACION_POR_ISLA[f.isla] || (estado.estaciones.find((s) => s.isla === f.isla) || {}).id;
      if (propia && estado.estaciones.some((s) => s.id === propia)) f.estacion = propia;
      actualizar(true);
    };
    $('f-zona').onchange = (e) => { f.zona = e.target.value; actualizar(false); };
    $('f-clase').onchange = (e) => { f.clase = e.target.value; actualizar(false); };
    $('f-estacion').onchange = (e) => { f.estacion = e.target.value; actualizar(true); };
    const fechas = () => {
      const d = inicioDelDia($('f-desde').value), h = inicioDelDia($('f-hasta').value) + DIA;
      if (Number.isNaN(d) || Number.isNaN(h) || h <= d) return;
      f.desde = Math.max(d, h - 62 * DIA); f.hasta = h; f.atajo = -1;
      actualizar(true);
    };
    $('f-desde').onchange = $('f-hasta').onchange = fechas;
    for (const b of document.querySelectorAll('[data-dias]')) b.onclick = () => { rango(Number(b.dataset.dias)); actualizar(true); };
    let espera = null; // al girar el teléfono o cambiar el ancho, los gráficos se vuelven a dibujar
    window.addEventListener('resize', () => { clearTimeout(espera); espera = setTimeout(pintar, 200); });
  }
  iniciar();
})();
