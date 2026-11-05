"""
grafy_most.py
=============
Grafy zatížení mostu pro protokol a GUI spojeného programu.  Každý graf:
půdorys mostu se zatížením stavu (g0, g − g0, q v poloze pro max M ve středu
rozpětí a pro max V u podpory) a napětí v betonu po výšce průřezu posuzovaného
nosníku v řezu ve středu rozpětí a u podpory (ve vzdálenosti d od osy ložiska).

Napětí (tah +, tlak −) s předpětím P_m,t příslušné fáze posudku:
  g0       P_m0 (vnesení předpětí) + g0
  g − g0   P_m,t (vnesení ostatních stálých zatížení) + g0 + (g − g0)
  q        P_m,∞ (konec životnosti) + g0 + (g − g0) + q (charakteristická hodnota)
Plná čára = celkem, čárkovaně = jen daný stav, tečkovaně = stav před jeho vnesením.
Funkce mají tvar fn(model, adr) jako grafy Posudku PB (grafy._uloz): v protokolu
uloží PNG, v GUI (grafy.vracet_obrazky) vrátí obrázek.
"""

from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from blc.plotting_sily import kresli_most, BARVY
from pb_posudek import grafy

GRAFY = {  # klíč obrázku → (název v GUI / popisek v protokolu, stav, poloha vozidla)
    "blc_g0": ("Zatížení mostu – vlastní tíha g0", "g0", None),
    "blc_g": ("Zatížení mostu – ostatní stálé g − g0", "g-g0", None),
    "blc_qM": ("Zatížení mostu – q, max M ve středu rozpětí", "q", "M"),
    "blc_qV": ("Zatížení mostu – q, max V u podpory", "q", "V"),
}


def _faze(m, stav: str):
    """Fáze posudku, jejíž předpětí se kreslí se stavem."""
    if stav == "g0":
        return m.faze[0]
    if stav == "g-g0":
        stale = [f for f in m.faze if not f.provoz]
        return stale[-1]
    return m.faze[-1]


def rezy_posudku(m) -> dict:
    """{"stred": (index řezu posudku, x lokální), "podpora": (…)} – x lokální od osy ložiska."""
    b = m.blc
    x_V = b["polohy"]["V"].x if "V" in b["polohy"] else b["vys"].K.d
    iV = int(np.argmin(np.abs(m.x - (m.xa + x_V))))
    return {"stred": (m.im, float(m.x[m.im] - m.xa)), "podpora": (iV, float(m.x[iV] - m.xa))}


def _M_stavy(m, i: int, x_lok: float, poloha_q) -> dict:
    """Momenty stavů v řezu i posudku [kNm]: g0 (posudek), g − g0 a q (BLC)."""
    b = m.blc
    vys, o = b["vys"], b["o"]
    tg = vys.tabulka(o, "g-g0")
    out = {"g0": float(m.zs_g0.M_max[i]), "g-g0": float(np.interp(x_lok, tg.x, tg.M_max))}
    if poloha_q is not None:
        tq = vys.tabulka_stavu(o, poloha_q.stav)
        out["q"] = float(np.interp(x_lok, tq.x, tq.M_max))
    return out


def napeti_v_rezu(m, stav: str, i: int, x_lok: float, poloha_q=None) -> dict:
    """Napětí po výšce průřezu v řezu i: z [mm] a složky σ [MPa]."""
    P = m.prurez
    z = np.linspace(0.0, P.h, 60)
    f = _faze(m, stav)
    NP, MP, _ = m._sily_predpeti(f.sigma)
    Ms = _M_stavy(m, i, x_lok, poloha_q)
    s = {"P": m._napeti(z, NP[i], MP[i], 0.0, 0.0, idx=i),
         "g0": m._napeti(z, 0.0, 0.0, Ms["g0"], 0.0, idx=i)}
    for k in ("g-g0", "q"):
        if k in Ms:
            s[k] = m._napeti(z, 0.0, 0.0, 0.0, Ms[k], idx=i)
    return dict(z=z, slozky=s, M=Ms, faze=f.nazev)


