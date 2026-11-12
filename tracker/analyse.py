"""Erklärung der Kursänderungen ohne LLM: Beta, Zerlegung in Effekte, Auffälligkeit, Text.

Reine Funktionen, keine Dateien, kein Netz.
"""
import statistics
from datetime import date

# Quelle: SPEC.md, Abschnitt "Analyse"
FENSTER = 60            # Tage für Beta und Streuung
MIN_PUNKTE = 20         # darunter: Beta 1,0 bzw. kein z-Wert
SCHWELLE_Z = 1.5        # ab diesem z-Wert gilt ein Tag als auffällig
DELTA_NAEHERUNG = 0.5   # wenn Delta nirgends bekannt ist
DELTA_KLEIN = 0.15      # darunter: Aktienbewegungen kommen kaum an (Näherung, Annahme)
TREIBER = {"markt": "DAX-Bewegung", "aktie": "Aktie selbst", "zeit": "Zeitwert",
           "rest": "Sonstiges (Spread, Vola, Zinsen)"}
MINUS = "−"
LEER_FELDER = ("z_pct", "basis_pct", "dax_pct", "dz", "delta", "delta_geschaetzt", "beta", "beta_geschaetzt",
               "effekt_basis", "effekt_markt", "effekt_aktie", "effekt_zeit", "effekt_rest", "haupttreiber",
               "aktie_spez_pct", "auffaellig", "z_score", "cap_abstand_pct")


def de(wert, stellen=2, vorzeichen=False):
    """Zahl deutsch formatiert (Tausenderpunkt, Dezimalkomma, echtes Minus)."""
    if wert is None:
        return "unbekannt"
    s = f"{wert:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if float(s.replace(".", "").replace(",", ".")) == 0:
        return s.lstrip("-")
    if s.startswith("-"):
        return MINUS + s[1:]
    return "+" + s if vorzeichen else s


def cap_abstand_pct(basis, cap):
    if basis is None or not cap:
        return None
    return (basis - cap) / cap * 100


def _vollstaendig(z):
    return all(z.get(c) is not None and z[c] > 0 for c in ("z_geld", "basis", "dax"))


def _rendite(neu, alt):
    return neu / alt - 1 if alt else None


def _beta(punkte):
    """Steigung der Regression Basiswert~DAX über (dax, basis)-Renditen. None bei zu wenig Punkten."""
    if len(punkte) < MIN_PUNKTE:
        return None
    mx = sum(p[0] for p in punkte) / len(punkte)
    my = sum(p[1] for p in punkte) / len(punkte)
    var = sum((p[0] - mx) ** 2 for p in punkte)
    if var <= 1e-18:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in punkte) / var


def _renditen(rows):
    """Je Zeile (dax_ret, basis_ret) oder None, wenn Zeile oder Vortag unvollständig."""
    erg = [None]
    for i in range(1, len(rows)):
        a, b = rows[i - 1], rows[i]
        if _vollstaendig(a) and _vollstaendig(b):
            erg.append((_rendite(b["dax"], a["dax"]), _rendite(b["basis"], a["basis"])))
        else:
            erg.append(None)
    return erg


def _bekannt(rows, i, feld, auch_spaeter):
    if rows[i].get(feld) is not None:
        return rows[i][feld]
    for j in range(i - 1, -1, -1):
        if rows[j].get(feld) is not None:
            return rows[j][feld]
    if auch_spaeter:
        for j in range(i + 1, len(rows)):
            if rows[j].get(feld) is not None:
                return rows[j][feld]
    return None


def _betas_und_ar(ren):
    """Beta je Tag (aus den bis zu 60 Beobachtungen davor) und aktienspezifische Rendite je Tag."""
    betas, ars = [], []
    for i, r in enumerate(ren):
        davor = [p for p in ren[:i] if p is not None][-FENSTER:]
        b = _beta(davor)
        betas.append((b if b is not None else 1.0, b is None))
        ars.append(None if r is None else r[1] - betas[-1][0] * r[0])
    return betas, ars


def _z_score(ars, i):
    davor = [a for a in ars[:i] if a is not None][-FENSTER:]
    if ars[i] is None or len(davor) < MIN_PUNKTE:
        return None
    sd = statistics.stdev(davor)
    return ars[i] / sd if sd > 1e-12 else None


def _treiber(e):
    name = max(TREIBER, key=lambda k: abs(e[k]))
    return TREIBER[name], e[name]


def _leerer_tag(datum, text):
    t = dict.fromkeys(LEER_FELDER)
    t.update(datum=datum, text=text)
    return t


