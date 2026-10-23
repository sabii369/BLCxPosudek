"""Příkazová řádka: python -m pb_posudek vstup.toml [-o vystup]"""
from __future__ import annotations

import argparse
import sys

from .protokol import fmt
from .report import uloz_protokol
from .vstup import nacti_model


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pb_posudek",
                                 description="Posudek nosníku z předpjatého betonu (ČSN EN 1992-1-1)")
    ap.add_argument("vstup", nargs="?", help="vstupní soubor .toml nebo .json (bez argumentu se otevře GUI)")
    ap.add_argument("--gui", action="store_true", help="otevřít grafické rozhraní")
    ap.add_argument("-o", "--vystup", default="vystup", help="výstupní adresář (výchozí: vystup)")
    ap.add_argument("--bez-vlozenych-obrazku", action="store_true",
                    help="obrázky v HTML odkazovat do složky místo vložení")
    a = ap.parse_args(argv)
    if a.gui or a.vstup is None:
        from .gui import main as gui_main
        return gui_main([a.vstup] if a.vstup else [])
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    model = nacti_model(a.vstup)
    model.spocitej()
    out = uloz_protokol(model, a.vystup, embed=not a.bez_vlozenych_obrazku)
    print(f"{'MS':4} {'Posudek':42} {'Fáze':28} {'x [m]':>7} {'η':>7}")
    for v in model.protokol.posudky:
        print(f"{v.mezni_stav:4} {v.nazev[:42]:42} {v.faze[:28]:28} {fmt(v.x, 3) if v.x is not None else '–':>7} "
              f"{v.vyuziti * 100:6.1f}% {'OK' if v.vyhovuje else 'NEVYHOVUJE'}")
    ok = all(v.vyhovuje for v in model.protokol.posudky)
    print(f"\nProtokol: {out}\nCelkem: {'VYHOVUJE' if ok else 'NEVYHOVUJE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
