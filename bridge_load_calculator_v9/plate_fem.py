"""
plate_fem.py  (v9)
==================
2D model mostovky přes VÍCE POLÍ metodou konečných prvků (MITC4).

Konstrukce se skládá z podélných PRUHŮ; každý pruh je obdélník v lokálních
souřadnicích (x ve směru osy prvku, y napříč) a může být v podélném směru
posunut o x0 (šikmý most):

  • nosníky ("nosniky"): pruh = nosník (šířka b, tloušťka h_ekv), volitelně
    mezi nosníky pruh spáry (b_s, h_s, E_s); kloubové spojení (βy zvlášť
    v každém pruhu) nebo tuhé; nosník má kolmé čelo a podporu přes celou
    svou šířku v místě, kde jeho osa protíná šikmou osu podpory (obr. 1);
    podepřeny jsou VŽDY jen nosníky – spára vlastní podporu nemá (kolmý
    i šikmý most; v9 od 13. 10. 2026, dříve byla u kolmého mostu podepřena),
  • deska ("deska"): deska šířky b a tloušťky h rozdělená na úzké pruhy
    šířky c ≈ ex s tuhým spojením; každý pruh je podepřen v místě, kde jeho
    osa protíná šikmou osu podpory → liniové uložení podél šikmé osy
    (obr. 2) aproximované schodovitě po pruzích šířky c.

Podpory jsou liniové přes šířku pruhu; okrajové podmínky (v9, K.uloz):
  tvrdé    w = 0 (pružina k_v), βy = 0 (u pružné podpory βy = ∂w/∂y podél
           linie podpory – bez parazitního smyku),
  měkké    jen w, βx i βy volné,
  vetknutí jako tvrdé + βx = 0 (pružné vetknutí: rotační pružina k_rot na βx).
(Šikmá deska v tomto modelu – starší schodovitá varianta – zůstává tvrdá/kloubová;
 výpočet desky používá slab_fem.DeskaSikmaMKP.)
Síť podél x je společná pro všechny pruhy (sjednocení poloh podpor všech
pruhů; body bližší než 0,3·ex se sloučí), takže sousední pruhy sdílejí uzly
na společné hraně.

Výslednice (vždy ve směru osy prvku, na řezu kolmém k ose):
  M_s(x), V_s(x⁻), V_s(x⁺) každého pruhu metodou uzlových sil (řídké matice
  výslednic → rychlé pro mnoho zatěžovacích stavů).
  VÝSTUPY:  nosníky → hodnoty na nosnících;
            deska   → hodnoty zintegrované na pás šířky 1 m (klouzavé okno
                      přes pruhy, přepočteno na přesně 1 m).

Kontrola rovnováhy: Σ všech pruhů vs statika z uzlových sil a skutečných
reakcí jednotlivých podepřených uzlů (platí i pro šikmé uložení).

Stupně volnosti uzlu: w, βx, βy.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .geometry import Konstrukce, Rez, EPS

# smykový opravný součinitel Mindlinovy desky (obdélníkový průřez): k·G·h, κ = 5/6
KAPPA = 5.0 / 6.0
# znaménko momentové reakce (f − K·u na βx) v momentu M(x) levé části (v9)
ROT_ZNAM = -1.0

Axle = Tuple[float, float, float]                    # (q [kN/m], s, e)
Platek = Tuple[float, float, float, float, float]    # (F [kN], x0, x1, y0, y1)


# ---------------------------------------------------------------------------
# Prvek MITC4 (shodný s v5)
# ---------------------------------------------------------------------------

def ke_mitc4(a: float, c: float, D: float, nu: float, kGh: float) -> np.ndarray:
    xn = np.array([-1, 1, 1, -1.]); en = np.array([-1, -1, 1, 1.])
    Nf = lambda x, e: 0.25 * (1 + x * xn) * (1 + e * en)

    def dN(x, e):
        return 0.25 * xn * (1 + e * en) * (2 / a), 0.25 * en * (1 + x * xn) * (2 / c)

    Db = D * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])
    g = 1 / math.sqrt(3)
    gp = [(-g, -g), (g, -g), (g, g), (-g, g)]
    dJ = a * c / 4
    K = np.zeros((12, 12))
    for x, e in gp:
        dx, dy = dN(x, e)
        B = np.zeros((3, 12))
        B[0, 1::3] = dx
        B[1, 2::3] = dy
        B[2, 1::3] = dy; B[2, 2::3] = dx
        K += B.T @ Db @ B * dJ

    def Bs(x, e):
        n = Nf(x, e); dx, dy = dN(x, e)
        B = np.zeros((2, 12))
        B[0, 0::3] = dx; B[0, 1::3] = -n
        B[1, 0::3] = dy; B[1, 2::3] = -n
        return B

    BA, BC = Bs(0, -1)[0], Bs(0, 1)[0]
    BD, BB = Bs(-1, 0)[1], Bs(1, 0)[1]
    for x, e in gp:
        B = np.vstack([0.5 * (1 - e) * BA + 0.5 * (1 + e) * BC,
                       0.5 * (1 - x) * BD + 0.5 * (1 + x) * BB])
        K += B.T @ B * kGh * dJ
    return K



# ---------------------------------------------------------------------------
# Výstupy (nosníky nebo pásy 1 m) nad pruhy modelu
# ---------------------------------------------------------------------------

@dataclass
class Vystupy:
    """Jak se z pruhů skládají posuzované výstupy."""
    S: np.ndarray                 # (n_out, n_pruhu) váhy pruhů
    skup: List[np.ndarray]        # indexy pruhů každého výstupu
    faktor: np.ndarray            # (n_out,) váha (1, u desky 1/šířka okna)
    i0: np.ndarray                # první uzel výstupu
    i1: np.ndarray                # poslední uzel výstupu
    skoky: List[np.ndarray]       # uzly podpor výstupu (skutečné skoky V)
    x0: np.ndarray                # (n_out,) střední posun čela (podpory 1)
    y: np.ndarray                 # (n_out,) příčná poloha osy výstupu
    popisky: List[str]
    deska: bool = False
    sirka_okna: float = 1.0       # deska: skutečná šířka okna z pruhů [m]
    skoky_vse: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    x0_glob: Optional[np.ndarray] = None   # deska: posun os výstupů do globálního x
    lokalni: bool = False                  # True: xs je ξ (vzdálenost od osy podpory)

    @property
    def n(self) -> int:
        return len(self.skup)


# ---------------------------------------------------------------------------
# Model desky
# ---------------------------------------------------------------------------

class DeskaMKP:
    """
    Args:
        K:     Konstrukce (pole, typ nosníky/deska, spáry, šikmost, E, ν)
        ex:    cílová délka prvku podél rozpětí [m] (u desky i šířka pruhu)
        ney:   min. počet prvků napříč nosníkem (zvýší se, aby c ≤ a)
        spoj:  "kloub" | "deska" – spojení nosníků BEZ spáry
               (se spárou vždy kloub, deska je vždy tuhá)
    """

    def __init__(self, K: Konstrukce, ex: float = 0.0625, ney: int = 4,
                 spoj: str = "kloub"):
        self.K = K
        self.L = K.Ltot
        self.B = K.B
        self.N = K.N
        self.b, self.h = K.b, K.h_ekv
        self.spoj = "deska" if K.je_deska else ("kloub" if K.spara else spoj)
        nu = K.nu
        E = K.E * 1000.0
        sikmy = K.sikmy
        self.ex = ex

        # ---- pruhy napříč ---------------------------------------------------
        pr = []                                   # (typ, y0, w, h, E)
        if K.je_deska:
            m = max(1, int(math.ceil(1.0 / ex - 1e-9)))       # pruhů na 1 m
            ns = max(1, int(round(self.B * m)))
            c = self.B / ns
            for i in range(ns):
                pr.append(("d", i * c, c, K.h, E))
        else:
            y = 0.0
            for i in range(K.N):
                pr.append(("n", y, K.b, K.h_ekv, E)); y += K.b
                if K.spara and i < K.N - 1:
                    pr.append(("s", y, K.b_s, K.h_spary, K.E_spary * 1000.0)); y += K.b_s
        self.n_pruhu = ns = len(pr)
        self.p_typ = np.array([p[0] for p in pr])
        self.p_y0 = np.array([p[1] for p in pr])
        self.p_w = np.array([p[2] for p in pr])
        x0_teor = np.array([K.x0(p[1] + 0.5 * p[2]) for p in pr])
        # hranice pruhů (podélné styčné čáry) a jejich posun podpory
        y_hr = np.concatenate([self.p_y0, [self.B]])
        x0_hr = np.array([K.x0(y) for y in y_hr])
        # deska: každá hranice pruhů má vlastní polohu podpory na šikmé ose
        hr_vlastni = np.full(ns + 1, bool(K.je_deska))
        hr_pruh = np.minimum(np.arange(ns + 1), ns - 1)

        # ---- síť podél x: společná pro všechny pruhy -------------------------
        xp = np.array(K.x_podpor)
        x0_vse = list(x0_teor) + list(x0_hr[hr_vlastni])
        pts = sorted(set(round(float(x0 + v), 9) for x0 in x0_vse for v in xp))
        tol = 0.05 * ex if sikmy else 1e-9
        hard = [pts[0]]
        for p in pts[1:]:
            if p - hard[-1] > tol:
                hard.append(p)
        if sikmy and abs(hard[-1] - pts[-1]) > 1e-12:
            hard[-1] = pts[-1]
        nmin = 1 if sikmy else 2
        xs = [hard[0]]
        i_hard = [0]
        for a, b in zip(hard[:-1], hard[1:]):
            ne = max(nmin, int(round((b - a) / ex)))
            if len(hard) == 2:
                ne = max(8, ne)                  # shodné s v5 pro jedno kolmé pole
            xs.extend(list(a + (b - a) * np.arange(1, ne + 1) / ne))
            i_hard.append(len(xs) - 1)
        self.xs = np.array(xs)
        self.nx = nx = len(self.xs)
        self.nex = nx - 1
        self.a_el = np.diff(self.xs)
        self.a_min = float(self.a_el.min())
        a_ref = float(np.median(self.a_el)) if sikmy else self.a_min
        self.a_ref = a_ref
        hard = np.array(hard)
        i_hard = np.array(i_hard)

        def uzel(x):
            return int(i_hard[int(np.argmin(np.abs(hard - x)))])

        p_sup = np.array([[uzel(x0 + v) for v in xp] for x0 in x0_teor], dtype=int)
        hr_sup = np.array([[uzel(x0_hr[bnd] + v) for v in xp] if hr_vlastni[bnd]
                           else list(p_sup[hr_pruh[bnd]]) for bnd in range(ns + 1)], dtype=int)
        self.hr_sup = hr_sup                                  # uzly podpor hranic pruhů
        if K.je_deska:
            # pruh desky: od dřívější z podpor jeho hranic po pozdější
            self.p_sup = np.rint(0.5 * (hr_sup[:-1] + hr_sup[1:])).astype(int)
            self.p_i0 = np.minimum(hr_sup[:-1, 0], hr_sup[1:, 0])
            self.p_i1 = np.maximum(hr_sup[:-1, -1], hr_sup[1:, -1])
        else:
            self.p_sup = p_sup
            self.p_i0 = p_sup[:, 0].copy()
            self.p_i1 = p_sup[:, -1].copy()
        self.p_xsup = self.xs[self.p_sup]                     # skutečné polohy podpor
        if K.je_deska:
            self.p_xsup = 0.5 * (self.xs[hr_sup[:-1]] + self.xs[hr_sup[1:]])
        self.p_x0 = self.xs[self.p_i0]
        self.p_nex = self.p_i1 - self.p_i0

        # ---- prvky napříč, tuhosti ------------------------------------------
        def n_prvku(w, nmin_):
            return max(nmin_, int(math.ceil(w / a_ref - 1e-9)))
        p_ney = []
        for t, _, w, _, _ in pr:
            nn = n_prvku(w, max(1, int(ney))) if t == "n" else n_prvku(w, 2) if t == "s" else 1
            p_ney.append(nn)
        self.p_ney = np.array(p_ney, dtype=int)
        self.p_c = self.p_w / self.p_ney
        self.ney = int(self.p_ney[self.p_typ != "s"][0])
        self.c = float(self.p_c[self.p_typ != "s"][0])
        self.p_g0 = np.concatenate([[0], np.cumsum(self.p_ney)[:-1]]).astype(int)
        self.p_by0 = np.concatenate([[0], np.cumsum(self.p_ney + 1)[:-1]]).astype(int)
        ng = int(self.p_ney.sum()) + 1
        self._ng = ng
        self._nw = nw = ng * nx
        if self.spoj == "deska":
            self.ndof = 3 * nw
        else:
            self.ndof = 2 * nw + int((self.p_ney + 1).sum()) * nx

        ke_tab, ke_idx = [], {}

        def ke(s, a):
            t, _, w, h, Et = pr[s]
            c = w / self.p_ney[s]
            key = (round(c, 9), round(h, 9), round(Et, 3), round(float(a), 9))
            if key not in ke_idx:
                Gt = Et / (2 * (1 + nu))
                D = Et * h ** 3 / (12 * (1 - nu ** 2))
                ke_idx[key] = len(ke_tab)
                ke_tab.append(ke_mitc4(float(a), c, D, nu, KAPPA * Gt * h))
            return ke_idx[key]

        dof_l, e_s, e_ix, e_ke, off = [], [], [], [], [0]
        for s in range(ns):
            ny, i0, i1 = self.p_ney[s], self.p_i0[s], self.p_i1[s]
            iy, ix = np.meshgrid(np.arange(ny), np.arange(i0, i1), indexing="ij")
            iy, ix = iy.ravel(), ix.ravel()
            cols = []
            for djl, dk in ((0, 0), (0, 1), (1, 1), (1, 0)):
                jl = iy + djl; k = ix + dk
                g = self.p_g0[s] + jl
                cols += [self._W(g, k), self._BX(g, k), self._BY(s, jl, k)]
            dof_l.append(np.stack(cols, axis=1))
            e_s.append(np.full(len(ix), s)); e_ix.append(ix)
            kk = {i: ke(s, self.a_el[i]) for i in range(i0, i1)}
            e_ke.append(np.array([kk[i] for i in ix], dtype=int))
            off.append(off[-1] + len(ix))
        self.E_dofs = np.concatenate(dof_l)
        self.e_strip = np.concatenate(e_s)
        self.e_ix = np.concatenate(e_ix)
        self.e_ke = np.concatenate(e_ke)
        self.p_off = np.array(off[:-1])
        self.Ke_tab = np.array(ke_tab)

        ne = len(self.E_dofs)
        Kt = self.Ke_tab[self.e_ke]
        rr = np.repeat(self.E_dofs, 12, axis=1).ravel()
        cc = np.tile(self.E_dofs, (1, 12)).ravel()
        self.Kfull = sp.csr_matrix((Kt.reshape(ne, 144).ravel(), (rr, cc)),
                                   shape=(self.ndof, self.ndof))

        # ---- matice výslednic (řez kolmý k ose, uzlové síly) ----------------
        cVm = Kt[:, 3, :] + Kt[:, 6, :]
        cM = -(Kt[:, 4, :] + Kt[:, 7, :])
        cVp = -(Kt[:, 0, :] + Kt[:, 9, :])
        row_m = np.repeat(self.e_strip * nx + self.e_ix + 1, 12)
        row_p = np.repeat(self.e_strip * nx + self.e_ix, 12)
        col = self.E_dofs.ravel()
        shp = (ns * nx, self.ndof)
        self.R_M = sp.csr_matrix((cM.ravel(), (row_m, col)), shape=shp)
        self.R_Vm = sp.csr_matrix((cVm.ravel(), (row_m, col)), shape=shp)
        self.R_Vp = sp.csr_matrix((cVp.ravel(), (row_p, col)), shape=shp)
        # v9: M(x⁺) z prvků vpravo od uzlu (potřeba u vetknutí – koncová podpora,
        # skok M nad vnitřní podporou)
        cMp = Kt[:, 1, :] + Kt[:, 10, :]
        self.R_Mp = sp.csr_matrix((cMp.ravel(), (row_p, col)), shape=shp)
        del Kt

        # ---- podepření -------------------------------------------------------
        # Podepření (w = 0; βy = 0 = „tvrdé“ kloubové uložení kolem osy y):
        #  kolmá deska: každá čára pruhu v uzlu podpory pruhu, βy = 0 (jako v7).
        #  šikmý most – deska (obr. 2): každá podélná čára v uzlu, kde ji
        #     protíná šikmá osa podpory (schodovitě po pruzích), βy volné
        #     (βy = 0 by na šikmé linii znamenalo i ∂w/∂x = 0, tj. vetknutí).
        #  nosníky (kolmý i šikmý most, obr. 1): nosník s kolmým čelem je
        #     podepřen liniově přes celou svou šířku (kolmo k ose) v místě, kde
        #     jeho osa protíná osu podpory, βy = 0.
        #  Spára vlastní podporu NEMÁ nikdy (ani u kolmého mostu – do 13. 10. 2026
        #     byla u kolmého mostu podepřena, u šikmého ne): ložiska jsou jen pod
        #     nosníky; okrajové uzly spáry sdílejí w (a βx) s podepřenými okraji
        #     nosníků, vnitřní uzly spáry na linii podpory jsou volné. Samostatné
        #     podepření spáry v jiném místě než sousední nosníky by navíc u šikmého
        #     mostu vytvořilo umělé vetknutí okrajů nosníků.
        fix, reac, reac_j = [], {}, {}
        trib: Dict[int, float] = {}            # zatěžovací šířka uzlu podpory [m]
        dep: Dict[int, list] = {}              # závislý dof → [(řídicí dof, koef.)]
        rot: Dict[int, float] = {}             # βx v podpoře → zatěžovací šířka (vetknutí)
        _sp = {"s": 0, "jl": 0}
        tvrde, vetkn = K.tvrde, K.vetknuti

        def podepri(dw, k, j):
            dw = int(dw)
            if not K.pruzna:
                fix.append(dw)
            reac[dw] = k; reac_j[dw] = j
            s_, jl_ = _sp["s"], _sp["jl"]
            c_ = float(self.p_c[s_])
            trib[dw] = trib.get(dw, 0.0) + (0.5 * c_ if jl_ in (0, self.p_ney[s_]) else c_)

        def rotace(s_, jl, ks, ny):
            """Okrajové podmínky natočení v uzlu liniové podpory pruhu s_ (kolmé čelo)."""
            g = self.p_g0[s_] + jl
            dby = int(self._BY(s_, jl, ks))
            if tvrde:
                if not K.beta_s_sleduje:
                    fix.append(dby)                       # βy = 0
                else:
                    # βy = ∂w/∂y podél linie podpory (centrální / jednostranná diference)
                    c_ = float(self.p_c[s_])
                    if jl == 0:
                        dep[dby] = [(self._W(g + 1, ks), 1 / c_), (self._W(g, ks), -1 / c_)]
                    elif jl == ny:
                        dep[dby] = [(self._W(g, ks), 1 / c_), (self._W(g - 1, ks), -1 / c_)]
                    else:
                        dep[dby] = [(self._W(g + 1, ks), 0.5 / c_),
                                    (self._W(g - 1, ks), -0.5 / c_)]
            if vetkn:
                dbx = int(self._BX(g, ks))
                c_ = float(self.p_c[s_])
                t_ = 0.5 * c_ if jl in (0, ny) else c_
                if K.k_rot:
                    rot[dbx] = rot.get(dbx, 0.0) + t_
                else:
                    fix.append(dbx)
                    rot[dbx] = rot.get(dbx, 0.0) + t_

        for s in range(ns):
            ny, t = self.p_ney[s], pr[s][0]
            if t == "s":
                continue                    # spára: bez podpory (kolmý i šikmý most)
            for j in range(len(xp)):
                ks = int(self.p_sup[s, j])
                for jl in range(ny + 1):
                    g = self.p_g0[s] + jl
                    _sp["s"], _sp["jl"] = s, jl
                    if K.je_deska and sikmy:
                        if jl in (0, ny):
                            k = int(hr_sup[s + (jl == ny), j])
                            podepri(self._W(g, k), k, j)
                    else:
                        # nosník (kolmý i šikmý most) / pruh kolmé desky: liniová
                        # podpora přes celou šířku čela (kolmo k ose) v místě
                        # průsečíku osy pruhu s osou podpory
                        podepri(self._W(g, ks), ks, j)
                        rotace(s, jl, ks, ny)
        used = np.zeros(self.ndof, bool)
        used[self.E_dofs.ravel()] = True
        fix = np.unique(np.concatenate([np.array(fix, dtype=int), np.where(~used)[0]]))
        self.reac_dof = np.array(sorted(reac), dtype=int)
        self.reac_x = self.xs[[reac[d] for d in self.reac_dof]]
        self.reac_j = np.array([reac_j[d] for d in self.reac_dof], dtype=int)
        # momentové reakce vetknutí (βx v podporách) – pro kontrolu statiky
        self.reac_rot_dof = np.array(sorted(rot), dtype=int)
        self.reac_rot_x = self.xs[self.reac_rot_dof % nx] if len(rot) else np.zeros(0)
        fixed = np.zeros(self.ndof, bool); fixed[fix] = True
        depm = np.zeros(self.ndof, bool)
        for d_ in dep:
            depm[d_] = True
        nez = np.where(~fixed & ~depm)[0]
        col_of = -np.ones(self.ndof, int); col_of[nez] = np.arange(len(nez))
        ri = list(nez); ci = list(range(len(nez))); vi = [1.0] * len(nez)
        for d_, lst in dep.items():
            for m_, cf in lst:
                if col_of[m_] >= 0:
                    ri.append(d_); ci.append(col_of[m_]); vi.append(cf)
        self.T = sp.csr_matrix((vi, (ri, ci)), shape=(self.ndof, len(nez)))
        self.free = nez
        kd = np.zeros(self.ndof)
        if K.pruzna:
            # pružné uložení: pružiny k_pod · zatěžovací šířka uzlu na w
            for d_, t_ in trib.items():
                kd[d_] += K.k_pod * t_
            self.k_uzlu = kd[self.reac_dof]
        else:
            self.k_uzlu = None
        if vetkn and K.k_rot:
            for d_, t_ in rot.items():
                kd[d_] += K.k_rot * t_
        Ks = (self.Kfull + sp.diags(kd)).tocsr() if kd.any() else self.Kfull
        Kr = (self.T.T @ Ks @ self.T).tocsc()
        self._lu = spla.splu(Kr, permc_spec="MMD_ATA")   # menší zaplnění než COLAMD

        self.i_nos = np.where(self.p_typ == "n")[0]
        self.i_spar = np.where(self.p_typ == "s")[0]
        self.vyst = self._vystupy()

    # ---- číslování stupňů volnosti ------------------------------------
    def _W(self, g, k):  return g * self.nx + k
    def _BX(self, g, k): return self._nw + g * self.nx + k
    def _BY(self, s, jl, k):
        if self.spoj == "deska":
            return 2 * self._nw + (self.p_g0[s] + jl) * self.nx + k
        return 2 * self._nw + (self.p_by0[s] + jl) * self.nx + k

    # ---- výstupy ------------------------------------------------------
    def _vystupy(self) -> Vystupy:
        ns = self.n_pruhu
        if self.K.je_deska:
            m = max(1, int(round(1.0 / float(self.p_w[0]))))
            m = min(m, ns)
            skup = [np.arange(j, j + m) for j in range(ns - m + 1)]
            sirka = float(self.p_w[:m].sum())
            fak = np.full(len(skup), 1.0 / sirka)
        else:
            skup = [np.array([s]) for s in self.i_nos]
            sirka = 1.0
            fak = np.ones(len(skup))
        S = np.zeros((len(skup), ns))
        for o, g in enumerate(skup):
            S[o, g] = fak[o]
        yc = np.array([float((self.p_y0[g] + 0.5 * self.p_w[g]).mean()) for g in skup])
        if self.K.je_deska:
            pop = [f"y={v:.2f}" for v in yc]
        else:
            pop = [f"N{k + 1}" for k in range(len(skup))]
        return Vystupy(
            S=S, skup=skup, faktor=fak,
            i0=np.array([self.p_i0[g].min() for g in skup]),
            i1=np.array([self.p_i1[g].max() for g in skup]),
            skoky=[np.unique(self.p_sup[g].ravel()) for g in skup],
            x0=np.array([self.p_x0[g].mean() for g in skup]),
            y=yc, popisky=pop, deska=self.K.je_deska, sirka_okna=sirka,
            skoky_vse=np.unique(self.p_sup.ravel()))

    # ---- zatížení -----------------------------------------------------
    def zatizeni(self, platky: List[Platek]) -> np.ndarray:
        """Konzistentní uzlové síly od rovnoměrně zatížených obdélníků.
        Příčně se ploška ořízne na šířku mostovky (síla zůstává), podélně se
        část mimo pruh (za jeho podporou) nezapočítává (jde do opěry)."""
        f = np.zeros(self.ndof)
        B = self.B
        xmin, xmax = self.xs[0], self.xs[-1]
        c_min = float(self.p_c.min())
        ns = self.n_pruhu
        for F, x0, x1, y0, y1 in platky:
            if x1 <= x0 or y1 <= y0 or F == 0:
                continue
            x0c, x1c = max(xmin, x0), min(xmax, x1)
            if x1c <= x0c:
                continue
            Fe = F * (x1c - x0c) / (x1 - x0)
            y0c, y1c = max(0.0, y0), min(B, y1)
            if y1c <= y0c:
                continue
            nsx = max(6, int(math.ceil((x1c - x0c) / self.a_ref * 6)))
            nsy = max(6, int(math.ceil((y1c - y0c) / c_min * 6)))
            xs_ = x0c + (np.arange(nsx) + 0.5) * (x1c - x0c) / nsx
            ys_ = y0c + (np.arange(nsy) + 0.5) * (y1c - y0c) / nsy
            X, Y = np.meshgrid(xs_, ys_, indexing="ij"); X = X.ravel(); Y = Y.ravel()
            Fp = Fe / X.size
            st = np.clip(np.searchsorted(self.p_y0, Y, side="right") - 1, 0, ns - 1)
            uvnitr = ((X >= self.xs[self.p_i0[st]] - 1e-12) &
                      (X <= self.xs[self.p_i1[st]] + 1e-12))
            if not uvnitr.all():
                X, Y, st = X[uvnitr], Y[uvnitr], st[uvnitr]
                if X.size == 0:
                    continue
            yl = Y - self.p_y0[st]
            c = self.p_c[st]
            iy = np.minimum((yl // c).astype(int), self.p_ney[st] - 1)
            ix = np.clip(np.searchsorted(self.xs, X, side="right") - 1,
                         self.p_i0[st], self.p_i1[st] - 1)
            xi = 2 * (X - self.xs[ix]) / self.a_el[ix] - 1
            et = 2 * (yl - iy * c) / c - 1
            Nn = 0.25 * np.stack([(1 - xi) * (1 - et), (1 + xi) * (1 - et),
                                  (1 + xi) * (1 + et), (1 - xi) * (1 + et)], axis=1)
            e = self.p_off[st] + iy * self.p_nex[st] + (ix - self.p_i0[st])
            np.add.at(f, self.E_dofs[e][:, 0::3].ravel(), (Fp * Nn).ravel())
        return f

    # ---- řešení a výslednice pruhů ------------------------------------
    def res(self, f: np.ndarray) -> np.ndarray:
        return self.T @ self._lu.solve(self.T.T @ f)

    def res_batch(self, F: np.ndarray) -> np.ndarray:
        return self.T @ self._lu.solve(np.ascontiguousarray(self.T.T @ F))

    def vyslednice(self, u: np.ndarray, surove: bool = False):
        """
        M, V(x⁻), V(x⁺) všech pruhů (n_pruhu, nx) [nebo (n_pruhu, nx, nb) pro
        matici posunů].  surove=False: na čele pruhu V(x⁻) := V(x⁺) a na konci
        V(x⁺) := V(x⁻) (hodnoty „uvnitř“ pruhu); surove=True: bez úpravy
        (V(x⁻) na čele = 0, pro kontrolu rovnováhy).
        """
        ns, nx = self.n_pruhu, self.nx
        shp = (ns, nx) + (() if u.ndim == 1 else (u.shape[1],))
        M = (self.R_M @ u).reshape(shp)
        Vm = (self.R_Vm @ u).reshape(shp)
        Vp = (self.R_Vp @ u).reshape(shp)
        if self.K.vetknuti and not surove:
            # vetknutí: nad podporou skok M → v uzlu podpory strana s větší |M|
            Mp = (self.R_Mp @ u).reshape(shp)
            si = np.repeat(np.arange(ns), self.p_sup.shape[1])
            ki = self.p_sup.ravel()
            a, b = M[si, ki], Mp[si, ki]
            M[si, ki] = np.where(np.abs(b) > np.abs(a), b, a)
        if not surove:
            s = np.arange(ns)
            Vm[s, self.p_i0] = Vp[s, self.p_i0]
            Vp[s, self.p_i1] = Vm[s, self.p_i1]
        return M, Vm, Vp

    def vysledky(self, f: np.ndarray):
        u = self.res(f)
        M, Vm, Vp = self.vyslednice(u)
        return M, Vm, Vp, u

    def reakce_uzlu(self, f: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Reakce (vzhůru kladně) v jednotlivých podepřených uzlech
        (u pružného uložení = síla v pružině k·w)."""
        if self.k_uzlu is not None:
            # pružné uložení: reakce = síla v pružině k·w (v9: u tvrdého uložení
            # se vazba β_s = ∂w/∂s projeví jen samorovnovážnými silovými dvojicemi
            # podél linie podpory – nejsou to síly do ložisek)
            k_ = self.k_uzlu if u.ndim == 1 else self.k_uzlu[:, None]
            return k_ * u[self.reac_dof]
        return (f - self.Kfull @ u)[self.reac_dof]

    def reakce_rot(self, f: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Momentové reakce vetknutí (na βx podepřených uzlů)."""
        if not len(self.reac_rot_dof):
            return np.zeros(0)
        return (f - self.Kfull @ u)[self.reac_rot_dof]

    def reakce(self, f: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Celkové reakce jednotlivých podpor (osy podpor 1 … n+1)."""
        r = self.reakce_uzlu(f, u)
        return np.bincount(self.reac_j, weights=r, minlength=self.K.n_poli + 1)


# ---------------------------------------------------------------------------
# Převod náprav na plošky kol
# ---------------------------------------------------------------------------

def platky_z_naprav(axles: List[Axle], y1: float, y2: float, b_k: float,
                    roz: float = 0.0) -> List[Platek]:
    out = []
    for q, s, e in axles:
        F = q * (e - s)
        if F == 0:
            continue
        stopy = (y1,) if abs(y1 - y2) < 1e-9 else (y1, y2)
        for yc in stopy:
            out.append((F / len(stopy), s - roz / 2, e + roz / 2,
                        yc - (b_k + roz) / 2, yc + (b_k + roz) / 2))
    return out




@dataclass
class SitMKP:
    """Geometrie sítě MKP pro vykreslení (půdorys, globální souřadnice 2D)."""
    X: np.ndarray            # (n_uzlu,) x uzlů [m]
    Y: np.ndarray            # (n_uzlu,) y uzlů [m]
    prvky: np.ndarray        # (n_prvku, 4) indexy uzlů (proti směru hod. ručiček)
    typ: np.ndarray          # (n_prvku,) "n" nosník, "s" spára, "d" deska
    podpory: np.ndarray      # indexy podepřených uzlů
    k_uzlu: Optional[np.ndarray]   # tuhost pružin v uzlech podpor [kN/m] (None = tuhé)
    klouby: List[Tuple[float, float, float]]   # (y, x_od, x_do) podélné klouby
    n_dof: int
    a: float                 # typická délka prvku [m]
    c: float                 # typická šířka prvku [m]
    kappa: float = 5.0 / 6.0


def sit_modelu(model) -> SitMKP:
    """Sestaví geometrii sítě z modelu DeskaMKP nebo DeskaSikmaMKP."""
    nx, ng = model.nx, model._ng
    k = np.tile(np.arange(nx), ng)
    g = np.repeat(np.arange(ng), nx)
    prvky = model.E_dofs[:, [0, 3, 6, 9]].astype(int)      # w-dofy = indexy uzlů
    klouby = []
    if getattr(model, "je_deska_model", False):            # šikmá / kolmá deska
        X = model.xs[k] + model.x0g[g]
        Y = model.yg[g]
        typ = np.full(len(prvky), "d")
    else:
        yl = np.zeros(ng)
        for s_ in range(model.n_pruhu):
            jl = np.arange(model.p_ney[s_] + 1)
            yl[model.p_g0[s_] + jl] = model.p_y0[s_] + jl * model.p_c[s_]
        X, Y = model.xs[k], yl[g]
        typ = model.p_typ[model.e_strip]
        if model.spoj != "deska":
            for s_ in range(1, model.n_pruhu):
                x_od = max(model.xs[model.p_i0[s_ - 1]], model.xs[model.p_i0[s_]])
                x_do = min(model.xs[model.p_i1[s_ - 1]], model.xs[model.p_i1[s_]])
                klouby.append((float(model.p_y0[s_]), float(x_od), float(x_do)))
    return SitMKP(X=X, Y=Y, prvky=prvky, typ=typ,
                  podpory=np.asarray(model.reac_dof, dtype=int),
                  k_uzlu=None if model.k_uzlu is None else np.asarray(model.k_uzlu),
                  klouby=klouby, n_dof=int(model.ndof),
                  a=float(model.a_ref), c=float(model.c), kappa=KAPPA)


def posun(axles: List[Axle], dx: float) -> List[Axle]:
    """Posun zatížení v podélném směru (z rámce 1D do globálního rámce 2D)."""
    if dx == 0.0:
        return list(axles)
    return [(q, s + dx, e + dx) for q, s, e in axles]


# ---------------------------------------------------------------------------
# Stav a vyhodnocení kontrolních řezů
# ---------------------------------------------------------------------------

@dataclass
class StavMKP:
    xs: np.ndarray
    M: np.ndarray            # (n_out, nx) – výstupy (nosníky / pásy 1 m)
    Vm: np.ndarray
    Vp: np.ndarray
    dM: float                # odchylka Σ pruhů od statiky [%]
    dV: float
    R: np.ndarray            # reakce podpor [kN]
    M1D: np.ndarray
    V1D: np.ndarray
    P_M: np.ndarray          # (n_pruhu, nx) – všechny pruhy
    P_Vm: np.ndarray
    P_Vp: np.ndarray
    vyst: Vystupy
    p_xsup: np.ndarray       # (n_pruhu, n+1) polohy podpor pruhů
    i_spar: np.ndarray

    @property
    def Ms(self):
        return self.P_M[self.i_spar] if len(self.i_spar) else None

    @property
    def Vms(self):
        return self.P_Vm[self.i_spar] if len(self.i_spar) else None

    @property
    def Vps(self):
        return self.P_Vp[self.i_spar] if len(self.i_spar) else None

    def suma(self):
        """Σ všech pruhů (nosníky + spáry / všechny pruhy desky)."""
        return self.P_M.sum(axis=0), self.P_Vm.sum(axis=0), self.P_Vp.sum(axis=0)


def _reference(model: DeskaMKP, f: np.ndarray, r: np.ndarray, rr=None):
    """Statika celé konstrukce (řez kolmý k ose) z uzlových sil a reakcí
    jednotlivých podepřených uzlů – platí i pro šikmé uložení.
    rr: momentové reakce vetknutí (na βx podepřených uzlů), v9."""
    nx, xs = model.nx, model.xs
    Fk = f[: model._nw].reshape(model._ng, nx).sum(axis=0)
    xr = model.reac_x
    M1 = np.zeros(nx); V1 = np.zeros(nx)
    cum = np.concatenate([[0.0], np.cumsum(Fk)])
    xrr = getattr(model, "reac_rot_x", np.zeros(0))
    for k in range(nx):
        left = xr < xs[k] - EPS
        V1[k] = r[left].sum() - cum[k]
        M1[k] = (r[left] * (xs[k] - xr[left])).sum() - np.sum(Fk[:k] * (xs[k] - xs[:k]))
        if rr is not None and len(rr):
            M1[k] += ROT_ZNAM * rr[xrr < xs[k] - EPS].sum()
    V1[0] = r[xr <= xs[0] + EPS].sum()
    return M1, V1


def reseni_stavu(model: DeskaMKP, axles: List[Axle], y1: float, y2: float,
                 b_k: float, roz: float, dx: float = 0.0) -> StavMKP:
    """Jeden zatěžovací stav; axles v rámci 1D, dx = posun do rámce 2D."""
    f = model.zatizeni(platky_z_naprav(posun(axles, dx), y1, y2, b_k, roz))
    u = model.res(f)
    Mr, Vmr, _ = model.vyslednice(u, surove=True)
    r = model.reakce_uzlu(f, u)
    rr = model.reakce_rot(f, u) if model.K.vetknuti else None
    if getattr(model, "je_deska_model", False) and model.K.sikmy:
        # šikmá deska: výsledky podél čar rovnoběžných s osou podpor – statika
        # na kolmém řezu se takto neověří
        M1 = np.full(model.nx, np.nan); V1 = np.full(model.nx, np.nan)
        dM = dV = float("nan")
    else:
        M1, V1 = _reference(model, f, r, rr)
        sM = Mr.sum(axis=0)
        okm = np.ones(model.nx, bool)
        if model.K.vetknuti:
            # nad vetknutou podporou je skok M – porovnává se mimo uzly podpor
            okm[np.unique(np.argmin(np.abs(model.xs[None, :] - model.reac_x[:, None]),
                                    axis=1))] = False
        dM = 100.0 * np.abs(sM - M1)[okm].max() / max(np.abs(M1).max(), 1e-9)
        sV = Vmr.sum(axis=0)
        dV = 100.0 * np.abs(sV[1:] - V1[1:]).max() / max(np.abs(V1[1:]).max(), 1e-9)
    PM, PVm, PVp = model.vyslednice(u)
    S = model.vyst.S
    return StavMKP(model.xs, S @ PM, S @ PVm, S @ PVp, dM, dV,
                   np.bincount(model.reac_j, weights=r, minlength=model.K.n_poli + 1),
                   M1, V1, PM, PVm, PVp, model.vyst, model.p_xsup, model.i_spar)


def _V_bod(xs, Vm, Vp, x: float, strana: str, na_podpore: bool) -> float:
    """V jednoho pruhu v bodě x; mezi uzly lineární interpolace uvnitř prvku."""
    kk = int(np.argmin(np.abs(xs - x)))
    if abs(xs[kk] - x) <= 1e-9:
        # řez v uzlové čáře: d = 0 → strana pole (P: x⁺, L: x⁻);
        # d > 0 → strana k podpoře (P: x⁻, L: x⁺), tj. V zahrnuje i zatížení
        # soustředěné do uzlové čáry řezu (zatížení sahající až k řezu)
        if na_podpore:
            return Vp[kk] if strana == "P" else Vm[kk]
        return Vm[kk] if strana == "P" else Vp[kk]
    e = int(np.searchsorted(xs, x) - 1)
    e = min(max(e, 0), len(xs) - 2)
    t = (x - xs[e]) / (xs[e + 1] - xs[e])
    return Vp[e] * (1 - t) + Vm[e + 1] * t


def hodnoty_rezu(st: StavMKP, rez: Rez, d: float = 0.0):
    """
    Hodnoty v kontrolním řezu pro každý výstup (nosník / pás 1 m).
    Řez každého pruhu se bere vůči JEHO podpoře (šikmý most).

    Returns:
        hodnoty (n_out,)  kladná čísla
        x_lok             poloha řezu rozhodujícího výstupu vůči jeho čelu [m]
        x_glob            poloha řezu rozhodujícího výstupu v rámci 2D [m]
    """
    xs = st.xs
    V = st.vyst
    n = V.n
    val = np.zeros(n)
    xg = np.zeros(n)
    if rez.typ in ("M+", "M-"):
        if rez.typ == "M+":
            j0, j1 = rez.pole, rez.pole + 1
        else:
            j0 = j1 = rez.podpora
        for o, g in enumerate(V.skup):
            lo = st.p_xsup[g, j0].min() - EPS
            hi = st.p_xsup[g, j1].max() + EPS
            mask = (xs >= lo) & (xs <= hi)
            if not mask.any():
                mask[int(np.argmin(np.abs(xs - 0.5 * (lo + hi))))] = True
            Mi = st.M[o, mask] if rez.typ == "M+" else -st.M[o, mask]
            k = int(np.argmax(Mi))
            val[o], xg[o] = Mi[k], xs[mask][k]
    else:
        k = rez.podpora
        znam = -1.0 if rez.strana == "L" else 1.0
        for o, g in enumerate(V.skup):
            tot, xx = 0.0, []
            for s in g:
                x = st.p_xsup[s, k] + znam * d
                tot += _V_bod(xs, st.P_Vm[s], st.P_Vp[s], x, rez.strana, rez.na_podpore)
                xx.append(x)
            val[o] = abs(V.faktor[o] * tot)
            xg[o] = float(np.mean(xx))
    ib = int(np.argmax(val))
    return val, float(xg[ib] - V.x0[ib]), float(xg[ib])


# ---------------------------------------------------------------------------
# Obálky na jednotlivých výstupech (pojezd vozidla po 2D desce)
# ---------------------------------------------------------------------------

@dataclass
class Obalky2D:
    xs: np.ndarray
    M_max: np.ndarray        # (n_out, nx)
    M_min: np.ndarray
    Vm_max: np.ndarray       # V(x⁻)
    Vm_min: np.ndarray
    Vp_max: np.ndarray       # V(x⁺)
    Vp_min: np.ndarray
    Vs_max: Optional[np.ndarray] = None   # ½(V(x⁻)+V(x⁺)) – hladký průběh pro graf
    Vs_min: Optional[np.ndarray] = None
    n_stavu: int = 0
    vyst: Optional[Vystupy] = None


def obalky_2D(model: DeskaMKP, stavy, y1: float, y2: float, b_k: float,
              roz: float, dx: float = 0.0, davka: int = 48) -> Obalky2D:
    """
    Obálky M(x), V(x) na každém výstupu přes zadané polohy vozidla.

    stavy: iterovatelné dvojice (axles, axles_rozsirene) v rámci 1D — použijí
           se původní nápravy posunuté o dx, roznos dělá platky_z_naprav.
    Soustava se řeší po dávkách (jedna LU faktorizace, více pravých stran).
    """
    V = model.vyst
    n, nx = V.n, model.nx
    inf = np.inf
    ob = Obalky2D(model.xs, *[np.full((n, nx), v) for v in (-inf, inf) * 4],
                  vyst=V)
    S = V.S

    def zpracuj(F):
        U = model.res_batch(F)
        PM, PVm, PVp = model.vyslednice(U)
        M = np.einsum("os,sxb->oxb", S, PM)
        Vm = np.einsum("os,sxb->oxb", S, PVm)
        Vp = np.einsum("os,sxb->oxb", S, PVp)
        Vs = 0.5 * (Vm + Vp)
        for a_max, a_min, A in ((ob.M_max, ob.M_min, M), (ob.Vm_max, ob.Vm_min, Vm),
                                (ob.Vp_max, ob.Vp_min, Vp), (ob.Vs_max, ob.Vs_min, Vs)):
            np.maximum(a_max, A.max(axis=2), out=a_max)
            np.minimum(a_min, A.min(axis=2), out=a_min)
        ob.n_stavu += F.shape[1]

    buf = []
    for ax0, _ in stavy:
        f = model.zatizeni(platky_z_naprav(posun(ax0, dx), y1, y2, b_k, roz))
        if not np.any(f):
            continue
        buf.append(f)
        if len(buf) >= davka:
            zpracuj(np.stack(buf, axis=1)); buf = []
    if buf:
        zpracuj(np.stack(buf, axis=1))
    for a in (ob.M_max, ob.M_min, ob.Vm_max, ob.Vm_min, ob.Vp_max, ob.Vp_min,
              ob.Vs_max, ob.Vs_min):
        a[~np.isfinite(a)] = 0.0
    return ob
