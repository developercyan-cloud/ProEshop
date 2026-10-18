# ProEshop — migración de Tenderly a MainNet Lab (Anvil fork)

Este parche conecta el checkout ERC-20 de prueba de ProEshop al RPC autoalojado MainNet Lab de Railway. Conserva Chain ID 1, el contrato USDT oficial (6 decimales), WalletConnect, pedidos, vencimiento de 5 minutos, correos y tablas existentes. No borra ni recrea la base de datos.

## Qué incluye

- `main.py`, `static/app.js`, `static/index.html`, `requirements.txt`: cambios del servicio ProEshop.
- `mainnet-lab-rpc/server.js`: cambio requerido en el servicio RPC autoalojado. Añade `/admin/transfer-usdt`, protegido por el mismo `ADMIN_TOKEN` que ya protege `/admin/fund-usdt`.

## Paso 1 — actualizar el servicio MainNet Lab

Reemplaza su `server.js` por `mainnet-lab-rpc/server.js` del parche y despliega ese servicio primero. Conserva el resto del proyecto, variables, volumen `/data`, snapshots y `ETHEREUM_RPC_URL`. Mantén `CHAIN_ID=1`.

La ruta nueva no se añade al RPC público `/rpc`: queda separada detrás de `requireAdmin` y del `ADMIN_TOKEN`. El método público sigue sin permitir `anvil_impersonateAccount` ni `eth_sendTransaction` sin firma.

## Paso 2 — configurar ProEshop en Railway

Agrega estas variables al servicio ProEshop:

- `MAINNET_FORK_RPC_URL=https://mainnetproetech-production.up.railway.app/rpc`
- `MAINNET_FORK_ADMIN_URL=https://mainnetproetech-production.up.railway.app/admin/transfer-usdt`
- `MAINNET_FORK_ADMIN_TOKEN`: el mismo valor secreto que `ADMIN_TOKEN` del servicio MainNet Lab. No lo pongas en GitHub, HTML, JavaScript ni mensajes.
- `MAINNET_FORK_USDT_RECEIVING_ADDRESS`: la dirección receptora configurada para pedidos ERC-20.

No cambies `TELEGRAM_BOT_TOKEN`, la DB, WalletConnect Project ID ni las variables de TRON. La aplicación conserva compatibilidad de lectura temporal con el nombre anterior `TENDERLY_USDT_RECEIVING_ADDRESS`, pero usa las nuevas variables del fork.

## Paso 3 — actualizar ProEshop

Reemplaza los cuatro archivos de la raíz/`static` indicados arriba en el repositorio ProEshop y despliega. No reemplaces el resto de `main.py` por un archivo de otro proyecto.

## Paso 4 — prueba segura

1. Comprueba `https://mainnetproetech-production.up.railway.app/health`: debe responder `ok: true` y `chainId: 1`.
2. En la wallet, selecciona el RPC de MainNet Lab con Chain ID 1 y comprueba que el bloque coincide con el que consulta ProEshop.
3. Usa una wallet de prueba que tenga USDT virtual en el fork y saldo nativo para gas (el endpoint puede asignar ETH virtual solo dentro del fork si hace falta).
4. Crea un pedido pequeño. La primera vez se firma un mensaje para vincular la wallet; no es una transacción. El backend llama a la ruta admin autenticada y el gateway verifica el recibo y el evento `Transfer` exacto.
5. ProEshop solo pasa el pedido a revisión tras verificar recibo, contrato, remitente, destinatario e importe. Si falla cualquier comprobación, no lo marca como pagado.

## Límite importante

MainNet Lab es un fork local de Ethereum Mainnet con Chain ID 1. Los saldos y transferencias de ese fork son datos de prueba persistidos por el servicio, no USDT reales y no se transfieren a Ethereum Mainnet. Para cobrar dinero real se requiere una transacción firmada por el cliente en Mainnet y verificación contra un RPC de Mainnet independiente; no uses el endpoint de impersonación para pagos reales.
