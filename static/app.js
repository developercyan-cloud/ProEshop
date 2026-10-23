'use strict';
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); try { tg.setHeaderColor('#11152b'); tg.setBackgroundColor('#0b0e1b'); } catch (_) {} }
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('shopcart_token') || '';
let authAccountType = sessionStorage.getItem('shopcart_account_type') || '';
let authDisplayName = sessionStorage.getItem('shopcart_display_name') || '';
let selectedStore = 'rolex';
let state = {balance:'1000.00',currency:'USD',cart:[],history:[],orders:[],tax_rate:'0.08',shipping_fee:'5.99'};
let lastSearch = [], lastSearchResponse = null, currentResults = [], favorites = new Set(), compareItems = new Map(), searchBusy = false, adminKey = '', checkoutSubmitting = false, cryptoPaymentInterval = null, cryptoCountdownInterval = null, orderCountdownInterval = null, activeCryptoDeadline = 0, activeCryptoOrder = '', cryptoQuoteCartSignature = '';  
const money = (v,c='USD') => `${c} ${Number(v||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const escapeHtml = s => String(s??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const storeLabel = s => ({amazon:'Amazon',walmart:'Walmart',target:'Target',hublot:'HUBLOT',jewelers:'Joyería',canam:'Can-Am',rolex:'Rolex'}[String(s||'').toLowerCase()]||'Tienda');
function toast(msg){ const el=$('toast'); if(!el)return; el.textContent=msg;el.classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.add('hidden'),3000); }
async function api(path,opts={}){const headers={'Content-Type':'application/json',...(token?{'Authorization':`Bearer ${token}`}:{})};const r=await fetch(path,{...opts,headers:{...headers,...opts.headers}});const data=await r.json().catch(()=>({detail:'Respuesta inválida del servidor.'}));if(!r.ok){if(r.status===401&&token){token='';sessionStorage.removeItem('shopcart_token');setLoggedIn(false)}throw new Error(data.detail||data.error||'Ocurrió un error. Intenta nuevamente.')}return data;}
function showView(view){if(view==='search'){showView('home');setTimeout(()=>$('query')?.focus(),100);return;}const ids={home:'shopView',cart:'cartView',checkout:'checkoutView',history:'historyView',account:'accountView'};document.querySelectorAll('main .view').forEach(v=>v.classList.add('hidden'));const target=$(ids[view]||`${view}View`);if(!target){console.error('Vista no encontrada:',view);return;}target.classList.remove('hidden');document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.tab===(view==='checkout'?'cart':view)));if(view==='home')setStoreContent(selectedStore);window.scrollTo({top:0,behavior:'smooth'});}
function setLoggedIn(on){$('loginView').classList.toggle('hidden',on);$('shopView').classList.toggle('hidden',!on);$('bottomNav').classList.toggle('hidden',!on);$('logoutBtn').classList.toggle('hidden',!on);if(on)showView('home');}
async function refresh(){state=await api('/api/state');$('balanceValue').textContent=window.proEshopWalletConnected?window.proEshopWalletBalanceDisplay:'Conecta tu billetera';$('accountBalance').textContent=money(state.balance,state.currency);$('cartCount').textContent=`${state.cart.length} artículo${state.cart.length===1?'':'s'}`;$('historyCount').textContent=`${(state.orders||[]).length} pedido${(state.orders||[]).length===1?'':'s'}`;$('orderCountLabel').textContent=`${(state.orders||[]).length} pedido${(state.orders||[]).length===1?'':'s'}`;$('navCartCount').textContent=state.cart.length;$('navCartCount').classList.toggle('hidden',!state.cart.length);$('greetingName').textContent=authDisplayName||'bienvenido';$('accountName').textContent=authDisplayName||'Sesión activa';renderCart();renderHistory();}
function estimateCart(){const subtotal=state.cart.reduce((sum,x)=>sum+Number(x.price)*Number(x.qty||1),0);const tax=subtotal*Number(state.tax_rate||0);const shipping=subtotal>0?Number(state.shipping_fee||0):0;return {subtotal,tax,shipping,total:subtotal+tax+shipping};}
function cartSignature(){return JSON.stringify((state.cart||[]).map(x=>({id:String(x.id),platform:String(x.platform||''),price:Number(x.price)||0,qty:Number(x.qty)||1,title:String(x.title||'')})).sort((a,b)=>a.id.localeCompare(b.id)));}
function storeIcon(s){return s==='walmart'?'✳':s==='amazon'?'a':s==='target'?'◎':s==='hublot'?'H':s==='jewelers'?'◇':s==='canam'?'C':s==='rolex'?'R':'▧';}
function renderCart(){const wrap=$('cartItems');wrap.innerHTML='';$('cartEmpty').classList.toggle('hidden',!!state.cart.length);$('cartSummary').classList.toggle('hidden',!state.cart.length);state.cart.forEach(x=>{const el=document.createElement('article');el.className='item-card';el.innerHTML=`<div class="item-icon">${x.image?`<img class="cart-product-image" src="${escapeHtml(x.image)}" alt="${escapeHtml(x.title)}" loading="lazy" referrerpolicy="no-referrer">`:`<span>${storeIcon(x.platform)}</span>`}</div><div class="item-info"><h3>${escapeHtml(x.title)}</h3><p>${escapeHtml(storeLabel(x.platform))} · ${Number(x.qty||1)} unidad(es)</p><div class="item-price">${['hublot','jewelers'].includes(String(x.platform).toLowerCase())?`<del>${money(Number(x.price)*2*Number(x.qty||1),x.currency)}</del> <strong>${money(Number(x.price)*Number(x.qty||1),x.currency)}</strong><small class="discount-note">Descuento del 50% aplicado por ProEshop</small>`:money(Number(x.price)*Number(x.qty||1),x.currency)}</div><div class="item-actions"><button class="qty-btn" data-qty="${Number(x.id)}" data-next="${Math.max(1,Number(x.qty||1)-1)}" aria-label="Disminuir cantidad">−</button><span class="qty-value">${Number(x.qty||1)}</span><button class="qty-btn" data-qty="${Number(x.id)}" data-next="${Math.min(25,Number(x.qty||1)+1)}" aria-label="Aumentar cantidad">＋</button><a class="external" href="${escapeHtml(x.url)}" target="_blank" rel="noopener noreferrer">Ver tienda ↗</a><button class="text-btn" data-remove="${Number(x.id)}">Quitar</button></div></div>`;wrap.appendChild(el)});const t=estimateCart();$('cartSubtotal').textContent=money(t.subtotal);$('cartTax').textContent=money(t.tax);$('cartShipping').textContent=money(t.shipping);$('cartTotal').textContent=money(t.total);$('cartSubtitle').textContent=`${state.cart.length} artículo(s) · ${money(t.total)} estimado`;wrap.querySelectorAll('[data-remove]').forEach(b=>b.onclick=async()=>{try{await api('/api/cart/'+b.dataset.remove,{method:'DELETE'});await refresh();toast('Artículo retirado del carrito.')}catch(e){toast(e.message)}});wrap.querySelectorAll('[data-qty]').forEach(b=>b.onclick=async()=>{try{await api('/api/cart/'+b.dataset.qty,{method:'PUT',body:JSON.stringify({qty:Number(b.dataset.next)})});await refresh();}catch(e){toast(e.message)}});}
function formatDate(value){try{return new Date(value).toLocaleString('es-CO',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}catch{return String(value||'Fecha no disponible')}}
function trackingStage(status, isUsdt=false){
 const stages=isUsdt?[['pending_payment','Pendiente de pago'],['payment_review','Pago en revisión'],['confirmed','Confirmado'],['in_process','En proceso'],['shipped','Enviado'],['delivered','Entregado']]:[['payment_review','Pago en revisión'],['confirmed','Confirmado'],['in_process','En proceso'],['shipped','Enviado'],['delivered','Entregado']];
 const aliases={received:'payment_review',reviewing:'payment_review',preparing:'in_process'};
 const normalized=aliases[status]||status;
 const terminal=['cancelled','unavailable','returned'];
 let idx=stages.findIndex(s=>s[0]===normalized);
 if(normalized==='action_required')idx=0;
 const isTerminal=terminal.includes(status);
 return `<div class="premium-timeline ${isUsdt?'timeline-usdt':'timeline-standard'} ${isTerminal?'timeline-terminal':''}">${stages.map((s,i)=>{const complete=!isTerminal&&idx>i;const active=!isTerminal&&idx===i;const future=!isTerminal&&idx<i;const glyph=complete?'✓':String(i+1);return `<div class="timeline-step ${complete?'is-complete':''} ${active?'is-active':''} ${future?'is-future':''}"><div class="timeline-node">${glyph}</div><div class="timeline-label">${s[1]}</div></div>`}).join('')}</div>`;
}
function statusLabelForTracking(status){const labels={pending_payment:'Pendiente de pago',received:'Confirmado',payment_review:'Pago en revisión',reviewing:'Pago en revisión',action_required:'Requiere tu atención',confirmed:'Confirmado',in_process:'En proceso',preparing:'En proceso',shipped:'Enviado',delivered:'Entregado',unavailable:'No disponible',cancelled:'Cancelado',returned:'Devuelto',confirmed_simulated:'Confirmado (registro anterior)'};return labels[status]||String(status||'Estado actualizado').replaceAll('_',' ')}
function renderHistory(){
 const wrap=$('historyItems');wrap.innerHTML='';
 const orders=state.orders||[];const storeOrders=state.store_orders||[];const events=state.store_order_events||[];const history=state.history||[];
 $('historyEmpty').classList.toggle('hidden',!orders.length);
 orders.forEach(order=>{
  const children=storeOrders.filter(s=>s.order_ref===order.order_ref);
  const lines=history.filter(x=>x.order_ref===order.order_ref);
  const el=document.createElement('article');el.className='order-card premium-parent-order';
  const isUsdt=order.payment_method==='usdt_trc20';
  const paymentPending=isUsdt&&order.status==='pending_payment'&&order.crypto_status==='pending';
  const countdownDeadline=order.crypto_deadline_at?Date.parse(order.crypto_deadline_at):(order.crypto_created_at?Date.parse(order.crypto_created_at)+300000:0);
  const category=['cancelled','unavailable','returned'].includes(order.status)||order.crypto_status==='expired'?'cancelled':(['confirmed','in_process','preparing','shipped','delivered','payment_review','reviewing','received'].includes(order.status)||order.crypto_status==='detected'?'confirmed':'pending');
  el.dataset.orderCategory=category;el.dataset.orderStore=[...new Set(children.map(x=>String(x.platform||'').toLowerCase())),...lines.map(x=>String(x.platform||'').toLowerCase())].join(',');
  el.innerHTML=`<div class="premium-order-header"><div><div class="tracking-eyebrow">PROESHOP · RESUMEN DE PEDIDO</div><h3>${escapeHtml(order.order_ref)}</h3><p>${escapeHtml(formatDate(order.created_at))} · ${children.length?`${children.length} ${children.length===1?'tienda':'tiendas'}`:'pedido anterior'}</p></div><div class="premium-order-total"><small>TOTAL REGISTRADO</small><strong>${money(order.total,order.currency)}</strong><span>${isUsdt?'Pago USDT · TRON':'USD · registro interno'}</span></div></div>
  <div class="premium-order-actions"><span class="status-pill">${escapeHtml(statusLabelForTracking(order.status))}</span><button class="secondary small-button receipt-btn" data-receipt="${escapeHtml(order.order_ref)}">Ver recibo ↗</button></div>
  ${paymentPending?`<div class="crypto-pending-resume"><div><b>Pago USDT pendiente</b><p>Importe exacto: <strong>${escapeHtml(order.crypto_amount||'—')} USDT</strong></p><p>Tiempo restante: <strong class="order-countdown" data-deadline="${countdownDeadline}">05:00</strong></p></div><button class="primary resume-usdt-btn" data-resume-payment="${escapeHtml(order.order_ref)}">Retomar pago</button></div>`:''}
  ${isUsdt&&order.crypto_status==='expired'?'<div class="tracking-alert">La cotización USDT expiró y el pedido fue cancelado porque no se detectó el pago en cinco minutos. Crea un nuevo pedido para intentarlo otra vez.</div>':''}
  ${children.length?`<div class="store-tracking-list">${children.map(store=>{
    const storeLines=history.filter(x=>x.store_order_ref===store.store_order_ref || (!x.store_order_ref&&x.order_ref===order.order_ref&&x.platform===store.platform));
    const storeEvents=events.filter(ev=>ev.store_order_ref===store.store_order_ref);
    const status=String(store.status||'received');const current=storeEvents[storeEvents.length-1];
    const key=String(store.platform||'store').toLowerCase().replace(/[^a-z0-9_-]/g,'');
    const stateClass=['cancelled','unavailable','returned'].includes(status)?'status-negative':status==='delivered'?'status-success':status==='action_required'?'status-warning':'';
    const eventMarkup=(storeEvents.length?storeEvents:[{status:'received',label:'Pedido recibido',detail:'Registro de pedido conservado. El historial previo puede no contener eventos por tienda.',created_at:store.created_at}]).slice().reverse().map(ev=>`<div class="store-event"><span class="store-event-dot"></span><div><b>${escapeHtml(ev.label||statusLabelForTracking(ev.status))}</b><p>${escapeHtml(ev.detail||'Actualización registrada.')}</p></div><time>${escapeHtml(formatDate(ev.created_at))}</time></div>`).join('');
    const itemMarkup=storeLines.map(x=>`<div class="order-line"><span>${escapeHtml(x.title)} × ${Number(x.qty||1)}</span><strong>${money(x.total,x.currency)}</strong></div>`).join('')||'<p class="hint">El detalle de artículos puede no estar disponible en registros antiguos.</p>';
    return `<section class="store-track-card store-${key}"><div class="store-track-top"><div class="store-avatar">${escapeHtml((store.store_label||store.platform||'S').slice(0,1).toUpperCase())}</div><div class="store-track-name"><small>SEGUIMIENTO INDEPENDIENTE</small><h4>${escapeHtml(store.store_label||store.platform)}</h4><span>Ref. ${escapeHtml(store.store_order_ref)}</span></div><div class="store-track-total"><small>TOTAL DE ESTA TIENDA</small><strong>${money(store.total,store.currency)}</strong></div></div>
    <div class="store-current-status ${stateClass}"><span class="status-indicator"></span><div><small>ESTADO ACTUAL</small><strong>${escapeHtml(statusLabelForTracking(status))}</strong><span>Actualizado ${escapeHtml(formatDate(store.updated_at||store.created_at))}</span></div></div>
    ${status==='action_required'?'<div class="tracking-alert">Este pedido requiere una acción. Revisa el detalle o contacta al equipo de ProEshop.</div>':''}
    ${trackingStage(status, order.payment_method==='usdt_trc20')}
    <div class="tracking-truth-note">${status==='shipped'||status==='delivered'?'Estado registrado en ProEshop; no confirma por sí solo un envío real del comercio.':'Seguimiento del estado registrado en ProEshop. No hay envío real ni guía de transportista integrada.'}</div>
    <details class="store-track-details"><summary>Artículos e historial de cambios <span>${storeLines.length} artículos · ${storeEvents.length} eventos</span></summary><div class="store-track-detail-body"><div class="store-lines">${itemMarkup}</div><div class="store-event-list">${eventMarkup}</div><div class="tracking-ref">Guía de transporte: <b>No disponible</b></div></div></details></section>`;
  }).join('')}</div>`:`<div class="legacy-track"><div class="tracking-heading"><b>Seguimiento del pedido</b><span>HISTÓRICO</span></div><p>Este pedido pertenece a una versión anterior al seguimiento independiente por tienda. Conservamos su referencia, total y recibo.</p><div class="order-breakdown"><span>Subtotal ${money(order.subtotal,order.currency)}</span><span>Impuestos ${money(order.tax,order.currency)}</span><span>Envío ${money(order.shipping,order.currency)}</span></div><details class="order-details"><summary>Ver artículos y datos del pedido (${lines.length})</summary>${lines.map(x=>`<div class="order-line"><span>${escapeHtml(x.title)} · ${escapeHtml(storeLabel(x.platform))} × ${Number(x.qty||1)}</span><strong>${money(x.total,x.currency)}</strong></div>`).join('')||'<p>Detalle no disponible para pedidos anteriores a esta versión.</p>'}</details></div>`}`;
  wrap.appendChild(el);
 });
 wrap.querySelectorAll('[data-receipt]').forEach(b=>b.onclick=()=>openReceipt(b.dataset.receipt));
 wrap.querySelectorAll('[data-resume-payment]').forEach(b=>b.onclick=async()=>{b.disabled=true;b.textContent='Recuperando pago…';try{const p=await api('/api/payment/'+encodeURIComponent(b.dataset.resumePayment));if(p.status==='expired'){await refresh();toast('La cotización expiró. Crea un nuevo pedido.');return;}showView('checkout');$('checkoutForm').classList.add('hidden');renderCryptoPayment(p);window.scrollTo({top:0,behavior:'smooth'});}catch(e){toast(e.message||'No se pudo recuperar el pago.');}finally{b.disabled=false;b.textContent='Retomar pago';}});
 applyOrderFilters();updateOrderCountdowns();if(orderCountdownInterval)clearInterval(orderCountdownInterval);orderCountdownInterval=setInterval(updateOrderCountdowns,1000);
}
function applyOrderFilters(){const category=$('orderCategoryFilter')?.value||'all';const store=$('orderStoreFilter')?.value||'all';document.querySelectorAll('#historyItems .premium-parent-order').forEach(card=>{const categoryOk=category==='all'||card.dataset.orderCategory===category;const stores=(card.dataset.orderStore||'').split(',').filter(Boolean);const storeOk=store==='all'||stores.includes(store);card.classList.toggle('hidden',!(categoryOk&&storeOk));});const visible=[...document.querySelectorAll('#historyItems .premium-parent-order')].filter(card=>!card.classList.contains('hidden')).length;const empty=$('historyFilteredEmpty');if(empty)empty.classList.toggle('hidden',visible>0||!(state.orders||[]).length);}
function updateOrderCountdowns(){document.querySelectorAll('.order-countdown[data-deadline]').forEach(el=>{const seconds=Math.max(0,Math.ceil((Number(el.dataset.deadline)-Date.now())/1000));el.textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;if(seconds===0){el.textContent='00:00';if(!el.dataset.expiryRefresh){el.dataset.expiryRefresh='1';setTimeout(()=>refresh().catch(()=>{}),500);}}});}

function officialStoreUrl(platform,query){const q=encodeURIComponent(String(query||'producto').trim()||'producto');return {amazon:`https://www.amazon.com/s?k=${q}`,walmart:`https://www.walmart.com/search?q=${q}`,target:`https://www.target.com/s?searchTerm=${q}`,hublot:'https://www.hublot.com/en-us/find-your-hublot',jewelers:'https://www.jewelerstoystore.com/Electronic-s/1074.htm',rolex:'https://www.rolex.com/watches'}[String(platform||'').toLowerCase()]||'https://www.walmart.com/';}
function normalizeStoreUrl(rawUrl,platform,title){const hosts={amazon:['amazon.com','www.amazon.com'],walmart:['walmart.com','www.walmart.com'],target:['target.com','www.target.com'],hublot:['hublot.com','www.hublot.com'],jewelers:['jewelerstoystore.com','www.jewelerstoystore.com'],rolex:['rolex.com','www.rolex.com']};try{const u=new URL(String(rawUrl||''));if(u.protocol==='https:'&&(hosts[String(platform||'').toLowerCase()]||[]).includes(u.hostname.toLowerCase()))return u.href;}catch(_){}return officialStoreUrl(platform,title);}
function productCards(items,r){return items.map((x,i)=>{const platform=String(r.platform||'').toLowerCase();const isDiscounted=['hublot','jewelers','rolex'].includes(platform);const shownPrice=Number(x.price);const listPrice=Number(x.list_price||(platform==='hublot'?Number(x.price)*2:platform==='jewelers'?Number(x.price)*2:Number(x.price)));return `<article class="product-result"><div class="product-media"><button class="favorite-btn ${favorites.has(x.title+'|'+x.url)?'active':''}" data-fav="${i}" aria-label="Guardar favorito">${favorites.has(x.title+'|'+x.url)?'♥':'♡'}</button>${x.image?`<img class="product-thumb" src="${escapeHtml(x.image)}" data-fallback="${escapeHtml(x.fallback_image||'')}" alt="Imagen del producto" loading="lazy" referrerpolicy="no-referrer"><div class="product-placeholder hidden">▧</div>`:`<img class="product-thumb" src="${escapeHtml(x.fallback_image||'/static/catalog_images/rolex_01.jpg')}" alt="Imagen de catálogo" loading="lazy"><div class="product-placeholder hidden">▧</div>`}</div><div class="product-result-info"><div class="product-store">${escapeHtml(storeLabel(r.platform))} · ${escapeHtml(x.source||'Catálogo ProEshop')}</div><strong>${escapeHtml(x.title)}</strong><div class="product-price">${isDiscounted?`<del>${money(listPrice,'USD')}</del> <strong>${money(shownPrice,'USD')}</strong>`:money(shownPrice,'USD')}</div><small>${isDiscounted?'Descuento del 50% aplicado por ProEshop; no es una oferta oficial del proveedor.':'Precio consultado · confirma el importe final en la tienda.'}</small><div class="product-actions"><button class="external details-btn" data-details="${i}" type="button">Detalles ↗</button><button class="secondary compare-btn ${compareItems.has(x.title+'|'+x.url)?'active':''}" data-compare="${i}" type="button">⇄ Comparar</button><button class="primary add-result" data-add="${i}" type="button">${isDiscounted?'＋ Agregar · 50% OFF':'＋ Agregar'}</button></div></div></article>`}).join('');}
function renderResults(r){const result=$('searchResult');if(!result||!r)return;let items=[...lastSearch];const min=Number($('minPrice')?.value||0),maxVal=$('maxPrice')?.value; if(min>0)items=items.filter(x=>Number(x.price)>=min);if(maxVal!==''&&maxVal!=null)items=items.filter(x=>Number(x.price)<=Number(maxVal));const sort=$('sortResults')?.value||'relevance';if(sort==='low')items.sort((a,b)=>a.price-b.price);if(sort==='high')items.sort((a,b)=>b.price-a.price);currentResults=items;const grid=result.querySelector('.product-results');if(!grid)return;grid.innerHTML=productCards(items,r)||`<div class="empty"><div>⌕</div><strong>No hay resultados con estos filtros</strong><p>Prueba con otro rango de precio o cambia la búsqueda.</p></div>`;grid.querySelectorAll('img.product-thumb').forEach(img=>{img.onerror=()=>{if(img.dataset.fallback&&!img.dataset.fallbackUsed){img.dataset.fallbackUsed='1';img.src=img.dataset.fallback;}else{img.style.display='none';img.nextElementSibling?.classList.remove('hidden')}}});grid.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>{const item=items[Number(b.dataset.add)];if(item)addItem(item,r.platform)});grid.querySelectorAll('[data-details]').forEach(b=>b.onclick=()=>openProduct(items[Number(b.dataset.details)],r));grid.querySelectorAll('[data-compare]').forEach(b=>b.onclick=()=>{const item=items[Number(b.dataset.compare)];if(!item)return;const key=item.title+'|'+item.url;if(compareItems.has(key)){compareItems.delete(key);toast('Artículo retirado del comparador.')}else if(compareItems.size>=3){toast('Compara hasta 3 artículos a la vez.');return}else{compareItems.set(key,{...item,platform:r.platform});toast('Artículo añadido al comparador.')}renderCompare();b.classList.toggle('active',compareItems.has(key));});grid.querySelectorAll('[data-fav]').forEach(b=>b.onclick=()=>{const item=items[Number(b.dataset.fav)];if(!item)return;const key=item.title+'|'+item.url;favorites.has(key)?favorites.delete(key):favorites.add(key);b.classList.toggle('active',favorites.has(key));b.textContent=favorites.has(key)?'♥':'♡';});const count=result.querySelector('#resultCount');if(count)count.textContent=`${items.length} resultado${items.length===1?'':'s'}`;}
function openProduct(item,r){if(!item)return;const d=$('productDialogContent');d.innerHTML=`<div class="product-dialog-media">${item.image?`<img src="${escapeHtml(item.image)}" data-fallback="${escapeHtml(item.fallback_image||'')}" alt="Producto" onerror="if(this.dataset.fallback&&!this.dataset.fallbackUsed){this.dataset.fallbackUsed='1';this.src=this.dataset.fallback}else{this.style.display='none'}">`:`<img src="${escapeHtml(item.fallback_image||'/static/catalog_images/rolex_01.jpg')}" alt="Imagen de catálogo">`}</div><div class="eyebrow dark-eyebrow">${escapeHtml(storeLabel(r.platform))} · DETALLE</div><h2>${escapeHtml(item.title)}</h2><div class="dialog-price">${['hublot','jewelers','rolex'].includes(String(r.platform).toLowerCase())?`<del>${money(item.list_price||Number(item.price)*2,'USD')}</del> ${money(item.price,'USD')}`:money(item.price,'USD')}</div><p class="dialog-note">Vendedor mostrado por el proveedor: ${escapeHtml(item.source||'No identificado')}. No se inventan valoraciones, descuentos ni disponibilidad. Confirma todos los detalles en la tienda oficial.</p><div class="dialog-actions"><a class="external" href="${escapeHtml(normalizeStoreUrl(item.url,r.platform,item.title))}" target="_blank" rel="noopener noreferrer">Ver en tienda ↗</a><button id="dialogAdd" class="primary">Agregar al carrito</button></div>`;$('productDialog').showModal();d.querySelector('img')?.addEventListener('error',e=>{e.currentTarget.style.display='none'});$('dialogAdd').onclick=async()=>{await addItem(item,r.platform);$('productDialog').close()};}
async function addItem(item,platform=selectedStore){try{const p=String(platform||selectedStore).toLowerCase();const url=normalizeStoreUrl(item.url,p,item.title);await api('/api/cart',{method:'POST',body:JSON.stringify({platform:p,title:String(item.title||'Producto').slice(0,180),price:String(['hublot','jewelers'].includes(p)?Number(item.price)*2:item.price),currency:'USD',url,image:String(item.fallback_image||item.image||'')})});await refresh();toast('Artículo agregado al carrito');}catch(e){toast(e.message||'No se pudo agregar el artículo');}}
async function performSearch(queryOverride, platformOverride){if(platformOverride){selectedStore=String(platformOverride).toLowerCase();if(['amazon','target','walmart'].includes(selectedStore)){selectedStore='rolex';toast('Amazon, Target y Walmart están deshabilitados temporalmente.');}document.querySelectorAll('.store').forEach(x=>x.classList.toggle('active',x.dataset.store===selectedStore));}const platform=selectedStore;const query=String(queryOverride??$('query').value).trim();if(!query)return toast(platform==='hublot'?'Escribe el nombre o la colección del reloj.':'Escribe qué artículo buscas.');if(searchBusy)return;searchBusy=true;$('query').value=query;$('clearSearch').classList.remove('hidden');$('homeEmpty').classList.add('hidden');const btn=$('searchBtn');btn.disabled=true;btn.textContent='Buscando…';document.querySelectorAll('[data-search-store]').forEach(b=>{b.disabled=true;if(b.dataset.searchStore===platform)b.dataset.originalLabel=b.innerHTML,b.innerHTML='Buscando…';});$('searchResult').classList.remove('hidden');$('searchResult').innerHTML='<div class="home-empty"><div class="empty-orbit">⌕</div><strong>Buscando productos…</strong><p>Consultando resultados para '+escapeHtml(storeLabel(platform))+'.</p></div>';try{let r;r=await api('/api/search',{method:'POST',body:JSON.stringify({platform,query})});if(['hublot','jewelers'].includes(platform)){r.live_results=(r.live_results||[]).map(x=>({...x,list_price:Number(x.list_price||x.price),price:Number(x.price)/2}));}lastSearch=r.live_results||[];lastSearchResponse=r;$('searchResult').innerHTML=`<div class="results-heading"><div><h3>${escapeHtml(r.label)} · Resultados</h3><p id="resultCount">${lastSearch.length} resultados para “${escapeHtml(query)}”</p></div><span class="live-dot">PRECIOS USD</span></div><p>${escapeHtml(r.notice||'Los precios pueden variar; confirma el total en la tienda.')}</p><div class="filter-row"><label>Precio mínimo<input id="minPrice" type="number" min="0" step="1" placeholder="USD 0"></label><label>Precio máximo<input id="maxPrice" type="number" min="0" step="1" placeholder="Sin límite"></label><label>Ordenar por<select id="sortResults"><option value="relevance">Relevancia</option><option value="low">Menor precio</option><option value="high">Mayor precio</option></select></label></div><div class="filter-extra"><label><input id="showImages" type="checkbox" checked> Mostrar imágenes</label><span class="view-toggle"><button type="button" class="active" data-layout="grid">▦</button><button type="button" data-layout="list">☰</button></span></div><a class="external" href="${escapeHtml(r.search_url)}" target="_blank" rel="noopener noreferrer">Abrir tienda oficial ↗</a><div id="comparePanel" class="compare-panel hidden"></div><div class="product-results"></div><p class="hint">Los productos se agregan desde las referencias del catálogo; la opción de agregar artículos manualmente está deshabilitada.</p>`;const redraw=()=>renderResults(r);['minPrice','maxPrice','sortResults'].forEach(id=>$(id).addEventListener(id==='sortResults'?'change':'input',redraw));$('showImages').onchange=e=>document.querySelectorAll('.product-thumb').forEach(img=>img.classList.toggle('hidden',!e.target.checked));document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-layout]').forEach(x=>x.classList.toggle('active',x===b));$('searchResult').querySelector('.product-results')?.classList.toggle('list-layout',b.dataset.layout==='list')});renderResults(r);renderCompare();$('searchResult').scrollIntoView({behavior:'smooth',block:'start'});}catch(e){$('searchResult').innerHTML=`<div class="empty"><div>⚠</div><strong>No se pudo completar la búsqueda</strong><p>${escapeHtml(e.message)}</p><button class="secondary" id="retrySearch">Intentar de nuevo</button></div>`;$('retrySearch').onclick=()=>performSearch(query,platform);}finally{searchBusy=false;btn.disabled=false;btn.textContent='Buscar';document.querySelectorAll('[data-search-store]').forEach(b=>{b.disabled=false;if(b.dataset.originalLabel){b.innerHTML=b.dataset.originalLabel;delete b.dataset.originalLabel;}});}}
function renderCompare(){const panel=$('comparePanel');if(!panel)return;const items=[...compareItems.values()];panel.classList.toggle('hidden',!items.length);if(!items.length){panel.innerHTML='';return;}panel.innerHTML=`<div class="compare-head"><div><b>Comparador de productos</b><small>${items.length} de 3 artículos</small></div><button class="text-btn" id="clearCompare">Limpiar</button></div><div class="compare-table-wrap"><table class="compare-table"><thead><tr><th>Característica</th>${items.map(x=>`<th>${escapeHtml(storeLabel(x.platform))}</th>`).join('')}</tr></thead><tbody><tr><td>Producto</td>${items.map(x=>`<td>${escapeHtml(x.title)}</td>`).join('')}</tr><tr><td>Precio consultado</td>${items.map(x=>`<td><b>${money(x.price,'USD')}</b></td>`).join('')}</tr><tr><td>Vendedor</td>${items.map(x=>`<td>${escapeHtml(x.source||'No verificado')}</td>`).join('')}</tr><tr><td>Acción</td>${items.map(x=>`<td><button class="primary compare-add" data-key="${escapeHtml(x.title+'|'+x.url)}">Agregar</button></td>`).join('')}</tr></tbody></table></div><p class="hint">Los precios se consultaron en el proveedor y pueden cambiar. Verifica precio, vendedor, impuestos y disponibilidad en la tienda.</p>`;$('clearCompare').onclick=()=>{compareItems.clear();renderCompare();renderResults(lastSearchResponse||{platform:selectedStore,label:storeLabel(selectedStore)});};panel.querySelectorAll('.compare-add').forEach(b=>b.onclick=()=>{const x=compareItems.get(b.dataset.key);if(x)addItem(x,x.platform)});}
const HUBLOT_PRODUCTS = [
 {
  "id": "bb-original-red",
  "name": "Big Bang Original Soft Touch All Red",
  "collection": "Big Bang",
  "price": 24900,
  "desc": "Rojo integral y diseño deportivo contemporáneo.",
  "img": "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-original-black",
  "name": "Big Bang Original Soft Touch All Black",
  "collection": "Big Bang",
  "price": 24900,
  "desc": "Acabado negro integral de carácter técnico.",
  "img": "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-original-titanium",
  "name": "Big Bang Original Titanium 43 mm",
  "collection": "Big Bang",
  "price": 20400,
  "desc": "Titanio ligero con estética emblemática.",
  "img": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-original-titanium-ceramic",
  "name": "Big Bang Original Titanium Ceramic 43 mm",
  "collection": "Big Bang",
  "price": 21600,
  "desc": "Titanio y cerámica en contraste.",
  "img": "https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-original-king-gold",
  "name": "Big Bang Original King Gold Ceramic 43 mm",
  "collection": "Big Bang",
  "price": 39600,
  "desc": "King Gold combinado con cerámica.",
  "img": "https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-original-black-magic",
  "name": "Big Bang Original Black Magic 43 mm",
  "collection": "Big Bang",
  "price": 22800,
  "desc": "Cerámica negra con presencia discreta.",
  "img": "https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-original-coal-blue",
  "name": "Big Bang Original Titanium Coal Blue 43 mm",
  "collection": "Big Bang",
  "price": 20400,
  "desc": "Esfera azul carbón y caja de titanio.",
  "img": "https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-reloaded-uefa",
  "name": "Big Bang Reloaded UEFA Champions League 44 mm",
  "collection": "Big Bang",
  "price": 25200,
  "desc": "Edición temática de fútbol.",
  "img": "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-sapphire-sky",
  "name": "Big Bang Sapphire Sky Blue 44 mm",
  "collection": "Big Bang",
  "price": 84300,
  "desc": "Caja de zafiro azul translúcido.",
  "img": "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-summer-42",
  "name": "Big Bang Summer Multi-Colored Ceramic 42 mm",
  "collection": "Big Bang",
  "price": 34300,
  "desc": "Cerámica multicolor de edición llamativa.",
  "img": "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-summer-44",
  "name": "Big Bang Summer Multi-Colored Ceramic 44 mm",
  "collection": "Big Bang",
  "price": 119000,
  "desc": "Versión de alta complejidad multicolor.",
  "img": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-peach-42",
  "name": "Big Bang Titanium Peach Ceramic 42 mm",
  "collection": "Big Bang",
  "price": 24000,
  "desc": "Cerámica tono melocotón y titanio.",
  "img": "https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-peach-33",
  "name": "Big Bang Peach Ceramic 33 mm",
  "collection": "Big Bang",
  "price": 15500,
  "desc": "Formato compacto en cerámica melocotón.",
  "img": "https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-petrol-33",
  "name": "Big Bang Petrol Blue Ceramic 33 mm",
  "collection": "Big Bang",
  "price": 15500,
  "desc": "Cerámica azul petróleo.",
  "img": "https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-mint-33",
  "name": "Big Bang Mint Green Ceramic 33 mm",
  "collection": "Big Bang",
  "price": 15500,
  "desc": "Cerámica verde menta.",
  "img": "https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-unico-grey",
  "name": "Big Bang Unico Essential Grey 42 mm",
  "collection": "Big Bang",
  "price": 24000,
  "desc": "Cronógrafo Unico en tonos grises.",
  "img": "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-magic-gold",
  "name": "Big Bang Reloaded Magic Gold 44 mm",
  "collection": "Big Bang",
  "price": 44500,
  "desc": "Aleación Magic Gold resistente a rayaduras.",
  "img": "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-king-gold",
  "name": "Big Bang Original King Gold 43 mm",
  "collection": "Big Bang",
  "price": 39600,
  "desc": "King Gold en silueta clásica Big Bang.",
  "img": "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "bb-unico-titanium",
  "name": "Big Bang Unico Titanium 42 mm",
  "collection": "Big Bang",
  "price": 26400,
  "desc": "Cronógrafo con caja de titanio.",
  "img": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "square-unico-titanium",
  "name": "Square Bang Unico Titanium 42 mm",
  "collection": "Big Bang",
  "price": 26400,
  "desc": "Caja cuadrada y movimiento Unico.",
  "img": "https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "square-unico-ceramic",
  "name": "Square Bang Unico Titanium Ceramic 42 mm",
  "collection": "Big Bang",
  "price": 27600,
  "desc": "Titanio y cerámica en formato cuadrado.",
  "img": "https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "square-king-gold",
  "name": "Square Bang Unico King Gold 42 mm",
  "collection": "Big Bang",
  "price": 49300,
  "desc": "King Gold con geometría cuadrada.",
  "img": "https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "square-black-magic",
  "name": "Square Bang Unico Black Magic 42 mm",
  "collection": "Big Bang",
  "price": 30000,
  "desc": "Caja cuadrada de cerámica negra.",
  "img": "https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-original-titanium",
  "name": "Classic Fusion Original Titanium 42 mm",
  "collection": "Classic Fusion",
  "price": 9400,
  "desc": "Elegancia minimalista en titanio.",
  "img": "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-original-black",
  "name": "Classic Fusion Original Black Magic 42 mm",
  "collection": "Classic Fusion",
  "price": 11400,
  "desc": "Diseño sobrio con acabado negro.",
  "img": "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-titanium",
  "name": "Classic Fusion Titanium 42 mm",
  "collection": "Classic Fusion",
  "price": 8700,
  "desc": "Perfil limpio y caja de titanio.",
  "img": "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-blue",
  "name": "Classic Fusion Titanium Blue 42 mm",
  "collection": "Classic Fusion",
  "price": 8700,
  "desc": "Esfera azul y estética refinada.",
  "img": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-king-gold",
  "name": "Classic Fusion King Gold 42 mm",
  "collection": "Classic Fusion",
  "price": 25200,
  "desc": "Oro cálido con líneas depuradas.",
  "img": "https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-black-magic",
  "name": "Classic Fusion Black Magic 42 mm",
  "collection": "Classic Fusion",
  "price": 10700,
  "desc": "Cerámica negra y diseño elegante.",
  "img": "https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-chrono-ti",
  "name": "Classic Fusion Chronograph Titanium 42 mm",
  "collection": "Classic Fusion",
  "price": 12300,
  "desc": "Cronógrafo clásico en titanio.",
  "img": "https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-chrono-gold",
  "name": "Classic Fusion Chronograph King Gold 42 mm",
  "collection": "Classic Fusion",
  "price": 32400,
  "desc": "Cronógrafo con caja King Gold.",
  "img": "https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-chrono-black",
  "name": "Classic Fusion Chronograph Black Magic 42 mm",
  "collection": "Classic Fusion",
  "price": 13500,
  "desc": "Cronógrafo con acabado cerámico negro.",
  "img": "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-aero-ti",
  "name": "Classic Fusion Aerofusion Titanium 45 mm",
  "collection": "Classic Fusion",
  "price": 17100,
  "desc": "Esfera esqueletizada y caja de titanio.",
  "img": "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "classic-aero-black",
  "name": "Classic Fusion Aerofusion Black Magic 45 mm",
  "collection": "Classic Fusion",
  "price": 18800,
  "desc": "Arquitectura esqueletizada en negro.",
  "img": "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-ti",
  "name": "Spirit of Big Bang Titanium 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 26400,
  "desc": "Caja tonneau y titanio ligero.",
  "img": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-ti-ceramic",
  "name": "Spirit of Big Bang Titanium Ceramic 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 27600,
  "desc": "Tonneau con combinación de materiales.",
  "img": "https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-king-gold",
  "name": "Spirit of Big Bang King Gold 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 49300,
  "desc": "Caja tonneau en King Gold.",
  "img": "https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-king-ceramic",
  "name": "Spirit of Big Bang King Gold Ceramic 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 45700,
  "desc": "King Gold y cerámica negra.",
  "img": "https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-black-magic",
  "name": "Spirit of Big Bang Black Magic 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 30000,
  "desc": "Silueta tonneau con acabado negro.",
  "img": "https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-taupe",
  "name": "Spirit of Big Bang Essential Taupe 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 24800,
  "desc": "Tono taupe, edición exclusiva online según fabricante.",
  "img": "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-impact-black",
  "name": "Spirit of Big Bang Impact All Black 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 33700,
  "desc": "Diseño oscuro de alta presencia.",
  "img": "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-impact-sapphire",
  "name": "Spirit of Big Bang Impact Sapphire 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 114500,
  "desc": "Caja de zafiro y diseño escultural.",
  "img": "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-sapphire-blue",
  "name": "Spirit of Big Bang Sapphire Blue 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 102400,
  "desc": "Caja de zafiro azul.",
  "img": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-coal-blue",
  "name": "Spirit of Big Bang Titanium Coal Blue 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 24000,
  "desc": "Titanio y esfera azul carbón.",
  "img": "https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-white",
  "name": "Spirit of Big Bang Titanium White 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 26400,
  "desc": "Titanio con estética blanca.",
  "img": "https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-meca-ti",
  "name": "Spirit of Big Bang Meca-10 Titanium 45 mm",
  "collection": "Spirit of Big Bang",
  "price": 27600,
  "desc": "Reserva de marcha larga y arquitectura mecánica.",
  "img": "https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-meca-gold",
  "name": "Spirit of Big Bang Meca-10 King Gold 45 mm",
  "collection": "Spirit of Big Bang",
  "price": 52900,
  "desc": "Meca-10 con caja King Gold.",
  "img": "https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-tourbillon-black",
  "name": "Spirit of Big Bang Tourbillon 5-Day Power Reserve Black Magic 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 109000,
  "desc": "Tourbillon y reserva de marcha de cinco días.",
  "img": "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-tourbillon-red",
  "name": "Spirit of Big Bang Tourbillon 5-Day Power Reserve Red Magic 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 109000,
  "desc": "Cerámica roja y tourbillon.",
  "img": "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-tourbillon-blue",
  "name": "Spirit of Big Bang Tourbillon 5-Day Power Reserve Sky Blue Ceramic 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 109000,
  "desc": "Cerámica azul cielo y tourbillon.",
  "img": "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-tourbillon-yellow",
  "name": "Spirit of Big Bang Tourbillon 5-Day Power Reserve Yellow Magic 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 109000,
  "desc": "Cerámica amarilla y tourbillon.",
  "img": "https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=900&q=85"
 },
 {
  "id": "spirit-tourbillon-sapphire",
  "name": "Spirit of Big Bang Tourbillon 5-Day Power Reserve Black Sapphire 42 mm",
  "collection": "Spirit of Big Bang",
  "price": 169000,
  "desc": "Caja de zafiro negro y tourbillon.",
  "img": "https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=900&q=85"
 }
];
async function openReceipt(ref){const win=window.open('about:blank','_blank');if(win)win.opener=null;try{const r=await fetch('/api/orders/'+encodeURIComponent(ref)+'/receipt',{headers:token?{'Authorization':`Bearer ${token}`}:{}});const html=await r.text();if(!r.ok)throw new Error('No se pudo cargar el recibo.');const blob=new Blob([html],{type:'text/html;charset=utf-8'});const url=URL.createObjectURL(blob);if(win)win.location.href=url;else toast('Permite ventanas emergentes para ver el recibo.');setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){if(win)win.close();toast(e.message||'No se pudo abrir el recibo.')}}
async function loadNotificationPreferences(){try{const p=await api('/api/notifications');$('notifyOrders').checked=!!p.order_updates;$('notifySecurity').checked=!!p.security_alerts;$('notificationStatusText').textContent=p.telegram_configured?'Telegram configurado; los avisos dependen de la disponibilidad del bot.':'Bot no configurado en servidor; las preferencias se guardan, pero no se enviarán mensajes.';}catch(e){toast(e.message)}}
async function saveNotificationPreferences(){try{const r=await api('/api/notifications',{method:'POST',body:JSON.stringify({order_updates:$('notifyOrders').checked,security_alerts:$('notifySecurity').checked})});$('notificationStatusText').textContent=r.telegram_configured?'Preferencias guardadas. Telegram está configurado.':'Preferencias guardadas. Configura el bot para recibir mensajes.';toast('Preferencias guardadas.');}catch(e){toast(e.message)}}
async function loadAdminOrders(){const wrap=$('adminOrders');wrap.innerHTML='<p class="hint">Cargando pedidos…</p>';try{const r=await fetch('/api/admin/orders',{headers:{'X-Admin-Key':adminKey}});const data=await r.json();if(!r.ok)throw new Error(data.detail||'No se pudieron cargar los pedidos.');const statuses=data.statuses||{};const transitions=data.transitions||{};wrap.innerHTML=(data.orders||[]).map(o=>{const label=storeLabel(o.platform||'');const allowed=[o.status,...(transitions[o.status]||[])].filter((v,i,a)=>a.indexOf(v)===i);return `<article class="admin-order-card"><div class="admin-order-head"><div><b>${escapeHtml(o.store_label||label||'ProEshop')}</b><small>${escapeHtml(o.order_ref)}</small><small>Pedido principal: ${escapeHtml(o.parent_order_ref||o.order_ref)}</small></div><strong>${money(o.total,o.currency)}</strong></div><label class="admin-status-label" for="email-${escapeHtml(o.order_ref)}">Correo del cliente</label><input id="email-${escapeHtml(o.order_ref)}" class="admin-status-detail" type="email" maxlength="254" value="${escapeHtml(o.customer_email||'')}" placeholder="cliente@correo.com"><button class="secondary full" data-save-email="${escapeHtml(o.order_ref)}">Guardar correo</button><label class="admin-status-label" for="status-${escapeHtml(o.order_ref)}">Estado</label><select id="status-${escapeHtml(o.order_ref)}" class="admin-status-select">${allowed.map(k=>`<option value="${escapeHtml(k)}" ${k===o.status?'selected':''}>${escapeHtml(statuses[k]||k)}</option>`).join('')}</select><label class="admin-status-label" for="detail-${escapeHtml(o.order_ref)}">Nota (opcional)</label><input id="detail-${escapeHtml(o.order_ref)}" class="admin-status-detail" maxlength="500" placeholder="Detalle para el historial y el correo"><div class="admin-order-actions"><button class="primary full" data-save-status="${escapeHtml(o.order_ref)}">Guardar estado</button><button class="secondary full" data-retry-email="${escapeHtml(o.order_ref)}">Reintentar correo</button></div><p class="admin-current-status">Actual: ${escapeHtml(statuses[o.status]||o.status)}</p></article>`}).join('')||'<p class="hint">No hay pedidos registrados.</p>';wrap.querySelectorAll('[data-save-status]').forEach(btn=>btn.onclick=async()=>{const ref=btn.dataset.saveStatus;btn.disabled=true;const original=btn.textContent;btn.textContent='Guardando…';try{const result=await fetch(`/api/admin/orders/${encodeURIComponent(ref)}/status`,{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':adminKey},body:JSON.stringify({status:$(`status-${ref}`).value,detail:$(`detail-${ref}`).value.trim()})});const payload=await result.json();if(!result.ok)throw new Error(payload.detail||'No se pudo guardar el estado.');toast(payload.email_sent?'Estado guardado · correo aceptado por el proveedor':`Estado guardado · correo: ${payload.email_status||'pendiente'}`);await loadAdminOrders();}catch(e){toast(e.message||'Error al guardar el estado.');}finally{btn.disabled=false;btn.textContent=original;}});wrap.querySelectorAll('[data-save-email]').forEach(btn=>btn.onclick=async()=>{const ref=btn.dataset.saveEmail;const customer_email=$(`email-${ref}`).value.trim();if(!customer_email){toast('Introduce el correo del cliente.');return;}btn.disabled=true;try{const r=await fetch(`/api/admin/orders/${encodeURIComponent(ref)}/email`,{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':adminKey},body:JSON.stringify({customer_email})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'No se pudo guardar el correo.');toast('Correo guardado. Ahora puedes reintentar el envío.');await loadAdminOrders();}catch(e){toast(e.message||'Error al guardar el correo.');}finally{btn.disabled=false;}});wrap.querySelectorAll('[data-retry-email]').forEach(btn=>btn.onclick=async()=>{const ref=btn.dataset.retryEmail;btn.disabled=true;try{const r=await fetch(`/api/admin/orders/${encodeURIComponent(ref)}/retry-email`,{method:'POST',headers:{'X-Admin-Key':adminKey}});const data=await r.json();if(!r.ok)throw new Error(data.detail||'No se pudo reintentar.');toast(data.email_sent?'Correo aceptado por el proveedor. Revisa también spam.':`Correo no enviado: ${data.email_status||'revisa logs de Railway'}`);}catch(e){toast(e.message);}finally{btn.disabled=false;}});}catch(e){wrap.innerHTML=`<p class="error">${escapeHtml(e.message)}</p>`;}}
async function loadAdminMetrics(){if(!adminKey){adminKey=prompt('Introduce la ADMIN_API_KEY configurada en Railway:')||'';}if(!adminKey)return;const status=$('adminStatus');status.textContent='Consultando métricas y pedidos…';try{const r=await fetch('/api/admin/metrics',{headers:{'X-Admin-Key':adminKey}});const data=await r.json();if(!r.ok)throw new Error(data.detail||'No se pudo cargar el panel.');$('adminPanel').classList.remove('hidden');status.textContent='Métricas internas. Cambiar el estado registra un evento e intenta notificar por correo; la aceptación por el proveedor no garantiza entrega en bandeja.';$('adminMetrics').innerHTML=[['Usuarios',data.users],['Pedidos registrados',data.orders],['Volumen registrado',money(data.demo_volume)],['Artículos en carritos',data.cart_items],['Búsquedas 24 h',data.searches_24h],['Eventos de auditoría',data.audit_events]].map(x=>`<div class="metric-card"><small>${escapeHtml(x[0])}</small><strong>${escapeHtml(x[1])}</strong></div>`).join('');$('adminAudit').innerHTML=(data.recent_audit||[]).map(x=>`<div class="audit-row"><b>${escapeHtml(x.action)}</b><span>${escapeHtml(x.detail)}</span><small>${escapeHtml(x.created_at)}</small></div>`).join('')||'<p class="hint">Sin eventos.</p>';await loadAdminOrders();}catch(e){status.textContent=e.message;adminKey='';$('adminPanel').classList.remove('hidden');}}
function renderCheckoutBreakdown(){const wrap=$('checkoutStoreBreakdown');if(!wrap)return;const groups=new Map();for(const item of state.cart){const key=String(item.platform||'other').toLowerCase();const group=groups.get(key)||{subtotal:0,qty:0,savings:0,items:[]};const price=Number(item.price)||0;const qty=Number(item.qty)||1;group.subtotal+=price*qty;group.qty+=qty;if(['hublot','jewelers'].includes(key))group.savings+=price*qty;group.items.push(item);groups.set(key,group);}const rows=[...groups.entries()].map(([key,g])=>`<div class="checkout-store-group"><div class="checkout-store-row"><span><b>${escapeHtml(storeLabel(key))}</b><small>${g.qty} artículo(s)${g.savings?` · ahorro ProEshop ${money(g.savings,state.currency)}`:''}</small></span><strong>${money(g.subtotal,state.currency)}</strong></div>${g.items.map(item=>`<div class="checkout-product-row">${item.image?`<img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.classList.add('image-failed');this.removeAttribute('src')">`:`<div class="checkout-product-placeholder">${storeIcon(key)}</div>`}<div class="checkout-product-info"><b>${escapeHtml(item.title)}</b><small>${Number(item.qty||1)} unidad(es)</small></div><strong>${money(Number(item.price)*Number(item.qty||1),state.currency)}</strong></div>`).join('')}</div>`).join('');const t=estimateCart();wrap.innerHTML=`<div class="checkout-breakdown-title">Detalle por tienda</div>${rows}<div class="checkout-store-row checkout-estimate-row"><span>Impuestos estimados</span><strong>${money(t.tax,state.currency)}</strong></div><div class="checkout-store-row checkout-estimate-row"><span>Envío estimado</span><strong>${money(t.shipping,state.currency)}</strong></div><p class="checkout-estimate-note">Las imágenes se cargan desde la tienda oficial cuando está disponible. Los importes son estimaciones internas; las promociones de ProEshop no son descuentos oficiales de los comercios.</p>`;}
function openCheckout(){const panel=$('cryptoPaymentPanel');const hasQuote=!!activeCryptoOrder&&panel&&!panel.classList.contains('hidden');if(hasQuote&&cryptoQuoteCartSignature===cartSignature()){$('checkoutForm').classList.add('hidden');showView('checkout');return;}if(hasQuote&&cryptoQuoteCartSignature!==cartSignature()){panel.classList.add('hidden');panel.innerHTML='';activeCryptoOrder='';cryptoQuoteCartSignature='';if(cryptoPaymentInterval){clearInterval(cryptoPaymentInterval);cryptoPaymentInterval=null;}toast('El carrito cambió. Revisa el nuevo total y genera una cotización USDT nueva.');}if(!state.cart.length){toast('Agrega primero un artículo al carrito.');return;}const t=estimateCart();$('checkoutTotal').textContent=money(t.total,state.currency);$('checkoutItemCount').textContent=`${state.cart.reduce((n,x)=>n+Number(x.qty||1),0)} artículo(s)`;$('checkoutError').textContent='';$('demoConsent').checked=false;$('checkoutForm').classList.remove('hidden');panel.classList.add('hidden');panel.innerHTML='';renderCheckoutBreakdown();updateCheckoutPaymentCopy();showView('checkout');}
function updateCheckoutPaymentCopy(){const method=document.querySelector('input[name=payment_method]:checked')?.value||'demo_balance';$('checkoutConsentText').textContent=method==='usdt_trc20'?'Confirmo que pagaré únicamente en USDT por la red TRON (TRC-20) y que el pedido no se confirma hasta la revisión del pago.':method==='tenderly_usdt_erc20'?'Confirmo que crearé un pedido de prueba en MainNet Lab. La transferencia solo se solicitará en el siguiente paso, al pulsar Procesar pago en MainNet Lab.':'Confirmo que deseo registrar este pedido con el saldo ficticio de ProEshop.';$('placeOrderBtn').innerHTML=method==='usdt_trc20'?'Crear pedido y mostrar dirección USDT <span>₮</span>':method==='tenderly_usdt_erc20'?'Crear pedido MainNet Lab y continuar al pago <span>Ξ</span>':'Registrar pedido de prueba <span>✓</span>'; }
function renderCryptoPayment(payment){const panel=$('cryptoPaymentPanel');panel.classList.remove('hidden');const expired=payment.status==='expired';const detected=payment.status==='detected';activeCryptoOrder=payment.order_ref;activeCryptoDeadline=payment.deadline_at?Date.parse(payment.deadline_at):Date.now()+Number(payment.remaining_seconds||300)*1000;panel.innerHTML=`<div class="form-section-title"><span>₮</span><div><b>Pago con USDT</b><small>Pedido ${escapeHtml(payment.order_ref)}</small></div></div><div class="info-banner"><span>!</span><div><strong>${expired?'Cotización expirada':detected?'Transferencia detectada':'Envía el importe exacto'}</strong><p>Red: TRON (TRC-20). No envíes USDT por Ethereum, BNB Chain ni otra red.</p></div></div><div class="crypto-countdown-card"><small>TIEMPO PARA COMPLETAR EL PAGO</small><strong id="cryptoCountdown">${expired?'00:00':detected?'—:—':'05:00'}</strong><span>${expired?'El pedido fue cancelado.':detected?'Pago detectado; pendiente de revisión.':'Si no se detecta en 5 minutos, el pedido se cancelará automáticamente.'}</span></div><label>Importe exacto <strong class="crypto-amount">${escapeHtml(payment.amount)} USDT</strong></label><label>Dirección de recepción<div class="crypto-address-row"><input id="cryptoReceivingAddress" readonly value="${escapeHtml(payment.address)}"><button id="copyCryptoAddress" class="secondary" type="button" ${expired||detected?'disabled':''}>Copiar</button></div></label><button id="copyCryptoAmount" class="secondary full" type="button" ${expired||detected?'disabled':''}>Copiar importe</button><div id="cryptoPaymentStatus" class="notification-status"><span class="pulse"></span><span>${expired?'El plazo de pago terminó; el pedido está cancelado.':detected?'Transferencia detectada y confirmada. El pedido está en revisión de pago.':'Esperando la transferencia confirmada en la blockchain…'}</span></div><p class="hint">El pedido solo pasa a revisión cuando se detecta una transferencia confirmada. Eso no significa que ya esté aprobado.</p><p id="cryptoTxLink" class="hint"></p><button id="cryptoBackToOrders" class="primary full" type="button">Ver mis pedidos</button><button id="cryptoEditCart" class="secondary full crypto-edit-cart" type="button">Volver al carrito</button>`;const copyAddress=$('copyCryptoAddress');if(copyAddress)copyAddress.onclick=async()=>{try{await navigator.clipboard.writeText(payment.address);toast('Dirección copiada');}catch(e){$('cryptoReceivingAddress').select();toast('Selecciona y copia la dirección manualmente');}};const copyAmount=$('copyCryptoAmount');if(copyAmount)copyAmount.onclick=async()=>{try{await navigator.clipboard.writeText(payment.amount);toast('Importe copiado');}catch(e){toast('Importe: '+payment.amount+' USDT');}};$('cryptoBackToOrders').onclick=async()=>{showView('history');try{await refresh()}catch(e){}};$('cryptoEditCart').onclick=async()=>{showView('cart');try{await refresh()}catch(e){toast(e.message);}};if(payment.explorer_url)$('cryptoTxLink').innerHTML=`Transacción: <a class="external" target="_blank" rel="noopener noreferrer" href="${escapeHtml(payment.explorer_url)}">Ver en Tronscan ↗</a>`;if(cryptoPaymentInterval)clearInterval(cryptoPaymentInterval);if(cryptoCountdownInterval)clearInterval(cryptoCountdownInterval);if(!expired&&!detected){updateCryptoCountdown();cryptoCountdownInterval=setInterval(updateCryptoCountdown,1000);checkCryptoPayment();cryptoPaymentInterval=setInterval(checkCryptoPayment,5000);}else{if(cryptoCountdownInterval){clearInterval(cryptoCountdownInterval);cryptoCountdownInterval=null;}if(cryptoPaymentInterval){clearInterval(cryptoPaymentInterval);cryptoPaymentInterval=null;}}}
function updateCryptoCountdown(){const el=$('cryptoCountdown');if(!el)return;const seconds=Math.max(0,Math.ceil((activeCryptoDeadline-Date.now())/1000));el.textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;if(seconds<=0){el.textContent='00:00';if(cryptoCountdownInterval){clearInterval(cryptoCountdownInterval);cryptoCountdownInterval=null;}checkCryptoPayment();}}
async function checkCryptoPayment(){if(!activeCryptoOrder)return;try{const p=await api('/api/payment/'+encodeURIComponent(activeCryptoOrder));const status=$('cryptoPaymentStatus');if(!status)return;if(p.status==='detected'){status.innerHTML='<span>✓</span><span>Transferencia detectada y confirmada. Tu pedido está <b>En revisión de pago</b>.</span>';if(p.explorer_url)$('cryptoTxLink').innerHTML=`Transacción: <a class="external" target="_blank" rel="noopener noreferrer" href="${escapeHtml(p.explorer_url)}">Ver en Tronscan ↗</a>`;if(cryptoPaymentInterval){clearInterval(cryptoPaymentInterval);cryptoPaymentInterval=null;}if(cryptoCountdownInterval){clearInterval(cryptoCountdownInterval);cryptoCountdownInterval=null;}await refresh();toast('Pago detectado. Pedido en revisión de pago.');}else if(p.status==='expired'){status.innerHTML='<span>×</span><span>Tiempo agotado. El pedido fue cancelado automáticamente. No envíes fondos a esta cotización.</span>';const countdown=$('cryptoCountdown');if(countdown)countdown.textContent='00:00';if(cryptoPaymentInterval){clearInterval(cryptoPaymentInterval);cryptoPaymentInterval=null;}if(cryptoCountdownInterval){clearInterval(cryptoCountdownInterval);cryptoCountdownInterval=null;}await refresh();toast('Cotización vencida; pedido cancelado.');}else{updateCryptoCountdown();status.innerHTML='<span class="pulse"></span><span>Esperando transferencia confirmada en la blockchain…</span>';}}catch(e){console.warn('No se pudo consultar el estado del pago USDT:',e.message);}}
let tenderlyPaymentInterval=null;let tenderlyCountdownInterval=null;let activeTenderlyPayment=null;
async function ensureTenderlyNetwork(provider){const expected=await api('/api/tenderly/network-check');const chain=await provider.request({method:'eth_chainId'});if(parseInt(chain,16)!==Number(expected.chain_id))throw new Error('La wallet no está en la red MainNet Lab (fork de Ethereum) configurada.');const block=await provider.request({method:'eth_getBlockByNumber',params:[expected.block_number,false]});if(!block||String(block.hash).toLowerCase()!==String(expected.block_hash).toLowerCase())throw new Error('La wallet no parece conectada al mismo fork de MainNet Lab que ProEshop. No firmes la transacción; selecciona el RPC de MainNet Lab correcto en tu wallet.');return expected;}
function tenderlyRawAmount(amount){const parts=String(amount).split('.');const whole=BigInt(parts[0]||'0');const fraction=BigInt(((parts[1]||'')+'000000').slice(0,6));return whole*1000000n+fraction;}
function renderTenderlyPayment(payment){activeTenderlyPayment=payment;const panel=$('cryptoPaymentPanel');panel.classList.remove('hidden');if(tenderlyPaymentInterval)clearInterval(tenderlyPaymentInterval);if(tenderlyCountdownInterval)clearInterval(tenderlyCountdownInterval);const deadline=payment.deadline_at?Date.parse(payment.deadline_at):Date.now()+Number(payment.remaining_seconds||300)*1000;panel.innerHTML=`<div class="form-section-title"><span>Ξ</span><div><b>Pago automatizado de prueba con USDT ERC-20</b><small>Pedido ${escapeHtml(payment.order_ref)}</small></div></div><div class="info-banner"><span>ⓘ</span><div><strong>MainNet Lab (fork de Ethereum)</strong><p>Chain ID 1 · entorno de pruebas. No es una confirmación de pago en Ethereum Mainnet.</p></div></div><div class="crypto-countdown-card"><small>TIEMPO PARA COMPLETAR EL PAGO</small><strong id="tenderlyCountdown">05:00</strong><span>El pedido se cancelará si la transferencia no se mina dentro de los 5 minutos.</span></div><label>Importe exacto <strong class="crypto-amount">${escapeHtml(payment.amount)} USDT</strong></label><label>Contrato USDT ERC-20 <input readonly value="${escapeHtml(payment.token_contract)}"></label><label>Dirección de recepción<div class="crypto-address-row"><input id="tenderlyReceivingAddress" readonly value="${escapeHtml(payment.address)}"><button id="copyTenderlyAddress" class="secondary" type="button">Copiar</button></div></label><div id="tenderlyPaymentStatus" class="notification-status"><span class="pulse"></span><span>Preparado para ejecutar el pago en MainNet Lab usando la wallet vinculada.</span></div><p id="tenderlyTxLink" class="hint"></p><button id="tenderlyPayNow" class="primary full" type="button">Procesar pago en MainNet Lab</button><button id="tenderlyBackToOrders" class="secondary full" type="button">Ver mis pedidos</button><p class="hint">La primera vez se solicitará una firma de mensaje para vincular tu wallet; no es una transferencia. Después, los pagos de prueba se ejecutan mediante la API privada de MainNet Lab sin pedir firma de transacción en MetaMask. Solo funciona en el fork aislado de MainNet Lab, nunca en Ethereum Mainnet. El pedido pasa a revisión únicamente tras verificar el recibo y el evento Transfer.</p>`;$('copyTenderlyAddress').onclick=async()=>{try{await navigator.clipboard.writeText(payment.address);toast('Dirección copiada');}catch(e){$('tenderlyReceivingAddress').select();toast('Selecciona y copia la dirección manualmente');}};$('tenderlyBackToOrders').onclick=async()=>{showView('history');try{await refresh()}catch(e){}};$('tenderlyPayNow').onclick=()=>sendTenderlyTransfer(payment);const tick=()=>{const el=$('tenderlyCountdown');const remaining=Math.max(0,Math.ceil((deadline-Date.now())/1000));if(el)el.textContent=String(Math.floor(remaining/60)).padStart(2,'0')+':'+String(remaining%60).padStart(2,'0');if(remaining<=0){if(tenderlyCountdownInterval)clearInterval(tenderlyCountdownInterval);$('tenderlyPaymentStatus').innerHTML='<span>×</span><span>Plazo vencido. Actualiza pedidos para consultar el estado final.</span>';}};tick();tenderlyCountdownInterval=setInterval(tick,1000);}
async function linkTenderlyWalletOnce(provider,wallet){const challenge=await api('/api/tenderly-wallet/challenge',{method:'POST',body:JSON.stringify({wallet_address:wallet})});if(challenge.linked)return;const messageHex='0x'+Array.from(new TextEncoder().encode(challenge.message)).map(b=>b.toString(16).padStart(2,'0')).join('');const signature=await provider.request({method:'personal_sign',params:[messageHex,wallet]});await api('/api/tenderly-wallet/link',{method:'POST',body:JSON.stringify({wallet_address:wallet,nonce:challenge.nonce,signature})});toast('Wallet vinculada. No tendrás que firmar cada pago de prueba.');}
async function sendTenderlyTransfer(payment){const btn=$('tenderlyPayNow');const status=$('tenderlyPaymentStatus');const provider=window.proEshopWalletProvider;const wallet=window.proEshopWalletAddress;if(!provider||!wallet){status.innerHTML='<span>!</span><span>Conecta MetaMask o Trust Wallet primero y vuelve al pedido.</span>';return;}try{btn.disabled=true;btn.textContent='Preparando pago…';status.innerHTML='<span class="pulse"></span><span>Verificando que la wallet esté vinculada y que el RPC de MainNet Lab…</span>';await linkTenderlyWalletOnce(provider,wallet);const net=await api('/api/tenderly/network-check');if(Number(window.proEshopWalletChainId)!==Number(net.chain_id))throw new Error('La wallet no está en la red configurada. No se enviará nada.');status.innerHTML='<span class="pulse"></span><span>Ejecutando la transferencia de prueba en MainNet Lab sin firma de transacción…</span>';btn.textContent='Ejecutando en MainNet Lab…';const result=await api('/api/tenderly-payment/'+encodeURIComponent(payment.order_ref)+'/execute',{method:'POST',body:JSON.stringify({wallet_address:wallet})});const txHash=result.tx_hash;if(!/^0x[0-9a-fA-F]{64}$/.test(txHash||''))throw new Error('MainNet Lab no devolvió un hash válido.');status.innerHTML='<span class="pulse"></span><span>Transferencia enviada a MainNet Lab. Verificando recibo y evento Transfer…</span>';$('tenderlyTxLink').textContent='Hash MainNet Lab: '+txHash;await verifyTenderlyTransfer(payment,txHash,wallet);}catch(e){console.warn('MainNet Lab USDT payment:',e);status.innerHTML='<span>!</span><span>'+escapeHtml(e.message||'No se pudo ejecutar el pago en MainNet Lab.')+' El pedido no se marcará como pagado. Revisa la configuración API privada de MainNet Lab.</span>';}finally{ if (btn.textContent !== 'Transferencia verificada') {
        btn.disabled = false;
        btn.textContent = 'Reintentar pago en MainNet Lab';
}}}
async function verifyTenderlyTransfer(payment,txHash,wallet){const status=$('tenderlyPaymentStatus');const btn=$('tenderlyPayNow');let attempts=0;async function check(){attempts++;try{const result=await api('/api/tenderly-payment/'+encodeURIComponent(payment.order_ref)+'/verify',{method:'POST',body:JSON.stringify({tx_hash:txHash,wallet_address:wallet})});if(result.status==='detected'){status.innerHTML='<span>✓</span><span>Transferencia verificada. Pedido en revisión de pago, pendiente de revisión administrativa.</span>';btn.disabled=true;btn.textContent='Transferencia verificada';if(tenderlyPaymentInterval)clearInterval(tenderlyPaymentInterval);if(tenderlyCountdownInterval)clearInterval(tenderlyCountdownInterval);toast('USDT verificado en MainNet Lab. Pedido en revisión.');await refresh();return true;}status.innerHTML='<span class="pulse"></span><span>'+escapeHtml(result.message||'Esperando confirmación en MainNet Lab…')+'</span>';return false;}catch(e){status.innerHTML='<span>!</span><span>'+escapeHtml(e.message||'No se pudo verificar todavía.')+'</span>';return false;}}if(await check())return;tenderlyPaymentInterval=setInterval(async()=>{if(++attempts>50){clearInterval(tenderlyPaymentInterval);tenderlyPaymentInterval=null;return;}if(await check()){clearInterval(tenderlyPaymentInterval);tenderlyPaymentInterval=null;}},5000);}
async function submitCheckout(ev){ev.preventDefault();if(checkoutSubmitting)return;if(!$('demoConsent').checked){$('checkoutError').textContent='Confirma el método de pago y las condiciones del pedido.';return;}const method=document.querySelector('input[name=payment_method]:checked')?.value||'demo_balance';if(method==='tenderly_usdt_erc20'&&(!window.proEshopWalletConnected||!window.proEshopWalletProvider||!window.proEshopWalletAddress)){$('checkoutError').textContent='Conecta MetaMask o Trust Wallet antes de crear el pedido de pago MainNet Lab.';return;}const btn=$('placeOrderBtn');checkoutSubmitting=true;btn.disabled=true;btn.textContent='Registrando pedido…';$('checkoutError').textContent='';const submittedCartSignature=cartSignature();const body={customer_email:$('orderEmail').value.trim(),email:$('orderEmail').value.trim(),shipping_name:$('shipName').value.trim(),shipping_city:$('shipCity').value.trim(),shipping_country:$('shipCountry').value.trim(),shipping_address:$('shipAddress').value.trim(),payment_method:method};try{const result=await api('/api/purchase',{method:'POST',body:JSON.stringify(body)});if(result.payment?.method==='usdt_trc20'){cryptoQuoteCartSignature=submittedCartSignature;renderCryptoPayment({...result.payment,order_ref:result.order_ref});$('checkoutForm').classList.add('hidden');showView('checkout');toast('Pedido creado. Envía el importe exacto en USDT TRC-20.');}else if(result.payment?.method==='tenderly_usdt_erc20'){renderTenderlyPayment({...result.payment,order_ref:result.order_ref});$('checkoutForm').classList.add('hidden');showView('checkout');toast('Pedido de prueba creado. Procesa la transferencia en MainNet Lab.');}else{showView('history');try{await refresh();}catch(refreshError){console.warn('Pedido registrado, pero no se pudo actualizar la pantalla:',refreshError);}const emailResults=Array.isArray(result.email_status)?result.email_status:[];const emailOk=emailResults.length>0&&emailResults.every(x=>x.email_sent);const emailFail=emailResults.filter(x=>!x.email_sent);toast(emailOk?`Pedido ${result.order_ref} registrado · proveedor aceptó todos los correos`:emailResults.length?`Pedido ${result.order_ref} registrado · ${emailFail.length} correo(s) pendientes; revisa el panel/logs`:`Pedido ${result.order_ref} registrado`);}if(tg&&typeof tg.HapticFeedback?.notificationOccurred==='function')tg.HapticFeedback.notificationOccurred('success');}catch(e){$('checkoutError').textContent=e.message||'No se pudo registrar el pedido.';}finally{checkoutSubmitting=false;btn.disabled=false;updateCheckoutPaymentCopy();}}
// Navigation: preserve the original API routes and session model.
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',async()=>{const tab=b.dataset.tab;if(tab==='search'){showView('home');setTimeout(()=>$('query')?.focus(),120);return;}if(['home','cart','checkout','history','account'].includes(tab)){if(tab!=='home')try{await refresh()}catch(e){toast(e.message);return;}if(tab==='checkout'){openCheckout();return;}showView(tab);}}));
function setStoreContent(store){const isCanAm=String(store||'').toLowerCase()==='canam';const home=$('shopView');if(!home)return;['.greeting-row','.balance-card','.search-wrap','.hero-banner','.category-section','.results-section-head','#searchResult','#homeEmpty','.quick-grid','.info-banner'].forEach(sel=>{const el=home.querySelector(sel);if(el)el.classList.toggle('hidden',isCanAm);});const configurator=$('canamConfigurator');if(configurator)configurator.classList.toggle('hidden',!isCanAm);home.classList.toggle('canam-home-active',isCanAm);}
window.proEshopAddCanAmToCart=async function(config){const price=Number(config?.price);if(!Number.isFinite(price)||price<=0||price>10000000)throw new Error('El total de la configuración no es válido.');await api('/api/cart',{method:'POST',body:JSON.stringify({platform:'canam',title:String(config.title||'Can-Am Maverick R 2027').slice(0,180),price:price.toFixed(2),currency:'USD',url:'https://can-am.brp.com/off-road/us/es/personaliza-el-tuyo/vehiculos-side-by-side/maverick-r.html',image:String(config.image||'')})});await refresh();toast('Configuración Can-Am agregada al carrito.');};
document.querySelectorAll('.store').forEach(b=>b.onclick=()=>{selectedStore=b.dataset.store;document.querySelectorAll('.store').forEach(x=>x.classList.toggle('active',x===b));if(selectedStore==='canam'){setStoreContent('canam');return;}setStoreContent(selectedStore);});
document.querySelectorAll('[data-search-store]').forEach(b=>b.addEventListener('click',()=>performSearch(undefined,b.dataset.searchStore)));
function saveAuth(data){token=data.token;authAccountType=data.account_type||'';authDisplayName=data.username||data.email||'Invitado';sessionStorage.setItem('shopcart_token',token);sessionStorage.setItem('shopcart_account_type',authAccountType);sessionStorage.setItem('shopcart_display_name',authDisplayName);setLoggedIn(true);return refresh();}
document.querySelectorAll('[data-auth-tab]').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('[data-auth-tab]').forEach(b=>b.classList.toggle('active',b===btn));$('loginForm').classList.toggle('hidden',btn.dataset.authTab!=='login');$('registerForm').classList.toggle('hidden',btn.dataset.authTab!=='register');$('loginError').textContent='';$('authMessage').textContent='';}));
$('loginForm').addEventListener('submit',async e=>{e.preventDefault();$('loginError').textContent='';$('authMessage').textContent='';try{const data=await api('/api/email-login',{method:'POST',body:JSON.stringify({email:$('loginEmail').value.trim(),password:$('password').value})});await saveAuth(data);toast('Bienvenido a ProEshop');}catch(err){$('loginError').textContent=err.message;}});
$('registerForm').addEventListener('submit',async e=>{e.preventDefault();$('loginError').textContent='';$('authMessage').textContent='';if($('registerPassword').value!==$('registerPassword2').value){$('loginError').textContent='Las contraseñas no coinciden.';return;}const submitBtn=$('registerForm').querySelector('button[type=submit]');const email=$('registerEmail').value.trim();if(submitBtn){submitBtn.disabled=true;submitBtn.textContent='Creando cuenta…';}try{const data=await api('/api/register',{method:'POST',body:JSON.stringify({email,password:$('registerPassword').value})});$('verificationSentText').textContent=`Enviamos un correo a ${email}. Abre el enlace de verificación para activar tu cuenta. Después volverás automáticamente al inicio de sesión.`;$('registerForm').reset();const dlg=$('verificationSentDialog');if(dlg&&!dlg.open)dlg.showModal();}catch(err){$('loginError').textContent=err.message;}finally{if(submitBtn){submitBtn.disabled=false;submitBtn.innerHTML='Crear cuenta <span>→</span>';}}});
function closeVerificationSent(){const dlg=$('verificationSentDialog');if(dlg?.open)dlg.close();}
$('closeVerificationSent')?.addEventListener('click',closeVerificationSent);$('verificationSentOk')?.addEventListener('click',closeVerificationSent);$('verificationSentDialog')?.addEventListener('click',e=>{if(e.target===$('verificationSentDialog'))closeVerificationSent();});
function showEmailVerifiedLogin(){const params=new URLSearchParams(location.search);if(params.get('email_verified')==='1'){document.querySelector('[data-auth-tab=login]')?.click();$('authMessage').textContent='¡Correo verificado! Tu cuenta está activa. Inicia sesión para continuar.';history.replaceState({},'',location.pathname+location.hash);}}
$('guestLoginBtn').onclick=async()=>{try{const data=await api('/api/guest-session',{method:'POST',body:'{}'});await saveAuth(data);toast('Continúas como invitado');}catch(e){$('loginError').textContent=e.message;}};
$('telegramLoginBtn').onclick=async()=>{if(!tg?.initData){$('loginError').textContent='Abre ProEshop desde el bot de Telegram para usar este acceso.';return;}try{const data=await api('/api/telegram-login',{method:'POST',body:JSON.stringify({init_data:tg.initData})});await saveAuth(data);toast('Acceso con Telegram correcto');}catch(e){$('loginError').textContent=e.message;}};
$('linkTelegramBtn').onclick=async()=>{if(!tg?.initData){$('linkTelegramMessage').textContent='Abre la Mini App desde Telegram para vincular tu cuenta.';return;}try{const r=await api('/api/link-telegram',{method:'POST',body:JSON.stringify({init_data:tg.initData})});$('linkTelegramMessage').textContent=r.message;toast('Telegram vinculado');}catch(e){$('linkTelegramMessage').textContent=e.message;}};
async function exploreLuxuryCategory(platform){
  const requested=String(platform||'rolex').toLowerCase();
  const chosen=requested==='joyeria'?'jewelers':requested;
  const queryByStore={rolex:'todos',hublot:'todos',jewelers:'joyeria'};
  selectedStore=chosen;
  document.querySelectorAll('.store').forEach(x=>x.classList.toggle('active',x.dataset.store===chosen));
  $('query').value=queryByStore[chosen]||'todos';
  $('homeEmpty').classList.add('hidden');
  $('searchResult').classList.remove('hidden');
  $('searchResult').innerHTML='<div class="home-empty"><div class="empty-orbit">✦</div><strong>Preparando selección de lujo…</strong><p>Eligiendo hasta 15 productos del catálogo.</p></div>';
  try{
    const r=await api('/api/search',{method:'POST',body:JSON.stringify({platform:chosen,query:queryByStore[chosen]||'todos'})});
    let all=Array.isArray(r.live_results)?r.live_results.slice():[];
    if(['hublot','jewelers'].includes(chosen)) all=all.map(x=>({...x,list_price:Number(x.list_price||x.price),price:Number(x.price)/2}));
    // Fisher-Yates shuffle, then show exactly 15 distinct products whenever the catalog has them.
    for(let i=all.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[all[i],all[j]]=[all[j],all[i]];}
    lastSearch=all.slice(0,15); lastSearchResponse={...r,live_results:lastSearch};
    r.live_results=lastSearch;
    $('searchResult').innerHTML=`<div class="results-heading"><div><h3>${escapeHtml(({rolex:'ROLEX',hublot:'HUBLOT',jewelers:'JOYERÍA'})[chosen]||'Lujo')} · Selección aleatoria</h3><p id="resultCount">${lastSearch.length} productos de catálogo</p></div><span class="live-dot">USD</span></div><p>${escapeHtml(r.notice||'Catálogo de lujo ProEshop.')}</p><div class="filter-row"><label>Precio mínimo<input id="minPrice" type="number" min="0" step="1" placeholder="USD 0"></label><label>Precio máximo<input id="maxPrice" type="number" min="0" step="1" placeholder="Sin límite"></label><label>Ordenar por<select id="sortResults"><option value="relevance">Selección aleatoria</option><option value="low">Menor precio</option><option value="high">Mayor precio</option></select></label></div><div class="filter-extra"><label><input id="showImages" type="checkbox" checked> Mostrar imágenes</label><span class="view-toggle"><button type="button" class="active" data-layout="grid">▦</button><button type="button" data-layout="list">☰</button></span></div><a class="external" href="${escapeHtml(r.search_url||'#')}" target="_blank" rel="noopener noreferrer">Ver catálogo del proveedor ↗</a><div id="comparePanel" class="compare-panel hidden"></div><div class="product-results"></div><p class="hint">Selección aleatoria de 15 referencias del catálogo disponible.</p>`;
    const redraw=()=>renderResults(r); ['minPrice','maxPrice','sortResults'].forEach(id=>$(id).addEventListener(id==='sortResults'?'change':'input',redraw));
    $('showImages').onchange=e=>document.querySelectorAll('.product-thumb').forEach(img=>img.classList.toggle('hidden',!e.target.checked));
    document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-layout]').forEach(x=>x.classList.toggle('active',x===b));$('searchResult').querySelector('.product-results')?.classList.toggle('list-layout',b.dataset.layout==='list')});
    renderResults(r); renderCompare(); $('searchResult').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){$('searchResult').innerHTML=`<div class="empty"><div>⚠</div><strong>No se pudo cargar el catálogo</strong><p>${escapeHtml(e.message)}</p><button class="secondary" id="retryCategory">Intentar de nuevo</button></div>`;$('retryCategory').onclick=()=>exploreLuxuryCategory(chosen);}
}
$('searchBtn').onclick=()=>performSearch();$('query').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();performSearch();}});$('clearSearch').onclick=()=>{$('query').value='';$('clearSearch').classList.add('hidden');$('searchResult').classList.add('hidden');$('homeEmpty').classList.remove('hidden');lastSearch=[];$('query').focus();};
document.querySelectorAll('[data-query]').forEach(b=>b.addEventListener('click',()=>performSearch(b.dataset.query)));document.querySelectorAll('[data-luxury-category]').forEach(b=>b.addEventListener('click',()=>exploreLuxuryCategory(b.dataset.luxuryCategory)));document.querySelectorAll('[data-category]').forEach(b=>b.addEventListener('click',()=>exploreLuxuryCategory(b.dataset.category)));document.querySelectorAll('[data-focus-search]').forEach(b=>b.addEventListener('click',()=>$('query').focus()));
$('checkoutBtn').onclick=openCheckout;$('checkoutForm').addEventListener('submit',submitCheckout);document.querySelectorAll('input[name=payment_method]').forEach(el=>el.addEventListener('change',updateCheckoutPaymentCopy));$('refreshOrders').onclick=async()=>{try{await refresh();toast('Pedidos actualizados');}catch(e){toast(e.message)}};$('orderCategoryFilter')?.addEventListener('change',applyOrderFilters);$('orderStoreFilter')?.addEventListener('change',applyOrderFilters);
$('notificationBtn').onclick=async()=>{await loadNotificationPreferences();$('notificationDialog').showModal()};$('saveNotificationsBtn').onclick=saveNotificationPreferences;$('adminOpenBtn').onclick=loadAdminMetrics;$('adminRefreshBtn').onclick=loadAdminMetrics;$('closeNotificationDialog').onclick=()=>$('notificationDialog').close();$('closeNotificationOk').onclick=()=>$('notificationDialog').close();$('closeProductDialog').onclick=()=>$('productDialog').close();$('logoutAccountBtn').onclick=()=>$('logoutBtn').click();
$('logoutBtn').onclick=async()=>{try{await api('/api/logout',{method:'POST',body:'{}'});}catch(_){}token='';authAccountType='';authDisplayName='';sessionStorage.removeItem('shopcart_token');sessionStorage.removeItem('shopcart_account_type');sessionStorage.removeItem('shopcart_display_name');setLoggedIn(false);$('password').value='';$('loginError').textContent='';toast('Sesión cerrada');};
showEmailVerifiedLogin();
(async()=>{
  // Telegram startapp payload issued after email verification. Exchange it once for a server session.
  const startParam=String(tg?.initDataUnsafe?.start_param||'');
  if(startParam.startsWith('verify_') && tg?.initData){
    try{
      const handoff=await fetch('/api/telegram-verification-handoff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:startParam,init_data:tg.initData})});
      const data=await handoff.json().catch(()=>({detail:'No se pudo completar el acceso.'}));
      if(!handoff.ok) throw new Error(data.detail||'No se pudo completar el acceso.');
      await saveAuth(data); toast('Correo verificado. Sesión iniciada.');
      return;
    }catch(err){ console.error('Telegram verification handoff:',err); $('loginError').textContent=err.message; }
  }
  if(token){try{setLoggedIn(true);await refresh();}catch(_){token='';sessionStorage.removeItem('shopcart_token');sessionStorage.removeItem('shopcart_account_type');sessionStorage.removeItem('shopcart_display_name');setLoggedIn(false);showEmailVerifiedLogin();}}
})();


/* ProEshop wallet balance: WalletConnect/Reown + injected MetaMask. Read-only USDT balance; no signing or transfers. */
(function(){
 const PROJECT_ID=window.PROESHOP_REOWN_PROJECT_ID || '8964c13e0d85a4ac687ce9ebd7474d87';
 const $w=id=>document.getElementById(id);
 const state={provider:null,address:'',walletName:'',chainId:null,ethereumProvider:null,connecting:false};
 window.proEshopWalletConnected=false;
 window.proEshopWalletBalanceDisplay=null;
 const networks={
  1:{name:'Ethereum',token:'0xdAC17F958D2ee523a2206206994597C13D831ec7',decimals:6},
  56:{name:'BNB Smart Chain',token:'0x55d398326f99059fF775485246999027B3197955',decimals:18},
  137:{name:'Polygon',token:'0xc2132D05D31c914a87C6611C10748AaCbAbaB0',decimals:6}
 };
 function status(t){const e=$w('walletConnectStatus');if(e)e.textContent=t;}
 function fmt(n){return Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:6})}
 function short(a){return a?a.slice(0,6)+'…'+a.slice(-4):'Sin conectar'}
 let pendingWalletUri='';
 function setBusy(b){state.connecting=b;['connectMetaMask','connectTrustWallet','connectWalletSelector','walletMetaMaskChoice','walletTrustChoice','walletCopyUri'].forEach(id=>{const e=$w(id);if(e)e.disabled=b});}
 function renderConnected(){
  window.proEshopWalletConnected=true;
  window.proEshopWalletProvider=state.provider;
  window.proEshopWalletAddress=state.address;
  window.proEshopWalletChainId=state.chainId;
  const mainConnect=$w('connectWalletSelector');
  if(mainConnect){mainConnect.textContent='Conectado';mainConnect.classList.add('wallet-connected');mainConnect.disabled=false;}
  $w('walletAddressShort').textContent=short(state.address);
  $w('walletConnectionLabel').textContent=state.walletName.toUpperCase();
  $w('refreshWalletBalance').disabled=false;$w('disconnectWallet').disabled=false;
 }
 async function balance(){
  if(!state.provider||!state.address)return;
  const chainHex=await state.provider.request({method:'eth_chainId'});
  state.chainId=parseInt(chainHex,16);
  const net=networks[state.chainId];
  if(!net){
   window.proEshopWalletBalanceDisplay='Red no compatible';
   $w('balanceValue').textContent='Red no compatible';
   $w('walletBalanceCaption').textContent='Cambia a Ethereum, BNB Smart Chain o Polygon';
   status('Red no compatible. Este panel consulta USDT en Ethereum, BNB Chain o Polygon.');
   return;
  }
  status('Consultando USDT en '+net.name+'…');
  const data='0x70a08231'+state.address.toLowerCase().replace('0x','').padStart(64,'0');
  const raw=await state.provider.request({method:'eth_call',params:[{to:net.token,data},'latest']});
  const amount=Number(BigInt(raw))/Math.pow(10,net.decimals);
  window.proEshopWalletBalanceDisplay=fmt(amount)+' USDT';
  $w('balanceValue').textContent=window.proEshopWalletBalanceDisplay;
  $w('walletBalanceCaption').textContent='USDT · '+net.name+' · saldo consultado en blockchain';
  status('Saldo actualizado correctamente.');
  renderConnected();
 }
 async function attach(provider,name){
  state.provider=provider;state.walletName=name;
  const accounts=await provider.request({method:'eth_requestAccounts'});
  if(!accounts||!accounts.length)throw new Error('La billetera no devolvió una cuenta.');
  state.address=accounts[0];renderConnected();
  if(provider.on){
   provider.on('accountsChanged',async a=>{if(!a||!a.length){disconnect(false);return;}state.address=a[0];renderConnected();try{await balance()}catch(e){status('No se pudo consultar el saldo: '+e.message)}});
   provider.on('chainChanged',async()=>{try{await balance()}catch(e){status('No se pudo consultar el saldo: '+e.message)}});
   provider.on('disconnect',()=>disconnect(false));
  }
  await balance();
 }
 async function connectInjected(){
  const eth=window.ethereum;
  if(!eth)throw new Error('No se detectó MetaMask en este navegador. Usa WalletConnect o abre ProEshop desde la billetera.');
  await attach(eth,'MetaMask');
 }
 async function connectWC(name, walletTarget=''){
  const EthereumProvider=window.ProEshopEthereumProvider;
  if(!EthereumProvider || typeof EthereumProvider.init!=='function'){
   throw new Error('El módulo local de WalletConnect no cargó. Verifica que Railway haya ejecutado npm run build:wallet y que exista /static/walletconnect.bundle.js.');
  }
  if(!PROJECT_ID || PROJECT_ID.length < 20){
   throw new Error('El Project ID de WalletConnect no está configurado correctamente.');
  }
  status('Inicializando WalletConnect…');
  let timer, wc;
  try{
   wc=await Promise.race([
    EthereumProvider.init({
     projectId:PROJECT_ID,
     chains:[1,56,137],
     optionalChains:[1,56,137],
     showQrModal:false,
     methods:['eth_sendTransaction','personal_sign','eth_signTypedData','eth_signTypedData_v4','eth_accounts','eth_chainId','eth_call','eth_getBlockByNumber'],
     events:['chainChanged','accountsChanged'],
     metadata:{name:'ProEshop',description:'Consulta de saldo USDT',url:location.origin,icons:[]}
    }),
    new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('WalletConnect no respondió en 15 segundos. Revisa la red e inténtalo de nuevo.')),15000);})
   ]);
  }finally{clearTimeout(timer);}
  state.ethereumProvider=wc;
  wc.on('display_uri',uri=>{
   if(!uri)return;
   pendingWalletUri=uri;
   const copy=$w('walletCopyUri');if(copy)copy.disabled=false;
   status('Solicitud creada. Autoriza la conexión en '+name+' y vuelve a ProEshop.');
   if(walletTarget==='metamask'){
    const target='https://metamask.app.link/wc?uri='+encodeURIComponent(uri);
    try{
     if(window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(target);
     else window.location.href=target;
    }catch(e){console.warn('MetaMask deep link:',e);status('No se pudo abrir MetaMask automáticamente. Usa “Copiar URI para otra billetera”.');}
   }else if(walletTarget==='trustwallet'){
    const target='https://link.trustwallet.com/wc?uri='+encodeURIComponent(uri);
    try{
     if(window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(target);
     else window.location.href=target;
    }catch(e){console.warn('Trust Wallet deep link:',e);status('No se pudo abrir Trust Wallet automáticamente. Usa “Copiar URI para otra billetera”.');}
   }
  });
  status('Esperando la solicitud de conexión…');
  await wc.connect();
  await attach(wc,name);
 }
 function findInjectedProvider(which){
  const providers=[];
  if(window.ethereum){
   if(Array.isArray(window.ethereum.providers))providers.push(...window.ethereum.providers);
   providers.push(window.ethereum);
  }
  if(which==='metamask')return providers.find(p=>p.isMetaMask&&!p.isTrust&&!p.isTrustWallet)||providers.find(p=>p.isMetaMask)||null;
  return providers.find(p=>p.isTrust||p.isTrustWallet)||null;
 }
 function disconnect(show=true){
  try{if(state.ethereumProvider&&state.ethereumProvider.disconnect)state.ethereumProvider.disconnect()}catch(e){}
  state.provider=null;state.address='';state.walletName='';state.chainId=null;state.ethereumProvider=null;pendingWalletUri='';
  window.proEshopWalletBalanceDisplay=null;
  window.proEshopWalletConnected=false;
  window.proEshopWalletProvider=null;
  window.proEshopWalletAddress=null;
  window.proEshopWalletChainId=null;
  const mainConnect=$w('connectWalletSelector');
  if(mainConnect){mainConnect.textContent='Conectar mi wallet';mainConnect.classList.remove('wallet-connected');mainConnect.disabled=false;}
  const b=$w('balanceValue');if(b)b.textContent='Conecta tu billetera';
  const c=$w('walletBalanceCaption');if(c)c.textContent='Saldo USDT de la red conectada';
  const a=$w('walletAddressShort');if(a)a.textContent='Sin conectar';
  const l=$w('walletConnectionLabel');if(l)l.textContent='PROESHOP WALLET';
  $w('refreshWalletBalance').disabled=true;$w('disconnectWallet').disabled=true;
  status('Billetera desconectada. El saldo interno no se modifica.');
  if(show&&window.toast)window.toast('Billetera desconectada.');
 }
 async function runConnect(which){
  if(state.connecting)return;
  setBusy(true);
  try{
   const injected=findInjectedProvider(which);
   if(injected && (which==='metamask'||which==='trustwallet')){
    await attach(injected,which==='metamask'?'MetaMask':'Trust Wallet');
   }else{
    await connectWC(which==='metamask'?'MetaMask':'Trust Wallet',which);
   }
  }catch(e){
   console.warn('Wallet connect:',e);
   if(e&&e.code===4001)status('Conexión cancelada en la billetera.');
   else status((e&&e.message)||'No se pudo completar la conexión. Intenta nuevamente.');
  }finally{setBusy(false);}
 }
 function openWalletDialog(){
  const d=$w('walletConnectDialog');
  if(d && !d.open){if(typeof d.showModal==='function')d.showModal();else d.setAttribute('open','');}
 }
 function closeWalletDialog(){
  const d=$w('walletConnectDialog');
  if(d?.open && typeof d.close==='function')d.close();else d?.removeAttribute('open');
 }
 document.addEventListener('DOMContentLoaded',()=>{
  // Keep the two direct wallet actions and the universal WalletConnect selector wired.
  $w('connectMetaMask')?.addEventListener('click',()=>runConnect('metamask'));
  $w('connectTrustWallet')?.addEventListener('click',()=>runConnect('trustwallet'));
  $w('connectWalletSelector')?.addEventListener('click',openWalletDialog);
  $w('walletMetaMaskChoice')?.addEventListener('click',()=>{closeWalletDialog();runConnect('metamask')});
  $w('walletTrustChoice')?.addEventListener('click',()=>{closeWalletDialog();runConnect('trustwallet')});
  $w('walletCopyUri')?.addEventListener('click',async()=>{
   if(!pendingWalletUri){status('Todavía no hay un URI para copiar. Selecciona MetaMask o Trust Wallet primero.');return;}
   try{
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(pendingWalletUri);
    else {const t=document.createElement('textarea');t.value=pendingWalletUri;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();}
    status('URI copiado. Pégalo en la billetera compatible.');
   }catch(e){status('No se pudo copiar el URI. Inténtalo de nuevo.');}
  });
  $w('walletCancelConnect')?.addEventListener('click',closeWalletDialog);
  $w('refreshWalletBalance')?.addEventListener('click',async()=>{try{await balance()}catch(e){status('Error al actualizar: '+e.message)}});
  $w('disconnectWallet')?.addEventListener('click',()=>disconnect(true));
 });
})();


