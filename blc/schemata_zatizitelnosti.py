"""
schemata_zatizitelnosti.py
==========================
Zatěžovací schémata pro stanovení zatížitelnosti podle ČSN 73 6222 (Zatížitelnost
mostů pozemních komunikací), kap. 7, a jejich příčné umístění na vozovce.

Normální zatížitelnost Vn (čl. 7.1, obr. 7.1, 7.2) – rovnoměrné zatížení vn [kN/m²]:
  • počet a šířka zatěžovacích pruhů podle šířky zatěžovacího prostoru w (čl. 7.1.3):
        w < 5,4 m  … 1 pruh 3,0 m;   5,4 ≤ w ≤ 6,0 m … 2 pruhy 0,5·w;
        w > 6,0 m  … ⌊w/3⌋ pruhů 3,0 m,
  • pruhy 1 a 2: dvounáprava 2 × 50·vn (kolo 25·vn, vzdálenost náprav 1,2 m), při Vn < 16 t
    náhradní jednoduchá náprava 100·vn (kolo 50·vn) (čl. 7.1.6); rovnoměrné 2,5·vn,
  • pruhy 3 a 4: jednoduchá náprava 50·vn (kolo 25·vn); rovnoměrné vn,
  • další pruhy a zbývající plocha zatěžovacího prostoru: rovnoměrné vn,
  • kola 2,0 m od sebe, 0,5 m od okraje pruhu šířky 3 m (v pruhu jiné šířky souměrně);
    ploška kola není v normě zadána – uvažuje se 0,40 × 0,40 m jako u modelu LM1
    (ČSN EN 1991-2, čl. 4.3.2), z něhož schéma vychází (čl. 7.1.1),
  • V_aw = 100·vn [kN], V_nw = 4/3·V_aw, Vn = V_nw/10 [t] → Vn = 13,33·vn (čl. 7.1.7).
Výhradní zatížitelnost Vr (čl. 7.2, obr. 7.3, 7.4) – jediné vozidlo tíhy 10·Vr [kN]:
  • šestinápravové 6 × Vr/6 (nápravy po 1,5 m, plošky kol 0,15 × 1,2 m, stopy 1,5 m,
    šířka vozidla 3,0 m), je-li Vr > 50 t,
  • jinak dvounápravové ¼ + ¾ Vr (rozvor 3,0 m) a je-li Vr > 16 t, lze třínápravové
    ¼ + ⅜ + ⅜ Vr (nápravy 2,4 + 1,2 m); kola 2,0 m od sebe, šířka vozidla 2,5 m,
    plošky kol přední 0,2 × 0,2 m, zadní 0,2 m (podélně) × 0,4 m (příčně).
Zatížení chodníků se schématy Vn a Vr: redukovaná hodnota w_f = 2,5 kN/m² (tab. 7.1, 7.2,
sestavy n1, r1); u výjimečné zatížitelnosti Ve jsou chodci vyloučeni (čl. 3.1.4, 5.2.8).

Příčná poloha (zadání uživatele, nehledá se nejnepříznivější): zatížení se klade ke kraji
vozovky u UŽŠÍHO chodníku – pruh č. 1 (vozidlo Vr vnějším okrajem) u tohoto kraje, další
pruhy směrem ke druhému kraji, zbytek vozovky = zbývající plocha.  Zatěžovací prostor =
vozovka mezi chodníky.  Při shodných chodnících se zatěžuje od levého kraje.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

NORMA = "ČSN 73 6222"

# ---- zatížení chodníků ----------------------------------------------------------
Q_CHODNIKY = 2.5                 # w_f [kN/m²] – tab. 7.1 (n1), 7.2 (r1)

# ---- normální zatížitelnost (kap. 7.1) ---------------------------------------------
SIRKA_PRUHU = 3.0                # [m]
ROZCHOD_KOL = 2.0                # vzdálenost os kol nápravy [m]
ROZTEC_DVOJNAPRAVY = 1.2         # [m]
PLOSKA_KOLA_VN = 0.40            # čtvercová ploška kola [m] (jako LM1)
VN_MEZ = 16.0                    # [t] – pod touto hodnotou náhradní jednoduchá náprava
KOEF_VN = 4.0 / 3.0 * 100.0 / 10.0      # Vn [t] = KOEF_VN · vn [kN/m²]  (= 13,33)
VR_MEZ_2 = 16.0                  # [t] – nad touto hodnotou lze třínápravové vozidlo
VR_MEZ_6 = 50.0                  # [t] – nad touto hodnotou šestinápravové vozidlo


def Vn_z_vn(vn: float) -> float:
    """Normální zatížitelnost Vn [t] z rovnoměrného zatížení vn [kN/m²] (čl. 7.1.7)."""
    return KOEF_VN * vn


def vn_z_Vn(Vn: float) -> float:
    """Rovnoměrné zatížení vn [kN/m²] odpovídající Vn [t]."""
    return Vn / KOEF_VN


def zatezovaci_pruhy(w: float) -> Tuple[int, float]:
    """(počet, šířka [m]) zatěžovacích pruhů pro šířku zatěžovacího prostoru w (čl. 7.1.3)."""
    if w < 5.4:
        return 1, SIRKA_PRUHU
    if w <= 6.0:
        return 2, 0.5 * w
    return int(math.floor(w / SIRKA_PRUHU + 1e-9)), SIRKA_PRUHU


# ---- výhradní zatížitelnost (kap. 7.2) – vozidla -------------------------------------

@dataclass(frozen=True)
class NapravaVozidla:
    podil: float          # podíl celkové tíhy vozidla na nápravu
    x: float              # poloha nápravy od čela vozidla [m]
    delka: float          # podélný rozměr plošky kola [m]
    sirka: float          # příčný rozměr plošky kola [m]


@dataclass(frozen=True)
class VozidloSchema:
    klic: str
    nazev: str
    napravy: Tuple[NapravaVozidla, ...]
    rozchod: float        # vzdálenost os kol (stop) [m]
    sirka: float          # šířka vozidla [m]
    delka: float          # délka vozidla [m]
    obrazek: str

    @property
    def symetricke(self) -> bool:
        """Souměrné podél (stejné nápravy ve stejných vzdálenostech od středu) – stačí jeden
        směr jízdy."""
        n = self.napravy
        return all(abs(a.podil - b.podil) < 1e-12 and abs(a.x + b.x - self.delka) < 1e-9
                   for a, b in zip(n, reversed(n)))


VOZIDLA_VR = {
    "6": VozidloSchema("6", "šestinápravové vozidlo",
                       tuple(NapravaVozidla(1.0 / 6.0, 0.75 + 1.5 * k, 0.15, 1.2) for k in range(6)),
                       rozchod=1.5, sirka=3.0, delka=9.0, obrazek="obr. 7.3"),
    "2": VozidloSchema("2", "dvounápravové vozidlo",
                       (NapravaVozidla(0.25, 1.5, 0.2, 0.2), NapravaVozidla(0.75, 4.5, 0.2, 0.4)),
                       rozchod=2.0, sirka=2.5, delka=6.0, obrazek="obr. 7.4a"),
    "3": VozidloSchema("3", "třínápravové vozidlo",
                       (NapravaVozidla(0.25, 1.5, 0.2, 0.2), NapravaVozidla(0.375, 3.9, 0.2, 0.4),
                        NapravaVozidla(0.375, 5.1, 0.2, 0.4)),
                       rozchod=2.0, sirka=2.5, delka=6.0, obrazek="obr. 7.4b"),
}


def schema_Vr(Vr: float) -> str:
    """Vozidlo schématu výhradní zatížitelnosti pro tíhu Vr [t] (čl. 7.2.2):
    "6" (Vr > 50 t), "3" (16 < Vr ≤ 50 t), "2" (Vr ≤ 16 t)."""
    if Vr > VR_MEZ_6:
        return "6"
    return "3" if Vr > VR_MEZ_2 else "2"


def schema_Vn(Vn: float) -> str:
    """Náprava schématu normální zatížitelnosti v pruzích 1, 2: "dvojnaprava" (Vn ≥ 16 t)
    nebo "naprava" (náhradní jednoduchá náprava, Vn < 16 t; čl. 7.1.6)."""
    return "dvojnaprava" if Vn >= VN_MEZ else "naprava"


POPIS_SCHEMAT = {
    "dvojnaprava": "dvounáprava 2 × 50·vn v pruzích 1, 2 (Vn ≥ 16 t)",
    "naprava": "náhradní jednoduchá náprava 100·vn v pruzích 1, 2 (Vn < 16 t, čl. 7.1.6)",
    "6": "šestinápravové vozidlo (obr. 7.3, Vr > 50 t)",
    "3": "třínápravové vozidlo (obr. 7.4b, Vr > 16 t)",
    "2": "dvounápravové vozidlo (obr. 7.4a)",
}


# ---- výsledná zatížitelnost z jednotlivých schémat ------------------------------------

def _inf(v: Optional[float]) -> float:
    return math.inf if v is None else float(v)


def Vn_ze_schemat(V_dvojnaprava: Optional[float], V_naprava: Optional[float] = None
                  ) -> Optional[float]:
    """Normální zatížitelnost z výsledků schémat (None = neomezuje): dvounáprava platí pro
    Vn ≥ 16 t, náhradní náprava pro Vn < 16 t → Vn = V_dvoj, je-li ≥ 16 t,
    jinak min(V_náhr, 16)."""
    if _inf(V_dvojnaprava) >= VN_MEZ:
        return V_dvojnaprava
    return min(_inf(V_naprava), VN_MEZ)


def Vr_ze_schemat(V6: Optional[float], V2: Optional[float] = None,
                  V3: Optional[float] = None) -> Optional[float]:
    """Výhradní zatížitelnost z výsledků schémat (None = neomezuje; čl. 7.2.2):
    Vr = V6, je-li > 50 t; jinak dvounápravové V2, a je-li V2 > 16 t, lze třínápravové
    (Vr = max(V2, V3)) – nejvýše 50 t (nad 50 t platí šestinápravové)."""
    v6 = _inf(V6)
    if v6 > VR_MEZ_6:
        return V6
    v2 = _inf(V2)
    if v2 > VR_MEZ_2:
        v2 = max(v2, _inf(V3))
    return min(v2, VR_MEZ_6)


# ---- příčné uspořádání ------------------------------------------------------------

@dataclass
class PricnaPoloha:
    """Zatěžovací prostor a strana, ke které se zatížení klade."""
    y_kraj: float           # kraj vozovky u užšího chodníku [m]
    smer: int               # +1 = pruhy přibývají ve směru +y (kraj vlevo), −1 = vpravo
    w: float                # šířka zatěžovacího prostoru (vozovky) [m]
    strana: str             # "L" | "P"
    y_druhy: float          # druhý kraj vozovky [m]

    def pas(self, od: float, do: float) -> Tuple[float, float]:
        """Pás mezi vzdálenostmi od a do od kraje (y0 < y1)."""
        a, b = self.y_kraj + self.smer * od, self.y_kraj + self.smer * do
        return (min(a, b), max(a, b))

    @property
    def popis(self) -> str:
        return (f"u {'levého' if self.strana == 'L' else 'pravého'} kraje vozovky "
                f"(užší chodník {'L' if self.strana == 'L' else 'P'})")


def pricna_poloha(chodnik_L: float, chodnik_P: float, B: float) -> PricnaPoloha:
    """Kraj vozovky u užšího chodníku (při shodných šířkách levý)."""
    w = B - chodnik_L - chodnik_P
    if chodnik_P < chodnik_L - 1e-9:
        return PricnaPoloha(B - chodnik_P, -1, w, "P", chodnik_L)
    return PricnaPoloha(chodnik_L, +1, w, "L", B - chodnik_P)


@dataclass
class Pruh:
    cislo: int
    y0: float
    y1: float
    q_rovnomerne: float     # násobek vn
    naprava: Optional[str]  # "dvojnaprava" | "naprava" | "jednoducha" | None
    F_kolo: float           # tíha kola jako násobek vn [kN / (kN/m²)]

    @property
    def y_c(self) -> float:
        return 0.5 * (self.y0 + self.y1)


def pruhy_Vn(p: PricnaPoloha, schema: str) -> Tuple[List[Pruh], Optional[Tuple[float, float]]]:
    """Zatěžovací pruhy schématu Vn od kraje u užšího chodníku a zbývající plocha
    (y0, y1) nebo None.  schema = "dvojnaprava" | "naprava" (pruhy 1, 2)."""
    n, wl = zatezovaci_pruhy(p.w)
    out = []
    for i in range(1, n + 1):
        y0, y1 = p.pas((i - 1) * wl, i * wl)
        if i <= 2:
            nap, Fk, qr = (schema, 25.0 if schema == "dvojnaprava" else 50.0, 2.5)
        elif i <= 4:
            nap, Fk, qr = ("jednoducha", 25.0, 1.0)
        else:
            nap, Fk, qr = (None, 0.0, 1.0)
        out.append(Pruh(i, y0, y1, qr, nap, Fk))
    zbytek = p.w - n * wl
    return out, (p.pas(n * wl, p.w) if zbytek > 1e-6 else None)


def stopy_vozidla_u_kraje(p: PricnaPoloha, v: VozidloSchema) -> Tuple[float, float, float]:
    """(osa vozidla, osa stopy 1, osa stopy 2) [m] – vozidlo vnějším okrajem u kraje vozovky."""
    yc = p.y_kraj + p.smer * 0.5 * v.sirka
    return yc, yc - 0.5 * v.rozchod, yc + 0.5 * v.rozchod
