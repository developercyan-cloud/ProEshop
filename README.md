# ProEshop — pedidos independientes por tienda

## Archivos
- `main.py`: backend actualizado para crear una referencia y un estado por tienda, y enviar correos independientes por tienda mediante la integración Brevo existente.
- `requirements.txt`: dependencias del backend.
- `Procfile`: comando de inicio de Railway.

## Despliegue seguro en Railway
1. Haz una copia de seguridad del volumen persistente antes del despliegue.
2. Sustituye el backend por `main.py` y conserva los archivos de configuración actuales.
3. Mantén `DATABASE_PATH=/data/shopcart.db` y no elimines ni recrees el volumen de Railway.
4. Conserva las variables de entorno existentes, incluidas las de Telegram, administración y Brevo.
5. Despliega y prueba un carrito con productos de dos tiendas. Cada tienda debe generar su propio correo y su propia referencia de pedido.

El backend usa migraciones SQLite aditivas (`CREATE TABLE IF NOT EXISTS` y `ALTER TABLE` cuando falta una columna); no elimina tablas ni registros existentes. Aun así, realiza una copia de seguridad antes de desplegar.

Las compras de este proyecto son de demostración: el registro de pedido/correo no acredita una compra real ni un pago al comercio.
