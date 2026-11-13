"""
__main__.py
===========
Spouštěcí skript Bridge Load Calculator.

Použití (ze složky repozitáře):
  python -m blc                  – spustí GUI
  python -m blc --demo           – ukázkový výpočet v konzoli + grafy do vystupy/demo
  python -m blc --demo --vystup DIR
  python -m blc --sily vstup.toml [--vystup DIR] [--pb posudek.toml]
                                 – vnitřní síly g0, g−g0, q pro posudek (export PB)
"""

import argparse
import os
import sys


def demo(vystup: str):
    """Ukázka: spojitý nosník 3 pole (10 + 14 + 10 m), 8 nosníků, MLC80, Ve = 80 t."""
    from . import porovnani_zatizeni
    from .prefabrikaty import prefabrikat
    from .plotting import (
        plot_obalky, plot_obalky_nosniky, plot_vyuziti_rezy, plot_pricny_roznos,
        plot_profily_nosniky, plot_zatizeni, plot_sit,
    )

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
    os.makedirs(vystup, exist_ok=True)

    def uloz(fig, nazev):
        fig.savefig(os.path.join(vystup, nazev), dpi=120)

    uloz(plot_obalky(cr, show=False), "obalky.png")
    uloz(plot_vyuziti_rezy(cr, show=False), "vyuziti.png")
    uloz(plot_pricny_roznos(cr, show=False), "pricny_roznos.png")
    fM, fV = plot_profily_nosniky(cr, show=False)
    uloz(fM, "profily_M.png"); uloz(fV, "profily_V.png")
    fM, fV = plot_obalky_nosniky(cr, "MLC", show=False)
    uloz(fM, "obalky_nosniky_MLC_M.png"); uloz(fV, "obalky_nosniky_MLC_V.png")
    uloz(plot_zatizeni(cr, cr.rezy.index(cr.rozhodujici_typ("M")), show=False), "zatizeni_M.png")
    uloz(plot_zatizeni(cr, cr.rezy.index(cr.rozhodujici_typ("V")), show=False), "zatizeni_V.png")
    uloz(plot_sit(cr, show=False), "sit_MKP.png")

    print("\n=== PŘÍKLAD SE SPÁROU – prefabrikát I-67 / 24, 2 pole ===\n")
    p = prefabrikat("I-67 / 24")
    porovnani_zatizeni(typ="k", MLC="MLC80", L=[p.L, p.L], n=20, dist=30.5, Ve=80.0,
                       N=8, beton="C45/55", beton_s="C30/37", Iy=p.Iy, b=p.b, d=1.0, spara=p.spara,
                       b_s=p.b_s, Iy_s=p.Iy_s, ex=0.25, obalky=False)
    print("\n=== PŘÍKLAD – ŠIKMÁ DESKA α = 120° (pravá), 12 m × 8 m, h = 0,5 m ===\n")
    porovnani_zatizeni(typ="k", MLC="MLC80", L=12.0, n=30, dist=30.5, Ve=80.0, N=1,
                       beton="C30/37", b=8.0, d=0.4, typ_konstrukce="deska", h=0.5,
                       alfa=120.0, sikmost="prava", k_pod=2.0e6, ex=0.25, obalky=False)
    print("\n=== OKRAJOVÉ PODMÍNKY – deska 20 × 10 m, α = 105°, vetknutí k_φ = 1000 MNm/rad/m ===\n")
    porovnani_zatizeni(typ="p", MLC="MLC80", L=20.0, n=20, dist=30.5, Ve=80.0, N=1,
                       beton="C35/45", b=10.0, d=0.5, typ_konstrukce="deska", h=0.5,
                       alfa=105.0, k_pod=2.0e6, uloz="vetknuti", k_rot=1.0e6,
                       ex=0.25, obalky=False)
    print(f"Grafy uloženy do {os.path.abspath(vystup)}")


def _utf8_vystup():
    """Výpis a nápověda v UTF-8 i při přesměrovaném výstupu ve Windows (jinak cp1250 → chyba u „−“, „η“ …)."""
    for proud in (sys.stdout, sys.stderr):
        if hasattr(proud, "reconfigure"):
            proud.reconfigure(encoding="utf-8")


def main(argv=None):
    _utf8_vystup()
    ap = argparse.ArgumentParser(prog="python -m blc",
                                 description="Bridge Load Calculator – přechodnost vozidel MLC vs Ve")
    ap.add_argument("--demo", action="store_true",
                    help="ukázkový výpočet v konzoli a uložení grafů (bez GUI)")
    ap.add_argument("--vystup", default=None,
                    help="výstupní složka (demo: vystupy/demo; --sily: podle vstupu)")
    ap.add_argument("--sily", metavar="VSTUP",
                    help="vnitřní síly g0, g−g0, q ze vstupu TOML/JSON a export do posudku PB")
    ap.add_argument("--pb", metavar="POSUDEK",
                    help="vstup Posudku PB (.toml) – vytvoří jeho kopii se zatížením z BLC")
    args = ap.parse_args(argv)
    if args.sily:
        import matplotlib
        matplotlib.use("Agg")
        from .vstup_sily import spocti_ze_souboru
        _, soubory = spocti_ze_souboru(args.sily, args.vystup, args.pb)
        print("Uloženo:")
        for s_ in soubory:
            print("  " + os.path.abspath(s_))
    elif args.demo:
        import matplotlib
        matplotlib.use("Agg")
        demo(args.vystup or os.path.join("vystupy", "demo"))
    else:
        from . import spustit_gui
        spustit_gui()


if __name__ == "__main__":
    sys.exit(main())
