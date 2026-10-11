# ProEshop — Telegram Mini App para Railway

Aplicación de demostración para comparar resultados de Amazon, Walmart y Target mediante SerpApi/Google Shopping. Incluye autenticación con Telegram Mini App `initData`, búsqueda, carrito, pedidos simulados, preferencias de avisos y métricas administrativas.

## Funcionalidades

- Inicio responsive con navegación inferior, categorías y animaciones suaves.
- Búsqueda por tienda, filtros de precio, ordenamiento, ficha de producto y comparador de hasta tres productos.
- Carrito persistente en SQLite con cantidades editables y desglose de subtotal, impuestos estimados, envío y total.
- Historial de pedidos, línea de tiempo marcada como simulada y recibo imprimible sin valor fiscal.
- Catálogo HUBLOT ampliado con 52 modelos/variantes de referencia de las familias Big Bang, Classic Fusion y Spirit of Big Bang.
- Descuento simulado del 50% en los relojes HUBLOT aplicado en el servidor al añadirlos al carrito; el precio rebajado alimenta carrito, impuestos, checkout e historial. No es una promoción oficial ni una compra real.
- Notificaciones opcionales de Telegram para confirmaciones de pedidos demo e inicio de sesión; requieren configurar el bot.
- Panel administrativo protegido con `ADMIN_API_KEY`, métricas del simulador y eventos de auditoría.
- Cabeceras de seguridad, limitación básica de solicitudes, índices SQLite, WAL y `busy_timeout`.
- Migraciones aditivas: no elimina ni recrea tablas existentes.

## Variables de entorno para Railway

Configura estas variables en el servicio. **Conserva el volumen persistente existente montado en `/data` y utiliza `DATABASE_PATH=/data/shopcart.db`.** El código también usa esa ruta por defecto.

- `DATABASE_PATH=/data/shopcart.db`
- `TELEGRAM_BOT_TOKEN` — token del bot creado con BotFather.
- `PUBLIC_BASE_URL=https://TU-SERVICIO.up.railway.app`
- `WEBHOOK_SECRET` — cadena aleatoria larga.
- `DEMO_USERNAME` y `DEMO_PASSWORD` — credenciales de demostración propias; no uses las de comercios.
- `ADMIN_API_KEY` — clave aleatoria, independiente de la contraseña demo, para métricas administrativas.
- `SERPAPI_KEY` — necesaria para obtener resultados del proveedor.
- `INITIAL_FAKE_BALANCE=1000.00`, `CURRENCY=USD`, `ESTIMATED_TAX_RATE=0.08`, `ESTIMATED_SHIPPING_FEE=5.99` (ajusta las estimaciones según la demo).
- `SESSION_TTL_MINUTES=120`

Genera secretos fuertes y no publiques `.env` ni tokens. El panel administrativo no estará disponible si `ADMIN_API_KEY` no está configurada. La limitación de solicitudes está en memoria por proceso y no reemplaza un WAF o un limitador distribuido.

## Instalación / actualización

1. Descomprime el paquete y reemplaza los archivos del proyecto conservando las variables de Railway y el volumen `/data`.
2. El paquete incluye `main.py`, `static/index.html`, `static/style.css`, `static/app.js`, `requirements.txt`, `Procfile`, `railway.toml`, `.env.example` y `.gitignore`.
3. Sube los cambios a tu repositorio o método de despliegue. Este paquete no realiza un despliegue por sí solo.
4. Verifica `https://TU-SERVICIO/health`, abre la Mini App desde Telegram y prueba búsqueda, carrito, recibo y panel administrativo.

## Límites del modo demo

No se procesan pagos, no se envían órdenes a Amazon/Walmart/Target y no se crean guías de transporte reales. Saldos, pedidos y recibos son ficticios y están marcados como simulación. Los precios del proveedor pueden cambiar; confirma el precio final y la disponibilidad en la tienda oficial.

## Módulo HUBLOT (nuevo)

- Sección HUBLOT integrada en la página principal, con selección destacada y filtro por colección (Big Bang, Classic Fusion y Spirit of Big Bang).
- Cada ficha permite añadir el reloj al carrito interno en USD; los artículos usan las rutas existentes `/api/cart`, `/api/state` y `/api/purchase`.
- El checkout descuenta únicamente el saldo ficticio configurado y guarda el pedido/recibo en las tablas actuales. No hay pagos, reserva ni envío real.
- Las fichas de esta versión son una selección ilustrativa de ocho modelos/estilos y precios de referencia no oficiales, no un volcado completo ni una cotización de HUBLOT. El enlace «Catálogo oficial» abre el sitio oficial para comprobar modelos, precios y disponibilidad actuales.
- Se amplió la lista de plataformas aceptadas en el carrito para admitir enlaces HTTPS de `hublot.com`. No se añadieron ni eliminaron tablas ni se cambió `DATABASE_PATH`.


## Búsqueda independiente HUBLOT
La sección HUBLOT incorpora un campo y botón propios que filtran únicamente el catálogo HUBLOT integrado. No cambia el término de búsqueda ni los resultados de Amazon, Walmart o Target. La compra sigue siendo simulada y el descuento del 50% se aplica al catálogo HUBLOT.
