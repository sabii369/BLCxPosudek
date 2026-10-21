"""
plotting.py  (v9)
=================
Grafy pro spojitý nosník / desku, kolmý i šikmý most.

  plot_obalky(cr)                     – 1D obálky M(x), V(x) celého mostu, MLC vs Ve
  plot_obalky_nosniky(cr, stav)       – 2D obálky M, V na každém nosníku / pásu 1 m
  plot_vyuziti_rezy(cr)               – využití MLC/Ve v každém kontrolním řezu
  plot_pricny_roznos(cr, i)           – hodnoty na nosnících / pásech ve vybraném řezu
  plot_profily_nosniky(cr, i, stav)   – M, V na nosnících + vedle Σ vs 1D statika
  plot_zatizeni(cr, i)                – poloha zatížení MLC a Ve v rozhodujícím stavu
                                        (pohled a půdorys)

Souřadnice: nosníky – x ve směru osy nosníků (globální rámec 2D modelu);
deska – ξ = vzdálenost od osy podpory měřená ve směru osy (výsledky podél čar
rovnoběžných s osou podpory).  Síly vždy ve směru osy prvku.
"""

from __future__ import annotations
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon

from .comparison import ComparisonResult
from .plate_fem import platky_z_naprav, posun

C_MLC = "#c0392b"
C_VE = "#2e75b6"
C_REZ = "#27ae60"


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------

def _vybrat(cr: ComparisonResult, i: Optional[int]):
    if i is None:
        return cr.rezy.index(cr.rozhodujici)
    return i


def _deska(cr) -> bool:
    return cr.K.je_deska


def _jm(cr, co="M"):
    if co == "M":
        return "kNm/m" if _deska(cr) else "kNm"
    return "kN/m" if _deska(cr) else "kN"


def _xlab(cr) -> str:
    if _deska(cr) and cr.K.sikmy:
        return "ξ [m] – vzdálenost od osy podpory 1 ve směru osy"
    return "x [m] (ve směru osy prvku)"


def _co(cr) -> str:
    return "pás 1 m" if _deska(cr) else "nosník"


def _podpory(ax, cr):
    """Osy podpor v rámci grafu (šikmé nosníky: rozsah poloh podpor nosníků)."""
    if cr.p_xsup is None or _deska(cr) or not cr.K.sikmy:
        for xp in cr.K.x_podpor:
            ax.axvline(xp, color="#555", lw=1.2, ls="-", alpha=0.6)
        return
    nos = cr.p_typ == "n"
    for j in range(cr.p_xsup.shape[1]):
        lo, hi = cr.p_xsup[nos, j].min(), cr.p_xsup[nos, j].max()
        ax.axvspan(lo, hi, color="#555", alpha=0.12, lw=0)


def _barvy(n):
    if n <= 10:
        cmap = plt.get_cmap("tab10"); return [cmap(k) for k in range(n)]
    if n <= 20:
        cmap = plt.get_cmap("tab20"); return [cmap(k) for k in range(n)]
    cmap = plt.get_cmap("viridis")
    return [cmap(k / max(n - 1, 1)) for k in range(n)]


def _rozsah(V, o):
    return int(V.i0[o]), int(V.i1[o])


def _hladky(xs, Vm, Vp, skoky, i0=0, i1=None, Vs=None):
    """
    Průběh V(x) pro graf v rozsahu uzlů i0 … i1.

    Uvnitř pole se kreslí průměr ½(V⁻ + V⁺) (rozdíl je jen diskretizační –
    smyk přenášený do sousedního pruhu je soustředěn do uzlů), skutečný skok
    se kreslí jen nad podporami (uzly `skoky`).
    """
    xs = np.asarray(xs)
    i1 = len(xs) - 1 if i1 is None else i1
    Vs = 0.5 * (Vm + Vp) if Vs is None else Vs
    sk = set(int(k) for k in skoky)
    X, V = [], []
    for k in range(i0, i1 + 1):
        if k == i0:
            X.append(xs[k]); V.append(Vp[k])
        elif k == i1:
            X.append(xs[k]); V.append(Vm[k])
        elif k in sk:
            X += [xs[k], xs[k]]; V += [Vm[k], Vp[k]]
        else:
            X.append(xs[k]); V.append(Vs[k])
    return np.array(X), np.array(V)


