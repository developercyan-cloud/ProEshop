const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); tg.setHeaderColor("#075fb2"); tg.setBackgroundColor("#f5f8fc"); }
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem("shopcart_token") || "";
let selectedStore = "walmart";
let state = {balance:"1000.00",currency:"USD",cart:[],history:[],orders:[],tax_rate:"0.08",shipping_fee:"5.99"};
let lastSearch = [];
const money = (v,c="USD") => `${c} ${Number(v||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const escapeHtml = s => String(s??"").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function toast(msg){$("toast").textContent=msg;$("toast").classList.remove("hidden");setTimeout(()=>$("toast").classList.add("hidden"),2800)}
async function api(path,opts={}){const headers={"Content-Type":"application/json",...(token?{"Authorization":`Bearer ${token}`}:{})};const r=await fetch(path,{...opts,headers:{...headers,...opts.headers}});const data=await r.json().catch(()=>({detail:"Respuesta inválida"}));if(!r.ok)throw new Error(data.detail||"Ocurrió un error");return data}
function showView(view){document.querySelectorAll("main .view").forEach(v=>v.classList.add("hidden"));$(view+"View").classList.remove("hidden");document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.tab===view));}
function setLoggedIn(on){$("loginView").classList.toggle("hidden",on);$("shopView").classList.toggle("hidden",!on);$("bottomNav").classList.toggle("hidden",!on);$("logoutBtn").classList.toggle("hidden",!on);if(on)showView("home");}
async function refresh(){state=await api("/api/state");$("balanceValue").textContent=money(state.balance,state.currency);$("accountBalance").textContent=money(state.balance,state.currency);$("cartCount").textContent=`${state.cart.length} artículos`;$("historyCount").textContent=`${(state.orders||[]).length} pedidos`;$("navCartCount").textContent=state.cart.length;$("navCartCount").classList.toggle("hidden",!state.cart.length);renderCart();renderHistory();}
function estimateCart(){const subtotal=state.cart.reduce((sum,x)=>sum+Number(x.price)*Number(x.qty||1),0);const tax=subtotal*Number(state.tax_rate||0);const shipping=subtotal>0?Number(state.shipping_fee||0):0;return {subtotal,tax,shipping,total:subtotal+tax+shipping};}
function renderCart(){
 const wrap=$("cartItems");wrap.innerHTML="";$("cartEmpty").classList.toggle("hidden",!!state.cart.length);$("cartSummary").classList.toggle("hidden",!state.cart.length);
 state.cart.forEach(x=>{const el=document.createElement("article");el.className="item-card";el.innerHTML=`<div class="item-icon">${storeIcon(x.platform)}</div><div class="item-info"><h3>${escapeHtml(x.title)}</h3><p>${escapeHtml(x.platform.toUpperCase())} · ${Number(x.qty||1)} unidad(es)</p><div class="item-price">${money(Number(x.price)*Number(x.qty||1),x.currency)}</div><div class="item-actions"><a class="external" href="${escapeHtml(x.url)}" target="_blank" rel="noopener">Ver tienda ↗</a><button class="text-btn" data-remove="${x.id}">Quitar</button></div></div>`;wrap.appendChild(el)});
 const totals=estimateCart();$("cartSubtotal").textContent=money(totals.subtotal);$("cartTax").textContent=money(totals.tax);$("cartShipping").textContent=money(totals.shipping);$("cartTotal").textContent=money(totals.total);$("cartSubtitle").textContent=`${state.cart.length} artículo(s) · ${money(totals.total)} estimado`;
 wrap.querySelectorAll("[data-remove]").forEach(b=>b.onclick=async()=>{try{await api("/api/cart/"+b.dataset.remove,{method:"DELETE"});await refresh()}catch(e){toast(e.message)}});
}
function storeIcon(s){return s==="walmart"?"✳":s==="amazon"?"a":"◎"}
function renderHistory(){
 const wrap=$("historyItems");wrap.innerHTML="";const orders=state.orders||[];$("historyEmpty").classList.toggle("hidden",!!orders.length);
 orders.forEach(order=>{
  const lines=(state.history||[]).filter(x=>x.order_ref===order.order_ref);
  const el=document.createElement("article");el.className="order-card";
  const statusLabel=order.status==="confirmed_simulated"?"Confirmado · Simulado":escapeHtml(order.status||"Registrado");
  el.innerHTML=`<div class="order-top"><div><small>REFERENCIA DEL PEDIDO</small><strong>${escapeHtml(order.order_ref)}</strong></div><span class="status-pill">${statusLabel}</span></div>
  <div class="order-meta"><span>${new Date(order.created_at).toLocaleString()}</span><strong>${money(order.total,order.currency)}</strong></div>
  <div class="order-breakdown"><span>Subtotal ${money(order.subtotal,order.currency)}</span><span>Impuestos ${money(order.tax,order.currency)}</span><span>Envío ${money(order.shipping,order.currency)}</span></div>
  <div class="tracking-steps"><div class="step active"><i>✓</i><span>Confirmado</span></div><div class="step"><i>2</i><span>Preparación</span></div><div class="step"><i>3</i><span>En camino</span></div><div class="step"><i>4</i><span>Entregado</span></div></div>
  <details class="order-details"><summary>Ver artículos (${lines.length})</summary>${lines.map(x=>`<div class="order-line"><span>${escapeHtml(x.title)} · ${escapeHtml(x.platform)}</span><strong>${money(x.total,x.currency)}</strong></div>`).join("")||"<p>Detalle no disponible para pedidos anteriores a esta versión.</p>"}</details>`;
  wrap.appendChild(el);
 });
}
function renderResults(r,sort="relevance",maxPrice=""){
 const result=$("searchResult");let items=[...lastSearch];
 if(maxPrice!=="")items=items.filter(x=>Number(x.price)<=Number(maxPrice));
 if(sort==="low")items.sort((a,b)=>a.price-b.price);if(sort==="high")items.sort((a,b)=>b.price-a.price);
 const cards=items.map((x,i)=>`<article class="product-result"><div class="product-media">${x.image?`<img class="product-thumb" src="${escapeHtml(x.image)}" alt="Imagen del producto" loading="lazy" onerror="this.style.display='none'">`:`<div class="product-placeholder" aria-hidden="true">▧</div>`}</div><div class="product-result-info"><strong>${escapeHtml(x.title)}</strong><div class="product-price">${money(x.price,"USD")}</div><small>${escapeHtml(x.source||r.label)} · Precio consultado</small><div class="product-actions"><a class="external" href="${escapeHtml(x.url)}" target="_blank" rel="noopener">Ver producto ↗</a><button class="primary add-result" data-index="${i}">＋ Agregar</button></div></div></article>`).join("");
 result.querySelector(".product-results")?.remove();
 const grid=document.createElement("div");grid.className="product-results";grid.innerHTML=cards||`<div class="empty"><div>⌕</div><strong>No hay resultados con estos filtros</strong><p>Prueba con otro precio máximo o cambia la búsqueda.</p></div>`;result.insertBefore(grid,result.querySelector(".manual-details"));
 grid.querySelectorAll(".add-result").forEach(b=>b.onclick=()=>{const item=items[Number(b.dataset.index)];if(item)addItem(item)});
 const count=result.querySelector("#resultCount");if(count)count.textContent=`${items.length} ${items.length===1?"resultado":"resultados"}`;
}
async function addItem(item){try{await api("/api/cart",{method:"POST",body:JSON.stringify({platform:selectedStore,title:item.title,price:String(item.price),currency:"USD",url:item.url})});await refresh();toast("Artículo agregado al carrito")}catch(err){toast(err.message)}}
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",async()=>{const tab=b.dataset.tab;if(["home","cart","history","account"].includes(tab)){if(tab!=="home")try{await refresh()}catch(e){toast(e.message);return}showView(tab)}}));
document.querySelectorAll(".store").forEach(b=>b.onclick=()=>{selectedStore=b.dataset.store;document.querySelectorAll(".store").forEach(x=>x.classList.toggle("active",x===b))});
$("loginForm").addEventListener("submit",async e=>{e.preventDefault();$("loginError").textContent="";try{if(!tg?.initData)throw new Error("Abre esta miniapp desde el botón de Telegram para validar tu cuenta.");const data=await api("/api/login",{method:"POST",body:JSON.stringify({init_data:tg.initData,username:$("username").value.trim(),password:$("password").value})});token=data.token;sessionStorage.setItem("shopcart_token",token);$("accountName").textContent=data.username;setLoggedIn(true);await refresh()}catch(err){$("loginError").textContent=err.message}});
$("searchBtn").onclick=async()=>{
 const query=$("query").value.trim();if(!query)return toast("Escribe qué artículo buscas.");
 const btn=$("searchBtn");btn.disabled=true;btn.textContent="Buscando…";
 try{
  const r=await api("/api/search",{method:"POST",body:JSON.stringify({platform:selectedStore,query})});lastSearch=r.live_results||[];
  const result=$("searchResult");result.classList.remove("hidden");
  result.innerHTML=`<div class="results-heading"><div><h3>Resultados de ${escapeHtml(r.label)}</h3><p id="resultCount">${lastSearch.length} ${lastSearch.length===1?"resultado":"resultados"}</p></div><span class="live-dot">PRECIOS USD</span></div>
  <p>${escapeHtml(r.notice||"Los precios pueden variar; comprueba el total en la tienda.")}</p>
  <div class="filter-row"><label>Ordenar<select id="sortResults"><option value="relevance">Relevancia</option><option value="low">Menor precio</option><option value="high">Mayor precio</option></select></label><label>Precio máximo (USD)<input id="maxPrice" type="number" min="0" step="1" placeholder="Sin límite"></label></div>
  <a class="external" href="${escapeHtml(r.search_url)}" target="_blank" rel="noopener">Abrir tienda oficial ↗</a>
  <div class="product-results"></div>
  <details class="manual-details"><summary>Agregar manualmente si no aparece</summary><form id="manualAdd" class="manual-form"><label>Nombre del artículo<input name="title" required maxlength="180" placeholder="Nombre como aparece en la tienda"></label><label>Precio en USD<input name="price" required type="number" min="0.01" step="0.01" placeholder="Ej. 49.99"></label><label>Enlace del producto<input name="url" type="url" required placeholder="https://..."></label><button class="primary full" type="submit">＋ Agregar al carrito de demostración</button></form></details>`;
  const redraw=()=>renderResults(r,$("sortResults").value,$("maxPrice").value);$("sortResults").onchange=redraw;$("maxPrice").oninput=redraw;renderResults(r);
  const manual=$("manualAdd");if(manual)manual.onsubmit=async ev=>{ev.preventDefault();const f=new FormData(ev.currentTarget);await addItem({title:f.get("title"),price:f.get("price"),url:f.get("url")});};
 }catch(e){toast(e.message)}finally{btn.disabled=false;btn.textContent="Buscar"}
};
$("buyBtn").onclick=async()=>{
 const t=estimateCart();if(!confirm(`Confirmar pedido de DEMOSTRACIÓN por ${money(t.total)} (subtotal ${money(t.subtotal)}, impuestos estimados ${money(t.tax)}, envío ${money(t.shipping)})? No se realizará ninguna compra real.`))return;
 try{const r=await api("/api/purchase",{method:"POST",body:"{}"});await refresh();toast(`Pedido de demostración ${r.order_ref} registrado`);showView("history")}catch(e){toast(e.message)}
};
$("logoutBtn").onclick=async()=>{try{await api("/api/logout",{method:"POST",body:"{}"})}catch{}token="";sessionStorage.removeItem("shopcart_token");setLoggedIn(false);$("password").value="";toast("Sesión cerrada")};
(async()=>{if(token){try{setLoggedIn(true);await refresh()}catch{token="";sessionStorage.removeItem("shopcart_token");setLoggedIn(false)}}})();
