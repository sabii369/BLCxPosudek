"""
zatizitelnost.py
================
Výpočet zatížitelnosti: místo posouzení při zadaném zatížení se pro každý mezní
stav (posudek × fáze × kombinace Posudku PB) hledá tíha vozidla Ve [t], při které
je využití η = 100 %.

Postup:
  • model mostu (BLC) se spočte jednou s referenčním Ve (zadané Ve); účinky vozidla
    jsou v Ve lineární (stejné polohy, síly ∝ Ve), pro jiné Ve se stav q přeškáluje,
  • pro zkoušené Ve se spočte celý posudek (nelineární MSÚ, ztráty předpětí, …) –
    jeden výpočet dá využití všech posudků najednou,
  • pro každý posudek: interval Ve, kde η přechází přes 1 (zdvojováním Ve), pak
    regula falsi (Illinois) se sdílenými výpočty, přesnost |η − 1| ≤ tol,
  • posudky, jejichž využití na Ve nezávisí (napínání, minimální výztuž …), se
    označí „nezávisí na Ve“ (vyhovuje / nevyhovuje); neomezující „neomezuje“.
Zatížitelnost = nejmenší Ve přes posudky (zvlášť MSÚ a MSP).  Posuzovaný nosník
je pevný (vybraný při referenčním Ve).  Ostatní zatížení (g0, g − g0, chodci) se
nemění; dynamický součinitel δ násobí Ve.
"""

from __future__ import annotations
import copy
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from blc.vnitrni_sily import StavSil, VysledekSil, vnitrni_sily

TOL = 1e-3              # přesnost využití
TOL_VE = 0.01           # přesnost Ve [t]
STAVY_TEXT = {
    "Ve": "",
    "neomezuje": "neomezuje",
    "nezavisi_ok": "nezávisí na Ve – vyhovuje",
    "nezavisi_nok": "nezávisí na Ve – NEVYHOVUJE",
    "bez_vozidla": "nevyhovuje již bez vozidla",
    "klesa": "η klesá s Ve – neomezuje (bez vozidla nevyhovuje)",
}


@dataclass
class PosudekZat:
    """Zatížitelnost pro jeden posudek (mezní stav)."""
    klic: tuple                  # (mezní stav, název, fáze, kombinace)
    Ve: Optional[float]          # [t]; None = neomezuje / nezávisí
    stav: str                    # klíč STAVY_TEXT
    eta_ref: float               # využití při referenčním Ve
    eta_0: float                 # využití bez vozidla

    @property
    def mezni_stav(self):
        return self.klic[0]

    @property
    def text(self) -> str:
        if self.stav == "Ve":
            return f"{self.Ve:.1f}"
        if self.stav == "bez_vozidla":
            return "0 (" + STAVY_TEXT[self.stav] + ")"
        return STAVY_TEXT[self.stav]


@dataclass
class VysledekZatizitelnosti:
    posudky: List[PosudekZat]
    Ve_ref: float
    Ve_max: float                       # největší zkoušené Ve
    n_vypoctu: int
    vys: Optional[VysledekSil] = None   # most pro Ve = zatížitelnost
    o: int = 0
    model: object = None                # posudek při Ve = zatížitelnost
    poznamky: List[str] = field(default_factory=list)

    def minimum(self, ms: Optional[str] = None) -> Optional[PosudekZat]:
        p = [x for x in self.posudky if x.Ve is not None and (ms is None or x.mezni_stav == ms)]
        return min(p, key=lambda x: x.Ve) if p else None

    @property
    def Ve(self) -> Optional[float]:
        m = self.minimum()
        return None if m is None else m.Ve

    @property
    def nevyhovuji_nezavisle(self) -> List[PosudekZat]:
        return [x for x in self.posudky if x.stav == "nezavisi_nok"]


def klic_posudku(p) -> tuple:
    return (p.mezni_stav, p.nazev, p.faze, p.kombinace)


