/* Línea del tiempo (/riesgos/informe/): todos los reportes y cuánto ha llovido, con filtros.

   Es vertical: cada fila es una hora; a un lado va la lluvia de esa hora y al otro los
   reportes. Los días sin reportes y casi sin lluvia se juntan en una sola fila, así que
   semanas de sol no alargan la página. Arriba, un navegador con todo el periodo lleva a
   cualquier día con un toque.

   Reúne tres fuentes, todas ya públicas:
     - los reportes hechos en este mapa (también los cerrados);
     - los reportes de campo que publica /mapas (capas con «marcador: reporte»);
     - la lluvia por hora de una estación, tal como la publica /clima.
   No hay dos ejes en un mismo gráfico: en el navegador la lluvia sube y los reportes bajan
   desde una misma línea de tiempo, cada uno con su escala dicha en la leyenda. */
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
        t: p.visto * 1000, clase: p.clase, titulo: p.titulo || p.tipo_nombre, lugar: p.zona || '', zona: p.zona || '', isla: p.isla || islaDe(lon, lat),
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
  }

  // ── Datos por día y por hora ──────────────────────────────────────────────
  const CALMA_MM = 5;      // un día sin reportes y con menos lluvia que esto (lluvia débil) se junta con sus vecinos
  const HORA_MM = 1;       // una hora sin reportes y con menos lluvia que esto no ocupa fila: va al resumen del día
  function porDias(lista) {
    const f = estado.filtros, ahora = Date.now(), dias = [], indice = new Map();
    for (let t = f.desde; t < f.hasta; t += DIA) {
      const d = { t, clave: claveDia(t), lluvia: 0, conDato: 0, sinDato: 0, reportes: [], horas: new Map() };
      dias.push(d); indice.set(d.clave, d);
    }
    const horaDeDia = (d, t) => {
      const h = Math.floor((t - d.t) / HORA);
      if (!d.horas.has(h)) d.horas.set(h, { h, lluvia: null, reportes: [] });
      return d.horas.get(h);
    };
    const { inicio, mm: serie } = estado.lluvia;
    if (inicio !== null) {
      serie.forEach((v, i) => {
        const t = inicio + i * HORA, d = indice.get(claveDia(t));
        if (!d || t >= ahora) return;
        if (v == null) { d.sinDato++; return; }
        d.conDato++; d.lluvia += v;
        if (v >= HORA_MM) horaDeDia(d, t).lluvia = v;
      });
    }
    for (const r of lista) { const d = indice.get(claveDia(r.t)); if (d) { d.reportes.push(r); horaDeDia(d, r.t).reportes.push(r); } }
    // La lluvia de las horas que sí tienen fila por sus reportes.
    if (inicio !== null) {
      for (const d of dias) for (const fila of d.horas.values()) {
        if (fila.lluvia !== null) continue;
        const v = serie[Math.round((d.t + fila.h * HORA - inicio) / HORA)];
        fila.lluvia = v == null ? null : v;
      }
    }
    return dias.filter((d) => d.t < ahora);
  }
  const esCalma = (d) => d.reportes.length === 0 && d.lluvia < CALMA_MM;

  // ── Navegador: todo el periodo, un día por columna ────────────────────────
  // Dos gráficos que comparten el eje del tiempo (no dos ejes en uno): la lluvia sube
  // desde la línea y los reportes bajan. Un toque en un día lleva a él.
  function navegador(dias) {
    const svg = $('g-nav');
    const W = Math.max(280, Math.round(svg.getBoundingClientRect().width) || 720), H = 92, m = { i: 2, d: 2 };
    const arriba = 34, abajo = 22, base = 4 + arriba; // lluvia: 4..38 · reportes: 42..64 · fechas: 88
    const n = dias.length, w = (W - m.i - m.d) / n, grosor = Math.max(1.5, Math.min(16, w - 2));
    const maxLl = Math.max(0.1, ...dias.map((d) => d.lluvia)), maxRe = Math.max(1, ...dias.map((d) => d.reportes.length));
    let h = `<rect class="visto" x="0" y="0" width="${w}" height="${H - 16}" rx="3" fill="#000" opacity="0"/>`;
    const cada = Math.max(1, Math.ceil(n * 44 / (W - m.i - m.d)));
    dias.forEach((d, i) => {
      const cx = m.i + i * w + w / 2;
      if (d.lluvia > 0) {
        const alt = Math.max(1.5, (d.lluvia / maxLl) * arriba), r = Math.min(2.5, grosor / 2, alt);
        h += `<path d="M${cx - grosor / 2} ${base}v${-(alt - r)}q0 ${-r} ${r} ${-r}h${grosor - 2 * r}q${r} 0 ${r} ${r}v${alt - r}z" fill="${COLOR.lluvia}"/>`;
      } else if (d.conDato === 0) {
        h += `<line x1="${cx - grosor / 2}" x2="${cx + grosor / 2}" y1="${base - 3}" y2="${base - 3}" stroke="#bdbdbd" stroke-width="1.5" stroke-dasharray="2 2"/>`; // sin dato
      }
      if (d.reportes.length) {
        const alt = Math.max(2, (d.reportes.length / maxRe) * abajo), r = Math.min(2.5, grosor / 2, alt);
        h += `<path d="M${cx - grosor / 2} ${base + 4}v${alt - r}q0 ${r} ${r} ${r}h${grosor - 2 * r}q${r} 0 ${r} ${-r}v${-(alt - r)}z" fill="${COLOR.reportes}"/>`;
      }
      const fecha = aLocal(d.t);
      if ((n - 1 - i) % cada === 0) h += `<text x="${cx}" y="${H - 4}" text-anchor="middle" class="eje${fecha.getUTCDate() === 1 ? ' fuerte' : ''}">${fecha.getUTCDate() === 1 || i < cada ? diaCorto(d.t) : fecha.getUTCDate()}</text>`;
    });
    h += `<line x1="${m.i}" x2="${W - m.d}" y1="${base + 2}" y2="${base + 2}" stroke="#8a8a8a" stroke-width="1"/>`;
    h += `<rect class="cursor" x="0" y="0" width="${w}" height="${H - 16}" rx="3" fill="#000" opacity="0" pointer-events="none"/>`;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.innerHTML = h;
    $('ley-lluvia').textContent = `Lluvia por día (el mayor: ${mm(maxLl)} mm)`;
    $('ley-reportes').textContent = `Reportes por día (el mayor: ${maxRe})`;

    const pista = $('pista-grafico');
    const cual = (e) => {
      const caja = svg.getBoundingClientRect();
      const px = ((e.touches ? e.touches[0].clientX : e.clientX) - caja.left) / caja.width * W;
      return Math.min(n - 1, Math.max(0, Math.floor((px - m.i) / w)));
    };
    const mover = (e) => {
      const i = cual(e), d = dias[i], caja = svg.getBoundingClientRect(), marco = $('navegador').getBoundingClientRect();
      const c = svg.querySelector('.cursor'); c.setAttribute('x', m.i + i * w); c.setAttribute('opacity', '0.08');
      const lluvia = d.conDato === 0 ? 'sin dato de lluvia' : `${mm(d.lluvia)} mm de lluvia`;
      pista.innerHTML = `<b>${x(diaLargo(d.t))}</b><span><i style="background:${COLOR.lluvia}"></i>${lluvia}</span><span><i style="background:${COLOR.reportes}"></i>${d.reportes.length} ${d.reportes.length === 1 ? 'reporte' : 'reportes'}</span>`;
      pista.hidden = false;
      const izq = caja.left - marco.left + (m.i + (i + 0.5) * w) / W * caja.width;
      pista.style.left = Math.min(marco.width - pista.offsetWidth - 4, Math.max(4, izq - pista.offsetWidth / 2)) + 'px';
    };
    svg.onmousemove = mover;
    svg.onmouseleave = () => { pista.hidden = true; svg.querySelector('.cursor').setAttribute('opacity', '0'); };
    svg.onclick = (e) => { irA(dias[cual(e)].clave); pista.hidden = true; };
    svg._dias = dias; svg._w = w; svg._i = m.i;
  }

  // Lleva a un día. Si ese día está dentro de una fila de días en calma, lleva a esa fila.
  function irA(clave) {
    const destino = document.getElementById('d-' + clave) || [...document.querySelectorAll('.calma')].find((c) => c.dataset.desde <= clave && clave <= c.dataset.hasta);
    if (!destino) return;
    destino.scrollIntoView({ behavior: 'smooth', block: 'start' });
    destino.classList.remove('destello'); void destino.offsetWidth; destino.classList.add('destello');
  }
  // Marca en el navegador el día que se está leyendo.
  function marcarVisto() {
    const svg = $('g-nav'), dias = svg._dias;
    if (!dias) return;
    const tope = $('navegador').getBoundingClientRect().bottom + 8;
    const bloques = [...document.querySelectorAll('#linea [data-desde]')];
    const actual = bloques.find((b) => b.getBoundingClientRect().bottom > tope) || bloques[bloques.length - 1];
    const visto = svg.querySelector('.visto');
    if (!actual || !visto) return;
    const a = dias.findIndex((d) => d.clave === actual.dataset.desde), b = dias.findIndex((d) => d.clave === actual.dataset.hasta);
    if (a < 0 || b < 0) return;
    visto.setAttribute('x', svg._i + Math.min(a, b) * svg._w);
    visto.setAttribute('width', (Math.abs(b - a) + 1) * svg._w);
    visto.setAttribute('opacity', '0.1');
  }

  function saltos(dias) {
    const conReportes = dias.filter((d) => d.reportes.length), conLluvia = dias.filter((d) => d.lluvia > 0);
    const lista = [];
    const hoy = dias[dias.length - 1];
    if (hoy) lista.push(['Hoy', hoy.clave]);
    if (conReportes.length) lista.push(['Último reporte', conReportes[conReportes.length - 1].clave]);
    if (conLluvia.length) { const p = conLluvia.reduce((a, d) => (d.lluvia > a.lluvia ? d : a)); lista.push([`Día más lluvioso · ${diaCorto(p.t)}`, p.clave]); }
    if (conReportes.length) { const p = conReportes.reduce((a, d) => (d.reportes.length > a.reportes.length ? d : a)); lista.push([`Más reportes · ${diaCorto(p.t)}`, p.clave]); }
    if (dias.length) lista.push([`Inicio · ${diaCorto(dias[0].t)}`, dias[0].clave]);
    $('saltos').innerHTML = lista.map(([texto, clave]) => `<button type="button" data-ir="${clave}">${x(texto)}</button>`).join('');
  }

  // ── La línea del tiempo, vertical: la lluvia a un lado y los reportes al otro ──
  function tarjeta(r) {
    const sub = [r.lugar, r.detalle].filter(Boolean).join(' · ');
    return `<a class="hito clase-${r.clase}" href="${x(r.enlace)}">
      ${r.foto ? `<img src="${x(r.foto)}" alt="" loading="lazy">` : ''}
      <span class="hito-texto"><span class="hito-clase">${horaDe(r.t)} · ${x(CLASES[r.clase] || '')}${r.nFotos > 1 ? ` · ${r.nFotos} fotos` : ''}</span>
      <b>${x(r.titulo)}</b>${sub ? `<span class="hito-sub">${x(sub)}</span>` : ''}${r.texto ? `<span class="hito-desc">${x(r.texto)}</span>` : ''}</span></a>`;
  }
  function calma(grupo) {
    // grupo: días en calma seguidos, del más reciente al más antiguo
    const nuevo = grupo[0], viejo = grupo[grupo.length - 1], n = grupo.length;
    const lluvia = grupo.reduce((s, d) => s + d.lluvia, 0), conDato = grupo.some((d) => d.conDato > 0);
    const cuando = n === 1 ? diaLargo(nuevo.t) : `del ${diaCorto(viejo.t)} al ${diaCorto(nuevo.t)}`;
    const clima = !conDato ? 'sin dato de lluvia' : lluvia < 0.1 ? 'sin lluvia' : `lluvia débil, ${mm(lluvia)} mm${n > 1 ? ' en total' : ''}`;
    const sol = conDato && lluvia < 0.1;
    return `<div class="calma" data-desde="${viejo.clave}" data-hasta="${nuevo.clave}">
      <svg viewBox="0 0 24 24" aria-hidden="true">${sol
        ? '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>'
        : '<path d="M7 18h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6.2 11.1 3.5 3.5 0 0 0 7 18z"/>'}</svg>
      <span><b>${n === 1 ? 'Un día' : n + ' días'} sin reportes</b> · ${x(cuando)} · ${clima}</span></div>`;
  }
  function linea(dias, hayFiltro) {
    if (!dias.length) return '<p class="vacio"><b>Sin datos</b> en estas fechas.</p>';
    const maxHora = Math.max(1, ...dias.flatMap((d) => [...d.horas.values()].map((f) => f.lluvia || 0)));
    let h = '', grupo = [];
    const cerrar = () => { if (grupo.length) { h += calma(grupo); grupo = []; } };
    for (const d of dias.slice().reverse()) {
      if (esCalma(d)) { grupo.push(d); continue; }
      cerrar();
      const filas = [...d.horas.values()].sort((a, b) => b.h - a.h);
      const resto = d.lluvia - filas.reduce((s, f) => s + (f.lluvia || 0), 0);
      h += `<section class="dia-bloque" id="d-${d.clave}" data-desde="${d.clave}" data-hasta="${d.clave}">
        <h3 class="dia">${x(diaLargo(d.t))}
          <small>${d.conDato ? mm(d.lluvia) + ' mm' : 'sin dato de lluvia'}${d.conDato && d.sinDato ? ` (${d.sinDato} h sin dato)` : ''}</small>
          ${d.reportes.length ? `<span>${d.reportes.length}</span>` : ''}</h3><ol class="vertical">`;
      for (const f of filas) {
        const ancho = f.lluvia ? Math.max(3, Math.round((f.lluvia / maxHora) * 100)) : 0;
        h += `<li class="fila"><div class="fila-lluvia">${f.lluvia == null ? '<small>sin dato</small>' : f.lluvia >= 0.05 ? `<span>${mm(f.lluvia)}</span><i style="width:${ancho}%"></i>` : ''}</div>
          <time>${dosCifras(f.h)} h</time>
          <div class="fila-reportes">${f.reportes.sort((a, b) => b.t - a.t).map(tarjeta).join('')}</div></li>`;
      }
      if (resto >= 0.1 && filas.length) h += `<li class="fila resto"><div class="fila-lluvia"><span>${mm(resto)}</span></div><time></time><div class="fila-reportes"><small>mm repartidos en el resto del día, en lloviznas</small></div></li>`;
      if (!filas.length) h += `<li class="fila resto"><div class="fila-lluvia"><span>${mm(d.lluvia)}</span></div><time></time><div class="fila-reportes"><small>mm en lloviznas a lo largo del día, sin reportes</small></div></li>`;
      h += '</ol></section>';
    }
    cerrar();
    if (hayFiltro && !dias.some((d) => d.reportes.length)) h = '<p class="vacio"><b>Sin reportes</b> con estos filtros. Prueba con todas las islas o con más días.</p>' + h;
    return h;
  }

  function pintar() {
    const f = estado.filtros, lista = filtrados(), dias = porDias(lista);
    const total = dias.reduce((s, d) => s + d.lluvia, 0), conDato = dias.some((d) => d.conDato > 0);
    const pico = dias.reduce((a, d) => (d.lluvia > a.lluvia ? d : a), dias[0] || { lluvia: 0 });
    const est = estado.estaciones.find((e) => e.id === f.estacion);
    $('cifra-lluvia').textContent = conDato ? mm(total) + ' mm' : 'sin dato';
    $('cifra-lluvia-sub').textContent = conDato && pico.lluvia > 0 ? `día más lluvioso: ${mm(pico.lluvia)} mm el ${diaCorto(pico.t)}${est ? ' · ' + est.nombre.split(' · ')[0] : ''}` : 'en el periodo';
    $('cifra-reportes').textContent = lista.length.toLocaleString('es');
    const calmos = dias.filter(esCalma).length;
    $('cifra-reportes-sub').textContent = `en ${dias.length} días · ${calmos} en calma`;
    navegador(dias);
    saltos(dias);
    $('linea').innerHTML = linea(dias, Boolean(f.isla || f.zona || f.clase));
    $('nota-lluvia').textContent = estado.lluvia.nota || '';
    marcarVisto();
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
    rango(0); // todo el evento: los días en calma se juntan, así que cabe
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
    $('saltos').addEventListener('click', (e) => { const b = e.target.closest('[data-ir]'); if (b) irA(b.dataset.ir); });
    let cuadro = null;
    window.addEventListener('scroll', () => { if (!cuadro) cuadro = requestAnimationFrame(() => { cuadro = null; marcarVisto(); }); }, { passive: true });
    let espera = null; // al girar el teléfono o cambiar el ancho, los gráficos se vuelven a dibujar
    window.addEventListener('resize', () => { clearTimeout(espera); espera = setTimeout(pintar, 200); });
  }
  iniciar();
})();
