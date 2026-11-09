"""
grafy_most.py
=============
Grafy spojeného programu pro protokol a GUI (tvar fn(model, adr) jako grafy
Posudku PB – grafy._uloz: v protokolu uloží PNG, v GUI vrátí obrázek).

Kapitola zatížení (Zatížení z modelu mostu (BLC)):
  blc_zat_stale   půdorys mostu – vlastní tíha g0 | ostatní stálé g − g0
  blc_zat_q       půdorys mostu – vozidlo v poloze pro max M ve středu rozpětí |
                  pro max V u podpory (řez d od osy ložiska)

Kapitola napětí v betonu (pod graf „Napětí v krajních vláknech po délce – fáze“):
  blc_rez_<i>     napětí po výšce průřezu ve středu rozpětí a u podpory pro fázi i –
                  stejné kombinace a obálka P_sup/P_inf jako graf po délce
                  (σ je po výšce lineární: σ(z) = σ_d + (σ_h − σ_d)·z/h).
"""

from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt

from blc.plotting_sily import kresli_most
from pb_posudek import grafy
from pb_posudek.zatizeni import NAZVY_KOMBINACI

GRAFY_ZATIZENI = {
    "blc_zat_stale": "Zatížení na mostě – vlastní tíha g0 a ostatní stálé g − g0",
    "blc_zat_q": "Zatížení na mostě – vozidlo v poloze pro max M ve středu rozpětí a max V u podpory",
}
NAZEV_REZY = "Napětí v řezech"
GRAF_SILY = ("blc_sily", "Vnitřní síly na nosnících od jednotlivých zatěžovacích stavů v půdorysu – "
                         "vlevo M, vpravo V; posuzovaný nosník zvýrazněn, u proměnných obálka max/min")


def rezy_posudku(m) -> dict:
    """{"stred": (index řezu posudku, x lokální), "podpora": (…)}; x lokální od osy ložiska,
    podpora = řez posudku nejbližší vzdálenosti d (rozhodující řez V v modelu mostu)."""
    b = getattr(m, "blc", None) or {}
    pol = b.get("polohy", {})
    x_V = pol["V"].x if "V" in pol else (b["vys"].K.d if "vys" in b else 0.0)
    iV = int(np.argmin(np.abs(m.x - (m.xa + x_V))))
    if iV == m.ia and len(m.x) > m.ia + 1:
        iV = m.ia + 1                               # ne přímo v ose ložiska
    return {"stred": (m.im, float(m.x[m.im] - m.xa)), "podpora": (iV, float(m.x[iV] - m.xa))}


# ---------------------------------------------------------------------------
# Zatížení na mostě
# ---------------------------------------------------------------------------

def _velikost_panelu(vys) -> tuple:
    K = vys.K
    w = K.Ltot + abs(K.B * K.cot)
    a = float(np.clip(w / (K.B * 1.3 + 0.6), 0.8, 3.5))
    return 3.6 * a + 1.0, 3.9


def graf_zatizeni(m, klic: str):
    b = getattr(m, "blc", None)
    if not b:
        return None
    vys, o, pol = b["vys"], b["o"], b["polohy"]
    rz = rezy_posudku(m)
    rezy = [(rz["stred"][1], "střed"), (rz["podpora"][1], "podpora")]
    if klic == "blc_zat_stale":
        panely = [("g0", None, "vlastní tíha g0"), ("g-g0", None, "ostatní stálé g − g0")]
    else:
        panely = [("q", pol.get(k), None) for k in ("M", "V") if k in pol]
        if not panely:
            return None
    w, h = _velikost_panelu(vys)
    fig, axs = plt.subplots(1, len(panely), figsize=(w * len(panely), h), squeeze=False)
    for ax, (stav, p, nadpis) in zip(axs[0], panely, strict=False):
        kresli_most(ax, vys, o, stav, p, rezy)
        if nadpis:
            ax.set_title(nadpis, fontsize=9)
    return fig


def graf_sil(m):
    """Vnitřní síly na nosnících v půdorysu (formát obálek BLC): řádek = zatěžovací stav,
    vlevo M, vpravo V; posuzovaný nosník zvýrazněn."""
    from blc.plotting_sily import plot_stavy_pudorys
    b = getattr(m, "blc", None)
    if not b:
        return None
    return plot_stavy_pudorys(b["vys"], b["o"], show=False)


def fn_sily(m, adr):
    fig = graf_sil(m)
    return None if fig is None else grafy._uloz(fig, adr, GRAF_SILY[0])


# ---------------------------------------------------------------------------
# Napětí v řezech (fáze posudku)
# ---------------------------------------------------------------------------

def profily_faze(m, idx: int, i: int) -> dict:
    """{kombinace: (z, σ_min(z), σ_max(z))} v řezu i pro fázi idx – obálka variant
    P_sup/P_inf × M_max/M_min z m.msp_napeti (σ lineární mezi krajními vlákny)."""
    f = m.faze[idx]
    h = m.prurez.h
    z = np.linspace(0.0, h, 41)
    out = {}
    for druh, var in m.msp_napeti[f.nazev].items():
        prof = np.array([sd[i] + (sh[i] - sd[i]) * z / h for sh, sd in var.values()])
        out[druh] = (z, prof.min(0), prof.max(0))
    return out


