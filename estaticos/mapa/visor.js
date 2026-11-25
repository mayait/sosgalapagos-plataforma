/* SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
   Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito. */
/* Visor de documentos (/riesgos/oficial/…, /riesgos/boletin/…).
   1. «Volver»: regresa a la página anterior del sitio. Si se llegó desde un aviso y no hay página
      anterior, el enlace lleva a la portada.
   2. El PDF se dibuja en la misma página, hoja por hoja y solo al acercarse a cada una,
      para no gastar la memoria del teléfono con un documento largo. */
(function () {
  const volver = document.querySelector('[data-volver]');
  if (volver) {
    let delSitio = false;
    try { delSitio = !!document.referrer && new URL(document.referrer).origin === location.origin; } catch (e) { /* sin referente */ }
    if (delSitio && history.length > 1) {
      volver.addEventListener('click', (e) => { e.preventDefault(); history.back(); });
    }
  }

  const caja = document.querySelector('[data-pdf]');
  if (!caja) return;
  const fallo = () => { caja.innerHTML = '<p class="docu-cargando">No se pudo mostrar el documento aquí. Puedes descargarlo con el botón de abajo.</p>'; };
  import(caja.dataset.lib).then(async (pdfjs) => {
    pdfjs.GlobalWorkerOptions.workerSrc = caja.dataset.obrero;
    const pdf = await pdfjs.getDocument({ url: caja.dataset.pdf }).promise;
    const nitidez = Math.min(window.devicePixelRatio || 1, 2);
    caja.innerHTML = '';
    const mirar = new IntersectionObserver((vistas) => {
      vistas.forEach((v) => { if (v.isIntersecting) { mirar.unobserve(v.target); dibujar(v.target); } });
    }, { rootMargin: '600px 0px' });
    async function dibujar(lienzo) {
      try {
        const hoja = await pdf.getPage(Number(lienzo.dataset.hoja));
        const escala = (caja.clientWidth / hoja.getViewport({ scale: 1 }).width) * nitidez;
        const vista = hoja.getViewport({ scale: escala });
        lienzo.width = Math.round(vista.width); lienzo.height = Math.round(vista.height);
        await hoja.render({ canvasContext: lienzo.getContext('2d'), viewport: vista }).promise;
      } catch (e) { /* una hoja que falla no tumba las demás */ }
    }
    const primera = (await pdf.getPage(1)).getViewport({ scale: 1 });
    for (let n = 1; n <= pdf.numPages; n++) {
      const lienzo = document.createElement('canvas');
      lienzo.dataset.hoja = n;
      lienzo.setAttribute('aria-label', 'Hoja ' + n + ' de ' + pdf.numPages);
      lienzo.style.aspectRatio = primera.width + ' / ' + primera.height;  // reserva el sitio antes de dibujar
      caja.appendChild(lienzo);
      mirar.observe(lienzo);
    }
  }).catch(fallo);
})();
