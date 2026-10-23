"""Smršťování a dotvarování betonu podle ČSN EN 1992-1-1, čl. 3.1.4 a přílohy B.

Čas t, t0, ts ve dnech (stáří betonu), RH [%], h0 [mm].
"""
from __future__ import annotations

import math

import numpy as np

from .materialy import CEMENT_ALPHA, CEMENT_ALPHA_DS, Beton


def k_h(h0: float) -> float:
    """Součinitel k_h podle tabulky 3.3 (lineární interpolace)."""
    return float(np.interp(h0, [100, 200, 300, 500], [1.0, 0.85, 0.75, 0.70]))


def smrstovani(beton: Beton, RH: float, h0: float, t: float, ts: float) -> dict:
    """Celkové smršťování ε_cs(t) = ε_cd(t) + ε_ca(t) (3.8). Vrací slovník mezivýsledků.

    Smršťování je uvažováno se zápornou hodnotou (zkrácení).
    """
    a1, a2 = CEMENT_ALPHA_DS[beton.cement]
    beta_RH = 1.55 * (1.0 - (RH / 100.0) ** 3)
    eps_cd0 = 0.85 * ((220.0 + 110.0 * a1) * math.exp(-a2 * beton.fcm / 10.0)) * 1e-6 * beta_RH
    kh = k_h(h0)
    dt = max(t - ts, 0.0)
    beta_ds = dt / (dt + 0.04 * math.sqrt(h0 ** 3))
    eps_cd = beta_ds * kh * eps_cd0
    eps_ca_inf = 2.5 * (beton.fck - 10.0) * 1e-6
    beta_as = 1.0 - math.exp(-0.2 * math.sqrt(max(t, 0.0)))
    eps_ca = beta_as * eps_ca_inf
    return dict(alpha_ds1=a1, alpha_ds2=a2, beta_RH=beta_RH, eps_cd0=eps_cd0, k_h=kh,
                beta_ds=beta_ds, eps_cd=eps_cd, eps_ca_inf=eps_ca_inf, beta_as=beta_as,
                eps_ca=eps_ca, eps_cs=-(eps_cd + eps_ca))


def upravene_stari(beton: Beton, t0: float) -> float:
    """Stáří při zatížení upravené podle druhu cementu (B.9), teplota 20 °C."""
    a = CEMENT_ALPHA[beton.cement]
    return max(t0 * (9.0 / (2.0 + t0 ** 1.2) + 1.0) ** a, 0.5)


def dotvarovani(beton: Beton, RH: float, h0: float, t: float, t0: float) -> dict:
    """Součinitel dotvarování φ(t,t0) podle přílohy B.1. Vrací slovník mezivýsledků."""
    fcm = beton.fcm
    a1 = (35.0 / fcm) ** 0.7
    a2 = (35.0 / fcm) ** 0.2
    a3 = (35.0 / fcm) ** 0.5
    if fcm <= 35:
        phi_RH = 1.0 + (1.0 - RH / 100.0) / (0.1 * h0 ** (1.0 / 3.0))
        beta_H = min(1.5 * (1.0 + (0.012 * RH) ** 18) * h0 + 250.0, 1500.0)
    else:
        phi_RH = (1.0 + (1.0 - RH / 100.0) / (0.1 * h0 ** (1.0 / 3.0)) * a1) * a2
        beta_H = min(1.5 * (1.0 + (0.012 * RH) ** 18) * h0 + 250.0 * a3, 1500.0 * a3)
    beta_fcm = 16.8 / math.sqrt(fcm)
    t0_u = upravene_stari(beton, t0)
    beta_t0 = 1.0 / (0.1 + t0_u ** 0.20)
    phi0 = phi_RH * beta_fcm * beta_t0
    dt = max(t - t0, 0.0)
    beta_c = (dt / (beta_H + dt)) ** 0.3 if dt > 0 else 0.0
    return dict(alpha1=a1, alpha2=a2, alpha3=a3, phi_RH=phi_RH, beta_fcm=beta_fcm,
                t0_upr=t0_u, beta_t0=beta_t0, phi0=phi0, beta_H=beta_H, beta_c=beta_c,
                phi=phi0 * beta_c)


def phi(beton: Beton, RH: float, h0: float, t: float, t0: float) -> float:
    return dotvarovani(beton, RH, h0, t, t0)["phi"]


def eps_cs(beton: Beton, RH: float, h0: float, t: float, ts: float) -> float:
    return smrstovani(beton, RH, h0, t, ts)["eps_cs"]


def nelinearni_dotvarovani(phi_lin: float, sigma_c: float, fck_t0: float) -> tuple[float, float]:
    """Nelineární dotvarování (3.7) pro |σ_c| > 0,45·f_ck(t0). Vrací (φ_nl, k_σ)."""
    k_sigma = abs(sigma_c) / fck_t0 if fck_t0 > 0 else 0.0
    if k_sigma <= 0.45:
        return phi_lin, k_sigma
    return phi_lin * math.exp(1.5 * (k_sigma - 0.45)), k_sigma
