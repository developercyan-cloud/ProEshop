# ProEshop: corrección de tiendas y navegación

Cambios:
- Se restauró `JEWELERS_CATALOG`, que faltaba y provocaba `NameError` en `/api/state`.
- La selección de tiendas y la búsqueda del servidor quedan limitadas a Rolex, HUBLOT y Joyería.
- Se reemplazaron las categorías genéricas por atajos que muestran una selección aleatoria de productos por marca.
- Se fijó el descuento simulado de Rolex al 50% en catálogo y cálculo del servidor.
- Se actualizó la versión de los archivos estáticos para invalidar caché del WebView.
- Se conservan los archivos de despliegue y la ruta de base de datos existente. No borres el volumen de Railway.

Importante: desplegar el ZIP en el mismo servicio y mantener `DATABASE_PATH=/data/shopcart.db` y el volumen persistente. La oferta del 50% es interna de ProEshop y no una promoción oficial de las marcas.