/* Native Can-Am configurator: embedded in ProEshop, no iframe or external HTML/JS. */
(function(){

const models=[
{id:'x',name:'MAVERICK R X',price:39699,seats:'2 plazas',terrain:'Sand & Dunes',susp:'FOX 2.5 PODIUM QS3',tires:'32″ ITP XNR Tenacity',wheels:'16″ Flow Formed',screen:'10.25″ + cámara trasera',colors:[
{name:'Granite Grey / Orange Crush',hex:'#777b7d',accent:'#f07822',url:'https://can-am.brp.com/content/dam/global/en/can-am-off-road/my27/studio/na/ssv/maverick-r/ORV-MY27-SSV-MAV-R-X-MillNT-GRANITE-GREY-0008GVA00-STUDIO-661x480-SHADOW-34F-NA.png'}]},
{id:'xrs',name:'MAVERICK R X rs',price:44199,seats:'2 plazas',terrain:'Sand & Dunes',susp:'FOX 3.0 PODIUM RC2',tires:'32″ ITP XNR Tenacity',wheels:'16″ Flow Formed Beadlock',screen:'10.25″ + cámaras delantera/trasera',colors:[
{name:'Dolomite Grey / Orange Crush',hex:'#777b7d',accent:'#f07822',url:'https://can-am.brp.com/content/dam/global/en/can-am-off-road/my27/studio/na/ssv/maverick-r/ORV-MY27-SSV-MAV-R-XrsSAS-MillNT-DOLOMITE-GREY-0007AVF00-STUDIO-661x480-SHADOW-34F-NA.png'},
{name:'Triple Black',hex:'#161719',accent:'#08090b',url:'https://can-am.brp.com/content/dam/global/en/can-am-off-road/my27/studio/na/ssv/maverick-r/ORV-MY27-SSV-MAV-R-Xrs-MillNT-BLACK-0007AVB00-STUDIO-661x480-SHADOW-34F-NA.png'}]},
{id:'xrc',name:'MAVERICK R X rc',price:48199,seats:'2 plazas',terrain:'Rock Crawling + Sand & Dunes',susp:'FOX 3.0 PODIUM RC2 · Smart-Lok modo Rock',tires:'35″ XPS Hammer King',wheels:'16″ Flow Formed Beadlock',screen:'10.25″ + cámaras delantera/trasera',colors:[
{name:'Loft Green Satin',hex:'#6c7565',accent:'#a5ad91',url:'https://can-am.brp.com/content/dam/global/en/can-am-off-road/my27/studio/na/ssv/maverick-r/ORV-MY27-SSV-MAV-R-Xrc-MillNT-LOFT-GREEN-0007GVD00-STUDIO-661x480-SHADOW-34F-NA.png'}]},
{id:'maxx',name:'MAVERICK R MAX X',price:43499,seats:'4 plazas',terrain:'Sand & Dunes',susp:'FOX 2.5 PODIUM QS3',tires:'32″ ITP XNR Tenacity',wheels:'16″ Flow Formed',screen:'10.25″ + cámara trasera',colors:[
{name:'Granite Grey / Orange Crush',hex:'#777b7d',accent:'#f07822',url:'https://can-am.brp.com/content/dam/global/en/can-am-off-road/my27/studio/na/ssv/maverick-r/ORV-MY27-SSV-MAV-R-MAX-X-MillNT-GRANITE-GREY-0008HVA00-STUDIO-661x480-SHADOW-34F-NA.png'}]},
{id:'maxxrs',name:'MAVERICK R MAX X rs',price:47699,seats:'4 plazas',terrain:'Sand & Dunes',susp:'FOX 3.0 PODIUM RC2',tires:'32″ ITP XNR Tenacity',wheels:'16″ Flow Formed Beadlock',screen:'10.25″ + cámaras delantera/trasera',colors:[
{name:'Dolomite Grey / Orange Crush',hex:'#777b7d',accent:'#f07822',url:'https://can-am.brp.com/content/dam/global/en/can-am-off-road/my27/studio/na/ssv/maverick-r/ORV-MY27-SSV-MAV-R-MAX-XrsSAS-MillNT-DOLOMITE-GREY-0007DVF00-STUDIO-661x480-SHADOW-34F-NA.png'},
{name:'Triple Black',hex:'#161719',accent:'#08090b',url:'https://can-am.brp.com/content/dam/global/en/can-am-off-road/my27/studio/na/ssv/maverick-r/ORV-MY27-SSV-MAV-R-MAX-XrsSAS-MillNT-BLACK-0007DVB00-STUDIO-661x480-SHADOW-34F-NA.png'}]},
{id:'maxxrc',name:'MAVERICK R MAX X rc',price:51699,seats:'4 plazas',terrain:'Rock Crawling + Trail',susp:'FOX 3.0 PODIUM RC2 · Smart-Lok modo Rock',tires:'35″ XPS Hammer King',wheels:'16″ Flow Formed Beadlock',screen:'10.25″ + cámaras delantera/trasera',colors:[
{name:'Loft Green Satin',hex:'#6c7565',accent:'#a5ad91',url:'https://can-am.brp.com/content/dam/global/en/can-am-off-road/my27/studio/na/ssv/maverick-r/ORV-MY27-SSV-MAV-R-MAX-XrcSAS-MillNT-LOFT-GREEN-0007JVE00-STUDIO-661x480-SHADOW-34F-NA.png'}]}
];
let selected=0,colorIndex=0,angle=0;
const viewLabels=['Vista de catálogo · 3/4 frontal','Vista lateral simulada · no es una foto independiente','Vista trasera simulada · no es una foto independiente'];


// Categorías tomadas del catálogo oficial de accesorios Maverick R de Can-Am.
// Los precios se tomaron de la tienda oficial Can-Am BRP de Estados Unidos y están expresados en USD; pueden variar por promociones, envío o cambios del fabricante.
const accessoryCategories=[
{id:'roof',name:'Techo y admisión',icon:'roof',items:[
{id:'sport-roof',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-sport-roof-715007364.html',urlMax:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-sport-roof-715008074.html',name:'Sport Roof',partR:'715007364',partMax:'715008074',price:529.99,priceMax:909.99,fit:'family',note:'Referencia del catálogo oficial Can-Am Maverick R: versión Maverick R y versión Maverick R MAX, según referencia indicada.'},
{id:'cold-air-scoop',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-cold-air-roof-scoop-715008280.html',urlMax:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-cold-air-roof-scoop-715008301.html',name:'Cold Air Roof Scoop',partR:'715008280',partMax:'715008301',price:559.99,priceMax:789.99,fit:'family',note:'Can-Am lo indica como requisito para los parabrisas completos. Requiere Sport Roof o Can-Am JL Audio Roof; no compatible con Audio Roof Flip Kit.'}
]},
{id:'wind',name:'Parabrisas y protección contra el viento',icon:'wind',items:[
{id:'wind-hardcoat',url:'https://can-am-shop.brp.com/off-road/us/en/maverick-r/accessories/windshields-wind-protections.html',name:'Parabrisas completo hardcoated',part:'715007321',price:919.99,fit:'family',requires:['cold-air-scoop'],conflicts:['audio-roof-flip'],note:'Referencia oficial para Maverick R y Maverick R MAX. Requiere Cold Air Roof Scoop; compatible con SMART Integrated LED Roof Light; no compatible con Audio Roof Flip Kit.'},
{id:'wind-glass',url:'https://can-am-shop.brp.com/off-road/us/en/maverick-r/accessories/windshields-wind-protections.html',name:'Parabrisas de vidrio',part:'715007181',price:1299.99,fit:'family',requires:['cold-air-scoop'],conflicts:['audio-roof-flip'],note:'Referencia oficial para Maverick R y Maverick R MAX. Requiere Cold Air Roof Scoop y kit limpiaparabrisas/lavaparabrisas; compatible con SMART Integrated LED Roof Light.'},
{id:'wind-powerflip',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-powerflip-windshield-715009900.html',name:'Parabrisas PowerFlip',part:'715009900',price:1849.99,fit:'family',requires:['cold-air-scoop'],conflicts:['audio-roof-flip','smart-roof-light'],note:'Referencia oficial para Maverick R y Maverick R MAX. Requiere Cold Air Roof Scoop y ACM (715010097) o arnés (715008854). No compatible con SMART Integrated LED Roof Light ni Audio Roof Flip Kit.'},
{id:'wiper-washer',url:'https://can-am-shop.brp.com/off-road/us/en/maverick-r/accessories/windshields-wind-protections.html',name:'Kit limpiaparabrisas y lavaparabrisas',part:'715007173',price:789.99,fit:'family',requires:['wind-glass'],note:'Can-Am lo indica para parabrisas de vidrio o hardcoated; la ficha del producto detalla las combinaciones admitidas.'}
]},
{id:'mirrors',name:'Retrovisores',icon:'mirror',items:[
{id:'aluminum-mirrors',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-x3-maverick-r-aluminum-side-mirrors-715007363.html',name:'Retrovisores laterales de aluminio',part:'715007363',price:369.99,fit:'family',note:'Referencia listada en el catálogo oficial Maverick R. Requeridos para instalar las luces SMART integradas en los retrovisores.'}
]},
{id:'protection',name:'Protectores, chasis y parachoques',icon:'shield',items:[]},
{id:'cargo',name:'LinQ, portaequipajes y almacenamiento',icon:'cargo',items:[
{id:'side-cargo',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-linq-36-us-gal-135-l-side-cargo-boxes-715007372.html',name:'Cajas laterales LinQ 13,5 L',part:'715007372',price:394.99,fit:'family',note:'Accesorio listado en el catálogo oficial de accesorios Maverick R.'},
{id:'trunk-box',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-linq-254-us-gal-96-l-trunk-box-715007182.html',name:'Maleta LinQ 96 L',part:'715007182',price:539.99,fit:'family',note:'Accesorio listado en la página oficial de accesorios Can-Am para la familia Maverick.'}
]},
{id:'electronics',name:'Módulos ACM / SMART y electrónica',icon:'circuit',items:[
{id:'acm',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-smart-accessory-control-module-715010097.html',name:'Accessory Control Module (ACM)',part:'715010097',price:619.99,fit:'family',note:'Módulo oficial requerido para la funcionalidad SMART de accesorios compatibles.'},
{id:'powerflip-harness',url:'https://can-am-shop.brp.com/off-road/us/en/maverick-r/accessories/windshields-wind-protections.html',name:'Arnés para parabrisas PowerFlip',part:'715008854',price:144.99,fit:'family',note:'Can-Am lo indica como alternativa al ACM para instalar el parabrisas PowerFlip.'},
{id:'xrc-roof-harness',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-x-rc-roof-harness-715010620.html',name:'Arnés de techo para modelos X rc',part:'715010620',price:54.99,fit:'rc',note:'Can-Am lo especifica para la funcionalidad SMART de la luz LED de techo en modelos X rc.'}
]},
{id:'lights',name:'Luces',icon:'light',items:[
{id:'smart-roof-light',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-smart-integrated-led-roof-light-715007322.html',name:'SMART Integrated LED Roof Light',part:'715007322',price:1374.99,fit:'family',conflicts:['wind-powerflip','audio-roof-flip'],note:'Can-Am la lista para Maverick R y Maverick R MAX. No compatible con parabrisas PowerFlip ni Audio Roof Flip Kit. Requiere ACM para función SMART o arnés 715008209 para encendido/apagado.'},
{id:'smart-hood-light',url:'https://can-am-shop.brp.com/off-road/us/en/maverick-r/accessories/lights-light-bars.html',name:'SMART Integrated LED Hood Light',part:'715007378',price:394.99,fit:'family',note:'Can-Am la lista para Maverick R y Maverick R MAX. Requiere ACM para función SMART o arnés 715008211 para encendido/apagado.'},
{id:'smart-mirror-lights',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-x3-maverick-r-smart-integrated-led-side-mirror-lights-715007185.html',name:'SMART Integrated LED Side Mirror Lights',part:'715007185',price:359.99,fit:'family',requires:['aluminum-mirrors'],note:'Can-Am las lista para Maverick R y Maverick R MAX. Requieren retrovisores de aluminio 715007363 y ACM o arnés 715008212.'}
]},
{id:'audio',name:'Sistemas de audio',icon:'audio',items:[
{id:'audio-roof-flip',url:'https://can-am-shop.brp.com/off-road/us/en/can-am-maverick-r-jl-audio-roof-flip-kit-715008164.html',name:'Audio Roof Flip Kit',part:'715008164',price:629.99,fit:'notRc',conflicts:['cold-air-scoop','wind-hardcoat','wind-glass','wind-powerflip','smart-roof-light'],note:'Se muestra solo para versiones que no incluyen el sistema JL Audio Nivel 3 de fábrica. Can-Am indica incompatibilidad con Cold Air Roof Scoop, parabrisas completos y SMART Integrated LED Roof Light.'}
]},
{id:'winch',name:'Cabrestantes',icon:'winch',items:[]},
{id:'performance',name:'Rendimiento',icon:'race',items:[]}
];
const $=id=>document.getElementById(id);
const money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:2}).format(n);
const VEHICLE_DISCOUNT=0.40;
const promotionalPrice=m=>Math.round(m.price*(1-VEHICLE_DISCOUNT)*100)/100;
const vehicleSavings=m=>Math.round((m.price-promotionalPrice(m))*100)/100;
function renderModels(){
 const sel=$('modelSelect');
 sel.innerHTML=models.map((m,i)=>`<option value="${i}" ${i===selected?'selected':''}>${m.name} · ${money(promotionalPrice(m))} (−40%)</option>`).join('');
 sel.onchange=()=>{selected=Number(sel.value);colorIndex=0;for(const key of [...selectedAccessories.keys()]){const item=itemById(key);if(!item||!accessoryFits(item,models[selected]))selectedAccessories.delete(key);}activeCategory='roof';if(root)renderAll();};
}
function renderColors(){
 const m=models[selected]; if(colorIndex>=m.colors.length)colorIndex=0;
 $('swatches').innerHTML=m.colors.map((c,i)=>`<button type="button" class="swatch ${i===colorIndex?'active':''}" style="background:linear-gradient(135deg,${c.hex} 0 70%,${c.accent} 70% 100%)" title="${c.name}" aria-label="Color ${c.name}" aria-pressed="${i===colorIndex}" data-color="${i}"></button>`).join('');
 $('colorName').textContent=m.colors[colorIndex]?.name||'Color no especificado';
 $('swatches').querySelectorAll('[data-color]').forEach(b=>b.addEventListener('click',()=>{colorIndex=Number(b.dataset.color);renderColors();renderImage();}));
}
function renderSpecs(){const m=models[selected];const specs=[['susp','Suspensión',m.susp],['tire','Neumáticos',m.tires],['wheel','Rines',m.wheels],['screen','Pantalla y cámaras',m.screen]];const icons={susp:'<path d="M12 2v3M12 19v3M8 5h8M8 19h8"/><path d="M9 5v3l6 3-6 3v5"/>',tire:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 3v5M21 12h-5M12 21v-5M3 12h5"/>',wheel:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><path d="m12 3 0 6m9 3h-6m-3 9v-6m-9-3h6"/>',screen:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4M7 8h10M7 11h6"/>'};$('specs').innerHTML=specs.map(([id,k,v])=>`<div class="spec"><span class="spec-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${icons[id]}</svg></span><b>${k}</b><span>${v}</span></div>`).join('');}
function renderImage(){const m=models[selected],c=m.colors[colorIndex]||m.colors[0];$('vehicleImage').src=c.url;$('vehicleImage').alt=`${m.name} 2027, color ${c.name}`;$('imageStage').className='stage '+(['view-catalog','view-side','view-rear'][angle]||'view-catalog');$('angleLabel').textContent=viewLabels[angle];root.querySelectorAll('[data-angle]').forEach(b=>{b.classList.toggle('active',Number(b.dataset.angle)===angle);b.setAttribute('aria-pressed',String(Number(b.dataset.angle)===angle));});}
const selectedAccessories=new Map();
let activeCategory='roof';
function accessoryFits(item,m){
 if(item.fit==='family')return true;
 if(item.fit==='rc')return m.id==='xrc'||m.id==='maxxrc';
 if(item.fit==='notRc')return !m.id.includes('rc');
 if(item.fit==='r')return !m.id.startsWith('max');
 if(item.fit==='max')return m.id.startsWith('max');
 return false;
}
function itemById(id){for(const cat of accessoryCategories){const found=cat.items.find(x=>x.id===id);if(found)return found;}return null;}
function selectedIds(){return new Set([...selectedAccessories.keys()]);}
function isItemAvailable(item,m){
 if(!accessoryFits(item,m))return false;
 const chosen=selectedIds();
 if(item.requires?.some(id=>!chosen.has(id)))return false;
 if(item.conflicts?.some(id=>chosen.has(id)))return false;
 if([...chosen].some(id=>{const other=itemById(id);return other&&other.conflicts?.includes(item.id)}))return false;
 // El audio de techo no puede combinarse con la toma de aire fría.
 if(item.id==='audio-roof-flip'&&chosen.has('cold-air-scoop'))return false;
 return true;
}
function itemPart(item,m){return item.part||(m.id.startsWith('max')?item.partMax:item.partR)||'—';}
function itemPrice(item,m){return m.id.startsWith('max')&&Number.isFinite(item.priceMax)?item.priceMax:(Number.isFinite(item.price)?item.price:0);}
function categoryHasSelection(cat){return cat.items.some(item=>selectedAccessories.has(item.id));}
function categoryIcon(key){
 const paths={
  roof:'<path d="M3 14l2-5h14l2 5"/><path d="M5 14v4h14v-4"/><path d="M8 9l1.5-3h5L16 9"/><path d="M7 18v2M17 18v2"/>',
  wind:'<path d="M4 5h16l2 13H2L4 5Z"/><path d="M5 8h14M7 12h10"/>',
  mirror:'<path d="M5 4h10a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H5z"/><path d="M10 15l-2 5M8 20h7"/>',
  shield:'<path d="M12 3 20 6v5c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V6l8-3Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/>',
  cargo:'<path d="M3 8 12 3l9 5-9 5-9-5Z"/><path d="M3 8v9l9 5 9-5V8M12 13v9"/>',
  circuit:'<rect x="7" y="7" width="10" height="10" rx="1"/><path d="M9 2v5M15 2v5M9 17v5M15 17v5M2 9h5M2 15h5M17 9h5M17 15h5"/><path d="m10 12 1.5 1.5L14 10"/>',
  light:'<path d="M9 18h6M10 21h4M8 15c-1.3-1-2-2.6-2-4.5a6 6 0 1 1 12 0c0 1.9-.7 3.5-2 4.5-.7.5-1 1.3-1 2H9c0-.7-.3-1.5-1-2Z"/><path d="M12 1v2M3 4l2 2M21 4l-2 2"/>',
  audio:'<path d="M4 10v4h4l5 4V6l-5 4H4Z"/><path d="M17 9a5 5 0 0 1 0 6M19 6a9 9 0 0 1 0 12"/>',
  winch:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 1v3M12 20v3M1 12h3M20 12h3M18 6l3-2M3 20l3-2"/>',
  race:'<path d="M4 21V4M5 5h14l-3 4 3 4H5"/><path d="M8 7h3v3H8zM13 9h3v3h-3z"/>'
 };
 return `<span class="category-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${paths[key]||paths.race}</svg></span>`;
}
function renderAccessoryCatalog(){
 const m=models[selected];let count=0;
 $('accessoryCatalog').innerHTML=accessoryCategories.map(cat=>{
   const items=cat.items.filter(it=>isItemAvailable(it,m));
   count+=items.length;
   const selectedInCat=items.filter(it=>selectedAccessories.has(it.id)).length;
   const body=items.length?items.map(it=>{
     const checked=selectedAccessories.has(it.id);
     const part=itemPart(it,m);
     const productUrl=(m.id.startsWith('max')&&it.urlMax)?it.urlMax:(it.url||'https://can-am-shop.brp.com/off-road/us/en/maverick-r/accessories.html');
     const price=itemPrice(it,m);
     return `<label class="accessory-item ${checked?'selected':''}"><input type="checkbox" data-accessory-key="${it.id}" data-price="${price}" ${checked?'checked':''}><span class="item-copy"><strong>${it.name}</strong><small>${it.note}</small><span class="item-tag">Ref. ${part} · <a href="${productUrl}" target="_blank" rel="noopener">Ver precio oficial</a></span></span><b>${money(price)}</b></label>`;
   }).join(''):'<div class="empty-accessories">No hay referencias listadas en esta categoría para mostrar como opción confirmada en el catálogo consultado.</div>';
   const isOpen=activeCategory===cat.id;
   const right=`<span class="category-status">${items.length} opciones${selectedInCat?' · '+selectedInCat+' activas':''}</span>${categoryIcon(cat.icon)}`;
   return `<section class="accessory-category"><button type="button" class="category-head" aria-expanded="${isOpen}"><span>${cat.name}</span>${right}</button><div class="category-items" ${isOpen?'':'hidden'}>${body}</div></section>`;
 }).join('');
 $('accessoryCount').textContent=`${count} referencias de accesorios listadas · ${m.name}`;
 $('accessoryCatalog').querySelectorAll('input[data-accessory-key]').forEach(input=>input.addEventListener('change',()=>{
   const key=input.dataset.accessoryKey,item=itemById(key);
   if(input.checked){
     for(const conflict of (item?.conflicts||[]))selectedAccessories.delete(conflict);
     if(key==='audio-roof-flip')selectedAccessories.delete('cold-air-scoop');
     selectedAccessories.set(key,{price:item?itemPrice(item,models[selected]):0,name:item?.name||key});
   } else selectedAccessories.delete(key);
   let changed=true;while(changed){changed=false;for(const id of [...selectedAccessories.keys()]){const chosen=selectedIds(),it=itemById(id);if(!it||it.requires?.some(req=>!chosen.has(req))||it.conflicts?.some(conf=>chosen.has(conf))||[...chosen].some(otherId=>{const other=itemById(otherId);return otherId!==id&&other?.conflicts?.includes(id)})){selectedAccessories.delete(id);changed=true;}}}
   renderAccessoryCatalog();updateTotal();
 }));
 $('accessoryCatalog').querySelectorAll('.category-head').forEach(btn=>btn.addEventListener('click',()=>{
   const cat=accessoryCategories.find(c=>btn.querySelector(':scope > span')?.textContent===c.name);
   if(!cat)return;
   activeCategory=activeCategory===cat.id?null:cat.id;
   renderAccessoryCatalog();
 }));
}
function updateTotal(){const m=models[selected];const accessoryTotal=[...selectedAccessories.keys()].reduce((sum,key)=>{const item=itemById(key);return sum+(item?itemPrice(item,m):0)},0);const promo=promotionalPrice(m);const total=promo+accessoryTotal;$('baseOriginal').textContent=money(m.price);$('base').textContent=money(promo);$('savings').textContent=money(vehicleSavings(m));$('accessoryPrice').textContent=selectedAccessories.size?money(accessoryTotal):money(0);$('total').textContent=money(total);$('stagePromoPrice').textContent=money(promo);$('stageOriginalPrice').textContent=money(m.price);$('stageSavings').textContent=`Ahorras ${money(vehicleSavings(m))}`;$('mobileTotal').textContent=money(total)}
function renderAll(){let m=models[selected];$('visualModel').textContent=m.name;$('subTitle').textContent=`2027 · ${m.seats} · ${m.terrain}`;renderModels();renderColors();renderSpecs();renderImage();renderAccessoryCatalog();updateTotal()}
root.addEventListener('click',function(e){const b=e.target.closest('button[data-angle]');if(!b)return;e.preventDefault();e.stopPropagation();const next=Number(b.getAttribute('data-angle'));if(!Number.isInteger(next)||next<0||next>2)return;angle=next;renderImage();});$('previewBtn').onclick=async()=>{const m=models[selected],color=m.colors[colorIndex]||m.colors[0];const accessoryTotal=[...selectedAccessories.keys()].reduce((sum,key)=>{const item=itemById(key);return sum+(item?itemPrice(item,m):0)},0);const price=promotionalPrice(m)+accessoryTotal;const accessories=[...selectedAccessories.values()].map(x=>x.name);const title=`${m.name} 2027 · ${color.name}${accessories.length?' · Mejoras: '+accessories.join(', '):''}`;const btn=$('previewBtn');btn.disabled=true;btn.textContent='AGREGANDO AL CARRITO…';try{if(typeof window.proEshopAddCanAmToCart!=='function')throw new Error('No se pudo conectar con el carrito de ProEshop. Recarga la página e inténtalo otra vez.');await window.proEshopAddCanAmToCart({title,price,image:color.url,url:'https://can-am.brp.com/off-road/us/es/personaliza-el-tuyo/vehiculos-side-by-side/maverick-r.html',model:m.name,color:color.name,accessories,regularPrice:m.price,vehiclePrice:promotionalPrice(m)});btn.textContent='AÑADIDO AL CARRITO ✓';}catch(e){alert(e.message||'No se pudo agregar la configuración.');btn.disabled=false;btn.textContent='CONTINUAR CON MI CONFIGURACIÓN →';}};$('mobileContinue').addEventListener('click',()=> $('previewBtn').click());
renderAll();

})();
