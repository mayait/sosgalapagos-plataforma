# Sección «Informes y mapas para descargar» en /riesgos/

Retirada el 21-nov-2026 por indicación de Julián: esa lista va solo en la portada del sitio (`sosgalapagos.org/#informes`), no en el mapa de riesgos.

Estuvo publicada unas horas. Leía el mismo índice que la portada (`/srv/sosgalapagos-descargas/indice.json`) y enlazaba los PDF de `/descargas/`.

- `informes.py`: lectura y validación del índice.
- `informes.html`: la lista que se mostraba bajo «Cerca de aquí».

Para volver a ponerla: restaurar los dos archivos, la ruta `informes/`, la vista y el ajuste `INFORMES_DIR`, y montar `/srv/sosgalapagos-descargas` en el contenedor.
