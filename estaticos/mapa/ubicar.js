/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito. */
/* «Ayúdanos a ubicar»: la persona mueve el mapa hasta que el pin quede donde se tomó la foto.
   La regla de cuándo pasa al mapa está en el servidor (reportes/reglas.py, proponer_ubicacion). */
(function () {
  'use strict';
  const SOS = window.SOS, cfg = SOS.cfg;

  window.ubicar = () => ({
    texto: '', nombre: '', enviando: false, error: '', listo: false, aceptada: false, puntos: 0, textoPuntos: '', enlace: '',
    mapa: null, movido: false,

    init() {
      try { this.nombre = localStorage.getItem('sos-nombre') || ''; } catch (e) { /* sin acceso */ }
      this.$nextTick(() => {
        this.mapa = new maplibregl.Map({
          container: 'mini-mapa', style: SOS.estiloBase(), center: cfg.centro, zoom: cfg.zoom,
          maxBounds: [[-93.2, -2.4], [-88.0, 1.6]], attributionControl: { compact: true }, dragRotate: false, fadeDuration: 0,
        });
        this.mapa.touchZoomRotate.disableRotation();
        this.mapa.on('dragend', () => { this.movido = true; });
        this.mapa.on('zoomend', () => { this.movido = true; });
      });
    },

    async enviar() {
      this.error = '';
      if (!this.mapa) return;
      if (this.mapa.getZoom() < 15) {
        this.error = 'Acércate más al lugar (pellizca para hacer zoom) para que el pin quede en la calle correcta.';
        return;
      }
      try { localStorage.setItem('sos-nombre', this.nombre.trim()); } catch (e) { /* sin acceso */ }
      const c = this.mapa.getCenter();
      const cuerpo = new FormData();
      cuerpo.append('lat', c.lat); cuerpo.append('lon', c.lng);
      cuerpo.append('texto', this.texto.trim()); cuerpo.append('nombre', this.nombre.trim());
      this.enviando = true;
      try {
        const r = await fetch(this.$root.dataset.enviar, { method: 'POST', body: cuerpo, headers: { 'X-CSRFToken': SOS.galleta('csrftoken') } });
        const datos = await r.json().catch(() => ({}));
        if (!r.ok) { this.error = datos.error || 'No se pudo enviar. Intenta otra vez.'; return; }
        this.aceptada = Boolean(datos.aceptada);
        this.enlace = datos.enlace || '';
        this.puntos = datos.puntos || 0;
        this.textoPuntos = `Ganaste ${this.puntos} punto${this.puntos === 1 ? '' : 's'}${datos.nombre ? ', ' + datos.nombre : ''}. Llevas ${datos.total || this.puntos}.`;
        this.listo = true;
        window.scrollTo(0, 0);
      } catch (e) {
        this.error = 'Sin conexión. Vuelve a intentarlo cuando tengas señal.';
      } finally {
        this.enviando = false;
      }
    },
  });
})();
