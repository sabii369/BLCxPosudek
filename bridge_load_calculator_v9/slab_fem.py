"""
slab_fem.py  (v9)
=================
Deska ("deska") – 2D MKP s KOSOÚHLOU sítí rovnoběžnou se šikmou osou podpor.

Deska šířky b (= B) a tloušťky h přes n polí, liniové kloubové podpory
přesně podél šikmých os podpor (obr. 2).  Síť: podélné uzlové čáry y_g
(rozteč c ≈ ex) a „příčné“ uzlové čáry rovnoběžné s osou podpor
      x = ξ_k + x0(y),   x0(y) = −s·(y − B/2)·cot(180° − alfa),
takže prvky jsou rovnoběžníky a podpory leží přesně v uzlech ξ = x_podpory.
Prvek: MITC4 (Bathe–Dvorkin) pro obecný čtyřúhelník.

Uložení (v9, K.uloz; s = směr osy podpory, n = normála k ní v půdorysu):
  tvrdé    w = 0 (pružina k_v) a natočení podél osy podpory β_s = 0; u pružné
           podpory konzistentně β_s = ∂w/∂s (podpora se natáčí s průhybem –
           v8 měla β_s = 0 i s pružinami → parazitní smyk κGh·∂w/∂s u tupých rohů),
  měkké    jen w; β_s i β_n volné (liniová podpora s volnými rotacemi),
  vetknutí navíc β_n = 0 (natočení kolem osy podpory), s k_rot rotační
           pružina k_rot·ℓ na β_n (ℓ = skutečná délka podpory příslušná uzlu).
  K.beta_s_pevne = True: β_s = 0 i u pružné podpory (chování v8, pro srovnání).
Vazby se zavádějí transformací stupňů volnosti u = T·u_r.

Vnitřní síly VŽDY ve směru osy prvku (x): m_x = D(κx + ν κy), v_x = kGh γx,
vyhodnocené v rozích prvků a zprůměrované do uzlů (zvlášť z prvků vlevo a
vpravo od uzlové čáry → skok nad podporou zůstane zachován).  Hodnoty pásu
šířky 1 m = integrál přes šířku pásu podél čáry ξ = konst., tj. podél čáry
rovnoběžné s osou podpory (u kolmé desky řez kolmý k ose).  Vodorovná osa
výsledků je proto ξ – vzdálenost od osy podpory měřená ve směru osy prvku.
"""

from __future__ import annotations
import math
from typing import List

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .geometry import Konstrukce
from .plate_fem import Vystupy, Platek, KAPPA

_XN = np.array([-1, 1, 1, -1.])
_EN = np.array([-1, -1, 1, 1.])
_G = 1 / math.sqrt(3)
_GP = [(-_G, -_G), (_G, -_G), (_G, _G), (-_G, _G)]
_ROHY = [(-1., -1.), (1., -1.), (1., 1.), (-1., 1.)]


def _N(x, e):
    return 0.25 * (1 + x * _XN) * (1 + e * _EN)


def _dNnat(x, e):
    return 0.25 * _XN * (1 + e * _EN), 0.25 * _EN * (1 + x * _XN)


def _J(X, Y, x, e):
    dxi, deta = _dNnat(x, e)
    return np.array([[dxi @ X, dxi @ Y], [deta @ X, deta @ Y]]), dxi, deta


def _Bb(X, Y, x, e):
    J, dxi, deta = _J(X, Y, x, e)
    Ji = np.linalg.inv(J)
    dNx = Ji[0, 0] * dxi + Ji[0, 1] * deta
    dNy = Ji[1, 0] * dxi + Ji[1, 1] * deta
    B = np.zeros((3, 12))
    B[0, 1::3] = dNx
    B[1, 2::3] = dNy
    B[2, 1::3] = dNy; B[2, 2::3] = dNx
    return B, np.linalg.det(J), Ji


def _kov(X, Y, x, e):
    """Řádky kovariantních smykových přetvoření γ_ξ, γ_η v bodě (x, e)."""
    J, dxi, deta = _J(X, Y, x, e)
    n = _N(x, e)
    rx = np.zeros(12); re = np.zeros(12)
    rx[0::3] = dxi; rx[1::3] = -n * J[0, 0]; rx[2::3] = -n * J[0, 1]
    re[0::3] = deta; re[1::3] = -n * J[1, 0]; re[2::3] = -n * J[1, 1]
    return rx, re


