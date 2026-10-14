import os, hmac, hashlib, json, time, secrets, sqlite3, logging, re, smtplib, asyncio
from urllib.parse import parse_qsl, quote_plus, urlparse, urljoin
from html import unescape
from datetime import datetime, timezone, timedelta
from html import escape
from email.message import EmailMessage
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("shopcart")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
TELEGRAM_MINI_APP_URL = os.getenv("TELEGRAM_MINI_APP_URL", "https://t.me/ProeshopBot").rstrip("/")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/shopcart.db")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()
DEMO_USERNAME = os.getenv("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "change-me")
INITIAL_BALANCE = Decimal(os.getenv("INITIAL_FAKE_BALANCE", "1000.00"))
CURRENCY = os.getenv("CURRENCY", "USD")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", secrets.token_urlsafe(24))
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
ESTIMATED_TAX_RATE = Decimal(os.getenv("ESTIMATED_TAX_RATE", "0.08"))
ESTIMATED_SHIPPING_FEE = Decimal(os.getenv("ESTIMATED_SHIPPING_FEE", "5.99"))
SESSION_TTL = int(os.getenv("SESSION_TTL_MINUTES", "120")) * 60
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER).strip()
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
# USDT TRC-20 mainnet configuration. Keep the receiving address in server config.
TRON_USDT_ADDRESS = os.getenv("TRON_USDT_ADDRESS", "TXVaW6HaAYaHxpEh9zU6pHTMASPYr3R6QC").strip()
TRON_USDT_CONTRACT = "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj"
TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY", "").strip()
TRON_API_BASE = os.getenv("TRON_API_BASE", "https://api.trongrid.io").rstrip("/")
TRON_POLL_SECONDS = max(20, int(os.getenv("TRON_POLL_SECONDS", "45")))
_tron_monitor_task = None


app = FastAPI(title="ProEshop Telegram Mini App", docs_url=None, redoc_url=None)

# Lightweight per-process throttling for public-facing credential/search endpoints.
_RATE_BUCKETS = {}
_SEARCH_CACHE = {}

@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    path = request.url.path
    if path in ("/api/login", "/api/register", "/api/verify-email-code", "/api/email-login", "/api/telegram-login", "/api/search"):
        ip = request.client.host if request.client else "unknown"
        key = (ip, path)
        now = time.time()
        window, limit = (60, 12 if path in ("/api/login", "/api/verify-email-code") else 30)
        hits = [t for t in _RATE_BUCKETS.get(key, []) if now - t < window]
        if len(hits) >= limit:
            return JSONResponse({"detail": "Demasiadas solicitudes. Espera un minuto e inténtalo otra vez."}, status_code=429)
        hits.append(now); _RATE_BUCKETS[key] = hits
        if len(_RATE_BUCKETS) > 5000:
            for old_key in list(_RATE_BUCKETS)[:1000]: _RATE_BUCKETS.pop(old_key, None)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' https: data: blob:; connect-src 'self' https://api.telegram.org; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if path == "/" or path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response
