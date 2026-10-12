'use strict';
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); try { tg.setHeaderColor('#075fc7'); tg.setBackgroundColor('#f4f7fc'); } catch (_) {} }
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('shopcart_token') || '';
let selectedStore = 'walmart';
let state = {balance:'1000.00',currency:'USD',cart:[],history:[],orders:[],tax_rate:'0.08',shipping_fee:'5.99'};
let lastSearch = [], lastSearchResponse = null, currentResults = [], favorites = new Set(), compareItems = new Map(), searchBusy = false, adminKey = ''; 
const money = (v,c='USD') => `${c} ${Number(v||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const escapeHtml = s => String(s??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const storeLabel = s => ({amazon:'Amazon',walmart:'Walmart',target:'Target',hublot:'HUBLOT',jewelers:'Jewelers Toy Store',rolex:'Rolex'}[String(s||'').toLowerCase()]||'Tienda');
function toast(msg){ const el=$('toast'); if(!el)return; el.textContent=msg;el.classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.add('hidden'),3000); }
async function api(path,opts={}){const headers={'Content-Type':'application/json',...(token?{'Authorization':`Bearer ${token}`}:{})};const r=await fetch(path,{...opts,headers:{...headers,...opts.headers}});const data=await r.json().catch(()=>({detail:'Respuesta inválida del servidor.'}));if(!r.ok){if(r.status===401&&token){token='';sessionStorage.removeItem('shopcart_token');setLoggedIn(false)}throw new Error(data.detail||data.error||'Ocurrió un error. Intenta nuevamente.')}return data;}
function showView(view){if(view==='search'){showView('home');setTimeout(()=>$('query')?.focus(),100);return;}const ids={home:'shopView',cart:'cartView',checkout:'checkoutView',history:'historyView',account:'accountView'};document.querySelectorAll('main .view').forEach(v=>v.classList.add('hidden'));const target=$(ids[view]||`${view}View`);if(!target){console.error('Vista no encontrada:',view);return;}target.classList.remove('hidden');document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.tab===(view==='checkout'?'cart':view)));window.scrollTo({top:0,behavior:'smooth'});}
function setLoggedIn(on){$('loginView').classList.toggle('hidden',on);$('shopView').classList.toggle('hidden',!on);$('bottomNav').classList.toggle('hidden',!on);$('logoutBtn').classList.toggle('hidden',!on);if(on)showView('home');}
async function refresh(){state=await api('/api/state');$('balanceValue').textContent=money(state.balance,state.currency);$('accountBalance').textContent=money(state.balance,state.currency);$('cartCount').textContent=`${state.cart.length} artículo${state.cart.length===1?'':'s'}`;$('historyCount').textContent=`${(state.orders||[]).length} pedido${(state.orders||[]).length===1?'':'s'}`;$('orderCountLabel').textContent=`${(state.orders||[]).length} pedido${(state.orders||[]).length===1?'':'s'}`;$('navCartCount').textContent=state.cart.length;$('navCartCount').classList.toggle('hidden',!state.cart.length);$('greetingName').textContent=$('username').value.trim()||'bienvenido';$('accountName').textContent=$('username').value.trim()||'Sesión activa';renderCart();renderHistory();}
function estimateCart(){const subtotal=state.cart.reduce((sum,x)=>sum+Number(x.price)*Number(x.qty||1),0);const tax=subtotal*Number(state.tax_rate||0);const shipping=subtotal>0?Number(state.shipping_fee||0):0;return {subtotal,tax,shipping,total:subtotal+tax+shipping};}
function storeIcon(s){return s==='walmart'?'✳':s==='amazon'?'a':s==='target'?'◎':s==='hublot'?'H':s==='rolex'?'R':s==='jewelers'?'J':'▧';}
function renderCart(){const wrap=$('cartItems');wrap.innerHTML='';$('cartEmpty').classList.toggle('hidden',!!state.cart.length);$('cartSummary').classList.toggle('hidden',!state.cart.length);state.cart.forEach(x=>{const el=document.createElement('article');el.className='item-card';el.innerHTML=`<div class="item-icon">${storeIcon(x.platform)}</div><div class="item-info"><h3>${escapeHtml(x.title)}</h3><p>${escapeHtml(storeLabel(x.platform))} · ${Number(x.qty||1)} unidad(es)</p><div class="item-price">${['hublot','jewelers'].includes(String(x.platform).toLowerCase())?`<del>${money(Number(x.price)*2*Number(x.qty||1),x.currency)}</del> <strong>${money(Number(x.price)*Number(x.qty||1),x.currency)}</strong><small class="discount-note">50% descuento ProEshop</small>`:String(x.platform).toLowerCase()==='rolex'&&['datejust-41','explorer-ii','sea-dweller'].some(id=>String(x.title).toLowerCase().includes(id.replaceAll('-',' ')))?`<del>${money(Number(x.price)/0.6*Number(x.qty||1),x.currency)}</del> <strong>${money(Number(x.price)*Number(x.qty||1),x.currency)}</strong><small class="discount-note">40% oferta ProEshop · no oficial de Rolex</small>`:money(Number(x.price)*Number(x.qty||1),x.currency)}</div><div class="item-actions"><button class="qty-btn" data-qty="${Number(x.id)}" data-next="${Math.max(1,Number(x.qty||1)-1)}" aria-label="Disminuir cantidad">−</button><span class="qty-value">${Number(x.qty||1)}</span><button class="qty-btn" data-qty="${Number(x.id)}" data-next="${Math.min(25,Number(x.qty||1)+1)}" aria-label="Aumentar cantidad">＋</button><a class="external" href="${escapeHtml(x.url)}" target="_blank" rel="noopener noreferrer">Ver tienda ↗</a><button class="text-btn" data-remove="${Number(x.id)}">Quitar</button></div></div>`;wrap.appendChild(el)});const t=estimateCart();$('cartSubtotal').textContent=money(t.subtotal);$('cartTax').textContent=money(t.tax);$('cartShipping').textContent=money(t.shipping);$('cartTotal').textContent=money(t.total);$('cartSubtitle').textContent=`${state.cart.length} artículo(s) · ${money(t.total)} estimado`;wrap.querySelectorAll('[data-remove]').forEach(b=>b.onclick=async()=>{try{await api('/api/cart/'+b.dataset.remove,{method:'DELETE'});await refresh();toast('Artículo retirado del carrito.')}catch(e){toast(e.message)}});wrap.querySelectorAll('[data-qty]').forEach(b=>b.onclick=async()=>{try{await api('/api/cart/'+b.dataset.qty,{method:'PUT',body:JSON.stringify({qty:Number(b.dataset.next)})});await refresh();}catch(e){toast(e.message)}});}
function formatDate(value){try{return new Date(value).toLocaleString('es-CO',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}catch{return String(value||'Fecha no disponible')}}
function renderHistory(){const wrap=$('historyItems');wrap.innerHTML='';const orders=state.orders||[];$('historyEmpty').classList.toggle('hidden',!!orders.length);orders.forEach(order=>{const lines=(state.history||[]).filter(x=>x.order_ref===order.order_ref);const el=document.createElement('article');el.className='order-card';const orderStatus=String(order.status||'confirmed_simulated');const labels={received:'Pedido recibido',reviewing:'En revisión',action_required:'Requiere acción',confirmed:'Pedido confirmado',preparing:'En preparación',shipped:'Enviado',delivered:'Entregado',unavailable:'No disponible',cancelled:'Cancelado',returned:'Devuelto',confirmed_simulated:'Confirmado · Simulado'};const statusLabel=escapeHtml(labels[orderStatus]||orderStatus.replaceAll('_',' '));const events=(state.order_events||[]).filter(ev=>ev.order_ref===order.order_ref).sort((a,b)=>String(a.created_at).localeCompare(String(b.created_at)));const stages=events.length?events.map((ev,i)=>[i+1,ev.label,ev]):[['1','Pedido recibido',null]];el.innerHTML=`<div class="order-top"><div><small>REFERENCIA DEL PEDIDO</small><strong>${escapeHtml(order.order_ref)}</strong></div><span class="status-pill">${statusLabel}</span></div><div class="order-meta"><span>${escapeHtml(formatDate(order.created_at))}</span><strong>${money(order.total,order.currency)}</strong></div><button class="secondary small-button receipt-btn" data-receipt="${escapeHtml(order.order_ref)}">Ver recibo de prueba ↗</button><div class="order-breakdown"><span>Subtotal ${money(order.subtotal,order.currency)}</span><span>Impuestos ${money(order.tax,order.currency)}</span><span>Envío ${money(order.shipping,order.currency)}</span></div><div class="tracking-heading"><b>Historial de estados</b><span>ACTUALIZADO</span></div><div class="tracking-steps">${stages.map((s,i)=>`<div class="step active"><i>${s[0]}</i><span>${escapeHtml(s[1])}</span></div>`).join('')}</div><p class="tracking-caption">Estado actual: <b>${statusLabel}</b>. Los estados de envío y entrega solo deben registrarse cuando estén respaldados por confirmaciones reales.</p><div class="tracking-ref">Guía de transporte: <b>No disponible — sin envío real</b></div><details class="order-details"><summary>Ver artículos y datos del pedido (${lines.length})</summary>${lines.map(x=>`<div class="order-line"><span>${escapeHtml(x.title)} · ${escapeHtml(storeLabel(x.platform))} × ${Number(x.qty||1)}</span><strong>${money(x.total,x.currency)}</strong></div>`).join('')||'<p>Detalle no disponible para pedidos anteriores a esta versión.</p>'}${order.shipping_city?`<div class="order-line"><span>Destino de prueba</span><strong>${escapeHtml(order.shipping_city)}${order.shipping_country?`, ${escapeHtml(order.shipping_country)}`:''}</strong></div>`:''}<div class="order-line"><span>Método</span><strong>Saldo ficticio</strong></div>${(state.order_events||[]).filter(ev=>ev.order_ref===order.order_ref).map(ev=>`<div class="order-line"><span>${escapeHtml(ev.label)}<br><small>${escapeHtml(ev.detail)}</small></span><strong>${escapeHtml(formatDate(ev.created_at))}</strong></div>`).join('')}</details>`;wrap.appendChild(el)});wrap.querySelectorAll('[data-receipt]').forEach(b=>b.onclick=()=>openReceipt(b.dataset.receipt));}
function officialStoreUrl(platform,query){const q=encodeURIComponent(String(query||'producto').trim()||'producto');return {amazon:`https://www.amazon.com/s?k=${q}`,walmart:`https://www.walmart.com/search?q=${q}`,target:`https://www.target.com/s?searchTerm=${q}`,hublot:`https://www.hublot.com/en-us/watches`,jewelers:`https://www.jewelerstoystore.com/Electronic-s/1074.htm`,rolex:`https://www.rolex.com/es/watches/find-rolex?group=0`}[String(platform||'').toLowerCase()]||'https://www.walmart.com/';}
function normalizeStoreUrl(rawUrl,platform,title){const hosts={amazon:['amazon.com','www.amazon.com'],walmart:['walmart.com','www.walmart.com'],target:['target.com','www.target.com'],hublot:['hublot.com','www.hublot.com'],jewelers:['jewelerstoystore.com','www.jewelerstoystore.com'],rolex:['rolex.com','www.rolex.com']};try{const u=new URL(String(rawUrl||''));if(u.protocol==='https:'&&(hosts[String(platform||'').toLowerCase()]||[]).includes(u.hostname.toLowerCase()))return u.href;}catch(_){}return officialStoreUrl(platform,title);}
function productCards(items,r){return items.map((x,i)=>{const isHublot=String(r.platform).toLowerCase()==='hublot';const isJewelers=String(r.platform).toLowerCase()==='jewelers';const isRolex=String(r.platform).toLowerCase()==='rolex';const hasDiscount=isHublot||isJewelers||(isRolex&&Number(x.discount_percent||0)===40);return `<article class="product-result"><div class="product-media"><button class="favorite-btn ${favorites.has(x.title+'|'+x.url)?'active':''}" data-fav="${i}" aria-label="Guardar favorito">${favorites.has(x.title+'|'+x.url)?'♥':'♡'}</button>${x.image?`<img class="product-thumb" src="${escapeHtml(x.image)}" alt="Imagen ilustrativa de reloj" loading="lazy" referrerpolicy="no-referrer"><div class="product-placeholder hidden">▧</div>`:`<div class="product-placeholder">▧</div>`}</div><div class="product-result-info"><div class="product-store">${escapeHtml(storeLabel(r.platform))} · ${escapeHtml(x.source||'Catálogo ProEshop')}</div><strong>${escapeHtml(x.title)}</strong><div class="product-price">${hasDiscount?`<del>${money(Number(x.list_price??(isRolex?Number(x.price)/0.6:Number(x.price)*2)),'USD')}</del> <strong>${money(x.price,'USD')}</strong>`:money(x.price,'USD')}</div><small>${isHublot?'50% de descuento ilustrativo · no es una oferta oficial de HUBLOT':isJewelers?'50% de descuento ProEshop sobre el precio publicado; disponibilidad por confirmar.':isRolex?(Number(x.discount_percent||0)===40?'40% de descuento propuesto por ProEshop; no es una oferta oficial de Rolex.':'Precio de referencia Rolex; confirma precio y disponibilidad.'):'Precio consultado · confirma el importe final en la tienda.'}</small><div class="product-actions"><button class="external details-btn" data-details="${i}" type="button">Detalles ↗</button><button class="secondary compare-btn ${compareItems.has(x.title+'|'+x.url)?'active':''}" data-compare="${i}" type="button">⇄ Comparar</button><button class="primary add-result" data-add="${i}" type="button">${hasDiscount?'＋ Agregar · '+(isRolex?'40% OFF':'50% OFF'):'＋ Agregar'}</button></div></div></article>`}).join('');}
function renderResults(r){const result=$('searchResult');if(!result||!r)return;let items=[...lastSearch];const min=Number($('minPrice')?.value||0),maxVal=$('maxPrice')?.value; if(min>0)items=items.filter(x=>Number(x.price)>=min);if(maxVal!==''&&maxVal!=null)items=items.filter(x=>Number(x.price)<=Number(maxVal));const sort=$('sortResults')?.value||'relevance';if(sort==='low')items.sort((a,b)=>a.price-b.price);if(sort==='high')items.sort((a,b)=>b.price-a.price);currentResults=items;const grid=result.querySelector('.product-results');if(!grid)return;grid.innerHTML=productCards(items,r)||`<div class="empty"><div>⌕</div><strong>No hay resultados con estos filtros</strong><p>Prueba con otro rango de precio o cambia la búsqueda.</p></div>`;grid.querySelectorAll('img.product-thumb').forEach(img=>img.addEventListener('error',()=>{img.style.display='none';img.nextElementSibling?.classList.remove('hidden')}));grid.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>{const item=items[Number(b.dataset.add)];if(item)addItem(item,r.platform)});grid.querySelectorAll('[data-details]').forEach(b=>b.onclick=()=>openProduct(items[Number(b.dataset.details)],r));grid.querySelectorAll('[data-compare]').forEach(b=>b.onclick=()=>{const item=items[Number(b.dataset.compare)];if(!item)return;const key=item.title+'|'+item.url;if(compareItems.has(key)){compareItems.delete(key);toast('Artículo retirado del comparador.')}else if(compareItems.size>=3){toast('Compara hasta 3 artículos a la vez.');return}else{compareItems.set(key,{...item,platform:r.platform});toast('Artículo añadido al comparador.')}renderCompare();b.classList.toggle('active',compareItems.has(key));});grid.querySelectorAll('[data-fav]').forEach(b=>b.onclick=()=>{const item=items[Number(b.dataset.fav)];if(!item)return;const key=item.title+'|'+item.url;favorites.has(key)?favorites.delete(key):favorites.add(key);b.classList.toggle('active',favorites.has(key));b.textContent=favorites.has(key)?'♥':'♡';});const count=result.querySelector('#resultCount');if(count)count.textContent=`${items.length} resultado${items.length===1?'':'s'}`;}
function openProduct(item,r){if(!item)return;const d=$('productDialogContent');d.innerHTML=`<div class="product-dialog-media">${item.image?`<img src="${escapeHtml(item.image)}" alt="Producto">`:'<span style="font-size:42px;color:#86a0bf">▧</span>'}</div><div class="eyebrow dark-eyebrow">${escapeHtml(storeLabel(r.platform))} · DETALLE</div><h2>${escapeHtml(item.title)}</h2><div class="dialog-price">${money(item.price,'USD')}</div><p class="dialog-note">Vendedor mostrado por el proveedor: ${escapeHtml(item.source||'No identificado')}. No se inventan valoraciones, descuentos ni disponibilidad. Confirma todos los detalles en la tienda oficial.</p><div class="dialog-actions"><a class="external" href="${escapeHtml(normalizeStoreUrl(item.url,r.platform,item.title))}" target="_blank" rel="noopener noreferrer">Ver en tienda ↗</a><button id="dialogAdd" class="primary">Agregar al carrito</button></div>`;$('productDialog').showModal();d.querySelector('img')?.addEventListener('error',e=>{e.currentTarget.style.display='none'});$('dialogAdd').onclick=async()=>{await addItem(item,r.platform);$('productDialog').close()};}
async function addItem(item,platform=selectedStore){try{const p=String(platform||selectedStore).toLowerCase();const url=normalizeStoreUrl(item.url,p,item.title);await api('/api/cart',{method:'POST',body:JSON.stringify({platform:p,title:String(item.title||'Producto').slice(0,180),price:String(p==='rolex'&&Number(item.discount_percent||0)===40?Number(item.list_price):['hublot','jewelers'].includes(p)?Number(item.price)*2:item.price),currency:'USD',url})});await refresh();toast('Artículo agregado al carrito');}catch(e){toast(e.message||'No se pudo agregar el artículo');}}
async function performSearch(queryOverride, platformOverride){if(platformOverride){selectedStore=String(platformOverride).toLowerCase();document.querySelectorAll('.store').forEach(x=>x.classList.toggle('active',x.dataset.store===selectedStore));}const platform=selectedStore;const query=String(queryOverride??$('query').value).trim();if(!query)return toast(platform==='hublot'?'Escribe el nombre o la colección del reloj.':'Escribe qué artículo buscas.');if(searchBusy)return;searchBusy=true;$('query').value=query;$('clearSearch').classList.remove('hidden');$('homeEmpty').classList.add('hidden');const btn=$('searchBtn');btn.disabled=true;btn.textContent='Buscando…';document.querySelectorAll('[data-search-store]').forEach(b=>{b.disabled=true;if(b.dataset.searchStore===platform)b.dataset.originalLabel=b.innerHTML,b.innerHTML='Buscando…';});$('searchResult').classList.remove('hidden');$('searchResult').innerHTML='<div class="home-empty"><div class="empty-orbit">⌕</div><strong>Buscando productos…</strong><p>Consultando resultados para '+escapeHtml(storeLabel(platform))+'.</p></div>';try{let r;if(platform==='jewelers'){const q=query.toLocaleLowerCase();const catalog=[{name:'Niton XL2 100p, Niton Gold XRF Analyzer XL2100',price:20500,desc:'Analizador XRF para metales preciosos.'},{name:'Niton DXL Precious Metal Analyzer',price:21750,desc:'Analizador de metales preciosos.'},{name:'Niton XL2 Battery: 7.4V 7800mAh Li-ion (NTL200SL)',price:295,desc:'Batería de repuesto para analizador XRF Niton XL2.'},{name:'Niton XL2 Battery Charger – Fast, Smart & Reliable Charging for Your XRF Analyzer',price:395,desc:'Cargador para analizador XRF Niton XL2.'}];const allTerms=['electronics','electronic','todos','todo','all','*','jewelers','jewelers toy store'];const matches=catalog.filter(x=>allTerms.includes(q)||[x.name,x.desc].some(v=>v.toLocaleLowerCase().includes(q)));const selected=matches.length?matches:catalog;const products=selected.map(x=>({title:x.name,price:x.price/2,image:'',url:'https://www.jewelerstoystore.com/Electronic-s/1074.htm',source:'Jewelers Toy Store · precio publicado',description:x.desc}));r={platform:'jewelers',label:'Jewelers Toy Store',notice:'Catálogo de la categoría Electronic. Precio base consultado del proveedor con descuento ProEshop del 50%; precio y disponibilidad deben confirmarse antes de vender.',search_url:'https://www.jewelerstoystore.com/Electronic-s/1074.htm',live_results:products};}else if(platform==='hublot'){const q=query.toLocaleLowerCase();const allHublotTerms=['hublot','watch','watches','reloj','relojes','todos','all'];const catalog=HUBLOT_PRODUCTS.filter(x=>allHublotTerms.includes(q)||[x.name,x.collection,x.desc].some(v=>String(v||'').toLocaleLowerCase().includes(q))).map(x=>({title:x.name,price:Number(x.price)/2,image:x.img,url:'https://www.hublot.com/en-us/watches',source:'Catálogo HUBLOT · modelo ilustrativo',collection:x.collection,description:x.desc}));r={platform:'hublot',label:'HUBLOT',notice:'Resultados del catálogo local de ProEshop. Los modelos, imágenes y precios son ilustrativos; el descuento del 50% es simulado y no es una oferta oficial.',search_url:'https://www.hublot.com/en-us/watches',live_results:catalog};}else if(platform==='rolex'){const q=query.toLocaleLowerCase();const catalog=[{id:'land-dweller-40',name:'Rolex Land-Dweller 40 · acero y oro blanco',price:16450,discount:0,desc:'Land-Dweller 40, esfera blanco intenso con motivo nido de abeja.',img:'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=1000&q=90'},{id:'datejust-41',name:'Rolex Datejust 41 · acero y oro blanco, esfera verde',price:11650,discount:40,desc:'Datejust 41, esfera verde sombreado.',img:'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1000&q=90'},{id:'datejust-41-steel',name:'Rolex Datejust 41 · acero Oystersteel',price:8950,discount:0,desc:'Datejust 41, versión Oystersteel.',img:'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=1000&q=90'},{id:'datejust-36',name:'Rolex Datejust 36 · acero y oro blanco',price:10400,discount:0,desc:'Datejust 36, diseño clásico.',img:'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=1000&q=90'},{id:'lady-datejust',name:'Rolex Lady-Datejust · 28 mm',price:15100,discount:0,desc:'Lady-Datejust, acero y oro amarillo.',img:'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=1000&q=90'},{id:'oyster-perpetual-41',name:'Rolex Oyster Perpetual 41 · acero y oro amarillo',price:9650,discount:40,desc:'Oyster Perpetual 41, esfera pizarra.',img:'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=1000&q=90'},{id:'cosmograph-daytona',name:'Rolex Cosmograph Daytona · platino',price:84600,discount:0,desc:'Cosmograph Daytona, esfera azul glaciar.',img:'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=1000&q=90'},{id:'submariner-date',name:'Rolex Submariner Date · acero Oystersteel',price:11900,discount:0,desc:'Submariner Date, esfera negra.',img:'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=1000&q=90'},{id:'submariner-date-gold',name:'Rolex Submariner Date · acero y oro amarillo',price:17200,discount:0,desc:'Submariner Date, esfera azul.',img:'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=1000&q=90'},{id:'gmt-master-ii',name:'Rolex GMT-Master II · Oystersteel',price:12500,discount:0,desc:'GMT-Master II, reloj de doble huso horario.',img:'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=1000&q=90'},{id:'explorer-40',name:'Rolex Explorer 40 · acero Oystersteel',price:8350,discount:40,desc:'Explorer 40, esfera negra.',img:'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1000&q=90'},{id:'explorer-ii',name:'Rolex Explorer II · 42 mm',price:10600,discount:40,desc:'Explorer II, esfera blanca.',img:'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=1000&q=90'},{id:'air-king',name:'Rolex Air-King · 40 mm',price:8150,discount:0,desc:'Air-King, esfera negra.',img:'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=1000&q=90'},{id:'sea-dweller',name:'Rolex Sea-Dweller · 43 mm',price:22450,discount:40,desc:'Sea-Dweller, reloj de submarinismo.',img:'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1000&q=90'},{id:'deepsea',name:'Rolex Deepsea · 44 mm',price:15880,discount:0,desc:'Deepsea, esfera D-blue.',img:'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=1000&q=90'},{id:'sky-dweller',name:'Rolex Sky-Dweller · oro Everose',price:64900,discount:0,desc:'Sky-Dweller, esfera pizarra.',img:'https://images.unsplash.com/photo-1612817159949-195b6eb9e31a?auto=format&fit=crop&w=1000&q=90'},{id:'yacht-master-42',name:'Rolex Yacht-Master 42 · oro amarillo',price:38100,discount:0,desc:'Yacht-Master 42, esfera negra.',img:'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=1000&q=90'},{id:'yacht-master-40',name:'Rolex Yacht-Master 40 · acero y platino',price:13200,discount:0,desc:'Yacht-Master 40, bisel de platino.',img:'https://images.unsplash.com/photo-1434056886845-dac89ffe9b56?auto=format&fit=crop&w=1000&q=90'},{id:'yacht-master-ii',name:'Rolex Yacht-Master II · 44 mm',price:20300,discount:0,desc:'Yacht-Master II, esfera blanca.',img:'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=1000&q=90'},{id:'day-date-40',name:'Rolex Day-Date 40 · platino',price:68800,discount:0,desc:'Day-Date 40, esfera azul glaciar.',img:'https://images.unsplash.com/photo-1614164185128-e4ec99c436d7?auto=format&fit=crop&w=1000&q=90'},{id:'day-date-36',name:'Rolex Day-Date 36 · platino',price:59000,discount:0,desc:'Day-Date 36, acabados clásicos.',img:'https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&w=1000&q=90'},{id:'1908',name:'Rolex 1908 · oro amarillo, 39 mm',price:27000,discount:0,desc:'1908, esfera blanco intenso.',img:'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=1000&q=90'}];const allTerms=['rolex','reloj','relojes','watch','watches','todos','todo','all','destacados','*'];const matches=catalog.filter(x=>allTerms.includes(q)||[x.name,x.desc,x.id].some(v=>String(v).toLowerCase().includes(q)));const chosen=matches.length?matches:catalog;const products=chosen.map(x=>({title:x.name,price:x.price*(1-x.discount/100),list_price:x.price,discount_percent:x.discount,image:x.img,url:'https://www.rolex.com/es/watches/find-rolex?group=0',source:'Rolex.com · precio de referencia; oferta ProEshop no oficial',description:x.desc}));r={platform:'rolex',label:'Rolex · catálogo ampliado',notice:'Catálogo de modelos destacados, no ranking de ventas. Algunos precios son referencias y deben confirmarse; imágenes ilustrativas de relojes, no fotografías oficiales verificadas de cada referencia. Los descuentos del 40% son ofertas propuestas por ProEshop y no promociones oficiales de Rolex.',search_url:'https://www.rolex.com/es/watches/find-rolex?group=0',live_results:products};}else{r=await api('/api/search',{method:'POST',body:JSON.stringify({platform,query})});}lastSearch=r.live_results||[];lastSearchResponse=r;$('searchResult').innerHTML=`<div class="results-heading"><div><h3>${escapeHtml(r.label)} · Resultados</h3><p id="resultCount">${lastSearch.length} resultados para “${escapeHtml(query)}”</p></div><span class="live-dot">PRECIOS USD</span></div><p>${escapeHtml(r.notice||'Los precios pueden variar; confirma el total en la tienda.')}</p><div class="filter-row"><label>Precio mínimo<input id="minPrice" type="number" min="0" step="1" placeholder="USD 0"></label><label>Precio máximo<input id="maxPrice" type="number" min="0" step="1" placeholder="Sin límite"></label><label>Ordenar por<select id="sortResults"><option value="relevance">Relevancia</option><option value="low">Menor precio</option><option value="high">Mayor precio</option></select></label></div><div class="filter-extra"><label><input id="showImages" type="checkbox" checked> Mostrar imágenes</label><span class="view-toggle"><button type="button" class="active" data-layout="grid">▦</button><button type="button" data-layout="list">☰</button></span></div><a class="external" href="${escapeHtml(r.search_url)}" target="_blank" rel="noopener noreferrer">Abrir tienda oficial ↗</a><div id="comparePanel" class="compare-panel hidden"></div><div class="product-results"></div>${['hublot','jewelers'].includes(platform)?'<p class="hint">El descuento del 50% lo establece ProEshop. Confirma precio base, disponibilidad y condiciones con el proveedor; no es una promoción anunciada por la tienda externa.</p>':platform==='rolex'?'<p class="hint">El 40% solo aplica a modelos seleccionados y es una oferta propuesta por ProEshop, no una promoción oficial de Rolex. Precios e imágenes de referencia; no se debe aceptar una venta real sin confirmar procedencia, autenticidad, proveedor y disponibilidad.</p>':'<details class="manual-details"><summary>＋ Agregar artículo manualmente</summary><form id="manualAdd" class="manual-form"><label>Nombre del artículo<input name="title" required maxlength="180" placeholder="Nombre como aparece en la tienda"></label><label>Precio en USD<input name="price" required type="number" min="0.01" max="10000000" step="0.01" placeholder="Ej. 49.99"></label><label>Enlace del producto<input name="url" type="url" required placeholder="https://www.walmart.com/…"></label><button class="primary full" type="submit">Agregar al carrito demo</button></form></details>'}`;const redraw=()=>renderResults(r);['minPrice','maxPrice','sortResults'].forEach(id=>$(id).addEventListener(id==='sortResults'?'change':'input',redraw));$('showImages').onchange=e=>document.querySelectorAll('.product-thumb').forEach(img=>img.classList.toggle('hidden',!e.target.checked));document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-layout]').forEach(x=>x.classList.toggle('active',x===b));$('searchResult').querySelector('.product-results')?.classList.toggle('list-layout',b.dataset.layout==='list')});if($('manualAdd'))$('manualAdd').onsubmit=async ev=>{ev.preventDefault();const f=new FormData(ev.currentTarget);await addItem({title:f.get('title'),price:f.get('price'),url:f.get('url')},selectedStore)};renderResults(r);renderCompare();$('searchResult').scrollIntoView({behavior:'smooth',block:'start'});}catch(e){$('searchResult').innerHTML=`<div class="empty"><div>⚠</div><strong>No se pudo completar la búsqueda</strong><p>${escapeHtml(e.message)}</p><button class="secondary" id="retrySearch">Intentar de nuevo</button></div>`;$('retrySearch').onclick=()=>performSearch(query,platform);}finally{searchBusy=false;btn.disabled=false;btn.textContent='Buscar';document.querySelectorAll('[data-search-store]').forEach(b=>{b.disabled=false;if(b.dataset.originalLabel){b.innerHTML=b.dataset.originalLabel;delete b.dataset.originalLabel;}});}}
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
let adminOrderRows=[];let adminStatusLabels={};
function adminHeaders(){return {'X-Admin-Key':adminKey,'Content-Type':'application/json'};}
function adminStatusOptions(current){return Object.entries(adminStatusLabels).map(([value,label])=>`<option value="${escapeHtml(value)}" ${value===current?'selected':''}>${escapeHtml(label)}</option>`).join('');}
function renderAdminOrders(){const host=$('adminOrders');if(!host)return;const filter=$('adminStatusFilter')?.value||'';const query=($('adminOrderSearch')?.value||'').trim().toLowerCase();const rows=adminOrderRows.filter(o=>(!filter||o.status===filter)&&(!query||String(o.order_ref||'').toLowerCase().includes(query)||String(o.customer_email||'').toLowerCase().includes(query)||String(o.telegram_id||'').toLowerCase().includes(query)));if(!rows.length){host.innerHTML='<div class="admin-empty">No hay pedidos que coincidan con el filtro.</div>';return;}host.innerHTML=rows.map(o=>{const statusLabel=adminStatusLabels[o.status]||o.status;return `<article class="admin-order-card" data-order-ref="${escapeHtml(o.order_ref)}"><div class="admin-order-top"><div><span class="admin-order-ref">${escapeHtml(o.order_ref)}</span><span class="admin-order-date">${escapeHtml(o.created_at||'')}</span></div><strong>${escapeHtml(money(o.total,o.currency))}</strong></div><div class="admin-order-meta"><span class="admin-status-pill status-${escapeHtml(o.status)}">${escapeHtml(statusLabel)}</span><span>${escapeHtml(o.customer_email||'Sin correo registrado')}</span></div><div class="admin-order-controls"><label>Nuevo estado<select class="admin-new-status">${adminStatusOptions(o.status)}</select></label><label>Detalle del cambio<textarea class="admin-status-detail" maxlength="500" rows="2" placeholder="Motivo, guía de envío o nota para el historial"></textarea></label><div class="admin-order-actions"><button type="button" class="primary admin-save-status" data-ref="${escapeHtml(o.order_ref)}">Guardar estado y notificar</button><button type="button" class="secondary admin-retry-email" data-ref="${escapeHtml(o.order_ref)}">Reintentar correo</button></div><p class="admin-order-result" aria-live="polite"></p></div></article>`;}).join('');}
async function loadAdminOrders(){const msg=$('adminOrdersMessage');if(msg)msg.textContent='Cargando pedidos…';try{const r=await fetch('/api/admin/orders',{headers:adminHeaders()});const data=await r.json();if(!r.ok)throw new Error(data.detail||'No se pudieron cargar los pedidos.');adminOrderRows=data.orders||[];adminStatusLabels=data.statuses||{};const filter=$('adminStatusFilter');if(filter){const previous=filter.value;filter.innerHTML='<option value="">Todos los estados</option>'+Object.entries(adminStatusLabels).map(([v,l])=>`<option value="${escapeHtml(v)}">${escapeHtml(l)}</option>`).join('');if([...filter.options].some(o=>o.value===previous))filter.value=previous;}renderAdminOrders();if(msg)msg.textContent=`${adminOrderRows.length} pedido(s) cargados. Los correos dependen de la configuración SMTP.`;}catch(e){if(msg)msg.textContent=e.message;throw e;}}
async function adminChangeStatus(button){const card=button.closest('.admin-order-card');if(!card)return;const ref=button.dataset.ref;const status=card.querySelector('.admin-new-status').value;const detail=card.querySelector('.admin-status-detail').value.trim();const result=card.querySelector('.admin-order-result');button.disabled=true;button.textContent='Guardando…';result.textContent='Actualizando estado y enviando notificación…';try{const r=await fetch(`/api/admin/orders/${encodeURIComponent(ref)}/status`,{method:'POST',headers:adminHeaders(),body:JSON.stringify({status,detail})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'No se pudo actualizar el pedido.');result.textContent=data.unchanged?'El pedido ya tenía ese estado.':`Estado actualizado. Correo: ${data.email_sent?'enviado':(data.email_status||'pendiente; revisa SMTP')}.`;toast(data.email_sent?'Estado actualizado y correo enviado.':'Estado actualizado; el correo no se confirmó como enviado.');await loadAdminOrders();}catch(e){result.textContent=e.message;toast(e.message);}finally{button.disabled=false;button.textContent='Guardar estado y notificar';}}
async function adminRetryEmail(button){const card=button.closest('.admin-order-card');const result=card?.querySelector('.admin-order-result');button.disabled=true;try{const r=await fetch(`/api/admin/orders/${encodeURIComponent(button.dataset.ref)}/retry-email`,{method:'POST',headers:adminHeaders()});const data=await r.json();if(!r.ok)throw new Error(data.detail||'No se pudo reintentar el correo.');const ok=!!(data.email_sent||data.sent);if(result)result.textContent=ok?'El correo figura como enviado.':`No se pudo confirmar el envío: ${data.email_status||'revisa la configuración SMTP'}.`;toast(ok?'Notificación enviada o ya registrada como enviada.':'El correo sigue pendiente.');}catch(e){if(result)result.textContent=e.message;toast(e.message);}finally{button.disabled=false;}}
async function loadAdminMetrics(){if(!adminKey){adminKey=prompt('Introduce la ADMIN_API_KEY configurada en Railway:')||'';}if(!adminKey)return;const status=$('adminStatus');status.textContent='Consultando métricas…';try{const r=await fetch('/api/admin/metrics',{headers:{'X-Admin-Key':adminKey}});const data=await r.json();if(!r.ok)throw new Error(data.detail||'No se pudo cargar el panel.');$('adminPanel').classList.remove('hidden');status.textContent='Panel administrativo · los estados se guardan en la base de datos.';$('adminMetrics').innerHTML=[['Usuarios',data.users],['Pedidos registrados',data.orders],['Volumen registrado',money(data.demo_volume)],['Artículos en carritos',data.cart_items],['Búsquedas 24 h',data.searches_24h],['Eventos de auditoría',data.audit_events]].map(x=>`<div class="metric-card"><small>${escapeHtml(x[0])}</small><strong>${escapeHtml(x[1])}</strong></div>`).join('');$('adminAudit').innerHTML=(data.recent_audit||[]).map(x=>`<div class="audit-row"><b>${escapeHtml(x.action)}</b><span>${escapeHtml(x.detail)}</span><small>${escapeHtml(x.created_at)}</small></div>`).join('')||'<p class="hint">Sin eventos.</p>';await loadAdminOrders();}catch(e){status.textContent=e.message;$('adminPanel').classList.remove('hidden');if(/clave|admin|403|503/i.test(e.message))adminKey='';}}
$('adminOrders')?.addEventListener('click',e=>{const save=e.target.closest('.admin-save-status');const retry=e.target.closest('.admin-retry-email');if(save)adminChangeStatus(save);if(retry)adminRetryEmail(retry);});
$('adminStatusFilter')?.addEventListener('change',renderAdminOrders);$('adminOrderSearch')?.addEventListener('input',renderAdminOrders);$('adminLoadOrdersBtn')?.addEventListener('click',async()=>{try{await loadAdminOrders();}catch(_){}});
function openCheckout(){if(!state.cart.length){toast('Agrega primero un artículo al carrito.');return;}const t=estimateCart();$('checkoutTotal').textContent=money(t.total,state.currency);$('checkoutItemCount').textContent=`${state.cart.reduce((n,x)=>n+Number(x.qty||1),0)} artículo(s)`;$('checkoutError').textContent='';$('demoConsent').checked=false;showView('checkout');}
async function submitCheckout(ev){ev.preventDefault();if(!$('demoConsent').checked){$('checkoutError').textContent='Confirma que entiendes que se trata de un pedido simulado.';return;}const btn=$('placeOrderBtn');btn.disabled=true;btn.textContent='Registrando pedido…';$('checkoutError').textContent='';const body={customer_email:$('customerEmail').value.trim(),shipping_name:$('shipName').value.trim(),shipping_city:$('shipCity').value.trim(),shipping_country:$('shipCountry').value.trim(),shipping_address:$('shipAddress').value.trim(),payment_method:'demo_balance'};try{const result=await api('/api/purchase',{method:'POST',body:JSON.stringify(body)});await refresh();showView('history');toast(`Pedido ${result.order_ref} registrado · correo ${result.email_sent?'enviado':'pendiente de configuración'}`);if(tg&&typeof tg.HapticFeedback?.notificationOccurred==='function')tg.HapticFeedback.notificationOccurred('success');}catch(e){$('checkoutError').textContent=e.message||'No se pudo registrar el pedido.';}finally{btn.disabled=false;btn.innerHTML='Confirmar pedido simulado <span>✓</span>';}}
// Navigation: preserve the original API routes and session model.
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',async()=>{const tab=b.dataset.tab;if(tab==='search'){showView('home');setTimeout(()=>$('query')?.focus(),120);return;}if(['home','cart','checkout','history','account'].includes(tab)){if(tab!=='home')try{await refresh()}catch(e){toast(e.message);return;}if(tab==='checkout'){openCheckout();return;}showView(tab);}}));
document.querySelectorAll('.store').forEach(b=>b.onclick=()=>{selectedStore=b.dataset.store;document.querySelectorAll('.store').forEach(x=>x.classList.toggle('active',x===b));});
document.querySelectorAll('[data-search-store]').forEach(b=>b.addEventListener('click',()=>performSearch(undefined,b.dataset.searchStore)));
$('loginForm').addEventListener('submit',async e=>{e.preventDefault();$('loginError').textContent='';try{const data=await api('/api/login',{method:'POST',body:JSON.stringify({init_data:tg?.initData||'',username:$('username').value.trim(),password:$('password').value})});token=data.token;sessionStorage.setItem('shopcart_token',token);setLoggedIn(true);await refresh();toast('Bienvenido a ProEshop');}catch(err){$('loginError').textContent=err.message;}});
$('searchBtn').onclick=()=>performSearch();$('query').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();performSearch();}});$('clearSearch').onclick=()=>{$('query').value='';$('clearSearch').classList.add('hidden');$('searchResult').classList.add('hidden');$('homeEmpty').classList.remove('hidden');lastSearch=[];$('query').focus();};
document.querySelectorAll('[data-query]').forEach(b=>b.addEventListener('click',()=>performSearch(b.dataset.query)));document.querySelectorAll('[data-focus-search]').forEach(b=>b.addEventListener('click',()=>$('query').focus()));
$('checkoutBtn').onclick=openCheckout;$('checkoutForm').addEventListener('submit',submitCheckout);$('refreshOrders').onclick=async()=>{try{await refresh();toast('Pedidos actualizados');}catch(e){toast(e.message)}};
$('notificationBtn').onclick=async()=>{await loadNotificationPreferences();$('notificationDialog').showModal()};$('saveNotificationsBtn').onclick=saveNotificationPreferences;$('adminOpenBtn').onclick=loadAdminMetrics;$('adminRefreshBtn').onclick=loadAdminMetrics;$('closeNotificationDialog').onclick=()=>$('notificationDialog').close();$('closeNotificationOk').onclick=()=>$('notificationDialog').close();$('closeProductDialog').onclick=()=>$('productDialog').close();$('logoutAccountBtn').onclick=()=>$('logoutBtn').click();
$('logoutBtn').onclick=async()=>{try{await api('/api/logout',{method:'POST',body:'{}'});}catch(_){}token='';sessionStorage.removeItem('shopcart_token');setLoggedIn(false);$('password').value='';$('loginError').textContent='';toast('Sesión cerrada');};
(async()=>{if(token){try{setLoggedIn(true);await refresh();}catch(_){token='';sessionStorage.removeItem('shopcart_token');setLoggedIn(false);}}})();