def _legenda(ax, n, **kw):
    if n <= 12:
        ax.legend(fontsize=6, ncol=max(1, n // 6), loc="upper right", **kw)


# ---------------------------------------------------------------------------
# Vnitřní síly v PŮDORYSU konstrukce: průběh vynesen od osy nosníku / pásu
# ---------------------------------------------------------------------------

def _podklad(ax, cr, svetle: bool = False):
    """Půdorys konstrukce (nosníky, spáry / deska, osy podpor)."""
    K = cr.K
    Lt, B = K.Ltot, K.B
    xmin, xmax = _meze(cr)
    ec = "#bbb" if svetle else "#999"
    if _deska(cr):
        pts = [[K.x0(0.0), 0.0], [K.x0(0.0) + Lt, 0.0], [K.x0(B) + Lt, B], [K.x0(B), B]]
        ax.add_patch(Polygon(pts, closed=True, facecolor="#f4f7fa" if svetle else "#eef3f8",
                             edgecolor="#666", lw=1, zorder=0))
        for xp in K.x_podpor:
            ax.plot([xp + K.x0(0.0), xp + K.x0(B)], [0, B], color="#555", lw=2.5, zorder=1)
    else:
        for s in range(len(cr.p_y0)):
            t = cr.p_typ[s]
            fc = "#e6e6e6" if t == "s" else ("#f4f7fa" if svetle else "#eef3f8")
            ax.add_patch(Rectangle((cr.p_xod[s], cr.p_y0[s]), cr.p_xdo[s] - cr.p_xod[s],
                                   cr.p_w[s], facecolor=fc, edgecolor=ec, lw=0.6, zorder=0))
            if t == "n":
                for xs_ in cr.p_xsup[s]:          # liniová podpora přes šířku nosníku
                    ax.plot([xs_, xs_], [cr.p_y0[s], cr.p_y0[s] + cr.p_w[s]],
                            color="#555", lw=2.5, zorder=1)
        if K.sikmy:
            for xp in K.x_podpor:
                ax.plot([xp + K.x0(0.0), xp + K.x0(B)], [0, B], color="#555", lw=0.8,
                        ls="-.", zorder=1)
    ax.set_xlim(xmin, xmax)


def _osy_vystupu(cr, V):
    """Které výstupy se v půdorysu kreslí a jejich rozteč (u desky pásy po 1 m)."""
    if not _deska(cr):
        return list(range(V.n)), cr.K.rozted
    B = cr.K.B
    stredy = np.arange(0.5, B, 1.0) if B >= 1.0 else np.array([0.5 * B])
    vyb = sorted(set(int(np.argmin(np.abs(V.y - yc))) for yc in stredy))
    return vyb, 1.0


def _x_glob(V, o, xs):
    if V.lokalni and V.x0_glob is not None:
        return xs + V.x0_glob[o]
    return xs


def _extremy(X, Y, rel=0.08, min_abs=1e-9):
    """Lokální extrémy průběhu (kladná maxima a záporná minima) s dostatečnou
    výrazností; vrací seznam indexů."""
    from scipy.signal import find_peaks
    Y = np.asarray(Y, float)
    if len(Y) < 3:
        return []
    ref = max(np.abs(Y).max(), min_abs)
    out = []
    for znam in (1.0, -1.0):
        Z = znam * Y
        # okraje doplníme, aby se našel i extrém na konci průběhu
        Zp = np.concatenate([[-np.inf], Z, [-np.inf]])
        pk, _ = find_peaks(Zp, prominence=rel * ref)
        for p in pk - 1:
            if Z[p] > rel * ref:
                out.append(int(p))
    # sloučit extrémy blízko sebe (na stejném místě po skoku)
    out = sorted(set(out), key=lambda k: X[k])
    vys = []
    for k in out:
        if vys and abs(X[k] - X[vys[-1]]) < 1e-6 and np.sign(Y[k]) == np.sign(Y[vys[-1]]):
            if abs(Y[k]) > abs(Y[vys[-1]]):
                vys[-1] = k
            continue
        vys.append(k)
    return vys


def _vynes(ax, X, Y, y0, meritko, barva, lw=1.0, alpha=0.35, popis=True, fs=6,
           tucne=False, zorder=3):
    """Průběh Y(X) vynesený od osy y0 (kladné hodnoty směrem dolů = −y)."""
    yy = y0 - meritko * Y
    ax.fill_between(X, y0, yy, color=barva, alpha=alpha, lw=0, zorder=zorder)
    ax.plot(X, yy, color=barva, lw=lw, zorder=zorder + 1)
    ax.plot([X[0], X[-1]], [y0, y0], color="#555", lw=0.6, ls="-.", zorder=zorder + 1)
    if not popis:
        return
    for k in _extremy(X, Y):
        ax.text(X[k], yy[k], f"{Y[k]:.2f}", ha="center",
                va="top" if Y[k] > 0 else "bottom", fontsize=fs,
                fontweight="bold" if tucne else "normal", color="k", zorder=zorder + 2,
                bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.7))


def _pudorys_sil(ax, cr, V, xs, radky, co, nazev, jed, zvyrazni=None, barva=C_MLC,
                 radky2=None, barva2=C_VE, x_rez=None):
    """
    radky: funkce o → (X, Y) průběh výstupu o (lokální xs).
    radky2: volitelně druhý průběh (obálka min) stejným měřítkem.
    """
    _podklad(ax, cr, svetle=True)
    vyb, rozt = _osy_vystupu(cr, V)
    if zvyrazni is not None and zvyrazni not in vyb:          # deska: rozhodující pás
        j = int(np.argmin([abs(V.y[o] - V.y[zvyrazni]) for o in vyb]))
        vyb[j] = zvyrazni
    data = {}
    for o in vyb:
        X, Y = radky(o)
        data[o] = [(_x_glob(V, o, X), Y)]
        if radky2 is not None:
            X2, Y2 = radky2(o)
            data[o].append((_x_glob(V, o, X2), Y2))
    # měřítko: kladná část nosníku k + záporná část sousedního nosníku se vejdou
    # do jedné rozteče → graf co nejvyšší, bez překrývání sousedních průběhů
    kl = max([np.nanmax(np.clip(Y, 0, None)) for d in data.values() for _, Y in d] + [0.0])
    za = max([np.nanmax(np.clip(-Y, 0, None)) for d in data.values() for _, Y in d] + [0.0])
    mer = 0.92 * rozt / max(kl + za, 1e-9)
    for o in vyb:
        gov = zvyrazni is not None and o == zvyrazni
        (X, Y) = data[o][0]
        _vynes(ax, X, Y, V.y[o], mer, barva, lw=1.6 if gov else 0.9,
               alpha=0.45 if gov else 0.3, tucne=gov, fs=7)
        if radky2 is not None:
            (X2, Y2) = data[o][1]
            _vynes(ax, X2, Y2, V.y[o], mer, barva2, lw=1.6 if gov else 0.9,
                   alpha=0.45 if gov else 0.3, tucne=gov, fs=7)
        ax.text(ax.get_xlim()[0], V.y[o], f" {V.popisky[o]}", ha="left", va="center",
                fontsize=7, fontweight="bold" if gov else "normal", color="#333")
    if x_rez is not None and zvyrazni is not None:
        ax.plot([x_rez], [V.y[zvyrazni]], marker="|", ms=18, mew=2, color=C_REZ, zorder=9)
    B = cr.K.B
    y_os = [V.y[o] for o in vyb]
    dole = min(min(y_os) - kl * mer, 0.0) - 0.08 * rozt
    nahore = max(max(y_os) + za * mer, B) + 0.08 * rozt
    ax.set_ylim(dole, nahore)
    ax.set_ylabel("y [m]")
    ax.set_title(f"{nazev} [{jed}] v půdorysu – průběh vynesen od osy "
                 f"{'pásu 1 m' if _deska(cr) else 'nosníku'} (kladné hodnoty dolů), "
                 "čísla = lokální extrémy", fontsize=9)
    ax.grid(alpha=0.2)


def _do_okna(fig, ax, pomer: float = 2.0, sirka: float = 16.0, max_vyska: float = 10.0):
    """Nastaví velikost okna tak, aby měřítko v y bylo `pomer`-krát větší než v x
    (b_vykr / L_vykr = pomer · b / L) – převýšení půdorysu pro čitelné průběhy."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    xr, yr = abs(x1 - x0), abs(y1 - y0)
    ml, mr, mt, mb = 0.75, 0.25, 0.75, 0.65          # okraje [palce]
    w_ax = sirka - ml - mr
    h_ax = w_ax * pomer * yr / xr
    h_max = max_vyska - mt - mb
    if h_ax > h_max:                                  # příliš vysoké → zúžit
        w_ax *= h_max / h_ax
        h_ax = h_max
    W, H = w_ax + ml + mr, h_ax + mt + mb
    fig.set_size_inches(W, H)
    ax.set_position([ml / W, mb / H, w_ax / W, h_ax / H])
    ax.set_aspect(pomer, adjustable="box")


# ---------------------------------------------------------------------------
# 1D obálky (celý most)
# ---------------------------------------------------------------------------

def plot_obalky(cr: ComparisonResult, show: bool = True):
    MLC, Ve = cr.MLC, cr.Ve
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    rM, rV = cr.res_MLC, cr.res_Ve
    a1.fill_between(rM.xs, rM.M_min, rM.M_max, color=C_MLC, alpha=0.18)
    a1.plot(rM.xs, rM.M_max, color=C_MLC, lw=1.4, label=f"{MLC}")
    a1.plot(rM.xs, rM.M_min, color=C_MLC, lw=1.4)
    a1.plot(rV.xs, rV.M_max, color=C_VE, lw=1.4, ls="--", label=f"Ve = {Ve:g} t")
    a1.plot(rV.xs, rV.M_min, color=C_VE, lw=1.4, ls="--")
    a1.invert_yaxis()
    a1.set_ylabel("M [kNm]")
    a1.set_title("1D obálky ohybového momentu – celý most (kladný moment dolů)")
    a1.legend(loc="best")
    a2.fill_between(rM.xs, rM.V_min, rM.V_max, color=C_MLC, alpha=0.18)
    a2.plot(rM.xs, rM.V_max, color=C_MLC, lw=1.4, label=f"{MLC}")
    a2.plot(rM.xs, rM.V_min, color=C_MLC, lw=1.4)
    a2.plot(rV.xs, rV.V_max, color=C_VE, lw=1.4, ls="--", label=f"Ve = {Ve:g} t")
    a2.plot(rV.xs, rV.V_min, color=C_VE, lw=1.4, ls="--")
    for x in rM.x_rezy_V:
        a2.axvline(x, color=C_REZ, lw=1, ls=":")
    a2.set_ylabel("V [kN]")
    a2.set_xlabel("x [m] (1D, v ose vozidla)")
    a2.set_title("1D obálky posouvající síly (zeleně kontrolní řezy ve vzdálenosti d od podpor)")
    a2.legend(loc="best")
    for a in (a1, a2):
        for xp in cr.K.x_podpor:
            a.axvline(xp, color="#555", lw=1.2, alpha=0.6)
        a.grid(alpha=0.3)
        a.axhline(0, color="k", lw=0.6)
    fig.tight_layout()
    if show:
        plt.show()
    return fig


# ---------------------------------------------------------------------------
# 2D obálky na jednotlivých nosnících / pásech
# ---------------------------------------------------------------------------

def plot_obalky_nosniky(cr: ComparisonResult, stav: str = "MLC", show: bool = True,
                        pomer: float = 2.0):
    """Obálky M a V na nosnících / pásech v půdorysu – dvě okna (M, V),
    převýšení v příčném směru `pomer`."""
    je_MLC = stav.upper() == "MLC"
    ob = cr.ob_MLC if je_MLC else cr.ob_Ve
    nazev = cr.MLC if je_MLC else f"Ve = {cr.Ve:g} t"
    if ob is None:
        raise ValueError("Obálky na nosnících nebyly spočítány (obalky=False).")
    V = ob.vyst
    jM, jV = _jm(cr, "M"), _jm(cr, "V")
    co = "pásy 1 m" if _deska(cr) else "jednotlivé nosníky"

    def rM_max(o):
        i0, i1 = _rozsah(V, o); sl = slice(i0, i1 + 1)
        return ob.xs[sl], ob.M_max[o, sl]

    def rM_min(o):
        i0, i1 = _rozsah(V, o); sl = slice(i0, i1 + 1)
        return ob.xs[sl], ob.M_min[o, sl]

    def rV_max(o):
        i0, i1 = _rozsah(V, o)
        return _hladky(ob.xs, ob.Vm_max[o], ob.Vp_max[o], V.skoky[o], i0, i1, ob.Vs_max[o])

    def rV_min(o):
        i0, i1 = _rozsah(V, o)
        return _hladky(ob.xs, ob.Vm_min[o], ob.Vp_min[o], V.skoky[o], i0, i1, ob.Vs_min[o])

    figs = []
    for velic, r1, r2, jed in (("M", rM_max, rM_min, jM), ("V", rV_max, rV_min, jV)):
        fig, ax = plt.subplots()
        fig.suptitle(f"Obálka {velic} – {co} – {nazev}  ({ob.n_stavu} poloh vozidla, 2D)",
                     fontsize=12, fontweight="bold")
        _pudorys_sil(ax, cr, V, ob.xs, r1, velic, f"Obálka {velic} (max červeně, min modře)",
                     jed, radky2=r2)
        ax.set_xlabel("x [m] (globální, ve směru osy prvku)")
        _do_okna(fig, ax, pomer)
        figs.append(fig)
    if show:
        plt.show()
    return tuple(figs)


# ---------------------------------------------------------------------------
# Využití po řezech, příčný roznos
# ---------------------------------------------------------------------------

def plot_vyuziti_rezy(cr: ComparisonResult, show: bool = True):
    n = len(cr.rezy)
    fig, ax = plt.subplots(figsize=(10, 0.55 * n + 1.6))
    y = np.arange(n)
    ax.barh(y + 0.2, [r.vyuziti_1D for r in cr.rezy], height=0.38,
            color="#b0b0b0", label="1D (celý most)")
    ax.barh(y - 0.2, [r.vyuziti_2D for r in cr.rezy], height=0.38,
            color=[C_MLC if r.vyuziti_2D >= 100 else C_REZ for r in cr.rezy],
            label="2D (" + ("nejvíc namáhaný pás 1 m)" if _deska(cr)
                          else "nejvíc namáhaný nosník)"))
    for yi, r in zip(y, cr.rezy):
        ax.text(max(r.vyuziti_2D, r.vyuziti_1D) + 1, yi, f"{r.vyuziti_2D:.0f} %",
                va="center", fontsize=8)
    ax.axvline(100, color="k", lw=1, ls="--")
    ax.set_yticks(y)
    ax.set_yticklabels([r.rez.id for r in cr.rezy], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel(f"Využití {cr.MLC} / Ve [%]")
    ax.set_title("Využití po kontrolních řezech")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    if show:
        plt.show()
    return fig


def plot_pricny_roznos(cr: ComparisonResult, i: Optional[int] = None, show: bool = True):
    i = _vybrat(cr, i)
    r = cr.rezy[i]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    if _deska(cr):
        yv = cr.vyst.y
        ax.plot(yv, r.MLC_nos, color=C_MLC, lw=1.8, marker=".", label=f"{cr.MLC}")
        ax.plot(yv, r.Ve_nos, color=C_VE, lw=1.8, marker=".", label=f"Ve = {cr.Ve:g} t")
        ax.set_xlabel("y – osa pásu 1 m [m]")
        ax.set_xlim(0, cr.K.B)
    else:
        N = cr.n_vyst
        x = np.arange(1, N + 1)
        w = 0.4
        b1 = ax.bar(x - w / 2, r.MLC_nos, w, color=C_MLC, label=f"{cr.MLC}")
        b2 = ax.bar(x + w / 2, r.Ve_nos, w, color=C_VE, label=f"Ve = {cr.Ve:g} t")
        for bars in (b1, b2):
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2, h, f"{h:.2f}",
                        ha="center", va="bottom", fontsize=6)
        ax.set_xticks(x)
        ax.set_xlabel("nosník")
    ax.set_ylabel(f"{'M' if r.rez.typ != 'V' else 'V'} [{r.jednotka}]")
    ax.set_title(f"{r.rez.id}: příčný roznos  –  využití {r.vyuziti_2D:.1f} % "
                 f"({cr.popisek(r.k_MLC)} / {cr.popisek(r.k_Ve)})")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    if show:
        plt.show()
    return fig


# ---------------------------------------------------------------------------
# Průběhy na nosnících / pásech + kontrola Σ vs statika (uspořádání jako ve v5)
# ---------------------------------------------------------------------------

def plot_profily_nosniky(cr: ComparisonResult, i: Optional[int] = None,
                         stav: str = "MLC", show: bool = True, pomer: float = 2.0):
    """M a V na nosnících / pásech 1 m v půdorysu pro rozhodující stav řezu i –
    dvě okna (M, V), převýšení v příčném směru `pomer`."""
    i = _vybrat(cr, i)
    r = cr.rezy[i]
    je_MLC = stav.upper() == "MLC"
    st = r.stav_MLC if je_MLC else r.stav_Ve
    nazev = cr.MLC if je_MLC else f"Ve = {cr.Ve:g} t"
    k_gov = r.k_MLC if je_MLC else r.k_Ve
    hodn = r.MLC_nos if je_MLC else r.Ve_nos
    V = st.vyst
    xs = st.xs
    jM, jV = _jm(cr, "M"), _jm(cr, "V")

    def rM(o):
        i0, i1 = _rozsah(V, o); sl = slice(i0, i1 + 1)
        return xs[sl], st.M[o, sl]

    def rV(o):
        i0, i1 = _rozsah(V, o)
        return _hladky(xs, st.Vm[o], st.Vp[o], V.skoky[o], i0, i1)

    xr = _x_rezu_glob(cr, r, je_MLC)
    figs = []
    for velic, fn, jed, barva, txt in (("M", rM, jM, C_MLC, "Ohybový moment M"),
                                       ("V", rV, jV, C_VE, "Posouvající síla V")):
        fig, ax = plt.subplots()
        fig.suptitle(f"{txt} – {nazev} – stav pro řez „{r.rez.id}“  –  rozhoduje "
                     f"{_co(cr)} {cr.popisek(k_gov)}: {hodn[k_gov - 1]:.2f} {r.jednotka}"
                     " (zeleně řez)", fontsize=12, fontweight="bold")
        _pudorys_sil(ax, cr, V, xs, fn, velic, txt, jed, zvyrazni=k_gov - 1,
                     barva=barva, x_rez=xr)
        ax.set_xlabel("x [m] (globální, ve směru osy prvku)")
        fig.text(0.99, 0.005, cr.popis, ha="right", va="bottom", fontsize=7, color="gray")
        _do_okna(fig, ax, pomer)
        figs.append(fig)
    if show:
        plt.show()
    return tuple(figs)


# ---------------------------------------------------------------------------
# Zatížení v rozhodujícím stavu (pohled + půdorys), globální rámec
# ---------------------------------------------------------------------------

def _viditelne(axles, xmin, xmax):
    return [(q, s, e) for q, s, e in axles if e > xmin and s < xmax]


def _meze(cr):
    K = cr.K
    x0s = [K.x0(0.0), K.x0(K.B)]
    lo = min(x0s) + 0.0
    hi = max(x0s) + K.Ltot
    okraj = 0.06 * (hi - lo)
    return lo - okraj, hi + okraj


def _x_rezu_glob(cr, r, je_MLC):
    """Poloha řezu rozhodujícího výstupu v globálním x (pro půdorys/pohled)."""
    xg = r.xg_MLC if je_MLC else r.xg_Ve
    if cr.vyst is not None and cr.vyst.lokalni and cr.vyst.x0_glob is not None:
        k = (r.k_MLC if je_MLC else r.k_Ve) - 1
        return xg + cr.vyst.x0_glob[k]
    return xg


def _kresli_pohled(ax, cr, axles, dx, y_voz, barva, x_rez, nazev):
    K = cr.K
    xmin, xmax = _meze(cr)
    ax_v = _viditelne(posun(axles, dx), xmin, xmax)
    qmax = max([q for q, s, e in ax_v] + [1.0])
    x_pod = [xp + K.x0(y_voz) for xp in K.x_podpor]
    ax.plot([x_pod[0], x_pod[-1]], [0, 0], color="k", lw=3, solid_capstyle="butt")
    h_tri, w_tri = 0.14 * qmax, 0.012 * (xmax - xmin) + 0.1
    for xk in x_pod:
        ax.add_patch(Polygon([[xk, 0], [xk - w_tri, -h_tri], [xk + w_tri, -h_tri]],
                             closed=True, color="#555"))
    for q, s, e in ax_v:
        ax.add_patch(Rectangle((s, 0.02 * qmax), e - s, q, color=barva, alpha=0.75, lw=0))
        ax.text(0.5 * (s + e), q + 0.05 * qmax, f"{q * (e - s):.2f}", ha="center",
                va="bottom", fontsize=6)
    ax.axvline(x_rez, color=C_REZ, lw=1.8, ls="--")
    ax.text(x_rez, 1.33 * qmax, " řez", color=C_REZ, fontsize=8, va="top")
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(-1.5 * h_tri, 1.4 * qmax)
    ax.set_ylabel("q [kN/m]")
    ax.set_title(f"{nazev}   (pohled v ose vozidla y = {y_voz:.2f} m; čísla = síla "
                 "nápravy/pásu [kN]; zeleně řez rozhodujícího prvku)", fontsize=9)
    ax.grid(alpha=0.25)


def _kresli_pudorys(ax, cr, axles, dx, y1, y2, b_k, barva, x_rez, y_pas=None):
    K = cr.K
    Lt, B = K.Ltot, K.B
    xmin, xmax = _meze(cr)
    if _deska(cr):
        pts = [[K.x0(0.0), 0.0], [K.x0(0.0) + Lt, 0.0], [K.x0(B) + Lt, B], [K.x0(B), B]]
        ax.add_patch(Polygon(pts, closed=True, facecolor="#eef3f8", edgecolor="#666", lw=1))
        for xp in K.x_podpor:
            ax.plot([xp + K.x0(0.0), xp + K.x0(B)], [0, B], color="#555", lw=2.5)
        if y_pas is not None:
            ax.add_patch(Rectangle((xmin, y_pas - 0.5), xmax - xmin, 1.0, facecolor="none",
                                   edgecolor=C_REZ, hatch="///", lw=0.8, alpha=0.6))
    else:
        for s in range(len(cr.p_y0)):
            t = cr.p_typ[s]
            ax.add_patch(Rectangle((cr.p_xod[s], cr.p_y0[s]), cr.p_xdo[s] - cr.p_xod[s],
                                   cr.p_w[s], facecolor="#d9d9d9" if t == "s" else "#eef3f8",
                                   edgecolor="#999", lw=0.6))
            if t == "n":
                yk = cr.p_y0[s] + 0.5 * cr.p_w[s]
                ax.plot([cr.p_xod[s], cr.p_xdo[s]], [yk] * 2, color="#9bb7d4", lw=0.8)
                k_n = int((cr.p_typ[:s] == "n").sum())
                ax.text(xmin + 0.005 * (xmax - xmin), yk, f"N{k_n + 1}", ha="left",
                        va="center", fontsize=6)
                for xs_ in cr.p_xsup[s]:          # liniová podpora přes šířku nosníku
                    ax.plot([xs_, xs_], [cr.p_y0[s], cr.p_y0[s] + cr.p_w[s]],
                            color="#555", lw=2.5)
        if K.sikmy:
            for xp in K.x_podpor:
                ax.plot([xp + K.x0(0.0), xp + K.x0(B)], [0, B], color="#555", lw=0.8,
                        ls="-.")
    ax_v = _viditelne(posun(axles, dx), xmin, xmax)
    for F, x0, x1, ya, yb in platky_z_naprav(ax_v, y1, y2, b_k, 0.0):
        ax.add_patch(Rectangle((x0, ya), x1 - x0, yb - ya, color=barva, alpha=0.8, lw=0))
    if cr.roz > 0:
        for F, x0, x1, ya, yb in platky_z_naprav(ax_v, y1, y2, b_k, cr.roz):
            ax.add_patch(Rectangle((x0, ya), x1 - x0, yb - ya, fill=False,
                                   edgecolor=barva, lw=0.7, ls="--"))
    ax.axvline(x_rez, color=C_REZ, lw=1.8, ls="--")
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(-0.05 * B, 1.05 * B)
    ax.set_ylabel("y [m]")
    ax.set_title("půdorys (plně kontaktní plochy, čárkovaně roznos do střednice desky"
                 + (", šedě spáry" if K.spara else "")
                 + (", šrafovaně rozhodující pás 1 m" if (_deska(cr) and y_pas is not None) else "")
                 + ")", fontsize=9)


def plot_zatizeni(cr: ComparisonResult, i: Optional[int] = None, show: bool = True):
    """Poloha zatížení MLC a Ve v nejnepříznivějším stavu pro řez i
    (i = None → rozhodující řez)."""
    i = _vybrat(cr, i)
    r = cr.rezy[i]
    fig, axs = plt.subplots(4, 1, figsize=(13, 10.5), sharex=True,
                            gridspec_kw=dict(height_ratios=[1.0, 1.1, 1.0, 1.1]))
    fig.suptitle(f"Zatížení v rozhodujícím stavu pro řez „{r.rez.id}“  –  "
                 f"využití 2D {r.vyuziti_2D:.1f} %  ({cr.popisek(r.k_MLC)} / "
                 f"{cr.popisek(r.k_Ve)})", fontsize=12, fontweight="bold")
    j = r.jednotka
    yM = 0.5 * (cr.y1_MLC + cr.y2_MLC)
    yV = 0.5 * (cr.y1_Ve + cr.y2_Ve)
    xM, xV = _x_rezu_glob(cr, r, True), _x_rezu_glob(cr, r, False)
    ypM = cr.vyst.y[r.k_MLC - 1] if _deska(cr) else None
    ypV = cr.vyst.y[r.k_Ve - 1] if _deska(cr) else None
    _kresli_pohled(axs[0], cr, r.axles_MLC, cr.dx_MLC, yM, C_MLC, xM,
                   f"{cr.MLC}: {r.MLC_2D:.2f} {j} ({_co(cr)} {cr.popisek(r.k_MLC)})")
    _kresli_pudorys(axs[1], cr, r.axles_MLC, cr.dx_MLC, cr.y1_MLC, cr.y2_MLC, cr.b_k_MLC,
                    C_MLC, xM, ypM)
    _kresli_pohled(axs[2], cr, r.axles_Ve, cr.dx_Ve, yV, C_VE, xV,
                   f"Ve = {cr.Ve:g} t: {r.Ve_2D:.2f} {j} ({_co(cr)} {cr.popisek(r.k_Ve)})")
    _kresli_pudorys(axs[3], cr, r.axles_Ve, cr.dx_Ve, cr.y1_Ve, cr.y2_Ve, cr.b_k_Ve,
                    C_VE, xV, ypV)
    axs[3].set_xlabel("x [m] (globální, ve směru osy prvku)")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    if show:
        plt.show()
    return fig


# ---------------------------------------------------------------------------
# Síť MKP
# ---------------------------------------------------------------------------

def plot_sit(cr: ComparisonResult, show: bool = True, pomer: float = 1.0,
             cisla: Optional[bool] = None):
    """
    Půdorys sítě 2D MKP: prvky (nosníky / spáry / deska), podepřené uzly
    (tuhé nebo pružné), podélné klouby mezi pruhy.

    pomer  – převýšení ve směru y (1 = skutečné měřítko)
    cisla  – číslovat nosníky (None = automaticky)
    """
    from matplotlib.collections import PolyCollection, LineCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    S = cr.sit
    if S is None:
        raise ValueError("Síť MKP není k dispozici (spusťte výpočet znovu).")
    K = cr.K
    ne = len(S.prvky)
    fig, ax = plt.subplots()
    verts = np.stack([S.X[S.prvky], S.Y[S.prvky]], axis=-1)
    barvy = {"n": "#dbe8f5", "s": "#d9d9d9", "d": "#dbe8f5"}
    lw = 0.5 if ne < 3000 else (0.3 if ne < 20000 else 0.15)
    ax.add_collection(PolyCollection(verts, facecolors=[barvy[t] for t in S.typ],
                                     edgecolors="#5b7a99", linewidths=lw, zorder=1))
    # klouby
    if S.klouby:
        ax.add_collection(LineCollection([[(x0, y), (x1, y)] for y, x0, x1 in S.klouby],
                                         colors="#c0392b", linewidths=1.2, zorder=3))
    # podpory
    xs_, ys_ = S.X[S.podpory], S.Y[S.podpory]
    pruzna = S.k_uzlu is not None
    ax.scatter(xs_, ys_, s=10 if len(xs_) < 400 else 4, marker="s",
               color="#e67e22" if pruzna else "k", zorder=4, linewidths=0)
    # osy podpor (šikmé)
    B = K.B
    for xp in K.x_podpor:
        ax.plot([xp + K.x0(0.0), xp + K.x0(B)], [0, B], color="#555", lw=0.8, ls="-.",
                zorder=2)
    # popisky nosníků
    if cisla is None:
        cisla = not K.je_deska
    if cisla and not K.je_deska and cr.p_typ is not None:
        n = 0
        for s in range(len(cr.p_typ)):
            if cr.p_typ[s] != "n":
                continue
            n += 1
            ax.text(cr.p_xod[s] - 0.15, cr.p_y0[s] + 0.5 * cr.p_w[s], f"N{n}", ha="right",
                    va="center", fontsize=7, color="#333")
    xmin, xmax = S.X[S.prvky].min(), S.X[S.prvky].max()
    ax.set_xlim(xmin - 0.04 * (xmax - xmin), xmax + 0.02 * (xmax - xmin))
    ax.set_ylim(-0.03 * B - 0.1, 1.03 * B + 0.1)
    ax.set_xlabel("x [m] (globální, ve směru osy prvku)")
    ax.set_ylabel("y [m]")
    n_uz = len(np.unique(S.prvky))
    pod_txt = "uložení: " + K.popis_ulozeni()
    ax.set_title(f"Síť MKP (MITC4, κ = {S.kappa:.3g}) – {ne} prvků, {n_uz} uzlů, {S.n_dof} DOF; "
                 f"prvek ≈ {S.a:.3f} × {S.c:.3f} m\n{pod_txt}", fontsize=10)
    leg = []
    if K.je_deska:
        leg.append(Patch(facecolor=barvy["d"], edgecolor="#5b7a99", label=f"deska h = {K.h:g} m"))
    else:
        leg.append(Patch(facecolor=barvy["n"], edgecolor="#5b7a99",
                         label=f"nosník (h_ekv = {K.h_ekv:.3f} m)"))
        if K.spara:
            leg.append(Patch(facecolor=barvy["s"], edgecolor="#5b7a99",
                             label=f"spára (h_s = {K.h_spary:.3f} m)"))
        if S.klouby:
            leg.append(Line2D([], [], color="#c0392b", lw=1.2, label="podélný kloub"))
    leg.append(Line2D([], [], color="#e67e22" if pruzna else "k", marker="s", ls="",
                      markersize=4, label="podepřený uzel" + (" (pružina)" if pruzna else "")))
    leg.append(Line2D([], [], color="#555", lw=0.8, ls="-.", label="osa podpory"))
    ax.legend(handles=leg, loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=8,
              frameon=False)
    _do_okna(fig, ax, pomer=pomer)
    W, H = fig.get_size_inches()
    pos = ax.get_position()
    fig.set_size_inches(W + 2.2, H)                  # místo pro legendu vpravo
    ax.set_position([pos.x0 * W / (W + 2.2), pos.y0, pos.width * W / (W + 2.2), pos.height])
    if show:
        plt.show()
    return fig
