"""
plotting_sily.py
================
Grafy vnitřních sil pro posudek (vnitrni_sily.VysledekSil):
  plot_sily     průběhy M a V stavů g0, g − g0, q (obálka) na jednom výstupu,
  plot_pricne   příčné rozdělení: max M a max |V| stavů po výstupech + příčný řez
                (chodníky, vozovka, liniová zatížení, poloha vozidla),
  kresli_most   půdorys mostu se zatížením stavu g0, g − g0 nebo q v dané poloze
                (do zadané osy), plot_zatizeni_most – samostatný graf.
"""

from __future__ import annotations
import textwrap
from typing import Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon, Rectangle

from .vnitrni_sily import VysledekSil, NAZVY_STAVU, PolohaVozidla

BARVY = {"g0": "#7f7f7f", "g-g0": "#2e75b6", "qch": "#1baf7a", "q": "#e74c3c"}
C_NOSNIK, C_SPARA, C_POS = "#d5e8f5", "#eeeeee", "#f39c12"


def _x_glob(vys: VysledekSil, o: int, x_lok: float, y: float) -> float:
    """Globální x 2D modelu pro lokální x výstupu o v příčné poloze y."""
    if getattr(vys.vyst, "lokalni", False):
        return x_lok + vys.K.x0(y)
    return x_lok + float(vys.vyst.x0[o])


def _pas(ax, vys, y0, y1, **kw):
    """Pás mostovky y0 … y1 po celé délce (rovnoběžník podél šikmých podpor)."""
    K = vys.K
    a, b = K.x0(y0), K.x0(y1)
    ax.add_patch(Polygon([(a, y0), (a + K.Ltot, y0), (b + K.Ltot, y1), (b, y1)], closed=True, **kw))