def vys_pro_Ve(vys: VysledekSil, Ve: float) -> VysledekSil:
    """Kopie výsledku mostu se stavem q přeškálovaným na tíhu vozidla Ve [t]."""
    if not vys.Ve or "q" not in vys.stavy:
        raise ValueError("Zatížitelnost se počítá pro vozidlo Ve (zadejte Ve > 0).")
    k = Ve / vys.Ve
    q = vys.stavy["q"]
    pole = [getattr(q, a) * k for a in ("M_max", "M_min", "Vm_max", "Vm_min", "Vp_max", "Vp_min",
                                         "Vs_max", "Vs_min")]
    stary, novy = f"Ve {vys.Ve:g} t", f"Ve {Ve:.1f} t"
    out = copy.copy(vys)
    out.stavy = dict(vys.stavy)
    out.stavy["q"] = StavSil("q", q.popis.replace(stary, novy), *pole, pohyblivy=True,
                             n_stavu=q.n_stavu)
    out.Ve, out.vozidlo = float(Ve), novy
    if vys.q_nastaveni is not None:
        qn = dict(vys.q_nastaveni)
        puv = vys.q_nastaveni["stavy"]

        def stavy():
            for ax, _ in puv():
                yield [(qq * k, s, e) for qq, s, e in ax], None
        qn["stavy"] = stavy
        out.q_nastaveni = qn
    return out


def zatizitelnost(d: dict, vys: Optional[VysledekSil] = None, o: Optional[int] = None,
                  tol: float = TOL, max_kol: int = 30, nasobek_max: float = 64.0,
                  prubeh=None) -> VysledekZatizitelnosti:
    """Zatížitelnost Ve pro všechny posudky; d = spojená vstupní data (s [blc]).
    prubeh(text) – volitelné hlášení průběhu."""
    from pb_posudek.vstup import model_ze_slovniku
    from .vypocet import parametry_blc, vyber_nosnik, data_pro_posudek, spocti

    if (d.get("blc", {}).get("vozidlo") or "Ve") != "Ve":
        raise ValueError("Výpočet zatížitelnosti je pro vozidlo Ve – zvolte vozidlo Ve.")
    if vys is None:
        vys = vnitrni_sily(**parametry_blc(d))
    if not vys.Ve:
        raise ValueError("Zatížitelnost: zadejte referenční Ve > 0.")
    o = vyber_nosnik(vys, d) if o is None else o
    Vr = float(vys.Ve)
    body: Dict[float, Dict[tuple, float]] = {}

    def eta(Ve: float) -> Dict[tuple, float]:
        Ve = round(float(Ve), 4)
        if Ve not in body:
            m = model_ze_slovniku(data_pro_posudek(vys_pro_Ve(vys, Ve), d, o))
            m.spocitej()
            body[Ve] = {klic_posudku(p): float(p.vyuziti) for p in m.protokol.posudky}
            if prubeh:
                prubeh(f"Zatížitelnost: výpočet {len(body)} (Ve = {Ve:.1f} t)")
        return body[Ve]

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
    for k in klice:
        hodn = [(V, body[V][k]) for V in sorted(body) if k in body[V]]
        rozptyl = max(h for _, h in hodn) - min(h for _, h in hodn)
        if rozptyl < 1e-6:
            vysl[k] = PosudekZat(k, None, "nezavisi_nok" if e0[k] > 1.0 + 1e-9 else "nezavisi_ok",
                                 er[k], e0[k])
            continue
        if e0[k] >= 1.0:
            # η klesá s Ve (např. křehký lom) – nevyhovuje jen při malém zatížení, Ve neomezuje
            stav = "klesa" if min(h for _, h in hodn) < 1.0 else "bez_vozidla"
            vysl[k] = PosudekZat(k, 0.0 if stav == "bez_vozidla" else None, stav, er[k], e0[k])
            continue
        i = next((j for j, (_, h) in enumerate(hodn) if h >= 1.0), None)
        if i is None:
            vysl[k] = PosudekZat(k, None, "neomezuje", er[k], e0[k])
            continue
        (a, fa), (b, fb) = hodn[i - 1], hodn[i]
        interval[k] = [a, fa - 1.0, b, fb - 1.0, 0]

    # ---- Illinois (regula falsi) se sdílenými výpočty -------------------------
    for _ in range(max_kol):
        hotove, plan = [], {}
        for k, (a, fa, b, fb, _) in interval.items():
            if b - a <= TOL_VE:
                hotove.append(k)
                continue
            c = a + (b - a) * (-fa) / (fb - fa) if fb != fa else 0.5 * (a + b)
            c = min(max(c, a + 1e-6), b - 1e-6)
            # sdílet blízký již plánovaný / spočtený výpočet
            blizky = [V for V in list(body) + list(plan.values()) if a < V < b and abs(V - c) <= 2e-3 * c]
            plan[k] = blizky[0] if blizky else c
        for k in hotove:
            a, fa, b, fb, _ = interval.pop(k)
            Ve = a + (b - a) * (-fa) / (fb - fa) if fb != fa else 0.5 * (a + b)
            vysl[k] = PosudekZat(k, Ve, "Ve", er[k], e0[k])
        if not interval:
            break
        for k, c in plan.items():
            if k not in interval:
                continue
            fc = eta(c).get(k, 1.0) - 1.0
            a, fa, b, fb, strana = interval[k]
            if abs(fc) <= tol:
                interval.pop(k)
                vysl[k] = PosudekZat(k, c, "Ve", er[k], e0[k])
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
        vysl[k] = PosudekZat(k, a + (b - a) * (-fa) / (fb - fa) if fb != fa else 0.5 * (a + b),
                             "Ve", er[k], e0[k])

    res = VysledekZatizitelnosti([vysl[k] for k in klice], Vr, Vmax, len(body))
    if res.nevyhovuji_nezavisle:
        res.poznamky.append(f"{len(res.nevyhovuji_nezavisle)} posudků nevyhovuje nezávisle na Ve "
                            "(předpětí, výstavba) – zatížitelnost je neomezují, ale konstrukce je "
                            "nutné posoudit.")
    # ---- posudek při Ve = zatížitelnost (protokol, grafy) --------------------
    Ve_fin = res.Ve if res.Ve is not None and res.Ve > 0 else Vr
    if prubeh:
        prubeh(f"Zatížitelnost: posudek při Ve = {Ve_fin:.1f} t")
    vk, o, model = spocti(d, vys_pro_Ve(vys, Ve_fin), o)
    res.vys, res.o, res.model = vk, o, model
    model.zatizitelnost = res
    kapitola_zatizitelnost(model, res)
    return res


