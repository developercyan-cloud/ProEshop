ProEshop — parche enfocado a WalletConnect Android

Incluye únicamente:
- package.json: actualiza @walletconnect/ethereum-provider de 2.21.1 a 2.26.0.
- static/app.js: actualiza la configuración WalletConnect, limita los métodos solicitados a consulta/cuentas y mejora el mensaje de timeout.
- static/index.html: cambia el identificador de caché de app.js y walletconnect.bundle.js.
- walletconnect-entry.js: entrada existente para compilar el bundle.

NO incluye ni modifica main.py, requisitos Python, ni la base de datos SQLite.

Aplicación:
1. En el repositorio de Railway, reemplaza package.json, walletconnect-entry.js y static/app.js y static/index.html por los de este ZIP.
2. Haz commit y espera que Railway complete npm install y `npm run build:wallet`.
3. Prueba una sola vez. El Project ID se conserva: 8964c13e0d85a4ac687ce9ebd7474d87.

Nota técnica: este parche corrige configuración obsoleta/ambigua y actualiza el SDK, pero no se puede garantizar que solucione un bloqueo de WebSocket/relay sin el error de consola del navegador. No modifica la tienda ni el backend.
