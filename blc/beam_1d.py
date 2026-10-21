"""
beam_1d.py
==========
1D analýza spojitého nosníku od pojezdu vozidel MLC a od schématu Ve.

METODA
------
Nosník konstantní tuhosti EI se sítí uzlů (Hermitovy prvky).  Jednou se
sestaví matice reakcí  Rmat[podpora, uzel]  = reakce podpory od jednotkové
síly v uzlu (tj. vlivové čáry reakcí).  Pro libovolné zatížení:

    f  = uzlové síly z obdélníkových zatížení (přesný 1. moment na prvek),
    R  = Rmat @ f                                (reakce podpor)
    M(x) = Σ_{x_j < x} R_j (x − x_j) − ∫ q (x − ξ) dξ      (vlevo od řezu)
    V(x) = Σ_{x_j < x} R_j          − ∫ q dξ               (V(x⁻))

Statisticky určitá část (integrály zatížení) se počítá přesně, jen reakce
vycházejí z vlivových čar.

Okrajové podmínky (K.uloz): u vetknutí („vetknuti“) se zabrání natočení
v podporách (dokonale, nebo rotační pružinou k_rot·L_p); momentové reakce C_j
vstupují do M(x) jako  + Σ_{x_j < x} C_j  a nad podporou se M skokem mění.
V uzlu podpory se pak bere strana s větší |M| (koncová podpora: M(x⁺)).
Tvrdé / měkké kloubové uložení je v 1D totožné (prostá podpora).
L_p = K.delka_podpory = podepřená délka napříč (deska B, nosníky N·b – spára
vlastní podporu nemá); pružná podpora má tuhost k_v·L_p (stejně jako ve 2D).

POJEZD
------
Vozidlo (nebo kolona) se posouvá po nosníku po kroku Ltot/(n·n_poli) v OBOU
směrech jízdy (zrcadlení kolem středu mostu).  K pravidelné mřížce poloh se
přidají polohy, kdy hrana zatížení padne přesně do kontrolního řezu x_k ± d
(skok V pod hranou zatížení).

KONTROLNÍ ŘEZY (viz geometry.py)
  M+ pole i       max. kladný moment v poli (rozhoduje řez s největším M)
  M- podpora k    záporný moment nad vnitřní podporou
  V               |V| v řezech x_k ± d; zatížení smí stát kdekoli
                  (i v pásu d u podpory)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

import numpy as np

from .geometry import Konstrukce, Rez, EPS
from .vehicles import pasove_vozidlo, kolove_vozidlo

Axle = Tuple[float, float, float]     # (q [kN/m], s [m], e [m])


# ---------------------------------------------------------------------------
# Generování náprav
# ---------------------------------------------------------------------------

def _axles_kolove(v, x1: float, k: int, dist: float) -> List[Axle]:
    b_ef = v.d
    delka_vozidla = v.a2 + v.a3 + v.a4 + v.a5 + b_ef
    offset = x1 - k * (dist + delka_vozidla)
    positions = [
        offset + v.a1,
        offset + v.a1 + v.a2,
        offset + v.a1 + v.a2 + v.a3,
        offset + v.a1 + v.a2 + v.a3 + v.a4,
        offset + v.a1 + v.a2 + v.a3 + v.a4 + v.a5,
    ]
    forces = [v.F1, v.F2, v.F3, v.F4, v.F5]
    return [(F / b_ef, pos - 0.5 * b_ef, pos + 0.5 * b_ef)
            for F, pos in zip(forces, positions)]


def _axles_pasove(v, x1: float, k: int, dist: float) -> List[Axle]:
    offset = x1 - k * (dist + v.a2)
    return [(v.F, offset + v.a1, offset + v.a1 + v.a2)]


def rozsir(axles: List[Axle], roz: float) -> List[Axle]:
    """Podélný roznos: ploška se prodlouží o roz/2 na každou stranu, síla zůstává."""
    if roz <= 0:
        return list(axles)
    out = []
    for q, s, e in axles:
        F = q * (e - s)
        s2, e2 = s - 0.5 * roz, e + 0.5 * roz
        out.append((F / (e2 - s2), s2, e2))
    return out


def zrcadli(axles: List[Axle], Ltot: float) -> List[Axle]:
    """Zrcadlení zatížení kolem středu mostu (opačný směr jízdy)."""
    return [(q, Ltot - e, Ltot - s) for q, s, e in axles]


# ---------------------------------------------------------------------------
# Výsledky
# ---------------------------------------------------------------------------

@dataclass
class CilVysledek:
    """Nejhorší stav pro jeden kontrolní řez (1D)."""
    rez: Rez
    hodnota: float                       # 1D maximum: kNm (M) nebo kN (V)
    axles: List[Axle]                    # původní (nerozšířené) nápravy
    x_gov: float                         # poloha rozhodujícího řezu [m]


@dataclass
class Beam1DResult:
    xs: np.ndarray
    M_max: np.ndarray                    # obálka max M(x) [kNm]
    M_min: np.ndarray                    # obálka min M(x) [kNm]
    V_max: np.ndarray                    # obálka max V(x⁻) [kN]
    V_min: np.ndarray
    cile: List[CilVysledek]
    Mmax_glob: float = 0.0               # max kladný moment přes celý most
    Mmin_glob: float = 0.0               # min záporný moment
    Vmax_glob: float = 0.0               # max |V| přes kontrolní řezy
    R_max: List[float] = field(default_factory=list)   # max reakce každé podpory
    L: float = 0.0
    x_podpor: List[float] = field(default_factory=list)
    x_rezy_V: List[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Spojitý nosník
# ---------------------------------------------------------------------------

class Nosnik1D:
    """Síť, matice reakcí a vyhodnocení jednoho zatěžovacího stavu."""

    def __init__(self, K: Konstrukce, n_elem_pole: int = 240):
        self.K = K
        self.Lt = K.Ltot
        self.xp = np.array(K.x_podpor)
        self.rezy = K.kontrolni_rezy()
        self.rezy_V = [r for r in self.rezy if r.typ == "V"]

        # ---- síť uzlů: tvrdé body = podpory a kontrolní řezy V -----------
        dx = min(K.L) / n_elem_pole
        hard = sorted(set([round(x, 10) for x in K.x_podpor] +
                          [round(r.x, 10) for r in self.rezy_V]))
        xs = [hard[0]]
        for a, b in zip(hard[:-1], hard[1:]):
            ne = max(1, int(math.ceil((b - a) / dx - 1e-9)))
            xs.extend(list(a + (b - a) * np.arange(1, ne + 1) / ne))
        self.xs = np.array(xs)
        self.nn = len(self.xs)
        self.ell = np.diff(self.xs)

        self.i_sup = np.array([self._uzel(x) for x in self.xp])
        self.i_V = np.array([self._uzel(r.x) for r in self.rezy_V], dtype=int)

        # maska podpor vlevo od každého V-řezu (včetně podpory v řezu u řezu typu P)
        mask = np.zeros((len(self.xp), len(self.rezy_V)), bool)
        for c, r in enumerate(self.rezy_V):
            for j, xj in enumerate(self.xp):
                if xj < r.x - EPS:
                    mask[j, c] = True
                elif abs(xj - r.x) <= EPS and r.strana == "P":
                    mask[j, c] = True
        self.mask_V = mask
        # V(x⁻) ve všech uzlech (pro obálku): podpory striktně vlevo
        self.mask_all = (self.xp[:, None] < self.xs[None, :] - EPS)

        self.Rmat = self._matice_reakci()

        # uzly jednotlivých polí (pro M+)
        self.uzly_pole = []
        for i in range(K.n_poli):
            lo, hi = self.xp[i], self.xp[i + 1]
            self.uzly_pole.append(np.where((self.xs >= lo - EPS) & (self.xs <= hi + EPS))[0])

    def _uzel(self, x: float) -> int:
        i = int(np.argmin(np.abs(self.xs - x)))
        if abs(self.xs[i] - x) > 1e-7:
            raise RuntimeError(f"Bod x = {x} není uzlem sítě.")
        return i

    # ---- matice reakcí ---------------------------------------------------
    def _matice_reakci(self) -> np.ndarray:
        """Vlivové čáry reakcí: svislé R (vrací se) a momentové self.Cmat."""
        nn, ell = self.nn, self.ell
        K = self.K
        Kg = np.zeros((2 * nn, 2 * nn))
        for e, l in enumerate(ell):
            ke = np.array([[12, 6 * l, -12, 6 * l],
                           [6 * l, 4 * l * l, -6 * l, 2 * l * l],
                           [-12, -6 * l, 12, -6 * l],
                           [6 * l, 2 * l * l, -6 * l, 4 * l * l]]) / l ** 3
            idx = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
            Kg[np.ix_(idx, idx)] += ke
        dw = 2 * self.i_sup                    # svislé posuny podpor
        dt = 2 * self.i_sup + 1                # natočení v podporách
        F = np.zeros((2 * nn, nn))
        F[2 * np.arange(nn), np.arange(nn)] = 1.0
        Kp = Kg.copy()
        fixed = []
        if K.pruzna:
            # pružné podpory: tuhost k_pod · L_p (podepřená délka – jen nosníky,
            # spára bez podpory), v soustavě s jednotkovou EI → /EI
            Kp[dw, dw] += K.k_pod * K.delka_podpory / K.EI_celk
        else:
            fixed += list(dw)
        if K.vetknuti:
            if K.k_rot:
                Kp[dt, dt] += K.k_rot * K.delka_podpory / K.EI_celk
            else:
                fixed += list(dt)
        free = np.setdiff1d(np.arange(2 * nn), np.array(fixed, dtype=int))
        U = np.zeros((2 * nn, nn))
        U[free] = np.linalg.solve(Kp[np.ix_(free, free)], F[free])
        S = Kg @ U - F                         # síly podpor na nosník (+ = ve směru zatížení)
        self.Cmat = S[dt]                      # momentové reakce (konvence: M(x) += Σ C_j)
        return -S[dw]                          # svislé reakce, vzhůru kladně (n_podpor, nn)

    # ---- jeden zatěžovací stav -------------------------------------------
    def stav(self, axles: List[Axle]):
        """
        Returns:
            M  (nn,)        ohybový moment v uzlech
            Vn (nn,)        V(x⁻) v uzlech
            Vr (n_rezV,)    V v kontrolních řezech
            R  (n_podpor,)  reakce
        """
        xs, Lt = self.xs, self.Lt
        nn = self.nn
        if not axles:
            z = np.zeros(nn)
            return z, z.copy(), np.zeros(len(self.rezy_V)), np.zeros(len(self.xp))
        A = np.asarray(axles, float)
        q = A[:, 0]
        s = np.clip(A[:, 1], 0.0, Lt)
        e = np.clip(A[:, 2], 0.0, Lt)
        ok = e > s + 1e-12
        if not ok.any():
            z = np.zeros(nn)
            return z, z.copy(), np.zeros(len(self.rezy_V)), np.zeros(len(self.xp))
        # síla beze změny při ořezu (plocha za krajní podporou jde do opěry)
        q, s, e = q[ok], s[ok][:, None], e[ok][:, None]
        q = q[:, None]

        # uzlové síly
        a = np.maximum(s, xs[None, :-1])
        bb = np.minimum(e, xs[None, 1:])
        w = np.maximum(bb - a, 0.0)
        mid = 0.5 * (a + bb)
        wq = q * w
        fi = (wq * (xs[None, 1:] - mid) / self.ell[None, :]).sum(axis=0)
        fj = (wq * (mid - xs[None, :-1]) / self.ell[None, :]).sum(axis=0)
        f = np.zeros(nn)
        f[:-1] += fi
        f[1:] += fj
        R = self.Rmat @ f
        C = self.Cmat @ f if self.K.vetknuti else None

        # moment a posouvající síla vlevo od uzlu
        ee = np.minimum(e, xs[None, :])
        ln = np.maximum(ee - s, 0.0)
        pos = ln > 0
        mom = (q * (xs[None, :] * ln - 0.5 * (ee ** 2 - s ** 2) * pos)).sum(axis=0)
        M = (R[:, None] * np.maximum(xs[None, :] - self.xp[:, None], 0.0)
             * self.mask_all).sum(axis=0) - mom
        if C is not None:
            # momentové reakce vetknutí: skok M nad podporou; v uzlu podpory
            # se bere strana s větší |M| (u koncové podpory tedy M(x⁺))
            M = M + (C[:, None] * self.mask_all).sum(axis=0)
            Ms = M[self.i_sup]
            Mp = Ms + C
            M[self.i_sup] = np.where(np.abs(Mp) > np.abs(Ms), Mp, Ms)
        load_left = (q * ln).sum(axis=0)
        Vn = (R[:, None] * self.mask_all).sum(axis=0) - load_left
        Vr = (R[:, None] * self.mask_V).sum(axis=0) - load_left[self.i_V]
        return M, Vn, Vr, R

    # ---- prohledání stavů ------------------------------------------------
    def prohledej(self, stavy) -> Beam1DResult:
        """
        stavy: iterovatelné dvojice (axles_puvodni, axles_rozsirene).
        """
        K, xs, Lt = self.K, self.xs, self.Lt
        nn = self.nn
        M_max = np.full(nn, -np.inf); M_min = np.full(nn, np.inf)
        V_max = np.full(nn, -np.inf); V_min = np.full(nn, np.inf)
        R_max = np.zeros(len(self.xp))

        cile = []
        best = [[-1.0, None, r.x] for r in self.rezy]      # [hodnota, axles, x_gov]
        idx_V = {id(r): c for c, r in enumerate(self.rezy_V)}

        for ax0, ax_r in stavy:
            M, Vn, Vr, R = self.stav(ax_r)
            np.maximum(M_max, M, out=M_max); np.minimum(M_min, M, out=M_min)
            np.maximum(V_max, Vn, out=V_max); np.minimum(V_min, Vn, out=V_min)
            np.maximum(R_max, R, out=R_max)
            for t, r in enumerate(self.rezy):
                if r.typ == "M+":
                    ii = self.uzly_pole[r.pole]
                    j = int(np.argmax(M[ii]))
                    val, xg = float(M[ii][j]), float(xs[ii][j])
                elif r.typ == "M-":
                    val, xg = -float(M[self.i_sup[r.podpora]]), r.x
                else:
                    val, xg = abs(float(Vr[idx_V[id(r)]])), r.x
                if val > best[t][0]:
                    best[t] = [val, ax0, xg]

        for t, r in enumerate(self.rezy):
            v, ax, xg = best[t]
            cile.append(CilVysledek(r, max(v, 0.0), ax, xg))

        Vv = [c.hodnota for c in cile if c.rez.typ == "V"]
        return Beam1DResult(
            xs=xs, M_max=M_max, M_min=M_min, V_max=V_max, V_min=V_min,
            cile=cile,
            Mmax_glob=float(M_max.max()), Mmin_glob=float(M_min.min()),
            Vmax_glob=max(Vv) if Vv else float(np.abs(V_max).max()),
            R_max=R_max.tolist(), L=Lt, x_podpor=list(K.x_podpor),
            x_rezy_V=[r.x for r in self.rezy_V],
        )

    # ---- generátory stavů ------------------------------------------------
    def _hranice_pasu(self) -> set:
        """Polohy kontrolních řezů V uvnitř mostu (x_k ± d, d > 0)."""
        return {r.x for r in self.rezy_V if not r.na_podpore}

    def _polohy(self, mk, n_total: int, roz: float, x1_min: float, x1_max: float,
                extra: bool = True) -> List[float]:
        """Mřížka poloh x1 (zarovnaná na 0) + polohy s hranou zatížení na hranici zóny."""
        dx = self.Lt / n_total
        i0 = int(math.floor(x1_min / dx))
        i1 = int(math.ceil(x1_max / dx))
        pol = [i * dx for i in range(i0, i1 + 1)]
        cile = self._hranice_pasu() if extra else set()
        if cile:
            hrany = [t for _, s0, e0 in rozsir(mk(0.0), roz) for t in (s0, e0)]
            for c in cile:
                for t in hrany:
                    x1 = c - t
                    if x1_min - 1e-9 <= x1 <= x1_max + 1e-9:
                        pol.append(x1)
        return pol

    def stavy_MLC(self, typ: str, MLC: str, n: int, dist: float, roz: float,
                  extra: bool = True):
        """Generátor dvojic (nápravy, nápravy s podélným roznosem); oba směry jízdy.
        extra=False: jen pravidelná mřížka poloh (pro 2D obálky)."""
        K, Lt = self.K, self.Lt
        typ = typ.lower()
        v = kolove_vozidlo(MLC) if typ == "k" else pasove_vozidlo(MLC)
        Nveh = math.ceil(Lt / dist) + 1

        def kolona(x1):
            ax = []
            for k in range(Nveh + 1):
                ax.extend(_axles_kolove(v, x1, k, dist) if typ == "k"
                          else _axles_pasove(v, x1, k, dist))
            return ax

        ext = max(e for _, s, e in kolona(0.0)[:5 if typ == "k" else 1]) + roz
        n_tot = max(1, n * K.n_poli)
        pol = self._polohy(kolona, n_tot, roz, -ext - Lt / n_tot, Lt, extra)
        for x1 in pol:
            ax = kolona(x1)
            yield ax, rozsir(ax, roz)
            axm = zrcadli(ax, Lt)
            yield axm, rozsir(axm, roz)

    def stavy_Ve(self, Ve: float, n: int, roz: float, extra: bool = True):
        K, Lt = self.K, self.Lt
        bw, a = 0.15, 1.5
        F = (10.0 / 9.0) * Ve / bw

        def vlak(x1):
            return [(F, x1 + k * a - 0.5 * bw, x1 + k * a + 0.5 * bw) for k in range(9)]

        n_tot = max(1, n * K.n_poli)
        dx = Lt / n_tot
        pol = []
        i = 0
        while True:
            x1 = 0.5 * bw + i * dx
            if x1 + 8 * a + 0.5 * bw >= Lt:
                pol.append(Lt - 8 * a - 0.5 * bw)
                break
            pol.append(x1)
            i += 1
        cile = self._hranice_pasu() if extra else set()
        hrany = [t for _, s0, e0 in rozsir(vlak(0.0), roz) for t in (s0, e0)]
        for c in cile:
            for t in hrany:
                pol.append(c - t)
        for x1 in pol:
            ax = vlak(x1)
            yield ax, rozsir(ax, roz)


# ---------------------------------------------------------------------------
# Veřejné funkce
# ---------------------------------------------------------------------------

def vypocet_MLC(nos: Nosnik1D, typ: str, MLC: str, n: int, dist: float,
                roz: float = 0.0) -> Beam1DResult:
    v = kolove_vozidlo(MLC) if typ.lower() == "k" else pasove_vozidlo(MLC)
    res = nos.prohledej(nos.stavy_MLC(typ, MLC, n, dist, roz))
    res.rozvor, res.b_k = v.rozvor, v.b_k
    return res


def vypocet_Ve(nos: Nosnik1D, Ve: float, n: int, roz: float = 0.0) -> Beam1DResult:
    res = nos.prohledej(nos.stavy_Ve(Ve, n, roz))
    res.rozvor, res.b_k = 1.5, 1.2
    return res
