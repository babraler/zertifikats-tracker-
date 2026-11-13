/* ---------- App: Menü (ein Eintrag je Zertifikat), Teilen, Suche ---------- */
// Jede Ansicht zeigt genau ein Zertifikat. Das Gerät merkt sich das zuletzt gewählte als Start.
// Braucht LOGIK (logik.js) und h, zeigeZertifikat (ansicht.js).
function starteApp(roh){
  const L=LOGIK;
  const root=document.getElementById('app');
  const MERKER='discount-tracker-start';
  // Altes Einzelformat (ein Zertifikat ohne Liste) weiter lesen können
  const G=roh&&typeof roh==='object'?(Array.isArray(roh.zertifikate)?roh:(roh.produkt?{stand:roh.stand,status:roh.status,zertifikate:[roh]}:null)):null;
  if(!G||!G.zertifikate.length){
    root.append(h('div',{class:'hint'},h('h1',{text:'Noch keine Kursdaten'}),
      h('p',{text:'Diese Seite wird beim täglichen Lauf mit den Kursen befüllt.'})));
    return;
  }
  const Z=G.zertifikate.filter(z=>z&&z.produkt&&L.isinGueltig(str(z.produkt.isin)));
  const ISINS=Z.map(z=>z.produkt.isin);
  const repo=str(G.repo);
  const entfernenUrl=z=>Z.length>1?L.issueUrl(repo,'entfernen',z.produkt.isin):null;
  const zuZ=isin=>'#/z/'+isin;
  function gemerkt(){try{return localStorage.getItem(MERKER);}catch(e){return null;}}
  function merke(isin){try{localStorage.setItem(MERKER,isin);}catch(e){}}

  /* Teilen: Teilen-Menü des Geräts, sonst Zwischenablage, sonst Text zum Kopieren */
  async function teile(daten,knopf,ablage){
    const alt=knopf.dataset.label||(knopf.dataset.label=knopf.textContent);
    const melde=t=>{knopf.textContent=t;ablage.replaceChildren(h('span',{class:'sr',text:t}));clearTimeout(knopf._uhr);
      knopf._uhr=setTimeout(()=>{if(knopf.isConnected){knopf.textContent=alt;ablage.replaceChildren();}},2200);};
    if(navigator.share){
      try{await navigator.share(daten);return;}catch(e){if(e&&e.name==='AbortError')return;}
    }
    const text=daten.url?(daten.text?daten.text+' ':'')+daten.url:daten.text;
    try{await navigator.clipboard.writeText(text);melde('Kopiert');return;}catch(e){}
    const feld=h('input',{class:'copy',readonly:true,value:text,'aria-label':'Zum Kopieren',onfocus:e=>e.target.select()});
    ablage.replaceChildren(feld);feld.focus();
  }
  function teilenKnopf(z){
    const url=L.teilenUrl(location.href,z.produkt.isin);
    if(!url)return null;
    const ablage=h('div',{role:'status'});
    const knopf=h('button',{type:'button',class:'btn2',text:'Link teilen'});
    knopf.addEventListener('click',()=>teile({title:L.kurzname(z.produkt)+' – Discount-Tracker',
      text:'Mein Discount-Zertifikat im Tracker:',url},knopf,ablage));
    return h('div',{class:'acts'},knopf,h('span',{class:'sub',text:'Der Link öffnet direkt diese Übersicht.'}),ablage);
  }

  /* Menü */
  const links=Z.map(z=>({href:zuZ(z.produkt.isin),text:L.kurzname(z.produkt),key:z.produkt.isin,warn:z.status&&z.status.ok===false}))
    .concat([{href:'#/suche',text:'Suchen',key:'suche'}]);
  const nav=h('nav',{class:'menu','aria-label':'Zertifikate'},links.map(l=>h('a',{href:l.href,'data-key':l.key},
    l.key==='suche'?[h('span',{class:'lupe','aria-hidden':'true'}),l.text]:l.text,l.warn?[h('span',{class:'dot-warn',title:'Abruf gestört','aria-hidden':'true'}),h('span',{class:'sr',text:' (Abruf gestört)'})]:null)));
  const seite=h('main',{id:'seite'});
  root.append(h('header',{class:'top'},h('a',{class:'brand',href:'#/'},'Discount-Tracker'),nav),seite);

  let aufraeumen=()=>{};
  function zeige(){
    aufraeumen();aufraeumen=()=>{};
    const r=L.route(location.hash,ISINS,L.startIsin(ISINS,gemerkt()));
    const key=r.seite==='zertifikat'?r.isin:r.seite;
    nav.querySelectorAll('a').forEach(a=>{
      const an=a.getAttribute('data-key')===key;
      if(an){a.setAttribute('aria-current','page');
        // nur das Menü seitlich schieben, nie die Seite (scrollIntoView würde auch senkrecht scrollen)
        if(a.offsetLeft<nav.scrollLeft||a.offsetLeft+a.offsetWidth>nav.scrollLeft+nav.clientWidth)nav.scrollLeft=a.offsetLeft-16;}
      else a.removeAttribute('aria-current');
    });
    seite.replaceChildren();
    try{zeigeSeite(r);}catch(e){
      seite.replaceChildren(h('div',{class:'warn',role:'alert'},h('b',{text:'Ansicht konnte nicht aufgebaut werden. '}),
        'Bitte neu laden oder oben ein anderes Zertifikat wählen.'));
    }
  }
  function zeigeSeite(r){
    if(r.seite==='zertifikat'){
      const z=Z.find(x=>x.produkt.isin===r.isin);
      merke(z.produkt.isin);
      document.title=L.kurzname(z.produkt)+' – Discount-Tracker';
      aufraeumen=zeigeZertifikat(seite,z,{entfernen:entfernenUrl(z),aktionen:teilenKnopf(z)});
    }else{
      document.title='Suchen – Discount-Tracker';
      aufraeumen=suche(seite);
    }
  }

  /* Suche */
  let q='';
  function suche(ziel){
    let abbruch=null;
    const eingabe=h('input',{type:'search',id:'q',value:q,placeholder:'Name, WKN oder ISIN',autocomplete:'off',autocapitalize:'characters',spellcheck:'false','aria-describedby':'qhint'});
    const ergebnis=h('div',{'aria-live':'polite'});
    const neu=h('div');
    function zeileVerfolgt(z){
      const e=entfernenUrl(z);
      return h('li',{class:'hit'},h('div',null,h('a',{href:zuZ(z.produkt.isin),class:'zlink',text:L.kurzname(z.produkt)}),
        h('div',{class:'sub',text:[z.produkt.name,z.produkt.wkn,z.produkt.isin].map(str).filter(Boolean).join(' · ')})),
        e?h('a',{class:'lnk',href:e,target:'_blank',rel:'noopener noreferrer',text:'Entfernen',title:'Nur für den Betreiber, öffnet GitHub'}):null);
    }
    function karte(v){
      const voll=Z.length>=L.MAX_ZERTIFIKATE, url=L.issueUrl(repo,'hinzufügen',v.isin);
      const fakten=[['WKN',v.wkn],['ISIN',v.isin],['Emittent',v.emittent],['Basiswert',v.basis],['Cap',eur(v.cap)],
        ['Fällig',v.faellig?L.dFull(v.faellig):'–'],['Geld / Brief',eur(v.geld)+' / '+eur(v.brief)]];
      const ablage=h('div',{role:'status'});
      const anfrage=h('button',{type:'button',class:'btn',text:'Hinzufügen anfragen'});
      anfrage.addEventListener('click',()=>teile({title:'Zertifikat für den Tracker',text:L.anfrageText(v)},anfrage,ablage));
      return h('div',{class:'card'},h('h3',{text:v.name||'Discount-Zertifikat'}),
        h('dl',{class:'facts'},fakten.map(([k,w])=>h('div',null,h('dt',{text:k}),h('dd',{class:'num',text:str(w)||'–'})))),
        voll?h('p',{class:'warn',text:`Es werden schon ${L.MAX_ZERTIFIKATE} Zertifikate verfolgt. Erst muss eines entfernt werden.`})
          :h('div',{class:'acts'},anfrage,
            url?h('a',{class:'btn2',href:url,target:'_blank',rel:'noopener noreferrer',text:'Über GitHub hinzufügen (Betreiber)'}):null,ablage),
        h('p',{class:'note',text:'„Hinzufügen anfragen“ schickt WKN und ISIN an den Betreiber des Trackers, zum Beispiel per Nachricht. Kurse: onvista, Stand jetzt.'}));
    }
    async function pruefe(k,knopf){
      knopf.disabled=true;knopf.textContent='Frage onvista …';
      if(abbruch)abbruch.abort();
      abbruch=new AbortController();const uhr=setTimeout(()=>abbruch.abort(),8000);
      let inhalt;
      try{
        // onvista erlaubt Abrufe aus dem Browser (CORS *), geprüft am 13.11.2026
        const res=await fetch(L.snapshotUrl(k),{signal:abbruch.signal,credentials:'omit',referrerPolicy:'no-referrer'});
        if(res.status===404)inhalt=h('p',{class:'warn',text:'onvista kennt diese Kennung nicht als Zertifikat.'});
        else if(!res.ok)inhalt=h('p',{class:'warn',text:`onvista antwortet nicht wie erwartet (HTTP ${res.status}). Später erneut versuchen.`});
        else{const v=L.vorschau(await res.json());inhalt=v.fehler?h('p',{class:'warn',text:v.fehler}):(L.verfolgt(Z,{art:'isin',wert:v.isin})?h('p',{class:'note',text:'Dieses Zertifikat wird schon verfolgt.'}):karte(v));}
      }catch(e){
        if(e&&e.name==='AbortError'&&!document.body.contains(knopf))return;
        inhalt=h('p',{class:'warn',text:'Keine Verbindung zu onvista. Ohne Netz geht nur die Suche in den verfolgten Zertifikaten.'});
      }finally{clearTimeout(uhr);}
      if(document.body.contains(knopf))neu.replaceChildren(inhalt);
    }
    function render(){
      q=eingabe.value;
      const treffer=L.filtere(Z,q), k=L.erkenne(q);
      ergebnis.replaceChildren(h('h2',{text:`Verfolgt (${Z.length} von ${L.MAX_ZERTIFIKATE})`}),
        treffer.length?h('ul',{class:'hits'},treffer.map(zeileVerfolgt)):h('p',{class:'empty',text:'Kein verfolgtes Zertifikat passt.'}));
      if(!q.trim()){neu.replaceChildren(h('p',{class:'note',text:'Für ein neues Zertifikat die WKN (6 Zeichen) oder ISIN (12 Zeichen) eingeben.'}));return;}
      if(!k){neu.replaceChildren(h('p',{class:'note',text:'Namen sucht die App nur unter den verfolgten Zertifikaten. Neue Zertifikate per WKN oder ISIN suchen.'}));return;}
      if(L.verfolgt(Z,k)){neu.replaceChildren(h('p',{class:'note',text:`${k.wert} wird schon verfolgt.`}));return;}
      const knopf=h('button',{type:'button',class:'btn','data-pruefen':'',text:`${k.wert} bei onvista nachsehen`});
      knopf.addEventListener('click',()=>pruefe(k,knopf));
      neu.replaceChildren(knopf);
    }
    eingabe.addEventListener('input',render);
    eingabe.addEventListener('keydown',e=>{if(e.key==='Enter'){const b=neu.querySelector('button[data-pruefen]');if(b){e.preventDefault();b.click();}}});
    ziel.append(h('div',{class:'ovhead'},h('h1',{text:'Suchen und hinzufügen'})),
      h('label',{class:'srch',for:'q'},h('span',{class:'sr',text:'Suche'}),eingabe),
      h('p',{class:'sub',id:'qhint',text:'Durchsucht die verfolgten Zertifikate. Mit WKN oder ISIN auch neue Discount-Zertifikate.'}),
      h('section',null,ergebnis),h('section',null,h('h2',{text:'Neu hinzufügen'}),neu),
      h('section',{class:'how'},h('h2',{text:'So kommt dein Zertifikat in den Tracker'}),h('ol',null,
        h('li',{text:'WKN oder ISIN eingeben und bei onvista nachsehen.'}),
        h('li',{text:'„Hinzufügen anfragen“ tippen und die Nachricht an den Betreiber schicken. Er nimmt das Zertifikat auf, ab dann wird es 10 Wochen lang verfolgt.'}),
        h('li',{text:'Danach steht es oben im Menü. Die App öffnet beim nächsten Start das zuletzt gewählte Zertifikat.'}))));
    render();
    return ()=>{if(abbruch)abbruch.abort();};
  }

  addEventListener('hashchange',()=>{zeige();scrollTo(0,0);});
  zeige();
}
starteApp(DATEN);
