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
    paso: 1, tipo: '', profundidad: '', gravedad: 'cuidado', gravedadTocada: false, nota: '',
    foto: null, lat: null, lon: null, precision: null, origen: '',
    vistoEn: new Date().toISOString(), enviando: false, error: '',
    tituloFinal: '', textoFinal: '', enlaceFinal: '/riesgos/', mini: null,

    init() {
      this.$watch('paso', (p) => { if (p === 4) this.$nextTick(() => this.abrirMiniMapa()); });
      this.$watch('gravedad', () => {});
      this.pedirGps();
    },
    get alturaAgua() { return ALTURA[this.profundidad]; },
    get textoUbicacion() {
      const de = { gps: 'Usamos la ubicación de tu teléfono.', foto: 'Usamos la ubicación guardada en la foto.', mano: 'Punto puesto a mano.' }[this.origen]
        || 'No tenemos tu ubicación.';
      return de + ' Mueve el mapa hasta que el pin quede en el lugar.';
    },

    pedirGps() {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition((p) => {
        if (this.origen === 'foto' || this.origen === 'mano') return; // la foto o la mano mandan
        this.lat = p.coords.latitude; this.lon = p.coords.longitude;
        this.precision = p.coords.accuracy; this.origen = 'gps';
        if (this.mini) this.mini.jumpTo({ center: [this.lon, this.lat] });
      }, () => {}, { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
    },

    async alElegirFoto(e) {
      const archivo = e.target.files[0];
      if (!archivo) return;
      const lugar = await ubicacionDeFoto(archivo);
      if (lugar) { this.lat = lugar.lat; this.lon = lugar.lon; this.origen = 'foto'; this.precision = null; }
      this.foto = await reducir(archivo);
      this.paso = 2;
    },
    sinFoto() { this.foto = null; this.paso = 2; },

    elegirTipo(codigo) {
      this.tipo = codigo;
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
      this.mini.on('dragend', () => { this.origen = 'mano'; this.precision = null; });
    },

    campos() {
      const c = this.mini ? this.mini.getCenter() : { lng: this.lon, lat: this.lat };
      return {
        tipo: this.tipo, profundidad: this.profundidad, gravedad: this.gravedad, nota: this.nota.trim(),
        lat: c.lat, lon: c.lng, precision: this.origen === 'gps' ? this.precision : '', visto_en: this.vistoEn, foto: this.foto,
      };
    },

    async enviar() {
      this.error = ''; this.enviando = true;
      const campos = this.campos();
      try {
        const r = await SOS.enviarReporte(campos);
        const datos = await r.json().catch(() => ({}));
        if (!r.ok) { this.error = datos.error || 'No se pudo enviar. Intenta otra vez.'; return; }
        this.tituloFinal = datos.duplicado ? 'Ya estaba reportado' : 'Reporte enviado';
        this.textoFinal = datos.duplicado
          ? 'Alguien ya había avisado de esto aquí mismo. Tu aviso confirma que sigue ahí y renueva el plazo.'
          : 'Ya aparece en el mapa como «por verificar». Se retira solo cuando pase su plazo.';
        this.enlaceFinal = '/riesgos/?r=' + datos.id;
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
