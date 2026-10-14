# ProEshop — corrección HUBLOT v4

- Se asignan URLs directas de imágenes oficiales HUBLOT verificadas para siete modelos Big Bang Original: All Red, All Black, Titanium, Titanium Ceramic, King Gold Ceramic, Black Magic y Titanium Coal Blue.
- Los productos de esos siete modelos muestran la misma imagen oficial en resultados, detalle, carrito y checkout, al guardarse la URL en `carts.image`.
- Las demás referencias del catálogo no reciben fotos de otro modelo. Si no hay una imagen individual verificada, siguen sin foto para evitar asociaciones incorrectas.
- La extracción automática de imágenes de Jewelers Toy Store no queda resuelta por este parche; sus fichas deben revisarse por separado porque el scraper anterior seguía devolviendo vacío.

## Despliegue
Conservar el volumen de Railway y `DATABASE_PATH=/data/shopcart.db`. No borrar ni recrear la base de datos.

## Pruebas
Validación de sintaxis Python/JavaScript y estructura ZIP; no se ha desplegado en Railway ni se ha probado la carga desde el WebView de producción.
