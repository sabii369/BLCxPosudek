"""
main.py
=======
Spouštěcí skript pro bridge_load_calculator_v9 (spojitý nosník).

Použití:
  python main.py           – spustí GUI
  python main.py --demo    – ukázkový výpočet v konzoli + uložení grafů
"""

import sys
import os

# Přidej rodičovský adresář do cesty (pro import balíčku)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge_load_calculator_v9 import porovnani_zatizeni, spustit_gui
from bridge_load_calculator_v9.plotting import (
    plot_obalky, plot_obalky_nosniky, plot_vyuziti_rezy, plot_pricny_roznos,
    plot_profily_nosniky, plot_zatizeni, plot_sit,
)


def demo():
    """Ukázka: spojitý nosník 3 pole (10 + 14 + 10 m), 8 nosníků, MLC80, Ve = 80 t."""
    print("\n=== UKÁZKOVÝ VÝPOČET – SPOJITÝ NOSNÍK ===\n")
    cr = porovnani_zatizeni(
        typ="k", MLC="MLC80",
        L=[10.0, 14.0, 10.0],     # rozpětí polí [m]
        n=30,                     # poloh vozidla na pole
        dist=30.5,                # vzdálenost vozidel [m]
        Ve=80.0,                  # výjimečná zatížitelnost [t]
        N=8, beton="C35/45", Iy=0.0144, b=1.0, nu=0.2,
        d=0.55,                   # statická účinná výška [m]
        ex=0.25,
    )
    print("\nGeneruji grafy...")
    plot_obalky(cr, show=False).savefig("obalky.png", dpi=120)
    plot_vyuziti_rezy(cr, show=False).savefig("vyuziti.png", dpi=120)
    plot_pricny_roznos(cr, show=False).savefig("pricny_roznos.png", dpi=120)
    fM, fV = plot_profily_nosniky(cr, show=False)
    fM.savefig("profily_M.png", dpi=120); fV.savefig("profily_V.png", dpi=120)
    fM, fV = plot_obalky_nosniky(cr, "MLC", show=False)
    fM.savefig("obalky_nosniky_MLC_M.png", dpi=120); fV.savefig("obalky_nosniky_MLC_V.png", dpi=120)
    plot_zatizeni(cr, cr.rezy.index(cr.rozhodujici_typ("M")), show=False
                  ).savefig("zatizeni_M.png", dpi=120)
    plot_zatizeni(cr, cr.rezy.index(cr.rozhodujici_typ("V")), show=False
                  ).savefig("zatizeni_V.png", dpi=120)
    plot_sit(cr, show=False).savefig("sit_MKP.png", dpi=120)
    print("\n=== PŘÍKLAD SE SPÁROU – prefabrikát I-67 / 24, 2 pole ===\n")
    from bridge_load_calculator_v9.prefabrikaty import prefabrikat
    p = prefabrikat("I-67 / 24")
    porovnani_zatizeni(typ="k", MLC="MLC80", L=[p.L, p.L], n=20, dist=30.5, Ve=80.0,
                       N=8, beton="C45/55", beton_s="C30/37", Iy=p.Iy, b=p.b, d=1.0, spara=p.spara,
                       b_s=p.b_s, Iy_s=p.Iy_s, ex=0.25, obalky=False)
    print("\n=== PŘÍKLAD – ŠIKMÁ DESKA α = 120° (pravá), 12 m × 8 m, h = 0,5 m ===\n")
    porovnani_zatizeni(typ="k", MLC="MLC80", L=12.0, n=30, dist=30.5, Ve=80.0, N=1,
                       beton="C30/37", b=8.0, d=0.4, typ_konstrukce="deska", h=0.5,
                       alfa=120.0, sikmost="prava", k_pod=2.0e6, ex=0.25, obalky=False)
    print("\n=== v9: OKRAJOVÉ PODMÍNKY – deska 20 × 10 m, α = 105°, vetknutí k_φ = 1000 MNm/rad/m ===\n")
    porovnani_zatizeni(typ="p", MLC="MLC80", L=20.0, n=20, dist=30.5, Ve=80.0, N=1,
                       beton="C35/45", b=10.0, d=0.5, typ_konstrukce="deska", h=0.5,
                       alfa=105.0, k_pod=2.0e6, uloz="vetknuti", k_rot=1.0e6,
                       ex=0.25, obalky=False)
    print("Grafy uloženy: obalky.png, vyuziti.png, pricny_roznos.png, profily_M/V.png, "
          "obalky_nosniky_MLC_M/V.png, zatizeni_M.png, zatizeni_V.png, sit_MKP.png")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        spustit_gui()
