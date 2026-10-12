# ProEshop — Telegram Mini App para Railway

Aplicación de demostración para comparar resultados de Amazon, Walmart y Target mediante SerpApi/Google Shopping. Incluye autenticación con Telegram Mini App `initData`, búsqueda, carrito, pedidos simulados, preferencias de avisos y métricas administrativas.

## Funcionalidades

- Inicio responsive con navegación inferior, categorías y animaciones suaves.
- Búsqueda por tienda, filtros de precio, ordenamiento, ficha de producto y comparador de hasta tres productos.
- Carrito persistente en SQLite con cantidades editables y desglose de subtotal, impuestos estimados, envío y total.
- Historial de pedidos, línea de tiempo marcada como simulada y recibo imprimible sin valor fiscal.
- Notificaciones opcionales de Telegram para confirmaciones de pedidos demo e inicio de sesión; requieren configurar el bot.
- Panel administrativo visual protegido con `ADMIN_API_KEY`: filtros por estado, búsqueda por referencia/correo, cambio de estado, detalle del cambio, resultado del correo y reintento de notificación.
- API de pedidos: `GET /api/admin/orders`, `POST /api/admin/orders/{order_ref}/status` y `POST /api/admin/orders/{order_ref}/retry-email`. Las transiciones se validan en el servidor y se registran en el historial.
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
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` y `SMTP_USE_SSL` — necesarios para correos de pedido. Usa puerto 587 con STARTTLS (`SMTP_USE_SSL=false`) o 465 con SSL (`SMTP_USE_SSL=true`), según tu proveedor.

Genera secretos fuertes y no publiques `.env` ni tokens. El panel administrativo no estará disponible si `ADMIN_API_KEY` no está configurada. La limitación de solicitudes está en memoria por proceso y no reemplaza un WAF o un limitador distribuido.

## Instalación / actualización

1. Descomprime el paquete y reemplaza los archivos del proyecto conservando las variables de Railway y el volumen `/data`.
2. El paquete incluye `main.py`, `static/index.html`, `static/style.css`, `static/app.js`, `requirements.txt`, `Procfile`, `railway.toml`, `.env.example` y `.gitignore`.
3. Sube los cambios a tu repositorio o método de despliegue. Este paquete no realiza un despliegue por sí solo.
4. Verifica `https://TU-SERVICIO/health`, abre la Mini App desde Telegram y prueba búsqueda, carrito, recibo y panel administrativo.

## Límites del modo demo

No se procesan pagos, no se envían órdenes a Amazon/Walmart/Target y no se crean guías de transporte reales. Saldos, pedidos y recibos son ficticios y están marcados como simulación. Los precios del proveedor pueden cambiar; confirma el precio final y la disponibilidad en la tienda oficial.


GUI restoration: the original ProEshop layout and store search area are retained. HUBLOT appears in a separate collapsed panel so it does not push out or replace the existing interface. HUBLOT purchases remain simulated with 50% demo discount; preserve DATABASE_PATH=/data/shopcart.db and the Railway persistent volume.


HUBLOT fix: `/api/search` returns local illustrative catalogue entries for HUBLOT as well as the client-side catalogue. This supports cached/older Telegram webviews; static asset URLs include a version query to invalidate cache. A non-matching query falls back to the catalogue instead of displaying an empty result set.


## Catálogo Jewelers Toy Store
Se agregó una sección `Jewelers` para los 4 productos visibles en https://www.jewelerstoystore.com/Electronic-s/1074.htm. Se usan los precios publicados observados en esa página como base y se aplica un descuento ProEshop del 50% en resultados y en el servidor al agregar al carrito. El enlace abre la categoría fuente, no una página individual del producto; revalidar precios/disponibilidad y confirmar condiciones de reventa antes de recibir pagos reales.

## Catálogo Rolex (modelos destacados)

