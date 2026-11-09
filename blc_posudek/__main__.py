"""
Spuštění spojeného programu BLC × Posudek PB.

  python -m blc_posudek                       GUI (otevře příklad priklady/most_KA67_12.toml)
  python -m blc_posudek soubor.toml --gui     GUI se souborem
  python -m blc_posudek soubor.toml [-o DIR]  dávkově: most (BLC) → posudek → HTML protokol
                                              + vnitřní síly mostu do DIR/most
  python -m blc_posudek soubor.toml --zatizitelnost   zatížitelnost: Ve pro η = 100 %
                                              každého mezního stavu (též [blc] zatizitelnost = true)
"""

from __future__ import annotations
import argparse
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m blc_posudek",
                                 description="BLC × Posudek PB – most → zatížení nosníku → posudek")
    ap.add_argument("vstup", nargs="?", help="vstupní soubor .toml / .json (bez něj se otevře GUI)")
    ap.add_argument("--gui", action="store_true", help="otevřít soubor v grafickém rozhraní")
    ap.add_argument("-o", "--vystup", default=None, help="výstupní složka (výchozí vystup_<soubor>)")
    ap.add_argument("--zatizitelnost", action="store_true",
                    help="místo posouzení hledat Ve pro využití 100 %% v každém mezním stavu")
    a = ap.parse_args(argv)
    if a.gui or a.vstup is None:
        from .gui import main as gui_main
        return gui_main([a.vstup] if a.vstup else [])
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    from blc.export_pb import uloz_vysledky
    from blc.vstup_sily import uloz_grafy
    from pb_posudek.protokol import fmt
    from .vypocet import nacti, spocti, uloz_protokol_most as uloz_protokol
    vystup = a.vystup or os.path.join(os.path.dirname(os.path.abspath(a.vstup)),
                                      "vystup_" + os.path.splitext(os.path.basename(a.vstup))[0])
    try:
        d = nacti(a.vstup)
        zat = a.zatizitelnost or bool(d.get("blc", {}).get("zatizitelnost"))
        if zat:
            from .zatizitelnost import zatizitelnost
            res = zatizitelnost(d, prubeh=lambda t: print(t, flush=True))
            vys, o, model = res.vys, res.o, res.model
        else:
            vys, o, model = spocti(d)
        out = uloz_protokol(model, vystup)
        most = os.path.join(vystup, "most")
        uloz_vysledky(vys, most, vystup=vys.popisky[o])
        uloz_grafy(vys, most, vys.popisky[o])
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"[CHYBA] {a.vstup}: {e}", file=sys.stderr)
        return 2
    print(f"Most: {vys.popis}\nVozidlo: {vys.vozidlo}; posuzovaný nosník {vys.popisky[o]}\n")
    if zat:
        print(f"{'MS':4} {'Posudek':42} {'Fáze':28} {'Ve [t]':>40}")
        for p in sorted(res.posudky, key=lambda p: (p.Ve is None, p.Ve or 0.0)):
            print(f"{p.klic[0]:4} {p.klic[1][:42]:42} {p.klic[2][:28]:28} {p.text:>40}")
        m = res.minimum()
        print(f"\nZatížitelnost: " + (f"Ve = {m.Ve:.1f} t – {m.klic[0]} {m.klic[1]} ({m.klic[2]})"
                                     if m else f"Ve > {res.Ve_max:.0f} t"))
        for t in res.poznamky:
            print("! " + t)
        print(f"Protokol (pro Ve = {vys.Ve:.1f} t): {out}\nVnitřní síly mostu: {most}")
        return 0
    print(f"{'MS':4} {'Posudek':42} {'Fáze':28} {'x [m]':>7} {'η':>7}")
    for v in model.protokol.posudky:
        print(f"{v.mezni_stav:4} {v.nazev[:42]:42} {v.faze[:28]:28} "
              f"{fmt(v.x, 3) if v.x is not None else '–':>7} {v.vyuziti * 100:6.1f}% "
              f"{'OK' if v.vyhovuje else 'NEVYHOVUJE'}")
    ok = all(v.vyhovuje for v in model.protokol.posudky)
    print(f"\nProtokol: {out}\nVnitřní síly mostu: {most}\nCelkem: {'VYHOVUJE' if ok else 'NEVYHOVUJE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