def _Bs(X, Y, x, e, tie):
    rA, rC, rD, rB = tie
    g_xi = 0.5 * (1 - e) * rA + 0.5 * (1 + e) * rC
    g_eta = 0.5 * (1 - x) * rD + 0.5 * (1 + x) * rB
    J, _, _ = _J(X, Y, x, e)
    return np.linalg.inv(J) @ np.vstack([g_xi, g_eta]), np.linalg.det(J)


def _tie(X, Y):
    rA = _kov(X, Y, 0.0, -1.0)[0]
    rC = _kov(X, Y, 0.0, 1.0)[0]
    rD = _kov(X, Y, -1.0, 0.0)[1]
    rB = _kov(X, Y, 1.0, 0.0)[1]
    return rA, rC, rD, rB


def ke_mitc4_quad(X, Y, D: float, nu: float, kGh: float) -> np.ndarray:
    """MITC4 pro obecný čtyřúhelník (uzly v pořadí (−1,−1),(1,−1),(1,1),(−1,1))."""
    X = np.asarray(X, float); Y = np.asarray(Y, float)
    Db = D * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])
    tie = _tie(X, Y)
    K = np.zeros((12, 12))
    for x, e in _GP:
        B, dJ, _ = _Bb(X, Y, x, e)
        K += B.T @ Db @ B * dJ
        Bs, dJ = _Bs(X, Y, x, e, tie)
        K += Bs.T @ Bs * kGh * dJ
    return K


def rohove_operatory(X, Y, D: float, nu: float, kGh: float):
    """Operátory m_x a v_x v rozích prvku: (4, 12) každý."""
    X = np.asarray(X, float); Y = np.asarray(Y, float)
    tie = _tie(X, Y)
    Om = np.zeros((4, 12)); Ov = np.zeros((4, 12))
    for i, (x, e) in enumerate(_ROHY):
        B, _, _ = _Bb(X, Y, x, e)
        Om[i] = -D * (B[0] + nu * B[1])        # kladný = tah dole (jako u nosníků)
        Bs, _ = _Bs(X, Y, x, e, tie)
        Ov[i] = kGh * Bs[0]
    return Om, Ov