def graf_napeti_rezu(m, idx: int):
    if not getattr(m, "msp_napeti", None) or idx >= len(m.faze):
        return None
    f = m.faze[idx]
    b, nn = m.beton, m.n
    rz = rezy_posudku(m)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.0), sharey=True)
    fck = b.fck_t(f.t)
    k_tl = nn.k_predpeti if idx == 0 else nn.k1
    ft = m._mez_tahu(nn.tah_provoz if f.provoz else nn.tah_predpeti, f.t)
    for ax, (klic, nazev) in zip(axs, (("stred", "střed rozpětí"), ("podpora", "u podpory"))):
        i, x_lok = rz[klic]
        krajni = []
        for ci, (druh, (z, lo, hi)) in enumerate(profily_faze(m, idx, i).items()):
            c = grafy.C[ci]
            ax.fill_betweenx(z, lo, hi, color=c, alpha=0.25, lw=0)
            ax.plot(lo, z, color=c, lw=1.4, label=NAZVY_KOMBINACI[druh])
            ax.plot(hi, z, color=c, lw=1.4)
            krajni.append((lo[[0, -1]], hi[[0, -1]]))
        # obálka všech kombinací v krajních vláknech: min vlevo, max vpravo
        for j, (zz, va, dy) in enumerate(((z[0], "bottom", 3), (z[-1], "top", -3))):
            vmin = min(float(a[j]) for a, _ in krajni)
            vmax = max(float(b_[j]) for _, b_ in krajni)
            for v, ha, dx in ((vmin, "right", -3), (vmax, "left", 3)):
                ax.annotate(f"{v:.2f}", (v, zz), xytext=(dx, dy), textcoords="offset points",
                            fontsize=8, ha=ha, va=va, color=grafy.INK)
                ax.plot([v], [zz], "o", color=grafy.INK, ms=3)
        ax.axvline(-k_tl * fck, color=grafy.BAD, ls="--", lw=1.2)
        ax.text(-k_tl * fck, z[-1] * 0.5, f" −{k_tl}·f_ck(t)", rotation=90, va="center",
                fontsize=8, color=grafy.BAD)
        if f.provoz:
            ax.axvline(-nn.k2 * fck, color=grafy.WARN, ls="--", lw=1.2)
            ax.text(-nn.k2 * fck, z[-1] * 0.5, f" −{nn.k2}·f_ck", rotation=90, va="center",
                    fontsize=8, color=grafy.INK2)
        ax.axvline(ft, color=grafy.BAD, ls="--", lw=1.2)
        ax.text(ft, z[-1] * 0.5, " mez tahu", rotation=90, va="center", fontsize=8, color=grafy.BAD)
        ax.axvline(0, color=grafy.INK2, lw=0.8)
        ax.set_ylim(0, z[-1])
        ax.set(title=f"{nazev} – x = {m.x[i]:.2f} m", xlabel="σ_c [MPa] (tah +, tlak −)")
    axs[0].set_ylabel("z [mm] (od spodního okraje)")
    axs[0].legend(fontsize=8, loc="lower left")
    fig.suptitle(f"Napětí v řezech – {f.nazev} (t = {f.t:.0f} d), obálka P_sup/P_inf", fontsize=10,
                 fontweight="bold", color=grafy.INK)
    return fig


# ---------------------------------------------------------------------------
# Funkce ve tvaru grafů posudku
# ---------------------------------------------------------------------------

def _fn_zat(klic):
    def fn(m, adr):
        fig = graf_zatizeni(m, klic)
        return None if fig is None else grafy._uloz(fig, adr, klic)
    fn.__name__ = klic
    return fn


def fn_rez(idx: int):
    def fn(m, adr):
        fig = graf_napeti_rezu(m, idx)
        return None if fig is None else grafy._uloz(fig, adr, f"blc_rez_{idx}")
    fn.__name__ = f"blc_rez_{idx}"
    return fn


FUNKCE_ZATIZENI = {k: _fn_zat(k) for k in GRAFY_ZATIZENI}


def seznam_grafu(m) -> dict:
    """{název grafu v GUI: fn} – zatížení mostu a napětí v řezech všech fází."""
    out = {}
    if getattr(m, "blc", None):
        for k, nazev in GRAFY_ZATIZENI.items():
            if k != "blc_zat_q" or m.blc["polohy"]:
                out[nazev.replace("Zatížení na mostě – ", "Zatížení mostu – ")] = FUNKCE_ZATIZENI[k]
        out["Zatížení mostu – vnitřní síly na nosnících"] = fn_sily
    for idx, f in enumerate(getattr(m, "faze", [])):
        out[f"{NAZEV_REZY} – {f.nazev}"] = fn_rez(idx)
    return out


def vykresli_most(m, adr) -> dict:
    """Uloží všechny grafy spojeného programu (PNG) – {klíč: soubor}."""
    out = {}
    for k, fn in list(FUNKCE_ZATIZENI.items()) + [(GRAF_SILY[0], fn_sily)]:
        r = fn(m, adr)
        if r:
            out[k] = r
    for idx in range(len(m.faze)):
        r = fn_rez(idx)(m, adr)
        if r:
            out[f"blc_rez_{idx}"] = r
    return out


def vloz_do_protokolu(m) -> None:
    """Napětí v řezech pod graf napětí v krajních vláknech každé fáze (obrázky kapitoly
    zatížení vkládá vypocet.kapitola_blc)."""
    from pb_posudek.protokol import Obrazek, fmt
    rz = rezy_posudku(m)
    xs, xp = fmt(m.x[rz["stred"][0]]), fmt(m.x[rz["podpora"][0]])
    for kap in m.protokol.kapitoly:
        for idx, f in enumerate(m.faze):
            klic = f"napeti_{idx}"
            for j, (typ, obj) in enumerate(kap.polozky):
                if typ == "obrazek" and isinstance(obj, Obrazek) and obj.soubor == klic:
                    kap.polozky.insert(j + 1, ("obrazek", Obrazek(
                        f"blc_rez_{idx}",
                        f"Napětí po výšce průřezu v řezu ve středu rozpětí (x = {xs} m) a u podpory "
                        f"(x = {xp} m) – {f.nazev}, obálka P_sup/P_inf")))
                    break
