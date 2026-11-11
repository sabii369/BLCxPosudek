"""
zatizitelnost.py
================
Výpočet zatížitelnosti podle ČSN 73 6222: místo posouzení při zadaném zatížení se pro
každý mezní stav (posudek × fáze × kombinace Posudku PB) hledá tíha vozidla V [t], při
které je využití η = 100 %, pro druhy zatížitelnosti
  Vn – normální (čl. 7.1): schéma obr. 7.1, dvounáprava (Vn ≥ 16 t), jinak náhradní
       jednoduchá náprava; pruhy od kraje vozovky u užšího chodníku; chodci 2,5 kN/m²,
  Vr – výhradní (čl. 7.2): jediné vozidlo u kraje vozovky u užšího chodníku –
       šestinápravové (Vr > 50 t), jinak dvounápravové, nad 16 t lze třínápravové;
       chodci 2,5 kN/m²,
  Ve – výjimečná (čl. 7.3): devítinápravová souprava v ose vozovky (nebo zadané stopě),
       chodci vyloučeni.
(chodci podle normy, není-li q_chodnik zadáno; součinitele kombinací z [blc]).

Postup pro jedno schéma:
  • stav q schématu se spočte jednou na modelu mostu s referenční tíhou (Vn, Vr, Ve z [blc]);
    účinky jsou v tíze lineární (stejné polohy, síly ∝ V) → pro jinou tíhu se q přeškáluje,
  • pro zkoušenou tíhu se spočte celý posudek (nelineární MSÚ, ztráty předpětí, …) – jeden
    výpočet dá využití všech posudků najednou,
  • pro každý posudek: interval V, kde η přechází přes 1 (zvětšováním V), pak regula falsi
    (Illinois) se sdílenými výpočty, přesnost |η − 1| ≤ tol,
  • posudky, jejichž využití na zatížení dopravou nezávisí (napínání, minimální výztuž …),
    se označí „nezávisí na zatížení“ (vyhovuje / nevyhovuje); neomezující „neomezuje“.
Výsledek druhu pro každý posudek ze schémat (blc.schemata_zatizitelnosti):
  Vn = V_dvounáprava, je-li ≥ 16 t, jinak min(V_náhradní náprava, 16 t);
  Vr = V_6, je-li > 50 t, jinak V_2, a je-li V_2 > 16 t, max(V_2, V_3) (nejvýše 50 t).
Zatížitelnost = nejmenší hodnota přes posudky (čl. 4.1; zvlášť MSÚ a MSP), do evidence
zaokrouhlená na celé tuny dolů (čl. 13.2).  Posuzovaný nosník je pro každý druh pevný
(zadaný, nebo nejzatíženější při referenční tíze prvního schématu).  Ostatní zatížení
(g0, g − g0, chodci) se nemění; dynamický součinitel δ je v účincích q.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from blc import schemata_zatizitelnosti as sz
from blc.vnitrni_sily import VysledekSil, vnitrni_sily, vys_pro_V, vys_s_vozidlem

TOL = 1e-3              # přesnost využití
TOL_V = 0.01            # přesnost V [t]
DRUHY = ("Vn", "Vr", "Ve")
NAZVY_DRUHU = {"Vn": "normální", "Vr": "výhradní", "Ve": "výjimečná"}
CLANKY = {"Vn": "čl. 7.1", "Vr": "čl. 7.2", "Ve": "čl. 7.3"}
STAVY_TEXT = {
    "V": "",
    "neomezuje": "neomezuje",
    "nezavisi_ok": "nezávisí na zatížení dopravou – vyhovuje",
    "nezavisi_nok": "nezávisí na zatížení dopravou – NEVYHOVUJE",
    "bez_vozidla": "nevyhovuje již bez vozidla",
    "klesa": "η klesá se zatížením – neomezuje (bez vozidla nevyhovuje)",
}
KRATKE = {"neomezuje": "∞", "nezavisi_ok": "∞", "klesa": "∞", "nezavisi_nok": "✗",
          "bez_vozidla": "0"}
POPIS_SCHEMAT = {"": "devítinápravová souprava (obr. 7.5)", **sz.POPIS_SCHEMAT}


@dataclass
class PosudekZat:
    """Zatížitelnost pro jeden posudek (mezní stav)."""
    klic: tuple                  # (mezní stav, název, fáze, kombinace)
    V: Optional[float]           # [t]; None = neomezuje / nezávisí
    stav: str                    # klíč STAVY_TEXT
    eta_ref: float               # využití při referenční tíze
    eta_0: float                 # využití bez vozidla
    schema: str = ""             # schéma, ze kterého hodnota plyne

    @property
    def mezni_stav(self):
        return self.klic[0]

    @property
    def Ve(self):                # kompatibilita (dříve jen Ve)
        return self.V

    @property
    def text(self) -> str:
        if self.stav == "V":
            return f"{self.V:.1f}"
        if self.stav == "bez_vozidla":
            return "0 (" + STAVY_TEXT[self.stav] + ")"
        return STAVY_TEXT[self.stav]

    @property
    def kratky(self) -> str:
        return f"{self.V:.1f}" if self.stav == "V" else KRATKE[self.stav]


@dataclass
class VysledekSchematu:
    """Hledání pro jedno zatěžovací schéma (jeden stav q)."""
    schema: str
    posudky: Dict[tuple, PosudekZat]
    V_ref: float
    V_max: float                 # největší zkoušená tíha
    n_vypoctu: int
    vys: VysledekSil             # most s referenčním zatížením schématu


def _minimum(posudky, ms: Optional[str] = None) -> Optional[PosudekZat]:
    p = [x for x in posudky if x.V is not None and (ms is None or x.mezni_stav == ms)]
    return min(p, key=lambda x: x.V) if p else None


@dataclass
class ZatizitelnostDruhu:
    """Zatížitelnost jednoho druhu (Vn, Vr, Ve) – po posudcích a celkově."""
    druh: str
    posudky: List[PosudekZat]
    schemata: Dict[str, VysledekSchematu]
    o: int                               # posuzovaný výstup
    poznamky: List[str] = field(default_factory=list)

    def minimum(self, ms: Optional[str] = None) -> Optional[PosudekZat]:
        return _minimum(self.posudky, ms)

    @property
    def V(self) -> Optional[float]:
        m = self.minimum()
        return None if m is None else m.V

    @property
    def V_evidence(self) -> Optional[int]:
        """Hodnota do evidence – zaokrouhleno na celé tuny dolů (čl. 13.2)."""
        return None if self.V is None else int(math.floor(self.V + 1e-9))

    @property
    def prvni(self) -> VysledekSchematu:
        return next(iter(self.schemata.values()))

    @property
    def V_ref(self) -> float:
        return self.prvni.V_ref

    @property
    def V_max(self) -> float:
        return max(s.V_max for s in self.schemata.values())

    @property
    def n_vypoctu(self) -> int:
        return sum(s.n_vypoctu for s in self.schemata.values())

    @property
    def nevyhovuji_nezavisle(self) -> List[PosudekZat]:
        return [x for x in self.posudky if x.stav == "nezavisi_nok"]

    @property
    def schema_V(self) -> str:
        """Schéma rozhodující pro zatížitelnost (bez rozhodujícího posudku první)."""
        m = self.minimum()
        return m.schema if m is not None else next(iter(self.schemata))

    @property
    def text(self) -> str:
        return f"{self.druh} > {self.V_max:.0f} t" if self.V is None else f"{self.druh} = {self.V:.1f} t"


@dataclass
class VysledekZatizitelnosti:
    """Zatížitelnosti všech spočtených druhů; protokol pro druh `druh`."""
    druhy: Dict[str, ZatizitelnostDruhu]
    druh: str
    vys: Optional[VysledekSil] = None    # most pro druh `druh` při jeho zatížitelnosti
    o: int = 0
    model: object = None                 # posudek při této zatížitelnosti
    poznamky: List[str] = field(default_factory=list)

    @property
    def hlavni(self) -> ZatizitelnostDruhu:
        return self.druhy[self.druh]

    # ---- zkratky na hlavní druh ------------------------------------------------
    @property
    def posudky(self) -> List[PosudekZat]:
        return self.hlavni.posudky

    def minimum(self, ms: Optional[str] = None) -> Optional[PosudekZat]:
        return self.hlavni.minimum(ms)

    @property
    def V(self) -> Optional[float]:
        return self.hlavni.V

    @property
    def Ve(self) -> Optional[float]:
        return self.druhy["Ve"].V if "Ve" in self.druhy else None

    @property
    def Vn(self) -> Optional[float]:
        return self.druhy["Vn"].V if "Vn" in self.druhy else None

    @property
    def Vr(self) -> Optional[float]:
        return self.druhy["Vr"].V if "Vr" in self.druhy else None

    @property
    def V_max(self) -> float:
        return self.hlavni.V_max

    @property
    def n_vypoctu(self) -> int:
        return sum(z.n_vypoctu for z in self.druhy.values())

    @property
    def nevyhovuji_nezavisle(self) -> List[PosudekZat]:
        return self.hlavni.nevyhovuji_nezavisle

    @property
    def Vaj(self) -> Optional[float]:
        """Zatížitelnost na jednu jednoduchou nápravu [t] (čl. 5.1.7): největší zatížení
        nápravy vozidla normální a výhradní zatížitelnosti (3/4 dvounápravového, 3/8
        třínápravového, 1/6 šestinápravového)."""
        vals = []
        for d in ("Vn", "Vr"):
            z = self.druhy.get(d)
            if z is None or z.V is None:
                continue
            V = z.V
            if d == "Vn":
                vals.append(V * (3.0 / 8.0 if V >= sz.VN_MEZ else 3.0 / 4.0))
            else:
                vals.append(V * {"6": 1.0 / 6.0, "3": 3.0 / 8.0, "2": 3.0 / 4.0}[
                    z.schema_V if z.schema_V in ("6", "3", "2") else sz.schema_Vr(V)])
        return max(vals) if vals else None


def klic_posudku(p) -> tuple:
    return (p.mezni_stav, p.nazev, p.faze, p.kombinace)


def vys_pro_Ve(vys: VysledekSil, Ve: float) -> VysledekSil:
    """Kopie výsledku mostu se stavem q přeškálovaným na tíhu Ve [t] (= vys_pro_V)."""
    if vys.druh_q != "Ve":
        raise ValueError("Zatížitelnost Ve se počítá pro vozidlo Ve (zadejte Ve > 0).")
    return vys_pro_V(vys, Ve)


# ---------------------------------------------------------------------------
# Hledání pro jedno schéma
# ---------------------------------------------------------------------------

def _hledej(d: dict, vys: VysledekSil, o: int, schema: str, tol: float, max_kol: int,
            nasobek_max: float, prubeh=None, nazev: str = "V") -> VysledekSchematu:
    """V [t] pro η = 1 každého posudku při zatížení q mostu vys (přeškálovaném z vys.V)."""
    from pb_posudek.vstup import model_ze_slovniku
    from .vypocet import data_pro_posudek

    Vr = float(vys.V)
    body: Dict[float, Dict[tuple, float]] = {}

    def eta(V: float) -> Dict[tuple, float]:
        V = round(float(V), 4)
        if V not in body:
            m = model_ze_slovniku(data_pro_posudek(vys_pro_V(vys, V), d, o))
            m.spocitej()
            body[V] = {klic_posudku(p): float(p.vyuziti) for p in m.protokol.posudky}
            if prubeh:
                prubeh(f"Zatížitelnost {nazev}: výpočet {len(body)} ({nazev} = {V:.1f} t)")
        return body[V]

    e0, er = eta(0.0), eta(Vr)
    klice = [k for k in er if k in e0]

    def roste(k, V):
        return eta(V).get(k, 0.0) > e0[k] + 1e-9

    # ---- rozšíření rozsahu, dokud rostoucí posudky nedosáhnou η ≥ 1 -----------
    Vmax = Vr
    while Vmax < nasobek_max * Vr:
        chybi = [k for k in klice if e0[k] < 1.0 and roste(k, Vmax) and eta(Vmax)[k] < 1.0]
        if not chybi:
            break
        # odhad z lineárního průběhu, nejvýše čtyřnásobek
        odh = [Vmax * (1.0 - e0[k]) / (eta(Vmax)[k] - e0[k]) for k in chybi]
        Vmax = min(max(1.05 * min(odh), 1.5 * Vmax), 4.0 * Vmax, nasobek_max * Vr)
        eta(Vmax)

    # ---- klasifikace a intervaly --------------------------------------------
    vysl: Dict[tuple, PosudekZat] = {}
    interval = {}                         # k → [a, fa, b, fb, strana]

    def zat(k, V, stav):
        return PosudekZat(k, V, stav, er[k], e0[k], schema)

    for k in klice:
        hodn = [(V, body[V][k]) for V in sorted(body) if k in body[V]]
        rozptyl = max(h for _, h in hodn) - min(h for _, h in hodn)
        if rozptyl < 1e-6:
            vysl[k] = zat(k, None, "nezavisi_nok" if e0[k] > 1.0 + 1e-9 else "nezavisi_ok")
            continue
        if e0[k] >= 1.0:
            # η klesá se zatížením (např. křehký lom) – nevyhovuje jen při malém zatížení
            stav = "klesa" if min(h for _, h in hodn) < 1.0 else "bez_vozidla"
            vysl[k] = zat(k, 0.0 if stav == "bez_vozidla" else None, stav)
            continue
        i = next((j for j, (_, h) in enumerate(hodn) if h >= 1.0), None)
        if i is None:
            vysl[k] = zat(k, None, "neomezuje")
            continue
        (a, fa), (b, fb) = hodn[i - 1], hodn[i]
        interval[k] = [a, fa - 1.0, b, fb - 1.0, 0]

    # ---- Illinois (regula falsi) se sdílenými výpočty -------------------------
    for _ in range(max_kol):
        hotove, plan = [], {}
        for k, (a, fa, b, fb, _) in interval.items():
            if b - a <= TOL_V:
                hotove.append(k)
                continue
            c = a + (b - a) * (-fa) / (fb - fa) if fb != fa else 0.5 * (a + b)
            c = min(max(c, a + 1e-6), b - 1e-6)
            # sdílet blízký již plánovaný / spočtený výpočet
            blizky = [V for V in list(body) + list(plan.values()) if a < V < b and abs(V - c) <= 2e-3 * c]
            plan[k] = blizky[0] if blizky else c
        for k in hotove:
            a, fa, b, fb, _ = interval.pop(k)
            vysl[k] = zat(k, a + (b - a) * (-fa) / (fb - fa) if fb != fa else 0.5 * (a + b), "V")
        if not interval:
            break
        for k, c in plan.items():
            if k not in interval:
                continue
            fc = eta(c).get(k, 1.0) - 1.0
            a, fa, b, fb, strana = interval[k]
            if abs(fc) <= tol:
                interval.pop(k)
                vysl[k] = zat(k, c, "V")
                continue
            if fc < 0:
                a, fa = c, fc
                if strana == -1:
                    fb *= 0.5
                strana = -1
            else:
                b, fb = c, fc
                if strana == 1:
                    fa *= 0.5
                strana = 1
            interval[k] = [a, fa, b, fb, strana]
    for k, (a, fa, b, fb, _) in interval.items():          # nekonvergovalo – interpolace
        vysl[k] = zat(k, a + (b - a) * (-fa) / (fb - fa) if fb != fa else 0.5 * (a + b), "V")
    return VysledekSchematu(schema, {k: vysl[k] for k in klice}, Vr, Vmax, len(body), vys)


# ---------------------------------------------------------------------------
# Druhy zatížitelnosti
# ---------------------------------------------------------------------------

def _V(p: Optional[PosudekZat]) -> Optional[float]:
    return None if p is None else p.V


def _slouc(druh: str, sch: Dict[str, VysledekSchematu]) -> List[PosudekZat]:
    """Výsledná zatížitelnost druhu po posudcích ze schémat (čl. 7.1.6, 7.2.2)."""
    prvni = next(iter(sch.values()))
    out = []
    for k, p0 in prvni.posudky.items():
        if druh == "Ve" or p0.stav != "V":
            out.append(p0)
            continue
        if druh == "Vn":
            vs = _V(sch["naprava"].posudky.get(k)) if "naprava" in sch else None
            V = sz.Vn_ze_schemat(p0.V, vs)
            schema = "dvojnaprava" if V == p0.V else "naprava"
        else:
            v2 = _V(sch["2"].posudky.get(k)) if "2" in sch else None
            v3 = _V(sch["3"].posudky.get(k)) if "3" in sch else None
            V = sz.Vr_ze_schemat(p0.V, v2, v3)
            tri = (v2 is None or v2 > sz.VR_MEZ_2) and "3" in sch and \
                (v3 is None or v2 is None or v3 >= v2)
            schema = "6" if V == p0.V else ("3" if tri else "2")
        stav = "V" if V is not None and math.isfinite(V) else "neomezuje"
        out.append(PosudekZat(k, V if stav == "V" else None, stav, p0.eta_ref, p0.eta_0, schema))
    return out


def _vys_druhu(vys: VysledekSil, druh: str, V: float, schema: str = "") -> VysledekSil:
    """Most se zatížením q daného druhu a schématu (stejný model MKP; znovu se nepočítá,
    odpovídá-li vys už tomuto zatížení)."""
    if vys.druh_q == druh and abs(vys.V - V) < 1e-9 and (not schema or vys.schema_q == schema):
        return vys
    return vys_s_vozidlem(vys, **{druh: V}, **({"schema": schema} if schema else {}))


def _druhy_ze_vstupu(d: dict, druhy) -> List[str]:
    from .vypocet import VYCHOZI_BLC
    b = {**VYCHOZI_BLC, **d.get("blc", {})}
    if druhy is None:
        druhy = b.get("zatizitelnost_druhy", "vse")
    if isinstance(druhy, str):
        druhy = list(DRUHY) if druhy in ("vse", "", "all") else \
            [b["vozidlo"]] if druhy == "vozidlo" else [x.strip() for x in druhy.split(",")]
    druhy = [x for x in DRUHY if x in druhy]
    if not druhy:
        raise ValueError("Zatížitelnost: zvolte alespoň jeden druh Vn, Vr, Ve.")
    return druhy


def zatizitelnost(d: dict, vys: Optional[VysledekSil] = None, o: Optional[int] = None,
                  druhy=None, tol: float = TOL, max_kol: int = 30, nasobek_max: float = 64.0,
                  prubeh=None) -> VysledekZatizitelnosti:
    """Zatížitelnost Vn, Vr, Ve pro všechny posudky; d = spojená vstupní data (s [blc]).
    druhy = seznam ("Vn", "Vr", "Ve") | "vse" | "vozidlo" | None (= [blc] zatizitelnost_druhy).
    o = posuzovaný výstup pro všechny druhy (None = podle [blc] vystup / nejzatíženější
    pro každý druh).  Protokol (res.model) je pro zvolené vozidlo [blc] (je-li mezi druhy),
    jinak pro první druh.  prubeh(text) – volitelné hlášení průběhu."""
    from .vypocet import VYCHOZI_BLC, parametry_blc, vyber_nosnik, spocti

    b = {**VYCHOZI_BLC, **d.get("blc", {})}
    voz = b.get("vozidlo") or "Ve"
    if voz not in DRUHY:
        raise ValueError("Výpočet zatížitelnosti je pro vozidla ČSN 73 6222 – zvolte vozidlo Vn, "
                         "Vr nebo Ve.")
    druhy = _druhy_ze_vstupu(d, druhy)
    if vys is None:
        vys = vnitrni_sily(**parametry_blc(d))
    V_ref = {k: float(b.get(k) or 0.0) for k in DRUHY}
    for k in druhy:
        if V_ref[k] <= 0:
            raise ValueError(f"Zatížitelnost: zadejte referenční {k} > 0.")
    pevny = o if o is not None else (vyber_nosnik(vys, d) if str(b.get("vystup") or "auto") != "auto"
                                      else None)
    kw = dict(tol=tol, max_kol=max_kol, nasobek_max=nasobek_max, prubeh=prubeh)
    res = VysledekZatizitelnosti({}, voz if voz in druhy else druhy[0])

    for druh in druhy:
        poradi = {"Vn": ["dvojnaprava"], "Vr": ["6"], "Ve": [""]}[druh]
        sch: Dict[str, VysledekSchematu] = {}
        o_d = pevny
        while poradi:
            s = poradi.pop(0)
            if prubeh:
                prubeh(f"Zatížitelnost {druh}: {POPIS_SCHEMAT[s]}")
            v_s = _vys_druhu(vys, druh, V_ref[druh], s)
            if o_d is None:
                o_d = vyber_nosnik(v_s, d)
            r = sch[s] = _hledej(d, v_s, o_d, s, nazev=druh, **kw)
            Vs = [p.V for p in r.posudky.values() if p.stav in ("V", "bez_vozidla")]
            if druh == "Vn" and s == "dvojnaprava" and any(v < sz.VN_MEZ for v in Vs):
                poradi.append("naprava")
            elif druh == "Vr" and s == "6" and any(v <= sz.VR_MEZ_6 for v in Vs):
                poradi.append("2")
            elif druh == "Vr" and s == "2":
                # třínápravové vozidlo jen tam, kde nerozhoduje šestinápravové a V2 > 16 t
                v6 = sch["6"].posudky
                if any(_V(v6.get(k)) is not None and v6[k].V <= sz.VR_MEZ_6 and
                       (p.V is None or p.V > sz.VR_MEZ_2) for k, p in r.posudky.items()):
                    poradi.append("3")
        z = ZatizitelnostDruhu(druh, _slouc(druh, sch), sch, o_d)
        if z.nevyhovuji_nezavisle:
            z.poznamky.append(f"{len(z.nevyhovuji_nezavisle)} posudků nevyhovuje nezávisle na "
                              "zatížení dopravou (předpětí, výstavba) – zatížitelnost neomezují, "
                              "ale konstrukci je nutné posoudit.")
        res.druhy[druh] = z

    # ---- posudek při zatížitelnosti hlavního druhu (protokol, grafy) -----------
    h = res.hlavni
    V_fin = h.V if h.V is not None and h.V > 0 else h.V_ref
    r = h.schemata.get(h.schema_V) or h.prvni
    if prubeh:
        prubeh(f"Zatížitelnost: posudek při {h.druh} = {V_fin:.1f} t")
    vk, o_p, model = spocti(d, vys_pro_V(r.vys, V_fin), h.o)
    res.vys, res.o, res.model = vk, o_p, model
    res.poznamky = list(dict.fromkeys(t for z in res.druhy.values() for t in z.poznamky))
    model.zatizitelnost = res
    kapitola_zatizitelnost(model, res)
    return res


# ---------------------------------------------------------------------------
# Protokol
# ---------------------------------------------------------------------------

def kapitola_zatizitelnost(model, res: VysledekZatizitelnosti) -> None:
    """Kapitola protokolu se zatížitelností (na začátek protokolu)."""
    from pb_posudek.protokol import Kapitola, fmt
    K = Kapitola("Zatížitelnost podle ČSN 73 6222", 1)
    vys = res.vys
    vyst = "pás" if vys.deska else "nosník"
    K.text("Pro každý posudek (mezní stav, fáze, kombinace) byla hledána tíha vozidla, při které je "
           "využití η = 100 % (iterací celého posudku; účinky zatížení dopravou z modelu mostu "
           "přeškálované z referenční tíhy – jsou v ní lineární). Zatížitelnost je nejmenší hodnota "
           "přes posudky (čl. 4.1); do evidence se zaokrouhluje na celé tuny dolů (čl. 13.2). "
           "Ostatní zatížení – g0, g − g0 a chodci – se nemění. Zatížení Vn a Vr stojí u kraje "
           "vozovky u užšího chodníku (pruh č. 1 / vnější okraj vozidla); nejnepříznivější příčná "
           "poloha se nehledá.")
    rows = []
    for druh, z in res.druhy.items():
        m_all, m_su, m_sp = z.minimum(), z.minimum("MSÚ"), z.minimum("MSP")
        r0 = z.prvni
        rows.append([
            f"{druh} – {NAZVY_DRUHU[druh]} ({CLANKY[druh]})",
            "> " + fmt(z.V_max) if m_all is None else fmt(m_all.V, 1),
            "–" if z.V_evidence is None else str(z.V_evidence),
            "–" if m_su is None else fmt(m_su.V, 1), "–" if m_sp is None else fmt(m_sp.V, 1),
            "–" if m_all is None else f"{m_all.klic[0]} {m_all.klic[1]} ({m_all.klic[2]})",
            POPIS_SCHEMAT[z.schema_V], r0.vys.popisky[z.o],
            fmt(r0.vys.q_ch, 2) + (" (norma)" if r0.vys.q_ch_zdroj != "zadáno" else "")])
    K.tabulka(["Druh", "Zatížitelnost [t]", "Evidence [t]", "MSÚ [t]", "MSP [t]", "Rozhoduje",
               "Schéma", vyst.capitalize(), "Chodci [kN/m²]"], rows,
              "Zatížitelnosti mostu (nejmenší hodnoty přes posudky)")
    if "Vn" in res.druhy or "Vr" in res.druhy:
        Vaj = res.Vaj
        if Vaj is not None:
            K.krok("Zatížitelnost na jednu jednoduchou nápravu V_aj (čl. 5.1.7)", "", "",
                   math.floor(Vaj * 10 + 1e-9) / 10, "t")
        zn = []
        ev = {k: z.V_evidence for k, z in res.druhy.items()}
        if ev.get("Vn") is not None and ev["Vn"] < 26:
            zn.append("normální zatížitelnost je nižší než 26 t")
        if ev.get("Vr") is not None and ev["Vr"] < 48:
            zn.append("výhradní zatížitelnost je nižší než 48 t")
        if Vaj is not None and Vaj < 11.5:
            zn.append("zatížitelnost na jednu nápravu je nižší než 11,5 t")
        if zn:
            K.text("Vyznačení zatížitelnosti (čl. 14.1): " + "; ".join(zn) + " – nutné osadit "
                   "příslušnou dopravní značku, případně dodatkovou tabulku.")
    for druh, z in res.druhy.items():
        r0 = z.prvni
        txt = []
        for s, r in z.schemata.items():
            txt.append(f"{POPIS_SCHEMAT[s]}: referenční {druh} = {fmt(r.V_ref)} t, {r.n_vypoctu} "
                       f"výpočtů posudku, zkoušeno do {fmt(r.V_max)} t")
        K.text(f"{druh} – {NAZVY_DRUHU[druh]} zatížitelnost: {r0.vys.stavy['q'].popis}. "
               f"Chodci: {fmt(r0.vys.q_ch, 2)} kN/m² ({r0.vys.q_ch_zdroj or 'bez chodníků'}). "
               f"Posuzovaný {vyst} {r0.vys.popisky[z.o]}. Schémata: " + "; ".join(txt) + ".")
        for t in z.poznamky:
            K.text("Upozornění: " + t)
        rows = []
        for p in sorted(z.posudky, key=lambda p: (p.V is None, p.V if p.V is not None else 0.0)):
            ms, naz, faze, komb = p.klic
            rows.append([ms, naz, faze, komb or "–", p.text,
                         POPIS_SCHEMAT[p.schema].split(" (")[0] if p.stav == "V" else "–",
                         f"{p.eta_ref * 100:.1f} %", f"{p.eta_0 * 100:.1f} %"])
        K.tabulka(["MS", "Posudek", "Fáze", "Kombinace", f"{druh} [t]", "Schéma",
                   f"η při {druh} = {fmt(z.V_ref)} t", "η bez vozidla"], rows,
                  f"Zatížitelnost {druh} po mezních stavech (seřazeno)")
    K.text(f"Následující protokol je spočten pro {res.druh} = {fmt(vys.V)} t ({res.hlavni.druh} – "
           f"{NAZVY_DRUHU[res.druh]} zatížitelnost, {POPIS_SCHEMAT[vys.schema_q or '']}) – "
           "rozhodující posudek má využití 100 %.")
    model.protokol.kapitoly.insert(0, K)
