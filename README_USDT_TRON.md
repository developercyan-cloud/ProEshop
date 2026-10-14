# Pagos USDT por TRON (TRC-20) en ProEshop

## Funcionamiento
- El checkout ofrece saldo ficticio o USDT por TRON (TRC-20).
- Para USDT, crea el pedido en estado `received` y genera un importe exacto con seis decimales para poder distinguir pedidos que comparten la misma dirección.
- La interfaz muestra la dirección receptora, el importe exacto y consulta el estado del pago.
- El backend consulta transferencias TRC-20 USDT confirmadas a la dirección configurada. Si coincide el destinatario, el contrato, el importe exacto y la fecha del pedido, registra el TXID y cambia el pedido principal y los pedidos por tienda a `payment_review` (En revisión de pago).
- `payment_review` no equivale a aprobación final; el administrador debe revisar el pago y continuar el flujo de estados.

## Configuración Railway
Variables opcionales/recomendadas:
- `TRON_USDT_ADDRESS=TXVaW6HaAYaHxpEh9zU6pHTMASPYr3R6QC` (dirección configurada por defecto en esta versión).
- `TRONGRID_API_KEY`: clave de TronGrid recomendada para estabilidad y límites de consulta más altos.
- `TRON_POLL_SECONDS=45`: frecuencia mínima de sondeo del backend (mínimo aceptado: 20 segundos).
- `TRON_API_BASE=https://api.trongrid.io`: cambiar solo si se utiliza un endpoint compatible.

El token de USDT usado es el contrato de TRON mainnet `TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj`. La consulta usa transferencias confirmadas (`only_confirmed=true`).

## Antes de producción
1. Haz copia de seguridad del volumen persistente y conserva `DATABASE_PATH=/data/shopcart.db`. La tabla `crypto_payments` se crea mediante migración aditiva.
2. Despliega el ZIP y verifica `/health`.
3. Prueba primero con una cantidad pequeña en mainnet; confirma que la wallet controla la dirección receptora.
4. Añade `TRONGRID_API_KEY` en Railway. La consulta pública sin clave puede tener límites.
5. El importe debe enviarse exactamente como aparece en el checkout. Enviar una cantidad diferente, otro token o una red distinta no se emparejará automáticamente.
6. El detector no mueve fondos ni necesita la clave privada de la wallet. No agregues una clave privada a Railway ni al código.
7. Mantén acceso administrativo seguro; la detección cambia el pedido a revisión, no a confirmado.

## Consideraciones operativas
El sondeo en segundo plano se ejecuta por instancia de la aplicación; si Railway escala a varias réplicas, se recomienda fijar una sola réplica o migrar el monitor a un worker único para evitar consultas duplicadas. Las consultas se hacen a TronGrid y pueden retrasarse por límites de API o disponibilidad del proveedor.
