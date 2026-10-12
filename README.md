# ProEshop — Seguimiento premium por tienda

## Cambios
- Seguimiento visual independiente por tienda con estados, referencias y totales propios.
- Historial de eventos por tienda en la base persistente.
- Historial anterior y recibos conservados como compatibilidad.
- Diseño adaptable a móvil y escritorio, en la estética oscura premium de ProEshop.

## Railway: despliegue seguro
1. Haz una copia de seguridad del volumen persistente antes de desplegar.
2. Reemplaza los archivos de la aplicación por los de este paquete.
3. Conserva el volumen actual y `DATABASE_PATH=/data/shopcart.db`.
4. Conserva las variables de entorno existentes, incluidas las de Brevo, Telegram, autenticación y administración.
5. No borres ni recrees `/data/shopcart.db`. Al arrancar se crea únicamente la tabla nueva `store_order_events` y su índice; las tablas y filas existentes no se eliminan.
6. Comprueba `/health`, inicia sesión, abre “Mis pedidos” y prueba un pedido con dos tiendas. Cambiar el estado de una referencia de tienda debe afectar únicamente esa tienda.

## Notas
El seguimiento representa los estados registrados en ProEshop. No acredita una compra real, un pago, ni el movimiento físico de un paquete. La guía de transportista solo podrá mostrarse cuando se integre una fuente real.