class DeskaSikmaMKP:
    """Model desky (kolmé i šikmé) s rozhraním kompatibilním s DeskaMKP."""

    je_deska_model = True

    def __init__(self, K: Konstrukce, ex: float = 0.125, **_):
        if not K.je_deska:
            raise ValueError("DeskaSikmaMKP je jen pro typ konstrukce 'deska'.")
        self.K = K
        self.L = K.Ltot
        self.B = B = K.B
        self.N = 1
        self.b, self.h = K.b, K.h
        self.spoj = "deska"
        self.ex = ex
        nu = K.nu
        E = K.E * 1000.0
        G = E / (2 * (1 + nu))
        D = E * K.h ** 3 / (12 * (1 - nu ** 2))
        kGh = KAPPA * G * K.h      # Mindlin: smyková tuhost κ·G·h, κ = 5/6
        self.sikmy = K.sikmy
        sgn = 1.0 if K.sikmost == "prava" else -1.0
        self.lam = sgn * K.cot                 # βy = lam·βx na podpoře

        # ---- síť: podélné čáry (y) a čáry rovnoběžné s osou podpor (ξ) --------
        m = max(1, int(math.ceil(1.0 / ex - 1e-9)))
        nr = max(1, int(round(B * m)))
        c = B / nr
        self.yg = np.arange(nr + 1) * c
        self.x0g = np.array([K.x0(y) for y in self.yg])
        xp = np.array(K.x_podpor)
        xs = [xp[0]]
        for a, b in zip(xp[:-1], xp[1:]):
            ne = max(2, int(round((b - a) / ex)))
            if len(xp) == 2:
                ne = max(8, ne)
            xs.extend(list(a + (b - a) * np.arange(1, ne + 1) / ne))
        self.xs = np.array(xs)                 # ξ – od osy podpory ve směru osy
        self.nx = nx = len(self.xs)
        self.nex = nx - 1
        self.a_el = np.diff(self.xs)
        self.a_min = float(self.a_el.min())
        self.a_ref = self.a_min
        self.c = c
        self.ney = 1
        self.k_sup = np.array([int(np.argmin(np.abs(self.xs - v))) for v in xp])
        ng = nr + 1
        self._ng = ng
        self._nw = nw = ng * nx
        self.ndof = 3 * nw
        self.n_pruhu = nr
        self.p_y0 = self.yg[:-1].copy()
        self.p_w = np.full(nr, c)
        self.p_c = self.p_w.copy()
        self.p_typ = np.array(["d"] * nr)
        self.p_ney = np.ones(nr, int)
        self.p_i0 = np.zeros(nr, int)
        self.p_i1 = np.full(nr, nx - 1)
        self.p_sup = np.tile(self.k_sup, (nr, 1))
        self.p_xsup = self.xs[self.p_sup]
        self.p_x0 = np.zeros(nr)
        self.i_nos = np.arange(nr)
        self.i_spar = np.zeros(0, int)

        # ---- prvky (rovnoběžníky; v řadě stejné, cache podle délky) -----------
        dx0 = self.x0g[1] - self.x0g[0] if nr >= 1 else 0.0
        jj, kk = np.meshgrid(np.arange(nr), np.arange(self.nex), indexing="ij")
        jj, kk = jj.ravel(), kk.ravel()
        cols = []
        for dg, dk in ((0, 0), (0, 1), (1, 1), (1, 0)):
            g = jj + dg; k = kk + dk
            n = g * nx + k
            cols += [n, nw + n, 2 * nw + n]
        self.E_dofs = np.stack(cols, axis=1)
        self.e_row, self.e_ix = jj, kk
        tab, idx, Om_t, Ov_t = [], {}, [], []
        e_ke = np.zeros(len(jj), int)
        for i, a in enumerate(self.a_el):
            key = round(float(a), 9)
            if key not in idx:
                X = np.array([0.0, a, a + dx0, dx0])
                Y = np.array([0.0, 0.0, c, c])
                idx[key] = len(tab)
                tab.append(ke_mitc4_quad(X, Y, D, nu, kGh))
                Om, Ov = rohove_operatory(X, Y, D, nu, kGh)
                Om_t.append(Om); Ov_t.append(Ov)
            e_ke[kk == i] = idx[key]
        self.e_ke = e_ke
        Kt = np.array(tab)[e_ke]
        ne = len(jj)
        rr = np.repeat(self.E_dofs, 12, axis=1).ravel()
        cc = np.tile(self.E_dofs, (1, 12)).ravel()
        self.Kfull = sp.csr_matrix((Kt.reshape(ne, 144).ravel(), (rr, cc)),
                                   shape=(self.ndof, self.ndof))
        del Kt

        # ---- výslednice: m_x, v_x v uzlech (průměr z prvků vlevo / vpravo) -----
        Om_t = np.array(Om_t); Ov_t = np.array(Ov_t)
        uz = [(jj, kk), (jj, kk + 1), (jj + 1, kk + 1), (jj + 1, kk)]
        strana = [1, 0, 0, 1]      # roh 0,3 leží na čáře k (prvek je VPRAVO), 1,2 na k+1 (VLEVO)
        mats = {}
        for nazev, Ot in (("m", Om_t), ("v", Ov_t)):
            for sid in (0, 1):     # 0 = z prvků vlevo (x⁻), 1 = z prvků vpravo (x⁺)
                rows, colsm, data = [], [], []
                for r_, (g, k) in enumerate(uz):
                    if strana[r_] != sid:
                        continue
                    node = g * nx + k
                    rows.append(np.repeat(node, 12))
                    colsm.append(self.E_dofs.ravel())
                    data.append(Ot[e_ke, r_, :].ravel())
                rows = np.concatenate(rows); colsm = np.concatenate(colsm)
                data = np.concatenate(data)
                A = sp.csr_matrix((data, (rows, colsm)), shape=(nw, self.ndof))
                # počet příspěvků v uzlu (1 nebo 2 prvky)
                cnt = np.zeros(nw)
                for r_, (g, k) in enumerate(uz):
                    if strana[r_] == sid:
                        np.add.at(cnt, g * nx + k, 1.0)
                with np.errstate(divide="ignore"):
                    wgt = np.where(cnt > 0, 1.0 / np.maximum(cnt, 1), 0.0)
                mats[(nazev, sid)] = sp.diags(wgt) @ A
        # uzly bez prvku na dané straně (ξ = 0 zleva, ξ = L zprava) → druhá strana
        for nazev in ("m", "v"):
            L_, P_ = mats[(nazev, 0)].tolil(), mats[(nazev, 1)].tolil()
            for g in range(ng):
                n0, n1 = g * nx, g * nx + nx - 1
                L_[n0] = P_[n0]
                P_[n1] = L_[n1]
            mats[(nazev, 0)], mats[(nazev, 1)] = L_.tocsr(), P_.tocsr()
        # integrace přes řadu prvků (lichoběžník v y): řada j = čáry j, j+1
        rows = np.concatenate([np.arange(nr * nx)] * 2)
        colsr = np.concatenate([(np.arange(nr)[:, None] * nx + np.arange(nx)[None, :]).ravel(),
                                ((np.arange(nr)[:, None] + 1) * nx + np.arange(nx)[None, :]).ravel()])
        Srow = sp.csr_matrix((np.full(len(rows), 0.5 * c), (rows, colsr)), shape=(nr * nx, nw))
        Mn = (0.5 * (mats[("m", 0)] + mats[("m", 1)])).tolil()
        for g in range(ng):                  # kloubové konce desky: m_x = 0
            Mn[g * nx] = 0
            Mn[g * nx + nx - 1] = 0
        self.R_M = Srow @ Mn.tocsr()
        # v9: m_x v uzlu podpory = lineární extrapolace z vnitřních uzlů pole
        # (zvlášť zleva a zprava).  Uzlová hodnota z rohů prvků jen z jedné strany
        # konverguje pomalu (O(h): při prvku 0,25 m o ~3–4 % menší |M| nad podporou),
        # extrapolace ze dvou sousedních (oboustranně průměrovaných) uzlů ~O(h²).
        # Kloub: konce M = 0, vnitřní podpora průměr obou stran; vetknutí: skok →
        # obě strany zvlášť (R_Mm, R_Mp), ve vyslednice() strana s větší |M|.
        R = self.R_M.tolil()
        nr_ = nr
        Rm = sp.lil_matrix(R.shape); Rp = sp.lil_matrix(R.shape)
        Rc = self.R_M.tocsr()
        for k in self.k_sup:
            for j in range(nr_):
                row = j * nx + k
                for side, Rs in ((-1, Rm), (1, Rp)):
                    k1, k2 = k + side, k + 2 * side
                    if 0 <= k2 < nx and k1 not in self.k_sup and 0 < k1 < nx - 1:
                        t = (xs_ := self.xs)[k] - xs_[k1]
                        t /= (xs_[k1] - xs_[k2])
                        Rs[row] = Rc[j * nx + k1] * (1 + t) - Rc[j * nx + k2] * t
                    else:
                        Rs[row] = Rc[row]
        self.R_Mm, self.R_Mp = Rm.tocsr(), Rp.tocsr()
        konce = (self.k_sup[0], self.k_sup[-1])
        for k in self.k_sup:
            for j in range(nr_):
                row = j * nx + k
                if k in konce:
                    R[row] = (self.R_Mp[row] if k == konce[0] else self.R_Mm[row]) \
                        if K.vetknuti else 0
                else:
                    R[row] = 0.5 * (self.R_Mm[row] + self.R_Mp[row])
        self.R_M = R.tocsr()
        self.R_Vm = Srow @ mats[("v", 0)]
        self.R_Vp = Srow @ mats[("v", 1)]

        # ---- podepření a vazby (v9: tvrdé / měkké / vetknutí) -------------------
        lam = self.lam
        sq = math.sqrt(1.0 + lam * lam)            # délka osy podpory na 1 m v y
        fix = []
        dep = {}                                  # závislý dof → [(řídicí dof, koef.)]
        reac, reac_j, rot = [], [], []
        kd = np.zeros(self.ndof)
        krot = []                                 # (βx, βy, ℓ) rotační pružiny vetknutí
        for j, k in enumerate(self.k_sup):
            for g in range(ng):
                n = g * nx + k
                ty = 0.5 * c if g in (0, ng - 1) else c
                if K.pruzna:
                    kd[n] += K.k_pod * ty
                else:
                    fix.append(n)
                reac.append(n); reac_j.append(j)
                bx, by = nw + n, 2 * nw + n
                if K.uloz == "mekke":
                    continue
                # ∂w/∂y podél osy podpory (jen u pružné podpory, jinak w = 0)
                gw = []
                if K.beta_s_sleduje and ng > 1:
                    if g == 0:
                        gw = [(n + nx, 1 / c), (n, -1 / c)]
                    elif g == ng - 1:
                        gw = [(n, 1 / c), (n - nx, -1 / c)]
                    else:
                        gw = [(n + nx, 0.5 / c), (n - nx, -0.5 / c)]
                if K.vetknuti and not K.k_rot:
                    # β_s = ∂w/∂s a β_n = 0:  βx = −λ·g/(1+λ²), βy = g/(1+λ²)
                    rot.append(bx)
                    if gw:
                        dep[bx] = [(d_, -lam * cf / sq ** 2) for d_, cf in gw] if lam else []
                        dep[by] = [(d_, cf / sq ** 2) for d_, cf in gw]
                    else:
                        fix += [bx, by]
                    continue
                # β_s = ∂w/∂s:  βy = λ·βx + ∂w/∂y
                if not gw and abs(lam) < 1e-14:
                    fix.append(by)                # kolmá tuhá podpora: βy = 0
                else:
                    dep[by] = ([(bx, lam)] if lam else []) + gw
                if K.vetknuti:                    # pružné vetknutí: k_rot·ℓ na β_n
                    rot.append(bx)
                    krot.append((bx, by, ty * sq))
        self.reac_dof = np.array(reac, dtype=int)
        self.reac_x = self.xs[self.reac_dof % nx]
        self.reac_j = np.array(reac_j, dtype=int)
        self.reac_rot_dof = np.array(rot, dtype=int)
        self.reac_rot_x = self.xs[(self.reac_rot_dof - nw) % nx] if rot else np.zeros(0)
        fixed = np.zeros(self.ndof, bool); fixed[fix] = True
        depm = np.zeros(self.ndof, bool)
        for d_ in dep:
            depm[d_] = True
        nez = np.where(~fixed & ~depm)[0]
        col_of = -np.ones(self.ndof, int); col_of[nez] = np.arange(len(nez))
        ri = list(nez); ci = list(range(len(nez))); vi = [1.0] * len(nez)
        for d_, lst in dep.items():
            for m_, cf in lst:
                if col_of[m_] >= 0 and cf != 0.0:
                    ri.append(d_); ci.append(col_of[m_]); vi.append(cf)
        self.T = sp.csr_matrix((vi, (ri, ci)), shape=(self.ndof, len(nez)))
        Ks = self.Kfull + sp.diags(kd) if K.pruzna else self.Kfull
        if krot:
            # β_n = (βx + λ·βy)/√(1+λ²) → k·ℓ·n nᵀ na (βx, βy)
            rr_, cc_, vv_ = [], [], []
            nv = np.array([1.0, lam]) / sq
            for bx, by, ell in krot:
                kk = K.k_rot * ell * np.outer(nv, nv)
                for a_, da in enumerate((bx, by)):
                    for b_, db in enumerate((bx, by)):
                        rr_.append(da); cc_.append(db); vv_.append(kk[a_, b_])
            Ks = Ks + sp.csr_matrix((vv_, (rr_, cc_)), shape=(self.ndof, self.ndof))
        Ks = Ks.tocsr()
        self.k_uzlu = kd[np.array(reac, dtype=int)] if K.pruzna else None
        Kr = (self.T.T @ Ks @ self.T).tocsc()
        self._lu = spla.splu(Kr, permc_spec="MMD_ATA")
        self.free = nez

        self.vyst = self._vystupy()

    # ---- výstupy (pásy 1 m) -------------------------------------------------
    def _vystupy(self) -> Vystupy:
        nr = self.n_pruhu
        m = min(max(1, int(round(1.0 / self.c))), nr)
        skup = [np.arange(j, j + m) for j in range(nr - m + 1)]
        sirka = m * self.c
        fak = np.full(len(skup), 1.0 / sirka)
        S = np.zeros((len(skup), nr))
        for o, g in enumerate(skup):
            S[o, g] = fak[o]
        yc = np.array([float((self.p_y0[g] + 0.5 * self.c).mean()) for g in skup])
        v = Vystupy(S=S, skup=skup, faktor=fak,
                    i0=np.zeros(len(skup), int), i1=np.full(len(skup), self.nx - 1),
                    skoky=[self.k_sup.copy() for _ in skup], x0=np.zeros(len(skup)),
                    y=yc, popisky=[f"y={t:.2f}" for t in yc], deska=True,
                    sirka_okna=sirka, skoky_vse=self.k_sup.copy())
        v.x0_glob = np.array([self.K.x0(t) for t in yc])
        v.lokalni = True
        return v

    # ---- zatížení -----------------------------------------------------------
    def zatizeni(self, platky: List[Platek]) -> np.ndarray:
        """Uzlové síly od plošek; x → ξ = x − x0(y); mimo desku (ξ < 0,
        ξ > L) jde zatížení do opěry, příčně se ploška ořízne (síla zůstává)."""
        f = np.zeros(self.ndof)
        B, nx = self.B, self.nx
        K = self.K
        s_ = 1.0 if K.sikmost == "prava" else -1.0
        for F, x0, x1, y0, y1 in platky:
            if x1 <= x0 or y1 <= y0 or F == 0:
                continue
            y0c, y1c = max(0.0, y0), min(B, y1)
            if y1c <= y0c:
                continue
            nsx = max(6, int(math.ceil((x1 - x0) / self.a_ref * 6)))
            nsy = max(6, int(math.ceil((y1c - y0c) / self.c * 6)))
            xs_ = x0 + (np.arange(nsx) + 0.5) * (x1 - x0) / nsx
            ys_ = y0c + (np.arange(nsy) + 0.5) * (y1c - y0c) / nsy
            X, Y = np.meshgrid(xs_, ys_, indexing="ij"); X = X.ravel(); Y = Y.ravel()
            Fp = F / X.size
            xi = X + s_ * (Y - 0.5 * B) * K.cot           # ξ = x − x0(y)
            ok = (xi >= self.xs[0] - 1e-12) & (xi <= self.xs[-1] + 1e-12)
            if not ok.any():
                continue
            xi, Y = xi[ok], Y[ok]
            j = np.clip((Y // self.c).astype(int), 0, self.n_pruhu - 1)
            k = np.clip(np.searchsorted(self.xs, xi, side="right") - 1, 0, self.nex - 1)
            xn = 2 * (xi - self.xs[k]) / self.a_el[k] - 1
            en = 2 * (Y - j * self.c) / self.c - 1
            Nn = 0.25 * np.stack([(1 - xn) * (1 - en), (1 + xn) * (1 - en),
                                  (1 + xn) * (1 + en), (1 - xn) * (1 + en)], axis=1)
            e = j * self.nex + k
            np.add.at(f, self.E_dofs[e][:, 0::3].ravel(), (Fp * Nn).ravel())
        return f

    # ---- řešení ---------------------------------------------------------------
    def res(self, f: np.ndarray) -> np.ndarray:
        return self.T @ self._lu.solve(self.T.T @ f)

    def res_batch(self, F: np.ndarray) -> np.ndarray:
        return self.T @ self._lu.solve(np.ascontiguousarray(self.T.T @ F))

    def vyslednice(self, u: np.ndarray, surove: bool = False):
        nr, nx = self.n_pruhu, self.nx
        shp = (nr, nx) + (() if u.ndim == 1 else (u.shape[1],))
        M = (self.R_M @ u).reshape(shp)
        if self.K.vetknuti and not surove:
            # nad vetknutou podporou skok m_x → v uzlu podpory strana s větší |M|
            ks = self.k_sup[1:-1]
            if len(ks):
                a = (self.R_Mm @ u).reshape(shp)[:, ks]
                b = (self.R_Mp @ u).reshape(shp)[:, ks]
                M[:, ks] = np.where(np.abs(b) > np.abs(a), b, a)
        return (M, (self.R_Vm @ u).reshape(shp), (self.R_Vp @ u).reshape(shp))

    def vysledky(self, f: np.ndarray):
        u = self.res(f)
        M, Vm, Vp = self.vyslednice(u)
        return M, Vm, Vp, u

    def reakce_uzlu(self, f: np.ndarray, u: np.ndarray) -> np.ndarray:
        if self.k_uzlu is not None:
            # pružné uložení: reakce = síla v pružině k·w (v9: u tvrdého uložení
            # se vazba β_s = ∂w/∂s projeví jen samorovnovážnými silovými dvojicemi
            # podél linie podpory – nejsou to síly do ložisek)
            k_ = self.k_uzlu if u.ndim == 1 else self.k_uzlu[:, None]
            return k_ * u[self.reac_dof]
        return (f - self.Kfull @ u)[self.reac_dof]

    def reakce_rot(self, f: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Momentové reakce vetknutí (na βx podepřených uzlů; smysl jen u kolmé desky)."""
        if not len(self.reac_rot_dof):
            return np.zeros(0)
        return (f - self.Kfull @ u)[self.reac_rot_dof]

    def reakce(self, f: np.ndarray, u: np.ndarray) -> np.ndarray:
        return np.bincount(self.reac_j, weights=self.reakce_uzlu(f, u),
                           minlength=self.K.n_poli + 1)