Se añadió una sección Rolex con seis modelos de referencia del catálogo oficial. La página de Rolex consultada no proporciona un ranking de ventas, por lo que se presentan como **modelos destacados**, no como una lista comprobada de los más vendidos. El descuento del 40% se aplica en Datejust 41, Explorer II y Sea-Dweller como una oferta propuesta por ProEshop; no es una promoción oficial de Rolex. Las imágenes son ilustrativas y los precios son referencias que deben volver a verificarse. Antes de aceptar pedidos reales, confirma autenticidad, procedencia, disponibilidad, precio y proveedor.


### Catálogo Rolex ampliado
Se incluyen 22 modelos/colecciones para navegación y búsqueda local. La página oficial de Rolex no publica un ranking de ventas en la vista consultada; no se etiquetan como best sellers. Algunas imágenes son ilustrativas de relojes y no fotografías oficiales verificadas de cada referencia. Precios de referencia deben confirmarse con vendedor autorizado y disponibilidad real antes de cualquier venta. El descuento del 40% es una oferta propuesta por ProEshop, no una promoción oficial de Rolex.


## Estados de pedidos y correos automáticos

Se añadió un flujo de estados y notificaciones de correo. Esta versión conserva el checkout sin pasarela: crear un pedido no representa un cobro ni una compra en Amazon/Walmart/Target ni un envío real. El correo confirma el registro y los cambios administrativos.

### Variables SMTP en Railway
- `SMTP_HOST` — servidor SMTP del proveedor de correo.
- `SMTP_PORT` — normalmente `587` para STARTTLS o `465` para SSL.
- `SMTP_USER` — usuario SMTP.
- `SMTP_PASSWORD` — contraseña o clave de aplicación SMTP.
- `SMTP_FROM_EMAIL` — remitente verificado.
- `SMTP_USE_SSL=false` para puerto 587/STARTTLS; `true` para SMTP SSL (habitualmente puerto 465).

El checkout solicita un correo de cliente. Si SMTP no está configurado o falla, el pedido queda registrado y la notificación se guarda como fallida para reintento.

### API administrativa de estados
Todas las rutas requieren el encabezado `X-Admin-Key: <ADMIN_API_KEY>` y deben llamarse desde un entorno administrativo seguro, no desde el navegador público.
- `GET /api/admin/orders` — lista los últimos pedidos. Acepta `?status=received` para filtrar.
- `POST /api/admin/orders/{order_ref}/status` con JSON `{"status":"reviewing","detail":"Disponibilidad solicitada al proveedor"}`.
- `POST /api/admin/orders/{order_ref}/retry-email` — reintenta la notificación del estado actual si falló.

Estados admitidos: `received`, `reviewing`, `action_required`, `confirmed`, `preparing`, `shipped`, `delivered`, `unavailable`, `cancelled`, `returned`. El backend bloquea transiciones no permitidas y registra cada cambio en `order_events` y `audit_log`. Solo deben seleccionarse estados de envío/entrega cuando existan confirmaciones reales.

### Persistencia y actualización
La migración añade `customer_email` y `order_notifications` de forma aditiva. Mantén el volumen persistente y `DATABASE_PATH=/data/shopcart.db`; no borres ni reinicialices la base de datos.


## Panel visual de gestión de pedidos

1. Despliega el proyecto manteniendo el volumen `/data` y `DATABASE_PATH=/data/shopcart.db`.
2. Configura `ADMIN_API_KEY` y las variables SMTP en Railway.
3. Entra a la miniapp, abre **Mi cuenta → Panel administrativo** e introduce la clave administrativa.
4. Filtra pedidos, selecciona un estado permitido, añade una nota y pulsa **Guardar estado y notificar**.
5. Si el correo falla, corrige la configuración SMTP y pulsa **Reintentar correo**.

El panel muestra estados guardados por el backend. El cambio de estado no confirma un pago ni una compra en una tienda externa. Esta versión sigue usando el flujo de pedido de demostración y no integra una pasarela de pago real. Prueba SMTP y las transiciones en Railway antes de utilizarlo con clientes.
