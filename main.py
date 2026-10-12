import os, hmac, hashlib, json, time, secrets, sqlite3, logging, re, smtplib
from urllib.parse import parse_qsl, quote_plus, urlparse
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


app = FastAPI(title="ProEshop Telegram Mini App", docs_url=None, redoc_url=None)

# Lightweight per-process throttling for public-facing credential/search endpoints.
_RATE_BUCKETS = {}
_SEARCH_CACHE = {}

@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    path = request.url.path
    if path in ("/api/login", "/api/search"):
        ip = request.client.host if request.client else "unknown"
        key = (ip, path)
        now = time.time()
        window, limit = (60, 12 if path == "/api/login" else 30)
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
        CREATE TABLE IF NOT EXISTS carts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id TEXT NOT NULL, platform TEXT NOT NULL,
          title TEXT NOT NULL, price TEXT NOT NULL, currency TEXT NOT NULL, url TEXT NOT NULL,
          qty INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
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
        db.execute("PRAGMA journal_mode=WAL")
        # Safe migration for databases created by earlier ShopCart versions.
        purchase_columns = {row["name"] for row in db.execute("PRAGMA table_info(purchases)").fetchall()}
        if "order_ref" not in purchase_columns:
            db.execute("ALTER TABLE purchases ADD COLUMN order_ref TEXT NOT NULL DEFAULT ''")
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
    "received": "Pedido recibido",
    "reviewing": "En revisión",
    "action_required": "Requiere acción del cliente",
    "confirmed": "Pedido confirmado",
    "preparing": "En preparación",
    "shipped": "Enviado",
    "delivered": "Entregado",
    "unavailable": "Producto no disponible",
    "cancelled": "Cancelado",
    "returned": "Devuelto",
}
ORDER_TRANSITIONS = {
    "confirmed_simulated": {"reviewing", "cancelled", "unavailable"},
    "received": {"reviewing", "action_required", "cancelled", "unavailable"},
    "reviewing": {"confirmed", "action_required", "cancelled", "unavailable"},
    "action_required": {"reviewing", "cancelled"},
    "confirmed": {"preparing", "cancelled"},
    "preparing": {"shipped", "cancelled"},
    "shipped": {"delivered", "returned"},
    "delivered": {"returned"},
    "unavailable": {"cancelled"},
    "cancelled": set(),
    "returned": set(),
}
ORDER_EMAIL_COPY = {
    "received": ("Recibimos tu pedido", "Tu pedido fue registrado en ProEshop. Esto confirma el registro, no un pago ni una compra con un proveedor."),
    "reviewing": ("Estamos revisando tu pedido", "Estamos verificando los detalles y la disponibilidad del pedido."),
    "action_required": ("Necesitamos información para tu pedido", "Tu pedido requiere una acción adicional. Revisa los detalles con el equipo de ProEshop."),
    "confirmed": ("Tu pedido ha sido confirmado", "El pedido fue confirmado por el equipo de ProEshop. El estado del pago se informa por separado."),
    "preparing": ("Tu pedido está en preparación", "Tu pedido ha pasado a la etapa de preparación."),
    "shipped": ("Tu pedido fue enviado", "Tu pedido figura como enviado. Consulta el número de guía en los detalles del pedido si se ha registrado."),
    "delivered": ("Tu pedido figura como entregado", "Se registró la entrega del pedido."),
    "unavailable": ("Actualización sobre disponibilidad", "El producto no está disponible actualmente. El equipo de ProEshop te informará sobre las opciones."),
    "cancelled": ("Tu pedido fue cancelado", "El pedido fue marcado como cancelado en ProEshop."),
    "returned": ("Actualización de devolución", "El pedido fue marcado como devuelto. El estado de cualquier reembolso se gestiona por separado."),
}

def send_status_email(recipient: str, order_ref: str, status: str, total: str, currency: str, detail: str = ""):
    if not all([SMTP_HOST, SMTP_FROM_EMAIL, recipient]):
        raise RuntimeError("SMTP no configurado o pedido sin correo del cliente")
    subject, message = ORDER_EMAIL_COPY.get(status, ("Actualización de tu pedido", "El estado de tu pedido ha cambiado."))
    msg = EmailMessage()
    msg["Subject"] = f"ProEshop · {subject} · {order_ref}"
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = recipient
    extra = f"\nDetalle: {detail}" if detail else ""
    msg.set_content(f"Hola,\n\n{message}\n\nPedido: {order_ref}\nEstado: {ORDER_STATUS_LABELS.get(status, status)}\nTotal registrado: {currency} {Decimal(total):.2f}{extra}\n\nEl estado del pedido no implica por sí mismo que el pago haya sido recibido.\nProEshop")
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
    init_data: str
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class SearchBody(BaseModel):
    platform: str
    query: str = Field(min_length=1, max_length=180)


class AddBody(BaseModel):
    platform: str
    title: str = Field(min_length=1, max_length=180)
    price: str
    currency: str = Field(default="USD", min_length=3, max_length=3)
    url: str = Field(min_length=8, max_length=1000)


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
    payment_method: str = Field(default="demo_balance", max_length=32)


