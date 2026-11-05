"""
plotting_sily.py
================
Grafy vnitřních sil pro posudek (vnitrni_sily.VysledekSil):
  plot_sily     průběhy M a V stavů g0, g − g0, q (obálka) na jednom výstupu,
  plot_pricne   příčné rozdělení: max M a max |V| stavů po výstupech + příčný řez
                (chodníky, vozovka, liniová zatížení, poloha vozidla).
"""

from __future__ import annotations
import matplotlib.pyplot as plt
import numpy as np

from .vnitrni_sily import VysledekSil, NAZVY_STAVU

BARVY = {"g0": "#7f7f7f", "g-g0": "#2e75b6", "q": "#e74c3c"}


def plot_sily(vys: VysledekSil, o: int, show: bool = True):
    """Průběhy M(x), V(x) stavů na výstupu o (0-based)."""
    jm, jv = vys.jednotky
    fig, (aM, aV) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True)
    for s in vys.stavy:
        t = vys.tabulka(o, s)
        c = BARVY.get(s, None)
        if vys.stavy[s].pohyblivy:
            aM.plot(t.x, t.M_max, c=c, label=f"{NAZVY_STAVU[s]} – max")
            aM.plot(t.x, t.M_min, c=c, ls="--", label=f"{NAZVY_STAVU[s]} – min")
            aV.plot(t.x, t.V_max, c=c)
            aV.plot(t.x, t.V_min, c=c, ls="--")
            aM.fill_between(t.x, t.M_min, t.M_max, color=c, alpha=0.08)
            aV.fill_between(t.x, t.V_min, t.V_max, color=c, alpha=0.08)
        else:
            aM.plot(t.x, t.M_max, c=c, label=NAZVY_STAVU[s])
            aV.plot(t.x, t.V_max, c=c)
    xp = np.array(vys.K.x_podpor)
    for a in (aM, aV):
        a.axhline(0, c="k", lw=0.6)
        for x in xp:
            a.axvline(x, c="k", lw=0.5, ls=":")
        a.grid(alpha=0.3)
    aM.invert_yaxis()
    aM.set_ylabel(f"M [{jm}]  (kladný dolů = tah dole)")
    aV.set_ylabel(f"V [{jv}]")
    aV.set_xlabel("x od osy první podpory [m]")
    aM.legend(fontsize=8, loc="lower right")
    aM.set_title(f"Vnitřní síly – {'pás' if vys.deska else 'nosník'} {vys.popisky[o]} "
                 f"(y = {float(vys.vyst.y[o]):.2f} m)")
    fig.tight_layout()
    if show:
        plt.show()
    return fig


def plot_pricne(vys: VysledekSil, show: bool = True):
    """Max M a max |V| jednotlivých stavů po výstupech a příčný řez mostovkou."""
    jm, jv = vys.jednotky
    sh = vys.souhrn()
    y = np.array([d["y"] for d in sh])
    B = vys.K.B
    fig, (aR, aM, aV) = plt.subplots(3, 1, figsize=(10, 9), sharex=True,
                                     gridspec_kw={"height_ratios": [1, 2.2, 2.2]})
    # příčný řez
    vyb = vys.vybaveni
    for nazev, g, y0, y1 in vyb.zony(B):
        aR.add_patch(plt.Rectangle((y0, 0.0), y1 - y0, 0.4,
                                   color="#bbbbbb" if "chodník" in nazev else "#555555",
                                   alpha=0.6))
        aR.text(0.5 * (y0 + y1), 0.2, f"{nazev}\n{g:g} kN/m²", ha="center", va="center",
                fontsize=7, color="w" if "vozovka" in nazev else "k")
    for l in vyb.liniova_vse(B):
        aR.add_patch(plt.Rectangle((l.y - 0.5 * l.sirka, 0.4), l.sirka, 0.35, color="#2e75b6"))
        aR.text(l.y, 0.85, f"{l.nazev}\n{l.g:g}", ha="center", va="bottom", fontsize=6)
    if "q" in vys.stavy:
        for yc in (vys.y_Ve - 0.5 * vys.rozvor, vys.y_Ve + 0.5 * vys.rozvor):
            aR.add_patch(plt.Rectangle((yc - 0.5 * vys.b_k, -0.45), vys.b_k, 0.3,
                                       color="#e74c3c", alpha=0.7))
        aR.text(vys.y_Ve, -0.75, vys.vozidlo, ha="center", fontsize=7, color="#e74c3c")
    if not vys.deska:
        for k in range(vys.K.N):
            y0 = k * vys.K.rozted
            aR.add_patch(plt.Rectangle((y0, -0.1), vys.K.b, 0.1, color="#2e75b6", alpha=0.3))
    aR.set_ylim(-0.9, 1.4)
    aR.set_yticks([])
    aR.set_title("Příčný řez – vybavení a poloha vozidla")
    gov = vys.rozhodujici("M")
    for s in vys.stavy:
        aM.plot(y, [d[f"M_{s}"] for d in sh], "o-", c=BARVY.get(s), ms=3, label=NAZVY_STAVU[s])
        aV.plot(y, [d[f"V_{s}"] for d in sh], "o-", c=BARVY.get(s), ms=3)
    aM.plot(y, [d["M_Ed"] for d in sh], "s-", c="k", ms=3, label="M_Ed (6.10, vč. g0)")
    aV.plot(y, [d["V_Ed"] for d in sh], "s-", c="k", ms=3)
    for a in (aM, aV):
        a.axvline(y[gov], c="#f39c12", lw=1.5, alpha=0.7)
        a.grid(alpha=0.3)
    aM.set_ylabel(f"max M [{jm}]")
    aV.set_ylabel(f"max |V| [{jv}]")
    aV.set_xlabel("y – příčná poloha osy výstupu [m]")
    aM.legend(fontsize=8)
    aM.set_title(f"Max. hodnoty po {'pásech 1 m' if vys.deska else 'nosnících'} "
                 f"(rozhoduje {vys.popisky[gov]})")
    aR.set_xlim(-0.2, B + 0.2)
    fig.tight_layout()
    if show:
        plt.show()
    return fig
