"""
comparison.py
=============
Porovnání vozidla MLC a výjimečné zatížitelnosti Ve na spojitém nosníku
po kontrolních řezech.

Postup:
  1. 1D analýza (beam_1d.py): pro každý kontrolní řez nejhorší poloha MLC a Ve.
  2. 2D příčný roznos: pro každý řez se nejhorší poloha zadá do 2D MKP desky
     a z výsledku se přečte hodnota na každém nosníku.
  3. Využití = max_i(MLC_i) / max_i(Ve_i) v každém řezu; rozhoduje řez
     s největším využitím.
  4. Obálky M_i(x), V_i(x) na každém nosníku z pojezdu po 2D desce
     (pravidelná mřížka poloh, oba směry jízdy).

Typ konstrukce "nosniky" (výstupy = nosníky) nebo "deska" (výstupy =
pásy šířky 1 m, hodnoty zintegrované na 1 m, jen podélný směr), šikmost
alfa/prava|leva.  1D analýza probíhá v rámci osy vozidla (podpory v místě,
kde osa vozidla protíná šikmé osy podpor); do 2D se zatížení posune o
x0(y_vozidla).

Okrajové podmínky podpor (uloz = "tvrde" | "mekke" | "vetknuti", k_rot)
jednou pro celý most – platí v 1D i ve 2D; u vetknutí přibudou řezy M- nad
krajními podporami.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Union

import numpy as np

from .geometry import Konstrukce, Rez, E_betonu
from .beam_1d import (Nosnik1D, Beam1DResult, vypocet_MLC, vypocet_Ve)
from .plate_fem import (DeskaMKP, StavMKP, Obalky2D, Vystupy, reseni_stavu, SitMKP, sit_modelu,
                        hodnoty_rezu, obalky_2D)


@dataclass
class RezVysledek:
    rez: Rez
    # ---- 1D (celý most bez příčného roznosu) ----
    MLC_1D: float
    Ve_1D: float
    vyuziti_1D: float                # %
    # ---- 2D (nejvíc namáhaný nosník) ----
    MLC_nos: np.ndarray              # hodnoty na nosnících [kNm | kN]
    Ve_nos: np.ndarray
    k_MLC: int                       # nejvíc namáhaný nosník (1-based)
    k_Ve: int
    MLC_2D: float
    Ve_2D: float
    vyuziti_2D: float                # %
    x_MLC: float                     # poloha rozhodujícího řezu vůči čelu výstupu [m]
    x_Ve: float
    eta_MLC: np.ndarray              # příčné součinitele (hodnota / průměr)
    eta_Ve: np.ndarray
    axles_MLC: list
    axles_Ve: list
    stav_MLC: Optional[StavMKP] = None
    stav_Ve: Optional[StavMKP] = None
    xg_MLC: float = 0.0              # poloha řezu v rámci 2D (globální x) [m]
    xg_Ve: float = 0.0
    deska: bool = False

    @property
    def jednotka(self) -> str:
        j = "kNm" if self.rez.typ != "V" else "kN"
        return j + "/m" if self.deska else j


@dataclass
class ComparisonResult:
    K: Konstrukce
    typ: str
    MLC: str
    Ve: float
    res_MLC: Beam1DResult
    res_Ve: Beam1DResult
    rezy: List[RezVysledek]
    y_c_MLC: float
    y1_MLC: float = 0.0
    y2_MLC: float = 0.0
    popis: str = ""
    roz: float = 0.0
    y1_Ve: float = 0.0
    y2_Ve: float = 0.0
    b_k_MLC: float = 0.0
    b_k_Ve: float = 0.0
    ob_MLC: Optional[Obalky2D] = None     # obálky na nosnících (2D)
    ob_Ve: Optional[Obalky2D] = None
    vyst: Optional[Vystupy] = None        # výstupy (nosníky / pásy 1 m)
    dx_MLC: float = 0.0                   # posun zatížení 1D → 2D [m]
    dx_Ve: float = 0.0
    p_xsup: Optional[np.ndarray] = None   # polohy podpor pruhů v 2D
    p_y0: Optional[np.ndarray] = None
    p_w: Optional[np.ndarray] = None
    p_typ: Optional[np.ndarray] = None
    p_xod: Optional[np.ndarray] = None    # nosníky: začátek a konec pruhu v 2D [m]
    p_xdo: Optional[np.ndarray] = None
    varovani: List[str] = None
    sit: Optional[SitMKP] = None          # síť MKP (pro vykreslení)

    def __post_init__(self):
        if self.varovani is None:
            self.varovani = []

    @property
    def n_vyst(self) -> int:
        return self.vyst.n if self.vyst is not None else self.K.N

    @property
    def popisky(self) -> List[str]:
        return self.vyst.popisky if self.vyst is not None else [
            f"N{k + 1}" for k in range(self.K.N)]

    def popisek(self, k: int) -> str:
        """Popisek výstupu k (1-based)."""
        return self.popisky[k - 1]

    # ---- vyhodnocení ----
    @property
    def rozhodujici(self) -> RezVysledek:
        return max(self.rezy, key=lambda r: r.vyuziti_2D)

    def rozhodujici_typ(self, typ: str) -> Optional[RezVysledek]:
        """Rozhodující řez daného druhu: "M" (M+ i M-) nebo "V"."""
        rr = [r for r in self.rezy if (r.rez.typ == "V") == (typ == "V")]
        return max(rr, key=lambda r: r.vyuziti_2D) if rr else None

    @property
    def rozhodujici_1D(self) -> RezVysledek:
        return max(self.rezy, key=lambda r: r.vyuziti_1D)

    @property
    def max_vyuziti(self) -> float:
        return max(r.vyuziti_2D for r in self.rezy)

    @property
    def max_vyuziti_1D(self) -> float:
        return max(r.vyuziti_1D for r in self.rezy)

    @property
    def projde(self) -> bool:
        return self.max_vyuziti < 100.0

    @property
    def projde_1D(self) -> bool:
        return self.max_vyuziti_1D < 100.0

    @property
    def N(self) -> int:
        return self.K.N

    @property
    def L(self) -> float:
        return self.K.Ltot


def _klic(axles) -> tuple:
    return tuple((round(q, 6), round(s, 6), round(e, 6)) for q, s, e in axles)


def porovnani_zatizeni(
    typ: str,
    MLC: str,
    L: Union[float, List[float]],
    n: int,
    dist: float,
    Ve: float,
    N: int,
    E: Optional[float] = None,
    Iy: float = 0.0,
    b: float = 1.0,
    nu: float = 0.2,
    d: float = 0.0,
    beton: Optional[str] = None,
    spara: bool = False,
    b_s: float = 0.0,
    Iy_s: float = 0.0,
    beton_s: Optional[str] = None,
    E_s: Optional[float] = None,
    y_center_MLC: Optional[float] = None,
    spoj: str = "kloub",
    roznos: bool = True,
    t_voz: float = 0.0,
    ex: float = 0.0625,
    obalky: bool = True,
    n_obalky: Optional[int] = None,
    krok_obalky: Optional[float] = 0.5,
    typ_konstrukce: str = "nosniky",
    h: float = 0.0,
    alfa: float = 90.0,
    sikmost: str = "prava",
    k_pod: Optional[float] = None,
    uloz: str = "tvrde",
    k_rot: Optional[float] = None,
    beta_s_pevne: bool = False,
    tisk: bool = True,
) -> ComparisonResult:
    """
    Args:
        typ, MLC:     „k"/„p" a třída MLC.
        L:            rozpětí [m]: jedno číslo (1 pole) nebo seznam (více polí).
        n:            počet poloh vozidla na jedno pole.
        dist:         vzdálenost vozidel v koloně [m].
        Ve:           výjimečná zatížitelnost [t].
        N, b:         počet nosníků a šířka nosníku [m] (bez spáry = rozteč).
        E, Iy, nu:    modul pružnosti [MPa], moment setrvačnosti nosníku [m⁴], ν.
        beton:        třída betonu (např. "C30/37") → E = Ecm; má přednost před E.
        spara:        podélná spára mezi nosníky (kloubově připojený deskový prvek).
        b_s, Iy_s:    šířka [m] a moment setrvačnosti [m⁴] spáry.
        beton_s, E_s: třída betonu spáry (→ E_s = Ecm) nebo přímo E_s [MPa];
                      není-li zadáno, spára má beton nosníků.
        d:            statická účinná výška [m] — V se posuzuje ve vzdálenosti d
                      od podpory; zatížení smí stát kdekoli (i v pásu d).
        y_center_MLC: příčná poloha středu vozidla MLC [m] (None = střed).
        spoj:         "kloub" | "deska" (propojení pruhů).
        roznos, t_voz: podélný i příčný roznos plošky.
        ex:           délka prvku MKP podél rozpětí [m].
        obalky:       spočítat obálky na jednotlivých nosnících (2D pojezd).
        n_obalky:     počet poloh na pole pro 2D obálky (None = n).
        krok_obalky:  krok poloh vozidla pro 2D obálky [m] (má přednost před
                      n_obalky; jemný krok = hladší obálky, delší výpočet).
        typ_konstrukce: "nosniky" | "deska" (deska: b = šířka desky, h = tloušťka,
                      N, Iy, spáry se nepoužijí; výsledky na pás 1 m).
        k_pod:        svislá tuhost podpory [kN/m na 1 m délky podpory];
                      None / 0 = tuhá podpora.
        uloz:         okrajové podmínky podpor: "tvrde" – kloubové tvrdé
                      (β_s = 0; u pružné podpory β_s = ∂w/∂s), "mekke" – kloubové
                      měkké (rotace volné), "vetknuti" – vetknutí (β_n = 0).
        k_rot:        tuhost pružného vetknutí [kNm/rad na 1 m délky podpory];
                      None / 0 = dokonalé vetknutí (jen uloz = "vetknuti").
        beta_s_pevne: True = β_s = 0 i u pružné podpory (zjednodušená vazba, odpovídá
                      SCIA s vetknutou rotací podél osy podpory; parazitní smyk).
        alfa, sikmost: úhel šikmosti [°] (90 = kolmý, šikmost roste k 180° – teoretická
                      mez; povoleno 90–165°) a druh "prava" | "leva".
    Podpory jsou liniové; okrajové podmínky viz uloz, k_rot, k_pod.
    """
    Lp = [float(L)] if np.isscalar(L) else [float(v) for v in L]
    if beton:
        E = E_betonu(beton)
    if E is None:
        raise ValueError("Zadejte třídu betonu nebo modul pružnosti E.")
    if beton_s:
        E_s = E_betonu(beton_s)
    K = Konstrukce(L=Lp, N=N, b=b, E=E, Iy=Iy, nu=nu, d=d,
                   spara=spara, b_s=b_s, Iy_s=Iy_s, E_s=E_s,
                   typ=typ_konstrukce, h=h, alfa=alfa, sikmost=sikmost, k_pod=k_pod,
                   uloz=uloz, k_rot=k_rot, beta_s_pevne=beta_s_pevne)

    # podélný roznos plošky (shodný s 2D MKP)
    roz = (K.h_ekv if roznos else 0.0) + 2.0 * t_voz

    # ===== 1. 1D analýza ==================================================
    nos = Nosnik1D(K)
    res_MLC = vypocet_MLC(nos, typ, MLC, n, dist, roz)
    res_Ve = vypocet_Ve(nos, Ve, n, roz)

    # ===== 2. příčné polohy stop ===========================================
    B = K.B
    y_c = y_center_MLC if y_center_MLC is not None else 0.5 * B
    y1_M, y2_M = y_c - 0.5 * res_MLC.rozvor, y_c + 0.5 * res_MLC.rozvor
    y1_V, y2_V = 0.5 * B - 0.5 * res_Ve.rozvor, 0.5 * B + 0.5 * res_Ve.rozvor

    # ===== 3. 2D příčný roznos pro každý kontrolní řez ====================
    if K.je_deska:
        from .slab_fem import DeskaSikmaMKP
        model = DeskaSikmaMKP(K, ex=ex)
    else:
        model = DeskaMKP(K, ex=ex, ney=4, spoj=spoj)
    Nv = model.vyst.n
    dx_M, dx_V = K.x0(y_c), K.x0(0.5 * B)     # posun 1D → 2D (šikmost)
    cache = {}

    def stav(axles, y1, y2, b_k, dx):
        key = (_klic(axles), round(y1, 6), round(y2, 6), round(b_k, 6), round(dx, 9))
        if key not in cache:
            cache[key] = reseni_stavu(model, axles, y1, y2, b_k, roz, dx)
        return cache[key]

    rezy: List[RezVysledek] = []
    for cM, cV in zip(res_MLC.cile, res_Ve.cile):
        sM = stav(cM.axles, y1_M, y2_M, res_MLC.b_k, dx_M)
        sV = stav(cV.axles, y1_V, y2_V, res_Ve.b_k, dx_V)
        vM, xM, xgM = hodnoty_rezu(sM, cM.rez, K.d)
        vV, xV, xgV = hodnoty_rezu(sV, cV.rez, K.d)
        mM, mV = float(vM.max()), float(vV.max())
        sumM, sumV = vM.sum(), vV.sum()
        rezy.append(RezVysledek(
            rez=cM.rez,
            MLC_1D=cM.hodnota, Ve_1D=cV.hodnota,
            vyuziti_1D=100.0 * cM.hodnota / cV.hodnota if cV.hodnota > 1e-9 else 0.0,
            MLC_nos=vM, Ve_nos=vV,
            k_MLC=int(np.argmax(vM)) + 1, k_Ve=int(np.argmax(vV)) + 1,
            MLC_2D=mM, Ve_2D=mV,
            vyuziti_2D=100.0 * mM / mV if mV > 1e-9 else 0.0,
            x_MLC=xM, x_Ve=xV,
            eta_MLC=vM / (sumM / Nv) if sumM > 1e-9 else np.ones(Nv),
            eta_Ve=vV / (sumV / Nv) if sumV > 1e-9 else np.ones(Nv),
            axles_MLC=cM.axles, axles_Ve=cV.axles,
            stav_MLC=sM, stav_Ve=sV, xg_MLC=xgM, xg_Ve=xgV, deska=K.je_deska,
        ))

    # ===== 4. obálky na jednotlivých nosnících ============================
    ob_M = ob_V = None
    if obalky:
        n_ob = n if n_obalky is None else n_obalky
        if krok_obalky is not None and krok_obalky > 0:
            n_ob = max(1, int(np.ceil(K.Ltot / (krok_obalky * K.n_poli))))
        ob_M = obalky_2D(model, nos.stavy_MLC(typ, MLC, n_ob, dist, roz, extra=False),
                         y1_M, y2_M, res_MLC.b_k, roz, dx_M)
        ob_V = obalky_2D(model, nos.stavy_Ve(Ve, n_ob, roz, extra=False),
                         y1_V, y2_V, res_Ve.b_k, roz, dx_V)

    if K.je_deska:
        spoj_txt = (f"deska {K.b:g} × {K.h:g} m, pruhy {model.p_w[0]:.3f} m, "
                    f"výsledky na pás 1 m")
    else:
        spoj_txt = ("spáry (kloubově, bez podpory)" if K.spara else
                    ("kloubové" if spoj != "deska" else "tuhé") + " spojení")
    sik = (f", šikmost {K.alfa:g}° {'pravá' if K.sikmost == 'prava' else 'levá'}"
           if K.sikmy else "")
    pod = f"liniové podpory: {K.popis_ulozeni()}"
    popis = (f"2D MKP (MITC4), prvek ≈ {model.a_ref:.3f} × {model.c:.3f} m, "
             f"{spoj_txt}, {pod}{sik}, roznos {roz:.2f} m")

    varovani = []
    if K.sikmy and not K.je_deska and not K.spara and K.N > 1:
        varovani.append(
            "Šikmé nosníky spojené kloubem přímo (bez spáry): posunuté liniové podpory "
            "sousedních nosníků se přes kloub navzájem podpírají a konce nosníků jsou "
            "částečně vetknuté – vliv šikmosti (pokles M+, koncentrace reakcí) je "
            "nadsazený. Doporučeno modelovat spáru.")
    if K.pruzna and K.tvrde and K.beta_s_pevne:
        varovani.append(
            "β_s = 0 i u pružné podpory (zjednodušená vazba): podél podpory vzniká parazitní smyk "
            "κGh·∂w/∂s – u šikmých mostů zkresluje V u podpor a reakce (jen pro srovnání).")
    if K.uloz == "mekke":
        varovani.append(
            "Měkké uložení: u podpory vzniká okrajová vrstva (šířka ~h) – posouvající "
            "síly u podpor pomalu konvergují se sítí (doporučen prvek ≤ 0,0625 m).")
    if K.vetknuti and not K.je_deska and K.spara:
        varovani.append(
            "Vetknutí u nosníků se spárou: spára nemá vlastní podporu, vetknuty jsou "
            "jen nosníky.")
    cr = ComparisonResult(K=K, typ=typ, MLC=MLC, Ve=Ve, res_MLC=res_MLC, res_Ve=res_Ve,
                          rezy=rezy, y_c_MLC=y_c, y1_MLC=y1_M, y2_MLC=y2_M,
                          popis=popis, roz=roz, y1_Ve=y1_V, y2_Ve=y2_V,
                          b_k_MLC=res_MLC.b_k, b_k_Ve=res_Ve.b_k,
                          ob_MLC=ob_M, ob_Ve=ob_V, vyst=model.vyst,
                          dx_MLC=dx_M, dx_Ve=dx_V, p_xsup=model.p_xsup,
                          p_y0=model.p_y0, p_w=model.p_w, p_typ=model.p_typ,
                          p_xod=model.xs[model.p_i0], p_xdo=model.xs[model.p_i1],
                          varovani=varovani, sit=sit_modelu(model))
    if tisk:
        vypis(cr)
    return cr


def vypis(cr: ComparisonResult) -> None:
    K = cr.K
    print("=" * 78)
    print(f"  VÝSLEDKY – DESKOVÝ MODEL, SPOJITÝ NOSNÍK    {cr.MLC} vs Ve = {cr.Ve} t")
    print("=" * 78)
    if K.je_deska:
        print(f"  DESKA {K.popis()},  b = {K.b} m,  h = {K.h} m,  d = {K.d} m,  "
              f"E = {K.E:g} MPa   (2D hodnoty na pás 1 m)")
    else:
        print(f"  {K.popis()},  N = {K.N},  b = {K.b} m,  d = {K.d} m,  E = {K.E:g} MPa")
        print(f"  Ekvivalentní tloušťka desky nosníku: h = {K.h_ekv:.4f} m")
    if K.spara:
        print(f"  Spára: b_s = {K.b_s:g} m, Iy_s = {K.Iy_s:.5g} m⁴, h_s = {K.h_spary:.4f} m, "
              f"E_s = {K.E_spary:g} MPa, "
              f"osová vzdálenost nosníků {K.rozted:g} m, B = {K.B:g} m")
    print(f"  Uložení: {K.popis_ulozeni()}")
    print(f"  Metoda: {cr.popis}")
    print()
    print(f"  {'Řez':<24}{'x [m]':>8}{'MLC 1D':>10}{'Ve 1D':>10}{'η 1D':>8}"
          f"{'MLC 2D':>10}{'Ve 2D':>10}{'η 2D':>8}  {'pás' if K.je_deska else 'nos.'}")
    print("  " + "-" * 92)
    for r in cr.rezy:
        x = r.rez.x if r.rez.typ != "M+" else r.x_MLC
        print(f"  {r.rez.id:<24}{x:>8.2f}{r.MLC_1D:>10.1f}{r.Ve_1D:>10.1f}{r.vyuziti_1D:>7.1f}%"
              f"{r.MLC_2D:>10.1f}{r.Ve_2D:>10.1f}{r.vyuziti_2D:>7.1f}%  {cr.popisek(r.k_MLC)}/{cr.popisek(r.k_Ve)}"
              )
    g = cr.rozhodujici
    print()
    print(f"  Rozhoduje: {g.rez.id}  –  využití {g.vyuziti_2D:.1f} %  "
          f"→ {'PROJDE' if cr.projde else 'NEPROJDE'}  (1D: {cr.max_vyuziti_1D:.1f} %)")
    for t in cr.varovani:
        print(f"  ! {t}")
    print("=" * 78)
