"""
plotting_sily.py
================
Grafy vnitřních sil pro posudek (vnitrni_sily.VysledekSil):
  Síly se kreslí v CHARAKTERISTICKÝCH hodnotách – bez kombinačních, dílčích a dynamických
  součinitelů (q bez δ: vnitrni_sily.vys_charakteristicky) – pro kontrolu s jinými výpočty.
  plot_sily     průběhy M a V stavů g0, g − g0, q (obálka) na jednom výstupu,
  plot_pricne   příčné rozdělení: max M a max |V| stavů po výstupech + příčný řez
                (chodníky, vozovka, liniová zatížení, poloha vozidla),
  kresli_most   půdorys mostu se zatížením stavu g0, g − g0 nebo q v dané poloze
                (do zadané osy), plot_zatizeni_most – samostatný graf,
  kresli_pricny_rez  příčný řez s příčnou polohou zatížení dopravou (pruhy Vn, vozidlo
                Vr / Ve / MLC, stopy kol, kóty od kraje vozovky, posuzovaný nosník),
                plot_pricny_rez – samostatný graf.
"""

from __future__ import annotations
from .cisla import cz
import textwrap
from typing import Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon, Rectangle

from .vnitrni_sily import VysledekSil, NAZVY_STAVU, PolohaVozidla, vys_charakteristicky


def _nazev_stavu(st: str) -> str:
    return NAZVY_STAVU[st] + (" (bez δ)" if st == "q" else "") if st in NAZVY_STAVU else st

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
        if not vys.deska and vys.g_dobetonavky:
            for k in range(K.N - 1):
                y0 = K.y_nos[k] + 0.5 * K.b
                y1 = K.y_nos[k + 1] - 0.5 * K.b
                if y1 - y0 < 0.02:                       # nosníky na dotyk – vyznačit pruhem
                    y0, y1 = y0 - 0.04, y0 + 0.04
                ax.add_patch(Rectangle((min(K.x0(y0), K.x0(y1)), y0), L, y1 - y0,
                                       fc=BARVY["g0"], alpha=0.8, ec="none", lw=0))
        txt = (f"g0 = {cz(vys.g0, 2)} {jm}" +
               ("" if vys.deska else " – každý nosník samostatně (bez spolupůsobení)") +
               (f"\n+ dobetonávka {cz(vys.g_dobetonavky, 2)} kN/m (½ na sousední nosníky)"
                if vys.g_dobetonavky else ""))
        ax.text(K.x0(0.5 * B) + 0.5 * L, 0.5 * B, txt, ha="center", va="center", fontsize=9,
                bbox=dict(fc="white", ec="#888888", alpha=0.9))
    elif stav == "g-g0":
        for nazev, g, y0, y1 in vyb.zony(B):
            voz = "vozovka" in nazev
            _pas(ax, vys, y0, y1, fc="#555555" if voz else "#bbbbbb", alpha=0.45, ec="none")
            ym = 0.5 * (y0 + y1)
            ax.text(K.x0(ym) + 0.72 * L, ym, f"{nazev} {cz(g)} kN/m²", ha="center", va="center",
                    fontsize=7, color="w" if voz else "k")
        for l in vyb.liniova_vse(B):
            _pas(ax, vys, max(0.0, l.y - 0.5 * l.sirka), min(B, l.y + 0.5 * l.sirka),
                 fc=BARVY["g-g0"], alpha=0.85, ec="none")
            ax.text(K.x0(l.y) + 0.03 * L, l.y, f"{l.nazev} {cz(l.g)} kN/m", fontsize=6.5, va="center",
                    color=BARVY["g-g0"], bbox=dict(fc="white", ec="none", alpha=0.75, pad=1))
        if vys.g_spary:
            ax.text(K.x0(0.0) + L, -0.08 * B, f"výplň spáry {cz(vys.g_spary)} kN/m (samostatně)",
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
                       sirka: float = 16.0, pomer: float = 2.0,
                       o_stavu: Optional[dict] = None):
    """Vnitřní síly na nosnících v půdorysu (formát obálek BLC): pro každý zatěžovací
    stav jeden řádek – vlevo M, vpravo V; průběh vynesen od osy nosníku (kladné dolů),
    u proměnných stavů max červeně a min modře; posuzovaný výstup o zvýrazněn
    (o_stavu = {stav: výstup} – jiný zvýrazněný výstup pro daný řádek)."""
    from .plotting import _pudorys_sil, _hladky, _rozsah, _meze
    vys = vys_charakteristicky(vys)
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
            _pudorys_sil(ax, geo, V, xs, r1, velic, velic, jed,
                         zvyrazni=(o_stavu or {}).get(st, o), radky2=r2)
            obal = " – obálka (max červeně, min modře)" if s.pohyblivy else ""
            ax.set_title(f"{_nazev_stavu(st)}: {velic} [{jed}]{obal}", fontsize=9,
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
    """Průběhy M(x), V(x) stavů na výstupu o (0-based) – charakteristické hodnoty (q bez δ)."""
    vys = vys_charakteristicky(vys)
    jm, jv = vys.jednotky
    fig, (aM, aV) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True)
    for s in vys.stavy:
        t = vys.tabulka(o, s)
        c = BARVY.get(s, None)
        if vys.stavy[s].pohyblivy:
            aM.plot(t.x, t.M_max, c=c, label=f"{_nazev_stavu(s)} – max")
            aM.plot(t.x, t.M_min, c=c, ls="--", label=f"{_nazev_stavu(s)} – min")
            aV.plot(t.x, t.V_max, c=c)
            aV.plot(t.x, t.V_min, c=c, ls="--")
            aM.fill_between(t.x, t.M_min, t.M_max, color=c, alpha=0.08)
            aV.fill_between(t.x, t.V_min, t.V_max, color=c, alpha=0.08)
        else:
            aM.plot(t.x, t.M_max, c=c, label=_nazev_stavu(s))
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
                 f"(y = {cz(float(vys.vyst.y[o]), 2)} m) – charakteristické hodnoty bez součinitelů")
    fig.tight_layout()
    if show:
        plt.show()
    return fig