def kresli_most(ax, vys: VysledekSil, o: int, stav: str, poloha: Optional[PolohaVozidla] = None,
                rezy: Sequence[tuple] = ()):
    """Půdorys mostu: nosníky (posuzovaný zvýrazněn), osy podpor a zatížení stavu
    "g0" | "g-g0" | "q" (q = plošky kol v poloze `poloha`).  rezy = [(x_lok, popisek)]
    – řezy na posuzovaném výstupu."""
    K, vyb = vys.K, vys.vybaveni
    B, L = K.B, K.Ltot
    jm = "kN/m²" if vys.deska else "kN/m"
    # nosná konstrukce
    if vys.deska:
        _pas(ax, vys, 0.0, B, fc=C_NOSNIK, ec="#2e75b6", lw=0.8)
    else:
        for k, y in enumerate(K.y_nos):
            y0 = y - 0.5 * K.b
            x0 = K.x0(y)
            ax.add_patch(Rectangle((x0, y0), L, K.b, fc=C_NOSNIK, ec="#2e75b6", lw=0.6))
            if K.spara and k < K.N - 1:
                ax.add_patch(Rectangle((min(x0, K.x0(y + K.rozted)), y0 + K.b),
                                       L, K.b_s, fc=C_SPARA, ec="#bbbbbb", lw=0.4))
    # zatížení
    if stav == "g0":
        if vys.deska:
            _pas(ax, vys, 0.0, B, fc=BARVY["g0"], alpha=0.35, hatch="//", ec="#555555", lw=0)
        else:
            for y in K.y_nos:
                ax.add_patch(Rectangle((K.x0(y), y - 0.5 * K.b), L, K.b, fc=BARVY["g0"], alpha=0.35,
                                       hatch="//", ec="#555555", lw=0))
        txt = (f"g0 = {vys.g0:.2f} {jm}" +
               ("" if vys.deska else " – každý nosník samostatně (bez spolupůsobení)"))
        ax.text(K.x0(0.5 * B) + 0.5 * L, 0.5 * B, txt, ha="center", va="center", fontsize=9,
                bbox=dict(fc="white", ec="#888888", alpha=0.9))
    elif stav == "g-g0":
        for nazev, g, y0, y1 in vyb.zony(B):
            voz = "vozovka" in nazev
            _pas(ax, vys, y0, y1, fc="#555555" if voz else "#bbbbbb", alpha=0.45, ec="none")
            ym = 0.5 * (y0 + y1)
            ax.text(K.x0(ym) + 0.72 * L, ym, f"{nazev} {g:g} kN/m²", ha="center", va="center",
                    fontsize=7, color="w" if voz else "k")
        for l in vyb.liniova_vse(B):
            _pas(ax, vys, max(0.0, l.y - 0.5 * l.sirka), min(B, l.y + 0.5 * l.sirka),
                 fc=BARVY["g-g0"], alpha=0.85, ec="none")
            ax.text(K.x0(l.y) + 0.03 * L, l.y, f"{l.nazev} {l.g:g} kN/m", fontsize=6.5, va="center",
                    color=BARVY["g-g0"], bbox=dict(fc="white", ec="none", alpha=0.75, pad=1))
        if vys.g_spary:
            ax.text(K.x0(0.0) + L, -0.08 * B, f"výplň spáry {vys.g_spary:g} kN/m (samostatně)",
                    ha="right", va="top", fontsize=7)
    elif stav == "q" and poloha is not None:
        for x0, x1, y0, y1, q in getattr(poloha, "plosne", []):     # rovnoměrné (schéma Vn)
            y0c, y1c = max(0.0, y0), min(B, y1)
            ax.add_patch(Rectangle((x0, y0c), x1 - x0, y1c - y0c, fc=BARVY["q"], alpha=0.18,
                                   ec="none", lw=0))
        for F, x0, x1, y0, y1 in poloha.platky:
            y0c, y1c = max(0.0, y0), min(B, y1)
            xa = K.x0(0.5 * (y0c + y1c))
            x0c, x1c = max(x0, xa), min(x1, xa + L)      # část mimo most jde do opěry
            if x1c <= x0c or y1c <= y0c:
                continue
            ax.add_patch(Rectangle((x0c, y0c), x1c - x0c, y1c - y0c, fc=BARVY["q"], alpha=0.6,
                                   ec="#a52a1a", lw=0.5))
        hl, _, hodn = poloha.popis.rpartition(": ")
        sirka = max(30, int(11 * ax.get_figure().get_figwidth() /
                            max(1, len(ax.get_figure().axes))))
        ax.set_title(textwrap.fill(hl + ":", sirka) + "\n" + hodn if hl else
                     textwrap.fill(poloha.popis, sirka), fontsize=8.5)
    # posuzovaný výstup
    yo = float(vys.vyst.y[o])
    if vys.deska:
        w = vys.vyst.sirka_okna
        _pas(ax, vys, yo - 0.5 * w, yo + 0.5 * w, fill=False, ec=C_POS, lw=2.2)
    else:
        ax.add_patch(Rectangle((K.x0(yo), yo - 0.5 * K.b), L, K.b, fill=False, ec=C_POS, lw=2.2))
    ax.text(K.x0(yo) - 0.02 * L, yo, vys.popisky[o], ha="right", va="center", fontsize=8,
            color=C_POS, fontweight="bold")
    # osy podpor
    for xp in K.x_podpor:
        ax.plot([xp + K.x0(0.0), xp + K.x0(B)], [0.0, B], color="k", lw=1.0, ls="-.")
    # řezy
    hw = 0.5 * (vys.vyst.sirka_okna if vys.deska else K.b) + 0.25
    for x_lok, pop in rezy:
        xg = _x_glob(vys, o, x_lok, yo)
        ax.plot([xg, xg], [yo - hw, yo + hw], color="#b42323", lw=1.8)
        ax.text(xg, yo + hw, pop, ha="center", va="bottom", fontsize=7, color="#b42323",
                bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
    sx = abs(0.5 * B * K.cot)
    ax.set_xlim(-sx - 0.06 * L, L + sx + 0.03 * L)
    ax.set_ylim(B + 0.12 * B + 0.3, -0.12 * B - 0.3)      # y dolů = pohled shora po směru x
    ax.set_aspect("equal")
    ax.set_xlabel("x [m] – podél mostu")
    ax.set_ylabel("y [m]")


def _geometrie_pudorysu(vys: VysledekSil):
    """Geometrie pruhů 2D modelu ve tvaru, který očekává plotting._pudorys_sil."""
    from types import SimpleNamespace
    m = vys.model
    return SimpleNamespace(K=vys.K, p_y0=m.p_y0, p_w=m.p_w, p_typ=m.p_typ,
                           p_xod=m.xs[m.p_i0], p_xdo=m.xs[m.p_i1], p_xsup=m.p_xsup)


def plot_stavy_pudorys(vys: VysledekSil, o: Optional[int] = None,
                       stavy: Optional[Sequence[str]] = None, show: bool = True,
                       sirka: float = 16.0, pomer: float = 2.0):
    """Vnitřní síly na nosnících v půdorysu (formát obálek BLC): pro každý zatěžovací
    stav jeden řádek – vlevo M, vpravo V; průběh vynesen od osy nosníku (kladné dolů),
    u proměnných stavů max červeně a min modře; posuzovaný výstup o zvýrazněn."""
    from .plotting import _pudorys_sil, _hladky, _rozsah, _meze
    geo = _geometrie_pudorysu(vys)
    V, xs = vys.vyst, vys.xs
    stavy = list(stavy or vys.stavy)
    jm, jv = vys.jednotky
    # výška řádku podle půdorysu (převýšení `pomer`, omezeno)
    x0, x1 = _meze(geo)
    w_ax = 0.5 * sirka - 0.8
    h_ax = float(np.clip(w_ax * pomer * 1.15 * vys.K.B / (x1 - x0), 2.6, 5.5))
    fig, axs = plt.subplots(len(stavy), 2, figsize=(sirka, len(stavy) * (h_ax + 0.9) + 0.6),
                            squeeze=False)
    for r, st in enumerate(stavy):
        s = vys.stavy[st]

        def rM(k, a=s.M_max):
            i0, i1 = _rozsah(V, k)
            return xs[i0:i1 + 1], a[k, i0:i1 + 1]

        def rV(k, vm=s.Vm_max, vp=s.Vp_max, vs=s.Vs_max):
            i0, i1 = _rozsah(V, k)
            return _hladky(xs, vm[k], vp[k], V.skoky[k], i0, i1, vs[k])

        rM2 = rV2 = None
        if s.pohyblivy:
            def rM2(k, a=s.M_min):
                i0, i1 = _rozsah(V, k)
                return xs[i0:i1 + 1], a[k, i0:i1 + 1]

            def rV2(k, vm=s.Vm_min, vp=s.Vp_min, vs=s.Vs_min):
                i0, i1 = _rozsah(V, k)
                return _hladky(xs, vm[k], vp[k], V.skoky[k], i0, i1, vs[k])
        for c, (velic, r1, r2, jed) in enumerate((("M", rM, rM2, jm), ("V", rV, rV2, jv))):
            ax = axs[r, c]
            _pudorys_sil(ax, geo, V, xs, r1, velic, velic, jed, zvyrazni=o, radky2=r2)
            obal = " – obálka (max červeně, min modře)" if s.pohyblivy else ""
            ax.set_title(f"{NAZVY_STAVU.get(st, st)}: {velic} [{jed}]{obal}", fontsize=9,
                         fontweight="bold")
            if r == len(stavy) - 1:
                ax.set_xlabel("x [m] (globální, ve směru osy prvku)")
            if c == 1:
                ax.set_ylabel("")
    fig.tight_layout()
    if show:
        plt.show()
    return fig


def plot_zatizeni_most(vys: VysledekSil, o: int, stav: str,
                       poloha: Optional[PolohaVozidla] = None, rezy=(), show: bool = True):
    """Samostatný graf půdorysu mostu se zatížením (viz kresli_most)."""
    fig, ax = plt.subplots(figsize=(10, 4.5))
    kresli_most(ax, vys, o, stav, poloha, rezy)
    if stav != "q":
        ax.set_title(NAZVY_STAVU.get(stav, stav))
    fig.tight_layout()
    if show:
        plt.show()
    return fig


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
        for y0, y1, pop in getattr(vys, "pruhy_q", []):          # zatěžovací pruhy (Vn)
            aR.add_patch(plt.Rectangle((y0, -0.5), y1 - y0, 0.4, fill=False, ec="#e74c3c", lw=0.8,
                                       ls="--"))
            aR.text(0.5 * (y0 + y1), -0.3, pop, ha="center", va="center", fontsize=6,
                    color="#e74c3c")
        stopy = getattr(vys, "stopy_q", None) or [
            (vys.y_Ve - 0.5 * vys.rozvor, vys.b_k), (vys.y_Ve + 0.5 * vys.rozvor, vys.b_k)]
        for yc, bk in stopy:
            aR.add_patch(plt.Rectangle((yc - 0.5 * bk, -0.45), bk, 0.3,
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
