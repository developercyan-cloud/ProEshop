# ProEshop Telegram Mini App — versión premium

Versión de demostración para Railway con catálogo consultado mediante SerpApi/Google Shopping, búsqueda por Amazon/Walmart/Target, filtros de precio, ordenamiento, ficha de producto, favoritos de sesión, carrito, checkout demo y seguimiento de pedidos.

## Características
- Interfaz responsive premium con navegación inferior, animaciones suaves, tarjetas y categorías.
- Resultados reales del proveedor de búsqueda cuando `SERPAPI_KEY` está configurada. No se inventan valoraciones, descuentos, stock ni reseñas.
- Filtros por precio mínimo/máximo y orden por relevancia o precio.
- Normalización de enlaces para que el carrito reciba enlaces HTTPS de la tienda elegida; se usa la búsqueda oficial si el proveedor entrega un redirect externo.
- Checkout con datos de entrega **ficticios** y saldo demo. No solicita datos de tarjeta, no cobra y no envía pedidos a comercios.
- Referencia única por pedido, subtotal/impuestos/envío, evento de estado y notificación de confirmación por Telegram si el bot está configurado.
- Timeline de seguimiento marcado como simulado. No se crea una guía de transporte ni se finge un envío real.
- Migraciones SQLite aditivas para las columnas y tabla de eventos. No elimina ni recrea tablas existentes.

## Variables Railway
Conserva el volumen persistente y `DATABASE_PATH=/data/shopcart.db`. Configura al menos:
- `TELEGRAM_BOT_TOKEN`
- `PUBLIC_BASE_URL=https://TU-SERVICIO.up.railway.app`
- `WEBHOOK_SECRET` aleatorio y largo
- `DEMO_USERNAME` y `DEMO_PASSWORD` propios
- `SERPAPI_KEY`
- `DATABASE_PATH=/data/shopcart.db`

Los nombres de usuario y contraseña son únicamente para la cuenta demo de ProEshop, nunca para los comercios.

## Actualización
1. Descarga el ZIP y reemplaza los archivos del proyecto conservando tus variables de Railway y el volumen persistente.
2. El paquete incluye `main.py`, `static/index.html`, `static/style.css`, `static/app.js`, `requirements.txt`, `Procfile`, `railway.toml` y `.env.example`.
3. Haz commit/push a GitHub o sube los archivos al método de despliegue que uses en Railway.
4. Comprueba `/health`, inicia sesión desde Telegram y prueba búsqueda, carrito, checkout demo y pedidos.

**Importante:** esta es una simulación. El proveedor de búsqueda puede mostrar precios que cambian; verifica el precio final en la tienda oficial. Los estados posteriores a “Confirmado (simulado)” son pasos ilustrativos, no actualizaciones de transporte.
