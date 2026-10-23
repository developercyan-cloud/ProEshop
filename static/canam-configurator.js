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
 sel.onchange=()=>{selected=Number(sel.value);colorIndex=0;for(const key of [...selectedAccessories.keys()]){const item=itemById(key);if(!item||!accessoryFits(item,models[selected]))selectedAccessories.delete(key);}activeCategory='roof';renderAll();};
}
function renderColors(){
 const m=models[selected]; if(colorIndex>=m.colors.length)colorIndex=0;
 $('swatches').innerHTML=m.colors.map((c,i)=>`<button type="button" class="swatch ${i===colorIndex?'active':''}" style="background:linear-gradient(135deg,${c.hex} 0 70%,${c.accent} 70% 100%)" title="${c.name}" aria-label="Color ${c.name}" aria-pressed="${i===colorIndex}" data-color="${i}"></button>`).join('');
 $('colorName').textContent=m.colors[colorIndex]?.name||'Color no especificado';
 $('swatches').querySelectorAll('[data-color]').forEach(b=>b.addEventListener('click',()=>{colorIndex=Number(b.dataset.color);renderColors();renderImage();}));
}
function renderSpecs(){const m=models[selected];const specs=[['susp','Suspensión',m.susp],['tire','Neumáticos',m.tires],['wheel','Rines',m.wheels],['screen','Pantalla y cámaras',m.screen]];const icons={susp:'<path d="M12 2v3M12 19v3M8 5h8M8 19h8"/><path d="M9 5v3l6 3-6 3v5"/>',tire:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 3v5M21 12h-5M12 21v-5M3 12h5"/>',wheel:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><path d="m12 3 0 6m9 3h-6m-3 9v-6m-9-3h6"/>',screen:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4M7 8h10M7 11h6"/>'};$('specs').innerHTML=specs.map(([id,k,v])=>`<div class="spec"><span class="spec-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${icons[id]}</svg></span><b>${k}</b><span>${v}</span></div>`).join('');}
function renderImage(){const m=models[selected],c=m.colors[colorIndex]||m.colors[0];$('vehicleImage').src=c.url;$('vehicleImage').alt=`${m.name} 2027, color ${c.name}`;$('imageStage').className='stage '+(['view-catalog','view-side','view-rear'][angle]||'view-catalog');$('angleLabel').textContent=viewLabels[angle];document.querySelectorAll('[data-angle]').forEach(b=>{b.classList.toggle('active',Number(b.dataset.angle)===angle);b.setAttribute('aria-pressed',String(Number(b.dataset.angle)===angle));});}
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
document.addEventListener('click',function(e){const b=e.target.closest('button[data-angle]');if(!b)return;e.preventDefault();e.stopPropagation();const next=Number(b.getAttribute('data-angle'));if(!Number.isInteger(next)||next<0||next>2)return;angle=next;renderImage();});function sendConfigurationToProEshop(){const m=models[selected];const accessoryTotal=[...selectedAccessories.keys()].reduce((sum,key)=>{const item=itemById(key);return sum+(item?itemPrice(item,m):0)},0);const total=promotionalPrice(m)+accessoryTotal;const extras=[...selectedAccessories.values()].map(x=>x.name);const title=(m.name+' 2027 · '+m.colors[colorIndex].name+(extras.length?' · Mejoras: '+extras.join(', '):' · Sin mejoras')).slice(0,180);if(window.parent&&window.parent!==window){window.parent.postMessage({type:'canam:add-to-cart',title,price:Math.round(total*100)/100,image:m.colors[colorIndex]?.url||'',model:m.name,color:m.colors[colorIndex].name,accessories:extras},location.origin);}else{alert('Abre este configurador desde la pestaña Can-Am de ProEshop para agregar la configuración al carrito.');}}
$('previewBtn').textContent='AGREGAR CONFIGURACIÓN AL CARRITO →';$('previewBtn').onclick=sendConfigurationToProEshop;
$('mobileContinue').addEventListener('click',()=> $('previewBtn').click());
function reportConfiguratorHeight(){if(window.parent&&window.parent!==window)window.parent.postMessage({type:'canam:resize',height:document.documentElement.scrollHeight},location.origin);}
window.addEventListener('load',reportConfiguratorHeight);window.addEventListener('resize',reportConfiguratorHeight);new MutationObserver(reportConfiguratorHeight).observe(document.body,{subtree:true,childList:true,attributes:true});window.addEventListener('message',e=>{if(e.origin===location.origin&&e.data?.type==='proeshop:resize-request')reportConfiguratorHeight();});setTimeout(reportConfiguratorHeight,300);setTimeout(reportConfiguratorHeight,1000);
renderAll();
