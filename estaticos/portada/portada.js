// SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
// Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
// Portada: monta la animación de la lluvia de las próximas 24 horas (LluviaMapa.reel, en mapa/lluvia-mapa.js).
// Leaflet, el motor del mapa y los datos se piden cuando la caja se acerca a la pantalla, no con la página:
// la portada se puede leer y usar antes, y también si el mapa no llega. Las direcciones vienen en la caja
// (data-…), con su versión, desde la plantilla.
(function () {
  "use strict";
  const caja = document.querySelector("[data-reel]");
  if (!caja) return;
  const d = caja.dataset;
  const ESPERA_MS = 12000;  // pasado este tiempo sin mapa, la caja dice dónde ver la lluvia medida (el mapa entra igual si llega después)
  const guion = src => new Promise((ok, mal) => {
    const s = document.createElement("script");
    s.src = src; s.onload = ok; s.onerror = () => mal(new Error(src));
    document.head.appendChild(s);
  });
  const hoja = href => new Promise((ok, mal) => {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = href; l.onload = ok; l.onerror = () => mal(new Error(href));
    document.head.appendChild(l);
  });
  let pedido = false;
  async function montar() {
    if (pedido) return;
    pedido = true;
    const lento = setTimeout(() => { if (d.estado === "espera") d.estado = "fallo"; }, ESPERA_MS);
    try {
      await Promise.all([hoja(d.leafletEstilos), hoja(d.estilos),
        window.L && window.L.version ? null : guion(d.leaflet), window.LluviaMapa ? null : guion(d.motor)]);
      const reel = await window.LluviaMapa.reel(caja, {datos: d.datos, islas: d.islas, leaflet: () => Promise.resolve(window.L)});
      if (!reel) throw new Error("sin pronóstico");
      d.estado = "listo";
    } catch (e) {
      d.estado = "fallo";
    }
    clearTimeout(lento);
  }
  if ("IntersectionObserver" in window) {
    const o = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { o.disconnect(); montar(); } }, {rootMargin: "300px"});
    o.observe(caja);
  } else {
    montar();
  }
})();
