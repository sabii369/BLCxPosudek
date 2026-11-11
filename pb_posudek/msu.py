"""Mezní stav únosnosti – ohyb (metoda mezních přetvoření) a smyk (ČSN EN 1992-1-1, 6.1–6.2).

Jednotky: mm, N, MPa uvnitř; výsledné síly v kN a momenty v kNm.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .materialy import Beton, BetonarskaVyztuz, PredpinaciVyztuz
from .prurez import Prurez


@dataclass
class VrstvaPredpeti:
    z: float          # mm
    Ap: float         # mm2
    eps0: float       # počáteční přetvoření (předpětí + dekomprese) [-]
    nazev: str = ""


@dataclass
class VrstvaVyztuze:
    z: float
    As: float
    nazev: str = ""
    phi: float | None = None   # průměr prutů [mm] (šířka trhlin, 7.3.4(3); None = neznámý)


@dataclass
class VysledekOhybu:
    MRd: float                      # kNm
    x: float                        # výška tlačené oblasti [mm]
    kappa: float                    # křivost [1/mm]
    eps_horni: float
    eps_dolni: float
    rozhoduje: str                  # "beton" | "výztuž"
    Fc: float                       # tlaková síla v betonu [kN] (záporná)
    z_Fc: float                     # působiště tlakové síly [mm od spodu]
    rameno: float                   # rameno vnitřních sil [mm]
    vrstvy_p: list[dict] = field(default_factory=list)
    vrstvy_s: list[dict] = field(default_factory=list)
    konvergence: bool = True


def ohybova_unosnost(prurez: Prurez, beton: Beton, predp: PredpinaciVyztuz,
                     betonarska: BetonarskaVyztuz, kabely: list[VrstvaPredpeti],
                     vyztuz: list[VrstvaVyztuze], N_Ed: float = 0.0,
                     eps_ud_p: float | None = None) -> VysledekOhybu:
    """Moment únosnosti pro kladný (dolní vlákna tažená) ohyb.

    Přetvoření roviny: ε(z) = κ·(z_n − z), z_n = h − x. Předpínací výztuž má počáteční
    přetvoření eps0, její celkové přetvoření je eps0 + ε(z). N_Ed [kN] – vnější osová síla
    (tah +), která musí být v rovnováze s vnitřními silami. eps_ud_p – mezní přetvoření
    předpínací výztuže (None = predp.eps_ud; menší při tažnosti oslabené korozí, pracovní
    diagram se nemění).
    """
    eud_p = predp.eps_ud if eps_ud_p is None else eps_ud_p
    h = prurez.h
    zp, dz, bp = prurez.pasy()
    zk = np.array([k.z for k in kabely]) if kabely else np.zeros(0)
    Ak = np.array([k.Ap for k in kabely]) if kabely else np.zeros(0)
    e0 = np.array([k.eps0 for k in kabely]) if kabely else np.zeros(0)
    zs = np.array([v.z for v in vyztuz]) if vyztuz else np.zeros(0)
    As = np.array([v.As for v in vyztuz]) if vyztuz else np.zeros(0)
    ecu = beton.eps_cu2

    def stav(x: float):
        zn = h - x
        k_c = ecu / x
        kap = k_c
        rozh = "beton"
        for zi, ei in zip(zk, e0):
            if zi < zn:
                k_p = (eud_p - ei) / (zn - zi)
                if k_p < kap:
                    kap, rozh = k_p, "výztuž"
        for zi in zs:
            if zi < zn:
                k_s = betonarska.eps_ud / (zn - zi)
                if k_s < kap:
                    kap, rozh = k_s, "výztuž"
        eps_c = kap * (zn - zp)
        sc = beton.sigma_msu(eps_c)
        Fc = sc * bp * dz
        eps_p = e0 + kap * (zn - zk)
        sp = predp.sigma_msu(eps_p)
        Fp = sp * Ak
        eps_s = kap * (zn - zs)
        ss = betonarska.sigma_msu(eps_s)
        Fs = ss * As
        N = Fc.sum() + Fp.sum() + Fs.sum()
        return N, kap, rozh, Fc, eps_p, sp, Fp, eps_s, ss, Fs

    target = N_Ed * 1e3
    lo, hi = 1e-3 * h, 5.0 * h
    f_lo = stav(lo)[0] - target
    f_hi = stav(hi)[0] - target
    ok = f_lo > 0 > f_hi
    if ok:
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if stav(mid)[0] - target > 0:
                lo = mid
            else:
                hi = mid
    x = 0.5 * (lo + hi)
    N, kap, rozh, Fc, eps_p, sp, Fp, eps_s, ss, Fs = stav(x)
    zt = prurez.zt
    M = (Fc * (zt - zp)).sum() + (Fp * (zt - zk)).sum() + (Fs * (zt - zs)).sum()
    Fc_sum = Fc.sum()
    z_Fc = (Fc * zp).sum() / Fc_sum if Fc_sum != 0 else h
    Ft = Fp[Fp > 0].sum() + Fs[Fs > 0].sum()
    z_Ft = ((Fp * zk)[Fp > 0].sum() + (Fs * zs)[Fs > 0].sum()) / Ft if Ft > 0 else 0.0
    zn = h - x
    return VysledekOhybu(
        MRd=M * 1e-6, x=x, kappa=kap, eps_horni=kap * (zn - h), eps_dolni=kap * zn,
        rozhoduje=rozh, Fc=Fc_sum * 1e-3, z_Fc=z_Fc, rameno=z_Fc - z_Ft,
        vrstvy_p=[dict(nazev=k.nazev, z=k.z, Ap=k.Ap, eps0=k.eps0, eps=float(e), sigma=float(s),
                       F=float(f) * 1e-3) for k, e, s, f in zip(kabely, eps_p, sp, Fp)],
        vrstvy_s=[dict(nazev=v.nazev, z=v.z, As=v.As, eps=float(e), sigma=float(s),
                       F=float(f) * 1e-3) for v, e, s, f in zip(vyztuz, eps_s, ss, Fs)],
        konvergence=ok,
    )


# ---------------------------------------------------------------------------
# Smyk
# ---------------------------------------------------------------------------

@dataclass
class VysledekSmyku:
    V_Ed: float
    V_Rd: float
    V_Rd_c: float
    V_Rd_s: float
    V_Rd_max: float
    cot_theta: float
    trhliny: bool
    sigma_cp: float
    d: float
    z: float
    bw: float
    bw_nom: float
    alpha_cw: float
    nu1: float
    rho_l: float
    k: float
    rho_w: float
    rho_w_min: float
    dF_td: float
    mezi: dict = field(default_factory=dict)


def alpha_cw(sigma_cp: float, fcd: float) -> float:
    """Součinitel α_cw (6.11aN–6.11cN), σ_cp tlak kladně."""
    s = max(sigma_cp, 0.0)
    if s <= 0:
        return 1.0
    if s <= 0.25 * fcd:
        return 1.0 + s / fcd
    if s <= 0.5 * fcd:
        return 1.25
    return max(2.5 * (1.0 - s / fcd), 0.0)


def smykova_unosnost(beton: Beton, betonarska: BetonarskaVyztuz, V_Ed: float, N_Ed: float,
                     A_c: float, I_c: float, S_t: float, b_t: float, bw: float, bw_nom: float,
                     d: float, A_sl: float, Asw_s: float, alpha_deg: float,
                     trhliny: bool, cot_min: float = 1.0, cot_max: float = 2.5,
                     alpha_l: float = 1.0, z_ohyb: float | None = None,
                     vrdc_uroven: dict | None = None) -> VysledekSmyku:
    """Smyková únosnost podle 6.2.2 a 6.2.3.

    V_Ed [kN] (absolutní), N_Ed [kN] (tlak záporný), A_c [mm2], I_c [mm4], S_t [mm3]
    statický moment k těžišti, b_t šířka v těžišti, bw, bw_nom [mm], d [mm],
    A_sl [mm2] podélná tahová výztuž (vč. soudržné předpínací), Asw_s [mm2/mm].
    vrdc_uroven – V_Rd,c podle (6.4) stanovené jako minimum přes úrovně průřezu
    (6.2.2(2) pozn.): dict(V, I, b, S, z, sigma_cp); jinak se (6.4) počítá v těžišti.
    Únosnost: V_Rd = max(V_Rd,c; min(V_Rd,s; V_Rd,max)).
    """
    fck, fcd, fctd = beton.fck, beton.fcd, beton.fctd
    sigma_cp = max(-N_Ed * 1e3 / A_c, 0.0)  # tlak kladně
    k = min(1.0 + math.sqrt(200.0 / d), 2.0)
    rho_l = min(A_sl / (bw * d), 0.02)
    if not trhliny and vrdc_uroven is not None:
        V_Rd_c = vrdc_uroven["V"]
    elif not trhliny:
        V_Rd_c = I_c * b_t / S_t * math.sqrt(fctd ** 2 + alpha_l * sigma_cp * fctd) * 1e-3
    else:
        CRdc = 0.18 / beton.gamma_c
        s_cp = min(sigma_cp, 0.2 * fcd)
        v_min = 0.035 * k ** 1.5 * math.sqrt(fck)
        V1 = (CRdc * k * (100 * rho_l * fck) ** (1 / 3) + 0.15 * s_cp) * bw * d
        V2 = (v_min + 0.15 * s_cp) * bw * d
        V_Rd_c = max(V1, V2) * 1e-3
    z = z_ohyb if z_ohyb else 0.9 * d
    nu1 = 0.6 * (1.0 - fck / 250.0)
    acw = alpha_cw(sigma_cp, fcd)
    a = math.radians(alpha_deg)
    cot_a = 1.0 / math.tan(a) if abs(a - math.pi / 2) > 1e-9 else 0.0
    fywd = betonarska.fyd

    def vrds(c):
        return Asw_s * z * fywd * (c + cot_a) * math.sin(a) * 1e-3

    def vrdmax(c):
        return acw * bw_nom * z * nu1 * fcd * (c + cot_a) / (1.0 + c * c) * 1e-3

    cs = np.linspace(cot_min, cot_max, 301)
    vals = [min(vrds(c), vrdmax(c)) for c in cs]
    i = int(np.argmax(vals))
    cot_t = float(cs[i])
    V_Rd_s, V_Rd_max = vrds(cot_t), vrdmax(cot_t)
    # bez výpočtové smykové výztuže únosnost V_Rd,c; se smykovou výztuží min(V_Rd,s; V_Rd,max)
    V_Rd = max(V_Rd_c, min(V_Rd_s, V_Rd_max)) if Asw_s > 0 else V_Rd_c
    rho_w = Asw_s / (bw * math.sin(a)) if bw > 0 else 0.0
    rho_w_min = 0.08 * math.sqrt(fck) / betonarska.fyk
    dF = 0.5 * V_Ed * (cot_t - cot_a)
    return VysledekSmyku(
        V_Ed=V_Ed, V_Rd=V_Rd, V_Rd_c=V_Rd_c, V_Rd_s=V_Rd_s, V_Rd_max=V_Rd_max,
        cot_theta=cot_t, trhliny=trhliny, sigma_cp=sigma_cp, d=d, z=z, bw=bw, bw_nom=bw_nom,
        alpha_cw=acw, nu1=nu1, rho_l=rho_l, k=k, rho_w=rho_w, rho_w_min=rho_w_min, dF_td=dF,
        mezi=dict(fywd=fywd, cot_alpha=cot_a, alpha_l=alpha_l, I_c=I_c, S_t=S_t, b_t=b_t,
                  uroven=vrdc_uroven),
    )
