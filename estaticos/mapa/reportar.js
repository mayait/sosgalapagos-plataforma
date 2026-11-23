/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito. */
/* Formulario de reporte: foto, tipo, profundidad y lugar. Sin cuenta.
   Si no hay señal, el reporte se guarda en el teléfono y se envía después. */
(function () {
  'use strict';
  const SOS = window.SOS, cfg = SOS.cfg;
  const CON_AGUA = ['agua_via', 'quebrada', 'vivienda']; // tipos en los que se pregunta la profundidad
  const ALTURA = { '': 300, sin_dato: 300, tobillo: 272, rodilla: 222, cintura: 158, puerta_auto: 190 };
  const LADO_MAXIMO = 1600;

  // Lee la ubicación de los metadatos de un JPEG (EXIF), antes de reducir la foto.
  async function ubicacionDeFoto(archivo) {
    try {
      const v = new DataView(await archivo.slice(0, 256 * 1024).arrayBuffer());
      if (v.getUint16(0) !== 0xffd8) return null;
      let p = 2;
      while (p < v.byteLength - 4) {
        const marca = v.getUint16(p), largo = v.getUint16(p + 2);
        if (marca === 0xffe1 && v.getUint32(p + 4) === 0x45786966) return leerGps(v, p + 10);
        if ((marca & 0xff00) !== 0xff00) break;
        p += 2 + largo;
      }
    } catch (e) { /* foto sin metadatos legibles */ }
    return null;
  }
  function leerGps(v, base) {
    const chico = v.getUint16(base) === 0x4949;
    const u16 = (o) => v.getUint16(base + o, chico), u32 = (o) => v.getUint32(base + o, chico);
    const buscar = (ifd, etiqueta) => {
      for (let i = 0, n = u16(ifd); i < n; i++) if (u16(ifd + 2 + i * 12) === etiqueta) return ifd + 2 + i * 12;
      return null;
    };
    const gps = buscar(u32(4), 0x8825);
    if (gps == null) return null;
    const ifd = u32(gps + 8);
    const grados = (etiqueta) => {
      const e = buscar(ifd, etiqueta);
      if (e == null) return null;
      const o = u32(e + 8);
      const r = (i) => u32(o + i * 8) / (u32(o + i * 8 + 4) || 1);
      return r(0) + r(1) / 60 + r(2) / 3600;
    };
    const letra = (etiqueta) => { const e = buscar(ifd, etiqueta); return e == null ? '' : String.fromCharCode(v.getUint8(base + e + 8)); };
    let lat = grados(2), lon = grados(4);
    if (lat == null || lon == null || (lat === 0 && lon === 0)) return null;
    if (letra(1) === 'S') lat = -lat;
    if (letra(3) === 'W') lon = -lon;
    return { lat, lon };
  }

  // Reduce la foto en el teléfono: sube más rápido con mala señal y ya va sin metadatos.
  async function reducir(archivo) {
    try {
      const img = await createImageBitmap(archivo, { imageOrientation: 'from-image' });
      const escala = Math.min(1, LADO_MAXIMO / Math.max(img.width, img.height));
      const lienzo = document.createElement('canvas');
      lienzo.width = Math.round(img.width * escala);
      lienzo.height = Math.round(img.height * escala);
      lienzo.getContext('2d').drawImage(img, 0, 0, lienzo.width, lienzo.height);
      return await new Promise((ok) => lienzo.toBlob(ok, 'image/jpeg', 0.8));
    } catch (e) { return archivo; }
  }

  window.reporte = () => ({
    paso: 1, tipo: '', clase: 'riesgo', profundidad: '', gravedad: 'cuidado', gravedadTocada: false, nota: '',
    foto: null, vistaFoto: '', lat: null, lon: null, precision: null, origen: '',
    gps: '', codigoGps: 0, pideContacto: false, pideDuracion: false, duraDias: 0, contacto: '', nombre: '', puntos: 0, textoPuntos: '',
    vistoEn: new Date().toISOString(), enviando: false, error: '',
    tituloFinal: '', textoFinal: '', enlaceFinal: '/riesgos/', mini: null,

    init() {
      this.$watch('paso', (p) => { if (p === 4) this.$nextTick(() => this.abrirMiniMapa()); });
      try { this.nombre = localStorage.getItem('sos-nombre') || ''; } catch (e) { /* sin acceso */ }
      // Si se llegó desde el mapa (pulsación larga en un punto), ese punto manda sobre el GPS.
      const q = new URLSearchParams(location.search);
      const lat = Number(q.get('lat')), lon = Number(q.get('lon'));
      if (q.has('lat') && q.has('lon') && Math.abs(lat) <= 2 && lon < -88 && lon > -93) {
        this.lat = lat; this.lon = lon; this.origen = 'mapa';
        return;
      }
      this.pedirGps();
    },
    get alturaAgua() { return ALTURA[this.profundidad]; },
    get ejemploDeNota() {
      return {
        riesgo: 'Ejemplo: el agua corre fuerte hacia la esquina',
        bueno: 'Ejemplo: ya volvió la luz en el barrio; vecinos reparten almuerzos en la cancha',
        ayuda: 'Ejemplo: reciben agua y ropa seca, de 8 a 18 h; hacen falta voluntarios para clasificar',
        observa: 'Ejemplo: en esta esquina el agua llegó al bordillo y no entró a las casas',
      }[this.clase];
    },
    get textoUbicacion() {
      const de = { gps: 'Usamos la ubicación de tu teléfono, tomada ahora.', foto: 'Usamos la ubicación guardada en la foto.', mano: 'Punto puesto a mano.', mapa: 'Es el punto que marcaste en el mapa.' }[this.origen]
        || 'No tenemos tu ubicación.';
      return de + ' Mueve el mapa hasta que el pin quede en el lugar.';
    },

    // Lo que se le dice a la persona sobre la ubicación de su teléfono, con los pasos para arreglarlo.
    get avisoGps() {
      const esIphone = /iPhone|iPad|iPod/.test(navigator.userAgent);
      if (this.gps === 'ok') {
        const m = Math.round(this.precision || 0);
        if (m > 150) return { titulo: `Ubicación poco precisa (±${m} m).`, pasos: ['Tu teléfono no sabe bien dónde estás. Sal a cielo abierto y vuelve a tocar el botón, o mueve el mapa hasta que el pin quede en el lugar.'] };
        return { titulo: `Ubicación tomada (±${Math.max(m, 1)} m).`, pasos: ['¿El pin está donde ocurre? Si estás lejos del lugar, mueve el mapa hasta él.'] };
      }
      if (this.gps === 'inseguro') return { titulo: 'Esta página no puede pedir tu ubicación.', pasos: ['Ábrela en sosgalapagos.org/riesgos o mueve el mapa hasta el lugar.'] };
      if (this.gps === 'sin_soporte') return { titulo: 'Este navegador no da la ubicación.', pasos: ['Mueve el mapa hasta que el pin quede en el lugar.'] };
      if (this.gps === 'denegado') {
        return {
          titulo: 'No tenemos permiso para ver tu ubicación.',
          pasos: esIphone
            ? ['1. Abre Ajustes → Privacidad y seguridad → Localización y enciéndela.', '2. En esa lista entra a «Sitios web de Safari» (o a tu navegador) y elige «Al usar la app».', '3. Vuelve aquí y toca otra vez el botón. O mueve el mapa hasta el lugar.']
            : ['1. Enciende la ubicación del teléfono (desliza desde arriba y toca «Ubicación»).', '2. Toca el candado o el icono junto a la dirección de la página → Permisos → Ubicación → Permitir.', '3. Vuelve aquí y toca otra vez el botón. O mueve el mapa hasta el lugar.'],
        };
      }
      if (this.gps === 'apagado') return { titulo: 'El teléfono no encontró su ubicación.', pasos: ['Revisa que la ubicación (GPS) esté encendida y que no estés en modo avión.', 'Si estás bajo techo, acércate a una ventana y vuelve a tocar el botón. O mueve el mapa hasta el lugar.'] };
      if (this.gps === 'tardo') return { titulo: 'La ubicación tardó demasiado.', pasos: ['Vuelve a tocar el botón; a cielo abierto es más rápido. O mueve el mapa hasta el lugar.'] };
      return null;
    },

    // `pedida` es true cuando la persona tocó el botón: entonces su ubicación manda sobre la foto o el mapa.
    pedirGps(pedida) {
      if (!window.isSecureContext) { if (pedida) this.gps = 'inseguro'; return; }
      if (!navigator.geolocation) { if (pedida) this.gps = 'sin_soporte'; return; }
      if (pedida) this.gps = 'buscando';
      navigator.geolocation.getCurrentPosition((p) => {
        if (!pedida && ['foto', 'mano', 'mapa'].includes(this.origen)) return; // la foto, la mano o el punto del mapa mandan
        this.lat = p.coords.latitude; this.lon = p.coords.longitude;
        this.precision = p.coords.accuracy; this.origen = 'gps'; this.gps = 'ok';
        if (this.mini) this.mini.jumpTo({ center: [this.lon, this.lat], zoom: Math.max(this.mini.getZoom(), 17) });
        if (pedida && navigator.vibrate) navigator.vibrate(15);
      }, (error) => {
        this.codigoGps = error.code;
        // Si no se pidió con el botón, solo se anota: el aviso sale al llegar al paso del lugar.
        this.gps = { 1: 'denegado', 2: 'apagado', 3: 'tardo' }[error.code] || 'apagado';
      }, { enableHighAccuracy: true, timeout: pedida ? 20000 : 10000, maximumAge: pedida ? 0 : 30000 });
    },

    async alElegirFoto(e) {
      const archivo = e.target.files[0];
      if (!archivo) return;
      const lugar = await ubicacionDeFoto(archivo);
      // La foto da el lugar, salvo que la persona ya haya marcado el punto en el mapa: una foto
      // de la galería puede ser de otro sitio.
      if (lugar && this.origen !== 'mapa') { this.lat = lugar.lat; this.lon = lugar.lon; this.origen = 'foto'; this.precision = null; }
      this.foto = await reducir(archivo);
      if (this.vistaFoto) URL.revokeObjectURL(this.vistaFoto);
      this.vistaFoto = URL.createObjectURL(this.foto);
      e.target.value = ''; // permite volver a elegir la misma foto
      this.paso = 2;
    },
    sinFoto() { this.foto = null; this.vistaFoto = ''; this.paso = 2; },

    elegirTipo(codigo, clase, pideContacto, pideDuracion) {
      this.tipo = codigo;
      this.pideContacto = Boolean(pideContacto);
      this.pideDuracion = Boolean(pideDuracion);
      this.clase = clase || 'riesgo';
      if (CON_AGUA.includes(codigo)) { this.paso = 3; return; }
      this.profundidad = 'sin_dato';
      if (!this.gravedadTocada) this.gravedad = codigo === 'cable' || codigo === 'via_cortada' ? 'no_pasar' : 'cuidado';
      this.paso = 4;
    },
    elegirProfundidad(valor) {
      this.profundidad = valor;
      // Se propone una gravedad según la altura; «peligro de vida» solo lo elige la persona.
      this.gravedad = ['rodilla', 'cintura', 'puerta_auto'].includes(valor) ? 'no_pasar' : 'cuidado';
      this.paso = 4;
    },

    abrirMiniMapa() {
      const centro = this.lon != null ? [this.lon, this.lat] : cfg.centro;
      if (this.mini) { this.mini.resize(); this.mini.jumpTo({ center: centro }); return; }
      this.mini = new maplibregl.Map({
        container: 'mini-mapa', style: SOS.estiloBase(), center: centro, zoom: 17,
        maxBounds: [[-93.2, -2.4], [-88.0, 1.6]], attributionControl: { compact: true }, dragRotate: false, fadeDuration: 0,
      });
      this.mini.touchZoomRotate.disableRotation();
      this.mini.on('dragend', () => { this.origen = 'mano'; this.precision = null; if (this.gps === 'ok') this.gps = ''; });
    },

    campos() {
      const c = this.mini ? this.mini.getCenter() : { lng: this.lon, lat: this.lat };
      return {
        tipo: this.tipo, profundidad: this.profundidad, gravedad: this.gravedad, nota: this.nota.trim(),
        lat: c.lat, lon: c.lng, precision: this.origen === 'gps' ? this.precision : '', visto_en: this.vistoEn, foto: this.foto,
        contacto: this.pideContacto ? this.contacto.trim() : '', nombre: this.nombre.trim(),
        dura_dias: this.pideDuracion && this.duraDias ? this.duraDias : '',
      };
    },

    async enviar() {
      this.error = '';
      // Sin ubicación del teléfono, de la foto ni puesta a mano, el pin estaría en cualquier parte.
      if (!this.origen) {
        this.error = 'Falta el lugar. Toca «Estoy aquí: usar mi ubicación» o mueve el mapa hasta que el pin quede donde ocurre.';
        return;
      }
      if (this.pideContacto && this.contacto.replace(/\D/g, '').length < 7) {
        this.error = 'Pon un teléfono de contacto del lugar, para que la gente llame antes de ir.';
        return;
      }
      try { localStorage.setItem('sos-nombre', this.nombre.trim()); } catch (e) { /* sin acceso */ }
      this.enviando = true;
      const campos = this.campos();
      try {
        const r = await SOS.enviarReporte(campos);
        const datos = await r.json().catch(() => ({}));
        if (!r.ok) { this.error = datos.error || 'No se pudo enviar. Intenta otra vez.'; return; }
        this.tituloFinal = datos.duplicado ? 'Ya estaba reportado' : 'Reporte enviado';
        this.textoFinal = datos.duplicado
          ? 'Alguien ya había avisado de esto aquí mismo. Tu aviso confirma que sigue ahí y renueva el plazo.'
          : 'Ya aparece en el mapa como «por verificar». Se retira solo cuando pase su plazo.';
        if (this.clase !== 'riesgo' && !datos.duplicado) this.textoFinal = 'Gracias. Ya aparece en el mapa.';
        if (this.clase === 'observa' && !datos.duplicado) this.textoFinal = 'Gracias. Con lo que viste se corrige el mapa de riesgo. Ya aparece en el mapa.';
        this.enlaceFinal = '/riesgos/?r=' + datos.id;
        this.puntos = datos.puntos || 0;
        this.textoPuntos = `Ganaste ${this.puntos} puntos${datos.nombre ? ', ' + datos.nombre : ''}. Llevas ${datos.total || this.puntos}.`
          + (datos.nombre ? '' : ' La próxima vez pon tu nombre o apodo para aparecer en la tabla.');
        this.paso = 5;
      } catch (e) {
        // Sin señal: queda guardado en el teléfono con la hora en que se vio.
        await SOS.cola.guardar(campos);
        this.tituloFinal = 'Guardado en tu teléfono';
        this.textoFinal = 'No hay señal. El reporte se enviará solo cuando vuelva la conexión, con la hora de ahora.';
        this.paso = 5;
      } finally { this.enviando = false; }
    },
  });
})();
