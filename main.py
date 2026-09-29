import os
import hmac
import hashlib
import json
import time
import secrets
import sqlite3
import logging
import re
from urllib.parse import parse_qsl, quote_plus, urlparse
from datetime import datetime, timezone, timedelta
from html import escape
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

app = FastAPI(title="ProEshop Telegram Mini App", docs_url=None, redoc_url=None)

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
            return JSONResponse(
                {"detail": "Demasiadas solicitudes. Espera un minuto e inténtalo otra vez."},
                status_code=429,
            )
        hits.append(now)
        _RATE_BUCKETS[key] = hits
        if len(_RATE_BUCKETS) > 5000:
            for old_key in list(_RATE_BUCKETS)[:1000]:
                _RATE_BUCKETS.pop(old_key, None)

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' https://telegram.org; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' https: data: blob:; "
        "connect-src 'self' https://api.telegram.org; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'",
    )
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
          token TEXT PRIMARY KEY, telegram_id TEXT NOT NULL, created_at REAL NOT NULL,
          active INTEGER NOT NULL DEFAULT 1
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
          payment_method TEXT NOT NULL DEFAULT 'demo_balance'
        );
        CREATE TABLE IF NOT EXISTS order_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, order_ref TEXT NOT NULL,
          status TEXT NOT NULL, label TEXT NOT NULL, detail TEXT NOT NULL,
          created_at TEXT NOT NULL,
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

        purchase_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(purchases)").fetchall()
        }
        if "order_ref" not in purchase_columns:
            db.execute(
                "ALTER TABLE purchases ADD COLUMN order_ref TEXT NOT NULL DEFAULT ''"
            )

        order_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(orders)").fetchall()
        }
        for column, declaration in {
            "shipping_name": "TEXT NOT NULL DEFAULT ''",
            "shipping_city": "TEXT NOT NULL DEFAULT ''",
            "shipping_country": "TEXT NOT NULL DEFAULT ''",
            "shipping_address": "TEXT NOT NULL DEFAULT ''",
            "payment_method": "TEXT NOT NULL DEFAULT 'demo_balance'",
        }.items():
            if column not in order_columns:
                db.execute(
                    f"ALTER TABLE orders ADD COLUMN {column} {declaration}"
                )


def audit(actor_id: str, action: str, detail: str = ""):
    """Store minimal audit events without passwords, tokens, or full addresses."""
    with conn() as db:
        db.execute(
            "INSERT INTO audit_log(actor_id,action,detail,created_at) VALUES(?,?,?,?)",
            (
                str(actor_id or "")[:80],
                str(action)[:80],
                str(detail)[:240],
                now_iso(),
            ),
        )


def validate_init_data(init_data: str):
    """Validate Telegram Mini App initData using Telegram's HMAC scheme."""
    if not BOT_TOKEN:
        raise HTTPException(503, "El bot no está configurado.")

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash")
    except Exception:
        raise HTTPException(401, "Falta initData válido de Telegram.")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(pairs.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256,
    ).digest()
    expected = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(401, "Firma de Telegram no válida.")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
        if time.time() - auth_date > 86400 or auth_date > time.time() + 300:
            raise HTTPException(
                401,
                "La autorización de Telegram expiró. Vuelve a abrir la miniapp.",
            )
        user = json.loads(pairs["user"])
        tg_id = str(user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            401,
            "No se pudo validar el usuario de Telegram.",
        )

    return tg_id, user


