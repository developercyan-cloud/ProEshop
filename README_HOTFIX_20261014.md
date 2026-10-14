PROESHOP HOTFIX — 2026-10-14

Cambios incluidos:
- Interfaz principal muestra únicamente Rolex, HUBLOT y Joyería.
- Explora por categoría ejecuta el catálogo de la marca elegida sin depender de la tienda seleccionada previamente.
- API limita nuevas búsquedas y altas al carrito a esas tres categorías.
- El endpoint /api/state devuelve solo plataformas activas y la versión incluida define JEWELERS_CATALOG antes de los endpoints que lo usan.
- Los catálogos de HUBLOT usan imágenes de respaldo del catálogo local y no necesitan consultar páginas de producto para mostrar resultados; si se usan URL de imágenes oficiales externas, el sitio puede responder 403.
- El precio de Rolex se calcula con descuento interno del 50% también en servidor. No es una promoción oficial de Rolex.

DESPLIEGUE:
1. Sustituye el código de la aplicación por el contenido de este ZIP.
2. Conserva las variables de entorno actuales.
3. Conserva DATABASE_PATH=/data/shopcart.db y el volumen persistente de Railway; NO borres el volumen ni la base de datos.
4. Redeploy y luego abre la miniapp de nuevo; si ves la versión antigua, cierra y vuelve a abrir la miniapp para recargar los archivos estáticos.

Las imágenes de respaldo son ilustrativas y no deben anunciarse como fotografías oficiales verificadas. Los precios deben confirmarse antes de vender.
