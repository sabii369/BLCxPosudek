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
  qch    chodci na chodnících – obálka (nepříznivé části plochy vlivu); hodnota zadaná,
           nebo podle ČSN 73 6222: Vn, Vr 2,5 kN/m² (tab. 7.1, 7.2), Ve 0 (chodci vyloučeni),
  q      pohyblivé zatížení na 2D desce (obálka max/min):
           Ve (výjimečná zatížitelnost) nebo vozidlo MLC (kolové / pásové; volitelně
           kolona) – pojezd jednoho vozidla, osa v ose vozovky nebo zadaná,
           Vn (normální zatížitelnost) – schéma obr. 7.1: zatěžovací pruhy od kraje
           vozovky u užšího chodníku, nápravy v pruzích (nezávisle na sobě, pojezd)
           a rovnoměrné zatížení v nepříznivých částech plochy vlivu; δ1/δ2/δ3 podle
           počtu zatížených pruhů,
           Vr (výhradní zatížitelnost) – jediné vozidlo obr. 7.3 / 7.4 vnějším okrajem
           u kraje vozovky u užšího chodníku, δ1 (schemata_zatizitelnosti.py);
           dynamický součinitel δ zadaný, nebo podle ČSN 73 6222, kap. 8
           (Ve: δ = 1,05, čl. 8.4) – dynamicky_soucinitel.py.

Model konstrukce (MKP, okrajové podmínky, šikmost, spáry) je totožný
s porovnáním MLC / Ve (comparison.py).  Výsledky jsou na síti 2D modelu;
pro každý výstup (nosník / pás 1 m) se dají vypsat jako tabulka
x [m od osy první podpory výstupu], M_max, M_min, V_max, V_min.

