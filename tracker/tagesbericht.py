"""Tagesbericht je Handelstag: was geschah mit Zertifikat, Aktie und DAX, welche Schlagzeilen gab es dazu.

Regelbasiert, ohne LLM. Gespeichert in daten/<ISIN>/tagesberichte.json (ein Eintrag je Datum, wird nie gelöscht)
und lesbar als daten/<ISIN>/tagesberichte.md. Schlagzeilen zeigen einen zeitlichen Zusammenhang, keinen Beweis.
"""
import json
from datetime import date
from pathlib import Path

from tracker import speicher
from tracker.analyse import de
from tracker.nachrichten import _name_im_titel, ordne_ein, passt

# Quelle: SPEC.md, Abschnitt "Tagesbericht"
TOP_JE_GRUPPE = 3
WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
HINWEIS = "Zeitlicher Zusammenhang, kein Beweis."
RICHTUNG_TEXT = {"positiv": "eher positiv", "negativ": "eher negativ"}


def _einordnen(roh, gruppe, tag):
    """Kategorie, Richtung und ob die Richtung zur Bewegung passt (Markt → DAX, Unternehmen → Aktie ohne Markt)."""
    kat, richtung = ordne_ein(roh["titel"])
    bezug = "Makro" if gruppe == "markt" else kat
    p = passt(bezug, richtung, tag.get("aktie_spez_pct"), tag.get("dax_pct"))
    return dict(roh, kategorie=kat, richtung=richtung, passt=p)


def _punkte(n, gruppe, basis_name):
    """Unternehmen: Name im Titel, echte Kategorie. Markt: DAX im Titel, Makro. Gegenläufiges rutscht nach hinten."""
    if gruppe == "markt":
        basis = _name_im_titel("DAX", n["titel"]) + 2 * (n["kategorie"] == "Makro")
    else:
        basis = _name_im_titel(basis_name, n["titel"]) + (n["kategorie"] != "Sonstiges")
    return basis + (n["passt"] is True) - (n["passt"] is False) + (n["richtung"] != "neutral")


def _rangfolge(liste, gruppe, basis_name):
    return sorted(liste, key=lambda n: (_punkte(n, gruppe, basis_name), n.get("zeit") or ""),
                  reverse=True)[:TOP_JE_GRUPPE]


def gruppiere(roh, tag, basis_name):
    """Schlagzeilen in „unternehmen“ (Basiswert im Titel) und „markt“ (übrige, meist aus der DAX-Abfrage)."""
    unternehmen, markt = [], []
    for r in roh or []:
        if not r.get("titel"):
            continue
        if _name_im_titel(basis_name, r["titel"]):
            unternehmen.append(_einordnen(r, "unternehmen", tag))
        else:
            markt.append(_einordnen(r, "markt", tag))
    return _rangfolge(unternehmen, "unternehmen", basis_name), _rangfolge(markt, "markt", basis_name)


def _datum_lang(datum):
    d = date.fromisoformat(datum)
    return f"{WOCHENTAGE[d.weekday()]}, {d.day:02d}.{d.month:02d}.{d.year}"


def _satz_kurse(t, name):
    if t.get("dz") is None:
        return "Ohne Vortag oder mit unvollständigen Kursen lässt sich die Bewegung nicht vergleichen."
    return (f"Zertifikat {de(t['z_pct'], 2, True)} % ({de(t['dz'], 2, True)} €), "
            f"{name}-Aktie {de(t['basis_pct'], 2, True)} %, DAX {de(t['dax_pct'], 2, True)} %.")


def _satz_einordnung(t):
    teile = []
    if t.get("haupttreiber"):
        teile.append(f"Haupttreiber beim Zertifikat: {t['haupttreiber']}")
    if t.get("verdikt"):
        teile.append(f"Einordnung: {t['verdikt']}")
    spr = [f"{s['wert']} {de(s['pct'], 2, True)} %" for s in t.get("spruenge") or []]
    if spr:
        teile.append("Kurssprung: " + ", ".join(spr))
    return "; ".join(teile) + "." if teile else ""


def _meldung(n, bewegung):
    zusatz = [x for x in (n.get("quelle"), n["kategorie"] if n["kategorie"] != "Sonstiges" else None,
                          RICHTUNG_TEXT.get(n["richtung"])) if x]
    if n["passt"] is True:
        zusatz.append(f"passt zur Bewegung {bewegung}")
    elif n["passt"] is False:
        zusatz.append(f"läuft gegen die Bewegung {bewegung}")
    return f"„{n['titel']}“" + (f" ({', '.join(zusatz)})" if zusatz else "")


def _wahl(liste):
    """Für den Satz die erste Meldung, die nicht gegen die Bewegung läuft (sonst die erste)."""
    return next((n for n in liste if n["passt"] is not False), liste[0])