def get_auth(request: Request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Inicia sesión primero.")

    with conn() as db:
        row = db.execute(
            "SELECT * FROM sessions WHERE token=? AND active=1",
            (token,),
        ).fetchone()

        if not row or time.time() - row["created_at"] > SESSION_TTL:
            if row:
                db.execute(
                    "UPDATE sessions SET active=0 WHERE token=?",
                    (token,),
                )
            raise HTTPException(
                401,
                "Sesión expirada. Inicia sesión nuevamente.",
            )

        db.execute(
            "UPDATE sessions SET created_at=? WHERE token=?",
            (time.time(), token),
        )

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


class CheckoutBody(BaseModel):
    shipping_name: str = Field(default="", max_length=100)
    shipping_city: str = Field(default="", max_length=80)
    shipping_country: str = Field(default="", max_length=80)
    shipping_address: str = Field(default="", max_length=180)
    payment_method: str = Field(default="demo_balance", max_length=32)


PLATFORMS = {
    "amazon": {
        "label": "Amazon",
        "url": "https://www.amazon.com/s?k={q}",
        "domains": ("amazon.com",),
    },
    "target": {
        "label": "Target",
        "url": "https://www.target.com/s?searchTerm={q}",
        "domains": ("target.com",),
    },
    "walmart": {
        "label": "Walmart",
        "url": "https://www.walmart.com/search?q={q}",
        "domains": ("walmart.com",),
    },
}


def belongs_to_store(raw_url: str, platform: str) -> bool:
    """Only accept HTTPS product links on the selected retailer's own domain."""
    try:
        parsed = urlparse(raw_url)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return False

        host = parsed.hostname.lower().rstrip(".")
        allowed_domains = PLATFORMS[platform]["domains"]

        return any(
            host == domain or host.endswith("." + domain)
            for domain in allowed_domains
        )
    except (KeyError, ValueError, TypeError):
        return False


@app.on_event("startup")
async def startup():
    init_db()

    if BOT_TOKEN and PUBLIC_BASE_URL:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={
                    "url": f"{PUBLIC_BASE_URL}/telegram-webhook/{WEBHOOK_SECRET}",
                    "allowed_updates": ["message"],
                    "drop_pending_updates": False,
                },
            )
            if response.status_code >= 400:
                log.error(
                    "No se pudo configurar webhook: %s",
                    response.text[:300],
                )


@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", encoding="utf-8") as file:
        return HTMLResponse(file.read())


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
        keyboard = {
            "inline_keyboard": [[{
                "text": "🛍️ Abrir ProEshop",
                "web_app": {"url": PUBLIC_BASE_URL},
            }]]
        }

        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": (
                        "Bienvenido a ProEshop. Busca productos y compara "
                        "resultados de las tiendas disponibles."
                    ),
                    "reply_markup": keyboard,
                },
            )

    return {"ok": True}


@app.post("/api/login")
async def login(body: AuthBody):
    tg_id, tg_user = validate_init_data(body.init_data)

    if not (
        hmac.compare_digest(body.username, DEMO_USERNAME)
        and hmac.compare_digest(body.password, DEMO_PASSWORD)
    ):
        raise HTTPException(401, "Usuario o contraseña incorrectos.")

    token = secrets.token_urlsafe(32)

    with conn() as db:
        db.execute(
            "INSERT OR IGNORE INTO users(telegram_id,username,demo_login,created_at) "
            "VALUES(?,?,?,?)",
            (tg_id, tg_user.get("username", ""), body.username, now_iso()),
        )
        db.execute(
            "INSERT OR IGNORE INTO balances(telegram_id,amount) VALUES(?,?)",
            (tg_id, str(INITIAL_BALANCE)),
        )
        db.execute(
            "UPDATE sessions SET active=0 WHERE telegram_id=?",
            (tg_id,),
        )
        db.execute(
            "INSERT INTO sessions(token,telegram_id,created_at,active) VALUES(?,?,?,1)",
            (token, tg_id, time.time()),
        )
        balance = db.execute(
            "SELECT amount FROM balances WHERE telegram_id=?",
            (tg_id,),
        ).fetchone()["amount"]

    audit(tg_id, "login", "Sesión de demostración iniciada")

    with conn() as db:
        pref = db.execute(
            "SELECT security_alerts FROM notification_preferences WHERE telegram_id=?",
            (tg_id,),
        ).fetchone()

    if BOT_TOKEN and (pref is None or pref["security_alerts"]):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": tg_id,
                        "text": (
                            "🔐 ProEshop: se inició una nueva sesión de "
                            "demostración en tu cuenta."
                        ),
                    },
                )
        except httpx.HTTPError:
            log.info("No se pudo enviar alerta de inicio de sesión")

    return {
        "token": token,
        "username": body.username,
        "balance": balance,
        "currency": CURRENCY,
    }


