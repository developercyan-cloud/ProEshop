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
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
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
          telegram_id TEXT PRIMARY KEY,
          username TEXT,
          demo_login TEXT,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY,
          telegram_id TEXT NOT NULL,
          created_at REAL NOT NULL,
          active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS carts(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          telegram_id TEXT NOT NULL,
          platform TEXT NOT NULL,
          title TEXT NOT NULL,
          price TEXT NOT NULL,
          currency TEXT NOT NULL,
          url TEXT NOT NULL,
          qty INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS purchases(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          telegram_id TEXT NOT NULL,
          platform TEXT NOT NULL,
          title TEXT NOT NULL,
          price TEXT NOT NULL,
          currency TEXT NOT NULL,
          qty INTEGER NOT NULL,
          total TEXT NOT NULL,
          url TEXT NOT NULL,
          purchased_at TEXT NOT NULL,
          order_ref TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS orders(
          order_ref TEXT PRIMARY KEY,
          telegram_id TEXT NOT NULL,
          subtotal TEXT NOT NULL,
          tax TEXT NOT NULL,
          shipping TEXT NOT NULL,
          total TEXT NOT NULL,
          currency TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS balances(
          telegram_id TEXT PRIMARY KEY,
          amount TEXT NOT NULL
        );
        """)

        # Migración segura para bases de datos de versiones anteriores.
        purchase_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(purchases)"
            ).fetchall()
        }

        if "order_ref" not in purchase_columns:
            db.execute(
                "ALTER TABLE purchases "
                "ADD COLUMN order_ref TEXT NOT NULL DEFAULT ''"
            )


def validate_init_data(init_data: str):
    """Valida initData mediante el esquema HMAC de Telegram."""
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
        hashlib.sha256
    ).digest()

    expected = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(401, "Firma de Telegram no válida.")

    try:
        auth_date = int(pairs.get("auth_date", "0"))

        if abs(time.time() - auth_date) > 86400:
            raise HTTPException(
                401,
                "La autorización de Telegram expiró. "
                "Vuelve a abrir la miniapp."
            )

        user = json.loads(pairs["user"])
        tg_id = str(user["id"])

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            401,
            "No se pudo validar el usuario de Telegram."
        )

    return tg_id, user


def get_auth(request: Request):
    token = (
        request.headers.get("Authorization", "")
        .removeprefix("Bearer ")
        .strip()
    )

    if not token:
        raise HTTPException(401, "Inicia sesión primero.")

    with conn() as db:
        row = db.execute(
            "SELECT * FROM sessions WHERE token=? AND active=1",
            (token,)
        ).fetchone()

        if not row or time.time() - row["created_at"] > SESSION_TTL:
            if row:
                db.execute(
                    "UPDATE sessions SET active=0 WHERE token=?",
                    (token,)
                )

            raise HTTPException(
                401,
                "Sesión expirada. Inicia sesión nuevamente."
            )

        db.execute(
            "UPDATE sessions SET created_at=? WHERE token=?",
            (time.time(), token)
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


PLATFORMS = {
    "amazon": {
        "label": "Amazon",
        "url": "https://www.amazon.com/s?k={q}"
    },
    "target": {
        "label": "Target",
        "url": "https://www.target.com/s?searchTerm={q}"
    },
    "walmart": {
        "label": "Walmart",
        "url": "https://www.walmart.com/search?q={q}"
    },
}


@app.on_event("startup")
async def startup():
    init_db()

    if BOT_TOKEN and PUBLIC_BASE_URL:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={
                    "url": (
                        f"{PUBLIC_BASE_URL}/telegram-webhook/"
                        f"{WEBHOOK_SECRET}"
                    ),
                    "allowed_updates": ["message"],
                    "drop_pending_updates": False,
                },
            )

            if response.status_code >= 400:
                log.error(
                    "No se pudo configurar webhook: %s",
                    response.text[:300]
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
                "text": "🛍️ Abrir ShopCart",
                "web_app": {"url": PUBLIC_BASE_URL}
            }]]
        }

        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": (
                        "Bienvenido a ShopCart. Abre la miniapp para "
                        "buscar artículos y gestionar tu carrito ficticio."
                    ),
                    "reply_markup": keyboard
                }
            )

    return {"ok": True}


@app.post("/api/login")
async def login(body: AuthBody):
    tg_id, tg_user = validate_init_data(body.init_data)

    # Acceso local de demostración; no usar credenciales de tiendas.
    if not (
        hmac.compare_digest(body.username, DEMO_USERNAME)
        and hmac.compare_digest(body.password, DEMO_PASSWORD)
    ):
        raise HTTPException(401, "Usuario o contraseña incorrectos.")

    token = secrets.token_urlsafe(32)

    with conn() as db:
        db.execute(
            """
            INSERT OR IGNORE INTO users(
                telegram_id, username, demo_login, created_at
            ) VALUES(?,?,?,?)
            """,
            (
                tg_id,
                tg_user.get("username", ""),
                body.username,
                now_iso()
            )
        )

        db.execute(
            "INSERT OR IGNORE INTO balances(telegram_id,amount) VALUES(?,?)",
            (tg_id, str(INITIAL_BALANCE))
        )

        db.execute(
            "UPDATE sessions SET active=0 WHERE telegram_id=?",
            (tg_id,)
        )

        db.execute(
            """
            INSERT INTO sessions(token,telegram_id,created_at,active)
            VALUES(?,?,?,1)
            """,
            (token, tg_id, time.time())
        )

        balance = db.execute(
            "SELECT amount FROM balances WHERE telegram_id=?",
            (tg_id,)
        ).fetchone()["amount"]

    return {
        "token": token,
        "username": body.username,
        "balance": balance,
        "currency": CURRENCY
    }


@app.post("/api/logout")
async def logout(request: Request):
    tg_id = get_auth(request)

    token = (
        request.headers.get("Authorization", "")
        .removeprefix("Bearer ")
        .strip()
    )

    with conn() as db:
        db.execute(
            "UPDATE sessions SET active=0 "
            "WHERE token=? AND telegram_id=?",
            (token, tg_id)
        )

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
                "resultados de productos."
            )
        }

    store_domains = {
        "amazon": ("amazon.com",),
        "walmart": ("walmart.com",),
        "target": ("target.com",)
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(45.0, connect=10.0),
            follow_redirects=True
        ) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_shopping",
                    "q": query,
                    "gl": "us",
                    "hl": "en",
                    "api_key": SERPAPI_KEY
                }
            )

        response.raise_for_status()
        payload = response.json()

        # SerpApi puede devolver un error dentro de un HTTP 200.
        if payload.get("error"):
            log.warning(
                "SerpApi informó un error: %s",
                str(payload["error"])[:250]
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
                )
            }

        # Algunas respuestas pueden usar una estructura alternativa.
        items = payload.get("shopping_results") or []
        if not items:
            items = payload.get("inline_shopping_results") or []

        results = []
        expected_domains = store_domains.get(platform, ())

        for item in items[:40]:
            source = str(item.get("source") or "").strip()
            raw_link = (
                item.get("product_link")
                or item.get("link")
                or ""
            )

            parsed = urlparse(raw_link)
            host = parsed.netloc.lower().split(":")[0]
            host = host.removeprefix("www.")

            source_lower = source.lower()

            # Identificar la tienda usando tanto el dominio
            # como el nombre del vendedor.
            domain_match = any(
                host == domain or host.endswith("." + domain)
                for domain in expected_domains
            )

            source_aliases = {
                "amazon": ("amazon",),
                "walmart": ("walmart",),
                "target": ("target",)
            }

            source_match = any(
                alias in source_lower
                for alias in source_aliases.get(platform, ())
            )

            # Evitar mezclar productos de otras tiendas.
            if not domain_match and not source_match:
                continue

            # Preferir enlaces directos oficiales.
            if (
                parsed.scheme == "https"
                and any(
                    host == domain or host.endswith("." + domain)
                    for domain in expected_domains
                )
            ):
                product_url = raw_link
            else:
                product_url = search_url

            # Obtener el precio numérico cuando esté disponible.
            price = item.get("extracted_price")

            try:
                price = float(price) if price is not None else None
            except (TypeError, ValueError):
                price = None

            # Alternativa: interpretar el precio mostrado.
            if price is None:
                raw_price = str(item.get("price") or "")
                match = re.search(
                    r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
                    raw_price
                )
                if match:
                    try:
                        price = float(
                            match.group(1).replace(",", "")
                        )
                    except ValueError:
                        price = None

            # No inventar precios ni mostrar valores inválidos.
            if price is None or price <= 0:
                continue

            results.append({
                "title": str(
                    item.get("title") or "Producto"
                )[:180],
                "price": round(price, 2),
                "currency": "USD",
                "url": product_url,
                "image": str(item.get("thumbnail") or ""),
                "source": source or store["label"]
            })

            if len(results) >= 12:
                break

        log.info(
            "Búsqueda completada: tienda=%s, resultados=%s",
            platform,
            len(results)
        )

        return {
            "platform": platform,
            "label": store["label"],
            "query": query,
            "search_url": search_url,
            "live_results": results,
            "notice": (
                "Los precios están expresados en USD y pueden "
                "variar según el vendedor, la ubicación, los "
                "impuestos y la disponibilidad. Confirma el "
                "precio final en la tienda."
                if results else
                "No se encontraron productos con precio verificable "
                "para esta tienda. Prueba otro término o abre "
                "la tienda oficial."
            )
        }

    except httpx.TimeoutException:
        log.warning("Timeout de SerpApi para tienda=%s", platform)
        return {
            "platform": platform,
            "label": store["label"],
            "query": query,
            "search_url": search_url,
            "live_results": [],
            "notice": (
                "La búsqueda tardó demasiado. Intenta de nuevo "
                "o abre la tienda oficial."
            )
        }

    except httpx.HTTPStatusError as exc:
        log.warning(
            "Error HTTP de SerpApi: status=%s",
            exc.response.status_code
        )
        raise HTTPException(
            502,
            "El proveedor de búsqueda devolvió un error HTTP."
        )

    except (httpx.HTTPError, ValueError) as exc:
        log.warning(
            "Fallo de búsqueda: tipo=%s",
            type(exc).__name__
        )
        raise HTTPException(
            502,
            "No se pudo procesar la búsqueda. Intenta de nuevo."
        )


@app.get("/api/state")
async def state(request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        balance = db.execute(
            "SELECT amount FROM balances WHERE telegram_id=?",
            (tg_id,)
        ).fetchone()

        cart = db.execute(
            "SELECT * FROM carts WHERE telegram_id=? ORDER BY id DESC",
            (tg_id,)
        ).fetchall()

        history = db.execute(
            "SELECT * FROM purchases WHERE telegram_id=? "
            "ORDER BY id DESC LIMIT 50",
            (tg_id,)
        ).fetchall()

        orders = db.execute(
            "SELECT * FROM orders WHERE telegram_id=? "
            "ORDER BY created_at DESC LIMIT 50",
            (tg_id,)
        ).fetchall()

    return {
        "balance": balance["amount"] if balance else str(INITIAL_BALANCE),
        "currency": CURRENCY,
        "tax_rate": str(ESTIMATED_TAX_RATE),
        "shipping_fee": str(ESTIMATED_SHIPPING_FEE),
        "cart": [dict(item) for item in cart],
        "history": [dict(item) for item in history],
        "orders": [dict(item) for item in orders],
        "platforms": [
            {"id": key, "label": value["label"]}
            for key, value in PLATFORMS.items()
        ]
    }


@app.post("/api/cart")
async def add_cart(body: AddBody, request: Request):
    tg_id = get_auth(request)

    if body.platform.lower() not in PLATFORMS:
        raise HTTPException(400, "Tienda no admitida.")

    if body.currency.upper() != CURRENCY.upper():
        raise HTTPException(
            400,
            f"El saldo ficticio está denominado en {CURRENCY}; "
            "usa esa misma moneda."
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
            "Introduce un precio válido mayor que cero."
        )

    parsed = urlparse(body.url)
    allowed = {
        "amazon.com", "www.amazon.com",
        "target.com", "www.target.com",
        "walmart.com", "www.walmart.com"
    }

    if parsed.scheme != "https" or parsed.netloc.lower() not in allowed:
        raise HTTPException(
            400,
            "Usa un enlace HTTPS de Amazon.com, Target.com o Walmart.com."
        )

    with conn() as db:
        db.execute(
            """
            INSERT INTO carts(
                telegram_id, platform, title, price, currency,
                url, qty, created_at
            ) VALUES(?,?,?,?,?,?,1,?)
            """,
            (
                tg_id,
                body.platform.lower(),
                body.title.strip(),
                str(price),
                body.currency.upper(),
                body.url,
                now_iso()
            )
        )

    return {"ok": True}


@app.delete("/api/cart/{item_id}")
async def remove_cart(item_id: int, request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        db.execute(
            "DELETE FROM carts WHERE id=? AND telegram_id=?",
            (item_id, tg_id)
        )

    return {"ok": True}


@app.delete("/api/cart")
async def clear_cart(request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        db.execute(
            "DELETE FROM carts WHERE telegram_id=?",
            (tg_id,)
        )

    return {"ok": True}


@app.post("/api/purchase")
async def fictional_purchase(request: Request):
    tg_id = get_auth(request)

    with conn() as db:
        rows = db.execute(
            "SELECT * FROM carts WHERE telegram_id=? ORDER BY id",
            (tg_id,)
        ).fetchall()

        if not rows:
            raise HTTPException(400, "El carrito está vacío.")

        currencies = {row["currency"] for row in rows}

        if len(currencies) != 1:
            raise HTTPException(
                400,
                "No combines monedas distintas en una misma compra ficticia."
            )

        subtotal = sum(
            (
                Decimal(row["price"]) * row["qty"]
                for row in rows
            ),
            Decimal("0")
        ).quantize(Decimal("0.01"))

        tax = (
            subtotal * ESTIMATED_TAX_RATE
        ).quantize(Decimal("0.01"))

        shipping = (
            ESTIMATED_SHIPPING_FEE
            if subtotal > 0 else Decimal("0.00")
        )

        total = (
            subtotal + tax + shipping
        ).quantize(Decimal("0.01"))

        balance_row = db.execute(
            "SELECT amount FROM balances WHERE telegram_id=?",
            (tg_id,)
        ).fetchone()

        balance = Decimal(
            balance_row["amount"]
            if balance_row else str(INITIAL_BALANCE)
        )

        if total > balance:
            raise HTTPException(
                400,
                f"Saldo ficticio insuficiente. "
                f"Total estimado {total:.2f}; saldo {balance:.2f}."
            )

        when = now_iso()
        order_ref = "SC-" + secrets.token_hex(5).upper()
        currency = next(iter(currencies))

        db.execute(
            """
            INSERT INTO orders(
                order_ref, telegram_id, subtotal, tax, shipping,
                total, currency, status, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                order_ref,
                tg_id,
                str(subtotal),
                str(tax),
                str(shipping),
                str(total),
                currency,
                "confirmed_simulated",
                when,
                when
            )
        )

        for row in rows:
            line_total = (
                Decimal(row["price"]) * row["qty"]
            ).quantize(Decimal("0.01"))

            db.execute(
                """
                INSERT INTO purchases(
                    telegram_id, platform, title, price, currency,
                    qty, total, url, purchased_at, order_ref
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    tg_id,
                    row["platform"],
                    row["title"],
                    row["price"],
                    row["currency"],
                    row["qty"],
                    str(line_total),
                    row["url"],
                    when,
                    order_ref
                )
            )

        db.execute(
            "UPDATE balances SET amount=? WHERE telegram_id=?",
            (str(balance - total), tg_id)
        )

        db.execute(
            "DELETE FROM carts WHERE telegram_id=?",
            (tg_id,)
        )

    # Notificación opcional de Telegram; la compra es ficticia.
    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": tg_id,
                        "text": (
                            "🛍️ ShopCart — pedido de demostración\n"
                            f"Referencia: {order_ref}\n"
                            f"Total estimado: {currency} {total:.2f}\n"
                            "Estado: Confirmado (simulado). "
                            "No se realizó ninguna compra real."
                        )
                    }
                )

        except httpx.HTTPError:
            log.info(
                "No se pudo enviar notificación de pedido %s",
                order_ref
            )

    return {
        "ok": True,
        "order_ref": order_ref,
        "subtotal": str(subtotal),
        "tax": str(tax),
        "shipping": str(shipping),
        "total": str(total),
        "balance": str(balance - total),
        "currency": currency,
        "status": "confirmed_simulated",
        "purchased_at": when,
        "message": (
            "Pedido de demostración registrado. "
            "No se envió ningún pedido real."
        )
    }
