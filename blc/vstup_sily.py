"""
vstup_sily.py
=============
Výpočet vnitřních sil pro posudek ze vstupního souboru TOML / JSON
(python -m blc --sily vstup.toml).  Vzor: priklady/sily_KA67_12.toml.

Sekce:
  [konstrukce]   typ_konstrukce, prefabrikat, L, N, b, Iy, h, beton, nu, d, spara, b_s, Iy_s,
                 beton_s, alfa, sikmost, k_v [MN/m na 1 m podpory; 0 = tuhá], uloz,
                 k_rot [MNm/rad na 1 m; prázdné = dokonalé], spoj, beta_s_pevne
  [stale]        A_nosniku [m²] nebo g0, gamma_beton, g_spary, chodnik_L, chodnik_P,
                 g_chodnik [kN/m²], g_vozovka [kN/m²], g_zabradli, g_svodidla [kN/m],
                 [[stale.liniova]] nazev, g, y, sirka
  [pohyblive]    Ve [t] nebo MLC + typ_MLC ("k" | "p") + dist (kolona), dyn, y_Ve,
                 roznos, t_voz, krok
  [vypocet]      ex
  [soucinitele]  gamma_G, gamma_G_inf, xi, gamma_Q, psi0, psi1, psi2
  [export]       slozka, vystup, kriterium, rezim, msu, L_nosniku, pb_vstup, t_stale,
                 t_vneseni
Relativní cesty (pb_vstup, slozka) se berou vůči vstupnímu souboru.
"""

from __future__ import annotations
import json
import os
import tomllib
from typing import Optional

from .prefabrikaty import prefabrikat
from .stale_zatizeni import Vybaveni, LiniovaZatizeni
from .vnitrni_sily import vnitrni_sily, Soucinitele, VysledekSil

_KONSTRUKCE = ("typ_konstrukce", "L", "N", "b", "Iy", "h", "beton", "E", "nu", "d", "spara",
               "b_s", "Iy_s", "beton_s", "E_s", "alfa", "sikmost", "uloz", "spoj",
               "beta_s_pevne")
_VYBAVENI = ("chodnik_L", "chodnik_P", "g_chodnik", "g_vozovka", "g_zabradli", "g_svodidla")


def nacti(cesta: str) -> dict:
    with open(cesta, encoding="utf-8-sig") as f:
        text = f.read()
    return json.loads(text) if cesta.lower().endswith(".json") else tomllib.loads(text)


def parametry(d: dict) -> dict:
    """Slovník vstupu → argumenty funkce vnitrni_sily."""
    k = dict(d.get("konstrukce", {}))
    kw = {}
    if k.get("prefabrikat"):
        p = prefabrikat(k["prefabrikat"])
        if p is None:
            raise ValueError(f"Neznámý prefabrikát '{k['prefabrikat']}'.")
        kw.update(L=p.L, b=p.b, Iy=p.Iy, spara=p.spara, b_s=p.b_s, Iy_s=p.Iy_s)
    kw.update({a: k[a] for a in _KONSTRUKCE if a in k})
    if "k_v" in k:
        kv = k["k_v"]
        kw["k_pod"] = float(kv) * 1000.0 if kv not in (None, "", 0) else None
    if "k_rot" in k:
        kr = k["k_rot"]
        kw["k_rot"] = float(kr) * 1000.0 if kr not in (None, "", 0) else None
    s = d.get("stale", {})
    kw["vybaveni"] = Vybaveni(
        **{a: float(s[a]) for a in _VYBAVENI if a in s},
        liniova=[LiniovaZatizeni(l.get("nazev", f"liniové {i + 1}"), float(l["g"]),
                                 float(l["y"]), float(l.get("sirka", 0.2)))
                 for i, l in enumerate(s.get("liniova", []))])
    for a in ("A_nosniku", "g0", "gamma_beton", "g_spary"):
        if a in s:
            kw[a] = s[a]
    p = d.get("pohyblive", {})
    for a in ("Ve", "MLC", "typ_MLC", "dist", "dyn", "y_Ve", "roznos", "t_voz", "krok"):
        if a in p:
            kw[a] = p[a]
    if "ex" in d.get("vypocet", {}):
        kw["ex"] = d["vypocet"]["ex"]
    if "soucinitele" in d:
        kw["soucinitele"] = Soucinitele(**d["soucinitele"])
    return kw


def spocti_ze_souboru(cesta: str, slozka: Optional[str] = None, pb_vstup: Optional[str] = None,
                      grafy: bool = True, tisk: bool = True):
    """Výpočet + uložení výsledků a exportu do posudku.  Vrací (VysledekSil, soubory)."""
    from .export_pb import uloz_vysledky
    d = nacti(cesta)
    zaklad = os.path.dirname(os.path.abspath(cesta))

    def cesta_k(p):
        return p if p is None or os.path.isabs(p) else os.path.join(zaklad, p)

    vys = vnitrni_sily(**parametry(d), tisk=tisk)
    e = dict(d.get("export", {}))
    slozka = slozka or cesta_k(e.get("slozka")) or os.path.join(
        zaklad, os.path.splitext(os.path.basename(cesta))[0] + "_vystup")
    soubory = uloz_vysledky(
        vys, slozka, vystup=e.get("vystup"), kriterium=e.get("kriterium", "M"),
        L_nosniku=e.get("L_nosniku"), rezim=e.get("rezim", "kombinace"),
        msu=e.get("msu", "6.10ab"), pb_vstup=pb_vstup or cesta_k(e.get("pb_vstup")),
        t_stale=e.get("t_stale"), t_vneseni=e.get("t_vneseni"))
    if grafy:
        soubory += uloz_grafy(vys, slozka, e.get("vystup"), e.get("kriterium", "M"))
    return vys, soubory


def uloz_grafy(vys: VysledekSil, slozka: str, vystup=None, kriterium: str = "M"):
    import matplotlib.pyplot as plt
    from .plotting_sily import plot_sily, plot_pricne
    o = vys.index(vystup) if vystup is not None else vys.rozhodujici(kriterium)
    out = []
    for nazev, fig in (("prubehy_sil.png", plot_sily(vys, o, show=False)),
                       ("pricne_rozdeleni.png", plot_pricne(vys, show=False))):
        p = os.path.join(slozka, nazev)
        fig.savefig(p, dpi=120)
        plt.close(fig)
        out.append(p)
    return out