PLATFORMS = {
    "amazon": {"label": "Amazon", "url": "https://www.amazon.com/s?k={q}"},
    "target": {"label": "Target", "url": "https://www.target.com/s?searchTerm={q}"},
    "walmart": {"label": "Walmart", "url": "https://www.walmart.com/search?q={q}"},
    "hublot": {"label": "HUBLOT", "url": "https://www.hublot.com/en-us/watches"},
    "jewelers": {"label": "Jewelers Toy Store", "url": "https://www.jewelerstoystore.com/Electronic-s/1074.htm"},
    "rolex": {"label": "Rolex", "url": "https://www.rolex.com/es/watches/find-rolex?group=0"},
}


# Catálogo local ilustrativo para que HUBLOT funcione aunque el cliente esté desactualizado.
HUBLOT_CATALOG = [{'id': 'bb-original-red', 'name': 'Big Bang Original Soft Touch All Red', 'collection': 'Big Bang', 'price': 24900, 'desc': 'Rojo integral y diseño deportivo contemporáneo.', 'img': 'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-original-black', 'name': 'Big Bang Original Soft Touch All Black', 'collection': 'Big Bang', 'price': 24900, 'desc': 'Acabado negro integral de carácter técnico.', 'img': 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-original-titanium', 'name': 'Big Bang Original Titanium 43 mm', 'collection': 'Big Bang', 'price': 20400, 'desc': 'Titanio ligero con estética emblemática.', 'img': 'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-original-titanium-ceramic', 'name': 'Big Bang Original Titanium Ceramic 43 mm', 'collection': 'Big Bang', 'price': 21600, 'desc': 'Titanio y cerámica en contraste.', 'img': 'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-original-king-gold', 'name': 'Big Bang Original King Gold Ceramic 43 mm', 'collection': 'Big Bang', 'price': 39600, 'desc': 'King Gold combinado con cerámica.', 'img': 'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-original-black-magic', 'name': 'Big Bang Original Black Magic 43 mm', 'collection': 'Big Bang', 'price': 22800, 'desc': 'Cerámica negra con presencia discreta.', 'img': 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-original-coal-blue', 'name': 'Big Bang Original Titanium Coal Blue 43 mm', 'collection': 'Big Bang', 'price': 20400, 'desc': 'Esfera azul carbón y caja de titanio.', 'img': 'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-reloaded-uefa', 'name': 'Big Bang Reloaded UEFA Champions League 44 mm', 'collection': 'Big Bang', 'price': 25200, 'desc': 'Edición temática de fútbol.', 'img': 'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-sapphire-sky', 'name': 'Big Bang Sapphire Sky Blue 44 mm', 'collection': 'Big Bang', 'price': 84300, 'desc': 'Caja de zafiro azul translúcido.', 'img': 'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-summer-42', 'name': 'Big Bang Summer Multi-Colored Ceramic 42 mm', 'collection': 'Big Bang', 'price': 34300, 'desc': 'Cerámica multicolor de edición llamativa.', 'img': 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-summer-44', 'name': 'Big Bang Summer Multi-Colored Ceramic 44 mm', 'collection': 'Big Bang', 'price': 119000, 'desc': 'Versión de alta complejidad multicolor.', 'img': 'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-peach-42', 'name': 'Big Bang Titanium Peach Ceramic 42 mm', 'collection': 'Big Bang', 'price': 24000, 'desc': 'Cerámica tono melocotón y titanio.', 'img': 'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-peach-33', 'name': 'Big Bang Peach Ceramic 33 mm', 'collection': 'Big Bang', 'price': 15500, 'desc': 'Formato compacto en cerámica melocotón.', 'img': 'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-petrol-33', 'name': 'Big Bang Petrol Blue Ceramic 33 mm', 'collection': 'Big Bang', 'price': 15500, 'desc': 'Cerámica azul petróleo.', 'img': 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-mint-33', 'name': 'Big Bang Mint Green Ceramic 33 mm', 'collection': 'Big Bang', 'price': 15500, 'desc': 'Cerámica verde menta.', 'img': 'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-unico-grey', 'name': 'Big Bang Unico Essential Grey 42 mm', 'collection': 'Big Bang', 'price': 24000, 'desc': 'Cronógrafo Unico en tonos grises.', 'img': 'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-magic-gold', 'name': 'Big Bang Reloaded Magic Gold 44 mm', 'collection': 'Big Bang', 'price': 44500, 'desc': 'Aleación Magic Gold resistente a rayaduras.', 'img': 'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-king-gold', 'name': 'Big Bang Original King Gold 43 mm', 'collection': 'Big Bang', 'price': 39600, 'desc': 'King Gold en silueta clásica Big Bang.', 'img': 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85'}, {'id': 'bb-unico-titanium', 'name': 'Big Bang Unico Titanium 42 mm', 'collection': 'Big Bang', 'price': 26400, 'desc': 'Cronógrafo con caja de titanio.', 'img': 'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85'}, {'id': 'square-unico-titanium', 'name': 'Square Bang Unico Titanium 42 mm', 'collection': 'Big Bang', 'price': 26400, 'desc': 'Caja cuadrada y movimiento Unico.', 'img': 'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85'}, {'id': 'square-unico-ceramic', 'name': 'Square Bang Unico Titanium Ceramic 42 mm', 'collection': 'Big Bang', 'price': 27600, 'desc': 'Titanio y cerámica en formato cuadrado.', 'img': 'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85'}, {'id': 'square-king-gold', 'name': 'Square Bang Unico King Gold 42 mm', 'collection': 'Big Bang', 'price': 49300, 'desc': 'King Gold con geometría cuadrada.', 'img': 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85'}, {'id': 'square-black-magic', 'name': 'Square Bang Unico Black Magic 42 mm', 'collection': 'Big Bang', 'price': 30000, 'desc': 'Caja cuadrada de cerámica negra.', 'img': 'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-original-titanium', 'name': 'Classic Fusion Original Titanium 42 mm', 'collection': 'Classic Fusion', 'price': 9400, 'desc': 'Elegancia minimalista en titanio.', 'img': 'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-original-black', 'name': 'Classic Fusion Original Black Magic 42 mm', 'collection': 'Classic Fusion', 'price': 11400, 'desc': 'Diseño sobrio con acabado negro.', 'img': 'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-titanium', 'name': 'Classic Fusion Titanium 42 mm', 'collection': 'Classic Fusion', 'price': 8700, 'desc': 'Perfil limpio y caja de titanio.', 'img': 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-blue', 'name': 'Classic Fusion Titanium Blue 42 mm', 'collection': 'Classic Fusion', 'price': 8700, 'desc': 'Esfera azul y estética refinada.', 'img': 'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-king-gold', 'name': 'Classic Fusion King Gold 42 mm', 'collection': 'Classic Fusion', 'price': 25200, 'desc': 'Oro cálido con líneas depuradas.', 'img': 'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-black-magic', 'name': 'Classic Fusion Black Magic 42 mm', 'collection': 'Classic Fusion', 'price': 10700, 'desc': 'Cerámica negra y diseño elegante.', 'img': 'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-chrono-ti', 'name': 'Classic Fusion Chronograph Titanium 42 mm', 'collection': 'Classic Fusion', 'price': 12300, 'desc': 'Cronógrafo clásico en titanio.', 'img': 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-chrono-gold', 'name': 'Classic Fusion Chronograph King Gold 42 mm', 'collection': 'Classic Fusion', 'price': 32400, 'desc': 'Cronógrafo con caja King Gold.', 'img': 'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-chrono-black', 'name': 'Classic Fusion Chronograph Black Magic 42 mm', 'collection': 'Classic Fusion', 'price': 13500, 'desc': 'Cronógrafo con acabado cerámico negro.', 'img': 'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-aero-ti', 'name': 'Classic Fusion Aerofusion Titanium 45 mm', 'collection': 'Classic Fusion', 'price': 17100, 'desc': 'Esfera esqueletizada y caja de titanio.', 'img': 'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85'}, {'id': 'classic-aero-black', 'name': 'Classic Fusion Aerofusion Black Magic 45 mm', 'collection': 'Classic Fusion', 'price': 18800, 'desc': 'Arquitectura esqueletizada en negro.', 'img': 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-ti', 'name': 'Spirit of Big Bang Titanium 42 mm', 'collection': 'Spirit of Big Bang', 'price': 26400, 'desc': 'Caja tonneau y titanio ligero.', 'img': 'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-ti-ceramic', 'name': 'Spirit of Big Bang Titanium Ceramic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 27600, 'desc': 'Tonneau con combinación de materiales.', 'img': 'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-king-gold', 'name': 'Spirit of Big Bang King Gold 42 mm', 'collection': 'Spirit of Big Bang', 'price': 49300, 'desc': 'Caja tonneau en King Gold.', 'img': 'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-king-ceramic', 'name': 'Spirit of Big Bang King Gold Ceramic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 45700, 'desc': 'King Gold y cerámica negra.', 'img': 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-black-magic', 'name': 'Spirit of Big Bang Black Magic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 30000, 'desc': 'Silueta tonneau con acabado negro.', 'img': 'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-taupe', 'name': 'Spirit of Big Bang Essential Taupe 42 mm', 'collection': 'Spirit of Big Bang', 'price': 24800, 'desc': 'Tono taupe, edición exclusiva online según fabricante.', 'img': 'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-impact-black', 'name': 'Spirit of Big Bang Impact All Black 42 mm', 'collection': 'Spirit of Big Bang', 'price': 33700, 'desc': 'Diseño oscuro de alta presencia.', 'img': 'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-impact-sapphire', 'name': 'Spirit of Big Bang Impact Sapphire 42 mm', 'collection': 'Spirit of Big Bang', 'price': 114500, 'desc': 'Caja de zafiro y diseño escultural.', 'img': 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-sapphire-blue', 'name': 'Spirit of Big Bang Sapphire Blue 42 mm', 'collection': 'Spirit of Big Bang', 'price': 102400, 'desc': 'Caja de zafiro azul.', 'img': 'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-coal-blue', 'name': 'Spirit of Big Bang Titanium Coal Blue 42 mm', 'collection': 'Spirit of Big Bang', 'price': 24000, 'desc': 'Titanio y esfera azul carbón.', 'img': 'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-white', 'name': 'Spirit of Big Bang Titanium White 42 mm', 'collection': 'Spirit of Big Bang', 'price': 26400, 'desc': 'Titanio con estética blanca.', 'img': 'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-meca-ti', 'name': 'Spirit of Big Bang Meca-10 Titanium 45 mm', 'collection': 'Spirit of Big Bang', 'price': 27600, 'desc': 'Reserva de marcha larga y arquitectura mecánica.', 'img': 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-meca-gold', 'name': 'Spirit of Big Bang Meca-10 King Gold 45 mm', 'collection': 'Spirit of Big Bang', 'price': 52900, 'desc': 'Meca-10 con caja King Gold.', 'img': 'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-tourbillon-black', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Black Magic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 109000, 'desc': 'Tourbillon y reserva de marcha de cinco días.', 'img': 'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-tourbillon-red', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Red Magic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 109000, 'desc': 'Cerámica roja y tourbillon.', 'img': 'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-tourbillon-blue', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Sky Blue Ceramic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 109000, 'desc': 'Cerámica azul cielo y tourbillon.', 'img': 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-tourbillon-yellow', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Yellow Magic 42 mm', 'collection': 'Spirit of Big Bang', 'price': 109000, 'desc': 'Cerámica amarilla y tourbillon.', 'img': 'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85'}, {'id': 'spirit-tourbillon-sapphire', 'name': 'Spirit of Big Bang Tourbillon 5-Day Power Reserve Black Sapphire 42 mm', 'collection': 'Spirit of Big Bang', 'price': 169000, 'desc': 'Caja de zafiro negro y tourbillon.', 'img': 'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85'}]


# Modelos destacados del catálogo oficial Rolex. La página oficial no publica ranking de ventas;
# se presentan como modelos destacados, no como una lista verificada de los más vendidos.
# Precios base en USD observados en la página oficial; confirmar antes de publicar ofertas de venta.
ROLEX_CATALOG = [
    {"id":'land-dweller-40', "name":'Rolex Land-Dweller 40 · acero y oro blanco', "price":16450.00, "discount":0, "desc":'Land-Dweller 40, esfera blanco intenso con motivo nido de abeja.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=1000&q=90'},
    {"id":'datejust-41', "name":'Rolex Datejust 41 · acero y oro blanco, esfera verde', "price":11650.00, "discount":40, "desc":'Datejust 41, esfera verde sombreado.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1000&q=90'},
    {"id":'datejust-41-steel', "name":'Rolex Datejust 41 · acero Oystersteel', "price":8950.00, "discount":0, "desc":'Datejust 41, versión Oystersteel.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=1000&q=90'},
    {"id":'datejust-36', "name":'Rolex Datejust 36 · acero y oro blanco', "price":10400.00, "discount":0, "desc":'Datejust 36, diseño clásico.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=1000&q=90'},
    {"id":'lady-datejust', "name":'Rolex Lady-Datejust · 28 mm', "price":15100.00, "discount":0, "desc":'Lady-Datejust, acero y oro amarillo.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=1000&q=90'},
    {"id":'oyster-perpetual-41', "name":'Rolex Oyster Perpetual 41 · acero y oro amarillo', "price":9650.00, "discount":40, "desc":'Oyster Perpetual 41, esfera pizarra.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=1000&q=90'},
    {"id":'cosmograph-daytona', "name":'Rolex Cosmograph Daytona · platino', "price":84600.00, "discount":0, "desc":'Cosmograph Daytona, esfera azul glaciar.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=1000&q=90'},
    {"id":'submariner-date', "name":'Rolex Submariner Date · acero Oystersteel', "price":11900.00, "discount":0, "desc":'Submariner Date, esfera negra.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=1000&q=90'},
    {"id":'submariner-date-gold', "name":'Rolex Submariner Date · acero y oro amarillo', "price":17200.00, "discount":0, "desc":'Submariner Date, esfera azul.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=1000&q=90'},
    {"id":'gmt-master-ii', "name":'Rolex GMT-Master II · Oystersteel', "price":12500.00, "discount":0, "desc":'GMT-Master II, reloj de doble huso horario.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=1000&q=90'},
    {"id":'explorer-40', "name":'Rolex Explorer 40 · acero Oystersteel', "price":8350.00, "discount":40, "desc":'Explorer 40, esfera negra.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1000&q=90'},
    {"id":'explorer-ii', "name":'Rolex Explorer II · 42 mm', "price":10600.00, "discount":40, "desc":'Explorer II, esfera blanca.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=1000&q=90'},
    {"id":'air-king', "name":'Rolex Air-King · 40 mm', "price":8150.00, "discount":0, "desc":'Air-King, esfera negra.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=1000&q=90'},
    {"id":'sea-dweller', "name":'Rolex Sea-Dweller · 43 mm', "price":22450.00, "discount":40, "desc":'Sea-Dweller, reloj de submarinismo.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1000&q=90'},
    {"id":'deepsea', "name":'Rolex Deepsea · 44 mm', "price":15880.00, "discount":0, "desc":'Deepsea, esfera D-blue.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=1000&q=90'},
    {"id":'sky-dweller', "name":'Rolex Sky-Dweller · oro Everose', "price":64900.00, "discount":0, "desc":'Sky-Dweller, esfera pizarra.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=1000&q=90'},
    {"id":'yacht-master-42', "name":'Rolex Yacht-Master 42 · oro amarillo', "price":38100.00, "discount":0, "desc":'Yacht-Master 42, esfera negra.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=1000&q=90'},
    {"id":'yacht-master-40', "name":'Rolex Yacht-Master 40 · acero y platino', "price":13200.00, "discount":0, "desc":'Yacht-Master 40, bisel de platino.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=1000&q=90'},
    {"id":'yacht-master-ii', "name":'Rolex Yacht-Master II · 44 mm', "price":20300.00, "discount":0, "desc":'Yacht-Master II, esfera blanca.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=1000&q=90'},
    {"id":'day-date-40', "name":'Rolex Day-Date 40 · platino', "price":68800.00, "discount":0, "desc":'Day-Date 40, esfera azul glaciar.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=1000&q=90'},
    {"id":'day-date-36', "name":'Rolex Day-Date 36 · platino', "price":59000.00, "discount":0, "desc":'Day-Date 36, acabados clásicos.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=1000&q=90'},
    {"id":'1908', "name":'Rolex 1908 · oro amarillo, 39 mm', "price":27000.00, "discount":0, "desc":'1908, esfera blanco intenso.', "url":"https://www.rolex.com/es/watches/find-rolex?group=0", "img":'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=1000&q=90'}
]
ROLEX_DISCOUNT_IDS = {p["id"] for p in ROLEX_CATALOG if p["discount"] == 40}


# Catálogo basado en los cuatro productos visibles en la categoría de electrónica del proveedor.
# Los precios son los Sale Price/Our Price publicados al consultar la página; se deben revalidar antes de vender.
JEWELERS_CATALOG = [
    {"id":"niton-xl2-100p", "name":"Niton XL2 100p, Niton Gold XRF Analyzer XL2100", "price":20500.00, "desc":"Analizador XRF para metales preciosos.", "url":"https://www.jewelerstoystore.com/Electronic-s/1074.htm"},
    {"id":"niton-dxl", "name":"Niton DXL Precious Metal Analyzer", "price":21750.00, "desc":"Analizador de metales preciosos.", "url":"https://www.jewelerstoystore.com/Electronic-s/1074.htm"},
    {"id":"niton-xl2-battery", "name":"Niton XL2 Battery: 7.4V 7800mAh Li-ion (NTL200SL)", "price":295.00, "desc":"Batería de repuesto para analizador XRF Niton XL2.", "url":"https://www.jewelerstoystore.com/Electronic-s/1074.htm"},
    {"id":"niton-xl2-charger", "name":"Niton XL2 Battery Charger – Fast, Smart & Reliable Charging for Your XRF Analyzer", "price":395.00, "desc":"Cargador para analizador XRF Niton XL2.", "url":"https://www.jewelerstoystore.com/Electronic-s/1074.htm"},
]


@app.on_event("startup")
async def startup():
    init_db()
    if BOT_TOKEN and PUBLIC_BASE_URL:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": f"{PUBLIC_BASE_URL}/telegram-webhook/{WEBHOOK_SECRET}",
                      "allowed_updates": ["message"], "drop_pending_updates": False},
            )
            if r.status_code >= 400:
                log.error("No se pudo configurar webhook: %s", r.text[:300])


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


