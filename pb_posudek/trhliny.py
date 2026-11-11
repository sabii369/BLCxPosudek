"""Mezní stav omezení trhlin – šířka trhlin (ČSN EN 1992-1-1, 7.3.4).

Průřez s trhlinou: rovinnost průřezu, beton v tahu nepůsobí, beton v tlaku i výztuž pružně
(E_cm, E_s, E_p). Soudržná předpínací výztuž má počáteční přetvoření ε_p0 (předpětí + dekomprese
betonu v úrovni výztuže od předpětí), vnější moment působí na celý průřez.
Jednotky: mm, N, MPa uvnitř; moment v kNm.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .prurez import Prurez

K1_SOUDRZNOST = 0.8    # 7.3.4(3): pruty s dobrou soudržností
K2_OHYB = 0.5          # ohyb
K3 = 3.4               # národní příloha – doporučená hodnota
K4 = 0.425
K_T = 0.4              # dlouhodobé zatížení (7.3.4(2)) – i pro opakované zatížení na mostech


@dataclass
class Vrstva:
    """Vrstva výztuže pro průřez s trhlinou."""
    z: float              # mm od spodního okraje
    A: float              # mm2
    E: float              # MPa
    eps0: float = 0.0     # počáteční přetvoření (předpínací výztuž)
    predpinaci: bool = False
    phi: float | None = None
    nazev: str = ""


@dataclass
class VysledekTrhliny:
    """Šířka trhliny u taženého okraje (strana +1 = dolní, −1 = horní)."""
    strana: int
    M: float                       # kNm
    x: float                       # výška tlačené oblasti [mm]
    kappa: float                   # křivost [1/mm]
    sigma_c: float                 # napětí v tlačeném okraji [MPa]
    sigma_s: float                 # napětí v tažené betonářské výztuži / přírůstek Δσ_p [MPa]
    vyztuz_s: str                  # "betonářská" | "předpínací"
    E_s: float
    h_cef: float
    A_ceff: float
    As_ef: float
    Ap_ef: float
    xi1: float
    rho: float
    deps: float                    # ε_sm − ε_cm
    deps_vzorec: str               # "(7.9)" | "0,6·σ_s/E_s"
    s_r: float                     # s_r,max [mm]
    s_r_vzorec: str                # "(7.11)" | "(7.14)"
    c: float | None
    phi: float | None
    w: float                       # mm
    vrstvy: list[dict] = field(default_factory=list)


def prurez_s_trhlinou(prurez: Prurez, Ec: float, vrstvy: list[Vrstva], M: float, strana: int = 1):
    """Pružný průřez s trhlinou pro moment M [kNm] (kladný = tah dole), N = 0.

    Přetvoření ε(z) = strana·κ·(z_n − z), κ > 0 (tah +). Pro danou polohu neutrálné osy z_n jsou
    síly lineární v κ; κ plyne z ΣN = 0, z_n se hledá tak, aby moment k těžišti byl roven M.
    Vrací (z_n, κ) nebo None (nenalezeno – např. bez předpětí nebo průřez bez trhliny).
    """
    h, zt = prurez.h, prurez.zt
    zp, dz, bp = prurez.pasy()
    z_v = np.array([v.z for v in vrstvy])
    EA = np.array([v.E * v.A for v in vrstvy])
    F0 = (EA * np.array([v.eps0 for v in vrstvy])).sum()
    if F0 <= 0 or strana * M <= 0:
        return None

    def moment(zn):
        e_c = strana * (zn - zp)
        a_c = Ec * np.minimum(e_c, 0.0) * bp * dz
        a_v = EA * strana * (zn - z_v)
        a = a_c.sum() + a_v.sum()
        if a >= 0:
            return None
        k = -F0 / a
        Mi = (k * a_c * (zt - zp)).sum() + ((k * a_v + EA * np.array([v.eps0 for v in vrstvy])) * (zt - z_v)).sum()
        return Mi * 1e-6, k

    # od taženého okraje k tlačenému – první průchod momentem M
    zz = np.linspace(0.002 * h, 0.998 * h, 500)
    if strana < 0:
        zz = zz[::-1]
    pred = None
    for zn in zz:
        r = moment(zn)
        if r is None:
            pred = None
            continue
        if pred is not None and (pred[1] - M) * (r[0] - M) <= 0:
            lo, hi = pred[0], zn
            f_lo = pred[1] - M
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                rm = moment(mid)
                if rm is None:
                    break
                if (rm[0] - M) * f_lo > 0:
                    lo, f_lo = mid, rm[0] - M
                else:
                    hi = mid
            zn = 0.5 * (lo + hi)
            r = moment(zn)
            return (zn, r[1]) if r else None
        pred = (zn, r[0])
    return None


def sirka_trhliny(prurez: Prurez, Ecm: float, fct_eff: float, vrstvy: list[Vrstva], M: float,
                  xi: float, strana: int = 1) -> VysledekTrhliny | None:
    """Šířka trhliny w_k = s_r,max·(ε_sm − ε_cm) podle 7.3.4 u taženého okraje."""
    res = prurez_s_trhlinou(prurez, Ecm, vrstvy, M, strana)
    if res is None:
        return None
    zn, k = res
    h = prurez.h
    x = h - zn if strana > 0 else zn
    zp, dz, bp = prurez.pasy()
    vzd = (lambda z: np.asarray(z, dtype=float)) if strana > 0 else (lambda z: h - np.asarray(z, dtype=float))
    sigma_c = -Ecm * k * x
    info = []
    tazene = []
    for v in vrstvy:
        eps = strana * k * (zn - v.z)
        ds = v.E * eps
        info.append(dict(nazev=v.nazev, z=v.z, A=v.A, eps=eps, dsigma=ds, predpinaci=v.predpinaci))
        if eps > 0:
            tazene.append((v, ds))
    if not tazene:
        return None
    A_t = sum(v.A for v, _ in tazene)
    hd = sum(v.A * float(vzd(v.z)) for v, _ in tazene) / A_t          # h − d
    h_cef = min(2.5 * hd, (h - x) / 3.0, h / 2.0)
    d_p = vzd(zp)
    A_ceff = float((bp * np.clip(h_cef - (d_p - dz / 2), 0.0, dz)).sum())
    v_ef = [(v, ds) for v, ds in tazene if float(vzd(v.z)) <= h_cef]
    s_ef = [(v, ds) for v, ds in v_ef if not v.predpinaci]
    p_ef = [(v, ds) for v, ds in v_ef if v.predpinaci]
    As_ef = sum(v.A for v, _ in s_ef)
    Ap_ef = sum(v.A for v, _ in p_ef)
    xi1 = math.sqrt(xi)
    rho = (As_ef + xi1 ** 2 * Ap_ef) / A_ceff if A_ceff > 0 else 0.0
    # napětí v tažené výztuži: betonářská (u okraje), jinak přírůstek napětí v předpínací výztuži
    s_t = [(v, ds) for v, ds in tazene if not v.predpinaci]
    if s_t:
        v_s, sigma_s = max(s_t, key=lambda t: t[1])
        druh_s = "betonářská"
    else:
        v_s, sigma_s = max(tazene, key=lambda t: t[1])
        druh_s = "předpínací"
    Es = v_s.E
    ae = Es / Ecm
    if rho > 0:
        d79 = (sigma_s - K_T * fct_eff / rho * (1 + ae * rho)) / Es
    else:
        d79 = sigma_s / Es
    d_min = 0.6 * sigma_s / Es
    deps, deps_vz = (d79, "(7.9)") if d79 >= d_min else (d_min, "0,6·σ_s/E_s")
    # vzdálenost trhlin: (7.11) s betonářskou výztuží o známém průměru v A_c,eff, jinak (7.14)
    c = phi = None
    if s_ef and all(v.phi for v, _ in s_ef) and rho > 0:
        n = [v.A / (math.pi * v.phi ** 2 / 4) for v, _ in s_ef]
        phi = sum(ni * v.phi ** 2 for ni, (v, _) in zip(n, s_ef)) / sum(ni * v.phi for ni, (v, _) in zip(n, s_ef))
        c = max(min(float(vzd(v.z)) - v.phi / 2 for v, _ in s_ef), 0.0)
        s_r = K3 * c + K1_SOUDRZNOST * K2_OHYB * K4 * phi / rho
        s_r_vz = "(7.11)"
    else:
        s_r = 1.3 * (h - x)
        s_r_vz = "(7.14)"
    return VysledekTrhliny(
        strana=strana, M=M, x=x, kappa=k, sigma_c=sigma_c, sigma_s=float(sigma_s), vyztuz_s=druh_s, E_s=Es,
        h_cef=h_cef, A_ceff=A_ceff, As_ef=As_ef, Ap_ef=Ap_ef, xi1=xi1, rho=rho, deps=deps, deps_vzorec=deps_vz,
        s_r=s_r, s_r_vzorec=s_r_vz, c=c, phi=phi, w=s_r * deps, vrstvy=info)


def xi_predpinaci(predem: bool, druh: str | None, fck: float) -> float:
    """Poměr soudržnosti ξ předpínací a betonářské výztuže (ČSN EN 1992-1-1, tab. 6.2).

    Lana / dráty (s vtisky); dodatečně předpjaté: ≤ C50/60 a ≥ C70/80, mezi lineárně.
    """
    drat = druh == "drat"
    if predem:
        return 0.7 if drat else 0.6
    lo, hi = (0.6, 0.4) if drat else (0.5, 0.25)
    t = min(max((fck - 50.0) / 20.0, 0.0), 1.0)
    return lo + (hi - lo) * t
