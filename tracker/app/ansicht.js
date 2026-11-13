// Detailansicht: Kennzahlen, Tagesanalyse, Chart, Wochenkurse, alle Tage. Braucht LOGIK (logik.js).
const {num,str,arr,fmt,eur,pct,WT,pd,dShort,dFull,dLong,tZeit,tStand,safeUrl}=LOGIK;

/* ---------- Helfer ---------- */
const NS='http://www.w3.org/2000/svg';
function h(tag,a,...kids){
  const e=document.createElement(tag);
  if(a)for(const k in a){const v=a[k];if(v==null||v===false)continue;
    if(k==='class')e.className=v;else if(k==='text')e.textContent=v;
    else if(k.slice(0,2)==='on')e.addEventListener(k.slice(2),v);
    else e.setAttribute(k,v===true?'':String(v));}
  kids.flat(Infinity).forEach(c=>{if(c==null||c===false)return;e.append(c.nodeType?c:document.createTextNode(String(c)));});
  return e;
}
function s(tag,a,...kids){
  const e=document.createElementNS(NS,tag);
  if(a)for(const k in a){const v=a[k];if(v==null||v===false)continue;
    if(k==='text')e.textContent=v;else e.setAttribute(k,String(v));}
  kids.flat(Infinity).forEach(c=>{if(c)e.append(c);});
  return e;
}
function chg(x){const v=num(x);if(v==null)return h('span',{class:'muted',text:'–'});
  return h('span',{class:v>0?'up':v<0?'down':'muted',text:(v>0?'▲ ':v<0?'▼ ':'')+pct(v)});}

