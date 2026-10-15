PROESHOP — conexión WalletConnect directa desde Telegram

Reemplaza estos archivos respetando las rutas:
- static/app.js
- static/index.html
- package.json
- nixpacks.toml
Y agrega en la raíz:
- walletconnect-entry.js

Este parche usa el proveedor WalletConnect empaquetado localmente (no ESM CDN), intenta abrir Trust Wallet con la solicitud wc: y conserva un botón de respaldo “Usar selector WalletConnect”.

No reemplaces main.py, requirements.txt ni modifiques /data/shopcart.db. Conserva las demás variables de Railway. El comando de inicio se fija en nixpacks.toml para usar el entorno virtual /opt/venv.

Nota: Android/Telegram/Trust Wallet pueden variar el manejo de enlaces universales. El URI se envía a Trust Wallet, pero la aprobación y retorno deben validarse en el teléfono tras desplegar. El saldo consultado sigue siendo solo lectura.
