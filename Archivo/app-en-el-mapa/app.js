/* La app en el teléfono: instalar el mapa como aplicación y recibir avisos.

   Instalar: en Android y en el computador el navegador ofrece el botón; en iPhone no hay
   botón y se explica el camino (Compartir → Añadir a pantalla de inicio).
   Avisos: notificaciones del navegador (Web Push). En iPhone solo funcionan con la app
   instalada. Nadie recibe avisos sin haberlos pedido, y se pueden apagar aquí mismo. */
(function () {
  'use strict';
  const SOS = window.SOS, cfg = SOS.cfg;
  const caja = document.getElementById('app-caja');
  if (!caja) return;
  const esIphone = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const instalada = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  let oferta = null; // lo que guarda el navegador para ofrecer la instalación
  let suscripcion = null, nota = '';

  const bytes = (b64) => Uint8Array.from(atob((b64 + '==='.slice((b64.length + 3) % 4)).replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
  const conAvisos = () => Boolean(cfg.pushPublica) && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

  function pintar() {
    let h = '';
    if (!instalada && (oferta || esIphone)) {
      h += '<button type="button" data-app="instalar"><svg><use href="#i-mas"/></svg><span>Instalar la app<small>Abre más rápido y funciona sin señal</small></span></button>';
    }
    if (conAvisos()) {
      h += `<button type="button" data-app="avisos" aria-pressed="${Boolean(suscripcion)}"><svg><use href="#i-campana"/></svg><span>${suscripcion ? 'Avisos encendidos' : 'Recibir avisos'}<small>${suscripcion ? 'Toca para apagarlos en este teléfono' : 'Cuando se confirme un peligro nuevo'}</small></span></button>`;
    } else if (cfg.pushPublica && esIphone && !instalada) {
      h += '<button type="button" data-app="avisos-iphone"><svg><use href="#i-campana"/></svg><span>Recibir avisos<small>En iPhone, primero instala la app</small></span></button>';
    }
    if (nota) h += `<p class="app-nota" role="status">${nota}</p>`;
    caja.innerHTML = h;
    caja.hidden = !h;
  }

  // ── Instalar ──────────────────────────────────────────────────────────────
  window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); oferta = e; pintar(); });
  window.addEventListener('appinstalled', () => { oferta = null; nota = 'App instalada. Búscala en tu pantalla de inicio.'; pintar(); });
  async function instalar() {
    if (oferta) {
      oferta.prompt();
      const { outcome } = await oferta.userChoice.catch(() => ({}));
      if (outcome === 'accepted') oferta = null;
      pintar();
      return;
    }
    nota = 'En iPhone: toca el botón <b>Compartir</b> de Safari (el cuadrado con la flecha) y elige <b>«Añadir a pantalla de inicio»</b>. Tiene que ser en Safari.';
    pintar();
  }

  // ── Avisos ────────────────────────────────────────────────────────────────
  const guardar = (datos) => fetch(cfg.pushSuscribir, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': SOS.galleta('csrftoken') }, body: JSON.stringify(datos),
  });
  async function alternarAvisos() {
    const registro = await navigator.serviceWorker.ready;
    if (suscripcion) {
      await guardar({ endpoint: suscripcion.endpoint, baja: true }).catch(() => {});
      await suscripcion.unsubscribe().catch(() => {});
      suscripcion = null; nota = 'Avisos apagados en este teléfono.';
      pintar();
      return;
    }
    if (Notification.permission === 'denied') {
      nota = 'Los avisos están bloqueados para este sitio. Actívalos en los ajustes del navegador (el candado junto a la dirección → Notificaciones) y vuelve a tocar.';
      pintar();
      return;
    }
    const permiso = await Notification.requestPermission();
    if (permiso !== 'granted') { nota = 'Sin tu permiso no podemos avisarte. Puedes darlo más tarde tocando otra vez.'; pintar(); return; }
    try {
      const nueva = await registro.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(cfg.pushPublica) });
      const r = await guardar(nueva.toJSON());
      if (!r.ok) throw new Error('no se guardó');
      suscripcion = nueva;
      nota = 'Listo. Te avisaremos cuando se confirme un peligro nuevo. Es información preliminar, no oficial.';
    } catch (e) {
      nota = 'No se pudo encender los avisos en este navegador. Intenta de nuevo más tarde.';
    }
    pintar();
  }

  caja.addEventListener('click', (e) => {
    const b = e.target.closest('[data-app]');
    if (!b) return;
    if (b.dataset.app === 'instalar') instalar();
    else if (b.dataset.app === 'avisos') alternarAvisos();
    else { nota = 'En iPhone los avisos solo llegan a la app instalada. Toca «Instalar la app» y luego ábrela desde tu pantalla de inicio.'; pintar(); }
  });

  if (conAvisos()) navigator.serviceWorker.ready.then((r) => r.pushManager.getSubscription()).then((s) => { suscripcion = s; pintar(); }).catch(() => {});
  pintar();
})();