def kapitola_zatizitelnost(model, res: VysledekZatizitelnosti) -> None:
    """Kapitola protokolu se zatížitelností (na začátek protokolu)."""
    from pb_posudek.protokol import Kapitola, fmt
    K = Kapitola("Zatížitelnost – tíha vozidla Ve pro dosažení mezních stavů", 1)
    m_all, m_su, m_sp = res.minimum(), res.minimum("MSÚ"), res.minimum("MSP")
    vys = res.vys
    K.text(f"Pro každý posudek (mezní stav, fáze, kombinace) byla hledána tíha vozidla Ve, při které "
           f"je využití η = 100 % (iterací celého posudku; účinky vozidla z modelu mostu přeškálované "
           f"z referenční hodnoty Ve = {fmt(res.Ve_ref)} t, dynamický součinitel δ = {fmt(vys.dyn)}). "
           f"Ostatní zatížení – g0, g − g0, chodci – zůstávají. Posuzovaný "
           f"{'pás' if vys.deska else 'nosník'} {vys.popisky[res.o]}; počet výpočtů posudku "
           f"{res.n_vypoctu}, zkoušeno Ve ≤ {fmt(res.Ve_max)} t.")
    if m_all is not None:
        K.krok("Zatížitelnost Ve (rozhoduje: " + f"{m_all.klic[0]} {m_all.klic[1]} – {m_all.klic[2]})",
               "", "", round(m_all.Ve, 1), "t")
    else:
        K.text("Žádný posudek závislý na Ve nedosáhne η = 100 % do zkoušeného Ve – zatížitelnost "
               f"je větší než {fmt(res.Ve_max)} t.")
    for naz, mm in (("MSÚ", m_su), ("MSP", m_sp)):
        if mm is not None:
            K.krok(f"Nejmenší Ve – {naz} ({mm.klic[1]}, {mm.klic[2]})", "", "", round(mm.Ve, 1), "t")
    for t in res.poznamky:
        K.text("Upozornění: " + t)
    rows = []
    for p in sorted(res.posudky, key=lambda p: (p.Ve is None, p.Ve if p.Ve is not None else 0.0)):
        ms, naz, faze, komb = p.klic
        rows.append([ms, naz, faze, komb or "–", p.text, f"{p.eta_ref * 100:.1f} %",
                     f"{p.eta_0 * 100:.1f} %"])
    K.tabulka(["MS", "Posudek", "Fáze", "Kombinace", "Ve [t]", f"η při Ve = {res.Ve_ref:g} t",
               "η bez vozidla"], rows, "Zatížitelnost po mezních stavech (seřazeno podle Ve)")
    K.text(f"Následující protokol je spočten pro Ve = {fmt(vys.Ve)} t (zatížitelnost) – rozhodující "
           "posudek má využití 100 %.")
    model.protokol.kapitoly.insert(0, K)
