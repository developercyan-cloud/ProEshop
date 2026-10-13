# Imágenes verificadas por producto — ProEshop

- Se eliminaron las fotos de stock de Unsplash del catálogo local HUBLOT para que no se presenten como relojes originales.
- La extracción de imagen ahora analiza `src`, `data-src`, `data-original`, `data-zoom-image` y `srcset` de las fichas oficiales, prioriza recursos ligados al nombre/código del producto y descarta píxeles, logos y marcadores genéricos.
- Para HUBLOT, solo se intenta mostrar imagen en las fichas directas identificadas de All Red y All Black; los demás modelos del catálogo local no mostrarán una foto inventada hasta contar con una ficha e imagen específicas verificadas.
- Para Jewelers Toy Store se extraen fotos vinculadas al código de cada ficha (XRF-XL2, DXL, XL-2, XL-3). Si la web del proveedor bloquea el acceso o no expone una imagen identificable, se mantiene el marcador neutral en vez de asociar una foto equivocada.
- Los enlaces `Ver en tienda` usan las URL de producto guardadas en los resultados; para modelos HUBLOT sin ficha individual conocida, el enlace abre la colección oficial adecuada.

## Railway

No se debe borrar ni recrear el volumen ni la base de datos. Mantener `DATABASE_PATH=/data/shopcart.db`. El código de migración de la columna de imagen es aditivo.

## Alcance de la verificación

Se validaron la sintaxis de Python/JavaScript y la integridad del ZIP. No se desplegó en Railway ni se pudo validar la carga de cada imagen desde el entorno de producción. La extracción depende de que el proveedor permita consultar sus páginas.
