/* Mapa base: extracto PMTiles de Galápagos, estilado en gris claro.
   Los datos son de OpenStreetMap (ODbL) y el esquema de Protomaps. */
(function () {
  'use strict';
  const SOS = window.SOS;
  const protocolo = new pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocolo.tile);

  // Tierra en gris claro y mar en azul: parte del sabor «light» de Protomaps y le quita el color a la tierra.
  function sabor() {
    const s = Object.assign({}, basemaps.namedFlavor('light'));
    const grises = {
      // El mar va en azul claro para que la costa se lea de un vistazo; la tierra sigue gris.
      background: '#b3d1e2', earth: '#f3f3f1', water: '#b3d1e2',
      park_a: '#e9ece6', park_b: '#e6eae2', wood_a: '#e7eae3', wood_b: '#e4e8df', scrub_a: '#eaece6', scrub_b: '#e8eae3',
      glacier: '#f3f3f1', sand: '#efeeea', beach: '#efeeea', hospital: '#efeded', industrial: '#ecebe9', school: '#efeeeb',
      zoo: '#e9ece6', military: '#ecebe9', aerodrome: '#e9e9e7', runway: '#dcdcda', pedestrian: '#ecebe8', pier: '#e4e4e2',
      buildings: '#e0dfdc',
      minor_service: '#ffffff', minor_a: '#ffffff', minor_b: '#ffffff', link: '#ffffff', other: '#ffffff',
      major: '#ffffff', highway: '#ffffff', minor_service_casing: '#dcdcda', minor_casing: '#dcdcda',
      link_casing: '#d2d2d0', major_casing_early: '#d2d2d0', major_casing_late: '#d2d2d0',
      highway_casing_early: '#c8c8c6', highway_casing_late: '#c8c8c6',
      roads_label_minor: '#7a7a78', roads_label_major: '#5c5c5a', city_label: '#3f3f3d', subplace_label: '#6a6a68',
      ocean_label: '#5f879c', state_label: '#9a9a98', country_label: '#8a8a88', address_label: '#9a9a98',
    };
    for (const k of Object.keys(grises)) if (k in s) s[k] = grises[k];
    return s;
  }

  SOS.estiloBase = function () {
    const e = location.origin + SOS.cfg.estaticos;
    return {
      version: 8,
      glyphs: e + 'base/glifos/{fontstack}/{range}.pbf',
      sprite: e + 'base/iconos/light',
      sources: {
        base: {
          type: 'vector',
          url: 'pmtiles://' + e + 'base/galapagos.pmtiles',
          attribution: '© <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> · <a href="https://protomaps.com">Protomaps</a>',
        },
      },
      // Sin los puntos de interés de la base (tiendas, restaurantes): tapan los reportes.
      layers: basemaps.layers('base', sabor(), { lang: 'es' }).filter((l) => !l.id.startsWith('pois')).concat([
        // Anclas invisibles: fijan el orden base < base ráster < capas < pines.
        { id: 'ancla-raster', type: 'background', paint: { 'background-opacity': 0 } },
        { id: 'ancla-capas', type: 'background', paint: { 'background-opacity': 0 } },
        { id: 'ancla-pines', type: 'background', paint: { 'background-opacity': 0 } },
      ]),
    };
  };

  // Mapas base alternativos (teselas de terceros): se cargan solo si se eligen.
  SOS.ponerBase = function (mapa, def) {
    if (mapa.getLayer('base-raster')) mapa.removeLayer('base-raster');
    if (mapa.getSource('base-raster')) mapa.removeSource('base-raster');
    if (!def) return;
    const urls = def.url.includes('{s}') ? ['a', 'b', 'c'].map((s) => def.url.replace('{s}', s)) : [def.url];
    mapa.addSource('base-raster', {
      type: 'raster', tiles: urls, tileSize: 256, maxzoom: def.maxNativeZoom || def.maxZoom || 19, attribution: def.atribucion,
    });
    mapa.addLayer({ id: 'base-raster', type: 'raster', source: 'base-raster' }, 'ancla-raster');
  };
})();
