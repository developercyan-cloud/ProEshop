# ShopCart — Telegram Mini App para Railway

Miniapp de compras ficticias con diseño azul/blanco inspirado en tiendas minoristas, autenticación de Telegram + usuario/contraseña de demostración, búsqueda por comercio, carrito, saldo virtual e historial persistente.

## Importante

- No realiza pedidos ni pagos reales.
- No solicita credenciales de Amazon, Target ni Walmart.
- Los precios en vivo no se inventan. Como aún no hay adaptadores de catálogo oficiales configurados, el usuario abre la búsqueda oficial y registra el precio que observa junto al enlace del producto.
- Para mostrar precios automáticamente, implementa únicamente adaptadores de APIs/proveedores oficialmente autorizados y compatibles con los términos de cada tienda.

## Desplegar en Railway

1. Sube estos archivos a un repositorio GitHub.
2. Crea un proyecto Railway y despliega el repositorio.
3. Añade variables:
   - `TELEGRAM_BOT_TOKEN`: token obtenido de `@BotFather`.
   - `PUBLIC_BASE_URL`: URL pública HTTPS de Railway, sin barra final.
   - `WEBHOOK_SECRET`: secreto aleatorio largo.
   - `DEMO_USERNAME`: por ejemplo `demo`.
   - `DEMO_PASSWORD`: contraseña robusta propia.
   - `DATABASE_PATH`: `/data/shopcart.db` si montas un volumen en `/data`; sin volumen, los datos SQLite pueden perderse al redeplegar.
4. Añade un Railway Volume montado en `/data` para persistir el historial y saldo.
5. Genera un dominio público HTTPS y actualiza `PUBLIC_BASE_URL` con ese dominio.
6. En `@BotFather`, configura el dominio de la Mini App para el bot mediante `/setdomain` con el dominio público de Railway (sin `https://`).
7. Vuelve a desplegar. En el arranque, la aplicación registra el webhook en Telegram.
8. Abre el bot en Telegram y envía `/start`; pulsa “Abrir ShopCart”.

## Uso

- El usuario se autentica dentro de la miniapp con las credenciales demo configuradas en Railway.
- Selecciona Walmart, Amazon o Target.
- Busca el artículo y abre la búsqueda oficial.
- Introduce nombre, precio observado, moneda y URL del producto para agregarlo al carrito ficticio.
- Confirma la compra ficticia: se descuenta el saldo virtual y se guarda el historial por ID de Telegram.
- Las compras y el saldo son simulados y no tienen valor monetario.

## Catálogos en vivo

El endpoint `/api/search` devuelve un enlace oficial. No incluye precios live hasta que se conecte una API autorizada por cada comercio. Los precios introducidos manualmente se consideran datos aportados por el usuario, no cotizaciones verificadas por la aplicación.

## Seguridad

- `initData` se valida mediante HMAC según el esquema oficial de Telegram.
- Token de sesión aleatorio, expiración por inactividad y consultas SQL parametrizadas.
- Usa HTTPS, mantén los secretos en Variables de Railway y no los subas a GitHub.
- La contraseña demo se transmite al backend por HTTPS; no uses contraseñas reales de terceros.
- Para uso multiusuario en producción, sustituye el login compartido por cuentas individuales, limitación de intentos y gestión segura de usuarios.
