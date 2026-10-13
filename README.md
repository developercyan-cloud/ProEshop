# ProEshop — paquete corregido

## Correcciones incluidas
- Se agregó Jewelers Toy Store al selector de tiendas.
- Se acepta el dominio `jewelerstoystore.com` al agregar al carrito y se mantiene la referencia de la tienda.
- Se muestra el descuento de Jewelers del 50% de forma coherente entre resultados, detalle y carrito; es una promoción simulada de ProEshop.
- Se añadieron controles administrativos para cargar pedidos por tienda, cambiar el estado permitido, registrar una nota y reintentar un correo fallido.
- Se aplicaron estilos oscuros de alto contraste al panel administrativo y sus formularios.
- El mensaje de checkout diferencia entre correo aceptado por el proveedor y correo pendiente/fallido.

## Despliegue seguro en Railway
1. Haz copia de seguridad del volumen persistente antes de desplegar.
2. Despliega los archivos de este paquete conservando la estructura `static/`.
3. Conserva el volumen actual y `DATABASE_PATH=/data/shopcart.db`.
4. Conserva las variables actuales de Telegram, Brevo, autenticación y administración. No pegues secretos en el chat.
5. No borres ni recrees la base de datos. Las migraciones son aditivas.
6. Verifica `/health`, inicia sesión y prueba una adición al carrito de Jewelers.
7. En Cuenta → Panel administrativo, carga los pedidos, elige una transición permitida y guarda. La respuesta indica si el proveedor aceptó el correo; revisa también spam y los logs de Railway porque aceptación no garantiza entrega.

## Alcance
Los pedidos, descuentos y estados de seguimiento son registros internos de ProEshop. No implican compra, pago ni envío real en las tiendas proveedoras.
