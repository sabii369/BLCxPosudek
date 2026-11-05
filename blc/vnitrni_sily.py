"""
vnitrni_sily.py
===============
Vnitřní síly na jednotlivých nosnících (u desky na pásech 1 m) od zatěžovacích
stavů pro posudek nosníku (modul Posudek PB):

  g0     vlastní tíha nosné konstrukce
           • nosníky: každý nosník SAMOSTATNĚ, bez spolupůsobení (1D spojitý
             nosník o polích K.L se stejným uložením jako most), g0 = A·γ_b,
           • deska: 2D MKP, g0 = h·γ_b po celé ploše,
  g-g0   ostatní stálé zatížení – 2D MKP (příčný roznos):
           skladba vozovky, skladba chodníků, svodidla, zábradlí, další liniová;
           u nosníků se spárou navíc tíha výplně spáry g_spary [kN/m] – nese ji
           SAMOSTATNĚ sousední dvojice nosníků (každý polovinu, před zmonolitněním),
  q      pohyblivé zatížení – pojezd JEDNOHO vybraného vozidla po 2D desce
           (obálka max/min, oba směry jízdy): Ve (výjimečná zatížitelnost) nebo
           vozidlo MLC (kolové / pásové; volitelně kolona), osa vozidla v ose
           vozovky nebo zadaná, volitelně dynamický součinitel.

Model konstrukce (MKP, okrajové podmínky, šikmost, spáry) je totožný
s porovnáním MLC / Ve (comparison.py).  Výsledky jsou na síti 2D modelu;
pro každý výstup (nosník / pás 1 m) se dají vypsat jako tabulka
x [m od osy první podpory výstupu], M_max, M_min, V_max, V_min.

Znaménka: kladný M táhne dolní vlákna, V = dM/dx (kladná u levé podpory).
Jednotky: kN, m (deska: hodnoty na pás 1 m → kNm/m, kN/m).
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

import numpy as np

from .geometry import Konstrukce, E_betonu
from .beam_1d import Nosnik1D, VE_ROZVOR, VE_B_K
from .vehicles import kolove_vozidlo, pasove_vozidlo
from .plate_fem import DeskaMKP, Vystupy, obalky_2D, sit_modelu, SitMKP
from .stale_zatizeni import Vybaveni, platky_plosne

GAMMA_BETON = 25.0               # objemová tíha železobetonu [kN/m³]
STAVY = ("g0", "g-g0", "q")
NAZVY_STAVU = {
    "g0": "vlastní tíha g0",
    "g-g0": "ostatní stálé g − g0",
    "q": "pohyblivé q",
}
DRUHY_KOMBINACI = ("6.10a", "6.10b", "6.10", "char", "casta", "kvazistala")


# ---------------------------------------------------------------------------
# Součinitele kombinací (ČSN EN 1990) – pro export do posudku a výběr nosníku
# ---------------------------------------------------------------------------

@dataclass
class Soucinitele:
    """Dílčí součinitele a součinitele kombinace.  Výchozí ψ odpovídají
    tandemové soustavě TS (ČSN EN 1990, tab. A2.1) – pro vozidlo Ve
    je nutné je ověřit / upravit podle zadání hodnocení."""
    gamma_G: float = 1.35
    gamma_G_inf: float = 1.0
    xi: float = 0.85
    gamma_Q: float = 1.35
    psi0: float = 0.75
    psi1: float = 0.75
    psi2: float = 0.0

    def faktory(self, druh: str):
        """(γ_sup stálého, γ_inf stálého, součinitel q) pro kombinaci."""
        g, gi, gq = self.gamma_G, self.gamma_G_inf, self.gamma_Q
        return {
            "6.10a": (g, gi, gq * self.psi0),
            "6.10b": (self.xi * g, gi, gq),
            "6.10": (g, gi, gq),
            "char": (1.0, 1.0, 1.0),
            "casta": (1.0, 1.0, self.psi1),
            "kvazistala": (1.0, 1.0, self.psi2),
        }[druh]


# ---------------------------------------------------------------------------
# Výsledky
# ---------------------------------------------------------------------------

@dataclass
class StavSil:
    """Zatěžovací stav na všech výstupech, pole (n_vyst, nx) na síti 2D modelu.
    Vm = V(x⁻), Vp = V(x⁺), Vs = ½(Vm + Vp).  U stálých stavů max = min."""
    nazev: str
    popis: str
    M_max: np.ndarray
    M_min: np.ndarray
    Vm_max: np.ndarray
    Vm_min: np.ndarray
    Vp_max: np.ndarray
    Vp_min: np.ndarray
    Vs_max: np.ndarray
    Vs_min: np.ndarray
    pohyblivy: bool = False
    n_stavu: int = 1

    @classmethod
    def staly(cls, nazev: str, popis: str, M, Vm, Vp) -> "StavSil":
        Vs = 0.5 * (Vm + Vp)
        return cls(nazev, popis, M, M.copy(), Vm, Vm.copy(), Vp, Vp.copy(), Vs, Vs.copy())

    @classmethod
    def nula(cls, nazev: str, popis: str, shape) -> "StavSil":
        z = np.zeros(shape)
        return cls.staly(nazev, popis, z, z.copy(), z.copy())

    def __add__(self, o: "StavSil") -> "StavSil":
        """Součet dvou stálých stavů (pohyblivý stav se nesčítá)."""
        if self.pohyblivy or o.pohyblivy:
            raise ValueError("Sčítat lze jen stálé stavy.")
        return StavSil.staly(self.nazev, self.popis, self.M_max + o.M_max,
                             self.Vm_max + o.Vm_max, self.Vp_max + o.Vp_max)


@dataclass
class TabulkaSil:
    """Průběh vnitřních sil jednoho výstupu (nosníku / pásu).
    x [m] od osy první podpory výstupu; nad vnitřní podporou dva řádky
    se stejným x (V vlevo a vpravo od podpory)."""
    x: np.ndarray
    M_max: np.ndarray
    M_min: np.ndarray
    V_max: np.ndarray
    V_min: np.ndarray

    @property
    def V_abs(self) -> np.ndarray:
        return np.maximum(np.abs(self.V_max), np.abs(self.V_min))


@dataclass
class VysledekSil:
    K: Konstrukce
    vybaveni: Vybaveni
    xs: np.ndarray                      # uzly sítě 2D modelu (globální x / ξ)
    vyst: Vystupy
    stavy: Dict[str, StavSil]
    g0: float                           # nosníky: g0 [kN/m] na nosník; deska: [kN/m²]
    g_spary: float = 0.0                # tíha výplně spáry [kN/m]
    Ve: float = 0.0                     # [t] (jen vozidlo Ve)
    dyn: float = 1.0
    y_Ve: float = 0.0                   # osa vozidla [m]
    vozidlo: str = ""                   # popis vozidla („Ve 80 t“, „MLC80 kolové“)
    rozvor: float = VE_ROZVOR           # osová vzdálenost stop vozidla [m]
    b_k: float = VE_B_K                 # šířka stopy [m]
    roz: float = 0.0                    # podélný / příčný roznos plošky [m]
    soucinitele: Soucinitele = field(default_factory=Soucinitele)
    popis: str = ""
    varovani: List[str] = field(default_factory=list)
    kontrola: Dict[str, float] = field(default_factory=dict)
    sit: Optional[SitMKP] = None
    y_vyst: Optional[np.ndarray] = None

    # ---- základní údaje --------------------------------------------------
    @property
    def n_vyst(self) -> int:
        return self.vyst.n

    @property
    def popisky(self) -> List[str]:
        return list(self.vyst.popisky)

    @property
    def deska(self) -> bool:
        return self.K.je_deska

    @property
    def jednotky(self):
        return ("kNm/m", "kN/m") if self.deska else ("kNm", "kN")

    def index(self, vystup: Union[int, str]) -> int:
        """Index výstupu (0-based) z čísla (1-based) nebo popisku („N3“)."""
        if isinstance(vystup, str):
            if vystup not in self.popisky:
                raise ValueError(f"Neznámý výstup '{vystup}'.")
            return self.popisky.index(vystup)
        if not 1 <= vystup <= self.n_vyst:
            raise ValueError(f"Výstup musí být 1 … {self.n_vyst}.")
        return int(vystup) - 1

    # ---- tabulky ----------------------------------------------------------
    def _radky(self, o: int):
        """[(uzel, strana)] výstupu o; strana "p" = V(x⁺), "m" = V(x⁻), "s" = ½(…)."""
        i0, i1 = int(self.vyst.i0[o]), int(self.vyst.i1[o])
        skoky = set(int(k) for k in self.vyst.skoky[o]) - {i0, i1}
        out = []
        for k in range(i0, i1 + 1):
            if k == i0:
                out.append((k, "p"))
            elif k == i1:
                out.append((k, "m"))
            elif k in skoky:
                out += [(k, "m"), (k, "p")]
            else:
                out.append((k, "s"))
        return out

    def x_lokalni(self, o: int) -> np.ndarray:
        return self.xs - float(self.vyst.x0[o])

    def tabulka(self, o: int, stav: str) -> TabulkaSil:
        """Průběh stavu `stav` ("g0" | "g-g0" | "q") na výstupu o (0-based)."""
        if stav not in self.stavy:
            raise ValueError(f"Stav '{stav}' nebyl spočten.")
        s = self.stavy[stav]
        r = self._radky(o)
        k = np.array([a for a, _ in r], dtype=int)
        st = np.array([b for _, b in r])
        V = {"m": (s.Vm_max, s.Vm_min), "p": (s.Vp_max, s.Vp_min), "s": (s.Vs_max, s.Vs_min)}
        Vmax = np.array([V[t][0][o, kk] for kk, t in zip(k, st)])
        Vmin = np.array([V[t][1][o, kk] for kk, t in zip(k, st)])
        x = self.x_lokalni(o)[k]
        x[0] = 0.0
        return TabulkaSil(x, s.M_max[o, k].copy(), s.M_min[o, k].copy(), Vmax, Vmin)

    def kombinace(self, o: int, druh: str, vcetne_g0: bool = False) -> TabulkaSil:
        """Obálka kombinace (ČSN EN 1990) na výstupu o:
        G = (g0 +) (g − g0), Q = q;  M_max = Σ max(γ_sup·G, γ_inf·G) + f_Q·Q_max."""
        if druh not in DRUHY_KOMBINACI:
            raise ValueError(f"Neznámá kombinace '{druh}'.")
        gs, gi, fq = self.soucinitele.faktory(druh)
        stale = (["g0"] if vcetne_g0 else []) + ["g-g0"]
        t0 = self.tabulka(o, stale[0])
        out = TabulkaSil(t0.x.copy(), *[np.zeros_like(t0.x) for _ in range(4)])
        for s in stale:
            t = self.tabulka(o, s)
            for a in ("M_max", "V_max"):
                v = getattr(t, a)
                getattr(out, a)[:] += np.maximum(gs * v, gi * v)
            for a, b in (("M_min", "M_max"), ("V_min", "V_max")):
                v = getattr(t, b)
                getattr(out, a)[:] += np.minimum(gs * v, gi * v)
        if "q" in self.stavy:
            t = self.tabulka(o, "q")
            for a in ("M_max", "M_min", "V_max", "V_min"):
                getattr(out, a)[:] += fq * getattr(t, a)
        return out

    # ---- souhrn a výběr nejzatíženějšího výstupu -------------------------
    def souhrn(self) -> List[dict]:
        """Pro každý výstup: max M a max |V| jednotlivých stavů a MSÚ (6.10, s g0)."""
        out = []
        for o in range(self.n_vyst):
            d = {"vystup": self.popisky[o], "y": float(self.vyst.y[o])}
            for s in self.stavy:
                t = self.tabulka(o, s)
                d[f"M_{s}"] = float(t.M_max.max())
                d[f"Mmin_{s}"] = float(t.M_min.min())
                d[f"V_{s}"] = float(t.V_abs.max())
            k = self.kombinace(o, "6.10", vcetne_g0=True)
            d["M_Ed"] = float(k.M_max.max())
            d["Mmin_Ed"] = float(k.M_min.min())
            d["V_Ed"] = float(k.V_abs.max())
            out.append(d)
        return out

    def rozhodujici(self, kriterium: str = "M") -> int:
        """Index (0-based) nejzatíženějšího výstupu podle MSÚ (6.10, včetně g0):
        "M" = max kladný moment, "M-" = max záporný moment, "V" = max |V|."""
        sh = self.souhrn()
        if kriterium == "M":
            vals = [d["M_Ed"] for d in sh]
        elif kriterium == "M-":
            vals = [-d["Mmin_Ed"] for d in sh]
        elif kriterium == "V":
            vals = [d["V_Ed"] for d in sh]
        else:
            raise ValueError("Kritérium musí být 'M', 'M-' nebo 'V'.")
        return int(np.argmax(vals))


# ---------------------------------------------------------------------------
# Pomocné výpočty
# ---------------------------------------------------------------------------

def _nosnik_samostatne(K: Konstrukce):
    """1D spojitý nosník = jeden nosník bez spolupůsobení, jednotkové zatížení
    q = 1 kN/m po celé délce.  Vrací (xs, M, V(x⁻), V(x⁺), indexy podpor)."""
    K1 = Konstrukce(L=list(K.L), N=1, b=K.b, E=K.E, Iy=K.Iy, nu=K.nu, d=K.d,
                    typ="nosniky", k_pod=K.k_pod, uloz=K.uloz, k_rot=K.k_rot)
    nos = Nosnik1D(K1)
    M, Vn, _, R = nos.stav([(1.0, 0.0, K.Ltot)])
    Vp = Vn.copy()
    Vp[nos.i_sup] += R
    return nos.xs, M, Vn, Vp, nos.i_sup


def _prenes_1D(xs2: np.ndarray, vyst: Vystupy, o: int, Ltot: float, xs1, M1, Vm1, Vp1,
               i_sup1, nx: int):
    """Průběh samostatného nosníku (1D) na uzly výstupu o 2D sítě."""
    M = np.zeros(nx); Vm = np.zeros(nx); Vp = np.zeros(nx)
    i0, i1 = int(vyst.i0[o]), int(vyst.i1[o])
    x0 = float(vyst.x0[o])
    sk = sorted(set(int(k) for k in vyst.skoky[o]))
    for k in range(i0, i1 + 1):
        x = min(max(xs2[k] - x0, 0.0), Ltot)
        if k in sk:                                   # uzel podpory → přesná hodnota
            j = int(i_sup1[sk.index(k)]) if len(sk) == len(i_sup1) else \
                int(i_sup1[int(np.argmin(np.abs(xs1[i_sup1] - x)))])
            M[k], Vm[k], Vp[k] = M1[j], Vm1[j], Vp1[j]
            continue
        e = int(np.clip(np.searchsorted(xs1, x) - 1, 0, len(xs1) - 2))
        t = (x - xs1[e]) / (xs1[e + 1] - xs1[e])
        M[k] = M1[e] * (1 - t) + M1[e + 1] * t
        Vm[k] = Vp[k] = Vp1[e] * (1 - t) + Vm1[e + 1] * t
    return M, Vm, Vp


def _staly_MKP(model, vyst: Vystupy, platky) -> tuple:
    """Stálé zatížení plochami na 2D modelu → (M, Vm, Vp) výstupů, ΣF, ΣR."""
    f = model.zatizeni(platky)
    u = model.res(f)
    PM, PVm, PVp = model.vyslednice(u)
    S = vyst.S
    F = float(f[: model._nw].sum())
    R = float(model.reakce(f, u).sum())
    return S @ PM, S @ PVm, S @ PVp, F, R


# ---------------------------------------------------------------------------
# Hlavní funkce
# ---------------------------------------------------------------------------

def vnitrni_sily(
    L: Union[float, List[float]],
    N: int = 1,
    b: float = 1.0,
    Iy: float = 0.0,
    beton: Optional[str] = None,
    E: Optional[float] = None,
    nu: float = 0.2,
    d: float = 0.0,
    spara: bool = False,
    b_s: float = 0.0,
    Iy_s: float = 0.0,
    beton_s: Optional[str] = None,
    E_s: Optional[float] = None,
    typ_konstrukce: str = "nosniky",
    h: float = 0.0,
    alfa: float = 90.0,
    sikmost: str = "prava",
    k_pod: Optional[float] = None,
    uloz: str = "tvrde",
    k_rot: Optional[float] = None,
    beta_s_pevne: bool = False,
    spoj: str = "kloub",
    # ---- stálé zatížení ----
    vybaveni: Optional[Vybaveni] = None,
    A_nosniku: Optional[float] = None,
    g0: Optional[float] = None,
    gamma_beton: float = GAMMA_BETON,
    g_spary: float = 0.0,
    # ---- pohyblivé zatížení ----
    Ve: Optional[float] = None,
    MLC: Optional[str] = None,
    typ_MLC: str = "k",
    dist: Optional[float] = None,
    dyn: float = 1.0,
    y_Ve: Optional[float] = None,
    roznos: bool = True,
    t_voz: float = 0.0,
    krok: float = 0.25,
    # ---- výpočet ----
    ex: float = 0.125,
    soucinitele: Optional[Soucinitele] = None,
    tisk: bool = True,
) -> VysledekSil:
    """
    Vnitřní síly od g0, g − g0 a q na každém nosníku (pásu 1 m).

    Konstrukce (L … spoj) – stejné parametry jako porovnani_zatizeni
    (k_pod [kN/m na 1 m podpory], k_rot [kNm/rad na 1 m podpory]).

    Args:
        vybaveni:    chodníky, skladby, svodidla, zábradlí (Vybaveni); None = bez.
        A_nosniku:   plocha průřezu nosníku [m²] → g0 = A·γ_b (nosníky).
        g0:          vlastní tíha přímo: nosníky [kN/m] na nosník, deska [kN/m²];
                     má přednost před A_nosniku (deska: výchozí h·γ_b).
        gamma_beton: objemová tíha [kN/m³].
        g_spary:     tíha výplně spáry [kN/m] (nese ji samostatně sousední dvojice
                     nosníků, každý polovinu) – přičte se ke g − g0.
        Ve:          vozidlo Ve – výjimečná zatížitelnost [t].
        MLC, typ_MLC: vozidlo MLC (např. "MLC80"), "k" kolové | "p" pásové.
                     Zadává se Ve NEBO MLC; bez vozidla se stav q nepočítá.
        dist:        MLC: vzdálenost vozidel v koloně [m]; None = jedno vozidlo.
        dyn:         dynamický součinitel pohyblivého zatížení [-].
        y_Ve:        příčná poloha osy vozidla [m] (None = osa vozovky).
        roznos, t_voz: roznos plošky kola do střednice desky (+ tloušťka vozovky [m]).
        krok:        krok poloh vozidla pro obálku q [m].
        ex:          velikost prvku MKP [m].
        soucinitele: součinitele kombinací (výběr nejzatíženějšího nosníku, export).
    """
    Lp = [float(L)] if np.isscalar(L) else [float(v) for v in L]
    if beton:
        E = E_betonu(beton)
    if E is None:
        raise ValueError("Zadejte třídu betonu nebo modul pružnosti E.")
    if beton_s:
        E_s = E_betonu(beton_s)
    K = Konstrukce(L=Lp, N=N, b=b, E=E, Iy=Iy, nu=nu, d=d, spara=spara, b_s=b_s,
                   Iy_s=Iy_s, E_s=E_s, typ=typ_konstrukce, h=h, alfa=alfa, sikmost=sikmost,
                   k_pod=k_pod, uloz=uloz, k_rot=k_rot, beta_s_pevne=beta_s_pevne)
    vyb = vybaveni or Vybaveni()
    B = K.B
    vyb.kontrola(B)
    if dyn <= 0:
        raise ValueError("Dynamický součinitel musí být kladný.")
    if g_spary < 0:
        raise ValueError("Tíha spáry musí být nezáporná.")
    varovani: List[str] = []

    # ---- 2D model -----------------------------------------------------------
    if K.je_deska:
        from .slab_fem import DeskaSikmaMKP
        model = DeskaSikmaMKP(K, ex=ex)
    else:
        model = DeskaMKP(K, ex=ex, ney=4, spoj=spoj)
    vyst = model.vyst
    nv, nx = vyst.n, model.nx
    shp = (nv, nx)
    # rozsah x pokrývající celou konstrukci (i šikmou)
    sx = 0.5 * B * K.cot + 1e-6
    x_od, x_do = -sx, K.Ltot + sx
    kontrola: Dict[str, float] = {}

    # ---- g0 ----------------------------------------------------------------
    if K.je_deska:
        g0_ = float(g0) if g0 is not None else K.h * gamma_beton           # kN/m²
        M, Vm, Vp, F, R = _staly_MKP(model, vyst, platky_plosne(g0_, x_od, x_do, 0.0, B))
        s_g0 = StavSil.staly("g0", f"vlastní tíha desky {g0_:.3g} kN/m² (MKP)", M, Vm, Vp)
        kontrola.update(g0_F=F, g0_R=R)
        jedn = None
    else:
        if g0 is not None:
            g0_ = float(g0)
        elif A_nosniku is not None:
            g0_ = float(A_nosniku) * gamma_beton
        else:
            g0_ = 0.0
            varovani.append("Vlastní tíha nosníku g0 není zadána (A nosníku ani g0) – g0 = 0.")
        jedn = _nosnik_samostatne(K)
        M = np.zeros(shp); Vm = np.zeros(shp); Vp = np.zeros(shp)
        for o in range(nv):
            M[o], Vm[o], Vp[o] = _prenes_1D(model.xs, vyst, o, K.Ltot, *jedn, nx)
        s_g0 = StavSil.staly("g0", f"vlastní tíha nosníku {g0_:.3g} kN/m "
                             "(každý nosník samostatně, bez spolupůsobení)",
                             g0_ * M, g0_ * Vm, g0_ * Vp)
        jedn = (M, Vm, Vp)

    # ---- g − g0 -----------------------------------------------------------
    platky = vyb.platky(B, x_od, x_do)
    if platky:
        M, Vm, Vp, F, R = _staly_MKP(model, vyst, platky)
        s_g = StavSil.staly("g-g0", "ostatní stálé (MKP): " + vyb.popis(B), M, Vm, Vp)
        kontrola.update(g_F=F, g_R=R, g_na_metr=vyb.tiha_na_metr(B))
    else:
        s_g = StavSil.nula("g-g0", "ostatní stálé: nezadáno", shp)
    if g_spary and not K.je_deska and K.spara:
        Mj, Vmj, Vpj = jedn
        c = np.array([0.5 * (o > 0) + 0.5 * (o < nv - 1) for o in range(nv)])[:, None]
        s_sp = StavSil.staly("g-g0", "", g_spary * c * Mj, g_spary * c * Vmj,
                             g_spary * c * Vpj)
        s_g = s_g + s_sp
        s_g.popis += f"; výplň spáry {g_spary:g} kN/m (samostatně, ½ na sousední nosníky)"
    elif g_spary and not K.spara:
        varovani.append("Tíha spáry je zadána, ale konstrukce spáru nemá – ignorováno.")

    stavy = {"g0": s_g0, "g-g0": s_g}

    # ---- q: pojezd vybraného vozidla ----------------------------------------
    roz = (K.h_ekv if roznos else 0.0) + 2.0 * t_voz
    y_c = float(y_Ve) if y_Ve is not None else vyb.y_osy_vozovky(B)
    if Ve and MLC:
        raise ValueError("Zadejte jedno vozidlo: Ve, nebo MLC.")
    voz_popis, rozvor, b_k = "", VE_ROZVOR, VE_B_K
    if Ve or MLC:
        nos = Nosnik1D(K)
        n_ob = max(1, int(math.ceil(K.Ltot / (krok * K.n_poli))))
        if Ve:
            if Ve < 0:
                raise ValueError("Ve musí být kladné.")
            voz_popis = f"Ve {Ve:g} t"
            gen = nos.stavy_Ve(Ve, n_ob, roz, extra=True)
        else:
            t = (typ_MLC or "k").lower()
            if t not in ("k", "p"):
                raise ValueError("Typ vozidla MLC musí být 'k' (kolové) nebo 'p' (pásové).")
            v = kolove_vozidlo(MLC) if t == "k" else pasove_vozidlo(MLC)
            rozvor, b_k = v.rozvor, v.b_k
            if dist is not None and dist <= 0:
                dist = None
            voz_popis = (f"{MLC} {'kolové' if t == 'k' else 'pásové'}" +
                         (f", kolona po {dist:g} m" if dist else ""))
            gen = nos.stavy_MLC(t, MLC, n_ob, dist, roz, extra=True)
        pul = 0.5 * (rozvor + b_k)
        if y_c - pul < vyb.chodnik_L - 1e-9 or y_c + pul > B - vyb.chodnik_P + 1e-9:
            varovani.append(f"Vozidlo {voz_popis} (šířka {2 * pul:.2f} m, osa y = {y_c:.2f} m) "
                            "přesahuje vozovku.")
        dx = K.x0(y_c)

        def stavy_q():
            for ax, _ in gen:
                yield [(q * dyn, s, e) for q, s, e in ax], None

        ob = obalky_2D(model, stavy_q(), y_c - 0.5 * rozvor, y_c + 0.5 * rozvor, b_k, roz, dx)
        stavy["q"] = StavSil("q", f"vozidlo {voz_popis}, osa y = {y_c:.2f} m, "
                             f"δ = {dyn:g}, roznos {roz:.2f} m, krok {krok:g} m",
                             ob.M_max, ob.M_min, ob.Vm_max, ob.Vm_min, ob.Vp_max, ob.Vp_min,
                             ob.Vs_max, ob.Vs_min, pohyblivy=True, n_stavu=ob.n_stavu)

    if K.n_poli > 1:
        varovani.append("Spojitý nosník o více polích – posudek PB řeší prostý nosník; "
                        "export do posudku je jen orientační.")
    if K.sikmy and not K.je_deska:
        varovani.append("Šikmý most: x výstupu se měří od osy podpory daného nosníku.")
    popis = (f"{'deska' if K.je_deska else f'{K.N} nosníků'}, {K.popis()}, "
             f"uložení: {K.popis_ulozeni()}; 2D MKP prvek ≈ {model.a_ref:.3f} m")

    vys = VysledekSil(K=K, vybaveni=vyb, xs=model.xs.copy(), vyst=vyst, stavy=stavy,
                      g0=g0_, g_spary=g_spary if K.spara else 0.0, Ve=float(Ve or 0.0),
                      dyn=dyn, y_Ve=y_c, roz=roz, vozidlo=voz_popis, rozvor=rozvor, b_k=b_k,
                      soucinitele=soucinitele or Soucinitele(), popis=popis,
                      varovani=varovani, kontrola=kontrola, sit=sit_modelu(model),
                      y_vyst=np.asarray(vyst.y, float))
    if tisk:
        vypis(vys)
    return vys


def vypis(v: VysledekSil) -> None:
    jm, jv = v.jednotky
    print("=" * 86)
    print("  VNITŘNÍ SÍLY PRO POSUDEK – g0, g − g0, q")
    print("=" * 86)
    print(f"  {v.popis}")
    for s in v.stavy.values():
        print(f"  {s.nazev:<5} {s.popis}")
    if "g_F" in v.kontrola:
        print(f"  Kontrola g − g0: ΣF = {v.kontrola['g_F']:.1f} kN, ΣR = {v.kontrola['g_R']:.1f} kN")
    print()
    sh = v.souhrn()
    hl = f"  {'výstup':<9}{'y [m]':>7}"
    for s in v.stavy:
        hl += f"{'M ' + s:>11}"
    for s in v.stavy:
        hl += f"{'|V| ' + s:>11}"
    hl += f"{'M_Ed':>10}{'V_Ed':>10}"
    print(hl + f"   [{jm}, {jv}]")
    print("  " + "-" * (len(hl) - 2))
    gov = v.rozhodujici("M")
    for o, d in enumerate(sh):
        r = f"  {d['vystup']:<9}{d['y']:>7.2f}"
        for s in v.stavy:
            r += f"{d['M_' + s]:>11.1f}"
        for s in v.stavy:
            r += f"{d['V_' + s]:>11.1f}"
        r += f"{d['M_Ed']:>10.1f}{d['V_Ed']:>10.1f}"
        print(r + ("   ◄ rozhoduje" if o == gov else ""))
    print(f"\n  M_Ed, V_Ed: kombinace 6.10 (γ_G = {v.soucinitele.gamma_G:g}, "
          f"γ_Q = {v.soucinitele.gamma_Q:g}) včetně g0.")
    for t in v.varovani:
        print(f"  ! {t}")
    print("=" * 86)