@app.post("/api/login")
async def login(body: AuthBody):
    tg_id, tg_user = validate_init_data(body.init_data)
    # Demo/local app account gate. Never use retailer credentials here.
    if not (hmac.compare_digest(body.username, DEMO_USERNAME) and
            hmac.compare_digest(body.password, DEMO_PASSWORD)):
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    token = secrets.token_urlsafe(32)
    with conn() as db:
        db.execute("INSERT OR IGNORE INTO users(telegram_id,username,demo_login,created_at) VALUES(?,?,?,?)",
                   (tg_id, tg_user.get("username", ""), body.username, now_iso()))
        db.execute("INSERT OR IGNORE INTO balances(telegram_id,amount) VALUES(?,?)",
                   (tg_id, str(INITIAL_BALANCE)))
        db.execute("UPDATE sessions SET active=0 WHERE telegram_id=?", (tg_id,))
        db.execute("INSERT INTO sessions(token,telegram_id,created_at,active) VALUES(?,?,?,1)",
                   (token, tg_id, time.time()))
        balance = db.execute("SELECT amount FROM balances WHERE telegram_id=?", (tg_id,)).fetchone()["amount"]
    audit(tg_id, "login", "Sesión de demostración iniciada")
    with conn() as db:
        pref = db.execute("SELECT security_alerts FROM notification_preferences WHERE telegram_id=?", (tg_id,)).fetchone()
    if BOT_TOKEN and (pref is None or pref["security_alerts"]):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                    "chat_id": tg_id, "text": "🔐 ProEshop: se inició una nueva sesión de demostración en tu cuenta. Si no fuiste tú, cierra la sesión y revisa el acceso al bot."
                })
        except httpx.HTTPError:
            log.info("No se pudo enviar alerta de inicio de sesión")
    return {"token": token, "username": body.username, "balance": balance, "currency": CURRENCY}


