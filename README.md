# ProEshop v3 — Premium Store Aggregator

Mini App para Telegram con diseño dark premium azul noche/violeta. Agrega resultados de Amazon, Walmart y Target en una misma búsqueda mediante SerpApi/Google Shopping, y permite filtrar por precio, ordenar, comparar hasta tres productos y abrir el enlace externo del vendedor.

## Railway: actualización segura

- Conserva el volumen persistente que ya tienes montado en `/data`.
- Conserva la ruta de base de datos `DATABASE_PATH=/data/shopcart.db` (también es el valor por defecto).
- El backend mantiene las rutas existentes: `/`, `/health`, `/api/login`, `/api/logout`, `/api/search`, `/api/state`, `/api/cart`, `/api/notifications`, `/api/orders/{order_ref}/receipt`, `/api/admin/metrics` y `/api/purchase`.
- Las migraciones son aditivas y no borran tablas ni datos existentes.
- Este ZIP no despliega automáticamente la aplicación.

## Variables de entorno

Configura en Railway: `DATABASE_PATH=/data/shopcart.db`, `TELEGRAM_BOT_TOKEN`, `PUBLIC_BASE_URL`, `WEBHOOK_SECRET`, `DEMO_USERNAME`, `DEMO_PASSWORD`, `ADMIN_API_KEY` y `SERPAPI_KEY`. Sin `SERPAPI_KEY`, el sitio indica que la búsqueda live no está configurada; no inventa resultados.

Las credenciales demo son solo para el acceso a ProEshop. Nunca uses credenciales de Amazon, Walmart o Target. Usa secretos propios y no subas `.env`.

## Búsqueda agregada

La opción **Todas** consulta en paralelo las rutas existentes para Amazon, Walmart y Target. Los resultados se agrupan, se ordenan por precio y conservan la tienda de origen para abrir el comercio correcto. Cada proveedor puede responder con cero resultados o errores sin invalidar las respuestas de los demás.

Los precios, vendedores y disponibilidad son orientativos y deben verificarse en la página de destino. ProEshop es un comparador/agregador; no realiza compras en las tiendas externas.

## Pagos y pedidos

El carrito y el flujo de pedido siguen siendo de demostración. No se conectan pasarelas, no se captura información de tarjetas, no se transmiten órdenes a comercios y no se generan envíos reales. Los importes de impuestos/envío y el saldo son ficticios.

## Despliegue

El arranque se define en `Procfile` y `railway.toml`. Tras subir el ZIP a tu repositorio/proceso de despliegue, verifica `/health`, abre la Mini App en Telegram y prueba búsqueda agregada, filtrado, comparador y carrito. No se ha realizado un despliegue desde este paquete.
