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


## Pagos reales con USDT por TRON
Se añadió checkout con USDT TRC-20, detección de transferencias confirmadas y cambio automático a `payment_review` (En revisión de pago). Consulta `README_USDT_TRON.md` para configuración de Railway y comprobaciones de despliegue. Configura `TRONGRID_API_KEY` para evitar depender de límites públicos.
