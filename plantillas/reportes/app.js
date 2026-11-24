/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito. */
/* La app de SOS Galápagos en el teléfono: instalar y recibir avisos. Sirve en todo el sitio.

   Se usa igual en la portada, en /riesgos/ y en /clima/:
     <div data-sos-app></div>
     <script src="/riesgos/app.js" defer></script>
   (ese archivo es un cargador mínimo; el componente se sirve en /riesgos/app/, sin caché).
   No depende de nada más: trae sus estilos y su configuración.

   Documentos oficiales: <section data-sos-oficiales></section> muestra el último de cada institución (INAMHI, SNGR, INOCAR, GAD…).
   Menú del sitio: la misma barra en todas las páginas, con los destinos de reportes/menu.py.
     <nav data-sos-menu>…enlaces de respaldo…</nav>             barra fija arriba (☰ en el teléfono)
     <nav data-sos-menu="flotante">…</nav>                       el mapa: solo el aviso y un botón ☰ redondo
   La página reserva la altura (estilos.css o su propio CSS); este componente reemplaza los enlaces
   de respaldo por la barra, el aviso general y el panel. Sin el marcador, no pinta nada.

   Instalar: en Android y en el computador el navegador ofrece la instalación; en iPhone no
   hay botón del sistema y se enseña el camino. Avisos: notificaciones del navegador (Web
   Push); en iPhone solo llegan a la app instalada. Nadie recibe avisos sin pedirlos. */