@app.post("/api/logout")
async def logout(request: Request):
    tg_id = get_auth(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()

    with conn() as db:
        db.execute(
            "UPDATE sessions SET active=0 WHERE token=? AND telegram_id=?",
            (token, tg_id),
        )

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

    audit(
        tg_id,
        "search",
        f"platform={platform}; query_length={len(query)}",
    )

    store = PLATFORMS[platform]
    search_url = store["url"].format(q=quote_plus(query))

    if not SERPAPI_KEY:
        return {
            "platform": platform,
            "label": store["label"],
            "query": query,
            "search_url": search_url,
            "live_results": [],
            "notice": (
                "Configura SERPAPI_KEY en Railway para consultar "
                "productos y precios."
            ),
        }

    cache_key = (platform, query.casefold())
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and time.time() - cached["timestamp"] < 90:
        return cached["data"]

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(35.0, connect=10.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_shopping",
                    "q": query,
                    "google_domain": "google.com",
                    "gl": "us",
                    "hl": "en",
                    "api_key": SERPAPI_KEY,
                },
            )

        response.raise_for_status()
        payload = response.json()

        if payload.get("error"):
            log.warning(
                "SerpApi error platform=%s error=%s",
                platform,
                str(payload["error"])[:200],
            )
            return {
                "platform": platform,
                "label": store["label"],
                "query": query,
                "search_url": search_url,
                "live_results": [],
                "notice": (
                    "El proveedor de búsqueda informó un problema. "
                    "Intenta de nuevo más tarde."
                ),
            }

        items = (
            payload.get("shopping_results")
            or payload.get("inline_shopping_results")
            or []
        )

        matched_results = []

        for item in items[:60]:
            raw_link = (
                item.get("product_link")
                or item.get("link")
                or item.get("product_url")
                or ""
            )

            # No basta con que Google muestre el nombre de Amazon o Target:
            # el enlace debe pertenecer al dominio oficial de la tienda elegida.
            if not belongs_to_store(raw_link, platform):
                continue

            title = str(item.get("title") or "").strip()
            if not title:
                continue

            raw_price = item.get("extracted_price")
            if isinstance(raw_price, dict):
                raw_price = (
                    raw_price.get("value")
                    or raw_price.get("extracted_price")
                )

            if raw_price is None:
                raw_price = item.get("price")
                if isinstance(raw_price, dict):
                    raw_price = (
                        raw_price.get("value")
                        or raw_price.get("extracted_price")
                    )
                elif raw_price is not None:
                    match = re.search(
                        r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
                        str(raw_price),
                    )
                    raw_price = (
                        match.group(1).replace(",", "")
                        if match else None
                    )

            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                continue

            if not 0 < price <= 10_000_000:
                continue

            product = {
                "title": title[:180],
                "price": round(price, 2),
                "currency": "USD",
                "url": raw_link,
                "image": str(item.get("thumbnail") or ""),
                "source": store["label"],
            }

            matched_results.append(product)

        # Deduplicar por URL sin aceptar enlaces de otros comercios.
        seen_urls = set()
        results = []
        for item in matched_results:
            normalized_url = item["url"].split("#", 1)[0].rstrip("/")
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            results.append(item)
            if len(results) >= 12:
                break

        if results:
            notice = (
                "Resultados filtrados por dominio oficial. Los precios, "
                "impuestos, disponibilidad y envío pueden variar; "
                "confirma el precio final en la tienda."
            )
        else:
            notice = (
                f"No se encontraron productos verificables con enlaces "
                f"directos a {store['label']}. Se ocultaron los resultados "
                "de otras tiendas. Prueba otro término o abre la tienda oficial."
            )

        data = {
            "platform": platform,
            "label": store["label"],
            "query": query,
            "search_url": search_url,
            "live_results": results,
            "notice": notice,
        }

        _SEARCH_CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": data,
        }

        # Limpiar entradas antiguas de caché.
        if len(_SEARCH_CACHE) > 500:
            now = time.time()
            for key in list(_SEARCH_CACHE):
                entry = _SEARCH_CACHE.get(key)
                if not entry or now - entry["timestamp"] > 300:
                    _SEARCH_CACHE.pop(key, None)

        return data

    except httpx.TimeoutException:
        log.warning("SERPAPI TIMEOUT platform=%s", platform)
        return {
            "platform": platform,
            "label": store["label"],
            "query": query,
            "search_url": search_url,
            "live_results": [],
            "notice": (
                "La búsqueda tardó demasiado. Intenta de nuevo "
                "o abre la tienda oficial."
            ),
        }
    except httpx.HTTPStatusError as exc:
        log.warning(
            "SERPAPI HTTP ERROR platform=%s status=%s",
            platform,
            exc.response.status_code,
        )
        raise HTTPException(
            502,
            "El proveedor de búsqueda devolvió un error HTTP.",
        )
    except (httpx.HTTPError, ValueError) as exc:
        log.warning(
            "SEARCH ERROR platform=%s type=%s",
            platform,
            type(exc).__name__,
        )
        raise HTTPException(
            502,
            "No se pudo procesar la búsqueda. Intenta nuevamente.",
        )