/* ---------- Detailansicht eines Zertifikats ---------- */
// Rückgabe: Aufräumfunktion (Beobachter und Listener lösen), wenn die Ansicht verlassen wird.
function zeigeZertifikat(app,P,extra){
extra=extra||{};
const T=P?arr(P.tage).filter(r=>r&&pd(r.datum)):[];
if(!P||!T.length){
  app.append(h('div',{class:'hint'},h('h1',{text:'Noch keine Kursdaten'}),
    h('p',{text:'Für dieses Zertifikat liegen noch keine Kurse vor. Sie erscheinen nach dem nächsten erfolgreichen Lauf.'}),
    extra.entfernen?h('p',{style:'margin-top:14px'},h('a',{href:extra.entfernen,target:'_blank',rel:'noopener noreferrer',text:'Nicht mehr verfolgen'})):null));
  return ()=>{};
}
T.sort((a,b)=>a.datum<b.datum?-1:1);
const prod=P.produkt||{}, akt=P.aktuell||{}, fort=P.fortschritt||{}, status=P.status||{};
const W=arr(P.wochen);
const bname=str(prod.basis_name)||'Basiswert';
const SER=[
  {id:'z',name:'Zertifikat',key:'z_geld',wk:'z_schnitt',pc:'z_pct',cls:'z',lbl:'Zertifikat (Geld)'},
  {id:'b',name:bname,key:'basis',wk:'basis_schnitt',pc:'basis_pct',cls:'b',lbl:bname},
  {id:'d',name:'DAX',key:'dax',wk:'dax_schnitt',pc:'dax_pct',cls:'d',lbl:'DAX'}
];
const cap=num(prod.cap);
const st={view:'kurse',wk:false,sel:T.length-1,hover:null,animate:true};
const latest=T.length-1;

/* ---------- Kopf ---------- */
function head(){
  const facts=[['ISIN',prod.isin],['WKN',prod.wkn],['Emittent',prod.emittent],['Basiswert',bname+(str(prod.basis_isin)?'':'')],
    ['Cap',cap==null?'–':eur(cap)],['Fälligkeit',prod.faellig?dFull(prod.faellig):'–']];
  const dl=h('dl',{class:'facts'});
  facts.forEach(([k,v])=>dl.append(h('div',null,h('dt',{text:k}),h('dd',{class:'num',text:str(v)||(typeof v==='number'?String(v):'–')}))));
  const wrap=h('header',{class:'head'},
    h('h1',null,h('span',{text:str(prod.name)||'Discount-Zertifikat'}),prod.demo===true?h('span',{class:'pill',text:'Beispiel-Zertifikat'}):null),dl);
  const tag=num(fort.tag),ges=num(fort.tage_gesamt);
  if(tag!=null&&ges){
    wrap.append(h('div',{class:'prog'},h('span',{class:'num',text:`Tag ${fmt(tag,0)} von ${fmt(ges,0)}`+(num(fort.woche)!=null?`, Woche ${fmt(fort.woche,0)} von 10`:'')}),
      h('span',{class:'bar','aria-hidden':'true'},h('i',{style:`width:${Math.max(0,Math.min(100,tag/ges*100)).toFixed(1)}%`}))));
  }
  if(status.ok===false)wrap.append(h('div',{class:'warn',role:'alert'},h('b',{text:'Abruf gestört. '}),str(status.meldung)||'Der letzte Lauf war nicht vollständig. Die Kurse können veraltet sein.'));
  return wrap;
}

/* ---------- Kennzahlen ---------- */
function lastVal(k){for(let i=T.length-1;i>=0;i--){const v=num(T[i][k]);if(v!=null)return v;}return null;}
function kpis(){
  const L=T[latest];
  const z=num(akt.z_geld)??lastVal('z_geld'), zb=num(akt.z_brief)??lastVal('z_brief');
  const cell=(k,v,d,s)=>h('div',{class:'kpi'},h('div',{class:'k',text:k}),h('div',{class:'v num'},v),h('div',{class:'d num'},d),s?h('div',{class:'s num'},s):null);
  const ss=akt.seit_start||{}, sd=str(ss.bezug_datum);
  const seit=(x,extra)=>sd&&num(x)!=null?['Seit Start ',chg(x),extra||'']:null;
  const strip=h('div',{class:'strip'},
    cell('Zertifikat, Geldkurs',[eur(z)],[chg(L.z_pct),h('span',{class:'muted',text:'  Brief '+eur(zb)})],seit(ss.z_pct,num(ss.z_eur)!=null?' ('+eur(ss.z_eur,2,true)+')':'')),
    cell(bname,[eur(num(L.basis)??lastVal('basis'))],[chg(L.basis_pct)],seit(ss.basis_pct)),
    cell('DAX',[fmt(num(L.dax)??lastVal('dax'),2)],[chg(L.dax_pct)],seit(ss.dax_pct)),
    cell('Restlicher Maximalertrag',[eur(akt.max_ertrag_eur,2,true)],[pct(akt.max_ertrag_pct,false)+(prod.faellig?' bis '+dFull(prod.faellig):'')]),
    cell('Delta',[fmt(akt.delta??lastVal('delta'),2)],[num(akt.discount_pct)!=null?'Discount '+pct(akt.discount_pct,false):'']));
  const d=num(akt.delta)??lastVal('delta'), bz=num(prod.bezug)??1, ca=num(akt.cap_abstand_pct);
  let txt='Delta nicht verfügbar.';
  if(d!=null){
    txt=`Delta ${fmt(d,2)}: Steigt der ${bname}-Kurs um 1 €, bewegt sich das Zertifikat um etwa ${fmt(d*bz,2)} €.`;
    if(ca!=null)txt+=ca>0?` Die Aktie liegt ${fmt(ca,1)} % über dem Cap. Das Zertifikat ist nahe am Höchstwert, Aktienbewegungen kommen kaum an.`
      :` Bis zum Cap fehlen ${fmt(Math.abs(ca),1)} %. Bewegungen der Aktie kommen deutlich stärker an.`;
  }
  return h('section',{'aria-label':'Kennzahlen'},h('h2',{class:'sr',text:'Kennzahlen'}),strip,h('p',{class:'delta-text',text:txt}));
}

/* ---------- Der Tag ---------- */
const EFF=[['effekt_markt','DAX-Bewegung','Markt'],['effekt_aktie','Aktie selbst','ohne Markt'],['effekt_zeit','Zeitwert','Laufzeit'],['effekt_rest','Sonstiges','Spread, Vola, Zinsen']];
const DRIVER={'DAX-Bewegung':'effekt_markt','Aktie selbst':'effekt_aktie','Zeitwert':'effekt_zeit'};
function newsItem(n){
  const u=safeUrl(n&&n.url), t=str(n&&n.titel)||'Ohne Titel';
  const title=u?h('a',{href:u,rel:'noopener noreferrer',target:'_blank',text:t}):h('span',{text:t});
  const rich=str(n.richtung), passt=n.passt;
  const bezug=str(n.kategorie)==='Makro'?'zum DAX':'zur Aktie ohne Markt', gegen=str(n.kategorie)==='Makro'?'gegen den DAX':'gegen die Aktie ohne Markt';
  const bits=[str(n.kategorie),rich&&rich!=='neutral'?rich:'',passt===true?'passt '+bezug:passt===false?'läuft '+gegen:''].filter(Boolean).join(', ');
  return h('li',null,h('div',{class:'t'},title),
    h('div',{class:'m'},[str(n.quelle),tZeit(n.zeit)].filter(Boolean).join(', ')),bits?h('div',{class:'m',text:bits}):null);
}
function effRows(r){
  const vals=EFF.map(e=>num(r[e[0]]));
  const mx=Math.max(0.0001,...vals.filter(v=>v!=null).map(Math.abs));
  const drv=str(r.haupttreiber);
  const rows=h('div',{class:'rows'});
  EFF.forEach((e,i)=>{
    const v=vals[i];
    const isD=drv&&(e[1]===drv||(e[0]==='effekt_rest'&&drv.indexOf('Sonstiges')===0));
    const bar=h('div',{class:'track'});
    if(v!=null&&v!==0)bar.append(h('i',{class:v>0?'p':'n',style:`width:${(Math.abs(v)/mx*50).toFixed(1)}%`}));
    rows.append(h('div',{class:'erow'},
      h('div',{class:'l'},e[1],h('em',{text:isD?'Haupttreiber':e[2]})),bar,h('div',{class:'v num',text:eur(v,2,true)})));
  });
  const dz=num(r.dz);
  rows.append(h('div',{class:'erow sum'},h('div',{class:'l',text:'Zertifikat gesamt'}),h('div',{class:'track'}),h('div',{class:'v num',text:eur(dz,2,true)})));
  return rows;
}
const spr=r=>arr(r&&r.spruenge).filter(s=>s&&num(s.pct)!=null);
function sprungText(s){return str(s.wert)+' '+pct(s.pct)+(num(s.schwelle)!=null?' (Schwelle ±'+fmt(s.schwelle,0)+' %)':'');}
function dayBody(r){
  const frag=h('div',{class:'daygrid'});
  const left=h('div');
  const sj=spr(r);
  if(sj.length)left.append(h('p',{class:'jumpnote',role:'note'},h('b',{text:'Kurssprung: '}),sj.map(sprungText).join(', ')+'.'));
  const vk=str(r.verdikt);
  if(vk)left.append(h('span',{class:'verdict'+(r.auffaellig===true||vk.indexOf('Zusammenhang')>=0?'':' soft'),text:vk}));
  left.append(h('p',{class:'daytext',text:str(r.text)||'Für diesen Tag liegt keine Erklärung vor (kein Vortag oder unvollständige Kurse).'}));
  const hasEff=EFF.some(e=>num(r[e[0]])!=null);
  if(hasEff){left.append(h('div',{class:'eff'},h('h3',{text:'Beitrag zur Kursänderung des Zertifikats'}),effRows(r)));}
  const right=h('div',{class:'news'},h('h3',{text:'Nachrichten im Zeitraum'}));
  const ns=arr(r.nachrichten);
  if(ns.length){right.append(h('ul',{class:'newslist'},ns.slice(0,3).map(newsItem)));}
  else right.append(h('p',{class:'empty',text:'Keine Nachrichten gefunden.'}));
  right.append(h('p',{class:'note',text:'Zeitlicher Zusammenhang, kein Beweis.'}));
  frag.append(left,right);
  return frag;
}
function daySection(){
  const r=T[st.sel];
  const isNow=st.sel===latest;
  const head=h('div',{class:'dayhead'},
    h('h2',{text:isNow?'Der heutige Tag':'Handelstag '+dShort(r.datum)+dFull(r.datum).slice(6)}),
    h('span',{class:'sub num',text:dLong(r.datum)+(r.phase==='vorlauf'?', Vorlauf':'')}),
    isNow?null:h('button',{class:'back',type:'button',text:'Zum aktuellen Tag',onclick:()=>selectDay(latest,false)}));
  return h('section',{id:'tag','aria-live':'polite',style:'scroll-margin-top:12px'},head,dayBody(r));
}

/* ---------- Chart ---------- */
function niceTicks(min,max,n){
  if(!(max>min)){max=min+1;}
  const raw=(max-min)/n, mag=Math.pow(10,Math.floor(Math.log10(raw))), nm=raw/mag;
  const step=(nm<1.5?1:nm<3?2:nm<7?5:10)*mag;
  const a=Math.floor(min/step+1e-9)*step, b=Math.ceil(max/step-1e-9)*step, t=[];
  for(let v=a;v<=b+step/2;v+=step)t.push(+v.toFixed(10));
  return {t,lo:a,hi:b,dec:Math.max(0,-Math.floor(Math.log10(step)+1e-9))};
}
const i0=(()=>{const k=T.findIndex(r=>r.phase==='lauf');return k<0?0:k;})();
function baseOf(key){for(let i=i0;i<T.length;i++){const v=num(T[i][key]);if(v!=null)return v;}
  for(let i=0;i<i0;i++){const v=num(T[i][key]);if(v!=null)return v;}return null;}
const BASE={};SER.forEach(x=>BASE[x.id]=baseOf(x.key));
function weekIdx(){ // pro Tag: Wochenobjekt oder null
  return T.map(r=>W.find(w=>str(w.von)<=r.datum&&r.datum<=str(w.bis))||null);
}
function panelsFor(view){
  if(view==='vergleich')return [{id:'v',sers:SER,idx:true,h:0.34}];
  return [{id:'p1',sers:[SER[0]],title:'Zertifikat, Geldkurs in €',h:0.5},{id:'p2',sers:[SER[1]],title:bname+' in €, Cap gestrichelt',cap:true,h:0.36}];
}
let geo=null, tipEl=null, xh=null, selLine=null;
function drawChart(){
  const box=document.getElementById('chart');
  const Wd=Math.max(280,box.clientWidth), narrow=Wd<560, n=T.length;
  const m={l:narrow?40:50,r:narrow?72:104,t:6,b:26};
  const pw=Wd-m.l-m.r;
  const totalH=narrow?(st.view==='kurse'?470:340):(st.view==='kurse'?560:420);
  const pans=panelsFor(st.view), titleH=st.view==='kurse'?20:4, gap=st.view==='kurse'?22:0;
  const avail=totalH-m.t-m.b-pans.length*titleH-(pans.length-1)*gap;
  const X=i=>m.l+(n===1?pw/2:pw*i/(n-1));
  const Xe=i=>Math.max(m.l,Math.min(m.l+pw,X(i)));
  const wk=weekIdx();
  const svg=s('svg',{viewBox:`0 0 ${Wd} ${totalH}`,width:Wd,height:totalH,role:'img','aria-label':st.view==='kurse'?'Kursverlauf von Zertifikat und Basiswert':'Zertifikat, Basiswert und DAX, indexiert auf Laufbeginn gleich 100'});
  let y0=m.t;
  geo={X,n,m,pw,totalH,panels:[],narrow};
  const drawn=st.animate;
  pans.forEach((pn,pi)=>{
    y0+=titleH;
    const ph=Math.round(avail*pn.h/pans.reduce((a,p)=>a+p.h,0));
    const val=(sr,r,i)=>{const v=num(r[sr.key]);if(v==null)return null;return pn.idx?(BASE[sr.id]?v/BASE[sr.id]*100:null):v;};
    const wval=(sr,i)=>{const w=wk[i];if(!w)return null;const v=num(w[sr.wk]);if(v==null)return null;return pn.idx?(BASE[sr.id]?v/BASE[sr.id]*100:null):v;};
    let lo=Infinity,hi=-Infinity;
    pn.sers.forEach(sr=>T.forEach((r,i)=>{[val(sr,r,i),st.wk?wval(sr,i):null].forEach(v=>{if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v);}});}));
    if(pn.cap&&cap!=null){lo=Math.min(lo,cap);hi=Math.max(hi,cap);}
    if(!isFinite(lo)){lo=0;hi=1;}
    const padv=(hi-lo||1)*0.06; const nt=niceTicks(lo-padv,hi+padv,narrow?3:4);
    const Y=v=>y0+ph-(v-nt.lo)/(nt.hi-nt.lo)*ph;
    const g=s('g');
    if(pn.title)g.append(s('text',{x:m.l,y:y0-7,class:'pt',text:pn.title}));
    // Vorlauf
    if(i0>0){
      const xb=Math.max(m.l,Math.min(m.l+pw,(X(i0-1)+X(i0))/2));
      g.append(s('rect',{x:m.l,y:y0,width:xb-m.l,height:ph,class:'band'}));
      if(pi===0)g.append(s('text',{x:m.l+6,y:y0+14,text:'Vorlauf'}));
    }
    nt.t.forEach(v=>{
      g.append(s('line',{x1:m.l,x2:m.l+pw,y1:Y(v),y2:Y(v),class:'grid'}),
        s('text',{x:m.l-8,y:Y(v)+4,'text-anchor':'end',text:fmt(v,nt.dec)}));
    });
    g.append(s('line',{x1:m.l,x2:m.l+pw,y1:y0+ph,y2:y0+ph,class:'axisl'}));
    if(pn.cap&&cap!=null){
      g.append(s('line',{x1:m.l,x2:m.l+pw,y1:Y(cap),y2:Y(cap),class:'cap'}),
        s('text',{x:m.l+pw-4,y:Y(cap)-6,'text-anchor':'end',class:'lb',text:'Cap '+fmt(cap,2)}));
    }
    const labels=[];
    pn.sers.forEach(sr=>{
      if(st.wk){ // Wochenschnitt als Stufe
        let d='',prev=null;
        for(let i=0;i<n;){
          const w=wk[i];if(!w){i++;continue;}
          let j=i;while(j+1<n&&wk[j+1]===w)j++;
          const v=wval(sr,i);
          if(v!=null){const xa=Xe(i-0.5),xb=Xe(j+0.5);
            d+=(prev==null?'M':'L')+xa.toFixed(1)+' '+Y(prev==null?v:prev).toFixed(1)+(prev==null?'':'')+' ';
            if(prev!=null)d+='L'+xa.toFixed(1)+' '+Y(v).toFixed(1)+' ';
            d+='L'+xb.toFixed(1)+' '+Y(v).toFixed(1)+' ';prev=v;}
          i=j+1;
        }
        if(d)g.append(s('path',{d,class:'ln w '+sr.cls}));
      }
      const segs=[];let cur=[];
      T.forEach((r,i)=>{const v=val(sr,r,i);if(v==null){if(cur.length)segs.push(cur);cur=[];}else cur.push([X(i),Y(v)]);});
      if(cur.length)segs.push(cur);
      let d='';
      segs.forEach(sg=>{if(sg.length===1)g.append(s('circle',{cx:sg[0][0],cy:sg[0][1],r:2.5,class:'dot '+sr.cls}));
        else d+=sg.map((p,k)=>(k?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ')+' ';});
      if(d)g.append(s('path',{d,class:'ln '+sr.cls+(drawn?' draw':''),pathLength:1}));
      // Marker
      if(sr.id==='z'||pn.idx&&sr.id==='z'){
        T.forEach((r,i)=>{if(r.auffaellig===true){const v=val(sr,r,i);if(v!=null)g.append(s('circle',{cx:X(i),cy:Y(v),r:4.5,class:'mark'}));}});
      }
      // Endbeschriftung
      for(let i=n-1;i>=0;i--){const v=val(sr,T[i],i);if(v!=null){labels.push({y:Y(v),t:sr.name,i});break;}}
    });
    labels.sort((a,b)=>a.y-b.y);
    for(let k=1;k<labels.length;k++)if(labels[k].y-labels[k-1].y<15)labels[k].y=labels[k-1].y+15;
    labels.forEach(l=>g.append(s('text',{x:m.l+pw+8,y:l.y+4,class:'lb',text:l.t})));
    // Zeitachse unten am letzten Panel
    if(pi===pans.length-1){
      const maxT=narrow?4:7, stp=Math.max(1,Math.ceil(n/maxT));
      for(let i=0;i<n;i+=stp){
        g.append(s('line',{x1:X(i),x2:X(i),y1:y0+ph,y2:y0+ph+4,class:'axisl'}),
          s('text',{x:X(i),y:y0+ph+18,'text-anchor':i===0?'start':'middle',text:dShort(T[i].datum).slice(0,5)}));
      }
    }
    geo.panels.push({pn,y0,ph,Y,val});
    svg.append(g);
    y0+=ph+gap;
  });
  const top=m.t, bot=y0-gap;
  selLine=s('line',{y1:top,y2:bot,class:'sel'});
  xh=s('g',{style:'display:none'});
  xh.append(s('line',{y1:top,y2:bot,class:'xh'}));
  geo.dots=[];
  geo.panels.forEach(p=>p.pn.sers.forEach(sr=>{const c=s('circle',{r:4.5,class:'dot '+sr.cls,stroke:'var(--surface)','stroke-width':2});xh.append(c);geo.dots.push({c,sr,p});}));
  const hit=s('rect',{x:m.l,y:top,width:pw,height:bot-top,class:'hit'});
  svg.append(selLine,xh,hit);
  hit.addEventListener('pointermove',e=>{setHover(idxAt(e,hit));});
  hit.addEventListener('pointerdown',e=>{setHover(idxAt(e,hit));});
  hit.addEventListener('pointerleave',e=>{if(e.pointerType==='mouse')setHover(null);});
  hit.addEventListener('click',e=>{const i=idxAt(e,hit);setHover(i);selectDay(i,true);});
  box.replaceChildren(svg,tipEl=h('div',{class:'tip',hidden:true,role:'status'}));
  st.animate=false;
  placeSel();
  if(st.hover!=null)setHover(st.hover);
}
function idxAt(e,hit){
  const r=hit.getBoundingClientRect(), k=geo.n===1?0:Math.round((e.clientX-r.left)/r.width*(geo.n-1));
  return Math.max(0,Math.min(geo.n-1,k));
}
function placeSel(){
  if(!selLine)return;
  const x=geo.X(st.sel);selLine.setAttribute('x1',x);selLine.setAttribute('x2',x);
}
function tipRow(sr,r){
  const v=num(r[sr.key]);
  return h('div',{class:'r'},h('span',{class:'n'},h('i',{style:`border-color:var(--s${sr.id==='z'?1:sr.id==='b'?2:3})`}),sr.name),
    h('span',{class:'num'},fmt(v,2)+' ',chg(r[sr.pc])));
}
function setHover(i){
  st.hover=i;
  if(i==null||!geo){xh&&(xh.style.display='none');tipEl&&(tipEl.hidden=true);return;}
  const r=T[i], x=geo.X(i);
  xh.style.display='';
  xh.firstChild.setAttribute('x1',x);xh.firstChild.setAttribute('x2',x);
  geo.dots.forEach(d=>{const v=d.p.val(d.sr,r,i);
    if(v==null)d.c.style.display='none';else{d.c.style.display='';d.c.setAttribute('cx',x);d.c.setAttribute('cy',d.p.Y(v));}});
  const kids=[h('div',null,h('b',{text:dLong(r.datum)}),r.phase==='vorlauf'?h('span',{class:'muted',text:'  Vorlauf'}):null)];
  SER.forEach(sr=>kids.push(tipRow(sr,r)));
  if(st.view==='vergleich'){
    const ix=SER.map(sr=>{const v=num(r[sr.key]);return BASE[sr.id]&&v!=null?sr.name+' '+fmt(v/BASE[sr.id]*100,1):null;}).filter(Boolean).join(', ');
    if(ix)kids.push(h('div',{class:'h',text:'Index: '+ix}));
  }
  if(r.auffaellig===true)kids.push(h('div',{class:'h',text:'Auffälliger Tag'+(str(r.verdikt)?': '+r.verdikt:'')}));
  kids.push(h('div',{class:'h',text:'Klicken für die Erklärung'}));
  tipEl.replaceChildren(...kids);tipEl.hidden=false;
  const bw=tipEl.offsetWidth, W2=document.getElementById('chart').clientWidth;
  tipEl.style.left=Math.max(0,Math.min(W2-bw,x+14+bw>W2?x-bw-14:x+14))+'px';
}
function chartSection(){
  const modeBtn=(id,t)=>h('button',{type:'button','aria-pressed':String(st.view===id),text:t,onclick:()=>{st.view=id;st.animate=false;refreshChart();}});
  const seg=h('div',{class:'seg',role:'group','aria-label':'Darstellung'},modeBtn('kurse','Kurse'),modeBtn('vergleich','Vergleich (Start = 100)'));
  const chk=h('label',{class:'chk'},h('input',{type:'checkbox',checked:st.wk?true:null,onchange:e=>{st.wk=e.target.checked;refreshChart();}}),'Wochenschnitt zeigen');
  const box=h('div',{class:'chartwrap',id:'chart',tabindex:'0',role:'group','aria-label':'Kursdiagramm. Pfeiltasten wählen einen Tag, Eingabe öffnet die Erklärung.',
    onkeydown:e=>{
      if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const b=st.hover??st.sel;setHover(Math.max(0,Math.min(T.length-1,b+(e.key==='ArrowLeft'?-1:1))));}
      else if(e.key==='Enter'&&st.hover!=null){e.preventDefault();selectDay(st.hover,true);}
      else if(e.key==='Escape')setHover(null);
    }});
  const legend=h('div',{class:'legend',id:'legend'});
  return h('section',{'aria-label':'Chart'},h('h2',{text:'Kursverlauf'}),
    h('div',{class:'chartbox'},h('div',{class:'ctrl'},seg,chk),legend,box,
      h('p',{class:'chartnote',id:'cnote'})));
}
function updateLegend(){
  const lg=document.getElementById('legend');
  const items=(st.view==='kurse'?[SER[0],SER[1]]:SER).map(sr=>h('span',null,h('i',{style:`border-color:var(--s${sr.id==='z'?1:sr.id==='b'?2:3})`}),sr.name));
  if(st.view==='kurse'&&cap!=null)items.push(h('span',null,h('i',{class:'dash',style:'border-color:var(--ink-3)'}),'Cap'));
  if(st.wk)items.push(h('span',null,h('i',{style:'border-color:var(--ink-3);opacity:.7;border-top-width:1.5px'}),'Wochenschnitt'));
  if(T.some(r=>r.auffaellig===true))items.push(h('span',null,h('i',{class:'mk'}),'Auffälliger Tag'));
  lg.replaceChildren(...items);
  document.getElementById('cnote').textContent=(st.view==='vergleich'?`Jede Linie auf 100 gesetzt am ${dFull(T[i0].datum)}${i0>0?' (Laufbeginn)':''}. `:'')+(i0>0?'Der graue Bereich links ist der Vorlauf vor Laufbeginn. ':'')+'Fehlende Kurse bleiben als Lücke.';
}
function refreshChart(){
  document.querySelectorAll('.seg button').forEach((b,i)=>b.setAttribute('aria-pressed',String((i===0)===(st.view==='kurse'))));
  updateLegend();drawChart();
}

/* ---------- Tabellen ---------- */
function weeksSection(){
  const sec=h('section',{'aria-label':'Wochenkurse'},h('h2',{text:'Wochenkurse'}));
  if(!W.length){sec.append(h('p',{class:'empty',text:'Noch keine Woche im Lauf.'}));return sec;}
  sec.append(h('p',{class:'wnote',text:'Schlusskurs am letzten Handelstag der Woche, darunter die Veränderung zum Schluss der Vorwoche. Ø ist der Wochenschnitt.'}));
  const tb=h('tbody');
  const wc=(w,k,d)=>h('td',null,fmt(w[k+'_schluss'],d),h('small',null,chg(w[k+'_woche_pct']),h('span',{class:'muted',text:'Ø '+fmt(w[k+'_schnitt'],d)})));
  W.slice().reverse().forEach(w=>{
    const kw=/-W(\d+)/.exec(str(w.woche));
    const t=num(w.tage);
    tb.append(h('tr',null,
      h('td',null,h('b',{text:kw?'KW '+kw[1]:str(w.woche)}),h('small',null,h('span',{text:`${dShort(w.von)} bis ${dShort(w.bis)}`}),h('span',{text:`${t==null?'–':t} ${t===1?'Tag':'Tage'}`+(t!=null&&t<5?', unvollständig':'')}))),
      wc(w,'z',2),wc(w,'basis',2),wc(w,'dax',0)));
  });
  sec.append(h('div',{class:'tw'},h('table',null,h('thead',null,h('tr',null,
    h('th',{text:'Woche'}),h('th',{text:'Zertifikat'}),h('th',{text:bname}),h('th',{text:'DAX'}))),tb)));
  return sec;
}
const open=new Set();
function daysSection(){
  const sec=h('section',{'aria-label':'Alle Tage'},h('h2',{text:'Alle Tage'}));
  const only=h('label',{class:'chk filter'},h('input',{type:'checkbox',onchange:e=>build(e.target.checked)}),'Nur auffällige Tage und Kurssprünge');
  const tb=h('tbody');
  const thead=h('thead',null,h('tr',null,h('th',{text:'Datum'}),h('th',{text:'Zertifikat'}),h('th',{text:bname}),h('th',{text:'DAX'}),h('th',{class:'vcol',text:'Einordnung'})));
  function build(onlyAuf){
    tb.replaceChildren();
    for(let i=T.length-1;i>=0;i--){
      const r=T[i]; if(onlyAuf&&r.auffaellig!==true&&!spr(r).length)continue;
      const key=r.datum, isOpen=open.has(key);
      const btn=h('button',{class:'dbtn',type:'button','aria-expanded':String(isOpen),'aria-controls':'det-'+key,onclick:()=>{
        if(open.has(key))open.delete(key);else open.add(key);
        const d=document.getElementById('det-'+key),o=open.has(key);d.hidden=!o;btn.setAttribute('aria-expanded',String(o));}},
        h('span',{class:'ch','aria-hidden':'true'}),
        h('span',{style:'white-space:nowrap'},h('span',{class:'num',title:dLong(r.datum),text:WT[pd(r.datum).getUTCDay()]+' '+dShort(r.datum)}),r.auffaellig===true?[h('span',{class:'flag','aria-hidden':'true'}),h('span',{class:'sr',text:' auffällig'})]:null,
          spr(r).length?h('span',{class:'jump',title:spr(r).map(sprungText).join(', '),text:'Sprung'}):null,
          r.phase==='vorlauf'?h('small',{text:'Vorlauf'}):null));
      const c=(sr)=>h('td',null,fmt(r[sr.key],sr.id==='d'?0:2),h('small',null,chg(r[sr.pc])));
      tb.append(h('tr',{class:r.phase==='vorlauf'?'vor':''},h('td',null,btn),c(SER[0]),c(SER[1]),c(SER[2]),
        h('td',{class:'vcol',text:str(r.verdikt)||'–'})));
      const det=h('tr',{class:'det',id:'det-'+key,hidden:!isOpen},h('td',{colspan:5}));
      const cell=det.firstChild;
      if(str(r.verdikt))cell.append(h('span',{class:'verdict soft',text:r.verdikt}));
      cell.append(h('p',{class:'daytext',text:str(r.text)||'Keine Erklärung für diesen Tag.'}));
      const ns=arr(r.nachrichten);
      if(ns.length)cell.append(h('ul',{class:'newslist',style:'margin-top:14px'},ns.slice(0,3).map(newsItem)));
      cell.append(h('button',{class:'lnk',type:'button',text:'Als Tagesansicht öffnen',onclick:()=>selectDay(i,true)}));
      tb.append(det);
    }
  }
  build(false);
  sec.append(only,h('div',{class:'tw'},h('table',null,thead,tb)));
  return sec;
}

/* ---------- Zusammenbau ---------- */
function selectDay(i,scroll){
  st.sel=Math.max(0,Math.min(T.length-1,i));
  const old=document.getElementById('tag');
  const nw=daySection();old.replaceWith(nw);
  placeSel();
  if(scroll){const r=nw.getBoundingClientRect();
    if(r.top<0||r.top>innerHeight*0.6)nw.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});}
}
function foot(){
  const x=h('a',{href:'kurse.xlsx',download:'kurse.xlsx',text:'kurse.xlsx'});
  return h('footer',null,
    h('div',{text:'Stand: '+tStand(P.stand)}),
    h('div',null,'Quellen: onvista (Kurse), Google News (Schlagzeilen). Alle Kurse als Excel: ',x,'.'),
    h('div',{text:'Regelbasierte Auswertung ohne KI. Keine Anlageberatung.'}),
    extra.entfernen?h('div',null,h('a',{href:extra.entfernen,target:'_blank',rel:'noopener noreferrer',text:'Dieses Zertifikat nicht mehr verfolgen'}),' (öffnet GitHub)'):null);
}
app.append(head(),kpis(),daySection(),chartSection(),weeksSection(),daysSection(),foot());
updateLegend();drawChart();
const chartEl=document.getElementById('chart');
let lastW=chartEl.clientWidth;
const ro=new ResizeObserver(()=>{const w=chartEl.clientWidth;if(Math.abs(w-lastW)>1){lastW=w;drawChart();}});
ro.observe(chartEl);
const weg=e=>{if(e.pointerType!=='mouse'&&!e.target.closest('#chart'))setHover(null);};
document.addEventListener('pointerdown',weg);
return ()=>{ro.disconnect();document.removeEventListener('pointerdown',weg);};
}
