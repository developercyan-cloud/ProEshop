
const tg = window.Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor("#075fb2");
  tg.setBackgroundColor("#f5f8fc");
}

const $ = id => document.getElementById(id);

let token = sessionStorage.getItem("shopcart_token") || "";
let selectedStore = "walmart";

let state = {
  balance: "1000.00",
  currency: "USD",
  cart: [],
  history: [],
  orders: [],
  tax_rate: "0.08",
  shipping_fee: "5.99"
};

let lastSearch = [];

const money = (v, c = "USD") =>
  `${c} ${Number(v || 0).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;

const escapeHtml = s =>
  String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[c]));

function toast(msg) {
  const el = $("toast");
  if (!el) return;

  el.textContent = msg;
  el.classList.remove("hidden");

  setTimeout(() => el.classList.add("hidden"), 2800);
}

async function api(path, opts = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {})
  };

  const r = await fetch(path, {
    ...opts,
    headers: { ...headers, ...opts.headers }
  });

  const data = await r.json().catch(() => ({
    detail: "Respuesta inválida"
  }));

  if (!r.ok) {
    throw new Error(data.detail || "Ocurrió un error");
  }

  return data;
}

/*
 * CORRECCIÓN:
 * La pantalla de Inicio es shopView.
 * No existe un elemento homeView en el HTML.
 */
function showView(view) {
  document.querySelectorAll("main .view").forEach(el => {
    el.classList.add("hidden");
  });

  const viewIds = {
    home: "shopView",
    cart: "cartView",
    history: "historyView",
    account: "accountView"
  };

  const targetId = viewIds[view];
  const target = targetId ? $(targetId) : null;

  if (!target) {
    console.error("No se encontró la vista:", view, targetId);
    return;
  }

  target.classList.remove("hidden");

  document.querySelectorAll(".nav-item").forEach(button => {
    button.classList.toggle(
      "active",
      button.dataset.tab === view
    );
  });
}

function setLoggedIn(on) {
  $("loginView")?.classList.toggle("hidden", on);
  $("shopView")?.classList.toggle("hidden", !on);
  $("bottomNav")?.classList.toggle("hidden", !on);
  $("logoutBtn")?.classList.toggle("hidden", !on);

  if (on) {
    showView("home");
  }
}

async function refresh() {
  state = await api("/api/state");

  $("balanceValue").textContent =
    money(state.balance, state.currency);

  $("accountBalance").textContent =
    money(state.balance, state.currency);

  $("cartCount").textContent =
    `${state.cart.length} artículos`;

  $("historyCount").textContent =
    `${(state.orders || []).length} pedidos`;

  $("navCartCount").textContent = state.cart.length;

  $("navCartCount").classList.toggle(
    "hidden",
    !state.cart.length
  );

  renderCart();
  renderHistory();
}

function estimateCart() {
  const subtotal = state.cart.reduce(
    (sum, item) =>
      sum + Number(item.price) * Number(item.qty || 1),
    0
  );

  const tax = subtotal * Number(state.tax_rate || 0);

  const shipping = subtotal > 0
    ? Number(state.shipping_fee || 0)
    : 0;

  return {
    subtotal,
    tax,
    shipping,
    total: subtotal + tax + shipping
  };
}

function renderCart() {
  const wrap = $("cartItems");
  if (!wrap) return;

  wrap.innerHTML = "";

  $("cartEmpty")?.classList.toggle(
    "hidden",
    !!state.cart.length
  );

  $("cartSummary")?.classList.toggle(
    "hidden",
    !state.cart.length
  );

  state.cart.forEach(item => {
    const el = document.createElement("article");
    el.className = "item-card";

    el.innerHTML = `
      <div class="item-icon">
        ${storeIcon(item.platform)}
      </div>

      <div class="item-info">
        <h3>${escapeHtml(item.title)}</h3>

        <p>
          ${escapeHtml((item.platform || "").toUpperCase())}
          · ${Number(item.qty || 1)} unidad(es)
        </p>

        <div class="item-price">
          ${money(
            Number(item.price) * Number(item.qty || 1),
            item.currency
          )}
        </div>

        <div class="item-actions">
          <a class="external"
             href="${escapeHtml(item.url)}"
             target="_blank"
             rel="noopener">
            Ver tienda ↗
          </a>

          <button class="text-btn"
                  data-remove="${escapeHtml(item.id)}">
            Quitar
          </button>
        </div>
      </div>
    `;

    wrap.appendChild(el);
  });

  const totals = estimateCart();

  if ($("cartSubtotal")) {
    $("cartSubtotal").textContent = money(totals.subtotal);
  }

  if ($("cartTax")) {
    $("cartTax").textContent = money(totals.tax);
  }

  if ($("cartShipping")) {
    $("cartShipping").textContent = money(totals.shipping);
  }

  if ($("cartTotal")) {
    $("cartTotal").textContent = money(totals.total);
  }

  if ($("cartSubtitle")) {
    $("cartSubtitle").textContent =
      `${state.cart.length} artículo(s) · ` +
      `${money(totals.total)} estimado`;
  }

  wrap.querySelectorAll("[data-remove]").forEach(button => {
    button.onclick = async () => {
      try {
        await api(
          "/api/cart/" + encodeURIComponent(button.dataset.remove),
          { method: "DELETE" }
        );

        await refresh();
      } catch (e) {
        toast(e.message);
      }
    };
  });
}

function storeIcon(store) {
  return store === "walmart"
    ? "✳"
    : store === "amazon"
      ? "a"
      : "◎";
}

function renderHistory() {
  const wrap = $("historyItems");
  if (!wrap) return;

  wrap.innerHTML = "";

  const orders = state.orders || [];

  $("historyEmpty")?.classList.toggle(
    "hidden",
    !!orders.length
  );

  orders.forEach(order => {
    const lines = (state.history || []).filter(
      item => item.order_ref === order.order_ref
    );

    const el = document.createElement("article");
    el.className = "order-card";

    const statusLabel =
      order.status === "confirmed_simulated"
        ? "Confirmado · Simulado"
        : escapeHtml(order.status || "Registrado");

    el.innerHTML = `
      <div class="order-top">
        <div>
          <small>REFERENCIA DEL PEDIDO</small>
          <strong>${escapeHtml(order.order_ref)}</strong>
        </div>
        <span class="status-pill">${statusLabel}</span>
      </div>

      <div class="order-meta">
        <span>${new Date(order.created_at).toLocaleString()}</span>
        <strong>${money(order.total, order.currency)}</strong>
      </div>

      <div class="order-breakdown">
        <span>
          Subtotal ${money(order.subtotal, order.currency)}
        </span>
        <span>
          Impuestos ${money(order.tax, order.currency)}
        </span>
        <span>
          Envío ${money(order.shipping, order.currency)}
        </span>
      </div>

      <div class="tracking-steps">
        <div class="step active">
          <i>✓</i><span>Confirmado</span>
        </div>
        <div class="step">
          <i>2</i><span>Preparación</span>
        </div>
        <div class="step">
          <i>3</i><span>En camino</span>
        </div>
        <div class="step">
          <i>4</i><span>Entregado</span>
        </div>
      </div>

      <details class="order-details">
        <summary>Ver artículos (${lines.length})</summary>

        ${
          lines.map(item => `
            <div class="order-line">
              <span>
                ${escapeHtml(item.title)}
                · ${escapeHtml(item.platform)}
              </span>
              <strong>
                ${money(item.total, item.currency)}
              </strong>
            </div>
          `).join("")
          || "<p>Detalle no disponible para pedidos anteriores a esta versión.</p>"
        }
      </details>
    `;

    wrap.appendChild(el);
  });
}

function renderResults(resultData, sort = "relevance", maxPrice = "") {
  const result = $("searchResult");
  if (!result) return;

  let items = [...lastSearch];

  if (maxPrice !== "") {
    items = items.filter(
      item => Number(item.price) <= Number(maxPrice)
    );
  }

  if (sort === "low") {
    items.sort((a, b) => Number(a.price) - Number(b.price));
  }

  if (sort === "high") {
    items.sort((a, b) => Number(b.price) - Number(a.price));
  }

  const cards = items.map((item, index) => `
    <article class="product-result">
      <img
        class="product-thumb"
        src="${escapeHtml(item.image || "")}"
        alt=""
        loading="lazy"
        onerror="this.style.display='none'"
      >

      <div class="product-result-info">
        <strong>${escapeHtml(item.title)}</strong>

        <div class="product-price">
          ${money(item.price, "USD")}
        </div>

        <small>
          ${escapeHtml(item.source || resultData.label)}
          · Precio consultado
        </small>

        <div class="product-actions">
          <a class="external"
             href="${escapeHtml(item.url)}"
             target="_blank"
             rel="noopener">
            Ver producto ↗
          </a>

          <button class="primary add-result"
                  data-index="${index}">
            Agregar
          </button>
        </div>
      </div>
    </article>
  `).join("");

  result.querySelector(".product-results")?.remove();

  if (cards) {
    const grid = document.createElement("div");
    grid.className = "product-results";
    grid.innerHTML = cards;

    const manualDetails = result.querySelector(".manual-details");

    if (manualDetails) {
      result.insertBefore(grid, manualDetails);
    } else {
      result.appendChild(grid);
    }

    grid.querySelectorAll(".add-result").forEach(button => {
      button.onclick = () => {
        const item = items[Number(button.dataset.index)];
        if (item) addItem(item);
      };
    });
  }

  const count = result.querySelector("#resultCount");

  if (count) {
    count.textContent = `${items.length} resultados`;
  }
}

async function addItem(item) {
  try {
    await api("/api/cart", {
      method: "POST",
      body: JSON.stringify({
        platform: selectedStore,
        title: item.title,
        price: String(item.price),
        currency: "USD",
        url: item.url
      })
    });

    await refresh();
    toast("Artículo agregado al carrito");
  } catch (err) {
    toast(err.message);
  }
}

/* Navegación inferior */
document.querySelectorAll("[data-tab]").forEach(button => {
  button.addEventListener("click", async () => {
    const tab = button.dataset.tab;

    if (!["home", "cart", "history", "account"].includes(tab)) {
      return;
    }

    if (tab !== "home") {
      try {
        await refresh();
      } catch (e) {
        toast(e.message);
        return;
      }
    }

    showView(tab);
  });
});

/* Selección de tienda */
document.querySelectorAll(".store").forEach(button => {
  button.onclick = () => {
    selectedStore = button.dataset.store;

    document.querySelectorAll(".store").forEach(storeButton => {
      storeButton.classList.toggle(
        "active",
        storeButton === button
      );
    });
  };
});

/* Inicio de sesión */
$("loginForm").addEventListener("submit", async event => {
  event.preventDefault();

  $("loginError").textContent = "";

  try {
    if (!tg?.initData) {
      throw new Error(
        "Abre esta miniapp desde el botón de Telegram para validar tu cuenta."
      );
    }

    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        init_data: tg.initData,
        username: $("username").value.trim(),
        password: $("password").value
      })
    });

    token = data.token;
    sessionStorage.setItem("shopcart_token", token);

    $("accountName").textContent = data.username;

    setLoggedIn(true);
    await refresh();
  } catch (err) {
    $("loginError").textContent = err.message;
  }
});

/* Búsqueda de productos */
$("searchBtn").onclick = async () => {
  const query = $("query").value.trim();

  if (!query) {
    return toast("Escribe qué artículo buscas.");
  }

  const button = $("searchBtn");
  button.disabled = true;
  button.textContent = "Buscando…";

  try {
    const data = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({
        platform: selectedStore,
        query
      })
    });

    lastSearch = data.live_results || [];

    const result = $("searchResult");
    result.classList.remove("hidden");

    result.innerHTML = `
      <div class="results-heading">
        <div>
          <h3>Resultados de ${escapeHtml(data.label)}</h3>
          <p id="resultCount">${lastSearch.length} resultados</p>
        </div>
        <span class="live-dot">USD</span>
      </div>

      <p>
        ${escapeHtml(
          data.notice ||
          "Los precios pueden variar; comprueba el total en la tienda."
        )}
      </p>

      <div class="filter-row">
        <label>
          Ordenar
          <select id="sortResults">
            <option value="relevance">Relevancia</option>
            <option value="low">Precio: menor a mayor</option>
            <option value="high">Precio: mayor a menor</option>
          </select>
        </label>

        <label>
          Precio máximo (USD)
          <input
            id="maxPrice"
            type="number"
            min="0"
            step="1"
            placeholder="Sin límite"
          >
        </label>
      </div>

      <a class="external"
         href="${escapeHtml(data.search_url)}"
         target="_blank"
         rel="noopener">
        Abrir tienda oficial ↗
      </a>

      <div class="product-results"></div>

      <details class="manual-details">
        <summary>Agregar manualmente si no aparece</summary>

        <form id="manualAdd" class="manual-form">
          <label>
            Nombre del artículo
            <input
              name="title"
              required
              maxlength="180"
              placeholder="Nombre como aparece en la tienda"
            >
          </label>

          <label>
            Precio en USD
            <input
              name="price"
              required
              type="number"
              min="0.01"
              step="0.01"
              placeholder="Ej. 49.99"
            >
          </label>

          <label>
            Enlace del producto
            <input
              name="url"
              type="url"
              required
              placeholder="https://..."
            >
          </label>

          <button class="primary full" type="submit">
            ＋ Agregar al carrito de demostración
          </button>
        </form>
      </details>
    `;

    const redraw = () => {
      renderResults(
        data,
        $("sortResults").value,
        $("maxPrice").value
      );
    };

    $("sortResults").onchange = redraw;
    $("maxPrice").oninput = redraw;

    renderResults(data);

    const manualForm = $("manualAdd");

    if (manualForm) {
      manualForm.onsubmit = async event => {
        event.preventDefault();

        const form = new FormData(event.currentTarget);

        await addItem({
          title: form.get("title"),
          price: form.get("price"),
          url: form.get("url")
        });
      };
    }
  } catch (e) {
    toast(e.message);
  } finally {
    button.disabled = false;
    button.textContent = "Buscar";
  }
};

/* Confirmación de compra de demostración */
$("buyBtn").onclick = async () => {
  const totals = estimateCart();

  const confirmed = confirm(
    `Confirmar pedido de DEMOSTRACIÓN por ${money(totals.total)} ` +
    `(subtotal ${money(totals.subtotal)}, ` +
    `impuestos estimados ${money(totals.tax)}, ` +
    `envío ${money(totals.shipping)})? ` +
    "No se realizará ninguna compra real."
  );

  if (!confirmed) return;

  try {
    const data = await api("/api/purchase", {
      method: "POST",
      body: "{}"
    });

    await refresh();

    toast(`Pedido de demostración ${data.order_ref} registrado`);
    showView("history");
  } catch (e) {
    toast(e.message);
  }
};

/* Cierre de sesión */
$("logoutBtn").onclick = async () => {
  try {
    await api("/api/logout", {
      method: "POST",
      body: "{}"
    });
  } catch {}

  token = "";
  sessionStorage.removeItem("shopcart_token");

  setLoggedIn(false);

  $("password").value = "";
  toast("Sesión cerrada");
};

/* Restaurar sesión existente */
(async () => {
  if (!token) {
    setLoggedIn(false);
    return;
  }

  try {
    setLoggedIn(true);
    await refresh();
  } catch (error) {
    token = "";
    sessionStorage.removeItem("shopcart_token");
    setLoggedIn(false);
  }
})();
