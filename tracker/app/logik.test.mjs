// Tests für logik.js. Start: node --test tracker/app/
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';

const L = createRequire(import.meta.url)('./logik.js');

const Z = (isin, wkn, name, basis, extra = {}) => ({produkt: {isin, wkn, name, basis_name: basis, emittent: 'J.P. Morgan', cap: 142.5}, ...extra});
const LISTE = [Z('DE000JE3NTM6', 'JE3NTM', 'Discount auf SAP', 'SAP'), Z('DE0007164600', 'ABC123', 'Discount auf Allianz', 'Allianz')];

test('ISIN-Prüfziffer', () => {
  for (const ok of ['DE000JE3NTM6', 'DE0007164600', 'DE0008469008', 'US0378331005']) assert.ok(L.isinGueltig(ok), ok);
  for (const falsch of ['DE000JE3NTM7', 'DE00JE3NTM6', 'de000je3ntm6', '', 'DE000JE3NTMX']) assert.ok(!L.isinGueltig(falsch), falsch);
});

test('erkenne: ISIN, WKN, Freitext', () => {
  assert.deepEqual(L.erkenne(' de000je3ntm6 '), {art: 'isin', wert: 'DE000JE3NTM6'});
  assert.deepEqual(L.erkenne('je3 ntm'), {art: 'wkn', wert: 'JE3NTM'});
  assert.equal(L.erkenne('SAP'), null);
  assert.equal(L.erkenne('DE000JE3NTM7'), null); // falsche Prüfziffer
  assert.equal(L.erkenne(null), null);
});

test('snapshotUrl nur für gültige Kennungen', () => {
  assert.equal(L.snapshotUrl(L.erkenne('JE3NTM')), 'https://api.onvista.de/api/v1/derivatives/WKN:JE3NTM/snapshot');
  assert.equal(L.snapshotUrl(L.erkenne('DE000JE3NTM6')), 'https://api.onvista.de/api/v1/derivatives/ISIN:DE000JE3NTM6/snapshot');
  assert.equal(L.snapshotUrl({art: 'wkn', wert: '../x/a'}), null);
  assert.equal(L.snapshotUrl(null), null);
});

test('filtere sucht in Name, ISIN, WKN und Basiswert, alle Wörter', () => {
  assert.deepEqual(L.filtere(LISTE, 'sap').map(z => z.produkt.wkn), ['JE3NTM']);
  assert.deepEqual(L.filtere(LISTE, 'discount allianz').map(z => z.produkt.wkn), ['ABC123']);
  assert.equal(L.filtere(LISTE, '').length, 2);
  assert.equal(L.filtere(LISTE, 'xyz').length, 0);
  assert.equal(L.filtere(null, 'x').length, 0);
});

test('verfolgt findet per ISIN und WKN', () => {
  assert.equal(L.verfolgt(LISTE, L.erkenne('je3ntm')).produkt.isin, 'DE000JE3NTM6');
  assert.equal(L.verfolgt(LISTE, L.erkenne('DE0007164600')).produkt.wkn, 'ABC123');
  assert.equal(L.verfolgt(LISTE, L.erkenne('ZZZ999')), null);
});

const SNAP = {
  instrument: {isin: 'DE000JE3NTM6', wkn: 'JE3NTM', name: 'DISCOUNT CERTIFICATE AUF SAP SE'},
  derivativesIssuer: {name: 'J.P. Morgan'},
  derivativesDetails: {derivativesSubCategory: {entitySubType: 'DISCOUNT_CERTIFICATE'}, datetimeMaturity: '2027-03-19T00:00:00.000+01:00'},
  derivativesUnderlyingList: {list: [{instrument: {name: 'SAP'}, derivativesBarrierList: {list: [{typeBarrier: 'CAP', barrier: 142.5}]}}]},
  quote: {bid: 140.17, ask: 140.67},
};

test('vorschau liest den onvista-Snapshot', () => {
  assert.deepEqual(L.vorschau(SNAP), {isin: 'DE000JE3NTM6', wkn: 'JE3NTM', name: 'DISCOUNT CERTIFICATE AUF SAP SE',
    emittent: 'J.P. Morgan', basis: 'SAP', cap: 142.5, faellig: '2027-03-19', geld: 140.17, brief: 140.67});
});

test('vorschau lehnt anderes ab', () => {
  const bonus = structuredClone(SNAP); bonus.derivativesDetails.derivativesSubCategory.entitySubType = 'BONUS_CERTIFICATE';
  assert.match(L.vorschau(bonus).fehler, /kein Discount/);
  assert.ok(L.vorschau({}).fehler);
  assert.ok(L.vorschau(null).fehler);
  const kaputt = structuredClone(SNAP); kaputt.instrument.isin = '<img>';
  assert.ok(L.vorschau(kaputt).fehler);
});

