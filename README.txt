# ProEshop — WalletConnect empaquetado localmente

Este parche sustituye la conexión de billetera que actualmente termina en un mensaje de error por WalletConnect Ethereum Provider compilado como archivo local. Así, el Mini App no intenta descargar el SDK desde esm.sh/jsDelivr en el navegador de Telegram.

## Archivos
- `static/index.html`
- `static/app.js`
- `walletconnect-entry.js`
- `package.json`
- `nixpacks.toml`

## Aplicación
Copia los archivos respetando estas rutas:
- `static/index.html` y `static/app.js` reemplazan los existentes.
- `walletconnect-entry.js`, `package.json` y `nixpacks.toml` van en la raíz junto a `main.py`.

No reemplaces `main.py`, `requirements.txt` ni la base de datos. Conserva el volumen `/data` y `DATABASE_PATH=/data/shopcart.db`.

Railway debe reconstruir la app desde el código para ejecutar `npm install` y `npm run build:wallet`. El resultado esperado es `static/walletconnect.bundle.js`, servido localmente. No subas el archivo `node_modules`.

## Prueba
1. Despliega y confirma en los logs que finalizó `npm run build:wallet`.
2. Abre ProEshop y pulsa Conectar Trust Wallet.
3. Autoriza la conexión en la ventana WalletConnect.
4. El saldo mostrado será USDT real de la red EVM seleccionada (Ethereum, BNB Smart Chain o Polygon). No modifica el saldo interno de la tienda ni firma pagos.

No puedo probar la aprobación real de Trust Wallet desde aquí. La compilación y la conexión deben verificarse en Railway/dispositivo después del despliegue.
