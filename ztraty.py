"""Ztráty předpětí podle ČSN EN 1992-1-1, čl. 5.10.4–5.10.6.

Všechny funkce pracují s napětím v předpínací výztuži [MPa] po délce kabelu.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def ztrata_trenim(sigma_max: float, theta: np.ndarray, s: np.ndarray, mu: float,
                  k: float) -> np.ndarray:
    """Napětí po ztrátě třením σ(x) = σ_max·e^{−μ(θ + k·s)}  (5.45).

    theta – součet úhlových změn od kotvy [rad], s – délka kabelu od kotvy [m].
    """
    return sigma_max * np.exp(-mu * (theta + k * s))


def _integral(y: np.ndarray, x: np.ndarray) -> float:
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(x)))


@dataclass
class VysledekPokluzu:
    sigma: np.ndarray       # napětí po pokluzu (na stejné síti jako vstup)
    x_w: float              # dosah pokluzu od kotvy [m]
    dsigma_kotva: float     # ztráta v místě kotvy [MPa]
    plocha: float           # požadovaná plocha w·Ep [MPa·m]
    cely_kabel: bool        # pokluz ovlivní celý kabel


def ztrata_pokluzem(x: np.ndarray, sigma0: np.ndarray, w_mm: float, Ep: float,
                    x_konec: float | None = None) -> VysledekPokluzu:
    """Ztráta pokluzem v kotvě metodou plochy napětí.

    Kotva je v x[0]; x roste od kotvy. Po zakotvení je průběh napětí zrcadlově
    převrácený podle úrovně λ = σ(x_w):  σ_po(x) = 2λ − σ0(x)  pro x < x_w,
    kde x_w je dáno podmínkou ∫ (σ0 − σ_po) dx = w·E_p.
    x_konec – omezení oblasti vlivu (např. místo minima při oboustranném napínání).
    """
    x = np.asarray(x, float)
    sigma0 = np.asarray(sigma0, float)
    xd = x - x[0]
    if x_konec is not None:
        m = xd <= abs(x_konec - x[0]) + 1e-12
    else:
        m = np.ones_like(xd, bool)
    xr, sr = xd[m], sigma0[m]
    req = w_mm * 1e-3 * Ep  # MPa·m

    def plocha(lam: float) -> float:
        # oblast od kotvy po první průsečík σ0 = λ
        below = np.nonzero(sr <= lam)[0]
        if len(below) == 0:
            xs, ss = xr, sr
        else:
            j = below[0]
            if j == 0:
                return 0.0
            # lineární dopočet průsečíku
            x1, x2, s1, s2 = xr[j - 1], xr[j], sr[j - 1], sr[j]
            xc = x1 + (s1 - lam) / (s1 - s2) * (x2 - x1) if s1 != s2 else x2
            xs = np.concatenate([xr[:j], [xc]])
            ss = np.concatenate([sr[:j], [lam]])
        return _integral(2.0 * np.maximum(ss - lam, 0.0), xs)

    lam_min = float(sr.min())
    sigma = sigma0.copy()
    if plocha(lam_min) < req:
        # pokluz zasáhne celou oblast – posun o konstantu
        c = (req - plocha(lam_min)) / max(xr[-1], 1e-9)
        loss = 2.0 * np.maximum(sr - lam_min, 0.0) + c
        sigma[m] = sr - loss
        return VysledekPokluzu(sigma, float(xr[-1]), float(loss[0]), req, True)
    lo, hi = lam_min, float(sr[0])
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if plocha(mid) > req:
            lo = mid
        else:
            hi = mid
    lam = 0.5 * (lo + hi)
    below = np.nonzero(sr <= lam)[0]
    if len(below):
        j = below[0]
        x1, x2, s1, s2 = xr[j - 1], xr[j], sr[j - 1], sr[j]
        x_w = x1 + (s1 - lam) / (s1 - s2) * (x2 - x1) if s1 != s2 else x2
    else:
        x_w = xr[-1]
    loss = np.where(xr < x_w, 2.0 * np.maximum(sr - lam, 0.0), 0.0)
    sigma[m] = sr - loss
    return VysledekPokluzu(sigma, float(x_w), float(loss[0]), req, False)


def ztrata_dlouhodoba_546(eps_cs: float, Ep: float, dsigma_pr: float, Ecm: float,
                          phi: float, sigma_c_qp: float, Ap: float, Ac: float, Ic: float,
                          z_cp: float, creep_term: float | None = None) -> tuple[float, dict]:
    """Dlouhodobá ztráta Δσ_p,c+s+r podle (5.46) [MPa] (kladná hodnota = ztráta).

    eps_cs   – smršťování po vnesení předpětí (záporné = zkrácení)
    dsigma_pr – ztráta relaxací (kladná)
    sigma_c_qp – napětí v betonu v úrovni kabelu od kvazistálé kombinace (tlak záporný)
    creep_term – volitelně přímo Σ φ(t,ti)·Δσ_c,i (superpozice zatěžovacích kroků)
    Ap, Ac [mm2], Ic [mm4], z_cp [mm].
    """
    alpha = Ep / Ecm
    ct = creep_term if creep_term is not None else phi * sigma_c_qp
    citatel = -eps_cs * Ep + 0.8 * dsigma_pr - alpha * ct
    jmenovatel = 1.0 + alpha * Ap / Ac * (1.0 + Ac / Ic * z_cp ** 2) * (1.0 + 0.8 * phi)
    return citatel / jmenovatel, dict(alpha=alpha, citatel=citatel, jmenovatel=jmenovatel,
                                      clen_smrst=-eps_cs * Ep, clen_relax=0.8 * dsigma_pr,
                                      clen_dotv=-alpha * ct)


def ztrata_pokluzem_obecne(x: np.ndarray, sigma0: np.ndarray, f_zpet: np.ndarray, w_mm: float, Ep: float,
                           x_konec: float | None = None) -> VysledekPokluzu:
    """Ztráta pokluzem pro obecný (i nemonotónní) průběh napětí, např. po přepnutí a povolení lisu.

    Při pokluzu se kabel u kotvy zkracuje a tření působí opačně než při napínání:
    σ_po(x) = min[σ0(x); σ_A·f_zpet(x)], f_zpet = e^{+μ(θ + k·x)} od kotvy, kde napětí v kotvě σ_A
    je dáno podmínkou ∫ (σ0 − σ_po) dx = w·E_p. Kotva je v x[0].
    """
    x = np.asarray(x, float)
    sigma0 = np.asarray(sigma0, float)
    xd = x - x[0]
    m = xd <= abs(x_konec - x[0]) + 1e-12 if x_konec is not None else np.ones_like(xd, bool)
    xr, sr, fr = xd[m], sigma0[m], np.asarray(f_zpet, float)[m]
    req = w_mm * 1e-3 * Ep

    def plocha(sa: float) -> float:
        return _integral(sr - np.minimum(sr, sa * fr), xr)

    sigma = sigma0.copy()
    if plocha(0.0) <= req:
        # pokluz zasáhne celou oblast – posun o konstantu
        c = (req - plocha(0.0)) / max(xr[-1], 1e-9)
        sigma[m] = -c * np.ones_like(sr)
        return VysledekPokluzu(sigma, float(xr[-1]), float(sr[0] - sigma[m][0]), req, True)
    lo, hi = 0.0, float(sr[0])
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if plocha(mid) > req:
            lo = mid
        else:
            hi = mid
    sa = 0.5 * (lo + hi)
    po = np.minimum(sr, sa * fr)
    zasah = np.nonzero(po < sr - 1e-9)[0]
    cely = bool(len(zasah)) and zasah[-1] == len(xr) - 1
    if len(zasah) and not cely:
        # průsečík σ_A·f_zpet(x) = σ0(x) lineární interpolací mezi uzly
        j = zasah[-1]
        d1, d2 = sa * fr[j] - sr[j], sa * fr[j + 1] - sr[j + 1]
        x_w = float(xr[j] + (xr[j + 1] - xr[j]) * (-d1) / (d2 - d1)) if d2 != d1 else float(xr[j + 1])
    else:
        x_w = float(xr[-1]) if len(zasah) else 0.0
    sigma[m] = po
    return VysledekPokluzu(sigma, x_w, float(sr[0] - po[0]), req, cely)
