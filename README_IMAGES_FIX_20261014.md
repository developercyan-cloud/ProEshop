# ProEshop — fix de imágenes y precios de catálogo

## Incluye
- 52 fichas HUBLOT con imágenes locales servidas desde `/static/images/hublot/`.
- 40 fichas Rolex con imágenes locales servidas desde `/static/images/rolex/`.
- 4 fichas de Joyería/Jewelers Toy Store con imágenes locales servidas desde `/static/images/jewelers/`.
- El 50% se calcula una sola vez en la respuesta de catálogo y vuelve a calcularse desde el precio base del catálogo al añadir al carrito.
- Las imágenes de producto del carrito y checkout usan las mismas rutas locales, sin depender de hotlinking externo.
- Las consultas que daban HTTP 403 a Hublot/Jewelers ya no bloquean la carga de las fichas.
- Los archivos JS/CSS llevan una versión nueva para evitar que el cliente conserve el JavaScript anterior.

## Importante sobre las imágenes y los precios
Los archivos de imagen incluidos son recortes visuales ilustrativos del catálogo de ProEshop y representaciones de producto; no son fotografías oficiales verificadas de cada referencia. Los precios de Rolex son valores de referencia del catálogo configurado en la aplicación y el 50% es una promoción interna de ProEshop, no una oferta oficial de Rolex. Confirma cada referencia, precio y disponibilidad antes de publicar una oferta comercial.

## Despliegue en Railway
1. Sube este ZIP al repositorio/servicio de ProEshop y despliega.
2. Conserva las variables de entorno actuales.
3. Conserva `DATABASE_PATH=/data/shopcart.db` y el volumen persistente; no borres ni recrees la base de datos.
4. Tras el despliegue, cierra y vuelve a abrir la Mini App para que cargue los recursos estáticos con la nueva versión.

## Validaciones realizadas
- `main.py` compila con `py_compile`.
- `static/app.js` pasa `node --check`.
- Se incluyen 52 imágenes HUBLOT, 40 Rolex y 4 Joyería dentro de `static/images/`.
