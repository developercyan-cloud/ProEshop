# ProEshop — Imágenes oficiales en carrito y checkout

## Cambios incluidos
- El carrito y el checkout muestran miniaturas por producto cuando la tienda ofrece una imagen oficial disponible.
- Las imágenes se transmiten al carrito y se guardan en la columna `carts.image`.
- Migración aditiva: en bases existentes se añade `carts.image` si falta; no elimina ni recrea tablas, pedidos ni filas.
- HUBLOT utiliza una imagen oficial de la ficha del Big Bang Original Soft Touch All Red y enlaza a la ficha oficial del modelo. Para otros modelos intenta leer la imagen Open Graph de la ficha oficial cuando hay una URL de producto identificada; si la página no ofrece una imagen compatible, conserva un marcador oscuro en vez de mostrar una foto ajena.
- Jewelers Toy Store usa URLs directas de fichas oficiales para el analizador, la batería y el cargador; el backend intenta extraer la imagen Open Graph de cada ficha oficial en paralelo.
- El checkout muestra imágenes, nombre, cantidad y subtotal de cada producto agrupado por tienda.
- Se mejoraron los fondos de “Resumen de compra”, el botón “Ver tienda” y los marcadores para mantener el tema oscuro.

## Límites
La obtención de imágenes desde las páginas oficiales depende de que esas páginas estén disponibles para el servidor y publiquen metadatos de imagen compatibles. Si el proveedor bloquea la consulta, no se inventa una imagen: se muestra el marcador oscuro. Los precios y promociones internas siguen sujetos a la lógica actual de ProEshop.

## Despliegue seguro en Railway
1. Respaldar el volumen antes del despliegue.
2. Conservar el volumen persistente y `DATABASE_PATH=/data/shopcart.db`.
3. Conservar todas las variables existentes (Brevo, Telegram, administración, búsqueda, moneda, impuestos y envío).
4. No borrar ni recrear `/data/shopcart.db`; la migración es aditiva.
5. Probar una búsqueda de HUBLOT y Jewelers, agregar un producto, abrir el carrito y continuar al checkout.

El paquete no se ha desplegado en Railway. Las comprobaciones locales validan sintaxis y migración SQLite; la carga de imágenes oficiales debe confirmarse desde Railway.
