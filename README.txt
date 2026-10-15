# ProEshop — corrección completa de compilación WalletConnect

El proyecto original no tenía `package.json`, por eso Railway no ejecutaba `npm` ni generaba `static/walletconnect.bundle.js`. Además, `railway.toml` seguía indicando `uvicorn ...`, lo que puede prevalecer sobre el comando de inicio de Nixpacks y explica `uvicorn: command not found`.

## Archivos incluidos
- `package.json` y `walletconnect-entry.js`: añaden el SDK y el comando para compilarlo localmente.
- `static/walletconnect.bundle.js` NO se incluye; se genera durante el build con `npm run build:wallet`.
- `static/index.html` y `static/app.js`: cargan el bundle local y usan la función de conexión WalletConnect.
- `nixpacks.toml`: instala Python/Node, crea `/opt/venv`, instala dependencias y compila WalletConnect.
- `railway.toml`: corrige el comando de inicio que antes invocaba `uvicorn` fuera del entorno virtual.

## Aplicación
Copia cada archivo de este ZIP a la raíz del repositorio respetando las rutas y reemplaza los archivos existentes con el mismo nombre. Los archivos de raíz van junto a `main.py` y `requirements.txt`; los dos archivos dentro de `static/` reemplazan los existentes.

Después haz un nuevo despliegue. En Build Logs deberías ver `npm install` y `npm run build:wallet`; el build debe generar `static/walletconnect.bundle.js`.

No reemplaces `main.py`, `requirements.txt`, ni borres o reinicialices el volumen `/data` y la base de datos `/data/shopcart.db`.

No se puede confirmar la conexión real a Trust Wallet hasta que Railway complete el build y se autorice la conexión desde el dispositivo.
