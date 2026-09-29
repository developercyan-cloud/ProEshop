import os, hmac, hashlib, json, time, secrets, sqlite3, logging, re
from urllib.parse import parse_qsl, quote_plus, urlparse
from datetime import datetime, timezone
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
DATABASE_PATH = os.getenv("DATABASE_PATH", "shopcart.db")
DEMO_USERNAME = os.getenv("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "change-me")
INITIAL_BALANCE = Decimal(os.getenv("INITIAL_FAKE_BALANCE", "1000.00"))
CURRENCY = os.getenv("CURRENCY", "USD")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", secrets.token_urlsafe(24))
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
ESTIMATED_TAX_RATE = Decimal(os.getenv("ESTIMATED_TAX_RATE", "0.08"))
ESTIMATED_SHIPPING_FEE = Decimal(os.getenv("ESTIMATED_SHIPPING_FEE", "5.99"))
SESSION_TTL = int(os.getenv("SESSION_TTL_MINUTES", "120")) * 60

app = FastAPI(title="ShopCart Telegram Mini App")
app.mount("/static", StaticFiles(directory="static"), name="static")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
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
        """)
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
        if abs(time.time() - auth_date) > 86400:
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
    return {"token": token, "username": body.username, "balance": balance, "currency": CURRENCY}


@app.post("/api/logout")
async def logout(request: Request):
    tg_id = get_auth(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    with conn() as db:
        db.execute("UPDATE sessions SET active=0 WHERE token=? AND telegram_id=?", (token, tg_id))
    return {"ok": True}


@app.post("/api/search")
async def search(body: SearchBody, request: Request):
    get_auth(request)

    platform = body.platform.lower().strip()
    query = body.query.strip()

    if platform not in PLATFORMS:
        raise HTTPException(400, "Tienda no admitida.")
    if not query:
        raise HTTPException(400, "Escribe el nombre de un producto.")

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

    domains = {
        "amazon": ("amazon.com",),
        "walmart": ("walmart.com",),
        "target": ("target.com",),
    }
    aliases = {
        "amazon": ("amazon",),
        "walmart": ("walmart",),
        "target": ("target",),
    }
    expected_domains = domains[platform]
    expected_aliases = aliases[platform]

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(45.0, connect=10.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_shopping",
                    "q": f"{query} {store['label']}",
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
        log.info(
            "SERPAPI DEBUG platform=%s total=%s sources=%s",
            platform,
            len(items),
            [str(item.get("source") or "SIN FUENTE") for item in items[:15]],
        )

        matched_results = []
        other_results = []

        for item in items[:40]:
            source = str(
                item.get("source")
                or item.get("seller")
                or item.get("merchant")
                or ""
            ).strip()
            raw_link = item.get("product_link") or item.get("link") or ""
            parsed = urlparse(raw_link)
            host = parsed.netloc.lower().split(":")[0].removeprefix("www.")

            domain_match = any(
                host == domain or host.endswith("." + domain)
                for domain in expected_domains
            )
            source_lower = source.lower()
            source_match = any(alias in source_lower for alias in expected_aliases)

            price = item.get("extracted_price")
            if isinstance(price, dict):
                price = price.get("value") or price.get("extracted_price")

            if price is None:
                raw_price = item.get("price")
                if isinstance(raw_price, dict):
                    price = raw_price.get("value") or raw_price.get("extracted_price")
                elif raw_price is not None:
                    match = re.search(
                        r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
                        str(raw_price),
                    )
                    if match:
                        price = match.group(1).replace(",", "")

            try:
                price = float(price)
            except (TypeError, ValueError):
                continue
            if not (0 < price <= 10_000_000):
                continue

            # Never label a result as belonging to the selected store unless
            # its seller or product domain actually matches. Keep an official
            # store search URL when the source is a Google Shopping redirect.
            if parsed.scheme == "https" and parsed.netloc:
                product_url = raw_link
            else:
                product_url = search_url

            product = {
                "title": str(item.get("title") or "Producto")[:180],
                "price": round(price, 2),
                "currency": "USD",
                "url": product_url,
                "image": str(item.get("thumbnail") or ""),
                "source": source or "Vendedor no identificado",
            }
            other_results.append(product)
            if domain_match or source_match:
                matched_results.append(product)

        if matched_results:
            results = matched_results[:12]
        else:
            # Show related priced results when seller identity is not explicit,
            # while clearly telling the user the store could not be verified.
            results = other_results[:12]

        log.info(
            "SEARCH COMPLETE platform=%s total=%s matched=%s fallback=%s",
            platform,
            len(results),
            len(matched_results),
            bool(results and not matched_results),
        )

        if matched_results:
            notice = (
                "Precios en USD; pueden variar por vendedor, ubicación, "
                "impuestos y disponibilidad. Confirma el precio final en la tienda."
            )
        elif results:
            notice = (
                f"No se pudo confirmar que estos productos pertenezcan a {store['label']}. "
                "Se muestran resultados relacionados de Google Shopping con su vendedor "
                "identificado. Verifica la tienda y el precio antes de comprar."
            )
        else:
            notice = (
                "Google Shopping no devolvió productos con precio verificable. "
                "Prueba otro término o abre la tienda oficial."
            )

        return {
            "platform": platform,
            "label": store["label"],
            "query": query,
            "search_url": search_url,
            "live_results": results,
            "notice": notice,
        }

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
    from urllib.parse import urlparse
    parsed = urlparse(body.url)
    allowed = {"amazon.com", "www.amazon.com", "target.com", "www.target.com",
               "walmart.com", "www.walmart.com"}
    if parsed.scheme != "https" or parsed.netloc.lower() not in allowed:
        raise HTTPException(400, "Usa un enlace HTTPS de Amazon.com, Target.com o Walmart.com.")
    with conn() as db:
        db.execute("""INSERT INTO carts(telegram_id,platform,title,price,currency,url,qty,created_at)
                      VALUES(?,?,?,?,?,?,1,?)""",
                   (tg_id, body.platform.lower(), body.title.strip(), str(price),
                    body.currency.upper(), body.url, now_iso()))
    return {"ok": True}


@app.delete("/api/cart/{item_id}")
async def remove_cart(item_id: int, request: Request):
    tg_id = get_auth(request)
    with conn() as db:
        db.execute("DELETE FROM carts WHERE id=? AND telegram_id=?", (item_id, tg_id))
    return {"ok": True}


@app.delete("/api/cart")
async def clear_cart(request: Request):
    tg_id = get_auth(request)
    with conn() as db:
        db.execute("DELETE FROM carts WHERE telegram_id=?", (tg_id,))
    return {"ok": True}


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
    # Telegram confirmation is best-effort. No message is sent if bot config is missing.
    if BOT_TOKEN:
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
