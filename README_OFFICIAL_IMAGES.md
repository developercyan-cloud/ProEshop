# ProEshop — imágenes oficiales, carrito y checkout

## Correcciones
- El carrito y el checkout renderizan la imagen guardada para cada producto, junto con título, cantidad y subtotal.
- Las imágenes se guardan en `carts.image`; la migración añade esa columna sin borrar ni recrear tablas o pedidos.
- Las fichas de Jewelers Toy Store se consultan en el dominio oficial. Se amplió la extracción de metadatos e imágenes de producto para admitir CDN HTTPS usados por la tienda (por ejemplo, BigCommerce), ya que limitar la imagen al dominio de la página impedía mostrar varias fotos.
- El guardado en carrito admite los dominios HTTPS permitidos de imágenes oficiales/CDN.
- HUBLOT All Red y All Black enlazan a las fichas oficiales verificadas. Los demás modelos conservan enlaces de su colección oficial y no muestran una foto de otro reloj como si fuera la del modelo.
- El checkout utiliza `item.image` de la misma fila del carrito, de modo que cuando la ficha proporciona una imagen oficial, se usa esa misma imagen también en el checkout.

## Limitación importante
El catálogo local incluye modelos que no todos tienen una ficha individual oficial enlazada en el código. Para esos modelos no se debe afirmar que la foto está verificada ni inventar una correspondencia. La carga dinámica de imágenes oficiales depende de que Railway pueda acceder a la página del proveedor y de que la ficha publique sus metadatos. El paquete no ha sido desplegado ni probado contra la web en producción desde este entorno.

## Railway: conservar datos
- Mantén el volumen persistente existente y `DATABASE_PATH=/data/shopcart.db`.
- Conserva las variables de entorno actuales.
- No borres ni recrees la base de datos.
- Después del despliegue, prueba búsqueda, imagen, agregar al carrito y checkout para HUBLOT y Jewelers.
