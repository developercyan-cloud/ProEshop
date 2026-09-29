
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

        # Migración compatible con bases de datos anteriores.
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
    """Valida initData de Telegram mediante HMAC."""
    if not BOT_TOKEN:
        raise HTTPException(503, "El bot no está configurado.")

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash")
    except Exception:
        raise HTTPException(401, "Falta initData válido de Telegram.")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(pairs.items())
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
        telegram_id = str(user["id"])

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            401,
            "No se pudo validar el usuario de Telegram."
        )

    return telegram_id, user


def get_auth(request: Request):
    token = request.headers.get(
        "Authorization", ""
    ).removeprefix("Bearer ").strip()

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
                    "drop_pending_updates": False
                }
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
    return {
        "ok": True,
        "service": "shopcart-miniapp"
    }


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
    telegram_id, telegram_user = validate_init_data(body.init_data)

    # Cuenta de acceso de demostración.
    if not (
        hmac.compare_digest(body.username, DEMO_USERNAME)
        and hmac.compare_digest(body.password, DEMO_PASSWORD)
    ):
        raise HTTPException(401, "Usuario o contraseña incorrectos.")

    token = secrets.token_urlsafe(32)

    with conn() as db:
        db.execute(
            """
            INSERT OR IGNORE INTO users
            (telegram_id, username, demo_login, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                telegram_id,
                telegram_user.get("username", ""),
                body.username,
                now_iso()
            )
        )

        db.execute(
            """
            INSERT OR IGNORE INTO balances(telegram_id, amount)
            VALUES (?, ?)
            """,
            (telegram_id, str(INITIAL_BALANCE))
        )

        db.execute(
            "UPDATE sessions SET active=0 WHERE telegram_id=?",
            (telegram_id,)
        )

        db.execute(
            """
            INSERT INTO sessions(token, telegram_id, created_at, active)
            VALUES (?, ?, ?, 1)
            """,
            (token, telegram_id, time.time())
        )

        balance = db.execute(
            "SELECT amount FROM balances WHERE telegram_id=?",
            (telegram_id,)
        ).fetchone()["amount"]

    return {
        "token": token,
        "username": body.username,
        "balance": balance,
        "currency": CURRENCY
    }


@app.post("/api/logout")
async def logout(request: Request):
    telegram_id = get_auth(request)
    token = request.headers.get(
        "Authorization", ""
    ).removeprefix("Bearer ").strip()

    with conn() as db:
        db.execute(
            "UPDATE sessions SET active=0 "
            "WHERE token=? AND telegram_id=?",
            (token, telegram_id)
        )

    return {"ok": True}


@app.post("/api/search")
async def search(body: SearchBody, request: Request):
    get_auth(request)

    platform = body.platform.lower()

    if platform not in PLATFORMS:
        raise HTTPException(400, "Tienda no admitida.")

    url = PLATFORMS[platform]["url"].format(
        q=quote_plus(body.query)
    )

    if not SERPAPI_KEY:
        return {
            "platform": platform,
            "label": PLATFORMS[platform]["label"],
            "query": body.query,
            "search_url": url,
            "live_results": [],
            "notice": (
                "Para mostrar precios automáticos en USD, configura "
                "SERPAPI_KEY en Railway. Sin esa clave puedes abrir "
                "la tienda oficial; no se inventan precios."
            )
        }

    domains = {
        "amazon": "amazon.com",
        "target": "target.com",
        "walmart": "walmart.com"
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=8.0)
        ) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_shopping",
                    "q": f"{body.query} site:{domains[platform]}",
                    "gl": "us",
                    "hl": "en",
                    "api_key": SERPAPI_KEY
                }
            )

        if response.status_code >= 400:
            log.warning(
                "Proveedor de búsqueda respondió %s",
                response.status_code
            )
            raise HTTPException(
                502,
                "El proveedor de búsqueda no respondió correctamente. "
                "Intenta de nuevo más tarde."
            )

        payload = response.json()
        results = []

        store_hosts = {
            "amazon": {"amazon.com", "www.amazon.com"},
            "target": {"target.com", "www.target.com"},
            "walmart": {"walmart.com", "www.walmart.com"}
        }

        for item in payload.get("shopping_results", [])[:12]:
            source = str(item.get("source", ""))
            link = item.get("link") or item.get("product_link") or ""
            parsed_link = urlparse(link)
            host = parsed_link.netloc.lower().split(":")[0]

            # Solo se muestran resultados asociados a la tienda elegida.
            haystack = (source + " " + link).lower()

            if (
                domains[platform] not in haystack
                and PLATFORMS[platform]["label"].lower()
                not in source.lower()
            ):
                continue

            if (
                parsed_link.scheme != "https"
                or host not in store_hosts[platform]
            ):
                link = url

            price = item.get("extracted_price")

            if price is None:
                raw = str(item.get("price", ""))
                match = re.search(
                    r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
                    raw
                )

                if match:
                    try:
                        price = float(match.group(1).replace(",", ""))
                    except ValueError:
                        price = None

            try:
                price = float(price)
                if price <= 0:
                    continue
            except (TypeError, ValueError):
                continue

            results.append({
                "title": str(item.get("title", "Producto"))[:180],
                "price": round(price, 2),
                "currency": "USD",
                "url": link,
                "image": item.get("thumbnail", ""),
                "source": source or PLATFORMS[platform]["label"]
            })

        return {
            "platform": platform,
            "label": PLATFORMS[platform]["label"],
            "query": body.query,
            "search_url": url,
            "live_results": results,
            "notice": (
                "Precios de resultados de búsqueda en USD; pueden variar "
                "según ubicación, vendedor, disponibilidad e impuestos. "
                "Verifica el precio final en el comercio."
                if results else
                "No se encontraron resultados con precio verificable "
                "para este comercio. Prueba otra búsqueda o abre "
                "la tienda oficial."
            )
        }

    except httpx.TimeoutException:
        log.warning(
            "Timeout de búsqueda en %s; se ofrece el enlace oficial",
            platform
        )

        return {
            "platform": platform,
            "label": PLATFORMS[platform]["label"],
            "query": body.query,
            "search_url": url,
            "live_results": [],
            "notice": (
                "La tienda tardó demasiado en responder. "
                "Puedes abrir la tienda oficial e intentar de nuevo."
            )
        }

    except HTTPException:
        raise

    except (httpx.HTTPError, ValueError) as exc:
        log.warning(
            "Fallo de búsqueda de productos: %s",
            type(exc).__name__
        )
        raise HTTPException(
            502,
            "No se pudo consultar el catálogo ahora. Intenta de nuevo."
        )


@app.get("/api/state")
async def state(request: Request):
    telegram_id = get_auth(request)

    with conn() as db:
        balance = db.execute(
            "SELECT amount FROM balances WHERE telegram_id=?",
            (telegram_id,)
        ).fetchone()

        cart = db.execute(
            "SELECT * FROM carts WHERE telegram_id=? ORDER BY id DESC",
            (telegram_id,)
        ).fetchall()

        history = db.execute(
            """
            SELECT * FROM purchases
            WHERE telegram_id=?
            ORDER BY id DESC LIMIT 50
            """,
            (telegram_id,)
        ).fetchall()

        orders = db.execute(
            """
            SELECT * FROM orders
            WHERE telegram_id=?
            ORDER BY created_at DESC LIMIT 50
            """,
            (telegram_id,)
        ).fetchall()

    return {
        "balance": (
            balance["amount"] if balance
            else str(INITIAL_BALANCE)
        ),
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
    telegram_id = get_auth(request)

    platform = body.platform.lower()

    if platform not in PLATFORMS:
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

    allowed_hosts = {
        "amazon.com", "www.amazon.com",
        "target.com", "www.target.com",
        "walmart.com", "www.walmart.com"
    }

    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() not in allowed_hosts
    ):
        raise HTTPException(
            400,
            "Usa un enlace HTTPS de Amazon.com, Target.com o Walmart.com."
        )

    with conn() as db:
        db.execute(
            """
            INSERT INTO carts
            (telegram_id, platform, title, price, currency, url, qty, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                telegram_id,
                platform,
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
    telegram_id = get_auth(request)

    with conn() as db:
        db.execute(
            "DELETE FROM carts WHERE id=? AND telegram_id=?",
            (item_id, telegram_id)
        )

    return {"ok": True}


@app.delete("/api/cart")
async def clear_cart(request: Request):
    telegram_id = get_auth(request)

    with conn() as db:
        db.execute(
            "DELETE FROM carts WHERE telegram_id=?",
            (telegram_id,)
        )

    return {"ok": True}


@app.post("/api/purchase")
async def fictional_purchase(request: Request):
    telegram_id = get_auth(request)

    with conn() as db:
        rows = db.execute(
            "SELECT * FROM carts WHERE telegram_id=? ORDER BY id",
            (telegram_id,)
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
            if subtotal > 0
            else Decimal("0.00")
        )

        total = (
            subtotal + tax + shipping
        ).quantize(Decimal("0.01"))

        balance_row = db.execute(
            "SELECT amount FROM balances WHERE telegram_id=?",
            (telegram_id,)
        ).fetchone()

        balance = Decimal(
            balance_row["amount"]
            if balance_row
            else str(INITIAL_BALANCE)
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
            INSERT INTO orders
            (order_ref, telegram_id, subtotal, tax, shipping, total,
             currency, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_ref,
                telegram_id,
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
                INSERT INTO purchases
                (telegram_id, platform, title, price, currency, qty,
                 total, url, purchased_at, order_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
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
            (str(balance - total), telegram_id)
        )

        db.execute(
            "DELETE FROM carts WHERE telegram_id=?",
            (telegram_id,)
        )

    # La notificación de Telegram es opcional.
    # La compra registrada es únicamente de demostración.
    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": telegram_id,
                        "text": (
                            f"🛍️ ShopCart — pedido de demostración\n"
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