def plot_pricne(vys: VysledekSil, show: bool = True):
    """Max M a max |V| jednotlivých stavů po výstupech (charakteristické hodnoty, q bez δ)
    a příčný řez mostovkou; svislice = nejzatíženější výstup (výběr podle MSÚ 6.10)."""
    gov = vys.rozhodujici("M")
    vys = vys_charakteristicky(vys)
    jm, jv = vys.jednotky
    sh = vys.souhrn()
    y = np.array([d["y"] for d in sh])
    B = vys.K.B
    fig, (aR, aM, aV) = plt.subplots(3, 1, figsize=(10, 10), sharex=True,
                                     gridspec_kw={"height_ratios": [1.7, 2.2, 2.2]})
    kresli_pricny_rez(aR, vys, gov, rovne=False)
    aR.set_xlabel("")
    aR.set_title("Příčný řez – vybavení a poloha zatížení dopravou")
    for s in vys.stavy:
        aM.plot(y, [d[f"M_{s}"] for d in sh], "o-", c=BARVY.get(s), ms=3, label=_nazev_stavu(s))
        aV.plot(y, [d[f"V_{s}"] for d in sh], "o-", c=BARVY.get(s), ms=3)
    for a in (aM, aV):
        a.axvline(y[gov], c="#f39c12", lw=1.5, alpha=0.7)
        a.grid(alpha=0.3)
    aM.set_ylabel(f"max M [{jm}]")
    aV.set_ylabel(f"max |V| [{jv}]")
    aV.set_xlabel("y – příčná poloha osy výstupu [m]")
    aM.legend(fontsize=8)
    aM.set_title(f"Max. charakteristické hodnoty po {'pásech 1 m' if vys.deska else 'nosnících'} "
                 f"bez součinitelů (rozhoduje {vys.popisky[gov]})")
    aR.set_xlim(-0.2, B + 0.2)
    fig.tight_layout()
    if show:
        plt.show()
    return fig


# ---------------------------------------------------------------------------
# Příčný řez s příčnou polohou zatížení dopravou
# ---------------------------------------------------------------------------

def _kota(ax, y0: float, y1: float, z: float, barva: str = "#333333"):
    """Kóta mezi y0 a y1 ve výšce z (popis = vzdálenost [m])."""
    ax.annotate("", (y0, z), (y1, z), arrowprops=dict(arrowstyle="<->", color=barva, lw=0.7,
                                                      shrinkA=0, shrinkB=0))
    ax.text(0.5 * (y0 + y1), z + 0.03, f"{cz(y1 - y0, 2)}", ha="center", va="bottom", fontsize=6.5,
            color=barva)


def _retez_kot(ax, body, z: float, barva: str = "#333333"):
    """Řetězec kót přes body (y) ve výšce z, s vynášecími čárkami."""
    body = sorted({round(float(b), 4) for b in body})
    for a, b in zip(body[:-1], body[1:]):
        if b - a > 1e-3:
            _kota(ax, a, b, z, barva)
    for y in body:
        ax.plot([y, y], [z - 0.07, z + 0.07], color=barva, lw=0.7)


