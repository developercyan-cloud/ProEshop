# ProEshop — paquete corregido

## Correcciones incluidas
- Se agregó Jewelers Toy Store al selector de tiendas.
- Se acepta el dominio `jewelerstoystore.com` al agregar al carrito y se mantiene la referencia de la tienda.
- Se muestra el descuento de Jewelers del 50% de forma coherente entre resultados, detalle y carrito; es una promoción simulada de ProEshop.
- Se añadieron controles administrativos para cargar pedidos por tienda, cambiar el estado permitido, registrar una nota y reintentar un correo fallido.
- Se aplicaron estilos oscuros de alto contraste al panel administrativo y sus formularios.
- Se corrigió el nombre del campo de correo del checkout (`customer_email`), conservando compatibilidad con versiones que envían `email`.
- El panel administrativo permite guardar/corregir el correo de pedidos antiguos y después reintentar el envío.
- Se corrigió el reintento cuando aún no existía un registro de notificación; la ruta `/api/admin/orders/{order_ref}/retry-email` está incluida en este backend.
- El mensaje de checkout diferencia entre correo aceptado por el proveedor y correo pendiente/fallido.

## Despliegue seguro en Railway
1. Haz copia de seguridad del volumen persistente antes de desplegar.
2. Despliega los archivos de este paquete conservando la estructura `static/`.
3. Conserva el volumen actual y `DATABASE_PATH=/data/shopcart.db`.
4. Conserva las variables actuales de Telegram, Brevo, autenticación y administración. No pegues secretos en el chat.
5. No borres ni recrees la base de datos. Las migraciones son aditivas.
6. Verifica `/health`, inicia sesión y prueba una adición al carrito de Jewelers.
7. En Cuenta → Panel administrativo, verifica el correo mostrado en cada pedido. Si está vacío, escríbelo y pulsa **Guardar correo**; luego pulsa **Reintentar correo**.
8. Para pedidos nuevos, el checkout ahora guarda el correo correctamente. Cambia un estado permitido y revisa la respuesta y los logs de Railway. La aceptación por Brevo no garantiza entrega en bandeja; revisa spam y el panel transaccional.

## Alcance
Los pedidos, descuentos y estados de seguimiento son registros internos de ProEshop. No implican compra, pago ni envío real en las tiendas proveedoras.


## Corrección adicional de navegación y errores API
- La navegación cambia de pestaña antes de intentar actualizar datos, de modo que un fallo de red no impide abrir la vista.
- Las respuestas no JSON del backend ahora muestran el código HTTP y una indicación para revisar los logs de Railway, en vez del mensaje genérico “Respuesta inválida del servidor”.
- Los atajos de categorías llaman directamente a `/api/category/{category}` y ya no dependen de la tienda seleccionada arriba.
- El selector visible conserva únicamente Rolex, HUBLOT y Joyería.
- Validaciones realizadas en el paquete: compilación sintáctica de `main.py` y comprobación `node --check` de `static/app.js`.

Para aplicar: reemplaza los archivos del proyecto con los del ZIP y despliega una nueva versión. No borres el volumen persistente; conserva `DATABASE_PATH=/data/shopcart.db`. Si el servidor sigue devolviendo HTTP 500, comparte los logs del despliegue para identificar la excepción de backend concreta.
