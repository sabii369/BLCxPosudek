"""
grafy_most.py
=============
Grafy spojeného programu pro protokol a GUI (tvar fn(model, adr) jako grafy
Posudku PB – grafy._uloz: v protokolu uloží PNG, v GUI vrátí obrázek).

Kapitola zatížení (Zatížení z modelu mostu (BLC)):
  blc_zat_stale   půdorys mostu – vlastní tíha g0 | ostatní stálé g − g0
  blc_zat_q       půdorys mostu – vozidlo v poloze pro max M ve středu rozpětí |
                  pro max V u podpory (řez d od osy ložiska)
  blc_zat_pricny  příčný řez – příčná poloha zatížení dopravou (pruhy Vn, vozidlo, kóty)

Kapitola zatížení – při výpočtu zatížitelnosti navíc (referenční tíhy Vn, Vr, Ve z [blc];
  graf sil blc_sily má místo řádku q řádky referenčních souprav):
  blc_zat_<druh>     půdorys – zatížení v poloze pro max M ve středu a max V u podpory
  blc_pricny_<druh>  příčný řez s polohou zatížení

Kapitola napětí v betonu (pod graf „Napětí v krajních vláknech po délce – fáze“):
  blc_rez_<i>     napětí po výšce průřezu ve středu rozpětí a u podpory pro fázi i –
                  stejné kombinace a obálka P_sup/P_inf jako graf po délce
                  (σ je po výšce lineární: σ(z) = σ_d + (σ_h − σ_d)·z/h).
"""

from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt

from blc.plotting_sily import kresli_most, plot_pricny_rez
from pb_posudek import grafy
from pb_posudek.zatizeni import NAZVY_KOMBINACI

GRAFY_ZATIZENI = {
    "blc_zat_stale": "Zatížení na mostě – vlastní tíha g0 a ostatní stálé g − g0",
    "blc_zat_q": "Zatížení na mostě – vozidlo v poloze pro max M ve středu rozpětí a max V u podpory",
    "blc_zat_pricny": "Zatížení na mostě – příčný řez s příčnou polohou zatížení dopravou",
}
GRAFY_Q = ("blc_zat_q", "blc_zat_pricny")       # jen je-li zatížení dopravou
NAZEV_REZY = "Napětí v řezech"
GRAF_SILY = ("blc_sily", "Vnitřní síly na nosnících od jednotlivých zatěžovacích stavů v půdorysu – "
                         "vlevo M, vpravo V; posuzovaný nosník zvýrazněn, u proměnných obálka max/min; "
                         "zatížení dopravou bez dynamického součinitele δ")


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
    if klic == "blc_zat_pricny":
        return plot_pricny_rez(vys, o, show=False) if "q" in vys.stavy else None
    rz = rezy_posudku(m)
    rezy = [(rz["stred"][1], "střed"), (rz["podpora"][1], "podpora")]
    return _panely_zatizeni(vys, o, pol, rezy, klic)


def _panely_zatizeni(vys, o, pol, rezy, klic):
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


def q_bez_dyn(vys):
    """Stav q bez dynamického součinitele (δ = 1) – viz blc.vnitrni_sily.vys_charakteristicky."""
    from blc.vnitrni_sily import vys_charakteristicky
    return vys_charakteristicky(vys).stavy.get("q")