Znaménka: kladný M táhne dolní vlákna, V = dM/dx (kladná u levé podpory).
Jednotky: kN, m (deska: hodnoty na pás 1 m → kNm/m, kN/m).
"""

from __future__ import annotations
import copy
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Union

import numpy as np

from .geometry import Konstrukce, E_betonu
from .beam_1d import Nosnik1D, VE_ROZVOR, VE_B_K, zrcadli
from .dynamicky_soucinitel import (dynamicky_soucinitel, delty_zatizitelnosti, DELTA_CHODNIKY,
                                   NORMA)
from .vehicles import kolove_vozidlo, pasove_vozidlo
from .plate_fem import (DeskaMKP, Vystupy, obalky_2D, obalky_2D_platky, sit_modelu, SitMKP,
                        platky_z_naprav, posun)
from .stale_zatizeni import Vybaveni, platky_plosne
from . import schemata_zatizitelnosti as sz

GAMMA_BETON = 25.0               # objemová tíha železobetonu [kN/m³]
STAVY = ("g0", "g-g0", "qch", "q")
NAZVY_STAVU = {
    "g0": "vlastní tíha g0",
    "g-g0": "ostatní stálé g − g0",
    "qch": "zatížení chodců q_ch",
    "q": "zatížení dopravou q",
}
#: skupiny zatížení pro součinitele kombinací (stálé, chodci, doprava)
SKUPINY = {"G": "g0 + (g − g0)", "qch": "q – chodníky", "q": "q – doprava"}
DRUHY_KOMBINACI = ("6.10a", "6.10b", "6.10", "char", "casta", "kvazistala")


# ---------------------------------------------------------------------------
# Součinitele kombinací (ČSN EN 1990) – pro export do posudku a výběr nosníku
# ---------------------------------------------------------------------------

@dataclass
class Soucinitele:
    """Dílčí součinitele a součinitele kombinace.  Výchozí ψ odpovídají
    tandemové soustavě TS (ČSN EN 1990, tab. A2.1) – pro vozidlo Ve
    je nutné je ověřit / upravit podle zadání hodnocení.
    Doprava (q): gamma_Q, psi0..2; chodci (qch): gamma_Qch, psi0_ch..psi2_ch.
    Obě proměnná zatížení působí v kombinaci současně (jako skupina)."""
    gamma_G: float = 1.35
    gamma_G_inf: float = 1.0
    xi: float = 0.85
    gamma_Q: float = 1.35
    psi0: float = 0.75
    psi1: float = 0.75
    psi2: float = 0.0
    gamma_Qch: float = 1.35
    psi0_ch: float = 0.75
    psi1_ch: float = 0.75
    psi2_ch: float = 0.0

    def gama_psi(self, skupina: str, druh: str) -> tuple:
        """(γ, ψ) skupiny "G" | "qch" | "q" v kombinaci; u stálých v 6.10b je ψ = ξ."""
        if skupina == "G":
            g = self.gamma_G
            return {"char": (1.0, 1.0), "casta": (1.0, 1.0), "kvazistala": (1.0, 1.0),
                    "6.10a": (g, 1.0), "6.10b": (g, self.xi), "6.10": (g, 1.0)}[druh]
        if skupina == "qch":
            g, p0, p1, p2 = self.gamma_Qch, self.psi0_ch, self.psi1_ch, self.psi2_ch
        else:
            g, p0, p1, p2 = self.gamma_Q, self.psi0, self.psi1, self.psi2
        return {"char": (1.0, 1.0), "casta": (1.0, p1), "kvazistala": (1.0, p2),
                "6.10a": (g, p0), "6.10b": (g, 1.0), "6.10": (g, 1.0)}[druh]

    def faktory(self, druh: str):
        """(γ_sup stálého, γ_inf stálého, součinitel q – doprava) pro kombinaci."""
        g, p = self.gama_psi("G", druh)
        gq, pq = self.gama_psi("q", druh)
        return g * p, (1.0 if druh in ("char", "casta", "kvazistala") else self.gamma_G_inf), gq * pq

    def faktor_q(self, stav: str, druh: str) -> float:
        """Součinitel proměnného stavu ("q" | "qch") v kombinaci = γ·ψ."""
        g, p = self.gama_psi("qch" if stav == "qch" else "q", druh)
        return g * p


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
    dyn: float = 1.0                    # δ (u Vn δ1 – jednoho pruhu)
    dyn_zdroj: str = ""                 # zdůvodnění δ („ČSN 73 6222, čl. 8.4 …“, „zadáno“)
    y_Ve: float = 0.0                   # osa vozidla [m] (Vn: osa pruhu 1)
    vozidlo: str = ""                   # popis vozidla („Ve 80 t“, „MLC80 kolové“, „Vn 32 t“)
    rozvor: float = VE_ROZVOR           # osová vzdálenost stop vozidla [m]
    b_k: float = VE_B_K                 # šířka stopy [m]
    roz: float = 0.0                    # podélný / příčný roznos plošky [m]
    druh_q: str = ""                    # "Ve" | "Vn" | "Vr" | "MLC" | "" (bez q)
    V: float = 0.0                      # tíha vozidla / zatížitelnost [t] (Ve, Vn, Vr)
    schema_q: str = ""                  # schéma Vn ("dvojnaprava" | "naprava"), Vr ("6", "3", "2")
    q_ch: float = 0.0                   # použité zatížení chodníků [kN/m²]
    q_ch_zdroj: str = ""                # „zadáno“ | odkaz na normu
    poloha_q: str = ""                  # popis příčné polohy pohyblivého zatížení
    stopy_q: list = field(default_factory=list)   # [(y_osy, šířka)] stop kol – příčný řez
    pruhy_q: list = field(default_factory=list)   # [(y0, y1, popis)] zatěžovacích pruhů (Vn)
    nastaveni_q: dict = field(default_factory=dict)  # vstupy q (pro přepočet jiného vozidla)
    cache: dict = field(default_factory=dict, repr=False)  # sdílené mezivýsledky (qch)
    soucinitele: Soucinitele = field(default_factory=Soucinitele)
    popis: str = ""
    varovani: List[str] = field(default_factory=list)
    varovani_zaklad: List[str] = field(default_factory=list, repr=False)  # bez varování k q
    kontrola: Dict[str, float] = field(default_factory=dict)
    sit: Optional[SitMKP] = None
    y_vyst: Optional[np.ndarray] = None
    model: object = field(default=None, repr=False)        # 2D model MKP (pro další stavy)
    q_nastaveni: Optional[dict] = field(default=None, repr=False)  # polohy vozidla q

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
        return self.tabulka_stavu(o, self.stavy[stav])

    def tabulka_stavu(self, o: int, s: StavSil) -> TabulkaSil:
        """Průběh libovolného stavu (StavSil na síti 2D modelu) na výstupu o."""
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
        for sq in ("qch", "q"):
            if sq in self.stavy:
                f = self.soucinitele.faktor_q(sq, druh)
                t = self.tabulka(o, sq)
                for a in ("M_max", "M_min", "V_max", "V_min"):
                    getattr(out, a)[:] += f * getattr(t, a)
        return out

    def extremy_kombinace(self, druh: str, vcetne_g0: bool = True) -> List[dict]:
        """Po výstupech: max/min M a max/min V kombinace (s polohou x maxima M)."""
        out = []
        for o in range(self.n_vyst):
            k = self.kombinace(o, druh, vcetne_g0)
            i = int(np.argmax(k.M_max))
            out.append({"vystup": self.popisky[o], "M_max": float(k.M_max.max()),
                        "x_M_max": float(k.x[i]), "M_min": float(k.M_min.min()),
                        "V_max": float(k.V_max.max()), "V_min": float(k.V_min.min())})
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


VELICINY = ("M", "Vm", "Vp", "Vs")
Usek = tuple          # (plošky, (x0, x1, y0, y1, q)) – jeden úsek plošného zatížení


def _useky_pasu(K: Konstrukce, y0: float, y1: float, q: float, krok: float,
                dy_max: Optional[float] = None) -> List[Usek]:
    """Rovnoměrné zatížení q [kN/m²] pásu y0 … y1 po celé délce mostu rozdělené na úseky
    délky ≈ krok.  dy_max: u šikmé konstrukce se pás dělí i příčně (každá část má vlastní
    posun čela x0(y)); None = jeden pás s x0 v jeho ose."""
    n = max(1, int(math.ceil(K.Ltot / krok - 1e-9)))
    dx = K.Ltot / n
    ny = max(1, int(math.ceil((y1 - y0) / dy_max - 1e-9))) if (dy_max and K.sikmy) else 1
    hy = (y1 - y0) / ny
    out = []
    for j in range(ny):
        ya, yb = y0 + j * hy, y0 + (j + 1) * hy
        x0 = K.x0(0.5 * (ya + yb))
        for k in range(n):
            xa, xb = x0 + k * dx, x0 + (k + 1) * dx
            out.append((platky_plosne(q, xa, xb, ya, yb, dx=dx, dy=0.5), (xa, xb, ya, yb, q)))
    return out


def _soucty_useku(model, vyst: Vystupy, useky: List[Usek], davka: int = 48) -> Dict[str, np.ndarray]:
    """Σ kladných („M+“ …) a Σ záporných („M-“ …) účinků úseků na výstupech (n_vyst, nx) –
    zatížení v nepříznivých částech plochy vlivu."""
    nv, nx = vyst.n, model.nx
    acc = {a + z: np.zeros((nv, nx)) for a in VELICINY for z in "+-"}
    sl = [model.zatizeni(pl) for pl, _ in useky]
    for i in range(0, len(sl), davka):
        U = model.res_batch(np.stack(sl[i:i + davka], axis=1))
        PM, PVm, PVp = model.vyslednice(U)
        A = {"M": np.einsum("os,sxb->oxb", vyst.S, PM),
             "Vm": np.einsum("os,sxb->oxb", vyst.S, PVm),
             "Vp": np.einsum("os,sxb->oxb", vyst.S, PVp)}
        A["Vs"] = 0.5 * (A["Vm"] + A["Vp"])
        for k, v in A.items():
            acc[k + "+"] += np.clip(v, 0, None).sum(axis=2)
            acc[k + "-"] += np.clip(v, None, 0).sum(axis=2)
    return acc


def _obalka_poloh(model, polohy) -> tuple:
    """Obálka přes polohy zatížení (seznamy plošek) ve tvaru ({„M+“: max, „M-“: min, …},
    počet poloh se zatížením na konstrukci)."""
    ob = obalky_2D_platky(model, polohy)
    return ({"M+": ob.M_max, "M-": ob.M_min, "Vm+": ob.Vm_max, "Vm-": ob.Vm_min,
             "Vp+": ob.Vp_max, "Vp-": ob.Vp_min, "Vs+": ob.Vs_max, "Vs-": ob.Vs_min}, ob.n_stavu)


def _stav(nazev: str, popis: str, a: Dict[str, np.ndarray], n_stavu: int) -> StavSil:
    return StavSil(nazev, popis, a["M+"], a["M-"], a["Vm+"], a["Vm-"], a["Vp+"], a["Vp-"],
                   a["Vs+"], a["Vs-"], pohyblivy=True, n_stavu=n_stavu)


def _pasy_chodniku(K: Konstrukce, vyb: Vybaveni) -> List[tuple]:
    pasy = []
    if vyb.chodnik_L > 0:
        pasy.append((0.0, vyb.chodnik_L))
    if vyb.chodnik_P > 0:
        pasy.append((K.B - vyb.chodnik_P, K.B))
    return pasy


def _chodniky(model, vyst: Vystupy, K: Konstrukce, vyb: Vybaveni, q: float,
              krok: float, davka: int = 48) -> StavSil:
    """Obálka od zatížení chodníků q [kN/m²]: chodníky rozdělené na úseky délky ≈ krok
    (levý a pravý zvlášť), max = Σ kladných, min = Σ záporných účinků úseků (zatížení
    v nepříznivých částech plochy vlivu)."""
    useky = [u for y0, y1 in _pasy_chodniku(K, vyb) for u in _useky_pasu(K, y0, y1, q, krok)]
    acc = _soucty_useku(model, vyst, useky, davka)
    dx = K.Ltot / max(1, int(math.ceil(K.Ltot / krok - 1e-9)))
    popis = (f"chodníky {vyb.chodnik_L:g} + {vyb.chodnik_P:g} m, q = {q:g} kN/m² v nepříznivých "
             f"částech plochy vlivu (úseky {dx:.2f} m), δ = {DELTA_CHODNIKY:g} ({NORMA}, čl. 8.5 b)")
    return _stav("qch", popis, acc, len(useky))


def _q_chodniku(druh: str, q_chodnik: Optional[float]) -> tuple:
    """(q [kN/m²], zdroj): zadaná hodnota, nebo podle ČSN 73 6222 podle druhu vozidla."""
    if q_chodnik is not None:
        if q_chodnik < 0:
            raise ValueError("Zatížení chodníků musí být nezáporné.")
        return float(q_chodnik), "zadáno"
    if druh in ("Vn", "Vr"):
        return sz.Q_CHODNIKY, (f"{NORMA}, tab. {'7.1' if druh == 'Vn' else '7.2'} – redukovaná "
                               "hodnota w_f")
    if druh == "Ve":
        return 0.0, f"{NORMA}, čl. 3.1.4, 5.2.8 – při výjimečné zatížitelnosti chodci vyloučeni"
    if druh == "MLC":
        return 0.0, f"pro MLC {NORMA} zatížení chodců neuvádí"
    return 0.0, ""


# ---- schémata zatížitelnosti Vn, Vr --------------------------------------------------

def _n_ob(K: Konstrukce, krok: float) -> int:
    return max(1, int(math.ceil(K.Ltot / (krok * K.n_poli))))


def _polohy_vozidla(nos: Nosnik1D, K: Konstrukce, napravy, y1: float, y2: float, roz: float,
                    krok: float, oba_smery: bool, dx: float) -> Callable:
    """Generátor poloh vozidla (seznamy plošek v rámci 2D) pro pojezd po mostě.
    napravy: [(F [kN], x [m od čela], délka plošky, šířka plošky)]; plošky kol ve stopách y1, y2
    (každé kolo F/2), podélný i příčný roznos roz; mřížka poloh s krokem ≈ krok + polohy
    s hranou zatížení v řezu d od podpory; oba směry jízdy (oba_smery) zrcadlením."""
    Lt = K.Ltot
    b_max = max(n[2] for n in napravy)

    def ax1d(x1):                                    # (q [kN/m], s, e) – pro hrany zatížení
        return [(F / L, x1 + x - 0.5 * L, x1 + x + 0.5 * L) for F, x, L, _ in napravy]

    xs = [n[1] for n in napravy]
    n_tot = max(1, _n_ob(K, krok) * K.n_poli)
    pol = nos._polohy(ax1d, n_tot, roz, -(max(xs) + b_max + roz), Lt - min(xs) + b_max + roz, True)
    sirky = [n[3] for n in napravy]

    def platky(ax):
        return [(0.5 * q * (e - s), s - 0.5 * roz + dx, e + 0.5 * roz + dx,
                 yc - 0.5 * (b + roz), yc + 0.5 * (b + roz))
                for (q, s, e), b in zip(ax, sirky) for yc in (y1, y2)]

    def gen():
        for x1 in pol:
            ax = ax1d(x1)
            yield platky(ax)
            if oba_smery:
                yield platky(zrcadli(ax, Lt))
    return gen


def _kombinuj_pruhy(pruhy: List[Dict[str, np.ndarray]], zbytek: Optional[Dict[str, np.ndarray]],
                    delty: Dict[int, float]) -> Dict[str, np.ndarray]:
    """Obálka schématu Vn: zatíženy pruhy 1 … k (a zbývající plocha), δ_k podle počtu pruhů;
    max = max_k δ_k·(Σ_{i≤k} příspěvek⁺ pruhu i + zbývající⁺), min obdobně.  Příspěvek pruhu =
    náprava v nejnepříznivější poloze (nebo mimo most) + rovnoměrné v nepříznivých úsecích."""
    out = {}
    for a in VELICINY:
        for z, fce in (("+", np.maximum), ("-", np.minimum)):
            cum = zbytek[a + z].copy() if zbytek else 0.0
            best = None
            for k, p in enumerate(pruhy, 1):
                cum = cum + p[a + z]
                val = delty[min(k, 3)] * cum
                best = val if best is None else fce(best, val)
            out[a + z] = best
    return out


def _schema_Vn(model, vyst, K: Konstrukce, vyb: Vybaveni, Vn: float, schema: str, roz: float,
               krok: float, krok_useky: float, dyn: Optional[float]) -> dict:
    """Stav q pro normální zatížitelnost Vn [t] (vn = Vn/13,33) – obr. 7.1 u kraje vozovky
    u užšího chodníku.  Vrací podklady pro VysledekSil (stav, popisy, q_nastaveni …)."""
    vn = sz.vn_z_Vn(Vn)
    pp = sz.pricna_poloha(vyb.chodnik_L, vyb.chodnik_P, K.B)
    pruhy, zbytek = sz.pruhy_Vn(pp, schema)
    delty, dzdroj = delty_zatizitelnosti(K, dyn)
    nos = Nosnik1D(K)
    bw = sz.PLOSKA_KOLA_VN
    slozky, acc_pruhy, n_st = [], [], 0
    stopy, pruhy_popis = [], []
    for p in pruhy:
        s: Dict[str, object] = {"cislo": p.cislo, "pojezd": None, "useky": []}
        acc = {a + z: np.zeros((vyst.n, model.nx)) for a in VELICINY for z in "+-"}
        if p.naprava:
            Fn = 2.0 * p.F_kolo * vn                              # tíha nápravy [kN]
            xs_n = (0.0, sz.ROZTEC_DVOJNAPRAVY) if p.naprava == "dvojnaprava" else (0.0,)
            ya, yb = p.y_c - 0.5 * sz.ROZCHOD_KOL, p.y_c + 0.5 * sz.ROZCHOD_KOL
            gen = _polohy_vozidla(nos, K, [(Fn, x, bw, bw) for x in xs_n], ya, yb, roz, krok,
                                  False, K.x0(p.y_c))
            ob, n_p = _obalka_poloh(model, gen())
            n_st += n_p
            for k in acc:
                acc[k] += np.maximum(ob[k], 0.0) if k.endswith("+") else np.minimum(ob[k], 0.0)
            s["pojezd"] = gen
            stopy += [(ya, bw), (yb, bw)]
        us = _useky_pasu(K, p.y0, p.y1, p.q_rovnomerne * vn, krok_useky, dy_max=1.0)
        su = _soucty_useku(model, vyst, us)
        n_st += len(us)
        for k in acc:
            acc[k] += su[k]
        s["useky"] = us
        slozky.append(s)
        acc_pruhy.append(acc)
        pruhy_popis.append((p.y0, p.y1, f"pruh {p.cislo}"))
    acc_z, us_z = None, []
    if zbytek is not None:
        us_z = _useky_pasu(K, zbytek[0], zbytek[1], vn, krok_useky, dy_max=1.0)
        acc_z = _soucty_useku(model, vyst, us_z)
        n_st += len(us_z)
    kom = _kombinuj_pruhy(acc_pruhy, acc_z, delty)
    n, wl = len(pruhy), (pruhy[0].y1 - pruhy[0].y0)
    dxu = K.Ltot / max(1, int(math.ceil(K.Ltot / krok_useky - 1e-9)))

    def popis(V):
        return (f"normální zatížitelnost Vn = {V:.4g} t (vn = {sz.vn_z_Vn(V):.4g} kN/m², "
                f"{sz.POPIS_SCHEMAT[schema]}, obr. 7.1), {n} {'pruh' if n == 1 else 'pruhy'} "
                f"{wl:g} m {pp.popis}" + (f", zbývající plocha {zbytek[1] - zbytek[0]:.2f} m"
                                          if zbytek else "") +
                f"; nápravy v pruzích nezávisle (pojezd, krok {krok:g} m), rovnoměrné zatížení "
                f"v nepříznivých částech plochy vlivu (úseky {dxu:.2f} m); δ podle počtu "
                f"zatížených pruhů – {dzdroj}; ploška kola {bw:g} × {bw:g} m (jako LM1), "
                f"roznos {roz:.2f} m")

    varovani = []
    if pp.w < sz.SIRKA_PRUHU - 1e-9:
        varovani.append(f"Vozovka ({pp.w:.2f} m) je užší než zatěžovací pruh 3 m – pruh přesahuje "
                        "na chodník.")
    return dict(stav=_stav("q", popis(Vn), kom, n_st), popis=popis,
                vozidlo=lambda t: f"Vn {t} t", y=pruhy[0].y_c, poloha=pp.popis,
                dyn=delty[1], dyn_zdroj=dzdroj, stopy=stopy, pruhy=pruhy_popis,
                varovani=varovani,
                q_nastaveni=dict(typ="sestava", pruhy=slozky, zbytek=us_z, delty=delty,
                                 meritko=1.0))


def _schema_Vr(model, vyst, K: Konstrukce, vyb: Vybaveni, Vr: float, schema: str, roz: float,
               krok: float, dyn: Optional[float]) -> dict:
    """Stav q pro výhradní zatížitelnost Vr [t] – jediné vozidlo obr. 7.3 / 7.4 vnějším
    okrajem u kraje vozovky u užšího chodníku, δ = δ1."""
    v = sz.VOZIDLA_VR[schema]
    pp = sz.pricna_poloha(vyb.chodnik_L, vyb.chodnik_P, K.B)
    yc, y1, y2 = sz.stopy_vozidla_u_kraje(pp, v)
    d, dzdroj = dynamicky_soucinitel("Vr", dyn, K)
    nos = Nosnik1D(K)
    G = 10.0 * Vr * d
    nap = [(a.podil * G, a.x, a.delka, a.sirka) for a in v.napravy]
    gen = _polohy_vozidla(nos, K, nap, y1, y2, roz, krok, not v.symetricke, K.x0(yc))
    ob, n_p = _obalka_poloh(model, gen())

    def popis(V):
        return (f"výhradní zatížitelnost Vr = {V:.4g} t – {v.nazev} ({v.obrazek}), vnějším okrajem "
                f"{pp.popis}, osa y = {yc:.2f} m; δ = {d:.3g} ({dzdroj}); roznos {roz:.2f} m, "
                f"krok {krok:g} m")

    varovani = []
    if v.sirka > pp.w + 1e-9:
        varovani.append(f"Vozidlo Vr (šířka {v.sirka:g} m) je širší než vozovka ({pp.w:.2f} m).")
    stopy = sorted({(y, b) for y in (y1, y2) for b in {a.sirka for a in v.napravy}})
    return dict(stav=_stav("q", popis(Vr), ob, n_p), popis=popis,
                vozidlo=lambda t: f"Vr {t} t ({v.nazev})", y=yc, poloha=pp.popis, dyn=d,
                dyn_zdroj=dzdroj, stopy=stopy, pruhy=[], varovani=varovani,
                rozvor=v.rozchod, b_k=max(a.sirka for a in v.napravy),
                q_nastaveni=dict(typ="pojezd", polohy=gen, meritko=1.0))


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
    Vn: Optional[float] = None,
    Vr: Optional[float] = None,
    schema: Optional[str] = None,
    dyn: Optional[float] = None,
    y_Ve: Optional[float] = None,
    roznos: bool = True,
    t_voz: float = 0.0,
    krok: float = 0.25,
    q_chodnik: Optional[float] = None,
    krok_chodnik: float = 0.5,
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
        dist:        MLC: vzdálenost vozidel v koloně [m]; None = jedno vozidlo.
        Vn:          normální zatížitelnost [t] – schéma obr. 7.1 (vn = Vn/13,33 kN/m²).
        Vr:          výhradní zatížitelnost [t] – jediné vozidlo obr. 7.3 / 7.4.
        schema:      Vn: "dvojnaprava" | "naprava", Vr: "6" | "3" | "2"; None = podle tíhy
                     (Vn ≥ 16 t dvounáprava; Vr > 50 t šestinápravové, > 16 t třínápravové).
                     Zadává se jedno vozidlo Ve, MLC, Vn NEBO Vr; bez vozidla se q nepočítá.
                     Vn a Vr stojí u kraje vozovky u užšího chodníku (y_Ve se nepoužije).
        dyn:         dynamický součinitel pohyblivého zatížení [-]; None = podle
                     ČSN 73 6222, kap. 8 (Ve: 1,05; Vr: δ1; Vn: δ1/δ2/δ3 podle počtu
                     zatížených pruhů; MLC: norma neuvádí → 1,0).
        q_chodnik:   zatížení chodníků chodci [kN/m²]; None = podle ČSN 73 6222 (Vn, Vr:
                     2,5 kN/m² – tab. 7.1, 7.2; Ve: 0 – chodci vyloučeni; MLC: 0); 0 = bez
                     stavu qch; obálka – zatížení se klade do nepříznivých částí plochy vlivu
                     (úseky chodníků délky krok_chodnik [m], levý i pravý chodník zvlášť;
                     stejně se dělí rovnoměrné zatížení pruhů schématu Vn).
        y_Ve:        příčná poloha osy vozidla Ve / MLC [m] (None = osa vozovky).
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
    if dyn is not None and dyn <= 0:
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

    # ---- qch (chodci) a q (pohyblivé zatížení) ---------------------------------
    roz = (K.h_ekv if roznos else 0.0) + 2.0 * t_voz
    nast = dict(Ve=Ve, MLC=MLC, typ_MLC=typ_MLC, dist=dist, Vn=Vn, Vr=Vr, schema=schema,
                dyn=dyn, y_Ve=y_Ve, roz=roz, krok=krok, q_chodnik=q_chodnik,
                krok_chodnik=krok_chodnik)
    cache: dict = {}
    pr = _promenne(model, vyst, K, vyb, nast, cache)
    stavy.update(pr["stavy"])

    if K.n_poli > 1:
        varovani.append("Spojitý nosník o více polích – posudek PB řeší prostý nosník; "
                        "export do posudku je jen orientační.")
    if K.sikmy and not K.je_deska:
        varovani.append("Šikmý most: x výstupu se měří od osy podpory daného nosníku.")
    popis = (f"{'deska' if K.je_deska else f'{K.N} nosníků'}, {K.popis()}, "
             f"uložení: {K.popis_ulozeni()}; 2D MKP prvek ≈ {model.a_ref:.3f} m")

    vys = VysledekSil(K=K, vybaveni=vyb, xs=model.xs.copy(), vyst=vyst, stavy=stavy,
                      g0=g0_, g_spary=g_spary if K.spara else 0.0,
                      soucinitele=soucinitele or Soucinitele(), popis=popis,
                      varovani=varovani + pr["varovani"], varovani_zaklad=varovani,
                      kontrola=kontrola, sit=sit_modelu(model), y_vyst=np.asarray(vyst.y, float),
                      model=model, nastaveni_q=nast, cache=cache, **pr["attrs"])
    if tisk:
        vypis(vys)
    return vys


def _promenne(model, vyst: Vystupy, K: Konstrukce, vyb: Vybaveni, n: dict, cache: dict) -> dict:
    """Stavy qch a q a údaje o pohyblivém zatížení pro nastavení n (klíče jako argumenty
    vnitrni_sily: Ve, MLC, typ_MLC, dist, Vn, Vr, schema, dyn, y_Ve, roz, krok, q_chodnik,
    krok_chodnik).  Vrací {"stavy", "attrs" (pole VysledekSil), "varovani"}."""
    Ve, MLC, Vn, Vr = n.get("Ve"), n.get("MLC"), n.get("Vn"), n.get("Vr")
    for k in ("Ve", "Vn", "Vr"):
        if n.get(k) is not None and n[k] < 0:
            raise ValueError(f"{k} musí být kladné.")
    zadana = [k for k, v in (("Ve", Ve), ("MLC", MLC), ("Vn", Vn), ("Vr", Vr)) if v]
    if len(zadana) > 1:
        raise ValueError("Zadejte jedno vozidlo: Ve, MLC, Vn, nebo Vr.")
    druh = zadana[0] if zadana else ""
    dyn_zad = n.get("dyn")
    if dyn_zad is not None and dyn_zad <= 0:
        raise ValueError("Dynamický součinitel musí být kladný.")
    roz, krok, B = float(n["roz"]), float(n["krok"]), K.B
    varovani: List[str] = []
    stavy: Dict[str, StavSil] = {}

    # ---- qch: zatížení chodníků (obálka přes plochu vlivu) ------------------
    q, qz = _q_chodniku(druh, n.get("q_chodnik"))
    chodniky = vyb.chodnik_L > 0 or vyb.chodnik_P > 0
    if q and chodniky:
        klic = ("qch", q, float(n["krok_chodnik"]))
        if klic not in cache:
            cache[klic] = _chodniky(model, vyst, K, vyb, q, n["krok_chodnik"])
        s = copy.copy(cache[klic])
        s.popis += f" – {qz}" if qz != "zadáno" else ""
        stavy["qch"] = s
    elif q and n.get("q_chodnik") is not None:
        varovani.append("Zatížení chodníků je zadáno, ale most nemá chodníky – ignorováno.")
    if druh == "MLC" and n.get("q_chodnik") is None and chodniky:
        varovani.append(f"Zatížení chodců pro MLC {NORMA} neuvádí – uvažováno 0; zadejte ho, "
                        "je-li třeba.")
    y_zad = n.get("y_Ve")
    attrs = dict(druh_q=druh, q_ch=q if "qch" in stavy else 0.0, q_ch_zdroj=qz, Ve=float(Ve or 0.0),
                 V=0.0, schema_q="", dyn=1.0, dyn_zdroj="", roz=roz, vozidlo="",
                 y_Ve=float(y_zad) if y_zad is not None else vyb.y_osy_vozovky(B),
                 rozvor=VE_ROZVOR, b_k=VE_B_K, poloha_q="", stopy_q=[], pruhy_q=[],
                 q_nastaveni=None)

    # ---- q: pohyblivé zatížení ----------------------------------------------
    if druh in ("Ve", "MLC"):
        y_c = attrs["y_Ve"]
        rozvor, b_k = VE_ROZVOR, VE_B_K
        dyn, dyn_zdroj = dynamicky_soucinitel(druh, dyn_zad)
        if druh == "MLC" and dyn_zad is None:
            varovani.append(f"Dynamický součinitel pro vozidla MLC {NORMA} neuvádí – uvažováno "
                            f"δ = {dyn:g}; zadejte ho, je-li známý.")
        nos = Nosnik1D(K)
        n_ob = _n_ob(K, krok)
        if druh == "Ve":
            voz_popis = f"Ve {Ve:g} t"

            def novy_gen():
                return nos.stavy_Ve(Ve, n_ob, roz, extra=True)
        else:
            t = (n.get("typ_MLC") or "k").lower()
            if t not in ("k", "p"):
                raise ValueError("Typ vozidla MLC musí být 'k' (kolové) nebo 'p' (pásové).")
            v = kolove_vozidlo(MLC) if t == "k" else pasove_vozidlo(MLC)
            rozvor, b_k = v.rozvor, v.b_k
            dist = n.get("dist")
            if dist is not None and dist <= 0:
                dist = None
            voz_popis = (f"{MLC} {'kolové' if t == 'k' else 'pásové'}" +
                         (f", kolona po {dist:g} m" if dist else ""))

            def novy_gen(t=t, dist=dist):
                return nos.stavy_MLC(t, MLC, n_ob, dist, roz, extra=True)
        pul = 0.5 * (rozvor + b_k)
        if y_c - pul < vyb.chodnik_L - 1e-9 or y_c + pul > B - vyb.chodnik_P + 1e-9:
            varovani.append(f"Vozidlo {voz_popis} (šířka {2 * pul:.2f} m, osa y = {y_c:.2f} m) "
                            "přesahuje vozovku.")
        dx = K.x0(y_c)
        y1, y2 = y_c - 0.5 * rozvor, y_c + 0.5 * rozvor

        def stavy_q():
            for ax, _ in novy_gen():
                yield [(qq * dyn, s, e) for qq, s, e in ax], None

        def polohy():
            for ax, _ in stavy_q():
                yield platky_z_naprav(posun(ax, dx), y1, y2, b_k, roz)

        def popis(V, t):
            vp = f"Ve {t} t" if druh == "Ve" else voz_popis
            return (f"vozidlo {vp}, osa y = {y_c:.2f} m, δ = {dyn:g} ({dyn_zdroj}), "
                    f"roznos {roz:.2f} m, krok {krok:g} m")

        ob = obalky_2D(model, stavy_q(), y1, y2, b_k, roz, dx)
        stavy["q"] = StavSil("q", popis(Ve, f"{Ve:g}" if Ve else ""), ob.M_max, ob.M_min,
                             ob.Vm_max, ob.Vm_min, ob.Vp_max, ob.Vp_min, ob.Vs_max, ob.Vs_min,
                             pohyblivy=True, n_stavu=ob.n_stavu)
        attrs.update(V=float(Ve or 0.0), dyn=dyn, dyn_zdroj=dyn_zdroj, vozidlo=voz_popis,
                     rozvor=rozvor, b_k=b_k, poloha_q=f"osa y = {y_c:.2f} m",
                     stopy_q=[(y1, b_k), (y2, b_k)],
                     q_nastaveni=dict(typ="pojezd", polohy=polohy, meritko=1.0, popis=popis,
                                      vozidlo=lambda t: f"Ve {t} t"))
    elif druh in ("Vn", "Vr"):
        if n.get("y_Ve") is not None:
            varovani.append(f"Osa vozidla y se u {druh} nepoužije – zatížení je u kraje vozovky "
                            "u užšího chodníku.")
        if druh == "Vn":
            sch = n.get("schema") or sz.schema_Vn(Vn)
            r = _schema_Vn(model, vyst, K, vyb, Vn, sch, roz, krok, n["krok_chodnik"], dyn_zad)
        else:
            sch = n.get("schema") or sz.schema_Vr(Vr)
            r = _schema_Vr(model, vyst, K, vyb, Vr, sch, roz, krok, dyn_zad)
        V = float(Vn if druh == "Vn" else Vr)
        stavy["q"] = r["stav"]
        varovani += r["varovani"]
        attrs.update(V=V, schema_q=sch, dyn=r["dyn"], dyn_zdroj=r["dyn_zdroj"],
                     vozidlo=r["vozidlo"](f"{V:g}"), y_Ve=r["y"], poloha_q=r["poloha"],
                     stopy_q=r["stopy"], pruhy_q=r["pruhy"],
                     q_nastaveni=dict(r["q_nastaveni"], popis=lambda VV, t: r["popis"](VV),
                                      vozidlo=r["vozidlo"]))
        if "rozvor" in r:
            attrs.update(rozvor=r["rozvor"], b_k=r["b_k"])
    return dict(stavy=stavy, attrs=attrs, varovani=varovani)


def vys_s_vozidlem(vys: VysledekSil, **zmeny) -> VysledekSil:
    """Kopie výsledku s jiným pohyblivým zatížením na STEJNÉM modelu MKP (g0, g − g0 se
    nepřepočítávají; q a podle druhu vozidla q_ch ano).  zmeny = klíče nastavení q (viz
    vnitrni_sily): vozidlo Ve | MLC (typ_MLC, dist) | Vn | Vr (schema) – zadané vozidlo nahradí
    původní –, dále dyn, q_chodnik, y_Ve, krok, krok_chodnik."""
    nast = dict(vys.nastaveni_q)
    if any(k in zmeny for k in ("Ve", "MLC", "Vn", "Vr")):
        for k in ("Ve", "MLC", "Vn", "Vr", "schema"):
            nast[k] = None
    nast.update(zmeny)
    pr = _promenne(vys.model, vys.vyst, vys.K, vys.vybaveni, nast, vys.cache)
    out = copy.copy(vys)
    out.stavy = {k: v for k, v in vys.stavy.items() if k not in ("qch", "q")}
    out.stavy.update(pr["stavy"])
    for k, v in pr["attrs"].items():
        setattr(out, k, v)
    out.varovani = list(vys.varovani_zaklad) + pr["varovani"]
    out.nastaveni_q = nast
    return out


def vys_pro_V(vys: VysledekSil, V: float) -> VysledekSil:
    """Kopie výsledku se stavem q přeškálovaným na tíhu vozidla / zatížitelnost V [t]
    (Ve, Vn, Vr – účinky jsou v V lineární, polohy a schéma se nemění)."""
    if vys.druh_q not in ("Ve", "Vn", "Vr") or not vys.V or "q" not in vys.stavy:
        raise ValueError("Přeškálovat lze jen zatížení Ve, Vn nebo Vr s tíhou > 0.")
    k = V / vys.V
    q = vys.stavy["q"]
    qn = vys.q_nastaveni or {}
    t = f"{V:.1f}"
    pole = [getattr(q, a) * k for a in ("M_max", "M_min", "Vm_max", "Vm_min", "Vp_max", "Vp_min",
                                         "Vs_max", "Vs_min")]
    popis = qn["popis"](V, t) if "popis" in qn else q.popis
    out = copy.copy(vys)
    out.stavy = dict(vys.stavy)
    out.stavy["q"] = StavSil("q", popis, *pole, pohyblivy=True, n_stavu=q.n_stavu)
    out.V = float(V)
    if vys.druh_q == "Ve":
        out.Ve = float(V)
    if "vozidlo" in qn:
        out.vozidlo = qn["vozidlo"](t)
    if vys.q_nastaveni is not None:
        out.q_nastaveni = dict(qn, meritko=qn.get("meritko", 1.0) * k)
    return out


@dataclass
class PolohaVozidla:
    """Rozhodující poloha pohyblivého zatížení pro jeden řez posuzovaného výstupu."""
    ucel: str                  # "M" (max M) | "V" (max V)
    x: float                   # lokální x řezu na výstupu [m] (od osy první podpory)
    hodnota: float             # M [kNm] / V [kN] v řezu (deska: na 1 m)
    napravy: list              # (nepoužívá se – zachováno pro kompatibilitu)
    platky: list               # plošky kol (F, x0, x1, y0, y1) vč. δ – pro vykreslení
    stav: StavSil              # vnitřní síly všech výstupů v této poloze
    popis: str = ""
    plosne: list = field(default_factory=list)   # rovnoměrné zatížení (x0, x1, y0, y1, q) vč. δ


def _skaluj(platky: list, k: float) -> list:
    return [(F * k, x0, x1, y0, y1) for F, x0, x1, y0, y1 in platky]


def polohy_q(vys: VysledekSil, o: int, x_M: Optional[float] = None,
             x_V: Optional[float] = None, davka: int = 48) -> Dict[str, PolohaVozidla]:
    """Polohy zatížení q s maximem M v řezu x_M (výchozí střed 1. pole) a maximem V
    v řezu x_V (výchozí d od první podpory) na výstupu o.  Prohledají se stejné polohy
    jako pro obálku q (vozidlo: max M, max |V|; schéma Vn: náprava každého pruhu
    v nejnepříznivější poloze, rovnoměrné zatížení v úsecích s kladným účinkem, počet
    zatížených pruhů s největším δ_k·účinkem).  Vrací {"M": …, "V": …} (prázdné, není-li q)."""
    qn, model = vys.q_nastaveni, vys.model
    if qn is None or model is None:
        return {}
    Vy = vys.vyst
    i0, i1 = int(Vy.i0[o]), int(Vy.i1[o])
    xl = vys.x_lokalni(o)
    x_M = 0.5 * vys.K.L[0] if x_M is None else float(x_M)
    x_V = vys.K.d if x_V is None else float(x_V)
    kk = np.arange(i0, i1 + 1)

    def uzel(x):
        return int(kk[np.argmin(np.abs(xl[kk] - x))])

    kM, kV = uzel(x_M), uzel(x_V)
    S = Vy.S[o]
    m = float(qn.get("meritko", 1.0))

    def vyhodnot(seznam):
        """M v kM a V v kV (se znaménkem) pro seznam poloh (seznamů plošek); ok = zatížení
        na konstrukci."""
        n = len(seznam)
        vM, vV, ok = np.zeros(n), np.zeros(n), np.zeros(n, bool)
        idx, buf = [], []

        def zpracuj():
            U = model.res_batch(np.stack(buf, axis=1))
            PM, PVm, PVp = model.vyslednice(U)
            M = np.einsum("s,sxb->xb", S, PM)
            Vm = np.einsum("s,sxb->xb", S, PVm)
            Vp = np.einsum("s,sxb->xb", S, PVp)
            vM[idx] = M[kM]
            vV[idx] = Vp[kV] if kV == i0 else 0.5 * (Vm[kV] + Vp[kV])
            ok[idx] = True

        for j, pl in enumerate(seznam):
            f = model.zatizeni(pl)
            if not np.any(f):
                continue
            buf.append(f)
            idx.append(j)
            if len(buf) >= davka:
                zpracuj()
                idx, buf = [], []
        if buf:
            zpracuj()
        return vM, vV, ok

    volba = {}                       # key → (plošky kol, plošky úseků, plošné, popis zatížení)
    if qn.get("typ") == "sestava":
        delty = qn["delty"]

        def prispevek(slozka, useky):
            out = {"M": [0.0, [], [], []], "V": [0.0, [], [], []]}
            if slozka is not None:
                pol = list(slozka())
                vM, vV, ok = vyhodnot(pol)
                for key, v in (("M", vM), ("V", vV)):
                    if ok.any():
                        j = int(np.argmax(np.where(ok, v, -np.inf)))
                        if v[j] > 0:
                            out[key][0] += float(v[j])
                            out[key][1] += pol[j]
            if useky:
                uM, uV, _ = vyhodnot([u[0] for u in useky])
                for key, v in (("M", uM), ("V", uV)):
                    for j in np.nonzero(v > 0)[0]:
                        out[key][0] += float(v[j])
                        out[key][2] += useky[j][0]
                        out[key][3].append(useky[j][1])
            return out

        pruhy = [prispevek(s["pojezd"], s["useky"]) for s in qn["pruhy"]]
        zb = prispevek(None, qn["zbytek"])
        for key in ("M", "V"):
            cum, best = zb[key][0], (-np.inf, 1)
            for k, p in enumerate(pruhy, 1):
                cum += p[key][0]
                if delty[min(k, 3)] * cum > best[0]:
                    best = (delty[min(k, 3)] * cum, k)
            k = best[1]
            d = delty[min(k, 3)] * m
            casti = pruhy[:k] + [zb]
            kola = _skaluj([pl for c in casti for pl in c[key][1]], d)
            useky = _skaluj([pl for c in casti for pl in c[key][2]], d)
            plosne = [(x0, x1, y0, y1, q * d) for c in casti for x0, x1, y0, y1, q in c[key][3]]
            volba[key] = (kola, useky, plosne,
                          f"zatížen{'y pruhy 1–' + str(k) if k > 1 else ' pruh 1'}, "
                          f"δ = {delty[min(k, 3)]:.3g}")
    else:
        pol = list(qn["polohy"]())
        vM, vV, ok = vyhodnot(pol)
        if ok.any():
            jM = int(np.argmax(np.where(ok, vM, -np.inf)))
            jV = int(np.argmax(np.where(ok, np.abs(vV), -np.inf)))
            volba = {"M": (_skaluj(pol[jM], m), [], [], ""), "V": (_skaluj(pol[jV], m), [], [], "")}

    jm, jv = vys.jednotky
    out = {}
    for key, k in (("M", kM), ("V", kV)):
        if key not in volba:
            continue
        kola, useky, plosne, txt = volba[key]
        u = model.res(model.zatizeni(kola + useky))
        PM, PVm, PVp = model.vyslednice(u)
        st = StavSil.staly(f"q-{key}", "", Vy.S @ PM, Vy.S @ PVm, Vy.S @ PVp)
        txt = f" ({txt})" if txt else ""
        if key == "M":
            h = float(st.M_max[o, k])
            st.popis = (f"{vys.vozidlo} – poloha pro max M v řezu x = {xl[k]:.2f} m{txt}: "
                        f"M = {h:.1f} {jm}")
        else:
            h = float(st.Vp_max[o, k]) if k == i0 else float(st.Vs_max[o, k])
            st.popis = (f"{vys.vozidlo} – poloha pro max V v řezu x = {xl[k]:.2f} m od podpory"
                        f"{txt}: V = {h:.1f} {jv}")
        out[key] = PolohaVozidla(key, float(xl[k]), h, [], kola, st, st.popis, plosne)
    return out


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
