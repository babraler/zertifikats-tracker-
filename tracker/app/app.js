/* ---------- App: Menü, Übersicht (eine Spalte je Zertifikat), Suche ---------- */
// Braucht LOGIK (logik.js) und h, s, chg, zeigeZertifikat (ansicht.js).
function starteApp(roh){
  const L=LOGIK;
  const root=document.getElementById('app');
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

  /* Menü */
  const links=[{href:'#/',text:'Übersicht',key:'uebersicht'}]
    .concat(Z.map(z=>({href:zuZ(z.produkt.isin),text:L.kurzname(z.produkt),key:z.produkt.isin,warn:z.status&&z.status.ok===false})))
    .concat([{href:'#/suche',text:'Suchen',key:'suche'}]);
  const nav=h('nav',{class:'menu','aria-label':'Ansichten'},links.map(l=>h('a',{href:l.href,'data-key':l.key},
    l.key==='suche'?[h('span',{class:'lupe','aria-hidden':'true'}),l.text]:l.text,l.warn?h('span',{class:'dot-warn',title:'Abruf gestört'}):null)));
  const seite=h('main',{id:'seite'});
  root.append(h('header',{class:'top'},h('a',{class:'brand',href:'#/'},'Discount-Tracker'),nav),seite);

  let aufraeumen=()=>{};
  function zeige(){
    aufraeumen();aufraeumen=()=>{};
    const r=L.route(location.hash,ISINS);
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
        'Bitte neu laden. Die Übersicht funktioniert weiter: ',h('a',{href:'#/',text:'zur Übersicht'})));
    }
  }
  function zeigeSeite(r){
    if(r.seite==='zertifikat'){
      const z=Z.find(x=>x.produkt.isin===r.isin);
      document.title=L.kurzname(z.produkt)+' – Discount-Tracker';
      aufraeumen=zeigeZertifikat(seite,z,{entfernen:entfernenUrl(z)});
    }else if(r.seite==='suche'){
      document.title='Suchen – Discount-Tracker';
      aufraeumen=suche(seite);
    }else{
      document.title='Discount-Tracker';
      uebersicht(seite);
    }
  }

  /* Übersicht */
  function sparkZelle(z){
    const d=L.sparkPfad(L.verlauf(z),120,32);
    if(!d)return h('span',{class:'muted',text:'noch kein Verlauf'});
    const v=L.verlauf(z), cls=v[v.length-1]>=v[0]?'up':'down';
    return s('svg',{class:'spark '+cls,viewBox:'0 0 120 32',width:120,height:32,role:'img','aria-label':'Geldkurs seit Laufbeginn'},s('path',{d}));
  }
  const ZEILEN=[
    ['Verlauf seit Start',z=>sparkZelle(z)],
    ['Geldkurs',z=>{const t=L.letzterTag(z);return [h('b',{class:'num',text:eur(z.aktuell&&z.aktuell.z_geld)}),h('small',null,t?chg(t.z_pct):'–',t?h('span',{class:'muted',text:' am '+L.dShort(t.datum)}):null)];}],
    ['Seit Start',z=>{const ss=(z.aktuell&&z.aktuell.seit_start)||{};return [chg(ss.z_pct),num(ss.z_eur)!=null?h('small',{class:'muted',text:eur(ss.z_eur,2,true)}):null];}],
    ['Basiswert',z=>{const t=L.letzterTag(z);return [h('span',{class:'num',text:t?eur(t.basis):'–'}),h('small',null,str(z.produkt.basis_name)+' ',t?chg(t.basis_pct):null)];}],
    ['Restlicher Maximalertrag',z=>[h('span',{class:'num',text:pct(z.aktuell&&z.aktuell.max_ertrag_pct,false)}),h('small',{class:'muted',text:eur(z.aktuell&&z.aktuell.max_ertrag_eur,2,true)})]],
    ['Discount',z=>h('span',{class:'num',text:pct(z.aktuell&&z.aktuell.discount_pct,false)})],
    ['Basiswert zum Cap',z=>{const c=num(z.aktuell&&z.aktuell.cap_abstand_pct);return h('span',{class:'num',text:c==null?'–':c>0?fmt(c,1)+' % darüber':fmt(Math.abs(c),1)+' % darunter'});}],
    ['Cap',z=>h('span',{class:'num',text:eur(z.produkt.cap)})],
    ['Delta',z=>h('span',{class:'num',text:fmt(z.aktuell&&z.aktuell.delta,2)})],
    ['Fälligkeit',z=>h('span',{class:'num',text:z.produkt.faellig?L.dFull(z.produkt.faellig):'–'})],
    ['Beobachtung',z=>{const f=z.fortschritt||{};return h('span',{class:'num',text:num(f.tag)!=null&&num(f.tage_gesamt)?`Tag ${fmt(f.tag,0)} von ${fmt(f.tage_gesamt,0)}`:'–'});}],
    ['Letzter Tag',z=>{const t=L.letzterTag(z);if(!t)return '–';const sp=arr(t.spruenge).filter(x=>x&&num(x.pct)!=null);
      return sp.length?h('span',{class:'jump',text:'Sprung'}):t.auffaellig===true?h('span',{class:'muted',text:'auffällig'}):h('span',{class:'muted',text:'unauffällig'});}],
    ['Abruf',z=>z.status&&z.status.ok===false?h('span',{class:'down',text:'gestört'}):h('span',{class:'muted',text:'ok'})],
  ];
  function uebersicht(ziel){
    const kopf=h('div',{class:'ovhead'},h('h1',{text:'Übersicht'}),
      h('p',{class:'sub',text:`${Z.length} ${Z.length===1?'Zertifikat':'Zertifikate'}, Stand ${tStand(G.stand)}`}));
    const teile=[kopf];
    const fehler=Z.filter(z=>z.status&&z.status.ok===false);
    if(fehler.length)teile.push(h('div',{class:'warn',role:'alert'},h('b',{text:'Abruf gestört: '}),
      fehler.map(z=>L.kurzname(z.produkt)).join(', ')+'. Die Kurse dieser Zertifikate können veraltet sein.'));
    const dax=Z.map(L.letzterTag).find(t=>t&&num(t.dax)!=null);
    if(dax)teile.push(h('p',{class:'daxline'},'DAX ',h('b',{class:'num',text:fmt(dax.dax,0)}),' ',chg(dax.dax_pct),h('span',{class:'muted',text:' am '+L.dShort(dax.datum)})));
    const thead=h('thead',null,h('tr',null,h('th',{scope:'col'},h('span',{class:'sr',text:'Kennzahl'})),
      Z.map(z=>h('th',{scope:'col'},h('a',{href:zuZ(z.produkt.isin),class:'zlink'},L.kurzname(z.produkt)),
        h('small',null,str(z.produkt.wkn)||z.produkt.isin,z.produkt.demo===true?' · Beispiel':'')))));
    const tb=h('tbody',null,ZEILEN.map(([titel,f])=>h('tr',null,h('th',{scope:'row',text:titel}),Z.map(z=>h('td',null,f(z))))));
    teile.push(h('div',{class:'ovw',tabindex:'0',role:'region','aria-label':'Vergleichstabelle, seitlich scrollbar'},h('table',{class:'ov'},thead,tb)));
    teile.push(h('p',{class:'note',text:'Tippe auf ein Zertifikat für Chart, Tagesanalyse und Wochenkurse. Neue Zertifikate fügst du unter „Suchen“ hinzu.'}));
    teile.push(h('footer',null,h('div',{text:'Stand: '+tStand(G.stand)}),
      h('div',null,'Alle Kurse als Excel (Übersicht und je Zertifikat ein Blatt): ',h('a',{href:'kurse.xlsx',download:'kurse.xlsx',text:'kurse.xlsx'}),'.'),
      h('div',{text:'Quellen: onvista (Kurse), Google News (Schlagzeilen). Regelbasierte Auswertung ohne KI. Keine Anlageberatung.'})));
    ziel.append(...teile);
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
        e?h('a',{class:'lnk',href:e,target:'_blank',rel:'noopener noreferrer',text:'Entfernen'}):null);
    }
    function karte(v){
      const voll=Z.length>=L.MAX_ZERTIFIKATE, url=L.issueUrl(repo,'hinzufügen',v.isin);
      const fakten=[['WKN',v.wkn],['ISIN',v.isin],['Emittent',v.emittent],['Basiswert',v.basis],['Cap',eur(v.cap)],
        ['Fällig',v.faellig?L.dFull(v.faellig):'–'],['Geld / Brief',eur(v.geld)+' / '+eur(v.brief)]];
      return h('div',{class:'card'},h('h3',{text:v.name||'Discount-Zertifikat'}),
        h('dl',{class:'facts'},fakten.map(([k,w])=>h('div',null,h('dt',{text:k}),h('dd',{class:'num',text:str(w)||'–'})))),
        voll?h('p',{class:'warn',text:`Es werden schon ${L.MAX_ZERTIFIKATE} Zertifikate verfolgt. Erst eines entfernen.`})
          :url?h('a',{class:'btn',href:url,target:'_blank',rel:'noopener noreferrer',text:'Über GitHub hinzufügen'}):h('p',{class:'note',text:'Kein Repo hinterlegt, Hinzufügen nicht möglich.'}),
        h('p',{class:'note',text:'Kurse: onvista, Stand jetzt. Der Tracker verfolgt ab heute 10 Wochen.'}));
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
      const knopf=h('button',{type:'button',class:'btn',text:`${k.wert} bei onvista nachsehen`});
      knopf.addEventListener('click',()=>pruefe(k,knopf));
      neu.replaceChildren(knopf);
    }
    eingabe.addEventListener('input',render);
    eingabe.addEventListener('keydown',e=>{if(e.key==='Enter'){const b=neu.querySelector('button');if(b){e.preventDefault();b.click();}}});
    ziel.append(h('div',{class:'ovhead'},h('h1',{text:'Suchen und hinzufügen'})),
      h('label',{class:'srch',for:'q'},h('span',{class:'sr',text:'Suche'}),eingabe),
      h('p',{class:'sub',id:'qhint',text:'Durchsucht die verfolgten Zertifikate. Mit WKN oder ISIN auch neue Discount-Zertifikate.'}),
      h('section',null,ergebnis),h('section',null,h('h2',{text:'Neu hinzufügen'}),neu),
      h('section',{class:'how'},h('h2',{text:'So funktioniert das Hinzufügen'}),h('ol',null,
        h('li',{text:'WKN oder ISIN eingeben und bei onvista nachsehen.'}),
        h('li',{text:'„Über GitHub hinzufügen“ öffnet ein vorbereitetes Issue. Dafür bei GitHub angemeldet sein, dann absenden.'}),
        h('li',{text:'Der Tracker prüft das Zertifikat, holt die Kurse und baut die App neu. Nach etwa 2 Minuten neu laden.'}))));
    render();
    return ()=>{if(abbruch)abbruch.abort();};
  }

  addEventListener('hashchange',()=>{zeige();scrollTo(0,0);});
  if(Z.length===1&&!location.hash)history.replaceState(null,'',zuZ(Z[0].produkt.isin));
  zeige();
}
starteApp(DATEN);