def graf_sil(m):
    """Vnitřní síly na nosnících v půdorysu (formát obálek BLC): řádek = zatěžovací stav,
    vlevo M, vpravo V; posuzovaný nosník zvýrazněn; zatížení dopravou BEZ dynamického
    součinitele.  Při výpočtu zatížitelnosti je místo řádku q (zatížení dopravou při
    zatížitelnosti) po řádku obálka od každé referenční soupravy Vn, Vr, Ve se zvýrazněným
    nosníkem posuzovaným pro daný druh."""
    import copy
    from blc.plotting_sily import plot_stavy_pudorys
    from blc_posudek.zatizitelnost import POPIS_SCHEMAT
    b = getattr(m, "blc", None)
    if not b:
        return None
    vys = copy.copy(b["vys"])
    vys.stavy = {k: s for k, s in b["vys"].stavy.items() if k != "q"}
    o_stavu = {}
    res = getattr(m, "zatizitelnost", None)
    if res is None or not res.druhy:
        if "q" in b["vys"].stavy:
            vys.stavy[f"zatížení dopravou q – {b['vys'].vozidlo}, bez δ"] = q_bez_dyn(b["vys"])
        return plot_stavy_pudorys(vys, b["o"], list(vys.stavy), show=False)
    # chodci: protokol pro Ve je nemá (čl. 3.1.4) – vzít z druhu, který je zahrnuje (Vn, Vr)
    s_ch = {d: z.vys_ref() for d, z in res.druhy.items() if "qch" in z.vys_ref().stavy}
    vys.stavy.pop("qch", None)
    if s_ch:
        v = next(iter(s_ch.values()))
        bez = [d for d in res.druhy if d not in s_ch]
        nazev = (f"zatížení chodců q_ch = {v.q_ch:g} kN/m² (s {', '.join(s_ch)}"
                 + (f"; s {', '.join(bez)} chodci nejsou" if bez else "") + ")")
        vys.stavy[nazev] = v.stavy["qch"]
    for druh, z in res.druhy.items():
        v = z.vys_ref()
        sch = POPIS_SCHEMAT[v.schema_q or ""].split(" (")[0].split(" v pruzích")[0]
        nazev = f"{druh} = {v.V:g} t ({sch}, bez δ), posuzovaný {v.popisky[z.o]}"
        vys.stavy[nazev] = q_bez_dyn(v)
        o_stavu[nazev] = z.o
    return plot_stavy_pudorys(vys, b["o"], list(vys.stavy), show=False, o_stavu=o_stavu)


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


# ---------------------------------------------------------------------------
# Zatížení druhů zatížitelnosti (Vn, Vr, Ve) – kapitola zatížitelnosti
# ---------------------------------------------------------------------------

def druhy_zatizitelnosti(m) -> list:
    res = getattr(m, "zatizitelnost", None)
    return list(res.druhy) if res is not None else []


def graf_zatizitelnosti(m, druh: str, typ: str):
    """typ "pudorys" – zatížení druhu při referenční tíze v poloze pro max M ve středu
    a max V u podpory posuzovaného nosníku; "pricny" – příčný řez s polohou zatížení."""
    res = getattr(m, "zatizitelnost", None)
    if res is None or druh not in res.druhy:
        return None
    z = res.druhy[druh]
    vys, o = z.vys_ref(), z.o
    if typ == "pricny":
        return plot_pricny_rez(vys, o, show=False)
    pol = z.polohy_ref()
    if not pol:
        return None
    rezy = [(pol["M"].x, "střed"), (pol["V"].x, "podpora")] if "V" in pol else []
    return _panely_zatizeni(vys, o, pol, rezy, "blc_zat_q")


def fn_zatizitelnost(druh: str, typ: str):
    klic = f"blc_{'zat' if typ == 'pudorys' else 'pricny'}_{druh}"

    def fn(m, adr):
        fig = graf_zatizitelnosti(m, druh, typ)
        return None if fig is None else grafy._uloz(fig, adr, klic)
    fn.__name__ = klic
    return fn


def seznam_grafu(m) -> dict:
    """{název grafu v GUI: fn} – zatížení mostu a napětí v řezech všech fází."""
    out = {}
    if getattr(m, "blc", None):
        for k, nazev in GRAFY_ZATIZENI.items():
            if k not in GRAFY_Q or m.blc["polohy"]:
                out[nazev.replace("Zatížení na mostě – ", "Zatížení mostu – ")] = FUNKCE_ZATIZENI[k]
        out["Zatížení mostu – vnitřní síly na nosnících"] = fn_sily
    for druh in druhy_zatizitelnosti(m):
        out[f"Zatížitelnost {druh} – zatížení na mostě (referenční)"] = fn_zatizitelnost(druh,
                                                                                       "pudorys")
        out[f"Zatížitelnost {druh} – příčný řez (referenční)"] = fn_zatizitelnost(druh, "pricny")
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
    for druh in druhy_zatizitelnosti(m):
        for typ in ("pudorys", "pricny"):
            fn = fn_zatizitelnost(druh, typ)
            r = fn(m, adr)
            if r:
                out[fn.__name__] = r
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
