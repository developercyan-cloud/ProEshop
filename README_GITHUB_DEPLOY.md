# ProEshop — paquete completo para GitHub/Railway

## Incluye
- Catálogos Rolex, HUBLOT y Joyería.
- Imágenes locales incluidas en `static/catalog_images/` para reducir fallos por respuestas HTTP 403 de los proveedores.
- Navegación inferior, carrito, pedidos, cuenta y exploración por categoría.
- Amazon, Target y Walmart deshabilitados temporalmente tanto en la interfaz como en el endpoint de búsqueda.
- Descuento interno del 50 % para Rolex, HUBLOT y Joyería; no representa una promoción oficial de las marcas.

## Reemplazo del repositorio
1. Descarga y descomprime este ZIP.
2. Sube el contenido de la carpeta a la raíz del repositorio GitHub, reemplazando los archivos de aplicación existentes.
3. Confirma que `main.py`, `Procfile`, `railway.toml`, `requirements.txt` y la carpeta `static/` queden en la raíz.
4. Haz commit y push; después espera el despliegue en Railway.
5. Conserva las variables de entorno actuales.
6. **No elimines ni recrees el volumen persistente ni la base de datos.** Mantén `DATABASE_PATH=/data/shopcart.db`.
7. Después del despliegue, abre `/health`, vuelve a abrir la miniapp y prueba las pestañas Inicio, Buscar, Carrito, Pedidos y Cuenta.

## Notas
- Las imágenes de respaldo se sirven localmente. Deben tratarse como imágenes de catálogo ilustrativas y no como fotos oficiales verificadas cuando no se haya confirmado la fuente.
- Los precios de catálogo y los descuentos son referencias internas de ProEshop; confirma precio, disponibilidad y especificaciones con el proveedor antes de vender.
- Las funciones de compra/checkout registran pedidos en ProEshop; no ejecutan compras ni pagos reales en las tiendas externas.
