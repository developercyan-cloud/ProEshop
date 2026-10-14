# ProEshop — imágenes HUBLOT v5

- Se mantiene el catálogo de 52 referencias HUBLOT de ProEshop.
- Cada referencia ahora tiene una URL de ficha individual propuesta en `HUBLOT_PRODUCT_PAGES`; la imagen se obtiene desde esa ficha oficial, se cachea en memoria y se guarda en el carrito para reutilizarla en checkout.
- Los siete modelos Big Bang Original con URL de imagen oficial previamente verificada conservan sus URLs directas.
- La extracción sólo puede mostrar una foto si la ficha oficial existe, responde desde Railway y publica su imagen en el HTML. Algunas referencias del catálogo local pueden ser variantes históricas o no coincidir exactamente con un producto oficial actual; en esos casos se deja el marcador en lugar de asociar una foto incorrecta.
- La carga de 52 imágenes no se ha validado en Railway desde este entorno sin acceso directo a la red.

## Despliegue
Conservar el volumen de Railway y `DATABASE_PATH=/data/shopcart.db`. No borrar ni recrear la base de datos.
