# ShopCart — Telegram Mini App para Railway

ShopCart v2: Telegram Mini App de compras de demostración con catálogo consultado por SerpApi/Google Shopping, filtros y ordenación, carrito, desglose de subtotal/impuestos/envío, referencias de pedido, seguimiento ilustrativo, notificación de Telegram y persistencia SQLite.

## Importante

- No realiza pedidos ni pagos reales.
- No solicita credenciales de Amazon, Target ni Walmart.
- La búsqueda de productos usa SerpApi / Google Shopping y filtra resultados de Amazon.com, Target.com o Walmart.com. Requiere `SERPAPI_KEY`; el servicio puede tener límites o costes según tu plan.
- Los precios se muestran en USD cuando el proveedor devuelve un precio numérico; pueden variar por ubicación, vendedor, impuestos o disponibilidad y deben verificarse en la página del comercio. La app no realiza pedidos ni pagos reales.

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
   - `SERPAPI_KEY`: clave API de SerpApi para consultar resultados de Google Shopping y precios. Sin ella, se mantiene el enlace a la búsqueda oficial, sin precios automáticos.
   - `ESTIMATED_TAX_RATE`: tasa estimada de impuestos para el simulador; por defecto `0.08` (8%). No representa la tasa exacta de una jurisdicción.
   - `ESTIMATED_SHIPPING_FEE`: envío estimado fijo en USD; por defecto `5.99`.
4. Añade un Railway Volume montado en `/data` para persistir el historial y saldo.
5. Genera un dominio público HTTPS y actualiza `PUBLIC_BASE_URL` con ese dominio.
6. En `@BotFather`, configura el dominio de la Mini App para el bot mediante `/setdomain` con el dominio público de Railway (sin `https://`).
7. Vuelve a desplegar. En el arranque, la aplicación registra el webhook en Telegram.
8. Abre el bot en Telegram y envía `/start`; pulsa “Abrir ShopCart”.

## Uso

- El usuario se autentica dentro de la miniapp con las credenciales demo configuradas en Railway.
- Selecciona Walmart, Amazon o Target.
- Busca el artículo en la tienda seleccionada; si `SERPAPI_KEY` está configurada, aparecerán resultados con precio en USD e imagen cuando el proveedor los facilite.
- Pulsa “Agregar” en un resultado para añadirlo al carrito ficticio; también puedes registrar un producto manualmente.
- Confirma la compra ficticia: se descuenta el saldo virtual y se guarda el historial por ID de Telegram.
- Las compras y el saldo son simulados y no tienen valor monetario.

## Catálogos en vivo

El endpoint `/api/search` consulta Google Shopping a través de SerpApi, filtra resultados por comercio y solo presenta resultados que incluyen precio numérico. Si el proveedor devuelve un enlace de redirección en lugar de un enlace HTTPS de la tienda, se usa la búsqueda oficial de esa tienda para evitar enlaces externos inesperados. Se necesita `SERPAPI_KEY` en Railway. Los precios son orientativos y deben verificarse en la página final del comercio; no constituyen una garantía de precio o disponibilidad.

## Seguridad

- `initData` se valida mediante HMAC según el esquema oficial de Telegram.
- Token de sesión aleatorio, expiración por inactividad y consultas SQL parametrizadas.
- Usa HTTPS, mantén los secretos en Variables de Railway y no los subas a GitHub.
- La contraseña demo se transmite al backend por HTTPS; no uses contraseñas reales de terceros.
- Para uso multiusuario en producción, sustituye el login compartido por cuentas individuales, limitación de intentos y gestión segura de usuarios.

## Checkout y seguimiento de demostración

- `POST /api/purchase` calcula subtotal + impuestos estimados + envío estimado, valida el saldo ficticio y crea un registro en `orders`.
- Los artículos de `purchases` se vinculan mediante `order_ref`; la inicialización añade esa columna de forma compatible con bases SQLite anteriores.
- Los estados de seguimiento se presentan como ilustrativos. No se crea una orden real en Amazon, Target ni Walmart, no se genera una etiqueta de envío y no se cobra dinero.
- Se recomienda montar un volumen Railway en `/data`, usar una sola réplica con SQLite y mantener todas las claves privadas en variables de entorno.
