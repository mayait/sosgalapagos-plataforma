/* La app de SOS Galápagos en el teléfono: instalar y recibir avisos. Sirve en todo el sitio.

   Se usa igual en la portada, en /riesgos/ y en /clima/:
     <div data-sos-app></div>
     <script src="/riesgos/app.js" defer></script>
   No depende de nada más: trae sus estilos y su configuración.

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
    dialog.sos-app-dialogo .icono{display:inline-block;vertical-align:-4px;width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}`;
  document.head.appendChild(estilo);

  const ICONO = {
    bajar: '<svg viewBox="0 0 24 24"><path d="M12 4v11"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/></svg>',
    campana: '<svg viewBox="0 0 24 24"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>',
    compartir: '<svg class="icono" viewBox="0 0 24 24"><path d="M12 15V3"/><path d="m8 7 4-4 4 4"/><path d="M6 11H5v9h14v-9h-1"/></svg>',
  };

  // ── Mensajes en una ventana, donde se ven ─────────────────────────────────
  let dialogo = null;
  function decir(titulo, cuerpo) {
    if (!dialogo) {
      dialogo = document.createElement('dialog');
      dialogo.className = 'sos-app-dialogo';
      document.body.appendChild(dialogo);
      dialogo.addEventListener('click', (e) => { if (e.target === dialogo || e.target.closest('[data-cerrar]')) dialogo.close(); });
    }
    dialogo.innerHTML = `<h2>${titulo}</h2>${cuerpo}<button type="button" data-cerrar>Entendido</button>`;
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
      if (suscripcion) {
        await guardar({ endpoint: suscripcion.endpoint, baja: true }).catch(() => {});
        await suscripcion.unsubscribe().catch(() => {});
        suscripcion = null;
        decir('Avisos apagados', '<p>Ya no recibirás avisos en este dispositivo. Puedes volver a encenderlos cuando quieras.</p>');
        return;
      }
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
      decir('Avisos encendidos', '<p>En unos segundos te llega un <b>aviso de prueba</b>. Si no llega, revisa que las notificaciones estén permitidas y que el teléfono no esté en modo «No molestar».</p><p class="nota">Te avisaremos cuando se confirme un peligro nuevo. Es información preliminar, no oficial.</p>');
    } catch (e) {
      decir('No se pudo', `<p>No se pudieron encender los avisos en este navegador. Intenta de nuevo en un momento.</p><p class="nota">${String(e && e.message || e).slice(0, 140)}</p>`);
    } finally { ocupado = false; pintar(); }
  }

  // ── Botones ───────────────────────────────────────────────────────────────
  function pintar() {
    let h = '';
    if (!instalada()) h += `<button type="button" data-sos="instalar">${ICONO.bajar}Instalar la app</button>`;
    if (CFG.publica) h += `<button type="button" data-sos="avisos" aria-pressed="${Boolean(suscripcion)}"${ocupado ? ' disabled' : ''}>${ICONO.campana}${suscripcion ? 'Avisos encendidos' : 'Recibir avisos'}</button>`;
    for (const caja of document.querySelectorAll('[data-sos-app]')) { caja.classList.add('sos-app'); if (caja.dataset.sosApp === 'oscuro') caja.classList.add('sos-app-oscuro'); caja.innerHTML = h; }
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-sos]');
    if (!b) return;
    if (b.dataset.sos === 'instalar') instalar(); else alternarAvisos();
  });

  function iniciar() {
    pintar();
    if (conPush()) {
      navigator.serviceWorker.getRegistration('/riesgos/').then((r) => r && r.pushManager.getSubscription()).then((s) => { suscripcion = s || null; pintar(); }).catch(() => {});
    }
    // Las páginas que pintan su contenido después (la portada) añaden el hueco más tarde.
    new MutationObserver(() => { if ([...document.querySelectorAll('[data-sos-app]')].some((c) => !c.classList.contains('sos-app'))) pintar(); }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