def analysiere(rows, bezug=1.0, cap=None, basis_name=None):
    """rows: nach Datum sortierte Zeilen (Liste von Dicts). Rückgabe: je Zeile ein Analyse-Dict."""
    ren = _renditen(rows)
    betas, ars = _betas_und_ar(ren)
    erg = []
    for i, z in enumerate(rows):
        if ren[i] is None:
            erg.append(_leerer_tag(z["datum"], "Erster Tag der Aufzeichnung, noch kein Vergleich mit dem Vortag."
                                   if i == 0 else "Für diesen Tag fehlen Kurse von ihm oder vom Vortag, daher keine Erklärung."))
            continue
        erg.append(_tag(rows, i, ren[i], betas[i], ars[i], _z_score(ars, i), bezug, cap, basis_name))
    return erg


def _tag(rows, i, ren, beta, ar, zs, bezug, cap, basis_name):
    t, v = rows[i], rows[i - 1]
    delta = _bekannt(rows, i, "delta", True)
    d_gesch = delta is None
    delta = DELTA_NAEHERUNG if d_gesch else delta
    theta = _bekannt(rows, i, "theta_tag", False) or 0.0
    tage = (date.fromisoformat(t["datum"]) - date.fromisoformat(v["datum"])).days
    dz = t["z_geld"] - v["z_geld"]
    e = {"basis": delta * bezug * (t["basis"] - v["basis"]),
         "markt": delta * bezug * v["basis"] * beta[0] * ren[0], "zeit": theta * tage}
    e["aktie"] = e["basis"] - e["markt"]
    e["rest"] = dz - e["basis"] - e["zeit"]
    haupt, haupt_wert = _treiber(e)
    tag = {
        "datum": t["datum"], "z_pct": _rendite(t["z_geld"], v["z_geld"]) * 100 if v["z_geld"] else None,
        "basis_pct": ren[1] * 100, "dax_pct": ren[0] * 100, "dz": dz,
        "delta": delta, "delta_geschaetzt": d_gesch, "beta": beta[0], "beta_geschaetzt": beta[1],
        "effekt_basis": e["basis"], "effekt_markt": e["markt"], "effekt_aktie": e["aktie"],
        "effekt_zeit": e["zeit"], "effekt_rest": e["rest"], "haupttreiber": haupt,
        "aktie_spez_pct": ar * 100, "auffaellig": zs is not None and abs(zs) >= SCHWELLE_Z, "z_score": zs,
        "cap_abstand_pct": cap_abstand_pct(t["basis"], cap),
    }
    tag["text"] = erklaerungstext(tag, v["z_geld"], t["z_geld"], basis_name, cap, haupt_wert)
    return tag


def _satz_zertifikat(a, b, dz, pct):
    if abs(dz) < 0.005:
        return f"Das Zertifikat blieb unverändert bei {de(b)} €."
    verb = "stieg" if dz > 0 else "fiel"
    return f"Das Zertifikat {verb} von {de(a)} € auf {de(b)} € ({de(dz, 2, True)} € oder {de(pct, 2, True)} %)."


def _satz_aktie(t, name):
    aktie = f"{name}-Aktie" if name else "Aktie"
    bew = "stieg" if t["basis_pct"] > 0 else "fiel" if t["basis_pct"] < 0 else "blieb unverändert"
    markt = t["beta"] * t["dax_pct"]
    teil = f"um {de(abs(t['basis_pct']))} %" if t["basis_pct"] else ""
    dax = "stieg" if t["dax_pct"] > 0 else "fiel" if t["dax_pct"] < 0 else "blieb unverändert"
    dax_teil = f" um {de(abs(t['dax_pct']))} %" if t["dax_pct"] else ""
    return (f"Die {aktie} {bew}{' ' + teil if teil else ''}, der DAX {dax}{dax_teil}; "
            f"davon entfallen rechnerisch etwa {de(markt, 2, True)} Prozentpunkte auf die allgemeine Marktbewegung.")


def _satz_delta(t, ueber_cap):
    zeit = f"der Zeitwert trug {de(t['effekt_zeit'], 2, True)} € bei"
    gesch = " (geschätzt)" if t["delta_geschaetzt"] else ""
    if ueber_cap:
        return (f"Das Zertifikat liegt nahe seinem Höchstwert (Cap), deshalb kommen Aktienbewegungen kaum an "
                f"(Delta {de(t['delta'])}{gesch}); {zeit}.")
    return (f"Das Delta von {de(t['delta'])}{gesch} sagt, welcher Anteil der Aktienbewegung beim Zertifikat ankommt; "
            f"so kamen {de(t['effekt_basis'], 2, True)} € an, {zeit}.")


def erklaerungstext(t, z_alt, z_neu, basis_name, cap, haupt_wert):
    dz = z_neu - z_alt
    pct = t["z_pct"] if t["z_pct"] is not None else 0.0
    ueber_cap = t["cap_abstand_pct"] is not None and t["cap_abstand_pct"] > 0 and t["delta"] < DELTA_KLEIN
    return " ".join([
        _satz_zertifikat(z_alt, z_neu, dz, pct), _satz_aktie(t, basis_name), _satz_delta(t, ueber_cap),
        f"Haupttreiber des Tages: {t['haupttreiber']} ({de(haupt_wert, 2, True)} €).",
    ])
