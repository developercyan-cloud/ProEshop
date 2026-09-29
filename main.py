import os, hmac, hashlib, json, time, secrets, sqlite3, logging, re
from urllib.parse import parse_qsl, quote_plus, urlparse
from datetime import datetime, timezone, timedelta
from html import escape
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
    payment_method: str = Field(default="demo_balance", max_length=32)


PLATFORMS = {
    "amazon": {"label": "Amazon", "url": "https://www.amazon.com/s?k={q}"},
    "target": {"label": "Target", "url": "https://www.target.com/s?searchTerm={q}"},
    "walmart": {"label": "Walmart", "url": "https://www.walmart.com/search?q={q}"},
}


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
    parsed = urlparse(body.url)
    host = (parsed.hostname or "").lower().rstrip(".")
    allowed_domains = {
        "amazon": ("amazon.com",),
        "target": ("target.com",),
        "walmart": ("walmart.com",),
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
    <h1>ProEshop</h1><div class='tag'>RECIBO DE PRUEBA · SIN VALOR FISCAL</div><h2>Pedido {esc(order_ref)}</h2><p>Fecha: {esc(order['created_at'])}<br>Estado: Confirmado (simulado)</p>
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
                      shipping_name,shipping_city,shipping_country,shipping_address,payment_method)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (order_ref, tg_id, str(subtotal), str(tax), str(shipping), str(total),
                    currency, "confirmed_simulated", when, when, shipping_name,
                    shipping_city, shipping_country, shipping_address, "demo_balance"))
        db.execute("""INSERT INTO order_events(order_ref,status,label,detail,created_at)
                      VALUES(?,?,?,?,?)""",
                   (order_ref, "confirmed_simulated", "Confirmado (simulado)",
                    "Pedido registrado en el simulador; no se envió una orden al comercio.", when))
        for row in rows:
            line_total = (Decimal(row["price"]) * row["qty"]).quantize(Decimal("0.01"))
            db.execute("""INSERT INTO purchases(telegram_id,platform,title,price,currency,qty,total,url,purchased_at,order_ref)
                          VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (tg_id, row["platform"], row["title"], row["price"], row["currency"],
                        row["qty"], str(line_total), row["url"], when, order_ref))
        db.execute("UPDATE balances SET amount=? WHERE telegram_id=?", (str(balance-total), tg_id))
        db.execute("DELETE FROM carts WHERE telegram_id=?", (tg_id,))
    audit(tg_id, "purchase_demo", f"order={order_ref}; total={total}; currency={currency}")
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
            "currency": currency, "status": "confirmed_simulated", "purchased_at": when,
            "tracking": {"available": False, "label": "No disponible: pedido simulado, sin transportista real"},
            "message": "Pedido de demostración registrado. No se envió ningún pedido real."}