def _kresli_napeti(ax, m, stav, i, x_lok, poloha_q, nadpis):
    d = napeti_v_rezu(m, stav, i, x_lok, poloha_q)
    z, s = d["z"], d["slozky"]
    poradi = ["P", "g0", "g-g0", "q"]
    posl = {"g0": "g0", "g-g0": "g-g0", "q": "q"}[stav]
    pred = sum(s[k] for k in poradi[:poradi.index(posl)])
    celk = pred + s[posl]
    c = BARVY[stav]
    ax.plot(pred, z, color="#7f7f7f", lw=1.0, ls=":", label="před vnesením stavu")
    ax.plot(s[posl], z, color=c, lw=1.2, ls="--", label=f"jen {posl}")
    ax.plot(celk, z, color=c, lw=2.2, label="celkem")
    ax.axvline(0, color="#52514e", lw=0.8)
    fck = m.beton.fck
    ax.axvline(-0.6 * fck, color=grafy.BAD, lw=1.0, ls="--")
    ax.axvline(m.beton.fctm, color=grafy.BAD, lw=1.0, ls="--")
    for zz, va in ((z[-1], "top"), (z[0], "bottom")):
        v = float(np.interp(zz, z, celk))
        ax.annotate(f"{v:.2f}", (v, zz), fontsize=8, ha="center", va=va, color=c,
                    xytext=(0, -2 if va == "top" else 2), textcoords="offset points")
    ax.set_ylim(0, z[-1])
    ax.set_xlabel("σ_c [MPa] (tah +)")
    ax.set_title(f"{nadpis}: x = {m.x[i]:.2f} m, M_{posl} = {d['M'][posl]:.1f} kNm\n"
                 f"P_m,t: {d['faze']}", fontsize=8.5)
    return ax


def graf_stavu(m, klic: str):
    """Obrázek pro klíč z GRAFY (půdorys + napětí ve středu a u podpory)."""
    b = getattr(m, "blc", None)
    if not b:
        return None
    nazev, stav, ucel = GRAFY[klic]
    pol = b["polohy"].get(ucel) if ucel else None
    if stav == "q" and pol is None:
        return None
    vys, o = b["vys"], b["o"]
    rz = rezy_posudku(m)
    K = vys.K
    w0 = float(np.clip(0.95 * (K.Ltot + abs(K.B * K.cot)) / K.B, 1.1, 2.8))
    fig = plt.figure(figsize=(4.2 * w0 + 7.2, 4.6))
    gs = GridSpec(1, 3, width_ratios=[w0, 1, 1], figure=fig)
    ax = fig.add_subplot(gs[0])
    kresli_most(ax, vys, o, stav, pol, rezy=[(rz["stred"][1], "střed"), (rz["podpora"][1], "podpora")])
    if stav != "q":
        ax.set_title(nazev.split("– ", 1)[1], fontsize=9)
    a1 = fig.add_subplot(gs[1])
    _kresli_napeti(a1, m, stav, *rz["stred"], pol, "Střed rozpětí")
    a1.set_ylabel("z [mm] (od spodu)")
    a2 = fig.add_subplot(gs[2], sharey=a1)
    _kresli_napeti(a2, m, stav, *rz["podpora"], pol, "U podpory")
    a2.legend(fontsize=7, loc="lower right", framealpha=0.9)
    fig.suptitle(f"{nazev} – {'pás' if vys.deska else 'nosník'} {vys.popisky[o]}", fontsize=11)
    return fig


def _fn(klic):
    def fn(m, adr):
        fig = graf_stavu(m, klic)
        return None if fig is None else grafy._uloz(fig, adr, klic)
    fn.__name__ = klic
    return fn


FUNKCE = {k: _fn(k) for k in GRAFY}


def vykresli_most(m, adr) -> dict:
    """Uloží grafy zatížení mostu (PNG) – {klíč: soubor}."""
    out = {}
    for k, fn in FUNKCE.items():
        r = fn(m, adr)
        if r:
            out[k] = r
    return out