def popis_vozidla(vys: VysledekSil) -> str:
    """Popis vozidla s tíhami náprav (charakteristické hodnoty, bez δ)."""
    from . import schemata_zatizitelnosti as sz
    V = vys.V
    if vys.druh_q == "Vr":
        v = sz.VOZIDLA_VR[vys.schema_q]
        F = [a.podil * 10.0 * V for a in v.napravy]
        nap = (f"{len(F)} × {F[0]:.0f}" if max(F) - min(F) < 1e-9 else
               " + ".join(f"{f:.0f}" for f in F))
        return f"Vr = {cz(V, 1)} t – {v.nazev} ({v.obrazek})\nnápravy {nap} kN, šířka {cz(v.sirka)} m"
    if vys.druh_q == "Ve":
        return f"Ve = {cz(V, 1)} t – souprava (obr. 7.5)\nnápravy 9 × {10.0 * V / 9.0:.0f} kN, šířka 3 m"
    return vys.vozidlo


def _popis_pruhu(p: dict, vn: float) -> str:
    txt = p["nazev"]
    if p["naprava"]:
        F = 2.0 * p["F_kola"] * vn                                  # tíha nápravy [kN]
        txt += "\n" + ("2 × " if p["naprava"] == "dvojnaprava" else "") + f"{F:.0f} kN"
    q = p["q"]
    return txt + f"\n{cz(q)}·vn = {cz(q * vn, 2)} kN/m²"


