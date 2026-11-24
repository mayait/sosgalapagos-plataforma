/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito. */
/* Línea del tiempo (/riesgos/informe/): todos los reportes en orden, con filtros.

   Lo que importa es la línea: cada fila es una hora con sus reportes. Los días sin
   reportes se juntan en una sola fila, así que semanas sin novedades no alargan la página.
   Arriba, un navegador con todo el periodo lleva a cualquier día con un toque.

   Reúne los reportes hechos en este mapa (también los cerrados), los reportes de campo
   que publica /mapas (capas con «marcador: reporte» o «corazon») y los sucesos que no tienen
   un punto en el mapa: avisos mandados a los teléfonos (o retenidos de noche), boletines
   oficiales, noticias e informes. Un suceso puede ser de una zona o de todo Galápagos.

   La lluvia no se dibuja (decisión de Julián, 21-nov-2026): solo deja un hito, «Llovió X mm»,
   los días de lluvia fuerte, con la serie por hora que publica /clima para la estación de la isla. */
(function () {
  'use strict';
  const SOS = window.SOS, cfg = SOS.cfg, x = SOS.escapar;
  const HORA = 3600000, DIA = 24 * HORA;
  const UTC_GALAPAGOS = -6; // Galápagos no cambia de hora
  const COLOR = { lluvia: '#2f6fb3', reportes: '#c8151b' }; // par validado (daltonismo y contraste)
  const CLASES = { campo: 'Reporte de campo', buena: 'Buena noticia o ayuda (de campo)', riesgo: 'Peligro', bueno: 'Algo bueno', ayuda: 'Donar o colaborar', observa: 'Observación para el mapa',
    aviso: 'Aviso a los teléfonos', oficial: 'Documentos oficiales', noticia: 'Noticia', informe: 'Informe', nota: 'Nota de coordinación', barrio: 'Informe comunitario' };
  const SUCESOS = ['aviso', 'oficial', 'noticia', 'informe', 'nota', 'barrio']; // sin punto en el mapa
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

  // Zonas grandes para filtrar. Los límites son aproximados (preliminares): la parte alta de
  // Santa Cruz empieza al norte de Puerto Ayora (Bellavista, Santa Rosa, El Cascajo) y la de
  // San Cristóbal al este de Puerto Baquerizo Moreno (El Progreso, La Soledad, Cerro Verde).
  const ZONAS = [
    { id: 'sc', nombre: 'Santa Cruz (Puerto Ayora)', isla: 'Santa Cruz' },
    { id: 'sc-alta', nombre: 'Santa Cruz, parte alta', isla: 'Santa Cruz' },
    { id: 'sx', nombre: 'San Cristóbal (Puerto Baquerizo)', isla: 'San Cristóbal' },
    { id: 'sx-alta', nombre: 'San Cristóbal, parte alta', isla: 'San Cristóbal' },
    { id: 'is', nombre: 'Isabela', isla: 'Isabela' },
    { id: 'otras', nombre: 'Otras islas', isla: '' },
  ];
  const SC_ALTA_LAT = -0.718, SX_ALTA_LON = -89.585;
  function zonaGrande(lon, lat) {
    const isla = islaDe(lon, lat);
    if (isla === 'Santa Cruz') return lat > SC_ALTA_LAT ? 'sc-alta' : 'sc';
    if (isla === 'San Cristóbal') return lon > SX_ALTA_LON ? 'sx-alta' : 'sx';
    return isla === 'Isabela' ? 'is' : 'otras';
  }
  const nombreZona = (id) => (ZONAS.find((z) => z.id === id) || {}).nombre || '';
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
        t: p.visto * 1000, clase: p.clase, titulo: p.titulo || p.tipo_nombre, lugar: p.zona || '', zona: zonaGrande(lon, lat), isla: islaDe(lon, lat),
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
          lugar: p.lugar || p.barrio || '', zona: zonaGrande(lon, lat), isla: islaDe(lon, lat),
          detalle: p.gravedad_txt ? 'gravedad ' + p.gravedad_txt.toLowerCase() : [p.estado_txt, p.autor].filter(Boolean).join(' · '),
          texto: p.descripcion || '', foto: fotos.length ? datos + (capa.fotos_base || '') + (fotos[0].mini || fotos[0].archivo) : '',
          nFotos: fotos.length, lon, lat, enlace: `${cfg.mapa}#${lat.toFixed(5)},${lon.toFixed(5)},17.5`,
        });
      }
    }
    return lista;
  }

  // Sucesos: lo que pasó y no es un punto del mapa. `zonas` vacío: todo Galápagos (sale con cualquier filtro de zona).
  async function cargarSucesos() {
    const d = await fetch(cfg.sucesos, { cache: 'no-store' }).then((r) => r.json());
    return (d.sucesos || []).map((s) => ({
      t: Date.parse(s.t), clase: s.clase, titulo: s.titulo, lugar: s.fuente || '', zonas: s.zonas || [], zona: (s.zonas || [])[0] || '', isla: '',
      detalle: s.detalle || '', texto: s.texto || '', foto: '', nFotos: 0, enlace: s.enlace || '', retenido: Boolean(s.retenido), suceso: true,
    }));
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
      && (!f.zona || (r.suceso ? !r.zonas.length || r.zonas.includes(f.zona) : r.zona === f.zona)) && (!f.clase || r.clase === f.clase))
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
    const conReportes = new Set(estado.reportes.map((r) => r.zona));
    opciones($('f-zona'), ZONAS.filter((z) => z.id !== 'otras' || conReportes.has('otras')).map((z) => [z.id, z.nombre]), 'Todas las zonas', f.zona);
    opciones($('f-clase'), Object.entries(CLASES), 'Todo', f.clase);
    $('f-desde').value = claveDia(f.desde);
    $('f-hasta').value = claveDia(f.hasta - 1);
  }

  // ── Datos por día y por hora ──────────────────────────────────────────────
  // La lluvia no se dibuja: solo deja un hito en la línea los días de lluvia fuerte.
  const HITO_MM = 50; // lluvia en un día a partir de la cual se anota «Llovió X mm» (umbral preliminar)
  function porDias(lista) {
    const f = estado.filtros, ahora = Date.now(), dias = [], indice = new Map();
    for (let t = f.desde; t < f.hasta; t += DIA) {
      const d = { t, clave: claveDia(t), lluvia: 0, pico: 0, horaPico: 0, hito: false, reportes: [], horas: new Map() };
      dias.push(d); indice.set(d.clave, d);
    }
    const horaDeDia = (d, h) => {
      if (!d.horas.has(h)) d.horas.set(h, { h, hito: false, reportes: [] });
      return d.horas.get(h);
    };
    for (const r of lista) { const d = indice.get(claveDia(r.t)); if (d) { d.reportes.push(r); horaDeDia(d, Math.floor((r.t - d.t) / HORA)).reportes.push(r); } }
    const { inicio, mm: serie } = estado.lluvia;
    if (inicio !== null) {
      serie.forEach((v, i) => {
        const t = inicio + i * HORA, d = indice.get(claveDia(t));
        if (!d || t >= ahora || v == null) return;
        d.lluvia += v;
        if (v > d.pico) { d.pico = v; d.horaPico = Math.floor((t - d.t) / HORA); }
      });
      for (const d of dias) if (d.lluvia >= HITO_MM) { d.hito = true; horaDeDia(d, d.horaPico).hito = true; }
    }
    return dias.filter((d) => d.t < ahora);
  }
  const esCalma = (d) => d.reportes.length === 0 && !d.hito;

  // ── Navegador: todo el periodo, un día por columna ────────────────────────
  // Reportes por día. Un punto azul marca los días de lluvia fuerte. Un toque en un día lleva a él.
  function navegador(dias) {
    const svg = $('g-nav');
    const W = Math.max(280, Math.round(svg.getBoundingClientRect().width) || 720), H = 70, m = { i: 2, d: 2 };
    const alto = 34, base = 12 + alto; // punto de lluvia: 5 · barras: 12..46 · fechas: 66
    const n = dias.length, w = (W - m.i - m.d) / n, grosor = Math.max(1.5, Math.min(16, w - 2));
    const maxRe = Math.max(1, ...dias.map((d) => d.reportes.length));
    let h = `<rect class="visto" x="0" y="0" width="${w}" height="${H - 16}" rx="3" fill="#000" opacity="0"/>`;
    const cada = Math.max(1, Math.ceil(n * 44 / (W - m.i - m.d)));
    dias.forEach((d, i) => {
      const cx = m.i + i * w + w / 2;
      if (d.reportes.length) {
        const alt = Math.max(2, (d.reportes.length / maxRe) * alto), r = Math.min(2.5, grosor / 2, alt);
        h += `<path d="M${cx - grosor / 2} ${base}v${-(alt - r)}q0 ${-r} ${r} ${-r}h${grosor - 2 * r}q${r} 0 ${r} ${r}v${alt - r}z" fill="${COLOR.reportes}"/>`;
      }
      if (d.hito) h += `<circle cx="${cx}" cy="5" r="${Math.min(3.5, Math.max(2, w / 2 - 1))}" fill="${COLOR.lluvia}"/>`;
      const fecha = aLocal(d.t);
      if ((n - 1 - i) % cada === 0) h += `<text x="${cx}" y="${H - 4}" text-anchor="middle" class="eje${fecha.getUTCDate() === 1 ? ' fuerte' : ''}">${fecha.getUTCDate() === 1 || i < cada ? diaCorto(d.t) : fecha.getUTCDate()}</text>`;
    });
    h += `<line x1="${m.i}" x2="${W - m.d}" y1="${base}" y2="${base}" stroke="#8a8a8a" stroke-width="1"/>`;
    h += `<rect class="cursor" x="0" y="0" width="${w}" height="${H - 16}" rx="3" fill="#000" opacity="0" pointer-events="none"/>`;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.innerHTML = h;
    $('ley-reportes').textContent = `Reportes por día (el mayor: ${maxRe})`;
    $('ley-lluvia').parentElement.hidden = !dias.some((d) => d.hito);

    const pista = $('pista-grafico');
    const cual = (e) => {
      const caja = svg.getBoundingClientRect();
      const px = ((e.touches ? e.touches[0].clientX : e.clientX) - caja.left) / caja.width * W;
      return Math.min(n - 1, Math.max(0, Math.floor((px - m.i) / w)));
    };
    const mover = (e) => {
      const i = cual(e), d = dias[i], caja = svg.getBoundingClientRect(), marco = $('navegador').getBoundingClientRect();
      const c = svg.querySelector('.cursor'); c.setAttribute('x', m.i + i * w); c.setAttribute('opacity', '0.08');
      pista.innerHTML = `<b>${x(diaLargo(d.t))}</b><span><i style="background:${COLOR.reportes}"></i>${d.reportes.length} ${d.reportes.length === 1 ? 'reporte' : 'reportes'}</span>${d.hito ? `<span><i style="background:${COLOR.lluvia};border-radius:50%"></i>llovió ${mm(d.lluvia)} mm</span>` : ''}`;
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
    const conReportes = dias.filter((d) => d.reportes.length), conLluvia = dias.filter((d) => d.hito);
    const lista = [];
    const hoy = dias[dias.length - 1];
    if (hoy) lista.push(['Hoy', hoy.clave]);
    if (conReportes.length) lista.push(['Último reporte', conReportes[conReportes.length - 1].clave]);
    if (conLluvia.length) { const p = conLluvia.reduce((a, d) => (d.lluvia > a.lluvia ? d : a)); lista.push([`Lluvia más fuerte · ${diaCorto(p.t)}`, p.clave]); }
    if (conReportes.length) { const p = conReportes.reduce((a, d) => (d.reportes.length > a.reportes.length ? d : a)); lista.push([`Más reportes · ${diaCorto(p.t)}`, p.clave]); }
    if (dias.length) lista.push([`Comienzo · ${diaCorto(dias[0].t)}`, dias[0].clave]);
    $('saltos').innerHTML = lista.map(([texto, clave]) => `<button type="button" data-ir="${clave}">${x(texto)}</button>`).join('');
  }

  // ── La línea del tiempo, vertical ─────────────────────────────────────────
  function tarjeta(r) {
    const sub = [r.lugar, r.detalle].filter(Boolean).join(' · ');
    const donde = r.suceso ? (r.zonas.length ? r.zonas.map(nombreZona).join(' y ') : 'Todo Galápagos') : nombreZona(r.zona);
    const etiqueta = r.enlace ? 'a' : 'div', destino = r.enlace ? ` href="${x(r.enlace)}"${/^https?:/.test(r.enlace) ? ' rel="noopener" target="_blank"' : ''}` : '';
    return `<${etiqueta} class="hito clase-${r.clase}${r.retenido ? ' retenido' : ''}"${destino}>
      ${r.foto ? `<img src="${x(r.foto)}" alt="" loading="lazy">` : ''}
      <span class="hito-texto"><span class="hito-clase">${horaDe(r.t)} · ${x(CLASES[r.clase] || '')}${r.nFotos > 1 ? ` · ${r.nFotos} fotos` : ''}</span>
      ${estado.filtros.zona && !r.suceso ? '' : `<span class="hito-zona">${x(donde)}</span>`}
      <b>${x(r.titulo)}</b>${sub ? `<span class="hito-sub">${x(sub)}</span>` : ''}${r.texto ? `<span class="hito-desc">${x(r.texto)}</span>` : ''}
      ${r.clase === 'oficial' && r.enlace ? '<span class="hito-abrir">Abrir el documento oficial ↗</span>' : ''}</span></${etiqueta}>`;
  }
  // Hito de lluvia: un dato de contexto, no un reporte. Va en la hora en que más llovió.
  function hitoLluvia(d) {
    const est = estado.estaciones.find((e) => e.id === estado.filtros.estacion);
    return `<a class="hito clase-lluvia" href="/clima/">
      <span class="hito-texto"><span class="hito-clase">Lluvia</span>
      <b>Llovió ${mm(d.lluvia)} mm este día</b>
      <span class="hito-sub">La hora más fuerte: ${mm(d.pico)} mm, a las ${dosCifras(d.horaPico)} h${est ? ' · estación ' + x(est.nombre.split(' · ')[0]) : ''} · medición preliminar</span></span></a>`;
  }
  function calma(grupo) {
    // grupo: días seguidos sin nada que contar, del más reciente al más antiguo
    const nuevo = grupo[0], viejo = grupo[grupo.length - 1], n = grupo.length;
    const cuando = n === 1 ? diaLargo(nuevo.t) : `del ${diaCorto(viejo.t)} al ${diaCorto(nuevo.t)}`;
    return `<div class="calma" data-desde="${viejo.clave}" data-hasta="${nuevo.clave}"><span><b>${n === 1 ? 'Un día' : n + ' días'} sin novedades</b> · ${x(cuando)}</span></div>`;
  }
  function linea(dias, hayFiltro) {
    if (!dias.length) return '<p class="vacio"><b>Sin datos</b> en estas fechas.</p>';
    let h = '', grupo = [];
    const cerrar = () => { if (grupo.length) { h += calma(grupo); grupo = []; } };
    for (const d of dias.slice().reverse()) {
      if (esCalma(d)) { grupo.push(d); continue; }
      cerrar();
      const filas = [...d.horas.values()].sort((a, b) => b.h - a.h);
      h += `<section class="dia-bloque" id="d-${d.clave}" data-desde="${d.clave}" data-hasta="${d.clave}">
        <h3 class="dia">${x(diaLargo(d.t))}${d.reportes.length ? `<span>${d.reportes.length}</span>` : ''}</h3><ol class="vertical">`;
      for (const f of filas) {
        h += `<li class="fila"><time>${dosCifras(f.h)} h</time>
          <div class="fila-reportes">${f.reportes.sort((a, b) => b.t - a.t).map(tarjeta).join('')}${f.hito ? hitoLluvia(d) : ''}</div></li>`;
      }
      h += '</ol></section>';
    }
    cerrar();
    if (hayFiltro && !dias.some((d) => d.reportes.length)) h = '<p class="vacio"><b>Sin reportes</b> con estos filtros. Prueba con todas las zonas o con más días.</p>' + h;
    return h;
  }

  function pintar() {
    const f = estado.filtros, lista = filtrados(), dias = porDias(lista);
    const conReportes = dias.filter((d) => d.reportes.length);
    const deGente = lista.filter((r) => !r.suceso), otros = lista.length - deGente.length;
    $('cifra-reportes').textContent = deGente.length.toLocaleString('es');
    $('cifra-reportes-sub').textContent = [deGente.length ? `con fotos: ${deGente.filter((r) => r.nFotos).length}` : 'en el periodo', otros ? `más ${otros} ${otros === 1 ? 'suceso' : 'sucesos'} (avisos, oficiales, noticias)` : ''].filter(Boolean).join(' · ');
    $('cifra-dias').textContent = conReportes.length.toLocaleString('es');
    $('cifra-dias-sub').textContent = `de ${dias.length} días${conReportes.length ? ' · el último, ' + diaCorto(conReportes[conReportes.length - 1].t) : ''}`;
    navegador(dias);
    saltos(dias);
    $('linea').innerHTML = linea(dias, Boolean(f.zona || f.clase));
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
    const [propios, campo, sucesos] = await Promise.all([cargarPropios().catch(() => []), cargarDeCampo().catch(() => []), cargarSucesos().catch(() => [])]);
    estado.reportes = propios.concat(campo, sucesos);
    rango(0); // todo el evento: los días en calma se juntan, así que cabe
    await cargarLluvia();
    const f = estado.filtros;
    f.estacion = ESTACION_POR_ISLA['Santa Cruz'];
    if (!estado.estaciones.some((e) => e.id === f.estacion)) f.estacion = (estado.estaciones[0] || {}).id || '';
    // El filtro viaja en la dirección, para poder compartirla: /riesgos/informe/?ver=oficial&zona=sc
    const pedido = new URLSearchParams(location.search);
    if (CLASES[pedido.get('ver')]) f.clase = pedido.get('ver');
    if (ZONAS.some((z) => z.id === pedido.get('zona'))) {
      f.zona = pedido.get('zona');
      f.isla = (ZONAS.find((z) => z.id === f.zona) || {}).isla || '';
    }
    await actualizar(true);
    $('informe').removeAttribute('aria-busy');
    const enlazar = () => {
      const q = new URLSearchParams();
      if (f.clase) q.set('ver', f.clase);
      if (f.zona) q.set('zona', f.zona);
      history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q : ''));
    };

    $('f-zona').onchange = (e) => {
      f.zona = e.target.value;
      // Los hitos de lluvia salen de la estación de la isla de esa zona.
      f.isla = (ZONAS.find((z) => z.id === f.zona) || {}).isla || '';
      const propia = ESTACION_POR_ISLA[f.isla || 'Santa Cruz'] || (estado.estaciones.find((st) => st.isla === f.isla) || {}).id;
      // Si esa isla no tiene estación con lluvia por hora, no se anota lluvia de otra isla.
      f.estacion = propia && estado.estaciones.some((st) => st.id === propia) ? propia : '';
      actualizar(true); enlazar();
    };
    $('f-clase').onchange = (e) => { f.clase = e.target.value; actualizar(false); enlazar(); };
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
