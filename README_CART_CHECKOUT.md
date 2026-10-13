# ProEshop — mejoras incrementales de carrito y checkout

Este paquete parte de la versión estable `ProEshop_email_fix.zip`. Los cambios de esta entrega se concentran en `static/app.js`, `static/index.html` y `static/style.css`; el backend `main.py`, las rutas existentes, la configuración de correo y el esquema de la base de datos se mantienen sin cambios.

## Mejoras
- Checkout con desglose por tienda y cantidades.
- Presentación explícita de impuestos y envío estimados.
- Aviso de transparencia sobre promociones propias de ProEshop.
- Protección en la interfaz contra doble envío simultáneo del formulario.
- Si el pedido se registra pero falla la actualización posterior de la pantalla, no se presenta falsamente como si hubiera fallado el registro.
- Estilos de alto contraste para tarjetas del carrito y formulario de checkout, sin rediseñar la estructura general.

## Despliegue seguro en Railway
1. Descarga una copia de seguridad del volumen persistente antes de desplegar.
2. Despliega el contenido del ZIP manteniendo `main.py`, `Procfile`, `railway.toml`, `requirements.txt` y la carpeta `static/`.
3. Conserva el volumen y `DATABASE_PATH=/data/shopcart.db`; no borres ni recrees la base de datos.
4. Conserva las variables de entorno actuales, incluidas Brevo, Telegram y administración.
5. Prueba: agregar producto, cambiar cantidad, quitar producto, volver a abrir la app y confirmar un pedido de prueba.

## Alcance de las pruebas
- `node --check static/app.js`: correcto.
- `python -m py_compile main.py`: correcto.
- Inspección estática de la estructura de checkout y sus controles: correcta.
- No se ha desplegado en Railway ni se han hecho pedidos o envíos reales desde este paquete.

El checkout registra pedidos internos de demostración. No procesa pagos ni envía órdenes a los comercios.