def kresli_pricny_rez(ax, vys: VysledekSil, o: Optional[int] = None, rovne: bool = True):
    """Příčný řez mostovkou (do osy ax): nosníky (posuzovaný oranžově), chodníky, vozovka,
    zábradlí / svodidla a příčná poloha zatížení dopravou – pruhy schématu Vn s nápravami
    a rovnoměrným zatížením, nebo obrys vozidla Vr / Ve / MLC; stopy kol; řetězec kót
    (u Vn a Vr od kraje vozovky u užšího chodníku).  rovne = stejné měřítko os."""
    from . import schemata_zatizitelnosti as sz
    K, vyb = vys.K, vys.vybaveni
    B = K.B
    hn = float(K.h if vys.deska else K.h_ekv)
    t_ch, t_v, zt = 0.20, 0.08, 1.55
    cq, ct = BARVY["q"], "#a52a1a"
    # nosná konstrukce
    if vys.deska:
        ax.add_patch(Rectangle((0.0, -hn), B, hn, fc=C_NOSNIK, ec="#2e75b6", lw=0.8))
    else:
        for k, y in enumerate(K.y_nos):
            ax.add_patch(Rectangle((y - 0.5 * K.b, -hn), K.b, hn, fc=C_NOSNIK, ec="#2e75b6", lw=0.6))
            ax.text(y, -0.5 * hn, vys.popisky[k], ha="center", va="center", fontsize=6.5,
                    color="#2e75b6")
            if K.spara and k < K.N - 1:
                ax.add_patch(Rectangle((y + 0.5 * K.b, -0.3 * hn), K.b_s, 0.3 * hn, fc=C_SPARA,
                                       ec="#bbbbbb", lw=0.4))
    # vybavení
    w = vyb.sirka_vozovky(B)
    for y0, sir, nazev in ((0.0, vyb.chodnik_L, "chodník L"),
                           (B - vyb.chodnik_P, vyb.chodnik_P, "chodník P")):
        if sir > 0:
            ax.add_patch(Rectangle((y0, 0.0), sir, t_ch, fc="#cccccc", ec="#888888", lw=0.5))
            ax.text(y0 + 0.5 * sir, 0.5 * t_ch, f"{nazev} {cz(sir)} m", ha="center", va="center",
                    fontsize=5.5)
    ax.add_patch(Rectangle((vyb.chodnik_L, 0.0), w, t_v, fc="#555555", ec="none"))
    for l in vyb.liniova_vse(B):
        v = 1.0 if l.nazev.startswith("zábradlí") else 0.75 if l.nazev.startswith("svodidlo") else 0.3
        na_chodniku = l.y < vyb.chodnik_L or l.y > B - vyb.chodnik_P
        ax.add_patch(Rectangle((l.y - 0.5 * l.sirka, t_ch if na_chodniku else t_v), l.sirka, v,
                               fc="#2e75b6", ec="none", alpha=0.7))
    # pohyblivé zatížení
    body = [vyb.chodnik_L, B - vyb.chodnik_P]
    if "q" in vys.stavy:
        if vys.druh_q == "Vn":
            vn = sz.vn_z_Vn(vys.V)
            for p in vys.pruhy_q:
                y0, y1 = p["y0"], p["y1"]
                zb = p["nazev"].startswith("zbý")
                ax.add_patch(Rectangle((y0, t_v), y1 - y0, 0.1, fc=cq, alpha=0.12 if zb else 0.3,
                                       ec="none", hatch="///" if zb else None))
                ax.add_patch(Rectangle((y0, t_v), y1 - y0, 1.25, fill=False, ec=cq, lw=0.8,
                                       ls="--"))
                ax.text(0.5 * (y0 + y1), t_v + 0.75, _popis_pruhu(p, vn), ha="center",
                        va="center", fontsize=6.5, color=ct)
                body += [y0, y1]
        else:
            for y0, y1 in vys.obrys_q:
                ax.add_patch(Rectangle((y0, t_v + 0.3), y1 - y0, 0.95, fc=cq, alpha=0.12, ec=cq,
                                       lw=1.0))
                ax.text(0.5 * (y0 + y1), t_v + 0.78, popis_vozidla(vys), ha="center",
                        va="center", fontsize=6.5, color=ct)
                body += [y0, y1]
        for y, b in vys.stopy_q:
            ax.add_patch(Rectangle((y - 0.5 * b, t_v), b, 0.14, fc=cq, ec=ct, lw=0.5, alpha=0.9))
            body.append(y)
        if vys.druh_q in ("Vn", "Vr"):
            pp = sz.pricna_poloha(vyb.chodnik_L, vyb.chodnik_P, B)
            ax.plot([pp.y_kraj] * 2, [-hn, zt + 0.2], color=cq, lw=1.0, ls=":")
            ax.text(pp.y_kraj, zt + 0.25, f" kraj vozovky u užšího chodníku {pp.strana} ",
                    ha="right" if pp.strana == "P" else "left", va="bottom", fontsize=6.5, color=ct)
        else:
            ax.plot([vys.y_Ve] * 2, [t_v, zt + 0.2], color=cq, lw=0.8, ls="-.")
            ax.text(vys.y_Ve, zt + 0.25, f"osa vozidla y = {cz(vys.y_Ve, 2)} m", ha="center",
                    va="bottom", fontsize=6.5, color=ct)
    _retez_kot(ax, body, zt)
    # posuzovaný výstup
    if o is not None:
        yo = float(vys.vyst.y[o])
        wo = vys.vyst.sirka_okna if vys.deska else K.b
        ax.add_patch(Rectangle((yo - 0.5 * wo, -hn), wo, hn, fill=False, ec=C_POS, lw=2.2))
        ax.text(yo, -hn - 0.06, f"posuzovaný {vys.popisky[o]}", ha="center", va="top", fontsize=7,
                color=C_POS, fontweight="bold")
    ax.set_xlim(-0.3, B + 0.3)
    ax.set_ylim(-hn - 0.45, zt + 0.6)
    if rovne:
        ax.set_aspect("equal")
    ax.set_yticks([])
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("y [m] od levého okraje mostovky; kóty [m]")


def nadpis_pricneho_rezu(vys: VysledekSil) -> str:
    nad = f"Příčný řez – {vys.vozidlo}" if "q" in vys.stavy else "Příčný řez"
    if vys.poloha_q:
        nad += f", {vys.poloha_q}"
    if "q" in vys.stavy:
        nad += f"; δ = {cz(vys.dyn, 3, g=True)}" + (" (1 pruh; δ2, δ3 při více pruzích)"
                                        if vys.druh_q == "Vn" else "")
    if vys.q_ch:
        nad += f"; chodci {cz(vys.q_ch)} kN/m²"
    return nad


def plot_pricny_rez(vys: VysledekSil, o: Optional[int] = None, show: bool = True):
    """Samostatný graf příčného řezu s polohou zatížení dopravou."""
    B = vys.K.B
    fig, ax = plt.subplots(figsize=(min(max(7.0, 0.8 * B + 1.5), 16.0), 3.8))
    kresli_pricny_rez(ax, vys, o)
    ax.set_title(textwrap.fill(nadpis_pricneho_rezu(vys), 110), fontsize=9)
    fig.tight_layout()
    if show:
        plt.show()
    return fig
