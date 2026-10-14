# ProEshop — verificación por código y sesión automática

Este parche cambia el registro para enviar un código numérico de 6 dígitos por correo, verificarlo dentro de la Mini App, mostrar un modal de éxito e iniciar sesión automáticamente antes de llevar al usuario a Inicio.

## Archivos incluidos
- `main.py` — endpoints de registro y verificación por código, con limitación de intentos; reutiliza la tabla `email_accounts` existente.
- `static/index.html` — modal para introducir el código y estado de registro exitoso.
- `static/app.js` — flujo de verificación, inicio de sesión automático y retorno a Inicio.

## Instalación
1. Haz una copia/commit de los archivos actuales.
2. Reemplaza `main.py`, `static/index.html` y `static/app.js` por los del ZIP, respetando las rutas.
3. Despliega en Railway. Conserva `DATABASE_PATH=/data/shopcart.db` y el volumen `/data`. No borres la base de datos.
4. Prueba con un correo nuevo: crear cuenta → recibir código → introducirlo en la Mini App → ver modal de éxito → llegar a Inicio con sesión iniciada.

El envío utiliza la configuración existente `BREVO_API_KEY` y `SMTP_FROM_EMAIL`, o el SMTP configurado. El código vence en 10 minutos y se almacena como hash. La verificación activa la cuenta una sola vez. No requiere migraciones ni elimina pedidos, pagos o historial.
