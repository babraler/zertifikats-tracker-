// Reine Logik ohne DOM: Formatierung, Suche, Routen, Links. Wird von seite.py in index.html eingebettet
// und in logik.test.mjs mit node:test geprüft.
const LOGIK = (() => {
  'use strict';
  const ONVISTA = 'https://api.onvista.de/api/v1';
  const MAX_ZERTIFIKATE = 10;          // wie tracker/konfig.py
  const ISIN_RE = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;
  const WKN_RE = /^[A-Z0-9]{6}$/;
  const REPO_RE = /^[A-Za-z0-9-]{1,39}\/[A-Za-z0-9._-]{1,100}$/;
  const AKTIONEN = ['hinzufügen', 'entfernen'];

  const num = x => (typeof x === 'number' && isFinite(x)) ? x : null;
  const str = x => typeof x === 'string' ? x : '';
  const arr = x => Array.isArray(x) ? x : [];

  const F = {};
  function fmt(x, d = 2, sign = false) {
    x = num(x); if (x == null) return '–';
    const k = d + (sign ? 's' : '');
    if (!F[k]) F[k] = new Intl.NumberFormat('de-DE', {minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: sign ? 'exceptZero' : 'auto'});
    return F[k].format(x);
  }
  const eur = (x, d = 2, sign = false) => num(x) == null ? '–' : fmt(x, d, sign) + ' €';
  const pct = (x, sign = true) => num(x) == null ? '–' : fmt(x, 2, sign) + ' %';

  const WT = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  function pd(iso) { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str(iso)); return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null; }
  function dShort(iso) { const d = pd(iso); return d ? String(d.getUTCDate()).padStart(2, '0') + '.' + String(d.getUTCMonth() + 1).padStart(2, '0') + '.' : '–'; }
  function dFull(iso) { const d = pd(iso); return d ? dShort(iso) + d.getUTCFullYear() : '–'; }
  function dLong(iso) { const d = pd(iso); return d ? WT[d.getUTCDay()] + ', ' + dFull(iso) : '–'; }
  function tZeit(iso) {
    const d = new Date(str(iso)); if (isNaN(d)) return '';
    return new Intl.DateTimeFormat('de-DE', {timeZone: 'Europe/Berlin', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'}).format(d) + ' Uhr';
  }
  function tStand(iso) {
    const d = new Date(str(iso)); if (isNaN(d)) return '–';
    return new Intl.DateTimeFormat('de-DE', {timeZone: 'Europe/Berlin', dateStyle: 'medium', timeStyle: 'short'}).format(d) + ' Uhr';
  }
  function safeUrl(u) { try { const x = new URL(str(u)); return x.protocol === 'https:' ? x.href : null; } catch (e) { return null; } }

  /* ---------- Kennungen ---------- */
  // ISIN-Prüfziffer: Buchstaben → Zahlen (A=10), dann Luhn über alle Ziffern.
  function isinGueltig(isin) {
    if (!ISIN_RE.test(isin)) return false;
    const ziffern = isin.split('').map(c => /[A-Z]/.test(c) ? String(c.charCodeAt(0) - 55) : c).join('');
    let summe = 0;
    for (let i = 0; i < ziffern.length; i++) {
      let z = +ziffern[ziffern.length - 1 - i];
      if (i % 2 === 1) { z *= 2; if (z > 9) z -= 9; }
      summe += z;
    }
    return summe % 10 === 0;
  }
  /** Freitext → {art:'isin'|'wkn', wert} oder null. Leerzeichen und Kleinschreibung zählen nicht. */
  function erkenne(eingabe) {
    const w = str(eingabe).replace(/\s+/g, '').toUpperCase();
    if (w.length === 12 && isinGueltig(w)) return {art: 'isin', wert: w};
    if (WKN_RE.test(w)) return {art: 'wkn', wert: w};
    return null;
  }
  function snapshotUrl(k) {
    if (!k || !(k.art === 'isin' ? isinGueltig(k.wert) : WKN_RE.test(str(k.wert)))) return null;
    return `${ONVISTA}/derivatives/${k.art.toUpperCase()}:${k.wert}/snapshot`;
  }

  /* ---------- Suche in den verfolgten Zertifikaten ---------- */
  function suchtext(z) {
    const p = (z && z.produkt) || {};
    return [p.name, p.isin, p.wkn, p.basis_name, p.emittent].map(str).join(' ').toUpperCase();
  }
  function filtere(liste, q) {
    const woerter = str(q).toUpperCase().split(/\s+/).filter(Boolean);
    return arr(liste).filter(z => { const t = suchtext(z); return woerter.every(w => t.includes(w)); });
  }
  function verfolgt(liste, k) {
    if (!k) return null;
    const feld = k.art === 'isin' ? 'isin' : 'wkn';
    return arr(liste).find(z => str(z && z.produkt && z.produkt[feld]).toUpperCase() === k.wert) || null;
  }

  /* ---------- onvista-Vorschau (gleiche Regeln wie onvista.parse_zertifikat) ---------- */
  function vorschau(d) {
    try {
      const sub = d.derivativesDetails.derivativesSubCategory.entitySubType;
      if (sub !== 'DISCOUNT_CERTIFICATE') return {fehler: 'Das ist kein Discount-Zertifikat.'};
      const u = d.derivativesUnderlyingList.list[0], inst = d.instrument, q = d.quote || {};
      const caps = arr(u.derivativesBarrierList && u.derivativesBarrierList.list).filter(b => b && b.typeBarrier === 'CAP');
      const isin = str(inst.isin);
      if (!isinGueltig(isin)) return {fehler: 'onvista liefert keine gültige ISIN.'};
      return {
        isin, wkn: str(inst.wkn), name: str(inst.name), emittent: str(d.derivativesIssuer && d.derivativesIssuer.name),
        basis: str(u.instrument && u.instrument.name), cap: caps.length ? num(caps[0].barrier) : null,
        faellig: str(d.derivativesDetails.datetimeMaturity).slice(0, 10) || null,
        geld: num(q.bid), brief: num(q.ask),
      };
    } catch (e) {
      return {fehler: 'Die Antwort von onvista hat einen unerwarteten Aufbau.'};
    }
  }

  /* ---------- Verwalten über GitHub-Issues ---------- */
  function issueUrl(repo, aktion, kennung) {
    const k = erkenne(kennung);
    if (!REPO_RE.test(str(repo)) || !AKTIONEN.includes(aktion) || !k) return null;
    const titel = `Zertifikat ${aktion}: ${k.wert}`;
    const text = aktion === 'hinzufügen'
      ? 'Bitte dieses Discount-Zertifikat ab heute verfolgen (10 Wochen).\n\nNur absenden, den Rest erledigt der Tracker. Das Ergebnis steht danach hier als Kommentar.'
      : 'Bitte dieses Zertifikat nicht mehr verfolgen. Die bisherigen Kurse bleiben im Repo gespeichert.\n\nNur absenden, den Rest erledigt der Tracker.';
    return `https://github.com/${repo}/issues/new?title=${encodeURIComponent(titel)}&body=${encodeURIComponent(text)}`;
  }

  /* ---------- Routen ---------- */
  function route(hash, isins) {
    const h = str(hash).replace(/^#\/?/, '');
    if (h === 'suche') return {seite: 'suche'};
    const m = /^z\/([A-Z0-9]{12})$/.exec(h);
    if (m && arr(isins).includes(m[1])) return {seite: 'zertifikat', isin: m[1]};
    return {seite: 'uebersicht'};
  }

  /* ---------- Übersicht ---------- */
  function kurzname(p) {
    p = p || {};
    const b = str(p.basis_name), c = num(p.cap);
    if (b && c != null) return `${b} ${fmt(c, c % 1 ? 2 : 0)}`;
    return b || str(p.wkn) || str(p.isin) || 'Zertifikat';
  }
  function letzterTag(z) {
    const t = arr(z && z.tage);
    for (let i = t.length - 1; i >= 0; i--) if (t[i] && num(t[i].z_geld) != null) return t[i];
    return null;
  }
  /** Geldkurse ab Laufbeginn (ohne Lücken) für die kleine Verlaufslinie. */
  function verlauf(z) {
    return arr(z && z.tage).filter(t => t && t.phase === 'lauf').map(t => num(t.z_geld)).filter(v => v != null);
  }
  function sparkPfad(werte, w, h, rand = 2) {
    const v = arr(werte).filter(x => num(x) != null);
    if (v.length < 2) return '';
    const lo = Math.min(...v), hi = Math.max(...v), sp = hi - lo || 1;
    return v.map((x, i) => (i ? 'L' : 'M') + (rand + (w - 2 * rand) * i / (v.length - 1)).toFixed(1) + ' ' +
      (h - rand - (h - 2 * rand) * (x - lo) / sp).toFixed(1)).join(' ');
  }

  return {MAX_ZERTIFIKATE, num, str, arr, fmt, eur, pct, WT, pd, dShort, dFull, dLong, tZeit, tStand, safeUrl,
    isinGueltig, erkenne, snapshotUrl, filtere, verfolgt, vorschau, issueUrl, route, kurzname, letzterTag, verlauf, sparkPfad};
})();
if (typeof module !== 'undefined') module.exports = LOGIK;