test('issueUrl baut einen vorbereiteten Issue-Link', () => {
  const u = new URL(L.issueUrl('babraler/zertifikats-tracker-', 'hinzufügen', 'je3ntm'));
  assert.equal(u.origin + u.pathname, 'https://github.com/babraler/zertifikats-tracker-/issues/new');
  assert.equal(u.searchParams.get('title'), 'Zertifikat hinzufügen: JE3NTM');
  assert.match(u.searchParams.get('body'), /absenden/);
  assert.equal(new URL(L.issueUrl('a/b', 'entfernen', 'DE000JE3NTM6')).searchParams.get('title'), 'Zertifikat entfernen: DE000JE3NTM6');
});

test('issueUrl verweigert Unsinn', () => {
  assert.equal(L.issueUrl('../evil', 'hinzufügen', 'JE3NTM'), null);
  assert.equal(L.issueUrl('a/b', 'löschen', 'JE3NTM'), null);
  assert.equal(L.issueUrl('a/b', 'hinzufügen', 'SAP AG'), null);
  assert.equal(L.issueUrl(null, 'hinzufügen', 'JE3NTM'), null);
});

test('route: ein Zertifikat je Ansicht, sonst das Startzertifikat', () => {
  const isins = ['DE000JE3NTM6', 'DE0007164600'];
  const z = isin => ({seite: 'zertifikat', isin});
  assert.deepEqual(L.route('#/z/DE0007164600', isins, 'DE000JE3NTM6'), z('DE0007164600'));
  assert.deepEqual(L.route('#/z/US0378331005', isins, 'DE000JE3NTM6'), z('DE000JE3NTM6'));   // nicht verfolgt
  assert.deepEqual(L.route('#/suche', isins, 'DE000JE3NTM6'), {seite: 'suche'});
  assert.deepEqual(L.route('', isins, 'DE0007164600'), z('DE0007164600'));
  assert.deepEqual(L.route('#/', isins, 'DE0007164600'), z('DE0007164600'));
  assert.deepEqual(L.route('#/z/<script>', isins, 'DE000JE3NTM6'), z('DE000JE3NTM6'));
  assert.deepEqual(L.route('#/', [], null), {seite: 'suche'});
  assert.deepEqual(L.route('#/z/de0007164600', isins, 'DE000JE3NTM6'), z('DE0007164600'));   // klein geschrieben
});

test('startIsin: gemerktes Zertifikat, sonst das erste', () => {
  const isins = ['DE000JE3NTM6', 'DE0007164600'];
  assert.equal(L.startIsin(isins, 'DE0007164600'), 'DE0007164600');
  assert.equal(L.startIsin(isins, 'US0378331005'), 'DE000JE3NTM6');   // nicht mehr verfolgt
  assert.equal(L.startIsin(isins, null), 'DE000JE3NTM6');
  assert.equal(L.startIsin([], 'DE000JE3NTM6'), null);
});

test('teilenUrl zeigt direkt auf ein Zertifikat', () => {
  assert.equal(L.teilenUrl('https://babraler.github.io/zertifikats-tracker-/?v=1#/suche', 'DE000JE3NTM6'),
    'https://babraler.github.io/zertifikats-tracker-/#/z/DE000JE3NTM6');
  assert.equal(L.teilenUrl('https://x.de/a/', 'kaputt'), null);
});

test('anfrageText für den Betreiber', () => {
  const t = L.anfrageText({isin: 'DE000JE3NTM6', wkn: 'JE3NTM', name: 'Discount auf SAP'});
  assert.match(t, /JE3NTM/);
  assert.match(t, /DE000JE3NTM6/);
  assert.match(t, /in den Tracker auf/);
});

test('kurzname', () => {
  assert.equal(L.kurzname({basis_name: 'SAP', cap: 142.5}), 'SAP 142,50');
  assert.equal(L.kurzname({basis_name: 'SAP', cap: 140}), 'SAP 140');
  assert.equal(L.kurzname({wkn: 'JE3NTM'}), 'JE3NTM');
});

test('Formatierung deutsch', () => {
  assert.equal(L.eur(1234.5), '1.234,50 €');
  assert.equal(L.pct(-1.234), '-1,23 %');
  assert.equal(L.pct(null), '–');
  assert.equal(L.dFull('2026-11-13'), '13.11.2026');
  assert.equal(L.dLong('2026-11-13'), 'Fr, 13.11.2026');
  assert.equal(L.safeUrl('javascript:alert(1)'), null);
});