@app.get("/api/state")
async def state(request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        balance = db.execute(
            "SELECT amount FROM balances WHERE telegram_id=?",
            (tg_id,),
        ).fetchone()
        cart = db.execute(
            "SELECT * FROM carts WHERE telegram_id=? ORDER BY id DESC",
            (tg_id,),
        ).fetchall()
        history = db.execute(
            "SELECT * FROM purchases WHERE telegram_id=? ORDER BY id DESC LIMIT 50",
            (tg_id,),
        ).fetchall()
        orders = db.execute(
            "SELECT * FROM orders WHERE telegram_id=? ORDER BY created_at DESC LIMIT 50",
            (tg_id,),
        ).fetchall()
        order_events = db.execute(
            "SELECT e.* FROM order_events e "
            "JOIN orders o ON o.order_ref=e.order_ref "
            "WHERE o.telegram_id=? ORDER BY e.created_at ASC, e.id ASC",
            (tg_id,),
        ).fetchall()

    return {
        "balance": balance["amount"] if balance else str(INITIAL_BALANCE),
        "currency": CURRENCY,
        "tax_rate": str(ESTIMATED_TAX_RATE),
        "shipping_fee": str(ESTIMATED_SHIPPING_FEE),
        "cart": [dict(x) for x in cart],
        "history": [dict(x) for x in history],
        "orders": [dict(x) for x in orders],
        "order_events": [dict(x) for x in order_events],
        "platforms": [
            {"id": key, "label": value["label"]}
            for key, value in PLATFORMS.items()
        ],
    }


@app.post("/api/cart")
async def add_cart(body: AddBody, request: Request):
    tg_id = get_auth(request)
    platform = body.platform.lower().strip()

    if platform not in PLATFORMS:
        raise HTTPException(400, "Tienda no admitida.")
    if body.currency.upper() != CURRENCY.upper():
        raise HTTPException(
            400,
            f"El saldo ficticio está denominado en {CURRENCY}; usa esa misma moneda.",
        )

    try:
        price = Decimal(body.price).quantize(Decimal("0.01"))
        if (
            not price.is_finite()
            or price <= 0
            or price > Decimal("10000000")
        ):
            raise InvalidOperation()
    except (InvalidOperation, ValueError):
        raise HTTPException(
            400,
            "Introduce un precio válido mayor que cero.",
        )

    if not belongs_to_store(body.url, platform):
        raise HTTPException(
            400,
            "El enlace no pertenece al dominio oficial de la tienda seleccionada.",
        )

    with conn() as db:
        db.execute(
            "INSERT INTO carts(telegram_id,platform,title,price,currency,url,qty,created_at) "
            "VALUES(?,?,?,?,?,?,1,?)",
            (
                tg_id,
                platform,
                body.title.strip(),
                str(price),
                body.currency.upper(),
                body.url,
                now_iso(),
            ),
        )

    audit(tg_id, "cart_add", f"platform={platform}; price={price}")
    return {"ok": True}


@app.put("/api/cart/{item_id}")
async def update_cart(item_id: int, body: QtyBody, request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        cur = db.execute(
            "UPDATE carts SET qty=? WHERE id=? AND telegram_id=?",
            (body.qty, item_id, tg_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(
                404,
                "Artículo no encontrado en tu carrito.",
            )

    audit(tg_id, "cart_qty", f"item={item_id}; qty={body.qty}")
    return {"ok": True, "qty": body.qty}


@app.delete("/api/cart/{item_id}")
async def remove_cart(item_id: int, request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        cur = db.execute(
            "DELETE FROM carts WHERE id=? AND telegram_id=?",
            (item_id, tg_id),
        )

    if cur.rowcount:
        audit(tg_id, "cart_remove", f"item={item_id}")

    return {"ok": True}


@app.delete("/api/cart")
async def clear_cart(request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        db.execute(
            "DELETE FROM carts WHERE telegram_id=?",
            (tg_id,),
        )

    return {"ok": True}


@app.get("/api/notifications")
async def get_notifications(request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        row = db.execute(
            "SELECT * FROM notification_preferences WHERE telegram_id=?",
            (tg_id,),
        ).fetchone()

    return {
        "order_updates": bool(row["order_updates"]) if row else True,
        "security_alerts": bool(row["security_alerts"]) if row else True,
        "telegram_configured": bool(BOT_TOKEN),
    }


@app.post("/api/notifications")
async def set_notifications(body: NotificationBody, request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        db.execute(
            """
            INSERT INTO notification_preferences(
                telegram_id,order_updates,security_alerts,updated_at
            ) VALUES(?,?,?,?)
            ON CONFLICT(telegram_id) DO UPDATE SET
              order_updates=excluded.order_updates,
              security_alerts=excluded.security_alerts,
              updated_at=excluded.updated_at
            """,
            (
                tg_id,
                int(body.order_updates),
                int(body.security_alerts),
                now_iso(),
            ),
        )

    audit(
        tg_id,
        "notification_preferences",
        f"orders={int(body.order_updates)}; security={int(body.security_alerts)}",
    )

    return {
        "ok": True,
        "order_updates": body.order_updates,
        "security_alerts": body.security_alerts,
        "telegram_configured": bool(BOT_TOKEN),
    }


@app.get("/api/orders/{order_ref}/receipt", response_class=HTMLResponse)
async def receipt(order_ref: str, request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        order = db.execute(
            "SELECT * FROM orders WHERE order_ref=? AND telegram_id=?",
            (order_ref, tg_id),
        ).fetchone()
        if not order:
            raise HTTPException(404, "Recibo no encontrado.")

        lines = db.execute(
            "SELECT * FROM purchases WHERE order_ref=? AND telegram_id=? ORDER BY id",
            (order_ref, tg_id),
        ).fetchall()

    esc = lambda value: escape(str(value or ""))
    rows = "".join(
        f"<tr><td>{esc(item['title'])}</td>"
        f"<td>{int(item['qty'])}</td>"
        f"<td>{esc(item['currency'])} {Decimal(item['total']):.2f}</td></tr>"
        for item in lines
    )

    page = f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recibo de prueba {esc(order_ref)}</title>
<style>
body{{font:16px system-ui;max-width:760px;margin:40px auto;padding:20px;color:#15243b}}
.tag{{display:inline-block;background:#fff0cf;padding:8px 12px;border-radius:8px;font-weight:700}}
table{{width:100%;border-collapse:collapse;margin:24px 0}}
td,th{{padding