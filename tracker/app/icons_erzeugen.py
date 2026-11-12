"""Erzeugt die App-Icons (PNG) ohne Zusatzpakete. Einmalig von Hand: python tracker/app/icons_erzeugen.py

Motiv: Auszahlungsprofil eines Discount-Zertifikats, steigt bis zum Cap und bleibt dann flach.
Vollflächiger Hintergrund, Motiv in der sicheren Zone (80 %), damit Android und iOS es selbst abrunden können.
"""
import struct
import zlib
from pathlib import Path

HINTERGRUND = (11, 11, 11)
LINIE = (42, 120, 214)      # --s1 aus vorlage.html
CAP = (195, 194, 183)       # --axis
SS = 3                      # Überabtastung für weiche Kanten
# Punkte in Anteilen der Kantenlänge, innerhalb 0.2..0.8
KURVE = [(0.22, 0.74), (0.40, 0.56), (0.52, 0.40), (0.60, 0.33), (0.80, 0.33)]
CAP_Y, CAP_X = 0.27, (0.22, 0.80)


def _abstand(px, py, a, b):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def _farbe(x, y):
    staerke = 0.045
    if min(_abstand(x, y, KURVE[i], KURVE[i + 1]) for i in range(len(KURVE) - 1)) <= staerke / 2:
        return LINIE
    if abs(y - CAP_Y) <= 0.009 and CAP_X[0] <= x <= CAP_X[1] and int((x - CAP_X[0]) / 0.045) % 2 == 0:
        return CAP
    return HINTERGRUND


def _png(n):
    zeilen = bytearray()
    m = n * SS
    for py in range(n):
        zeilen.append(0)
        for px in range(n):
            r = g = b = 0
            for sy in range(SS):
                for sx in range(SS):
                    c = _farbe((px * SS + sx + 0.5) / m, (py * SS + sy + 0.5) / m)
                    r, g, b = r + c[0], g + c[1], b + c[2]
            k = SS * SS
            zeilen += bytes((r // k, g // k, b // k))

    def chunk(typ, daten):
        return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(zeilen), 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    ziel = Path(__file__).parent
    for name, n in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        (ziel / name).write_bytes(_png(n))
        print(name, n)