app.mount("/static", StaticFiles(directory="static"), name="static")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=20000")
    db.execute("PRAGMA busy_timeout=20000")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def init_db():
    with conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          telegram_id TEXT PRIMARY KEY, username TEXT, demo_login TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY, telegram_id TEXT NOT NULL, created_at REAL NOT NULL, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS email_accounts(
          account_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
          verified INTEGER NOT NULL DEFAULT 0, verify_hash TEXT NOT NULL DEFAULT '', verify_expires REAL NOT NULL DEFAULT 0,
          telegram_id TEXT UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pending_email_registrations(
          email TEXT PRIMARY KEY COLLATE NOCASE, password_hash TEXT NOT NULL,
          verify_hash TEXT NOT NULL, verify_expires REAL NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS telegram_verification_handoffs(
          code_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL, expires_at REAL NOT NULL,
          used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS carts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id TEXT NOT NULL, platform TEXT NOT NULL,
          title TEXT NOT NULL, price TEXT NOT NULL, currency TEXT NOT NULL, url TEXT NOT NULL,
          image TEXT NOT NULL DEFAULT '', qty INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS purchases(
          id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id TEXT NOT NULL, platform TEXT NOT NULL,
          title TEXT NOT NULL, price TEXT NOT NULL, currency TEXT NOT NULL, qty INTEGER NOT NULL,
          total TEXT NOT NULL, url TEXT NOT NULL, purchased_at TEXT NOT NULL,
          order_ref TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS orders(
          order_ref TEXT PRIMARY KEY, telegram_id TEXT NOT NULL, subtotal TEXT NOT NULL,
          tax TEXT NOT NULL, shipping TEXT NOT NULL, total TEXT NOT NULL, currency TEXT NOT NULL,
          status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          shipping_name TEXT NOT NULL DEFAULT '', shipping_city TEXT NOT NULL DEFAULT '',
          shipping_country TEXT NOT NULL DEFAULT '', shipping_address TEXT NOT NULL DEFAULT '',
          payment_method TEXT NOT NULL DEFAULT 'demo_balance',
          customer_email TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS crypto_payments(
          order_ref TEXT PRIMARY KEY, network TEXT NOT NULL, token_symbol TEXT NOT NULL,
          token_contract TEXT NOT NULL, receiving_address TEXT NOT NULL, requested_amount TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', txid TEXT NOT NULL DEFAULT '', paid_amount TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_checked_at TEXT NOT NULL DEFAULT '',
          FOREIGN KEY(order_ref) REFERENCES orders(order_ref) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_crypto_payments_status ON crypto_payments(status, created_at);
        CREATE TABLE IF NOT EXISTS store_orders(
          store_order_ref TEXT PRIMARY KEY, order_ref TEXT NOT NULL, platform TEXT NOT NULL,
          store_label TEXT NOT NULL, subtotal TEXT NOT NULL, tax TEXT NOT NULL,
          shipping TEXT NOT NULL, total TEXT NOT NULL, currency TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'received', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          customer_email TEXT NOT NULL DEFAULT '',
          FOREIGN KEY(order_ref) REFERENCES orders(order_ref) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_store_orders_parent ON store_orders(order_ref, platform);
        CREATE TABLE IF NOT EXISTS store_order_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, store_order_ref TEXT NOT NULL,
          status TEXT NOT NULL, label TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          FOREIGN KEY(store_order_ref) REFERENCES store_orders(store_order_ref) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_store_order_events_ref ON store_order_events(store_order_ref, created_at, id);
        CREATE TABLE IF NOT EXISTS store_order_notifications(
          id INTEGER PRIMARY KEY AUTOINCREMENT, store_order_ref TEXT NOT NULL,
          event_key TEXT NOT NULL, recipient TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(store_order_ref,event_key),
          FOREIGN KEY(store_order_ref) REFERENCES store_orders(store_order_ref) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS order_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, order_ref TEXT NOT NULL,
          status TEXT NOT NULL, label TEXT NOT NULL, detail TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(order_ref) REFERENCES orders(order_ref) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS order_notifications(
          id INTEGER PRIMARY KEY AUTOINCREMENT, order_ref TEXT NOT NULL,
          event_key TEXT NOT NULL, recipient TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(order_ref,event_key),
          FOREIGN KEY(order_ref) REFERENCES orders(order_ref) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS balances(
          telegram_id TEXT PRIMARY KEY, amount TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notification_preferences(
          telegram_id TEXT PRIMARY KEY, order_updates INTEGER NOT NULL DEFAULT 1,
          security_alerts INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT NOT NULL DEFAULT '',
          action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_carts_user ON carts(telegram_id, id);
        CREATE INDEX IF NOT EXISTS idx_orders_user_date ON orders(telegram_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_purchases_user_date ON purchases(telegram_id, purchased_at);
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
        """)
        # Additive migration: CREATE TABLE IF NOT EXISTS does not add columns to
        # an existing pending_email_registrations table from older deployments.
        pending_columns = {row["name"] for row in db.execute("PRAGMA table_info(pending_email_registrations)").fetchall()}
        pending_migrations = {
            "email": "TEXT",
            "password_hash": "TEXT NOT NULL DEFAULT ''",
            "verify_hash": "TEXT NOT NULL DEFAULT ''",
            "verify_expires": "REAL NOT NULL DEFAULT 0",
            "attempts": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, column_definition in pending_migrations.items():
            if column_name not in pending_columns:
                db.execute(f'ALTER TABLE pending_email_registrations ADD COLUMN "{column_name}" {column_definition}')
        db.execute("PRAGMA journal_mode=WAL")
        # Safe migration for databases created by earlier ShopCart versions.
        purchase_columns = {row["name"] for row in db.execute("PRAGMA table_info(purchases)").fetchall()}
        if "order_ref" not in purchase_columns:
            db.execute("ALTER TABLE purchases ADD COLUMN order_ref TEXT NOT NULL DEFAULT ''")
        if "store_order_ref" not in purchase_columns:
            db.execute("ALTER TABLE purchases ADD COLUMN store_order_ref TEXT NOT NULL DEFAULT ''")
        cart_columns = {row["name"] for row in db.execute("PRAGMA table_info(carts)").fetchall()}
        if "image" not in cart_columns:
            db.execute("ALTER TABLE carts ADD COLUMN image TEXT NOT NULL DEFAULT ''")
        # Additive migrations only: preserve the existing Railway volume and all data.
        order_columns = {row["name"] for row in db.execute("PRAGMA table_info(orders)").fetchall()}
        for column, declaration in {
            "shipping_name": "TEXT NOT NULL DEFAULT ''",
            "shipping_city": "TEXT NOT NULL DEFAULT ''",
            "shipping_country": "TEXT NOT NULL DEFAULT ''",
            "shipping_address": "TEXT NOT NULL DEFAULT ''",
            "payment_method": "TEXT NOT NULL DEFAULT 'demo_balance'",
            "customer_email": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in order_columns:
                db.execute(f"ALTER TABLE orders ADD COLUMN {column} {declaration}")


def audit(actor_id: str, action: str, detail: str = ""):
    """Store a minimal audit event; do not record passwords, tokens, or full addresses."""
    with conn() as db:
        db.execute("INSERT INTO audit_log(actor_id,action,detail,created_at) VALUES(?,?,?,?)",
                   (str(actor_id or "")[:80], str(action)[:80], str(detail)[:240], now_iso()))


def audit(actor_id: str, action: str, detail: str = ""):
    """Store a minimal audit event; do not record passwords, tokens, or full addresses."""
    with conn() as db:
        db.execute("INSERT INTO audit_log(actor_id,action,detail,created_at) VALUES(?,?,?,?)",
                   (str(actor_id or "")[:80], str(action)[:80], str(detail)[:240], now_iso()))


ORDER_STATUS_LABELS = {
    "confirmed_simulated": "Confirmado (simulado, legado)",
    "pending_payment": "Pendiente de pago",
    "received": "Pedido recibido",
    "reviewing": "En revisión",
    "payment_review": "En revisión de pago",
    "action_required": "Requiere acción del cliente",
    "confirmed": "Confirmado",
    "in_process": "En proceso",
    "preparing": "En proceso",
    "shipped": "Enviado",
    "delivered": "Entregado",
    "unavailable": "Producto no disponible",
    "cancelled": "Cancelado",
    "returned": "Devuelto",
}
ORDER_TRANSITIONS = {
    "confirmed_simulated": {"reviewing", "cancelled", "unavailable"},
    "pending_payment": {"payment_review", "cancelled"},
    "received": {"reviewing", "payment_review", "action_required", "cancelled", "unavailable"},
    "payment_review": {"reviewing", "confirmed", "action_required", "cancelled", "unavailable"},
    "reviewing": {"confirmed", "action_required", "cancelled", "unavailable"},
    "action_required": {"reviewing", "cancelled"},
    "confirmed": {"in_process", "preparing", "cancelled"},
    "in_process": {"shipped", "cancelled"},
    "preparing": {"shipped", "cancelled"},
    "shipped": {"delivered", "returned"},
    "delivered": {"returned"},
    "unavailable": {"cancelled"},
    "cancelled": set(),
    "returned": set(),
}
ORDER_EMAIL_COPY = {
    "pending_payment": ("Tu pedido está pendiente de pago", "Tu pedido se creó y estará reservado durante cinco minutos mientras completas el pago USDT por TRON (TRC-20). Si no se detecta el pago en ese plazo, se cancelará automáticamente."),
    "received": ("Recibimos tu pedido", "Tu pedido fue registrado en ProEshop. Esto confirma el registro, no un pago ni una compra con un proveedor."),
    "reviewing": ("Estamos revisando tu pedido", "Estamos verificando los detalles y la disponibilidad del pedido."),
    "payment_review": ("Pago detectado: en revisión", "Detectamos la transferencia USDT en TRON. El equipo está revisando el pago antes de confirmar el pedido."),
    "action_required": ("Necesitamos información para tu pedido", "Tu pedido requiere una acción adicional. Revisa los detalles con el equipo de ProEshop."),
    "confirmed": ("Tu pedido ha sido confirmado", "El pedido fue confirmado por el equipo de ProEshop. El estado del pago se informa por separado."),
    "in_process": ("Tu pedido está en proceso", "Tu pedido ha pasado a la etapa de proceso."),
    "preparing": ("Tu pedido está en proceso", "Tu pedido ha pasado a la etapa de proceso."),
    "shipped": ("Tu pedido fue enviado", "Tu pedido figura como enviado. Consulta el número de guía en los detalles del pedido si se ha registrado."),
    "delivered": ("Tu pedido figura como entregado", "Se registró la entrega del pedido."),
    "unavailable": ("Actualización sobre disponibilidad", "El producto no está disponible actualmente. El equipo de ProEshop te informará sobre las opciones."),
    "cancelled": ("Pedido cancelado por falta de pago", "Tu pedido con pago USDT fue cancelado automáticamente porque no se detectó el pago confirmado dentro del plazo de cinco minutos. La cotización expiró y ya no debes enviar fondos usando esos datos. Si deseas comprar, crea un nuevo pedido."),
    "returned": ("Actualización de devolución", "El pedido fue marcado como devuelto. El estado de cualquier reembolso se gestiona por separado."),
}

def _email_store_theme(detail: str = ""):
    """Choose a neutral ProEshop accent by store; never impersonate the retailer."""
    match = re.search(r"(?:^|[.\n])\s*Tienda:\s*([^.;\n]+)", detail or "", re.IGNORECASE)
    store = (match.group(1).strip() if match else "ProEshop")[:80]
    normalized = store.lower()
    themes = {
        "amazon": ("#232f3e", "#ffb84d"),
        "walmart": ("#073b75", "#ffc220"),
        "target": ("#9f1239", "#f87171"),
        "hublot": ("#111827", "#c7a76c"),
        "jewelers": ("#173b35", "#c9a96e"),
    }
    accent, highlight = ("#24205b", "#8b7cff")
    for key, colors in themes.items():
        if key in normalized:
            accent, highlight = colors
            break
    return store, accent, highlight


def send_status_email(recipient: str, order_ref: str, status: str, total: str, currency: str, detail: str = ""):
    """Send branded responsive HTML email through Brevo API or legacy SMTP."""
    if not all([SMTP_FROM_EMAIL, recipient]):
        raise RuntimeError("Falta SMTP_FROM_EMAIL/remitente o el pedido no tiene correo del cliente")

    subject, message = ORDER_EMAIL_COPY.get(status, ("Actualización de tu pedido", "El estado de tu pedido ha cambiado."))
    status_label = ORDER_STATUS_LABELS.get(status, status)
    store, accent, highlight = _email_store_theme(detail)
    total_formatted = f"{escape(str(currency))} {Decimal(total):,.2f}"
    detail_text = str(detail or "").strip()
    detail_html = (f'<div style="margin-top:20px;padding:14px 16px;border-left:3px solid {highlight};background:#fbfbfe;color:#4b5568;font-size:13px;line-height:1.65;"><strong style="color:#172033;">Detalle</strong><br>{escape(detail_text)}</div>' if detail_text else "")
    # The email clearly comes from ProEshop; store-specific colors are only an accent.
    html_content = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f5fa;font-family:Arial,Helvetica,sans-serif;color:#172033;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f5fa;padding:28px 10px;"><tr><td align="center">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:18px;overflow:hidden;box-shadow:0 8px 28px rgba(20,28,55,.10);">
<tr><td style="background:{accent};padding:26px 30px;border-bottom:4px solid {highlight};">
<div style="font-size:12px;letter-spacing:3px;font-weight:700;color:#ffffff;opacity:.85;">PROESHOP</div>
<div style="font-size:26px;line-height:1.25;font-weight:700;color:#ffffff;margin-top:9px;">{escape(subject)}</div>
<div style="font-size:13px;color:#ffffff;margin-top:8px;opacity:.9;">Actualización de tu pedido · {escape(store)}</div>
</td></tr>
<tr><td style="padding:30px;">
<p style="font-size:16px;line-height:1.65;margin:0 0 12px;">Hola,</p>
<p style="font-size:15px;line-height:1.7;color:#4b5568;margin:0 0 24px;">{escape(message)}</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f8f9fc;border:1px solid #e5e9f2;border-radius:12px;">
<tr><td style="padding:17px 18px;border-bottom:1px solid #e5e9f2;"><div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#667085;">Tienda</div><div style="font-size:16px;font-weight:700;margin-top:5px;color:#172033;">{escape(store)}</div></td></tr>
<tr><td style="padding:17px 18px;border-bottom:1px solid #e5e9f2;"><div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#667085;">Referencia del pedido</div><div style="font-size:16px;font-weight:700;margin-top:5px;color:#172033;">{escape(order_ref)}</div></td></tr>
<tr><td style="padding:17px 18px;border-bottom:1px solid #e5e9f2;"><div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#667085;">Estado actual</div><span style="display:inline-block;margin-top:8px;padding:8px 12px;border-radius:999px;background:{highlight};color:#171717;font-size:13px;font-weight:700;">{escape(status_label)}</span></td></tr>
<tr><td style="padding:17px 18px;"><div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#667085;">Total registrado de esta tienda</div><div style="font-size:24px;font-weight:700;margin-top:5px;color:{accent};">{total_formatted}</div></td></tr>
</table>
{detail_html}
<div style="margin-top:22px;padding:14px 16px;background:#fff8e8;border:1px solid #f3dfad;border-radius:10px;color:#73551a;font-size:12px;line-height:1.65;">Esta notificación informa el estado registrado en ProEshop. Por sí sola no confirma que se haya recibido un pago ni que la compra se haya completado en la tienda proveedora.</div>
<p style="font-size:14px;line-height:1.6;margin:24px 0 0;color:#4b5568;">Gracias por usar <strong style="color:#172033;">ProEshop</strong>.</p>
</td></tr>
<tr><td style="background:#f8f9fc;border-top:1px solid #e8ebf2;padding:18px 30px;color:#8a93a5;font-size:11px;line-height:1.6;">Mensaje automático de ProEshop. No respondas a este correo si el remitente no admite respuestas.</td></tr>
</table></td></tr></table></body></html>"""
    text_content = (
        f"Hola,\n\n{message}\n\nTienda: {store}\nPedido: {order_ref}\n"
        f"Estado: {status_label}\nTotal registrado de esta tienda: {currency} {Decimal(total):.2f}"
        f"{chr(10) + 'Detalle: ' + detail_text if detail_text else ''}\n\n"
        "El estado del pedido no implica por sí mismo que el pago haya sido recibido.\nProEshop"
    )

    if BREVO_API_KEY:
        payload = {
            "sender": {"email": SMTP_FROM_EMAIL, "name": "ProEshop"},
            "to": [{"email": recipient}],
            "subject": f"ProEshop · {store} · {subject} · {order_ref}",
            "textContent": text_content,
            "htmlContent": html_content,
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
                response = client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={"api-key": BREVO_API_KEY, "accept": "application/json", "content-type": "application/json"},
                    json=payload,
                )
            if response.status_code not in (200, 201, 202):
                raise RuntimeError(f"Brevo API HTTP {response.status_code}: {response.text[:240]}")
            return
        except httpx.TimeoutException as exc:
            raise RuntimeError("Tiempo de espera agotado al conectar con la API HTTPS de Brevo") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Error de conexión con la API HTTPS de Brevo: {type(exc).__name__}") from exc

    if not SMTP_HOST:
        raise RuntimeError("Configura BREVO_API_KEY en Railway para enviar por la API HTTPS de Brevo")
    msg = EmailMessage()
    msg["Subject"] = f"ProEshop · {store} · {subject} · {order_ref}"
    msg["From"] = f"ProEshop <{SMTP_FROM_EMAIL}>"
    msg["To"] = recipient
    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")
    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            if SMTP_USER: server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            if SMTP_USER: server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

def enqueue_and_send_order_email(order_ref: str, status: str, recipient: str, total: str, currency: str, detail: str = ""):
    if not recipient:
        return {"sent": False, "reason": "El cliente no proporcionó correo electrónico."}
    now = now_iso()
    with conn() as db:
        db.execute("INSERT OR IGNORE INTO order_notifications(order_ref,event_key,recipient,status,created_at,updated_at) VALUES(?,?,?,'pending',?,?)", (order_ref, status, recipient, now, now))
        row = db.execute("SELECT * FROM order_notifications WHERE order_ref=? AND event_key=?", (order_ref, status)).fetchone()
        if row and row["status"] == "sent": return {"sent": True, "duplicate": True}
        db.execute("UPDATE order_notifications SET attempts=attempts+1,updated_at=? WHERE order_ref=? AND event_key=?", (now, order_ref, status))
    try:
        send_status_email(recipient, order_ref, status, total, currency, detail)
        with conn() as db:
            db.execute("UPDATE order_notifications SET status='sent',last_error='',updated_at=? WHERE order_ref=? AND event_key=?", (now_iso(), order_ref, status))
        return {"sent": True}
    except Exception as exc:
        err = str(exc)[:300]
        with conn() as db:
            db.execute("UPDATE order_notifications SET status='failed',last_error=?,updated_at=? WHERE order_ref=? AND event_key=?", (err, now_iso(), order_ref, status))
        log.warning("Email de pedido falló order=%s event=%s: %s", order_ref, status, err)
        return {"sent": False, "reason": "No se pudo enviar el correo; quedó registrado para reintento."}

def enqueue_and_send_store_order_email(store_order_ref: str, status: str, recipient: str, total: str, currency: str, detail: str = ""):
    """Idempotent email queue for a per-store order; kept separate from legacy order notifications."""
    if not recipient:
        return {"sent": False, "reason": "El cliente no proporcionó correo electrónico."}
    now = now_iso()
    with conn() as db:
        db.execute("INSERT OR IGNORE INTO store_order_notifications(store_order_ref,event_key,recipient,status,created_at,updated_at) VALUES(?,?,?,'pending',?,?)", (store_order_ref, status, recipient, now, now))
        row = db.execute("SELECT * FROM store_order_notifications WHERE store_order_ref=? AND event_key=?", (store_order_ref, status)).fetchone()
        if row and row["status"] == "sent": return {"sent": True, "duplicate": True}
        db.execute("UPDATE store_order_notifications SET attempts=attempts+1,updated_at=? WHERE store_order_ref=? AND event_key=?", (now, store_order_ref, status))
    try:
        send_status_email(recipient, store_order_ref, status, total, currency, detail)
        with conn() as db:
            db.execute("UPDATE store_order_notifications SET status='sent',last_error='',updated_at=? WHERE store_order_ref=? AND event_key=?", (now_iso(), store_order_ref, status))
        return {"sent": True}
    except Exception as exc:
        err = str(exc)[:300]
        with conn() as db:
            db.execute("UPDATE store_order_notifications SET status='failed',last_error=?,updated_at=? WHERE store_order_ref=? AND event_key=?", (err, now_iso(), store_order_ref, status))
        log.warning("Email de tienda falló order=%s event=%s: %s", store_order_ref, status, err)
        return {"sent": False, "reason": "No se pudo enviar el correo; quedó registrado para reintento."}


def validate_init_data(init_data: str):
    """Validate Telegram Mini App initData using Telegram's documented HMAC scheme."""
    if not BOT_TOKEN:
        raise HTTPException(503, "El bot no está configurado.")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash")
    except Exception:
        raise HTTPException(401, "Falta initData válido de Telegram.")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(401, "Firma de Telegram no válida.")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        if time.time() - auth_date > 86400 or auth_date > time.time() + 300:
            raise HTTPException(401, "La autorización de Telegram expiró. Vuelve a abrir la miniapp.")
        user = json.loads(pairs["user"])
        tg_id = str(user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "No se pudo validar el usuario de Telegram.")
    return tg_id, user


def get_auth(request: Request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Inicia sesión primero.")
    with conn() as db:
        row = db.execute("SELECT * FROM sessions WHERE token=? AND active=1", (token,)).fetchone()
        if not row or time.time() - row["created_at"] > SESSION_TTL:
            if row:
                db.execute("UPDATE sessions SET active=0 WHERE token=?", (token,))
            raise HTTPException(401, "Sesión expirada. Inicia sesión nuevamente.")
        db.execute("UPDATE sessions SET created_at=? WHERE token=?", (time.time(), token))
    return row["telegram_id"]


class AuthBody(BaseModel):
    init_data: str = ""
    username: str = Field(default="", max_length=80)
    password: str = Field(min_length=1, max_length=200)

class RegisterBody(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=200)

class EmailLoginBody(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=200)

class TelegramBody(BaseModel):
    init_data: str = Field(min_length=1, max_length=10000)


class SearchBody(BaseModel):
    platform: str
    query: str = Field(min_length=1, max_length=180)


class AddBody(BaseModel):
    platform: str
    title: str = Field(min_length=1, max_length=180)
    price: str
    currency: str = Field(default="USD", min_length=3, max_length=3)
    url: str = Field(min_length=8, max_length=1000)
    image: str = Field(default="", max_length=2000)


class QtyBody(BaseModel):
    qty: int = Field(ge=1, le=25)


class NotificationBody(BaseModel):
    order_updates: bool = True
    security_alerts: bool = True


class QtyBody(BaseModel):
    qty: int = Field(ge=1, le=25)


class NotificationBody(BaseModel):
    order_updates: bool = True
    security_alerts: bool = True


class CheckoutBody(BaseModel):
    # These are explicitly demo-only details; never collect card or bank credentials.
    shipping_name: str = Field(default="", max_length=100)
    shipping_city: str = Field(default="", max_length=80)
    shipping_country: str = Field(default="", max_length=80)
    shipping_address: str = Field(default="", max_length=180)
    customer_email: str = Field(default="", max_length=254)
    # Backward compatibility: older frontend versions sent the address as "email".
    email: str = Field(default="", max_length=254)
    payment_method: str = Field(default="demo_balance", max_length=32)


PLATFORMS = {
    "amazon": {"label": "Amazon", "url": "https://www.amazon.com/s?k={q}"},
    "target": {"label": "Target", "url": "https://www.target.com/s?searchTerm={q}"},
    "walmart": {"label": "Walmart", "url": "https://www.walmart.com/search?q={q}"},
    "hublot": {"label": "HUBLOT", "url": "https://www.hublot.com/en-us/watches"},
    "jewelers": {"label": "Jewelers Toy Store", "url": "https://www.jewelerstoystore.com/Electronic-s/1074.htm"},
    "rolex": {"label": "Rolex", "url": "https://www.rolex.com/es/watches/find-rolex?group=0"},
}


DISABLED_STORES = {"amazon", "target", "walmart"}


# Catálogo local ilustrativo para que HUBLOT funcione aunque el cliente esté desactualizado.
HUBLOT_CATALOG = [{'id': 'bb-original-red', 'name': 'Big Bang Original Soft Touch All Red', 'collection': 'Big Bang', 'price': 24900, 'desc': 'Rojo integral y diseño deportivo contemporáneo.', 'img': ''}, {'id': 'bb-original-black', 'name': 'Big Bang Original Soft Touch All Black', 'collection': 'Big Bang', 'price': 24900, 'desc': 'Acabado negro integral de carácter técnico.', 'img': ''}, {'id': 'bb-original-titanium', 'name': 'Big Bang Original Titanium 43 mm', 'collection': 'Big Bang', 'price': 20400, 'desc': 'Titanio ligero con estética emblemática.', 'img': ''}, {'id': 'bb-original-titanium-ceramic', 'name': 'Big Bang Original Titanium Ceramic 43 mm', 'collection': 'Big Bang', 'price': 21600, 'desc': 'Titanio y cerámica en contraste.', 'img': ''}, {'id': 'bb-original-king-gold', 'name': 'Big Bang Original King Gold Ceramic 43 mm', 'collection': 'Big Bang', 'price': 39600, 'desc': 'King Gold combinado con cerámica.', 'img': ''}, {'id': 'bb-original-black-magic', 'name': 'Big Bang Original Black Magic 43 mm', 'collection': 'Big Bang', 'price': 22800, 'desc': 'Cerámica negra con presencia discreta.', 'img': ''}, {'id': 'bb-original-coal-blue', 'name': 'Big Bang Original Titanium Coal Blue 43 mm', 'collection': 'Big Bang', 'price': 20400, 'desc': 'Esfera azul carbón y caja de titanio.', 'img': ''}, {'id': 'bb-reloaded-uefa', 'name': 'Big Bang Reloaded UEFA Champions League 44 mm', 'collection': 'Big Bang', 'price': 25200, 'desc': 'Edición temática de fútbol.', 'img': ''}, {'id': 'bb-sapphire-sky', 'name': 'Big Bang Sapphire Sky Blue 44 mm', 'collection': 'Big Bang', 'price': 84300, 'desc': 'Caja de zafiro azul translúcido.', 'img': ''}, {'id': 'bb-summer-42', 'name': 'Big Bang Summer Multi-Colored Ceramic 42 mm', 'collection': 'Big Bang', 'price': 34300, 'desc': 'Cerámica multicolor de edición llamativa.', 'img': ''}, {'id': 'bb-summer-44', 'name': 'Big Bang Summer Multi-Colored Ceramic 44 mm', 'collection': 'Big Bang', 'price': 119000, 'desc': 'Versión de alta complejidad multicolor.', 'img': ''}, {'id': 'bb-peach-42', 'name': 'Big Bang Titanium Peach Ceramic 42 mm', 'collection': 'Big Bang', 'price': 24000, 'desc': 'Cerámica tono melocotón y titanio.', 'img': ''}, {'id': 'bb-peach-33', 'name': 'Big Bang Peach Ceramic 33 mm', 'collection': 'Big Bang', 'price': 15500, 'desc': 'Formato compacto en cerámica melocotón.', 'img': ''}, {'id': 'bb-petrol-33', 'name': 'Big Bang Petrol Blue Ceramic 33 mm', 'collection': 'Big Bang', 'price': 15500, 'desc': 'Cerámica azul petróleo.', 'img': ''}, {'id': 'bb-mint-33', 'name': 'Big Bang Mint Green Ceramic 33 mm', 'collection': 'Big Bang', 'price': 15500, 'desc': 'Cerámica verde menta.', 'img': ''}, {'id': 'bb-unico-grey', 'name': 'Big Bang Unico Essential Grey 42 mm', 'collection': 'Big Bang', 'price': 24000, 'desc': 'Cronógrafo Unico en tonos grises.', 'img': ''}, {'id': 'bb-magic-gold', 'name': 'Big Bang Reloaded Magic Gold 44 mm', 'collection': 'Big Bang', 'price': 44500, 'desc': 'Aleación Magic Gold resistente a rayaduras.', 'img': ''}, {'id': 'bb-king-gold', 'name': 'Big Bang Original King Gold 43 mm', 'collection': 'Big Bang', 'price': 39600, 'desc': 'King Gold en silueta clásica Big Bang.', 'img': ''}, {'id': 'bb-unico-titanium', 'name': 'Big Bang Unico Titanium 42 mm', 'collection': 'Big Bang', 'price': 26400, 'desc': 'Cronógrafo con caja de titanio.', 'img': ''}, {'id': 'square-unico-titanium', 'name': 'Square Bang Unico Titanium 42 mm', 'collection': 'Big Bang', 'price': 26400, 'desc': 'Caja cuadrada y movimiento Unico.', 'img': ''}, {'id': 'square-unico-ceramic', 'name': 'Square Bang Unico Titanium Ceramic 42 mm', 'collection': 'Big Bang', 'price': 27600, 'desc': 'Titanio y cerámica en formato cuadrado.', 'img': ''}, {'id': 'square-king-gold', 'name': 'Square Bang Unico King Gold 42 mm', 'collection': 'Big Bang', 'price': 49300, 'desc': 'King Gold con geometría cuadrada.', 'img': ''}, {'id': 'square-black-magic', 'name': 'Square Bang Unico Black Magic 42 mm', 'collection': 'Big Bang', 'price': 30000, 'desc': 'Caja cuadrada de cerámica negra.', 'img': ''}, {'id': 'classic-original-titanium', 'name': 'Classic Fusion Original Titanium 42 mm', 'collection': 'Classic Fusion', 'price': 9400, 'desc': 'Elegancia minimalista en titanio.', 'img': ''}, {'id': 'classic-original-black', 'name': 'Classic Fusion Original Black Magic 42 mm', 'collection': 'Classic Fusion', 'price': 11400, 'desc': 'Diseño sobrio con acabado negro.', 'img': ''}, {'id': 'classic-titanium', 'name': 'Classic Fusion Titanium 42 mm', 'collection': 'Classic Fusion', 'price': 8700, 'desc': 'Perfil limpio y caja de titanio.', 'img': ''}, {'id': 'classic-blue', 'name': 'Classic Fusion Titanium Blue 42 mm', 'collection': 'Classic Fusion', 'price': 8700, 'desc': 'Esfera azul y estética refinada.', 'img': ''}, {'id': 'classic-king-gold', 'name': 'Classic Fusion King Gold 42 mm', 'collection': 'Classic Fusion', 'price': 25200, 'desc': 'Oro cálido con líneas depuradas.', 'img': ''}, {'id': 'classic-black-magic', 'name': 'Classic Fusion Black Magic 42 mm', 'collection': 'Classic Fusion', 'price': 10700, 'desc': 'Cerámica negra y diseño elegante.', 'img': ''}, {'id': 'classic-chrono-ti', 'name': 'Classic Fusion Chronograph Titanium 42 mm', 'collection': 'Classic Fusion', 'price': 12300, 'desc': 'Cronógrafo clásico en titanio.', 'img': ''}, {'id': 'classic-chrono-gold', 'name': 'Classic Fusion Chronograph King Gold 42 mm', 'collection': 'Classic Fusion', 'price': 32400, 'desc': 'Cronógrafo con caja King Gold.', 'img': ''}, {'id': 'classic-chrono-black', 'name': 'Classic Fusion Chronograph Black Magic 42 mm', 'collection': 'Classic Fusion', 'price': 13500, 'desc': 'Cronógrafo con acabado cerámico negro.', 'img': ''}, {'id': 'classic-aero-ti', 'name': 'Classic Fusion Aerofusion Titanium 45 mm', 'collection': 'Classic Fusion', 'price': 17100, 'desc': 'Esfera esqueletizada y caja de titanio.', 'img': ''}, {'id': 'classic-aero-black', 'name': 'Classic Fusion Aerofusion Black Magic 45 mm', 'collection': 'Classic Fusion', 'price': 18800, 'desc': 'Arquitectura esqueletizada en negro.', 'img': ''}, {'id': 'spirit-ti', 'name': 'Spirit of Big Bang Titanium 42 mm', 'collection': 'Spirit of Big Bang', 'price': 26400, 'desc': 'Caja tonneau y titanio ligero.', 'img': ''}, {'id': 'spirit-ti-ceramic', 'name': 'Spirit of Big Bang Titanium Ceramic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 27600, 'desc': 'Tonneau con combinación de materiales.', 'img': ''}, {'id': 'spirit-king-gold', 'name': 'Spirit of Big Bang King Gold 42 mm', 'collection': 'Spirit of Big Bang', 'price': 49300, 'desc': 'Caja tonneau en King Gold.', 'img': ''}, {'id': 'spirit-king-ceramic', 'name': 'Spirit of Big Bang King Gold Ceramic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 45700, 'desc': 'King Gold y cerámica negra.', 'img': ''}, {'id': 'spirit-black-magic', 'name': 'Spirit of Big Bang Black Magic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 30000, 'desc': 'Silueta tonneau con acabado negro.', 'img': ''}, {'id': 'spirit-taupe', 'name': 'Spirit of Big Bang Essential Taupe 42 mm', 'collection': 'Spirit of Big Bang', 'price': 24800, 'desc': 'Tono taupe, edición exclusiva online según fabricante.', 'img': ''}, {'id': 'spirit-impact-black', 'name': 'Spirit of Big Bang Impact All Black 42 mm', 'collection': 'Spirit of Big Bang', 'price': 33700, 'desc': 'Diseño oscuro de alta presencia.', 'img': ''}, {'id': 'spirit-impact-sapphire', 'name': 'Spirit of Big Bang Impact Sapphire 42 mm', 'collection': 'Spirit of Big Bang', 'price': 114500, 'desc': 'Caja de zafiro y diseño escultural.', 'img': ''}, {'id': 'spirit-sapphire-blue', 'name': 'Spirit of Big Bang Sapphire Blue 42 mm', 'collection': 'Spirit of Big Bang', 'price': 102400, 'desc': 'Caja de zafiro azul.', 'img': ''}, {'id': 'spirit-coal-blue', 'name': 'Spirit of Big Bang Titanium Coal Blue 42 mm', 'collection': 'Spirit of Big Bang', 'price': 24000, 'desc': 'Titanio y esfera azul carbón.', 'img': ''}, {'id': 'spirit-white', 'name': 'Spirit of Big Bang Titanium White 42 mm', 'collection': 'Spirit of Big Bang', 'price': 26400, 'desc': 'Titanio con estética blanca.', 'img': ''}, {'id': 'spirit-meca-ti', 'name': 'Spirit of Big Bang Meca-10 Titanium 45 mm', 'collection': 'Spirit of Big Bang', 'price': 27600, 'desc': 'Reserva de marcha larga y arquitectura mecánica.', 'img': ''}, {'id': 'spirit-meca-gold', 'name': 'Spirit of Big Bang Meca-10 King Gold 45 mm', 'collection': 'Spirit of Big Bang', 'price': 52900, 'desc': 'Meca-10 con caja King Gold.', 'img': ''}, {'id': 'spirit-tourbillon-black', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Black Magic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 109000, 'desc': 'Tourbillon y reserva de marcha de cinco días.', 'img': ''}, {'id': 'spirit-tourbillon-red', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Red Magic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 109000, 'desc': 'Cerámica roja y tourbillon.', 'img': ''}, {'id': 'spirit-tourbillon-blue', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Sky Blue Ceramic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 109000, 'desc': 'Cerámica azul cielo y tourbillon.', 'img': ''}, {'id': 'spirit-tourbillon-yellow', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Yellow Magic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 109000, 'desc': 'Cerámica amarilla y tourbillon.', 'img': ''}, {'id': 'spirit-tourbillon-sapphire', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Black Sapphire 42 mm', 'collection': 'Spirit of Big Bang', 'price': 169000, 'desc': 'Caja de zafiro negro y tourbillon.', 'img': ''}]


# Modelos destacados del catálogo oficial Rolex. La página oficial no publica ranking de ventas;
# se presentan como modelos destacados, no como una lista verificada de los más vendidos.
# Precios base en USD observados en la página oficial; confirmar antes de publicar ofertas de venta.
# Catálogo Rolex: 47 referencias/modelos destacados con fotografías servidas por media.rolex.com.
# Los precios son referencias en USD; el descuento del 50% es una promoción interna de ProEshop, no oficial de Rolex.
ROLEX_CATALOG = [
    {"id":"land-dweller-40", "name":"Rolex Land-Dweller 40 · acero y oro blanco", "price":16100.00, "discount":50, "desc":"Esfera blanco intenso con motivo nido de abeja.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m127334-0001", "reference":"m127334-0001"},
    {"id":"day-date-40-platinum", "name":"Rolex Day-Date 40 · platino, esfera azul glaciar", "price":68800.00, "discount":50, "desc":"Caja de platino y esfera azul glaciar.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m228236-0018", "reference":"m228236-0018"},
    {"id":"sky-dweller-everose", "name":"Rolex Sky-Dweller · oro Everose, esfera pizarra", "price":64900.00, "discount":50, "desc":"Caja de oro Everose y esfera pizarra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m336935-0008", "reference":"m336935-0008"},
    {"id":"lady-datejust-two-tone", "name":"Rolex Lady-Datejust 28 · acero y oro amarillo", "price":15100.00, "discount":50, "desc":"Lady-Datejust con esfera plateada engastada de diamantes.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m279173-0007", "reference":"m279173-0007"},
    {"id":"datejust-41-green", "name":"Rolex Datejust 41 · acero y oro blanco, esfera verde", "price":11650.00, "discount":50, "desc":"Datejust 41 con esfera verde sombreado.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126334-0033", "reference":"m126334-0033"},
    {"id":"oyster-perpetual-41-slate", "name":"Rolex Oyster Perpetual 41 · acero y oro amarillo", "price":9650.00, "discount":50, "desc":"Oyster Perpetual 41 con esfera pizarra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m134303-0001", "reference":"m134303-0001"},
    {"id":"sea-dweller-two-tone", "name":"Rolex Sea-Dweller 43 · acero y oro amarillo", "price":22450.00, "discount":50, "desc":"Reloj de buceo con esfera negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126603-0001", "reference":"m126603-0001"},
    {"id":"gmt-master-ii-grnr", "name":"Rolex GMT-Master II · bisel gris y negro", "price":12000.00, "discount":50, "desc":"GMT-Master II de acero, referencia GRNR.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/c_limit%2Cw_1920/v1/rolexcom/094398bf1f99/collection/watches-grid/beautyshot-cards/m126710grnr-0004/m126710grnr-0004_v01", "reference":"m126710grnr-0004"},
    {"id":"gmt-master-ii-batman", "name":"Rolex GMT-Master II · bisel azul y negro", "price":12000.00, "discount":50, "desc":"GMT-Master II de acero con bisel azul y negro.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126710blnr-0003", "reference":"m126710blnr-0003"},
    {"id":"yacht-master-42-gold", "name":"Rolex Yacht-Master 42 · oro amarillo", "price":38100.00, "discount":50, "desc":"Yacht-Master 42 en oro amarillo con esfera negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m226658-0001", "reference":"m226658-0001"},
    {"id":"yacht-master-ii-steel", "name":"Rolex Yacht-Master II 44 · acero", "price":20300.00, "discount":50, "desc":"Yacht-Master II con esfera blanca.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126680-0001", "reference":"m126680-0001"},
    {"id":"explorer-40", "name":"Rolex Explorer 40 · acero Oystersteel", "price":8200.00, "discount":50, "desc":"Explorer 40 con esfera negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m224270-0001", "reference":"m224270-0001"},
    {"id":"explorer-ii-black", "name":"Rolex Explorer II 42 · esfera negra", "price":10600.00, "discount":50, "desc":"Explorer II de acero con indicador de segundo huso horario.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m226570-0001", "reference":"m226570-0001"},
    {"id":"air-king-40", "name":"Rolex Air-King 40 · esfera negra", "price":8150.00, "discount":50, "desc":"Diseño inspirado en la historia de la aviación.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126900-0001", "reference":"m126900-0001"},
    {"id":"1908-yellow-gold", "name":"Rolex 1908 39 · oro amarillo", "price":40900.00, "discount":50, "desc":"Modelo clásico de oro amarillo con esfera blanca.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m52508-0008", "reference":"m52508-0008"},
    {"id":"oyster-perpetual-36-multicolor", "name":"Rolex Oyster Perpetual 36 · esfera multicolor", "price":6750.00, "discount":50, "desc":"Oyster Perpetual 36 de acero con motivo multicolor.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126000-0016", "reference":"m126000-0016"},
    {"id":"land-dweller-platinum", "name":"Rolex Land-Dweller 40 · platino", "price":67000.00, "discount":50, "desc":"Land-Dweller con esfera azul glaciar y motivo nido de abeja.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m127336-0001", "reference":"m127336-0001"},
    {"id":"daytona-steel-white", "name":"Rolex Cosmograph Daytona 40 · acero, esfera blanca", "price":16900.00, "discount":50, "desc":"Cronógrafo Cosmograph Daytona de acero Oystersteel.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126500ln-0001", "reference":"m126500ln-0001"},
    {"id":"oyster-perpetual-36-black", "name":"Rolex Oyster Perpetual 36 · esfera negra", "price":6750.00, "discount":50, "desc":"Oyster Perpetual 36 con esfera negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126000-0014", "reference":"m126000-0014"},
    {"id":"gmt-master-ii-grnr-black", "name":"Rolex GMT-Master II · bisel gris y negro, variante", "price":12000.00, "discount":50, "desc":"GMT-Master II de acero con bisel gris y negro.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126710grnr-0003", "reference":"m126710grnr-0003"},
    {"id":"1908-platinum", "name":"Rolex 1908 39 · platino, esfera azul glaciar", "price":32900.00, "discount":50, "desc":"1908 en platino con esfera azul glaciar.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m52506-0003", "reference":"m52506-0003"},
    {"id":"1908-white-gold", "name":"Rolex 1908 39 · oro blanco", "price":29600.00, "discount":50, "desc":"1908 de oro blanco con esfera negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m52509-0002", "reference":"m52509-0002"},
    {"id":"daytona-everose-chocolate", "name":"Rolex Cosmograph Daytona · oro Everose", "price":59100.00, "discount":50, "desc":"Daytona de oro Everose con esfera chocolate y negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126505-0005", "reference":"m126505-0005"},
    {"id":"day-date-white-gold", "name":"Rolex Day-Date 40 · oro blanco", "price":53100.00, "discount":50, "desc":"Day-Date 40 de oro blanco con esfera verde oliva.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m228239-0033", "reference":"m228239-0033"},
    {"id":"deepsea-yellow-gold", "name":"Rolex Deepsea · oro amarillo, esfera azul", "price":68100.00, "discount":50, "desc":"Deepsea de alta resistencia con esfera azul.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m136668lb-0001", "reference":"m136668lb-0001"},
    {"id":"submariner-date-black", "name":"Rolex Submariner Date 41 · acero, esfera negra", "price":11350.00, "discount":50, "desc":"Submariner Date de acero Oystersteel.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126610ln-0001", "reference":"m126610ln-0001"},
    {"id":"oyster-perpetual-28-gold", "name":"Rolex Oyster Perpetual 28 · oro amarillo", "price":31600.00, "discount":50, "desc":"Oyster Perpetual 28 con piedra verde.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m276208-0002", "reference":"m276208-0002"},
    {"id":"datejust-36-two-tone", "name":"Rolex Datejust 36 · acero y oro amarillo", "price":15050.00, "discount":50, "desc":"Datejust 36 con esfera verde oliva.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126203-0058", "reference":"m126203-0058"},
    {"id":"day-date-yellow-gold", "name":"Rolex Day-Date 40 · oro amarillo", "price":49400.00, "discount":50, "desc":"Day-Date 40 con esfera blanca.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m228238-0042", "reference":"m228238-0042"},
    {"id":"land-dweller-diamond", "name":"Rolex Land-Dweller 36 · platino y diamantes", "price":100050.00, "discount":50, "desc":"Land-Dweller 36 con esfera azul glaciar y diamantes.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m127286tbr-0001", "reference":"m127286tbr-0001"},
    {"id":"daytona-everose-sundust", "name":"Rolex Cosmograph Daytona · oro Everose, Sundust", "price":44800.00, "discount":50, "desc":"Daytona Everose con esfera Sundust y contadores negros.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126515ln-0006", "reference":"m126515ln-0006"},
    {"id":"oyster-perpetual-34-everose", "name":"Rolex Oyster Perpetual 34 · oro Everose", "price":40100.00, "discount":50, "desc":"Oyster Perpetual 34 con piedra azul.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m124205-0002", "reference":"m124205-0002"},
    {"id":"yacht-master-40-platinum", "name":"Rolex Yacht-Master 40 · acero y platino", "price":13200.00, "discount":50, "desc":"Yacht-Master 40 con bisel de platino y esfera pizarra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126622-0001", "reference":"m126622-0001"},
    {"id":"yacht-master-37-everose", "name":"Rolex Yacht-Master 37 · acero y oro Everose", "price":17750.00, "discount":50, "desc":"Yacht-Master 37 con esfera chocolate.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m268621-0003", "reference":"m268621-0003"},
    {"id":"yacht-master-42-white-gold", "name":"Rolex Yacht-Master 42 · oro blanco", "price":40000.00, "discount":50, "desc":"Yacht-Master 42 de oro blanco con esfera negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m226659-0002", "reference":"m226659-0002"},
    {"id":"datejust-41-yellow-gold", "name":"Rolex Datejust 41 · acero y oro amarillo", "price":17700.00, "discount":50, "desc":"Datejust 41 con esfera champagne.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126333-0010", "reference":"m126333-0010"},
    {"id":"lady-datejust-everose-diamonds", "name":"Rolex Lady-Datejust 28 · oro Everose y diamantes", "price":53100.00, "discount":50, "desc":"Lady-Datejust con esfera chocolate engastada de diamantes.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m279135rbr-0001", "reference":"m279135rbr-0001"},
    {"id":"datejust-36-diamond", "name":"Rolex Datejust 36 · oro blanco y diamantes", "price":18050.00, "discount":50, "desc":"Datejust 36 con esfera nácar blanco engastada de diamantes.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126284rbr-0011", "reference":"m126284rbr-0011"},
    {"id":"gmt-master-ii-everose", "name":"Rolex GMT-Master II · oro Everose", "price":57500.00, "discount":50, "desc":"GMT-Master II de oro Everose con esfera ojo de hierro.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126715chnr-0002", "reference":"m126715chnr-0002"},
    {"id":"datejust-31-everose", "name":"Rolex Datejust 31 · acero y oro Everose", "price":13950.00, "discount":50, "desc":"Datejust 31 con esfera pizarra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m278241-0018", "reference":"m278241-0018"},
    {"id":"yacht-master-42-titanium", "name":"Rolex Yacht-Master 42 · titanio RLX", "price":15500.00, "discount":50, "desc":"Yacht-Master 42 en titanio RLX.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m226627-0001", "reference":"m226627-0001"},
    {"id":"sky-dweller-steel-white-gold", "name":"Rolex Sky-Dweller 42 · acero y oro blanco", "price":17750.00, "discount":50, "desc":"Sky-Dweller con esfera verde menta.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m336934-0001", "reference":"m336934-0001"},
    {"id":"day-date-yellow-gold-green", "name":"Rolex Day-Date 40 · oro amarillo, esfera verde", "price":49400.00, "discount":50, "desc":"Day-Date 40 de oro amarillo con esfera verde sombreado.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m228238-0069", "reference":"m228238-0069"},
    {"id":"gmt-master-ii-yellow-gold", "name":"Rolex GMT-Master II · oro amarillo", "price":50800.00, "discount":50, "desc":"GMT-Master II de oro amarillo con esfera negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126718grnr-0001", "reference":"m126718grnr-0001"},
    {"id":"sky-dweller-white-gold", "name":"Rolex Sky-Dweller · oro blanco", "price":53450.00, "discount":50, "desc":"Sky-Dweller de oro blanco con esfera negra.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m336239-0002", "reference":"m336239-0002"},
    {"id":"yacht-master-ii-yellow-gold", "name":"Rolex Yacht-Master II 44 · oro amarillo", "price":60700.00, "discount":50, "desc":"Yacht-Master II de oro amarillo con esfera blanca.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126688-0001", "reference":"m126688-0001"},
    {"id":"datejust-41-steel-blue", "name":"Rolex Datejust 41 · acero, esfera azul", "price":8950.00, "discount":50, "desc":"Datejust 41 de acero Oystersteel con esfera azul vivo.", "url":"https://www.rolex.com/es/watches/find-rolex", "img":"https://media.rolex.com/image/upload/q_auto%3Aeco/f_auto/t_v7-grid/c_limit%2Cw_1920/v1/a677b2c664f6/catalogue/2026/upright-bba-with-shadow/m126300-0029", "reference":"m126300-0029"}
]


JEWELERS_CATALOG = [{'id': 'niton-xl2-100p',
  'name': 'Niton XL2 100p, Niton Gold XRF Analyzer XL2100',
  'price': 20500.0,
  'desc': 'Analizador XRF para metales preciosos.',
  'url': 'https://www.jewelerstoystore.com/Niton-XL2-100p-XL2100-Niton-Gold-XRF-Analyzer-p/xrf-xl2.htm'},
 {'id': 'niton-dxl',
  'name': 'Niton DXL Precious Metal Analyzer',
  'price': 21750.0,
  'desc': 'Analizador de metales preciosos.',
  'url': 'https://www.jewelerstoystore.com/precious-metal-analyzer-p/dxl.htm'},
 {'id': 'niton-xl2-battery',
  'name': 'Niton XL2 Battery: 7.4V 7800mAh Li-ion (NTL200SL)',
  'price': 295.0,
  'desc': 'Batería de repuesto para analizador XRF Niton XL2.',
  'url': 'https://www.jewelerstoystore.com/Niton-XL2-Battery-7-4V-p/xl-2.htm'},
 {'id': 'niton-xl2-charger',
  'name': 'Niton XL2 Battery Charger – Fast, Smart & Reliable Charging for Your XRF Analyzer',
  'price': 395.0,
  'desc': 'Cargador para analizador XRF Niton XL2.',
  'url': 'https://www.jewelerstoystore.com/Niton-XL2-Battery-Charger-p/xl-3.htm'}]



# Imágenes locales de respaldo: las páginas oficiales pueden bloquear la extracción de imágenes (HTTP 403).
HUBLOT_LOCAL_IMAGES = {p["id"]: f"/static/catalog_images/hublot_{i+1:02d}.jpg" for i, p in enumerate(HUBLOT_CATALOG)}
def _rolex_fallback_for(product, index):
    key = (str(product.get("id", "")) + " " + str(product.get("name", ""))).casefold()
    ranges = [("oyster-perpetual", 1, 13), ("datejust", 14, 26), ("day-date", 27, 30),
              ("sky-dweller", 31, 34), ("gmt-master", 35, 38), ("submariner", 39, 42),
              ("sea-dweller", 43, 45), ("deepsea", 43, 45), ("explorer", 46, 49),
              ("air-king", 46, 49), ("yacht-master", 50, 53), ("milgauss", 54, 55),
              ("1908", 56, 58), ("cellini", 56, 58), ("pearlmaster", 59, 61),
              ("land-dweller", 14, 26), ("daytona", 35, 38)]
    for family, first, last in ranges:
        if family in key:
            return f"/static/catalog_images/rolex_crop_{first + (index % (last-first+1)):03d}.jpg"
    return f"/static/catalog_images/rolex_crop_{1 + (index % 61):03d}.jpg"
ROLEX_LOCAL_IMAGES = {p["id"]: _rolex_fallback_for(p, i) for i, p in enumerate(ROLEX_CATALOG)}
JEWELERS_LOCAL_IMAGES = {p["id"]: f"/static/catalog_images/jewelers_{i+1:02d}.jpg" for i, p in enumerate(JEWELERS_CATALOG)}
for _p in JEWELERS_CATALOG:
    _p["img"] = JEWELERS_LOCAL_IMAGES.get(_p["id"], "/static/catalog_images/jewelers_01.jpg")
for _p in ROLEX_CATALOG:
    _p["discount"] = 50

@app.on_event("startup")
async def startup():
    global _tron_monitor_task
    init_db()
    _tron_monitor_task = asyncio.create_task(tron_payment_monitor())
    if BOT_TOKEN and PUBLIC_BASE_URL:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": f"{PUBLIC_BASE_URL}/telegram-webhook/{WEBHOOK_SECRET}",
                      "allowed_updates": ["message"], "drop_pending_updates": False},
            )
            if r.status_code >= 400:
                log.error("No se pudo configurar webhook: %s", r.text[:300])


@app.on_event("shutdown")
async def shutdown_tron_monitor():
    global _tron_monitor_task
    if _tron_monitor_task:
        _tron_monitor_task.cancel()
        try:
            await _tron_monitor_task
        except asyncio.CancelledError:
            pass
        _tron_monitor_task = None


@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
async def health():
    return {"ok": True, "service": "shopcart-miniapp"}


@app.post("/telegram-webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if not hmac.compare_digest(secret, WEBHOOK_SECRET):
        raise HTTPException(404, "Not found")
    update = await request.json()
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id and text.startswith("/start"):
        keyboard = {"inline_keyboard": [[{
            "text": "🛍️ Abrir ShopCart",
            "web_app": {"url": PUBLIC_BASE_URL}
        }]]}
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                "chat_id": chat_id,
                "text": "Bienvenido a ShopCart. Abre la miniapp para buscar artículos y gestionar tu carrito ficticio.",
                "reply_markup": keyboard
            })
    return {"ok": True}


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + salt.hex() + "$" + digest.hex()

def _password_matches(password: str, stored: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = stored.split("$", 2)
        if algorithm != "scrypt": return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual.hex(), digest_hex)
    except Exception:
        return False

def _new_session(identity: str) -> str:
    token = secrets.token_urlsafe(40)
    with conn() as db:
        db.execute("INSERT OR IGNORE INTO users(telegram_id,username,demo_login,created_at) VALUES(?,?,?,?)", (identity, identity[:80], '', now_iso()))
        db.execute("INSERT OR IGNORE INTO balances(telegram_id,amount) VALUES(?,?)", (identity, str(INITIAL_BALANCE)))
        db.execute("INSERT INTO sessions(token,telegram_id,created_at,active) VALUES(?,?,?,1)", (token, identity, time.time()))
    return token

def _send_verification_code(email: str, code: str):
    """Send a short-lived numeric verification code using Brevo API or configured SMTP."""
    if not SMTP_FROM_EMAIL:
        raise RuntimeError("Configura SMTP_FROM_EMAIL para verificar las cuentas por correo.")
    subject = "Tu código de verificación · ProEshop"
    text_body = (f"Hola. Tu código para verificar tu correo en ProEshop es: {code}\n\n"
                 "El código vence en 10 minutos y solo puede utilizarse una vez. "
                 "Si no solicitaste esta cuenta, ignora este mensaje.")
    html_body = f"""<!doctype html><html lang='es'><meta charset='utf-8'><body style='font-family:Arial;background:#101429;color:#eef0ff;padding:28px'><div style='max-width:560px;margin:auto;background:#191d38;padding:28px;border-radius:18px'><h1>ProEshop</h1><h2>Tu código de verificación</h2><p>Regresa a ProEshop en Telegram e introduce este código para activar tu cuenta:</p><div style='font-size:34px;letter-spacing:9px;font-weight:bold;background:#101429;color:#fff;text-align:center;padding:18px;border-radius:12px'>{code}</div><p>El código vence en 10 minutos y solo puede utilizarse una vez.</p><p style='color:#b9bdd3'>Si no solicitaste esta cuenta, ignora este mensaje.</p></div></body></html>"""
    if BREVO_API_KEY:
        with httpx.Client(timeout=12) as client:
            response = client.post("https://api.brevo.com/v3/smtp/email", headers={"api-key": BREVO_API_KEY, "accept":"application/json", "content-type":"application/json"}, json={"sender":{"email":SMTP_FROM_EMAIL,"name":"ProEshop"},"to":[{"email":email}],"subject":subject,"textContent":text_body,"htmlContent":html_body})
            if response.status_code >= 300: raise RuntimeError("No se pudo enviar el código de verificación.")
        return
    if not SMTP_HOST: raise RuntimeError("Configura BREVO_API_KEY o SMTP_HOST para enviar verificaciones.")
    msg=EmailMessage(); msg["Subject"]=subject; msg["From"]=f"ProEshop <{SMTP_FROM_EMAIL}>"; msg["To"]=email; msg.set_content(text_body); msg.add_alternative(html_body,subtype="html")
    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST,SMTP_PORT,timeout=15) as server:
            if SMTP_USER: server.login(SMTP_USER,SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST,SMTP_PORT,timeout=15) as server:
            server.starttls()
            if SMTP_USER: server.login(SMTP_USER,SMTP_PASSWORD)
            server.send_message(msg)

@app.post("/api/register")
async def register_account(body: RegisterBody, request: Request):
    email=body.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email): raise HTTPException(422,"Introduce un correo válido.")
    if len(body.password)<10 or not re.search(r"[A-Za-z]",body.password) or not re.search(r"\d",body.password): raise HTTPException(422,"La contraseña debe tener al menos 10 caracteres e incluir letras y números.")
    code=f"{secrets.randbelow(1_000_000):06d}"
    code_hash=hashlib.sha256(code.encode()).hexdigest()
    expires=time.time()+600
    with conn() as db:
        exists=db.execute("SELECT 1 FROM email_accounts WHERE email=? COLLATE NOCASE",(email,)).fetchone()
        if exists:
            raise HTTPException(409,"Ya existe una cuenta con ese correo. Inicia sesión o recupera tu acceso.")
        # Replacing a pending attempt is safe: pending registrations are not user accounts.
        db.execute("DELETE FROM pending_email_registrations WHERE email=? COLLATE NOCASE",(email,))
        db.execute("INSERT INTO pending_email_registrations(email,password_hash,verify_hash,verify_expires,attempts,created_at) VALUES(?,?,?,?,0,?)",
                   (email,_password_hash(body.password),code_hash,expires,now_iso()))
    try:
        _send_verification_code(email,code)
    except Exception as exc:
        with conn() as db: db.execute("DELETE FROM pending_email_registrations WHERE email=? COLLATE NOCASE",(email,))
        log.warning("No se pudo enviar código de verificación: %s",str(exc)[:180])
        raise HTTPException(503,"No pudimos enviar el código. Revisa la configuración de correo en Railway e inténtalo de nuevo.")
    audit("pending:"+hashlib.sha256(email.encode()).hexdigest()[:16],"register_pending","Código de verificación enviado; la cuenta aún no ha sido creada")
    return {"ok":True,"message":"Te enviamos un código de verificación de 6 dígitos. La cuenta se creará únicamente si el código es correcto.","email":email}


@app.post("/api/verify-email-code")
async def verify_email_code(body: dict):
    email=str(body.get("email", "")).strip().lower()
    code=str(body.get("code", "")).strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not re.fullmatch(r"\d{6}", code):
        raise HTTPException(400,"Introduce el correo y el código de 6 dígitos.")
    code_hash=hashlib.sha256(code.encode()).hexdigest()
    pending_error=None
    account_id=None
    with conn() as db:
        row=db.execute("SELECT * FROM pending_email_registrations WHERE email=? COLLATE NOCASE",(email,)).fetchone()
        if not row:
            pending_error=(400,"No hay un registro pendiente para ese correo. Vuelve a registrarte.")
        elif float(row["verify_expires"] or 0) <= time.time():
            db.execute("DELETE FROM pending_email_registrations WHERE email=? COLLATE NOCASE",(email,))
            pending_error=(400,"El código venció. Vuelve a registrarte para recibir uno nuevo.")
        elif int(row["attempts"] or 0) >= 5:
            db.execute("DELETE FROM pending_email_registrations WHERE email=? COLLATE NOCASE",(email,))
            pending_error=(429,"Se agotaron los intentos. Vuelve a registrarte para recibir un nuevo código.")
        elif not hmac.compare_digest(str(row["verify_hash"] or ""),code_hash):
            attempts=int(row["attempts"] or 0)+1
            if attempts >= 5:
                db.execute("DELETE FROM pending_email_registrations WHERE email=? COLLATE NOCASE",(email,))
                pending_error=(429,"El código no es correcto y se agotaron los intentos. Vuelve a registrarte.")
            else:
                db.execute("UPDATE pending_email_registrations SET attempts=? WHERE email=? COLLATE NOCASE",(attempts,email))
                pending_error=(400,f"El código no es correcto. Te quedan {5-attempts} intentos.")
        else:
            account_id="email:"+secrets.token_urlsafe(18)
            timestamp=now_iso()
            # Only now, after a valid code, create the actual email account.
            db.execute("INSERT INTO email_accounts(account_id,email,password_hash,verified,verify_hash,verify_expires,created_at,updated_at) VALUES(?,?,?,1,'',0,?,?)",
                       (account_id,email,row["password_hash"],timestamp,timestamp))
            db.execute("DELETE FROM pending_email_registrations WHERE email=? COLLATE NOCASE",(email,))
    # Raise only after leaving the transaction so attempt counters / expiry cleanup commit.
    if pending_error:
        raise HTTPException(pending_error[0],pending_error[1])
    identity=account_id
    token=_new_session(identity)
    audit(identity,"email_verified","Cuenta creada tras verificar el código; sesión iniciada automáticamente")
    return {"ok":True,"token":token,"username":email.split('@')[0],"email":email,"account_type":"email","message":"Registro exitoso. Tu cuenta fue creada y tu sesión está iniciada."}

@app.get("/api/verify-email", response_class=HTMLResponse)
async def verify_email(token: str):
    token_hash=hashlib.sha256(token.encode()).hexdigest()
    with conn() as db:
        row=db.execute("SELECT account_id FROM email_accounts WHERE verify_hash=? AND verified=0 AND verify_expires>?",(token_hash,time.time())).fetchone()
        if not row: return HTMLResponse("<h2>Enlace inválido o vencido</h2><p>Solicita una nueva verificación desde ProEshop.</p>",status_code=400)
        db.execute("UPDATE email_accounts SET verified=1,verify_hash='',verify_expires=0,updated_at=? WHERE account_id=?",(now_iso(),row['account_id']))
        # One-time, short-lived handoff; never put a ProEshop session token in the Telegram URL.
        handoff=secrets.token_urlsafe(24)
        db.execute("INSERT INTO telegram_verification_handoffs(code_hash,account_id,expires_at,used,created_at) VALUES(?,?,?,0,?)",
                   (hashlib.sha256(handoff.encode()).hexdigest(),row['account_id'],time.time()+600,now_iso()))
    audit(row['account_id'],"email_verified","Correo verificado; retorno seguro a Telegram preparado")
    deep_link=f"{TELEGRAM_MINI_APP_URL}?startapp=verify_{handoff}"
    safe_link=escape(deep_link, quote=True)
    return HTMLResponse(f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><meta name='referrer' content='no-referrer'><title>Correo verificado · ProEshop</title></head><body style='font-family:Arial;background:#101429;color:#eef0ff;padding:32px'><main style='max-width:520px;margin:8vh auto;background:#191d38;padding:28px;border-radius:18px'><h1>¡Correo verificado!</h1><p>Tu correo quedó verificado. Abre ProEshop en Telegram para iniciar sesión automáticamente.</p><p><a id='openApp' style='display:inline-block;background:#8970f5;color:#fff;padding:14px 22px;border-radius:10px;text-decoration:none;font-weight:bold' href='{safe_link}'>Volver a ProEshop en Telegram</a></p><p style='color:#b9bdd3'>Si Telegram no se abre automáticamente, pulsa el botón. Este enlace de acceso es de un solo uso y vence en 10 minutos.</p><script>setTimeout(()=>{{ location.href={deep_link!r}; }},900);</script></main></body></html>")

@app.post("/api/telegram-verification-handoff")
async def telegram_verification_handoff(body: dict):
    code=str(body.get("code", ""))
    init_data=str(body.get("init_data", ""))
    if not code.startswith("verify_") or len(code)>100:
        raise HTTPException(400,"Enlace de retorno inválido.")
    tg_id,tg_user=validate_init_data(init_data)
    code_hash=hashlib.sha256(code[7:].encode()).hexdigest()
    with conn() as db:
        handoff=db.execute("SELECT * FROM telegram_verification_handoffs WHERE code_hash=? AND used=0 AND expires_at>?",(code_hash,time.time())).fetchone()
        if not handoff: raise HTTPException(400,"El enlace ya se usó o venció. Vuelve a solicitar la verificación.")
        conflict=db.execute("SELECT account_id FROM email_accounts WHERE telegram_id=? AND account_id<>?",(tg_id,handoff['account_id'])).fetchone()
        if conflict: raise HTTPException(409,"Este Telegram ya está vinculado a otra cuenta. Inicia sesión y vincula las cuentas desde tu perfil.")
        db.execute("UPDATE email_accounts SET telegram_id=?,updated_at=? WHERE account_id=? AND verified=1",(tg_id,now_iso(),handoff['account_id']))
        db.execute("UPDATE telegram_verification_handoffs SET used=1 WHERE code_hash=? AND used=0",(code_hash,))
    identity=handoff['account_id']
    with conn() as db:
        db.execute("INSERT OR IGNORE INTO users(telegram_id,username,demo_login,created_at) VALUES(?,?,?,?)",(identity,tg_user.get('username',''),'',now_iso()))
    session_token=_new_session(identity)
    audit(identity,"telegram_email_handoff","Inicio de sesión tras verificar correo y validar Telegram")
    return {"token":session_token,"username":tg_user.get('first_name') or tg_user.get('username') or 'Cliente',"account_type":"email+telegram"}

@app.post("/api/email-login")
async def email_login(body: EmailLoginBody):
    email=body.email.strip().lower()
    with conn() as db: row=db.execute("SELECT * FROM email_accounts WHERE email=? COLLATE NOCASE",(email,)).fetchone()
    if not row or not _password_matches(body.password,row['password_hash']): raise HTTPException(401,"Correo o contraseña incorrectos.")
    if not row['verified']: raise HTTPException(403,"Primero verifica tu correo desde el enlace que te enviamos.")
    token=_new_session(row['account_id']); audit(row['account_id'],"email_login","Inicio de sesión por correo")
    return {"token":token,"username":email.split('@')[0],"email":email,"account_type":"email"}

@app.post("/api/guest-session")
async def guest_session():
    identity="guest:"+secrets.token_urlsafe(20); token=_new_session(identity); audit(identity,"guest_session","Sesión de invitado creada")
    return {"token":token,"username":"Invitado","account_type":"guest"}

@app.post("/api/telegram-login")
async def telegram_login(body: TelegramBody):
    tg_id,tg_user=validate_init_data(body.init_data)
    with conn() as db:
        linked=db.execute("SELECT account_id,email FROM email_accounts WHERE telegram_id=? AND verified=1",(tg_id,)).fetchone()
    if linked:
        identity=linked['account_id']
    else:
        with conn() as db:
            legacy=db.execute("SELECT telegram_id FROM users WHERE telegram_id IN (?,?) ORDER BY CASE WHEN telegram_id=? THEN 0 ELSE 1 END LIMIT 1",(tg_id,"tg:"+tg_id,tg_id)).fetchone()
        identity=legacy['telegram_id'] if legacy else "tg:"+tg_id
    token=_new_session(identity)
    with conn() as db:
        db.execute("INSERT OR IGNORE INTO users(telegram_id,username,demo_login,created_at) VALUES(?,?,?,?)",(identity,tg_user.get('username',''),'',now_iso()))
    audit(identity,"telegram_login","Inicio de sesión con Telegram")
    return {"token":token,"username":tg_user.get('first_name') or tg_user.get('username') or 'Telegram',"account_type":"email+telegram" if linked else "telegram"}

@app.post("/api/link-telegram")
async def link_telegram(body: TelegramBody, request: Request):
    identity=get_auth(request)
    with conn() as db: account=db.execute("SELECT * FROM email_accounts WHERE account_id=? AND verified=1",(identity,)).fetchone()
    if not account: raise HTTPException(403,"Inicia sesión con una cuenta de correo verificada para vincular Telegram.")
    tg_id,_=validate_init_data(body.init_data)
    with conn() as db:
        conflict=db.execute("SELECT account_id FROM email_accounts WHERE telegram_id=? AND account_id<>?",(tg_id,identity)).fetchone()
        if conflict: raise HTTPException(409,"Este Telegram ya está vinculado a otra cuenta.")
        db.execute("UPDATE email_accounts SET telegram_id=?,updated_at=? WHERE account_id=?",(tg_id,now_iso(),identity))
        # Merge both legacy raw Telegram IDs and the newer namespaced IDs into the verified account.
        for old_identity in {tg_id, "tg:"+tg_id}:
            for table in ('carts','purchases','orders','balances','notification_preferences'):
                old=db.execute(f"SELECT 1 FROM {table} WHERE telegram_id=? LIMIT 1",(old_identity,)).fetchone()
                if old and table=='balances':
                    oldbal=db.execute("SELECT amount FROM balances WHERE telegram_id=?",(old_identity,)).fetchone()
                    db.execute("INSERT OR IGNORE INTO balances(telegram_id,amount) VALUES(?,?)",(identity,oldbal['amount']))
                    db.execute("DELETE FROM balances WHERE telegram_id=?",(old_identity,))
                elif old and table=='notification_preferences':
                    db.execute("INSERT OR IGNORE INTO notification_preferences(telegram_id,order_updates,security_alerts,updated_at) SELECT ?,order_updates,security_alerts,updated_at FROM notification_preferences WHERE telegram_id=?",(identity,old_identity))
                    db.execute("DELETE FROM notification_preferences WHERE telegram_id=?",(old_identity,))
                elif old:
                    db.execute(f"UPDATE {table} SET telegram_id=? WHERE telegram_id=?",(identity,old_identity))
            db.execute("UPDATE sessions SET active=0 WHERE telegram_id=?",(old_identity,))
    audit(identity,"telegram_linked","Telegram vinculado tras verificación de correo")
    return {"ok":True,"message":"Telegram quedó vinculado a tu cuenta."}

@app.post("/api/login")
async def login(body: AuthBody):
    # Backward-compatible route: email login is preferred; old demo credentials are not used for customer accounts.
    raise HTTPException(410,"El acceso antiguo fue sustituido. Usa correo verificado, Telegram o continuar como invitado.")

@app.post("/api/logout")
async def logout(request: Request):
    tg_id = get_auth(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    with conn() as db:
        db.execute("UPDATE sessions SET active=0 WHERE token=? AND telegram_id=?", (token, tg_id))
    audit(tg_id, "logout", "Sesión cerrada")
    return {"ok": True}


HUBLOT_OFFICIAL_IMAGES = {'bb-original-red': 'https://www.hublot.com/sites/default/files/styles/watch_item_desktop_1x_scale_no_crop_600_6000_/public/2026-08/Big-Bang-Original-Soft-Touch-All-Red-43-mm-Soldier.png?itok=evq1Szm7', 'bb-original-black': 'https://www.hublot.com/sites/default/files/styles/watch_item_desktop_1x_scale_no_crop_600_6000_/public/2026-08/Big-Bang-Original-Soft-Touch-All-Black-43-mm-Soldier.png?itok=3YcrBXPZ', 'bb-original-titanium': 'https://www.hublot.com/sites/default/files/styles/watch_item_desktop_1x_scale_no_crop_600_6000_/public/2026-01/Big-Bang-Original-Unico-Titanium-43-mm-Soldier.png?itok=1O9ZHuP7', 'bb-original-titanium-ceramic': 'https://www.hublot.com/sites/default/files/styles/watch_item_desktop_1x_scale_no_crop_600_6000_/public/2026-01/Big-Bang-Original-Unico-Titanium-Ceramic-43-mm-Soldier.png?itok=pxMh47pH', 'bb-original-king-gold': 'https://www.hublot.com/sites/default/files/styles/watch_item_desktop_1x_scale_no_crop_600_6000_/public/2026-01/Big-Bang-Original-Unico-King-Gold-Ceramic-43-mm-Soldier.png?itok=FdLdvA9F', 'bb-original-black-magic': 'https://www.hublot.com/sites/default/files/styles/watch_item_desktop_1x_scale_no_crop_600_6000_/public/2026-01/Big-Bang-Original-Unico-Black-Magic-43-mm-Soldier.png?itok=VNheq-YQ', 'bb-original-coal-blue': 'https://www.hublot.com/sites/default/files/styles/watch_item_desktop_1x_scale_no_crop_600_6000_/public/2026-01/Big-Bang-Original-Unico-Coal-Blue-43-mm-Soldier.png?itok=m5jhSv6e'}


# Páginas oficiales individuales para los 52 modelos del catálogo local.
# Las imágenes se extraen exclusivamente de la ficha individual correspondiente;
# no se reutiliza la foto de otro reloj si una referencia no existe en la web oficial.
HUBLOT_PRODUCT_PAGES = {
    "bb-original-red": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-soft-touch-all-red-43-mm",
    "bb-original-black": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-soft-touch-all-black-43-mm",
    "bb-original-titanium": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-titanium-43-mm",
    "bb-original-titanium-ceramic": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-titanium-ceramic-43-mm",
    "bb-original-king-gold": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-king-gold-ceramic-43-mm",
    "bb-original-black-magic": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-black-magic-43-mm",
    "bb-original-coal-blue": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-titanium-coal-blue-43-mm",
    "bb-reloaded-uefa": "https://www.hublot.com/en-us/watches/big-bang/big-bang-reloaded-uefa-champions-league-titanium-ceramic-44-mm",
    "bb-sapphire-sky": "https://www.hublot.com/en-us/watches/big-bang/big-bang-sapphire-sky-blue-44-mm",
    "bb-summer-42": "https://www.hublot.com/en-us/watches/big-bang/big-bang-summer-multi-colored-ceramic-42-mm",
    "bb-summer-44": "https://www.hublot.com/en-us/watches/big-bang/big-bang-summer-multi-colored-ceramic-44-mm",
    "bb-peach-42": "https://www.hublot.com/en-us/watches/big-bang/big-bang-titanium-peach-ceramic-42-mm",
    "bb-peach-33": "https://www.hublot.com/en-us/watches/big-bang/big-bang-peach-ceramic-33-mm",
    "bb-petrol-33": "https://www.hublot.com/en-us/watches/big-bang/big-bang-petrol-blue-ceramic-33-mm",
    "bb-mint-33": "https://www.hublot.com/en-us/watches/big-bang/big-bang-mint-green-ceramic-33-mm",
    "bb-unico-grey": "https://www.hublot.com/en-us/watches/big-bang/big-bang-unico-essential-grey-42-mm",
    "bb-magic-gold": "https://www.hublot.com/en-us/watches/big-bang/big-bang-reloaded-magic-gold-44-mm",
    "bb-king-gold": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-king-gold-43-mm",
    "bb-unico-titanium": "https://www.hublot.com/en-us/watches/big-bang/big-bang-unico-titanium-42-mm",
    "square-unico-titanium": "https://www.hublot.com/en-us/watches/square-bang/square-bang-unico-titanium-42-mm",
    "square-unico-ceramic": "https://www.hublot.com/en-us/watches/square-bang/square-bang-unico-titanium-ceramic-42-mm",
    "square-king-gold": "https://www.hublot.com/en-us/watches/square-bang/square-bang-unico-king-gold-42-mm",
    "square-black-magic": "https://www.hublot.com/en-us/watches/square-bang/square-bang-unico-black-magic-42-mm",
    "classic-original-titanium": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-original-titanium-42-mm",
    "classic-original-black": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-original-black-magic-42-mm",
    "classic-titanium": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-titanium-42-mm",
    "classic-blue": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-titanium-blue-42-mm",
    "classic-king-gold": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-king-gold-42-mm",
    "classic-black-magic": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-black-magic-42-mm",
    "classic-chrono-ti": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-chronograph-titanium-42-mm",
    "classic-chrono-gold": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-chronograph-king-gold-42-mm",
    "classic-chrono-black": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-chronograph-black-magic-42-mm",
    "classic-aero-ti": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-aerofusion-titanium-45-mm",
    "classic-aero-black": "https://www.hublot.com/en-us/watches/classic-fusion/classic-fusion-aerofusion-black-magic-45-mm",
    "spirit-ti": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-titanium-42-mm",
    "spirit-ti-ceramic": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-titanium-ceramic-42-mm",
    "spirit-king-gold": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-king-gold-42-mm",
    "spirit-king-ceramic": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-king-gold-ceramic-42-mm",
    "spirit-black-magic": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-black-magic-42-mm",
    "spirit-taupe": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-essential-taupe-42-mm",
    "spirit-impact-black": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-impact-all-black-42-mm",
    "spirit-impact-sapphire": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-impact-sapphire-42-mm",
    "spirit-sapphire-blue": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-sapphire-blue-42-mm",
    "spirit-coal-blue": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-titanium-coal-blue-42-mm",
    "spirit-white": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-titanium-white-42-mm",
    "spirit-meca-ti": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-meca-10-titanium-45-mm",
    "spirit-meca-gold": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-meca-10-king-gold-45-mm",
    "spirit-tourbillon-black": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-tourbillon-5-day-power-reserve-black-magic-42-mm",
    "spirit-tourbillon-red": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-tourbillon-5-day-power-reserve-red-magic-42-mm",
    "spirit-tourbillon-blue": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-tourbillon-5-day-power-reserve-sky-blue-ceramic-42-mm",
    "spirit-tourbillon-yellow": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-tourbillon-5-day-power-reserve-yellow-magic-42-mm",
    "spirit-tourbillon-sapphire": "https://www.hublot.com/en-us/watches/spirit-of-big-bang/spirit-of-big-bang-tourbillon-5-day-power-reserve-black-sapphire-42-mm",
}

HUBLOT_IMAGE_CACHE = {}
HUBLOT_IMAGE_SEMAPHORE = asyncio.Semaphore(8)

async def cached_hublot_image(product_id: str) -> str:
    """Obtiene y guarda en memoria la imagen publicada en la ficha oficial exacta."""
    if product_id in HUBLOT_IMAGE_CACHE:
        return HUBLOT_IMAGE_CACHE[product_id]
    product_url = HUBLOT_PRODUCT_PAGES.get(product_id)
    if not product_url:
        return ""
    async with HUBLOT_IMAGE_SEMAPHORE:
        if product_id not in HUBLOT_IMAGE_CACHE:
            HUBLOT_IMAGE_CACHE[product_id] = await official_product_image(product_url, "hublot.com")
    return HUBLOT_IMAGE_CACHE[product_id]

async def official_product_image(product_url: str, allowed_domain: str) -> str:
    """Extract the main image referenced by an exact official product page.

    The page host must be the retailer's official domain. Its own HTML may point
    at a retailer-selected CDN, so the image host is not incorrectly restricted
    to a short hard-coded CDN list.
    """
    try:
        parsed = urlparse(product_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not (host == allowed_domain or host.endswith("." + allowed_domain)):
            return ""
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=True, headers=headers) as client:
            response = await client.get(product_url)
            final_host = (urlparse(str(response.url)).hostname or "").lower().rstrip(".")
            if response.status_code != 200 or not (final_host == allowed_domain or final_host.endswith("." + allowed_domain)):
                return ""
            source = response.text[:3_000_000]
        source = unescape(source).replace('\\/', '/')
        candidates = []
        # Parse metadata tags without assuming attribute order.
        for tag in re.findall(r'<meta\b[^>]*>', source, re.I):
            prop = re.search(r'\b(?:property|name)=["\']([^"\']+)', tag, re.I)
            content = re.search(r'\bcontent=["\']([^"\']+)', tag, re.I)
            if prop and content and prop.group(1).lower() in {
                'og:image', 'og:image:url', 'twitter:image', 'twitter:image:src',
            }:
                candidates.append(content.group(1).strip())
        # Structured product data is often more reliable than a theme-specific img selector.
        for match in re.finditer(r'["\']image["\']\s*:\s*(\[[^\]]{1,5000}\]|["\'][^"\']+["\'])', source, re.I):
            raw = match.group(1)
            candidates.extend(re.findall(r'["\'](https?:[^"\']+)["\']', raw))
            if raw.startswith(('"', "'")):
                candidates.append(raw[1:-1])
        # Product image markup; support lazy loading and srcset.
        for tag in re.findall(r'<img\b[^>]*>', source, re.I):
            alt = re.search(r'\balt=["\']([^"\']*)', tag, re.I)
            src = re.search(r'\b(?:data-zoom-image|data-image-src|data-src|data-lazyload|src)=["\']([^"\']+)', tag, re.I)
            if src:
                value = src.group(1).strip()
                if not value.startswith('data:') and not any(x in value.lower() for x in ('logo', 'sprite', 'icon', 'placeholder')):
                    # Prioritize product images rather than footer/recommendation images.
                    candidates.append(value)
            srcset = re.search(r'\bsrcset=["\']([^"\']+)', tag, re.I)
            if srcset:
                options = [part.strip().split()[0] for part in srcset.group(1).split(',') if part.strip()]
                if options:
                    candidates.append(options[-1])
        for candidate in candidates:
            candidate = unescape(candidate.strip()).replace('\\/', '/')
            if candidate.startswith('//'):
                candidate = 'https:' + candidate
            image_url = urljoin(str(response.url), candidate)
            image_parsed = urlparse(image_url)
            # Accept a CDN only when its URL was explicitly referenced by the verified official page.
            if image_parsed.scheme == 'https' and image_parsed.hostname and image_parsed.path and not image_parsed.path.lower().endswith(('.svg', '.ico')):
                return image_url
    except Exception as exc:
        log.info("No se pudo obtener imagen oficial desde %s: %s", product_url, type(exc).__name__)
    return ""


@app.post("/api/search")
async def search(body: SearchBody, request: Request):
    tg_id = get_auth(request)
    platform = body.platform.lower().strip()
    query = body.query.strip()
    if platform in DISABLED_STORES:
        raise HTTPException(403, "Esta tienda está deshabilitada temporalmente en ProEshop.")

    if platform not in PLATFORMS:
        raise HTTPException(400, "Tienda no admitida.")
    if not query:
        raise HTTPException(400, "Escribe el nombre de un producto.")

    audit(tg_id, "search", f"platform={platform}; query_length={len(query)}")
    store = PLATFORMS[platform]
    search_url = store["url"].format(q=quote_plus(query))
    # HUBLOT local catalog fallback is served by the API too, so an older/cached
    # app.js still receives actual results instead of an empty list.
    if platform == "hublot":
        q = query.casefold().strip()
        broad_terms = {"hublot", "watch", "watches", "reloj", "relojes", "todos", "todo", "all", "*"}
        matches = [p for p in HUBLOT_CATALOG if q in broad_terms or any(
            q in str(p.get(field, "")).casefold()
            for field in ("name", "collection", "desc", "id")
        )]
        # If a phrase does not match a model exactly, return the catalogue rather
        # than a blank screen; the user can then filter/sort in the shared results UI.
        if not matches:
            matches = HUBLOT_CATALOG
        requested_matches = matches[:52]
        results = []
        for p in requested_matches:
            # Use a verified product page when known; otherwise open the official
            # Hublot collection matching the model instead of sending every item to /watches.
            pid = p.get("id", "")
            exact_hublot_pages = {
                "bb-original-red": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-soft-touch-all-red-43-mm",
                "bb-original-black": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-soft-touch-all-black-43-mm",
                "bb-original-titanium": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-titanium-43-mm",
                "bb-original-titanium-ceramic": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-titanium-ceramic-43-mm",
                "bb-original-king-gold": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-king-gold-ceramic-43-mm",
                "bb-original-black-magic": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-black-magic-43-mm",
                "bb-original-coal-blue": "https://www.hublot.com/en-us/watches/big-bang/big-bang-original-unico-titanium-coal-blue-43-mm",
            }
            if pid in HUBLOT_PRODUCT_PAGES:
                product_url = HUBLOT_PRODUCT_PAGES[pid]
            elif pid in exact_hublot_pages:
                product_url = exact_hublot_pages[pid]
            elif str(p.get("collection", "")).casefold() == "classic fusion":
                product_url = "https://www.hublot.com/en-us/find-your-hublot/classic-fusion"
            elif str(p.get("collection", "")).casefold() == "spirit of big bang":
                product_url = "https://www.hublot.com/en-us/find-your-hublot/spirit-of-big-bang"
            elif pid.startswith("square-"):
                product_url = "https://www.hublot.com/en-us/find-your-hublot/square-bang"
            elif str(p.get("collection", "")).casefold() == "big bang":
                product_url = "https://www.hublot.com/en-us/find-your-hublot/big-bang/big-bang-original"
            else:
                product_url = "https://www.hublot.com/en-us/find-your-hublot"
            # Only assign a photo from an exact model page; never borrow a different model's image.
            fallback_image = HUBLOT_LOCAL_IMAGES.get(pid, "/static/catalog_images/hublot_01.jpg")
            image_url = HUBLOT_OFFICIAL_IMAGES.get(pid, "") or HUBLOT_IMAGE_CACHE.get(pid, "") or fallback_image
            results.append({"title": p["name"], "price": round(float(p["price"]), 2),
                            "currency": "USD", "url": product_url, "image": image_url,
                            "fallback_image": fallback_image,
                            "source": "HUBLOT.com · foto oficial si está disponible; respaldo local de catálogo",
                            "collection": p.get("collection", ""), "description": p.get("desc", "")})
        return {
            "platform": "hublot", "label": "HUBLOT", "query": query,
            "search_url": search_url, "live_results": results,
            "notice": "Catálogo local ilustrativo de ProEshop. Precios e imágenes no son cotización oficial; el 50% de descuento es simulado."
        }
    if platform == "jewelers":
        q = query.casefold().strip()
        broad_terms = {"electronics", "electronic", "todos", "todo", "all", "*", "jewelers", "jewelers toy store", "joyeria", "joyería"}
        matches = [p for p in JEWELERS_CATALOG if q in broad_terms or any(q in str(p.get(field, "")).casefold() for field in ("name", "desc", "id"))]
        if not matches:
            matches = JEWELERS_CATALOG
        results = []
        for p in matches:
            fallback_image = JEWELERS_LOCAL_IMAGES.get(p["id"], "/static/catalog_images/jewelers_01.jpg")
            results.append({"title": p["name"], "price": round(float(p["price"]), 2),
                            "currency": "USD", "url": p["url"], "image": fallback_image,
                            "fallback_image": fallback_image,
                            "source": "JewelersToyStore.com · imagen ilustrativa local; consulta la ficha del proveedor",
                            "description": p["desc"]})
        return {"platform":"jewelers", "label":"Jewelers Toy Store", "query":query, "search_url":search_url,
                "live_results":results, "notice":"Las imágenes de respaldo son ilustrativas porque el proveedor bloquea la consulta automática (HTTP 403). Verifica el producto, precio y disponibilidad en la ficha del proveedor."}
    if platform == "rolex":
        q = query.casefold().strip()
        broad_terms = {"rolex", "reloj", "relojes", "watch", "watches", "todos", "todo", "all", "destacados", "*"}
        matches = [p for p in ROLEX_CATALOG if q in broad_terms or any(q in str(p.get(field, "")).casefold() for field in ("name", "desc", "id"))]
        if not matches:
            matches = ROLEX_CATALOG
        rolex_collections = {
            "land-dweller": "https://www.rolex.com/watches/land-dweller",
            "datejust": "https://www.rolex.com/watches/datejust",
            "lady-datejust": "https://www.rolex.com/watches/lady-datejust",
            "oyster-perpetual": "https://www.rolex.com/watches/oyster-perpetual",
            "cosmograph-daytona": "https://www.rolex.com/watches/cosmograph-daytona",
            "submariner": "https://www.rolex.com/watches/submariner",
            "gmt-master-ii": "https://www.rolex.com/watches/gmt-master-ii",
            "explorer": "https://www.rolex.com/watches/explorer",
            "air-king": "https://www.rolex.com/watches/air-king",
            "sea-dweller": "https://www.rolex.com/watches/sea-dweller",
            "deepsea": "https://www.rolex.com/watches/deepsea",
            "sky-dweller": "https://www.rolex.com/watches/sky-dweller",
            "yacht-master": "https://www.rolex.com/watches/yacht-master",
            "day-date": "https://www.rolex.com/watches/day-date",
            "1908": "https://www.rolex.com/watches/1908",
        }
        def rolex_product_url(product):
            pid = str(product.get("id", ""))
            # Prefer the most specific prefix; links go to the official collection for that model.
            for prefix in sorted(rolex_collections, key=len, reverse=True):
                if pid == prefix or pid.startswith(prefix + "-"):
                    return rolex_collections[prefix]
            return "https://www.rolex.com/watches"
        results = []
        for p in matches:
            fallback_image = ROLEX_LOCAL_IMAGES.get(p["id"], "/static/catalog_images/rolex_01.jpg")
            results.append({"title": p["name"], "price": round(float(p["price"])*0.50, 2),
                            "list_price": round(float(p["price"]), 2), "discount_percent": 50, "currency":"USD",
                            "url":p.get("url") or rolex_product_url(p), "image":p.get("img") or fallback_image,
                            "fallback_image":fallback_image, "source":"Rolex.com · precio de referencia; oferta ProEshop no oficial",
                            "description":p["desc"]})
        return {"platform":"rolex", "label":"Rolex · modelos destacados", "query":query, "search_url":"https://www.rolex.com/es/watches/find-rolex?group=0", "live_results":results, "notice":"Catálogo de 40 referencias. Precios de referencia publicados en el catálogo oficial de EE. UU.; el 50% es una promoción de ProEshop, no una oferta oficial de Rolex. Las fotos oficiales se intentan cargar primero y existe respaldo local si el CDN no responde."}

    domains = {"amazon": "amazon.com", "target": "target.com", "walmart": "walmart.com"}
    domain = domains[platform]

    def is_store_url(raw_url):
        try:
            parsed = urlparse(str(raw_url or ""))
            host = (parsed.hostname or "").lower()
            return parsed.scheme == "https" and (host == domain or host.endswith("." + domain))
        except (ValueError, TypeError):
            return False

    def source_matches(source):
        normalized = re.sub(r"[^a-z0-9]", "", str(source or "").lower())
        aliases = {
            "amazon": ("amazon", "amazoncom"),
            "target": ("target", "targetcom"),
            "walmart": ("walmart", "walmartcom"),
        }[platform]
        return any(alias in normalized for alias in aliases)

    def extract_price(item):
        for candidate in (item.get("extracted_price"), item.get("price")):
            if isinstance(candidate, dict):
                candidate = candidate.get("value") or candidate.get("extracted_price")
            if isinstance(candidate, (int, float)):
                price = float(candidate)
                if 0 < price <= 10_000_000:
                    return round(price, 2)
            if isinstance(candidate, str):
                match = re.search(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)", candidate)
                if match:
                    try:
                        price = float(match.group(1).replace(",", ""))
                        if 0 < price <= 10_000_000:
                            return round(price, 2)
                    except ValueError:
                        pass
        return None

    if not SERPAPI_KEY:
        return {"platform": platform, "label": store["label"], "query": query,
                "search_url": search_url, "live_results": [],
                "notice": "Configura SERPAPI_KEY en Railway para consultar productos y precios."}

    # Cache results briefly so repeating the same search does not consume another API call.
    cache_key = (platform, query.casefold())
    cached = _SEARCH_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < 300:
        result = dict(cached[1])
        result["cached"] = True
        return result

    try:
        # One broad Shopping request is much faster and more reliable than using
        # site:domain inside Google Shopping, which often returns no results.
        async with httpx.AsyncClient(timeout=httpx.Timeout(18.0, connect=5.0)) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_shopping",
                    "q": query,
                    "gl": "us",
                    "hl": "en",
                    "api_key": SERPAPI_KEY,
                },
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            log.warning("SerpApi Shopping error platform=%s error=%s", platform, str(payload["error"])[:180])
            return {"platform": platform, "label": store["label"], "query": query,
                    "search_url": search_url, "live_results": [],
                    "notice": "El proveedor no devolvió resultados para esta búsqueda. Prueba con un término más específico o abre la tienda oficial."}

        items = payload.get("shopping_results") or payload.get("inline_shopping_results") or []
        results, seen = [], set()
        for item in items[:80]:
            source = str(item.get("source") or item.get("seller") or item.get("merchant") or "").strip()
            # The merchant label must identify the selected retailer. Other shops are excluded.
            if not source_matches(source):
                continue
            price = extract_price(item)
            if price is None:
                continue
            title = str(item.get("title") or "Producto")[:180]
            raw_link = item.get("link") or item.get("product_link") or ""
            # Shopping often supplies a Google product-page URL rather than a merchant URL.
            # In that case, link to a search for this exact title on the official retailer site.
            product_url = raw_link if is_store_url(raw_link) else store["url"].format(q=quote_plus(title))
            dedupe_key = (re.sub(r"\W+", " ", title.lower()).strip(), price)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            results.append({"title": title, "price": price, "currency": "USD", "url": product_url,
                            "image": str(item.get("thumbnail") or ""), "source": store["label"]})
            if len(results) >= 12:
                break

        notice = (f"Se muestran productos atribuidos a {store['label']}. Los enlaces abren la tienda oficial; cuando Google no entrega un enlace directo al producto, se abre una búsqueda por su título. Confirma disponibilidad y precio final en la tienda."
                  if results else f"No se encontraron resultados atribuidos a {store['label']} para esta consulta. Prueba otro término o abre la tienda oficial.")
        result = {"platform": platform, "label": store["label"], "query": query,
                  "search_url": search_url, "live_results": results, "notice": notice}
        _SEARCH_CACHE[cache_key] = (now, result)
        # Keep the in-memory cache bounded.
        if len(_SEARCH_CACHE) > 250:
            for key in list(_SEARCH_CACHE)[:100]:
                _SEARCH_CACHE.pop(key, None)
        log.info("SEARCH COMPLETE platform=%s returned=%s shopping_items=%s", platform, len(results), len(items))
        return result
    except httpx.TimeoutException:
        log.warning("SERPAPI TIMEOUT platform=%s", platform)
        return {"platform": platform, "label": store["label"], "query": query,
                "search_url": search_url, "live_results": [],
                "notice": "La búsqueda agotó el tiempo de espera. Intenta de nuevo o abre la tienda oficial."}
    except httpx.HTTPStatusError as exc:
        log.warning("SERPAPI HTTP ERROR platform=%s status=%s", platform, exc.response.status_code)
        raise HTTPException(502, "El proveedor de búsqueda devolvió un error HTTP.")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("SEARCH ERROR platform=%s type=%s", platform, type(exc).__name__)
        raise HTTPException(502, "No se pudo procesar la búsqueda. Intenta nuevamente.")


@app.get("/api/state")
async def state(request: Request):
    tg_id = get_auth(request)
    expire_stale_crypto_payments()
    with conn() as db:
        balance = db.execute("SELECT amount FROM balances WHERE telegram_id=?", (tg_id,)).fetchone()
        cart = [dict(x) for x in db.execute("SELECT * FROM carts WHERE telegram_id=? ORDER BY id DESC", (tg_id,)).fetchall()]
        history = db.execute("SELECT * FROM purchases WHERE telegram_id=? ORDER BY id DESC LIMIT 50", (tg_id,)).fetchall()
        orders = db.execute("""SELECT o.*, cp.status AS crypto_status, cp.requested_amount AS crypto_amount,
                    cp.created_at AS crypto_created_at, cp.receiving_address AS crypto_address,
                    cp.network AS crypto_network, cp.token_symbol AS crypto_token
                    FROM orders o LEFT JOIN crypto_payments cp ON cp.order_ref=o.order_ref
                    WHERE o.telegram_id=? ORDER BY o.created_at DESC LIMIT 50""", (tg_id,)).fetchall()
        order_events = db.execute("SELECT e.* FROM order_events e JOIN orders o ON o.order_ref=e.order_ref WHERE o.telegram_id=? ORDER BY e.created_at ASC, e.id ASC", (tg_id,)).fetchall()
        store_orders = db.execute("SELECT so.*, o.created_at AS parent_created_at FROM store_orders so JOIN orders o ON o.order_ref=so.order_ref WHERE o.telegram_id=? ORDER BY so.created_at DESC, so.store_label ASC", (tg_id,)).fetchall()
        store_order_events = db.execute("SELECT e.* FROM store_order_events e JOIN store_orders so ON so.store_order_ref=e.store_order_ref JOIN orders o ON o.order_ref=so.order_ref WHERE o.telegram_id=? ORDER BY e.created_at ASC, e.id ASC", (tg_id,)).fetchall()
    # Backfill local image paths for older cart rows; avoids external-site 403 errors in cart/checkout.
    for item in cart:
        platform = str(item.get("platform", "")).lower()
        if platform == "hublot":
            match = next((p for p in HUBLOT_CATALOG if p.get("name", "").casefold() == str(item.get("title", "")).casefold()), None)
            fallback = HUBLOT_LOCAL_IMAGES.get(match.get("id", ""), "/static/catalog_images/hublot_01.jpg") if match else "/static/catalog_images/hublot_01.jpg"
        elif platform == "rolex":
            match = next((p for p in ROLEX_CATALOG if p.get("name", "").casefold() == str(item.get("title", "")).casefold()), None)
            fallback = ROLEX_LOCAL_IMAGES.get(match.get("id", ""), "/static/catalog_images/rolex_01.jpg") if match else "/static/catalog_images/rolex_01.jpg"
        elif platform == "jewelers":
            match = next((p for p in JEWELERS_CATALOG if p.get("name", "").casefold() == str(item.get("title", "")).casefold()), None)
            fallback = JEWELERS_LOCAL_IMAGES.get(match.get("id", ""), "/static/catalog_images/jewelers_01.jpg") if match else "/static/catalog_images/jewelers_01.jpg"
        else:
            continue
        if not str(item.get("image", "")).startswith("/static/catalog_images/"):
            item["image"] = fallback
            with conn() as db:
                db.execute("UPDATE carts SET image=? WHERE id=? AND telegram_id=?", (fallback, item["id"], tg_id))
    return {
        "balance": balance["amount"] if balance else str(INITIAL_BALANCE),
        "currency": CURRENCY,
        "tax_rate": str(ESTIMATED_TAX_RATE),
        "shipping_fee": str(ESTIMATED_SHIPPING_FEE),
        "cart": cart,
        "history": [dict(x) for x in history],
        "orders": [dict(x) for x in orders],
        "order_events": [dict(x) for x in order_events],
        "store_orders": [dict(x) for x in store_orders],
        "store_order_events": [dict(x) for x in store_order_events],
        "platforms": [{"id": k, "label": v["label"]} for k,v in PLATFORMS.items()]
    }


@app.post("/api/cart")
async def add_cart(body: AddBody, request: Request):
    tg_id = get_auth(request)
    if body.platform.lower() not in PLATFORMS:
        raise HTTPException(400, "Tienda no admitida.")
    if body.platform.lower() in DISABLED_STORES:
        raise HTTPException(403, "Esta tienda está deshabilitada temporalmente en ProEshop.")
    if body.currency.upper() != CURRENCY.upper():
        raise HTTPException(400, f"El saldo ficticio está denominado en {CURRENCY}; usa esa misma moneda.")
    try:
        price = Decimal(body.price).quantize(Decimal("0.01"))
        if not price.is_finite() or price <= 0 or price > Decimal("10000000"):
            raise InvalidOperation()
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "Introduce un precio válido mayor que cero.")
    platform = body.platform.lower().strip()
    # Oferta simulada exclusiva de HUBLOT: se aplica en servidor para que
    # el subtotal, los impuestos, el saldo ficticio y el historial usen el precio rebajado.
    if platform == "hublot":
        matching = next((p for p in HUBLOT_CATALOG if p["name"].casefold() == body.title.strip().casefold()), None)
        if matching:
            price = (Decimal(str(matching["price"])) * Decimal("0.50")).quantize(Decimal("0.01"))
    elif platform == "jewelers":
        matching = next((p for p in JEWELERS_CATALOG if p["name"].casefold() == body.title.strip().casefold()), None)
        if matching:
            price = (Decimal(str(matching["price"])) * Decimal("0.50")).quantize(Decimal("0.01"))
    elif platform == "rolex":
        matching = next((p for p in ROLEX_CATALOG if p["name"] == body.title.strip()), None)
        if matching and matching["discount"] == 50:
            # Calculate the ProEshop 50% promotional price server-side.
            price = (Decimal(str(matching["price"])) * Decimal("0.50")).quantize(Decimal("0.01"))
        elif matching:
            price = Decimal(str(matching["price"])).quantize(Decimal("0.01"))
    parsed = urlparse(body.url)
    host = (parsed.hostname or "").lower().rstrip(".")
    allowed_domains = {
        "amazon": ("amazon.com",),
        "target": ("target.com",),
        "walmart": ("walmart.com",),
        "hublot": ("hublot.com",),
        "jewelers": ("jewelerstoystore.com",),
        "rolex": ("rolex.com",),
    }
    if (
        parsed.scheme.lower() != "https"
        or platform not in allowed_domains
        or not host
        or not any(
            host == domain or host.endswith("." + domain)
            for domain in allowed_domains[platform]
        )
    ):
        raise HTTPException(
            400,
            "El enlace debe pertenecer al dominio oficial de la tienda seleccionada.",
        )
    image_url = ""
    if body.image:
        if body.image.startswith("/static/catalog_images/") and ".." not in body.image:
            image_url = body.image[:2000]
        else:
            image_parsed = urlparse(body.image)
            image_host = (image_parsed.hostname or "").lower().rstrip(".")
            image_domains = set(allowed_domains[platform]) | {"cdn11.bigcommerce.com", "cdn.shopify.com", "images.squarespace-cdn.com", "images.ctfassets.net", "media.hublot.com", "assets.hublot.com", "media.rolex.com"}
            if image_parsed.scheme.lower() == "https" and any(
                image_host == domain or image_host.endswith("." + domain)
                for domain in image_domains
            ):
                image_url = body.image[:2000]
    with conn() as db:
        db.execute("""INSERT INTO carts(telegram_id,platform,title,price,currency,url,image,qty,created_at)
                      VALUES(?,?,?,?,?,?,?,1,?)""",
                   (tg_id, body.platform.lower(), body.title.strip(), str(price),
                    body.currency.upper(), body.url, image_url, now_iso()))
    audit(tg_id, "cart_add", f"platform={body.platform.lower()}; price={price}")
    return {"ok": True}


@app.put("/api/cart/{item_id}")
async def update_cart(item_id: int, body: QtyBody, request: Request):
    tg_id = get_auth(request)
    with conn() as db:
        cur = db.execute("UPDATE carts SET qty=? WHERE id=? AND telegram_id=?", (body.qty, item_id, tg_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Artículo no encontrado en tu carrito.")
    audit(tg_id, "cart_qty", f"item={item_id}; qty={body.qty}")
    return {"ok": True, "qty": body.qty}


@app.delete("/api/cart/{item_id}")
async def remove_cart(item_id: int, request: Request):
    tg_id = get_auth(request)
    with conn() as db:
        cur = db.execute("DELETE FROM carts WHERE id=? AND telegram_id=?", (item_id, tg_id))
    if cur.rowcount: audit(tg_id, "cart_remove", f"item={item_id}")
    return {"ok": True}


@app.delete("/api/cart")
async def clear_cart(request: Request):
    tg_id = get_auth(request)
    with conn() as db:
        db.execute("DELETE FROM carts WHERE telegram_id=?", (tg_id,))
    return {"ok": True}


@app.get("/api/notifications")
async def get_notifications(request: Request):
    tg_id = get_auth(request)
    with conn() as db:
        row = db.execute("SELECT * FROM notification_preferences WHERE telegram_id=?", (tg_id,)).fetchone()
    return {"order_updates": bool(row["order_updates"]) if row else True,
            "security_alerts": bool(row["security_alerts"]) if row else True,
            "telegram_configured": bool(BOT_TOKEN)}


@app.post("/api/notifications")
async def set_notifications(body: NotificationBody, request: Request):
    tg_id = get_auth(request)
    with conn() as db:
        db.execute("""INSERT INTO notification_preferences(telegram_id,order_updates,security_alerts,updated_at)
                      VALUES(?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET
                      order_updates=excluded.order_updates, security_alerts=excluded.security_alerts,
                      updated_at=excluded.updated_at""",
                   (tg_id, int(body.order_updates), int(body.security_alerts), now_iso()))
    audit(tg_id, "notification_preferences", f"orders={int(body.order_updates)}; security={int(body.security_alerts)}")
    return {"ok": True, "order_updates": body.order_updates, "security_alerts": body.security_alerts,
            "telegram_configured": bool(BOT_TOKEN)}


@app.get("/api/admin/orders")
async def admin_orders(request: Request, status: str = ""):
    if not ADMIN_API_KEY:
        raise HTTPException(503, "Configura ADMIN_API_KEY en Railway.")
    if not hmac.compare_digest(request.headers.get("X-Admin-Key", ""), ADMIN_API_KEY):
        raise HTTPException(403, "Clave administrativa no válida.")
    with conn() as db:
        # New checkouts are listed as independent per-store orders. Legacy orders remain visible.
        query = """SELECT so.store_order_ref AS order_ref, so.order_ref AS parent_order_ref,
                   o.telegram_id, so.total, so.currency, so.status, so.created_at, so.updated_at,
                   COALESCE(NULLIF(so.customer_email,''),o.customer_email,'') AS customer_email,
                   so.platform, so.store_label, so.subtotal, so.tax, so.shipping
                   FROM store_orders so JOIN orders o ON o.order_ref=so.order_ref"""
        params = ()
        if status:
            query += " WHERE so.status=?"; params = (status,)
        query += " ORDER BY so.created_at DESC LIMIT 100"
        stores = [dict(r) for r in db.execute(query, params).fetchall()]
        legacy_query = "SELECT order_ref,telegram_id,total,currency,status,created_at,updated_at,customer_email FROM orders WHERE NOT EXISTS (SELECT 1 FROM store_orders so WHERE so.order_ref=orders.order_ref)"
        legacy_params = ()
        if status:
            legacy_query += " AND status=?"; legacy_params = (status,)
        legacy_query += " ORDER BY created_at DESC LIMIT 100"
        legacy = [dict(r) for r in db.execute(legacy_query, legacy_params).fetchall()]
    return {"orders": stores + legacy, "statuses": ORDER_STATUS_LABELS, "transitions": {k: sorted(v) for k, v in ORDER_TRANSITIONS.items()},
            "note": "Los pedidos nuevos se gestionan por tienda usando order_ref (referencia de tienda)."}


class OrderStatusBody(BaseModel):
    status: str = Field(min_length=3, max_length=32)
    detail: str = Field(default="", max_length=500)


@app.post("/api/admin/orders/{order_ref}/status")
async def admin_update_order_status(order_ref: str, body: OrderStatusBody, request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(503, "Configura ADMIN_API_KEY en Railway.")
    if not hmac.compare_digest(request.headers.get("X-Admin-Key", ""), ADMIN_API_KEY):
        raise HTTPException(403, "Clave administrativa no válida.")
    new_status = body.status.strip().lower()
    if new_status not in ORDER_STATUS_LABELS:
        raise HTTPException(400, "Estado no reconocido.")
    with conn() as db:
        store_order = db.execute("SELECT * FROM store_orders WHERE store_order_ref=?", (order_ref,)).fetchone()
        if store_order:
            old_status = store_order["status"]
            if old_status == new_status:
                return {"ok": True, "unchanged": True, "status": new_status, "email_sent": False, "store_order_ref": order_ref}
            if new_status not in ORDER_TRANSITIONS.get(old_status, set()):
                raise HTTPException(409, f"Transición no permitida: {ORDER_STATUS_LABELS.get(old_status, old_status)} → {ORDER_STATUS_LABELS[new_status]}.")
            now = now_iso()
            detail = body.detail.strip() or f"Estado actualizado para {store_order['store_label']}: {ORDER_STATUS_LABELS[new_status]}"
            db.execute("UPDATE store_orders SET status=?,updated_at=? WHERE store_order_ref=?", (new_status, now, order_ref))
            db.execute("INSERT INTO order_events(order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)",
                       (store_order["order_ref"], new_status, f"{store_order['store_label']}: {ORDER_STATUS_LABELS[new_status]}", detail, now))
            db.execute("INSERT INTO store_order_events(store_order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)",
                       (order_ref, new_status, ORDER_STATUS_LABELS[new_status], detail, now))
            email_order_ref = order_ref
            email_total, email_currency, recipient = store_order["total"], store_order["currency"], store_order["customer_email"]
            parent_ref, store_label = store_order["order_ref"], store_order["store_label"]
        else:
            # Backward compatibility for historical single-order references.
            order = db.execute("SELECT * FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
            if not order: raise HTTPException(404, "Pedido no encontrado.")
            old_status = order["status"]
            if old_status == new_status:
                return {"ok": True, "unchanged": True, "status": new_status, "email_sent": False}
            if new_status not in ORDER_TRANSITIONS.get(old_status, set()):
                raise HTTPException(409, f"Transición no permitida: {ORDER_STATUS_LABELS.get(old_status, old_status)} → {ORDER_STATUS_LABELS[new_status]}.")
            now = now_iso(); detail = body.detail.strip() or f"Estado actualizado por administrador: {ORDER_STATUS_LABELS[new_status]}"
            db.execute("UPDATE orders SET status=?,updated_at=? WHERE order_ref=?", (new_status, now, order_ref))
            db.execute("INSERT INTO order_events(order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)",
                       (order_ref, new_status, ORDER_STATUS_LABELS[new_status], detail, now))
            email_order_ref, email_total, email_currency, recipient = order_ref, order["total"], order["currency"], order["customer_email"]
            parent_ref, store_label = order_ref, "ProEshop"
    audit("admin", "order_status_change", f"order={order_ref}; from={old_status}; to={new_status}")
    email_result = (enqueue_and_send_store_order_email(email_order_ref, new_status, recipient, email_total, email_currency,
        f"Tienda: {store_label}. {detail}") if store_order else enqueue_and_send_order_email(email_order_ref, new_status, recipient, email_total, email_currency, detail))
    return {"ok": True, "order_ref": order_ref, "parent_order_ref": parent_ref, "store": store_label,
            "previous_status": old_status, "status": new_status, "status_label": ORDER_STATUS_LABELS[new_status],
            "email_sent": bool(email_result.get("sent")),
            "email_status": "sent" if email_result.get("sent") else email_result.get("reason", "not_configured")}


class AdminEmailBody(BaseModel):
    customer_email: str = Field(min_length=3, max_length=254)


@app.post("/api/admin/orders/{order_ref}/email")
async def admin_update_order_email(order_ref: str, body: AdminEmailBody, request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(503, "Configura ADMIN_API_KEY en Railway.")
    if not hmac.compare_digest(request.headers.get("X-Admin-Key", ""), ADMIN_API_KEY):
        raise HTTPException(403, "Clave administrativa no válida.")
    recipient = body.customer_email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        raise HTTPException(400, "Introduce un correo electrónico válido.")
    with conn() as db:
        store_order = db.execute("SELECT order_ref FROM store_orders WHERE store_order_ref=?", (order_ref,)).fetchone()
        if store_order:
            db.execute("UPDATE store_orders SET customer_email=? WHERE store_order_ref=?", (recipient, order_ref))
            # Also retain it on the parent order for backward compatibility.
            db.execute("UPDATE orders SET customer_email=? WHERE order_ref=? AND (customer_email='' OR customer_email IS NULL)", (recipient, store_order["order_ref"]))
            kind = "store_order_notifications"
            db.execute("UPDATE store_order_notifications SET recipient=?,status='pending',last_error='',updated_at=? WHERE store_order_ref=? AND status!='sent'", (recipient, now_iso(), order_ref))
        else:
            order = db.execute("SELECT order_ref FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
            if not order:
                raise HTTPException(404, "Pedido no encontrado.")
            db.execute("UPDATE orders SET customer_email=? WHERE order_ref=?", (recipient, order_ref))
            db.execute("UPDATE store_orders SET customer_email=? WHERE order_ref=?", (recipient, order_ref))
            db.execute("UPDATE order_notifications SET recipient=?,status='pending',last_error='',updated_at=? WHERE order_ref=? AND status!='sent'", (recipient, now_iso(), order_ref))
            kind = "order_notifications"
    audit("admin", "order_email_updated", f"order={order_ref}; recipient_domain={recipient.rsplit('@',1)[-1]}")
    return {"ok": True, "order_ref": order_ref, "email_updated": True, "message": "Correo guardado. Puedes pulsar Reintentar correo."}


@app.post("/api/admin/orders/{order_ref}/retry-email")
async def admin_retry_order_email(order_ref: str, request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(503, "Configura ADMIN_API_KEY en Railway.")
    if not hmac.compare_digest(request.headers.get("X-Admin-Key", ""), ADMIN_API_KEY):
        raise HTTPException(403, "Clave administrativa no válida.")
    with conn() as db:
        order = db.execute("SELECT * FROM store_orders WHERE store_order_ref=?", (order_ref,)).fetchone()
        if order:
            parent = db.execute("SELECT customer_email FROM orders WHERE order_ref=?", (order["order_ref"],)).fetchone()
            status = order["status"]
            recipient = (order["customer_email"] or (parent["customer_email"] if parent else "") or "").strip()
            total, currency = order["total"], order["currency"]
            store_label = order["store_label"]
        else:
            order = db.execute("SELECT * FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
            if not order: raise HTTPException(404, "Pedido no encontrado.")
            status, recipient, total, currency, store_label = order["status"], order["customer_email"], order["total"], order["currency"], "ProEshop"
        if not recipient:
            raise HTTPException(400, "Este pedido no tiene correo guardado. Introduce y guarda el correo en el panel administrativo antes de reintentar.")
        notification_table = "store_order_notifications" if db.execute("SELECT 1 FROM store_orders WHERE store_order_ref=?", (order_ref,)).fetchone() else "order_notifications"
        ref_column = "store_order_ref" if notification_table == "store_order_notifications" else "order_ref"
        event = db.execute(f"SELECT * FROM {notification_table} WHERE {ref_column}=? AND event_key=?", (order_ref, status)).fetchone()
        if event and event["status"] == "sent":
            return {"ok": True, "sent": True, "email_sent": True, "message": "El correo ya fue aceptado por el proveedor."}
        if not event:
            now = now_iso()
            if notification_table == "store_order_notifications":
                db.execute("INSERT OR IGNORE INTO store_order_notifications(store_order_ref,event_key,recipient,status,attempts,last_error,created_at,updated_at) VALUES(?,?,?,'pending',0,'',?,?)", (order_ref, status, recipient, now, now))
            else:
                db.execute("INSERT OR IGNORE INTO order_notifications(order_ref,event_key,recipient,status,attempts,last_error,created_at,updated_at) VALUES(?,?,?,'pending',0,'',?,?)", (order_ref, status, recipient, now, now))
        else:
            db.execute(f"UPDATE {notification_table} SET recipient=?,status='pending',last_error='',updated_at=? WHERE id=?", (recipient, now_iso(), event["id"]))
    result = (enqueue_and_send_store_order_email(order_ref, status, recipient, total, currency, f"Tienda: {store_label}. Reintento de notificación del estado actual.") if notification_table == "store_order_notifications" else enqueue_and_send_order_email(order_ref, status, recipient, total, currency, f"Reintento de notificación del estado actual."))
    return {"ok": bool(result.get("sent")), "email_sent": bool(result.get("sent")), "email_status": result.get("reason", "sent")}


@app.get("/api/orders/{order_ref}/receipt", response_class=HTMLResponse)
async def receipt(order_ref: str, request: Request):
    tg_id = get_auth(request)
    with conn() as db:
        order = db.execute("SELECT * FROM orders WHERE order_ref=? AND telegram_id=?", (order_ref, tg_id)).fetchone()
        if not order:
            raise HTTPException(404, "Recibo no encontrado.")
        lines = db.execute("SELECT * FROM purchases WHERE order_ref=? AND telegram_id=? ORDER BY id", (order_ref, tg_id)).fetchall()
    esc = lambda value: escape(str(value or ""))
    rows = "".join(f"<tr><td>{esc(x['title'])}</td><td>{int(x['qty'])}</td><td>{esc(x['currency'])} {Decimal(x['total']):.2f}</td></tr>" for x in lines)
    page = f"""<!doctype html><html lang='es'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Recibo ProEshop {esc(order_ref)}</title><style>body{{font:16px system-ui;max-width:760px;margin:40px auto;padding:20px;color:#15243b}}.tag{{display:inline-block;background:#fff0cf;padding:8px 12px;border-radius:8px;font-weight:700}}table{{width:100%;border-collapse:collapse;margin:24px 0}}td,th{{padding:12px;border-bottom:1px solid #ddd;text-align:left}}.total{{font-size:1.4rem;font-weight:800}}button{{padding:12px 16px;background:#075fc7;color:white;border:0;border-radius:8px}}@media print{{button{{display:none}}}}</style>
    <h1>ProEshop</h1><div class='tag'>{'REGISTRO DE PAGO USDT · PENDIENTE DE REVISIÓN' if order['payment_method']=='usdt_trc20' else 'RECIBO DE PRUEBA · SIN VALOR FISCAL'}</div><h2>Pedido {esc(order_ref)}</h2><p>Fecha: {esc(order['created_at'])}<br>Estado: {esc(ORDER_STATUS_LABELS.get(order['status'], order['status']))}</p>
    <table><thead><tr><th>Artículo</th><th>Cantidad</th><th>Total de línea</th></tr></thead><tbody>{rows}</tbody></table>
    <p>Subtotal: {esc(order['currency'])} {Decimal(order['subtotal']):.2f}</p><p>Impuestos estimados: {esc(order['currency'])} {Decimal(order['tax']):.2f}</p><p>Envío estimado: {esc(order['currency'])} {Decimal(order['shipping']):.2f}</p><p class='total'>Total estimado: {esc(order['currency'])} {Decimal(order['total']):.2f}</p>
    <p>{'Este registro no confirma por sí solo el pago. Consulta el estado en ProEshop; el equipo debe revisar la transferencia antes de aprobar el pedido.' if order['payment_method']=='usdt_trc20' else 'Este documento solo registra una operación ficticia del simulador. No acredita pago, compra, envío ni obligación fiscal.'}</p><p>Para guardar una copia, usa la opción Imprimir del navegador y selecciona Guardar como PDF.</p></html>"""
    audit(tg_id, "receipt_view", f"order={order_ref}")
    return HTMLResponse(page)


@app.get("/api/admin/metrics")
async def admin_metrics(request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(503, "Configura ADMIN_API_KEY en Railway para habilitar el panel administrativo.")
    supplied = request.headers.get("X-Admin-Key", "")
    if not hmac.compare_digest(supplied, ADMIN_API_KEY):
        raise HTTPException(403, "Clave administrativa no válida.")
    audit("admin", "admin_metrics_view", "Métricas administrativas consultadas")
    with conn() as db:
        metrics = {
            "users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "demo_volume": db.execute("SELECT COALESCE(SUM(CAST(total AS REAL)),0) FROM orders").fetchone()[0],
            "cart_items": db.execute("SELECT COUNT(*) FROM carts").fetchone()[0],
            "searches_24h": db.execute("SELECT COUNT(*) FROM audit_log WHERE action='search' AND created_at >= ?", ((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec="seconds"),)).fetchone()[0],
            "audit_events": db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
            "recent_orders": [dict(x) for x in db.execute("SELECT order_ref,currency,total,status,created_at FROM orders ORDER BY created_at DESC LIMIT 10").fetchall()],
            "recent_audit": [dict(x) for x in db.execute("SELECT actor_id,action,detail,created_at FROM audit_log ORDER BY id DESC LIMIT 25").fetchall()],
        }
    return metrics


def _payment_deadline_seconds(created_at: str) -> float:
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp() + 300
    except Exception:
        return time.time() + 300


def expire_stale_crypto_payments(order_ref: str | None = None):
    """Cancel unpaid USDT orders after five minutes and email the customer once."""
    expired_notifications = []
    with conn() as db:
        query = "SELECT cp.order_ref,cp.created_at,o.telegram_id,o.customer_email,o.total,o.currency FROM crypto_payments cp JOIN orders o ON o.order_ref=cp.order_ref WHERE cp.status='pending'"
        args = ()
        if order_ref:
            query += " AND cp.order_ref=?"
            args = (order_ref,)
        rows = db.execute(query, args).fetchall()
        now_epoch = time.time()
        for row in rows:
            if now_epoch < _payment_deadline_seconds(row["created_at"]):
                continue
            ref = row["order_ref"]
            now = now_iso()
            changed = db.execute("UPDATE crypto_payments SET status='expired',updated_at=? WHERE order_ref=? AND status='pending'", (now, ref)).rowcount
            if not changed:
                continue
            db.execute("UPDATE orders SET status='cancelled',updated_at=? WHERE order_ref=? AND status='pending_payment'", (now, ref))
            cancel_detail = "El pedido se canceló automáticamente porque no se detectó el pago USDT confirmado dentro de los cinco minutos. La cotización expiró; crea un nuevo pedido si deseas intentarlo otra vez."
            db.execute("INSERT INTO order_events(order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)", (ref, "cancelled", "Pedido cancelado", cancel_detail, now))
            stores = db.execute("SELECT store_order_ref FROM store_orders WHERE order_ref=? AND status='pending_payment'", (ref,)).fetchall()
            for store in stores:
                db.execute("UPDATE store_orders SET status='cancelled',updated_at=? WHERE store_order_ref=? AND status='pending_payment'", (now, store["store_order_ref"]))
                db.execute("INSERT INTO store_order_events(store_order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)", (store["store_order_ref"], "cancelled", "Pedido cancelado", "Pago USDT no detectado dentro del plazo de cinco minutos.", now))
            expired_notifications.append((ref, row["customer_email"], row["total"], row["currency"], cancel_detail))
            log.info("USDT payment expired order=%s", ref)
    # Send email outside the transaction. The notification queue makes retries idempotent.
    for ref, recipient, total, currency, detail in expired_notifications:
        if recipient:
            enqueue_and_send_order_email(ref, "cancelled", recipient, total, currency, detail)


async def verify_pending_tron_payments():
    """Match confirmed incoming TRC-20 USDT transfers against unique order amounts."""
    expire_stale_crypto_payments()
    with conn() as db:
        pending = db.execute("SELECT cp.*,o.telegram_id,o.customer_email,o.total,o.currency FROM crypto_payments cp JOIN orders o ON o.order_ref=cp.order_ref WHERE cp.status='pending' ORDER BY cp.created_at LIMIT 100").fetchall()
    if not pending:
        return
    headers = {"Accept": "application/json"}
    if TRONGRID_API_KEY:
        headers["TRON-PRO-API-KEY"] = TRONGRID_API_KEY
    params = {"limit": 200, "only_confirmed": "true", "order_by": "block_timestamp,desc", "contract_address": TRON_USDT_CONTRACT}
    try:
        async with httpx.AsyncClient(timeout=12, headers=headers) as client:
            response = await client.get(f"{TRON_API_BASE}/v1/accounts/{TRON_USDT_ADDRESS}/transactions/trc20", params=params)
            response.raise_for_status()
            transfers = response.json().get("data", [])
    except Exception as exc:
        log.warning("No se pudieron consultar transferencias USDT TRON: %s", str(exc)[:220])
        return
    by_amount = {}
    for tx in transfers:
        try:
            token = tx.get("token_info") or {}
            if str(token.get("address", "")) != TRON_USDT_CONTRACT:
                continue
            if str(tx.get("to", "")) != TRON_USDT_ADDRESS:
                continue
            raw = Decimal(str(tx.get("value", "0")))
            decimals = int(token.get("decimals", 6))
            amount = (raw / (Decimal(10) ** decimals)).quantize(Decimal("0.000001"))
            txid = str(tx.get("transaction_id", ""))
            timestamp = int(tx.get("block_timestamp", 0))
            if txid:
                by_amount.setdefault(str(amount), []).append((txid, amount, timestamp))
        except (ValueError, TypeError, InvalidOperation):
            continue
    for payment in pending:
        matches = by_amount.get(str(Decimal(payment["requested_amount"]).quantize(Decimal("0.000001"))), [])
        try:
            created_ms = int(datetime.fromisoformat(payment["created_at"].replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            created_ms = 0
        match = next((x for x in matches if x[2] >= created_ms and x[0]), None)
        with conn() as db:
            db.execute("UPDATE crypto_payments SET last_checked_at=?,updated_at=? WHERE order_ref=? AND status='pending'", (now_iso(), now_iso(), payment["order_ref"]))
            if not match:
                continue
            txid, amount, _ = match
            # A txid is unique; avoid crediting the same transfer to another order.
            if db.execute("SELECT 1 FROM crypto_payments WHERE txid=? AND status='detected'", (txid,)).fetchone():
                continue
            now = now_iso(); ref = payment["order_ref"]
            db.execute("UPDATE crypto_payments SET status='detected',txid=?,paid_amount=?,updated_at=? WHERE order_ref=? AND status='pending'", (txid, str(amount), now, ref))
            db.execute("UPDATE orders SET status='payment_review',updated_at=? WHERE order_ref=? AND status='pending_payment'", (now, ref))
            db.execute("INSERT INTO order_events(order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)", (ref, "payment_review", "En revisión de pago", f"Transferencia USDT TRC-20 detectada y confirmada. TXID: {txid}. Importe: {amount} USDT. Pendiente de revisión administrativa.", now))
            stores = db.execute("SELECT * FROM store_orders WHERE order_ref=? AND status='pending_payment'", (ref,)).fetchall()
            for store in stores:
                db.execute("UPDATE store_orders SET status='payment_review',updated_at=? WHERE store_order_ref=? AND status='pending_payment'", (now, store["store_order_ref"]))
                detail = f"Pago USDT detectado para el pedido principal. TXID: {txid}. Pendiente de revisión administrativa."
                db.execute("INSERT INTO store_order_events(store_order_ref,status,label,detail,created_at) VALUES(?,?,?, ?,?)", (store["store_order_ref"], "payment_review", "En revisión de pago", detail, now))
        log.info("USDT payment detected order=%s txid=%s amount=%s", payment["order_ref"], txid, amount)
        audit(payment["telegram_id"], "usdt_payment_detected", f"order={payment['order_ref']}; txid={txid}; amount={amount}")
        if payment["customer_email"]:
            enqueue_and_send_order_email(payment["order_ref"], "payment_review", payment["customer_email"], payment["total"], payment["currency"], f"Transferencia detectada en TRON. TXID: {txid}. El pago aún debe ser revisado por ProEshop.")


@app.get("/api/payment/{order_ref}")
async def get_crypto_payment(order_ref: str, request: Request):
    tg_id = get_auth(request)
    expire_stale_crypto_payments(order_ref)
    with conn() as db:
        row = db.execute("SELECT cp.*,o.status AS order_status,o.total,o.currency FROM crypto_payments cp JOIN orders o ON o.order_ref=cp.order_ref WHERE cp.order_ref=? AND o.telegram_id=?", (order_ref, tg_id)).fetchone()
    if not row:
        raise HTTPException(404, "No se encontró el pago de este pedido.")
    if row["status"] == "pending":
        await verify_pending_tron_payments()
        with conn() as db:
            row = db.execute("SELECT cp.*,o.status AS order_status,o.total,o.currency FROM crypto_payments cp JOIN orders o ON o.order_ref=cp.order_ref WHERE cp.order_ref=? AND o.telegram_id=?", (order_ref, tg_id)).fetchone()
    deadline = _payment_deadline_seconds(row["created_at"])
    return {"order_ref": order_ref, "network": row["network"], "token": row["token_symbol"], "address": row["receiving_address"], "amount": row["requested_amount"], "status": row["status"], "order_status": row["order_status"], "created_at": row["created_at"], "deadline_at": datetime.fromtimestamp(deadline, timezone.utc).isoformat(), "remaining_seconds": max(0, int(deadline-time.time())) if row["status"] == "pending" else 0, "txid": row["txid"] or None, "paid_amount": row["paid_amount"] or None, "last_checked_at": row["last_checked_at"] or None, "explorer_url": ("https://tronscan.org/#/transaction/" + row["txid"]) if row["txid"] else None}


async def tron_payment_monitor():
    while True:
        try:
            await verify_pending_tron_payments()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error inesperado en el monitor de pagos TRON")
        await asyncio.sleep(TRON_POLL_SECONDS)


@app.post("/api/purchase")
async def fictional_purchase(body: CheckoutBody, request: Request):
    tg_id = get_auth(request)
    if body.payment_method not in {"demo_balance", "usdt_trc20"}:
        raise HTTPException(400, "Método de pago no compatible.")
    is_crypto = body.payment_method == "usdt_trc20"
    customer_email = (body.customer_email or body.email).strip().lower()
    if is_crypto and not customer_email:
        raise HTTPException(400, "Introduce tu correo electrónico para recibir las notificaciones de pago pendiente y cancelación.")
    if customer_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", customer_email):
        raise HTTPException(400, "Introduce un correo electrónico válido.")
    submitted_shipping = [body.shipping_name.strip(), body.shipping_city.strip(), body.shipping_country.strip(), body.shipping_address.strip()]
    if any(submitted_shipping) and not all(submitted_shipping):
        raise HTTPException(400, "Completa todos los datos de entrega de demostración.")
    if all(submitted_shipping):
        shipping_name, shipping_city, shipping_country, shipping_address = submitted_shipping
    else:
        shipping_name, shipping_city, shipping_country, shipping_address = ("Demo Recipient", "Demo City", "Demo Region", "Demo Address")
    store_emails = []
    with conn() as db:
        rows = db.execute("SELECT * FROM carts WHERE telegram_id=? ORDER BY id", (tg_id,)).fetchall()
        if not rows: raise HTTPException(400, "El carrito está vacío.")
        currencies = {r["currency"] for r in rows}
        if len(currencies) != 1: raise HTTPException(400, "No combines monedas distintas en una misma compra ficticia.")
        currency = next(iter(currencies))
        subtotal = sum((Decimal(r["price"]) * r["qty"] for r in rows), Decimal("0")).quantize(Decimal("0.01"))
        tax = (subtotal * ESTIMATED_TAX_RATE).quantize(Decimal("0.01"))
        shipping = ESTIMATED_SHIPPING_FEE if subtotal > 0 else Decimal("0.00")
        total = (subtotal + tax + shipping).quantize(Decimal("0.01"))
        b = db.execute("SELECT amount FROM balances WHERE telegram_id=?", (tg_id,)).fetchone()
        balance = Decimal(b["amount"] if b else str(INITIAL_BALANCE))
        if not is_crypto and total > balance: raise HTTPException(400, f"Saldo ficticio insuficiente. Total estimado {total:.2f}; saldo {balance:.2f}.")
        if is_crypto and currency.upper() != "USD":
            raise HTTPException(400, "El pago con USDT solo admite pedidos con precios en USD.")
        when = now_iso(); order_ref = "SC-" + secrets.token_hex(5).upper()
        # Add a unique micro-amount so concurrent orders to the same wallet can be matched safely.
        requested_usdt = None
        if is_crypto:
            pending_amounts = {r[0] for r in db.execute("SELECT requested_amount FROM crypto_payments WHERE status='pending'").fetchall()}
            for _attempt in range(1000):
                candidate = (total + (Decimal(secrets.randbelow(999) + 1) / Decimal("1000000"))).quantize(Decimal("0.000001"))
                if str(candidate) not in pending_amounts:
                    requested_usdt = candidate
                    break
            if requested_usdt is None:
                raise HTTPException(503, "No se pudo generar un importe único para el pago. Inténtalo nuevamente.")
        db.execute("""INSERT INTO orders(order_ref,telegram_id,subtotal,tax,shipping,total,currency,status,created_at,updated_at,
                      shipping_name,shipping_city,shipping_country,shipping_address,payment_method,customer_email)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (order_ref, tg_id, str(subtotal), str(tax), str(shipping), str(total), currency, "pending_payment" if is_crypto else "confirmed", when, when,
                    shipping_name, shipping_city, shipping_country, shipping_address, body.payment_method, customer_email))
        initial_status = "pending_payment" if is_crypto else "confirmed"
        initial_label = "Pendiente de pago" if is_crypto else "Confirmado"
        initial_detail = (f"Pedido creado. Pago pendiente durante 5 minutos: enviar {requested_usdt} USDT por TRON (TRC-20). Si no se detecta el pago en ese plazo, se cancelará automáticamente." if is_crypto else "Pedido de demostración registrado; no se envió una orden al comercio ni se procesó un pago real.")
        db.execute("INSERT INTO order_events(order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)",
                   (order_ref, initial_status, initial_label, initial_detail, when))
        if is_crypto:
            db.execute("INSERT INTO crypto_payments(order_ref,network,token_symbol,token_contract,receiving_address,requested_amount,status,created_at,updated_at) VALUES(?,?,?,?,?,?, 'pending', ?, ?)",
                       (order_ref, "TRON (TRC-20)", "USDT", TRON_USDT_CONTRACT, TRON_USDT_ADDRESS, str(requested_usdt), when, when))
        # Group items by source and create independent status/order references per store.
        groups = {}
        for row in rows:
            key = str(row["platform"] or "other").strip().lower()
            groups.setdefault(key, []).append(row)
        group_subtotals = {k: sum((Decimal(r["price"]) * r["qty"] for r in items), Decimal("0")).quantize(Decimal("0.01")) for k, items in groups.items()}
        allocated_tax = {}; allocated_shipping = {}
        keys = list(groups.keys())
        tax_left, shipping_left = tax, Decimal(shipping).quantize(Decimal("0.01"))
        for idx, key in enumerate(keys):
            if idx == len(keys)-1:
                allocated_tax[key], allocated_shipping[key] = tax_left, shipping_left
            else:
                allocated_tax[key] = (tax * group_subtotals[key] / subtotal).quantize(Decimal("0.01")) if subtotal else Decimal("0.00")
                allocated_shipping[key] = (Decimal(shipping) / Decimal(len(keys))).quantize(Decimal("0.01"))
                tax_left -= allocated_tax[key]; shipping_left -= allocated_shipping[key]
        for platform, items in groups.items():
            platform_cfg = PLATFORMS.get(platform, {})
            store_label = platform_cfg.get("label", platform.replace("_", " ").title())
            store_ref = f"{order_ref}-{re.sub(r'[^A-Z0-9]', '', platform.upper())[:10] or 'STORE'}"
            store_subtotal = group_subtotals[platform]
            store_tax, store_shipping = allocated_tax[platform], allocated_shipping[platform]
            store_total = (store_subtotal + store_tax + store_shipping).quantize(Decimal("0.01"))
            db.execute("""INSERT INTO store_orders(store_order_ref,order_ref,platform,store_label,subtotal,tax,shipping,total,currency,status,created_at,updated_at,customer_email)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (store_ref, order_ref, platform, store_label, str(store_subtotal), str(store_tax), str(store_shipping), str(store_total), currency, "pending_payment" if is_crypto else "confirmed", when, when, customer_email))
            lines = []
            for row in items:
                line_total = (Decimal(row["price"]) * row["qty"]).quantize(Decimal("0.01"))
                db.execute("""INSERT INTO purchases(telegram_id,platform,title,price,currency,qty,total,url,purchased_at,order_ref,store_order_ref)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                           (tg_id, row["platform"], row["title"], row["price"], row["currency"], row["qty"], str(line_total), row["url"], when, order_ref, store_ref))
                lines.append(f"{row['qty']} × {row['title']} — {currency} {line_total:.2f}")
            initial_detail = f"Pedido registrado en ProEshop para {store_label}. No implica compra ni envío real."
            db.execute("INSERT INTO order_events(order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)",
                       (order_ref, initial_status, f"{store_label}: {initial_label}", f"Referencia de tienda: {store_ref}. Artículos: " + "; ".join(lines), when))
            db.execute("INSERT INTO store_order_events(store_order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)",
                       (store_ref, initial_status, initial_label, initial_detail, when))
            store_emails.append({"store_order_ref": store_ref, "store": store_label, "total": str(store_total), "items": lines})
        if not is_crypto:
            db.execute("UPDATE balances SET amount=? WHERE telegram_id=?", (str(balance-total), tg_id))
        db.execute("DELETE FROM carts WHERE telegram_id=?", (tg_id,))
    audit(tg_id, "purchase_usdt" if is_crypto else "purchase_demo", f"order={order_ref}; stores={len(groups)}; total={total}; currency={currency}")
    email_results = []
    # USDT orders get a dedicated pending-payment email immediately after creation.
    if is_crypto and customer_email:
        pending_email = enqueue_and_send_order_email(
            order_ref, "pending_payment", customer_email, str(total), currency,
            f"Pedido: {order_ref}\nImporte exacto: {requested_usdt} USDT\nRed: TRON (TRC-20)\nDirección de recepción: {TRON_USDT_ADDRESS}\nPlazo: 5 minutos desde la creación del pedido. Si no se detecta el pago confirmado antes del vencimiento, el pedido se cancelará automáticamente."
        )
        email_results.append({"store": "ProEshop", "store_order_ref": order_ref,
                              "email_sent": bool(pending_email.get("sent")),
                              "email_status": "sent" if pending_email.get("sent") else pending_email.get("reason", "not_configured")})
    for item in store_emails:
        detail = (f"Tienda: {item['store']}\nArtículos de esta tienda:\n" + "\n".join(item["items"]) +
                  f"\nSubtotal: {currency} {Decimal(next(v for k,v in group_subtotals.items() if PLATFORMS.get(k, {}).get('label', k.replace('_',' ').title()) == item['store'])):.2f}" +
                  (f"\nPago pendiente: enviar {requested_usdt} USDT por TRC-20 a {TRON_USDT_ADDRESS}." if is_crypto else "\nPedido de demostración: no se realizó compra ni pago real."))
        result = enqueue_and_send_store_order_email(item["store_order_ref"], "received", customer_email, item["total"], currency, detail) if customer_email and not is_crypto else {"sent": False, "reason": "Pago USDT pendiente" if is_crypto else "Sin correo proporcionado"}
        email_results.append({"store": item["store"], "store_order_ref": item["store_order_ref"], "email_sent": bool(result.get("sent")), "email_status": "sent" if result.get("sent") else result.get("reason", "not_configured")})
    with conn() as db:
        pref = db.execute("SELECT order_updates FROM notification_preferences WHERE telegram_id=?", (tg_id,)).fetchone()
    if BOT_TOKEN and (pref is None or pref["order_updates"]):
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                    "chat_id": tg_id,
                    "text": ((f"🛍️ ProEshop — pedido con pago USDT pendiente\nReferencia: {order_ref}\nImporte exacto: {requested_usdt} USDT\nRed: TRON (TRC-20)\nDirección: {TRON_USDT_ADDRESS}" if is_crypto else f"🛍️ ProEshop — pedido de demostración\nReferencia general: {order_ref}\nTotal estimado: {currency} {total:.2f}\nNo se realizó ninguna compra real ni se procesó un pago.") +
                             ("\nPedidos por tienda: " + ", ".join(x['store_order_ref'] for x in store_emails)) )})
        except httpx.HTTPError:
            log.info("No se pudo enviar notificación de pedido %s", order_ref)
    return {"ok": True, "order_ref": order_ref, "store_orders": store_emails,
            "subtotal": str(subtotal), "tax": str(tax), "shipping": str(shipping), "total": str(total),
            "balance": str(balance-total) if not is_crypto else str(balance), "currency": currency, "status": "pending_payment" if is_crypto else "received", "purchased_at": when,
            "payment": ({"method": "usdt_trc20", "network": "TRON (TRC-20)", "token": "USDT", "address": TRON_USDT_ADDRESS, "amount": str(requested_usdt), "status": "pending", "deadline_at": datetime.fromtimestamp(_payment_deadline_seconds(when), timezone.utc).isoformat(), "remaining_seconds": 300} if is_crypto else None),
            "email_sent": (bool(email_results[0]["email_sent"]) if is_crypto and email_results else (bool(email_results) and all(x["email_sent"] for x in email_results))),
            "email_status": email_results, "message": ("Pedido pendiente de pago. Tienes 5 minutos para enviar el importe exacto en USDT por TRC-20; si no se detecta el pago, se cancelará automáticamente." if is_crypto else "Pedido de demostración registrado; no se realizó una compra real.")}

