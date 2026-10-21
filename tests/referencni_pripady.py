"""
Referenční výpočty pro regresní test (tests/test_regrese.py).

Hodnoty v `referencni_hodnoty.json` jsou výsledky ověřeného stavu programu
(21. 10. 2026, 134/134 kontrol). Regresní test hlídá, že se výsledky nezmění
nechtěně. Při ZÁMĚRNÉ změně modelu je potřeba hodnoty přegenerovat:

    python tests/referencni_pripady.py

a změnu v JSON zkontrolovat v `git diff` a popsat v commitu.
"""
import json
import os
import sys

import numpy as np

SOUBOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "referencni_hodnoty.json")

_PROSTY = dict(n=60, dist=30.5, Ve=80, N=15, E=32000, Iy=0.0144, b=1, nu=0.2, ex=0.25, L=12)
_ZAKLAD = dict(typ="k", MLC="MLC80", L=[12, 14], n=10, dist=30.5, Ve=80, d=0.5, ex=0.25)
_SIKME_NOSNIKY = dict(N=5, Iy=0.0144, b=1.0, E=32000, alfa=110, spara=True, b_s=0.3, Iy_s=0.003)
_SIKMA_DESKA = dict(N=1, b=8.0, E=32000, typ_konstrukce="deska", h=0.5, alfa=110)

# název → parametry porovnani_zatizeni (bez tisk / obalky)
PRIPADY = {
    "prosty_nosnik_pasove_MLC80_d0": dict(typ="p", MLC="MLC80", d=0.0, **_PROSTY),
    "prosty_nosnik_pasove_MLC80_d2": dict(typ="p", MLC="MLC80", d=2.0, **_PROSTY),
    "prosty_nosnik_kolove_MLC40_d2": dict(typ="k", MLC="MLC40", d=2.0, **_PROSTY),
    "nosniky_kolme_2_pole": dict(typ="k", MLC="MLC80", L=[12, 14], n=15, dist=30.5, Ve=80,
                                 N=5, E=32000, Iy=0.0144, b=1.0, d=0.5, ex=0.25),
    "nosniky_sikme_110_spara": dict(**_ZAKLAD, **_SIKME_NOSNIKY),
    "nosniky_sikme_110_spara_kv": dict(**_ZAKLAD, **_SIKME_NOSNIKY, k_pod=2e6),
    "nosniky_sikme_110_spara_kv_beta_s_0": dict(**_ZAKLAD, **_SIKME_NOSNIKY, k_pod=2e6,
                                                beta_s_pevne=True),
    "deska_sikma_110": dict(**_ZAKLAD, **_SIKMA_DESKA),
    "deska_sikma_110_kv": dict(**_ZAKLAD, **_SIKMA_DESKA, k_pod=2e6),
    "deska_sikma_110_kv_beta_s_0": dict(**_ZAKLAD, **_SIKMA_DESKA, k_pod=2e6, beta_s_pevne=True),
    "nosniky_spara_mekke": dict(typ="k", MLC="MLC80", L=[12, 10], n=10, dist=30.5, Ve=80, N=5,
                                E=32000, Iy=0.0144, b=1.0, d=0.5, ex=0.25, spara=True,
                                b_s=0.3, Iy_s=0.003, uloz="mekke"),
    "deska_105_pruzne_vetknuti": dict(typ="p", MLC="MLC80", L=20.0, n=10, dist=30.5, Ve=80.0,
                                      N=1, beton="C35/45", b=10.0, d=0.5, typ_konstrukce="deska",
                                      h=0.5, alfa=105.0, k_pod=2.0e6, uloz="vetknuti",
                                      k_rot=1.0e6, ex=0.25),
}

# případ, u kterého se kontrolují i 2D obálky
PRIPAD_OBALKY = ("deska_sikma_obalky", dict(typ="k", MLC="MLC40", L=[12, 12], n=5, dist=30.5,
                                             Ve=40, N=1, beton="C30/37", b=8.0, d=0.4,
                                             typ_konstrukce="deska", h=0.5, alfa=110,
                                             uloz="vetknuti", k_rot=5e5, k_pod=2e6, ex=0.5,
                                             krok_obalky=1.0))


def vysledky_rezu(cr):
    return {r.rez.id: dict(MLC_1D=r.MLC_1D, Ve_1D=r.Ve_1D, MLC_2D=r.MLC_2D, Ve_2D=r.Ve_2D,
                           k_MLC=r.k_MLC, k_Ve=r.k_Ve) for r in cr.rezy}


def vysledky_obalek(cr):
    out = {}
    for nazev, ob in (("MLC", cr.ob_MLC), ("Ve", cr.ob_Ve)):
        for pole in ("M_max", "M_min", "Vp_max", "Vp_min"):
            a = np.asarray(getattr(ob, pole))
            out[f"{nazev}_{pole}"] = float(a.max() if pole.endswith("max") else a.min())
    return out


def spocti(porovnani_zatizeni, nazev):
    if nazev == PRIPAD_OBALKY[0]:
        cr = porovnani_zatizeni(**PRIPAD_OBALKY[1], obalky=True, tisk=False)
        return dict(rezy=vysledky_rezu(cr), obalky=vysledky_obalek(cr))
    cr = porovnani_zatizeni(**PRIPADY[nazev], obalky=False, tisk=False)
    return dict(rezy=vysledky_rezu(cr))


def vsechny_nazvy():
    return list(PRIPADY) + [PRIPAD_OBALKY[0]]


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from blc import porovnani_zatizeni
    data = {}
    for nazev in vsechny_nazvy():
        print("počítám", nazev)
        data[nazev] = spocti(porovnani_zatizeni, nazev)
    with open(SOUBOR, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("uloženo", SOUBOR)
