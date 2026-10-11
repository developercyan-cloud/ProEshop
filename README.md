# ProEshop — Telegram Mini App para Railway

Aplicación para comparar resultados de Amazon, Walmart y Target mediante SerpApi/Google Shopping. Incluye autenticación con Telegram Mini App `initData`, búsqueda, carrito, pedidos registrados, preferencias de avisos y métricas administrativas.

## Funcionalidades

- Inicio responsive con navegación inferior, categorías y animaciones suaves.
- Búsqueda por tienda, filtros de precio, ordenamiento, ficha de producto y comparador de hasta tres productos.
- Carrito persistente en SQLite con cantidades editables y desglose de subtotal, impuestos estimados, envío y total.
- Historial de pedidos, línea de tiempo de pedidos y recibo imprimible sin valor fiscal.
- Notificaciones opcionales de Telegram para confirmaciones de pedidos e inicio de sesión; requieren configurar el bot.
- Panel administrativo protegido con `ADMIN_API_KEY`, métricas de actividad y eventos de auditoría.
- Cabeceras de seguridad, limitación básica de solicitudes, índices SQLite, WAL y `busy_timeout`.
- Migraciones aditivas: no elimina ni recrea tablas existentes.

## Variables de entorno para Railway

Configura estas variables en el servicio. **Conserva el volumen persistente existente montado en `/data` y utiliza `DATABASE_PATH=/data/shopcart.db`.** El código también usa esa ruta por defecto.

- `DATABASE_PATH=/data/shopcart.db`
- `TELEGRAM_BOT_TOKEN` — token del bot creado con BotFather.
- `PUBLIC_BASE_URL=https://TU-SERVICIO.up.railway.app`
- `WEBHOOK_SECRET` — cadena aleatoria larga.
- `DEMO_USERNAME` y `DEMO_PASSWORD` — variables de acceso existentes; no uses las de comercios.
- `ADMIN_API_KEY` — clave aleatoria, independiente de la contraseña de acceso, para métricas administrativas.
- `SERPAPI_KEY` — necesaria para obtener resultados del proveedor.
- `INITIAL_FAKE_BALANCE=1000.00`, `CURRENCY=USD`, `ESTIMATED_TAX_RATE=0.08`, `ESTIMATED_SHIPPING_FEE=5.99` (ajusta las estimaciones según tu configuración).
- `SESSION_TTL_MINUTES=120`

Genera secretos fuertes y no publiques `.env` ni tokens. El panel administrativo no estará disponible si `ADMIN_API_KEY` no está configurada. La limitación de solicitudes está en memoria por proceso y no reemplaza un WAF o un limitador distribuido.

## Instalación / actualización

1. Descomprime el paquete y reemplaza los archivos del proyecto conservando las variables de Railway y el volumen `/data`.
2. El paquete incluye `main.py`, `static/index.html`, `static/style.css`, `static/app.js`, `requirements.txt`, `Procfile`, `railway.toml`, `.env.example` y `.gitignore`.
3. Sube los cambios a tu repositorio o método de despliegue. Este paquete no realiza un despliegue por sí solo.
4. Verifica `https://TU-SERVICIO/health`, abre la Mini App desde Telegram y prueba búsqueda, carrito, recibo y panel administrativo.

## Alcance de las operaciones

El checkout registra la actividad dentro de ProEshop. No procesa pagos ni envía órdenes a Amazon, Walmart, Target o HUBLOT, y no crea guías de transporte. Los saldos y los importes de los recibos son registros internos, no comprobantes de pago. Los precios del proveedor pueden cambiar; confirma el precio final y la disponibilidad en la tienda oficial.


GUI restoration: the original ProEshop layout and store search area are retained. HUBLOT appears in a separate collapsed panel so it does not push out or replace the existing interface. HUBLOT keeps the 50% displayed discount; preserve DATABASE_PATH=/data/shopcart.db and the Railway persistent volume.


HUBLOT fix: `/api/search` returns local illustrative catalogue entries for HUBLOT as well as the client-side catalogue. This supports cached/older Telegram webviews; static asset URLs include a version query to invalidate cache. A non-matching query falls back to the catalogue instead of displaying an empty result set.
