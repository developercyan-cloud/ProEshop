# Catálogo Rolex en ProEshop

- Catálogo integrado: 40 referencias con nombre, referencia, descripción y fotografía servida desde el CDN multimedia de Rolex (`media.rolex.com`).
- Los precios se muestran en USD y el precio promocional se calcula al 50% del precio de catálogo registrado.
- El 50% es una promoción interna/simulada de ProEshop; no representa una oferta de Rolex.
- Verifica en Rolex.com el precio vigente de cada configuración antes de publicar o vender, ya que precios y disponibilidad pueden variar por mercado.
- Fuente oficial de modelos/precios para comprobación: https://www.rolex.com/es/watches/new-watches/all-models y https://www.rolex.com/es/watches/find-rolex
- Amazon, Target y Walmart quedan deshabilitados en la interfaz y sus rutas de búsqueda y alta de nuevos artículos devuelven 403 temporalmente. Se conservan sus identificadores en el código para no romper el historial de pedidos anteriores.
- No borres ni cambies el volumen persistente de Railway. Conserva `DATABASE_PATH=/data/shopcart.db`.