(function () {
  'use strict';
  if (window.__sosApp) return;
  window.__sosApp = true;
  const CFG = { publica: '{{ push_publica }}', suscribir: '{{ suscribir }}', sw: '/riesgos/sw.js', manifiesto: '{{ manifiesto }}' };
  const ua = navigator.userAgent;
  const esIOS = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const esAndroid = /Android/.test(ua);
  const instalada = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const conPush = () => Boolean(CFG.publica) && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  let oferta = null, suscripcion = null, ocupado = false;

  // Una sola app para todo el sitio: si la página no enlaza el manifiesto, se añade.
  if (!document.querySelector('link[rel="manifest"]')) {
    const l = document.createElement('link'); l.rel = 'manifest'; l.href = CFG.manifiesto; document.head.appendChild(l);
  }

  const estilo = document.createElement('style');
  estilo.textContent = `
    .sos-oficiales{margin:0;padding:22px 20px;border:1px solid #e3e3e0;border-top:4px solid #1d4ed8;border-radius:14px;background:#fff;color:#1d1d1b;font-family:inherit}
    .sos-oficiales[hidden]{display:none}
    .sos-oficiales h2{margin:0;font-weight:800;font-size:20px;line-height:1.2}
    .sos-oficiales .sos-of-sub{margin:4px 0 14px;font-size:13.5px;line-height:1.45;color:#5c5c58}
    .sos-of-lista{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin:0;padding:0;list-style:none}
    .sos-of-doc{display:flex;flex-direction:column;gap:5px;height:100%;padding:13px 14px;border:1px solid #e3e3e0;border-radius:11px;background:#fafaf8}
    .sos-of-doc.vigente{border-color:#1d4ed8;background:#f2f6ff}
    .sos-of-quien{font-weight:800;font-size:11.5px;line-height:1.3;letter-spacing:.06em;text-transform:uppercase;color:#1d4ed8}
    .sos-of-quien span{font-weight:600;letter-spacing:0;text-transform:none;color:#5c5c58}
    .sos-of-doc b{font-weight:800;font-size:15.5px;line-height:1.3}
    .sos-of-fecha{font-size:12px;color:#5c5c58}
    .sos-of-doc p{margin:0;font-size:13.5px;line-height:1.45;color:#33332f;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical;overflow:hidden}
    .sos-of-enlaces{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:auto;padding-top:6px}
    .sos-of-enlaces a{font-size:13.5px;font-weight:700;color:#1d4ed8;text-decoration:underline;text-underline-offset:2px}
    .sos-of-todos{display:inline-flex;align-items:center;min-height:44px;margin-top:14px;padding:9px 16px;border-radius:999px;background:#1d1d1b;color:#fff;font-weight:700;font-size:14px;line-height:1.2;text-decoration:none}
    .sos-app{display:flex;flex-wrap:wrap;gap:8px;margin:0;font-family:inherit}
    .sos-app:empty{display:none}
    .sos-app button{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:9px 14px;border:1.5px solid #1d1d1b;border-radius:999px;background:#fff;color:#1d1d1b;font:700 13.5px/1.2 inherit;font-family:inherit;cursor:pointer;-webkit-tap-highlight-color:transparent}
    .sos-app button svg{width:18px;height:18px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
    .sos-app button[aria-pressed="true"]{background:#1d1d1b;color:#fff}
    .sos-app button:disabled{opacity:.6}
    .sos-app-oscuro button{background:transparent;color:#fff;border-color:rgba(255,255,255,.6)}
    .sos-app-oscuro button[aria-pressed="true"]{background:#fff;color:#1d1d1b}
    dialog.sos-app-dialogo{width:min(92vw,400px);max-height:86vh;padding:20px 20px 16px;border:0;border-radius:16px;background:#fff;color:#1d1d1b;font:400 15px/1.45 system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.3)}
    dialog.sos-app-dialogo::backdrop{background:rgba(0,0,0,.45)}
    dialog.sos-app-dialogo h2{margin:0 0 10px;font:800 18px/1.2 inherit;font-family:inherit}
    dialog.sos-app-dialogo ol{margin:0 0 12px;padding-left:22px}
    dialog.sos-app-dialogo li{margin:0 0 8px}
    dialog.sos-app-dialogo p{margin:0 0 12px}
    dialog.sos-app-dialogo .nota{font-size:13px;color:#666}
    dialog.sos-app-dialogo button{width:100%;min-height:46px;margin-top:4px;border:0;border-radius:12px;background:#e11b22;color:#fff;font:800 14px/1 inherit;font-family:inherit;cursor:pointer}
    dialog.sos-app-dialogo .grupo{margin:14px 0 6px;font-size:11px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#666}
    dialog.sos-app-dialogo .grupo small{font-weight:400;text-transform:none;letter-spacing:0}
    dialog.sos-app-dialogo .opcion{display:flex;align-items:flex-start;gap:10px;padding:8px 0;font-size:14.5px;line-height:1.3;cursor:pointer}
    dialog.sos-app-dialogo .opcion input{flex:none;width:20px;height:20px;margin:0;accent-color:#e11b22}
    dialog.sos-app-dialogo button.secundario{background:none;color:#666;font-weight:600;text-decoration:underline;min-height:36px}
    dialog.sos-app-dialogo .icono{display:inline-block;vertical-align:-4px;width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
    :root{--sos-barra-alto:48px;--sos-aviso-alto:34px}
    @media (min-width:600px){:root{--sos-aviso-alto:26px}}
    .sos-menu{display:block;box-sizing:border-box;position:relative;padding-top:var(--sos-barra-alto);color:#1d1d1b;font-family:"Helvetica Neue",Helvetica,Arial,system-ui,sans-serif;font-size:15px;line-height:1.3}
    .sos-menu *,.sos-menu-panel *{box-sizing:border-box}
    .sos-menu-barra{position:fixed;top:0;left:0;right:0;z-index:1000;height:var(--sos-barra-alto);display:flex;align-items:center;gap:6px;padding:0 max(6px,env(safe-area-inset-right)) 0 max(16px,env(safe-area-inset-left));background:#fff;border-bottom:1px solid #e5e5e5}
    .sos-menu-marca{flex:none;display:inline-flex;align-items:center;gap:8px;min-height:44px;margin-right:auto;color:#000;text-decoration:none;font:900 15px/1 "Zalando Sans Expanded","Helvetica Neue",Helvetica,Arial,sans-serif;letter-spacing:-.01em;text-transform:uppercase;white-space:nowrap}
    .sos-menu-marca::before{content:"";flex:none;width:10px;height:10px;background:#e11b22}
    .sos-menu-enlaces{display:none;list-style:none;margin:0;padding:0}
    .sos-menu-911{order:1;flex:none;display:inline-flex;align-items:center;justify-content:center;min-width:58px;height:44px;padding:0 14px;border-radius:999px;background:#e11b22;color:#fff;font:800 15px/1 "Helvetica Neue",Helvetica,Arial,sans-serif;letter-spacing:.02em;text-decoration:none}
    .sos-menu-911:active{background:#b3141a}
    .sos-menu-abrir{order:2;flex:none;display:inline-flex;align-items:center;justify-content:center;gap:6px;width:44px;height:44px;padding:0;border:0;border-radius:10px;background:none;color:#000;font:600 14px/1 "Helvetica Neue",Helvetica,Arial,sans-serif;cursor:pointer;-webkit-tap-highlight-color:transparent}
    .sos-menu-abrir svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round}
    .sos-menu-abrir .sos-mas{display:none}
    .sos-menu-abrir:focus-visible,.sos-menu a:focus-visible,.sos-menu-panel a:focus-visible,.sos-menu-panel button:focus-visible{outline:3px solid #e11b22;outline-offset:2px}
    .sos-menu-aviso{box-sizing:border-box;display:flex;align-items:center;justify-content:center;height:var(--sos-aviso-alto);margin:0;padding:0 12px;overflow:hidden;background:#fff;border-bottom:1px solid #e5e5e5;color:#666;font-size:11.5px;line-height:1.3;text-align:center;text-wrap:balance}
    .sos-menu-aviso b{color:#1d1d1b;font-weight:700}
    .sos-menu:not(.sos-menu-flotante) .sos-menu-aviso .sos-aviso-tel{display:none}  /* la barra ya tiene el botón 911 */
    .sos-aviso-largo{display:none}
    .sos-aviso-911{position:relative;color:#e11b22;font-weight:800;text-decoration:none}
    .sos-aviso-911::after{content:"";position:absolute;inset:-16px -14px}
    .sos-menu-flotante{height:0;padding:0}
    .sos-menu-flotante .sos-menu-aviso{position:fixed;top:0;left:0;right:0;z-index:60}
    .sos-menu-flotante .sos-menu-abrir{position:fixed;z-index:20;top:var(--sos-flotante-arriba,calc(var(--sos-aviso-alto) + 10px));right:var(--sos-flotante-derecha,10px);border:1px solid #e5e5e5;border-radius:50%;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.16)}
    @media (min-width:1024px){
      .sos-menu-marca{margin-right:14px}
      .sos-menu-enlaces{display:flex;gap:0;margin-right:auto;min-width:0}
      .sos-menu-enlaces a{display:flex;align-items:center;height:48px;padding:0 10px;color:#1d1d1b;font-size:14px;font-weight:600;text-decoration:none;white-space:nowrap;border-bottom:3px solid transparent;border-top:3px solid transparent}
      .sos-menu-enlaces a:hover{color:#000;border-bottom-color:#d4d4d4}
      .sos-menu-enlaces a[aria-current=page]{color:#000;border-bottom-color:#e11b22}
      .sos-menu-911{order:3}
      .sos-menu:not(.sos-menu-flotante) .sos-menu-abrir{width:auto;padding:0 12px;border:1.5px solid #e5e5e5;border-radius:999px}
      .sos-menu:not(.sos-menu-flotante) .sos-menu-abrir svg{display:none}
      .sos-menu:not(.sos-menu-flotante) .sos-menu-abrir .sos-mas{display:inline}
      .sos-aviso-corto{display:none}
      .sos-aviso-largo{display:inline}
    }
    dialog.sos-menu-panel{position:fixed;inset:0;width:100%;max-width:100%;height:100%;max-height:100%;margin:0;padding:0 0 env(safe-area-inset-bottom);border:0;background:#fff;color:#1d1d1b;overflow-y:auto;overscroll-behavior:contain;font:400 15px/1.4 "Helvetica Neue",Helvetica,Arial,system-ui,sans-serif}
    dialog.sos-menu-panel::backdrop{background:rgba(0,0,0,.4)}
    html:has(dialog.sos-menu-panel[open]){overflow:hidden}
    @media (min-width:700px){dialog.sos-menu-panel{left:auto;right:0;width:380px;box-shadow:-8px 0 30px rgba(0,0,0,.18)}}
    .sos-panel-cab{position:sticky;top:0;z-index:1;display:flex;align-items:center;gap:6px;height:var(--sos-barra-alto);padding:0 max(6px,env(safe-area-inset-right)) 0 16px;background:#fff;border-bottom:1px solid #e5e5e5}
    .sos-panel-cerrar{flex:none;width:44px;height:44px;padding:0;border:0;border-radius:10px;background:none;color:#000;font:300 34px/1 "Helvetica Neue",Helvetica,Arial,sans-serif;cursor:pointer}
    .sos-panel-lista{list-style:none;margin:0;padding:8px 0}
    .sos-panel-lista a{display:flex;align-items:center;min-height:48px;padding:0 20px 0 16px;border-left:4px solid transparent;color:#000;text-decoration:none;font:800 17px/1.2 "Zalando Sans Expanded","Helvetica Neue",Helvetica,Arial,sans-serif;letter-spacing:-.01em}
    .sos-panel-lista a::after{content:"›";margin-left:auto;padding-left:12px;color:#8a8a8a;font:400 22px/1 "Helvetica Neue",Helvetica,Arial,sans-serif}
    .sos-panel-lista a:active{background:#f5f5f5}
    .sos-panel-lista a[aria-current=page]{border-left-color:#e11b22;background:#fdecec}
    .sos-panel-bloque{margin:0;padding:14px 20px;border-top:1px solid #e5e5e5}
    .sos-panel-titulo{margin:0 0 10px;color:#666;font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
    .sos-panel-911{display:flex;align-items:center;justify-content:center;min-height:48px;border-radius:12px;background:#e11b22;color:#fff;font:800 16px/1 "Helvetica Neue",Helvetica,Arial,sans-serif;text-decoration:none}
    .sos-panel-pie{margin:0;padding:4px 20px 24px;color:#666;font-size:13px;line-height:1.45}
    .sos-panel-pie b{color:#1d1d1b}`;
  document.head.appendChild(estilo);

  const ICONO = {
    bajar: '<svg viewBox="0 0 24 24"><path d="M12 4v11"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/></svg>',
    campana: '<svg viewBox="0 0 24 24"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>',
    compartir: '<svg class="icono" viewBox="0 0 24 24"><path d="M12 15V3"/><path d="m8 7 4-4 4 4"/><path d="M6 11H5v9h14v-9h-1"/></svg>',
  };

  // ── Mensajes en una ventana, donde se ven ─────────────────────────────────
  let dialogo = null;
  function decir(titulo, cuerpo, boton) {
    if (!dialogo) {
      dialogo = document.createElement('dialog');
      dialogo.className = 'sos-app-dialogo';
      document.body.appendChild(dialogo);
      dialogo.addEventListener('click', (e) => { if (e.target === dialogo || e.target.closest('[data-cerrar]')) dialogo.close(); });
    }
    dialogo.innerHTML = `<h2>${titulo}</h2>${cuerpo}<button type="button" data-cerrar>${boton || 'Entendido'}</button>`;
    if (dialogo.showModal) { if (!dialogo.open) dialogo.showModal(); } else dialogo.setAttribute('open', '');
  }

  // ── Instalar ──────────────────────────────────────────────────────────────
  window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); oferta = e; pintar(); });
  window.addEventListener('appinstalled', () => { oferta = null; pintar(); decir('App instalada', '<p>Búscala en tu pantalla de inicio con el nombre <b>SOS Galápagos</b>.</p>'); });
  async function instalar() {
    if (oferta) {
      const o = oferta;
      o.prompt();
      const r = await o.userChoice.catch(() => ({}));
      if (r.outcome === 'accepted') oferta = null;
      pintar();
      return;
    }
    if (esIOS) {
      const enSafari = !/CriOS|FxiOS|EdgiOS/.test(ua);
      decir('Instalar en iPhone', `<ol>
        <li>Toca el botón <b>Compartir</b> ${ICONO.compartir}${enSafari ? ', abajo en Safari' : ', en la barra del navegador'}.</li>
        <li>Baja en la lista y elige <b>«Añadir a pantalla de inicio»</b>.</li>
        <li>Toca <b>«Añadir»</b>. Luego abre la app desde tu pantalla de inicio.</li></ol>
        <p class="nota">${enSafari ? 'Si no ves la opción, desliza la lista hacia abajo.' : 'Si no aparece la opción, abre esta página en Safari.'} Con la app instalada puedes encender los avisos.</p>`);
    } else if (esAndroid) {
      decir('Instalar en Android', `<ol>
        <li>Toca el menú <b>⋮</b> del navegador, arriba a la derecha.</li>
        <li>Elige <b>«Instalar app»</b> o <b>«Añadir a pantalla de inicio»</b>.</li>
        <li>Confirma con <b>«Instalar»</b>.</li></ol>
        <p class="nota">Si ya la instalaste, búscala como «SOS Galápagos» entre tus aplicaciones.</p>`);
    } else {
      decir('Instalar en el computador', `<ol>
        <li>En Chrome o Edge, busca el icono de <b>instalar</b> al final de la barra de direcciones.</li>
        <li>O abre el menú <b>⋮</b> → <b>«Transmitir, guardar y compartir»</b> → <b>«Instalar página como aplicación»</b>.</li></ol>
        <p class="nota">En Safari: Archivo → «Añadir al Dock». Si ya está instalada, ábrela desde tus aplicaciones.</p>`);
    }
  }

  // ── Avisos ────────────────────────────────────────────────────────────────
  const bytes = (b64) => Uint8Array.from(atob((b64 + '==='.slice((b64.length + 3) % 4)).replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
  const guardar = (datos) => fetch(CFG.suscribir, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) });
  // El service worker de /riesgos/ recibe los avisos. Se registra desde cualquier página del sitio.
  async function registro() {
    const r = await navigator.serviceWorker.register(CFG.sw, { scope: '/riesgos/' });
    if (r.active) return r;
    const sw = r.installing || r.waiting;
    await new Promise((listo) => {
      if (!sw) return listo();
      sw.addEventListener('statechange', () => { if (sw.state === 'activated') listo(); });
      setTimeout(listo, 8000);
    });
    return r;
  }
  async function alternarAvisos() {
    if (ocupado) return;
    if (!conPush()) {
      if (esIOS && !instalada()) return decir('Avisos en iPhone', '<p>En iPhone los avisos solo llegan a la <b>app instalada</b>.</p><ol><li>Toca <b>«Instalar la app»</b> y sigue los pasos.</li><li>Abre la app desde tu pantalla de inicio.</li><li>Ahí toca <b>«Recibir avisos»</b>.</li></ol>');
      return decir('Avisos no disponibles', '<p>Este navegador no admite avisos. Prueba con Chrome, Edge, Firefox o Safari actualizados.</p>');
    }
    ocupado = true; pintar();
    try {
      if (suscripcion) return await elegir();
      if (Notification.permission === 'denied') {
        return decir('Avisos bloqueados', esIOS
          ? '<p>Los avisos están apagados para esta app. Actívalos en <b>Ajustes → Notificaciones → SOS Galápagos</b> y vuelve a tocar.</p>'
          : '<p>Los avisos están bloqueados para este sitio. Toca el candado junto a la dirección → <b>Notificaciones</b> → <b>Permitir</b>, y vuelve a tocar.</p>');
      }
      // El permiso se pide lo primero, dentro del mismo toque: si se espera a otra cosa antes,
      // Safari (iPhone) ya no muestra la pregunta.
      const permiso = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
      if (permiso !== 'granted') return decir('Sin permiso', '<p>Sin tu permiso no podemos avisarte. Puedes darlo más tarde tocando otra vez.</p>');
      const r = await registro();
      const nueva = (await r.pushManager.getSubscription()) || (await r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(CFG.publica) }));
      const respuesta = await guardar(nueva.toJSON());
      if (!respuesta.ok) throw new Error('el servidor no guardó la suscripción');
      suscripcion = nueva;
      await elegir('<p>En unos segundos te llega un <b>aviso de prueba</b>. Ahora elige de qué quieres enterarte.</p>');
      return;
      decir('Avisos encendidos', '<p>En unos segundos te llega un <b>aviso de prueba</b>. Si no llega, revisa que las notificaciones estén permitidas y que el teléfono no esté en modo «No molestar».</p><p class="nota">Te avisaremos cuando se confirme un peligro nuevo. Es información preliminar, no oficial.</p>');
    } catch (e) {
      decir('No se pudo', `<p>No se pudieron encender los avisos en este navegador. Intenta de nuevo en un momento.</p><p class="nota">${String(e && e.message || e).slice(0, 140)}</p>`);
    } finally { ocupado = false; pintar(); }
  }

  // ── Elegir temas e islas ──────────────────────────────────────────────────
  const TEMAS = {{ temas|safe }}, ZONAS = {{ zonas|safe }};
  async function elegir(entrada) {
    let tengo = { temas: TEMAS.filter((t) => t.por_defecto).map((t) => t.id), zonas: [] };
    try { const r = await guardar({ endpoint: suscripcion.endpoint, consulta: true }); if (r.ok) tengo = await r.json(); } catch (e) { /* se muestran los de siempre */ }
    const casilla = (grupo, x, marcado) => `<label class="opcion"><input type="checkbox" data-${grupo}="${x.id}"${marcado ? ' checked' : ''}><span>${x.nombre}</span></label>`;
    decir('Mis avisos', `${entrada || ''}
      <p class="grupo">Quiero enterarme de</p>${TEMAS.map((t) => casilla('tema', t, tengo.temas.includes(t.id))).join('')}
      <p class="grupo">De estas islas <small>(sin marcar ninguna: de todas)</small></p>${ZONAS.map((z) => casilla('zona', z, (tengo.zonas || []).includes(z.id))).join('')}
      <p class="grupo">De noche <small>(de 21:00 a 06:00)</small></p>
      <p class="nota">De noche no mandamos avisos: a las 06:00 llega un resumen de lo que pasó.</p>
      <label class="opcion"><input type="checkbox" data-noche${tengo.de_noche ? ' checked' : ''}><span>Despiértame solo si llueve muy fuerte en ese momento o hay un peligro de vida confirmado</span></label>
      <p class="nota">Son estimaciones y reportes preliminares, no alertas oficiales. Las alertas las dan el COE, la SNGR y el ECU 911.</p>
      <button type="button" class="secundario" data-apagar>Apagar todos los avisos</button>`, 'Guardar');
    dialogo.onclose = null;
    dialogo.querySelector('[data-cerrar]').addEventListener('click', () => {
      const de = (g) => [...dialogo.querySelectorAll(`[data-${g}]:checked`)].map((i) => i.dataset[g]);
      guardar({ endpoint: suscripcion.endpoint, temas: de('tema'), zonas: de('zona'), de_noche: Boolean(dialogo.querySelector('[data-noche]:checked')) }).catch(() => {});
    }, { once: true });
    dialogo.querySelector('[data-apagar]').addEventListener('click', async () => {
      await guardar({ endpoint: suscripcion.endpoint, baja: true }).catch(() => {});
      await suscripcion.unsubscribe().catch(() => {});
      suscripcion = null; pintar();
      decir('Avisos apagados', '<p>Ya no recibirás avisos en este dispositivo. Puedes volver a encenderlos cuando quieras.</p>');
    }, { once: true });
  }

  // ── Menú del sitio ────────────────────────────────────────────────────────
  // Los destinos y el aviso salen de reportes/menu.py: es la única lista del sitio.
  const DESTINOS = {{ destinos|safe }};
  const AVISO = { titulo: '{{ aviso_titulo|escapejs }}', resto: '{{ aviso_resto|escapejs }}' };
  const ICONO_MENU = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
  // La página actual se compara entera, no por prefijo: si no, «Inicio» y «Mapa» se encenderían en todas.
  const rutaActual = () => { let r = location.pathname.replace(/index\.html$/, ''); if (!r.endsWith('/')) r += '/'; return r; };
  const aviso911 = '<a class="sos-aviso-911" href="tel:911">911</a>';
  const avisoLinea = () => `<span class="sos-aviso-corto"><b>${AVISO.titulo}</b><span class="sos-aviso-tel"> Emergencias: ${aviso911}</span></span><span class="sos-aviso-largo"><b>${AVISO.titulo}</b> ${AVISO.resto}<span class="sos-aviso-tel"> Emergencias: ${aviso911}</span></span>`;
  let menus = 0;
  function pintarMenus() {
    const actual = rutaActual();
    const enlace = (d) => `<a href="${d.ruta}"${d.ruta === actual ? ' aria-current="page"' : ''}>${d.nombre}</a>`;
    for (const nav of document.querySelectorAll('[data-sos-menu]:not(.sos-menu-listo)')) {
      const flotante = nav.dataset.sosMenu === 'flotante', id = 'sos-menu-panel-' + (++menus);
      const abrir = `<button type="button" class="sos-menu-abrir" aria-expanded="false" aria-controls="${id}" aria-haspopup="dialog" aria-label="Menú del sitio">${ICONO_MENU}<span class="sos-mas" aria-hidden="true">Más</span></button>`;
      nav.classList.add('sos-menu', 'sos-menu-listo');
      if (flotante) nav.classList.add('sos-menu-flotante');
      if (!nav.getAttribute('aria-label')) nav.setAttribute('aria-label', 'SOS Galápagos');
      nav.innerHTML = (flotante ? '' : `<div class="sos-menu-barra"><a class="sos-menu-marca" href="/">SOS Galápagos</a>` +
          `<ul class="sos-menu-enlaces">${DESTINOS.filter((d) => d.barra).map((d) => `<li>${enlace(d)}</li>`).join('')}</ul>` +
          `${abrir}<a class="sos-menu-911" href="tel:911" aria-label="Emergencias: llamar al 911">911</a></div>`) +
        `<p class="sos-menu-aviso" role="note">${avisoLinea()}</p>` + (flotante ? abrir : '') +
        `<dialog class="sos-menu-panel" id="${id}" aria-label="Menú del sitio">` +
          `<div class="sos-panel-cab"><a class="sos-menu-marca" href="/">SOS Galápagos</a><button type="button" class="sos-panel-cerrar" aria-label="Cerrar el menú" autofocus>×</button></div>` +
          `<nav aria-label="Páginas del sitio"><ul class="sos-panel-lista">${DESTINOS.map((d) => `<li>${enlace(d)}</li>`).join('')}</ul></nav>` +
          `<div class="sos-panel-bloque"><p class="sos-panel-titulo">La app en el teléfono</p><div data-sos-app></div></div>` +
          `<div class="sos-panel-bloque"><a class="sos-panel-911" href="tel:911">Emergencias: llamar al 911</a></div>` +
          `<p class="sos-panel-pie"><b>${AVISO.titulo}</b> ${AVISO.resto}</p>` +
        `</dialog>`;
      const panel = nav.querySelector('dialog'), boton = nav.querySelector('.sos-menu-abrir');
      panel.addEventListener('close', () => { boton.setAttribute('aria-expanded', 'false'); boton.focus(); });
      // Foco atrapado: con showModal() lo de atrás queda inerte; además el tabulador da la vuelta dentro del panel.
      panel.addEventListener('keydown', (e) => {
        if (e.key !== 'Tab') return;
        const f = [...panel.querySelectorAll('a[href], button:not(:disabled)')].filter((x) => x.offsetParent !== null);
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      });
    }
  }
  document.addEventListener('click', (e) => {
    const abrir = e.target.closest('.sos-menu-abrir');
    if (abrir) {
      const panel = document.getElementById(abrir.getAttribute('aria-controls'));
      if (panel && !panel.open) { if (panel.showModal) panel.showModal(); else panel.setAttribute('open', ''); abrir.setAttribute('aria-expanded', 'true'); }
      return;
    }
    const panel = e.target.closest('dialog.sos-menu-panel');
    // Se cierra con ×, con Esc (lo da el navegador) o tocando fuera del panel.
    if (panel && (e.target === panel || e.target.closest('.sos-panel-cerrar'))) panel.close();
  });

  // ── Botones ───────────────────────────────────────────────────────────────
  function pintar() {
    let h = '';
    if (!instalada()) h += `<button type="button" data-sos="instalar">${ICONO.bajar}Instalar la app</button>`;
    if (CFG.publica) h += `<button type="button" data-sos="avisos" aria-pressed="${Boolean(suscripcion)}"${ocupado ? ' disabled' : ''}>${ICONO.campana}${suscripcion ? 'Mis avisos' : 'Recibir avisos'}</button>`;
    for (const caja of document.querySelectorAll('[data-sos-app]')) { caja.classList.add('sos-app'); if (caja.dataset.sosApp === 'oscuro') caja.classList.add('sos-app-oscuro'); caja.innerHTML = h; }
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-sos]');
    if (!b) return;
    if (b.dataset.sos === 'instalar') instalar(); else alternarAvisos();
  });

  // ── Documentos oficiales: lo último de cada institución ─────────────────────
  // Se pinta dentro de [data-sos-oficiales]. En la portada, si no hay ese hueco, se abre uno antes de «Situación hoy».
  let oficiales = null, pidiendoOficiales = false;
  const limpio = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const enWeb = (u) => (/^(https:\/\/|\/)/.test(u || '') ? u : '');
  function cuandoFue(iso) {
    const t = new Date(iso), min = Math.round((Date.now() - t) / 60000);
    const dia = t.toLocaleString('es-EC', { timeZone: 'Pacific/Galapagos', weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
    return (min >= 0 && min < 90 ? `hace ${Math.max(1, min)} min · ` : min >= 90 && min < 36 * 60 ? `hace ${Math.round(min / 60)} h · ` : '') + dia;
  }
  function huecosOficiales() {
    if (location.pathname === '/' && !document.querySelector('[data-sos-oficiales]')) {
      const antes = document.querySelector('section[aria-labelledby="situacion-heading"]');
      if (antes) { const hueco = document.createElement('section'); hueco.setAttribute('data-sos-oficiales', ''); hueco.hidden = true; antes.parentNode.insertBefore(hueco, antes); }
    }
    return [...document.querySelectorAll('[data-sos-oficiales]:not(.sos-oficiales)')];
  }
  function pintarOficiales() {
    const huecos = huecosOficiales();
    if (!huecos.length) return;
    if (!oficiales) {
      if (pidiendoOficiales) return;
      pidiendoOficiales = true;
      fetch('/riesgos/api/oficiales.json').then((r) => (r.ok ? r.json() : null)).then((d) => { oficiales = d || { documentos: [] }; pintarOficiales(); }).catch(() => { pidiendoOficiales = false; });
      return;
    }
    const docs = oficiales.documentos || [];
    for (const hueco of huecos) {
      hueco.classList.add('sos-oficiales');
      if (!docs.length) { hueco.hidden = true; continue; }
      hueco.hidden = false;
      hueco.setAttribute('aria-labelledby', 'sos-oficiales-titulo');
      // El título toma la letra de los demás títulos de la página, para que el bloque no desentone.
      const modelo = [...document.querySelectorAll('main h2, h2')].find((h) => !h.closest('.sos-oficiales'));
      const letra = modelo ? getComputedStyle(modelo) : null;
      hueco.innerHTML = `<h2 id="sos-oficiales-titulo">Documentos oficiales</h2>
        <p class="sos-of-sub">El último de cada institución. El resumen es una ayuda: el documento original es el que vale.</p>
        <ul class="sos-of-lista">${docs.map((d) => `<li><article class="sos-of-doc${d.vigente ? ' vigente' : ''}">
          <span class="sos-of-quien">${limpio(d.nombre)} <span>· ${limpio(d.que_es)}${d.vigente ? ' · vigente' : ''}</span></span>
          <b>${limpio(d.titulo)}</b><span class="sos-of-fecha">${limpio(cuandoFue(d.fecha))}</span>
          ${d.resumen ? `<p>${limpio(d.resumen)}</p>` : ''}
          <span class="sos-of-enlaces">${enWeb(d.enlace) ? `<a href="${limpio(enWeb(d.enlace))}" target="_blank" rel="noopener">Abrir el documento ↗</a>` : ''}${enWeb(d.infografia) ? `<a href="${limpio(enWeb(d.infografia))}" target="_blank" rel="noopener">Infografía ↗</a>` : ''}</span>
        </article></li>`).join('')}</ul>
        <a class="sos-of-todos" href="${limpio(enWeb(oficiales.todos) || '/riesgos/informe/?ver=oficial')}">Ver todos los documentos oficiales →</a>`;
      const titulo = hueco.querySelector('h2');
      if (letra && titulo) for (const k of ['fontFamily', 'fontSize', 'fontWeight', 'textTransform', 'letterSpacing', 'lineHeight']) titulo.style[k] = letra[k];
    }
  }

  function iniciar() {
    pintarMenus();
    pintar();
    pintarOficiales();
    if (conPush()) {
      navigator.serviceWorker.getRegistration('/riesgos/').then((r) => r && r.pushManager.getSubscription()).then((s) => { suscripcion = s || null; pintar(); }).catch(() => {});
    }
    // Las páginas que pintan su contenido después (la portada) añaden el hueco más tarde.
    new MutationObserver(() => {
      if (document.querySelector('[data-sos-menu]:not(.sos-menu-listo)')) pintarMenus();
      if ([...document.querySelectorAll('[data-sos-app]')].some((c) => !c.classList.contains('sos-app'))) pintar();
      if (document.querySelector('[data-sos-oficiales]:not(.sos-oficiales)') || (location.pathname === '/' && !document.querySelector('[data-sos-oficiales]'))) pintarOficiales();
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