@app.post("/api/logout")
async def logout(request: Request):
    tg_id = get_auth(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    with conn() as db:
        db.execute("UPDATE sessions SET active=0 WHERE token=? AND telegram_id=?", (token, tg_id))
    audit(tg_id, "logout", "Sesión cerrada")
    return {"ok": True}


@app.post("/api/search")
async def search(body: SearchBody, request: Request):
    tg_id = get_auth(request)
    platform = body.platform.lower().strip()
    query = body.query.strip()

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
        results = [{
            "title": p["name"], "price": round(float(p["price"]), 2),
            "currency": "USD", "url": "https://www.hublot.com/en-us/watches",
            "image": p.get("img", ""), "source": "Catálogo HUBLOT · modelo ilustrativo",
            "collection": p.get("collection", ""), "description": p.get("desc", "")
        } for p in matches[:52]]
        return {
            "platform": "hublot", "label": "HUBLOT", "query": query,
            "search_url": search_url, "live_results": results,
            "notice": "Catálogo local ilustrativo de ProEshop. Precios e imágenes no son cotización oficial; el 50% de descuento es simulado."
        }
    if platform == "jewelers":
        q = query.casefold().strip()
        broad_terms = {"electronics", "electronic", "todos", "todo", "all", "*", "jewelers", "jewelers toy store"}
        matches = [p for p in JEWELERS_CATALOG if q in broad_terms or any(q in str(p.get(field, "")).casefold() for field in ("name", "desc", "id"))]
        if not matches:
            matches = JEWELERS_CATALOG
        results = [{"title": p["name"], "price": round(float(p["price"]), 2), "currency": "USD", "url": p["url"], "image": "", "source": "Jewelers Toy Store · categoría Electronic", "description": p["desc"]} for p in matches]
        return {"platform":"jewelers", "label":"Jewelers Toy Store", "query":query, "search_url":search_url, "live_results":results, "notice":"Catálogo leído de la categoría Electronic del proveedor. Precios base observados: $20,500, $21,750, $295 y $395 USD; el descuento ProEshop del 50% es propio de esta miniapp, no una oferta anunciada por el proveedor. Confirma precio y disponibilidad antes de comprar."}
    if platform == "rolex":
        q = query.casefold().strip()
        broad_terms = {"rolex", "reloj", "relojes", "watch", "watches", "todos", "todo", "all", "destacados", "*"}
        matches = [p for p in ROLEX_CATALOG if q in broad_terms or any(q in str(p.get(field, "")).casefold() for field in ("name", "desc", "id"))]
        if not matches:
            matches = ROLEX_CATALOG
        results = [{"title": p["name"], "price": round(float(p["price"])*(1-float(p["discount"])/100), 2), "list_price": round(float(p["price"]), 2), "discount_percent": p["discount"], "currency":"USD", "url":p["url"], "image":p["img"], "source":"Rolex.com · precio de referencia; oferta ProEshop no oficial", "description":p["desc"]} for p in matches]
        return {"platform":"rolex", "label":"Rolex · modelos destacados", "query":query, "search_url":"https://www.rolex.com/es/watches/find-rolex?group=0", "live_results":results, "notice":"Modelos destacados del catálogo oficial; Rolex no identifica estos artículos como los más vendidos en esta página. El 40% en modelos seleccionados es una oferta propuesta por ProEshop, no una promoción oficial de Rolex. Imágenes ilustrativas; antes de vender, confirma proveedor autorizado, autenticidad, disponibilidad y precio real."}

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
    with conn() as db:
        balance = db.execute("SELECT amount FROM balances WHERE telegram_id=?", (tg_id,)).fetchone()
        cart = db.execute("SELECT * FROM carts WHERE telegram_id=? ORDER BY id DESC", (tg_id,)).fetchall()
        history = db.execute("SELECT * FROM purchases WHERE telegram_id=? ORDER BY id DESC LIMIT 50", (tg_id,)).fetchall()
        orders = db.execute("SELECT * FROM orders WHERE telegram_id=? ORDER BY created_at DESC LIMIT 50", (tg_id,)).fetchall()
        order_events = db.execute("SELECT e.* FROM order_events e JOIN orders o ON o.order_ref=e.order_ref WHERE o.telegram_id=? ORDER BY e.created_at ASC, e.id ASC", (tg_id,)).fetchall()
    return {
        "balance": balance["amount"] if balance else str(INITIAL_BALANCE),
        "currency": CURRENCY,
        "tax_rate": str(ESTIMATED_TAX_RATE),
        "shipping_fee": str(ESTIMATED_SHIPPING_FEE),
        "cart": [dict(x) for x in cart],
        "history": [dict(x) for x in history],
        "orders": [dict(x) for x in orders],
        "order_events": [dict(x) for x in order_events],
        "platforms": [{"id": k, "label": v["label"]} for k,v in PLATFORMS.items()]
    }


@app.post("/api/cart")
async def add_cart(body: AddBody, request: Request):
    tg_id = get_auth(request)
    if body.platform.lower() not in PLATFORMS:
        raise HTTPException(400, "Tienda no admitida.")
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
    if platform in {"hublot", "jewelers"}:
        price = (price / Decimal("2")).quantize(Decimal("0.01"))
    elif platform == "rolex":
        matching = next((p for p in ROLEX_CATALOG if p["name"] == body.title.strip()), None)
        if matching and matching["discount"] == 40:
            # Calculate the discount on the server from the catalog reference price.
            price = (Decimal(str(matching["price"])) * Decimal("0.60")).quantize(Decimal("0.01"))
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
    with conn() as db:
        db.execute("""INSERT INTO carts(telegram_id,platform,title,price,currency,url,qty,created_at)
                      VALUES(?,?,?,?,?,?,1,?)""",
                   (tg_id, body.platform.lower(), body.title.strip(), str(price),
                    body.currency.upper(), body.url, now_iso()))
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
        if status:
            rows = db.execute("SELECT order_ref,telegram_id,total,currency,status,created_at,updated_at,customer_email FROM orders WHERE status=? ORDER BY created_at DESC LIMIT 100", (status,)).fetchall()
        else:
            rows = db.execute("SELECT order_ref,telegram_id,total,currency,status,created_at,updated_at,customer_email FROM orders ORDER BY created_at DESC LIMIT 100").fetchall()
    return {"orders": [dict(r) for r in rows], "statuses": ORDER_STATUS_LABELS}


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
        order = db.execute("SELECT * FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
        if not order: raise HTTPException(404, "Pedido no encontrado.")
        old_status = order["status"]
        if old_status == new_status:
            return {"ok": True, "unchanged": True, "status": new_status, "email_sent": False}
        if new_status not in ORDER_TRANSITIONS.get(old_status, set()):
            raise HTTPException(409, f"Transición no permitida: {ORDER_STATUS_LABELS.get(old_status, old_status)} → {ORDER_STATUS_LABELS[new_status]}.")
        now = now_iso()
        detail = body.detail.strip() or f"Estado actualizado por administrador: {ORDER_STATUS_LABELS[new_status]}"
        db.execute("UPDATE orders SET status=?,updated_at=? WHERE order_ref=?", (new_status, now, order_ref))
        db.execute("INSERT INTO order_events(order_ref,status,label,detail,created_at) VALUES(?,?,?,?,?)",
                   (order_ref, new_status, ORDER_STATUS_LABELS[new_status], detail, now))
    audit("admin", "order_status_change", f"order={order_ref}; from={old_status}; to={new_status}")
    email_result = enqueue_and_send_order_email(order_ref, new_status, order["customer_email"], order["total"], order["currency"], detail)
    return {"ok": True, "order_ref": order_ref, "previous_status": old_status, "status": new_status,
            "status_label": ORDER_STATUS_LABELS[new_status], "email_sent": bool(email_result.get("sent")),
            "email_status": "sent" if email_result.get("sent") else email_result.get("reason", "not_configured")}


@app.post("/api/admin/orders/{order_ref}/retry-email")
async def admin_retry_order_email(order_ref: str, request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(503, "Configura ADMIN_API_KEY en Railway.")
    if not hmac.compare_digest(request.headers.get("X-Admin-Key", ""), ADMIN_API_KEY):
        raise HTTPException(403, "Clave administrativa no válida.")
    with conn() as db:
        order = db.execute("SELECT * FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
        if not order: raise HTTPException(404, "Pedido no encontrado.")
        event = db.execute("SELECT * FROM order_notifications WHERE order_ref=? AND event_key=?", (order_ref, order["status"])).fetchone()
        if not event: raise HTTPException(404, "No hay notificación registrada para el estado actual.")
        if event["status"] == "sent": return {"ok": True, "sent": True, "message": "El correo ya fue enviado."}
        db.execute("UPDATE order_notifications SET status='pending',last_error='',updated_at=? WHERE id=?", (now_iso(), event["id"]))
    result = enqueue_and_send_order_email(order_ref, order["status"], order["customer_email"], order["total"], order["currency"], "Reintento de notificación del estado actual.")
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
    <title>Recibo de prueba {esc(order_ref)}</title><style>body{{font:16px system-ui;max-width:760px;margin:40px auto;padding:20px;color:#15243b}}.tag{{display:inline-block;background:#fff0cf;padding:8px 12px;border-radius:8px;font-weight:700}}table{{width:100%;border-collapse:collapse;margin:24px 0}}td,th{{padding:12px;border-bottom:1px solid #ddd;text-align:left}}.total{{font-size:1.4rem;font-weight:800}}button{{padding:12px 16px;background:#075fc7;color:white;border:0;border-radius:8px}}@media print{{button{{display:none}}}}</style>
    <h1>ProEshop</h1><div class='tag'>RECIBO DE PRUEBA · SIN VALOR FISCAL</div><h2>Pedido {esc(order_ref)}</h2><p>Fecha: {esc(order['created_at'])}<br>Estado: {esc(ORDER_STATUS_LABELS.get(order['status'], order['status']))}</p>
    <table><thead><tr><th>Artículo</th><th>Cantidad</th><th>Total de línea</th></tr></thead><tbody>{rows}</tbody></table>
    <p>Subtotal: {esc(order['currency'])} {Decimal(order['subtotal']):.2f}</p><p>Impuestos estimados: {esc(order['currency'])} {Decimal(order['tax']):.2f}</p><p>Envío estimado: {esc(order['currency'])} {Decimal(order['shipping']):.2f}</p><p class='total'>Total estimado: {esc(order['currency'])} {Decimal(order['total']):.2f}</p>
    <p>Este documento solo registra una operación ficticia del simulador. No acredita pago, compra, envío ni obligación fiscal.</p><p>Para guardar una copia, usa la opción Imprimir del navegador y selecciona Guardar como PDF.</p></html>"""
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


@app.post("/api/purchase")
async def fictional_purchase(body: CheckoutBody, request: Request):
    tg_id = get_auth(request)
    if body.payment_method != "demo_balance":
        raise HTTPException(400, "Solo está disponible el método de pago de demostración.")
    customer_email = body.customer_email.strip().lower()
    if customer_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", customer_email):
        raise HTTPException(400, "Introduce un correo electrónico válido.")
    submitted_shipping = [body.shipping_name.strip(), body.shipping_city.strip(),
                          body.shipping_country.strip(), body.shipping_address.strip()]
    # Backward-compatible fallback for older clients that POST an empty JSON body.
    # New UI users enter explicitly fictional delivery details in the checkout form.
    if any(submitted_shipping) and not all(submitted_shipping):
        raise HTTPException(400, "Completa todos los datos de entrega de demostración.")
    if all(submitted_shipping):
        shipping_name, shipping_city, shipping_country, shipping_address = submitted_shipping
    else:
        shipping_name, shipping_city, shipping_country, shipping_address = (
            "Demo Recipient", "Demo City", "Demo Region", "Demo Address"
        )
    with conn() as db:
        rows = db.execute("SELECT * FROM carts WHERE telegram_id=? ORDER BY id", (tg_id,)).fetchall()
        if not rows:
            raise HTTPException(400, "El carrito está vacío.")
        currencies = {r["currency"] for r in rows}
        if len(currencies) != 1:
            raise HTTPException(400, "No combines monedas distintas en una misma compra ficticia.")
        subtotal = sum((Decimal(r["price"]) * r["qty"] for r in rows), Decimal("0")).quantize(Decimal("0.01"))
        tax = (subtotal * ESTIMATED_TAX_RATE).quantize(Decimal("0.01"))
        shipping = ESTIMATED_SHIPPING_FEE if subtotal > 0 else Decimal("0.00")
        total = (subtotal + tax + shipping).quantize(Decimal("0.01"))
        b = db.execute("SELECT amount FROM balances WHERE telegram_id=?", (tg_id,)).fetchone()
        balance = Decimal(b["amount"] if b else str(INITIAL_BALANCE))
        if total > balance:
            raise HTTPException(400, f"Saldo ficticio insuficiente. Total estimado {total:.2f}; saldo {balance:.2f}.")
        when = now_iso()
        order_ref = "SC-" + secrets.token_hex(5).upper()
        currency = next(iter(currencies))
        db.execute("""INSERT INTO orders(order_ref,telegram_id,subtotal,tax,shipping,total,currency,status,created_at,updated_at,
                      shipping_name,shipping_city,shipping_country,shipping_address,payment_method,customer_email)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (order_ref, tg_id, str(subtotal), str(tax), str(shipping), str(total),
                    currency, "received", when, when, shipping_name,
                    shipping_city, shipping_country, shipping_address, "demo_balance", customer_email))
        db.execute("""INSERT INTO order_events(order_ref,status,label,detail,created_at)
                      VALUES(?,?,?,?,?)""",
                   (order_ref, "received", "Pedido recibido",
                    "Pedido registrado en ProEshop; no se envió una orden al comercio ni se procesó un pago real.", when))
        for row in rows:
            line_total = (Decimal(row["price"]) * row["qty"]).quantize(Decimal("0.01"))
            db.execute("""INSERT INTO purchases(telegram_id,platform,title,price,currency,qty,total,url,purchased_at,order_ref)
                          VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (tg_id, row["platform"], row["title"], row["price"], row["currency"],
                        row["qty"], str(line_total), row["url"], when, order_ref))
        db.execute("UPDATE balances SET amount=? WHERE telegram_id=?", (str(balance-total), tg_id))
        db.execute("DELETE FROM carts WHERE telegram_id=?", (tg_id,))
    audit(tg_id, "purchase_demo", f"order={order_ref}; total={total}; currency={currency}")
    email_result = enqueue_and_send_order_email(order_ref, "received", customer_email, str(total), currency,
        "Pedido registrado en modo sin pasarela de pago; no confirma una compra ni un cobro real.") if customer_email else {"sent": False, "reason": "Sin correo proporcionado"}
    with conn() as db:
        pref = db.execute("SELECT order_updates FROM notification_preferences WHERE telegram_id=?", (tg_id,)).fetchone()
    # Telegram confirmation is best-effort and opt-out aware. This is not a real purchase.
    if BOT_TOKEN and (pref is None or pref["order_updates"]):
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                    "chat_id": tg_id,
                    "text": (f"🛍️ ShopCart — pedido de demostración\\n"
                             f"Referencia: {order_ref}\\nTotal estimado: {currency} {total:.2f}\\n"
                             "Estado: Confirmado (simulado). No se realizó ninguna compra real.")
                })
        except httpx.HTTPError:
            log.info("No se pudo enviar notificación de pedido %s", order_ref)
    return {"ok": True, "order_ref": order_ref, "subtotal": str(subtotal), "tax": str(tax),
            "shipping": str(shipping), "total": str(total), "balance": str(balance-total),
            "currency": currency, "status": "received", "purchased_at": when,
            "email_sent": bool(email_result.get("sent")),
            "email_status": "sent" if email_result.get("sent") else email_result.get("reason", "not_configured"),
            "tracking": {"available": False, "label": "No disponible hasta integrar un transportista real"},
            "message": "Pedido registrado. Este flujo aún no procesa pagos ni envía órdenes a los comercios."}