def _satz_news(unternehmen, markt, name, abgerufen):
    if not abgerufen:
        return "Für diesen Tag wurden keine Schlagzeilen abgerufen."
    saetze = [f"Zu {name}: " + _meldung(_wahl(unternehmen), "der Aktie ohne Markteinfluss") + "." if unternehmen
              else f"Zu {name} gab es keine Schlagzeile im Zeitraum.",
              "Gesamtmarkt: " + _meldung(_wahl(markt), "des DAX") + "." if markt
              else "Zum Gesamtmarkt gab es keine Schlagzeile im Zeitraum."]
    return " ".join(saetze)


def erstelle(tag, roh, basis_name):
    """Ein Tagesbericht aus einem Tag von daten.json (mit Analyse) und den gespeicherten Schlagzeilen des Tages.

    roh = None heißt: für den Tag wurden keine Schlagzeilen abgerufen; [] heißt: abgerufen, keine gefunden.
    """
    name = basis_name or "Basiswert"
    unternehmen, markt = gruppiere(roh, tag, basis_name)
    text = " ".join(s for s in (_satz_kurse(tag, name), _satz_einordnung(tag),
                                _satz_news(unternehmen, markt, name, roh is not None)) if s)
    felder = ("z_geld", "basis", "dax", "z_pct", "basis_pct", "dax_pct", "dz", "haupttreiber", "verdikt", "auffaellig")
    return {"datum": tag["datum"], "phase": tag.get("phase"), "zusammenfassung": text,
            "kurse": {k: tag.get(k) for k in felder}, "spruenge": tag.get("spruenge") or [],
            "nachrichten_unternehmen": unternehmen, "nachrichten_markt": markt,
            "nachrichten_gesamt": len(roh or []), "hinweis": HINWEIS}


def berichte(tage, news_roh, basis_name):
    """Berichte für alle Tage im Lauf und für Vorlauftage, zu denen Schlagzeilen gespeichert sind."""
    return {t["datum"]: erstelle(t, news_roh.get(t["datum"]), basis_name)
            for t in tage if t.get("phase") == "lauf" or t["datum"] in news_roh}


def lies(pfad):
    obj = speicher.lies_meta(pfad)
    return {k: v for k, v in obj.items() if isinstance(v, dict)} if isinstance(obj, dict) else {}


def _md_text(s):
    """Fremde Schlagzeilen ohne Markdown-/HTML-Wirkung (Links, Fett, eingebettetes HTML)."""
    for z in ("\\", "[", "]", "*", "_", "`", "<", ">", "|"):
        s = s.replace(z, "\\" + z)
    return s


def _zeit_kurz(zeit):
    """ISO-Zeit → „19.11. 20:50“ (Datum dabei, weil das Fenster am Vorabend beginnt)."""
    z = str(zeit or "")
    return f"{z[8:10]}.{z[5:7]}. {z[11:16]}" if len(z) >= 16 else None


def _md_zeile(n):
    url = n.get("url") if str(n.get("url") or "").startswith("https://") else None
    titel = _md_text(n["titel"])
    kopf = f"[{titel}]({url.replace(')', '%29')})" if url else titel
    rest = [x for x in (n.get("quelle"), _zeit_kurz(n.get("zeit")), n.get("kategorie"),
                        RICHTUNG_TEXT.get(n.get("richtung"))) if x]
    return f"- {kopf}" + (f" ({_md_text(', '.join(rest))})" if rest else "")


def als_markdown(alle, titel, basis_name):
    zeilen = [f"# Tagesberichte: {_md_text(titel)}", "",
              f"Automatisch erstellt, regelbasiert. {HINWEIS}", ""]
    for d in sorted(alle, reverse=True):
        b = alle[d]
        zeilen += [f"## {_datum_lang(d)}", "", _md_text(b.get("zusammenfassung") or ""), ""]
        for schluessel, kopf in (("nachrichten_unternehmen", f"Schlagzeilen zu {basis_name or 'Basiswert'}"),
                                 ("nachrichten_markt", "Schlagzeilen zum Markt")):
            liste = b.get(schluessel) or []
            if liste:
                zeilen += [f"**{_md_text(kopf)}**", ""] + [_md_zeile(n) for n in liste] + [""]
    return "\n".join(zeilen).rstrip() + "\n"


def speichere(ordner, neue, titel, basis_name):
    """Neue Berichte mit den gespeicherten zusammenführen (gleiches Datum wird aktualisiert, nichts gelöscht)."""
    ordner = Path(ordner)
    alle = lies(ordner / "tagesberichte.json")
    alle.update(neue)
    alle = {d: alle[d] for d in sorted(alle)}
    text = json.dumps(alle, ensure_ascii=False, indent=1) + "\n"
    geaendert = speicher._atomar_schreiben(ordner / "tagesberichte.json", text.encode("utf-8"))
    speicher._atomar_schreiben(ordner / "tagesberichte.md", als_markdown(alle, titel, basis_name).encode("utf-8"))
    return geaendert
